from django.db import models

from .base import TimeStampedModel, _generate_unique_slug


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
    personal_data_access_logging_enabled = models.BooleanField(
        default=True,
        help_text="Journalise les consultations des fiches clients/equipements contenant des donnees personnelles.",
    )
    ticket_retention_years = models.PositiveSmallIntegerField(
        default=5,
        help_text="Duree de conservation active des tickets clos avant archivage logique.",
    )
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


class Agency(TimeStampedModel):
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="agencies",
    )
    name = models.CharField(max_length=180)
    code = models.SlugField(max_length=80, blank=True)
    city = models.CharField(max_length=120, blank=True)
    region = models.CharField(max_length=120, blank=True)
    address = models.CharField(max_length=255, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["organization__name", "city", "name"]
        unique_together = [("organization", "code")]

    def __str__(self):
        return f"{self.name} - {self.city}" if self.city else self.name

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = _generate_unique_slug(self.__class__, self.name, self.pk, field_name="code")
        super().save(*args, **kwargs)
