import base64
import json
import os
import re
from datetime import timedelta
from dataclasses import dataclass
from email import policy
from email.header import decode_header
from email.parser import BytesParser
from email.utils import parseaddr
from urllib import error, parse, request

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.mail import send_mail
from django.utils import timezone
from google.auth.transport.requests import Request as GoogleAuthRequest

from .file_validation import validate_ticket_attachment_file
from .models import AuditLog, DeviceRegistration, Message, Notification, Organization, Ticket, TicketAttachment, User


EXTERNAL_CHANNEL_FALLBACKS = {
    Notification.CHANNEL_WHATSAPP: Notification.CHANNEL_SMS,
    Notification.CHANNEL_SMS: Notification.CHANNEL_EMAIL,
}
DEFAULT_EXTERNAL_CHANNELS = [
    Notification.CHANNEL_WHATSAPP,
    Notification.CHANNEL_SMS,
    Notification.CHANNEL_EMAIL,
]
SAV_EVENT_CHANNELS = {
    "ticket_created_by_client": DEFAULT_EXTERNAL_CHANNELS,
    "ticket_assignment": DEFAULT_EXTERNAL_CHANNELS,
    "ticket_technician_assigned": DEFAULT_EXTERNAL_CHANNELS,
    "ticket_team_assigned": DEFAULT_EXTERNAL_CHANNELS,
    "planning_proposed": DEFAULT_EXTERNAL_CHANNELS,
    "planning_confirmed": [Notification.CHANNEL_WHATSAPP, Notification.CHANNEL_SMS],
    "start_validated": [Notification.CHANNEL_WHATSAPP, Notification.CHANNEL_SMS],
    "finish_validated": [Notification.CHANNEL_WHATSAPP, Notification.CHANNEL_SMS],
    "ticket_escalation_requested": DEFAULT_EXTERNAL_CHANNELS,
    "ticket_escalation_solution": DEFAULT_EXTERNAL_CHANNELS,
    "ticket_reassigned": DEFAULT_EXTERNAL_CHANNELS,
    "ticket_closure_report": [Notification.CHANNEL_EMAIL],
}


@dataclass
class DeliveryResult:
    success: bool
    provider: str
    external_id: str = ""
    error_message: str = ""
    payload: dict | None = None


def normalize_phone(value: str) -> str:
    if not value:
        return ""
    value = value.strip()
    value = value.replace("whatsapp:", "")
    digits = re.sub(r"[^\d+]", "", value)
    if digits.startswith("00"):
        digits = f"+{digits[2:]}"
    return digits


def twilio_sms_enabled() -> bool:
    return bool(settings.TWILIO_ACCOUNT_SID and settings.TWILIO_AUTH_TOKEN and settings.TWILIO_SMS_FROM)


def twilio_whatsapp_enabled() -> bool:
    return bool(settings.TWILIO_ACCOUNT_SID and settings.TWILIO_AUTH_TOKEN and settings.TWILIO_WHATSAPP_FROM)


def email_enabled() -> bool:
    return bool(settings.EMAIL_HOST and settings.DEFAULT_FROM_EMAIL)


def firebase_push_enabled() -> bool:
    return bool(settings.FIREBASE_PROJECT_ID)


def build_ticket_deep_link(ticket: Ticket | None) -> str:
    if not ticket:
        return ""
    public_base_url = getattr(settings, "SAV_PUBLIC_BASE_URL", "").strip().rstrip("/")
    if not public_base_url:
        public_base_url = "http://127.0.0.1:8000"
    return f"{public_base_url}/tickets/{ticket.pk}/"


def notification_action_payload(event_type: str, ticket: Ticket | None) -> dict:
    actions_by_event = {
        "planning_proposed": [
            {"key": "accept", "label": "Accepter"},
            {"key": "reject", "label": "Refuser"},
        ],
        "start_requested": [
            {"key": "yes", "label": "Oui, commencer"},
            {"key": "no", "label": "Non, reporter"},
        ],
        "finish_requested": [
            {"key": "yes", "label": "Oui, terminer"},
            {"key": "no", "label": "Non, continuer"},
        ],
    }
    actions = actions_by_event.get(event_type, [])
    if not actions:
        return {}
    return {
        "event_type": event_type,
        "ticket_id": ticket.id if ticket else None,
        "actions": actions,
    }


