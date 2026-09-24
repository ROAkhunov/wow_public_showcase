"""T-137: фильтр «Город» в колонке фильтров и общая страница города.

Страницы городов T-134 жили отдельно от каталога: из колонки фильтров на них
было не попасть. Теперь город это ещё один фильтр колонки, а у города есть
общая страница `/city/<slug>` по площадкам tg, vk, max.

Шов тот же: засеяли слой, дёрнули адрес. Цифры `city_section` засеяны ровно
по засеянным каналам, как их считает сборщик, чтобы порог страницы (счёт по
каналам) и набор городов в колонке (цифры дампа) не расходились.

Города и каналы выдуманные: репозиторий публичный.
"""
import re
from html.parser import HTMLParser

import pytest

from conftest import assert_only_allowed_scripts

#: (slug, имя, родительный падеж, местных каналов по площадкам).
#: Сумма по tg, vk, max: Москва 67, дальше 21…13 (первая десятка вместе с
#: Казанью на 15), хвост Самара 12, Омск 11, Тула 10. По алфавиту хвост идёт
#: иначе, чем по счёту: Омск, Самара, Тула. Ижевск 9 без YT, с YT 12.
CITIES = [
    ("moskva", "Москва", "Москвы", {"tg": 30, "vk": 25, "max": 12}),
    ("barnaul", "Барнаул", "Барнаула", {"tg": 21}),
    ("voronezh", "Воронеж", "Воронежа", {"tg": 20}),
    ("ekb", "Екатеринбург", "Екатеринбурга", {"tg": 19}),
    ("krasnodar", "Краснодар", "Краснодара", {"tg": 18}),
    ("nsk", "Новосибирск", "Новосибирска", {"tg": 17}),
    ("perm", "Пермь", "Перми", {"tg": 16}),
    ("kazan", "Казань", "Казани", {"tg": 12, "vk": 3, "yt": 7}),
    ("tver", "Тверь", "Твери", {"tg": 14}),
    ("ufa", "Уфа", "Уфы", {"tg": 13}),
    ("samara", "Самара", "Самары", {"tg": 6, "vk": 6}),
    ("omsk", "Омск", "Омска", {"vk": 11}),
    ("tula", "Тула", "Тулы", {"tg": 5, "vk": 5}),
    ("izhevsk", "Ижевск", "Ижевска", {"tg": 4, "vk": 5, "yt": 3}),
]

TOP_TEN = ["Москва", "Барнаул", "Воронеж", "Екатеринбург", "Краснодар",
           "Новосибирск", "Пермь", "Казань", "Тверь", "Уфа"]


@pytest.fixture
def live(layer):
    next_id = 1
    for slug, name, gen, by_platform in CITIES:
        layer.city(slug, name, gen)
        for platform, n in by_platform.items():
            for i in range(1, n + 1):
                layer.channel(next_id, platform, f"{slug}_{platform}_{i}",
                              subscribers=100_000 - i * 1000,
                              display_name=f"{name} {platform} {i}",
                              city=name, city_slug=slug, is_local=True)
                next_id += 1
            layer.city_section(platform, slug, channels=n, views_median=1_000,
                               ads_share=10.0)
    # Город есть в справочнике, местных каналов у него нет.
    layer.city("pustograd", "Пустоград", "Пустограда")
    # Город тот же, но канал не местный: у каталогов это город автора.
    layer.channel(9001, "tg", "kazan_author", subscribers=900_000,
                  display_name="Автор из Казани", city="Казань", city_slug="kazan",
                  is_local=False)
    layer.channel(9002, "tg", "no_city", subscribers=800_000, display_name="Без города")

    # Тематики: «Новости» у пары TG проходит порог посадочной (T-83),
    # «Спорт» нет, живёт параметром.
    ids = {}
    with layer.conn.cursor() as cur:
        cur.execute(f'SELECT id, username_lower FROM "{layer.schema}".channel')
        ids = {u: i for i, u in cur.fetchall()}
    for u in ("kazan_tg_1", "kazan_tg_2", "kazan_tg_3", "kazan_vk_1", "moskva_tg_1"):
        layer.category(ids[u], "Новости", "news")
    for u in ("kazan_tg_4", "moskva_vk_1", "moskva_tg_2"):
        layer.category(ids[u], "Спорт", "sport")

    layer.section("", "", channels=300)
    for p in ("tg", "vk", "max", "yt"):
        layer.section(p, "", channels=100)
    layer.section("", "news", name="Новости", channels=5)
    layer.section("", "sport", name="Спорт", channels=3)
    layer.section("tg", "news", name="Новости", channels=12)
    layer.section("yt", "news", name="Новости", channels=10)
    layer.section("tg", "sport", name="Спорт", channels=2)
    return layer.go_live()


