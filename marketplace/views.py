import re
from functools import wraps
from urllib.parse import urlencode
from django.contrib import messages
from django.contrib.auth import login, logout
from django.core.paginator import Paginator
from django.http import Http404
from django.db import transaction
from django.db.models import Count, F, Prefetch, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .backends import AdminBackend
from .forms import (
    AdminAccountForm, BookForm, FarmerProfileForm, LoginForm, OrderRequestForm, ProductForm, RegisterForm,
    ReviewForm, SellerProfileForm, WallAdForm, WorkerSettingsForm,
)
from .geo import city_centers, iran_border
from .models import (
    AdminAccount, Booking, Category, City, LandOwner, Product, Review, Seller, Service, ServiceProvider, User,
    WallAd, WallCategory,
)
from .sms import SmsError, send_account_sms

ADMIN_BACKEND = 'marketplace.backends.AdminBackend'


def _login_redirect(request):
    return redirect(f"{reverse('login')}?{urlencode({'next': request.get_full_path()})}")


def _is_admin(user):
    return isinstance(user, AdminAccount)


def base_user_required(view):
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return _login_redirect(request)
        if _is_admin(request.user):
            messages.error(request, 'این بخش برای کاربران سایت است.')
            return redirect('admin_panel')
        return view(request, *args, **kwargs)
    return wrapper


def role_required(kind):
    def decorator(view):
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return _login_redirect(request)
            if kind == 'admin':
                if not _is_admin(request.user):
                    messages.error(request, 'این بخش مخصوص ادمین است.')
                    return redirect('home')
                return view(request, *args, **kwargs)
            if _is_admin(request.user):
                messages.error(request, {
                    'land': 'رزرو نیرو فقط برای صاحبان زمین امکان‌پذیر است.',
                    'service': 'این بخش مخصوص سرویس دهندگان است.',
                    'seller': 'این بخش مخصوص فروشندگان است.',
                }.get(kind, 'به این بخش دسترسی ندارید.'))
                return redirect('home')
            if kind == 'land' and not LandOwner.objects.filter(user=request.user).exists():
                messages.info(request, 'برای این بخش، اول زمین خود را ثبت کنید.')
                return redirect('farmer_profile')
            if kind == 'service' and not ServiceProvider.objects.filter(user=request.user).exists():
                messages.info(request, 'برای این بخش، اول خدمت خود را ثبت کنید.')
                return redirect('worker_profile')
            if kind == 'seller':
                seller = Seller.objects.filter(user=request.user).first()
                if seller is None or not seller.is_profile_complete:
                    messages.info(request, 'برای این بخش، اول فروشگاه را با آدرس و موقعیت ثبت کنید.')
                    return redirect('seller_profile')
            return view(request, *args, **kwargs)
        return wrapper
    return decorator


def _service_users():
    return (
        User.objects.filter(service_profile__isnull=False)
        .select_related('service_profile')
        .prefetch_related('service_profile__services', 'service_profile__cities')
    )


def _safe_next(request, fallback='home'):
    target = request.POST.get('next') or request.GET.get('next') or ''
    if target and url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()}):
        return target
    return reverse(fallback)


def home(request):
    return render(request, 'marketplace/home.html', {
        'categories': Category.objects.annotate(service_count=Count('services')),
        'popular_services': Service.objects.filter(is_popular=True).select_related('category'),
        'all_services': Service.objects.all(),
        'featured_workers': (
            _service_users()
            .filter(service_profile__accepts_jobs=True)
            .order_by('-service_profile__rating', '-service_profile__jobs_done')[:4]
        ),
        'reviews': (
            Review.objects.select_related('farmer', 'worker', 'worker__service_profile')
            .prefetch_related('worker__service_profile__cities')[:6]
        ),
        'featured_cities': City.objects.filter(is_featured=True).order_by('featured_order'),
        'cities': City.objects.all(),
        'stats': {
            'workers': User.objects.filter(service_profile__accepts_jobs=True).count(),
            'cities': City.objects.count(),
            'services': Service.objects.count(),
        },
    })


def service_list(request):
    categories = Category.objects.prefetch_related('services')
    return render(request, 'marketplace/services.html', {'categories': categories})


def category_detail(request, slug):
    category = get_object_or_404(Category.objects.prefetch_related('services'), slug=slug)
    return render(request, 'marketplace/category.html', {'category': category})


def _account(request):
    user = request.user
    if user.is_authenticated and not _is_admin(user):
        return user
    return None


def order_service(request, slug):
    if _is_admin(request.user):
        messages.error(request, 'رزرو سرویس‌دهنده فقط برای صاحبان زمین است.')
        return redirect('admin_panel')
    profile = _account(request)
    service = get_object_or_404(Service.objects.select_related('category'), slug=slug)
    initial = {}
    locked = None
    if profile and profile._land():
        if profile.has_saved_farm:
            locked = (profile.farm_city, profile.farm_address)
        else:
            if profile.farm_city_id:
                initial['city'] = profile.farm_city_id
            if profile.farm_address:
                initial['address'] = profile.farm_address
    form = OrderRequestForm(request.POST or None, initial=initial, locked_location=locked)
    if request.method == 'POST' and form.is_valid():
        data = form.cleaned_data
        query = urlencode({
            'service': service.slug,
            'city': data['city'].pk,
            'address': data['address'],
            'date': data['work_date'].isoformat(),
            'area': data['land_area'] or '',
            'note': data['note'],
        })
        return redirect(f"{reverse('workers')}?{query}")
    return render(request, 'marketplace/order.html', {
        'service': service,
        'form': form,
        'farm_locked': locked is not None,
    })