def recipient_contact_for_channel(recipient: User, channel: str) -> str:
    if channel == Notification.CHANNEL_EMAIL:
        return (recipient.email or recipient.professional_email or "").strip()
    if channel == Notification.CHANNEL_WHATSAPP:
        return normalize_phone(getattr(recipient, "whatsapp_phone", "") or recipient.phone)
    if channel == Notification.CHANNEL_SMS:
        return normalize_phone(getattr(recipient, "sms_phone", "") or recipient.phone)
    if channel == Notification.CHANNEL_PUSH:
        return "device"
    return recipient.username


def recipient_channel_enabled(recipient: User, channel: str) -> bool:
    if channel == Notification.CHANNEL_IN_APP:
        return True
    if channel == Notification.CHANNEL_EMAIL:
        return bool(getattr(recipient, "notification_email_enabled", True))
    if channel == Notification.CHANNEL_SMS:
        return bool(getattr(recipient, "notification_sms_enabled", True))
    if channel == Notification.CHANNEL_WHATSAPP:
        return bool(getattr(recipient, "notification_whatsapp_enabled", True))
    if channel == Notification.CHANNEL_PUSH:
        return bool(getattr(recipient, "notification_push_enabled", True))
    return False


def channel_provider_available(recipient: User, channel: str) -> bool:
    contact = recipient_contact_for_channel(recipient, channel)
    if channel == Notification.CHANNEL_IN_APP:
        return True
    if channel == Notification.CHANNEL_EMAIL:
        return bool(contact and email_enabled())
    if channel == Notification.CHANNEL_SMS:
        return bool(contact and twilio_sms_enabled())
    if channel == Notification.CHANNEL_WHATSAPP:
        return bool(contact and twilio_whatsapp_enabled())
    if channel == Notification.CHANNEL_PUSH:
        return bool(firebase_push_enabled() and recipient.device_registrations.filter(is_active=True).exists())
    return False


def external_delivery_paused(recipient: User, now=None) -> str:
    now = timezone.localtime(now or timezone.now())
    start = getattr(recipient, "notification_do_not_disturb_start", None)
    end = getattr(recipient, "notification_do_not_disturb_end", None)
    if start and end:
        current = now.time()
        in_window = start <= current < end if start < end else current >= start or current < end
        if in_window:
            return "Plage ne pas deranger active."

    daily_limit = int(getattr(recipient, "notification_daily_limit", 0) or 0)
    if daily_limit > 0:
        sent_today = Notification.objects.filter(
            recipient=recipient,
            channel__in=DEFAULT_EXTERNAL_CHANNELS,
            created_at__date=now.date(),
        ).count()
        if sent_today >= daily_limit:
            return "Limite quotidienne de notifications atteinte."

    min_interval = int(getattr(recipient, "notification_min_interval_minutes", 0) or 0)
    if min_interval > 0:
        recent_since = now - timedelta(minutes=min_interval)
        if Notification.objects.filter(
            recipient=recipient,
            channel__in=DEFAULT_EXTERNAL_CHANNELS,
            created_at__gte=recent_since,
        ).exists():
            return "Intervalle minimum entre notifications non atteint."
    return ""


def _message_with_deep_link(notification: Notification, *, max_length=None) -> str:
    message = notification.message or ""
    if notification.deep_link and notification.deep_link not in message:
        message = f"{message}\nOuvrir: {notification.deep_link}".strip()
    if max_length and len(message) > max_length:
        return f"{message[: max_length - 3]}..."
    return message


def _default_sla_deadline(priority: str):
    from .services import compute_ticket_sla_deadline

    return compute_ticket_sla_deadline(priority)


