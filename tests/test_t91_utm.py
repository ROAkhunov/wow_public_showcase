"""T-91: исходящие ссылки в WOWBlogger уходят с UTM-метками.

Метки нужны на стороне WOWBlogger: браузер шлёт с витрины только origin, без
пути, и без меток в отчётах видно «пришли с fomobase.ru», но не с какого
блогера. Отсюда `utm_content` числовым `blogger_id` и `utm_term` местом клика.

Проверяется разобранный адрес, а не подстрока сырого HTML: в разметке `&`
живёт как `&amp;`, и подстрочная проверка ловила бы экранирование, а не метки.
"""
import re
from urllib.parse import parse_qs, urlparse

import pytest

from app.links import WOW_BASE, wow_url

SLUG = "vykhino-zhulebino-2"


def hrefs_to_wow(body: str) -> list[str]:
    """Все адреса на WOWBlogger со страницы, со снятым экранированием."""
    body = body.replace("&amp;", "&")
    return re.findall(r'href="(https://wowblogger\.ru[^"]*)"', body)


def marks(url: str) -> dict:
    return {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}


# ── сама функция ─────────────────────────────────────────────────────────────

def test_all_five_marks_in_the_order_maxim_asked_for():
    url = wow_url(SLUG, "list", 4211)
    assert url == (f"{WOW_BASE}/bloggers/{SLUG}"
                   "?utm_source=fomobase&utm_medium=referral&utm_campaign=catalog"
                   "&utm_content=4211&utm_term=list")


def test_slug_with_special_characters_is_escaped_in_the_path():
    """Слаг едет сегментом пути: `@` и косая черта не должны в нём выжить.

    На проде слагов с косой чертой нет ни одного, с `@` — два. Экранируем без
    исключений: слаг приезжает из чужой базы, а не из нашего кода.
    """
    url = wow_url("a/b@wowblogger.ru", "card", 7)
    assert "/bloggers/a%2Fb%40wowblogger.ru?" in url
    assert marks(url)["utm_term"] == "card"


def test_no_slug_no_link():
    assert wow_url(None, "list", 7) == ""
    assert wow_url("", "list", 7) == ""


def test_empty_blogger_id_drops_the_mark_instead_of_writing_none():
    """`utm_content=None` в отчёте Метрики хуже, чем отсутствие метки.

    На проде строк «слаг есть, а `blogger_id` пуст» ноль, так что ветка
    страхует будущий дамп, а не сегодняшний.
    """
    got = marks(wow_url(SLUG, "list", None))
    assert "utm_content" not in got
    assert set(got) == {"utm_source", "utm_medium", "utm_campaign", "utm_term"}


# ── страницы ─────────────────────────────────────────────────────────────────

@pytest.mark.integration
def test_catalog_button_carries_list(layer, client):
    layer.channel(1, "tg", "listed_one", blogger_id=4211, wowblogger_slug=SLUG)
    layer.go_live()

    links = hrefs_to_wow(client.get("/").text)
    assert len(links) == 1
    assert urlparse(links[0]).path == f"/bloggers/{SLUG}"
    assert marks(links[0]) == {"utm_source": "fomobase", "utm_medium": "referral",
                               "utm_campaign": "catalog", "utm_content": "4211",
                               "utm_term": "list"}


@pytest.mark.integration
def test_every_link_on_the_channel_page_carries_card(layer, client):
    """Кнопок на странице канала две: правая колонка и блок соседней площадки.

    Блогер у них один, поэтому `utm_content` совпадает — в отчёте эти переходы
    неразличимы, и это свойство данных, а не недосмотр меток.
    """
    layer.channel(1, "tg", "main_channel", blogger_id=4211,
                  blogger_has_siblings=True, wowblogger_slug=SLUG)
    layer.channel(2, "vk", "vk_page", blogger_id=4211,
                  blogger_has_siblings=True, wowblogger_slug="sosed-slug")
    layer.sibling(1, 2)
    layer.sibling(2, 1)
    layer.go_live()

    links = hrefs_to_wow(client.get("/tg/main_channel").text)
    assert links, "на странице канала должна быть хотя бы одна ссылка в WOW"
    for url in links:
        assert marks(url)["utm_term"] == "card", url
        assert marks(url)["utm_content"] == "4211", url
    assert {urlparse(u).path for u in links} == {f"/bloggers/{SLUG}", "/bloggers/sosed-slug"}


@pytest.mark.integration
def test_same_blogger_same_content_mark_from_list_and_from_card(layer, client):
    """DoD глазами PO: `utm_content` один и тот же, `utm_term` разный."""
    layer.channel(1, "tg", "listed_one", blogger_id=4211, wowblogger_slug=SLUG)
    layer.go_live()

    from_list = marks(hrefs_to_wow(client.get("/").text)[0])
    from_card = marks(hrefs_to_wow(client.get("/tg/listed_one").text)[0])
    assert from_list["utm_content"] == from_card["utm_content"] == "4211"
    assert (from_list["utm_term"], from_card["utm_term"]) == ("list", "card")


@pytest.mark.integration
def test_channel_without_a_slug_still_has_no_button(layer, client):
    layer.channel(1, "tg", "stranger_one", blogger_id=4211)
    layer.go_live()
    assert hrefs_to_wow(client.get("/tg/stranger_one").text) == []
    assert hrefs_to_wow(client.get("/").text) == []