def _request_context(request):
    service_slug = request.GET.get('service', '').strip()
    query = request.GET.get('q', '').strip()
    city_raw = request.GET.get('city', '').strip()
    selected_service = None
    if service_slug:
        selected_service = Service.objects.filter(slug=service_slug).select_related('category').first()
    elif query:
        selected_service = Service.objects.filter(name=query).select_related('category').first()
    selected_city = City.objects.filter(pk=city_raw).first() if city_raw.isdigit() else None
    return {
        'q': query,
        'selected_service': selected_service,
        'selected_city': selected_city,
        'address': request.GET.get('address', '').strip(),
        'work_date': request.GET.get('date', '').strip(),
        'area': request.GET.get('area', '').strip(),
        'note': request.GET.get('note', '').strip(),
        'sort': request.GET.get('sort', 'rating'),
    }


def workers(request):
    ctx = _request_context(request)
    qs = _service_users().filter(service_profile__accepts_jobs=True)
    if ctx['selected_service']:
        qs = qs.filter(service_profile__services=ctx['selected_service'])
    elif ctx['q']:
        qs = qs.filter(
            Q(name__icontains=ctx['q'])
            | Q(service_profile__services__name__icontains=ctx['q'])
            | Q(service_profile__bio__icontains=ctx['q'])
        )
    profile = _account(request)
    farm_locked = bool(profile and profile.has_saved_farm and ctx['address'])
    if farm_locked:
        ctx['selected_city'] = profile.farm_city
        ctx['address'] = profile.farm_address.strip()
    ctx['farm_locked'] = farm_locked
    if ctx['selected_city']:
        qs = qs.filter(service_profile__cities=ctx['selected_city'])

    sort = ctx['sort']
    if sort == 'wage':
        qs = qs.order_by('service_profile__daily_wage', '-service_profile__rating')
    elif sort == 'experience':
        qs = qs.order_by('-service_profile__experience_years', '-service_profile__rating')
    else:
        qs = qs.order_by('-service_profile__rating', '-service_profile__jobs_done')

    page_obj = Paginator(qs.distinct(), 8).get_page(request.GET.get('page'))
    ctx.update({
        'page_obj': page_obj,
        'services': Service.objects.select_related('category'),
        'cities': City.objects.all(),
    })
    return render(request, 'marketplace/workers.html', ctx)


def worker_detail(request, pk):
    worker = get_object_or_404(
        _service_users().prefetch_related(
            Prefetch('reviews', queryset=Review.objects.select_related('farmer')),
        ),
        pk=pk,
    )
    return render(request, 'marketplace/worker_detail.html', {
        'worker': worker,
        **_request_context(request),
    })


def _book_initial(request, worker):
    initial = {}
    slug = request.GET.get('service', '')
    if slug:
        service = worker.services.filter(slug=slug).first()
        if service:
            initial['service'] = service.pk
    city_raw = request.GET.get('city', '')
    if city_raw.isdigit() and worker.cities.filter(pk=city_raw).exists():
        initial['city'] = city_raw
    if request.GET.get('address'):
        initial['address'] = request.GET.get('address')
    if request.GET.get('date'):
        initial['work_date'] = request.GET.get('date')
    if request.GET.get('area'):
        initial['land_area'] = request.GET.get('area')
    if request.GET.get('note'):
        initial['note'] = request.GET.get('note')
    profile = request.user
    if profile.has_saved_farm:
        initial['city'] = profile.farm_city_id
        initial['address'] = profile.farm_address.strip()
    else:
        if 'city' not in initial and profile.farm_city_id and worker.cities.filter(pk=profile.farm_city_id).exists():
            initial['city'] = profile.farm_city_id
        if 'address' not in initial and profile.farm_address:
            initial['address'] = profile.farm_address
    return initial


@role_required('land')
def book(request, pk):
    if not request.user.land_profile.is_profile_complete:
        messages.info(request, 'قبل از رزرو، شهر و آدرس زمین را در پروفایل کامل کنید.')
        return redirect(f"{reverse('farmer_profile')}?{urlencode({'next': request.get_full_path()})}")
    worker = get_object_or_404(_service_users(), pk=pk)
    if not worker.accepts_jobs:
        messages.error(request, 'این سرویس دهنده فعلاً سفارش جدید نمی‌پذیرد.')
        return redirect('workers')
    if not worker.services.exists() or not worker.cities.exists():
        messages.error(request, 'پروفایل این سرویس دهنده هنوز کامل نشده است.')
        return redirect('workers')

    profile = request.user
    locked = (profile.farm_city, profile.farm_address) if profile.has_saved_farm else None
    if request.method == 'POST':
        form = BookForm(request.POST, worker=worker, locked_location=locked)
        if form.is_valid():
            booking = form.save(request.user)
            messages.success(request, 'درخواست رزرو ثبت شد.')
            return redirect('bookings')
    else:
        form = BookForm(worker=worker, initial=_book_initial(request, worker), locked_location=locked)
    return render(request, 'marketplace/book.html', {
        'worker': worker,
        'form': form,
        'farm_locked': locked is not None,
    })


