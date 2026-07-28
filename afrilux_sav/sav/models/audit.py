from django.db import models

from .base import TimeStampedModel
from .organizations import Organization
from .users import User
from .tickets import Ticket
from .equipment import Product


class AIActionLog(models.Model):
    ACTION_TRIAGE = "triage"
    ACTION_DIAGNOSIS = "diagnosis"
    ACTION_AUTO_RESOLUTION = "auto_resolution"
    ACTION_OFFER_GENERATION = "offer_generation"
    ACTION_PREDICTIVE_ANALYSIS = "predictive_analysis"
    ACTION_INSIGHT_SUMMARY = "insight_summary"

    ACTION_CHOICES = (
        (ACTION_TRIAGE, "Qualification"),
        (ACTION_DIAGNOSIS, "Diagnostic"),
        (ACTION_AUTO_RESOLUTION, "Resolution automatique"),
        (ACTION_OFFER_GENERATION, "Generation d'offres"),
        (ACTION_PREDICTIVE_ANALYSIS, "Analyse predictive"),
        (ACTION_INSIGHT_SUMMARY, "Synthese client"),
    )

    STATUS_SUGGESTED = "suggested"
    STATUS_EXECUTED = "executed"
    STATUS_REJECTED = "rejected"
    STATUS_ERROR = "error"

    STATUS_CHOICES = (
        (STATUS_SUGGESTED, "Suggeree"),
        (STATUS_EXECUTED, "Executee"),
        (STATUS_REJECTED, "Rejetee"),
        (STATUS_ERROR, "Erreur"),
    )

    organization = models.ForeignKey(
        Organization,
        on_delete=models.SET_NULL,
        related_name="ai_actions",
        null=True,
        blank=True,
    )
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="ai_actions", null=True, blank=True)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="ai_actions", null=True, blank=True)
    action_type = models.CharField(max_length=30, choices=ACTION_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_SUGGESTED)
    confidence = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    rationale = models.TextField()
    input_snapshot = models.JSONField(default=dict, blank=True)
    output_snapshot = models.JSONField(default=dict, blank=True)
    approved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="approved_ai_actions",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.action_type} - {self.status}"

    def save(self, *args, **kwargs):
        if self.ticket_id and self.ticket.organization_id:
            self.organization = self.ticket.organization
        elif self.product_id and self.product.organization_id:
            self.organization = self.product.organization
        super().save(*args, **kwargs)


class AuditLog(models.Model):
    ACTOR_HUMAN = "human"
    ACTOR_AI = "ai"
    ACTOR_SYSTEM = "system"

    ACTOR_CHOICES = (
        (ACTOR_HUMAN, "Humain"),
        (ACTOR_AI, "IA"),
        (ACTOR_SYSTEM, "Systeme"),
    )

    organization = models.ForeignKey(
        Organization,
        on_delete=models.SET_NULL,
        related_name="audit_logs",
        null=True,
        blank=True,
    )
    actor = models.ForeignKey(User, on_delete=models.SET_NULL, related_name="audit_logs", null=True, blank=True)
    actor_type = models.CharField(max_length=20, choices=ACTOR_CHOICES, default=ACTOR_HUMAN)
    action = models.CharField(max_length=100)
    target_model = models.CharField(max_length=100)
    target_id = models.PositiveIntegerField(null=True, blank=True)
    target_reference = models.CharField(max_length=255, blank=True)
    source_ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=255, blank=True)
    request_path = models.CharField(max_length=255, blank=True)
    http_method = models.CharField(max_length=10, blank=True)
    details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.actor_type} - {self.action}"


class EscalationHistory(TimeStampedModel):
    """
    Historique complet de chaque escalade d'un ticket.
    Traçabilité : qui a escaladé, quand, pourquoi, et quelle action a été prise.
    """

    ACTION_ESCALATED = "escalated"
    ACTION_REASSIGNED = "reassigned"
    ACTION_SOLUTION_PROVIDED = "solution_provided"
    ACTION_DECLINED = "declined"
    ACTION_CONTINUED = "continued"

    ACTION_CHOICES = (
        (ACTION_ESCALATED, "Escaladee"),
        (ACTION_REASSIGNED, "Reassignee a un autre technicien"),
        (ACTION_SOLUTION_PROVIDED, "Solution fournie"),
        (ACTION_DECLINED, "Declinee par le responsable"),
        (ACTION_CONTINUED, "Continuee apres solution"),
    )

    ticket = models.ForeignKey(
        Ticket,
        on_delete=models.CASCADE,
        related_name="escalation_history",
    )
    action = models.CharField(
        max_length=30,
        choices=ACTION_CHOICES,
        help_text="Action prise par le responsable",
    )
    reason = models.TextField(
        blank=True,
        help_text="Motif de l'escalade ou de l'action",
    )
    escalated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="escalations_initiated",
        help_text="Qui a escaladé le ticket (technicien ou chef d'équipe)",
    )
    handled_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="escalations_handled",
        help_text="Qui a traité l'escalade (responsable SAV ou admin)",
    )
    reassigned_to = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="escalation_reassignments_received",
        help_text="Nouveau technicien assigné (si action=reassigned)",
    )
    solution_text = models.TextField(
        blank=True,
        help_text="Texte de la solution proposée (si action=solution_provided)",
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Historique d'escalade"
        verbose_name_plural = "Historiques d'escalade"

    def __str__(self):
        return f"{self.ticket.reference} - {self.get_action_display()}"
