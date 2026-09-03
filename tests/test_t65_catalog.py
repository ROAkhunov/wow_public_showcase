"""T-65: фильтры, сортировка и адреса каталога.

Фильтры серверные: своего клиентского кода на странице не появляется (кроме
счётчика Метрики, T-90), состояние живёт в адресе. Отсюда две группы проверок — что фильтр действительно сужает
выдачу и что у каждого состояния ровно один адрес.

Классы параметров разные, и правила у них разные: `page` это путь краулера,
`sort` и диапазоны — нет. Мусор в номере страницы это 404, мусор в фильтре —
301 на нормализованный адрес.
"""
import pytest

from conftest import assert_metrika_is_the_only_script

pytestmark = pytest.mark.integration


def seed(layer, n=6):
    """Каналы с разбегом по всем колонкам, которые каталог фильтрует."""
    for i in range(1, n + 1):
        layer.channel(i, "tg", f"ch{i}",
                      subscribers=i * 10_000,
                      views_organic=i * 1_000,
                      coverage_ratio=float(i),
                      ad_share_30d=float(i * 10),
                      adv_total=i if i % 2 else 0,
                      blogger_has_siblings=(i == 3))
    return layer


def plain(body):
    """Тело со снятым экранированием: в разметке `&` живёт как `&amp;`."""
    return body.replace("&amp;", "&")


def names(body):
    return {f"ch{i}" for i in range(1, 12) if f"/tg/ch{i}" in body}


# ── колонка фильтров есть везде, где есть список ─────────────────────────────

@pytest.mark.parametrize("url", ["/", "/tg", "/category/eda"])
def test_every_listing_carries_the_filter_column(layer, client, url):
    """Решение созвона 22.07: фильтры в левой колонке, разделы сверху.

    Раздел это тоже список, и приходить в него без фильтров значит терять их при
    первом же переходе из каталога.
    """
    cid = seed(layer).channel(9, "tg", "tagged")
    layer.category(9, "Еда", "eda")
    layer.go_live()

    body = client.get(url).text
    assert "Подписчики" in body and "Доля рекламы" in body
    assert_metrika_is_the_only_script(body, url)


# ── фильтр сужает выдачу ─────────────────────────────────────────────────────

def test_subscriber_range_narrows_the_listing(layer, client):
    seed(layer).go_live()
    body = client.get("/?subs_min=25000&subs_max=45000").text
    assert names(body) == {"ch3", "ch4"}


def test_views_and_ad_share_ranges_work_together(layer, client):
    seed(layer).go_live()
    body = client.get("/?views_min=2000&ads_max=40").text
    assert names(body) == {"ch2", "ch3", "ch4"}


def test_checkbox_keeps_only_channels_with_an_advertising_history(layer, client):
    seed(layer).go_live()
    assert names(client.get("/?has_ads=1").text) == {"ch1", "ch3", "ch5"}


def test_checkbox_keeps_only_authors_with_several_platforms(layer, client):
    seed(layer).go_live()
    assert names(client.get("/?has_siblings=1").text) == {"ch3"}


def test_filter_narrows_the_counter_too(layer, client):
    """«Найдено N» под фильтром считает отфильтрованное, а не весь каталог."""
    seed(layer).go_live()
    body = client.get("/?subs_min=45000").text
    assert ">2<" in body.replace("\n", "")


# ── сортировка ───────────────────────────────────────────────────────────────

def test_sort_changes_the_order_and_is_a_link_not_a_button(layer, client):
    """Кнопка сортировки в дизайн-системе нарисована `button`, но кнопка без
    клиентского кода никуда не ведёт: на витрине это ссылка с адресом."""
    seed(layer)
    # У остальных каналов подписчики и охват растут вместе, и по обеим
    # сортировкам порядок вышел бы один. Этот канал разводит их: по подписчикам
    # он последний, по охвату первый.
    layer.channel(7, "tg", "ch7", subscribers=5_000, views_organic=99_000)
    layer.go_live()

    body = client.get("/?sort=views").text
    assert 'href="/?sort=views"' not in body, "текущая сортировка не ссылается сама на себя"
    assert '<a class="sbtn' in body
    assert body.index("/tg/ch7") < body.index("/tg/ch6"), "по охвату первым идёт ch7"

    default = client.get("/").text
    assert default.index("/tg/ch6") < default.index("/tg/ch7"), "по подписчикам ch7 последний"


