from .base import *


class FinancialTests(SavPlatformTests):
    def test_admin_can_credit_account_via_api(self):
        admin_user = User.objects.create_user(
            username="admin_credit",
            password="secret123",
            organization=self.organization,
            role=User.ROLE_ADMIN,
            is_staff=True,
        )
        self.api.force_authenticate(user=admin_user)
        ticket = Ticket.objects.create(
            client=self.client_user,
            product=self.product,
            title="Demande geste commercial",
            description="Le client demande un credit sur son compte.",
            category=Ticket.CATEGORY_BREAKDOWN,
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
        self.assertEqual(credit.executed_by, admin_user)
        self.assertTrue(WorkflowExecution.objects.filter(ticket=ticket, trigger_event="account_credit").exists())
        self.assertTrue(
            Notification.objects.filter(ticket=ticket, recipient=self.client_user, event_type="account_credit").exists()
        )
        self.assertTrue(
            Message.objects.filter(ticket=ticket, direction=Message.DIRECTION_OUTBOUND, content__icontains="15000.00").exists()
        )

    def test_support_cannot_credit_account_via_api(self):
        ticket = Ticket.objects.create(
            client=self.client_user,
            product=self.product,
            title="Demande geste commercial",
            description="Le credit compte est reserve a l'administrateur.",
            category=Ticket.CATEGORY_BREAKDOWN,
            status=Ticket.STATUS_IN_PROGRESS,
            priority=Ticket.PRIORITY_HIGH,
        )

        response = self.api.post(
            reverse("sav_api:ticket-credit-account", args=[ticket.pk]),
            {
                "amount": "15000.00",
                "currency": "XAF",
                "reason": "Geste commercial SAV",
                "note": "Credit demande par le support.",
            },
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(AccountCredit.objects.filter(ticket=ticket).exists())

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
