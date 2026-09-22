"""T-121: надпись кнопки по центру, панель заказа под метриками на телефоне.

Доработка T-118 по замечаниям PO после раскатки. Две находки: у канала без
крючка одинокое «Заказать рекламу» прижималось к левому краю кнопки в шапке,
а панель «увидит до N человек» на телефоне стояла последним блоком страницы,
потому что правая колонка под 860 px идёт по порядку разметки.

Панель теперь размечена дважды, как «Площадки автора»: копия в основной
колонке сразу под метриками основного канала, оригинал в aside. Каждая скрыта
на чужой ширине, и это разводит CSS — здесь стоят контракты на разметку и на
сами правила, а как оно выглядит на 390 px, проверяется глазами по DoD.
"""
import re

import pytest

from conftest import assert_only_allowed_scripts

pytestmark = pytest.mark.integration

ACTIONS = re.compile(r'<div class="actions">(.*?)</div>', re.S)
ORDER_BTN = re.compile(r'<a class="btn([^"]*\border-btn\b[^"]*)"[^>]*>(.*?)</a>', re.S)
INVITE_MOBILE = re.compile(r'<div class="invite-mobile">(.*?)</div>', re.S)
INVITE_PANEL = '<div class="group invite-panel">'


def text_of(html: str) -> str:
    return " ".join(re.sub(r"<[^>]+>", " ", html).replace("\xa0", " ").split())


@pytest.fixture
def css(client):
    body = client.get("/assets/components.css")
    assert body.status_code == 200
    return re.sub(r"/\*.*?\*/", " ", body.text, flags=re.S)


def _media_860(css: str) -> str:
    """Тело всех медиазапросов `max-width: 860px` одной строкой."""
    blocks = []
    for m in re.finditer(r"@media\s*\(max-width:\s*860px\)\s*\{", css):
        depth, i = 1, m.end()
        while depth and i < len(css):
            depth += {"{": 1, "}": -1}.get(css[i], 0)
            i += 1
        blocks.append(css[m.end():i - 1])
    assert blocks, "медиазапроса 860px в components.css нет"
    return "\n".join(blocks)


def _rule(css: str, selector: str) -> str:
    body = ""
    for heads, decls in re.findall(r"([^{}]+)\{([^}]*)\}", css):
        if selector in [one.strip() for one in heads.split(",")]:
            body += decls + ";"
    assert body, f"правила `{selector}` нет"
    return body


def own_block(body: str, channel_id: int) -> str:
    """Разметка `section.ch-block` канала от `.head` до первой `section.panel`."""
    start = body.index(f'<section class="ch-block" id="ch-{channel_id}">')
    end = body.index('<section class="panel"', start)
    return body[start:end]


# ── кнопка в шапке ───────────────────────────────────────────────────────────

def test_order_button_without_a_subline_centers_its_label(layer, client):
    layer.channel(1, "max", "solo", wowblogger_slug="solo", blogger_id=3,
                  url="https://max.ru/solo", views_organic=None, views_ad=None, ads_30d=0)
    layer.go_live()

    actions = ACTIONS.search(client.get("/max/solo").text).group(1)
    cls, inner = ORDER_BTN.search(actions).groups()
    assert "order-btn" in cls.split()
    assert "order-btn--solo" in cls.split()
    assert "order-sub" not in inner
    assert text_of(inner) == "Заказать рекламу"


def test_order_button_with_a_subline_keeps_the_two_line_look(layer, client):
    layer.channel(1, "tg", "hooked", wowblogger_slug="hooked", blogger_id=4,
                  url="https://t.me/hooked", views_organic=22_200, views_ad=95_400)
    layer.go_live()

    actions = ACTIONS.search(client.get("/tg/hooked").text).group(1)
    cls, inner = ORDER_BTN.search(actions).groups()
    assert "order-btn" in cls.split()
    assert "order-btn--solo" not in cls.split()
    assert '<span class="order-sub">увидят до 95 тыс.</span>' in inner


def test_solo_modifier_centers_and_keeps_the_finger_height(css):
    assert re.search(r"align-items\s*:\s*center", _rule(css, ".order-btn--solo"))
    assert re.search(r"min-height\s*:\s*44px", _rule(css, ".order-btn"))


# ── мобильная копия панели под метриками ────────────────────────────────────

