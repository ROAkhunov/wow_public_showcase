"""T-134: страницы «<площадка> каналы <города>» под региональный спрос.

Шов тот же: засеяли публичный слой — дёрнули адрес. Город, признак «местный» и
цифры пары «площадка + город» приезжают из дампа (T-133), витрина только
проверяет порог в 10 местных каналов и печатает.

Города и каналы выдуманные, как и везде в тестах: репозиторий публичный.
"""
import re

import pytest

from conftest import assert_only_allowed_scripts


def paths_in_sitemap(xml: str) -> list[str]:
    return [url.split("fomobase.ru")[-1] for url in re.findall(r"<loc>(.*?)</loc>", xml)]


def h1(html: str) -> str:
    return re.search(r"<h1>(.*?)</h1>", html, re.S).group(1).strip()


def title(html: str) -> str:
    return re.search(r"<title>(.*?)</title>", html, re.S).group(1).strip()


def description(html: str) -> str:
    return re.search(r'<meta name="description" content="([^"]*)"', html).group(1)


@pytest.fixture
def live(layer):
    """Казань: 10 местных в TG (ровно порог) и неместный-гигант того же города.
    Москва: VK крупнее TG, MAX на пороге. Ижевск: MAX на 9, ниже порога.
    Город «Равноград»: TG и VK поровну, выбор по порядку площадок."""
    layer.city("kazan", "Казань", "Казани")
    layer.city("moskva", "Москва", "Москвы")
    layer.city("izhevsk", "Ижевск", "Ижевска")
    layer.city("ravnograd", "Равноград", "Равнограда")
    layer.city("pustograd", "Пустоград", "Пустограда")

    for i in range(1, 11):
        layer.channel(i, "tg", f"kazan_local_{i}", subscribers=50_000 - i * 1000,
                      display_name=f"Казань местный {i}",
                      city="Казань", city_slug="kazan", is_local=True)
    # Город тот же, но канал не местный: у каталогов это город автора.
    layer.channel(11, "tg", "kazan_author", subscribers=900_000,
                  display_name="Автор из Казани", city="Казань", city_slug="kazan",
                  is_local=False)
    # Местный канал другой площадки у автора неместного канала.
    layer.channel(12, "vk", "moskva_local", subscribers=30_000,
                  display_name="Москва местная", city="Москва", city_slug="moskva",
                  is_local=True)
    layer.sibling(11, 12)
    layer.sibling(12, 11)
    # Местный, но пара ниже порога.
    layer.channel(13, "max", "izhevsk_local", subscribers=5_000,
                  display_name="Ижевск местный", city="Ижевск", city_slug="izhevsk",
                  is_local=True)
    layer.channel(14, "tg", "no_city", subscribers=70_000, display_name="Без города")
    layer.category(1, "Финансы", "finance")

    layer.section("", "", channels=14, views_median=20_000, ads_share=42.0)
    layer.section("tg", "", channels=500, views_median=99_999, ads_share=11.0)
    layer.section("vk", "", channels=300, views_median=88_888, ads_share=12.0)
    layer.section("max", "", channels=200, views_median=77_777, ads_share=13.0)
    layer.section("tg", "finance", name="Финансы", channels=1)

    layer.city_section("tg", "kazan", channels=10, subs_median=45_000,
                       views_median=7_700, ads_share=33.0)
    layer.city_section("vk", "kazan", channels=3, views_median=1_000, ads_share=5.0)
    layer.city_section("yt", "kazan", channels=7, views_median=2_000, ads_share=1.0)
    layer.city_section("tg", "moskva", channels=11, views_median=6_600, ads_share=20.0)
    layer.city_section("vk", "moskva", channels=25, views_median=5_500, ads_share=21.0)
    layer.city_section("max", "moskva", channels=10, views_median=4_400, ads_share=22.0)
    layer.city_section("max", "izhevsk", channels=9, views_median=3_300, ads_share=23.0)
    layer.city_section("tg", "ravnograd", channels=15)
    layer.city_section("vk", "ravnograd", channels=15)
    layer.city_section("tg", "pustograd", channels=4)
    return layer.go_live()


