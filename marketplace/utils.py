import re

_DIGIT_MAP = str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789')


def normalize_digits(value):
    return str(value or '').translate(_DIGIT_MAP)


def normalize_phone(value):
    phone = normalize_digits(value)
    phone = re.sub(r'[\s\-\u200c]', '', phone)
    if phone.startswith('+98'):
        phone = '0' + phone[3:]
    elif phone.startswith('0098'):
        phone = '0' + phone[4:]
    elif phone.startswith('98') and len(phone) == 12:
        phone = '0' + phone[2:]
    return phone
