"""T-124: описание канала вернулось в шапку, свёрнутое до одной строки.

T-120 унесла описание в конец шапки, под плитки и тематики: в нём лежал
контакт «по рекламе @…» выше нашей кнопки. Контакт снял фильтр, а не место, и
после приёмки глазами 22.09 PO вернул описание наверх, рядом с аватаром.

Рядом с аватаром помещается ровно одна строка: заголовок 21 px, подпись и
строка описания дают ~68 px из 72. Поэтому длинное описание свёрнуто в
`<details>` с многоточием и подсказкой «ещё», а короткое остаётся обычным
абзацем — разворачивать в нём нечего. Порог один и телефонный: на 390 px в
строку рядом с аватаром ложится 30-35 символов, взято 28.

Геометрия браузером здесь не меряется (её проверяет PO глазами по DoD) —
стоят контракты на разметку и на сами правила, которые эту геометрию держат.
"""
import re

import pytest

pytestmark = pytest.mark.integration


# ── разметка ─────────────────────────────────────────────────────────────────

DETAILS = re.compile(r'<details class="desc">(.*?)</details>', re.S)
PARAGRAPH = re.compile(r'<p class="desc">(.*?)</p>', re.S)
DESC_TEXT = re.compile(r'<span class="desc-text">(.*?)</span>', re.S)

#: Наполнитель, которого фильтр T-120 не касается: ни маркера, ни контакта.
FILLER = "Канал про кино и музыку каждый день новые обзоры и подборки "


def desc_of_length(n: int) -> str:
    """Описание ровно в n символов, которое `clip` не укорачивает.

    Длина считается по тому, что выводится, то есть после `strip_ad_contacts`
    и `clip(400)`. Срез не должен попасть на пробел, иначе `clip` схлопнет его
    и тест начнёт мерить не ту цифру — отсюда проверка внутри.
    """
    text = (FILLER * 20)[:n]
    if text.endswith(" "):
        text = text[:-1] + "."
    assert len(" ".join(text.split())) == n, f"текст в {n} символов не пережил clip"
    return text


def test_long_description_is_collapsed_into_details(layer, client):
    text = desc_of_length(120)
    layer.channel(1, "tg", "kittens", description=text)
    layer.go_live()
    body = client.get("/tg/kittens").text

    inside = DETAILS.search(body)
    assert inside, "длинное описание не свёрнуто в `<details class=\"desc\">`"
    assert "<summary>" in inside.group(1), "у `<details>` нет `<summary>`"
    held = DESC_TEXT.search(inside.group(1))
    assert held, "текст описания не завёрнут в `<span class=\"desc-text\">` — обрезать нечего"
    assert held.group(1).strip() == text
    assert PARAGRAPH.search(body) is None, "описание задвоилось абзацем"


def test_short_description_stays_a_plain_paragraph(layer, client):
    text = desc_of_length(20)
    layer.channel(1, "tg", "kittens", description=text)
    layer.go_live()
    body = client.get("/tg/kittens").text

    inside = PARAGRAPH.search(body)
    assert inside, "короткое описание не абзац"
    assert inside.group(1).strip() == text
    assert DETAILS.search(body) is None, "короткое описание нечего разворачивать"
    assert "desc-text" not in body


@pytest.mark.parametrize("length, collapsed", [(28, False), (29, True)])
def test_threshold_is_checked_from_both_sides(layer, client, length, collapsed):
    """Порог 28: ровно 28 символов — абзац, 29 — уже свёртка."""
    layer.channel(1, "tg", "kittens", description=desc_of_length(length))
    layer.go_live()
    body = client.get("/tg/kittens").text
    assert bool(DETAILS.search(body)) is collapsed
    assert bool(PARAGRAPH.search(body)) is not collapsed


def test_branch_is_chosen_by_the_clipped_text(layer, client):
    """Ветка выбирается по тому, что выводится, а не по сырой строке.

    `clip` схлопывает пробелы и переносы: описание в 30 символов до него и в
    23 после обязано остаться абзацем, иначе у каждого описания с переносами
    в шапке заведётся подсказка «ещё» на пустом месте.
    """
    raw = "Канал про кино\n\n\n     и музыку"
    assert len(raw) > 28 and len(" ".join(raw.split())) <= 28
    layer.channel(1, "tg", "kittens", description=raw)
    layer.go_live()
    body = client.get("/tg/kittens").text

    inside = PARAGRAPH.search(body)
    assert inside, "описание, короткое после клипа, свернули в `<details>`"
    assert inside.group(1).strip() == "Канал про кино и музыку"


