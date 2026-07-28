import json
import re
from calendar import monthrange
from datetime import datetime, timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.text import slugify

from ..comms import create_external_channel_notifications
from ..models import (
    MaintenanceProgram,
    MaintenanceReport,
    MaintenanceReportPhoto,
    MaintenanceTicket,
    Product,
    Ticket,
    User,
)
from .roles import (
    can_manage_maintenance,
    can_act_on_maintenance_ticket,
    maintenance_team_recipients,
)
from .audit import log_audit_event
from .tickets import manager_queryset_for_organization
from .parts import (
    _coerce_bool,
    _coerce_id_list,
    _coerce_json_dict,
    _coerce_json_list,
    _parse_datetime_value,
    record_maintenance_part_usages,
)


def _business_domain_for_maintenance_service(service):
    mapping = {
        MaintenanceProgram.SERVICE_IT: Ticket.DOMAIN_IT,
        MaintenanceProgram.SERVICE_CFAO: Ticket.DOMAIN_CFAO,
        MaintenanceProgram.SERVICE_GENERATOR: Ticket.DOMAIN_GENERATOR,
        MaintenanceProgram.SERVICE_COOLING: Ticket.DOMAIN_COOLING,
    }
    return mapping.get(service, Ticket.DOMAIN_OTHER)


def _resolve_maintenance_client(line, *, program, index):
    client_id = line.get("client_id") or line.get("client")
    if client_id not in (None, "", 0, "0"):
        client = User.objects.filter(pk=client_id, role=User.ROLE_CLIENT, is_active=True).first()
        if client is None:
            raise ValueError(f"Ligne {index}: client introuvable.")
        return client

    client_label = str(
        line.get("client_label")
        or line.get("client_name")
        or line.get("client_site")
        or line.get("site_client")
        or ""
    ).strip()
    if not client_label:
        raise ValueError(f"Ligne {index}: le client / site concerne est obligatoire.")

    normalized_label = re.sub(r"^#\d+\s*-\s*", "", client_label).strip()
    organization = program.organization
    queryset = User.objects.filter(role=User.ROLE_CLIENT, is_active=True)
    if organization:
        queryset = queryset.filter(Q(organization=organization) | Q(organization__isnull=True))
    existing = queryset.filter(Q(company_name__iexact=normalized_label) | Q(username__iexact=slugify(normalized_label))).first()
    if existing:
        return existing

    base_username = slugify(normalized_label)[:120] or f"client-maintenance-{index}"
    username = base_username
    suffix = 1
    while User.objects.filter(username=username).exists():
        suffix += 1
        username = f"{base_username[:110]}-{suffix}"

    return User.objects.create(
        username=username,
        role=User.ROLE_CLIENT,
        organization=organization,
        company_name=normalized_label[:255],
        is_active=True,
    )


def _is_placeholder_maintenance_line(line):
    if not isinstance(line, dict):
        return False
    title = str(line.get("title") or "").strip().lower()
    client_label = str(line.get("client_label") or "").strip().lower()
    equipment_label = str(line.get("equipment_label") or "").strip().lower()
    client_id = line.get("client_id") or line.get("client")
    technician_ids = line.get("technician_ids") or line.get("technicien_ids") or []
    product_ids = line.get("product_ids") or line.get("products") or line.get("equipment_ids") or []
    return (
        title == "entretien preventif equipement client"
        and (not client_label or client_label == "client / site a renseigner")
        and (not equipment_label or equipment_label == "equipement a renseigner")
        and client_id in (None, "", 0, "0")
        and not technician_ids
        and not product_ids
    )


def _add_months(value, months):
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    return value.replace(year=year, month=month, day=min(value.day, monthrange(year, month)[1]))


def _monthly_ordinal_date(value, rule):
    """Return the date represented by ordinal:first:monday style rules."""
    try:
        _, ordinal, weekday_name = rule.split(":", 2)
        weekday = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6}[weekday_name]
    except (ValueError, KeyError):
        return value
    last_day = monthrange(value.year, value.month)[1]
    if ordinal == "last":
        candidate = value.replace(day=last_day)
        return candidate - timedelta(days=(candidate.weekday() - weekday) % 7)
    occurrence = {"first": 1, "second": 2, "third": 3, "fourth": 4}.get(ordinal, 1)
    candidate = value.replace(day=1)
    candidate += timedelta(days=(weekday - candidate.weekday()) % 7 + 7 * (occurrence - 1))
    return candidate if candidate.month == value.month else value


