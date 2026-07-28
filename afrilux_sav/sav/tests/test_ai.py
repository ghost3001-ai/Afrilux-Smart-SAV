import json
from datetime import timedelta
from unittest.mock import patch

from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from .base import *

from ..ai import LLMCompletion
from ..models import AIActionLog, Message, Notification, PredictiveAlert, ProductTelemetry, Ticket


class AITests(SavPlatformTests):
    def test_agentic_resolution_auto_resolves_warranty_return(self):
        ticket = Ticket.objects.create(
            client=self.client_user,
            product=self.product,
            title="Retour sous garantie",
            description="Produit defectueux, je souhaite un retour sous garantie.",
            category=Ticket.CATEGORY_RETURN,
            status=Ticket.STATUS_NEW,
            priority=Ticket.PRIORITY_NORMAL,
        )

        response = self.api.post(reverse("sav_api:ticket-agentic-resolution", args=[ticket.pk]), {})
        ticket.refresh_from_db()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(ticket.status, Ticket.STATUS_RESOLVED)
        self.assertTrue(response.data["auto_resolved"])
        self.assertTrue(AIActionLog.objects.filter(ticket=ticket).exists())
        self.assertTrue(Notification.objects.filter(ticket=ticket, recipient=self.client_user).exists())

    def test_predictive_analysis_creates_alert_and_preventive_ticket(self):
        ProductTelemetry.objects.create(
            product=self.product,
            metric_name="temperature",
            value=86,
            unit="C",
        )

        response = self.api.post(reverse("sav_api:product-predictive-analysis", args=[self.product.pk]), {})

        self.assertEqual(response.status_code, 200)
        self.product.refresh_from_db()
        self.assertGreaterEqual(len(response.data["alerts_created"]), 1)
        self.assertLess(self.product.health_score, 100)
        self.assertTrue(
            Ticket.objects.filter(product=self.product, category=Ticket.CATEGORY_MAINTENANCE).exists()
        )

    def test_customer_insights_returns_high_risk_for_critical_case(self):
        ticket = Ticket.objects.create(
            client=self.client_user,
            product=self.product,
            title="Panne totale",
            description="Le systeme est completement bloque.",
            category=Ticket.CATEGORY_BREAKDOWN,
            status=Ticket.STATUS_NEW,
            priority=Ticket.PRIORITY_CRITICAL,
        )
        Message.objects.create(
            ticket=ticket,
            sender=self.client_user,
            message_type=Message.TYPE_PUBLIC,
            channel=Message.CHANNEL_WHATSAPP,
            direction=Message.DIRECTION_INBOUND,
            content="Je suis tres decu, le probleme revient encore.",
            sentiment_score=-0.60,
        )

        response = self.api.get(reverse("sav_api:user-insights", args=[self.client_user.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["risk_level"], "high")
        self.assertEqual(response.data["critical_open_tickets"], 1)

    def test_analytics_ask_answers_about_critical_tickets(self):
        Ticket.objects.create(
            client=self.client_user,
            product=self.product,
            title="Alerte critique",
            description="Incident critique en cours.",
            category=Ticket.CATEGORY_BREAKDOWN,
            status=Ticket.STATUS_NEW,
            priority=Ticket.PRIORITY_CRITICAL,
            sla_deadline=timezone.now() + timedelta(hours=2),
        )

        response = self.api.post(reverse("sav_api:analytics-ask"), {"question": "Combien de tickets critiques avons-nous ?"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["matched_intent"], "critical_tickets")
        self.assertIn("ticket(s) critique(s)", response.data["answer"])

    def test_analytics_ask_answers_about_agent_performance(self):
        ticket = Ticket.objects.create(
            client=self.client_user,
            product=self.product,
            assigned_agent=self.agent,
            title="Resolution express",
            description="Ticket clos pour mesure de performance.",
            category=Ticket.CATEGORY_BREAKDOWN,
            status=Ticket.STATUS_RESOLVED,
            priority=Ticket.PRIORITY_NORMAL,
        )
        Ticket.objects.filter(pk=ticket.pk).update(created_at=timezone.now() - timedelta(hours=3))

        response = self.api.post(reverse("sav_api:analytics-ask"), {"question": "Quels sont les agents les plus performants ?"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["matched_intent"], "top_agents")
        self.assertTrue(response.data["data"]["top_agents"])

    def test_analytics_ask_is_forbidden_for_client_profiles(self):
        self.api.force_authenticate(user=self.client_user)

        response = self.api.post(reverse("sav_api:analytics-ask"), {"question": "Combien de tickets critiques avons-nous ?"})

        self.assertEqual(response.status_code, 403)

    def test_analytics_ask_is_forbidden_for_support_profiles(self):
        self.api.force_authenticate(user=self.agent)

        response = self.api.post(reverse("sav_api:analytics-ask"), {"question": "Combien de tickets critiques avons-nous ?"})

        self.assertEqual(response.status_code, 403)

    def test_support_assistant_returns_ticket_draft(self):
        response = self.api.post(
            reverse("sav_api:support-assistant"),
            {
                "question": "Mon equipement ne charge plus et affiche une erreur de cablage.",
                "product": self.product.id,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("answer", response.data)
        self.assertIn("draft_ticket", response.data)
        self.assertEqual(response.data["suggested_category"], Ticket.CATEGORY_BREAKDOWN)
        self.assertTrue(response.data["matched_articles"])

    @override_settings(OPENAI_API_KEY="", OPENAI_MODEL="gpt-5.1")
    def test_ai_status_reports_heuristic_mode_without_api_key(self):
        response = self.api.get(reverse("sav_api:ai-status"))

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["enabled"])
        self.assertEqual(response.data["mode"], "heuristique")
        self.assertNotIn("api_key", response.data)

    @override_settings(OPENAI_API_KEY="", OPENAI_MODEL="gpt-5.1")
    def test_support_assistant_exposes_heuristic_ai_metadata(self):
        response = self.api.post(
            reverse("sav_api:support-assistant"),
            {
                "question": "Mon equipement signale un probleme de batterie.",
                "product": self.product.id,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["ai_mode"], "heuristique")
        self.assertFalse(response.data["ai_configured"])

    @override_settings(OPENAI_API_KEY="sk-test-openai-enabled", OPENAI_MODEL="gpt-5.1")
    def test_support_assistant_uses_openai_payload_when_configured(self):
        completion = LLMCompletion(
            ok=True,
            content=json.dumps(
                {
                    "answer": "Controlez la batterie puis ouvrez un ticket si le defaut persiste.",
                    "suggested_priority": Ticket.PRIORITY_HIGH,
                    "suggested_category": Ticket.CATEGORY_BREAKDOWN,
                    "likely_issue": "battery_issue",
                    "should_create_ticket": True,
                    "recommended_next_step": "Programmer une verification batterie",
                    "draft_title": "Defaut batterie",
                    "draft_description": "Controle batterie recommande.",
                    "confidence": "0.91",
                }
            ),
            raw={"id": "resp_test"},
            provider="openai",
            model="gpt-5.1",
            request_id="resp_test",
        )

        with patch("sav.ai.OpenAIResponsesClient.complete_json", return_value=completion):
            response = self.api.post(
                reverse("sav_api:support-assistant"),
                {
                    "question": "La batterie ne tient plus la charge.",
                    "product": self.product.id,
                },
                format="json",
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["ai_mode"], "openai")
        self.assertTrue(response.data["ai_configured"])
        self.assertEqual(response.data["ai_model"], "gpt-5.1")
        self.assertEqual(response.data["draft_ticket"]["title"], "Defaut batterie")

    def test_analytics_page_redirects_anonymous_users_to_login(self):
        response = self.client.get(reverse("analytics-page"))

        self.assertRedirects(response, f"{reverse('login')}?next={reverse('analytics-page')}")

    def test_analytics_page_is_forbidden_for_client_profiles(self):
        self.client.force_login(self.client_user)

        response = self.client.get(reverse("analytics-page"))

        self.assertEqual(response.status_code, 403)
