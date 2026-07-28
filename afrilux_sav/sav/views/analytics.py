from rest_framework import filters, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from ..models import AIActionLog, AuditLog, KnowledgeArticle, PredictiveAlert, ProductTelemetry
from ..permissions import IsAuthenticatedSavUser, IsInternalUser, IsManagerUser
from ..serializers import (
    AIActionLogSerializer,
    AuditLogSerializer,
    KnowledgeArticleSerializer,
    PredictiveAlertSerializer,
    ProductTelemetrySerializer,
)
from ..services import (
    get_ai_runtime_status,
    is_internal_user,
    scope_ai_action_queryset,
    scope_audit_log_queryset,
    scope_by_client_relation,
    scope_knowledge_article_queryset,
    scope_predictive_alert_queryset,
    scope_product_queryset,
)
from .base import AuditedModelViewSet
from django.utils import timezone
from rest_framework.views import APIView


class AIStatusView(APIView):
    permission_classes = [IsAuthenticatedSavUser]

    def get(self, request):
        return Response(get_ai_runtime_status())


class AnalyticsAskView(APIView):
    permission_classes = [IsAuthenticatedSavUser]

    def post(self, request):
        from ..services import answer_bi_question, has_reporting_access
        if not has_reporting_access(request.user):
            raise PermissionDenied("Les analytics sont reserves aux profils de supervision, pilotage et lecture seule habilites.")
        question = request.data.get("question", "").strip()
        if not question:
            return Response({"detail": "Le champ 'question' est obligatoire."}, status=400)
        return Response(answer_bi_question(question, request.user))


class SupportAssistantView(APIView):
    permission_classes = [IsAuthenticatedSavUser]

    def post(self, request):
        from ..services import answer_support_question, scope_ticket_queryset, scope_product_queryset
        from ..models import Ticket, Product
        from django.shortcuts import get_object_or_404
        question = str(request.data.get("question", "")).strip()
        if not question:
            return Response({"detail": "Le champ 'question' est obligatoire."}, status=400)
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
        queryset = KnowledgeArticle.objects.select_related("product", "equipment_category").all()
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
