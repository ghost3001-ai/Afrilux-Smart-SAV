from datetime import datetime, time

from django.utils import timezone
from rest_framework import viewsets

from ..services import log_audit_event
from ..permissions import ReadOnlyForAuditors


class AuditedModelViewSet(viewsets.ModelViewSet):
    permission_classes = [ReadOnlyForAuditors]

    def audit(self, action_name, instance, details=None):
        log_audit_event(
            actor=self.request.user,
            action=action_name,
            instance=instance,
            details=details or {"via": "api"},
        )


def _request_bool(data, key, default=False):
    value = data.get(key, default)
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on", "oui"}


def _parse_anchor_date(raw_value):
    if not raw_value:
        return None
    try:
        return datetime.fromisoformat(str(raw_value)).date()
    except ValueError:
        return None


def _start_of_day(value):
    return timezone.make_aware(datetime.combine(value, time.min), timezone.get_current_timezone())
