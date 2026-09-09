"""T-100: кнопка «Наверх» на длинных страницах витрины.

Со дна каталога (50 строк), карточки канала или политики к фильтрам и шапке
иначе только колесо или Home. Кнопка — третий и последний исполняемый скрипт
витрины, заведён осознанно решением PO 08.09 ценой правки спеки.

Проверяется структура и цель якоря, а не подпись: подпись правится без задачи.
Каталог берётся не одним адресом — корень, раздел площадки и посадочная пара, —
иначе кнопку однажды включат частично и никто не заметит.
"""
import re

import pytest

from conftest import assert_only_allowed_scripts

pytestmark = pytest.mark.integration


@pytest.fixture
def live(layer):
    """Живой слой с разделом площадки и посадочной парой «тематика + площадка»."""
    for i in range(1, 13):
        layer.channel(i, "tg", f"finance_{i}", display_name=f"Финансы {i}")
        layer.category(i, "Финансы", "finance")
    layer.post(1, "p1")
    layer.section("", "", channels=12, views_median=20_000, ads_share=40.0)
    layer.section("tg", "", channels=12, views_median=20_000, ads_share=40.0)
    layer.section("tg", "finance", name="Финансы", channels=12,
                  views_median=19_000, ads_share=41.0)
    return layer.go_live()


LONG_PAGES = ("/", "/tg", "/category/finance/tg", "/tg/finance_1", "/privacy")
CATALOG_PAGES = ("/", "/tg", "/category/finance/tg")
SHORT_PAGES = ("/report", "/report/thanks", "/no-such-page-xyz")


# ── кнопка есть там, где решено, и нет там, где не решено ─────────────────────

def test_button_stands_on_every_long_page(live, client):
    for path in LONG_PAGES:
        body = client.get(path).text
        assert '<button class="to-top"' in body, path
        assert 'aria-label="Наверх"' in body, path
        assert 'data-script="to-top"' in body, path


def test_button_is_absent_from_short_pages(live, client):
    for path in SHORT_PAGES:
        body = client.get(path).text
        assert 'class="to-top"' not in body, path
        # Скрипт едет вместе с кнопкой: нет кнопки — нет и скрипта.
        assert 'data-script="to-top"' not in body, path


# ── цель якоря ──────────────────────────────────────────────────────────────

def test_catalog_points_the_button_at_the_listing_not_the_header(live, client):
    """На каталоге управление выдачей стоит вверху списка, а не у логотипа:
    `#to-top` висит на `.layout`, шапка его не получает."""
    for path in CATALOG_PAGES:
        body = client.get(path).text
        assert '<div class="layout" id="to-top" tabindex="-1">' in body, path
        assert '<header class="hdr" id="to-top"' not in body, path


def test_channel_and_privacy_point_the_button_at_the_header(live, client):
    """Управления на карточке и политике нет — цель кнопки начало документа."""
    for path in ("/tg/finance_1", "/privacy"):
        body = client.get(path).text
        assert '<header class="hdr" id="to-top" tabindex="-1">' in body, path


def test_the_anchor_id_is_unique_on_every_long_page(live, client):
    """Провал здесь — это дубль с шапкой: два элемента с одним `id` увели бы
    к первому в документе, то есть к шапке, мимо решения PO."""
    for path in LONG_PAGES:
        body = client.get(path).text
        assert body.count('id="to-top"') == 1, (path, body.count('id="to-top"'))


# ── белый список скриптов ───────────────────────────────────────────────────

def test_scripts_stay_inside_the_whitelist_everywhere(live, client):
    """Кнопка — третий разрешённый скрипт. На коротких страницах его нет, и это
    не ошибка; счётчик Метрики по-прежнему ровно один."""
    for path in LONG_PAGES + SHORT_PAGES:
        assert_only_allowed_scripts(client.get(path).text, path)


def test_a_second_to_top_script_would_be_caught():
    """Тихо мимо проверки задвоенный скрипт кнопки проехать не должен."""
    counter = ('<script type="text/javascript">'
               "ym(112192205, 'init', {});"
               ' new Image().src = "https://mc.yandex.ru/metrika/tag.js";</script>')
    page = (f'<body>{counter}'
            '<script data-script="to-top">1</script>'
            '<script data-script="to-top">2</script></body>')
    with pytest.raises(AssertionError):
        assert_only_allowed_scripts(page)


# ── плавность и уменьшенное движение ─────────────────────────────────────────

def test_smooth_scroll_is_a_root_rule_with_a_reduced_motion_escape(live, client):
    css = client.get("/assets/tokens.css").text
    bare = re.sub(r"/\*.*?\*/", " ", css, flags=re.S)
    assert re.search(r"html\s*\{[^}]*scroll-behavior\s*:\s*smooth", bare)
    reduce = re.search(
        r"@media\s*\(\s*prefers-reduced-motion\s*:\s*reduce\s*\)\s*\{(.+?\})\s*\}",
        bare, re.S)
    assert reduce and re.search(r"scroll-behavior\s*:\s*auto", reduce.group(1))


def test_button_clears_the_cookie_notice_by_reading_its_height(live, client):
    """Смещение над плашкой куки объявляет сама плашка переменной; кнопка
    читает её с запасным значением, иначе `calc()` невалиден до объявления."""
    components = client.get("/assets/components.css").text
    bare = re.sub(r"/\*.*?\*/", " ", components, flags=re.S)
    rule = re.search(r"\.to-top\s*\{([^}]*)\}", bare)
    assert rule and "var(--cookie-notice-h, 0px)" in rule.group(1)
    base = client.get("/").text
    assert "--cookie-notice-h" in base


def test_button_hides_under_open_mobile_filters_without_the_script(live, client):
    components = client.get("/assets/components.css").text
    bare = re.sub(r"/\*.*?\*/", " ", components, flags=re.S)
    assert re.search(r"body:has\(details\.side-mobile\[open\]\)\s*\.to-top", bare)
