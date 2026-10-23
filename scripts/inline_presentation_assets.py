"""Inline a Marp HTML deck's local images so the file travels on its own.

`marp -o deck.html` leaves images as relative paths like `./images/foo.gif`,
so the deck only renders while it sits next to `presentation/images/`. This
rewrites every local reference as a base64 `data:` URI, giving a single file
that can be opened anywhere -- and, unlike the PDF build, one where animated
GIFs still animate.

    task presentation:html SLIDES=from-data-ingestion-to-context-engineering.md
"""

from __future__ import annotations

import base64
import mimetypes
import re
import sys
from pathlib import Path

SRC_REFERENCE = re.compile(r'src="([^"]+)"')
CSS_URL_REFERENCE = re.compile(r"""url\((['"]?)([^'")]+)\1\)""")
REMOTE_SCHEMES = ("data:", "http://", "https://", "//")


def to_data_uri(asset: Path) -> str:
    """Return *asset* encoded as a base64 `data:` URI."""
    mime, _ = mimetypes.guess_type(asset.name)
    payload = base64.b64encode(asset.read_bytes()).decode("ascii")
    return f"data:{mime or 'application/octet-stream'};base64,{payload}"


def inline_assets(deck: Path) -> int:
    """Rewrite local asset references in *deck* in place, returning the count."""
    inlined = 0

    def resolve(reference: str) -> str | None:
        """Return the data URI for a local *reference*, or None to keep it."""
        if reference.startswith(REMOTE_SCHEMES):
            return None
        asset = (deck.parent / reference).resolve()
        return to_data_uri(asset) if asset.is_file() else None

    def handle_src(match: re.Match[str]) -> str:
        nonlocal inlined
        data_uri = resolve(match.group(1))
        if data_uri is None:
            return match.group(0)
        inlined += 1
        return f'src="{data_uri}"'

    def handle_css_url(match: re.Match[str]) -> str:
        nonlocal inlined
        quote, reference = match.groups()
        data_uri = resolve(reference)
        if data_uri is None:
            return match.group(0)
        inlined += 1
        return f"url({quote}{data_uri}{quote})"

    html = deck.read_text()
    html = SRC_REFERENCE.sub(handle_src, html)
    html = CSS_URL_REFERENCE.sub(handle_css_url, html)
    deck.write_text(html)
    return inlined


def main() -> None:
    """Inline every deck passed on the command line."""
    decks = [Path(argument) for argument in sys.argv[1:]]
    if not decks:
        sys.exit("usage: inline_presentation_assets.py DECK.html [DECK.html ...]")

    for deck in decks:
        if not deck.is_file():
            sys.exit(f"no such deck: {deck}")
        inlined = inline_assets(deck)
        size_mb = deck.stat().st_size / 1024 / 1024
        print(f"{deck}: inlined {inlined} assets ({size_mb:.1f} MB)")


if __name__ == "__main__":
    main()
