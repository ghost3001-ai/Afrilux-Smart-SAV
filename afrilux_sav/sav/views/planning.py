from datetime import datetime, time, timedelta

from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from ..models import Intervention, MaintenanceTicket, SupportSession, Ticket, User
from ..permissions import IsAuthenticatedSavUser, IsManagerUser
from ..serializers import TechnicianAvailabilitySerializer
from ..services import (
    compute_technician_availability_rows,
    is_support_user,
    is_manager_user as _is_manager_user,
    scope_intervention_queryset,
    scope_maintenance_ticket_queryset,
    scope_support_session_queryset,
    scope_ticket_queryset,
    scope_user_queryset,
)
from .base import _parse_anchor_date, _request_bool


class TechnicianPlanningView(APIView):
    permission_classes = [IsAuthenticatedSavUser]

    def get(self, request, pk):
        from ..services import OPEN_TICKET_STATUSES
        if not (_is_manager_user(request.user) or is_support_user(request.user)):
            raise PermissionDenied("Le planning technicien est reserve aux profils de supervision et de dispatch.")
        technician_queryset = User.objects.filter(role__in=User.TECHNICIAN_SPACE_ROLES, is_active=True)
        if not request.user.is_superuser and request.user.organization_id:
            technician_queryset = technician_queryset.filter(organization=request.user.organization)
        technician = get_object_or_404(technician_queryset, pk=pk)
        date_from = _parse_anchor_date(request.query_params.get("date_from")) or timezone.localdate()
        date_to = _parse_anchor_date(request.query_params.get("date_to")) or (date_from + timedelta(days=7))
        start_dt = timezone.make_aware(datetime.combine(date_from, time.min))
        end_dt = timezone.make_aware(datetime.combine(date_to, time.min))
        tickets = scope_ticket_queryset(
            Ticket.objects.select_related("client", "product", "assigned_agent"),
            request.user,
        ).filter(assigned_agent=technician, status__in=OPEN_TICKET_STATUSES)
        interventions = scope_intervention_queryset(
            Intervention.objects.select_related("ticket", "ticket__client", "agent"),
            request.user,
        ).filter(agent=technician, scheduled_for__gte=start_dt, scheduled_for__lt=end_dt)
        sessions = scope_support_session_queryset(
            SupportSession.objects.select_related("ticket", "client", "agent"),
            request.user,
        ).filter(agent=technician, scheduled_for__gte=start_dt, scheduled_for__lt=end_dt)
        maintenance_tickets = scope_maintenance_ticket_queryset(
            MaintenanceTicket.objects.select_related("client", "technician").prefetch_related("products"),
            request.user,
        ).filter(technician=technician, scheduled_date__gte=start_dt, scheduled_date__lt=end_dt)
        return Response({
            "technician_id": technician.id,
            "technician_name": str(technician),
            "technician_status": technician.technician_status,
            "specialties": technician.specialties,
            "primary_city": technician.primary_city,
            "primary_region": technician.primary_region,
            "weekly_availability": technician.weekly_availability,
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "tickets_assignes": [
                {
                    "id": ticket.id,
                    "reference": ticket.reference,
                    "title": ticket.title,
                    "client": str(ticket.client),
                    "status": ticket.status,
                    "priority": ticket.priority,
                    "sla_deadline": ticket.sla_deadline.isoformat() if ticket.sla_deadline else None,
                }
                for ticket in tickets[:100]
            ],
            "interventions": [
                {
                    "id": intervention.id,
                    "ticket_reference": intervention.ticket.reference,
                    "client": str(intervention.ticket.client),
                    "status": intervention.status,
                    "scheduled_for": intervention.scheduled_for.isoformat() if intervention.scheduled_for else None,
                    "action_taken": intervention.action_taken,
                }
                for intervention in interventions
            ],
            "sessions_support": [
                {
                    "id": session.id,
                    "ticket_reference": session.ticket.reference,
                    "client": str(session.client),
                    "status": session.status,
                    "scheduled_for": session.scheduled_for.isoformat() if session.scheduled_for else None,
                    "session_type": session.session_type,
                }
                for session in sessions
            ],
            "maintenances_planifiees": [
                {
                    "id": item.id,
                    "title": item.title,
                    "client": str(item.client),
                    "status": item.status,
                    "priority": item.priority,
                    "scheduled_date": item.scheduled_date.isoformat(),
                    "badge": "MAINTENANCE",
                    "location": item.location,
                }
                for item in maintenance_tickets
            ],
        })


class TechnicianAvailabilityView(APIView):
    permission_classes = [IsManagerUser]

    def get(self, request):
        from rest_framework import status as http_status
        organization = request.user.organization
        if not organization:
            return Response(
                {"detail": "Vous devez appartenir a une organisation."},
                status=http_status.HTTP_400_BAD_REQUEST,
            )
        rows = compute_technician_availability_rows(organization)
        after_param = request.query_params.get("after")
        after_dt = None
        if after_param:
            try:
                after_dt = timezone.datetime.fromisoformat(after_param.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                return Response(
                    {"detail": "Format 'after' invalide. Utilisez ISO 8601."},
                    status=http_status.HTTP_400_BAD_REQUEST,
                )
        skills = [item.strip().lower() for item in request.query_params.get("skills", "").split(",") if item.strip()]
        sector = (request.query_params.get("sector") or request.query_params.get("region") or "").strip().lower()
        if skills:
            rows = [
                row for row in rows
                if any(skill in " ".join(row.get("specialties") or []).lower() for skill in skills)
            ]
        if sector:
            rows = [
                row for row in rows
                if sector in (row.get("primary_city") or "").lower()
                or sector in (row.get("primary_region") or "").lower()
            ]
        if _request_bool(request.query_params, "assignable_only", False):
            rows = [row for row in rows if row.get("assignable")]
        if after_dt:
            rows = [
                row for row in rows
                if not row.get("next_available_at") or row["next_available_at"] <= after_dt
            ]
        rows.sort(key=lambda row: row.get("next_available_at") or timezone.now())
        serializer = TechnicianAvailabilitySerializer(rows, many=True)
        return Response({
            "count": len(serializer.data),
            "results": serializer.data,
            "requested_at": timezone.now(),
        })
