"""T-118: «Заказать рекламу» — первое действие карточки канала.

До этой задачи единственной акцентной кнопкой в шапке была «Открыть канал»,
а выход в WOWBlogger у основного канала жил только в правой колонке — на
телефоне это последний блок страницы. Теперь выход стоит первым в шапке,
у основного канала и у соседей одинаково, «Открыть канал» уходит в призрачные.
Надпись одна на все три выхода (каталог, шапка, панель): «Заказать рекламу» —
так действие названо на стороне WOWBlogger.

Что из этого видно на первом экране телефона, pytest не видит: это проверяется
глазами по DoD.
"""
import re

import pytest

from conftest import assert_only_allowed_scripts

pytestmark = pytest.mark.integration

ACTIONS = re.compile(r'<div class="actions">(.*?)</div>', re.S)
BUTTON = re.compile(r'<a class="btn([^"]*)"[^>]*href="([^"]*)"[^>]*>(.*?)</a>', re.S)
INVITE_PANEL = re.compile(r'<div class="group invite-panel">(.*?)</div>', re.S)


def text_of(html: str) -> str:
    return " ".join(re.sub(r"<[^>]+>", " ", html).replace("\xa0", " ").split())


def buttons_of(actions_html: str) -> list[tuple[str, str, str]]:
    """Кнопки блока действий по порядку: (классы, адрес, видимый текст)."""
    return [(cls.strip(), href, text_of(inner)) for cls, href, inner in BUTTON.findall(actions_html)]


# ── шапка основного канала ───────────────────────────────────────────────────

def test_order_button_is_the_first_action_of_the_channel_head(layer, client):
    layer.channel(1, "tg", "ordered", wowblogger_slug="ordered", blogger_id=77,
                  url="https://t.me/ordered", views_organic=22_200, views_ad=95_400)
    layer.go_live()

    body = client.get("/tg/ordered").text
    actions = ACTIONS.search(body)
    assert actions is not None
    first, second = buttons_of(actions.group(1))[:2]

    cls, href, text = first
    assert "btn--primary" in cls
    assert href.startswith("https://wowblogger.ru/bloggers/ordered?")
    assert "utm_term=card" in href and "utm_content=77" in href
    assert text.startswith("Заказать рекламу")
    assert "увидят до 95 тыс." in text          # тот же крючок, что в каталоге

    cls, href, text = second
    assert "btn--ghost" in cls and "btn--primary" not in cls
    assert href == "https://t.me/ordered"
    assert text == "Открыть канал"
    assert_only_allowed_scripts(body, where=" (карточка канала)")


def test_order_button_without_a_number_has_no_subline(layer, client):
    layer.channel(1, "tg", "silent", wowblogger_slug="silent",
                  url="https://t.me/silent", views_organic=None, views_ad=None, ads_30d=0)
    layer.go_live()

    actions = ACTIONS.search(client.get("/tg/silent").text).group(1)
    cls, _, text = buttons_of(actions)[0]
    assert "btn--primary" in cls
    assert text == "Заказать рекламу"
    assert "увидят" not in actions


def test_channel_without_a_slug_keeps_only_the_ghost_open_button(layer, client):
    layer.channel(1, "tg", "orphan", wowblogger_slug=None, url="https://t.me/orphan")
    layer.go_live()

    actions = ACTIONS.search(client.get("/tg/orphan").text).group(1)
    assert buttons_of(actions) == [("btn--ghost", "https://t.me/orphan", "Открыть канал")]
    assert "wowblogger.ru" not in actions


# ── соседняя площадка автора ─────────────────────────────────────────────────

def test_sibling_head_orders_with_the_same_words(layer, client):
    layer.channel(1, "tg", "main_one", wowblogger_slug="author", blogger_id=5,
                  url="https://t.me/main_one", views_ad=95_400)
    layer.channel(2, "vk", "side_one", wowblogger_slug="author", blogger_id=5,
                  url="https://vk.com/side_one", views_ad=None, views_organic=None, ads_30d=0)
    layer.sibling(1, 2)
    layer.sibling(2, 1)
    layer.go_live()

    body = client.get("/tg/main_one").text
    heads = ACTIONS.findall(body)
    assert len(heads) == 2
    own, sibling = (buttons_of(h) for h in heads)
    assert own[0][2].startswith("Заказать рекламу") and "btn--primary" in own[0][0]
    assert sibling[0][2] == "Заказать рекламу" and "btn--primary" in sibling[0][0]
    assert [t for _, _, t in sibling] == ["Заказать рекламу", "Открыть канал", "Страница канала →"]
    assert "Разместить рекламу в WOWBlogger" not in body


# ── одно слово на все выходы ─────────────────────────────────────────────────

def test_every_exit_to_wowblogger_says_order_ads(layer, client):
    layer.channel(1, "tg", "worded", subscribers=300_000, wowblogger_slug="worded",
                  url="https://t.me/worded", views_ad=95_400)
    layer.channel(2, "tg", "worded_silent", subscribers=200_000, wowblogger_slug="worded-silent",
                  url="https://t.me/worded_silent", views_ad=None, views_organic=None, ads_30d=0)
    layer.go_live()

    catalog = client.get("/").text
    assert catalog.count("Заказать рекламу") == 2
    assert "Разместить" not in catalog

    card = client.get("/tg/worded").text
    panel = INVITE_PANEL.search(card)
    assert panel is not None
    assert text_of(panel.group(1)).endswith("Заказать рекламу →")
    assert "Подробнее" not in card and "Разместить" not in card

    silent = client.get("/tg/worded_silent").text
    panel = INVITE_PANEL.search(silent)
    assert text_of(panel.group(1)) == "Реклама в этом канале Заказать рекламу →"
