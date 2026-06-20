from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from .file_validation import MAX_TICKET_ATTACHMENT_BYTES, validate_ticket_attachment_file
from .models import (
    AccountCredit,
    Agency,
    AIActionLog,
    AuditLog,
    AutomationRule,
    ChecklistTemplate,
    ClientContact,
    ClientSite,
    DeviceRegistration,
    EquipmentCategory,
    EquipmentLocationHistory,
    FinancialTransaction,
    GeneratedReport,
    Intervention,
    InterventionMedia,
    InterventionPartUsage,
    KnowledgeArticle,
    MaintenancePartUsage,
    MaintenanceProgram,
    MaintenanceReport,
    MaintenanceReportPhoto,
    MaintenanceTicket,
    Message,
    Notification,
    OfflineSyncOperation,
    Organization,
    OfferRecommendation,
    PredictiveAlert,
    Product,
    ProductTelemetry,
    SlaRule,
    SparePart,
    SupportSession,
    TicketAttachment,
    TicketAssignment,
    TicketFeedback,
    Ticket,
    User,
    WorkflowExecution,
)
from .services import (
    ESCALATION_TARGET_CFAO_MANAGER,
    ESCALATION_TARGET_CFAO_WORKS,
    ESCALATION_TARGET_CHIEF_TECHNICIAN,
    ESCALATION_TARGET_EXPERT_THEN_HEAD_SAV,
    ESCALATION_TARGET_HEAD_SAV,
    ESCALATION_TARGET_SUPERVISOR,
    generate_client_username,
    is_admin_user,
    provision_client_account,
    scope_message_queryset,
)


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


class TicketAssignmentSerializer(serializers.ModelSerializer):
    ticket_reference = serializers.CharField(source="ticket.reference", read_only=True)
    technician_name = serializers.SerializerMethodField()
    assigned_by_name = serializers.SerializerMethodField()
    organization_name = serializers.CharField(source="organization.display_name", read_only=True)

    class Meta:
        model = TicketAssignment
        fields = [
            "id",
            "organization",
            "organization_name",
            "ticket",
            "ticket_reference",
            "technician",
            "technician_name",
            "assigned_by",
            "assigned_by_name",
            "assigned_at",
            "released_at",
            "status",
            "note",
            "created_at",
            "updated_at",
        ]

    def get_technician_name(self, obj):
        return str(obj.technician)

    def get_assigned_by_name(self, obj):
        if not obj.assigned_by:
            return None
        return str(obj.assigned_by)


class SlaRuleSerializer(serializers.ModelSerializer):
    organization_name = serializers.CharField(source="organization.display_name", read_only=True)
    priority_label = serializers.CharField(source="get_priority_display", read_only=True)

    class Meta:
        model = SlaRule
        fields = [
            "id",
            "organization",
            "organization_name",
            "priority",
            "priority_label",
            "response_deadline_minutes",
            "resolution_deadline_hours",
            "is_active",
            "created_at",
            "updated_at",
        ]


class GeneratedReportSerializer(serializers.ModelSerializer):
    organization_name = serializers.CharField(source="organization.display_name", read_only=True)
    generated_by_name = serializers.SerializerMethodField()
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = GeneratedReport
        fields = [
            "id",
            "organization",
            "organization_name",
            "generated_by",
            "generated_by_name",
            "report_type",
            "export_format",
            "period_label",
            "payload",
            "archive_file",
            "file_url",
            "sent_to",
            "created_at",
            "updated_at",
        ]

    def get_generated_by_name(self, obj):
        if not obj.generated_by:
            return None
        return str(obj.generated_by)

    def get_file_url(self, obj):
        if not obj.archive_file:
            return ""
        request = self.context.get("request")
        if request:
            return request.build_absolute_uri(obj.archive_file.url)
        return obj.archive_file.url


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
            "sms_phone",
            "whatsapp_phone",
            "professional_email",
            "preferred_language",
            "notification_whatsapp_enabled",
            "notification_sms_enabled",
            "notification_email_enabled",
            "notification_push_enabled",
            "notification_do_not_disturb_start",
            "notification_do_not_disturb_end",
            "notification_daily_limit",
            "notification_min_interval_minutes",
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


