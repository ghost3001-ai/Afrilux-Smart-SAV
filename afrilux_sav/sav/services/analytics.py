import json
from datetime import datetime, timedelta
from decimal import Decimal

from django.db.models import Count, Q
from django.utils import timezone

from ..ai import OpenAIResponsesClient
from ..comms import create_external_channel_notifications
from ..models import (
    AIActionLog,
    AuditLog,
    ClientContact,
    FinancialTransaction,
    KnowledgeArticle,
    Message,
    PredictiveAlert,
    Product,
    Ticket,
    User,
)
from .audit import log_audit_event
from .roles import scope_predictive_alert_queryset, scope_product_queryset, scope_ticket_queryset
from .tickets import (
    manager_queryset_for_organization,
    assignment_eligible_queryset_for_organization,
    technician_assignment_conflicts,
    serialize_assignment_conflicts,
    format_assignment_conflicts,
)
from .users import compute_ticket_sla_deadline

LLM_CLIENT = OpenAIResponsesClient()

OPEN_TICKET_STATUSES = [
    Ticket.STATUS_NEW,
    Ticket.STATUS_PENDING_ASSIGNMENT,
    Ticket.STATUS_ASSIGNED,
    Ticket.STATUS_TEAM_PENDING,
    Ticket.STATUS_TEAM_READY,
    Ticket.STATUS_PLANNING_PROPOSED,
    Ticket.STATUS_PLANNED,
    Ticket.STATUS_START_REQUESTED,
    Ticket.STATUS_IN_PROGRESS,
    Ticket.STATUS_COLLECTIVE_IN_PROGRESS,
    Ticket.STATUS_WAITING_PART,
    Ticket.STATUS_ESCALATED,
    Ticket.STATUS_WAITING_SOLUTION,
    Ticket.STATUS_WAITING_DIAGNOSTIC,
    Ticket.STATUS_FINISH_REQUESTED,
    Ticket.STATUS_REASSIGN_REQUIRED,
    Ticket.STATUS_REASSIGNED,
]

TECHNICIAN_AVAILABILITY_ROLES = tuple(
    dict.fromkeys(
        [
            *User.TECHNICIAN_SPACE_ROLES,
            User.ROLE_EXPERT,
            User.ROLE_FIELD_TECHNICIAN,
        ]
    )
)

NEGATIVE_WORDS = [
    "decu",
    "frustre",
    "encore",
    "toujours",
    "erreur",
    "probleme",
    "bloque",
    "plainte",
    "retard",
    "defectueux",
]

POSITIVE_WORDS = [
    "merci",
    "parfait",
    "resolu",
    "ok",
    "super",
    "satisfait",
]

CRITICAL_WORDS = [
    "danger",
    "fumee",
    "incendie",
    "court-circuit",
    "electrocution",
]

HIGH_PRIORITY_WORDS = [
    "urgent",
    "bloque",
    "hors service",
    "panne totale",
    "impossible",
]

ISSUE_KEYWORDS = {
    "battery_issue": ["batterie", "charge", "autonomie"],
    "overheating_issue": ["chauffe", "temperature", "surchauffe"],
    "wiring_issue": ["cable", "branchement", "connexion", "borne"],
    "configuration_issue": ["configuration", "parametre", "reset", "wifi", "reseau"],
    "noise_issue": ["bruit", "vibration", "ventilateur"],
}


def calculate_sentiment(text):
    lowered_text = (text or "").lower()
    score = Decimal("0.00")

    for word in NEGATIVE_WORDS:
        if word in lowered_text:
            score -= Decimal("0.20")
    for word in POSITIVE_WORDS:
        if word in lowered_text:
            score += Decimal("0.15")

    if score < Decimal("-1.00"):
        return Decimal("-1.00")
    if score > Decimal("1.00"):
        return Decimal("1.00")
    return score.quantize(Decimal("0.01"))


def _parse_completion_json(completion):
    if not completion.ok:
        return None
    try:
        return json.loads(completion.content)
    except json.JSONDecodeError:
        return None


def get_ai_runtime_status():
    return LLM_CLIENT.status()


def _coerce_bool(value, default=False):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "oui"}
    return default


def _coerce_decimal(value, default="0.00"):
    try:
        return Decimal(str(value))
    except Exception:  # noqa: BLE001
        return Decimal(default)


def _format_money(value):
    return _coerce_decimal(value, "0.00").quantize(Decimal("0.01"))


def _clamp_confidence(value, default="0.50"):
    decimal_value = _coerce_decimal(value, default)
    if decimal_value < Decimal("0"):
        return Decimal("0")
    if decimal_value > Decimal("1"):
        return Decimal("1")
    return decimal_value.quantize(Decimal("0.01"))


def _completed_at(ticket):
    return ticket.closed_at or ticket.resolved_at


def compute_average_first_response_hours(tickets):
    total_hours = Decimal("0.00")
    responded_tickets = 0

    for ticket in tickets:
        if not ticket.first_response_at:
            continue
        hours = Decimal(str((ticket.first_response_at - ticket.created_at).total_seconds() / 3600))
        total_hours += hours
        responded_tickets += 1

    if not responded_tickets:
        return None
    return (total_hours / responded_tickets).quantize(Decimal("0.01"))


def compute_average_resolution_hours(tickets):
    total_hours = Decimal("0.00")
    completed_tickets = 0

    for ticket in tickets:
        completed_at = _completed_at(ticket)
        if not completed_at:
            continue
        hours = Decimal(str((completed_at - ticket.created_at).total_seconds() / 3600))
        total_hours += hours
        completed_tickets += 1

    if not completed_tickets:
        return None
    return (total_hours / completed_tickets).quantize(Decimal("0.01"))


def compute_agent_performance_rows(tickets, limit=5):
    rows = {}

    for ticket in tickets.select_related("assigned_agent"):
        agent = ticket.assigned_agent
        if not agent:
            continue

        row = rows.setdefault(
            agent.id,
            {
                "agent_id": agent.id,
                "agent_name": str(agent),
                "resolved_tickets": 0,
                "open_tickets": 0,
                "_resolution_hours_total": Decimal("0.00"),
                "_resolution_ticket_count": 0,
            },
        )

        if ticket.status in OPEN_TICKET_STATUSES:
            row["open_tickets"] += 1

        completed_at = _completed_at(ticket)
        if completed_at:
            row["resolved_tickets"] += 1
            row["_resolution_hours_total"] += Decimal(str((completed_at - ticket.created_at).total_seconds() / 3600))
            row["_resolution_ticket_count"] += 1

    ranked_rows = []
    for row in rows.values():
        avg_resolution = None
        if row["_resolution_ticket_count"]:
            avg_resolution = (
                row["_resolution_hours_total"] / row["_resolution_ticket_count"]
            ).quantize(Decimal("0.01"))

        ranked_rows.append(
            {
                "agent_id": row["agent_id"],
                "agent_name": row["agent_name"],
                "resolved_tickets": row["resolved_tickets"],
                "open_tickets": row["open_tickets"],
                "average_resolution_hours": avg_resolution,
            }
        )

    ranked_rows.sort(
        key=lambda row: (
            -row["resolved_tickets"],
            row["average_resolution_hours"] if row["average_resolution_hours"] is not None else Decimal("9999.99"),
            row["open_tickets"],
            row["agent_name"],
        )
    )
    return ranked_rows[:limit]


