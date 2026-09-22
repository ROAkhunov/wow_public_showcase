"""Как цифра выглядит на экране. Считать здесь нечего — только форматирование.

Граница простая: если функция делит, сравнивает даты или сводит несколько
колонок в одну, ей место в сборщике дампа (T-60), а не тут.
"""
from __future__ import annotations

import re
from datetime import date, datetime

NBSP = " "

MONTHS = ("января", "февраля", "марта", "апреля", "мая", "июня",
          "июля", "августа", "сентября", "октября", "ноября", "декабря")


def num(value) -> str:
    """12345 → «12 345». Пусто → прочерк, а не ноль: это разные вещи."""
    if value is None:
        return "—"
    return f"{int(value):,}".replace(",", NBSP)


def pct(value, digits: int = 1) -> str:
    if value is None:
        return "—"
    return f"{value:.{digits}f}".replace(".", ",") + "%"


def signed(value, digits: int = 1) -> str:
    if value is None:
        return "—"
    sign = "+" if value >= 0 else "−"
    return sign + f"{abs(value):.{digits}f}".replace(".", ",") + "%"


def date_ru(value) -> str:
    if isinstance(value, datetime):
        value = value.date()
    if not isinstance(value, date):
        return "—"
    return f"{value.day} {MONTHS[value.month - 1]} {value.year}"


def clip(text: str | None, limit: int = 420) -> str:
    if not text:
        return ""
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0] + "…"


#: ниже этой цифры обещание не показывается вовсе (T-97). «До 40 человек» не
#: приглашение, а повод закрыть вкладку; таких строк с кнопкой 3 110 из 36 571.
REACH_MIN = 100


