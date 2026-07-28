import json
from datetime import datetime
from decimal import Decimal

from django.db.models import Q
from django.utils import timezone

from ..models import InterventionPartUsage, MaintenancePartUsage, SparePart


def _coerce_bool(value, default=False):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "oui"}
    return default


def _parse_date_value(value, field_label="date"):
    if hasattr(value, "date") and callable(value.date):
        return value.date()
    if hasattr(value, "isoformat") and not isinstance(value, str):
        return value
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError(f"Le champ {field_label} est obligatoire.")
    try:
        return datetime.fromisoformat(normalized).date()
    except ValueError as exc:
        raise ValueError(f"Le champ {field_label} doit etre une date ISO valide.") from exc


def _parse_datetime_value(value, field_label="date_heure"):
    if hasattr(value, "isoformat") and not isinstance(value, str):
        parsed = value
    else:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError(f"Le champ {field_label} est obligatoire.")
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError as exc:
            raise ValueError(f"Le champ {field_label} doit etre une date/heure ISO valide.") from exc
    if timezone.is_naive(parsed):
        return timezone.make_aware(parsed)
    return parsed


def _coerce_json_list(value, field_label):
    if value in (None, ""):
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return []
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            return [item.strip() for item in stripped.splitlines() if item.strip()]
        if not isinstance(parsed, list):
            raise ValueError(f"Le champ {field_label} doit etre une liste.")
        return parsed
    raise ValueError(f"Le champ {field_label} doit etre une liste.")


def _coerce_json_dict(value, field_label):
    if value in (None, ""):
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return {}
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Le champ {field_label} doit etre un objet JSON valide.") from exc
        if not isinstance(parsed, dict):
            raise ValueError(f"Le champ {field_label} doit etre un objet JSON.")
        return parsed
    raise ValueError(f"Le champ {field_label} doit etre un objet JSON.")


def _coerce_id_list(value, error_message="Les identifiants d'equipements doivent etre numeriques."):
    if value in (None, ""):
        return []
    if isinstance(value, (list, tuple, set)):
        raw_items = value
    else:
        raw_items = str(value).replace(";", ",").split(",")
    ids = []
    for item in raw_items:
        normalized = str(item).strip()
        if not normalized:
            continue
        try:
            ids.append(int(normalized))
        except ValueError as exc:
            raise ValueError(error_message) from exc
    return ids


def _coerce_decimal_quantity(value, default=Decimal("1.00")):
    if value in (None, ""):
        return default
    try:
        quantity = Decimal(str(value))
    except Exception as exc:
        raise ValueError("La quantite de piece doit etre numerique.") from exc
    if quantity <= 0:
        raise ValueError("La quantite de piece doit etre superieure a zero.")
    return quantity


def _part_queryset_for_organization(organization):
    queryset = SparePart.objects.filter(is_active=True)
    if organization is not None:
        queryset = queryset.filter(Q(organization=organization) | Q(organization__isnull=True))
    return queryset


