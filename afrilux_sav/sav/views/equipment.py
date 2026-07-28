from rest_framework import filters, mixins, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from django.shortcuts import get_object_or_404

from ..models import EquipmentCategory, EquipmentLocationHistory, Product, SparePart, ClientSite, User
from ..permissions import IsAuthenticatedSavUser, IsInternalUser
from ..serializers import (
    EquipmentCategorySerializer,
    EquipmentLocationHistorySerializer,
    ProductSerializer,
    SparePartSerializer,
)
from ..services import (
    is_internal_user,
    run_predictive_analysis,
    scope_client_site_queryset,
    scope_equipment_category_queryset,
    scope_equipment_location_history_queryset,
    scope_product_queryset,
    scope_spare_part_queryset,
    scope_user_queryset,
    transfer_product_location,
)
from .base import AuditedModelViewSet


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


class SparePartViewSet(AuditedModelViewSet):
    serializer_class = SparePartSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["name", "reference", "category", "description"]
    ordering_fields = ["name", "reference", "category", "created_at"]

    def get_permissions(self):
        if self.request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            return [IsInternalUser()]
        return [IsAuthenticatedSavUser()]

    def get_queryset(self):
        queryset = SparePart.objects.select_related("organization", "equipment_category").all()
        return scope_spare_part_queryset(queryset, self.request.user)

    def perform_create(self, serializer):
        organization = serializer.validated_data.get("organization") or getattr(self.request.user, "organization", None)
        if (
            organization
            and not self.request.user.is_superuser
            and self.request.user.organization_id
            and organization.id != self.request.user.organization_id
        ):
            raise PermissionDenied("Vous ne pouvez pas creer une piece pour une autre organisation.")
        instance = serializer.save(organization=organization)
        self.audit("spare_part_created", instance)

    def perform_update(self, serializer):
        instance = serializer.save()
        self.audit("spare_part_updated", instance)


class ProductViewSet(AuditedModelViewSet):
    serializer_class = ProductSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["name", "serial_number", "sku", "client__username", "client__company_name", "organization__name"]
    ordering_fields = ["name", "warranty_end", "health_score", "created_at"]

    def get_permissions(self):
        if self.action in {"predictive_analysis", "transfer_location"}:
            return [IsInternalUser()]
        if self.request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            return [IsInternalUser()]
        return [IsAuthenticatedSavUser()]

    def get_queryset(self):
        queryset = Product.objects.select_related("client", "equipment_category", "site").all()
        queryset = scope_product_queryset(queryset, self.request.user)
        equipment_category = self.request.query_params.get("equipment_category")
        if equipment_category:
            queryset = queryset.filter(equipment_category_id=equipment_category)
        site = self.request.query_params.get("site")
        if site:
            queryset = queryset.filter(site_id=site)
        location_status = self.request.query_params.get("location_status")
        if location_status:
            queryset = queryset.filter(location_status=location_status)
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

    @action(detail=True, methods=["post"], permission_classes=[IsInternalUser], url_path="transfer-location")
    def transfer_location(self, request, pk=None):
        product = self.get_object()
        to_site = None
        to_client = product.client
        if request.data.get("to_site"):
            to_site = get_object_or_404(scope_client_site_queryset(ClientSite.objects.all(), request.user), pk=request.data["to_site"])
            to_client = to_site.client
        elif request.data.get("to_client"):
            to_client = get_object_or_404(scope_user_queryset(User.objects.filter(role=User.ROLE_CLIENT), request.user), pk=request.data["to_client"])
        history = transfer_product_location(
            product=product,
            to_client=to_client,
            to_site=to_site,
            to_location=request.data.get("to_location", ""),
            to_location_status=request.data.get("to_location_status", Product.LOCATION_INSTALLED),
            moved_by=request.user,
            reason=request.data.get("reason", ""),
        )
        serializer = EquipmentLocationHistorySerializer(history, context=self.get_serializer_context())
        return Response(serializer.data, status=200)


class EquipmentLocationHistoryViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = EquipmentLocationHistorySerializer
    permission_classes = [IsAuthenticatedSavUser]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["product__serial_number", "to_location", "reason"]
    ordering_fields = ["moved_at", "created_at"]

    def get_queryset(self):
        queryset = EquipmentLocationHistory.objects.select_related(
            "organization",
            "product",
            "from_client",
            "from_site",
            "to_client",
            "to_site",
            "moved_by",
        ).all()
        return scope_equipment_location_history_queryset(queryset, self.request.user)


class EquipmentViewSet(ProductViewSet):
    pass
