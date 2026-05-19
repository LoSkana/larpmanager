from typing import Any

from django.db import migrations


def migrate_player_cancellation(apps: Any, schema_editor: Any) -> None:
    """Remove player_cancellation feature; disable cancellation for events that never had it."""
    Feature = apps.get_model("larpmanager", "Feature")
    Event = apps.get_model("larpmanager", "Event")
    EventConfig = apps.get_model("larpmanager", "EventConfig")

    try:
        feature = Feature.objects.get(slug="player_cancellation")
    except Feature.DoesNotExist:
        return

    # Events that explicitly had the feature enabled (via M2M)
    enabled_event_ids = set(feature.events.values_list("id", flat=True))

    # Events that did NOT have the feature: disable self-service cancellation for them
    for event in Event.objects.exclude(id__in=enabled_event_ids):
        EventConfig.objects.get_or_create(
            event=event,
            name="player_cancellation_disable",
            defaults={"value": "True"},
        )

    # Remove the feature from all events and delete it
    feature.events.clear()
    feature.delete()


class Migration(migrations.Migration):
    dependencies = [
        ("larpmanager", "0163_add_emailcontent_attachment_name"),
    ]

    operations = [
        migrations.RunPython(migrate_player_cancellation, migrations.RunPython.noop),
    ]
