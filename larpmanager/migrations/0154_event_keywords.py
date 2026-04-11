from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("larpmanager", "0153_systemexp_hidden"),
    ]

    operations = [
        migrations.RenameField(
            model_name="event",
            old_name="genre",
            new_name="keywords",
        ),
    ]
