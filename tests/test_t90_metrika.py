"""T-90: счётчик Яндекс.Метрики на всех страницах витрины.

Счётчик — первый и единственный исполняемый скрипт на сайте. Проверяется две
вещи: что он приезжает на каждый тип страницы и что правило шва 3 после его
появления не превратилось в «скриптам можно всё».

Правило живёт в `conftest.assert_metrika_is_the_only_script`, и его собственный
разбор написан здесь на синтетическом HTML: разметки JSON-LD на живых страницах
ещё нет (её принесёт T-83), проверить пропуск `application/ld+json` на настоящем
ответе нечем. Синтетика тут — задел под T-83, чтобы её микроразметка не уронила
этот тест.
"""
import pytest

from conftest import (METRIKA_COUNTER, METRIKA_TAG_SRC,
                      assert_metrika_is_the_only_script)


@pytest.fixture
def live(layer):
    layer.channel(1, "tg", "example_channel")
    layer.post(1, "p1")
    return layer.go_live()


def test_counter_stands_on_every_kind_of_page(live, client):
    for path in ("/", "/tg/example_channel", "/report"):
        body = client.get(path).text
        assert METRIKA_TAG_SRC in body, path
        assert METRIKA_COUNTER in body, path
        assert_metrika_is_the_only_script(body, path)


def test_noscript_pixel_comes_along(live, client):
    """Пиксель это `<img>`, а не скрипт: браузер с выключенным JS тоже считается."""
    body = client.get("/").text
    assert f"https://mc.yandex.ru/watch/{METRIKA_COUNTER}" in body


def test_report_form_is_hidden_from_the_webvisor(live, client):
    """Введённый email не должен попасть в запись сессии.

    Класс висит на секции целиком: при ошибке валидации адрес возвращается
    сервером в `value` и виден не только внутри поля ввода.
    """
    body = client.get("/report").text
    assert "report-form ym-hide-content" in body


# ── само правило шва 3 ───────────────────────────────────────────────────────

_COUNTER = (
    '<script type="text/javascript">'
    f"(function(){{}})(window, document, 'script', 'https://{METRIKA_TAG_SRC}?id={METRIKA_COUNTER}', 'ym');"
    f" ym({METRIKA_COUNTER}, 'init', {{}});"
    '</script>'
)


def test_rule_lets_json_ld_through():
    """Микроразметка T-83 это данные, а не код, и правило её пропускает."""
    page = ('<body>'
            '<script type="application/ld+json">{"@type":"WebSite"}</script>'
            f'{_COUNTER}</body>')
    assert_metrika_is_the_only_script(page)


def test_rule_catches_a_foreign_script():
    page = f'<body><script>alert(1)</script>{_COUNTER}</body>'
    with pytest.raises(AssertionError):
        assert_metrika_is_the_only_script(page)


def test_rule_catches_a_page_without_the_counter():
    with pytest.raises(AssertionError):
        assert_metrika_is_the_only_script("<body><p>без счётчика</p></body>")
