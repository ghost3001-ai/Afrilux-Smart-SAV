from .base import *


class MaintenanceTests(SavPlatformTests):
    def test_manager_can_create_a_single_maintenance_intervention(self):
        self.client.force_login(self.manager)
        scheduled_date = timezone.now() + timedelta(days=2)

        response = self.client.post(
            reverse("maintenance-ticket-create"),
            {
                "title": "Contrôle batterie ponctuel",
                "client": self.client_user.pk,
                "technician": self.technician.pk,
                "products": [self.product.pk],
                "maintenance_type": MaintenanceTicket.TYPE_INSPECTION,
                "priority": Ticket.PRIORITY_NORMAL,
                "scheduled_date": timezone.localtime(scheduled_date).strftime("%Y-%m-%dT%H:%M"),
                "planned_duration_minutes": 45,
                "location": "Douala",
                "route": "Agence - client",
                "overnight_stays": 0,
                "intervention_reason": "Contrôle préventif",
                "checklist": "Vérifier la tension\nNettoyer le coffret",
            },
        )

        self.assertRedirects(response, reverse("maintenance-calendar"))
        maintenance_ticket = MaintenanceTicket.objects.get(title="Contrôle batterie ponctuel")
        self.assertIsNone(maintenance_ticket.program)
        self.assertEqual(maintenance_ticket.planned_duration_minutes, 45)
        self.assertEqual(maintenance_ticket.checklist, ["Vérifier la tension", "Nettoyer le coffret"])

    def test_rule_based_program_generates_monthly_interventions(self):
        start_date = timezone.localdate().replace(day=1)
        program = MaintenanceProgram.objects.create(
            organization=self.organization,
            responsible=self.manager,
            client=self.client_user,
            equipment=self.product,
            technician=self.technician,
            title="Entretien mensuel onduleur",
            start_date=start_date,
            end_date=start_date + timedelta(days=95),
            frequency=MaintenanceProgram.FREQUENCY_MONTHLY,
            checklist=["Controle", "Nettoyage"],
        )

        tickets = publish_maintenance_program(program, actor=self.manager)

        self.assertGreaterEqual(len(tickets), 3)
        self.assertTrue(all(ticket.program_id == program.id for ticket in tickets))
        self.assertTrue(all(ticket.maintenance_type == MaintenanceTicket.TYPE_PREVENTIVE for ticket in tickets))
        self.assertEqual(MaintenanceTicket.objects.filter(program=program).count(), len(tickets))

    def test_weekly_program_generates_only_selected_days(self):
        start_date = timezone.localdate() - timedelta(days=timezone.localdate().weekday())
        program = MaintenanceProgram.objects.create(
            organization=self.organization,
            responsible=self.manager,
            client=self.client_user,
            equipment=self.product,
            technician=self.technician,
            title="Contrôle hebdomadaire",
            start_date=start_date,
            end_date=start_date + timedelta(days=13),
            frequency=MaintenanceProgram.FREQUENCY_WEEKLY,
            weekly_days=["0", "2"],
        )

        tickets = publish_maintenance_program(program, actor=self.manager)

        self.assertEqual(len(tickets), 4)
        self.assertTrue(all(ticket.scheduled_date.weekday() in {0, 2} for ticket in tickets))

    def test_program_form_accepts_typed_client_equipment_parts_and_team(self):
        self.expert.role = User.ROLE_TECHNICIAN
        self.expert.save(update_fields=["role"])
        form = MaintenanceProgramForm(
            data={
                "title": "Entretien climatiseur",
                "service": MaintenanceProgram.SERVICE_COOLING,
                "client_label": self.client_user.company_name,
                "equipment_label": self.product.name,
                "technician": self.technician.pk,
                "team_members": [self.expert.pk],
                "maintenance_type": MaintenanceProgram.TYPE_PREVENTIVE,
                "priority": Ticket.PRIORITY_NORMAL,
                "start_date": timezone.localdate().isoformat(),
                "frequency": MaintenanceProgram.FREQUENCY_MONTHLY,
                "frequency_interval": 1,
                "scheduled_time": "08:00",
                "estimated_duration_minutes": 60,
                "checklist": "Nettoyage\nControle visuel",
                "required_parts_label": "Filtre air, huile",
                "notify_email": "on",
                "notify_internal": "on",
                "period_type": MaintenanceProgram.PERIOD_MONTHLY,
                "year": timezone.localdate().year,
                "task_lines": "[]",
            },
            user=self.manager,
        )

        self.assertTrue(form.is_valid(), form.errors)
        program = form.save()
        self.assertEqual(program.client, self.client_user)
        self.assertEqual(program.equipment, self.product)
        self.assertEqual(list(program.team_members.all()), [self.expert])
        self.assertEqual(program.required_parts.count(), 2)

    def test_maintenance_program_publish_creates_planned_tickets(self):
        program = MaintenanceProgram.objects.create(
            organization=self.organization,
            responsible=self.manager,
            service=MaintenanceProgram.SERVICE_IT,
            period_type=MaintenanceProgram.PERIOD_MONTHLY,
            month=timezone.localdate().month,
            year=timezone.localdate().year,
            task_lines=[
                {
                    "title": "Entretien onduleur client",
                    "technician_id": self.technician.pk,
                    "client_id": self.client_user.pk,
                    "product_ids": [self.product.pk],
                    "scheduled_date": (timezone.localdate() + timedelta(days=2)).isoformat(),
                    "periodicity": MaintenanceTicket.PERIOD_MONTHLY,
                    "checklist": ["Controle visuel", "Test batterie"],
                    "instructions": "Verifier la charge et nettoyer les grilles.",
                    "priority": Ticket.PRIORITY_NORMAL,
                }
            ],
        )

        response = self.api.post(reverse("sav_api:maintenance-program-publier", args=[program.pk]), {}, format="json")

        self.assertEqual(response.status_code, 201)
        program.refresh_from_db()
        self.assertEqual(program.status, MaintenanceProgram.STATUS_PUBLISHED)
        maintenance_ticket = MaintenanceTicket.objects.get(program=program)
        self.assertEqual(maintenance_ticket.status, MaintenanceTicket.STATUS_PLANNED)
        self.assertEqual(maintenance_ticket.technician, self.technician)
        self.assertEqual(list(maintenance_ticket.products.all()), [self.product])

    def test_maintenance_program_publish_accepts_free_client_site_and_equipment(self):
        program = MaintenanceProgram.objects.create(
            organization=self.organization,
            responsible=self.manager,
            service=MaintenanceProgram.SERVICE_COOLING,
            period_type=MaintenanceProgram.PERIOD_MONTHLY,
            month=timezone.localdate().month,
            year=timezone.localdate().year,
            task_lines=[
                {
                    "title": "Maintenance climatiseur agence",
                    "technician_ids": [self.technician.pk],
                    "client_id": 0,
                    "client_label": "AFRILUX Bonaberi - Salle technique",
                    "equipment_label": "Climatiseur split mural LG / SN-LIBRE-001",
                    "scheduled_date": (timezone.localdate() + timedelta(days=2)).isoformat(),
                    "periodicity": MaintenanceTicket.PERIOD_MONTHLY,
                    "checklist": ["Controle visuel", "Nettoyage filtres", "Test froid"],
                    "instructions": "Renseigner la fiche intervention apres la maintenance.",
                    "priority": Ticket.PRIORITY_NORMAL,
                }
            ],
        )

        response = self.api.post(reverse("sav_api:maintenance-program-publier", args=[program.pk]), {}, format="json")

        self.assertEqual(response.status_code, 201)
        program.refresh_from_db()
        self.assertEqual(program.status, MaintenanceProgram.STATUS_PUBLISHED)
        maintenance_ticket = MaintenanceTicket.objects.get(program=program)
        self.assertEqual(maintenance_ticket.client.company_name, "AFRILUX Bonaberi - Salle technique")
        self.assertEqual(maintenance_ticket.equipment_identifier, "Climatiseur split mural LG / SN-LIBRE-001")

    def test_maintenance_program_publish_ignores_old_placeholder_line(self):
        program = MaintenanceProgram.objects.create(
            organization=self.organization,
            responsible=self.manager,
            service=MaintenanceProgram.SERVICE_IT,
            period_type=MaintenanceProgram.PERIOD_MONTHLY,
            month=timezone.localdate().month,
            year=timezone.localdate().year,
            task_lines=[
                {
                    "title": "Entretien preventif equipement client",
                    "technician_ids": [],
                    "client_id": "",
                    "product_ids": [],
                    "scheduled_date": timezone.localtime().replace(second=0, microsecond=0).isoformat(timespec="minutes"),
                    "periodicity": MaintenanceTicket.PERIOD_MONTHLY,
                    "checklist": ["Controle visuel", "Nettoyage", "Test fonctionnement"],
                    "instructions": "Verifier les points critiques et signaler toute anomalie.",
                    "priority": Ticket.PRIORITY_NORMAL,
                },
                {
                    "title": "Maintenance valide",
                    "technician_ids": [self.technician.pk],
                    "client_label": "Site libre Douala",
                    "equipment_label": "Groupe electrogene GE-01",
                    "scheduled_date": (timezone.localdate() + timedelta(days=2)).isoformat(),
                    "periodicity": MaintenanceTicket.PERIOD_MONTHLY,
                    "checklist": ["Controle huile"],
                    "priority": Ticket.PRIORITY_NORMAL,
                },
            ],
        )

        response = self.api.post(reverse("sav_api:maintenance-program-publier", args=[program.pk]), {}, format="json")

        self.assertEqual(response.status_code, 201)
        program.refresh_from_db()
        self.assertEqual(program.status, MaintenanceProgram.STATUS_PUBLISHED)
        self.assertEqual(MaintenanceTicket.objects.filter(program=program).count(), 1)
        self.assertEqual(MaintenanceTicket.objects.get(program=program).title, "Maintenance valide")

    def test_draft_maintenance_program_can_be_edited_from_web(self):
        program = MaintenanceProgram.objects.create(
            organization=self.organization,
            responsible=self.manager,
            service=MaintenanceProgram.SERVICE_IT,
            period_type=MaintenanceProgram.PERIOD_MONTHLY,
            month=timezone.localdate().month,
            year=timezone.localdate().year,
            task_lines=[],
        )
        self.client.force_login(self.manager)

        response = self.client.post(
            reverse("maintenance-program-update", args=[program.pk]),
            {
                "title": "Programme corrige",
                "service": MaintenanceProgram.SERVICE_IT,
                "period_type": MaintenanceProgram.PERIOD_MONTHLY,
                "month": timezone.localdate().month,
                "quarter": "",
                "year": timezone.localdate().year,
                "task_lines": json.dumps(
                    [
                        {
                            "title": "Maintenance corrigee",
                            "technician_ids": [self.technician.pk],
                            "client_label": "Site corrige",
                            "equipment_label": "Equipement corrige",
                            "scheduled_date": (timezone.localdate() + timedelta(days=2)).isoformat(),
                            "periodicity": MaintenanceTicket.PERIOD_MONTHLY,
                            "checklist": ["Controle visuel"],
                            "priority": Ticket.PRIORITY_NORMAL,
                        }
                    ]
                ),
            },
        )

        self.assertEqual(response.status_code, 302)
        program.refresh_from_db()
        self.assertEqual(program.title, "Programme corrige")
        self.assertEqual(program.task_lines[0]["title"], "Maintenance corrigee")

    def test_team_member_can_view_but_not_start_team_maintenance(self):
        teammate = User.objects.create_user(
            username="maintenance_member",
            password="MemberPass123!",
            role=User.ROLE_TECHNICIAN,
            organization=self.organization,
            is_active=True,
        )
        scheduled_at = (timezone.localtime(timezone.now()) + timedelta(days=2)).replace(
            hour=15,
            minute=45,
            second=0,
            microsecond=0,
        )
        program = MaintenanceProgram.objects.create(
            organization=self.organization,
            responsible=self.manager,
            service=MaintenanceProgram.SERVICE_IT,
            period_type=MaintenanceProgram.PERIOD_MONTHLY,
            month=timezone.localdate().month,
            year=timezone.localdate().year,
            task_lines=[
                {
                    "title": "Maintenance collective salle reseau",
                    "technician_ids": [self.technician.pk, teammate.pk],
                    "client_id": self.client_user.pk,
                    "product_ids": [self.product.pk],
                    "scheduled_date": scheduled_at.isoformat(timespec="minutes"),
                    "periodicity": MaintenanceTicket.PERIOD_MONTHLY,
                    "checklist": ["Controle visuel", "Test alimentation"],
                    "instructions": "Intervention avec chef et membre.",
                    "priority": Ticket.PRIORITY_NORMAL,
                }
            ],
        )

        response = self.api.post(reverse("sav_api:maintenance-program-publier", args=[program.pk]), {}, format="json")

        self.assertEqual(response.status_code, 201)
        maintenance_ticket = MaintenanceTicket.objects.get(program=program)
        self.assertEqual(maintenance_ticket.technician, self.technician)
        self.assertEqual(list(maintenance_ticket.team_members.all()), [teammate])
        self.assertEqual(timezone.localtime(maintenance_ticket.scheduled_date).hour, 15)
        self.assertEqual(timezone.localtime(maintenance_ticket.scheduled_date).minute, 45)
        self.assertIn(str(teammate), maintenance_ticket.technician_team_label)

        self.api.force_authenticate(user=teammate)
        detail_response = self.api.get(reverse("sav_api:maintenance-ticket-detail", args=[maintenance_ticket.pk]))
        self.assertEqual(detail_response.status_code, 200)

        start_response = self.api.post(reverse("sav_api:maintenance-ticket-demarrer", args=[maintenance_ticket.pk]), {})
        self.assertEqual(start_response.status_code, 400)
        maintenance_ticket.refresh_from_db()
        self.assertEqual(maintenance_ticket.status, MaintenanceTicket.STATUS_PLANNED)

        self.api.force_authenticate(user=self.technician)
        leader_start_response = self.api.post(reverse("sav_api:maintenance-ticket-demarrer", args=[maintenance_ticket.pk]), {})
        self.assertEqual(leader_start_response.status_code, 200)

    def test_technician_can_view_maintenance_dashboard_calendar_and_interventions(self):
        browser = Client()
        browser.force_login(self.technician)

        for route_name in ("maintenance-dashboard", "maintenance-calendar", "maintenance-interventions", "maintenance-program"):
            response = browser.get(reverse(route_name))
            self.assertEqual(response.status_code, 200, route_name)

    def test_team_member_can_close_completed_team_ticket(self):
        teammate = User.objects.create_user(
            username="sav_team_member_close",
            password="MemberPass123!",
            role=User.ROLE_TECHNICIAN,
            organization=self.organization,
            is_active=True,
        )
        ticket = Ticket.objects.create(
            client=self.client_user,
            product=self.product,
            assigned_agent=self.technician,
            team_leader=self.technician,
            is_team_intervention=True,
            title="Resolution en equipe",
            description="Verifier la cloture par un membre d'equipe.",
            category=Ticket.CATEGORY_BREAKDOWN,
            status=Ticket.STATUS_DONE,
            priority=Ticket.PRIORITY_NORMAL,
        )
        ticket.team_members.add(teammate)
        Intervention.objects.create(
            organization=self.organization,
            ticket=ticket,
            agent=self.technician,
            intervention_type=Intervention.TYPE_ON_SITE,
            status=Intervention.STATUS_DONE,
            started_at=timezone.now() - timedelta(hours=1),
            finished_at=timezone.now(),
            diagnosis="Diagnostic realise par l'equipe.",
            action_taken="Resolution collective.",
        )
        signature = SimpleUploadedFile("signature.png", b"signature", content_type="image/png")

        close_sav_dossier(
            ticket,
            diagnosis="Diagnostic confirme.",
            action_taken="Action terminee en equipe.",
            client_name="Client signataire",
            signature=signature,
            actor=teammate,
        )

        ticket.refresh_from_db()
        self.assertEqual(ticket.status, Ticket.STATUS_CLOSED)
        self.assertIsNotNone(ticket.closed_at)

    def test_maintenance_closure_with_anomaly_generates_incident_ticket(self):
        maintenance_ticket = MaintenanceTicket.objects.create(
            organization=self.organization,
            responsible=self.manager,
            technician=self.technician,
            client=self.client_user,
            title="Entretien chambre froide",
            service=MaintenanceProgram.SERVICE_COOLING,
            periodicity=MaintenanceTicket.PERIOD_MONTHLY,
            scheduled_date=timezone.localdate(),
            status=MaintenanceTicket.STATUS_IN_PROGRESS,
            checklist=["Controle temperature", "Nettoyage filtre"],
            priority=Ticket.PRIORITY_HIGH,
            location="Salle serveurs",
            started_at=timezone.now() - timedelta(minutes=45),
        )
        maintenance_ticket.products.add(self.product)
        self.api.force_authenticate(user=self.technician)

        response = self.api.post(
            reverse("sav_api:maintenance-ticket-cloturer", args=[maintenance_ticket.pk]),
            {
                "final_status": MaintenanceTicket.STATUS_ANOMALY,
                "actual_started_at": (timezone.now() - timedelta(minutes=45)).isoformat(),
                "actual_finished_at": timezone.now().isoformat(),
                "checklist_completed": ["Controle temperature", "Nettoyage filtre"],
                "observations": "Temperature instable detectee pendant l'entretien.",
                "parts_used": "Filtre remplace",
                "anomaly_detected": True,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        maintenance_ticket.refresh_from_db()
        self.assertEqual(maintenance_ticket.status, MaintenanceTicket.STATUS_ANOMALY)
        self.assertTrue(MaintenanceReport.objects.filter(maintenance_ticket=maintenance_ticket).exists())
        self.assertIsNotNone(maintenance_ticket.anomaly_ticket)
        self.assertEqual(maintenance_ticket.anomaly_ticket.category, Ticket.CATEGORY_BREAKDOWN)
        self.assertEqual(maintenance_ticket.anomaly_ticket.business_domain, Ticket.DOMAIN_COOLING)
        self.assertTrue(maintenance_ticket.anomaly_ticket.reference.startswith("ASS-SAV-"))

    def test_cfao_maintenance_anomaly_generates_cfao_incident_ticket(self):
        maintenance_ticket = MaintenanceTicket.objects.create(
            organization=self.organization,
            responsible=self.manager,
            technician=self.technician,
            client=self.client_user,
            title="Controle CFAO",
            service=MaintenanceProgram.SERVICE_CFAO,
            periodicity=MaintenanceTicket.PERIOD_QUARTERLY,
            scheduled_date=timezone.localdate(),
            status=MaintenanceTicket.STATUS_IN_PROGRESS,
            checklist=["Controle plan", "Verification dossier technique"],
            priority=Ticket.PRIORITY_NORMAL,
            started_at=timezone.now() - timedelta(minutes=30),
        )
        self.api.force_authenticate(user=self.technician)

        response = self.api.post(
            reverse("sav_api:maintenance-ticket-cloturer", args=[maintenance_ticket.pk]),
            {
                "final_status": MaintenanceTicket.STATUS_ANOMALY,
                "actual_started_at": (timezone.now() - timedelta(minutes=30)).isoformat(),
                "actual_finished_at": timezone.now().isoformat(),
                "checklist_completed": ["Controle plan", "Verification dossier technique"],
                "observations": "Anomalie detectee sur le dossier technique CFAO.",
                "anomaly_detected": True,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        maintenance_ticket.refresh_from_db()
        self.assertEqual(maintenance_ticket.anomaly_ticket.business_domain, Ticket.DOMAIN_CFAO)

    def test_maintenance_ticket_acknowledge_and_cancel_actions(self):
        maintenance_ticket = MaintenanceTicket.objects.create(
            organization=self.organization,
            responsible=self.manager,
            technician=self.technician,
            client=self.client_user,
            title="Controle trimestriel groupe",
            service=MaintenanceProgram.SERVICE_GENERATOR,
            periodicity=MaintenanceTicket.PERIOD_QUARTERLY,
            scheduled_date=timezone.localdate() + timedelta(days=3),
            checklist=["Controle huile"],
            priority=Ticket.PRIORITY_NORMAL,
        )

        self.api.force_authenticate(user=self.technician)
        ack_response = self.api.post(reverse("sav_api:maintenance-ticket-accuser-reception", args=[maintenance_ticket.pk]), {})

        self.assertEqual(ack_response.status_code, 200)
        maintenance_ticket.refresh_from_db()
        self.assertEqual(maintenance_ticket.status, MaintenanceTicket.STATUS_NOTIFIED)
        self.assertIsNotNone(maintenance_ticket.acknowledged_at)

        self.api.force_authenticate(user=self.manager)
        cancel_response = self.api.post(
            reverse("sav_api:maintenance-ticket-annuler", args=[maintenance_ticket.pk]),
            {"reason": "Client inaccessible et intervention reportee hors periode."},
            format="json",
        )

        self.assertEqual(cancel_response.status_code, 200)
        maintenance_ticket.refresh_from_db()
        self.assertEqual(maintenance_ticket.status, MaintenanceTicket.STATUS_CANCELLED)
        self.assertIn("Client inaccessible", maintenance_ticket.cancellation_reason)
        self.assertIsNotNone(maintenance_ticket.cancelled_at)

    def test_maintenance_operational_notifications_cover_j_minus_3_and_j_plus_1(self):
        upcoming = MaintenanceTicket.objects.create(
            organization=self.organization,
            responsible=self.manager,
            technician=self.technician,
            client=self.client_user,
            title="Maintenance J-3",
            service=MaintenanceProgram.SERVICE_IT,
            periodicity=MaintenanceTicket.PERIOD_MONTHLY,
            scheduled_date=timezone.localdate() + timedelta(days=3),
            checklist=["Controle"],
            priority=Ticket.PRIORITY_NORMAL,
        )
        overdue = MaintenanceTicket.objects.create(
            organization=self.organization,
            responsible=self.manager,
            technician=self.technician,
            client=self.client_user,
            title="Maintenance non realisee",
            service=MaintenanceProgram.SERVICE_IT,
            periodicity=MaintenanceTicket.PERIOD_MONTHLY,
            scheduled_date=timezone.localdate() - timedelta(days=1),
            checklist=["Controle"],
            priority=Ticket.PRIORITY_NORMAL,
        )

        results = dispatch_maintenance_operational_notifications(
            organization=self.organization,
            now=timezone.now(),
        )
        upcoming.refresh_from_db()
        overdue.refresh_from_db()

        self.assertEqual(results["j_minus_3"], 1)
        self.assertEqual(results["not_realized_j_plus_1"], 1)
        self.assertEqual(upcoming.status, MaintenanceTicket.STATUS_NOTIFIED)
        self.assertIsNotNone(upcoming.notified_at)
        self.assertIsNotNone(overdue.overdue_alerted_at)
        self.assertTrue(
            Notification.objects.filter(recipient=self.technician, event_type="maintenance_j_minus_3").exists()
        )
        self.assertTrue(
            Notification.objects.filter(recipient=self.manager, event_type="maintenance_not_realized_j_plus_1").exists()
        )

    def test_maintenance_closure_stores_photos_and_generates_pdf(self):
        maintenance_ticket = MaintenanceTicket.objects.create(
            organization=self.organization,
            responsible=self.manager,
            technician=self.technician,
            client=self.client_user,
            title="Entretien preventif copieur",
            service=MaintenanceProgram.SERVICE_IT,
            periodicity=MaintenanceTicket.PERIOD_MONTHLY,
            scheduled_date=timezone.localdate(),
            status=MaintenanceTicket.STATUS_IN_PROGRESS,
            checklist=["Nettoyage", "Test impression"],
            priority=Ticket.PRIORITY_NORMAL,
            started_at=timezone.now() - timedelta(minutes=30),
        )
        self.api.force_authenticate(user=self.technician)
        photo = SimpleUploadedFile("maintenance-photo.png", b"fake image content", content_type="image/png")

        response = self.api.post(
            reverse("sav_api:maintenance-ticket-cloturer", args=[maintenance_ticket.pk]),
            {
                "final_status": MaintenanceTicket.STATUS_DONE,
                "actual_started_at": (timezone.now() - timedelta(minutes=30)).isoformat(),
                "actual_finished_at": timezone.now().isoformat(),
                "checklist_completed": json.dumps(["Nettoyage", "Test impression"]),
                "observations": "Maintenance realisee sans anomalie.",
                "anomaly_detected": "false",
                "photos": photo,
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, 200)
        maintenance_ticket.refresh_from_db()
        report = maintenance_ticket.report
        self.assertEqual(maintenance_ticket.status, MaintenanceTicket.STATUS_DONE)
        self.assertTrue(bool(report.report_pdf))
        self.assertEqual(MaintenanceReportPhoto.objects.filter(report=report).count(), 1)
        self.assertFalse(Ticket.objects.filter(title__icontains="Anomalie maintenance").exists())

        self.api.force_authenticate(user=self.manager)
        validate_response = self.api.post(reverse("sav_api:maintenance-ticket-valider", args=[maintenance_ticket.pk]), {})
        self.assertEqual(validate_response.status_code, 200)
        report.refresh_from_db()
        self.assertEqual(report.validated_by, self.manager)
        self.assertIsNotNone(report.validated_at)

    def test_maintenance_period_report_exports_pdf(self):
        MaintenanceTicket.objects.create(
            organization=self.organization,
            responsible=self.manager,
            technician=self.technician,
            client=self.client_user,
            title="Entretien export PDF",
            service=MaintenanceProgram.SERVICE_IT,
            periodicity=MaintenanceTicket.PERIOD_MONTHLY,
            scheduled_date=timezone.localdate(),
            status=MaintenanceTicket.STATUS_DONE,
            checklist=["Controle"],
            priority=Ticket.PRIORITY_NORMAL,
        )

        response = self.api.get(reverse("sav_api:maintenance-period-report", args=["mensuel"]) + "?format=pdf")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
