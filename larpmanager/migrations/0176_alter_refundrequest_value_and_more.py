import django.core.validators
from decimal import Decimal
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('larpmanager', '0175_rename_demo_association_lite_mode'),
    ]

    operations = [
        migrations.AlterField(
            model_name='refundrequest',
            name='value',
            field=models.DecimalField(decimal_places=2, default=0, help_text='Indicates the amount of reimbursement desired', max_digits=10, validators=[django.core.validators.MinValueValidator(Decimal('0.01'))], verbose_name='Refund'),
        ),
        migrations.AddConstraint(
            model_name='membership',
            constraint=models.UniqueConstraint(condition=models.Q(('card_number__isnull', False), ('deleted', None)), fields=('association', 'card_number'), name='unique_membership_card_number'),
        ),
    ]
