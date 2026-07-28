import re
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from ..models import (
    AuditLog,
    EquipmentCategory,
    SlaRule,
    Ticket,
    User,
)
from .constants import (
    DEFAULT_EQUIPMENT_CATEGORIES,
    RESOLUTION_SLA_HOURS,
    RESPONSE_SLA_MINUTES,
)
from .audit import log_audit_event


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