def reach(value) -> str:
    """Охват в обещании «увидит до N человек». Пусто — если обещать нечего.

    Округление всегда вниз: «до N» не должно обещать больше, чем есть. Пустая
    строка вместо прочерка не случайна — по ней шаблон снимает весь блок, а не
    рисует прочерк внутри фразы.
    """
    if value is None:
        return ""
    n = int(value)
    if n < REACH_MIN:
        return ""
    if n < 1_000:
        return str(n // 10 * 10)
    if n < 1_000_000:
        if n < 10_000:
            whole, tenth = divmod(n // 100, 10)
            return f"{whole},{tenth} тыс." if tenth else f"{whole} тыс."
        return f"{n // 1000:,}".replace(",", NBSP) + " тыс."
    whole, tenth = divmod(n // 100_000, 10)
    return f"{whole},{tenth} млн" if tenth else f"{whole} млн"


def plural(n: int, one: str, few: str, many: str) -> str:
    n = abs(int(n or 0))
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


def reach_promise(row) -> dict | None:
    """Крючок у кнопки «Заказать рекламу»: готовые куски фразы или `None`.

    Выбор живёт здесь, а не в шаблонах: мест показа пять (всплывашка и
    подстрочник в каталоге, подстрочник в шапке, панель и её мобильная копия
    на карточке), и решать по-своему каждое из них не должно. Они кладут вокруг
    цифры свою разметку, но слов не сочиняют: фраза целиком собирается как
    `lead verb num tail`, подстрочник кнопки печатает `sub`.

    Цепочка (T-119): рекламный охват, иначе обычный, иначе число рекламных
    постов за месяц, иначе крючка нет. Рекламный охват побеждает всегда, даже
    когда он мал: ноль и сорок — это заполненные значения, у такого канала
    рекламный пост столько и собирает. Подменить его обычным охватом значило бы
    пообещать за рекламный пост то, чего рекламный пост не даёт. Порог
    применяется после выбора и подмены не делает. А вот к рекламе такой канал
    пускается: «12 рекламных постов» охвата не обещает. Без этого MAX, у
    которого просмотров нет вовсе (T-48), остался бы без крючка целиком.
    """
    value = row["views_ad"] if row.get("views_ad") is not None else row.get("views_organic")
    number = reach(value)
    if number:
        return dict(kind="reach", lead="Вашу рекламу в этом канале", verb="увидит",
                    num=f"до {number}", tail="человек", sub=f"увидят до {number}")
    ads = int(row.get("ads_30d") or 0)
    if ads < 1:
        return None
    one = plural(ads, "рекламный", "рекламных", "рекламных")
    return dict(kind="ads", lead="За месяц в канале",
                verb=plural(ads, "вышел", "вышло", "вышло"), num=str(ads),
                tail=f"{one} {plural(ads, 'пост', 'поста', 'постов')}",
                sub=f"{ads} {one} за месяц")


#: имя сайта в заголовке страницы. В каталоге бренд стоял с самого начала, на
#: карточке появился с T-83.
BRAND = "Fomobase"

#: потолок длины заголовка страницы. Дальше поисковик обрезает его сам, и
#: обрезает не там, где нам нужно.
TITLE_LIMIT = 70


def channel_title(name: str, username: str, platform: str, limit: int = TITLE_LIMIT) -> str:
    """Заголовок страницы канала: имя, площадка, @имя_на_площадке и бренд.

    Запрос человек набирает как «durov телеграм статистика», а в заголовке до
    T-83 не было ни площадки, ни `@username`, ни бренда. Всё вместе в 70
    символов помещается не всегда, поэтому лишнее отваливается по порядку: сначала
    бренд, потом `@имя`, и только потом подрезается имя канала — оно и есть то,
    что человек ищет глазами в выдаче.
    """
    name = " ".join((name or username or "").split())
    for tail in (f"@{username} — статистика канала в {platform} · {BRAND}",
                 f"@{username} — статистика канала в {platform}",
                 f"— статистика канала в {platform} · {BRAND}",
                 f"— статистика канала в {platform}"):
        room = limit - len(tail) - 1
        if room >= 12:
            break
    return f"{clip(name, room - 1) if len(name) > room else name} {tail}"


def section_note(row) -> str | None:
    """Абзац с цифрами под заголовком раздела.

    Разделы были заголовком, строкой подзаголовка и таблицей — под запросы это
    тонко. Цифры приезжают колонками из дампа: сервис их не считает, а
    печатает.
    """
    if not row or not row.get("channels"):
        return None
    count = row["channels"]
    parts = [f"В подборке {num(count)} {plural(count, 'канал', 'канала', 'каналов')}"]
    if row.get("views_median"):
        parts.append(f"медианный охват поста {num(row['views_median'])}")
    if row.get("ads_share") is not None:
        parts.append(f"рекламная история есть у {pct(row['ads_share'], 0)} каналов")
    return ", ".join(parts) + "."


# ── T-120: описание канала не продаёт рекламу мимо нас ──────────────────────
#
# Описание стоит на карточке рядом с нашей кнопкой, и у 54% телеграм-каналов с
# кнопкой в нём лежит контакт «по рекламе @…», у 39% адрес биржи-конкурента.
# Слой переносит описание как есть (спека), вырезка живёт здесь, на показе.
#
# Правило «маркер + токен контакта» (прототип C, замер 22.09, остаток 1,1%):
# вырезается ровно подпись («Реклама:», «По вопросам рекламы 👉») и стоящие за
# ней контакты, а не «до конца фразы» — тот вариант проглатывал соседние
# пункты и 3 047 раз ссылку на реестр РКН.

_EMOJI = (
    "\U0001F000-\U0001FAFF"  # пиктограммы, эмоции, транспорт, флаги
    "☀-➿"          # misc symbols + dingbats (☎ ✅ ✔ ❗ ❌ ✨)
    "⬀-⯿"          # стрелки и геометрия (⭐ ⬇)
    "⌀-⏿"          # технические (⏰ ⌚)
    "←-⇿"          # стрелки (→ ↓)
    "■-◿"          # геометрия (■ ▪ ▶)
    "⤀-⥿"          # стрелки дополнительные
    "〰〽㊗㊙"
)

#: токен контакта; порядок важен: почта раньше @ника, ссылка раньше голого домена
CONTACT_RE = re.compile(
    r"[\w.+-]+@[\w-]+\.[\w.-]+"                     # почта
    r"|@[A-Za-z0-9_]{3,}"                            # @ник
    r"|https?://\S+"
    r"|t\.me/\S+"
    r"|tg://\S+"
    r"|vk\.(?:com|ru)/\S+"
    r"|(?<![\w@/.])[\w-]+(?:\.[\w-]+)*\.(?:ru|com|me|in|net|org|su|io|рф)(?:/\S*)?(?![\w])",
    re.I,
)
#: ссылка на реестр РКН контактом не считается никогда…
RKN_LINK_RE = re.compile(r"gosuslugi\.ru/snet|knd\.gov\.ru", re.I)
#: …как и любая ссылка (не @ник и не почта), перед которой в 60 символах той же
#: строки стоит РКН / Роскомнадзор / реестр / перечень
RKN_NEAR_RE = re.compile(r"(?:ркн|роскомнадзор|реестр|перечень|перечне)[^\n]{0,60}$", re.I)
RKN_NEAR_WINDOW = 70

#: адрес биржи-конкурента: сам себе и маркер, и контакт
COMPETITOR_RE = re.compile(r"telega\.i[no]|telegram-ads|tgstat|telemetr|perfluence", re.I)

#: маркер: без учёта регистра, на границе слова
MARKER_RE = re.compile(
    r"(?<![а-яёa-z])(?:"
    r"по\s+(?:всем\s+)?вопросам"
    r"|для\s+связи"
    r"|реклам\w*|сотрудничеств\w*|прайс\w*|менеджер\w*|пиар\w*|коллаб\w*|партн[её]рств\w*"
    r"|pr|adv|ads"
    r"|связь|предложка|контакт\w*|размещени\w*"
    r")(?![а-яёa-z])",
    re.I,
)
#: не подпись контакта, а услуга или должность
MARKER_EXCEPT_RE = re.compile(
    r"^(?:прайс\w*\s+на\s+(?:услуг|товар|продаж)|менеджер\w*\s+по\s+(?:продаж|проект))",
    re.I,
)

#: маркер → контакт не дальше стольких символов
MAX_GAP = 60
#: конец фразы между маркером и контактом — стоп
HARD_END_RE = re.compile(r"[.!?](?=\s|$)")
#: перенос строки допустим, если до него после маркера только `:`, `-`, `—`, `→`, эмодзи, пробелы
PRE_NEWLINE_OK_RE = re.compile(r"^[\s:\-—–→➡" + _EMOJI + r"\uFE0F\u200D]*$")
#: цепочка контактов: «@a / @b, @c», «@a и @b», «@a или @b»
CHAIN_SEP_RE = re.compile(r"[\s,/|]+(?:(?:и|или)\s+)?")
#: граница при расширении назад: перенос, конец фразы, эмодзи, буллет, « - », « — », «|»
BACK_BOUNDARY_RE = re.compile(r"\n|[.!?](?=\s)|[" + _EMOJI + r"]|[•·▪➖|]|\s[-—–]\s")
BACK_MAX_WORDS = 4
SERVICE_WORDS = {
    "по", "для", "вопросы", "вопросам", "всем", "и", "или", "о", "об", "контакт", "контакты",
    "связь", "запись", "предложить", "купить", "заказать", "размещение", "размещению",
    "размещения", "отзывы", "рекламодателей", "канал", "ваша", "вашей", "здесь", "тут", "сюда",
    "писать", "пишите", "обращаться", "вопрос",
    "почта", "email", "e-mail", "телеграм", "тг", "tg", "с", "нами", "мной", "разместить",
}
WORD_STRIP = ":,;-—–→➡()«»\"'"
#: висящие разделители на стыке после вырезки; знак конца фразы снимается,
#: только если стоял сразу за контактом и за ним пробел или конец текста
JUNK_LEFT_RE = re.compile(r"[ \t]*[:\-—–→➡/|·•,]+[ \t]*$")
JUNK_RIGHT_RE = re.compile(r"^[ \t]*(?:[:\-—–→➡/|·•,]|[.;!?](?=\s|$))+[ \t]*")
SPACES_RE = re.compile(r"[ \t]{2,}")


def _is_rkn(text: str, s: int, e: int) -> bool:
    tok = text[s:e]
    if RKN_LINK_RE.search(tok):
        return True
    if "@" in tok:  # @ник и почта реестром не бывают
        return False
    return bool(RKN_NEAR_RE.search(text[max(0, s - RKN_NEAR_WINDOW):s]))


def _contacts(text: str) -> list[tuple[int, int]]:
    """Все токены контактов (start, end), без РКН. Адрес конкурента — контакт всегда,
    даже голым словом и даже рядом с «РКН»."""
    comp = []
    for m in COMPETITOR_RE.finditer(text):
        s, e = m.start(), m.end()
        while s > 0 and not text[s - 1].isspace():
            s -= 1
        while e < len(text) and not text[e].isspace():
            e += 1
        if not comp or comp[-1][1] <= s:
            comp.append((s, e))
    out = []
    for m in CONTACT_RE.finditer(text):
        if any(cs <= m.start() < ce for cs, ce in comp):
            continue
        if not _is_rkn(text, m.start(), m.end()):
            out.append((m.start(), m.end()))
    return sorted(out + comp)


def _chain_end(text: str, end: int, by_start: dict) -> int:
    """Продлить конец на следующие подряд идущие контакты («@a / @b, @c»)."""
    while True:
        m = CHAIN_SEP_RE.match(text, end)
        nxt = m.end() if m else end
        if nxt == end or nxt not in by_start:
            return end
        end = by_start[nxt]


def _extend_back(text: str, start: int, contact_ends: list) -> int:
    """Расширить начало назад на служебные слова («Вопросы по», «Купить»), не более 4."""
    left = 0
    for m in BACK_BOUNDARY_RE.finditer(text, 0, start):
        left = m.end()
    for ce in contact_ends:
        if ce <= start and ce > left:
            left = ce
    words = text[left:start].split()
    taken = 0
    pos = start
    for w in reversed(words):
        if taken >= BACK_MAX_WORDS or w.strip(WORD_STRIP).lower() not in SERVICE_WORDS:
            break
        pos = text.rfind(w, left, pos)
        taken += 1
    return pos


def _spans(text: str) -> list[tuple[int, int]]:
    """Вырезаемые фрагменты (start, end), по порядку, без пересечений."""
    contacts = _contacts(text)
    by_start = {s: e for s, e in contacts}
    contact_ends = [e for _, e in contacts]

    cands = []  # (marker_start, marker_end, competitor?)
    for m in MARKER_RE.finditer(text):
        if MARKER_EXCEPT_RE.match(text, m.start()):
            continue
        if any(s <= m.start() < e for s, e in contacts):  # «pr» внутри @ника — не маркер
            continue
        cands.append((m.start(), m.end(), False))
    for s, e in contacts:
        if COMPETITOR_RE.search(text[s:e]):
            cands.append((s, s, True))
    cands.sort()

    spans = []
    cur_end = -1
    for ms, me, competitor in cands:
        if ms < cur_end:
            continue
        if competitor:
            first_e = by_start[ms]
        else:
            first_e = None
            for s, e in contacts:
                if s < me:
                    continue
                if s - me > MAX_GAP:
                    break
                between = text[me:s]
                if HARD_END_RE.search(between):
                    break
                if "\n" in between and not PRE_NEWLINE_OK_RE.match(between.split("\n", 1)[0]):
                    break
                first_e = e
                break
            if first_e is None:
                continue
        end = _chain_end(text, first_e, by_start)
        start = max(_extend_back(text, ms, contact_ends), cur_end)
        spans.append((start, end))
        cur_end = end
    return spans


def strip_ad_contacts(text: str | None) -> str:
    """Вырезать из описания подписи рекламных контактов: «Реклама: @x»,
    «По вопросам сотрудничества 👉 @x, @y», «Купить рекламу https://telega.in/…».

    Маркер (реклам*, сотрудничеств*, прайс*, менеджер*, pr, связь, контакт*,
    «по вопросам», «для связи», … или адрес биржи-конкурента) плюс ближайший токен
    контакта (@ник, почта, ссылка) не дальше 60 символов и без конца фразы между
    ними. Начало расширяется назад на служебные слова («Вопросы по», «Купить»),
    хвост — на цепочку контактов. Ссылки на реестр РКН не трогаются, одиночный
    контакт без маркера остаётся, переносы строк сохраняются (их схлопнет `clip`).
    Чистая функция: строка на входе, строка на выходе, пусто → «».
    """
    if not text:
        return ""
    spans = _spans(text)
    if not spans:
        return text
    pieces = []
    pos = 0
    for s, e in spans:
        pieces.append(text[pos:s])
        pos = e
    pieces.append(text[pos:])
    res = pieces[0]
    for piece in pieces[1:]:
        res = JUNK_LEFT_RE.sub("", res)
        piece = JUNK_RIGHT_RE.sub("", piece)
        if res and piece and not res[-1].isspace() and not piece[0].isspace():
            res += " "
        res += piece
    res = SPACES_RE.sub(" ", res)
    res = re.sub(r"[ \t]*\n[ \t]*", "\n", res)
    return res.strip()
