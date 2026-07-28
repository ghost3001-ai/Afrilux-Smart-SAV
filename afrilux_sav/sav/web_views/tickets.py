from django.contrib import messages as django_messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, DeleteView, DetailView, FormView, ListView, TemplateView, UpdateView

from ..comms import create_message_delivery_notifications, infer_attachment_kind
from ..forms import (
    CreditAccountForm,
    InterventionForm,
    MessageForm,
    SupportAssistantQuestionForm,
    TicketAttachmentForm,
    TicketClosureForm,
    TicketCreateForm,
    TicketEscalationDeclineForm,
    TicketEscalationForm,
    TicketEscalationSolutionForm,
    TicketFeedbackForm,
    TicketForm,
    TicketPlanningForm,
    TicketTeamAssignmentForm,
    TicketTechnicianAssignmentForm,
    TicketValidationBypassForm,
)
from ..models import (
    Intervention,
    InterventionMedia,
    KnowledgeArticle,
    Message,
    Notification,
    PredictiveAlert,
    Product,
    TicketAttachment,
    TicketFeedback,
    Ticket,
    User,
)
from ..services import (
    OPEN_TICKET_STATUSES,
    apply_agentic_resolution,
    assign_ticket_to_technician,
    assign_ticket_to_team,
    build_customer_insight,
    can_assign_ticket_technician,
    can_create_ticket,
    can_drive_ticket_workflow,
    can_participate_in_ticket_conversation,
    can_record_ticket_intervention,
    calculate_sentiment,
    compute_technician_availability_rows,
    compute_ticket_sla_deadline,
    continue_after_escalation_solution,
    credit_account_for_ticket,
    decline_ticket_escalation,
    escalate_ticket,
    ensure_assignment_intervention,
    close_sav_dossier,
    confirm_planning,
    generate_intervention_pdf,
    has_backoffice_access,
    is_admin_user,
    is_internal_user,
    is_manager_user,
    is_read_only_user,
    log_audit_event,
    notify_client_created_ticket,
    notify_ticket_status_change,
    propose_planning,
    provide_escalation_solution,
    request_finish_intervention,
    request_start_intervention,
    request_ticket_escalation,
    record_intervention_part_usages,
    run_automation_rules_for_ticket,
    scope_attachment_queryset,
    scope_knowledge_article_queryset,
    scope_message_queryset,
    scope_product_queryset,
    scope_ticket_queryset,
    scope_user_queryset,
    validate_finish_intervention,
    validate_start_intervention,
)
from .base import (
    AdminRequiredMixin,
    InternalRequiredMixin,
    _ticket_status_from_intervention,
    _workspace_redirect_url,
)


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
            form.instance.status = Ticket.STATUS_PENDING_ASSIGNMENT
            form.instance.priority = Ticket.PRIORITY_NORMAL
            form.instance.assigned_agent = None
            form.instance.channel = Ticket.CHANNEL_WEB
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
        elif self.request.user.role == User.ROLE_HEAD_SAV and form.cleaned_data.get("initial_escalation_target"):
            previous_status = self.object.status
            try:
                escalate_ticket(
                    self.object,
                    actor=self.request.user,
                    target=form.cleaned_data["initial_escalation_target"],
                    note="Escalade initiale depuis la creation du ticket.",
                    increase_priority=False,
                    notification_event_type="ticket_initial_escalation",
                )
            except ValueError as exc:
                form.add_error("initial_escalation_target", str(exc))
                return self.form_invalid(form)
            if self.object.status != previous_status:
                notify_ticket_status_change(self.object, previous_status, actor=self.request.user)

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
        if self.request.user.role == User.ROLE_CLIENT and self.object.status == Ticket.STATUS_PENDING_ASSIGNMENT:
            notify_client_created_ticket(self.object, actor=self.request.user)
        run_automation_rules_for_ticket(self.object, actor=self.request.user)
        if self.request.user.role == User.ROLE_CLIENT and self.object.status == Ticket.STATUS_PENDING_ASSIGNMENT:
            django_messages.success(
                self.request,
                f"Demande {self.object.reference} envoyee au Responsable SAV. Vous pouvez suivre son etat depuis cette fiche.",
            )
        else:
            django_messages.success(self.request, f"Ticket {self.object.reference} cree avec succes.")
        return response

    def get_success_url(self):
        return reverse("ticket-detail", args=[self.object.pk])


