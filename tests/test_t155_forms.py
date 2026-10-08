"""T-155: «Неточность?», «Сообщить» и «Ещё» — кнопки GET-форм, а не ссылки.

Google ходил по ссылкам `/report?…` и `?posts=N`, упирался в `Disallow` и
копил отчёт «Заблокировано в robots.txt» (710 адресов на 08.10). Формы он не
отправляет, а человек получает тот же адрес: браузер собирает строку запроса
из скрытых полей, якорь из `action` при GET-отправке остаётся на месте.

Тесты смотрят на то, что отдаёт сервер: ссылок нет, формы есть, и их поля,
раскодированные, совпадают с параметрами прежних ссылок.
"""
import re
from urllib.parse import urlencode

import pytest

from conftest import assert_only_allowed_scripts, forms

pytestmark = pytest.mark.integration

REPORT_HREF = re.compile(r'href="/report')
POSTS_HREF = re.compile(r'href="[^"]*posts=')


def seed(layer):
    """Шестьдесят каналов tg в «Спорте» и Казани, у первого лента на три
    страницы и сосед во вконтакте."""
    layer.city("kazan", "Казань", "Казани")
    for i in range(1, 61):
        family = dict(blogger_id=7, blogger_has_siblings=True) if i == 1 else {}
        layer.channel(i, "tg", f"ch{i}", subscribers=200_000 - i * 1000,
                      city="Казань", city_slug="kazan", is_local=True, **family)
        layer.category(i, "Спорт", "sport")
    layer.channel(100, "vk", "ch1_vk", blogger_id=7, blogger_has_siblings=True)
    for i in range(25):
        layer.post(1, f"p{i}", text=f"Публикация номер {i}", days_ago=i)
        layer.post(100, f"v{i}", text=f"Пост во вконтакте {i}", days_ago=i)
    layer.section("tg", "sport", name="Спорт", channels=60)
    layer.city_section("tg", "kazan", channels=60)
    layer.go_live()


LISTINGS = (
    "/", "/?page=2", "/?subs_min=1000",
    "/tg", "/tg?subs_min=1000&sort=subs",
    "/category/sport", "/category/sport?subs_min=1000",
    "/category/sport/tg",
    "/city/kazan", "/city/kazan/tg",
)
CARDS = ("/tg/ch1", "/tg/ch1?posts=2", "/tg/ch1?posts=3", "/vk/ch1_vk", "/tg/ch2")


def report_forms(body):
    return forms(body, "/report")


def more_forms(body):
    return [f for f in forms(body) if "posts" in f["fields"]]


# ── ссылок, по которым Google упирается в robots, на страницах нет ───────────

def test_pages_google_reads_have_no_href_to_report_or_posts(layer, client):
    seed(layer)
    for path in LISTINGS + CARDS:
        r = client.get(path)
        assert r.status_code == 200, path
        assert not REPORT_HREF.findall(r.text), f"{path}: осталась ссылка на /report"
        assert not POSTS_HREF.findall(r.text), f"{path}: осталась ссылка с posts="


# ── «Неточность?» в каталоге ─────────────────────────────────────────────────

def test_every_catalog_row_has_a_report_form_with_the_old_link_parameters(layer, client):
    seed(layer)
    path = "/category/sport?subs_min=1000"
    body = client.get(path).text
    found = report_forms(body)
    assert len(found) == body.count('<div class="row-actions">') > 0
    for f in found:
        assert f["attrs"].get("method") == "get"
        assert set(f["fields"]) == {"platform", "channel", "back"}
        assert f["fields"]["platform"] == "tg"
        assert re.fullmatch(r"ch\d+", f["fields"]["channel"])
        assert f["fields"]["back"] == path, "в back ушёл не сырой адрес выдачи"
        [button] = f["buttons"]
        assert "report-link" in button["attrs"].get("class", "")
        assert button["text"] == "Неточность?"


def test_bare_root_sends_back_to_the_root(layer, client):
    seed(layer)
    [f, *_] = report_forms(client.get("/").text)
    assert f["fields"]["back"] == "/"


