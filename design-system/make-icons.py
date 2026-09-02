"""Растровые иконки витрины из того же знака, что стоит в шапке (T-81).

Рисуются скриптом, а не руками в редакторе: знак задан геометрией `.logo-mark`
и цветом токена `--accent`, и когда токен поменяется, иконка перерисовывается
одной командой, а не ищется по переписке. Внешних библиотек нет намеренно —
Pillow ради трёх прямоугольников в зависимости сервиса не тянем.

    python design-system/make-icons.py

Кладёт рядом `favicon.ico` (32) и `apple-touch-icon.png` (180). Векторный
`favicon.svg` лежит в репозитории руками и остаётся источником геометрии:
цифры ниже — те же самые.
"""
import struct
import zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent

ACCENT = (0x0D, 0x6E, 0x63)
WHITE = (0xFF, 0xFF, 0xFF)

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


def png(size: int) -> bytes:
    raw = render(size)
    stride = size * 4
    # Фильтр 0 на каждой строке: картинка из трёх заливок жмётся и так.
    lines = b"".join(b"\x00" + raw[i * stride:(i + 1) * stride] for i in range(size))

    def chunk(tag: bytes, body: bytes) -> bytes:
        return (struct.pack(">I", len(body)) + tag + body
                + struct.pack(">I", zlib.crc32(tag + body) & 0xFFFFFFFF))

    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(lines, 9))
            + chunk(b"IEND", b""))


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
    print("favicon.ico (32), apple-touch-icon.png (180)")
