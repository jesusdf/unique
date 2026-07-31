#!/usr/bin/env python3
# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Private-corpus leak check (audit 2026-07-24 T2 / 09-fix-briefs.md B18).

CLAUDE.md and the development-workflow skill forbid real object names (table,
procedure, column, schema...) from the untracked ``fixtures-private/`` corpus
leaking into any committed file or commit message. This script is the
mechanical version of the manual sweep in ``audit/2026-07-24/07-confidentiality.md``
section 2: it derives a private-token inventory **at runtime** from whatever
is on disk under ``fixtures-private/`` and checks it against what is about to
be pushed.

**This script contains no private data itself** and is safe to commit: the
token inventory is built fresh on every run from local files that are
git-ignored. On a clone/CI runner without ``fixtures-private/`` present, the
check no-ops (exit 0, "private corpus absent") — public CI is unaffected.

Token derivation (mirrors the audit's methodology): every identifier-shaped
run of characters in the private files, case-folded, length >= 6, with SQL
keywords, this repo's own catalogued builtins (``src/unique/core/data/builtins/``)
and common English/Spanish dictionary words dropped — those would otherwise
false-positive on every ordinary line of SQL or prose. ``fixtures-private/
leak_fragments.txt`` (already exists, untracked) supplies extra short/compound
fragments the length-6 token filter would miss (checked as substrings, not
whole-token matches).

What gets scanned:
  (a) changed lines of ``git diff <base-ref>..HEAD`` (committed, about to be
      pushed) plus ``git diff HEAD`` (staged + working tree, not yet committed);
  (b) commit messages in ``git log <base-ref>..HEAD``.

Exits non-zero listing ``file:line: token`` (or ``<commit sha> line N: token``)
for every hit; exits 0 on a clean tree or an absent private corpus.

Usage::

    python scripts/private_leak_check.py
    python scripts/private_leak_check.py --base-ref origin/main
    python scripts/private_leak_check.py --private-dir /path/to/fixtures-private

Suggested pre-push hook (``.git/hooks/pre-push``, chmod +x)::

    #!/bin/sh
    exec python scripts/private_leak_check.py
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections.abc import Iterator, Sequence
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_PRIVATE_DIR = _ROOT / "fixtures-private"
_DEFAULT_BASE_REF = "origin/main"
_MIN_TOKEN_LEN = 6

_TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")
_NEW_FILE_RE = re.compile(r"^\+\+\+ b/(.+)$")

# SQL keywords/clause words + common English/Spanish dictionary words dropped
# from the derived private-token inventory (else "SELECT ... FROM ... WHERE"
# would trip the guard on every diff). Not exhaustive by design -- extend as
# false positives appear; this is a local pre-push habit, not a certification.
_CURATED_STOPWORDS: tuple[str, ...] = (
    # generic programming/tech identifiers that occur in embedded code or
    # comments of the private corpus but identify nothing (FP tail):
    "filename",
    "lineno",
    "nocheck",
    "nocount",
    "noexec",
    "nullable",
    "parent_object_id",
    "schemas",
    "updlock",
    "result_cursor",
    "returncode",
    "untranslated",
    "yyyymmdd",
    "column_name",
    "sqlserver",
    "params",
    "data_type",
    "datatype",
    "dataset",
    "sqlerrm",
    "sqlcode",
    "deallocate",
    "upsert",
    "upserts",
    "raiserror",
    "sqlstate",
    "rowlock",
    "nolock",
    "fetch_status",
    "identity_insert",
    "scope_identity",
    "datetime2",
    "datetimeoffset",
    "smalldatetime",
    "uniqueidentifier",
    "getdate",
    "sysdatetime",
    "binary_double",
    "binary_float",
    "pls_integer",
    # engine-standard vocabulary surfaced by the generated reference pages and
    # rationale docs (2026-07-30): builtin types/packages/keywords, never
    # client-identifying.
    "binary_integer",
    "bitwise",
    "cast_to_raw",
    "cast_to_varchar2",
    "column_value",
    "autonomous_transaction",
    "create_job",
    "dbms_scheduler",
    "dbms_session",
    "dbms_lob",
    "dbms_output",
    "endpoint",
    "maxvalue",
    "minvalue",
    "nocache",
    "nocycle",
    "noorder",
    "nvarchar2",
    "odcivarchar2list",
    "put_line",
    "raise_application_error",
    "rownum",
    "serveroutput",
    "sys_refcursor",
    "textimage_on",
    "time_zone",
    "tooltip",
    "traceability",
    "trancount",
    "utl_raw",
    "xmltype",
    "simple_integer",
    "timestamptz",
    "timestampltz",
    "mediumtext",
    "mediumint",
    "tinytext",
    "longtext",
    "longblob",
    "mediumblob",
    "tinyblob",
    "localhost",
    "timeout",
    "timeouts",
    "base64",
    "all_objects",
    "user_objects",
    "all_tables",
    "user_tables",
    "user_errors",
    "information_schema",
    "pg_catalog",
    # -- SQL / DDL / DML keywords and clause words --------------------------
    "select",
    "insert",
    "update",
    "delete",
    "create",
    "alter",
    "drop",
    "declare",
    "cursor",
    "procedure",
    "function",
    "package",
    "trigger",
    "exception",
    "return",
    "returns",
    "returning",
    "values",
    "column",
    "columns",
    "table",
    "tables",
    "index",
    "indexes",
    "constraint",
    "primary",
    "foreign",
    "references",
    "default",
    "unique",
    "check",
    "distinct",
    "union",
    "exists",
    "between",
    "escape",
    "collate",
    "cascade",
    "restrict",
    "sequence",
    "synonym",
    "schema",
    "database",
    "grant",
    "revoke",
    "commit",
    "rollback",
    "savepoint",
    "transaction",
    "isolation",
    "session",
    "global",
    "local",
    "temp",
    "temporary",
    "materialized",
    "refresh",
    "explain",
    "analyze",
    "vacuum",
    "partition",
    "lateral",
    "recursive",
    "having",
    "order",
    "group",
    "limit",
    "offset",
    "fetch",
    "cursor",
    "loop",
    "while",
    "exit",
    "continue",
    "raise",
    "execute",
    "immediate",
    "output",
    "merge",
    "matched",
    "target",
    "source",
    "using",
    "current",
    "number",
    "varchar",
    "varchar2",
    "integer",
    "boolean",
    "datetime",
    "timestamp",
    "nvarchar",
    "nchar",
    "numeric",
    "decimal",
    "smallint",
    "bigint",
    "tinyint",
    "float",
    "double",
    "binary",
    "varbinary",
    "boolean",
    "cascade",
    "deferred",
    "deferrable",
    "initially",
    "nowait",
    "skipped",
    "isnull",
    "coalesce",
    "concat",
    "convert",
    "extract",
    "substring",
    "trim",
    "upper",
    "lower",
    "replace",
    "length",
    "position",
    "overlay",
    "greatest",
    "least",
    "handler",
    "condition",
    "diagnostics",
    "signal",
    "resignal",
    "invoker",
    "definer",
    "security",
    "language",
    "volatile",
    "stable",
    "strict",
    "parallel",
    "enable",
    "disable",
    "validate",
    "novalidate",
    "identity",
    "generated",
    "always",
    "sequence",
    "rowtype",
    "rowcount",
    "notfound",
    "isopen",
    "bulk",
    "collect",
    "forall",
    "pragma",
    # -- generic engine/tech vocabulary (English) ---------------------------
    "example",
    "however",
    "because",
    "before",
    "during",
    "should",
    "result",
    "results",
    "string",
    "object",
    "objects",
    "method",
    "methods",
    "module",
    "modules",
    "record",
    "records",
    "detail",
    "details",
    "account",
    "accounts",
    "address",
    "addresses",
    "comment",
    "comments",
    "content",
    "contents",
    "handle",
    "handled",
    "handling",
    "process",
    "processed",
    "processing",
    "request",
    "requests",
    "response",
    "service",
    "services",
    "status",
    "statuses",
    "system",
    "systems",
    "version",
    "versions",
    "window",
    "windows",
    "value",
    "values",
    "public",
    "private",
    "internal",
    "external",
    "global",
    "config",
    "configs",
    "setting",
    "settings",
    "option",
    "options",
    "message",
    "messages",
    "parameter",
    "parameters",
    "variable",
    "variables",
    "argument",
    "arguments",
    "output",
    "input",
    "inputs",
    "before",
    "after",
    "during",
    "always",
    "never",
    "unless",
    "until",
    "please",
    "thanks",
    "thank",
    "regards",
    "cannot",
    "unable",
    "invalid",
    "missing",
    "expected",
    "actual",
    "current",
    "previous",
    "history",
    "summary",
    "overview",
    "example",
    "warning",
    "warnings",
    "notice",
    # -- generic vocabulary (Spanish) ----------------------------------------
    "usuario",
    "usuarios",
    "fecha",
    "fechas",
    "nombre",
    "nombres",
    "numero",
    "numeros",
    "codigo",
    "codigos",
    "estado",
    "estados",
    "tipo",
    "tipos",
    "datos",
    "registro",
    "registros",
    "configuracion",
    "descripcion",
    "direccion",
    "telefono",
    "correo",
    "pais",
    "ciudad",
    "empresa",
    "cliente",
    "clientes",
    "producto",
    "productos",
    "pedido",
    "pedidos",
    "factura",
    "facturas",
    "articulo",
    "articulos",
    "cantidad",
    "precio",
    "total",
    "detalle",
    "detalles",
    "historial",
    "periodo",
    "activo",
    "activos",
    "inactivo",
    "creado",
    "modificado",
    "actualizado",
    "eliminado",
    "vigente",
    "origen",
    "destino",
    "resultado",
    "mensaje",
    "parametro",
    "parametros",
    "valor",
    "valores",
    "campo",
    "campos",
    "tabla",
    "tablas",
    "consulta",
    "consultas",
    "procedimiento",
    "funcion",
    "paquete",
    "esquema",
    "llave",
    "indice",
    "restriccion",
    "transaccion",
    "sesion",
    "sistema",
    "version",
    "ventana",
    "usuarios",
    "informacion",
    "mediante",
    "siguiente",
    "anterior",
    "cuando",
    "donde",
    "porque",
    "tambien",
    "entonces",
)


def _load_builtin_names() -> frozenset[str]:
    """Case-folded names from this repo's own per-engine builtin catalogs.

    Reused rather than duplicated: they are the authoritative "is this a
    known engine function" source (``src/unique/core/builtins.py``).
    """
    names: set[str] = set()
    builtins_dir = _ROOT / "src" / "unique" / "core" / "data" / "builtins"
    if builtins_dir.is_dir():
        for path in sorted(builtins_dir.glob("*.txt")):
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    names.add(line.casefold())
    return frozenset(names)


#: System wordlists (the audit's sweep filtered English AND Spanish dictionary
#: words — the client corpus carries Spanish comments). Best-effort: absent
#: files are skipped, the curated list is the floor.
_SYSTEM_WORDLISTS = (
    Path("/usr/share/dict/american-english"),
    Path("/usr/share/dict/spanish"),
)


def _load_system_wordlists() -> frozenset[str]:
    words: set[str] = set()
    for path in _SYSTEM_WORDLISTS:
        if path.is_file():
            for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
                w = line.strip().casefold()
                if w.isalpha():
                    words.add(w)
    return frozenset(words)


def stopwords() -> frozenset[str]:
    """The full drop-set: curated keywords/dictionary words + real builtins."""
    return (
        frozenset(w.casefold() for w in _CURATED_STOPWORDS)
        | _load_builtin_names()
        | _load_system_wordlists()
    )


def _private_files(private_dir: Path) -> Iterator[Path]:
    if not private_dir.is_dir():
        return
    for path in sorted(private_dir.rglob("*")):
        if path.is_file() and path.name != "leak_fragments.txt":
            yield path


def build_token_set(
    private_dir: Path, drop: frozenset[str] | None = None
) -> frozenset[str]:
    """The private-token inventory: identifier-shaped runs, case-folded,
    length >= 6, minus ``drop`` (SQL keywords/builtins/dictionary words)."""
    drop = stopwords() if drop is None else drop
    tokens: set[str] = set()
    for path in _private_files(private_dir):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for match in _TOKEN_RE.finditer(text):
            tok = match.group(0).casefold()
            if len(tok) >= _MIN_TOKEN_LEN and tok not in drop:
                tokens.add(tok)
    return frozenset(tokens)


def build_fragment_list(private_dir: Path) -> tuple[str, ...]:
    """Extra case-folded substrings from ``leak_fragments.txt`` (one per
    line, ``#`` comments and blank lines skipped) — for short/compound
    identifiers the whole-token filter above would miss."""
    frag_path = private_dir / "leak_fragments.txt"
    if not frag_path.is_file():
        return ()
    fragments = []
    for line in frag_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            fragments.append(line.casefold())
    return tuple(fragments)


def find_hits(text: str, tokens: frozenset[str], fragments: Sequence[str]) -> list[str]:
    """Private tokens/fragments present in one line of text (order-preserving,
    duplicates allowed so multiple hits on one line are all reported)."""
    hits: list[str] = []
    for match in _TOKEN_RE.finditer(text):
        tok = match.group(0).casefold()
        if tok in tokens:
            hits.append(tok)
    if fragments:
        lower = text.casefold()
        for frag in fragments:
            if frag in lower:
                hits.append(frag)
    return hits


def iter_added_lines(diff_text: str) -> Iterator[tuple[str, int, str]]:
    """Yield ``(path, new_line_no, content)`` for every ``+`` line of a
    unified diff (unified git diff format; content excludes the leading
    ``+``). Context/removed lines are consumed to keep line numbers correct
    but not yielded."""
    path: str | None = None
    in_hunk = False
    lineno = 0
    for raw in diff_text.splitlines():
        if raw.startswith("diff --git ") or raw.startswith("index "):
            in_hunk = False
            continue
        new_file_match = _NEW_FILE_RE.match(raw)
        if new_file_match:
            path = new_file_match.group(1)
            in_hunk = False
            continue
        if raw.startswith("--- "):
            continue
        hunk_match = _HUNK_RE.match(raw)
        if hunk_match:
            lineno = int(hunk_match.group(1))
            in_hunk = True
            continue
        if not in_hunk or path is None:
            continue
        if raw.startswith("+"):
            yield path, lineno, raw[1:]
            lineno += 1
        elif raw.startswith("-"):
            continue  # removed line: doesn't exist in the new file
        else:
            lineno += 1  # context line


def _git(args: list[str], cwd: Path) -> tuple[int, str]:
    result = subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=False
    )
    return result.returncode, result.stdout


