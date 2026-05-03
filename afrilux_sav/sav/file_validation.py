from pathlib import Path

from django.core.exceptions import ValidationError

MAX_TICKET_ATTACHMENT_BYTES = 10 * 1024 * 1024
ALLOWED_TICKET_ATTACHMENT_EXTENSIONS = {
    ".csv",
    ".doc",
    ".docx",
    ".jpeg",
    ".jpg",
    ".pdf",
    ".png",
    ".txt",
    ".xls",
    ".xlsx",
}
ALLOWED_TICKET_ATTACHMENT_CONTENT_TYPES = {
    "application/msword",
    "application/pdf",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "image/jpeg",
    "image/png",
    "text/csv",
    "text/plain",
}


def validate_ticket_attachment_file(uploaded_file):
    size = getattr(uploaded_file, "size", 0) or 0
    if size > MAX_TICKET_ATTACHMENT_BYTES:
        raise ValidationError("La piece jointe ne peut pas depasser 10 Mo.")

    name = getattr(uploaded_file, "name", "") or ""
    extension = Path(name).suffix.lower()
    if extension and extension not in ALLOWED_TICKET_ATTACHMENT_EXTENSIONS:
        raise ValidationError("Type de piece jointe non autorise.")

    content_type = (getattr(uploaded_file, "content_type", "") or "").lower()
    if content_type and content_type not in ALLOWED_TICKET_ATTACHMENT_CONTENT_TYPES:
        raise ValidationError("Type de piece jointe non autorise.")

    return uploaded_file
