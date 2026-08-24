#!/bin/bash
# T-67: отдельный дамп `public` базы showcase (обращения "Сообщить о неточности").
#
# Не встроено в /opt/scripts/pg_backup.sh (репозиторий датаколлектора): тот
# скрипт весь про ротацию и disk-floor базы datacollector, посчитанные под её
# объёмы, и лишний pg_dump другой базы задел бы эти расчёты, ничего в них не
# выиграв — здесь единицы мегабайт. Отдельный маленький скрипт, отдельная
# строка в cron, схема дампа (`dump_*`) в бэкап не идёт — она пересобирается
# каждую ночь заново, нужен только `public`.
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/opt/backups}"
DATE=$(date +%Y%m%d_%H%M)
OUT="$BACKUP_DIR/showcase_public_${DATE}.dump"
PART="${OUT}.part"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"; }

if ! sudo -u postgres pg_dump -Fc -n public -d showcase > "$PART"; then
    rm -f "$PART"
    log "ERROR: pg_dump showcase(public) failed"
    /opt/scripts/notify.sh --tag backups "<b>Бэкап public.showcase не удался — pg_dump упал</b>" >/dev/null 2>&1 || true
    exit 1
fi

if ! sudo -u postgres pg_restore -f /dev/null "$PART" >/dev/null 2>&1; then
    rm -f "$PART"
    log "ERROR: dump failed verification"
    /opt/scripts/notify.sh --tag backups "<b>Бэкап public.showcase битый — не прошёл проверку, файл удалён</b>" >/dev/null 2>&1 || true
    exit 1
fi

mv "$PART" "$OUT"
log "$(basename "$OUT"): $(du -h "$OUT" | cut -f1) (verified)"

# Единицы мегабайт, диск ими не критичен — но копиться бесконечно тоже незачем.
find "$BACKUP_DIR" -maxdepth 1 -name 'showcase_public_*.dump' -mtime +7 -delete
