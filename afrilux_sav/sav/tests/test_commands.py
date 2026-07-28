from .base import *


class CommandTests(SavPlatformTests):
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

    def test_dispatch_due_reports_returns_send_failed_when_smtp_breaks(self):
        self.organization.reporting_emails = "sav-manager@test.local"
        self.organization.save(update_fields=["reporting_emails"])

        with patch("sav.services.send_report_to_recipients", side_effect=RuntimeError("SMTP indisponible")):
            results = dispatch_due_reports(
                organization=self.organization,
                now=timezone.now(),
                report_types=["journalier"],
            )

        self.assertEqual(results[0]["status"], "send_failed")
        self.assertIn("SMTP indisponible", results[0]["error"])
        self.assertFalse(
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
            "--skip-reports",
            "--organization-slug",
            self.organization.slug,
            stdout=output,
        )

        self.assertIn("Cycle unique execute.", output.getvalue())

    def test_platform_scheduler_once_accepts_skip_reports_option(self):
        output = io.StringIO()

        call_command(
            "run_platform_scheduler",
            "--once",
            "--skip-backup",
            "--skip-reports",
            "--organization-slug",
            self.organization.slug,
            stdout=output,
        )

        self.assertIn("Cycle unique execute.", output.getvalue())
