import json
import re
from datetime import datetime, timedelta
from decimal import Decimal
from io import BytesIO

from django.core.files.base import ContentFile
from django.core.mail import EmailMessage
from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone
from django.utils.text import slugify
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from reportlab.lib import colors

from .ai import OpenAIResponsesClient
from .comms import create_external_channel_notifications, deliver_notification
from .models import (
    AccountCredit,
    AIActionLog,
    AuditLog,
    AutomationRule,
    ClientContact,
    EquipmentCategory,
    FinancialTransaction,
    GeneratedReport,
    Intervention,
    InterventionMedia,
    KnowledgeArticle,
    Message,
    Notification,
    Organization,
    OfferRecommendation,
    PredictiveAlert,
    Product,
    SlaRule,
    SupportSession,
    TicketFeedback,
    Ticket,
    TicketAssignment,
    User,
    WorkflowExecution,
)
from .request_context import get_current_request


LLM_CLIENT = OpenAIResponsesClient()


OPEN_TICKET_STATUSES = [
    Ticket.STATUS_NEW,
    Ticket.STATUS_ASSIGNED,
    Ticket.STATUS_IN_PROGRESS,
    Ticket.STATUS_WAITING,
]

ESCALATION_PRIORITY_SEQUENCE = [
    Ticket.PRIORITY_LOW,
    Ticket.PRIORITY_NORMAL,
    Ticket.PRIORITY_HIGH,
    Ticket.PRIORITY_CRITICAL,
]

ESCALATION_TARGET_CFAO_MANAGER = "cfao_manager"
ESCALATION_TARGET_CFAO_WORKS = "cfao_works"
ESCALATION_TARGET_HVAC_MANAGER = "hvac_manager"
ESCALATION_TARGET_CHIEF_TECHNICIAN = "chief_technician"
ESCALATION_ALLOWED_TARGETS = {
    ESCALATION_TARGET_CFAO_MANAGER,
    ESCALATION_TARGET_CFAO_WORKS,
    ESCALATION_TARGET_HVAC_MANAGER,
    ESCALATION_TARGET_CHIEF_TECHNICIAN,
}
ESCALATION_TARGET_ROLE_MAP = {
    ESCALATION_TARGET_CFAO_MANAGER: [User.ROLE_CFAO_MANAGER],
    ESCALATION_TARGET_CFAO_WORKS: [User.ROLE_CFAO_WORKS],
    ESCALATION_TARGET_HVAC_MANAGER: [User.ROLE_HVAC_MANAGER],
    ESCALATION_TARGET_CHIEF_TECHNICIAN: [User.ROLE_CHIEF_TECHNICIAN],
}

TICKET_CREATOR_ROLES = {
    User.ROLE_CLIENT,
    User.ROLE_HEAD_SAV,
}

NEGATIVE_WORDS = [
    "decu",
    "frustre",
    "encore",
    "toujours",
    "erreur",
    "probleme",
    "bloque",
    "plainte",
    "retard",
    "defectueux",
]

POSITIVE_WORDS = [
    "merci",
    "parfait",
    "resolu",
    "ok",
    "super",
    "satisfait",
]

CRITICAL_WORDS = [
    "danger",
    "fumee",
    "incendie",
    "court-circuit",
    "electrocution",
]

HIGH_PRIORITY_WORDS = [
    "urgent",
    "bloque",
    "hors service",
    "panne totale",
    "impossible",
]

RESPONSE_SLA_MINUTES = {
    Ticket.PRIORITY_CRITICAL: 30,
    Ticket.PRIORITY_HIGH: 60,
    Ticket.PRIORITY_NORMAL: 120,
    Ticket.PRIORITY_LOW: 240,
}

RESOLUTION_SLA_HOURS = {
    Ticket.PRIORITY_CRITICAL: 2,
    Ticket.PRIORITY_HIGH: 4,
    Ticket.PRIORITY_NORMAL: 8,
    Ticket.PRIORITY_LOW: 24,
}

DEFAULT_EQUIPMENT_CATEGORIES = [
    "Informatique",
    "Copieurs & imprimantes",
    "Froid & climatisation",
    "Groupes electrogenes",
    "Videosurveillance",
    "Geolocalisation",
    "Autre",
]

ISSUE_KEYWORDS = {
    "battery_issue": ["batterie", "charge", "autonomie"],
    "overheating_issue": ["chauffe", "temperature", "surchauffe"],
    "wiring_issue": ["cable", "branchement", "connexion", "borne"],
    "configuration_issue": ["configuration", "parametre", "reset", "wifi", "reseau"],
    "noise_issue": ["bruit", "vibration", "ventilateur"],
}


def is_manager_user(user):
    return bool(
        user
        and user.is_authenticated
        and (user.is_superuser or getattr(user, "role", "") in set(User.MANAGER_ROLES))
    )


def is_support_user(user):
    return False


def is_admin_user(user):
    return bool(user and user.is_authenticated and (user.is_superuser or getattr(user, "role", "") == User.ROLE_ADMIN))


def can_create_ticket(user):
    return bool(
        user
        and user.is_authenticated
        and getattr(user, "role", "") in TICKET_CREATOR_ROLES
    )


def is_internal_user(user):
    return bool(
        user
        and user.is_authenticated
        and (user.is_superuser or getattr(user, "role", "") in set(User.INTERNAL_ROLES))
    )


def is_platform_internal_user(user):
    return bool(is_internal_user(user) and not getattr(user, "organization_id", None))


def is_read_only_user(user):
    return bool(user and user.is_authenticated and getattr(user, "role", "") in set(User.READ_ONLY_ROLES))


def is_auditor_user(user):
    return bool(user and user.is_authenticated and getattr(user, "role", "") == User.ROLE_AUDITOR)


def has_technician_space_access(user):
    return bool(
        user
        and user.is_authenticated
        and (user.is_superuser or getattr(user, "role", "") in set(User.TECHNICIAN_SPACE_ROLES))
    )


def has_reporting_access(user):
    return bool(
        user
        and user.is_authenticated
        and (user.is_superuser or getattr(user, "role", "") in set(User.REPORTING_ROLES))
    )


def has_oversight_access(user):
    return bool(
        user
        and user.is_authenticated
        and (user.is_superuser or getattr(user, "role", "") in set(User.OVERSIGHT_ROLES))
    )


def has_backoffice_access(user):
    return bool(is_internal_user(user) or is_read_only_user(user))


def role_workspace_name(user):
    if not user or not user.is_authenticated:
        return "login"
    if user.role == User.ROLE_CLIENT:
        return "support-page"
    if user.role in set(User.TECHNICIAN_SPACE_ROLES):
        return "technician-space"
    if user.role == User.ROLE_AUDITOR:
        return "reporting-page"
    if user.role in {User.ROLE_HEAD_SAV, User.ROLE_ADMIN, User.ROLE_MANAGER}:
        return "dashboard"
    return "dashboard"


def role_default_processing_status(user):
    if not user or not user.is_authenticated:
        return Ticket.STATUS_NEW
    return Ticket.STATUS_IN_PROGRESS


def scope_by_access(queryset, user, own_relation, organization_relation="organization"):
    if not user or not user.is_authenticated:
        return queryset.none()
    if has_backoffice_access(user):
        if user.is_superuser or not user.organization_id:
            return queryset
        return queryset.filter(**{organization_relation: user.organization})
    return queryset.filter(**{own_relation: user})


def scope_by_client_relation(queryset, user, relation):
    if not user or not user.is_authenticated:
        return queryset.none()
    if has_backoffice_access(user):
        if user.is_superuser or not user.organization_id:
            return queryset
        return queryset.filter(**{f"{relation}__organization": user.organization})
    return queryset.filter(**{relation: user})


def scope_user_queryset(queryset, user):
    if not user or not user.is_authenticated:
        return queryset.none()
    if user.is_superuser:
        return queryset
    if has_oversight_access(user):
        if user.organization_id:
            return queryset.filter(organization=user.organization)
        return queryset
    if getattr(user, "role", "") in set(User.INTERNAL_ROLES):
        queryset = queryset.filter(role=User.ROLE_CLIENT)
        if user.organization_id:
            return queryset.filter(organization=user.organization)
        return queryset
    return queryset.filter(id=user.id)


def scope_ticket_queryset(queryset, user):
    if not user or not user.is_authenticated:
        return queryset.none()
    if user.is_superuser:
        return queryset
    if has_backoffice_access(user):
        if user.organization_id:
            queryset = queryset.filter(
                Q(organization=user.organization)
                | Q(client__organization=user.organization)
                | Q(product__organization=user.organization)
            ).distinct()
        if getattr(user, "role", "") == User.ROLE_HEAD_SAV:
            return queryset
        if getattr(user, "role", "") in set(User.ASSIGNABLE_ROLES):
            return queryset.filter(Q(assigned_agent=user) | Q(interventions__agent=user)).distinct()
        if is_admin_user(user):
            return queryset.none()
        return queryset.filter(Q(created_by=user) | Q(assigned_agent=user) | Q(interventions__agent=user)).distinct()
    return queryset.filter(client=user)


def scope_product_queryset(queryset, user):
    return scope_by_access(queryset, user, "client", "organization")


def scope_equipment_category_queryset(queryset, user):
    if not user or not user.is_authenticated:
        return queryset.none()
    if user.is_superuser or not user.organization_id:
        return queryset
    return queryset.filter(Q(organization=user.organization) | Q(organization__isnull=True))


def _scope_ticket_related_queryset(queryset, user, ticket_relation):
    if not user or not user.is_authenticated:
        return queryset.none()
    visible_tickets = scope_ticket_queryset(Ticket.objects.all(), user)
    return queryset.filter(**{f"{ticket_relation}__in": visible_tickets})


def scope_message_queryset(queryset, user):
    queryset = _scope_ticket_related_queryset(queryset, user, "ticket")
    if not user or not user.is_authenticated:
        return queryset.none()
    if getattr(user, "role", "") == User.ROLE_HEAD_SAV:
        return queryset
    queryset = queryset.filter(Q(recipient__isnull=True) | Q(recipient=user) | Q(sender=user))
    if not has_backoffice_access(user) and not getattr(user, "is_superuser", False):
        queryset = queryset.exclude(message_type=Message.TYPE_INTERNAL)
    return queryset


def scope_attachment_queryset(queryset, user):
    return _scope_ticket_related_queryset(queryset, user, "ticket")


def scope_intervention_queryset(queryset, user):
    return _scope_ticket_related_queryset(queryset, user, "ticket")


def scope_intervention_media_queryset(queryset, user):
    return _scope_ticket_related_queryset(queryset, user, "intervention__ticket")


def scope_ticket_assignment_queryset(queryset, user):
    return _scope_ticket_related_queryset(queryset, user, "ticket")


def scope_client_contact_queryset(queryset, user):
    return scope_by_access(queryset, user, "client", "organization")


def scope_support_session_queryset(queryset, user):
    return _scope_ticket_related_queryset(queryset, user, "ticket")


def scope_predictive_alert_queryset(queryset, user):
    return scope_by_access(queryset, user, "product__client", "product__organization")


def scope_notification_queryset(queryset, user):
    if not user or not user.is_authenticated:
        return queryset.none()
    return queryset.filter(recipient=user)


def scope_knowledge_article_queryset(queryset, user):
    if not user or not user.is_authenticated:
        return queryset.none()
    if has_backoffice_access(user):
        if user.is_superuser or not user.organization_id:
            return queryset
        return queryset.filter(Q(organization=user.organization) | Q(organization__isnull=True))
    return queryset.filter(
        status=KnowledgeArticle.STATUS_PUBLISHED,
        audience=KnowledgeArticle.AUDIENCE_PUBLIC,
    ).filter(Q(organization=user.organization) | Q(organization__isnull=True))


def scope_offer_queryset(queryset, user):
    return scope_by_access(queryset, user, "client", "organization")


def scope_account_credit_queryset(queryset, user):
    if not is_admin_user(user):
        return queryset.none()
    return scope_by_access(queryset, user, "client", "organization")


def scope_financial_transaction_queryset(queryset, user):
    return scope_by_access(queryset, user, "client", "organization")


def scope_ticket_feedback_queryset(queryset, user):
    return scope_by_access(queryset, user, "ticket__client", "organization")


def scope_ai_action_queryset(queryset, user):
    return scope_by_access(queryset, user, "ticket__client", "organization")


def scope_automation_rule_queryset(queryset, user):
    if not user or not user.is_authenticated:
        return queryset.none()
    if user.is_superuser or not user.organization_id:
        return queryset
    return queryset.filter(Q(organization=user.organization) | Q(organization__isnull=True))


def scope_sla_rule_queryset(queryset, user):
    if not user or not user.is_authenticated:
        return queryset.none()
    if user.is_superuser or not user.organization_id:
        return queryset
    return queryset.filter(Q(organization=user.organization) | Q(organization__isnull=True))


def scope_workflow_execution_queryset(queryset, user):
    return scope_by_access(queryset, user, "ticket__client", "organization")


def scope_generated_report_queryset(queryset, user):
    if not user or not user.is_authenticated:
        return queryset.none()
    if not has_backoffice_access(user) and not user.is_superuser:
        return queryset.none()
    if user.is_superuser or not user.organization_id:
        return queryset
    return queryset.filter(organization=user.organization)


