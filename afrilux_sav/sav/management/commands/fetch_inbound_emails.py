import imaplib

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from ...comms import handle_email_inbound, parse_inbound_email_message


class Command(BaseCommand):
    help = "Recupere les emails entrants depuis une boite IMAP et les transforme en tickets SAV."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=20, help="Nombre maximum d'emails a traiter.")
        parser.add_argument("--search", default="", help="Recherche IMAP a utiliser. Par defaut: INBOUND_EMAIL_IMAP_SEARCH.")
        parser.add_argument("--mailbox", default="", help="Boite IMAP a ouvrir. Par defaut: INBOUND_EMAIL_IMAP_MAILBOX.")
        parser.add_argument(
            "--mark-seen",
            action="store_true",
            default=False,
            help="Marque explicitement les emails traites comme lus.",
        )

    def handle(self, *args, **options):
        if not settings.INBOUND_EMAIL_IMAP_HOST or not settings.INBOUND_EMAIL_IMAP_USER:
            raise CommandError("La boite IMAP entrante n'est pas configuree.")

        search_query = options["search"] or settings.INBOUND_EMAIL_IMAP_SEARCH or "UNSEEN"
        mailbox = options["mailbox"] or settings.INBOUND_EMAIL_IMAP_MAILBOX or "INBOX"
        limit = max(options["limit"], 1)
        mark_seen = bool(options["mark_seen"] or "UNSEEN" in search_query.upper())

        client_class = imaplib.IMAP4_SSL if settings.INBOUND_EMAIL_IMAP_USE_SSL else imaplib.IMAP4
        client = client_class(settings.INBOUND_EMAIL_IMAP_HOST, settings.INBOUND_EMAIL_IMAP_PORT)

        try:
            client.login(settings.INBOUND_EMAIL_IMAP_USER, settings.INBOUND_EMAIL_IMAP_PASSWORD)
            status, _ = client.select(mailbox)
            if status != "OK":
                raise CommandError(f"Impossible d'ouvrir la boite IMAP {mailbox}.")

            status, data = client.search(None, search_query)
            if status != "OK":
                raise CommandError("La recherche IMAP a echoue.")

            identifiers = [item for item in data[0].split() if item][-limit:]
            processed = 0

            for message_id in identifiers:
                status, payload = client.fetch(message_id, "(RFC822)")
                if status != "OK":
                    continue

                raw_message = b""
                for chunk in payload:
                    if isinstance(chunk, tuple) and len(chunk) == 2:
                        raw_message = chunk[1]
                        break
                if not raw_message:
                    continue

                email_payload, uploaded_files = parse_inbound_email_message(raw_message)
                result = handle_email_inbound(email_payload, uploaded_files=uploaded_files)
                if not result.get("created"):
                    continue

                processed += 1
                if mark_seen:
                    client.store(message_id, "+FLAGS", "(\\Seen)")

                self.stdout.write(
                    self.style.SUCCESS(
                        f"Email {message_id.decode()} traite pour le ticket {result['ticket_reference']}."
                    )
                )

            self.stdout.write(self.style.SUCCESS(f"{processed} email(s) traite(s)."))
        finally:
            try:
                client.logout()
            except Exception:  # noqa: BLE001
                pass
