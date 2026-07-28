from rest_framework import filters
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from ..models import User, ClientContact
from ..permissions import IsAuthenticatedSavUser, IsInternalUser, IsManagerUser
from ..serializers import ClientContactSerializer, UserSerializer, OfferRecommendationSerializer
from ..services import (
    build_customer_insight,
    is_internal_user,
    is_manager_user,
    log_audit_event,
    scope_user_queryset,
    scope_client_contact_queryset,
    compute_technician_availability_dashboard,
)
from .base import AuditedModelViewSet


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

    @action(detail=False, methods=["get"], url_path="availability-dashboard")
    def availability_dashboard(self, request):
        if not is_manager_user(request.user):
            raise PermissionDenied("Acces reserve aux responsables SAV.")
        organization = getattr(request.user, "organization", None)
        if not organization and not request.user.is_superuser:
            return Response([])
        data = compute_technician_availability_dashboard(organization)
        return Response(data)

    @action(detail=False, methods=["get"])
    def me(self, request):
        serializer = self.get_serializer(request.user)
        return Response(serializer.data)

    @action(detail=True, methods=["get"])
    def insights(self, request, pk=None):
        user = self.get_object()
        if user.role != User.ROLE_CLIENT:
            return Response({"detail": "Insights disponibles uniquement pour les clients."}, status=400)
        return Response(build_customer_insight(user))

    @action(detail=True, methods=["post"])
    def generate_offers(self, request, pk=None):
        from ..services import generate_offer_recommendations
        user = self.get_object()
        if user.role != User.ROLE_CLIENT:
            return Response({"detail": "Generation d'offres reservee aux clients."}, status=400)
        offers = generate_offer_recommendations(client=user, persist=True)
        serializer = OfferRecommendationSerializer([item["offer"] for item in offers], many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["post"], permission_classes=[IsManagerUser])
    def verify_account(self, request, pk=None):
        user = self.get_object()
        if user.role != User.ROLE_CLIENT:
            return Response({"detail": "Verification reservee aux comptes clients."}, status=400)
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
        "username", "first_name", "last_name", "email",
        "company_name", "sector", "tax_identifier",
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