def deliver_notification(notification: Notification) -> DeliveryResult:
    notification.recipient_contact = notification.recipient_contact or recipient_contact_for_channel(
        notification.recipient,
        notification.channel,
    )
    if notification.channel == Notification.CHANNEL_IN_APP:
        notification.status = Notification.STATUS_SENT
        notification.sent_at = timezone.now()
        notification.provider = "in_app"
        notification.provider_reference = str(notification.id or "")
        notification.error_message = ""
        notification.save(
            update_fields=[
                "status",
                "sent_at",
                "provider",
                "provider_reference",
                "error_message",
                "recipient_contact",
            ]
        )
        return DeliveryResult(success=True, provider="in_app")

    pause_reason = external_delivery_paused(notification.recipient)
    if pause_reason:
        notification.status = Notification.STATUS_PENDING
        notification.error_message = pause_reason
        notification.save(update_fields=["status", "error_message", "recipient_contact"])
        return DeliveryResult(success=False, provider="paused", error_message=pause_reason)

    if notification.channel == Notification.CHANNEL_EMAIL:
        result = _deliver_email(notification)
    elif notification.channel == Notification.CHANNEL_PUSH:
        result = _deliver_push(notification)
    elif notification.channel == Notification.CHANNEL_SMS:
        result = _deliver_twilio_message(notification, use_whatsapp=False)
    elif notification.channel == Notification.CHANNEL_WHATSAPP:
        result = _deliver_twilio_message(notification, use_whatsapp=True)
    else:
        result = DeliveryResult(success=False, provider="unsupported", error_message="Unsupported channel.")

    if result.success:
        notification.status = Notification.STATUS_SENT
        notification.sent_at = timezone.now()
        notification.error_message = ""
    else:
        notification.status = Notification.STATUS_FAILED
        notification.error_message = result.error_message[:1000]
    notification.provider = result.provider
    notification.provider_reference = result.external_id[:255]
    notification.delivery_payload = result.payload or {}
    notification.save(
        update_fields=[
            "status",
            "sent_at",
            "provider",
            "provider_reference",
            "error_message",
            "delivery_payload",
            "recipient_contact",
        ]
    )

    return result


def dispatch_pending_notifications(channel: str | None = None, organization=None) -> list[dict]:
    queryset = Notification.objects.filter(status=Notification.STATUS_PENDING)
    if channel:
        queryset = queryset.filter(channel=channel)
    if organization is not None:
        queryset = queryset.filter(organization=organization)

    results = []
    for notification in queryset.order_by("created_at"):
        result = deliver_notification(notification)
        results.append(
            {
                "notification_id": notification.id,
                "success": result.success,
                "provider": result.provider,
                "external_id": result.external_id,
                "error_message": result.error_message,
            }
        )
    return results


def _incoming_contacts_organization():
    organization, _ = Organization.objects.get_or_create(
        slug="contacts-entrants",
        defaults={
            "name": "Contacts entrants",
            "brand_name": "Contacts entrants",
            "portal_tagline": "Flux entrants SMS et WhatsApp",
        },
    )
    return organization


def _create_and_deliver_notifications(
    *,
    recipient: User,
    subject: str,
    message: str,
    event_type: str,
    ticket: Ticket | None,
    channels: list[str],
    deep_link: str = "",
    action_payload: dict | None = None,
) -> list[Notification]:
    notifications = []
    created_channels = set()
    action_payload = action_payload or notification_action_payload(event_type, ticket)
    deep_link = deep_link or build_ticket_deep_link(ticket)

    def create_for_channel(channel):
        if channel in created_channels:
            return None
        if not recipient_channel_enabled(recipient, channel):
            return None
        if not channel_provider_available(recipient, channel):
            return None
        notification = Notification.objects.create(
            recipient=recipient,
            ticket=ticket,
            channel=channel,
            event_type=event_type,
            subject=subject,
            message=message,
            status=Notification.STATUS_PENDING,
            recipient_contact=recipient_contact_for_channel(recipient, channel),
            deep_link=deep_link,
            action_payload=action_payload,
        )
        created_channels.add(channel)
        result = deliver_notification(notification)
        notifications.append(notification)
        return notification, result

    for channel in channels:
        created = create_for_channel(channel)
        if not created:
            continue
        notification, result = created
        fallback_channel = EXTERNAL_CHANNEL_FALLBACKS.get(notification.channel)
        if result and not result.success and result.provider != "paused" and fallback_channel:
            create_for_channel(fallback_channel)
    return notifications


