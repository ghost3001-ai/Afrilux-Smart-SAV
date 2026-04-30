from datetime import datetime, time, timedelta

from django.core.cache import cache
from django.db import connections
from django.http import HttpResponse
from django.db.models import Avg, Count, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import filters, mixins, parsers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .comms import (
    create_message_delivery_notifications,
    deliver_notification,
    dispatch_pending_notifications,
    handle_email_inbound,
    handle_twilio_inbound,
)
from .models import (
    AccountCredit,
    AIActionLog,
    AuditLog,
    AutomationRule,
    ClientContact,
    DeviceRegistration,
    EquipmentCategory,
    FinancialTransaction,
    GeneratedReport,
    Intervention,
    InterventionMedia,
    KnowledgeArticle,
    Message,
    Notification,
    Organization,
    OfferRecommendation,
    PredictiveAlert,
    Product,
    ProductTelemetry,
    SlaRule,
    SupportSession,
    TicketAttachment,
    TicketAssignment,
    TicketFeedback,
    Ticket,
    User,
    WorkflowExecution,
)
from .permissions import IsAuthenticatedSavUser, IsInternalUser, IsManagerUser, ReadOnlyForAuditors
from .reporting import (
    REPORT_DAILY,
    REPORT_MONTHLY,
    REPORT_WEEKLY,
    build_report,
    export_report_csv,
    export_report_pdf,
    export_report_xlsx,
)
from .serializers import (
    AccountCreditSerializer,
    AIActionLogSerializer,
    AuditLogSerializer,
    AutomationRuleSerializer,
    ClientContactSerializer,
    ClientRegistrationSerializer,
    DeviceRegistrationSerializer,
    EquipmentCategorySerializer,
    FinancialTransactionSerializer,
    GeneratedReportSerializer,
    InterventionSerializer,
    InterventionMediaSerializer,
    KnowledgeArticleSerializer,
    MessageSerializer,
    NotificationSerializer,
    OfferRecommendationSerializer,
    PredictiveAlertSerializer,
    ProductSerializer,
    ProductTelemetrySerializer,
    PublicOrganizationSerializer,
    SlaRuleSerializer,
    SupportSessionSerializer,
    TicketAttachmentSerializer,
    TicketAssignmentSerializer,
    TicketFeedbackSerializer,
    TicketSerializer,
    UserSerializer,
    WorkflowExecutionSerializer,
)
from .services import (
    OPEN_TICKET_STATUSES,
    answer_bi_question,
    apply_agentic_resolution,
    answer_support_question,
    build_customer_insight,
    can_create_ticket,
    calculate_sentiment,
    compute_agent_performance_rows,
    compute_average_first_response_hours,
    compute_average_resolution_hours,
    compute_technician_status_rows,
    compute_ticket_hotspots,
    compute_ticket_monthly_series,
    compute_ticket_sla_deadline,
    compute_ticket_volume_series,
    credit_account_for_ticket,
    dispatch_due_reports,
    ensure_assignment_intervention,
    escalate_ticket,
    generate_intervention_pdf,
    has_reporting_access,
    is_admin_user,
    is_internal_user,
    is_manager_user,
    is_support_user,
    log_audit_event,
    run_automation_rules_for_ticket,
    run_predictive_analysis,
    scope_equipment_category_queryset,
    scope_generated_report_queryset,
    scope_ai_action_queryset,
    scope_audit_log_queryset,
    scope_automation_rule_queryset,
    scope_by_client_relation,
    scope_knowledge_article_queryset,
    scope_intervention_queryset,
    scope_message_queryset,
    scope_notification_queryset,
    scope_offer_queryset,
    scope_predictive_alert_queryset,
    scope_product_queryset,
    scope_support_session_queryset,
    scope_sla_rule_queryset,
    scope_attachment_queryset,
    scope_client_contact_queryset,
    scope_financial_transaction_queryset,
    scope_intervention_media_queryset,
    scope_ticket_assignment_queryset,
    scope_ticket_feedback_queryset,
    scope_ticket_queryset,
    scope_user_queryset,
    scope_workflow_execution_queryset,
    notify_ticket_status_change,
    archive_generated_report,
)


def _ticket_status_from_intervention(intervention):
    if intervention.status == Intervention.STATUS_DONE or intervention.finished_at:
        return Ticket.STATUS_INTERVENTION_DONE
    if intervention.status == Intervention.STATUS_IN_PROGRESS or intervention.started_at:
        return Ticket.STATUS_IN_PROGRESS_N2
    if intervention.status == Intervention.STATUS_CANCELLED:
        return Ticket.STATUS_WAITING
    if intervention.scheduled_for:
        return Ticket.STATUS_INTERVENTION_PLANNED
    return Ticket.STATUS_ASSIGNED if intervention.ticket.assigned_agent_id else Ticket.STATUS_NEW


class AuditedModelViewSet(viewsets.ModelViewSet):
    permission_classes = [ReadOnlyForAuditors]

    def audit(self, action_name, instance, details=None):
        log_audit_event(
            actor=self.request.user,
            action=action_name,
            instance=instance,
            details=details or {"via": "api"},
        )


class UserViewSet(AuditedModelViewSet):
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticatedSavUser]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["username", "first_name", "last_name", "email", "company_name", "organization__name", "organization__brand_name"]
    ordering_fields = ["username", "role"]

    def get_permissions(self):
        if self.request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            return [IsManagerUser()]
        return [IsAuthenticatedSavUser()]

    def get_queryset(self):
        queryset = User.objects.all().order_by("first_name", "last_name", "username")
        return scope_user_queryset(queryset, self.request.user)

    @action(detail=False, methods=["get"])
    def me(self, request):
        serializer = self.get_serializer(request.user)
        return Response(serializer.data)

    @action(detail=True, methods=["get"])
    def insights(self, request, pk=None):
        user = self.get_object()
        if user.role != User.ROLE_CLIENT:
            return Response({"detail": "Insights disponibles uniquement pour les clients."}, status=status.HTTP_400_BAD_REQUEST)
        return Response(build_customer_insight(user))

    @action(detail=True, methods=["post"])
    def generate_offers(self, request, pk=None):
        user = self.get_object()
        if user.role != User.ROLE_CLIENT:
            return Response({"detail": "Generation d'offres reservee aux clients."}, status=status.HTTP_400_BAD_REQUEST)

        from .services import generate_offer_recommendations

        offers = generate_offer_recommendations(client=user, persist=True)
        serializer = OfferRecommendationSerializer([item["offer"] for item in offers], many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["post"], permission_classes=[IsManagerUser])
    def verify_account(self, request, pk=None):
        user = self.get_object()
        if user.role != User.ROLE_CLIENT:
            return Response({"detail": "Verification reservee aux comptes clients."}, status=status.HTTP_400_BAD_REQUEST)
        desired_state = str(request.data.get("is_verified", "true")).strip().lower() in {"true", "1", "yes", "oui"}
        user.is_verified = desired_state
        user.save(update_fields=["is_verified"])
        log_audit_event(request.user, "client_verification_updated", user, {"is_verified": desired_state})
        return Response(self.get_serializer(user).data)

    @action(detail=True, methods=["post"], permission_classes=[IsManagerUser])
    def set_active(self, request, pk=None):
        user = self.get_object()
        desired_state = str(request.data.get("is_active", "true")).strip().lower() in {"true", "1", "yes", "oui"}
        user.is_active = desired_state
        user.save(update_fields=["is_active"])
        log_audit_event(request.user, "user_active_state_updated", user, {"is_active": desired_state})
        return Response(self.get_serializer(user).data)

    def perform_create(self, serializer):
        organization = serializer.validated_data.get("organization") or getattr(self.request.user, "organization", None)
        if (
            organization
            and not self.request.user.is_superuser
            and self.request.user.organization_id
            and organization.id != self.request.user.organization_id
        ):
            raise PermissionDenied("Vous ne pouvez pas creer un utilisateur pour une autre organisation.")
        instance = serializer.save(organization=organization)
        self.audit("user_created", instance)

    def perform_update(self, serializer):
        organization = serializer.validated_data.get("organization", serializer.instance.organization)
        if (
            organization
            and not self.request.user.is_superuser
            and self.request.user.organization_id
            and organization.id != self.request.user.organization_id
        ):
            raise PermissionDenied("Vous ne pouvez pas deplacer un utilisateur vers une autre organisation.")
        instance = serializer.save()
        self.audit("user_updated", instance)