def _farmer_stage_options():
    return [
        (Booking.PENDING, 'پذیرش سرویس دهنده', Q(status=Booking.PENDING)),
        (Booking.CONFIRMED, 'اتمام کار', Q(status=Booking.CONFIRMED)),
        ('feedback', 'ثبت نظر', Q(status=Booking.DONE, review__isnull=True)),
        ('finished', 'تکمیل شده', Q(status=Booking.DONE, review__isnull=False)),
        (Booking.REJECTED, 'رد شده', Q(status=Booking.REJECTED)),
        (Booking.CANCELLED, 'لغو شده', Q(status=Booking.CANCELLED)),
    ]


def _bookings_url(request):
    allowed = {value for value, _label, _query in _farmer_stage_options()}
    stage = request.GET.get('stage', '')
    if stage in allowed:
        return f"{reverse('bookings')}?{urlencode({'stage': stage})}"
    return reverse('bookings')


@role_required('land')
def bookings(request):
    options = _farmer_stage_options()
    allowed = {value for value, _label, _query in options}
    selected = request.GET.get('stage', '')
    if selected not in allowed:
        selected = ''
    base = (
        request.user.bookings
        .select_related('service', 'city', 'worker', 'review')
        .order_by('-created_at')
    )
    counts = base.aggregate(**{
        value: Count('id', filter=query) for value, _label, query in options
    })
    items = base.filter(next(query for value, _label, query in options if value == selected)) if selected else base
    filters = [{'value': '', 'label': 'همه', 'count': sum(counts.values())}]
    filters.extend(
        {'value': value, 'label': label, 'count': counts[value]}
        for value, label, _query in options
    )
    return render(request, 'marketplace/bookings.html', {
        'bookings': items,
        'filters': filters,
        'selected': selected,
    })


@require_POST
@role_required('land')
def booking_cancel(request, pk):
    booking = get_object_or_404(Booking, pk=pk, farmer=request.user)
    if booking.status in (Booking.PENDING, Booking.CONFIRMED):
        booking.status = Booking.CANCELLED
        booking.save(update_fields=['status'])
        messages.success(request, 'رزرو لغو شد.')
    else:
        messages.error(request, 'این رزرو دیگر قابل لغو نیست.')
    return redirect(_bookings_url(request))


@require_POST
@role_required('land')
def booking_complete(request, pk):
    booking = get_object_or_404(
        Booking.objects.select_related('worker'),
        pk=pk,
        farmer=request.user,
        status=Booking.CONFIRMED,
    )
    booking.status = Booking.DONE
    booking.save(update_fields=['status'])
    ServiceProvider.objects.filter(user_id=booking.worker_id).update(jobs_done=F('jobs_done') + 1)
    messages.success(request, 'اتمام کار ثبت شد. حالا می‌توانید نظر خود را بنویسید.')
    return redirect(_bookings_url(request))


@require_POST
@role_required('land')
def booking_review(request, pk):
    booking = get_object_or_404(Booking, pk=pk, farmer=request.user, status=Booking.DONE)
    if booking.existing_review:
        messages.error(request, 'برای این رزرو قبلاً نظر ثبت شده است.')
        return redirect(_bookings_url(request))
    form = ReviewForm(request.POST)
    if form.is_valid():
        Review.objects.create(
            booking=booking,
            worker=booking.worker,
            farmer=request.user,
            rating=form.cleaned_data['rating'],
            comment=form.cleaned_data['comment'].strip(),
        )
        booking.worker.refresh_rating()
        messages.success(request, 'نظر شما ثبت شد.')
    else:
        messages.error(request, 'امتیاز و متن نظر را کامل کنید.')
    return redirect(_bookings_url(request))


def _farmer_viewer(request, farmer):
    if not request.user.is_authenticated:
        return False, []
    if _is_admin(request.user):
        return True, []
    if request.user.pk == farmer.pk:
        return True, []
    if not ServiceProvider.objects.filter(user=request.user).exists():
        return False, []
    jobs = list(
        request.user.jobs.filter(farmer=farmer, admin_approved=True)
        .select_related('service', 'city')
        .order_by('-created_at')
    )
    return bool(jobs), jobs


def farmer_public(request, pk):
    farmer = get_object_or_404(
        User.objects.select_related('land_profile__farm_city'),
        pk=pk,
        land_profile__isnull=False,
    )
    can_see_contact, shared_jobs = _farmer_viewer(request, farmer)
    reviews = (
        Review.objects.filter(farmer=farmer)
        .select_related('worker', 'booking__service')
        .order_by('-created_at')[:12]
    )
    return render(request, 'marketplace/farmer_public.html', {
        'farmer': farmer,
        'profile': farmer,
        'can_see_contact': can_see_contact,
        'shared_jobs': shared_jobs,
        'reviews': reviews,
        'completed_jobs': farmer.bookings.filter(status=Booking.DONE).count(),
        'is_self': request.user.is_authenticated and not _is_admin(request.user) and request.user.pk == farmer.pk,
    })


