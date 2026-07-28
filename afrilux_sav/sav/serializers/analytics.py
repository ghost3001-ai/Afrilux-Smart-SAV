from rest_framework import serializers

from ..models import (
    AIActionLog,
    AuditLog,
    KnowledgeArticle,
    PredictiveAlert,
    ProductTelemetry,
)


class ProductTelemetrySerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)

    class Meta:
        model = ProductTelemetry
        fields = [
            "id",
            "product",
            "product_name",
            "metric_name",
            "value",
            "unit",
            "source",
            "captured_at",
        ]


class PredictiveAlertSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    ticket_reference = serializers.CharField(source="ticket.reference", read_only=True)
    organization_name = serializers.CharField(source="product.organization.display_name", read_only=True)

    class Meta:
        model = PredictiveAlert
        fields = [
            "id",
            "organization_name",
            "product",
            "product_name",
            "ticket",
            "ticket_reference",
            "alert_type",
            "severity",
            "status",
            "title",
            "description",
            "metric_name",
            "metric_value",
            "predicted_failure_at",
            "recommended_action",
            "resolved_at",
            "created_at",
            "updated_at",
        ]


class KnowledgeArticleSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    equipment_category_name = serializers.CharField(source="equipment_category.name", read_only=True)
    organization_name = serializers.CharField(source="organization.display_name", read_only=True)

    class Meta:
        model = KnowledgeArticle
        fields = [
            "id",
            "organization",
            "organization_name",
            "title",
            "slug",
            "category",
            "equipment_category",
            "equipment_category_name",
            "business_domain",
            "product",
            "product_name",
            "summary",
            "content",
            "keywords",
            "status",
            "audience",
            "helpful_votes",
            "unhelpful_votes",
            "created_at",
            "updated_at",
        ]


class AIActionLogSerializer(serializers.ModelSerializer):
    ticket_reference = serializers.CharField(source="ticket.reference", read_only=True)
    product_name = serializers.CharField(source="product.name", read_only=True)
    approved_by_name = serializers.SerializerMethodField()
    organization_name = serializers.CharField(source="organization.display_name", read_only=True)

    class Meta:
        model = AIActionLog
        fields = [
            "id",
            "organization",
            "organization_name",
            "ticket",
            "ticket_reference",
            "product",
            "product_name",
            "action_type",
            "status",
            "confidence",
            "rationale",
            "input_snapshot",
            "output_snapshot",
            "approved_by",
            "approved_by_name",
            "created_at",
        ]

    def get_approved_by_name(self, obj):
        if not obj.approved_by:
            return None
        return str(obj.approved_by)


class AuditLogSerializer(serializers.ModelSerializer):
    actor_name = serializers.SerializerMethodField()
    organization_name = serializers.CharField(source="organization.display_name", read_only=True)

    class Meta:
        model = AuditLog
        fields = [
            "id",
            "organization",
            "organization_name",
            "actor",
            "actor_name",
            "actor_type",
            "action",
            "target_model",
            "target_id",
            "target_reference",
            "source_ip",
            "user_agent",
            "request_path",
            "http_method",
            "details",
            "created_at",
        ]

    def get_actor_name(self, obj):
        if not obj.actor:
            return None
        return str(obj.actor)