# ── «Сообщить» на карточке ───────────────────────────────────────────────────

def test_card_report_form_carries_the_channel_and_the_feed_page(layer, client):
    seed(layer)
    [f] = report_forms(client.get("/tg/ch1?posts=3").text)
    assert f["attrs"].get("method") == "get"
    assert f["fields"] == {"platform": "tg", "channel": "ch1", "back": "/tg/ch1?posts=3#post-21"}
    [button] = f["buttons"]
    assert button["text"] == "Сообщить"
    assert button["attrs"].get("class") == "btn btn--ghost"


def test_buttons_have_no_name_so_nothing_extra_goes_into_the_address(layer, client):
    seed(layer)
    for path in ("/category/sport", "/tg/ch1"):
        for f in forms(client.get(path).text):
            if f["attrs"].get("action", "").startswith(("/report", "/tg/ch1")):
                for b in f["buttons"]:
                    assert "name" not in b["attrs"], (path, b)
                    assert b["attrs"].get("type") == "submit", (path, b)


def test_submitting_the_form_opens_the_report_for_that_channel(layer, client):
    """Браузер собирает адрес из полей сам: `/` кодируется в `%2F`, пробел в
    `+`. Сервер получает то же значение, что из прежней ссылки."""
    from app.report import safe_back

    seed(layer)
    for path in ("/category/sport?subs_min=1000", "/tg/ch1?posts=2"):
        f = report_forms(client.get(path).text)[0]
        r = client.get("/report?" + urlencode(f["fields"]))
        assert r.status_code == 200, path
        assert f["fields"]["channel"] in r.text
        assert safe_back(f["fields"]["back"]) == f["fields"]["back"], path
        assert f'href="{f["fields"]["back"]}"' in r.text.replace("&amp;", "&"), (
            "«Отмена» ведёт не туда, откуда пришли")


# ── «Ещё» в ленте ────────────────────────────────────────────────────────────

def test_more_is_a_form_with_the_next_page_and_the_anchor_on_the_new_post(layer, client):
    seed(layer)
    [f] = more_forms(client.get("/tg/ch1").text)
    assert f["attrs"].get("method") == "get"
    assert f["attrs"].get("action") == "/tg/ch1#post-11"
    assert f["fields"] == {"posts": "2"}
    [button] = f["buttons"]
    assert button["text"] == "Ещё"
    assert button["attrs"].get("class") == "btn btn--ghost more"

    [f2] = more_forms(client.get("/tg/ch1?posts=2").text)
    assert f2["attrs"]["action"] == "/tg/ch1#post-21"
    assert f2["fields"] == {"posts": "3"}


def test_last_feed_page_has_no_more_form(layer, client):
    seed(layer)
    assert more_forms(client.get("/tg/ch1?posts=3").text) == []


def test_the_more_form_lands_on_the_next_feed_page(layer, client):
    seed(layer)
    f = more_forms(client.get("/tg/ch1").text)[0]
    r = client.get(f["attrs"]["action"].split("#")[0] + "?" + urlencode(f["fields"]))
    assert r.status_code == 200
    assert r.text.count("Публикация номер") == 20


# ── без JS ───────────────────────────────────────────────────────────────────

def test_no_new_scripts(layer, client):
    seed(layer)
    for path in ("/category/sport", "/tg/ch1"):
        assert_only_allowed_scripts(client.get(path).text, path)


def test_the_form_wrapper_has_no_box_of_its_own(client):
    """Кнопка встаёт в раскладку там же, где стояла ссылка: обёртка формы
    своей коробки не даёт, иначе «Сообщить» перестала бы тянуться на всю
    колонку. «Неточность?» снимает стили кнопки целиком."""
    css = client.get("/assets/components.css").text
    assert re.search(r"\.form-link\s*\{\s*display:\s*contents;", css)
    rule = re.search(r"\.report-link\s*\{([^}]*)\}", css).group(1)
    for decl in ("font: inherit", "background: none", "border: 0", "padding: 0", "cursor: pointer"):
        assert decl in rule, decl
    assert rule.index("font: inherit") < rule.index("font-size"), "font: inherit перебьёт размер"
