from decimal import Decimal

from django.apps import apps
from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import AbstractUser, UserManager as AuthUserManager
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Avg, Count
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .dates import to_jalali
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

    FARMER = 'farmer'
    WORKER = 'worker'
    ADMIN = 'admin'
    ROLE_CHOICES = [
        (FARMER, 'صاحب زمین'),
        (WORKER, 'سرویس دهنده'),
        (ADMIN, 'ادمین'),
    ]

    name = models.CharField('نام', max_length=150, blank=True)
    role = models.CharField('نقش', max_length=10, choices=ROLE_CHOICES, blank=True, default='')
    phone = models.CharField('موبایل', max_length=11, blank=True, default='')
    farm_city = models.ForeignKey(
        'City', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='farmers', verbose_name='شهر زمین',
    )
    farm_address = models.CharField('آدرس زمین', max_length=255, blank=True, default='')
    farm_latitude = models.DecimalField(
        'عرض جغرافیایی زمین', max_digits=9, decimal_places=6, null=True, blank=True,
    )
    farm_longitude = models.DecimalField(
        'طول جغرافیایی زمین', max_digits=9, decimal_places=6, null=True, blank=True,
    )
    created_by = models.ForeignKey(
        'self', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='created_accounts', verbose_name='ثبت‌کننده',
        limit_choices_to={'role': ADMIN},
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
        'Service', blank=True, related_name='workers', verbose_name='حوزه کاری',
    )
    cities = models.ManyToManyField(
        'City', blank=True, related_name='workers', verbose_name='محل کار',
    )
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
        if self.role:
            return f'{label} — {self.get_role_display()}'
        return label

    def get_full_name(self):
        return (self.name or '').strip()

    def get_short_name(self):
        return self.get_full_name() or self.get_username()

    def clean(self):
        super().clean()
        if self.created_by_id and getattr(self.created_by, 'role', None) != self.ADMIN:
            raise ValidationError({'created_by': 'ثبت‌کننده باید ادمین باشد.'})
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
        if self.role == self.FARMER:
            pairs = [
                ('نام', bool((self.name or '').strip())),
                ('شماره موبایل', bool(self.phone)),
                ('شهر زمین', bool(self.farm_city_id)),
                ('آدرس دقیق زمین', len((self.farm_address or '').strip()) >= 8),
            ]
        elif self.role == self.WORKER:
            pairs = [
                ('نام', bool((self.name or '').strip())),
                ('شماره موبایل', bool(self.phone)),
                ('توضیح تجربه کاری', len((self.bio or '').strip()) >= 10),
                ('حوزه کاری', self.services.exists()),
                ('شهرهای محل کار', self.cities.exists()),
            ]
        else:
            pairs = [
                ('نام', bool((self.name or '').strip())),
                ('شماره موبایل', bool(self.phone)),
            ]
        return [{'label': label, 'done': done} for label, done in pairs]

    @property
    def completion_percent(self):
        steps = self.completion_steps()
        if not steps:
            return 100
        done = sum(1 for step in steps if step['done'])
        return round(100 * done / len(steps))

    @property
    def is_profile_complete(self):
        return self.completion_percent == 100

    def refresh_rating(self):
        data = self.reviews.aggregate(avg=Avg('rating'), total=Count('id'))
        average = data['avg'] or 0
        self.rating = Decimal(str(round(average, 1)))
        self.review_count = data['total'] or 0
        self.save(update_fields=['rating', 'review_count'])


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
        User, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='approved_jobs', verbose_name='ادمین بررسی‌کننده',
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
        limit_choices_to={'role': User.FARMER},
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
