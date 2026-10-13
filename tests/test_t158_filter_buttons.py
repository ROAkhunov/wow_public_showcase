"""T-158: чипы колонки фильтров, чей адрес несёт `?cat=`, стали кнопками формы.

Адреса с `?cat=` закрыты в robots.txt, а колонка ссылалась на них `href`-ами:
89 тысяч ссылок по карте сайта на 13.10. Google ходит по ссылкам и упирается в
запрет, формы он не отправляет. Чип с `?cat=` теперь кнопка
`formaction` + `name="cat"` + `value` пустой GET-формы, человек по клику
попадает на тот же адрес. Чипы на открытые адреса остаются ссылками.

Слаг тематики кириллический намеренно: на латинском двойное кодирование
значения не проявилось бы. Города и каналы выдуманные: репозиторий публичный.
"""
import re
from html.parser import HTMLParser
from urllib.parse import quote

import pytest

from conftest import assert_only_allowed_scripts, chips

pytestmark = pytest.mark.integration

SPORT = "спорт"          # у пары с TG ниже порога: живёт параметром
NEWS = "новости-дня"     # у пары с TG своя посадочная
SPORT_Q = quote(SPORT, safe="")
NEWS_Q = quote(NEWS, safe="")

CAT_HREF = re.compile(r'href="[^"]*cat=')


@pytest.fixture
def live(layer):
    """Казань: 12 местных в TG. Москва: 10 в TG и 10 во VK. Плюс YT без города.
    «Новости дня» у TG на 10 каналов (посадочная), «Спорт» на 4 (параметр)."""
    next_id = 1
    plan = [("kazan", "Казань", "Казани", {"tg": 12}),
            ("moskva", "Москва", "Москвы", {"tg": 10, "vk": 10})]
    by_platform: dict[str, list[int]] = {}
    for slug, name, gen, counts in plan:
        layer.city(slug, name, gen)
        for platform, n in counts.items():
            for i in range(1, n + 1):
                layer.channel(next_id, platform, f"{slug}_{platform}_{i}",
                              subscribers=100_000 - next_id * 100,
                              display_name=f"{name} {platform} {i}",
                              city=name, city_slug=slug, is_local=True)
                by_platform.setdefault(platform, []).append(next_id)
                next_id += 1
            layer.city_section(platform, slug, channels=n)
    for i in range(3):
        layer.channel(next_id, "yt", f"yt_{i}", subscribers=50_000)
        by_platform.setdefault("yt", []).append(next_id)
        next_id += 1

    tg = by_platform["tg"]
    for cid in tg[:10]:
        layer.category(cid, "Новости дня", NEWS)
    for cid in tg[10:14] + by_platform["vk"][:2] + by_platform["yt"][:2]:
        layer.category(cid, "Спорт", SPORT)

    layer.section("", "", channels=next_id - 1)
    for p in ("tg", "vk", "max", "yt"):
        layer.section(p, "", channels=len(by_platform.get(p, [])))
    layer.section("", NEWS, name="Новости дня", channels=10)
    layer.section("", SPORT, name="Спорт", channels=8)
    layer.section("tg", NEWS, name="Новости дня", channels=10)
    layer.section("tg", SPORT, name="Спорт", channels=4)
    layer.section("vk", SPORT, name="Спорт", channels=2)
    layer.section("yt", SPORT, name="Спорт", channels=2)
    return layer.go_live()


# ── разбор страницы ──────────────────────────────────────────────────────────

def desktop(html: str) -> str:
    return html.split('<aside class="side-desktop">', 1)[1].split("</aside>", 1)[0]


def mobile(html: str) -> str:
    return html.split('<details class="side-mobile">', 1)[1].split("</details>\n<aside", 1)[0]


def side(html: str) -> str:
    """Колонка фильтров обеих копий: от основной формы до конца её разметки."""
    return mobile(html) + desktop(html)


def group(html: str, label: str) -> list[dict]:
    """Чипы группы десктопной колонки по подписи («Площадка», «Тематика», «Город»)."""
    col = desktop(html)
    start = col.find(f'<span class="ds-label">{label}</span>')
    assert start >= 0, f"нет группы «{label}»"
    end = col.find('<div class="group">', start)
    return chips(col[start:end if end > 0 else len(col)])


def chip(found: list[dict], text: str) -> dict:
    return next(c for c in found if c["text"] == text)