def test_mobile_invite_stands_between_the_head_and_the_first_panel(layer, client):
    layer.channel(1, "tg", "metrics", wowblogger_slug="metrics", blogger_id=9,
                  url="https://t.me/metrics", views_ad=95_400)
    layer.go_live()

    body = client.get("/tg/metrics").text
    block = own_block(body, 1)
    copies = INVITE_MOBILE.findall(block)
    assert len(copies) == 1
    head_end = block.index('<div class="m-tiles">')
    assert block.index('<div class="invite-mobile">') > head_end

    copy = copies[0]
    assert "Вашу рекламу в этом канале увидит" in text_of(copy)
    assert '<b class="invite-num">до 95 тыс.</b>' in copy
    assert re.search(r'<a class="btn invite-btn" href="([^"]*)"', copy)
    href = re.search(r'<a class="btn invite-btn" href="([^"]*)"', copy).group(1)
    assert href.startswith("https://wowblogger.ru/bloggers/metrics?")
    assert "utm_term=card" in href and "utm_content=9" in href
    assert text_of(copy).endswith("Заказать рекламу →")

    assert body.count(INVITE_PANEL) == 1
    assert body.index(INVITE_PANEL) > body.index('<aside class="side channel-side">')
    assert body.count('<div class="invite-mobile">') == 1
    assert_only_allowed_scripts(body, where=" (карточка канала)")


def test_mobile_invite_without_a_number_shows_the_heading(layer, client):
    layer.channel(1, "max", "quiet", wowblogger_slug="quiet", blogger_id=2,
                  url="https://max.ru/quiet", views_organic=None, views_ad=None, ads_30d=0)
    layer.go_live()

    copy = INVITE_MOBILE.search(client.get("/max/quiet").text).group(1)
    assert text_of(copy) == "Реклама в этом канале Заказать рекламу →"
    assert "invite-num" not in copy


def test_mobile_invite_precedes_the_chart_when_there_is_one(layer, client):
    from datetime import date, timedelta
    layer.channel(1, "tg", "charted", wowblogger_slug="charted", blogger_id=8,
                  url="https://t.me/charted")
    today = date.today()
    layer.history(1, [(today - timedelta(days=d), 100_000 + d * 10) for d in range(10, 0, -1)])
    layer.go_live()

    body = client.get("/tg/charted").text
    assert "Динамика подписчиков" in body
    assert body.index('<div class="invite-mobile">') < body.index("Динамика подписчиков")


def test_siblings_have_no_mobile_copy(layer, client):
    layer.channel(1, "tg", "main_two", wowblogger_slug="author", blogger_id=5,
                  url="https://t.me/main_two", views_ad=95_400)
    layer.channel(2, "vk", "side_two", wowblogger_slug="author", blogger_id=5,
                  url="https://vk.com/side_two", views_ad=None, views_organic=None, ads_30d=0)
    layer.sibling(1, 2)
    layer.sibling(2, 1)
    layer.go_live()

    body = client.get("/tg/main_two").text
    assert body.count('<div class="invite-mobile">') == 1
    assert '<div class="invite-mobile">' in own_block(body, 1)
    sibling_start = body.index('<section class="ch-block" id="ch-2">')
    assert '<div class="invite-mobile">' not in body[sibling_start:]
    assert body.count(INVITE_PANEL) == 1


def test_no_slug_means_no_mobile_copy(layer, client):
    layer.channel(1, "tg", "orphan", wowblogger_slug=None, url="https://t.me/orphan")
    layer.go_live()

    body = client.get("/tg/orphan").text
    assert "invite-mobile" not in body
    assert INVITE_PANEL not in body
    assert "wowblogger.ru" not in body


# ── CSS: каждая разметка скрыта на чужой ширине ─────────────────────────────

def test_mobile_copy_is_hidden_by_default_and_shown_under_860(css):
    assert re.search(r"display\s*:\s*none", _rule(css, ".invite-mobile"))
    narrow = _media_860(css)
    assert re.search(r"\.invite-mobile\s*\{[^}]*display\s*:\s*(flex|block)", narrow)
    assert re.search(r"\.channel-side \.group\.invite-panel\s*\{[^}]*display\s*:\s*none", narrow)


def test_mobile_copy_has_its_own_box_not_the_side_panel_one(css):
    body = _rule(css, ".invite-mobile")
    assert "invite-bg" in body
    assert re.search(r"border-radius\s*:\s*var\(--r-lg\)", body)
    assert re.search(r"margin-top\s*:\s*var\(--sp-4\)", body)
    assert "calc(var(--sp-4) * -1)" not in body


def test_under_860_the_side_groups_lose_the_top_line(css):
    narrow = _media_860(css)
    assert re.search(r"\.channel-side \.group\s*\{[^}]*border-top\s*:\s*0", narrow)
    assert re.search(r"\.channel-side \.group\s*\{[^}]*padding-top\s*:\s*0", narrow)
    assert ".channel-side .group.sites-nav-desktop:first-of-type + .group" not in narrow
