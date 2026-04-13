from datetime import datetime, timedelta
from time import sleep

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = (
        "Lance un scheduler local AFRILUX pour les alertes SLA, "
        "l'auto-cloture 72h, les rapports planifies et la sauvegarde quotidienne."
    )

    def add_arguments(self, parser):
        parser.add_argument("--interval-seconds", type=int, default=60)
        parser.add_argument("--backup-hour", type=int, default=2)
        parser.add_argument("--backup-minute", type=int, default=0)
        parser.add_argument("--once", action="store_true")
        parser.add_argument("--organization-slug", default="")

    def _run_cycle(self, *, organization_slug, backup_hour, backup_minute, last_backup_date):
        now = timezone.localtime()
        run_kwargs = {}
        if organization_slug:
            run_kwargs["organization_slug"] = organization_slug
        call_command("run_sav_automation", **run_kwargs)

        should_backup = now.hour == backup_hour and now.minute >= backup_minute and last_backup_date != now.date()
        if should_backup:
            call_command("backup_database")
            return now.date()
        return last_backup_date

    def handle(self, *args, **options):
        interval_seconds = max(15, int(options["interval_seconds"]))
        backup_hour = int(options["backup_hour"])
        backup_minute = int(options["backup_minute"])
        organization_slug = options["organization_slug"].strip()
        last_backup_date = None

        if options["once"]:
            self._run_cycle(
                organization_slug=organization_slug,
                backup_hour=backup_hour,
                backup_minute=backup_minute,
                last_backup_date=last_backup_date,
            )
            self.stdout.write(self.style.SUCCESS("Cycle unique execute."))
            return

        self.stdout.write(
            self.style.SUCCESS(
                "Scheduler AFRILUX actif "
                f"(intervalle {interval_seconds}s, backup {backup_hour:02d}:{backup_minute:02d})."
            )
        )
        while True:
            cycle_started_at = timezone.localtime()
            last_backup_date = self._run_cycle(
                organization_slug=organization_slug,
                backup_hour=backup_hour,
                backup_minute=backup_minute,
                last_backup_date=last_backup_date,
            )
            next_run = cycle_started_at + timedelta(seconds=interval_seconds)
            self.stdout.write(
                f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] cycle termine, prochain passage vers {next_run.strftime('%H:%M:%S')}"
            )
            sleep(interval_seconds)
