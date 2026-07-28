from datetime import timedelta

from django.db.models import Avg, Count
from rest_framework.response import Response
from rest_framework.views import APIView

from ..models import (
    AIActionLog,
    KnowledgeArticle,
    MaintenanceTicket,
    Message,
    Notification,
    OfferRecommendation,
    PredictiveAlert,
    Product,
    SupportSession,
    Ticket,
    TicketFeedback,
    User,
)
from ..permissions import IsAuthenticatedSavUser
from ..services import (
    OPEN_TICKET_STATUSES,
    compute_agent_performance_rows,
    compute_average_first_response_hours,
    compute_average_resolution_hours,
    compute_technician_availability_dashboard,
    compute_ticket_hotspots,
    compute_ticket_monthly_series,
    compute_ticket_volume_series,
    scope_ai_action_queryset,
    scope_knowledge_article_queryset,
    scope_maintenance_ticket_queryset,
    scope_message_queryset,
    scope_notification_queryset,
    scope_offer_queryset,
    scope_predictive_alert_queryset,
    scope_product_queryset,
    scope_support_session_queryset,
    scope_ticket_feedback_queryset,
    scope_ticket_queryset,
    scope_user_queryset,
)
from django.utils import timezone


class DashboardView(APIView):
    permission_classes = [IsAuthenticatedSavUser]

    def get(self, request):
        tickets = scope_ticket_queryset(Ticket.objects.all(), request.user)
        products = scope_product_queryset(Product.objects.all(), request.user)
        alerts = scope_predictive_alert_queryset(PredictiveAlert.objects.all(), request.user)
        notifications = scope_notification_queryset(Notification.objects.all(), request.user)
        offers = scope_offer_queryset(OfferRecommendation.objects.all(), request.user)
        ai_actions = scope_ai_action_queryset(AIActionLog.objects.all(), request.user)
        messages = scope_message_queryset(Message.objects.filter(sentiment_score__isnull=False), request.user)
        support_sessions = scope_support_session_queryset(SupportSession.objects.all(), request.user)
        feedbacks = scope_ticket_feedback_queryset(TicketFeedback.objects.all(), request.user)
        maintenance_tickets = scope_maintenance_ticket_queryset(MaintenanceTicket.objects.all(), request.user)
        users = scope_user_queryset(User.objects.filter(role=User.ROLE_CLIENT), request.user)
        technicians = scope_user_queryset(
            User.objects.filter(role__in=User.TECHNICIAN_SPACE_ROLES, is_active=True),
            request.user,
        )

        status_breakdown = list(tickets.values("status").annotate(total=Count("id")).order_by("status"))
        priority_breakdown = list(tickets.values("priority").annotate(total=Count("id")).order_by("priority"))
        top_categories = list(tickets.values("category").annotate(total=Count("id")).order_by("-total")[:5])
        average_sentiment = messages.aggregate(avg=Avg("sentiment_score"))["avg"]
        average_first_response_hours = compute_average_first_response_hours(tickets)
        average_resolution_hours = compute_average_resolution_hours(tickets)
        top_agents = compute_agent_performance_rows(tickets)
        knowledge_articles = scope_knowledge_article_queryset(KnowledgeArticle.objects.all(), request.user)

        data = {
            "organization_name": request.user.organization.display_name if getattr(request.user, "organization_id", None) else "",
            "organization_slug": request.user.organization.slug if getattr(request.user, "organization_id", None) else "",
            "organization_primary_color": request.user.organization.primary_color if getattr(request.user, "organization_id", None) else "",
            "organization_accent_color": request.user.organization.accent_color if getattr(request.user, "organization_id", None) else "",
            "tickets_total": tickets.count(),
            "tickets_open": tickets.filter(status__in=OPEN_TICKET_STATUSES).count(),
            "tickets_overdue": tickets.filter(status__in=OPEN_TICKET_STATUSES, sla_deadline__lt=timezone.now()).count(),
            "tickets_unassigned": tickets.filter(status__in=OPEN_TICKET_STATUSES, assigned_agent__isnull=True).count(),
            "maintenance_total": tickets.filter(category=Ticket.CATEGORY_MAINTENANCE).count(),
            "planned_maintenance_total": maintenance_tickets.count(),
            "planned_maintenance_active": maintenance_tickets.exclude(
                status__in=[MaintenanceTicket.STATUS_DONE, MaintenanceTicket.STATUS_ANOMALY, MaintenanceTicket.STATUS_CANCELLED]
            ).count(),
            "planned_maintenance_done": maintenance_tickets.filter(status=MaintenanceTicket.STATUS_DONE).count(),
            "planned_maintenance_anomalies": maintenance_tickets.filter(status=MaintenanceTicket.STATUS_ANOMALY).count(),
            "bug_total": tickets.filter(category=Ticket.CATEGORY_BUG).count(),
            "tickets_critical_open": tickets.filter(status__in=OPEN_TICKET_STATUSES, priority=Ticket.PRIORITY_CRITICAL).count(),
            "products_total": products.count(),
            "products_under_warranty": products.filter(warranty_end__gte=timezone.localdate()).count(),
            "predictive_alerts_open": alerts.filter(status__in=[PredictiveAlert.STATUS_OPEN, PredictiveAlert.STATUS_IN_PROGRESS]).count(),
            "predictive_alerts_critical": alerts.filter(
                status__in=[PredictiveAlert.STATUS_OPEN, PredictiveAlert.STATUS_IN_PROGRESS],
                severity=PredictiveAlert.SEVERITY_CRITICAL,
            ).count(),
            "ai_actions_executed": ai_actions.filter(status=AIActionLog.STATUS_EXECUTED).count(),
            "notifications_unread": notifications.exclude(status=Notification.STATUS_READ).count(),
            "offers_accepted": offers.filter(status=OfferRecommendation.STATUS_ACCEPTED).count(),
            "support_sessions_active": support_sessions.filter(
                status__in=[SupportSession.STATUS_SCHEDULED, SupportSession.STATUS_LIVE]
            ).count(),
            "clients_verified": users.filter(is_verified=True).count(),
            "feedback_average_rating": float(feedbacks.aggregate(avg=Avg("rating"))["avg"]) if feedbacks.exists() else None,
            "average_sentiment": average_sentiment,
            "average_first_response_hours": float(average_first_response_hours) if average_first_response_hours is not None else None,
            "average_resolution_hours": float(average_resolution_hours) if average_resolution_hours is not None else None,
            "top_agents": [
                {
                    **row,
                    "average_resolution_hours": float(row["average_resolution_hours"]) if row["average_resolution_hours"] is not None else None,
                }
                for row in top_agents
            ],
            "tickets_by_status": status_breakdown,
            "tickets_by_priority": priority_breakdown,
            "top_categories": top_categories,
            "knowledge_articles_published": knowledge_articles.filter(status=KnowledgeArticle.STATUS_PUBLISHED).count(),
            "sla_due_soon": tickets.filter(
                status__in=OPEN_TICKET_STATUSES,
                sla_deadline__gte=timezone.now(),
                sla_deadline__lte=timezone.now() + timedelta(hours=2),
            ).count(),
            "geo_hotspots": compute_ticket_hotspots(tickets),
            "trend_7_days": compute_ticket_volume_series(tickets, days=7),
            "trend_30_days": compute_ticket_volume_series(tickets, days=30),
            "trend_12_months": compute_ticket_monthly_series(tickets, months=12),
            "technician_status_breakdown": compute_technician_availability_dashboard(getattr(request.user, "organization", None)),
        }
        return Response(data)
