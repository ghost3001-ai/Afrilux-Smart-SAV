from datetime import timedelta

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.utils import timezone
from django.views.generic import TemplateView

from ..models import Intervention, MaintenanceTicket, Ticket
from ..services import (
    OPEN_TICKET_STATUSES,
    scope_maintenance_ticket_queryset,
    scope_ticket_queryset,
)
from .base import TechnicianWorkspaceRequiredMixin


class TechnicianSpaceView(LoginRequiredMixin, TechnicianWorkspaceRequiredMixin, TemplateView):
    template_name = "sav/technician_space.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        technician = self.request.user
        today = timezone.localdate()
        tickets = (
            scope_ticket_queryset(
                Ticket.objects.select_related("client", "product", "assigned_agent"),
                self.request.user,
            )
            .filter(assigned_agent=technician, status__in=OPEN_TICKET_STATUSES)
            .order_by("priority", "sla_deadline", "-created_at")
        )
        interventions_today = (
            Intervention.objects.select_related("ticket", "ticket__client", "agent")
            .filter(
                agent=technician,
                scheduled_for__date=today,
            )
            .order_by("scheduled_for", "created_at")
        )
        history_30_days = (
            Intervention.objects.select_related("ticket", "ticket__client", "agent")
            .filter(
                agent=technician,
                created_at__gte=timezone.now() - timedelta(days=30),
            )
            .order_by("-created_at")
        )
        maintenance_tickets = (
            scope_maintenance_ticket_queryset(
                MaintenanceTicket.objects.select_related("client", "technician", "anomaly_ticket").prefetch_related("products", "team_members"),
                self.request.user,
            )
            .filter(
                Q(technician=technician) | Q(team_members=technician),
            )
            .filter(
                Q(status__in=[MaintenanceTicket.STATUS_NOTIFIED, MaintenanceTicket.STATUS_IN_PROGRESS, MaintenanceTicket.STATUS_POSTPONED])
                | Q(scheduled_date__date__lte=today + timedelta(days=3))
            )
            .exclude(status__in=[MaintenanceTicket.STATUS_DONE, MaintenanceTicket.STATUS_ANOMALY, MaintenanceTicket.STATUS_CANCELLED])
            .distinct()
            .order_by("scheduled_date", "priority", "id")
        )
        maintenance_today = maintenance_tickets.filter(scheduled_date__date=today)
        context.update(
            {
                "technician": technician,
                "assigned_tickets": tickets,
                "sla_due_soon_tickets": tickets.filter(
                    sla_deadline__gte=timezone.now(),
                    sla_deadline__lte=timezone.now() + timedelta(hours=2),
                ),
                "interventions_today": interventions_today,
                "maintenance_tickets": maintenance_tickets,
                "maintenance_today": maintenance_today,
                "route_stops": [
                    {
                        "order": index + 1,
                        "reference": intervention.ticket.reference,
                        "location": intervention.location_snapshot or intervention.ticket.location or intervention.ticket.client.address,
                        "scheduled_for": intervention.scheduled_for,
                        "kind": "incident",
                    }
                    for index, intervention in enumerate(interventions_today)
                ]
                + [
                    {
                        "order": interventions_today.count() + index + 1,
                        "reference": f"MAINT-{maintenance_ticket.id}",
                        "location": maintenance_ticket.location or maintenance_ticket.client.address,
                        "scheduled_for": maintenance_ticket.scheduled_date,
                        "kind": "maintenance",
                    }
                    for index, maintenance_ticket in enumerate(maintenance_today)
                ],
                "history_30_days": history_30_days[:20],
            }
        )
        return context
