"""Адреса наружу. Пока наружу ведёт одно место — карточка блогера в WOWBlogger.

Ссылок на WOWBlogger в шаблонах три (строка каталога, правая колонка канала,
блок соседней площадки), и собираются они здесь, а не в разметке: три ручных
строки запроса через месяц разъедутся между собой, а метки нужны одинаковые —
по ним Максим читает отчёт на своей стороне.
"""
from __future__ import annotations

from urllib.parse import quote, urlencode

#: Адрес WOWBlogger одинаков и на проде, и на локальной машине, поэтому он
#: константа, а не настройка: в `Settings` живёт только то, чем прод отличается.
WOW_BASE = "https://wowblogger.ru"


def wow_url(slug: str | None, block: str, blogger_id: int | None = None) -> str:
    """Карточка блогера в WOWBlogger с UTM-метками.

    `block` — откуда ушёл человек: `list` (строка каталога) или `card`
    (страница канала, обе кнопки на ней). `blogger_id` — числовой id из слоя,
    он же `utm_content`: по нему на стороне WOWBlogger видно, с какого блогера
    пришли, а не просто «с fomobase.ru».

    Пустой слаг — пустая строка: вести в никуда хуже, чем не вести. Кнопку в
    этом случае всё равно закрывает `{% if %}` в шаблоне.
    """
    if not slug:
        return ""
    marks = {"utm_source": "fomobase", "utm_medium": "referral", "utm_campaign": "catalog"}
    # Пустой `blogger_id` — метки нет вовсе: `utm_content=None` в отчёте хуже,
    # чем её отсутствие.
    if blogger_id is not None:
        marks["utm_content"] = str(blogger_id)
    marks["utm_term"] = block
    # `safe=""`: слаг приезжает из чужой базы и едет сегментом пути — косая
    # черта и `@` внутри него не должны разбирать адрес.
    return f"{WOW_BASE}/bloggers/{quote(str(slug), safe='')}?{urlencode(marks)}"