@base_user_required
def farmer_profile(request):
    land = LandOwner.objects.filter(user=request.user).select_related('farm_city').first()
    form = FarmerProfileForm(request.POST or None, instance=land)
    if request.method == 'POST' and form.is_valid():
        saved = form.save(commit=False)
        saved.user = request.user
        saved.save()
        messages.success(request, 'موقعیت زمین ذخیره شد.')
        if saved.is_profile_complete:
            return redirect(_safe_next(request))
        land = saved
        form = FarmerProfileForm(instance=land)
    if not getattr(form.instance, 'user_id', None):
        form.instance.user = request.user
    return render(request, 'marketplace/farmer_profile.html', {
        'form': form,
        'profile': form.instance,
        'city_centers': city_centers(),
        'iran_border': iran_border(),
    })


ADMIN_PAGE_SIZE = 10


@role_required('admin')
def admin_panel(request):
    selected = request.GET.get('status', '')
    valid = {value for value, _label in Booking.STATUS_CHOICES} | {'awaiting'}
    if selected not in valid:
        selected = ''
    jobs = (
        Booking.objects.select_related(
            'service', 'city', 'farmer', 'worker', 'confirmed_by',
        )
        .order_by('-created_at')
    )
    if selected == 'awaiting':
        jobs = jobs.filter(status=Booking.PENDING, admin_approved=False)
    elif selected == Booking.PENDING:
        jobs = jobs.filter(status=Booking.PENDING, admin_approved=True)
    elif selected:
        jobs = jobs.filter(status=selected)
    page_obj = Paginator(jobs, ADMIN_PAGE_SIZE).get_page(request.GET.get('page'))
    counts = {row['status']: row['total'] for row in Booking.objects.values('status').annotate(total=Count('id'))}
    awaiting = Booking.objects.filter(status=Booking.PENDING, admin_approved=False).count()
    pending_ready = counts.get(Booking.PENDING, 0) - awaiting
    filters = [
        {'value': '', 'label': 'همه', 'count': sum(counts.values())},
        {'value': 'awaiting', 'label': 'منتظر تأیید صلاحیت', 'count': awaiting},
        {'value': Booking.PENDING, 'label': 'در انتظار پذیرش سرویس دهنده', 'count': pending_ready},
        *[
            {'value': value, 'label': label, 'count': counts.get(value, 0)}
            for value, label in Booking.STATUS_CHOICES
            if value != Booking.PENDING
        ],
    ]
    return render(request, 'marketplace/admin_panel.html', {
        'page_obj': page_obj,
        'filters': filters,
        'selected': selected,
    })


_PEOPLE_DIGIT_TRANS = str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789')


def _filter_people(queryset, query):
    query = (query or '').strip()
    if not query:
        return queryset
    normalized = query.translate(_PEOPLE_DIGIT_TRANS)
    matched = (
        Q(name__icontains=query)
    )
    for term in {query, normalized}:
        matched |= Q(username__icontains=term)
    return queryset.filter(matched).distinct()


@role_required('admin')
def admin_people(request):
    selected = request.GET.get('role', 'farmer')
    if selected not in {'farmer', 'worker', 'seller'}:
        selected = 'farmer'
    query = request.GET.get('q', '').strip()
    farmers = _filter_people(
        User.objects.filter(land_profile__isnull=False)
        .select_related('land_profile__farm_city', 'land_profile__created_by')
        .order_by('name', 'username'),
        query,
    )
    workers = _filter_people(
        User.objects.filter(service_profile__isnull=False)
        .select_related('service_profile__created_by')
        .prefetch_related('service_profile__services', 'service_profile__cities')
        .order_by('name', 'username'),
        query,
    )
    sellers = _filter_people(
        User.objects.filter(seller_profile__isnull=False)
        .select_related('seller_profile__store_city', 'seller_profile__created_by')
        .order_by('name', 'username'),
        query,
    )
    people = {'worker': workers, 'seller': sellers}.get(selected, farmers)
    return render(request, 'marketplace/admin_people.html', {
        'selected': selected,
        'query': query,
        'page_obj': Paginator(people, ADMIN_PAGE_SIZE).get_page(request.GET.get('page')),
        'farmer_count': farmers.count(),
        'worker_count': workers.count(),
        'seller_count': sellers.count(),
    })


def _posted_ids(request, key):
    return {int(item) for item in request.POST.getlist(key) if str(item).isdigit()}


