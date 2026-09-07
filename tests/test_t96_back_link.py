"""T-96: с карточки канала есть заметная дорога назад.

Крошки набраны самым мелким кеглем страницы и единственным выходом с карточки
не читались. Над ними встала кнопка обычного кегля.

Проверки структурные, а не по подписи: ссылка на каталог на карточке была и до
задачи — это крошка. Тест «на странице есть ссылка на /» прошёл бы и у кнопки,
положенной в правую колонку, то есть ровно у того провала, от которого задача
уходит: ниже 860 пикселей колонка встаёт под основную, и кнопка оказалась бы
под всей лентой.

Отдельная группа — про хвост возврата. Он живёт только на ссылках с
отфильтрованной выдачи: адрес карточки входит в ключ кэша целиком, и хвост на
голом каталоге завёл бы по копии карточки на каждое состояние фильтров, а
краулеру — второе множество адресов на те же 143 тысячи страниц.
"""
import re

import pytest

pytestmark = pytest.mark.integration


def seed(layer, n=3):
    for i in range(1, n + 1):
        layer.channel(i, "tg", f"ch{i}", subscribers=i * 10_000)
    return layer


def back_block(body: str) -> str:
    """Разметка кнопки возврата от её обёртки до конца."""
    assert 'class="back-link"' in body, "кнопки возврата на карточке нет"
    return body.split('class="back-link"')[1].split("</div>")[0]


def card_links(body):
    """Ссылки на карточки каналов: `back` у строки каталога есть и своей ссылкой
    «Неточность?», и искать хвост по всему телу бессмысленно."""
    return re.findall(r'href="/tg/ch[0-9][^"]*"', body)


def plain(body):
    """Тело со снятым экранированием: в разметке `&` живёт как `&amp;`."""
    return body.replace("&amp;", "&")


# ── место кнопки на странице ─────────────────────────────────────────────────

def test_back_button_stands_above_the_breadcrumbs_and_both_columns(layer, client):
    """Кнопка первой на странице. В правой колонке она была бы бесполезна ровно
    на телефоне: ниже 860 пикселей колонка встаёт под основную."""
    layer.channel(1, "tg", "lonely")
    layer.go_live()
    body = client.get("/tg/lonely").text
    assert body.index('class="back-link"') < body.index('class="breadcrumbs"')
    assert body.index('class="back-link"') < body.index('class="channel-layout"')


def test_back_button_is_a_full_size_button_with_a_silent_arrow(layer, client):
    """Кегль штатный: мелкой кнопкой набрана крошка, из-за чего её и не видно.
    Стрелка — отдельный элемент, скрытый от читалки, иначе она произносит
    «стрелка влево в каталог». Подпись прячется на телефоне, поэтому смысл
    держит `aria-label`, а не текст."""
    layer.channel(1, "tg", "lonely")
    layer.go_live()
    block = back_block(client.get("/tg/lonely").text)
    assert "btn--ghost" in block and "btn--sm" not in block
    assert '<span aria-hidden="true">' in block
    assert 'aria-label="В каталог"' in block
    assert "В каталог" in block


# ── куда ведёт ───────────────────────────────────────────────────────────────

def test_without_a_tail_the_button_leads_to_the_bare_catalog(layer, client):
    """Прямой заход из поиска и переход с голого каталога: кнопка ведёт в
    корень. Раздел своей площадки она не подставляет — это тот же фильтр,
    которого человек не ставил."""
    layer.channel(1, "tg", "lonely")
    layer.go_live()
    block = back_block(client.get("/tg/lonely").text)
    assert 'href="/"' in block


def test_the_button_returns_to_the_filtered_listing_the_reader_came_from(layer, client):
    """Фильтры переживают заход в карточку — ради этого хвост и передаётся."""
    layer.channel(1, "tg", "lonely")
    layer.go_live()
    block = back_block(client.get("/tg/lonely?back=/%3Fsubs_min%3D25000").text)
    assert 'href="/?subs_min=25000"' in plain(block)


def test_a_foreign_address_in_the_tail_is_refused(layer, client):
    """Параметр приезжает из браузера, а не только от каталога: проверка та же,
    что у возврата формы обращений (T-73), иначе кнопка уводит на чужой сайт."""
    layer.channel(1, "tg", "lonely")
    layer.go_live()
    for evil in ("https://evil.tld", "//evil.tld", "/%5Cevil.tld"):
        block = back_block(client.get(f"/tg/lonely?back={evil}").text)
        assert "evil.tld" not in block, f"чужой адрес принят: {evil}"
        assert 'href="/"' in block


# ── хвост возврата ставится только там, где он безвреден ─────────────────────

def test_filtered_listing_hands_its_address_to_the_card(layer, client):
    seed(layer)
    layer.go_live()
    body = plain(client.get("/?subs_min=25000").text)
    assert 'href="/tg/ch3?back=/%3Fsubs_min%3D25000"' in body


def test_bare_catalog_links_to_cards_without_any_tail(layer, client):
    """Голый каталог это дорога краулера к 143 тысячам карточек: хвост здесь
    завёл бы второе множество адресов и по копии карточки в кэше."""
    seed(layer)
    layer.go_live()
    cards = card_links(plain(client.get("/").text))
    assert 'href="/tg/ch1"' in cards
    assert not [one for one in cards if "?" in one]


def test_platform_section_links_to_cards_without_any_tail(layer, client):
    """Раздел площадки индексируется наравне с корнем — по той же причине."""
    seed(layer)
    layer.go_live()
    cards = card_links(plain(client.get("/tg").text))
    assert 'href="/tg/ch1"' in cards
    assert not [one for one in cards if "?" in one]


def test_the_report_link_does_not_carry_the_tail_any_further(layer, client):
    """«Сообщить» возвращает на саму карточку, а не на её адрес с хвостом:
    вложенный `back` уезжает в форму с двойным кодированием и упирается в
    потолок длины, за которым возврат молча становится пустым."""
    layer.channel(1, "tg", "lonely")
    layer.go_live()
    body = plain(client.get("/tg/lonely?back=/%3Fsubs_min%3D25000").text)
    report = body.split('href="/report?')[1].split('"')[0]
    assert "back=/tg/lonely%23feed" in report
    assert "subs_min" not in report
