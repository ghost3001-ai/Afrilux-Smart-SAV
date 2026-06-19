from django.core.management.base import BaseCommand

from sav.comms import dispatch_pending_notifications


class Command(BaseCommand):
    help = "Envoie les notifications en attente: email, SMS, WhatsApp et notifications internes."

    def add_arguments(self, parser):
        parser.add_argument("--channel", default="", help="Filtre optionnel par canal: email, sms, whatsapp, push, in_app")

    def handle(self, *args, **options):
        channel = options["channel"] or None
        results = dispatch_pending_notifications(channel=channel)
        self.stdout.write(self.style.SUCCESS(f"{len(results)} notification(s) traitee(s)."))
        for result in results:
            self.stdout.write(str(result))
