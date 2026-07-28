from rest_framework import serializers

from ..models import Agency, Organization


class OrganizationSerializer(serializers.ModelSerializer):
    display_name = serializers.CharField(read_only=True)
    initials = serializers.CharField(read_only=True)

    class Meta:
        model = Organization
        fields = [
            "id",
            "name",
            "slug",
            "brand_name",
            "display_name",
            "initials",
            "portal_tagline",
            "primary_color",
            "accent_color",
            "support_email",
            "support_phone",
            "headquarters_address",
            "city",
            "country",
            "reporting_emails",
            "is_active",
            "created_at",
            "updated_at",
        ]


class PublicOrganizationSerializer(serializers.ModelSerializer):
    display_name = serializers.CharField(read_only=True)

    class Meta:
        model = Organization
        fields = [
            "id",
            "slug",
            "display_name",
            "portal_tagline",
            "primary_color",
            "accent_color",
            "support_email",
            "support_phone",
            "city",
            "country",
        ]


class AgencySerializer(serializers.ModelSerializer):
    organization_name = serializers.CharField(source="organization.display_name", read_only=True)

    class Meta:
        model = Agency
        fields = [
            "id",
            "organization",
            "organization_name",
            "name",
            "code",
            "city",
            "region",
            "address",
            "phone",
            "email",
            "is_active",
            "created_at",
            "updated_at",
        ]