def create_external_channel_notifications(
    recipient,
    subject,
    message,
    event_type,
    ticket=None,
    channels=None,
    deep_link="",
    action_payload=None,
) -> list[Notification]:
    selected_channels = [Notification.CHANNEL_IN_APP]
    if recipient_channel_enabled(recipient, Notification.CHANNEL_PUSH) and channel_provider_available(recipient, Notification.CHANNEL_PUSH):
        selected_channels.append(Notification.CHANNEL_PUSH)

    requested_external_channels = list(channels) if channels is not None else list(DEFAULT_EXTERNAL_CHANNELS)
    for channel in requested_external_channels:
        if channel != Notification.CHANNEL_IN_APP and channel not in selected_channels:
            selected_channels.append(channel)
    return _create_and_deliver_notifications(
        recipient=recipient,
        subject=subject,
        message=message,
        event_type=event_type,
        ticket=ticket,
        channels=selected_channels,
        deep_link=deep_link,
        action_payload=action_payload,
    )


def create_sav_event_notifications(recipients, *, event_type, subject, message, ticket=None, channels=None) -> list[Notification]:
    if isinstance(recipients, User):
        recipients = [recipients]
    selected_channels = list(channels) if channels is not None else list(SAV_EVENT_CHANNELS.get(event_type, DEFAULT_EXTERNAL_CHANNELS))
    notifications = []
    deduped_recipients = {recipient.id: recipient for recipient in recipients if getattr(recipient, "id", None)}
    for recipient in deduped_recipients.values():
        notifications.extend(
            create_external_channel_notifications(
                recipient=recipient,
                ticket=ticket,
                event_type=event_type,
                subject=subject,
                message=message,
                channels=selected_channels,
            )
        )
    return notifications


def create_message_delivery_notifications(message: Message) -> list[Notification]:
    if message.direction != Message.DIRECTION_OUTBOUND or message.message_type != Message.TYPE_PUBLIC:
        return []

    recipient = message.recipient or message.ticket.client
    channels = [Notification.CHANNEL_IN_APP]
    if recipient_channel_enabled(recipient, Notification.CHANNEL_PUSH) and channel_provider_available(recipient, Notification.CHANNEL_PUSH):
        channels.append(Notification.CHANNEL_PUSH)

    if message.channel == Message.CHANNEL_EMAIL and channel_provider_available(recipient, Notification.CHANNEL_EMAIL):
        channels.append(Notification.CHANNEL_EMAIL)
    elif message.channel == Message.CHANNEL_SMS and channel_provider_available(recipient, Notification.CHANNEL_SMS):
        channels.append(Notification.CHANNEL_SMS)
    elif message.channel == Message.CHANNEL_WHATSAPP and channel_provider_available(recipient, Notification.CHANNEL_WHATSAPP):
        channels.append(Notification.CHANNEL_WHATSAPP)

    return _create_and_deliver_notifications(
        recipient=recipient,
        ticket=message.ticket,
        event_type="ticket_message",
        subject=f"{message.ticket.reference} - Mise a jour SAV",
        message=message.content,
        channels=channels,
    )


def handle_twilio_inbound(payload: dict[str, str]) -> dict:
    from_value = payload.get("From", "")
    body = payload.get("Body", "").strip()
    channel = Message.CHANNEL_WHATSAPP if from_value.startswith("whatsapp:") else Message.CHANNEL_SMS
    phone = normalize_phone(from_value)

    if not phone or not body:
        return {"created": False, "reason": "missing_phone_or_body"}

    client = User.objects.filter(role=User.ROLE_CLIENT, phone=phone).first()
    if client is None:
        username = f"contact_{re.sub(r'[^0-9]', '', phone)[-8:] or 'client'}"
        incoming_organization = _incoming_contacts_organization()
        client, _ = User.objects.get_or_create(
            username=username,
            defaults={
                "organization": incoming_organization,
                "role": User.ROLE_CLIENT,
                "phone": phone,
                "company_name": "Contact entrant",
            },
        )
        if not client.phone:
            client.phone = phone
        if not client.organization_id:
            client.organization = incoming_organization
        client.save(update_fields=["phone", "organization"])

    ticket_reference_match = re.search(r"(SAV-[A-Z0-9-]+)", body)
    ticket = None
    if ticket_reference_match:
        ticket = Ticket.objects.filter(reference=ticket_reference_match.group(1), client=client).first()

    if ticket is None:
        ticket = client.tickets.filter(status__in=[
            Ticket.STATUS_NEW,
            Ticket.STATUS_PENDING_ASSIGNMENT,
            Ticket.STATUS_ASSIGNED,
            Ticket.STATUS_IN_PROGRESS,
            Ticket.STATUS_WAITING_PART,
        ]).order_by("-created_at").first()

    if ticket is None:
        ticket = Ticket.objects.create(
            client=client,
            title=body[:80],
            description=body,
            category=Ticket.CATEGORY_BREAKDOWN,
            channel=Ticket.CHANNEL_WHATSAPP if channel == Message.CHANNEL_WHATSAPP else Ticket.CHANNEL_PHONE,
            status=Ticket.STATUS_PENDING_ASSIGNMENT,
            priority=Ticket.PRIORITY_NORMAL,
            sla_deadline=_default_sla_deadline(Ticket.PRIORITY_NORMAL),
        )

    message = Message.objects.create(
        ticket=ticket,
        sender=client,
        message_type=Message.TYPE_PUBLIC,
        channel=channel,
        direction=Message.DIRECTION_INBOUND,
        content=body,
    )

    from .services import log_audit_event

    log_audit_event(
        actor=client,
        actor_type=AuditLog.ACTOR_SYSTEM,
        action="twilio_inbound_received",
        instance=message,
        target_reference=ticket.reference,
        details={"from": phone, "channel": channel},
    )

    return {
        "created": True,
        "ticket_reference": ticket.reference,
        "message_id": message.id,
        "client_id": client.id,
        "channel": channel,
    }


