from django.urls import reverse

from .models import Notification, Ticket
from .services import (
    OPEN_TICKET_STATUSES,
    has_backoffice_access,
    has_reporting_access,
    has_technician_space_access,
    is_internal_user,
    is_manager_user,
    role_workspace_name,
    scope_notification_queryset,
    scope_ticket_queryset,
)


def sav_shell(request):
    def _workspace_payload(current_user):
        workspace_name = role_workspace_name(current_user)
        workspace_url = reverse(workspace_name)
        if workspace_name == "ticket-list" and current_user.role in {
            current_user.ROLE_SUPPORT,
            current_user.ROLE_AGENT,
            current_user.ROLE_VIP_SUPPORT,
            current_user.ROLE_CFAO_MANAGER,
            current_user.ROLE_CFAO_WORKS,
            current_user.ROLE_HVAC_MANAGER,
            current_user.ROLE_SOFTWARE_OWNER,
        }:
            workspace_url = f"{workspace_url}?assignment=mine"
        workspace_labels = {
            "support-page": "Espace client",
            "ticket-list": "Espace tickets",
            "technician-space": "Espace technicien",
            "planning-page": "Espace dispatch",
            "reporting-page": "Espace reporting",
            "dashboard": "Espace pilotage",
        }
        return {
            "workspace_name": workspace_name,
            "workspace_url": workspace_url,
            "workspace_label": workspace_labels.get(workspace_name, "Mon espace"),
        }

    user = request.user
    if not user or not user.is_authenticated:
        return {
            "sav_shell": {
                "is_authenticated": False,
                "is_internal": False,
                "has_backoffice_access": False,
                "has_reporting_access": False,
                "has_management_access": False,
                "has_technician_space_access": False,
                "unread_notifications": 0,
                "open_tickets": 0,
                "organization_name": "",
                "organization_initials": "",
                "organization_tagline": "",
                "organization_primary_color": "",
                "organization_accent_color": "",
                "workspace_name": "login",
                "workspace_url": reverse("login"),
                "workspace_label": "Connexion",
            }
        }

    notifications = scope_notification_queryset(Notification.objects.all(), user)
    tickets = scope_ticket_queryset(Ticket.objects.all(), user)

    return {
        "sav_shell": {
            "is_authenticated": True,
            "is_internal": is_internal_user(user),
            "has_backoffice_access": has_backoffice_access(user) or getattr(user, "is_superuser", False),
            "has_reporting_access": has_reporting_access(user),
            "has_management_access": is_manager_user(user),
            "has_technician_space_access": has_technician_space_access(user),
            "unread_notifications": notifications.exclude(status=Notification.STATUS_READ).count(),
            "open_tickets": tickets.filter(status__in=OPEN_TICKET_STATUSES).count(),
            "organization_name": user.organization.display_name if getattr(user, "organization_id", None) else "",
            "organization_initials": user.organization.initials if getattr(user, "organization_id", None) else "",
            "organization_tagline": user.organization.portal_tagline if getattr(user, "organization_id", None) else "",
            "organization_primary_color": user.organization.primary_color if getattr(user, "organization_id", None) else "",
            "organization_accent_color": user.organization.accent_color if getattr(user, "organization_id", None) else "",
            **_workspace_payload(user),
        }
    }