def scope_audit_log_queryset(queryset, user):
    if not user or not user.is_authenticated:
        return queryset.none()
    if user.is_superuser or not user.organization_id:
        return queryset
    return queryset.filter(organization=user.organization)


def organization_for_instance(instance):
    if instance is None:
        return None
    organization = getattr(instance, "organization", None)
    if organization is not None:
        return organization
    for attr_name in ["ticket", "product", "client", "recipient", "user", "actor", "rule"]:
        related = getattr(instance, attr_name, None)
        if related is not None and getattr(related, "organization", None) is not None:
            return related.organization
    return None


def manager_queryset_for_organization(organization=None):
    queryset = User.objects.filter(is_active=True).filter(Q(role__in=User.MANAGER_ROLES) | Q(is_superuser=True))
    if organization is None:
        return queryset
    scoped_queryset = queryset.filter(Q(organization=organization) | Q(is_superuser=True))
    if scoped_queryset.exists():
        return scoped_queryset
    return queryset.filter(Q(organization__isnull=True) | Q(is_superuser=True))


def assignment_eligible_queryset_for_organization(organization=None):
    queryset = User.objects.filter(
        role__in=User.ASSIGNABLE_ROLES,
        technician_status="available",
        is_active=True,
    )
    if organization is None:
        return queryset
    scoped_queryset = queryset.filter(organization=organization)
    if scoped_queryset.exists():
        return scoped_queryset
    return queryset.filter(organization__isnull=True)


def field_technician_queryset_for_organization(organization=None):
    queryset = User.objects.filter(
        role=User.ROLE_TECHNICIAN,
        technician_status="available",
        is_active=True,
    )
    if organization is None:
        return queryset
    scoped_queryset = queryset.filter(organization=organization)
    if scoped_queryset.exists():
        return scoped_queryset
    return queryset.filter(organization__isnull=True)


def _select_least_loaded_agent_for_roles(*, roles, organization=None, exclude_user_ids=None):
    exclude_user_ids = [user_id for user_id in (exclude_user_ids or []) if user_id]
    queryset = User.objects.filter(is_active=True, role__in=roles)
    if organization is not None:
        scoped_queryset = queryset.filter(organization=organization)
        if scoped_queryset.exists():
            queryset = scoped_queryset
        else:
            queryset = queryset.filter(organization__isnull=True)
    if exclude_user_ids:
        queryset = queryset.exclude(pk__in=exclude_user_ids)
    return (
        queryset
        .annotate(
            open_ticket_count=Count(
                "assigned_tickets",
                filter=Q(assigned_tickets__status__in=OPEN_TICKET_STATUSES),
            )
        )
        .order_by("open_ticket_count", "id")
        .first()
    )


def next_ticket_priority(priority):
    priority = (priority or Ticket.PRIORITY_NORMAL).strip().lower()
    try:
        current_index = ESCALATION_PRIORITY_SEQUENCE.index(priority)
    except ValueError:
        return Ticket.PRIORITY_HIGH
    if current_index >= len(ESCALATION_PRIORITY_SEQUENCE) - 1:
        return ESCALATION_PRIORITY_SEQUENCE[-1]
    return ESCALATION_PRIORITY_SEQUENCE[current_index + 1]


def select_escalation_agent(ticket, *, target=ESCALATION_TARGET_CHIEF_TECHNICIAN):
    current_agent = getattr(ticket, "assigned_agent", None)
    exclude_ids = [getattr(current_agent, "id", None)]
    normalized_target = (target or ESCALATION_TARGET_CHIEF_TECHNICIAN).strip().lower()
    roles = ESCALATION_TARGET_ROLE_MAP.get(normalized_target)
    if roles:
        return _select_least_loaded_agent_for_roles(
            roles=roles,
            organization=ticket.organization,
            exclude_user_ids=exclude_ids,
        )

    return None


def create_notification(recipient, subject, message, channel=Notification.CHANNEL_IN_APP, event_type="info", ticket=None):
    notification = Notification.objects.create(
        recipient=recipient,
        ticket=ticket,
        channel=channel,
        event_type=event_type,
        subject=subject,
        message=message,
        status=Notification.STATUS_PENDING,
    )
    deliver_notification(notification)
    return notification


def ensure_default_sla_rules(organization):
    created_rules = []
    if organization is None:
        return created_rules
    for priority, _label in Ticket.PRIORITY_CHOICES:
        rule, created = SlaRule.objects.get_or_create(
            organization=organization,
            priority=priority,
            defaults={
                "response_deadline_minutes": RESPONSE_SLA_MINUTES.get(priority, RESPONSE_SLA_MINUTES[Ticket.PRIORITY_NORMAL]),
                "resolution_deadline_hours": RESOLUTION_SLA_HOURS.get(priority, RESOLUTION_SLA_HOURS[Ticket.PRIORITY_NORMAL]),
                "is_active": True,
            },
        )
        if created:
            created_rules.append(rule)
    return created_rules


def ensure_default_equipment_categories(organization):
    created_categories = []
    if organization is None:
        return created_categories
    for name in DEFAULT_EQUIPMENT_CATEGORIES:
        category, created = EquipmentCategory.objects.get_or_create(
            organization=organization,
            name=name,
            defaults={"description": f"Categorie standard AFRILUX: {name}"},
        )
        if created:
            created_categories.append(category)
    return created_categories


def _resolve_sla_rule(priority, organization=None):
    queryset = SlaRule.objects.filter(priority=priority, is_active=True)
    if organization is not None:
        rule = queryset.filter(organization=organization).order_by("-created_at").first()
        if rule:
            return rule
    return queryset.filter(organization__isnull=True).order_by("-created_at").first()


def get_sla_rule_values(priority, organization=None):
    rule = _resolve_sla_rule(priority, organization=organization)
    if rule:
        return rule.response_deadline_minutes, rule.resolution_deadline_hours
    return (
        RESPONSE_SLA_MINUTES.get(priority, RESPONSE_SLA_MINUTES[Ticket.PRIORITY_NORMAL]),
        RESOLUTION_SLA_HOURS.get(priority, RESOLUTION_SLA_HOURS[Ticket.PRIORITY_NORMAL]),
    )


def compute_ticket_response_deadline(priority, base_time=None, organization=None):
    base_time = base_time or timezone.now()
    response_minutes, _resolution_hours = get_sla_rule_values(priority, organization=organization)
    return base_time + timedelta(minutes=response_minutes)


def compute_ticket_sla_deadline(priority, base_time=None, organization=None):
    base_time = base_time or timezone.now()
    _response_minutes, resolution_hours = get_sla_rule_values(priority, organization=organization)
    return base_time + timedelta(hours=resolution_hours)


def generate_client_username(email):
    base = re.sub(r"[^a-z0-9]+", "_", email.split("@")[0].lower()).strip("_") or "client"
    username = base[:140]
    suffix = 2
    while User.objects.filter(username=username).exists():
        username = f"{base[:130]}_{suffix}"
        suffix += 1
    return username[:150]


@transaction.atomic
def provision_client_account(
    *,
    organization,
    email,
    password,
    first_name="",
    last_name="",
    phone="",
    company_name="",
    client_type="",
    sector="",
    tax_identifier="",
    address="",
):
    normalized_email = (email or "").strip().lower()
    if not normalized_email:
        raise ValueError("L'email est obligatoire.")
    if not password:
        raise ValueError("Le mot de passe est obligatoire.")

    existing = User.objects.filter(email__iexact=normalized_email).order_by("id").first()
    created = False

    if existing:
        if existing.role != User.ROLE_CLIENT:
            raise ValueError("Cet email est deja utilise par un compte interne.")
        if existing.organization_id and organization and existing.organization_id != organization.id:
            if existing.organization.slug != "contacts-entrants":
                raise ValueError("Cet email est deja rattache a une autre organisation.")
            existing.organization = organization
        if existing.has_usable_password():
            raise ValueError("Un compte client existe deja avec cet email.")
        user = existing
    else:
        user = User(
            username=generate_client_username(normalized_email),
            email=normalized_email,
            role=User.ROLE_CLIENT,
            organization=organization,
        )
        created = True

    if organization and not user.organization_id:
        user.organization = organization
    if first_name.strip():
        user.first_name = first_name.strip()
    if last_name.strip():
        user.last_name = last_name.strip()
    if phone.strip():
        user.phone = phone.strip()
    normalized_client_type = (client_type or "").strip().lower()
    if normalized_client_type:
        user.client_type = normalized_client_type

    if company_name.strip():
        user.company_name = company_name.strip()
    elif normalized_client_type == "enterprise" and organization and not user.company_name:
        user.company_name = organization.display_name
    elif normalized_client_type and normalized_client_type != "enterprise":
        user.company_name = ""
    if sector.strip():
        user.sector = sector.strip()
    if tax_identifier.strip():
        user.tax_identifier = tax_identifier.strip()
    if address.strip():
        user.address = address.strip()

    user.email = normalized_email
    user.role = User.ROLE_CLIENT
    user.is_active = True
    user.set_password(password)
    user.save()

    log_audit_event(
        actor=user,
        actor_type=AuditLog.ACTOR_SYSTEM,
        action="client_account_registered" if created else "client_account_activated",
        instance=user,
        details={"organization": user.organization.slug if user.organization_id else "", "email": normalized_email},
    )
    return user, created


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


def calculate_sentiment(text):
    lowered_text = (text or "").lower()
    score = Decimal("0.00")

    for word in NEGATIVE_WORDS:
        if word in lowered_text:
            score -= Decimal("0.20")
    for word in POSITIVE_WORDS:
        if word in lowered_text:
            score += Decimal("0.15")

    if score < Decimal("-1.00"):
        return Decimal("-1.00")
    if score > Decimal("1.00"):
        return Decimal("1.00")
    return score.quantize(Decimal("0.01"))


def _parse_completion_json(completion):
    if not completion.ok:
        return None
    try:
        return json.loads(completion.content)
    except json.JSONDecodeError:
        return None


def _coerce_bool(value, default=False):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "oui"}
    return default


def _coerce_decimal(value, default="0.00"):
    try:
        return Decimal(str(value))
    except Exception:  # noqa: BLE001
        return Decimal(default)


def _format_money(value):
    return _coerce_decimal(value, "0.00").quantize(Decimal("0.01"))


def _clamp_confidence(value, default="0.50"):
    decimal_value = _coerce_decimal(value, default)
    if decimal_value < Decimal("0"):
        return Decimal("0")
    if decimal_value > Decimal("1"):
        return Decimal("1")
    return decimal_value.quantize(Decimal("0.01"))


def _completed_at(ticket):
    return ticket.closed_at or ticket.resolved_at


def compute_average_first_response_hours(tickets):
    total_hours = Decimal("0.00")
    responded_tickets = 0

    for ticket in tickets:
        if not ticket.first_response_at:
            continue
        hours = Decimal(str((ticket.first_response_at - ticket.created_at).total_seconds() / 3600))
        total_hours += hours
        responded_tickets += 1

    if not responded_tickets:
        return None
    return (total_hours / responded_tickets).quantize(Decimal("0.01"))


def compute_average_resolution_hours(tickets):
    total_hours = Decimal("0.00")
    completed_tickets = 0

    for ticket in tickets:
        completed_at = _completed_at(ticket)
        if not completed_at:
            continue
        hours = Decimal(str((completed_at - ticket.created_at).total_seconds() / 3600))
        total_hours += hours
        completed_tickets += 1

    if not completed_tickets:
        return None
    return (total_hours / completed_tickets).quantize(Decimal("0.01"))


def compute_agent_performance_rows(tickets, limit=5):
    rows = {}

    for ticket in tickets.select_related("assigned_agent"):
        agent = ticket.assigned_agent
        if not agent:
            continue

        row = rows.setdefault(
            agent.id,
            {
                "agent_id": agent.id,
                "agent_name": str(agent),
                "resolved_tickets": 0,
                "open_tickets": 0,
                "_resolution_hours_total": Decimal("0.00"),
                "_resolution_ticket_count": 0,
            },
        )

        if ticket.status in OPEN_TICKET_STATUSES:
            row["open_tickets"] += 1

        completed_at = _completed_at(ticket)
        if completed_at:
            row["resolved_tickets"] += 1
            row["_resolution_hours_total"] += Decimal(str((completed_at - ticket.created_at).total_seconds() / 3600))
            row["_resolution_ticket_count"] += 1

    ranked_rows = []
    for row in rows.values():
        avg_resolution = None
        if row["_resolution_ticket_count"]:
            avg_resolution = (
                row["_resolution_hours_total"] / row["_resolution_ticket_count"]
            ).quantize(Decimal("0.01"))

        ranked_rows.append(
            {
                "agent_id": row["agent_id"],
                "agent_name": row["agent_name"],
                "resolved_tickets": row["resolved_tickets"],
                "open_tickets": row["open_tickets"],
                "average_resolution_hours": avg_resolution,
            }
        )

    ranked_rows.sort(
        key=lambda row: (
            -row["resolved_tickets"],
            row["average_resolution_hours"] if row["average_resolution_hours"] is not None else Decimal("9999.99"),
            row["open_tickets"],
            row["agent_name"],
        )
    )
    return ranked_rows[:limit]


