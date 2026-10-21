from django import template

from marketplace.dates import to_jalali

register = template.Library()

_FA_DIGITS = str.maketrans('0123456789', '۰۱۲۳۴۵۶۷۸۹')


@register.filter
def fa_digits(value):
    if value is None:
        return ''
    return str(value).translate(_FA_DIGITS)


@register.filter
def jalali(value, fmt='Y/m/d'):
    return to_jalali(value, fmt)


@register.filter
def toman(value):
    try:
        number = int(value)
    except (TypeError, ValueError):
        return value
    if number == 0:
        return 'توافقی'
    formatted = f'{number:,}'.replace(',', '٬')
    return fa_digits(formatted) + ' تومان'
