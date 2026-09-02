"""T-73: возврат со страницы ленты приводит туда, откуда ушли.

Прилипание колонки, высоты панели и полоса прокрутки внутри карточки — это вид,
он меряется браузером и в pytest не переносится. Здесь стоит вторая половина
задачи: адрес возврата собирается целиком (номер страницы ленты плюс якорь),
доезжает через форму до страницы «спасибо» и не разводит там две кнопки в одно
место.
"""
from urllib.parse import quote, unquote

import pytest

pytestmark = pytest.mark.integration

CATALOG_BACK = "/?subs_min=1000&sort=subs&page=2"
FEED_BACK = "/tg/talky?posts=3#feed"


@pytest.fixture
def talky(layer):
    """Канал с лентой на три страницы: возврат проверяется с третьей."""
    layer.channel(1, "tg", "talky", display_name="Болтливый канал")
    for i in range(25):
        layer.post(1, f"p{i}", text=f"Публикация номер {i}", days_ago=i)
    layer.go_live()
    return layer


def _report_link(body: str) -> str:
    """Адрес возврата из ссылки «Сообщить» правой колонки, раскодированный."""
    import re
    found = re.search(r'href="(/report\?[^"]*)"[^>]*>Сообщить</a>', body)
    assert found, "ссылки «Сообщить» нет на странице канала"
    href = found.group(1).replace("&amp;", "&")
    return unquote(href.split("back=", 1)[1])


# ── ссылка «Сообщить» несёт страницу ленты целиком ───────────────────────────

def test_report_link_carries_the_feed_page_and_the_anchor(client, talky):
    """Обращение с третьей страницы возвращало в начало первой: в параметр
    уходил один путь, без `?posts=N` и без якоря."""
    from app.report import safe_back

    back = _report_link(client.get("/tg/talky?posts=3").text)
    assert back == FEED_BACK
    assert safe_back(back) == FEED_BACK, "адрес возврата не прошёл проверку целиком"


def test_report_link_from_the_first_page_has_no_posts_parameter(client, talky):
    """На первой странице параметра `posts` нет вовсе, а `?posts=1` уводит
    редиректом на голый адрес. Якорь при этом стоит и здесь."""
    assert _report_link(client.get("/tg/talky").text) == "/tg/talky#feed"


def test_cancel_returns_to_the_feed_page(client, talky):
    """«Отмена» на форме кормится тем же адресом — уходит и возвращается туда
    же, куда и отправленное обращение."""
    r = client.get(f"/report?platform=tg&channel=talky&back={quote(FEED_BACK, safe='')}")
    assert r.status_code == 200
    assert f'href="{FEED_BACK}"' in r.text.replace("&amp;", "&")


# ── страница «спасибо» ───────────────────────────────────────────────────────

def test_thanks_from_the_feed_shows_one_road_to_the_channel(client, talky):
    """Путь возврата совпал с адресом канала, значит «Вернуться к выдаче» не
    показывается, а акцентная кнопка ведёт на ту же страницу ленты."""
    r = client.get("/report/thanks?platform=tg&channel=talky"
                   f"&back={quote(FEED_BACK, safe='')}")
    text = r.text.replace("&amp;", "&")
    assert "Вернуться к выдаче" not in text
    assert f'href="{FEED_BACK}"' in text
    assert text.count("Вернуться к каналу") == 1


def test_thanks_still_hides_the_listing_road_for_a_bare_root(client, talky):
    """Сравнение с корнем осталось точным: голый `/` это те же три дороги в
    одно место, что и раньше."""
    text = client.get("/report/thanks?platform=tg&channel=talky&back=%2F").text
    assert "Вернуться к выдаче" not in text


def test_thanks_keeps_the_filtered_listing_apart_from_the_root(client, talky):
    """Отфильтрованная выдача это корень с параметрами: по пути она совпала бы
    с `/`, и человек потерял бы фильтры."""
    text = client.get("/report/thanks?platform=tg&channel=talky"
                      f"&back={quote(CATALOG_BACK, safe='')}").text.replace("&amp;", "&")
    assert "Вернуться к выдаче" in text
    assert f'href="{CATALOG_BACK}"' in text
    assert 'href="/tg/talky"' in text, "кнопка к каналу уехала на каталожную выдачу"


def test_thanks_survives_a_channel_that_is_not_in_the_dump(client, talky):
    """`channel_url` бывает пустым — канала нет в дампе. Непустой `back` при
    этом сравнивать не с чем, и страница не должна падать."""
    r = client.get("/report/thanks?platform=tg&channel=nosuchchannel"
                   f"&back={quote(FEED_BACK, safe='')}")
    assert r.status_code == 200
    assert "nosuchchannel" not in r.text
    assert "Вернуться к выдаче" in r.text.replace("&amp;", "&")
