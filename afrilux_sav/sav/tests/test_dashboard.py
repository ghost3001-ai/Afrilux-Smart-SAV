from datetime import timedelta

from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from .base import *

from ..models import PredictiveAlert, Ticket


class DashboardTests(SavPlatformTests):
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

    def test_dashboard_returns_resolution_and_agent_metrics(self):
        ticket = Ticket.objects.create(
            client=self.client_user,
            product=self.product,
            assigned_agent=self.agent,
            title="Bug cloture",
            description="Incident logiciel resolu.",
            category=Ticket.CATEGORY_BUG,
            status=Ticket.STATUS_RESOLVED,
            priority=Ticket.PRIORITY_HIGH,
        )
        Ticket.objects.filter(pk=ticket.pk).update(created_at=timezone.now() - timedelta(hours=6))

        response = self.api.get(reverse("sav_api:dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["bug_total"], 1)
        self.assertEqual(response.data["maintenance_total"], 0)
        self.assertAlmostEqual(response.data["average_resolution_hours"], 6.0, places=1)
        self.assertEqual(response.data["top_agents"][0]["agent_name"], str(self.agent))

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

    def test_dashboard_web_page_renders_for_manager(self):
        self.client.force_login(self.manager)

        response = self.client.get(reverse("dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "sav/dashboard.html")

    def test_dashboard_counts_only_operational_profiles_in_status_breakdown(self):
        response = self.api.get(reverse("sav_api:dashboard"))

        self.assertEqual(response.status_code, 200)
        technician_rows = {row["status"]: row["total"] for row in response.data["technician_status_breakdown"]}
        self.assertEqual(sum(technician_rows.values()), 3)
        self.assertEqual(technician_rows["available"], 3)

    def test_dashboard_only_returns_same_organization_metrics(self):
        Ticket.objects.create(
            client=self.client_user,
            product=self.product,
            title="Ticket organisation A",
            description="Visible pour le manager A.",
            category=Ticket.CATEGORY_MAINTENANCE,
            status=Ticket.STATUS_NEW,
            priority=Ticket.PRIORITY_HIGH,
        )
        Ticket.objects.create(
            client=self.other_client,
            product=self.other_product,
            title="Ticket organisation B",
            description="Ne doit pas etre visible pour le manager A.",
            category=Ticket.CATEGORY_MAINTENANCE,
            status=Ticket.STATUS_NEW,
            priority=Ticket.PRIORITY_HIGH,
        )

        response = self.api.get(reverse("sav_api:dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["tickets_total"], 1)
        self.assertEqual(response.data["maintenance_total"], 1)
        self.assertEqual(response.data["organization_name"], self.organization.display_name)

    def test_api_v1_alias_exposes_dashboard(self):
        response = self.api.get("/api/v1/dashboard/")

        self.assertEqual(response.status_code, 200)
