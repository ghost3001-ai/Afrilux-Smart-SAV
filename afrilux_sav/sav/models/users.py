from decimal import Decimal

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models import Sum
from django.utils import timezone

from .base import TimeStampedModel, _generate_unique_slug
from .organizations import Agency, Organization


class User(AbstractUser):
    LANGUAGE_FRENCH = "fr"
    LANGUAGE_ENGLISH = "en"

    LANGUAGE_CHOICES = (
        (LANGUAGE_FRENCH, "Francais"),
    )

    ROLE_CLIENT = "client"
    ROLE_SUPPORT = "support"
    ROLE_TECHNICIAN = "technician"
    ROLE_CHIEF_TECHNICIAN = "chief_technician"
    ROLE_EXPERT = "expert"
    ROLE_CFAO_MANAGER = "cfao_manager"
    ROLE_CFAO_WORKS = "cfao_works"
    ROLE_HVAC_MANAGER = "hvac_manager"
    ROLE_SOFTWARE_OWNER = "software_owner"
    ROLE_SUPERVISOR = "supervisor"
    ROLE_QA = "qa"
    ROLE_DISPATCHER = "dispatcher"
    ROLE_FIELD_TECHNICIAN = "field_technician"  # legacy value preserved for compatibility/migrations
    ROLE_VIP_SUPPORT = "vip_support"
    ROLE_SYSTEM_BOT = "system_bot"
    ROLE_HEAD_SAV = "head_sav"
    ROLE_AUDITOR = "auditor"
    ROLE_ADMIN = "admin"
    ROLE_AGENT = "agent"
    ROLE_MANAGER = "manager"

    ROLE_CHOICES = (
        (ROLE_ADMIN, "Administrateur"),
        (ROLE_HEAD_SAV, "Responsable SAV"),
        (ROLE_SUPPORT, "Agent assistance / centre d'appels"),
        (ROLE_CFAO_MANAGER, "Responsable CFAO / Responsable de Projet Technique CFAO"),
        (ROLE_CFAO_WORKS, "Conducteur de travaux CFAO"),
        (ROLE_HVAC_MANAGER, "Responsable Froid et climatisation / Responsable technique froid"),
        (ROLE_CHIEF_TECHNICIAN, "Chef Technicien Froid & Climatisation"),
        (ROLE_TECHNICIAN, "Technicien de maintenance"),
        (ROLE_CLIENT, "Client"),
        (ROLE_AUDITOR, "Auditeur / Direction"),
    )

    LEGACY_ROLE_CHOICES = (
        (ROLE_EXPERT, "Chef technicien / Expert (Niveau 3)"),
        (ROLE_SOFTWARE_OWNER, "Gestionnaire principal du logiciel"),
        (ROLE_SUPERVISOR, "Superviseur / Chef d'equipe"),
        (ROLE_QA, "Qualite / QA SAV"),
        (ROLE_DISPATCHER, "Planificateur / repartition"),
        (ROLE_VIP_SUPPORT, "Assistance VIP / Grands comptes"),
        (ROLE_SYSTEM_BOT, "Systeme automatique (IA / Bot)"),
        (ROLE_AGENT, "Agent support (legacy)"),
        (ROLE_MANAGER, "Responsable SAV (legacy)"),
    )

    SUPPORT_ROLE_ALIASES = (
        ROLE_SUPPORT,
        ROLE_AGENT,
        ROLE_DISPATCHER,
        ROLE_VIP_SUPPORT,
    )
    STANDARD_SUPPORT_ROLES = (
        ROLE_SUPPORT,
        ROLE_AGENT,
        ROLE_DISPATCHER,
    )
    SPECIAL_SUPPORT_ROLES = (
        ROLE_VIP_SUPPORT,
    )
    FRONTLINE_ROLES = (*SUPPORT_ROLE_ALIASES,)
    SUPERVISOR_ROLES = (
        ROLE_SUPERVISOR,
    )
    ESCALATION_TARGET_ROLES = (
        ROLE_CFAO_MANAGER,
        ROLE_CFAO_WORKS,
        ROLE_HVAC_MANAGER,
        ROLE_CHIEF_TECHNICIAN,
    )
    FIELD_TECHNICIAN_ROLES = (
        ROLE_TECHNICIAN,
    )
    TECHNICAL_ROLES = (
        *SUPERVISOR_ROLES,
        *ESCALATION_TARGET_ROLES,
        *FIELD_TECHNICIAN_ROLES,
    )
    SPECIALIST_ROLES = (
        *ESCALATION_TARGET_ROLES,
    )
    LEADERSHIP_ROLES = (
        ROLE_HEAD_SAV,
        ROLE_ADMIN,
        ROLE_MANAGER,
    )
    READ_ONLY_ROLES = (ROLE_AUDITOR,)
    BOT_ROLES = (
        ROLE_SYSTEM_BOT,
    )
    INTERNAL_ROLES = (
        *FRONTLINE_ROLES,
        *TECHNICAL_ROLES,
        *SPECIALIST_ROLES,
        *LEADERSHIP_ROLES,
        *BOT_ROLES,
    )
    MANAGER_ROLES = (
        ROLE_HEAD_SAV,
        ROLE_ADMIN,
        ROLE_MANAGER,
    )
    ASSIGNABLE_ROLES = (
        *FRONTLINE_ROLES,
        *SUPERVISOR_ROLES,
        *ESCALATION_TARGET_ROLES,
        *FIELD_TECHNICIAN_ROLES,
    )
    TECHNICIAN_SPACE_ROLES = (
        *ESCALATION_TARGET_ROLES,
        *FIELD_TECHNICIAN_ROLES,
    )
    REPORTING_ROLES = (
        *LEADERSHIP_ROLES,
        *READ_ONLY_ROLES,
        *SPECIALIST_ROLES,
    )
    OVERSIGHT_ROLES = (
        *LEADERSHIP_ROLES,
        *READ_ONLY_ROLES,
        *SPECIALIST_ROLES,
    )

    organization = models.ForeignKey(
        Organization,
        on_delete=models.SET_NULL,
        related_name="users",
        null=True,
        blank=True,
    )
    agency = models.ForeignKey(
        Agency,
        on_delete=models.SET_NULL,
        related_name="users",
        null=True,
        blank=True,
    )
    role = models.CharField("Fonction", max_length=20, choices=ROLE_CHOICES, default=ROLE_CLIENT)
    phone = models.CharField(max_length=20, blank=True)
    whatsapp_phone = models.CharField(max_length=30, blank=True)
    sms_phone = models.CharField(max_length=30, blank=True)
    preferred_language = models.CharField(max_length=8, choices=LANGUAGE_CHOICES, default=LANGUAGE_FRENCH)
    notification_email_enabled = models.BooleanField(default=True)
    notification_sms_enabled = models.BooleanField(default=True)
    notification_whatsapp_enabled = models.BooleanField(default=True)
    notification_push_enabled = models.BooleanField(default=True)
    notification_do_not_disturb_start = models.TimeField(null=True, blank=True)
    notification_do_not_disturb_end = models.TimeField(null=True, blank=True)
    notification_daily_limit = models.PositiveIntegerField(default=0, help_text="0 = illimite.")
    notification_min_interval_minutes = models.PositiveIntegerField(default=0, help_text="0 = pas de limite.")
    company_name = models.CharField(max_length=255, blank=True)
    is_verified = models.BooleanField(default=False)
    professional_email = models.EmailField(blank=True)
    profile_photo = models.FileField(upload_to="users/profile_photos/%Y/%m/%d/", blank=True)
    address = models.TextField(blank=True)
    internal_note = models.TextField(blank=True)
    sector = models.CharField(max_length=120, blank=True)
    tax_identifier = models.CharField(max_length=120, blank=True)
    client_type = models.CharField(
        max_length=20,
        choices=(
            ("enterprise", "Entreprise"),
            ("individual", "Particulier"),
            ("administration", "Administration"),
        ),
        default="enterprise",
        blank=True,
    )
    client_status = models.CharField(
        max_length=20,
        choices=(
            ("active", "Actif"),
            ("inactive", "Inactif"),
            ("prospect", "Prospect"),
        ),
        default="active",
        blank=True,
    )
    specialties = models.TextField(blank=True)
    primary_city = models.CharField(max_length=120, blank=True)
    primary_region = models.CharField(max_length=120, blank=True)
    weekly_availability = models.JSONField(default=dict, blank=True)
    technician_status = models.CharField(
        max_length=20,
        choices=(
            ("available", "Disponible"),
            ("on_site", "En intervention"),
            ("on_leave", "En conge"),
            ("unavailable", "Indisponible"),
        ),
        default="available",
        blank=True,
    )

    def __str__(self):
        full_name = self.get_full_name().strip()
        return full_name or self.username

    def save(self, *args, **kwargs):
        if self.agency_id and not self.organization_id:
            self.organization = self.agency.organization
        if self.role == self.ROLE_FIELD_TECHNICIAN:
            self.role = self.ROLE_TECHNICIAN
        if self.role == self.ROLE_EXPERT:
            self.role = self.ROLE_CHIEF_TECHNICIAN
        if self.role == self.ROLE_QA:
            self.role = self.ROLE_AUDITOR
        if self.role == self.ROLE_ADMIN and not self.is_staff:
            self.is_staff = True
        if (
            self.role == self.ROLE_CLIENT
            and self.client_type == "enterprise"
            and self.organization_id
            and not self.company_name
        ):
            self.company_name = self.organization.display_name
        super().save(*args, **kwargs)

    @property
    def is_ticket_assignment_eligible(self):
        if not self.is_active:
            return False
        return self.role in set(self.ASSIGNABLE_ROLES) and self.technician_status == "available"

    @property
    def has_support_role(self):
        return self.role in set(self.SUPPORT_ROLE_ALIASES)

    @property
    def is_ticket_escalation_target(self):
        return self.role in set(self.ESCALATION_TARGET_ROLES)

    @property
    def account_balance(self):
        from .financial import AccountCredit
        credits_total = (
            self.received_account_credits.filter(status=AccountCredit.STATUS_EXECUTED).aggregate(total=Sum("amount"))["total"]
            or Decimal("0.00")
        )
        transaction_total = Decimal("0.00")
        for item in self.financial_transactions.all():
            transaction_total += item.signed_amount
        return (credits_total + transaction_total).quantize(Decimal("0.01"))


