"""Чтение публичного слоя. Единственное место в сервисе, которое знает SQL.

Слой лежит не в фиксированной схеме: сборщик (T-60) пишет каждую сборку в новую
схему `dump_<штамп>`, а боевой её делает строка `public.build_meta` с `is_live`.
Старая схема дропается сразу после переключения, поэтому имя схемы нельзя
запоминать надолго — оно резолвится на каждый запрос. Одна лишняя строка из
`build_meta` по индексу дешевле, чем страница, которая после ротации ходит в
снесённую схему.

Сервис ничего не вычисляет: каждый метод возвращает строки как есть, а деления и
проценты уже посчитаны сборщиком.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

import psycopg2
import psycopg2.extras
import psycopg2.pool

from app.query import FLAGS, RANGES, SORTS, Filters


class ShowcaseUnavailable(RuntimeError):
    """Боевой схемы нет: дамп ни разу не собирался или указатель пуст."""


@dataclass(frozen=True)
class Build:
    schema: str
    built_at: Any
    channels_total: int = 0
    categories_covered: int = 0
    er_covered: int = 0

    #: доля заполненности, ниже которой метрика с экрана снимается.
    COVERAGE_FLOOR = 0.5

    @property
    def show_er(self) -> bool:
        """Показывать ли ER вообще.

        Метрика не вырезана из кода, а погашена порогом: сегодня она заполнена
        у 37 каналов из 140 015, и плитка с прочерком на 99,97% страниц хуже её
        отсутствия. Починят расчёт в коллекторе — метрика вернётся сама, без
        правки витрины.

        ВНИМАНИЕ (T-68.1): включение флага само по себе строку выдачи не
        починит. Блок `.m-cols` в строке рассчитан на четыре колонки шириной
        400 px; пятая метрика перенесётся на вторую строку внутри блока и
        разъедет высоту строк. Вернётся ER — сначала правится сетка строки в
        `design-system/components.css`, потом снимается порог.
        """
        return bool(self.channels_total) and (
            self.er_covered / self.channels_total > self.COVERAGE_FLOOR)


@dataclass(frozen=True)
class Page:
    rows: list[dict]
    total: int
    number: int
    size: int

    #: сколько соседей текущей страницы показывать номерами в пагинации.
    WINDOW_SPAN = 2

    @property
    def pages(self) -> int:
        return pages_in(self.total, self.size)

    @property
    def has_next(self) -> bool:
        return self.number < self.pages

    @property
    def window(self) -> list[int]:
        """Номера страниц для пагинации, `0` вместо пропущенного куска.

        Все номера в строку не помещаются: каталог это 2 700 страниц. Показываем
        первую, последнюю и соседей текущей — краулеру хватает, чтобы шагом за
        шагом дойти до конца, а человеку чтобы понять, где он.
        """
        last = self.pages
        shown = {1, last}
        shown |= {n for n in range(self.number - self.WINDOW_SPAN,
                                   self.number + self.WINDOW_SPAN + 1)
                  if 1 <= n <= last}
        out: list[int] = []
        for n in sorted(shown):
            if out and n - out[-1] > 1:
                out.append(0)
            out.append(n)
        return out


def pages_in(total: int, size: int) -> int:
    """Сколько страниц (или кусков карты сайта) выйдет из `total` строк."""
    return max(1, -(-total // size))


class Showcase:
    def __init__(self, dsn: str, pool_min: int = 1, pool_max: int = 8):
        self._pool = psycopg2.pool.ThreadedConnectionPool(pool_min, pool_max, dsn)

    def close(self) -> None:
        self._pool.closeall()

    # ── соединение без привязки к боевой схеме ────────────────────────────
    @contextmanager
    def _raw_cursor(self):
        """Курсор для запросов к `public`, которым живая схема дампа не нужна.

        Обращения (T-67) обязаны переживать состояние «дамп ни разу не
        собирался» — `public.data_report` их не теряет именно потому, что не
        зависит от `build_meta`. Через `_cursor()` эта независимость сломалась
        бы: он падает `ShowcaseUnavailable`, если живой схемы нет.
        """
        conn = self._pool.getconn()
        try:
            conn.autocommit = True
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                yield cur
        finally:
            self._pool.putconn(conn)

    # ── соединение с указателем на боевую схему ──────────────────────────
    @contextmanager
    def _cursor(self):
        conn = self._pool.getconn()
        try:
            conn.autocommit = True
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                # Схема указателя пишется явно: соединение живёт в пуле, а
                # search_path на нём остаётся от прошлого запроса и увёл бы этот
                # SELECT в схему дампа, где build_meta нет.
                cur.execute("SELECT schema_name, built_at, channels_total, "
                            "categories_covered, er_covered "
                            "FROM public.build_meta WHERE is_live")
                row = cur.fetchone()
                if not row:
                    raise ShowcaseUnavailable("в build_meta нет боевой схемы")
                cur.execute('SET search_path TO "%s"' % row["schema_name"].replace('"', ""))
                yield cur, Build(row["schema_name"], row["built_at"],
                                 row["channels_total"], row["categories_covered"],
                                 row["er_covered"])
        finally:
            self._pool.putconn(conn)

    def build(self) -> Build:
        with self._cursor() as (_, build):
            return build

    # ── страница канала ──────────────────────────────────────────────────
    def channel(self, platform: str, username: str, *, feed_page: int = 1,
                feed_size: int = 10) -> dict | None:
        """Канал со всем, что рисуется на его странице, или None.

        Площадки автора приезжают полными блоками (решение PO 27.07): у соседа
        свои метрики, история, тематики, рекламодатели и лента. Всё это берётся
        ПАКЕТНО — один запрос на всю семью по каждому виду данных, а не по
        запросу на соседа: иначе страница растёт с шести запросов до тридцати.
        """
        with self._cursor() as (cur, build):
            cur.execute("""
                SELECT * FROM channel
                WHERE platform = %s AND username_lower = lower(%s)
            """, (platform, username))
            channel = cur.fetchone()
            if not channel:
                return None
            cid = channel["id"]

            cur.execute("""
                SELECT c.* FROM channel_sibling s JOIN channel c ON c.id = s.sibling_channel_id
                WHERE s.channel_id = %s
                ORDER BY c.subscribers DESC NULLS LAST, c.id
            """, (cid,))
            siblings = cur.fetchall()
            family = [channel] + siblings
            ids = [row["id"] for row in family]

            history = self._by_channel(cur, """
                SELECT channel_id, point_date, subscribers FROM channel_history
                WHERE channel_id = ANY(%s) AND subscribers IS NOT NULL
                ORDER BY channel_id, point_date
            """, ids)
            categories = self._by_channel(cur, """
                SELECT channel_id, category_name, category_slug FROM channel_category
                WHERE channel_id = ANY(%s) ORDER BY channel_id, category_name
            """, ids)
            advertisers = self._by_channel(cur, """
                SELECT channel_id, label, inn, ogrn, entity_type, placements_count,
                       last_placed_at
                FROM channel_advertiser WHERE channel_id = ANY(%s) ORDER BY channel_id, rank
            """, ids)
            # Лента соседа всегда первая страница: «Ещё» у него ведёт на его
            # собственный адрес, а не на следующую страницу этой семьи.
            posts = self._by_channel(cur, """
                SELECT * FROM (
                    SELECT *, row_number() OVER (PARTITION BY channel_id
                        ORDER BY posted_at DESC NULLS LAST, platform_post_id DESC) AS n
                    FROM channel_post WHERE channel_id = ANY(%s)) t
                WHERE n <= %s ORDER BY channel_id, n
            """, ids, feed_size * feed_page)

            for row in family:
                own = posts.get(row["id"], [])
                shown = own[(feed_page - 1) * feed_size:] if row["id"] == cid else own[:feed_size]
                row["history"] = history.get(row["id"], [])
                row["categories"] = categories.get(row["id"], [])
                row["advertisers"] = advertisers.get(row["id"], [])
                row["posts"] = shown[:feed_size]
                row["built_at"] = build.built_at

            channel["siblings"] = siblings
            channel["family"] = family
            channel["feed_pages"] = self._feed_pages(cur, cid, feed_size)
            return channel

    @staticmethod
    def _by_channel(cur, sql: str, ids: list[int], *extra) -> dict[int, list[dict]]:
        """Разложить пакетную выборку по каналам, сохранив порядок строк."""
        cur.execute(sql, [ids, *extra])
        out: dict[int, list[dict]] = {}
        for row in cur.fetchall():
            out.setdefault(row["channel_id"], []).append(row)
        return out

    @staticmethod
    def _feed_pages(cur, cid: int, size: int) -> int:
        cur.execute("SELECT count(*) AS n FROM channel_post WHERE channel_id = %s", (cid,))
        return pages_in(cur.fetchone()["n"], size)

    # ── каталог ──────────────────────────────────────────────────────────
    def catalog(self, platform: str | None = None, category: str | None = None,
                page: int = 1, size: int = 50,
                filters: Filters | None = None) -> Page:
        filters = filters or Filters()
        category = category or filters.category
        where, params = [], []
        if platform:
            where.append("c.platform = %s")
            params.append(platform)
        # Тематика материализуется первой, а не джойнится. С обычным JOIN после
        # появления индексов каталога планировщик идёт по индексу подписчиков и
        # пробует тематику у каждой строки: 10 292 строки ради 50 нужных, 168 мс
        # против 6. Индекс (category_slug, channel_id) плана не меняет — лечится
        # именно форма запроса (замер 20.08 на 140 015 каналах).
        head = ""
        if category:
            head = ("WITH ids AS MATERIALIZED ("
                    " SELECT channel_id FROM channel_category WHERE category_slug = %s) ")
            where.append("c.id IN (SELECT channel_id FROM ids)")
            params.insert(0, category)
        for key, value in filters.ranges.items():
            column, edge, _ = RANGES[key]
            where.append(f"c.{column} {'>=' if edge == 'min' else '<='} %s")
            params.append(value)
        for flag in filters.flags:
            where.append(f"c.{FLAGS[flag]}")
        clause = ("WHERE " + " AND ".join(where)) if where else ""
        order = f"c.{SORTS[filters.sort]} DESC NULLS LAST, c.id"

        with self._cursor() as (cur, _):
            cur.execute(f"{head}SELECT count(*) AS n FROM channel c {clause}", params)
            total = cur.fetchone()["n"]
            # Страницы за последней не существует, и выбирать для неё строки
            # незачем: `?page=100000` увёл бы базу в OFFSET на пять миллионов
            # строк, а ответ всё равно 404. Обход каталога краулером и без того
            # самая частая нагрузка на этот запрос.
            if page > pages_in(total, size):
                return Page([], total, page, size)
            cur.execute(f"""
                {head}SELECT c.id, c.platform, c.username, c.username_lower, c.display_name,
                       c.avatar_file, c.blogger_has_siblings, c.wowblogger_slug,
                       c.subscribers, c.views_organic, c.coverage_ratio, c.er_percent,
                       c.posts_30d, c.ad_share_30d, c.last_post_at
                FROM channel c {clause}
                ORDER BY {order}
                LIMIT %s OFFSET %s
            """, params + [size, (page - 1) * size])
            rows = cur.fetchall()

            # Мини-строка площадок автора — второй запрос на страницу, одним
            # батчем по всем строкам сразу (T-66), а не по строке: то же
            # правило, что у семьи канала на странице (`channel()` выше).
            ids = [r["id"] for r in rows if r["blogger_has_siblings"]]
            siblings = self._by_channel(cur, """
                SELECT s.channel_id, c.platform, c.username_lower
                FROM channel_sibling s JOIN channel c ON c.id = s.sibling_channel_id
                WHERE s.channel_id = ANY(%s)
                ORDER BY s.channel_id, c.subscribers DESC NULLS LAST, c.id
            """, ids) if ids else {}
            for r in rows:
                r["siblings"] = siblings.get(r["id"], [])

            return Page(rows, total, page, size)

    def categories(self) -> list[dict]:
        with self._cursor() as (cur, _):
            cur.execute("""
                SELECT category_slug, min(category_name) AS category_name, count(*) AS channels
                FROM channel_category GROUP BY category_slug
                ORDER BY count(*) DESC, min(category_name)
            """)
            return cur.fetchall()

    def category_name(self, slug: str) -> str | None:
        with self._cursor() as (cur, _):
            cur.execute("SELECT category_name FROM channel_category "
                        "WHERE category_slug = %s LIMIT 1", (slug,))
            row = cur.fetchone()
            return row["category_name"] if row else None

    def platform_counts(self) -> dict[str, int]:
        with self._cursor() as (cur, _):
            cur.execute("SELECT platform, count(*) AS n FROM channel GROUP BY platform")
            return {r["platform"]: r["n"] for r in cur.fetchall()}

    # ── обращения «Сообщить о неточности» (T-67) ───────────────────────────
    def channel_name(self, platform: str, username_lower: str) -> str | None:
        """Показываемое имя канала для формы обращения, или None, если пары
        нет в живой схеме — обращение всё равно принимается."""
        with self._cursor() as (cur, _):
            cur.execute("SELECT display_name FROM channel "
                        "WHERE platform = %s AND username_lower = %s",
                        (platform, username_lower))
            row = cur.fetchone()
            return row["display_name"] if row else None

    def submit_report(self, *, platform: str | None, username_lower: str | None,
                      kind: str, details: str, email: str | None,
                      referrer: str | None) -> None:
        """Записать обращение в `public.data_report` — единственная запись
        сервиса витрины в базу, всё остальное здесь чтение.

        Имя канала резолвится через живую схему дампа отдельным, необязательным
        шагом: если дампа сейчас нет (`ShowcaseUnavailable`), обращение всё
        равно должно сохраниться, просто без показываемого названия — public
        не зависит от ротации дампа и не имеет права падать вместе с ней.
        """
        display_name = None
        if platform and username_lower:
            try:
                display_name = self.channel_name(platform, username_lower)
            except ShowcaseUnavailable:
                display_name = None
        with self._raw_cursor() as cur:
            cur.execute("""
                INSERT INTO public.data_report
                    (platform, username_lower, display_name, kind, details, email, referrer)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (platform, username_lower, display_name, kind, details, email, referrer))

    # ── sitemap ──────────────────────────────────────────────────────────
    def channels_total(self) -> int:
        with self._cursor() as (cur, _):
            cur.execute("SELECT count(*) AS n FROM channel")
            return cur.fetchone()["n"]

    def sitemap_chunk(self, number: int, size: int) -> list[dict]:
        with self._cursor() as (cur, _):
            # В карту едет только нижний регистр: адрес у страницы один.
            cur.execute("""
                SELECT platform, username_lower, built_at FROM channel
                ORDER BY id LIMIT %s OFFSET %s
            """, (size, (number - 1) * size))
            return cur.fetchall()
