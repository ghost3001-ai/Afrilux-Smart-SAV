from unittest.mock import patch

from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from .base import *

from ..comms import DeliveryResult, create_external_channel_notifications
from ..models import Message, Notification, Ticket


class NotificationTests(SavPlatformTests):
    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        EMAIL_HOST="smtp.test.local",
        DEFAULT_FROM_EMAIL="noreply@afrilux.test",
    )
    def test_internal_outbound_message_creates_email_notification(self):
        self.client_user.email = "client@example.com"
        self.client_user.save(update_fields=["email"])
        ticket = Ticket.objects.create(
            client=self.client_user,
            product=self.product,
            assigned_agent=self.agent,
            title="Mise a jour par email",
            description="Ticket cible pour notification email.",
            category=Ticket.CATEGORY_BREAKDOWN,
            status=Ticket.STATUS_IN_PROGRESS,
            priority=Ticket.PRIORITY_NORMAL,
        )

        response = self.api.post(
            reverse("sav_api:message-list"),
            {
                "ticket": ticket.id,
                "content": "Nous avons commande la piece et revenons vers vous.",
                "channel": Message.CHANNEL_EMAIL,
            },
        )

        self.assertEqual(response.status_code, 201)
        self.assertTrue(
            Notification.objects.filter(
                ticket=ticket,
                recipient=self.client_user,
                channel=Notification.CHANNEL_EMAIL,
                event_type="ticket_message",
                status=Notification.STATUS_SENT,
            ).exists()
        )

    @override_settings(
        EMAIL_HOST="smtp.test.local",
        DEFAULT_FROM_EMAIL="noreply@afrilux.test",
        TWILIO_ACCOUNT_SID="AC123",
        TWILIO_AUTH_TOKEN="secret",
        TWILIO_WHATSAPP_FROM="whatsapp:+15551230000",
        TWILIO_SMS_FROM="",
    )
    def test_external_notification_creates_email_and_whatsapp_channels(self):
        self.client_user.email = "client@example.com"
        self.client_user.phone = "+237691674993"
        self.client_user.save(update_fields=["email", "phone"])
        ticket = Ticket.objects.create(
            client=self.client_user,
            product=self.product,
            assigned_agent=self.agent,
            title="Notification multicanal",
            description="Ticket cible pour notification email et WhatsApp.",
            category=Ticket.CATEGORY_BREAKDOWN,
            status=Ticket.STATUS_IN_PROGRESS,
            priority=Ticket.PRIORITY_NORMAL,
        )

        with patch("sav.comms.deliver_notification") as deliver:
            notifications = create_external_channel_notifications(
                recipient=self.client_user,
                ticket=ticket,
                event_type="ticket_update",
                subject="Mise a jour SAV",
                message="Votre dossier SAV a ete mis a jour.",
            )

        channels = {notification.channel for notification in notifications}
        self.assertIn(Notification.CHANNEL_IN_APP, channels)
        self.assertIn(Notification.CHANNEL_EMAIL, channels)
        self.assertIn(Notification.CHANNEL_WHATSAPP, channels)
        self.assertNotIn(Notification.CHANNEL_SMS, channels)
        self.assertEqual(deliver.call_count, len(notifications))

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        EMAIL_HOST="smtp.test.local",
        DEFAULT_FROM_EMAIL="noreply@afrilux.test",
        TWILIO_ACCOUNT_SID="AC123",
        TWILIO_AUTH_TOKEN="secret",
        TWILIO_WHATSAPP_FROM="whatsapp:+15551230000",
        TWILIO_SMS_FROM="+15551239999",
        SAV_PUBLIC_BASE_URL="https://sav.afrilux.test",
    )
    def test_external_notification_records_deep_link_contact_and_delivery_trace(self):
        self.client_user.email = "client@example.com"
        self.client_user.phone = "+237600000000"
        self.client_user.sms_phone = "+237691111111"
        self.client_user.whatsapp_phone = "+237692222222"
        self.client_user.save(update_fields=["email", "phone", "sms_phone", "whatsapp_phone"])
        ticket = Ticket.objects.create(
            client=self.client_user,
            product=self.product,
            title="Notification tracee",
            description="Verifier les traces multicanaux.",
            category=Ticket.CATEGORY_BREAKDOWN,
            status=Ticket.STATUS_ASSIGNED,
            priority=Ticket.PRIORITY_NORMAL,
        )

        def fake_twilio(notification, use_whatsapp):
            if use_whatsapp:
                return DeliveryResult(False, "twilio_whatsapp", error_message="Numero WhatsApp non inscrit")
            return DeliveryResult(True, "twilio_sms", external_id="SM123")

        with patch("sav.comms._deliver_twilio_message", side_effect=fake_twilio):
            notifications = create_external_channel_notifications(
                recipient=self.client_user,
                ticket=ticket,
                event_type="start_requested",
                subject="Validation debut",
                message="Veuillez valider le debut.",
            )

        by_channel = {notification.channel: notification for notification in notifications}
        self.assertEqual(by_channel[Notification.CHANNEL_WHATSAPP].status, Notification.STATUS_FAILED)
        self.assertIn("WhatsApp", by_channel[Notification.CHANNEL_WHATSAPP].error_message)
        self.assertEqual(by_channel[Notification.CHANNEL_WHATSAPP].recipient_contact, "+237692222222")
        self.assertEqual(by_channel[Notification.CHANNEL_SMS].status, Notification.STATUS_SENT)
        self.assertEqual(by_channel[Notification.CHANNEL_SMS].provider_reference, "SM123")
        self.assertEqual(by_channel[Notification.CHANNEL_SMS].recipient_contact, "+237691111111")
        self.assertTrue(by_channel[Notification.CHANNEL_EMAIL].deep_link.endswith(f"/tickets/{ticket.pk}/"))
        self.assertEqual(by_channel[Notification.CHANNEL_EMAIL].status, Notification.STATUS_SENT)
        self.assertEqual(by_channel[Notification.CHANNEL_EMAIL].provider, "smtp")
        self.assertEqual(by_channel[Notification.CHANNEL_IN_APP].action_payload["event_type"], "start_requested")

    @override_settings(
        EMAIL_HOST="smtp.test.local",
        DEFAULT_FROM_EMAIL="noreply@afrilux.test",
        TWILIO_ACCOUNT_SID="AC123",
        TWILIO_AUTH_TOKEN="secret",
        TWILIO_WHATSAPP_FROM="whatsapp:+15551230000",
        TWILIO_SMS_FROM="+15551239999",
    )
    def test_external_notification_respects_user_channel_preferences(self):
        self.client_user.email = "client@example.com"
        self.client_user.phone = "+237691674993"
        self.client_user.notification_whatsapp_enabled = False
        self.client_user.notification_sms_enabled = False
        self.client_user.save(
            update_fields=[
                "email",
                "phone",
                "notification_whatsapp_enabled",
                "notification_sms_enabled",
            ]
        )
        ticket = Ticket.objects.create(
            client=self.client_user,
            product=self.product,
            title="Preferences notification",
            description="Verifier les canaux actifs.",
            category=Ticket.CATEGORY_BREAKDOWN,
            status=Ticket.STATUS_ASSIGNED,
            priority=Ticket.PRIORITY_NORMAL,
        )

        with patch("sav.comms.deliver_notification") as deliver:
            notifications = create_external_channel_notifications(
                recipient=self.client_user,
                ticket=ticket,
                event_type="ticket_update",
                subject="Mise a jour",
                message="Notification selon preferences.",
            )

        channels = {notification.channel for notification in notifications}
        self.assertIn(Notification.CHANNEL_IN_APP, channels)
        self.assertIn(Notification.CHANNEL_EMAIL, channels)
        self.assertNotIn(Notification.CHANNEL_WHATSAPP, channels)
        self.assertNotIn(Notification.CHANNEL_SMS, channels)
        self.assertEqual(deliver.call_count, len(notifications))

    def test_client_created_ticket_notifies_manager_on_multichannel_event(self):
        self.api.force_authenticate(user=self.client_user)

        with patch("sav.comms.deliver_notification") as deliver:
            response = self.api.post(
                reverse("sav_api:ticket-list"),
                {
                    "title": "Ticket cree par client",
                    "description": "Le client ouvre un ticket depuis l'application.",
                    "category": Ticket.CATEGORY_BREAKDOWN,
                    "channel": Ticket.CHANNEL_EMAIL,
                },
                format="json",
            )

        self.assertEqual(response.status_code, 201)
        ticket = Ticket.objects.get(pk=response.data["id"])
        self.assertEqual(ticket.status, Ticket.STATUS_PENDING_ASSIGNMENT)
        self.assertEqual(ticket.channel, Ticket.CHANNEL_WEB)
        self.assertTrue(
            Notification.objects.filter(
                ticket=ticket,
                recipient=self.manager,
                event_type="ticket_created_by_client",
            ).exists()
        )
        self.assertGreaterEqual(deliver.call_count, 1)

    def test_notification_can_be_marked_clicked_for_deep_link_tracking(self):
        notification = Notification.objects.create(
            recipient=self.manager,
            ticket=Ticket.objects.create(
                client=self.client_user,
                product=self.product,
                title="Lien profond",
                description="Verifier le clic.",
                category=Ticket.CATEGORY_BREAKDOWN,
                status=Ticket.STATUS_ASSIGNED,
                priority=Ticket.PRIORITY_NORMAL,
            ),
            channel=Notification.CHANNEL_IN_APP,
            event_type="ticket_update",
            subject="Lien disponible",
            message="Ouvrir le ticket.",
            deep_link="https://sav.afrilux.test/tickets/1/",
        )

        response = self.api.post(reverse("sav_api:notification-mark-clicked", args=[notification.pk]))

        self.assertEqual(response.status_code, 200)
        notification.refresh_from_db()
        self.assertEqual(notification.status, Notification.STATUS_CLICKED)
        self.assertIsNotNone(notification.clicked_at)

    def test_notification_list_returns_only_current_recipient_notifications(self):
        Notification.objects.create(
            recipient=self.manager,
            channel=Notification.CHANNEL_IN_APP,
            event_type="manager_only",
            subject="Notif manager",
            message="Visible uniquement manager.",
        )
        Notification.objects.create(
            recipient=self.agent,
            channel=Notification.CHANNEL_IN_APP,
            event_type="agent_only",
            subject="Notif agent",
            message="Visible uniquement agent.",
        )
        self.api.force_authenticate(user=self.manager)

        response = self.api.get(reverse("sav_api:notification-list"))

        self.assertEqual(response.status_code, 200)
        payload = response.data["results"] if isinstance(response.data, dict) and "results" in response.data else response.data
        self.assertEqual(len(payload), 1)
        self.assertEqual(payload[0]["recipient"], self.manager.id)
