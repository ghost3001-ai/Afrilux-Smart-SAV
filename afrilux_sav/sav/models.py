import uuid
from decimal import Decimal

from django.contrib.auth.models import AbstractUser
from django.db import IntegrityError, models, transaction
from django.db.models import Sum
from django.utils import timezone
from django.utils.text import slugify


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


def _generate_unique_slug(model_cls, value, instance_pk=None, field_name="slug"):
    base_slug = slugify(value) or uuid.uuid4().hex[:8]
    slug = base_slug
    suffix = 2
    queryset = model_cls.objects.all()
    if instance_pk:
        queryset = queryset.exclude(pk=instance_pk)
    while queryset.filter(**{field_name: slug}).exists():
        slug = f"{base_slug}-{suffix}"
        suffix += 1
    return slug


class Organization(TimeStampedModel):
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True, blank=True)
    brand_name = models.CharField(max_length=255, blank=True)
    portal_tagline = models.CharField(max_length=255, blank=True)
    primary_color = models.CharField(max_length=7, default="#D5671D")
    accent_color = models.CharField(max_length=7, default="#1C7A6A")
    support_email = models.EmailField(blank=True)
    support_phone = models.CharField(max_length=20, blank=True)
    headquarters_address = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=120, blank=True)
    country = models.CharField(max_length=120, blank=True)
    reporting_emails = models.TextField(blank=True, help_text="Liste d'emails separes par des virgules pour les rapports automatiques.")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.display_name

    @property
    def display_name(self):
        return self.brand_name or self.name

    @property
    def initials(self):
        words = [chunk for chunk in self.display_name.split() if chunk]
        if not words:
            return "SV"
        return "".join(word[0].upper() for word in words[:2])

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = _generate_unique_slug(self.__class__, self.display_name, self.pk)
        super().save(*args, **kwargs)


class User(AbstractUser):
    ROLE_CLIENT = "client"
    ROLE_SUPPORT = "support"
    ROLE_TECHNICIAN = "technician"
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
        (ROLE_CLIENT, "Client"),
        (ROLE_SUPPORT, "Agent support (Niveau 1 / Hotliner)"),
        (ROLE_TECHNICIAN, "Agent technique (Niveau 2)"),
        (ROLE_EXPERT, "Chef technicien / Expert (Niveau 3)"),
        (ROLE_CFAO_MANAGER, "Responsable CFAO / GTC & dessin technique"),
        (ROLE_CFAO_WORKS, "Conducteur de travaux CFAO"),
        (ROLE_HVAC_MANAGER, "Responsable froid & climatisation"),
        (ROLE_SOFTWARE_OWNER, "Gestionnaire principal du logiciel"),
        (ROLE_SUPERVISOR, "Superviseur / Team Leader"),
        (ROLE_QA, "Qualite / QA SAV"),
        (ROLE_DISPATCHER, "Planificateur / Dispatch"),
        (ROLE_VIP_SUPPORT, "Support VIP / Grands comptes"),
        (ROLE_SYSTEM_BOT, "Systeme automatique (IA / Bot)"),
        (ROLE_HEAD_SAV, "Responsable SAV"),
        (ROLE_AUDITOR, "Auditeur / Direction"),
        (ROLE_ADMIN, "Administrateur"),
        (ROLE_AGENT, "Agent support (legacy)"),
        (ROLE_MANAGER, "Responsable SAV (legacy)"),
    )

    SUPPORT_ROLE_ALIASES = (
        ROLE_SUPPORT,
        ROLE_SOFTWARE_OWNER,
        ROLE_SUPERVISOR,
        ROLE_DISPATCHER,
        ROLE_VIP_SUPPORT,
        ROLE_MANAGER,
        ROLE_HEAD_SAV,
        ROLE_AGENT,
    )
    STANDARD_SUPPORT_ROLES = (
        ROLE_SUPPORT,
        ROLE_AGENT,
    )
    SPECIAL_SUPPORT_ROLES = (
        ROLE_VIP_SUPPORT,
    )
    FRONTLINE_ROLES = (
        *SUPPORT_ROLE_ALIASES,
    )
    TECHNICAL_ROLES = (
        ROLE_TECHNICIAN,
        ROLE_EXPERT,
    )
    SPECIALIST_ROLES = (
        ROLE_CFAO_MANAGER,
        ROLE_CFAO_WORKS,
        ROLE_HVAC_MANAGER,
        ROLE_SOFTWARE_OWNER,
    )
    LEADERSHIP_ROLES = (
        ROLE_SUPERVISOR,
        ROLE_DISPATCHER,
        ROLE_HEAD_SAV,
        ROLE_ADMIN,
        ROLE_MANAGER,
    )
    READ_ONLY_ROLES = (
        ROLE_AUDITOR,
        ROLE_QA,
    )
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
        ROLE_SOFTWARE_OWNER,
        ROLE_SUPERVISOR,
        ROLE_HEAD_SAV,
        ROLE_ADMIN,
        ROLE_MANAGER,
    )
    ASSIGNABLE_ROLES = (
        *SUPPORT_ROLE_ALIASES,
        ROLE_TECHNICIAN,
    )
    TECHNICIAN_SPACE_ROLES = (
        ROLE_TECHNICIAN,
        ROLE_EXPERT,
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
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_CLIENT)
    phone = models.CharField(max_length=20, blank=True)
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
        if self.role == self.ROLE_FIELD_TECHNICIAN:
            self.role = self.ROLE_TECHNICIAN
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
        if self.role in set(self.SUPPORT_ROLE_ALIASES):
            return True
        return self.role == self.ROLE_TECHNICIAN and self.technician_status == "available"

    @property
    def has_support_role(self):
        return self.role in set(self.SUPPORT_ROLE_ALIASES)

    @property
    def is_ticket_escalation_target(self):
        return self.role in {
            self.ROLE_HEAD_SAV,
            self.ROLE_MANAGER,
            self.ROLE_ADMIN,
            self.ROLE_SUPERVISOR,
            self.ROLE_EXPERT,
            self.ROLE_CFAO_MANAGER,
            self.ROLE_CFAO_WORKS,
        }

    @property
    def account_balance(self):
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


