# Generated on 2026-06-16

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("sav", "0032_intervention_add_finish_validation_tracking"),
    ]

    operations = [
        # EscalationHistory model
        migrations.CreateModel(
            name="EscalationHistory",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "action",
                    models.CharField(
                        choices=[
                            ("escalated", "Escaladée"),
                            ("reassigned", "Réassignée à un autre technicien"),
                            ("solution_provided", "Solution fournie"),
                            ("declined", "Déclinée par le responsable"),
                            ("continued", "Continuée après solution"),
                        ],
                        help_text="Action prise par le responsable",
                        max_length=30,
                    ),
                ),
                (
                    "reason",
                    models.TextField(
                        blank=True,
                        help_text="Motif de l'escalade ou de l'action",
                    ),
                ),
                (
                    "solution_text",
                    models.TextField(
                        blank=True,
                        help_text="Texte de la solution proposée (si action=solution_provided)",
                    ),
                ),
                (
                    "escalated_by",
                    models.ForeignKey(
                        blank=True,
                        help_text="Qui a escaladé le ticket (technicien ou chef d'équipe)",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="escalations_initiated",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "handled_by",
                    models.ForeignKey(
                        blank=True,
                        help_text="Qui a traité l'escalade (responsable SAV ou admin)",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="escalations_handled",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "reassigned_to",
                    models.ForeignKey(
                        blank=True,
                        help_text="Nouveau technicien assigné (si action=reassigned)",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="escalation_reassignments_received",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "ticket",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="escalation_history",
                        to="sav.ticket",
                    ),
                ),
            ],
            options={
                "verbose_name_plural": "Escalation Histories",
                "ordering": ["-created_at"],
            },
        ),
    ]

