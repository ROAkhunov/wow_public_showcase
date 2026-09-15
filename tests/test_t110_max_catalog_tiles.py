"""T-110: у MAX в строке каталога вместо охватных плиток — прирост и реклама.

Охваты постов MAX не считаются (T-102), и пустые «Охват поста» / «Коэф. охвата»
читались как дыра в данных. Тест держит замену плиток по платформе и то, что
строки других площадок не задело.
"""
import re

import pytest

from conftest import assert_only_allowed_scripts

pytestmark = pytest.mark.integration


def _metrics_block(body: str, platform: str, username: str) -> str:
    """Блок `.m-cols` строки конкретного канала, без соседних строк выдачи."""
    anchor = f'href="/{platform}/{username}"'
    pos = body.index(anchor)
    block = re.search(r'<div class="m-cols">(.*?)</div>\s*<div class="row-actions"',
                       body[pos:], re.S)
    assert block, f"блок метрик канала {username} не найден"
    return block.group(1)


def test_max_row_shows_growth_and_ads_instead_of_reach(layer, client):
    # er_percent=None у обоих: боевой порог `Build.show_er` сегодня не пройден
    # (T-110, разведка), и число плиток без ER — то, что видит человек сейчас.
    layer.channel(1, "max", "max_channel", growth_90d=12.3, ads_30d=4, er_percent=None)
    layer.channel(2, "tg", "tg_channel", er_percent=None)
    layer.go_live()
    body = client.get("/").text
    assert_only_allowed_scripts(body, "каталог")

    max_metrics = _metrics_block(body, "max", "max_channel")
    assert "Прирост за 90 дней" in max_metrics
    assert "Рекламных постов" in max_metrics
    assert "Охват поста" not in max_metrics
    assert "Коэф. охвата" not in max_metrics
    assert max_metrics.count('class="m"') == 4
    assert '<span class="ds-value up">+12,3%</span>' in max_metrics

    tg_metrics = _metrics_block(body, "tg", "tg_channel")
    assert "Охват поста" in tg_metrics
    assert "Коэф. охвата" in tg_metrics
    assert "Прирост за 90 дней" not in tg_metrics
    assert "Рекламных постов" not in tg_metrics
    assert tg_metrics.count('class="m"') == 4


def test_max_row_growth_dash_without_class_when_no_history(layer, client):
    layer.channel(1, "max", "max_channel", growth_90d=None)
    layer.go_live()
    body = client.get("/").text

    max_metrics = _metrics_block(body, "max", "max_channel")
    assert '<span class="ds-value">—</span>' in max_metrics
    assert "ds-value up" not in max_metrics
    assert "ds-value down" not in max_metrics