def _program_rule_dates(program):
    if not program.is_rule_based:
        return []
    end_date = program.end_date or (program.start_date + timedelta(days=365))
    interval = max(1, program.frequency_interval or 1)
    current = program.start_date
    dates = []
    while current <= end_date:
        if program.frequency == MaintenanceProgram.FREQUENCY_WEEKLY and program.weekly_days:
            week_start = current - timedelta(days=current.weekday())
            for weekday in sorted({int(day) for day in program.weekly_days if str(day).isdigit() and 0 <= int(day) <= 6}):
                candidate = week_start + timedelta(days=weekday)
                if program.start_date <= candidate <= end_date:
                    dates.append(candidate)
            current += timedelta(weeks=interval)
            continue
        if program.frequency == MaintenanceProgram.FREQUENCY_MONTHLY and program.monthly_rule:
            rule = program.monthly_rule
            if rule.startswith("day:"):
                try:
                    day = max(1, min(31, int(rule.split(":", 1)[1])))
                    current = current.replace(day=min(day, monthrange(current.year, current.month)[1]))
                except ValueError:
                    pass
            elif rule.startswith("ordinal:"):
                current = _monthly_ordinal_date(current, rule)
        dates.append(current)
        if len(dates) > 1000:
            raise ValueError("La periode du programme genere trop d'interventions. Reduisez la plage ou augmentez l'intervalle.")
        if program.frequency == MaintenanceProgram.FREQUENCY_DAILY:
            current += timedelta(days=interval)
        elif program.frequency == MaintenanceProgram.FREQUENCY_WEEKLY:
            current += timedelta(weeks=interval)
        elif program.frequency == MaintenanceProgram.FREQUENCY_CUSTOM:
            unit = program.custom_frequency_unit
            if unit == "days":
                current += timedelta(days=interval)
            elif unit == "weeks":
                current += timedelta(weeks=interval)
            elif unit == "years":
                current = _add_months(current, 12 * interval)
            else:
                current = _add_months(current, interval)
        else:
            months = {
                MaintenanceProgram.FREQUENCY_MONTHLY: 1,
                MaintenanceProgram.FREQUENCY_QUARTERLY: 3,
                MaintenanceProgram.FREQUENCY_SEMIANNUAL: 6,
                MaintenanceProgram.FREQUENCY_ANNUAL: 12,
            }.get(program.frequency, 1)
            current = _add_months(current, months * interval)
    return dates


def _rule_task_lines(program):
    periodicity = {
        MaintenanceProgram.FREQUENCY_QUARTERLY: MaintenanceTicket.PERIOD_QUARTERLY,
        MaintenanceProgram.FREQUENCY_SEMIANNUAL: MaintenanceTicket.PERIOD_SEMIANNUAL,
        MaintenanceProgram.FREQUENCY_ANNUAL: MaintenanceTicket.PERIOD_ANNUAL,
    }.get(program.frequency, MaintenanceTicket.PERIOD_MONTHLY)
    maintenance_type = {
        MaintenanceProgram.TYPE_PREVENTIVE: MaintenanceTicket.TYPE_PREVENTIVE,
        MaintenanceProgram.TYPE_INSPECTION: MaintenanceTicket.TYPE_INSPECTION,
        MaintenanceProgram.TYPE_CALIBRATION: MaintenanceTicket.TYPE_CONTROL,
        MaintenanceProgram.TYPE_CONTROL: MaintenanceTicket.TYPE_CONTROL,
        MaintenanceProgram.TYPE_PERIODIC_CHECK: MaintenanceTicket.TYPE_CONTROL,
    }[program.maintenance_type]
    technician_ids = [program.technician_id, *program.team_members.values_list("id", flat=True)]
    title = program.title or f"{program.get_maintenance_type_display()} - {program.equipment.name}"
    lines = []
    for scheduled_day in _program_rule_dates(program):
        scheduled_at = timezone.make_aware(datetime.combine(scheduled_day, program.scheduled_time))
        lines.append({
            "title": title,
            "technician_ids": technician_ids,
            "client_id": program.client_id,
            "product_ids": [program.equipment_id],
            "equipment_label": str(program.equipment),
            "scheduled_date": scheduled_at.isoformat(),
            "periodicity": periodicity,
            "maintenance_type": maintenance_type,
            "priority": program.priority,
            "planned_duration_minutes": program.estimated_duration_minutes,
            "checklist": [item.get("description", "") if isinstance(item, dict) else item for item in program.checklist],
            "instructions": f"{program.description}\nDurée estimée : {program.estimated_duration_minutes} min.\nNuitées prévues : {program.overnight_stays}".strip(),
            "location": program.site.address if program.site_id and program.site.address else program.city,
            "overnight_stays": program.overnight_stays,
        })
    return lines


