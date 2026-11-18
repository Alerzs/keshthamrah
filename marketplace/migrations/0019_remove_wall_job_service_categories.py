from django.db import migrations


def remove_categories(apps, schema_editor):
    WallCategory = apps.get_model('marketplace', 'WallCategory')
    WallAd = apps.get_model('marketplace', 'WallAd')
    categories = WallCategory.objects.filter(slug__in=('jobs', 'services'))
    WallAd.objects.filter(category__in=categories).delete()
    categories.delete()


class Migration(migrations.Migration):

    dependencies = [
        ('marketplace', '0018_wall_ads'),
    ]

    operations = [
        migrations.RunPython(remove_categories, migrations.RunPython.noop),
    ]
