from django.conf import settings
from django.contrib import messages as django_messages
from django.contrib.auth import login
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db.models import Count, Q
from django.http import HttpResponse, JsonResponse, StreamingHttpResponse
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import FormView, TemplateView

from ..forms import AnalyticsQuestionForm, ClientRegistrationForm
from ..models import (
    AuditLog,
    EquipmentCategory,
    GeneratedReport,
    Intervention,
    MaintenanceTicket,
    Notification,
    SlaRule,
    Ticket,
    User,
)
from ..reporting import REPORT_DAILY, REPORT_MONTHLY, REPORT_WEEKLY, build_report
from ..services import (
    OPEN_TICKET_STATUSES,
    build_customer_insight,
    has_backoffice_access,
    is_internal_user,
    is_manager_user,
    is_support_user,
    scope_audit_log_queryset,
    scope_equipment_category_queryset,
    scope_generated_report_queryset,
    scope_maintenance_ticket_queryset,
    scope_notification_queryset,
    scope_product_queryset,
    scope_sla_rule_queryset,
    scope_ticket_queryset,
    scope_user_queryset,
)
from .base import (
    AdminRequiredMixin,
    InternalRequiredMixin,
    ManagerRequiredMixin,
    ReportingRequiredMixin,
    _dashboard_snapshot,
    _workspace_redirect_url,
)


