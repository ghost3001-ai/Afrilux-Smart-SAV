import re
from datetime import datetime, timedelta
from io import BytesIO

from django.core.files.base import ContentFile
from django.core.mail import EmailMessage
from django.contrib.staticfiles import finders
from django.db.models import Q
from django.utils import timezone
from django.utils.text import slugify
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Image as ReportLabImage
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from reportlab.lib import colors

from ..comms import build_ticket_deep_link
from ..models import (
    GeneratedReport,
    MaintenanceReport,
    MaintenanceTicket,
    Notification,
    Organization,
    User,
)
from .audit import log_audit_event
from .tickets import manager_queryset_for_organization
from .parts import _part_usage_records_summary


def parse_reporting_recipients(organization):
    recipients = set()
    if not organization:
        return []
    if organization.reporting_emails:
        for item in organization.reporting_emails.replace(";", ",").split(","):
            email = item.strip().lower()
            if email:
                recipients.add(email)
    if organization.support_email:
        recipients.add(organization.support_email.strip().lower())
    users = User.objects.filter(
        organization=organization,
        is_active=True,
    ).filter(Q(role__in=User.REPORTING_ROLES) | Q(is_superuser=True))
    for user in users:
        email = (user.professional_email or user.email or "").strip().lower()
        if email:
            recipients.add(email)
    return sorted(recipients)


def generate_intervention_pdf(intervention, persist=True, force=False):
    if persist and not force and getattr(intervention, "report_pdf", None):
        try:
            with intervention.report_pdf.open("rb") as existing_report:
                return existing_report.read()
        except OSError:
            pass

    buffer = BytesIO()
    document = SimpleDocTemplate(buffer, pagesize=A4)
    styles = getSampleStyleSheet()

    parts_text = intervention.parts_used or "-"
    if intervention.structured_parts_used:
        formatted_parts = []
        for part in intervention.structured_parts_used:
            if not isinstance(part, dict):
                formatted_parts.append(str(part))
                continue
            name = part.get("name") or part.get("designation") or part.get("label") or part.get("reference") or "Piece"
            quantity = part.get("quantity") or part.get("quantite") or part.get("qty")
            formatted_parts.append(f"{name} (x{quantity})" if quantity else str(name))
        parts_text = ", ".join(formatted_parts) or "-"

    team_text = str(intervention.agent)
    if intervention.ticket.is_team_intervention:
        members = ", ".join([str(u) for u in intervention.ticket.team_members.all()])
        team_text = f"Chef: {intervention.ticket.team_leader} | Membres: {members}"

    validation_text = "Valide par client"
    if intervention.client_validation_impossible:
        validation_text = f"Bypass: {intervention.validation_impossible_reason}"

    data = [
        ["Numero ticket", intervention.ticket.reference],
        ["Client", str(intervention.ticket.client)],
        ["Equipe Intervenante", team_text],
        ["Type", intervention.get_intervention_type_display()],
        ["Statut", intervention.get_status_display()],
        ["Debut (Valide)", intervention.started_at.strftime("%d/%m/%Y %H:%M") if intervention.started_at else "-"],
        ["Fin (Valide)", intervention.finished_at.strftime("%d/%m/%Y %H:%M") if intervention.finished_at else "-"],
        ["Validation", validation_text],
        ["Lieu", intervention.location_snapshot or intervention.ticket.location or "-"],
        ["Diagnostic", intervention.diagnosis or "-"],
        ["Action effectuee", intervention.action_taken or "-"],
        ["Pieces utilisees", parts_text],
        ["Temps total calcule", f"{intervention.time_spent_minutes} minutes"],
        ["Signataire client", intervention.client_signed_by or "-"],
    ]
    story = []
    logo_path = finders.find("sav/images/afrilux-smart-solutions-logo.jpeg")
    if logo_path:
        logo = _safe_reportlab_image(logo_path, width=150, height=64)
        if logo:
            story.extend([logo, Spacer(1, 8)])
    story.extend(
        [
            Paragraph("Bon d'intervention AFRILUX SMART SOLUTIONS", styles["Title"]),
            Spacer(1, 12),
            Table(data, colWidths=[150, 340]),
            Spacer(1, 12),
            Paragraph("Rapport technique", styles["Heading2"]),
            Paragraph(intervention.technical_report or "Aucun rapport technique saisi.", styles["BodyText"]),
        ]
    )
    if intervention.client_signature_file:
        story.extend([Spacer(1, 12), Paragraph("Signature client", styles["Heading3"])])
        signature = _safe_reportlab_image(intervention.client_signature_file.path, width=220, height=90)
        if signature:
            story.append(signature)
        else:
            story.append(Paragraph(intervention.client_signature_file.name.split("/")[-1], styles["BodyText"]))
    media_items = list(intervention.media.all()[:5])
    if media_items:
        story.extend([Spacer(1, 12), Paragraph("Pieces jointes terrain", styles["Heading3"])])
        media_rows = [["Type", "Note", "Fichier"]]
        for item in media_items:
            media_rows.append([item.get_kind_display(), item.note or "-", item.file.name.split("/")[-1]])
        media_table = Table(media_rows, colWidths=[120, 220, 150])
        media_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E8D5BF")),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ]
            )
        )
        story.append(media_table)
        for item in media_items:
            try:
                lower_name = item.file.name.lower()
                if lower_name.endswith((".jpg", ".jpeg", ".png")):
                    image = _safe_reportlab_image(item.file.path, width=220, height=150)
                    if image:
                        story.extend(
                            [
                                Spacer(1, 8),
                                Paragraph(item.note or item.get_kind_display(), styles["BodyText"]),
                                image,
                            ]
                        )
            except Exception:
                continue
    document.build(story)
    content = buffer.getvalue()
    if persist:
        filename = f"intervention-{slugify(intervention.ticket.reference)}-{intervention.pk}.pdf"
        intervention.report_pdf.save(filename, ContentFile(content), save=False)
        intervention.report_generated_at = timezone.now()
        intervention.save(update_fields=["report_pdf", "report_generated_at"])
    return content