def test_filtered_and_clipped_text_goes_into_the_collapsed_line(layer, client):
    """Внутри свёртки — текст после фильтра T-120 и клипа на 400."""
    layer.channel(1, "tg", "kittens",
                  description=desc_of_length(500) + " Реклама: @manager")
    layer.go_live()
    body = client.get("/tg/kittens").text

    shown = DESC_TEXT.search(DETAILS.search(body).group(1)).group(1).strip()
    assert "@manager" not in body
    assert shown.startswith("Канал про кино")
    assert shown.endswith("…"), "клипа на 400 не видно"
    assert len(shown) <= 401


def test_sibling_description_collapses_the_same_way(layer, client):
    """Шаблон один: у соседа шапка ведёт себя как у основного канала."""
    layer.channel(1, "tg", "main_channel", blogger_id=7, blogger_has_siblings=True,
                  description=desc_of_length(20))
    layer.channel(2, "vk", "vk_page", blogger_id=7, blogger_has_siblings=True,
                  description=desc_of_length(120))
    layer.sibling(1, 2)
    layer.sibling(2, 1)
    layer.go_live()
    body = client.get("/tg/main_channel").text

    assert len(PARAGRAPH.findall(body)) == 1
    assert len(DETAILS.findall(body)) == 1


# ── стиль ────────────────────────────────────────────────────────────────────
#
# Хелперы продублированы из `test_t77_mobile` и `test_t121_mobile_invite`
# намеренно: вынос в `conftest` потребовал бы правок в тех файлах, а они по
# T-124 остаются нетронутыми.

@pytest.fixture
def css(client):
    body = client.get("/assets/components.css")
    assert body.status_code == 200
    return re.sub(r"/\*.*?\*/", " ", body.text, flags=re.S)


def _rule(css: str, selector: str) -> str:
    """Все объявления селектора, включая правила, где он стоит в общем списке.

    Внутрь `@media` хелпер попадает только для правил, стоящих в блоке не
    первыми: у первого голова `@media (...)` съедает и сам селектор. На этом
    держится проверка десктопного отступа `.ch-block + .ch-block` ниже.
    """
    body = ""
    for heads, decls in re.findall(r"([^{}]+)\{([^}]*)\}", css):
        if selector in [one.strip() for one in heads.split(",")]:
            body += decls + ";"
    assert body, f"правила `{selector}` нет"
    return body


def _media_860(css: str) -> str:
    """Тело всех медиазапросов `max-width: 860px` одной строкой."""
    blocks = []
    for m in re.finditer(r"@media\s*\(max-width:\s*860px\)\s*\{", css):
        depth, i = 1, m.end()
        while depth and i < len(css):
            depth += {"{": 1, "}": -1}.get(css[i], 0)
            i += 1
        blocks.append(css[m.end():i - 1])
    assert blocks, "медиазапроса 860px в components.css нет"
    return "\n".join(blocks)


def test_head_is_a_grid_with_a_column_for_the_avatar(css):
    """Флекс с вложенной колонкой не даёт описанию встать и рядом с аватаром,
    и под ним. Сетка даёт, но row-gap обязан остаться нулевым: 16 px между
    подписью и описанием сразу ломают бюджет 72 px."""
    rule = _rule(css, ".top")
    assert re.search(r"display\s*:\s*grid", rule)
    assert re.search(r"grid-template-columns\s*:\s*72px", rule), \
        "первая колонка шапки не по аватару 72 px"
    assert "column-gap" in rule
    assert not re.search(r"(?<![-\w])gap\s*:", rule), \
        "у `.top` голый `gap` — между подписью и описанием встанет отступ"


