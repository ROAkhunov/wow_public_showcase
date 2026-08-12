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
    span = (high - low) or 1
    step = (WIDTH - PAD * 2) / (len(points) - 1)

    def x(i: int) -> float:
        return PAD + i * step

    def y(v: int) -> float:
        return HEIGHT - PAD - (v - low) / span * (HEIGHT - PAD * 2)

    line = " ".join(
        f"{'M' if i == 0 else 'L'}{x(i):.1f},{y(v):.1f}" for i, (_, v) in enumerate(points))
    area = f"{line} L{x(len(points) - 1):.1f},{HEIGHT - PAD} L{x(0):.1f},{HEIGHT - PAD} Z"
    return Sparkline(line, area, points[0][0], points[-1][0], low, high)
