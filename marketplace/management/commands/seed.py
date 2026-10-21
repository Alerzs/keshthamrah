from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from marketplace.models import Booking, Category, City, Profile, Review, Service, WorkerProfile

PASSWORD = 'demo1234'

CATEGORIES = [
    ('کاشت و برداشت', 'planting', 'کاشت، وجین و برداشت محصول در مزرعه و باغ', 'bg-teal-50 text-soil', 1),
    ('آبیاری', 'irrigation', 'آبیاری، اجرای قطره‌ای و تعمیر شبکه آب', 'bg-teal-50 text-soil', 2),
    ('سمپاشی و تغذیه', 'protection', 'سمپاشی، کوددهی و مراقبت از گیاه', 'bg-teal-50 text-soil', 3),
    ('هرس و باغداری', 'orchard', 'هرس، پیوند و نگهداری باغ میوه', 'bg-teal-50 text-soil', 4),
    ('ماشین‌آلات', 'machinery', 'شخم، تراکتور و برداشت مکانیزه', 'bg-teal-50 text-soil', 5),
    ('سایر خدمات', 'other', 'نیروی روزمزد و کارهای عمومی مزرعه', 'bg-teal-50 text-soil', 6),
]

SERVICES = [
    ('planting', 'برداشت گندم و جو', 'wheat-harvest', 'برداشت دستی یا نیمه‌مکانیزه گندم و جو در سطح مزرعه', 950000, 'from-amber-400 to-orange-500', True, 1),
    ('planting', 'برداشت میوه', 'fruit-picking', 'چیدن میوه رسیده بدون آسیب به شاخه و محصول', 800000, 'from-rose-400 to-orange-400', True, 2),
    ('planting', 'کاشت نشا و بذر', 'transplanting', 'نشاکاری و بذرکاری ردیفی در زمین آماده‌شده', 750000, 'from-lime-400 to-emerald-500', False, 3),
    ('planting', 'وجین و تنک کردن', 'weeding', 'حذف علف هرز و تنک کردن بوته‌ها', 600000, 'from-green-400 to-lime-500', False, 4),
    ('irrigation', 'آبیاری مزرعه', 'classic-irrigation', 'آبیاری نواری و کرتی طبق برنامه زمین', 700000, 'from-sky-400 to-cyan-500', True, 5),
    ('irrigation', 'اجرای آبیاری قطره‌ای', 'drip-irrigation', 'لوله‌کشی و راه‌اندازی آبیاری قطره‌ای باغ و مزرعه', 1200000, 'from-cyan-400 to-teal-500', False, 6),
    ('irrigation', 'تعمیر شبکه آبیاری', 'irrigation-repair', 'رفع نشتی، تعویض نوار تیپ و تنظیم فشار', 850000, 'from-blue-400 to-sky-500', False, 7),
    ('protection', 'سمپاشی باغ و مزرعه', 'spraying', 'سمپاشی با رعایت دوز و زمان مناسب محصول', 900000, 'from-lime-500 to-green-600', True, 8),
    ('protection', 'کوددهی و تغذیه گیاه', 'fertilizing', 'کود جامد یا محلول‌پاشی بر اساس نیاز زمین', 780000, 'from-emerald-400 to-teal-500', False, 9),
    ('orchard', 'هرس درختان میوه', 'pruning', 'هرس زمستانه و فرم‌دهی تاج درخت', 880000, 'from-emerald-500 to-green-700', True, 10),
    ('orchard', 'پیوند و تربیت درخت', 'grafting', 'پیوند و بستن شاخه برای تربیت نهال', 1000000, 'from-teal-400 to-emerald-600', False, 11),
    ('machinery', 'شخم و دیسک‌زدن', 'tillage', 'آماده‌سازی زمین با گاوآهن و دیسک', 1100000, 'from-stone-500 to-amber-700', True, 12),
    ('machinery', 'راننده تراکتور', 'tractor-driver', 'راننده آشنا به ادوات و کار در قطعه کشاورزی', 1300000, 'from-blue-500 to-indigo-600', False, 13),
    ('machinery', 'برداشت با کمباین', 'combine', 'برداشت مکانیزه غله با کمباین', 1500000, 'from-amber-500 to-yellow-600', True, 14),
    ('other', 'سرویس دهنده روزمزد مزرعه', 'day-labor', 'نیروی عمومی برای کارهایی که همان روز پیش می‌آید', 500000, 'from-teal-400 to-cyan-500', True, 15),
    ('other', 'نگهبانی مزرعه', 'farm-guard', 'نگهبانی شیفتی از زمین، انبار یا باغ', 450000, 'from-slate-500 to-teal-700', False, 16),
]