def publish_maintenance_program(program, *, actor=None):
    if program.status == MaintenanceProgram.STATUS_PUBLISHED and program.tickets.exists() and not program.is_rule_based:
        return list(program.tickets.select_related("client", "technician").prefetch_related("products", "team_members"))
    if program.status == MaintenanceProgram.STATUS_ARCHIVED:
        raise ValueError("Un programme archive ne peut pas etre publie.")

    task_lines = _rule_task_lines(program) if program.is_rule_based else program.task_lines
    if isinstance(task_lines, str):
        raw = task_lines.strip()
        if raw:
            try:
                task_lines = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ValueError("task_lines: contenu doit etre un JSON valide (liste JSON attendu).") from exc
        else:
            task_lines = []

    if not isinstance(task_lines, list) or not task_lines:
        raise ValueError("Ajoutez au moins une ligne de maintenance avant publication (task_lines vide ou non-list).")
    task_lines = [line for line in task_lines if not _is_placeholder_maintenance_line(line)]
    if not task_lines:
        raise ValueError("Ajoutez au moins une ligne de maintenance complete avant publication.")

    created_tickets = []
    with transaction.atomic():
        for index, line in enumerate(task_lines, start=1):
            if not isinstance(line, dict):
                raise ValueError(f"Ligne {index}: chaque ligne doit etre un objet JSON (dict).")
            if not isinstance(line, dict):
                raise ValueError(f"Ligne {index}: format invalide.")
            title = str(line.get("title") or line.get("intitule") or line.get("task") or "").strip()
            if not title:
                raise ValueError(f"Ligne {index}: l'intitule de la tache est obligatoire.")
            technician_ids = _coerce_id_list(
                line.get("technician_ids")
                or line.get("technicien_ids")
                or line.get("technicians")
                or line.get("techniciens")
                or line.get("team_member_ids")
                or line.get("membres_equipe")
                or [],
                "Les identifiants de techniciens doivent etre numeriques.",
            )
            technician_id = line.get("technician_id") or line.get("technicien_id") or line.get("technician")
            if technician_id:
                try:
                    primary_technician_id = int(str(technician_id).strip())
                except (TypeError, ValueError) as exc:
                    raise ValueError(f"Ligne {index}: l'identifiant du technicien principal doit etre numerique.") from exc
                if primary_technician_id not in technician_ids:
                    technician_ids.insert(0, primary_technician_id)
            technician_ids = list(dict.fromkeys(technician_ids))
            if not technician_ids:
                raise ValueError(f"Ligne {index}: technicien obligatoire.")

            technician_queryset = User.objects.filter(pk__in=technician_ids, role__in=User.TECHNICIAN_SPACE_ROLES, is_active=True)
            technician_by_id = {technician.pk: technician for technician in technician_queryset}
            missing_technicians = [technician_id for technician_id in technician_ids if technician_id not in technician_by_id]
            if missing_technicians:
                raise ValueError(
                    f"Ligne {index}: technicien introuvable ou non habilite pour la maintenance terrain."
                )
            technicians = [technician_by_id[technician_id] for technician_id in technician_ids]
            technician = technicians[0]
            team_members = [member for member in technicians[1:] if member.pk != technician.pk]
            client = _resolve_maintenance_client(line, program=program, index=index)
            if program.organization_id:
                for technician_item in technicians:
                    if technician_item.organization_id and technician_item.organization_id != program.organization_id:
                        raise ValueError(f"Ligne {index}: un technicien appartient a une autre organisation.")
                if client.organization_id and client.organization_id != program.organization_id:
                    raise ValueError(f"Ligne {index}: le client appartient a une autre organisation.")

            product_ids = _coerce_id_list(
                line.get("product_ids")
                or line.get("products")
                or line.get("equipment_ids")
                or line.get("equipement_ids")
                or line.get("equipements")
            )
            products = list(Product.objects.filter(pk__in=product_ids)) if product_ids else []
            equipment_label = str(
                line.get("equipment_label")
                or line.get("equipement_label")
                or line.get("equipment")
                or line.get("equipement")
                or ""
            ).strip()
            if not equipment_label and products:
                equipment_label = ", ".join(f"{product.name} / {product.serial_number}" for product in products)
            if not equipment_label:
                raise ValueError(f"Ligne {index}: le champ Equipement(s) est obligatoire.")
            for product in products:
                if product.client_id != client.id:
                    raise ValueError(f"Ligne {index}: l'equipement {product.serial_number} n'appartient pas au client.")

            scheduled_date = _parse_datetime_value(
                line.get("scheduled_date") or line.get("due_date") or line.get("date_prevue") or line.get("date"),
                "date_prevue",
            )
            existing_ticket = MaintenanceTicket.objects.filter(
                program=program,
                title=title[:255],
                scheduled_date=scheduled_date,
            ).first()
            if existing_ticket:
                created_tickets.append(existing_ticket)
                continue
            ticket = MaintenanceTicket.objects.create(
                organization=program.organization,
                program=program,
                responsible=program.responsible or actor,
                technician=technician,
                client=client,
                title=title[:255],
                service=str(line.get("service") or program.service or MaintenanceProgram.SERVICE_IT).strip(),
                periodicity=str(line.get("periodicity") or line.get("periodicite") or MaintenanceTicket.PERIOD_MONTHLY).strip(),
                maintenance_type=str(line.get("maintenance_type") or line.get("type_maintenance") or MaintenanceTicket.TYPE_PREVENTIVE).strip(),
                scheduled_date=scheduled_date,
                initial_scheduled_date=scheduled_date,
                planned_duration_minutes=max(1, int(line.get("planned_duration_minutes") or line.get("estimated_duration_minutes") or program.estimated_duration_minutes or 60)),
                checklist=_coerce_json_list(line.get("checklist") or line.get("check_list"), "checklist"),
                instructions=str(line.get("instructions") or line.get("notes") or "").strip(),
                priority=str(line.get("priority") or line.get("priorite") or Ticket.PRIORITY_NORMAL).strip(),
                location=str(line.get("location") or line.get("localisation") or client.address or "").strip()[:255],
                route=str(line.get("route") or line.get("trajet") or "").strip()[:255],
                overnight_stays=int(line.get("overnight_stays") or line.get("nuitees") or line.get("nuitées") or 0),
                call_date=_parse_datetime_value(line.get("call_date") or line.get("date_appel") or scheduled_date, "date_appel"),
                system_tools=str(line.get("system_tools") or line.get("systeme_outillage") or line.get("systeme") or "").strip()[:255],
                equipment_brand=str(line.get("equipment_brand") or line.get("marque") or "").strip()[:120],
                equipment_type=str(line.get("equipment_type") or line.get("type_equipement") or line.get("type") or "").strip()[:120],
                equipment_identifier=str(
                    line.get("equipment_identifier")
                    or line.get("numero")
                    or line.get("numero_serie")
                    or equipment_label
                    or ""
                ).strip()[:120],
                intervention_reason=str(line.get("intervention_reason") or line.get("motif") or title).strip(),
                estimated_cost=Decimal(str(line.get("estimated_cost") or line.get("cout_prevu") or "0")),
                actual_cost=Decimal(str(line.get("actual_cost") or line.get("cout_reel") or "0")),
                status=MaintenanceTicket.STATUS_PLANNED,
            )
            if products:
                ticket.products.set(products)
            if team_members:
                ticket.team_members.set(team_members)
            created_tickets.append(ticket)

        program.status = MaintenanceProgram.STATUS_PUBLISHED
        program.published_at = timezone.now()
        upcoming_dates = [scheduled for scheduled in _program_rule_dates(program) if scheduled >= timezone.localdate()]
        program.next_generation_date = upcoming_dates[0] if upcoming_dates else None
        program.save(update_fields=["status", "published_at", "next_generation_date", "updated_at"])

    log_audit_event(
        actor=actor,
        action="maintenance_program_published",
        instance=program,
        details={"created_ticket_ids": [ticket.id for ticket in created_tickets]},
    )
    return created_tickets


