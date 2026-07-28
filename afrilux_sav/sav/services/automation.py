import logging
from datetime import timedelta
from decimal import Decimal

from django.db.models import Q
from django.utils import timezone
from django.utils.text import slugify

from ..comms import create_external_channel_notifications
from ..models import (
    AutomationRule,
    GeneratedReport,
    Notification,
    Organization,
    SupportSession,
    Ticket,
    User,
    WorkflowExecution,
)
from .audit import log_audit_event
from .tickets import manager_queryset_for_organization

logger = logging.getLogger(__name__)


def conditions_match_ticket(ticket, conditions, sentiment_score):
    """Verifie si les conditions d'une regle d'automation sont satisfaites par le ticket.

    Args:
        ticket: Instance du modele Ticket.
        conditions: Dictionnaire des conditions a verifier (priorite, statut, domaine, etc.).
        sentiment_score: Score de sentiment du ticket (Decimal entre -1 et 1).

    Returns:
        True si toutes les conditions sont satisfaites, False sinon.
    """
    if not conditions:
        return True

    if "priority" in conditions and ticket.priority != conditions["priority"]:
        return False
    if "status" in conditions and ticket.status != conditions["status"]:
        return False
    if "category" in conditions and ticket.category != conditions["category"]:
        return False
    if "overdue" in conditions and ticket.is_overdue != conditions["overdue"]:
        return False
    if "has_product" in conditions and bool(ticket.product_id) != conditions["has_product"]:
        return False
    if "sentiment_below" in conditions and sentiment_score >= Decimal(str(conditions["sentiment_below"])):
        return False

    return True


def execute_rule_action(ticket, action, actor=None):
    """Execute une action de regle d'automation sur un ticket.

    Actions supportees: assign_least_loaded_agent, set_priority, change_status,
    notify_manager, create_support_session, credit_account.

    Args:
        ticket: Instance du modele Ticket.
        action: Dictionnaire decrivant l'action (type + parametres).
        actor: Utilisateur ayant déclenché l'action (optionnel).

    Returns:
        Dictionnaire decrivant le resultat de l'action executee.

    Raises:
        ValueError: Si le type d'action est inconnu ou les parametres invalides.
    """
    if isinstance(action, str):
        action = {"type": action}

    action_type = action.get("type")
    result = {"type": action_type}

    if action_type == "assign_least_loaded_agent":
        from .analytics import select_least_loaded_agent
        agent = select_least_loaded_agent(ticket.organization)
        if agent:
            ticket.assigned_agent = agent
            if ticket.status == Ticket.STATUS_NEW:
                ticket.status = Ticket.STATUS_ASSIGNED
                ticket.save(update_fields=["assigned_agent", "status", "updated_at"])
            else:
                ticket.save(update_fields=["assigned_agent", "updated_at"])
            from .interventions import ensure_assignment_intervention
            ensure_assignment_intervention(ticket, actor=actor, note="Affectation automatique du moteur de workflow.")
            result["assigned_agent"] = str(agent)
        return result

    if action_type == "set_priority":
        new_priority = action.get("value", Ticket.PRIORITY_HIGH)
        ticket.priority = new_priority
        ticket.save(update_fields=["priority", "updated_at"])
        result["priority"] = new_priority
        return result

    if action_type == "change_status":
        new_status = action.get("value", Ticket.STATUS_ASSIGNED)
        ticket.status = new_status
        ticket.save(update_fields=["status", "updated_at"])
        result["status"] = new_status
        return result

    if action_type == "notify_manager":
        from .tickets import create_notification
        created_notifications = []
        for manager in manager_queryset_for_organization(ticket.organization):
            notification = create_notification(
                recipient=manager,
                ticket=ticket,
                channel=Notification.CHANNEL_IN_APP,
                event_type="workflow_notification",
                subject=f"Escalade ticket {ticket.reference}",
                message=f"Le workflow a signale le ticket '{ticket.title}' comme prioritaire.",
            )
            created_notifications.append(notification.id)
        result["notifications"] = created_notifications
        return result

    if action_type == "create_offer_recommendations":
        from .financial import generate_offer_recommendations
        offers = generate_offer_recommendations(client=ticket.client, ticket=ticket, product=ticket.product, persist=True)
        result["offers"] = [item["offer"].id for item in offers]
        return result

    if action_type == "schedule_ar_session":
        session = SupportSession.objects.filter(
            ticket=ticket,
            status__in=[SupportSession.STATUS_SCHEDULED, SupportSession.STATUS_LIVE],
        ).first()
        if not session:
            from .analytics import select_least_loaded_agent
            session = SupportSession.objects.create(
                ticket=ticket,
                client=ticket.client,
                agent=ticket.assigned_agent or select_least_loaded_agent(ticket.organization),
                session_type=SupportSession.TYPE_AR,
                status=SupportSession.STATUS_SCHEDULED,
                meeting_link="https://support.afrilux.local/ar-session",
                scheduled_for=timezone.now() + timedelta(hours=1),
                annotations_summary="Session AR creee automatiquement par le moteur de workflow.",
            )
        result["support_session"] = session.id
        return result

    if action_type == "credit_account":
        from .financial import credit_account_for_ticket
        credit_payload = credit_account_for_ticket(
            ticket,
            amount=action.get("amount", "0"),
            actor=actor,
            reason=action.get("reason", "Credit automatique SAV"),
            note=action.get("note", ""),
            currency=action.get("currency", "XAF"),
            external_reference=action.get("external_reference", ""),
        )
        result["credit_id"] = credit_payload["credit"].id
        result["amount"] = str(credit_payload["credit"].amount)
        result["currency"] = credit_payload["credit"].currency
        return result

    result["ignored"] = True
    return result


