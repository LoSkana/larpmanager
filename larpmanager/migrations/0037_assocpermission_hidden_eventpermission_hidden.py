# Generated by Django 5.2.3 on 2025-07-14 09:37

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("larpmanager", "0036_alter_event_register_link_alter_run_end_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="assocpermission",
            name="hidden",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="eventpermission",
            name="hidden",
            field=models.BooleanField(default=False),
        ),
    ]
