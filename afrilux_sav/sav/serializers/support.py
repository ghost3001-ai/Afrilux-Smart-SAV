from rest_framework import serializers

from ..models import SupportSession


class SupportSessionInlineSerializer(serializers.ModelSerializer):
    client_name = serializers.SerializerMethodField()
    agent_name = serializers.SerializerMethodField()

    class Meta:
        model = SupportSession
        fields = [
            "id",
            "client",
            "client_name",
            "agent",
            "agent_name",
            "session_type",
            "status",
            "meeting_link",
            "recording_url",
            "annotations_summary",
            "scheduled_for",
            "started_at",
            "ended_at",
            "created_at",
            "updated_at",
        ]

    def get_client_name(self, obj):
        return str(obj.client)

    def get_agent_name(self, obj):
        if not obj.agent:
            return None
        return str(obj.agent)


class SupportSessionSerializer(SupportSessionInlineSerializer):
    class Meta(SupportSessionInlineSerializer.Meta):
        fields = ["ticket", *SupportSessionInlineSerializer.Meta.fields]

    def validate(self, attrs):
        attrs = super().validate(attrs)
        ticket = attrs.get("ticket") or getattr(self.instance, "ticket", None)
        client = attrs.get("client") or getattr(self.instance, "client", None)
        agent = attrs.get("agent") or getattr(self.instance, "agent", None)
        if ticket and client and ticket.client_id != client.id:
            raise serializers.ValidationError("La session doit etre rattachee au client du ticket.")
        if ticket and agent and agent.organization_id and ticket.organization_id and agent.organization_id != ticket.organization_id:
            raise serializers.ValidationError("L'agent selectionne appartient a une autre organisation.")
        return attrs
