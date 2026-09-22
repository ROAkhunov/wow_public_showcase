"""T-120: описание канала не продаёт рекламу мимо нас.

Описание стояло в шапке выше метрик и любой нашей кнопки, и у 54% телеграм-каналов
с кнопкой в нём лежал контакт «по рекламе @…», у 39% адрес биржи-конкурента.
Закупщик видел «купить рекламу» и адрес раньше нашего выхода.

Фильтр `strip_ad_contacts` вырезает подпись контакта и сам контакт по правилу
«маркер + токен контакта» (прототип C из замера 22.09, остаток 1,1%). Абзац
описания показывается по результату фильтра, а не по оригиналу. Случаи ниже —
дословно из замера.

С T-124 описание вернулось в шапку, под подпись канала: причину ухода вниз
снял фильтр, а не место. Свёртка и порог длины — в `test_t124_desc_in_head`.
"""
import re

import pytest

from app.format import strip_ad_contacts
from conftest import assert_only_allowed_scripts

pytestmark = pytest.mark.integration


# ── фильтр ───────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("before, after", [
    # адрес биржи-конкурента: сам себе и маркер, и контакт
    ("3d модели stl для 3д принтера\nКупить рекламу https://telega.in/?r=w4EhDFMLLNTV",
     "3d модели stl для 3д принтера"),
    ("Купить рекламу https://telega.io/c/a", ""),
    # эмодзи между маркером и контактом не рвёт подпись; служебные слова уходят назад
    ("Вопросы по рекламе 👉 @mgrace_pr", ""),
    ("Реклама: @promo Мы пишем о котиках", "Мы пишем о котиках"),
    # перенос строки допустим, если до него после маркера только двоеточие
    ("Реклама:\n@promo", ""),
    # висящая точка за контактом снимается (правка 5)
    ("Связь с нами — @promo. Канал о кино", "Канал о кино"),
    # цепочка контактов через «/», запятую, «или» (правка 3)
    ("Реклама: @aaa / @bbb, @ccc или @ddd", ""),
    # реестр РКН контактом не считается
    ("Купить рекламу: https://telega.in/c/a https://gosuslugi.ru/snet/1",
     "https://gosuslugi.ru/snet/1"),
    # назад расширяемся только по служебным словам
    ("Апогей идиотии Связь @xxx", "Апогей идиотии"),
    # все вхождения, не первое; переносы остаются, их схлопнет `clip`
    ("Про кино. Реклама: @one\nСотрудничество: @two\nСмотрим вместе", "Про кино.\n\nСмотрим вместе"),
])
def test_ad_contact_is_cut(before, after):
    assert strip_ad_contacts(before) == after


@pytest.mark.parametrize("text", [
    # конец фразы между маркером и контактом — стоп
    "Реклама в канале не размещается. Подпишись @promo",
    # перенос со словами после маркера — стоп
    "Реклама не размещается\nПодпишись @promo",
    # ссылка на реестр РКН
    "Страница включена в перечень РКН https://knd.gov.ru/license?id=1",
    "Включена РКН в перечень персональных страниц https://clck.ru/abc",
    # исключения из маркеров: услуга и должность
    "Прайс на услуги https://site.ru/",
    "Менеджер по продажам @promo",
    # контакт без маркера остаётся
    "Наш сайт site.ru",
    "Подпишись @promo и заходи на t.me/promo",
    # маркер без контакта в окне — ничего не трогать (правка 4)
    "Реклама на канале не продаётся, только авторские материалы",
    # «предложени*» не маркер (правка 1)
    "Принимаем предложения от местного бизнеса мояноваярига.рф",
])
def test_plain_text_is_kept(text):
    assert strip_ad_contacts(text) == text


@pytest.mark.parametrize("text", [None, ""])
def test_empty_gives_empty_string(text):
    assert strip_ad_contacts(text) == ""


def test_filter_is_pure():
    text = "Реклама: @promo Мы пишем о котиках"
    assert strip_ad_contacts(text) == strip_ad_contacts(text)
    assert text == "Реклама: @promo Мы пишем о котиках"


# ── страница ─────────────────────────────────────────────────────────

HEAD = re.compile(r'<div class="head">(.*?)(?=<div class="invite-mobile">|</section>)', re.S)
TOP = re.compile(r'<div class="top">(.*?)<div class="actions">', re.S)
SUB = '<div class="sub">'
DESC = '<p class="desc">'
DETAILS = '<details class="desc">'


def heads(body: str) -> list[str]:
    found = HEAD.findall(body)
    assert found, "на странице нет шапки канала"
    return found