def infer_attachment_kind(uploaded_file):
    content_type = (getattr(uploaded_file, "content_type", "") or "").lower()
    name = (getattr(uploaded_file, "name", "") or "").lower()
    if "receipt" in name or "recu" in name:
        return TicketAttachment.KIND_RECEIPT
    if content_type.startswith("image/"):
        return TicketAttachment.KIND_SCREENSHOT
    return TicketAttachment.KIND_PROOF


def _decode_mime_header(value):
    if not value:
        return ""

    decoded_parts = []
    for chunk, encoding in decode_header(value):
        if isinstance(chunk, bytes):
            decoded_parts.append(chunk.decode(encoding or "utf-8", errors="replace"))
        else:
            decoded_parts.append(chunk)
    return "".join(decoded_parts).strip()


def _extract_email_body(message):
    text_parts = []
    html_parts = []

    if message.is_multipart():
        for part in message.walk():
            if part.get_content_maintype() == "multipart":
                continue
            if part.get_content_disposition() == "attachment":
                continue
            try:
                content = part.get_content()
            except Exception:  # noqa: BLE001
                content = ""
            if not content:
                continue
            if part.get_content_type() == "text/plain":
                text_parts.append(str(content).strip())
            elif part.get_content_type() == "text/html":
                html_parts.append(str(content).strip())
    else:
        try:
            content = message.get_content()
        except Exception:  # noqa: BLE001
            content = ""
        if content:
            if message.get_content_type() == "text/html":
                html_parts.append(str(content).strip())
            else:
                text_parts.append(str(content).strip())

    if text_parts:
        return "\n\n".join(part for part in text_parts if part).strip()
    if html_parts:
        html = "\n\n".join(part for part in html_parts if part)
        html = re.sub(r"<br\s*/?>", "\n", html, flags=re.IGNORECASE)
        html = re.sub(r"</p\s*>", "\n\n", html, flags=re.IGNORECASE)
        html = re.sub(r"<[^>]+>", " ", html)
        return re.sub(r"\s+", " ", html).strip()
    return ""


def parse_inbound_email_message(raw_message, *, default_recipient="", organization_slug=""):
    message = BytesParser(policy=policy.default).parsebytes(raw_message)
    sender_name, sender_email = parseaddr(message.get("From", ""))
    recipient = (
        _decode_mime_header(message.get("Delivered-To", ""))
        or _decode_mime_header(message.get("To", ""))
        or default_recipient
    )
    subject = _decode_mime_header(message.get("Subject", ""))
    body = _extract_email_body(message)

    uploaded_files = []
    for part in message.iter_attachments():
        filename = _decode_mime_header(part.get_filename() or "") or "piece-jointe"
        content_type = part.get_content_type() or "application/octet-stream"
        try:
            content = part.get_content()
        except Exception:  # noqa: BLE001
            content = b""
        if isinstance(content, str):
            content = content.encode(part.get_content_charset() or "utf-8", errors="replace")
        uploaded_files.append(
            SimpleUploadedFile(
                filename,
                content,
                content_type=content_type,
            )
        )

    payload = {
        "from": sender_email.strip().lower(),
        "from_name": _decode_mime_header(sender_name),
        "subject": subject,
        "body": body,
        "to": recipient,
        "organization_slug": organization_slug,
    }
    return payload, uploaded_files