def button_to(c: dict, formaction: str, value: str) -> None:
    a = c["attrs"]
    assert c["tag"] == "button", c
    assert a.get("type") == "submit", c
    assert a.get("formaction") == formaction, c
    assert a.get("name") == "cat", c
    assert a.get("value") == value, "в value не сырой слаг"
    assert "?" not in formaction


class Forms(HTMLParser):
    """Формы страницы с глубиной вложенности и содержимым."""

    def __init__(self):
        super().__init__()
        self.stack: list[dict] = []
        self.forms: dict[str, dict] = {}
        self.nested = 0

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if self.stack:
            self.stack[-1]["children"] += 1
        if tag == "form":
            f = {"attrs": a, "depth": len(self.stack), "children": 0}
            if self.stack:
                self.nested += 1
            self.stack.append(f)
            if a.get("id"):
                self.forms[a["id"]] = f

    def handle_endtag(self, tag):
        if tag == "form" and self.stack:
            self.stack.pop()


def parsed_forms(html: str) -> Forms:
    p = Forms()
    p.feed(html)
    return p


# ── индексируемые страницы без ссылок на `?cat=` ─────────────────────────────

CLEAN = ("/", "/tg", "/vk", "/yt", "/city/kazan", "/city/kazan/tg", "/city/moskva/vk",
         f"/category/{SPORT_Q}", f"/category/{NEWS_Q}", f"/category/{NEWS_Q}/tg")


@pytest.mark.parametrize("path", CLEAN)
def test_pages_have_no_href_with_cat(live, client, path):
    r = client.get(path, follow_redirects=False)
    assert r.status_code == 200, path
    assert not CAT_HREF.findall(r.text), f"{path}: осталась ссылка с cat="


@pytest.mark.parametrize("path", [f"/city/kazan?cat={SPORT_Q}", f"/tg?cat={SPORT_Q}",
                                  f"/city/moskva?cat={SPORT_Q}"])
def test_filter_column_has_no_href_with_cat_when_a_topic_is_chosen(live, client, path):
    """Сортировка и пагинация несут `?cat=` законно: страница уже под фильтром.
    Колонка нет."""
    r = client.get(path, follow_redirects=False)
    assert r.status_code == 200, path
    assert not CAT_HREF.findall(side(r.text)), path


# ── какие чипы стали кнопками ────────────────────────────────────────────────

def test_city_chip_on_a_category_page_is_a_button_of_the_empty_form(live, client):
    html = client.get(f"/category/{SPORT_Q}").text
    kazan = chip(group(html, "Город"), "Казань")
    button_to(kazan, "/city/kazan", SPORT)
    fid = kazan["attrs"].get("form")
    forms = parsed_forms(html)
    assert forms.nested == 0, "вложенная форма: браузер её выкинет"
    f = forms.forms[fid]
    assert f["depth"] == 0, "форма кнопок внутри другой формы"
    assert f["attrs"].get("method") == "get"
    assert f["children"] == 0, "форма кнопок не пустая"
    assert "side" not in (f["attrs"].get("class") or ""), "кнопка привязана к основной форме"


def test_topic_chip_on_a_city_page_is_a_button(live, client):
    html = client.get("/city/kazan").text
    button_to(chip(group(html, "Тематика"), "Спорт"), "/city/kazan", SPORT)
    button_to(chip(group(html, "Тематика"), "Новости дня"), "/city/kazan", NEWS)
    html = client.get("/city/kazan/tg").text
    button_to(chip(group(html, "Тематика"), "Спорт"), "/city/kazan/tg", SPORT)


def test_topic_chip_on_a_platform_page_below_threshold_is_a_button(live, client):
    found = group(client.get("/tg").text, "Тематика")
    button_to(chip(found, "Спорт"), "/tg", SPORT)
    news = chip(found, "Новости дня")
    assert news["tag"] == "a"
    assert news["attrs"]["href"] == f"/category/{NEWS_Q}/tg"


def test_topics_on_youtube_are_buttons_without_the_city_block(live, client):
    html = client.get("/yt").text
    assert '<span class="ds-label">Город</span>' not in html
    sport = chip(group(html, "Тематика"), "Спорт")
    button_to(sport, "/yt", SPORT)
    assert sport["attrs"]["form"] in parsed_forms(html).forms, "у кнопки нет своей формы"


