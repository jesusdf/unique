#!/usr/bin/env python3
# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Generate the ``docs/rationale/`` navigation indexes from the article pages.

The rationale tree is book/MSDN-style: one directory per topic, one file per
article (see ``scripts/migrate_rationale_split.py`` for how it was split). The
article/overview pages are the source of truth; this script derives from them:

- ``docs/rationale/<topic>/README.md`` — the topic index: one table per
  **type** (the article's ``## `` section on the pre-split page), columns
  ``Article | Direction | Description``. Prefaced by the topic's hand-written
  ``_intro.md`` partial.
- ``docs/rationale/README.md`` — the master index: a **by-topic** table
  (topic · what it covers · article count) and a **by-engine** index (for each
  of the four engines, the articles where it appears as source and as target).
  Prefaced/closed by the hand-written ``_index_intro.md`` / ``_index_appendix.md``
  partials.

Each page carries a machine-readable metadata comment written by the migration:

    <!-- rationale: topic=procedural type="Loop and cursor desugaring"
         direction="oracle → tsql" kind=article order=29 [direction-inferred=true] -->

``direction`` uses normalized engine tokens (``tsql``/``oracle``/``postgresql``/
``mysql``, ``all``, or ``cross-engine``) joined by ``/`` around a ``→``/``↔``
arrow, so the by-engine index can be computed mechanically. The **Description**
column is the first sentence of each page's ``**Problem.**`` paragraph (its
body's first sentence for overview pages, which have no Problem).

``--check`` regenerates into memory, diffs against the committed READMEs, and
runs a **link checker** over every relative link in ``docs/rationale/**.md``;
it prints every stale index and broken link and exits non-zero — the freshness
gate wired into CI next to ``generate_reference_docs.py --check``.

Stdlib only. Output ordering is deterministic (fixed topic order, type order by
first appearance, articles by ``order``), so a rerun with no content change
reproduces byte-identical files.

Usage::

    python scripts/generate_rationale_index.py           # (re)write the indexes
    python scripts/generate_rationale_index.py --check    # freshness + link gate
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_RATIONALE = _ROOT / "docs" / "rationale"
_GEN_CMD = "python scripts/generate_rationale_index.py"

#: Topic order + display title + "covers" blurb for the master by-topic table.
_TOPICS: tuple[tuple[str, str, str], ...] = (
    (
        "datetime",
        "Date/time arithmetic and formatting",
        "date/time arithmetic, truncation, unit maps, month-end semantics, "
        "epoch rebasing",
    ),
    (
        "strings-collation",
        "Strings, concatenation and collation",
        "concatenation & NULL, LIKE/ESCAPE, character classes, collation/order, "
        "Oracle `''` ≡ NULL, byte vs char lengths",
    ),
    (
        "aggregates-windows",
        "Aggregates and window functions",
        "window frames, ordered aggregates, string aggregation, DISTINCT ON, "
        "boolean aggregates",
    ),
    (
        "booleans",
        "Booleans: the value/predicate duality",
        "tri-state `CASE` wrap for value position, `<> 0` synthesis for predicate "
        "position, boolean-column `IS TRUE`/`IS FALSE` re-spelling",
    ),
    (
        "dml",
        "DML: PIVOT/UNPIVOT, MERGE, DELETE, row values",
        "PIVOT/UNPIVOT, MERGE/upsert lowering, multi-table DELETE, row caps, "
        "row-value comparisons",
    ),
    (
        "ddl",
        "DDL: identity, temp tables, foreign keys, sequences, storage options",
        "identity/SERIAL, temp tables, FK actions, sequences, storage options",
    ),
    (
        "procedural",
        "Procedural: cursors, dynamic SQL, system procedures, session directives",
        "cursors, error handling, dynamic SQL, system procedures, session directives",
    ),
)
_TOPIC_TITLE = {t: title for t, title, _ in _TOPICS}
_TOPIC_ORDER = [t for t, _, _ in _TOPICS]

_ENGINES: tuple[str, ...] = ("tsql", "oracle", "postgresql", "mysql")
_ENGINE_LABEL = {
    "tsql": "T-SQL",
    "oracle": "Oracle",
    "postgresql": "PostgreSQL",
    "mysql": "MySQL",
}

_META_RE = re.compile(
    r"<!--\s*rationale:\s*topic=(?P<topic>\S+)\s+"
    r'type="(?P<type>[^"]*)"\s+'
    r'direction="(?P<direction>[^"]*)"\s+'
    r"kind=(?P<kind>\S+)\s+"
    r"order=(?P<order>\d+)"
    r"(?P<inferred>\s+direction-inferred=true)?\s*-->"
)


@dataclass(frozen=True)
class Article:
    topic: str
    slug: str
    title: str
    type_name: str
    direction: str
    kind: str
    order: int
    description: str


# ---------------------------------------------------------------------------
# Parsing article pages.
# ---------------------------------------------------------------------------


def _first_sentence(text: str) -> str:
    """First sentence of *text* — up to a period that ends a sentence, guarding
    the common ``e.g.``/``i.e.`` abbreviations."""
    text = " ".join(text.split())
    for m in re.finditer(r"\.(?:\s|$)", text):
        head = text[: m.start()]
        last = head.rsplit(" ", 1)[-1].lower()
        if last in {"e.g", "i.e", "cf", "vs", "etc", "no"}:
            continue
        return head + "."
    return text


def _description(body: str) -> str:
    """Description column: first sentence of the ``**Problem.**`` paragraph, or
    of the first prose paragraph for overview pages (no Problem)."""
    m = re.search(r"\*\*Problem\.\*\*\s*(.+?)(?:\n\s*\n|\Z)", body, re.DOTALL)
    if m:
        return _first_sentence(m.group(1))
    # overview: first non-heading, non-blank paragraph
    for para in re.split(r"\n\s*\n", body):
        para = para.strip()
        if para and not para.startswith(("#", "|", ">", "```")):
            return _first_sentence(para)
    return ""


def load_articles() -> list[Article]:
    articles: list[Article] = []
    for topic in _TOPIC_ORDER:
        topic_dir = _RATIONALE / topic
        if not topic_dir.is_dir():
            continue
        for path in sorted(topic_dir.glob("*.md")):
            if path.name.startswith("_") or path.name == "README.md":
                continue
            text = path.read_text(encoding="utf-8")
            m = _META_RE.search(text)
            if not m:
                raise SystemExit(f"error: no rationale metadata in {path}")
            title_m = re.search(r"^# (.+)$", text, re.MULTILINE)
            if not title_m:
                raise SystemExit(f"error: no title in {path}")
            body = text[title_m.end() :]
            articles.append(
                Article(
                    topic=m.group("topic"),
                    slug=path.stem,
                    title=title_m.group(1).strip(),
                    type_name=m.group("type"),
                    direction=m.group("direction"),
                    kind=m.group("kind"),
                    order=int(m.group("order")),
                    description=_description(body),
                )
            )
    return articles


# ---------------------------------------------------------------------------
# Rendering helpers.
# ---------------------------------------------------------------------------


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ").strip()


def _table(headers: list[str], rows: list[tuple[str, ...]]) -> str:
    if not rows:
        return "_(none)_\n"
    out = [
        "| " + " | ".join(headers) + " |",
        "|" + "|".join(["---"] * len(headers)) + "|",
    ]
    for row in rows:
        out.append("| " + " | ".join(_cell(c) for c in row) + " |")
    return "\n".join(out) + "\n"


def _types_in_order(items: list[Article]) -> list[str]:
    seen: list[str] = []
    for a in sorted(items, key=lambda x: x.order):
        if a.type_name not in seen:
            seen.append(a.type_name)
    return seen


# ---------------------------------------------------------------------------
# Topic README.
# ---------------------------------------------------------------------------


def render_topic_readme(topic: str, articles: list[Article]) -> str:
    items = [a for a in articles if a.topic == topic]
    intro = (_RATIONALE / topic / "_intro.md").read_text(encoding="utf-8").strip("\n")
    parts = [
        "[← All rationale topics](../README.md)\n\n",
        f"# {_TOPIC_TITLE[topic]}\n\n",
        f"{intro}\n\n",
        "> **Generated file — do not edit by hand.** Produced by "
        f"`{_GEN_CMD}` from the article pages in this directory; the intro "
        "above comes from `_intro.md`. The CI freshness gate "
        f"(`{_GEN_CMD} --check`) fails the build if it drifts.\n\n",
    ]
    for type_name in _types_in_order(items):
        rows: list[tuple[str, ...]] = []
        for a in sorted(
            (x for x in items if x.type_name == type_name),
            key=lambda x: (x.kind != "overview", x.order),
        ):
            direction = "overview" if a.kind == "overview" else a.direction
            rows.append((f"[{a.title}]({a.slug}.md)", direction, a.description))
        parts.append(f"## {type_name}\n\n")
        parts.append(_table(["Article", "Direction", "Description"], rows))
        parts.append("\n")
    return "".join(parts).rstrip("\n") + "\n"


# ---------------------------------------------------------------------------
# Master README + by-engine index.
# ---------------------------------------------------------------------------


def _parse_direction(direction: str) -> tuple[set[str], set[str], bool]:
    """Return ``(sources, targets, is_cross)`` from a normalized direction."""
    if direction in ("cross-engine", "—", ""):
        return set(), set(), direction == "cross-engine"

    def expand(side: str) -> set[str]:
        side = side.strip()
        if side == "all":
            return set(_ENGINES)
        return {t for t in side.split("/") if t in _ENGINES}

    for arrow in (" ↔ ", " → "):
        if arrow in direction:
            left, right = direction.split(arrow, 1)
            ls, rs = expand(left), expand(right)
            if arrow.strip() == "↔":
                both = ls | rs
                return both, both, False
            return ls, rs, False
    # single bare token (e.g. "oracle", "mysql"): an engine-internal case
    return expand(direction), set(), False


def _by_engine_section(articles: list[Article]) -> str:
    real = [a for a in articles if a.kind == "article"]
    parsed = {a: _parse_direction(a.direction) for a in real}
    parts = ["## By engine\n\n"]
    parts.append(
        "Each article grouped by the engine it converts **from** and **to** "
        "(derived from the `direction` metadata). Cross-engine articles — no "
        "single source/target — are listed once at the end.\n\n"
    )

    def _slug(text: str) -> str:
        # GitHub heading anchor: lowercase; drop everything but word chars,
        # spaces and hyphens; spaces -> hyphens. (Repeated headings get -1,
        # -2, ... suffixes — handled by the dedup counter below.)
        kept = re.sub(r"[^\w\- ]", "", text.lower())
        return kept.replace(" ", "-")

    jump_rows = [
        (
            _ENGINE_LABEL[eng],
            f"[as source](#{_slug(_ENGINE_LABEL[eng] + ' as source')})",
            f"[as target](#{_slug(_ENGINE_LABEL[eng] + ' as target')})",
        )
        for eng in _ENGINES
    ]
    jump_rows.append(
        (
            "Cross-engine",
            f"[multi-directional](#{_slug('Cross-engine / multi-directional')})",
            "",
        )
    )
    parts.append(_table(["Engine", "As source", "As target"], jump_rows))
    parts.append("\n")

    # Pre-compute every section's per-topic groups IN EMISSION ORDER, assigning
    # each repeated `#### <topic>` heading its GitHub-deduplicated anchor
    # (`slug`, `slug-1`, `slug-2`, ...) so the per-section topic nav can link
    # to the right instance.
    ordered = sorted(real, key=lambda x: (x.topic, x.order))
    sections: list[tuple[str, list[tuple[str, str, list[tuple[str, str]]]]]] = []
    for eng in _ENGINES:
        for role, idx in (("as source", 0), ("as target", 1)):
            selected = [a for a in ordered if eng in parsed[a][idx]]
            sections.append((f"{_ENGINE_LABEL[eng]} {role}", _group(selected)))
    sections.append(
        (
            "Cross-engine / multi-directional",
            _group([a for a in ordered if parsed[a][2]]),
        )
    )

    slug_seen: dict[str, int] = {}

    def _dedup(slug: str) -> str:
        n = slug_seen.get(slug, 0)
        slug_seen[slug] = n + 1
        return slug if n == 0 else f"{slug}-{n}"

    # Engine/cross headings also occupy the anchor namespace, in order.
    resolved: list[tuple[str, list[tuple[str, str, str, list[tuple[str, str]]]]]] = []
    for heading, groups in sections:
        _dedup(_slug(heading))
        resolved.append(
            (
                heading,
                [
                    (topic, _dedup(_slug(_TOPIC_TITLE[topic])), label, rows)
                    for topic, label, rows in groups
                ],
            )
        )

    for heading, groups in resolved:
        parts.append(f"### {heading}\n\n")
        if len(groups) > 1:
            cells = [f"[{label}](#{anchor})" for _, anchor, label, _ in groups]
            parts.append("| " + " | ".join(cells) + " |\n")
            parts.append("|" + "|".join(["---"] * len(cells)) + "|\n\n")
        for topic, _anchor, _label, rows in groups:
            parts.append(f"#### [{_TOPIC_TITLE[topic]}]({topic}/README.md)\n\n")
            parts.append(_table(["Article", "Description"], rows))
            parts.append("\n")
    return "".join(parts)


#: Compact topic labels for the per-section jump tables.
_TOPIC_SHORT = {
    "datetime": "Date/time",
    "strings-collation": "Strings",
    "aggregates-windows": "Aggregates & windows",
    "booleans": "Booleans",
    "dml": "DML",
    "ddl": "DDL",
    "procedural": "Procedural",
}


def _group(selected: list[Article]) -> list[tuple[str, str, list[tuple[str, str]]]]:
    """Per-topic (topic, short label, table rows) groups, topic order."""
    groups = []
    for topic in _TOPIC_ORDER:
        rows = [
            (f"[{a.title}]({a.topic}/{a.slug}.md)", a.description)
            for a in selected
            if a.topic == topic
        ]
        if rows:
            groups.append((topic, _TOPIC_SHORT[topic], rows))
    return groups


def render_master_readme(articles: list[Article]) -> str:
    intro = (_RATIONALE / "_index_intro.md").read_text(encoding="utf-8").strip("\n")
    appendix = (
        (_RATIONALE / "_index_appendix.md").read_text(encoding="utf-8").strip("\n")
    )
    counts = {
        t: sum(1 for a in articles if a.topic == t and a.kind == "article")
        for t in _TOPIC_ORDER
    }
    topic_rows = [
        (f"[{title}]({topic}/README.md)", covers, str(counts[topic]))
        for topic, title, covers in _TOPICS
    ]
    parts = [
        "# Transpilation rationale\n\n",
        f"{intro}\n\n",
        "> **This index is generated — do not edit by hand.** Produced by "
        f"`{_GEN_CMD}` from the article pages under each topic directory. The "
        f"CI freshness gate (`{_GEN_CMD} --check`) fails the build if it "
        "drifts or if any relative link in `docs/rationale/**.md` goes "
        "stale. The intro above and the appendix below come from the "
        "`_index_intro.md` / `_index_appendix.md` partials.\n\n",
        "## Topics\n\n",
        _table(["Topic", "Covers", "Articles"], topic_rows),
        "\n",
        _by_engine_section(articles),
        f"{appendix}\n",
    ]
    return "".join(parts)


# ---------------------------------------------------------------------------
# Link checker.
# ---------------------------------------------------------------------------

_MD_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
_FENCE_RE = re.compile(r"^(```+|~~~+)")


def check_links() -> list[str]:
    """Every relative link in ``docs/rationale/**.md`` must resolve to a file
    that exists. Returns a list of ``"<file>: <target>"`` problems."""
    problems: list[str] = []
    for path in sorted(_RATIONALE.rglob("*.md")):
        in_fence = False
        fence_tok: str | None = None
        for line in path.read_text(encoding="utf-8").split("\n"):
            m = _FENCE_RE.match(line)
            if m:
                tok = m.group(1)[0] * 3
                if not in_fence:
                    in_fence, fence_tok = True, tok
                elif line.strip().startswith(fence_tok or ""):
                    in_fence, fence_tok = False, None
                continue
            if in_fence:
                continue
            for target in _MD_LINK_RE.findall(line):
                target = target.strip()
                if target.startswith(("http://", "https://", "mailto:", "#")):
                    continue
                base = target.split("#", 1)[0]
                if not base:
                    continue
                resolved = (path.parent / base).resolve()
                if not resolved.exists():
                    problems.append(f"{path.relative_to(_ROOT)}: {target}")
    return problems


# ---------------------------------------------------------------------------
# Orchestration.
# ---------------------------------------------------------------------------


def generate_all() -> dict[Path, str]:
    articles = load_articles()
    pages: dict[Path, str] = {}
    for topic in _TOPIC_ORDER:
        if (_RATIONALE / topic).is_dir():
            pages[_RATIONALE / topic / "README.md"] = render_topic_readme(
                topic, articles
            )
    pages[_RATIONALE / "README.md"] = render_master_readme(articles)
    return pages


def check() -> int:
    pages = generate_all()
    stale: list[str] = []
    for path, content in pages.items():
        rel = path.relative_to(_ROOT)
        if not path.exists():
            stale.append(f"missing: {rel}")
        elif path.read_text(encoding="utf-8") != content:
            stale.append(f"stale: {rel}")
    problems = check_links()
    for s in stale:
        print(s)
    for p in problems:
        print(f"broken link: {p}")
    if stale or problems:
        print(f"\n{len(stale)} stale index file(s), {len(problems)} broken link(s).")
        print(f"Run `{_GEN_CMD}` and fix any broken links, then commit.")
        return 1
    print(
        f"docs/rationale/ indexes up to date; all relative links resolve "
        f"({len(pages)} index files checked)."
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--check", action="store_true", help="freshness + link gate; no writes"
    )
    args = ap.parse_args(argv)
    if args.check:
        return check()
    pages = generate_all()
    for path, content in pages.items():
        path.write_text(content, encoding="utf-8")
    print(f"wrote {len(pages)} index file(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
