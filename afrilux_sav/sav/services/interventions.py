from django.utils import timezone

from ..comms import create_external_channel_notifications, create_sav_event_notifications
from ..models import Intervention, InterventionMedia, Ticket
from .roles import can_drive_ticket_workflow, can_record_ticket_intervention, is_manager_user
from .audit import log_audit_event
from .reporting import generate_intervention_pdf, send_intervention_assignment_email, send_ticket_closure_report_notifications


def push_realtime_update(target_user, payload, *, ticket=None):
    if not target_user:
        return None
    event_type = payload.get("event") or payload.get("action_required") or "realtime_update"
    notifications = create_sav_event_notifications(
        [target_user],
        event_type=event_type,
        subject=payload.get("subject", "Mise a jour SAV"),
        message=payload.get("message", "Une action SAV est disponible."),
        ticket=ticket,
    )
    return notifications[0] if notifications else None


def propose_planning(ticket, scheduled_at, actor=None):
    if not can_drive_ticket_workflow(actor, ticket):
        raise ValueError("Permissions insuffisantes pour planifier cette intervention.")
    if ticket.status not in {Ticket.STATUS_ASSIGNED, Ticket.STATUS_TEAM_READY, Ticket.STATUS_PLANNING_PROPOSED}:
        raise ValueError("La planification est disponible uniquement apres assignation.")

    intervention = (
        ticket.interventions.filter(status=Intervention.STATUS_PLANNED)
        .order_by("-created_at")
        .first()
    )
    if not intervention:
        intervention = Intervention.objects.create(
            organization=ticket.organization,
            ticket=ticket,
            agent=actor,
            scheduled_for=scheduled_at,
            status=Intervention.STATUS_PLANNED,
            action_taken="Planification proposee",
        )
    else:
        intervention.scheduled_for = scheduled_at
        intervention.save(update_fields=["scheduled_for"])

    ticket.status = Ticket.STATUS_PLANNING_PROPOSED
    ticket.save(update_fields=["status", "updated_at"])

    push_realtime_update(ticket.client, {
        "event": "planning_proposed",
        "ticket_id": ticket.id,
        "action_required": "validate_planning",
        "scheduled_at": scheduled_at.isoformat(),
        "message": f"Le technicien propose une intervention pour le {scheduled_at.strftime('%d/%m/%Y %H:%M')}. Veuillez valider."
    }, ticket=ticket)

    log_audit_event(actor, "planning_proposed", ticket, {"scheduled_at": str(scheduled_at)})
    return intervention


def confirm_planning(ticket, accepted=True, actor=None):
    if actor != ticket.client and not is_manager_user(actor):
        raise ValueError("Seul le client peut valider la planification.")
    if ticket.status != Ticket.STATUS_PLANNING_PROPOSED:
        raise ValueError("Aucune proposition de planification n'est en attente.")

    if accepted:
        ticket.status = Ticket.STATUS_PLANNED
        msg = "Planification acceptee par le client."
    else:
        ticket.status = Ticket.STATUS_ASSIGNED
        msg = "Planification refusee par le client."

    ticket.save(update_fields=["status", "updated_at"])

    if ticket.assigned_agent:
        push_realtime_update(ticket.assigned_agent, {
            "ticket_id": ticket.id,
            "event": "planning_confirmed",
            "accepted": accepted,
            "message": msg
        }, ticket=ticket)

    log_audit_event(actor, "planning_confirmed", ticket, {"accepted": accepted})


def request_start_intervention(ticket, actor=None):
    if not can_drive_ticket_workflow(actor, ticket):
        raise ValueError("Seul le technicien assigne peut demarrer l'intervention.")
    if ticket.status not in {Ticket.STATUS_ASSIGNED, Ticket.STATUS_TEAM_READY, Ticket.STATUS_PLANNED, Ticket.STATUS_WAITING_PART}:
        raise ValueError("Le debut d'intervention doit etre demande depuis un ticket assigne ou planifie.")

    ticket.status = Ticket.STATUS_START_REQUESTED
    ticket.save(update_fields=["status", "updated_at"])

    intervention = (
        ticket.interventions.filter(status=Intervention.STATUS_PLANNED)
        .order_by("-created_at")
        .first()
    )
    if intervention is None:
        intervention = Intervention.objects.create(
            organization=ticket.organization,
            ticket=ticket,
            agent=ticket.team_leader or ticket.assigned_agent or actor,
            intervention_type=Intervention.TYPE_ON_SITE,
            status=Intervention.STATUS_PLANNED,
            action_taken="Demande de debut d'intervention",
            location_snapshot=ticket.location,
        )
    intervention.client_validation_requested_at = timezone.now()
    intervention.save(update_fields=["client_validation_requested_at"])

    push_realtime_update(ticket.client, {
        "event": "start_requested",
        "ticket_id": ticket.id,
        "action_required": "validate_start",
        "message": "Le technicien est arrive. Veuillez valider le debut de l'intervention."
    }, ticket=ticket)

    log_audit_event(actor, "start_requested", ticket)


