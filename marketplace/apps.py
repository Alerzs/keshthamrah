from django.apps import AppConfig
from django.db.backends.signals import connection_created


def configure_sqlite(sender, connection, **kwargs):
    if connection.vendor != 'sqlite':
        return
    with connection.cursor() as cursor:
        cursor.execute('PRAGMA journal_mode=WAL;')
        cursor.execute('PRAGMA synchronous=NORMAL;')
        cursor.execute('PRAGMA busy_timeout=20000;')


class MarketplaceConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'marketplace'
    verbose_name = 'بازار خدمات کشاورزی'

    def ready(self):
        connection_created.connect(configure_sqlite)
        from django.contrib import admin

        from .models import AdminAccount

        def skip_history(original):
            def wrapped(request, *args, **kwargs):
                if isinstance(getattr(request, 'user', None), AdminAccount):
                    return None
                return original(request, *args, **kwargs)
            wrapped._admin_account_safe = True
            return wrapped

        for model_admin in admin.site._registry.values():
            for name in ('log_addition', 'log_change', 'log_deletion'):
                current = getattr(model_admin, name)
                if getattr(current, '_admin_account_safe', False):
                    continue
                setattr(model_admin, name, skip_history(current))
