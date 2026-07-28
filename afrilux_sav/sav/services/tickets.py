from datetime import timedelta

from django.db.models import Count, Q
from django.utils import timezone

from ..comms import (
    create_external_channel_notifications,
    create_sav_event_notifications,
    deliver_notification,
)
from ..models import (
    EquipmentLocationHistory,
    MaintenanceTicket,
    Message,
    Notification,
    Product,
    Ticket,
    TicketAssignment,
    User,
)
from .roles import (
    can_drive_ticket_workflow,
    can_record_ticket_intervention,
    is_manager_user,
    is_read_only_user,
    should_scope_to_agency,
)
from .audit import log_audit_event
from .constants import (
    ESCALATION_ALLOWED_TARGETS,
    ESCALATION_TARGET_CHIEF_TECHNICIAN,
    ESCALATION_TARGET_EXPERT_THEN_HEAD_SAV,
    ESCALATION_TARGET_HEAD_SAV,
    ESCALATION_TARGET_ROLE_MAP,
    ESCALATION_PRIORITY_SEQUENCE,
    MAINTENANCE_ASSIGNMENT_BLOCKING_STATUSES,
    MAINTENANCE_NEAR_TERM_BLOCKING_STATUSES,
    OPEN_TICKET_STATUSES,
    SAV_ASSIGNMENT_BLOCKING_STATUSES,
)
from .users import compute_ticket_sla_deadline


def organization_for_instance(instance):
    if instance is None:
        return None
    organization = getattr(instance, "organization", None)
    if organization is not None:
        return organization
    for attr_name in ["ticket", "product", "client", "recipient", "user", "actor", "rule"]:
        related = getattr(instance, attr_name, None)
        if related is not None and getattr(related, "organization", None) is not None:
            return related.organization
    return None


def manager_queryset_for_organization(organization=None):
    queryset = User.objects.filter(is_active=True).filter(Q(role__in=User.MANAGER_ROLES) | Q(is_superuser=True))
    if organization is None:
        return queryset
    scoped_queryset = queryset.filter(Q(organization=organization) | Q(is_superuser=True))
    if scoped_queryset.exists():
        return scoped_queryset
    return queryset.filter(Q(organization__isnull=True) | Q(is_superuser=True))


def assignment_eligible_queryset_for_organization(organization=None):
    queryset = User.objects.filter(
        role__in=User.ASSIGNABLE_ROLES,
        technician_status="available",
        is_active=True,
    )
    if organization is None:
        return queryset
    scoped_queryset = queryset.filter(organization=organization)
    if scoped_queryset.exists():
        return scoped_queryset
    return queryset.filter(organization__isnull=True)


def field_technician_queryset_for_organization(organization=None):
    queryset = User.objects.filter(
        role=User.ROLE_TECHNICIAN,
        technician_status="available",
        is_active=True,
    )
    if organization is None:
        return queryset
    scoped_queryset = queryset.filter(organization=organization)
    if scoped_queryset.exists():
        return scoped_queryset
    return queryset.filter(organization__isnull=True)


def transfer_product_location(
    *,
    product,
    to_client=None,
    to_site=None,
    to_location="",
    to_location_status=Product.LOCATION_INSTALLED,
    moved_by=None,
    reason="",
):
    """Transfere un equipement vers un nouveau client, site ou statut.

    Cree un historique de localisation, met a jour l'equipement et journalise
    l'action dans l'audit.
    """
    if to_site is not None:
        to_client = to_site.client
        if not to_location:
            to_location = to_site.address
    if to_client is None:
        to_client = product.client
    if to_location_status not in {choice[0] for choice in Product.LOCATION_STATUS_CHOICES}:
        raise ValueError("Statut de localisation equipement invalide.")
    if product.organization_id and to_client.organization_id and product.organization_id != to_client.organization_id:
        raise ValueError("Impossible de transferer un equipement vers une autre organisation.")
    if to_site is not None and to_site.client_id != to_client.id:
        raise ValueError("Le site cible n'appartient pas au client cible.")
    if moved_by is not None and not getattr(moved_by, "is_authenticated", False):
        raise ValueError("L'utilisateur qui effectue le transfert doit etre authentifie.")

    history = EquipmentLocationHistory.objects.create(
        product=product,
        from_client=product.client,
        from_site=product.site,
        from_location=product.detailed_location or product.installation_address,
        from_location_status=product.location_status,
        to_client=to_client,
        to_site=to_site,
        to_location=to_location,
        to_location_status=to_location_status,
        moved_by=moved_by if getattr(moved_by, "is_authenticated", False) else None,
        reason=reason,
    )
    product.client = to_client
    product.site = to_site
    product.location_status = to_location_status
    if to_location:
        product.detailed_location = to_location
    if to_site and to_site.address:
        product.installation_address = to_site.address
    product.save()
    log_audit_event(
        actor=moved_by if getattr(moved_by, "is_authenticated", False) else None,
        action="equipment_location_transferred",
        instance=product,
        details={
            "history_id": history.id,
            "to_client_id": to_client.id if to_client else None,
            "to_site_id": to_site.id if to_site else None,
            "to_location_status": to_location_status,
        },
    )
    return history


