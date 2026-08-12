"""Настройки сервиса. Всё, что отличает прод от локального запуска, — здесь.

Переключатель индексации живёт одним понятным местом (спека, «Индексация закрыта
гейтом»): переменная окружения, а не строки в пяти шаблонах. По умолчанию он
**включён**, то есть сайт закрыт. Забыть выставить переменную и открыть витрину
поисковику до согласования с заказчиком таким образом нельзя.
"""
import os
from dataclasses import dataclass

PLATFORMS = ("tg", "vk", "max", "yt", "ok")

PLATFORM_NAMES = {
    "tg": "Telegram",
    "vk": "ВКонтакте",
    "max": "MAX",
    "yt": "YouTube",
    "ok": "Одноклассники",
}

#: подпись на цветном квадрате площадки. Полное имя в него не влезает: квадрат
#: 18 px, а рядом с ним и так стоит название площадки словом.
PLATFORM_CODES = {
    "tg": "TG",
    "vk": "VK",
    "max": "MAX",
    "yt": "YT",
    "ok": "OK",
}


@dataclass(frozen=True)
class Settings:
    dsn: str
    #: закрыт ли сайт от индексации. Снимается только после подтверждения PO.
    noindex: bool = True
    #: откуда nginx отдаёт аватарки коллектора (в дамп они не копируются).
    avatar_base: str = "/avatars"
    site_origin: str = "https://fomobase.ru"
    page_size: int = 50
    #: адресов в одном файле sitemap; предел протокола — 50 000.
    sitemap_chunk: int = 45_000
    pool_min: int = 1
    pool_max: int = 8


def from_env() -> Settings:
    dsn = os.getenv("SHOWCASE_DSN")
    if not dsn:
        raise RuntimeError(
            "SHOWCASE_DSN не задан: сервису нечего читать. Строка вида "
            "postgresql://<пользователь>@<хост>/showcase")
    return Settings(
        dsn=dsn,
        noindex=os.getenv("SHOWCASE_NOINDEX", "1") not in ("0", "false", "False", ""),
        avatar_base=os.getenv("SHOWCASE_AVATAR_BASE", "/avatars"),
        site_origin=os.getenv("SHOWCASE_ORIGIN", "https://fomobase.ru"),
    )