CITIES = [
    ('مشهد', 'خراسان رضوی', True, 1),
    ('نیشابور', 'خراسان رضوی', False, 0),
    ('سبزوار', 'خراسان رضوی', False, 0),
    ('شیراز', 'فارس', True, 2),
    ('مرودشت', 'فارس', False, 0),
    ('اصفهان', 'اصفهان', True, 3),
    ('تبریز', 'آذربایجان شرقی', True, 4),
    ('ارومیه', 'آذربایجان غربی', True, 5),
    ('اهواز', 'خوزستان', True, 6),
    ('دزفول', 'خوزستان', False, 0),
    ('کرمان', 'کرمان', True, 7),
    ('رفسنجان', 'کرمان', False, 0),
    ('رشت', 'گیلان', True, 8),
    ('گرگان', 'گلستان', True, 9),
    ('ساری', 'مازندران', True, 10),
    ('همدان', 'همدان', True, 11),
    ('قزوین', 'قزوین', True, 12),
    ('کرمانشاه', 'کرمانشاه', False, 0),
    ('زنجان', 'زنجان', False, 0),
    ('یزد', 'یزد', False, 0),
    ('بیرجند', 'خراسان جنوبی', False, 0),
    ('زاهدان', 'سیستان و بلوچستان', False, 0),
    ('بجنورد', 'خراسان شمالی', False, 0),
    ('اراک', 'مرکزی', False, 0),
    ('سنندج', 'کردستان', False, 0),
    ('خرم‌آباد', 'لرستان', False, 0),
    ('کرج', 'البرز', False, 0),
    ('ورامین', 'تهران', False, 0),
    ('قم', 'قم', False, 0),
    ('بوشهر', 'بوشهر', False, 0),
]

