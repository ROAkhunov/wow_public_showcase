"""T-98: политика перестала расходиться с фактом — проверяется то, что в коде.

Три вещи, каждая закрывает конкретную находку аудита 07.09:
почта посетителя не уезжает в Телеграм, обращения не лежат в базе бессрочно,
и про согласие сказано там, где его дают, — рядом с кнопкой.

`report_sender` живёт в `deploy/` пакетом не оформленным (его запускает systemd
по пути, а не импортом), отсюда загрузка по файлу.
"""
import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path

import psycopg2
import psycopg2.extras
import pytest

_SENDER = Path(__file__).resolve().parent.parent / "deploy" / "report_sender.py"
_spec = importlib.util.spec_from_file_location("report_sender", _SENDER)
report_sender = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(report_sender)


# ── почта не уезжает за границу ──────────────────────────────────────────────

def test_visitor_email_is_not_in_the_telegram_message():
    """Чат живёт в Телеграме, то есть за пределами страны. Контакт человека
    остаётся в базе на территории РФ, в сообщение идёт только номер записи."""
    text = report_sender.build_message({
        "id": 42, "platform": "tg", "username_lower": "example_channel",
        "display_name": "Пример канала", "kind": "Неверное число подписчиков",
        "details": "Подписчиков на самом деле 50 000", "email": "po@example.com",
    })

    assert "po@example.com" not in text
    assert "example.com" not in text
    assert "42" in text
    assert "Подписчиков на самом деле 50 000" in text


def test_message_without_email_says_nothing_about_it():
    text = report_sender.build_message({
        "id": 43, "platform": None, "username_lower": None, "display_name": None,
        "kind": "Другое", "details": "Общее замечание", "email": None,
    })

    assert "Почта" not in text
    assert "Общее замечание" in text


# ── обращения не лежат бессрочно ─────────────────────────────────────────────

def _report(cur, *, days_ago: int, details: str) -> int:
    created = datetime.now(timezone.utc) - timedelta(days=days_ago)
    cur.execute("""
        INSERT INTO public.data_report (created_at, kind, details)
        VALUES (%s, 'Другое', %s) RETURNING id
    """, (created, details))
    return cur.fetchone()["id"]


@pytest.mark.integration
def test_reports_older_than_a_year_are_deleted(dsn):
    """Политика обещает срок хранения — год. До T-98 механизма удаления не было
    вовсе, и «год» был бы третьим неверным утверждением на той же странице."""
    conn = psycopg2.connect(dsn, cursor_factory=psycopg2.extras.RealDictCursor)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            old = _report(cur, days_ago=400, details="старое обращение")
            fresh = _report(cur, days_ago=10, details="свежее обращение")
            edge = _report(cur, days_ago=360, details="ещё не год")

            purged = report_sender.purge_expired(cur)

            cur.execute("SELECT id FROM public.data_report ORDER BY id")
            left = [r["id"] for r in cur.fetchall()]
    finally:
        conn.close()

    assert purged == 1
    assert old not in left
    assert fresh in left
    assert edge in left


# ── о согласии сказано там, где его дают ─────────────────────────────────────

@pytest.mark.integration
def test_report_form_says_what_sending_it_means(client):
    """На факт ссылки на /privacy тест не вешаем: она стоит в подвале каждой
    страницы и был бы зелёным до правки. Проверяется сам текст согласия."""
    body = client.get("/report").text

    assert "соглашаетесь с обработкой указанных данных" in body
