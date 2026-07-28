import json
import csv
from datetime import datetime, timedelta

from django.contrib import messages as django_messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.exceptions import ValidationError
from django.db.models import Count, F, Q, Sum
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, FormView, ListView, TemplateView, UpdateView

from ..forms import (
    MaintenanceCancelForm,
    MaintenanceClosureForm,
    MaintenanceProgramForm,
    MaintenanceTicketQuickForm,
    MaintenanceSettingsForm,
    SparePartForm,
)
from ..models import (
    MaintenanceProgram,
    MaintenanceTicket,
    Product,
    SparePart,
    Ticket,
    User,
)
from ..services import (
    can_act_on_maintenance_ticket,
    can_manage_maintenance,
    cancel_maintenance_ticket,
    close_maintenance_ticket,
    log_audit_event,
    publish_maintenance_program,
    reschedule_maintenance_ticket,
    scope_maintenance_program_queryset,
    scope_maintenance_ticket_queryset,
    scope_product_queryset,
    scope_spare_part_queryset,
    scope_user_queryset,
    start_maintenance_ticket,
    validate_maintenance_report,
    has_technician_space_access,
)
from .base import _percentage


class MaintenanceManagerRequiredMixin(UserPassesTestMixin):
    def test_func(self):
        return can_manage_maintenance(self.request.user)


class MaintenanceReadRequiredMixin(UserPassesTestMixin):
    def test_func(self):
        user = self.request.user
        return can_manage_maintenance(user) or getattr(user, "role", "") in (
            set(User.TECHNICIAN_SPACE_ROLES) | {User.ROLE_FIELD_TECHNICIAN, User.ROLE_EXPERT}
        )


def _maintenance_queryset_for_cmms(user):
    return scope_maintenance_ticket_queryset(
        MaintenanceTicket.objects.select_related("client", "technician", "program", "responsible").prefetch_related("products__site", "team_members"),
        user,
    )


def _maintenance_product_queryset(user):
    if getattr(user, "organization_id", None) and (
        can_manage_maintenance(user) or getattr(user, "role", "") in (set(User.TECHNICIAN_SPACE_ROLES) | {User.ROLE_FIELD_TECHNICIAN, User.ROLE_EXPERT})
    ):
        return Product.objects.filter(organization=user.organization)
    return scope_product_queryset(Product.objects.all(), user)


def _maintenance_chart_context(tickets, products):
    today = timezone.localdate()
    months = []
    cursor = today.replace(day=1)
    for _ in range(6):
        months.append(cursor)
        cursor = (cursor - timedelta(days=1)).replace(day=1)
    months.reverse()
    labels = [item.strftime("%m/%Y") for item in months]
    breakdowns = []
    for month in months:
        next_month = (month + timedelta(days=32)).replace(day=1)
        breakdowns.append(tickets.filter(scheduled_date__date__gte=month, scheduled_date__date__lt=next_month, maintenance_type=MaintenanceTicket.TYPE_CORRECTIVE).count())
    type_counts = [tickets.filter(maintenance_type=value).count() for value, _ in MaintenanceTicket.MAINTENANCE_TYPE_CHOICES[:3]]
    total_equipment = products.count()
    operational = products.filter(status=Product.STATUS_OPERATIONAL).count()
    availability = round((operational / total_equipment) * 100, 1) if total_equipment else 0
    return {
        "chart_data": json.dumps({
            "months": labels,
            "breakdowns": breakdowns,
            "types": type_counts,
            "availability": [availability, round(100 - availability, 1)],
        }),
    }


class MaintenanceDashboardView(LoginRequiredMixin, MaintenanceReadRequiredMixin, TemplateView):
    template_name = "sav/maintenance_dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        tickets = _maintenance_queryset_for_cmms(self.request.user)
        products = _maintenance_product_queryset(self.request.user).select_related("client", "site")
        parts = scope_spare_part_queryset(SparePart.objects.all(), self.request.user)
        programs = scope_maintenance_program_queryset(MaintenanceProgram.objects.all(), self.request.user)
        today = timezone.localdate()
        next_week = today + timedelta(days=7)
        late_tickets = [ticket for ticket in tickets if ticket.is_late]
        due_soon = tickets.filter(
            scheduled_date__date__gte=today,
            scheduled_date__date__lte=next_week,
            status__in=[MaintenanceTicket.STATUS_PLANNED, MaintenanceTicket.STATUS_NOTIFIED, MaintenanceTicket.STATUS_POSTPONED],
        )
        warranty_expired = products.filter(warranty_end__lt=today)
        low_stock = [part for part in parts if part.is_low_stock]
        chart_context = _maintenance_chart_context(tickets, products)
        availability_data = json.loads(chart_context["chart_data"])["availability"][0]
        context.update({
            "kpis": {
                "equipment": products.count(),
                "programs": programs.filter(status=MaintenanceProgram.STATUS_PUBLISHED).count(),
                "today": tickets.filter(scheduled_date__date=today).count(),
                "in_progress": tickets.filter(status=MaintenanceTicket.STATUS_IN_PROGRESS).count(),
                "done": tickets.filter(status__in=[MaintenanceTicket.STATUS_DONE, MaintenanceTicket.STATUS_ANOMALY]).count(),
                "critical": tickets.filter(priority=Ticket.PRIORITY_CRITICAL).exclude(status__in=[MaintenanceTicket.STATUS_DONE, MaintenanceTicket.STATUS_CANCELLED]).count(),
                "upcoming": due_soon.count(),
                "alerts": len(late_tickets) + warranty_expired.count() + len(low_stock),
                "availability": availability_data,
            },
            "due_soon": due_soon.order_by("scheduled_date")[:6],
            "late_tickets": late_tickets[:6],
            "warranty_expired": warranty_expired.order_by("warranty_end")[:6],
            "low_stock": low_stock[:6],
            "can_manage_programs": can_manage_maintenance(self.request.user),
        })
        context.update(chart_context)
        return context


