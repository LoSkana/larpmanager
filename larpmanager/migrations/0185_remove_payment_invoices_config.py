from django.core.cache import cache
from django.db import migrations

from larpmanager.cache.config import cache_configs_key
from larpmanager.cache.permission import clear_index_permission_cache


def remove_payment_invoices(apps, schema_editor):
    """Drop the payment_invoices pseudo-feature, its permissions and its configs."""
    apps.get_model("larpmanager", "AssociationPermission").objects.filter(slug="exe_invoices").delete()
    apps.get_model("larpmanager", "EventPermission").objects.filter(slug="orga_invoices").delete()
    apps.get_model("larpmanager", "Feature").objects.filter(slug="payment_invoices").delete()

    # historical models don't fire signals: collect owners to invalidate their config caches manually
    for model_name, owner_field in (("AssociationConfig", "association_id"), ("EventConfig", "event_id")):
        queryset = apps.get_model("larpmanager", model_name).objects.filter(name="payment_invoices")
        owner_ids = list(queryset.values_list(owner_field, flat=True))
        queryset.delete()
        for owner_id in owner_ids:
            cache.delete(cache_configs_key(owner_id, model_name.replace("Config", "").lower()))

    # permission index is cached for a day, and stale entries would reverse a removed url name
    clear_index_permission_cache("association")
    clear_index_permission_cache("event")


class Migration(migrations.Migration):
    dependencies = [
        ("larpmanager", "0184_relationshiptag_relationship_tags_and_more"),
    ]

    operations = [
        migrations.RunPython(remove_payment_invoices, migrations.RunPython.noop),
    ]