class EquipmentCategory(TimeStampedModel):
    organization = models.ForeignKey(
        Organization,
        on_delete=models.SET_NULL,
        related_name="equipment_categories",
        null=True,
        blank=True,
    )
    name = models.CharField(max_length=120)
    code = models.SlugField(max_length=120, blank=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        unique_together = [("organization", "code")]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = _generate_unique_slug(self.__class__, self.name, self.pk, field_name="code")
        super().save(*args, **kwargs)


class FinancialTransaction(TimeStampedModel):
    TYPE_DEPOSIT = "deposit"
    TYPE_WITHDRAWAL = "withdrawal"
    TYPE_PAYMENT = "payment"
    TYPE_REFUND = "refund"
    TYPE_ADJUSTMENT = "adjustment"

    TYPE_CHOICES = (
        (TYPE_DEPOSIT, "Depot"),
        (TYPE_WITHDRAWAL, "Retrait"),
        (TYPE_PAYMENT, "Paiement"),
        (TYPE_REFUND, "Remboursement"),
        (TYPE_ADJUSTMENT, "Ajustement"),
    )

    SIDE_CREDIT = "credit"
    SIDE_DEBIT = "debit"

    SIDE_CHOICES = (
        (SIDE_CREDIT, "Credit"),
        (SIDE_DEBIT, "Debit"),
    )

    STATUS_PENDING = "pending"
    STATUS_COMPLETED = "completed"
    STATUS_FAILED = "failed"
    STATUS_DISPUTED = "disputed"
    STATUS_BLOCKED = "blocked"

    STATUS_CHOICES = (
        (STATUS_PENDING, "En attente"),
        (STATUS_COMPLETED, "Completee"),
        (STATUS_FAILED, "Echouee"),
        (STATUS_DISPUTED, "Contestee"),
        (STATUS_BLOCKED, "Bloquee"),
    )

    organization = models.ForeignKey(
        Organization,
        on_delete=models.SET_NULL,
        related_name="financial_transactions",
        null=True,
        blank=True,
    )
    client = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="financial_transactions",
        limit_choices_to={"role": User.ROLE_CLIENT},
    )
    external_reference = models.CharField(max_length=120, blank=True, db_index=True)
    provider_reference = models.CharField(max_length=120, blank=True)
    transaction_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default=TYPE_PAYMENT)
    ledger_side = models.CharField(max_length=10, choices=SIDE_CHOICES, default=SIDE_DEBIT)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=10, default="XAF")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_COMPLETED)
    description = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    occurred_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-occurred_at", "-created_at"]

    def __str__(self):
        reference = self.external_reference or self.provider_reference or f"TX-{self.pk or 'N/A'}"
        return f"{reference} - {self.amount} {self.currency}"

    def save(self, *args, **kwargs):
        if self.client_id and self.client.organization_id:
            self.organization = self.client.organization
        super().save(*args, **kwargs)

    @property
    def signed_amount(self):
        if self.status != self.STATUS_COMPLETED:
            return Decimal("0.00")
        if self.ledger_side == self.SIDE_CREDIT:
            return self.amount
        return -self.amount


class Product(TimeStampedModel):
    STATUS_ACTIVE = "active"
    STATUS_IN_SERVICE = "in_service"
    STATUS_REPLACED = "replaced"
    STATUS_RETIRED = "retired"

    STATUS_CHOICES = (
        (STATUS_ACTIVE, "Active"),
        (STATUS_IN_SERVICE, "En service"),
        (STATUS_REPLACED, "Remplace"),
        (STATUS_RETIRED, "Retire"),
    )

    organization = models.ForeignKey(
        Organization,
        on_delete=models.SET_NULL,
        related_name="products",
        null=True,
        blank=True,
    )
    client = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="products",
        limit_choices_to={"role": User.ROLE_CLIENT},
    )
    equipment_category = models.ForeignKey(
        EquipmentCategory,
        on_delete=models.SET_NULL,
        related_name="products",
        null=True,
        blank=True,
    )
    name = models.CharField(max_length=255)
    sku = models.CharField(max_length=100, blank=True)
    serial_number = models.CharField(max_length=100)
    equipment_type = models.CharField(
        max_length=20,
        choices=(
            ("copier", "Copieur"),
            ("printer", "Imprimante"),
            ("aircon", "Climatiseur"),
            ("generator", "Groupe electrogene"),
            ("camera", "Camera"),
            ("other", "Autre"),
        ),
        default="other",
    )
    brand = models.CharField(max_length=120, blank=True)
    model_reference = models.CharField(max_length=120, blank=True)
    purchase_date = models.DateField(null=True, blank=True)
    installation_date = models.DateField(null=True, blank=True)
    warranty_end = models.DateField(null=True, blank=True)
    installation_address = models.CharField(max_length=255, blank=True)
    detailed_location = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_ACTIVE)
    iot_enabled = models.BooleanField(default=False)
    health_score = models.PositiveSmallIntegerField(default=100)
    counter_total = models.PositiveIntegerField(default=0)
    counter_color = models.PositiveIntegerField(default=0)
    counter_bw = models.PositiveIntegerField(default=0)
    equipment_photo = models.FileField(upload_to="products/photos/%Y/%m/%d/", blank=True)
    contract_reference = models.CharField(max_length=120, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["name", "serial_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "serial_number"],
                name="sav_product_unique_serial_per_organization",
            ),
        ]

    def __str__(self):
        return f"{self.name} ({self.serial_number})"

    def save(self, *args, **kwargs):
        if self.client_id and self.client.organization_id:
            self.organization = self.client.organization
        if self.equipment_category_id and self.equipment_category.organization_id and not self.organization_id:
            self.organization = self.equipment_category.organization
        super().save(*args, **kwargs)

    @property
    def is_under_warranty(self):
        if not self.warranty_end:
            return False
        return self.warranty_end >= timezone.localdate()


