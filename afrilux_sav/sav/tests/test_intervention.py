import json

from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone

from .base import SavPlatformTests
from ..models import (
    Intervention,
    Ticket,
    TicketAssignment,
)


class InterventionTests(SavPlatformTests):
    def test_client_can_confirm_resolution(self):
        ticket = Ticket.objects.create(
            client=self.client_user,
            product=self.product,
            title="Validation client",
            description="Le client confirme la resolution.",
            category=Ticket.CATEGORY_BREAKDOWN,
            status=Ticket.STATUS_RESOLVED,
            priority=Ticket.PRIORITY_NORMAL,
            resolved_at=timezone.now(),
        )
        self.api.force_authenticate(user=self.client_user)

        response = self.api.post(reverse("sav_api:ticket-confirm-resolution", args=[ticket.pk]), {})
        ticket.refresh_from_db()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(ticket.status, Ticket.STATUS_CLOSED)
        self.assertIsNotNone(ticket.closed_at)

    def test_client_validates_intervention_start_and_finish(self):
        ticket = Ticket.objects.create(
            client=self.client_user,
            product=self.product,
            assigned_agent=self.agent,
            title="Validation debut fin",
            description="Le client valide le debut puis la fin de l'intervention.",
            category=Ticket.CATEGORY_BREAKDOWN,
            status=Ticket.STATUS_ASSIGNED,
            priority=Ticket.PRIORITY_NORMAL,
        )
        TicketAssignment.objects.create(
            ticket=ticket,
            technician=self.agent,
            assigned_by=self.manager,
            status=TicketAssignment.STATUS_ACTIVE,
        )
        Intervention.objects.create(
            organization=self.organization,
            ticket=ticket,
            agent=self.agent,
            intervention_type=Intervention.TYPE_ON_SITE,
            status=Intervention.STATUS_PLANNED,
            action_taken="Intervention a valider par le client.",
        )

        self.api.force_authenticate(user=self.agent)
        start_request = self.api.post(reverse("sav_api:ticket-request-start", args=[ticket.pk]), {})
        ticket.refresh_from_db()
        self.assertEqual(start_request.status_code, 200)
        self.assertEqual(ticket.status, Ticket.STATUS_START_REQUESTED)

        self.api.force_authenticate(user=self.client_user)
        start_validation = self.api.post(reverse("sav_api:ticket-validate-start", args=[ticket.pk]), {})
        ticket.refresh_from_db()
        intervention = ticket.interventions.order_by("-created_at").first()
        self.assertEqual(start_validation.status_code, 200)
        self.assertEqual(ticket.status, Ticket.STATUS_IN_PROGRESS)
        self.assertIsNotNone(intervention.client_validated_start_at)
        self.assertEqual(intervention.started_at, intervention.client_validated_start_at)

        self.api.force_authenticate(user=self.agent)
        finish_request = self.api.post(reverse("sav_api:ticket-request-finish", args=[ticket.pk]), {})
        ticket.refresh_from_db()
        self.assertEqual(finish_request.status_code, 200)
        self.assertEqual(ticket.status, Ticket.STATUS_FINISH_REQUESTED)

        self.api.force_authenticate(user=self.client_user)
        finish_validation = self.api.post(reverse("sav_api:ticket-validate-finish", args=[ticket.pk]), {})
        ticket.refresh_from_db()
        intervention.refresh_from_db()
        self.assertEqual(finish_validation.status_code, 200)
        self.assertEqual(ticket.status, Ticket.STATUS_DONE)
        self.assertIsNotNone(intervention.client_validated_finish_at)
        self.assertEqual(intervention.finished_at, intervention.client_validated_finish_at)
        self.assertIsNotNone(intervention.time_spent_minutes)

        signature = SimpleUploadedFile("signature.png", b"fake-signature", content_type="image/png")
        photo = SimpleUploadedFile("intervention.png", b"fake-photo", content_type="image/png")
        self.api.force_authenticate(user=self.agent)
        close_response = self.api.post(
            reverse("sav_api:ticket-close-dossier", args=[ticket.pk]),
            {
                "diagnosis": "Alimentation defectueuse.",
                "action_taken": "Remplacement et tests de fonctionnement.",
                "parts": json.dumps([{"designation": "Bloc alimentation", "quantity": 1}]),
                "client_name": "Client Test",
                "signature": signature,
                "photos": photo,
            },
            format="multipart",
        )
        ticket.refresh_from_db()
        intervention.refresh_from_db()

        self.assertEqual(close_response.status_code, 200)
        self.assertEqual(ticket.status, Ticket.STATUS_CLOSED)
        self.assertTrue(intervention.report_pdf)
        self.assertTrue(intervention.client_signature_file)
        self.assertTrue(intervention.media.exists())
