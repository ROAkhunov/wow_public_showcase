"""T-89: низ страницы не рассыпается, когда выдача короче окна.

Дефект виден на короткой выдаче — узкий фильтр, последняя страница, пустой
результат: содержимое кончалось выше нижней кромки, строка «Данные собраны из
открытых источников» вставала сразу под ним, а дальше до низа окна тянулось
белое поле. На полной странице каталога этого не бывает: в выдаче 50 строк,
список всегда выше окна.

Сама геометрия меряется браузером и в pytest не переносится. Здесь стоят
контракты, на которых она держится, и запрет, нарушение которого молча уронит
сразу четыре липкости: колонку фильтров каталога, колонку канала и оба подвала
формы. Стили читаются через сервис — наружу едет то, что отдано.
"""
import re

import pytest

pytestmark = pytest.mark.integration


@pytest.fixture
def tokens(client):
    r = client.get("/assets/tokens.css")
    assert r.status_code == 200
    return r.text


@pytest.fixture
def components(client):
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


# ── подвал садится на низ окна ───────────────────────────────────────────────

def test_page_is_a_flex_column_at_least_a_screen_tall(tokens):
    """Без этих трёх строк подвалу не от чего отталкиваться: страница короче
    окна кончается там, где кончилось содержимое."""
    body = _rule(tokens, "body")
    assert re.search(r"min-height\s*:\s*100vh", body)
    assert re.search(r"display\s*:\s*flex", body)
    assert re.search(r"flex-direction\s*:\s*column", body)


def test_main_takes_the_leftover_height(tokens):
    """Растягивается содержимое, а не подвал: иначе к низу прижмётся не строка
    про источники, а пустое поле над ней."""
    assert re.search(r"flex\s*:\s*1\b", _rule(tokens, ".ds-main"))


def test_wrappers_keep_their_width_inside_the_flex_column(tokens, components):
    """`margin: 0 auto` по поперечной оси флекса отменяет растягивание. Без
    явной ширины страница садится по содержимому — на «спасибо» и 404 это узкий
    столбец вместо страницы."""
    for css, selector in ((tokens, ".ds-wrap"), (components, ".hero")):
        assert re.search(r"width\s*:\s*100%", _rule(css, selector)), \
            f"у `{selector}` нет ширины — во флекс-колонке блок схлопнется"


def test_pinned_footer_keeps_a_gap_from_the_edge(tokens):
    """Прижатая к низу строка иначе ложится на кромку окна. Отступ адресный:
    вертикальный padding в самом `.ds-wrap` сдвинул бы поля на всех страницах."""
    assert re.search(r"padding-bottom\s*:", _rule(tokens, ".ds-foot"))


def test_frame_carries_the_two_classes(client, layer):
    """Правила висят на классах каркаса, а каркас один на все пять страниц."""
    layer.channel(1, "tg", "example_channel")
    layer.go_live()
    body = client.get("/").text
    assert 'class="ds-wrap ds-main"' in body
    assert 'class="ds-wrap ds-foot"' in body


# ── запрет, на котором держатся липкие колонки ───────────────────────────────

def test_page_root_never_becomes_the_scroll_port(tokens, components):
    """`height` или `overflow` на `html`/`body` переносят прокрутку с окна на
    body, и липкость колонок каталога и канала вместе с подвалами формы
    перестаёт работать молча. `min-height` под запрет не подпадает."""
    for css in (tokens, components):
        bare = re.sub(r"/\*.*?\*/", " ", css, flags=re.S)
        for heads, decls in re.findall(r"([^{}]+)\{([^}]*)\}", bare):
            names = [one.strip() for one in heads.split(",")]
            if not ({"html", "body"} & set(names)):
                continue
            for line in decls.split(";"):
                assert not re.match(r"\s*(height|overflow(-[xy])?)\s*:", line), \
                    f"`{heads.strip()}` делает страницу скролл-портом: {line.strip()}"


def test_filter_column_still_scrolls_by_itself(components):
    """Колонка фильтров каталога прокручивается своей полосой, а не страницей —
    правку подвала это не касается.

    Носитель прокрутки с T-93 разделён: потолок высоты держит форма, полосу
    везёт внутренняя обёртка. Контракт тот же — прокрутка внутри колонки."""
    assert re.search(r"max-height\s*:", _rule(components, ".side-desktop .side"))
    assert re.search(r"overflow-y\s*:\s*auto",
                     _rule(components, ".side-desktop .side-scroll"))
