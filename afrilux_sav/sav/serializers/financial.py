from rest_framework import serializers

from ..models import AccountCredit, FinancialTransaction, OfferRecommendation


class AccountCreditInlineSerializer(serializers.ModelSerializer):
    client_name = serializers.SerializerMethodField()
    executed_by_name = serializers.SerializerMethodField()
    organization_name = serializers.CharField(source="organization.display_name", read_only=True)
    ticket_reference = serializers.CharField(source="ticket.reference", read_only=True)

    class Meta:
        model = AccountCredit
        fields = [
            "id",
            "organization",
            "organization_name",
            "ticket",
            "ticket_reference",
            "client",
            "client_name",
            "executed_by",
            "executed_by_name",
            "amount",
            "currency",
            "reason",
            "note",
            "external_reference",
            "status",
            "executed_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "organization",
            "organization_name",
            "ticket_reference",
            "client",
            "client_name",
            "executed_by",
            "executed_by_name",
            "status",
            "executed_at",
            "created_at",
            "updated_at",
        ]

    def get_client_name(self, obj):
        return str(obj.client)

    def get_executed_by_name(self, obj):
        if not obj.executed_by:
            return None
        return str(obj.executed_by)


class AccountCreditSerializer(AccountCreditInlineSerializer):
    class Meta(AccountCreditInlineSerializer.Meta):
        read_only_fields = AccountCreditInlineSerializer.Meta.read_only_fields


class FinancialTransactionSerializer(serializers.ModelSerializer):
    client_name = serializers.SerializerMethodField()
    organization_name = serializers.CharField(source="organization.display_name", read_only=True)
    signed_amount = serializers.SerializerMethodField()

    class Meta:
        model = FinancialTransaction
        fields = [
            "id",
            "organization",
            "organization_name",
            "client",
            "client_name",
            "external_reference",
            "provider_reference",
            "transaction_type",
            "ledger_side",
            "amount",
            "signed_amount",
            "currency",
            "status",
            "description",
            "metadata",
            "occurred_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["organization", "organization_name", "client_name", "signed_amount", "created_at", "updated_at"]

    def get_client_name(self, obj):
        return str(obj.client)

    def get_signed_amount(self, obj):
        return str(obj.signed_amount)


class OfferRecommendationSerializer(serializers.ModelSerializer):
    client_name = serializers.SerializerMethodField()
    product_name = serializers.CharField(source="product.name", read_only=True)
    ticket_reference = serializers.CharField(source="ticket.reference", read_only=True)
    organization_name = serializers.CharField(source="organization.display_name", read_only=True)

    class Meta:
        model = OfferRecommendation
        fields = [
            "id",
            "organization",
            "organization_name",
            "client",
            "client_name",
            "ticket",
            "ticket_reference",
            "product",
            "product_name",
            "offer_type",
            "title",
            "description",
            "rationale",
            "price",
            "status",
            "valid_until",
            "created_at",
        ]

    def get_client_name(self, obj):
        return str(obj.client)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        client = attrs.get("client") or getattr(self.instance, "client", None)
        product = attrs.get("product") or getattr(self.instance, "product", None)
        ticket = attrs.get("ticket") or getattr(self.instance, "ticket", None)
        if client and product and product.client_id != client.id:
            raise serializers.ValidationError("Le produit selectionne n'appartient pas a ce client.")
        if client and ticket and ticket.client_id != client.id:
            raise serializers.ValidationError("Le ticket selectionne n'appartient pas a ce client.")
        return attrs
