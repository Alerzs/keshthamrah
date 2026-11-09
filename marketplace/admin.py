from io import BytesIO

from django.contrib import admin, messages
from django.contrib.admin.options import IncorrectLookupParameters
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
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
from .models import Booking, Category, City, Profile, Review, Service, User, WorkerProfile

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
)


def profile_export_row(profile):
    user = profile.user
    city = profile.farm_city
    created_by = profile.created_by
    return (
        user.get_full_name(),
        user.username,
        profile.get_role_display(),
        profile.phone,
        city.name if city else '',
        city.province if city else '',
        profile.farm_address,
        '' if profile.farm_latitude is None else str(profile.farm_latitude),
        '' if profile.farm_longitude is None else str(profile.farm_longitude),
        created_by.get_full_name() if created_by else '',
        to_jalali(user.date_joined, 'Y/m/d H:i'),
    )


def profiles_workbook(profiles):
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = 'پروفایل‌ها'
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


class WorkerInline(admin.StackedInline):
    model = WorkerProfile
    fk_name = 'user'
    filter_horizontal = ('services', 'cities')
    extra = 0


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        ('اطلاعات شخصی', {'fields': ('name', 'first_name', 'last_name', 'email')}),
        ('دسترسی‌ها', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('تاریخ‌ها', {'fields': ('jalali_last_login', 'jalali_date_joined')}),
    )
    list_display = ('username', 'name', 'is_staff')
    readonly_fields = ('jalali_last_login', 'jalali_date_joined')
    search_fields = ('username', 'name', 'first_name', 'last_name')
    inlines = [WorkerInline]

    @admin.display(description='آخرین ورود')
    def jalali_last_login(self, obj):
        return to_jalali(obj.last_login, 'Y/m/d H:i') or '—'

    @admin.display(description='تاریخ عضویت')
    def jalali_date_joined(self, obj):
        return to_jalali(obj.date_joined, 'Y/m/d H:i')


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    change_list_template = 'admin/marketplace/profile/change_list.html'
    list_display = ('user', 'role', 'phone', 'farm_city', 'created_by')
    list_filter = ('role',)
    list_select_related = ('user', 'farm_city', 'created_by')
    search_fields = ('phone', 'user__name', 'user__first_name', 'user__last_name', 'user__username')

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
            return redirect('admin:marketplace_profile_changelist')
        stamp = to_jalali(timezone.localdate(), 'Y-m-d').translate(str.maketrans('۰۱۲۳۴۵۶۷۸۹', '0123456789'))
        response = HttpResponse(
            profiles_workbook(profiles),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        response['Content-Disposition'] = f'attachment; filename="profiles-{stamp or "export"}.xlsx"'
        return response


@admin.register(WorkerProfile)
class WorkerProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'daily_wage', 'rating', 'is_verified', 'is_active')
    list_filter = ('is_verified', 'is_active', 'cities')
    search_fields = ('user__name', 'user__first_name', 'user__last_name', 'user__profile__phone')
    filter_horizontal = ('services', 'cities')
    actions = ('verify_workers',)

    @admin.action(description='تأیید هویت سرویس دهندگان انتخاب‌شده')
    def verify_workers(self, request, queryset):
        queryset.update(is_verified=True)


class JalaliDateAdmin(admin.ModelAdmin):
    def formfield_for_dbfield(self, db_field, request, **kwargs):
        if type(db_field) is models.DateField:
            kwargs['widget'] = JalaliDateWidget()
            kwargs.setdefault('error_messages', {})['invalid'] = 'تاریخ جلالی معتبر نیست.'
        elif type(db_field) is models.DateTimeField and not db_field.auto_now and not db_field.auto_now_add:
            kwargs['widget'] = JalaliDateTimeWidget()
            kwargs.setdefault('error_messages', {})['invalid'] = 'تاریخ جلالی معتبر نیست.'
        return super().formfield_for_dbfield(db_field, request, **kwargs)


@admin.register(Booking)
class BookingAdmin(JalaliDateAdmin):
    list_display = ('id', 'farmer', 'worker', 'service', 'city', 'jalali_work_date', 'status', 'admin_approved')
    list_filter = ('status', 'admin_approved', 'city', 'service')
    search_fields = ('address', 'farmer__username', 'farmer__name', 'worker__user__profile__phone')

    @admin.display(description='تاریخ مراجعه', ordering='work_date')
    def jalali_work_date(self, obj):
        return to_jalali(obj.work_date)


@admin.register(Review)
class ReviewAdmin(JalaliDateAdmin):
    list_display = ('farmer', 'worker', 'rating', 'jalali_created_at')
    list_filter = ('rating',)
    search_fields = ('farmer__name', 'farmer__username', 'comment')

    @admin.display(description='تاریخ ثبت', ordering='created_at')
    def jalali_created_at(self, obj):
        return to_jalali(obj.created_at, 'Y/m/d H:i')
