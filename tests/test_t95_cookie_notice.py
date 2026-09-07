"""T-95: плашка согласия на куки и страница политики обработки данных.

Плашка уведомительная: счётчик Метрики она не блокирует и своих кук не ставит —
отметка о показе живёт в localStorage браузера. Отсюда две особенности, которые
и проверяются: в разметку плашка приезжает скрытой (показывает её скрипт, иначе
уже закрывший её человек видел бы мигание на каждой кэшированной странице), а
без JS её не видно вовсе — это осознанная цена, и она зафиксирована тестом,
чтобы «пропала на странице без скриптов» не читалось как дефект.
"""
import pytest

from conftest import assert_only_allowed_scripts


@pytest.fixture
def live(layer):
    layer.channel(1, "tg", "example_channel")
    layer.post(1, "p1")
    return layer.go_live()


PAGES = ("/", "/tg/example_channel", "/report", "/privacy")


def test_notice_stands_on_every_kind_of_page(live, client):
    for path in PAGES:
        body = client.get(path).text
        assert 'id="cookie-notice"' in body, path
        assert "Сайт использует файлы cookie и Яндекс.Метрику" in body, path
        assert 'id="cookie-notice-ok"' in body, path


def test_notice_comes_hidden_and_is_shown_by_script(live, client):
    """Разметка одна на всех и лежит в кэше nginx: видимой она приезжать не может."""
    body = client.get("/").text
    box = body[body.index('<div class="cookie-notice"'):]
    assert "hidden" in box[:box.index(">") + 1]
    assert 'data-script="cookie-notice"' in body
    assert "fomobase.cookie-notice" in body


def test_page_scripts_stay_inside_the_whitelist(live, client):
    """Плашка — второй и последний разрешённый скрипт витрины."""
    for path in PAGES:
        assert_only_allowed_scripts(client.get(path).text, path)


def test_notice_sets_no_cookie(live, client):
    """Своей куки плашка про куки не ставит: `Set-Cookie` выбил бы страницу из
    кэша nginx (ключ кэша строится без кук)."""
    for path in PAGES:
        assert "set-cookie" not in client.get(path).headers, path


# ── страница политики ────────────────────────────────────────────────────────

def test_privacy_page_answers_with_its_own_title(live, client):
    r = client.get("/privacy")
    assert r.status_code == 200
    assert "<title>Политика обработки персональных данных · Fomobase</title>" in r.text
    assert "Яндекс.Метрика" in r.text


def test_privacy_names_what_the_law_requires(live, client):
    """Документ по статье 18.1 152-ФЗ: без этих разделов он не политика, а
    пересказ. Проверяется наличие, а не формулировки, — текст правится с PO."""
    body = client.get("/privacy").text
    for must in ("152-ФЗ", "Правовые основания", "Цели обработки",
                 "Порядок и условия обработки", "Права субъекта персональных данных",
                 "Изменения политики", "10 рабочих дней"):
        assert must in body, must


def test_privacy_is_not_eaten_by_the_platform_catch_all(live, client):
    """`/{platform}` стоит ниже по файлу, но порядок маршрутов молчалив: если
    он однажды поедет, адрес отдаст 404 раздела, а не политику."""
    body = client.get("/privacy").text
    assert "Политика обработки персональных данных" in body
    assert "Такой страницы нет" not in body


def test_privacy_holds_the_operator_placeholder(live, client):
    """Реквизиты оператора ещё не пришли, и дыра в правовом тексте подсвечена
    нарочно. Тест снимается вместе с заглушкой."""
    assert "legal-todo" in client.get("/privacy").text


def test_privacy_is_closed_to_indexing(live, make_client):
    """Проверяется на открытом клиенте: на закрытом `robots.txt` отдаёт
    `Disallow: /` целиком, и тест зазеленел бы, ничего не проверив (T-67)."""
    closed_client = make_client()
    assert "noindex" in closed_client.get("/privacy").headers.get("x-robots-tag", "")

    open_client = make_client(noindex=False)
    assert "noindex" in open_client.get("/privacy").headers.get("x-robots-tag", "")
    assert "Disallow: /privacy\n" in open_client.get("/robots.txt").text


def test_privacy_is_not_in_the_sitemap(live, make_client):
    open_client = make_client(noindex=False)
    assert "/privacy" not in open_client.get("/sitemap.xml").text
    assert "/privacy" not in open_client.get("/sitemap-sections.xml").text


def test_footer_keeps_the_permanent_link(live, client):
    """Плашка исчезает после первого нажатия: без ссылки в подвале политика
    осталась бы доступной только тому, кто её застал."""
    for path in PAGES:
        assert 'href="/privacy"' in client.get(path).text, path
