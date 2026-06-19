# Generated on 2026-06-16

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sav", "0031_alter_maintenanceticket_initial_scheduled_date_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="intervention",
            name="client_validation_requested_at_finish",
            field=models.DateTimeField(
                blank=True,
                null=True,
                help_text="Timestamp quand le technicien a demandé la validation de fin d'intervention",
            ),
        ),
    ]
