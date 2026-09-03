"""T-68.1: колонка фильтров со своей прокруткой, действия строки — вбок.

Раскладку CSS тест не проверяет: он держит разметочные швы, без которых
правка молча разъедется обратно — метрики общим блоком, действия отдельной
ячейкой строки, подвал колонки фильтров отдельным блоком, текст пустой
выдачи внутри строки.
"""
import re

import pytest

from conftest import assert_metrika_is_the_only_script

pytestmark = pytest.mark.integration


def test_metrics_live_in_one_block_not_as_row_children(layer, client):
    layer.channel(1, "tg", "example_channel")
    layer.go_live()
    body = client.get("/").text
    assert 'class="m-cols"' in body, "метрики обязаны лежать общим блоком"
    # все метрики строки лежат внутри блока и ни одной снаружи
    block = re.search(r'<div class="m-cols">(.*?)</div>\s*<div class="row-actions"', body, re.S)
    assert block, "блок метрик не найден"
    inside = block.group(1).count('class="m"')
    assert inside >= 4
    assert body.count('class="m"') == inside, "метрика осталась прямым ребёнком строки"


def test_actions_left_the_text_block_and_stand_as_their_own_cell(layer, client):
    layer.channel(1, "tg", "example_channel", wowblogger_slug="some-blogger")
    layer.go_live()
    body = client.get("/").text
    name_cell = re.search(r'<div class="row-name">(.*?)\n    </div>', body, re.S)
    assert name_cell, "текстовая зона строки не найдена"
    assert "row-actions" not in name_cell.group(1), "действия остались внутри текста строки"
    assert 'class="row-actions"' in body
    # порядок ячеек: имя, метрики, действия
    assert body.index('class="row-name"') < body.index('class="m-cols"') < body.index('class="row-actions"')


def test_place_button_is_accented(layer, client):
    layer.channel(1, "tg", "example_channel", wowblogger_slug="some-blogger")
    layer.go_live()
    body = client.get("/").text
    assert "btn--primary btn--sm" in body
    assert "btn--ghost btn--sm" not in body


def test_spacer_column_is_gone(layer, client):
    layer.channel(1, "tg", "example_channel")
    layer.go_live()
    assert "<span></span>" not in client.get("/").text


def test_empty_result_text_stays_inside_the_row(layer, client):
    layer.channel(1, "tg", "example_channel")
    layer.go_live()
    body = client.get("/?subs_min=999999999").text
    assert "Под эти условия ничего не подошло" in body
    assert 'class="row"><span class="none">' in body


def test_filter_column_has_a_footer_block(layer, client):
    layer.channel(1, "tg", "example_channel")
    layer.go_live()
    body = client.get("/").text
    # подвал есть в обеих разметках формы — десктопной и мобильной
    assert body.count('class="side-foot"') == 2
    foot = re.search(r'<div class="side-foot">(.*?)</div>', body, re.S)
    assert "Показать" in foot.group(1)


def test_no_client_side_script_but_metrika_appeared(layer, client):
    layer.channel(1, "tg", "example_channel")
    layer.go_live()
    assert_metrika_is_the_only_script(client.get("/").text)