def _ticket_context(ticket):
    return {
        "reference": ticket.reference,
        "title": ticket.title,
        "description": ticket.description,
        "category": ticket.category,
        "channel": ticket.channel,
        "priority": ticket.priority,
        "status": ticket.status,
        "warranty_eligible": bool(ticket.product and ticket.product.is_under_warranty),
        "product": {
            "name": ticket.product_display_name or None,
            "serial_number": ticket.product.serial_number if ticket.product else None,
            "health_score": ticket.product.health_score if ticket.product else None,
        },
        "messages": list(ticket.messages.values("content", "channel", "direction", "message_type")[:12]),
    }


def _client_context(client):
    tickets = client.tickets.order_by("-created_at")[:20]
    recent_transactions = client.financial_transactions.order_by("-occurred_at", "-created_at")[:15]
    return {
        "client_id": client.id,
        "client_name": str(client),
        "company_name": client.company_name,
        "organization_name": client.organization.display_name if client.organization_id else "",
        "is_verified": client.is_verified,
        "client_type": client.client_type,
        "client_status": client.client_status,
        "sector": client.sector,
        "tax_identifier": client.tax_identifier,
        "address": client.address,
        "account_balance": str(client.account_balance),
        "product_count": client.products.count(),
        "contacts": [
            {
                "full_name": f"{contact.first_name} {contact.last_name}".strip(),
                "job_title": contact.job_title,
                "phone": contact.phone,
                "email": contact.email,
                "is_primary": contact.is_primary,
            }
            for contact in client.contacts.order_by("-is_primary", "first_name", "last_name")[:10]
        ],
        "tickets": [
            {
                "reference": ticket.reference,
                "title": ticket.title,
                "status": ticket.status,
                "priority": ticket.priority,
                "category": ticket.category,
            }
            for ticket in tickets
        ],
        "recent_messages": list(
            Message.objects.filter(ticket__client=client).order_by("-created_at").values("content", "direction")[:10]
        ),
        "recent_transactions": [
            {
                "external_reference": transaction.external_reference,
                "transaction_type": transaction.transaction_type,
                "ledger_side": transaction.ledger_side,
                "amount": str(transaction.amount),
                "currency": transaction.currency,
                "status": transaction.status,
                "occurred_at": transaction.occurred_at.isoformat(),
            }
            for transaction in recent_transactions
        ],
    }


def _product_context(product):
    return {
        "product_id": product.id,
        "name": product.name,
        "serial_number": product.serial_number,
        "equipment_type": product.equipment_type,
        "brand": product.brand,
        "model_reference": product.model_reference,
        "health_score": product.health_score,
        "iot_enabled": product.iot_enabled,
        "installation_date": str(product.installation_date) if product.installation_date else None,
        "warranty_end": str(product.warranty_end) if product.warranty_end else None,
        "installation_address": product.installation_address,
        "detailed_location": product.detailed_location,
        "contract_reference": product.contract_reference,
        "counter_total": product.counter_total,
        "counter_color": product.counter_color,
        "counter_bw": product.counter_bw,
        "recent_telemetry": [
            {
                "metric_name": point.metric_name,
                "value": str(point.value),
                "unit": point.unit,
                "captured_at": point.captured_at.isoformat(),
            }
            for point in product.telemetry.order_by("-captured_at")[:30]
        ],
        "recent_tickets": [
            {
                "reference": ticket.reference,
                "title": ticket.title,
                "category": ticket.category,
                "priority": ticket.priority,
            }
            for ticket in product.tickets.order_by("-created_at")[:15]
        ],
    }


def compute_ticket_hotspots(tickets, limit=6):
    counts = {}
    for ticket in tickets.select_related("product"):
        location = (ticket.location or "").strip()
        if not location and ticket.product_id:
            location = (ticket.product.detailed_location or ticket.product.installation_address or "").strip()
        if not location:
            location = "Non renseigne"
        counts[location] = counts.get(location, 0) + 1
    rows = [{"location": key, "total": value} for key, value in counts.items()]
    rows.sort(key=lambda row: (-row["total"], row["location"]))
    return rows[:limit]


def compute_ticket_volume_series(tickets, days=7):
    anchor = timezone.localdate()
    series = []
    for offset in range(days - 1, -1, -1):
        day = anchor - timedelta(days=offset)
        day_start = timezone.make_aware(datetime.combine(day, datetime.min.time()))
        day_end = day_start + timedelta(days=1)
        series.append(
            {
                "label": day.strftime("%d/%m"),
                "created": tickets.filter(created_at__gte=day_start, created_at__lt=day_end).count(),
                "resolved": tickets.filter(resolved_at__gte=day_start, resolved_at__lt=day_end).count(),
            }
        )
    return series


def compute_ticket_monthly_series(tickets, months=12):
    anchor = timezone.localdate().replace(day=1)
    series = []
    for offset in range(months - 1, -1, -1):
        month_cursor = anchor
        for _ in range(offset):
            if month_cursor.month == 1:
                month_cursor = month_cursor.replace(year=month_cursor.year - 1, month=12)
            else:
                month_cursor = month_cursor.replace(month=month_cursor.month - 1)
        month_start = timezone.make_aware(datetime.combine(month_cursor, datetime.min.time()))
        if month_cursor.month == 12:
            next_month = month_cursor.replace(year=month_cursor.year + 1, month=1)
        else:
            next_month = month_cursor.replace(month=month_cursor.month + 1)
        month_end = timezone.make_aware(datetime.combine(next_month, datetime.min.time()))
        series.append(
            {
                "label": month_cursor.strftime("%m/%Y"),
                "created": tickets.filter(created_at__gte=month_start, created_at__lt=month_end).count(),
                "resolved": tickets.filter(resolved_at__gte=month_start, resolved_at__lt=month_end).count(),
            }
        )
    return series