def validate_start_intervention(ticket, actor=None, impossible=False, reason="", photo=None):
    if actor != ticket.client and not (impossible and can_drive_ticket_workflow(actor, ticket)):
        raise ValueError("Seul le client peut valider le debut.")
    if ticket.status != Ticket.STATUS_START_REQUESTED:
        raise ValueError("Aucune validation de debut n'est en attente.")

    intervention = ticket.interventions.filter(
        status__in=[Intervention.STATUS_PLANNED, Intervention.STATUS_IN_PROGRESS]
    ).order_by("-client_validation_requested_at", "-created_at").first()
    if intervention is None:
        raise ValueError("Aucune intervention planifiee trouvee.")

    now = timezone.now()
    if impossible:
        if not reason or not photo:
            raise ValueError("Motif et photo obligatoires pour contourner la validation client.")
        intervention.client_validation_impossible = True
        intervention.validation_impossible_reason = reason
        intervention.validation_impossible_photo = photo
        msg = f"Debut valide sans client (Motif: {reason})"
    else:
        intervention.client_validated_start_at = now
        msg = "Debut valide par le client."

    intervention.status = Intervention.STATUS_IN_PROGRESS
    intervention.started_at = now
    intervention.save()

    ticket.status = Ticket.STATUS_COLLECTIVE_IN_PROGRESS if ticket.is_team_intervention else Ticket.STATUS_IN_PROGRESS
    ticket.save(update_fields=["status", "updated_at"])

    if ticket.assigned_agent:
        push_realtime_update(ticket.assigned_agent, {
            "ticket_id": ticket.id,
            "event": "start_validated",
            "message": msg,
            "started_at": now.isoformat()
        }, ticket=ticket)
    if ticket.team_leader and ticket.team_leader_id != ticket.assigned_agent_id:
        push_realtime_update(ticket.team_leader, {
            "ticket_id": ticket.id,
            "event": "start_validated",
            "message": msg,
            "started_at": now.isoformat()
        }, ticket=ticket)

    log_audit_event(actor, "start_validated", ticket, {"impossible": impossible})


def request_finish_intervention(ticket, actor=None):
    if not can_drive_ticket_workflow(actor, ticket):
        raise ValueError("Permissions insuffisantes.")
    if ticket.status not in {Ticket.STATUS_IN_PROGRESS, Ticket.STATUS_COLLECTIVE_IN_PROGRESS}:
        raise ValueError("Seule une intervention en cours peut etre terminee.")

    ticket.status = Ticket.STATUS_FINISH_REQUESTED
    ticket.save(update_fields=["status", "updated_at"])

    push_realtime_update(ticket.client, {
        "event": "finish_requested",
        "ticket_id": ticket.id,
        "action_required": "validate_finish",
        "message": "Le technicien a termine les travaux. Veuillez valider la fin de l'intervention."
    }, ticket=ticket)

    log_audit_event(actor, "finish_requested", ticket)


def validate_finish_intervention(ticket, actor=None, impossible=False, reason="", photo=None):
    if actor != ticket.client and not (impossible and can_drive_ticket_workflow(actor, ticket)):
        raise ValueError("Seul le client peut valider la fin.")
    if ticket.status != Ticket.STATUS_FINISH_REQUESTED:
        raise ValueError("Aucune validation de fin n'est en attente.")

    intervention = ticket.interventions.filter(status=Intervention.STATUS_IN_PROGRESS).first()
    if not intervention:
        raise ValueError("Aucune intervention en cours trouvee.")

    now = timezone.now()
    if impossible:
        if not reason or not photo:
            raise ValueError("Motif et photo obligatoires pour contourner la validation client.")
        intervention.client_validation_impossible = True
        intervention.validation_impossible_reason = reason
        intervention.validation_impossible_photo = photo
    else:
        intervention.client_validated_finish_at = now

    intervention.finished_at = now
    intervention.status = Intervention.STATUS_DONE

    if intervention.started_at:
        delta = now - intervention.started_at
        intervention.time_spent_minutes = int(delta.total_seconds() / 60)

    intervention.save()

    ticket.status = Ticket.STATUS_DONE
    ticket.save(update_fields=["status", "updated_at"])

    if ticket.assigned_agent:
        push_realtime_update(ticket.assigned_agent, {
            "ticket_id": ticket.id,
            "event": "finish_validated",
            "message": "Fin d'intervention validee.",
            "finished_at": now.isoformat()
        }, ticket=ticket)
    if ticket.team_leader and ticket.team_leader_id != ticket.assigned_agent_id:
        push_realtime_update(ticket.team_leader, {
            "ticket_id": ticket.id,
            "event": "finish_validated",
            "message": "Fin d'intervention validee.",
            "finished_at": now.isoformat()
        }, ticket=ticket)

    log_audit_event(actor, "finish_validated", ticket, {"impossible": impossible})


