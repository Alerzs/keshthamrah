import re
from io import BytesIO

from django import forms
from django.contrib import admin, messages
from django.contrib.admin.options import IncorrectLookupParameters
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.forms import UserChangeForm, UserCreationForm
from django.core.exceptions import PermissionDenied
from django.db import models
from django.http import HttpResponse
from django.shortcuts import redirect
from django.utils import timezone
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from .dates import to_jalali
from .forms import JalaliDateTimeWidget, JalaliDateWidget
from .models import (
    AdminAccount, Booking, Category, City, LandOwner, Product, Review, Seller, Service, ServiceProvider, User,
    WallAd, WallCategory,
)
from .utils import normalize_phone

PROFILE_EXPORT_HEADERS = (
    'نام',
    'نام کاربری',
    'موبایل',
    'تاریخ عضویت',
    'فعال',
)


def profile_export_row(user):
    return (
        user.get_full_name(),
        user.username,
        user.phone,
        to_jalali(user.date_joined, 'Y/m/d H:i'),
        'بله' if user.is_active else 'خیر',
    )


def profiles_workbook(profiles):
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = 'کاربران'
    sheet.sheet_view.rightToLeft = True
    sheet.freeze_panes = 'A2'
    sheet.auto_filter.ref = f'A1:{get_column_letter(len(PROFILE_EXPORT_HEADERS))}1'
    header_font = Font(bold=True, color='FFFFFF')
    header_fill = PatternFill('solid', fgColor='0F766E')
    alignment = Alignment(horizontal='right', vertical='center')
    for column, title in enumerate(PROFILE_EXPORT_HEADERS, 1):
        cell = sheet.cell(1, column, title)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = alignment
    text_columns = {2, 3}
    for row_index, profile in enumerate(profiles, 2):
        for column, value in enumerate(profile_export_row(profile), 1):
            cell = sheet.cell(row_index, column, value)
            cell.alignment = alignment
            if column in text_columns:
                cell.number_format = '@'
    for column in range(1, len(PROFILE_EXPORT_HEADERS) + 1):
        sheet.column_dimensions[get_column_letter(column)].width = 22
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


@admin.register(City)
class CityAdmin(admin.ModelAdmin):
    list_display = ('name', 'province', 'is_featured', 'featured_order')
    list_filter = ('province', 'is_featured')
    search_fields = ('name', 'province')


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'sort_order')
    prepopulated_fields = {'slug': ('name',)}


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'base_price', 'is_popular')
    list_filter = ('category', 'is_popular')
    search_fields = ('name',)
    prepopulated_fields = {'slug': ('name',)}


class SiteUserCreationForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = User
        fields = ('username', 'name')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].label = 'شماره تماس'
        self.fields['username'].help_text = 'نام کاربری همان شماره تماس است.'

    def clean_username(self):
        self.cleaned_data['username'] = normalize_phone(self.cleaned_data.get('username', ''))
        username = super().clean_username()
        if not re.fullmatch(r'09\d{9}', username):
            raise forms.ValidationError('شماره تماس را با ۰۹ و ۱۱ رقم وارد کنید.')
        return username


class SiteUserChangeForm(UserChangeForm):
    class Meta(UserChangeForm.Meta):
        model = User
        fields = ('username', 'name')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].label = 'شماره تماس'
        self.fields['username'].help_text = 'نام کاربری همان شماره تماس است.'

    def clean_username(self):
        username = normalize_phone(self.cleaned_data.get('username', ''))
        if re.fullmatch(r'09\d{9}', username):
            return username
        if self.instance.pk and self.instance.is_superuser:
            return username
        raise forms.ValidationError('شماره تماس را با ۰۹ و ۱۱ رقم وارد کنید.')


