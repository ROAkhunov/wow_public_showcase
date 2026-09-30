"""T-145: тег Google Analytics на всех страницах витрины.

Тег — два исполняемых скрипта: внешний загрузчик `gtag.js` и инлайн с
`config`. Оба стоят в белом списке шва 3 поимённо, рядом со счётчиком Метрики,
и оба обязаны быть на каждой странице ровно по одному. Сигналы Google для
рекламы и персонализации рекламы выключены в самом теге: политика обещает, что
данные посетителей не используются для рекламы, и тег держит это обещание
независимо от настроек ресурса в кабинете GA.

Помощник белого списка проверяется здесь и на синтетике: страница без GA,
с задвоенным тегом или с загрузчиком чужого ресурса проехать не должна.
"""
import re

import pytest

from conftest import (GA_CONFIG, GA_ID, GA_TAG_SRC, METRIKA_COUNTER, METRIKA_TAG_SRC,
                      assert_only_allowed_scripts)


@pytest.fixture
def live(layer):
    layer.channel(1, "tg", "example_channel")
    layer.post(1, "p1")
    return layer.go_live()


PAGES = ("/", "/tg/example_channel", "/report", "/report/thanks", "/privacy",
         "/no-such-page-xyz")


def test_ga_tag_stands_on_every_kind_of_page(live, client):
    for path in PAGES:
        body = client.get(path).text
        assert body.count(f'<script async src="{GA_TAG_SRC}"></script>') == 1, path
        assert body.count(GA_CONFIG) == 1, path
        assert_only_allowed_scripts(body, path)


def test_ga_config_turns_advertising_signals_off(live, client):
    body = client.get("/").text
    config = re.search(r"gtag\('config', '" + GA_ID + r"', \{([^}]*)\}\);", body)
    assert config, "вызов config с параметрами не найден"
    params = config.group(1)
    assert "'allow_google_signals': false" in params
    assert "'allow_ad_personalization_signals': false" in params


def test_ga_tag_follows_the_metrika_counter(live, client):
    """Тег стоит сразу после блока Метрики и до скрипта плашки."""
    body = client.get("/").text
    metrika_end = body.index("<!-- /Yandex.Metrika counter -->")
    ga_start = body.index("<!-- Google tag (gtag.js) -->")
    notice = body.index('data-script="cookie-notice"')
    assert metrika_end < ga_start < notice


def test_notice_and_privacy_name_google_analytics(live, client):
    notice = " ".join(client.get("/").text.split())
    assert "файлы cookie, Яндекс.Метрику и Google Analytics" in notice
    body = " ".join(client.get("/privacy").text.split())
    assert "Редакция от 30 сентября 2026 года" in body
    assert "сервисов Яндекс.Метрика и Google Analytics" in body
    assert "Счётчики Яндекс.Метрики и Google Analytics загружаются" in body
    assert "на стороне Яндекса и Google на их условиях" in body
    assert "ведёт также Google LLC (США)" in body
    assert "https://policies.google.com/privacy" in body
    assert "Сигналы Google для рекламы и персонализации рекламы на сайте выключены." in body
    assert "Файлы cookie ставят счётчики Яндекс.Метрики и Google Analytics" in body
    assert "https://tools.google.com/dlpage/gaoptout" in body
    # Обещание «не для рекламы» остаётся на месте.
    assert "Данные посетителей не используются для рекламы" in body


# ── помощник белого списка ───────────────────────────────────────────────────

_METRIKA = (
    '<script type="text/javascript">'
    f"(function(){{}})(window, document, 'script', 'https://{METRIKA_TAG_SRC}?id={METRIKA_COUNTER}', 'ym');"
    f" ym({METRIKA_COUNTER}, 'init', {{}});"
    '</script>'
)
_GA_LOADER = f'<script async src="{GA_TAG_SRC}"></script>'
_GA_CONFIG = f"<script>gtag('js', new Date()); {GA_CONFIG}', {{}});</script>"


def test_rule_accepts_the_full_set():
    assert_only_allowed_scripts(f"<body>{_METRIKA}{_GA_LOADER}{_GA_CONFIG}</body>")


def test_rule_catches_a_page_without_ga():
    with pytest.raises(AssertionError):
        assert_only_allowed_scripts(f"<body>{_METRIKA}</body>")


def test_rule_catches_a_page_without_the_ga_loader():
    with pytest.raises(AssertionError):
        assert_only_allowed_scripts(f"<body>{_METRIKA}{_GA_CONFIG}</body>")


def test_rule_catches_a_page_without_the_ga_config():
    with pytest.raises(AssertionError):
        assert_only_allowed_scripts(f"<body>{_METRIKA}{_GA_LOADER}</body>")


def test_rule_catches_a_doubled_ga_tag():
    with pytest.raises(AssertionError):
        assert_only_allowed_scripts(
            f"<body>{_METRIKA}{_GA_LOADER}{_GA_CONFIG}{_GA_LOADER}{_GA_CONFIG}</body>")


def test_rule_catches_a_loader_of_someone_elses_resource():
    """Загрузчик с чужим номером — посторонний скрипт, а не «второй GA»."""
    other = '<script async src="https://www.googletagmanager.com/gtag/js?id=G-OTHER000"></script>'
    with pytest.raises(AssertionError):
        assert_only_allowed_scripts(f"<body>{_METRIKA}{_GA_LOADER}{_GA_CONFIG}{other}</body>")


def test_rule_catches_a_foreign_script_next_to_ga():
    with pytest.raises(AssertionError):
        assert_only_allowed_scripts(
            f"<body>{_METRIKA}{_GA_LOADER}{_GA_CONFIG}<script>alert(1)</script></body>")