class Ticket(TimeStampedModel):
    STATUS_NEW = "new"
    STATUS_QUALIFICATION = "qualification"
    STATUS_PENDING_CUSTOMER = "pending_customer"
    STATUS_ASSIGNED = "assigned"
    STATUS_IN_PROGRESS = "in_progress"
    STATUS_IN_PROGRESS_N1 = "in_progress_n1"
    STATUS_IN_PROGRESS_N2 = "in_progress_n2"
    STATUS_EXPERTISE = "expertise"
    STATUS_INTERVENTION_PLANNED = "intervention_planned"
    STATUS_INTERVENTION_DONE = "intervention_done"
    STATUS_QA_CONTROL = "qa_control"
    STATUS_PENDING_CLIENT_CONFIRMATION = "pending_client_confirmation"
    STATUS_WAITING = "waiting"
    STATUS_RESOLVED = "resolved"
    STATUS_CLOSED = "closed"
    STATUS_CANCELLED = "cancelled"

    STATUS_CHOICES = (
        (STATUS_NEW, "Nouveau"),
        (STATUS_QUALIFICATION, "Qualification en cours"),
        (STATUS_PENDING_CUSTOMER, "En attente client"),
        (STATUS_ASSIGNED, "Assigne"),
        (STATUS_IN_PROGRESS, "En cours"),
        (STATUS_IN_PROGRESS_N1, "En traitement (N1)"),
        (STATUS_IN_PROGRESS_N2, "En traitement (N2)"),
        (STATUS_EXPERTISE, "Expertise en cours"),
        (STATUS_INTERVENTION_PLANNED, "Intervention planifiee"),
        (STATUS_INTERVENTION_DONE, "Intervention realisee"),
        (STATUS_QA_CONTROL, "En controle qualite"),
        (STATUS_PENDING_CLIENT_CONFIRMATION, "En attente confirmation client"),
        (STATUS_WAITING, "En attente"),
        (STATUS_RESOLVED, "Resolue"),
        (STATUS_CLOSED, "Ferme"),
        (STATUS_CANCELLED, "Annule"),
    )

    PRIORITY_LOW = "low"
    PRIORITY_NORMAL = "normal"
    PRIORITY_HIGH = "high"
    PRIORITY_CRITICAL = "critical"

    PRIORITY_CHOICES = (
        (PRIORITY_LOW, "Faible"),
        (PRIORITY_NORMAL, "Normale"),
        (PRIORITY_HIGH, "Haute"),
        (PRIORITY_CRITICAL, "Critique"),
    )

    CHANNEL_EMAIL = "email"
    CHANNEL_PHONE = "phone"
    CHANNEL_WHATSAPP = "whatsapp"
    CHANNEL_WEB = "web"
    CHANNEL_API = "api"
    CHANNEL_ON_SITE = "on_site"

    CHANNEL_CHOICES = (
        (CHANNEL_EMAIL, "Email"),
        (CHANNEL_PHONE, "Telephone"),
        (CHANNEL_WHATSAPP, "WhatsApp"),
        (CHANNEL_WEB, "Portail web"),
        (CHANNEL_API, "API"),
        (CHANNEL_ON_SITE, "Visite"),
    )

    DOMAIN_IT = "it"
    DOMAIN_COOLING = "cooling"
    DOMAIN_GENERATOR = "generator"
    DOMAIN_VIDEO = "video"
    DOMAIN_OTHER = "other"

    BUSINESS_DOMAIN_CHOICES = (
        (DOMAIN_IT, "Informatique"),
        (DOMAIN_COOLING, "Froid & Climatisation"),
        (DOMAIN_GENERATOR, "Groupe electrogene"),
        (DOMAIN_VIDEO, "Videosurveillance"),
        (DOMAIN_OTHER, "Autre"),
    )

    CATEGORY_BREAKDOWN = "breakdown"
    CATEGORY_INSTALLATION = "installation"
    CATEGORY_MAINTENANCE = "maintenance"
    CATEGORY_RETURN = "return"
    CATEGORY_REFUND = "refund"
    CATEGORY_COMPLAINT = "complaint"
    CATEGORY_PAYMENT = "payment"
    CATEGORY_WITHDRAWAL = "withdrawal"
    CATEGORY_BUG = "bug"
    CATEGORY_ACCOUNT = "account"

    CATEGORY_CHOICES = (
        (CATEGORY_BREAKDOWN, "Panne"),
        (CATEGORY_INSTALLATION, "Installation"),
        (CATEGORY_MAINTENANCE, "Maintenance"),
        (CATEGORY_BUG, "Bug"),
    )

    reference = models.CharField(max_length=32, unique=True, editable=False, blank=True)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.SET_NULL,
        related_name="tickets",
        null=True,
        blank=True,
    )
    client = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="tickets",
        limit_choices_to={"role": User.ROLE_CLIENT},
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="created_tickets",
        null=True,
        blank=True,
    )
    product_label = models.CharField(max_length=255, blank=True)
    product = models.ForeignKey(
        Product,
        on_delete=models.SET_NULL,
        related_name="tickets",
        null=True,
        blank=True,
    )
    assigned_agent = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="assigned_tickets",
        limit_choices_to={"role__in": User.ASSIGNABLE_ROLES},
        null=True,
        blank=True,
    )
    title = models.CharField(max_length=255)
    description = models.TextField()
    business_domain = models.CharField(max_length=20, choices=BUSINESS_DOMAIN_CHOICES, default=DOMAIN_OTHER)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default=CATEGORY_BREAKDOWN)
    channel = models.CharField(max_length=20, choices=CHANNEL_CHOICES, default=CHANNEL_WEB)
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default=STATUS_NEW)
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default=PRIORITY_NORMAL)
    location = models.CharField(max_length=255, blank=True)
    sla_deadline = models.DateTimeField(null=True, blank=True)
    first_response_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    resolution_summary = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.reference or 'N/A'} - {self.title}"

    @property
    def is_open(self):
        return self.status not in {self.STATUS_RESOLVED, self.STATUS_CLOSED, self.STATUS_CANCELLED}

    @property
    def is_overdue(self):
        return bool(self.is_open and self.sla_deadline and self.sla_deadline < timezone.now())

    @property
    def product_display_name(self):
        if self.product_label:
            return self.product_label
        if self.product_id:
            return self.product.name
        return ""

    def save(self, *args, **kwargs):
        if self.client_id and self.client.organization_id:
            self.organization = self.client.organization
        elif self.product_id and self.product.organization_id:
            self.organization = self.product.organization
        if not self.created_by_id and self.client_id:
            self.created_by = self.client
        should_generate_reference = not self.reference
        if should_generate_reference:
            self.reference = self.generate_reference()
        if self.assigned_agent_id and self.status in {
            self.STATUS_NEW,
            self.STATUS_QUALIFICATION,
            self.STATUS_PENDING_CUSTOMER,
            self.STATUS_WAITING,
        }:
            self.status = self.STATUS_ASSIGNED
        if self.status == self.STATUS_RESOLVED and not self.resolved_at:
            self.resolved_at = timezone.now()
        if self.status == self.STATUS_CLOSED and not self.closed_at:
            self.closed_at = timezone.now()
        try:
            with transaction.atomic():
                super().save(*args, **kwargs)
        except IntegrityError:
            if not should_generate_reference:
                raise
            self.reference = ""
            for _ in range(10):
                self.reference = self.generate_reference()
                try:
                    with transaction.atomic():
                        super().save(*args, **kwargs)
                    return
                except IntegrityError:
                    self.reference = ""
            raise

    @staticmethod
    def generate_reference():
        year = timezone.localdate().year
        prefix = f"SAV-{year}-"
        last_ticket = Ticket.objects.filter(reference__startswith=prefix).order_by("-reference").first()
        next_index = 1
        if last_ticket and last_ticket.reference:
            try:
                next_index = int(last_ticket.reference.rsplit("-", 1)[-1]) + 1
            except (TypeError, ValueError):
                next_index = 1
        return f"{prefix}{next_index:05d}"