class ClientContact(TimeStampedModel):
    organization = models.ForeignKey(
        Organization,
        on_delete=models.SET_NULL,
        related_name="client_contacts",
        null=True,
        blank=True,
    )
    client = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="contacts",
        limit_choices_to={"role": User.ROLE_CLIENT},
    )
    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150, blank=True)
    job_title = models.CharField(max_length=120, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    is_primary = models.BooleanField(default=False)
    note = models.TextField(blank=True)

    class Meta:
        ordering = ["-is_primary", "first_name", "last_name", "id"]

    def __str__(self):
        full_name = f"{self.first_name} {self.last_name}".strip()
        return full_name or self.email or self.phone or f"Contact {self.pk}"

    def save(self, *args, **kwargs):
        if self.client_id and self.client.organization_id:
            self.organization = self.client.organization
        super().save(*args, **kwargs)


class ClientSite(TimeStampedModel):
    organization = models.ForeignKey(
        Organization,
        on_delete=models.SET_NULL,
        related_name="client_sites",
        null=True,
        blank=True,
    )
    client = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="sites",
        limit_choices_to={"role": User.ROLE_CLIENT},
    )
    agency = models.ForeignKey(
        Agency,
        on_delete=models.SET_NULL,
        related_name="client_sites",
        null=True,
        blank=True,
    )
    name = models.CharField(max_length=180)
    code = models.SlugField(max_length=100, blank=True)
    address = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=120, blank=True)
    region = models.CharField(max_length=120, blank=True)
    gps_latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    gps_longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    is_primary = models.BooleanField(default=False)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["client__company_name", "client__username", "-is_primary", "name"]
        unique_together = [("client", "code")]

    def __str__(self):
        return f"{self.client} - {self.name}"

    def save(self, *args, **kwargs):
        if self.client_id and self.client.organization_id:
            self.organization = self.client.organization
        elif self.agency_id and self.agency.organization_id:
            self.organization = self.agency.organization
        if not self.code:
            self.code = _generate_unique_slug(self.__class__, self.name, self.pk, field_name="code")
        super().save(*args, **kwargs)
