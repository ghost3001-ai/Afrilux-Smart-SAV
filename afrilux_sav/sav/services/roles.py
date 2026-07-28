from django.db.models import Q

from ..models import KnowledgeArticle, MaintenanceTicket, Message, Ticket, User
from .constants import GLOBAL_AGENCY_SCOPE_ROLES, TICKET_CREATOR_ROLES


def is_manager_user(user):
    return bool(
        user
        and user.is_authenticated
        and (user.is_superuser or getattr(user, "role", "") in set(User.MANAGER_ROLES))
    )


def is_support_user(user):
    return bool(
        user
        and user.is_authenticated
        and getattr(user, "role", "") in set(User.FRONTLINE_ROLES)
    )


def is_admin_user(user):
    return bool(user and user.is_authenticated and (user.is_superuser or getattr(user, "role", "") == User.ROLE_ADMIN))


def can_create_ticket(user):
    return bool(
        user
        and user.is_authenticated
        and (user.is_superuser or getattr(user, "role", "") in TICKET_CREATOR_ROLES)
    )


def is_internal_user(user):
    return bool(
        user
        and user.is_authenticated
        and (user.is_superuser or getattr(user, "role", "") in set(User.INTERNAL_ROLES))
    )


def is_platform_internal_user(user):
    return bool(is_internal_user(user) and not getattr(user, "organization_id", None))


def is_read_only_user(user):
    return bool(user and user.is_authenticated and getattr(user, "role", "") in set(User.READ_ONLY_ROLES))


def is_auditor_user(user):
    return bool(user and user.is_authenticated and getattr(user, "role", "") == User.ROLE_AUDITOR)


def has_technician_space_access(user):
    return bool(
        user
        and user.is_authenticated
        and (user.is_superuser or getattr(user, "role", "") in set(User.TECHNICIAN_SPACE_ROLES))
    )


def has_reporting_access(user):
    return bool(
        user
        and user.is_authenticated
        and (user.is_superuser or getattr(user, "role", "") in set(User.REPORTING_ROLES))
    )


def has_oversight_access(user):
    return bool(
        user
        and user.is_authenticated
        and (user.is_superuser or getattr(user, "role", "") in set(User.OVERSIGHT_ROLES))
    )


def has_backoffice_access(user):
    return bool(is_internal_user(user) or is_read_only_user(user))


def should_scope_to_agency(user):
    return bool(
        user
        and user.is_authenticated
        and getattr(user, "agency_id", None)
        and not user.is_superuser
        and getattr(user, "role", "") not in GLOBAL_AGENCY_SCOPE_ROLES
    )


def can_manage_maintenance(user):
    return bool(
        user
        and user.is_authenticated
        and (
            user.is_superuser
            or getattr(user, "role", "") in set(User.MANAGER_ROLES)
            or getattr(user, "role", "") in set(User.ESCALATION_TARGET_ROLES)
        )
    )


def maintenance_team_recipients(maintenance_ticket):
    recipients = []
    if getattr(maintenance_ticket, "technician_id", None):
        recipients.append(maintenance_ticket.technician)
    recipients.extend(list(maintenance_ticket.team_members.all()))
    return list({recipient.id: recipient for recipient in recipients if getattr(recipient, "id", None)}.values())


def can_act_on_maintenance_ticket(user, maintenance_ticket):
    if not user or not user.is_authenticated:
        return False
    if can_manage_maintenance(user):
        return True
    if maintenance_ticket.technician_id == user.id:
        return True
    return False


def role_workspace_name(user):
    if not user or not user.is_authenticated:
        return "login"
    if user.role == User.ROLE_CLIENT:
        return "support-page"
    if is_support_user(user):
        return "ticket-list"
    if user.role in set(User.TECHNICIAN_SPACE_ROLES):
        return "technician-space"
    if user.role == User.ROLE_AUDITOR:
        return "reporting-page"
    if user.role in {User.ROLE_HEAD_SAV, User.ROLE_ADMIN, User.ROLE_MANAGER}:
        return "dashboard"
    return "dashboard"


