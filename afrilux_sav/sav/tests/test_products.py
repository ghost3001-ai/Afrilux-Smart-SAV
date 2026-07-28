from .base import *


class ProductTests(SavPlatformTests):
    def test_admin_can_open_product_create_page(self):
        admin_user = User.objects.create_user(
            username="admin_product",
            password="secret123",
            organization=self.organization,
            role=User.ROLE_ADMIN,
            is_staff=True,
        )
        self.client.force_login(admin_user)

        response = self.client.get(reverse("product-create"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "sav/product_form.html")
        self.assertContains(response, "Ajouter un produit")

    def test_admin_can_create_product_via_web_portal(self):
        admin_user = User.objects.create_user(
            username="admin_product_create",
            password="secret123",
            organization=self.organization,
            role=User.ROLE_ADMIN,
            is_staff=True,
        )
        self.client.force_login(admin_user)

        response = self.client.post(
            reverse("product-create"),
            {
                "client": self.client_user.pk,
                "equipment_category": self.category.pk,
                "name": "HP Color LaserJet",
                "sku": "HP-COLOR-01",
                "serial_number": "HP-PORTAL-0001",
                "equipment_type": "printer",
                "brand": "HP",
                "model_reference": "Color LaserJet Pro",
                "status": Product.STATUS_ACTIVE,
                "health_score": 96,
                "counter_total": 0,
                "counter_color": 0,
                "counter_bw": 0,
                "iot_enabled": "on",
                "installation_address": "Douala",
                "detailed_location": "Plateau technique",
                "contract_reference": "CTR-2026-001",
                "notes": "Produit cree depuis le portail admin.",
            },
        )

        self.assertEqual(response.status_code, 302)
        created = Product.objects.get(serial_number="HP-PORTAL-0001")
        self.assertEqual(created.client, self.client_user)
        self.assertEqual(created.organization, self.organization)
        self.assertEqual(created.equipment_category, self.category)
        self.assertTrue(AuditLog.objects.filter(action="product_created_web", target_id=created.pk).exists())

    def test_admin_can_update_product_via_web_portal(self):
        admin_user = User.objects.create_user(
            username="admin_product_update",
            password="secret123",
            organization=self.organization,
            role=User.ROLE_ADMIN,
            is_staff=True,
        )
        self.client.force_login(admin_user)

        response = self.client.post(
            reverse("product-update", args=[self.product.pk]),
            {
                "client": self.client_user.pk,
                "equipment_category": self.category.pk,
                "name": "Onduleur 5kVA Revise",
                "sku": "AFR-OND-5KVA",
                "serial_number": self.product.serial_number,
                "equipment_type": "other",
                "brand": "Afrilux",
                "model_reference": "Revision 2026",
                "status": Product.STATUS_IN_SERVICE,
                "health_score": 88,
                "counter_total": 145,
                "counter_color": 23,
                "counter_bw": 122,
                "installation_address": "Douala",
                "detailed_location": "Salle technique B",
                "contract_reference": "CTR-REV-01",
                "notes": "Mise a jour depuis le portail admin.",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.product.refresh_from_db()
        self.assertEqual(self.product.name, "Onduleur 5kVA Revise")
        self.assertEqual(self.product.status, Product.STATUS_OPERATIONAL)
        self.assertEqual(self.product.health_score, 88)
        self.assertTrue(AuditLog.objects.filter(action="product_updated_web", target_id=self.product.pk).exists())

    def test_admin_can_delete_product_via_web_portal(self):
        admin_user = User.objects.create_user(
            username="admin_product_delete",
            password="secret123",
            organization=self.organization,
            role=User.ROLE_ADMIN,
            is_staff=True,
        )
        product = Product.objects.create(
            client=self.client_user,
            equipment_category=self.category,
            name="Produit a supprimer",
            serial_number="AFR-DELETE-0001",
        )
        self.client.force_login(admin_user)

        response = self.client.post(reverse("product-delete", args=[product.pk]))

        self.assertEqual(response.status_code, 302)
        self.assertFalse(Product.objects.filter(pk=product.pk).exists())
        self.assertTrue(AuditLog.objects.filter(action="product_deleted_web", target_reference__icontains="AFR-DELETE-0001").exists())

    def test_non_admin_cannot_access_product_create_page(self):
        self.client.force_login(self.manager)

        response = self.client.get(reverse("product-create"))

        self.assertEqual(response.status_code, 403)

    def test_non_admin_cannot_access_product_update_or_delete_pages(self):
        self.client.force_login(self.manager)

        update_response = self.client.get(reverse("product-update", args=[self.product.pk]))
        delete_response = self.client.get(reverse("product-delete", args=[self.product.pk]))

        self.assertEqual(update_response.status_code, 403)
        self.assertEqual(delete_response.status_code, 403)

    def test_product_transfer_location_records_history_and_new_status(self):
        workshop_note = "Atelier central Douala - banc de test"

        response = self.api.post(
            reverse("sav_api:product-transfer-location", args=[self.product.pk]),
            {
                "to_location": workshop_note,
                "to_location_status": Product.LOCATION_WORKSHOP,
                "reason": "Diagnostic approfondi en atelier.",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.product.refresh_from_db()
        self.assertEqual(self.product.location_status, Product.LOCATION_WORKSHOP)
        self.assertEqual(self.product.detailed_location, workshop_note)
        history = EquipmentLocationHistory.objects.get(product=self.product)
        self.assertEqual(history.from_client, self.client_user)
        self.assertEqual(history.to_client, self.client_user)
        self.assertEqual(history.to_location_status, Product.LOCATION_WORKSHOP)
        self.assertEqual(history.moved_by, self.manager)

    def test_product_transfer_to_client_site_updates_client_site_relation(self):
        site = ClientSite.objects.create(
            client=self.client_user,
            agency=Agency.objects.create(organization=self.organization, name="Agence Bonanjo", city="Douala"),
            name="Siege Bonanjo",
            address="Bonanjo, Douala",
            city="Douala",
        )

        response = self.api.post(
            reverse("sav_api:product-transfer-location", args=[self.product.pk]),
            {
                "to_site": site.pk,
                "to_location_status": Product.LOCATION_INSTALLED,
                "reason": "Installation sur le site principal.",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.product.refresh_from_db()
        self.assertEqual(self.product.site, site)
        self.assertEqual(self.product.installation_address, "Bonanjo, Douala")

    def test_spare_part_catalog_usage_snapshots_reference_on_intervention(self):
        part_response = self.api.post(
            reverse("sav_api:spare-part-list"),
            {
                "name": "Filtre climatisation 18000 BTU",
                "reference": "CLIM-FILT-18K",
                "category": "Froid",
                "equipment_category": self.category.pk,
                "unit": "piece",
            },
            format="json",
        )
        self.assertEqual(part_response.status_code, 201)
        spare_part = SparePart.objects.get(reference="CLIM-FILT-18K")
        ticket = Ticket.objects.create(
            client=self.client_user,
            product=self.product,
            assigned_agent=self.agent,
            title="Remplacement filtre",
            description="Intervention avec piece referencee.",
            status=Ticket.STATUS_IN_PROGRESS,
            priority=Ticket.PRIORITY_NORMAL,
        )
        intervention = Intervention.objects.create(
            ticket=ticket,
            agent=self.agent,
            diagnosis="Filtre encrasse.",
            action_taken="Remplacement du filtre.",
        )

        usage_response = self.api.post(
            reverse("sav_api:intervention-part-usage-list"),
            {
                "intervention": intervention.pk,
                "spare_part": spare_part.pk,
                "quantity": "2.00",
                "note": "Deux filtres remplaces.",
            },
            format="json",
        )

        self.assertEqual(usage_response.status_code, 201)
        usage = InterventionPartUsage.objects.get(intervention=intervention)
        self.assertEqual(usage.reference_snapshot, "CLIM-FILT-18K")
        self.assertEqual(usage.name_snapshot, "Filtre climatisation 18000 BTU")
        self.assertEqual(str(usage.quantity), "2.00")

    def test_knowledge_base_filters_internal_articles_from_client(self):
        KnowledgeArticle.objects.create(
            organization=self.organization,
            title="Procedure interne serveur",
            category="depannage",
            equipment_category=self.category,
            summary="Procedure reservee aux techniciens.",
            content="Acces interne uniquement.",
            status=KnowledgeArticle.STATUS_PUBLISHED,
            audience=KnowledgeArticle.AUDIENCE_INTERNAL,
        )

        self.api.force_authenticate(user=self.client_user)
        client_response = self.api.get(reverse("sav_api:knowledge-article-list"))
        self.assertEqual(client_response.status_code, 200)
        client_payload = (
            client_response.data["results"]
            if isinstance(client_response.data, dict) and "results" in client_response.data
            else client_response.data
        )
        client_titles = {item["title"] for item in client_payload}
        self.assertIn("Guide de verification du cablage", client_titles)
        self.assertNotIn("Procedure interne serveur", client_titles)

        self.api.force_authenticate(user=self.manager)
        manager_response = self.api.get(reverse("sav_api:knowledge-article-list"))
        self.assertEqual(manager_response.status_code, 200)
        manager_payload = (
            manager_response.data["results"]
            if isinstance(manager_response.data, dict) and "results" in manager_response.data
            else manager_response.data
        )
        manager_titles = {item["title"] for item in manager_payload}
        self.assertIn("Procedure interne serveur", manager_titles)
