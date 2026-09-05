"""T-93: полоса прокрутки колонки фильтров не режет скругление рамки.

Дефект виден только на классической полосе (Windows, не overlay): дорожка
рисуется внутри padding-box, и её квадратный верх упирался в `border-radius`
формы — правый верхний угол карточки читался срезанным, а сама полоса стояла
вплотную к рамке. Лечится разделением ролей: внешняя коробка держит рамку и
обрезает по радиусу, содержимое прокручивается во внутренней обёртке.

Геометрия меряется браузером и в pytest не переносится — здесь стоят
контракты, на которых она держится, и запреты, снимающие два известных
капкана: прокрутку внутри прокрутки на телефоне и скрытую колонку, которую
`display` из этой правки способен вернуть на экран.

Стили читаются через сервис (`/assets/components.css`): наружу едет то, что
отдано.
"""
import re

import pytest

pytestmark = pytest.mark.integration


@pytest.fixture
def css(client):
    r = client.get("/assets/components.css")
    assert r.status_code == 200
    return r.text


def _rule(css: str, selector: str) -> str:
    """Все объявления селектора, включая правила, где он стоит в общем списке."""
    body = ""
    bare = re.sub(r"/\*.*?\*/", " ", css, flags=re.S)
    for heads, decls in re.findall(r"([^{}]+)\{([^}]*)\}", bare):
        if selector in [one.strip() for one in heads.split(",")]:
            body += decls + ";"
    assert body, f"правила `{selector}` нет в стилях"
    return body


# ── прокрутка съехала с формы во внутреннюю обёртку ──────────────────────────

def test_filter_form_clips_its_content_by_the_radius(css):
    """Рамка и обрезка остаются на форме: без `overflow: hidden` дорожка снова
    вылезет в скругление, ради чего задача и заведена."""
    body = _rule(css, ".side-desktop .side")
    assert re.search(r"overflow\s*:\s*hidden", body), \
        "форма не обрезает содержимое по радиусу — угол опять срежет"
    assert not re.search(r"overflow-y\s*:\s*auto", body), \
        "прокрутка вернулась на форму с рамкой — это и есть дефект T-93"


def test_filter_form_is_a_flex_column(css):
    """Колонка делится на прокручиваемую часть и подвал. Без flex-раскладки
    обёртка не узнает своей высоты, и `max-height` формы ничего не ограничит."""
    body = _rule(css, ".side-desktop .side")
    assert re.search(r"display\s*:\s*flex", body)
    assert re.search(r"flex-direction\s*:\s*column", body)
    assert re.search(r"max-height\s*:", body), \
        "без потолка высоты колонке нечего прокручивать"


def test_inner_wrapper_scrolls_and_can_shrink(css):
    """`min-height: 0` не украшение: flex-элемент по умолчанию не сжимается
    ниже содержимого, колонка вырастет за `max-height` и прокрутки не будет."""
    body = _rule(css, ".side-desktop .side-scroll")
    assert re.search(r"overflow-y\s*:\s*auto", body)
    assert re.search(r"min-height\s*:\s*0", body)


def test_footer_left_the_scrolled_area(css):
    """Подвал стоит нижней строкой колонки, а не липнет изнутри прокрутки: у
    липкости здесь больше нет скролл-порта, к которому липнуть."""
    body = _rule(css, ".side-desktop .side-foot")
    assert "sticky" not in body, \
        "подвал вынесен из прокрутки — липкость прилипнет к окну, а не к колонке"
    assert re.search(r"padding\s*:[^;]*var\(--sp-4\)", body), \
        "у `.side` снизу отступа нет, его держит подвал — иначе кнопка ляжет на рамку"


# ── капкан: прокрутка не должна протечь на телефон ───────────────────────────

def test_desktop_scroll_is_declared_only_through_the_desktop_column(css):
    """Страховка от лёгкого пути: селектор без `.side-desktop` накрыл бы и
    мобильную панель, и правую колонку канала — класс `.side` носят все трое."""
    bare = re.sub(r"/\*.*?\*/", " ", css, flags=re.S)
    for heads, _ in re.findall(r"([^{}]+)\{([^}]*)\}", bare):
        for one in heads.split(","):
            if ".side-scroll" in one:
                assert ".side-desktop" in one, \
                    f"`{one.strip()}` цепляет обёртку мимо десктопной колонки"


def test_channel_column_keeps_its_own_scrolling(css):
    """Правая колонка канала прокручивается штатно (решение PO 02.09) и в этой
    правке не участвует: обёртки в её разметке нет."""
    assert ".channel-side .side-scroll" not in css


# ── капкан: скрытая колонка не должна вернуться из-за display ────────────────

def test_hidden_column_outweighs_the_new_display(css):
    """`display: none` скрытой колонки и `display: flex` этой правки имели
    одинаковый вес, и решал порядок правил в файле — тот самый, который
    правкой ниже по файлу молча переворачивается."""
    heads = re.findall(r"([^{}]+)\{[^}]*display\s*:\s*none[^}]*\}",
                       re.sub(r"/\*.*?\*/", " ", css, flags=re.S))
    hiding = [one.strip() for head in heads for one in head.split(",")
              if "layout--off" in one and one.strip().endswith(".side")]
    assert hiding, "правило, скрывающее колонку фильтров, пропало"
    for one in hiding:
        assert one.count(".") >= 3, \
            f"`{one}` не перевешивает `.side-desktop .side` — скрытая колонка вернётся"


# ── разметка: обёртка есть в обеих формах, подвал вне её ─────────────────────

def test_both_forms_carry_the_wrapper(client, layer):
    """Разметок две — мобильная и десктопная, обе собираются одним макросом."""
    layer.channel(1, "tg", "example_channel")
    layer.go_live()

    body = client.get("/").text
    assert body.count('class="side-scroll"') == 2


def test_footer_stands_outside_the_wrapper(client, layer):
    """Если подвал остался внутри прокрутки, вынос ролей не состоялся: кнопка
    «Показать» снова уедет вместе с 57 тематиками. Считается вложенность: к
    моменту подвала обёртка должна быть уже закрыта."""
    layer.channel(1, "tg", "example_channel")
    layer.go_live()

    form = client.get("/").text.split('<form class="side"')[1].split("</form>")[0]
    inside = form.split('class="side-scroll"', 1)[1]

    depth = 1  # обёртка открыта
    for token in re.finditer(r'<div class="side-foot">|<div[ >][^>]*>?|</div>', inside):
        text = token.group(0)
        if text == '<div class="side-foot">':
            assert depth == 0, "подвал остался внутри прокручиваемой обёртки"
            return
        depth += -1 if text == "</div>" else 1
    raise AssertionError("подвала `.side-foot` нет в форме фильтров")
