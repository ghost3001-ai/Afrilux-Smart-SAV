from rest_framework import serializers

from ..models import (
    ChecklistTemplate,
    MaintenancePartUsage,
    MaintenanceProgram,
    MaintenanceReport,
    MaintenanceReportPhoto,
    MaintenanceTicket,
    Product,
    User,
)


class ChecklistTemplateSerializer(serializers.ModelSerializer):
    organization_name = serializers.CharField(source="organization.display_name", read_only=True)
    equipment_category_name = serializers.CharField(source="equipment_category.name", read_only=True)

    class Meta:
        model = ChecklistTemplate
        fields = [
            "id",
            "organization",
            "organization_name",
            "service",
            "equipment_category",
            "equipment_category_name",
            "name",
            "checklist",
            "is_active",
            "created_at",
            "updated_at",
        ]


class MaintenanceReportPhotoSerializer(serializers.ModelSerializer):
    uploaded_by_name = serializers.SerializerMethodField()
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = MaintenanceReportPhoto
        fields = ["id", "report", "uploaded_by", "uploaded_by_name", "file", "file_url", "note", "created_at", "updated_at"]
        read_only_fields = ["uploaded_by", "uploaded_by_name", "file_url", "created_at", "updated_at"]

    def get_uploaded_by_name(self, obj):
        return str(obj.uploaded_by) if obj.uploaded_by else None

    def get_file_url(self, obj):
        request = self.context.get("request")
        if not obj.file:
            return ""
        url = obj.file.url
        return request.build_absolute_uri(url) if request else url


class MaintenanceReportSerializer(serializers.ModelSerializer):
    technician_name = serializers.SerializerMethodField()
    validated_by_name = serializers.SerializerMethodField()
    ticket_title = serializers.CharField(source="maintenance_ticket.title", read_only=True)
    organization_name = serializers.CharField(source="organization.display_name", read_only=True)
    report_pdf_url = serializers.SerializerMethodField()
    photo_files = MaintenanceReportPhotoSerializer(many=True, read_only=True)

    class Meta:
        model = MaintenanceReport
        fields = [
            "id",
            "organization",
            "organization_name",
            "maintenance_ticket",
            "ticket_title",
            "technician",
            "technician_name",
            "validated_by",
            "validated_by_name",
            "validated_at",
            "actual_started_at",
            "actual_finished_at",
            "checklist_completed",
            "observations",
            "work_to_plan",
            "parts_used",
            "parts_status",
            "intervention_types",
            "anomaly_detected",
            "photos",
            "photo_files",
            "client_signed_by",
            "client_signature_file",
            "report_pdf",
            "report_pdf_url",
            "report_generated_at",
            "final_status",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "organization",
            "organization_name",
            "technician_name",
            "validated_by",
            "validated_by_name",
            "validated_at",
            "ticket_title",
            "report_pdf_url",
            "photo_files",
            "report_generated_at",
            "created_at",
            "updated_at",
        ]

    def get_technician_name(self, obj):
        return str(obj.technician)

    def get_validated_by_name(self, obj):
        return str(obj.validated_by) if obj.validated_by else None

    def get_report_pdf_url(self, obj):
        request = self.context.get("request")
        if not obj.report_pdf:
            return ""
        url = obj.report_pdf.url
        return request.build_absolute_uri(url) if request else url


