"""T-65: площадки автора полными блоками и пагинация ленты.

Решение PO 27.07, подтверждённое 20.08: табов нет, площадки автора выводятся
целиком вертикальным скроллом. В T-61 они собрались строкой чипсов — это дефект
приёмки, а не смена рамок.

Лента при этом пагинируется (решение PO 20.08, отменяет «пагинации ленты нет» от
11.08): 10 постов и кнопка «Ещё» обычной ссылкой. Клиентского JS на сайте нет,
поэтому «прогрузить ещё» означает открыть следующий адрес.
"""
import pytest

pytestmark = pytest.mark.integration


def family(layer):
    """Автор с тремя площадками: две в базе, третья своей страницей."""
    main = layer.channel(1, "tg", "main_channel", subscribers=120_000, blogger_id=7,
                         blogger_has_siblings=True)
    vk = layer.channel(2, "vk", "vk_page", subscribers=48_000, blogger_id=7,
                       blogger_has_siblings=True, views_organic=9_000,
                       coverage_ratio=18.7, ad_share_30d=12.0)
    layer.sibling(1, 2)
    layer.sibling(2, 1)
    return main, vk


# ── полные блоки площадок ────────────────────────────────────────────────────

def test_sibling_platform_gets_a_full_block_not_a_chip(layer, client):
    """Плитки метрик, а не название со ссылкой: решение 27.07 про «целиком»."""
    family(layer)
    layer.post(2, "vp1", text="Пост во вконтакте про кухню")
    layer.history(2, [("2026-05-01", 40_000), ("2026-06-01", 44_000),
                      ("2026-07-01", 48_000)])
    layer.advertiser(2, "ООО «Соседи»", inn="7712345678")
    layer.go_live()

    body = client.get("/tg/main_channel").text
    assert "48 000" in body.replace("\xa0", " ").replace(" ", " "), "нет метрик соседа"
    assert "про кухню" in body, "нет ленты соседа"
    assert "ООО «Соседи»" in body, "нет рекламодателей соседа"
    assert "Динамика подписчиков" in body


def test_platforms_are_stacked_with_anchors_and_no_tabs(layer, client):
    family(layer)
    layer.go_live()
    body = client.get("/tg/main_channel").text
    assert 'id="ch-2"' in body and 'href="#ch-2"' in body
    assert "role=\"tab\"" not in body


def test_sibling_block_promises_only_what_we_have(layer, client):
    """Дзен, инстаграм и тикток в дамп не попадают вовсе, часть площадок автора
    не появится никогда. Подпись это признаёт, а не обещает все."""
    family(layer)
    layer.go_live()
    assert "в нашей базе" in client.get("/tg/main_channel").text


def test_single_channel_has_no_platforms_block_at_all(layer, client):
    layer.channel(1, "tg", "lonely")
    layer.go_live()
    body = client.get("/tg/lonely").text
    assert "площадки автора" not in body.lower()


def test_sibling_block_links_to_its_own_page(layer, client):
    family(layer)
    layer.go_live()
    assert '/vk/vk_page' in client.get("/tg/main_channel").text


# ── пагинация ленты ──────────────────────────────────────────────────────────

def feed_of(layer, cid, n):
    for i in range(n):
        layer.post(cid, f"p{i}", text=f"Публикация номер {i}", days_ago=i)


def test_feed_shows_ten_posts_and_offers_more(layer, client):
    layer.channel(1, "tg", "talky")
    feed_of(layer, 1, 25)
    layer.go_live()

    body = client.get("/tg/talky").text
    assert body.count("Публикация номер") == 10
    assert "?posts=2#feed" in body, "кнопка «Ещё» без якоря вернёт на верх страницы"


def test_second_page_of_the_feed_continues_the_same_channel(layer, client):
    layer.channel(1, "tg", "talky")
    feed_of(layer, 1, 25)
    layer.go_live()

    body = client.get("/tg/talky?posts=2").text
    assert "Публикация номер 10" in body and "Публикация номер 0" not in body


def test_last_page_of_the_feed_offers_nothing_more(layer, client):
    layer.channel(1, "tg", "talky")
    feed_of(layer, 1, 12)
    layer.go_live()
    assert "posts=2" not in client.get("/tg/talky?posts=2").text


def test_feed_page_beyond_the_last_is_404_not_an_empty_page(layer, client):
    """`posts` это номер страницы: мусор в нём означает несуществующую страницу,
    как и у `page`, то есть 404, а не редирект."""
    layer.channel(1, "tg", "talky")
    feed_of(layer, 1, 12)
    layer.go_live()

    assert client.get("/tg/talky?posts=9").status_code == 404
    assert client.get("/tg/talky?posts=abc").status_code == 404
    assert client.get("/tg/talky?posts=0").status_code == 404


def test_first_page_of_the_feed_spelled_out_redirects_to_the_bare_address(layer, client):
    layer.channel(1, "tg", "talky")
    feed_of(layer, 1, 12)
    layer.go_live()
    r = client.get("/tg/talky?posts=1", follow_redirects=False)
    assert r.status_code == 301 and r.headers["location"] == "/tg/talky"


def test_feed_pages_are_closed_from_the_index_and_point_at_the_channel(layer, client,
                                                                       make_client):
    layer.channel(1, "tg", "talky")
    feed_of(layer, 1, 25)
    layer.go_live()

    r = make_client(noindex=False).get("/tg/talky?posts=2")
    assert r.headers["X-Robots-Tag"] == "noindex, follow"
    assert 'rel="canonical" href="https://fomobase.ru/tg/talky"' in r.text


def test_sibling_feed_sends_the_reader_to_the_siblings_own_page(layer, client):
    """У соседа «Ещё» ведёт на его страницу, а не на следующую страницу этой:
    адрес у него уже есть, новые плодить незачем."""
    family(layer)
    feed_of(layer, 2, 25)
    layer.go_live()

    body = client.get("/tg/main_channel").text
    assert "/vk/vk_page?posts=2" not in body
    assert '/vk/vk_page' in body


def test_channel_page_has_no_script_tag(layer, client):
    """«Ещё» это ссылка, а не подгрузка: шов 3 не ослабляется."""
    family(layer)
    feed_of(layer, 1, 25)
    layer.go_live()
    assert "<script" not in client.get("/tg/main_channel").text


# ── мёртвая метрика ──────────────────────────────────────────────────────────

def test_er_tile_is_hidden_while_the_coverage_is_tiny(layer, client):
    layer.channel(1, "tg", "example_channel", er_percent=4.2)
    layer.go_live(channels_total=140_015, er_covered=37)
    assert "4,2" not in client.get("/tg/example_channel").text


def test_er_tile_returns_once_the_coverage_crosses_a_half(layer, client):
    layer.channel(1, "tg", "example_channel", er_percent=4.2)
    layer.go_live(channels_total=140_015, er_covered=90_000)
    assert "4,2" in client.get("/tg/example_channel").text