def start_maintenance_ticket(maintenance_ticket, *, actor=None):
    if maintenance_ticket.status not in {
        MaintenanceTicket.STATUS_PLANNED,
        MaintenanceTicket.STATUS_NOTIFIED,
        MaintenanceTicket.STATUS_POSTPONED,
    }:
        raise ValueError("Cette maintenance ne peut pas etre demarree depuis son statut actuel.")
    if actor and actor.is_authenticated and not can_act_on_maintenance_ticket(actor, maintenance_ticket):
        raise ValueError("Seul le technicien assigne ou un responsable peut demarrer cette maintenance.")
    maintenance_ticket.status = MaintenanceTicket.STATUS_IN_PROGRESS
    maintenance_ticket.started_at = maintenance_ticket.started_at or timezone.now()
    maintenance_ticket.save(update_fields=["status", "started_at", "updated_at"])
    log_audit_event(actor, "maintenance_ticket_started", maintenance_ticket)
    return maintenance_ticket


def acknowledge_maintenance_ticket(maintenance_ticket, *, actor=None):
    if actor and actor.is_authenticated and not can_act_on_maintenance_ticket(actor, maintenance_ticket):
        raise ValueError("Seul le technicien assigne ou un responsable peut accuser reception de cette maintenance.")
    if maintenance_ticket.status not in {MaintenanceTicket.STATUS_PLANNED, MaintenanceTicket.STATUS_NOTIFIED}:
        raise ValueError("Seules les maintenances planifiees ou notifiees peuvent etre accusees reception.")

    now = timezone.now()
    maintenance_ticket.status = MaintenanceTicket.STATUS_NOTIFIED
    maintenance_ticket.notified_at = maintenance_ticket.notified_at or now
    maintenance_ticket.acknowledged_at = now
    maintenance_ticket.save(update_fields=["status", "notified_at", "acknowledged_at", "updated_at"])

    recipients = []
    if maintenance_ticket.responsible_id:
        recipients.append(maintenance_ticket.responsible)
    for recipient in {item.id: item for item in recipients if getattr(item, "id", None)}.values():
        create_external_channel_notifications(
            recipient=recipient,
            ticket=None,
            event_type="maintenance_acknowledged",
            subject=f"Maintenance accusee - {maintenance_ticket.title}",
            message=f"{actor or maintenance_ticket.technician} a accuse reception de la maintenance du {timezone.localtime(maintenance_ticket.scheduled_date):%d/%m/%Y %H:%M}.",
        )
    log_audit_event(actor, "maintenance_ticket_acknowledged", maintenance_ticket)
    return maintenance_ticket