def _ticket_context(ticket):
    return {
        "reference": ticket.reference,
        "title": ticket.title,
        "description": ticket.description,
        "category": ticket.category,
        "channel": ticket.channel,
        "priority": ticket.priority,
        "status": ticket.status,
        "warranty_eligible": bool(ticket.product and ticket.product.is_under_warranty),
        "product": {
            "name": ticket.product_display_name or None,
            "serial_number": ticket.product.serial_number if ticket.product else None,
            "health_score": ticket.product.health_score if ticket.product else None,
        },
        "messages": list(ticket.messages.values("content", "channel", "direction", "message_type")[:12]),
    }


def _client_context(client):
    tickets = client.tickets.order_by("-created_at")[:20]
    recent_transactions = client.financial_transactions.order_by("-occurred_at", "-created_at")[:15]
    return {
        "client_id": client.id,
        "client_name": str(client),
        "company_name": client.company_name,
        "organization_name": client.organization.display_name if client.organization_id else "",
        "is_verified": client.is_verified,
        "client_type": client.client_type,
        "client_status": client.client_status,
        "sector": client.sector,
        "tax_identifier": client.tax_identifier,
        "address": client.address,
        "account_balance": str(client.account_balance),
        "product_count": client.products.count(),
        "contacts": [
            {
                "full_name": f"{contact.first_name} {contact.last_name}".strip(),
                "job_title": contact.job_title,
                "phone": contact.phone,
                "email": contact.email,
                "is_primary": contact.is_primary,
            }
            for contact in client.contacts.order_by("-is_primary", "first_name", "last_name")[:10]
        ],
        "tickets": [
            {
                "reference": ticket.reference,
                "title": ticket.title,
                "status": ticket.status,
                "priority": ticket.priority,
                "category": ticket.category,
            }
            for ticket in tickets
        ],
        "recent_messages": list(
            Message.objects.filter(ticket__client=client).order_by("-created_at").values("content", "direction")[:10]
        ),
        "recent_transactions": [
            {
                "external_reference": transaction.external_reference,
                "transaction_type": transaction.transaction_type,
                "ledger_side": transaction.ledger_side,
                "amount": str(transaction.amount),
                "currency": transaction.currency,
                "status": transaction.status,
                "occurred_at": transaction.occurred_at.isoformat(),
            }
            for transaction in recent_transactions
        ],
    }


def _product_context(product):
    return {
        "product_id": product.id,
        "name": product.name,
        "serial_number": product.serial_number,
        "equipment_type": product.equipment_type,
        "brand": product.brand,
        "model_reference": product.model_reference,
        "health_score": product.health_score,
        "iot_enabled": product.iot_enabled,
        "installation_date": str(product.installation_date) if product.installation_date else None,
        "warranty_end": str(product.warranty_end) if product.warranty_end else None,
        "installation_address": product.installation_address,
        "detailed_location": product.detailed_location,
        "contract_reference": product.contract_reference,
        "counter_total": product.counter_total,
        "counter_color": product.counter_color,
        "counter_bw": product.counter_bw,
        "recent_telemetry": [
            {
                "metric_name": point.metric_name,
                "value": str(point.value),
                "unit": point.unit,
                "captured_at": point.captured_at.isoformat(),
            }
            for point in product.telemetry.order_by("-captured_at")[:30]
        ],
        "recent_tickets": [
            {
                "reference": ticket.reference,
                "title": ticket.title,
                "category": ticket.category,
                "priority": ticket.priority,
            }
            for ticket in product.tickets.order_by("-created_at")[:15]
        ],
    }


def compute_ticket_hotspots(tickets, limit=6):
    counts = {}
    for ticket in tickets.select_related("product"):
        location = (ticket.location or "").strip()
        if not location and ticket.product_id:
            location = (ticket.product.detailed_location or ticket.product.installation_address or "").strip()
        if not location:
            location = "Non renseigne"
        counts[location] = counts.get(location, 0) + 1
    rows = [{"location": key, "total": value} for key, value in counts.items()]
    rows.sort(key=lambda row: (-row["total"], row["location"]))
    return rows[:limit]


def compute_ticket_volume_series(tickets, days=7):
    anchor = timezone.localdate()
    series = []
    for offset in range(days - 1, -1, -1):
        day = anchor - timedelta(days=offset)
        day_start = timezone.make_aware(datetime.combine(day, datetime.min.time()))
        day_end = day_start + timedelta(days=1)
        series.append(
            {
                "label": day.strftime("%d/%m"),
                "created": tickets.filter(created_at__gte=day_start, created_at__lt=day_end).count(),
                "resolved": tickets.filter(resolved_at__gte=day_start, resolved_at__lt=day_end).count(),
            }
        )
    return series


def compute_ticket_monthly_series(tickets, months=12):
    anchor = timezone.localdate().replace(day=1)
    series = []
    for offset in range(months - 1, -1, -1):
        month_cursor = anchor
        for _ in range(offset):
            if month_cursor.month == 1:
                month_cursor = month_cursor.replace(year=month_cursor.year - 1, month=12)
            else:
                month_cursor = month_cursor.replace(month=month_cursor.month - 1)
        month_start = timezone.make_aware(datetime.combine(month_cursor, datetime.min.time()))
        if month_cursor.month == 12:
            next_month = month_cursor.replace(year=month_cursor.year + 1, month=1)
        else:
            next_month = month_cursor.replace(month=month_cursor.month + 1)
        month_end = timezone.make_aware(datetime.combine(next_month, datetime.min.time()))
        series.append(
            {
                "label": month_cursor.strftime("%m/%Y"),
                "created": tickets.filter(created_at__gte=month_start, created_at__lt=month_end).count(),
                "resolved": tickets.filter(resolved_at__gte=month_start, resolved_at__lt=month_end).count(),
            }
        )
    return series


def compute_technician_status_rows(users):
    rows = []
    status_labels = dict(User._meta.get_field("technician_status").choices)
    for status_code, label in status_labels.items():
        rows.append(
            {
                "status": status_code,
                "label": label,
                "total": users.filter(technician_status=status_code).count(),
            }
        )
    return rows


def parse_reporting_recipients(organization):
    recipients = set()
    if not organization:
        return []
    if organization.reporting_emails:
        for item in organization.reporting_emails.replace(";", ",").split(","):
            email = item.strip().lower()
            if email:
                recipients.add(email)
    if organization.support_email:
        recipients.add(organization.support_email.strip().lower())
    users = User.objects.filter(
        organization=organization,
        is_active=True,
    ).filter(Q(role__in=User.REPORTING_ROLES) | Q(is_superuser=True))
    for user in users:
        email = (user.professional_email or user.email or "").strip().lower()
        if email:
            recipients.add(email)
    return sorted(recipients)


def generate_intervention_pdf(intervention, persist=True, force=False):
    if persist and not force and getattr(intervention, "report_pdf", None):
        try:
            with intervention.report_pdf.open("rb") as existing_report:
                return existing_report.read()
        except OSError:
            pass

    buffer = BytesIO()
    document = SimpleDocTemplate(buffer, pagesize=A4)
    styles = getSampleStyleSheet()
    data = [
        ["Numero ticket", intervention.ticket.reference],
        ["Client", str(intervention.ticket.client)],
        ["Technicien", str(intervention.agent)],
        ["Type", intervention.get_intervention_type_display()],
        ["Statut", intervention.get_status_display()],
        ["Date prevue", intervention.scheduled_for.strftime("%d/%m/%Y %H:%M") if intervention.scheduled_for else "-"],
        ["Lieu", intervention.location_snapshot or intervention.ticket.location or "-"],
        ["Diagnostic", intervention.diagnosis or "-"],
        ["Action effectuee", intervention.action_taken or "-"],
        ["Pieces utilisees", intervention.parts_used or "-"],
        ["Temps passe", f"{intervention.time_spent_minutes} min"],
        ["Signature client", intervention.client_signed_by or "-"],
    ]
    story = [
        Paragraph("Bon d'intervention AFRILUX SMART SOLUTIONS", styles["Title"]),
        Spacer(1, 12),
        Table(data, colWidths=[150, 340]),
        Spacer(1, 12),
        Paragraph("Rapport technique", styles["Heading2"]),
        Paragraph(intervention.technical_report or "Aucun rapport technique saisi.", styles["BodyText"]),
    ]
    media_items = list(intervention.media.all()[:5])
    if media_items:
        story.extend([Spacer(1, 12), Paragraph("Pieces jointes terrain", styles["Heading3"])])
        media_rows = [["Type", "Note", "Fichier"]]
        for item in media_items:
            media_rows.append([item.get_kind_display(), item.note or "-", item.file.name.split("/")[-1]])
        media_table = Table(media_rows, colWidths=[120, 220, 150])
        media_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E8D5BF")),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ]
            )
        )
        story.append(media_table)
    document.build(story)
    content = buffer.getvalue()
    if persist:
        filename = f"intervention-{slugify(intervention.ticket.reference)}-{intervention.pk}.pdf"
        intervention.report_pdf.save(filename, ContentFile(content), save=False)
        intervention.report_generated_at = timezone.now()
        intervention.save(update_fields=["report_pdf", "report_generated_at"])
    return content


def send_intervention_assignment_email(intervention, pdf_content=None):
    technician = intervention.agent
    recipient = (technician.professional_email or technician.email or "").strip()
    if not recipient:
        return False

    pdf_content = pdf_content or generate_intervention_pdf(intervention, persist=False)
    message = EmailMessage(
        subject=f"Bon d'intervention {intervention.ticket.reference}",
        body=(
            "Veuillez trouver en piece jointe votre bon d'intervention AFRILUX. "
            "Merci de mettre a jour le rapport apres passage sur site."
        ),
        to=[recipient],
    )
    filename = f"intervention-{slugify(intervention.ticket.reference)}-{intervention.pk}.pdf"
    message.attach(filename, pdf_content, "application/pdf")
    message.send(fail_silently=False)
    return True


def archive_generated_report(
    *,
    organization,
    report,
    report_type,
    export_format,
    generated_by=None,
    filename,
    content,
    sent_to="",
):
    record = GeneratedReport.objects.create(
        organization=organization,
        generated_by=generated_by,
        report_type=report_type,
        export_format=export_format,
        period_label=report.get("period_label", ""),
        payload=report,
        sent_to=sent_to,
    )
    if content:
        record.archive_file.save(filename, ContentFile(content), save=False)
        record.save(update_fields=["archive_file", "updated_at"])
    return record


def send_report_to_recipients(*, report, report_type, recipients, filename, pdf_content=None):
    if not recipients:
        return False
    message = EmailMessage(
        subject=f"{report.get('title', 'Rapport SAV')} - {report.get('period_label', '')}",
        body="Veuillez trouver en piece jointe le rapport SAV automatise.",
        to=recipients,
    )
    from .reporting import export_report_pdf

    pdf_content = pdf_content or export_report_pdf(report)
    message.attach(filename, pdf_content, "application/pdf")
    message.send(fail_silently=False)
    return True


def sync_ticket_assignment(ticket, *, assigned_by=None, note="", release_status=TicketAssignment.STATUS_RELEASED):
    active_assignments = list(
        TicketAssignment.objects.filter(
            ticket=ticket,
            status=TicketAssignment.STATUS_ACTIVE,
            released_at__isnull=True,
        ).select_related("technician")
    )
    now = timezone.now()
    current_assignment = None
    created = False
    released_ids = []

    for assignment in active_assignments:
        if ticket.assigned_agent_id and assignment.technician_id == ticket.assigned_agent_id:
            current_assignment = assignment
            continue
        assignment.status = release_status
        assignment.released_at = now
        if note:
            assignment.note = note[:500]
        assignment.save(update_fields=["status", "released_at", "note", "updated_at"])
        released_ids.append(assignment.id)

    if ticket.assigned_agent_id and current_assignment is None:
        current_assignment = TicketAssignment.objects.create(
            organization=ticket.organization,
            ticket=ticket,
            technician=ticket.assigned_agent,
            assigned_by=assigned_by if getattr(assigned_by, "is_authenticated", False) else None,
            assigned_at=now,
            note=note[:500],
        )
        created = True

    return current_assignment, created, released_ids


