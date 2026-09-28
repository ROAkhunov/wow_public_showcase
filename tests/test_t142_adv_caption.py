"""T-142: подпись блока рекламодателей.

Число размещений в строке рекламодателя путало: читалось как «сколько раз
купили рекламу за всё время», а считалось за окно сборщика. Из строки его
убрали, дата подписана «последний пост», окно ушло в заголовок блока, подпись
под списком стала одной фразой про маркировку. Политика обещает ровно то, что
видно на странице: дату последнего размещения, без числа.

Порядок строк по `placements_count` и `rank` не трогали: его держит сборщик.
"""
import re

import pytest

pytestmark = pytest.mark.integration

PANEL = re.compile(r'<section class="panel">\s*<h2>Кто рекламировался.*?</section>', re.S)
ADV_LINE = re.compile(r'<div class="adv-line">(.*?)</div>', re.S)
CAPTION = "Рекламодатель определён по маркировке рекламы в постах канала"


def text_of(html: str) -> str:
    return " ".join(re.sub(r"<[^>]+>", " ", html).replace("\xa0", " ").split())


def adv_panel(body: str) -> str:
    found = PANEL.search(body)
    assert found, "блок рекламодателей не найден"
    return found.group(0)


def seed(layer, window, with_advertisers=True):
    layer.channel(1, username="adv_channel", adv_window_days=window)
    if with_advertisers:
        layer.advertiser(1, "ООО «Кондитер»", rank=1, inn="7712345678",
                         ogrn="1027700000000", placements_count=155)
        layer.advertiser(1, "ИП", rank=2, entity_type="fl",
                         ogrn="304770000000000", placements_count=3)
    layer.go_live()


def page(client) -> str:
    resp = client.get("/tg/adv_channel")
    assert resp.status_code == 200
    return resp.text


# ── строка рекламодателя ─────────────────────────────────────────────────────

def test_line_has_no_placements_count_and_says_last_post(layer, client):
    seed(layer, 180)
    lines = ADV_LINE.findall(page(client))
    assert len(lines) == 2
    for line in lines:
        text = text_of(line)
        assert "размещени" not in text
        assert "155" not in text
        assert "последний пост" in text
        assert "последнее" not in text


# ── заголовок из окна ────────────────────────────────────────────────────────

@pytest.mark.parametrize("window, title", [
    (180, "Кто рекламировался за полгода"),
    (90, "Кто рекламировался за 90 дней"),
])
def test_title_follows_window(layer, client, window, title):
    seed(layer, window)
    panel = text_of(adv_panel(page(client)))
    assert panel.startswith(title)


def test_title_without_advertisers_and_window(layer, client):
    seed(layer, None, with_advertisers=False)
    body = page(client)
    panel = text_of(adv_panel(body))
    assert panel.startswith("Кто рекламировался за полгода")
    assert "Рекламных размещений с маркировкой не найдено" in panel
    assert "None" not in text_of(body)


# ── подпись под списком ──────────────────────────────────────────────────────

def test_caption_is_one_phrase_about_marking(layer, client):
    seed(layer, 180)
    panel = text_of(adv_panel(page(client)))
    assert CAPTION in panel
    assert "180" not in panel
    assert "реестр" not in panel


# ── политика ─────────────────────────────────────────────────────────────────

def test_privacy_promises_only_last_date(layer, client):
    layer.go_live()
    body = text_of(client.get("/privacy").text)
    assert "число размещений" not in body
    assert "У всех рекламодателей указывается дата последнего размещения" in body
    assert "Редакция от 28 сентября 2026 года" in body