def reschedule_maintenance_ticket(maintenance_ticket, *, scheduled_date, planned_duration_minutes=None, actor=None):
    """Move a generated intervention without changing its workflow status."""
    parsed_date = _parse_datetime_value(scheduled_date, "date_prevue")
    if actor and actor.is_authenticated and not can_act_on_maintenance_ticket(actor, maintenance_ticket):
        raise ValueError("Seul le technicien responsable ou un responsable peut replanifier cette intervention.")
    if maintenance_ticket.status in {
        MaintenanceTicket.STATUS_DONE,
        MaintenanceTicket.STATUS_ANOMALY,
        MaintenanceTicket.STATUS_CANCELLED,
    }:
        raise ValueError("Une intervention terminée ou annulée ne peut pas être replanifiée.")

    duration = planned_duration_minutes or maintenance_ticket.planned_duration_minutes or 60
    try:
        duration = max(1, int(duration))
    except (TypeError, ValueError) as exc:
        raise ValueError("La durée prévue doit être un nombre de minutes valide.") from exc

    maintenance_ticket.initial_scheduled_date = maintenance_ticket.initial_scheduled_date or maintenance_ticket.scheduled_date
    maintenance_ticket.scheduled_date = parsed_date
    maintenance_ticket.planned_duration_minutes = duration
    maintenance_ticket.save(update_fields=[
        "initial_scheduled_date", "scheduled_date", "planned_duration_minutes", "updated_at",
    ])
    log_audit_event(
        actor,
        "maintenance_ticket_rescheduled",
        maintenance_ticket,
        {"scheduled_date": parsed_date.isoformat(), "planned_duration_minutes": duration},
    )
    return maintenance_ticket