def _organization_from_inbound_email(payload, sender_email):
    organization_slug = str(payload.get("organization_slug", "")).strip()
    if organization_slug:
        organization = Organization.objects.filter(slug=organization_slug).first()
        if organization:
            return organization

    recipient_email = (
        str(payload.get("to", "")).strip()
        or str(payload.get("recipient", "")).strip()
        or str(payload.get("envelope_to", "")).strip()
    )
    if recipient_email:
        organization = Organization.objects.filter(support_email__iexact=recipient_email).first()
        if organization:
            return organization

    if sender_email:
        client = User.objects.filter(role=User.ROLE_CLIENT, email__iexact=sender_email).select_related("organization").first()
        if client and client.organization_id:
            return client.organization

    return _incoming_contacts_organization()


def _find_or_create_email_client(sender_email, organization, sender_name=""):
    client = User.objects.filter(role=User.ROLE_CLIENT, email__iexact=sender_email).first()
    if client:
        fields_to_update = []
        if organization and not client.organization_id:
            client.organization = organization
            fields_to_update.append("organization")
        if organization and not client.company_name:
            client.company_name = organization.display_name
            fields_to_update.append("company_name")
        if fields_to_update:
            client.save(update_fields=fields_to_update)
        return client

    base_username = re.sub(r"[^a-z0-9]+", "_", sender_email.split("@")[0].lower()).strip("_") or "email_client"
    username = base_username
    suffix = 2
    while User.objects.filter(username=username).exists():
        username = f"{base_username}_{suffix}"
        suffix += 1

    first_name = sender_name.strip()[:150]
    client = User.objects.create(
        username=username[:150],
        email=sender_email,
        organization=organization,
        role=User.ROLE_CLIENT,
        company_name=organization.display_name if organization else "",
        first_name=first_name,
    )
    client.set_unusable_password()
    client.save(update_fields=["password"])
    return client


def handle_email_inbound(payload: dict[str, str], uploaded_files=None) -> dict:
    from .services import (
        calculate_sentiment,
        infer_priority_from_text,
        infer_ticket_category_from_text,
    )

    uploaded_files = uploaded_files or []
    sender_email = (
        str(payload.get("from", "")).strip()
        or str(payload.get("sender", "")).strip()
        or str(payload.get("email", "")).strip()
    ).lower()
    sender_name = str(payload.get("from_name", "")).strip() or str(payload.get("sender_name", "")).strip()
    subject = str(payload.get("subject", "")).strip()
    body = (
        str(payload.get("text", "")).strip()
        or str(payload.get("body", "")).strip()
        or str(payload.get("plain", "")).strip()
        or str(payload.get("stripped-text", "")).strip()
    )

    if not sender_email or not (subject or body):
        return {"created": False, "reason": "missing_sender_or_content"}

    organization = _organization_from_inbound_email(payload, sender_email)
    client = _find_or_create_email_client(sender_email, organization, sender_name=sender_name)

    full_text = " ".join(filter(None, [subject, body]))
    ticket_reference_match = re.search(r"(SAV-[A-Z0-9-]+)", full_text.upper())
    ticket = None
    if ticket_reference_match:
        ticket = Ticket.objects.filter(reference=ticket_reference_match.group(1), client=client).first()

    if ticket is None:
        ticket = client.tickets.filter(
            status__in=[
                Ticket.STATUS_NEW,
                Ticket.STATUS_PENDING_ASSIGNMENT,
                Ticket.STATUS_ASSIGNED,
                Ticket.STATUS_IN_PROGRESS,
                Ticket.STATUS_WAITING_PART,
            ]
        ).order_by("-created_at").first()

    created_ticket = False
    if ticket is None:
        priority = infer_priority_from_text(full_text, Ticket.PRIORITY_NORMAL)
        ticket = Ticket.objects.create(
            client=client,
            title=(subject or body[:80] or "Demande email SAV")[:255],
            description=body or subject,
            category=infer_ticket_category_from_text(full_text, Ticket.CATEGORY_BREAKDOWN),
            channel=Ticket.CHANNEL_EMAIL,
            status=Ticket.STATUS_PENDING_ASSIGNMENT,
            priority=priority,
            sla_deadline=_default_sla_deadline(priority),
        )
        created_ticket = True

    message = Message.objects.create(
        ticket=ticket,
        sender=client,
        message_type=Message.TYPE_PUBLIC,
        channel=Message.CHANNEL_EMAIL,
        direction=Message.DIRECTION_INBOUND,
        content=body or subject,
        sentiment_score=calculate_sentiment(full_text),
    )

    created_attachments = []
    rejected_attachments = []
    for uploaded_file in uploaded_files:
        try:
            validate_ticket_attachment_file(uploaded_file)
        except ValidationError as exc:
            rejected_attachments.append({"name": getattr(uploaded_file, "name", ""), "error": "; ".join(exc.messages)})
            continue
        attachment = TicketAttachment.objects.create(
            ticket=ticket,
            uploaded_by=None,
            kind=infer_attachment_kind(uploaded_file),
            file=uploaded_file,
            note="Piece jointe recue par email entrant.",
        )
        created_attachments.append(attachment.id)

    from .services import log_audit_event

    log_audit_event(
        actor=client,
        actor_type=AuditLog.ACTOR_SYSTEM,
        action="email_inbound_received",
        instance=message,
        target_reference=ticket.reference,
        details={
            "from": sender_email,
            "subject": subject,
            "attachments": created_attachments,
            "rejected_attachments": rejected_attachments,
            "created_ticket": created_ticket,
        },
    )

    return {
        "created": True,
        "created_ticket": created_ticket,
        "ticket_reference": ticket.reference,
        "message_id": message.id,
        "attachment_count": len(created_attachments),
        "rejected_attachment_count": len(rejected_attachments),
        "organization_slug": organization.slug if organization else "",
        "client_id": client.id,
    }


