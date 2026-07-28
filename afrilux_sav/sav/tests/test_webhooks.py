import json

from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, override_settings
from django.urls import reverse

from .base import SavPlatformTests
from ..models import (
    Message,
    Notification,
    Ticket,
    TicketAttachment,
)


class WebhookTests(SavPlatformTests):
    def test_twilio_inbound_webhook_creates_message(self):
        self.client_user.phone = "+237690000000"
        self.client_user.save(update_fields=["phone"])
        ticket = Ticket.objects.create(
            client=self.client_user,
            product=self.product,
            title="Incident WhatsApp",
            description="Ticket cible pour webhook.",
            category=Ticket.CATEGORY_BREAKDOWN,
            status=Ticket.STATUS_NEW,
            priority=Ticket.PRIORITY_NORMAL,
        )

        response = self.client.post(
            reverse("sav_api:twilio-inbound"),
            {
                "From": "whatsapp:+237690000000",
                "Body": f"{ticket.reference} Le probleme persiste apres redemarrage.",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["created"])
        self.assertTrue(
            Message.objects.filter(ticket=ticket, channel=Message.CHANNEL_WHATSAPP, content__icontains="persiste").exists()
        )

    @override_settings(SAV_REQUIRE_WEBHOOK_SIGNATURES=True, TWILIO_AUTH_TOKEN="")
    def test_twilio_inbound_webhook_rejects_unsigned_requests_when_required(self):
        response = self.client.post(
            reverse("sav_api:twilio-inbound"),
            {
                "From": "whatsapp:+237690000000",
                "Body": "Demande non signee",
            },
        )

        self.assertEqual(response.status_code, 403)

    def test_email_inbound_webhook_creates_ticket_and_attachment(self):
        payload = SimpleUploadedFile("capture-erreur.txt", b"preuve ticket email", content_type="text/plain")

        response = self.client.post(
            reverse("sav_api:email-inbound"),
            {
                "from": "nouveau.client@example.com",
                "subject": "Retrait echoue",
                "body": "Bonjour, le retrait a echoue et voici la preuve.",
                "to": self.organization.support_email,
                "attachments": payload,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["created"])
        created_ticket = Ticket.objects.get(reference=response.json()["ticket_reference"])
        self.assertEqual(created_ticket.organization, self.organization)
        self.assertEqual(created_ticket.channel, Ticket.CHANNEL_EMAIL)
        self.assertTrue(
            TicketAttachment.objects.filter(ticket=created_ticket, original_name="capture-erreur.txt").exists()
        )

    @override_settings(SAV_REQUIRE_WEBHOOK_SIGNATURES=True, INBOUND_EMAIL_WEBHOOK_TOKEN="secret-webhook-token")
    def test_email_inbound_webhook_requires_token_when_signatures_are_enabled(self):
        response = self.client.post(
            reverse("sav_api:email-inbound"),
            {
                "from": "unsigned@example.com",
                "subject": "Email non signe",
                "body": "Ce message doit etre refuse.",
            },
        )

        self.assertEqual(response.status_code, 403)

    def test_email_inbound_webhook_rejects_unsafe_attachment_type(self):
        payload = SimpleUploadedFile("payload.exe", b"binary", content_type="application/octet-stream")

        response = self.client.post(
            reverse("sav_api:email-inbound"),
            {
                "from": "nouveau.client@example.com",
                "subject": "Piece jointe dangereuse",
                "body": "Bonjour, voir la piece jointe.",
                "to": self.organization.support_email,
                "attachments": payload,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["attachment_count"], 0)
        self.assertEqual(response.json()["rejected_attachment_count"], 1)

    def test_support_assistant_accepts_csrf_protected_portal_request(self):
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.client_user)

        page_response = csrf_client.get(reverse("support-page"))

        self.assertEqual(page_response.status_code, 200)
        self.assertIn("csrftoken", page_response.cookies)

        response = csrf_client.post(
            reverse("sav_api:support-assistant"),
            data=json.dumps(
                {
                    "question": "Ma climatisation ne refroidit plus correctement.",
                    "product": self.product.id,
                }
            ),
            content_type="application/json",
            HTTP_X_CSRFTOKEN=page_response.cookies["csrftoken"].value,
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("answer", response.json())

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        EMAIL_HOST="smtp.test.local",
        DEFAULT_FROM_EMAIL="noreply@afrilux.test",
    )
    def test_web_public_message_to_specific_recipient_sends_email(self):
        ticket = Ticket.objects.create(
            client=self.client_user,
            product=self.product,
            assigned_agent=self.agent,
            title="Message email sortant",
            description="Verifier l'envoi email depuis le portail.",
            category=Ticket.CATEGORY_BREAKDOWN,
            status=Ticket.STATUS_IN_PROGRESS,
            priority=Ticket.PRIORITY_NORMAL,
        )
        self.client.force_login(self.manager)

        response = self.client.post(
            reverse("ticket-message-create", args=[ticket.pk]),
            {
                "recipient": self.client_user.pk,
                "message_type": Message.TYPE_PUBLIC,
                "channel": Message.CHANNEL_EMAIL,
                "content": "Votre intervention est bien programmee.",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.client_user.email])
        self.assertTrue(
            Notification.objects.filter(
                ticket=ticket,
                recipient=self.client_user,
                channel=Notification.CHANNEL_EMAIL,
                status=Notification.STATUS_SENT,
            ).exists()
        )

    def test_support_page_renders_for_client(self):
        self.client.force_login(self.client_user)

        response = self.client.get(reverse("support-page"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "sav/support.html")
        self.assertContains(response, 'name="csrfmiddlewaretoken"', html=False)
