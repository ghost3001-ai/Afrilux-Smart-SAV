from rest_framework import serializers

from ..models import (
    EquipmentCategory,
    EquipmentLocationHistory,
    Product,
    SparePart,
)


class EquipmentCategorySerializer(serializers.ModelSerializer):
    organization_name = serializers.CharField(source="organization.display_name", read_only=True)

    class Meta:
        model = EquipmentCategory
        fields = [
            "id",
            "organization",
            "organization_name",
            "name",
            "code",
            "description",
            "is_active",
            "created_at",
            "updated_at",
        ]


class SparePartSerializer(serializers.ModelSerializer):
    organization_name = serializers.CharField(source="organization.display_name", read_only=True)
    equipment_category_name = serializers.CharField(source="equipment_category.name", read_only=True)

    class Meta:
        model = SparePart
        fields = [
            "id",
            "organization",
            "organization_name",
            "name",
            "reference",
            "category",
            "equipment_category",
            "equipment_category_name",
            "description",
            "unit",
            "is_active",
            "created_at",
            "updated_at",
        ]


class ProductSerializer(serializers.ModelSerializer):
    client_name = serializers.SerializerMethodField()
    organization_name = serializers.CharField(source="organization.display_name", read_only=True)
    equipment_category_name = serializers.CharField(source="equipment_category.name", read_only=True)
    site_name = serializers.CharField(source="site.name", read_only=True)
    is_under_warranty = serializers.BooleanField(read_only=True)

    class Meta:
        model = Product
        fields = [
            "id",
            "organization",
            "organization_name",
            "client",
            "client_name",
            "equipment_category",
            "equipment_category_name",
            "site",
            "site_name",
            "name",
            "sku",
            "serial_number",
            "equipment_type",
            "brand",
            "model_reference",
            "purchase_date",
            "installation_date",
            "warranty_end",
            "is_under_warranty",
            "installation_address",
            "detailed_location",
            "status",
            "location_status",
            "current_location_notes",
            "iot_enabled",
            "health_score",
            "counter_total",
            "counter_color",
            "counter_bw",
            "equipment_photo",
            "contract_reference",
            "notes",
            "created_at",
            "updated_at",
        ]

    def get_client_name(self, obj):
        return str(obj.client)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        client = attrs.get("client") or getattr(self.instance, "client", None)
        organization = attrs.get("organization") or getattr(self.instance, "organization", None)
        equipment_category = attrs.get("equipment_category") or getattr(self.instance, "equipment_category", None)
        site = attrs.get("site") or getattr(self.instance, "site", None)
        if client and organization and client.organization_id != organization.id:
            raise serializers.ValidationError("Le client selectionne n'appartient pas a cette organisation.")
        if equipment_category and organization and equipment_category.organization_id and equipment_category.organization_id != organization.id:
            raise serializers.ValidationError("La categorie d'equipement selectionnee appartient a une autre organisation.")
        if site and client and site.client_id != client.id:
            raise serializers.ValidationError({"site": "Le site selectionne appartient a un autre client."})
        if site and organization and site.organization_id and site.organization_id != organization.id:
            raise serializers.ValidationError({"site": "Le site selectionne appartient a une autre organisation."})
        return attrs


class EquipmentLocationHistorySerializer(serializers.ModelSerializer):
    product_reference = serializers.CharField(source="product.serial_number", read_only=True)
    organization_name = serializers.CharField(source="organization.display_name", read_only=True)
    from_site_name = serializers.CharField(source="from_site.name", read_only=True)
    to_site_name = serializers.CharField(source="to_site.name", read_only=True)
    moved_by_name = serializers.SerializerMethodField()

    class Meta:
        model = EquipmentLocationHistory
        fields = [
            "id",
            "organization",
            "organization_name",
            "product",
            "product_reference",
            "from_client",
            "from_site",
            "from_site_name",
            "from_location",
            "from_location_status",
            "to_client",
            "to_site",
            "to_site_name",
            "to_location",
            "to_location_status",
            "moved_by",
            "moved_by_name",
            "reason",
            "moved_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "organization",
            "organization_name",
            "product_reference",
            "from_site_name",
            "to_site_name",
            "moved_by_name",
            "created_at",
            "updated_at",
        ]

    def get_moved_by_name(self, obj):
        return str(obj.moved_by) if obj.moved_by else None
