from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('marketplace', '0006_review_farmer'),
    ]

    operations = [
        migrations.AddField(
            model_name='booking',
            name='rejection_reason',
            field=models.TextField(blank=True, default='', verbose_name='علت رد'),
        ),
    ]