def _safe_execute_rule_action(ticket, action, actor=None):
    try:
        return execute_rule_action(ticket, action, actor=actor)
    except Exception as exc:
        action_type = action.get("type") if isinstance(action, dict) else str(action)
        logger.exception("Erreur lors de l'execution de l'action workflow '%s' sur le ticket %s", action_type, ticket.reference)
        return {"type": action_type, "error": str(exc)}


def run_automation_rules_for_ticket(ticket, actor=None, trigger_event=AutomationRule.TRIGGER_MANUAL):
    """Execute toutes les regles d'automation applicables a un ticket.

    Evalue les regles actives dont le trigger correspond, verifie les conditions
    et execute les actions associees. En l'absence de regle, applique les actions
    integrees (affectation, notification, session AR).

    Args:
        ticket: Instance du modele Ticket.
        actor: Utilisateur ayant déclenché l'evaluation (optionnel).
        trigger_event: Evenement déclencheur (creation, changement_statut, manuel, etc.).

    Returns:
        Dictionnaire contenant les IDs des executions et leurs resultats.
    """
    from .analytics import calculate_sentiment
    full_text = " ".join([ticket.title, ticket.description] + list(ticket.messages.values_list("content", flat=True)))
    sentiment_score = calculate_sentiment(full_text)
    rules = (
        AutomationRule.objects.filter(is_active=True, trigger_event=trigger_event)
        .filter(Q(organization=ticket.organization) | Q(organization__isnull=True))
        .order_by("priority")
    )

    execution_results = []

    if not rules.exists():
        builtin_actions = []
        if ticket.priority == Ticket.PRIORITY_CRITICAL and not ticket.assigned_agent:
            builtin_actions.append({"type": "assign_least_loaded_agent"})
        if ticket.priority in {Ticket.PRIORITY_HIGH, Ticket.PRIORITY_CRITICAL} or ticket.is_overdue:
            builtin_actions.append({"type": "notify_manager"})
        if sentiment_score <= Decimal("-0.50") and ticket.category in {
            Ticket.CATEGORY_BREAKDOWN,
            Ticket.CATEGORY_INSTALLATION,
        }:
            builtin_actions.append({"type": "schedule_ar_session"})

        if not builtin_actions:
            execution = WorkflowExecution.objects.create(
                ticket=ticket,
                status=WorkflowExecution.STATUS_SKIPPED,
                trigger_event=trigger_event,
                result={"reason": "no_rule_matched"},
            )
            return {"executions": [execution.id], "results": [execution.result]}

        action_results = [_safe_execute_rule_action(ticket, action, actor=actor) for action in builtin_actions]
        execution = WorkflowExecution.objects.create(
            ticket=ticket,
            status=WorkflowExecution.STATUS_SUCCESS,
            trigger_event=trigger_event,
            result={"builtin": True, "actions": action_results},
        )
        log_audit_event(
            actor=actor,
            action="automation_executed",
            instance=ticket,
            details={"workflow_execution_id": execution.id, "builtin": True},
        )
        return {"executions": [execution.id], "results": action_results}

    for rule in rules:
        if not conditions_match_ticket(ticket, rule.conditions, sentiment_score):
            execution = WorkflowExecution.objects.create(
                rule=rule,
                ticket=ticket,
                status=WorkflowExecution.STATUS_SKIPPED,
                trigger_event=trigger_event,
                result={"reason": "conditions_not_met"},
            )
            execution_results.append({"execution_id": execution.id, "result": execution.result})
            continue

        action_results = [_safe_execute_rule_action(ticket, action, actor=actor) for action in rule.actions]
        execution = WorkflowExecution.objects.create(
            rule=rule,
            ticket=ticket,
            status=WorkflowExecution.STATUS_SUCCESS,
            trigger_event=trigger_event,
            result={"actions": action_results},
        )
        execution_results.append({"execution_id": execution.id, "result": action_results})
        log_audit_event(
            actor=actor,
            action="automation_rule_executed",
            instance=ticket,
            details={"workflow_execution_id": execution.id, "rule_id": rule.id},
        )

    return {
        "executions": [item["execution_id"] for item in execution_results],
        "results": [item["result"] for item in execution_results],
    }


