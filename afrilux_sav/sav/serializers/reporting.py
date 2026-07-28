from rest_framework import serializers

from ..models import GeneratedReport, SlaRule, TicketAssignment


class SlaRuleSerializer(serializers.ModelSerializer):
    organization_name = serializers.CharField(source="organization.display_name", read_only=True)
    priority_label = serializers.CharField(source="get_priority_display", read_only=True)

    class Meta:
        model = SlaRule
        fields = [
            "id",
            "organization",
            "organization_name",
            "priority",
            "priority_label",
            "response_deadline_minutes",
            "resolution_deadline_hours",
            "is_active",
            "created_at",
            "updated_at",
        ]


class GeneratedReportSerializer(serializers.ModelSerializer):
    organization_name = serializers.CharField(source="organization.display_name", read_only=True)
    generated_by_name = serializers.SerializerMethodField()
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = GeneratedReport
        fields = [
            "id",
            "organization",
            "organization_name",
            "generated_by",
            "generated_by_name",
            "report_type",
            "export_format",
            "period_label",
            "payload",
            "archive_file",
            "file_url",
            "sent_to",
            "created_at",
            "updated_at",
        ]

    def get_generated_by_name(self, obj):
        if not obj.generated_by:
            return None
        return str(obj.generated_by)

    def get_file_url(self, obj):
        if not obj.archive_file:
            return ""
        request = self.context.get("request")
        if request:
            return request.build_absolute_uri(obj.archive_file.url)
        return obj.archive_file.url


class TicketAssignmentSerializer(serializers.ModelSerializer):
    ticket_reference = serializers.CharField(source="ticket.reference", read_only=True)
    technician_name = serializers.SerializerMethodField()
    assigned_by_name = serializers.SerializerMethodField()
    organization_name = serializers.CharField(source="organization.display_name", read_only=True)

    class Meta:
        model = TicketAssignment
        fields = [
            "id",
            "organization",
            "organization_name",
            "ticket",
            "ticket_reference",
            "technician",
            "technician_name",
            "assigned_by",
            "assigned_by_name",
            "assigned_at",
            "released_at",
            "status",
            "note",
            "created_at",
            "updated_at",
        ]

    def get_technician_name(self, obj):
        return str(obj.technician)

    def get_assigned_by_name(self, obj):
        if not obj.assigned_by:
            return None
        return str(obj.assigned_by)


class TechnicianAvailabilitySerializer(serializers.Serializer):
    """Sérialise la disponibilité d'un technicien"""
    id = serializers.IntegerField()
    name = serializers.CharField()
    email = serializers.EmailField()
    role = serializers.CharField()
    status = serializers.CharField()  # "available", "busy", "absent"
    status_label = serializers.CharField(required=False)
    assignable = serializers.BooleanField(required=False)
    assignable_label = serializers.CharField(required=False)
    next_available_at = serializers.DateTimeField(allow_null=True)
    busy_until = serializers.DateTimeField(allow_null=True)
    can_be_leader = serializers.BooleanField()
    can_be_member = serializers.BooleanField()
    current_tickets_count = serializers.IntegerField()
    sav_active_count = serializers.IntegerField(required=False)
    maintenance_active_count = serializers.IntegerField(required=False)
    conflicts_label = serializers.CharField(required=False, allow_blank=True)
    conflicts = serializers.ListField(required=False)
