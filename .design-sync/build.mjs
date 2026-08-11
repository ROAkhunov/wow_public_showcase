#!/usr/bin/env node
// Сборка выгрузки для claude.ai/design из design-system/.
//
// Штатный конвертер скилла /design-sync (package-build.mjs) собирает бандл из
// dist/ npm-пакета с React-компонентами. У витрины ни пакета, ни React нет:
// дизайн-система — это токены, общий CSS и самодостаточные HTML-превью.
// Поэтому раскладку собираем здесь, но по тому же контракту, который проверяет
// package-validate.mjs и читает self-check приложения:
//
//   _ds_bundle.js   первой строкой /* @ds-bundle: {…} */, пустое пространство
//                   имён: импортируемых компонентов у статики нет
//   _ds_bundle.css  общий CSS компонентов (design-system/components.css)
//   styles.css      точка входа: @import шрифта, токенов и _ds_bundle.css.
//                   Дизайн, который собирает агент, получает ТОЛЬКО замыкание
//                   этих @import — всё, что должно на него влиять, идёт сюда
//   components/<группа>/<Имя>/<Имя>.html   карточка превью, первой строкой @dsCard
//   components/<группа>/<Имя>/<Имя>.prompt.md   как этим пользоваться
//   _ds_sync.json   якорь для следующей синхронизации
//
// Запуск: node .design-sync/build.mjs [--out ./ds-bundle]