@admin.register(LandOwner)
class LandOwnerAdmin(admin.ModelAdmin):
    list_display = ('user', 'farm_city', 'farm_address', 'created_by')
    list_select_related = ('user', 'farm_city', 'created_by')
    search_fields = ('user__name', 'user__username', 'farm_address')
    list_filter = ('farm_city',)
    autocomplete_fields = ('user', 'farm_city', 'created_by')
    fields = ('user', 'farm_city', 'farm_address', 'farm_latitude', 'farm_longitude', 'created_by')

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'created_by':
            kwargs['queryset'] = AdminAccount.objects.order_by('name', 'username')
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(Seller)
class SellerAdmin(admin.ModelAdmin):
    list_display = ('store_name', 'user', 'store_city', 'store_address', 'store_phone', 'created_by')
    list_select_related = ('user', 'store_city', 'created_by')
    search_fields = ('store_name', 'user__name', 'user__username', 'store_address', 'store_phone')
    list_filter = ('store_city',)
    autocomplete_fields = ('user', 'store_city', 'created_by')
    fields = (
        'user', 'store_name', 'store_city', 'store_address', 'store_phone',
        'store_latitude', 'store_longitude', 'created_by',
    )

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'created_by':
            kwargs['queryset'] = AdminAccount.objects.order_by('name', 'username')
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'seller', 'price', 'unit', 'is_available', 'updated_at')
    list_select_related = ('seller__user',)
    list_filter = ('is_available', 'unit', 'seller__store_city')
    search_fields = ('name', 'description', 'seller__user__name', 'seller__user__username')
    autocomplete_fields = ('seller',)


@admin.register(ServiceProvider)
class ServiceProviderAdmin(admin.ModelAdmin):
    list_display = ('user', 'daily_wage', 'rating', 'jobs_done', 'is_verified', 'accepts_jobs', 'created_by')
    list_select_related = ('user', 'created_by')
    list_filter = ('is_verified', 'accepts_jobs', 'cities')
    search_fields = ('user__name', 'user__username', 'bio')
    filter_horizontal = ('services', 'cities')
    autocomplete_fields = ('user', 'created_by')
    fields = (
        'user', 'bio', 'experience_years', 'daily_wage', 'rating', 'review_count', 'jobs_done',
        'is_verified', 'accepts_jobs', 'services', 'cities', 'created_by',
    )

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'created_by':
            kwargs['queryset'] = AdminAccount.objects.order_by('name', 'username')
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


class AdminAccountAdminForm(forms.ModelForm):
    password = forms.CharField(
        label='رمز عبور',
        required=False,
        widget=forms.PasswordInput(render_value=False),
        help_text='هنگام ویرایش، اگر خالی بماند رمز فعلی حفظ می‌شود.',
    )

    class Meta:
        model = AdminAccount
        fields = ('username', 'name', 'is_active')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk is None:
            self.fields['password'].required = True

    def save(self, commit=True):
        account = super().save(commit=False)
        raw = self.cleaned_data.get('password')
        if raw:
            account.set_password(raw)
        if commit:
            account.save()
        return account