def escalate_ticket(
    ticket,
    *,
    actor=None,
    note="",
    target=ESCALATION_TARGET_CHIEF_TECHNICIAN,
    increase_priority=True,
    notification_event_type="ticket_escalated",
):
    if ticket.status not in OPEN_TICKET_STATUSES:
        raise ValueError("Seuls les tickets ouverts peuvent etre escalades.")

    previous_priority = ticket.priority
    previous_status = ticket.status
    previous_assigned_agent = ticket.assigned_agent
    if getattr(actor, "role", "") != User.ROLE_HEAD_SAV:
        raise ValueError("Seul le Responsable SAV peut escalader un ticket.")
    normalized_target = (target or ESCALATION_TARGET_CHIEF_TECHNICIAN).strip().lower()
    if normalized_target not in ESCALATION_ALLOWED_TARGETS:
        raise ValueError("Cible d'escalade invalide. Cibles autorisees: CFAO, travaux CFAO, froid/climatisation ou chef technicien.")
    escalation_target = select_escalation_agent(ticket, target=normalized_target)
    escalation_note = (note or "Escalade du ticket pour prise en charge de niveau superieur.").strip()[:500]

    if escalation_target is None:
        raise ValueError("Aucun utilisateur disponible pour recevoir cette escalade.")

    if increase_priority:
        ticket.priority = next_ticket_priority(ticket.priority)
    ticket.assigned_agent = escalation_target
    if previous_assigned_agent is None or previous_assigned_agent.id != escalation_target.id:
        ticket.status = Ticket.STATUS_ASSIGNED
    ticket.sla_deadline = compute_ticket_sla_deadline(ticket.priority, organization=ticket.organization)
    ticket.save(update_fields=["priority", "assigned_agent", "status", "sla_deadline", "updated_at"])

    assignment = None
    created_assignment = False
    released_ids = []
    if previous_assigned_agent is not None and previous_assigned_agent.id != ticket.assigned_agent_id:
        assignment, created_assignment, released_ids = sync_ticket_assignment(
            ticket,
            assigned_by=actor,
            note=escalation_note,
            release_status=TicketAssignment.STATUS_ESCALATED,
        )
    if ticket.assigned_agent_id:
        intervention_result = ensure_assignment_intervention(ticket, actor=actor, note=escalation_note)
        assignment = assignment or intervention_result.get("assignment")
        created_assignment = created_assignment or intervention_result.get("created_assignment", False)

    Message.objects.create(
        ticket=ticket,
        sender=actor if getattr(actor, "is_authenticated", False) else ticket.assigned_agent or ticket.client,
        message_type=Message.TYPE_INTERNAL,
        channel=Message.CHANNEL_PORTAL,
        direction=Message.DIRECTION_INTERNAL,
        content=(
            "Le ticket a ete escalade."
            f"{' Priorite: ' + previous_priority + ' -> ' + ticket.priority + '.' if previous_priority != ticket.priority else ''}"
            f"{' Nouveau referent: ' + str(ticket.assigned_agent) + '.' if ticket.assigned_agent else ''}"
        ),
        sentiment_score=calculate_sentiment("Le ticket a ete escalade."),
    )

    recipients = []
    if ticket.assigned_agent_id:
        recipients.append(ticket.assigned_agent)
    if previous_assigned_agent is not None:
        recipients.append(previous_assigned_agent)
    if getattr(actor, "is_authenticated", False):
        recipients.append(actor)
    deduped_recipients = {recipient.id: recipient for recipient in recipients if getattr(recipient, "id", None)}
    for recipient in deduped_recipients.values():
        create_external_channel_notifications(
            recipient=recipient,
            ticket=ticket,
            event_type=notification_event_type,
            subject=f"Ticket escalade {ticket.reference}",
            message=(
                f"Le ticket '{ticket.title}' a ete escalade avec une priorite {ticket.get_priority_display().lower()}."
                f"{' Nouveau referent: ' + str(ticket.assigned_agent) + '.' if ticket.assigned_agent else ''}"
            ),
        )

    log_audit_event(
        actor,
        "ticket_escalated",
        ticket,
        {
            "previous_priority": previous_priority,
            "new_priority": ticket.priority,
            "previous_status": previous_status,
            "new_status": ticket.status,
            "previous_assigned_agent": getattr(previous_assigned_agent, "id", None),
            "assigned_agent": ticket.assigned_agent_id,
            "target": normalized_target,
            "released_assignment_ids": released_ids,
            "created_assignment": created_assignment,
        },
    )

    return {
        "ticket_id": ticket.id,
        "reference": ticket.reference,
        "previous_priority": previous_priority,
        "priority": ticket.priority,
        "previous_status": previous_status,
        "status": ticket.status,
        "previous_assigned_agent": str(previous_assigned_agent) if previous_assigned_agent else None,
        "assigned_agent": str(ticket.assigned_agent) if ticket.assigned_agent else None,
        "target": normalized_target,
        "released_assignment_ids": released_ids,
        "created_assignment": created_assignment,
        "assignment_id": getattr(assignment, "id", None),
    }


def can_assign_ticket_technician(user, ticket):
    if not user or not user.is_authenticated or is_read_only_user(user):
        return False
    if user.role == User.ROLE_HEAD_SAV:
        return True
    return bool(user.role in set(User.ESCALATION_TARGET_ROLES) and ticket.assigned_agent_id == user.id)


def assign_ticket_to_technician(ticket, technician, *, actor=None, note=""):
    if ticket.status not in OPEN_TICKET_STATUSES:
        raise ValueError("Seuls les tickets ouverts peuvent etre affectes.")
    if not can_assign_ticket_technician(actor, ticket):
        raise ValueError("Seul le Responsable SAV ou le responsable escalade sur ce ticket peut affecter un technicien.")
    if not technician or technician.role != User.ROLE_TECHNICIAN:
        raise ValueError("La cible doit etre un technicien de maintenance.")
    if not technician.is_ticket_assignment_eligible:
        raise ValueError("Le technicien doit etre actif et disponible.")
    if ticket.organization_id and technician.organization_id and ticket.organization_id != technician.organization_id:
        raise ValueError("Le technicien doit appartenir a la meme organisation que le ticket.")

    previous_status = ticket.status
    previous_assigned_agent = ticket.assigned_agent
    assignment_note = (note or "Affectation du ticket a un technicien de maintenance.").strip()[:500]

    ticket.assigned_agent = technician
    if ticket.status in {Ticket.STATUS_NEW, Ticket.STATUS_WAITING, Ticket.STATUS_ASSIGNED}:
        ticket.status = Ticket.STATUS_ASSIGNED
    ticket.save(update_fields=["assigned_agent", "status", "updated_at"])
    intervention_result = ensure_assignment_intervention(ticket, actor=actor, note=assignment_note)

    Message.objects.create(
        ticket=ticket,
        sender=actor if getattr(actor, "is_authenticated", False) else technician,
        message_type=Message.TYPE_INTERNAL,
        channel=Message.CHANNEL_PORTAL,
        direction=Message.DIRECTION_INTERNAL,
        content=f"Le ticket a ete affecte au technicien {technician}.",
        sentiment_score=calculate_sentiment("Le ticket a ete affecte a un technicien."),
    )

    recipients = [technician]
    if previous_assigned_agent is not None and previous_assigned_agent.id != technician.id:
        recipients.append(previous_assigned_agent)
    if getattr(actor, "is_authenticated", False):
        recipients.append(actor)
    deduped_recipients = {recipient.id: recipient for recipient in recipients if getattr(recipient, "id", None)}
    for recipient in deduped_recipients.values():
        create_external_channel_notifications(
            recipient=recipient,
            ticket=ticket,
            event_type="ticket_technician_assigned",
            subject=f"Technicien affecte {ticket.reference}",
            message=f"Le ticket '{ticket.title}' est maintenant affecte au technicien {technician}.",
        )

    log_audit_event(
        actor,
        "ticket_technician_assigned",
        ticket,
        {
            "previous_status": previous_status,
            "new_status": ticket.status,
            "previous_assigned_agent": getattr(previous_assigned_agent, "id", None),
            "technician": technician.id,
            "created_assignment": intervention_result.get("created_assignment", False),
            "assignment_id": getattr(intervention_result.get("assignment"), "id", None),
        },
    )

    return {
        "ticket_id": ticket.id,
        "reference": ticket.reference,
        "previous_status": previous_status,
        "status": ticket.status,
        "previous_assigned_agent": str(previous_assigned_agent) if previous_assigned_agent else None,
        "assigned_agent": str(ticket.assigned_agent) if ticket.assigned_agent else None,
        "assignment_id": getattr(intervention_result.get("assignment"), "id", None),
        "created_assignment": intervention_result.get("created_assignment", False),
    }


def ensure_assignment_intervention(ticket, *, actor=None, note=""):
    if not ticket.assigned_agent_id:
        sync_ticket_assignment(ticket, assigned_by=actor, note=note)
        return {"assignment": None, "intervention": None, "emailed": False, "created_assignment": False}

    assignment, created_assignment, released_ids = sync_ticket_assignment(ticket, assigned_by=actor, note=note)
    intervention = (
        ticket.interventions.filter(
            agent=ticket.assigned_agent,
            status__in=[Intervention.STATUS_PLANNED, Intervention.STATUS_IN_PROGRESS],
        )
        .order_by("-created_at")
        .first()
    )
    if intervention is None:
        intervention = Intervention.objects.create(
            organization=ticket.organization,
            ticket=ticket,
            agent=ticket.assigned_agent,
            intervention_type=Intervention.TYPE_ON_SITE,
            status=Intervention.STATUS_PLANNED,
            scheduled_for=timezone.now(),
            action_taken="Prise en charge initiale du ticket",
            location_snapshot=ticket.location,
            technical_report="Bon d'intervention genere automatiquement a l'affectation.",
        )

    pdf_content = generate_intervention_pdf(intervention)
    emailed = False
    should_notify = bool(created_assignment or released_ids)
    if should_notify:
        try:
            emailed = send_intervention_assignment_email(intervention, pdf_content=pdf_content)
        except Exception:  # noqa: BLE001
            emailed = False
        create_external_channel_notifications(
            recipient=ticket.assigned_agent,
            ticket=ticket,
            event_type="ticket_assignment",
            subject=f"Affectation ticket {ticket.reference}",
            message=(
                f"Le ticket '{ticket.title}' vous a ete affecte. "
                f"Le bon d'intervention {intervention.pk} est disponible."
            ),
        )
        log_audit_event(
            actor=actor,
            action="ticket_assignment_synced",
            instance=ticket,
            details={
                "technician_id": ticket.assigned_agent_id,
                "assignment_id": assignment.id if assignment else None,
                "intervention_id": intervention.id,
                "emailed": emailed,
            },
        )

    return {
        "assignment": assignment,
        "intervention": intervention,
        "emailed": emailed,
        "created_assignment": created_assignment,
    }


def infer_priority_from_text(text, current_priority):
    lowered_text = (text or "").lower()
    priority_rank = {
        Ticket.PRIORITY_LOW: 1,
        Ticket.PRIORITY_NORMAL: 2,
        Ticket.PRIORITY_HIGH: 3,
        Ticket.PRIORITY_CRITICAL: 4,
    }

    inferred = current_priority
    if any(word in lowered_text for word in CRITICAL_WORDS):
        inferred = Ticket.PRIORITY_CRITICAL
    elif any(word in lowered_text for word in HIGH_PRIORITY_WORDS):
        inferred = Ticket.PRIORITY_HIGH

    return inferred if priority_rank[inferred] >= priority_rank[current_priority] else current_priority


def infer_issue_from_text(text):
    lowered_text = (text or "").lower()
    for issue, keywords in ISSUE_KEYWORDS.items():
        if any(keyword in lowered_text for keyword in keywords):
            return issue
    return "general_diagnostic"


def infer_ticket_category_from_text(text, current_category=Ticket.CATEGORY_BREAKDOWN):
    lowered_text = (text or "").lower()
    if any(word in lowered_text for word in ["bug", "erreur app", "application plante", "crash"]):
        return Ticket.CATEGORY_BUG
    if any(word in lowered_text for word in ["installation", "installer", "mise en service"]):
        return Ticket.CATEGORY_INSTALLATION
    if any(word in lowered_text for word in ["maintenance", "preventive", "entretien"]):
        return Ticket.CATEGORY_MAINTENANCE
    return current_category


def match_knowledge_articles(text, product=None, organization=None, limit=3):
    lowered_text = (text or "").lower()
    queryset = KnowledgeArticle.objects.filter(status=KnowledgeArticle.STATUS_PUBLISHED)
    scoped_organization = organization or getattr(product, "organization", None)
    if scoped_organization:
        queryset = queryset.filter(Q(organization=scoped_organization) | Q(organization__isnull=True))
    if product and product.organization_id:
        queryset = queryset.filter(Q(organization=product.organization) | Q(organization__isnull=True))
    if product:
        queryset = queryset.filter(Q(product=product) | Q(product__isnull=True))

    ranked_articles = []
    for article in queryset:
        score = 0
        keyword_blob = " ".join(filter(None, [article.title, article.summary, article.keywords, article.content])).lower()
        for token in set(lowered_text.split()):
            if len(token) > 3 and token in keyword_blob:
                score += 1
        if score:
            ranked_articles.append((score, article))

    ranked_articles.sort(key=lambda item: (-item[0], item[1].title))
    return [
        {
            "id": article.id,
            "title": article.title,
            "slug": article.slug,
            "summary": article.summary,
            "score": score,
        }
        for score, article in ranked_articles[:limit]
    ]


