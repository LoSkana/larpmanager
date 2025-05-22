from django.db import migrations


def remove_obsolete_features(apps, schema_editor):
    Feature = apps.get_model("larpmanager", "Feature")
    Feature.objects.filter(id__in=[176]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("larpmanager", "0013_alter_character_preview_alter_character_teaser_and_more"),
    ]

    operations = [
        migrations.RunPython(remove_obsolete_features),
    ]