class TicketAssignment(TimeStampedModel):
    STATUS_ACTIVE = "active"
    STATUS_RELEASED = "released"
    STATUS_ESCALATED = "escalated"

    STATUS_CHOICES = (
        (STATUS_ACTIVE, "Active"),
        (STATUS_RELEASED, "Liberee"),
        (STATUS_ESCALATED, "Escaladee"),
    )

    organization = models.ForeignKey(
        Organization,
        on_delete=models.SET_NULL,
        related_name="ticket_assignments",
        null=True,
        blank=True,
    )
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="assignment_history")
    technician = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="ticket_assignments",
        limit_choices_to={"role__in": User.ASSIGNABLE_ROLES},
    )
    assigned_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="issued_ticket_assignments",
        null=True,
        blank=True,
    )
    assigned_at = models.DateTimeField(default=timezone.now)
    released_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_ACTIVE)
    note = models.TextField(blank=True)

    class Meta:
        ordering = ["-assigned_at", "-created_at"]

    def __str__(self):
        return f"{self.ticket.reference} -> {self.technician}"

    def save(self, *args, **kwargs):
        if self.ticket_id and self.ticket.organization_id:
            self.organization = self.ticket.organization
        elif self.technician_id and self.technician.organization_id:
            self.organization = self.technician.organization
        super().save(*args, **kwargs)


class Message(models.Model):
    TYPE_PUBLIC = "public"
    TYPE_INTERNAL = "internal"

    TYPE_CHOICES = (
        (TYPE_PUBLIC, "Visible client"),
        (TYPE_INTERNAL, "Note interne"),
    )

    CHANNEL_EMAIL = "email"
    CHANNEL_PHONE = "phone"
    CHANNEL_CHAT = "chat"
    CHANNEL_WHATSAPP = "whatsapp"
    CHANNEL_SMS = "sms"
    CHANNEL_SOCIAL = "social"
    CHANNEL_PORTAL = "portal"
    CHANNEL_AR = "ar"

    CHANNEL_CHOICES = (
        (CHANNEL_EMAIL, "Email"),
        (CHANNEL_PHONE, "Telephone"),
        (CHANNEL_CHAT, "Chat"),
        (CHANNEL_WHATSAPP, "WhatsApp"),
        (CHANNEL_SMS, "SMS"),
        (CHANNEL_SOCIAL, "Reseaux sociaux"),
        (CHANNEL_PORTAL, "Portail client"),
        (CHANNEL_AR, "Session AR"),
    )

    DIRECTION_INBOUND = "inbound"
    DIRECTION_OUTBOUND = "outbound"
    DIRECTION_INTERNAL = "internal"

    DIRECTION_CHOICES = (
        (DIRECTION_INBOUND, "Entrant"),
        (DIRECTION_OUTBOUND, "Sortant"),
        (DIRECTION_INTERNAL, "Interne"),
    )

    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="messages")
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name="messages")
    recipient = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="received_messages",
        null=True,
        blank=True,
    )
    message_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default=TYPE_PUBLIC)
    channel = models.CharField(max_length=20, choices=CHANNEL_CHOICES, default=CHANNEL_PORTAL)
    direction = models.CharField(max_length=20, choices=DIRECTION_CHOICES, default=DIRECTION_INBOUND)
    content = models.TextField()
    sentiment_score = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)
    ai_summary = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.ticket.reference} - {self.sender}"


class TicketAttachment(TimeStampedModel):
    KIND_PROOF = "proof"
    KIND_SCREENSHOT = "screenshot"
    KIND_RECEIPT = "receipt"
    KIND_OTHER = "other"

    KIND_CHOICES = (
        (KIND_PROOF, "Preuve"),
        (KIND_SCREENSHOT, "Capture"),
        (KIND_RECEIPT, "Recu"),
        (KIND_OTHER, "Autre"),
    )

    organization = models.ForeignKey(
        Organization,
        on_delete=models.SET_NULL,
        related_name="ticket_attachments",
        null=True,
        blank=True,
    )
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="attachments")
    uploaded_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="ticket_attachments",
        null=True,
        blank=True,
    )
    kind = models.CharField(max_length=20, choices=KIND_CHOICES, default=KIND_OTHER)
    file = models.FileField(upload_to="ticket_attachments/%Y/%m/%d/")
    original_name = models.CharField(max_length=255, blank=True)
    content_type = models.CharField(max_length=120, blank=True)
    size_bytes = models.PositiveIntegerField(default=0)
    note = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.ticket.reference} - {self.original_name or self.file.name}"

    def save(self, *args, **kwargs):
        if self.ticket_id and self.ticket.organization_id:
            self.organization = self.ticket.organization
        elif self.uploaded_by_id and self.uploaded_by.organization_id:
            self.organization = self.uploaded_by.organization

        if self.file:
            if not self.original_name:
                self.original_name = getattr(self.file, "name", "").split("/")[-1][:255]
            if not self.size_bytes:
                self.size_bytes = getattr(self.file, "size", 0) or 0
            uploaded_content_type = getattr(self.file, "content_type", "")
            if uploaded_content_type and not self.content_type:
                self.content_type = uploaded_content_type[:120]

        super().save(*args, **kwargs)


