from rest_framework import filters, mixins, parsers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from ..models import Message, Ticket, TicketAttachment, TicketAssignment, TicketFeedback, User
from ..permissions import IsAuthenticatedSavUser, IsInternalUser, IsManagerUser, ReadOnlyForAuditors
from ..serializers import (
    MessageSerializer,
    TicketAttachmentSerializer,
    TicketAssignmentSerializer,
    TicketFeedbackSerializer,
    TicketSerializer,
    UserSerializer,
)
from ..services import (
    assign_ticket_to_technician,
    assign_ticket_to_team,
    can_create_ticket,
    can_participate_in_ticket_conversation,
    can_record_ticket_intervention,
    calculate_sentiment,
    compute_ticket_sla_deadline,
    close_sav_dossier,
    confirm_planning,
    continue_after_escalation_solution,
    credit_account_for_ticket,
    decline_ticket_escalation,
    escalate_ticket,
    ensure_assignment_intervention,
    is_internal_user,
    is_manager_user,
    log_audit_event,
    notify_ticket_status_change,
    notify_client_created_ticket,
    provide_escalation_solution,
    propose_planning,
    reassign_escalated_ticket,
    request_finish_intervention,
    request_start_intervention,
    request_ticket_escalation,
    run_automation_rules_for_ticket,
    scope_attachment_queryset,
    scope_message_queryset,
    scope_ticket_assignment_queryset,
    scope_ticket_feedback_queryset,
    scope_ticket_queryset,
    scope_user_queryset,
    ticket_conversation_participant_ids,
)
from ..comms import create_message_delivery_notifications
from ..models import AutomationRule, SupportSession
from ..services import scope_support_session_queryset
from ..serializers import SupportSessionSerializer
from .base import AuditedModelViewSet, _request_bool

import json
from datetime import datetime
from django.utils import timezone
from django.shortcuts import get_object_or_404