import { createHash } from 'node:crypto';
import { cpSync, existsSync, mkdirSync, readFileSync, readdirSync, rmSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const REPO = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const DS = join(REPO, 'design-system');
const outFlag = process.argv.indexOf('--out');
const OUT = resolve(REPO, outFlag > 0 ? process.argv[outFlag + 1] : './ds-bundle');

const NAMESPACE = 'WOWShowcase';
const sha = (s) => createHash('sha256').update(s).digest('hex');
const sha12 = (s) => sha(s).slice(0, 12);
const read = (p) => readFileSync(p, 'utf8');

// Состав выгрузки. Имя каталога компонента — латиницей: оно попадает в URL,
// по которому карточку открывает и рендер-проверка, и приложение. Человеческое
// имя группы живёт в маркере @dsCard, его и показывает панель.
const COMPONENTS = [
  { src: 'colors.html',         name: 'Colors',        dir: 'foundation', group: 'Основа' },
  { src: 'type.html',           name: 'Typography',    dir: 'foundation', group: 'Основа' },
  { src: 'site-header.html',    name: 'SiteHeader',    dir: 'ui',         group: 'Компоненты' },
  { src: 'channel-header.html', name: 'ChannelHeader', dir: 'ui',         group: 'Компоненты' },
  { src: 'row.html',            name: 'Row',           dir: 'ui',         group: 'Компоненты' },
  { src: 'metric.html',         name: 'Metric',        dir: 'ui',         group: 'Компоненты' },
  { src: 'score-badge.html',    name: 'ScoreBadge',    dir: 'ui',         group: 'Компоненты' },
  { src: 'ad-flag.html',        name: 'AdFlag',        dir: 'ui',         group: 'Компоненты' },
  { src: 'filters.html',        name: 'Filters',       dir: 'ui',         group: 'Компоненты' },
  { src: 'pagination.html',     name: 'Pagination',    dir: 'ui',         group: 'Компоненты' },
];

// --- чистый выходной каталог ------------------------------------------------
if (existsSync(OUT)) {
  const stray = readdirSync(OUT).filter((f) => !/^(_|components$|tokens$|fonts$|styles\.css$|README\.md$|\.)/.test(f));
  if (stray.length) {
    console.error(`✗ ${OUT} — не похож на прошлую сборку (лишнее: ${stray.join(', ')}). Укажи пустой каталог.`);
    process.exit(1);
  }
  rmSync(OUT, { recursive: true, force: true });
}
mkdirSync(OUT, { recursive: true });

// --- стили ------------------------------------------------------------------
const tokensCss = read(join(DS, 'tokens.css'));
const componentsCss = read(join(DS, 'components.css'));
const fontsCss = read(join(DS, 'fonts', 'fonts.css'));
const previewCss = read(join(DS, 'preview.css'));

mkdirSync(join(OUT, 'tokens'), { recursive: true });
mkdirSync(join(OUT, 'fonts'), { recursive: true });
mkdirSync(join(OUT, '_preview'), { recursive: true });

writeFileSync(join(OUT, 'tokens', 'tokens.css'), tokensCss);
writeFileSync(join(OUT, '_ds_bundle.css'), componentsCss);
writeFileSync(join(OUT, '_preview', 'preview.css'), previewCss);
// Имя fonts/fonts.css не случайное: под ним файл ищет проверка шрифтов
// в package-validate.mjs.
writeFileSync(join(OUT, 'fonts', 'fonts.css'), fontsCss);
for (const f of readdirSync(join(DS, 'fonts')).filter((f) => f.endsWith('.woff2'))) {
  cpSync(join(DS, 'fonts', f), join(OUT, 'fonts', f));
}

// Порядок тот же, что в design-system/index.css: шрифт, токены, компоненты.
const stylesCss = `/* Точка входа дизайн-системы публичной витрины WOW.
   Дизайн, собранный агентом, получает только замыкание этих @import. */

@import "./fonts/fonts.css";
@import "./tokens/tokens.css";
@import "./_ds_bundle.css";
`;
writeFileSync(join(OUT, 'styles.css'), stylesCss);

// --- бандл ------------------------------------------------------------------
// Импортируемых компонентов нет: витрина — статика, отдавать в window нечего.
// Пространство имён создаём пустым, чтобы обращение к нему не падало.
const sourceHashes = {
  'tokens.css': sha12(tokensCss),
  'components.css': sha12(componentsCss),
  'fonts.css': sha12(fontsCss),
};
const header = JSON.stringify({
  namespace: NAMESPACE,
  components: [],
  sourceHashes,
  inlinedExternals: [],
  note: 'HTML/CSS design system — no importable React components; build with styles.css and the class vocabulary in README.md',
});
const bundleJs = `/* @ds-bundle: ${header} */
(function () {
  // Дизайн-система витрины — HTML и CSS. Собирать интерфейс из неё нужно
  // разметкой с классами из _ds_bundle.css, а не импортом компонентов.
  window.${NAMESPACE} = window.${NAMESPACE} || {};
})();
`;
writeFileSync(join(OUT, '_ds_bundle.js'), bundleJs);

// --- карточки компонентов ---------------------------------------------------
// Превью в репозитории ссылаются на ../index.css и ../preview.css. В выгрузке
// раскладка другая (components/<группа>/<Имя>/), поэтому переписываем пути:
// стиль продукта — на styles.css, каркас карточки — на _preview/preview.css.
const promptsDir = join(REPO, '.design-sync', 'prompts');
const renderHashes = {};
let previews = 0;

for (const c of COMPONENTS) {
  const srcPath = join(DS, 'components', c.src);
  let html = read(srcPath)
    .replace('<link rel="stylesheet" href="../index.css">', '<link rel="stylesheet" href="../../../styles.css">')
    .replace('<link rel="stylesheet" href="../preview.css">', '<link rel="stylesheet" href="../../../_preview/preview.css">');

  if (html.includes('../index.css') || html.includes('../preview.css')) {
    console.error(`✗ ${c.src}: не удалось переписать <link> — превью должно ссылаться на ../index.css и ../preview.css`);
    process.exit(1);
  }
  if (!/^<!--\s*@dsCard\s+group="/.test(html)) {
    console.error(`✗ ${c.src}: первой строкой должен идти маркер <!-- @dsCard group="…" -->`);
    process.exit(1);
  }

  const promptPath = join(promptsDir, `${c.name}.prompt.md`);
  if (!existsSync(promptPath)) {
    console.error(`✗ нет .design-sync/prompts/${c.name}.prompt.md`);
    process.exit(1);
  }
  const prompt = read(promptPath);

  const dir = join(OUT, 'components', c.dir, c.name);
  mkdirSync(dir, { recursive: true });
  writeFileSync(join(dir, `${c.name}.html`), html);
  writeFileSync(join(dir, `${c.name}.prompt.md`), prompt);
  renderHashes[c.name] = sha12(html + prompt);
  previews++;
}

// --- README -----------------------------------------------------------------
// Шапку с конвенциями пишет человек и она лежит в репозитории; тело —
// оглавление, которое собирается отсюда.
const headerPath = join(REPO, '.design-sync', 'conventions.md');
const conventions = existsSync(headerPath) ? read(headerPath).trimEnd() + '\n\n' : '';
const index = ['## Что где в этой выгрузке', '',
  '- `styles.css` — единственная точка входа. Шрифт, токены, классы компонентов.',
  '- `tokens/tokens.css` — палитра, шкала размеров, плотность, скругления.',
  '- `_ds_bundle.css` — классы компонентов.',
  '- `fonts/` — Onest, вариативный, лежит локально.',
  '- `components/<группа>/<Имя>/` — карточка превью и `<Имя>.prompt.md` с тем,',
  '  из чего компонент собирается.', '',
  '## Компоненты', ''];
for (const g of ['Основа', 'Компоненты']) {
  index.push(`**${g}**`, '');
  for (const c of COMPONENTS.filter((c) => c.group === g)) {
    const title = read(join(DS, 'components', c.src)).match(/<title>([^<]*)<\/title>/)?.[1] ?? c.name;
    index.push(`- \`${c.name}\` — ${title}`);
  }
  index.push('');
}
const readme = `${conventions}${index.join('\n')}`;
writeFileSync(join(OUT, 'README.md'), readme);

// --- служебное --------------------------------------------------------------
writeFileSync(join(OUT, '_ds_needs_recompile'), JSON.stringify({ by: 'design-sync-cli' }));
writeFileSync(join(OUT, '.ds-build-meta.json'), JSON.stringify({
  componentCount: previews,
  shape: 'static-html (off-script)',
  namespace: NAMESPACE,
  builtBy: '.design-sync/build.mjs',
}, null, 2));

// Якорь. Хеши считаем по содержимому карточек: штатный renderHashFor завязан на
// манифест историй, которого у статики нет. Пересчёт в package-validate.mjs
// пропускается, потому что .stories-map.json мы не пишем.
writeFileSync(join(OUT, '_ds_sync.json'), JSON.stringify({
  shape: 'static-html',
  keyRecipe: 'sha256(<Name>.html + <Name>.prompt.md).slice(0,12) — считает .design-sync/build.mjs',
  styleSha: sha12(stylesCss + tokensCss + componentsCss + fontsCss),
  bundleSha12: sha12(bundleJs),
  sourceHashes,
  renderHashes,
}, null, 2));

console.error(`✓ ${OUT}: ${previews} карточек, ${(Buffer.byteLength(componentsCss) / 1024).toFixed(1)} КБ CSS компонентов`);