class Intervention(models.Model):
    TYPE_REMOTE = "remote"
    TYPE_ON_SITE = "on_site"
    TYPE_WORKSHOP = "workshop"

    TYPE_CHOICES = (
        (TYPE_REMOTE, "A distance"),
        (TYPE_ON_SITE, "Sur site"),
        (TYPE_WORKSHOP, "Atelier"),
    )

    STATUS_PLANNED = "planned"
    STATUS_IN_PROGRESS = "in_progress"
    STATUS_DONE = "done"
    STATUS_CANCELLED = "cancelled"

    STATUS_CHOICES = (
        (STATUS_PLANNED, "Planifiee"),
        (STATUS_IN_PROGRESS, "En cours"),
        (STATUS_DONE, "Terminee"),
        (STATUS_CANCELLED, "Annulee"),
    )

    organization = models.ForeignKey(
        Organization,
        on_delete=models.SET_NULL,
        related_name="interventions",
        null=True,
        blank=True,
    )
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="interventions")
    agent = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="interventions",
        limit_choices_to={"role__in": User.ASSIGNABLE_ROLES},
    )
    intervention_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default=TYPE_REMOTE)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PLANNED)
    scheduled_for = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    diagnosis = models.TextField(blank=True)
    action_taken = models.CharField(max_length=255)
    parts_used = models.TextField(blank=True)
    structured_parts_used = models.JSONField(default=list, blank=True)
    time_spent_minutes = models.PositiveIntegerField(default=0)
    technical_report = models.TextField(blank=True)
    location_snapshot = models.CharField(max_length=255, blank=True)
    client_signed_by = models.CharField(max_length=255, blank=True)
    client_signed_at = models.DateTimeField(null=True, blank=True)
    client_signature_file = models.FileField(upload_to="interventions/signatures/%Y/%m/%d/", blank=True)
    report_pdf = models.FileField(upload_to="interventions/reports/%Y/%m/%d/", blank=True)
    report_generated_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.ticket.reference} - {self.action_taken}"

    def save(self, *args, **kwargs):
        if self.ticket_id and self.ticket.organization_id:
            self.organization = self.ticket.organization
        if self.ticket_id and not self.location_snapshot:
            self.location_snapshot = self.ticket.location
        super().save(*args, **kwargs)


class InterventionMedia(TimeStampedModel):
    KIND_BEFORE = "before"
    KIND_DURING = "during"
    KIND_AFTER = "after"
    KIND_OTHER = "other"

    KIND_CHOICES = (
        (KIND_BEFORE, "Avant intervention"),
        (KIND_DURING, "Pendant intervention"),
        (KIND_AFTER, "Apres intervention"),
        (KIND_OTHER, "Autre"),
    )

    organization = models.ForeignKey(
        Organization,
        on_delete=models.SET_NULL,
        related_name="intervention_media",
        null=True,
        blank=True,
    )
    intervention = models.ForeignKey(Intervention, on_delete=models.CASCADE, related_name="media")
    uploaded_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="intervention_media",
        null=True,
        blank=True,
    )
    kind = models.CharField(max_length=20, choices=KIND_CHOICES, default=KIND_OTHER)
    file = models.FileField(upload_to="interventions/media/%Y/%m/%d/")
    note = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["created_at", "id"]

    def __str__(self):
        return f"{self.intervention.ticket.reference} - {self.get_kind_display()}"

    def save(self, *args, **kwargs):
        if self.intervention_id and self.intervention.organization_id:
            self.organization = self.intervention.organization
        elif self.uploaded_by_id and self.uploaded_by.organization_id:
            self.organization = self.uploaded_by.organization
        super().save(*args, **kwargs)


class SupportSession(TimeStampedModel):
    TYPE_VIDEO = "video"
    TYPE_AR = "ar"

    TYPE_CHOICES = (
        (TYPE_VIDEO, "Visio"),
        (TYPE_AR, "Realite augmentee"),
    )

    STATUS_SCHEDULED = "scheduled"
    STATUS_LIVE = "live"
    STATUS_COMPLETED = "completed"
    STATUS_CANCELLED = "cancelled"

    STATUS_CHOICES = (
        (STATUS_SCHEDULED, "Planifiee"),
        (STATUS_LIVE, "En direct"),
        (STATUS_COMPLETED, "Terminee"),
        (STATUS_CANCELLED, "Annulee"),
    )

    organization = models.ForeignKey(
        Organization,
        on_delete=models.SET_NULL,
        related_name="support_sessions",
        null=True,
        blank=True,
    )
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="support_sessions")
    client = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="support_sessions",
        limit_choices_to={"role": User.ROLE_CLIENT},
    )
    agent = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="handled_support_sessions",
        limit_choices_to={"role__in": User.ASSIGNABLE_ROLES},
        null=True,
        blank=True,
    )
    session_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default=TYPE_VIDEO)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_SCHEDULED)
    meeting_link = models.URLField(blank=True)
    recording_url = models.URLField(blank=True)
    annotations_summary = models.TextField(blank=True)
    scheduled_for = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.ticket.reference} - {self.get_session_type_display()}"

    def save(self, *args, **kwargs):
        if self.ticket_id and self.ticket.organization_id:
            self.organization = self.ticket.organization
        elif self.client_id and self.client.organization_id:
            self.organization = self.client.organization
        super().save(*args, **kwargs)


class ProductTelemetry(models.Model):
    SOURCE_IOT = "iot"
    SOURCE_MANUAL = "manual"
    SOURCE_IMPORT = "import"

    SOURCE_CHOICES = (
        (SOURCE_IOT, "Capteur IoT"),
        (SOURCE_MANUAL, "Saisie manuelle"),
        (SOURCE_IMPORT, "Import"),
    )

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="telemetry")
    metric_name = models.CharField(max_length=100)
    value = models.DecimalField(max_digits=10, decimal_places=2)
    unit = models.CharField(max_length=20, blank=True)
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default=SOURCE_IOT)
    captured_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-captured_at"]

    def __str__(self):
        return f"{self.product.serial_number} - {self.metric_name}={self.value}"


