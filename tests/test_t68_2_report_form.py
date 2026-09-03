"""T-68.2: форма «Сообщить о неточности» — ширина, поле подробностей, выход.

Проверяется то, что видит человек: есть ли дорога назад, доезжает ли хвост
фильтров через ошибку валидации и не уводит ли подставленный в параметр чужой
адрес на сторонний сайт. Устройство функций внутри приложения тестам, как и в
шве 3, не известно — кроме одного места: `safe_back` проверяется напрямую,
потому что её работа это перебор написаний одного и того же адреса.
"""
import re

import pytest

from app.report import safe_back
from conftest import assert_metrika_is_the_only_script

CATALOG_BACK = "/?subs_min=1000&sort=subs&page=2"


def _report_url(back: str) -> str:
    from urllib.parse import quote
    return f"/report?platform=tg&channel=example_channel&back={quote(back, safe='')}"


@pytest.fixture
def live(layer):
    layer.channel(1, "tg", "example_channel", display_name="Пример канала")
    layer.go_live()
    return layer


# ── адрес возврата: что считается своим ──────────────────────────────────
@pytest.mark.parametrize("raw", [
    "/", "/tg/example_channel", CATALOG_BACK, "/category/nauka?platform=tg",
])
def test_own_address_passes(raw):
    assert safe_back(raw) == raw


@pytest.mark.parametrize("raw", [
    None, "", "https://evil.tld", "//evil.tld", r"/\evil.tld", r"\evil.tld",
    "http:/evil.tld", "javascript:alert(1)", "/ok\nLocation: https://evil.tld",
    "/" + "a" * 600,
])
def test_foreign_or_broken_address_is_dropped(raw):
    assert safe_back(raw) is None


def test_query_tail_is_kept_whole():
    """Хвост параметров и есть смысл затеи: обрезать его по вопросительному
    знаку значит вернуть человека на голый каталог."""
    assert safe_back(CATALOG_BACK).endswith("subs_min=1000&sort=subs&page=2")


# ── форма ────────────────────────────────────────────────────────────────
def test_catalog_row_carries_current_listing_into_the_form(client, live):
    r = client.get("/?subs_min=1000")
    assert r.status_code == 200
    assert "back=/%3Fsubs_min%3D1000" in r.text


def test_cancel_returns_to_the_same_listing(client, live):
    r = client.get(_report_url(CATALOG_BACK))
    assert r.status_code == 200
    assert f'href="{CATALOG_BACK}"' in r.text.replace("&amp;", "&")


def test_cancel_falls_back_to_the_channel_page(client, live):
    """Адреса возврата нет — уходим на канал, он известен по скрытым полям."""
    r = client.get("/report?platform=tg&channel=example_channel")
    assert 'href="/tg/example_channel"' in r.text


def test_cancel_falls_back_to_catalog_for_a_general_report(client, live):
    r = client.get("/report")
    assert re.search(r'class="link-quiet" href="/"', r.text)


@pytest.mark.parametrize("evil", ["https://evil.tld/", "//evil.tld/", r"/\evil.tld"])
def test_foreign_address_never_becomes_the_way_out(client, live, evil):
    r = client.get(_report_url(evil))
    assert "evil.tld" not in r.text
    assert 'href="/tg/example_channel"' in r.text


def test_tail_survives_a_rejected_submit(client, live):
    """Введённое не теряется (T-67), и адрес возврата вместе с ним: после POST
    в адресной строке его нет, он живёт скрытым полем."""
    r = client.post("/report", data={
        "platform": "tg", "username_lower": "example_channel",
        "kind": "Другое", "details": "   ", "email": "keep@me.example",
        "back": CATALOG_BACK,
    })
    assert r.status_code == 422
    text = r.text.replace("&amp;", "&")
    assert "keep@me.example" in text
    assert f'value="{CATALOG_BACK}"' in text
    assert f'href="{CATALOG_BACK}"' in text


def test_field_error_is_not_a_grey_caption(client, live):
    r = client.post("/report", data={"kind": "Другое", "details": ""})
    assert r.status_code == 422
    assert 'class="field-error"' in r.text


def test_details_field_is_multiline(client, live):
    r = client.get("/report")
    assert re.search(r'<textarea[^>]*rows="6"', r.text)


def test_form_stands_in_its_own_column(client, live):
    r = client.get("/report")
    assert "form-narrow" in r.text


# ── страница «спасибо» ───────────────────────────────────────────────────
def test_thanks_offers_the_way_back_to_the_channel_and_the_listing(client, live):
    r = client.post("/report", data={
        "platform": "tg", "username_lower": "example_channel",
        "kind": "Другое", "details": "Замечание", "back": CATALOG_BACK,
    }, follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"].startswith("/report/thanks?")

    thanks = client.get(r.headers["location"])
    text = thanks.text.replace("&amp;", "&")
    assert 'href="/tg/example_channel"' in text
    assert f'href="{CATALOG_BACK}"' in text
    assert 'href="/"' in text
    assert "form-narrow" in text


def test_thanks_ignores_a_channel_that_is_not_in_the_dump(client, live):
    r = client.get("/report/thanks?platform=tg&channel=nosuchchannel")
    assert r.status_code == 200
    assert "nosuchchannel" not in r.text


def test_thanks_ignores_a_foreign_address(client, live):
    r = client.get("/report/thanks?platform=tg&channel=example_channel&back=https%3A%2F%2Fevil.tld")
    assert "evil.tld" not in r.text


def test_thanks_does_not_repeat_one_road_twice(client, live):
    """Возврат на канал и «к выдаче» в одно место — три ссылки в одну точку
    читаются как ошибка, а не как выбор."""
    r = client.get("/report/thanks?platform=tg&channel=example_channel"
                   "&back=%2Ftg%2Fexample_channel")
    assert r.text.count('href="/tg/example_channel"') == 1


def test_thanks_page_refresh_still_writes_nothing(client, live, dsn):
    import psycopg2
    client.post("/report", data={"platform": "tg", "username_lower": "example_channel",
                                 "kind": "Другое", "details": "Раз", "back": CATALOG_BACK})
    client.get("/report/thanks?platform=tg&channel=example_channel")
    client.get("/report/thanks?platform=tg&channel=example_channel")
    conn = psycopg2.connect(dsn)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM public.data_report")
            assert cur.fetchone()[0] == 1
    finally:
        conn.close()


# ── общие места не поехали ───────────────────────────────────────────────
def test_catalog_filter_column_is_untouched(client, live):
    """Правка вида формы не должна тащить за собой колонку фильтров: поля там
    те же самые, `.field` общий."""
    r = client.get("/")
    assert "report-form" not in r.text
    assert "<textarea" not in r.text


def test_no_script_but_metrika_in_the_answer(client, live):
    for url in ("/report", "/report/thanks?platform=tg&channel=example_channel"):
        assert_metrika_is_the_only_script(client.get(url).text, url)
