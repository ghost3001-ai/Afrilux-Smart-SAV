from django.core.management.base import BaseCommand

from sav.comms import dispatch_pending_notifications


class Command(BaseCommand):
    help = "Dispatch pending email, SMS, WhatsApp, and in-app notifications."

    def add_arguments(self, parser):
        parser.add_argument("--channel", default="", help="Optional channel filter: email, sms, whatsapp, push, in_app")

    def handle(self, *args, **options):
        channel = options["channel"] or None
        results = dispatch_pending_notifications(channel=channel)
        self.stdout.write(self.style.SUCCESS(f"Processed {len(results)} notification(s)."))
        for result in results:
            self.stdout.write(str(result))
