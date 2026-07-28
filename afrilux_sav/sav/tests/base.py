import io
import json
from datetime import timedelta
from email.message import EmailMessage
from unittest.mock import patch

from django.core import mail
from django.core.management import call_command
from django.core.files.uploadedfile import SimpleUploadedFile
from django.forms import HiddenInput
from django.test import Client, TestCase
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from ..ai import LLMCompletion
from ..comms import DeliveryResult, create_external_channel_notifications
from ..forms import MaintenanceProgramForm, TicketCreateForm
from ..models import (
    AccountCredit,
    Agency,
    AIActionLog,
    AuditLog,
    ClientSite,
    DeviceRegistration,
    EquipmentCategory,
    EquipmentLocationHistory,
    GeneratedReport,
    FinancialTransaction,
    KnowledgeArticle,
    Intervention,
    InterventionPartUsage,
    MaintenanceProgram,
    MaintenanceReport,
    MaintenanceReportPhoto,
    MaintenanceTicket,
    Message,
    Notification,
    OfflineSyncOperation,
    Organization,
    PredictiveAlert,
    Product,
    ProductTelemetry,
    SlaRule,
    SparePart,
    TicketAttachment,
    TicketAssignment,
    TicketFeedback,
    Ticket,
    User,
    WorkflowExecution,
)
from ..services import close_sav_dossier, dispatch_due_reports, dispatch_maintenance_operational_notifications, publish_maintenance_program


class SavPlatformTests(TestCase):
    def setUp(self):
        self.api = APIClient()
        self.organization = Organization.objects.create(
            name="Afrilux Habitat",
            brand_name="Afrilux Habitat",
            portal_tagline="Support energie et equipements habitat",
            primary_color="#D5671D",
            accent_color="#1C7A6A",
            support_email="support-habitat@test.local",
        )
        self.other_organization = Organization.objects.create(
            name="Solaris Industries",
            brand_name="Solaris Industries",
            portal_tagline="Operations industrielles",
            primary_color="#0F6E8C",
            accent_color="#1F9D73",
            support_email="support-solaris@test.local",
        )
        self.manager = User.objects.create_user(
            username="manager",
            email="manager@test.local",
            password="secret123",
            organization=self.organization,
            role=User.ROLE_HEAD_SAV,
            is_staff=True,
        )
        self.auditor = User.objects.create_user(
            username="auditor",
            email="auditor@test.local",
            password="secret123",
            organization=self.organization,
            role=User.ROLE_AUDITOR,
        )
        self.qa_user = User.objects.create_user(
            username="qa",
            email="qa@test.local",
            password="secret123",
            organization=self.organization,
            role=User.ROLE_QA,
        )
        self.dispatcher = User.objects.create_user(
            username="dispatcher",
            email="dispatcher@test.local",
            password="secret123",
            organization=self.organization,
            role=User.ROLE_DISPATCHER,
        )
        self.supervisor = User.objects.create_user(
            username="supervisor",
            email="supervisor@test.local",
            password="secret123",
            organization=self.organization,
            role=User.ROLE_SUPERVISOR,
        )
        self.agent = User.objects.create_user(
            username="agent",
            password="secret123",
            organization=self.organization,
            role=User.ROLE_SUPPORT,
        )
        self.technician = User.objects.create_user(
            username="technician",
            password="secret123",
            organization=self.organization,
            role=User.ROLE_TECHNICIAN,
        )
        self.expert = User.objects.create_user(
            username="expert",
            password="secret123",
            organization=self.organization,
            role=User.ROLE_EXPERT,
        )
        self.field_technician = User.objects.create_user(
            username="fieldtech",
            password="secret123",
            organization=self.organization,
            role=User.ROLE_FIELD_TECHNICIAN,
        )
        self.vip_support = User.objects.create_user(
            username="vipsupport",
            password="secret123",
            organization=self.organization,
            role=User.ROLE_VIP_SUPPORT,
        )
        self.client_user = User.objects.create_user(
            username="client",
            email="client@test.local",
            password="secret123",
            organization=self.organization,
            role=User.ROLE_CLIENT,
            company_name="Afrilux Habitat",
        )
        self.other_manager = User.objects.create_user(
            username="manager_b",
            password="secret123",
            organization=self.other_organization,
            role=User.ROLE_HEAD_SAV,
            is_staff=True,
        )
        self.other_agent = User.objects.create_user(
            username="agent_b",
            password="secret123",
            organization=self.other_organization,
            role=User.ROLE_SUPPORT,
        )
        self.other_client = User.objects.create_user(
            username="client_b",
            password="secret123",
            organization=self.other_organization,
            role=User.ROLE_CLIENT,
            company_name="Solaris Industries",
        )
        self.category = EquipmentCategory.objects.create(
            organization=self.organization,
            name="Impression",
            code="print",
            is_active=True,
        )
        self.other_category = EquipmentCategory.objects.create(
            organization=self.other_organization,
            name="Energie",
            code="energy",
            is_active=True,
        )
        self.product = Product.objects.create(
            client=self.client_user,
            name="Onduleur 5kVA",
            sku="AFR-OND-5KVA",
            serial_number="AFR-0001",
            warranty_end=timezone.localdate() + timedelta(days=40),
            iot_enabled=True,
        )
        self.other_product = Product.objects.create(
            client=self.other_client,
            name="Regulateur 8kVA",
            sku="SOL-REG-8KVA",
            serial_number="SOL-0001",
            warranty_end=timezone.localdate() + timedelta(days=55),
            iot_enabled=True,
        )
        KnowledgeArticle.objects.create(
            title="Guide de verification du cablage",
            category="depannage",
            product=self.product,
            summary="Verifier les connexions et redemarrer l'equipement.",
            content="Controlez le cable principal, resserrez les bornes et relancez le systeme.",
            keywords="cable, branchement, borne, redemarrer",
            status=KnowledgeArticle.STATUS_PUBLISHED,
            audience=KnowledgeArticle.AUDIENCE_PUBLIC,
        )
        self.api.force_authenticate(user=self.manager)
