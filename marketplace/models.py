from decimal import Decimal

from django.apps import apps
from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import AbstractBaseUser, AbstractUser, UserManager as AuthUserManager
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Avg, Count
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .dates import relative_fa, to_jalali
from .geo import OUTSIDE_IRAN, in_iran


class UserManager(AuthUserManager):
    def _create_user_object(self, username, email, password, **extra_fields):
        extra_fields.pop('email', None)
        if not username:
            raise ValueError('نام کاربری لازم است.')
        user_model = apps.get_model(self.model._meta.app_label, self.model._meta.object_name)
        username = user_model.normalize_username(username)
        user = self.model(username=username, **extra_fields)
        user.password = make_password(password)
        return user


class User(AbstractUser):
    first_name = None
    last_name = None
    email = None

    objects = UserManager()
    REQUIRED_FIELDS = []

    name = models.CharField('نام', max_length=150, blank=True)
    groups = models.ManyToManyField(
        'auth.Group',
        verbose_name=_('groups'),
        blank=True,
        help_text=_(
            'The groups this user belongs to. A user will get all permissions '
            'granted to each of their groups.'
        ),
        related_name='user_set',
        related_query_name='user',
        db_table='auth_user_groups',
    )
    user_permissions = models.ManyToManyField(
        'auth.Permission',
        verbose_name=_('user permissions'),
        blank=True,
        help_text=_('Specific permissions for this user.'),
        related_name='user_set',
        related_query_name='user',
        db_table='auth_user_user_permissions',
    )

    class Meta:
        db_table = 'auth_user'
        verbose_name = 'کاربر'
        verbose_name_plural = 'کاربران'

    def __str__(self):
        label = self.get_full_name() or self.username
        kind = self.get_role_display()
        if kind:
            return f'{label} — {kind}'
        return label

    def get_full_name(self):
        return (self.name or '').strip()

    def get_short_name(self):
        return self.get_full_name() or self.get_username()

    @property
    def phone(self):
        return self.username or ''

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        land = getattr(self, '_pending_land', None)
        if land is not None:
            land.user = self
            land.save()
            self._pending_land = None

    def _land(self):
        pending = getattr(self, '_pending_land', None)
        if pending is not None:
            return pending
        try:
            return self.land_profile
        except LandOwner.DoesNotExist:
            return None

    def _service(self):
        try:
            return self.service_profile
        except ServiceProvider.DoesNotExist:
            return None

    def _seller(self):
        try:
            return self.seller_profile
        except Seller.DoesNotExist:
            return None

    def _attached_profiles(self):
        return [
            profile for profile in (self._land(), self._service(), self._seller())
            if profile is not None
        ]

    def _edit_land(self):
        pending = getattr(self, '_pending_land', None)
        if pending is not None:
            return pending
        try:
            land = self.land_profile
        except LandOwner.DoesNotExist:
            land = LandOwner(user=self)
        self._pending_land = land
        return land

    @property
    def role(self):
        parts = []
        if self._land() is not None:
            parts.append('farmer')
        if self._service() is not None:
            parts.append('worker')
        if self._seller() is not None:
            parts.append('seller')
        if parts == ['farmer', 'worker']:
            return 'both'
        if len(parts) == 1:
            return parts[0]
        return '+'.join(parts)

    def get_role_display(self):
        labels = []
        if self._land() is not None:
            labels.append('صاحب زمین')
        if self._service() is not None:
            labels.append('سرویس‌دهنده')
        if self._seller() is not None:
            labels.append('فروشنده')
        if labels == ['صاحب زمین', 'سرویس‌دهنده']:
            return 'صاحب زمین و سرویس‌دهنده'
        if not labels:
            return ''
        if len(labels) == 1:
            return labels[0]
        if len(labels) == 2:
            return f'{labels[0]} و {labels[1]}'
        return f'{labels[0]}، {labels[1]} و {labels[2]}'

    @property
    def account_label(self):
        return self.get_role_display() or 'کاربر'

    @property
    def farm_city(self):
        land = self._land()
        return land.farm_city if land else None

    @farm_city.setter
    def farm_city(self, value):
        self._edit_land().farm_city = value

    @property
    def farm_city_id(self):
        land = self._land()
        return land.farm_city_id if land else None

    @property
    def farm_address(self):
        land = self._land()
        return land.farm_address if land else ''

    @farm_address.setter
    def farm_address(self, value):
        self._edit_land().farm_address = value

    @property
    def farm_latitude(self):
        land = self._land()
        return land.farm_latitude if land else None

    @farm_latitude.setter
    def farm_latitude(self, value):
        self._edit_land().farm_latitude = value

    @property
    def farm_longitude(self):
        land = self._land()
        return land.farm_longitude if land else None

    @farm_longitude.setter
    def farm_longitude(self, value):
        self._edit_land().farm_longitude = value

    @property
    def has_farm_location(self):
        land = self._land()
        return bool(land and land.has_farm_location)

    @property
    def has_saved_farm(self):
        land = self._land()
        return bool(land and land.has_saved_farm)

    @property
    def bio(self):
        profile = self._service()
        return profile.bio if profile else ''

    @property
    def experience_years(self):
        profile = self._service()
        return profile.experience_years if profile else 0

    @property
    def daily_wage(self):
        profile = self._service()
        return profile.daily_wage if profile else 0

    @property
    def rating(self):
        profile = self._service()
        return profile.rating if profile else Decimal('0')

    @property
    def review_count(self):
        profile = self._service()
        return profile.review_count if profile else 0

    @property
    def jobs_done(self):
        profile = self._service()
        return profile.jobs_done if profile else 0

    @property
    def is_verified(self):
        profile = self._service()
        return profile.is_verified if profile else False

    @property
    def accepts_jobs(self):
        profile = self._service()
        return profile.accepts_jobs if profile else False

    @property
    def services(self):
        profile = self._service()
        if profile is None:
            return Service.objects.none()
        return profile.services

    @property
    def cities(self):
        profile = self._service()
        if profile is None:
            return City.objects.none()
        return profile.cities

    @property
    def created_by(self):
        for profile in (self._land(), self._service(), self._seller()):
            if profile is not None and profile.created_by_id:
                return profile.created_by
        return None

    @property
    def initials(self):
        parts = (self.name or '').split()
        if not parts:
            return 'ک'
        first = parts[0][:1]
        last = parts[1][:1] if len(parts) > 1 else ''
        return f'{first}{last}'

    @property
    def avatar_class(self):
        palette = [
            'bg-teal-600',
            'bg-emerald-600',
            'bg-cyan-700',
            'bg-lime-700',
            'bg-amber-600',
            'bg-orange-600',
            'bg-sky-700',
            'bg-green-700',
        ]
        return palette[(self.pk or 0) % len(palette)]

    def completion_steps(self):
        profiles = self._attached_profiles()
        if len(profiles) == 1:
            return profiles[0].completion_steps()
        return [
            {'label': 'نام', 'done': bool((self.name or '').strip())},
            {'label': 'شماره موبایل', 'done': bool(self.phone)},
        ]

    @property
    def completion_percent(self):
        profiles = self._attached_profiles()
        if not profiles:
            return 100
        if len(profiles) == 1:
            return profiles[0].completion_percent
        return min(profile.completion_percent for profile in profiles)

    @property
    def is_profile_complete(self):
        return self.completion_percent == 100

    def refresh_rating(self):
        profile = self._service()
        if profile is not None:
            profile.refresh_rating()