@role_required('admin')
def admin_create_account(request):
    posted = request.POST if request.method == 'POST' else None
    form = AdminAccountForm(posted)
    land_form = FarmerProfileForm(posted)
    seller_form = SellerProfileForm(posted)
    worker_form = WorkerSettingsForm(
        posted,
        initial={'accepts_jobs': True, 'experience_years': 0, 'daily_wage': 0},
    )
    for profile_form in (land_form, seller_form, worker_form):
        profile_form.use_required_attribute = False
    worker_form.fields['bio'].widget.attrs.pop('minlength', None)
    if request.method == 'POST':
        selected_services = set(
            Service.objects.filter(pk__in=_posted_ids(request, 'services')).values_list('pk', flat=True)
        )
        selected_cities = set(
            City.objects.filter(pk__in=_posted_ids(request, 'cities')).values_list('pk', flat=True)
        )
    else:
        selected_services = set()
        selected_cities = set()
    if request.method == 'POST':
        account_ok = form.is_valid()
        role = form.cleaned_data.get('role') or request.POST.get('role', '')
        profile_ok = False
        if role == AdminAccountForm.ROLE_FARMER:
            profile_ok = land_form.is_valid()
        elif role == AdminAccountForm.ROLE_SELLER:
            profile_ok = seller_form.is_valid()
        elif role == AdminAccountForm.ROLE_WORKER:
            profile_ok = worker_form.is_valid()
            if not selected_services:
                worker_form.add_error(None, 'حداقل یک حوزه کاری انتخاب کنید.')
                profile_ok = False
            if not selected_cities:
                worker_form.add_error(None, 'حداقل یک شهر برای محل کار انتخاب کنید.')
                profile_ok = False
        if account_ok and profile_ok:
            with transaction.atomic():
                user = form.save()
                admin = request.user if isinstance(request.user, AdminAccount) else None
                if role == AdminAccountForm.ROLE_FARMER:
                    land = land_form.save(commit=False)
                    land.user = user
                    land.created_by = admin
                    land.save()
                elif role == AdminAccountForm.ROLE_SELLER:
                    seller = seller_form.save(commit=False)
                    seller.user = user
                    seller.created_by = admin
                    seller.save()
                else:
                    provider = worker_form.save(commit=False)
                    provider.user = user
                    provider.created_by = admin
                    provider.save()
                    provider.services.set(selected_services)
                    provider.cities.set(selected_cities)
            password = form.cleaned_data['password']
            try:
                send_account_sms(user.username, password)
            except SmsError as exc:
                messages.warning(
                    request,
                    f'حساب {user.get_full_name()} ساخته شد، ولی پیامک ارسال نشد: {exc}',
                )
            else:
                messages.success(
                    request,
                    f'حساب {user.get_full_name()} ساخته شد و نام کاربری و رمز عبور به {user.username} پیامک شد.',
                )
            return redirect('admin_panel')
    return render(request, 'marketplace/admin_account.html', {
        'form': form,
        'land_form': land_form,
        'seller_form': seller_form,
        'worker_form': worker_form,
        'categories': Category.objects.prefetch_related('services'),
        'cities': City.objects.all(),
        'selected_services': selected_services,
        'selected_cities': selected_cities,
        'city_centers': city_centers(),
        'iran_border': iran_border(),
    })


@require_POST
@role_required('admin')
def admin_approve(request, pk):
    booking = get_object_or_404(Booking, pk=pk, status=Booking.PENDING, admin_approved=False)
    booking.confirmed_by = request.user
    booking.confirmed_at = timezone.now()
    if request.POST.get('action') == 'reject':
        reason = (request.POST.get('reason') or '').strip()
        if not reason:
            messages.error(request, 'برای رد درخواست، علت را بنویسید.')
            return redirect('admin_panel')
        if len(reason) > 500:
            messages.error(request, 'علت رد را در ۵۰۰ نویسه بنویسید.')
            return redirect('admin_panel')
        booking.status = Booking.REJECTED
        booking.rejection_reason = reason
        booking.save(update_fields=['status', 'rejection_reason', 'confirmed_by', 'confirmed_at'])
        messages.success(request, 'صلاحیت درخواست رد شد.')
    else:
        booking.admin_approved = True
        booking.save(update_fields=['admin_approved', 'confirmed_by', 'confirmed_at'])
        messages.success(request, 'صلاحیت درخواست تأیید شد و برای سرویس دهنده ارسال گردید.')
    return redirect('admin_panel')


@base_user_required
def worker_profile(request):
    provider = ServiceProvider.objects.filter(user=request.user).first()
    if request.method == 'POST':
        selected_services = {int(item) for item in request.POST.getlist('services') if item.isdigit()}
        selected_cities = {int(item) for item in request.POST.getlist('cities') if item.isdigit()}
    elif provider:
        selected_services = set(provider.services.values_list('pk', flat=True))
        selected_cities = set(provider.cities.values_list('pk', flat=True))
    else:
        selected_services = set()
        selected_cities = set()
    form = WorkerSettingsForm(request.POST or None, instance=provider)
    if request.method == 'POST' and form.is_valid():
        if not selected_services:
            form.add_error(None, 'حداقل یک حوزه کاری انتخاب کنید.')
        elif not selected_cities:
            form.add_error(None, 'حداقل یک شهر برای محل کار انتخاب کنید.')
        else:
            saved = form.save(commit=False)
            saved.user = request.user
            saved.save()
            saved.services.set(selected_services)
            saved.cities.set(selected_cities)
            messages.success(request, 'پروفایل کاری ذخیره شد. صاحبان زمین شما را در همین حوزه‌ها و شهرها می‌بینند.')
            return redirect('worker_profile')
    if not getattr(form.instance, 'user_id', None):
        form.instance.user = request.user
    categories = Category.objects.prefetch_related('services')
    return render(request, 'marketplace/worker_profile.html', {
        'form': form,
        'worker': request.user,
        'profile': form.instance,
        'categories': categories,
        'cities': City.objects.all(),
        'selected_services': selected_services,
        'selected_cities': selected_cities,
    })


