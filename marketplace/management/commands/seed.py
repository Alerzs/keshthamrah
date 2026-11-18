from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from marketplace.models import (
    AdminAccount, Booking, Category, City, LandOwner, Product, Review, Seller, Service, ServiceProvider,
    WallAd, WallCategory,
)

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

SELLERS = [
    (
        '09125550001', 'فرهاد', 'بازرگان', 'بازرگانی بازرگان', 'مشهد',
        'بلوار وکیل‌آباد، بازار روز کشاورزی، غرفه ۱۲',
        Decimal('36.297200'), Decimal('59.606700'), '05137654321',
        [
            ('بذر گندم پیشگام', 'بذر گواهی‌شده برای کشت پاییزه. هر سفارش از کیسه ۲۵ کیلویی تحویل می‌شود.', 185000, Product.KILO),
            ('کود اوره', 'کود سفید پریل در کیسه ۵۰ کیلویی. تحویل از انبار مشهد.', 42000, Product.KILO),
        ],
    ),
    (
        '09125550002', 'زهرا', 'گلستان', 'نهالستان گلستان', 'شیراز',
        'جاده مرودشت، نهالستان گلستان، سوله ۲',
        Decimal('29.591800'), Decimal('52.583700'), '',
        [
            ('نهال بادام', 'نهال یک‌ساله پیوندی، مناسب باغ دیم و آبی. ریشه پوشیده تحویل می‌شود.', 250000, Product.PIECE),
            ('سم کنه‌کش', 'کنه‌کش تماسی برای باغ مرکبات. بطری یک لیتری با برگه مصرف.', 310000, Product.LITER),
        ],
    ),
]

WALL_CATEGORIES = [
    ('محصولات کشاورزی', 'crops', 'گندم، میوه، سبزی و محصول آماده فروش', 1),
    ('زمین و باغ', 'land', 'فروش و اجاره زمین، باغ و گلخانه', 2),
    ('ادوات و ماشین‌آلات', 'machinery', 'تراکتور، کمباین و ابزار مزرعه', 3),
    ('نهاده، کود و سم', 'inputs', 'بذر، کود، سم و خوراک', 4),
    ('دام و طیور', 'livestock', 'دام، طیور، زنبور و آبزی', 5),
    ('آبیاری و تجهیزات', 'irrigation', 'لوله، پمپ، نوار تیپ و قطره‌ای', 6),
]