def postpone_maintenance_ticket(maintenance_ticket, *, new_date, justification, actor=None):
    if not str(justification or "").strip():
        raise ValueError("La justification du report est obligatoire.")
    parsed_date = _parse_datetime_value(new_date, "nouvelle_date")
    if actor and actor.is_authenticated and not can_act_on_maintenance_ticket(actor, maintenance_ticket):
        raise ValueError("Seul le technicien assigne ou un responsable peut reporter cette maintenance.")

    maintenance_ticket.status = MaintenanceTicket.STATUS_POSTPONED
    maintenance_ticket.initial_scheduled_date = maintenance_ticket.initial_scheduled_date or maintenance_ticket.scheduled_date
    maintenance_ticket.postponed_to = parsed_date
    maintenance_ticket.scheduled_date = parsed_date
    maintenance_ticket.postponement_reason = str(justification).strip()
    maintenance_ticket.save(
        update_fields=["status", "initial_scheduled_date", "postponed_to", "scheduled_date", "postponement_reason", "updated_at"]
    )

    recipients = []
    if maintenance_ticket.responsible_id:
        recipients.append(maintenance_ticket.responsible)
    recipients.extend(manager_queryset_for_organization(maintenance_ticket.organization))
    for recipient in {item.id: item for item in recipients if getattr(item, "id", None)}.values():
        create_external_channel_notifications(
            recipient=recipient,
            ticket=None,
            event_type="maintenance_postponed",
            subject=f"Maintenance reportee - {maintenance_ticket.title}",
            message=f"La maintenance du {timezone.localtime(maintenance_ticket.scheduled_date):%d/%m/%Y %H:%M} a ete reportee: {maintenance_ticket.postponement_reason}",
        )
    log_audit_event(actor, "maintenance_ticket_postponed", maintenance_ticket, {"new_date": parsed_date.isoformat()})
    return maintenance_ticket


def cancel_maintenance_ticket(maintenance_ticket, *, reason, actor=None):
    normalized_reason = str(reason or "").strip()
    if not normalized_reason:
        raise ValueError("Le motif d'annulation est obligatoire.")
    if actor and actor.is_authenticated and not can_manage_maintenance(actor):
        raise ValueError("L'annulation d'une maintenance est reservee au responsable de service.")
    if maintenance_ticket.status in {
        MaintenanceTicket.STATUS_DONE,
        MaintenanceTicket.STATUS_ANOMALY,
        MaintenanceTicket.STATUS_CANCELLED,
    }:
        raise ValueError("Cette maintenance ne peut plus etre annulee depuis son statut actuel.")

    maintenance_ticket.status = MaintenanceTicket.STATUS_CANCELLED
    maintenance_ticket.cancellation_reason = normalized_reason
    maintenance_ticket.cancelled_at = timezone.now()
    maintenance_ticket.save(update_fields=["status", "cancellation_reason", "cancelled_at", "updated_at"])

    recipients = maintenance_team_recipients(maintenance_ticket)
    if maintenance_ticket.responsible_id:
        recipients.append(maintenance_ticket.responsible)
    for recipient in {item.id: item for item in recipients if getattr(item, "id", None)}.values():
        create_external_channel_notifications(
            recipient=recipient,
            ticket=None,
            event_type="maintenance_cancelled",
            subject=f"Maintenance annulee - {maintenance_ticket.title}",
            message=f"La maintenance planifiee le {timezone.localtime(maintenance_ticket.scheduled_date):%d/%m/%Y %H:%M} est annulee. Motif: {normalized_reason}",
        )
    log_audit_event(actor, "maintenance_ticket_cancelled", maintenance_ticket, {"reason": normalized_reason})
    return maintenance_ticket


