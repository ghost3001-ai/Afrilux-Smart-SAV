from rest_framework import serializers

from ..models import DeviceRegistration, Notification


class NotificationSerializer(serializers.ModelSerializer):
    recipient_name = serializers.SerializerMethodField()
    ticket_reference = serializers.CharField(source="ticket.reference", read_only=True)
    organization_name = serializers.CharField(source="organization.display_name", read_only=True)

    class Meta:
        model = Notification
        fields = [
            "id",
            "organization",
            "organization_name",
            "recipient",
            "recipient_name",
            "ticket",
            "ticket_reference",
            "channel",
            "event_type",
            "subject",
            "message",
            "status",
            "created_at",
            "sent_at",
            "read_at",
        ]

    def get_recipient_name(self, obj):
        return str(obj.recipient)


class DeviceRegistrationSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeviceRegistration
        fields = [
            "id",
            "user",
            "token",
            "platform",
            "device_id",
            "app_version",
            "is_active",
            "last_seen_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "user",
            "is_active",
            "last_seen_at",
            "created_at",
            "updated_at",
        ]
