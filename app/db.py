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


class ShowcaseUnavailable(RuntimeError):
    """Боевой схемы нет: дамп ни разу не собирался или указатель пуст."""


@dataclass(frozen=True)
class Build:
    schema: str
    built_at: Any


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
                cur.execute("SELECT schema_name, built_at FROM public.build_meta WHERE is_live")
                row = cur.fetchone()
                if not row:
                    raise ShowcaseUnavailable("в build_meta нет боевой схемы")
                cur.execute('SET search_path TO "%s"' % row["schema_name"].replace('"', ""))
                yield cur, Build(row["schema_name"], row["built_at"])
        finally:
            self._pool.putconn(conn)

    def build(self) -> Build:
        with self._cursor() as (_, build):
            return build

    # ── страница канала ──────────────────────────────────────────────────
    def channel(self, platform: str, username: str) -> dict | None:
        """Канал со всем, что рисуется на его странице, или None."""
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
                SELECT * FROM channel_post WHERE channel_id = %s
                ORDER BY posted_at DESC NULLS LAST, platform_post_id DESC
            """, (cid,))
            channel["posts"] = cur.fetchall()

            cur.execute("""
                SELECT point_date, subscribers FROM channel_history
                WHERE channel_id = %s AND subscribers IS NOT NULL
                ORDER BY point_date
            """, (cid,))
            channel["history"] = cur.fetchall()

            cur.execute("""
                SELECT category_name, category_slug FROM channel_category
                WHERE channel_id = %s ORDER BY category_name
            """, (cid,))
            channel["categories"] = cur.fetchall()

            cur.execute("""
                SELECT c.platform, c.username_lower, c.display_name, c.subscribers
                FROM channel_sibling s JOIN channel c ON c.id = s.sibling_channel_id
                WHERE s.channel_id = %s
                ORDER BY c.subscribers DESC NULLS LAST
            """, (cid,))
            channel["siblings"] = cur.fetchall()

            cur.execute("""
                SELECT label, inn, ogrn, entity_type, placements_count, last_placed_at
                FROM channel_advertiser WHERE channel_id = %s ORDER BY rank
            """, (cid,))
            channel["advertisers"] = cur.fetchall()

            channel["built_at"] = build.built_at
            return channel

    # ── каталог ──────────────────────────────────────────────────────────
    def catalog(self, platform: str | None = None, category: str | None = None,
                page: int = 1, size: int = 50) -> Page:
        where, params = [], []
        join = ""
        if platform:
            where.append("c.platform = %s")
            params.append(platform)
        if category:
            join = "JOIN channel_category cc ON cc.channel_id = c.id"
            where.append("cc.category_slug = %s")
            params.append(category)
        clause = ("WHERE " + " AND ".join(where)) if where else ""

        with self._cursor() as (cur, _):
            cur.execute(f"SELECT count(*) AS n FROM channel c {join} {clause}", params)
            total = cur.fetchone()["n"]
            # Страницы за последней не существует, и выбирать для неё строки
            # незачем: `?page=100000` увёл бы базу в OFFSET на пять миллионов
            # строк, а ответ всё равно 404. Обход каталога краулером и без того
            # самая частая нагрузка на этот запрос.
            if page > pages_in(total, size):
                return Page([], total, page, size)
            cur.execute(f"""
                SELECT c.platform, c.username, c.username_lower, c.display_name,
                       c.avatar_file,
                       c.subscribers, c.views_organic, c.coverage_ratio, c.er_percent,
                       c.posts_30d, c.ad_share_30d, c.last_post_at
                FROM channel c {join} {clause}
                ORDER BY c.subscribers DESC NULLS LAST, c.id
                LIMIT %s OFFSET %s
            """, params + [size, (page - 1) * size])
            return Page(cur.fetchall(), total, page, size)

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