def role_default_processing_status(user):
    if not user or not user.is_authenticated:
        return Ticket.STATUS_NEW
    return Ticket.STATUS_IN_PROGRESS


def can_record_ticket_intervention(user, ticket):
    if not user or not user.is_authenticated or is_read_only_user(user):
        return False
    if is_manager_user(user):
        return True
    if getattr(user, "role", "") not in set(User.ASSIGNABLE_ROLES):
        return False
    return bool(
        ticket.assigned_agent_id == user.id
        or ticket.team_leader_id == user.id
        or ticket.team_members.filter(pk=user.pk).exists()
        or ticket.interventions.filter(agent=user).exists()
    )


def can_drive_ticket_workflow(user, ticket):
    if not can_record_ticket_intervention(user, ticket):
        return False
    if is_manager_user(user):
        return True
    if ticket.is_team_intervention:
        return bool(ticket.team_leader_id == user.id)
    return bool(ticket.assigned_agent_id == user.id)


def ticket_conversation_participant_ids(ticket):
    participant_ids = {ticket.client_id}
    if ticket.assigned_agent_id:
        participant_ids.add(ticket.assigned_agent_id)
    if ticket.team_leader_id:
        participant_ids.add(ticket.team_leader_id)
    participant_ids.update(ticket.team_members.values_list("id", flat=True))
    participant_ids.update(ticket.interventions.values_list("agent_id", flat=True))
    participant_ids.discard(None)
    return participant_ids


def can_participate_in_ticket_conversation(user, ticket):
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser or is_manager_user(user):
        return True
    if getattr(user, "role", "") == User.ROLE_CLIENT:
        return ticket.client_id == user.id
    return user.id in ticket_conversation_participant_ids(ticket)


def _apply_user_agency_scope(queryset, user):
    if not should_scope_to_agency(user):
        return queryset
    return queryset.filter(Q(agency=user.agency) | Q(sites__agency=user.agency)).distinct()


def _apply_client_site_agency_scope(queryset, user):
    if not should_scope_to_agency(user):
        return queryset
    return queryset.filter(Q(agency=user.agency) | Q(client__agency=user.agency)).distinct()


def _apply_product_agency_scope(queryset, user):
    if not should_scope_to_agency(user):
        return queryset
    return queryset.filter(Q(client__agency=user.agency) | Q(site__agency=user.agency)).distinct()


def _apply_ticket_agency_scope(queryset, user):
    if not should_scope_to_agency(user):
        return queryset
    return queryset.filter(
        Q(client__agency=user.agency)
        | Q(product__client__agency=user.agency)
        | Q(product__site__agency=user.agency)
        | Q(created_by__agency=user.agency)
        | Q(assigned_agent__agency=user.agency)
        | Q(interventions__agent__agency=user.agency)
    ).distinct()


def _apply_maintenance_agency_scope(queryset, user):
    if not should_scope_to_agency(user):
        return queryset
    return queryset.filter(
        Q(client__agency=user.agency)
        | Q(products__client__agency=user.agency)
        | Q(products__site__agency=user.agency)
        | Q(technician__agency=user.agency)
        | Q(team_members__agency=user.agency)
        | Q(responsible__agency=user.agency)
    ).distinct()


def scope_by_access(queryset, user, own_relation, organization_relation="organization"):
    if not user or not user.is_authenticated:
        return queryset.none()
    if has_backoffice_access(user):
        if user.is_superuser or not user.organization_id:
            return queryset
        return queryset.filter(**{organization_relation: user.organization})
    return queryset.filter(**{own_relation: user})


def scope_by_client_relation(queryset, user, relation):
    if not user or not user.is_authenticated:
        return queryset.none()
    if has_backoffice_access(user):
        if user.is_superuser or not user.organization_id:
            return queryset
        return queryset.filter(**{f"{relation}__organization": user.organization})
    return queryset.filter(**{relation: user})


