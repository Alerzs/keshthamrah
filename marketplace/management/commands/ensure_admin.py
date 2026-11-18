import os
import re

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from marketplace.models import AdminAccount


class Command(BaseCommand):
    help = 'اگر DJANGO_SUPERUSER_USERNAME تازه باشد، ادمین سایت را می‌سازد.'

    def handle(self, *args, **options):
        username = os.environ.get('DJANGO_SUPERUSER_USERNAME', '').strip()
        password = os.environ.get('DJANGO_SUPERUSER_PASSWORD', '')
        if not username or not password:
            self.stdout.write('DJANGO_SUPERUSER_USERNAME is unset; skipping.')
            return
        name = os.environ.get('DJANGO_SUPERUSER_NAME', '').strip() or 'مدیر کل'
        if AdminAccount.objects.filter(username=username).exists():
            self.stdout.write(f'{username} already exists; password left unchanged.')
        else:
            AdminAccount.objects.create_account(username, password, name=name)
            self.stdout.write(self.style.SUCCESS(f'Created site admin {username}.'))
        if re.fullmatch(r'09\d{9}', username):
            return
        User = get_user_model()
        if User.objects.filter(username=username).exists():
            self.stdout.write(f'Django superuser {username} already exists.')
            return
        User.objects.create_superuser(username=username, password=password, name=name)
        self.stdout.write(self.style.SUCCESS(f'Created Django superuser {username}.'))
