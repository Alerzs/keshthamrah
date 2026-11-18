from .models import AdminAccount, Category, City, LandOwner, Seller, ServiceProvider


BAZAAR_PAGES = {
    'bazaar',
    'product_detail',
    'seller_profile',
    'seller_products',
    'seller_product_new',
    'seller_product_edit',
}

WALL_PAGES = {
    'wall',
    'wall_city',
    'wall_ad',
    'wall_new',
    'wall_edit',
    'wall_mine',
}


def site_nav(request):
    user = request.user
    is_admin = user.is_authenticated and isinstance(user, AdminAccount)
    match = getattr(request, 'resolver_match', None)
    url_name = match.url_name if match else ''
    land_profile = None
    service_profile = None
    seller_profile = None
    if user.is_authenticated and not is_admin:
        land_profile = (
            LandOwner.objects.filter(user=user).select_related('farm_city').first()
        )
        service_profile = ServiceProvider.objects.filter(user=user).first()
        seller_profile = Seller.objects.filter(user=user).select_related('store_city').first()
    return {
        'nav_categories': Category.objects.all(),
        'nav_cities': City.objects.all(),
        'current_profile': user if user.is_authenticated else None,
        'is_admin': is_admin,
        'land_profile': land_profile,
        'service_profile': service_profile,
        'seller_profile': seller_profile,
        'bazaar_nav': url_name in BAZAAR_PAGES,
        'wall_nav': url_name in WALL_PAGES,
    }
