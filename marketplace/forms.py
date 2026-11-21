import re
from decimal import Decimal

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.utils import timezone
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from .dates import (
    JALALI_MONTHS,
    fa_digits,
    gregorian_from_jalali,
    jalali_parts,
    jalali_year_span,
)
from .models import (
    AdminAccount, Booking, City, LandOwner, Product, Seller, Service, ServiceProvider, WallAd, WallCategory,
)
from .utils import normalize_phone

INPUT_CLASS = (
    'w-full rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm outline-none '
    'transition focus:border-teal-500 focus:bg-white focus:ring-4 focus:ring-teal-100'
)

_PASSWORD_TOGGLE = mark_safe(
    '<button type="button" class="password-toggle" aria-label="نمایش رمز" aria-pressed="false">'
    '<svg class="eye-open h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">'
    '<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>'
    '</svg>'
    '<svg class="eye-off hidden h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">'
    '<path d="M3 3l18 18"/><path d="M10.6 10.6a2 2 0 002.8 2.8"/>'
    '<path d="M9.9 5.1A10.8 10.8 0 0112 5c6.5 0 10 7 10 7a18.5 18.5 0 01-3.2 4.2"/>'
    '<path d="M6.1 6.1C3.8 7.8 2 12 2 12s3.5 7 10 7a10.8 10.8 0 004.1-.8"/>'
    '</svg>'
    '</button>'
)


class JalaliDateWidget(forms.MultiWidget):
    template_name = 'marketplace/widgets/jalali_date.html'

    def id_for_label(self, id_):
        return f'{id_}_0' if id_ else ''

    def __init__(self, attrs=None):
        widgets = [forms.Select() for _ in range(3)]
        super().__init__(widgets, attrs)

    def get_context(self, name, value, attrs):
        self._fill_choices(self._selected_year(value))
        return super().get_context(name, value, attrs)

    def _selected_year(self, value):
        if isinstance(value, (list, tuple)):
            return value[0] if value else None
        restored = _restore_invalid(value, 3)
        if restored is not None:
            return restored[0]
        try:
            parts = jalali_parts(value)
        except (TypeError, ValueError):
            return None
        return parts[0] if parts else None

    def decompress(self, value):
        restored = _restore_invalid(value, 3)
        if restored is not None:
            return restored
        if not value:
            return [None, None, None]
        try:
            parts = jalali_parts(value)
        except (TypeError, ValueError):
            return [None, None, None]
        if not parts:
            return [None, None, None]
        return list(parts[:3])

    def value_from_datadict(self, data, files, name):
        return _jalali_from_datadict(data, name, 3)

    def _fill_choices(self, selected_year):
        self.widgets[0].choices = [('', 'سال')] + [
            (str(year), fa_digits(year)) for year in jalali_year_span(selected_year)
        ]
        self.widgets[1].choices = [('', 'ماه')] + [
            (str(month), name) for month, name in enumerate(JALALI_MONTHS) if month
        ]
        self.widgets[2].choices = [('', 'روز')] + [
            (str(day), fa_digits(day)) for day in range(1, 32)
        ]
        for widget, label in zip(self.widgets, ('سال', 'ماه', 'روز')):
            widget.attrs['aria-label'] = label


class JalaliDateTimeWidget(JalaliDateWidget):
    def __init__(self, attrs=None):
        forms.MultiWidget.__init__(self, [forms.Select() for _ in range(5)], attrs)

    def decompress(self, value):
        restored = _restore_invalid(value, 5)
        if restored is not None:
            return restored
        if not value:
            return [None, None, None, None, None]
        try:
            parts = jalali_parts(value)
        except (TypeError, ValueError):
            return [None, None, None, None, None]
        if not parts:
            return [None, None, None, None, None]
        if len(parts) == 3:
            return [*parts, '0', '0']
        return list(parts)

    def value_from_datadict(self, data, files, name):
        return _jalali_from_datadict(data, name, 5, with_time=True)

    def _fill_choices(self, selected_year):
        super()._fill_choices(selected_year)
        self.widgets[3].choices = [('', 'ساعت')] + [
            (str(hour), fa_digits(f'{hour:02d}')) for hour in range(24)
        ]
        self.widgets[4].choices = [('', 'دقیقه')] + [
            (str(minute), fa_digits(f'{minute:02d}')) for minute in range(60)
        ]
        self.widgets[3].attrs['aria-label'] = 'ساعت'
        self.widgets[4].attrs['aria-label'] = 'دقیقه'