def notify_ticket_status_change(ticket, previous_status, *, actor=None):
    if not previous_status or previous_status == ticket.status:
        return []

    notifications = []
    previous_public_status = Ticket.PUBLIC_STATUS_MAP.get(
        Ticket.normalize_process_status(previous_status),
        previous_status,
    )
    current_public_status = ticket.public_status
    client_action_statuses = {
        Ticket.STATUS_PLANNING_PROPOSED,
        Ticket.STATUS_START_REQUESTED,
        Ticket.STATUS_FINISH_REQUESTED,
    }
    if previous_public_status != current_public_status or ticket.status in client_action_statuses:
        notifications.extend(
            create_external_channel_notifications(
                recipient=ticket.client,
                ticket=ticket,
                event_type="ticket_status_update",
                subject=f"Mise a jour ticket {ticket.reference}",
                message=f"Le statut de votre ticket est maintenant '{current_public_status}'.",
            )
        )

    if ticket.status == Ticket.STATUS_RESOLVED:
        for manager in manager_queryset_for_organization(ticket.organization):
            notifications.extend(
                create_external_channel_notifications(
                    recipient=manager,
                    ticket=ticket,
                    event_type="ticket_resolved",
                    subject=f"Ticket resolu {ticket.reference}",
                    message=f"Le ticket '{ticket.title}' a ete resolu.",
                )
            )
        if not hasattr(ticket, "feedback") and not Notification.objects.filter(
            ticket=ticket,
            recipient=ticket.client,
            event_type="ticket_csat_request",
        ).exists():
            notifications.extend(
                create_external_channel_notifications(
                    recipient=ticket.client,
                    ticket=ticket,
                    event_type="ticket_csat_request",
                    subject=f"Evaluation satisfaction {ticket.reference}",
                    message=(
                        "Votre ticket est resolu. Merci d'evaluer l'intervention: "
                        "Satisfait / Moyen / Mecontent, avec un commentaire si besoin."
                    ),
                )
            )
    if ticket.status == Ticket.STATUS_CLOSED and not hasattr(ticket, "feedback") and not Notification.objects.filter(
        ticket=ticket,
        recipient=ticket.client,
        event_type="ticket_csat_request",
    ).exists():
        notifications.extend(
            create_external_channel_notifications(
                recipient=ticket.client,
                ticket=ticket,
                event_type="ticket_csat_request",
                subject=f"Evaluation satisfaction {ticket.reference}",
                message=(
                    "Votre ticket est ferme. Merci d'evaluer l'intervention: "
                    "Satisfait / Moyen / Mecontent, avec un commentaire si besoin."
                ),
            )
        )
    if previous_status in {Ticket.STATUS_RESOLVED, Ticket.STATUS_CLOSED} and ticket.status == Ticket.STATUS_NEW:
        recipients = manager_queryset_for_organization(ticket.organization)
        if ticket.assigned_agent_id:
            recipients = list(recipients) + [ticket.assigned_agent]
        for recipient in {item.id: item for item in recipients}.values():
            notifications.extend(
                create_external_channel_notifications(
                    recipient=recipient,
                    ticket=ticket,
                    event_type="ticket_reopened",
                    subject=f"Ticket rouvert {ticket.reference}",
                    message=f"Le ticket '{ticket.title}' a ete rouvert et requiert une reprise en charge.",
                )
            )

    log_audit_event(
        actor=actor,
        action="ticket_status_notification",
        instance=ticket,
        details={"from": previous_status, "to": ticket.status, "notifications": [item.id for item in notifications]},
    )
    return notifications