def compute_technician_availability_rows(organization):
    technicians = User.objects.filter(
        organization=organization,
        role__in=TECHNICIAN_AVAILABILITY_ROLES,
        is_active=True
    ).order_by("first_name", "last_name", "username")

    dashboard = []
    now = timezone.now()

    for tech in technicians:
        conflicts = technician_assignment_conflicts(tech)
        sav_conflicts = [item for item in conflicts if item["type"] == "sav"]
        maintenance_conflicts = [item for item in conflicts if item["type"] == "maintenance"]
        assignable = tech.is_ticket_assignment_eligible and not conflicts
        next_candidates = [item["scheduled_at"] for item in conflicts if item.get("scheduled_at")]
        next_available = max(next_candidates) if next_candidates else None

        if conflicts:
            status = "busy"
        elif tech.technician_status in {"on_leave", "unavailable"}:
            status = "absent"
        elif tech.technician_status == "on_site":
            status = "busy"
            next_available = now + timedelta(hours=2)
            assignable = False
        else:
            status = "available"

        dashboard.append({
            "id": tech.id,
            "name": tech.get_full_name() or tech.username,
            "email": tech.email,
            "role": tech.get_role_display(),
            "full_name": str(tech),
            "technician_name": str(tech),
            "status": status,
            "status_label": {"available": "Disponible", "busy": "Occupe", "absent": "Absent"}.get(status, status),
            "assignable": assignable,
            "assignable_label": "Oui" if assignable else "Non",
            "current_ticket": sav_conflicts[0]["reference"] if sav_conflicts else None,
            "sav_active_count": len(sav_conflicts),
            "maintenance_active_count": len(maintenance_conflicts),
            "conflicts": serialize_assignment_conflicts(conflicts),
            "conflicts_label": format_assignment_conflicts(conflicts) if conflicts else "",
            "next_available": next_available.isoformat() if next_available else None,
            "next_available_at": next_available,
            "busy_until": next_available,
            "can_be_leader": tech.role in [User.ROLE_CHIEF_TECHNICIAN, User.ROLE_SUPERVISOR, User.ROLE_HEAD_SAV],
            "can_be_member": tech.role in User.ASSIGNABLE_ROLES,
            "current_tickets_count": len(sav_conflicts),
            "specialties": tech.specialties if hasattr(tech, "specialties") else [],
            "primary_city": tech.primary_city,
            "primary_region": tech.primary_region,
        })

    return dashboard


def compute_technician_availability_dashboard(organization):
    rows = compute_technician_availability_rows(organization)
    labels = {"available": "Disponible", "busy": "Occupe", "absent": "Absent"}
    return [
        {
            "status": status,
            "label": labels[status],
            "status_label": labels[status],
            "total": sum(1 for row in rows if row["status"] == status),
        }
        for status in ["available", "busy", "absent"]
        if any(row["status"] == status for row in rows)
    ]


def infer_priority_from_text(text, current_priority):
    lowered_text = (text or "").lower()
    priority_rank = {
        Ticket.PRIORITY_LOW: 1,
        Ticket.PRIORITY_NORMAL: 2,
        Ticket.PRIORITY_HIGH: 3,
        Ticket.PRIORITY_CRITICAL: 4,
    }

    inferred = current_priority
    if any(word in lowered_text for word in CRITICAL_WORDS):
        inferred = Ticket.PRIORITY_CRITICAL
    elif any(word in lowered_text for word in HIGH_PRIORITY_WORDS):
        inferred = Ticket.PRIORITY_HIGH

    return inferred if priority_rank[inferred] >= priority_rank[current_priority] else current_priority


def infer_issue_from_text(text):
    lowered_text = (text or "").lower()
    for issue, keywords in ISSUE_KEYWORDS.items():
        if any(keyword in lowered_text for keyword in keywords):
            return issue
    return "general_diagnostic"


def infer_ticket_category_from_text(text, current_category=Ticket.CATEGORY_BREAKDOWN):
    lowered_text = (text or "").lower()
    if any(word in lowered_text for word in ["bug", "erreur app", "application plante", "crash"]):
        return Ticket.CATEGORY_BUG
    if any(word in lowered_text for word in ["installation", "installer", "mise en service"]):
        return Ticket.CATEGORY_INSTALLATION
    if any(word in lowered_text for word in ["maintenance", "preventive", "entretien"]):
        return Ticket.CATEGORY_MAINTENANCE
    return current_category


def match_knowledge_articles(text, product=None, organization=None, limit=3):
    lowered_text = (text or "").lower()
    queryset = KnowledgeArticle.objects.filter(status=KnowledgeArticle.STATUS_PUBLISHED)
    scoped_organization = organization or getattr(product, "organization", None)
    if scoped_organization:
        queryset = queryset.filter(Q(organization=scoped_organization) | Q(organization__isnull=True))
    if product and product.organization_id:
        queryset = queryset.filter(Q(organization=product.organization) | Q(organization__isnull=True))
    if product:
        queryset = queryset.filter(Q(product=product) | Q(product__isnull=True))

    ranked_articles = []
    for article in queryset:
        score = 0
        keyword_blob = " ".join(filter(None, [article.title, article.summary, article.keywords, article.content])).lower()
        for token in set(lowered_text.split()):
            if len(token) > 3 and token in keyword_blob:
                score += 1
        if score:
            ranked_articles.append((score, article))

    ranked_articles.sort(key=lambda item: (-item[0], item[1].title))
    return [
        {
            "id": article.id,
            "title": article.title,
            "slug": article.slug,
            "summary": article.summary,
            "score": score,
        }
        for score, article in ranked_articles[:limit]
    ]


