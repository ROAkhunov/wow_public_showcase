"""T-156: правки по аудиту индексации 08.10.

Тонкая тематика открывается людям, но в индекс и в карту не идёт; ShapBot
закрыт и в robots.txt, и в nginx. Индексируемость проверяется на клиенте с
открытым переключателем: на закрытом `noindex` стоит на каждом ответе, и тест
зазеленел бы, ничего не проверив.
"""
import re
from pathlib import Path

import pytest

from app.main import MIN_LANDING_CHANNELS

DEPLOY = Path(__file__).resolve().parent.parent / "deploy"


@pytest.fixture
def topics(layer):
    """Две тематики: одна на пороге посадочной, другая на канал меньше."""
    thick, thin = MIN_LANDING_CHANNELS, MIN_LANDING_CHANNELS - 1
    for i in range(1, thick + 1):
        layer.channel(i, "tg", f"thick_{i}", subscribers=100_000 - i)
        layer.category(i, "Толстая", "thick")
    for i in range(100, 100 + thin):
        layer.channel(i, "tg", f"thin_{i}", subscribers=50_000 - i)
        layer.category(i, "Тонкая", "thin")
    layer.section("", "", channels=thick + thin)
    layer.section("tg", "", channels=thick + thin)
    layer.section("", "thick", name="Толстая", channels=thick)
    layer.section("tg", "thick", name="Толстая", channels=thick)
    layer.section("", "thin", name="Тонкая", channels=thin)
    layer.section("tg", "thin", name="Тонкая", channels=thin)
    return layer.go_live()


def sections_map(client) -> list[str]:
    xml = client.get("/sitemap-sections.xml").text
    return [url.split("fomobase.ru")[-1] for url in re.findall(r"<loc>(.*?)</loc>", xml)]


def test_thin_category_opens_but_stays_out_of_the_index(topics, make_client):
    open_client = make_client(noindex=False)
    answer = open_client.get("/category/thin")
    assert answer.status_code == 200
    assert answer.headers["x-robots-tag"] == "noindex, follow"
    assert "/category/thin" not in sections_map(open_client)


def test_category_on_the_threshold_is_indexed_and_mapped(topics, make_client):
    open_client = make_client(noindex=False)
    answer = open_client.get("/category/thick")
    assert answer.status_code == 200
    assert "noindex" not in answer.headers.get("x-robots-tag", "")
    assert "/category/thick" in sections_map(open_client)


def test_closed_site_still_closes_the_thin_category_completely(topics, client):
    """Переключатель главнее: на закрытом сайте `nofollow` не ослабевает."""
    assert client.get("/category/thin").headers["x-robots-tag"] == "noindex, nofollow"


@pytest.mark.parametrize("noindex", [True, False])
def test_robots_file_shuts_shapbot_out_in_both_branches(make_client, noindex):
    body = make_client(noindex=noindex).get("/robots.txt").text
    assert "User-agent: ShapBot\nDisallow: /\n" in body


def test_nginx_maps_shapbot_case_insensitively_at_the_http_level():
    conf = (DEPLOY / "nginx-fomobase-cache.conf").read_text(encoding="utf-8")
    block = re.search(r"map \$http_user_agent \$(\w+) \{(.*?)\}", conf, re.S)
    assert block, "в nginx-fomobase-cache.conf нет карты по $http_user_agent"
    assert re.search(r'"~\*ShapBot"\s+1;', block.group(2))
    # Поисковики под карту не попадают.
    for bot in ("Googlebot", "YandexBot", "bingbot"):
        assert bot.lower() not in block.group(2).lower()


def test_nginx_answers_shapbot_403_on_every_address_of_the_site():
    cache = (DEPLOY / "nginx-fomobase-cache.conf").read_text(encoding="utf-8")
    var = re.search(r"map \$http_user_agent \$(\w+) \{", cache).group(1)
    conf = (DEPLOY / "nginx-fomobase.ru.conf").read_text(encoding="utf-8")
    main = conf.split("server_name fomobase.ru;", 1)[1]
    # На уровне server, до первого location: так 403 ложится и на robots.txt,
    # и на файлы подтверждения, и на аватарки.
    head = main.split("location", 1)[0]
    assert re.search(rf"if \(\${var}\) \{{\s*return 403;\s*\}}", head)
