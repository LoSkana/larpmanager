# Generated by Django 5.2.3 on 2025-06-17 18:39

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("larpmanager", "0024_alter_association_profile"),
    ]

    operations = [
        migrations.DeleteModel(
            name="LarpManagerHowto",
        ),
        migrations.RemoveField(
            model_name="feature",
            name="link",
        ),
    ]
