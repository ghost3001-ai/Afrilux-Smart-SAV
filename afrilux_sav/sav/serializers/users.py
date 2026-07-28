from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from ..models import ClientContact, ClientSite, Organization, User
from ..services import generate_client_username, provision_client_account


class ClientContactSerializer(serializers.ModelSerializer):
    client_name = serializers.SerializerMethodField()
    organization_name = serializers.CharField(source="organization.display_name", read_only=True)

    class Meta:
        model = ClientContact
        fields = [
            "id",
            "organization",
            "organization_name",
            "client",
            "client_name",
            "first_name",
            "last_name",
            "job_title",
            "phone",
            "email",
            "is_primary",
            "note",
            "created_at",
            "updated_at",
        ]

    def get_client_name(self, obj):
        return str(obj.client)


class ClientSiteSerializer(serializers.ModelSerializer):
    client_name = serializers.SerializerMethodField()
    organization_name = serializers.CharField(source="organization.display_name", read_only=True)
    agency_name = serializers.CharField(source="agency.name", read_only=True)

    class Meta:
        model = ClientSite
        fields = [
            "id",
            "organization",
            "organization_name",
            "client",
            "client_name",
            "agency",
            "agency_name",
            "name",
            "code",
            "address",
            "city",
            "region",
            "gps_latitude",
            "gps_longitude",
            "is_primary",
            "notes",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["organization", "organization_name", "client_name", "agency_name", "created_at", "updated_at"]

    def get_client_name(self, obj):
        return str(obj.client)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        client = attrs.get("client") or getattr(self.instance, "client", None)
        agency = attrs.get("agency") or getattr(self.instance, "agency", None)
        if agency and client and client.organization_id and agency.organization_id != client.organization_id:
            raise serializers.ValidationError({"agency": "L'agence appartient a une autre organisation que le client."})
        return attrs


class UserSerializer(serializers.ModelSerializer):
    organization_name = serializers.CharField(source="organization.display_name", read_only=True)
    organization_slug = serializers.CharField(source="organization.slug", read_only=True)
    agency_name = serializers.CharField(source="agency.name", read_only=True)
    organization_primary_color = serializers.CharField(source="organization.primary_color", read_only=True)
    organization_accent_color = serializers.CharField(source="organization.accent_color", read_only=True)
    organization_portal_tagline = serializers.CharField(source="organization.portal_tagline", read_only=True)
    organization_support_email = serializers.CharField(source="organization.support_email", read_only=True)
    organization_support_phone = serializers.CharField(source="organization.support_phone", read_only=True)
    account_balance = serializers.SerializerMethodField()
    contacts = ClientContactSerializer(many=True, read_only=True)
    password = serializers.CharField(write_only=True, required=False, allow_blank=False)

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "first_name",
            "last_name",
            "email",
            "organization",
            "organization_name",
            "organization_slug",
            "agency",
            "agency_name",
            "organization_primary_color",
            "organization_accent_color",
            "organization_portal_tagline",
            "organization_support_email",
            "organization_support_phone",
            "role",
            "phone",
            "professional_email",
            "company_name",
            "is_active",
            "is_verified",
            "address",
            "sector",
            "tax_identifier",
            "client_type",
            "client_status",
            "specialties",
            "primary_city",
            "primary_region",
            "weekly_availability",
            "technician_status",
            "account_balance",
            "contacts",
            "password",
        ]
        extra_kwargs = {
            "username": {"required": False},
            "email": {"required": False},
            "role": {"label": "Fonction"},
        }

    def get_account_balance(self, obj):
        return str(obj.account_balance)

    def validate_password(self, value):
        validate_password(value)
        return value

    def validate(self, attrs):
        attrs = super().validate(attrs)
        email = (attrs.get("email") or getattr(self.instance, "email", "") or "").strip().lower()
        role = attrs.get("role") or getattr(self.instance, "role", User.ROLE_CLIENT)
        if role == User.ROLE_FIELD_TECHNICIAN:
            role = User.ROLE_TECHNICIAN
            attrs["role"] = role
        organization = attrs.get("organization") or getattr(self.instance, "organization", None)
        agency = attrs.get("agency") or getattr(self.instance, "agency", None)
        professional_email = (attrs.get("professional_email") or "").strip().lower()
        password = attrs.get("password", "")
        client_type = (attrs.get("client_type") or getattr(self.instance, "client_type", "") or "").strip().lower()
        company_name = (attrs.get("company_name") or "").strip()

        if self.instance is None and not password:
            raise serializers.ValidationError({"password": "Le mot de passe est obligatoire a la creation."})
        if self.instance is None and not attrs.get("username") and not email:
            raise serializers.ValidationError({"username": "Renseignez au minimum un identifiant ou un email."})

        if email:
            attrs["email"] = email
            existing = User.objects.filter(email__iexact=email).order_by("id")
            if self.instance is not None:
                existing = existing.exclude(pk=self.instance.pk)
            if existing.exists():
                raise serializers.ValidationError({"email": "Cet email est deja utilise par un autre compte."})
        if professional_email:
            attrs["professional_email"] = professional_email
        if not attrs.get("username") and email:
            attrs["username"] = generate_client_username(email)
        if role == User.ROLE_CLIENT:
            if client_type and client_type != "enterprise":
                attrs["company_name"] = ""
            elif organization and not company_name and not getattr(self.instance, "company_name", ""):
                attrs["company_name"] = organization.display_name
        if agency and organization and agency.organization_id != organization.id:
            raise serializers.ValidationError({"agency": "L'agence selectionnee appartient a une autre organisation."})
        if agency and not organization:
            attrs["organization"] = agency.organization
        return attrs

    def create(self, validated_data):
        password = validated_data.pop("password", "")
        user = User(**validated_data)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save()
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop("password", "")
        for field, value in validated_data.items():
            setattr(instance, field, value)
        if password:
            instance.set_password(password)
        instance.save()
        return instance


