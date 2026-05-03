from datetime import datetime, timedelta

from django.contrib import messages as django_messages
from django.contrib.auth import login
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db.models import Avg, Count, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, DeleteView, DetailView, FormView, ListView, TemplateView, UpdateView

from .comms import create_message_delivery_notifications, infer_attachment_kind
from .forms import (
    AnalyticsQuestionForm,
    ClientRegistrationForm,
    CreditAccountForm,
    InterventionForm,
    MessageForm,
    ProductForm,
    SupportAssistantQuestionForm,
    TicketEscalationForm,
    TicketAttachmentForm,
    TicketCreateForm,
    TicketForm,
)
from .models import (
    AIActionLog,
    AuditLog,
    EquipmentCategory,
    GeneratedReport,
    Intervention,
    InterventionMedia,
    KnowledgeArticle,
    Message,
    Notification,
    OfferRecommendation,
    PredictiveAlert,
    Product,
    SlaRule,
    TicketAttachment,
    Ticket,
    User,
)
from .reporting import REPORT_DAILY, REPORT_MONTHLY, REPORT_WEEKLY, build_report
from .services import (
    OPEN_TICKET_STATUSES,
    answer_bi_question,
    apply_agentic_resolution,
    build_customer_insight,
    can_create_ticket,
    calculate_sentiment,
    compute_agent_performance_rows,
    compute_average_first_response_hours,
    compute_average_resolution_hours,
    compute_technician_status_rows,
    compute_ticket_hotspots,
    compute_ticket_monthly_series,
    compute_ticket_sla_deadline,
    compute_ticket_volume_series,
    credit_account_for_ticket,
    create_notification,
    ensure_assignment_intervention,
    escalate_ticket,
    generate_intervention_pdf,
    has_backoffice_access,
    has_reporting_access,
    has_technician_space_access,
    is_admin_user,
    is_internal_user,
    is_manager_user,
    is_read_only_user,
    is_support_user,
    log_audit_event,
    scope_audit_log_queryset,
    scope_equipment_category_queryset,
    run_automation_rules_for_ticket,
    run_predictive_analysis,
    scope_knowledge_article_queryset,
    scope_message_queryset,
    scope_notification_queryset,
    scope_predictive_alert_queryset,
    scope_product_queryset,
    scope_attachment_queryset,
    scope_generated_report_queryset,
    scope_sla_rule_queryset,
    scope_ticket_queryset,
    scope_user_queryset,
    role_workspace_name,
    notify_ticket_status_change,
)


def _choice_map(choices):
    return dict(choices)


def _percentage(value, total):
    if not total:
        return 0
    return round((value / total) * 100, 1)


def _ticket_status_from_intervention(intervention):
    if intervention.status == Intervention.STATUS_DONE or intervention.finished_at:
        return Ticket.STATUS_INTERVENTION_DONE
    if intervention.status == Intervention.STATUS_IN_PROGRESS or intervention.started_at:
        return Ticket.STATUS_IN_PROGRESS_N2
    if intervention.status == Intervention.STATUS_CANCELLED:
        return Ticket.STATUS_WAITING
    if intervention.scheduled_for:
        return Ticket.STATUS_INTERVENTION_PLANNED
    return Ticket.STATUS_ASSIGNED if intervention.ticket.assigned_agent_id else Ticket.STATUS_NEW


def _workspace_redirect_url(user):
    workspace_name = role_workspace_name(user)
    if workspace_name == "ticket-list" and is_support_user(user):
        return f"{reverse(workspace_name)}?assignment=mine"
    return reverse(workspace_name)