def _safe_reportlab_image(path, *, width, height):
    try:
        from PIL import Image as PILImage

        with PILImage.open(path) as image:
            image.verify()
        return ReportLabImage(path, width=width, height=height)
    except Exception:
        return None


def generate_maintenance_report_pdf(report, persist=True, force=False):
    if persist and not force and getattr(report, "report_pdf", None):
        try:
            with report.report_pdf.open("rb") as existing_report:
                return existing_report.read()
        except OSError:
            pass

    maintenance_ticket = report.maintenance_ticket
    products = list(maintenance_ticket.products.all())
    product_label = (
        ", ".join(
            f"{product.name} / {product.serial_number}".strip(" /")
            for product in products
        )
        if products
        else maintenance_ticket.equipment_identifier or "-"
    )
    parts_text = report.parts_used or _part_usage_records_summary(report.part_usages.select_related("spare_part").all()) or "-"
    parts_status = report.parts_status or {}
    intervention_types = ", ".join(str(item).replace("_", " ") for item in report.intervention_types or []) or "-"
    checklist_rows = [["Operation realisee"]]
    checklist_rows.extend([[str(item)] for item in report.checklist_completed or ["-"]])
    data = [
        ["Reference maintenance", f"MAINT-{maintenance_ticket.id}"],
        ["Client", str(maintenance_ticket.client)],
        ["Systeme / outillage", maintenance_ticket.system_tools or "-"],
        ["Marque", maintenance_ticket.equipment_brand or "-"],
        ["Type", maintenance_ticket.equipment_type or "-"],
        ["Numero", maintenance_ticket.equipment_identifier or "-"],
        ["Cause d'appel / motif", maintenance_ticket.intervention_reason or maintenance_ticket.title],
        ["Date d'appel", timezone.localtime(maintenance_ticket.call_date).strftime("%d/%m/%Y %H:%M") if maintenance_ticket.call_date else "-"],
        ["Technicien principal", str(report.technician)],
        ["Equipe technique", maintenance_ticket.technician_team_label],
        ["Service", maintenance_ticket.get_service_display()],
        ["Periodicite", maintenance_ticket.get_periodicity_display()],
        ["Date prevue", timezone.localtime(maintenance_ticket.initial_scheduled_date or maintenance_ticket.scheduled_date).strftime("%d/%m/%Y %H:%M")],
        ["Execution reelle", f"{report.actual_started_at:%d/%m/%Y %H:%M} - {report.actual_finished_at:%d/%m/%Y %H:%M}"],
        ["Equipement(s)", product_label],
        ["Lieu", maintenance_ticket.location or maintenance_ticket.client.address or "-"],
        ["Trajet", maintenance_ticket.route or "-"],
        ["Nuitees", str(maintenance_ticket.overnight_stays or 0)],
        ["Types d'intervention", intervention_types],
        ["Statut final", report.get_final_status_display()],
        ["Anomalie detectee", "Oui" if report.anomaly_detected else "Non"],
        ["Signature client", report.client_signed_by or "-"],
    ]

    buffer = BytesIO()
    document = SimpleDocTemplate(buffer, pagesize=A4)
    styles = getSampleStyleSheet()
    story = []
    logo_path = finders.find("sav/images/afrilux-smart-solutions-logo.jpeg")
    if logo_path:
        logo = _safe_reportlab_image(logo_path, width=150, height=64)
        if logo:
            story.extend([logo, Spacer(1, 8)])
    story.extend(
        [
            Paragraph("Bon de maintenance planifiee AFRILUX SMART SOLUTIONS", styles["Title"]),
            Spacer(1, 12),
            Table(data, colWidths=[150, 340]),
            Spacer(1, 12),
            Paragraph("Check-list realisee", styles["Heading2"]),
        ]
    )
    checklist_table = Table(checklist_rows, colWidths=[490])
    checklist_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E8D5BF")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ]
        )
    )
    story.extend(
        [
            checklist_table,
            Spacer(1, 12),
            Paragraph("Observations techniques", styles["Heading2"]),
            Paragraph(report.observations or "-", styles["BodyText"]),
            Spacer(1, 12),
            Paragraph("Observations, anomalies et travaux a prevoir", styles["Heading2"]),
            Paragraph(report.work_to_plan or "-", styles["BodyText"]),
            Spacer(1, 12),
            Paragraph("Pieces / consommables", styles["Heading2"]),
            Paragraph(
                " - ".join(
                    [
                        "Remplacables: Oui" if parts_status.get("remplacables") else "Remplacables: Non",
                        "Ajoutables: Oui" if parts_status.get("ajoutables") else "Ajoutables: Non",
                        "Defectueuses: Oui" if parts_status.get("defectueuses") else "Defectueuses: Non",
                    ]
                ),
                styles["BodyText"],
            ),
            Paragraph(parts_text, styles["BodyText"]),
        ]
    )
    if report.client_signature_file:
        story.extend([Spacer(1, 12), Paragraph("Signature client", styles["Heading3"])])
        signature = _safe_reportlab_image(report.client_signature_file.path, width=220, height=90)
        if signature:
            story.append(signature)
        else:
            story.append(Paragraph(report.client_signature_file.name.split("/")[-1], styles["BodyText"]))
    photo_items = list(report.photo_files.all()[:5])
    if photo_items:
        story.extend([Spacer(1, 12), Paragraph("Photos jointes", styles["Heading3"])])
        photo_rows = [["Note", "Fichier"]]
        for photo in photo_items:
            photo_rows.append([photo.note or "-", photo.file.name.split("/")[-1]])
        photo_table = Table(photo_rows, colWidths=[240, 250])
        photo_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E8D5BF")),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ]
            )
        )
        story.append(photo_table)
        for photo in photo_items:
            try:
                lower_name = photo.file.name.lower()
                if lower_name.endswith((".jpg", ".jpeg", ".png")):
                    image = _safe_reportlab_image(photo.file.path, width=220, height=150)
                    if image:
                        story.extend(
                            [
                                Spacer(1, 8),
                                Paragraph(photo.note or "Photo maintenance", styles["BodyText"]),
                                image,
                            ]
                        )
            except Exception:
                continue

    document.build(story)
    content = buffer.getvalue()
    if persist:
        filename = f"maintenance-{maintenance_ticket.id}-{timezone.localdate():%Y%m%d}.pdf"
        report.report_pdf.save(filename, ContentFile(content), save=False)
        report.report_generated_at = timezone.now()
        report.save(update_fields=["report_pdf", "report_generated_at", "updated_at"])
    return content


