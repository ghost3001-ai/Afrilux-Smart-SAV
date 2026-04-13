from django.core.management.base import BaseCommand, CommandError

from sav.models import Organization, User
from sav.services import ensure_default_equipment_categories, ensure_default_sla_rules


class Command(BaseCommand):
    help = "Initialise une organisation AFRILUX reelle avec un compte administrateur."

    def add_arguments(self, parser):
        parser.add_argument("--organization-name", required=True)
        parser.add_argument("--organization-slug", default="")
        parser.add_argument("--brand-name", default="")
        parser.add_argument("--portal-tagline", default="")
        parser.add_argument("--support-email", default="")
        parser.add_argument("--support-phone", default="")
        parser.add_argument("--headquarters-address", default="")
        parser.add_argument("--city", default="")
        parser.add_argument("--country", default="Cameroun")
        parser.add_argument("--reporting-emails", default="")
        parser.add_argument("--primary-color", default="#D5671D")
        parser.add_argument("--accent-color", default="#1C7A6A")
        parser.add_argument("--admin-username", required=True)
        parser.add_argument("--admin-email", required=True)
        parser.add_argument("--admin-password", required=True)
        parser.add_argument("--admin-first-name", default="Admin")
        parser.add_argument("--admin-last-name", default="AFRILUX")

    def handle(self, *args, **options):
        organization_name = options["organization_name"].strip()
        organization_slug = options["organization_slug"].strip()
        admin_username = options["admin_username"].strip()
        admin_email = options["admin_email"].strip().lower()
        admin_password = options["admin_password"]
        if not organization_name:
            raise CommandError("Le nom de l'organisation est obligatoire.")
        if not admin_username or not admin_email or not admin_password:
            raise CommandError("Les informations du compte administrateur sont obligatoires.")

        organization = None
        if organization_slug:
            organization = Organization.objects.filter(slug=organization_slug).first()
        if organization is None:
            organization = Organization.objects.filter(name__iexact=organization_name).first()
        created = organization is None
        if organization is None:
            organization = Organization(name=organization_name)
        if organization_slug:
            organization.slug = organization_slug
        organization.name = organization_name
        organization.brand_name = options["brand_name"].strip()
        organization.portal_tagline = options["portal_tagline"].strip()
        organization.support_email = options["support_email"].strip()
        organization.support_phone = options["support_phone"].strip()
        organization.headquarters_address = options["headquarters_address"].strip()
        organization.city = options["city"].strip()
        organization.country = options["country"].strip()
        organization.reporting_emails = options["reporting_emails"].strip()
        organization.primary_color = options["primary_color"].strip() or "#D5671D"
        organization.accent_color = options["accent_color"].strip() or "#1C7A6A"
        organization.save()
        ensure_default_sla_rules(organization)
        ensure_default_equipment_categories(organization)

        admin_user, admin_created = User.objects.get_or_create(
            username=admin_username,
            defaults={
                "email": admin_email,
                "organization": organization,
                "role": User.ROLE_ADMIN,
                "is_staff": True,
                "is_superuser": True,
                "first_name": options["admin_first_name"].strip(),
                "last_name": options["admin_last_name"].strip(),
                "professional_email": admin_email,
            },
        )
        admin_user.email = admin_email
        admin_user.organization = organization
        admin_user.role = User.ROLE_ADMIN
        admin_user.is_staff = True
        admin_user.is_superuser = True
        admin_user.first_name = options["admin_first_name"].strip()
        admin_user.last_name = options["admin_last_name"].strip()
        admin_user.professional_email = admin_email
        admin_user.set_password(admin_password)
        admin_user.save()

        self.stdout.write(
            self.style.SUCCESS(
                "Bootstrap termine pour "
                f"{organization.display_name}. Compte admin {'cree' if admin_created else 'mis a jour'}: {admin_user.username}"
            )
        )
