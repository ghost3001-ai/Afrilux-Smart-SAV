from datetime import timedelta

from django.contrib.auth.mixins import UserPassesTestMixin
from django.db.models import Avg, Count, Q
from django.shortcuts import reverse
from django.utils import timezone

from ..models import (
    Intervention,
    MaintenanceTicket,
    Message,
    Notification,
    PredictiveAlert,
    Product,
    Ticket,
    User,
)
from ..services import (
    OPEN_TICKET_STATUSES,
    compute_agent_performance_rows,
    compute_average_first_response_hours,
    compute_average_resolution_hours,
    compute_technician_availability_dashboard,
    compute_ticket_hotspots,
    compute_ticket_monthly_series,
    compute_ticket_volume_series,
    has_backoffice_access,
    has_reporting_access,
    has_technician_space_access,
    is_internal_user,
    is_manager_user,
    is_support_user,
    role_workspace_name,
    scope_maintenance_ticket_queryset,
    scope_notification_queryset,
    scope_predictive_alert_queryset,
    scope_product_queryset,
    scope_ticket_queryset,
    scope_user_queryset,
)


def _choice_map(choices):
    return dict(choices)


def _percentage(value, total):
    if not total:
        return 0
    return round((value / total) * 100, 1)


def _ticket_status_from_intervention(intervention):
    if intervention.status == Intervention.STATUS_DONE or intervention.finished_at:
        return Ticket.STATUS_DONE
    if intervention.status == Intervention.STATUS_IN_PROGRESS or intervention.started_at:
        return Ticket.STATUS_IN_PROGRESS
    if intervention.status == Intervention.STATUS_CANCELLED:
        return Ticket.STATUS_WAITING_PART
    if intervention.scheduled_for:
        return Ticket.STATUS_PLANNED
    return Ticket.STATUS_ASSIGNED if intervention.ticket.assigned_agent_id else Ticket.STATUS_PENDING_ASSIGNMENT


def _workspace_redirect_url(user):
    workspace_name = role_workspace_name(user)
    if workspace_name == "ticket-list" and is_support_user(user):
        return f"{reverse(workspace_name)}?assignment=mine"
    return reverse(workspace_name)


