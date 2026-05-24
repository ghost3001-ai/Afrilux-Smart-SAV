from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    AgencyViewSet,
    AIActionLogViewSet,
    AnalyticsAskView,
    AuditLogViewSet,
    AutomationRuleViewSet,
    ChecklistTemplateViewSet,
    ClientViewSet,
    ClientSiteViewSet,
    ClientContactViewSet,
    DailyReportView,
    EquipmentCategoryViewSet,
    EquipmentLocationHistoryViewSet,
    EquipmentViewSet,
    FinancialTransactionViewSet,
    DashboardView,
    DeviceRegistrationViewSet,
    EmailInboundWebhookView,
    GeneratedReportViewSet,
    HealthCheckView,
    InterventionViewSet,
    InterventionMediaViewSet,
    InterventionPartUsageViewSet,
    KnowledgeArticleViewSet,
    MaintenancePeriodReportView,
    MaintenanceProgramViewSet,
    MaintenanceReportViewSet,
    MaintenancePartUsageViewSet,
    MaintenanceTicketViewSet,
    MessageViewSet,
    MonthlyReportView,
    NotificationViewSet,
    OfflineSyncOperationViewSet,
    OfferRecommendationViewSet,
    PredictiveAlertViewSet,
    ProductTelemetryViewSet,
    ProductViewSet,
    PublicOrganizationListView,
    ReportExportView,
    SlaRuleViewSet,
    SparePartViewSet,
    SupportAssistantView,
    SupportSessionViewSet,
    TechnicianPlanningView,
    TicketAttachmentViewSet,
    TicketAssignmentViewSet,
    TicketFeedbackViewSet,
    TicketViewSet,
    TwilioInboundWebhookView,
    ClientRegistrationView,
    UserViewSet,
    WeeklyReportView,
    WorkflowExecutionViewSet,
)

router = DefaultRouter()
router.register("users", UserViewSet, basename="user")
router.register("clients", ClientViewSet, basename="client")
router.register("client-contacts", ClientContactViewSet, basename="client-contact")
router.register("client-sites", ClientSiteViewSet, basename="client-site")
router.register("agencies", AgencyViewSet, basename="agency")
router.register("equipment-categories", EquipmentCategoryViewSet, basename="equipment-category")
router.register("spare-parts", SparePartViewSet, basename="spare-part")
router.register("products", ProductViewSet, basename="product")
router.register("equipements", EquipmentViewSet, basename="equipment")
router.register("equipment-location-history", EquipmentLocationHistoryViewSet, basename="equipment-location-history")
router.register("maintenance/programmes", MaintenanceProgramViewSet, basename="maintenance-program")
router.register("maintenance/tickets", MaintenanceTicketViewSet, basename="maintenance-ticket")
router.register("maintenance/rapports", MaintenanceReportViewSet, basename="maintenance-report")
router.register("maintenance/pieces-utilisees", MaintenancePartUsageViewSet, basename="maintenance-part-usage")
router.register("maintenance/modeles-checklist", ChecklistTemplateViewSet, basename="maintenance-checklist-template")
router.register("tickets", TicketViewSet, basename="ticket")
router.register("ticket-assignments", TicketAssignmentViewSet, basename="ticket-assignment")
router.register("financial-transactions", FinancialTransactionViewSet, basename="financial-transaction")
router.register("messages", MessageViewSet, basename="message")
router.register("ticket-attachments", TicketAttachmentViewSet, basename="ticket-attachment")
router.register("ticket-feedbacks", TicketFeedbackViewSet, basename="ticket-feedback")
router.register("interventions", InterventionViewSet, basename="intervention")
router.register("intervention-media", InterventionMediaViewSet, basename="intervention-media")
router.register("intervention-pieces", InterventionPartUsageViewSet, basename="intervention-part-usage")
router.register("support-sessions", SupportSessionViewSet, basename="support-session")
router.register("telemetry", ProductTelemetryViewSet, basename="telemetry")
router.register("predictive-alerts", PredictiveAlertViewSet, basename="predictive-alert")
router.register("knowledge-articles", KnowledgeArticleViewSet, basename="knowledge-article")
router.register("notifications", NotificationViewSet, basename="notification")
router.register("device-registrations", DeviceRegistrationViewSet, basename="device-registration")
router.register("offline-sync", OfflineSyncOperationViewSet, basename="offline-sync")
router.register("offers", OfferRecommendationViewSet, basename="offer")
router.register("sla-rules", SlaRuleViewSet, basename="sla-rule")
router.register("generated-reports", GeneratedReportViewSet, basename="generated-report")
router.register("automation-rules", AutomationRuleViewSet, basename="automation-rule")
router.register("workflow-executions", WorkflowExecutionViewSet, basename="workflow-execution")
router.register("ai-actions", AIActionLogViewSet, basename="ai-action")
router.register("audit-logs", AuditLogViewSet, basename="audit-log")

app_name = "sav_api"

urlpatterns = [
    path("health/", HealthCheckView.as_view(), name="health"),
    path("public/organizations/", PublicOrganizationListView.as_view(), name="public-organizations"),
    path("public/register/", ClientRegistrationView.as_view(), name="public-register"),
    path("dashboard/", DashboardView.as_view(), name="dashboard"),
    path("rapports/journalier/", DailyReportView.as_view(), name="report-daily"),
    path("rapports/hebdomadaire/", WeeklyReportView.as_view(), name="report-weekly"),
    path("rapports/mensuel/", MonthlyReportView.as_view(), name="report-monthly"),
    path("rapports/export/<str:report_type>/", ReportExportView.as_view(), name="report-export"),
    path("maintenance/rapports/<str:periode>/", MaintenancePeriodReportView.as_view(), name="maintenance-period-report"),
    path("analytics/ask/", AnalyticsAskView.as_view(), name="analytics-ask"),
    path("techniciens/<int:pk>/planning/", TechnicianPlanningView.as_view(), name="technician-planning"),
    path("support/assistant/", SupportAssistantView.as_view(), name="support-assistant"),
    path("webhook/email/", EmailInboundWebhookView.as_view(), name="email-webhook"),
    path("channels/email/inbound/", EmailInboundWebhookView.as_view(), name="email-inbound"),
    path("channels/twilio/inbound/", TwilioInboundWebhookView.as_view(), name="twilio-inbound"),
    path("", include(router.urls)),
]