def scope_user_queryset(queryset, user):
    if not user or not user.is_authenticated:
        return queryset.none()
    if user.is_superuser:
        return queryset
    if has_oversight_access(user):
        if user.organization_id:
            queryset = queryset.filter(organization=user.organization)
        return _apply_user_agency_scope(queryset, user)
    if getattr(user, "role", "") in set(User.INTERNAL_ROLES):
        queryset = queryset.filter(role=User.ROLE_CLIENT)
        if user.organization_id:
            queryset = queryset.filter(organization=user.organization)
        return _apply_user_agency_scope(queryset, user)
    return queryset.filter(id=user.id)


def scope_agency_queryset(queryset, user):
    if not user or not user.is_authenticated:
        return queryset.none()
    if user.is_superuser or not user.organization_id:
        return queryset
    queryset = queryset.filter(organization=user.organization)
    if should_scope_to_agency(user):
        queryset = queryset.filter(id=user.agency_id)
    return queryset


def scope_ticket_queryset(queryset, user):
    if not user or not user.is_authenticated:
        return queryset.none()
    if user.is_superuser:
        return queryset
    if has_backoffice_access(user):
        if user.organization_id:
            queryset = queryset.filter(
                Q(organization=user.organization)
                | Q(client__organization=user.organization)
                | Q(product__organization=user.organization)
            ).distinct()
        queryset = _apply_ticket_agency_scope(queryset, user)
        if is_admin_user(user) or getattr(user, "role", "") == User.ROLE_HEAD_SAV:
            return queryset
        queryset = queryset.exclude(status=Ticket.STATUS_PENDING_ASSIGNMENT)
        if is_support_user(user):
            return queryset.filter(
                Q(created_by=user)
                | Q(assigned_agent=user)
                | Q(team_leader=user)
                | Q(team_members=user)
                | Q(assigned_agent__isnull=True)
                | Q(interventions__agent=user)
            ).distinct()
        if getattr(user, "role", "") in set(User.ASSIGNABLE_ROLES):
            return queryset.filter(
                Q(assigned_agent=user) | Q(team_leader=user) | Q(team_members=user) | Q(interventions__agent=user)
            ).distinct()
        return queryset.filter(
            Q(created_by=user) | Q(assigned_agent=user) | Q(team_leader=user) | Q(team_members=user) | Q(interventions__agent=user)
        ).distinct()
    return queryset.filter(client=user)


def scope_product_queryset(queryset, user):
    if not user or not user.is_authenticated:
        return queryset.none()
    if has_backoffice_access(user):
        if user.is_superuser or not user.organization_id:
            return queryset
        queryset = queryset.filter(Q(organization=user.organization) | Q(client__organization=user.organization)).distinct()
        return _apply_product_agency_scope(queryset, user)
    return queryset.filter(client=user)


def scope_equipment_category_queryset(queryset, user):
    if not user or not user.is_authenticated:
        return queryset.none()
    if user.is_superuser or not user.organization_id:
        return queryset
    return queryset.filter(Q(organization=user.organization) | Q(organization__isnull=True))


def _scope_ticket_related_queryset(queryset, user, ticket_relation):
    if not user or not user.is_authenticated:
        return queryset.none()
    visible_tickets = scope_ticket_queryset(Ticket.objects.all(), user)
    return queryset.filter(**{f"{ticket_relation}__in": visible_tickets})


def scope_message_queryset(queryset, user):
    queryset = _scope_ticket_related_queryset(queryset, user, "ticket")
    if not user or not user.is_authenticated:
        return queryset.none()
    if not user.is_superuser and not is_manager_user(user):
        if getattr(user, "role", "") == User.ROLE_CLIENT:
            queryset = queryset.filter(ticket__client=user)
        else:
            queryset = queryset.filter(
                Q(ticket__assigned_agent=user)
                | Q(ticket__team_leader=user)
                | Q(ticket__team_members=user)
                | Q(ticket__interventions__agent=user)
            ).distinct()
    if getattr(user, "role", "") == User.ROLE_CLIENT:
        queryset = queryset.filter(Q(recipient__isnull=True) | Q(recipient=user) | Q(sender=user))
        queryset = queryset.exclude(message_type=Message.TYPE_INTERNAL)
    return queryset


