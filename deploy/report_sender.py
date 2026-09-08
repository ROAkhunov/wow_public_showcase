#!/usr/bin/env python3
"""T-67: разбор очереди обращений — раз в 5 минут шлёт в notify.sh, ставит отметку.

Не веб-процесс: ему незачем читать `/opt/scripts/.env` с боевыми токенами
notify.sh (сам notify.sh их читает сам), а форма не должна ждать сеть Телеграма
и падать вместе с ним. Живёт отдельным systemd-таймером
(`wow-showcase-report-sender.timer`), не веб-сервисом.
"""
from __future__ import annotations

import html
import logging
import os
import subprocess
import sys
from pathlib import Path

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

NOTIFY = "/opt/scripts/notify.sh"
BATCH = 20

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("report-sender")


def build_message(row: dict) -> str:
    """Текст уведомления в служебный чат.

    Почты посетителя здесь нет и быть не должно (T-98, решение PO от 07.09):
    чат живёт в Телеграме, то есть за пределами страны, и контакт человека туда
    не уезжает — только пометка, что он оставлен, и номер записи. Адрес читается
    в базе на территории РФ по этому номеру. Цена решения принята сознательно:
    интерфейса к таблице нет, и чтобы ответить, сотрудник лезет в базу.
    """
    lines = ["<b>Обращение с витрины</b>"]
    if row["platform"] and row["username_lower"]:
        url = f"https://fomobase.ru/{row['platform']}/{row['username_lower']}"
        name = html.escape(row["display_name"] or row["username_lower"])
        lines.append(f'Канал: <a href="{html.escape(url)}">{name}</a>')
    else:
        lines.append("Канал: общее обращение по каталогу")
    lines.append(f"Что не так: {html.escape(row['kind'])}")
    lines.append(f"Подробности: {html.escape(row['details'])}")
    if row["email"]:
        lines.append(f"Почта для ответа указана, лежит в базе: запись № {row['id']}")
    return "\n".join(lines)


def purge_expired(cur) -> int:
    """Удалить обращения старше срока хранения. Возвращает число удалённых.

    Срок объявлен в политике приватности (год с даты обращения), и за
    обещанием идёт код: до T-98 механизма удаления не было вовсе, строки лежали
    бессрочно. Опора — created_at: колонки «дата рассмотрения» в таблице нет,
    и заводить её ради формулировки незачем.

    Живёт в этом же скрипте и в этом же таймере: отдельный таймер ради одного
    DELETE в сутки — лишняя деталь, которая однажды окажется отключённой и
    никем не замеченной.
    """
    cur.execute("""
        DELETE FROM public.data_report
        WHERE created_at < now() - INTERVAL '1 year'
    """)
    return cur.rowcount


def main() -> int:
    dsn = os.environ["SHOWCASE_DSN"]
    conn = psycopg2.connect(dsn, cursor_factory=psycopg2.extras.RealDictCursor)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT * FROM public.data_report
                WHERE sent_at IS NULL ORDER BY created_at LIMIT %s
            """, (BATCH,))
            rows = cur.fetchall()

            for row in rows:
                text = build_message(row)
                result = subprocess.run(
                    [NOTIFY, "--tag", "showcase", text],
                    capture_output=True, text=True, timeout=20)
                if result.returncode == 0:
                    cur.execute("UPDATE public.data_report SET sent_at = now() WHERE id = %s",
                               (row["id"],))
                    log.info("отправлено обращение id=%s", row["id"])
                else:
                    attempts = row["send_attempts"] + 1
                    cur.execute("UPDATE public.data_report SET send_attempts = %s WHERE id = %s",
                               (attempts, row["id"]))
                    # Не проглатывать неудачу отправки: правило проекта — потеря
                    # и отказ это warning/error, а не debug.
                    log.error("не удалось отправить обращение id=%s (попытка %s): %s",
                             row["id"], attempts, (result.stderr or "").strip())

            purged = purge_expired(cur)
            if purged:
                log.info("удалено обращений старше года: %s", purged)
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
