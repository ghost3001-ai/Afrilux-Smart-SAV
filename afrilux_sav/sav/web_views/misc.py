from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views import View
from django.views.generic import DetailView, FormView, ListView

from ..forms import AnalyticsQuestionForm
from ..models import KnowledgeArticle, Notification
from ..services import (
    answer_bi_question,
    log_audit_event,
    scope_knowledge_article_queryset,
    scope_notification_queryset,
)
from .base import ReportingRequiredMixin


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
