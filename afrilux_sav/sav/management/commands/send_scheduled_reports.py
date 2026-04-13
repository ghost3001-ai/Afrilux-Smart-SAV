from datetime import datetime

from django.core.management.base import BaseCommand
from django.utils import timezone

from sav.models import Organization
from sav.reporting import REPORT_DAILY, REPORT_MONTHLY, REPORT_WEEKLY
from sav.services import dispatch_due_reports


class Command(BaseCommand):
    help = "Envoie les rapports SAV planifies par email."

    def add_arguments(self, parser):
        parser.add_argument("--report-type", choices=[REPORT_DAILY, REPORT_WEEKLY, REPORT_MONTHLY, "all"], default="all")
        parser.add_argument("--date", default="")
        parser.add_argument("--organization-slug", default="")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        anchor_date = timezone.localdate()
        if options["date"]:
            anchor_date = datetime.fromisoformat(options["date"]).date()
        execution_time = timezone.make_aware(datetime.combine(anchor_date, datetime.min.time())).replace(hour=8)
        if options["report_type"] == REPORT_DAILY:
            execution_time = execution_time.replace(hour=7)
        forced_report_types = None if options["report_type"] == "all" else [options["report_type"]]

        orgs = Organization.objects.filter(is_active=True).order_by("name")
        if options["organization_slug"]:
            orgs = orgs.filter(slug=options["organization_slug"].strip())

        for organization in orgs:
            results = dispatch_due_reports(
                organization=organization,
                now=execution_time,
                dry_run=options["dry_run"],
                report_types=forced_report_types,
            )
            if not results:
                self.stdout.write(self.style.WARNING(f"{organization.display_name}: aucun rapport a envoyer sur cette fenetre."))
                continue
            for item in results:
                status_label = item.get("status", "unknown")
                report_type = item.get("report_type", options["report_type"])
                if status_label == "sent":
                    self.stdout.write(self.style.SUCCESS(f"{organization.display_name}: rapport {report_type} envoye."))
                elif status_label == "dry_run":
                    self.stdout.write(f"[DRY RUN] {organization.display_name}: rapport {report_type} pret.")
                else:
                    self.stdout.write(self.style.WARNING(f"{organization.display_name}: rapport {report_type} -> {status_label}"))