def answer_support_question(question, user, product=None, ticket=None):
    full_text = " ".join(
        filter(
            None,
            [
                question,
                getattr(ticket, "title", ""),
                getattr(ticket, "description", ""),
                getattr(product, "name", ""),
            ],
        )
    )
    matching_articles = match_knowledge_articles(
        full_text,
        product=product or getattr(ticket, "product", None),
        organization=getattr(ticket, "organization", None)
        or getattr(product, "organization", None)
        or getattr(user, "organization", None),
    )
    suggested_priority = infer_priority_from_text(full_text, getattr(ticket, "priority", Ticket.PRIORITY_NORMAL))
    suggested_category = infer_ticket_category_from_text(
        full_text,
        getattr(ticket, "category", Ticket.CATEGORY_BREAKDOWN),
    )
    likely_issue = infer_issue_from_text(full_text)
    should_create_ticket = ticket is None and (
        suggested_priority in {Ticket.PRIORITY_HIGH, Ticket.PRIORITY_CRITICAL}
        or any(keyword in full_text.lower() for keyword in ["probleme", "panne", "reclamation", "incident"])
    )

    if matching_articles:
        answer = (
            f"Je recommande d'abord l'article '{matching_articles[0]['title']}' pour guider la resolution. "
            "Si le probleme persiste, ouvrez ou mettez a jour un ticket afin qu'un agent prenne le relais."
        )
        recommended_next_step = f"Consulter {matching_articles[0]['title']}"
    else:
        answer = (
            "Je n'ai pas trouve d'article parfaitement cible. Decrivez l'incident avec le contexte produit, "
            "les symptomes, les captures ou recus, puis ouvrez un ticket pour prise en charge rapide."
        )
        recommended_next_step = "Creer ou mettre a jour un ticket avec des preuves"

    openai_data = None
    completion = None
    if LLM_CLIENT.enabled:
        system_prompt = (
            "Vous êtes l\u2019assistant SAV d\u2019Afrilux. Répondez exclusivement en français et retournez uniquement "
            "un JSON valide avec les clés : answer, suggested_priority, suggested_category, likely_issue, "
            "should_create_ticket, recommended_next_step, draft_title, draft_description, "
            "recommended_article_slug, confidence."
        )
        user_prompt = (
            "Répondez à cette question d\u2019assistance en utilisant le contexte disponible.\n"
            f"{json.dumps({'question': question, 'ticket': _ticket_context(ticket) if ticket else None, 'product': _product_context(product) if product else None, 'knowledge': matching_articles}, ensure_ascii=False)}"
        )
        completion = LLM_CLIENT.complete_json(system_prompt, user_prompt)
        openai_data = _parse_completion_json(completion)

    if openai_data:
        answer = openai_data.get("answer") or answer
        suggested_priority = openai_data.get("suggested_priority") or suggested_priority
        suggested_category = openai_data.get("suggested_category") or suggested_category
        likely_issue = openai_data.get("likely_issue") or likely_issue
        should_create_ticket = _coerce_bool(openai_data.get("should_create_ticket"), should_create_ticket)
        recommended_next_step = openai_data.get("recommended_next_step") or recommended_next_step
        if openai_data.get("recommended_article_slug"):
            matching_articles = [
                article for article in matching_articles if article["slug"] == openai_data.get("recommended_article_slug")
            ] or matching_articles
        confidence = _clamp_confidence(openai_data.get("confidence"), "0.82")
        draft_title = openai_data.get("draft_title") or question[:80]
        draft_description = openai_data.get("draft_description") or question
    else:
        confidence = Decimal("0.79")
        draft_title = question[:80]
        draft_description = question

    ai_log = AIActionLog.objects.create(
        organization=getattr(user, "organization", None) or getattr(ticket, "organization", None) or getattr(product, "organization", None),
        ticket=ticket,
        product=product,
        action_type=AIActionLog.ACTION_DIAGNOSIS,
        status=AIActionLog.STATUS_EXECUTED,
        confidence=confidence,
        rationale="Assistant d\u2019assistance alimenté par la base de connaissances, les heuristiques SAV et OpenAI si configuré.",
        input_snapshot={"question": question, "user_id": getattr(user, "id", None)},
        output_snapshot={
            "suggested_priority": suggested_priority,
            "suggested_category": suggested_category,
            "likely_issue": likely_issue,
            "matched_articles": matching_articles,
            "should_create_ticket": should_create_ticket,
            "llm_used": bool(openai_data),
            "llm_error": completion.error_message if completion and not completion.ok else "",
        },
        approved_by=None,
    )
    ai_status = LLM_CLIENT.status()

    return {
        "answer": answer,
        "ai_mode": "openai" if openai_data else "heuristique",
        "ai_provider": "openai" if openai_data else ai_status["provider"],
        "ai_model": completion.model if completion and openai_data else ai_status["model"],
        "ai_configured": ai_status["enabled"],
        "suggested_priority": suggested_priority,
        "suggested_category": suggested_category,
        "likely_issue": likely_issue,
        "matched_articles": matching_articles,
        "recommended_next_step": recommended_next_step,
        "should_create_ticket": should_create_ticket,
        "draft_ticket": {
            "title": draft_title,
            "description": draft_description,
            "category": suggested_category,
            "priority": suggested_priority,
        },
        "ai_action_id": ai_log.id,
    }


def select_least_loaded_agent(organization=None):
    queryset = assignment_eligible_queryset_for_organization(organization=organization)
    return (
        queryset
        .annotate(
            open_ticket_count=Count(
                "assigned_tickets",
                filter=Q(assigned_tickets__status__in=OPEN_TICKET_STATUSES),
            )
        )
        .order_by("open_ticket_count", "id")
        .first()
    )


