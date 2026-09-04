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


#: имя сайта в заголовке страницы. В каталоге бренд стоял с самого начала, на
#: карточке появился с T-83.
BRAND = "Fomobase"

#: потолок длины заголовка страницы. Дальше поисковик обрезает его сам, и
#: обрезает не там, где нам нужно.
TITLE_LIMIT = 70


def channel_title(name: str, username: str, platform: str, limit: int = TITLE_LIMIT) -> str:
    """Заголовок страницы канала: имя, площадка, @имя_на_площадке и бренд.

    Запрос человек набирает как «durov телеграм статистика», а в заголовке до
    T-83 не было ни площадки, ни `@username`, ни бренда. Всё вместе в 70
    символов помещается не всегда, поэтому лишнее отваливается по порядку: сначала
    бренд, потом `@имя`, и только потом подрезается имя канала — оно и есть то,
    что человек ищет глазами в выдаче.
    """
    name = " ".join((name or username or "").split())
    for tail in (f"@{username} — статистика канала в {platform} · {BRAND}",
                 f"@{username} — статистика канала в {platform}",
                 f"— статистика канала в {platform} · {BRAND}",
                 f"— статистика канала в {platform}"):
        room = limit - len(tail) - 1
        if room >= 12:
            break
    return f"{clip(name, room - 1) if len(name) > room else name} {tail}"


def section_note(row) -> str | None:
    """Абзац с цифрами под заголовком раздела.

    Разделы были заголовком, строкой подзаголовка и таблицей — под запросы это
    тонко. Цифры приезжают колонками из дампа: сервис их не считает, а
    печатает.
    """
    if not row or not row.get("channels"):
        return None
    count = row["channels"]
    parts = [f"В подборке {num(count)} {plural(count, 'канал', 'канала', 'каналов')}"]
    if row.get("views_median"):
        parts.append(f"медианный охват поста {num(row['views_median'])}")
    if row.get("ads_share") is not None:
        parts.append(f"рекламная история есть у {pct(row['ads_share'], 0)} каналов")
    return ", ".join(parts) + "."