def test_removed_sorts_are_not_offered_and_their_addresses_lead_home(layer, client):
    """Коэффициент охвата и свежесть убраны решением PO 03.09 (T-86). Плиток в
    интерфейсе нет, а старые адреса не 404, а 301 на канонический: с ними
    приходят из закладок и из чужих ссылок."""
    seed(layer).go_live()
    body = client.get("/").text
    assert "по коэффициенту охвата" not in body and "по свежести" not in body

    for gone in ("coverage", "fresh"):
        r = client.get(f"/?sort={gone}", follow_redirects=False)
        assert r.status_code == 301 and r.headers["location"] == "/"


def test_unknown_sort_is_not_a_page_but_a_normalised_address(layer, client):
    seed(layer).go_live()
    r = client.get("/?sort=nonsense", follow_redirects=False)
    assert r.status_code == 301 and r.headers["location"] == "/"


def test_default_sort_spelled_out_redirects_to_the_bare_address(layer, client):
    """`?sort=subscribers` и `/` это один список: адрес у него один."""
    seed(layer).go_live()
    r = client.get("/?sort=subscribers", follow_redirects=False)
    assert r.status_code == 301 and r.headers["location"] == "/"


# ── состояние переживает переходы ────────────────────────────────────────────

def test_filter_survives_the_move_to_the_second_page(layer, make_client):
    for i in range(1, 8):
        layer.channel(i, "tg", f"ch{i}", subscribers=i * 10_000)
    layer.go_live()

    small = make_client(page_size=2)
    r = small.get("/?subs_min=20000&page=2")
    assert r.status_code == 200
    assert "subs_min=20000&page=3" in plain(r.text), "ссылки страниц потеряли фильтр"


def test_sort_and_filter_live_in_the_same_address(layer, client):
    seed(layer).go_live()
    body = client.get("/?subs_min=20000&sort=views").text
    assert names(body) == {"ch2", "ch3", "ch4", "ch5", "ch6"}
    # Сортировка переживает отправку формы скрытым полем, фильтр переезжает в
    # ссылки сортировки: одно состояние — один адрес, и он не рассыпается.
    # Соседняя плитка здесь — умолчание, поэтому ключа `sort` в её адресе нет,
    # а фильтр в нём остаться обязан.
    assert '<input type="hidden" name="sort" value="views">' in body
    assert 'href="/?subs_min=20000"' in plain(body)


# ── пустая выдача ────────────────────────────────────────────────────────────

def test_empty_result_offers_a_way_back(layer, client):
    seed(layer).go_live()
    body = client.get("/?subs_min=999999999").text
    assert "ничего не подошло" in body
    assert 'href="/"' in body


def test_from_greater_than_to_is_an_empty_result_not_an_error(layer, client):
    seed(layer).go_live()
    r = client.get("/?subs_min=50000&subs_max=10000")
    assert r.status_code == 200 and "ничего не подошло" in r.text


# ── адреса ───────────────────────────────────────────────────────────────────

def test_filtered_page_is_closed_from_the_index_but_open_for_crawling(layer, client, make_client):
    seed(layer).go_live()
    open_site = make_client(noindex=False)
    r = open_site.get("/?subs_min=20000")
    assert r.headers["X-Robots-Tag"] == "noindex, follow"
    assert 'rel="canonical" href="' in r.text
    assert "subs_min" not in r.text.split('rel="canonical"')[1].split(">")[0]


def test_filter_links_are_closed_from_crawling(layer, client, make_client):
    """Краулеру в фильтрах делать нечего: он туда не ходит, и лимит запросов его
    не задевает. Иначе обход ушёл бы в четыре варианта сортировки на каждую из
    2 700 страниц каталога."""
    seed(layer).go_live()
    body = make_client(noindex=False).get("/").text
    links = [chunk for chunk in body.split("<a ") if 'class="sbtn' in chunk.split(">")[0]]
    assert links, "ссылок сортировки нет вовсе"
    assert all('rel="nofollow"' in link.split(">")[0] for link in links)