class MaintenanceInterventionListView(LoginRequiredMixin, MaintenanceReadRequiredMixin, ListView):
    template_name = "sav/maintenance_intervention_list.html"
    context_object_name = "interventions"
    paginate_by = 20

    def get_queryset(self):
        queryset = _maintenance_queryset_for_cmms(self.request.user)
        filters = self.request.GET
        if filters.get("status"):
            status = filters["status"]
            if status == "late":
                queryset = queryset.exclude(status__in=[MaintenanceTicket.STATUS_DONE, MaintenanceTicket.STATUS_ANOMALY, MaintenanceTicket.STATUS_CANCELLED]).filter(scheduled_date__lt=timezone.now())
            elif status == "planned":
                queryset = queryset.filter(status__in=[MaintenanceTicket.STATUS_PLANNED, MaintenanceTicket.STATUS_NOTIFIED, MaintenanceTicket.STATUS_POSTPONED], scheduled_date__gte=timezone.now())
            elif status == "done":
                queryset = queryset.filter(status__in=[MaintenanceTicket.STATUS_DONE, MaintenanceTicket.STATUS_ANOMALY])
            elif status == "cancelled":
                queryset = queryset.filter(status=MaintenanceTicket.STATUS_CANCELLED)
            else:
                queryset = queryset.filter(status=MaintenanceTicket.STATUS_IN_PROGRESS)
        for key, field in (("technician", "technician_id"), ("client", "client_id"), ("equipment", "products__id")):
            if filters.get(key):
                queryset = queryset.filter(**{field: filters[key]})
        if filters.get("from"):
            queryset = queryset.filter(scheduled_date__date__gte=filters["from"])
        if filters.get("to"):
            queryset = queryset.filter(scheduled_date__date__lte=filters["to"])
        if filters.get("q"):
            query = filters["q"]
            queryset = queryset.filter(Q(title__icontains=query) | Q(client__username__icontains=query) | Q(products__name__icontains=query) | Q(products__serial_number__icontains=query))
        ordering = filters.get("sort", "scheduled_date")
        allowed = {"scheduled_date", "-scheduled_date", "priority", "-priority", "status", "-status"}
        return queryset.distinct().order_by(ordering if ordering in allowed else "scheduled_date")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            "filters": self.request.GET,
            "technicians": scope_user_queryset(User.objects.filter(role__in=User.TECHNICIAN_SPACE_ROLES, is_active=True), self.request.user).order_by("first_name", "last_name"),
            "clients": scope_user_queryset(User.objects.filter(role=User.ROLE_CLIENT, is_active=True), self.request.user).order_by("company_name", "username"),
            "products": _maintenance_product_queryset(self.request.user).order_by("name")[:200],
            "can_manage_programs": can_manage_maintenance(self.request.user),
        })
        for intervention in context["page_obj"].object_list:
            intervention.can_modify = can_act_on_maintenance_ticket(self.request.user, intervention)
        return context