def _dashboard_snapshot(user):
    tickets = scope_ticket_queryset(Ticket.objects.select_related("client", "product", "assigned_agent"), user)
    products = scope_product_queryset(Product.objects.select_related("client"), user)
    alerts = scope_predictive_alert_queryset(PredictiveAlert.objects.select_related("product", "ticket"), user)
    notifications = scope_notification_queryset(Notification.objects.select_related("ticket"), user)
    messages = Message.objects.filter(ticket__in=tickets, sentiment_score__isnull=False)
    technicians = scope_user_queryset(
        User.objects.filter(role__in=User.TECHNICIAN_SPACE_ROLES, is_active=True),
        user,
    )

    status_labels = _choice_map(Ticket.STATUS_CHOICES)
    priority_labels = _choice_map(Ticket.PRIORITY_CHOICES)

    status_rows = list(tickets.values("status").annotate(total=Count("id")).order_by("status"))
    priority_rows = list(tickets.values("priority").annotate(total=Count("id")).order_by("priority"))
    open_tickets = tickets.filter(status__in=OPEN_TICKET_STATUSES)
    total_tickets = tickets.count()
    average_first_response_hours = compute_average_first_response_hours(tickets)
    average_resolution_hours = compute_average_resolution_hours(tickets)

    return {
        "tickets_total": total_tickets,
        "tickets_open": open_tickets.count(),
        "tickets_overdue": open_tickets.filter(sla_deadline__lt=timezone.now()).count(),
        "tickets_critical_open": open_tickets.filter(priority=Ticket.PRIORITY_CRITICAL).count(),
        "tickets_unassigned": open_tickets.filter(assigned_agent__isnull=True).count(),
        "maintenance_total": tickets.filter(category=Ticket.CATEGORY_MAINTENANCE).count(),
        "bug_total": tickets.filter(category=Ticket.CATEGORY_BUG).count(),
        "products_total": products.count(),
        "products_under_warranty": products.filter(warranty_end__gte=timezone.localdate()).count(),
        "alerts_open": alerts.filter(status__in=[PredictiveAlert.STATUS_OPEN, PredictiveAlert.STATUS_IN_PROGRESS]).count(),
        "alerts_critical": alerts.filter(
            status__in=[PredictiveAlert.STATUS_OPEN, PredictiveAlert.STATUS_IN_PROGRESS],
            severity=PredictiveAlert.SEVERITY_CRITICAL,
        ).count(),
        "notifications_unread": notifications.exclude(status=Notification.STATUS_READ).count(),
        "average_sentiment": messages.aggregate(avg=Avg("sentiment_score"))["avg"],
        "average_first_response_hours": average_first_response_hours,
        "average_resolution_hours": average_resolution_hours,
        "sla_due_soon": open_tickets.filter(
            sla_deadline__gte=timezone.now(),
            sla_deadline__lte=timezone.now() + timedelta(hours=2),
        ).count(),
        "status_breakdown": [
            {
                "value": row["status"],
                "label": status_labels.get(row["status"], row["status"]),
                "total": row["total"],
                "percent": _percentage(row["total"], total_tickets or 1),
            }
            for row in status_rows
        ],
        "priority_breakdown": [
            {
                "value": row["priority"],
                "label": priority_labels.get(row["priority"], row["priority"]),
                "total": row["total"],
                "percent": _percentage(row["total"], total_tickets or 1),
            }
            for row in priority_rows
        ],
        "recent_tickets": list(tickets.order_by("-created_at")[:6]),
        "recent_alerts": list(alerts.order_by("-created_at")[:5]),
        "recent_notifications": list(notifications.order_by("-created_at")[:5]),
        "expiring_products": list(
            products.filter(
                warranty_end__gte=timezone.localdate(),
                warranty_end__lte=timezone.localdate() + timedelta(days=60),
            ).order_by("warranty_end")[:5]
        ),
        "top_agents": compute_agent_performance_rows(tickets),
        "geo_hotspots": compute_ticket_hotspots(tickets),
        "trend_7_days": compute_ticket_volume_series(tickets, days=7),
        "trend_30_days": compute_ticket_volume_series(tickets, days=30),
        "trend_12_months": compute_ticket_monthly_series(tickets, months=12),
        "technician_status_breakdown": compute_technician_status_rows(technicians),
    }


class InternalRequiredMixin(UserPassesTestMixin):
    def test_func(self):
        return is_internal_user(self.request.user)


class ManagerRequiredMixin(UserPassesTestMixin):
    def test_func(self):
        return is_manager_user(self.request.user)


class AdminRequiredMixin(UserPassesTestMixin):
    def test_func(self):
        return bool(
            self.request.user.is_authenticated
            and (self.request.user.is_superuser or self.request.user.role == User.ROLE_ADMIN)
        )


class BackofficeRequiredMixin(UserPassesTestMixin):
    def test_func(self):
        return has_backoffice_access(self.request.user) or getattr(self.request.user, "is_superuser", False)


class ReportingRequiredMixin(UserPassesTestMixin):
    def test_func(self):
        return has_reporting_access(self.request.user)


class TechnicianWorkspaceRequiredMixin(UserPassesTestMixin):
    def test_func(self):
        return has_technician_space_access(self.request.user)


