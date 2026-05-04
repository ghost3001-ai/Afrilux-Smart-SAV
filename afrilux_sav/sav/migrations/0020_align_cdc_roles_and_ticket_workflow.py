from django.db import migrations, models


ROLE_MAP = {
    "agent": "head_sav",
    "support": "head_sav",
    "manager": "head_sav",
    "field_technician": "technician",
    "expert": "chief_technician",
    "software_owner": "head_sav",
    "supervisor": "head_sav",
    "dispatcher": "head_sav",
    "vip_support": "head_sav",
    "qa": "auditor",
    "system_bot": "head_sav",
}


STATUS_MAP = {
    "qualification": "new",
    "pending_customer": "waiting",
    "in_progress_n1": "in_progress",
    "in_progress_n2": "in_progress",
    "expertise": "in_progress",
    "intervention_planned": "assigned",
    "intervention_done": "resolved",
    "qa_control": "resolved",
    "pending_client_confirmation": "resolved",
}


def align_roles_and_workflow(apps, schema_editor):
    User = apps.get_model("sav", "User")
    Ticket = apps.get_model("sav", "Ticket")

    for old_role, new_role in ROLE_MAP.items():
        User.objects.filter(role=old_role).update(role=new_role)

    for old_status, new_status in STATUS_MAP.items():
        Ticket.objects.filter(status=old_status).update(status=new_status)


class Migration(migrations.Migration):
    dependencies = [
        ("sav", "0019_harden_roles_products_and_knowledge"),
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
        migrations.AlterField(
            model_name="ticket",
            name="status",
            field=models.CharField(
                choices=[
                    ("new", "Nouveau"),
                    ("assigned", "Assigne"),
                    ("in_progress", "En cours"),
                    ("waiting", "En attente"),
                    ("resolved", "Resolue"),
                    ("closed", "Ferme"),
                    ("cancelled", "Annule"),
                ],
                default="new",
                max_length=32,
            ),
        ),
        migrations.RunPython(align_roles_and_workflow, migrations.RunPython.noop),
    ]
