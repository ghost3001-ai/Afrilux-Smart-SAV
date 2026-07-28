from rest_framework import filters, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from ..models import FinancialTransaction, GeneratedReport, OfferRecommendation, SlaRule
from ..permissions import IsAuthenticatedSavUser, IsInternalUser, IsManagerUser, ReadOnlyForAuditors
from ..serializers import (
    FinancialTransactionSerializer,
    GeneratedReportSerializer,
    OfferRecommendationSerializer,
    SlaRuleSerializer,
)
from ..services import (
    is_internal_user,
    scope_financial_transaction_queryset,
    scope_generated_report_queryset,
    scope_offer_queryset,
    scope_sla_rule_queryset,
)
from .base import AuditedModelViewSet


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