def _planning_datetime(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return timezone.make_aware(parsed, timezone.get_current_timezone()) if timezone.is_naive(parsed) else parsed


def _planning_filters(queryset, params):
    for key, field in (("technician", "technician_id"), ("client", "client_id"), ("equipment", "products__id"), ("priority", "priority"), ("maintenance_type", "maintenance_type")):
        if params.get(key):
            queryset = queryset.filter(**{field: params[key]})
    status = params.get("status")
    if status == "late":
        queryset = queryset.exclude(status__in=[MaintenanceTicket.STATUS_DONE, MaintenanceTicket.STATUS_ANOMALY, MaintenanceTicket.STATUS_CANCELLED]).filter(scheduled_date__lt=timezone.now())
    elif status == "done":
        queryset = queryset.filter(status__in=[MaintenanceTicket.STATUS_DONE, MaintenanceTicket.STATUS_ANOMALY])
    elif status == "planned":
        queryset = queryset.filter(status__in=[MaintenanceTicket.STATUS_PLANNED, MaintenanceTicket.STATUS_NOTIFIED, MaintenanceTicket.STATUS_POSTPONED])
    elif status:
        queryset = queryset.filter(status=status)
    if params.get("zone"):
        queryset = queryset.filter(Q(location__icontains=params["zone"]) | Q(client__primary_city__icontains=params["zone"]) | Q(technician__primary_region__icontains=params["zone"]))
    if params.get("q"):
        query = params["q"]
        queryset = queryset.filter(Q(title__icontains=query) | Q(client__username__icontains=query) | Q(client__company_name__icontains=query) | Q(products__name__icontains=query) | Q(products__serial_number__icontains=query))
    if params.get("date"):
        queryset = queryset.filter(scheduled_date__date=params["date"])
    return queryset.distinct()


class MaintenanceTicketQuickCreateView(LoginRequiredMixin, MaintenanceManagerRequiredMixin, CreateView):
    model = MaintenanceTicket
    form_class = MaintenanceTicketQuickForm
    template_name = "sav/maintenance_ticket_form.html"
    success_url = reverse_lazy("maintenance-calendar")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        form.instance.responsible = self.request.user
        response = super().form_valid(form)
        form.instance.team_members.set(form.cleaned_data["team_members"])
        django_messages.success(self.request, "Intervention créée et ajoutée au planning.")
        return response


class MaintenancePlanningCalendarView(LoginRequiredMixin, MaintenanceReadRequiredMixin, TemplateView):
    template_name = "sav/maintenance_calendar.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        tickets = _maintenance_queryset_for_cmms(self.request.user)
        technicians = scope_user_queryset(User.objects.filter(role__in=User.TECHNICIAN_SPACE_ROLES, is_active=True), self.request.user).order_by("first_name", "last_name", "username")
        today = timezone.localdate()
        final_statuses = [MaintenanceTicket.STATUS_DONE, MaintenanceTicket.STATUS_ANOMALY]
        rows = []
        for technician in technicians:
            count = tickets.filter(technician=technician, scheduled_date__date=today).exclude(status__in=final_statuses + [MaintenanceTicket.STATUS_CANCELLED]).count()
            rows.append({"person": technician, "today_count": count, "availability": technician.technician_status or "available", "zone": technician.primary_region or technician.primary_city or "Zone non renseignée"})
        context.update({
            "planner_kpis": [
                {"label": "Aujourd'hui", "value": tickets.filter(scheduled_date__date=today).count(), "icon": "calendar-event", "tone": "blue"},
                {"label": "En cours", "value": tickets.filter(status=MaintenanceTicket.STATUS_IN_PROGRESS).count(), "icon": "tools", "tone": "orange"},
                {"label": "Terminées", "value": tickets.filter(status__in=final_statuses).count(), "icon": "check2-circle", "tone": "green"},
                {"label": "En retard", "value": sum(1 for item in tickets if item.is_late), "icon": "alarm", "tone": "red"},
                {"label": "Urgentes", "value": tickets.filter(priority=Ticket.PRIORITY_CRITICAL).exclude(status__in=final_statuses + [MaintenanceTicket.STATUS_CANCELLED]).count(), "icon": "exclamation-octagon", "tone": "red"},
                {"label": "Disponibles", "value": technicians.filter(technician_status="available").count(), "icon": "people", "tone": "green"},
            ],
            "planner_technicians": rows,
            "technicians": technicians,
            "clients": scope_user_queryset(User.objects.filter(role=User.ROLE_CLIENT, is_active=True), self.request.user).order_by("company_name", "username"),
            "products": _maintenance_product_queryset(self.request.user).order_by("name")[:300],
            "can_manage_planning": can_manage_maintenance(self.request.user),
        })
        return context


class MaintenancePlanningEventsView(LoginRequiredMixin, MaintenanceReadRequiredMixin, View):
    def get(self, request):
        start, end = _planning_datetime(request.GET.get("start")), _planning_datetime(request.GET.get("end"))
        if not start or not end or end <= start:
            return JsonResponse({"detail": "Période de planning invalide."}, status=400)
        tickets = _planning_filters(_maintenance_queryset_for_cmms(request.user), request.GET).filter(scheduled_date__gte=start, scheduled_date__lt=end).order_by("scheduled_date")[:500]
        events = []
        for ticket in tickets:
            products = list(ticket.products.all())
            product = products[0] if products else None
            site = getattr(product, "site", None)
            duration = max(1, ticket.planned_duration_minutes or 60)
            events.append({
                "id": str(ticket.pk), "title": f"{ticket.client} · {ticket.title}", "start": ticket.scheduled_date.isoformat(),
                "end": (ticket.scheduled_date + timedelta(minutes=duration)).isoformat(),
                "classNames": [f"planner-event--{ticket.cmms_status}"],
                "extendedProps": {"client": str(ticket.client), "site": ticket.location or getattr(site, "name", "") or "Site non renseigné", "technician": ticket.technician_team_label, "technicianId": ticket.technician_id, "canModify": can_act_on_maintenance_ticket(request.user, ticket), "latitude": float(site.gps_latitude) if site and site.gps_latitude is not None else None, "longitude": float(site.gps_longitude) if site and site.gps_longitude is not None else None},
            })
        return JsonResponse(events, safe=False)


class MaintenancePlanningDetailView(LoginRequiredMixin, MaintenanceReadRequiredMixin, View):
    def get(self, request, pk):
        ticket = get_object_or_404(_maintenance_queryset_for_cmms(request.user), pk=pk)
        report = getattr(ticket, "report", None)
        required_parts = list(ticket.program.required_parts.all()) if ticket.program_id else []
        return JsonResponse({
            "id": ticket.pk, "title": ticket.title, "program": str(ticket.program) if ticket.program_id else "Intervention manuelle", "client": str(ticket.client),
            "site": ticket.location or ticket.client.address or "Non renseigné", "equipment": [str(product) for product in ticket.products.all()] or [ticket.equipment_identifier or "Non renseigné"],
            "technician": ticket.technician_team_label, "priority": ticket.get_priority_display(), "status": ticket.cmms_status_label,
            "scheduled_date": timezone.localtime(ticket.scheduled_date).strftime("%d/%m/%Y %H:%M"), "actual_date": timezone.localtime(ticket.started_at).strftime("%d/%m/%Y %H:%M") if ticket.started_at else "Non démarrée",
            "duration": ticket.planned_duration_minutes, "objective": ticket.intervention_reason or ticket.title, "checklist": ticket.checklist or [], "required_parts": [str(part) for part in required_parts],
            "history": [{"label": "Créée", "date": timezone.localtime(ticket.created_at).strftime("%d/%m/%Y %H:%M")}, *([{"label": "Démarrée", "date": timezone.localtime(ticket.started_at).strftime("%d/%m/%Y %H:%M")}] if ticket.started_at else []), *([{"label": "Terminée", "date": timezone.localtime(ticket.finished_at).strftime("%d/%m/%Y %H:%M")}] if ticket.finished_at else [])],
            "observations": report.observations if report else "Aucune observation.", "route": ticket.route, "overnight_stays": ticket.overnight_stays, "can_modify": can_act_on_maintenance_ticket(request.user, ticket),
            "start_url": reverse("maintenance-planning-action", args=[ticket.pk, "start"]), "close_url": reverse("maintenance-ticket-close", args=[ticket.pk]), "assign_url": reverse("maintenance-planning-assign", args=[ticket.pk]),
        })


class MaintenancePlanningRescheduleView(LoginRequiredMixin, MaintenanceReadRequiredMixin, View):
    def post(self, request, pk):
        try:
            payload = json.loads(request.body or "{}")
        except json.JSONDecodeError:
            return JsonResponse({"detail": "Données de replanification invalides."}, status=400)
        ticket = get_object_or_404(_maintenance_queryset_for_cmms(request.user), pk=pk)
        scheduled_date = _planning_datetime(payload.get("start"))
        try:
            duration = max(1, int(payload.get("duration") or ticket.planned_duration_minutes or 60))
        except (TypeError, ValueError):
            return JsonResponse({"detail": "Durée invalide."}, status=400)
        if not scheduled_date:
            return JsonResponse({"detail": "Date prévue invalide."}, status=400)
        candidate_end = scheduled_date + timedelta(minutes=duration)
        product_ids = list(ticket.products.values_list("id", flat=True))
        conflicts = []
        candidates = _maintenance_queryset_for_cmms(request.user).exclude(pk=ticket.pk).exclude(status__in=[MaintenanceTicket.STATUS_DONE, MaintenanceTicket.STATUS_ANOMALY, MaintenanceTicket.STATUS_CANCELLED]).filter(scheduled_date__lt=candidate_end, scheduled_date__gte=scheduled_date - timedelta(hours=24))
        for candidate in candidates.distinct():
            overlaps = candidate.scheduled_date < candidate_end and candidate.scheduled_date + timedelta(minutes=max(1, candidate.planned_duration_minutes or 60)) > scheduled_date
            same_technician = candidate.technician_id == ticket.technician_id
            same_equipment = bool(product_ids and candidate.products.filter(pk__in=product_ids).exists())
            if overlaps and (same_technician or same_equipment):
                conflicts.append({"id": candidate.pk, "title": candidate.title, "reason": "Même technicien" if same_technician else "Même équipement", "scheduled_date": timezone.localtime(candidate.scheduled_date).strftime("%d/%m %H:%M")})
        if conflicts and not payload.get("force"):
            return JsonResponse({"detail": "Conflit de planning détecté.", "conflicts": conflicts}, status=409)
        try:
            updated = reschedule_maintenance_ticket(ticket, scheduled_date=scheduled_date, planned_duration_minutes=duration, actor=request.user)
        except ValueError as exc:
            return JsonResponse({"detail": str(exc)}, status=403)
        return JsonResponse({"detail": "Intervention replanifiée avec succès.", "start": updated.scheduled_date.isoformat(), "duration": updated.planned_duration_minutes, "conflicts": conflicts})


class MaintenancePlanningActionView(LoginRequiredMixin, MaintenanceReadRequiredMixin, View):
    def post(self, request, pk, action):
        ticket = get_object_or_404(_maintenance_queryset_for_cmms(request.user), pk=pk)
        if action != "start":
            return JsonResponse({"detail": "Action inconnue."}, status=400)
        try:
            start_maintenance_ticket(ticket, actor=request.user)
        except ValueError as exc:
            return JsonResponse({"detail": str(exc)}, status=403)
        return JsonResponse({"detail": "Intervention démarrée."})


class MaintenancePlanningAssignView(LoginRequiredMixin, MaintenanceManagerRequiredMixin, View):
    def post(self, request, pk):
        try:
            payload = json.loads(request.body or "{}")
            technician_id = int(payload.get("technician_id"))
        except (json.JSONDecodeError, TypeError, ValueError):
            return JsonResponse({"detail": "Technicien invalide."}, status=400)
        ticket = get_object_or_404(_maintenance_queryset_for_cmms(request.user), pk=pk)
        technician = get_object_or_404(
            scope_user_queryset(User.objects.filter(role__in=User.TECHNICIAN_SPACE_ROLES, is_active=True), request.user),
            pk=technician_id,
        )
        ticket.technician = technician
        ticket.save(update_fields=["technician", "updated_at"])
        log_audit_event(request.user, "maintenance_ticket_reassigned", ticket, {"technician_id": technician.pk})
        return JsonResponse({"detail": "Technicien réaffecté avec succès.", "technician": str(technician)})


class MaintenanceCalendarView(LoginRequiredMixin, MaintenanceReadRequiredMixin, TemplateView):
    template_name = "sav/maintenance_calendar.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        events = []
        for ticket in _maintenance_queryset_for_cmms(self.request.user).order_by("scheduled_date")[:500]:
            events.append({
                "title": f"#{ticket.pk} · {ticket.title}",
                "start": ticket.scheduled_date.isoformat(),
                "url": reverse("maintenance-interventions") + f"?q={ticket.pk}",
                "className": f"cmms-event--{ticket.cmms_status}",
            })
        context["calendar_events"] = json.dumps(events)
        return context


class MaintenanceTechnicianListView(LoginRequiredMixin, MaintenanceReadRequiredMixin, TemplateView):
    template_name = "sav/maintenance_people.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        technicians = scope_user_queryset(User.objects.filter(role__in=User.TECHNICIAN_SPACE_ROLES, is_active=True), self.request.user)
        tickets = _maintenance_queryset_for_cmms(self.request.user)
        rows = []
        for technician in technicians.order_by("first_name", "last_name", "username"):
            rows.append({"person": technician, "planned": tickets.filter(technician=technician).exclude(status__in=[MaintenanceTicket.STATUS_DONE, MaintenanceTicket.STATUS_CANCELLED]).count(), "done": tickets.filter(technician=technician, status__in=[MaintenanceTicket.STATUS_DONE, MaintenanceTicket.STATUS_ANOMALY]).count()})
        context.update({"rows": rows, "title": "Techniciens", "subtitle": "Charge et activite des equipes terrain"})
        return context


class MaintenanceClientListView(LoginRequiredMixin, MaintenanceReadRequiredMixin, TemplateView):
    template_name = "sav/maintenance_people.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        clients = scope_user_queryset(User.objects.filter(role=User.ROLE_CLIENT, is_active=True), self.request.user)
        products = scope_product_queryset(Product.objects.all(), self.request.user)
        tickets = _maintenance_queryset_for_cmms(self.request.user)
        rows = []
        for client in clients.order_by("company_name", "username"):
            rows.append({"person": client, "planned": tickets.filter(client=client).exclude(status__in=[MaintenanceTicket.STATUS_DONE, MaintenanceTicket.STATUS_CANCELLED]).count(), "done": products.filter(client=client).count()})
        context.update({"rows": rows, "title": "Clients", "subtitle": "Parc installe et interventions en suivi", "is_clients": True})
        return context


class SparePartListView(LoginRequiredMixin, MaintenanceReadRequiredMixin, ListView):
    template_name = "sav/spare_part_list.html"
    context_object_name = "parts"
    paginate_by = 20

    def get_queryset(self):
        queryset = scope_spare_part_queryset(SparePart.objects.select_related("equipment_category"), self.request.user)
        if self.request.GET.get("q"):
            query = self.request.GET["q"]
            queryset = queryset.filter(Q(name__icontains=query) | Q(reference__icontains=query) | Q(supplier__icontains=query))
        if self.request.GET.get("low"):
            queryset = queryset.filter(stock_quantity__lte=F("minimum_stock"))
        return queryset.order_by("name")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["q"] = self.request.GET.get("q", "")
        context["low"] = self.request.GET.get("low", "")
        return context


class SparePartCreateView(LoginRequiredMixin, MaintenanceManagerRequiredMixin, CreateView):
    model = SparePart
    form_class = SparePartForm
    template_name = "sav/spare_part_form.html"
    success_url = reverse_lazy("maintenance-parts")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        form.instance.organization = self.request.user.organization
        return super().form_valid(form)


class SparePartUpdateView(LoginRequiredMixin, MaintenanceManagerRequiredMixin, UpdateView):
    model = SparePart
    form_class = SparePartForm
    template_name = "sav/spare_part_form.html"
    success_url = reverse_lazy("maintenance-parts")

    def get_queryset(self):
        return scope_spare_part_queryset(SparePart.objects.all(), self.request.user)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs


class MaintenanceReportsView(LoginRequiredMixin, MaintenanceReadRequiredMixin, TemplateView):
    template_name = "sav/maintenance_reports.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        tickets = _maintenance_queryset_for_cmms(self.request.user)
        completed = tickets.filter(status__in=[MaintenanceTicket.STATUS_DONE, MaintenanceTicket.STATUS_ANOMALY], finished_at__isnull=False, started_at__isnull=False)
        durations = [(ticket.finished_at - ticket.started_at).total_seconds() / 3600 for ticket in completed]
        mttr = round(sum(durations) / len(durations), 1) if durations else 0
        products = scope_product_queryset(Product.objects.all(), self.request.user)
        failures = tickets.filter(maintenance_type=MaintenanceTicket.TYPE_CORRECTIVE).count()
        mtbf = round((products.count() * 30) / failures, 1) if failures else 0
        top_technician = tickets.values("technician__first_name", "technician__last_name", "technician__username").annotate(total=Count("id")).order_by("-total").first()
        failing_equipment = tickets.filter(maintenance_type=MaintenanceTicket.TYPE_CORRECTIVE).values("products__name", "products__serial_number").annotate(total=Count("id")).order_by("-total").first()
        context.update({"metrics": {"total": tickets.count(), "cost": tickets.aggregate(total=Sum("actual_cost"))["total"] or 0, "mttr": mttr, "mtbf": mtbf, "availability": _maintenance_chart_context(tickets, products)["chart_data"], "top_technician": top_technician, "failing_equipment": failing_equipment}})
        return context


class MaintenanceReportCsvView(LoginRequiredMixin, MaintenanceReadRequiredMixin, View):
    def get(self, request):
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="rapport-maintenance.csv"'
        response.write("\ufeff")
        writer = csv.writer(response)
        writer.writerow(["ID", "Intervention", "Client", "Technicien", "Type", "Priorite", "Statut", "Date", "Cout reel"])
        for ticket in _maintenance_queryset_for_cmms(request.user).order_by("scheduled_date"):
            writer.writerow([ticket.pk, ticket.title, str(ticket.client), str(ticket.technician), ticket.type_label, ticket.get_priority_display(), ticket.cmms_status_label, timezone.localtime(ticket.scheduled_date).strftime("%d/%m/%Y %H:%M"), ticket.actual_cost])
        return response


class MaintenanceSettingsView(LoginRequiredMixin, MaintenanceManagerRequiredMixin, UpdateView):
    form_class = MaintenanceSettingsForm
    template_name = "sav/maintenance_settings.html"
    success_url = reverse_lazy("maintenance-settings")

    def get_object(self, queryset=None):
        if not self.request.user.organization_id:
            raise ValidationError("Aucune organisation n'est associee a cet utilisateur.")
        return self.request.user.organization

    def form_valid(self, form):
        django_messages.success(self.request, "Parametres de maintenance mis a jour.")
        return super().form_valid(form)


class MaintenanceProgramListView(LoginRequiredMixin, MaintenanceReadRequiredMixin, TemplateView):
    template_name = "sav/maintenance_program.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        programs = scope_maintenance_program_queryset(
            MaintenanceProgram.objects.select_related("organization", "responsible").prefetch_related("tickets"),
            self.request.user,
        )
        tickets = scope_maintenance_ticket_queryset(
            MaintenanceTicket.objects.select_related("client", "technician", "program", "anomaly_ticket", "report").prefetch_related("products", "team_members"),
            self.request.user,
        )
        active_tickets = tickets.exclude(
            status__in=[
                MaintenanceTicket.STATUS_DONE,
                MaintenanceTicket.STATUS_ANOMALY,
                MaintenanceTicket.STATUS_CANCELLED,
            ]
        )
        context.update(
            {
                "programs": programs[:20],
                "planned_tickets": active_tickets.order_by("scheduled_date", "priority")[:40],
                "recent_done": tickets.filter(
                    status__in=[MaintenanceTicket.STATUS_DONE, MaintenanceTicket.STATUS_ANOMALY],
                ).order_by("-finished_at", "-updated_at")[:12],
                "stats": {
                    "programs": programs.count(),
                    "planned": active_tickets.count(),
                    "done": tickets.filter(status=MaintenanceTicket.STATUS_DONE).count(),
                    "anomalies": tickets.filter(status=MaintenanceTicket.STATUS_ANOMALY).count(),
                },
                "status_choices": MaintenanceTicket.STATUS_CHOICES,
                "maintenance_report_export_url": "/api/maintenance/rapports/mensuel/?format=pdf",
                "maintenance_realization_rate": _percentage(
                    tickets.filter(status=MaintenanceTicket.STATUS_DONE).count(),
                    tickets.count(),
                ),
                "can_manage_programs": can_manage_maintenance(self.request.user),
            }
        )
        return context


