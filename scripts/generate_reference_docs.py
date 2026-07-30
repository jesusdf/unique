#!/usr/bin/env python3
# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Generate ``docs/reference/`` from the code (docs/TODO.md T8).

Three artifacts, all mechanically derived so they cannot drift from what the
transpiler actually does:

- ``mappings-<source>-<target>.md`` (12 pages, one per ordered engine pair) —
  the function/type rename tables and niladic-expression tables from
  ``src/unique/core/mappings.py``, plus the per-source "no cross-engine
  equivalent" gate list from ``unique.core.builtins._ENGINE_STANDARD``.
- ``limits.md`` — the degradation catalog: every ``-- CASE[limit]...:``
  header across ``tests/fixtures/challenge/challenge_*.sql``, parsed into one
  row per case (id, source engine, class, description, its
  ``docs/03-unsupported.md`` citation).
- ``coverage.md`` — per-source-engine and per-class corpus counts, reusing
  ``scripts/challenge_stats.py``'s own header parser (imported, not forked).

``--check`` regenerates into a temp directory and diffs it against
``docs/reference/``, printing every stale/missing/orphaned file and exiting
non-zero on drift — the freshness gate wired into CI
(``.github/workflows/ci.yaml``, next to the architecture-ratchet gate).

Stdlib only, plus ``unique``'s own modules and (by import, not by forking its
parsing) ``scripts/challenge_stats.py``. Output ordering is fully
deterministic (dialect tuple order, sorted dict keys, sorted file globs) and
carries no timestamps, so a rerun with no code change reproduces byte-identical
files.

Usage::

    python scripts/generate_reference_docs.py            # (re)write docs/reference/
    python scripts/generate_reference_docs.py --check     # freshness gate; no writes