def apply_agentic_resolution(ticket, approved_by=None):
    previous_status = ticket.status
    openai_data = None
    content_parts = [ticket.title, ticket.description]
    content_parts.extend(ticket.messages.values_list("content", flat=True))
    full_text = " ".join(filter(None, content_parts))
    sentiment = calculate_sentiment(full_text)
    suggested_priority = infer_priority_from_text(full_text, ticket.priority)
    likely_issue = infer_issue_from_text(full_text)
    matching_articles = match_knowledge_articles(full_text, product=ticket.product, organization=ticket.organization)

    if LLM_CLIENT.enabled:
        system_prompt = (
            "Vous êtes l\u2019agent autonome du SAV Afrilux. Répondez exclusivement en français et retournez uniquement "
            "un JSON valide avec les clés : summary, suggested_priority, likely_issue, auto_resolve, "
            "resolution_summary, recommended_article_slug, actions_taken, confidence. N\u2019activez auto_resolve "
            "que pour des corrections simples réalisables en autonomie ou un remplacement manifestement sous garantie."
        )
        user_prompt = (
            "Analysez ce ticket d\u2019assistance et proposez la prochaine action.\n"
            f"{json.dumps(_ticket_context(ticket), ensure_ascii=False)}\n"
            f"Articles de connaissances candidats : {json.dumps(matching_articles, ensure_ascii=False)}"
        )
        openai_data = _parse_completion_json(LLM_CLIENT.complete_json(system_prompt, user_prompt))

    if openai_data:
        suggested_priority = openai_data.get("suggested_priority") or suggested_priority
        likely_issue = openai_data.get("likely_issue") or likely_issue
        if openai_data.get("recommended_article_slug"):
            matching_articles = [
                article for article in matching_articles if article["slug"] == openai_data.get("recommended_article_slug")
            ] or matching_articles
        llm_auto_resolve = _coerce_bool(openai_data.get("auto_resolve"), default=False)
        llm_resolution_summary = openai_data.get("resolution_summary", "")
        llm_actions = [str(item) for item in openai_data.get("actions_taken", []) if item]
        llm_confidence = _clamp_confidence(openai_data.get("confidence"), "0.70")
    else:
        llm_auto_resolve = False
        llm_resolution_summary = ""
        llm_actions = []
        llm_confidence = Decimal("0.78")

    actions_taken = []
    auto_resolved = False
    warranty_eligible = bool(ticket.product and ticket.product.is_under_warranty)

    if suggested_priority != ticket.priority:
        ticket.priority = suggested_priority
        if ticket.is_open:
            ticket.sla_deadline = compute_ticket_sla_deadline(suggested_priority, organization=ticket.organization)
        actions_taken.append("priority_recalculated")

    if not ticket.first_response_at:
        ticket.first_response_at = timezone.now()
        actions_taken.append("first_response_recorded")

    if llm_auto_resolve and llm_resolution_summary:
        ticket.status = Ticket.STATUS_RESOLVED
        ticket.resolution_summary = llm_resolution_summary
        actions_taken.extend(llm_actions or ["llm_auto_resolution"])
        auto_resolved = True
    elif "garantie" in full_text.lower() and warranty_eligible:
        ticket.status = Ticket.STATUS_RESOLVED
        ticket.resolution_summary = (
            "Resolution agentique: cas sous garantie detecte, orientation echange standard automatisee."
        )
        actions_taken.append("warranty_exchange_approved")
        auto_resolved = True
    elif likely_issue in {"wiring_issue", "configuration_issue"} and matching_articles:
        article = matching_articles[0]
        ticket.status = Ticket.STATUS_RESOLVED
        ticket.resolution_summary = (
            f"Resolution agentique via auto-assistance. Consultez l'article '{article['title']}' pour la procedure guidee."
        )
        actions_taken.append("self_service_resolution")
        auto_resolved = True

    ticket.save()
    from .automation import notify_ticket_status_change
    notify_ticket_status_change(ticket, previous_status, actor=approved_by)

    from .financial import generate_offer_recommendations
    created_offers = generate_offer_recommendations(client=ticket.client, ticket=ticket, product=ticket.product, persist=True)

    if auto_resolved:
        create_external_channel_notifications(
            recipient=ticket.client,
            ticket=ticket,
            event_type="ticket_auto_resolved",
            subject=f"Votre ticket {ticket.reference} a ete resolu",
            message=ticket.resolution_summary,
        )

    output_snapshot = {
        "ticket_reference": ticket.reference,
        "sentiment_score": str(sentiment),
        "suggested_priority": suggested_priority,
        "likely_issue": likely_issue,
        "matching_articles": matching_articles,
        "actions_taken": actions_taken,
        "auto_resolved": auto_resolved,
        "offers_generated": [item["offer"].id for item in created_offers],
        "llm_used": bool(openai_data),
        "llm_output": openai_data or {},
    }

    ai_log = AIActionLog.objects.create(
        ticket=ticket,
        product=ticket.product,
        action_type=AIActionLog.ACTION_AUTO_RESOLUTION if auto_resolved else AIActionLog.ACTION_DIAGNOSIS,
        status=AIActionLog.STATUS_EXECUTED if auto_resolved else AIActionLog.STATUS_SUGGESTED,
        confidence=Decimal("0.92") if auto_resolved and not openai_data else llm_confidence,
        rationale=(
            "Decision basee sur le contexte ticket, la base de connaissances et la couche LLM OpenAI lorsqu'elle est configuree."
        ),
        input_snapshot={
            "title": ticket.title,
            "category": ticket.category,
            "priority": ticket.priority,
            "warranty_eligible": warranty_eligible,
        },
        output_snapshot=output_snapshot,
        approved_by=approved_by,
    )

    log_audit_event(
        actor=approved_by,
        actor_type=AuditLog.ACTOR_AI,
        action="agentic_resolution",
        instance=ticket,
        details={"ai_action_id": ai_log.id, "output": output_snapshot},
    )

    return {
        "ticket_reference": ticket.reference,
        "status": ticket.status,
        "resolution_summary": ticket.resolution_summary,
        "sentiment_score": str(sentiment),
        "likely_issue": likely_issue,
        "matching_articles": matching_articles,
        "actions_taken": actions_taken,
        "auto_resolved": auto_resolved,
        "offers_generated": [item["offer"].id for item in created_offers],
        "ai_action_id": ai_log.id,
    }