class PredictiveAlert(TimeStampedModel):
    TYPE_ANOMALY = "anomaly"
    TYPE_MAINTENANCE = "maintenance"
    TYPE_WARRANTY = "warranty"
    TYPE_REPEAT_FAILURE = "repeat_failure"

    TYPE_CHOICES = (
        (TYPE_ANOMALY, "Anomalie"),
        (TYPE_MAINTENANCE, "Maintenance"),
        (TYPE_WARRANTY, "Fin de garantie"),
        (TYPE_REPEAT_FAILURE, "Panne recurrente"),
    )

    SEVERITY_LOW = "low"
    SEVERITY_MEDIUM = "medium"
    SEVERITY_HIGH = "high"
    SEVERITY_CRITICAL = "critical"

    SEVERITY_CHOICES = (
        (SEVERITY_LOW, "Faible"),
        (SEVERITY_MEDIUM, "Moyenne"),
        (SEVERITY_HIGH, "Haute"),
        (SEVERITY_CRITICAL, "Critique"),
    )

    STATUS_OPEN = "open"
    STATUS_IN_PROGRESS = "in_progress"
    STATUS_RESOLVED = "resolved"
    STATUS_DISMISSED = "dismissed"

    STATUS_CHOICES = (
        (STATUS_OPEN, "Ouverte"),
        (STATUS_IN_PROGRESS, "En traitement"),
        (STATUS_RESOLVED, "Resolue"),
        (STATUS_DISMISSED, "Ignoree"),
    )

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="predictive_alerts")
    ticket = models.ForeignKey(
        Ticket,
        on_delete=models.SET_NULL,
        related_name="predictive_alerts",
        null=True,
        blank=True,
    )
    alert_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default=TYPE_ANOMALY)
    severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES, default=SEVERITY_MEDIUM)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_OPEN)
    title = models.CharField(max_length=255)
    description = models.TextField()
    metric_name = models.CharField(max_length=100, blank=True)
    metric_value = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    predicted_failure_at = models.DateTimeField(null=True, blank=True)
    recommended_action = models.TextField(blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.product.serial_number} - {self.title}"


class KnowledgeArticle(TimeStampedModel):
    STATUS_DRAFT = "draft"
    STATUS_PUBLISHED = "published"

    STATUS_CHOICES = (
        (STATUS_DRAFT, "Brouillon"),
        (STATUS_PUBLISHED, "Publie"),
    )

    AUDIENCE_PUBLIC = "public"
    AUDIENCE_INTERNAL = "internal"

    AUDIENCE_CHOICES = (
        (AUDIENCE_PUBLIC, "Clients"),
        (AUDIENCE_INTERNAL, "Interne"),
    )

    organization = models.ForeignKey(
        Organization,
        on_delete=models.SET_NULL,
        related_name="knowledge_articles",
        null=True,
        blank=True,
    )
    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True, blank=True)
    category = models.CharField(max_length=100, blank=True)
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, related_name="knowledge_articles", null=True, blank=True)
    summary = models.TextField(blank=True)
    content = models.TextField()
    keywords = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    audience = models.CharField(max_length=20, choices=AUDIENCE_CHOICES, default=AUDIENCE_PUBLIC)
    helpful_votes = models.PositiveIntegerField(default=0)
    unhelpful_votes = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["title"]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if self.product_id and self.product.organization_id:
            self.organization = self.product.organization
        if not self.slug:
            self.slug = _generate_unique_slug(self.__class__, self.title, self.pk)
        super().save(*args, **kwargs)


class Notification(models.Model):
    CHANNEL_EMAIL = "email"
    CHANNEL_SMS = "sms"
    CHANNEL_WHATSAPP = "whatsapp"
    CHANNEL_PUSH = "push"
    CHANNEL_IN_APP = "in_app"

    CHANNEL_CHOICES = (
        (CHANNEL_EMAIL, "Email"),
        (CHANNEL_SMS, "SMS"),
        (CHANNEL_WHATSAPP, "WhatsApp"),
        (CHANNEL_PUSH, "Push"),
        (CHANNEL_IN_APP, "In-app"),
    )

    STATUS_PENDING = "pending"
    STATUS_SENT = "sent"
    STATUS_READ = "read"
    STATUS_FAILED = "failed"

    STATUS_CHOICES = (
        (STATUS_PENDING, "En attente"),
        (STATUS_SENT, "Envoyee"),
        (STATUS_READ, "Lue"),
        (STATUS_FAILED, "Echouee"),
    )

    organization = models.ForeignKey(
        Organization,
        on_delete=models.SET_NULL,
        related_name="notifications",
        null=True,
        blank=True,
    )
    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name="notifications")
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="notifications", null=True, blank=True)
    channel = models.CharField(max_length=20, choices=CHANNEL_CHOICES, default=CHANNEL_IN_APP)
    event_type = models.CharField(max_length=100)
    subject = models.CharField(max_length=255)
    message = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.recipient} - {self.subject}"

    def save(self, *args, **kwargs):
        if self.ticket_id and self.ticket.organization_id:
            self.organization = self.ticket.organization
        elif self.recipient_id and self.recipient.organization_id:
            self.organization = self.recipient.organization
        super().save(*args, **kwargs)


class DeviceRegistration(TimeStampedModel):
    PLATFORM_ANDROID = "android"
    PLATFORM_IOS = "ios"
    PLATFORM_WEB = "web"
    PLATFORM_DESKTOP = "desktop"

    PLATFORM_CHOICES = (
        (PLATFORM_ANDROID, "Android"),
        (PLATFORM_IOS, "iOS"),
        (PLATFORM_WEB, "Web"),
        (PLATFORM_DESKTOP, "Desktop"),
    )

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="device_registrations")
    token = models.CharField(max_length=512, unique=True)
    platform = models.CharField(max_length=20, choices=PLATFORM_CHOICES)
    device_id = models.CharField(max_length=255, blank=True)
    app_version = models.CharField(max_length=50, blank=True)
    is_active = models.BooleanField(default=True)
    last_seen_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-last_seen_at", "-updated_at"]

    def __str__(self):
        return f"{self.user} - {self.platform}"


