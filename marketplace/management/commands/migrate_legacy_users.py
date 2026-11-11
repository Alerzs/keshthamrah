import sqlite3
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from marketplace.models import City, Service, User


def merged_person_name(name='', first_name='', last_name=''):
    stored = (name or '').strip()
    combined = f'{(first_name or "").strip()} {(last_name or "").strip()}'.strip()
    if not stored:
        return combined
    if not combined or combined == stored or combined in stored:
        return stored
    if stored in combined:
        return combined
    return stored


def _cell(row, key, default=None):
    return row[key] if key in row.keys() else default


def _when(value):
    if value in (None, ''):
        return None
    if hasattr(value, 'tzinfo') or hasattr(value, 'hour'):
        return value
    return parse_datetime(str(value))


class Command(BaseCommand):
    help = (
        'کاربر، پروفایل و پروفایل سرویس‌دهنده را از فایل sqlite قدیمی '
        'به مدل یکپارچه کاربر در دیتابیس فعلی منتقل می‌کند. '
        'برای همان دیتابیس، migrate کافی است؛ این دستور برای فایل جدا است.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--source', required=True, help='مسیر فایل sqlite دیتابیس قدیمی')

    def handle(self, *args, **options):
        source = Path(options['source'])
        if not source.is_file():
            raise CommandError(f'فایل پیدا نشد: {source}')
        with sqlite3.connect(source) as raw:
            raw.row_factory = sqlite3.Row
            tables = {
                row[0]
                for row in raw.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
            }
            missing = {'auth_user', 'marketplace_profile', 'marketplace_workerprofile'} - tables
            if missing:
                raise CommandError(
                    'جدول‌های قدیمی در این فایل نیستند: ' + '، '.join(sorted(missing))
                )
            users = list(raw.execute('SELECT * FROM auth_user'))
            profiles = list(raw.execute('SELECT * FROM marketplace_profile'))
            workers = list(raw.execute('SELECT * FROM marketplace_workerprofile'))
            service_links = (
                list(raw.execute(
                    'SELECT workerprofile_id, service_id FROM marketplace_workerprofile_services'
                ))
                if 'marketplace_workerprofile_services' in tables else []
            )
            city_links = (
                list(raw.execute(
                    'SELECT workerprofile_id, city_id FROM marketplace_workerprofile_cities'
                ))
                if 'marketplace_workerprofile_cities' in tables else []
            )

        profile_by_user = {_cell(row, 'user_id'): row for row in profiles}
        worker_by_user = {_cell(row, 'user_id'): row for row in workers}
        services_by_worker = {}
        for row in service_links:
            services_by_worker.setdefault(row['workerprofile_id'], []).append(row['service_id'])
        cities_by_worker = {}
        for row in city_links:
            cities_by_worker.setdefault(row['workerprofile_id'], []).append(row['city_id'])

        known_services = set(Service.objects.values_list('pk', flat=True))
        known_cities = set(City.objects.values_list('pk', flat=True))
        taken_ids = set(User.objects.values_list('pk', flat=True))
        copied = 0
        linked_services = 0
        linked_cities = 0
        skipped_links = 0

        with transaction.atomic():
            target_by_source = {}
            for row in users:
                user = self._upsert_user(row, taken_ids)
                target_by_source[row['id']] = user
                copied += 1

            for source_id, profile in profile_by_user.items():
                user = target_by_source.get(source_id)
                if user is None:
                    self.stdout.write(self.style.WARNING(f'پروفایل بدون کاربر: {source_id}'))
                    continue
                creator_id = _cell(profile, 'created_by_id')
                creator_profile = profile_by_user.get(creator_id) if creator_id else None
                creator_role = _cell(creator_profile, 'role', '') if creator_profile else ''
                creator = target_by_source.get(creator_id) if creator_role == User.ADMIN else None
                user.role = _cell(profile, 'role', '') or ''
                user.phone = _cell(profile, 'phone', '') or ''
                user.farm_city_id = _cell(profile, 'farm_city_id') if _cell(profile, 'farm_city_id') in known_cities else None
                user.farm_address = _cell(profile, 'farm_address', '') or ''
                user.farm_latitude = _cell(profile, 'farm_latitude')
                user.farm_longitude = _cell(profile, 'farm_longitude')
                user.created_by = creator
                user.save()

            for source_id, worker in worker_by_user.items():
                user = target_by_source.get(source_id)
                if user is None:
                    self.stdout.write(self.style.WARNING(f'پروفایل سرویس‌دهنده بدون کاربر: {source_id}'))
                    continue
                user.bio = _cell(worker, 'bio', '') or ''
                user.experience_years = _cell(worker, 'experience_years', 0) or 0
                user.daily_wage = _cell(worker, 'daily_wage', 0) or 0
                user.rating = _cell(worker, 'rating', 0) or 0
                user.review_count = _cell(worker, 'review_count', 0) or 0
                user.jobs_done = _cell(worker, 'jobs_done', 0) or 0
                user.is_verified = bool(_cell(worker, 'is_verified', False))
                user.accepts_jobs = bool(_cell(worker, 'is_active', True))
                user.save()
                service_ids = [
                    pk for pk in services_by_worker.get(worker['id'], []) if pk in known_services
                ]
                city_ids = [
                    pk for pk in cities_by_worker.get(worker['id'], []) if pk in known_cities
                ]
                skipped_links += (
                    len(services_by_worker.get(worker['id'], [])) - len(service_ids)
                    + len(cities_by_worker.get(worker['id'], [])) - len(city_ids)
                )
                user.services.set(service_ids)
                user.cities.set(city_ids)
                linked_services += len(service_ids)
                linked_cities += len(city_ids)

        self.stdout.write(self.style.SUCCESS(
            f'{copied} کاربر منتقل شد. {linked_services} حوزه کاری و {linked_cities} شهر وصل شد.'
        ))
        if skipped_links:
            self.stdout.write(self.style.WARNING(
                f'{skipped_links} ارتباط رد شد چون شهر یا خدمت متناظر در دیتابیس جدید نبود.'
            ))

    def _upsert_user(self, row, taken_ids):
        values = {
            'password': row['password'],
            'last_login': _when(_cell(row, 'last_login')),
            'is_superuser': bool(row['is_superuser']),
            'is_staff': bool(row['is_staff']),
            'is_active': bool(row['is_active']),
            'date_joined': _when(_cell(row, 'date_joined')) or timezone.now(),
            'name': merged_person_name(
                _cell(row, 'name', ''),
                _cell(row, 'first_name', ''),
                _cell(row, 'last_name', ''),
            ),
        }
        user = User.objects.filter(username=row['username']).first()
        if user is None:
            user = User(username=row['username'])
            if row['id'] not in taken_ids:
                user.id = row['id']
        for field, value in values.items():
            setattr(user, field, value)
        user.save()
        taken_ids.add(user.pk)
        return user
