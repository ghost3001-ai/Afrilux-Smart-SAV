from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from .file_validation import MAX_TICKET_ATTACHMENT_BYTES, validate_ticket_attachment_file
from .models import (
    AccountCredit,
    AIActionLog,
    AuditLog,
    AutomationRule,
    ClientContact,
    DeviceRegistration,
    EquipmentCategory,
    FinancialTransaction,
    GeneratedReport,
    Intervention,
    InterventionMedia,
    KnowledgeArticle,
    Message,
    Notification,
    Organization,
    OfferRecommendation,
    PredictiveAlert,
    Product,
    ProductTelemetry,
    SlaRule,
    SupportSession,
    TicketAttachment,
    TicketAssignment,
    TicketFeedback,
    Ticket,
    User,
    WorkflowExecution,
)
from .services import generate_client_username, is_admin_user, provision_client_account, scope_message_queryset


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
            role = User.ROLE_CHIEF_TECHNICIAN
            attrs["role"] = role
        organization = attrs.get("organization") or getattr(self.instance, "organization", None)
        professional_email = (attrs.get("professional_email") or "").strip().lower()
        password = attrs.get("password", "")

        if self.instance is None and not password:
            raise serializers.ValidationError({"password": "Le mot de passe est obligatoire a la creation."})
        if self.instance is None and not attrs.get("username") and not email:
            raise serializers.ValidationError({"username": "Renseignez au minimum un identifiant ou un email."})

        if email:
            attrs["email"] = email
        if professional_email:
            attrs["professional_email"] = professional_email
        if not attrs.get("username") and email:
            attrs["username"] = generate_client_username(email)
        if role == User.ROLE_CLIENT and organization and not attrs.get("company_name") and not getattr(self.instance, "company_name", ""):
            attrs["company_name"] = organization.display_name
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
        client_type = (attrs.get("client_type") or "").strip().lower()
        company_name = (attrs.get("company_name") or "").strip()
        if client_type == "enterprise" and not company_name:
            raise serializers.ValidationError({"company_name": "Le champ Entreprise est obligatoire pour ce type de client."})
        if client_type and client_type != "enterprise":
            attrs["company_name"] = ""
        return attrs

    def create(self, validated_data):
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
        self.context["account_created"] = created
        return user


class ProductSerializer(serializers.ModelSerializer):
    client_name = serializers.SerializerMethodField()
    organization_name = serializers.CharField(source="organization.display_name", read_only=True)
    equipment_category_name = serializers.CharField(source="equipment_category.name", read_only=True)
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
        if client and organization and client.organization_id != organization.id:
            raise serializers.ValidationError("Le client selectionne n'appartient pas a cette organisation.")
        if equipment_category and organization and equipment_category.organization_id and equipment_category.organization_id != organization.id:
            raise serializers.ValidationError("La categorie d'equipement selectionnee appartient a une autre organisation.")
        return attrs


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
            "created_at",
            "sent_at",
            "read_at",
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
    organization_name = serializers.CharField(source="organization.display_name", read_only=True)
    product_name = serializers.CharField(source="product_display_name", read_only=True)
    is_overdue = serializers.BooleanField(read_only=True)
    messages = serializers.SerializerMethodField()
    attachments = TicketAttachmentSerializer(many=True, read_only=True)
    interventions = InterventionInlineSerializer(many=True, read_only=True)
    support_sessions = SupportSessionInlineSerializer(many=True, read_only=True)
    account_credits = serializers.SerializerMethodField()
    assignment_history = TicketAssignmentSerializer(many=True, read_only=True)
    feedback = TicketFeedbackSerializer(read_only=True)

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
            "title",
            "description",
            "business_domain",
            "category",
            "channel",
            "status",
            "priority",
            "location",
            "sla_deadline",
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

    def get_client_name(self, obj):
        return str(obj.client)

    def get_assigned_agent_name(self, obj):
        if not obj.assigned_agent:
            return None
        return str(obj.assigned_agent)

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
                {"assigned_agent": "Affectation autorisee uniquement aux techniciens disponibles."}
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