def scope_attachment_queryset(queryset, user):
    return _scope_ticket_related_queryset(queryset, user, "ticket")


def scope_intervention_queryset(queryset, user):
    return _scope_ticket_related_queryset(queryset, user, "ticket")


def scope_intervention_media_queryset(queryset, user):
    return _scope_ticket_related_queryset(queryset, user, "intervention__ticket")


def scope_ticket_assignment_queryset(queryset, user):
    return _scope_ticket_related_queryset(queryset, user, "ticket")


def scope_client_contact_queryset(queryset, user):
    queryset = scope_by_access(queryset, user, "client", "organization")
    if should_scope_to_agency(user):
        return queryset.filter(Q(client__agency=user.agency) | Q(client__sites__agency=user.agency)).distinct()
    return queryset


def scope_client_site_queryset(queryset, user):
    queryset = scope_by_access(queryset, user, "client", "organization")
    return _apply_client_site_agency_scope(queryset, user)


def scope_spare_part_queryset(queryset, user):
    if not user or not user.is_authenticated:
        return queryset.none()
    if user.is_superuser or not user.organization_id:
        return queryset
    return queryset.filter(Q(organization=user.organization) | Q(organization__isnull=True))


def scope_equipment_location_history_queryset(queryset, user):
    return scope_by_access(queryset, user, "product__client", "organization")


def scope_intervention_part_usage_queryset(queryset, user):
    return _scope_ticket_related_queryset(queryset, user, "intervention__ticket")


def scope_maintenance_part_usage_queryset(queryset, user):
    from ..models import MaintenanceReport
    visible_reports = scope_maintenance_report_queryset(MaintenanceReport.objects.all(), user)
    return queryset.filter(report__in=visible_reports)


def scope_support_session_queryset(queryset, user):
    return _scope_ticket_related_queryset(queryset, user, "ticket")


def scope_predictive_alert_queryset(queryset, user):
    return scope_by_access(queryset, user, "product__client", "product__organization")


def scope_notification_queryset(queryset, user):
    if not user or not user.is_authenticated:
        return queryset.none()
    return queryset.filter(recipient=user)


def scope_knowledge_article_queryset(queryset, user):
    if not user or not user.is_authenticated:
        return queryset.none()
    if has_backoffice_access(user):
        if user.is_superuser or not user.organization_id:
            return queryset
        return queryset.filter(Q(organization=user.organization) | Q(organization__isnull=True))
    return queryset.filter(
        status=KnowledgeArticle.STATUS_PUBLISHED,
        audience=KnowledgeArticle.AUDIENCE_PUBLIC,
    ).filter(Q(organization=user.organization) | Q(organization__isnull=True))


def scope_offer_queryset(queryset, user):
    return scope_by_access(queryset, user, "client", "organization")


def scope_account_credit_queryset(queryset, user):
    if not is_admin_user(user):
        return queryset.none()
    return scope_by_access(queryset, user, "client", "organization")


def scope_financial_transaction_queryset(queryset, user):
    return scope_by_access(queryset, user, "client", "organization")


def scope_ticket_feedback_queryset(queryset, user):
    queryset = scope_by_access(queryset, user, "ticket__client", "organization")
    if should_scope_to_agency(user):
        return queryset.filter(Q(ticket__client__agency=user.agency) | Q(ticket__product__site__agency=user.agency)).distinct()
    return queryset


def scope_offline_sync_operation_queryset(queryset, user):
    if not user or not user.is_authenticated:
        return queryset.none()
    if user.is_superuser:
        return queryset
    if has_backoffice_access(user):
        if user.organization_id:
            return queryset.filter(organization=user.organization)
        return queryset
    return queryset.filter(user=user)


