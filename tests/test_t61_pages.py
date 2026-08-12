"""T-61, шов 3: что сервис отдаёт по HTTP.

Список проверок — из спеки (`docs/showcase-spec-live-site.md`, «Шов 3»). Каждый
тест сеет публичный слой руками и смотрит на ответ: код, тело, заголовки. Про
устройство приложения тесты не знают ничего.
"""
from datetime import date, timedelta

import pytest

pytestmark = pytest.mark.integration


# ── страница канала ──────────────────────────────────────────────────────────

def test_channel_page_shows_metrics_posts_and_advertisers(layer, client):
    cid = layer.channel(1, "tg", "example_channel", subscribers=120_000,
                        views_organic=22_200, coverage_ratio=18.5, er_percent=4.2)
    layer.post(cid, "p1", text="Обычная публикация про котиков")
    layer.post(cid, "p2", text="Рекламная публикация", is_ad=True)
    layer.advertiser(cid, "ООО «Ромашка»", inn="7701234567", ogrn="1027700000001")
    layer.go_live()

    r = client.get("/tg/example_channel")
    assert r.status_code == 200
    body = r.text
    assert "120 000" in body.replace(" ", " ").replace("\xa0", " ")
    assert "22 200" in body.replace(" ", " ").replace("\xa0", " ")
    assert "4,2" in body or "4.2" in body
    assert "про котиков" in body
    assert "ООО «Ромашка»" in body
    assert "7701234567" in body


def test_unknown_channel_is_404(layer, client):
    layer.channel(1, "tg", "example_channel")
    layer.go_live()

    assert client.get("/tg/no_such_channel").status_code == 404
    assert client.get("/tg").status_code == 200          # раздел площадки есть
    assert client.get("/xx/example_channel").status_code == 404


def test_username_case_does_not_matter(layer, client):
    layer.channel(1, "tg", "Example_Channel")
    layer.go_live()

    assert client.get("/tg/example_channel").status_code == 200
    assert client.get("/tg/Example_Channel").status_code == 200


def test_empty_feed_says_so_and_is_not_an_error(layer, client):
    cid = layer.channel(1, "tg", "silent_one", posts_30d=0, ads_30d=0,
                        ad_share_30d=None, views_organic=None, views_ad=None)
    layer.go_live()

    r = client.get("/tg/silent_one")
    assert r.status_code == 200
    assert "постов нет" in r.text.lower()


def test_channel_without_history_has_no_chart(layer, client):
    layer.channel(1, "tg", "no_history")
    layer.channel(2, "tg", "with_history")
    layer.history(2, [(date.today() - timedelta(days=14 * i), 100_000 + 1_000 * i)
                      for i in range(7)])
    layer.go_live()

    plain = client.get("/tg/no_history").text
    charted = client.get("/tg/with_history").text
    assert "<svg" not in plain
    assert "Динамика подписчиков" not in plain
    assert "<svg" in charted
    assert "Динамика подписчиков" in charted


def test_individual_advertiser_shows_requisites_without_a_name(layer, client):
    cid = layer.channel(1, "tg", "example_channel")
    layer.advertiser(cid, "ИП, ИНН 500100732259", entity_type="fl",
                     inn="500100732259", ogrn="304500116000157")
    layer.go_live()

    body = client.get("/tg/example_channel").text
    assert "500100732259" in body
    assert "ИП" in body


def test_siblings_link_to_their_own_pages(layer, client):
    layer.channel(1, "tg", "main_channel", blogger_id=77, blogger_has_siblings=True)
    layer.channel(2, "vk", "same_author", blogger_id=77, blogger_has_siblings=True)
    layer.sibling(1, 2)
    layer.sibling(2, 1)
    layer.go_live()

    body = client.get("/tg/main_channel").text
    assert "/vk/same_author" in body


# ── каталог, разделы, пагинация ──────────────────────────────────────────────

