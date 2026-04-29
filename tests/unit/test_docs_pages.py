"""Static checks for GitHub Pages documentation."""

from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

DOCS_ROOT = Path(__file__).resolve().parents[2] / "docs"


class LinkParser(HTMLParser):
    """Collect HTML links from a static document."""

    def __init__(self) -> None:
        super().__init__()
        self.hrefs: list[str] = []
        self.images: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key: value for key, value in attrs}
        if tag == "a" and values.get("href"):
            self.hrefs.append(values["href"] or "")
        if tag == "meta" and values.get("property") == "og:image" and values.get("content"):
            self.images.append(values["content"] or "")


def test_pages_landing_has_no_injected_or_dead_links() -> None:
    html = (DOCS_ROOT / "index.html").read_text()

    assert "omelette" not in html.lower()
    assert "claude.complete" not in html
    assert 'href="#"' not in html
    assert "Working memory" in html


def test_pages_landing_local_links_resolve() -> None:
    parser = LinkParser()
    parser.feed((DOCS_ROOT / "index.html").read_text())

    for href in parser.hrefs:
        parsed = urlparse(href)
        if parsed.scheme or parsed.netloc or href.startswith("#"):
            continue
        local_path = (DOCS_ROOT / parsed.path).resolve()
        assert local_path.is_relative_to(DOCS_ROOT.resolve())
        source_path = local_path.with_suffix(".md") if local_path.suffix == ".html" else local_path
        assert local_path.exists() or source_path.exists(), href


def test_pages_landing_social_preview_asset_exists() -> None:
    parser = LinkParser()
    parser.feed((DOCS_ROOT / "index.html").read_text())

    assert parser.images
    image_path = urlparse(parser.images[0]).path.removeprefix("/gwt-context/")
    assert (DOCS_ROOT / image_path).exists()
