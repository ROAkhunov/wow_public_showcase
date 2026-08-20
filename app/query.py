"""Адрес списка: разбор фильтров, нормализация и сборка обратно.

Единственное место, которое знает про параметры каталога. Знает целиком: белый
список ключей, порядок, границы значений, что считать «условие не задано» и как
собрать адрес обратно. Всё остальное — маршруты, шаблоны, SQL — получает готовый
`Filters` и не догадывается, откуда он взялся.

Так устроено ради одного правила: **у списка ровно один адрес**. Свободные поля
«от» и «до» (решение PO 20.08) дают бесконечно много написаний одного и того же
условия — переставленные ключи, пустые поля формы, мусор, отрицательные числа,
доля рекламы больше ста, явно выписанная сортировка по умолчанию. Все они
приводятся к одному написанию, а несовпадение отдаётся редиректом 301.

Номер страницы сюда не входит: `page` и `posts` это не фильтры, а номера
страниц, и мусор в них означает несуществующую страницу, то есть 404.
"""
from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote

#: Сортировки каталога. Ключ — то, что стоит в адресе; значение — колонка слоя.
#: ER здесь нет: метрика заполнена у 37 каналов из 140 015, сортировать по ней
#: нечего. Вернётся вместе с плиткой, когда покрытие перевалит за половину.
SORTS = {
    "subscribers": "subscribers",
    "views": "views_organic",
    "coverage": "coverage_ratio",
    "fresh": "last_post_at",
}
SORT_NAMES = {
    "subscribers": "по подписчикам",
    "views": "по охвату",
    "coverage": "по коэффициенту охвата",
    "fresh": "по свежести",
}
DEFAULT_SORT = "subscribers"

#: Диапазоны: ключ в адресе → (колонка слоя, край, потолок значения).
#: Потолок у доли рекламы — сто процентов: «до 150%» это тот же список, что
#: «до 100%», и жить ему по второму адресу незачем.
RANGES = {
    "subs_min": ("subscribers", "min", None),
    "subs_max": ("subscribers", "max", None),
    "views_min": ("views_organic", "min", None),
    "views_max": ("views_organic", "max", None),
    "ads_min": ("ad_share_30d", "min", 100),
    "ads_max": ("ad_share_30d", "max", 100),
}
FLAGS = {
    "has_ads": "adv_total > 0",
    "has_siblings": "blogger_has_siblings",
}

#: Порядок ключей в адресе — часть контракта: переставленные ключи это тот же
#: список, и приводятся они именно к этому написанию.
ORDER = ("subs_min", "subs_max", "views_min", "views_max", "ads_min", "ads_max",
         "has_ads", "has_siblings", "cat", "sort")

#: Ключи, которые разбираются не здесь, но и мусором не считаются.
PAGE_KEYS = ("page", "posts")


