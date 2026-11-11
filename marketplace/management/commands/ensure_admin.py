import os
import re

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'اگر DJANGO_SUPERUSER_USERNAME تازه باشد، یک مدیر می‌سازد.'

    def handle(self, *args, **options):
        username = os.environ.get('DJANGO_SUPERUSER_USERNAME', '').strip()
        password = os.environ.get('DJANGO_SUPERUSER_PASSWORD', '')
        if not username or not password:
            self.stdout.write('DJANGO_SUPERUSER_USERNAME is unset; skipping.')
            return
        User = get_user_model()
        if User.objects.filter(username=username).exists():
            self.stdout.write(f'{username} already exists; password and role left unchanged.')
            return
        name = os.environ.get('DJANGO_SUPERUSER_NAME', '').strip() or 'مدیر کل'
        user = User.objects.create_superuser(
            username=username,
            password=password,
        )
        user.name = name
        user.save(update_fields=['name'])
        if re.fullmatch(r'09\d{9}', username):
            user.role = User.ADMIN
            user.phone = username
            user.save(update_fields=['role', 'phone'])
            self.stdout.write(self.style.SUCCESS(f'Created site admin {username}.'))
            return
        self.stdout.write(self.style.SUCCESS(
            f'Created Django superuser {username}. Site login needs a mobile username.'
        ))
