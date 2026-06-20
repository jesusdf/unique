#!/usr/bin/env python3
# Copyright (C) 2026 Unique Contributors
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.

"""Build the self-contained web UI.

Inlines the vendored CodeMirror CSS/JS (under ``web/vendor/``) into the HTML
template (``web/src/index.template.html``) and writes the result to the served
location (``src/unique/api/static/index.html``). The output is fully
self-contained: it loads no external resources, which is required because the
app may be served behind a reverse proxy with no internet access.

Run it whenever the template or the vendored assets change::

    python web/build.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "web" / "src" / "index.template.html"
VENDOR = ROOT / "web" / "vendor"
OUTPUT = ROOT / "src" / "unique" / "api" / "static" / "index.html"

CSS_MARKER = "<!-- CODEMIRROR_CSS -->"
JS_MARKER = "<!-- CODEMIRROR_JS -->"


def build() -> None:
    template = TEMPLATE.read_text(encoding="utf-8")
    css = (VENDOR / "codemirror.min.css").read_text(encoding="utf-8")
    js = (VENDOR / "codemirror.min.js").read_text(encoding="utf-8")

    if CSS_MARKER not in template or JS_MARKER not in template:
        sys.exit(
            f"Template is missing injection markers "
            f"({CSS_MARKER!r} / {JS_MARKER!r})."
        )

    # Inline as <style> / <script> blocks so the page loads no external files.
    html = template.replace(CSS_MARKER, f"<style>\n{css}\n</style>")
    html = html.replace(JS_MARKER, f"<script>\n{js}\n</script>")

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(html, encoding="utf-8")

    kb = len(html.encode("utf-8")) / 1024
    print(f"Built {OUTPUT.relative_to(ROOT)} ({kb:.0f} KB, self-contained).")


if __name__ == "__main__":
    build()