class MaintenancePartUsageSerializer(serializers.ModelSerializer):
    spare_part_label = serializers.SerializerMethodField()
    organization_name = serializers.CharField(source="organization.display_name", read_only=True)

    class Meta:
        model = MaintenancePartUsage
        fields = [
            "id",
            "organization",
            "organization_name",
            "report",
            "spare_part",
            "spare_part_label",
            "name_snapshot",
            "reference_snapshot",
            "category_snapshot",
            "quantity",
            "unit_snapshot",
            "note",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["organization", "organization_name", "spare_part_label", "created_at", "updated_at"]

    def get_spare_part_label(self, obj):
        return str(obj.spare_part) if obj.spare_part else ""


class MaintenanceTicketSerializer(serializers.ModelSerializer):
    organization_name = serializers.CharField(source="organization.display_name", read_only=True)
    program_title = serializers.CharField(source="program.title", read_only=True)
    responsible_name = serializers.SerializerMethodField()
    technician_name = serializers.SerializerMethodField()
    client_name = serializers.SerializerMethodField()
    products = serializers.PrimaryKeyRelatedField(many=True, required=False, queryset=Product.objects.all())
    product_names = serializers.SerializerMethodField()
    report = MaintenanceReportSerializer(read_only=True)
    anomaly_ticket_reference = serializers.CharField(source="anomaly_ticket.reference", read_only=True)
    type_label = serializers.CharField(read_only=True)
    is_late = serializers.BooleanField(read_only=True)

    class Meta:
        model = MaintenanceTicket
        fields = [
            "id",
            "organization",
            "organization_name",
            "program",
            "program_title",
            "responsible",
            "responsible_name",
            "technician",
            "technician_name",
            "client",
            "client_name",
            "products",
            "product_names",
            "title",
            "type_label",
            "service",
            "periodicity",
            "scheduled_date",
            "initial_scheduled_date",
            "status",
            "checklist",
            "instructions",
            "priority",
            "location",
            "route",
            "overnight_stays",
            "call_date",
            "system_tools",
            "equipment_brand",
            "equipment_type",
            "equipment_identifier",
            "intervention_reason",
            "started_at",
            "finished_at",
            "postponed_to",
            "postponement_reason",
            "notified_at",
            "acknowledged_at",
            "overdue_alerted_at",
            "cancelled_at",
            "cancellation_reason",
            "anomaly_ticket",
            "anomaly_ticket_reference",
            "is_late",
            "report",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "organization",
            "organization_name",
            "program_title",
            "responsible_name",
            "technician_name",
            "client_name",
            "product_names",
            "type_label",
            "started_at",
            "finished_at",
            "notified_at",
            "acknowledged_at",
            "overdue_alerted_at",
            "cancelled_at",
            "anomaly_ticket",
            "anomaly_ticket_reference",
            "is_late",
            "report",
            "created_at",
            "updated_at",
        ]

    def get_responsible_name(self, obj):
        return str(obj.responsible) if obj.responsible else None

    def get_technician_name(self, obj):
        return str(obj.technician)

    def get_client_name(self, obj):
        return str(obj.client)

    def get_product_names(self, obj):
        return [str(product) for product in obj.products.all()]

    def validate(self, attrs):
        attrs = super().validate(attrs)
        program = attrs.get("program") or getattr(self.instance, "program", None)
        technician = attrs.get("technician") or getattr(self.instance, "technician", None)
        client = attrs.get("client") or getattr(self.instance, "client", None)
        products = attrs.get("products")
        organization = attrs.get("organization") or getattr(self.instance, "organization", None) or getattr(program, "organization", None)
        if technician and technician.role not in set(User.TECHNICIAN_SPACE_ROLES):
            raise serializers.ValidationError({"technician": "Selectionnez un technicien terrain ou responsable technique habilite."})
        if technician and organization and technician.organization_id and technician.organization_id != organization.id:
            raise serializers.ValidationError({"technician": "Le technicien appartient a une autre organisation."})
        if client and organization and client.organization_id and client.organization_id != organization.id:
            raise serializers.ValidationError({"client": "Le client appartient a une autre organisation."})
        if products and client:
            for product in products:
                if product.client_id != client.id:
                    raise serializers.ValidationError({"products": "Tous les equipements doivent appartenir au client selectionne."})
        return attrs


class MaintenanceProgramSerializer(serializers.ModelSerializer):
    organization_name = serializers.CharField(source="organization.display_name", read_only=True)
    responsible_name = serializers.SerializerMethodField()
    tickets_count = serializers.SerializerMethodField()
    tickets_done = serializers.SerializerMethodField()
    period_label = serializers.CharField(read_only=True)

    class Meta:
        model = MaintenanceProgram
        fields = [
            "id",
            "organization",
            "organization_name",
            "responsible",
            "responsible_name",
            "title",
            "service",
            "period_type",
            "period_label",
            "month",
            "quarter",
            "year",
            "task_lines",
            "status",
            "published_at",
            "tickets_count",
            "tickets_done",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["organization_name", "responsible_name", "period_label", "published_at", "tickets_count", "tickets_done"]

    def get_responsible_name(self, obj):
        return str(obj.responsible) if obj.responsible else None

    def get_tickets_count(self, obj):
        return obj.tickets.count()

    def get_tickets_done(self, obj):
        return obj.tickets.filter(status=MaintenanceTicket.STATUS_DONE).count()