class OfferRecommendation(models.Model):
    TYPE_WARRANTY_EXTENSION = "warranty_extension"
    TYPE_MAINTENANCE_CONTRACT = "maintenance_contract"
    TYPE_SPARE_PART = "spare_part"
    TYPE_UPGRADE = "upgrade"
    TYPE_PREMIUM_SUPPORT = "premium_support"

    TYPE_CHOICES = (
        (TYPE_WARRANTY_EXTENSION, "Extension de garantie"),
        (TYPE_MAINTENANCE_CONTRACT, "Contrat de maintenance"),
        (TYPE_SPARE_PART, "Piece detachee"),
        (TYPE_UPGRADE, "Mise a niveau"),
        (TYPE_PREMIUM_SUPPORT, "Support premium"),
    )

    STATUS_PROPOSED = "proposed"
    STATUS_ACCEPTED = "accepted"
    STATUS_REJECTED = "rejected"
    STATUS_EXPIRED = "expired"

    STATUS_CHOICES = (
        (STATUS_PROPOSED, "Proposee"),
        (STATUS_ACCEPTED, "Acceptee"),
        (STATUS_REJECTED, "Refusee"),
        (STATUS_EXPIRED, "Expiree"),
    )

    organization = models.ForeignKey(
        Organization,
        on_delete=models.SET_NULL,
        related_name="offers",
        null=True,
        blank=True,
    )
    client = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="offers",
        limit_choices_to={"role": User.ROLE_CLIENT},
    )
    ticket = models.ForeignKey(Ticket, on_delete=models.SET_NULL, related_name="offers", null=True, blank=True)
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, related_name="offers", null=True, blank=True)
    offer_type = models.CharField(max_length=30, choices=TYPE_CHOICES)
    title = models.CharField(max_length=255)
    description = models.TextField()
    rationale = models.TextField(blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PROPOSED)
    valid_until = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.client} - {self.title}"

    def save(self, *args, **kwargs):
        if self.client_id and self.client.organization_id:
            self.organization = self.client.organization
        elif self.ticket_id and self.ticket.organization_id:
            self.organization = self.ticket.organization
        elif self.product_id and self.product.organization_id:
            self.organization = self.product.organization
        super().save(*args, **kwargs)


class AccountCredit(TimeStampedModel):
    STATUS_EXECUTED = "executed"
    STATUS_CANCELLED = "cancelled"

    STATUS_CHOICES = (
        (STATUS_EXECUTED, "Execute"),
        (STATUS_CANCELLED, "Annule"),
    )

    organization = models.ForeignKey(
        Organization,
        on_delete=models.SET_NULL,
        related_name="account_credits",
        null=True,
        blank=True,
    )
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="account_credits")
    client = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="received_account_credits",
        limit_choices_to={"role": User.ROLE_CLIENT},
    )
    executed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="executed_account_credits",
        null=True,
        blank=True,
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=10, default="XAF")
    reason = models.CharField(max_length=255)
    note = models.TextField(blank=True)
    external_reference = models.CharField(max_length=120, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_EXECUTED)
    executed_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-executed_at", "-created_at"]

    def __str__(self):
        return f"{self.ticket.reference} - {self.amount} {self.currency}"

    def save(self, *args, **kwargs):
        if self.ticket_id:
            if not self.client_id:
                self.client = self.ticket.client
            if self.ticket.organization_id:
                self.organization = self.ticket.organization
        elif self.client_id and self.client.organization_id:
            self.organization = self.client.organization
        super().save(*args, **kwargs)


class TicketFeedback(TimeStampedModel):
    organization = models.ForeignKey(
        Organization,
        on_delete=models.SET_NULL,
        related_name="ticket_feedbacks",
        null=True,
        blank=True,
    )
    ticket = models.OneToOneField(Ticket, on_delete=models.CASCADE, related_name="feedback")
    client = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="ticket_feedbacks",
        limit_choices_to={"role": User.ROLE_CLIENT},
    )
    rating = models.PositiveSmallIntegerField()
    comment = models.TextField(blank=True)
    submitted_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-submitted_at", "-created_at"]

    def __str__(self):
        return f"{self.ticket.reference} - {self.rating}/5"

    def save(self, *args, **kwargs):
        if self.ticket_id:
            self.client = self.ticket.client
            self.organization = self.ticket.organization
        elif self.client_id and self.client.organization_id:
            self.organization = self.client.organization
        super().save(*args, **kwargs)


class SlaRule(TimeStampedModel):
    organization = models.ForeignKey(
        Organization,
        on_delete=models.SET_NULL,
        related_name="sla_rules",
        null=True,
        blank=True,
    )
    priority = models.CharField(max_length=20, choices=Ticket.PRIORITY_CHOICES)
    response_deadline_minutes = models.PositiveIntegerField(default=120)
    resolution_deadline_hours = models.PositiveIntegerField(default=8)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["priority", "id"]
        unique_together = [("organization", "priority")]

    def __str__(self):
        return f"{self.get_priority_display()} - {self.response_deadline_minutes} min / {self.resolution_deadline_hours} h"


class GeneratedReport(TimeStampedModel):
    TYPE_DAILY = "journalier"
    TYPE_WEEKLY = "hebdomadaire"
    TYPE_MONTHLY = "mensuel"

    TYPE_CHOICES = (
        (TYPE_DAILY, "Journalier"),
        (TYPE_WEEKLY, "Hebdomadaire"),
        (TYPE_MONTHLY, "Mensuel"),
    )

    FORMAT_PDF = "pdf"
    FORMAT_XLSX = "xlsx"
    FORMAT_CSV = "csv"

    FORMAT_CHOICES = (
        (FORMAT_PDF, "PDF"),
        (FORMAT_XLSX, "Excel"),
        (FORMAT_CSV, "CSV"),
    )

    organization = models.ForeignKey(
        Organization,
        on_delete=models.SET_NULL,
        related_name="generated_reports",
        null=True,
        blank=True,
    )
    generated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="generated_reports",
        null=True,
        blank=True,
    )
    report_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    export_format = models.CharField(max_length=10, choices=FORMAT_CHOICES, default=FORMAT_PDF)
    period_label = models.CharField(max_length=120)
    payload = models.JSONField(default=dict, blank=True)
    archive_file = models.FileField(upload_to="reports/%Y/%m/%d/", blank=True)
    sent_to = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.report_type} - {self.period_label}"


