from datetime import timedelta
from decimal import Decimal
from pathlib import Path

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from marketplace.models import Booking, City, Review, Service

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
        self.assertContains(response, reverse('order', args=['wheat-harvest']))

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
        profile = User.objects.get(username='09121111111').profile
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

        worker = User.objects.get(username='09130000001').worker
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
        profile = User.objects.get(username='09121111111').profile
        profile.farm_city = city
        profile.farm_address = 'جاده کلات، کیلومتر ۱۲، قطعه نمونه'
        profile.save()
        service = Service.objects.get(slug='wheat-harvest')
        worker = User.objects.get(username='09130000001').worker
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
        worker = User.objects.get(username='09130000001').worker
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

    def test_worker_cannot_book(self):
        self.client.login(username='09130000001', password='demo1234')
        other = User.objects.get(username='09130000002').worker
        response = self.client.get(reverse('book', args=[other.pk]))
        self.assertRedirects(response, reverse('home'))

    def test_worker_cannot_start_a_service_request_from_home(self):
        self.client.login(username='09130000001', password='demo1234')
        other = User.objects.get(username='09130000002').worker
        home = self.client.get(reverse('home'))
        self.assertNotContains(home, reverse('order', args=['wheat-harvest']))
        self.assertContains(home, 'ثبت درخواست جدید برای صاحبان زمین است')

        category = self.client.get(reverse('category', args=['planting']))
        self.assertNotContains(category, 'انتخاب و ادامه')
        self.assertNotContains(category, reverse('order', args=['wheat-harvest']))

        listing = self.client.get(reverse('workers'))
        self.assertNotContains(listing, reverse('book', args=[other.pk]))

        detail = self.client.get(reverse('worker_detail', args=[other.pk]))
        self.assertNotContains(detail, reverse('book', args=[other.pk]))
        self.assertNotContains(detail, reverse('order', args=['classic-irrigation']))

        city = City.objects.get(name='شیراز')
        response = self.client.post(reverse('order', args=['spraying']), {
            'city': city.pk,
            'address': 'جاده مرودشت، قطعه جنوبی باغ',
            'work_date': (timezone.localdate() + timedelta(days=2)).isoformat(),
            'land_area': '1.5',
            'note': 'نباید ثبت شود',
        })
        self.assertRedirects(response, reverse('worker_jobs'))
        self.assertEqual(Booking.objects.count(), 0)

    def test_worker_list_renders_pages(self):
        response = self.client.get(reverse('workers'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'بعدی')

    def test_incomplete_farmer_is_sent_to_profile(self):
        self.client.login(username='09121111111', password='demo1234')
        worker = User.objects.get(username='09130000001').worker
        response = self.client.get(reverse('book', args=[worker.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('farmer_profile'), response['Location'])
        profile = User.objects.get(username='09121111111').profile
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
        farmer.profile.farm_city = city
        farmer.profile.farm_address = 'جاده کلات، کیلومتر ۱۲، قطعه نمونه'
        farmer.profile.save()
        worker_profile = User.objects.get(username='09130000001').worker
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
        worker_profile.refresh_from_db()
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
        profile = User.objects.get(username='09121111111').profile
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
        profile = User.objects.get(username='09121111111').profile
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
        profile = User.objects.get(username='09121111111').profile
        profile.farm_city = city
        profile.farm_address = 'جاده کلات، کیلومتر ۱۲، قطعه نمونه'
        profile.save()
        service = Service.objects.get(slug='wheat-harvest')
        worker = User.objects.get(username='09130000001').worker
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

        admin = User.objects.get(username='09124444444')
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
        worker = User.objects.get(username='09130000001').worker
        farmer_url = reverse('farmer_public', args=[farmer.pk])
        worker_url = reverse('worker_detail', args=[worker.pk])

        public_page = self.client.get(farmer_url)
        self.assertContains(public_page, 'سامان کریمی')
        self.assertContains(public_page, 'صاحب زمین')
        self.assertNotContains(public_page, '۰۹۱۲۱۱۱۱۱۱۱')
        self.assertEqual(self.client.get(reverse('farmer_public', args=[worker.user.pk])).status_code, 404)

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
        worker = User.objects.get(username='09130000001').worker
        response = self.client.get(reverse('book', args=[worker.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response['Location'])

    def test_admin_creates_worker_and_farmer_accounts(self):
        self.client.login(username='09124444444', password='demo1234')
        page = self.client.get(reverse('admin_create_account'))
        self.assertContains(page, 'افزودن حساب')
        self.assertContains(page, 'مشخصات زمین')
        self.assertContains(page, 'مشخصات کاری')
        service = Service.objects.get(slug='wheat-harvest')
        city = City.objects.get(name='مشهد')

        created_worker = self.client.post(reverse('admin_create_account'), {
            'role': 'worker',
            'name': 'علی رضایی',
            'username': '09125556677',
            'password': 'workerpass',
            'password2': 'workerpass',
            'bio': 'برداشت گندم و رانندگی تراکتور در مشهد',
            'experience_years': '8',
            'daily_wage': '900000',
            'is_active': 'on',
            'services': [str(service.pk)],
            'cities': [str(city.pk)],
        })
        self.assertRedirects(created_worker, reverse('admin_panel'))
        worker_user = User.objects.get(username='09125556677')
        self.assertEqual(worker_user.name, 'علی رضایی')
        self.assertEqual(worker_user.profile.role, 'worker')
        self.assertEqual(worker_user.profile.phone, '09125556677')
        self.assertTrue(worker_user.check_password('workerpass'))
        self.assertEqual(worker_user.worker.experience_years, 8)
        self.assertEqual(worker_user.worker.daily_wage, 900000)
        self.assertTrue(worker_user.worker.services.filter(pk=service.pk).exists())
        self.assertTrue(worker_user.worker.cities.filter(pk=city.pk).exists())
        self.assertEqual(worker_user.profile.completion_percent, 100)
        listing = self.client.get(reverse('workers'), {'service': 'wheat-harvest', 'city': city.pk})
        self.assertContains(listing, 'علی رضایی')

        created_farmer = self.client.post(reverse('admin_create_account'), {
            'role': 'farmer',
            'name': 'مزرعه نمونه شمال',
            'username': '09128887766',
            'password': 'farmerpass',
            'password2': 'farmerpass',
            'farm_city': city.pk,
            'farm_address': 'جاده کلات، کیلومتر ۲۰، قطعه شمالی',
            'farm_latitude': '36.300000',
            'farm_longitude': '59.600000',
        })
        self.assertRedirects(created_farmer, reverse('admin_panel'))
        farmer_user = User.objects.get(username='09128887766')
        self.assertEqual(farmer_user.profile.role, 'farmer')
        self.assertEqual(farmer_user.profile.farm_city, city)
        self.assertEqual(farmer_user.profile.farm_address, 'جاده کلات، کیلومتر ۲۰، قطعه شمالی')
        self.assertTrue(farmer_user.profile.has_farm_location)
        self.assertEqual(farmer_user.profile.completion_percent, 100)
        self.assertFalse(hasattr(farmer_user, 'worker') and farmer_user.worker.pk)
        self.client.logout()
        self.assertTrue(self.client.login(username='09128887766', password='farmerpass'))

    def test_admin_can_create_accounts_with_only_login_fields(self):
        self.client.login(username='09124444444', password='demo1234')
        worker = self.client.post(reverse('admin_create_account'), {
            'role': 'worker',
            'name': 'بدون حوزه',
            'username': '09120000000',
            'password': 'workerpass',
        })
        self.assertRedirects(worker, reverse('admin_panel'))
        worker_user = User.objects.get(username='09120000000')
        self.assertEqual(worker_user.worker.bio, '')
        self.assertFalse(worker_user.worker.services.exists())
        self.assertFalse(worker_user.worker.cities.exists())
        self.assertLess(worker_user.profile.completion_percent, 100)

        farmer = self.client.post(reverse('admin_create_account'), {
            'role': 'farmer',
            'name': 'بدون زمین',
            'username': '09121110000',
            'password': 'farmerpass',
            'farm_address': 'کوتاه',
        })
        self.assertRedirects(farmer, reverse('admin_panel'))
        farmer_user = User.objects.get(username='09121110000')
        self.assertIsNone(farmer_user.profile.farm_city)
        self.assertEqual(farmer_user.profile.farm_address, 'کوتاه')
        self.assertLess(farmer_user.profile.completion_percent, 100)

        mismatch = self.client.post(reverse('admin_create_account'), {
            'role': 'farmer',
            'name': 'رمز ناهماهنگ',
            'username': '09123334455',
            'password': 'farmerpass',
            'password2': 'mismatch',
        })
        self.assertEqual(mismatch.status_code, 200)
        self.assertContains(mismatch, 'تکرار رمز عبور یکسان نیست')
        self.assertFalse(User.objects.filter(username='09123334455').exists())

        duplicate = self.client.post(reverse('admin_create_account'), {
            'role': 'farmer',
            'name': 'تکراری',
            'username': '09121111111',
            'password': 'farmerpass',
            'password2': 'farmerpass',
        })
        self.assertEqual(duplicate.status_code, 200)
        self.assertContains(duplicate, 'این نام کاربری قبلاً ثبت شده است')

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
        worker = User.objects.get(username='09130000001').worker
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
