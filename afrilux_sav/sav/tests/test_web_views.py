from .base import *


class WebViewTests(SavPlatformTests):
    def test_field_technician_can_access_operational_workspace(self):
        self.client.force_login(self.field_technician)

        response = self.client.get(reverse("technician-space"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "sav/technician_space.html")

    def test_technician_can_open_ticket_from_today_intervention(self):
        ticket = Ticket.objects.create(
            client=self.client_user,
            product=self.product,
            assigned_agent=self.agent,
            title="Intervention du jour",
            description="Le technicien doit pouvoir ouvrir le dossier depuis son espace.",
            category=Ticket.CATEGORY_BREAKDOWN,
            status=Ticket.STATUS_INTERVENTION_PLANNED,
            priority=Ticket.PRIORITY_HIGH,
        )
        Intervention.objects.create(
            ticket=ticket,
            organization=self.organization,
            agent=self.technician,
            intervention_type=Intervention.TYPE_ON_SITE,
            status=Intervention.STATUS_PLANNED,
            scheduled_for=timezone.now(),
            location_snapshot="Douala",
        )
        self.client.force_login(self.technician)

        workspace_response = self.client.get(reverse("technician-space"))
        detail_response = self.client.get(reverse("ticket-detail", args=[ticket.pk]))

        self.assertEqual(workspace_response.status_code, 200)
        self.assertContains(workspace_response, reverse("ticket-detail", args=[ticket.pk]))
        self.assertEqual(detail_response.status_code, 200)

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

    def test_register_page_renders_for_anonymous_user(self):
        response = self.client.get(reverse("register"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "data-client-registration")
        self.assertContains(response, "data-company-field")
        self.assertContains(response, "field--hidden")

    def test_anonymous_user_can_create_client_from_register_page(self):
        response = self.client.post(
            reverse("register"),
            {
                "organization": self.organization.id,
                "first_name": "Aline",
                "last_name": "Client",
                "email": "aline.client@example.com",
                "phone": "+237699000222",
                "client_type": "individual",
                "company_name": "",
                "sector": "Services",
                "tax_identifier": "",
                "address": "Douala",
                "password1": "ClientPass123!",
                "password2": "ClientPass123!",
            },
        )

        self.assertRedirects(response, reverse("support-page"))
        created = User.objects.get(email="aline.client@example.com")
        self.assertEqual(created.role, User.ROLE_CLIENT)
        self.assertEqual(int(self.client.session["_auth_user_id"]), created.id)

    def test_register_page_existing_email_returns_form_error(self):
        response = self.client.post(
            reverse("register"),
            {
                "organization": self.organization.id,
                "first_name": "Client",
                "last_name": "Existant",
                "email": self.client_user.email,
                "phone": "+237699000333",
                "client_type": "individual",
                "company_name": "",
                "sector": "",
                "tax_identifier": "",
                "address": "Douala",
                "password1": "ClientPass123!",
                "password2": "ClientPass123!",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Un compte client existe deja avec cet email")

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

    def test_offline_sync_operation_can_be_queued_by_mobile_client(self):
        self.api.force_authenticate(user=self.technician)

        response = self.api.post(
            reverse("sav_api:offline-sync-list"),
            {
                "endpoint": "/api/maintenance/tickets/42/cloturer/",
                "method": OfflineSyncOperation.METHOD_POST,
                "payload": {
                    "observations": "Rapport saisi hors ligne.",
                    "final_status": MaintenanceTicket.STATUS_DONE,
                },
                "client_created_at": timezone.now().isoformat(),
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        operation = OfflineSyncOperation.objects.get(endpoint="/api/maintenance/tickets/42/cloturer/")
        self.assertEqual(operation.user, self.technician)
        self.assertEqual(operation.organization, self.organization)
        self.assertEqual(operation.status, OfflineSyncOperation.STATUS_PENDING)

    def test_planning_events_and_reschedule_are_available_for_manager(self):
        scheduled_date = timezone.now() + timedelta(days=2)
        maintenance_ticket = MaintenanceTicket.objects.create(
            organization=self.organization,
            responsible=self.manager,
            technician=self.technician,
            client=self.client_user,
            title="Inspection onduleur",
            scheduled_date=scheduled_date,
            planned_duration_minutes=90,
        )
        maintenance_ticket.products.add(self.product)
        self.client.force_login(self.manager)

        response = self.client.get(
            reverse("maintenance-planning-events"),
            {"start": (scheduled_date - timedelta(days=1)).isoformat(), "end": (scheduled_date + timedelta(days=2)).isoformat()},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]["id"], str(maintenance_ticket.pk))
        new_date = scheduled_date + timedelta(hours=3)
        response = self.client.post(
            reverse("maintenance-planning-reschedule", args=[maintenance_ticket.pk]),
            data=json.dumps({"start": new_date.isoformat(), "duration": 120}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        maintenance_ticket.refresh_from_db()
        self.assertEqual(maintenance_ticket.planned_duration_minutes, 120)
        self.assertEqual(maintenance_ticket.scheduled_date, new_date)
