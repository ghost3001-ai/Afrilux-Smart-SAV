from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

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
    Ticket,
    TicketAssignment,
    TicketFeedback,
    User,
    WorkflowExecution,
)


admin.site.site_header = "Afrilux SAV Administration"
admin.site.site_title = "Afrilux SAV Admin"
admin.site.index_title = "Back-office et supervision"


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("display_name", "slug", "city", "country", "support_email", "support_phone", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name", "brand_name", "slug", "support_email", "support_phone", "city", "country")


class MessageInline(admin.TabularInline):
    model = Message
    extra = 0


class InterventionInline(admin.TabularInline):
    model = Intervention
    extra = 0


class SupportSessionInline(admin.TabularInline):
    model = SupportSession
    extra = 0


class ClientContactInline(admin.TabularInline):
    model = ClientContact
    extra = 0


class AccountCreditInline(admin.TabularInline):
    model = AccountCredit
    extra = 0


class TicketFeedbackInline(admin.TabularInline):
    model = TicketFeedback
    extra = 0


class ProductTelemetryInline(admin.TabularInline):
    model = ProductTelemetry
    extra = 0


class PredictiveAlertInline(admin.TabularInline):
    model = PredictiveAlert
    extra = 0


class InterventionMediaInline(admin.TabularInline):
    model = InterventionMedia
    extra = 0


class TicketAssignmentInline(admin.TabularInline):
    model = TicketAssignment
    extra = 0


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    fieldsets = BaseUserAdmin.fieldsets + (
        (
            "SAV",
            {
                "fields": (
                    "organization",
                    "role",
                    "phone",
                    "professional_email",
                    "company_name",
                    "profile_photo",
                    "is_verified",
                    "client_type",
                    "client_status",
                    "sector",
                    "tax_identifier",
                    "address",
                    "internal_note",
                    "specialties",
                    "primary_city",
                    "primary_region",
                    "weekly_availability",
                    "technician_status",
                )
            },
        ),
    )
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        (
            "SAV",
            {
                "fields": (
                    "organization",
                    "role",
                    "phone",
                    "professional_email",
                    "company_name",
                    "is_verified",
                    "client_type",
                    "client_status",
                    "sector",
                    "tax_identifier",
                    "address",
                    "specialties",
                    "primary_city",
                    "primary_region",
                    "technician_status",
                )
            },
        ),
    )
    list_display = (
        "username",
        "email",
        "organization",
        "role",
        "company_name",
        "client_status",
        "technician_status",
        "is_verified",
        "is_staff",
    )
    list_filter = ("organization", "role", "client_status", "technician_status", "is_verified", "is_staff", "is_superuser", "is_active")
    inlines = [ClientContactInline]


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "serial_number",
        "equipment_category",
        "equipment_type",
        "brand",
        "model_reference",
        "organization",
        "client",
        "status",
        "health_score",
        "warranty_end",
    )
    list_filter = ("organization", "equipment_category", "equipment_type", "status", "iot_enabled")
    search_fields = ("name", "serial_number", "sku", "brand", "model_reference", "client__username", "client__company_name", "organization__name")
    inlines = [ProductTelemetryInline, PredictiveAlertInline]


@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = (
        "reference",
        "title",
        "organization",
        "client",
        "assigned_agent",
        "business_domain",
        "status",
        "priority",
        "sla_deadline",
    )
    list_filter = ("organization", "business_domain", "status", "priority", "channel", "category")
    search_fields = ("reference", "title", "description", "product_label", "client__username", "product__serial_number", "organization__name")
    inlines = [MessageInline, TicketAssignmentInline, InterventionInline, SupportSessionInline, AccountCreditInline, TicketFeedbackInline]


@admin.register(FinancialTransaction)
class FinancialTransactionAdmin(admin.ModelAdmin):
    list_display = (
        "external_reference",
        "client",
        "transaction_type",
        "ledger_side",
        "amount",
        "currency",
        "status",
        "occurred_at",
    )
    list_filter = ("organization", "transaction_type", "ledger_side", "status", "currency")
    search_fields = ("external_reference", "provider_reference", "client__username", "description", "organization__name")


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ("ticket", "sender", "channel", "direction", "message_type", "created_at")
    list_filter = ("message_type", "channel", "direction")
    search_fields = ("ticket__reference", "sender__username", "content")


@admin.register(Intervention)
class InterventionAdmin(admin.ModelAdmin):
    list_display = ("ticket", "agent", "intervention_type", "status", "scheduled_for", "time_spent_minutes", "report_generated_at")
    list_filter = ("intervention_type", "status")
    search_fields = ("ticket__reference", "agent__username", "action_taken", "diagnosis")
    inlines = [InterventionMediaInline]


@admin.register(SupportSession)
class SupportSessionAdmin(admin.ModelAdmin):
    list_display = ("ticket", "client", "agent", "session_type", "status", "scheduled_for")
    list_filter = ("session_type", "status")
    search_fields = ("ticket__reference", "client__username", "agent__username")


@admin.register(ProductTelemetry)
class ProductTelemetryAdmin(admin.ModelAdmin):
    list_display = ("product", "metric_name", "value", "unit", "source", "captured_at")
    list_filter = ("source", "metric_name")
    search_fields = ("product__name", "product__serial_number", "metric_name")


