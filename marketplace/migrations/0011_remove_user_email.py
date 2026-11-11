import django.db.models.deletion
from django.db import migrations, models


def clear_non_admin_creators(apps, schema_editor):
    User = apps.get_model('marketplace', 'User')
    (
        User.objects.exclude(created_by=None)
        .exclude(created_by__role='admin')
        .update(created_by=None)
    )


class Migration(migrations.Migration):

    dependencies = [
        ('marketplace', '0010_user_single_name'),
    ]

    operations = [
        migrations.RunPython(clear_non_admin_creators, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name='user',
            name='email',
        ),
        migrations.AlterField(
            model_name='user',
            name='created_by',
            field=models.ForeignKey(
                blank=True,
                limit_choices_to={'role': 'admin'},
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='created_accounts',
                to='marketplace.user',
                verbose_name='ثبت‌کننده',
            ),
        ),
    ]
