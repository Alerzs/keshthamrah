from io import BytesIO

from django.contrib import admin, messages
from django.contrib.admin.options import IncorrectLookupParameters
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.core.exceptions import PermissionDenied
from django.db import models
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import redirect
from django.utils import timezone
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from .dates import to_jalali
from .forms import JalaliDateTimeWidget, JalaliDateWidget
from .models import Booking, Category, City, Review, Service, User

PROFILE_EXPORT_HEADERS = (
    'نام',
    'نام کاربری',
    'نقش',
    'موبایل',
    'شهر زمین',
    'استان',
    'آدرس زمین',
    'عرض جغرافیایی',
    'طول جغرافیایی',
    'ثبت‌کننده',
    'تاریخ عضویت',
    'سابقه (سال)',
    'دستمزد روزانه',
    'امتیاز',
    'کارهای انجام‌شده',
    'هویت تأیید شده',
    'آماده دریافت کار',
    'حوزه کاری',
    'شهرهای محل کار',
)


def profile_export_row(user):
    city = user.farm_city
    created_by = user.created_by
    return (
        user.get_full_name(),
        user.username,
        user.get_role_display(),
        user.phone,
        city.name if city else '',
        city.province if city else '',
        user.farm_address,
        '' if user.farm_latitude is None else str(user.farm_latitude),
        '' if user.farm_longitude is None else str(user.farm_longitude),
        created_by.get_full_name() if created_by else '',
        to_jalali(user.date_joined, 'Y/m/d H:i'),
        user.experience_years,
        user.daily_wage,
        str(user.rating),
        user.jobs_done,
        'بله' if user.is_verified else 'خیر',
        'بله' if user.accepts_jobs else 'خیر',
        '، '.join(user.services.values_list('name', flat=True)),
        '، '.join(user.cities.values_list('name', flat=True)),
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
    text_columns = {2, 4}
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


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    change_list_template = 'admin/marketplace/user/change_list.html'
    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        ('اطلاعات شخصی', {'fields': ('name', 'role', 'phone', 'created_by')}),
        ('زمین', {'fields': ('farm_city', 'farm_address', 'farm_latitude', 'farm_longitude')}),
        ('سرویس‌دهنده', {'fields': (
            'bio', 'experience_years', 'daily_wage', 'rating', 'review_count', 'jobs_done',
            'is_verified', 'accepts_jobs', 'services', 'cities',
        )}),
        ('دسترسی‌ها', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('تاریخ‌ها', {'fields': ('jalali_last_login', 'jalali_date_joined')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('username', 'usable_password', 'password1', 'password2'),
        }),
        ('اطلاعات شخصی', {'fields': ('name', 'role', 'phone', 'created_by')}),
        ('زمین', {'fields': ('farm_city', 'farm_address', 'farm_latitude', 'farm_longitude')}),
        ('سرویس‌دهنده', {'fields': (
            'bio', 'experience_years', 'daily_wage', 'is_verified', 'accepts_jobs', 'services', 'cities',
        )}),
        ('دسترسی‌ها', {'fields': ('is_active', 'is_staff', 'is_superuser')}),
    )
    list_display = (
        'username', 'name', 'role_label', 'phone', 'farm_city',
        'daily_wage', 'rating', 'jobs_done', 'is_verified', 'accepts_jobs', 'is_active',
    )
    list_filter = ('role', 'is_staff', 'is_active', 'is_verified', 'accepts_jobs', 'farm_city', 'cities')
    list_select_related = ('farm_city', 'created_by')
    readonly_fields = ('rating', 'review_count', 'jalali_last_login', 'jalali_date_joined')
    search_fields = ('username', 'name', 'phone', 'farm_address', 'bio')
    ordering = ('-date_joined',)
    filter_horizontal = ('services', 'cities', 'groups', 'user_permissions')
    actions = ('verify_workers',)

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

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'created_by':
            kwargs['queryset'] = User.objects.filter(role=User.ADMIN).order_by('name', 'username')
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        formfield = super().formfield_for_dbfield(db_field, request, **kwargs)
        if db_field.name == 'username' and formfield is not None:
            formfield.label = 'نام کاربری'
            formfield.help_text = 'برای ورود به سایت، نام کاربری همان شماره موبایل ۱۱ رقمی است.'
        return formfield

    @admin.display(description='نقش', ordering='role')
    def role_label(self, obj):
        return obj.get_role_display() or '—'

    @admin.display(description='آخرین ورود')
    def jalali_last_login(self, obj):
        return to_jalali(obj.last_login, 'Y/m/d H:i') or '—'

    @admin.display(description='تاریخ عضویت')
    def jalali_date_joined(self, obj):
        return to_jalali(obj.date_joined, 'Y/m/d H:i')

    @admin.action(description='تأیید هویت سرویس‌دهندگان انتخاب‌شده')
    def verify_workers(self, request, queryset):
        updated = queryset.filter(role=User.WORKER).update(is_verified=True)
        self.message_user(request, f'هویت {updated} سرویس‌دهنده تأیید شد.')


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
            kwargs['queryset'] = User.objects.filter(role=User.FARMER).order_by('name', 'username')
        elif db_field.name == 'worker':
            kwargs['queryset'] = User.objects.filter(role=User.WORKER).order_by('name', 'username')
        elif db_field.name == 'confirmed_by':
            kwargs['queryset'] = User.objects.filter(Q(role=User.ADMIN) | Q(is_staff=True)).order_by('name')
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(Booking)
class BookingAdmin(JalaliDateAdmin):
    list_display = (
        'id', 'farmer', 'worker', 'service', 'city', 'jalali_work_date', 'status_label', 'admin_approved',
    )
    list_filter = ('status', 'admin_approved', 'city', 'service')
    list_select_related = ('farmer', 'worker', 'service', 'city', 'confirmed_by')
    search_fields = (
        'address', 'farmer__username', 'farmer__name', 'farmer__phone',
        'worker__phone', 'worker__name', 'worker__username',
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
    search_fields = ('farmer__name', 'farmer__username', 'farmer__phone', 'worker__name', 'worker__phone', 'comment')
    autocomplete_fields = ('booking',)
    fields = ('booking', 'farmer', 'worker', 'rating', 'comment', 'created_at')

    @admin.display(description='تاریخ ثبت', ordering='created_at')
    def jalali_created_at(self, obj):
        return to_jalali(obj.created_at, 'Y/m/d H:i')
