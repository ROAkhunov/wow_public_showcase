"""Микросервис публичной витрины (T-61): адреса, шаблоны, заголовки для краулера.

Страницы отдаются готовым серверным HTML без единой строчки клиентского JS —
решение об архитектуре: каталог неинтерактивен, а краулеру и Core Web Vitals так
лучше всего. Отсюда же inline-SVG вместо графика на JS.

Адреса каналов (`/tg/example_channel`) переигрывать нельзя: смена адресов после
индексации обнуляет накопленный индекс, а он и есть цель направления.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, Request
from fastapi.responses import (FileResponse, HTMLResponse, PlainTextResponse,
                               RedirectResponse, Response)
from fastapi.templating import Jinja2Templates

from app import format as fmt
from app.chart import sparkline
from app.db import Page, Showcase, ShowcaseUnavailable, pages_in
from app.settings import PLATFORM_CODES, PLATFORM_NAMES, PLATFORMS, Settings, from_env

ROOT = Path(__file__).resolve().parent.parent
ASSETS_DIR = ROOT / "design-system"

log = logging.getLogger("showcase")

#: значение X-Robots-Tag, когда сайт открыт, но страница в индекс не нужна.
FOLLOW_ONLY = "noindex, follow"
CLOSED = "noindex, nofollow"

#: что из дизайн-системы отдаётся наружу. Каталог целиком монтировать нельзя:
#: рядом с этими файлами лежат `specimen.html` и превью компонентов, а это
#: лишние индексируемые страницы на публичном домене.
PUBLIC_ASSETS = ("index.css", "tokens.css", "components.css", "fonts/fonts.css")


def positive_int(raw: str) -> int | None:
    """Целое из строки адреса, или None, если это не номер.

    Проверяется ASCII, а не только `isdigit`: юникодные «цифры» вроде `²` и `⁵`
    ему подходят, а `int()` их уже не берёт — и `?page=²` отвечал бы пятисоткой
    вместо 404. Это тот же класс, что 422 на `/sitemap-abc.xml`: краулеру на
    неизвестный адрес нужна страница 404, а не ошибка сервера.
    """
    if not (raw.isascii() and raw.isdigit()):
        return None
    number = int(raw)
    return number if number >= 1 else None


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or from_env()
    app = FastAPI(title="Fomobase", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.settings = settings
    app.state.db = Showcase(settings.dsn, settings.pool_min, settings.pool_max)

    templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
    templates.env.filters.update(num=fmt.num, pct=fmt.pct, signed=fmt.signed,
                                 date_ru=fmt.date_ru, clip=fmt.clip)
    templates.env.globals.update(plural=fmt.plural, platform_names=PLATFORM_NAMES,
                                 platform_codes=PLATFORM_CODES, platforms=PLATFORMS,
                                 settings=settings)
    app.state.templates = templates

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield
        app.state.db.close()

    app.router.lifespan_context = lifespan

    @app.middleware("http")
    async def robots_header(request: Request, call_next):
        """Один переключатель на весь сайт, как требует спека.

        Закрыт — `noindex` на каждом ответе. Открыт — в индекс идут карточки и
        первые страницы разделов, а вторая и дальше отдают `noindex, follow`:
        краулер проходит их насквозь до карточек, а клонов в индексе не копится.
        """
        response = await call_next(request)
        if settings.noindex:
            response.headers["X-Robots-Tag"] = CLOSED
        elif getattr(request.state, "robots", None):
            response.headers["X-Robots-Tag"] = request.state.robots
        return response

    def render(request: Request, template: str, status: int = 200, **context) -> HTMLResponse:
        return templates.TemplateResponse(
            request=request, name=template, status_code=status,
            context={"noindex": settings.noindex, **context})

    def not_found(request: Request, what: str = "Страница не найдена") -> HTMLResponse:
        return render(request, "404.html", status=404, what=what)

    def page_number(request: Request) -> int | None:
        """Номер страницы из `?page=`, или None, если такой страницы не бывает.

        Мусор, ноль и отрицательные — это несуществующий адрес, а не первая
        страница: подставив первую, мы завели бы бесконечное число адресов с
        одинаковым содержанием (US19).
        """
        return positive_int(request.query_params.get("page", "1"))

    def catalog_page(request: Request, *, title: str, subtitle: str, base_url: str,
                     platform: str | None = None, category: str | None = None,
                     section: str | None = None, counts: dict | None = None,
                     categories: list | None = None) -> HTMLResponse:
        """Один ход всех каталожных страниц: номер → выборка → пометка → рендер.

        Каталог, раздел площадки и раздел категории отличаются только заголовком
        и условием выборки, поэтому пагинация и её 404 живут в одном месте.
        """
        n = page_number(request)
        if n is None:
            return not_found(request, "Такой страницы каталога нет")
        page = app.state.db.catalog(platform=platform, category=category,
                                    page=n, size=settings.page_size)
        # Страница за последней — такой же несуществующий адрес, как неизвестный
        # канал: пустой список со статусом 200 краулер копил бы себе в индекс.
        if n > page.pages:
            return not_found(request, "Такой страницы каталога нет")
        if page.number > 1:
            request.state.robots = FOLLOW_ONLY
        return render(request, "catalog.html", page=page, title=title, subtitle=subtitle,
                      base_url=base_url, section=section,
                      counts=counts or {}, categories=categories or [],
                      built_at=app.state.db.build().built_at)

    # ── каталог и разделы ────────────────────────────────────────────────
    @app.get("/", response_class=HTMLResponse)
    def catalog(request: Request):
        return catalog_page(
            request, title="Каталог каналов",
            subtitle="Аудитория, охваты и реклама по данным открытых источников",
            base_url="/", counts=app.state.db.platform_counts(),
            categories=app.state.db.categories()[:24])

    @app.get("/category/{slug}", response_class=HTMLResponse)
    def category(request: Request, slug: str):
        name = app.state.db.category_name(slug)
        if not name:
            return not_found(request, "Такой категории нет")
        return catalog_page(
            request, title=name, subtitle=f"Каналы в категории «{name}»",
            base_url=f"/category/{quote(slug)}", category=slug,
            categories=app.state.db.categories()[:24])

    # ── статика дизайн-системы ───────────────────────────────────────────
    # Регистрируется до `/{platform}`, иначе раздел-заглушка перехватит адрес.
    @app.get("/assets/{path:path}")
    def asset(request: Request, path: str):
        font = path.startswith("fonts/") and path.endswith(".woff2") and path.count("/") == 1
        if path not in PUBLIC_ASSETS and not font:
            return not_found(request, "Такого файла нет")
        # Белого списка мало: имя файла в нём проверяется как строка, а из
        # каталога наружу уводит и обратный слэш («fonts/..\..\ключ.woff2»).
        # Решает уже разобранный путь, а не догадки о том, что считать
        # разделителем на этой системе.
        target = (ASSETS_DIR / path).resolve()
        if not target.is_relative_to(ASSETS_DIR.resolve()) or not target.is_file():
            return not_found(request, "Такого файла нет")
        return FileResponse(target)

    # ── краулер ──────────────────────────────────────────────────────────
    # Регистрируются до `/{platform}`: маршруты разбираются по порядку, и
    # каталог-заглушка перехватил бы и robots.txt, и карту сайта.
    @app.get("/robots.txt", response_class=PlainTextResponse)
    def robots(request: Request):
        if settings.noindex:
            body = ("# Витрина закрыта от индексации до подтверждения владельца.\n"
                    "User-agent: *\nDisallow: /\n")
        else:
            body = (f"User-agent: *\nAllow: /\n\n"
                    f"Sitemap: {settings.site_origin}/sitemap.xml\n")
        return PlainTextResponse(body)

    def sitemap_chunks() -> int:
        return pages_in(app.state.db.channels_total(), settings.sitemap_chunk)

    @app.get("/sitemap.xml")
    def sitemap_index(request: Request):
        xml = app.state.templates.get_template("sitemap_index.xml").render(
            chunks=range(1, sitemap_chunks() + 1), origin=settings.site_origin)
        return Response(xml, media_type="application/xml")

    # Номер принимается строкой и проверяется руками: на `/sitemap-abc.xml`
    # валидатор FastAPI ответил бы своим JSON с кодом 422, а краулеру на
    # неизвестный адрес нужна страница 404.
    @app.get("/sitemap-{number}.xml")
    def sitemap_chunk(request: Request, number: str):
        n = positive_int(number)
        if n is None or n > sitemap_chunks():
            return not_found(request, "Такого файла карты сайта нет")
        rows = app.state.db.sitemap_chunk(n, settings.sitemap_chunk)
        xml = app.state.templates.get_template("sitemap.xml").render(
            rows=rows, origin=settings.site_origin)
        return Response(xml, media_type="application/xml")

    # ── разделы площадок и страница канала ───────────────────────────────
    @app.get("/{platform}", response_class=HTMLResponse)
    def platform_section(request: Request, platform: str):
        if platform not in PLATFORMS:
            return not_found(request)
        name = PLATFORM_NAMES[platform]
        return catalog_page(request, title=f"Каналы · {name}",
                            subtitle=f"Все площадки {name} в базе",
                            base_url=f"/{platform}", platform=platform, section=platform)

    @app.get("/{platform}/{username}", response_class=HTMLResponse)
    def channel(request: Request, platform: str, username: str):
        if platform not in PLATFORMS:
            return not_found(request)
        # У канала ровно один адрес, и он в нижнем регистре. Иначе одна и та же
        # страница жила бы по двум адресам, а страницы-клоны роняют оценку
        # домена целиком (US19). Регистр приводим до похода в базу.
        if username != username.lower():
            return RedirectResponse(f"/{platform}/{username.lower()}", status_code=301)
        row = app.state.db.channel(platform, username)
        if not row:
            return not_found(request, "Такого канала в базе нет")
        return render(request, "channel.html", c=row, chart=sparkline(row["history"]),
                      posts=row["posts"], built_at=row["built_at"])

    # ── дамп ещё не собран ───────────────────────────────────────────────
    @app.exception_handler(ShowcaseUnavailable)
    def no_live_schema(request: Request, exc: ShowcaseUnavailable):
        # Отказ обслуживания не уходит в тишину: правило проекта — потеря и
        # отказ это warning, а не debug (WOWlist_manage/CLAUDE.md).
        log.warning("витрина недоступна на %s: %s", request.url.path, exc)
        return render(request, "404.html", status=503,
                      what="Витрина ещё наполняется, загляните чуть позже")

    return app
