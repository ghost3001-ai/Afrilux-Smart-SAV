from django.db import models
from django.utils import timezone

from .base import _generate_unique_slug, TimeStampedModel
from .organizations import Organization
from .equipment import EquipmentCategory
from .tickets import Ticket


class ProductTelemetry(models.Model):
    SOURCE_IOT = "iot"
    SOURCE_MANUAL = "manual"
    SOURCE_IMPORT = "import"

    SOURCE_CHOICES = (
        (SOURCE_IOT, "Capteur IoT"),
        (SOURCE_MANUAL, "Saisie manuelle"),
        (SOURCE_IMPORT, "Import"),
    )

    product = models.ForeignKey("Product", on_delete=models.CASCADE, related_name="telemetry")
    metric_name = models.CharField(max_length=100)
    value = models.DecimalField(max_digits=10, decimal_places=2)
    unit = models.CharField(max_length=20, blank=True)
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default=SOURCE_IOT)
    captured_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-captured_at"]

    def __str__(self):
        return f"{self.product.serial_number} - {self.metric_name}={self.value}"


class PredictiveAlert(TimeStampedModel):
    TYPE_ANOMALY = "anomaly"
    TYPE_MAINTENANCE = "maintenance"
    TYPE_WARRANTY = "warranty"
    TYPE_REPEAT_FAILURE = "repeat_failure"

    TYPE_CHOICES = (
        (TYPE_ANOMALY, "Anomalie"),
        (TYPE_MAINTENANCE, "Maintenance"),
        (TYPE_WARRANTY, "Fin de garantie"),
        (TYPE_REPEAT_FAILURE, "Panne recurrente"),
    )

    SEVERITY_LOW = "low"
    SEVERITY_MEDIUM = "medium"
    SEVERITY_HIGH = "high"
    SEVERITY_CRITICAL = "critical"

    SEVERITY_CHOICES = (
        (SEVERITY_LOW, "Faible"),
        (SEVERITY_MEDIUM, "Moyenne"),
        (SEVERITY_HIGH, "Haute"),
        (SEVERITY_CRITICAL, "Critique"),
    )

    STATUS_OPEN = "open"
    STATUS_IN_PROGRESS = "in_progress"
    STATUS_RESOLVED = "resolved"
    STATUS_DISMISSED = "dismissed"

    STATUS_CHOICES = (
        (STATUS_OPEN, "Ouverte"),
        (STATUS_IN_PROGRESS, "En traitement"),
        (STATUS_RESOLVED, "Resolue"),
        (STATUS_DISMISSED, "Ignoree"),
    )

    product = models.ForeignKey("Product", on_delete=models.CASCADE, related_name="predictive_alerts")
    ticket = models.ForeignKey(
        Ticket,
        on_delete=models.SET_NULL,
        related_name="predictive_alerts",
        null=True,
        blank=True,
    )
    alert_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default=TYPE_ANOMALY)
    severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES, default=SEVERITY_MEDIUM)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_OPEN)
    title = models.CharField(max_length=255)
    description = models.TextField()
    metric_name = models.CharField(max_length=100, blank=True)
    metric_value = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    predicted_failure_at = models.DateTimeField(null=True, blank=True)
    recommended_action = models.TextField(blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "severity"], name="sav_alert_status_severity_idx"),
            models.Index(fields=["product", "status"], name="sav_alert_product_status_idx"),
        ]

    def __str__(self):
        return f"{self.product.serial_number} - {self.title}"


class KnowledgeArticle(TimeStampedModel):
    STATUS_DRAFT = "draft"
    STATUS_PUBLISHED = "published"

    STATUS_CHOICES = (
        (STATUS_DRAFT, "Brouillon"),
        (STATUS_PUBLISHED, "Publie"),
    )

    AUDIENCE_PUBLIC = "public"
    AUDIENCE_INTERNAL = "internal"

    AUDIENCE_CHOICES = (
        (AUDIENCE_PUBLIC, "Clients"),
        (AUDIENCE_INTERNAL, "Interne"),
    )

    organization = models.ForeignKey(
        Organization,
        on_delete=models.SET_NULL,
        related_name="knowledge_articles",
        null=True,
        blank=True,
    )
    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True, blank=True)
    category = models.CharField(max_length=100, blank=True)
    equipment_category = models.ForeignKey(
        EquipmentCategory,
        on_delete=models.SET_NULL,
        related_name="knowledge_articles",
        null=True,
        blank=True,
    )
    business_domain = models.CharField(max_length=20, choices=Ticket.BUSINESS_DOMAIN_CHOICES, default=Ticket.DOMAIN_OTHER)
    product = models.ForeignKey("Product", on_delete=models.SET_NULL, related_name="knowledge_articles", null=True, blank=True)
    summary = models.TextField(blank=True)
    content = models.TextField()
    keywords = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    audience = models.CharField(max_length=20, choices=AUDIENCE_CHOICES, default=AUDIENCE_PUBLIC)
    helpful_votes = models.PositiveIntegerField(default=0)
    unhelpful_votes = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["title"]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if self.product_id and self.product.organization_id:
            self.organization = self.product.organization
        elif self.equipment_category_id and self.equipment_category.organization_id:
            self.organization = self.equipment_category.organization
        if not self.slug:
            self.slug = _generate_unique_slug(self.__class__, self.title, self.pk)
        super().save(*args, **kwargs)