# ── разбор колонки ───────────────────────────────────────────────────────────

CHIP = re.compile(r'<a class="chip( on)?" href="([^"]*)">([^<]*)</a>')


def desktop(html: str) -> str:
    """Десктопная копия колонки: на странице их две, `d` и `m`."""
    return html.split('<aside class="side-desktop">', 1)[1].split("</aside>", 1)[0]


def city_group(html: str) -> str | None:
    """Блок «Город» десктопной колонки целиком, или None."""
    side = desktop(html)
    start = side.find('<span class="ds-label">Город</span>')
    if start < 0:
        return None
    end = side.find('<div class="group">', start)
    return side[start:end if end > 0 else len(side)]


def city_chips(html: str) -> tuple[list[tuple], list[tuple]]:
    """Чипы блока «Город»: (видимые, под «Показать все»), каждый (on, href, имя)."""
    group = city_group(html)
    assert group is not None, "блока «Город» нет"
    head, _, tail = group.partition("<details")
    visible = [(bool(on), href, name) for on, href, name in CHIP.findall(head)]
    rest = [(bool(on), href, name) for on, href, name in CHIP.findall(tail)]
    return visible, rest


def names(chips):
    return [name for _, _, name in chips]


def href_of(chips, name):
    return next(href for _, href, n in chips if n == name)


def h1(html: str) -> str:
    return re.search(r"<h1>(.*?)</h1>", html, re.S).group(1).strip()


def title(html: str) -> str:
    return re.search(r"<title>(.*?)</title>", html, re.S).group(1).strip()


def description(html: str) -> str:
    return re.search(r'<meta name="description" content="([^"]*)"', html).group(1)


def paths_in_sitemap(xml: str) -> list[str]:
    return [url.split("fomobase.ru")[-1] for url in re.findall(r"<loc>(.*?)</loc>", xml)]


# ── п. 1: общая страница города ──────────────────────────────────────────────

def test_general_city_page_at_ten_local_channels_is_200(live, client):
    assert client.get("/city/tula").status_code == 200


def test_general_city_page_at_nine_is_404_youtube_does_not_count(live, client):
    assert client.get("/city/izhevsk").status_code == 404


def test_general_city_page_of_unknown_or_empty_city_is_404(live, client):
    assert client.get("/city/nowhere").status_code == 404
    assert client.get("/city/pustograd").status_code == 404


def test_general_city_page_is_a_page_not_a_move(live, client):
    got = client.get("/city/moskva", follow_redirects=False)
    assert got.status_code == 200


def test_general_list_holds_local_channels_of_three_platforms_only(live, client):
    body = client.get("/city/kazan").text
    for u in ("kazan_tg_1", "kazan_tg_12", "kazan_vk_1", "kazan_vk_3"):
        assert f"/{u.split('_')[1]}/{u}?" in body, u
    assert "kazan_yt_" not in body, "YT попал в общую страницу города"
    assert "kazan_author" not in body, "неместный канал попал в список"
    assert "no_city" not in body
    assert "moskva_" not in body


def test_general_list_is_sorted_and_paginated_like_the_root(live, make_client):
    client = make_client(page_size=10)
    assert client.get("/city/moskva?page=7").status_code == 200
    assert client.get("/city/moskva?page=8").status_code == 404
    first = client.get("/city/moskva").text
    # Подписчики у первых по каждой площадке одинаковые: 99 000.
    assert "moskva_tg_1?" in first and "moskva_vk_1?" in first and "moskva_max_1?" in first


