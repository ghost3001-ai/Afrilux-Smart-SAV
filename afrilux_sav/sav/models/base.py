import uuid
from django.db import models
from django.utils import timezone
from django.utils.text import slugify


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


def _generate_unique_slug(model_cls, value, instance_pk=None, field_name="slug"):
    base_slug = slugify(value) or uuid.uuid4().hex[:8]
    slug = base_slug
    suffix = 2
    queryset = model_cls.objects.all()
    if instance_pk:
        queryset = queryset.exclude(pk=instance_pk)
    while queryset.filter(**{field_name: slug}).exists():
        slug = f"{base_slug}-{suffix}"
        suffix += 1
    return slug


def _current_year():
    return timezone.localdate().year