def send_intervention_assignment_email(intervention, pdf_content=None):
    technician = intervention.agent
    recipient = (technician.professional_email or technician.email or "").strip()
    if not recipient:
        return False

    pdf_content = pdf_content or generate_intervention_pdf(intervention, persist=False)
    message = EmailMessage(
        subject=f"Bon d'intervention {intervention.ticket.reference}",
        body=(
            "Veuillez trouver en piece jointe votre bon d'intervention AFRILUX. "
            "Merci de mettre a jour le rapport apres passage sur site."
        ),
        to=[recipient],
    )
    filename = f"intervention-{slugify(intervention.ticket.reference)}-{intervention.pk}.pdf"
    message.attach(filename, pdf_content, "application/pdf")
    try:
        return bool(message.send(fail_silently=False))
    except Exception as exc:  # noqa: BLE001
        log_audit_event(
            actor=technician,
            action="intervention_assignment_email_failed",
            instance=intervention,
            details={"recipient": recipient, "error": str(exc)[:1000]},
        )
        return False


def send_ticket_closure_report_notifications(ticket, intervention, *, pdf_content=None, actor=None):
    managers = list(manager_queryset_for_organization(ticket.organization))
    if not managers:
        return []

    pdf_content = pdf_content or generate_intervention_pdf(intervention, persist=False)
    filename = f"rapport-intervention-{slugify(ticket.reference)}-{intervention.pk}.pdf"
    notifications = []
    for manager in managers:
        recipient_email = (manager.email or manager.professional_email or "").strip()
        notification = Notification.objects.create(
            recipient=manager,
            ticket=ticket,
            channel=Notification.CHANNEL_EMAIL,
            event_type="ticket_closure_report",
            subject=f"Ticket cloture {ticket.reference}",
            message=(
                f"Le ticket '{ticket.title}' est cloture. "
                "Le rapport PDF d'intervention est joint a cet email."
            ),
            status=Notification.STATUS_PENDING,
            recipient_contact=recipient_email,
            provider="smtp",
            deep_link=build_ticket_deep_link(ticket),
        )
        notifications.append(notification)
        if not recipient_email:
            notification.status = Notification.STATUS_FAILED
            notification.error_message = "Aucune adresse email responsable disponible."
            notification.save(update_fields=["status", "error_message"])
            continue
        try:
            message = EmailMessage(
                subject=notification.subject,
                body=f"{notification.message}\nOuvrir: {notification.deep_link}",
                to=[recipient_email],
            )
            message.attach(filename, pdf_content, "application/pdf")
            message.send(fail_silently=False)
        except Exception as exc:  # noqa: BLE001
            notification.status = Notification.STATUS_FAILED
            notification.error_message = str(exc)[:1000]
            notification.save(update_fields=["status", "error_message"])
            continue
        notification.status = Notification.STATUS_SENT
        notification.sent_at = timezone.now()
        notification.provider_reference = filename
        notification.error_message = ""
        notification.save(update_fields=["status", "sent_at", "provider_reference", "error_message"])

    log_audit_event(
        actor=actor,
        action="ticket_closure_report_notifications",
        instance=ticket,
        details={"notifications": [item.id for item in notifications]},
    )
    return notifications


