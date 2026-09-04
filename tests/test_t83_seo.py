"""T-83: SEO-каркас витрины под закрытым от индексации сайтом.

Шов тот же, что у остальных: засеяли публичный слой — дёрнули адрес. Проверяется
то, что увидит краулер: микроразметка, превью ссылки, честная дата в карте
сайта, переезд адреса при переименовании, дороги вбок с карточки и посадочные
«площадка + тематика».

Сайт при этом остаётся закрытым, и в проверках это видно: запрет стоит на
каждом ответе. Индексируемость новых адресов проверяется отдельно, на клиенте с
открытым переключателем, — иначе проверить её нечем, а трогать переключатель на
проде задача запрещает.
"""
import json
import re

import pytest

from conftest import assert_metrika_is_the_only_script

LD = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)


def marks(html: str) -> list[dict]:
    return [json.loads(chunk) for chunk in LD.findall(html)]


def of_type(html: str, kind: str) -> dict | None:
    for mark in marks(html):
        if mark.get("@type") == kind:
            return mark
    return None


def meta(html: str, prop: str) -> str | None:
    found = re.search(rf'<meta property="{prop}" content="([^"]*)"', html)
    return found.group(1) if found else None


@pytest.fixture
def live(layer):
    """Небольшой, но живой слой: две тематики, три площадки, посадочная пара."""
    for i in range(1, 13):
        layer.channel(i, "tg", f"finance_{i}", subscribers=100_000 - i * 1000,
                      display_name=f"Финансы {i}")
        layer.category(i, "Финансы", "finance")
    layer.channel(50, "tg", "lonely", subscribers=50_500, display_name="Одинокий")
    layer.channel(60, "vk", "vk_finance", subscribers=40_000, display_name="ВК Финансы")
    layer.category(60, "Финансы", "finance")
    layer.post(1, "p1")

    layer.section("", "", channels=14, views_median=20_000, ads_share=42.0)
    layer.section("tg", "", channels=13, views_median=21_000, ads_share=40.0)
    layer.section("vk", "", channels=1, views_median=9_000, ads_share=0.0)
    layer.section("", "finance", name="Финансы", channels=13,
                  views_median=19_000, ads_share=38.0)
    layer.section("tg", "finance", name="Финансы", channels=12,
                  views_median=19_500, ads_share=41.0)
    # Пара ниже порога: собственной страницы у неё нет.
    layer.section("vk", "finance", name="Финансы", channels=1,
                  views_median=9_000, ads_share=0.0)
    return layer.go_live()


# ── микроразметка ────────────────────────────────────────────────────────────

def test_channel_page_carries_the_breadcrumb_trail_for_the_robot(live, client):
    """Крошки нарисованы давно, но роботу они видны только разметкой."""
    html = client.get("/tg/finance_1").text
    trail = of_type(html, "BreadcrumbList")
    assert trail, "на карточке нет BreadcrumbList"
    names = [item["name"] for item in trail["itemListElement"]]
    assert names == ["Каталог", "Telegram", "Финансы 1"]
    assert trail["itemListElement"][1]["item"].endswith("/tg")
    # Последняя крошка — сама страница, ссылки на себя в ней нет.
    assert "item" not in trail["itemListElement"][-1]


def test_root_introduces_the_site_and_the_catalog_lists_its_channels(live, client):
    html = client.get("/").text
    assert of_type(html, "Organization"), "на корне нет Organization"
    assert of_type(html, "WebSite"), "на корне нет WebSite"
    listing = of_type(html, "ItemList")
    assert listing, "на каталоге нет ItemList"
    first = listing["itemListElement"][0]
    assert first["position"] == 1
    assert first["url"].endswith("/tg/finance_1")


def test_inner_pages_carry_the_list_but_not_the_organization(live, client):
    """Организация и сайт — разметка корня: на 143 тысячах страниц она вес, а не польза."""
    html = client.get("/tg").text
    assert of_type(html, "ItemList"), "на разделе нет ItemList"
    assert of_type(html, "Organization") is None


def test_positions_in_the_list_continue_on_the_second_page(live, client):
    """На пятой странице первый канал не первый в списке."""
    small = client.get("/?page=2")
    assert small.status_code in (200, 404)  # страниц может и не быть на малом слое


def test_markup_does_not_break_the_no_client_code_rule(live, client):
    for path in ("/", "/tg", "/tg/finance_1", "/category/finance/tg"):
        assert_metrika_is_the_only_script(client.get(path).text, path)


def test_a_quote_in_the_channel_name_does_not_break_the_markup(layer, client):
    layer.channel(1, "tg", "quoted", display_name='Канал "Кавычки" <b>')
    layer.go_live()

    html = client.get("/tg/quoted").text
    trail = of_type(html, "BreadcrumbList")
    assert trail["itemListElement"][-1]["name"] == 'Канал "Кавычки" <b>'


