"""Zip the committed Superset bundle with the ClickHouse password filled in.

The committed database YAML holds a placeholder, never the password, so no
secret is stored in git. This reads the bundle, swaps in the URL-quoted password
from the environment and writes a ZIP that `superset import-dashboards` accepts.
"""

from __future__ import annotations

import os
import sys
import zipfile
from pathlib import Path
from urllib.parse import quote

BUNDLE_DIR = Path(__file__).parent / "bundle"
EXPORT_ROOT = "aictx_bundle"
PLACEHOLDER = "__CLICKHOUSE_SUPERSET_READER_PASSWORD__"
CREDENTIAL_ENV = "CLICKHOUSE_SUPERSET_READER_PASSWORD"


def render_bundle(bundle_dir: Path, password: str, out_zip: Path) -> None:
    """Write `out_zip` with every bundle file and the password filled in."""
    secret = _url_safe(password)
    with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(bundle_dir.rglob("*.yaml")):
            arcname = f"{EXPORT_ROOT}/{path.relative_to(bundle_dir).as_posix()}"
            content = path.read_text(encoding="utf-8").replace(PLACEHOLDER, secret)
            archive.writestr(arcname, content)


def _url_safe(password: str) -> str:
    """Percent-encode a password for use inside a SQLAlchemy URI."""
    return quote(password, safe="")


def main(argv: list[str]) -> int:
    """Render the bundle to the ZIP path given as the first argument."""
    if len(argv) != 2:
        print(f"usage: {Path(argv[0]).name} OUT_ZIP", file=sys.stderr)
        return 2
    render_bundle(BUNDLE_DIR, os.environ[CREDENTIAL_ENV], Path(argv[1]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
