from django.urls import reverse

from .base import SavPlatformTests
from ..models import (
    Message,
    Ticket,
    TicketAssignment,
    User,
)


class EscalationTests(SavPlatformTests):
    def test_internal_user_can_escalate_ticket_to_supervisor_via_api(self):
        ticket = Ticket.objects.create(
            client=self.client_user,
            product=self.product,
            assigned_agent=self.agent,
            title="Ticket a escalader",
            description="Le support de niveau 1 demande une escalation.",
            category=Ticket.CATEGORY_BREAKDOWN,
            status=Ticket.STATUS_IN_PROGRESS,
            priority=Ticket.PRIORITY_NORMAL,
        )
        TicketAssignment.objects.create(
            ticket=ticket,
            technician=self.agent,
            assigned_by=self.manager,
            status=TicketAssignment.STATUS_ACTIVE,
        )
        self.api.force_authenticate(user=self.manager)

        response = self.api.post(
            reverse("sav_api:ticket-escalate", args=[ticket.pk]),
            {"target": "supervisor"},
            format="json",
        )
        ticket.refresh_from_db()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(ticket.priority, Ticket.PRIORITY_HIGH)
        self.assertEqual(ticket.status, Ticket.STATUS_ASSIGNED)
        self.assertEqual(ticket.assigned_agent, self.supervisor)
        self.assertTrue(
            TicketAssignment.objects.filter(
                ticket=ticket,
                technician=self.agent,
                status=TicketAssignment.STATUS_ESCALATED,
            ).exists()
        )
        self.assertTrue(
            TicketAssignment.objects.filter(
                ticket=ticket,
                technician=self.supervisor,
                status=TicketAssignment.STATUS_ACTIVE,
            ).exists()
        )

    def test_internal_user_can_escalate_ticket_to_head_sav_via_api(self):
        ticket = Ticket.objects.create(
            client=self.client_user,
            product=self.product,
            assigned_agent=self.agent,
            title="Ticket vers responsable SAV",
            description="Escalade vers le head SAV.",
            category=Ticket.CATEGORY_BREAKDOWN,
            status=Ticket.STATUS_IN_PROGRESS,
            priority=Ticket.PRIORITY_NORMAL,
        )
        TicketAssignment.objects.create(
            ticket=ticket,
            technician=self.agent,
            assigned_by=self.manager,
            status=TicketAssignment.STATUS_ACTIVE,
        )
        self.api.force_authenticate(user=self.manager)

        response = self.api.post(
            reverse("sav_api:ticket-escalate", args=[ticket.pk]),
            {"target": "head_sav"},
            format="json",
        )
        ticket.refresh_from_db()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(ticket.priority, Ticket.PRIORITY_HIGH)
        self.assertEqual(ticket.assigned_agent, self.manager)
        self.assertTrue(
            TicketAssignment.objects.filter(
                ticket=ticket,
                technician=self.agent,
                status=TicketAssignment.STATUS_ESCALATED,
            ).exists()
        )

    def test_internal_user_can_escalate_ticket_to_expert_then_head_sav_via_api(self):
        ticket = Ticket.objects.create(
            client=self.client_user,
            product=self.product,
            assigned_agent=self.agent,
            title="Ticket vers expert",
            description="Escalade prioritaire vers expert.",
            category=Ticket.CATEGORY_BREAKDOWN,
            status=Ticket.STATUS_IN_PROGRESS,
            priority=Ticket.PRIORITY_LOW,
        )
        TicketAssignment.objects.create(
            ticket=ticket,
            technician=self.agent,
            assigned_by=self.manager,
            status=TicketAssignment.STATUS_ACTIVE,
        )
        self.api.force_authenticate(user=self.manager)

        response = self.api.post(
            reverse("sav_api:ticket-escalate", args=[ticket.pk]),
            {"target": "expert_then_head_sav"},
            format="json",
        )
        ticket.refresh_from_db()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(ticket.priority, Ticket.PRIORITY_NORMAL)
        self.assertEqual(ticket.assigned_agent, self.expert)

    def test_internal_user_can_escalate_ticket_via_web_with_expert_fallback_to_head_sav(self):
        ticket = Ticket.objects.create(
            client=self.client_user,
            product=self.product,
            assigned_agent=self.agent,
            title="Ticket portail a escalader",
            description="Escalade depuis la fiche ticket.",
            category=Ticket.CATEGORY_BREAKDOWN,
            status=Ticket.STATUS_IN_PROGRESS,
            priority=Ticket.PRIORITY_LOW,
        )
        TicketAssignment.objects.create(
            ticket=ticket,
            technician=self.agent,
            assigned_by=self.manager,
            status=TicketAssignment.STATUS_ACTIVE,
        )
        self.expert.is_active = False
        self.expert.save(update_fields=["is_active"])
        self.client.force_login(self.manager)

        response = self.client.post(
            reverse("ticket-escalate-web", args=[ticket.pk]),
            {
                "target": "expert_then_head_sav",
                "note": "Escalade web avec secours head SAV.",
            },
        )
        ticket.refresh_from_db()

        self.assertEqual(response.status_code, 302)
        self.assertEqual(ticket.priority, Ticket.PRIORITY_NORMAL)
        self.assertEqual(ticket.assigned_agent, self.manager)
        self.assertTrue(
            TicketAssignment.objects.filter(
                ticket=ticket,
                technician=self.agent,
                status=TicketAssignment.STATUS_ESCALATED,
            ).exists()
        )

    def test_ticket_detail_shows_extended_escalation_targets(self):
        ticket = Ticket.objects.create(
            client=self.client_user,
            product=self.product,
            assigned_agent=self.agent,
            title="Ticket avec escalades etendues",
            description="Verifier les nouvelles cibles d'escalade.",
            category=Ticket.CATEGORY_BREAKDOWN,
            status=Ticket.STATUS_IN_PROGRESS,
            priority=Ticket.PRIORITY_NORMAL,
        )
        self.client.force_login(self.manager)

        response = self.client.get(reverse("ticket-detail", args=[ticket.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Vers responsable CFAO")
        self.assertContains(response, "Vers conducteur de travaux CFAO")
        self.assertNotContains(response, "Vers responsable froid &amp; climatisation")
        self.assertNotContains(response, "Vers gestionnaire principal du logiciel")

    def test_internal_user_can_escalate_ticket_to_cfao_manager_via_api(self):
        cfao_manager = User.objects.create_user(
            username="cfao_manager",
            password="secret123",
            organization=self.organization,
            role=User.ROLE_CFAO_MANAGER,
        )
        ticket = Ticket.objects.create(
            client=self.client_user,
            product=self.product,
            assigned_agent=self.agent,
            title="Ticket vers CFAO",
            description="Escalade vers le responsable CFAO.",
            category=Ticket.CATEGORY_INSTALLATION,
            status=Ticket.STATUS_IN_PROGRESS,
            priority=Ticket.PRIORITY_NORMAL,
        )
        TicketAssignment.objects.create(
            ticket=ticket,
            technician=self.agent,
            assigned_by=self.manager,
            status=TicketAssignment.STATUS_ACTIVE,
        )
        self.api.force_authenticate(user=self.manager)

        response = self.api.post(
            reverse("sav_api:ticket-escalate", args=[ticket.pk]),
            {"target": "cfao_manager"},
            format="json",
        )
        ticket.refresh_from_db()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(ticket.assigned_agent, cfao_manager)

    def test_internal_user_can_escalate_ticket_to_cfao_works_via_api(self):
        cfao_works = User.objects.create_user(
            username="cfao_works",
            password="secret123",
            organization=self.organization,
            role=User.ROLE_CFAO_WORKS,
        )
        ticket = Ticket.objects.create(
            client=self.client_user,
            product=self.product,
            assigned_agent=self.agent,
            title="Ticket vers travaux CFAO",
            description="Escalade vers le conducteur de travaux.",
            category=Ticket.CATEGORY_INSTALLATION,
            status=Ticket.STATUS_IN_PROGRESS,
            priority=Ticket.PRIORITY_NORMAL,
        )
        TicketAssignment.objects.create(
            ticket=ticket,
            technician=self.agent,
            assigned_by=self.manager,
            status=TicketAssignment.STATUS_ACTIVE,
        )
        self.api.force_authenticate(user=self.manager)

        response = self.api.post(
            reverse("sav_api:ticket-escalate", args=[ticket.pk]),
            {"target": "cfao_works"},
            format="json",
        )
        ticket.refresh_from_db()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(ticket.assigned_agent, cfao_works)

    def test_internal_user_can_escalate_ticket_to_hvac_manager_via_api(self):
        hvac_manager = User.objects.create_user(
            username="hvac_manager",
            password="secret123",
            organization=self.organization,
            role=User.ROLE_HVAC_MANAGER,
        )
        ticket = Ticket.objects.create(
            client=self.client_user,
            product=self.product,
            assigned_agent=self.agent,
            title="Ticket vers froid et climatisation",
            description="Escalade vers le specialiste CVC.",
            business_domain=Ticket.DOMAIN_COOLING,
            category=Ticket.CATEGORY_BREAKDOWN,
            status=Ticket.STATUS_IN_PROGRESS,
            priority=Ticket.PRIORITY_NORMAL,
        )
        TicketAssignment.objects.create(
            ticket=ticket,
            technician=self.agent,
            assigned_by=self.manager,
            status=TicketAssignment.STATUS_ACTIVE,
        )
        self.api.force_authenticate(user=self.manager)

        response = self.api.post(
            reverse("sav_api:ticket-escalate", args=[ticket.pk]),
            {"target": "hvac_manager"},
            format="json",
        )
        ticket.refresh_from_db()

        self.assertEqual(response.status_code, 400)
        self.assertEqual(ticket.assigned_agent, self.agent)

    def test_internal_user_can_escalate_ticket_to_software_owner_via_api(self):
        software_owner = User.objects.create_user(
            username="software_owner",
            password="secret123",
            organization=self.organization,
            role=User.ROLE_SOFTWARE_OWNER,
        )
        ticket = Ticket.objects.create(
            client=self.client_user,
            product=self.product,
            assigned_agent=self.agent,
            title="Ticket vers gestionnaire logiciel",
            description="Escalade vers le referent applicatif.",
            business_domain=Ticket.DOMAIN_IT,
            category=Ticket.CATEGORY_BUG,
            status=Ticket.STATUS_IN_PROGRESS,
            priority=Ticket.PRIORITY_NORMAL,
        )
        TicketAssignment.objects.create(
            ticket=ticket,
            technician=self.agent,
            assigned_by=self.manager,
            status=TicketAssignment.STATUS_ACTIVE,
        )
        self.api.force_authenticate(user=self.manager)

        response = self.api.post(
            reverse("sav_api:ticket-escalate", args=[ticket.pk]),
            {"target": "software_owner"},
            format="json",
        )
        ticket.refresh_from_db()

        self.assertEqual(response.status_code, 400)
        self.assertEqual(ticket.assigned_agent, self.agent)

    def test_manager_cannot_assign_ticket_to_unavailable_technician(self):
        unavailable_technician = User.objects.create_user(
            username="technician_unavailable",
            password="secret123",
            organization=self.organization,
            role=User.ROLE_TECHNICIAN,
            technician_status="on_leave",
        )
        ticket = Ticket.objects.create(
            client=self.client_user,
            product=self.product,
            title="Affectation indisponible",
            description="Ne doit pas etre assigne a un technicien indisponible.",
            category=Ticket.CATEGORY_BREAKDOWN,
            status=Ticket.STATUS_NEW,
            priority=Ticket.PRIORITY_NORMAL,
        )

        response = self.api.post(
            reverse("sav_api:ticket-assign", args=[ticket.pk]),
            {"technician": unavailable_technician.pk},
            format="json",
        )
        ticket.refresh_from_db()

        self.assertEqual(response.status_code, 404)
        self.assertIsNone(ticket.assigned_agent)

    def test_expert_then_head_sav_falls_back_to_head_sav_for_cooling_ticket(self):
        hvac_manager = User.objects.create_user(
            username="hvac_fallback",
            password="secret123",
            organization=self.organization,
            role=User.ROLE_HVAC_MANAGER,
        )
        self.expert.is_active = False
        self.expert.save(update_fields=["is_active"])
        ticket = Ticket.objects.create(
            client=self.client_user,
            product=self.product,
            assigned_agent=self.agent,
            title="Fallback froid",
            description="Escalade cooling sans expert disponible.",
            business_domain=Ticket.DOMAIN_COOLING,
            category=Ticket.CATEGORY_BREAKDOWN,
            status=Ticket.STATUS_IN_PROGRESS,
            priority=Ticket.PRIORITY_NORMAL,
        )
        TicketAssignment.objects.create(
            ticket=ticket,
            technician=self.agent,
            assigned_by=self.manager,
            status=TicketAssignment.STATUS_ACTIVE,
        )
        self.api.force_authenticate(user=self.manager)

        response = self.api.post(
            reverse("sav_api:ticket-escalate", args=[ticket.pk]),
            {"target": "expert_then_head_sav"},
            format="json",
        )
        ticket.refresh_from_db()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(ticket.assigned_agent, self.manager)

    def test_expert_then_head_sav_falls_back_to_head_sav_for_bug_ticket(self):
        software_owner = User.objects.create_user(
            username="software_fallback",
            password="secret123",
            organization=self.organization,
            role=User.ROLE_SOFTWARE_OWNER,
        )
        self.expert.is_active = False
        self.expert.save(update_fields=["is_active"])
        ticket = Ticket.objects.create(
            client=self.client_user,
            product=self.product,
            assigned_agent=self.agent,
            title="Fallback applicatif",
            description="Escalade bug sans expert disponible.",
            business_domain=Ticket.DOMAIN_IT,
            category=Ticket.CATEGORY_BUG,
            status=Ticket.STATUS_IN_PROGRESS,
            priority=Ticket.PRIORITY_NORMAL,
        )
        TicketAssignment.objects.create(
            ticket=ticket,
            technician=self.agent,
            assigned_by=self.manager,
            status=TicketAssignment.STATUS_ACTIVE,
        )
        self.api.force_authenticate(user=self.manager)

        response = self.api.post(
            reverse("sav_api:ticket-escalate", args=[ticket.pk]),
            {"target": "expert_then_head_sav"},
            format="json",
        )
        ticket.refresh_from_db()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(ticket.assigned_agent, self.manager)

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

        self.assertEqual(response.status_code, 404)
        self.assertFalse(Message.objects.filter(ticket=ticket, content="Tentative auditeur").exists())

    def test_qa_and_support_are_not_manager_profiles(self):
        for user in [self.qa_user, self.agent, self.dispatcher]:
            self.api.force_authenticate(user=user)
            response = self.api.post(
                reverse("sav_api:user-list"),
                {
                    "username": f"created_by_{user.username}",
                    "password": "secret123",
                    "role": User.ROLE_SUPPORT,
                    "organization": self.organization.id,
                },
                format="json",
            )
            self.assertEqual(response.status_code, 403)
