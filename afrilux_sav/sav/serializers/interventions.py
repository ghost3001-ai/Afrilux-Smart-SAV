from rest_framework import serializers

from ..models import Intervention, InterventionMedia, InterventionPartUsage


class InterventionMediaInlineSerializer(serializers.ModelSerializer):
    uploaded_by_name = serializers.SerializerMethodField()
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = InterventionMedia
        fields = [
            "id",
            "intervention",
            "uploaded_by",
            "uploaded_by_name",
            "kind",
            "file",
            "file_url",
            "note",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["uploaded_by", "uploaded_by_name", "file_url", "created_at", "updated_at"]

    def get_uploaded_by_name(self, obj):
        if not obj.uploaded_by:
            return None
        return str(obj.uploaded_by)

    def get_file_url(self, obj):
        if not obj.file:
            return ""
        request = self.context.get("request")
        if request:
            return request.build_absolute_uri(obj.file.url)
        return obj.file.url


class InterventionMediaSerializer(InterventionMediaInlineSerializer):
    class Meta(InterventionMediaInlineSerializer.Meta):
        fields = InterventionMediaInlineSerializer.Meta.fields


class InterventionInlineSerializer(serializers.ModelSerializer):
    agent_name = serializers.SerializerMethodField()
    media = serializers.SerializerMethodField()

    class Meta:
        model = Intervention
        fields = [
            "id",
            "agent",
            "agent_name",
            "intervention_type",
            "status",
            "scheduled_for",
            "started_at",
            "finished_at",
            "client_validation_requested_at",
            "client_validated_start_at",
            "client_validated_finish_at",
            "client_validation_impossible",
            "validation_impossible_reason",
            "validation_impossible_photo",
            "diagnosis",
            "action_taken",
            "parts_used",
            "structured_parts_used",
            "time_spent_minutes",
            "technical_report",
            "location_snapshot",
            "client_signed_by",
            "client_signed_at",
            "client_signature_file",
            "report_pdf",
            "report_generated_at",
            "media",
            "created_at",
        ]

    def get_agent_name(self, obj):
        return str(obj.agent)

    def get_media(self, obj):
        return InterventionMediaInlineSerializer(obj.media.all(), many=True, context=self.context).data


class InterventionSerializer(InterventionInlineSerializer):
    class Meta(InterventionInlineSerializer.Meta):
        fields = ["ticket", *InterventionInlineSerializer.Meta.fields]

    def validate(self, attrs):
        attrs = super().validate(attrs)
        ticket = attrs.get("ticket") or getattr(self.instance, "ticket", None)
        agent = attrs.get("agent") or getattr(self.instance, "agent", None)
        if ticket and agent and agent.organization_id and ticket.organization_id and agent.organization_id != ticket.organization_id:
            raise serializers.ValidationError("L'agent selectionne appartient a une autre organisation.")
        return attrs


class InterventionPartUsageSerializer(serializers.ModelSerializer):
    spare_part_label = serializers.SerializerMethodField()
    intervention_reference = serializers.CharField(source="intervention.ticket.reference", read_only=True)
    organization_name = serializers.CharField(source="organization.display_name", read_only=True)

    class Meta:
        model = InterventionPartUsage
        fields = [
            "id",
            "organization",
            "organization_name",
            "intervention",
            "intervention_reference",
            "spare_part",
            "spare_part_label",
            "name_snapshot",
            "reference_snapshot",
            "category_snapshot",
            "quantity",
            "unit_snapshot",
            "note",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "organization",
            "organization_name",
            "intervention_reference",
            "spare_part_label",
            "created_at",
            "updated_at",
        ]

    def get_spare_part_label(self, obj):
        return str(obj.spare_part) if obj.spare_part else ""