class MaintenanceProgramCreateView(LoginRequiredMixin, MaintenanceManagerRequiredMixin, CreateView):
    model = MaintenanceProgram
    form_class = MaintenanceProgramForm
    template_name = "sav/maintenance_program_form.html"
    success_url = reverse_lazy("maintenance-program")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        technicians = scope_user_queryset(
            User.objects.filter(role__in=User.TECHNICIAN_SPACE_ROLES, is_active=True),
            self.request.user,
        ).order_by("first_name", "last_name", "username")
        clients = scope_user_queryset(
            User.objects.filter(role=User.ROLE_CLIENT, is_active=True),
            self.request.user,
        ).order_by("company_name", "first_name", "last_name", "username")
        products = scope_product_queryset(Product.objects.select_related("client"), self.request.user).order_by("client__company_name", "name")
        context.update(
            {
                "maintenance_technicians": technicians[:40],
                "maintenance_clients": clients[:40],
                "maintenance_products": products[:60],
                "periodicity_choices": MaintenanceTicket.PERIODICITY_CHOICES,
                "monthly_days": range(1, 32),
            }
        )
        return context

    def form_valid(self, form):
        form.instance.responsible = self.request.user
        form.instance.organization = getattr(self.request.user, "organization", None)
        publish_now = self.request.POST.get("submit_action") == "publish"
        if not publish_now:
            form.instance.status = MaintenanceProgram.STATUS_DRAFT
        response = super().form_valid(form)
        log_audit_event(self.request.user, "maintenance_program_created_web", self.object, {"via": "portal"})
        if publish_now:
            try:
                tickets = publish_maintenance_program(self.object, actor=self.request.user)
            except ValueError as exc:
                django_messages.error(self.request, f"Programme enregistré en brouillon : {exc}")
            else:
                django_messages.success(self.request, f"Programme publié : {len(tickets)} intervention(s) générée(s).")
        else:
            django_messages.success(self.request, "Programme enregistré comme brouillon.")
        return response