def test_general_page_texts(live, client):
    html = client.get("/city/kazan").text
    line = "Местные каналы и группы Казани в Telegram, ВКонтакте и MAX: подписчики, охваты и реклама"
    assert title(html) == "Каналы и группы Казани — Fomobase"
    assert h1(html) == "Каналы и группы Казани"
    assert f"<p>{line}</p>" in html
    assert description(html) == line


def test_general_page_has_no_numbers_paragraph(live, client):
    assert "section-note" not in client.get("/city/kazan").text
    assert "section-note" not in client.get("/city/kazan?cat=news").text


def test_general_page_filters_and_canonical(live, client):
    body = client.get("/city/moskva?subs_min=98500").text
    assert "moskva_tg_1?" in body and "moskva_tg_2?" not in body
    html = client.get("/city/kazan").text
    assert 'rel="canonical" href="https://fomobase.ru/city/kazan"' in html


def test_general_page_does_not_fall_into_platform_or_card(live, client):
    for path in ("/city/kazan", "/city"):
        body = client.get(path).text
        assert "Такого канала в базе нет" not in body, path


def test_general_page_keeps_the_no_client_code_rule(live, client):
    assert_only_allowed_scripts(client.get("/city/kazan").text, "/city/kazan")


# ── п. 2: тематика внутри города ─────────────────────────────────────────────

def test_category_works_on_the_general_city_page(live, client):
    got = client.get("/city/kazan?cat=news", follow_redirects=False)
    assert got.status_code == 200
    for u in ("tg/kazan_tg_1", "tg/kazan_tg_3", "vk/kazan_vk_1"):
        assert f"/{u}?" in got.text, u
    assert "/tg/kazan_tg_4?" not in got.text
    assert "/tg/moskva_tg_1?" not in got.text


def test_category_works_on_the_city_platform_page(live, client):
    got = client.get("/city/kazan/tg?cat=news", follow_redirects=False)
    assert got.status_code == 200
    assert "/tg/kazan_tg_1?" in got.text and "/tg/kazan_tg_4?" not in got.text
    assert "/vk/kazan_vk_1?" not in got.text


def test_city_with_category_is_noindex_follow(live, make_client):
    client = make_client(noindex=False)
    for path in ("/city/kazan?cat=news", "/city/kazan/tg?cat=news"):
        got = client.get(path)
        assert got.headers.get("x-robots-tag") == "noindex, follow", path


def test_city_with_category_does_not_point_at_the_landing(live, client):
    html = client.get("/city/kazan/tg?cat=news").text
    assert 'rel="canonical" href="https://fomobase.ru/category/news/tg"' not in html


# ── п. 3: блок «Город» ───────────────────────────────────────────────────────

@pytest.mark.parametrize("path", [
    "/", "/tg", "/vk", "/max", "/category/news", "/category/news/tg",
    "/city/kazan", "/city/kazan/tg",
])
def test_the_block_is_on_every_catalog_address(live, client, path):
    got = client.get(path)
    assert got.status_code == 200, path
    assert city_group(got.text) is not None, path


@pytest.mark.parametrize("path", ["/yt", "/category/news/yt"])
def test_the_block_is_not_on_youtube(live, client, path):
    got = client.get(path)
    assert got.status_code == 200, path
    assert city_group(got.text) is None, path


def test_the_set_depends_on_the_platform(live, client):
    root = names(sum(city_chips(client.get("/").text), []))
    tg = names(sum(city_chips(client.get("/tg").text), []))
    vk = names(sum(city_chips(client.get("/vk").text), []))
    assert "Казань" in root and "Омск" in root and "Тула" in root
    assert "Ижевск" not in root and "Пустоград" not in root
    assert "Казань" in tg and "Омск" not in tg and "Тула" not in tg
    assert vk == ["Все города", "Москва", "Омск"]


def test_first_ten_by_count_then_the_tail_by_alphabet(live, client):
    visible, rest = city_chips(client.get("/").text)
    assert names(visible) == ["Все города"] + TOP_TEN
    assert names(rest) == ["Омск", "Самара", "Тула"]


def test_on_a_platform_the_order_is_by_that_platform(live, client):
    visible, _ = city_chips(client.get("/tg").text)
    # Казань в TG на 12, после Уфы на 13; Москва первая.
    assert names(visible)[1] == "Москва"
    assert names(visible)[-1] == "Казань"