def get_diff_text(base_ref: str, root: Path) -> str:
    """``base_ref..HEAD`` (committed, about to be pushed) plus ``HEAD`` (staged
    + working tree, not yet committed). The former is best-effort: an
    unresolvable ``base_ref`` (e.g. no network to fetch a remote) warns and is
    skipped rather than aborting the whole check."""
    code, committed = _git(["diff", f"{base_ref}..HEAD"], root)
    if code != 0:
        print(
            f"private-leak-check: warning: 'git diff {base_ref}..HEAD' failed "
            "(unresolvable ref?) — skipping the committed-history check.",
            file=sys.stderr,
        )
        committed = ""
    _, working = _git(["diff", "HEAD"], root)
    return committed + working


def get_commit_messages(base_ref: str, root: Path) -> list[tuple[str, str]]:
    """``(short_sha, message)`` for every commit in ``base_ref..HEAD``."""
    code, out = _git(["log", f"{base_ref}..HEAD", "--format=%h%x1f%B%x1e"], root)
    if code != 0 or not out:
        return []
    messages = []
    for chunk in out.split("\x1e"):
        chunk = chunk.strip("\n")
        if not chunk:
            continue
        sha, _, body = chunk.partition("\x1f")
        messages.append((sha, body))
    return messages


def scan_repo(root: Path, private_dir: Path, base_ref: str) -> list[str]:
    """Every ``location: token`` hit across the diff and commit messages."""
    tokens = build_token_set(private_dir)
    fragments = build_fragment_list(private_dir)
    hits: list[str] = []

    for path, lineno, content in iter_added_lines(get_diff_text(base_ref, root)):
        for tok in find_hits(content, tokens, fragments):
            hits.append(f"{path}:{lineno}: {tok}")

    for sha, message in get_commit_messages(base_ref, root):
        for i, line in enumerate(message.splitlines(), start=1):
            for tok in find_hits(line, tokens, fragments):
                hits.append(f"<commit {sha}> line {i}: {tok}")

    return hits


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--private-dir",
        type=Path,
        default=_DEFAULT_PRIVATE_DIR,
        help="path to fixtures-private/ (default: repo-root/fixtures-private)",
    )
    parser.add_argument(
        "--base-ref",
        default=_DEFAULT_BASE_REF,
        help="ref to diff/log against (default: origin/main)",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=_ROOT,
        help="git repo root to run diff/log in (default: this repo)",
    )
    args = parser.parse_args(argv)

    if not args.private_dir.is_dir():
        print(
            "private-leak-check: private corpus absent "
            f"({args.private_dir} not found) — nothing to check."
        )
        return 0

    hits = scan_repo(args.root, args.private_dir, args.base_ref)
    if hits:
        print(f"private-leak-check: {len(hits)} possible leak(s):")
        for hit in hits:
            print(f"  {hit}")
        return 1

    print("private-leak-check: clean.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
