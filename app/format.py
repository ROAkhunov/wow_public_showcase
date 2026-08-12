"""Как цифра выглядит на экране. Считать здесь нечего — только форматирование.

Граница простая: если функция делит, сравнивает даты или сводит несколько
колонок в одну, ей место в сборщике дампа (T-60), а не тут.
"""
from __future__ import annotations

from datetime import date, datetime

NBSP = " "

MONTHS = ("января", "февраля", "марта", "апреля", "мая", "июня",
          "июля", "августа", "сентября", "октября", "ноября", "декабря")


def num(value) -> str:
    """12345 → «12 345». Пусто → прочерк, а не ноль: это разные вещи."""
    if value is None:
        return "—"
    return f"{int(value):,}".replace(",", NBSP)


def pct(value, digits: int = 1) -> str:
    if value is None:
        return "—"
    return f"{value:.{digits}f}".replace(".", ",") + "%"


def signed(value, digits: int = 1) -> str:
    if value is None:
        return "—"
    sign = "+" if value >= 0 else "−"
    return sign + f"{abs(value):.{digits}f}".replace(".", ",") + "%"


def date_ru(value) -> str:
    if isinstance(value, datetime):
        value = value.date()
    if not isinstance(value, date):
        return "—"
    return f"{value.day} {MONTHS[value.month - 1]} {value.year}"


def clip(text: str | None, limit: int = 420) -> str:
    if not text:
        return ""
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0] + "…"


def plural(n: int, one: str, few: str, many: str) -> str:
    n = abs(int(n or 0))
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many