class AutomationRule(TimeStampedModel):
    TRIGGER_TICKET_CREATED = "ticket_created"
    TRIGGER_TICKET_UPDATED = "ticket_updated"
    TRIGGER_TICKET_OVERDUE = "ticket_overdue"
    TRIGGER_PREDICTIVE_ALERT = "predictive_alert_created"
    TRIGGER_MANUAL = "manual_run"

    TRIGGER_CHOICES = (
        (TRIGGER_TICKET_CREATED, "Ticket cree"),
        (TRIGGER_TICKET_UPDATED, "Ticket mis a jour"),
        (TRIGGER_TICKET_OVERDUE, "Ticket en retard"),
        (TRIGGER_PREDICTIVE_ALERT, "Alerte predictive"),
        (TRIGGER_MANUAL, "Execution manuelle"),
    )

    organization = models.ForeignKey(
        Organization,
        on_delete=models.SET_NULL,
        related_name="automation_rules",
        null=True,
        blank=True,
    )
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    trigger_event = models.CharField(max_length=30, choices=TRIGGER_CHOICES, default=TRIGGER_MANUAL)
    is_active = models.BooleanField(default=True)
    priority = models.PositiveIntegerField(default=100)
    conditions = models.JSONField(default=dict, blank=True)
    actions = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ["priority", "name"]

    def __str__(self):
        return self.name


class WorkflowExecution(models.Model):
    STATUS_SUCCESS = "success"
    STATUS_FAILED = "failed"
    STATUS_SKIPPED = "skipped"

    STATUS_CHOICES = (
        (STATUS_SUCCESS, "Succes"),
        (STATUS_FAILED, "Echec"),
        (STATUS_SKIPPED, "Ignore"),
    )

    organization = models.ForeignKey(
        Organization,
        on_delete=models.SET_NULL,
        related_name="workflow_executions",
        null=True,
        blank=True,
    )
    rule = models.ForeignKey(AutomationRule, on_delete=models.SET_NULL, related_name="executions", null=True, blank=True)
    ticket = models.ForeignKey(Ticket, on_delete=models.SET_NULL, related_name="workflow_executions", null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_SUCCESS)
    trigger_event = models.CharField(max_length=50)
    result = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.trigger_event} - {self.status}"

    def save(self, *args, **kwargs):
        if self.ticket_id and self.ticket.organization_id:
            self.organization = self.ticket.organization
        elif self.rule_id and self.rule.organization_id:
            self.organization = self.rule.organization
        super().save(*args, **kwargs)


class AIActionLog(models.Model):
    ACTION_TRIAGE = "triage"
    ACTION_DIAGNOSIS = "diagnosis"
    ACTION_AUTO_RESOLUTION = "auto_resolution"
    ACTION_OFFER_GENERATION = "offer_generation"
    ACTION_PREDICTIVE_ANALYSIS = "predictive_analysis"
    ACTION_INSIGHT_SUMMARY = "insight_summary"

    ACTION_CHOICES = (
        (ACTION_TRIAGE, "Qualification"),
        (ACTION_DIAGNOSIS, "Diagnostic"),
        (ACTION_AUTO_RESOLUTION, "Resolution automatique"),
        (ACTION_OFFER_GENERATION, "Generation d'offres"),
        (ACTION_PREDICTIVE_ANALYSIS, "Analyse predictive"),
        (ACTION_INSIGHT_SUMMARY, "Synthese client"),
    )

    STATUS_SUGGESTED = "suggested"
    STATUS_EXECUTED = "executed"
    STATUS_REJECTED = "rejected"
    STATUS_ERROR = "error"

    STATUS_CHOICES = (
        (STATUS_SUGGESTED, "Suggeree"),
        (STATUS_EXECUTED, "Executee"),
        (STATUS_REJECTED, "Rejetee"),
        (STATUS_ERROR, "Erreur"),
    )

    organization = models.ForeignKey(
        Organization,
        on_delete=models.SET_NULL,
        related_name="ai_actions",
        null=True,
        blank=True,
    )
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="ai_actions", null=True, blank=True)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="ai_actions", null=True, blank=True)
    action_type = models.CharField(max_length=30, choices=ACTION_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_SUGGESTED)
    confidence = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    rationale = models.TextField()
    input_snapshot = models.JSONField(default=dict, blank=True)
    output_snapshot = models.JSONField(default=dict, blank=True)
    approved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="approved_ai_actions",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.action_type} - {self.status}"

    def save(self, *args, **kwargs):
        if self.ticket_id and self.ticket.organization_id:
            self.organization = self.ticket.organization
        elif self.product_id and self.product.organization_id:
            self.organization = self.product.organization
        super().save(*args, **kwargs)


class AuditLog(models.Model):
    ACTOR_HUMAN = "human"
    ACTOR_AI = "ai"
    ACTOR_SYSTEM = "system"

    ACTOR_CHOICES = (
        (ACTOR_HUMAN, "Humain"),
        (ACTOR_AI, "IA"),
        (ACTOR_SYSTEM, "Systeme"),
    )

    organization = models.ForeignKey(
        Organization,
        on_delete=models.SET_NULL,
        related_name="audit_logs",
        null=True,
        blank=True,
    )
    actor = models.ForeignKey(User, on_delete=models.SET_NULL, related_name="audit_logs", null=True, blank=True)
    actor_type = models.CharField(max_length=20, choices=ACTOR_CHOICES, default=ACTOR_HUMAN)
    action = models.CharField(max_length=100)
    target_model = models.CharField(max_length=100)
    target_id = models.PositiveIntegerField(null=True, blank=True)
    target_reference = models.CharField(max_length=255, blank=True)
    source_ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=255, blank=True)
    request_path = models.CharField(max_length=255, blank=True)
    http_method = models.CharField(max_length=10, blank=True)
    details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.actor_type} - {self.action}"