def archive_generated_report(
    *,
    organization,
    report,
    report_type,
    export_format,
    generated_by=None,
    filename,
    content,
    sent_to="",
):
    record = GeneratedReport.objects.create(
        organization=organization,
        generated_by=generated_by,
        report_type=report_type,
        export_format=export_format,
        period_label=report.get("period_label", ""),
        payload=report,
        sent_to=sent_to,
    )
    if content:
        record.archive_file.save(filename, ContentFile(content), save=False)
        record.save(update_fields=["archive_file", "updated_at"])
    return record


def send_report_to_recipients(*, report, report_type, recipients, filename, pdf_content=None):
    if not recipients:
        return False
    message = EmailMessage(
        subject=f"{report.get('title', 'Rapport SAV')} - {report.get('period_label', '')}",
        body="Veuillez trouver en piece jointe le rapport SAV automatise.",
        to=recipients,
    )
    from sav.reporting import export_report_pdf

    pdf_content = pdf_content or export_report_pdf(report)
    message.attach(filename, pdf_content, "application/pdf")
    try:
        return bool(message.send(fail_silently=False))
    except Exception as exc:  # noqa: BLE001
        GeneratedReport.objects.create(
            organization=None,
            report_type=report_type,
            export_format=GeneratedReport.FORMAT_PDF,
            period_label=report.get("period_label", ""),
            payload={"email_failed": True, "error": str(exc)[:1000], "recipients": recipients},
            sent_to=", ".join(recipients),
        )
        return False