class AdminAccountManager(models.Manager):
    def create_account(self, username, password, **extra_fields):
        if not username:
            raise ValueError('نام کاربری لازم است.')
        account = self.model(username=username, **extra_fields)
        account.set_password(password)
        account.save(using=self._db)
        return account


class AdminAccount(AbstractBaseUser):
    username = models.CharField('نام کاربری', max_length=150, unique=True)
    name = models.CharField('نام', max_length=150, blank=True, default='')
    is_active = models.BooleanField('فعال', default=True)
    date_joined = models.DateTimeField('تاریخ ایجاد', default=timezone.now)

    objects = AdminAccountManager()
    USERNAME_FIELD = 'username'
    REQUIRED_FIELDS = []

    class Meta:
        verbose_name = 'ادمین'
        verbose_name_plural = 'ادمین‌ها'
        ordering = ['username']

    def __str__(self):
        return self.get_full_name() or self.username

    def get_full_name(self):
        return (self.name or '').strip() or self.username

    def get_short_name(self):
        return self.get_full_name()

    @property
    def is_staff(self):
        return self.is_active

    @property
    def is_superuser(self):
        return self.is_active

    def has_perm(self, perm, obj=None):
        return self.is_active

    def has_module_perms(self, app_label):
        return self.is_active

    def get_all_permissions(self, obj=None):
        return set()

    @property
    def role(self):
        return 'admin'

    def get_role_display(self):
        return 'ادمین'

    @property
    def account_label(self):
        return 'ادمین'

    @property
    def phone(self):
        return ''

    @property
    def initials(self):
        parts = (self.name or self.username or '').split()
        if not parts:
            return 'ا'
        first = parts[0][:1]
        last = parts[1][:1] if len(parts) > 1 else ''
        return f'{first}{last}'

    @property
    def completion_percent(self):
        return 100