def test_platform_chips_with_a_topic(live, client):
    # вне города: пара ниже порога кнопкой, посадочная ссылкой
    found = group(client.get(f"/category/{SPORT_Q}").text, "Площадка")
    button_to(chip(found, "Telegram"), "/tg", SPORT)
    found = group(client.get(f"/category/{NEWS_Q}").text, "Площадка")
    assert chip(found, "Telegram")["tag"] == "a"
    assert chip(found, "Telegram")["attrs"]["href"] == f"/category/{NEWS_Q}/tg"
    # на городе с тематикой: кнопки, без тематики: ссылки
    found = group(client.get(f"/city/moskva?cat={SPORT_Q}").text, "Площадка")
    button_to(chip(found, "ВКонтакте"), "/city/moskva/vk", SPORT)
    button_to(chip(found, "Все площадки"), "/city/moskva", SPORT)
    found = group(client.get("/city/moskva").text, "Площадка")
    assert {c["tag"] for c in found} == {"a"}


def test_all_cities_with_a_thin_pair_is_a_button(live, client):
    found = group(client.get(f"/city/kazan/tg?cat={SPORT_Q}").text, "Город")
    button_to(chip(found, "Все города"), "/tg", SPORT)
    found = group(client.get(f"/city/kazan/tg?cat={NEWS_Q}").text, "Город")
    assert chip(found, "Все города")["attrs"].get("href") == f"/category/{NEWS_Q}/tg"


def test_chips_to_open_addresses_stay_links(live, client):
    for path in ("/", "/tg", "/city/kazan"):
        for c in group(client.get(path).text, "Город"):
            assert c["tag"] == "a", (path, c)
    for c in group(client.get("/").text, "Тематика"):
        assert c["tag"] == "a", c


# ── клик открывает тот же адрес, без редиректа ───────────────────────────────

BUTTON_PAGES = (f"/category/{SPORT_Q}", "/city/kazan", "/city/kazan/tg", "/tg", "/yt",
                f"/city/moskva?cat={SPORT_Q}", f"/city/kazan/tg?cat={SPORT_Q}",
                f"/category/{NEWS_Q}/tg")


def test_every_button_lands_on_its_address_without_a_redirect(live, client):
    """Адрес собирается как браузер: `formaction` + `?cat=` + значение поля в
    кодировке формы. Сервер сверяет строку запроса с канонической, лишний 301
    на каждом клике был бы дефектом."""
    seen = 0
    for path in BUTTON_PAGES:
        for c in chips(side(client.get(path).text)):
            if c["tag"] != "button":
                continue
            seen += 1
            r = client.get(c["target"], follow_redirects=False)
            assert r.status_code == 200, (path, c["target"], r.headers.get("location"))
    assert seen > 0


def test_button_target_is_the_old_href(live, client):
    found = group(client.get(f"/category/{SPORT_Q}").text, "Город")
    assert chip(found, "Казань")["target"] == f"/city/kazan?cat={SPORT_Q}"


def test_selected_topic_is_lit_after_the_click(live, client):
    html = client.get(f"/city/kazan?cat={SPORT_Q}").text
    sport = chip(group(html, "Тематика"), "Спорт")
    assert sport["on"] and sport["tag"] == "button"


# ── две копии колонки ────────────────────────────────────────────────────────

@pytest.mark.parametrize("path", [f"/category/{SPORT_Q}", "/city/kazan", "/yt"])
def test_each_copy_has_its_own_form(live, client, path):
    html = client.get(path).text
    ids = []
    for copy in (mobile(html), desktop(html)):
        forms = parsed_forms(copy)
        buttons = [c for c in chips(copy) if c["tag"] == "button"]
        assert buttons, path
        bound = {c["attrs"].get("form") for c in buttons}
        assert len(bound) == 1, bound
        [fid] = bound
        assert fid in forms.forms, f"{path}: форма {fid} не в своей копии"
        ids.append(fid)
    assert ids[0] != ids[1], "у копий один id формы"


def test_no_new_scripts(live, client):
    for path in ("/city/kazan", f"/category/{SPORT_Q}", "/yt"):
        assert_only_allowed_scripts(client.get(path).text, path)


# ── вид ──────────────────────────────────────────────────────────────────────

def test_button_chip_resets_browser_defaults_without_the_font_shorthand(client):
    """`button.chip` по специфичности выше `.chip`: шорткат `font` затёр бы
    размер и `line-height`, чип сменил бы высоту."""
    css = client.get("/assets/components.css").text
    rule = re.search(r"button\.chip\s*\{([^}]*)\}", css).group(1)
    assert "font-family: inherit" in rule
    assert not re.search(r"(^|[;\s])font\s*:", rule), "шорткат font в button.chip"
    for decl in ("color: inherit", "cursor: pointer", "margin: 0", "text-align"):
        assert decl in rule, decl
