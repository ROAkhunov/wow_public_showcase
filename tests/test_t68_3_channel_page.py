"""T-68.3: страница канала — отступ плиток, выравнивание цифр, верхние кромки.

Раскладку CSS тест не проверяет: он держит разметочные швы, без которых правка
молча разъедется обратно — крошки над обеими колонками, оглавление площадок
двумя вставками, текущая площадка без ссылки, длинные имена обрезаны.
"""
import pytest

pytestmark = pytest.mark.integration


def family(layer, name_main="Канал main_channel", name_sib="Канал vk_page", **kw):
    layer.channel(1, "tg", "main_channel", subscribers=120_000, blogger_id=7,
                  blogger_has_siblings=True, display_name=name_main, **kw)
    layer.channel(2, "vk", "vk_page", subscribers=48_000, blogger_id=7,
                  blogger_has_siblings=True, display_name=name_sib)
    layer.sibling(1, 2)
    layer.sibling(2, 1)


# ── верхние кромки колонок ──────────────────────────────────────────────────

def test_breadcrumbs_stand_above_both_columns(layer, client):
    """Крошки внутри колонки опускали белую карточку на свою высоту, и правая
    колонка выглядела поднятой над основной."""
    layer.channel(1, "tg", "lonely")
    layer.go_live()
    body = client.get("/tg/lonely").text
    assert body.index('class="breadcrumbs"') < body.index('class="channel-layout"')


def test_platforms_block_left_the_main_column(layer, client):
    """Второй блок, поднимавший карточку: площадки автора уехали в правую
    колонку, в основной остаётся только скрытая на десктопе вставка."""
    family(layer)
    layer.go_live()
    body = client.get("/tg/main_channel").text
    assert 'class="group sites-nav-desktop"' in body
    main_column = body.split('<aside class="side channel-side">')[0]
    assert 'class="switch sites-nav-mobile"' in main_column, "мобильная вставка на месте"
    assert main_column.index('sites-nav-mobile') < main_column.index('class="ch-block"')


def test_platforms_group_stands_between_placement_and_feedback(layer, client):
    family(layer, wowblogger_slug="vykhino-zhulebino-2")
    layer.go_live()
    body = client.get("/tg/main_channel").text
    side = body.split('<aside class="side channel-side">')[1]
    assert side.index("Разместить рекламу") < side.index("Площадки автора") \
           < side.index("Нашли неточность?") < side.index("Данные обновлены")


# ── список площадок ─────────────────────────────────────────────────────────

def test_list_is_inserted_twice_and_only_twice(layer, client):
    """Две разметки, каждая скрыта на чужой ширине (приём `_filters.html`).
    Третьей вставки быть не должно: два видимых списка на одной ширине — это
    та самая каша, ради которой блок и переезжал."""
    family(layer)
    layer.go_live()
    body = client.get("/tg/main_channel").text
    assert body.count('class="sites-nav"') == 2
    assert body.count('href="#ch-2"') == 2


def test_current_platform_is_marked_but_is_not_a_link(layer, client):
    family(layer)
    layer.go_live()
    body = client.get("/tg/main_channel").text
    assert 'class="sn-row on"' in body
    assert 'href="#ch-1"' not in body, "ссылка «сюда же» в оглавлении не нужна"


def test_long_platform_name_is_clipped(layer, client):
    family(layer, name_main="Очень длинное название канала про всё на свете")
    layer.go_live()
    body = client.get("/tg/main_channel").text
    assert "Очень длинное название канала про всё на свете" in body, "в шапке имя целиком"
    assert "Очень длинное…" in body, "в списке площадок имя обрезано"


def test_subscribers_stand_in_the_list(layer, client):
    family(layer)
    layer.go_live()
    body = client.get("/tg/main_channel").text.replace("\xa0", " ")
    assert 'class="sn-subs">48 000' in body


def test_no_platform_list_without_siblings(layer, client):
    layer.channel(1, "tg", "lonely")
    layer.go_live()
    body = client.get("/tg/lonely").text
    assert "sites-nav" not in body
    assert "площадки автора" not in body.lower()


def test_no_client_side_code_appeared(layer, client):
    family(layer)
    layer.go_live()
    assert "<script" not in client.get("/tg/main_channel").text