def answer_support_question(question, user, product=None, ticket=None):
    full_text = " ".join(
        filter(
            None,
            [
                question,
                getattr(ticket, "title", ""),
                getattr(ticket, "description", ""),
                getattr(product, "name", ""),
            ],
        )
    )
    matching_articles = match_knowledge_articles(
        full_text,
        product=product or getattr(ticket, "product", None),
        organization=getattr(ticket, "organization", None)
        or getattr(product, "organization", None)
        or getattr(user, "organization", None),
    )
    suggested_priority = infer_priority_from_text(full_text, getattr(ticket, "priority", Ticket.PRIORITY_NORMAL))
    suggested_category = infer_ticket_category_from_text(
        full_text,
        getattr(ticket, "category", Ticket.CATEGORY_BREAKDOWN),
    )
    likely_issue = infer_issue_from_text(full_text)
    should_create_ticket = ticket is None and (
        suggested_priority in {Ticket.PRIORITY_HIGH, Ticket.PRIORITY_CRITICAL}
        or any(keyword in full_text.lower() for keyword in ["probleme", "panne", "reclamation", "incident"])
    )

    if matching_articles:
        answer = (
            f"Je recommande d'abord l'article '{matching_articles[0]['title']}' pour guider la resolution. "
            "Si le probleme persiste, ouvrez ou mettez a jour un ticket afin qu'un agent prenne le relais."
        )
        recommended_next_step = f"Consulter {matching_articles[0]['title']}"
    else:
        answer = (
            "Je n'ai pas trouve d'article parfaitement cible. Decrivez l'incident avec le contexte produit, "
            "les symptomes, les captures ou recus, puis ouvrez un ticket pour prise en charge rapide."
        )
        recommended_next_step = "Creer ou mettre a jour un ticket avec des preuves"

    openai_data = None
    if LLM_CLIENT.enabled:
        system_prompt = (
            "You are Afrilux SAV's support assistant. Return valid JSON only with keys: "
            "answer, suggested_priority, suggested_category, likely_issue, should_create_ticket, "
            "recommended_next_step, draft_title, draft_description, recommended_article_slug, confidence."
        )
        user_prompt = (
            "Answer this support question using the available context.\n"
            f"{json.dumps({'question': question, 'ticket': _ticket_context(ticket) if ticket else None, 'product': _product_context(product) if product else None, 'knowledge': matching_articles}, ensure_ascii=False)}"
        )
        openai_data = _parse_completion_json(LLM_CLIENT.complete_json(system_prompt, user_prompt))

    if openai_data:
        answer = openai_data.get("answer") or answer
        suggested_priority = openai_data.get("suggested_priority") or suggested_priority
        suggested_category = openai_data.get("suggested_category") or suggested_category
        likely_issue = openai_data.get("likely_issue") or likely_issue
        should_create_ticket = _coerce_bool(openai_data.get("should_create_ticket"), should_create_ticket)
        recommended_next_step = openai_data.get("recommended_next_step") or recommended_next_step
        if openai_data.get("recommended_article_slug"):
            matching_articles = [
                article for article in matching_articles if article["slug"] == openai_data.get("recommended_article_slug")
            ] or matching_articles
        confidence = _clamp_confidence(openai_data.get("confidence"), "0.82")
        draft_title = openai_data.get("draft_title") or question[:80]
        draft_description = openai_data.get("draft_description") or question
    else:
        confidence = Decimal("0.79")
        draft_title = question[:80]
        draft_description = question

    ai_log = AIActionLog.objects.create(
        organization=getattr(user, "organization", None) or getattr(ticket, "organization", None) or getattr(product, "organization", None),
        ticket=ticket,
        product=product,
        action_type=AIActionLog.ACTION_DIAGNOSIS,
        status=AIActionLog.STATUS_EXECUTED,
        confidence=confidence,
        rationale="Assistant support alimente par la knowledge base, les heuristiques SAV et OpenAI si configure.",
        input_snapshot={"question": question, "user_id": getattr(user, "id", None)},
        output_snapshot={
            "suggested_priority": suggested_priority,
            "suggested_category": suggested_category,
            "likely_issue": likely_issue,
            "matched_articles": matching_articles,
            "should_create_ticket": should_create_ticket,
            "llm_used": bool(openai_data),
        },
        approved_by=None,
    )

    return {
        "answer": answer,
        "suggested_priority": suggested_priority,
        "suggested_category": suggested_category,
        "likely_issue": likely_issue,
        "matched_articles": matching_articles,
        "recommended_next_step": recommended_next_step,
        "should_create_ticket": should_create_ticket,
        "draft_ticket": {
            "title": draft_title,
            "description": draft_description,
            "category": suggested_category,
            "priority": suggested_priority,
        },
        "ai_action_id": ai_log.id,
    }


def select_least_loaded_agent(organization=None):
    queryset = assignment_eligible_queryset_for_organization(organization=organization)
    return (
        queryset
        .annotate(
            open_ticket_count=Count(
                "assigned_tickets",
                filter=Q(assigned_tickets__status__in=OPEN_TICKET_STATUSES),
            )
        )
        .order_by("open_ticket_count", "id")
        .first()
    )


def ensure_offer(client, offer_type, title, description, rationale, price, ticket=None, product=None, valid_days=30):
    existing_offer = OfferRecommendation.objects.filter(
        client=client,
        product=product,
        offer_type=offer_type,
        status=OfferRecommendation.STATUS_PROPOSED,
    ).first()
    if existing_offer:
        return existing_offer, False

    offer = OfferRecommendation.objects.create(
        client=client,
        ticket=ticket,
        product=product,
        offer_type=offer_type,
        title=title,
        description=description,
        rationale=rationale,
        price=price,
        valid_until=timezone.now() + timedelta(days=valid_days),
    )
    return offer, True


def generate_offer_recommendations(client, ticket=None, product=None, persist=True):
    product = product or getattr(ticket, "product", None)
    offers = []

    if product and product.warranty_end:
        days_to_warranty_end = (product.warranty_end - timezone.localdate()).days
        if 0 <= days_to_warranty_end <= 60:
            offer_data = {
                "offer_type": OfferRecommendation.TYPE_WARRANTY_EXTENSION,
                "title": "Extension de garantie Afrilux",
                "description": "Etendez la couverture de votre equipement pour 12 mois supplementaires.",
                "rationale": "La garantie du produit arrive a expiration bientot.",
                "price": Decimal("25000.00"),
            }
            offers.append(offer_data)

    if product:
        breakdown_count = product.tickets.filter(category=Ticket.CATEGORY_BREAKDOWN).count()
        if breakdown_count >= 2:
            offer_data = {
                "offer_type": OfferRecommendation.TYPE_MAINTENANCE_CONTRACT,
                "title": "Contrat de maintenance predictive",
                "description": "Programme de maintenance preventive avec surveillance et priorite d'intervention.",
                "rationale": "Le produit presente des incidents repetes. Un contrat reduit le risque d'arret.",
                "price": Decimal("60000.00"),
            }
            offers.append(offer_data)

        if breakdown_count >= 3 or product.health_score <= 60:
            offer_data = {
                "offer_type": OfferRecommendation.TYPE_UPGRADE,
                "title": "Offre de mise a niveau produit",
                "description": "Remplacez l'equipement actuel par une version plus recente et plus fiable.",
                "rationale": "Les pannes recurrentes et l'etat de sante du produit suggerent une mise a niveau.",
                "price": Decimal("120000.00"),
            }
            offers.append(offer_data)

    if ticket and ticket.priority == Ticket.PRIORITY_CRITICAL:
        offer_data = {
            "offer_type": OfferRecommendation.TYPE_PREMIUM_SUPPORT,
            "title": "Support premium 24/7",
            "description": "Beneficiez d'un SLA renforce et d'un canal prioritaire pour vos incidents critiques.",
            "rationale": "Ce client rencontre un incident critique et peut beneficier d'un support renforce.",
            "price": Decimal("45000.00"),
        }
        offers.append(offer_data)

    if not persist:
        return offers

    persisted_offers = []
    for offer in offers:
        offer_obj, created = ensure_offer(
            client=client,
            ticket=ticket,
            product=product,
            offer_type=offer["offer_type"],
            title=offer["title"],
            description=offer["description"],
            rationale=offer["rationale"],
            price=offer["price"],
        )
        persisted_offers.append({"offer": offer_obj, "created": created})
    return persisted_offers


def apply_agentic_resolution(ticket, approved_by=None):
    previous_status = ticket.status
    openai_data = None
    content_parts = [ticket.title, ticket.description]
    content_parts.extend(ticket.messages.values_list("content", flat=True))
    full_text = " ".join(filter(None, content_parts))
    sentiment = calculate_sentiment(full_text)
    suggested_priority = infer_priority_from_text(full_text, ticket.priority)
    likely_issue = infer_issue_from_text(full_text)
    matching_articles = match_knowledge_articles(full_text, product=ticket.product, organization=ticket.organization)

    if LLM_CLIENT.enabled:
        system_prompt = (
            "You are Afrilux SAV's autonomous support agent. "
            "Return valid JSON only with keys: summary, suggested_priority, likely_issue, "
            "auto_resolve, resolution_summary, recommended_article_slug, actions_taken, confidence. "
            "Only set auto_resolve to true for simple self-service fixes or obvious under-warranty replacement guidance."
        )
        user_prompt = (
            "Analyse this support ticket and propose the next action.\n"
            f"{json.dumps(_ticket_context(ticket), ensure_ascii=False)}\n"
            f"Knowledge article candidates: {json.dumps(matching_articles, ensure_ascii=False)}"
        )
        openai_data = _parse_completion_json(LLM_CLIENT.complete_json(system_prompt, user_prompt))

    if openai_data:
        suggested_priority = openai_data.get("suggested_priority") or suggested_priority
        likely_issue = openai_data.get("likely_issue") or likely_issue
        if openai_data.get("recommended_article_slug"):
            matching_articles = [
                article for article in matching_articles if article["slug"] == openai_data.get("recommended_article_slug")
            ] or matching_articles
        llm_auto_resolve = _coerce_bool(openai_data.get("auto_resolve"), default=False)
        llm_resolution_summary = openai_data.get("resolution_summary", "")
        llm_actions = [str(item) for item in openai_data.get("actions_taken", []) if item]
        llm_confidence = _clamp_confidence(openai_data.get("confidence"), "0.70")
    else:
        llm_auto_resolve = False
        llm_resolution_summary = ""
        llm_actions = []
        llm_confidence = Decimal("0.78")

    actions_taken = []
    auto_resolved = False
    warranty_eligible = bool(ticket.product and ticket.product.is_under_warranty)

    if suggested_priority != ticket.priority:
        ticket.priority = suggested_priority
        if ticket.is_open:
            ticket.sla_deadline = compute_ticket_sla_deadline(suggested_priority, organization=ticket.organization)
        actions_taken.append("priority_recalculated")

    if not ticket.first_response_at:
        ticket.first_response_at = timezone.now()
        actions_taken.append("first_response_recorded")

    if llm_auto_resolve and llm_resolution_summary:
        ticket.status = Ticket.STATUS_RESOLVED
        ticket.resolution_summary = llm_resolution_summary
        actions_taken.extend(llm_actions or ["llm_auto_resolution"])
        auto_resolved = True
    elif "garantie" in full_text.lower() and warranty_eligible:
        ticket.status = Ticket.STATUS_RESOLVED
        ticket.resolution_summary = (
            "Resolution agentique: cas sous garantie detecte, orientation echange standard automatisee."
        )
        actions_taken.append("warranty_exchange_approved")
        auto_resolved = True
    elif likely_issue in {"wiring_issue", "configuration_issue"} and matching_articles:
        article = matching_articles[0]
        ticket.status = Ticket.STATUS_RESOLVED
        ticket.resolution_summary = (
            f"Resolution agentique via auto-assistance. Consultez l'article '{article['title']}' pour la procedure guidee."
        )
        actions_taken.append("self_service_resolution")
        auto_resolved = True

    ticket.save()
    notify_ticket_status_change(ticket, previous_status, actor=approved_by)

    created_offers = generate_offer_recommendations(client=ticket.client, ticket=ticket, product=ticket.product, persist=True)

    if auto_resolved:
        create_external_channel_notifications(
            recipient=ticket.client,
            ticket=ticket,
            event_type="ticket_auto_resolved",
            subject=f"Votre ticket {ticket.reference} a ete resolu",
            message=ticket.resolution_summary,
        )

    output_snapshot = {
        "ticket_reference": ticket.reference,
        "sentiment_score": str(sentiment),
        "suggested_priority": suggested_priority,
        "likely_issue": likely_issue,
        "matching_articles": matching_articles,
        "actions_taken": actions_taken,
        "auto_resolved": auto_resolved,
        "offers_generated": [item["offer"].id for item in created_offers],
        "llm_used": bool(openai_data),
        "llm_output": openai_data or {},
    }

    ai_log = AIActionLog.objects.create(
        ticket=ticket,
        product=ticket.product,
        action_type=AIActionLog.ACTION_AUTO_RESOLUTION if auto_resolved else AIActionLog.ACTION_DIAGNOSIS,
        status=AIActionLog.STATUS_EXECUTED if auto_resolved else AIActionLog.STATUS_SUGGESTED,
        confidence=Decimal("0.92") if auto_resolved and not openai_data else llm_confidence,
        rationale=(
            "Decision basee sur le contexte ticket, la base de connaissances et la couche LLM OpenAI lorsqu'elle est configuree."
        ),
        input_snapshot={
            "title": ticket.title,
            "category": ticket.category,
            "priority": ticket.priority,
            "warranty_eligible": warranty_eligible,
        },
        output_snapshot=output_snapshot,
        approved_by=approved_by,
    )

    log_audit_event(
        actor=approved_by,
        actor_type=AuditLog.ACTOR_AI,
        action="agentic_resolution",
        instance=ticket,
        details={"ai_action_id": ai_log.id, "output": output_snapshot},
    )

    return {
        "ticket_reference": ticket.reference,
        "status": ticket.status,
        "resolution_summary": ticket.resolution_summary,
        "sentiment_score": str(sentiment),
        "likely_issue": likely_issue,
        "matching_articles": matching_articles,
        "actions_taken": actions_taken,
        "auto_resolved": auto_resolved,
        "offers_generated": [item["offer"].id for item in created_offers],
        "ai_action_id": ai_log.id,
    }


