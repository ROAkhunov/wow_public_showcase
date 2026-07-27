// Прототип публичной витрины. Данные — реальный срез с прода (25 каналов), только чтение.
const PF = {tg:'TG', vk:'VK', max:'MX', ok:'OK', yt:'YT', zen:'Z', ig:'IG', tt:'TT'};
const PF_NAME = {tg:'Telegram', vk:'ВКонтакте', max:'MAX', ok:'Одноклассники', yt:'YouTube',
                 zen:'Дзен', ig:'Instagram', tt:'TikTok'};

const num = n => (n == null ? '—' : String(Math.round(n)).replace(/\B(?=(\d{3})+(?!\d))/g, ' '));
const pct = n => (n == null ? '—' : n.toFixed(1).replace('.', ',') + '%');
const cats = c => (c || []).filter(x => x && x !== 'undefined');

function coverageRatio(c) {
  if (!c.views_avg || !c.subscribers) return null;
  return c.views_avg / c.subscribers * 100;
}
function adShare(c) {
  if (!c.posts_90d) return null;
  return (c.ads_90d || 0) / c.posts_90d * 100;
}
function dateRu(s) {
  if (!s) return '—';
  const d = new Date(s);
  return d.toLocaleDateString('ru-RU', {day: '2-digit', month: 'short', year: 'numeric'});
}
function daysAgo(s) {
  if (!s) return null;
  return Math.floor((Date.now() - new Date(s)) / 864e5);
}
function avatar(c, cls) {
  const letter = (c.display_name || c.username || '?').trim()[0].toUpperCase();
  if (c.avatar_url && c.avatar_url.startsWith('http')) {
    return `<img class="ava ${cls||''}" src="${c.avatar_url}" alt="" loading="lazy"
      onerror="this.outerHTML='<div class=\\'ava-ph ${cls||''}\\'>${letter}</div>'">`;
  }
  return `<div class="ava-ph ${cls||''}">${letter}</div>`;
}
const esc = s => (s || '').replace(/[<>&]/g, m => ({'<':'&lt;','>':'&gt;','&':'&amp;'}[m]));
const clip = (s, n) => { s = (s || '').replace(/\s+/g, ' ').trim(); return s.length > n ? s.slice(0, n) + '…' : s; };

// Потеря охвата на рекламном посте относительно обычного
function adReachDrop(c) {
  if (!c.views_organic || !c.views_ad) return null;
  return (c.views_ad - c.views_organic) / c.views_organic * 100;
}
// Прирост подписчиков за период истории
function growth(c) {
  const h = (c.history || []).filter(x => x[1]);
  if (h.length < 2 || !h[0][1]) return null;
  return (h[h.length - 1][1] - h[0][1]) / h[0][1] * 100;
}
// Доля рекламодателей, разместившихся повторно
function repeatRate(c) {
  if (!c.adv_total) return null;
  return (c.adv_repeat || 0) / c.adv_total * 100;
}
const signed = n => (n == null ? '—' : (n > 0 ? '+' : '') + n.toFixed(1).replace('.', ',') + '%');

// Название рекламодателя. Решение PO 27.07: ИП показываем наравне с юрлицами —
// публикуем то, что и так публично (наименование, ОГРН, ИНН), обезличивание снято.
function advLabel(a) {
  return a.name_short || a.name_full || '—';
}
