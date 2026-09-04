"""Общая обвязка тестов T-61, шов 3: «засеяли базу витрины — дёрнули адрес».

Тесты знают о сервисе ровно две вещи: что лежит в публичном слое и что он
ответил по HTTP. Ни устройство запросов, ни имена функций внутри приложения ни
одному тесту здесь не известны — переписать внутренности целиком, не тронув ни
одного теста, должно быть возможно (решение по тестированию из спеки).

База берётся из `SHOWCASE_TEST_DSN` и обязана быть локальной. Guard ниже стоит
не для красоты: в этом проекте 14.07.2026 интеграционные тесты уже писали в
боевую базу, потому что DSN в окружении оказался прод-овым.
"""
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

import pytest

# ── шов 3: какой клиентский JS на странице разрешён ──────────────────────────
#
# До T-90 правило звучало «ни одного тега script» и проверялось шестью копиями
# `assert "<script" not in body`. Счётчик Метрики его нарушил, а T-83 принесёт
# на страницы JSON-LD. Поэтому правило сужено по типу скрипта, а не по числу:
# исполняемый script на странице ровно один и он счётчик, микроразметка не в
# счёт. Живёт одной функцией — шесть расходящихся копий однажды разъедутся.

METRIKA_COUNTER = "112192205"
METRIKA_TAG_SRC = "mc.yandex.ru/metrika/tag.js"

_SCRIPT_TAG = re.compile(r"<script\b([^>]*)>", re.I)
_SCRIPT_TYPE = re.compile(r"""\btype\s*=\s*["']?([^"'\s>]+)""", re.I)


def assert_metrika_is_the_only_script(body: str, where: str = "") -> None:
    """Исполняемый `<script>` на странице ровно один, и это счётчик Метрики.

    Исполняемым считается тег без атрибута `type` либо с `type` из семейства
    javascript. `type="application/ld+json"` это данные, а не код: такие теги
    пропускаются (задел под микроразметку T-83).
    """
    executable = []
    for attrs in _SCRIPT_TAG.findall(body):
        found = _SCRIPT_TYPE.search(attrs)
        kind = (found.group(1).lower() if found else "text/javascript")
        if kind in ("text/javascript", "application/javascript", "module"):
            executable.append(attrs.strip())

    tail = f" ({where})" if where else ""
    assert len(executable) == 1, (
        f"исполняемых тегов script на странице {len(executable)}, а должен быть "
        f"один — счётчик Метрики{tail}: {executable}"
    )
    assert METRIKA_TAG_SRC in body, f"на странице нет загрузки {METRIKA_TAG_SRC}{tail}"
    assert METRIKA_COUNTER in body, f"на странице нет номера счётчика {METRIKA_COUNTER}{tail}"

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

_DSN = os.getenv("SHOWCASE_TEST_DSN") or ""
if not _DSN:
    pytest.skip(
        "SHOWCASE_TEST_DSN не задан — тесты шва 3 пропущены. "
        "Строка вида postgresql://<пользователь>@localhost/datacollector_showcase_test в .env",
        allow_module_level=True,
    )

_HOST = (urlparse(_DSN).hostname or "").lower()
if _HOST not in ("localhost", "127.0.0.1", "::1", ""):
    pytest.skip(
        f"SHOWCASE_TEST_DSN смотрит на '{_HOST}', а не на localhost — тесты пишут в базу "
        "и на нелокальной работать отказываются",
        allow_module_level=True,
    )

import psycopg2
import psycopg2.extras

LAYER_SQL = (Path(__file__).parent / "layer.sql").read_text(encoding="utf-8")

NOW = datetime.now(timezone.utc)


def _reset(dsn: str) -> None:
    conn = psycopg2.connect(dsn)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT nspname FROM pg_namespace WHERE nspname LIKE 'dump\\_%'")
            for (name,) in cur.fetchall():
                cur.execute(f'DROP SCHEMA "{name}" CASCADE')
            cur.execute("DROP TABLE IF EXISTS build_meta")
            cur.execute("""
                CREATE TABLE build_meta (
                    schema_name      TEXT PRIMARY KEY,
                    built_at         TIMESTAMPTZ NOT NULL,
                    channels_total   INTEGER NOT NULL DEFAULT 0,
                    posts_total      INTEGER NOT NULL DEFAULT 0,
                    empty_feed_share DOUBLE PRECISION NOT NULL DEFAULT 0,
                    categories_covered INTEGER NOT NULL DEFAULT 0,
                    er_covered         INTEGER NOT NULL DEFAULT 0,
                    is_live          BOOLEAN NOT NULL DEFAULT FALSE
                )
            """)
            # T-67: таблица обращений живёт в public и схему не пересоздаёт —
            # чистим руками, чтобы прогоны тестов не копили чужие строки.
            cur.execute("SELECT to_regclass('public.data_report')")
            if cur.fetchone()[0]:
                cur.execute("DELETE FROM public.data_report")
    finally:
        conn.close()


