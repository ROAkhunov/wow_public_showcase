"""T-81: у витрины есть свой знак во вкладке, в закладке и на экране телефона.

Проверяется отданное сервисом, а не файлы на диске: браузер видит ровно то,
что приехало по HTTP. Корневые адреса стоят отдельно от `/assets/` намеренно —
за `/favicon.ico` и `/apple-touch-icon.png` браузер и iOS ходят сами, без
ссылок в разметке, и там их встречает заглушка раздела `/{platform}`, если
маршрут не зарегистрирован раньше неё.
"""
import pytest

pytestmark = pytest.mark.integration


ICONS = {
    "/assets/favicon.svg": "image/svg+xml",
    "/assets/favicon.ico": ("image/x-icon", "image/vnd.microsoft.icon"),
    "/assets/apple-touch-icon.png": "image/png",
    "/favicon.ico": ("image/x-icon", "image/vnd.microsoft.icon"),
    "/apple-touch-icon.png": "image/png",
}


@pytest.mark.parametrize("path, kind", ICONS.items())
def test_icon_is_served_as_a_picture(client, path, kind):
    answer = client.get(path)
    assert answer.status_code == 200, path
    got = answer.headers["content-type"].split(";")[0].strip()
    expected = (kind,) if isinstance(kind, str) else kind
    assert got in expected, f"{path} отдан как {got}"
    assert answer.content, f"{path} пустой"


def test_favicon_is_the_header_mark(client):
    """Знак во вкладке и знак в шапке — один знак, а не два похожих."""
    svg = client.get("/assets/favicon.svg").text.lower()
    assert "#0d6e63" in svg, "цвет знака разошёлся с токеном --accent"
    assert "<script" not in svg


def test_every_page_points_at_the_icon(layer, client):
    """Ссылки стоят в общем каркасе, значит есть на любой странице."""
    layer.channel(1, "tg", "example_channel")
    layer.go_live()

    for path in ("/", "/tg", "/tg/example_channel"):
        html = client.get(path).text
        assert 'rel="icon"' in html, path
        assert "/assets/favicon.svg" in html, path
        assert "/assets/favicon.ico" in html, path
        assert "apple-touch-icon" in html, path


def test_the_component_gallery_is_still_private(client):
    """Белый список расширен иконками, а не открыт целиком."""
    for path in ("/assets/specimen.html", "/assets/preview.css", "/assets/README.md"):
        assert client.get(path).status_code == 404, path
