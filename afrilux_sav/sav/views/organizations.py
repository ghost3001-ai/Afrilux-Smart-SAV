from rest_framework import filters
from rest_framework.exceptions import PermissionDenied

from ..models import Agency, ClientSite, User
from ..permissions import IsAuthenticatedSavUser, IsInternalUser, IsManagerUser
from ..serializers import AgencySerializer, ClientSiteSerializer
from ..services import is_manager_user, scope_agency_queryset, scope_client_site_queryset
from .base import AuditedModelViewSet


class AgencyViewSet(AuditedModelViewSet):
    serializer_class = AgencySerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["name", "code", "city", "region", "organization__name"]
    ordering_fields = ["name", "city", "created_at"]

    def get_permissions(self):
        if self.request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            return [IsManagerUser()]
        return [IsAuthenticatedSavUser()]

    def get_queryset(self):
        return scope_agency_queryset(Agency.objects.select_related("organization").all(), self.request.user)

    def perform_create(self, serializer):
        organization = serializer.validated_data.get("organization") or getattr(self.request.user, "organization", None)
        if (
            organization
            and not self.request.user.is_superuser
            and self.request.user.organization_id
            and organization.id != self.request.user.organization_id
        ):
            raise PermissionDenied("Vous ne pouvez pas creer une agence pour une autre organisation.")
        instance = serializer.save(organization=organization)
        self.audit("agency_created", instance)

    def perform_update(self, serializer):
        instance = serializer.save()
        self.audit("agency_updated", instance)


class ClientSiteViewSet(AuditedModelViewSet):
    serializer_class = ClientSiteSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["name", "code", "address", "city", "client__username", "client__company_name"]
    ordering_fields = ["name", "city", "created_at"]

    def get_permissions(self):
        if self.request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            return [IsInternalUser()]
        return [IsAuthenticatedSavUser()]

    def get_queryset(self):
        queryset = ClientSite.objects.select_related("organization", "client", "agency").all()
        return scope_client_site_queryset(queryset, self.request.user)

    def perform_create(self, serializer):
        client = serializer.validated_data.get("client")
        if (
            client
            and not self.request.user.is_superuser
            and self.request.user.organization_id
            and client.organization_id != self.request.user.organization_id
        ):
            raise PermissionDenied("Vous ne pouvez pas creer un site pour une autre organisation.")
        instance = serializer.save()
        self.audit("client_site_created", instance)

    def perform_update(self, serializer):
        instance = serializer.save()
        self.audit("client_site_updated", instance)