def _select_least_loaded_agent_for_roles(*, roles, organization=None, exclude_user_ids=None):
    exclude_user_ids = [user_id for user_id in (exclude_user_ids or []) if user_id]
    queryset = User.objects.filter(is_active=True, role__in=roles)
    if organization is not None:
        scoped_queryset = queryset.filter(organization=organization)
        if scoped_queryset.exists():
            queryset = scoped_queryset
        else:
            queryset = queryset.filter(organization__isnull=True)
    if exclude_user_ids:
        queryset = queryset.exclude(pk__in=exclude_user_ids)
    return (
        queryset
        .annotate(
            open_ticket_count=Count(
                "assigned_tickets",
                filter=Q(assigned_tickets__status__in=OPEN_TICKET_STATUSES),
            )
        )
        .order_by("open_ticket_count", "id")
        .first()
    )


def next_ticket_priority(priority):
    priority = (priority or Ticket.PRIORITY_NORMAL).strip().lower()
    try:
        current_index = ESCALATION_PRIORITY_SEQUENCE.index(priority)
    except ValueError:
        return Ticket.PRIORITY_HIGH
    if current_index >= len(ESCALATION_PRIORITY_SEQUENCE) - 1:
        return ESCALATION_PRIORITY_SEQUENCE[-1]
    return ESCALATION_PRIORITY_SEQUENCE[current_index + 1]


def select_escalation_agent(ticket, *, target=ESCALATION_TARGET_CHIEF_TECHNICIAN):
    current_agent = getattr(ticket, "assigned_agent", None)
    exclude_ids = [getattr(current_agent, "id", None)]
    normalized_target = (target or ESCALATION_TARGET_CHIEF_TECHNICIAN).strip().lower()
    if normalized_target == ESCALATION_TARGET_EXPERT_THEN_HEAD_SAV:
        expert = _select_least_loaded_agent_for_roles(
            roles=ESCALATION_TARGET_ROLE_MAP[ESCALATION_TARGET_EXPERT_THEN_HEAD_SAV],
            organization=ticket.organization,
            exclude_user_ids=exclude_ids,
        )
        if expert:
            return expert
        return _select_least_loaded_agent_for_roles(
            roles=ESCALATION_TARGET_ROLE_MAP[ESCALATION_TARGET_HEAD_SAV],
            organization=ticket.organization,
            exclude_user_ids=exclude_ids,
        )
    roles = ESCALATION_TARGET_ROLE_MAP.get(normalized_target)
    if roles:
        return _select_least_loaded_agent_for_roles(
            roles=roles,
            organization=ticket.organization,
            exclude_user_ids=exclude_ids,
        )

    return None


def create_notification(recipient, subject, message, channel=Notification.CHANNEL_IN_APP, event_type="info", ticket=None):
    notification = Notification.objects.create(
        recipient=recipient,
        ticket=ticket,
        channel=channel,
        event_type=event_type,
        subject=subject,
        message=message,
        status=Notification.STATUS_PENDING,
    )
    deliver_notification(notification)
    return notification


def notify_client_created_ticket(ticket, *, actor=None):
    managers = list(manager_queryset_for_organization(ticket.organization))
    if not managers:
        return []
    notifications = create_sav_event_notifications(
        managers,
        ticket=ticket,
        event_type="ticket_created_by_client",
        subject=f"Nouveau ticket client {ticket.reference}",
        message=(
            f"Nouveau ticket cree par {ticket.client}. "
            f"Client: {ticket.client}. "
            f"Panne: {ticket.title}. "
            "Affectation responsable requise."
        ),
    )
    log_audit_event(
        actor=actor,
        action="ticket_client_created_notifications",
        instance=ticket,
        details={"notifications": [item.id for item in notifications]},
    )
    return notifications


def sync_ticket_assignment(ticket, *, assigned_by=None, note="", release_status=TicketAssignment.STATUS_RELEASED):
    active_assignments = list(
        TicketAssignment.objects.filter(
            ticket=ticket,
            status=TicketAssignment.STATUS_ACTIVE,
            released_at__isnull=True,
        ).select_related("technician")
    )
    now = timezone.now()
    current_assignment = None
    created = False
    released_ids = []

    for assignment in active_assignments:
        if ticket.assigned_agent_id and assignment.technician_id == ticket.assigned_agent_id:
            current_assignment = assignment
            continue
        assignment.status = release_status
        assignment.released_at = now
        if note:
            assignment.note = note[:500]
        assignment.save(update_fields=["status", "released_at", "note", "updated_at"])
        released_ids.append(assignment.id)

    if ticket.assigned_agent_id and current_assignment is None:
        current_assignment = TicketAssignment.objects.create(
            organization=ticket.organization,
            ticket=ticket,
            technician=ticket.assigned_agent,
            assigned_by=assigned_by if getattr(assigned_by, "is_authenticated", False) else None,
            assigned_at=now,
            note=note[:500],
        )
        created = True

    return current_assignment, created, released_ids


