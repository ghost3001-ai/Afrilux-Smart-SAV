from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.db import models
from django.utils import timezone

from .base import TimeStampedModel, _current_year
from .equipment import EquipmentCategory, Product, SparePart
from .organizations import Organization
from .tickets import Ticket
from .users import ClientSite, User


class MaintenanceProgram(TimeStampedModel):
    SERVICE_IT = "it"
    SERVICE_CFAO = "cfao"
    SERVICE_GENERATOR = "generator"
    SERVICE_COOLING = "cooling"
    SERVICE_OTHER = "other"

    SERVICE_CHOICES = (
        (SERVICE_IT, "SAV Informatique"),
        (SERVICE_CFAO, "SAV CFAO"),
        (SERVICE_GENERATOR, "SAV Groupe electrogene"),
        (SERVICE_COOLING, "SAV Froid & Climatisation"),
        (SERVICE_OTHER, "Autre service"),
    )

    PERIOD_MONTHLY = "monthly"
    PERIOD_QUARTERLY = "quarterly"

    PERIOD_CHOICES = (
        (PERIOD_MONTHLY, "Mensuelle"),
        (PERIOD_QUARTERLY, "Trimestrielle"),
    )

    FREQUENCY_DAILY = "daily"
    FREQUENCY_WEEKLY = "weekly"
    FREQUENCY_MONTHLY = "monthly"
    FREQUENCY_QUARTERLY = "quarterly"
    FREQUENCY_SEMIANNUAL = "semiannual"
    FREQUENCY_ANNUAL = "annual"
    FREQUENCY_CUSTOM = "custom"
    FREQUENCY_CHOICES = (
        (FREQUENCY_DAILY, "Quotidienne"), (FREQUENCY_WEEKLY, "Hebdomadaire"),
        (FREQUENCY_MONTHLY, "Mensuelle"), (FREQUENCY_QUARTERLY, "Trimestrielle"),
        (FREQUENCY_SEMIANNUAL, "Semestrielle"), (FREQUENCY_ANNUAL, "Annuelle"),
        (FREQUENCY_CUSTOM, "Personnalisée"),
    )
    TYPE_PREVENTIVE = "preventive"
    TYPE_INSPECTION = "inspection"
    TYPE_CALIBRATION = "calibration"
    TYPE_CONTROL = "control"
    TYPE_PERIODIC_CHECK = "periodic_check"
    MAINTENANCE_TYPE_CHOICES = (
        (TYPE_PREVENTIVE, "Préventive"), (TYPE_INSPECTION, "Inspection"),
        (TYPE_CALIBRATION, "Calibration"), (TYPE_CONTROL, "Contrôle"),
        (TYPE_PERIODIC_CHECK, "Vérification périodique"),
    )

    STATUS_DRAFT = "draft"
    STATUS_PUBLISHED = "published"
    STATUS_ARCHIVED = "archived"
    STATUS_SUSPENDED = "suspended"

    STATUS_CHOICES = (
        (STATUS_DRAFT, "Brouillon"),
        (STATUS_PUBLISHED, "Publie"),
        (STATUS_ARCHIVED, "Archive"),
        (STATUS_SUSPENDED, "Suspendu"),
    )

    organization = models.ForeignKey(
        Organization,
        on_delete=models.SET_NULL,
        related_name="maintenance_programs",
        null=True,
        blank=True,
    )
    responsible = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="maintenance_programs",
        limit_choices_to={"role__in": User.MANAGER_ROLES + User.ESCALATION_TARGET_ROLES},
        null=True,
        blank=True,
    )
    client = models.ForeignKey(User, on_delete=models.SET_NULL, related_name="maintenance_rules", null=True, blank=True, limit_choices_to={"role": User.ROLE_CLIENT})
    equipment = models.ForeignKey(Product, on_delete=models.SET_NULL, related_name="maintenance_rules", null=True, blank=True)
    site = models.ForeignKey(ClientSite, on_delete=models.SET_NULL, related_name="maintenance_programs", null=True, blank=True)
    technician = models.ForeignKey(User, on_delete=models.SET_NULL, related_name="scheduled_maintenance_programs", null=True, blank=True, limit_choices_to={"role__in": User.TECHNICIAN_SPACE_ROLES})
    team_members = models.ManyToManyField(User, related_name="maintenance_program_teams", blank=True, limit_choices_to={"role__in": User.TECHNICIAN_SPACE_ROLES})
    title = models.CharField(max_length=255, blank=True)
    reference = models.CharField(max_length=80, blank=True)
    description = models.TextField(blank=True)
    city = models.CharField(max_length=120, blank=True)
    overnight_stays = models.PositiveSmallIntegerField(default=0)
    service = models.CharField(max_length=20, choices=SERVICE_CHOICES, default=SERVICE_IT)
    period_type = models.CharField(max_length=20, choices=PERIOD_CHOICES, default=PERIOD_MONTHLY)
    month = models.PositiveSmallIntegerField(null=True, blank=True)
    quarter = models.PositiveSmallIntegerField(null=True, blank=True)
    year = models.PositiveSmallIntegerField(default=_current_year)
    maintenance_type = models.CharField(max_length=20, choices=MAINTENANCE_TYPE_CHOICES, default=TYPE_PREVENTIVE)
    priority = models.CharField(max_length=20, choices=Ticket.PRIORITY_CHOICES, default=Ticket.PRIORITY_NORMAL)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    frequency = models.CharField(max_length=20, choices=FREQUENCY_CHOICES, default=FREQUENCY_MONTHLY)
    frequency_interval = models.PositiveSmallIntegerField(default=1)
    custom_frequency_unit = models.CharField(max_length=12, choices=(("days", "jours"), ("weeks", "semaines"), ("months", "mois"), ("years", "années")), default="days")
    weekly_days = models.JSONField(default=list, blank=True)
    monthly_rule = models.CharField(max_length=40, blank=True)
    scheduled_time = models.TimeField(default=time(8, 0))
    estimated_duration_minutes = models.PositiveIntegerField(default=60)
    checklist = models.JSONField(default=list, blank=True)
    required_parts = models.ManyToManyField(SparePart, related_name="maintenance_programs", blank=True)
    notify_email = models.BooleanField(default=True)
    notify_sms = models.BooleanField(default=False)
    notify_internal = models.BooleanField(default=True)
    notification_days_before = models.PositiveSmallIntegerField(default=3)
    next_generation_date = models.DateField(null=True, blank=True)
    task_lines = models.JSONField(default=list, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-year", "-month", "-quarter", "-created_at"]

    def __str__(self):
        return self.title or f"{self.get_service_display()} {self.period_label}"

    @property
    def period_label(self):
        if self.period_type == self.PERIOD_QUARTERLY:
            return f"T{self.quarter or '-'} {self.year}"
        return f"{self.month or '-':>02} {self.year}" if self.month else f"{self.year}"

    def save(self, *args, **kwargs):
        if self.responsible_id and self.responsible.organization_id:
            self.organization = self.responsible.organization
        if not self.title:
            self.title = f"Programme {self.get_service_display()} - {self.period_label}"
        super().save(*args, **kwargs)

    @property
    def is_rule_based(self):
        return bool(self.equipment_id and self.client_id and self.technician_id and self.start_date)


class MaintenanceProgramPart(TimeStampedModel):
    program = models.ForeignKey(MaintenanceProgram, on_delete=models.CASCADE, related_name="planned_parts")
    spare_part = models.ForeignKey(SparePart, on_delete=models.SET_NULL, related_name="maintenance_program_part_lines", null=True, blank=True)
    quantity = models.PositiveIntegerField(default=1)
    observation = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"{self.program} - {self.spare_part or 'Pièce'}"


class MaintenanceTicket(TimeStampedModel):
    PERIOD_MONTHLY = "monthly"
    PERIOD_QUARTERLY = "quarterly"
    PERIOD_SEMIANNUAL = "semiannual"
    PERIOD_ANNUAL = "annual"

    PERIODICITY_CHOICES = (
        (PERIOD_MONTHLY, "Mensuelle"),
        (PERIOD_QUARTERLY, "Trimestrielle"),
        (PERIOD_SEMIANNUAL, "Semestrielle"),
        (PERIOD_ANNUAL, "Annuelle"),
    )

    STATUS_PLANNED = "planned"
    STATUS_NOTIFIED = "notified"
    STATUS_IN_PROGRESS = "in_progress"
    STATUS_DONE = "done"
    STATUS_POSTPONED = "postponed"
    STATUS_ANOMALY = "anomaly_detected"
    STATUS_CANCELLED = "cancelled"

    STATUS_CHOICES = (
        (STATUS_PLANNED, "Planifie"),
        (STATUS_NOTIFIED, "Notifie"),
        (STATUS_IN_PROGRESS, "En cours"),
        (STATUS_DONE, "Termine"),
        (STATUS_POSTPONED, "Reporte"),
        (STATUS_ANOMALY, "Anomalie detectee"),
        (STATUS_CANCELLED, "Annule"),
    )

    FINAL_STATUS_CHOICES = (
        (STATUS_DONE, "Termine"),
        (STATUS_POSTPONED, "Reporte"),
        (STATUS_ANOMALY, "Anomalie detectee"),
    )

    organization = models.ForeignKey(
        Organization,
        on_delete=models.SET_NULL,
        related_name="maintenance_tickets",
        null=True,
        blank=True,
    )
    program = models.ForeignKey(
        MaintenanceProgram,
        on_delete=models.SET_NULL,
        related_name="tickets",
        null=True,
        blank=True,
    )
    responsible = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="managed_maintenance_tickets",
        limit_choices_to={"role__in": User.MANAGER_ROLES + User.ESCALATION_TARGET_ROLES},
        null=True,
        blank=True,
    )
    technician = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="maintenance_tickets",
        limit_choices_to={"role__in": User.TECHNICIAN_SPACE_ROLES},
    )

    TYPE_PREVENTIVE = "preventive"
    TYPE_CORRECTIVE = "corrective"
    TYPE_PREDICTIVE = "predictive"
    TYPE_INSPECTION = "inspection"
    TYPE_CONTROL = "control"

    MAINTENANCE_TYPE_CHOICES = (
        (TYPE_PREVENTIVE, "Preventive"),
        (TYPE_CORRECTIVE, "Corrective"),
        (TYPE_PREDICTIVE, "Predictive"),
        (TYPE_INSPECTION, "Inspection"),
        (TYPE_CONTROL, "Controle"),
    )
    team_members = models.ManyToManyField(
        User,
        related_name="maintenance_team_tickets",
        limit_choices_to={"role__in": User.TECHNICIAN_SPACE_ROLES},
        blank=True,
    )
    client = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="client_maintenance_tickets",
        limit_choices_to={"role": User.ROLE_CLIENT},
    )
    products = models.ManyToManyField(Product, related_name="maintenance_tickets", blank=True)
    title = models.CharField(max_length=255)
    service = models.CharField(max_length=20, choices=MaintenanceProgram.SERVICE_CHOICES, default=MaintenanceProgram.SERVICE_IT)
    periodicity = models.CharField(max_length=20, choices=PERIODICITY_CHOICES, default=PERIOD_MONTHLY)
    maintenance_type = models.CharField(max_length=20, choices=MAINTENANCE_TYPE_CHOICES, default=TYPE_PREVENTIVE)
    scheduled_date = models.DateTimeField()
    planned_duration_minutes = models.PositiveIntegerField(default=60)
    status = models.CharField(max_length=24, choices=STATUS_CHOICES, default=STATUS_PLANNED)
    checklist = models.JSONField(default=list, blank=True)
    instructions = models.TextField(blank=True)
    priority = models.CharField(max_length=20, choices=Ticket.PRIORITY_CHOICES, default=Ticket.PRIORITY_NORMAL)
    location = models.CharField(max_length=255, blank=True)
    route = models.CharField(max_length=255, blank=True)
    overnight_stays = models.PositiveSmallIntegerField(default=0)
    call_date = models.DateTimeField(null=True, blank=True)
    system_tools = models.CharField(max_length=255, blank=True)
    equipment_brand = models.CharField(max_length=120, blank=True)
    equipment_type = models.CharField(max_length=120, blank=True)
    equipment_identifier = models.CharField(max_length=120, blank=True)
    intervention_reason = models.TextField(blank=True)
    estimated_cost = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    actual_cost = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    initial_scheduled_date = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    postponed_to = models.DateTimeField(null=True, blank=True)
    postponement_reason = models.TextField(blank=True)
    notified_at = models.DateTimeField(null=True, blank=True)
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    overdue_alerted_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancellation_reason = models.TextField(blank=True)
    anomaly_ticket = models.ForeignKey(
        Ticket,
        on_delete=models.SET_NULL,
        related_name="source_maintenance_tickets",
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ["scheduled_date", "priority", "id"]
        indexes = [
            models.Index(fields=["organization", "status", "scheduled_date"], name="sav_maint_org_status_date_idx"),
            models.Index(fields=["technician", "status", "scheduled_date"], name="sav_maint_tech_status_date_idx"),
            models.Index(fields=["client", "scheduled_date"], name="sav_maint_client_date_idx"),
        ]

    def __str__(self):
        return f"{self.title} - {self.client}"

    @property
    def type_label(self):
        return self.get_maintenance_type_display()

    @property
    def cmms_status(self):
        if self.status == self.STATUS_CANCELLED:
            return "cancelled"
        if self.is_late:
            return "late"
        if self.status == self.STATUS_IN_PROGRESS:
            return "in_progress"
        if self.status in {self.STATUS_DONE, self.STATUS_ANOMALY}:
            return "done"
        return "planned"

    @property
    def cmms_status_label(self):
        return {
            "planned": "Prevue",
            "in_progress": "En cours",
            "done": "Terminee",
            "cancelled": "Annulee",
            "late": "En retard",
        }[self.cmms_status]

    @property
    def technician_team_members(self):
        members = [self.technician] if self.technician_id else []
        for member in self.team_members.all():
            if not self.technician_id or member.id != self.technician_id:
                members.append(member)
        return members

    @property
    def technician_team_label(self):
        members = self.technician_team_members
        return ", ".join(str(member) for member in members) if members else "Non affecte"

    @property
    def appears_in_technician_pipeline(self):
        if self.status in {self.STATUS_NOTIFIED, self.STATUS_IN_PROGRESS, self.STATUS_POSTPONED}:
            return True
        return timezone.localtime(self.scheduled_date).date() <= timezone.localdate() + timedelta(days=3)

    @property
    def is_late(self):
        return self.status not in {
            self.STATUS_DONE,
            self.STATUS_ANOMALY,
            self.STATUS_CANCELLED,
        } and self.scheduled_date < timezone.now()

    @staticmethod
    def _coerce_datetime(value):
        if isinstance(value, datetime):
            if timezone.is_naive(value):
                return timezone.make_aware(value, timezone.get_current_timezone())
            return value
        if isinstance(value, date):
            return timezone.make_aware(
                datetime.combine(value, time.min),
                timezone.get_current_timezone(),
            )
        return value

    def save(self, *args, **kwargs):
        self.scheduled_date = self._coerce_datetime(self.scheduled_date)
        self.initial_scheduled_date = self._coerce_datetime(self.initial_scheduled_date)
        self.postponed_to = self._coerce_datetime(self.postponed_to)
        if self.program_id and self.program.organization_id:
            self.organization = self.program.organization
        elif self.client_id and self.client.organization_id:
            self.organization = self.client.organization
        elif self.technician_id and self.technician.organization_id:
            self.organization = self.technician.organization
        if self.program_id and not self.responsible_id:
            self.responsible = self.program.responsible
        if self.program_id and not self.service:
            self.service = self.program.service
        if self.scheduled_date and not self.initial_scheduled_date:
            self.initial_scheduled_date = self.scheduled_date
        super().save(*args, **kwargs)


class MaintenanceReport(TimeStampedModel):
    organization = models.ForeignKey(
        Organization,
        on_delete=models.SET_NULL,
        related_name="maintenance_reports",
        null=True,
        blank=True,
    )
    maintenance_ticket = models.OneToOneField(
        MaintenanceTicket,
        on_delete=models.CASCADE,
        related_name="report",
    )
    technician = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="maintenance_reports",
        limit_choices_to={"role__in": User.TECHNICIAN_SPACE_ROLES},
    )
    validated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="validated_maintenance_reports",
        null=True,
        blank=True,
    )
    validated_at = models.DateTimeField(null=True, blank=True)
    actual_started_at = models.DateTimeField()
    actual_finished_at = models.DateTimeField()
    checklist_completed = models.JSONField(default=list, blank=True)
    observations = models.TextField()
    work_to_plan = models.TextField(blank=True)
    parts_used = models.TextField(blank=True)
    parts_status = models.JSONField(default=dict, blank=True)
    intervention_types = models.JSONField(default=list, blank=True)
    anomaly_detected = models.BooleanField(default=False)
    photos = models.JSONField(default=list, blank=True)
    client_signed_by = models.CharField(max_length=255, blank=True)
    client_signature_file = models.FileField(upload_to="maintenance/signatures/%Y/%m/%d/", blank=True)
    report_pdf = models.FileField(upload_to="maintenance/reports/%Y/%m/%d/", blank=True)
    report_generated_at = models.DateTimeField(null=True, blank=True)
    final_status = models.CharField(
        max_length=24,
        choices=MaintenanceTicket.FINAL_STATUS_CHOICES,
        default=MaintenanceTicket.STATUS_DONE,
    )

    class Meta:
        ordering = ["-actual_finished_at", "-created_at"]

    def __str__(self):
        return f"{self.maintenance_ticket} - {self.technician}"

    def save(self, *args, **kwargs):
        if self.maintenance_ticket_id and self.maintenance_ticket.organization_id:
            self.organization = self.maintenance_ticket.organization
        elif self.technician_id and self.technician.organization_id:
            self.organization = self.technician.organization
        super().save(*args, **kwargs)


