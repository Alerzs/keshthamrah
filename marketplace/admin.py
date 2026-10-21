from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.db import models

from .dates import to_jalali
from .forms import JalaliDateTimeWidget, JalaliDateWidget
from .models import Booking, Category, City, Profile, Review, Service, User, WorkerProfile


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
    list_display = ('user', 'role', 'phone', 'farm_city')
    list_filter = ('role',)
    search_fields = ('phone', 'user__name', 'user__first_name', 'user__last_name')


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