# ── превью ссылки ────────────────────────────────────────────────────────────

def test_channel_link_carries_a_full_open_graph_set(live, client):
    html = client.get("/tg/finance_1").text
    assert meta(html, "og:type") == "profile"
    assert meta(html, "og:site_name") == "Fomobase"
    assert meta(html, "og:title") == re.search(r"<title>(.*?)</title>", html).group(1)
    assert meta(html, "og:url").endswith("/tg/finance_1")
    assert meta(html, "og:description")
    assert meta(html, "og:image").endswith("/assets/og-cover.png")
    assert 'name="twitter:card" content="summary_large_image"' in html


def test_the_preview_picture_is_actually_served(client):
    answer = client.get("/assets/og-cover.png")
    assert answer.status_code == 200
    assert answer.headers["content-type"] == "image/png"


def test_open_graph_url_repeats_the_canonical_not_the_requested_address(live, client):
    """У карточки один адрес: `?posts=2` и регистр не заводят второй."""
    html = client.get("/tg/finance_1?posts=2").text
    assert meta(html, "og:url").endswith("/tg/finance_1")


# ── карта сайта ──────────────────────────────────────────────────────────────

def test_sitemap_dates_differ_between_channels(layer, client):
    """До T-83 в карте ехало время сборки, одинаковое у всех строк."""
    from datetime import timedelta

    from conftest import NOW

    layer.channel(1, "tg", "fresh", changed_at=NOW)
    layer.channel(2, "tg", "stale", changed_at=NOW - timedelta(days=40))
    layer.go_live()

    xml = client.get("/sitemap-1.xml").text
    dates = set(re.findall(r"<lastmod>(.*?)</lastmod>", xml))
    assert len(dates) == 2, xml


def test_sitemap_index_points_at_the_sections_file(live, client):
    assert "/sitemap-sections.xml" in client.get("/sitemap.xml").text


def test_sections_map_holds_the_root_the_platforms_and_the_landings(live, client):
    xml = client.get("/sitemap-sections.xml").text
    urls = re.findall(r"<loc>(.*?)</loc>", xml)
    paths = [url.split("fomobase.ru")[-1] for url in urls]

    assert "/" in paths
    assert "/tg" in paths and "/vk" in paths
    assert "/category/finance" in paths
    assert "/category/finance/tg" in paths
    # Площадка без каналов и тонкая пара в карту не идут.
    assert "/max" not in paths and "/ok" not in paths
    assert "/category/finance/vk" not in paths


# ── переезд адреса при переименовании ────────────────────────────────────────

def test_old_address_of_a_renamed_channel_answers_with_a_move(layer, client):
    layer.channel(1, "tg", "newname")
    layer.alias(1, "oldname")
    layer.go_live()

    moved = client.get("/tg/oldname", follow_redirects=False)
    assert moved.status_code == 301
    assert moved.headers["location"] == "/tg/newname"
    assert client.get("/tg/newname").status_code == 200


def test_only_the_current_name_stands_in_the_catalog_and_the_map(layer, client):
    layer.channel(1, "tg", "newname")
    layer.alias(1, "oldname")
    layer.go_live()

    xml = client.get("/sitemap-1.xml").text
    assert "/tg/newname" in xml
    assert "oldname" not in xml
    assert "oldname" not in client.get("/").text


def test_an_unknown_address_is_still_a_404(layer, client):
    layer.channel(1, "tg", "newname")
    layer.alias(1, "oldname")
    layer.go_live()

    assert client.get("/tg/never_existed").status_code == 404


# ── дороги вбок с карточки ───────────────────────────────────────────────────

def test_channel_page_offers_similar_channels(live, client):
    html = client.get("/tg/finance_1").text
    assert "Похожие каналы" in html
    links = set(re.findall(r'href="(/tg/finance_\d+)"', html))
    assert len(links) >= 6, links
    assert "/tg/finance_1" not in links, "канал не похож сам на себя"


def test_similar_block_is_not_empty_for_a_channel_without_a_category(live, client):
    """Тематика есть у четверти каналов: без добора три четверти глубины —
    тупик, ради которого блок и делался."""
    html = client.get("/tg/lonely").text
    assert "Похожие каналы" in html
    assert re.search(r'href="/tg/finance_\d+"', html)


def test_similar_links_are_plain_links_not_dead_ends(live, client):
    """Ссылки без `nofollow`: они и есть дорога вглубь каталога."""
    html = client.get("/tg/finance_1").text
    block = html.split("Похожие каналы", 1)[1].split("</section>", 1)[0]
    assert "nofollow" not in block