class ClientRegistrationSerializer(serializers.Serializer):
    organization = serializers.PrimaryKeyRelatedField(queryset=Organization.objects.filter(is_active=True).order_by("name"))
    first_name = serializers.CharField(max_length=150)
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    email = serializers.EmailField()
    phone = serializers.CharField(max_length=20, required=False, allow_blank=True)
    company_name = serializers.CharField(max_length=255, required=False, allow_blank=True)
    client_type = serializers.ChoiceField(choices=[choice[0] for choice in User._meta.get_field("client_type").choices], required=False)
    sector = serializers.CharField(max_length=120, required=False, allow_blank=True)
    tax_identifier = serializers.CharField(max_length=120, required=False, allow_blank=True)
    address = serializers.CharField(required=False, allow_blank=True)
    password = serializers.CharField(write_only=True, min_length=8)
    password_confirm = serializers.CharField(write_only=True, min_length=8)

    def validate_email(self, value):
        return value.strip().lower()

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if attrs["password"] != attrs["password_confirm"]:
            raise serializers.ValidationError({"password_confirm": "Les mots de passe ne correspondent pas."})
        validate_password(attrs["password"])
        email = (attrs.get("email") or "").strip().lower()
        organization = attrs.get("organization")
        client_type = (attrs.get("client_type") or "").strip().lower()
        company_name = (attrs.get("company_name") or "").strip()
        if client_type == "enterprise" and not company_name:
            raise serializers.ValidationError({"company_name": "Le champ Entreprise est obligatoire pour ce type de client."})
        if client_type and client_type != "enterprise":
            attrs["company_name"] = ""
        existing = User.objects.filter(email__iexact=email).select_related("organization").order_by("id").first()
        if existing:
            if existing.role != User.ROLE_CLIENT:
                raise serializers.ValidationError({"email": "Cet email est deja utilise par un compte interne."})
            if (
                existing.organization_id
                and organization
                and existing.organization_id != organization.id
                and existing.organization.slug != "contacts-entrants"
            ):
                raise serializers.ValidationError({"email": "Cet email est deja rattache a une autre organisation."})
            if existing.has_usable_password():
                raise serializers.ValidationError({"email": "Un compte client existe deja avec cet email."})
        return attrs

    def create(self, validated_data):
        try:
            user, created = provision_client_account(
                organization=validated_data["organization"],
                email=validated_data["email"],
                password=validated_data["password"],
                first_name=validated_data["first_name"],
                last_name=validated_data.get("last_name", ""),
                phone=validated_data.get("phone", ""),
                company_name=validated_data.get("company_name", ""),
                client_type=validated_data.get("client_type", ""),
                sector=validated_data.get("sector", ""),
                tax_identifier=validated_data.get("tax_identifier", ""),
                address=validated_data.get("address", ""),
            )
        except ValueError as exc:
            raise serializers.ValidationError({"detail": str(exc)}) from exc
        self.context["account_created"] = created
        return user
