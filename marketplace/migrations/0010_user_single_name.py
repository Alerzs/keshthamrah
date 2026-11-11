from django.db import migrations


def merge_names(apps, schema_editor):
    User = apps.get_model('marketplace', 'User')
    for user in User.objects.all().iterator():
        stored = (user.name or '').strip()
        combined = f'{(user.first_name or "").strip()} {(user.last_name or "").strip()}'.strip()
        if not stored:
            merged = combined
        elif not combined or combined == stored or combined in stored:
            merged = stored
        elif stored in combined:
            merged = combined
        else:
            merged = stored
        if merged != (user.name or ''):
            user.name = merged
            user.save(update_fields=['name'])


class Migration(migrations.Migration):

    dependencies = [
        ('marketplace', '0009_merge_user_profiles'),
    ]

    operations = [
        migrations.RunPython(merge_names, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name='user',
            name='first_name',
        ),
        migrations.RemoveField(
            model_name='user',
            name='last_name',
        ),
    ]
