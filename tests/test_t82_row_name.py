"""T-82: длинное имя канала обрезается по своей колонке, цифры метрик ровно.

Геометрия меряется браузером и в pytest не переносится: здесь, как в T-77,
стоят контракты правил — сломается любой, и вернётся ровно тот дефект, из-за
которого задача заведена (имя печаталось поверх лейблов метрик, а значения в
колонках сидели на разной высоте).

Стили читаются через сервис (`/assets/components.css`), а не с диска.
"""
import re

import pytest

pytestmark = pytest.mark.integration

# Имя, на котором PO поймал наезд 02.09 (длина того же порядка, само имя своё).
LONG_NAME = "Вселенная кино 2026 | Человек-паук Новый день и премьеры всего года"


@pytest.fixture
def css(client):
    body = client.get("/assets/components.css")
    assert body.status_code == 200
    return body.text


def _rule(css: str, selector: str) -> str:
    """Все объявления селектора, включая правила, где он стоит в общем списке.

    Тот же хелпер, что в `test_t77_mobile.py`. Внутрь `@media` он не заглядывает:
    для медиаблока головой подбирается сам `@media`, поэтому правила из него
    сюда не попадают — это здесь свойство полезное, база отделена от сброса.
    """
    body = ""
    bare = re.sub(r"/\*.*?\*/", " ", css, flags=re.S)
    for heads, decls in re.findall(r"([^{}]+)\{([^}]*)\}", bare):
        if selector in [one.strip() for one in heads.split(",")]:
            body += decls + ";"
    assert body, f"правила `{selector}` нет в components.css"
    return body


def _media_bodies(css: str, condition: str):
    """Тела всех `@media` с указанным условием и позиция начала каждого.

    Своя разборка нужна потому, что `_rule` в медиаблок не заходит, а проверить
    надо обе половины сброса: что он есть и что он стоит в файле ниже базового
    правила. Специфичность у базы и сброса одна, медиазапрос её не поднимает —
    решает порядок, и правило, вытащенное выше базы, окажется мёртвым.
    Не заменять этот разбор на `_rule`: тест позеленеет на неработающем CSS.
    """
    out = []
    for head in re.finditer(r"@media\s*([^{]+)\{", css):
        if condition not in " ".join(head.group(1).split()):
            continue
        depth, i = 1, head.end()
        while depth and i < len(css):
            if css[i] == "{":
                depth += 1
            elif css[i] == "}":
                depth -= 1
            i += 1
        out.append((head.start(), css[head.end():i - 1]))
    return out


# ── имя обрезается по своей колонке ─────────────────────────────────────────

def test_name_link_clips_itself(css):
    """Обрезка обязана стоять на флекс-элементе `a`: на строчном `b` из четырёх
    свойств работало одно `nowrap`, и имя распирало колонку."""
    rule = _rule(css, ".name > a")
    assert re.search(r"min-width:\s*0", rule), "без min-width: 0 ссылка не сожмётся"
    assert re.search(r"overflow:\s*hidden", rule)
    assert re.search(r"text-overflow:\s*ellipsis", rule)
    assert re.search(r"white-space:\s*nowrap", rule)


def test_second_line_of_the_row_wraps_anywhere(css):
    """Во вторую строку печатается логин — токен без пробелов. Правило адресное:
    класс `.sub` носят шесть разных мест."""
    assert re.search(r"overflow-wrap:\s*anywhere", _rule(css, ".row-name .sub"))


# ── цифры метрик стоят на одной высоте ──────────────────────────────────────

def test_metric_in_a_row_reserves_rows_for_the_label(css):
    """Свободная колонка сажала значение в каждой метрике на свою высоту.
    Резерв — сеткой, две строки: подписи под значением в строке выдачи нет."""
    rule = _rule(css, ".m-cols .m")
    assert re.search(r"display:\s*grid", rule)
    assert "grid-template-rows" in rule


def test_metric_reserve_is_dropped_below_1200_and_the_reset_stands_lower(css):
    """Ниже 1200 px блок метрик перестаёт быть 400 px и резерв даёт пустую
    строку под каждым лейблом. Проверяются обе половины: сброс есть и стоит в
    файле ниже базового правила."""
    bare = re.sub(r"/\*.*?\*/", " ", css, flags=re.S)
    base = re.search(r"\.m-cols \.m\s*\{", bare)
    assert base, "базового правила `.m-cols .m` нет"
    resets = [pos for pos, body in _media_bodies(bare, "max-width: 1200px")
              if re.search(r"\.m-cols \.m\s*\{[^}]*display:\s*flex", body)]
    assert resets, "резерв не сброшен ниже 1200 px"
    assert max(resets) > base.start(), (
        "сброс стоит в файле выше базового правила — специфичность одна, "
        "и такой сброс мёртв")


# ── страница каталога ───────────────────────────────────────────────────────

def test_name_link_carries_a_title(layer, client):
    layer.channel(1, "tg", "example_channel")
    layer.go_live()
    body = client.get("/").text
    assert re.search(r'<a href="/tg/example_channel"\s+title="Канал example_channel">', body),         "у ссылки имени нет подсказки с полным названием"


def test_title_holds_the_whole_name(layer, client):
    """Длину строки в шаблоне не измерить, обрезка идёт в браузере — сервер
    имя не режет, иначе подсказка показывала бы тот же обрезок."""
    layer.channel(1, "tg", "example_channel", display_name=LONG_NAME)
    layer.go_live()
    body = client.get("/").text
    assert f'title="{LONG_NAME}"' in body, "в подсказке имя обрезано на сервере"
    assert f"<b>{LONG_NAME}</b>" in body, "в самой ссылке имя обрезано на сервере"
