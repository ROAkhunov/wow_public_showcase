"""T-107: форма спарклайна, а не только его наличие.

Без базы: `sparkline()` — чистая функция координат, ряды синтетические.
Разброс 0,35% реального канала не должен читаться как обвал, а плоский ряд —
ложиться на дно заливки.
"""
import re
from datetime import date, timedelta

from app.chart import sparkline

_LINE_TOP, _LINE_BOTTOM = 35.8, 89.7
_FLAT_Y = (_LINE_TOP + _LINE_BOTTOM) / 2  # 62.75


def _history(values: list[int]) -> list[dict]:
    start = date(2026, 1, 1)
    return [{"point_date": start + timedelta(days=i), "subscribers": v}
            for i, v in enumerate(values)]


def _line_ys(line: str) -> list[float]:
    return [float(y) for _, y in re.findall(r"[ML](-?[\d.]+),(-?[\d.]+)", line)]


def test_flat_series_sits_mid_band_off_the_floor():
    chart = sparkline(_history([1_000_000] * 5))
    ys = _line_ys(chart.line)

    assert max(ys) - min(ys) < 0.2
    assert all(abs(y - _FLAT_Y) <= 0.5 for y in ys)


def test_tiny_drift_stays_almost_flat_but_inside_the_band():
    flat = sparkline(_history([1_000_000] * 5))
    drift = sparkline(_history([1_000_000, 1_000_750, 1_001_500, 1_002_250, 1_003_000]))
    big = sparkline(_history([1_000_000, 1_050_000, 1_100_000, 1_150_000, 1_200_000]))

    drift_ys, big_ys = _line_ys(drift.line), _line_ys(big.line)
    drift_span, big_span = max(drift_ys) - min(drift_ys), max(big_ys) - min(big_ys)

    for chart, ys in ((flat, _line_ys(flat.line)), (drift, drift_ys), (big, big_ys)):
        assert all(_LINE_TOP - 0.1 <= y <= _LINE_BOTTOM + 0.1 for y in ys)

    assert big_span >= 50
    assert drift_span <= big_span / 5


def test_caption_numbers_stay_honest_after_min_span():
    chart = sparkline(_history([1_000_000, 1_000_750, 1_001_500, 1_002_250, 1_003_000]))

    assert chart.minimum == 1_000_000
    assert chart.maximum == 1_003_000