class ClientContactViewSet(AuditedModelViewSet):
    serializer_class = ClientContactSerializer
    permission_classes = [IsAuthenticatedSavUser]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["first_name", "last_name", "job_title", "phone", "email", "client__username", "client__company_name"]
    ordering_fields = ["first_name", "last_name", "created_at"]

    def get_queryset(self):
        queryset = ClientContact.objects.select_related("client", "organization").all()
        return scope_client_contact_queryset(queryset, self.request.user)

    def perform_create(self, serializer):
        client = serializer.validated_data["client"]
        if self.request.user.role == User.ROLE_CLIENT and client.id != self.request.user.id:
            raise PermissionDenied("Vous ne pouvez creer que vos propres contacts.")
        if (
            is_internal_user(self.request.user)
            and not self.request.user.is_superuser
            and self.request.user.organization_id
            and client.organization_id != self.request.user.organization_id
        ):
            raise PermissionDenied("Vous ne pouvez pas creer un contact pour une autre organisation.")
        instance = serializer.save(organization=client.organization)
        self.audit("client_contact_created", instance)

    def perform_update(self, serializer):
        instance = serializer.save()
        self.audit("client_contact_updated", instance)


class ClientViewSet(UserViewSet):
    search_fields = [
        "username",
        "first_name",
        "last_name",
        "email",
        "company_name",
        "sector",
        "tax_identifier",
    ]
    ordering_fields = ["username", "company_name", "date_joined"]

    def get_queryset(self):
        queryset = User.objects.filter(role=User.ROLE_CLIENT).order_by("first_name", "last_name", "username")
        return scope_user_queryset(queryset, self.request.user)

    def perform_create(self, serializer):
        organization = serializer.validated_data.get("organization") or getattr(self.request.user, "organization", None)
        if (
            organization
            and not self.request.user.is_superuser
            and self.request.user.organization_id
            and organization.id != self.request.user.organization_id
        ):
            raise PermissionDenied("Vous ne pouvez pas creer un client pour une autre organisation.")
        instance = serializer.save(role=User.ROLE_CLIENT, organization=organization)
        self.audit("client_created", instance)

    def perform_update(self, serializer):
        organization = serializer.validated_data.get("organization", serializer.instance.organization)
        if (
            organization
            and not self.request.user.is_superuser
            and self.request.user.organization_id
            and organization.id != self.request.user.organization_id
        ):
            raise PermissionDenied("Vous ne pouvez pas deplacer un client vers une autre organisation.")
        instance = serializer.save(role=User.ROLE_CLIENT)
        self.audit("client_updated", instance)


class EquipmentCategoryViewSet(AuditedModelViewSet):
    serializer_class = EquipmentCategorySerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["name", "code", "description"]
    ordering_fields = ["name", "code", "created_at"]

    def get_permissions(self):
        if self.request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            return [IsInternalUser()]
        return [IsAuthenticatedSavUser()]

    def get_queryset(self):
        queryset = EquipmentCategory.objects.all()
        return scope_equipment_category_queryset(queryset, self.request.user)

    def perform_create(self, serializer):
        organization = serializer.validated_data.get("organization") or getattr(self.request.user, "organization", None)
        if (
            organization
            and not self.request.user.is_superuser
            and self.request.user.organization_id
            and organization.id != self.request.user.organization_id
        ):
            raise PermissionDenied("Vous ne pouvez pas gerer une categorie pour une autre organisation.")
        instance = serializer.save(organization=organization)
        self.audit("equipment_category_created", instance)

    def perform_update(self, serializer):
        instance = serializer.save()
        self.audit("equipment_category_updated", instance)


class ProductViewSet(AuditedModelViewSet):
    serializer_class = ProductSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["name", "serial_number", "sku", "client__username", "client__company_name", "organization__name"]
    ordering_fields = ["name", "warranty_end", "health_score", "created_at"]

    def get_permissions(self):
        if self.action == "predictive_analysis":
            return [IsInternalUser()]
        if self.request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            return [IsInternalUser()]
        return [IsAuthenticatedSavUser()]

    def get_queryset(self):
        queryset = Product.objects.select_related("client", "equipment_category").all()
        queryset = scope_product_queryset(queryset, self.request.user)
        equipment_category = self.request.query_params.get("equipment_category")
        if equipment_category:
            queryset = queryset.filter(equipment_category_id=equipment_category)
        return queryset

    def perform_create(self, serializer):
        client = serializer.validated_data.get("client")
        if (
            client
            and is_internal_user(self.request.user)
            and not self.request.user.is_superuser
            and self.request.user.organization_id
            and client.organization_id != self.request.user.organization_id
        ):
            raise PermissionDenied("Vous ne pouvez pas rattacher un produit a une autre organisation.")
        instance = serializer.save()
        self.audit("product_created", instance)

    def perform_update(self, serializer):
        client = serializer.validated_data.get("client", serializer.instance.client)
        if (
            client
            and is_internal_user(self.request.user)
            and not self.request.user.is_superuser
            and self.request.user.organization_id
            and client.organization_id != self.request.user.organization_id
        ):
            raise PermissionDenied("Vous ne pouvez pas rattacher un produit a une autre organisation.")
        instance = serializer.save()
        self.audit("product_updated", instance)

    @action(detail=True, methods=["post"], permission_classes=[IsInternalUser])
    def predictive_analysis(self, request, pk=None):
        product = self.get_object()
        result = run_predictive_analysis(product, approved_by=request.user)
        return Response(result)


