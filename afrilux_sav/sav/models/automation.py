import uuid

from django.db import models
from django.utils import timezone

from .base import TimeStampedModel
from .organizations import Organization
from .users import User
from .tickets import Ticket
from .notifications import DeviceRegistration


class OfflineSyncOperation(TimeStampedModel):
    STATUS_PENDING = "pending"
    STATUS_APPLIED = "applied"
    STATUS_FAILED = "failed"

    STATUS_CHOICES = (
        (STATUS_PENDING, "En attente"),
        (STATUS_APPLIED, "Synchronisee"),
        (STATUS_FAILED, "Echec"),
    )

    METHOD_POST = "POST"
    METHOD_PUT = "PUT"
    METHOD_PATCH = "PATCH"
    METHOD_DELETE = "DELETE"

    METHOD_CHOICES = (
        (METHOD_POST, "POST"),
        (METHOD_PUT, "PUT"),
        (METHOD_PATCH, "PATCH"),
        (METHOD_DELETE, "DELETE"),
    )

    organization = models.ForeignKey(
        Organization,
        on_delete=models.SET_NULL,
        related_name="offline_sync_operations",
        null=True,
        blank=True,
    )
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="offline_sync_operations")
    device = models.ForeignKey(
        DeviceRegistration,
        on_delete=models.SET_NULL,
        related_name="offline_sync_operations",
        null=True,
        blank=True,
    )
    operation_uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    endpoint = models.CharField(max_length=255)
    method = models.CharField(max_length=10, choices=METHOD_CHOICES, default=METHOD_POST)
    payload = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    error_message = models.TextField(blank=True)
    client_created_at = models.DateTimeField(null=True, blank=True)
    applied_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["status", "created_at"]

    def __str__(self):
        return f"{self.user} - {self.method} {self.endpoint} ({self.status})"

    def save(self, *args, **kwargs):
        if self.user_id and self.user.organization_id:
            self.organization = self.user.organization
        elif self.device_id and self.device.user.organization_id:
            self.organization = self.device.user.organization
        if self.status == self.STATUS_APPLIED and not self.applied_at:
            self.applied_at = timezone.now()
        super().save(*args, **kwargs)


class AutomationRule(TimeStampedModel):
    TRIGGER_TICKET_CREATED = "ticket_created"
    TRIGGER_TICKET_UPDATED = "ticket_updated"
    TRIGGER_TICKET_OVERDUE = "ticket_overdue"
    TRIGGER_PREDICTIVE_ALERT = "predictive_alert_created"
    TRIGGER_MANUAL = "manual_run"

    TRIGGER_CHOICES = (
        (TRIGGER_TICKET_CREATED, "Ticket cree"),
        (TRIGGER_TICKET_UPDATED, "Ticket mis a jour"),
        (TRIGGER_TICKET_OVERDUE, "Ticket en retard"),
        (TRIGGER_PREDICTIVE_ALERT, "Alerte predictive"),
        (TRIGGER_MANUAL, "Execution manuelle"),
    )

    organization = models.ForeignKey(
        Organization,
        on_delete=models.SET_NULL,
        related_name="automation_rules",
        null=True,
        blank=True,
    )
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    trigger_event = models.CharField(max_length=30, choices=TRIGGER_CHOICES, default=TRIGGER_MANUAL)
    is_active = models.BooleanField(default=True)
    priority = models.PositiveIntegerField(default=100)
    conditions = models.JSONField(default=dict, blank=True)
    actions = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ["priority", "name"]

    def __str__(self):
        return self.name


class WorkflowExecution(models.Model):
    STATUS_SUCCESS = "success"
    STATUS_FAILED = "failed"
    STATUS_SKIPPED = "skipped"

    STATUS_CHOICES = (
        (STATUS_SUCCESS, "Succes"),
        (STATUS_FAILED, "Echec"),
        (STATUS_SKIPPED, "Ignore"),
    )

    organization = models.ForeignKey(
        Organization,
        on_delete=models.SET_NULL,
        related_name="workflow_executions",
        null=True,
        blank=True,
    )
    rule = models.ForeignKey(AutomationRule, on_delete=models.SET_NULL, related_name="executions", null=True, blank=True)
    ticket = models.ForeignKey(Ticket, on_delete=models.SET_NULL, related_name="workflow_executions", null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_SUCCESS)
    trigger_event = models.CharField(max_length=50)
    result = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.trigger_event} - {self.status}"

    def save(self, *args, **kwargs):
        if self.ticket_id and self.ticket.organization_id:
            self.organization = self.ticket.organization
        elif self.rule_id and self.rule.organization_id:
            self.organization = self.rule.organization
        super().save(*args, **kwargs)
