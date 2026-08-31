"""T-77: каталог не едет вбок на телефоне, «Показать» под рукой, палец попадает.

Геометрия меряется браузером и в pytest не переносится: здесь стоят контракты,
которые эту геометрию держат. Сломается любой из них — вернётся ровно та
находка аудита T-68.4, из-за которой задача заведена.

Стили читаются через сервис (`/assets/components.css`), а не с диска: наружу
едет то, что отдано, и путь к файлу тесту знать незачем.
"""
import re

import pytest

pytestmark = pytest.mark.integration


@pytest.fixture
def css(client):
    body = client.get("/assets/components.css")
    assert body.status_code == 200
    return body.text


def _rule(css: str, selector: str) -> str:
    """Все объявления селектора, включая правила, где он стоит в общем списке."""
    body = ""
    bare = re.sub(r"/\*.*?\*/", " ", css, flags=re.S)
    for heads, decls in re.findall(r"([^{}]+)\{([^}]*)\}", bare):
        if selector in [one.strip() for one in heads.split(",")]:
            body += decls + ";"
    assert body, f"правила `{selector}` нет в components.css"
    return body


def _count(css: str, selector: str) -> int:
    return len(re.findall(re.escape(selector) + r"\s*\{", css))


# ── находка №3: полоса сортировки не вылезает за край окна ───────────────────

def test_sort_strip_wraps(css):
    """`.bar` переносится, а `.sort` внутри — нет: полоса вылезала за правый
    край, scrollWidth 436 при окне 410 (аудит T-68.4, находка №3)."""
    assert "wrap" in _rule(css, ".sort")


def test_sort_button_has_no_fixed_height(css):
    """Высота была фиксированной, и длинная подпись рвалась на три строки
    внутри пилюли. Высота объявлена и у `.sbtn`, и у активной `.sbtn.on`."""
    for selector in (".sbtn", ".sbtn.on"):
        for line in _rule(css, selector).split(";"):
            assert not re.match(r"\s*height\s*:", line), \
                f"у `{selector}` осталась фиксированная height — подпись снова порвётся"


def test_active_sort_button_declared_once(css):
    """`.sbtn.on` был объявлен дважды целиком: правка в одном месте оставляла
    активную кнопку сломанной."""
    assert _count(css, ".sbtn.on") == 1


# ── находка №4: «Показать» у нижнего края экрана, а не через два экрана ──────

def test_mobile_filter_footer_sticks_to_the_screen(css):
    """Липкий подвал был заведён только десктопной разметке, и на телефоне
    кнопка «Показать» стояла в 1669 px от верха страницы."""
    body = _rule(css, ".side-mobile .side-foot")
    assert "sticky" in body
    assert re.search(r"bottom\s*:\s*0", body)


def test_mobile_filter_column_does_not_scroll_inside_itself(css):
    """Десктопный приём двухчастный, мобильной панели нужна только вторая
    половина: своя прокрутка на телефоне завела бы прокрутку внутри страницы."""
    body = _rule(css, ".side-mobile .side")  if ".side-mobile .side {" in css else ""
    assert "overflow-y" not in body and "max-height" not in body


# ── находки №24–26: вертикальная цель нажатия 44 px ──────────────────────────

@pytest.mark.parametrize("selector", [".post-src", ".link-quiet", ".side-hide"])
def test_action_links_get_a_44px_tap_zone(css, selector):
    """Зона растёт накладкой, а не размером надписи: было 19, 21 и 16 px
    (находки №24–26), а размером поехала бы плотность строки и десктоп."""
    over = _rule(css, selector + "::after")
    assert re.search(r"height\s*:\s*44px", over), \
        f"у `{selector}` накладка не 44 px — палец промахивается"
    assert "absolute" in over
    assert "relative" in _rule(css, selector), \
        f"`{selector}` не система координат для своей накладки"


def test_original_link_has_its_own_class(layer, client):
    """«Оригинал» шёл общим `.sub`, а `.sub` несёт шесть ролей: отступ в нём
    уехал бы ещё в пять мест на десктопе."""
    cid = layer.channel(1, "tg", "example_channel")
    layer.post(cid, "p1")
    layer.go_live()

    body = client.get("/tg/example_channel").text
    found = re.search(r'<a class="([^"]*)"[^>]*>Оригинал</a>', body)
    assert found, "ссылки «Оригинал» нет на странице канала"
    classes = found.group(1).split()
    assert "post-src" in classes
    assert "sub" not in classes


def test_sub_stays_untouched(css):
    """Страховка от лёгкого пути: накладка, повешенная на `.sub`, поедет на
    десктопе в пяти местах."""
    assert ".sub::after" not in css


# ── находка на живых данных: канал ехал вбок от неразрывной строки ───────────

def test_channel_columns_do_not_grow_with_their_content(css):
    """Грид-элемент по умолчанию не сужается уже содержимого: один hex-ключ из
    поста растягивал страницу канала до 703 px при окне 360 (замер на проде
    27.08). В каталоге это закрыто `.listing`, у канала строку забыли."""
    for selector in (".channel-main", ".channel-side"):
        assert re.search(r"min-width\s*:\s*0", _rule(css, selector)), \
            f"`{selector}` не ограничен по ширине — канал снова поедет вбок"


@pytest.mark.parametrize("selector", [".post-text", ".desc", ".adv-line"])
def test_foreign_text_wraps_anywhere(css, selector):
    """Чужой текст переносится по любому месту: страницу он уже не растянет,
    но без переноса вылезет из карточки за её край."""
    assert "anywhere" in _rule(css, selector)
