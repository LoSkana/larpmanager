from django.db import migrations


def remove_calendar_past_events(apps, schema_editor):
    """Drop the old opt-in past events config and reset association caches."""
    from django.core.cache import cache

    from larpmanager.cache.association import cache_association_key

    AssociationConfig = apps.get_model("larpmanager", "AssociationConfig")
    Association = apps.get_model("larpmanager", "Association")

    AssociationConfig.objects.filter(name="calendar_past_events").delete()

    for slug in Association.objects.values_list("slug", flat=True):
        cache.delete(cache_association_key(slug))


class Migration(migrations.Migration):
    dependencies = [
        ("larpmanager", "0200_ability_creation_only_exclusiveexp"),
    ]

    operations = [
        migrations.RunPython(remove_calendar_past_events, migrations.RunPython.noop),
    ]
