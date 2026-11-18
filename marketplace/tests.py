from datetime import timedelta
from decimal import Decimal
from pathlib import Path

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from marketplace.models import (
    AdminAccount, Booking, City, LandOwner, Product, Review, Seller, Service, ServiceProvider, WallAd, WallCategory,
)

User = get_user_model()


class MarketplaceFlowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('seed')

    def test_home_lists_services(self):
        response = self.client.get(reverse('home'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'کشت همراه')
        self.assertContains(response, 'برداشت گندم و جو')
        self.assertContains(response, reverse('services'))

    def test_suggests_workers_by_service_and_city(self):
        city = City.objects.get(name='مشهد')
        response = self.client.get(reverse('workers'), {'service': 'wheat-harvest', 'city': city.pk})
        self.assertContains(response, 'رضا محمدی')
        self.assertContains(response, 'مجید کاظمی')
        self.assertNotContains(response, 'حسین کریمی')

    def test_order_form_redirects_to_matching_workers(self):
        city = City.objects.get(name='شیراز')
        response = self.client.post(reverse('order', args=['spraying']), {
            'city': city.pk,
            'address': 'جاده مرودشت، قطعه جنوبی باغ',
            'work_date': (timezone.localdate() + timedelta(days=2)).isoformat(),
            'land_area': '1.5',
            'note': 'سمپاشی مرکبات',
        })
        self.assertEqual(response.status_code, 302)
        self.assertIn('/workers/', response['Location'])
        self.assertIn('service=spraying', response['Location'])

    def test_saved_farm_city_and_address_stay_fixed_on_a_request(self):
        from urllib.parse import unquote_plus

        self.client.login(username='09121111111', password='demo1234')
        editable = self.client.get(reverse('order', args=['wheat-harvest']))
        self.assertFalse(editable.context['form'].fields['city'].disabled)
        self.assertNotContains(editable, 'عوض نمی‌شود')

        mashhad = City.objects.get(name='مشهد')
        shiraz = City.objects.get(name='شیراز')
        profile = User.objects.get(username='09121111111')
        profile.farm_city = mashhad
        profile.farm_address = 'جاده کلات، کیلومتر ۱۲، قطعه نمونه'
        profile.save()
        order = self.client.get(reverse('order', args=['wheat-harvest']))
        self.assertTrue(order.context['form'].fields['city'].disabled)
        self.assertTrue(order.context['form'].fields['address'].disabled)
        self.assertContains(order, 'جاده کلات، کیلومتر ۱۲، قطعه نمونه')
        self.assertContains(order, 'عوض نمی‌شود')
        posted = self.client.post(reverse('order', args=['wheat-harvest']), {
            'city': shiraz.pk,
            'address': 'آدرس جعلی در شیراز برای دور زدن',
            'work_date': (timezone.localdate() + timedelta(days=2)).isoformat(),
        })
        location = unquote_plus(posted['Location'])
        self.assertIn(f'city={mashhad.pk}', location)
        self.assertNotIn(f'city={shiraz.pk}', location)
        self.assertIn(profile.farm_address, location)

        listing = self.client.get(reverse('workers'), {
            'service': 'wheat-harvest',
            'city': shiraz.pk,
            'address': 'آدرس جعلی در شیراز برای دور زدن',
        })
        self.assertContains(listing, 'disabled')
        self.assertContains(listing, 'مشهد')
        self.assertContains(listing, profile.farm_address)
        self.assertNotContains(listing, 'حسین کریمی')

        worker = User.objects.get(username='09130000001')
        service = Service.objects.get(slug='wheat-harvest')
        booked = self.client.post(reverse('book', args=[worker.pk]), {
            'service': service.pk,
            'city': shiraz.pk,
            'address': 'آدرس جعلی در شیراز برای دور زدن',
            'work_date': (timezone.localdate() + timedelta(days=3)).isoformat(),
        })
        self.assertRedirects(booked, reverse('bookings'))
        booking = Booking.objects.get()
        self.assertEqual(booking.city, mashhad)
        self.assertEqual(booking.address, profile.farm_address)

    def test_farmer_can_book_matching_worker(self):
        self.client.login(username='09121111111', password='demo1234')
        city = City.objects.get(name='مشهد')
        profile = User.objects.get(username='09121111111')
        profile.farm_city = city
        profile.farm_address = 'جاده کلات، کیلومتر ۱۲، قطعه نمونه'
        profile.save()
        service = Service.objects.get(slug='wheat-harvest')
        worker = User.objects.get(username='09130000001')
        response = self.client.post(reverse('book', args=[worker.pk]), {
            'service': service.pk,
            'city': city.pk,
            'address': 'جاده کلات، کیلومتر ۱۲',
            'work_date': (timezone.localdate() + timedelta(days=3)).isoformat(),
            'land_area': '2.5',
            'note': 'برداشت قطعه شمالی',
        })
        self.assertRedirects(response, reverse('bookings'))
        booking = Booking.objects.get()
        self.assertEqual(booking.status, Booking.PENDING)
        self.assertFalse(booking.admin_approved)
        self.assertEqual(booking.worker, worker)

    def test_admin_cannot_book_a_worker(self):
        worker = User.objects.get(username='09130000001')
        book_url = reverse('book', args=[worker.pk])
        self.client.login(username='09124444444', password='demo1234')
        detail = self.client.get(reverse('worker_detail', args=[worker.pk]))
        self.assertNotContains(detail, book_url)
        self.assertNotContains(detail, 'رزرو این سرویس دهنده')
        listing = self.client.get(reverse('workers'))
        self.assertNotContains(listing, book_url)
        category = self.client.get(reverse('category', args=['planting']))
        self.assertNotContains(category, 'انتخاب و ادامه')
        self.assertRedirects(self.client.get(reverse('order', args=['wheat-harvest'])), reverse('admin_panel'))
        self.assertRedirects(self.client.get(book_url), reverse('home'))
        self.client.logout()

        self.client.login(username='09121111111', password='demo1234')
        farmer_detail = self.client.get(reverse('worker_detail', args=[worker.pk]))
        self.assertContains(farmer_detail, 'رزرو این سرویس دهنده')

    def test_admin_panel_requests_open_on_click(self):
        self._book_sample()
        self.client.login(username='09124444444', password='demo1234')
        panel = self.client.get(reverse('admin_panel'))
        self.assertContains(panel, '<details')
        self.assertContains(panel, '<summary')
        self.assertContains(panel, 'جاده کلات، کیلومتر ۱۲')

    def test_admin_rejection_reason_is_visible_to_farmer_and_worker(self):
        booking, _worker = self._book_sample()
        self.client.login(username='09124444444', password='demo1234')
        missing = self.client.post(reverse('admin_approve', args=[booking.pk]), {
            'action': 'reject',
            'reason': '   ',
        }, follow=True)
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.PENDING)
        self.assertContains(missing, 'برای رد درخواست، علت را بنویسید.')

        reason = 'زمان درخواست با فصل کار این زمین هم‌خوان نیست'
        rejected = self.client.post(reverse('admin_approve', args=[booking.pk]), {
            'action': 'reject',
            'reason': reason,
        })
        self.assertRedirects(rejected, reverse('admin_panel'))
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.REJECTED)
        self.assertEqual(booking.rejection_reason, reason)
        self.assertFalse(booking.admin_approved)
        panel = self.client.get(reverse('admin_panel'))
        self.assertContains(panel, reason)
        self.client.logout()

        self.client.login(username='09121111111', password='demo1234')
        farmer_page = self.client.get(reverse('bookings'))
        self.assertContains(farmer_page, reason)
        self.assertContains(farmer_page, 'علت رد')
        self.client.logout()

        self.client.login(username='09130000001', password='demo1234')
        jobs = self.client.get(reverse('worker_jobs'))
        self.assertContains(jobs, reason)
        self.assertContains(jobs, 'علت رد')
        self.assertNotContains(jobs, 'جاده کلات، کیلومتر ۱۲')
        self.assertNotContains(jobs, '۰۹۱۲۱۱۱۱۱۱۱')

    def test_service_provider_without_land_is_sent_to_register_land(self):
        self.client.login(username='09130000001', password='demo1234')
        other = User.objects.get(username='09130000002')
        response = self.client.get(reverse('book', args=[other.pk]))
        self.assertRedirects(response, reverse('farmer_profile'))

    def test_service_provider_can_request_work_for_a_land(self):
        self.client.login(username='09130000001', password='demo1234')
        other = User.objects.get(username='09130000002')
        home = self.client.get(reverse('home'))
        self.assertContains(home, 'ثبت زمین')
        self.assertContains(home, 'ثبت خدمت')

        category = self.client.get(reverse('category', args=['planting']))
        self.assertContains(category, 'انتخاب و ادامه')
        self.assertContains(category, reverse('order', args=['wheat-harvest']))

        listing = self.client.get(reverse('workers'))
        self.assertContains(listing, reverse('book', args=[other.pk]))

        detail = self.client.get(reverse('worker_detail', args=[other.pk]))
        self.assertContains(detail, reverse('book', args=[other.pk]))
        self.assertContains(detail, reverse('order', args=['classic-irrigation']))

        city = City.objects.get(name='شیراز')
        response = self.client.post(reverse('order', args=['spraying']), {
            'city': city.pk,
            'address': 'جاده مرودشت، قطعه جنوبی باغ',
            'work_date': (timezone.localdate() + timedelta(days=2)).isoformat(),
            'land_area': '1.5',
            'note': 'سمپاشی برای زمین خودم',
        })
        self.assertEqual(response.status_code, 302)
        self.assertIn('/workers/', response['Location'])
        self.assertEqual(Booking.objects.count(), 0)

    def test_worker_list_renders_pages(self):
        response = self.client.get(reverse('workers'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'بعدی')

    def test_incomplete_farmer_is_sent_to_profile(self):
        self.client.login(username='09121111111', password='demo1234')
        worker = User.objects.get(username='09130000001')
        response = self.client.get(reverse('book', args=[worker.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('farmer_profile'), response['Location'])
        profile = User.objects.get(username='09121111111')
        self.assertEqual(profile.completion_percent, 50)
        response = self.client.post(reverse('farmer_profile'), {
            'farm_city': City.objects.get(name='مشهد').pk,
            'farm_address': 'جاده کلات، کیلومتر ۱۲، قطعه نمونه',
        })
        self.assertRedirects(response, reverse('home'))
        profile.refresh_from_db()
        self.assertEqual(profile.completion_percent, 100)

    def _book_sample(self):
        farmer = User.objects.get(username='09121111111')
        city = City.objects.get(name='مشهد')
        farmer.farm_city = city
        farmer.farm_address = 'جاده کلات، کیلومتر ۱۲، قطعه نمونه'
        farmer.save()
        worker_profile = User.objects.get(username='09130000001')
        self.client.login(username='09121111111', password='demo1234')
        self.client.post(reverse('book', args=[worker_profile.pk]), {
            'service': Service.objects.get(slug='wheat-harvest').pk,
            'city': city.pk,
            'address': 'جاده کلات، کیلومتر ۱۲',
            'work_date': (timezone.localdate() + timedelta(days=4)).isoformat(),
            'note': 'برداشت آزمایشی',
        })
        self.client.logout()
        return Booking.objects.get(), worker_profile

    def test_request_reaches_gardener_only_after_admin_approval(self):
        booking, worker_profile = self._book_sample()
        jobs_before = worker_profile.jobs_done

        self.client.login(username='09121111111', password='demo1234')
        farmer_page = self.client.get(reverse('bookings'))
        self.assertContains(farmer_page, 'در انتظار پذیرش')
        self.assertContains(farmer_page, 'پذیرش سرویس دهنده')
        self.assertNotContains(farmer_page, '09130000001')
        self.assertNotContains(farmer_page, 'رضا محمدی')
        self.assertNotContains(farmer_page, 'ادمین')
        self.assertNotContains(farmer_page, 'صلاحیت')
        self.client.logout()

        self.client.login(username='09130000001', password='demo1234')
        hidden = self.client.get(reverse('worker_jobs'))
        self.assertNotContains(hidden, 'جاده کلات، کیلومتر ۱۲')
        self.assertNotContains(hidden, 'ادمین')
        blocked = self.client.post(reverse('job_update', args=[booking.pk]), {'action': 'confirm'})
        self.assertEqual(blocked.status_code, 404)
        self.client.logout()

        self.client.login(username='09124444444', password='demo1234')
        panel = self.client.get(reverse('admin_panel'))
        self.assertContains(panel, 'تأیید صلاحیت')
        self.assertContains(panel, 'رضا محمدی')
        self.client.post(reverse('admin_approve', args=[booking.pk]), {'action': 'approve'})
        booking.refresh_from_db()
        self.assertTrue(booking.admin_approved)
        self.assertEqual(booking.status, Booking.PENDING)
        self.assertEqual(booking.confirmed_by.username, '09124444444')
        self.client.logout()

        self.client.login(username='09121111111', password='demo1234')
        still_hidden = self.client.get(reverse('bookings'))
        self.assertNotContains(still_hidden, '09130000001')
        self.assertNotContains(still_hidden, 'رضا محمدی')
        self.assertNotContains(still_hidden, 'ادمین')
        self.assertNotContains(still_hidden, 'صلاحیت')
        self.client.logout()

        self.client.login(username='09130000001', password='demo1234')
        visible = self.client.get(reverse('worker_jobs'))
        self.assertContains(visible, 'جاده کلات، کیلومتر ۱۲')
        self.assertContains(visible, 'پذیرش')
        self.assertNotContains(visible, 'ادمین')
        self.assertNotContains(visible, 'صلاحیت')
        self.client.post(reverse('job_update', args=[booking.pk]), {'action': 'confirm'})
        self.client.logout()

        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.CONFIRMED)
        self.client.login(username='09121111111', password='demo1234')
        revealed = self.client.get(reverse('bookings'))
        self.assertContains(revealed, '09130000001')
        self.assertContains(revealed, 'رضا محمدی')
        self.assertContains(revealed, reverse('worker_detail', args=[worker_profile.pk]))
        self.assertContains(revealed, 'اتمام کار')
        self.assertNotContains(revealed, 'ادمین')
        self.client.post(reverse('booking_complete', args=[booking.pk]))
        booking.refresh_from_db()
        worker_profile = User.objects.get(pk=worker_profile.pk)
        self.assertEqual(booking.status, Booking.DONE)
        self.assertEqual(worker_profile.jobs_done, jobs_before + 1)
        reviewed = self.client.post(reverse('booking_review', args=[booking.pk]), {
            'rating': '5',
            'comment': 'کار تمیز و به‌موقع بود',
        })
        self.assertRedirects(reviewed, reverse('bookings'))
        review = Review.objects.get(booking=booking, comment='کار تمیز و به‌موقع بود')
        self.assertEqual(review.farmer.username, '09121111111')
        finished = self.client.get(reverse('bookings'))
        self.assertContains(finished, 'کار تمیز و به‌موقع بود')
        self.assertContains(finished, '09130000001')

    def test_farmer_can_save_optional_map_location(self):
        self.client.login(username='09121111111', password='demo1234')
        city = City.objects.get(name='مشهد')
        response = self.client.post(reverse('farmer_profile'), {
            'farm_city': city.pk,
            'farm_address': 'جاده کلات، کیلومتر ۱۲، قطعه نمونه',
            'farm_latitude': '36.297200',
            'farm_longitude': '59.606700',
        })
        self.assertRedirects(response, reverse('home'))
        profile = User.objects.get(username='09121111111')
        self.assertTrue(profile.has_farm_location)
        self.assertEqual(profile.farm_latitude, Decimal('36.297200'))
        self.assertEqual(profile.farm_longitude, Decimal('59.606700'))
        self.assertEqual(profile.completion_percent, 100)
        page = self.client.get(reverse('farmer_profile'))
        self.assertContains(page, 'id="farm-map"')
        self.assertContains(page, '36.297200')
        self.assertContains(page, 'farm-map.js?v=3')
        script = (Path(__file__).resolve().parents[1] / 'static' / 'js' / 'farm-map.js').read_text(encoding='utf-8')
        self.assertLess(script.index('map.setView(start, zoom)'), script.index('if (hasPin && inIran'))

    def test_farmer_map_location_must_stay_inside_iran(self):
        from marketplace.geo import in_iran

        self.assertTrue(in_iran('25.291900', '60.643000'))
        self.assertTrue(in_iran('27.220000', '56.280000'))
        self.assertTrue(in_iran('26.532000', '53.980000'))
        self.assertTrue(in_iran('28.923400', '50.820300'))
        self.assertFalse(in_iran('33.315200', '44.366100'))
        self.assertFalse(in_iran('29.375900', '47.977400'))
        self.assertFalse(in_iran('25.204800', '55.270800'))
        self.assertFalse(in_iran('34.352900', '62.204000'))
        self.assertFalse(in_iran('37.960100', '58.326100'))

        self.client.login(username='09121111111', password='demo1234')
        city = City.objects.get(name='مشهد')
        outside = self.client.post(reverse('farmer_profile'), {
            'farm_city': city.pk,
            'farm_address': 'جاده کلات، کیلومتر ۱۲، قطعه نمونه',
            'farm_latitude': '33.315200',
            'farm_longitude': '44.366100',
        })
        self.assertEqual(outside.status_code, 200)
        self.assertContains(outside, 'خارج از مرزهای ایران')
        profile = User.objects.get(username='09121111111')
        self.assertFalse(profile.has_farm_location)
        coast = self.client.post(reverse('farmer_profile'), {
            'farm_city': city.pk,
            'farm_address': 'جاده کلات، کیلومتر ۱۲، قطعه نمونه',
            'farm_latitude': '25.291900',
            'farm_longitude': '60.643000',
        })
        self.assertRedirects(coast, reverse('home'))
        profile.refresh_from_db()
        self.assertEqual(profile.farm_latitude, Decimal('25.291900'))
        page = self.client.get(reverse('farmer_profile'))
        self.assertContains(page, 'id="iran-border"')
        self.assertContains(page, 'sm:h-[28rem]')
        self.assertContains(page, 'farm-map.js')

    def test_order_page_shows_order_steps(self):
        response = self.client.get(reverse('order', args=['wheat-harvest']))
        self.assertContains(response, 'مراحل ثبت سفارش')
        self.assertContains(response, 'خدمت و آدرس')
        self.assertContains(response, 'aria-current="step"')

    def test_dates_are_entered_and_shown_in_jalali(self):
        import jdatetime

        from marketplace.dates import jalali_parts, to_jalali

        order = self.client.get(reverse('order', args=['wheat-harvest']))
        self.assertContains(order, 'فروردین')
        self.assertContains(order, 'name="work_date_0"')
        self.assertNotContains(order, 'type="date"')

        work_date = timezone.localdate() + timedelta(days=2)
        year, month, day = jalali_parts(work_date)
        self.client.login(username='09121111111', password='demo1234')
        city = City.objects.get(name='مشهد')
        profile = User.objects.get(username='09121111111')
        profile.farm_city = city
        profile.farm_address = 'جاده کلات، کیلومتر ۱۲، قطعه نمونه'
        profile.save()
        service = Service.objects.get(slug='wheat-harvest')
        worker = User.objects.get(username='09130000001')
        booked = self.client.post(reverse('book', args=[worker.pk]), {
            'service': service.pk,
            'city': city.pk,
            'address': profile.farm_address,
            'work_date_0': year,
            'work_date_1': month,
            'work_date_2': day,
        })
        self.assertRedirects(booked, reverse('bookings'))
        booking = Booking.objects.get()
        self.assertEqual(booking.work_date, work_date)
        shown = to_jalali(work_date)
        self.assertContains(self.client.get(reverse('bookings')), shown)
        listing = self.client.get(reverse('workers'), {'date': work_date.isoformat(), 'address': profile.farm_address})
        self.assertContains(listing, shown)
        self.assertContains(listing, f'value="{work_date.isoformat()}"')

        invalid = self.client.post(reverse('book', args=[worker.pk]), {
            'service': service.pk,
            'city': city.pk,
            'address': profile.farm_address,
            'work_date_0': str(jdatetime.date.fromgregorian(date=work_date).year),
            'work_date_1': '7',
            'work_date_2': '31',
        })
        self.assertEqual(invalid.status_code, 200)
        self.assertContains(invalid, 'تاریخ جلالی معتبر نیست')

        admin = AdminAccount.objects.get(username='09124444444')
        booking.admin_approved = True
        booking.confirmed_by = admin
        booking.confirmed_at = timezone.now()
        booking.save()
        self.client.login(username='09124444444', password='demo1234')
        panel = self.client.get(reverse('admin_panel'))
        self.assertContains(panel, shown)
        self.assertContains(panel, to_jalali(booking.confirmed_at, 'Y/m/d H:i'))
        self.client.login(username='09130000001', password='demo1234')
        self.assertContains(self.client.get(reverse('worker_jobs')), shown)

    def test_clicking_a_person_opens_their_profile(self):
        farmer = User.objects.get(username='09121111111')
        worker = User.objects.get(username='09130000001')
        farmer_url = reverse('farmer_public', args=[farmer.pk])
        worker_url = reverse('worker_detail', args=[worker.pk])

        public_page = self.client.get(farmer_url)
        self.assertContains(public_page, 'سامان کریمی')
        self.assertContains(public_page, 'صاحب زمین')
        self.assertNotContains(public_page, '۰۹۱۲۱۱۱۱۱۱۱')
        self.assertEqual(self.client.get(reverse('farmer_public', args=[worker.pk])).status_code, 404)

        home = self.client.get(reverse('home'))
        featured = home.context['featured_workers'][0]
        self.assertContains(home, reverse('worker_detail', args=[featured.pk]))
        city = City.objects.get(name='مشهد')
        listing = self.client.get(reverse('workers'), {'service': 'wheat-harvest', 'city': city.pk})
        self.assertContains(listing, worker_url)

        self.client.login(username='09121111111', password='demo1234')
        own_page = self.client.get(farmer_url)
        self.assertContains(own_page, '۰۹۱۲۱۱۱۱۱۱۱')
        self.assertContains(own_page, 'ویرایش پروفایل')
        self.client.logout()

    def test_farmer_contact_is_visible_to_the_assigned_worker(self):
        booking, worker_profile = self._book_sample()
        farmer = User.objects.get(username='09121111111')
        farmer_url = reverse('farmer_public', args=[farmer.pk])
        worker_url = reverse('worker_detail', args=[worker_profile.pk])

        self.client.login(username='09130000001', password='demo1234')
        hidden = self.client.get(farmer_url)
        self.assertContains(hidden, 'سامان کریمی')
        self.assertNotContains(hidden, '۰۹۱۲۱۱۱۱۱۱۱')
        self.assertNotContains(hidden, 'جاده کلات')
        self.client.logout()

        self.client.login(username='09124444444', password='demo1234')
        self.client.post(reverse('admin_approve', args=[booking.pk]), {'action': 'approve'})
        panel = self.client.get(reverse('admin_panel'))
        self.assertContains(panel, farmer_url)
        self.assertContains(panel, worker_url)
        admin_view = self.client.get(farmer_url)
        self.assertContains(admin_view, '۰۹۱۲۱۱۱۱۱۱۱')
        self.client.logout()

        self.client.login(username='09130000001', password='demo1234')
        jobs = self.client.get(reverse('worker_jobs'))
        self.assertContains(jobs, farmer_url)
        visible = self.client.get(farmer_url)
        self.assertContains(visible, '۰۹۱۲۱۱۱۱۱۱۱')
        self.assertContains(visible, 'جاده کلات، کیلومتر ۱۲، قطعه نمونه')

    def test_farmer_filters_orders_by_request_stage(self):
        booking, _worker = self._book_sample()
        done = Booking.objects.create(
            farmer=booking.farmer,
            worker=booking.worker,
            service=booking.service,
            city=booking.city,
            address='قطعه آماده نظر',
            work_date=booking.work_date,
            wage=booking.wage,
            status=Booking.DONE,
            admin_approved=True,
        )
        self.client.login(username='09121111111', password='demo1234')

        page = self.client.get(reverse('bookings'))
        self.assertContains(page, 'فیلتر مرحله درخواست')
        self.assertContains(page, 'پذیرش سرویس دهنده (۱)')
        self.assertContains(page, 'ثبت نظر (۱)')
        self.assertContains(page, 'جاده کلات، کیلومتر ۱۲')
        self.assertContains(page, 'قطعه آماده نظر')

        waiting = self.client.get(reverse('bookings'), {'stage': 'pending'})
        self.assertContains(waiting, 'جاده کلات، کیلومتر ۱۲')
        self.assertNotContains(waiting, 'قطعه آماده نظر')

        review_stage = self.client.get(reverse('bookings'), {'stage': 'feedback'})
        self.assertContains(review_stage, 'قطعه آماده نظر')
        self.assertNotContains(review_stage, 'جاده کلات، کیلومتر ۱۲')

        empty = self.client.get(reverse('bookings'), {'stage': 'confirmed'})
        self.assertContains(empty, 'در این مرحله سفارشی نیست')
        self.assertNotContains(empty, 'جاده کلات، کیلومتر ۱۲')

        unknown = self.client.get(reverse('bookings'), {'stage': '../admin'})
        self.assertContains(unknown, 'جاده کلات، کیلومتر ۱۲')
        self.assertContains(unknown, 'قطعه آماده نظر')

        booking.status = Booking.CONFIRMED
        booking.save(update_fields=['status'])
        cancelled = self.client.post(f"{reverse('booking_cancel', args=[booking.pk])}?stage=confirmed")
        self.assertRedirects(cancelled, f"{reverse('bookings')}?stage=confirmed")
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.CANCELLED)
        cancelled_list = self.client.get(reverse('bookings'), {'stage': 'cancelled'})
        self.assertContains(cancelled_list, 'جاده کلات، کیلومتر ۱۲')

        Review.objects.create(
            booking=done,
            worker=done.worker,
            farmer=done.farmer,
            rating=5,
            comment='مرحله تکمیل شد',
        )
        finished = self.client.get(reverse('bookings'), {'stage': 'finished'})
        self.assertContains(finished, 'قطعه آماده نظر')
        self.assertContains(finished, 'مرحله تکمیل شد')
        still_review = self.client.get(reverse('bookings'), {'stage': 'feedback'})
        self.assertContains(still_review, 'در این مرحله سفارشی نیست')

    def test_guest_booking_goes_to_login(self):
        worker = User.objects.get(username='09130000001')
        response = self.client.get(reverse('book', args=[worker.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response['Location'])

    def test_admin_creates_a_base_account_without_profiles(self):
        self.client.login(username='09124444444', password='demo1234')
        page = self.client.get(reverse('admin_create_account'))
        self.assertContains(page, 'افزودن حساب')
        self.assertContains(page, 'شماره تماس')
        self.assertNotContains(page, 'مشخصات زمین')
        self.assertNotContains(page, 'مشخصات کاری')

        created = self.client.post(reverse('admin_create_account'), {
            'name': 'علی رضایی',
            'username': '09125556677',
            'password': 'workerpass',
            'password2': 'workerpass',
        })
        self.assertRedirects(created, reverse('admin_panel'))
        user = User.objects.get(username='09125556677')
        self.assertEqual(user.name, 'علی رضایی')
        self.assertEqual(user.phone, '09125556677')
        self.assertTrue(user.check_password('workerpass'))
        self.assertFalse(LandOwner.objects.filter(user=user).exists())
        self.assertFalse(ServiceProvider.objects.filter(user=user).exists())
        self.client.logout()
        self.assertTrue(self.client.login(username='09125556677', password='workerpass'))

    def test_admin_can_create_accounts_with_only_login_fields(self):
        self.client.login(username='09124444444', password='demo1234')
        created = self.client.post(reverse('admin_create_account'), {
            'name': 'بدون زمین',
            'username': '09121110000',
            'password': 'farmerpass',
            'farm_address': 'کوتاه',
        })
        self.assertRedirects(created, reverse('admin_panel'))
        farmer_user = User.objects.get(username='09121110000')
        self.assertFalse(LandOwner.objects.filter(user=farmer_user).exists())
        self.assertFalse(ServiceProvider.objects.filter(user=farmer_user).exists())

        mismatch = self.client.post(reverse('admin_create_account'), {
            'name': 'رمز ناهماهنگ',
            'username': '09123334455',
            'password': 'farmerpass',
            'password2': 'mismatch',
        })
        self.assertEqual(mismatch.status_code, 200)
        self.assertContains(mismatch, 'تکرار رمز عبور یکسان نیست')
        self.assertFalse(User.objects.filter(username='09123334455').exists())

        duplicate = self.client.post(reverse('admin_create_account'), {
            'name': 'تکراری',
            'username': '09121111111',
            'password': 'farmerpass',
            'password2': 'farmerpass',
        })
        self.assertEqual(duplicate.status_code, 200)
        self.assertContains(duplicate, 'این شماره قبلاً ثبت شده است')

    def test_only_admin_can_open_account_form(self):
        guest = self.client.get(reverse('admin_create_account'))
        self.assertEqual(guest.status_code, 302)
        self.assertIn('/login/', guest['Location'])
        self.client.login(username='09121111111', password='demo1234')
        farmer = self.client.get(reverse('admin_create_account'))
        self.assertRedirects(farmer, reverse('home'))

    def test_admin_navigation_shows_only_jobs_and_accounts(self):
        guest = self.client.get(reverse('home'))
        self.assertContains(guest, '>خانه</a>')
        self.assertContains(guest, '>خدمات</a>')
        self.assertNotContains(guest, '?role=worker" class="hover:text-white">ثبت‌نام سرویس دهندگان</a>')
        self.client.login(username='09124444444', password='demo1234')
        hidden = (
            '>خانه</a>',
            '>خدمات</a>',
            '>سرویس‌دهندگان</a>',
            '>پرسش‌ها</a>',
            '>درباره ما</a>',
            '>پرسش‌های متداول</a>',
            '>همه خدمات</a>',
            '>ثبت‌نام سرویس دهندگان</a>',
        )
        for name in ('admin_panel', 'admin_create_account', 'admin_people'):
            page = self.client.get(reverse(name))
            self.assertContains(page, '>پنل کارها</a>')
            self.assertContains(page, '>افراد</a>')
            self.assertContains(page, '>افزودن حساب</a>')
            for label in hidden:
                self.assertNotContains(page, label)
        self.assertRedirects(self.client.get(reverse('login')), reverse('admin_panel'))

    def test_admin_can_list_farmers_and_workers(self):
        guest = self.client.get(reverse('admin_people'))
        self.assertIn('/login/', guest['Location'])
        self.client.login(username='09121111111', password='demo1234')
        self.assertRedirects(self.client.get(reverse('admin_people')), reverse('home'))
        self.client.logout()

        self.client.login(username='09124444444', password='demo1234')
        farmers = self.client.get(reverse('admin_people'))
        self.assertContains(farmers, 'سامان کریمی')
        self.assertContains(farmers, 'صاحبان زمین')
        self.assertNotContains(farmers, 'رضا محمدی')
        workers = self.client.get(reverse('admin_people'), {'role': 'worker'})
        self.assertContains(workers, 'رضا محمدی')
        self.assertContains(workers, 'سرویس‌دهندگان')
        self.assertNotContains(workers, 'سامان کریمی')
        unknown = self.client.get(reverse('admin_people'), {'role': 'admin'})
        self.assertContains(unknown, 'سامان کریمی')
        self.assertNotContains(unknown, 'رضا محمدی')

    def test_password_fields_include_a_visibility_toggle(self):
        login = self.client.get(reverse('login'))
        self.assertContains(login, 'class="password-field"', count=1)
        self.assertContains(login, 'aria-label="نمایش رمز"', count=1)
        register = self.client.get(reverse('register'))
        self.assertContains(register, 'aria-label="نمایش رمز"', count=2)
        self.client.login(username='09124444444', password='demo1234')
        account = self.client.get(reverse('admin_create_account'))
        self.assertContains(account, 'aria-label="نمایش رمز"', count=2)

    def test_admin_people_search_by_name_and_phone(self):
        self.client.login(username='09124444444', password='demo1234')
        by_name = self.client.get(reverse('admin_people'), {'q': 'سامان'})
        self.assertContains(by_name, 'سامان کریمی')
        self.assertNotContains(by_name, 'حسین یوسفی')
        self.assertContains(by_name, 'صاحبان زمین (۱)')
        by_phone = self.client.get(reverse('admin_people'), {'q': '09121111111'})
        self.assertContains(by_phone, 'سامان کریمی')
        self.assertNotContains(by_phone, 'حسین یوسفی')
        persian_digits = self.client.get(reverse('admin_people'), {'q': '۱۱۱۱۱'})
        self.assertContains(persian_digits, 'سامان کریمی')
        self.assertNotContains(persian_digits, 'حسین یوسفی')
        worker_name = self.client.get(reverse('admin_people'), {'role': 'worker', 'q': 'رضا'})
        self.assertContains(worker_name, 'رضا محمدی')
        self.assertNotContains(worker_name, 'حسن موسوی')
        worker_phone = self.client.get(reverse('admin_people'), {'role': 'worker', 'q': '09130000001'})
        self.assertContains(worker_phone, 'رضا محمدی')
        self.assertNotContains(worker_phone, 'حسن موسوی')
        missing = self.client.get(reverse('admin_people'), {'q': 'ناموجود'})
        self.assertContains(missing, 'کسی با این نام یا شماره پیدا نشد.')
        self.assertNotContains(missing, 'سامان کریمی')

    def test_admin_lists_are_paginated(self):
        self.client.login(username='09124444444', password='demo1234')
        farmers = [
            'احمد توکلی', 'باغ سیب مهربان', 'باغستان نمونه', 'تعاونی دشت طلا',
            'حسین یوسفی', 'رضا کیانی', 'سامان کریمی', 'فاطمه نادری',
            'مریم صالحی', 'مزرعه سبزدشت', 'مزرعه شمال',
        ]
        workers = [
            'ابراهیم صالحی', 'امیر قاسمی', 'جواد اکبری', 'حسن موسوی',
            'حسین کریمی', 'رضا محمدی', 'سعید نوری', 'علی حسینی',
            'مجید کاظمی', 'مهدی رضایی', 'ناصر حیدری', 'یوسف مرادی',
        ]
        farmer_pages = self._listed_names(reverse('admin_people'), farmers)
        self.assertEqual(len(farmer_pages), 2)
        self.assertEqual(sum(len(page) for page in farmer_pages), len(farmers))
        self.assertFalse(set.intersection(*farmer_pages))
        worker_pages = self._listed_names(reverse('admin_people'), workers, {'role': 'worker'})
        self.assertEqual(len(worker_pages), 2)
        self.assertEqual(sum(len(page) for page in worker_pages), len(workers))
        self.assertFalse(set.intersection(*worker_pages))
        kept = self.client.get(reverse('admin_people'), {'role': 'worker', 'q': '0913'})
        self.assertContains(kept, 'role=worker')
        self.assertContains(kept, 'q=0913')
        self.assertContains(kept, 'page=2')

        farmer = User.objects.get(username='09121111111')
        worker = User.objects.get(username='09130000001')
        service = Service.objects.get(slug='wheat-harvest')
        city = City.objects.get(name='مشهد')
        created = timezone.now()
        for index in range(11):
            booking = Booking.objects.create(
                farmer=farmer,
                worker=worker,
                service=service,
                city=city,
                address=f'نشانی‌یکتا-{index:02d}',
                work_date=timezone.localdate() + timedelta(days=index + 1),
            )
            Booking.objects.filter(pk=booking.pk).update(created_at=created + timedelta(minutes=index))
        first = self.client.get(reverse('admin_panel'))
        self.assertContains(first, 'نشانی‌یکتا-10')
        self.assertNotContains(first, 'نشانی‌یکتا-00')
        self.assertContains(first, 'page=2')
        second = self.client.get(reverse('admin_panel'), {'page': 2})
        self.assertContains(second, 'نشانی‌یکتا-00')
        self.assertNotContains(second, 'نشانی‌یکتا-10')
        self.assertContains(second, 'قبلی')
        awaiting = self.client.get(reverse('admin_panel'), {'status': 'awaiting'})
        self.assertContains(awaiting, 'status=awaiting')
        self.assertContains(awaiting, 'page=2')

    def _listed_names(self, url, names, params=None):
        pages = []
        seen = set()
        page = 1
        while True:
            query = dict(params or {})
            query['page'] = page
            response = self.client.get(url, query)
            self.assertEqual(response.status_code, 200)
            found = {name for name in names if name in response.content.decode()}
            self.assertTrue(found)
            self.assertFalse(found & seen)
            pages.append(found)
            seen |= found
            if 'بعدی' not in response.content.decode():
                break
            page += 1
            self.assertLessEqual(page, 5)
        self.assertEqual(seen, set(names))
        return pages

    @override_settings(
        MELIPAYAMAK_USERNAME='panel-user',
        MELIPAYAMAK_PASSWORD='panel-pass',
        MELIPAYAMAK_FROM='50004000',
        MELIPAYAMAK_KEY='',
    )
    @patch('marketplace.sms.requests.post')
    def test_admin_account_texts_the_new_login(self, post):
        post.return_value.json.return_value = {
            'RetStatus': 1,
            'Value': '12345',
            'StrRetStatus': 'Ok',
        }
        post.return_value.raise_for_status.return_value = None
        self.client.login(username='09124444444', password='demo1234')
        response = self.client.post(reverse('admin_create_account'), {
            'role': 'worker',
            'name': 'پیامک تست',
            'username': '09126667788',
            'password': 'sms-pass-1',
            'bio': '',
            'experience_years': '',
            'daily_wage': '',
            'is_active': 'on',
        }, follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'پیامک شد')
        self.assertTrue(User.objects.filter(username='09126667788').exists())
        sent = post.call_args.kwargs['data']
        self.assertEqual(sent['to'], '09126667788')
        self.assertEqual(sent['from'], '50004000')
        self.assertEqual(sent['username'], 'panel-user')
        self.assertEqual(sent['isFlash'], 'false')
        self.assertIn('نام کاربری: 09126667788', sent['text'])
        self.assertIn('رمز عبور: sms-pass-1', sent['text'])
        self.assertNotContains(response, 'sms-pass-1')

    @override_settings(
        MELIPAYAMAK_USERNAME='',
        MELIPAYAMAK_PASSWORD='',
        MELIPAYAMAK_FROM='',
        MELIPAYAMAK_KEY='',
    )
    @patch('marketplace.sms.requests.post')
    def test_account_is_kept_when_sms_is_not_configured(self, post):
        self.client.login(username='09124444444', password='demo1234')
        response = self.client.post(reverse('admin_create_account'), {
            'role': 'farmer',
            'name': 'بدون پیامک',
            'username': '09126660000',
            'password': 'sms-pass-2',
        }, follow=True)

        self.assertTrue(User.objects.filter(username='09126660000').exists())
        self.assertContains(response, 'پیامک ارسال نشد')
        post.assert_not_called()

    @override_settings(
        MELIPAYAMAK_USERNAME='panel-user',
        MELIPAYAMAK_PASSWORD='panel-pass',
        MELIPAYAMAK_FROM='50004000',
        MELIPAYAMAK_KEY='',
    )
    @patch('marketplace.sms.requests.post')
    def test_account_is_kept_when_sms_is_rejected(self, post):
        post.return_value.json.return_value = {'RetStatus': 0, 'StrRetStatus': 'Error'}
        post.return_value.raise_for_status.return_value = None
        self.client.login(username='09124444444', password='demo1234')
        response = self.client.post(reverse('admin_create_account'), {
            'role': 'farmer',
            'name': 'رد پیامک',
            'username': '09126661111',
            'password': 'sms-pass-3',
        }, follow=True)

        self.assertTrue(User.objects.filter(username='09126661111').exists())
        self.assertContains(response, 'پیامک ارسال نشد')
        self.assertNotContains(response, 'sms-pass-3')

    @override_settings(
        MELIPAYAMAK_USERNAME='panel-user',
        MELIPAYAMAK_PASSWORD='panel-pass',
        MELIPAYAMAK_FROM='50004000',
        MELIPAYAMAK_KEY='',
    )
    @patch('marketplace.sms.requests.post')
    def test_blacklist_code_is_not_reported_as_sent(self, post):
        post.return_value.json.return_value = {
            'RetStatus': 1,
            'Value': '11',
            'StrRetStatus': 'Ok',
        }
        post.return_value.raise_for_status.return_value = None
        self.client.login(username='09124444444', password='demo1234')
        response = self.client.post(reverse('admin_create_account'), {
            'role': 'farmer',
            'name': 'لیست سیاه',
            'username': '09126663333',
            'password': 'sms-pass-5',
        }, follow=True)

        self.assertTrue(User.objects.filter(username='09126663333').exists())
        self.assertContains(response, 'لیست سیاه')
        self.assertNotContains(response, 'پیامک شد')
        self.assertNotContains(response, 'sms-pass-5')

    @override_settings(
        MELIPAYAMAK_USERNAME='panel-user',
        MELIPAYAMAK_PASSWORD='panel-pass',
        MELIPAYAMAK_FROM='50004000',
        MELIPAYAMAK_KEY='console-key',
    )
    @patch('marketplace.sms.requests.post')
    def test_console_key_explains_when_melipayamak_rejects_it(self, post):
        post.return_value.json.return_value = {'status': 'کلید کنسول معتبر نیست'}
        self.client.login(username='09124444444', password='demo1234')
        response = self.client.post(reverse('admin_create_account'), {
            'role': 'farmer',
            'name': 'کلید کنسول',
            'username': '09126662222',
            'password': 'sms-pass-4',
        }, follow=True)

        self.assertTrue(User.objects.filter(username='09126662222').exists())
        self.assertContains(response, 'کلید کنسول معتبر نیست')
        self.assertNotContains(response, 'sms-pass-4')
        self.assertTrue(post.call_args.args[0].endswith('/api/send/simple/console-key'))
        self.assertEqual(post.call_args.kwargs['json']['to'], '09126662222')
        self.assertNotIn('username', post.call_args.kwargs['json'])
        self.assertNotIn('console-key', response.content.decode())

    def test_admin_can_export_profiles_to_excel(self):
        from io import BytesIO

        from openpyxl import load_workbook

        guest = self.client.get(reverse('admin:marketplace_user_export'))
        self.assertEqual(guest.status_code, 302)
        self.assertIn('/admin/login/', guest['Location'])

        self.client.login(username='09121111111', password='demo1234')
        self.assertEqual(self.client.get(reverse('admin:marketplace_user_changelist')).status_code, 302)
        self.client.logout()

        self.client.login(username='admin', password='demo1234')
        page = self.client.get(reverse('admin:marketplace_user_changelist'))
        self.assertContains(page, 'خروجی اکسل')
        export_url = reverse('admin:marketplace_user_export')
        self.assertContains(page, export_url)

        response = self.client.get(export_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response['Content-Type'],
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        self.assertIn('profiles-', response['Content-Disposition'])
        sheet = load_workbook(BytesIO(response.content)).active
        rows = list(sheet.iter_rows(values_only=True))
        self.assertEqual(rows[0][0], 'نام')
        self.assertEqual(rows[0][2], 'موبایل')
        self.assertNotIn('نقش', rows[0])
        self.assertNotIn('شهر زمین', rows[0])
        self.assertNotIn('دستمزد روزانه', rows[0])
        names = {row[0] for row in rows[1:]}
        self.assertIn('سامان کریمی', names)
        self.assertIn('رضا محمدی', names)
        saman = next(row for row in rows[1:] if row[0] == 'سامان کریمی')
        self.assertEqual(saman[2], '09121111111')

        searched = self.client.get(export_url, {'q': 'رضا'})
        searched_names = {
            row[0] for row in load_workbook(BytesIO(searched.content)).active.iter_rows(min_row=2, values_only=True)
        }
        self.assertIn('رضا محمدی', searched_names)
        self.assertNotIn('سامان کریمی', searched_names)

    def test_django_admin_shows_the_unified_account(self):
        self.client.login(username='admin', password='demo1234')
        worker = User.objects.get(username='09130000001')
        change = self.client.get(reverse('admin:marketplace_user_change', args=[worker.pk]))
        self.assertEqual(change.status_code, 200)
        self.assertContains(change, 'شماره تماس')
        self.assertNotContains(change, 'حوزه کاری')
        self.assertNotContains(change, 'آدرس زمین')
        self.assertNotContains(change, 'id_email')

        add = self.client.get(reverse('admin:marketplace_user_add'))
        self.assertEqual(add.status_code, 200)
        self.assertContains(add, 'شماره تماس')
        self.assertContains(add, 'نام')
        self.assertNotContains(add, 'آدرس زمین')
        self.assertNotContains(add, 'آماده دریافت کار')

        provider = ServiceProvider.objects.get(user=worker)
        provider_change = self.client.get(reverse('admin:marketplace_serviceprovider_change', args=[provider.pk]))
        self.assertContains(provider_change, 'حوزه کاری')
        self.assertContains(provider_change, 'آماده دریافت کار')
        self.assertContains(provider_change, worker.bio[:24])

        listing = self.client.get(reverse('admin:marketplace_user_changelist'))
        self.assertNotContains(listing, 'نقش')
        self.assertNotContains(listing, 'دستمزد روزانه')
        self.assertNotContains(listing, 'شهر زمین')
        lands = self.client.get(reverse('admin:marketplace_landowner_changelist'))
        self.assertContains(lands, 'شهر زمین')
        providers = self.client.get(reverse('admin:marketplace_serviceprovider_changelist'))
        self.assertContains(providers, 'دستمزد روزانه')
        self.assertContains(providers, 'امتیاز')
        self.assertContains(providers, 'کارهای انجام‌شده')
        self.assertContains(providers, 'آماده دریافت کار')

        booking_add = self.client.get(reverse('admin:marketplace_booking_add'))
        self.assertEqual(booking_add.status_code, 200)
        html = booking_add.content.decode()
        farmer_select = html.split('id="id_farmer"', 1)[1].split('</select>', 1)[0]
        worker_select = html.split('id="id_worker"', 1)[1].split('</select>', 1)[0]
        self.assertIn('سامان کریمی', farmer_select)
        self.assertNotIn('رضا محمدی', farmer_select)
        self.assertIn('رضا محمدی', worker_select)
        self.assertNotIn('سامان کریمی', worker_select)

        review_add = self.client.get(reverse('admin:marketplace_review_add'))
        self.assertEqual(review_add.status_code, 200)
        review_html = review_add.content.decode()
        self.assertIn('رضا محمدی', review_html.split('id="id_worker"', 1)[1].split('</select>', 1)[0])

    def test_one_account_can_register_land_and_service(self):
        created = self.client.post(reverse('register'), {
            'name': 'نرگس راد',
            'phone': '09127778899',
            'password': 'demo1234',
            'password2': 'demo1234',
        })
        self.assertRedirects(created, reverse('home'))
        user = User.objects.get(username='09127778899')
        self.assertFalse(LandOwner.objects.filter(user=user).exists())
        self.assertFalse(ServiceProvider.objects.filter(user=user).exists())
        home = self.client.get(reverse('home'))
        self.assertContains(home, 'ثبت زمین')
        self.assertContains(home, 'ثبت خدمت')

        city = City.objects.get(name='مشهد')
        land = self.client.post(reverse('farmer_profile'), {
            'farm_city': city.pk,
            'farm_address': 'جاده کلات، کیلومتر ۱۲، قطعه نمونه',
        })
        self.assertRedirects(land, reverse('home'))
        self.assertTrue(LandOwner.objects.filter(user=user, farm_city=city).exists())

        service = Service.objects.get(slug='wheat-harvest')
        saved = self.client.post(reverse('worker_profile'), {
            'bio': 'برداشت گندم در زمین‌های مشهد',
            'experience_years': '3',
            'daily_wage': '700000',
            'accepts_jobs': 'on',
            'services': [str(service.pk)],
            'cities': [str(city.pk)],
        })
        self.assertRedirects(saved, reverse('worker_profile'))
        user.refresh_from_db()
        self.assertTrue(user.service_profile.services.filter(pk=service.pk).exists())
        self.assertTrue(LandOwner.objects.filter(user=user).exists())
        menu = self.client.get(reverse('home'))
        self.assertContains(menu, reverse('bookings'))
        self.assertContains(menu, reverse('worker_jobs'))

    def test_site_admin_opens_the_django_admin(self):
        logged_in = self.client.post(reverse('admin:login'), {
            'username': '09124444444',
            'password': 'demo1234',
            'next': reverse('admin:index'),
        })
        self.assertRedirects(logged_in, reverse('admin:index'))
        index = self.client.get(reverse('admin:index'))
        self.assertContains(index, 'مدیریت کشت همراه')
        self.assertContains(index, 'کاربران')
        self.assertContains(index, 'صاحبان زمین')
        self.assertContains(index, 'سرویس‌دهندگان')
        users = self.client.get(reverse('admin:marketplace_user_changelist'))
        self.assertContains(users, 'سامان کریمی')
        self.assertContains(users, 'رضا محمدی')
        city = City.objects.get(name='مشهد')
        renamed = self.client.post(reverse('admin:marketplace_city_change', args=[city.pk]), {
            'name': city.name,
            'province': city.province,
            'is_featured': 'on',
            'featured_order': city.featured_order,
        })
        self.assertRedirects(renamed, reverse('admin:marketplace_city_changelist'))

    def test_admin_logs_in_with_username(self):
        AdminAccount.objects.create_account('leila', 'secret-pass', name='لیلا')
        page = self.client.get(reverse('login'))
        self.assertContains(page, 'نام کاربری')
        response = self.client.post(reverse('login'), {
            'username': 'leila',
            'password': 'secret-pass',
        })
        self.assertRedirects(response, reverse('admin_panel'))

    def test_bazaar_shows_products_and_contact_on_the_product_page(self):
        listing = self.client.get(reverse('bazaar'))
        self.assertContains(listing, 'بذر گندم پیشگام')
        self.assertContains(listing, 'بازرگانی بازرگان')
        self.assertContains(listing, 'نهال بادام')
        self.assertNotContains(listing, '05137654321')
        self.assertNotContains(listing, '09125550001')

        wheat = Product.objects.get(name='بذر گندم پیشگام')
        detail = self.client.get(wheat.get_absolute_url())
        self.assertContains(detail, 'بازرگانی بازرگان')
        self.assertContains(detail, 'فرهاد بازرگان')
        self.assertContains(detail, 'بذر گواهی‌شده برای کشت پاییزه')
        self.assertContains(detail, 'بلوار وکیل‌آباد، بازار روز کشاورزی، غرفه ۱۲')
        self.assertContains(detail, 'برای دیدن شماره وارد شوید')
        self.assertNotContains(detail, '05137654321')
        self.assertNotContains(detail, '09125550001')
        self.assertNotContains(detail, 'شماره فروشگاه')
        self.assertNotContains(detail, 'شماره فروشنده')

        sapling = Product.objects.get(name='نهال بادام')
        shop = self.client.get(sapling.get_absolute_url())
        self.assertContains(shop, 'نهالستان گلستان')
        self.assertContains(shop, 'برای دیدن شماره وارد شوید')
        self.assertNotContains(shop, '09125550002')
        self.assertNotContains(shop, 'شماره فروشنده')
        self.assertNotContains(shop, 'شماره فروشگاه')

        self.client.login(username='09121111111', password='demo1234')
        detail = self.client.get(wheat.get_absolute_url())
        self.assertContains(detail, '05137654321')
        self.assertContains(detail, '09125550001')
        self.assertContains(detail, 'شماره فروشگاه')
        self.assertContains(detail, 'شماره فروشنده')
        self.assertNotContains(detail, 'برای دیدن شماره وارد شوید')
        shop = self.client.get(sapling.get_absolute_url())
        self.assertContains(shop, '09125550002')
        self.assertContains(shop, 'شماره فروشنده')
        self.assertNotContains(shop, 'شماره فروشگاه')
        self.client.logout()

        mashhad = City.objects.get(name='مشهد')
        filtered = self.client.get(reverse('bazaar'), {'city': mashhad.pk, 'q': 'کود'})
        self.assertContains(filtered, 'کود اوره')
        self.assertNotContains(filtered, 'نهال بادام')

    def test_seller_can_add_and_edit_a_product(self):
        self.client.login(username='09121111111', password='demo1234')
        blocked = self.client.get(reverse('seller_products'))
        self.assertRedirects(blocked, reverse('seller_profile'))

        city = City.objects.get(name='مشهد')
        missing_pin = self.client.post(reverse('seller_profile'), {
            'store_name': 'سرای کشاورزی رضا',
            'store_city': city.pk,
            'store_address': 'بازار رضا، سرای کشاورزی',
        })
        self.assertEqual(missing_pin.status_code, 200)
        self.assertContains(missing_pin, 'موقعیت فروشگاه را روی نقشه مشخص کنید.')

        outside = self.client.post(reverse('seller_profile'), {
            'store_name': 'سرای کشاورزی رضا',
            'store_city': city.pk,
            'store_address': 'بازار رضا، سرای کشاورزی',
            'store_latitude': '33.315200',
            'store_longitude': '44.366100',
        })
        self.assertEqual(outside.status_code, 200)
        self.assertContains(outside, 'خارج از مرزهای ایران')

        saved = self.client.post(reverse('seller_profile'), {
            'store_name': 'سرای کشاورزی رضا',
            'store_city': city.pk,
            'store_address': 'بازار رضا، سرای کشاورزی',
            'store_phone': '05138887766',
            'store_latitude': '36.297200',
            'store_longitude': '59.606700',
        })
        self.assertRedirects(saved, reverse('seller_products'))
        seller = User.objects.get(username='09121111111')
        self.assertEqual(seller.get_role_display(), 'صاحب زمین و فروشنده')
        self.assertEqual(seller.seller_profile.store_name, 'سرای کشاورزی رضا')
        self.assertTrue(seller.seller_profile.has_store_location)
        self.assertNotIn('نام', [step['label'] for step in seller.seller_profile.completion_steps()])
        shop = self.client.get(reverse('seller_profile'))
        self.assertNotContains(shop, 'font-semibold">نام</span>')
        seller.name = ''
        seller.save(update_fields=['name'])
        self.assertTrue(User.objects.get(pk=seller.pk).seller_profile.is_profile_complete)

        created = self.client.post(reverse('seller_product_new'), {
            'name': 'سم علف‌کش',
            'description': 'علف‌کش انتخابی برای مزرعه گندم، بطری نیم‌لیتری.',
            'price': '96000',
            'unit': Product.LITER,
            'is_available': 'on',
        })
        self.assertRedirects(created, reverse('seller_products'))
        product = Product.objects.get(name='سم علف‌کش', seller=seller.seller_profile)
        self.assertContains(self.client.get(reverse('bazaar')), 'سم علف‌کش')

        edited = self.client.post(reverse('seller_product_edit', args=[product.pk]), {
            'name': 'سم علف‌کش انتخابی',
            'description': 'علف‌کش انتخابی برای مزرعه گندم، بطری یک لیتری.',
            'price': '120000',
            'unit': Product.LITER,
        })
        self.assertRedirects(edited, reverse('seller_products'))
        product.refresh_from_db()
        self.assertEqual(product.name, 'سم علف‌کش انتخابی')
        self.assertEqual(product.price, 120000)
        self.assertFalse(product.is_available)
        self.assertNotContains(self.client.get(reverse('bazaar')), 'سم علف‌کش انتخابی')
        self.assertEqual(self.client.get(product.get_absolute_url()).status_code, 200)
        self.client.logout()
        self.assertEqual(self.client.get(product.get_absolute_url()).status_code, 404)

        self.client.login(username='09125550002', password='demo1234')
        foreign = self.client.post(reverse('seller_product_edit', args=[product.pk]), {
            'name': 'محصول دیگران',
            'description': 'این ویرایش نباید ذخیره شود.',
            'price': '10',
            'unit': Product.PIECE,
            'is_available': 'on',
        })
        self.assertEqual(foreign.status_code, 404)
        product.refresh_from_db()
        self.assertEqual(product.name, 'سم علف‌کش انتخابی')

        self.client.login(username='09121111111', password='demo1234')
        removed = self.client.post(reverse('seller_product_edit', args=[product.pk]), {'action': 'delete'})
        self.assertRedirects(removed, reverse('seller_products'))
        self.assertFalse(Product.objects.filter(pk=product.pk).exists())

    def test_bazaar_menu_panel_and_product_images(self):
        from io import BytesIO

        from django.core.files.uploadedfile import SimpleUploadedFile
        from PIL import Image

        guest = self.client.get(reverse('bazaar'))
        self.assertContains(guest, 'id="bazaar-btn"')
        self.assertContains(guest, 'پنل فروشگاه')
        self.assertContains(guest, 'ثبت فروشگاه')
        self.assertContains(guest, 'فیلتر')
        menu = guest.content.decode().split('id="bazaar-panel"', 1)[1].split('id="hamrah-menu"', 1)[0]
        self.assertIn('پنل فروشگاه', menu)
        self.assertIn('ثبت فروشگاه', menu)
        self.assertIn('محصولات', menu)

        self.client.login(username='09121111111', password='demo1234')
        blocked = self.client.get(reverse('seller_products'))
        self.assertRedirects(blocked, reverse('seller_profile'))

        self.client.login(username='09125550002', password='demo1234')
        panel = self.client.get(reverse('seller_products'))
        self.assertContains(panel, 'پنل فروشگاه')
        self.assertContains(panel, 'محصولات من')
        self.assertContains(panel, 'ثبت محصول جدید')
        self.assertContains(panel, 'نهال بادام')
        self.assertContains(panel, reverse('bazaar'))
        fresh = self.client.get(reverse('seller_product_new'))
        self.assertRedirects(fresh, f"{reverse('seller_products')}#new-product", fetch_redirect_response=False)

        buffer = BytesIO()
        Image.new('RGB', (8, 8), (160, 90, 40)).save(buffer, format='PNG')
        created = self.client.post(reverse('seller_product_new'), {
            'name': 'کود مایع',
            'description': 'کود مایع برای باغ مرکبات، بطری یک لیتری.',
            'price': '88000',
            'unit': Product.LITER,
            'is_available': 'on',
            'image': SimpleUploadedFile('fertilizer.png', buffer.getvalue(), content_type='image/png'),
        })
        self.assertRedirects(created, reverse('seller_products'))
        product = Product.objects.get(name='کود مایع')
        self.assertTrue(product.image.name.endswith('.png'))
        listing = self.client.get(reverse('bazaar'))
        self.assertContains(listing, product.image.url)
        detail = self.client.get(product.get_absolute_url())
        self.assertContains(detail, product.image.url)

    def test_admin_can_list_sellers(self):
        self.client.login(username='09124444444', password='demo1234')
        page = self.client.get(reverse('admin_people'), {'role': 'seller'})
        self.assertContains(page, 'فرهاد بازرگان')
        self.assertContains(page, 'زهرا گلستان')
        self.assertContains(page, 'فروشندگان')
        self.assertNotContains(page, 'رضا محمدی')
        self.assertNotContains(page, 'سامان کریمی')


class WallFlowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('seed')

    def _ad(self, **kwargs):
        data = {
            'user': User.objects.get(username='09121111111'),
            'category': WallCategory.objects.get(slug='crops'),
            'city': City.objects.get(name='مشهد'),
            'title': 'آگهی آزمایشی دیوار',
            'description': 'توضیح کافی برای یک آگهی آزمایشی روی دیوار کشاورزی.',
            'is_published': True,
        }
        data.update(kwargs)
        return WallAd.objects.create(**data)

    def test_picker_and_city_feed_match_the_board(self):
        mashhad = City.objects.get(name='مشهد')
        home = self.client.get(reverse('wall'))
        self.assertRedirects(home, reverse('wall_city', args=[mashhad.pk]))

        page = self.client.get(reverse('wall_city', args=[mashhad.pk]))
        self.assertContains(page, 'گندم دیم درجه یک')
        self.assertContains(page, 'وکیل‌آباد')
        self.assertNotContains(page, 'نردبان')
        self.assertContains(page, 'توافقی')
        self.assertContains(page, 'جستجو در همهٔ آگهی‌ها')
        self.assertContains(page, 'عکس‌دار')
        self.assertContains(page, 'آگهی‌ها')
        self.assertContains(page, 'دیوار من')
        self.assertNotContains(page, 'ثبت آگهی')
        self.assertNotContains(page, 'شهرهای پربازدید')
        self.assertNotContains(page, 'نهال بادام پیوندی')
        self.assertNotContains(page, 'استخدام کشاورزی')
        self.assertNotContains(page, 'خدمات کشاورزی')
        shell = self.client.get(reverse('home'))
        self.assertContains(shell, 'آگهی‌ها')
        self.assertContains(shell, 'دیوار من')

    def test_filters_city_category_price_and_photo(self):
        mashhad = City.objects.get(name='مشهد')
        shiraz = City.objects.get(name='شیراز')
        livestock = WallCategory.objects.get(slug='livestock')
        self._ad(title='یونجه ارزان دامی', price=1000, district='طرقبه')
        self._ad(title='پسته گران صادراتی', price=500000, district='کنه بیست')
        self._ad(title='بره پرواری', price=None, category=livestock)
        self._ad(title='پرتقال شیراز فقط', price=20000, city=shiraz)

        priced = self.client.get(reverse('wall_city', args=[mashhad.pk]), {'min_price': '10000', 'q': 'پسته'})
        self.assertContains(priced, 'پسته گران صادراتی')
        self.assertNotContains(priced, 'یونجه ارزان دامی')

        by_job = self.client.get(reverse('wall_city', args=[mashhad.pk]), {'cat': 'livestock'})
        self.assertContains(by_job, 'بره پرواری')
        self.assertNotContains(by_job, 'پسته گران صادراتی')

        by_place = self.client.get(reverse('wall_city', args=[mashhad.pk]), {'district': 'کنه بیست'})
        self.assertContains(by_place, 'پسته گران صادراتی')
        self.assertNotContains(by_place, 'یونجه ارزان دامی')

        other_city = self.client.get(reverse('wall_city', args=[shiraz.pk]))
        self.assertContains(other_city, 'پرتقال شیراز فقط')
        self.assertNotContains(other_city, 'یونجه ارزان دامی')

        from io import BytesIO

        from django.core.files.uploadedfile import SimpleUploadedFile
        from PIL import Image

        buffer = BytesIO()
        Image.new('RGB', (8, 8), (30, 140, 50)).save(buffer, format='PNG')
        photo = self._ad(title='هندوانه عکس‌دار')
        photo.image.save(
            'melon.png',
            SimpleUploadedFile('melon.png', buffer.getvalue(), content_type='image/png'),
            save=True,
        )
        self._ad(title='خربزه بدون عکس')
        listed = self.client.get(reverse('wall_city', args=[mashhad.pk]), {'photo': '1'})
        self.assertContains(listed, 'هندوانه عکس‌دار')
        self.assertContains(listed, photo.image.url)
        self.assertNotContains(listed, 'خربزه بدون عکس')

    def test_simple_account_can_post_without_a_role_profile(self):
        guest = self.client.get(reverse('wall_new'))
        self.assertEqual(guest.status_code, 302)
        self.assertIn('/login/', guest['Location'])

        user = User.objects.create_user(username='09129998877', password='demo1234', name='کاربر دیوار')
        self.client.login(username='09129998877', password='demo1234')
        city = City.objects.get(name='رشت')
        category = WallCategory.objects.get(slug='irrigation')
        created = self.client.post(reverse('wall_new'), {
            'category': category.pk,
            'city': city.pk,
            'district': 'کوچصفهان',
            'title': 'پمپ آب کشاورزی نو',
            'description': 'پمپ آب دو اینچ سالم، مناسب باغ چای و مرکبات گیلان، تحویل در رشت.',
            'price': '18500',
            'price_note': 'هر دستگاه',
        })
        ad = WallAd.objects.get(title='پمپ آب کشاورزی نو')
        self.assertRedirects(created, ad.get_absolute_url())
        self.assertEqual(ad.user, user)
        self.assertFalse(LandOwner.objects.filter(user=user).exists())
        self.assertFalse(ServiceProvider.objects.filter(user=user).exists())
        self.assertFalse(Seller.objects.filter(user=user).exists())

        detail = self.client.get(ad.get_absolute_url())
        self.assertContains(detail, '۱۸٬۵۰۰ تومان')
        self.assertContains(detail, 'اطلاعات تماس')
        self.assertContains(detail, '۰۹۱۲۹۹۹۸۸۷۷')
        self.client.logout()
        public = self.client.get(ad.get_absolute_url())
        self.assertContains(public, 'برای دیدن شماره وارد شوید')
        self.assertNotContains(public, '09129998877')
        self.assertNotContains(public, '۰۹۱۲۹۹۹۸۸۷۷')

        self.client.login(username='09124444444', password='demo1234')
        blocked = self.client.get(reverse('wall_new'))
        self.assertRedirects(blocked, reverse('admin_panel'))

    def test_owner_manages_ad_and_others_cannot(self):
        ad = self._ad(title='یونجه بسته‌بندی شده برای دام', price=12000, district='وکیل‌آباد')
        self.client.login(username='09130000001', password='demo1234')
        self.assertEqual(self.client.get(reverse('wall_edit', args=[ad.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse('wall_delete', args=[ad.pk])).status_code, 404)

        self.client.login(username='09121111111', password='demo1234')
        hidden = self.client.post(reverse('wall_toggle', args=[ad.pk]))
        self.assertRedirects(hidden, reverse('wall_mine'))
        ad.refresh_from_db()
        self.assertFalse(ad.is_published)
        self.client.logout()
        self.assertEqual(self.client.get(ad.get_absolute_url()).status_code, 404)
        self.assertNotContains(self.client.get(reverse('wall_city', args=[ad.city_id])), ad.title)

        self.client.login(username='09121111111', password='demo1234')
        self.assertContains(self.client.get(reverse('wall_mine')), ad.title)
        removed = self.client.post(reverse('wall_delete', args=[ad.pk]))
        self.assertRedirects(removed, reverse('wall_mine'))
        self.assertFalse(WallAd.objects.filter(pk=ad.pk).exists())

        short = self.client.post(reverse('wall_new'), {
            'category': WallCategory.objects.get(slug='crops').pk,
            'city': City.objects.get(name='مشهد').pk,
            'title': 'کم',
            'description': 'کوتاه',
        })
        self.assertEqual(short.status_code, 200)
        self.assertContains(short, 'توضیحات را حداقل')

