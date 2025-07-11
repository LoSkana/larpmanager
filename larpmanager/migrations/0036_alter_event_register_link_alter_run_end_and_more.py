# Generated by Django 5.2.3 on 2025-07-10 09:27

from django.db import migrations, models

import larpmanager.models.utils


class Migration(migrations.Migration):
    dependencies = [
        ("larpmanager", "0035_remove_event_lang_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="event",
            name="register_link",
            field=models.URLField(
                blank=True,
                help_text="Insert the link to an external tool where users will be redirected if they are not yet registered. Registered users will be granted normal access",
                max_length=150,
                verbose_name="External register link",
            ),
        ),
        migrations.AlterField(
            model_name="run",
            name="end",
            field=models.DateField(blank=True, null=True, verbose_name="End date"),
        ),
        migrations.AlterField(
            model_name="run",
            name="registration_open",
            field=models.DateTimeField(
                blank=True,
                help_text="Enter the date and time when registrations open - leave blank to keep registrations closed",
                null=True,
                verbose_name="Registration opening date",
            ),
        ),
        migrations.AlterField(
            model_name="run",
            name="registration_secret",
            field=models.CharField(
                db_index=True,
                default=larpmanager.models.utils.my_uuid_short,
                help_text="This code is used to generate the secret registration link, you may keep the default or customize it",
                max_length=12,
                unique=True,
                verbose_name="Secret code",
            ),
        ),
        migrations.AlterField(
            model_name="run",
            name="start",
            field=models.DateField(blank=True, null=True, verbose_name="Start date"),
        ),
    ]
