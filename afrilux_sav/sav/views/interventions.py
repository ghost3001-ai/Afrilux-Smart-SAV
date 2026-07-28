from django.http import HttpResponse
from rest_framework import filters, mixins, parsers, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from ..models import Intervention, InterventionMedia, InterventionPartUsage, User
from ..permissions import IsAuthenticatedSavUser, IsInternalUser, ReadOnlyForAuditors
from ..serializers import (
    InterventionMediaSerializer,
    InterventionPartUsageSerializer,
    InterventionSerializer,
)
from ..services import (
    can_record_ticket_intervention,
    generate_intervention_pdf,
    is_internal_user,
    log_audit_event,
    notify_ticket_status_change,
    scope_intervention_media_queryset,
    scope_intervention_part_usage_queryset,
    scope_intervention_queryset,
)
from .base import AuditedModelViewSet


def _ticket_status_from_intervention(intervention):
    from ..models import Ticket
    if intervention.status == Intervention.STATUS_DONE or intervention.finished_at:
        return Ticket.STATUS_DONE
    if intervention.status == Intervention.STATUS_IN_PROGRESS or intervention.started_at:
        return Ticket.STATUS_IN_PROGRESS
    if intervention.status == Intervention.STATUS_CANCELLED:
        return Ticket.STATUS_WAITING_PART
    if intervention.scheduled_for:
        return Ticket.STATUS_PLANNED
    return Ticket.STATUS_ASSIGNED if intervention.ticket.assigned_agent_id else Ticket.STATUS_PENDING_ASSIGNMENT


class InterventionViewSet(AuditedModelViewSet):
    serializer_class = InterventionSerializer
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ["scheduled_for", "created_at"]

    def get_permissions(self):
        if self.request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            return [IsInternalUser()]
        return [IsAuthenticatedSavUser()]

    def get_queryset(self):
        queryset = Intervention.objects.select_related("ticket", "agent").all()
        return scope_intervention_queryset(queryset, self.request.user)

    def perform_create(self, serializer):
        ticket = serializer.validated_data["ticket"]
        if not can_record_ticket_intervention(self.request.user, ticket):
            raise PermissionDenied("Vous ne pouvez intervenir que sur les tickets qui vous sont affectes ou planifies.")
        if (
            not self.request.user.is_superuser
            and self.request.user.organization_id
            and ticket.organization_id != self.request.user.organization_id
        ):
            raise PermissionDenied("Vous ne pouvez pas creer une intervention pour une autre organisation.")
        extra = {"organization": ticket.organization}
        if self.request.user.role in set(User.ASSIGNABLE_ROLES):
            extra["agent"] = self.request.user
            extra["intervention_type"] = Intervention.TYPE_ON_SITE
        instance = serializer.save(**extra)
        if instance.status == Intervention.STATUS_DONE:
            generate_intervention_pdf(instance)
        previous_status = ticket.status
        next_status = _ticket_status_from_intervention(instance)
        if next_status != previous_status:
            ticket.status = next_status
            ticket.save(update_fields=["status", "updated_at"])
            notify_ticket_status_change(ticket, previous_status, actor=self.request.user)
        self.audit("intervention_created", instance)

    def perform_update(self, serializer):
        ticket = serializer.validated_data.get("ticket", serializer.instance.ticket)
        if (
            not self.request.user.is_superuser
            and self.request.user.organization_id
            and ticket.organization_id != self.request.user.organization_id
        ):
            raise PermissionDenied("Vous ne pouvez pas deplacer cette intervention vers une autre organisation.")
        instance = serializer.save(organization=ticket.organization)
        if instance.status == Intervention.STATUS_DONE:
            generate_intervention_pdf(instance)
        self.audit("intervention_updated", instance)

    @action(detail=True, methods=["get"], url_path="report-pdf")
    def report_pdf(self, request, pk=None):
        intervention = self.get_object()
        content = generate_intervention_pdf(intervention, persist=False)
        response = HttpResponse(content, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="intervention-{intervention.ticket.reference}-{intervention.pk}.pdf"'
        return response


class InterventionMediaViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = InterventionMediaSerializer
    permission_classes = [ReadOnlyForAuditors]
    parser_classes = [parsers.MultiPartParser, parsers.FormParser]
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ["created_at", "kind"]

    def get_queryset(self):
        queryset = InterventionMedia.objects.select_related("intervention", "uploaded_by").all()
        queryset = scope_intervention_media_queryset(queryset, self.request.user)
        intervention_id = self.request.query_params.get("intervention")
        if intervention_id:
            queryset = queryset.filter(intervention_id=intervention_id)
        return queryset

    def perform_create(self, serializer):
        intervention = serializer.validated_data["intervention"]
        if (
            is_internal_user(self.request.user)
            and not self.request.user.is_superuser
            and self.request.user.organization_id
            and intervention.organization_id != self.request.user.organization_id
        ):
            raise PermissionDenied("Vous ne pouvez pas ajouter un media sur une autre organisation.")
        if not is_internal_user(self.request.user) and intervention.ticket.client_id != self.request.user.id:
            raise PermissionDenied("Vous ne pouvez pas ajouter un media sur le dossier d'un autre client.")
        instance = serializer.save(uploaded_by=self.request.user, organization=intervention.organization)
        log_audit_event(
            self.request.user,
            "intervention_media_created",
            instance,
            {"ticket_reference": intervention.ticket.reference},
        )


class InterventionPartUsageViewSet(AuditedModelViewSet):
    serializer_class = InterventionPartUsageSerializer
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ["created_at", "quantity"]

    def get_permissions(self):
        if self.request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            return [IsInternalUser()]
        return [IsAuthenticatedSavUser()]

    def get_queryset(self):
        queryset = InterventionPartUsage.objects.select_related("organization", "intervention__ticket", "spare_part").all()
        return scope_intervention_part_usage_queryset(queryset, self.request.user)

    def perform_create(self, serializer):
        intervention = serializer.validated_data["intervention"]
        if not can_record_ticket_intervention(self.request.user, intervention.ticket):
            raise PermissionDenied("Vous ne pouvez declarer des pieces que sur vos interventions autorisees.")
        instance = serializer.save(organization=intervention.organization)
        self.audit("intervention_part_usage_created", instance)

    def perform_update(self, serializer):
        instance = serializer.save()
        self.audit("intervention_part_usage_updated", instance)