class Layer:
    """Засев публичного слоя: сборщика тут нет, строки кладутся руками.

    Так тесты быстрые и позволяют собрать состояние, которого сборщик не
    создаёт (канал без истории, лента из одного рекламного поста).
    """

    def __init__(self, dsn: str, schema: str):
        self.dsn = dsn
        self.schema = schema
        self.conn = psycopg2.connect(dsn)
        self.conn.autocommit = True
        with self.conn.cursor() as cur:
            cur.execute(LAYER_SQL.replace("{schema}", schema))

    def _insert(self, table: str, row: dict) -> None:
        cols = ", ".join(row)
        holders = ", ".join(["%s"] * len(row))
        with self.conn.cursor() as cur:
            cur.execute(f'INSERT INTO "{self.schema}".{table} ({cols}) VALUES ({holders})',
                        list(row.values()))

    def columns(self, table: str) -> list[str]:
        """Состав колонок таблицы слоя: им проверяется, чего в слое нет."""
        with self.conn.cursor() as cur:
            cur.execute("SELECT column_name FROM information_schema.columns "
                        "WHERE table_schema = %s AND table_name = %s",
                        (self.schema, table))
            return [name for (name,) in cur.fetchall()]

    # ── строки слоя ──────────────────────────────────────────────────────
    def channel(self, id: int, platform: str = "tg", username: str = "example_channel", **kw):
        row = dict(
            id=id, platform=platform, username=username,
            username_lower=username.lower(),
            url=f"https://t.me/{username}",
            display_name=f"Канал {username}", description="Описание канала",
            avatar_file=None, blogger_id=None, blogger_has_siblings=False,
            wowblogger_slug=None,
            subscribers=120_000, views_avg=None, coverage_ratio=18.5, er_percent=4.2,
            posts_30d=12, ads_30d=3, ad_share_30d=25.0,
            views_organic=22_200, views_ad=15_400, views_drop=-30.6, views_spread=18.0,
            last_post_at=NOW - timedelta(days=1), growth_90d=7.5,
            adv_total=4, adv_repeat=1, adv_window_days=180,
            stats_scraped_at=NOW - timedelta(hours=6),
            changed_at=NOW - timedelta(hours=6), built_at=NOW,
        )
        row.update(kw)
        self._insert("channel", row)
        return id

    def post(self, channel_id: int, post_id: str, days_ago: int | None = None, **kw):
        if days_ago is not None:
            kw.setdefault("posted_at", NOW - timedelta(days=days_ago))
        row = dict(
            channel_id=channel_id, platform_post_id=post_id,
            text="Текст публикации", url=f"https://t.me/c/{post_id}",
            views=20_000, likes=100, reactions=120, comments=15,
            is_ad=False, posted_at=NOW - timedelta(days=1),
        )
        row.update(kw)
        self._insert("channel_post", row)

    def history(self, channel_id: int, points: list[tuple]):
        with self.conn.cursor() as cur:
            psycopg2.extras.execute_values(
                cur, f'INSERT INTO "{self.schema}".channel_history '
                     "(channel_id, point_date, subscribers) VALUES %s",
                [(channel_id, d, s) for d, s in points])

    def category(self, channel_id: int, name: str, slug: str):
        with self.conn.cursor() as cur:
            cur.execute(f'INSERT INTO "{self.schema}".channel_category '
                        "(channel_id, category_name, category_slug) VALUES (%s, %s, %s)",
                        (channel_id, name, slug))

    def alias(self, channel_id: int, username: str, platform: str = "tg"):
        """Прежний адрес канала (T-83): по нему страница отвечает переездом."""
        with self.conn.cursor() as cur:
            cur.execute(f'INSERT INTO "{self.schema}".channel_alias '
                        "(platform, username_lower, channel_id) VALUES (%s, %s, %s)",
                        (platform, username.lower(), channel_id))

    def section(self, platform: str = "", slug: str = "", *, name: str | None = None,
                channels: int = 0, subs_median: int | None = None,
                views_median: int | None = None, ads_share: float | None = None):
        """Цифры раздела, как их кладёт сборщик: пустая строка значит «все»."""
        self._insert("section", dict(
            platform=platform, category_slug=slug, category_name=name,
            channels=channels, subs_median=subs_median, views_median=views_median,
            ads_share=ads_share))

    def sibling(self, channel_id: int, sibling_id: int):
        with self.conn.cursor() as cur:
            cur.execute(f'INSERT INTO "{self.schema}".channel_sibling '
                        "(channel_id, sibling_channel_id) VALUES (%s, %s)",
                        (channel_id, sibling_id))

    def advertiser(self, channel_id: int, label: str, rank: int = 1, **kw):
        row = dict(channel_id=channel_id, label=label, inn=None, ogrn=None,
                   entity_type="ul", placements_count=2,
                   last_placed_at=NOW - timedelta(days=10), rank=rank)
        row.update(kw)
        self._insert("channel_advertiser", row)

    # ── указатель ────────────────────────────────────────────────────────
    def go_live(self, channels_total: int | None = None, *,
                categories_covered: int | None = None, er_covered: int | None = None):
        """Сделать схему боевой.

        Покрытия считаются по засеянному слою, если их не задали руками: тесты
        про пороги (плитка ER, строка о тематиках) ставят свою цифру, остальным
        достаточно честного счёта.
        """
        with self.conn.cursor() as cur:
            cur.execute(f'SELECT count(*) FROM "{self.schema}".channel')
            total = channels_total if channels_total is not None else cur.fetchone()[0]
            cur.execute(f'SELECT count(*) FROM "{self.schema}".channel WHERE er_percent IS NOT NULL')
            er = er_covered if er_covered is not None else cur.fetchone()[0]
            cur.execute(f'SELECT count(DISTINCT channel_id) FROM "{self.schema}".channel_category')
            cats = categories_covered if categories_covered is not None else cur.fetchone()[0]
            cur.execute("UPDATE build_meta SET is_live = FALSE WHERE is_live")
            cur.execute("""
                INSERT INTO build_meta (schema_name, built_at, channels_total,
                                        categories_covered, er_covered, is_live)
                VALUES (%s, %s, %s, %s, %s, TRUE)
                ON CONFLICT (schema_name) DO UPDATE SET is_live = TRUE
            """, (self.schema, NOW, total, cats, er))
        return self


