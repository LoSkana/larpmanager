from typing import Any

from django.db import migrations


def convert_configs(apps: Any, schema_editor: Any) -> None:
    """Convert config names."""
    EventConfig = apps.get_model("larpmanager", "EventConfig")
    configs = EventConfig.objects.filter(name="calendar_genre")
    for config in configs:
        config.name = "calendar_keywords"
        config.save()

class Migration(migrations.Migration):

    dependencies = [
        ("larpmanager", "0154_player_relationships_feature"),
    ]

    operations = [
        migrations.RenameField(
            model_name="event",
            old_name="genre",
            new_name="keywords",
        ),
        migrations.RunPython(
            convert_configs,
            migrations.RunPython.noop,
        ),
    ]
