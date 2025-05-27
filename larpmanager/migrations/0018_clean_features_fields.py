from django.core.exceptions import ObjectDoesNotExist
from django.db import migrations


def remove_obsolete_features(apps, schema_editor):
    Feature = apps.get_model("larpmanager", "Feature")
    EventConfig = apps.get_model("larpmanager", "EventConfig")
    features = {
        "writing": {2: "title", 3: "props", 19: "cover", 22: "hide", 92: "assigned"},
        "casting": {4: "mirror"},
        "user_character": {76: "player_relationships"},
    }
    for feat_name, feat_items in features.items():
        for feature_id, feature_name in feat_items:
            try:
                feature = Feature.objects.get(pk=feature_id)
            except ObjectDoesNotExist:
                continue

            for event in feature.events.all():
                EventConfig.objects.create(name=f"{feat_name}_{feature_name}", value="True", event=event)
            feature.delete()

    try:
        Feature.objects.get(pk=1).delete()
    except ObjectDoesNotExist:
        pass


class Migration(migrations.Migration):
    dependencies = [
        ("larpmanager", "0017_alter_faction_typ"),
    ]

    operations = [
        migrations.RunPython(remove_obsolete_features),
    ]
