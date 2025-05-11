from django.db import migrations


def remove_obsolete_features(apps, schema_editor):
    Feature = apps.get_model("larpmanager", "Feature")
    Feature.objects.filter(id__in=[1, 5, 14, 17, 23]).delete()

    EventPermission = apps.get_model("larpmanager", "EventPermission")
    EventPermission.objects.filter(id__in=[48]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("larpmanager", "0002_clean_character"),
    ]

    operations = [
        migrations.RunPython(remove_obsolete_features),
    ]