class HomeRedirectView(View):
    def get(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect(_workspace_redirect_url(request.user))
        return redirect("login")


class RoleWorkspaceRedirectView(LoginRequiredMixin, View):
    def get(self, request, *args, **kwargs):
        return redirect(_workspace_redirect_url(request.user))


class ClientRegisterView(FormView):
    template_name = "sav/register.html"
    form_class = ClientRegistrationForm
    success_url = reverse_lazy("support-page")

    def form_valid(self, form):
        user = form.save()
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
        snapshot = _dashboard_snapshot(self.request.user)
        context.update(snapshot)
        context["analytics_form"] = AnalyticsQuestionForm(
            initial={"question": "Combien de tickets critiques avons-nous ?"}
        )
        context["client_insight"] = build_customer_insight(self.request.user) if self.request.user.role == User.ROLE_CLIENT else None

        if is_internal_user(self.request.user):
            context["at_risk_clients"] = list(
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
            context["at_risk_clients"] = []
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
                selected_date = datetime.fromisoformat(self.request.GET["week"]).date()
            except ValueError:
                selected_date = timezone.localdate()
        week_start = selected_date - timedelta(days=selected_date.weekday())
        week_end = week_start + timedelta(days=7)
        technicians = scope_user_queryset(
            User.objects.filter(role__in=User.ASSIGNABLE_ROLES, is_active=True),
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
                calendar_rows.append(
                    {
                        "day": day,
                        "items": day_items,
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
        internal_users = users.filter(role__in=User.INTERNAL_ROLES + User.READ_ONLY_ROLES).order_by("role", "first_name", "last_name", "username")
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
                    "superviseurs": internal_users.filter(role=User.ROLE_SUPERVISOR).count(),
                    "dispatchers": internal_users.filter(role=User.ROLE_DISPATCHER).count(),
                    "supports": internal_users.filter(role__in=User.STANDARD_SUPPORT_ROLES).count(),
                    "vip_support": internal_users.filter(role__in=User.SPECIAL_SUPPORT_ROLES).count(),
                    "techniciens": internal_users.filter(role__in=User.TECHNICAL_ROLES).count(),
                    "experts": internal_users.filter(role=User.ROLE_EXPERT).count(),
                    "cfao": internal_users.filter(role=User.ROLE_CFAO_MANAGER).count(),
                    "cfao_works": internal_users.filter(role=User.ROLE_CFAO_WORKS).count(),
                    "hvac": internal_users.filter(role=User.ROLE_HVAC_MANAGER).count(),
                    "software_owner": internal_users.filter(role=User.ROLE_SOFTWARE_OWNER).count(),
                    "qa": internal_users.filter(role=User.ROLE_QA).count(),
                    "auditeurs": internal_users.filter(role=User.ROLE_AUDITOR).count(),
                    "bots": internal_users.filter(role=User.ROLE_SYSTEM_BOT).count(),
                    "clients": clients.count(),
                },
            }
        )
        return context


class TechnicianSpaceView(LoginRequiredMixin, TechnicianWorkspaceRequiredMixin, TemplateView):
    template_name = "sav/technician_space.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        technician = self.request.user
        today = timezone.localdate()
        tickets = (
            scope_ticket_queryset(
                Ticket.objects.select_related("client", "product", "assigned_agent"),
                self.request.user,
            )
            .filter(assigned_agent=technician, status__in=OPEN_TICKET_STATUSES)
            .order_by("priority", "sla_deadline", "-created_at")
        )
        interventions_today = (
            Intervention.objects.select_related("ticket", "ticket__client", "agent")
            .filter(
                agent=technician,
                scheduled_for__date=today,
            )
            .order_by("scheduled_for", "created_at")
        )
        history_30_days = (
            Intervention.objects.select_related("ticket", "ticket__client", "agent")
            .filter(
                agent=technician,
                created_at__gte=timezone.now() - timedelta(days=30),
            )
            .order_by("-created_at")
        )
        context.update(
            {
                "technician": technician,
                "assigned_tickets": tickets,
                "sla_due_soon_tickets": tickets.filter(
                    sla_deadline__gte=timezone.now(),
                    sla_deadline__lte=timezone.now() + timedelta(hours=2),
                ),
                "interventions_today": interventions_today,
                "route_stops": [
                    {
                        "order": index + 1,
                        "reference": intervention.ticket.reference,
                        "location": intervention.location_snapshot or intervention.ticket.location or intervention.ticket.client.address,
                        "scheduled_for": intervention.scheduled_for,
                    }
                    for index, intervention in enumerate(interventions_today)
                ],
                "history_30_days": history_30_days[:20],
            }
        )
        return context


class SupportPageView(LoginRequiredMixin, TemplateView):
    template_name = "sav/support.html"

    def dispatch(self, request, *args, **kwargs):
        if has_backoffice_access(request.user):
            return redirect("ticket-list")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["support_form"] = SupportAssistantQuestionForm(user=self.request.user)
        context["recent_tickets"] = list(
            scope_ticket_queryset(
                Ticket.objects.select_related("product").prefetch_related("attachments"),
                self.request.user,
            ).order_by("-created_at")[:8]
        )
        context["open_ticket_count"] = scope_ticket_queryset(Ticket.objects.all(), self.request.user).filter(
            status__in=OPEN_TICKET_STATUSES
        ).count()
        context["ticket_create_url"] = reverse("ticket-create")
        return context


class TicketListView(LoginRequiredMixin, ListView):
    model = Ticket
    template_name = "sav/ticket_list.html"
    context_object_name = "tickets"
    paginate_by = 16

    def get_queryset(self):
        queryset = scope_ticket_queryset(
            Ticket.objects.select_related("client", "product", "assigned_agent").all(),
            self.request.user,
        )
        query = self.request.GET.get("q", "").strip()
        status_filter = self.request.GET.get("status", "").strip()
        priority_filter = self.request.GET.get("priority", "").strip()
        focus_filter = self.request.GET.get("focus", "").strip()
        assignment_filter = self.request.GET.get("assignment", "").strip()

        if query:
            queryset = queryset.filter(
                Q(reference__icontains=query)
                | Q(title__icontains=query)
                | Q(description__icontains=query)
                | Q(client__username__icontains=query)
                | Q(product_label__icontains=query)
                | Q(product__name__icontains=query)
                | Q(product__serial_number__icontains=query)
            )
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        if priority_filter:
            queryset = queryset.filter(priority=priority_filter)
        if focus_filter == "urgent":
            queryset = queryset.filter(priority__in=[Ticket.PRIORITY_HIGH, Ticket.PRIORITY_CRITICAL])
        if assignment_filter == "mine" and is_internal_user(self.request.user):
            queryset = queryset.filter(assigned_agent=self.request.user)
        if assignment_filter == "unassigned" and is_internal_user(self.request.user):
            queryset = queryset.filter(assigned_agent__isnull=True)

        return queryset.order_by("-created_at")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["filters"] = {
            "q": self.request.GET.get("q", ""),
            "status": self.request.GET.get("status", ""),
            "priority": self.request.GET.get("priority", ""),
            "focus": self.request.GET.get("focus", ""),
            "assignment": self.request.GET.get("assignment", ""),
        }
        context["status_choices"] = Ticket.STATUS_CHOICES
        context["priority_choices"] = Ticket.PRIORITY_CHOICES
        context["can_create_ticket"] = can_create_ticket(self.request.user)
        return context


class TicketCreateView(LoginRequiredMixin, CreateView):
    model = Ticket
    form_class = TicketCreateForm
    template_name = "sav/ticket_form.html"

    def dispatch(self, request, *args, **kwargs):
        if not can_create_ticket(request.user):
            django_messages.error(request, "Votre role ne permet pas de creer un ticket.")
            return redirect(_workspace_redirect_url(request.user))
        if is_read_only_user(request.user):
            django_messages.error(request, "Le profil lecture seule est limite a la consultation.")
            return redirect("ticket-list")
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def get_initial(self):
        initial = super().get_initial()
        for field_name in ["title", "description", "category", "priority", "product_label"]:
            value = self.request.GET.get(field_name, "").strip()
            if value:
                initial[field_name] = value
        product_value = self.request.GET.get("product", "").strip()
        if product_value:
            if not initial.get("product_label"):
                scoped_products = scope_product_queryset(Product.objects.all(), self.request.user)
                if product_value.isdigit():
                    product = scoped_products.filter(pk=product_value).first()
                    if product:
                        initial["product"] = product.pk
                        initial["product_label"] = product.name
                    else:
                        initial["product_label"] = product_value
                else:
                    initial["product_label"] = product_value
        return initial

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        if self.request.user.role == User.ROLE_CLIENT:
            form.instance.client = self.request.user
            form.instance.status = Ticket.STATUS_NEW
            form.instance.priority = Ticket.PRIORITY_NORMAL
            form.instance.assigned_agent = None
        else:
            try:
                form.instance.client = form.resolve_ticket_client()
            except ValueError as exc:
                form.add_error("client_email", str(exc))
                return self.form_invalid(form)
        if form.instance.assigned_agent_id:
            form.instance.status = Ticket.STATUS_ASSIGNED

        response = super().form_valid(form)

        if not self.object.sla_deadline:
            self.object.sla_deadline = compute_ticket_sla_deadline(self.object.priority, organization=self.object.organization)
            self.object.save(update_fields=["sla_deadline", "updated_at"])
        if self.object.assigned_agent_id:
            ensure_assignment_intervention(self.object, actor=self.request.user, note="Affectation initiale depuis le portail.")

        for uploaded_file in form.cleaned_data.get("initial_attachments", []):
            attachment = TicketAttachment.objects.create(
                ticket=self.object,
                organization=self.object.organization,
                uploaded_by=self.request.user,
                kind=infer_attachment_kind(uploaded_file),
                file=uploaded_file,
                note="Piece jointe ajoutee a la creation du ticket.",
            )
            log_audit_event(self.request.user, "ticket_attachment_created_web", attachment, {"ticket": self.object.reference})

        log_audit_event(self.request.user, "ticket_created_web", self.object, {"via": "portal"})
        run_automation_rules_for_ticket(self.object, actor=self.request.user)
        django_messages.success(self.request, f"Ticket {self.object.reference} cree avec succes.")
        return response

    def get_success_url(self):
        return reverse("ticket-detail", args=[self.object.pk])


class TicketUpdateView(LoginRequiredMixin, InternalRequiredMixin, UpdateView):
    model = Ticket
    form_class = TicketForm
    template_name = "sav/ticket_form.html"

    def dispatch(self, request, *args, **kwargs):
        if not (is_support_user(request.user) or is_admin_user(request.user)):
            django_messages.error(request, "Seul le support peut modifier directement un ticket.")
            return redirect("ticket-detail", pk=kwargs["pk"])
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        previous_status = self.get_object().status
        previous_assigned_agent_id = self.get_object().assigned_agent_id
        if (
            form.instance.assigned_agent_id
            and not previous_assigned_agent_id
            and form.instance.status
            in {
                Ticket.STATUS_NEW,
                Ticket.STATUS_QUALIFICATION,
                Ticket.STATUS_PENDING_CUSTOMER,
                Ticket.STATUS_WAITING,
            }
        ):
            form.instance.status = Ticket.STATUS_ASSIGNED
        response = super().form_valid(form)
        if self.object.is_open:
            self.object.sla_deadline = compute_ticket_sla_deadline(self.object.priority, organization=self.object.organization)
            self.object.save(update_fields=["sla_deadline", "updated_at"])
        if self.object.assigned_agent_id and self.object.assigned_agent_id != previous_assigned_agent_id:
            ensure_assignment_intervention(self.object, actor=self.request.user, note="Affectation mise a jour depuis le portail.")
        log_audit_event(self.request.user, "ticket_updated_web", self.object, {"via": "portal"})
        notify_ticket_status_change(self.object, previous_status, actor=self.request.user)
        run_automation_rules_for_ticket(self.object, actor=self.request.user)
        django_messages.success(self.request, f"Ticket {self.object.reference} mis a jour.")
        return response

    def get_success_url(self):
        return reverse("ticket-detail", args=[self.object.pk])


class TicketDetailView(LoginRequiredMixin, DetailView):
    model = Ticket
    template_name = "sav/ticket_detail.html"
    context_object_name = "ticket"

    def get_queryset(self):
        return scope_ticket_queryset(
            Ticket.objects.select_related("client", "product", "assigned_agent", "feedback").prefetch_related(
                "messages",
                "attachments",
                "client__contacts",
                "assignment_history",
                "interventions",
                "interventions__media",
                "support_sessions",
                "offers",
                "ai_actions",
                "account_credits",
            ),
            self.request.user,
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        ticket = self.object
        user = self.request.user
        can_support_edit = is_support_user(user) or is_admin_user(user)
        is_assigned_technician = user.role == User.ROLE_TECHNICIAN and ticket.assigned_agent_id == user.id
        can_participate = (
            not is_read_only_user(user)
            and (user.role == User.ROLE_CLIENT and ticket.client_id == user.id or can_support_edit)
        )
        context["message_form"] = MessageForm(user=user, ticket=ticket)
        context["attachment_form"] = TicketAttachmentForm()
        context["product_alerts"] = (
            ticket.product.predictive_alerts.order_by("-created_at")[:5] if ticket.product else []
        )
        context["knowledge_articles"] = (
            scope_knowledge_article_queryset(
                KnowledgeArticle.objects.filter(status=KnowledgeArticle.STATUS_PUBLISHED),
                self.request.user,
            ).filter(Q(product=ticket.product) | Q(product__isnull=True))[:4]
            if ticket.product
            else scope_knowledge_article_queryset(
                KnowledgeArticle.objects.filter(status=KnowledgeArticle.STATUS_PUBLISHED),
                self.request.user,
            )[:4]
        )
        context["offers"] = ticket.offers.order_by("-created_at")
        context["ai_actions"] = ticket.ai_actions.order_by("-created_at")
        context["visible_messages"] = scope_message_queryset(ticket.messages.all(), self.request.user)
        context["attachments"] = scope_attachment_queryset(ticket.attachments.all(), self.request.user)
        context["account_credits"] = ticket.account_credits.order_by("-executed_at") if is_admin_user(user) else []
        context["can_participate"] = can_participate
        context["can_edit"] = can_support_edit
        context["can_add_intervention"] = can_support_edit or is_assigned_technician
        context["can_credit_account"] = is_admin_user(user)
        context["can_escalate"] = can_support_edit and ticket.status in OPEN_TICKET_STATUSES
        context["escalation_form"] = TicketEscalationForm()
        context["can_confirm_resolution"] = (
            ticket.status == Ticket.STATUS_RESOLVED
            and (user.role == User.ROLE_CLIENT and ticket.client_id == user.id)
        )
        context["can_reopen"] = can_participate and ticket.status in {Ticket.STATUS_RESOLVED, Ticket.STATUS_CLOSED}
        context["client_contacts"] = ticket.client.contacts.order_by("-is_primary", "first_name", "last_name")[:8]
        context["assignment_history"] = ticket.assignment_history.select_related("technician", "assigned_by").all()[:12]
        context["intervention_form"] = InterventionForm(
            user=user,
            ticket=ticket,
            initial={
                "agent": ticket.assigned_agent or (user if is_internal_user(user) else None),
                "status": Intervention.STATUS_PLANNED,
                "scheduled_for": timezone.now(),
                "location_snapshot": ticket.location,
            },
        )
        context["credit_form"] = CreditAccountForm(
            initial={
                "currency": "XAF",
                "reason": f"Avoir commercial {ticket.reference}",
            }
        )
        return context


class TicketConfirmResolutionView(LoginRequiredMixin, View):
    def post(self, request, pk):
        ticket = get_object_or_404(scope_ticket_queryset(Ticket.objects.all(), request.user), pk=pk)
        if is_read_only_user(request.user):
            django_messages.error(request, "Le profil lecture seule est limite a la consultation.")
            return redirect("ticket-detail", pk=pk)
        if request.user.role == User.ROLE_CLIENT and ticket.client_id != request.user.id:
            django_messages.error(request, "Vous ne pouvez valider que vos propres tickets.")
            return redirect("ticket-detail", pk=pk)
        if ticket.status != Ticket.STATUS_RESOLVED:
            django_messages.error(request, "Seuls les tickets resolus peuvent etre fermes par validation client.")
            return redirect("ticket-detail", pk=pk)

        previous_status = ticket.status
        ticket.status = Ticket.STATUS_CLOSED
        ticket.closed_at = timezone.now()
        ticket.save(update_fields=["status", "closed_at", "updated_at"])
        Message.objects.create(
            ticket=ticket,
            sender=request.user,
            message_type=Message.TYPE_PUBLIC,
            channel=Message.CHANNEL_PORTAL,
            direction=Message.DIRECTION_INBOUND if request.user.role == User.ROLE_CLIENT else Message.DIRECTION_INTERNAL,
            content="Le client a valide la resolution. Le dossier est ferme.",
            sentiment_score=calculate_sentiment("Le client a valide la resolution."),
        )
        log_audit_event(request.user, "ticket_resolution_confirmed_web", ticket, {"via": "portal"})
        notify_ticket_status_change(ticket, previous_status, actor=request.user)
        django_messages.success(request, "La resolution a ete validee et le ticket est maintenant ferme.")
        return redirect("ticket-detail", pk=pk)


class TicketReopenView(LoginRequiredMixin, View):
    def post(self, request, pk):
        ticket = get_object_or_404(scope_ticket_queryset(Ticket.objects.all(), request.user), pk=pk)
        if is_read_only_user(request.user):
            django_messages.error(request, "Le profil lecture seule est limite a la consultation.")
            return redirect("ticket-detail", pk=pk)
        if ticket.status not in {Ticket.STATUS_RESOLVED, Ticket.STATUS_CLOSED}:
            django_messages.error(request, "Seuls les tickets resolus ou fermes peuvent etre rouverts.")
            return redirect("ticket-detail", pk=pk)

        previous_status = ticket.status
        if request.user.role == User.ROLE_CLIENT:
            ticket.status = Ticket.STATUS_NEW
        elif ticket.assigned_agent_id:
            ticket.status = Ticket.STATUS_ASSIGNED
        else:
            ticket.status = Ticket.STATUS_NEW
        ticket.resolved_at = None
        ticket.closed_at = None
        ticket.save(update_fields=["status", "resolved_at", "closed_at", "updated_at"])
        Message.objects.create(
            ticket=ticket,
            sender=request.user,
            message_type=Message.TYPE_PUBLIC if request.user.role == User.ROLE_CLIENT else Message.TYPE_INTERNAL,
            channel=Message.CHANNEL_PORTAL,
            direction=Message.DIRECTION_INBOUND if request.user.role == User.ROLE_CLIENT else Message.DIRECTION_INTERNAL,
            content="Le ticket a ete rouvert pour reprise en charge.",
            sentiment_score=calculate_sentiment("Le ticket a ete rouvert pour reprise en charge."),
        )
        log_audit_event(request.user, "ticket_reopened_web", ticket, {"via": "portal"})
        notify_ticket_status_change(ticket, previous_status, actor=request.user)
        django_messages.success(request, "Le ticket a ete rouvert.")
        return redirect("ticket-detail", pk=pk)


class TicketEscalateView(LoginRequiredMixin, View):
    def post(self, request, pk):
        ticket = get_object_or_404(scope_ticket_queryset(Ticket.objects.all(), request.user), pk=pk)
        if not is_internal_user(request.user) or is_read_only_user(request.user):
            django_messages.error(request, "Seuls les profils internes peuvent escalader un ticket.")
            return redirect("ticket-detail", pk=pk)

        form = TicketEscalationForm(request.POST)
        if not form.is_valid():
            django_messages.error(request, "Choisissez une cible d'escalade valide.")
            return redirect("ticket-detail", pk=pk)

        previous_status = ticket.status
        try:
            result = escalate_ticket(
                ticket,
                actor=request.user,
                note=form.cleaned_data.get("note", ""),
                target=form.cleaned_data["target"],
            )
        except ValueError as exc:
            django_messages.error(request, str(exc))
            return redirect("ticket-detail", pk=pk)

        if ticket.status != previous_status:
            notify_ticket_status_change(ticket, previous_status, actor=request.user)

        if result.get("assigned_agent"):
            django_messages.success(
                request,
                f"Le ticket a ete escalade vers {result['assigned_agent']} avec priorite {ticket.get_priority_display().lower()}.",
            )
        else:
            django_messages.success(
                request,
                f"Le ticket a ete escalade avec priorite {ticket.get_priority_display().lower()}.",
            )
        return redirect("ticket-detail", pk=pk)


class TicketMessageCreateView(LoginRequiredMixin, View):
    def post(self, request, pk):
        ticket = get_object_or_404(scope_ticket_queryset(Ticket.objects.all(), request.user), pk=pk)
        if is_read_only_user(request.user):
            django_messages.error(request, "Le profil lecture seule est limite a la consultation.")
            return redirect("ticket-detail", pk=pk)
        form = MessageForm(request.POST, user=request.user, ticket=ticket)
        if not form.is_valid():
            django_messages.error(request, "Impossible d'ajouter le message. Verifiez les champs.")
            return redirect("ticket-detail", pk=pk)

        direction = Message.DIRECTION_OUTBOUND if is_internal_user(request.user) else Message.DIRECTION_INBOUND
        message_type = form.cleaned_data["message_type"] if is_internal_user(request.user) else Message.TYPE_PUBLIC

        message = form.save(commit=False)
        message.ticket = ticket
        message.sender = request.user
        message.recipient = form.cleaned_data.get("recipient")
        message.direction = direction
        message.channel = form.cleaned_data["channel"] if is_internal_user(request.user) else Message.CHANNEL_PORTAL
        message.message_type = message_type
        message.sentiment_score = calculate_sentiment(message.content)
        message.save()

        if is_internal_user(request.user) and ticket.first_response_at is None:
            ticket.first_response_at = timezone.now()
            ticket.save(update_fields=["first_response_at", "updated_at"])

        if message.recipient_id:
            create_notification(
                recipient=message.recipient,
                subject=f"{ticket.reference} - Nouveau message",
                message=message.content,
                event_type="ticket_message",
                ticket=ticket,
            )
        elif direction == Message.DIRECTION_OUTBOUND and message_type == Message.TYPE_PUBLIC:
            create_message_delivery_notifications(message)

        log_audit_event(request.user, "ticket_message_created_web", message, {"ticket": ticket.reference})
        django_messages.success(request, "Message ajoute au dossier.")
        return redirect("ticket-detail", pk=pk)


class TicketAgenticResolutionView(LoginRequiredMixin, InternalRequiredMixin, View):
    def post(self, request, pk):
        ticket = get_object_or_404(scope_ticket_queryset(Ticket.objects.all(), request.user), pk=pk)
        result = apply_agentic_resolution(ticket, approved_by=request.user)
        summary = result["resolution_summary"] or "Analyse IA terminee."
        django_messages.success(request, summary)
        return redirect("ticket-detail", pk=pk)


class TicketAttachmentCreateView(LoginRequiredMixin, View):
    def post(self, request, pk):
        ticket = get_object_or_404(scope_ticket_queryset(Ticket.objects.all(), request.user), pk=pk)
        if is_read_only_user(request.user):
            django_messages.error(request, "Le profil lecture seule est limite a la consultation.")
            return redirect("ticket-detail", pk=pk)
        form = TicketAttachmentForm(request.POST, request.FILES)
        if not form.is_valid():
            django_messages.error(request, "Impossible d'ajouter la piece jointe.")
            return redirect("ticket-detail", pk=pk)

        attachment = form.save(commit=False)
        attachment.ticket = ticket
        attachment.organization = ticket.organization
        attachment.uploaded_by = request.user
        attachment.save()
        log_audit_event(request.user, "ticket_attachment_created_web", attachment, {"ticket": ticket.reference})
        django_messages.success(request, "Piece jointe enregistree sur le dossier.")
        return redirect("ticket-detail", pk=pk)


class TicketInterventionCreateView(LoginRequiredMixin, InternalRequiredMixin, View):
    def post(self, request, pk):
        ticket = get_object_or_404(scope_ticket_queryset(Ticket.objects.all(), request.user), pk=pk)
        if request.user.role == User.ROLE_TECHNICIAN and ticket.assigned_agent_id != request.user.id:
            django_messages.error(request, "Vous ne pouvez intervenir que sur les tickets qui vous sont affectes.")
            return redirect("ticket-detail", pk=pk)
        form = InterventionForm(request.POST, request.FILES, user=request.user, ticket=ticket)
        if not form.is_valid():
            django_messages.error(request, "Impossible d'enregistrer l'intervention. Verifiez les champs saisis.")
            return redirect("ticket-detail", pk=pk)

        intervention = form.save(commit=False)
        intervention.ticket = ticket
        intervention.organization = ticket.organization
        if request.user.role == User.ROLE_TECHNICIAN:
            intervention.agent = request.user
            intervention.intervention_type = Intervention.TYPE_ON_SITE
        if not intervention.location_snapshot:
            intervention.location_snapshot = ticket.location
        intervention.save()

        for uploaded_file in form.cleaned_data.get("intervention_media", []):
            intervention.media.create(
                organization=ticket.organization,
                uploaded_by=request.user,
                kind=InterventionMedia.KIND_OTHER,
                file=uploaded_file,
                note="Piece terrain ajoutee depuis le portail.",
            )

        generate_intervention_pdf(intervention)
        previous_status = ticket.status
        next_status = _ticket_status_from_intervention(intervention)
        if next_status != previous_status:
            ticket.status = next_status
            ticket.save(update_fields=["status", "updated_at"])
            notify_ticket_status_change(ticket, previous_status, actor=request.user)
        log_audit_event(request.user, "intervention_created_web", intervention, {"ticket": ticket.reference})
        django_messages.success(request, "Intervention enregistree et bon PDF genere.")
        return redirect("ticket-detail", pk=pk)


class TicketInterventionPdfView(LoginRequiredMixin, InternalRequiredMixin, View):
    def get(self, request, ticket_pk, intervention_pk):
        ticket = get_object_or_404(scope_ticket_queryset(Ticket.objects.all(), request.user), pk=ticket_pk)
        intervention = get_object_or_404(ticket.interventions.select_related("agent"), pk=intervention_pk)
        content = generate_intervention_pdf(intervention, persist=False)
        response = HttpResponse(content, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="intervention-{ticket.reference}-{intervention.pk}.pdf"'
        return response


class TicketAutomationRunView(LoginRequiredMixin, InternalRequiredMixin, View):
    def post(self, request, pk):
        ticket = get_object_or_404(scope_ticket_queryset(Ticket.objects.all(), request.user), pk=pk)
        result = run_automation_rules_for_ticket(ticket, actor=request.user)
        django_messages.success(request, f"Workflow execute sur {len(result['executions'])} element(s).")
        return redirect("ticket-detail", pk=pk)


class TicketCreditAccountView(LoginRequiredMixin, AdminRequiredMixin, View):
    def post(self, request, pk):
        ticket = get_object_or_404(scope_ticket_queryset(Ticket.objects.all(), request.user), pk=pk)
        form = CreditAccountForm(request.POST)
        if not form.is_valid():
            django_messages.error(request, "Impossible de crediter le compte. Verifiez le formulaire.")
            return redirect("ticket-detail", pk=pk)

        try:
            credit_account_for_ticket(
                ticket,
                amount=form.cleaned_data["amount"],
                actor=request.user,
                reason=form.cleaned_data["reason"],
                note=form.cleaned_data["note"],
                currency=form.cleaned_data["currency"],
                external_reference=form.cleaned_data["external_reference"],
            )
        except ValueError as exc:
            django_messages.error(request, str(exc))
            return redirect("ticket-detail", pk=pk)

        django_messages.success(request, "Le compte du client a ete credite et trace dans le workflow.")
        return redirect("ticket-detail", pk=pk)


class ProductListView(LoginRequiredMixin, ListView):
    model = Product
    template_name = "sav/product_list.html"
    context_object_name = "products"
    paginate_by = 16

    def get_queryset(self):
        queryset = scope_product_queryset(Product.objects.select_related("client").all(), self.request.user)
        query = self.request.GET.get("q", "").strip()
        if query:
            queryset = queryset.filter(
                Q(name__icontains=query)
                | Q(serial_number__icontains=query)
                | Q(sku__icontains=query)
                | Q(client__username__icontains=query)
            )
        return queryset.order_by("name")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["q"] = self.request.GET.get("q", "")
        context["can_create_product"] = bool(
            self.request.user.is_authenticated
            and (self.request.user.is_superuser or self.request.user.role == User.ROLE_ADMIN)
        )
        return context


class ProductCreateView(LoginRequiredMixin, AdminRequiredMixin, CreateView):
    model = Product
    form_class = ProductForm
    template_name = "sav/product_form.html"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        client = form.cleaned_data["client"]
        form.instance.organization = client.organization
        response = super().form_valid(form)
        log_audit_event(self.request.user, "product_created_web", self.object, {"via": "portal"})
        django_messages.success(self.request, f"Produit {self.object.name} enregistre avec succes.")
        return response

    def get_success_url(self):
        return reverse("product-detail", args=[self.object.pk])


class ProductUpdateView(LoginRequiredMixin, AdminRequiredMixin, UpdateView):
    model = Product
    form_class = ProductForm
    template_name = "sav/product_form.html"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def get_queryset(self):
        return scope_product_queryset(Product.objects.select_related("client", "equipment_category"), self.request.user)

    def form_valid(self, form):
        client = form.cleaned_data["client"]
        form.instance.organization = client.organization
        response = super().form_valid(form)
        log_audit_event(self.request.user, "product_updated_web", self.object, {"via": "portal"})
        django_messages.success(self.request, f"Produit {self.object.name} mis a jour.")
        return response

    def get_success_url(self):
        return reverse("product-detail", args=[self.object.pk])


class ProductDeleteView(LoginRequiredMixin, AdminRequiredMixin, DeleteView):
    model = Product
    template_name = "sav/product_confirm_delete.html"
    success_url = reverse_lazy("product-list")

    def get_queryset(self):
        return scope_product_queryset(Product.objects.select_related("client"), self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["related_ticket_count"] = self.object.tickets.count()
        context["predictive_alert_count"] = self.object.predictive_alerts.count()
        return context

    def form_valid(self, form):
        product = self.object
        product_reference = str(product)
        log_audit_event(
            self.request.user,
            "product_deleted_web",
            target_model=product._meta.label_lower,
            target_id=product.pk,
            target_reference=product_reference,
            details={"via": "portal"},
        )
        django_messages.success(self.request, f"Produit {product.name} supprime.")
        return super().form_valid(form)


class ProductDetailView(LoginRequiredMixin, DetailView):
    model = Product
    template_name = "sav/product_detail.html"
    context_object_name = "product"

    def get_queryset(self):
        return scope_product_queryset(
            Product.objects.select_related("client").prefetch_related("telemetry", "predictive_alerts", "tickets"),
            self.request.user,
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        product = self.object
        context["can_manage_product"] = bool(
            self.request.user.is_authenticated
            and (self.request.user.is_superuser or self.request.user.role == User.ROLE_ADMIN)
        )
        context["telemetry_points"] = product.telemetry.order_by("-captured_at")[:20]
        context["predictive_alerts"] = product.predictive_alerts.order_by("-created_at")[:12]
        context["recent_tickets"] = scope_ticket_queryset(
            product.tickets.select_related("assigned_agent").all(),
            self.request.user,
        ).order_by("-created_at")[:8]
        context["knowledge_articles"] = product.knowledge_articles.filter(status=KnowledgeArticle.STATUS_PUBLISHED)[:6]
        return context


class ProductPredictiveAnalysisView(LoginRequiredMixin, InternalRequiredMixin, View):
    def post(self, request, pk):
        product = get_object_or_404(scope_product_queryset(Product.objects.all(), request.user), pk=pk)
        result = run_predictive_analysis(product, approved_by=request.user)
        django_messages.success(request, f"Analyse predictive terminee. {len(result['alerts_created'])} alerte(s) detectee(s).")
        return redirect("product-detail", pk=pk)


class PredictiveAlertListView(LoginRequiredMixin, ListView):
    model = PredictiveAlert
    template_name = "sav/alert_list.html"
    context_object_name = "alerts"
    paginate_by = 16

    def get_queryset(self):
        queryset = scope_predictive_alert_queryset(
            PredictiveAlert.objects.select_related("product", "ticket"),
            self.request.user,
        )
        status_filter = self.request.GET.get("status", "").strip()
        severity_filter = self.request.GET.get("severity", "").strip()
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        if severity_filter:
            queryset = queryset.filter(severity=severity_filter)
        return queryset.order_by("-created_at")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["status_filter"] = self.request.GET.get("status", "")
        context["severity_filter"] = self.request.GET.get("severity", "")
        context["status_choices"] = PredictiveAlert.STATUS_CHOICES
        context["severity_choices"] = PredictiveAlert.SEVERITY_CHOICES
        return context


class KnowledgeArticleListView(LoginRequiredMixin, ListView):
    model = KnowledgeArticle
    template_name = "sav/knowledge_list.html"
    context_object_name = "articles"
    paginate_by = 16

    def get_queryset(self):
        queryset = scope_knowledge_article_queryset(KnowledgeArticle.objects.select_related("product").all(), self.request.user)
        query = self.request.GET.get("q", "").strip()
        if query:
            queryset = queryset.filter(
                Q(title__icontains=query)
                | Q(summary__icontains=query)
                | Q(content__icontains=query)
                | Q(keywords__icontains=query)
            )
        return queryset.order_by("title")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["q"] = self.request.GET.get("q", "")
        return context


class KnowledgeArticleDetailView(LoginRequiredMixin, DetailView):
    model = KnowledgeArticle
    template_name = "sav/knowledge_detail.html"
    context_object_name = "article"
    slug_field = "slug"
    slug_url_kwarg = "slug"

    def get_queryset(self):
        return scope_knowledge_article_queryset(KnowledgeArticle.objects.select_related("product").all(), self.request.user)


class NotificationListView(LoginRequiredMixin, ListView):
    model = Notification
    template_name = "sav/notification_list.html"
    context_object_name = "notifications"
    paginate_by = 20

    def get_queryset(self):
        return scope_notification_queryset(Notification.objects.select_related("ticket"), self.request.user).order_by("-created_at")


class NotificationMarkReadView(LoginRequiredMixin, View):
    def post(self, request, pk):
        notification = get_object_or_404(scope_notification_queryset(Notification.objects.all(), request.user), pk=pk)
        notification.status = Notification.STATUS_READ
        notification.read_at = timezone.now()
        notification.save(update_fields=["status", "read_at"])
        log_audit_event(request.user, "notification_marked_read_web", notification, {"via": "portal"})
        return redirect("notifications")


class AnalyticsPageView(LoginRequiredMixin, ReportingRequiredMixin, FormView):
    template_name = "sav/analytics.html"
    form_class = AnalyticsQuestionForm

    def form_valid(self, form):
        answer = answer_bi_question(form.cleaned_data["question"], self.request.user)
        context = self.get_context_data(form=form, answer=answer)
        return self.render_to_response(context)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if "answer" not in context:
            context["answer"] = None
        return context