WORKERS = [
    ('09130000001', 'رضا', 'محمدی', 'دوازده سال در دشت مشهد گندم و جو برداشت کرده‌ام و با تراکتور و شخم عمیق کار می‌کنم.', 12, 980000, 86, True, ['wheat-harvest', 'tillage', 'tractor-driver'], ['مشهد', 'نیشابور']),
    ('09130000002', 'علی', 'حسینی', 'شبکه آبیاری قطره‌ای و نواری را اجرا و تعمیر می‌کنم. بیشتر در زمین‌های اطراف مشهد حاضرم.', 7, 820000, 54, True, ['classic-irrigation', 'drip-irrigation', 'irrigation-repair'], ['مشهد', 'نیشابور', 'سبزوار']),
    ('09130000003', 'حسین', 'کریمی', 'سمپاشی باغ مرکبات و غلات، و کوددهی بر اساس آزمون خاک. مرودشت و شیراز را پوشش می‌دهم.', 9, 900000, 61, True, ['spraying', 'fertilizing', 'weeding'], ['شیراز', 'مرودشت']),
    ('09130000004', 'مهدی', 'رضایی', 'راننده تراکتور با پانزده سال سابقه شخم، دیسک و کار با کمباین در زمین‌های اصفهان.', 15, 1400000, 110, True, ['tractor-driver', 'tillage', 'combine'], ['اصفهان']),
    ('09130000005', 'جواد', 'اکبری', 'هرس و پیوند درختان سیب و انگور. کار برداشت میوه را هم با تیم کوچک انجام می‌دهم.', 11, 920000, 73, True, ['pruning', 'grafting', 'fruit-picking'], ['تبریز', 'ارومیه']),
    ('09130000006', 'سعید', 'نوری', 'چیدن سیب و انگور برای باغ‌های ارومیه و تبریز. وجین و هرس سبک را هم انجام می‌دهم.', 6, 760000, 40, True, ['fruit-picking', 'pruning', 'weeding'], ['ارومیه', 'تبریز']),
    ('09130000007', 'امیر', 'قاسمی', 'کوددهی مزارع شمال و سمپاشی به‌موقع. آبیاری سنتی مزرعه را هم بلد هستم.', 8, 800000, 48, True, ['fertilizing', 'spraying', 'classic-irrigation'], ['گرگان', 'ساری']),
    ('09130000010', 'یوسف', 'مرادی', 'وجین پسته و کار روزمزد باغ. کاشت نهال را هم در کرمان و رفسنجان انجام می‌دهم.', 5, 640000, 28, False, ['weeding', 'day-labor', 'transplanting'], ['کرمان', 'رفسنجان']),
    ('09130000011', 'حسن', 'موسوی', 'برداشت کمباینی غله در دشت قزوین و زنجان. خودم راننده و هماهنگ‌کننده دستگاه هستم.', 18, 1550000, 140, True, ['combine', 'wheat-harvest', 'tractor-driver'], ['قزوین', 'زنجان']),
    ('09130000012', 'ابراهیم', 'صالحی', 'آبیاری قطره‌ای باغ چای و مرکبات، سمپاشی و هرس سبک در گیلان و مازندران.', 9, 870000, 52, True, ['drip-irrigation', 'spraying', 'pruning'], ['رشت', 'ساری']),
    ('09130000013', 'مجید', 'کاظمی', 'سرویس دهنده برداشت و نیروی روزمزد. در فصل درو مشهد و نیشابور حاضر می‌شوم.', 4, 560000, 22, False, ['wheat-harvest', 'day-labor', 'weeding'], ['مشهد', 'نیشابور']),
    ('09130000014', 'ناصر', 'حیدری', 'سمپاشی و تغذیه مزارع اصفهان. با سمپاش فرغونی و پشتی کار می‌کنم.', 8, 840000, 45, True, ['spraying', 'fertilizing'], ['اصفهان']),
]

REVIEW_TEXTS = [
    (5, 'کار تمیز و به‌موقع انجام شد. برای فصل بعد هم هماهنگ می‌کنم.'),
    (4, 'با زمین و ابزار آشنا بود و وسط کار لازم نشد چیزی را دوباره توضیح بدهم.'),
    (5, 'برخورد محترمانه و سرعتش برای مساحت زمین ما مناسب بود.'),
    (3, 'نتیجه کار قابل قبول بود، ولی کمی دیرتر از ساعت قرار به مزرعه رسید.'),
    (4, 'دستمزدش با کیفیت کار جور بود و قطعه را مرتب تحویل داد.'),
]
AUTHORS = [
    ('09122000001', 'مزرعه', 'سبزدشت'),
    ('09122000002', 'حسین', 'یوسفی'),
    ('09122000003', 'باغ', 'سیب مهربان'),
    ('09122000004', 'فاطمه', 'نادری'),
    ('09122000005', 'تعاونی', 'دشت طلا'),
    ('09122000006', 'رضا', 'کیانی'),
    ('09122000007', 'باغستان', 'نمونه'),
    ('09122000008', 'مریم', 'صالحی'),
    ('09122000009', 'مزرعه', 'شمال'),
    ('09122000010', 'احمد', 'توکلی'),
]


