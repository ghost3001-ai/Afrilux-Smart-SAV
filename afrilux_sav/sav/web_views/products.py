from django.contrib import messages as django_messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from ..forms import ProductForm
from ..models import (
    GeneratedReport,
    KnowledgeArticle,
    MaintenanceTicket,
    PredictiveAlert,
    Product,
    Ticket,
    User,
)
from ..services import (
    can_create_ticket,
    is_internal_user,
    is_manager_user,
    log_audit_event,
    run_predictive_analysis,
    scope_maintenance_ticket_queryset,
    scope_product_queryset,
    scope_predictive_alert_queryset,
    scope_ticket_queryset,
)
from .base import AdminRequiredMixin, InternalRequiredMixin


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
            Product.objects.select_related("client", "site", "equipment_category").prefetch_related(
                "telemetry",
                "predictive_alerts",
                "tickets",
                "location_history",
            ),
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
        context["maintenance_history"] = scope_maintenance_ticket_queryset(
            MaintenanceTicket.objects.select_related("technician", "client").filter(products=product),
            self.request.user,
        ).order_by("-scheduled_date", "-updated_at")[:12]
        context["knowledge_articles"] = product.knowledge_articles.filter(status=KnowledgeArticle.STATUS_PUBLISHED)[:6]
        context["location_history"] = product.location_history.select_related("from_site", "to_site", "moved_by").all()[:8]
        if product.organization and product.organization.personal_data_access_logging_enabled:
            log_audit_event(
                self.request.user,
                "personal_data_viewed",
                product,
                {"surface": "product_detail", "client_id": product.client_id},
            )
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
