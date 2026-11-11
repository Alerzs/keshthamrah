from .models import Category, City


def site_nav(request):
    profile = None
    if request.user.is_authenticated and request.user.role:
        profile = request.user
    return {
        'nav_categories': Category.objects.all(),
        'nav_cities': City.objects.all(),
        'current_profile': profile,
    }
