import django.core.validators
import django.db.models.deletion
from django.db import migrations, models


def copy_legacy_accounts(apps, schema_editor):
    User = apps.get_model('marketplace', 'User')
    Profile = apps.get_model('marketplace', 'Profile')
    WorkerProfile = apps.get_model('marketplace', 'WorkerProfile')
    Booking = apps.get_model('marketplace', 'Booking')
    Review = apps.get_model('marketplace', 'Review')

    for profile in Profile.objects.all():
        User.objects.filter(pk=profile.user_id).update(
            role=profile.role or '',
            phone=profile.phone or '',
            farm_city_id=profile.farm_city_id,
            farm_address=profile.farm_address or '',
            farm_latitude=profile.farm_latitude,
            farm_longitude=profile.farm_longitude,
            created_by_id=profile.created_by_id,
        )

    for worker in WorkerProfile.objects.all():
        user = User.objects.get(pk=worker.user_id)
        user.bio = worker.bio or ''
        user.experience_years = worker.experience_years
        user.daily_wage = worker.daily_wage
        user.rating = worker.rating
        user.review_count = worker.review_count
        user.jobs_done = worker.jobs_done
        user.is_verified = worker.is_verified
        user.accepts_jobs = worker.is_active
        user.save()
        user.services.set(worker.services.values_list('pk', flat=True))
        user.cities.set(worker.cities.values_list('pk', flat=True))

    worker_users = dict(WorkerProfile.objects.values_list('id', 'user_id'))
    for booking in Booking.objects.all():
        booking.worker_user_id = worker_users[booking.worker_id]
        booking.save(update_fields=['worker_user_id'])
    for review in Review.objects.all():
        review.worker_user_id = worker_users[review.worker_id]
        review.save(update_fields=['worker_user_id'])