class MaintenanceProgramUpdateView(LoginRequiredMixin, MaintenanceManagerRequiredMixin, UpdateView):
    model = MaintenanceProgram
    form_class = MaintenanceProgramForm
    template_name = "sav/maintenance_program_form.html"
    success_url = reverse_lazy("maintenance-program")

    def get_queryset(self):
        return scope_maintenance_program_queryset(MaintenanceProgram.objects.all(), self.request.user).exclude(
            status=MaintenanceProgram.STATUS_ARCHIVED,
        )

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        technicians = scope_user_queryset(
            User.objects.filter(role__in=User.TECHNICIAN_SPACE_ROLES, is_active=True),
            self.request.user,
        ).order_by("first_name", "last_name", "username")
        clients = scope_user_queryset(
            User.objects.filter(role=User.ROLE_CLIENT, is_active=True),
            self.request.user,
        ).order_by("company_name", "first_name", "last_name", "username")
        products = scope_product_queryset(Product.objects.select_related("client"), self.request.user).order_by("client__company_name", "name")
        context.update(
            {
                "maintenance_technicians": technicians[:40],
                "maintenance_clients": clients[:40],
                "maintenance_products": products[:60],
                "periodicity_choices": MaintenanceTicket.PERIODICITY_CHOICES,
                "monthly_days": range(1, 32),
            }
        )
        return context

    def form_valid(self, form):
        form.instance.responsible = form.instance.responsible or self.request.user
        form.instance.organization = form.instance.organization or getattr(self.request.user, "organization", None)
        publish_now = self.request.POST.get("submit_action") == "publish"
        if not publish_now and form.instance.status != MaintenanceProgram.STATUS_SUSPENDED:
            form.instance.status = MaintenanceProgram.STATUS_DRAFT
        response = super().form_valid(form)
        log_audit_event(self.request.user, "maintenance_program_updated_web", self.object, {"via": "portal"})
        if publish_now:
            try:
                tickets = publish_maintenance_program(self.object, actor=self.request.user)
            except ValueError as exc:
                django_messages.error(self.request, f"Programme enregistré : {exc}")
            else:
                django_messages.success(self.request, f"Programme publié : {len(tickets)} intervention(s) générée(s).")
        else:
            django_messages.success(self.request, "Programme de maintenance enregistré comme brouillon.")
        return response