def _restore_invalid(value, count):
    if not isinstance(value, str) or not value.startswith('invalid:'):
        return None
    bits = value.split(':')[1:]
    bits = (bits + [''] * count)[:count]
    return [bit or None for bit in bits]


def _jalali_from_datadict(data, name, count, with_time=False):
    parts = [data.get(f'{name}_{index}') for index in range(count)]
    if any(part not in (None, '') for part in parts):
        token = 'invalid:' + ':'.join(part or '' for part in parts)
        if not all(part not in (None, '') for part in parts):
            return token
        if with_time:
            gregorian = gregorian_from_jalali(*parts[:3], hour=parts[3], minute=parts[4])
            return gregorian.isoformat() if gregorian else token
        gregorian = gregorian_from_jalali(*parts[:3])
        return gregorian.isoformat() if gregorian else token
    single = data.get(name)
    if single not in (None, ''):
        return single
    return None


class PasswordToggleInput(forms.PasswordInput):
    def render(self, name, value, attrs=None, renderer=None):
        return format_html(
            '<div class="password-field">{}{}</div>',
            super().render(name, value, attrs, renderer),
            _PASSWORD_TOGGLE,
        )


class RegisterForm(forms.Form):
    name = forms.CharField(label='نام', max_length=150)
    phone = forms.CharField(label='شماره موبایل', max_length=20)
    password = forms.CharField(label='رمز عبور', widget=PasswordToggleInput)
    password2 = forms.CharField(label='تکرار رمز عبور', widget=PasswordToggleInput)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs['class'] = INPUT_CLASS
        self.fields['phone'].widget.attrs.update({'dir': 'ltr', 'inputmode': 'numeric', 'placeholder': '0912...'})

    def clean_phone(self):
        phone = normalize_phone(self.cleaned_data['phone'])
        if not re.fullmatch(r'09\d{9}', phone):
            raise forms.ValidationError('شماره موبایل را با ۰۹ و ۱۱ رقم وارد کنید.')
        if get_user_model().objects.filter(username=phone).exists() or AdminAccount.objects.filter(username=phone).exists():
            raise forms.ValidationError('این شماره قبلاً ثبت شده است.')
        return phone

    def clean_name(self):
        name = self.cleaned_data['name'].strip()
        if not name:
            raise forms.ValidationError('نام را وارد کنید.')
        return name

    def clean(self):
        cleaned = super().clean()
        password = cleaned.get('password')
        if password:
            validate_password(password)
        if password and cleaned.get('password2') and password != cleaned.get('password2'):
            self.add_error('password2', 'تکرار رمز عبور یکسان نیست.')
        return cleaned

    def save(self):
        data = self.cleaned_data
        user = get_user_model().objects.create_user(
            username=data['phone'],
            password=data['password'],
            name=data['name'],
        )
        return user


class AdminAccountForm(forms.Form):
    ROLE_FARMER = 'farmer'
    ROLE_SELLER = 'seller'
    ROLE_WORKER = 'worker'
    ROLE_CHOICES = (
        (ROLE_FARMER, 'صاحب زمین'),
        (ROLE_SELLER, 'فروشنده'),
        (ROLE_WORKER, 'سرویس‌دهنده'),
    )

    role = forms.ChoiceField(
        label='نوع کاربر',
        choices=ROLE_CHOICES,
        widget=forms.RadioSelect,
        error_messages={'required': 'نوع کاربر را انتخاب کنید.'},
    )
    name = forms.CharField(label='نام', max_length=150)
    username = forms.CharField(label='شماره تماس', max_length=20)
    password = forms.CharField(label='رمز عبور', widget=PasswordToggleInput)
    password2 = forms.CharField(label='تکرار رمز عبور', required=False, widget=PasswordToggleInput)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs['class'] = INPUT_CLASS
        self.fields['username'].widget.attrs.update({
            'dir': 'ltr', 'inputmode': 'numeric', 'placeholder': '0912...',
        })

    def clean_name(self):
        name = self.cleaned_data['name'].strip()
        if not name:
            raise forms.ValidationError('نام را وارد کنید.')
        return name

    def clean_username(self):
        phone = normalize_phone(self.cleaned_data['username'])
        if not re.fullmatch(r'09\d{9}', phone):
            raise forms.ValidationError('شماره تماس را با ۰۹ و ۱۱ رقم وارد کنید. نام کاربری همان شماره است.')
        if get_user_model().objects.filter(username=phone).exists() or AdminAccount.objects.filter(username=phone).exists():
            raise forms.ValidationError('این شماره قبلاً ثبت شده است.')
        return phone

    def clean(self):
        cleaned = super().clean()
        password = cleaned.get('password')
        if password:
            validate_password(password)
        if password and cleaned.get('password2') and password != cleaned.get('password2'):
            self.add_error('password2', 'تکرار رمز عبور یکسان نیست.')
        return cleaned

    def save(self, created_by=None):
        data = self.cleaned_data
        return get_user_model().objects.create_user(
            username=data['username'],
            password=data['password'],
            name=data['name'],
        )


