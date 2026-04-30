from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.utils import timezone

from .models import EquipmentCategory, Intervention, InterventionMedia, Message, Organization, Product, Ticket, TicketAttachment, User
from .services import (
    ESCALATION_TARGET_CFAO_MANAGER,
    ESCALATION_TARGET_CFAO_WORKS,
    ESCALATION_TARGET_EXPERT_THEN_HEAD_SAV,
    ESCALATION_TARGET_HEAD_SAV,
    ESCALATION_TARGET_SUPERVISOR,
    compute_ticket_sla_deadline,
    provision_client_account,
)

MAX_TICKET_ATTACHMENT_BYTES = 10 * 1024 * 1024


def _split_full_name(value):
    normalized = " ".join((value or "").split())
    if not normalized:
        return "", ""
    first_name, *rest = normalized.split(" ", 1)
    return first_name, rest[0] if rest else ""


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    widget = MultipleFileInput

    def clean(self, data, initial=None):
        single_clean = super().clean
        if not data:
            return []
        if isinstance(data, (list, tuple)):
            return [single_clean(item, initial) for item in data]
        return [single_clean(data, initial)]


class SavAuthenticationForm(AuthenticationForm):
    username = forms.CharField(
        label="Email ou identifiant",
        widget=forms.TextInput(attrs={"autofocus": True, "placeholder": "Email ou nom d'utilisateur"}),
    )
    password = forms.CharField(widget=forms.PasswordInput(attrs={"placeholder": "Mot de passe"}))


class ClientRegistrationForm(forms.Form):
    organization = forms.ModelChoiceField(queryset=Organization.objects.filter(is_active=True).order_by("name"), label="Organisation")
    first_name = forms.CharField(label="Prenom", max_length=150)
    last_name = forms.CharField(label="Nom", max_length=150, required=False)
    email = forms.EmailField(label="Email")
    phone = forms.CharField(label="Telephone", max_length=20, required=False)
    company_name = forms.CharField(label="Entreprise", max_length=255, required=False)
    client_type = forms.ChoiceField(label="Type de client", choices=User._meta.get_field("client_type").choices, required=False)
    sector = forms.CharField(label="Secteur d'activite", max_length=120, required=False)
    tax_identifier = forms.CharField(label="NINEA / RC", max_length=120, required=False)
    address = forms.CharField(label="Adresse complete", required=False, widget=forms.Textarea(attrs={"rows": 3}))
    password1 = forms.CharField(label="Mot de passe", widget=forms.PasswordInput())
    password2 = forms.CharField(label="Confirmation", widget=forms.PasswordInput())

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.data:
            self.fields["client_type"].initial = "individual"

    def clean_email(self):
        return self.cleaned_data["email"].strip().lower()

    def clean(self):
        cleaned_data = super().clean()
        password1 = cleaned_data.get("password1", "")
        password2 = cleaned_data.get("password2", "")
        if password1 and password2 and password1 != password2:
            self.add_error("password2", "Les mots de passe ne correspondent pas.")
        if password1:
            try:
                validate_password(password1)
            except ValidationError as exc:
                self.add_error("password1", exc)
        client_type = (cleaned_data.get("client_type") or "").strip().lower()
        company_name = (cleaned_data.get("company_name") or "").strip()
        if client_type == "enterprise" and not company_name:
            self.add_error("company_name", "Le champ Entreprise est obligatoire pour un client de type Entreprise.")
        if client_type and client_type != "enterprise":
            cleaned_data["company_name"] = ""
        return cleaned_data

    def save(self):
        if not self.is_valid():
            raise ValueError("Le formulaire d'inscription n'est pas valide.")
        user, _ = provision_client_account(
            organization=self.cleaned_data["organization"],
            email=self.cleaned_data["email"],
            password=self.cleaned_data["password1"],
            first_name=self.cleaned_data["first_name"],
            last_name=self.cleaned_data.get("last_name", ""),
            phone=self.cleaned_data.get("phone", ""),
            company_name=self.cleaned_data.get("company_name", ""),
            client_type=self.cleaned_data.get("client_type", ""),
            sector=self.cleaned_data.get("sector", ""),
            tax_identifier=self.cleaned_data.get("tax_identifier", ""),
            address=self.cleaned_data.get("address", ""),
        )
        return user


