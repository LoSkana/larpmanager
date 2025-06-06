# Generated by Django 5.2 on 2025-05-11 15:18

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("larpmanager", "0001_initial"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="character",
            name="concept",
        ),
        migrations.RemoveField(
            model_name="character",
            name="gender",
        ),
        migrations.RemoveField(
            model_name="character",
            name="keywords",
        ),
        migrations.RemoveField(
            model_name="character",
            name="motto",
        ),
        migrations.RemoveField(
            model_name="character",
            name="role",
        ),
        migrations.RemoveField(
            model_name="character",
            name="safety",
        ),
        migrations.RemoveField(
            model_name="character",
            name="special",
        ),
        migrations.RemoveField(
            model_name="faction",
            name="concept",
        ),
        migrations.RemoveField(
            model_name="handout",
            name="concept",
        ),
        migrations.RemoveField(
            model_name="plot",
            name="concept",
        ),
        migrations.RemoveField(
            model_name="prologue",
            name="concept",
        ),
        migrations.RemoveField(
            model_name="prologuetype",
            name="concept",
        ),
        migrations.RemoveField(
            model_name="quest",
            name="concept",
        ),
        migrations.RemoveField(
            model_name="questtype",
            name="concept",
        ),
        migrations.RemoveField(
            model_name="speedlarp",
            name="concept",
        ),
        migrations.RemoveField(
            model_name="textversion",
            name="concept",
        ),
        migrations.RemoveField(
            model_name="trait",
            name="concept",
        ),
        migrations.RemoveField(
            model_name="trait",
            name="gender",
        ),
        migrations.AlterField(
            model_name="characterquestion",
            name="typ",
            field=models.CharField(
                choices=[
                    ("s", "Single choice"),
                    ("m", "Multiple choice"),
                    ("t", "Text (short)"),
                    ("p", "Text (long)"),
                    ("name", "Name"),
                    ("teaser", "Presentation"),
                    ("text", "Sheet"),
                    ("cover", "Cover"),
                    ("faction", "Factions"),
                    ("title", "Title"),
                    ("mirror", "Mirror"),
                    ("props", "Prop"),
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
            model_name="registrationquestion",
            name="typ",
            field=models.CharField(
                choices=[
                    ("s", "Single choice"),
                    ("m", "Multiple choice"),
                    ("t", "Text (short)"),
                    ("p", "Text (long)"),
                    ("name", "Name"),
                    ("teaser", "Presentation"),
                    ("text", "Sheet"),
                    ("cover", "Cover"),
                    ("faction", "Factions"),
                    ("title", "Title"),
                    ("mirror", "Mirror"),
                    ("props", "Prop"),
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
