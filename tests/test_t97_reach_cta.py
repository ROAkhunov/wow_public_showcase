"""T-97: обещание охвата как приглашение купить рекламу.

Цифра одна на три места — всплывашка каталога, подстрочник кнопки и панель
карточки канала. Тесты смотрят на две вещи: как цифра записывается и что из неё
попадает в HTML. Что из этих трёх мест видно на телефоне, а что на десктопе,
pytest не видит вовсе: это разводит CSS, и проверяется глазами.
"""
import re

import pytest

from app.format import reach, reach_promise
from conftest import assert_only_allowed_scripts

pytestmark = pytest.mark.integration

#: блок приглашения в строке каталога и панель на карточке — вложенных `div`
#: внутри нет, поэтому нежадной вырезки хватает. Проверять слово «WOWBlogger»
#: по всей странице нельзя: у соседних площадок канала оно стоит сознательно.
INVITE_ROW = re.compile(r'<div class="invite">(.*?)</div>', re.S)
INVITE_PANEL = re.compile(r'<div class="group invite-panel">(.*?)</div>', re.S)

PHRASE = "Вашу рекламу в этом канале увидит до {} человек"


def text_of(html: str) -> str:
    """Видимый текст фрагмента: без тегов и с одиночными пробелами."""
    return " ".join(re.sub(r"<[^>]+>", " ", html).replace("\xa0", " ").split())


def invite_for(body: str, slug: str) -> str | None:
    """Блок приглашения той строки каталога, что ведёт на этот слаг."""
    for block in INVITE_ROW.findall(body):
        if f"/{slug}" in block:
            return block
    return None


# ── как записывается цифра ───────────────────────────────────────────────────

@pytest.mark.parametrize("value, expected", [
    (None, ""),          # обещать нечего
    (0, ""),
    (12, ""),
    (99, ""),            # порог: ниже сотни обещания нет вовсе
    (100, "100"),
    (843, "840"),        # округление всегда вниз
    (999, "990"),
    (1_000, "1 тыс."),   # хвост «,0» не печатается ни в тысячах, ни в миллионах
    (2_149, "2,1 тыс."),
    (9_999, "9,9 тыс."),
    (10_000, "10 тыс."),
    (18_900, "18 тыс."),
    (95_000, "95 тыс."),
    (950_500, "950 тыс."),
    (999_999, "999 тыс."),
    (1_000_000, "1 млн"),
    (1_280_000, "1,2 млн"),
])
def test_reach_is_always_rounded_down(value, expected):
    assert reach(value).replace("\xa0", " ") == expected


# ── какое поле берётся ───────────────────────────────────────────────────────

@pytest.mark.parametrize("row, expected", [
    ({"views_ad": 15_400, "views_organic": 22_200}, "15 тыс."),   # рекламный побеждает
    ({"views_ad": None, "views_organic": 22_200}, "22 тыс."),     # и заменяется обычным
    ({"views_ad": 0, "views_organic": 5_000}, ""),                # ноль это заполненное значение
    ({"views_ad": 40, "views_organic": 5_000}, ""),               # порог подмены не делает
    ({"views_ad": None, "views_organic": None}, ""),
])
def test_ad_reach_wins_even_when_it_is_small(row, expected):
    assert reach_promise(row).replace("\xa0", " ") == expected


# ── строка каталога ──────────────────────────────────────────────────────────

def test_catalog_row_promises_the_ad_reach(layer, client):
    layer.channel(1, "tg", "with_ad", subscribers=300_000,
                  wowblogger_slug="with-ad", views_organic=22_200, views_ad=95_400)
    layer.go_live()

    body = client.get("/").text
    block = invite_for(body, "with-ad")
    assert block is not None
    text = text_of(block)
    assert PHRASE.format("95 тыс.") in text          # всплывашка, дословно
    assert "увидят до 95 тыс." in text               # подстрочник кнопки
    assert "22 200" not in text                      # обычный охват сюда не попадает
    assert "WOWBlogger" not in block                 # имя площадки в блоке не звучит
    assert_only_allowed_scripts(body, where=" (каталог)")


