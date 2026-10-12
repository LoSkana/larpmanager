import django.db.models.deletion
from django.db import migrations, models


def link_discounts_to_registrations(apps, schema_editor):
    """Link confirmed discount items to the member registration on the same run, drop the rest."""
    accounting_item_discount = apps.get_model("larpmanager", "AccountingItemDiscount")
    registration_model = apps.get_model("larpmanager", "Registration")

    # Pending reservations and items without run/member cannot be linked
    accounting_item_discount.objects.filter(expires__isnull=False).delete()
    accounting_item_discount.objects.filter(models.Q(run__isnull=True) | models.Q(member__isnull=True)).delete()

    for item in accounting_item_discount.objects.all().iterator():
        registrations = registration_model.objects.filter(run_id=item.run_id, member_id=item.member_id)
        active = registrations.filter(deleted__isnull=True, cancellation_date__isnull=True)
        registration = (
            active.filter(redeem_code__isnull=True).order_by("-created").first()
            or active.order_by("-created").first()
            or registrations.order_by("-created").first()
        )
        if registration:
            accounting_item_discount.objects.filter(pk=item.pk).update(registration_id=registration.pk)

    accounting_item_discount.objects.filter(registration__isnull=True).delete()

    # Keep a single item per registration and discount
    seen = set()
    for item in accounting_item_discount.objects.order_by("id").iterator():
        item_key = (item.registration_id, item.disc_id, item.deleted)
        if item_key in seen:
            accounting_item_discount.objects.filter(pk=item.pk).delete()
        seen.add(item_key)


class Migration(migrations.Migration):

    dependencies = [
        ("larpmanager", "0195_callexp"),
    ]

    operations = [
        migrations.AddField(
            model_name="accountingitemdiscount",
            name="registration",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="discount_items",
                to="larpmanager.registration",
            ),
        ),
        migrations.RunPython(link_discounts_to_registrations, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="accountingitemdiscount",
            name="run",
        ),
        migrations.RemoveField(
            model_name="accountingitemdiscount",
            name="expires",
        ),
        migrations.RemoveField(
            model_name="accountingitemdiscount",
            name="detail",
        ),
        migrations.AlterField(
            model_name="accountingitemdiscount",
            name="registration",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="discount_items",
                to="larpmanager.registration",
            ),
        ),
        migrations.AddConstraint(
            model_name="accountingitemdiscount",
            constraint=models.UniqueConstraint(
                fields=("registration", "disc", "deleted"),
                name="unique_accounting_item_discount_with_optional",
            ),
        ),
        migrations.AddConstraint(
            model_name="accountingitemdiscount",
            constraint=models.UniqueConstraint(
                condition=models.Q(("deleted", None)),
                fields=("registration", "disc"),
                name="unique_accounting_item_discount_without_optional",
            ),
        ),
    ]
