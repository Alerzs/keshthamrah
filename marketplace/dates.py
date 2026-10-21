import datetime

import jdatetime
from django.utils import timezone

JALALI_MONTHS = (
    '',
    'فروردین',
    'اردیبهشت',
    'خرداد',
    'تیر',
    'مرداد',
    'شهریور',
    'مهر',
    'آبان',
    'آذر',
    'دی',
    'بهمن',
    'اسفند',
)

_FA_DIGITS = str.maketrans('0123456789', '۰۱۲۳۴۵۶۷۸۹')


def fa_digits(value):
    return str(value).translate(_FA_DIGITS)


def _as_gregorian(value):
    if isinstance(value, datetime.datetime):
        if timezone.is_aware(value):
            value = timezone.localtime(value).replace(tzinfo=None)
        return value
    if isinstance(value, datetime.date):
        return value
    text = str(value).strip()
    if not text:
        return None
    if 'T' in text or ' ' in text:
        parsed = datetime.datetime.fromisoformat(text.replace('Z', '+00:00'))
        if timezone.is_aware(parsed):
            parsed = timezone.localtime(parsed).replace(tzinfo=None)
        return parsed
    return datetime.date.fromisoformat(text[:10])


def _strftime_format(fmt):
    converted = fmt
    for token, spec in (('Y', '%Y'), ('m', '%m'), ('d', '%d'), ('H', '%H'), ('i', '%M')):
        converted = converted.replace(token, spec)
    return converted


def to_jalali(value, fmt='Y/m/d'):
    if value in (None, ''):
        return ''
    try:
        gregorian = _as_gregorian(value)
    except (TypeError, ValueError):
        return fa_digits(value)
    if gregorian is None:
        return ''
    if isinstance(gregorian, datetime.datetime):
        converted = jdatetime.datetime.fromgregorian(datetime=gregorian)
    else:
        converted = jdatetime.date.fromgregorian(date=gregorian)
    return fa_digits(converted.strftime(_strftime_format(fmt)))


def jalali_parts(value):
    gregorian = _as_gregorian(value)
    if gregorian is None:
        return None
    if isinstance(gregorian, datetime.datetime):
        converted = jdatetime.datetime.fromgregorian(datetime=gregorian)
        return (
            str(converted.year),
            str(converted.month),
            str(converted.day),
            str(converted.hour),
            str(converted.minute),
        )
    converted = jdatetime.date.fromgregorian(date=gregorian)
    return str(converted.year), str(converted.month), str(converted.day)


def jalali_year_span(selected=None):
    today = jdatetime.date.fromgregorian(date=timezone.localdate())
    years = list(range(today.year, today.year + 3))
    try:
        year = int(selected)
    except (TypeError, ValueError):
        year = None
    if year and year not in years:
        years.append(year)
        years.sort()
    return years


def gregorian_from_jalali(year, month, day, hour=None, minute=None):
    try:
        if hour is None:
            return jdatetime.date(int(year), int(month), int(day)).togregorian()
        return jdatetime.datetime(
            int(year), int(month), int(day), int(hour), int(minute),
        ).togregorian()
    except (TypeError, ValueError):
        return None