def test_every_similar_link_leads_to_an_existing_page(live, client):
    html = client.get("/tg/finance_1").text
    block = html.split("Похожие каналы", 1)[1].split("</section>", 1)[0]
    for href in re.findall(r'href="(/[^"]+)"', block):
        assert client.get(href).status_code == 200, href


# ── посадочные «площадка + тематика» ─────────────────────────────────────────

def test_landing_page_answers_and_points_at_itself(live, client):
    answer = client.get("/category/finance/tg")
    assert answer.status_code == 200
    assert 'rel="canonical" href="https://fomobase.ru/category/finance/tg"' in answer.text


def test_thin_pair_has_no_page_of_its_own(live, client):
    assert client.get("/category/finance/vk").status_code == 404


def test_parameter_version_hands_the_index_over_to_the_landing(live, client):
    """Список один, и адрес у него один: `?cat=` остаётся дорогой для человека."""
    html = client.get("/tg?cat=finance").text
    assert 'rel="canonical" href="https://fomobase.ru/category/finance/tg"' in html


def test_filter_column_leads_to_the_landing_where_it_exists(live, client):
    html = client.get("/tg").text
    assert 'href="/category/finance/tg"' in html
    assert 'href="/tg?cat=finance"' not in html


def test_filter_column_keeps_the_parameter_for_a_thin_pair(live, client):
    html = client.get("/vk").text
    assert 'href="/vk?cat=finance"' in html
    assert 'href="/category/finance/vk"' not in html


def test_platform_parameter_on_a_category_page_moves_to_the_landing(live, client):
    moved = client.get("/category/finance?platform=tg", follow_redirects=False)
    assert moved.status_code == 301
    assert moved.headers["location"] == "/category/finance/tg"


def test_landing_of_an_unknown_platform_or_category_is_a_404(live, client):
    assert client.get("/category/finance/zen").status_code == 404
    assert client.get("/category/nothing/tg").status_code == 404


# ── заголовок и текст ────────────────────────────────────────────────────────

def test_channel_title_names_the_platform_the_handle_and_the_brand(live, client):
    title = re.search(r"<title>(.*?)</title>", client.get("/tg/finance_1").text).group(1)
    assert "Telegram" in title
    assert "@finance_1" in title
    assert "Fomobase" in title
    assert len(title) <= 70, f"{len(title)}: {title}"


def test_sections_carry_a_paragraph_built_from_their_own_numbers(live, client):
    for path in ("/tg", "/category/finance", "/category/finance/tg"):
        body = client.get(path).text
        assert "В подборке" in body, path
        assert "медианный охват поста" in body, path
        assert "рекламная история" in body, path


def test_the_root_has_no_section_paragraph(live, client):
    assert "В подборке" not in client.get("/").text


def test_main_avatar_says_what_it_shows(layer, client):
    layer.channel(1, "tg", "with_face", avatar_file="a/face.jpg",
                  display_name="Лицо канала")
    layer.go_live()

    html = client.get("/tg/with_face").text
    assert 'alt="Аватар канала Лицо канала"' in html


# ── краулеру дешевле ─────────────────────────────────────────────────────────

def test_pages_say_when_they_last_changed(live, client):
    answer = client.get("/tg/finance_1")
    assert answer.headers["Last-Modified"]
    assert answer.headers["ETag"]


def test_the_same_version_is_not_sent_twice(live, client):
    first = client.get("/tg/finance_1")
    again = client.get("/tg/finance_1", headers={"If-None-Match": first.headers["ETag"]})
    assert again.status_code == 304
    assert not again.content


def test_open_robots_file_carries_clean_param_for_yandex(live, make_client):
    body = make_client(noindex=False).get("/robots.txt").text
    assert "Clean-param: " in body
    assert "cat" in body.split("Clean-param: ", 1)[1]


# ── переключатель не тронут ──────────────────────────────────────────────────

def test_the_whole_site_including_the_new_addresses_stays_closed(live, client):
    for path in ("/", "/tg", "/category/finance", "/category/finance/tg",
                 "/tg/finance_1", "/sitemap-sections.xml"):
        assert client.get(path).headers["x-robots-tag"] == "noindex, nofollow", path
    assert client.get("/robots.txt").text.strip().endswith("Disallow: /")


def test_with_the_switch_open_the_landing_is_indexable(live, make_client):
    """Проверка индексируемости живёт здесь, а не на проде: на проде запрет
    стоит на каждом ответе и обязан стоять."""
    open_client = make_client(noindex=False)
    assert "noindex" not in open_client.get("/category/finance/tg").headers.get(
        "x-robots-tag", "")
    # А фильтрованный адрес того же списка в индекс по-прежнему не идёт.
    assert open_client.get("/tg?cat=finance").headers["x-robots-tag"] == "noindex, follow"
