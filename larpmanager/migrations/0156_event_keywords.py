from typing import Any

from django.db import migrations, models


def convert_configs(apps: Any, schema_editor: Any) -> None:
    """Convert config names."""
    EventConfig = apps.get_model("larpmanager", "EventConfig")
    configs = EventConfig.objects.filter(name="calendar_genre")
    for config in configs:
        config.name = "calendar_keywords"
        config.save()

class Migration(migrations.Migration):

    dependencies = [
        ("larpmanager", "0155_interface_version_system"),
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
        migrations.AlterField(
            model_name='event',
            name='keywords',
            field=models.CharField(blank=True, help_text='Keywords describing the event', max_length=100,
                                   verbose_name='Keywords'),
        ),
    ]