def dispatch_maintenance_operational_notifications(*, organization=None, now=None):
    now = timezone.localtime(now or timezone.now())
    today = now.date()
    queryset = MaintenanceTicket.objects.select_related("technician", "responsible", "client", "organization").prefetch_related("team_members").filter(
        status__in=[
            MaintenanceTicket.STATUS_PLANNED,
            MaintenanceTicket.STATUS_NOTIFIED,
            MaintenanceTicket.STATUS_IN_PROGRESS,
            MaintenanceTicket.STATUS_POSTPONED,
        ]
    )
    if organization is not None:
        queryset = queryset.filter(organization=organization)

    sent = {"j_minus_3": 0, "not_realized_j_plus_1": 0}
    for maintenance_ticket in queryset:
        scheduled_day = timezone.localtime(maintenance_ticket.scheduled_date).date()
        if (
            maintenance_ticket.status == MaintenanceTicket.STATUS_PLANNED
            and scheduled_day >= today
            and scheduled_day <= today + timedelta(days=3)
        ):
            from .maintenance import maintenance_team_recipients
            for recipient in maintenance_team_recipients(maintenance_ticket):
                from ..comms import create_external_channel_notifications
                create_external_channel_notifications(
                    recipient=recipient,
                    ticket=None,
                    event_type="maintenance_j_minus_3",
                    subject=f"Maintenance a venir - {maintenance_ticket.title}",
                    message=f"La maintenance planifiee chez {maintenance_ticket.client} est prevue le {timezone.localtime(maintenance_ticket.scheduled_date):%d/%m/%Y %H:%M}.",
                )
            maintenance_ticket.status = MaintenanceTicket.STATUS_NOTIFIED
            maintenance_ticket.notified_at = now
            maintenance_ticket.save(update_fields=["status", "notified_at", "updated_at"])
            sent["j_minus_3"] += 1

        if (
            maintenance_ticket.status
            not in {
                MaintenanceTicket.STATUS_DONE,
                MaintenanceTicket.STATUS_ANOMALY,
                MaintenanceTicket.STATUS_CANCELLED,
            }
            and scheduled_day <= today - timedelta(days=1)
            and not maintenance_ticket.overdue_alerted_at
        ):
            recipients = []
            if maintenance_ticket.responsible_id:
                recipients.append(maintenance_ticket.responsible)
            recipients.extend(manager_queryset_for_organization(maintenance_ticket.organization))
            for recipient in {item.id: item for item in recipients if getattr(item, "id", None)}.values():
                from ..comms import create_external_channel_notifications
                create_external_channel_notifications(
                    recipient=recipient,
                    ticket=None,
                    event_type="maintenance_not_realized_j_plus_1",
                    subject=f"Maintenance non realisee - {maintenance_ticket.title}",
                    message=f"La maintenance planifiee le {timezone.localtime(maintenance_ticket.scheduled_date):%d/%m/%Y %H:%M} n'est pas cloturee.",
                )
                sent["not_realized_j_plus_1"] += 1
            maintenance_ticket.overdue_alerted_at = now
            maintenance_ticket.save(update_fields=["overdue_alerted_at", "updated_at"])

    return sent


