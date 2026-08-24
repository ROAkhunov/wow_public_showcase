"""T-66: разбор скриншотов PO 23.08 — возвращённые в каталог площадки автора и
действия строки, тематика и площадка в колонке фильтров, правая колонка канала.

Раскладка меняется, контракт данных — нет: тесты касаются только вида,
которого не было в T-61/T-65 (или который у них по ошибке пропал).
"""
import pytest

pytestmark = pytest.mark.integration


# ── строка каталога: соседи, «Разместить», «Неточность?» ────────────────────

def test_sibling_squares_link_to_their_pages_with_a_count(layer, client):
    layer.channel(1, "tg", "main_channel", blogger_id=7, blogger_has_siblings=True)
    layer.channel(2, "vk", "vk_page", blogger_id=7, blogger_has_siblings=True)
    layer.sibling(1, 2)
    layer.sibling(2, 1)
    layer.go_live()

    body = client.get("/").text
    assert "/vk/vk_page" in body
    assert "ещё 1 у автора" in body


def test_no_sibling_strip_without_siblings(layer, client):
    layer.channel(1, "tg", "lonely")
    layer.go_live()
    assert "у автора" not in client.get("/").text


def test_place_button_in_catalog_row_only_with_a_slug(layer, client):
    layer.channel(1, "tg", "listed_one", wowblogger_slug="vykhino-zhulebino-2")
    layer.channel(2, "tg", "stranger_one")
    layer.go_live()

    body = client.get("/").text
    assert "https://wowblogger.ru/bloggers/vykhino-zhulebino-2" in body
    assert body.count("wowblogger.ru") == 1, "кнопка не должна стоять у канала без слага"


def test_report_link_in_every_row(layer, client):
    layer.channel(1, "tg", "example_channel")
    layer.go_live()
    body = client.get("/").text.replace("&amp;", "&")
    assert "/report?platform=tg&channel=example_channel" in body
    assert "Неточность?" in body


# ── площадка и тематика в колонке фильтров ───────────────────────────────────

def test_platform_row_removed_from_the_header(layer, client):
    layer.channel(1, "tg", "example_channel")
    layer.go_live()
    body = client.get("/").text
    assert 'class="sections"' not in body


def test_category_strip_lives_in_the_filter_column_not_above_the_list(layer, client):
    layer.channel(1, "tg", "tagged")
    layer.category(1, "Еда", "eda")
    layer.go_live()

    body = client.get("/").text
    assert '<span class="ds-label">Тематика</span>' in body
    assert '/category/eda' in body


def test_thirteenth_category_hidden_behind_show_all(layer, client):
    """Двенадцать видны сразу, тринадцатая (и остальные) — под «Показать все»."""
    for i in range(13):
        cid = layer.channel(i + 1, "tg", f"ch{i}")
        # Больше каналов у категории — выше в списке по счёту (порядок в db.categories()).
        for n in range(13 - i):
            layer.channel(1000 + i * 100 + n, "tg", f"pad{i}_{n}")
            layer.category(1000 + i * 100 + n, f"Тема {i}", f"tema-{i}")
        layer.category(cid, f"Тема {i}", f"tema-{i}")
    layer.go_live()

    body = client.get("/").text
    assert "Показать все" in body
    before_details = body.split("<details class=\"cats-more\">")[0]
    assert "tema-12" not in before_details, "13-я тематика должна быть под деталями, не над"


def test_selected_category_stays_visible_even_when_far_down_the_list(layer, client):
    """Выбранная тематика видна всегда, даже если по счёту она в хвосте (DoD)."""
    for i in range(13):
        cid = layer.channel(i + 1, "tg", f"ch{i}")
        for n in range(13 - i):
            layer.channel(2000 + i * 100 + n, "tg", f"pad{i}_{n}")
            layer.category(2000 + i * 100 + n, f"Тема {i}", f"tema-{i}")
        layer.category(cid, f"Тема {i}", f"tema-{i}")
    layer.go_live()

    body = client.get("/category/tema-12").text
    before_details = body.split("<details class=\"cats-more\">")[0]
    assert 'href="/category/tema-12"' in before_details
    assert 'chip on" href="/category/tema-12"' in body


# ── правая колонка страницы канала, разброс охвата ───────────────────────────

def test_views_spread_tile_is_gone(layer, client):
    layer.channel(1, "tg", "example_channel", views_spread=18.0)
    layer.go_live()
    assert "Разброс охвата" not in client.get("/tg/example_channel").text


def test_channel_right_column_has_three_blocks_once(layer, client):
    layer.channel(1, "tg", "listed_one", wowblogger_slug="vykhino-zhulebino-2")
    layer.go_live()

    body = client.get("/tg/listed_one").text
    assert body.count("Разместить рекламу") == 1
    assert body.count("Нашли неточность?") == 1
    assert body.count("Данные обновлены") == 1


def test_right_column_absent_for_siblings_button_stays_in_their_header(layer, client):
    main = layer.channel(1, "tg", "main_channel", blogger_id=7, blogger_has_siblings=True)
    vk = layer.channel(2, "vk", "vk_page", blogger_id=7, blogger_has_siblings=True,
                       wowblogger_slug="sosed-slug")
    layer.sibling(1, 2)
    layer.sibling(2, 1)
    layer.go_live()

    body = client.get("/tg/main_channel").text
    # У соседа кнопка размещения в его шапке (правой колонки у него нет).
    assert "https://wowblogger.ru/bloggers/sosed-slug" in body
    assert body.count("Нашли неточность?") == 1, "карточка ОС только у основного канала"
