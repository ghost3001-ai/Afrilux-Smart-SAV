from decimal import Decimal

from django.db import models
from django.utils import timezone

from .base import TimeStampedModel, _generate_unique_slug
from .organizations import Organization
from .users import ClientSite, User


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


class SparePart(TimeStampedModel):
    organization = models.ForeignKey(
        Organization,
        on_delete=models.SET_NULL,
        related_name="spare_parts",
        null=True,
        blank=True,
    )
    name = models.CharField(max_length=180)
    reference = models.CharField(max_length=120)
    category = models.CharField(max_length=120, blank=True)
    equipment_category = models.ForeignKey(
        EquipmentCategory,
        on_delete=models.SET_NULL,
        related_name="spare_parts",
        null=True,
        blank=True,
    )
    description = models.TextField(blank=True)
    unit = models.CharField(max_length=40, default="piece")
    stock_quantity = models.PositiveIntegerField(default=0)
    minimum_stock = models.PositiveIntegerField(default=0)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    supplier = models.CharField(max_length=180, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["category", "name", "reference"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "reference"],
                name="sav_sparepart_unique_reference_per_organization",
            ),
        ]

    def __str__(self):
        return f"{self.reference} - {self.name}"

    def save(self, *args, **kwargs):
        if self.equipment_category_id and self.equipment_category.organization_id and not self.organization_id:
            self.organization = self.equipment_category.organization
        super().save(*args, **kwargs)

    @property
    def is_low_stock(self):
        return self.stock_quantity <= self.minimum_stock


class Product(TimeStampedModel):
    STATUS_OPERATIONAL = "operational"
    STATUS_BROKEN = "broken"
    STATUS_MAINTENANCE = "maintenance"
    STATUS_OUT_OF_SERVICE = "out_of_service"

    STATUS_ACTIVE = "active"
    STATUS_IN_SERVICE = "in_service"
    STATUS_REPLACED = "replaced"
    STATUS_RETIRED = "retired"

    LEGACY_STATUS_MAP = {
        STATUS_ACTIVE: STATUS_OPERATIONAL,
        STATUS_IN_SERVICE: STATUS_OPERATIONAL,
        STATUS_REPLACED: STATUS_OUT_OF_SERVICE,
        STATUS_RETIRED: STATUS_OUT_OF_SERVICE,
    }

    STATUS_CHOICES = (
        (STATUS_OPERATIONAL, "Operationnel"),
        (STATUS_BROKEN, "En panne"),
        (STATUS_MAINTENANCE, "En maintenance"),
        (STATUS_OUT_OF_SERVICE, "Hors service"),
    )

    LOCATION_INSTALLED = "installed"
    LOCATION_WORKSHOP = "workshop"
    LOCATION_TRANSIT = "transit"
    LOCATION_STORAGE = "storage"

    LOCATION_STATUS_CHOICES = (
        (LOCATION_INSTALLED, "Installe chez le client"),
        (LOCATION_WORKSHOP, "En atelier"),
        (LOCATION_TRANSIT, "En transit"),
        (LOCATION_STORAGE, "En stockage"),
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
    site = models.ForeignKey(
        ClientSite,
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
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_OPERATIONAL)
    location_status = models.CharField(max_length=20, choices=LOCATION_STATUS_CHOICES, default=LOCATION_INSTALLED)
    current_location_notes = models.TextField(blank=True)
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
        indexes = [
            models.Index(fields=["organization", "status"], name="sav_product_org_status_idx"),
            models.Index(fields=["client", "status"], name="sav_product_client_status_idx"),
            models.Index(fields=["organization", "warranty_end"], name="sav_product_org_warranty_idx"),
        ]

    def __str__(self):
        return f"{self.name} ({self.serial_number})"

    def save(self, *args, **kwargs):
        self.status = self.LEGACY_STATUS_MAP.get(self.status, self.status)
        if self.site_id:
            self.client = self.site.client
            if self.site.organization_id:
                self.organization = self.site.organization
            if self.site.address and not self.installation_address:
                self.installation_address = self.site.address
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


class EquipmentLocationHistory(TimeStampedModel):
    organization = models.ForeignKey(
        Organization,
        on_delete=models.SET_NULL,
        related_name="equipment_location_history",
        null=True,
        blank=True,
    )
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="location_history")
    from_client = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="equipment_moves_from",
        null=True,
        blank=True,
        limit_choices_to={"role": User.ROLE_CLIENT},
    )
    from_site = models.ForeignKey(
        ClientSite,
        on_delete=models.SET_NULL,
        related_name="equipment_moves_from",
        null=True,
        blank=True,
    )
    from_location = models.CharField(max_length=255, blank=True)
    from_location_status = models.CharField(max_length=20, choices=Product.LOCATION_STATUS_CHOICES, blank=True)
    to_client = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="equipment_moves_to",
        null=True,
        blank=True,
        limit_choices_to={"role": User.ROLE_CLIENT},
    )
    to_site = models.ForeignKey(
        ClientSite,
        on_delete=models.SET_NULL,
        related_name="equipment_moves_to",
        null=True,
        blank=True,
    )
    to_location = models.CharField(max_length=255, blank=True)
    to_location_status = models.CharField(max_length=20, choices=Product.LOCATION_STATUS_CHOICES, default=Product.LOCATION_INSTALLED)
    moved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="equipment_location_moves",
        null=True,
        blank=True,
    )
    reason = models.TextField(blank=True)
    moved_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-moved_at", "-created_at"]

    def __str__(self):
        return f"{self.product.serial_number} -> {self.to_location_status}"

    def save(self, *args, **kwargs):
        if self.product_id and self.product.organization_id:
            self.organization = self.product.organization
        super().save(*args, **kwargs)
