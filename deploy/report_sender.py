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
        lines.append(f"Email: {html.escape(row['email'])}")
    return "\n".join(lines)


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
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