@role_required('service')
def worker_jobs(request):
    worker = request.user
    jobs = (
        worker.jobs.filter(Q(admin_approved=True) | ~Q(rejection_reason=''))
        .select_related('service', 'city', 'farmer', 'review')
        .order_by('-created_at')
    )
    return render(request, 'marketplace/worker_jobs.html', {'jobs': jobs, 'worker': worker})


@require_POST
@role_required('service')
def job_update(request, pk):
    worker = request.user
    booking = get_object_or_404(Booking, pk=pk, worker=worker, admin_approved=True)
    action = request.POST.get('action')
    if action == 'confirm' and booking.status == Booking.PENDING:
        booking.status = Booking.CONFIRMED
        booking.save(update_fields=['status'])
        messages.success(request, 'درخواست را پذیرفتید. صاحب زمین حالا اطلاعات تماس شما را می‌بیند.')
    elif action == 'reject' and booking.status == Booking.PENDING:
        booking.status = Booking.REJECTED
        booking.save(update_fields=['status'])
        messages.success(request, 'درخواست رد شد.')
    else:
        messages.error(request, 'این تغییر وضعیت ممکن نیست.')
    return redirect('worker_jobs')


def _authenticate_identifier(request, identifier, password):
    if re.fullmatch(r'09\d{9}', identifier):
        try:
            account = User.objects.get(username=identifier)
        except User.DoesNotExist:
            account = None
        if account is not None:
            if account.is_active and account.check_password(password):
                account.backend = 'django.contrib.auth.backends.ModelBackend'
                return account
            return None
    account = AdminBackend().authenticate(request, username=identifier, password=password)
    if account is not None:
        account.backend = ADMIN_BACKEND
    return account


def _public_products():
    return (
        Product.objects.filter(is_available=True, seller__store_latitude__isnull=False)
        .select_related('seller__user', 'seller__store_city')
    )


def bazaar(request):
    query = request.GET.get('q', '').strip()
    seller_query = request.GET.get('seller', '').strip()
    min_raw = request.GET.get('min_price', '').strip()
    max_raw = request.GET.get('max_price', '').strip()
    sort = request.GET.get('sort', 'new')
    if sort not in {'new', 'cheap', 'expensive'}:
        sort = 'new'
    ordering = {
        'new': ('-updated_at', '-pk'),
        'cheap': ('price', '-pk'),
        'expensive': ('-price', '-pk'),
    }[sort]
    selected_cities = {pk for pk in request.GET.getlist('city') if pk.isdigit()}
    selected_units = [
        unit for unit in request.GET.getlist('unit')
        if unit in dict(Product.UNIT_CHOICES)
    ]
    products = _public_products()
    cities = City.objects.filter(
        pk__in=products.values('seller__store_city_id'),
    )
    if query:
        products = products.filter(
            Q(name__icontains=query)
            | Q(description__icontains=query)
            | Q(seller__user__name__icontains=query)
            | Q(seller__store_name__icontains=query)
        )
    if seller_query:
        products = products.filter(
            Q(seller__store_name__icontains=seller_query)
            | Q(seller__user__name__icontains=seller_query)
        )
    if selected_cities:
        products = products.filter(seller__store_city_id__in=selected_cities)
    if selected_units:
        products = products.filter(unit__in=selected_units)
    if min_raw.isdigit():
        products = products.filter(price__gte=int(min_raw))
    if max_raw.isdigit():
        products = products.filter(price__lte=int(max_raw))
    filters_active = bool(
        query or seller_query or selected_cities or selected_units
        or min_raw or max_raw or sort != 'new'
    )
    return render(request, 'marketplace/bazaar.html', {
        'page_obj': Paginator(products.order_by(*ordering), 12).get_page(request.GET.get('page')),
        'query': query,
        'seller_query': seller_query,
        'min_price': min_raw if min_raw.isdigit() else '',
        'max_price': max_raw if max_raw.isdigit() else '',
        'selected_cities': selected_cities,
        'selected_units': selected_units,
        'units': Product.UNIT_CHOICES,
        'cities': cities,
        'sort': sort,
        'filters_active': filters_active,
    })


def product_detail(request, pk):
    product = get_object_or_404(
        Product.objects.select_related('seller__user', 'seller__store_city'),
        pk=pk,
    )
    seller = product.seller
    is_owner = (
        request.user.is_authenticated
        and not _is_admin(request.user)
        and Seller.objects.filter(pk=seller.pk, user=request.user).exists()
    )
    if not product.is_available and not is_owner:
        raise Http404('این محصول در بازار نیست.')
    if not seller.has_store_location and not is_owner:
        raise Http404('این محصول در بازار نیست.')
    return render(request, 'marketplace/product_detail.html', {
        'product': product,
        'seller': seller,
        'is_owner': is_owner,
    })