def build_customer_insight(client):
    tickets = client.tickets.all()
    messages = Message.objects.filter(ticket__client=client, direction=Message.DIRECTION_INBOUND)
    recent_transactions = client.financial_transactions.order_by("-occurred_at", "-created_at")[:8]
    disputed_transactions = client.financial_transactions.filter(status=FinancialTransaction.STATUS_DISPUTED).count()

    repeat_issue_groups = list(
        tickets.values("category", "product__name")
        .annotate(total=Count("id"))
        .filter(total__gt=1)
        .order_by("-total")[:5]
    )

    critical_open_tickets = tickets.filter(priority=Ticket.PRIORITY_CRITICAL, status__in=OPEN_TICKET_STATUSES).count()
    open_tickets = tickets.filter(status__in=OPEN_TICKET_STATUSES).count()
    resolved_tickets = tickets.filter(status=Ticket.STATUS_RESOLVED).count()
    average_sentiment = Decimal("0.00")
    sentiment_count = 0

    for message in messages:
        text = message.content
        score = message.sentiment_score if message.sentiment_score is not None else calculate_sentiment(text)
        average_sentiment += score
        sentiment_count += 1

    if sentiment_count:
        average_sentiment = (average_sentiment / sentiment_count).quantize(Decimal("0.01"))

    if critical_open_tickets or average_sentiment <= Decimal("-0.50"):
        risk_level = "high"
    elif open_tickets >= 2 or repeat_issue_groups:
        risk_level = "medium"
    else:
        risk_level = "low"

    recommended_offers = generate_offer_recommendations(client=client, persist=False)

    summary = (
        f"{client} possede {client.products.count()} equipement(s), {open_tickets} ticket(s) ouvert(s), "
        f"un solde de {client.account_balance} et un niveau de risque {risk_level}."
    )

    openai_data = None
    if LLM_CLIENT.enabled:
        system_prompt = (
            "You are an Afrilux customer success analyst. "
            "Return valid JSON only with keys: summary, risk_level, focus_points, suggested_actions, confidence."
        )
        user_prompt = (
            "Build a concise customer insight summary from this account context:\n"
            f"{json.dumps(_client_context(client), ensure_ascii=False)}"
        )
        openai_data = _parse_completion_json(LLM_CLIENT.complete_json(system_prompt, user_prompt))

    if openai_data:
        summary = openai_data.get("summary") or summary
        risk_level = openai_data.get("risk_level") or risk_level
        suggested_actions = [str(item) for item in openai_data.get("suggested_actions", []) if item]
        confidence = _clamp_confidence(openai_data.get("confidence"), "0.80")
    else:
        suggested_actions = []
        confidence = Decimal("0.84")

    ai_log = AIActionLog.objects.create(
        organization=client.organization,
        action_type=AIActionLog.ACTION_INSIGHT_SUMMARY,
        status=AIActionLog.STATUS_EXECUTED,
        confidence=confidence,
        rationale="Synthese client construite a partir de l'historique tickets, des interactions et de la couche OpenAI si configuree.",
        input_snapshot={"client_id": client.id},
        output_snapshot={
            "risk_level": risk_level,
            "open_tickets": open_tickets,
            "llm_used": bool(openai_data),
            "llm_output": openai_data or {},
        },
        approved_by=None,
    )

    return {
        "client_id": client.id,
        "client_name": str(client),
        "summary": summary,
        "risk_level": risk_level,
        "open_tickets": open_tickets,
        "critical_open_tickets": critical_open_tickets,
        "resolved_tickets": resolved_tickets,
        "account_balance": str(client.account_balance),
        "is_verified": client.is_verified,
        "disputed_transactions": disputed_transactions,
        "recent_transactions": [
            {
                "external_reference": item.external_reference,
                "transaction_type": item.transaction_type,
                "amount": str(item.amount),
                "currency": item.currency,
                "status": item.status,
                "occurred_at": item.occurred_at.isoformat(),
            }
            for item in recent_transactions
        ],
        "average_sentiment": str(average_sentiment),
        "repeat_issue_groups": repeat_issue_groups,
        "recommended_offers": recommended_offers,
        "suggested_actions": suggested_actions,
        "ai_action_id": ai_log.id,
    }


def _create_predictive_alert(
    product,
    alert_type,
    severity,
    title,
    description,
    recommended_action,
    metric_name="",
    metric_value=None,
    predicted_failure_at=None,
):
    existing_alert = PredictiveAlert.objects.filter(
        product=product,
        alert_type=alert_type,
        metric_name=metric_name,
        status__in=[PredictiveAlert.STATUS_OPEN, PredictiveAlert.STATUS_IN_PROGRESS],
    ).first()
    if existing_alert:
        return existing_alert, False

    alert = PredictiveAlert.objects.create(
        product=product,
        alert_type=alert_type,
        severity=severity,
        title=title,
        description=description,
        metric_name=metric_name,
        metric_value=metric_value,
        predicted_failure_at=predicted_failure_at,
        recommended_action=recommended_action,
    )
    return alert, True


def run_predictive_analysis(product, approved_by=None):
    now = timezone.now()
    latest_telemetry = {}
    for point in product.telemetry.order_by("-captured_at")[:100]:
        latest_telemetry.setdefault(point.metric_name.lower(), point)

    alerts_created = []
    severity_penalty = 0

    thresholds = {
        "temperature": [(Decimal("80"), PredictiveAlert.SEVERITY_CRITICAL), (Decimal("70"), PredictiveAlert.SEVERITY_HIGH)],
        "vibration": [(Decimal("7"), PredictiveAlert.SEVERITY_HIGH), (Decimal("5"), PredictiveAlert.SEVERITY_MEDIUM)],
        "error_rate": [(Decimal("10"), PredictiveAlert.SEVERITY_CRITICAL), (Decimal("5"), PredictiveAlert.SEVERITY_HIGH)],
    }

    for metric_name, point in latest_telemetry.items():
        if metric_name not in thresholds:
            continue
        for threshold, severity in thresholds[metric_name]:
            if point.value >= threshold:
                alert, created = _create_predictive_alert(
                    product=product,
                    alert_type=PredictiveAlert.TYPE_ANOMALY,
                    severity=severity,
                    title=f"Anomalie detectee sur {metric_name}",
                    description=f"La valeur {point.value}{point.unit} depasse le seuil defini pour {metric_name}.",
                    metric_name=metric_name,
                    metric_value=point.value,
                    predicted_failure_at=now + timedelta(days=7 if severity == PredictiveAlert.SEVERITY_CRITICAL else 21),
                    recommended_action="Planifier une verification technique et reserver les pieces critiques.",
                )
                if created:
                    alerts_created.append(alert)
                    severity_penalty += 25 if severity == PredictiveAlert.SEVERITY_CRITICAL else 15
                break

    recurring_breakdowns = product.tickets.filter(
        category=Ticket.CATEGORY_BREAKDOWN,
        created_at__gte=now - timedelta(days=90),
    ).count()
    if recurring_breakdowns >= 2:
        alert, created = _create_predictive_alert(
            product=product,
            alert_type=PredictiveAlert.TYPE_REPEAT_FAILURE,
            severity=PredictiveAlert.SEVERITY_HIGH,
            title="Pannes recurrentes detectees",
            description="Le produit a enregistre plusieurs incidents similaires sur les 90 derniers jours.",
            recommended_action="Declencher une maintenance preventive approfondie et envisager une mise a niveau.",
            predicted_failure_at=now + timedelta(days=14),
        )
        if created:
            alerts_created.append(alert)
            severity_penalty += 20

    if product.warranty_end:
        days_to_warranty_end = (product.warranty_end - timezone.localdate()).days
        if 0 <= days_to_warranty_end <= 30:
            alert, created = _create_predictive_alert(
                product=product,
                alert_type=PredictiveAlert.TYPE_WARRANTY,
                severity=PredictiveAlert.SEVERITY_MEDIUM,
                title="Garantie proche de l'expiration",
                description="La garantie du produit expire prochainement.",
                recommended_action="Contacter le client pour une extension de garantie ou un contrat de maintenance.",
                predicted_failure_at=now + timedelta(days=days_to_warranty_end),
            )
            if created:
                alerts_created.append(alert)
                severity_penalty += 10

    openai_data = None
    if LLM_CLIENT.enabled:
        system_prompt = (
            "You are an Afrilux predictive maintenance analyst. "
            "Return valid JSON only with keys: summary, health_score, alerts. "
            "Each alert must include title, severity, description, recommended_action, metric_name, metric_value, days_to_failure."
        )
        user_prompt = (
            "Analyse this equipment context and propose predictive maintenance alerts.\n"
            f"{json.dumps(_product_context(product), ensure_ascii=False)}"
        )
        openai_data = _parse_completion_json(LLM_CLIENT.complete_json(system_prompt, user_prompt))

    if openai_data:
        proposed_health_score = openai_data.get("health_score")
        if proposed_health_score is not None:
            try:
                severity_penalty = max(0, 100 - int(proposed_health_score))
            except (TypeError, ValueError):
                pass

        for proposed in openai_data.get("alerts", [])[:5]:
            severity = proposed.get("severity", PredictiveAlert.SEVERITY_MEDIUM)
            title = proposed.get("title") or "Alerte predictive generee par IA"
            description = proposed.get("description") or openai_data.get("summary") or "Signal predictif detecte."
            recommended_action = proposed.get("recommended_action", "")
            metric_name = proposed.get("metric_name", "")
            metric_value = proposed.get("metric_value")
            days_to_failure = proposed.get("days_to_failure")
            predicted_failure_at = None
            try:
                if days_to_failure is not None:
                    predicted_failure_at = now + timedelta(days=int(days_to_failure))
            except (TypeError, ValueError):
                predicted_failure_at = None

            alert, created = _create_predictive_alert(
                product=product,
                alert_type=PredictiveAlert.TYPE_ANOMALY if metric_name else PredictiveAlert.TYPE_MAINTENANCE,
                severity=severity,
                title=title,
                description=description,
                recommended_action=recommended_action,
                metric_name=metric_name,
                metric_value=_coerce_decimal(metric_value, "0.00") if metric_value is not None else None,
                predicted_failure_at=predicted_failure_at,
            )
            if created:
                alerts_created.append(alert)

    product.health_score = max(0, 100 - severity_penalty)
    product.save(update_fields=["health_score", "updated_at"])

    preventive_ticket = None
    severe_alert_exists = any(
        alert.severity in {PredictiveAlert.SEVERITY_HIGH, PredictiveAlert.SEVERITY_CRITICAL} for alert in alerts_created
    )
    if severe_alert_exists:
        preventive_ticket = product.tickets.filter(
            category=Ticket.CATEGORY_MAINTENANCE,
            status__in=OPEN_TICKET_STATUSES,
        ).first()
        if preventive_ticket is None:
            preventive_ticket = Ticket.objects.create(
                client=product.client,
                product=product,
                assigned_agent=select_least_loaded_agent(product.organization),
                title=f"Maintenance preventive recommandee - {product.name}",
                description="Ticket genere automatiquement suite a une analyse predictive des donnees equipement.",
                category=Ticket.CATEGORY_MAINTENANCE,
                channel=Ticket.CHANNEL_WEB,
                status=Ticket.STATUS_NEW,
                priority=Ticket.PRIORITY_HIGH,
                sla_deadline=now + timedelta(days=2),
            )

    for alert in alerts_created:
        if preventive_ticket and not alert.ticket_id:
            alert.ticket = preventive_ticket
            alert.save(update_fields=["ticket", "updated_at"])

    ai_log = AIActionLog.objects.create(
        product=product,
        ticket=preventive_ticket,
        action_type=AIActionLog.ACTION_PREDICTIVE_ANALYSIS,
        status=AIActionLog.STATUS_EXECUTED,
        confidence=Decimal("0.88") if not openai_data else _clamp_confidence("0.90"),
        rationale="Analyse predictive calculee a partir des telemetries recentes, de l'historique et d'OpenAI si configure.",
        input_snapshot={"product_id": product.id, "telemetry_points": len(latest_telemetry)},
        output_snapshot={
            "alerts_created": [alert.id for alert in alerts_created],
            "preventive_ticket": preventive_ticket.reference if preventive_ticket else None,
            "health_score": product.health_score,
            "llm_used": bool(openai_data),
            "llm_output": openai_data or {},
        },
        approved_by=approved_by,
    )

    for manager in manager_queryset_for_organization(product.organization):
        if alerts_created:
            create_external_channel_notifications(
                recipient=manager,
                ticket=preventive_ticket,
                event_type="predictive_alert",
                subject=f"Alertes predictives sur {product.serial_number}",
                message=f"{len(alerts_created)} alerte(s) predictive(s) ont ete detectee(s) sur le produit {product.name}.",
            )

    log_audit_event(
        actor=approved_by,
        actor_type=AuditLog.ACTOR_AI,
        action="predictive_analysis",
        instance=product,
        details={
            "alerts_created": [alert.id for alert in alerts_created],
            "preventive_ticket": preventive_ticket.reference if preventive_ticket else None,
            "ai_action_id": ai_log.id,
        },
    )

    return {
        "product_id": product.id,
        "product_name": product.name,
        "health_score": product.health_score,
        "alerts_created": [
            {
                "id": alert.id,
                "title": alert.title,
                "severity": alert.severity,
                "ticket_reference": alert.ticket.reference if alert.ticket else None,
            }
            for alert in alerts_created
        ],
        "preventive_ticket_reference": preventive_ticket.reference if preventive_ticket else None,
        "ai_action_id": ai_log.id,
    }