def scope_ai_action_queryset(queryset, user):
    return scope_by_access(queryset, user, "ticket__client", "organization")


def scope_automation_rule_queryset(queryset, user):
    if not user or not user.is_authenticated:
        return queryset.none()
    if user.is_superuser or not user.organization_id:
        return queryset
    return queryset.filter(Q(organization=user.organization) | Q(organization__isnull=True))


def scope_sla_rule_queryset(queryset, user):
    if not user or not user.is_authenticated:
        return queryset.none()
    if user.is_superuser or not user.organization_id:
        return queryset
    return queryset.filter(Q(organization=user.organization) | Q(organization__isnull=True))


def scope_workflow_execution_queryset(queryset, user):
    return scope_by_access(queryset, user, "ticket__client", "organization")


def scope_maintenance_program_queryset(queryset, user):
    if not user or not user.is_authenticated:
        return queryset.none()
    if user.is_superuser:
        return queryset
    if can_manage_maintenance(user) or is_read_only_user(user):
        if user.organization_id:
            queryset = queryset.filter(organization=user.organization)
        if should_scope_to_agency(user):
            queryset = queryset.filter(
                Q(responsible__agency=user.agency)
                | Q(tickets__client__agency=user.agency)
                | Q(tickets__products__site__agency=user.agency)
                | Q(tickets__technician__agency=user.agency)
                | Q(tickets__team_members__agency=user.agency)
            ).distinct()
        return queryset
    if getattr(user, "role", "") in set(User.TECHNICIAN_SPACE_ROLES) | {User.ROLE_FIELD_TECHNICIAN, User.ROLE_EXPERT}:
        if user.organization_id:
            return queryset.filter(organization=user.organization)
        return queryset
    return queryset.none()


def scope_maintenance_ticket_queryset(queryset, user):
    if not user or not user.is_authenticated:
        return queryset.none()
    if user.is_superuser:
        return queryset
    if can_manage_maintenance(user) or is_read_only_user(user):
        if user.organization_id:
            queryset = queryset.filter(
                Q(organization=user.organization)
                | Q(client__organization=user.organization)
                | Q(technician__organization=user.organization)
                | Q(team_members__organization=user.organization)
            ).distinct()
        return _apply_maintenance_agency_scope(queryset, user)
    if getattr(user, "role", "") in set(User.TECHNICIAN_SPACE_ROLES) | {User.ROLE_FIELD_TECHNICIAN, User.ROLE_EXPERT}:
        if user.organization_id:
            return queryset.filter(
                Q(organization=user.organization)
                | Q(client__organization=user.organization)
                | Q(technician__organization=user.organization)
            ).distinct()
        return queryset
    if getattr(user, "role", "") == User.ROLE_CLIENT:
        return queryset.filter(client=user)
    return queryset.none()


def scope_maintenance_report_queryset(queryset, user):
    visible_tickets = scope_maintenance_ticket_queryset(MaintenanceTicket.objects.all(), user)
    return queryset.filter(maintenance_ticket__in=visible_tickets)


def scope_checklist_template_queryset(queryset, user):
    if not user or not user.is_authenticated:
        return queryset.none()
    if user.is_superuser or not user.organization_id:
        return queryset
    return queryset.filter(Q(organization=user.organization) | Q(organization__isnull=True))


def scope_generated_report_queryset(queryset, user):
    if not user or not user.is_authenticated:
        return queryset.none()
    if not has_backoffice_access(user) and not user.is_superuser:
        return queryset.none()
    if user.is_superuser or not user.organization_id:
        return queryset
    return queryset.filter(organization=user.organization)


def scope_audit_log_queryset(queryset, user):
    if not user or not user.is_authenticated:
        return queryset.none()
    if user.is_superuser or not user.organization_id:
        return queryset
    return queryset.filter(organization=user.organization)