def _deliver_email(notification: Notification) -> DeliveryResult:
    if not email_enabled():
        return DeliveryResult(success=False, provider="smtp", error_message="SMTP is not configured.")
    recipient_email = recipient_contact_for_channel(notification.recipient, Notification.CHANNEL_EMAIL)
    if not recipient_email:
        return DeliveryResult(success=False, provider="smtp", error_message="Recipient has no email address.")

    try:
        sent_count = send_mail(
            notification.subject,
            _message_with_deep_link(notification),
            settings.DEFAULT_FROM_EMAIL,
            [recipient_email],
            fail_silently=False,
        )
    except Exception as exc:  # noqa: BLE001
        return DeliveryResult(success=False, provider="smtp", error_message=str(exc))

    return DeliveryResult(success=sent_count > 0, provider="smtp")


def _firebase_access_token():
    scopes = ["https://www.googleapis.com/auth/firebase.messaging"]
    credentials_file = settings.FIREBASE_CREDENTIALS_FILE or os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "")

    try:
        if credentials_file:
            from google.oauth2 import service_account

            credentials = service_account.Credentials.from_service_account_file(credentials_file, scopes=scopes)
        else:
            import google.auth

            credentials, _ = google.auth.default(scopes=scopes)
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"Impossible de charger les credentials Firebase: {exc}") from exc

    credentials.refresh(GoogleAuthRequest())
    return credentials.token


