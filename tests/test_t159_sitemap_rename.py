"""T-159: файлы карточек в карте сайта под новыми именами.

Search Console 12.10 закэшировал `sitemap-2.xml` как «Не получено» и не
перечитывает его. Файлы карточек переехали на `/sitemap-channels-{n}.xml`,
индекс перечисляет только их и `sitemap-sections.xml`. Старые адреса отдают
то же содержимое, пока Google их помнит, но в индекс не попадают.

Карта режется по два канала на файл, чтобы файлов было несколько: номер
второго и третьего проверяется так же, как первого.
"""
import re

import pytest


@pytest.fixture
def chunked(layer, make_client):
    for i in range(1, 6):
        layer.channel(i, "tg", f"chan_{i}", subscribers=100_000 - i)
    layer.go_live()
    return make_client(sitemap_chunk=2)


def locs(xml: str) -> list[str]:
    return [url.split("fomobase.ru")[-1] for url in re.findall(r"<loc>(.*?)</loc>", xml)]


def test_channel_files_answer_under_the_new_names(chunked):
    seen = []
    for n in (1, 2, 3):
        answer = chunked.get(f"/sitemap-channels-{n}.xml")
        assert answer.status_code == 200, n
        assert answer.headers["content-type"].startswith("application/xml"), n
        assert "<urlset" in answer.text, n
        seen += locs(answer.text)
    assert sorted(seen) == sorted(f"/tg/chan_{i}" for i in range(1, 6))


def test_index_lists_sections_and_new_names_only(chunked):
    files = locs(chunked.get("/sitemap.xml").text)
    assert files == ["/sitemap-sections.xml", "/sitemap-channels-1.xml",
                     "/sitemap-channels-2.xml", "/sitemap-channels-3.xml"]
    assert not any(re.fullmatch(r"/sitemap-\d+\.xml", f) for f in files)


def test_old_address_keeps_the_same_content(chunked):
    for n in (1, 2, 3):
        old = chunked.get(f"/sitemap-{n}.xml")
        new = chunked.get(f"/sitemap-channels-{n}.xml")
        assert old.status_code == 200, n
        assert old.text == new.text, n
        assert old.headers["content-type"] == new.headers["content-type"], n


def test_unknown_channel_file_is_a_404_page(chunked):
    for bad in ("/sitemap-channels-99.xml", "/sitemap-channels-4.xml",
                "/sitemap-channels-abc.xml", "/sitemap-channels-0.xml",
                "/sitemap-channels-².xml", "/sitemap-channels-.xml"):
        answer = chunked.get(bad)
        assert answer.status_code == 404, bad
        assert "text/html" in answer.headers["content-type"], bad


def test_sections_file_is_not_shadowed(chunked):
    assert chunked.get("/sitemap-sections.xml").status_code == 200