def credit_account_for_ticket(
    ticket,
    *,
    amount,
    actor=None,
    reason="Credit SAV",
    note="",
    currency="XAF",
    external_reference="",
):
    credited_amount = _format_money(amount)
    if credited_amount <= Decimal("0.00"):
        raise ValueError("Le montant du credit doit etre strictement positif.")

    normalized_currency = (currency or "XAF").strip().upper()[:10] or "XAF"
    resolved_actor = actor
    if resolved_actor is None or not getattr(resolved_actor, "is_authenticated", False):
        resolved_actor = ticket.assigned_agent or manager_queryset_for_organization(ticket.organization).first()

    credit = AccountCredit.objects.create(
        ticket=ticket,
        client=ticket.client,
        executed_by=resolved_actor,
        amount=credited_amount,
        currency=normalized_currency,
        reason=(reason or "Credit SAV").strip()[:255] or "Credit SAV",
        note=(note or "").strip(),
        external_reference=(external_reference or "").strip()[:120],
        status=AccountCredit.STATUS_EXECUTED,
        executed_at=timezone.now(),
    )

    message_text = (
        f"Un credit de {credit.amount} {credit.currency} a ete applique sur votre compte. Raison: {credit.reason}."
    )
    if credit.note:
        message_text = f"{message_text} {credit.note}"

    message = None
    if resolved_actor is not None:
        message = Message.objects.create(
            ticket=ticket,
            sender=resolved_actor,
            message_type=Message.TYPE_PUBLIC,
            channel=Message.CHANNEL_PORTAL,
            direction=Message.DIRECTION_OUTBOUND,
            content=message_text,
            sentiment_score=calculate_sentiment(message_text),
        )
        if ticket.first_response_at is None:
            ticket.first_response_at = timezone.now()
            ticket.save(update_fields=["first_response_at", "updated_at"])

    notifications = create_external_channel_notifications(
        recipient=ticket.client,
        subject=f"Credit compte {ticket.reference}",
        message=message_text,
        event_type="account_credit",
        ticket=ticket,
    )

    execution = WorkflowExecution.objects.create(
        ticket=ticket,
        status=WorkflowExecution.STATUS_SUCCESS,
        trigger_event="account_credit",
        result={
            "credit_id": credit.id,
            "amount": str(credit.amount),
            "currency": credit.currency,
            "reason": credit.reason,
            "notification_ids": [item.id for item in notifications],
            "message_id": message.id if message else None,
        },
    )
    log_audit_event(
        actor=resolved_actor or actor,
        action="account_credit_executed",
        instance=credit,
        details={"ticket_reference": ticket.reference, "workflow_execution_id": execution.id},
    )

    return {
        "credit": credit,
        "message": message,
        "notifications": notifications,
        "workflow_execution": execution,
    }


def conditions_match_ticket(ticket, conditions, sentiment_score):
    if not conditions:
        return True

    if "priority" in conditions and ticket.priority != conditions["priority"]:
        return False
    if "status" in conditions and ticket.status != conditions["status"]:
        return False
    if "category" in conditions and ticket.category != conditions["category"]:
        return False
    if "overdue" in conditions and ticket.is_overdue != conditions["overdue"]:
        return False
    if "has_product" in conditions and bool(ticket.product_id) != conditions["has_product"]:
        return False
    if "sentiment_below" in conditions and sentiment_score >= Decimal(str(conditions["sentiment_below"])):
        return False

    return True


def execute_rule_action(ticket, action, actor=None):
    if isinstance(action, str):
        action = {"type": action}

    action_type = action.get("type")
    result = {"type": action_type}

    if action_type == "assign_least_loaded_agent":
        agent = select_least_loaded_agent(ticket.organization)
        if agent:
            ticket.assigned_agent = agent
            if ticket.status == Ticket.STATUS_NEW:
                ticket.status = Ticket.STATUS_ASSIGNED
                ticket.save(update_fields=["assigned_agent", "status", "updated_at"])
            else:
                ticket.save(update_fields=["assigned_agent", "updated_at"])
            ensure_assignment_intervention(ticket, actor=actor, note="Affectation automatique du moteur de workflow.")
            result["assigned_agent"] = str(agent)
        return result

    if action_type == "set_priority":
        new_priority = action.get("value", Ticket.PRIORITY_HIGH)
        ticket.priority = new_priority
        ticket.save(update_fields=["priority", "updated_at"])
        result["priority"] = new_priority
        return result

    if action_type == "change_status":
        new_status = action.get("value", Ticket.STATUS_ASSIGNED)
        ticket.status = new_status
        ticket.save(update_fields=["status", "updated_at"])
        result["status"] = new_status
        return result

    if action_type == "notify_manager":
        created_notifications = []
        for manager in manager_queryset_for_organization(ticket.organization):
            notification = create_notification(
                recipient=manager,
                ticket=ticket,
                channel=Notification.CHANNEL_IN_APP,
                event_type="workflow_notification",
                subject=f"Escalade ticket {ticket.reference}",
                message=f"Le workflow a signale le ticket '{ticket.title}' comme prioritaire.",
            )
            created_notifications.append(notification.id)
        result["notifications"] = created_notifications
        return result

    if action_type == "create_offer_recommendations":
        offers = generate_offer_recommendations(client=ticket.client, ticket=ticket, product=ticket.product, persist=True)
        result["offers"] = [item["offer"].id for item in offers]
        return result

    if action_type == "schedule_ar_session":
        session = SupportSession.objects.filter(
            ticket=ticket,
            status__in=[SupportSession.STATUS_SCHEDULED, SupportSession.STATUS_LIVE],
        ).first()
        if not session:
            session = SupportSession.objects.create(
                ticket=ticket,
                client=ticket.client,
                agent=ticket.assigned_agent or select_least_loaded_agent(ticket.organization),
                session_type=SupportSession.TYPE_AR,
                status=SupportSession.STATUS_SCHEDULED,
                meeting_link="https://support.afrilux.local/ar-session",
                scheduled_for=timezone.now() + timedelta(hours=1),
                annotations_summary="Session AR creee automatiquement par le moteur de workflow.",
            )
        result["support_session"] = session.id
        return result

    if action_type == "credit_account":
        credit_payload = credit_account_for_ticket(
            ticket,
            amount=action.get("amount", "0"),
            actor=actor,
            reason=action.get("reason", "Credit automatique SAV"),
            note=action.get("note", ""),
            currency=action.get("currency", "XAF"),
            external_reference=action.get("external_reference", ""),
        )
        result["credit_id"] = credit_payload["credit"].id
        result["amount"] = str(credit_payload["credit"].amount)
        result["currency"] = credit_payload["credit"].currency
        return result

    result["ignored"] = True
    return result


def run_automation_rules_for_ticket(ticket, actor=None, trigger_event=AutomationRule.TRIGGER_MANUAL):
    full_text = " ".join([ticket.title, ticket.description] + list(ticket.messages.values_list("content", flat=True)))
    sentiment_score = calculate_sentiment(full_text)
    rules = (
        AutomationRule.objects.filter(is_active=True, trigger_event=trigger_event)
        .filter(Q(organization=ticket.organization) | Q(organization__isnull=True))
        .order_by("priority")
    )

    execution_results = []

    if not rules.exists():
        builtin_actions = []
        if ticket.priority == Ticket.PRIORITY_CRITICAL and not ticket.assigned_agent:
            builtin_actions.append({"type": "assign_least_loaded_agent"})
        if ticket.priority in {Ticket.PRIORITY_HIGH, Ticket.PRIORITY_CRITICAL} or ticket.is_overdue:
            builtin_actions.append({"type": "notify_manager"})
        if sentiment_score <= Decimal("-0.50") and ticket.category in {
            Ticket.CATEGORY_BREAKDOWN,
            Ticket.CATEGORY_INSTALLATION,
        }:
            builtin_actions.append({"type": "schedule_ar_session"})

        if not builtin_actions:
            execution = WorkflowExecution.objects.create(
                ticket=ticket,
                status=WorkflowExecution.STATUS_SKIPPED,
                trigger_event=trigger_event,
                result={"reason": "no_rule_matched"},
            )
            return {"executions": [execution.id], "results": [execution.result]}

        action_results = [execute_rule_action(ticket, action, actor=actor) for action in builtin_actions]
        execution = WorkflowExecution.objects.create(
            ticket=ticket,
            status=WorkflowExecution.STATUS_SUCCESS,
            trigger_event=trigger_event,
            result={"builtin": True, "actions": action_results},
        )
        log_audit_event(
            actor=actor,
            action="automation_executed",
            instance=ticket,
            details={"workflow_execution_id": execution.id, "builtin": True},
        )
        return {"executions": [execution.id], "results": action_results}

    for rule in rules:
        if not conditions_match_ticket(ticket, rule.conditions, sentiment_score):
            execution = WorkflowExecution.objects.create(
                rule=rule,
                ticket=ticket,
                status=WorkflowExecution.STATUS_SKIPPED,
                trigger_event=trigger_event,
                result={"reason": "conditions_not_met"},
            )
            execution_results.append({"execution_id": execution.id, "result": execution.result})
            continue

        action_results = [execute_rule_action(ticket, action, actor=actor) for action in rule.actions]
        execution = WorkflowExecution.objects.create(
            rule=rule,
            ticket=ticket,
            status=WorkflowExecution.STATUS_SUCCESS,
            trigger_event=trigger_event,
            result={"actions": action_results},
        )
        execution_results.append({"execution_id": execution.id, "result": action_results})
        log_audit_event(
            actor=actor,
            action="automation_rule_executed",
            instance=ticket,
            details={"workflow_execution_id": execution.id, "rule_id": rule.id},
        )

    return {
        "executions": [item["execution_id"] for item in execution_results],
        "results": [item["result"] for item in execution_results],
    }


def notify_ticket_status_change(ticket, previous_status, *, actor=None):
    if not previous_status or previous_status == ticket.status:
        return []

    notifications = []
    notifications.extend(
        create_external_channel_notifications(
            recipient=ticket.client,
            ticket=ticket,
            event_type="ticket_status_update",
            subject=f"Mise a jour ticket {ticket.reference}",
            message=f"Le statut de votre ticket est passe de '{previous_status}' a '{ticket.status}'.",
        )
    )

    if ticket.status == Ticket.STATUS_RESOLVED:
        for manager in manager_queryset_for_organization(ticket.organization):
            notifications.extend(
                create_external_channel_notifications(
                    recipient=manager,
                    ticket=ticket,
                    event_type="ticket_resolved",
                    subject=f"Ticket resolu {ticket.reference}",
                    message=f"Le ticket '{ticket.title}' a ete resolu.",
                )
            )
    if previous_status in {Ticket.STATUS_RESOLVED, Ticket.STATUS_CLOSED} and ticket.status == Ticket.STATUS_NEW:
        recipients = manager_queryset_for_organization(ticket.organization)
        if ticket.assigned_agent_id:
            recipients = list(recipients) + [ticket.assigned_agent]
        for recipient in {item.id: item for item in recipients}.values():
            notifications.extend(
                create_external_channel_notifications(
                    recipient=recipient,
                    ticket=ticket,
                    event_type="ticket_reopened",
                    subject=f"Ticket rouvert {ticket.reference}",
                    message=f"Le ticket '{ticket.title}' a ete rouvert et requiert une reprise en charge.",
                )
            )

    log_audit_event(
        actor=actor,
        action="ticket_status_notification",
        instance=ticket,
        details={"from": previous_status, "to": ticket.status, "notifications": [item.id for item in notifications]},
    )
    return notifications


def _notification_recently_sent(ticket, recipient, event_type, since):
    return Notification.objects.filter(
        ticket=ticket,
        recipient=recipient,
        event_type=event_type,
        created_at__gte=since,
    ).exists()


