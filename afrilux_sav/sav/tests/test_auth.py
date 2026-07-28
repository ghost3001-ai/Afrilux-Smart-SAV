import json

from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from .base import *

from ..models import FinancialTransaction, User


class AuthTests(SavPlatformTests):
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

    def test_public_registration_requires_company_for_enterprise_client_type(self):
        response = self.client.post(
            reverse("sav_api:public-register"),
            json.dumps(
                {
                    "organization": self.organization.id,
                    "first_name": "Client",
                    "last_name": "Entreprise",
                    "email": "client.entreprise@example.com",
                    "phone": "+237677000101",
                    "client_type": "enterprise",
                    "company_name": "",
                    "password": "ClientPass123!",
                    "password_confirm": "ClientPass123!",
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("company_name", response.json())

    def test_public_registration_clears_company_for_non_enterprise_types(self):
        response = self.client.post(
            reverse("sav_api:public-register"),
            json.dumps(
                {
                    "organization": self.organization.id,
                    "first_name": "Client",
                    "last_name": "Particulier",
                    "email": "client.particulier@example.com",
                    "phone": "+237677000102",
                    "client_type": "individual",
                    "company_name": "Ne doit pas etre conserve",
                    "password": "ClientPass123!",
                    "password_confirm": "ClientPass123!",
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        created = User.objects.get(email="client.particulier@example.com")
        self.assertEqual(created.client_type, "individual")
        self.assertEqual(created.company_name, "")

    def test_public_registration_existing_email_returns_validation_error(self):
        response = self.client.post(
            reverse("sav_api:public-register"),
            json.dumps(
                {
                    "organization": self.organization.id,
                    "first_name": "Client",
                    "last_name": "Existant",
                    "email": self.client_user.email,
                    "phone": "+237677000103",
                    "client_type": "individual",
                    "password": "ClientPass123!",
                    "password_confirm": "ClientPass123!",
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("email", response.json())

    def test_manager_can_create_individual_client_via_api(self):
        self.api.force_authenticate(user=self.manager)

        response = self.api.post(
            reverse("sav_api:client-list"),
            {
                "organization": self.organization.id,
                "first_name": "API",
                "last_name": "Particulier",
                "email": "api.particulier@example.com",
                "password": "ClientPass123!",
                "client_type": "individual",
                "company_name": "Ne doit pas rester",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        created = User.objects.get(email="api.particulier@example.com")
        self.assertEqual(created.role, User.ROLE_CLIENT)
        self.assertEqual(created.client_type, "individual")
        self.assertEqual(created.company_name, "")

    def test_manager_client_creation_rejects_duplicate_email(self):
        self.api.force_authenticate(user=self.manager)

        response = self.api.post(
            reverse("sav_api:client-list"),
            {
                "organization": self.organization.id,
                "first_name": "Doublon",
                "last_name": "Client",
                "email": self.client_user.email,
                "password": "ClientPass123!",
                "client_type": "individual",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("email", response.data)

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
        self.assertEqual(response.url, "/workspace/")

    def test_workspace_redirects_client_to_support_page(self):
        self.client.force_login(self.client_user)

        response = self.client.get(reverse("workspace"))

        self.assertRedirects(response, reverse("support-page"))

    def test_workspace_redirects_dispatcher_to_ticket_list_with_mine_filter(self):
        self.client.force_login(self.dispatcher)

        response = self.client.get(reverse("workspace"))

        self.assertRedirects(response, f"{reverse('ticket-list')}?assignment=mine")

    def test_workspace_redirects_support_to_ticket_list_with_mine_filter(self):
        self.client.force_login(self.agent)

        response = self.client.get(reverse("workspace"))

        self.assertRedirects(response, f"{reverse('ticket-list')}?assignment=mine")

    def test_logout_redirects_to_login_page(self):
        self.client.force_login(self.client_user)

        response = self.client.post(reverse("logout"))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/login/")

    def test_analytics_redirects_to_custom_login_url(self):
        response = self.client.get(reverse("analytics-page"))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/login/?next=/analytics/")

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
