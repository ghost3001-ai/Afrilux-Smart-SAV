from django.db import transaction

from ..models import AuditLog
from ..request_context import get_current_request


def _extract_request_audit_metadata():
    request = get_current_request()
    if request is None:
        return {
            "source_ip": None,
            "user_agent": "",
            "request_path": "",
            "http_method": "",
        }

    forwarded_for = str(request.META.get("HTTP_X_FORWARDED_FOR", "")).strip()
    source_ip = forwarded_for.split(",")[0].strip() if forwarded_for else str(request.META.get("REMOTE_ADDR", "")).strip()
    return {
        "source_ip": source_ip or None,
        "user_agent": str(request.META.get("HTTP_USER_AGENT", ""))[:255],
        "request_path": str(getattr(request, "path", "") or "")[:255],
        "http_method": str(getattr(request, "method", "") or "")[:10],
    }


def log_audit_event(
    actor=None,
    action="",
    instance=None,
    details=None,
    actor_type=None,
    target_model=None,
    target_id=None,
    target_reference=None,
    source_ip=None,
    user_agent="",
    request_path="",
    http_method="",
):
    if actor_type is None:
        actor_type = AuditLog.ACTOR_HUMAN if actor else AuditLog.ACTOR_SYSTEM

    resolved_target_model = ""
    resolved_target_id = None
    resolved_target_reference = ""

    if instance is not None:
        resolved_target_model = instance._meta.label_lower
        resolved_target_id = instance.pk
        if hasattr(instance, "reference") and getattr(instance, "reference"):
            resolved_target_reference = str(instance.reference)
        else:
            resolved_target_reference = str(instance)[:255]

    if target_model is not None:
        resolved_target_model = target_model
    if target_id is not None:
        resolved_target_id = target_id
    if target_reference is not None:
        resolved_target_reference = str(target_reference)[:255]

    request_meta = _extract_request_audit_metadata()
    resolved_source_ip = source_ip or request_meta["source_ip"]
    resolved_user_agent = user_agent or request_meta["user_agent"]
    resolved_request_path = request_path or request_meta["request_path"]
    resolved_http_method = http_method or request_meta["http_method"]

    from .tickets import organization_for_instance

    return AuditLog.objects.create(
        organization=organization_for_instance(instance) or getattr(actor, "organization", None),
        actor=actor,
        actor_type=actor_type,
        action=action,
        target_model=resolved_target_model,
        target_id=resolved_target_id,
        target_reference=resolved_target_reference,
        source_ip=resolved_source_ip,
        user_agent=resolved_user_agent,
        request_path=resolved_request_path,
        http_method=resolved_http_method,
        details=details or {},
    )
