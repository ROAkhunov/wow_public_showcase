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


#: ниже этой цифры обещание не показывается вовсе (T-97). «До 40 человек» не
#: приглашение, а повод закрыть вкладку; таких строк с кнопкой 3 110 из 36 571.
REACH_MIN = 100


def reach(value) -> str:
    """Охват в обещании «увидит до N человек». Пусто — если обещать нечего.

    Округление всегда вниз: «до N» не должно обещать больше, чем есть. Пустая
    строка вместо прочерка не случайна — по ней шаблон снимает весь блок, а не
    рисует прочерк внутри фразы.
    """
    if value is None:
        return ""
    n = int(value)
    if n < REACH_MIN:
        return ""
    if n < 1_000:
        return str(n // 10 * 10)
    if n < 1_000_000:
        if n < 10_000:
            whole, tenth = divmod(n // 100, 10)
            return f"{whole},{tenth} тыс." if tenth else f"{whole} тыс."
        return f"{n // 1000:,}".replace(",", NBSP) + " тыс."
    whole, tenth = divmod(n // 100_000, 10)
    return f"{whole},{tenth} млн" if tenth else f"{whole} млн"


def reach_promise(row) -> str:
    """Цифра обещания для строки каталога или карточки канала, готовой строкой.

    Выбор поля живёт здесь, а не в шаблонах: мест показа три (всплывашка
    каталога, подстрочник кнопки, панель карточки), и решать по-своему каждое
    из них не должно.

    Рекламный охват побеждает всегда, даже когда он мал: ноль и сорок — это
    заполненные значения, у такого канала рекламный пост столько и собирает.
    Подменить его обычным охватом значило бы пообещать за рекламный пост то,
    чего рекламный пост не даёт. Порог применяется после выбора и подмены не
    делает.
    """
    value = row["views_ad"] if row.get("views_ad") is not None else row.get("views_organic")
    return reach(value)


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
