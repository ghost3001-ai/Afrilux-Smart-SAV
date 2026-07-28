from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from ..comms import create_external_channel_notifications
from ..models import (
    AccountCredit,
    Message,
    OfferRecommendation,
    Ticket,
    WorkflowExecution,
)
from .analytics import _format_money, calculate_sentiment
from .audit import log_audit_event
from .tickets import manager_queryset_for_organization


def ensure_offer(client, offer_type, title, description, rationale, price, ticket=None, product=None, valid_days=30):
    existing_offer = OfferRecommendation.objects.filter(
        client=client,
        product=product,
        offer_type=offer_type,
        status=OfferRecommendation.STATUS_PROPOSED,
    ).first()
    if existing_offer:
        return existing_offer, False

    offer = OfferRecommendation.objects.create(
        client=client,
        ticket=ticket,
        product=product,
        offer_type=offer_type,
        title=title,
        description=description,
        rationale=rationale,
        price=price,
        valid_until=timezone.now() + timedelta(days=valid_days),
    )
    return offer, True


def generate_offer_recommendations(client, ticket=None, product=None, persist=True):
    product = product or getattr(ticket, "product", None)
    offers = []

    if product and product.warranty_end:
        days_to_warranty_end = (product.warranty_end - timezone.localdate()).days
        if 0 <= days_to_warranty_end <= 60:
            offer_data = {
                "offer_type": OfferRecommendation.TYPE_WARRANTY_EXTENSION,
                "title": "Extension de garantie Afrilux",
                "description": "Etendez la couverture de votre equipement pour 12 mois supplementaires.",
                "rationale": "La garantie du produit arrive a expiration bientot.",
                "price": Decimal("25000.00"),
            }
            offers.append(offer_data)

    if product:
        breakdown_count = product.tickets.filter(category=Ticket.CATEGORY_BREAKDOWN).count()
        if breakdown_count >= 2:
            offer_data = {
                "offer_type": OfferRecommendation.TYPE_MAINTENANCE_CONTRACT,
                "title": "Contrat de maintenance predictive",
                "description": "Programme de maintenance preventive avec surveillance et priorite d'intervention.",
                "rationale": "Le produit presente des incidents repetes. Un contrat reduit le risque d'arret.",
                "price": Decimal("60000.00"),
            }
            offers.append(offer_data)

        if breakdown_count >= 3 or product.health_score <= 60:
            offer_data = {
                "offer_type": OfferRecommendation.TYPE_UPGRADE,
                "title": "Offre de mise a niveau produit",
                "description": "Remplacez l'equipement actuel par une version plus recente et plus fiable.",
                "rationale": "Les pannes recurrentes et l'etat de sante du produit suggerent une mise a niveau.",
                "price": Decimal("120000.00"),
            }
            offers.append(offer_data)

    if ticket and ticket.priority == Ticket.PRIORITY_CRITICAL:
        offer_data = {
            "offer_type": OfferRecommendation.TYPE_PREMIUM_SUPPORT,
            "title": "Support premium 24/7",
            "description": "Beneficiez d'un SLA renforce et d'un canal prioritaire pour vos incidents critiques.",
            "rationale": "Ce client rencontre un incident critique et peut beneficier d'un support renforce.",
            "price": Decimal("45000.00"),
        }
        offers.append(offer_data)

    if not persist:
        return offers

    persisted_offers = []
    for offer in offers:
        offer_obj, created = ensure_offer(
            client=client,
            ticket=ticket,
            product=product,
            offer_type=offer["offer_type"],
            title=offer["title"],
            description=offer["description"],
            rationale=offer["rationale"],
            price=offer["price"],
        )
        persisted_offers.append({"offer": offer_obj, "created": created})
    return persisted_offers


def credit_account_for_ticket(
    ticket,
    *,
    amount,
    actor=None,
    reason="Credit SAV",
    note="",
    currency="XAF",
    external_reference="",
):
    """Credite le compte d'un client suite a un ticket SAV.

    Valide le montant, cree le credit, envoie les notifications
    et journalise l'action dans le workflow et l'audit.

    Args:
        ticket: Instance du modele Ticket concerne.
        amount: Montant du credit (Decimal ou string, doit etre > 0).
        actor: Utilisateur ayant effectue l'action (optionnel).
        reason: Motif du credit.
        note: Note complementaire (optionnel).
        currency: Code devise (defaut XAF).
        external_reference: Reference externe (optionnel).

    Returns:
        Dictionnaire contenant le credit cree et les notifications.

    Raises:
        ValueError: Si le montant est <= 0.
    """
    credited_amount = _format_money(amount)
    if credited_amount <= Decimal("0.00"):
        raise ValueError("Le montant du credit doit etre strictement positif.")

    normalized_currency = (currency or "XAF").strip().upper()[:10] or "XAF"
    resolved_actor = actor
    if resolved_actor is None or not getattr(resolved_actor, "is_authenticated", False):
        resolved_actor = ticket.assigned_agent or manager_queryset_for_organization(ticket.organization).first()

    credit = AccountCredit.objects.create(
        ticket=ticket,
        client=ticket.client,
        executed_by=resolved_actor,
        amount=credited_amount,
        currency=normalized_currency,
        reason=(reason or "Credit SAV").strip()[:255] or "Credit SAV",
        note=(note or "").strip(),
        external_reference=(external_reference or "").strip()[:120],
        status=AccountCredit.STATUS_EXECUTED,
        executed_at=timezone.now(),
    )

    message_text = (
        f"Un credit de {credit.amount} {credit.currency} a ete applique sur votre compte. Raison: {credit.reason}."
    )
    if credit.note:
        message_text = f"{message_text} {credit.note}"

    message = None
    if resolved_actor is not None:
        message = Message.objects.create(
            ticket=ticket,
            sender=resolved_actor,
            message_type=Message.TYPE_PUBLIC,
            channel=Message.CHANNEL_PORTAL,
            direction=Message.DIRECTION_OUTBOUND,
            content=message_text,
            sentiment_score=calculate_sentiment(message_text),
        )
        if ticket.first_response_at is None:
            ticket.first_response_at = timezone.now()
            ticket.save(update_fields=["first_response_at", "updated_at"])

    notifications = create_external_channel_notifications(
        recipient=ticket.client,
        subject=f"Credit compte {ticket.reference}",
        message=message_text,
        event_type="account_credit",
        ticket=ticket,
    )

    execution = WorkflowExecution.objects.create(
        ticket=ticket,
        status=WorkflowExecution.STATUS_SUCCESS,
        trigger_event="account_credit",
        result={
            "credit_id": credit.id,
            "amount": str(credit.amount),
            "currency": credit.currency,
            "reason": credit.reason,
            "notification_ids": [item.id for item in notifications],
            "message_id": message.id if message else None,
        },
    )
    log_audit_event(
        actor=resolved_actor or actor,
        action="account_credit_executed",
        instance=credit,
        details={"ticket_reference": ticket.reference, "workflow_execution_id": execution.id},
    )

    return {
        "credit": credit,
        "message": message,
        "notifications": notifications,
        "workflow_execution": execution,
    }
