from .base import TimeStampedModel, _generate_unique_slug, _current_year
from .organizations import Agency, Organization
from .users import ClientContact, ClientSite, User
from .equipment import EquipmentCategory, EquipmentLocationHistory, Product, SparePart
from .tickets import Message, Ticket, TicketAssignment, TicketAttachment, TicketFeedback
from .interventions import Intervention, InterventionMedia, InterventionPartUsage
from .maintenance import (
    ChecklistTemplate,
    MaintenancePartUsage,
    MaintenanceProgram,
    MaintenanceProgramPart,
    MaintenanceReport,
    MaintenanceReportPhoto,
    MaintenanceTicket,
    SupportSession,
)
from .financial import AccountCredit, FinancialTransaction, OfferRecommendation
from .analytics import KnowledgeArticle, PredictiveAlert, ProductTelemetry
from .notifications import DeviceRegistration, Notification
from .automation import AutomationRule, OfflineSyncOperation, WorkflowExecution
from .audit import AIActionLog, AuditLog, EscalationHistory
from .reporting import GeneratedReport, SlaRule

__all__ = [
    "AccountCredit",
    "Agency",
    "AIActionLog",
    "AuditLog",
    "AutomationRule",
    "ChecklistTemplate",
    "ClientContact",
    "ClientSite",
    "DeviceRegistration",
    "EquipmentCategory",
    "EquipmentLocationHistory",
    "EscalationHistory",
    "FinancialTransaction",
    "GeneratedReport",
    "Intervention",
    "InterventionMedia",
    "InterventionPartUsage",
    "KnowledgeArticle",
    "MaintenancePartUsage",
    "MaintenanceProgram",
    "MaintenanceProgramPart",
    "MaintenanceReport",
    "MaintenanceReportPhoto",
    "MaintenanceTicket",
    "Message",
    "Notification",
    "OfferRecommendation",
    "OfflineSyncOperation",
    "Organization",
    "PredictiveAlert",
    "Product",
    "ProductTelemetry",
    "SlaRule",
    "SparePart",
    "SupportSession",
    "Ticket",
    "TicketAssignment",
    "TicketAttachment",
    "TicketFeedback",
    "TimeStampedModel",
    "User",
    "WorkflowExecution",
    "_current_year",
    "_generate_unique_slug",
]