def escalate_ticket(
    ticket,
    *,
    actor=None,
    note="",
    target=ESCALATION_TARGET_CHIEF_TECHNICIAN,
    increase_priority=True,
    notification_event_type="ticket_escalated",
):
    if ticket.status not in OPEN_TICKET_STATUSES:
        raise ValueError("Seuls les tickets ouverts peuvent etre escalades.")

    previous_priority = ticket.priority
    previous_status = ticket.status
    previous_assigned_agent = ticket.assigned_agent
    if not is_manager_user(actor):
        raise ValueError("Seul le Responsable SAV peut escalader un ticket.")
    normalized_target = (target or ESCALATION_TARGET_CHIEF_TECHNICIAN).strip().lower()
    if normalized_target not in ESCALATION_ALLOWED_TARGETS:
        raise ValueError("Cible d'escalade invalide. Cibles autorisees: CFAO, travaux CFAO, superviseur, expert ou Responsable SAV.")
    escalation_target = select_escalation_agent(ticket, target=normalized_target)
    escalation_note = (note or "Escalade du ticket pour prise en charge de niveau superieur.").strip()[:500]

    if escalation_target is None:
        raise ValueError("Aucun utilisateur disponible pour recevoir cette escalade.")

    if increase_priority:
        ticket.priority = next_ticket_priority(ticket.priority)
    ticket.assigned_agent = escalation_target
    if previous_assigned_agent is None or previous_assigned_agent.id != escalation_target.id:
        ticket.status = Ticket.STATUS_ASSIGNED
    ticket.sla_deadline = compute_ticket_sla_deadline(ticket.priority, organization=ticket.organization)
    ticket.save(update_fields=["priority", "assigned_agent", "status", "sla_deadline", "updated_at"])

    assignment = None
    created_assignment = False
    released_ids = []
    if previous_assigned_agent is not None and previous_assigned_agent.id != ticket.assigned_agent_id:
        assignment, created_assignment, released_ids = sync_ticket_assignment(
            ticket,
            assigned_by=actor,
            note=escalation_note,
            release_status=TicketAssignment.STATUS_ESCALATED,
        )
    if ticket.assigned_agent_id:
        from .interventions import ensure_assignment_intervention
        intervention_result = ensure_assignment_intervention(ticket, actor=actor, note=escalation_note)
        assignment = assignment or intervention_result.get("assignment")
        created_assignment = created_assignment or intervention_result.get("created_assignment", False)

    from .analytics import calculate_sentiment
    Message.objects.create(
        ticket=ticket,
        sender=actor if getattr(actor, "is_authenticated", False) else ticket.assigned_agent or ticket.client,
        message_type=Message.TYPE_INTERNAL,
        channel=Message.CHANNEL_PORTAL,
        direction=Message.DIRECTION_INTERNAL,
        content=(
            "Le ticket a ete escalade."
            f"{' Priorite: ' + previous_priority + ' -> ' + ticket.priority + '.' if previous_priority != ticket.priority else ''}"
            f"{' Nouveau referent: ' + str(ticket.assigned_agent) + '.' if ticket.assigned_agent else ''}"
        ),
        sentiment_score=calculate_sentiment("Le ticket a ete escalade."),
    )

    recipients = []
    if ticket.assigned_agent_id:
        recipients.append(ticket.assigned_agent)
    if previous_assigned_agent is not None:
        recipients.append(previous_assigned_agent)
    if getattr(actor, "is_authenticated", False):
        recipients.append(actor)
    deduped_recipients = {recipient.id: recipient for recipient in recipients if getattr(recipient, "id", None)}
    for recipient in deduped_recipients.values():
        create_external_channel_notifications(
            recipient=recipient,
            ticket=ticket,
            event_type=notification_event_type,
            subject=f"Ticket escalade {ticket.reference}",
            message=(
                f"Le ticket '{ticket.title}' a ete escalade avec une priorite {ticket.get_priority_display().lower()}."
                f"{' Nouveau referent: ' + str(ticket.assigned_agent) + '.' if ticket.assigned_agent else ''}"
            ),
        )

    log_audit_event(
        actor,
        "ticket_escalated",
        ticket,
        {
            "previous_priority": previous_priority,
            "new_priority": ticket.priority,
            "previous_status": previous_status,
            "new_status": ticket.status,
            "previous_assigned_agent": getattr(previous_assigned_agent, "id", None),
            "assigned_agent": ticket.assigned_agent_id,
            "target": normalized_target,
            "released_assignment_ids": released_ids,
            "created_assignment": created_assignment,
        },
    )

    return {
        "ticket_id": ticket.id,
        "reference": ticket.reference,
        "previous_priority": previous_priority,
        "priority": ticket.priority,
        "previous_status": previous_status,
        "status": ticket.status,
        "previous_assigned_agent": str(previous_assigned_agent) if previous_assigned_agent else None,
        "assigned_agent": str(ticket.assigned_agent) if ticket.assigned_agent else None,
        "target": normalized_target,
        "released_assignment_ids": released_ids,
        "created_assignment": created_assignment,
        "assignment_id": getattr(assignment, "id", None),
    }