# ── порог ────────────────────────────────────────────────────────────────────

def test_a_pair_at_the_threshold_has_a_page(live, client):
    assert client.get("/city/kazan/tg").status_code == 200


def test_a_pair_below_the_threshold_is_a_404(live, client):
    assert client.get("/city/izhevsk/max").status_code == 404
    assert client.get("/city/kazan/vk").status_code == 404


def test_a_pair_without_a_row_is_a_404(live, client):
    assert client.get("/city/kazan/max").status_code == 404


def test_unknown_city_platform_and_youtube_are_404(live, client):
    assert client.get("/city/nowhere/tg").status_code == 404
    assert client.get("/city/kazan/zen").status_code == 404
    assert client.get("/city/kazan/yt").status_code == 404


# ── список ───────────────────────────────────────────────────────────────────

def test_the_list_holds_only_local_channels_of_the_city_and_platform(live, client):
    body = client.get("/city/kazan/tg").text
    for i in range(1, 11):
        assert f"/tg/kazan_local_{i}" in body, i
    assert "/tg/kazan_author" not in body, "неместный канал того же города попал в список"
    assert "/tg/no_city" not in body
    assert "/vk/moskva_local" not in body


def test_the_list_goes_down_by_subscribers(live, client):
    body = client.get("/city/kazan/tg").text
    assert body.index("/tg/kazan_local_1?") < body.index("/tg/kazan_local_2?")
    assert body.index("/tg/kazan_local_9?") < body.index("/tg/kazan_local_10?")


def test_the_list_is_paginated_like_a_section(live, make_client):
    client = make_client(page_size=4)
    assert client.get("/city/kazan/tg?page=3").status_code == 200
    assert client.get("/city/kazan/tg?page=4").status_code == 404
    assert "/tg/kazan_local_5?" in client.get("/city/kazan/tg?page=2").text


def test_filters_work_on_the_city_page(live, client):
    body = client.get("/city/kazan/tg?subs_min=45000").text
    assert "/tg/kazan_local_1?" in body
    assert "/tg/kazan_local_6?" not in body


# ── тексты ───────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("path, head, line", [
    ("/city/kazan/tg", "Telegram-каналы Казани",
     "Местные Telegram-каналы Казани: подписчики, охваты и реклама"),
    ("/city/moskva/vk", "Группы ВКонтакте Москвы",
     "Местные группы и паблики ВКонтакте Москвы: подписчики, охваты и реклама"),
    ("/city/moskva/max", "Каналы MAX Москвы",
     "Местные каналы MAX Москвы: подписчики, охваты и реклама"),
])
def test_title_heading_and_line_follow_the_table(live, client, path, head, line):
    html = client.get(path).text
    assert title(html) == f"{head} — Fomobase"
    assert h1(html) == head
    assert f"<p>{line}</p>" in html
    assert description(html) == line


def test_the_paragraph_carries_the_numbers_of_the_city_not_of_the_platform(live, client):
    body = client.get("/city/kazan/tg").text
    assert "В подборке 10 каналов" in body
    assert "медианный охват поста 7" in body and "700" in body
    assert "рекламная история есть у 33%" in body
    assert "99" not in re.search(r'<p class="sub section-note">(.*?)</p>', body).group(1)
    assert "500" not in re.search(r'<p class="sub section-note">(.*?)</p>', body).group(1)


def test_the_page_points_at_itself(live, client):
    html = client.get("/city/kazan/tg").text
    assert 'rel="canonical" href="https://fomobase.ru/city/kazan/tg"' in html


def test_the_page_keeps_the_no_client_code_rule(live, client):
    assert_only_allowed_scripts(client.get("/city/kazan/tg").text, "/city/kazan/tg")


# ── параметр тематики ────────────────────────────────────────────────────────
# Перевёрнуто T-137 (п. 2): правило «у города тематики нет» отменено, `?cat=`
# работает параметром, а не срезается 301.

def test_category_parameter_works_on_the_city_page(live, client):
    got = client.get("/city/kazan/tg?cat=finance", follow_redirects=False)
    assert got.status_code == 200