@admin.register(ClientContact)
class ClientContactAdmin(admin.ModelAdmin):
    list_display = ("client", "first_name", "last_name", "job_title", "phone", "email", "is_primary")
    list_filter = ("organization", "is_primary")
    search_fields = ("client__username", "client__company_name", "first_name", "last_name", "email", "phone")


@admin.register(EquipmentCategory)
class EquipmentCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "organization", "is_active")
    list_filter = ("organization", "is_active")
    search_fields = ("name", "code", "description", "organization__name")


@admin.register(TicketAssignment)
class TicketAssignmentAdmin(admin.ModelAdmin):
    list_display = ("ticket", "technician", "assigned_by", "assigned_at", "released_at", "status")
    list_filter = ("organization", "status")
    search_fields = ("ticket__reference", "technician__username", "assigned_by__username", "note")


@admin.register(InterventionMedia)
class InterventionMediaAdmin(admin.ModelAdmin):
    list_display = ("intervention", "kind", "uploaded_by", "created_at")
    list_filter = ("organization", "kind")
    search_fields = ("intervention__ticket__reference", "uploaded_by__username", "note")


@admin.register(PredictiveAlert)
class PredictiveAlertAdmin(admin.ModelAdmin):
    list_display = ("product", "alert_type", "severity", "status", "predicted_failure_at", "ticket")
    list_filter = ("alert_type", "severity", "status")
    search_fields = ("product__name", "product__serial_number", "title", "description")


@admin.register(KnowledgeArticle)
class KnowledgeArticleAdmin(admin.ModelAdmin):
    list_display = ("title", "organization", "category", "status", "audience", "product")
    list_filter = ("organization", "status", "audience", "category")
    search_fields = ("title", "summary", "keywords", "content")
    prepopulated_fields = {"slug": ("title",)}


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("recipient", "organization", "event_type", "channel", "status", "ticket", "created_at")
    list_filter = ("organization", "channel", "status", "event_type")
    search_fields = ("recipient__username", "subject", "message", "ticket__reference", "organization__name")


@admin.register(SlaRule)
class SlaRuleAdmin(admin.ModelAdmin):
    list_display = ("organization", "priority", "response_deadline_minutes", "resolution_deadline_hours", "is_active")
    list_filter = ("organization", "priority", "is_active")
    search_fields = ("organization__name",)


@admin.register(GeneratedReport)
class GeneratedReportAdmin(admin.ModelAdmin):
    list_display = ("organization", "report_type", "export_format", "period_label", "generated_by", "created_at")
    list_filter = ("organization", "report_type", "export_format")
    search_fields = ("organization__name", "period_label", "sent_to", "generated_by__username")


@admin.register(DeviceRegistration)
class DeviceRegistrationAdmin(admin.ModelAdmin):
    list_display = ("user", "platform", "device_id", "is_active", "last_seen_at", "updated_at")
    list_filter = ("platform", "is_active")
    search_fields = ("user__username", "token", "device_id", "app_version")


@admin.register(OfferRecommendation)
class OfferRecommendationAdmin(admin.ModelAdmin):
    list_display = ("client", "organization", "offer_type", "status", "price", "valid_until", "ticket")
    list_filter = ("organization", "offer_type", "status")
    search_fields = ("client__username", "title", "description", "ticket__reference", "organization__name")


@admin.register(AccountCredit)
class AccountCreditAdmin(admin.ModelAdmin):
    list_display = ("ticket", "client", "amount", "currency", "status", "executed_by", "executed_at")
    list_filter = ("organization", "status", "currency")
    search_fields = ("ticket__reference", "client__username", "reason", "external_reference", "organization__name")


@admin.register(TicketFeedback)
class TicketFeedbackAdmin(admin.ModelAdmin):
    list_display = ("ticket", "client", "rating", "submitted_at")
    list_filter = ("organization", "rating")
    search_fields = ("ticket__reference", "client__username", "comment", "organization__name")


@admin.register(AutomationRule)
class AutomationRuleAdmin(admin.ModelAdmin):
    list_display = ("name", "organization", "trigger_event", "is_active", "priority")
    list_filter = ("organization", "trigger_event", "is_active")
    search_fields = ("name", "description")


@admin.register(WorkflowExecution)
class WorkflowExecutionAdmin(admin.ModelAdmin):
    list_display = ("rule", "organization", "ticket", "trigger_event", "status", "created_at")
    list_filter = ("organization", "status", "trigger_event")
    search_fields = ("rule__name", "ticket__reference", "organization__name")


@admin.register(AIActionLog)
class AIActionLogAdmin(admin.ModelAdmin):
    list_display = ("action_type", "organization", "status", "ticket", "product", "approved_by", "created_at")
    list_filter = ("organization", "action_type", "status")
    search_fields = ("ticket__reference", "product__serial_number", "rationale", "organization__name")


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = (
        "actor",
        "organization",
        "actor_type",
        "action",
        "target_model",
        "target_reference",
        "source_ip",
        "http_method",
        "created_at",
    )
    list_filter = ("organization", "actor_type", "action", "target_model", "http_method")
    search_fields = ("actor__username", "target_reference", "action", "organization__name", "source_ip", "request_path", "user_agent")