def can_assign_ticket_technician(user, ticket):
    if not user or not user.is_authenticated or is_read_only_user(user):
        return False
    if is_manager_user(user):
        return True
    return bool(user.role in set(User.ESCALATION_TARGET_ROLES) and ticket.assigned_agent_id == user.id)


def _maintenance_blocks_assignment(maintenance_ticket, *, now=None):
    now = now or timezone.now()
    if maintenance_ticket.status in MAINTENANCE_ASSIGNMENT_BLOCKING_STATUSES:
        return True
    if maintenance_ticket.status in MAINTENANCE_NEAR_TERM_BLOCKING_STATUSES:
        return maintenance_ticket.scheduled_date <= now + timedelta(days=1)
    return False


def technician_assignment_conflicts(technician, *, exclude_ticket=None, exclude_maintenance_ticket=None):
    conflicts = []
    now = timezone.now()
    ticket_queryset = (
        Ticket.objects
        .select_related("client")
        .filter(status__in=SAV_ASSIGNMENT_BLOCKING_STATUSES)
        .filter(Q(assigned_agent=technician) | Q(team_leader=technician) | Q(team_members=technician))
        .distinct()
    )
    if exclude_ticket is not None and exclude_ticket.pk:
        ticket_queryset = ticket_queryset.exclude(pk=exclude_ticket.pk)

    for ticket in ticket_queryset.order_by("sla_deadline", "created_at")[:8]:
        conflicts.append(
            {
                "type": "sav",
                "label": "SAV",
                "id": ticket.id,
                "reference": ticket.reference,
                "title": ticket.title,
                "status": ticket.status,
                "status_label": ticket.get_status_display(),
                "scheduled_at": ticket.sla_deadline,
            }
        )

    maintenance_queryset = (
        MaintenanceTicket.objects
        .select_related("client", "technician")
        .filter(Q(technician=technician) | Q(team_members=technician))
        .exclude(status__in=[
            MaintenanceTicket.STATUS_DONE,
            MaintenanceTicket.STATUS_ANOMALY,
            MaintenanceTicket.STATUS_CANCELLED,
        ])
        .distinct()
    )
    if exclude_maintenance_ticket is not None and exclude_maintenance_ticket.pk:
        maintenance_queryset = maintenance_queryset.exclude(pk=exclude_maintenance_ticket.pk)

    for maintenance_ticket in maintenance_queryset.order_by("scheduled_date", "created_at")[:12]:
        if not _maintenance_blocks_assignment(maintenance_ticket, now=now):
            continue
        conflicts.append(
            {
                "type": "maintenance",
                "label": "Maintenance",
                "id": maintenance_ticket.id,
                "reference": f"MAINT-{maintenance_ticket.id}",
                "title": maintenance_ticket.title,
                "status": maintenance_ticket.status,
                "status_label": maintenance_ticket.get_status_display(),
                "scheduled_at": maintenance_ticket.scheduled_date,
            }
        )

    return conflicts


def technician_is_assignable(technician, *, exclude_ticket=None, exclude_maintenance_ticket=None):
    if not technician or not technician.is_ticket_assignment_eligible:
        return False
    return not technician_assignment_conflicts(
        technician,
        exclude_ticket=exclude_ticket,
        exclude_maintenance_ticket=exclude_maintenance_ticket,
    )


def format_assignment_conflicts(conflicts):
    parts = []
    for item in conflicts:
        date_label = ""
        if item.get("scheduled_at"):
            date_label = f" ({timezone.localtime(item['scheduled_at']):%d/%m/%Y %H:%M})"
        parts.append(f"{item['label']} {item['reference']} - {item['status_label']}{date_label}")
    return "; ".join(parts)


def serialize_assignment_conflicts(conflicts):
    serialized = []
    for item in conflicts:
        payload = dict(item)
        scheduled_at = payload.get("scheduled_at")
        if scheduled_at:
            payload["scheduled_at"] = timezone.localtime(scheduled_at).isoformat()
        serialized.append(payload)
    return serialized


