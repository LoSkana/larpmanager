# Generated by Django 5.2.3 on 2025-07-14 13:58

import django.db.models.deletion
from django.db import migrations, models

import larpmanager.models.utils


class Migration(migrations.Migration):
    dependencies = [
        ("larpmanager", "0037_assocpermission_hidden_eventpermission_hidden"),
    ]

    operations = [
        migrations.AlterField(
            model_name="event",
            name="background",
            field=models.ImageField(
                blank=True,
                help_text="Background image used across all event pages",
                max_length=500,
                upload_to="event_background/",
                verbose_name="Background image",
            ),
        ),
        migrations.AlterField(
            model_name="event",
            name="cover",
            field=models.ImageField(
                blank=True,
                help_text="Cover image shown on the organization's homepage — rectangular, ideally 4:3 ratio",
                max_length=500,
                upload_to="cover/",
            ),
        ),
        migrations.AlterField(
            model_name="event",
            name="font",
            field=models.FileField(
                blank=True,
                help_text="Font used for title texts across all event pages",
                null=True,
                upload_to=larpmanager.models.utils.UploadToPathAndRename("event_font/"),
                verbose_name="Title font",
            ),
        ),
        migrations.AlterField(
            model_name="event",
            name="max_filler",
            field=models.IntegerField(
                default=0, help_text="Maximum number of filler spots (0 = unlimited)", verbose_name="Max fillers"
            ),
        ),
        migrations.AlterField(
            model_name="event",
            name="max_pg",
            field=models.IntegerField(
                default=0, help_text="Maximum number of player spots (0 = unlimited)", verbose_name="Max players"
            ),
        ),
        migrations.AlterField(
            model_name="event",
            name="max_waiting",
            field=models.IntegerField(
                default=0, help_text="Maximum number of waiting spots (0 = unlimited)", verbose_name="Max waitings"
            ),
        ),
        migrations.AlterField(
            model_name="event",
            name="parent",
            field=models.ForeignKey(
                blank=True,
                help_text="If you select another event, it will be considered in the same campaign, and they will share the characters - if you leave this empty, this can be the starting event of a new campaign",
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                to="larpmanager.event",
                verbose_name="Campaign",
            ),
        ),
        migrations.AlterField(
            model_name="registrationoption",
            name="max_available",
            field=models.IntegerField(
                default=0,
                help_text="Indicates the maximum number of times it can be requested (0 = unlimited)",
                verbose_name="Maximum number",
            ),
        ),
        migrations.AlterField(
            model_name="registrationticket",
            name="max_available",
            field=models.IntegerField(default=0, help_text="Maximum number of tickets available (0 = unlimited)"),
        ),
        migrations.AlterField(
            model_name="writingoption",
            name="max_available",
            field=models.IntegerField(
                default=0, help_text="Indicates the maximum number of times it can be requested (0 = unlimited)"
            ),
        ),
    ]
