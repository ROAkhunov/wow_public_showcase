"""T-67: форма «Сообщить о неточности» — состав и проверка полей.

Валидация только формы: существует ли канал с такой площадкой и именем,
здесь не проверяется — «канал не существует или закрыт» сам по себе один из
шести вариантов проблемы, отклонять обращение из-за него нельзя.
"""
from __future__ import annotations

from dataclasses import dataclass, field

KINDS = (
    "Неверное число подписчиков",
    "Неверный охват или ER",
    "Неверные рекламодатели",
    "Канал не существует или закрыт",
    "Канал привязан не к тому автору",
    "Другое",
)

MAX_DETAILS = 5_000
MAX_EMAIL = 254

#: потолок длины адреса возврата. Хвост фильтров каталога в разы короче;
#: всё, что длиннее, это не наша выдача, а чужая полезная нагрузка.
MAX_BACK = 512

#: имя поля-приманки в форме. Заполнено — значит форму отправил не человек:
#: скрытое поле автозаполнитель браузера не видит и не трогает.
HONEYPOT_FIELD = "hp_topic"


@dataclass
class ReportForm:
    """Введённые значения плюс ошибки. Один объект и для первого показа формы
    (пустой, без ошибок), и для повторного показа после отклонённой отправки —
    введённое не теряется (DoD)."""
    platform: str | None = None
    username_lower: str | None = None
    kind: str = KINDS[0]
    details: str = ""
    email: str = ""
    back: str | None = None
    errors: dict[str, str] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.errors


def valid_email(raw: str) -> bool:
    """Наличие `@` и точки, не строже: строгая проверка отсекает живые адреса
    чаще, чем мусорные (решение в ТЗ T-67)."""
    return "@" in raw and "." in raw


def safe_back(raw: str | None) -> str | None:
    r"""Адрес возврата из параметра, или None, если ему нельзя доверять.

    Проверяется только начало: хвост параметров сохраняется целиком, в нём и
    лежат фильтры, ради которых адрес вообще передаётся. Обрезать всё после
    вопросительного знака значит вернуть человека на голый каталог.

    Обратный слэш перед проверкой считается тем же символом, что и прямой:
    `/\evil.tld` проходит наивную проверку «один слэш в начале», а браузер
    разворачивает его в переход на сторонний сайт.
    """
    raw = raw or ""
    if not raw or len(raw) > MAX_BACK:
        return None
    # Перевод строки в адресе — это уже не адрес, а попытка дописать заголовок.
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in raw):
        return None
    # Свой путь начинается с одного прямого слэша — и до нормализации тоже:
    # `\evil.tld` браузер развернёт в свой же корень, но адресом выдачи он не
    # был никогда, и принимать его незачем.
    if not raw.startswith("/"):
        return None
    # Обратный слэш дальше считается тем же символом: `/\evil.tld` проходит
    # наивную проверку «один слэш в начале», а браузер уводит по нему наружу.
    path = raw.replace("\\", "/")
    if path.startswith("//"):
        return None
    return path


def back_or_channel(back: str | None, platform: str | None,
                     username_lower: str | None) -> str:
    """Куда уводит «Отмена»: на переданную выдачу, иначе на страницу канала,
    иначе в каталог. Вызывающий передаёт площадку и имя, только если такой
    канал в дампе есть, — иначе возврат вёл бы на 404."""
    if back:
        return back
    if platform and username_lower:
        return f"/{platform}/{username_lower}"
    return "/"


def channel_params(platform: str | None, username_lower: str | None,
                    platforms: tuple[str, ...]) -> tuple[str | None, str | None]:
    """Площадка и имя канала из адресной строки, или (None, None), если пара
    неполная или площадка не из списка — общее обращение по каталогу."""
    username_lower = (username_lower or "").strip().lower() or None
    if platform not in platforms or not username_lower:
        return None, None
    return platform, username_lower


def parse(form: dict, *, platforms: tuple[str, ...]) -> ReportForm:
    """Разобрать и провалидировать тело POST. Приманку проверяет вызывающий
    код раньше — он же решает, писать ли обращение в базу вовсе."""
    platform, username_lower = channel_params(
        form.get("platform"), form.get("username_lower"), platforms)

    kind = form.get("kind", "")
    details = (form.get("details") or "").strip()
    email = (form.get("email") or "").strip()

    out = ReportForm(platform=platform, username_lower=username_lower,
                      kind=kind if kind in KINDS else KINDS[0],
                      details=details, email=email,
                      back=safe_back(form.get("back")))

    if kind not in KINDS:
        out.errors["kind"] = "Выберите, что не так, из списка"
    if not details:
        out.errors["details"] = "Опишите, что видите неверного"
    if email and (len(email) > MAX_EMAIL or not valid_email(email)):
        out.errors["email"] = "Проверьте адрес: не похож на почту"
    return out