def build_customer_insight(client):
    tickets = client.tickets.all()
    messages = Message.objects.filter(ticket__client=client, direction=Message.DIRECTION_INBOUND)
    recent_transactions = client.financial_transactions.order_by("-occurred_at", "-created_at")[:8]
    disputed_transactions = client.financial_transactions.filter(status=FinancialTransaction.STATUS_DISPUTED).count()

    repeat_issue_groups = list(
        tickets.values("category", "product__name")
        .annotate(total=Count("id"))
        .filter(total__gt=1)
        .order_by("-total")[:5]
    )

    critical_open_tickets = tickets.filter(priority=Ticket.PRIORITY_CRITICAL, status__in=OPEN_TICKET_STATUSES).count()
    open_tickets = tickets.filter(status__in=OPEN_TICKET_STATUSES).count()
    resolved_tickets = tickets.filter(status=Ticket.STATUS_RESOLVED).count()
    average_sentiment = Decimal("0.00")
    sentiment_count = 0

    for message in messages:
        text = message.content
        score = message.sentiment_score if message.sentiment_score is not None else calculate_sentiment(text)
        average_sentiment += score
        sentiment_count += 1

    if sentiment_count:
        average_sentiment = (average_sentiment / sentiment_count).quantize(Decimal("0.01"))

    if critical_open_tickets or average_sentiment <= Decimal("-0.50"):
        risk_level = "high"
    elif open_tickets >= 2 or repeat_issue_groups:
        risk_level = "medium"
    else:
        risk_level = "low"

    from .financial import generate_offer_recommendations
    recommended_offers = generate_offer_recommendations(client=client, persist=False)

    summary = (
        f"{client} possede {client.products.count()} equipement(s), {open_tickets} ticket(s) ouvert(s), "
        f"un solde de {client.account_balance} et un niveau de risque {risk_level}."
    )

    openai_data = None
    if LLM_CLIENT.enabled:
        system_prompt = (
            "You are an Afrilux customer success analyst. "
            "Return valid JSON only with keys: summary, risk_level, focus_points, suggested_actions, confidence."
        )
        user_prompt = (
            "Build a concise customer insight summary from this account context:\n"
            f"{json.dumps(_client_context(client), ensure_ascii=False)}"
        )
        openai_data = _parse_completion_json(LLM_CLIENT.complete_json(system_prompt, user_prompt))

    if openai_data:
        summary = openai_data.get("summary") or summary
        risk_level = openai_data.get("risk_level") or risk_level
        suggested_actions = [str(item) for item in openai_data.get("suggested_actions", []) if item]
        confidence = _clamp_confidence(openai_data.get("confidence"), "0.80")
    else:
        suggested_actions = []
        confidence = Decimal("0.84")

    ai_log = AIActionLog.objects.create(
        organization=client.organization,
        action_type=AIActionLog.ACTION_INSIGHT_SUMMARY,
        status=AIActionLog.STATUS_EXECUTED,
        confidence=confidence,
        rationale="Synthese client construite a partir de l\u2019historique tickets, des interactions et de la couche OpenAI si configuree.",
        input_snapshot={"client_id": client.id},
        output_snapshot={
            "risk_level": risk_level,
            "open_tickets": open_tickets,
            "llm_used": bool(openai_data),
            "llm_output": openai_data or {},
        },
        approved_by=None,
    )

    return {
        "client_id": client.id,
        "client_name": str(client),
        "summary": summary,
        "risk_level": risk_level,
        "open_tickets": open_tickets,
        "critical_open_tickets": critical_open_tickets,
        "resolved_tickets": resolved_tickets,
        "account_balance": str(client.account_balance),
        "is_verified": client.is_verified,
        "disputed_transactions": disputed_transactions,
        "recent_transactions": [
            {
                "external_reference": item.external_reference,
                "transaction_type": item.transaction_type,
                "amount": str(item.amount),
                "currency": item.currency,
                "status": item.status,
                "occurred_at": item.occurred_at.isoformat(),
            }
            for item in recent_transactions
        ],
        "average_sentiment": str(average_sentiment),
        "repeat_issue_groups": repeat_issue_groups,
        "recommended_offers": recommended_offers,
        "suggested_actions": suggested_actions,
        "ai_action_id": ai_log.id,
    }


def _create_predictive_alert(
    product,
    alert_type,
    severity,
    title,
    description,
    recommended_action,
    metric_name="",
    metric_value=None,
    predicted_failure_at=None,
):
    existing_alert = PredictiveAlert.objects.filter(
        product=product,
        alert_type=alert_type,
        metric_name=metric_name,
        status__in=[PredictiveAlert.STATUS_OPEN, PredictiveAlert.STATUS_IN_PROGRESS],
    ).first()
    if existing_alert:
        return existing_alert, False

    alert = PredictiveAlert.objects.create(
        product=product,
        alert_type=alert_type,
        severity=severity,
        title=title,
        description=description,
        metric_name=metric_name,
        metric_value=metric_value,
        predicted_failure_at=predicted_failure_at,
        recommended_action=recommended_action,
    )
    return alert, True