class TicketForm(forms.ModelForm):
    class Meta:
        model = Ticket
        fields = [
            "client",
            "product_label",
            "product",
            "assigned_agent",
            "title",
            "description",
            "business_domain",
            "category",
            "channel",
            "status",
            "priority",
            "location",
            "sla_deadline",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 5}),
            "sla_deadline": forms.DateTimeInput(attrs={"type": "datetime-local"}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.fields["business_domain"].required = False
        self.fields["business_domain"].initial = self.instance.business_domain or Ticket.DOMAIN_OTHER
        self.fields["product_label"].required = False
        self.fields["product_label"].label = "Produit / equipement concerne"
        self.fields["product_label"].help_text = "Saisissez librement le produit, le modele ou l'equipement signale."
        if self.instance.pk and not self.initial.get("product_label") and self.instance.product_display_name:
            self.initial["product_label"] = self.instance.product_display_name
        self.fields["product"].required = False
        self.fields["product"].widget = forms.HiddenInput()
        client_queryset = User.objects.filter(role=User.ROLE_CLIENT)
        agent_queryset = User.objects.filter(is_active=True).filter(
            Q(role__in=User.SUPPORT_ROLE_ALIASES)
            | Q(role=User.ROLE_TECHNICIAN, technician_status="available")
        )
        if user and user.is_authenticated and not user.is_superuser and user.organization_id:
            client_queryset = client_queryset.filter(organization=user.organization)
            agent_queryset = agent_queryset.filter(organization=user.organization)
        if self.instance.pk and self.instance.assigned_agent_id:
            agent_queryset = (agent_queryset | User.objects.filter(pk=self.instance.assigned_agent_id)).distinct()
        self.fields["client"].queryset = client_queryset.order_by("company_name", "first_name", "last_name", "username")
        self.fields["assigned_agent"].queryset = agent_queryset.order_by("first_name", "last_name", "username")
        self.fields["assigned_agent"].help_text = "Affectation autorisee uniquement aux agents et techniciens disponibles."
        self.fields["category"].choices = [
            choice
            for choice in self.fields["category"].choices
            if choice[0] in {Ticket.CATEGORY_BREAKDOWN, Ticket.CATEGORY_INSTALLATION, Ticket.CATEGORY_MAINTENANCE, Ticket.CATEGORY_BUG}
        ]
        if not self.instance.pk and not self.initial.get("sla_deadline"):
            base_priority = self.initial.get("priority") or self.fields["priority"].initial or Ticket.PRIORITY_NORMAL
            org = getattr(user, "organization", None) if user and user.is_authenticated else None
            default_deadline = compute_ticket_sla_deadline(base_priority, base_time=timezone.now(), organization=org)
            self.initial["sla_deadline"] = timezone.localtime(default_deadline).replace(second=0, microsecond=0)

        if user and user.is_authenticated and user.role == User.ROLE_CLIENT:
            self.fields["client"].queryset = client_queryset.filter(pk=user.pk)
            self.fields["client"].initial = user
            self.fields["client"].required = False
            self.fields["client"].empty_label = None
            self.fields["client"].help_text = "Votre compte client est preselectionne pour ce ticket."
            self.fields["assigned_agent"].widget = forms.HiddenInput()
            self.fields["assigned_agent"].required = False
            self.fields["status"].initial = Ticket.STATUS_NEW
            self.fields["status"].widget = forms.HiddenInput()
            self.fields["status"].required = False
            self.fields["priority"].initial = Ticket.PRIORITY_NORMAL
            self.fields["priority"].widget = forms.HiddenInput()
            self.fields["priority"].required = False
            self.fields["product"].queryset = Product.objects.filter(client=user).order_by("name")
        else:
            product_queryset = Product.objects.select_related("client")
            if user and user.is_authenticated and not user.is_superuser and user.organization_id:
                product_queryset = product_queryset.filter(organization=user.organization)
            self.fields["product"].queryset = product_queryset.order_by("name")

    def clean(self):
        cleaned_data = super().clean()
        client = cleaned_data.get("client")
        product = cleaned_data.get("product")
        assigned_agent = cleaned_data.get("assigned_agent")
        cleaned_data["business_domain"] = cleaned_data.get("business_domain") or Ticket.DOMAIN_OTHER
        if self.user and self.user.is_authenticated and self.user.role == User.ROLE_CLIENT:
            cleaned_data["client"] = self.user
            cleaned_data["assigned_agent"] = None
            cleaned_data["status"] = Ticket.STATUS_NEW
            cleaned_data["priority"] = Ticket.PRIORITY_NORMAL
            client = self.user
        if client and product and product.client_id != client.id:
            self.add_error("product", "Le produit selectionne n'appartient pas a ce client.")
        previous_assigned_agent = getattr(self.instance, "assigned_agent", None)
        if (
            assigned_agent
            and not assigned_agent.is_ticket_assignment_eligible
            and (not previous_assigned_agent or previous_assigned_agent.id != assigned_agent.id)
        ):
            self.add_error("assigned_agent", "Affectation autorisee uniquement aux agents et techniciens disponibles.")
        return cleaned_data


class TicketCreateForm(TicketForm):
    CLIENT_MODE_EXISTING = "existing"
    CLIENT_MODE_NEW = "new"
    CLIENT_MODE_CHOICES = (
        (CLIENT_MODE_EXISTING, "Client existant"),
        (CLIENT_MODE_NEW, "Nouveau client"),
    )

    client_mode = forms.ChoiceField(
        required=False,
        label="Mode client",
        choices=CLIENT_MODE_CHOICES,
        initial=CLIENT_MODE_EXISTING,
    )
    existing_client_email = forms.CharField(
        required=False,
        label="Client existant",
        max_length=255,
        widget=forms.TextInput(attrs={"placeholder": "Nom, entreprise, email ou telephone"}),
    )
    client_name = forms.CharField(
        required=False,
        label="Nom du client",
        widget=forms.TextInput(attrs={"placeholder": "Ex: Marie Nlend"}),
    )
    client_email = forms.EmailField(
        required=False,
        label="Email client",
        widget=forms.EmailInput(attrs={"placeholder": "client@example.com"}),
    )
    client_password1 = forms.CharField(
        required=False,
        label="Mot de passe client",
        widget=forms.PasswordInput(attrs={"placeholder": "Mot de passe initial"}),
    )
    client_password2 = forms.CharField(
        required=False,
        label="Confirmation mot de passe",
        widget=forms.PasswordInput(attrs={"placeholder": "Confirmer le mot de passe"}),
    )
    initial_attachments = MultipleFileField(
        required=False,
        label="Preuves / captures / recus",
        help_text="Optionnel: ajoutez des pieces jointes des la creation du dossier.",
        widget=MultipleFileInput(attrs={"accept": "image/*,.pdf,.txt"}),
    )

    class Meta(TicketForm.Meta):
        fields = [*TicketForm.Meta.fields, "initial_attachments"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self._uses_inline_client_creation():
            self.fields["client"].required = False
            self.fields["client"].widget = forms.HiddenInput()
            self.fields["client_mode"].help_text = "Choisissez un client existant par recherche ou creez-en un nouveau."
            self.fields["existing_client_email"].help_text = "Recherchez par nom, entreprise, email, telephone ou identifiant."
            self.fields["client_name"].help_text = "Le compte client sera cree automatiquement a la validation du ticket."
            self.fields["client_email"].help_text = "Cet email servira d'identifiant de connexion du client."
            self.fields["client_password1"].help_text = "Definissez le mot de passe initial du compte client."
        else:
            for field_name in ["client_mode", "existing_client_email", "client_name", "client_email", "client_password1", "client_password2"]:
                self.fields[field_name].widget = forms.HiddenInput()
                self.fields[field_name].required = False

    def _uses_inline_client_creation(self):
        return bool(
            self.user
            and self.user.is_authenticated
            and (self.user.is_superuser or self.user.role in set(User.SUPPORT_ROLE_ALIASES))
        )

    def _inline_client_organization(self):
        return getattr(self.user, "organization", None)

    def _selected_client_mode(self, cleaned_data=None):
        source = cleaned_data if cleaned_data is not None else self.cleaned_data
        mode = (source.get("client_mode") or self.CLIENT_MODE_EXISTING).strip().lower()
        if mode not in {self.CLIENT_MODE_EXISTING, self.CLIENT_MODE_NEW}:
            return ""
        return mode

    def _lookup_existing_client(self, search_value):
        normalized_search = (search_value or "").strip()
        normalized_email = normalized_search.lower()
        organization = self._inline_client_organization()
        queryset = User.objects.filter(role=User.ROLE_CLIENT)
        if organization is not None:
            queryset = queryset.filter(Q(organization=organization) | Q(organization__slug="contacts-entrants"))
        existing = (
            queryset.filter(
                Q(email__iexact=normalized_email)
                | Q(username__icontains=normalized_search)
                | Q(first_name__icontains=normalized_search)
                | Q(last_name__icontains=normalized_search)
                | Q(company_name__icontains=normalized_search)
                | Q(phone__icontains=normalized_search)
            )
            .order_by("company_name", "first_name", "last_name", "username", "id")
            .first()
        )

        if not existing:
            raise ValidationError("Aucun client existant ne correspond a cette recherche. Choisissez 'Nouveau client' pour le creer.")
        if existing.role != User.ROLE_CLIENT:
            raise ValidationError("Cette recherche correspond a un compte interne.")
        if existing.organization_id and organization and existing.organization_id != organization.id:
            if existing.organization.slug != "contacts-entrants":
                raise ValidationError("Cet email est deja rattache a une autre organisation.")

        return existing

    def clean_existing_client_email(self):
        return (self.cleaned_data.get("existing_client_email") or "").strip().lower()

    def clean_client_email(self):
        return (self.cleaned_data.get("client_email") or "").strip().lower()

    def clean(self):
        cleaned_data = super().clean()
        if not self._uses_inline_client_creation():
            return cleaned_data

        mode = self._selected_client_mode(cleaned_data)
        if not mode:
            self.add_error("client_mode", "Choisissez un mode client valide.")
            return cleaned_data

        cleaned_data["client"] = None
        cleaned_data["product"] = None

        if mode == self.CLIENT_MODE_EXISTING:
            existing_client_email = (cleaned_data.get("existing_client_email") or "").strip().lower()
            if not existing_client_email:
                self.add_error("existing_client_email", "La recherche du client existant est obligatoire.")
            else:
                try:
                    cleaned_data["client"] = self._lookup_existing_client(existing_client_email)
                except ValidationError as exc:
                    self.add_error("existing_client_email", exc)

            cleaned_data["client_name"] = ""
            cleaned_data["client_email"] = ""
            cleaned_data["client_password1"] = ""
            cleaned_data["client_password2"] = ""
            return cleaned_data

        client_name = (cleaned_data.get("client_name") or "").strip()
        client_email = (cleaned_data.get("client_email") or "").strip().lower()
        password1 = cleaned_data.get("client_password1", "")
        password2 = cleaned_data.get("client_password2", "")
        organization = self._inline_client_organization()

        if not client_name:
            self.add_error("client_name", "Le nom du client est obligatoire.")
        if not client_email:
            self.add_error("client_email", "L'email du client est obligatoire.")
        if not password1:
            self.add_error("client_password1", "Le mot de passe client est obligatoire.")
        if not password2:
            self.add_error("client_password2", "Confirmez le mot de passe client.")
        if password1 and password2 and password1 != password2:
            self.add_error("client_password2", "Les mots de passe ne correspondent pas.")
        if password1:
            try:
                validate_password(password1)
            except ValidationError as exc:
                self.add_error("client_password1", exc)

        if client_email:
            existing = User.objects.filter(email__iexact=client_email).order_by("id").first()
            if existing:
                if existing.role != User.ROLE_CLIENT:
                    self.add_error("client_email", "Cet email est deja utilise par un compte interne.")
                elif existing.organization_id and organization and existing.organization_id != organization.id:
                    if existing.organization.slug != "contacts-entrants":
                        self.add_error("client_email", "Cet email est deja rattache a une autre organisation.")
                elif existing.has_usable_password():
                    self.add_error("client_email", "Un compte client existe deja avec cet email. Utilisez le mode 'Client existant'.")

        return cleaned_data

    def resolve_ticket_client(self):
        if not self._uses_inline_client_creation():
            return self.cleaned_data.get("client")
        if hasattr(self, "_inline_client_account"):
            return self._inline_client_account
        if not self.is_valid():
            raise ValueError("Le formulaire de ticket n'est pas valide.")

        if self._selected_client_mode(self.cleaned_data) == self.CLIENT_MODE_EXISTING:
            client = self.cleaned_data.get("client")
            if client is None:
                raise ValueError("Aucun client existant n'a ete trouve.")
            organization = self._inline_client_organization()
            if organization and client.organization_id != organization.id:
                client.organization = organization
                client.save(update_fields=["organization"])
            self._inline_client_account = client
            return client

        first_name, last_name = _split_full_name(self.cleaned_data.get("client_name", ""))
        client, _created = provision_client_account(
            organization=self._inline_client_organization(),
            email=self.cleaned_data["client_email"],
            password=self.cleaned_data["client_password1"],
            first_name=first_name,
            last_name=last_name,
        )
        self._inline_client_account = client
        return client

    def clean_initial_attachments(self):
        attachments = self.cleaned_data.get("initial_attachments", [])
        total_size = sum(getattr(item, "size", 0) or 0 for item in attachments)
        if total_size > MAX_TICKET_ATTACHMENT_BYTES:
            raise ValidationError("Le total des pieces jointes ne peut pas depasser 10 Mo par ticket.")
        return attachments


class MessageForm(forms.ModelForm):
    recipient = forms.ModelChoiceField(
        queryset=User.objects.none(),
        required=False,
        label="Destinataire",
        empty_label="Tous les participants autorises",
    )

    class Meta:
        model = Message
        fields = ["recipient", "message_type", "channel", "content"]
        widgets = {
            "content": forms.Textarea(attrs={"rows": 4, "placeholder": "Ajoutez un message, une note interne ou une mise a jour..."}),
        }

    def __init__(self, *args, user=None, ticket=None, **kwargs):
        super().__init__(*args, **kwargs)
        recipient_queryset = User.objects.none()
        if user and user.is_authenticated and ticket:
            participant_ids = {ticket.client_id}
            if ticket.assigned_agent_id and ticket.assigned_agent.has_support_role:
                participant_ids.add(ticket.assigned_agent_id)
            if user.organization_id:
                support_queryset = User.objects.filter(
                    organization=user.organization,
                    role__in=User.SUPPORT_ROLE_ALIASES,
                    is_active=True,
                )
            else:
                support_queryset = User.objects.filter(role__in=User.SUPPORT_ROLE_ALIASES, is_active=True)
            participant_ids.update(support_queryset.values_list("id", flat=True))
            recipient_queryset = User.objects.filter(pk__in=participant_ids).exclude(pk=user.pk).order_by(
                "first_name",
                "last_name",
                "username",
            )
        self.fields["recipient"].queryset = recipient_queryset
        if not user or user.role == User.ROLE_CLIENT:
            self.fields["message_type"].widget = forms.HiddenInput()
            self.fields["message_type"].initial = Message.TYPE_PUBLIC
            self.fields["channel"].widget = forms.HiddenInput()
            self.fields["channel"].initial = Message.CHANNEL_PORTAL
        else:
            self.fields["message_type"].help_text = "Choisissez 'Note interne' pour un commentaire reserve a l'equipe SAV."
            self.fields["channel"].help_text = "Choisissez le canal externe si cette reponse doit etre diffusee hors portail."


class TicketEscalationForm(forms.Form):
    TARGET_SUPERVISOR = ESCALATION_TARGET_SUPERVISOR
    TARGET_HEAD_SAV = ESCALATION_TARGET_HEAD_SAV
    TARGET_EXPERT_THEN_HEAD_SAV = ESCALATION_TARGET_EXPERT_THEN_HEAD_SAV
    TARGET_CFAO_MANAGER = ESCALATION_TARGET_CFAO_MANAGER
    TARGET_CFAO_WORKS = ESCALATION_TARGET_CFAO_WORKS
    TARGET_CHOICES = (
        (TARGET_SUPERVISOR, "1. Vers superviseur"),
        (TARGET_HEAD_SAV, "2. Vers responsable SAV"),
        (TARGET_EXPERT_THEN_HEAD_SAV, "3. Expert puis responsable SAV"),
        (TARGET_CFAO_MANAGER, "4. Vers responsable CFAO"),
        (TARGET_CFAO_WORKS, "5. Vers conducteur de travaux CFAO"),
    )

    target = forms.ChoiceField(
        label="Cible d'escalade",
        choices=TARGET_CHOICES,
        initial=TARGET_EXPERT_THEN_HEAD_SAV,
    )
    note = forms.CharField(
        required=False,
        label="Note d'escalade",
        widget=forms.Textarea(attrs={"rows": 2, "placeholder": "Optionnel: motif ou contexte de l'escalade."}),
    )


class TicketAttachmentForm(forms.ModelForm):
    class Meta:
        model = TicketAttachment
        fields = ["kind", "file", "note"]
        widgets = {
            "note": forms.TextInput(attrs={"placeholder": "Ex: capture du message d'erreur, recu client..."}),
        }

    def clean_file(self):
        uploaded = self.cleaned_data["file"]
        if getattr(uploaded, "size", 0) > MAX_TICKET_ATTACHMENT_BYTES:
            raise ValidationError("La piece jointe ne peut pas depasser 10 Mo.")
        return uploaded


class InterventionForm(forms.ModelForm):
    intervention_media = MultipleFileField(
        required=False,
        label="Photos intervention",
        help_text="Ajoutez jusqu'a 5 photos avant, pendant ou apres intervention.",
        widget=MultipleFileInput(attrs={"accept": "image/*,.pdf"}),
    )

    class Meta:
        model = Intervention
        fields = [
            "agent",
            "intervention_type",
            "status",
            "scheduled_for",
            "started_at",
            "finished_at",
            "diagnosis",
            "action_taken",
            "parts_used",
            "structured_parts_used",
            "time_spent_minutes",
            "technical_report",
            "location_snapshot",
            "client_signed_by",
            "client_signed_at",
            "client_signature_file",
            "intervention_media",
        ]
        widgets = {
            "scheduled_for": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "started_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "finished_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "client_signed_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "diagnosis": forms.Textarea(attrs={"rows": 3}),
            "parts_used": forms.Textarea(attrs={"rows": 2}),
            "technical_report": forms.Textarea(attrs={"rows": 4}),
            "structured_parts_used": forms.Textarea(
                attrs={"rows": 3, "placeholder": '[{"reference":"P-01","designation":"Carte","quantite":1}]'}
            ),
        }

    TECHNICIAN_ALLOWED_FIELDS = {
        "status",
        "scheduled_for",
        "started_at",
        "finished_at",
        "diagnosis",
        "action_taken",
        "parts_used",
        "structured_parts_used",
        "time_spent_minutes",
        "technical_report",
        "client_signed_at",
        "client_signature_file",
    }

    def __init__(self, *args, user=None, ticket=None, **kwargs):
        super().__init__(*args, **kwargs)
        agent_queryset = User.objects.filter(role__in=User.ASSIGNABLE_ROLES, is_active=True)
        if user and user.is_authenticated and not user.is_superuser and user.organization_id:
            agent_queryset = agent_queryset.filter(organization=user.organization)
        self.fields["agent"].queryset = agent_queryset.order_by("first_name", "last_name", "username")
        if user and user.is_authenticated and user.role == User.ROLE_TECHNICIAN:
            for field_name in list(self.fields):
                if field_name not in self.TECHNICIAN_ALLOWED_FIELDS:
                    self.fields.pop(field_name)
            if ticket and ticket.assigned_agent_id == user.id:
                self.initial.setdefault("status", Intervention.STATUS_IN_PROGRESS)

    def clean_structured_parts_used(self):
        value = self.cleaned_data.get("structured_parts_used")
        if isinstance(value, str):
            import json

            value = value.strip()
            if not value:
                return []
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError as exc:
                raise ValidationError("Le JSON des pieces remplacees est invalide.") from exc
            if not isinstance(parsed, list):
                raise ValidationError("Le champ pieces remplacees doit etre une liste JSON.")
            return parsed
        return value or []

    def clean_intervention_media(self):
        files = self.cleaned_data.get("intervention_media", [])
        if len(files) > 5:
            raise ValidationError("Vous pouvez joindre au maximum 5 photos par intervention.")
        return files


class InterventionMediaForm(forms.ModelForm):
    class Meta:
        model = InterventionMedia
        fields = ["kind", "file", "note"]
        widgets = {
            "note": forms.TextInput(attrs={"placeholder": "Ex: photo avant intervention"}),
        }


class AnalyticsQuestionForm(forms.Form):
    question = forms.CharField(
        label="Question analytique",
        widget=forms.TextInput(
            attrs={
                "placeholder": "Ex: pourquoi les tickets critiques augmentent cette semaine ?",
            }
        ),
    )


class SupportAssistantQuestionForm(forms.Form):
    product = forms.ModelChoiceField(queryset=Product.objects.none(), required=False, label="Produit")
    question = forms.CharField(
        label="Question",
        widget=forms.Textarea(
            attrs={
                "rows": 3,
                "placeholder": "Expliquez votre incident comme dans une conversation de support.",
            }
        ),
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        product_queryset = Product.objects.none()
        if user and user.is_authenticated:
            if user.role == User.ROLE_CLIENT:
                product_queryset = Product.objects.filter(client=user).order_by("name")
            else:
                product_queryset = Product.objects.select_related("client").order_by("name")
                if not user.is_superuser and user.organization_id:
                    product_queryset = product_queryset.filter(organization=user.organization)
        self.fields["product"].queryset = product_queryset


class CreditAccountForm(forms.Form):
    amount = forms.DecimalField(label="Montant", min_value=0.01, decimal_places=2, max_digits=12)
    currency = forms.CharField(label="Devise", max_length=10, initial="XAF")
    reason = forms.CharField(label="Motif", max_length=255)
    note = forms.CharField(label="Note", required=False, widget=forms.Textarea(attrs={"rows": 3}))
    external_reference = forms.CharField(label="Reference externe", required=False, max_length=120)


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = [
            "client",
            "equipment_category",
            "name",
            "sku",
            "serial_number",
            "equipment_type",
            "brand",
            "model_reference",
            "purchase_date",
            "installation_date",
            "warranty_end",
            "installation_address",
            "detailed_location",
            "status",
            "iot_enabled",
            "health_score",
            "counter_total",
            "counter_color",
            "counter_bw",
            "equipment_photo",
            "contract_reference",
            "notes",
        ]
        widgets = {
            "purchase_date": forms.DateInput(attrs={"type": "date"}),
            "installation_date": forms.DateInput(attrs={"type": "date"}),
            "warranty_end": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        client_queryset = User.objects.filter(role=User.ROLE_CLIENT, is_active=True)
        category_queryset = EquipmentCategory.objects.filter(is_active=True)
        if user and user.is_authenticated and not user.is_superuser and user.organization_id:
            client_queryset = client_queryset.filter(organization=user.organization)
            category_queryset = category_queryset.filter(organization=user.organization)
        self.fields["client"].queryset = client_queryset.order_by("company_name", "username")
        self.fields["equipment_category"].queryset = category_queryset.order_by("name")
        self.fields["equipment_category"].required = False
        self.fields["brand"].required = False
        self.fields["model_reference"].required = False
        self.fields["sku"].required = False
        self.fields["installation_address"].required = False
        self.fields["detailed_location"].required = False
        self.fields["contract_reference"].required = False
        self.fields["notes"].required = False
        self.fields["health_score"].help_text = "Valeur entre 0 et 100."

    def clean_health_score(self):
        value = self.cleaned_data.get("health_score")
        if value is None:
            return value
        if value < 0 or value > 100:
            raise ValidationError("Le score de sante doit etre compris entre 0 et 100.")
        return value

    def clean(self):
        cleaned_data = super().clean()
        client = cleaned_data.get("client")
        equipment_category = cleaned_data.get("equipment_category")
        if client and equipment_category and client.organization_id != equipment_category.organization_id:
            self.add_error("equipment_category", "La categorie selectionnee n'appartient pas a l'organisation du client.")
        return cleaned_data
