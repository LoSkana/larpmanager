from django.core.exceptions import ObjectDoesNotExist
from django.db import migrations


def remove_obsolete_features(apps, schema_editor):
    Feature = apps.get_model("larpmanager", "Feature")
    EventConfig = apps.get_model("larpmanager", "EventConfig")
    features = {159: "reg_que_age", 49: "reg_que_faction", 61: "reg_que_tickets"}
    for feature_id, feature_name in features.items():
        try:
            feature = Feature.objects.get(pk=feature_id)
        except ObjectDoesNotExist:
            continue

        for event in feature.events.all():
            EventConfig.objects.create(name=f"registration_{feature_name}", value="True", event=event)
        feature.delete()


class Migration(migrations.Migration):
    dependencies = [
        ("larpmanager", "0009_alter_writingquestion_applicable"),
    ]

    operations = [
        migrations.RunPython(remove_obsolete_features),
    ]
