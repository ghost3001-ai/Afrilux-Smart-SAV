from django.db import models
from django.utils import timezone

from .base import TimeStampedModel
from .organizations import Organization
from .users import User
from .tickets import Ticket


class Notification(models.Model):
    CHANNEL_EMAIL = "email"
    CHANNEL_SMS = "sms"
    CHANNEL_WHATSAPP = "whatsapp"
    CHANNEL_PUSH = "push"
    CHANNEL_IN_APP = "in_app"

    CHANNEL_CHOICES = (
        (CHANNEL_EMAIL, "Email"),
        (CHANNEL_SMS, "SMS"),
        (CHANNEL_WHATSAPP, "WhatsApp"),
        (CHANNEL_PUSH, "Notification mobile"),
        (CHANNEL_IN_APP, "Dans l'application"),
    )

    STATUS_PENDING = "pending"
    STATUS_SENT = "sent"
    STATUS_READ = "read"
    STATUS_CLICKED = "clicked"
    STATUS_FAILED = "failed"

    STATUS_CHOICES = (
        (STATUS_PENDING, "En attente"),
        (STATUS_SENT, "Envoyee"),
        (STATUS_READ, "Lue"),
        (STATUS_CLICKED, "Cliquee"),
        (STATUS_FAILED, "Echouee"),
    )

    organization = models.ForeignKey(
        Organization,
        on_delete=models.SET_NULL,
        related_name="notifications",
        null=True,
        blank=True,
    )
    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name="notifications")
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="notifications", null=True, blank=True)
    channel = models.CharField(max_length=20, choices=CHANNEL_CHOICES, default=CHANNEL_IN_APP)
    event_type = models.CharField(max_length=100)
    subject = models.CharField(max_length=255)
    message = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    provider = models.CharField(max_length=80, blank=True)
    provider_reference = models.CharField(max_length=255, blank=True)
    recipient_contact = models.CharField(max_length=255, blank=True)
    deep_link = models.URLField(max_length=500, blank=True)
    action_payload = models.JSONField(default=dict, blank=True)
    delivery_payload = models.JSONField(default=dict, blank=True)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)
    clicked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["recipient", "status"], name="sav_notif_recipient_status_idx"),
            models.Index(fields=["organization", "status"], name="sav_notif_org_status_idx"),
            models.Index(fields=["channel", "status"], name="sav_notif_channel_status_idx"),
            models.Index(fields=["event_type", "created_at"], name="sav_notif_event_created_idx"),
        ]

    def __str__(self):
        return f"{self.recipient} - {self.subject}"

    def save(self, *args, **kwargs):
        if self.ticket_id and self.ticket.organization_id:
            self.organization = self.ticket.organization
        elif self.recipient_id and self.recipient.organization_id:
            self.organization = self.recipient.organization
        super().save(*args, **kwargs)


class DeviceRegistration(TimeStampedModel):
    PLATFORM_ANDROID = "android"
    PLATFORM_IOS = "ios"
    PLATFORM_WEB = "web"
    PLATFORM_DESKTOP = "desktop"

    PLATFORM_CHOICES = (
        (PLATFORM_ANDROID, "Android"),
        (PLATFORM_IOS, "iOS"),
        (PLATFORM_WEB, "Web"),
        (PLATFORM_DESKTOP, "Desktop"),
    )

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="device_registrations")
    token = models.CharField(max_length=512, unique=True)
    platform = models.CharField(max_length=20, choices=PLATFORM_CHOICES)
    device_id = models.CharField(max_length=255, blank=True)
    app_version = models.CharField(max_length=50, blank=True)
    is_active = models.BooleanField(default=True)
    last_seen_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-last_seen_at", "-updated_at"]

    def __str__(self):
        return f"{self.user} - {self.platform}"
