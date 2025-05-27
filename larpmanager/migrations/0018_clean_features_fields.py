from django.core.exceptions import ObjectDoesNotExist
from django.db import migrations


def remove_obsolete_features(apps, schema_editor):
    Feature = apps.get_model("larpmanager", "Feature")
    EventConfig = apps.get_model("larpmanager", "EventConfig")
    features = {2: "title", 3: "props", 4: "mirror", 19: "cover", 22: "hide", 91: "progress", 92: "assigned"}
    for feature_id, feature_name in features.items():
        try:
            feature = Feature.objects.get(pk=feature_id)
        except ObjectDoesNotExist:
            continue

        for event in feature.events.all():
            EventConfig.objects.create(name=f"writing_{feature_name}", value="True", event=event)
        feature.delete()

    try:
        Feature.objects.get(pk=1).delete()
    except ObjectDoesNotExist:
        pass


class Migration(migrations.Migration):
    dependencies = [
        ("larpmanager", "0003_clean_features"),
    ]

    operations = [
        migrations.RunPython(remove_obsolete_features),
    ]
