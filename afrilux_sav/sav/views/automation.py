from rest_framework import filters, mixins, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from ..models import AutomationRule, OfflineSyncOperation, WorkflowExecution
from ..permissions import IsAuthenticatedSavUser, IsInternalUser, IsManagerUser, ReadOnlyForAuditors
from ..serializers import (
    AutomationRuleSerializer,
    OfflineSyncOperationSerializer,
    WorkflowExecutionSerializer,
)
from ..services import (
    log_audit_event,
    scope_automation_rule_queryset,
    scope_offline_sync_operation_queryset,
    scope_workflow_execution_queryset,
)
from .base import AuditedModelViewSet
from django.utils import timezone


class AutomationRuleViewSet(AuditedModelViewSet):
    serializer_class = AutomationRuleSerializer
    permission_classes = [IsManagerUser]
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ["priority", "created_at", "updated_at"]

    def get_queryset(self):
        return scope_automation_rule_queryset(AutomationRule.objects.all(), self.request.user)

    def perform_create(self, serializer):
        extra = {}
        if not self.request.user.is_superuser and self.request.user.organization_id:
            extra["organization"] = self.request.user.organization
        instance = serializer.save(**extra)
        self.audit("automation_rule_created", instance)

    def perform_update(self, serializer):
        instance = serializer.save()
        self.audit("automation_rule_updated", instance)


class WorkflowExecutionViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = WorkflowExecutionSerializer
    permission_classes = [IsInternalUser]
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ["created_at"]

    def get_queryset(self):
        queryset = WorkflowExecution.objects.select_related("rule", "ticket").all()
        return scope_workflow_execution_queryset(queryset, self.request.user)


class OfflineSyncOperationViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = OfflineSyncOperationSerializer
    permission_classes = [IsAuthenticatedSavUser]
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ["created_at", "client_created_at", "status"]

    def get_queryset(self):
        queryset = OfflineSyncOperation.objects.select_related("organization", "user", "device").all()
        queryset = scope_offline_sync_operation_queryset(queryset, self.request.user)
        status_value = self.request.query_params.get("status")
        if status_value:
            queryset = queryset.filter(status=status_value)
        return queryset

    def perform_create(self, serializer):
        device = serializer.validated_data.get("device")
        if device and device.user_id != self.request.user.id:
            raise PermissionDenied("Vous ne pouvez synchroniser qu'un appareil lie a votre compte.")
        instance = serializer.save(user=self.request.user)
        log_audit_event(self.request.user, "offline_sync_operation_queued", instance, {"endpoint": instance.endpoint})

    @action(detail=True, methods=["post"], permission_classes=[IsInternalUser], url_path="mark-applied")
    def mark_applied(self, request, pk=None):
        operation = self.get_object()
        operation.status = OfflineSyncOperation.STATUS_APPLIED
        operation.error_message = ""
        operation.applied_at = timezone.now()
        operation.save(update_fields=["status", "error_message", "applied_at", "updated_at"])
        return Response(self.get_serializer(operation).data)

    @action(detail=True, methods=["post"], permission_classes=[IsInternalUser], url_path="mark-failed")
    def mark_failed(self, request, pk=None):
        operation = self.get_object()
        operation.status = OfflineSyncOperation.STATUS_FAILED
        operation.error_message = request.data.get("error_message", "")
        operation.save(update_fields=["status", "error_message", "updated_at"])
        return Response(self.get_serializer(operation).data)
