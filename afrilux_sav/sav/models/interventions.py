from decimal import Decimal

from django.db import models

from .base import TimeStampedModel
from .equipment import SparePart
from .organizations import Organization
from .tickets import Ticket
from .users import User


class Intervention(models.Model):
    TYPE_REMOTE = "remote"
    TYPE_ON_SITE = "on_site"
    TYPE_WORKSHOP = "workshop"

    TYPE_CHOICES = (
        (TYPE_REMOTE, "A distance"),
        (TYPE_ON_SITE, "Sur site"),
        (TYPE_WORKSHOP, "Atelier"),
    )

    STATUS_PLANNED = "planned"
    STATUS_IN_PROGRESS = "in_progress"
    STATUS_DONE = "done"
    STATUS_CANCELLED = "cancelled"

    STATUS_CHOICES = (
        (STATUS_PLANNED, "Planifiee"),
        (STATUS_IN_PROGRESS, "En cours"),
        (STATUS_DONE, "Terminee"),
        (STATUS_CANCELLED, "Annulee"),
    )

    organization = models.ForeignKey(
        Organization,
        on_delete=models.SET_NULL,
        related_name="interventions",
        null=True,
        blank=True,
    )
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="interventions")
    agent = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="interventions",
        limit_choices_to={"role__in": User.ASSIGNABLE_ROLES},
    )
    intervention_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default=TYPE_REMOTE)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PLANNED)
    client_validation_requested_at = models.DateTimeField(null=True, blank=True)
    client_validated_start_at = models.DateTimeField(null=True, blank=True)
    client_validation_requested_at_finish = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp quand le technicien a demandé la validation de fin d'intervention",
    )
    client_validated_finish_at = models.DateTimeField(null=True, blank=True)
    client_validation_impossible = models.BooleanField(default=False)
    validation_impossible_reason = models.CharField(max_length=255, blank=True)
    validation_impossible_photo = models.FileField(upload_to="interventions/bypass/%Y/%m/%d/", blank=True)
    scheduled_for = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    diagnosis = models.TextField(blank=True)
    action_taken = models.CharField(max_length=255)
    parts_used = models.TextField(blank=True)
    structured_parts_used = models.JSONField(default=list, blank=True)
    time_spent_minutes = models.PositiveIntegerField(default=0)
    technical_report = models.TextField(blank=True)
    location_snapshot = models.CharField(max_length=255, blank=True)
    client_signed_by = models.CharField(max_length=255, blank=True)
    client_signed_at = models.DateTimeField(null=True, blank=True)
    client_signature_file = models.FileField(upload_to="interventions/signatures/%Y/%m/%d/", blank=True)
    report_pdf = models.FileField(upload_to="interventions/reports/%Y/%m/%d/", blank=True)
    report_generated_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["organization", "agent", "scheduled_for"], name="sav_interv_org_agent_sched_idx"),
            models.Index(fields=["ticket", "created_at"], name="sav_interv_ticket_created_idx"),
            models.Index(fields=["status", "scheduled_for"], name="sav_interv_status_sched_idx"),
        ]

    def __str__(self):
        return f"{self.ticket.reference} - {self.action_taken}"

    def save(self, *args, **kwargs):
        if self.ticket_id and self.ticket.organization_id:
            self.organization = self.ticket.organization
        if self.ticket_id and not self.location_snapshot:
            self.location_snapshot = self.ticket.location
        super().save(*args, **kwargs)


class InterventionPartUsage(TimeStampedModel):
    organization = models.ForeignKey(
        Organization,
        on_delete=models.SET_NULL,
        related_name="intervention_part_usages",
        null=True,
        blank=True,
    )
    intervention = models.ForeignKey(Intervention, on_delete=models.CASCADE, related_name="part_usages")
    spare_part = models.ForeignKey(SparePart, on_delete=models.SET_NULL, related_name="intervention_usages", null=True, blank=True)
    name_snapshot = models.CharField(max_length=180, blank=True)
    reference_snapshot = models.CharField(max_length=120, blank=True)
    category_snapshot = models.CharField(max_length=120, blank=True)
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("1.00"))
    unit_snapshot = models.CharField(max_length=40, blank=True)
    note = models.TextField(blank=True)

    class Meta:
        ordering = ["created_at", "id"]

    def __str__(self):
        return f"{self.intervention.ticket.reference} - {self.reference_snapshot or self.name_snapshot}"

    def save(self, *args, **kwargs):
        if self.intervention_id and self.intervention.organization_id:
            self.organization = self.intervention.organization
        if self.spare_part_id:
            if not self.name_snapshot:
                self.name_snapshot = self.spare_part.name
            if not self.reference_snapshot:
                self.reference_snapshot = self.spare_part.reference
            if not self.category_snapshot:
                self.category_snapshot = self.spare_part.category
            if not self.unit_snapshot:
                self.unit_snapshot = self.spare_part.unit
            if self.spare_part.organization_id and not self.organization_id:
                self.organization = self.spare_part.organization
        super().save(*args, **kwargs)


class InterventionMedia(TimeStampedModel):
    KIND_BEFORE = "before"
    KIND_DURING = "during"
    KIND_AFTER = "after"
    KIND_OTHER = "other"

    KIND_CHOICES = (
        (KIND_BEFORE, "Avant intervention"),
        (KIND_DURING, "Pendant intervention"),
        (KIND_AFTER, "Apres intervention"),
        (KIND_OTHER, "Autre"),
    )

    organization = models.ForeignKey(
        Organization,
        on_delete=models.SET_NULL,
        related_name="intervention_media",
        null=True,
        blank=True,
    )
    intervention = models.ForeignKey(Intervention, on_delete=models.CASCADE, related_name="media")
    uploaded_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="intervention_media",
        null=True,
        blank=True,
    )
    kind = models.CharField(max_length=20, choices=KIND_CHOICES, default=KIND_OTHER)
    file = models.FileField(upload_to="interventions/media/%Y/%m/%d/")
    note = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["created_at", "id"]

    def __str__(self):
        return f"{self.intervention.ticket.reference} - {self.get_kind_display()}"

    def save(self, *args, **kwargs):
        if self.intervention_id and self.intervention.organization_id:
            self.organization = self.intervention.organization
        elif self.uploaded_by_id and self.uploaded_by.organization_id:
            self.organization = self.uploaded_by.organization
        super().save(*args, **kwargs)
