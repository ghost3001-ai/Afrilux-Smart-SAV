from rest_framework import serializers

from ..file_validation import validate_ticket_attachment_file
from ..models import (
    Message,
    Ticket,
    TicketAttachment,
    TicketFeedback,
    User,
)
from .interventions import InterventionInlineSerializer
from .support import SupportSessionInlineSerializer
from ..services import (
    ESCALATION_TARGET_CFAO_MANAGER,
    ESCALATION_TARGET_CFAO_WORKS,
    ESCALATION_TARGET_CHIEF_TECHNICIAN,
    ESCALATION_TARGET_EXPERT_THEN_HEAD_SAV,
    ESCALATION_TARGET_HEAD_SAV,
    ESCALATION_TARGET_SUPERVISOR,
    is_admin_user,
    scope_message_queryset,
)
from .financial import AccountCreditInlineSerializer
from .reporting import TicketAssignmentSerializer


class MessageInlineSerializer(serializers.ModelSerializer):
    sender_name = serializers.SerializerMethodField()
    recipient_name = serializers.SerializerMethodField()

    class Meta:
        model = Message
        fields = [
            "id",
            "sender",
            "sender_name",
            "recipient",
            "recipient_name",
            "message_type",
            "channel",
            "direction",
            "content",
            "sentiment_score",
            "ai_summary",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "sender",
            "sender_name",
            "recipient_name",
            "sentiment_score",
            "ai_summary",
            "created_at",
        ]

    def get_sender_name(self, obj):
        return str(obj.sender)

    def get_recipient_name(self, obj):
        if not obj.recipient:
            return None
        return str(obj.recipient)


class MessageSerializer(MessageInlineSerializer):
    class Meta(MessageInlineSerializer.Meta):
        fields = ["ticket", *MessageInlineSerializer.Meta.fields]


class TicketAttachmentSerializer(serializers.ModelSerializer):
    uploaded_by_name = serializers.SerializerMethodField()
    ticket_reference = serializers.CharField(source="ticket.reference", read_only=True)
    organization_name = serializers.CharField(source="organization.display_name", read_only=True)
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = TicketAttachment
        fields = [
            "id",
            "organization",
            "organization_name",
            "ticket",
            "ticket_reference",
            "uploaded_by",
            "uploaded_by_name",
            "kind",
            "file",
            "file_url",
            "original_name",
            "content_type",
            "size_bytes",
            "note",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "organization",
            "organization_name",
            "ticket_reference",
            "uploaded_by",
            "uploaded_by_name",
            "original_name",
            "content_type",
            "size_bytes",
            "created_at",
            "updated_at",
            "file_url",
        ]

    def get_uploaded_by_name(self, obj):
        if not obj.uploaded_by:
            return "Systeme"
        return str(obj.uploaded_by)

    def get_file_url(self, obj):
        if not obj.file:
            return ""
        request = self.context.get("request")
        if request:
            return request.build_absolute_uri(obj.file.url)
        return obj.file.url

    def validate_file(self, value):
        try:
            return validate_ticket_attachment_file(value)
        except Exception as exc:
            raise serializers.ValidationError(str(exc)) from exc

    def validate(self, attrs):
        attrs = super().validate(attrs)
        ticket = attrs.get("ticket") or getattr(self.instance, "ticket", None)
        organization = attrs.get("organization") or getattr(self.instance, "organization", None)
        if ticket and organization and ticket.organization_id and organization.id != ticket.organization_id:
            raise serializers.ValidationError("La piece jointe doit appartenir a l'organisation du ticket.")
        return attrs


class TicketFeedbackSerializer(serializers.ModelSerializer):
    ticket_reference = serializers.CharField(source="ticket.reference", read_only=True)
    client_name = serializers.SerializerMethodField()
    organization_name = serializers.CharField(source="organization.display_name", read_only=True)

    class Meta:
        model = TicketFeedback
        fields = [
            "id",
            "organization",
            "organization_name",
            "ticket",
            "ticket_reference",
            "client",
            "client_name",
            "rating",
            "comment",
            "submitted_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "organization",
            "organization_name",
            "ticket_reference",
            "client",
            "client_name",
            "submitted_at",
            "created_at",
            "updated_at",
        ]

    def get_client_name(self, obj):
        return str(obj.client)

    def validate_rating(self, value):
        if value < 1 or value > 5:
            raise serializers.ValidationError("La note doit etre comprise entre 1 et 5.")
        return value