def run_predictive_analysis(product, approved_by=None):
    now = timezone.now()
    latest_telemetry = {}
    for point in product.telemetry.order_by("-captured_at")[:100]:
        latest_telemetry.setdefault(point.metric_name.lower(), point)

    alerts_created = []
    severity_penalty = 0

    thresholds = {
        "temperature": [(Decimal("80"), PredictiveAlert.SEVERITY_CRITICAL), (Decimal("70"), PredictiveAlert.SEVERITY_HIGH)],
        "vibration": [(Decimal("7"), PredictiveAlert.SEVERITY_HIGH), (Decimal("5"), PredictiveAlert.SEVERITY_MEDIUM)],
        "error_rate": [(Decimal("10"), PredictiveAlert.SEVERITY_CRITICAL), (Decimal("5"), PredictiveAlert.SEVERITY_HIGH)],
    }

    for metric_name, point in latest_telemetry.items():
        if metric_name not in thresholds:
            continue
        for threshold, severity in thresholds[metric_name]:
            if point.value >= threshold:
                alert, created = _create_predictive_alert(
                    product=product,
                    alert_type=PredictiveAlert.TYPE_ANOMALY,
                    severity=severity,
                    title=f"Anomalie detectee sur {metric_name}",
                    description=f"La valeur {point.value}{point.unit} depasse le seuil defini pour {metric_name}.",
                    metric_name=metric_name,
                    metric_value=point.value,
                    predicted_failure_at=now + timedelta(days=7 if severity == PredictiveAlert.SEVERITY_CRITICAL else 21),
                    recommended_action="Planifier une verification technique et reserver les pieces critiques.",
                )
                if created:
                    alerts_created.append(alert)
                    severity_penalty += 25 if severity == PredictiveAlert.SEVERITY_CRITICAL else 15
                break

    recurring_breakdowns = product.tickets.filter(
        category=Ticket.CATEGORY_BREAKDOWN,
        created_at__gte=now - timedelta(days=90),
    ).count()
    if recurring_breakdowns >= 2:
        alert, created = _create_predictive_alert(
            product=product,
            alert_type=PredictiveAlert.TYPE_REPEAT_FAILURE,
            severity=PredictiveAlert.SEVERITY_HIGH,
            title="Pannes recurrentes detectees",
            description="Le produit a enregistre plusieurs incidents similaires sur les 90 derniers jours.",
            recommended_action="Declencher une maintenance preventive approfondie et envisager une mise a niveau.",
            predicted_failure_at=now + timedelta(days=14),
        )
        if created:
            alerts_created.append(alert)
            severity_penalty += 20

    if product.warranty_end:
        days_to_warranty_end = (product.warranty_end - timezone.localdate()).days
        if 0 <= days_to_warranty_end <= 30:
            alert, created = _create_predictive_alert(
                product=product,
                alert_type=PredictiveAlert.TYPE_WARRANTY,
                severity=PredictiveAlert.SEVERITY_MEDIUM,
                title="Garantie proche de l'expiration",
                description="La garantie du produit expire prochainement.",
                recommended_action="Contacter le client pour une extension de garantie ou un contrat de maintenance.",
                predicted_failure_at=now + timedelta(days=days_to_warranty_end),
            )
            if created:
                alerts_created.append(alert)
                severity_penalty += 10

    openai_data = None
    if LLM_CLIENT.enabled:
        system_prompt = (
            "You are an Afrilux predictive maintenance analyst. "
            "Return valid JSON only with keys: summary, health_score, alerts. "
            "Each alert must include title, severity, description, recommended_action, metric_name, metric_value, days_to_failure."
        )
        user_prompt = (
            "Analyse this equipment context and propose predictive maintenance alerts.\n"
            f"{json.dumps(_product_context(product), ensure_ascii=False)}"
        )
        openai_data = _parse_completion_json(LLM_CLIENT.complete_json(system_prompt, user_prompt))

    if openai_data:
        proposed_health_score = openai_data.get("health_score")
        if proposed_health_score is not None:
            try:
                severity_penalty = max(0, 100 - int(proposed_health_score))
            except (TypeError, ValueError):
                pass

        for proposed in openai_data.get("alerts", [])[:5]:
            severity = proposed.get("severity", PredictiveAlert.SEVERITY_MEDIUM)
            title = proposed.get("title") or "Alerte predictive generee par IA"
            description = proposed.get("description") or openai_data.get("summary") or "Signal predictif detecte."
            recommended_action = proposed.get("recommended_action", "")
            metric_name = proposed.get("metric_name", "")
            metric_value = proposed.get("metric_value")
            days_to_failure = proposed.get("days_to_failure")
            predicted_failure_at = None
            try:
                if days_to_failure is not None:
                    predicted_failure_at = now + timedelta(days=int(days_to_failure))
            except (TypeError, ValueError):
                predicted_failure_at = None

            alert, created = _create_predictive_alert(
                product=product,
                alert_type=PredictiveAlert.TYPE_ANOMALY if metric_name else PredictiveAlert.TYPE_MAINTENANCE,
                severity=severity,
                title=title,
                description=description,
                recommended_action=recommended_action,
                metric_name=metric_name,
                metric_value=_coerce_decimal(metric_value, "0.00") if metric_value is not None else None,
                predicted_failure_at=predicted_failure_at,
            )
            if created:
                alerts_created.append(alert)

    product.health_score = max(0, 100 - severity_penalty)
    product.save(update_fields=["health_score", "updated_at"])

    preventive_ticket = None
    severe_alert_exists = any(
        alert.severity in {PredictiveAlert.SEVERITY_HIGH, PredictiveAlert.SEVERITY_CRITICAL} for alert in alerts_created
    )
    if severe_alert_exists:
        preventive_ticket = product.tickets.filter(
            category=Ticket.CATEGORY_MAINTENANCE,
            status__in=OPEN_TICKET_STATUSES,
        ).first()
        if preventive_ticket is None:
            preventive_ticket = Ticket.objects.create(
                client=product.client,
                product=product,
                assigned_agent=select_least_loaded_agent(product.organization),
                title=f"Maintenance preventive recommandee - {product.name}",
                description="Ticket genere automatiquement suite a une analyse predictive des donnees equipement.",
                category=Ticket.CATEGORY_MAINTENANCE,
                channel=Ticket.CHANNEL_WEB,
                status=Ticket.STATUS_NEW,
                priority=Ticket.PRIORITY_HIGH,
                sla_deadline=now + timedelta(days=2),
            )

    for alert in alerts_created:
        if preventive_ticket and not alert.ticket_id:
            alert.ticket = preventive_ticket
            alert.save(update_fields=["ticket", "updated_at"])

    ai_log = AIActionLog.objects.create(
        product=product,
        ticket=preventive_ticket,
        action_type=AIActionLog.ACTION_PREDICTIVE_ANALYSIS,
        status=AIActionLog.STATUS_EXECUTED,
        confidence=Decimal("0.88") if not openai_data else _clamp_confidence("0.90"),
        rationale="Analyse predictive calculee a partir des telemetries recentes, de l'historique et d'OpenAI si configure.",
        input_snapshot={"product_id": product.id, "telemetry_points": len(latest_telemetry)},
        output_snapshot={
            "alerts_created": [alert.id for alert in alerts_created],
            "preventive_ticket": preventive_ticket.reference if preventive_ticket else None,
            "health_score": product.health_score,
            "llm_used": bool(openai_data),
            "llm_output": openai_data or {},
        },
        approved_by=approved_by,
    )

    for manager in manager_queryset_for_organization(product.organization):
        if alerts_created:
            create_external_channel_notifications(
                recipient=manager,
                ticket=preventive_ticket,
                event_type="predictive_alert",
                subject=f"Alertes predictives sur {product.serial_number}",
                message=f"{len(alerts_created)} alerte(s) predictive(s) ont ete detectee(s) sur le produit {product.name}.",
            )

    log_audit_event(
        actor=approved_by,
        actor_type=AuditLog.ACTOR_AI,
        action="predictive_analysis",
        instance=product,
        details={
            "alerts_created": [alert.id for alert in alerts_created],
            "preventive_ticket": preventive_ticket.reference if preventive_ticket else None,
            "ai_action_id": ai_log.id,
        },
    )

    return {
        "product_id": product.id,
        "product_name": product.name,
        "health_score": product.health_score,
        "alerts_created": [
            {
                "id": alert.id,
                "title": alert.title,
                "severity": alert.severity,
                "ticket_reference": alert.ticket.reference if alert.ticket else None,
            }
            for alert in alerts_created
        ],
        "preventive_ticket_reference": preventive_ticket.reference if preventive_ticket else None,
        "ai_action_id": ai_log.id,
    }