def test_title_shrinks_and_the_sibling_heading_matches_it(css):
    """Заголовок с 30 px на 21 px, и поля `h2` обнуляются: без этого дефолтные
    ~17 px сверху и снизу не дадут шапке соседа уложиться в 72 px."""
    for selector in (".title h1", ".title h2"):
        assert re.search(r"font-size\s*:\s*var\(--fs-h2\)", _rule(css, selector)), \
            f"у `{selector}` не 21 px"
    assert re.search(r"margin\s*:\s*0", _rule(css, ".title h2"))


def test_sibling_heading_wraps_anywhere(css):
    """У `h1` защита от длинного неразрывного имени есть с T-77, у соседа не было."""
    assert "anywhere" in _rule(css, ".title h2")


def test_collapsed_line_is_cut_with_an_ellipsis(css):
    """Обрезка живёт на `.desc-text`, а не на `summary`: `summary` —
    флекс-контейнер, `text-overflow` на нём к детям не применяется."""
    rule = _rule(css, "details.desc .desc-text")
    assert re.search(r"white-space\s*:\s*nowrap", rule)
    assert re.search(r"text-overflow\s*:\s*ellipsis", rule)


def test_open_state_puts_the_hint_under_the_text(css):
    """«Свернуть» в развороте стоит отдельной строкой под текстом (решение PO)."""
    assert re.search(r"flex-direction\s*:\s*column",
                     _rule(css, "details.desc[open] > summary"))


def test_open_state_lets_the_text_wrap(css):
    """Без возврата `white-space` в `normal` разворот не сработает вовсе:
    текст останется одной неразрывной строкой и утащит страницу вбок."""
    assert re.search(r"white-space\s*:\s*normal",
                     _rule(css, "details.desc[open] .desc-text"))


def test_hint_says_more_and_then_collapse(css):
    assert re.search(r'content\s*:\s*"ещё"', _rule(css, "details.desc > summary::after"))
    assert re.search(r'content\s*:\s*"свернуть"',
                     _rule(css, "details.desc[open] > summary::after"))


def test_details_marker_is_hidden(css):
    """Приём тот же, что у `.side-mobile` и `.cats-more`: треугольника нет."""
    assert re.search(r"list-style\s*:\s*none", _rule(css, "details.desc > summary"))
    assert "details.desc > summary::-webkit-details-marker" in css


# ── телефон ──────────────────────────────────────────────────────────────────

def test_open_description_spans_the_card_on_a_phone(css):
    """Развёрнутое описание уходит под аватар на всю ширину карточки: справа
    от аватара ему на 390 px не хватает места. В свёрнутом виде остаётся
    справа."""
    rule = _rule(_media_860(css), ".top > details.desc[open]")
    assert re.search(r"grid-column\s*:\s*1\s*/\s*-1", rule)
    assert re.search(r"grid-row\s*:\s*3", rule)
    assert re.search(r"margin-top\s*:\s*var\(--sp-3\)", rule)


def test_head_buttons_share_one_row_on_a_phone(css):
    """Кнопки шапки одной строкой и одной высоты. `white-space: nowrap`
    обязателен: без него третья кнопка у соседа не переносится на вторую
    строку, а схлопывает первую."""
    rule = _rule(_media_860(css), ".actions > .btn")
    for expected in (r"flex\s*:\s*1 1 0",
                     r"height\s*:\s*auto",
                     r"min-height\s*:\s*44px",
                     r"justify-content\s*:\s*center",
                     r"align-items\s*:\s*center",
                     r"text-align\s*:\s*center",
                     r"padding-inline\s*:\s*var\(--sp-3\)",
                     r"white-space\s*:\s*nowrap"):
        assert re.search(expected, rule), f"у `.actions > .btn` нет `{expected}`"


def test_sibling_label_sits_closer_on_a_phone(css):
    """Надпись «Ещё одна площадка автора» на телефоне отбивается от панели
    заказа тем же шагом, что и от карточки соседа снизу. На десктопе шаг
    прежний."""
    assert re.search(r"margin-top\s*:\s*var\(--sp-4\)",
                     _rule(_media_860(css), ".ch-block + .ch-block"))
    wide = _rule(css, ".ch-block + .ch-block")
    assert re.search(r"margin-top\s*:\s*var\(--sp-6\)", wide)
    assert "--sp-4" not in wide, \
        "мобильный отступ виден снаружи медиазапроса — правило в блоке 860 px " \
        "перестало быть первым, и `_rule` стал его замечать"