def validate_technician_assignment_availability(
    technician,
    *,
    actor=None,
    exclude_ticket=None,
    exclude_maintenance_ticket=None,
    force=False,
    force_reason="",
):
    conflicts = technician_assignment_conflicts(
        technician,
        exclude_ticket=exclude_ticket,
        exclude_maintenance_ticket=exclude_maintenance_ticket,
    )
    if not conflicts:
        return []
    if force:
        if not is_manager_user(actor):
            raise ValueError("Seul le Responsable SAV peut forcer une affectation sur technicien occupe.")
        if not (force_reason or "").strip():
            raise ValueError("Le motif est obligatoire pour forcer une affectation.")
        return conflicts
    raise ValueError(
        f"{technician} est indisponible. Interventions actives: {format_assignment_conflicts(conflicts)}"
    )


def assign_ticket_to_technician(ticket, technician, *, actor=None, note="", force=False, force_reason=""):
    if ticket.status not in OPEN_TICKET_STATUSES:
        raise ValueError("Seuls les tickets ouverts peuvent etre affectes.")
    if not can_assign_ticket_technician(actor, ticket):
        raise ValueError("Seul le Responsable SAV ou le responsable escalade sur ce ticket peut affecter un technicien.")
    if not technician or technician.role not in set(User.ASSIGNABLE_ROLES):
        raise ValueError("La cible doit etre un technicien ou agent SAV habilite.")
    if not technician.is_ticket_assignment_eligible:
        raise ValueError("La cible doit etre active et disponible.")
    if ticket.organization_id and technician.organization_id and ticket.organization_id != technician.organization_id:
        raise ValueError("Le technicien doit appartenir a la meme organisation que le ticket.")
    if should_scope_to_agency(actor):
        ticket_agency_ids = {
            item
            for item in [
                getattr(ticket.client, "agency_id", None),
                getattr(getattr(ticket.product, "client", None), "agency_id", None),
                getattr(getattr(ticket.product, "site", None), "agency_id", None),
            ]
            if item
        }
        if technician.agency_id and technician.agency_id != actor.agency_id:
            raise ValueError("Le technicien cible appartient a une autre agence.")
        if ticket_agency_ids and actor.agency_id not in ticket_agency_ids:
            raise ValueError("Ce ticket appartient a une autre agence.")
    conflicts = validate_technician_assignment_availability(
        technician,
        actor=actor,
        exclude_ticket=ticket,
        force=force,
        force_reason=force_reason,
    )

    previous_status = ticket.status
    previous_assigned_agent = ticket.assigned_agent
    assignment_note = (note or "Affectation du ticket a un technicien ou agent SAV.").strip()[:500]

    ticket.assigned_agent = technician
    ticket.team_leader = None
    ticket.is_team_intervention = False
    if ticket.status in {
        Ticket.STATUS_NEW,
        Ticket.STATUS_PENDING_ASSIGNMENT,
        Ticket.STATUS_REASSIGN_REQUIRED,
        Ticket.STATUS_REASSIGNED,
        Ticket.STATUS_ASSIGNED,
        Ticket.STATUS_TEAM_PENDING,
        Ticket.STATUS_TEAM_READY,
    }:
        ticket.status = Ticket.STATUS_ASSIGNED
    ticket.save(update_fields=["assigned_agent", "team_leader", "is_team_intervention", "status", "updated_at"])
    ticket.team_members.clear()
    from .interventions import ensure_assignment_intervention
    intervention_result = ensure_assignment_intervention(ticket, actor=actor, note=assignment_note)

    from .analytics import calculate_sentiment
    Message.objects.create(
        ticket=ticket,
        sender=actor if getattr(actor, "is_authenticated", False) else technician,
        message_type=Message.TYPE_INTERNAL,
        channel=Message.CHANNEL_PORTAL,
        direction=Message.DIRECTION_INTERNAL,
        content=f"Le ticket a ete affecte a {technician}.",
        sentiment_score=calculate_sentiment("Le ticket a ete affecte a un agent SAV."),
    )

    recipients = [technician]
    if previous_assigned_agent is not None and previous_assigned_agent.id != technician.id:
        recipients.append(previous_assigned_agent)
    if getattr(actor, "is_authenticated", False):
        recipients.append(actor)
    deduped_recipients = {recipient.id: recipient for recipient in recipients if getattr(recipient, "id", None)}
    for recipient in deduped_recipients.values():
        create_external_channel_notifications(
            recipient=recipient,
            ticket=ticket,
            event_type="ticket_technician_assigned",
            subject=f"Technicien affecte {ticket.reference}",
            message=f"Le ticket '{ticket.title}' est maintenant affecte a {technician}.",
        )

    log_audit_event(
        actor,
        "ticket_technician_assigned",
        ticket,
        {
            "previous_status": previous_status,
            "new_status": ticket.status,
            "previous_assigned_agent": getattr(previous_assigned_agent, "id", None),
            "technician": technician.id,
            "forced": bool(force and conflicts),
            "force_reason": (force_reason or "").strip(),
            "conflicts": serialize_assignment_conflicts(conflicts),
            "created_assignment": intervention_result.get("created_assignment", False),
            "assignment_id": getattr(intervention_result.get("assignment"), "id", None),
        },
    )

    return {
        "ticket_id": ticket.id,
        "reference": ticket.reference,
        "previous_status": previous_status,
        "status": ticket.status,
        "previous_assigned_agent": str(previous_assigned_agent) if previous_assigned_agent else None,
        "assigned_agent": str(ticket.assigned_agent) if ticket.assigned_agent else None,
        "forced": bool(force and conflicts),
        "conflicts": serialize_assignment_conflicts(conflicts),
        "assignment_id": getattr(intervention_result.get("assignment"), "id", None),
        "created_assignment": intervention_result.get("created_assignment", False),
    }


