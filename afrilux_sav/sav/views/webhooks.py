import base64
import hashlib
import hmac
from urllib.parse import urlparse

from django.conf import settings
from django.core.cache import cache
from rest_framework import parsers
from rest_framework.exceptions import Throttled
from rest_framework.response import Response
from rest_framework.views import APIView

from ..comms import handle_email_inbound, handle_twilio_inbound


def _webhook_client_ip(request):
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded_for:
        return forwarded_for.split(",", 1)[0].strip()
    return request.META.get("REMOTE_ADDR", "")


def _enforce_webhook_rate_limit(request, namespace):
    limit = int(getattr(settings, "SAV_WEBHOOK_RATE_LIMIT_PER_MINUTE", 60))
    if limit <= 0:
        return
    cache_key = f"sav:webhook:{namespace}:{_webhook_client_ip(request) or 'unknown'}"
    count = cache.get(cache_key, 0) + 1
    cache.set(cache_key, count, 60)
    if count > limit:
        raise Throttled(detail="Trop de requetes webhook.")


def _require_webhook_signatures():
    return bool(getattr(settings, "SAV_REQUIRE_WEBHOOK_SIGNATURES", True))


def _validate_twilio_signature(request):
    if not _require_webhook_signatures():
        return True
    auth_token = getattr(settings, "TWILIO_AUTH_TOKEN", "").strip()
    received_signature = request.META.get("HTTP_X_TWILIO_SIGNATURE", "").strip()
    if not auth_token or not received_signature:
        return False
    url = request.build_absolute_uri()
    public_base_url = getattr(settings, "SAV_PUBLIC_BASE_URL", "").strip()
    if public_base_url:
        parsed_request = urlparse(url)
        url = public_base_url.rstrip("/") + parsed_request.path
        if parsed_request.query:
            url = f"{url}?{parsed_request.query}"
    payload = "".join(f"{key}{value}" for key, value in sorted(request.data.items()))
    expected = base64.b64encode(hmac.new(auth_token.encode(), f"{url}{payload}".encode(), hashlib.sha1).digest()).decode()
    return hmac.compare_digest(expected, received_signature)


def _validate_email_webhook_signature(request):
    if not _require_webhook_signatures():
        return True
    secret = getattr(settings, "INBOUND_EMAIL_WEBHOOK_SECRET", "").strip()
    token = getattr(settings, "INBOUND_EMAIL_WEBHOOK_TOKEN", "").strip()
    received_token = request.META.get("HTTP_X_SAV_WEBHOOK_TOKEN", "").strip()
    if token and hmac.compare_digest(token, received_token):
        return True
    received_signature = request.META.get("HTTP_X_SAV_WEBHOOK_SIGNATURE", "").strip()
    if not secret or not received_signature:
        return False
    expected_digest = hmac.new(secret.encode(), request.body, hashlib.sha256).hexdigest()
    expected_signature = f"sha256={expected_digest}"
    return hmac.compare_digest(expected_digest, received_signature) or hmac.compare_digest(expected_signature, received_signature)


class TwilioInboundWebhookView(APIView):
    authentication_classes = []
    permission_classes = []

    def post(self, request):
        _enforce_webhook_rate_limit(request, "twilio")
        if not _validate_twilio_signature(request):
            return Response({"detail": "Signature Twilio invalide."}, status=403)
        payload = {key: value for key, value in request.data.items()}
        result = handle_twilio_inbound(payload)
        return Response(result)


class EmailInboundWebhookView(APIView):
    authentication_classes = []
    permission_classes = []
    parser_classes = [parsers.JSONParser, parsers.MultiPartParser, parsers.FormParser]

    def post(self, request):
        _enforce_webhook_rate_limit(request, "email")
        if not _validate_email_webhook_signature(request):
            return Response({"detail": "Signature email invalide."}, status=403)
        payload = {key: value for key, value in request.data.items()}
        files = []
        for key in request.FILES:
            files.extend(request.FILES.getlist(key))
        result = handle_email_inbound(payload, uploaded_files=files)
        return Response(result)
