from django.core.exceptions import ObjectDoesNotExist
from django.db import migrations, models


def remove_obsolete_features(apps, schema_editor):
    Feature = apps.get_model("larpmanager", "Feature")
    EventConfig = apps.get_model("larpmanager", "EventConfig")
    features = {
        "writing": {2: "title", 3: "props", 19: "cover", 22: "hide", 92: "assigned"},
        "casting": {4: "mirror"},
        "user_character": {76: "player_relationships"},
    }
    for feat_name, feat_items in features.items():
        for feature_id, feature_name in feat_items.items():
            try:
                feature = Feature.objects.get(pk=feature_id)
            except ObjectDoesNotExist:
                continue

            for event in feature.events.all():
                EventConfig.objects.create(name=f"{feat_name}_{feature_name}", value="True", event=event)
            feature.delete()

    # create question and answer to save data in "props"
    Character = apps.get_model("larpmanager", "Character")
    WritingQuestion = apps.get_model("larpmanager", "WritingQuestion")
    WritingAnswer = apps.get_model("larpmanager", "WritingAnswer")
    for char in Character.objects.exclude(props="").exclude(props__isnull=True):
        (que, cr) = WritingQuestion.objects.get_or_create(event=char.event, typ="t", display="Props")
        (ca, cr) = WritingAnswer.objects.get_or_create(element_id=char.id, question=que)
        ca.text = char.props
        ca.save()

    WritingQuestion.objects.filter(typ="props").delete()

    # Delete orga_props permission
    EventPermission = apps.get_model("larpmanager", "EventPermission")
    EventPermission.objects.filter(id__in=[56]).delete()

    # re-delete motto that it didn't work first time?
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
        migrations.RemoveField(
            model_name="character",
            name="props",
        ),
        migrations.RemoveField(
            model_name="faction",
            name="props",
        ),
        migrations.RemoveField(
            model_name="handout",
            name="props",
        ),
        migrations.RemoveField(
            model_name="plot",
            name="props",
        ),
        migrations.RemoveField(
            model_name="prologue",
            name="props",
        ),
        migrations.RemoveField(
            model_name="prologuetype",
            name="props",
        ),
        migrations.RemoveField(
            model_name="quest",
            name="props",
        ),
        migrations.RemoveField(
            model_name="questtype",
            name="props",
        ),
        migrations.RemoveField(
            model_name="speedlarp",
            name="props",
        ),
        migrations.RemoveField(
            model_name="trait",
            name="props",
        ),
        migrations.AlterField(
            model_name="registrationquestion",
            name="typ",
            field=models.CharField(
                choices=[
                    ("s", "Single choice"),
                    ("m", "Multiple choice"),
                    ("t", "Single-line text"),
                    ("p", "Multi-line text"),
                    ("e", "Advanced text editor"),
                    ("name", "Name"),
                    ("teaser", "Presentation"),
                    ("text", "Sheet"),
                    ("preview", "Preview"),
                    ("cover", "Cover"),
                    ("faction", "Factions"),
                    ("title", "Title"),
                    ("mirror", "Mirror"),
                    ("hide", "Hide"),
                    ("progress", "Progress"),
                    ("assigned", "Assigned"),
                ],
                default="s",
                help_text="Question type",
                max_length=10,
                verbose_name="Type",
            ),
        ),
        migrations.AlterField(
            model_name="writingquestion",
            name="typ",
            field=models.CharField(
                choices=[
                    ("s", "Single choice"),
                    ("m", "Multiple choice"),
                    ("t", "Single-line text"),
                    ("p", "Multi-line text"),
                    ("e", "Advanced text editor"),
                    ("name", "Name"),
                    ("teaser", "Presentation"),
                    ("text", "Sheet"),
                    ("preview", "Preview"),
                    ("cover", "Cover"),
                    ("faction", "Factions"),
                    ("title", "Title"),
                    ("mirror", "Mirror"),
                    ("hide", "Hide"),
                    ("progress", "Progress"),
                    ("assigned", "Assigned"),
                ],
                default="s",
                help_text="Question type",
                max_length=10,
                verbose_name="Type",
            ),
        ),
    ]
