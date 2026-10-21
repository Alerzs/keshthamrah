import django.db.models.deletion
from django.db import migrations, models


def copy_farmer_from_booking(apps, schema_editor):
    Review = apps.get_model('marketplace', 'Review')
    Booking = apps.get_model('marketplace', 'Booking')
    farmer_by_booking = dict(Booking.objects.values_list('id', 'farmer_id'))
    for review in Review.objects.all().iterator():
        farmer_id = farmer_by_booking.get(review.booking_id)
        if farmer_id:
            review.farmer_id = farmer_id
            review.save(update_fields=['farmer'])
    Review.objects.filter(farmer__isnull=True).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('marketplace', '0005_booking_admin_approval'),
    ]

    operations = [
        migrations.AddField(
            model_name='review',
            name='farmer',
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='reviews',
                to='marketplace.user',
                verbose_name='صاحب زمین',
            ),
        ),
        migrations.RunPython(copy_farmer_from_booking, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='review',
            name='farmer',
            field=models.ForeignKey(
                limit_choices_to={'profile__role': 'farmer'},
                on_delete=django.db.models.deletion.CASCADE,
                related_name='reviews',
                to='marketplace.user',
                verbose_name='صاحب زمین',
            ),
        ),
        migrations.RemoveField(
            model_name='review',
            name='author_name',
        ),
    ]