def assign_ticket_to_team(ticket, *, leader, members, actor=None, note="", force=False, force_reason=""):
    if ticket.status not in OPEN_TICKET_STATUSES:
        raise ValueError("Seuls les tickets ouverts peuvent etre affectes.")
    if not can_assign_ticket_technician(actor, ticket):
        raise ValueError("Seul le Responsable SAV peut constituer une equipe.")
    members = list(members or [])
    if not leader:
        raise ValueError("Un chef d'equipe est obligatoire.")
    if leader.role not in set(User.ASSIGNABLE_ROLES):
        raise ValueError("Le chef d'equipe doit etre un technicien habilite.")
    if not leader.is_ticket_assignment_eligible:
        raise ValueError("Le chef d'equipe doit etre disponible.")
    member_ids = {member.id for member in members if member and member.id != leader.id}
    members = list(User.objects.filter(id__in=member_ids, role__in=User.ASSIGNABLE_ROLES, is_active=True))
    if not members:
        raise ValueError("Une equipe doit contenir au moins un membre en plus du chef.")
    if ticket.organization_id:
        selected = [leader, *members]
        if any(member.organization_id and member.organization_id != ticket.organization_id for member in selected):
            raise ValueError("Tous les techniciens doivent appartenir a la meme organisation que le ticket.")
    selected_technicians = [leader, *members]
    forced_conflicts = {}
    for technician in selected_technicians:
        if not technician.is_ticket_assignment_eligible:
            raise ValueError(f"{technician} n'est pas disponible.")
        conflicts = validate_technician_assignment_availability(
            technician,
            actor=actor,
            exclude_ticket=ticket,
            force=force,
            force_reason=force_reason,
        )
        if conflicts:
            forced_conflicts[technician.id] = conflicts

    previous_status = ticket.status
    previous_assigned_agent = ticket.assigned_agent
    ticket.assigned_agent = leader
    ticket.team_leader = leader
    ticket.is_team_intervention = True
    ticket.status = Ticket.STATUS_TEAM_READY
    ticket.save(update_fields=["assigned_agent", "team_leader", "is_team_intervention", "status", "updated_at"])
    ticket.team_members.set(members)
    from .interventions import ensure_assignment_intervention
    intervention_result = ensure_assignment_intervention(ticket, actor=actor, note=note or "Equipe constituee pour intervention SAV.")

    from .analytics import calculate_sentiment
    Message.objects.create(
        ticket=ticket,
        sender=actor if getattr(actor, "is_authenticated", False) else leader,
        message_type=Message.TYPE_INTERNAL,
        channel=Message.CHANNEL_PORTAL,
        direction=Message.DIRECTION_INTERNAL,
        content=f"Equipe constituee. Chef: {leader}. Membres: {', '.join(str(member) for member in members)}.",
        sentiment_score=calculate_sentiment("Equipe constituee pour intervention SAV."),
    )

    recipients = {leader.id: leader, **{member.id: member for member in members}}
    if previous_assigned_agent is not None and previous_assigned_agent.id not in recipients:
        recipients[previous_assigned_agent.id] = previous_assigned_agent
    for recipient in recipients.values():
        create_external_channel_notifications(
            recipient=recipient,
            ticket=ticket,
            event_type="ticket_team_assigned",
            subject=f"Equipe affectee {ticket.reference}",
            message=f"Vous faites partie de l'equipe affectee au ticket '{ticket.title}'.",
        )

    log_audit_event(
        actor,
        "ticket_team_assigned",
        ticket,
        {
            "previous_status": previous_status,
            "new_status": ticket.status,
            "leader": leader.id,
            "members": [member.id for member in members],
            "forced": bool(force and forced_conflicts),
            "force_reason": (force_reason or "").strip(),
            "conflicts": {
                str(technician_id): serialize_assignment_conflicts(conflicts)
                for technician_id, conflicts in forced_conflicts.items()
            },
            "assignment_id": getattr(intervention_result.get("assignment"), "id", None),
        },
    )
    return {
        "ticket_id": ticket.id,
        "reference": ticket.reference,
        "previous_status": previous_status,
        "status": ticket.status,
        "leader": str(leader),
        "members": [str(member) for member in members],
        "forced": bool(force and forced_conflicts),
        "conflicts": {
            str(technician_id): serialize_assignment_conflicts(conflicts)
            for technician_id, conflicts in forced_conflicts.items()
        },
        "assignment_id": getattr(intervention_result.get("assignment"), "id", None),
    }


