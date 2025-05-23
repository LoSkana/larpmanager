from django.db import migrations


def remove_obsolete_features(apps, schema_editor):
    Feature = apps.get_model("larpmanager", "Feature")
    Feature.objects.filter(id__in=[176]).delete()

    # save all the events to retrigger question generation
    Event = apps.get_model("larpmanager", "Event")
    for event in Event.objects.all():
        event.save()

    AssocPermission = apps.get_model("larpmanager", "AssocPermission")
    AssocPermission.objects.filter(id__in=[41]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("larpmanager", "0013_alter_character_preview_alter_character_teaser_and_more"),
    ]

    operations = [
        migrations.RunPython(remove_obsolete_features),
    ]