class TicketSerializer(serializers.ModelSerializer):
    channel = serializers.ChoiceField(
        choices=[
            (Ticket.CHANNEL_PHONE, "Téléphone"),
            (Ticket.CHANNEL_EMAIL, "Email"),
            (Ticket.CHANNEL_WHATSAPP, "WhatsApp"),
            (Ticket.CHANNEL_WEB, "Portail Web"),
        ],
        required=False,
        default=Ticket.CHANNEL_WEB,
    )
    client = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.filter(role=User.ROLE_CLIENT, is_active=True),
        required=False,
    )
    client_name = serializers.SerializerMethodField()
    assigned_agent_name = serializers.SerializerMethodField()
    team_leader_name = serializers.SerializerMethodField()
    team_member_names = serializers.SerializerMethodField()
    organization_name = serializers.CharField(source="organization.display_name", read_only=True)
    product_name = serializers.CharField(source="product_display_name", read_only=True)
    public_status = serializers.CharField(read_only=True)
    is_overdue = serializers.BooleanField(read_only=True)
    messages = serializers.SerializerMethodField()
    attachments = TicketAttachmentSerializer(many=True, read_only=True)
    interventions = InterventionInlineSerializer(many=True, read_only=True)
    support_sessions = SupportSessionInlineSerializer(many=True, read_only=True)
    account_credits = serializers.SerializerMethodField()
    assignment_history = TicketAssignmentSerializer(many=True, read_only=True)
    feedback = TicketFeedbackSerializer(read_only=True)
    initial_escalation_target = serializers.ChoiceField(
        choices=[
            (ESCALATION_TARGET_CFAO_MANAGER, "responsable CFAO"),
            (ESCALATION_TARGET_CFAO_WORKS, "conducteur de travaux CFAO"),
            (ESCALATION_TARGET_CHIEF_TECHNICIAN, "chef technicien froid & climatisation"),
            (ESCALATION_TARGET_SUPERVISOR, "superviseur"),
            (ESCALATION_TARGET_EXPERT_THEN_HEAD_SAV, "expert puis Responsable SAV"),
            (ESCALATION_TARGET_HEAD_SAV, "Responsable SAV"),
        ],
        required=False,
        allow_blank=True,
        write_only=True,
    )

    class Meta:
        model = Ticket
        fields = [
            "id",
            "reference",
            "organization",
            "organization_name",
            "client",
            "client_name",
            "product_label",
            "product",
            "product_name",
            "assigned_agent",
            "assigned_agent_name",
            "team_leader",
            "team_leader_name",
            "team_members",
            "team_member_names",
            "is_team_intervention",
            "initial_escalation_target",
            "title",
            "description",
            "business_domain",
            "category",
            "channel",
            "status",
            "public_status",
            "priority",
            "location",
            "sla_deadline",
            "escalation_count",
            "last_escalation_at",
            "last_escalation_reason",
            "status_before_escalation",
            "first_response_at",
            "resolved_at",
            "closed_at",
            "resolution_summary",
            "is_overdue",
            "messages",
            "attachments",
            "interventions",
            "support_sessions",
            "account_credits",
            "assignment_history",
            "feedback",
            "created_at",
            "updated_at",
        ]

    def get_client_name(self, obj):
        return str(obj.client)

    def get_assigned_agent_name(self, obj):
        if not obj.assigned_agent:
            return None
        return str(obj.assigned_agent)

    def get_team_leader_name(self, obj):
        if not obj.team_leader:
            return None
        return str(obj.team_leader)

    def get_team_member_names(self, obj):
        return [str(member) for member in obj.team_members.all()]

    def get_messages(self, obj):
        request = self.context.get("request")
        user = getattr(request, "user", None)
        queryset = scope_message_queryset(obj.messages.all(), user) if user and user.is_authenticated else obj.messages.none()
        return MessageInlineSerializer(queryset, many=True, context=self.context).data

    def get_account_credits(self, obj):
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if not is_admin_user(user):
            return []
        return AccountCreditInlineSerializer(obj.account_credits.all(), many=True, context=self.context).data

    def validate(self, attrs):
        attrs = super().validate(attrs)
        blocked_categories = {
            Ticket.CATEGORY_RETURN,
            Ticket.CATEGORY_REFUND,
            Ticket.CATEGORY_WITHDRAWAL,
            Ticket.CATEGORY_COMPLAINT,
            Ticket.CATEGORY_PAYMENT,
            Ticket.CATEGORY_ACCOUNT,
        }
        if attrs.get("category") in blocked_categories:
            raise serializers.ValidationError(
                {"category": "Cette categorie n'est plus autorisee pour la creation ou la mise a jour des tickets."}
            )
        client = attrs.get("client") or getattr(self.instance, "client", None)
        product = attrs.get("product") or getattr(self.instance, "product", None)
        assigned_agent = attrs.get("assigned_agent") or getattr(self.instance, "assigned_agent", None)
        organization = attrs.get("organization") or getattr(self.instance, "organization", None)
        if self.instance is not None and "status" in attrs:
            next_status = Ticket.normalize_process_status(attrs["status"])
            if not Ticket.can_transition(self.instance.status, next_status):
                raise serializers.ValidationError(
                    {"status": "Transition non autorisee par le cycle de vie du cahier des charges."}
                )
            attrs["status"] = next_status

        if client and product and product.client_id != client.id:
            raise serializers.ValidationError("Le produit selectionne n'appartient pas a ce client.")
        if client and organization and client.organization_id != organization.id:
            raise serializers.ValidationError("Le client selectionne n'appartient pas a cette organisation.")
        if assigned_agent and client and assigned_agent.organization_id and client.organization_id and assigned_agent.organization_id != client.organization_id:
            raise serializers.ValidationError("L'agent selectionne appartient a une autre organisation.")
        previous_assigned_agent = getattr(self.instance, "assigned_agent", None)
        if (
            assigned_agent
            and not assigned_agent.is_ticket_assignment_eligible
            and (not previous_assigned_agent or previous_assigned_agent.id != assigned_agent.id)
        ):
            raise serializers.ValidationError(
                {"assigned_agent": "Affectation autorisee uniquement aux responsables d'escalade ou techniciens disponibles."}
            )
        request = self.context.get("request")
        user = getattr(request, "user", None)
        initial_target = (attrs.get("initial_escalation_target") or "").strip()
        if initial_target:
            if not user or not user.is_authenticated or user.role != User.ROLE_HEAD_SAV:
                raise serializers.ValidationError(
                    {"initial_escalation_target": "Seul le Responsable SAV peut escalader un ticket a la creation."}
                )
            if assigned_agent:
                raise serializers.ValidationError(
                    {"initial_escalation_target": "Choisissez soit une affectation directe, soit une escalade initiale."}
                )
        return attrs
