# WOW Public Showcase

Публичная витрина WOW Blogger List: вёрстка публичного каталога блогеров.

Репозиторий заведён 2026-07-23, чтобы прототип перестал жить только на проде вне git. До этого
он лежал в `/var/www/t7-preview/` на сервере, без истории и без чейнджлога.

## Что здесь есть, а чего нет

**Есть:** вёрстка публичного каталога — выдача, карточка канала, стили, клиентская логика.

**Нет:** бэкенда, запросов к базе, расчёта метрик. Данные прототипа лежат статикой в
`prototype/data.js` — срез с прода, только чтение, никакого подключения к БД.

Смежные репозитории:
- `WOW_claude_datacollector` — сбор данных, пайплайн, БД;
- `wow_blogger_list` — внутренняя витрина (FastAPI, порт 8501), боевой каталог;
- `WOWlist_manage` — PM-репозиторий: задачи, отчёты, решения. Задачи по этой вёрстке — T-7
  (зонтичная), **T-41** (правки прототипа по созвону 22.07), T-21 (SEO и релиз).

## Структура

```
prototype/
  index.html        выдача каталога: фильтры, сортировки, карточки
  channel.html      страница канала: метрики, график, посты, площадки автора
  style.css         стили
  app.js            клиентская логика (фильтры, сортировка, рендер)
  data.js           срез данных с прода — вне git, см. ниже
  data.example.js   синтетический пример той же структуры, чтобы прототип открылся из клона
```

## Данные

`prototype/data.js` **в git не хранится**. Причина: в срезе есть наименования
рекламодателей-физлиц (ФИО), а решение по перс. данным ещё не принято — вопрос висит за Максимом
(см. T-7 в `WOWlist_manage/pm/backlog/tasks.md`). Репозиторий публичный, класть туда ФИО нельзя.

Чтобы открыть прототип после свежего клона:

```bash
cp prototype/data.example.js prototype/data.js
```

Актуальный срез забирается с прода:

```bash
scp wow-prod:/var/www/t7-preview/data.js prototype/data.js
```

Структура одной записи (25 каналов в срезе, 8 платформ):
`id, platform, username, display_name, description, url, avatar_url, blogger_id, blogger_name,
subscribers, views_avg, er_percent, scraped_at, categories[], posts_30d, ads_90d, posts_90d,
last_post_at, views_organic, views_ad, views_spread, posts[], advertisers[], adv_total,
adv_repeat, history[[дата, подписчики]], siblings[]`.

## Локальный запуск

Статика без сборки, нужен только http-сервер (из `file://` браузер не отдаст `data.js`):

```bash
cd prototype && python -m http.server 8080
# http://localhost:8080/index.html
```

## Деплой

Прототип раздаётся nginx с прода как статика:

- путь на сервере — `/var/www/t7-preview/`, адрес `https://list.wowblogger.com/t7-preview/`;
- отдаётся с `X-Robots-Tag: noindex` — прототип в индекс не пускаем;
- боевая витрина (`location /` → порт 8501) не затронута, бэкап конфига —
  `/root/nginx-list-backup-2026-07-22.conf`.

Выкладка: `scp prototype/*.{html,css,js} wow-prod:/var/www/t7-preview/`. `data.js` на сервере
живёт своей жизнью, при выкладке его не перезатирать без необходимости.