def test_selected_city_outside_ten_is_visible_and_on(live, client):
    visible, rest = city_chips(client.get("/city/tula").text)
    assert (True, "/city/tula", "Тула") in visible
    assert "Тула" not in names(rest)
    assert (False, "/", "Все города") in visible


def test_all_cities_is_on_when_no_city_is_chosen(live, client):
    visible, _ = city_chips(client.get("/").text)
    assert visible[0] == (True, "/", "Все города")
    assert not any(on for on, _, _ in visible[1:])


def test_city_chip_keeps_platform_and_category(live, client):
    visible, _ = city_chips(client.get("/tg?cat=sport").text)
    assert href_of(visible, "Казань") == "/city/kazan/tg?cat=sport"
    visible, _ = city_chips(client.get("/").text)
    assert href_of(visible, "Казань") == "/city/kazan"
    visible, _ = city_chips(client.get("/category/sport").text)
    assert href_of(visible, "Казань") == "/city/kazan?cat=sport"
    visible, _ = city_chips(client.get("/category/news/tg").text)
    assert href_of(visible, "Казань") == "/city/kazan/tg?cat=news"


def test_city_chip_drops_ranges_and_sort(live, client):
    visible, _ = city_chips(client.get("/tg?subs_min=100&sort=views").text)
    assert href_of(visible, "Казань") == "/city/kazan/tg"


def test_all_cities_leads_to_the_same_address_without_the_city(live, client):
    visible, _ = city_chips(client.get("/city/kazan/tg?cat=sport").text)
    assert href_of(visible, "Все города") == "/tg?cat=sport"
    visible, _ = city_chips(client.get("/city/kazan").text)
    assert href_of(visible, "Все города") == "/"
    visible, _ = city_chips(client.get("/city/kazan/tg").text)
    assert href_of(visible, "Все города") == "/tg"


# ── п. 3: поиск города ───────────────────────────────────────────────────────

@pytest.mark.parametrize("q", ["Казань", "казань", " КАЗАНЬ "])
def test_search_moves_to_the_city_ignoring_case(live, client, q):
    got = client.get("/city", params={"q": q}, follow_redirects=False)
    assert got.status_code == 301
    assert got.headers["location"] == "/city/kazan"


def test_search_keeps_platform_and_category(live, client):
    got = client.get("/city", params={"q": "казань", "platform": "tg", "cat": "sport"},
                     follow_redirects=False)
    assert got.status_code == 301
    assert got.headers["location"] == "/city/kazan/tg?cat=sport"
    got = client.get("/city", params={"q": "Москва", "cat": "news"}, follow_redirects=False)
    assert got.headers["location"] == "/city/moskva?cat=news"


def test_search_for_an_unknown_city_is_404(live, client):
    for params in ({"q": "Нигдебург"}, {"q": ""}, {}, {"q": "Ижевск"}, {"q": "Пустоград"}):
        got = client.get("/city", params=params, follow_redirects=False)
        assert got.status_code == 404, params
        assert "Такого города нет" in got.text, params


class Forms(HTMLParser):
    """Формы страницы, вложенность и поля, привязанные атрибутом `form`."""

    def __init__(self):
        super().__init__()
        self.depth = 0
        self.nested = 0
        self.forms = {}
        self.bound = []          # (tag, attrs) с атрибутом form
        self.datalists = {}
        self._list = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "form":
            self.depth += 1
            if self.depth > 1:
                self.nested += 1
            if a.get("id"):
                self.forms[a["id"]] = a
        if "form" in a and tag in ("input", "button"):
            self.bound.append((tag, a))
        if tag == "datalist":
            self._list = a.get("id")
            self.datalists[self._list] = []
        if tag == "option" and self._list:
            self.datalists[self._list].append(a.get("value"))

    def handle_endtag(self, tag):
        if tag == "form":
            self.depth -= 1
        if tag == "datalist":
            self._list = None