def test_category_parameter_and_other_filters_stay(live, client):
    got = client.get("/city/kazan/tg?subs_min=100&cat=finance", follow_redirects=False)
    assert got.status_code == 200


# ── колонка фильтров ─────────────────────────────────────────────────────────
# Перевёрнуто T-137 (п. 4): чипы площадок и тематик на странице города больше
# не уводят с города. Площадка ниже порога не показывается вовсе.

def test_filter_chips_stay_in_the_city(live, client):
    body = client.get("/city/kazan/tg").text
    assert 'href="/city/kazan/tg?cat=finance"' in body
    assert 'href="/tg?cat=finance"' not in body
    assert 'href="/city/kazan/vk"' not in body, "пара ниже порога в чипах площадок"
    assert 'href="/city/kazan"' in body


# ── город без площадки ───────────────────────────────────────────────────────
# Перевёрнуто T-137 (п. 1): вместо 301 на крупную пару у города общая страница
# по tg, vk, max с порогом 10 местных каналов вместе. Здесь у Казани 10 местных
# каналов в TG, у Москвы и Равнограда по одному в VK.

def test_city_without_platform_is_a_page_at_the_threshold(live, client):
    got = client.get("/city/kazan", follow_redirects=False)
    assert got.status_code == 200


def test_city_without_platform_counts_channels_not_pairs(live, client):
    # Цифры пар у Москвы и Равнограда большие, а местных каналов в слое один
    # и ноль: общий порог считается по каналам.
    assert client.get("/city/moskva", follow_redirects=False).status_code == 404
    assert client.get("/city/ravnograd", follow_redirects=False).status_code == 404


def test_city_without_a_pair_over_the_threshold_is_a_404(live, client):
    assert client.get("/city/izhevsk", follow_redirects=False).status_code == 404
    assert client.get("/city/pustograd", follow_redirects=False).status_code == 404
    assert client.get("/city/nowhere", follow_redirects=False).status_code == 404


def test_city_addresses_do_not_fall_into_the_channel_card(live, client):
    for path in ("/city/nowhere/tg", "/city/kazan/zen"):
        body = client.get(path).text
        assert "Такого канала в базе нет" not in body, path


# ── карта сайта ──────────────────────────────────────────────────────────────

def test_sitemap_holds_city_pairs_over_the_threshold_only(live, client):
    paths = paths_in_sitemap(client.get("/sitemap-sections.xml").text)
    for good in ("/city/kazan/tg", "/city/moskva/tg", "/city/moskva/vk",
                 "/city/moskva/max", "/city/ravnograd/tg", "/city/ravnograd/vk"):
        assert good in paths, good
    for bad in ("/city/kazan/vk", "/city/kazan/yt", "/city/izhevsk/max",
                "/city/pustograd/tg"):
        assert bad not in paths, bad


# ── ссылка со страницы канала ────────────────────────────────────────────────

def city_block(html: str) -> list[str]:
    """Ссылки блоков «Город» на странице."""
    return re.findall(r'<span class="ds-label">Город</span>\s*<div class="sites-list">\s*'
                      r'<a class="chip" href="([^"]+)">([^<]+)</a>', html)


def test_local_channel_links_to_its_city_page(live, client):
    html = client.get("/tg/kazan_local_3").text
    assert city_block(html) == [("/city/kazan/tg", "Telegram-каналы Казани")]


def test_the_block_does_not_need_a_category(live, client):
    html = client.get("/tg/kazan_local_2").text
    assert "Тематики" not in html
    assert city_block(html) == [("/city/kazan/tg", "Telegram-каналы Казани")]


def test_non_local_channel_has_no_city_link_but_its_local_sibling_does(live, client):
    html = client.get("/tg/kazan_author").text
    assert city_block(html) == [("/city/moskva/vk", "Группы ВКонтакте Москвы")]


def test_local_channel_of_a_thin_city_has_no_block(live, client):
    assert city_block(client.get("/max/izhevsk_local").text) == []


def test_channel_without_a_city_has_no_block(live, client):
    assert city_block(client.get("/tg/no_city").text) == []