class MaintenanceProgramPublishView(LoginRequiredMixin, MaintenanceManagerRequiredMixin, View):
    def post(self, request, pk):
        program = get_object_or_404(scope_maintenance_program_queryset(MaintenanceProgram.objects.all(), request.user), pk=pk)
        try:
            tickets = publish_maintenance_program(program, actor=request.user)
        except ValueError as exc:
            django_messages.error(request, str(exc))
            return redirect("maintenance-program")
        django_messages.success(request, f"Programme publie: {len(tickets)} ticket(s) de maintenance generes.")
        return redirect("maintenance-program")


class MaintenanceProgramStatusView(LoginRequiredMixin, MaintenanceManagerRequiredMixin, View):
    def post(self, request, pk, action):
        program = get_object_or_404(scope_maintenance_program_queryset(MaintenanceProgram.objects.all(), request.user), pk=pk)
        if action == "suspend":
            program.status = MaintenanceProgram.STATUS_SUSPENDED
            message = "Programme suspendu. Les interventions deja creees sont conservees."
        elif action == "activate":
            program.status = MaintenanceProgram.STATUS_PUBLISHED
            message = "Programme active."
        else:
            django_messages.error(request, "Action de programme inconnue.")
            return redirect("maintenance-program")
        program.save(update_fields=["status", "updated_at"])
        log_audit_event(request.user, f"maintenance_program_{action}d", program)
        django_messages.success(request, message)
        return redirect("maintenance-program")


