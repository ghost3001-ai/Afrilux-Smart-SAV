from django.db import models

from .base import TimeStampedModel
from .organizations import Organization
from .users import User
from .tickets import Ticket


class SlaRule(TimeStampedModel):
    organization = models.ForeignKey(
        Organization,
        on_delete=models.SET_NULL,
        related_name="sla_rules",
        null=True,
        blank=True,
    )
    priority = models.CharField(max_length=20, choices=Ticket.PRIORITY_CHOICES)
    response_deadline_minutes = models.PositiveIntegerField(default=120)
    resolution_deadline_hours = models.PositiveIntegerField(default=8)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["priority", "id"]
        unique_together = [("organization", "priority")]

    def __str__(self):
        return f"{self.get_priority_display()} - {self.response_deadline_minutes} min / {self.resolution_deadline_hours} h"


class GeneratedReport(TimeStampedModel):
    TYPE_DAILY = "journalier"
    TYPE_WEEKLY = "hebdomadaire"
    TYPE_MONTHLY = "mensuel"

    TYPE_CHOICES = (
        (TYPE_DAILY, "Journalier"),
        (TYPE_WEEKLY, "Hebdomadaire"),
        (TYPE_MONTHLY, "Mensuel"),
    )

    FORMAT_PDF = "pdf"
    FORMAT_XLSX = "xlsx"
    FORMAT_CSV = "csv"

    FORMAT_CHOICES = (
        (FORMAT_PDF, "PDF"),
        (FORMAT_XLSX, "Tableur XLSX"),
        (FORMAT_CSV, "CSV"),
    )

    organization = models.ForeignKey(
        Organization,
        on_delete=models.SET_NULL,
        related_name="generated_reports",
        null=True,
        blank=True,
    )
    generated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="generated_reports",
        null=True,
        blank=True,
    )
    report_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    export_format = models.CharField(max_length=10, choices=FORMAT_CHOICES, default=FORMAT_PDF)
    period_label = models.CharField(max_length=120)
    payload = models.JSONField(default=dict, blank=True)
    archive_file = models.FileField(upload_to="reports/%Y/%m/%d/", blank=True)
    sent_to = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.report_type} - {self.period_label}"