def test_catalog_lists_channels_and_paginates_by_fifty(layer, client):
    for i in range(1, 61):
        layer.channel(i, "tg", f"chan{i:03d}", subscribers=100_000 - i)
    layer.go_live()

    first = client.get("/")
    assert first.status_code == 200
    assert first.text.count("/tg/chan") >= 50
    assert "chan001" in first.text
    assert "chan060" not in first.text

    second = client.get("/?page=2")
    assert second.status_code == 200
    assert "chan060" in second.text


def test_platform_and_category_sections(layer, client):
    layer.channel(1, "tg", "tg_one")
    layer.channel(2, "vk", "vk_one")
    layer.category(2, "Автомобили", "автомобили")
    layer.go_live()

    tg = client.get("/tg")
    assert tg.status_code == 200
    assert "tg_one" in tg.text and "vk_one" not in tg.text

    cat = client.get("/category/автомобили")
    assert cat.status_code == 200
    assert "vk_one" in cat.text and "tg_one" not in cat.text

    assert client.get("/category/нет-такой").status_code == 404


# ── краулер ──────────────────────────────────────────────────────────────────

def test_noindex_on_every_response_while_the_switch_is_on(layer, client):
    layer.channel(1, "tg", "example_channel")
    layer.go_live()

    for path in ("/", "/tg", "/tg/example_channel", "/sitemap.xml"):
        r = client.get(path)
        assert "noindex" in r.headers.get("x-robots-tag", ""), path

    robots = client.get("/robots.txt")
    assert robots.status_code == 200
    assert "Disallow: /" in robots.text


def test_switch_off_opens_indexing_but_keeps_deep_pages_closed(layer, make_client):
    for i in range(1, 61):
        layer.channel(i, "tg", f"chan{i:03d}")
    layer.go_live()
    client = make_client(noindex=False)

    assert "noindex" not in client.get("/tg/chan001").headers.get("x-robots-tag", "")
    assert "noindex" not in client.get("/").headers.get("x-robots-tag", "")

    second = client.get("/?page=2")
    assert "noindex, follow" in second.headers.get("x-robots-tag", "")

    robots = client.get("/robots.txt")
    assert "Disallow: /" not in robots.text
    assert "Sitemap:" in robots.text


def test_sitemap_lists_published_channels_only(layer, client):
    layer.channel(1, "tg", "published_one")
    layer.go_live()

    index = client.get("/sitemap.xml")
    assert index.status_code == 200
    assert "sitemapindex" in index.text

    chunk = client.get("/sitemap-1.xml")
    assert chunk.status_code == 200
    assert "/tg/published_one" in chunk.text
    assert "no_such_channel" not in chunk.text
    assert client.get("/sitemap-99.xml").status_code == 404


def test_pages_carry_no_client_side_javascript(layer, client):
    cid = layer.channel(1, "tg", "example_channel")
    layer.post(cid, "p1")
    layer.history(cid, [(date.today() - timedelta(days=14 * i), 100_000 + i)
                        for i in range(7)])
    layer.go_live()

    for path in ("/", "/tg", "/tg/example_channel"):
        body = client.get(path).text
        assert "<script" not in body.lower(), path
        assert "onclick" not in body.lower(), path


# ── ротация и свежесть ───────────────────────────────────────────────────────

def test_service_follows_the_pointer_after_rotation(layer, client, dsn):
    layer.channel(1, "tg", "yesterday_only")
    layer.go_live()
    assert client.get("/tg/yesterday_only").status_code == 200

    from tests.conftest import Layer
    tomorrow = Layer(dsn, "dump_t61_test_2")
    tomorrow.channel(1, "tg", "today_only")
    tomorrow.go_live()

    assert client.get("/tg/today_only").status_code == 200
    assert client.get("/tg/yesterday_only").status_code == 404


def test_page_shows_when_the_data_was_updated(layer, client):
    layer.channel(1, "tg", "example_channel")
    layer.go_live()

    body = client.get("/tg/example_channel").text
    assert "Данные обновлены" in body
