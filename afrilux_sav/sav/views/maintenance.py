from datetime import timedelta

from rest_framework import filters, parsers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from ..models import (
    ChecklistTemplate,
    MaintenancePartUsage,
    MaintenanceProgram,
    MaintenanceReport,
    MaintenanceTicket,
    Ticket,
)
from ..permissions import IsAuthenticatedSavUser, IsInternalUser
from ..serializers import (
    ChecklistTemplateSerializer,
    MaintenancePartUsageSerializer,
    MaintenanceProgramSerializer,
    MaintenanceReportSerializer,
    MaintenanceTicketSerializer,
    TicketSerializer,
)
from ..services import (
    acknowledge_maintenance_ticket,
    can_manage_maintenance,
    cancel_maintenance_ticket,
    close_maintenance_ticket,
    postpone_maintenance_ticket,
    publish_maintenance_program,
    scope_checklist_template_queryset,
    scope_maintenance_part_usage_queryset,
    scope_maintenance_program_queryset,
    scope_maintenance_report_queryset,
    scope_maintenance_ticket_queryset,
    start_maintenance_ticket,
    validate_maintenance_report,
)
from .base import AuditedModelViewSet, _parse_anchor_date, _start_of_day


class ChecklistTemplateViewSet(AuditedModelViewSet):
    serializer_class = ChecklistTemplateSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["name", "service", "equipment_category__name"]
    ordering_fields = ["service", "name", "created_at"]

    def get_permissions(self):
        if self.request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            return [IsInternalUser()]
        return [IsAuthenticatedSavUser()]

    def get_queryset(self):
        queryset = ChecklistTemplate.objects.select_related("organization", "equipment_category").all()
        queryset = scope_checklist_template_queryset(queryset, self.request.user)
        service = self.request.query_params.get("service")
        if service:
            queryset = queryset.filter(service=service)
        return queryset

    def perform_create(self, serializer):
        if not can_manage_maintenance(self.request.user):
            raise PermissionDenied("La gestion des modeles de checklist est reservee aux responsables de service.")
        organization = serializer.validated_data.get("organization") or getattr(self.request.user, "organization", None)
        instance = serializer.save(organization=organization)
        self.audit("maintenance_checklist_template_created", instance)

    def perform_update(self, serializer):
        if not can_manage_maintenance(self.request.user):
            raise PermissionDenied("La gestion des modeles de checklist est reservee aux responsables de service.")
        instance = serializer.save()
        self.audit("maintenance_checklist_template_updated", instance)


class MaintenanceProgramViewSet(AuditedModelViewSet):
    serializer_class = MaintenanceProgramSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["title", "service", "responsible__username", "responsible__first_name", "responsible__last_name"]
    ordering_fields = ["year", "month", "quarter", "created_at", "published_at"]

    def get_permissions(self):
        if self.action == "publier" or self.request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            return [IsInternalUser()]
        return [IsAuthenticatedSavUser()]

    def get_queryset(self):
        queryset = MaintenanceProgram.objects.select_related("organization", "responsible").prefetch_related("tickets")
        queryset = scope_maintenance_program_queryset(queryset, self.request.user)
        status_value = self.request.query_params.get("status")
        service = self.request.query_params.get("service")
        year = self.request.query_params.get("year")
        if status_value:
            queryset = queryset.filter(status=status_value)
        if service:
            queryset = queryset.filter(service=service)
        if year:
            queryset = queryset.filter(year=year)
        return queryset

    def perform_create(self, serializer):
        if not can_manage_maintenance(self.request.user):
            raise PermissionDenied("La creation du programme de maintenance est reservee aux responsables de service.")
        organization = serializer.validated_data.get("organization") or getattr(self.request.user, "organization", None)
        responsible = serializer.validated_data.get("responsible") or self.request.user
        if (
            organization
            and not self.request.user.is_superuser
            and self.request.user.organization_id
            and organization.id != self.request.user.organization_id
        ):
            raise PermissionDenied("Vous ne pouvez pas creer un programme pour une autre organisation.")
        instance = serializer.save(organization=organization, responsible=responsible)
        self.audit("maintenance_program_created", instance)

    def perform_update(self, serializer):
        if not can_manage_maintenance(self.request.user):
            raise PermissionDenied("La mise a jour du programme est reservee aux responsables de service.")
        instance = serializer.save()
        self.audit("maintenance_program_updated", instance)

    @action(detail=True, methods=["post"], url_path="publier")
    def publier(self, request, pk=None):
        if not can_manage_maintenance(request.user):
            raise PermissionDenied("La publication est reservee aux responsables de service.")
        program = self.get_object()
        try:
            tickets = publish_maintenance_program(program, actor=request.user)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        serializer = MaintenanceTicketSerializer(tickets, many=True, context=self.get_serializer_context())
        return Response({"program": self.get_serializer(program).data, "tickets": serializer.data}, status=status.HTTP_201_CREATED)