class LandOwner(models.Model):
    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name='land_profile', verbose_name='کاربر',
    )
    farm_city = models.ForeignKey(
        'City', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='land_owners', verbose_name='شهر زمین',
    )
    farm_address = models.CharField('آدرس زمین', max_length=255, blank=True, default='')
    farm_latitude = models.DecimalField(
        'عرض جغرافیایی زمین', max_digits=9, decimal_places=6, null=True, blank=True,
    )
    farm_longitude = models.DecimalField(
        'طول جغرافیایی زمین', max_digits=9, decimal_places=6, null=True, blank=True,
    )
    created_by = models.ForeignKey(
        AdminAccount, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='created_land_owners', verbose_name='ثبت‌کننده',
    )

    class Meta:
        verbose_name = 'صاحب زمین'
        verbose_name_plural = 'صاحبان زمین'

    def __str__(self):
        return self.user.get_full_name() or self.user.username

    def clean(self):
        super().clean()
        lat = self.farm_latitude
        lng = self.farm_longitude
        if lat is None and lng is None:
            return
        if lat is None or lng is None:
            raise ValidationError('برای ثبت موقعیت روی نقشه، عرض و طول جغرافیایی را با هم مشخص کنید.')
        if not in_iran(lat, lng):
            raise ValidationError({'farm_latitude': OUTSIDE_IRAN})

    @property
    def has_farm_location(self):
        return self.farm_latitude is not None and self.farm_longitude is not None

    @property
    def has_saved_farm(self):
        return bool(self.farm_city_id) and len((self.farm_address or '').strip()) >= 8

    def completion_steps(self):
        user = self.user
        pairs = [
            ('نام', bool((user.name or '').strip())),
            ('شماره موبایل', bool(user.phone)),
            ('شهر زمین', bool(self.farm_city_id)),
            ('آدرس دقیق زمین', len((self.farm_address or '').strip()) >= 8),
        ]
        return [{'label': label, 'done': done} for label, done in pairs]

    @property
    def completion_percent(self):
        steps = self.completion_steps()
        done = sum(1 for step in steps if step['done'])
        return round(100 * done / len(steps))

    @property
    def is_profile_complete(self):
        return self.completion_percent == 100


class ServiceProvider(models.Model):
    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name='service_profile', verbose_name='کاربر',
    )
    bio = models.TextField('درباره تجربه کاری', blank=True, default='')
    experience_years = models.PositiveSmallIntegerField(
        'سابقه (سال)', default=0, validators=[MaxValueValidator(60)],
    )
    daily_wage = models.PositiveIntegerField('دستمزد روزانه (تومان)', default=0)
    rating = models.DecimalField('امتیاز', max_digits=2, decimal_places=1, default=0)
    review_count = models.PositiveIntegerField('تعداد نظر', default=0)
    jobs_done = models.PositiveIntegerField('کارهای انجام‌شده', default=0)
    is_verified = models.BooleanField('هویت تأیید شده', default=False)
    accepts_jobs = models.BooleanField('آماده دریافت کار', default=True)
    services = models.ManyToManyField(
        'Service', blank=True, related_name='providers', verbose_name='حوزه کاری',
    )
    cities = models.ManyToManyField(
        'City', blank=True, related_name='providers', verbose_name='محل کار',
    )
    created_by = models.ForeignKey(
        AdminAccount, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='created_service_providers', verbose_name='ثبت‌کننده',
    )

    class Meta:
        verbose_name = 'سرویس‌دهنده'
        verbose_name_plural = 'سرویس‌دهندگان'

    def __str__(self):
        return self.user.get_full_name() or self.user.username

    def completion_steps(self):
        user = self.user
        pairs = [
            ('نام', bool((user.name or '').strip())),
            ('شماره موبایل', bool(user.phone)),
            ('توضیح تجربه کاری', len((self.bio or '').strip()) >= 10),
            ('حوزه کاری', bool(self.pk) and self.services.exists()),
            ('شهرهای محل کار', bool(self.pk) and self.cities.exists()),
        ]
        return [{'label': label, 'done': done} for label, done in pairs]

    @property
    def completion_percent(self):
        steps = self.completion_steps()
        done = sum(1 for step in steps if step['done'])
        return round(100 * done / len(steps))

    @property
    def is_profile_complete(self):
        return self.completion_percent == 100

    def refresh_rating(self):
        data = self.user.reviews.aggregate(avg=Avg('rating'), total=Count('id'))
        average = data['avg'] or 0
        self.rating = Decimal(str(round(average, 1)))
        self.review_count = data['total'] or 0
        self.save(update_fields=['rating', 'review_count'])


