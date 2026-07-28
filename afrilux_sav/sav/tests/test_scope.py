from unittest.mock import patch

from .base import *


class ScopeTests(SavPlatformTests):
    def test_public_health_endpoint_returns_ok(self):
        response = self.client.get(reverse("sav_api:health"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")
        self.assertEqual(response.json()["database"], "ok")
        self.assertEqual(response.json()["cache"], "ok")

    @override_settings(SAV_REALTIME_STREAM_SECONDS=10, SAV_REALTIME_POLL_SECONDS=1)
    def test_realtime_events_stream_is_short_lived_with_heartbeat(self):
        self.client.force_login(self.manager)

        with patch("time.monotonic", side_effect=[0, 0, 11]), patch("time.sleep"):
            response = self.client.get(reverse("realtime-events"))
            content = b"".join(response.streaming_content).decode()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/event-stream")
        self.assertIn("retry: 3000", content)
        self.assertIn("event: connected", content)
        self.assertIn("event: heartbeat", content)

    def test_api_docs_page_renders(self):
        response = self.client.get(reverse("api-docs"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Documentation rapide")

    def test_local_static_asset_is_served(self):
        response = self.client.get("/static/sav/styles.css")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "body[data-theme=\"dark\"]")

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

    def test_agency_scope_limits_responsable_to_own_zone(self):
        douala = Agency.objects.create(organization=self.organization, name="Agence Douala", city="Douala")
        garoua = Agency.objects.create(organization=self.organization, name="Agence Garoua", city="Garoua")
        self.manager.agency = douala
        self.manager.save(update_fields=["agency"])
        self.client_user.agency = douala
        self.client_user.save(update_fields=["agency"])
        garoua_client = User.objects.create_user(
            username="client_garoua",
            password="secret123",
            organization=self.organization,
            agency=garoua,
            role=User.ROLE_CLIENT,
            company_name="Client Garoua",
        )
        garoua_product = Product.objects.create(
            client=garoua_client,
            name="Climatiseur agence nord",
            sku="GAR-CLIM",
            serial_number="GAR-0001",
        )
        douala_ticket = Ticket.objects.create(
            client=self.client_user,
            product=self.product,
            title="Ticket Douala",
            description="Visible par le responsable Douala.",
            priority=Ticket.PRIORITY_NORMAL,
        )
        Ticket.objects.create(
            client=garoua_client,
            product=garoua_product,
            title="Ticket Garoua",
            description="Ne doit pas apparaitre dans le scope Douala.",
            priority=Ticket.PRIORITY_NORMAL,
        )

        response = self.api.get(reverse("sav_api:ticket-list"))

        self.assertEqual(response.status_code, 200)
        payload = response.data["results"] if isinstance(response.data, dict) and "results" in response.data else response.data
        references = {item["reference"] for item in payload}
        self.assertIn(douala_ticket.reference, references)
        self.assertNotIn("Ticket Garoua", {item["title"] for item in payload})