def desc_at(html: str) -> int:
    """Где в куске разметки начинается описание, какой бы ни была ветка.

    С T-124 абзац у коротких описаний и `<details>` у длинных — одно и то же
    место в шапке, и место проверяется одинаково для обоих.
    """
    spots = [html.index(one) for one in (DESC, DETAILS) if one in html]
    assert spots, "описания в разметке нет"
    return min(spots)


def has_desc(html: str) -> bool:
    return DESC in html or DETAILS in html


def test_description_is_shown_without_the_ad_contact(layer, client):
    layer.channel(1, "tg", "kittens", description="Про котиков\nРеклама: @manager")
    layer.go_live()
    body = client.get("/tg/kittens").text
    assert_only_allowed_scripts(body, "/tg/kittens")
    assert "Про котиков" in body
    assert "@manager" not in body


def test_description_stands_in_the_top_under_the_sub(layer, client):
    """T-124: описание вернулось в шапку, рядом с аватаром и под подписью.

    T-120 уносила его в конец `.head`, после тематик. Причина ухода —
    рекламный контакт выше нашей кнопки — снята фильтром, а не местом, и
    после приёмки глазами 22.09 описание вернули наверх.
    """
    layer.channel(1, "tg", "kittens",
                  description="Про котиков и их повадки каждый день\nРеклама: @manager")
    layer.category(1, "Животные", "zhivotnye")
    layer.go_live()
    head = heads(client.get("/tg/kittens").text)[0]
    top = TOP.search(head).group(1)
    assert has_desc(top), "описания в `.top` нет"
    assert top.index(SUB) < desc_at(top), "описание стоит выше подписи"
    after_top = head[head.index('<div class="actions">'):]
    assert not has_desc(after_top), "вторая копия описания осталась ниже шапки"


def test_description_stays_in_the_top_when_there_are_no_topics(layer, client):
    layer.channel(1, "tg", "kittens", description="Про котиков и их повадки каждый день")
    layer.go_live()
    head = heads(client.get("/tg/kittens").text)[0]
    assert '<div class="sites">' not in head
    top = TOP.search(head).group(1)
    assert has_desc(top)
    assert desc_at(top) < head.index('<div class="m-tiles">'), "описание ушло под плитки"


def test_emptied_description_leaves_no_paragraph(layer, client):
    """Опустевшее после фильтра описание не даёт ни абзаца, ни `<details>`."""
    layer.channel(1, "tg", "kittens", description="Реклама: @promo")
    layer.go_live()
    body = client.get("/tg/kittens").text
    assert "@promo" not in body
    assert DESC not in body
    assert DETAILS not in body


def test_missing_description_leaves_no_paragraph(layer, client):
    layer.channel(1, "tg", "kittens", description=None)
    layer.go_live()
    head = heads(client.get("/tg/kittens").text)[0]
    assert not has_desc(head), "у канала без описания в шапке пустая строка"


def test_sibling_description_is_filtered_too(layer, client):
    layer.channel(1, "tg", "main_channel", blogger_id=7, blogger_has_siblings=True,
                  description="Про котиков и их повадки каждый день")
    layer.channel(2, "vk", "vk_page", blogger_id=7, blogger_has_siblings=True,
                  description="Про собак и их повадки каждый день\nПо всем вопросам: @sib_manager")
    layer.sibling(1, 2)
    layer.sibling(2, 1)
    layer.go_live()
    body = client.get("/tg/main_channel").text
    assert "Про собак" in body
    assert "@sib_manager" not in body
    assert len(heads(body)) == 2
    for head in heads(body):
        top = TOP.search(head).group(1)
        assert has_desc(top), "у соседа описание не в `.top`"
        assert top.index(SUB) < desc_at(top)


# ── стиль ────────────────────────────────────────────────────────────────────

@pytest.fixture
def css(client):
    body = client.get("/assets/components.css")
    assert body.status_code == 200
    return re.sub(r"/\*.*?\*/", " ", body.text, flags=re.S)


def test_description_no_longer_carries_the_separator_line(css):
    """T-124: отбивки T-120 сняты — описание теперь часть шапки, а не хвост.

    `max-width: 62ch` тоже снят: в колонке шапки он обрезал бы свёрнутую
    строку посреди белого места.
    """
    rule = ""
    for selector, decls in re.findall(r"([^{}]+)\{([^}]*)\}", css):
        if ".desc" in [one.strip() for one in selector.split(",")]:
            rule += decls + ";"
    assert rule, "правила `.desc` нет"
    assert "border-top" not in rule
    assert "max-width" not in rule