class Seller(models.Model):
    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name='seller_profile', verbose_name='کاربر',
    )
    store_name = models.CharField('نام فروشگاه', max_length=80)
    store_city = models.ForeignKey(
        'City', on_delete=models.PROTECT, related_name='sellers', verbose_name='شهر فروشگاه',
    )
    store_address = models.CharField('آدرس فروشگاه', max_length=255)
    store_latitude = models.DecimalField('عرض جغرافیایی فروشگاه', max_digits=9, decimal_places=6)
    store_longitude = models.DecimalField('طول جغرافیایی فروشگاه', max_digits=9, decimal_places=6)
    store_phone = models.CharField('شماره تماس فروشگاه', max_length=20, blank=True, default='')
    created_by = models.ForeignKey(
        AdminAccount, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='created_sellers', verbose_name='ثبت‌کننده',
    )

    class Meta:
        verbose_name = 'کاربر فروشنده'
        verbose_name_plural = 'کاربران فروشنده'

    def __str__(self):
        return self.display_name or self.user.username

    @property
    def display_name(self):
        return (self.store_name or '').strip() or self.user.get_full_name()

    def clean(self):
        super().clean()
        errors = {}
        if self.store_name is not None and 0 < len(self.store_name.strip()) < 2:
            errors['store_name'] = 'نام فروشگاه را کامل‌تر بنویسید.'
        if self.store_address is not None and len(self.store_address.strip()) < 8:
            errors['store_address'] = 'آدرس فروشگاه را دقیق‌تر بنویسید.'
        if (
            self.store_latitude is not None
            and self.store_longitude is not None
            and not in_iran(self.store_latitude, self.store_longitude)
        ):
            errors['store_latitude'] = OUTSIDE_IRAN
        if errors:
            raise ValidationError(errors)

    @property
    def has_store_location(self):
        return self.store_latitude is not None and self.store_longitude is not None

    @property
    def contact_phone(self):
        return (self.store_phone or '').strip() or self.user.phone

    def contact_lines(self):
        lines = []
        store_phone = (self.store_phone or '').strip()
        account_phone = (self.user.phone or '').strip()
        if store_phone:
            lines.append({'label': 'شماره فروشگاه', 'phone': store_phone})
        if account_phone and account_phone != store_phone:
            lines.append({'label': 'شماره فروشنده', 'phone': account_phone})
        elif account_phone and not lines:
            lines.append({'label': 'شماره فروشنده', 'phone': account_phone})
        return lines

    def completion_steps(self):
        user = self.user
        pairs = [
            ('شماره موبایل', bool(user.phone)),
            ('نام فروشگاه', len((self.store_name or '').strip()) >= 2),
            ('شهر فروشگاه', bool(self.store_city_id)),
            ('آدرس فروشگاه', len((self.store_address or '').strip()) >= 8),
            ('موقعیت فروشگاه', self.has_store_location),
        ]
        return [{'label': label, 'done': done} for label, done in pairs]

    @property
    def completion_percent(self):
        steps = self.completion_steps()
        done = sum(1 for step in steps if step['done'])
        return round(100 * done / len(steps))

    @property
    def is_profile_complete(self):
        return self.completion_percent == 100