def _notification_recently_sent(ticket, recipient, event_type, since):
    return Notification.objects.filter(
        ticket=ticket,
        recipient=recipient,
        event_type=event_type,
        created_at__gte=since,
    ).exists()


def dispatch_sla_operational_notifications(*, organization=None, now=None):
    now = now or timezone.now()
    queryset = Ticket.objects.select_related("assigned_agent", "client", "organization").filter(status__in=[
        Ticket.STATUS_NEW,
        Ticket.STATUS_PENDING_ASSIGNMENT,
        Ticket.STATUS_ASSIGNED,
        Ticket.STATUS_TEAM_PENDING,
        Ticket.STATUS_TEAM_READY,
        Ticket.STATUS_PLANNING_PROPOSED,
        Ticket.STATUS_PLANNED,
        Ticket.STATUS_START_REQUESTED,
        Ticket.STATUS_IN_PROGRESS,
        Ticket.STATUS_COLLECTIVE_IN_PROGRESS,
        Ticket.STATUS_WAITING_PART,
        Ticket.STATUS_ESCALATED,
        Ticket.STATUS_WAITING_SOLUTION,
        Ticket.STATUS_WAITING_DIAGNOSTIC,
        Ticket.STATUS_FINISH_REQUESTED,
        Ticket.STATUS_REASSIGN_REQUIRED,
        Ticket.STATUS_REASSIGNED,
    ])
    if organization is not None:
        queryset = queryset.filter(organization=organization)

    sent = {"unassigned_30m": 0, "new_1h": 0, "sla_due_soon": 0, "sla_overdue": 0}

    from django.conf import settings
    dedup_hours = int(getattr(settings, "NOTIFICATION_DEDUP_WINDOW_HOURS", 6) or 6)

    for ticket in queryset:
        managers = list(manager_queryset_for_organization(ticket.organization))
        recent_since = now - timedelta(hours=dedup_hours)

        if ticket.assigned_agent_id is None and ticket.created_at <= now - timedelta(minutes=30):
            for manager in managers:
                if _notification_recently_sent(ticket, manager, "ticket_unassigned_30m", recent_since):
                    continue
                create_external_channel_notifications(
                    recipient=manager,
                    ticket=ticket,
                    event_type="ticket_unassigned_30m",
                    subject=f"Ticket non assigne {ticket.reference}",
                    message=f"Le ticket '{ticket.title}' n'est toujours pas assigne 30 minutes apres sa creation.",
                )
                sent["unassigned_30m"] += 1

        if ticket.status == Ticket.STATUS_NEW and ticket.created_at <= now - timedelta(hours=1):
            for manager in managers:
                if _notification_recently_sent(ticket, manager, "ticket_new_1h", recent_since):
                    continue
                create_external_channel_notifications(
                    recipient=manager,
                    ticket=ticket,
                    event_type="ticket_new_1h",
                    subject=f"Ticket nouveau >1h {ticket.reference}",
                    message=f"Le ticket '{ticket.title}' est encore au statut Nouveau depuis plus d'une heure.",
                )
                sent["new_1h"] += 1

        if ticket.sla_deadline and now <= ticket.sla_deadline <= now + timedelta(hours=2):
            recipients = managers[:]
            if ticket.assigned_agent_id:
                recipients.append(ticket.assigned_agent)
            for recipient in {item.id: item for item in recipients}.values():
                if _notification_recently_sent(ticket, recipient, "sla_due_soon", now - timedelta(hours=2)):
                    continue
                create_external_channel_notifications(
                    recipient=recipient,
                    ticket=ticket,
                    event_type="sla_due_soon",
                    subject=f"SLA proche {ticket.reference}",
                    message=f"Le ticket '{ticket.title}' arrive a echeance SLA dans moins de 2 heures.",
                )
                sent["sla_due_soon"] += 1

        if ticket.is_overdue:
            for manager in managers:
                if _notification_recently_sent(ticket, manager, "sla_overdue", recent_since):
                    continue
                create_external_channel_notifications(
                    recipient=manager,
                    ticket=ticket,
                    event_type="sla_overdue",
                    subject=f"SLA depasse {ticket.reference}",
                    message=f"Le ticket '{ticket.title}' est maintenant en depassement de SLA.",
                )
                sent["sla_overdue"] += 1

    return sent