def answer_bi_question(question, user):
    lowered = (question or "").lower()
    tickets = scope_ticket_queryset(Ticket.objects.all(), user)
    products = scope_product_queryset(Product.objects.all(), user)
    alerts = scope_predictive_alert_queryset(PredictiveAlert.objects.all(), user)
    average_first_response_hours = compute_average_first_response_hours(tickets)
    average_resolution_hours = compute_average_resolution_hours(tickets)
    top_agents = compute_agent_performance_rows(tickets)
    base_result = None

    if "critique" in lowered:
        open_critical = tickets.filter(priority=Ticket.PRIORITY_CRITICAL, status__in=OPEN_TICKET_STATUSES).count()
        overdue_critical = tickets.filter(
            priority=Ticket.PRIORITY_CRITICAL,
            status__in=OPEN_TICKET_STATUSES,
            sla_deadline__lt=timezone.now(),
        ).count()
        base_result = {
            "matched_intent": "critical_tickets",
            "answer": (
                f"Il y a {open_critical} ticket(s) critique(s) ouvert(s), dont {overdue_critical} en depassement de SLA."
            ),
            "data": {
                "open_critical_tickets": open_critical,
                "overdue_critical_tickets": overdue_critical,
            },
        }

    elif "retard" in lowered or "sla" in lowered:
        overdue_count = tickets.filter(status__in=OPEN_TICKET_STATUSES, sla_deadline__lt=timezone.now()).count()
        total_open = tickets.filter(status__in=OPEN_TICKET_STATUSES).count()
        base_result = {
            "matched_intent": "sla",
            "answer": f"{overdue_count} ticket(s) ouvert(s) sur {total_open} sont actuellement hors SLA.",
            "data": {"overdue_tickets": overdue_count, "open_tickets": total_open},
        }

    elif "garantie" in lowered:
        under_warranty = products.filter(warranty_end__gte=timezone.localdate()).count()
        expiring = products.filter(
            warranty_end__gte=timezone.localdate(),
            warranty_end__lte=timezone.localdate() + timedelta(days=30),
        ).count()
        base_result = {
            "matched_intent": "warranty",
            "answer": (
                f"{under_warranty} produit(s) sont encore sous garantie, dont {expiring} avec une expiration dans 30 jours."
            ),
            "data": {"under_warranty": under_warranty, "warranty_expiring_soon": expiring},
        }

    elif "maintenance" in lowered or "entretien" in lowered:
        maintenance_total = tickets.filter(category=Ticket.CATEGORY_MAINTENANCE).count()
        base_result = {
            "matched_intent": "maintenance",
            "answer": f"{maintenance_total} ticket(s) de maintenance sont enregistres dans le perimetre courant.",
            "data": {
                "maintenance_total": maintenance_total,
            },
        }

    elif "bug" in lowered or "erreur" in lowered:
        bug_total = tickets.filter(category=Ticket.CATEGORY_BUG).count()
        base_result = {
            "matched_intent": "bugs",
            "answer": f"{bug_total} ticket(s) sont classes comme bug.",
            "data": {"bug_total": bug_total},
        }

    elif "resolution" in lowered or "resolu" in lowered:
        base_result = {
            "matched_intent": "resolution_time",
            "answer": (
                f"Le temps moyen de resolution est de {average_resolution_hours} heure(s)."
                if average_resolution_hours is not None
                else "Aucun historique clos ne permet encore de calculer un temps moyen de resolution."
            ),
            "data": {
                "average_resolution_hours": float(average_resolution_hours) if average_resolution_hours is not None else None,
            },
        }

    elif "premiere reponse" in lowered or "temps de reponse" in lowered or "temps moyen de reponse" in lowered:
        base_result = {
            "matched_intent": "first_response_time",
            "answer": (
                f"Le temps moyen de premiere reponse est de {average_first_response_hours} heure(s)."
                if average_first_response_hours is not None
                else "Aucun historique de premiere reponse n'est encore disponible."
            ),
            "data": {
                "average_first_response_hours": float(average_first_response_hours)
                if average_first_response_hours is not None
                else None,
            },
        }

    elif "agent" in lowered or "performant" in lowered:
        highlights = [
            f"{row['agent_name']}: {row['resolved_tickets']} resolu(s), {row['open_tickets']} ouvert(s)"
            for row in top_agents[:3]
        ]
        base_result = {
            "matched_intent": "top_agents",
            "answer": (
                "Les agents les plus performants ont ete identifies."
                if top_agents
                else "Aucun agent ne dispose encore d'assez d'historique pour etre compare."
            ),
            "data": {
                "top_agents": [
                    {
                        **row,
                        "average_resolution_hours": float(row["average_resolution_hours"])
                        if row["average_resolution_hours"] is not None
                        else None,
                    }
                    for row in top_agents
                ]
            },
        }
        if highlights:
            base_result["highlights"] = highlights

    elif "panne" in lowered or "recurrente" in lowered:
        recurrent_products = list(
            tickets.filter(category=Ticket.CATEGORY_BREAKDOWN)
            .values("product__name", "product__serial_number")
            .annotate(total=Count("id"))
            .order_by("-total")[:5]
        )
        base_result = {
            "matched_intent": "recurrent_failures",
            "answer": "Les produits les plus exposes aux pannes recurrentes ont ete identifies.",
            "data": {"top_recurrent_products": recurrent_products},
        }

    elif "predictif" in lowered or "alerte" in lowered:
        open_alerts = alerts.filter(status__in=[PredictiveAlert.STATUS_OPEN, PredictiveAlert.STATUS_IN_PROGRESS]).count()
        critical_alerts = alerts.filter(
            status__in=[PredictiveAlert.STATUS_OPEN, PredictiveAlert.STATUS_IN_PROGRESS],
            severity=PredictiveAlert.SEVERITY_CRITICAL,
        ).count()
        base_result = {
            "matched_intent": "predictive_alerts",
            "answer": f"{open_alerts} alerte(s) predictive(s) sont ouvertes, dont {critical_alerts} critique(s).",
            "data": {"open_alerts": open_alerts, "critical_alerts": critical_alerts},
        }

    if base_result is None:
        total_tickets = tickets.count()
        total_products = products.count()
        total_alerts = alerts.count()
        base_result = {
            "matched_intent": "general_summary",
            "answer": (
                f"Le perimetre courant contient {total_tickets} ticket(s), {total_products} produit(s) et {total_alerts} alerte(s) predictive(s)."
            ),
            "data": {
                "tickets_total": total_tickets,
                "products_total": total_products,
                "alerts_total": total_alerts,
                "maintenance_total": tickets.filter(category=Ticket.CATEGORY_MAINTENANCE).count(),
                "bug_total": tickets.filter(category=Ticket.CATEGORY_BUG).count(),
                "average_resolution_hours": float(average_resolution_hours) if average_resolution_hours is not None else None,
            },
        }

    if LLM_CLIENT.enabled:
        system_prompt = (
            "You are an Afrilux SAV BI analyst. "
            "Return valid JSON only with keys: matched_intent, answer, highlights. "
            "Use the supplied numeric facts and do not invent values."
        )
        user_prompt = (
            f"User question: {question}\n"
            f"Baseline answer: {json.dumps(base_result, ensure_ascii=False)}"
        )
        openai_data = _parse_completion_json(LLM_CLIENT.complete_json(system_prompt, user_prompt, max_output_tokens=500))
        if openai_data:
            base_result["matched_intent"] = openai_data.get("matched_intent") or base_result["matched_intent"]
            base_result["answer"] = openai_data.get("answer") or base_result["answer"]
            if openai_data.get("highlights"):
                base_result["highlights"] = openai_data["highlights"]

    return base_result