class HomeRedirectView(View):
    def get(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect(_workspace_redirect_url(request.user))
        return redirect("login")


class RealtimeEventsView(LoginRequiredMixin, View):
    def get(self, request, *args, **kwargs):
        def serialize_notification(notification):
            ticket = notification.ticket
            payload = {
                "id": notification.id,
                "event_type": notification.event_type,
                "subject": notification.subject,
                "message": notification.message,
                "created_at": notification.created_at.isoformat(),
                "ticket_id": ticket.id if ticket else None,
                "ticket_reference": ticket.reference if ticket else "",
                "ticket_status": ticket.status if ticket else "",
                "ticket_status_label": ticket.get_status_display() if ticket else "",
                "ticket_public_status": ticket.public_status if ticket else "",
            }
            return payload

        def stream():
            import json
            import time as _time

            try:
                cursor = int(request.GET.get("last_id") or 0)
            except (TypeError, ValueError):
                cursor = 0
            base_queryset = scope_notification_queryset(
                Notification.objects.select_related("ticket").filter(recipient=request.user),
                request.user,
            )
            if cursor <= 0:
                latest = base_queryset.order_by("-id").first()
                cursor = latest.id if latest else 0
            max_stream_seconds = max(10, min(int(getattr(settings, "SAV_REALTIME_STREAM_SECONDS", 25)), 60))
            poll_seconds = max(1, min(float(getattr(settings, "SAV_REALTIME_POLL_SECONDS", 2)), 10))
            deadline = _time.monotonic() + max_stream_seconds
            yield f"retry: 3000\nevent: connected\ndata: {json.dumps({'last_id': cursor})}\n\n"
            while _time.monotonic() < deadline:
                notifications = list(base_queryset.filter(id__gt=cursor).order_by("id")[:20])
                for notification in notifications:
                    cursor = max(cursor, notification.id)
                    data = json.dumps(serialize_notification(notification), ensure_ascii=True)
                    yield f"event: notification\ndata: {data}\n\n"
                if not notifications:
                    yield f"event: heartbeat\ndata: {json.dumps({'last_id': cursor})}\n\n"
                _time.sleep(poll_seconds)

        response = StreamingHttpResponse(stream(), content_type="text/event-stream")
        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"
        return response


class WebManifestView(View):
    def get(self, request, *args, **kwargs):
        return JsonResponse(
            {
                "name": "Afrilux Smart SAV",
                "short_name": "Afrilux SAV",
                "start_url": "/workspace/",
                "scope": "/",
                "display": "standalone",
                "background_color": "#F7F2EC",
                "theme_color": "#D5671D",
                "description": "Helpdesk SAV avec support terrain et synchronisation hors ligne.",
                "icons": [
                    {
                        "src": "/static/sav/images/afrilux-smart-solutions-logo.jpeg",
                        "sizes": "192x192",
                        "type": "image/jpeg",
                    }
                ],
            },
            content_type="application/manifest+json",
        )


class ServiceWorkerView(View):
    def get(self, request, *args, **kwargs):
        script = """
const CACHE_NAME = "afrilux-sav-offline-v3";
const CORE_ASSETS = [
  "/login/",
  "/workspace/",
  "/static/sav/styles.css?v=20260721.3",
  "/static/sav/app.js?v=20260721.3",
  "/static/sav/images/afrilux-smart-solutions-logo.jpeg"
];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE_NAME).then((cache) => cache.addAll(CORE_ASSETS)).catch(() => undefined));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))))
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET" || new URL(request.url).origin !== self.location.origin) {
    return;
  }
  event.respondWith(
    fetch(request)
      .then((response) => {
        const copy = response.clone();
        caches.open(CACHE_NAME).then((cache) => cache.put(request, copy)).catch(() => undefined);
        return response;
      })
      .catch(() => caches.match(request).then((cached) => cached || caches.match("/workspace/") || caches.match("/login/")))
  );
});
"""
        response = HttpResponse(script.strip(), content_type="application/javascript")
        response["Service-Worker-Allowed"] = "/"
        response["Cache-Control"] = "no-cache, no-store, must-revalidate"
        return response


class RoleWorkspaceRedirectView(LoginRequiredMixin, View):
    def get(self, request, *args, **kwargs):
        return redirect(_workspace_redirect_url(request.user))


class ClientRegisterView(FormView):
    template_name = "sav/register.html"
    form_class = ClientRegistrationForm
    success_url = reverse_lazy("support-page")

    def form_valid(self, form):
        try:
            user = form.save()
        except ValidationError as exc:
            form.add_error(None, exc)
            return self.form_invalid(form)
        if self.request.user.is_authenticated:
            django_messages.success(
                self.request,
                f"Compte client {user.email or user.username} cree avec succes.",
            )
            target = "administration-page" if self.request.user.is_superuser or self.request.user.role == User.ROLE_ADMIN else "dashboard"
            return redirect(target)

        login(self.request, user, backend="sav.auth_backends.EmailOrUsernameBackend")
        django_messages.success(
            self.request,
            "Compte client cree avec succes. Vous etes maintenant connecte.",
        )
        return super().form_valid(form)


class DashboardPageView(LoginRequiredMixin, TemplateView):
    template_name = "sav/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        cache_timeout = max(0, int(getattr(settings, "SAV_DASHBOARD_CACHE_SECONDS", 60)))
        cache_key = (
            "sav-dashboard:v2:"
            f"{self.request.user.pk}:{self.request.user.role}:{self.request.user.organization_id}:{int(self.request.user.is_superuser)}"
        )
        cached_dashboard = cache.get(cache_key) if cache_timeout else None
        if cached_dashboard is None:
            snapshot = _dashboard_snapshot(self.request.user)
            if is_internal_user(self.request.user):
                at_risk_clients = list(
                    scope_user_queryset(User.objects.filter(role=User.ROLE_CLIENT), self.request.user)
                    .annotate(
                        critical_open=Count(
                            "tickets",
                            filter=Q(tickets__priority=Ticket.PRIORITY_CRITICAL, tickets__status__in=OPEN_TICKET_STATUSES),
                        ),
                        open_total=Count("tickets", filter=Q(tickets__status__in=OPEN_TICKET_STATUSES)),
                    )
                    .filter(Q(critical_open__gt=0) | Q(open_total__gte=2))
                    .order_by("-critical_open", "-open_total", "username")[:6]
                )
            else:
                at_risk_clients = []
            cached_dashboard = {"snapshot": snapshot, "at_risk_clients": at_risk_clients}
            if cache_timeout:
                cache.set(cache_key, cached_dashboard, cache_timeout)
        snapshot = cached_dashboard["snapshot"]
        context.update(snapshot)
        context["analytics_form"] = AnalyticsQuestionForm(
            initial={"question": "Combien de tickets critiques avons-nous ?"}
        )
        context["client_insight"] = build_customer_insight(self.request.user) if self.request.user.role == User.ROLE_CLIENT else None
        context["at_risk_clients"] = cached_dashboard["at_risk_clients"]
        return context


class ReportingPageView(LoginRequiredMixin, ReportingRequiredMixin, TemplateView):
    template_name = "sav/reporting.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        anchor_date = timezone.localdate()
        context["daily_report"] = build_report(REPORT_DAILY, self.request.user, anchor_date=anchor_date)
        context["weekly_report"] = build_report(REPORT_WEEKLY, self.request.user, anchor_date=anchor_date)
        context["monthly_report"] = build_report(REPORT_MONTHLY, self.request.user, anchor_date=anchor_date)
        context["generated_reports"] = list(
            scope_generated_report_queryset(
                GeneratedReport.objects.select_related("organization", "generated_by"),
                self.request.user,
            )[:12]
        )
        return context


class TechnicianPlanningPageView(LoginRequiredMixin, ManagerRequiredMixin, TemplateView):
    template_name = "sav/planning.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        selected_date = timezone.localdate()
        if self.request.GET.get("week"):
            try:
                from datetime import datetime as _datetime
                selected_date = _datetime.fromisoformat(self.request.GET["week"]).date()
            except ValueError:
                selected_date = timezone.localdate()
        from datetime import timedelta
        week_start = selected_date - timedelta(days=selected_date.weekday())
        week_end = week_start + timedelta(days=7)
        technicians = scope_user_queryset(
            User.objects.filter(role__in=User.TECHNICIAN_SPACE_ROLES, is_active=True),
            self.request.user,
        ).order_by("first_name", "last_name", "username")
        tickets = scope_ticket_queryset(
            Ticket.objects.select_related("client", "product", "assigned_agent"),
            self.request.user,
        ).filter(status__in=OPEN_TICKET_STATUSES)
        interventions = Intervention.objects.select_related("ticket", "ticket__client", "agent").filter(
            agent__in=technicians,
            scheduled_for__date__gte=week_start,
            scheduled_for__date__lt=week_end,
        )
        maintenance_tickets = scope_maintenance_ticket_queryset(
            MaintenanceTicket.objects.select_related("client", "technician").prefetch_related("products", "team_members"),
            self.request.user,
        ).filter(
            Q(technician__in=technicians) | Q(team_members__in=technicians),
            scheduled_date__date__gte=week_start,
            scheduled_date__date__lt=week_end,
        ).distinct()
        days = [week_start + timedelta(days=index) for index in range(7)]
        technician_cards = []
        for technician in technicians:
            assigned_tickets = list(
                tickets.filter(assigned_agent=technician).order_by("priority", "sla_deadline", "-created_at")[:24]
            )
            technician_interventions = list(
                interventions.filter(agent=technician).order_by("scheduled_for", "created_at")
            )
            calendar_rows = []
            for day in days:
                day_items = [item for item in technician_interventions if item.scheduled_for and item.scheduled_for.date() == day]
                maintenance_items = [
                    item
                    for item in maintenance_tickets
                    if (
                        (
                            item.technician_id == technician.id
                            or any(member.id == technician.id for member in item.team_members.all())
                        )
                        and timezone.localtime(item.scheduled_date).date() == day
                    )
                ]
                calendar_rows.append(
                    {
                        "day": day,
                        "items": day_items,
                        "maintenance_items": maintenance_items,
                    }
                )
            technician_cards.append(
                {
                    "technician": technician,
                    "assigned_tickets": assigned_tickets,
                    "calendar_rows": calendar_rows,
                }
            )

        context.update(
            {
                "week_start": week_start,
                "week_end": week_end - timedelta(days=1),
                "week_days": days,
                "unassigned_tickets": list(tickets.filter(assigned_agent__isnull=True).order_by("priority", "created_at")[:30]),
                "technician_cards": technician_cards,
                "ticket_assign_url_template": "/api/tickets/__ticket__/assign/",
            }
        )
        return context


class AdministrationPageView(LoginRequiredMixin, AdminRequiredMixin, TemplateView):
    template_name = "sav/administration.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        users = scope_user_queryset(User.objects.all(), self.request.user)
        cdc_internal_roles = [
            User.ROLE_ADMIN,
            User.ROLE_HEAD_SAV,
            User.ROLE_CFAO_MANAGER,
            User.ROLE_CFAO_WORKS,
            User.ROLE_HVAC_MANAGER,
            User.ROLE_CHIEF_TECHNICIAN,
            User.ROLE_TECHNICIAN,
            User.ROLE_AUDITOR,
        ]
        internal_users = users.filter(role__in=cdc_internal_roles).order_by("role", "first_name", "last_name", "username")
        clients = users.filter(role=User.ROLE_CLIENT).order_by("company_name", "username")
        organization = getattr(self.request.user, "organization", None)
        context.update(
            {
                "organization": organization,
                "internal_users": internal_users[:20],
                "clients": clients[:20],
                "sla_rules": scope_sla_rule_queryset(SlaRule.objects.all(), self.request.user).order_by("priority"),
                "equipment_categories": scope_equipment_category_queryset(
                    EquipmentCategory.objects.all(),
                    self.request.user,
                ).order_by("name")[:20],
                "recent_audits": scope_audit_log_queryset(
                    AuditLog.objects.select_related("actor"),
                    self.request.user,
                )[:20],
                "generated_reports": scope_generated_report_queryset(
                    GeneratedReport.objects.select_related("generated_by"),
                    self.request.user,
                )[:12],
                "users_summary": {
                    "admins": internal_users.filter(role=User.ROLE_ADMIN).count(),
                    "responsables": internal_users.filter(role=User.ROLE_HEAD_SAV).count(),
                    "cfao": internal_users.filter(role=User.ROLE_CFAO_MANAGER).count(),
                    "travaux_cfao": internal_users.filter(role=User.ROLE_CFAO_WORKS).count(),
                    "froid_clim": internal_users.filter(role=User.ROLE_HVAC_MANAGER).count(),
                    "chefs_techniciens": internal_users.filter(role=User.ROLE_CHIEF_TECHNICIAN).count(),
                    "techniciens": internal_users.filter(role=User.ROLE_TECHNICIAN).count(),
                    "auditeurs": internal_users.filter(role=User.ROLE_AUDITOR).count(),
                    "clients": clients.count(),
                },
            }
        )
        return context
