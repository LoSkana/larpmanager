import django.core.validators
import django.db.models.deletion
import larpmanager.models.utils
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('larpmanager', '0181_registration_question_applicable'),
    ]

    operations = [
        migrations.AddField(
            model_name='registration',
            name='pending',
            field=models.BooleanField(default=False),
        ),
        migrations.AddIndex(
            model_name='registration',
            index=models.Index(condition=models.Q(('pending', True)), fields=['run', 'pending'], name='reg_run_pending_idx'),
        ),
        migrations.AlterField(
            model_name='registrationquestion',
            name='applicable',
            field=models.CharField(choices=[('r', 'registration'), ('m', 'matchmaker'), ('q', 'request')], default='r', help_text='Select which form this question belongs to', max_length=1, verbose_name='Applicable'),
        ),
        migrations.AlterField(
            model_name='eventtext',
            name='typ',
            field=models.CharField(choices=[('i', 'Character sheet intro'), ('t', 'Terms and conditions'), ('r', 'Registration form'), ('s', 'Search'), ('g', 'Registration mail'), ('a', 'Mail assignment'), ('c', "Player's character form"), ('cs', 'Proposed character'), ('ca', 'Approved character'), ('cr', 'Character review'), ('ra', 'Registration approval request')], max_length=2, verbose_name='Type'),
        ),
        migrations.AlterField(
            model_name='associationtext',
            name='typ',
            field=models.CharField(choices=[('p', 'Profile'), ('h', 'Calendar'), ('u', 'Registration mail'), ('m', 'Membership request'), ('s', 'Statute'), ('l', 'Legal notice'), ('f', 'Footer'), ('t', 'Terms and Conditions'), ('r', 'Receipt'), ('g', 'Mail signature'), ('y', 'Privacy'), ('rm', 'Reminder membership request'), ('rf', 'Reminder membership fee'), ('rp', 'Reminder payment'), ('rr', 'Reminder profile')], help_text='Type of text', max_length=2, verbose_name='Type'),
        ),
        migrations.AlterField(
            model_name='collection',
            name='status',
            field=models.CharField(choices=[('o', 'Open'), ('d', 'Closed'), ('p', 'Delivered')], default='o', max_length=1),
        ),
        migrations.AlterField(
            model_name='emailrecipient',
            name='sent',
            field=models.DateTimeField(blank=True, null=True, verbose_name='Time And Date Of Sending'),
        ),
        migrations.AlterField(
            model_name='event',
            name='max_filler',
            field=models.IntegerField(default=0, help_text='Maximum number of reserve character slots available (set to 0 for unlimited)', validators=[django.core.validators.MinValueValidator(0)], verbose_name='Maximum reserves'),
        ),
        migrations.AlterField(
            model_name='event',
            name='parent',
            field=models.ForeignKey(blank=True, help_text='Selecting an event joins its campaign and shares characters with it (leave empty to start a new campaign)', null=True, on_delete=django.db.models.deletion.CASCADE, to='larpmanager.event', verbose_name='Parent campaign'),
        ),
        migrations.AlterField(
            model_name='member',
            name='newsletter',
            field=models.CharField(choices=[('a', 'Yes, keep me posted!'), ('o', 'Only really important communications'), ('n', "No, I don't want updates")], default='a', help_text='Would you like to receive updates about our upcoming events?', max_length=1, null=True, verbose_name='Newsletter'),
        ),
        migrations.AlterField(
            model_name='membership',
            name='status',
            field=models.CharField(choices=[('e', 'Inactive (E)'), ('j', 'Inactive (J)'), ('u', 'Inactive (U)'), ('s', 'Review'), ('a', 'Accepted'), ('r', 'Removed')], db_index=True, default='e', help_text='Current status of the membership application and approval process', max_length=1, verbose_name='Membership status'),
        ),
        migrations.AlterField(
            model_name='notificationqueue',
            name='notification_type',
            field=models.CharField(choices=[('registration_new', 'New Registration'), ('registration_update', 'Updated Registration'), ('registration_cancel', 'Cancelled Registration'), ('registration_request_new', 'New Signup Request'), ('payment_money', 'Money Payment'), ('payment_credit', 'Credit Payment'), ('payment_token', 'Token Payment'), ('invoice_approval', 'Invoice Awaiting Approval'), ('help_question', 'Help Question'), ('password_reminder', 'Password Reminder'), ('refund_request', 'Refund Request'), ('invoice_approval_exe', 'Invoice Approval (Executive)')], max_length=30),
        ),
        migrations.AlterField(
            model_name='onetimeaccesstoken',
            name='used_at',
            field=models.DateTimeField(blank=True, help_text='When this token was used', null=True, verbose_name='Time And Date Of Use'),
        ),
        migrations.AlterField(
            model_name='onetimeaccesstoken',
            name='used_by',
            field=models.ForeignKey(blank=True, help_text='Member who used this token (if authenticated)', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='used_onetime_tokens', to='larpmanager.member', verbose_name='User'),
        ),
        migrations.AlterField(
            model_name='paymentinvoice',
            name='invoice',
            field=models.FileField(blank=True, help_text='Statement issued by the bank as proof of the issuance of the transfer (as pdf file)', null=True, upload_to=larpmanager.models.utils.UploadToPathAndRename('wire/'), verbose_name='Bank Statement'),
        ),
        migrations.AlterField(
            model_name='problem',
            name='assigned',
            field=models.CharField(max_length=100),
        ),
        migrations.AlterField(
            model_name='problem',
            name='severity',
            field=models.CharField(choices=[('r', '1 - RED'), ('o', '2 - ORANGE'), ('y', '3 - YELLOW'), ('g', '4 - GREEN')], default='g', max_length=1, verbose_name='Severity'),
        ),
        migrations.AlterField(
            model_name='problem',
            name='status',
            field=models.CharField(choices=[('o', '1 - OPEN'), ('w', '2 - WORKING'), ('c', '3 - CLOSED')], db_index=True, default='o', max_length=1, verbose_name='Status'),
        ),
        migrations.AlterField(
            model_name='problem',
            name='what',
            field=models.TextField(verbose_name='What'),
        ),
        migrations.AlterField(
            model_name='problem',
            name='when',
            field=models.TextField(verbose_name='When'),
        ),
        migrations.AlterField(
            model_name='problem',
            name='where',
            field=models.TextField(verbose_name='Where'),
        ),
        migrations.AlterField(
            model_name='problem',
            name='who',
            field=models.TextField(verbose_name='Who'),
        ),
        migrations.AlterField(
            model_name='registrationquestion',
            name='typ',
            field=models.CharField(choices=[('s', 'Single choice'), ('m', 'Multiple choice'), ('t', 'Single-line text'), ('p', 'Multi-line text'), ('e', 'Advanced text editor'), ('ticket', 'Ticket'), ('additional_tickets', 'Additional'), ('pay_what_you_want', 'Pay what you want'), ('reg_quotas', 'Installments'), ('reg_surcharges', 'Surcharge'), ('faction_preference', 'Faction preference')], default='s', help_text='Question type', max_length=50, verbose_name='Type'),
        ),
        migrations.AlterField(
            model_name='registrationticket',
            name='tier',
            field=models.CharField(choices=[('b', 'Standard'), ('y', 'New player'), ('l', 'Lottery'), ('w', 'Waiting'), ('f', 'Reserve'), ('r', 'Reduced'), ('p', 'Patron'), ('t', 'Staff'), ('n', 'NPC'), ('c', 'Collaborator'), ('s', 'Seller')], default='b', help_text='Type of ticket', max_length=1, verbose_name='Tier'),
        ),
        migrations.AlterField(
            model_name='writingquestion',
            name='typ',
            field=models.CharField(choices=[('s', 'Single choice'), ('m', 'Multiple choice'), ('t', 'Single-line text'), ('p', 'Multi-line text'), ('e', 'Advanced text editor'), ('name', 'Name'), ('teaser', 'Presentation'), ('text', 'Sheet'), ('cover', 'Cover'), ('faction', 'Factions'), ('title', 'Title'), ('mirror', 'Mirror'), ('hide', 'Hide'), ('locked', 'Locked'), ('progress', 'Progress'), ('assigned', 'Assignment'), ('c', 'Computed')], default='s', help_text='Question type', max_length=10, verbose_name='Type'),
        ),
    ]