def _dashboard_snapshot(user):
    tickets = scope_ticket_queryset(Ticket.objects.select_related("client", "product", "assigned_agent"), user)
    products = scope_product_queryset(Product.objects.select_related("client"), user)
    alerts = scope_predictive_alert_queryset(PredictiveAlert.objects.select_related("product", "ticket"), user)
    notifications = scope_notification_queryset(Notification.objects.select_related("ticket"), user)
    maintenance_tickets = scope_maintenance_ticket_queryset(MaintenanceTicket.objects.all(), user)
    messages = Message.objects.filter(ticket__in=tickets, sentiment_score__isnull=False)
    technicians = scope_user_queryset(
        User.objects.filter(role__in=User.TECHNICIAN_SPACE_ROLES, is_active=True),
        user,
    )

    status_labels = _choice_map(Ticket.STATUS_CHOICES)
    priority_labels = _choice_map(Ticket.PRIORITY_CHOICES)

    status_rows = list(tickets.values("status").annotate(total=Count("id")).order_by("status"))
    priority_rows = list(tickets.values("priority").annotate(total=Count("id")).order_by("priority"))
    open_tickets = tickets.filter(status__in=OPEN_TICKET_STATUSES)
    total_tickets = tickets.count()
    average_first_response_hours = compute_average_first_response_hours(tickets)
    average_resolution_hours = compute_average_resolution_hours(tickets)

    return {
        "tickets_total": total_tickets,
        "tickets_open": open_tickets.count(),
        "tickets_overdue": open_tickets.filter(sla_deadline__lt=timezone.now()).count(),
        "tickets_critical_open": open_tickets.filter(priority=Ticket.PRIORITY_CRITICAL).count(),
        "tickets_unassigned": open_tickets.filter(assigned_agent__isnull=True).count(),
        "maintenance_total": tickets.filter(category=Ticket.CATEGORY_MAINTENANCE).count(),
        "planned_maintenance_total": maintenance_tickets.count(),
        "planned_maintenance_active": maintenance_tickets.exclude(
            status__in=[MaintenanceTicket.STATUS_DONE, MaintenanceTicket.STATUS_ANOMALY, MaintenanceTicket.STATUS_CANCELLED],
        ).count(),
        "planned_maintenance_anomalies": maintenance_tickets.filter(status=MaintenanceTicket.STATUS_ANOMALY).count(),
        "bug_total": tickets.filter(category=Ticket.CATEGORY_BUG).count(),
        "products_total": products.count(),
        "products_under_warranty": products.filter(warranty_end__gte=timezone.localdate()).count(),
        "alerts_open": alerts.filter(status__in=[PredictiveAlert.STATUS_OPEN, PredictiveAlert.STATUS_IN_PROGRESS]).count(),
        "alerts_critical": alerts.filter(
            status__in=[PredictiveAlert.STATUS_OPEN, PredictiveAlert.STATUS_IN_PROGRESS],
            severity=PredictiveAlert.SEVERITY_CRITICAL,
        ).count(),
        "notifications_unread": notifications.exclude(status=Notification.STATUS_READ).count(),
        "average_sentiment": messages.aggregate(avg=Avg("sentiment_score"))["avg"],
        "average_first_response_hours": average_first_response_hours,
        "average_resolution_hours": average_resolution_hours,
        "sla_due_soon": open_tickets.filter(
            sla_deadline__gte=timezone.now(),
            sla_deadline__lte=timezone.now() + timedelta(hours=2),
        ).count(),
        "status_breakdown": [
            {
                "value": row["status"],
                "label": status_labels.get(row["status"], row["status"]),
                "total": row["total"],
                "percent": _percentage(row["total"], total_tickets or 1),
            }
            for row in status_rows
        ],
        "priority_breakdown": [
            {
                "value": row["priority"],
                "label": priority_labels.get(row["priority"], row["priority"]),
                "total": row["total"],
                "percent": _percentage(row["total"], total_tickets or 1),
            }
            for row in priority_rows
        ],
        "recent_tickets": list(tickets.order_by("-created_at")[:6]),
        "recent_alerts": list(alerts.order_by("-created_at")[:5]),
        "recent_notifications": list(notifications.order_by("-created_at")[:5]),
        "expiring_products": list(
            products.filter(
                warranty_end__gte=timezone.localdate(),
                warranty_end__lte=timezone.localdate() + timedelta(days=60),
            ).order_by("warranty_end")[:5]
        ),
        "top_agents": compute_agent_performance_rows(tickets),
        "geo_hotspots": compute_ticket_hotspots(tickets),
        "trend_7_days": compute_ticket_volume_series(tickets, days=7),
        "trend_30_days": compute_ticket_volume_series(tickets, days=30),
        "trend_12_months": compute_ticket_monthly_series(tickets, months=12),
        "technician_status_breakdown": compute_technician_availability_dashboard(getattr(user, "organization", None)),
    }


class InternalRequiredMixin(UserPassesTestMixin):
    def test_func(self):
        return is_internal_user(self.request.user)


class ManagerRequiredMixin(UserPassesTestMixin):
    def test_func(self):
        return is_manager_user(self.request.user)


class AdminRequiredMixin(UserPassesTestMixin):
    def test_func(self):
        return bool(
            self.request.user.is_authenticated
            and (self.request.user.is_superuser or self.request.user.role == User.ROLE_ADMIN)
        )


class BackofficeRequiredMixin(UserPassesTestMixin):
    def test_func(self):
        return has_backoffice_access(self.request.user) or getattr(self.request.user, "is_superuser", False)


class ReportingRequiredMixin(UserPassesTestMixin):
    def test_func(self):
        return has_reporting_access(self.request.user)


class TechnicianWorkspaceRequiredMixin(UserPassesTestMixin):
    def test_func(self):
        return has_technician_space_access(self.request.user)
