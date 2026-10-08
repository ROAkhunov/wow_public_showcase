"""T-154: ссылка на карточку из каталога всегда чистая.

До задачи каталог дописывал к ссылке на карточку `?back=<адрес выдачи>` со
всех выдач, кроме корня. Адреса с `back` закрыты в robots, и Google видел на
разделах, тематиках и городах только закрытые копии карточек: новые карточки
оттуда не обходились, а отчёт «Заблокировано в robots.txt» рос.

Теперь адрес выдачи до кнопки «В каталог» доносит браузер: referrer или
память вкладки (`sessionStorage`). В HTML кнопка по-прежнему ведёт на `?back=`
старых адресов или в `/`, а скрипт подставляет выдачу, только когда `back` пуст.

Сам выбор адреса живёт в JS и здесь не исполняется: тесты проверяют то, что
отдаёт сервер, — чистые ссылки, `href` кнопки, наличие скрипта и его правила
проверки адреса.
"""
import re

import pytest

from conftest import assert_only_allowed_scripts, forms

pytestmark = pytest.mark.integration

BACK_SCRIPT = re.compile(r'<script data-script="back-link"[^>]*>(.*?)</script>', re.S)
TAILED_CARD = re.compile(r'href="/[a-z]+/[^"?]+\?back=')


def seed(layer):
    """Шестьдесят каналов tg в тематике «Спорт» и в Казани: хватает на вторую
    страницу и на собственные адреса пары «площадка + тематика» и города."""
    layer.city("kazan", "Казань", "Казани")
    for i in range(1, 61):
        layer.channel(i, "tg", f"ch{i}", subscribers=200_000 - i * 1000,
                      city="Казань", city_slug="kazan", is_local=True)
        layer.category(i, "Спорт", "sport")
    layer.section("tg", "sport", name="Спорт", channels=60)
    layer.city_section("tg", "kazan", channels=60)
    layer.go_live()


LISTINGS = (
    "/", "/?page=2", "/?subs_min=1000",
    "/tg", "/tg?page=2", "/tg?subs_min=1000&sort=subs",
    "/category/sport", "/category/sport?page=2", "/category/sport?subs_min=1000",
    "/category/sport/tg", "/category/sport/tg?page=2",
    "/city/kazan", "/city/kazan/tg", "/city/kazan/tg?page=2",
)


def plain(body):
    return body.replace("&amp;", "&")


# ── ссылки каталога ─────────────────────────────────────────────────────────

def test_no_listing_links_to_a_card_with_a_tail(layer, client):
    seed(layer)
    for path in LISTINGS:
        r = client.get(path)
        assert r.status_code == 200, path
        body = plain(r.text)
        assert 'href="/tg/ch' in body, f"на выдаче нет карточек: {path}"
        tailed = TAILED_CARD.findall(body)
        assert not tailed, f"{path}: ссылки на карточку с хвостом {tailed[:3]}"


def test_report_in_the_catalog_is_no_link_and_keeps_its_back(layer, client):
    """Хвост «Неточность?» нужен форме, но краулеру по нему ходить незачем:
    с T-155 это кнопка формы, ссылки на `/report` нет вовсе."""
    seed(layer)
    body = client.get("/category/sport?subs_min=1000").text
    assert 'href="/report' not in body
    found = forms(body, "/report")
    assert found
    for f in found:
        assert f["fields"]["back"] == "/category/sport?subs_min=1000", f


# ── карточка ────────────────────────────────────────────────────────────────

def back_anchor(body):
    block = body.split('class="back-link"')[1].split("</div>")[0]
    return re.search(r"<a [^>]*>", block).group(0)


def test_card_without_a_tail_points_home_and_carries_the_picker(layer, client):
    """Без JS кнопка ведёт в корень, скрипт выбора адреса на странице есть и
    помечен как разрешённый."""
    seed(layer)
    body = client.get("/tg/ch1").text
    assert 'href="/"' in back_anchor(body)
    assert BACK_SCRIPT.search(body), "скрипта выбора адреса на карточке нет"
    assert_only_allowed_scripts(body, "/tg/ch1")


def test_card_with_an_old_tail_keeps_it_and_the_clean_canonical(layer, client):
    """Старые адреса с `?back=` живут как раньше: кнопка с этим адресом,
    canonical на чистый."""
    seed(layer)
    body = plain(client.get("/tg/ch1?back=/category/sport%3Fsubs_min%3D1000").text)
    assert 'href="/category/sport?subs_min=1000"' in back_anchor(body)
    assert re.search(r'<link rel="canonical" href="[^"]*/tg/ch1"', body)


def test_the_picker_only_fills_an_empty_button(layer, client):
    """Сервер помечает кнопку для скрипта только когда `back` пуст: адрес из
    старой ссылки скрипт не перебивает."""
    seed(layer)
    bare = back_anchor(client.get("/tg/ch1").text)
    tailed = back_anchor(client.get("/tg/ch1?back=/tg").text)
    assert "data-back-auto" in bare
    assert "data-back-auto" not in tailed


def test_report_on_the_card_is_no_link(layer, client):
    """«Сообщить» — кнопка формы (T-155): ссылки на `/report` краулер не видит."""
    seed(layer)
    body = client.get("/tg/ch1").text
    assert 'href="/report' not in body
    assert forms(body, "/report")


# ── память вкладки ─────────────────────────────────────────────────────────

def test_every_listing_remembers_its_address_in_the_tab(layer, client):
    seed(layer)
    for path in LISTINGS:
        body = client.get(path).text
        found = BACK_SCRIPT.search(body)
        assert found, f"на выдаче нет скрипта памяти: {path}"
        code = found.group(1)
        assert "sessionStorage" in code and "location.pathname + location.search" in code, path
        assert_only_allowed_scripts(body, path)


def test_the_script_checks_addresses_like_safe_back(layer, client):
    """Значение из referrer и `sessionStorage` проверяется так же, как `?back=`
    на сервере: только свой путь, без `//host` и обратного слэша, и с тем же
    потолком длины. Доступ к хранилищу в try/catch."""
    from app.report import MAX_BACK

    seed(layer)
    code = BACK_SCRIPT.search(client.get("/tg/ch1").text).group(1)
    assert f"MAX_BACK = {MAX_BACK}" in code
    assert "'//'" in code and "\\\\" in code
    assert "try {" in code and "catch (e)" in code
    assert "document.referrer" in code and "location.origin" in code


def test_the_script_knows_every_listing_route(layer, client):
    """Список маршрутов выдачи в скрипте совпадает с площадками сервиса."""
    from app.settings import PLATFORMS

    seed(layer)
    code = BACK_SCRIPT.search(client.get("/tg/ch1").text).group(1)
    for platform in PLATFORMS:
        assert f'"{platform}"' in code, platform
    for prefix in ("category", "city"):
        assert prefix in code, prefix


def test_short_pages_do_not_carry_the_script(layer, client):
    seed(layer)
    for path in ("/report", "/privacy", "/nope/nope/nope"):
        assert 'data-script="back-link"' not in client.get(path).text, path
