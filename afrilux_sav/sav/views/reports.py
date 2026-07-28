from django.http import HttpResponse
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from ..models import GeneratedReport
from ..permissions import IsAuthenticatedSavUser
from ..reporting import (
    REPORT_DAILY,
    REPORT_MONTHLY,
    REPORT_WEEKLY,
    build_report,
    export_report_csv,
    export_report_pdf,
    export_report_xlsx,
)
from ..services import archive_generated_report, build_maintenance_period_report, can_manage_maintenance, has_reporting_access
from .base import _parse_anchor_date


class BaseReportView(APIView):
    permission_classes = [IsAuthenticatedSavUser]
    report_type = None

    def get(self, request):
        if not has_reporting_access(request.user):
            raise PermissionDenied("Le reporting est reserve aux profils de supervision, pilotage et lecture seule habilites.")
        anchor_date = _parse_anchor_date(request.query_params.get("date"))
        return Response(build_report(self.report_type, request.user, anchor_date=anchor_date))


class DailyReportView(BaseReportView):
    report_type = REPORT_DAILY


class WeeklyReportView(BaseReportView):
    report_type = REPORT_WEEKLY


class MonthlyReportView(BaseReportView):
    report_type = REPORT_MONTHLY


class ReportExportView(APIView):
    permission_classes = [IsAuthenticatedSavUser]

    def get(self, request, report_type):
        if not has_reporting_access(request.user):
            raise PermissionDenied("L'export de rapports est reserve aux profils de supervision, pilotage et lecture seule habilites.")
        anchor_date = _parse_anchor_date(request.query_params.get("date"))
        export_format = str(request.query_params.get("format", "xlsx")).strip().lower()
        report = build_report(report_type, request.user, anchor_date=anchor_date)
        safe_period = str(report.get("period_label", "")).replace("/", "-").replace(" ", "_")
        filename = f"{report_type}-{safe_period}"
        if export_format == "csv":
            content = export_report_csv(report)
            archive_generated_report(
                organization=getattr(request.user, "organization", None),
                report=report, report_type=report_type,
                export_format=GeneratedReport.FORMAT_CSV,
                generated_by=request.user, filename=f"{filename}.csv", content=content,
            )
            response = HttpResponse(content, content_type="text/csv; charset=utf-8")
            response["Content-Disposition"] = f'attachment; filename="{filename}.csv"'
            return response
        if export_format == "pdf":
            content = export_report_pdf(report)
            archive_generated_report(
                organization=getattr(request.user, "organization", None),
                report=report, report_type=report_type,
                export_format=GeneratedReport.FORMAT_PDF,
                generated_by=request.user, filename=f"{filename}.pdf", content=content,
            )
            response = HttpResponse(content, content_type="application/pdf")
            response["Content-Disposition"] = f'attachment; filename="{filename}.pdf"'
            return response
        content = export_report_xlsx(report)
        archive_generated_report(
            organization=getattr(request.user, "organization", None),
            report=report, report_type=report_type,
            export_format=GeneratedReport.FORMAT_XLSX,
            generated_by=request.user, filename=f"{filename}.xlsx", content=content,
        )
        response = HttpResponse(
            content,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response["Content-Disposition"] = f'attachment; filename="{filename}.xlsx"'
        return response


class MaintenancePeriodReportView(APIView):
    permission_classes = [IsAuthenticatedSavUser]

    def get(self, request, periode):
        if not (has_reporting_access(request.user) or can_manage_maintenance(request.user)):
            raise PermissionDenied("Le bilan de maintenance est reserve aux responsables, admins et profils direction.")
        anchor_date = _parse_anchor_date(request.query_params.get("date"))
        report = build_maintenance_period_report(periode, request.user, anchor_date=anchor_date)
        export_format = request.query_params.get("format", "").strip().lower()
        filename = f"maintenance-{periode}-{report.get('period_label', '')}".replace(" ", "-").lower()
        if export_format == "pdf":
            content = export_report_pdf(report)
            response = HttpResponse(content, content_type="application/pdf")
            response["Content-Disposition"] = f'attachment; filename="{filename}.pdf"'
            return response
        if export_format == "xlsx":
            content = export_report_xlsx(report)
            response = HttpResponse(
                content,
                content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
            response["Content-Disposition"] = f'attachment; filename="{filename}.xlsx"'
            return response
        if export_format == "csv":
            content = export_report_csv(report)
            response = HttpResponse(content, content_type="text/csv; charset=utf-8")
            response["Content-Disposition"] = f'attachment; filename="{filename}.csv"'
            return response
        return Response(report)