class Product(models.Model):
    KILO = 'کیلو'
    PIECE = 'عدد'
    PACK = 'بسته'
    LITER = 'لیتر'
    UNIT_CHOICES = [
        (KILO, 'کیلو'),
        (PIECE, 'عدد'),
        (PACK, 'بسته'),
        (LITER, 'لیتر'),
    ]

    seller = models.ForeignKey(
        Seller, on_delete=models.CASCADE, related_name='products', verbose_name='فروشنده',
    )
    name = models.CharField('نام محصول', max_length=120)
    description = models.TextField('مشخصات')
    price = models.PositiveIntegerField('قیمت (تومان)', default=0)
    unit = models.CharField('واحد', max_length=12, choices=UNIT_CHOICES, default=KILO)
    image = models.ImageField('تصویر', upload_to='products/%Y/%m', blank=True)
    is_available = models.BooleanField('قابل عرضه در بازار', default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'محصول'
        verbose_name_plural = 'محصولات'
        ordering = ['-updated_at', '-pk']

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse('product_detail', args=[self.pk])


class City(models.Model):
    name = models.CharField('شهر', max_length=64, unique=True)
    province = models.CharField('استان', max_length=64)
    is_featured = models.BooleanField('شهر پربازدید', default=False)
    featured_order = models.PositiveSmallIntegerField('ترتیب نمایش', default=0)

    class Meta:
        verbose_name = 'شهر'
        verbose_name_plural = 'شهرها'
        ordering = ['province', 'name']

    def __str__(self):
        return f'{self.name} ({self.province})'


class Category(models.Model):
    name = models.CharField('نام', max_length=80)
    slug = models.SlugField(unique=True)
    description = models.CharField('توضیح', max_length=180)
    icon_bg = models.CharField(max_length=80, default='bg-teal-50 text-soil')
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        verbose_name = 'دسته‌بندی'
        verbose_name_plural = 'دسته‌بندی‌ها'
        ordering = ['sort_order', 'name']

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse('category', args=[self.slug])


class Service(models.Model):
    category = models.ForeignKey(
        Category, on_delete=models.CASCADE, related_name='services', verbose_name='دسته',
    )
    name = models.CharField('نام خدمت', max_length=120)
    slug = models.SlugField(unique=True)
    description = models.CharField('توضیح', max_length=220)
    base_price = models.PositiveIntegerField('شروع قیمت روزانه', default=0)
    gradient = models.CharField(max_length=80, blank=True)
    is_popular = models.BooleanField('پرتقاضا', default=False)
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        verbose_name = 'خدمت'
        verbose_name_plural = 'خدمات'
        ordering = ['sort_order', 'name']

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse('order', args=[self.slug])


class Booking(models.Model):
    PENDING = 'pending'
    CONFIRMED = 'confirmed'
    REJECTED = 'rejected'
    CANCELLED = 'cancelled'
    DONE = 'done'
    STATUS_CHOICES = [
        (PENDING, 'در انتظار پذیرش'),
        (CONFIRMED, 'پذیرفته شده'),
        (REJECTED, 'رد شده'),
        (CANCELLED, 'لغو شده'),
        (DONE, 'انجام شده'),
    ]
    STATUS_CLASSES = {
        PENDING: 'bg-amber-100 text-amber-800',
        CONFIRMED: 'bg-sky-100 text-sky-800',
        REJECTED: 'bg-rose-100 text-rose-700',
        CANCELLED: 'bg-slate-100 text-slate-600',
        DONE: 'bg-emerald-100 text-emerald-800',
    }

    farmer = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='bookings', verbose_name='صاحب زمین',
    )
    worker = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='jobs', verbose_name='سرویس دهنده',
    )
    service = models.ForeignKey(
        Service, on_delete=models.PROTECT, related_name='bookings', verbose_name='خدمت',
    )
    city = models.ForeignKey(City, on_delete=models.PROTECT, verbose_name='شهر')
    address = models.CharField('آدرس زمین', max_length=255)
    work_date = models.DateField('تاریخ مراجعه')
    land_area = models.DecimalField(
        'مساحت (هکتار)', max_digits=8, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(0)],
    )
    note = models.TextField('توضیح', blank=True)
    wage = models.PositiveIntegerField('دستمزد روزانه در زمان رزرو', default=0)
    status = models.CharField('وضعیت', max_length=12, choices=STATUS_CHOICES, default=PENDING)
    admin_approved = models.BooleanField('صلاحیت تأیید شده', default=False)
    rejection_reason = models.TextField('علت رد', blank=True, default='')
    reported_at = models.DateTimeField('زمان اعلام انجام', null=True, blank=True)
    confirmed_by = models.ForeignKey(
        AdminAccount, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='approved_bookings', verbose_name='ادمین بررسی‌کننده',
    )
    confirmed_at = models.DateTimeField('زمان بررسی صلاحیت', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'رزرو'
        verbose_name_plural = 'رزروها'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.service} — {to_jalali(self.work_date)}'

    def _build_stages(self, labels, current):
        failed = self.status in (self.REJECTED, self.CANCELLED)
        stages = []
        for index, label in enumerate(labels, start=1):
            if current > len(labels):
                state = 'done'
            elif failed:
                state = 'done' if index == 1 else 'muted'
            elif index < current:
                state = 'done'
            elif index == current:
                state = 'current'
            else:
                state = 'upcoming'
            stages.append({'label': label, 'state': state})
        return stages

    @property
    def public_progress_stages(self):
        labels = ['ثبت درخواست', 'پذیرش سرویس دهنده', 'اتمام کار', 'ثبت نظر']
        if self.status == self.DONE and self.existing_review:
            current = len(labels) + 1
        elif self.status == self.DONE:
            current = 4
        elif self.status == self.CONFIRMED:
            current = 3
        else:
            current = 2
        return self._build_stages(labels, current)

    @property
    def admin_progress_stages(self):
        labels = ['ثبت درخواست', 'تأیید صلاحیت', 'پذیرش سرویس دهنده', 'اتمام کار']
        if self.status == self.DONE:
            current = len(labels) + 1
        elif self.status == self.CONFIRMED:
            current = 4
        elif self.status == self.PENDING and self.admin_approved:
            current = 3
        elif self.status == self.PENDING:
            current = 2
        else:
            current = 1
        return self._build_stages(labels, current)

    @property
    def shows_worker_contact(self):
        return self.status in (self.CONFIRMED, self.DONE)

    @property
    def admin_status_label(self):
        if self.status == self.PENDING and not self.admin_approved:
            return 'در انتظار تأیید صلاحیت'
        if self.status == self.PENDING:
            return 'در انتظار پذیرش سرویس دهنده'
        return self.get_status_display()

    @property
    def admin_status_classes(self):
        if self.status == self.PENDING and not self.admin_approved:
            return 'bg-orange-100 text-orange-800'
        return self.status_classes

    @property
    def status_classes(self):
        return self.STATUS_CLASSES.get(self.status, 'bg-slate-100 text-slate-600')

    @property
    def existing_review(self):
        try:
            return self.review
        except Review.DoesNotExist:
            return None