class Migration(migrations.Migration):

    dependencies = [
        ('marketplace', '0008_profile_created_by'),
    ]

    operations = [
        migrations.AlterField(
            model_name='profile',
            name='farm_city',
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name='legacy_farmers', to='marketplace.city', verbose_name='شهر زمین',
            ),
        ),
        migrations.AlterField(
            model_name='profile',
            name='created_by',
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name='legacy_created_accounts', to='marketplace.user', verbose_name='ثبت‌کننده',
            ),
        ),
        migrations.AlterField(
            model_name='workerprofile',
            name='services',
            field=models.ManyToManyField(
                blank=True, related_name='legacy_service_workers', to='marketplace.service',
                verbose_name='حوزه کاری',
            ),
        ),
        migrations.AlterField(
            model_name='workerprofile',
            name='cities',
            field=models.ManyToManyField(
                blank=True, related_name='legacy_city_workers', to='marketplace.city',
                verbose_name='محل کار',
            ),
        ),
        migrations.AlterField(
            model_name='review',
            name='farmer',
            field=models.ForeignKey(
                limit_choices_to={'role': 'farmer'},
                on_delete=django.db.models.deletion.CASCADE,
                related_name='given_reviews',
                to='marketplace.user',
                verbose_name='صاحب زمین',
            ),
        ),
        migrations.AddField(
            model_name='user',
            name='role',
            field=models.CharField(
                blank=True,
                choices=[('farmer', 'صاحب زمین'), ('worker', 'سرویس دهنده'), ('admin', 'ادمین')],
                default='',
                max_length=10,
                verbose_name='نقش',
            ),
        ),
        migrations.AddField(
            model_name='user',
            name='phone',
            field=models.CharField(blank=True, default='', max_length=11, verbose_name='موبایل'),
        ),
        migrations.AddField(
            model_name='user',
            name='farm_address',
            field=models.CharField(blank=True, default='', max_length=255, verbose_name='آدرس زمین'),
        ),
        migrations.AddField(
            model_name='user',
            name='farm_latitude',
            field=models.DecimalField(
                blank=True, decimal_places=6, max_digits=9, null=True, verbose_name='عرض جغرافیایی زمین',
            ),
        ),
        migrations.AddField(
            model_name='user',
            name='farm_longitude',
            field=models.DecimalField(
                blank=True, decimal_places=6, max_digits=9, null=True, verbose_name='طول جغرافیایی زمین',
            ),
        ),
        migrations.AddField(
            model_name='user',
            name='farm_city',
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name='farmers', to='marketplace.city', verbose_name='شهر زمین',
            ),
        ),
        migrations.AddField(
            model_name='user',
            name='created_by',
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name='created_accounts', to='marketplace.user', verbose_name='ثبت‌کننده',
            ),
        ),
        migrations.AddField(
            model_name='user',
            name='bio',
            field=models.TextField(blank=True, default='', verbose_name='درباره تجربه کاری'),
        ),
        migrations.AddField(
            model_name='user',
            name='experience_years',
            field=models.PositiveSmallIntegerField(
                default=0,
                validators=[django.core.validators.MaxValueValidator(60)],
                verbose_name='سابقه (سال)',
            ),
        ),
        migrations.AddField(
            model_name='user',
            name='daily_wage',
            field=models.PositiveIntegerField(default=0, verbose_name='دستمزد روزانه (تومان)'),
        ),
        migrations.AddField(
            model_name='user',
            name='rating',
            field=models.DecimalField(decimal_places=1, default=0, max_digits=2, verbose_name='امتیاز'),
        ),
        migrations.AddField(
            model_name='user',
            name='review_count',
            field=models.PositiveIntegerField(default=0, verbose_name='تعداد نظر'),
        ),
        migrations.AddField(
            model_name='user',
            name='jobs_done',
            field=models.PositiveIntegerField(default=0, verbose_name='کارهای انجام‌شده'),
        ),
        migrations.AddField(
            model_name='user',
            name='is_verified',
            field=models.BooleanField(default=False, verbose_name='هویت تأیید شده'),
        ),
        migrations.AddField(
            model_name='user',
            name='accepts_jobs',
            field=models.BooleanField(default=True, verbose_name='آماده دریافت کار'),
        ),
        migrations.AddField(
            model_name='user',
            name='services',
            field=models.ManyToManyField(
                blank=True, related_name='workers', to='marketplace.service', verbose_name='حوزه کاری',
            ),
        ),
        migrations.AddField(
            model_name='user',
            name='cities',
            field=models.ManyToManyField(
                blank=True, related_name='workers', to='marketplace.city', verbose_name='محل کار',
            ),
        ),
        migrations.AddField(
            model_name='booking',
            name='worker_user',
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.CASCADE,
                related_name='booked_jobs', to='marketplace.user', verbose_name='سرویس دهنده',
            ),
        ),
        migrations.AddField(
            model_name='review',
            name='worker_user',
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.CASCADE,
                related_name='reviews', to='marketplace.user', verbose_name='سرویس دهنده',
            ),
        ),
        migrations.RunPython(copy_legacy_accounts, migrations.RunPython.noop),
        migrations.RemoveField(model_name='booking', name='worker'),
        migrations.RemoveField(model_name='review', name='worker'),
        migrations.RenameField(model_name='booking', old_name='worker_user', new_name='worker'),
        migrations.RenameField(model_name='review', old_name='worker_user', new_name='worker'),
        migrations.AlterField(
            model_name='booking',
            name='worker',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='jobs',
                to='marketplace.user',
                verbose_name='سرویس دهنده',
            ),
        ),
        migrations.AlterField(
            model_name='review',
            name='worker',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='reviews',
                to='marketplace.user',
                verbose_name='سرویس دهنده',
            ),
        ),
        migrations.DeleteModel(name='WorkerProfile'),
        migrations.DeleteModel(name='Profile'),
        migrations.AlterField(
            model_name='category',
            name='icon_bg',
            field=models.CharField(default='bg-teal-50 text-soil', max_length=80),
        ),
    ]
