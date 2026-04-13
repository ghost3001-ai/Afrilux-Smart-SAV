from datetime import datetime

from django.core.management.base import BaseCommand
from django.utils import timezone

from sav.models import Organization
from sav.services import auto_close_resolved_tickets, dispatch_due_reports, dispatch_sla_operational_notifications


class Command(BaseCommand):
    help = "Execute les automatismes SAV obligatoires: alertes SLA, auto-cloture 72h et rapports planifies."

    def add_arguments(self, parser):
        parser.add_argument("--organization-slug", default="")
        parser.add_argument("--date-time", default="")
        parser.add_argument("--skip-reports", action="store_true")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        now = timezone.localtime()
        if options["date_time"]:
            now = timezone.make_aware(datetime.fromisoformat(options["date_time"]))

        organizations = Organization.objects.filter(is_active=True).order_by("name")
        if options["organization_slug"]:
            organizations = organizations.filter(slug=options["organization_slug"].strip())

        for organization in organizations:
            sla_results = dispatch_sla_operational_notifications(organization=organization, now=now)
            self.stdout.write(
                f"{organization.display_name}: alertes SLA "
                f"{sla_results['unassigned_30m']}/{sla_results['new_1h']}/{sla_results['sla_due_soon']}/{sla_results['sla_overdue']}"
            )

            closed = []
            if not options["dry_run"]:
                closed = auto_close_resolved_tickets(organization=organization, now=now)
            self.stdout.write(f"{organization.display_name}: auto-clotures 72h -> {len(closed)}")

            if options["skip_reports"]:
                continue
            report_results = dispatch_due_reports(organization=organization, now=now, dry_run=options["dry_run"])
            if not report_results:
                self.stdout.write(f"{organization.display_name}: aucun rapport du a cette heure.")
                continue
            for item in report_results:
                self.stdout.write(
                    f"{organization.display_name}: rapport {item.get('report_type', '-')}"
                    f" -> {item.get('status', 'unknown')}"
                )