def request_ticket_escalation(ticket, *, actor=None, reason=""):
    if ticket.status not in OPEN_TICKET_STATUSES or ticket.status in {Ticket.STATUS_DONE, Ticket.STATUS_CLOSED}:
        raise ValueError("Ce ticket ne peut plus etre escalade.")
    if not can_record_ticket_intervention(actor, ticket):
        raise ValueError("Seul un intervenant du ticket peut demander l'aide du responsable.")
    normalized_reason = (reason or "").strip()
    if not normalized_reason:
        raise ValueError("Le motif d'escalade est obligatoire.")
    if (
        ticket.is_team_intervention
        and ticket.team_members.filter(pk=getattr(actor, "pk", None)).exists()
        and ticket.team_leader_id != getattr(actor, "id", None)
        and not is_manager_user(actor)
    ):
        from .analytics import calculate_sentiment
        Message.objects.create(
            ticket=ticket,
            sender=actor,
            message_type=Message.TYPE_INTERNAL,
            channel=Message.CHANNEL_PORTAL,
            direction=Message.DIRECTION_INTERNAL,
            content=f"Demande d'aide au chef d'equipe: {normalized_reason}",
            sentiment_score=calculate_sentiment(normalized_reason),
        )
        if ticket.team_leader_id:
            create_external_channel_notifications(
                recipient=ticket.team_leader,
                ticket=ticket,
                event_type="ticket_team_member_help_requested",
                subject=f"Aide membre equipe {ticket.reference}",
                message=f"{actor} demande de l'aide: {normalized_reason}",
            )
        log_audit_event(actor, "ticket_team_member_help_requested", ticket, {"reason": normalized_reason})
        return {"status": ticket.status, "team_leader_notified": bool(ticket.team_leader_id)}
    previous_status = ticket.status
    ticket.escalation_count = (ticket.escalation_count or 0) + 1
    ticket.last_escalation_at = timezone.now()
    ticket.last_escalation_reason = normalized_reason
    ticket.status_before_escalation = previous_status if previous_status != Ticket.STATUS_ESCALATED else ticket.status_before_escalation
    if ticket.escalation_count > 3:
        ticket.status = Ticket.STATUS_BLOCKED_DIRECTION
    else:
        ticket.status = Ticket.STATUS_ESCALATED
    ticket.save(
        update_fields=[
            "status",
            "escalation_count",
            "last_escalation_at",
            "last_escalation_reason",
            "status_before_escalation",
            "updated_at",
        ]
    )
    from .analytics import calculate_sentiment
    Message.objects.create(
        ticket=ticket,
        sender=actor,
        message_type=Message.TYPE_INTERNAL,
        channel=Message.CHANNEL_PORTAL,
        direction=Message.DIRECTION_INTERNAL,
        content=f"Demande d'aide responsable: {normalized_reason}",
        sentiment_score=calculate_sentiment(normalized_reason),
    )
    for manager in manager_queryset_for_organization(ticket.organization):
        create_external_channel_notifications(
            recipient=manager,
            ticket=ticket,
            event_type="ticket_escalation_requested",
            subject=f"Escalade {ticket.reference}",
            message=f"{actor} demande une aide responsable sur '{ticket.title}'. Motif: {normalized_reason}",
        )
    log_audit_event(
        actor,
        "ticket_escalation_requested",
        ticket,
        {
            "previous_status": previous_status,
            "new_status": ticket.status,
            "reason": normalized_reason,
            "escalation_count": ticket.escalation_count,
        },
    )
    return {"status": ticket.status, "previous_status": previous_status, "escalation_count": ticket.escalation_count}


