from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("sav", "0020_align_cdc_roles_and_ticket_workflow"),
    ]

    operations = [
        migrations.AlterField(
            model_name="user",
            name="role",
            field=models.CharField(
                choices=[
                    ("admin", "Administrateur"),
                    ("head_sav", "Responsable SAV"),
                    ("cfao_manager", "Responsable CFAO / Responsable de Projet Technique CFAO"),
                    ("cfao_works", "Conducteur de travaux CFAO"),
                    ("hvac_manager", "Responsable Froid et climatisation / Responsable technique froid"),
                    ("chief_technician", "Chef Technicien Froid & Climatisation"),
                    ("technician", "Technicien de maintenance"),
                    ("client", "Client"),
                    ("auditor", "Auditeur / Direction"),
                ],
                default="client",
                max_length=20,
            ),
        ),
    ]
