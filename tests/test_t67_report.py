"""T-67: форма «Сообщить о неточности» — запись обращения, без прод-базы.

Пишет в `public.data_report` той же тестовой БД, что и шов 3 (`SHOWCASE_TEST_DSN`,
только localhost — гвард в conftest). Таблица не пересоздаётся вместе со схемой
дампа, `conftest._reset` чистит её строки перед каждым тестом.
"""
import psycopg2
import psycopg2.extras
import pytest

from app.report import HONEYPOT_FIELD, MAX_DETAILS

pytestmark = pytest.mark.integration


def _rows(dsn):
    conn = psycopg2.connect(dsn, cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM public.data_report ORDER BY id")
            return cur.fetchall()
    finally:
        conn.close()


def test_report_with_channel_is_saved_and_shows_thanks(layer, client, dsn):
    layer.channel(1, "tg", "example_channel", display_name="Пример канала")
    layer.go_live()

    r = client.post("/report", data={
        "platform": "tg", "username_lower": "example_channel",
        "kind": "Неверное число подписчиков", "details": "Подписчиков на самом деле 50 000",
        "email": "po@example.com",
    })
    assert r.status_code == 200
    assert r.url.path == "/report/thanks"

    rows = _rows(dsn)
    assert len(rows) == 1
    assert rows[0]["platform"] == "tg"
    assert rows[0]["username_lower"] == "example_channel"
    assert rows[0]["display_name"] == "Пример канала"
    assert rows[0]["kind"] == "Неверное число подписчиков"
    assert "50 000" in rows[0]["details"]
    assert rows[0]["email"] == "po@example.com"
    assert rows[0]["sent_at"] is None
    assert rows[0]["send_attempts"] == 0


def test_general_report_without_channel_is_accepted(client, dsn):
    r = client.post("/report", data={
        "kind": "Другое", "details": "Общее замечание по каталогу",
    })
    assert r.status_code == 200

    rows = _rows(dsn)
    assert len(rows) == 1
    assert rows[0]["platform"] is None
    assert rows[0]["username_lower"] is None


def test_prg_redirect_then_refresh_does_not_duplicate(client, dsn):
    r = client.post("/report", data={"kind": "Другое", "details": "Раз"},
                    follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/report/thanks"

    # Повторный GET страницы «спасибо» ничего не пишет — это и есть PRG.
    client.get("/report/thanks")
    client.get("/report/thanks")
    assert len(_rows(dsn)) == 1


def test_honeypot_filled_shows_thanks_but_writes_nothing(client, dsn):
    r = client.post("/report", data={
        "kind": "Другое", "details": "Пишет бот",
        HONEYPOT_FIELD: "я бот",
    })
    assert r.status_code == 200
    assert _rows(dsn) == []


def test_empty_details_is_rejected_and_input_is_kept(client, dsn):
    r = client.post("/report", data={
        "kind": "Другое", "details": "   ", "email": "keep@me.example",
    })
    assert r.status_code == 422
    assert "keep@me.example" in r.text
    assert _rows(dsn) == []


def test_bad_email_is_rejected(client, dsn):
    r = client.post("/report", data={
        "kind": "Другое", "details": "Есть что сказать", "email": "not-an-email",
    })
    assert r.status_code == 422
    assert _rows(dsn) == []


def test_details_over_limit_are_truncated_on_save(client, dsn):
    long_text = "а" * 20_000
    r = client.post("/report", data={"kind": "Другое", "details": long_text})
    assert r.status_code == 200

    rows = _rows(dsn)
    assert len(rows) == 1
    assert len(rows[0]["details"]) == MAX_DETAILS


def test_report_is_not_in_sitemap(layer, client):
    layer.channel(1, "tg", "example_channel")
    layer.go_live()

    for chunk in ("/sitemap.xml", "/sitemap-1.xml"):
        body = client.get(chunk).text
        assert "/report" not in body


def test_report_form_prefilled_from_query_and_shows_channel_name(layer, client):
    layer.channel(1, "tg", "example_channel", display_name="Пример канала")
    layer.go_live()

    r = client.get("/report", params={"platform": "tg", "channel": "Example_Channel"})
    assert r.status_code == 200
    assert "Пример канала" in r.text
    assert 'value="tg"' in r.text
    assert 'value="example_channel"' in r.text


def test_report_pages_are_closed_to_indexing(layer, client, make_client):
    layer.channel(1, "tg", "example_channel")
    layer.go_live()

    closed_client = client
    assert "noindex" in closed_client.get("/report").headers.get("x-robots-tag", "")

    open_client = make_client(noindex=False)
    r = open_client.get("/report")
    assert "noindex" in r.headers.get("x-robots-tag", "")
    thanks = open_client.get("/report/thanks")
    assert "noindex" in thanks.headers.get("x-robots-tag", "")

    robots = open_client.get("/robots.txt").text
    assert "Disallow: /report\n" in robots
    assert "Disallow: /report/thanks\n" in robots