def provide_escalation_solution(ticket, *, actor=None, solution=""):
    if not is_manager_user(actor):
        raise ValueError("Seul le Responsable SAV peut traiter une escalade.")
    if ticket.status != Ticket.STATUS_ESCALATED:
        raise ValueError("Le ticket doit etre en escalade.")
    normalized_solution = (solution or "").strip()
    if not normalized_solution:
        raise ValueError("La solution du responsable est obligatoire.")
    previous_status = ticket.status
    ticket.status = Ticket.STATUS_WAITING_SOLUTION
    ticket.save(update_fields=["status", "updated_at"])
    from .analytics import calculate_sentiment
    Message.objects.create(
        ticket=ticket,
        sender=actor,
        message_type=Message.TYPE_INTERNAL,
        channel=Message.CHANNEL_PORTAL,
        direction=Message.DIRECTION_INTERNAL,
        content=f"Solution responsable: {normalized_solution}",
        sentiment_score=calculate_sentiment(normalized_solution),
    )
    recipients = []
    if ticket.assigned_agent_id:
        recipients.append(ticket.assigned_agent)
    if ticket.team_leader_id:
        recipients.append(ticket.team_leader)
    for recipient in {item.id: item for item in recipients if getattr(item, "id", None)}.values():
        create_external_channel_notifications(
            recipient=recipient,
            ticket=ticket,
            event_type="ticket_escalation_solution",
            subject=f"Solution responsable {ticket.reference}",
            message=normalized_solution,
        )
    log_audit_event(actor, "ticket_escalation_solution_provided", ticket, {"previous_status": previous_status})
    return {"status": ticket.status, "solution": normalized_solution}


def continue_after_escalation_solution(ticket, *, actor=None):
    if not can_drive_ticket_workflow(actor, ticket):
        raise ValueError("Seul le technicien responsable peut continuer.")
    if ticket.status != Ticket.STATUS_WAITING_SOLUTION:
        raise ValueError("Aucune solution responsable n'est en attente d'application.")
    previous_status = ticket.status
    next_status = ticket.status_before_escalation or (
        Ticket.STATUS_COLLECTIVE_IN_PROGRESS if ticket.is_team_intervention else Ticket.STATUS_IN_PROGRESS
    )
    if next_status in {Ticket.STATUS_ESCALATED, Ticket.STATUS_WAITING_SOLUTION, Ticket.STATUS_FINISH_REQUESTED}:
        next_status = Ticket.STATUS_COLLECTIVE_IN_PROGRESS if ticket.is_team_intervention else Ticket.STATUS_IN_PROGRESS
    ticket.status = next_status
    ticket.save(update_fields=["status", "updated_at"])
    Message.objects.create(
        ticket=ticket,
        sender=actor,
        message_type=Message.TYPE_INTERNAL,
        channel=Message.CHANNEL_PORTAL,
        direction=Message.DIRECTION_INTERNAL,
        content="Le technicien reprend le traitement apres solution responsable.",
        sentiment_score=0,
    )
    log_audit_event(actor, "ticket_escalation_solution_continued", ticket, {"previous_status": previous_status, "new_status": next_status})
    return {"status": ticket.status, "previous_status": previous_status}


def decline_ticket_escalation(ticket, *, actor=None, reason=""):
    if not is_manager_user(actor):
        raise ValueError("Seul le Responsable SAV peut decliner une escalade.")
    if ticket.status != Ticket.STATUS_ESCALATED:
        raise ValueError("Le ticket doit etre en escalade.")
    normalized_reason = (reason or "").strip()
    if not normalized_reason:
        raise ValueError("Le motif de refus est obligatoire.")
    previous_status = ticket.status
    next_status = ticket.status_before_escalation or Ticket.STATUS_ASSIGNED
    if next_status in {Ticket.STATUS_ESCALATED, Ticket.STATUS_WAITING_SOLUTION}:
        next_status = Ticket.STATUS_ASSIGNED
    ticket.status = next_status
    ticket.save(update_fields=["status", "updated_at"])
    from .analytics import calculate_sentiment
    Message.objects.create(
        ticket=ticket,
        sender=actor,
        message_type=Message.TYPE_INTERNAL,
        channel=Message.CHANNEL_PORTAL,
        direction=Message.DIRECTION_INTERNAL,
        content=f"Escalade declinee: {normalized_reason}",
        sentiment_score=calculate_sentiment(normalized_reason),
    )
    if ticket.assigned_agent_id:
        create_external_channel_notifications(
            recipient=ticket.assigned_agent,
            ticket=ticket,
            event_type="ticket_escalation_declined",
            subject=f"Escalade declinee {ticket.reference}",
            message=normalized_reason,
        )
    log_audit_event(actor, "ticket_escalation_declined", ticket, {"previous_status": previous_status, "new_status": next_status})
    return {"status": ticket.status, "reason": normalized_reason}


def reassign_escalated_ticket(ticket, technician, *, actor=None, note=""):
    if not is_manager_user(actor):
        raise ValueError("Seul le Responsable SAV peut reassigner une escalade.")
    if ticket.status not in {Ticket.STATUS_ESCALATED, Ticket.STATUS_REASSIGN_REQUIRED, Ticket.STATUS_REASSIGNED}:
        raise ValueError("Le ticket doit etre en escalade ou a reassigner.")
    previous_status = ticket.status
    ticket.status = Ticket.STATUS_REASSIGNED
    ticket.save(update_fields=["status", "updated_at"])
    result = assign_ticket_to_technician(ticket, technician, actor=actor, note=note or "Reassignation apres escalade.")
    result["previous_status"] = previous_status
    result["status"] = ticket.status
    return result