def validate_maintenance_report(maintenance_ticket, *, actor=None):
    if actor and actor.is_authenticated and not can_manage_maintenance(actor):
        raise ValueError("La validation du rapport est reservee au responsable de service.")
    if maintenance_ticket.status not in {MaintenanceTicket.STATUS_DONE, MaintenanceTicket.STATUS_ANOMALY}:
        raise ValueError("Seules les maintenances terminees ou avec anomalie peuvent etre validees.")
    try:
        report = maintenance_ticket.report
    except MaintenanceReport.DoesNotExist as exc:
        raise ValueError("Aucun rapport de maintenance n'est disponible pour validation.") from exc
    report.validated_by = actor if getattr(actor, "is_authenticated", False) else None
    report.validated_at = timezone.now()
    report.save(update_fields=["validated_by", "validated_at", "updated_at"])
    log_audit_event(actor, "maintenance_report_validated", maintenance_ticket, {"report_id": report.id})
    return report


def _create_incident_from_maintenance(maintenance_ticket, report, *, actor=None):
    if maintenance_ticket.anomaly_ticket_id:
        return maintenance_ticket.anomaly_ticket

    product = maintenance_ticket.products.first()
    description = (
        "Anomalie detectee lors d'une maintenance planifiee.\n\n"
        f"Maintenance: {maintenance_ticket.title}\n"
        f"Client: {maintenance_ticket.client}\n"
        f"Observations: {report.observations}\n"
        f"Pieces / consommables: {report.parts_used or '-'}"
    )
    assigned_agent = maintenance_ticket.technician if maintenance_ticket.technician.is_ticket_assignment_eligible else None
    incident = Ticket.objects.create(
        client=maintenance_ticket.client,
        created_by=actor if getattr(actor, "is_authenticated", False) else maintenance_ticket.responsible,
        product=product,
        product_label=product.name if product else "",
        assigned_agent=assigned_agent,
        title=f"Anomalie maintenance - {maintenance_ticket.title}"[:255],
        description=description,
        business_domain=_business_domain_for_maintenance_service(maintenance_ticket.service),
        category=Ticket.CATEGORY_BREAKDOWN,
        channel=Ticket.CHANNEL_WEB,
        status=Ticket.STATUS_WAITING_DIAGNOSTIC,
        priority=maintenance_ticket.priority,
        location=maintenance_ticket.location,
        sla_deadline=_compute_ticket_sla_deadline(maintenance_ticket.priority, organization=maintenance_ticket.organization),
    )
    if incident.assigned_agent_id:
        from .interventions import ensure_assignment_intervention
        ensure_assignment_intervention(incident, actor=actor, note="Ticket incident genere depuis une maintenance planifiee.")
    maintenance_ticket.anomaly_ticket = incident
    maintenance_ticket.save(update_fields=["anomaly_ticket", "updated_at"])
    log_audit_event(
        actor=actor,
        action="maintenance_anomaly_incident_created",
        instance=maintenance_ticket,
        details={"incident_ticket": incident.reference},
    )
    return incident


def _compute_ticket_sla_deadline(priority, base_time=None, organization=None):
    from .users import compute_ticket_sla_deadline
    return compute_ticket_sla_deadline(priority, base_time=base_time, organization=organization)


