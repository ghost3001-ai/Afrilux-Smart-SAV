from django.core.management.base import BaseCommand
from django.db.models import Q

from sav.models import Organization, Ticket, User


DEMO_ORGANIZATION_SLUGS = ["afrilux-habitat", "solaris-industries"]
PLACEHOLDER_ORGANIZATION_SLUG_PREFIXES = ["tmp-org", "client-demo"]
PLACEHOLDER_ORGANIZATION_NAMES = ["Client Demo"]
PLACEHOLDER_ORGANIZATION_NAME_PREFIXES = ["Tmp Org"]
DEMO_USERNAMES = [
    "sav_manager",
    "sav_head",
    "sav_support",
    "sav_technician",
    "sav_auditor",
    "sav_agent",
    "client_demo",
    "sav_manager_solaris",
    "sav_head_solaris",
    "sav_support_solaris",
    "sav_technician_solaris",
    "sav_auditor_solaris",
    "sav_agent_solaris",
    "client_solaris",
]
PLACEHOLDER_USERNAME_PREFIXES = ["tmp_"]


def _placeholder_organization_queryset():
    query = Q(slug__in=DEMO_ORGANIZATION_SLUGS)
    for prefix in PLACEHOLDER_ORGANIZATION_SLUG_PREFIXES:
        query |= Q(slug__startswith=prefix)
    for name in PLACEHOLDER_ORGANIZATION_NAMES:
        query |= Q(name__iexact=name)
    for prefix in PLACEHOLDER_ORGANIZATION_NAME_PREFIXES:
        query |= Q(name__istartswith=prefix)
    return Organization.objects.filter(query).distinct()


def _placeholder_user_queryset(demo_orgs):
    query = Q(username__in=DEMO_USERNAMES) | Q(organization__in=demo_orgs)
    for prefix in PLACEHOLDER_USERNAME_PREFIXES:
        query |= Q(username__startswith=prefix)
    return User.objects.filter(query).distinct()


class Command(BaseCommand):
    help = (
        "Supprime les donnees de demonstration connues et les jeux temporaires "
        "de type Client Demo / Tmp Org / tmp_*. "
    )

    def add_arguments(self, parser):
        parser.add_argument("--execute", action="store_true")

    def handle(self, *args, **options):
        demo_orgs = _placeholder_organization_queryset()
        demo_users = _placeholder_user_queryset(demo_orgs)
        demo_tickets = Ticket.objects.filter(
            Q(reference__startswith="SAV-DEMO-")
            | Q(organization__in=demo_orgs)
            | Q(client__in=demo_users)
            | Q(assigned_agent__in=demo_users)
        ).distinct()

        self.stdout.write(
            f"Organisations demo: {demo_orgs.count()} | Utilisateurs demo: {demo_users.count()} | Tickets demo: {demo_tickets.count()}"
        )
        if demo_orgs.exists():
            self.stdout.write(
                "Organisations ciblees: "
                + ", ".join(demo_orgs.order_by("slug").values_list("slug", flat=True)[:20])
            )
        if demo_users.exists():
            self.stdout.write(
                "Utilisateurs cibles: "
                + ", ".join(demo_users.order_by("username").values_list("username", flat=True)[:20])
            )
        if not options["execute"]:
            self.stdout.write("Relancez avec --execute pour supprimer ces donnees.")
            return

        demo_ticket_ids = list(demo_tickets.values_list("pk", flat=True))
        demo_user_ids = list(demo_users.values_list("pk", flat=True))
        demo_org_ids = list(demo_orgs.values_list("pk", flat=True))
        deleted_tickets = len(demo_ticket_ids)
        deleted_users = len(demo_user_ids)
        deleted_orgs = len(demo_org_ids)
        if demo_ticket_ids:
            Ticket.objects.filter(pk__in=demo_ticket_ids).delete()
        if demo_user_ids:
            User.objects.filter(pk__in=demo_user_ids).delete()
        if demo_org_ids:
            Organization.objects.filter(pk__in=demo_org_ids).delete()
        self.stdout.write(
            self.style.SUCCESS(
                f"Nettoyage termine. Tickets: {deleted_tickets}, utilisateurs: {deleted_users}, organisations: {deleted_orgs}"
            )
        )
