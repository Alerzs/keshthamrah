import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

CLASSIC_URL = 'https://rest.payamak-panel.com/api/SendSMS/SendSMS'
CONSOLE_URL = 'https://console.melipayamak.com/api/send/simple/'

CLASSIC_ERRORS = {
    '0': 'نام کاربری یا رمز عبور پنل ملی‌پیامک اشتباه است.',
    '-108': 'آی‌پی این سرور به‌خاطر تلاش ناموفق در ملی‌پیامک مسدود شده است.',
    '-109': 'آی‌پی سرور در پنل ملی‌پیامک مجاز نشده است.',
    '-110': 'به‌جای رمز عبور باید کلید API پنل را وارد کنید.',
    '2': 'اعتبار پنل ملی‌پیامک کافی نیست.',
    '5': 'شماره خط ارسال معتبر نیست.',
    '6': 'سامانه ملی‌پیامک در حال به‌روزرسانی است.',
    '7': 'متن پیامک از نظر ملی‌پیامک مجاز نیست.',
    '9': 'ارسال از خط عمومی با وب‌سرویس ممکن نیست.',
    '10': 'کاربر پنل فعال نیست.',
    '11': 'پیامک ارسال نشد. شماره گیرنده در لیست سیاه مخابرات است.',
    '35': 'پیامک ارسال نشد. شماره گیرنده در لیست سیاه مخابرات است.',
    '12': 'مدارک پنل کامل نیست.',
    '14': 'متن پیامک لینک دارد و این خط آن را نمی‌پذیرد.',
    '18': 'شماره گیرنده نامعتبر است.',
}


class SmsError(Exception):
    pass


def send_account_sms(phone, password):
    panel_user = settings.MELIPAYAMAK_USERNAME
    panel_password = settings.MELIPAYAMAK_PASSWORD
    sender = settings.MELIPAYAMAK_FROM
    api_key = settings.MELIPAYAMAK_KEY
    if not sender or not (api_key or (panel_user and panel_password)):
        raise SmsError('تنظیمات ملی‌پیامک کامل نیست.')

    text = f'کشت همراه\nنام کاربری: {phone}\nرمز عبور: {password}'
    if api_key:
        return _send_console(api_key, sender, phone, text)
    return _send_classic(panel_user, panel_password, sender, phone, text)


def _send_classic(panel_user, panel_password, sender, phone, text):
    payload = _post(CLASSIC_URL, data={
        'username': panel_user,
        'password': panel_password,
        'to': phone,
        'from': sender,
        'text': text,
        'isFlash': 'false',
    })
    if _accepted_rec_id(payload.get('Value') if isinstance(payload, dict) else None):
        return payload
    raise SmsError(_classic_reason(payload))


def _send_console(api_key, sender, phone, text):
    payload = _post(CONSOLE_URL + api_key, json={
        'from': sender,
        'to': phone,
        'text': text,
    })
    rec_id = payload.get('recId') if isinstance(payload, dict) else None
    try:
        accepted = int(rec_id) > 0
    except (TypeError, ValueError):
        accepted = False
    if accepted:
        return payload
    status = payload.get('status') if isinstance(payload, dict) else ''
    reason = str(status).strip()[:160] if status else ''
    logger.warning('Melipayamak rejected the message: %s', reason or 'unknown')
    raise SmsError(reason or 'ملی‌پیامک پیام را نپذیرفت.')


def _post(url, **kwargs):
    try:
        response = requests.post(url, timeout=15, **kwargs)
        payload = response.json()
    except requests.RequestException as exc:
        logger.warning('Melipayamak request failed: %s', type(exc).__name__)
        raise SmsError('ارتباط با ملی‌پیامک برقرار نشد.') from exc
    except ValueError as exc:
        logger.warning('Melipayamak returned a non-JSON response')
        raise SmsError('ارتباط با ملی‌پیامک برقرار نشد.') from exc
    if not isinstance(payload, dict):
        raise SmsError('ملی‌پیامک پیام را نپذیرفت.')
    return payload


def _accepted_rec_id(value):
    try:
        return int(str(value).strip()) > 100
    except (TypeError, ValueError):
        return False


def _classic_reason(payload):
    if not isinstance(payload, dict):
        return 'ملی‌پیامک پیام را نپذیرفت.'
    value = str(payload.get('Value', '')).strip()
    status = str(payload.get('StrRetStatus') or '')
    logger.warning('Melipayamak rejected the message: %s %s', value or '-', status or '-')
    if value in CLASSIC_ERRORS:
        return CLASSIC_ERRORS[value]
    if status == 'UserNameAndPasswordFailed':
        return CLASSIC_ERRORS['0']
    return 'ملی‌پیامک پیام را نپذیرفت.'
