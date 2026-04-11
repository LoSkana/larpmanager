from typing import Any

from django.db import migrations


def convert_player_relationships_config_to_feature(apps: Any, schema_editor: Any) -> None:
    """Convert user_character_player_relationships EventConfig entries to Feature assignments."""
    Feature = apps.get_model("larpmanager", "Feature")
    EventConfig = apps.get_model("larpmanager", "EventConfig")

    try:
        feature = Feature.objects.get(slug="player_relationships")
    except Feature.DoesNotExist:
        return

    configs = EventConfig.objects.filter(name="user_character_player_relationships", value="True")
    for config in configs:
        feature.events.add(config.event)

    configs.delete()


class Migration(migrations.Migration):
    dependencies = [
        ("larpmanager", "0153_systemexp_hidden"),
    ]

    operations = [
        migrations.RunPython(
            convert_player_relationships_config_to_feature,
            migrations.RunPython.noop,
        ),
    ]
