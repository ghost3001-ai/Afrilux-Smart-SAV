from rest_framework import serializers

from ..models import AutomationRule, OfflineSyncOperation, WorkflowExecution


class AutomationRuleSerializer(serializers.ModelSerializer):
    organization_name = serializers.CharField(source="organization.display_name", read_only=True)

    class Meta:
        model = AutomationRule
        fields = [
            "id",
            "organization",
            "organization_name",
            "name",
            "description",
            "trigger_event",
            "is_active",
            "priority",
            "conditions",
            "actions",
            "created_at",
            "updated_at",
        ]


class WorkflowExecutionSerializer(serializers.ModelSerializer):
    rule_name = serializers.CharField(source="rule.name", read_only=True)
    ticket_reference = serializers.CharField(source="ticket.reference", read_only=True)
    organization_name = serializers.CharField(source="organization.display_name", read_only=True)

    class Meta:
        model = WorkflowExecution
        fields = [
            "id",
            "organization",
            "organization_name",
            "rule",
            "rule_name",
            "ticket",
            "ticket_reference",
            "status",
            "trigger_event",
            "result",
            "created_at",
        ]


class OfflineSyncOperationSerializer(serializers.ModelSerializer):
    user_name = serializers.SerializerMethodField()
    organization_name = serializers.CharField(source="organization.display_name", read_only=True)

    class Meta:
        model = OfflineSyncOperation
        fields = [
            "id",
            "organization",
            "organization_name",
            "user",
            "user_name",
            "device",
            "operation_uuid",
            "endpoint",
            "method",
            "payload",
            "status",
            "error_message",
            "client_created_at",
            "applied_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "organization",
            "organization_name",
            "user",
            "user_name",
            "operation_uuid",
            "status",
            "error_message",
            "applied_at",
            "created_at",
            "updated_at",
        ]

    def get_user_name(self, obj):
        return str(obj.user)