def _normalize_part_usage_payloads(*, organization=None, spare_parts=None, structured_parts_used=None):
    payloads = []
    part_queryset = _part_queryset_for_organization(organization)

    for item in spare_parts or []:
        if isinstance(item, SparePart):
            part = item
            if organization and part.organization_id and part.organization_id != organization.id:
                raise ValueError("Une piece selectionnee appartient a une autre organisation.")
        else:
            try:
                part_id = int(str(item).strip())
            except (TypeError, ValueError) as exc:
                raise ValueError("Les identifiants de pieces doivent etre numeriques.") from exc
            part = part_queryset.filter(pk=part_id).first()
            if part is None:
                raise ValueError("Piece catalogue introuvable ou inactive.")
        payloads.append(
            {
                "spare_part": part,
                "quantity": Decimal("1.00"),
                "note": "",
            }
        )

    for item in _coerce_json_list(structured_parts_used, "pieces_catalogue"):
        if isinstance(item, str):
            name = item.strip()
            if not name:
                continue
            payloads.append(
                {
                    "spare_part": None,
                    "name_snapshot": name[:180],
                    "reference_snapshot": "",
                    "category_snapshot": "",
                    "unit_snapshot": "piece",
                    "quantity": Decimal("1.00"),
                    "note": "",
                }
            )
            continue
        if not isinstance(item, dict):
            raise ValueError("Chaque piece catalogue doit etre un objet JSON ou une ligne texte.")

        part = None
        part_id = item.get("spare_part") or item.get("spare_part_id") or item.get("part_id") or item.get("piece_id")
        reference = str(item.get("reference") or item.get("ref") or "").strip()
        if part_id:
            try:
                part = part_queryset.filter(pk=int(part_id)).first()
            except (TypeError, ValueError) as exc:
                raise ValueError("Les identifiants de pieces doivent etre numeriques.") from exc
        elif reference:
            part = part_queryset.filter(reference__iexact=reference).first()
        if (part_id or reference) and part is None:
            raise ValueError("Piece catalogue introuvable ou inactive.")

        payloads.append(
            {
                "spare_part": part,
                "name_snapshot": str(item.get("name") or item.get("designation") or (part.name if part else ""))[:180],
                "reference_snapshot": str(reference or (part.reference if part else ""))[:120],
                "category_snapshot": str(item.get("category") or (part.category if part else ""))[:120],
                "unit_snapshot": str(item.get("unit") or item.get("unite") or (part.unit if part else "piece"))[:40],
                "quantity": _coerce_decimal_quantity(item.get("quantity") or item.get("quantite") or item.get("qty")),
                "note": str(item.get("note") or item.get("comment") or "")[:1000],
            }
        )
    return payloads


def _part_usage_summary(payloads):
    lines = []
    for payload in payloads:
        part = payload.get("spare_part")
        reference = payload.get("reference_snapshot") or (part.reference if part else "")
        name = payload.get("name_snapshot") or (part.name if part else "")
        quantity = payload.get("quantity") or Decimal("1.00")
        unit = payload.get("unit_snapshot") or (part.unit if part else "piece")
        label = " - ".join(chunk for chunk in [reference, name] if chunk) or "Piece"
        lines.append(f"{label} x {quantity:g} {unit}".strip())
    return "\n".join(lines)


def _part_usage_records_summary(records):
    lines = []
    for usage in records:
        part = usage.spare_part
        reference = usage.reference_snapshot or (part.reference if part else "")
        name = usage.name_snapshot or (part.name if part else "")
        quantity = usage.quantity or Decimal("1.00")
        unit = usage.unit_snapshot or (part.unit if part else "piece")
        label = " - ".join(chunk for chunk in [reference, name] if chunk) or "Piece"
        lines.append(f"{label} x {quantity:g} {unit}".strip())
    return "\n".join(lines)


def record_intervention_part_usages(intervention, *, spare_parts=None, structured_parts_used=None, replace=False):
    payloads = _normalize_part_usage_payloads(
        organization=intervention.organization,
        spare_parts=spare_parts,
        structured_parts_used=structured_parts_used,
    )
    if replace:
        intervention.part_usages.all().delete()
    created = []
    for payload in payloads:
        created.append(
            InterventionPartUsage.objects.create(
                intervention=intervention,
                organization=intervention.organization,
                **payload,
            )
        )
    if created and not (intervention.parts_used or "").strip():
        intervention.parts_used = _part_usage_summary(payloads)
        intervention.save(update_fields=["parts_used", "updated_at"])
    return created


def record_maintenance_part_usages(report, *, spare_parts=None, structured_parts_used=None, replace=False):
    payloads = _normalize_part_usage_payloads(
        organization=report.organization,
        spare_parts=spare_parts,
        structured_parts_used=structured_parts_used,
    )
    if replace:
        report.part_usages.all().delete()
    created = []
    for payload in payloads:
        created.append(
            MaintenancePartUsage.objects.create(
                report=report,
                organization=report.organization,
                **payload,
            )
        )
    if created and not (report.parts_used or "").strip():
        report.parts_used = _part_usage_summary(payloads)
        report.save(update_fields=["parts_used", "updated_at"])
    return created
