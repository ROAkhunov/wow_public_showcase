"""Растровые иконки витрины из того же знака, что стоит в шапке (T-81).

Рисуются скриптом, а не руками в редакторе: знак задан геометрией `.logo-mark`
и цветом токена `--accent`, и когда токен поменяется, иконка перерисовывается
одной командой, а не ищется по переписке. Внешних библиотек нет намеренно —
Pillow ради трёх прямоугольников в зависимости сервиса не тянем.

    python design-system/make-icons.py

Кладёт рядом `favicon.ico` (32), `apple-touch-icon.png` (180) и картинку
превью ссылки `og-cover.png` (1200x630, T-83). Векторный `favicon.svg` лежит в
репозитории руками и остаётся источником геометрии: цифры ниже — те же самые.
"""
import struct
import zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent

ACCENT = (0x0D, 0x6E, 0x63)
WHITE = (0xFF, 0xFF, 0xFF)
#: фон превью ссылки — тот же тёплый небелёный, что у страницы (--bg)
PAGE_BG = (0xFA, 0xF9, 0xF7)

#: размер картинки превью: 1200x630 — то, что ждут и Телеграм, и соцсети.
OG_SIZE = (1200, 630)
OG_MARK = 260

#: геометрия знака в единицах вьюбокса 32x32, один в один с `favicon.svg`
BOX = 32.0
RADIUS = 8.0
BARS = (  # x, y, ширина, высота
    (10.5, 7.0, 4.0, 18.0),
    (10.5, 7.0, 11.0, 4.0),
    (10.5, 14.0, 9.0, 4.0),
)
SS = 4  # кратность суперсэмплинга: края скругления без него рвутся ступенькой


def _inside_square(x: float, y: float, size: float, r: float) -> bool:
    """Точка внутри скруглённого квадрата размером size со скруглением r."""
    cx = min(max(x, r), size - r)
    cy = min(max(y, r), size - r)
    return (x - cx) ** 2 + (y - cy) ** 2 <= r * r


def render(size: int) -> bytes:
    """RGBA-пиксели знака стороной size, слева направо и сверху вниз."""
    scale = size / BOX
    r = RADIUS * scale
    bars = [(bx * scale, by * scale, bw * scale, bh * scale) for bx, by, bw, bh in BARS]
    step = 1.0 / SS
    rows = bytearray()
    for py in range(size):
        for px in range(size):
            hits = ink = 0
            for sy in range(SS):
                y = py + (sy + 0.5) * step
                for sx in range(SS):
                    x = px + (sx + 0.5) * step
                    if not _inside_square(x, y, float(size), r):
                        continue
                    hits += 1
                    if any(bx <= x < bx + bw and by <= y < by + bh for bx, by, bw, bh in bars):
                        ink += 1
            if not hits:
                rows += bytes(4)
                continue
            total = SS * SS
            share = ink / hits
            rgb = tuple(round(ACCENT[i] + (WHITE[i] - ACCENT[i]) * share) for i in range(3))
            rows += bytes((*rgb, round(255 * hits / total)))
    return bytes(rows)


def encode(raw: bytes, width: int, height: int) -> bytes:
    stride = width * 4
    # Фильтр 0 на каждой строке: картинка из трёх заливок жмётся и так.
    lines = b"".join(b"\x00" + raw[i * stride:(i + 1) * stride] for i in range(height))

    def chunk(tag: bytes, body: bytes) -> bytes:
        return (struct.pack(">I", len(body)) + tag + body
                + struct.pack(">I", zlib.crc32(tag + body) & 0xFFFFFFFF))

    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(lines, 9))
            + chunk(b"IEND", b""))


def png(size: int) -> bytes:
    return encode(render(size), size, size)


def og_cover() -> bytes:
    """Картинка превью ссылки: знак на фоне страницы.

    Одна на весь сайт и без текста намеренно: превью с именем канала пришлось
    бы рисовать на каждую из 143 тысяч карточек, а знак и фон узнаются и так.
    Собирается тем же кодом, что иконки, — знак задан геометрией, а не файлом
    из редактора.
    """
    width, height = OG_SIZE
    mark = render(OG_MARK)
    left, top = (width - OG_MARK) // 2, (height - OG_MARK) // 2
    row = bytes((*PAGE_BG, 255)) * width
    canvas = bytearray(row * height)
    for y in range(OG_MARK):
        for x in range(OG_MARK):
            i = (y * OG_MARK + x) * 4
            alpha = mark[i + 3]
            if not alpha:
                continue
            j = ((top + y) * width + left + x) * 4
            for c in range(3):
                # знак кладётся поверх фона с учётом прозрачности края
                canvas[j + c] = round((mark[i + c] * alpha + PAGE_BG[c] * (255 - alpha)) / 255)
    return encode(bytes(canvas), width, height)


def ico(size: int) -> bytes:
    """ICO с PNG внутри: так умеют все браузеры, которым ICO вообще нужен."""
    body = png(size)
    header = struct.pack("<HHH", 0, 1, 1)
    entry = struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0, 1, 32,
                        len(body), struct.calcsize("<HHH") + struct.calcsize("<BBBBHHII"))
    return header + entry + body


if __name__ == "__main__":
    (HERE / "favicon.ico").write_bytes(ico(32))
    (HERE / "apple-touch-icon.png").write_bytes(png(180))
    (HERE / "og-cover.png").write_bytes(og_cover())
    print("favicon.ico (32), apple-touch-icon.png (180), og-cover.png (1200x630)")