class MaintenanceProgramDeleteView(LoginRequiredMixin, MaintenanceManagerRequiredMixin, View):
    def post(self, request, pk):
        program = get_object_or_404(scope_maintenance_program_queryset(MaintenanceProgram.objects.all(), request.user), pk=pk)
        if program.tickets.exists():
            program.status = MaintenanceProgram.STATUS_ARCHIVED
            program.save(update_fields=["status", "updated_at"])
            django_messages.success(request, "Programme archive pour conserver son historique d'interventions.")
        else:
            log_audit_event(request.user, "maintenance_program_deleted", program)
            program.delete()
            django_messages.success(request, "Programme supprime.")
        return redirect("maintenance-program")


class MaintenanceTicketStartView(LoginRequiredMixin, View):
    def post(self, request, pk):
        maintenance_ticket = get_object_or_404(
            scope_maintenance_ticket_queryset(MaintenanceTicket.objects.all(), request.user),
            pk=pk,
        )
        try:
            start_maintenance_ticket(maintenance_ticket, actor=request.user)
        except ValueError as exc:
            django_messages.error(request, str(exc))
            return redirect("technician-space")
        django_messages.success(request, "Maintenance demarree.")
        return redirect("technician-space")


class MaintenanceTicketAcknowledgeView(LoginRequiredMixin, View):
    def post(self, request, pk):
        maintenance_ticket = get_object_or_404(
            scope_maintenance_ticket_queryset(MaintenanceTicket.objects.all(), request.user),
            pk=pk,
        )
        try:
            acknowledge_maintenance_ticket(maintenance_ticket, actor=request.user)
        except ValueError as exc:
            django_messages.error(request, str(exc))
            return redirect("technician-space")
        django_messages.success(request, "Reception de la maintenance confirmee.")
        return redirect("technician-space")