def auto_close_resolved_tickets(*, organization=None, now=None):
    from .analytics import calculate_sentiment
    now = now or timezone.now()
    queryset = Ticket.objects.select_related("client", "organization").filter(
        status=Ticket.STATUS_RESOLVED,
        resolved_at__isnull=False,
        resolved_at__lte=now - timedelta(hours=72),
    )
    if organization is not None:
        queryset = queryset.filter(organization=organization)

    closed_references = []
    for ticket in queryset:
        previous_status = ticket.status
        ticket.status = Ticket.STATUS_CLOSED
        ticket.closed_at = now
        ticket.save(update_fields=["status", "closed_at", "updated_at"])
        from ..models import Message
        Message.objects.create(
            ticket=ticket,
            sender=ticket.assigned_agent or ticket.client,
            message_type=Message.TYPE_PUBLIC,
            channel=Message.CHANNEL_PORTAL,
            direction=Message.DIRECTION_OUTBOUND,
            content="Le ticket a ete ferme automatiquement 72h apres resolution sans contestation client.",
            sentiment_score=calculate_sentiment("Le ticket a ete ferme automatiquement 72h apres resolution."),
        )
        notify_ticket_status_change(ticket, previous_status, actor=ticket.assigned_agent)
        log_audit_event(
            actor=None,
            actor_type="system",
            action="ticket_auto_closed_72h",
            instance=ticket,
            details={"resolved_at": ticket.resolved_at.isoformat() if ticket.resolved_at else ""},
        )
        closed_references.append(ticket.reference)
    return closed_references


def _due_report_types(now):
    due_types = []
    if now.hour >= 7:
        due_types.append("journalier")
    if now.weekday() == 0 and now.hour >= 8:
        due_types.append("hebdomadaire")
    if now.day == 1 and now.hour >= 8:
        due_types.append("mensuel")
    return due_types


def dispatch_due_reports(*, organization=None, now=None, dry_run=False, report_types=None):
    from .reporting import parse_reporting_recipients, archive_generated_report, send_report_to_recipients

    now = timezone.localtime(now or timezone.now())
    report_types = report_types or _due_report_types(now)
    if not report_types:
        return []

    if organization is None:
        organizations = Organization.objects.filter(is_active=True).order_by("name")
    else:
        organizations = [organization]

    results = []
    for org in organizations:
        actor = (
            User.objects.filter(organization=org, is_active=True)
            .filter(Q(role__in=User.REPORTING_ROLES + User.TECHNICIAN_SPACE_ROLES) | Q(is_superuser=True))
            .order_by("role", "id")
            .first()
        )
        if actor is None:
            results.append({"organization": org.slug, "status": "skipped_no_actor"})
            continue

        recipients = parse_reporting_recipients(org)
        if not recipients:
            results.append({"organization": org.slug, "status": "skipped_no_recipients"})
            continue

        sent_to = ", ".join(recipients)
        for report_type in report_types:
            from .reporting import build_maintenance_period_report
            from sav.reporting import build_report, export_report_pdf
            report = build_report(report_type, actor, anchor_date=now.date())
            if GeneratedReport.objects.filter(
                organization=org,
                report_type=report_type,
                export_format=GeneratedReport.FORMAT_PDF,
                period_label=report.get("period_label", ""),
                sent_to=sent_to,
            ).exists():
                results.append({"organization": org.slug, "report_type": report_type, "status": "already_sent"})
                continue

            filename = f"{report_type}-{slugify(report.get('period_label', 'periode'))}.pdf"
            pdf_content = export_report_pdf(report)
            if dry_run:
                results.append({"organization": org.slug, "report_type": report_type, "status": "dry_run"})
                continue
            try:
                send_report_to_recipients(
                    report=report,
                    report_type=report_type,
                    recipients=recipients,
                    filename=filename,
                    pdf_content=pdf_content,
                )
            except Exception as exc:
                results.append(
                    {
                        "organization": org.slug,
                        "report_type": report_type,
                        "status": "send_failed",
                        "error": str(exc)[:300],
                    }
                )
                continue
            archive_generated_report(
                organization=org,
                report=report,
                report_type=report_type,
                export_format=GeneratedReport.FORMAT_PDF,
                generated_by=actor,
                filename=filename,
                content=pdf_content,
                sent_to=sent_to,
            )
            results.append({"organization": org.slug, "report_type": report_type, "status": "sent"})
    return results