class LoginForm(forms.Form):
    username = forms.CharField(label='شماره موبایل یا نام کاربری')
    password = forms.CharField(label='رمز عبور', widget=PasswordToggleInput)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs['class'] = INPUT_CLASS
        self.fields['username'].widget.attrs.update({
            'dir': 'ltr',
            'placeholder': '0912... یا نام کاربری',
        })

    def clean_username(self):
        raw = (self.cleaned_data['username'] or '').strip()
        phone = normalize_phone(raw)
        if re.fullmatch(r'09\d{9}', phone):
            return phone
        if not raw:
            raise forms.ValidationError('نام کاربری را وارد کنید.')
        return raw


class OrderRequestForm(forms.Form):
    city = forms.ModelChoiceField(label='شهر محل زمین', queryset=City.objects.all(), empty_label='شهر را انتخاب کنید')
    address = forms.CharField(label='آدرس دقیق زمین', max_length=255)
    work_date = forms.DateField(
        label='تاریخ مراجعه',
        widget=JalaliDateWidget(),
        error_messages={'invalid': 'تاریخ جلالی معتبر نیست.'},
    )
    land_area = forms.DecimalField(
        label='مساحت زمین (هکتار)', required=False, min_value=0, max_value=10000, decimal_places=2,
    )
    note = forms.CharField(label='توضیح کار', required=False, widget=forms.Textarea(attrs={'rows': 4}), max_length=500)

    def __init__(self, *args, locked_location=None, **kwargs):
        self.locked_location = None
        if locked_location:
            city, address = locked_location
            address = address.strip()
            self.locked_location = (city, address)
            initial = dict(kwargs.get('initial') or {})
            initial['city'] = city.pk
            initial['address'] = address
            kwargs['initial'] = initial
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            field.widget.attrs['class'] = INPUT_CLASS
        self.fields['land_area'].widget.attrs.update({'dir': 'ltr', 'placeholder': 'مثلاً ۲.۵', 'step': '0.1'})
        self.fields['address'].widget.attrs['placeholder'] = 'روستا، جاده، نام قطعه یا نشانه محلی'
        self.fields['note'].widget.attrs['placeholder'] = 'نوع محصول، ساعت حضور، ابزار موردنیاز...'
        if self.locked_location:
            city, _address = self.locked_location
            self.fields['city'].queryset = City.objects.filter(pk=city.pk)
            self.fields['city'].empty_label = None
            self.fields['city'].disabled = True
            self.fields['address'].disabled = True
            for name in ('city', 'address'):
                css = self.fields[name].widget.attrs['class'].replace('bg-slate-50', 'cursor-not-allowed bg-slate-100 text-slate-500')
                self.fields[name].widget.attrs['class'] = css

    def clean_address(self):
        address = self.cleaned_data['address'].strip()
        if len(address) < 8:
            raise forms.ValidationError('آدرس را دقیق‌تر بنویسید تا سرویس دهنده زمین را پیدا کند.')
        return address

    def clean_work_date(self):
        value = self.cleaned_data['work_date']
        if value < timezone.localdate():
            raise forms.ValidationError('تاریخ نمی‌تواند در گذشته باشد.')
        return value


