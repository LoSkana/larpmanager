from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('larpmanager', '0157_alter_member_gender_alter_member_legal_name_config'),
    ]

    operations = [
        migrations.AddField(
            model_name='eventbutton',
            name='icon',
            field=models.CharField(blank=True, default='', max_length=50),
        ),
    ]
