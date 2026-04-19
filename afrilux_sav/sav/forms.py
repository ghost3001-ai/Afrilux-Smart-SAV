from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from .models import EquipmentCategory, FinancialTransaction, Intervention, InterventionMedia, Message, Organization, Product, Ticket, TicketAttachment, User
from .services import provision_client_account

MAX_TICKET_ATTACHMENT_BYTES = 10 * 1024 * 1024


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
            "related_transaction",
            "assigned_agent",
            "title",
            "description",
            "business_domain",
            "category",
            "channel",
            "status",
            "priority",
            "suspected_fraud",
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
        agent_queryset = User.objects.filter(role__in=User.ASSIGNABLE_ROLES)
        transaction_queryset = FinancialTransaction.objects.select_related("client")
        if user and user.is_authenticated and not user.is_superuser and user.organization_id:
            client_queryset = client_queryset.filter(organization=user.organization)
            agent_queryset = agent_queryset.filter(organization=user.organization)
            transaction_queryset = transaction_queryset.filter(organization=user.organization)
        self.fields["client"].queryset = client_queryset.order_by("username")
        self.fields["assigned_agent"].queryset = agent_queryset.order_by("username")
        self.fields["related_transaction"].queryset = transaction_queryset.order_by("-occurred_at", "-created_at")

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
            self.fields["suspected_fraud"].widget = forms.HiddenInput()
            self.fields["suspected_fraud"].required = False
            self.fields["product"].queryset = Product.objects.filter(client=user).order_by("name")
            self.fields["related_transaction"].queryset = transaction_queryset.filter(client=user).order_by("-occurred_at", "-created_at")
        else:
            product_queryset = Product.objects.select_related("client")
            if user and user.is_authenticated and not user.is_superuser and user.organization_id:
                product_queryset = product_queryset.filter(organization=user.organization)
            self.fields["product"].queryset = product_queryset.order_by("name")

    def clean(self):
        cleaned_data = super().clean()
        client = cleaned_data.get("client")
        product = cleaned_data.get("product")
        related_transaction = cleaned_data.get("related_transaction")
        cleaned_data["business_domain"] = cleaned_data.get("business_domain") or Ticket.DOMAIN_OTHER
        if client and product and product.client_id != client.id:
            self.add_error("product", "Le produit selectionne n'appartient pas a ce client.")
        if client and related_transaction and related_transaction.client_id != client.id:
            self.add_error("related_transaction", "La transaction selectionnee n'appartient pas a ce client.")
        return cleaned_data


class TicketCreateForm(TicketForm):
    initial_attachments = MultipleFileField(
        required=False,
        label="Preuves / captures / recus",
        help_text="Optionnel: ajoutez des pieces jointes des la creation du dossier.",
        widget=MultipleFileInput(attrs={"accept": "image/*,.pdf,.txt"}),
    )

    class Meta(TicketForm.Meta):
        fields = [*TicketForm.Meta.fields, "initial_attachments"]

    def clean_initial_attachments(self):
        attachments = self.cleaned_data.get("initial_attachments", [])
        total_size = sum(getattr(item, "size", 0) or 0 for item in attachments)
        if total_size > MAX_TICKET_ATTACHMENT_BYTES:
            raise ValidationError("Le total des pieces jointes ne peut pas depasser 10 Mo par ticket.")
        return attachments


class MessageForm(forms.ModelForm):
    class Meta:
        model = Message
        fields = ["message_type", "channel", "content"]
        widgets = {
            "content": forms.Textarea(attrs={"rows": 4, "placeholder": "Ajoutez un message, une note interne ou une mise a jour..."}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if not user or user.role == User.ROLE_CLIENT:
            self.fields["message_type"].widget = forms.HiddenInput()
            self.fields["message_type"].initial = Message.TYPE_PUBLIC
            self.fields["channel"].widget = forms.HiddenInput()
            self.fields["channel"].initial = Message.CHANNEL_PORTAL
        else:
            self.fields["message_type"].help_text = "Choisissez 'Note interne' pour un commentaire reserve a l'equipe SAV."
            self.fields["channel"].help_text = "Choisissez le canal externe si cette reponse doit etre diffusee hors portail."


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
            "cost",
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

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        agent_queryset = User.objects.filter(role__in=User.ASSIGNABLE_ROLES, is_active=True)
        if user and user.is_authenticated and not user.is_superuser and user.organization_id:
            agent_queryset = agent_queryset.filter(organization=user.organization)
        self.fields["agent"].queryset = agent_queryset.order_by("first_name", "last_name", "username")

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
