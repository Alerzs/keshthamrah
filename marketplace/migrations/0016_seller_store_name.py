from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('marketplace', '0015_seller_and_products'),
    ]

    operations = [
        migrations.AddField(
            model_name='seller',
            name='store_name',
            field=models.CharField(default='', max_length=80, verbose_name='نام فروشگاه'),
            preserve_default=False,
        ),
    ]