class BookForm(OrderRequestForm):
    service = forms.ModelChoiceField(label='نوع خدمت', queryset=Service.objects.none(), empty_label='خدمت را انتخاب کنید')

    def __init__(self, *args, worker, **kwargs):
        self.worker = worker
        super().__init__(*args, **kwargs)
        self.fields['service'].queryset = worker.services.all()
        if self.locked_location:
            city, _address = self.locked_location
            self.fields['city'].queryset = City.objects.filter(pk=city.pk)
        else:
            self.fields['city'].queryset = worker.cities.all()
        self.fields['service'].widget.attrs['class'] = INPUT_CLASS
        self.order_fields(['service', 'city', 'address', 'work_date', 'land_area', 'note'])

    def clean(self):
        cleaned = super().clean()
        service = cleaned.get('service')
        city = cleaned.get('city')
        if service and not self.worker.services.filter(pk=service.pk).exists():
            self.add_error('service', 'این سرویس دهنده در حوزه انتخاب‌شده فعالیت نمی‌کند.')
        if city and not self.worker.cities.filter(pk=city.pk).exists():
            self.add_error('city', 'این سرویس دهنده در شهر انتخاب‌شده کار نمی‌کند.')
        return cleaned

    def save(self, farmer):
        data = self.cleaned_data
        return Booking.objects.create(
            farmer=farmer,
            worker=self.worker,
            service=data['service'],
            city=data['city'],
            address=data['address'],
            work_date=data['work_date'],
            land_area=data.get('land_area') or None,
            note=(data.get('note') or '').strip(),
            wage=self.worker.daily_wage,
        )


