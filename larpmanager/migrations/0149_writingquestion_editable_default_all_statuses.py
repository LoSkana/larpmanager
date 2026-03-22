from django.db import migrations, models


def set_editable_all_statuses(apps, schema_editor):
    """Set editable to all character statuses for WritingQuestions with no editable value."""
    WritingQuestion = apps.get_model("larpmanager", "WritingQuestion")
    all_statuses = "c,s,r,a"
    WritingQuestion.objects.filter(deleted__isnull=True, editable="").update(editable=all_statuses)
    WritingQuestion.objects.filter(deleted__isnull=True, editable__isnull=True).update(editable=all_statuses)


class Migration(migrations.Migration):
    dependencies = [
        ("larpmanager", "0148_systempx_and_px_systems"),
    ]

    operations = [
        migrations.AlterField(
            model_name='writingquestion',
            name='editable',
            field=models.CharField(blank=True, default='c,s,r,a',
                                   help_text='This field can be edited by the participant only when the character is in one of the selected statuses',
                                   max_length=20, null=True, verbose_name='Editable'),
        ),
        migrations.RunPython(set_editable_all_statuses, migrations.RunPython.noop),
    ]
