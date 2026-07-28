from .base import *


class AssignmentTests(SavPlatformTests):
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

    def test_assigned_ticket_does_not_block_new_assignment(self):
        Ticket.objects.create(
            client=self.client_user,
            product=self.product,
            assigned_agent=self.technician,
            title="Ticket seulement assigne",
            description="Ce statut ne doit pas bloquer une nouvelle affectation.",
            category=Ticket.CATEGORY_BREAKDOWN,
            status=Ticket.STATUS_ASSIGNED,
            priority=Ticket.PRIORITY_NORMAL,
        )
        ticket = Ticket.objects.create(
            client=self.client_user,
            product=self.product,
            title="Nouvelle affectation autorisee",
            description="Le technicien peut encore etre choisi.",
            category=Ticket.CATEGORY_BREAKDOWN,
            status=Ticket.STATUS_NEW,
            priority=Ticket.PRIORITY_NORMAL,
        )

        response = self.api.post(
            reverse("sav_api:ticket-assign", args=[ticket.pk]),
            {"technician": self.technician.pk},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        ticket.refresh_from_db()
        self.assertEqual(ticket.assigned_agent, self.technician)

    def test_blocking_ticket_prevents_assignment_unless_manager_forces_it(self):
        Ticket.objects.create(
            client=self.client_user,
            product=self.product,
            assigned_agent=self.technician,
            title="Intervention deja planifiee",
            description="Ce ticket rend le technicien indisponible.",
            category=Ticket.CATEGORY_BREAKDOWN,
            status=Ticket.STATUS_PLANNED,
            priority=Ticket.PRIORITY_NORMAL,
            sla_deadline=timezone.now() + timedelta(hours=2),
        )
        ticket = Ticket.objects.create(
            client=self.client_user,
            product=self.product,
            title="Affectation bloquee",
            description="Doit etre refusee sans forcage.",
            category=Ticket.CATEGORY_BREAKDOWN,
            status=Ticket.STATUS_NEW,
            priority=Ticket.PRIORITY_NORMAL,
        )

        blocked_response = self.api.post(
            reverse("sav_api:ticket-assign", args=[ticket.pk]),
            {"technician": self.technician.pk},
            format="json",
        )
        ticket.refresh_from_db()

        self.assertEqual(blocked_response.status_code, 403)
        self.assertIsNone(ticket.assigned_agent)
        self.assertIn("indisponible", str(blocked_response.data["detail"]))

        forced_response = self.api.post(
            reverse("sav_api:ticket-assign", args=[ticket.pk]),
            {
                "technician": self.technician.pk,
                "force_assignment": True,
                "force_reason": "Urgence client validee par le responsable SAV.",
            },
            format="json",
        )
        ticket.refresh_from_db()

        self.assertEqual(forced_response.status_code, 200)
        self.assertEqual(ticket.assigned_agent, self.technician)
        self.assertTrue(
            AuditLog.objects.filter(
                action="ticket_technician_assigned",
                target_id=ticket.id,
                details__forced=True,
            ).exists()
        )

    def test_technician_availability_is_unified_for_sav_and_maintenance(self):
        maintenance_free = User.objects.create_user(
            username="maintenance_free",
            password="secret123",
            organization=self.organization,
            role=User.ROLE_TECHNICIAN,
        )
        maintenance_busy = User.objects.create_user(
            username="maintenance_busy",
            password="secret123",
            organization=self.organization,
            role=User.ROLE_TECHNICIAN,
        )
        Ticket.objects.create(
            client=self.client_user,
            product=self.product,
            assigned_agent=self.technician,
            title="SAV en cours",
            description="Conflit SAV actif.",
            category=Ticket.CATEGORY_BREAKDOWN,
            status=Ticket.STATUS_IN_PROGRESS,
            priority=Ticket.PRIORITY_HIGH,
        )
        MaintenanceTicket.objects.create(
            organization=self.organization,
            responsible=self.manager,
            technician=maintenance_free,
            client=self.client_user,
            title="Maintenance long terme",
            service=MaintenanceProgram.SERVICE_IT,
            periodicity=MaintenanceTicket.PERIOD_MONTHLY,
            scheduled_date=timezone.now() + timedelta(days=3),
            checklist=["Controle"],
            priority=Ticket.PRIORITY_NORMAL,
        )
        MaintenanceTicket.objects.create(
            organization=self.organization,
            responsible=self.manager,
            technician=maintenance_busy,
            client=self.client_user,
            title="Maintenance proche",
            service=MaintenanceProgram.SERVICE_IT,
            periodicity=MaintenanceTicket.PERIOD_MONTHLY,
            scheduled_date=timezone.now() + timedelta(hours=6),
            checklist=["Controle"],
            priority=Ticket.PRIORITY_NORMAL,
        )

        response = self.api.get(reverse("sav_api:technician-availability"))

        self.assertEqual(response.status_code, 200)
        rows = {row["id"]: row for row in response.data["results"]}
        self.assertFalse(rows[self.technician.id]["assignable"])
        self.assertEqual(rows[self.technician.id]["sav_active_count"], 1)
        self.assertTrue(rows[maintenance_free.id]["assignable"])
        self.assertEqual(rows[maintenance_free.id]["maintenance_active_count"], 0)
        self.assertFalse(rows[maintenance_busy.id]["assignable"])
        self.assertEqual(rows[maintenance_busy.id]["maintenance_active_count"], 1)

        filtered_response = self.api.get(reverse("sav_api:technician-availability"), {"assignable_only": "true"})
        filtered_ids = {row["id"] for row in filtered_response.data["results"]}
        self.assertIn(maintenance_free.id, filtered_ids)
        self.assertNotIn(maintenance_busy.id, filtered_ids)

    def test_assign_team_creates_collective_intervention_context(self):
        member = User.objects.create_user(
            username="team_member",
            password="secret123",
            organization=self.organization,
            role=User.ROLE_TECHNICIAN,
        )
        ticket = Ticket.objects.create(
            client=self.client_user,
            product=self.product,
            title="Intervention collective",
            description="Le dossier doit etre traite par une equipe.",
            category=Ticket.CATEGORY_BREAKDOWN,
            status=Ticket.STATUS_PENDING_ASSIGNMENT,
            priority=Ticket.PRIORITY_HIGH,
        )

        response = self.api.post(
            reverse("sav_api:ticket-assign-team", args=[ticket.pk]),
            {"team_leader": self.technician.pk, "team_members": [member.pk]},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        ticket.refresh_from_db()
        self.assertTrue(ticket.is_team_intervention)
        self.assertEqual(ticket.team_leader, self.technician)
        self.assertEqual(ticket.assigned_agent, self.technician)
        self.assertEqual(ticket.status, Ticket.STATUS_TEAM_READY)
        self.assertEqual(list(ticket.team_members.all()), [member])

    def test_web_assign_team_redirects_without_key_error(self):
        member = User.objects.create_user(
            username="team_member_web",
            password="secret123",
            organization=self.organization,
            role=User.ROLE_TECHNICIAN,
        )
        ticket = Ticket.objects.create(
            client=self.client_user,
            product=self.product,
            title="Equipe depuis portail",
            description="Le bouton Constituer equipe ne doit pas lever d'erreur.",
            category=Ticket.CATEGORY_BREAKDOWN,
            status=Ticket.STATUS_PENDING_ASSIGNMENT,
            priority=Ticket.PRIORITY_HIGH,
        )
        self.client.force_login(self.manager)

        response = self.client.post(
            reverse("ticket-assign-team-web", args=[ticket.pk]),
            {
                "leader": self.technician.pk,
                "members": [member.pk],
                "note": "",
                "force_reason": "",
            },
        )

        self.assertEqual(response.status_code, 302)
        ticket.refresh_from_db()
        self.assertTrue(ticket.is_team_intervention)
        self.assertEqual(ticket.team_leader, self.technician)
        self.assertEqual(ticket.status, Ticket.STATUS_TEAM_READY)