@base_user_required
def seller_profile(request):
    seller = Seller.objects.filter(user=request.user).select_related('store_city').first()
    form = SellerProfileForm(request.POST or None, instance=seller)
    if request.method == 'POST' and form.is_valid():
        saved = form.save(commit=False)
        saved.user = request.user
        saved.save()
        messages.success(request, 'فروشگاه ذخیره شد.')
        if saved.is_profile_complete:
            return redirect('seller_products')
        seller = saved
        form = SellerProfileForm(instance=seller)
    if not getattr(form.instance, 'user_id', None):
        form.instance.user = request.user
    return render(request, 'marketplace/seller_profile.html', {
        'form': form,
        'profile': form.instance,
        'city_centers': city_centers(),
        'iran_border': iran_border(),
    })


@role_required('seller')
def seller_products(request):
    return _seller_panel(request)


def _seller_panel(request, form=None):
    seller = request.user.seller_profile
    return render(request, 'marketplace/seller_products.html', {
        'seller': seller,
        'products': seller.products.all(),
        'form': form or ProductForm(),
    })


@role_required('seller')
def seller_product_edit(request, pk=None):
    seller = request.user.seller_profile
    product = get_object_or_404(Product, pk=pk, seller=seller) if pk else None
    if product is None and request.method != 'POST':
        return redirect(f"{reverse('seller_products')}#new-product")
    if request.method == 'POST' and request.POST.get('action') == 'delete':
        if product is None:
            messages.error(request, 'محصولی برای حذف نیست.')
            return redirect('seller_products')
        product.delete()
        messages.success(request, 'محصول حذف شد.')
        return redirect('seller_products')
    form = ProductForm(request.POST or None, request.FILES or None, instance=product)
    if request.method == 'POST' and form.is_valid():
        saved = form.save(commit=False)
        saved.seller = seller
        saved.save()
        messages.success(request, 'محصول ثبت شد.' if product is None else 'محصول ذخیره شد.')
        return redirect('seller_products')
    if product is None:
        return _seller_panel(request, form=form)
    return render(request, 'marketplace/seller_product_form.html', {
        'form': form,
        'product': product,
        'seller': seller,
    })


def _published_ads():
    return WallAd.objects.filter(is_published=True).select_related('user', 'city', 'category')


def _wall_owner(request, ad):
    user = request.user
    return bool(user.is_authenticated and not _is_admin(user) and ad.user_id == user.pk)


def _own_ad(request, pk):
    return get_object_or_404(WallAd, pk=pk, user=request.user)


def _city_pk(value):
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _session_city(request):
    pk = _city_pk(request.session.get('wall_city_id'))
    if not pk:
        return None
    return City.objects.filter(pk=pk).first()


def _remember_city(request, city):
    request.session['wall_city_id'] = city.pk


def _initial_city_id(request):
    for raw in (request.GET.get('city'), request.session.get('wall_city_id')):
        pk = _city_pk(raw)
        if pk and City.objects.filter(pk=pk).exists():
            return pk
    return None


def _wall_listing(request, ads):
    query = request.GET.get('q', '').strip()
    district = request.GET.get('district', '').strip()
    cat_slug = request.GET.get('cat', '').strip()
    min_raw = request.GET.get('min_price', '').strip()
    max_raw = request.GET.get('max_price', '').strip()
    sort = request.GET.get('sort', 'new')
    if sort not in {'new', 'cheap', 'expensive'}:
        sort = 'new'
    photo = request.GET.get('photo') == '1'
    current_category = WallCategory.objects.filter(slug=cat_slug).first() if cat_slug else None
    if query:
        ads = ads.filter(
            Q(title__icontains=query)
            | Q(description__icontains=query)
            | Q(district__icontains=query)
            | Q(price_note__icontains=query)
        )
    if district:
        ads = ads.filter(district__icontains=district)
    if current_category:
        ads = ads.filter(category=current_category)
    if min_raw.isdigit():
        ads = ads.filter(price__gte=int(min_raw))
    if max_raw.isdigit():
        ads = ads.filter(price__lte=int(max_raw))
    if photo:
        ads = ads.exclude(image='')
    ordering = {
        'new': ('-created_at', '-pk'),
        'cheap': (F('price').asc(nulls_last=True), 'pk'),
        'expensive': (F('price').desc(nulls_last=True), '-pk'),
    }[sort]
    return {
        'page_obj': Paginator(ads.order_by(*ordering), 20).get_page(request.GET.get('page')),
        'query': query,
        'district': district,
        'current_category': current_category,
        'categories': WallCategory.objects.all(),
        'min_price': min_raw if min_raw.isdigit() else '',
        'max_price': max_raw if max_raw.isdigit() else '',
        'sort': sort,
        'photo': photo,
        'filters_active': bool(
            query or district or current_category or photo
            or min_raw.isdigit() or max_raw.isdigit() or sort != 'new'
        ),
    }


def wall(request):
    city = _session_city(request)
    if city is None:
        city = (
            City.objects.filter(is_featured=True).order_by('featured_order', 'name').first()
            or City.objects.order_by('name').first()
        )
    if city is None:
        raise Http404('شهری برای نمایش آگهی‌ها نیست.')
    return redirect('wall_city', city.pk)


