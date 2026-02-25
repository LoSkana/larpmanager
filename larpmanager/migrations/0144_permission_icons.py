from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('larpmanager', '0143_feature_dependencies'),
    ]

    operations = [
        migrations.AddField(
            model_name='associationpermission',
            name='icon',
            field=models.CharField(blank=True, default='', max_length=100),
        ),
        migrations.AddField(
            model_name='eventpermission',
            name='icon',
            field=models.CharField(blank=True, default='', max_length=100),
        ),
    ]