class MaintenancePartUsage(TimeStampedModel):
    organization = models.ForeignKey(
        Organization,
        on_delete=models.SET_NULL,
        related_name="maintenance_part_usages",
        null=True,
        blank=True,
    )
    report = models.ForeignKey(MaintenanceReport, on_delete=models.CASCADE, related_name="part_usages")
    spare_part = models.ForeignKey(SparePart, on_delete=models.SET_NULL, related_name="maintenance_usages", null=True, blank=True)
    name_snapshot = models.CharField(max_length=180, blank=True)
    reference_snapshot = models.CharField(max_length=120, blank=True)
    category_snapshot = models.CharField(max_length=120, blank=True)
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("1.00"))
    unit_snapshot = models.CharField(max_length=40, blank=True)
    note = models.TextField(blank=True)

    class Meta:
        ordering = ["created_at", "id"]

    def __str__(self):
        return f"{self.report.maintenance_ticket.title} - {self.reference_snapshot or self.name_snapshot}"

    def save(self, *args, **kwargs):
        if self.report_id and self.report.organization_id:
            self.organization = self.report.organization
        if self.spare_part_id:
            if not self.name_snapshot:
                self.name_snapshot = self.spare_part.name
            if not self.reference_snapshot:
                self.reference_snapshot = self.spare_part.reference
            if not self.category_snapshot:
                self.category_snapshot = self.spare_part.category
            if not self.unit_snapshot:
                self.unit_snapshot = self.spare_part.unit
            if self.spare_part.organization_id and not self.organization_id:
                self.organization = self.spare_part.organization
        super().save(*args, **kwargs)


