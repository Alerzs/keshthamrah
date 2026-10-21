import django.db.models.deletion
from django.db import migrations, models


def fill_user_names(apps, schema_editor):
    User = apps.get_model('marketplace', 'User')
    for user in User.objects.all():
        full_name = f'{user.first_name} {user.last_name}'.strip()
        if full_name and not (user.name or '').strip():
            user.name = full_name
            user.save(update_fields=['name'])


def copy_worker_users(apps, schema_editor):
    WorkerProfile = apps.get_model('marketplace', 'WorkerProfile')
    Profile = apps.get_model('marketplace', 'Profile')
    user_ids = dict(Profile.objects.values_list('id', 'user_id'))
    for worker in WorkerProfile.objects.all():
        worker.user_id = user_ids[worker.profile_id]
        worker.save(update_fields=['user_id'])


class Migration(migrations.Migration):

    dependencies = [
        ('marketplace', '0003_profile_farm_location'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='name',
            field=models.CharField(blank=True, default='', max_length=150, verbose_name='نام'),
            preserve_default=False,
        ),
        migrations.RunPython(fill_user_names, migrations.RunPython.noop),
        migrations.AlterModelOptions(
            name='workerprofile',
            options={'ordering': ['-rating', '-jobs_done'], 'verbose_name': 'پروفایل باغبان', 'verbose_name_plural': 'پروفایل باغبانان'},
        ),
        migrations.AlterField(
            model_name='booking',
            name='worker',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='jobs', to='marketplace.workerprofile', verbose_name='باغبان'),
        ),
        migrations.AlterField(
            model_name='profile',
            name='role',
            field=models.CharField(choices=[('farmer', 'صاحب زمین'), ('worker', 'باغبان'), ('admin', 'ادمین')], max_length=10, verbose_name='نقش'),
        ),
        migrations.AddField(
            model_name='workerprofile',
            name='user',
            field=models.OneToOneField(
                blank=True, null=True, on_delete=django.db.models.deletion.CASCADE,
                related_name='worker', to='marketplace.User', verbose_name='کاربر',
            ),
        ),
        migrations.RunPython(copy_worker_users, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='workerprofile',
            name='user',
            field=models.OneToOneField(
                on_delete=django.db.models.deletion.CASCADE, related_name='worker',
                to='marketplace.User', verbose_name='کاربر',
            ),
        ),
        migrations.RemoveField(
            model_name='workerprofile',
            name='profile',
        ),
    ]