def test_robots_txt_closes_filters_by_key_not_by_any_query(layer, client, make_client):
    """Шаблон на любую строку запроса накрыл бы `?page`, то есть единственный
    путь краулера к 140 тысячам страниц."""
    seed(layer).go_live()
    body = make_client(noindex=False).get("/robots.txt").text
    assert "Disallow: /*?*sort=" in body
    assert "Disallow: /*?*subs_min=" in body
    assert "?page" not in body


@pytest.mark.parametrize("url,where", [
    ("/?subs_max=45000&subs_min=25000", "/?subs_min=25000&subs_max=45000"),
    ("/?subs_min=&sort=views", "/?sort=views"),
    ("/?subs_min=abc", "/"),
    ("/?utm_source=mail", "/"),
])
def test_the_same_meaning_has_a_single_address(layer, client, url, where):
    """Переставленные ключи, пустые поля формы, мусор и чужие метки — это всё
    один и тот же список, и адрес у него один."""
    seed(layer).go_live()
    r = client.get(url, follow_redirects=False)
    assert r.status_code == 301 and r.headers["location"] == where


def test_values_outside_the_range_are_clipped_not_rejected(layer, client):
    seed(layer).go_live()
    r = client.get("/?ads_max=150&subs_min=-5", follow_redirects=False)
    assert r.status_code == 301 and r.headers["location"] == "/?ads_max=100"


def test_broken_page_number_is_still_404_not_a_redirect(layer, client):
    """404 сильнее 301: у номера страницы мусор означает несуществующую
    страницу, а не «условие не задано»."""
    seed(layer).go_live()
    assert client.get("/?page=abc").status_code == 404
    assert client.get("/?page=0").status_code == 404
    assert client.get("/?page=99&subs_min=20000").status_code == 404


def test_page_number_is_checked_before_the_filter_is_normalised(layer, client):
    """Иначе адрес с мусором в двух местах сначала редиректится, потом отдаёт
    404 — два ответа там, где нужен один."""
    seed(layer).go_live()
    assert client.get("/?page=abc&subs_max=10000&subs_min=1", follow_redirects=False
                      ).status_code == 404


# ── площадка плюс тематика ───────────────────────────────────────────────────

def test_category_can_be_added_inside_a_platform_section(layer, client):
    seed(layer)
    layer.category(2, "Еда", "eda")
    layer.channel(7, "vk", "vk1", subscribers=1000)
    layer.category(7, "Еда", "eda")
    layer.go_live()

    body = client.get("/tg?cat=eda").text
    assert names(body) == {"ch2"}
    assert "vk1" not in body


def test_platform_chosen_inside_a_category_section_redirects_to_the_platform(layer, client):
    """Пара несимметрична намеренно: иначе у одного списка два адреса."""
    seed(layer)
    layer.category(2, "Еда", "eda")
    layer.go_live()
    r = client.get("/category/eda?platform=tg", follow_redirects=False)
    assert r.status_code == 301 and r.headers["location"] == "/tg?cat=eda"


def test_category_section_says_how_many_channels_have_a_category(layer, client):
    """Под фильтром по тематике три четверти каталога исчезают: без этой строки
    пропажа выглядит поломкой."""
    seed(layer)
    layer.category(2, "Еда", "eda")
    layer.go_live(channels_total=140_015, categories_covered=35_597)

    body = client.get("/category/eda").text.replace("\xa0", " ").replace(" ", " ")
    assert "35 597" in body and "140 015" in body


# ── мёртвая метрика ──────────────────────────────────────────────────────────

def test_er_is_not_shown_while_almost_nobody_has_it(layer, client):
    seed(layer).go_live(channels_total=140_015, er_covered=37)
    body = client.get("/").text
    assert "ER" not in body


def test_er_comes_back_by_itself_once_the_coverage_crosses_a_half(layer, client):
    """Порог, а не вырезание: починят расчёт — метрика появится без правки кода."""
    seed(layer).go_live(channels_total=140_015, er_covered=90_000)
    assert "ER" in client.get("/").text
