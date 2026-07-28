from django.db import IntegrityError, models, transaction
from django.utils import timezone

from .base import TimeStampedModel
from .equipment import Product
from .organizations import Organization
from .users import User


class Ticket(TimeStampedModel):
    STATUS_NEW = "new"
    STATUS_PENDING_ASSIGNMENT = "pending_assignment"
    STATUS_ASSIGNED = "assigned"
    STATUS_TEAM_PENDING = "team_pending"
    STATUS_TEAM_READY = "team_ready"
    STATUS_PLANNING_PROPOSED = "planning_proposed"
    STATUS_PLANNED = "planned"
    STATUS_START_REQUESTED = "start_requested"
    STATUS_IN_PROGRESS = "in_progress"
    STATUS_COLLECTIVE_IN_PROGRESS = "collective_in_progress"
    STATUS_WAITING_PART = "waiting_part"
    STATUS_WAITING = STATUS_WAITING_PART
    STATUS_ESCALATED = "escalated"
    STATUS_WAITING_SOLUTION = "waiting_solution"
    STATUS_WAITING_DIAGNOSTIC = "waiting_diagnostic"
    STATUS_FINISH_REQUESTED = "finish_requested"
    STATUS_DONE = "done"
    STATUS_RESOLVED = "resolved"
    STATUS_CLOSED = "closed"
    STATUS_CANCELLED = "cancelled"
    STATUS_REASSIGN_REQUIRED = "reassign_required"
    STATUS_REASSIGNED = "reassigned"
    STATUS_BLOCKED_DIRECTION = "blocked_direction"

    STATUS_CHOICES = (
        (STATUS_NEW, "Nouveau"),
        (STATUS_PENDING_ASSIGNMENT, "En attente d'assignation"),
        (STATUS_ASSIGNED, "Assigne"),
        (STATUS_TEAM_PENDING, "En attente constitution equipe"),
        (STATUS_TEAM_READY, "Equipe constituee"),
        (STATUS_PLANNING_PROPOSED, "Planification proposee"),
        (STATUS_PLANNED, "Planifie"),
        (STATUS_START_REQUESTED, "Demande de debut envoyee"),
        (STATUS_IN_PROGRESS, "En cours"),
        (STATUS_COLLECTIVE_IN_PROGRESS, "Intervention collective"),
        (STATUS_WAITING_PART, "En attente de piece"),
        (STATUS_ESCALATED, "En escalade"),
        (STATUS_WAITING_SOLUTION, "En attente solution responsable"),
        (STATUS_WAITING_DIAGNOSTIC, "En attente diagnostic"),
        (STATUS_FINISH_REQUESTED, "Demande de fin envoyee"),
        (STATUS_DONE, "Termine"),
        (STATUS_RESOLVED, "Resolue (valide client)"),
        (STATUS_CLOSED, "Ferme"),
        (STATUS_CANCELLED, "Annule"),
        (STATUS_REASSIGN_REQUIRED, "A reassigner"),
        (STATUS_REASSIGNED, "Reassigne"),
        (STATUS_BLOCKED_DIRECTION, "Bloque - Direction"),
    )

    STATUS_QUALIFICATION = "qualification"
    STATUS_PENDING_CUSTOMER = "pending_customer"
    STATUS_IN_PROGRESS_N1 = "in_progress_n1"
    STATUS_IN_PROGRESS_N2 = "in_progress_n2"
    STATUS_EXPERTISE = "expertise"
    STATUS_INTERVENTION_PLANNED = "intervention_planned"
    STATUS_INTERVENTION_DONE = "intervention_done"
    STATUS_QA_CONTROL = "qa_control"
    STATUS_PENDING_CLIENT_CONFIRMATION = "pending_client_confirmation"

    LEGACY_STATUS_MAP = {
        STATUS_QUALIFICATION: STATUS_PENDING_ASSIGNMENT,
        STATUS_PENDING_CUSTOMER: STATUS_WAITING_PART,
        STATUS_IN_PROGRESS_N1: STATUS_IN_PROGRESS,
        STATUS_IN_PROGRESS_N2: STATUS_IN_PROGRESS,
        STATUS_EXPERTISE: STATUS_ESCALATED,
        STATUS_INTERVENTION_PLANNED: STATUS_PLANNED,
        STATUS_INTERVENTION_DONE: STATUS_DONE,
        STATUS_QA_CONTROL: STATUS_RESOLVED,
        STATUS_PENDING_CLIENT_CONFIRMATION: STATUS_RESOLVED,
        "waiting": STATUS_WAITING_PART,
        "waiting_parts": STATUS_WAITING_PART,
        "waiting_customer": STATUS_WAITING_PART,
        "triaged": STATUS_PENDING_ASSIGNMENT,
        "scheduled": STATUS_PLANNED,
    }

    PUBLIC_STATUS_MAP = {
        STATUS_NEW: "Nouveau",
        STATUS_PENDING_ASSIGNMENT: "Nouveau",
        STATUS_ASSIGNED: "Assigné",
        STATUS_REASSIGN_REQUIRED: "Assigné",
        STATUS_REASSIGNED: "Assigné",
        STATUS_TEAM_PENDING: "Assigné",
        STATUS_TEAM_READY: "Assigné",
        STATUS_PLANNING_PROPOSED: "Assigné",
        STATUS_PLANNED: "Planifié",
        STATUS_START_REQUESTED: "En cours",
        STATUS_IN_PROGRESS: "En cours",
        STATUS_COLLECTIVE_IN_PROGRESS: "En cours",
        STATUS_WAITING_PART: "Planifié",
        STATUS_ESCALATED: "En cours",
        STATUS_WAITING_SOLUTION: "En cours",
        STATUS_WAITING_DIAGNOSTIC: "En cours",
        STATUS_FINISH_REQUESTED: "En cours",
        STATUS_DONE: "Terminé",
        STATUS_RESOLVED: "Terminé",
        STATUS_CLOSED: "Terminé",
        STATUS_CANCELLED: "Terminé",
        STATUS_BLOCKED_DIRECTION: "En cours",
    }

    PROCESS_TRANSITIONS = {
        STATUS_NEW: {STATUS_NEW, STATUS_PENDING_ASSIGNMENT, STATUS_ASSIGNED, STATUS_TEAM_PENDING, STATUS_REASSIGN_REQUIRED, STATUS_CANCELLED},
        STATUS_PENDING_ASSIGNMENT: {STATUS_PENDING_ASSIGNMENT, STATUS_ASSIGNED, STATUS_TEAM_PENDING, STATUS_REASSIGN_REQUIRED, STATUS_CANCELLED},
        STATUS_ASSIGNED: {STATUS_ASSIGNED, STATUS_TEAM_PENDING, STATUS_TEAM_READY, STATUS_PLANNING_PROPOSED, STATUS_START_REQUESTED, STATUS_ESCALATED, STATUS_REASSIGN_REQUIRED, STATUS_CANCELLED},
        STATUS_TEAM_PENDING: {STATUS_TEAM_PENDING, STATUS_TEAM_READY, STATUS_ASSIGNED, STATUS_REASSIGN_REQUIRED, STATUS_CANCELLED},
        STATUS_TEAM_READY: {STATUS_TEAM_READY, STATUS_PLANNING_PROPOSED, STATUS_START_REQUESTED, STATUS_ESCALATED, STATUS_REASSIGN_REQUIRED, STATUS_CANCELLED},
        STATUS_PLANNING_PROPOSED: {STATUS_PLANNING_PROPOSED, STATUS_PLANNED, STATUS_ASSIGNED, STATUS_CANCELLED},
        STATUS_PLANNED: {STATUS_PLANNED, STATUS_START_REQUESTED, STATUS_ESCALATED, STATUS_REASSIGN_REQUIRED, STATUS_CANCELLED},
        STATUS_START_REQUESTED: {STATUS_START_REQUESTED, STATUS_IN_PROGRESS, STATUS_COLLECTIVE_IN_PROGRESS, STATUS_PLANNED, STATUS_CANCELLED},
        STATUS_IN_PROGRESS: {STATUS_IN_PROGRESS, STATUS_WAITING_PART, STATUS_ESCALATED, STATUS_FINISH_REQUESTED, STATUS_CANCELLED},
        STATUS_COLLECTIVE_IN_PROGRESS: {STATUS_COLLECTIVE_IN_PROGRESS, STATUS_WAITING_PART, STATUS_ESCALATED, STATUS_FINISH_REQUESTED, STATUS_CANCELLED},
        STATUS_WAITING_PART: {STATUS_WAITING_PART, STATUS_START_REQUESTED, STATUS_IN_PROGRESS, STATUS_COLLECTIVE_IN_PROGRESS, STATUS_ESCALATED, STATUS_CANCELLED},
        STATUS_ESCALATED: {STATUS_ESCALATED, STATUS_WAITING_SOLUTION, STATUS_REASSIGNED, STATUS_REASSIGN_REQUIRED, STATUS_ASSIGNED, STATUS_CANCELLED},
        STATUS_WAITING_SOLUTION: {STATUS_WAITING_SOLUTION, STATUS_IN_PROGRESS, STATUS_COLLECTIVE_IN_PROGRESS, STATUS_PLANNED, STATUS_ASSIGNED, STATUS_TEAM_READY, STATUS_CANCELLED},
        STATUS_WAITING_DIAGNOSTIC: {STATUS_WAITING_DIAGNOSTIC, STATUS_PLANNING_PROPOSED, STATUS_PLANNED, STATUS_START_REQUESTED, STATUS_ESCALATED, STATUS_ASSIGNED, STATUS_REASSIGN_REQUIRED, STATUS_CANCELLED},
        STATUS_FINISH_REQUESTED: {STATUS_FINISH_REQUESTED, STATUS_DONE, STATUS_IN_PROGRESS, STATUS_COLLECTIVE_IN_PROGRESS, STATUS_CANCELLED},
        STATUS_DONE: {STATUS_DONE, STATUS_CLOSED, STATUS_RESOLVED, STATUS_CANCELLED},
        STATUS_RESOLVED: {STATUS_RESOLVED, STATUS_CLOSED, STATUS_ASSIGNED},
        STATUS_CLOSED: {STATUS_CLOSED},
        STATUS_CANCELLED: {STATUS_CANCELLED},
        STATUS_REASSIGN_REQUIRED: {STATUS_REASSIGN_REQUIRED, STATUS_ASSIGNED, STATUS_TEAM_PENDING, STATUS_TEAM_READY, STATUS_REASSIGNED},
        STATUS_REASSIGNED: {STATUS_REASSIGNED, STATUS_ASSIGNED, STATUS_TEAM_READY},
        STATUS_BLOCKED_DIRECTION: {STATUS_BLOCKED_DIRECTION, STATUS_ESCALATED, STATUS_REASSIGN_REQUIRED},
    }

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
    DOMAIN_MONETICS = "monetics"
    DOMAIN_CFAO = "cfao"
    DOMAIN_COOLING = "cooling"
    DOMAIN_GENERATOR = "generator"
    DOMAIN_VIDEO = "video"
    DOMAIN_GEOLOCATION = "geolocation"
    DOMAIN_OTHER = "other"

    BUSINESS_DOMAIN_CHOICES = (
        (DOMAIN_IT, "Informatique"),
        (DOMAIN_MONETICS, "Monetique"),
        (DOMAIN_CFAO, "CFAO"),
        (DOMAIN_COOLING, "Froid & Climatisation"),
        (DOMAIN_GENERATOR, "Groupe electrogene"),
        (DOMAIN_VIDEO, "Videosurveillance"),
        (DOMAIN_GEOLOCATION, "Geolocalisation"),
        (DOMAIN_OTHER, "Autre"),
    )
    DOMAIN_REFERENCE_CODES = {
        DOMAIN_IT: "IT",
        DOMAIN_MONETICS: "MO",
        DOMAIN_CFAO: "CF",
        DOMAIN_COOLING: "FR",
        DOMAIN_GENERATOR: "GE",
        DOMAIN_VIDEO: "VD",
        DOMAIN_GEOLOCATION: "GL",
        DOMAIN_OTHER: "SAV",
    }

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
    team_leader = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="led_team_tickets",
        null=True,
        blank=True,
    )
    team_members = models.ManyToManyField(
        User,
        related_name="member_team_tickets",
        blank=True,
    )
    is_team_intervention = models.BooleanField(default=False)
    escalation_count = models.PositiveSmallIntegerField(default=0)
    last_escalation_at = models.DateTimeField(null=True, blank=True)
    last_escalation_reason = models.TextField(blank=True)
    status_before_escalation = models.CharField(max_length=32, blank=True)
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
    archived_at = models.DateTimeField(null=True, blank=True)
    archive_reason = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["organization", "status"], name="sav_ticket_org_status_idx"),
            models.Index(fields=["organization", "priority"], name="sav_ticket_org_priority_idx"),
            models.Index(fields=["organization", "created_at"], name="sav_ticket_org_created_idx"),
            models.Index(fields=["organization", "sla_deadline"], name="sav_ticket_org_sla_idx"),
            models.Index(fields=["client", "status"], name="sav_ticket_client_status_idx"),
            models.Index(fields=["assigned_agent", "status"], name="sav_ticket_agent_status_idx"),
            models.Index(fields=["status", "sla_deadline"], name="sav_ticket_status_sla_idx"),
        ]

    def __str__(self):
        return f"{self.reference or 'N/A'} - {self.title}"

    @property
    def is_open(self):
        return self.status not in {
            self.STATUS_DONE,
            self.STATUS_RESOLVED,
            self.STATUS_CLOSED,
            self.STATUS_CANCELLED,
            self.STATUS_BLOCKED_DIRECTION,
        }

    @property
    def public_status(self):
        if self.status in {self.STATUS_ESCALATED, self.STATUS_WAITING_SOLUTION} and self.status_before_escalation:
            return self.PUBLIC_STATUS_MAP.get(self.status_before_escalation, self.PUBLIC_STATUS_MAP[self.STATUS_IN_PROGRESS])
        return self.PUBLIC_STATUS_MAP.get(self.status, "Inconnu")

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
        self.status = self.normalize_process_status(self.status)
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
            self.STATUS_PENDING_ASSIGNMENT,
            self.STATUS_REASSIGNED,
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

    @property
    def service_reference_code(self):
        return "SAV"

    def generate_reference(self):
        year = timezone.localdate().year
        month = timezone.localdate().month
        prefix = f"ASS-SAV-{month:02d}-{year}-"
        last_ticket = Ticket.objects.filter(reference__startswith=prefix).order_by("-reference").first()
        next_index = 1
        if last_ticket and last_ticket.reference:
            try:
                next_index = int(last_ticket.reference.rsplit("-", 1)[-1]) + 1
            except (TypeError, ValueError):
                next_index = 1
        return f"{prefix}{next_index:05d}"

    @classmethod
    def normalize_process_status(cls, status):
        return cls.LEGACY_STATUS_MAP.get(status, status)

    @classmethod
    def can_transition(cls, current_status, next_status):
        current_status = cls.normalize_process_status(current_status)
        next_status = cls.normalize_process_status(next_status)
        return next_status in cls.PROCESS_TRANSITIONS.get(current_status, {current_status})


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