class EquipmentViewSet(ProductViewSet):
    pass


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
            serializer.validated_data["status"] = Ticket.STATUS_NEW
            serializer.validated_data["assigned_agent"] = None
            client = self.request.user
        else:
            client = serializer.validated_data.get("client")
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
        if instance.assigned_agent_id:
            ensure_assignment_intervention(instance, actor=self.request.user, note="Affectation initiale a la creation du ticket.")

        self.audit("ticket_created", instance)
        run_automation_rules_for_ticket(instance, actor=self.request.user, trigger_event=AutomationRule.TRIGGER_TICKET_CREATED)

    def perform_update(self, serializer):
        if not (is_support_user(self.request.user) or is_admin_user(self.request.user)):
            raise PermissionDenied("Seul le support peut modifier directement un ticket.")
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
            serializer.instance.status
            in {
                Ticket.STATUS_NEW,
                Ticket.STATUS_QUALIFICATION,
                Ticket.STATUS_PENDING_CUSTOMER,
                Ticket.STATUS_WAITING,
            }
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
        ticket = self.get_object()
        result = apply_agentic_resolution(ticket, approved_by=request.user)
        return Response(result)

    @action(detail=True, methods=["post"], permission_classes=[IsInternalUser])
    def take_ownership(self, request, pk=None):
        ticket = self.get_object()
        if not request.user.is_ticket_assignment_eligible:
            return Response(
                {"detail": "Prise en charge autorisee uniquement pour les agents et techniciens disponibles."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        previous_status = ticket.status
        ticket.assigned_agent = request.user
        if ticket.status in {Ticket.STATUS_NEW, Ticket.STATUS_WAITING, Ticket.STATUS_PENDING_CUSTOMER, Ticket.STATUS_QUALIFICATION}:
            ticket.status = Ticket.STATUS_ASSIGNED
        ticket.save(update_fields=["assigned_agent", "status", "updated_at"])
        ensure_assignment_intervention(ticket, actor=request.user, note="Prise en charge manuelle du ticket.")
        self.audit("ticket_taken_ownership", ticket, {"assigned_agent": request.user.id})
        notify_ticket_status_change(ticket, previous_status, actor=request.user)
        return Response(self.get_serializer(ticket).data)

    @action(detail=True, methods=["post"], permission_classes=[IsManagerUser], url_path="assign")
    def assign(self, request, pk=None):
        ticket = self.get_object()
        previous_status = ticket.status
        technician_id = request.data.get("technician") or request.data.get("assigned_agent")
        if not technician_id:
            return Response({"detail": "Le technicien est obligatoire."}, status=status.HTTP_400_BAD_REQUEST)
        assignment_queryset = User.objects.filter(is_active=True).filter(
            Q(role__in=User.STANDARD_SUPPORT_ROLES + User.SPECIAL_SUPPORT_ROLES)
            | Q(role=User.ROLE_TECHNICIAN, technician_status="available")
        )
        technician = get_object_or_404(
            scope_user_queryset(assignment_queryset, request.user),
            pk=technician_id,
        )
        ticket.assigned_agent = technician
        if ticket.status in {Ticket.STATUS_NEW, Ticket.STATUS_WAITING, Ticket.STATUS_PENDING_CUSTOMER, Ticket.STATUS_QUALIFICATION}:
            ticket.status = Ticket.STATUS_ASSIGNED
        ticket.save(update_fields=["assigned_agent", "status", "updated_at"])
        ensure_assignment_intervention(ticket, actor=request.user, note="Affectation explicite du responsable SAV.")
        self.audit("ticket_assigned", ticket, {"assigned_agent": technician.id})
        notify_ticket_status_change(ticket, previous_status, actor=request.user)
        return Response(self.get_serializer(ticket).data)

    @action(detail=True, methods=["post"], permission_classes=[IsInternalUser])
    def escalate(self, request, pk=None):
        ticket = self.get_object()
        previous_status = ticket.status
        try:
            result = escalate_ticket(
                ticket,
                actor=request.user,
                note=str(request.data.get("note", "")).strip(),
                target=str(request.data.get("target", "")).strip(),
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        if ticket.status != previous_status:
            notify_ticket_status_change(ticket, previous_status, actor=request.user)

        payload = self.get_serializer(ticket).data
        payload["escalation"] = result
        return Response(payload)

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

    @action(detail=True, methods=["post"], permission_classes=[IsInternalUser], url_path="close")
    def close(self, request, pk=None):
        ticket = self.get_object()
        previous_status = ticket.status
        if ticket.status == Ticket.STATUS_CANCELLED:
            return Response({"detail": "Un ticket annule ne peut pas etre cloture."}, status=status.HTTP_400_BAD_REQUEST)
        ticket.status = Ticket.STATUS_CLOSED
        if request.data.get("resolution_summary"):
            ticket.resolution_summary = str(request.data.get("resolution_summary", "")).strip()
        ticket.save(update_fields=["status", "resolution_summary", "closed_at", "updated_at"])
        self.audit("ticket_closed", ticket, {"closed_by": request.user.id})
        notify_ticket_status_change(ticket, previous_status, actor=request.user)
        return Response(self.get_serializer(ticket).data)

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


class FinancialTransactionViewSet(AuditedModelViewSet):
    serializer_class = FinancialTransactionSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["external_reference", "provider_reference", "description", "client__username", "client__company_name"]
    ordering_fields = ["occurred_at", "created_at", "amount", "status"]

    def get_permissions(self):
        if self.request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            return [IsInternalUser()]
        return [IsAuthenticatedSavUser()]

    def get_queryset(self):
        queryset = FinancialTransaction.objects.select_related("client", "organization").all()
        queryset = scope_financial_transaction_queryset(queryset, self.request.user)
        status_value = self.request.query_params.get("status")
        transaction_type = self.request.query_params.get("transaction_type")
        client_id = self.request.query_params.get("client")
        if status_value:
            queryset = queryset.filter(status=status_value)
        if transaction_type:
            queryset = queryset.filter(transaction_type=transaction_type)
        if client_id:
            queryset = queryset.filter(client_id=client_id)
        return queryset

    def perform_create(self, serializer):
        client = serializer.validated_data["client"]
        if (
            not self.request.user.is_superuser
            and self.request.user.organization_id
            and client.organization_id != self.request.user.organization_id
        ):
            raise PermissionDenied("Vous ne pouvez pas creer une transaction pour une autre organisation.")
        instance = serializer.save(organization=client.organization)
        self.audit("financial_transaction_created", instance)

    def perform_update(self, serializer):
        client = serializer.validated_data.get("client", serializer.instance.client)
        if (
            not self.request.user.is_superuser
            and self.request.user.organization_id
            and client.organization_id != self.request.user.organization_id
        ):
            raise PermissionDenied("Vous ne pouvez pas deplacer une transaction vers une autre organisation.")
        instance = serializer.save(organization=client.organization)
        self.audit("financial_transaction_updated", instance)


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
        if recipient.pk == ticket.client_id:
            return
        if recipient.role in set(User.SUPPORT_ROLE_ALIASES) and (
            not ticket.organization_id or recipient.organization_id == ticket.organization_id
        ):
            return
        raise PermissionDenied("Le destinataire doit etre le client ou un membre support autorise sur ce ticket.")

    def perform_create(self, serializer):
        ticket = serializer.validated_data["ticket"]
        if not (
            self.request.user.role == User.ROLE_CLIENT
            or is_support_user(self.request.user)
            or is_admin_user(self.request.user)
        ):
            raise PermissionDenied("Seuls le client et le support peuvent participer a la conversation.")
        if self.request.user.role == User.ROLE_CLIENT and ticket.client_id != self.request.user.id:
            raise PermissionDenied("Vous ne pouvez pas publier un message sur le ticket d'un autre client.")
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
            from .services import create_notification

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


class InterventionViewSet(AuditedModelViewSet):
    serializer_class = InterventionSerializer
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ["scheduled_for", "created_at"]

    def get_permissions(self):
        if self.request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            return [IsInternalUser()]
        return [IsAuthenticatedSavUser()]

    def get_queryset(self):
        queryset = Intervention.objects.select_related("ticket", "agent").all()
        return scope_intervention_queryset(queryset, self.request.user)

    def perform_create(self, serializer):
        ticket = serializer.validated_data["ticket"]
        if self.request.user.role == User.ROLE_TECHNICIAN and ticket.assigned_agent_id != self.request.user.id:
            raise PermissionDenied("Vous ne pouvez intervenir que sur les tickets qui vous sont affectes.")
        if (
            not self.request.user.is_superuser
            and self.request.user.organization_id
            and ticket.organization_id != self.request.user.organization_id
        ):
            raise PermissionDenied("Vous ne pouvez pas creer une intervention pour une autre organisation.")
        extra = {"organization": ticket.organization}
        if self.request.user.role == User.ROLE_TECHNICIAN:
            extra["agent"] = self.request.user
            extra["intervention_type"] = Intervention.TYPE_ON_SITE
        instance = serializer.save(**extra)
        if instance.status == Intervention.STATUS_DONE:
            generate_intervention_pdf(instance)
        previous_status = ticket.status
        next_status = _ticket_status_from_intervention(instance)
        if next_status != previous_status:
            ticket.status = next_status
            ticket.save(update_fields=["status", "updated_at"])
            notify_ticket_status_change(ticket, previous_status, actor=self.request.user)
        self.audit("intervention_created", instance)

    def perform_update(self, serializer):
        ticket = serializer.validated_data.get("ticket", serializer.instance.ticket)
        if (
            not self.request.user.is_superuser
            and self.request.user.organization_id
            and ticket.organization_id != self.request.user.organization_id
        ):
            raise PermissionDenied("Vous ne pouvez pas deplacer cette intervention vers une autre organisation.")
        instance = serializer.save(organization=ticket.organization)
        if instance.status == Intervention.STATUS_DONE:
            generate_intervention_pdf(instance)
        self.audit("intervention_updated", instance)

    @action(detail=True, methods=["get"], url_path="report-pdf")
    def report_pdf(self, request, pk=None):
        intervention = self.get_object()
        content = generate_intervention_pdf(intervention)
        response = HttpResponse(content, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="intervention-{intervention.ticket.reference}-{intervention.pk}.pdf"'
        return response


class InterventionMediaViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = InterventionMediaSerializer
    permission_classes = [ReadOnlyForAuditors]
    parser_classes = [parsers.MultiPartParser, parsers.FormParser]
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ["created_at", "kind"]

    def get_queryset(self):
        queryset = InterventionMedia.objects.select_related("intervention", "uploaded_by").all()
        queryset = scope_intervention_media_queryset(queryset, self.request.user)
        intervention_id = self.request.query_params.get("intervention")
        if intervention_id:
            queryset = queryset.filter(intervention_id=intervention_id)
        return queryset

    def perform_create(self, serializer):
        intervention = serializer.validated_data["intervention"]
        if (
            is_internal_user(self.request.user)
            and not self.request.user.is_superuser
            and self.request.user.organization_id
            and intervention.organization_id != self.request.user.organization_id
        ):
            raise PermissionDenied("Vous ne pouvez pas ajouter un media sur une autre organisation.")
        if not is_internal_user(self.request.user) and intervention.ticket.client_id != self.request.user.id:
            raise PermissionDenied("Vous ne pouvez pas ajouter un media sur le dossier d'un autre client.")
        instance = serializer.save(uploaded_by=self.request.user, organization=intervention.organization)
        log_audit_event(
            self.request.user,
            "intervention_media_created",
            instance,
            {"ticket_reference": intervention.ticket.reference},
        )


class TicketAssignmentViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = TicketAssignmentSerializer
    permission_classes = [IsAuthenticatedSavUser]
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ["assigned_at", "released_at", "created_at"]

    def get_queryset(self):
        queryset = TicketAssignment.objects.select_related("ticket", "technician", "assigned_by").all()
        queryset = scope_ticket_assignment_queryset(queryset, self.request.user)
        ticket_id = self.request.query_params.get("ticket")
        technician_id = self.request.query_params.get("technician")
        if ticket_id:
            queryset = queryset.filter(ticket_id=ticket_id)
        if technician_id:
            queryset = queryset.filter(technician_id=technician_id)
        return queryset


class SlaRuleViewSet(AuditedModelViewSet):
    serializer_class = SlaRuleSerializer
    permission_classes = [IsAuthenticatedSavUser]
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ["priority", "response_deadline_minutes", "resolution_deadline_hours", "created_at"]

    def get_permissions(self):
        if self.request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            return [IsManagerUser()]
        return [IsAuthenticatedSavUser()]

    def get_queryset(self):
        queryset = SlaRule.objects.all()
        return scope_sla_rule_queryset(queryset, self.request.user)

    def perform_create(self, serializer):
        organization = serializer.validated_data.get("organization") or getattr(self.request.user, "organization", None)
        if (
            organization
            and not self.request.user.is_superuser
            and self.request.user.organization_id
            and organization.id != self.request.user.organization_id
        ):
            raise PermissionDenied("Vous ne pouvez pas definir un SLA pour une autre organisation.")
        instance = serializer.save(organization=organization)
        self.audit("sla_rule_created", instance)

    def perform_update(self, serializer):
        instance = serializer.save()
        self.audit("sla_rule_updated", instance)


class GeneratedReportViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = GeneratedReportSerializer
    permission_classes = [IsAuthenticatedSavUser]
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ["created_at", "report_type", "period_label"]

    def get_queryset(self):
        queryset = GeneratedReport.objects.select_related("organization", "generated_by").all()
        queryset = scope_generated_report_queryset(queryset, self.request.user)
        report_type = self.request.query_params.get("report_type")
        if report_type:
            queryset = queryset.filter(report_type=report_type)
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


class ProductTelemetryViewSet(AuditedModelViewSet):
    serializer_class = ProductTelemetrySerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["metric_name", "product__name", "product__serial_number"]
    ordering_fields = ["captured_at", "value"]

    def get_permissions(self):
        if self.request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            return [IsInternalUser()]
        return [IsAuthenticatedSavUser()]

    def get_queryset(self):
        queryset = ProductTelemetry.objects.select_related("product").all()
        return scope_by_client_relation(queryset, self.request.user, "product__client")

    def perform_create(self, serializer):
        product = serializer.validated_data["product"]
        if (
            not self.request.user.is_superuser
            and self.request.user.organization_id
            and product.organization_id != self.request.user.organization_id
        ):
            raise PermissionDenied("Vous ne pouvez pas ajouter de telemetry sur une autre organisation.")
        instance = serializer.save()
        self.audit("telemetry_created", instance)

    def perform_update(self, serializer):
        product = serializer.validated_data.get("product", serializer.instance.product)
        if (
            not self.request.user.is_superuser
            and self.request.user.organization_id
            and product.organization_id != self.request.user.organization_id
        ):
            raise PermissionDenied("Vous ne pouvez pas modifier de telemetry sur une autre organisation.")
        instance = serializer.save()
        self.audit("telemetry_updated", instance)


class PredictiveAlertViewSet(AuditedModelViewSet):
    serializer_class = PredictiveAlertSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["title", "description", "product__name", "product__serial_number"]
    ordering_fields = ["created_at", "severity", "predicted_failure_at"]

    def get_permissions(self):
        if self.request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            return [IsInternalUser()]
        return [IsAuthenticatedSavUser()]

    def get_queryset(self):
        queryset = PredictiveAlert.objects.select_related("product", "ticket").all()
        return scope_predictive_alert_queryset(queryset, self.request.user)

    def perform_create(self, serializer):
        product = serializer.validated_data["product"]
        if (
            not self.request.user.is_superuser
            and self.request.user.organization_id
            and product.organization_id != self.request.user.organization_id
        ):
            raise PermissionDenied("Vous ne pouvez pas creer une alerte sur une autre organisation.")
        instance = serializer.save()
        self.audit("predictive_alert_created", instance)

    def perform_update(self, serializer):
        product = serializer.validated_data.get("product", serializer.instance.product)
        if (
            not self.request.user.is_superuser
            and self.request.user.organization_id
            and product.organization_id != self.request.user.organization_id
        ):
            raise PermissionDenied("Vous ne pouvez pas modifier une alerte d'une autre organisation.")
        instance = serializer.save()
        if instance.status == PredictiveAlert.STATUS_RESOLVED and instance.resolved_at is None:
            instance.resolved_at = timezone.now()
            instance.save(update_fields=["resolved_at", "updated_at"])
        self.audit("predictive_alert_updated", instance)


class KnowledgeArticleViewSet(AuditedModelViewSet):
    serializer_class = KnowledgeArticleSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["title", "summary", "content", "keywords", "category"]
    ordering_fields = ["title", "created_at", "updated_at"]

    def get_permissions(self):
        if self.request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            return [IsInternalUser()]
        return [IsAuthenticatedSavUser()]

    def get_queryset(self):
        queryset = KnowledgeArticle.objects.select_related("product").all()
        return scope_knowledge_article_queryset(queryset, self.request.user)

    def perform_create(self, serializer):
        extra = {}
        if is_internal_user(self.request.user) and not self.request.user.is_superuser and self.request.user.organization_id:
            extra["organization"] = self.request.user.organization
        instance = serializer.save(**extra)
        self.audit("knowledge_article_created", instance)

    def perform_update(self, serializer):
        instance = serializer.save()
        self.audit("knowledge_article_updated", instance)

    @action(detail=True, methods=["post"])
    def vote(self, request, pk=None):
        article = self.get_object()
        helpful = bool(request.data.get("helpful", True))
        if helpful:
            article.helpful_votes += 1
        else:
            article.unhelpful_votes += 1
        article.save(update_fields=["helpful_votes", "unhelpful_votes", "updated_at"])
        return Response({"helpful_votes": article.helpful_votes, "unhelpful_votes": article.unhelpful_votes})


class NotificationViewSet(AuditedModelViewSet):
    serializer_class = NotificationSerializer
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ["created_at", "sent_at", "read_at"]

    def get_permissions(self):
        if self.action == "mark_read":
            return [ReadOnlyForAuditors()]
        if self.action == "dispatch_pending":
            return [IsInternalUser()]
        if self.request.method == "POST":
            return [IsInternalUser()]
        if self.request.method in {"PUT", "PATCH"}:
            return [ReadOnlyForAuditors()]
        if self.request.method == "DELETE":
            return [IsInternalUser()]
        return [IsAuthenticatedSavUser()]

    def get_queryset(self):
        queryset = Notification.objects.select_related("recipient", "ticket").all()
        return scope_notification_queryset(queryset, self.request.user)

    def perform_create(self, serializer):
        recipient = serializer.validated_data.get("recipient")
        ticket = serializer.validated_data.get("ticket")
        if (
            recipient
            and is_internal_user(self.request.user)
            and not self.request.user.is_superuser
            and self.request.user.organization_id
            and recipient.organization_id != self.request.user.organization_id
        ):
            raise PermissionDenied("Vous ne pouvez pas notifier une autre organisation.")
        if (
            ticket
            and is_internal_user(self.request.user)
            and not self.request.user.is_superuser
            and self.request.user.organization_id
            and ticket.organization_id != self.request.user.organization_id
        ):
            raise PermissionDenied("Vous ne pouvez pas utiliser un ticket d'une autre organisation.")
        instance = serializer.save()
        deliver_notification(instance)
        self.audit("notification_created", instance)

    def perform_update(self, serializer):
        recipient = serializer.validated_data.get("recipient", serializer.instance.recipient)
        ticket = serializer.validated_data.get("ticket", serializer.instance.ticket)
        if (
            is_internal_user(self.request.user)
            and not self.request.user.is_superuser
            and self.request.user.organization_id
            and recipient.organization_id != self.request.user.organization_id
        ):
            raise PermissionDenied("Vous ne pouvez pas reaffecter cette notification a une autre organisation.")
        if (
            ticket
            and is_internal_user(self.request.user)
            and not self.request.user.is_superuser
            and self.request.user.organization_id
            and ticket.organization_id != self.request.user.organization_id
        ):
            raise PermissionDenied("Vous ne pouvez pas rattacher cette notification a un ticket d'une autre organisation.")
        instance = serializer.save()
        if not is_internal_user(self.request.user):
            instance.status = Notification.STATUS_READ
            instance.read_at = timezone.now()
            instance.save(update_fields=["status", "read_at"])
        self.audit("notification_updated", instance)

    @action(detail=True, methods=["post"])
    def mark_read(self, request, pk=None):
        notification = self.get_object()
        notification.status = Notification.STATUS_READ
        notification.read_at = timezone.now()
        notification.save(update_fields=["status", "read_at"])
        self.audit("notification_read", notification)
        return Response({"status": notification.status, "read_at": notification.read_at})

    @action(detail=False, methods=["post"])
    def dispatch_pending(self, request):
        channel = request.data.get("channel")
        organization = None if request.user.is_superuser or not request.user.organization_id else request.user.organization
        results = dispatch_pending_notifications(channel=channel, organization=organization)
        return Response({"count": len(results), "results": results})


class DeviceRegistrationViewSet(viewsets.GenericViewSet):
    serializer_class = DeviceRegistrationSerializer
    permission_classes = [ReadOnlyForAuditors]

    def get_queryset(self):
        return DeviceRegistration.objects.filter(user=self.request.user)

    def list(self, request):
        serializer = self.get_serializer(self.get_queryset().order_by("-last_seen_at"), many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["post"])
    def register(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        registration, created = DeviceRegistration.objects.update_or_create(
            token=serializer.validated_data["token"],
            defaults={
                "user": request.user,
                "platform": serializer.validated_data["platform"],
                "device_id": serializer.validated_data.get("device_id", ""),
                "app_version": serializer.validated_data.get("app_version", ""),
                "is_active": True,
                "last_seen_at": timezone.now(),
            },
        )
        status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
        return Response(self.get_serializer(registration).data, status=status_code)

    @action(detail=False, methods=["post"])
    def unregister(self, request):
        token = str(request.data.get("token", "")).strip()
        device_id = str(request.data.get("device_id", "")).strip()
        queryset = self.get_queryset()

        if token:
            queryset = queryset.filter(token=token)
        elif device_id:
            queryset = queryset.filter(device_id=device_id)
        else:
            return Response({"detail": "Le jeton ou l'identifiant de l'appareil est obligatoire."}, status=status.HTTP_400_BAD_REQUEST)

        updated = queryset.update(is_active=False, last_seen_at=timezone.now())
        return Response({"updated": updated})


class OfferRecommendationViewSet(AuditedModelViewSet):
    serializer_class = OfferRecommendationSerializer
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ["created_at", "valid_until", "price"]

    def get_permissions(self):
        if self.action in {"accept", "reject"}:
            return [ReadOnlyForAuditors()]
        if self.request.method == "POST":
            return [IsInternalUser()]
        if self.request.method == "DELETE":
            return [IsInternalUser()]
        return [IsAuthenticatedSavUser()]

    def get_queryset(self):
        queryset = OfferRecommendation.objects.select_related("client", "product", "ticket").all()
        return scope_offer_queryset(queryset, self.request.user)

    def perform_create(self, serializer):
        client = serializer.validated_data.get("client")
        if (
            client
            and is_internal_user(self.request.user)
            and not self.request.user.is_superuser
            and self.request.user.organization_id
            and client.organization_id != self.request.user.organization_id
        ):
            raise PermissionDenied("Vous ne pouvez pas creer une offre pour une autre organisation.")
        instance = serializer.save()
        self.audit("offer_created", instance)

    def perform_update(self, serializer):
        client = serializer.validated_data.get("client", serializer.instance.client)
        if (
            client
            and is_internal_user(self.request.user)
            and not self.request.user.is_superuser
            and self.request.user.organization_id
            and client.organization_id != self.request.user.organization_id
        ):
            raise PermissionDenied("Vous ne pouvez pas deplacer cette offre vers une autre organisation.")
        instance = serializer.save()
        self.audit("offer_updated", instance)

    @action(detail=True, methods=["post"])
    def accept(self, request, pk=None):
        offer = self.get_object()
        offer.status = OfferRecommendation.STATUS_ACCEPTED
        offer.save(update_fields=["status"])
        self.audit("offer_accepted", offer)
        return Response({"status": offer.status})

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        offer = self.get_object()
        offer.status = OfferRecommendation.STATUS_REJECTED
        offer.save(update_fields=["status"])
        self.audit("offer_rejected", offer)
        return Response({"status": offer.status})


class AutomationRuleViewSet(AuditedModelViewSet):
    serializer_class = AutomationRuleSerializer
    permission_classes = [IsManagerUser]
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ["priority", "created_at", "updated_at"]

    def get_queryset(self):
        return scope_automation_rule_queryset(AutomationRule.objects.all(), self.request.user)

    def perform_create(self, serializer):
        extra = {}
        if not self.request.user.is_superuser and self.request.user.organization_id:
            extra["organization"] = self.request.user.organization
        instance = serializer.save(**extra)
        self.audit("automation_rule_created", instance)

    def perform_update(self, serializer):
        instance = serializer.save()
        self.audit("automation_rule_updated", instance)


class WorkflowExecutionViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = WorkflowExecutionSerializer
    permission_classes = [IsInternalUser]
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ["created_at"]

    def get_queryset(self):
        queryset = WorkflowExecution.objects.select_related("rule", "ticket").all()
        return scope_workflow_execution_queryset(queryset, self.request.user)


class AIActionLogViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = AIActionLogSerializer
    permission_classes = [IsAuthenticatedSavUser]
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ["created_at", "confidence"]

    def get_queryset(self):
        queryset = AIActionLog.objects.select_related("ticket", "product", "approved_by").all()
        return scope_ai_action_queryset(queryset, self.request.user)


class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = AuditLogSerializer
    permission_classes = [IsManagerUser]
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ["created_at"]

    def get_queryset(self):
        queryset = AuditLog.objects.select_related("actor").all()
        return scope_audit_log_queryset(queryset, self.request.user)


class HealthCheckView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        database_ok = True
        cache_ok = True

        try:
            with connections["default"].cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
        except Exception:  # noqa: BLE001
            database_ok = False

        try:
            cache_key = "sav:healthcheck"
            cache.set(cache_key, "ok", timeout=5)
            cache_ok = cache.get(cache_key) == "ok"
        except Exception:  # noqa: BLE001
            cache_ok = False

        payload = {
            "status": "ok" if database_ok and cache_ok else "degraded",
            "database": "ok" if database_ok else "error",
            "cache": "ok" if cache_ok else "error",
            "timestamp": timezone.now().isoformat(),
        }
        status_code = status.HTTP_200_OK if database_ok and cache_ok else status.HTTP_503_SERVICE_UNAVAILABLE
        return Response(payload, status=status_code)


class PublicOrganizationListView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        queryset = Organization.objects.filter(is_active=True).order_by("name")
        serializer = PublicOrganizationSerializer(queryset, many=True)
        return Response(serializer.data)


class ClientRegistrationView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = ClientRegistrationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        response_serializer = UserSerializer(user)
        return Response(
            {
                "account_created": serializer.context.get("account_created", True),
                "message": "Compte client cree. Vous pouvez maintenant vous connecter avec votre email.",
                "user": response_serializer.data,
            },
            status=status.HTTP_201_CREATED,
        )


class DashboardView(APIView):
    permission_classes = [IsAuthenticatedSavUser]

    def get(self, request):
        tickets = scope_ticket_queryset(Ticket.objects.all(), request.user)
        products = scope_product_queryset(Product.objects.all(), request.user)
        alerts = scope_predictive_alert_queryset(PredictiveAlert.objects.all(), request.user)
        notifications = scope_notification_queryset(Notification.objects.all(), request.user)
        offers = scope_offer_queryset(OfferRecommendation.objects.all(), request.user)
        ai_actions = scope_ai_action_queryset(AIActionLog.objects.all(), request.user)
        messages = scope_message_queryset(Message.objects.filter(sentiment_score__isnull=False), request.user)
        support_sessions = scope_support_session_queryset(SupportSession.objects.all(), request.user)
        feedbacks = scope_ticket_feedback_queryset(TicketFeedback.objects.all(), request.user)
        users = scope_user_queryset(User.objects.filter(role=User.ROLE_CLIENT), request.user)
        technicians = scope_user_queryset(
            User.objects.filter(role__in=User.TECHNICIAN_SPACE_ROLES, is_active=True),
            request.user,
        )

        status_breakdown = list(tickets.values("status").annotate(total=Count("id")).order_by("status"))
        priority_breakdown = list(tickets.values("priority").annotate(total=Count("id")).order_by("priority"))
        top_categories = list(tickets.values("category").annotate(total=Count("id")).order_by("-total")[:5])
        average_sentiment = messages.aggregate(avg=Avg("sentiment_score"))["avg"]
        average_first_response_hours = compute_average_first_response_hours(tickets)
        average_resolution_hours = compute_average_resolution_hours(tickets)
        top_agents = compute_agent_performance_rows(tickets)
        knowledge_articles = scope_knowledge_article_queryset(KnowledgeArticle.objects.all(), request.user)

        data = {
            "organization_name": request.user.organization.display_name if getattr(request.user, "organization_id", None) else "",
            "organization_slug": request.user.organization.slug if getattr(request.user, "organization_id", None) else "",
            "organization_primary_color": request.user.organization.primary_color if getattr(request.user, "organization_id", None) else "",
            "organization_accent_color": request.user.organization.accent_color if getattr(request.user, "organization_id", None) else "",
            "tickets_total": tickets.count(),
            "tickets_open": tickets.filter(status__in=OPEN_TICKET_STATUSES).count(),
            "tickets_overdue": tickets.filter(status__in=OPEN_TICKET_STATUSES, sla_deadline__lt=timezone.now()).count(),
            "tickets_unassigned": tickets.filter(status__in=OPEN_TICKET_STATUSES, assigned_agent__isnull=True).count(),
            "maintenance_total": tickets.filter(category=Ticket.CATEGORY_MAINTENANCE).count(),
            "bug_total": tickets.filter(category=Ticket.CATEGORY_BUG).count(),
            "tickets_critical_open": tickets.filter(
                status__in=OPEN_TICKET_STATUSES,
                priority=Ticket.PRIORITY_CRITICAL,
            ).count(),
            "products_total": products.count(),
            "products_under_warranty": products.filter(warranty_end__gte=timezone.localdate()).count(),
            "predictive_alerts_open": alerts.filter(
                status__in=[PredictiveAlert.STATUS_OPEN, PredictiveAlert.STATUS_IN_PROGRESS]
            ).count(),
            "predictive_alerts_critical": alerts.filter(
                status__in=[PredictiveAlert.STATUS_OPEN, PredictiveAlert.STATUS_IN_PROGRESS],
                severity=PredictiveAlert.SEVERITY_CRITICAL,
            ).count(),
            "ai_actions_executed": ai_actions.filter(status=AIActionLog.STATUS_EXECUTED).count(),
            "notifications_unread": notifications.exclude(status=Notification.STATUS_READ).count(),
            "offers_accepted": offers.filter(status=OfferRecommendation.STATUS_ACCEPTED).count(),
            "support_sessions_active": support_sessions.filter(
                status__in=[SupportSession.STATUS_SCHEDULED, SupportSession.STATUS_LIVE]
            ).count(),
            "clients_verified": users.filter(is_verified=True).count(),
            "feedback_average_rating": float(feedbacks.aggregate(avg=Avg("rating"))["avg"])
            if feedbacks.exists()
            else None,
            "average_sentiment": average_sentiment,
            "average_first_response_hours": float(average_first_response_hours)
            if average_first_response_hours is not None
            else None,
            "average_resolution_hours": float(average_resolution_hours) if average_resolution_hours is not None else None,
            "top_agents": [
                {
                    **row,
                    "average_resolution_hours": float(row["average_resolution_hours"])
                    if row["average_resolution_hours"] is not None
                    else None,
                }
                for row in top_agents
            ],
            "tickets_by_status": status_breakdown,
            "tickets_by_priority": priority_breakdown,
            "top_categories": top_categories,
            "knowledge_articles_published": knowledge_articles.filter(status=KnowledgeArticle.STATUS_PUBLISHED).count(),
            "sla_due_soon": tickets.filter(
                status__in=OPEN_TICKET_STATUSES,
                sla_deadline__gte=timezone.now(),
                sla_deadline__lte=timezone.now() + timedelta(hours=2),
            ).count(),
            "geo_hotspots": compute_ticket_hotspots(tickets),
            "trend_7_days": compute_ticket_volume_series(tickets, days=7),
            "trend_30_days": compute_ticket_volume_series(tickets, days=30),
            "trend_12_months": compute_ticket_monthly_series(tickets, months=12),
            "technician_status_breakdown": compute_technician_status_rows(technicians),
        }
        return Response(data)


def _parse_anchor_date(raw_value):
    if not raw_value:
        return None
    try:
        return datetime.fromisoformat(str(raw_value)).date()
    except ValueError:
        return None


class BaseReportView(APIView):
    permission_classes = [IsAuthenticatedSavUser]
    report_type = None

    def get(self, request):
        if not has_reporting_access(request.user):
            raise PermissionDenied("Le reporting est reserve aux profils de supervision, pilotage et lecture seule habilites.")
        anchor_date = _parse_anchor_date(request.query_params.get("date"))
        return Response(build_report(self.report_type, request.user, anchor_date=anchor_date))


class DailyReportView(BaseReportView):
    report_type = REPORT_DAILY


class WeeklyReportView(BaseReportView):
    report_type = REPORT_WEEKLY


class MonthlyReportView(BaseReportView):
    report_type = REPORT_MONTHLY


class ReportExportView(APIView):
    permission_classes = [IsAuthenticatedSavUser]

    def get(self, request, report_type):
        if not has_reporting_access(request.user):
            raise PermissionDenied("L'export de rapports est reserve aux profils de supervision, pilotage et lecture seule habilites.")

        anchor_date = _parse_anchor_date(request.query_params.get("date"))
        export_format = str(request.query_params.get("format", "xlsx")).strip().lower()
        report = build_report(report_type, request.user, anchor_date=anchor_date)
        safe_period = str(report.get("period_label", "")).replace("/", "-").replace(" ", "_")
        filename = f"{report_type}-{safe_period}"

        if export_format == "csv":
            content = export_report_csv(report)
            archive_generated_report(
                organization=getattr(request.user, "organization", None),
                report=report,
                report_type=report_type,
                export_format=GeneratedReport.FORMAT_CSV,
                generated_by=request.user,
                filename=f"{filename}.csv",
                content=content,
            )
            response = HttpResponse(content, content_type="text/csv; charset=utf-8")
            response["Content-Disposition"] = f'attachment; filename="{filename}.csv"'
            return response
        if export_format == "pdf":
            content = export_report_pdf(report)
            archive_generated_report(
                organization=getattr(request.user, "organization", None),
                report=report,
                report_type=report_type,
                export_format=GeneratedReport.FORMAT_PDF,
                generated_by=request.user,
                filename=f"{filename}.pdf",
                content=content,
            )
            response = HttpResponse(content, content_type="application/pdf")
            response["Content-Disposition"] = f'attachment; filename="{filename}.pdf"'
            return response

        content = export_report_xlsx(report)
        archive_generated_report(
            organization=getattr(request.user, "organization", None),
            report=report,
            report_type=report_type,
            export_format=GeneratedReport.FORMAT_XLSX,
            generated_by=request.user,
            filename=f"{filename}.xlsx",
            content=content,
        )
        response = HttpResponse(
            content,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response["Content-Disposition"] = f'attachment; filename="{filename}.xlsx"'
        return response


class TechnicianPlanningView(APIView):
    permission_classes = [IsAuthenticatedSavUser]

    def get(self, request, pk):
        if not is_manager_user(request.user):
            raise PermissionDenied("Le planning technicien est reserve aux profils de supervision.")

        technician = get_object_or_404(
            scope_user_queryset(
                User.objects.filter(role__in=User.ASSIGNABLE_ROLES, is_active=True),
                request.user,
            ),
            pk=pk,
        )
        date_from = _parse_anchor_date(request.query_params.get("date_from")) or timezone.localdate()
        date_to = _parse_anchor_date(request.query_params.get("date_to")) or (date_from + timedelta(days=7))
        start_dt = timezone.make_aware(datetime.combine(date_from, time.min))
        end_dt = timezone.make_aware(datetime.combine(date_to, time.min))

        tickets = scope_ticket_queryset(
            Ticket.objects.select_related("client", "product", "assigned_agent"),
            request.user,
        ).filter(assigned_agent=technician, status__in=OPEN_TICKET_STATUSES)
        interventions = scope_intervention_queryset(
            Intervention.objects.select_related("ticket", "ticket__client", "agent"),
            request.user,
        ).filter(agent=technician, scheduled_for__gte=start_dt, scheduled_for__lt=end_dt)
        sessions = scope_support_session_queryset(
            SupportSession.objects.select_related("ticket", "client", "agent"),
            request.user,
        ).filter(agent=technician, scheduled_for__gte=start_dt, scheduled_for__lt=end_dt)

        return Response(
            {
                "technician_id": technician.id,
                "technician_name": str(technician),
                "technician_status": technician.technician_status,
                "specialties": technician.specialties,
                "primary_city": technician.primary_city,
                "primary_region": technician.primary_region,
                "weekly_availability": technician.weekly_availability,
                "date_from": date_from.isoformat(),
                "date_to": date_to.isoformat(),
                "tickets_assignes": [
                    {
                        "id": ticket.id,
                        "reference": ticket.reference,
                        "title": ticket.title,
                        "client": str(ticket.client),
                        "status": ticket.status,
                        "priority": ticket.priority,
                        "sla_deadline": ticket.sla_deadline.isoformat() if ticket.sla_deadline else None,
                    }
                    for ticket in tickets[:100]
                ],
                "interventions": [
                    {
                        "id": intervention.id,
                        "ticket_reference": intervention.ticket.reference,
                        "client": str(intervention.ticket.client),
                        "status": intervention.status,
                        "scheduled_for": intervention.scheduled_for.isoformat() if intervention.scheduled_for else None,
                        "action_taken": intervention.action_taken,
                    }
                    for intervention in interventions
                ],
                "sessions_support": [
                    {
                        "id": session.id,
                        "ticket_reference": session.ticket.reference,
                        "client": str(session.client),
                        "status": session.status,
                        "scheduled_for": session.scheduled_for.isoformat() if session.scheduled_for else None,
                        "session_type": session.session_type,
                    }
                    for session in sessions
                ],
            }
        )


class AnalyticsAskView(APIView):
    permission_classes = [IsAuthenticatedSavUser]

    def post(self, request):
        if not has_reporting_access(request.user):
            raise PermissionDenied("Les analytics sont reserves aux profils de supervision, pilotage et lecture seule habilites.")
        question = request.data.get("question", "").strip()
        if not question:
            return Response({"detail": "Le champ 'question' est obligatoire."}, status=status.HTTP_400_BAD_REQUEST)
        return Response(answer_bi_question(question, request.user))


class SupportAssistantView(APIView):
    permission_classes = [IsAuthenticatedSavUser]

    def post(self, request):
        question = str(request.data.get("question", "")).strip()
        if not question:
            return Response({"detail": "Le champ 'question' est obligatoire."}, status=status.HTTP_400_BAD_REQUEST)

        ticket = None
        ticket_id = request.data.get("ticket")
        if ticket_id:
            ticket = get_object_or_404(scope_ticket_queryset(Ticket.objects.all(), request.user), pk=ticket_id)

        product = None
        product_id = request.data.get("product")
        if product_id:
            product = get_object_or_404(scope_product_queryset(Product.objects.all(), request.user), pk=product_id)
        elif ticket and ticket.product_id:
            product = ticket.product

        return Response(answer_support_question(question, request.user, product=product, ticket=ticket))


class TwilioInboundWebhookView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        payload = {key: value for key, value in request.data.items()}
        result = handle_twilio_inbound(payload)
        return Response(result)


class EmailInboundWebhookView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    parser_classes = [parsers.JSONParser, parsers.MultiPartParser, parsers.FormParser]

    def post(self, request):
        payload = {key: value for key, value in request.data.items()}
        files = []
        for key in request.FILES:
            files.extend(request.FILES.getlist(key))
        result = handle_email_inbound(payload, uploaded_files=files)
        return Response(result)
