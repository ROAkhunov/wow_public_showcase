"""Спарклайн подписчиков: точки истории → координаты для inline-SVG.

Клиентского JS на страницах нет по решению об архитектуре, поэтому график
рисуется на сервере обычным `<path>`. Это не расчёт метрики: сами точки уже
посчитаны сборщиком, здесь только перевод чисел в координаты картинки.

Меньше трёх точек — графика нет вовсе (спека): пустой график хуже отсутствующего.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

WIDTH, HEIGHT, PAD = 900, 150, 26
MIN_POINTS = 3

# Линия живёт не по всей рабочей полосе, а с отступами от её краёв: воздух
# сверху, чтобы пик не упирался в рамку, и подложка снизу, чтобы даже
# плоский ряд не касался дна заливки (T-107).
_LINE_TOP_FRAC = 0.10
_LINE_BOTTOM_FRAC = 0.35

# Минимальный размах шкалы: без него доли процента растягиваются на всю
# полосу линии и читаются как обвал (T-107). Доля от максимума ряда,
# применяется симметрично вокруг середины фактического размаха.
_MIN_SPAN_FRAC = 0.03


@dataclass(frozen=True)
class Sparkline:
    line: str
    area: str
    first_date: date
    last_date: date
    minimum: int
    maximum: int


def sparkline(history: list[dict]) -> Sparkline | None:
    points = [(row["point_date"], row["subscribers"]) for row in history
              if row.get("subscribers")]
    if len(points) < MIN_POINTS:
        return None

    values = [v for _, v in points]
    low, high = min(values), max(values)

    scale_low, scale_high = low, high
    min_span = _MIN_SPAN_FRAC * high
    if high - low < min_span:
        center = (high + low) / 2
        scale_low, scale_high = center - min_span / 2, center + min_span / 2
    span = scale_high - scale_low

    step = (WIDTH - PAD * 2) / (len(points) - 1)
    line_top = PAD + _LINE_TOP_FRAC * (HEIGHT - PAD * 2)
    line_bottom = HEIGHT - PAD - _LINE_BOTTOM_FRAC * (HEIGHT - PAD * 2)

    def x(i: int) -> float:
        return PAD + i * step

    def y(v: int) -> float:
        return line_bottom - (v - scale_low) / span * (line_bottom - line_top)

    line = " ".join(
        f"{'M' if i == 0 else 'L'}{x(i):.1f},{y(v):.1f}" for i, (_, v) in enumerate(points))
    area = f"{line} L{x(len(points) - 1):.1f},{HEIGHT - PAD} L{x(0):.1f},{HEIGHT - PAD} Z"
    return Sparkline(line, area, points[0][0], points[-1][0], low, high)
