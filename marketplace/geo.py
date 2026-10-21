import json
from functools import lru_cache
from pathlib import Path

CITY_CENTERS = {
    'مشهد': (36.2972, 59.6067),
    'نیشابور': (36.2140, 58.7960),
    'سبزوار': (36.2126, 57.6819),
    'شیراز': (29.5918, 52.5837),
    'مرودشت': (29.8742, 52.8025),
    'اصفهان': (32.6546, 51.6680),
    'تبریز': (38.0800, 46.2919),
    'ارومیه': (37.5550, 45.0725),
    'اهواز': (31.3183, 48.6706),
    'دزفول': (32.3831, 48.4236),
    'کرمان': (30.2839, 57.0834),
    'رفسنجان': (30.4067, 55.9939),
    'رشت': (37.2808, 49.5832),
    'گرگان': (36.8456, 54.4393),
    'ساری': (36.5633, 53.0601),
    'همدان': (34.7990, 48.5150),
    'قزوین': (36.2797, 50.0049),
    'کرمانشاه': (34.3277, 47.0778),
    'زنجان': (36.6736, 48.4787),
    'یزد': (31.8974, 54.3569),
    'بیرجند': (32.8663, 59.2211),
    'زاهدان': (29.4963, 60.8629),
    'بجنورد': (37.4750, 57.3290),
    'اراک': (34.0954, 49.7013),
    'سنندج': (35.3219, 46.9862),
}


OUTSIDE_IRAN = 'موقعیت انتخاب‌شده خارج از مرزهای ایران است.'
_BORDER_PATH = Path(__file__).resolve().parent / 'data' / 'iran_border.json'


@lru_cache(maxsize=1)
def iran_border():
    with _BORDER_PATH.open(encoding='utf-8') as handle:
        return json.load(handle)


def _ring_contains(lng, lat, ring):
    inside = False
    previous = ring[-1]
    for point in ring:
        lng_a, lat_a = previous
        lng_b, lat_b = point
        if (lat_a > lat) != (lat_b > lat) and lng < (lng_b - lng_a) * (lat - lat_a) / (lat_b - lat_a) + lng_a:
            inside = not inside
        previous = point
    return inside


def in_iran(lat, lng):
    try:
        lat = float(lat)
        lng = float(lng)
    except (TypeError, ValueError):
        return False
    return any(_ring_contains(lng, lat, ring) for ring in iran_border()['polygons'])


def city_centers():
    from .models import City

    centers = {}
    for city in City.objects.all().only('id', 'name'):
        coords = CITY_CENTERS.get(city.name)
        if coords:
            centers[str(city.pk)] = {'lat': coords[0], 'lng': coords[1]}
    return centers
