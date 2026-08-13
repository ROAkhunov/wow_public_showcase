# Как витрина стоит на проде

Раскатано 13.08 на `wow-dc-prod` (45.91.168.74), домен `fomobase.ru`. Файлы рядом — копии того, что
реально лежит на сервере; правится сначала здесь, потом на сервере, а не наоборот.

## Что где

| Что | Где на сервере |
|---|---|
| Код | `/opt/wow_public_showcase`, ветка `main`, тянется из GitHub |
| Настройки | `/opt/wow_public_showcase/.env`, права `600`, в git не едет |
| Сервис | `wow-showcase.service`, uvicorn на `127.0.0.1:8502`, 2 воркера, `Restart=always` |
| nginx | `/etc/nginx/sites-available/fomobase.ru`, зона кэша в `/etc/nginx/conf.d/fomobase-cache.conf` |
| Кэш | `/var/cache/nginx/fomobase`, до 2 ГБ, страница живёт час |
| Сертификат | `/etc/letsencrypt/live/fomobase.ru`, `fomobase.ru` и `www`, продлевает `certbot.timer` |
| Файлы подтверждения прав | `/var/www/fomobase/` — `yandex_*.html`, `google*.html` |
| Аватарки | отдаются из `/opt/datacollector/data/avatars` как есть, ACL `u:www-data:--x` на `/opt/datacollector` |

## Раскатка новой версии

```bash
ssh wow-prod
cd /opt/wow_public_showcase && git pull --ff-only
systemctl restart wow-showcase && systemctl is-active wow-showcase
curl -s -o /dev/null -w '%{http_code}\n' https://fomobase.ru/
```

Кэш nginx после выкатки держит старые страницы до часа. Сбросить, если правка касается вёрстки:

```bash
rm -rf /var/cache/nginx/fomobase/* && systemctl reload nginx
```

## Две вещи, которые легко сломать

**Индексация закрыта гейтом.** `SHOWCASE_NOINDEX=1` в `.env` — единственный переключатель, снятие
только после встречи с Максимом и его подтверждения. В конфиге nginx его нет и быть не должно.

**Витрина стоит первой по алфавиту в `sites-enabled`,** то есть без явного `default_server` она
собрала бы на себя весь трафик с чужим или пустым `Host`. Поэтому в конфиге живёт отдельный блок
`listen 80 default_server` с `return 444`. Внутренняя витрина на 8501 (`list.wowblogger.com`) при
этом не затронута: у неё свой блок по имени.

## Файл подтверждения прав против catch-all

В приложении есть маршрут `/{platform}`, который отвечает на любой односегментный адрес. Файл
`/yandex_*.html` он перехватил бы страницей 404, поэтому в nginx стоит regexp-локация до `location /`
— она выигрывает у префиксной по правилам nginx. Проверено 13.08: файл на диске отдаётся, чужое имя
того же вида даёт 404 от приложения.