class MaintenanceReportPhoto(TimeStampedModel):
    organization = models.ForeignKey(
        Organization,
        on_delete=models.SET_NULL,
        related_name="maintenance_report_photos",
        null=True,
        blank=True,
    )
    report = models.ForeignKey(MaintenanceReport, on_delete=models.CASCADE, related_name="photo_files")
    uploaded_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="maintenance_report_photos",
        null=True,
        blank=True,
    )
    file = models.FileField(upload_to="maintenance/photos/%Y/%m/%d/")
    note = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["created_at", "id"]

    def __str__(self):
        return f"{self.report.maintenance_ticket.title} - photo {self.pk or 'N/A'}"

    def save(self, *args, **kwargs):
        if self.report_id and self.report.organization_id:
            self.organization = self.report.organization
        elif self.uploaded_by_id and self.uploaded_by.organization_id:
            self.organization = self.uploaded_by.organization
        super().save(*args, **kwargs)


class ChecklistTemplate(TimeStampedModel):
    organization = models.ForeignKey(
        Organization,
        on_delete=models.SET_NULL,
        related_name="checklist_templates",
        null=True,
        blank=True,
    )
    service = models.CharField(max_length=20, choices=MaintenanceProgram.SERVICE_CHOICES, default=MaintenanceProgram.SERVICE_IT)
    equipment_category = models.ForeignKey(
        EquipmentCategory,
        on_delete=models.SET_NULL,
        related_name="checklist_templates",
        null=True,
        blank=True,
    )
    name = models.CharField(max_length=255)
    checklist = models.JSONField(default=list, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["service", "name"]
        unique_together = [("organization", "service", "equipment_category", "name")]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if self.equipment_category_id and self.equipment_category.organization_id and not self.organization_id:
            self.organization = self.equipment_category.organization
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
