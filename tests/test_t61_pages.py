"""T-61, шов 3: что сервис отдаёт по HTTP.

Список проверок — из спеки (`docs/showcase-spec-live-site.md`, «Шов 3»). Каждый
тест сеет публичный слой руками и смотрит на ответ: код, тело, заголовки. Про
устройство приложения тесты не знают ничего.
"""
from datetime import date, timedelta

import psycopg2
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


def test_address_in_upper_case_redirects_to_the_only_one(layer, client):
    """У канала ровно один адрес: два живых адреса это страницы-клоны (US19)."""
    layer.channel(1, "tg", "Example_Channel")
    layer.go_live()

    upper = client.get("/tg/Example_Channel", follow_redirects=False)
    assert upper.status_code == 301
    assert upper.headers["location"] == "/tg/example_channel"

    page = client.get("/tg/example_channel")
    assert page.status_code == 200
    assert 'href="https://fomobase.ru/tg/example_channel"' in page.text

    # Ни каталог, ни карта сайта исходный регистр не печатают.
    assert "/tg/example_channel" in client.get("/").text
    assert "/tg/Example_Channel" not in client.get("/").text
    assert "/tg/Example_Channel" not in client.get("/sitemap-1.xml").text


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
    """У ИП наименование в реестре и есть ФИО, поэтому на странице реквизиты.

    Защита структурная: в публичном слое нет колонок с именами, и положить туда
    ФИО тесту просто некуда — что здесь и проверяется. Утечка возможна только
    через сборщик (T-60), а не через шаблон.
    """
    cid = layer.channel(1, "tg", "example_channel")
    layer.advertiser(cid, "ИП, ИНН 500100732259", entity_type="fl",
                     inn="500100732259", ogrn="304500116000157")
    layer.go_live()

    assert [c for c in layer.columns("channel_advertiser") if "name" in c] == []
    with pytest.raises(psycopg2.errors.UndefinedColumn):
        layer.advertiser(cid, "ООО «Ромашка»", rank=2, name_short="Иванов Иван Иванович")

    body = client.get("/tg/example_channel").text
    assert "500100732259" in body
    assert "ИП" in body
    assert "Иванов" not in body


def test_wowblogger_button_appears_only_with_a_slug(layer, client):
    """US41: со страницы канала уходят на размещение в WOWBlogger.

    Адрес не сочиняется на месте: слаг карточки автора приезжает колонкой слоя,
    и без него кнопки нет вовсе.
    """
    layer.channel(1, "tg", "listed_one", wowblogger_slug="vykhino-zhulebino-2")
    layer.channel(2, "tg", "stranger_one")
    layer.go_live()

    listed = client.get("/tg/listed_one").text
    assert "https://wowblogger.ru/bloggers/vykhino-zhulebino-2" in listed
    assert "WOWBlogger" in listed

    assert "wowblogger.ru" not in client.get("/tg/stranger_one").text


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


def test_page_beyond_the_last_one_is_404(layer, client):
    """Страница за последней — такой же несуществующий адрес, как чужой канал."""
    for i in range(1, 61):
        layer.channel(i, "tg", f"chan{i:03d}")
    layer.category(1, "Автомобили", "автомобили")
    layer.go_live()

    assert client.get("/?page=2").status_code == 200
    assert client.get("/?page=3").status_code == 404
    assert client.get("/tg?page=3").status_code == 404
    assert client.get("/category/автомобили?page=2").status_code == 404
    # «²» и «１» — цифры по мнению str.isdigit(), и без проверки на ASCII
    # первая уронила бы ответ в 500, а вторая завела бы странице второй адрес.
    for bad in ("?page=0", "?page=-1", "?page=abc", "?page=", "?page=²", "?page=１"):
        assert client.get("/" + bad).status_code == 404, bad


def test_catalog_shows_when_the_last_post_was(layer, client):
    layer.channel(1, "tg", "example_channel",
                  last_post_at=date(2026, 8, 9))
    layer.go_live()

    for path in ("/", "/tg/example_channel"):
        assert "9 августа 2026" in client.get(path).text, path


def test_platform_and_category_sections(layer, client):
    layer.channel(1, "tg", "tg_one")
    layer.channel(2, "vk", "vk_one")
    layer.category(2, "Автомобили", "автомобили")
    layer.go_live()

    tg = client.get("/tg")
    assert tg.status_code == 200
    assert "tg_one" in tg.text and "vk_one" not in tg.text
    # Раздел, в котором стоит посетитель, подсвечен в нав-панели именно свой.
    assert '<a class="sec on" href="/tg">' in tg.text
    assert '<a class="sec on" href="/">' in client.get("/").text

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
    # Проверяется отсутствие запрета на весь сайт, а не отсутствие запретов
    # вообще: с T-65 в файле есть построчные `Disallow` на ключи фильтров, и
    # подстрока «Disallow: /» теперь встречается законно.
    assert "Disallow: /\n" not in robots.text
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

    # Мусор в номере — тоже страница 404, а не JSON валидатора с кодом 422.
    for bad in ("/sitemap-99.xml", "/sitemap-abc.xml", "/sitemap-0.xml", "/sitemap-².xml"):
        answer = client.get(bad)
        assert answer.status_code == 404, bad
        assert "text/html" in answer.headers["content-type"], bad


def test_only_the_stylesheet_side_of_the_design_system_is_public(layer, client):
    """Наружу едет вид страницы, а не витрина компонентов рядом с ним."""
    layer.channel(1, "tg", "example_channel")
    layer.go_live()

    for path in ("/assets/index.css", "/assets/tokens.css", "/assets/components.css",
                 "/assets/fonts/fonts.css", "/assets/fonts/onest-cyrillic.woff2"):
        assert client.get(path).status_code == 200, path

    for path in ("/assets/specimen.html", "/assets/preview.css", "/assets/README.md",
                 "/assets/components/channel-header.html"):
        assert client.get(path).status_code == 404, path


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