WALL_ADS = [
    (
        '09121111111', 'crops', 'مشهد', 'وکیل‌آباد',
        'گندم دیم درجه یک، تحویل سیلو',
        'ده تن گندم دیم تمیز، تحویل از انبار مشهد. امکان بازدید پیش از خرید هست.',
        18500, 'هر کیلو', 3000,
    ),
    (
        '09125550001', 'inputs', 'مشهد', 'بازار روز',
        'کود اوره کیسه ۵۰ کیلویی',
        'کود سفید پریل در کیسه ۵۰ کیلویی. تحویل از انبار بازار روز کشاورزی مشهد.',
        42000, 'هر کیسه', 45,
    ),
    (
        '09130000001', 'machinery', 'مشهد', 'نیشابور',
        'تراکتور رومانی ۲۸۵ سالم',
        'تراکتور رومانی ۲۸۵ با لاستیک نو و مدارک کامل. بازدید در نیشابور، تحویل مشهد.',
        780000000, '', 6000,
    ),
    (
        '09122000001', 'land', 'مشهد', 'طرقبه',
        'اجاره زمین کشاورزی ۱۲ هکتار',
        'زمین آبی دوازده هکتاری با دسترسی جاده. اجاره برای یک سال زراعی، آب چاه موجود است.',
        None, 'سال زراعی', 500,
    ),
    (
        '09125550002', 'crops', 'شیراز', 'مرودشت',
        'نهال بادام پیوندی یک‌ساله',
        'نهال بادام پیوندی ریشه پر، مناسب باغ دیم و آبی. تحویل از نهالستان مرودشت.',
        250000, 'هر اصله', 180,
    ),
    (
        '09130000004', 'machinery', 'اصفهان', 'زیار',
        'کمباین جاندیر کارکرده',
        'کمباین جاندیر آماده فصل برداشت، سرویس‌شده و با راننده آشنا به دشت اصفهان.',
        3200000000, '', 10000,
    ),
    (
        '09130000005', 'crops', 'تبریز', 'خسروشاه',
        'سیب درختی درجه یک سردخانه',
        'سیب درختی درجه یک، خارج‌شده از سردخانه. فروش عمده برای بازار تبریز و اطراف.',
        28000, 'هر کیلو', 90,
    ),
    (
        '09130000007', 'livestock', 'ساری', 'فرح‌آباد',
        'گاو شیری هلشتاین، زایش دوم',
        'گاو شیری هلشتاین، زایش دوم، واکسن‌ها کامل است. بازدید در دامداری فرح‌آباد ساری.',
        260000000, '', 2500,
    ),
    (
        '09130000012', 'irrigation', 'رشت', 'کوچصفهان',
        'نوار تیپ آبیاری، حلقه ۱۰۰۰ متری',
        'نوار تیپ آبیاری قطره‌ای، حلقه هزار متری، مناسب باغ چای و مرکبات گیلان.',
        950000, 'هر حلقه', 800,
    ),
    (
        '09130000011', 'machinery', 'قزوین', 'الوند',
        'گاوآهن برگردان‌دار سه خیش',
        'گاوآهن برگردان‌دار سه خیش، سالم و رنگ‌شده. مناسب تراکتورهای سنگین دشت قزوین.',
        145000000, '', 9000,
    ),
    (
        '09130000014', 'inputs', 'اصفهان', 'خوراسگان',
        'سم کنه‌کش یک لیتری',
        'کنه‌کش تماسی برای باغ، بطری یک لیتری به همراه برگه مصرف. تحویل در خوراسگان.',
        310000, 'هر بطری', 70,
    ),
    (
        '09130000006', 'land', 'ارومیه', 'بالانج',
        'فروش باغ سیب ۳ هکتار',
        'باغ سیب سه هکتاری بارده با حقابه. سند و امکان بازدید در بالانج ارومیه فراهم است.',
        None, 'قیمت توافقی', 12000,
    ),
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

        self._land(self._user('09121111111', 'سامان', 'کریمی'))
        admin_account, _ = AdminAccount.objects.get_or_create(
            username='09124444444',
            defaults={'name': 'لیلا احمدی'},
        )
        admin_account.name = 'لیلا احمدی'
        admin_account.is_active = True
        admin_account.set_password(PASSWORD)
        admin_account.save()
        Account = get_user_model()
        admin, created = Account.objects.get_or_create(
            username='admin',
            defaults={'is_staff': True, 'is_superuser': True, 'name': 'مدیر'},
        )
        admin.is_staff = True
        admin.is_superuser = True
        admin.set_password(PASSWORD)
        admin.save()

        for item in WORKERS:
            phone, first, last, bio, years, wage, jobs, verified, service_slugs, city_names = item
            user = self._user(phone, first, last)
            provider, _ = ServiceProvider.objects.get_or_create(user=user)
            provider.bio = bio
            provider.experience_years = years
            provider.daily_wage = wage
            provider.jobs_done = jobs
            provider.is_verified = verified
            provider.accepts_jobs = True
            provider.save()
            provider.services.set([services[slug] for slug in service_slugs])
            provider.cities.set([cities[name] for name in city_names])

        for item in SELLERS:
            phone, first, last, store_name, city_name, address, lat, lng, store_phone, products = item
            self._seller(phone, first, last, store_name, cities[city_name], address, lat, lng, store_phone, products)

        Account.objects.filter(username__in=('09130000008', '09130000009', '09130000015')).delete()

        authors = [
            self._land(self._user(phone, first, last))
            for phone, first, last in AUTHORS
        ]
        Review.objects.filter(booking__isnull=True).delete()
        now = timezone.now()
        for index, worker in enumerate(
            Account.objects.filter(service_profile__isnull=False).order_by('-service_profile__jobs_done', 'pk')
        ):
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

        self._wall(cities)

        self.stdout.write(self.style.SUCCESS('Sample data is ready.'))
        self.stdout.write('Farmer: 09121111111 / demo1234')
        self.stdout.write('Worker: 09130000001 / demo1234')
        self.stdout.write('Seller: 09125550001 / demo1234')
        self.stdout.write('Site admin: 09124444444 / demo1234')
        self.stdout.write('Django admin: admin / demo1234')

    def _wall(self, cities):
        removed = WallCategory.objects.filter(slug__in=('jobs', 'services'))
        WallAd.objects.filter(category__in=removed).delete()
        removed.delete()
        categories = {}
        for name, slug, description, sort_order in WALL_CATEGORIES:
            category, _ = WallCategory.objects.update_or_create(
                slug=slug,
                defaults={'name': name, 'description': description, 'sort_order': sort_order},
            )
            categories[slug] = category
        now = timezone.now()
        for phone, slug, city_name, district, title, description, price, note, minutes_ago in WALL_ADS:
            user = get_user_model().objects.get(username=phone)
            ad, _ = WallAd.objects.update_or_create(
                user=user,
                title=title,
                defaults={
                    'category': categories[slug],
                    'city': cities[city_name],
                    'district': district,
                    'description': description,
                    'price': price,
                    'price_note': note,
                    'is_published': True,
                },
            )
            created = now - timedelta(minutes=minutes_ago)
            WallAd.objects.filter(pk=ad.pk).update(created_at=created)

    def _user(self, phone, first, last):
        Account = get_user_model()
        name = f'{first} {last}'.strip()
        user, _ = Account.objects.get_or_create(
            username=phone,
            defaults={'name': name},
        )
        user.name = name
        user.set_password(PASSWORD)
        user.save()
        return user

    def _land(self, user):
        LandOwner.objects.get_or_create(user=user)
        return user

    def _seller(self, phone, first, last, store_name, city, address, lat, lng, store_phone, products):
        user = self._user(phone, first, last)
        seller, _ = Seller.objects.update_or_create(
            user=user,
            defaults={
                'store_name': store_name,
                'store_city': city,
                'store_address': address,
                'store_latitude': lat,
                'store_longitude': lng,
                'store_phone': store_phone,
            },
        )
        for name, description, price, unit in products:
            Product.objects.update_or_create(
                seller=seller,
                name=name,
                defaults={
                    'description': description,
                    'price': price,
                    'unit': unit,
                    'is_available': True,
                },
            )
        return seller