class FarmerProfileForm(forms.ModelForm):
    class Meta:
        model = LandOwner
        fields = ['farm_city', 'farm_address', 'farm_latitude', 'farm_longitude']
        labels = {
            'farm_city': 'شهر زمین',
            'farm_address': 'آدرس دقیق زمین',
            'farm_latitude': 'عرض جغرافیایی',
            'farm_longitude': 'طول جغرافیایی',
        }
        widgets = {
            'farm_address': forms.Textarea(attrs={'rows': 3}),
            'farm_latitude': forms.HiddenInput,
            'farm_longitude': forms.HiddenInput,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['farm_city'].queryset = City.objects.all()
        self.fields['farm_city'].empty_label = 'شهر زمین را انتخاب کنید'
        self.fields['farm_city'].required = True
        self.fields['farm_address'].required = True
        for name, field in self.fields.items():
            if name not in ('farm_latitude', 'farm_longitude'):
                field.widget.attrs['class'] = INPUT_CLASS
        self.fields['farm_address'].widget.attrs['placeholder'] = 'روستا، جاده، نام قطعه یا نشانه محلی'
        self.fields['farm_address'].widget.attrs['class'] += ' min-h-28 resize-y'
        self.fields['farm_latitude'].required = False
        self.fields['farm_longitude'].required = False

    def clean_farm_address(self):
        address = self.cleaned_data['farm_address'].strip()
        if len(address) < 8:
            raise forms.ValidationError('آدرس را دقیق‌تر بنویسید تا سرویس دهنده زمین را پیدا کند.')
        return address


class WorkerSettingsForm(forms.ModelForm):
    class Meta:
        model = ServiceProvider
        fields = ['bio', 'experience_years', 'daily_wage', 'accepts_jobs']
        labels = {
            'bio': 'درباره تجربه کاری',
            'experience_years': 'سابقه کار (سال)',
            'daily_wage': 'دستمزد روزانه (تومان)',
            'accepts_jobs': 'آماده دریافت کار هستم',
        }
        help_texts = {
            'daily_wage': 'صفر یعنی دستمزد توافقی است.',
            'bio': 'بگویید در چه محصولی و چه کاری مهارت دارید.',
        }
        widgets = {'bio': forms.Textarea(attrs={'rows': 4})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if name != 'accepts_jobs':
                field.widget.attrs['class'] = INPUT_CLASS
        self.fields['bio'].widget.attrs['minlength'] = '10'
        self.fields['bio'].widget.attrs['class'] += ' min-h-32 resize-y'
        self.fields['daily_wage'].widget.attrs.update({'dir': 'ltr', 'min': '0'})
        self.fields['experience_years'].widget.attrs.update({'dir': 'ltr', 'min': '0', 'max': '60'})
        self.fields['accepts_jobs'].widget.attrs['class'] = 'h-5 w-5 accent-teal-600'

    def clean_bio(self):
        bio = self.cleaned_data['bio'].strip()
        if len(bio) < 10:
            raise forms.ValidationError('حداقل ۱۰ نویسه درباره تجربه کاری بنویسید.')
        return bio


class SellerProfileForm(forms.ModelForm):
    class Meta:
        model = Seller
        fields = ['store_name', 'store_city', 'store_address', 'store_phone', 'store_latitude', 'store_longitude']
        labels = {
            'store_name': 'نام فروشگاه',
            'store_city': 'شهر فروشگاه',
            'store_address': 'آدرس فروشگاه',
            'store_phone': 'شماره تماس فروشگاه',
            'store_latitude': 'عرض جغرافیایی',
            'store_longitude': 'طول جغرافیایی',
        }
        widgets = {
            'store_address': forms.Textarea(attrs={'rows': 3}),
            'store_latitude': forms.HiddenInput,
            'store_longitude': forms.HiddenInput,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['store_city'].queryset = City.objects.all()
        self.fields['store_city'].empty_label = 'شهر فروشگاه را انتخاب کنید'
        self.fields['store_phone'].required = False
        for name, field in self.fields.items():
            if name not in ('store_latitude', 'store_longitude'):
                field.widget.attrs['class'] = INPUT_CLASS
        self.fields['store_name'].widget.attrs['placeholder'] = 'مثلاً نهالستان گلستان'
        self.fields['store_name'].widget.attrs['maxlength'] = '80'
        self.fields['store_address'].widget.attrs['placeholder'] = 'خیابان، بازار، پلاک یا نشانه محلی فروشگاه'
        self.fields['store_address'].widget.attrs['class'] += ' min-h-28 resize-y'
        self.fields['store_phone'].widget.attrs.update({
            'dir': 'ltr',
            'inputmode': 'numeric',
            'placeholder': 'اختیاری، مثلاً ۰۲۱ یا ۰۹۱۲',
        })
        self.fields['store_latitude'].required = False
        self.fields['store_longitude'].required = False

    def clean_store_name(self):
        name = self.cleaned_data['store_name'].strip()
        if len(name) < 2:
            raise forms.ValidationError('نام فروشگاه را کامل‌تر بنویسید.')
        return name

    def clean_store_address(self):
        return self.cleaned_data['store_address'].strip()

    def clean_store_phone(self):
        raw = (self.cleaned_data.get('store_phone') or '').strip()
        if not raw:
            return ''
        phone = normalize_phone(raw)
        if not re.fullmatch(r'0\d{7,10}', phone):
            raise forms.ValidationError('شماره تماس فروشگاه را با پیش‌شماره شهر یا ۰۹ وارد کنید.')
        return phone

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('store_latitude') is None or cleaned.get('store_longitude') is None:
            self.add_error('store_latitude', 'موقعیت فروشگاه را روی نقشه مشخص کنید.')
        return cleaned


class ProductImageInput(forms.ClearableFileInput):
    template_name = 'marketplace/widgets/product_image.html'


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ['name', 'description', 'price', 'unit', 'image', 'is_available']
        labels = {
            'name': 'نام محصول',
            'description': 'مشخصات',
            'price': 'قیمت (تومان)',
            'unit': 'واحد',
            'image': 'تصویر',
            'is_available': 'در بازار نشان داده شود',
        }
        widgets = {
            'description': forms.Textarea(attrs={'rows': 5}),
            'image': ProductImageInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if name not in ('is_available', 'image'):
                field.widget.attrs['class'] = INPUT_CLASS
        self.fields['image'].required = False
        self.fields['image'].widget.attrs['accept'] = 'image/*'
        self.fields['description'].widget.attrs['class'] += ' min-h-32 resize-y'
        self.fields['description'].widget.attrs['placeholder'] = 'وزن، بسته‌بندی، نوع محصول و شرط تحویل'
        self.fields['price'].widget.attrs.update({'dir': 'ltr', 'min': '0'})
        self.fields['name'].widget.attrs['placeholder'] = 'مثلاً بذر گندم پیشگام'
        self.fields['is_available'].widget.attrs['class'] = 'h-5 w-5 accent-teal-600'

    def clean_name(self):
        name = self.cleaned_data['name'].strip()
        if len(name) < 2:
            raise forms.ValidationError('نام محصول را بنویسید.')
        return name

    def clean_description(self):
        description = self.cleaned_data['description'].strip()
        if len(description) < 10:
            raise forms.ValidationError('مشخصات محصول را حداقل در ۱۰ نویسه بنویسید.')
        return description

    def clean_image(self):
        image = self.cleaned_data.get('image')
        if not image or not hasattr(image, 'content_type'):
            return image
        if image.size > 5 * 1024 * 1024:
            raise forms.ValidationError('حجم تصویر باید کمتر از ۵ مگابایت باشد.')
        if not (image.content_type or '').startswith('image/'):
            raise forms.ValidationError('فقط فایل تصویری مجاز است.')
        return image


class ReviewForm(forms.Form):
    rating = forms.IntegerField(min_value=1, max_value=5, label='امتیاز')
    comment = forms.CharField(label='نظر', max_length=500, widget=forms.Textarea(attrs={'rows': 3, 'class': INPUT_CLASS}))


WALL_INPUT = (
    'w-full border border-[#e4e4e4] bg-white px-3 py-2.5 text-sm text-[#222] outline-none '
    'placeholder:text-[#9a9a9a] focus:border-[#a62626]'
)


class WallAdForm(forms.ModelForm):
    class Meta:
        model = WallAd
        fields = ['category', 'city', 'district', 'title', 'description', 'price', 'price_note', 'image']
        labels = {
            'category': 'دسته',
            'city': 'شهر',
            'district': 'روستا یا محله',
            'title': 'عنوان آگهی',
            'description': 'توضیحات',
            'price': 'قیمت (تومان)',
            'price_note': 'توضیح قیمت',
            'image': 'عکس آگهی',
        }
        widgets = {
            'description': forms.Textarea(attrs={'rows': 6}),
            'image': ProductImageInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['category'].queryset = WallCategory.objects.all()
        self.fields['category'].empty_label = 'انتخاب دسته'
        self.fields['city'].queryset = City.objects.all()
        self.fields['city'].empty_label = 'انتخاب شهر'
        self.fields['price'].required = False
        self.fields['image'].required = False
        self.fields['image'].widget.attrs['accept'] = 'image/*'
        self.fields['price_note'].help_text = 'مثلاً هر کیلو، روزانه یا پرداخت ماهانه'
        for name, field in self.fields.items():
            if name == 'image':
                continue
            field.widget.attrs['class'] = WALL_INPUT
        self.fields['title'].widget.attrs['placeholder'] = 'مثلاً بذر گندم پیشگام، کیسه ۲۵ کیلویی'
        self.fields['district'].widget.attrs['placeholder'] = 'مثلاً وکیل‌آباد یا روستای فرومد'
        self.fields['price'].widget.attrs.update({
            'dir': 'ltr',
            'inputmode': 'numeric',
            'min': '0',
            'placeholder': 'خالی یعنی توافقی',
        })
        self.fields['price_note'].widget.attrs['placeholder'] = 'هر کیلو'
        self.fields['description'].widget.attrs['placeholder'] = 'مقدار، کیفیت، محل تحویل و شرط بازدید را بنویسید'

    def clean_title(self):
        title = self.cleaned_data['title'].strip()
        if len(title) < 3:
            raise forms.ValidationError('عنوان آگهی را بنویسید.')
        return title

    def clean_description(self):
        description = self.cleaned_data['description'].strip()
        if len(description) < 20:
            raise forms.ValidationError('توضیحات را حداقل در ۲۰ نویسه بنویسید.')
        return description

    def clean_district(self):
        return (self.cleaned_data.get('district') or '').strip()

    def clean_price_note(self):
        return (self.cleaned_data.get('price_note') or '').strip()

    def clean_price(self):
        price = self.cleaned_data.get('price')
        if not price:
            return None
        return price

    def clean_image(self):
        image = self.cleaned_data.get('image')
        if not image or not hasattr(image, 'content_type'):
            return image
        if image.size > 5 * 1024 * 1024:
            raise forms.ValidationError('حجم تصویر باید کمتر از ۵ مگابایت باشد.')
        if not (image.content_type or '').startswith('image/'):
            raise forms.ValidationError('فقط فایل تصویری مجاز است.')
        return image