def wall_city(request, city_id):
    city = get_object_or_404(City, pk=city_id)
    _remember_city(request, city)
    context = _wall_listing(request, _published_ads().filter(city=city))
    context['city'] = city
    return render(request, 'marketplace/wall/list.html', context)


def wall_ad(request, pk):
    ad = get_object_or_404(WallAd.objects.select_related('user', 'city', 'category'), pk=pk)
    owner = _wall_owner(request, ad)
    if not ad.is_published and not owner:
        raise Http404('این آگهی روی دیوار نیست.')
    related = []
    if ad.is_published:
        related = list(
            _published_ads().filter(city_id=ad.city_id, category_id=ad.category_id).exclude(pk=ad.pk)[:4]
        )
    return render(request, 'marketplace/wall/detail.html', {
        'ad': ad,
        'city': ad.city,
        'is_owner': owner,
        'related': related,
        'categories': WallCategory.objects.all(),
    })


@base_user_required
def wall_new(request):
    if request.method == 'GET' and not request.GET.get('cat'):
        return render(request, 'marketplace/wall/pick.html', {
            'categories': WallCategory.objects.all(),
            'city_id': _initial_city_id(request) or '',
            'city': _session_city(request),
        })
    picked = None
    initial = None
    if request.method == 'GET':
        picked = get_object_or_404(WallCategory, slug=request.GET.get('cat', '').strip())
        initial = {'category': picked.pk}
        city_id = _initial_city_id(request)
        if city_id:
            initial['city'] = city_id
    form = WallAdForm(request.POST or None, request.FILES or None, initial=initial)
    if request.method == 'POST' and form.is_valid():
        ad = form.save(commit=False)
        ad.user = request.user
        ad.is_published = True
        ad.save()
        _remember_city(request, ad.city)
        messages.success(request, 'آگهی به دیوار چسبید.')
        return redirect(ad.get_absolute_url())
    if picked is None and str(request.POST.get('category', '')).isdigit():
        picked = WallCategory.objects.filter(pk=request.POST.get('category')).first()
    return render(request, 'marketplace/wall/form.html', {
        'form': form,
        'ad': None,
        'picked': picked,
        'city': _session_city(request),
        'categories': WallCategory.objects.all(),
    })


@base_user_required
def wall_edit(request, pk):
    ad = _own_ad(request, pk)
    form = WallAdForm(request.POST or None, request.FILES or None, instance=ad)
    if request.method == 'POST' and form.is_valid():
        saved = form.save()
        _remember_city(request, saved.city)
        messages.success(request, 'آگهی ذخیره شد.')
        return redirect(saved.get_absolute_url())
    return render(request, 'marketplace/wall/form.html', {
        'form': form,
        'ad': ad,
        'picked': ad.category,
        'city': ad.city,
        'categories': WallCategory.objects.all(),
    })


@base_user_required
def wall_mine(request):
    return render(request, 'marketplace/wall/mine.html', {
        'ads': WallAd.objects.filter(user=request.user).select_related('city', 'category', 'user'),
        'city': _session_city(request),
        'categories': WallCategory.objects.all(),
    })


@base_user_required
@require_POST
def wall_delete(request, pk):
    ad = _own_ad(request, pk)
    ad.delete()
    messages.success(request, 'آگهی از دیوار حذف شد.')
    return redirect('wall_mine')


@base_user_required
@require_POST
def wall_toggle(request, pk):
    ad = _own_ad(request, pk)
    ad.is_published = not ad.is_published
    ad.save(update_fields=['is_published'])
    if ad.is_published:
        messages.success(request, 'آگهی دوباره روی دیوار است.')
    else:
        messages.success(request, 'آگهی از دید دیگران برداشته شد.')
    return redirect('wall_mine')


def register(request):
    if request.user.is_authenticated:
        if _is_admin(request.user):
            return redirect('admin_panel')
        return redirect('home')
    form = RegisterForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.save()
        user.backend = 'django.contrib.auth.backends.ModelBackend'
        login(request, user)
        messages.success(request, 'حساب شما ساخته شد. از منو می‌توانید زمین، خدمت یا فروشگاه ثبت کنید.')
        return redirect(_safe_next(request))
    return render(request, 'marketplace/register.html', {'form': form})


def login_view(request):
    if request.user.is_authenticated:
        if _is_admin(request.user):
            return redirect('admin_panel')
        return redirect('home')
    form = LoginForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = _authenticate_identifier(
            request,
            form.cleaned_data['username'],
            form.cleaned_data['password'],
        )
        if user is None:
            form.add_error(None, 'شماره موبایل، نام کاربری یا رمز عبور نادرست است.')
        else:
            login(request, user)
            if _is_admin(user) and not (request.POST.get('next') or request.GET.get('next')):
                return redirect('admin_panel')
            return redirect(_safe_next(request))
    return render(request, 'marketplace/login.html', {'form': form})


@require_POST
def logout_view(request):
    logout(request)
    messages.success(request, 'از حساب خارج شدید.')
    return redirect('home')


def about(request):
    return render(request, 'marketplace/about.html')


def faq(request):
    return render(request, 'marketplace/faq.html')
