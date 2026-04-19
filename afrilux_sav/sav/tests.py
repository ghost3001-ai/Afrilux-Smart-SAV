import io
import json
from datetime import timedelta
from email.message import EmailMessage
from unittest.mock import patch

from django.core.management import call_command
from django.core.files.uploadedfile import SimpleUploadedFile
from django.forms import HiddenInput
from django.test import TestCase
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from .forms import TicketCreateForm
from .models import (
    AccountCredit,
    AIActionLog,
    AuditLog,
    DeviceRegistration,
    EquipmentCategory,
    GeneratedReport,
    FinancialTransaction,
    KnowledgeArticle,
    Message,
    Notification,
    Organization,
    PredictiveAlert,
    Product,
    ProductTelemetry,
    SlaRule,
    TicketAttachment,
    TicketAssignment,
    TicketFeedback,
    Ticket,
    User,
    WorkflowExecution,
)


class SavPlatformTests(TestCase):
    def setUp(self):
        self.api = APIClient()
        self.organization = Organization.objects.create(
            name="Afrilux Habitat",
            brand_name="Afrilux Habitat",
            portal_tagline="Support energie et equipements habitat",
            primary_color="#D5671D",
            accent_color="#1C7A6A",
            support_email="support-habitat@test.local",
        )
        self.other_organization = Organization.objects.create(
            name="Solaris Industries",
            brand_name="Solaris Industries",
            portal_tagline="Operations industrielles",
            primary_color="#0F6E8C",
            accent_color="#1F9D73",
            support_email="support-solaris@test.local",
        )
        self.manager = User.objects.create_user(
            username="manager",
            email="manager@test.local",
            password="secret123",
            organization=self.organization,
            role=User.ROLE_HEAD_SAV,
            is_staff=True,
        )
        self.auditor = User.objects.create_user(
            username="auditor",
            email="auditor@test.local",
            password="secret123",
            organization=self.organization,
            role=User.ROLE_AUDITOR,
        )
        self.qa_user = User.objects.create_user(
            username="qa",
            email="qa@test.local",
            password="secret123",
            organization=self.organization,
            role=User.ROLE_QA,
        )
        self.dispatcher = User.objects.create_user(
            username="dispatcher",
            email="dispatcher@test.local",
            password="secret123",
            organization=self.organization,
            role=User.ROLE_DISPATCHER,
        )
        self.agent = User.objects.create_user(
            username="agent",
            password="secret123",
            organization=self.organization,
            role=User.ROLE_SUPPORT,
        )
        self.technician = User.objects.create_user(
            username="technician",
            password="secret123",
            organization=self.organization,
            role=User.ROLE_TECHNICIAN,
        )
        self.expert = User.objects.create_user(
            username="expert",
            password="secret123",
            organization=self.organization,
            role=User.ROLE_EXPERT,
        )
        self.field_technician = User.objects.create_user(
            username="fieldtech",
            password="secret123",
            organization=self.organization,
            role=User.ROLE_FIELD_TECHNICIAN,
        )
        self.vip_support = User.objects.create_user(
            username="vipsupport",
            password="secret123",
            organization=self.organization,
            role=User.ROLE_VIP_SUPPORT,
        )
        self.client_user = User.objects.create_user(
            username="client",
            email="client@test.local",
            password="secret123",
            organization=self.organization,
            role=User.ROLE_CLIENT,
            company_name="Afrilux Habitat",
        )
        self.other_manager = User.objects.create_user(
            username="manager_b",
            password="secret123",
            organization=self.other_organization,
            role=User.ROLE_HEAD_SAV,
            is_staff=True,
        )
        self.other_agent = User.objects.create_user(
            username="agent_b",
            password="secret123",
            organization=self.other_organization,
            role=User.ROLE_SUPPORT,
        )
        self.other_client = User.objects.create_user(
            username="client_b",
            password="secret123",
            organization=self.other_organization,
            role=User.ROLE_CLIENT,
            company_name="Solaris Industries",
        )
        self.category = EquipmentCategory.objects.create(
            organization=self.organization,
            name="Impression",
            code="print",
            is_active=True,
        )
        self.other_category = EquipmentCategory.objects.create(
            organization=self.other_organization,
            name="Energie",
            code="energy",
            is_active=True,
        )
        self.product = Product.objects.create(
            client=self.client_user,
            name="Onduleur 5kVA",
            sku="AFR-OND-5KVA",
            serial_number="AFR-0001",
            warranty_end=timezone.localdate() + timedelta(days=40),
            iot_enabled=True,
        )
        self.other_product = Product.objects.create(
            client=self.other_client,
            name="Regulateur 8kVA",
            sku="SOL-REG-8KVA",
            serial_number="SOL-0001",
            warranty_end=timezone.localdate() + timedelta(days=55),
            iot_enabled=True,
        )
        KnowledgeArticle.objects.create(
            title="Guide de verification du cablage",
            category="depannage",
            product=self.product,
            summary="Verifier les connexions et redemarrer l'equipement.",
            content="Controlez le cable principal, resserrez les bornes et relancez le systeme.",
            keywords="cable, branchement, borne, redemarrer",
            status=KnowledgeArticle.STATUS_PUBLISHED,
            audience=KnowledgeArticle.AUDIENCE_PUBLIC,
        )
        self.api.force_authenticate(user=self.manager)

    def test_dashboard_returns_augmented_metrics(self):
        Ticket.objects.create(
            client=self.client_user,
            product=self.product,
            assigned_agent=self.agent,
            title="Bruit anormal",
            description="Le ventilateur fait du bruit.",
            status=Ticket.STATUS_IN_PROGRESS,
            priority=Ticket.PRIORITY_HIGH,
            sla_deadline=timezone.now() + timedelta(hours=4),
        )
        Ticket.objects.create(
            client=self.client_user,
            product=self.product,
            title="Pas de charge",
            description="Batterie defectueuse, situation critique.",
            status=Ticket.STATUS_NEW,
            priority=Ticket.PRIORITY_CRITICAL,
            sla_deadline=timezone.now() - timedelta(hours=1),
        )
        PredictiveAlert.objects.create(
            product=self.product,
            alert_type=PredictiveAlert.TYPE_ANOMALY,
            severity=PredictiveAlert.SEVERITY_HIGH,
            title="Temperature elevee",
            description="Le seuil de temperature est depasse.",
        )

        response = self.api.get(reverse("sav_api:dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["tickets_total"], 2)
        self.assertEqual(response.data["tickets_open"], 2)
        self.assertEqual(response.data["tickets_overdue"], 1)
        self.assertEqual(response.data["predictive_alerts_open"], 1)
        self.assertEqual(response.data["tickets_critical_open"], 1)

    def test_public_health_endpoint_returns_ok(self):
        response = self.client.get(reverse("sav_api:health"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")
        self.assertEqual(response.json()["database"], "ok")
        self.assertEqual(response.json()["cache"], "ok")

    def test_dashboard_returns_resolution_and_agent_metrics(self):
        ticket = Ticket.objects.create(
            client=self.client_user,
            product=self.product,
            assigned_agent=self.agent,
            title="Reclamation cloturee",
            description="Plainte client resolue.",
            category=Ticket.CATEGORY_COMPLAINT,
            status=Ticket.STATUS_RESOLVED,
            priority=Ticket.PRIORITY_HIGH,
            suspected_fraud=True,
        )
        Ticket.objects.filter(pk=ticket.pk).update(created_at=timezone.now() - timedelta(hours=6))

        response = self.api.get(reverse("sav_api:dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["complaints_total"], 1)
        self.assertEqual(response.data["fraud_suspected_open"], 0)
        self.assertAlmostEqual(response.data["average_resolution_hours"], 6.0, places=1)
        self.assertEqual(response.data["top_agents"][0]["agent_name"], str(self.agent))

    def test_ticket_list_supports_optional_pagination(self):
        Ticket.objects.create(
            client=self.client_user,
            product=self.product,
            title="Ticket pagination 1",
            description="Premier ticket.",
            category=Ticket.CATEGORY_BREAKDOWN,
            status=Ticket.STATUS_NEW,
            priority=Ticket.PRIORITY_NORMAL,
        )
        Ticket.objects.create(
            client=self.client_user,
            product=self.product,
            title="Ticket pagination 2",
            description="Second ticket.",
            category=Ticket.CATEGORY_BREAKDOWN,
            status=Ticket.STATUS_NEW,
            priority=Ticket.PRIORITY_NORMAL,
        )

        response = self.api.get(reverse("sav_api:ticket-list"), {"page": 1, "page_size": 1})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 2)
        self.assertEqual(len(response.data["results"]), 1)

    def test_jwt_token_endpoint_accepts_email_identifier(self):
        token_client = APIClient()

        response = token_client.post(
            reverse("token_obtain_pair"),
            {"username": self.client_user.email, "password": "secret123"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)

    def test_audit_log_records_request_metadata(self):
        response = self.api.post(
            reverse("sav_api:ticket-list"),
            {
                "client": self.client_user.id,
                "product": self.product.id,
                "title": "Incident audite",
                "description": "Verifier les metadonnees d'audit.",
                "category": Ticket.CATEGORY_BREAKDOWN,
                "channel": Ticket.CHANNEL_WEB,
                "priority": Ticket.PRIORITY_NORMAL,
            },
            format="json",
            HTTP_USER_AGENT="sav-test-suite",
        )

        self.assertEqual(response.status_code, 201)
        audit_log = AuditLog.objects.filter(action="ticket_created").latest("created_at")
        self.assertEqual(audit_log.http_method, "POST")
        self.assertEqual(audit_log.request_path, reverse("sav_api:ticket-list"))
        self.assertEqual(audit_log.user_agent, "sav-test-suite")
        self.assertTrue(audit_log.source_ip)

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

    def test_agent_can_list_clients_for_mobile_ticket_creation(self):
        self.api.force_authenticate(user=self.agent)

        response = self.api.get(reverse("sav_api:user-list"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["id"], self.client_user.id)
        self.assertEqual(response.data[0]["organization_name"], self.organization.display_name)

    def test_ticket_queryset_can_filter_suspected_fraud(self):
        Ticket.objects.create(
            client=self.client_user,
            product=self.product,
            title="Paiement frauduleux",
            description="Je signale une fraude sur la transaction.",
            category=Ticket.CATEGORY_COMPLAINT,
            status=Ticket.STATUS_NEW,
            priority=Ticket.PRIORITY_HIGH,
            suspected_fraud=True,
        )
        Ticket.objects.create(
            client=self.client_user,
            product=self.product,
            title="Panne standard",
            description="Incident classique.",
            category=Ticket.CATEGORY_BREAKDOWN,
            status=Ticket.STATUS_NEW,
            priority=Ticket.PRIORITY_NORMAL,
        )

        response = self.api.get(reverse("sav_api:ticket-list"), {"suspected_fraud": "true"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertTrue(response.data[0]["suspected_fraud"])

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

    def test_ticket_attachment_api_allows_client_upload(self):
        self.api.force_authenticate(user=self.client_user)
        ticket = Ticket.objects.create(
            client=self.client_user,
            product=self.product,
            title="Ticket avec preuve",
            description="Le client va charger une preuve.",
            category=Ticket.CATEGORY_BREAKDOWN,
            status=Ticket.STATUS_NEW,
            priority=Ticket.PRIORITY_NORMAL,
        )
        uploaded = SimpleUploadedFile("preuve.png", b"fake-image-content", content_type="image/png")

        response = self.api.post(
            reverse("sav_api:ticket-attachment-list"),
            {
                "ticket": ticket.id,
                "kind": TicketAttachment.KIND_SCREENSHOT,
                "note": "Capture mobile",
                "file": uploaded,
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, 201)
        self.assertTrue(
            TicketAttachment.objects.filter(ticket=ticket, uploaded_by=self.client_user, kind=TicketAttachment.KIND_SCREENSHOT).exists()
        )

    def test_dashboard_returns_average_first_response_hours(self):
        ticket = Ticket.objects.create(
            client=self.client_user,
            product=self.product,
            title="Attente prise en charge",
            description="Le client attend une premiere reponse.",
            category=Ticket.CATEGORY_BREAKDOWN,
            status=Ticket.STATUS_NEW,
            priority=Ticket.PRIORITY_NORMAL,
        )
        Ticket.objects.filter(pk=ticket.pk).update(created_at=timezone.now() - timedelta(hours=2))

        response = self.api.post(
            reverse("sav_api:message-list"),
            {
                "ticket": ticket.id,
                "content": "Nous prenons votre dossier en charge.",
                "channel": Message.CHANNEL_PORTAL,
            },
        )

        self.assertEqual(response.status_code, 201)

        dashboard = self.api.get(reverse("sav_api:dashboard"))

        self.assertEqual(dashboard.status_code, 200)
        self.assertAlmostEqual(dashboard.data["average_first_response_hours"], 2.0, places=1)

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

    def test_manager_can_credit_account_via_api(self):
        ticket = Ticket.objects.create(
            client=self.client_user,
            product=self.product,
            title="Demande geste commercial",
            description="Le client demande un credit sur son compte.",
            category=Ticket.CATEGORY_REFUND,
            status=Ticket.STATUS_IN_PROGRESS,
            priority=Ticket.PRIORITY_HIGH,
        )
        self.client_user.email = "client@example.com"
        self.client_user.save(update_fields=["email"])

        response = self.api.post(
            reverse("sav_api:ticket-credit-account", args=[ticket.pk]),
            {
                "amount": "15000.00",
                "currency": "XAF",
                "reason": "Geste commercial SAV",
                "note": "Credit accorde apres retard de traitement.",
                "external_reference": "CRM-7781",
            },
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(AccountCredit.objects.filter(ticket=ticket).count(), 1)
        credit = AccountCredit.objects.get(ticket=ticket)
        self.assertEqual(str(credit.amount), "15000.00")
        self.assertEqual(credit.executed_by, self.manager)
        self.assertTrue(WorkflowExecution.objects.filter(ticket=ticket, trigger_event="account_credit").exists())
        self.assertTrue(
            Notification.objects.filter(ticket=ticket, recipient=self.client_user, event_type="account_credit").exists()
        )
        self.assertTrue(
            Message.objects.filter(ticket=ticket, direction=Message.DIRECTION_OUTBOUND, content__icontains="15000.00").exists()
        )

    def test_device_registration_endpoint_registers_token(self):
        response = self.api.post(
            reverse("sav_api:device-registration-register"),
            {
                "token": "fcm-token-123",
                "platform": "android",
                "device_id": "pixel-7",
                "app_version": "1.0.0",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertTrue(
            DeviceRegistration.objects.filter(
                user=self.manager,
                token="fcm-token-123",
                platform=DeviceRegistration.PLATFORM_ANDROID,
                is_active=True,
            ).exists()
        )

    def test_dashboard_web_page_renders_for_manager(self):
        self.client.force_login(self.manager)

        response = self.client.get(reverse("dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "sav/dashboard.html")

    def test_dashboard_counts_only_operational_profiles_in_status_breakdown(self):
        response = self.api.get(reverse("sav_api:dashboard"))

        self.assertEqual(response.status_code, 200)
        technician_rows = {row["status"]: row["total"] for row in response.data["technician_status_breakdown"]}
        self.assertEqual(sum(technician_rows.values()), 5)
        self.assertEqual(technician_rows["available"], 5)

    def test_api_docs_page_renders(self):
        response = self.client.get(reverse("api-docs"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Documentation rapide")

    def test_local_static_asset_is_served(self):
        response = self.client.get("/static/sav/styles.css")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "body[data-theme=\"dark\"]")

    def test_analytics_page_redirects_anonymous_users_to_login(self):
        response = self.client.get(reverse("analytics-page"))

        self.assertRedirects(response, f"{reverse('login')}?next={reverse('analytics-page')}")

    def test_analytics_page_is_forbidden_for_client_profiles(self):
        self.client.force_login(self.client_user)

        response = self.client.get(reverse("analytics-page"))

        self.assertEqual(response.status_code, 403)

    def test_reporting_page_renders_for_qa_profiles(self):
        self.client.force_login(self.qa_user)

        response = self.client.get(reverse("reporting-page"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "sav/reporting.html")

    def test_manager_scope_excludes_other_organization_tickets(self):
        Ticket.objects.create(
            client=self.client_user,
            product=self.product,
            title="Incident habitat",
            description="Incident organisation A.",
            category=Ticket.CATEGORY_BREAKDOWN,
            status=Ticket.STATUS_NEW,
            priority=Ticket.PRIORITY_NORMAL,
        )
        Ticket.objects.create(
            client=self.other_client,
            product=self.other_product,
            title="Incident industrie",
            description="Incident organisation B.",
            category=Ticket.CATEGORY_BREAKDOWN,
            status=Ticket.STATUS_NEW,
            priority=Ticket.PRIORITY_NORMAL,
        )

        response = self.api.get(reverse("sav_api:ticket-list"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["client"], self.client_user.id)

    def test_ticket_detail_stays_accessible_when_legacy_ticket_org_drift_exists(self):
        ticket = Ticket.objects.create(
            client=self.client_user,
            product=self.product,
            organization=self.other_organization,
            assigned_agent=self.agent,
            title="Ticket legacy incoherent",
            description="Le ticket pointe sur le bon produit mais garde une organisation obsolete.",
            category=Ticket.CATEGORY_BREAKDOWN,
            status=Ticket.STATUS_NEW,
            priority=Ticket.PRIORITY_NORMAL,
        )
        self.client.force_login(self.manager)

        product_response = self.client.get(reverse("product-detail", args=[self.product.pk]))
        detail_response = self.client.get(reverse("ticket-detail", args=[ticket.pk]))

        self.assertEqual(product_response.status_code, 200)
        self.assertContains(product_response, ticket.reference)
        self.assertEqual(detail_response.status_code, 200)

    def test_dashboard_only_returns_same_organization_metrics(self):
        Ticket.objects.create(
            client=self.client_user,
            product=self.product,
            title="Ticket organisation A",
            description="Visible pour le manager A.",
            category=Ticket.CATEGORY_COMPLAINT,
            status=Ticket.STATUS_NEW,
            priority=Ticket.PRIORITY_HIGH,
        )
        Ticket.objects.create(
            client=self.other_client,
            product=self.other_product,
            title="Ticket organisation B",
            description="Ne doit pas etre visible pour le manager A.",
            category=Ticket.CATEGORY_COMPLAINT,
            status=Ticket.STATUS_NEW,
            priority=Ticket.PRIORITY_HIGH,
        )

        response = self.api.get(reverse("sav_api:dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["tickets_total"], 1)
        self.assertEqual(response.data["complaints_total"], 1)
        self.assertEqual(response.data["organization_name"], self.organization.display_name)

    def test_me_endpoint_exposes_verification_and_balance(self):
        FinancialTransaction.objects.create(
            client=self.client_user,
            organization=self.organization,
            external_reference="TX-DEP-1",
            transaction_type=FinancialTransaction.TYPE_DEPOSIT,
            ledger_side=FinancialTransaction.SIDE_CREDIT,
            amount="50000.00",
            currency="XAF",
            status=FinancialTransaction.STATUS_COMPLETED,
        )
        FinancialTransaction.objects.create(
            client=self.client_user,
            organization=self.organization,
            external_reference="TX-WDL-1",
            transaction_type=FinancialTransaction.TYPE_WITHDRAWAL,
            ledger_side=FinancialTransaction.SIDE_DEBIT,
            amount="12500.00",
            currency="XAF",
            status=FinancialTransaction.STATUS_COMPLETED,
        )
        self.client_user.is_verified = True
        self.client_user.save(update_fields=["is_verified"])
        self.api.force_authenticate(user=self.client_user)

        response = self.api.get(reverse("sav_api:user-me"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["is_verified"], True)
        self.assertEqual(response.data["account_balance"], "37500.00")

    def test_me_endpoint_exposes_organization_branding(self):
        response = self.api.get(reverse("sav_api:user-me"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["organization_name"], self.organization.display_name)
        self.assertEqual(response.data["organization_primary_color"], "#D5671D")

    def test_agent_can_take_unassigned_ticket(self):
        ticket = Ticket.objects.create(
            client=self.client_user,
            product=self.product,
            title="Ticket non assigne",
            description="A prendre par un agent.",
            category=Ticket.CATEGORY_BREAKDOWN,
            status=Ticket.STATUS_NEW,
            priority=Ticket.PRIORITY_NORMAL,
        )
        self.api.force_authenticate(user=self.agent)

        response = self.api.post(reverse("sav_api:ticket-take-ownership", args=[ticket.pk]), {})
        ticket.refresh_from_db()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(ticket.assigned_agent, self.agent)
        self.assertEqual(ticket.status, Ticket.STATUS_IN_PROGRESS)

    def test_client_can_reopen_resolved_ticket(self):
        ticket = Ticket.objects.create(
            client=self.client_user,
            product=self.product,
            title="Ticket resolu",
            description="Le client souhaite rouvrir le dossier.",
            category=Ticket.CATEGORY_COMPLAINT,
            status=Ticket.STATUS_RESOLVED,
            priority=Ticket.PRIORITY_NORMAL,
            resolved_at=timezone.now(),
        )
        self.api.force_authenticate(user=self.client_user)

        response = self.api.post(reverse("sav_api:ticket-reopen", args=[ticket.pk]), {})
        ticket.refresh_from_db()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(ticket.status, Ticket.STATUS_NEW)
        self.assertIsNone(ticket.resolved_at)

    def test_client_can_confirm_resolution(self):
        ticket = Ticket.objects.create(
            client=self.client_user,
            product=self.product,
            title="Validation client",
            description="Le client confirme la resolution.",
            category=Ticket.CATEGORY_BREAKDOWN,
            status=Ticket.STATUS_RESOLVED,
            priority=Ticket.PRIORITY_NORMAL,
            resolved_at=timezone.now(),
        )
        self.api.force_authenticate(user=self.client_user)

        response = self.api.post(reverse("sav_api:ticket-confirm-resolution", args=[ticket.pk]), {})
        ticket.refresh_from_db()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(ticket.status, Ticket.STATUS_CLOSED)
        self.assertIsNotNone(ticket.closed_at)

    def test_auditor_cannot_create_ticket_via_api(self):
        self.api.force_authenticate(user=self.auditor)

        response = self.api.post(
            reverse("sav_api:ticket-list"),
            {
                "client": self.client_user.id,
                "product_label": "Climatiseur split 18000 BTU",
                "title": "Creation interdite audit",
                "description": "Le profil auditeur ne doit pas creer de ticket.",
                "category": Ticket.CATEGORY_BREAKDOWN,
                "channel": Ticket.CHANNEL_WEB,
                "priority": Ticket.PRIORITY_NORMAL,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 403)

    def test_qa_cannot_create_ticket_via_api(self):
        self.api.force_authenticate(user=self.qa_user)

        response = self.api.post(
            reverse("sav_api:ticket-list"),
            {
                "client": self.client_user.id,
                "product_label": "Baie reseau datacenter",
                "title": "Creation interdite QA",
                "description": "Le profil QA ne doit pas creer de ticket.",
                "category": Ticket.CATEGORY_BREAKDOWN,
                "channel": Ticket.CHANNEL_WEB,
                "priority": Ticket.PRIORITY_NORMAL,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 403)

    def test_auditor_cannot_reply_on_ticket_via_web(self):
        ticket = Ticket.objects.create(
            client=self.client_user,
            product=self.product,
            title="Ticket lecture seule",
            description="L'auditeur ne doit pas intervenir.",
            category=Ticket.CATEGORY_BREAKDOWN,
            status=Ticket.STATUS_NEW,
            priority=Ticket.PRIORITY_NORMAL,
        )
        self.client.force_login(self.auditor)

        response = self.client.post(
            reverse("ticket-message-create", args=[ticket.pk]),
            {
                "message_type": Message.TYPE_PUBLIC,
                "channel": Message.CHANNEL_PORTAL,
                "content": "Tentative auditeur",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(Message.objects.filter(ticket=ticket, content="Tentative auditeur").exists())

    def test_client_cannot_patch_ticket_directly(self):
        ticket = Ticket.objects.create(
            client=self.client_user,
            product=self.product,
            title="Ticket verrouille",
            description="Le client ne doit pas modifier le workflow.",
            category=Ticket.CATEGORY_BREAKDOWN,
            status=Ticket.STATUS_NEW,
            priority=Ticket.PRIORITY_NORMAL,
        )
        self.api.force_authenticate(user=self.client_user)

        response = self.api.patch(
            reverse("sav_api:ticket-detail", args=[ticket.pk]),
            {"status": Ticket.STATUS_CLOSED},
            format="json",
        )

        self.assertEqual(response.status_code, 403)

    def test_client_does_not_see_internal_messages_in_ticket_payload(self):
        ticket = Ticket.objects.create(
            client=self.client_user,
            product=self.product,
            title="Ticket avec note interne",
            description="Le client ne doit pas voir la note interne.",
            category=Ticket.CATEGORY_BREAKDOWN,
            status=Ticket.STATUS_IN_PROGRESS,
            priority=Ticket.PRIORITY_NORMAL,
            assigned_agent=self.agent,
        )
        Message.objects.create(
            ticket=ticket,
            sender=self.agent,
            message_type=Message.TYPE_INTERNAL,
            channel=Message.CHANNEL_PORTAL,
            direction=Message.DIRECTION_INTERNAL,
            content="Note interne reservee a l'equipe.",
        )
        Message.objects.create(
            ticket=ticket,
            sender=self.agent,
            message_type=Message.TYPE_PUBLIC,
            channel=Message.CHANNEL_PORTAL,
            direction=Message.DIRECTION_OUTBOUND,
            content="Mise a jour visible client.",
        )
        self.api.force_authenticate(user=self.client_user)

        response = self.api.get(reverse("sav_api:ticket-detail", args=[ticket.pk]))

        self.assertEqual(response.status_code, 200)
        contents = [item["content"] for item in response.data["messages"]]
        self.assertEqual(contents, ["Mise a jour visible client."])

    def test_client_can_submit_feedback_after_resolution(self):
        ticket = Ticket.objects.create(
            client=self.client_user,
            product=self.product,
            title="Ticket a noter",
            description="Le support est termine.",
            category=Ticket.CATEGORY_BREAKDOWN,
            status=Ticket.STATUS_CLOSED,
            priority=Ticket.PRIORITY_NORMAL,
            closed_at=timezone.now(),
        )
        self.api.force_authenticate(user=self.client_user)

        response = self.api.post(
            reverse("sav_api:ticket-feedback-list"),
            {"ticket": ticket.id, "rating": 4, "comment": "Support clair et rapide."},
        )

        self.assertEqual(response.status_code, 201)
        self.assertTrue(TicketFeedback.objects.filter(ticket=ticket, rating=4).exists())

    def test_public_registration_endpoint_creates_client_account(self):
        response = self.client.post(
            reverse("sav_api:public-register"),
            json.dumps(
                {
                    "organization": self.organization.id,
                    "first_name": "Nadia",
                    "last_name": "Client",
                    "email": "nadia@example.com",
                    "phone": "+237677000001",
                    "company_name": "Habitat Client",
                    "password": "ClientPass123!",
                    "password_confirm": "ClientPass123!",
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertTrue(User.objects.filter(email="nadia@example.com", role=User.ROLE_CLIENT).exists())

    def test_web_login_accepts_email_identifier(self):
        user = User.objects.create_user(
            username="email_client",
            email="email.client@example.com",
            password="ClientPass123!",
            organization=self.organization,
            role=User.ROLE_CLIENT,
        )

        response = self.client.post(
            reverse("login"),
            {"username": user.email, "password": "ClientPass123!"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/dashboard/")

    def test_logout_redirects_to_login_page(self):
        self.client.force_login(self.client_user)

        response = self.client.post(reverse("logout"))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/login/")

    def test_analytics_redirects_to_custom_login_url(self):
        response = self.client.get(reverse("analytics-page"))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/login/?next=/analytics/")

    def test_client_can_create_ticket_via_web_portal(self):
        self.client.force_login(self.client_user)

        response = self.client.post(
            reverse("ticket-create"),
            {
                "product_label": "Split mural 12000 BTU",
                "title": "Demande portail web",
                "description": "Le client cree un ticket depuis le portail.",
                "category": Ticket.CATEGORY_BREAKDOWN,
                "channel": Ticket.CHANNEL_WEB,
                "priority": Ticket.PRIORITY_NORMAL,
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            Ticket.objects.filter(
                title="Demande portail web",
                client=self.client_user,
                product_label="Split mural 12000 BTU",
            ).exists()
        )

    def test_ticket_create_form_shows_client_field_for_client_user(self):
        form = TicketCreateForm(user=self.client_user)

        self.assertNotIsInstance(form.fields["client"].widget, HiddenInput)
        self.assertQuerySetEqual(form.fields["client"].queryset, [self.client_user], transform=lambda user: user)
        self.assertEqual(form.fields["client"].initial, self.client_user)
        self.assertFalse(form.fields["client"].required)

    def test_ticket_create_form_uses_inline_client_fields_for_internal_user(self):
        form = TicketCreateForm(user=self.manager)

        self.assertEqual(form.fields["client_mode"].initial, TicketCreateForm.CLIENT_MODE_EXISTING)
        self.assertNotIsInstance(form.fields["client_mode"].widget, HiddenInput)
        self.assertNotIsInstance(form.fields["client"].widget, HiddenInput)
        self.assertFalse(form.fields["client"].required)
        self.assertNotIsInstance(form.fields["client_name"].widget, HiddenInput)
        self.assertNotIsInstance(form.fields["client_email"].widget, HiddenInput)
        self.assertNotIsInstance(form.fields["client_password1"].widget, HiddenInput)
        self.assertNotIsInstance(form.fields["client_password2"].widget, HiddenInput)

    def test_internal_user_can_create_ticket_for_existing_client(self):
        self.client.force_login(self.manager)

        response = self.client.post(
            reverse("ticket-create"),
            {
                "client_mode": TicketCreateForm.CLIENT_MODE_EXISTING,
                "client": self.client_user.pk,
                "product_label": "Serveur ondule",
                "title": "Ticket pour client existant",
                "description": "Creation de ticket sans recrer le client.",
                "category": Ticket.CATEGORY_MAINTENANCE,
                "channel": Ticket.CHANNEL_PHONE,
                "status": Ticket.STATUS_NEW,
                "priority": Ticket.PRIORITY_NORMAL,
            },
        )

        self.assertEqual(response.status_code, 302)
        created_ticket = Ticket.objects.get(title="Ticket pour client existant")
        self.assertEqual(created_ticket.client, self.client_user)

    def test_internal_user_can_create_ticket_and_client_in_one_flow(self):
        self.client.force_login(self.manager)

        response = self.client.post(
            reverse("ticket-create"),
            {
                "client_mode": TicketCreateForm.CLIENT_MODE_NEW,
                "client_name": "Mireille Ndjana",
                "client_email": "mireille.ndjana@example.com",
                "client_password1": "ClientPass123!",
                "client_password2": "ClientPass123!",
                "product_label": "Groupe electrogene 40kVA",
                "title": "Creation combinee ticket client",
                "description": "Le ticket cree aussi le compte client.",
                "category": Ticket.CATEGORY_BREAKDOWN,
                "channel": Ticket.CHANNEL_PHONE,
                "status": Ticket.STATUS_NEW,
                "priority": Ticket.PRIORITY_HIGH,
            },
        )

        self.assertEqual(response.status_code, 302)
        created_client = User.objects.get(email="mireille.ndjana@example.com")
        self.assertEqual(created_client.role, User.ROLE_CLIENT)
        self.assertEqual(created_client.organization, self.organization)
        self.assertTrue(created_client.check_password("ClientPass123!"))

        created_ticket = Ticket.objects.get(title="Creation combinee ticket client")
        self.assertEqual(created_ticket.client, created_client)
        self.assertEqual(created_ticket.product_label, "Groupe electrogene 40kVA")

    def test_client_can_create_ticket_via_web_portal_with_attachment(self):
        self.client.force_login(self.client_user)
        uploaded = SimpleUploadedFile("capture.png", b"fake-image-content", content_type="image/png")

        response = self.client.post(
            reverse("ticket-create"),
            {
                "product_label": "Imprimante reseau bureau direction",
                "title": "Ticket avec preuve initiale",
                "description": "Le client cree un ticket avec une capture des la creation.",
                "category": Ticket.CATEGORY_BREAKDOWN,
                "channel": Ticket.CHANNEL_WEB,
                "priority": Ticket.PRIORITY_NORMAL,
                "initial_attachments": uploaded,
            },
        )

        self.assertEqual(response.status_code, 302)
        created_ticket = Ticket.objects.get(title="Ticket avec preuve initiale")
        self.assertEqual(created_ticket.product_label, "Imprimante reseau bureau direction")
        self.assertTrue(TicketAttachment.objects.filter(ticket=created_ticket, uploaded_by=self.client_user).exists())

    def test_support_page_renders_for_client(self):
        self.client.force_login(self.client_user)

        response = self.client.get(reverse("support-page"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "sav/support.html")

    def test_field_technician_can_access_operational_workspace(self):
        self.client.force_login(self.field_technician)

        response = self.client.get(reverse("technician-space"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "sav/technician_space.html")

    def test_internal_user_can_create_client_from_register_page(self):
        self.client.force_login(self.manager)

        response = self.client.post(
            reverse("register"),
            {
                "organization": self.organization.id,
                "first_name": "Rita",
                "last_name": "Nouveau",
                "email": "rita.nouveau@example.com",
                "phone": "+237699000111",
                "company_name": "Rita SARL",
                "client_type": "enterprise",
                "sector": "Distribution",
                "tax_identifier": "RC-7788",
                "address": "Douala",
                "password1": "ClientPass123!",
                "password2": "ClientPass123!",
            },
        )

        self.assertRedirects(response, reverse("dashboard"))
        self.assertTrue(User.objects.filter(email="rita.nouveau@example.com", role=User.ROLE_CLIENT).exists())

    def test_planning_page_renders_for_manager(self):
        self.client.force_login(self.manager)

        response = self.client.get(reverse("planning-page"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "sav/planning.html")

    def test_dispatcher_can_access_planning_api_for_operational_profiles(self):
        self.api.force_authenticate(user=self.dispatcher)

        response = self.api.get(reverse("sav_api:technician-planning", args=[self.technician.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["technician_id"], self.technician.pk)

    def test_administration_page_renders_for_admin(self):
        admin_user = User.objects.create_user(
            username="admin_local",
            password="secret123",
            organization=self.organization,
            role=User.ROLE_ADMIN,
            is_staff=True,
        )
        self.client.force_login(admin_user)

        response = self.client.get(reverse("administration-page"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "sav/administration.html")

    def test_admin_role_automatically_gets_django_admin_staff_access(self):
        admin_user = User.objects.create_user(
            username="admin_auto_staff",
            password="secret123",
            organization=self.organization,
            role=User.ROLE_ADMIN,
        )

        self.assertTrue(admin_user.is_staff)
        self.assertFalse(admin_user.is_superuser)
        self.assertTrue(self.client.login(username="admin_auto_staff", password="secret123"))

        response = self.client.get("/admin/")

        self.assertEqual(response.status_code, 200)

    def test_admin_can_open_product_create_page(self):
        admin_user = User.objects.create_user(
            username="admin_product",
            password="secret123",
            organization=self.organization,
            role=User.ROLE_ADMIN,
            is_staff=True,
        )
        self.client.force_login(admin_user)

        response = self.client.get(reverse("product-create"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "sav/product_form.html")
        self.assertContains(response, "Ajouter un produit")

    def test_admin_can_create_product_via_web_portal(self):
        admin_user = User.objects.create_user(
            username="admin_product_create",
            password="secret123",
            organization=self.organization,
            role=User.ROLE_ADMIN,
            is_staff=True,
        )
        self.client.force_login(admin_user)

        response = self.client.post(
            reverse("product-create"),
            {
                "client": self.client_user.pk,
                "equipment_category": self.category.pk,
                "name": "HP Color LaserJet",
                "sku": "HP-COLOR-01",
                "serial_number": "HP-PORTAL-0001",
                "equipment_type": "printer",
                "brand": "HP",
                "model_reference": "Color LaserJet Pro",
                "status": Product.STATUS_ACTIVE,
                "health_score": 96,
                "counter_total": 0,
                "counter_color": 0,
                "counter_bw": 0,
                "iot_enabled": "on",
                "installation_address": "Douala",
                "detailed_location": "Plateau technique",
                "contract_reference": "CTR-2026-001",
                "notes": "Produit cree depuis le portail admin.",
            },
        )

        self.assertEqual(response.status_code, 302)
        created = Product.objects.get(serial_number="HP-PORTAL-0001")
        self.assertEqual(created.client, self.client_user)
        self.assertEqual(created.organization, self.organization)
        self.assertEqual(created.equipment_category, self.category)
        self.assertTrue(AuditLog.objects.filter(action="product_created_web", target_id=created.pk).exists())

    def test_admin_can_update_product_via_web_portal(self):
        admin_user = User.objects.create_user(
            username="admin_product_update",
            password="secret123",
            organization=self.organization,
            role=User.ROLE_ADMIN,
            is_staff=True,
        )
        self.client.force_login(admin_user)

        response = self.client.post(
            reverse("product-update", args=[self.product.pk]),
            {
                "client": self.client_user.pk,
                "equipment_category": self.category.pk,
                "name": "Onduleur 5kVA Revise",
                "sku": "AFR-OND-5KVA",
                "serial_number": self.product.serial_number,
                "equipment_type": "other",
                "brand": "Afrilux",
                "model_reference": "Revision 2026",
                "status": Product.STATUS_IN_SERVICE,
                "health_score": 88,
                "counter_total": 145,
                "counter_color": 23,
                "counter_bw": 122,
                "installation_address": "Douala",
                "detailed_location": "Salle technique B",
                "contract_reference": "CTR-REV-01",
                "notes": "Mise a jour depuis le portail admin.",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.product.refresh_from_db()
        self.assertEqual(self.product.name, "Onduleur 5kVA Revise")
        self.assertEqual(self.product.status, Product.STATUS_IN_SERVICE)
        self.assertEqual(self.product.health_score, 88)
        self.assertTrue(AuditLog.objects.filter(action="product_updated_web", target_id=self.product.pk).exists())

    def test_admin_can_delete_product_via_web_portal(self):
        admin_user = User.objects.create_user(
            username="admin_product_delete",
            password="secret123",
            organization=self.organization,
            role=User.ROLE_ADMIN,
            is_staff=True,
        )
        product = Product.objects.create(
            client=self.client_user,
            equipment_category=self.category,
            name="Produit a supprimer",
            serial_number="AFR-DELETE-0001",
        )
        self.client.force_login(admin_user)

        response = self.client.post(reverse("product-delete", args=[product.pk]))

        self.assertEqual(response.status_code, 302)
        self.assertFalse(Product.objects.filter(pk=product.pk).exists())
        self.assertTrue(AuditLog.objects.filter(action="product_deleted_web", target_reference__icontains="AFR-DELETE-0001").exists())

    def test_non_admin_cannot_access_product_create_page(self):
        self.client.force_login(self.manager)

        response = self.client.get(reverse("product-create"))

        self.assertEqual(response.status_code, 403)

    def test_non_admin_cannot_access_product_update_or_delete_pages(self):
        self.client.force_login(self.manager)

        update_response = self.client.get(reverse("product-update", args=[self.product.pk]))
        delete_response = self.client.get(reverse("product-delete", args=[self.product.pk]))

        self.assertEqual(update_response.status_code, 403)
        self.assertEqual(delete_response.status_code, 403)

    @override_settings(
        INBOUND_EMAIL_IMAP_HOST="imap.test.local",
        INBOUND_EMAIL_IMAP_PORT=993,
        INBOUND_EMAIL_IMAP_USER="support@test.local",
        INBOUND_EMAIL_IMAP_PASSWORD="secret",
        INBOUND_EMAIL_IMAP_USE_SSL=True,
        INBOUND_EMAIL_IMAP_MAILBOX="INBOX",
        INBOUND_EMAIL_IMAP_SEARCH="UNSEEN",
    )
    def test_fetch_inbound_emails_command_creates_ticket_and_attachment(self):
        email_message = EmailMessage()
        email_message["From"] = "mail.client@example.com"
        email_message["To"] = self.organization.support_email
        email_message["Subject"] = "Panne urgente"
        email_message.set_content("Bonjour, voici une capture de l'incident.")
        email_message.add_attachment(
            b"fake-png",
            maintype="image",
            subtype="png",
            filename="capture-incident.png",
        )
        raw_message = email_message.as_bytes()

        class FakeIMAPClient:
            def __init__(self, message_bytes):
                self.message_bytes = message_bytes
                self.stored_flags = []

            def login(self, username, password):
                return "OK", [b""]

            def select(self, mailbox):
                return "OK", [b"1"]

            def search(self, charset, query):
                return "OK", [b"1"]

            def fetch(self, message_id, query):
                return "OK", [(b"1 (RFC822)", self.message_bytes)]

            def store(self, message_id, operation, flags):
                self.stored_flags.append((message_id, operation, flags))
                return "OK", [b""]

            def logout(self):
                return "BYE", [b""]

        fake_client = FakeIMAPClient(raw_message)

        with patch("sav.management.commands.fetch_inbound_emails.imaplib.IMAP4_SSL", return_value=fake_client):
            output = io.StringIO()
            call_command("fetch_inbound_emails", stdout=output)

        created_ticket = Ticket.objects.get(title__icontains="Panne urgente")
        self.assertEqual(created_ticket.channel, Ticket.CHANNEL_EMAIL)
        self.assertTrue(
            TicketAttachment.objects.filter(ticket=created_ticket, original_name="capture-incident.png").exists()
        )
        self.assertTrue(fake_client.stored_flags)

    def test_custom_sla_rule_applies_on_ticket_creation(self):
        SlaRule.objects.create(
            organization=self.organization,
            priority=Ticket.PRIORITY_NORMAL,
            response_deadline_minutes=180,
            resolution_deadline_hours=12,
            is_active=True,
        )

        response = self.api.post(
            reverse("sav_api:ticket-list"),
            {
                "client": self.client_user.id,
                "product": self.product.id,
                "title": "Ticket avec SLA personnalise",
                "description": "Verifier l'application de la regle SLA de l'organisation.",
                "category": Ticket.CATEGORY_BREAKDOWN,
                "channel": Ticket.CHANNEL_WEB,
                "priority": Ticket.PRIORITY_NORMAL,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        ticket = Ticket.objects.get(title="Ticket avec SLA personnalise")
        self.assertIsNotNone(ticket.sla_deadline)
        delta_hours = (ticket.sla_deadline - ticket.created_at).total_seconds() / 3600
        self.assertGreaterEqual(delta_hours, 11.9)

    def test_assign_action_creates_assignment_history_and_intervention(self):
        ticket = Ticket.objects.create(
            client=self.client_user,
            product=self.product,
            title="Affectation terrain",
            description="Le dossier doit generer un bon d'intervention.",
            category=Ticket.CATEGORY_BREAKDOWN,
            status=Ticket.STATUS_NEW,
            priority=Ticket.PRIORITY_HIGH,
        )

        response = self.api.post(
            reverse("sav_api:ticket-assign", args=[ticket.pk]),
            {"technician": self.agent.pk},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        ticket.refresh_from_db()
        self.assertEqual(ticket.assigned_agent, self.agent)
        self.assertTrue(TicketAssignment.objects.filter(ticket=ticket, technician=self.agent).exists())
        intervention = ticket.interventions.get(agent=self.agent)
        self.assertTrue(bool(intervention.report_pdf))

    def test_report_export_archives_generated_report(self):
        response = self.api.get(reverse("sav_api:report-export", args=["journalier"]) + "?format=pdf")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            GeneratedReport.objects.filter(
                organization=self.organization,
                report_type=GeneratedReport.TYPE_DAILY,
                export_format=GeneratedReport.FORMAT_PDF,
            ).exists()
        )

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_send_scheduled_reports_command_archives_pdf(self):
        self.organization.reporting_emails = "sav-manager@test.local"
        self.organization.save(update_fields=["reporting_emails"])

        output = io.StringIO()
        call_command(
            "send_scheduled_reports",
            "--report-type",
            "journalier",
            "--date",
            timezone.localdate().isoformat(),
            "--organization-slug",
            self.organization.slug,
            stdout=output,
        )

        self.assertTrue(
            GeneratedReport.objects.filter(
                organization=self.organization,
                report_type=GeneratedReport.TYPE_DAILY,
                export_format=GeneratedReport.FORMAT_PDF,
                sent_to__icontains="sav-manager@test.local",
            ).exists()
        )

    def test_purge_demo_data_removes_tmp_placeholder_sets(self):
        tmp_org = Organization.objects.create(name="Tmp Org Sandbox", slug="tmp-org-sandbox")
        tmp_client = User.objects.create_user(
            username="tmp_client_sandbox",
            password="secret123",
            organization=tmp_org,
            role=User.ROLE_CLIENT,
            company_name="Tmp Org Sandbox",
        )
        tmp_ticket = Ticket.objects.create(
            client=tmp_client,
            title="Ticket temporaire",
            description="Donnee de travail a supprimer.",
            category=Ticket.CATEGORY_BREAKDOWN,
            priority=Ticket.PRIORITY_NORMAL,
        )

        call_command("purge_demo_data", "--execute")

        self.assertFalse(Organization.objects.filter(pk=tmp_org.pk).exists())
        self.assertFalse(User.objects.filter(pk=tmp_client.pk).exists())
        self.assertFalse(Ticket.objects.filter(pk=tmp_ticket.pk).exists())

    def test_bootstrap_platform_creates_admin_and_default_categories(self):
        call_command(
            "bootstrap_platform",
            "--organization-name",
            "AFRILUX SMART SOLUTIONS",
            "--organization-slug",
            "afrilux-smart-bootstrap",
            "--support-email",
            "sav@test.local",
            "--support-phone",
            "+237600000000",
            "--city",
            "Douala",
            "--country",
            "Cameroun",
            "--admin-username",
            "bootstrap_admin",
            "--admin-email",
            "bootstrap-admin@test.local",
            "--admin-password",
            "secret123",
        )

        organization = Organization.objects.get(slug="afrilux-smart-bootstrap")
        admin = User.objects.get(username="bootstrap_admin")

        self.assertEqual(admin.organization, organization)
        self.assertEqual(admin.role, User.ROLE_ADMIN)
        self.assertTrue(admin.is_superuser)
        self.assertTrue(SlaRule.objects.filter(organization=organization).exists())
        self.assertTrue(organization.equipment_categories.exists())

    def test_run_sav_automation_auto_closes_resolved_ticket_after_72h(self):
        ticket = Ticket.objects.create(
            client=self.client_user,
            product=self.product,
            title="Resolution ancienne",
            description="Doit etre auto-cloturee apres 72h.",
            category=Ticket.CATEGORY_BREAKDOWN,
            status=Ticket.STATUS_RESOLVED,
            priority=Ticket.PRIORITY_NORMAL,
            resolved_at=timezone.now() - timedelta(hours=80),
        )

        output = io.StringIO()
        call_command(
            "run_sav_automation",
            "--organization-slug",
            self.organization.slug,
            "--skip-reports",
            stdout=output,
        )

        ticket.refresh_from_db()
        self.assertEqual(ticket.status, Ticket.STATUS_CLOSED)

    def test_platform_scheduler_once_executes_cycle(self):
        output = io.StringIO()

        call_command(
            "run_platform_scheduler",
            "--once",
            "--organization-slug",
            self.organization.slug,
            stdout=output,
        )

        self.assertIn("Cycle unique execute.", output.getvalue())

    def test_api_v1_alias_exposes_dashboard(self):
        response = self.api.get("/api/v1/dashboard/")

        self.assertEqual(response.status_code, 200)
