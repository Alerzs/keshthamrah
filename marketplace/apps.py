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
