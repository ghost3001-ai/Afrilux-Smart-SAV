from django.core.cache import cache
from django.db import connections
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from ..models import Organization
from ..permissions import IsAuthenticatedSavUser
from ..serializers import ClientRegistrationSerializer, PublicOrganizationSerializer, UserSerializer
from rest_framework import status as http_status


class HealthCheckView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        database_ok = True
        cache_ok = True
        try:
            with connections["default"].cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
        except Exception:
            database_ok = False
        try:
            cache_key = "sav:healthcheck"
            cache.set(cache_key, "ok", timeout=5)
            cache_ok = cache.get(cache_key) == "ok"
        except Exception:
            cache_ok = False
        payload = {
            "status": "ok" if database_ok and cache_ok else "degraded",
            "database": "ok" if database_ok else "error",
            "cache": "ok" if cache_ok else "error",
            "timestamp": timezone.now().isoformat(),
        }
        status_code = http_status.HTTP_200_OK if database_ok and cache_ok else http_status.HTTP_503_SERVICE_UNAVAILABLE
        return Response(payload, status=status_code)


class PublicOrganizationListView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        queryset = Organization.objects.filter(is_active=True).order_by("name")
        serializer = PublicOrganizationSerializer(queryset, many=True)
        return Response(serializer.data)


class ClientRegistrationView(APIView):
    authentication_classes = []
    permission_classes = []

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
            status=http_status.HTTP_201_CREATED,
        )