def close_sav_dossier(ticket, diagnosis, action_taken, parts=None, client_name="", signature=None, photos=None, actor=None):
    if not can_record_ticket_intervention(actor, ticket):
        raise ValueError("Seul un technicien affecte au ticket peut fermer le dossier.")
    if ticket.status != Ticket.STATUS_DONE:
        raise ValueError("Le dossier doit etre en statut Termine pour etre clos.")
    if not diagnosis or not action_taken or not client_name or not signature:
        raise ValueError("Diagnostic, action effectuee, nom client et signature sont obligatoires.")

    intervention = ticket.interventions.filter(status=Intervention.STATUS_DONE).order_by("-finished_at").first()
    if not intervention:
        raise ValueError("Aucune intervention terminee trouvee.")

    intervention.diagnosis = diagnosis
    intervention.action_taken = action_taken
    if parts:
        intervention.structured_parts_used = parts
    intervention.client_signed_by = client_name
    intervention.client_signed_at = intervention.client_validated_finish_at or intervention.finished_at or timezone.now()
    if signature:
        intervention.client_signature_file = signature
    intervention.save()

    if photos:
        for photo in photos:
            InterventionMedia.objects.create(
                intervention=intervention,
                file=photo,
                kind=InterventionMedia.KIND_AFTER,
                note="Photo de cloture",
                uploaded_by=actor if getattr(actor, "is_authenticated", False) else None,
                organization=ticket.organization,
            )

    ticket.status = Ticket.STATUS_CLOSED
    ticket.closed_at = timezone.now()
    ticket.save(update_fields=["status", "closed_at", "updated_at"])

    pdf_content = generate_intervention_pdf(intervention, force=True)
    send_ticket_closure_report_notifications(ticket, intervention, pdf_content=pdf_content, actor=actor)

    log_audit_event(actor, "dossier_closed", ticket)
    return intervention


def ensure_assignment_intervention(ticket, *, actor=None, note=""):
    if not ticket.assigned_agent_id:
        from .tickets import sync_ticket_assignment
        sync_ticket_assignment(ticket, assigned_by=actor, note=note)
        return {"assignment": None, "intervention": None, "emailed": False, "created_assignment": False}

    from .tickets import sync_ticket_assignment
    assignment, created_assignment, released_ids = sync_ticket_assignment(ticket, assigned_by=actor, note=note)
    intervention = (
        ticket.interventions.filter(
            agent=ticket.assigned_agent,
            status__in=[Intervention.STATUS_PLANNED, Intervention.STATUS_IN_PROGRESS],
        )
        .order_by("-created_at")
        .first()
    )
    if intervention is None:
        intervention = Intervention.objects.create(
            organization=ticket.organization,
            ticket=ticket,
            agent=ticket.assigned_agent,
            intervention_type=Intervention.TYPE_ON_SITE,
            status=Intervention.STATUS_PLANNED,
            scheduled_for=timezone.now(),
            action_taken="Prise en charge initiale du ticket",
            location_snapshot=ticket.location,
            technical_report="Bon d'intervention genere automatiquement a l'affectation.",
        )

    pdf_content = generate_intervention_pdf(intervention)
    emailed = False
    should_notify = bool(created_assignment or released_ids)
    if should_notify:
        try:
            emailed = send_intervention_assignment_email(intervention, pdf_content=pdf_content)
        except Exception:  # noqa: BLE001
            emailed = False
        create_external_channel_notifications(
            recipient=ticket.assigned_agent,
            ticket=ticket,
            event_type="ticket_assignment",
            subject=f"Affectation ticket {ticket.reference}",
            message=(
                f"Le ticket '{ticket.title}' vous a ete affecte. "
                f"Le bon d'intervention {intervention.pk} est disponible."
            ),
        )
        log_audit_event(
            actor=actor,
            action="ticket_assignment_synced",
            instance=ticket,
            details={
                "technician_id": ticket.assigned_agent_id,
                "assignment_id": assignment.id if assignment else None,
                "intervention_id": intervention.id,
                "emailed": emailed,
            },
        )

    return {
        "assignment": assignment,
        "intervention": intervention,
        "emailed": emailed,
        "created_assignment": created_assignment,
    }
