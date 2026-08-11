# Дизайн-система публичной витрины WOW

**Импортируемых компонентов тут нет.** Это HTML и CSS: страницу собирают разметкой
с классами из `_ds_bundle.css`, а не импортом из `window.WOWShowcase` — пространство
имён пустое намеренно. Всё оформление приходит из одного файла.

## Подключение

```html
<link rel="stylesheet" href="styles.css">
```

`styles.css` тянет за собой шрифт (Onest, лежит локально), токены и классы
компонентов — больше ничего подключать не нужно. Никаких обёрток и провайдеров:
`body` получает фон, цвет и шрифт из базовых правил токенов. Содержимое страницы
центрируем в `.ds-wrap` (максимум `--wrap` = 1240px, боковые отступы внутри).

Внешних `@import` в дизайн-системе нет намеренно — ни Google Fonts, ни другого
чужого хоста. Не добавлять: превью их не пускают, а на релизе чужой хост
в критическом пути отрисовки не нужен.

## Идиома: классы для структуры, `var(--*)` для всего остального

Цвет, размер, отступ и скругление берутся токеном, а не числом. В релизе
шаблонных страниц сотни тысяч — вид меняется в одном файле, а не в разметке.

```css
color: var(--dim);  font-size: var(--fs-meta);  gap: var(--sp-3);
```

| Семейство | Токены |
|---|---|
| поверхности | `--bg` `--surface` `--surface-sunk` |
| границы | `--line` `--line-soft` `--line-strong` |
| текст | `--text` `--dim` `--muted` |
| акцент | `--accent` `--accent-dark` `--accent-soft` `--accent-line` |
| реклама | `--ad` `--ad-soft` `--ad-line` |
| скоринг | `--score-good-bg/-fg` `--score-mid-bg/-fg` `--score-low-bg/-fg` |
| статусы | `--ok` `--warn` |
| размеры | `--fs-label` `--fs-meta` `--fs-body` `--fs-lead` `--fs-h3` `--fs-h2` `--fs-h1` |
| плотность | `--sp-1` … `--sp-6`, `--row-h` `--control-h` `--avatar` `--wrap` |
| форма | `--r-sm` `--r-md` `--r-lg` `--r-pill` |
| прочее | `--font` `--lh-tight` `--lh-body` `--tracking-head` `--tracking-label` `--shadow-pop` |

Готовые классы-словарь (полностью — в `_ds_bundle.css`, по компонентам —
в `components/*/*/*.prompt.md`):

| Семейство | Классы |
|---|---|
| выдача | `.list` `.row` `.ava` `.name` `.sub` `.plat` `.ver` |
| метрика | `.m` `.m-cols` `.m-tiles` `.ds-label` `.ds-value` |
| скоринг | `.score` + `--good` `--mid` `--low` `--none` `--lg` |
| реклама | `.flag` `.flag--solid` `.feed` `.post` `.post--ad` `.adv-line` |
| фильтры | `.layout` `.side` `.group` `.field` `.pair` `.check` `.fbtn` `.tag` |
| навигация | `.bar` `.sort` `.sbtn` `.pg` `.hdr` `.nav` `.sections` `.sec` `.hero` |
| канал | `.head` `.title` `.breadcrumbs` `.desc` `.actions` `.btn` `.chip` `.sites` |
| значения | `.adv` `.up` `.down` `.none` |
| каркас | `.ds-wrap` `.ds-panel` |

Крупные варианты для страницы канала — модификатором: `.ava--lg` `.plat--lg`
`.ver--lg` `.score--lg`. Площадки — цветом: `.plat--tg` `--vk` `--yt` `--dz`.

Своих классов лучше не заводить. Если нужного нет — сначала посмотреть, не
собирается ли это из имеющихся; новая сущность в вёрстке страницы означает, что
следующая страница оформит её иначе.

## Что нельзя

- **Теней в потоке страницы нет.** Мы на границах: `border: 1px solid var(--line)`.
  Единственная тень — `--shadow-pop`, и только для всплывающего поверх контента.
- **Синего нет.** Ни в ссылках, ни в кнопках, ни в состояниях: у конкурента
  акцент `#2f6fed`, выглядеть его клоном витрине незачем. Акцент — тил `--accent`.
- **Насыщенный цвет — ровно два места:** плашка `.flag` и бейдж `.score`.
- **Денег нет.** Ни цен, ни CPM, ни CPV, ни себестоимости — нигде.
- **Табов нет нигде.** Ни по площадкам автора, ни по постам: у каждого канала
  свой URL, переходы — ссылками.
- **Демографии аудитории нет.**
- Пагинация — обычные `<a href>`, а не подгрузка по скроллу: краулер должен
  дойти до последней страницы.
- **WOW пишется капсом** во всех пользовательских надписях. URL и технические
  строки не трогаем.

## Пример страницы

```html
<link rel="stylesheet" href="styles.css">

<header class="hdr">
  <div class="inner">
    <a class="logo" href="/"><span class="logo-mark">Б</span> Блогеры России</a>
    <nav class="nav"><a class="on" href="/">Каталог</a><a href="/topics">Тематики</a></nav>
  </div>
</header>

<div class="hero">
  <h1>Телеграм-каналы про технологии</h1>
  <p>1 284 канала: подписчики, охваты, вовлечённость и доля рекламы в ленте.</p>
</div>

<div class="ds-wrap">
  <div class="bar">
    <div class="sort">
      <span class="ds-label">Сортировка</span>
      <button class="sbtn on">По подписчикам</button>
      <button class="sbtn">По охвату</button>
    </div>
    <span class="count">Найдено <b>1 284</b> канала</span>
  </div>

  <div class="list">
    <div class="row">
      <div class="ava">МТ</div>
      <div>
        <div class="name">
          <span class="plat plat--tg">TG</span>
          <a href="/tg/mirtrendov"><b>Мир трендов</b></a>
          <span class="ver">✓</span>
        </div>
        <div class="sub">Технологии · 218 постов за месяц</div>
      </div>
      <span class="score score--good">3,6</span>
      <div class="m"><span class="ds-label">Подписчиков</span><span class="ds-value">3 087 084</span></div>
      <div class="m"><span class="ds-label">Средний охват</span><span class="ds-value">57 146</span></div>
      <div class="m"><span class="ds-label">ER</span><span class="ds-value">1,84%</span></div>
      <div class="m"><span class="ds-label">Доля рекламы</span><span class="ds-value adv">7,4%</span></div>
    </div>
  </div>
</div>
```

Если чего-то не хватает — читать сами файлы: `tokens/tokens.css` (что вообще
есть) и `_ds_bundle.css` (как устроен каждый класс). Это точнее любого пересказа.
