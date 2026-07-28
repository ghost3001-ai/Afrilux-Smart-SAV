from decimal import Decimal

from django.db import models
from django.utils import timezone

from .base import TimeStampedModel
from .organizations import Organization
from .users import User
from .tickets import Ticket


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
        (TYPE_PREMIUM_SUPPORT, "Assistance premium"),
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
    product = models.ForeignKey("Product", on_delete=models.SET_NULL, related_name="offers", null=True, blank=True)
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