@pytest.fixture
def dsn():
    try:
        psycopg2.connect(_DSN).close()
    except psycopg2.OperationalError as exc:
        name = urlparse(_DSN).path.lstrip("/")
        pytest.skip(f"нет локальной базы витрины '{name}' ({exc.args[0].strip()[:60]}). "
                    f"Создать один раз: CREATE DATABASE {name} OWNER datacollector;")
    _reset(_DSN)
    return _DSN


@pytest.fixture
def layer(dsn):
    """Пустая схема-кандидат. Боевой её делает вызов `.go_live()`.

    Соединение закрывается за тестом: без этого каждый тест оставлял своё, и
    на девятом десятке прогон упирался в `max_connections` — падал последний
    тест, а причина выглядела как поломка в нём (T-68.1).
    """
    made = Layer(dsn, "dump_t61_test")
    try:
        yield made
    finally:
        made.conn.close()


@pytest.fixture
def make_client(dsn):
    """Клиент поверх сервиса, настроенного на тестовую базу витрины."""
    from fastapi.testclient import TestClient

    from app.main import create_app
    from app.settings import Settings

    created = []

    def _make(**kw):
        settings = Settings(dsn=dsn, **kw)
        client = TestClient(create_app(settings), raise_server_exceptions=False)
        created.append(client)
        return client

    yield _make
    for client in created:
        # Пул соединений закрывается руками: `lifespan` у TestClient
        # отрабатывает только через `with`, а `.close()` гасит транспорт, но не
        # базу — соединения копились до `max_connections` (T-68.1).
        client.app.state.db.close()
        client.close()


@pytest.fixture
def client(make_client):
    return make_client()