class ChecklistTemplateSerializer(serializers.ModelSerializer):
    organization_name = serializers.CharField(source="organization.display_name", read_only=True)
    equipment_category_name = serializers.CharField(source="equipment_category.name", read_only=True)

    class Meta:
        model = ChecklistTemplate
        fields = [
            "id",
            "organization",
            "organization_name",
            "service",
            "equipment_category",
            "equipment_category_name",
            "name",
            "checklist",
            "is_active",
            "created_at",
            "updated_at",
        ]


class MaintenanceReportPhotoSerializer(serializers.ModelSerializer):
    uploaded_by_name = serializers.SerializerMethodField()
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = MaintenanceReportPhoto
        fields = ["id", "report", "uploaded_by", "uploaded_by_name", "file", "file_url", "note", "created_at", "updated_at"]
        read_only_fields = ["uploaded_by", "uploaded_by_name", "file_url", "created_at", "updated_at"]

    def get_uploaded_by_name(self, obj):
        return str(obj.uploaded_by) if obj.uploaded_by else None

    def get_file_url(self, obj):
        request = self.context.get("request")
        if not obj.file:
            return ""
        url = obj.file.url
        return request.build_absolute_uri(url) if request else url


class MaintenanceReportSerializer(serializers.ModelSerializer):
    technician_name = serializers.SerializerMethodField()
    validated_by_name = serializers.SerializerMethodField()
    ticket_title = serializers.CharField(source="maintenance_ticket.title", read_only=True)
    organization_name = serializers.CharField(source="organization.display_name", read_only=True)
    report_pdf_url = serializers.SerializerMethodField()
    photo_files = MaintenanceReportPhotoSerializer(many=True, read_only=True)

    class Meta:
        model = MaintenanceReport
        fields = [
            "id",
            "organization",
            "organization_name",
            "maintenance_ticket",
            "ticket_title",
            "technician",
            "technician_name",
            "validated_by",
            "validated_by_name",
            "validated_at",
            "actual_started_at",
            "actual_finished_at",
            "checklist_completed",
            "observations",
            "parts_used",
            "anomaly_detected",
            "photos",
            "photo_files",
            "client_signed_by",
            "client_signature_file",
            "report_pdf",
            "report_pdf_url",
            "report_generated_at",
            "final_status",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "organization",
            "organization_name",
            "technician_name",
            "validated_by",
            "validated_by_name",
            "validated_at",
            "ticket_title",
            "report_pdf_url",
            "photo_files",
            "report_generated_at",
            "created_at",
            "updated_at",
        ]

    def get_technician_name(self, obj):
        return str(obj.technician)

    def get_validated_by_name(self, obj):
        return str(obj.validated_by) if obj.validated_by else None

    def get_report_pdf_url(self, obj):
        request = self.context.get("request")
        if not obj.report_pdf:
            return ""
        url = obj.report_pdf.url
        return request.build_absolute_uri(url) if request else url


