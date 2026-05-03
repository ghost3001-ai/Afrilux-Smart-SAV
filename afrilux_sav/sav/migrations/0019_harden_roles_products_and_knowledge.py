from django.db import migrations, models


def deduplicate_product_serials(apps, schema_editor):
    Product = apps.get_model("sav", "Product")
    seen = set()
    for product in Product.objects.order_by("organization_id", "serial_number", "id"):
        key = (product.organization_id, product.serial_number)
        if key not in seen:
            seen.add(key)
            continue
        base_serial = product.serial_number[:90]
        next_serial = f"{base_serial}-{product.id}"
        while Product.objects.filter(organization_id=product.organization_id, serial_number=next_serial).exclude(pk=product.pk).exists():
            base_serial = base_serial[:85]
            next_serial = f"{base_serial}-{product.id}"
        Product.objects.filter(pk=product.pk).update(serial_number=next_serial)
        seen.add((product.organization_id, next_serial))


class Migration(migrations.Migration):

    dependencies = [
        ("sav", "0018_message_recipient_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="product",
            name="serial_number",
            field=models.CharField(max_length=100),
        ),
        migrations.RunPython(deduplicate_product_serials, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="product",
            constraint=models.UniqueConstraint(
                fields=("organization", "serial_number"),
                name="sav_product_unique_serial_per_organization",
            ),
        ),
    ]