def _deliver_push(notification: Notification) -> DeliveryResult:
    if not firebase_push_enabled():
        return DeliveryResult(success=False, provider="fcm", error_message="Firebase Cloud Messaging is not configured.")

    devices = list(
        DeviceRegistration.objects.filter(user=notification.recipient, is_active=True).order_by("-last_seen_at")
    )
    if not devices:
        return DeliveryResult(success=False, provider="fcm", error_message="Recipient has no active push device.")

    try:
        access_token = _firebase_access_token()
    except Exception as exc:  # noqa: BLE001
        return DeliveryResult(success=False, provider="fcm", error_message=str(exc))

    successes = []
    failures = []

    for device in devices:
        payload = {
            "message": {
                "token": device.token,
                "notification": {
                    "title": notification.subject,
                    "body": notification.message[:500],
                },
                "data": {
                    "notification_id": str(notification.id),
                    "ticket_id": str(notification.ticket_id or ""),
                    "event_type": notification.event_type,
                    "channel": notification.channel,
                    "subject": notification.subject,
                    "message": notification.message[:500],
                    "deep_link": notification.deep_link,
                    "action_payload": json.dumps(notification.action_payload or {}),
                },
                "android": {"priority": "high"},
                "apns": {
                    "headers": {"apns-priority": "10"},
                    "payload": {"aps": {"sound": "default"}},
                },
            }
        }

        req = request.Request(
            f"https://fcm.googleapis.com/v1/projects/{settings.FIREBASE_PROJECT_ID}/messages:send",
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json; charset=UTF-8",
            },
        )

        try:
            with request.urlopen(req, timeout=30) as response:
                raw = json.loads(response.read().decode("utf-8"))
                successes.append(raw.get("name", ""))
                device.last_seen_at = timezone.now()
                device.save(update_fields=["last_seen_at", "updated_at"])
        except error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            failures.append({"token": device.token, "error": body[:300]})
            if exc.code in {400, 404} and "UNREGISTERED" in body.upper():
                device.is_active = False
                device.save(update_fields=["is_active", "updated_at"])
        except Exception as exc:  # noqa: BLE001
            failures.append({"token": device.token, "error": str(exc)})

    if successes:
        return DeliveryResult(
            success=True,
            provider="fcm",
            external_id=",".join(filter(None, successes)),
            payload={"successes": successes, "failures": failures},
        )

    return DeliveryResult(
        success=False,
        provider="fcm",
        error_message=failures[0]["error"] if failures else "Unknown FCM failure.",
        payload={"failures": failures},
    )


def _deliver_twilio_message(notification: Notification, use_whatsapp: bool) -> DeliveryResult:
    if use_whatsapp and not twilio_whatsapp_enabled():
        return DeliveryResult(success=False, provider="twilio_whatsapp", error_message="Twilio WhatsApp is not configured.")
    if not use_whatsapp and not twilio_sms_enabled():
        return DeliveryResult(success=False, provider="twilio_sms", error_message="Twilio SMS is not configured.")

    to_phone = recipient_contact_for_channel(
        notification.recipient,
        Notification.CHANNEL_WHATSAPP if use_whatsapp else Notification.CHANNEL_SMS,
    )
    if not to_phone:
        return DeliveryResult(success=False, provider="twilio", error_message="Recipient has no phone number.")

    from_value = settings.TWILIO_WHATSAPP_FROM if use_whatsapp else settings.TWILIO_SMS_FROM
    to_value = f"whatsapp:{to_phone}" if use_whatsapp else to_phone
    if use_whatsapp and not from_value.startswith("whatsapp:"):
        from_value = f"whatsapp:{from_value}"

    form = {
        "To": to_value,
        "From": from_value,
        "Body": _message_with_deep_link(notification, max_length=1500 if use_whatsapp else 320),
    }
    if settings.TWILIO_STATUS_CALLBACK_URL:
        form["StatusCallback"] = settings.TWILIO_STATUS_CALLBACK_URL

    encoded = parse.urlencode(form).encode("utf-8")
    auth_value = base64.b64encode(
        f"{settings.TWILIO_ACCOUNT_SID}:{settings.TWILIO_AUTH_TOKEN}".encode("utf-8")
    ).decode("ascii")
    req = request.Request(
        f"https://api.twilio.com/2010-04-01/Accounts/{settings.TWILIO_ACCOUNT_SID}/Messages.json",
        data=encoded,
        method="POST",
        headers={
            "Authorization": f"Basic {auth_value}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )

    try:
        with request.urlopen(req, timeout=30) as response:
            raw = json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return DeliveryResult(
            success=False,
            provider="twilio_whatsapp" if use_whatsapp else "twilio_sms",
            error_message=f"Twilio HTTP {exc.code}: {body[:300]}",
        )
    except Exception as exc:  # noqa: BLE001
        return DeliveryResult(
            success=False,
            provider="twilio_whatsapp" if use_whatsapp else "twilio_sms",
            error_message=str(exc),
        )

    return DeliveryResult(
        success=True,
        provider="twilio_whatsapp" if use_whatsapp else "twilio_sms",
        external_id=raw.get("sid", ""),
        payload=raw,
    )