def close_maintenance_ticket(
    maintenance_ticket,
    *,
    actor=None,
    final_status=MaintenanceTicket.STATUS_DONE,
    actual_started_at=None,
    actual_finished_at=None,
    checklist_completed=None,
    observations="",
    actual_cost=0,
    work_to_plan="",
    parts_used="",
    parts_status=None,
    intervention_types=None,
    spare_parts=None,
    structured_parts_used=None,
    anomaly_detected=None,
    photos=None,
    client_signed_by="",
    client_signature_file=None,
    photo_files=None,
    new_date=None,
    postponement_reason="",
):
    if final_status not in {choice[0] for choice in MaintenanceTicket.FINAL_STATUS_CHOICES}:
        raise ValueError("Statut final de maintenance invalide.")
    if actor and actor.is_authenticated and not can_act_on_maintenance_ticket(actor, maintenance_ticket):
        raise ValueError("Seul le technicien assigne ou un responsable peut cloturer cette maintenance.")
    normalized_observations = str(observations or "").strip()
    if not normalized_observations:
        raise ValueError("Les observations techniques sont obligatoires.")

    actual_started_at = _parse_datetime_value(actual_started_at or maintenance_ticket.started_at or timezone.now(), "debut_reel")
    actual_finished_at = _parse_datetime_value(actual_finished_at or timezone.now(), "fin_reelle")
    checklist_payload = _coerce_json_list(checklist_completed, "checklist_realisee")
    if not checklist_payload:
        raise ValueError("La check-list realisee est obligatoire.")
    anomaly_flag = _coerce_bool(anomaly_detected) or final_status == MaintenanceTicket.STATUS_ANOMALY

    if final_status == MaintenanceTicket.STATUS_POSTPONED:
        if not new_date:
            raise ValueError("La nouvelle date est obligatoire pour un report.")
        if not str(postponement_reason or "").strip():
            raise ValueError("La justification du report est obligatoire.")

    report_defaults = {
        "organization": maintenance_ticket.organization,
        "technician": maintenance_ticket.technician,
        "actual_started_at": actual_started_at,
        "actual_finished_at": actual_finished_at,
        "checklist_completed": checklist_payload,
        "observations": normalized_observations,
        "work_to_plan": str(work_to_plan or "").strip(),
        "parts_used": str(parts_used or "").strip(),
        "parts_status": parts_status if isinstance(parts_status, dict) else _coerce_json_dict(parts_status, "etat_pieces"),
        "intervention_types": _coerce_json_list(intervention_types, "types_intervention"),
        "anomaly_detected": anomaly_flag,
        "photos": _coerce_json_list(photos, "photos"),
        "client_signed_by": str(client_signed_by or "").strip(),
        "final_status": final_status,
    }
    if client_signature_file:
        report_defaults["client_signature_file"] = client_signature_file
    report, _created = MaintenanceReport.objects.update_or_create(
        maintenance_ticket=maintenance_ticket,
        defaults=report_defaults,
    )
    record_maintenance_part_usages(
        report,
        spare_parts=spare_parts,
        structured_parts_used=structured_parts_used,
        replace=True,
    )
    photo_records = []
    for uploaded_file in photo_files or []:
        photo = MaintenanceReportPhoto.objects.create(
            report=report,
            uploaded_by=actor if getattr(actor, "is_authenticated", False) else None,
            file=uploaded_file,
            note="Photo jointe a la cloture de maintenance.",
        )
        photo_records.append(photo)
    if photo_records:
        report.photos = [photo.file.name for photo in report.photo_files.all()]
        report.save(update_fields=["photos", "updated_at"])

    maintenance_ticket.status = final_status
    maintenance_ticket.started_at = maintenance_ticket.started_at or actual_started_at
    maintenance_ticket.finished_at = actual_finished_at
    maintenance_ticket.actual_cost = Decimal(str(actual_cost or "0"))
    update_fields = ["status", "started_at", "finished_at", "actual_cost", "updated_at"]
    if final_status == MaintenanceTicket.STATUS_POSTPONED:
        parsed_date = _parse_datetime_value(new_date, "nouvelle_date")
        maintenance_ticket.postponed_to = parsed_date
        maintenance_ticket.scheduled_date = parsed_date
        maintenance_ticket.postponement_reason = str(postponement_reason).strip()
        update_fields.extend(["postponed_to", "scheduled_date", "postponement_reason"])
    maintenance_ticket.save(update_fields=update_fields)

    incident = None
    if anomaly_flag:
        maintenance_ticket.status = MaintenanceTicket.STATUS_ANOMALY
        maintenance_ticket.save(update_fields=["status", "updated_at"])
        incident = _create_incident_from_maintenance(maintenance_ticket, report, actor=actor)

    recipients = []
    if maintenance_ticket.responsible_id:
        recipients.append(maintenance_ticket.responsible)
    recipients.extend(manager_queryset_for_organization(maintenance_ticket.organization))
    for recipient in {item.id: item for item in recipients if getattr(item, "id", None)}.values():
        create_external_channel_notifications(
            recipient=recipient,
            ticket=incident,
            event_type="maintenance_closed",
            subject=f"Maintenance {maintenance_ticket.get_status_display()} - {maintenance_ticket.title}",
            message=f"L'equipe {maintenance_ticket.technician_team_label} a cloture la maintenance: {normalized_observations[:180]}",
        )

    from .reporting import generate_maintenance_report_pdf
    generate_maintenance_report_pdf(report)
    log_audit_event(
        actor,
        "maintenance_ticket_closed",
        maintenance_ticket,
        {"final_status": maintenance_ticket.status, "incident_ticket": incident.reference if incident else ""},
    )
    return {"maintenance_ticket": maintenance_ticket, "report": report, "incident_ticket": incident}
