"""Микроразметка страниц (T-83). Данные для робота, а не разметка для человека.

Строится здесь, а не в шаблонах: JSON внутри HTML собирается кавычками, и
собранный руками он ломается на первом же имени канала с кавычкой внутри.
Шаблон получает готовый словарь и печатает его фильтром `tojson`, который
экранирует и кавычки, и `<`.

Скрипты `type="application/ld+json"` — данные, а не код: правило «на витрине
нет клиентского JS» они не нарушают, и тест шва 3 проверяет именно тип.
"""
from __future__ import annotations

SITE_NAME = "Fomobase"


def organization(origin: str) -> dict:
    return {
        "@context": "https://schema.org",
        "@type": "Organization",
        "name": SITE_NAME,
        "url": origin + "/",
        "logo": f"{origin}/assets/apple-touch-icon.png",
        "description": "Каталог каналов: аудитория, охваты и реклама по данным "
                       "открытых источников.",
    }


def website(origin: str) -> dict:
    return {
        "@context": "https://schema.org",
        "@type": "WebSite",
        "name": SITE_NAME,
        "url": origin + "/",
    }


def breadcrumbs(origin: str, trail: list[tuple[str, str | None]]) -> dict:
    """Крошки для робота. `trail` — пары «название, адрес», последний без адреса.

    Нарисованы крошки давно, но для робота это просто ссылки: цепочку он видит
    только разметкой.
    """
    items = []
    for position, (name, path) in enumerate(trail, start=1):
        item = {"@type": "ListItem", "position": position, "name": name}
        if path:
            item["item"] = origin + path
        items.append(item)
    return {"@context": "https://schema.org", "@type": "BreadcrumbList",
            "itemListElement": items}


def item_list(origin: str, name: str, rows: list[dict], *, offset: int = 0) -> dict:
    """Список каналов страницы каталога. Позиция сквозная, а не от единицы:
    на пятой странице первый канал не первый в списке."""
    return {
        "@context": "https://schema.org",
        "@type": "ItemList",
        "name": name,
        "itemListElement": [
            {"@type": "ListItem", "position": offset + i,
             "name": row["display_name"] or row["username"],
             "url": f"{origin}/{row['platform']}/{row['username_lower']}"}
            for i, row in enumerate(rows, start=1)
        ],
    }
