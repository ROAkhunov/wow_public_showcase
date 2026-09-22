"""T-119: крючок по цепочке охват → реклама за месяц.

MAX просмотров не отдаёт (T-48), и у всех его карточек с кнопкой цифры не было:
панель показывала нейтральное «Реклама в этом канале». Цепочка теперь длиннее:
рекламный охват, иначе обычный, иначе число рекламных постов за месяц («За месяц
в канале вышло 12 рекламных постов»), и только потом нейтральный вариант.

`reach_promise` отдаёт не строку, а объект с готовыми кусками текста: пять мест
показа кладут вокруг цифры свою разметку, но слов сами не сочиняют. Как хвост
всплывашки помещается в 300 px, pytest не видит: это глазами по DoD.
"""
import re

import pytest

from app.format import reach_promise
from conftest import assert_only_allowed_scripts

pytestmark = pytest.mark.integration

INVITE_ROW = re.compile(r'<div class="invite">(.*?)</div>', re.S)
INVITE_PANEL = re.compile(r'<div class="group invite-panel">(.*?)</div>', re.S)
INVITE_MOBILE = re.compile(r'<div class="invite-mobile">(.*?)</div>', re.S)
ACTIONS = re.compile(r'<div class="actions">(.*?)</div>', re.S)
ORDER_BTN = re.compile(r'<a class="btn([^"]*\border-btn\b[^"]*)"[^>]*>(.*?)</a>', re.S)

ADS_PHRASE = "За месяц в канале вышло 12 рекламных постов"


def text_of(html: str) -> str:
    return " ".join(re.sub(r"<[^>]+>", " ", html).replace("\xa0", " ").split())


def invite_for(body: str, slug: str) -> str | None:
    for block in INVITE_ROW.findall(body):
        if f"/{slug}" in block:
            return block
    return None


def plain(hook) -> dict:
    return {k: v.replace("\xa0", " ") for k, v in hook.items()}


# ── какой крючок выбирается ──────────────────────────────────────────────────

@pytest.mark.parametrize("row, kind, num", [
    ({"views_ad": 15_400, "views_organic": 22_200, "ads_30d": 12}, "reach", "до 15 тыс."),
    ({"views_ad": None, "views_organic": 22_200, "ads_30d": 12}, "reach", "до 22 тыс."),
    ({"views_ad": 40, "views_organic": 5_000, "ads_30d": 12}, "ads", "12"),   # порог подмены не делает, но к рекламе пускает
    ({"views_ad": 0, "views_organic": 5_000, "ads_30d": 12}, "ads", "12"),
    ({"views_ad": None, "views_organic": None, "ads_30d": 12}, "ads", "12"),
])
def test_hook_follows_the_chain(row, kind, num):
    hook = plain(reach_promise(row))
    assert hook["kind"] == kind
    assert hook["num"] == num


@pytest.mark.parametrize("ads", [0, None])
def test_no_hook_without_reach_and_without_ads(ads):
    assert reach_promise({"views_ad": None, "views_organic": None, "ads_30d": ads}) is None
    assert reach_promise({"views_ad": 40, "views_organic": 5_000, "ads_30d": ads}) is None


def test_reach_hook_has_every_piece():
    hook = plain(reach_promise({"views_ad": 95_400, "views_organic": None, "ads_30d": 12}))
    assert hook == {"kind": "reach", "lead": "Вашу рекламу в этом канале", "verb": "увидит",
                    "num": "до 95 тыс.", "tail": "человек", "sub": "увидят до 95 тыс."}


@pytest.mark.parametrize("ads, verb, tail, sub", [
    (1, "вышел", "рекламный пост", "1 рекламный за месяц"),
    (2, "вышло", "рекламных поста", "2 рекламных за месяц"),
    (5, "вышло", "рекламных постов", "5 рекламных за месяц"),
    (12, "вышло", "рекламных постов", "12 рекламных за месяц"),
    (21, "вышел", "рекламный пост", "21 рекламный за месяц"),
])
def test_ads_hook_agrees_in_number(ads, verb, tail, sub):
    hook = plain(reach_promise({"views_ad": None, "views_organic": None, "ads_30d": ads}))
    assert hook["kind"] == "ads"
    assert hook["lead"] == "За месяц в канале"
    assert (hook["verb"], hook["num"], hook["tail"], hook["sub"]) == (verb, str(ads), tail, sub)


# ── строка каталога ──────────────────────────────────────────────────────────

def test_catalog_row_without_reach_promises_the_ads(layer, client):
    layer.channel(1, "max", "adsonly", subscribers=300_000, wowblogger_slug="ads-only",
                  url="https://max.ru/adsonly", views_organic=None, views_ad=None, ads_30d=12)
    layer.channel(2, "tg", "with_ad", subscribers=300_000, wowblogger_slug="with-ad",
                  views_organic=22_200, views_ad=95_400, ads_30d=12)
    layer.go_live()

    body = client.get("/").text
    block = invite_for(body, "ads-only")
    assert block is not None
    text = text_of(block)
    assert "12 рекламных за месяц" in text            # подстрочник кнопки
    assert ADS_PHRASE in text                          # всплывашка, дословно
    assert "увидит" not in text and "увидят" not in text
    assert 'class="invite-nb">вышло <b>12</b> рекламных постов' in block  # хвост одной строкой

    block = invite_for(body, "with-ad")
    text = text_of(block)
    assert "увидят до 95 тыс." in text
    assert "Вашу рекламу в этом канале увидит до 95 тыс. человек" in text
    assert "рекламных постов" not in text
    assert_only_allowed_scripts(body, where=" (каталог)")


# ── карточка канала ──────────────────────────────────────────────────────────

def test_channel_page_without_reach_promises_the_ads(layer, client):
    layer.channel(1, "max", "club1", wowblogger_slug="club-1", blogger_id=3,
                  url="https://max.ru/club1", views_organic=None, views_ad=None, ads_30d=12)
    layer.go_live()

    body = client.get("/max/club1").text
    cls, inner = ORDER_BTN.search(ACTIONS.search(body).group(1)).groups()
    assert "order-btn--solo" not in cls
    assert text_of(inner) == "Заказать рекламу 12 рекламных за месяц"

    for pattern in (INVITE_PANEL, INVITE_MOBILE):
        html = pattern.search(body).group(1)
        assert ADS_PHRASE in text_of(html)
        assert '<b class="invite-num">12</b>' in html
        assert "invite-head" not in html
        assert "увидит" not in html
    assert_only_allowed_scripts(body, where=" (карточка канала)")


def test_channel_page_without_reach_and_ads_stays_neutral(layer, client):
    layer.channel(1, "max", "club0", wowblogger_slug="club-0", blogger_id=3,
                  url="https://max.ru/club0", views_organic=None, views_ad=None, ads_30d=0)
    layer.go_live()

    body = client.get("/max/club0").text
    cls, inner = ORDER_BTN.search(ACTIONS.search(body).group(1)).groups()
    assert "order-btn--solo" in cls
    assert text_of(inner) == "Заказать рекламу"
    for pattern in (INVITE_PANEL, INVITE_MOBILE):
        html = pattern.search(body).group(1)
        assert text_of(html) == "Реклама в этом канале Заказать рекламу →"
        assert "рекламных" not in html