class TicketUpdateView(LoginRequiredMixin, InternalRequiredMixin, UpdateView):
    model = Ticket
    form_class = TicketForm
    template_name = "sav/ticket_form.html"

    def dispatch(self, request, *args, **kwargs):
        if request.user.role != User.ROLE_HEAD_SAV:
            django_messages.error(request, "Seul le responsable SAV peut modifier directement un ticket.")
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
                Ticket.STATUS_PENDING_ASSIGNMENT,
                Ticket.STATUS_WAITING_PART,
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
        can_support_edit = is_manager_user(user)
        is_assigned_technician = can_record_ticket_intervention(user, ticket)
        workflow_driver = can_drive_ticket_workflow(user, ticket)
        is_client_owner = user.role == User.ROLE_CLIENT and ticket.client_id == user.id
        terminal_statuses = {Ticket.STATUS_DONE, Ticket.STATUS_RESOLVED, Ticket.STATUS_CLOSED, Ticket.STATUS_CANCELLED}
        can_participate = not is_read_only_user(user) and can_participate_in_ticket_conversation(user, ticket)
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
        context["can_edit"] = can_support_edit and ticket.status != Ticket.STATUS_CLOSED
        context["can_add_intervention"] = False
        context["can_credit_account"] = is_admin_user(user)
        context["can_escalate"] = (
            is_internal_user(user)
            and not is_read_only_user(user)
            and ticket.status not in terminal_statuses
            and ticket.status != Ticket.STATUS_BLOCKED_DIRECTION
            and can_record_ticket_intervention(user, ticket)
        )
        context["escalation_form"] = TicketEscalationForm()
        context["can_assign_technician"] = can_assign_ticket_technician(user, ticket) and ticket.status in OPEN_TICKET_STATUSES
        context["technician_assignment_form"] = TicketTechnicianAssignmentForm(user=user, ticket=ticket)
        context["team_assignment_form"] = TicketTeamAssignmentForm(user=user, ticket=ticket)
        context["technician_availability"] = (
            compute_technician_availability_rows(ticket.organization) if context["can_assign_technician"] else []
        )
        context["can_confirm_resolution"] = (
            ticket.status == Ticket.STATUS_RESOLVED
            and (user.role == User.ROLE_CLIENT and ticket.client_id == user.id)
        )
        context["can_submit_feedback"] = (
            user.role == User.ROLE_CLIENT
            and ticket.client_id == user.id
            and ticket.status in {Ticket.STATUS_RESOLVED, Ticket.STATUS_CLOSED}
            and not hasattr(ticket, "feedback")
        )
        context["feedback_form"] = TicketFeedbackForm()
        context["can_reopen"] = can_participate and ticket.status in {Ticket.STATUS_RESOLVED, Ticket.STATUS_CLOSED}
        context["client_contacts"] = ticket.client.contacts.order_by("-is_primary", "first_name", "last_name")[:8]
        context["assignment_history"] = ticket.assignment_history.select_related("technician", "assigned_by").all()[:12]
        latest_intervention = ticket.interventions.order_by("-created_at").first()
        context["latest_intervention"] = latest_intervention
        context["workflow_driver"] = workflow_driver
        context["is_client_owner"] = is_client_owner
        context["public_status"] = ticket.public_status
        context["can_plan_intervention"] = workflow_driver and ticket.status in {
            Ticket.STATUS_ASSIGNED,
            Ticket.STATUS_TEAM_READY,
            Ticket.STATUS_PLANNING_PROPOSED,
        }
        context["can_validate_planning"] = is_client_owner and ticket.status == Ticket.STATUS_PLANNING_PROPOSED
        context["can_request_start"] = workflow_driver and ticket.status in {
            Ticket.STATUS_ASSIGNED,
            Ticket.STATUS_TEAM_READY,
            Ticket.STATUS_PLANNED,
            Ticket.STATUS_WAITING_PART,
        }
        context["can_validate_start"] = is_client_owner and ticket.status == Ticket.STATUS_START_REQUESTED
        context["can_bypass_start"] = workflow_driver and ticket.status == Ticket.STATUS_START_REQUESTED
        context["can_request_finish"] = workflow_driver and ticket.status in {
            Ticket.STATUS_IN_PROGRESS,
            Ticket.STATUS_COLLECTIVE_IN_PROGRESS,
        }
        context["can_validate_finish"] = is_client_owner and ticket.status == Ticket.STATUS_FINISH_REQUESTED
        context["can_bypass_finish"] = workflow_driver and ticket.status == Ticket.STATUS_FINISH_REQUESTED
        context["can_close_dossier"] = is_assigned_technician and ticket.status == Ticket.STATUS_DONE
        context["can_answer_escalation"] = is_manager_user(user) and ticket.status == Ticket.STATUS_ESCALATED
        context["can_continue_solution"] = workflow_driver and ticket.status == Ticket.STATUS_WAITING_SOLUTION
        context["planning_form"] = TicketPlanningForm()
        context["validation_bypass_form"] = TicketValidationBypassForm()
        context["closure_form"] = TicketClosureForm(
            initial={
                "client_name": str(ticket.client),
                "parts_used": getattr(latest_intervention, "parts_used", "") if latest_intervention else "",
            }
        )
        context["escalation_solution_form"] = TicketEscalationSolutionForm()
        context["escalation_decline_form"] = TicketEscalationDeclineForm()
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
        if ticket.organization and ticket.organization.personal_data_access_logging_enabled:
            log_audit_event(
                user,
                "personal_data_viewed",
                ticket,
                {"surface": "ticket_detail", "client_id": ticket.client_id},
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


class TicketFeedbackCreateView(LoginRequiredMixin, View):
    def post(self, request, pk):
        ticket = get_object_or_404(scope_ticket_queryset(Ticket.objects.select_related("client"), request.user), pk=pk)
        if request.user.role != User.ROLE_CLIENT or ticket.client_id != request.user.id:
            django_messages.error(request, "Seul le client proprietaire peut evaluer ce ticket.")
            return redirect("ticket-detail", pk=pk)
        if ticket.status not in {Ticket.STATUS_RESOLVED, Ticket.STATUS_CLOSED}:
            django_messages.error(request, "L'evaluation est disponible apres resolution ou fermeture.")
            return redirect("ticket-detail", pk=pk)
        if hasattr(ticket, "feedback"):
            django_messages.info(request, "Une evaluation existe deja pour ce ticket.")
            return redirect("ticket-detail", pk=pk)
        form = TicketFeedbackForm(request.POST)
        if not form.is_valid():
            django_messages.error(request, "Impossible d'enregistrer l'evaluation. Verifiez votre choix.")
            return redirect("ticket-detail", pk=pk)
        feedback = form.save(commit=False)
        feedback.ticket = ticket
        feedback.client = request.user
        feedback.organization = ticket.organization
        feedback.submitted_at = timezone.now()
        feedback.save()
        log_audit_event(request.user, "ticket_feedback_created_web", feedback, {"ticket_reference": ticket.reference})
        django_messages.success(request, "Merci, votre evaluation a ete enregistree.")
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
            django_messages.error(request, "Le motif d'escalade est obligatoire.")
            return redirect("ticket-detail", pk=pk)

        previous_status = ticket.status
        try:
            target = (form.cleaned_data.get("target") or "").strip()
            if target:
                result = escalate_ticket(
                    ticket,
                    actor=request.user,
                    note=form.cleaned_data.get("note", ""),
                    target=target,
                )
            else:
                result = request_ticket_escalation(
                    ticket,
                    actor=request.user,
                    reason=form.cleaned_data.get("note", ""),
                )
        except ValueError as exc:
            django_messages.error(request, str(exc))
            return redirect("ticket-detail", pk=pk)

        if ticket.status != previous_status:
            notify_ticket_status_change(ticket, previous_status, actor=request.user)

        if result.get("notified_leader"):
            django_messages.success(request, "Le chef d'equipe a ete notifie avant escalade responsable.")
        elif ticket.status == Ticket.STATUS_BLOCKED_DIRECTION:
            django_messages.warning(request, "Le maximum d'escalades est atteint. Le ticket est bloque pour arbitrage direction.")
        else:
            django_messages.success(request, "La demande d'aide a ete transmise au responsable SAV.")
        return redirect("ticket-detail", pk=pk)


class TicketAssignTechnicianView(LoginRequiredMixin, View):
    def post(self, request, pk):
        ticket = get_object_or_404(scope_ticket_queryset(Ticket.objects.all(), request.user), pk=pk)
        form = TicketTechnicianAssignmentForm(request.POST, user=request.user, ticket=ticket)
        if not form.is_valid():
            django_messages.error(request, "Choisissez un technicien disponible.")
            return redirect("ticket-detail", pk=pk)

        previous_status = ticket.status
        try:
            result = assign_ticket_to_technician(
                ticket,
                form.cleaned_data["technician"],
                actor=request.user,
                note=form.cleaned_data.get("note", ""),
                force=form.cleaned_data.get("force_assignment", False),
                force_reason=form.cleaned_data.get("force_reason", ""),
            )
        except ValueError as exc:
            django_messages.error(request, str(exc))
            return redirect("ticket-detail", pk=pk)

        if ticket.status != previous_status:
            notify_ticket_status_change(ticket, previous_status, actor=request.user)
        django_messages.success(request, f"Le ticket a ete affecte a {result['assigned_agent']}.")
        return redirect("ticket-detail", pk=pk)


class TicketAssignTeamView(LoginRequiredMixin, View):
    def post(self, request, pk):
        ticket = get_object_or_404(scope_ticket_queryset(Ticket.objects.all(), request.user), pk=pk)
        form = TicketTeamAssignmentForm(request.POST, user=request.user, ticket=ticket)
        if not form.is_valid():
            django_messages.error(request, "Choisissez exactement un chef et au moins un membre disponible.")
            return redirect("ticket-detail", pk=pk)

        previous_status = ticket.status
        try:
            result = assign_ticket_to_team(
                ticket,
                leader=form.cleaned_data["leader"],
                members=form.cleaned_data["members"],
                actor=request.user,
                note=form.cleaned_data.get("note", ""),
                force=form.cleaned_data.get("force_assignment", False),
                force_reason=form.cleaned_data.get("force_reason", ""),
            )
        except ValueError as exc:
            django_messages.error(request, str(exc))
            return redirect("ticket-detail", pk=pk)

        notify_ticket_status_change(ticket, previous_status, actor=request.user)
        django_messages.success(request, f"Equipe constituee avec {result['leader']} comme chef.")
        return redirect("ticket-detail", pk=pk)


class TicketPlanningProposeView(LoginRequiredMixin, View):
    def post(self, request, pk):
        ticket = get_object_or_404(scope_ticket_queryset(Ticket.objects.all(), request.user), pk=pk)
        form = TicketPlanningForm(request.POST)
        if not form.is_valid():
            django_messages.error(request, "Renseignez une date et heure de debut valides.")
            return redirect("ticket-detail", pk=pk)
        previous_status = ticket.status
        try:
            propose_planning(ticket, form.cleaned_data["scheduled_at"], actor=request.user)
        except ValueError as exc:
            django_messages.error(request, str(exc))
            return redirect("ticket-detail", pk=pk)
        notify_ticket_status_change(ticket, previous_status, actor=request.user)
        django_messages.success(request, "Proposition de planification envoyee au client.")
        return redirect("ticket-detail", pk=pk)


class TicketPlanningConfirmView(LoginRequiredMixin, View):
    def post(self, request, pk):
        ticket = get_object_or_404(scope_ticket_queryset(Ticket.objects.all(), request.user), pk=pk)
        previous_status = ticket.status
        accepted = request.POST.get("accepted") == "1"
        try:
            confirm_planning(ticket, accepted=accepted, actor=request.user)
        except ValueError as exc:
            django_messages.error(request, str(exc))
            return redirect("ticket-detail", pk=pk)
        notify_ticket_status_change(ticket, previous_status, actor=request.user)
        django_messages.success(request, "Planification acceptee." if accepted else "Planification refusee.")
        return redirect("ticket-detail", pk=pk)


class TicketRequestStartView(LoginRequiredMixin, View):
    def post(self, request, pk):
        ticket = get_object_or_404(scope_ticket_queryset(Ticket.objects.all(), request.user), pk=pk)
        previous_status = ticket.status
        try:
            request_start_intervention(ticket, actor=request.user)
        except ValueError as exc:
            django_messages.error(request, str(exc))
            return redirect("ticket-detail", pk=pk)
        notify_ticket_status_change(ticket, previous_status, actor=request.user)
        django_messages.success(request, "Demande de validation de debut envoyee au client.")
        return redirect("ticket-detail", pk=pk)


class TicketValidateStartView(LoginRequiredMixin, View):
    def post(self, request, pk):
        ticket = get_object_or_404(scope_ticket_queryset(Ticket.objects.all(), request.user), pk=pk)
        impossible = request.POST.get("impossible") == "1"
        form = TicketValidationBypassForm(request.POST, request.FILES) if impossible else None
        if form is not None and not form.is_valid():
            django_messages.error(request, "Motif et photo justificative obligatoires.")
            return redirect("ticket-detail", pk=pk)
        previous_status = ticket.status
        try:
            validate_start_intervention(
                ticket,
                actor=request.user,
                impossible=impossible,
                reason=form.cleaned_data["reason"] if form else "",
                photo=form.cleaned_data["photo"] if form else None,
            )
        except ValueError as exc:
            django_messages.error(request, str(exc))
            return redirect("ticket-detail", pk=pk)
        notify_ticket_status_change(ticket, previous_status, actor=request.user)
        django_messages.success(request, "Debut d'intervention valide.")
        return redirect("ticket-detail", pk=pk)


class TicketRequestFinishView(LoginRequiredMixin, View):
    def post(self, request, pk):
        ticket = get_object_or_404(scope_ticket_queryset(Ticket.objects.all(), request.user), pk=pk)
        previous_status = ticket.status
        try:
            request_finish_intervention(ticket, actor=request.user)
        except ValueError as exc:
            django_messages.error(request, str(exc))
            return redirect("ticket-detail", pk=pk)
        notify_ticket_status_change(ticket, previous_status, actor=request.user)
        django_messages.success(request, "Demande de validation de fin envoyee au client.")
        return redirect("ticket-detail", pk=pk)


class TicketValidateFinishView(LoginRequiredMixin, View):
    def post(self, request, pk):
        ticket = get_object_or_404(scope_ticket_queryset(Ticket.objects.all(), request.user), pk=pk)
        impossible = request.POST.get("impossible") == "1"
        form = TicketValidationBypassForm(request.POST, request.FILES) if impossible else None
        if form is not None and not form.is_valid():
            django_messages.error(request, "Motif et photo justificative obligatoires.")
            return redirect("ticket-detail", pk=pk)
        previous_status = ticket.status
        try:
            validate_finish_intervention(
                ticket,
                actor=request.user,
                impossible=impossible,
                reason=form.cleaned_data["reason"] if form else "",
                photo=form.cleaned_data["photo"] if form else None,
            )
        except ValueError as exc:
            django_messages.error(request, str(exc))
            return redirect("ticket-detail", pk=pk)
        notify_ticket_status_change(ticket, previous_status, actor=request.user)
        django_messages.success(request, "Fin d'intervention validee. Le formulaire de cloture est disponible.")
        return redirect("ticket-detail", pk=pk)


class TicketCloseDossierView(LoginRequiredMixin, View):
    def post(self, request, pk):
        ticket = get_object_or_404(scope_ticket_queryset(Ticket.objects.all(), request.user), pk=pk)
        form = TicketClosureForm(request.POST, request.FILES)
        if not form.is_valid():
            django_messages.error(request, "Completez les champs obligatoires de cloture.")
            return redirect("ticket-detail", pk=pk)
        previous_status = ticket.status
        try:
            close_sav_dossier(
                ticket,
                diagnosis=form.cleaned_data["diagnosis"],
                action_taken=form.cleaned_data["action_taken"],
                parts=form.cleaned_data["parts_used"],
                client_name=form.cleaned_data["client_name"],
                signature=form.cleaned_data["signature"],
                photos=form.cleaned_data.get("photos", []),
                actor=request.user,
            )
        except ValueError as exc:
            django_messages.error(request, str(exc))
            return redirect("ticket-detail", pk=pk)
        notify_ticket_status_change(ticket, previous_status, actor=request.user)
        django_messages.success(request, "Dossier cloture et rapport PDF genere.")
        return redirect("ticket-detail", pk=pk)


class TicketEscalationSolutionView(LoginRequiredMixin, View):
    def post(self, request, pk):
        ticket = get_object_or_404(scope_ticket_queryset(Ticket.objects.all(), request.user), pk=pk)
        form = TicketEscalationSolutionForm(request.POST)
        if not form.is_valid():
            django_messages.error(request, "La solution responsable est obligatoire.")
            return redirect("ticket-detail", pk=pk)
        previous_status = ticket.status
        try:
            provide_escalation_solution(ticket, actor=request.user, solution=form.cleaned_data["solution"])
        except ValueError as exc:
            django_messages.error(request, str(exc))
            return redirect("ticket-detail", pk=pk)
        notify_ticket_status_change(ticket, previous_status, actor=request.user)
        django_messages.success(request, "Solution transmise au technicien.")
        return redirect("ticket-detail", pk=pk)


class TicketEscalationDeclineView(LoginRequiredMixin, View):
    def post(self, request, pk):
        ticket = get_object_or_404(scope_ticket_queryset(Ticket.objects.all(), request.user), pk=pk)
        form = TicketEscalationDeclineForm(request.POST)
        if not form.is_valid():
            django_messages.error(request, "Le motif de refus est obligatoire.")
            return redirect("ticket-detail", pk=pk)
        previous_status = ticket.status
        try:
            decline_ticket_escalation(ticket, actor=request.user, reason=form.cleaned_data["reason"])
        except ValueError as exc:
            django_messages.error(request, str(exc))
            return redirect("ticket-detail", pk=pk)
        notify_ticket_status_change(ticket, previous_status, actor=request.user)
        django_messages.success(request, "Escalade declinee et ticket renvoye au technicien.")
        return redirect("ticket-detail", pk=pk)


class TicketEscalationContinueView(LoginRequiredMixin, View):
    def post(self, request, pk):
        ticket = get_object_or_404(scope_ticket_queryset(Ticket.objects.all(), request.user), pk=pk)
        previous_status = ticket.status
        try:
            continue_after_escalation_solution(ticket, actor=request.user)
        except ValueError as exc:
            django_messages.error(request, str(exc))
            return redirect("ticket-detail", pk=pk)
        notify_ticket_status_change(ticket, previous_status, actor=request.user)
        django_messages.success(request, "La solution responsable est prise en compte. Reprise du processus.")
        return redirect("ticket-detail", pk=pk)


class TicketWaitPartView(LoginRequiredMixin, View):
    def post(self, request, pk):
        ticket = get_object_or_404(scope_ticket_queryset(Ticket.objects.all(), request.user), pk=pk)
        if not can_drive_ticket_workflow(request.user, ticket):
            django_messages.error(request, "Seul le technicien responsable peut signaler une piece manquante.")
            return redirect("ticket-detail", pk=pk)
        reason = (request.POST.get("reason") or "").strip()
        if not reason:
            django_messages.error(request, "Precisez la piece manquante ou le motif d'attente.")
            return redirect("ticket-detail", pk=pk)
        previous_status = ticket.status
        ticket.status = Ticket.STATUS_WAITING_PART
        ticket.save(update_fields=["status", "updated_at"])
        Message.objects.create(
            ticket=ticket,
            sender=request.user,
            message_type=Message.TYPE_INTERNAL,
            channel=Message.CHANNEL_PORTAL,
            direction=Message.DIRECTION_INTERNAL,
            content=f"Piece manquante / attente approvisionnement: {reason}",
            sentiment_score=calculate_sentiment(reason),
        )
        notify_ticket_status_change(ticket, previous_status, actor=request.user)
        django_messages.success(request, "Ticket place en attente de piece.")
        return redirect("ticket-detail", pk=pk)


class TicketMessageCreateView(LoginRequiredMixin, View):
    def post(self, request, pk):
        ticket = get_object_or_404(scope_ticket_queryset(Ticket.objects.all(), request.user), pk=pk)
        if is_read_only_user(request.user):
            django_messages.error(request, "Le profil lecture seule est limite a la consultation.")
            return redirect("ticket-detail", pk=pk)
        if not can_participate_in_ticket_conversation(request.user, ticket):
            django_messages.error(request, "Vous ne participez pas à la conversation de ce ticket.")
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

        if message.recipient_id and direction == Message.DIRECTION_OUTBOUND and message_type == Message.TYPE_PUBLIC:
            create_message_delivery_notifications(message)
        elif message.recipient_id:
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

        if not can_record_ticket_intervention(request.user, ticket):
            django_messages.error(request, "Vous ne pouvez intervenir que sur les tickets qui vous sont affectes ou planifies.")
            return redirect("ticket-detail", pk=pk)

        form = InterventionForm(request.POST, request.FILES, user=request.user, ticket=ticket)
        if not form.is_valid():
            django_messages.error(request, "Impossible d'enregistrer l'intervention. Verifiez les champs saisis.")
            return redirect("ticket-detail", pk=pk)

        intervention = form.save(commit=False)
        intervention.ticket = ticket
        intervention.organization = ticket.organization
        if request.user.role in set(User.ASSIGNABLE_ROLES):
            intervention.agent = request.user
            intervention.intervention_type = Intervention.TYPE_ON_SITE
        if not intervention.location_snapshot:
            intervention.location_snapshot = ticket.location
        intervention.save()
        record_intervention_part_usages(
            intervention,
            spare_parts=form.cleaned_data.get("spare_parts"),
            structured_parts_used=form.cleaned_data.get("structured_parts_used"),
            replace=True,
        )

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