class TicketViewSet(AuditedModelViewSet):
    serializer_class = TicketSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = [
        "reference",
        "title",
        "description",
        "client__username",
        "client__company_name",
        "organization__name",
        "product_label",
        "product__name",
        "product__serial_number",
    ]
    ordering_fields = ["created_at", "updated_at", "priority", "sla_deadline"]

    def get_permissions(self):
        if self.action == "credit_account":
            return [IsAuthenticatedSavUser()]
        if self.action in {"confirm_resolution", "reopen"}:
            return [ReadOnlyForAuditors()]
        if self.action == "agentic_resolution":
            return [IsInternalUser()]
        if self.action in {"take_ownership", "close"}:
            return [IsInternalUser()]
        if self.action in {"assign"}:
            return [IsManagerUser()]
        if self.action == "run_automation":
            return [IsInternalUser()]
        if self.request.method == "POST":
            return [ReadOnlyForAuditors()]
        if self.request.method in {"PUT", "PATCH"}:
            return [IsInternalUser()]
        if self.request.method == "DELETE":
            return [IsInternalUser()]
        return [IsAuthenticatedSavUser()]

    def get_queryset(self):
        queryset = Ticket.objects.select_related(
            "client",
            "product",
            "assigned_agent",
            "feedback",
        ).prefetch_related(
            "messages",
            "attachments",
            "assignment_history",
            "interventions",
            "support_sessions",
            "account_credits",
        )
        status_value = self.request.query_params.get("status")
        priority = self.request.query_params.get("priority")
        assigned_agent = self.request.query_params.get("assigned_agent")
        assignment = self.request.query_params.get("assignment")
        client = self.request.query_params.get("client")
        urgent = self.request.query_params.get("urgent")
        queryset = scope_ticket_queryset(queryset, self.request.user)
        if status_value:
            queryset = queryset.filter(status=status_value)
        if priority:
            queryset = queryset.filter(priority=priority)
        if assigned_agent:
            queryset = queryset.filter(assigned_agent_id=assigned_agent)
        if assignment == "mine" and is_internal_user(self.request.user):
            queryset = queryset.filter(assigned_agent=self.request.user)
        if assignment == "unassigned" and is_internal_user(self.request.user):
            queryset = queryset.filter(assigned_agent__isnull=True)
        if client:
            queryset = queryset.filter(client_id=client)
        if urgent is not None and urgent.strip().lower() in {"true", "1", "yes", "oui"}:
            queryset = queryset.filter(priority__in=[Ticket.PRIORITY_HIGH, Ticket.PRIORITY_CRITICAL])
        return queryset

    def perform_create(self, serializer):
        if not can_create_ticket(self.request.user):
            raise PermissionDenied("Votre role ne permet pas de creer un ticket.")
        ticket_kwargs = {}
        ticket_kwargs["created_by"] = self.request.user
        if self.request.user.role == User.ROLE_CLIENT:
            ticket_kwargs["client"] = self.request.user
            serializer.validated_data["priority"] = Ticket.PRIORITY_NORMAL
            serializer.validated_data["status"] = Ticket.STATUS_PENDING_ASSIGNMENT
            serializer.validated_data["assigned_agent"] = None
            serializer.validated_data["channel"] = Ticket.CHANNEL_WEB
            client = self.request.user
        else:
            client = serializer.validated_data.get("client")
        initial_escalation_target = serializer.validated_data.pop("initial_escalation_target", "")
        if (
            client
            and is_internal_user(self.request.user)
            and not self.request.user.is_superuser
            and self.request.user.organization_id
            and client.organization_id != self.request.user.organization_id
        ):
            raise PermissionDenied("Vous ne pouvez pas creer un ticket pour une autre organisation.")
        instance = serializer.save(**ticket_kwargs)
        update_fields = []
        if instance.assigned_agent_id and instance.status == Ticket.STATUS_NEW:
            instance.status = Ticket.STATUS_ASSIGNED
            update_fields.append("status")
        if not instance.sla_deadline:
            instance.sla_deadline = compute_ticket_sla_deadline(instance.priority, organization=instance.organization)
            update_fields.append("sla_deadline")
        if update_fields:
            instance.save(update_fields=[*update_fields, "updated_at"])

        team_leader_id = serializer.validated_data.get("team_leader_id") or self.request.data.get("team_leader")
        team_members_ids = serializer.validated_data.get("team_members") or self.request.data.get("team_members", [])
        if isinstance(team_members_ids, str):
            team_members_ids = [int(x.strip()) for x in team_members_ids.split(",") if x.strip()]

        if team_leader_id and team_members_ids:
            try:
                leader = User.objects.get(pk=team_leader_id, is_active=True)
                members = User.objects.filter(pk__in=team_members_ids, is_active=True)
                if members.count() != len(set(team_members_ids)):
                    raise PermissionDenied("Un ou plusieurs membres sont introuvables.")
                assign_ticket_to_team(
                    instance,
                    leader=leader,
                    members=members,
                    actor=self.request.user,
                    note="Assignation d'equipe a la creation du ticket."
                )
                instance.refresh_from_db()
            except User.DoesNotExist:
                raise PermissionDenied(f"Le chef d'equipe avec l'ID {team_leader_id} est introuvable.")
            except ValueError as exc:
                raise PermissionDenied(str(exc))
        elif instance.assigned_agent_id:
            ensure_assignment_intervention(instance, actor=self.request.user, note="Affectation initiale a la creation du ticket.")
        elif self.request.user.role == User.ROLE_HEAD_SAV and initial_escalation_target:
            previous_status = instance.status
            try:
                escalate_ticket(
                    instance,
                    actor=self.request.user,
                    target=initial_escalation_target,
                    note="Escalade initiale depuis la creation du ticket.",
                    increase_priority=False,
                    notification_event_type="ticket_initial_escalation",
                )
            except ValueError as exc:
                raise PermissionDenied(str(exc)) from exc
            if instance.status != previous_status:
                notify_ticket_status_change(instance, previous_status, actor=self.request.user)

        self.audit("ticket_created", instance)
        if self.request.user.role == User.ROLE_CLIENT:
            notify_client_created_ticket(instance, actor=self.request.user)
        run_automation_rules_for_ticket(instance, actor=self.request.user, trigger_event=AutomationRule.TRIGGER_TICKET_CREATED)

    def perform_update(self, serializer):
        if self.request.user.role != User.ROLE_HEAD_SAV:
            raise PermissionDenied("Seul le responsable SAV peut modifier directement un ticket.")
        if serializer.instance.status == Ticket.STATUS_CLOSED:
            raise PermissionDenied("Un ticket cloture est irreversible. Creez un nouveau ticket pour une correction.")
        previous_status = serializer.instance.status
        previous_assigned_agent_id = serializer.instance.assigned_agent_id
        client = serializer.validated_data.get("client", serializer.instance.client)
        if (
            client
            and is_internal_user(self.request.user)
            and not self.request.user.is_superuser
            and self.request.user.organization_id
            and client.organization_id != self.request.user.organization_id
        ):
            raise PermissionDenied("Vous ne pouvez pas deplacer ce ticket vers une autre organisation.")
        if serializer.validated_data.get("assigned_agent") and (
            serializer.instance.status in {Ticket.STATUS_NEW, Ticket.STATUS_PENDING_ASSIGNMENT}
            or not previous_assigned_agent_id
        ):
            serializer.validated_data["status"] = Ticket.STATUS_ASSIGNED
        instance = serializer.save()
        if serializer.validated_data.get("priority") and instance.is_open:
            instance.sla_deadline = compute_ticket_sla_deadline(instance.priority, organization=instance.organization)
            instance.save(update_fields=["sla_deadline", "updated_at"])
        if instance.assigned_agent_id and instance.assigned_agent_id != previous_assigned_agent_id:
            ensure_assignment_intervention(instance, actor=self.request.user, note="Affectation mise a jour depuis l'API.")
        self.audit("ticket_updated", instance)
        notify_ticket_status_change(instance, previous_status, actor=self.request.user)
        trigger_event = AutomationRule.TRIGGER_TICKET_OVERDUE if instance.is_overdue else AutomationRule.TRIGGER_TICKET_UPDATED
        run_automation_rules_for_ticket(instance, actor=self.request.user, trigger_event=trigger_event)

    @action(detail=True, methods=["post"])
    def agentic_resolution(self, request, pk=None):
        from ..services import apply_agentic_resolution
        ticket = self.get_object()
        result = apply_agentic_resolution(ticket, approved_by=request.user)
        return Response(result)

    @action(detail=True, methods=["post"], permission_classes=[IsInternalUser])
    def take_ownership(self, request, pk=None):
        ticket = self.get_object()
        if not request.user.is_ticket_assignment_eligible:
            return Response(
                {"detail": "Prise en charge autorisee uniquement pour les responsables d'escalade ou techniciens disponibles."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        previous_status = ticket.status
        ticket.assigned_agent = request.user
        if ticket.status in {Ticket.STATUS_NEW, Ticket.STATUS_PENDING_ASSIGNMENT, Ticket.STATUS_ASSIGNED, Ticket.STATUS_WAITING_PART}:
            ticket.status = Ticket.STATUS_ASSIGNED
        ticket.save(update_fields=["assigned_agent", "status", "updated_at"])
        ensure_assignment_intervention(ticket, actor=request.user, note="Prise en charge manuelle du ticket.")
        self.audit("ticket_taken_ownership", ticket, {"assigned_agent": request.user.id})
        notify_ticket_status_change(ticket, previous_status, actor=request.user)
        return Response(self.get_serializer(ticket).data)

    @action(detail=True, methods=["post"], permission_classes=[IsInternalUser], url_path="assign")
    def assign(self, request, pk=None):
        ticket = self.get_object()
        previous_status = ticket.status
        technician_id = request.data.get("technician") or request.data.get("assigned_agent")
        if not technician_id:
            return Response({"detail": "La cible d'affectation est obligatoire."}, status=status.HTTP_400_BAD_REQUEST)
        assignment_queryset = User.objects.filter(
            role__in=User.ASSIGNABLE_ROLES,
            technician_status="available",
            is_active=True,
        )
        technician = get_object_or_404(
            scope_user_queryset(assignment_queryset, request.user),
            pk=technician_id,
        )
        if technician.role in set(User.FRONTLINE_ROLES + User.FIELD_TECHNICIAN_ROLES):
            try:
                assign_ticket_to_technician(
                    ticket,
                    technician,
                    actor=request.user,
                    note=str(request.data.get("note", "")).strip() or "Affectation depuis l'API.",
                    force=_request_bool(request.data, "force_assignment"),
                    force_reason=str(request.data.get("force_reason", "")).strip(),
                )
            except ValueError as exc:
                raise PermissionDenied(str(exc)) from exc
            self.audit("ticket_assigned_to_technician", ticket, {"assigned_agent": technician.id})
            notify_ticket_status_change(ticket, previous_status, actor=request.user)
            return Response(self.get_serializer(ticket).data)
        if request.user.role != User.ROLE_HEAD_SAV:
            raise PermissionDenied("Seul le responsable SAV peut affecter une cible d'escalade.")
        if technician.role not in set(User.ESCALATION_TARGET_ROLES):
            raise PermissionDenied("La cible doit etre un responsable d'escalade ou un technicien.")
        ticket.assigned_agent = technician
        if ticket.status in {Ticket.STATUS_NEW, Ticket.STATUS_PENDING_ASSIGNMENT, Ticket.STATUS_WAITING_PART, Ticket.STATUS_REASSIGNED}:
            ticket.status = Ticket.STATUS_ASSIGNED
        ticket.save(update_fields=["assigned_agent", "status", "updated_at"])
        ensure_assignment_intervention(ticket, actor=request.user, note="Affectation explicite du responsable SAV.")
        self.audit("ticket_assigned", ticket, {"assigned_agent": technician.id})
        notify_ticket_status_change(ticket, previous_status, actor=request.user)
        return Response(self.get_serializer(ticket).data)

    @action(detail=True, methods=["post"], permission_classes=[IsInternalUser], url_path="assign-team")
    def assign_team(self, request, pk=None):
        ticket = self.get_object()
        previous_status = ticket.status
        leader_id = request.data.get("leader") or request.data.get("team_leader")
        member_ids = request.data.get("members") or request.data.get("team_members") or []
        if isinstance(member_ids, str):
            member_ids = [item.strip() for item in member_ids.split(",") if item.strip()]
        if not leader_id:
            return Response({"detail": "Le chef d'equipe est obligatoire."}, status=status.HTTP_400_BAD_REQUEST)
        if not member_ids:
            return Response({"detail": "Selectionnez au moins un membre."}, status=status.HTTP_400_BAD_REQUEST)
        technician_queryset = User.objects.filter(
            role__in=User.ASSIGNABLE_ROLES,
            technician_status="available",
            is_active=True,
        )
        leader = get_object_or_404(scope_user_queryset(technician_queryset, request.user), pk=leader_id)
        members = list(scope_user_queryset(technician_queryset, request.user).filter(pk__in=member_ids))
        if len(members) != len(set(str(item) for item in member_ids)):
            return Response({"detail": "Un ou plusieurs membres sont introuvables."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            result = assign_ticket_to_team(
                ticket,
                leader=leader,
                members=members,
                actor=request.user,
                note=str(request.data.get("note", "")).strip(),
                force=_request_bool(request.data, "force_assignment"),
                force_reason=str(request.data.get("force_reason", "")).strip(),
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        notify_ticket_status_change(ticket, previous_status, actor=request.user)
        payload = self.get_serializer(ticket).data
        payload["team_assignment"] = result
        return Response(payload)

    @action(detail=True, methods=["post"], permission_classes=[IsInternalUser])
    def escalate(self, request, pk=None):
        ticket = self.get_object()
        previous_status = ticket.status
        try:
            target = str(request.data.get("target", "")).strip()
            if target:
                result = escalate_ticket(
                    ticket,
                    actor=request.user,
                    note=str(request.data.get("note", "")).strip(),
                    target=target,
                )
            else:
                result = request_ticket_escalation(
                    ticket,
                    actor=request.user,
                    reason=str(request.data.get("reason") or request.data.get("note") or "").strip(),
                )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        if ticket.status != previous_status:
            notify_ticket_status_change(ticket, previous_status, actor=request.user)
        payload = self.get_serializer(ticket).data
        payload["escalation"] = result
        return Response(payload)

    @action(detail=True, methods=["post"], permission_classes=[IsInternalUser], url_path="escalation-solution")
    def escalation_solution(self, request, pk=None):
        ticket = self.get_object()
        previous_status = ticket.status
        try:
            provide_escalation_solution(
                ticket,
                actor=request.user,
                solution=str(request.data.get("solution", "")).strip(),
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        notify_ticket_status_change(ticket, previous_status, actor=request.user)
        return Response(self.get_serializer(ticket).data)

    @action(detail=True, methods=["post"], permission_classes=[IsInternalUser], url_path="escalation-continue")
    def escalation_continue(self, request, pk=None):
        ticket = self.get_object()
        previous_status = ticket.status
        try:
            continue_after_escalation_solution(ticket, actor=request.user)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        notify_ticket_status_change(ticket, previous_status, actor=request.user)
        return Response(self.get_serializer(ticket).data)

    @action(detail=True, methods=["post"], permission_classes=[IsInternalUser], url_path="escalation-decline")
    def escalation_decline(self, request, pk=None):
        ticket = self.get_object()
        previous_status = ticket.status
        try:
            decline_ticket_escalation(
                ticket,
                actor=request.user,
                reason=str(request.data.get("reason", "")).strip(),
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        notify_ticket_status_change(ticket, previous_status, actor=request.user)
        return Response(self.get_serializer(ticket).data)

    @action(detail=True, methods=["post"], permission_classes=[IsInternalUser], url_path="escalation-reassign")
    def escalation_reassign(self, request, pk=None):
        ticket = self.get_object()
        previous_status = ticket.status
        technician_id = request.data.get("technician") or request.data.get("assigned_agent")
        if not technician_id:
            return Response({"detail": "Le technicien cible est obligatoire."}, status=status.HTTP_400_BAD_REQUEST)
        technician = get_object_or_404(
            scope_user_queryset(User.objects.filter(role=User.ROLE_TECHNICIAN, is_active=True), request.user),
            pk=technician_id,
        )
        try:
            reassign_escalated_ticket(
                ticket,
                technician,
                actor=request.user,
                note=str(request.data.get("note", "")).strip(),
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        notify_ticket_status_change(ticket, previous_status, actor=request.user)
        return Response(self.get_serializer(ticket).data)

    @action(detail=True, methods=["post"])
    def reopen(self, request, pk=None):
        ticket = self.get_object()
        previous_status = ticket.status
        if ticket.status not in {Ticket.STATUS_RESOLVED, Ticket.STATUS_CLOSED}:
            return Response({"detail": "Seuls les tickets resolus ou fermes peuvent etre rouverts."}, status=status.HTTP_400_BAD_REQUEST)
        if request.user.role == User.ROLE_CLIENT:
            ticket.status = Ticket.STATUS_NEW
        elif ticket.assigned_agent_id:
            ticket.status = Ticket.STATUS_ASSIGNED
        else:
            ticket.status = Ticket.STATUS_NEW
        ticket.resolved_at = None
        ticket.closed_at = None
        ticket.save(update_fields=["status", "resolved_at", "closed_at", "updated_at"])
        Message.objects.create(
            ticket=ticket,
            sender=request.user,
            message_type=Message.TYPE_PUBLIC if request.user.role == User.ROLE_CLIENT else Message.TYPE_INTERNAL,
            channel=Message.CHANNEL_PORTAL,
            direction=Message.DIRECTION_INBOUND if request.user.role == User.ROLE_CLIENT else Message.DIRECTION_INTERNAL,
            content="Le ticket a ete rouvert pour reprise en charge.",
            sentiment_score=calculate_sentiment("Le ticket a ete rouvert pour reprise en charge."),
        )
        self.audit("ticket_reopened", ticket, {"actor_role": request.user.role})
        notify_ticket_status_change(ticket, previous_status, actor=request.user)
        return Response(self.get_serializer(ticket).data)

    @action(detail=True, methods=["post"], url_path="propose-planning")
    def propose_planning_action(self, request, pk=None):
        ticket = self.get_object()
        previous_status = ticket.status
        scheduled_at_str = request.data.get("scheduled_at")
        if not scheduled_at_str:
            return Response({"detail": "La date 'scheduled_at' est obligatoire."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            scheduled_at = datetime.fromisoformat(scheduled_at_str)
            if timezone.is_naive(scheduled_at):
                scheduled_at = timezone.make_aware(scheduled_at)
            propose_planning(ticket, scheduled_at, actor=request.user)
            notify_ticket_status_change(ticket, previous_status, actor=request.user)
            return Response({"detail": "Planification proposee.", "scheduled_at": scheduled_at.isoformat(), "status": ticket.status})
        except (ValueError, TypeError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["post"], url_path="confirm-planning")
    def confirm_planning_action(self, request, pk=None):
        ticket = self.get_object()
        previous_status = ticket.status
        accepted = request.data.get("accepted", True)
        accepted = str(accepted).strip().lower() not in {"false", "0", "non", "no", "refuse", "refus"}
        try:
            confirm_planning(ticket, accepted=accepted, actor=request.user)
            notify_ticket_status_change(ticket, previous_status, actor=request.user)
            return Response({"detail": "Action enregistree.", "status": ticket.status})
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["post"], url_path="request-start")
    def request_start(self, request, pk=None):
        ticket = self.get_object()
        previous_status = ticket.status
        try:
            request_start_intervention(ticket, actor=request.user)
            notify_ticket_status_change(ticket, previous_status, actor=request.user)
            return Response({"detail": "Demande de debut envoyee au client."})
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["post"], url_path="validate-start")
    def validate_start(self, request, pk=None):
        from ..services import validate_start_intervention
        ticket = self.get_object()
        previous_status = ticket.status
        impossible = request.data.get("impossible", False)
        impossible = str(impossible).strip().lower() in {"true", "1", "oui", "yes"}
        reason = request.data.get("reason", "")
        photo = request.FILES.get("photo")
        try:
            validate_start_intervention(ticket, actor=request.user, impossible=impossible, reason=reason, photo=photo)
            notify_ticket_status_change(ticket, previous_status, actor=request.user)
            return Response({"detail": "Debut d'intervention valide.", "status": ticket.status})
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["post"], url_path="request-finish")
    def request_finish(self, request, pk=None):
        ticket = self.get_object()
        previous_status = ticket.status
        try:
            request_finish_intervention(ticket, actor=request.user)
            notify_ticket_status_change(ticket, previous_status, actor=request.user)
            return Response({"detail": "Demande de fin envoyee au client."})
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["post"], url_path="validate-finish")
    def validate_finish(self, request, pk=None):
        from ..services import validate_finish_intervention
        ticket = self.get_object()
        previous_status = ticket.status
        impossible = request.data.get("impossible", False)
        impossible = str(impossible).strip().lower() in {"true", "1", "oui", "yes"}
        reason = request.data.get("reason", "")
        photo = request.FILES.get("photo")
        try:
            validate_finish_intervention(ticket, actor=request.user, impossible=impossible, reason=reason, photo=photo)
            notify_ticket_status_change(ticket, previous_status, actor=request.user)
            return Response({"detail": "Fin d'intervention validee.", "status": ticket.status})
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["post"], url_path="close-dossier")
    def close_dossier(self, request, pk=None):
        ticket = self.get_object()
        previous_status = ticket.status
        diagnosis = request.data.get("diagnosis", "")
        action_taken = request.data.get("action_taken", "")
        parts = request.data.get("parts", [])
        if isinstance(parts, str):
            parts = parts.strip()
            if parts.startswith("["):
                try:
                    parts = json.loads(parts)
                except json.JSONDecodeError:
                    return Response({"detail": "Le JSON des pieces utilisees est invalide."}, status=status.HTTP_400_BAD_REQUEST)
            elif parts:
                parts = [{"designation": line.strip()} for line in parts.splitlines() if line.strip()]
            else:
                parts = []
        client_name = request.data.get("client_name", "")
        signature = request.FILES.get("signature")
        photos = request.FILES.getlist("photos")
        try:
            intervention = close_sav_dossier(
                ticket,
                diagnosis=diagnosis,
                action_taken=action_taken,
                parts=parts,
                client_name=client_name,
                signature=signature,
                photos=photos,
                actor=request.user
            )
            notify_ticket_status_change(ticket, previous_status, actor=request.user)
            return Response({"detail": "Dossier clos avec succes.", "report_url": intervention.report_pdf.url if intervention.report_pdf else None})
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticatedSavUser], url_path="confirm-resolution")
    def confirm_resolution(self, request, pk=None):
        ticket = self.get_object()
        if request.user.role == User.ROLE_CLIENT and ticket.client_id != request.user.id:
            raise PermissionDenied("Vous ne pouvez valider que vos propres tickets.")
        if ticket.status != Ticket.STATUS_RESOLVED:
            return Response({"detail": "Seuls les tickets resolus peuvent etre valides."}, status=status.HTTP_400_BAD_REQUEST)
        previous_status = ticket.status
        ticket.status = Ticket.STATUS_CLOSED
        ticket.closed_at = timezone.now()
        ticket.save(update_fields=["status", "closed_at", "updated_at"])
        Message.objects.create(
            ticket=ticket,
            sender=request.user,
            message_type=Message.TYPE_PUBLIC,
            channel=Message.CHANNEL_PORTAL,
            direction=Message.DIRECTION_INBOUND if request.user.role == User.ROLE_CLIENT else Message.DIRECTION_INTERNAL,
            content="Le client a valide la resolution du ticket. Le dossier est maintenant ferme.",
            sentiment_score=calculate_sentiment("Le client a valide la resolution du ticket."),
        )
        self.audit("ticket_resolution_confirmed", ticket, {"confirmed_by": request.user.id})
        notify_ticket_status_change(ticket, previous_status, actor=request.user)
        return Response(self.get_serializer(ticket).data)

    @action(detail=True, methods=["post"], permission_classes=[IsManagerUser])
    def credit_account(self, request, pk=None):
        from ..services import is_admin_user
        if not is_admin_user(request.user):
            raise PermissionDenied("Le credit compte est reserve a l'administrateur.")
        ticket = self.get_object()
        try:
            credit_payload = credit_account_for_ticket(
                ticket,
                amount=request.data.get("amount", "0"),
                actor=request.user,
                reason=request.data.get("reason", "Credit SAV"),
                note=request.data.get("note", ""),
                currency=request.data.get("currency", "XAF"),
                external_reference=request.data.get("external_reference", ""),
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        from ..serializers import AccountCreditSerializer
        serializer = AccountCreditSerializer(credit_payload["credit"], context=self.get_serializer_context())
        return Response(
            {
                "credit": serializer.data,
                "workflow_execution_id": credit_payload["workflow_execution"].id,
                "notification_ids": [item.id for item in credit_payload["notifications"]],
                "message_id": credit_payload["message"].id if credit_payload["message"] else None,
            },
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"], permission_classes=[IsInternalUser])
    def run_automation(self, request, pk=None):
        ticket = self.get_object()
        trigger_event = request.data.get("trigger_event", AutomationRule.TRIGGER_MANUAL)
        result = run_automation_rules_for_ticket(ticket, actor=request.user, trigger_event=trigger_event)
        return Response(result)


class TicketFeedbackViewSet(AuditedModelViewSet):
    serializer_class = TicketFeedbackSerializer
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ["submitted_at", "created_at", "rating"]

    def get_permissions(self):
        if self.request.method in {"POST", "PATCH", "PUT", "DELETE"}:
            return [ReadOnlyForAuditors()]
        return [IsAuthenticatedSavUser()]

    def get_queryset(self):
        queryset = TicketFeedback.objects.select_related("ticket", "client", "organization").all()
        queryset = scope_ticket_feedback_queryset(queryset, self.request.user)
        ticket_id = self.request.query_params.get("ticket")
        if ticket_id:
            queryset = queryset.filter(ticket_id=ticket_id)
        return queryset

    def perform_create(self, serializer):
        ticket = serializer.validated_data["ticket"]
        if ticket.client_id != self.request.user.id:
            raise PermissionDenied("Seul le client proprietaire peut noter ce ticket.")
        if ticket.status not in {Ticket.STATUS_RESOLVED, Ticket.STATUS_CLOSED}:
            raise PermissionDenied("Le feedback est disponible apres resolution ou fermeture du ticket.")
        if hasattr(ticket, "feedback"):
            raise PermissionDenied("Un feedback existe deja pour ce ticket.")
        instance = serializer.save(client=self.request.user, organization=ticket.organization, submitted_at=timezone.now())
        log_audit_event(self.request.user, "ticket_feedback_created", instance, {"ticket_reference": ticket.reference})

    def perform_update(self, serializer):
        instance = serializer.instance
        if instance.client_id != self.request.user.id:
            raise PermissionDenied("Vous ne pouvez modifier que votre propre feedback.")
        updated = serializer.save()
        log_audit_event(self.request.user, "ticket_feedback_updated", updated, {"ticket_reference": updated.ticket.reference})


class MessageViewSet(AuditedModelViewSet):
    serializer_class = MessageSerializer
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ["created_at"]

    def get_permissions(self):
        if self.request.method == "DELETE":
            return [IsInternalUser()]
        return [ReadOnlyForAuditors()]

    def get_queryset(self):
        queryset = Message.objects.select_related("ticket", "sender", "recipient").all()
        return scope_message_queryset(queryset, self.request.user)

    def _validate_recipient(self, ticket, recipient):
        if not recipient:
            return
        if recipient.pk in ticket_conversation_participant_ids(ticket):
            return
        raise PermissionDenied("Le destinataire doit participer a la conversation de ce ticket.")

    def perform_create(self, serializer):
        from ..services import create_notification
        ticket = serializer.validated_data["ticket"]
        if not can_participate_in_ticket_conversation(self.request.user, ticket):
            raise PermissionDenied("Vous ne participez pas a la conversation de ce ticket.")
        if (
            is_internal_user(self.request.user)
            and not self.request.user.is_superuser
            and self.request.user.organization_id
            and ticket.organization_id != self.request.user.organization_id
        ):
            raise PermissionDenied("Vous ne pouvez pas publier un message sur une autre organisation.")
        self._validate_recipient(ticket, serializer.validated_data.get("recipient"))
        if is_internal_user(self.request.user):
            direction = serializer.validated_data.get("direction") or Message.DIRECTION_OUTBOUND
            message_type = serializer.validated_data.get("message_type") or Message.TYPE_PUBLIC
        else:
            direction = Message.DIRECTION_INBOUND
            message_type = Message.TYPE_PUBLIC
        sentiment_score = calculate_sentiment(serializer.validated_data.get("content", ""))
        instance = serializer.save(
            sender=self.request.user,
            direction=direction,
            message_type=message_type,
            sentiment_score=sentiment_score,
        )
        if is_internal_user(self.request.user) and ticket.first_response_at is None:
            ticket.first_response_at = timezone.now()
            ticket.save(update_fields=["first_response_at", "updated_at"])
        self.audit("message_created", instance)
        if instance.recipient_id:
            create_notification(
                recipient=instance.recipient,
                subject=f"{ticket.reference} - Nouveau message",
                message=instance.content,
                event_type="ticket_message",
                ticket=ticket,
            )
        elif direction == Message.DIRECTION_OUTBOUND and message_type == Message.TYPE_PUBLIC and is_internal_user(self.request.user):
            create_message_delivery_notifications(instance)

    def perform_update(self, serializer):
        ticket = serializer.validated_data.get("ticket", serializer.instance.ticket)
        recipient = serializer.validated_data.get("recipient", serializer.instance.recipient)
        if not can_participate_in_ticket_conversation(self.request.user, ticket):
            raise PermissionDenied("Vous ne participez pas a la conversation de ce ticket.")
        if (
            is_internal_user(self.request.user)
            and not self.request.user.is_superuser
            and self.request.user.organization_id
            and ticket.organization_id != self.request.user.organization_id
        ):
            raise PermissionDenied("Vous ne pouvez pas deplacer ce message vers une autre organisation.")
        self._validate_recipient(ticket, recipient)
        instance = serializer.save()
        self.audit("message_updated", instance)


class TicketAttachmentViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = TicketAttachmentSerializer
    permission_classes = [ReadOnlyForAuditors]
    parser_classes = [parsers.MultiPartParser, parsers.FormParser]
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ["created_at", "updated_at", "kind"]

    def get_queryset(self):
        queryset = TicketAttachment.objects.select_related("ticket", "uploaded_by").all()
        queryset = scope_attachment_queryset(queryset, self.request.user)
        ticket_id = self.request.query_params.get("ticket")
        if ticket_id:
            queryset = queryset.filter(ticket_id=ticket_id)
        return queryset

    def perform_create(self, serializer):
        ticket = serializer.validated_data["ticket"]
        if self.request.user.role == User.ROLE_CLIENT and ticket.client_id != self.request.user.id:
            raise PermissionDenied("Vous ne pouvez pas joindre un fichier au ticket d'un autre client.")
        if (
            is_internal_user(self.request.user)
            and not self.request.user.is_superuser
            and self.request.user.organization_id
            and ticket.organization_id != self.request.user.organization_id
        ):
            raise PermissionDenied("Vous ne pouvez pas joindre un fichier a une autre organisation.")
        instance = serializer.save(uploaded_by=self.request.user, organization=ticket.organization)
        log_audit_event(
            actor=self.request.user,
            action="ticket_attachment_created",
            instance=instance,
            details={"ticket_reference": ticket.reference},
        )

    def destroy(self, request, *args, **kwargs):
        attachment = self.get_object()
        if (
            not request.user.is_superuser
            and not is_internal_user(request.user)
            and attachment.ticket.client_id != request.user.id
        ):
            raise PermissionDenied("Vous ne pouvez pas supprimer la piece jointe d'un autre ticket.")
        log_audit_event(
            actor=request.user,
            action="ticket_attachment_deleted",
            instance=attachment,
            details={"ticket_reference": attachment.ticket.reference},
        )
        return super().destroy(request, *args, **kwargs)


class TicketAssignmentViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = TicketAssignmentSerializer
    permission_classes = [IsAuthenticatedSavUser]
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ["assigned_at", "released_at", "created_at"]

    def get_queryset(self):
        from ..services import scope_ticket_assignment_queryset
        queryset = TicketAssignment.objects.select_related("ticket", "technician", "assigned_by").all()
        queryset = scope_ticket_assignment_queryset(queryset, self.request.user)
        ticket_id = self.request.query_params.get("ticket")
        technician_id = self.request.query_params.get("technician")
        if ticket_id:
            queryset = queryset.filter(ticket_id=ticket_id)
        if technician_id:
            queryset = queryset.filter(technician_id=technician_id)
        return queryset


class SupportSessionViewSet(AuditedModelViewSet):
    serializer_class = SupportSessionSerializer
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ["scheduled_for", "created_at"]

    def get_queryset(self):
        queryset = SupportSession.objects.select_related("ticket", "client", "agent").all()
        return scope_support_session_queryset(queryset, self.request.user)

    def perform_create(self, serializer):
        ticket = serializer.validated_data["ticket"]
        if self.request.user.role == User.ROLE_CLIENT and ticket.client_id != self.request.user.id:
            raise PermissionDenied("Vous ne pouvez pas ouvrir une session de support pour un autre client.")
        if (
            is_internal_user(self.request.user)
            and not self.request.user.is_superuser
            and self.request.user.organization_id
            and ticket.organization_id != self.request.user.organization_id
        ):
            raise PermissionDenied("Vous ne pouvez pas ouvrir une session pour une autre organisation.")
        if self.request.user.role == User.ROLE_CLIENT:
            instance = serializer.save(client=self.request.user)
        else:
            instance = serializer.save(client=serializer.validated_data.get("client") or ticket.client)
        self.audit("support_session_created", instance)

    def perform_update(self, serializer):
        ticket = serializer.validated_data.get("ticket", serializer.instance.ticket)
        if (
            is_internal_user(self.request.user)
            and not self.request.user.is_superuser
            and self.request.user.organization_id
            and ticket.organization_id != self.request.user.organization_id
        ):
            raise PermissionDenied("Vous ne pouvez pas deplacer cette session vers une autre organisation.")
        instance = serializer.save()
        self.audit("support_session_updated", instance)
