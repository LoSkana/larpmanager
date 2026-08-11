from django.db import migrations


def remove_payment_invoices(apps, schema_editor):
    """Drop the payment_invoices pseudo-feature, its permissions and its configs."""
    apps.get_model("larpmanager", "AssociationPermission").objects.filter(slug="exe_invoices").delete()
    apps.get_model("larpmanager", "EventPermission").objects.filter(slug="orga_invoices").delete()
    apps.get_model("larpmanager", "Feature").objects.filter(slug="payment_invoices").delete()
    for model_name in ("AssociationConfig", "EventConfig"):
        apps.get_model("larpmanager", model_name).objects.filter(name="payment_invoices").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("larpmanager", "0184_relationshiptag_relationship_tags_and_more"),
    ]

    operations = [
        migrations.RunPython(remove_payment_invoices, migrations.RunPython.noop),
    ]
