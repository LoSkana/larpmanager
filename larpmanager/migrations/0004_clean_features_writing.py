from typing import Any

from django.core.exceptions import ObjectDoesNotExist
from django.db import migrations


def remove_obsolete_features(apps: Any, schema_editor: Any) -> Any:
    Feature = apps.get_model("larpmanager", "Feature")
    EventConfig = apps.get_model("larpmanager", "EventConfig")
    features = {137: "paste_text", 147: "working_ticket"}
    for feature_id, feature_name in features.items():
        try:
            feature = Feature.objects.get(pk=feature_id)
        except ObjectDoesNotExist:
            continue

        for event in feature.events.all():
            EventConfig.objects.create(name=f"writing_{feature_name}", value="True", event=event)
        feature.delete()


class Migration(migrations.Migration):
    dependencies = [
        ("larpmanager", "0003_clean_features"),
    ]

    operations = [
        migrations.RunPython(remove_obsolete_features),
    ]