class MaintenanceTicketViewSet(AuditedModelViewSet):
    serializer_class = MaintenanceTicketSerializer
    parser_classes = [parsers.JSONParser, parsers.MultiPartParser, parsers.FormParser]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["title", "client__username", "client__company_name", "technician__username", "location"]
    ordering_fields = ["scheduled_date", "priority", "status", "created_at"]

    def get_permissions(self):
        if self.action in {"accuser_reception", "demarrer", "cloturer", "reporter", "annuler", "valider"}:
            return [IsInternalUser()]
        if self.request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            return [IsInternalUser()]
        return [IsAuthenticatedSavUser()]

    def get_queryset(self):
        queryset = MaintenanceTicket.objects.select_related(
            "organization", "program", "responsible", "technician",
            "client", "anomaly_ticket", "report",
        ).prefetch_related("products", "report__photo_files")
        queryset = scope_maintenance_ticket_queryset(queryset, self.request.user)
        technician = self.request.query_params.get("technicien") or self.request.query_params.get("technician")
        client = self.request.query_params.get("client")
        status_value = self.request.query_params.get("status")
        service = self.request.query_params.get("service")
        date_from = _parse_anchor_date(self.request.query_params.get("date_from"))
        date_to = _parse_anchor_date(self.request.query_params.get("date_to"))
        if technician:
            queryset = queryset.filter(technician_id=technician)
        if client:
            queryset = queryset.filter(client_id=client)
        if status_value:
            queryset = queryset.filter(status=status_value)
        if service:
            queryset = queryset.filter(service=service)
        if date_from:
            queryset = queryset.filter(scheduled_date__gte=_start_of_day(date_from))
        if date_to:
            queryset = queryset.filter(scheduled_date__lt=_start_of_day(date_to + timedelta(days=1)))
        return queryset

    def perform_create(self, serializer):
        if not can_manage_maintenance(self.request.user):
            raise PermissionDenied("La creation de tickets maintenance est reservee aux responsables de service.")
        client = serializer.validated_data["client"]
        if (
            client
            and not self.request.user.is_superuser
            and self.request.user.organization_id
            and client.organization_id != self.request.user.organization_id
        ):
            raise PermissionDenied("Vous ne pouvez pas creer une maintenance pour une autre organisation.")
        instance = serializer.save(
            organization=client.organization,
            responsible=serializer.validated_data.get("responsible") or self.request.user,
        )
        self.audit("maintenance_ticket_created", instance)

    def perform_update(self, serializer):
        if not can_manage_maintenance(self.request.user):
            raise PermissionDenied("La mise a jour de maintenance est reservee aux responsables de service.")
        instance = serializer.save()
        self.audit("maintenance_ticket_updated", instance)

    @action(detail=True, methods=["post"], url_path="demarrer")
    def demarrer(self, request, pk=None):
        maintenance_ticket = self.get_object()
        try:
            start_maintenance_ticket(maintenance_ticket, actor=request.user)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(maintenance_ticket).data)

    @action(detail=True, methods=["post"], url_path="accuser-reception")
    def accuser_reception(self, request, pk=None):
        maintenance_ticket = self.get_object()
        try:
            acknowledge_maintenance_ticket(maintenance_ticket, actor=request.user)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(maintenance_ticket).data)

    @action(detail=True, methods=["post"], url_path="reporter")
    def reporter(self, request, pk=None):
        maintenance_ticket = self.get_object()
        try:
            postpone_maintenance_ticket(
                maintenance_ticket,
                new_date=request.data.get("new_date") or request.data.get("nouvelle_date"),
                justification=request.data.get("justification") or request.data.get("reason") or request.data.get("motif"),
                actor=request.user,
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(maintenance_ticket).data)

    @action(detail=True, methods=["post"], url_path="annuler")
    def annuler(self, request, pk=None):
        maintenance_ticket = self.get_object()
        try:
            cancel_maintenance_ticket(
                maintenance_ticket,
                reason=request.data.get("reason") or request.data.get("motif") or request.data.get("justification"),
                actor=request.user,
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(maintenance_ticket).data)

    @action(detail=True, methods=["post"], url_path="valider")
    def valider(self, request, pk=None):
        maintenance_ticket = self.get_object()
        try:
            report = validate_maintenance_report(maintenance_ticket, actor=request.user)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        payload = self.get_serializer(maintenance_ticket).data
        payload["report"] = MaintenanceReportSerializer(report, context=self.get_serializer_context()).data
        return Response(payload)

    @action(detail=True, methods=["post"], url_path="cloturer")
    def cloturer(self, request, pk=None):
        maintenance_ticket = self.get_object()
        try:
            photo_files = request.FILES.getlist("photos") or request.FILES.getlist("maintenance_photos")
            result = close_maintenance_ticket(
                maintenance_ticket,
                actor=request.user,
                final_status=request.data.get("final_status") or request.data.get("nouveau_statut") or MaintenanceTicket.STATUS_DONE,
                actual_started_at=request.data.get("actual_started_at") or request.data.get("debut_reel"),
                actual_finished_at=request.data.get("actual_finished_at") or request.data.get("fin_reelle"),
                checklist_completed=request.data.get("checklist_completed") or request.data.get("checklist_realisee"),
                observations=request.data.get("observations", ""),
                work_to_plan=request.data.get("work_to_plan") or request.data.get("travaux_a_prevoir") or "",
                parts_used=request.data.get("parts_used") or request.data.get("pieces_utilisees") or "",
                parts_status=request.data.get("parts_status") or request.data.get("etat_pieces") or {},
                intervention_types=request.data.get("intervention_types") or request.data.get("types_intervention") or [],
                anomaly_detected=request.data.get("anomaly_detected") or request.data.get("anomalie_detectee"),
                photos=request.data.get("photo_refs") or request.data.get("photos_json"),
                photo_files=photo_files,
                client_signed_by=request.data.get("client_signed_by") or request.data.get("signature_client") or "",
                client_signature_file=request.FILES.get("client_signature_file"),
                new_date=request.data.get("new_date") or request.data.get("nouvelle_date"),
                postponement_reason=request.data.get("postponement_reason") or request.data.get("justification") or "",
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        payload = self.get_serializer(result["maintenance_ticket"]).data
        payload["report"] = MaintenanceReportSerializer(result["report"], context=self.get_serializer_context()).data
        if result.get("incident_ticket"):
            payload["incident_ticket"] = TicketSerializer(result["incident_ticket"], context=self.get_serializer_context()).data
        return Response(payload)


class MaintenanceReportViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = MaintenanceReportSerializer
    permission_classes = [IsAuthenticatedSavUser]
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ["actual_finished_at", "created_at"]

    def get_queryset(self):
        queryset = MaintenanceReport.objects.select_related("maintenance_ticket", "technician", "organization").prefetch_related("photo_files")
        queryset = scope_maintenance_report_queryset(queryset, self.request.user)
        ticket_id = self.request.query_params.get("ticket") or self.request.query_params.get("maintenance_ticket")
        if ticket_id:
            queryset = queryset.filter(maintenance_ticket_id=ticket_id)
        return queryset


class MaintenancePartUsageViewSet(AuditedModelViewSet):
    serializer_class = MaintenancePartUsageSerializer
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ["created_at", "quantity"]

    def get_permissions(self):
        if self.request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            return [IsInternalUser()]
        return [IsAuthenticatedSavUser()]

    def get_queryset(self):
        queryset = MaintenancePartUsage.objects.select_related("organization", "report__maintenance_ticket", "spare_part").all()
        return scope_maintenance_part_usage_queryset(queryset, self.request.user)

    def perform_create(self, serializer):
        report = serializer.validated_data["report"]
        if not can_manage_maintenance(self.request.user) and report.technician_id != self.request.user.id:
            raise PermissionDenied("Vous ne pouvez declarer des pieces que sur vos rapports de maintenance.")
        instance = serializer.save(organization=report.organization)
        self.audit("maintenance_part_usage_created", instance)

    def perform_update(self, serializer):
        instance = serializer.save()
        self.audit("maintenance_part_usage_updated", instance)