@admin.register(AdminAccount)
class AdminAccountAdmin(admin.ModelAdmin):
    form = AdminAccountAdminForm
    list_display = ('username', 'name', 'is_active', 'jalali_date_joined')
    search_fields = ('username', 'name')
    ordering = ('username',)
    fields = ('username', 'name', 'password', 'is_active', 'jalali_last_login', 'jalali_date_joined')
    readonly_fields = ('jalali_last_login', 'jalali_date_joined')

    @admin.display(description='آخرین ورود')
    def jalali_last_login(self, obj):
        return to_jalali(obj.last_login, 'Y/m/d H:i') or '—'

    @admin.display(description='تاریخ ایجاد')
    def jalali_date_joined(self, obj):
        return to_jalali(obj.date_joined, 'Y/m/d H:i')


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    form = SiteUserChangeForm
    add_form = SiteUserCreationForm
    change_list_template = 'admin/marketplace/user/change_list.html'
    fieldsets = (
        (None, {'fields': ('username', 'name', 'password')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('username', 'name', 'password1', 'password2'),
        }),
    )
    list_display = ('phone', 'name')
    list_filter = ()
    readonly_fields = ()
    search_fields = ('username', 'name')
    ordering = ('-date_joined',)
    filter_horizontal = ()
    actions = ()

    def get_urls(self):
        from django.urls import path

        info = self.opts.app_label, self.opts.model_name
        custom = [
            path(
                'export/',
                self.admin_site.admin_view(self.export_excel),
                name='%s_%s_export' % info,
            ),
        ]
        return custom + super().get_urls()

    def export_excel(self, request):
        if not self.has_view_permission(request):
            raise PermissionDenied
        try:
            profiles = self.get_changelist_instance(request).get_queryset(request)
        except IncorrectLookupParameters:
            messages.error(request, 'فیلتر خروجی معتبر نیست.')
            return redirect('admin:marketplace_user_changelist')
        stamp = to_jalali(timezone.localdate(), 'Y-m-d').translate(str.maketrans('۰۱۲۳۴۵۶۷۸۹', '0123456789'))
        response = HttpResponse(
            profiles_workbook(profiles),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        response['Content-Disposition'] = f'attachment; filename="profiles-{stamp or "export"}.xlsx"'
        return response

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        formfield = super().formfield_for_dbfield(db_field, request, **kwargs)
        if db_field.name == 'username' and formfield is not None:
            formfield.label = 'شماره تماس'
            formfield.help_text = 'نام کاربری همان شماره تماس است.'
        return formfield

    @admin.display(description='شماره تماس', ordering='username')
    def phone(self, obj):
        return obj.phone


class JalaliDateAdmin(admin.ModelAdmin):
    def formfield_for_dbfield(self, db_field, request, **kwargs):
        if type(db_field) is models.DateField:
            kwargs['widget'] = JalaliDateWidget()
            kwargs.setdefault('error_messages', {})['invalid'] = 'تاریخ جلالی معتبر نیست.'
        elif type(db_field) is models.DateTimeField and not db_field.auto_now and not db_field.auto_now_add:
            kwargs['widget'] = JalaliDateTimeWidget()
            kwargs.setdefault('error_messages', {})['invalid'] = 'تاریخ جلالی معتبر نیست.'
        return super().formfield_for_dbfield(db_field, request, **kwargs)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'farmer':
            kwargs['queryset'] = User.objects.filter(land_profile__isnull=False).order_by('name', 'username')
        elif db_field.name == 'worker':
            kwargs['queryset'] = User.objects.filter(service_profile__isnull=False).order_by('name', 'username')
        elif db_field.name == 'confirmed_by':
            kwargs['queryset'] = AdminAccount.objects.order_by('name', 'username')
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(Booking)
class BookingAdmin(JalaliDateAdmin):
    list_display = (
        'id', 'farmer', 'worker', 'service', 'city', 'jalali_work_date', 'status_label', 'admin_approved',
    )
    list_filter = ('status', 'admin_approved', 'city', 'service')
    list_select_related = ('farmer', 'worker', 'service', 'city', 'confirmed_by')
    search_fields = (
        'address', 'farmer__username', 'farmer__name',
        'worker__name', 'worker__username',
    )
    readonly_fields = ('jalali_created_at',)
    fieldsets = (
        ('درخواست', {'fields': (
            'farmer', 'worker', 'service', 'city', 'address', 'work_date', 'land_area', 'note', 'wage',
        )}),
        ('وضعیت', {'fields': ('status', 'admin_approved', 'rejection_reason', 'reported_at')}),
        ('بررسی', {'fields': ('confirmed_by', 'confirmed_at', 'jalali_created_at')}),
    )

    @admin.display(description='تاریخ مراجعه', ordering='work_date')
    def jalali_work_date(self, obj):
        return to_jalali(obj.work_date)

    @admin.display(description='وضعیت', ordering='status')
    def status_label(self, obj):
        return obj.admin_status_label

    @admin.display(description='زمان ثبت')
    def jalali_created_at(self, obj):
        return to_jalali(obj.created_at, 'Y/m/d H:i')


@admin.register(Review)
class ReviewAdmin(JalaliDateAdmin):
    list_display = ('farmer', 'worker', 'rating', 'jalali_created_at')
    list_filter = ('rating',)
    list_select_related = ('farmer', 'worker', 'booking')
    search_fields = ('farmer__name', 'farmer__username', 'worker__name', 'worker__username', 'comment')
    autocomplete_fields = ('booking',)
    fields = ('booking', 'farmer', 'worker', 'rating', 'comment', 'created_at')

    @admin.display(description='تاریخ ثبت', ordering='created_at')
    def jalali_created_at(self, obj):
        return to_jalali(obj.created_at, 'Y/m/d H:i')


@admin.register(WallCategory)
class WallCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'sort_order')
    search_fields = ('name',)
    ordering = ('sort_order', 'name')


@admin.register(WallAd)
class WallAdAdmin(admin.ModelAdmin):
    list_display = ('title', 'category', 'city', 'user', 'price', 'is_published', 'created_at')
    list_filter = ('is_published', 'category', 'city')
    list_select_related = ('category', 'city', 'user')
    search_fields = ('title', 'description', 'district', 'user__name', 'user__username')
    autocomplete_fields = ('user', 'category', 'city')
    readonly_fields = ('created_at',)
