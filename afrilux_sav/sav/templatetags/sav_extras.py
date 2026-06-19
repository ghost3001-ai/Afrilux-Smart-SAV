from decimal import Decimal, InvalidOperation

from django import template

register = template.Library()


@register.filter
def badge_tone(value):
    value = (value or "").lower()
    mapping = {
        "critical": "critical",
        "high": "warning",
        "normal": "neutral",
        "low": "calm",
        "resolved": "success",
        "closed": "neutral",
        "cancelled": "critical",
        "assigned": "accent",
        "pending_assignment": "accent",
        "team_pending": "accent",
        "team_ready": "accent",
        "planning_proposed": "accent",
        "in_progress": "warning",
        "collective_in_progress": "warning",
        "start_requested": "warning",
        "finish_requested": "warning",
        "waiting_part": "warning",
        "waiting_solution": "warning",
        "reassigned": "accent",
        "reassign_required": "warning",
        "blocked_direction": "critical",
        "new": "accent",
        "planned": "accent",
        "notified": "accent",
        "done": "success",
        "postponed": "warning",
        "anomaly_detected": "critical",
        "draft": "neutral",
        "published": "success",
        "archived": "neutral",
        "open": "accent",
        "waiting": "warning",
        "escalated": "warning",
        "completed": "success",
        "sent": "accent",
        "read": "success",
        "failed": "critical",
        "accepted": "success",
        "rejected": "critical",
        "proposed": "accent",
        "medium": "warning",
    }
    return mapping.get(value, "neutral")


@register.filter
def percentage(value):
    try:
        return f"{float(value):.0f}%"
    except (TypeError, ValueError):
        return "0%"


@register.filter
def currency_xaf(value):
    try:
        amount = Decimal(value or 0)
    except (InvalidOperation, TypeError, ValueError):
        amount = Decimal("0")
    return f"{int(amount):,} XAF".replace(",", " ")


@register.filter
def sentiment_tone(value):
    try:
        score = Decimal(value)
    except (InvalidOperation, TypeError, ValueError):
        return "neutral"
    if score <= Decimal("-0.50"):
        return "critical"
    if score < Decimal("0"):
        return "warning"
    if score >= Decimal("0.30"):
        return "success"
    return "neutral"
