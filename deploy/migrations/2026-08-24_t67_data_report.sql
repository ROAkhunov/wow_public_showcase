-- T-67. Таблица обращений «Сообщить о неточности».
--
-- Живёт в public базы showcase, а не в схеме дампа (dump_* дропается каждую
-- ночь при ротации, public.build_meta её переживает). Единственная запись
-- сервиса витрины в базу, всё остальное остаётся чтением.
--
-- Применять на проде вручную до раскатки кода:
--   psql "$SHOWCASE_DSN" -f deploy/migrations/2026-08-24_t67_data_report.sql

CREATE TABLE IF NOT EXISTS public.data_report (
    id             BIGSERIAL PRIMARY KEY,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    platform       TEXT,
    username_lower TEXT,
    display_name   TEXT,
    kind           TEXT NOT NULL,
    details        TEXT NOT NULL,
    email          TEXT,
    referrer       TEXT,
    sent_at        TIMESTAMPTZ,
    send_attempts  INTEGER NOT NULL DEFAULT 0
);

-- Отправитель раз в 5 минут выбирает необработанные обращения этим индексом.
CREATE INDEX IF NOT EXISTS data_report_unsent_idx
    ON public.data_report (created_at)
    WHERE sent_at IS NULL;
