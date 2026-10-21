import django.db.models.deletion
from django.db import migrations, models


def open_existing_jobs_to_workers(apps, schema_editor):
    Booking = apps.get_model('marketplace', 'Booking')
    Booking.objects.filter(status='reported').update(status='confirmed')
    Booking.objects.exclude(status='pending').update(admin_approved=True)


class Migration(migrations.Migration):

    dependencies = [
        ('marketplace', '0004_user_name_and_worker_user'),
    ]

    operations = [
        migrations.AddField(
            model_name='booking',
            name='admin_approved',
            field=models.BooleanField(default=False, verbose_name='صلاحیت تأیید شده'),
        ),
        migrations.AlterField(
            model_name='booking',
            name='confirmed_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='زمان بررسی صلاحیت'),
        ),
        migrations.AlterField(
            model_name='booking',
            name='confirmed_by',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='approved_jobs',
                to='marketplace.user',
                verbose_name='ادمین بررسی‌کننده',
            ),
        ),
        migrations.RunPython(open_existing_jobs_to_workers, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='booking',
            name='status',
            field=models.CharField(
                choices=[
                    ('pending', 'در انتظار پذیرش'),
                    ('confirmed', 'پذیرفته شده'),
                    ('rejected', 'رد شده'),
                    ('cancelled', 'لغو شده'),
                    ('done', 'انجام شده'),
                ],
                default='pending',
                max_length=12,
                verbose_name='وضعیت',
            ),
        ),
    ]