class MaintenanceTicketCancelView(LoginRequiredMixin, MaintenanceManagerRequiredMixin, View):
    def post(self, request, pk):
        maintenance_ticket = get_object_or_404(
            scope_maintenance_ticket_queryset(MaintenanceTicket.objects.all(), request.user),
            pk=pk,
        )
        form = MaintenanceCancelForm(request.POST)
        if not form.is_valid():
            django_messages.error(request, "Le motif d'annulation est obligatoire.")
            return redirect("maintenance-program")
        try:
            cancel_maintenance_ticket(maintenance_ticket, reason=form.cleaned_data["reason"], actor=request.user)
        except ValueError as exc:
            django_messages.error(request, str(exc))
            return redirect("maintenance-program")
        django_messages.success(request, "Maintenance annulee avec motif archive.")
        return redirect("maintenance-program")


class MaintenanceReportValidateView(LoginRequiredMixin, MaintenanceManagerRequiredMixin, View):
    def post(self, request, pk):
        maintenance_ticket = get_object_or_404(
            scope_maintenance_ticket_queryset(
                MaintenanceTicket.objects.select_related("technician", "client").prefetch_related("team_members"),
                request.user,
            ),
            pk=pk,
        )
        try:
            validate_maintenance_report(maintenance_ticket, actor=request.user)
        except ValueError as exc:
            django_messages.error(request, str(exc))
            return redirect("maintenance-program")
        django_messages.success(request, "Rapport de maintenance valide par le responsable.")
        return redirect("maintenance-program")


class MaintenanceTicketCloseView(LoginRequiredMixin, FormView):
    template_name = "sav/maintenance_ticket_close.html"
    form_class = MaintenanceClosureForm

    def dispatch(self, request, *args, **kwargs):
        self.maintenance_ticket = get_object_or_404(
            scope_maintenance_ticket_queryset(
                MaintenanceTicket.objects.select_related("client", "technician", "responsible").prefetch_related("products", "team_members"),
                request.user,
            ),
            pk=kwargs["pk"],
        )
        if not can_act_on_maintenance_ticket(request.user, self.maintenance_ticket):
            django_messages.error(request, "Vous n'etes pas autorise a cloturer cette maintenance.")
            return redirect("technician-space")
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["maintenance_ticket"] = self.maintenance_ticket
        kwargs["user"] = self.request.user
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["maintenance_ticket"] = self.maintenance_ticket
        return context

    def form_valid(self, form):
        try:
            result = close_maintenance_ticket(
                self.maintenance_ticket,
                actor=self.request.user,
                final_status=form.cleaned_data["final_status"],
                actual_started_at=form.cleaned_data["actual_started_at"],
                actual_finished_at=form.cleaned_data["actual_finished_at"],
                checklist_completed=form.cleaned_data["checklist_completed"],
                observations=form.cleaned_data["observations"],
                actual_cost=form.cleaned_data.get("actual_cost") or 0,
                work_to_plan=form.cleaned_data.get("work_to_plan", ""),
                parts_used=form.cleaned_data.get("parts_used", ""),
                parts_status={
                    "remplacables": form.cleaned_data.get("parts_replaceable", False),
                    "ajoutables": form.cleaned_data.get("parts_addable", False),
                    "defectueuses": form.cleaned_data.get("parts_defective", False),
                },
                intervention_types=[
                    *form.cleaned_data.get("intervention_types", []),
                    *([form.cleaned_data.get("other_intervention_type", "").strip()] if form.cleaned_data.get("other_intervention_type") else []),
                ],
                spare_parts=form.cleaned_data.get("spare_parts"),
                anomaly_detected=form.cleaned_data.get("anomaly_detected", False),
                photo_files=form.cleaned_data.get("maintenance_photos", []),
                client_signed_by=form.cleaned_data.get("client_signed_by", ""),
                client_signature_file=form.cleaned_data.get("client_signature_file"),
                new_date=form.cleaned_data.get("new_date"),
                postponement_reason=form.cleaned_data.get("postponement_reason", ""),
            )
        except ValueError as exc:
            form.add_error(None, str(exc))
            return self.form_invalid(form)
        if result.get("incident_ticket"):
            django_messages.success(
                self.request,
                f"Maintenance cloturee avec anomalie. Ticket incident {result['incident_ticket'].reference} genere.",
            )
        else:
            django_messages.success(self.request, "Rapport de maintenance enregistre.")
        return redirect("technician-space" if has_technician_space_access(self.request.user) else "maintenance-program")
