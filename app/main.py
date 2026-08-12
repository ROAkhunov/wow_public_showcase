"""Микросервис публичной витрины (T-61): адреса, шаблоны, заголовки для краулера.

Страницы отдаются готовым серверным HTML без единой строчки клиентского JS —
решение об архитектуре: каталог неинтерактивен, а краулеру и Core Web Vitals так
лучше всего. Отсюда же inline-SVG вместо графика на JS.

Адреса каналов (`/tg/example_channel`) переигрывать нельзя: смена адресов после
индексации обнуляет накопленный индекс, а он и есть цель направления.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app import format as fmt
from app.chart import sparkline
from app.db import Page, Showcase, ShowcaseUnavailable
from app.settings import PLATFORM_NAMES, PLATFORMS, Settings, from_env

ROOT = Path(__file__).resolve().parent.parent

#: значение X-Robots-Tag, когда сайт открыт, но страница в индекс не нужна.
FOLLOW_ONLY = "noindex, follow"
CLOSED = "noindex, nofollow"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or from_env()
    app = FastAPI(title="Fomobase", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.settings = settings
    app.state.db = Showcase(settings.dsn, settings.pool_min, settings.pool_max)

    templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
    templates.env.filters.update(num=fmt.num, pct=fmt.pct, signed=fmt.signed,
                                 date_ru=fmt.date_ru, clip=fmt.clip)
    templates.env.globals.update(plural=fmt.plural, platform_names=PLATFORM_NAMES,
                                 platforms=PLATFORMS, settings=settings)
    app.state.templates = templates

    app.mount("/assets", StaticFiles(directory=str(ROOT / "design-system")), name="assets")

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

    def page_number(request: Request) -> int:
        raw = request.query_params.get("page", "1")
        return max(1, int(raw)) if raw.isdigit() else 1

    def mark_pagination(request: Request, page: Page) -> None:
        if page.number > 1:
            request.state.robots = FOLLOW_ONLY

    # ── каталог и разделы ────────────────────────────────────────────────
    @app.get("/", response_class=HTMLResponse)
    def catalog(request: Request):
        n = page_number(request)
        page = app.state.db.catalog(page=n, size=settings.page_size)
        mark_pagination(request, page)
        return render(request, "catalog.html", page=page, title="Каталог каналов",
                      subtitle="Аудитория, охваты и реклама по данным открытых источников",
                      base_url="/", counts=app.state.db.platform_counts(),
                      categories=app.state.db.categories()[:24],
                      built_at=app.state.db.build().built_at)

    @app.get("/category/{slug}", response_class=HTMLResponse)
    def category(request: Request, slug: str):
        name = app.state.db.category_name(slug)
        if not name:
            return not_found(request, "Такой категории нет")
        n = page_number(request)
        page = app.state.db.catalog(category=slug, page=n, size=settings.page_size)
        mark_pagination(request, page)
        return render(request, "catalog.html", page=page, title=name,
                      subtitle=f"Каналы в категории «{name}»",
                      base_url=f"/category/{quote(slug)}",
                      counts={}, categories=app.state.db.categories()[:24],
                      built_at=app.state.db.build().built_at)

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

    @app.get("/sitemap.xml")
    def sitemap_index(request: Request):
        total = app.state.db.channels_total()
        chunks = max(1, -(-total // settings.sitemap_chunk))
        xml = app.state.templates.get_template("sitemap_index.xml").render(
            chunks=range(1, chunks + 1), origin=settings.site_origin)
        return Response(xml, media_type="application/xml")

    @app.get("/sitemap-{number}.xml")
    def sitemap_chunk(request: Request, number: int):
        total = app.state.db.channels_total()
        chunks = max(1, -(-total // settings.sitemap_chunk))
        if number < 1 or number > chunks:
            return not_found(request, "Такого файла карты сайта нет")
        rows = app.state.db.sitemap_chunk(number, settings.sitemap_chunk)
        xml = app.state.templates.get_template("sitemap.xml").render(
            rows=rows, origin=settings.site_origin)
        return Response(xml, media_type="application/xml")

    # ── разделы площадок и страница канала ───────────────────────────────
    @app.get("/{platform}", response_class=HTMLResponse)
    def platform_section(request: Request, platform: str):
        if platform not in PLATFORMS:
            return not_found(request)
        n = page_number(request)
        page = app.state.db.catalog(platform=platform, page=n, size=settings.page_size)
        mark_pagination(request, page)
        name = PLATFORM_NAMES[platform]
        return render(request, "catalog.html", page=page, title=f"Каналы · {name}",
                      subtitle=f"Все площадки {name} в базе", base_url=f"/{platform}",
                      counts={}, categories=[], built_at=app.state.db.build().built_at)

    @app.get("/{platform}/{username}", response_class=HTMLResponse)
    def channel(request: Request, platform: str, username: str):
        if platform not in PLATFORMS:
            return not_found(request)
        row = app.state.db.channel(platform, username)
        if not row:
            return not_found(request, "Такого канала в базе нет")
        return render(request, "channel.html", c=row, chart=sparkline(row["history"]),
                      posts=row["posts"], built_at=row["built_at"])

    # ── дамп ещё не собран ───────────────────────────────────────────────
    @app.exception_handler(ShowcaseUnavailable)
    def no_live_schema(request: Request, exc: ShowcaseUnavailable):
        return render(request, "404.html", status=503,
                      what="Витрина ещё наполняется, загляните чуть позже")

    return app


app = None  # создаётся в точке входа: см. app/asgi.py