def _maintenance_period_bounds(period, anchor_date=None):
    anchor_date = anchor_date or timezone.localdate()
    normalized = str(period or "mensuel").strip().lower()
    if normalized in {"jour", "daily", "journalier"}:
        return anchor_date, anchor_date + timedelta(days=1), "Journalier"
    if normalized in {"semaine", "weekly", "hebdomadaire"}:
        start = anchor_date - timedelta(days=anchor_date.weekday())
        return start, start + timedelta(days=7), "Hebdomadaire"
    if re.fullmatch(r"\d{4}-\d{2}", normalized):
        year, month = [int(item) for item in normalized.split("-")]
        start = anchor_date.replace(year=year, month=month, day=1)
        next_month = start.replace(year=year + 1, month=1, day=1) if month == 12 else start.replace(month=month + 1)
        return start, next_month, normalized
    start = anchor_date.replace(day=1)
    next_month = start.replace(year=start.year + 1, month=1, day=1) if start.month == 12 else start.replace(month=start.month + 1)
    return start, next_month, "Mensuel"


def build_maintenance_period_report(period, user, *, anchor_date=None):
    from .roles import scope_maintenance_ticket_queryset
    start, end, label = _maintenance_period_bounds(period, anchor_date=anchor_date)
    start_dt = timezone.make_aware(datetime.combine(start, datetime.min.time()))
    end_dt = timezone.make_aware(datetime.combine(end, datetime.min.time()))
    tickets = scope_maintenance_ticket_queryset(
        MaintenanceTicket.objects.select_related("client", "technician").prefetch_related("team_members"),
        user,
    ).filter(
        scheduled_date__gte=start_dt,
        scheduled_date__lt=end_dt,
    )
    total = tickets.count()
    done = tickets.filter(status=MaintenanceTicket.STATUS_DONE).count()
    anomalies = tickets.filter(status=MaintenanceTicket.STATUS_ANOMALY).count()
    postponed = tickets.filter(status=MaintenanceTicket.STATUS_POSTPONED).count()
    cancelled = tickets.filter(status=MaintenanceTicket.STATUS_CANCELLED).count()
    generated_incidents = tickets.filter(anomaly_ticket__isnull=False).count()
    postponed_delays = []
    for item in tickets.filter(postponed_to__isnull=False):
        original_date = item.initial_scheduled_date or item.created_at
        postponed_delays.append((item.postponed_to - original_date).total_seconds() / 86400)

    return {
        "title": "Bilan de maintenance planifiee",
        "report_type": "maintenance",
        "period_label": label,
        "period": label,
        "date_from": start.isoformat(),
        "date_to": end.isoformat(),
        "total": total,
        "done": done,
        "postponed": postponed,
        "cancelled": cancelled,
        "anomalies": anomalies,
        "generated_incidents": generated_incidents,
        "realization_rate": round((done / total) * 100, 1) if total else 0,
        "anomaly_rate": round((anomalies / total) * 100, 1) if total else 0,
        "average_postponement_delay_days": round(sum(postponed_delays) / len(postponed_delays), 1) if postponed_delays else 0,
        "tickets": [
            {
                "id": item.id,
                "title": item.title,
                "client": str(item.client),
                "technician": item.technician_team_label,
                "scheduled_date": item.scheduled_date.isoformat(),
                "status": item.status,
                "incident_reference": item.anomaly_ticket.reference if item.anomaly_ticket_id else "",
            }
            for item in tickets.order_by("scheduled_date", "client__company_name", "title")[:200]
        ],
    }
