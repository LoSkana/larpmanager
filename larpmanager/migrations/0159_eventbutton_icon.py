from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('larpmanager', '0158_add_icon_to_larpmanager_guide'),
    ]

    operations = [
        migrations.AddField(
            model_name='eventbutton',
            name='icon',
            field=models.CharField(blank=True, default='', max_length=50),
        ),
    ]