class MaintenancePartUsageSerializer(serializers.ModelSerializer):
    spare_part_label = serializers.SerializerMethodField()
    organization_name = serializers.CharField(source="organization.display_name", read_only=True)

    class Meta:
        model = MaintenancePartUsage
        fields = [
            "id",
            "organization",
            "organization_name",
            "report",
            "spare_part",
            "spare_part_label",
            "name_snapshot",
            "reference_snapshot",
            "category_snapshot",
            "quantity",
            "unit_snapshot",
            "note",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["organization", "organization_name", "spare_part_label", "created_at", "updated_at"]

    def get_spare_part_label(self, obj):
        return str(obj.spare_part) if obj.spare_part else ""


class MaintenanceTicketSerializer(serializers.ModelSerializer):
    organization_name = serializers.CharField(source="organization.display_name", read_only=True)
    program_title = serializers.CharField(source="program.title", read_only=True)
    responsible_name = serializers.SerializerMethodField()
    technician_name = serializers.SerializerMethodField()
    team_members = serializers.PrimaryKeyRelatedField(
        many=True,
        required=False,
        queryset=User.objects.filter(role__in=User.TECHNICIAN_SPACE_ROLES),
    )
    team_member_names = serializers.SerializerMethodField()
    technician_team_label = serializers.CharField(read_only=True)
    client_name = serializers.SerializerMethodField()
    products = serializers.PrimaryKeyRelatedField(many=True, required=False, queryset=Product.objects.all())
    product_names = serializers.SerializerMethodField()
    report = MaintenanceReportSerializer(read_only=True)
    anomaly_ticket_reference = serializers.CharField(source="anomaly_ticket.reference", read_only=True)
    type_label = serializers.CharField(read_only=True)
    is_late = serializers.BooleanField(read_only=True)

    class Meta:
        model = MaintenanceTicket
        fields = [
            "id",
            "organization",
            "organization_name",
            "program",
            "program_title",
            "responsible",
            "responsible_name",
            "technician",
            "technician_name",
            "team_members",
            "team_member_names",
            "technician_team_label",
            "client",
            "client_name",
            "products",
            "product_names",
            "title",
            "type_label",
            "service",
            "periodicity",
            "scheduled_date",
            "initial_scheduled_date",
            "status",
            "checklist",
            "instructions",
            "priority",
            "location",
            "started_at",
            "finished_at",
            "postponed_to",
            "postponement_reason",
            "notified_at",
            "acknowledged_at",
            "overdue_alerted_at",
            "cancelled_at",
            "cancellation_reason",
            "anomaly_ticket",
            "anomaly_ticket_reference",
            "is_late",
            "report",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "organization",
            "organization_name",
            "program_title",
            "responsible_name",
            "technician_name",
            "team_member_names",
            "technician_team_label",
            "client_name",
            "product_names",
            "type_label",
            "started_at",
            "finished_at",
            "notified_at",
            "acknowledged_at",
            "overdue_alerted_at",
            "cancelled_at",
            "anomaly_ticket",
            "anomaly_ticket_reference",
            "is_late",
            "report",
            "created_at",
            "updated_at",
        ]

    def get_responsible_name(self, obj):
        return str(obj.responsible) if obj.responsible else None

    def get_technician_name(self, obj):
        return str(obj.technician)

    def get_team_member_names(self, obj):
        return [str(member) for member in obj.team_members.all()]

    def get_client_name(self, obj):
        return str(obj.client)

    def get_product_names(self, obj):
        return [str(product) for product in obj.products.all()]

    def validate(self, attrs):
        attrs = super().validate(attrs)
        program = attrs.get("program") or getattr(self.instance, "program", None)
        technician = attrs.get("technician") or getattr(self.instance, "technician", None)
        client = attrs.get("client") or getattr(self.instance, "client", None)
        products = attrs.get("products")
        team_members = attrs.get("team_members")
        organization = attrs.get("organization") or getattr(self.instance, "organization", None) or getattr(program, "organization", None)
        if technician and technician.role not in set(User.TECHNICIAN_SPACE_ROLES):
            raise serializers.ValidationError({"technician": "Selectionnez un technicien terrain ou responsable technique habilite."})
        if technician and organization and technician.organization_id and technician.organization_id != organization.id:
            raise serializers.ValidationError({"technician": "Le technicien appartient a une autre organisation."})
        if team_members:
            for member in team_members:
                if member.role not in set(User.TECHNICIAN_SPACE_ROLES):
                    raise serializers.ValidationError({"team_members": "Tous les membres doivent etre des techniciens habilites."})
                if organization and member.organization_id and member.organization_id != organization.id:
                    raise serializers.ValidationError({"team_members": "Un membre appartient a une autre organisation."})
        if client and organization and client.organization_id and client.organization_id != organization.id:
            raise serializers.ValidationError({"client": "Le client appartient a une autre organisation."})
        if products and client:
            for product in products:
                if product.client_id != client.id:
                    raise serializers.ValidationError({"products": "Tous les equipements doivent appartenir au client selectionne."})
        return attrs


class MaintenanceProgramSerializer(serializers.ModelSerializer):
    organization_name = serializers.CharField(source="organization.display_name", read_only=True)
    responsible_name = serializers.SerializerMethodField()
    tickets_count = serializers.SerializerMethodField()
    tickets_done = serializers.SerializerMethodField()
    period_label = serializers.CharField(read_only=True)

    class Meta:
        model = MaintenanceProgram
        fields = [
            "id",
            "organization",
            "organization_name",
            "responsible",
            "responsible_name",
            "title",
            "service",
            "period_type",
            "period_label",
            "month",
            "quarter",
            "year",
            "task_lines",
            "status",
            "published_at",
            "tickets_count",
            "tickets_done",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["organization_name", "responsible_name", "period_label", "published_at", "tickets_count", "tickets_done"]

    def get_responsible_name(self, obj):
        return str(obj.responsible) if obj.responsible else None

    def get_tickets_count(self, obj):
        return obj.tickets.count()

    def get_tickets_done(self, obj):
        return obj.tickets.filter(status=MaintenanceTicket.STATUS_DONE).count()


class MessageInlineSerializer(serializers.ModelSerializer):
    sender_name = serializers.SerializerMethodField()
    recipient_name = serializers.SerializerMethodField()

    class Meta:
        model = Message
        fields = [
            "id",
            "sender",
            "sender_name",
            "recipient",
            "recipient_name",
            "message_type",
            "channel",
            "direction",
            "content",
            "sentiment_score",
            "ai_summary",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "sender",
            "sender_name",
            "recipient_name",
            "sentiment_score",
            "ai_summary",
            "created_at",
        ]

    def get_sender_name(self, obj):
        return str(obj.sender)

    def get_recipient_name(self, obj):
        if not obj.recipient:
            return None
        return str(obj.recipient)


class MessageSerializer(MessageInlineSerializer):
    class Meta(MessageInlineSerializer.Meta):
        fields = ["ticket", *MessageInlineSerializer.Meta.fields]


class TicketAttachmentSerializer(serializers.ModelSerializer):
    uploaded_by_name = serializers.SerializerMethodField()
    ticket_reference = serializers.CharField(source="ticket.reference", read_only=True)
    organization_name = serializers.CharField(source="organization.display_name", read_only=True)
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = TicketAttachment
        fields = [
            "id",
            "organization",
            "organization_name",
            "ticket",
            "ticket_reference",
            "uploaded_by",
            "uploaded_by_name",
            "kind",
            "file",
            "file_url",
            "original_name",
            "content_type",
            "size_bytes",
            "note",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "organization",
            "organization_name",
            "ticket_reference",
            "uploaded_by",
            "uploaded_by_name",
            "original_name",
            "content_type",
            "size_bytes",
            "created_at",
            "updated_at",
            "file_url",
        ]

    def get_uploaded_by_name(self, obj):
        if not obj.uploaded_by:
            return "Systeme"
        return str(obj.uploaded_by)

    def get_file_url(self, obj):
        if not obj.file:
            return ""
        request = self.context.get("request")
        if request:
            return request.build_absolute_uri(obj.file.url)
        return obj.file.url

    def validate_file(self, value):
        try:
            return validate_ticket_attachment_file(value)
        except Exception as exc:
            raise serializers.ValidationError(str(exc)) from exc

    def validate(self, attrs):
        attrs = super().validate(attrs)
        ticket = attrs.get("ticket") or getattr(self.instance, "ticket", None)
        organization = attrs.get("organization") or getattr(self.instance, "organization", None)
        if ticket and organization and ticket.organization_id and organization.id != ticket.organization_id:
            raise serializers.ValidationError("La piece jointe doit appartenir a l'organisation du ticket.")
        return attrs


class InterventionInlineSerializer(serializers.ModelSerializer):
    agent_name = serializers.SerializerMethodField()
    media = serializers.SerializerMethodField()

    class Meta:
        model = Intervention
        fields = [
            "id",
            "agent",
            "agent_name",
            "intervention_type",
            "status",
            "scheduled_for",
            "started_at",
            "finished_at",
            "client_validation_requested_at",
            "client_validated_start_at",
            "client_validated_finish_at",
            "client_validation_impossible",
            "validation_impossible_reason",
            "validation_impossible_photo",
            "diagnosis",
            "action_taken",
            "parts_used",
            "structured_parts_used",
            "time_spent_minutes",
            "technical_report",
            "location_snapshot",
            "client_signed_by",
            "client_signed_at",
            "client_signature_file",
            "report_pdf",
            "report_generated_at",
            "media",
            "created_at",
        ]

    def get_agent_name(self, obj):
        return str(obj.agent)

    def get_media(self, obj):
        return InterventionMediaInlineSerializer(obj.media.all(), many=True, context=self.context).data


class InterventionSerializer(InterventionInlineSerializer):
    class Meta(InterventionInlineSerializer.Meta):
        fields = ["ticket", *InterventionInlineSerializer.Meta.fields]

    def validate(self, attrs):
        attrs = super().validate(attrs)
        ticket = attrs.get("ticket") or getattr(self.instance, "ticket", None)
        agent = attrs.get("agent") or getattr(self.instance, "agent", None)
        if ticket and agent and agent.organization_id and ticket.organization_id and agent.organization_id != ticket.organization_id:
            raise serializers.ValidationError("L'agent selectionne appartient a une autre organisation.")
        return attrs


class InterventionPartUsageSerializer(serializers.ModelSerializer):
    spare_part_label = serializers.SerializerMethodField()
    intervention_reference = serializers.CharField(source="intervention.ticket.reference", read_only=True)
    organization_name = serializers.CharField(source="organization.display_name", read_only=True)

    class Meta:
        model = InterventionPartUsage
        fields = [
            "id",
            "organization",
            "organization_name",
            "intervention",
            "intervention_reference",
            "spare_part",
            "spare_part_label",
            "name_snapshot",
            "reference_snapshot",
            "category_snapshot",
            "quantity",
            "unit_snapshot",
            "note",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "organization",
            "organization_name",
            "intervention_reference",
            "spare_part_label",
            "created_at",
            "updated_at",
        ]

    def get_spare_part_label(self, obj):
        return str(obj.spare_part) if obj.spare_part else ""


class SupportSessionInlineSerializer(serializers.ModelSerializer):
    client_name = serializers.SerializerMethodField()
    agent_name = serializers.SerializerMethodField()

    class Meta:
        model = SupportSession
        fields = [
            "id",
            "client",
            "client_name",
            "agent",
            "agent_name",
            "session_type",
            "status",
            "meeting_link",
            "recording_url",
            "annotations_summary",
            "scheduled_for",
            "started_at",
            "ended_at",
            "created_at",
            "updated_at",
        ]

    def get_client_name(self, obj):
        return str(obj.client)

    def get_agent_name(self, obj):
        if not obj.agent:
            return None
        return str(obj.agent)


class SupportSessionSerializer(SupportSessionInlineSerializer):
    class Meta(SupportSessionInlineSerializer.Meta):
        fields = ["ticket", *SupportSessionInlineSerializer.Meta.fields]

    def validate(self, attrs):
        attrs = super().validate(attrs)
        ticket = attrs.get("ticket") or getattr(self.instance, "ticket", None)
        client = attrs.get("client") or getattr(self.instance, "client", None)
        agent = attrs.get("agent") or getattr(self.instance, "agent", None)
        if ticket and client and ticket.client_id != client.id:
            raise serializers.ValidationError("La session doit etre rattachee au client du ticket.")
        if ticket and agent and agent.organization_id and ticket.organization_id and agent.organization_id != ticket.organization_id:
            raise serializers.ValidationError("L'agent selectionne appartient a une autre organisation.")
        return attrs


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


class NotificationSerializer(serializers.ModelSerializer):
    recipient_name = serializers.SerializerMethodField()
    ticket_reference = serializers.CharField(source="ticket.reference", read_only=True)
    organization_name = serializers.CharField(source="organization.display_name", read_only=True)

    class Meta:
        model = Notification
        fields = [
            "id",
            "organization",
            "organization_name",
            "recipient",
            "recipient_name",
            "ticket",
            "ticket_reference",
            "channel",
            "event_type",
            "subject",
            "message",
            "status",
            "recipient_contact",
            "provider",
            "provider_reference",
            "error_message",
            "delivery_payload",
            "deep_link",
            "action_payload",
            "created_at",
            "sent_at",
            "read_at",
            "clicked_at",
        ]
        read_only_fields = [
            "organization",
            "organization_name",
            "recipient_name",
            "ticket_reference",
            "recipient_contact",
            "provider",
            "provider_reference",
            "error_message",
            "delivery_payload",
            "created_at",
            "sent_at",
            "read_at",
            "clicked_at",
        ]

    def get_recipient_name(self, obj):
        return str(obj.recipient)


class DeviceRegistrationSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeviceRegistration
        fields = [
            "id",
            "user",
            "token",
            "platform",
            "device_id",
            "app_version",
            "is_active",
            "last_seen_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "user",
            "is_active",
            "last_seen_at",
            "created_at",
            "updated_at",
        ]


class OfflineSyncOperationSerializer(serializers.ModelSerializer):
    user_name = serializers.SerializerMethodField()
    organization_name = serializers.CharField(source="organization.display_name", read_only=True)

    class Meta:
        model = OfflineSyncOperation
        fields = [
            "id",
            "organization",
            "organization_name",
            "user",
            "user_name",
            "device",
            "operation_uuid",
            "endpoint",
            "method",
            "payload",
            "status",
            "error_message",
            "client_created_at",
            "applied_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "organization",
            "organization_name",
            "user",
            "user_name",
            "operation_uuid",
            "status",
            "error_message",
            "applied_at",
            "created_at",
            "updated_at",
        ]

    def get_user_name(self, obj):
        return str(obj.user)


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


class TicketFeedbackSerializer(serializers.ModelSerializer):
    ticket_reference = serializers.CharField(source="ticket.reference", read_only=True)
    client_name = serializers.SerializerMethodField()
    organization_name = serializers.CharField(source="organization.display_name", read_only=True)

    class Meta:
        model = TicketFeedback
        fields = [
            "id",
            "organization",
            "organization_name",
            "ticket",
            "ticket_reference",
            "client",
            "client_name",
            "rating",
            "comment",
            "submitted_at",
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
            "submitted_at",
            "created_at",
            "updated_at",
        ]

    def get_client_name(self, obj):
        return str(obj.client)

    def validate_rating(self, value):
        if value < 1 or value > 5:
            raise serializers.ValidationError("La note doit etre comprise entre 1 et 5.")
        return value


class AutomationRuleSerializer(serializers.ModelSerializer):
    organization_name = serializers.CharField(source="organization.display_name", read_only=True)

    class Meta:
        model = AutomationRule
        fields = [
            "id",
            "organization",
            "organization_name",
            "name",
            "description",
            "trigger_event",
            "is_active",
            "priority",
            "conditions",
            "actions",
            "created_at",
            "updated_at",
        ]


class WorkflowExecutionSerializer(serializers.ModelSerializer):
    rule_name = serializers.CharField(source="rule.name", read_only=True)
    ticket_reference = serializers.CharField(source="ticket.reference", read_only=True)
    organization_name = serializers.CharField(source="organization.display_name", read_only=True)

    class Meta:
        model = WorkflowExecution
        fields = [
            "id",
            "organization",
            "organization_name",
            "rule",
            "rule_name",
            "ticket",
            "ticket_reference",
            "status",
            "trigger_event",
            "result",
            "created_at",
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


class TicketSerializer(serializers.ModelSerializer):
    client_name = serializers.SerializerMethodField()
    assigned_agent_name = serializers.SerializerMethodField()
    team_leader_name = serializers.SerializerMethodField()
    team_member_names = serializers.SerializerMethodField()
    organization_name = serializers.CharField(source="organization.display_name", read_only=True)
    product_name = serializers.CharField(source="product_display_name", read_only=True)
    public_status = serializers.CharField(read_only=True)
    is_overdue = serializers.BooleanField(read_only=True)
    messages = serializers.SerializerMethodField()
    attachments = TicketAttachmentSerializer(many=True, read_only=True)
    interventions = InterventionInlineSerializer(many=True, read_only=True)
    support_sessions = SupportSessionInlineSerializer(many=True, read_only=True)
    account_credits = serializers.SerializerMethodField()
    assignment_history = TicketAssignmentSerializer(many=True, read_only=True)
    feedback = TicketFeedbackSerializer(read_only=True)
    initial_escalation_target = serializers.ChoiceField(
        choices=[
            (ESCALATION_TARGET_CFAO_MANAGER, "responsable CFAO"),
            (ESCALATION_TARGET_CFAO_WORKS, "conducteur de travaux CFAO"),
            (ESCALATION_TARGET_CHIEF_TECHNICIAN, "chef technicien froid & climatisation"),
            (ESCALATION_TARGET_SUPERVISOR, "superviseur"),
            (ESCALATION_TARGET_EXPERT_THEN_HEAD_SAV, "expert puis Responsable SAV"),
            (ESCALATION_TARGET_HEAD_SAV, "Responsable SAV"),
        ],
        required=False,
        allow_blank=True,
        write_only=True,
    )

    class Meta:
        model = Ticket
        fields = [
            "id",
            "reference",
            "organization",
            "organization_name",
            "client",
            "client_name",
            "product_label",
            "product",
            "product_name",
            "assigned_agent",
            "assigned_agent_name",
            "team_leader",
            "team_leader_name",
            "team_members",
            "team_member_names",
            "is_team_intervention",
            "initial_escalation_target",
            "title",
            "description",
            "business_domain",
            "category",
            "channel",
            "status",
            "public_status",
            "priority",
            "location",
            "sla_deadline",
            "escalation_count",
            "last_escalation_at",
            "last_escalation_reason",
            "status_before_escalation",
            "first_response_at",
            "resolved_at",
            "closed_at",
            "resolution_summary",
            "is_overdue",
            "messages",
            "attachments",
            "interventions",
            "support_sessions",
            "account_credits",
            "assignment_history",
            "feedback",
            "created_at",
            "updated_at",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if user and user.is_authenticated and getattr(user, "role", "") == User.ROLE_CLIENT:
            self.fields["client"].required = False

    def get_client_name(self, obj):
        return str(obj.client)

    def get_assigned_agent_name(self, obj):
        if not obj.assigned_agent:
            return None
        return str(obj.assigned_agent)

    def get_team_leader_name(self, obj):
        if not obj.team_leader:
            return None
        return str(obj.team_leader)

    def get_team_member_names(self, obj):
        return [str(member) for member in obj.team_members.all()]

    def get_messages(self, obj):
        request = self.context.get("request")
        user = getattr(request, "user", None)
        queryset = scope_message_queryset(obj.messages.all(), user) if user and user.is_authenticated else obj.messages.none()
        return MessageInlineSerializer(queryset, many=True, context=self.context).data

    def get_account_credits(self, obj):
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if not is_admin_user(user):
            return []
        return AccountCreditInlineSerializer(obj.account_credits.all(), many=True, context=self.context).data

    def validate(self, attrs):
        attrs = super().validate(attrs)
        blocked_categories = {
            Ticket.CATEGORY_RETURN,
            Ticket.CATEGORY_REFUND,
            Ticket.CATEGORY_WITHDRAWAL,
            Ticket.CATEGORY_COMPLAINT,
            Ticket.CATEGORY_PAYMENT,
            Ticket.CATEGORY_ACCOUNT,
        }
        if attrs.get("category") in blocked_categories:
            raise serializers.ValidationError(
                {"category": "Cette categorie n'est plus autorisee pour la creation ou la mise a jour des tickets."}
            )
        client = attrs.get("client") or getattr(self.instance, "client", None)
        product = attrs.get("product") or getattr(self.instance, "product", None)
        assigned_agent = attrs.get("assigned_agent") or getattr(self.instance, "assigned_agent", None)
        organization = attrs.get("organization") or getattr(self.instance, "organization", None)
        if self.instance is not None and "status" in attrs:
            next_status = Ticket.normalize_process_status(attrs["status"])
            if not Ticket.can_transition(self.instance.status, next_status):
                raise serializers.ValidationError(
                    {"status": "Transition non autorisee par le cycle de vie du cahier des charges."}
                )
            attrs["status"] = next_status

        if client and product and product.client_id != client.id:
            raise serializers.ValidationError("Le produit selectionne n'appartient pas a ce client.")
        if client and organization and client.organization_id != organization.id:
            raise serializers.ValidationError("Le client selectionne n'appartient pas a cette organisation.")
        if assigned_agent and client and assigned_agent.organization_id and client.organization_id and assigned_agent.organization_id != client.organization_id:
            raise serializers.ValidationError("L'agent selectionne appartient a une autre organisation.")
        previous_assigned_agent = getattr(self.instance, "assigned_agent", None)
        if (
            assigned_agent
            and not assigned_agent.is_ticket_assignment_eligible
            and (not previous_assigned_agent or previous_assigned_agent.id != assigned_agent.id)
        ):
            raise serializers.ValidationError(
                {"assigned_agent": "Affectation autorisee uniquement aux responsables d'escalade ou techniciens disponibles."}
            )
        request = self.context.get("request")
        user = getattr(request, "user", None)
        initial_target = (attrs.get("initial_escalation_target") or "").strip()
        if initial_target:
            if not user or not user.is_authenticated or user.role != User.ROLE_HEAD_SAV:
                raise serializers.ValidationError(
                    {"initial_escalation_target": "Seul le Responsable SAV peut escalader un ticket a la creation."}
                )
            if assigned_agent:
                raise serializers.ValidationError(
                    {"initial_escalation_target": "Choisissez soit une affectation directe, soit une escalade initiale."}
                )
        return attrs


class InterventionMediaInlineSerializer(serializers.ModelSerializer):
    uploaded_by_name = serializers.SerializerMethodField()
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = InterventionMedia
        fields = [
            "id",
            "intervention",
            "uploaded_by",
            "uploaded_by_name",
            "kind",
            "file",
            "file_url",
            "note",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["uploaded_by", "uploaded_by_name", "file_url", "created_at", "updated_at"]

    def get_uploaded_by_name(self, obj):
        if not obj.uploaded_by:
            return None
        return str(obj.uploaded_by)

    def get_file_url(self, obj):
        if not obj.file:
            return ""
        request = self.context.get("request")
        if request:
            return request.build_absolute_uri(obj.file.url)
        return obj.file.url


class InterventionMediaSerializer(InterventionMediaInlineSerializer):
    class Meta(InterventionMediaInlineSerializer.Meta):
        fields = InterventionMediaInlineSerializer.Meta.fields


class TechnicianAvailabilitySerializer(serializers.Serializer):
    """Sérialise la disponibilité d'un technicien"""
    id = serializers.IntegerField()
    name = serializers.CharField()
    email = serializers.EmailField()
    role = serializers.CharField()
    status = serializers.CharField()  # "available", "busy", "absent"
    next_available_at = serializers.DateTimeField()
    busy_until = serializers.DateTimeField(allow_null=True)
    can_be_leader = serializers.BooleanField()
    can_be_member = serializers.BooleanField()
    current_tickets_count = serializers.IntegerField()