def dispatch_sla_operational_notifications(*, organization=None, now=None):
    now = now or timezone.now()
    queryset = Ticket.objects.select_related("assigned_agent", "client", "organization").filter(status__in=OPEN_TICKET_STATUSES)
    if organization is not None:
        queryset = queryset.filter(organization=organization)

    sent = {"unassigned_30m": 0, "new_1h": 0, "sla_due_soon": 0, "sla_overdue": 0}

    for ticket in queryset:
        managers = list(manager_queryset_for_organization(ticket.organization))
        recent_since = now - timedelta(hours=6)

        if ticket.assigned_agent_id is None and ticket.created_at <= now - timedelta(minutes=30):
            for manager in managers:
                if _notification_recently_sent(ticket, manager, "ticket_unassigned_30m", recent_since):
                    continue
                create_external_channel_notifications(
                    recipient=manager,
                    ticket=ticket,
                    event_type="ticket_unassigned_30m",
                    subject=f"Ticket non assigne {ticket.reference}",
                    message=f"Le ticket '{ticket.title}' n'est toujours pas assigne 30 minutes apres sa creation.",
                )
                sent["unassigned_30m"] += 1

        if ticket.status == Ticket.STATUS_NEW and ticket.created_at <= now - timedelta(hours=1):
            for manager in managers:
                if _notification_recently_sent(ticket, manager, "ticket_new_1h", recent_since):
                    continue
                create_external_channel_notifications(
                    recipient=manager,
                    ticket=ticket,
                    event_type="ticket_new_1h",
                    subject=f"Ticket nouveau >1h {ticket.reference}",
                    message=f"Le ticket '{ticket.title}' est encore au statut Nouveau depuis plus d'une heure.",
                )
                sent["new_1h"] += 1

        if ticket.sla_deadline and now <= ticket.sla_deadline <= now + timedelta(hours=2):
            recipients = managers[:]
            if ticket.assigned_agent_id:
                recipients.append(ticket.assigned_agent)
            for recipient in {item.id: item for item in recipients}.values():
                if _notification_recently_sent(ticket, recipient, "sla_due_soon", now - timedelta(hours=2)):
                    continue
                create_external_channel_notifications(
                    recipient=recipient,
                    ticket=ticket,
                    event_type="sla_due_soon",
                    subject=f"SLA proche {ticket.reference}",
                    message=f"Le ticket '{ticket.title}' arrive a echeance SLA dans moins de 2 heures.",
                )
                sent["sla_due_soon"] += 1

        if ticket.is_overdue:
            for manager in managers:
                if _notification_recently_sent(ticket, manager, "sla_overdue", recent_since):
                    continue
                create_external_channel_notifications(
                    recipient=manager,
                    ticket=ticket,
                    event_type="sla_overdue",
                    subject=f"SLA depasse {ticket.reference}",
                    message=f"Le ticket '{ticket.title}' est maintenant en depassement de SLA.",
                )
                sent["sla_overdue"] += 1

    return sent


def auto_close_resolved_tickets(*, organization=None, now=None):
    now = now or timezone.now()
    queryset = Ticket.objects.select_related("client", "organization").filter(
        status=Ticket.STATUS_RESOLVED,
        resolved_at__isnull=False,
        resolved_at__lte=now - timedelta(hours=72),
    )
    if organization is not None:
        queryset = queryset.filter(organization=organization)

    closed_references = []
    for ticket in queryset:
        previous_status = ticket.status
        ticket.status = Ticket.STATUS_CLOSED
        ticket.closed_at = now
        ticket.save(update_fields=["status", "closed_at", "updated_at"])
        Message.objects.create(
            ticket=ticket,
            sender=ticket.assigned_agent or ticket.client,
            message_type=Message.TYPE_PUBLIC,
            channel=Message.CHANNEL_PORTAL,
            direction=Message.DIRECTION_OUTBOUND,
            content="Le ticket a ete ferme automatiquement 72h apres resolution sans contestation client.",
            sentiment_score=calculate_sentiment("Le ticket a ete ferme automatiquement 72h apres resolution."),
        )
        notify_ticket_status_change(ticket, previous_status, actor=ticket.assigned_agent)
        log_audit_event(
            actor=None,
            actor_type=AuditLog.ACTOR_SYSTEM,
            action="ticket_auto_closed_72h",
            instance=ticket,
            details={"resolved_at": ticket.resolved_at.isoformat() if ticket.resolved_at else ""},
        )
        closed_references.append(ticket.reference)
    return closed_references


def _due_report_types(now):
    due_types = []
    if now.hour >= 7:
        due_types.append("journalier")
    if now.weekday() == 0 and now.hour >= 8:
        due_types.append("hebdomadaire")
    if now.day == 1 and now.hour >= 8:
        due_types.append("mensuel")
    return due_types


def dispatch_due_reports(*, organization=None, now=None, dry_run=False, report_types=None):
    from .reporting import REPORT_DAILY, REPORT_MONTHLY, REPORT_WEEKLY, build_report, export_report_pdf

    now = timezone.localtime(now or timezone.now())
    report_types = report_types or _due_report_types(now)
    if not report_types:
        return []

    if organization is None:
        organizations = Organization.objects.filter(is_active=True).order_by("name")
    else:
        organizations = [organization]

    results = []
    for org in organizations:
        actor = (
            User.objects.filter(organization=org, is_active=True)
            .filter(Q(role__in=User.REPORTING_ROLES + User.TECHNICIAN_SPACE_ROLES) | Q(is_superuser=True))
            .order_by("role", "id")
            .first()
        )
        if actor is None:
            results.append({"organization": org.slug, "status": "skipped_no_actor"})
            continue

        recipients = parse_reporting_recipients(org)
        if not recipients:
            results.append({"organization": org.slug, "status": "skipped_no_recipients"})
            continue

        sent_to = ", ".join(recipients)
        for report_type in report_types:
            report = build_report(report_type, actor, anchor_date=now.date())
            if GeneratedReport.objects.filter(
                organization=org,
                report_type=report_type,
                export_format=GeneratedReport.FORMAT_PDF,
                period_label=report.get("period_label", ""),
                sent_to=sent_to,
            ).exists():
                results.append({"organization": org.slug, "report_type": report_type, "status": "already_sent"})
                continue

            filename = f"{report_type}-{slugify(report.get('period_label', 'periode'))}.pdf"
            pdf_content = export_report_pdf(report)
            if dry_run:
                results.append({"organization": org.slug, "report_type": report_type, "status": "dry_run"})
                continue
            send_report_to_recipients(
                report=report,
                report_type=report_type,
                recipients=recipients,
                filename=filename,
                pdf_content=pdf_content,
            )
            archive_generated_report(
                organization=org,
                report=report,
                report_type=report_type,
                export_format=GeneratedReport.FORMAT_PDF,
                generated_by=actor,
                filename=filename,
                content=pdf_content,
                sent_to=sent_to,
            )
            results.append({"organization": org.slug, "report_type": report_type, "status": "sent"})
    return results


def answer_bi_question(question, user):
    lowered = (question or "").lower()
    tickets = scope_ticket_queryset(Ticket.objects.all(), user)
    products = scope_product_queryset(Product.objects.all(), user)
    alerts = scope_predictive_alert_queryset(PredictiveAlert.objects.all(), user)
    average_first_response_hours = compute_average_first_response_hours(tickets)
    average_resolution_hours = compute_average_resolution_hours(tickets)
    top_agents = compute_agent_performance_rows(tickets)
    base_result = None

    if "critique" in lowered:
        open_critical = tickets.filter(priority=Ticket.PRIORITY_CRITICAL, status__in=OPEN_TICKET_STATUSES).count()
        overdue_critical = tickets.filter(
            priority=Ticket.PRIORITY_CRITICAL,
            status__in=OPEN_TICKET_STATUSES,
            sla_deadline__lt=timezone.now(),
        ).count()
        base_result = {
            "matched_intent": "critical_tickets",
            "answer": (
                f"Il y a {open_critical} ticket(s) critique(s) ouvert(s), dont {overdue_critical} en depassement de SLA."
            ),
            "data": {
                "open_critical_tickets": open_critical,
                "overdue_critical_tickets": overdue_critical,
            },
        }

    elif "retard" in lowered or "sla" in lowered:
        overdue_count = tickets.filter(status__in=OPEN_TICKET_STATUSES, sla_deadline__lt=timezone.now()).count()
        total_open = tickets.filter(status__in=OPEN_TICKET_STATUSES).count()
        base_result = {
            "matched_intent": "sla",
            "answer": f"{overdue_count} ticket(s) ouvert(s) sur {total_open} sont actuellement hors SLA.",
            "data": {"overdue_tickets": overdue_count, "open_tickets": total_open},
        }

    elif "garantie" in lowered:
        under_warranty = products.filter(warranty_end__gte=timezone.localdate()).count()
        expiring = products.filter(
            warranty_end__gte=timezone.localdate(),
            warranty_end__lte=timezone.localdate() + timedelta(days=30),
        ).count()
        base_result = {
            "matched_intent": "warranty",
            "answer": (
                f"{under_warranty} produit(s) sont encore sous garantie, dont {expiring} avec une expiration dans 30 jours."
            ),
            "data": {"under_warranty": under_warranty, "warranty_expiring_soon": expiring},
        }

    elif "maintenance" in lowered or "entretien" in lowered:
        maintenance_total = tickets.filter(category=Ticket.CATEGORY_MAINTENANCE).count()
        base_result = {
            "matched_intent": "maintenance",
            "answer": f"{maintenance_total} ticket(s) de maintenance sont enregistres dans le perimetre courant.",
            "data": {
                "maintenance_total": maintenance_total,
            },
        }

    elif "bug" in lowered or "erreur" in lowered:
        bug_total = tickets.filter(category=Ticket.CATEGORY_BUG).count()
        base_result = {
            "matched_intent": "bugs",
            "answer": f"{bug_total} ticket(s) sont classes comme bug.",
            "data": {"bug_total": bug_total},
        }

    elif "resolution" in lowered or "resolu" in lowered:
        base_result = {
            "matched_intent": "resolution_time",
            "answer": (
                f"Le temps moyen de resolution est de {average_resolution_hours} heure(s)."
                if average_resolution_hours is not None
                else "Aucun historique clos ne permet encore de calculer un temps moyen de resolution."
            ),
            "data": {
                "average_resolution_hours": float(average_resolution_hours) if average_resolution_hours is not None else None,
            },
        }

    elif "premiere reponse" in lowered or "temps de reponse" in lowered or "temps moyen de reponse" in lowered:
        base_result = {
            "matched_intent": "first_response_time",
            "answer": (
                f"Le temps moyen de premiere reponse est de {average_first_response_hours} heure(s)."
                if average_first_response_hours is not None
                else "Aucun historique de premiere reponse n'est encore disponible."
            ),
            "data": {
                "average_first_response_hours": float(average_first_response_hours)
                if average_first_response_hours is not None
                else None,
            },
        }

    elif "agent" in lowered or "performant" in lowered:
        highlights = [
            f"{row['agent_name']}: {row['resolved_tickets']} resolu(s), {row['open_tickets']} ouvert(s)"
            for row in top_agents[:3]
        ]
        base_result = {
            "matched_intent": "top_agents",
            "answer": (
                "Les agents les plus performants ont ete identifies."
                if top_agents
                else "Aucun agent ne dispose encore d'assez d'historique pour etre compare."
            ),
            "data": {
                "top_agents": [
                    {
                        **row,
                        "average_resolution_hours": float(row["average_resolution_hours"])
                        if row["average_resolution_hours"] is not None
                        else None,
                    }
                    for row in top_agents
                ]
            },
        }
        if highlights:
            base_result["highlights"] = highlights

    elif "panne" in lowered or "recurrente" in lowered:
        recurrent_products = list(
            tickets.filter(category=Ticket.CATEGORY_BREAKDOWN)
            .values("product__name", "product__serial_number")
            .annotate(total=Count("id"))
            .order_by("-total")[:5]
        )
        base_result = {
            "matched_intent": "recurrent_failures",
            "answer": "Les produits les plus exposes aux pannes recurrentes ont ete identifies.",
            "data": {"top_recurrent_products": recurrent_products},
        }

    elif "predictif" in lowered or "alerte" in lowered:
        open_alerts = alerts.filter(status__in=[PredictiveAlert.STATUS_OPEN, PredictiveAlert.STATUS_IN_PROGRESS]).count()
        critical_alerts = alerts.filter(
            status__in=[PredictiveAlert.STATUS_OPEN, PredictiveAlert.STATUS_IN_PROGRESS],
            severity=PredictiveAlert.SEVERITY_CRITICAL,
        ).count()
        base_result = {
            "matched_intent": "predictive_alerts",
            "answer": f"{open_alerts} alerte(s) predictive(s) sont ouvertes, dont {critical_alerts} critique(s).",
            "data": {"open_alerts": open_alerts, "critical_alerts": critical_alerts},
        }

    if base_result is None:
        total_tickets = tickets.count()
        total_products = products.count()
        total_alerts = alerts.count()
        base_result = {
            "matched_intent": "general_summary",
            "answer": (
                f"Le perimetre courant contient {total_tickets} ticket(s), {total_products} produit(s) et {total_alerts} alerte(s) predictive(s)."
            ),
            "data": {
                "tickets_total": total_tickets,
                "products_total": total_products,
                "alerts_total": total_alerts,
                "maintenance_total": tickets.filter(category=Ticket.CATEGORY_MAINTENANCE).count(),
                "bug_total": tickets.filter(category=Ticket.CATEGORY_BUG).count(),
                "average_resolution_hours": float(average_resolution_hours) if average_resolution_hours is not None else None,
            },
        }

    if LLM_CLIENT.enabled:
        system_prompt = (
            "You are an Afrilux SAV BI analyst. "
            "Return valid JSON only with keys: matched_intent, answer, highlights. "
            "Use the supplied numeric facts and do not invent values."
        )
        user_prompt = (
            f"User question: {question}\n"
            f"Baseline answer: {json.dumps(base_result, ensure_ascii=False)}"
        )
        openai_data = _parse_completion_json(LLM_CLIENT.complete_json(system_prompt, user_prompt, max_output_tokens=500))
        if openai_data:
            base_result["matched_intent"] = openai_data.get("matched_intent") or base_result["matched_intent"]
            base_result["answer"] = openai_data.get("answer") or base_result["answer"]
            if openai_data.get("highlights"):
                base_result["highlights"] = openai_data["highlights"]

    return base_result
