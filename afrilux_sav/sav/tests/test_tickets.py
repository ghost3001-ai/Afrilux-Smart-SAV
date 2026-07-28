from django.core.files.uploadedfile import SimpleUploadedFile
from django.forms import HiddenInput
from django.urls import reverse
from django.utils import timezone

from .base import SavPlatformTests
from ..forms import TicketCreateForm
from ..models import (
    Product,
    Ticket,
    TicketAttachment,
    TicketFeedback,
    Message,
    User,
)


class TicketTests(SavPlatformTests):
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

    def test_agent_can_list_clients_for_mobile_ticket_creation(self):
        self.api.force_authenticate(user=self.agent)

        response = self.api.get(reverse("sav_api:user-list"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["id"], self.client_user.id)
        self.assertEqual(response.data[0]["organization_name"], self.organization.display_name)

    def test_ticket_queryset_ignores_removed_fraud_filter(self):
        Ticket.objects.create(
            client=self.client_user,
            product=self.product,
            title="Bug applicatif",
            description="Je signale une erreur dans l'application.",
            category=Ticket.CATEGORY_BUG,
            status=Ticket.STATUS_NEW,
            priority=Ticket.PRIORITY_HIGH,
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
        payload = response.data["results"] if isinstance(response.data, dict) and "results" in response.data else response.data
        self.assertEqual(len(payload), 2)
        self.assertNotIn("suspected_fraud", payload[0])

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
        created_ticket = Ticket.objects.get(
            title="Demande portail web",
            client=self.client_user,
            product_label="Split mural 12000 BTU",
        )
        self.assertRedirects(response, reverse("ticket-detail", args=[created_ticket.pk]))
        self.assertEqual(
            created_ticket.status,
            Ticket.STATUS_PENDING_ASSIGNMENT,
        )

    def test_client_can_follow_pending_assignment_ticket_detail(self):
        ticket = Ticket.objects.create(
            client=self.client_user,
            created_by=self.client_user,
            title="Demande en attente",
            description="Ticket cree par le client en attente d'assignation.",
            category=Ticket.CATEGORY_BREAKDOWN,
            channel=Ticket.CHANNEL_WEB,
            status=Ticket.STATUS_PENDING_ASSIGNMENT,
            priority=Ticket.PRIORITY_NORMAL,
        )
        self.client.force_login(self.client_user)

        response = self.client.get(reverse("ticket-detail", args=[ticket.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Nouveau")
        self.assertContains(response, ticket.reference)

    def test_client_sees_pending_assignment_ticket_in_api_followup(self):
        ticket = Ticket.objects.create(
            client=self.client_user,
            created_by=self.client_user,
            title="Demande API en attente",
            description="Ticket visible au client avant assignation.",
            category=Ticket.CATEGORY_BREAKDOWN,
            channel=Ticket.CHANNEL_WEB,
            status=Ticket.STATUS_PENDING_ASSIGNMENT,
            priority=Ticket.PRIORITY_NORMAL,
        )
        self.api.force_authenticate(user=self.client_user)

        detail_response = self.api.get(reverse("sav_api:ticket-detail", args=[ticket.pk]))
        list_response = self.api.get(reverse("sav_api:ticket-list"))

        self.assertEqual(detail_response.status_code, 200)
        self.assertEqual(detail_response.data["public_status"], "Nouveau")
        payload = list_response.data["results"] if isinstance(list_response.data, dict) and "results" in list_response.data else list_response.data
        self.assertIn(ticket.reference, {item["reference"] for item in payload})

    def test_client_can_create_and_follow_ticket_via_api(self):
        self.api.force_authenticate(user=self.client_user)

        response = self.api.post(
            reverse("sav_api:ticket-list"),
            {
                "product_label": "Onduleur bureau accueil",
                "title": "Demande API client",
                "description": "Le client cree une demande depuis une application connectee.",
                "category": Ticket.CATEGORY_BREAKDOWN,
                "channel": Ticket.CHANNEL_API,
                "priority": Ticket.PRIORITY_HIGH,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        ticket = Ticket.objects.get(title="Demande API client")
        self.assertEqual(ticket.client, self.client_user)
        self.assertEqual(ticket.status, Ticket.STATUS_PENDING_ASSIGNMENT)
        self.assertEqual(ticket.priority, Ticket.PRIORITY_NORMAL)
        self.assertEqual(response.data["public_status"], "Nouveau")

        detail_response = self.api.get(reverse("sav_api:ticket-detail", args=[ticket.pk]))
        self.assertEqual(detail_response.status_code, 200)
        self.assertEqual(detail_response.data["reference"], ticket.reference)

    def test_technician_does_not_see_client_pending_assignment_ticket(self):
        ticket = Ticket.objects.create(
            client=self.client_user,
            created_by=self.client_user,
            title="Demande cachee technicien",
            description="Ticket client non encore assigne.",
            category=Ticket.CATEGORY_BREAKDOWN,
            channel=Ticket.CHANNEL_WEB,
            status=Ticket.STATUS_PENDING_ASSIGNMENT,
            priority=Ticket.PRIORITY_NORMAL,
        )
        self.api.force_authenticate(user=self.agent)

        detail_response = self.api.get(reverse("sav_api:ticket-detail", args=[ticket.pk]))
        list_response = self.api.get(reverse("sav_api:ticket-list"))

        self.assertEqual(detail_response.status_code, 404)
        payload = list_response.data["results"] if isinstance(list_response.data, dict) and "results" in list_response.data else list_response.data
        self.assertNotIn(ticket.reference, {item["reference"] for item in payload})

    def test_ticket_create_form_shows_client_field_for_client_user(self):
        form = TicketCreateForm(user=self.client_user)

        self.assertNotIsInstance(form.fields["client"].widget, HiddenInput)
        self.assertQuerySetEqual(form.fields["client"].queryset, [self.client_user], transform=lambda user: user)
        self.assertEqual(form.fields["client"].initial, self.client_user)
        self.assertFalse(form.fields["client"].required)

    def test_ticket_form_hides_sla_and_limits_channels_by_role(self):
        client_form = TicketCreateForm(user=self.client_user)
        agent_form = TicketCreateForm(user=self.manager)
        submitted_client_form = TicketCreateForm(
            data={
                "title": "Canal imposé par le portail",
                "description": "Le client ne doit pas choisir le canal.",
                "category": Ticket.CATEGORY_BREAKDOWN,
                "channel": Ticket.CHANNEL_EMAIL,
            },
            user=self.client_user,
        )

        self.assertNotIn("sla_deadline", client_form.fields)
        self.assertIsInstance(client_form.fields["channel"].widget, HiddenInput)
        self.assertEqual(client_form.fields["channel"].initial, Ticket.CHANNEL_WEB)
        self.assertTrue(submitted_client_form.is_valid())
        self.assertEqual(submitted_client_form.cleaned_data["channel"], Ticket.CHANNEL_WEB)
        self.assertEqual(
            [choice[0] for choice in agent_form.fields["channel"].choices],
            [Ticket.CHANNEL_PHONE, Ticket.CHANNEL_EMAIL, Ticket.CHANNEL_WHATSAPP, Ticket.CHANNEL_WEB],
        )

    def test_ticket_conversation_is_private_to_client_and_assigned_team(self):
        ticket = Ticket.objects.create(
            client=self.client_user,
            product=self.product,
            assigned_agent=self.agent,
            title="Conversation privée",
            description="Seuls les participants peuvent écrire.",
            category=Ticket.CATEGORY_BREAKDOWN,
            channel=Ticket.CHANNEL_WEB,
            status=Ticket.STATUS_ASSIGNED,
        )
        ticket.team_members.add(self.technician)
        message = Message.objects.create(
            ticket=ticket,
            sender=self.agent,
            recipient=self.client_user,
            message_type=Message.TYPE_PUBLIC,
            channel=Message.CHANNEL_PORTAL,
            direction=Message.DIRECTION_OUTBOUND,
            content="Votre dossier est pris en charge.",
        )

        self.api.force_authenticate(user=self.other_client)
        hidden_response = self.api.get(reverse("sav_api:message-list"))
        hidden_payload = hidden_response.data["results"] if isinstance(hidden_response.data, dict) else hidden_response.data
        self.assertNotIn(message.id, {item["id"] for item in hidden_payload})
        forbidden_response = self.api.post(
            reverse("sav_api:message-list"),
            {"ticket": ticket.id, "content": "Je ne dois pas pouvoir écrire.", "channel": Message.CHANNEL_PORTAL},
            format="json",
        )
        self.assertEqual(forbidden_response.status_code, 403)

        self.api.force_authenticate(user=self.technician)
        team_response = self.api.get(reverse("sav_api:message-list"))
        team_payload = team_response.data["results"] if isinstance(team_response.data, dict) else team_response.data
        self.assertIn(message.id, {item["id"] for item in team_payload})

    def test_ticket_create_form_uses_inline_client_fields_for_internal_user(self):
        form = TicketCreateForm(user=self.manager)

        self.assertEqual(form.fields["client_mode"].initial, TicketCreateForm.CLIENT_MODE_EXISTING)
        self.assertNotIsInstance(form.fields["client_mode"].widget, HiddenInput)
        self.assertNotIsInstance(form.fields["existing_client_email"].widget, HiddenInput)
        self.assertIsInstance(form.fields["client"].widget, HiddenInput)
        self.assertFalse(form.fields["client"].required)
        self.assertNotIsInstance(form.fields["client_name"].widget, HiddenInput)
        self.assertNotIsInstance(form.fields["client_email"].widget, HiddenInput)
        self.assertNotIsInstance(form.fields["client_password1"].widget, HiddenInput)
        self.assertNotIsInstance(form.fields["client_password2"].widget, HiddenInput)

    def test_internal_user_must_enter_existing_client_email_when_using_existing_mode(self):
        self.client.force_login(self.manager)

        response = self.client.post(
            reverse("ticket-create"),
            {
                "client_mode": TicketCreateForm.CLIENT_MODE_EXISTING,
                "product_label": "Serveur ondule",
                "title": "Ticket sans email client",
                "description": "Creation de ticket sans recherche email.",
                "category": Ticket.CATEGORY_MAINTENANCE,
                "channel": Ticket.CHANNEL_PHONE,
                "status": Ticket.STATUS_NEW,
                "priority": Ticket.PRIORITY_NORMAL,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.context["form"].errors["existing_client_email"],
            ["La recherche du client existant est obligatoire."],
        )
        self.assertFalse(Ticket.objects.filter(title="Ticket sans email client").exists())

    def test_internal_user_can_attach_ticket_to_existing_client_by_email(self):
        self.client.force_login(self.manager)

        response = self.client.post(
            reverse("ticket-create"),
            {
                "client_mode": TicketCreateForm.CLIENT_MODE_EXISTING,
                "existing_client_email": self.client_user.email,
                "product_label": "Serveur ondule",
                "title": "Ticket pour client existant",
                "description": "Creation de ticket avec rattachement auto par email.",
                "category": Ticket.CATEGORY_MAINTENANCE,
                "channel": Ticket.CHANNEL_PHONE,
                "status": Ticket.STATUS_NEW,
                "priority": Ticket.PRIORITY_NORMAL,
            },
        )

        self.assertEqual(response.status_code, 302)
        created_ticket = Ticket.objects.get(title="Ticket pour client existant")
        self.assertEqual(created_ticket.client, self.client_user)

    def test_internal_user_can_create_ticket_with_initial_assignee(self):
        self.client.force_login(self.manager)

        response = self.client.post(
            reverse("ticket-create"),
            {
                "client_mode": TicketCreateForm.CLIENT_MODE_EXISTING,
                "existing_client_email": self.client_user.email,
                "product_label": "Serveur ondule",
                "assigned_agent": self.agent.pk,
                "title": "Ticket assigne a la creation",
                "description": "Creation de ticket avec affectation initiale.",
                "category": Ticket.CATEGORY_MAINTENANCE,
                "channel": Ticket.CHANNEL_PHONE,
                "status": Ticket.STATUS_NEW,
                "priority": Ticket.PRIORITY_NORMAL,
            },
        )

        self.assertEqual(response.status_code, 302)
        created_ticket = Ticket.objects.get(title="Ticket assigne a la creation")
        self.assertEqual(created_ticket.client, self.client_user)
        self.assertEqual(created_ticket.assigned_agent, self.agent)
        self.assertEqual(created_ticket.status, Ticket.STATUS_ASSIGNED)

    def test_admin_can_create_ticket_via_web_portal(self):
        admin_user = User.objects.create_user(
            username="admin_ticket_create",
            password="secret123",
            organization=self.organization,
            role=User.ROLE_ADMIN,
            is_staff=True,
        )
        self.client.force_login(admin_user)

        response = self.client.post(
            reverse("ticket-create"),
            {
                "client_mode": TicketCreateForm.CLIENT_MODE_EXISTING,
                "existing_client_email": self.client_user.email,
                "product_label": "Copieur accueil",
                "title": "Ticket cree par administrateur",
                "description": "Creation de ticket depuis le centre administrateur.",
                "category": Ticket.CATEGORY_BREAKDOWN,
                "channel": Ticket.CHANNEL_PHONE,
                "status": Ticket.STATUS_NEW,
                "priority": Ticket.PRIORITY_HIGH,
            },
        )

        self.assertEqual(response.status_code, 302)
        created_ticket = Ticket.objects.get(title="Ticket cree par administrateur")
        self.assertEqual(created_ticket.client, self.client_user)
        self.assertEqual(created_ticket.created_by, admin_user)
        self.assertEqual(created_ticket.organization, self.organization)
        self.assertTrue(created_ticket.sla_deadline)

    def test_admin_can_create_ticket_via_api(self):
        admin_user = User.objects.create_user(
            username="admin_ticket_api",
            password="secret123",
            organization=self.organization,
            role=User.ROLE_ADMIN,
            is_staff=True,
        )
        self.api.force_authenticate(user=admin_user)

        response = self.api.post(
            reverse("sav_api:ticket-list"),
            {
                "client": self.client_user.pk,
                "product_label": "Groupe electrogene 20kVA",
                "title": "Ticket API administrateur",
                "description": "Creation de ticket administrateur via API REST.",
                "category": Ticket.CATEGORY_BREAKDOWN,
                "channel": Ticket.CHANNEL_PHONE,
                "status": Ticket.STATUS_NEW,
                "priority": Ticket.PRIORITY_NORMAL,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        created_ticket = Ticket.objects.get(title="Ticket API administrateur")
        self.assertEqual(created_ticket.client, self.client_user)
        self.assertEqual(created_ticket.created_by, admin_user)
        self.assertTrue(created_ticket.reference.startswith("ASS-SAV-"))

    def test_internal_user_gets_error_when_existing_client_email_is_unknown(self):
        self.client.force_login(self.manager)

        response = self.client.post(
            reverse("ticket-create"),
            {
                "client_mode": TicketCreateForm.CLIENT_MODE_EXISTING,
                "existing_client_email": "inconnu@example.com",
                "product_label": "Serveur ondule",
                "title": "Ticket client inconnu",
                "description": "Aucun compte client ne correspond a cet email.",
                "category": Ticket.CATEGORY_MAINTENANCE,
                "channel": Ticket.CHANNEL_PHONE,
                "status": Ticket.STATUS_NEW,
                "priority": Ticket.PRIORITY_NORMAL,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Aucun client existant ne correspond a cette recherche.")
        self.assertFalse(Ticket.objects.filter(title="Ticket client inconnu").exists())

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

    def test_internal_user_is_prompted_to_use_existing_mode_when_email_already_exists(self):
        self.client.force_login(self.manager)

        response = self.client.post(
            reverse("ticket-create"),
            {
                "client_mode": TicketCreateForm.CLIENT_MODE_NEW,
                "client_name": "Client Deja La",
                "client_email": self.client_user.email,
                "client_password1": "ClientPass123!",
                "client_password2": "ClientPass123!",
                "product_label": "Compresseur",
                "title": "Tentative doublon client",
                "description": "Le compte client existe deja.",
                "category": Ticket.CATEGORY_BREAKDOWN,
                "channel": Ticket.CHANNEL_PHONE,
                "status": Ticket.STATUS_NEW,
                "priority": Ticket.PRIORITY_NORMAL,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.context["form"].errors["client_email"],
            ["Un compte client existe deja avec cet email. Utilisez le mode 'Client existant'."],
        )
        self.assertFalse(Ticket.objects.filter(title="Tentative doublon client").exists())

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

    def test_ticket_reference_uses_cdc_format(self):
        ticket = Ticket.objects.create(
            client=self.client_user,
            product=self.product,
            title="Reference CDC",
            description="Le numero doit suivre le format officiel.",
            category=Ticket.CATEGORY_BREAKDOWN,
            priority=Ticket.PRIORITY_NORMAL,
        )

        self.assertRegex(ticket.reference, r"^ASS-SAV-\d{2}-\d{4}-\d{5}$")

    def test_cdc_v3_equipment_status_and_ticket_domains_are_available(self):
        self.assertEqual(self.product.status, Product.STATUS_OPERATIONAL)
        self.product.status = Product.STATUS_ACTIVE
        self.product.save()
        self.product.refresh_from_db()
        self.assertEqual(self.product.status, Product.STATUS_OPERATIONAL)

        domain_values = {value for value, _label in Ticket.BUSINESS_DOMAIN_CHOICES}
        self.assertIn(Ticket.DOMAIN_CFAO, domain_values)
        self.assertIn(Ticket.DOMAIN_MONETICS, domain_values)
        self.assertIn(Ticket.DOMAIN_GEOLOCATION, domain_values)

    def test_client_can_reopen_resolved_ticket(self):
        ticket = Ticket.objects.create(
            client=self.client_user,
            product=self.product,
            title="Ticket resolu",
            description="Le client souhaite rouvrir le dossier.",
            category=Ticket.CATEGORY_BREAKDOWN,
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
        self.assertEqual(ticket.status, Ticket.STATUS_ASSIGNED)

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