@pytest.mark.parametrize("path, platform, cat", [
    ("/", None, None), ("/tg?cat=sport", "tg", "sport"), ("/city/kazan/tg", "tg", None),
])
def test_search_field_is_bound_to_its_own_form_without_nesting(live, client, path, platform, cat):
    html = client.get(path).text
    forms = Forms()
    forms.feed(html)
    assert forms.nested == 0, "вложенная форма: браузер её выкинет"
    for s in ("d", "m"):
        fid = f"city-search-{s}"
        assert fid in forms.forms, fid
        assert forms.forms[fid].get("action") == "/city"
        assert forms.forms[fid].get("method", "get").lower() == "get"
        mine = [(t, a) for t, a in forms.bound if a["form"] == fid]
        query = [a for t, a in mine if t == "input" and a.get("name") == "q"]
        assert len(query) == 1, fid
        assert query[0].get("list") == f"cities-{s}"
        assert forms.datalists.get(f"cities-{s}"), "пустой datalist"
        assert any(t == "button" for t, _ in mine), f"нет кнопки у {fid}"
        hidden = {a["name"]: a["value"] for t, a in mine
                  if t == "input" and a.get("type") == "hidden"}
        assert hidden.get("platform") == platform
        assert hidden.get("cat") == cat


def test_datalist_holds_the_cities_of_the_set(live, client):
    forms = Forms()
    forms.feed(client.get("/vk").text)
    assert sorted(forms.datalists["cities-d"]) == ["Москва", "Омск"]


def test_catalog_pages_keep_the_no_client_code_rule(live, client):
    for path in ("/", "/tg?cat=sport", "/city/kazan/tg"):
        assert_only_allowed_scripts(client.get(path).text, path)


# ── п. 4: чипы площадок и тематик на странице города ─────────────────────────

def platform_group(html: str) -> list[tuple]:
    side = desktop(html)
    start = side.find('<span class="ds-label">Площадка</span>')
    end = side.find('<div class="group">', start)
    return [(bool(on), href) for on, href, _ in CHIP.findall(
        re.sub(r'<span class="dot[^>]*>[^<]*</span>', "", side[start:end]))]


def topic_hrefs(html: str) -> list[str]:
    side = desktop(html)
    start = side.find('<span class="ds-label">Тематика</span>')
    end = side.find('<span class="ds-label">Город</span>', start)
    return [href for _, href, _ in CHIP.findall(side[start:end])]


def test_platform_chips_on_a_city_page_stay_in_the_city(live, client):
    chips = platform_group(client.get("/city/moskva").text)
    assert chips == [(True, "/city/moskva"), (False, "/city/moskva/tg"),
                     (False, "/city/moskva/vk"), (False, "/city/moskva/max")]


def test_platform_chips_below_threshold_and_youtube_are_hidden(live, client):
    chips = platform_group(client.get("/city/kazan/tg").text)
    assert chips == [(False, "/city/kazan"), (True, "/city/kazan/tg")]


def test_platform_chips_on_a_city_page_keep_the_category(live, client):
    chips = platform_group(client.get("/city/moskva?cat=sport").text)
    assert (False, "/city/moskva/vk?cat=sport") in chips
    assert (True, "/city/moskva?cat=sport") in chips


def test_topic_chips_on_a_city_page_stay_in_the_city(live, client):
    assert set(topic_hrefs(client.get("/city/kazan/tg").text)) == {
        "/city/kazan/tg?cat=news", "/city/kazan/tg?cat=sport"}
    assert set(topic_hrefs(client.get("/city/kazan").text)) == {
        "/city/kazan?cat=news", "/city/kazan?cat=sport"}


def test_topic_chips_off_the_city_are_as_before(live, client):
    assert "/category/news/tg" in topic_hrefs(client.get("/tg").text)
    assert "/tg?cat=sport" in topic_hrefs(client.get("/tg").text)


# ── п. 5: карта сайта ────────────────────────────────────────────────────────

def test_sitemap_holds_general_city_pages_on_two_platforms_or_more(live, client):
    paths = paths_in_sitemap(client.get("/sitemap-sections.xml").text)
    for good in ("/city/moskva", "/city/kazan", "/city/samara", "/city/tula"):
        assert good in paths, good
    for bad in ("/city/omsk", "/city/barnaul", "/city/izhevsk", "/city/pustograd"):
        assert bad not in paths, bad
    # Пары T-134 на месте.
    for pair in ("/city/moskva/max", "/city/omsk/vk", "/city/kazan/tg"):
        assert pair in paths, pair
    assert "/city" not in paths