"""

from __future__ import annotations

import argparse
import difflib
import filecmp
import importlib.util
import re
import sys
import tempfile
import textwrap
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from types import ModuleType

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "src"))

from unique.core import builtins as core_builtins  # noqa: E402
from unique.core import mappings  # noqa: E402

_OUT_DIR = _ROOT / "docs" / "reference"
_CHALLENGE_DIR = _ROOT / "tests" / "fixtures" / "challenge"
_UNSUPPORTED_DOC = "docs/03-unsupported.md"
_GEN_CMD = "python scripts/generate_reference_docs.py"

# ---------------------------------------------------------------------------
# Small rendering helpers shared by every page.
# ---------------------------------------------------------------------------


def _preamble(title: str, source_desc: str) -> str:
    """The generated-file banner every page opens with."""
    return (
        f"# {title}\n\n"
        f"> **Generated — do not edit by hand.** Produced by `{_GEN_CMD}` "
        f"from {source_desc}. The CI freshness gate "
        f"(`{_GEN_CMD} --check`) fails the build if this file drifts from "
        "the source data.\n\n"
    )


def _escape_cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def _wrap_cell(text: str, width: int = 100) -> str:
    """Wrap an overlong table-cell value across multiple visual lines using
    ``<br>`` (GitHub-flavored markdown renders this inside a table cell;
    markdown's own line breaks do not)."""
    text = _escape_cell(text)
    if len(text) <= width:
        return text
    return "<br>".join(textwrap.wrap(text, width=width))


def _table(headers: list[str], rows: Sequence[tuple[str, ...]]) -> str:
    if not rows:
        return "_(none)_\n"
    lines = [
        "| " + " | ".join(headers) + " |",
        "|" + "|".join(["---"] * len(headers)) + "|",
    ]
    for row in rows:
        lines.append("| " + " | ".join(_wrap_cell(str(c)) for c in row) + " |")
    return "\n".join(lines) + "\n"


def _name_list(names: frozenset[str]) -> str:
    """A wrapped, backtick-quoted, comma-separated list — used for the
    gate/degrade sets instead of a one-name-per-row table, which would dwarf
    the page for sets this size."""
    if not names:
        return "_(none)_\n"
    return textwrap.fill(", ".join(f"`{n}`" for n in sorted(names)), width=96) + "\n"


def _code_or_dash(value: str) -> str:
    return f"`{value}`" if value else "—"


# ---------------------------------------------------------------------------
# challenge_stats.py reuse (coverage.md + the limits.md header parser).
# ---------------------------------------------------------------------------


@cache
def _load_challenge_stats() -> ModuleType:
    """Import ``scripts/challenge_stats.py`` by path so its header parser is
    reused rather than forked (T8 requirement). Mirrors
    ``tests/unit/test_challenge_stats.py``'s own loading idiom, including
    registering the module in ``sys.modules`` *before* exec — its
    ``@dataclass`` uses ``from __future__ import annotations`` (PEP 563),
    which resolves string-form annotations via ``sys.modules[cls.__module__]``
    at class-definition time. Cached: this module is imported by every
    per-file parse call, and a file-backed import is not free.
    """
    path = _ROOT / "scripts" / "challenge_stats.py"
    spec = importlib.util.spec_from_file_location("challenge_stats", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["challenge_stats"] = module
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# mappings-<source>-<target>.md
# ---------------------------------------------------------------------------

#: (label, {dialect: niladic-expression}) pairs rendered as one shared table
#: per pair page — every single-dialect-keyed table in mappings.py that
#: represents "the same construct, spelled per engine".
_NILADIC_TABLES: list[tuple[str, dict[str, str]]] = [
    ("`CURRENT_TIMESTAMP`", mappings.CURRENT_TIMESTAMP_EXPR),
    ("`CURRENT_DATE`", mappings.CURRENT_DATE_EXPR),
    ("UUID generator", mappings.UUID_FUNCTION),
    ("Last identity value", mappings.LAST_IDENTITY_EXPR),
    ("DML-affected-rows predicate", mappings.DML_FOUND_EXPR),
    ("Current error message", mappings.ERROR_MESSAGE_EXPR),
]


def _function_table(source: str, target: str) -> str:
    mapping = mappings.PROCEDURAL_FUNC_MAPS.get((source, target), {})
    if not mapping:
        return "_No procedural function renames recorded for this pair._\n"
    rows = []
    for src_fn in sorted(mapping):
        tgt = mapping[src_fn]
        if tgt.startswith("--"):
            rows.append(
                (f"`{src_fn}`", "_manual conversion needed_", tgt.lstrip("- ").strip())
            )
        else:
            rows.append((f"`{src_fn}`", f"`{tgt}`", "—"))
    return _table(["Source function", "Target form", "Note"], rows)


def _type_table(source: str, target: str) -> str:
    mapping = mappings.PROCEDURAL_TYPE_MAPS.get((source, target), {})
    if not mapping:
        return "_No procedural type renames recorded for this pair._\n"
    rows = [(f"`{k}`", f"`{mapping[k]}`") for k in sorted(mapping)]
    return _table(["Source type", "Target type"], rows)


def _emit_type_table(target: str) -> str:
    mapping = mappings.EMIT_TYPE_MAP.get(target, {})
    if not mapping:
        return "_No DML-pipeline type renames recorded for this target._\n"
    rows = [(f"`{k}`", f"`{mapping[k]}`") for k in sorted(mapping)]
    return _table(["Non-portable source type name", f"{target} emission"], rows)


def _bare_char_table(target: str) -> str:
    mapping = mappings.BARE_CHAR_BIGTEXT.get(target, {})
    if not mapping:
        return ""
    rows = [(f"`{k}`", f"`{mapping[k]}`") for k in sorted(mapping)]
    return _table(["Bare (length-less) type", f"{target} large-text type"], rows)


def _niladic_table(source: str, target: str) -> str:
    rows = []
    for label, table in _NILADIC_TABLES:
        rows.append(
            (
                label,
                _code_or_dash(table.get(source, "")),
                _code_or_dash(table.get(target, "")),
            )
        )
    for name, per_dialect in mappings.ERROR_DIAGNOSTIC_EXPRS.items():
        rows.append(
            (
                f"Diagnostic global `{name}`",
                _code_or_dash(per_dialect.get(source, "")),
                _code_or_dash(per_dialect.get(target, "")),
            )
        )
    return _table(["Construct", f"{source} form", f"{target} form"], rows)


def _date_format_style_table() -> str:
    rows = [(f"`{k}`", str(v)) for k, v in mappings.ORACLE_DATE_FORMAT_STYLES.items()]
    return _table(["Oracle format", "T-SQL CONVERT style"], rows)


def _degrade_section(source: str) -> str:
    names = core_builtins._ENGINE_STANDARD.get(source, frozenset())  # noqa: SLF001
    if not names:
        return (
            "_No engine-exclusive built-ins with zero cross-engine equivalent "
            f"are catalogued for {source}._\n"
        )
    return (
        f"Built-in functions of {source} that the catalog "
        "(`unique.core.builtins._ENGINE_STANDARD`) records as having **no "
        f"cross-engine equivalent on any target** — a call to one of these "
        f"degrades to a documented carrier + warning wherever it lands off "
        f"{source}:\n\n"
        f"{_name_list(names)}"
    )


def _tsql_foreign_gate_section() -> str:
    return (
        "Built-in functions of the other three engines with **no name-level "
        "mapping onto T-SQL** (`core/mappings.py:FOREIGN_BUILTIN_FUNCTIONS`). "
        "If one of these reaches T-SQL output unqualified, the transpiler must "
        "not silently qualify it as a phantom `dbo.<name>` user function — it "
        "is a visible mapping gap:\n\n"
        f"{_name_list(mappings.FOREIGN_BUILTIN_FUNCTIONS)}"
    )


def _render_mapping_page(source: str, target: str) -> str:
    parts = [
        _preamble(
            f"{source} → {target}: function & type mappings",
            "`src/unique/core/mappings.py`",
        )
    ]
    parts.append(
        "Both pipelines share this data (audit doc 03): the procedural "
        "pipeline rewrites raw routine text using the pair-keyed tables "
        "below; the DML pipeline converts through sqlglot's canonical names, "
        "so its type table is keyed by target only. See "
        "[SKILL-development-workflow.md](../../skills/SKILL-development-workflow.md) "
        '· "Dual-pipeline symmetry rule".\n\n'
    )
    parts.append("## Procedural function renames\n\n")
    parts.append(_function_table(source, target))
    parts.append("\n## Procedural type renames\n\n")
    parts.append(_type_table(source, target))
    bare = _bare_char_table(target)
    if bare:
        parts.append(f"\n## Bare-length character types (target: {target})\n\n")
        parts.append(bare)
    parts.append(f"\n## DML-pipeline type emission (target: {target})\n\n")
    parts.append(_emit_type_table(target))
    parts.append("\n## Niladic / builtin expressions\n\n")
    parts.append(_niladic_table(source, target))
    if source == "oracle" and target == "tsql":
        parts.append("\n## Oracle date-format → T-SQL `CONVERT` style\n\n")
        parts.append(_date_format_style_table())
    if target == "oracle":
        parts.append(
            "\n> Month/quarter/year `DATEADD` targeting Oracle uses a "
            "day-preserving rewrite (`oracle_month_add_daypreserving` in "
            "`core/mappings.py`) rather than a bare `ADD_MONTHS` call; see "
            "[docs/rationale/datetime.md](../rationale/datetime.md) for the "
            "worked example.\n"
        )
    parts.append(f"\n## Built-ins of {source} with no cross-engine equivalent\n\n")
    parts.append(_degrade_section(source))
    if target == "tsql":
        parts.append("\n## Foreign builtins gated on T-SQL output\n\n")
        parts.append(_tsql_foreign_gate_section())
    return "".join(parts)


def build_mapping_pages() -> dict[str, str]:
    pages = {}
    for source in mappings.DIALECTS:
        for target in mappings.DIALECTS:
            if source == target:
                continue
            pages[f"mappings-{source}-{target}.md"] = _render_mapping_page(
                source, target
            )
    return pages


# ---------------------------------------------------------------------------
# limits.md — the [limit] degradation catalog.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LimitRow:
    """One ``[limit]`` corpus case.

    ``code`` is reserved for the future stable ``UNIQUE-NNNN`` identifier
    (brief B32, docs/TODO.md); it is placed last, defaults to empty, and is
    the only field a future generator revision needs to populate — the row
    model does not need to change shape when that registry lands.
    """

    case_id: str
    source: str
    klass: str
    description: str
    citation: str
    code: str = ""


_CITATION_RE = re.compile(
    r"docs/03-unsupported\.md(?:\s*(?:§|[Ss]ection)?\s*(\d+(?:\.\d+)?[a-z]?))?"
)
_CASE_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*")


def _split_case_id(desc: str) -> tuple[str, str]:
    """Split ``"pg-accent-eq — fails on mysql. ..."`` into
    ``("pg-accent-eq", "fails on mysql. ...")``. Cases whose description does
    not start with a recognizable ``<id> — `` prefix keep an empty id and
    the description verbatim."""
    parts = desc.split(" — ", 1)
    if len(parts) == 2 and _CASE_ID_RE.fullmatch(parts[0]):
        return parts[0], parts[1]
    return "", desc


def _citation(desc: str) -> str:
    match = _CITATION_RE.search(desc)
    if match is None:
        return ""
    section = match.group(1)
    return _UNSUPPORTED_DOC + (f" §{section}" if section else "")


def parse_limit_catalog(text: str, source: str) -> list[LimitRow]:
    """Parse every ``-- CASE[limit]...:`` header out of *text* (one challenge
    fixture file's contents) into :class:`LimitRow`.

    Reuses ``challenge_stats.parse_header_line`` for the header syntax itself
    (status/class/description extraction) — only the id/citation split below,
    specific to the limit catalog, is added here.
    """
    cs = _load_challenge_stats()
    rows: list[LimitRow] = []
    for line in text.splitlines():
        header = cs.parse_header_line(line, source=source)
        if header is None or header.status != "limit":
            continue
        case_id, rest = _split_case_id(header.desc)
        rows.append(
            LimitRow(
                case_id=case_id,
                source=source,
                klass=header.klass,
                description=rest,
                citation=_citation(header.desc),
            )
        )
    return rows


def build_limits_catalog() -> list[LimitRow]:
    cs = _load_challenge_stats()
    rows: list[LimitRow] = []
    for path in sorted(_CHALLENGE_DIR.glob("challenge_*.sql")):
        source = cs.source_from_filename(path)
        rows.extend(parse_limit_catalog(path.read_text(encoding="utf-8"), source))
    rows.sort(key=lambda r: (r.source, r.case_id))
    return rows


def _citation_cell(citation: str) -> str:
    if not citation:
        return "—"
    label = citation.replace("docs/03-unsupported.md", "03-unsupported.md")
    return f"[{label}](../03-unsupported.md)"


def render_limits_page(rows: list[LimitRow]) -> str:
    parts = [
        _preamble(
            "Degradation catalog ([limit] cases)",
            "every `-- CASE[limit]...:` header in "
            "`tests/fixtures/challenge/challenge_*.sql`",
        )
    ]
    parts.append(
        "Each row is an approved, documented divergence: a construct the "
        "transpiler cannot render faithfully off the listed source engine, "
        "already live-verified and citing its "
        "[docs/03-unsupported.md](../03-unsupported.md) entry. A future "
        "stable per-case code (`UNIQUE-NNNN`, brief B32) will slot in as an "
        "additional column once that registry lands.\n\n"
    )
    headers = ["Case ID", "Source", "Class", "Description", "03-unsupported"]
    table_rows = [
        (
            f"`{r.case_id}`" if r.case_id else "_(untitled)_",
            r.source,
            f"`{r.klass}`" if r.klass != cs_unclassified() else "—",
            r.description,
            _citation_cell(r.citation),
        )
        for r in rows
    ]
    parts.append(_table(headers, table_rows))
    n_sources = len({r.source for r in rows})
    parts.append(
        f"\n{len(rows)} `[limit]` cases across {n_sources} source engine(s).\n"
    )
    return "".join(parts)


def cs_unclassified() -> str:
    """``challenge_stats.UNCLASSIFIED`` — the "no [class=...] tag" sentinel."""
    return str(_load_challenge_stats().UNCLASSIFIED)


# ---------------------------------------------------------------------------
# coverage.md
# ---------------------------------------------------------------------------


def render_coverage_page() -> str:
    cs = _load_challenge_stats()
    headers_ = cs.parse_corpus(_CHALLENGE_DIR)
    parts = [
        _preamble(
            "Challenge-corpus coverage",
            "`tests/fixtures/challenge/challenge_*.sql`, parsed by "
            "`scripts/challenge_stats.py`",
        )
    ]
    parts.append(
        "Per-source-engine counts of the challenge corpus's "
        '`-- CASE[status][class=...]:` headers. "Direction" here is the '
        "case's tagged source engine — the corpus's only structured axis; "
        "each fixture file (`challenge_<source>.sql`) holds every case found "
        "starting from that source dialect, against all applicable targets.\n\n"
    )
    sources = sorted({h.source for h in headers_})
    statuses = sorted({h.status for h in headers_})
    rows = []
    for source in sources:
        counts = Counter(h.status for h in headers_ if h.source == source)
        row = [
            source,
            *(str(counts.get(s, 0)) for s in statuses),
            str(sum(counts.values())),
        ]
        rows.append(tuple(row))
    all_counts = Counter(h.status for h in headers_)
    total_row = [
        "**all**",
        *(str(all_counts.get(s, 0)) for s in statuses),
        str(len(headers_)),
    ]
    rows.append(tuple(total_row))
    parts.append(_table(["Source", *statuses, "total"], rows))

    parts.append("\n## By finding class\n\n")
    class_counts = Counter(h.klass for h in headers_)
    class_rows = [(k, str(class_counts[k])) for k in sorted(class_counts)]
    parts.append(_table(["Class", "count"], class_rows))
    return "".join(parts)


# ---------------------------------------------------------------------------
# Orchestration: generate, write, --check.
# ---------------------------------------------------------------------------


def generate_all() -> dict[str, str]:
    pages = build_mapping_pages()
    pages["limits.md"] = render_limits_page(build_limits_catalog())
    pages["coverage.md"] = render_coverage_page()
    return pages


def write_pages(pages: dict[str, str], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, content in pages.items():
        (out_dir / name).write_text(content, encoding="utf-8")


def check(out_dir: Path) -> int:
    pages = generate_all()
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        write_pages(pages, tmp_dir)

        expected_names = set(pages)
        existing_names = (
            {p.name for p in out_dir.glob("*.md")} if out_dir.exists() else set()
        )
        stale: list[str] = []
        for name in sorted(expected_names | existing_names):
            new_path = tmp_dir / name
            old_path = out_dir / name
            rel = (
                out_dir.relative_to(_ROOT) / name
                if out_dir.is_relative_to(_ROOT)
                else Path(name)
            )
            if not old_path.exists():
                stale.append(name)
                print(f"missing: {rel} (would be generated)")
                continue
            if not new_path.exists():
                stale.append(name)
                print(f"orphaned: {rel} (no longer generated)")
                continue
            if not filecmp.cmp(old_path, new_path, shallow=False):
                stale.append(name)
                print(f"stale: {rel}")
                diff = difflib.unified_diff(
                    old_path.read_text(encoding="utf-8").splitlines(keepends=True),
                    new_path.read_text(encoding="utf-8").splitlines(keepends=True),
                    fromfile=f"{rel} (committed)",
                    tofile=f"{rel} (regenerated)",
                )
                sys.stdout.writelines(list(diff)[:40])

        if stale:
            print(f"\n{len(stale)} file(s) out of date.")
            print(f"Run `{_GEN_CMD}` and commit the result.")
            return 1
        shown_dir = (
            out_dir.relative_to(_ROOT) if out_dir.is_relative_to(_ROOT) else out_dir
        )
        print(f"{shown_dir} is up to date.")
        return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify docs/reference/ matches the generated output; do not write",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=_OUT_DIR,
        help="output directory (default: docs/reference)",
    )
    args = parser.parse_args(argv)

    if args.check:
        return check(args.out_dir)

    pages = generate_all()
    write_pages(pages, args.out_dir)
    print(f"wrote {len(pages)} page(s) to {args.out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