class Command(BaseCommand):
    help = 'شهرها، خدمات و سرویس دهندگان نمونه کشت همراه را می‌سازد.'

    @transaction.atomic
    def handle(self, *args, **options):
        categories = {}
        for name, slug, description, icon_bg, sort_order in CATEGORIES:
            category, _ = Category.objects.update_or_create(
                slug=slug,
                defaults={
                    'name': name,
                    'description': description,
                    'icon_bg': icon_bg,
                    'sort_order': sort_order,
                },
            )
            categories[slug] = category

        services = {}
        for category_slug, name, slug, description, price, gradient, popular, sort_order in SERVICES:
            service, _ = Service.objects.update_or_create(
                slug=slug,
                defaults={
                    'category': categories[category_slug],
                    'name': name,
                    'description': description,
                    'base_price': price,
                    'gradient': gradient,
                    'is_popular': popular,
                    'sort_order': sort_order,
                },
            )
            services[slug] = service

        obsolete = Category.objects.filter(slug__in=('livestock', 'logistics'))
        Booking.objects.filter(service__category__in=obsolete).delete()
        obsolete.delete()

        cities = {}
        for name, province, featured, order in CITIES:
            city, _ = City.objects.update_or_create(
                name=name,
                defaults={
                    'province': province,
                    'is_featured': featured,
                    'featured_order': order,
                },
            )
            cities[name] = city

        self._user('09121111111', 'سامان', 'کریمی', Profile.FARMER)
        self._user('09124444444', 'لیلا', 'احمدی', Profile.ADMIN)
        User = get_user_model()
        admin, created = User.objects.get_or_create(
            username='admin',
            defaults={'is_staff': True, 'is_superuser': True, 'first_name': 'مدیر', 'name': 'مدیر'},
        )
        admin.is_staff = True
        admin.is_superuser = True
        admin.set_password(PASSWORD)
        admin.save()

        for item in WORKERS:
            phone, first, last, bio, years, wage, jobs, verified, service_slugs, city_names = item
            user = self._user(phone, first, last, Profile.WORKER)
            worker, _ = WorkerProfile.objects.update_or_create(
                user=user,
                defaults={
                    'bio': bio,
                    'experience_years': years,
                    'daily_wage': wage,
                    'jobs_done': jobs,
                    'is_verified': verified,
                    'is_active': True,
                },
            )
            worker.services.set([services[slug] for slug in service_slugs])
            worker.cities.set([cities[name] for name in city_names])

        User.objects.filter(username__in=('09130000008', '09130000009', '09130000015')).delete()

        authors = [
            self._user(phone, first, last, Profile.FARMER)
            for phone, first, last in AUTHORS
        ]
        Review.objects.filter(booking__isnull=True).delete()
        now = timezone.now()
        for index, worker in enumerate(WorkerProfile.objects.select_related('user')):
            for offset in (0, 2):
                rating, comment = REVIEW_TEXTS[(index + offset) % len(REVIEW_TEXTS)]
                review = Review.objects.create(
                    worker=worker,
                    farmer=authors[index % len(authors)],
                    rating=rating,
                    comment=comment,
                )
                Review.objects.filter(pk=review.pk).update(created_at=now - timedelta(days=index + offset))
            worker.refresh_rating()

        self.stdout.write(self.style.SUCCESS('Sample data is ready.'))
        self.stdout.write('Farmer: 09121111111 / demo1234')
        self.stdout.write('Worker: 09130000001 / demo1234')
        self.stdout.write('Site admin: 09124444444 / demo1234')
        self.stdout.write('Django admin: admin / demo1234')

    def _user(self, phone, first, last, role):
        User = get_user_model()
        name = f'{first} {last}'.strip()
        user, _ = User.objects.get_or_create(
            username=phone,
            defaults={'first_name': first, 'last_name': last, 'name': name},
        )
        user.first_name = first
        user.last_name = last
        user.name = name
        user.set_password(PASSWORD)
        user.save()
        Profile.objects.update_or_create(user=user, defaults={'role': role, 'phone': phone})
        return user