def test_catalog_row_falls_back_to_the_organic_reach(layer, client):
    layer.channel(1, "tg", "no_ad", subscribers=300_000,
                  wowblogger_slug="no-ad", views_organic=2_149, views_ad=None)
    layer.go_live()

    block = invite_for(client.get("/").text, "no-ad")
    assert PHRASE.format("2,1 тыс.") in text_of(block)


def test_catalog_row_without_a_number_promises_nothing(layer, client):
    """Кнопка остаётся, обещания нет: ни всплывашки, ни подстрочника."""
    layer.channel(1, "tg", "empty_reach", subscribers=300_000,
                  wowblogger_slug="empty-reach", views_organic=None, views_ad=None)
    layer.channel(2, "tg", "tiny_ad", subscribers=200_000,
                  wowblogger_slug="tiny-ad", views_organic=5_000, views_ad=40)
    layer.go_live()

    body = client.get("/").text
    for slug in ("empty-reach", "tiny-ad"):
        block = invite_for(body, slug)
        assert block is not None, f"кнопка у строки {slug} должна остаться"
        assert "Разместить" in block
        assert "увидит" not in block and "увидят" not in block
    assert "до 5 тыс." not in body                   # подмены обычным охватом нет


def test_catalog_row_without_a_slug_has_no_button_at_all(layer, client):
    layer.channel(1, "tg", "no_slug", subscribers=300_000,
                  wowblogger_slug=None, views_organic=95_400)
    layer.go_live()

    body = client.get("/").text
    assert INVITE_ROW.search(body) is None
    assert "Неточность" in body                      # колонка действий не опустела


def test_popover_and_button_carry_the_same_number(layer, client):
    layer.channel(1, "tg", "same_number", subscribers=300_000,
                  wowblogger_slug="same-number", views_organic=1_000, views_ad=18_900)
    layer.go_live()

    block = invite_for(client.get("/").text, "same-number")
    numbers = re.findall(r"до (\S+ (?:тыс\.|млн)|\d+)", text_of(block))
    assert numbers and len(set(numbers)) == 1, numbers


# ── карточка канала ──────────────────────────────────────────────────────────

def test_channel_panel_replaces_the_old_disclaimer(layer, client):
    layer.channel(1, "tg", "with_panel", wowblogger_slug="with-panel",
                  views_organic=22_200, views_ad=95_400)
    layer.go_live()

    body = client.get("/tg/with_panel").text
    panel = INVITE_PANEL.search(body)
    assert panel is not None
    text = text_of(panel.group(1))
    assert PHRASE.format("95 тыс.") in text
    assert "Подробнее" in text
    assert "WOWBlogger" not in panel.group(1)
    assert "стоимость размещения на стороне" not in body
    assert "Перейти к размещению" not in body
    assert_only_allowed_scripts(body, where=" (карточка канала)")


def test_channel_panel_stays_dark_without_a_number(layer, client):
    layer.channel(1, "tg", "silent_panel", wowblogger_slug="silent-panel",
                  views_organic=None, views_ad=None)
    layer.go_live()

    body = client.get("/tg/silent_panel").text
    panel = INVITE_PANEL.search(body)
    assert panel is not None
    assert text_of(panel.group(1)) == "Реклама в этом канале Подробнее →"
    assert "стоимость размещения на стороне" not in body


def test_channel_without_a_slug_has_no_panel(layer, client):
    layer.channel(1, "tg", "orphan", wowblogger_slug=None, views_ad=95_400)
    layer.go_live()

    assert INVITE_PANEL.search(client.get("/tg/orphan").text) is None


def test_panel_number_is_the_main_channel_own_promise(layer, client):
    """Плиток «Охват поста» на странице столько, сколько площадок у автора, —
    сверяемся с цифрой из фикстуры, а не со строкой соседней плитки."""
    layer.channel(1, "tg", "main_one", blogger_id=7, blogger_has_siblings=True,
                  wowblogger_slug="main-one", views_organic=1_000, views_ad=95_400)
    layer.channel(2, "vk", "sibling_one", blogger_id=7, blogger_has_siblings=True,
                  wowblogger_slug="sibling-one", views_organic=500_000, views_ad=700_000)
    layer.sibling(1, 2)
    layer.sibling(2, 1)
    layer.go_live()

    panel = INVITE_PANEL.search(client.get("/tg/main_one").text)
    assert PHRASE.format("95 тыс.") in text_of(panel.group(1))