class Review(models.Model):
    booking = models.OneToOneField(
        Booking, null=True, blank=True, on_delete=models.CASCADE, related_name='review',
    )
    worker = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reviews', verbose_name='سرویس دهنده')
    farmer = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='given_reviews', verbose_name='صاحب زمین',
    )
    rating = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    comment = models.TextField()
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = 'نظر'
        verbose_name_plural = 'نظرها'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.farmer.get_full_name()} — {self.rating}'


class WallCategory(models.Model):
    name = models.CharField('نام', max_length=80)
    slug = models.SlugField(unique=True)
    description = models.CharField('توضیح', max_length=160, blank=True)
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        verbose_name = 'دسته دیوار'
        verbose_name_plural = 'دسته‌های دیوار'
        ordering = ['sort_order', 'name']

    def __str__(self):
        return self.name


class WallAd(models.Model):
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='wall_ads', verbose_name='آگهی‌دهنده',
    )
    category = models.ForeignKey(
        WallCategory, on_delete=models.PROTECT, related_name='ads', verbose_name='دسته',
    )
    city = models.ForeignKey(
        City, on_delete=models.PROTECT, related_name='wall_ads', verbose_name='شهر',
    )
    district = models.CharField('روستا یا محله', max_length=80, blank=True, default='')
    title = models.CharField('عنوان', max_length=80)
    description = models.TextField('توضیحات')
    price = models.PositiveIntegerField('قیمت (تومان)', null=True, blank=True)
    price_note = models.CharField('توضیح قیمت', max_length=40, blank=True, default='')
    image = models.ImageField('عکس', upload_to='wall/%Y/%m', blank=True)
    is_published = models.BooleanField('روی دیوار', default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'آگهی دیوار'
        verbose_name_plural = 'آگهی‌های دیوار'
        ordering = ['-created_at', '-pk']

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse('wall_ad', args=[self.pk])

    @property
    def author_name(self):
        return self.user.get_full_name() or self.user.username

    @property
    def place_name(self):
        return (self.district or '').strip() or (self.city.name if self.city_id else '')

    @property
    def place_line(self):
        place = self.place_name
        when = relative_fa(self.created_at)
        if place:
            return f'{when} در {place}'
        return when