@dataclass(frozen=True)
class Filters:
    """Условие отбора, как его понял сервис. Пустой — список без фильтров."""

    ranges: dict[str, int] = None          # ключ адреса → значение
    flags: tuple[str, ...] = ()
    category: str | None = None
    sort: str = DEFAULT_SORT

    def __post_init__(self):
        if self.ranges is None:
            object.__setattr__(self, "ranges", {})

    @property
    def active(self) -> bool:
        """Есть ли в адресе хоть что-то, кроме раздела и первой страницы.

        По этому признаку страница закрывается от индекса и не кэшируется:
        фильтрованных написаний много, а содержимое у них пересекается.
        """
        return bool(self.ranges or self.flags or self.category
                    or self.sort != DEFAULT_SORT)

    def query(self, page: int = 1) -> str:
        """Собрать строку запроса в каноническом порядке."""
        pairs = []
        for key in ORDER:
            if key in self.ranges:
                pairs.append((key, str(self.ranges[key])))
            elif key in FLAGS and key in self.flags:
                pairs.append((key, "1"))
            elif key == "cat" and self.category:
                pairs.append((key, quote(self.category, safe="")))
            elif key == "sort" and self.sort != DEFAULT_SORT:
                pairs.append((key, self.sort))
        if page > 1:
            pairs.append(("page", str(page)))
        return "&".join(f"{k}={v}" for k, v in pairs)

    def url(self, base: str, page: int = 1) -> str:
        qs = self.query(page)
        return f"{base}?{qs}" if qs else base

    def with_sort(self, sort: str) -> "Filters":
        """Тот же отбор с другой сортировкой — для ссылок в панели над списком."""
        return Filters(self.ranges, self.flags, self.category, sort)

    def without(self, key: str) -> "Filters":
        """Тот же отбор без одного условия — для ссылки «убрать» на теге.

        Крестик из компонента дизайн-системы живёт на клиентском обработчике,
        а здесь его роль исполняет обычная ссылка на соседний адрес.
        """
        if key in self.ranges:
            rest = {k: v for k, v in self.ranges.items() if k != key}
            return Filters(rest, self.flags, self.category, self.sort)
        if key in self.flags:
            return Filters(self.ranges, tuple(f for f in self.flags if f != key),
                           self.category, self.sort)
        if key == "cat":
            return Filters(self.ranges, self.flags, None, self.sort)
        if key == "sort":
            return Filters(self.ranges, self.flags, self.category, DEFAULT_SORT)
        return self


def _number(raw: str, ceiling: int | None) -> int | None:
    """Целое из поля формы, или None, если условие не задано.

    Мусор и пустая строка — это «не задано», а не ошибка: поля формы уезжают в
    адрес пустыми на каждой отправке, и отвечать на это ошибкой значит ругаться
    на человека за то, что он не заполнил необязательное поле.
    """
    raw = raw.strip()
    if not raw:
        return None
    negative = raw.startswith("-")
    digits = raw[1:] if negative else raw
    if not (digits.isascii() and digits.isdigit()):
        return None
    value = -int(digits) if negative else int(digits)
    if value < 0:
        value = 0
    if ceiling is not None and value > ceiling:
        value = ceiling
    return value


def parse(params, *, allow_category: bool = True) -> tuple[Filters, bool]:
    """Разобрать параметры адреса.

    Возвращает отбор и признак «адрес написан не канонически»: по нему маршрут
    отвечает 301, а не рисует страницу. Само сравнение делает вызывающий —
    он же знает базовый адрес и номер страницы.
    """
    ranges: dict[str, int] = {}
    canonical = True

    for key, (_, edge, ceiling) in RANGES.items():
        if key not in params:
            continue
        value = _number(params[key], ceiling)
        # Нижняя граница в нуле не сужает ничего: это то же самое, что её не
        # задавать, и жить этому списку по второму адресу незачем.
        if value is None or (edge == "min" and value <= 0):
            canonical = False
            continue
        if params[key].strip() != str(value):
            canonical = False
        ranges[key] = value

    flags = tuple(k for k in FLAGS if params.get(k) == "1")
    for key in FLAGS:
        if key in params and params[key] != "1":
            canonical = False

    category = None
    if "cat" in params:
        slug = params["cat"].strip()
        if slug and allow_category:
            category = slug
        else:
            canonical = False

    sort = params.get("sort", DEFAULT_SORT)
    if sort not in SORTS or ("sort" in params and sort == DEFAULT_SORT):
        # Неизвестная сортировка и явно выписанная сортировка по умолчанию —
        # это один и тот же список, что и адрес без параметра.
        if "sort" in params:
            canonical = False
        sort = DEFAULT_SORT

    # Всё, чего нет в белом списке: чужие метки кампаний, хвосты рассылок,
    # перебор параметров. Содержимое от них не меняется, а адресов становится
    # бесконечно много.
    known = set(RANGES) | set(FLAGS) | {"cat", "sort"} | set(PAGE_KEYS)
    if any(k not in known for k in params):
        canonical = False

    return Filters(ranges, flags, category, sort), canonical
