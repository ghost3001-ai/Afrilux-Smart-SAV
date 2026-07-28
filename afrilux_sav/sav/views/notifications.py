from rest_framework import filters, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from ..models import DeviceRegistration, Notification
from ..permissions import IsAuthenticatedSavUser, IsInternalUser, ReadOnlyForAuditors
from ..serializers import DeviceRegistrationSerializer, NotificationSerializer
from ..comms import deliver_notification as _deliver, dispatch_pending_notifications
from ..services import is_internal_user, scope_notification_queryset
from .base import AuditedModelViewSet
from django.utils import timezone


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
        _deliver(instance)
        self.audit("notification_created", instance)

    def perform_update(self, serializer):
        raise PermissionDenied("Les notifications ne peuvent etre modifiees que via l'action mark_read.")

    @action(detail=True, methods=["post"])
    def mark_read(self, request, pk=None):
        notification = self.get_object()
        notification.status = Notification.STATUS_READ
        notification.read_at = timezone.now()
        notification.save(update_fields=["status", "read_at"])
        self.audit("notification_read", notification)
        return Response({"status": notification.status, "read_at": notification.read_at})

    @action(detail=True, methods=["post"], url_path="mark-clicked")
    def mark_clicked(self, request, pk=None):
        notification = self.get_object()
        notification.status = Notification.STATUS_CLICKED
        notification.clicked_at = timezone.now()
        update_fields = ["status", "clicked_at"]
        if not notification.read_at:
            notification.read_at = notification.clicked_at
            update_fields.append("read_at")
        notification.save(update_fields=update_fields)
        self.audit("notification_clicked", notification)
        return Response({"status": notification.status, "clicked_at": notification.clicked_at})

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
        from rest_framework import status as http_status
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
        status_code = http_status.HTTP_201_CREATED if created else http_status.HTTP_200_OK
        return Response(self.get_serializer(registration).data, status=status_code)

    @action(detail=False, methods=["post"])
    def unregister(self, request):
        from rest_framework import status as http_status
        token = str(request.data.get("token", "")).strip()
        device_id = str(request.data.get("device_id", "")).strip()
        queryset = self.get_queryset()
        if token:
            queryset = queryset.filter(token=token)
        elif device_id:
            queryset = queryset.filter(device_id=device_id)
        else:
            return Response({"detail": "Le jeton ou l'identifiant de l'appareil est obligatoire."}, status=http_status.HTTP_400_BAD_REQUEST)
        updated = queryset.update(is_active=False, last_seen_at=timezone.now())
        return Response({"updated": updated})
