#!/usr/bin/env python3
# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""One-shot migration: split the flat ``docs/rationale/*.md`` pages into a
book/MSDN-style tree — one directory per topic, one file per article.

**This script is a documented one-shot.** It was run once to perform the
2026-07-31 navigation restructure and is kept in the tree as the executable
record of exactly how the split was done (and so it can be re-run to
regenerate the article tree byte-for-byte from the pre-split pages, should
those ever be restored from git history). It is *not* part of the CI gate and
is not re-run in normal development — the generated topic/master indexes are
kept fresh by ``scripts/generate_rationale_index.py`` instead.

What it does, per source page (e.g. ``procedural.md``):

1. Rewrites every intra-repo relative link so it still resolves from the new,
   one-level-deeper location ``docs/rationale/<topic>/`` (``../`` → ``../../``,
   a sibling ``README.md`` → the master ``../README.md``, a sibling
   ``<page>.md`` → that topic's ``../<page>/README.md``). Fence-aware: bytes
   inside ``` fences are never touched.
2. Parses the (link-rewritten) page into blocks at fence-aware headings:
   the ``# Title`` block (title + page intro), each ``## Section`` block
   (section header + optional section intro), and each ``### Article`` block.
3. Writes, under ``docs/rationale/<topic>/``:
   - ``_intro.md`` — the page-intro prose (partial included verbatim by the
     index generator into the topic ``README.md``);
   - one ``<slug>.md`` per ``### `` article (its ``### `` title becomes the
     page ``# `` title, body verbatim);
   - one overview page per ``## `` section that carries an intro paragraph
     (the intro becomes that type's landing page) and per prose-only ``## ``
     section (a section with prose but no ``### `` children).
   Every article/overview page opens with a breadcrumb nav line and a
   machine-readable ``<!-- rationale: ... -->`` metadata comment.
4. Replaces the old flat page with a 3-line stub pointing at the new topic
   index (stubs, not deletes, because the public GitHub repo may be
   deep-linked at the old ``docs/rationale/<page>.md`` URLs).

**Content preservation is asserted, not assumed.** For every page the script
(a) proves the link rewrite touched *only* link targets (blanking every
``](...)`` target in the original and in the rewritten text leaves them
identical) and (b) reconstructs the page's full link-rewritten text back out
of the files it is about to write and asserts it is byte-for-byte identical.
Any mismatch aborts with a diff before anything is written.

Usage::

    python scripts/migrate_rationale_split.py            # perform the split
    python scripts/migrate_rationale_split.py --dry-run   # verify only, no writes
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_RATIONALE = _ROOT / "docs" / "rationale"

#: Source pages, in the order they appear in the old master index.
_TOPICS: tuple[str, ...] = (
    "datetime",
    "strings-collation",
    "aggregates-windows",
    "booleans",
    "dml",
    "ddl",
    "procedural",
)

#: The seven topic basenames — a same-dir ``<page>.md`` link points at one of
#: these and is rewritten to that topic's index.
_TOPIC_SET = frozenset(f"{t}.md" for t in _TOPICS)

_ENGINE_TITLE: dict[str, str] = {
    "datetime": "Date/time arithmetic and formatting",
    "strings-collation": "Strings, concatenation and collation",
    "aggregates-windows": "Aggregates and window functions",
    "booleans": "Booleans: the value/predicate duality",
    "dml": "DML: PIVOT/UNPIVOT, MERGE, DELETE, row values",
    "ddl": "DDL: identity, temp tables, foreign keys, sequences, storage options",
    "procedural": "Procedural: cursors, dynamic SQL, system procedures, session directives",
}

# ---------------------------------------------------------------------------
# Type assignment for the two flat pages (no ``## `` sections of their own).
# ---------------------------------------------------------------------------

_FLAT_TYPES: dict[str, str] = {
    # datetime.md
    "DATEADD(MONTH) (T-SQL/MySQL/PostgreSQL) → Oracle ADD_MONTHS": "Month arithmetic and month-end semantics",
    "ADD_MONTHS (Oracle) → DATEADD/DATE_ADD/interval-add (T-SQL/MySQL/PostgreSQL)": "Month arithmetic and month-end semantics",
    "PostgreSQL date_trunc → Oracle TRUNC format codes and T-SQL ISO week": "Truncation and unit maps",
    "Temporal +/− arithmetic: date ± int, MySQL numeric coercion, timestamp − timestamp": "Interval and temporal arithmetic",
    "MySQL TIMESTAMPDIFF complete-month adjustment, ported to every target": "Month arithmetic and month-end semantics",
    "MySQL TO_DAYS year-0000 epoch rebase": "Epoch rebasing",
    "Multi-field PostgreSQL INTERVAL decomposition": "Interval and temporal arithmetic",
    "DATEDIFF/DATEPART unit maps: the QUARTER crash and WEEKDAY per-target forms": "Truncation and unit maps",
    # strings-collation.md
    "CONCAT / `||` NULL-propagation per engine": "Concatenation",
    "`GREATEST`/`LEAST` NULL-propagation per engine": "NULL and empty-string semantics",
    "`REPLACE` and `NULL`: Oracle's 2-arg form vs MySQL's propagation": "NULL and empty-string semantics",
    "Oracle `'' ≡ NULL`": "NULL and empty-string semantics",
    "LIKE … ESCAPE mapping": "LIKE and pattern matching",
    "T-SQL LIKE character classes (`'[A-C]%'`) → SIMILAR TO / REGEXP / REGEXP_LIKE": "LIKE and pattern matching",
    "Negative/zero REPEAT/REPLICATE clamps": "Repeat, substring and splice",
    "SUBSTRING negative/zero start semantics per engine": "Repeat, substring and splice",
    "Character-set `TRIM(chars FROM string)` → Oracle": "Trimming",
    "Positional string-splice: `OVERLAY`/`STUFF`/`INSERT` (PostgreSQL/T-SQL/MySQL) → all targets": "Repeat, substring and splice",
    "DATALENGTH byte-vs-char lengths (UTF-16 caveat)": "Length and encoding",
    "SOUNDEX as the canonical unmapped-builtin gate example": "Unmapped built-ins",
    "Collation and ordering divergences — documented limits": "Collation and ordering",
}

# ---------------------------------------------------------------------------
# Direction overrides for titles with no ``→``/``↔`` arrow (inferred from the
# article body). Normalized-token form, read by the generator's by-engine index.
# ---------------------------------------------------------------------------

_DIRECTION_OVERRIDE: dict[str, str] = {
    "Temporal +/− arithmetic: date ± int, MySQL numeric coercion, timestamp − timestamp": "cross-engine",
    "MySQL TIMESTAMPDIFF complete-month adjustment, ported to every target": "mysql → all",
    "MySQL TO_DAYS year-0000 epoch rebase": "mysql → all",
    "Multi-field PostgreSQL INTERVAL decomposition": "postgresql → all",
    "DATEDIFF/DATEPART unit maps: the QUARTER crash and WEEKDAY per-target forms": "cross-engine",
    "CONCAT / `||` NULL-propagation per engine": "cross-engine",
    "`GREATEST`/`LEAST` NULL-propagation per engine": "cross-engine",
    "`REPLACE` and `NULL`: Oracle's 2-arg form vs MySQL's propagation": "cross-engine",
    "Oracle `'' ≡ NULL`": "oracle → all",
    "LIKE … ESCAPE mapping": "cross-engine",
    "Negative/zero REPEAT/REPLICATE clamps": "cross-engine",
    "SUBSTRING negative/zero start semantics per engine": "cross-engine",
    "DATALENGTH byte-vs-char lengths (UTF-16 caveat)": "cross-engine",
    "SOUNDEX as the canonical unmapped-builtin gate example": "cross-engine",
    "Collation and ordering divergences — documented limits": "cross-engine",
    "Integer-truncating vs. decimal division (cross-engine)": "cross-engine",
    "Oracle PL/SQL `BOOLEAN` variables and parameters keep native `NOT` (handled)": "oracle",
    "`FROM DUAL` synthesis and removal (bidirectional)": "oracle ↔ all",
    "Parenthesized set-operation arms unwrap; an arm's own `ORDER BY`/`LIMIT` is shielded": "cross-engine",
    "Parenthesized join-relation groups unwrap; a column-aliased table ref wraps into a derived table": "cross-engine",
    "Auto-incrementing key columns (PostgreSQL `SERIAL` / T-SQL `IDENTITY` / Oracle `GENERATED … AS IDENTITY` / MySQL `AUTO_INCREMENT`)": "cross-engine",
    "One-word vs two-word negative options (Oracle `NOMAXVALUE`/`NOCYCLE` vs T-SQL/PostgreSQL `NO MAXVALUE`/`NO CYCLE`)": "oracle ↔ tsql/postgresql",
    "Statement-after-`EXEC` survival fix": "tsql → all",
    "Leading `DECLARE` block reordered (MySQL): variables before cursors": "mysql",
}

#: Slug overrides for ``### `` article titles (short, readable, collision-free).
_SLUG_OVERRIDE: dict[str, str] = {
    "DATEADD(MONTH) (T-SQL/MySQL/PostgreSQL) → Oracle ADD_MONTHS": "dateadd-month-to-oracle-add-months",
    "ADD_MONTHS (Oracle) → DATEADD/DATE_ADD/interval-add (T-SQL/MySQL/PostgreSQL)": "oracle-add-months-to-dateadd",
    "PostgreSQL date_trunc → Oracle TRUNC format codes and T-SQL ISO week": "date-trunc-to-oracle-trunc",
    "Temporal +/− arithmetic: date ± int, MySQL numeric coercion, timestamp − timestamp": "temporal-plus-minus-arithmetic",
    "MySQL TIMESTAMPDIFF complete-month adjustment, ported to every target": "mysql-timestampdiff-complete-month",
    "MySQL TO_DAYS year-0000 epoch rebase": "mysql-to-days-epoch-rebase",
    "Multi-field PostgreSQL INTERVAL decomposition": "postgresql-interval-decomposition",
    "DATEDIFF/DATEPART unit maps: the QUARTER crash and WEEKDAY per-target forms": "datediff-datepart-unit-maps",
    "CONCAT / `||` NULL-propagation per engine": "concat-null-propagation",
    "`GREATEST`/`LEAST` NULL-propagation per engine": "greatest-least-null-propagation",
    "`REPLACE` and `NULL`: Oracle's 2-arg form vs MySQL's propagation": "replace-and-null",
    "Oracle `'' ≡ NULL`": "oracle-empty-string-is-null",
    "LIKE … ESCAPE mapping": "like-escape-mapping",
    "T-SQL LIKE character classes (`'[A-C]%'`) → SIMILAR TO / REGEXP / REGEXP_LIKE": "tsql-like-character-classes",
    "Negative/zero REPEAT/REPLICATE clamps": "repeat-replicate-clamps",
    "SUBSTRING negative/zero start semantics per engine": "substring-negative-start",
    "Character-set `TRIM(chars FROM string)` → Oracle": "trim-chars-from-string-to-oracle",
    "Positional string-splice: `OVERLAY`/`STUFF`/`INSERT` (PostgreSQL/T-SQL/MySQL) → all targets": "overlay-stuff-insert-splice",
    "DATALENGTH byte-vs-char lengths (UTF-16 caveat)": "datalength-byte-vs-char",
    "SOUNDEX as the canonical unmapped-builtin gate example": "soundex-unmapped-builtin-gate",
    "Collation and ordering divergences — documented limits": "collation-and-ordering-limits",
    "`GROUPS` window frame (PostgreSQL / Oracle) → T-SQL / MySQL": "groups-window-frame",
    "Oracle `KEEP (DENSE_RANK FIRST/LAST …)` → PostgreSQL / T-SQL / MySQL": "oracle-keep-dense-rank",
    "`agg(x) FILTER (WHERE p)` clause (PostgreSQL) → T-SQL / MySQL / Oracle": "filter-clause",
    "`bool_or`/`bool_and` value wrapping (PostgreSQL) → T-SQL / Oracle": "bool-or-and-value-wrapping",
    "`bool_or(...) FILTER (WHERE …)` composition (PostgreSQL) → T-SQL / Oracle": "bool-or-filter-composition",
    "`DISTINCT` + numeric `ORDER BY` restructure (MySQL) → PostgreSQL": "distinct-numeric-order-by",
    "`CAST` folding for `LISTAGG`/`STRING_AGG` value arguments (PostgreSQL) → Oracle / T-SQL": "cast-folding-listagg-string-agg",
    "`ANY_VALUE` (MySQL / PostgreSQL 16+) → T-SQL": "any-value-to-tsql",
    "Oracle `LISTAGG(...) WITHIN GROUP (...) OVER (...)` → PostgreSQL / T-SQL / MySQL": "oracle-listagg-over",
    "PostgreSQL `DISTINCT ON (a)` → T-SQL / MySQL / Oracle": "distinct-on",
    "Integer-truncating vs. decimal division (cross-engine)": "integer-vs-decimal-division",
    "`CAST(... AS <integer type>)` rounding vs. truncation trade (PostgreSQL / MySQL) → T-SQL": "cast-to-integer-rounding",
    "`MOD`/`%` by a zero divisor (MySQL) → PostgreSQL / T-SQL / Oracle": "mod-by-zero-divisor",
    "Comparisons, `AND`/`OR`, `IS [NOT] NULL`, `EXISTS` in a SELECT-list value position (MySQL, PostgreSQL) → T-SQL, Oracle": "predicate-in-value-position",
    "`NOT` of a truthy variable, assignment, or function `RETURN` (MySQL, PostgreSQL) → T-SQL, Oracle": "not-of-truthy-value",
    "Oracle PL/SQL `BOOLEAN` variables and parameters keep native `NOT` (handled)": "oracle-plsql-native-boolean",
    "A numeric/bit value where a genuine predicate or boolean is required (MySQL, PostgreSQL) → T-SQL, Oracle": "value-in-predicate-position",
    "A value-wrapped predicate compared again in predicate position collapses back to the predicate (MySQL) → T-SQL": "value-wrapped-predicate-collapse",
    "`flag IS [NOT] TRUE/FALSE` on a boolean column (PostgreSQL) → T-SQL, Oracle": "boolean-column-is-true-false",
    "`IS [NOT] DISTINCT FROM` (PostgreSQL null-safe comparison) → MySQL `<=>` / T-SQL, Oracle `EXISTS`/`INTERSECT`": "is-distinct-from",
    "`PIVOT` (T-SQL / Oracle) → PostgreSQL / MySQL": "pivot",
    "`UNPIVOT` (T-SQL / Oracle) → all targets": "unpivot",
    "`WHEN NOT MATCHED BY SOURCE` (T-SQL) → PostgreSQL / Oracle": "merge-when-not-matched-by-source",
    "Conditional `MATCHED` UPDATE+DELETE pair (T-SQL) → Oracle fold": "merge-matched-update-delete-fold",
    "A leading CTE feeding `MERGE` (T-SQL) → Oracle / MySQL": "merge-with-leading-cte",
    "Multi-table `DELETE … JOIN` (MySQL) → PostgreSQL / T-SQL / Oracle": "multi-table-delete-join",
    "`DELETE TOP (n)` row caps (T-SQL) → MySQL / Oracle / PostgreSQL": "delete-top-n-row-cap",
    "Multi-join `UPDATE … FROM … JOIN … JOIN …` (T-SQL / PostgreSQL) → Oracle / MySQL / PostgreSQL": "multi-join-update-from",
    "Row-value inequality (PostgreSQL / Oracle / MySQL) → T-SQL": "row-value-inequality",
    "Row-value `IN` (Oracle) → T-SQL": "row-value-in",
    "`INSERT`/`UPDATE … OUTPUT` (T-SQL) → PostgreSQL `RETURNING` / Oracle carrier": "output-to-returning",
    "`OUTPUT … INTO` redirect (T-SQL) → PostgreSQL": "output-into-redirect",
    "Trailing `ORDER BY` on `UNION`/`EXCEPT`/`INTERSECT` (T-SQL) → PostgreSQL / Oracle / MySQL": "set-op-trailing-order-by",
    "`ORDER BY` inside a joined derived table (any source) → T-SQL: kept only with a row cap": "derived-table-order-by-to-tsql",
    "Oracle `(+)` outer-join mark → explicit `LEFT JOIN … ON`; comma joins → `CROSS JOIN`": "oracle-outer-join-mark",
    "`ROWNUM <= n` (Oracle) → `LIMIT` / `TOP` / `FETCH FIRST`": "oracle-rownum-row-cap",
    "`FROM DUAL` synthesis and removal (bidirectional)": "from-dual",
    "`FROM (VALUES …)` / a quantified bare-`VALUES` subquery (PostgreSQL) → `UNION ALL` chain (every target)": "from-values-to-union-all",
    "`FROM generate_series(…)` (PostgreSQL) → a synthesized numbers source (every target)": "from-generate-series",
    "Parenthesized set-operation arms unwrap; an arm's own `ORDER BY`/`LIMIT` is shielded": "parenthesized-set-op-arms",
    "Parenthesized join-relation groups unwrap; a column-aliased table ref wraps into a derived table": "parenthesized-join-groups",
    "Auto-incrementing key columns (PostgreSQL `SERIAL` / T-SQL `IDENTITY` / Oracle `GENERATED … AS IDENTITY` / MySQL `AUTO_INCREMENT`)": "auto-incrementing-keys",
    "T-SQL identity-scope reads (`SCOPE_IDENTITY()`/`@@IDENTITY`/`IDENT_CURRENT()`) → PostgreSQL / Oracle / MySQL": "tsql-identity-scope-reads",
    "T-SQL `BIT` `0`/`1` values (defaults, `INSERT`, `UPDATE`, incl. inside procedure bodies) → PostgreSQL `BOOLEAN`": "tsql-bit-to-postgresql-boolean",
    "T-SQL `ALTER COLUMN <c> <type>` re-states the column's last-known nullability → PostgreSQL (both directions)": "alter-column-nullability",
    "Oracle bare `NUMBER` (no precision/scale) → role-aware numeric (B47)": "oracle-bare-number-role-aware",
    "Session-scoped temp tables (PostgreSQL `TEMP` / T-SQL `#temp` / MySQL `TEMPORARY`) → Oracle `GLOBAL TEMPORARY`": "session-temp-tables-to-oracle",
    "`CREATE TABLE AS SELECT` ↔ `SELECT ... INTO` for ordinary (non-temporary) tables": "ctas-vs-select-into",
    "`ON UPDATE <action>` (PostgreSQL / T-SQL / MySQL) → Oracle": "fk-on-update-action-to-oracle",
    "Self-referencing FK cascade (MySQL) → T-SQL": "self-referencing-fk-cascade",
    "One-word vs two-word negative options (Oracle `NOMAXVALUE`/`NOCYCLE` vs T-SQL/PostgreSQL `NO MAXVALUE`/`NO CYCLE`)": "sequence-negative-option-spelling",
    "T-SQL index `WITH (FILLFACTOR = n)` → Oracle / MySQL": "tsql-index-fillfactor",
    "`ENUM('lo','mid','hi')` (MySQL) → PostgreSQL / T-SQL / Oracle VARCHAR + CHECK": "mysql-enum-to-varchar-check",
    "Nameless `CREATE INDEX ON t(col)` (PostgreSQL) → T-SQL": "nameless-create-index-to-tsql",
    "Unnamed derived-table / `SELECT ... INTO` projections → synthesized `uq_col1` (T-SQL)": "unnamed-projection-synthesized-name",
    "`EXEC sp_<name>` degrade policy (T-SQL) → PostgreSQL / Oracle / MySQL": "exec-sp-degrade-policy",
    "Statement-after-`EXEC` survival fix": "statement-after-exec-survival",
    "`SET IDENTITY_INSERT t ON … INSERT … SET IDENTITY_INSERT t OFF` (T-SQL) → PostgreSQL / Oracle / MySQL": "set-identity-insert-degrade",
    "`SET SERVEROUTPUT ON` and similar client directives (Oracle) → PostgreSQL / T-SQL / MySQL": "sqlplus-client-directives",
    "Oracle `%TYPE`/`%ROWTYPE` column-type references → PostgreSQL / T-SQL / MySQL": "oracle-type-rowtype-references",
    "Oracle `%FOUND`/`%NOTFOUND`/`%ISOPEN`/`%ROWCOUNT` → T-SQL / MySQL": "oracle-cursor-attributes",
    "PL/pgSQL implicit `FOUND` / Oracle implicit `SQL%FOUND` → T-SQL `@@ROWCOUNT` / MySQL `ROW_COUNT()`": "implicit-found-flag",
    "MySQL `DECLARE {EXIT|CONTINUE} HANDLER FOR ...` → block-structured exception handling (PostgreSQL / Oracle / T-SQL)": "mysql-declare-handler",
    "RAISERROR (T-SQL) ↔ Oracle `RAISE_APPLICATION_ERROR` / PostgreSQL `RAISE EXCEPTION`: expression messages and printf substitutions": "raiserror-expression-messages",
    "EXEC / routine-call expression argument (Oracle) → synthesized variable (T-SQL)": "exec-expression-argument-hoist",
    "A constant dynamic-SQL string (T-SQL `EXEC sp_executesql` / Oracle `EXECUTE IMMEDIATE` / PL/pgSQL `EXECUTE`) → any target": "constant-dynamic-sql-string",
    "`RETURNS void` (PostgreSQL) → neutral scalar return type + synthesized `RETURN` (MySQL / T-SQL / Oracle)": "returns-void-signature-synthesis",
    "A bare result `SELECT` inside a procedure body (MySQL / PostgreSQL / T-SQL) → Oracle `SYS_REFCURSOR` OUT parameter, propagated to `CALL` sites": "bare-result-select-to-refcursor",
    "Scroll cursor `FETCH PRIOR/FIRST/LAST/ABSOLUTE/RELATIVE` (T-SQL) → Oracle / PostgreSQL / MySQL": "scroll-cursor-fetch",
    "Row-level trigger body (`SET NEW.col = expr`) → T-SQL statement-level `UPDATE ... WHERE ... IN (SELECT ... FROM inserted)`": "row-level-trigger-body-to-tsql",
    "Oracle event predicates (`INSERTING`/`DELETING`/`UPDATING('col')`) → per-engine rewrite": "oracle-trigger-event-predicates",
    "PL/pgSQL trigger context variables (`TG_NAME`/`TG_TABLE_NAME`/`TG_OP`/`TG_WHEN`/`TG_LEVEL`, `TG_ARGV`/`TG_NARGS`) → compile-time constants once the function inlines": "plpgsql-trigger-context-variables",
    "PG named transition tables (`REFERENCING ... TABLE AS alias`) → T-SQL `inserted`/`deleted` alias rename": "pg-named-transition-tables",
    "Row-level trigger re-reading its own table (MySQL/PostgreSQL) ↔ Oracle `COMPOUND TRIGGER`": "trigger-reading-own-table",
    "T-SQL `INSTEAD OF` trigger → PostgreSQL (native on views, emulated on tables)": "tsql-instead-of-trigger",
    "Trigger body → PostgreSQL `CREATE FUNCTION ... RETURNS TRIGGER` + `CREATE TRIGGER`": "trigger-body-to-pg-function",
    "Bare `RETURN;` inside a PostgreSQL trigger function's nested handler → `RETURN NEW;`": "pg-trigger-bare-return",
    "Empty trigger body → synthesized `SET NOCOUNT ON;` no-op (T-SQL)": "empty-trigger-body-noop",
    "T-SQL cursor-variable binding (`SET @cur = CURSOR ... FOR q; OPEN @cur;`) → PostgreSQL / Oracle / MySQL": "tsql-cursor-variable-binding",
    "PL/SQL `FOR rec IN cur LOOP` (Oracle) → T-SQL explicit cursor scaffold": "cursor-for-loop-to-tsql",
    "PL/SQL cursor `FOR` loop (Oracle) → MySQL explicit cursor scaffold": "cursor-for-loop-to-mysql",
    "Numeric range `FOR i IN a..b LOOP` (Oracle) → MySQL / T-SQL explicit `WHILE` + counter": "numeric-range-for-loop",
    "Bare `RETURN` in a MySQL procedure → labeled `proc_exit:` block + `LEAVE`": "mysql-bare-return-to-leave",
    "Leading `DECLARE` block reordered (MySQL): variables before cursors": "mysql-declare-reorder",
}

#: Slug overrides for the prose-only ``## `` sections and section overviews.
_SECTION_SLUG_OVERRIDE: dict[tuple[str, str], str] = {
    (
        "aggregates-windows",
        "Topics left out for lack of source support",
    ): "topics-left-out",
    (
        "aggregates-windows",
        "Numeric division, cast rounding, and zero-divisor semantics",
    ): "numeric-division-overview",
    ("ddl", "Topics left out for lack of source support"): "topics-left-out",
    (
        "ddl",
        "Cross-statement schema-state-driven coercion",
    ): "cross-statement-coercion-overview",
    (
        "ddl",
        "Synthesized identifiers for anonymous constructs",
    ): "synthesized-identifiers-overview",
    ("procedural", "Topics left out for lack of source support"): "topics-left-out",
    (
        "procedural",
        "Comments written before a routine header",
    ): "comments-before-routine-header",
    (
        "procedural",
        "Return-type and signature synthesis",
    ): "return-type-synthesis-overview",
    ("procedural", "Triggers"): "triggers-overview",
    ("procedural", "Loop and cursor desugaring"): "loop-cursor-desugaring-overview",
    (
        "dml",
        "Oracle join syntax and row limits (source direction)",
    ): "oracle-join-source-overview",
}

# ---------------------------------------------------------------------------
# Link rewriting (fence-aware).
# ---------------------------------------------------------------------------

_LINK_RE = re.compile(r"\]\(([^)]+)\)")
_FENCE_RE = re.compile(r"^(```+|~~~+)")


def _rewrite_target(target: str) -> str:
    """Rewrite one relative link target for the new one-level-deeper home."""
    if target.startswith("#") or target.startswith(("http://", "https://")):
        return target
    base, sep, anchor = target.partition("#")
    anchor = sep + anchor
    if base.startswith("../"):
        return "../" + base + anchor
    if base == "README.md":
        return "../README.md" + anchor
    if base in _TOPIC_SET:
        return f"../{base[:-3]}/README.md" + anchor
    return target


def _map_lines_outside_fences(text: str, fn) -> str:
    out: list[str] = []
    in_fence = False
    fence_tok: str | None = None
    for line in text.split("\n"):
        m = _FENCE_RE.match(line)
        if m:
            tok = m.group(1)[0] * 3
            if not in_fence:
                in_fence, fence_tok = True, tok
            elif line.strip().startswith(fence_tok or ""):
                in_fence, fence_tok = False, None
            out.append(line)
            continue
        out.append(line if in_fence else fn(line))
    return "\n".join(out)


def rewrite_links(text: str) -> str:
    """Apply :func:`_rewrite_target` to every ``](...)`` outside code fences."""
    return _map_lines_outside_fences(
        text,
        lambda line: _LINK_RE.sub(
            lambda mm: "](" + _rewrite_target(mm.group(1)) + ")", line
        ),
    )


def _blank_link_targets(text: str) -> str:
    """Replace every ``](target)`` with ``](@)`` so two texts can be compared
    ignoring link targets — used to prove the rewrite touched nothing else."""
    return _map_lines_outside_fences(text, lambda line: _LINK_RE.sub("](@)", line))


# ---------------------------------------------------------------------------
# Parsing into blocks.
# ---------------------------------------------------------------------------


@dataclass
class Block:
    level: int  # 1, 2 or 3
    title: str  # heading text (without the ``#`` prefix)
    lines: list[str]  # full block text INCLUDING the heading line, as lines


def parse_blocks(text: str) -> list[Block]:
    lines = text.split("\n")
    in_fence = False
    fence_tok: str | None = None
    heads: list[tuple[int, int, str]] = []
    for i, line in enumerate(lines):
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
        if line.startswith("### "):
            heads.append((i, 3, line[4:]))
        elif line.startswith("## "):
            heads.append((i, 2, line[3:]))
        elif line.startswith("# "):
            heads.append((i, 1, line[2:]))
    blocks: list[Block] = []
    for idx, (ln, level, title) in enumerate(heads):
        nxt = heads[idx + 1][0] if idx + 1 < len(heads) else len(lines)
        blocks.append(Block(level=level, title=title, lines=lines[ln:nxt]))
    return blocks


def _section_has_children(blocks: list[Block], i: int) -> bool:
    """Does the ``## `` block at index *i* have a ``### `` before the next ``## ``?"""
    for j in range(i + 1, len(blocks)):
        if blocks[j].level == 2:
            return False
        if blocks[j].level == 3:
            return True
    return False


# ---------------------------------------------------------------------------
# Slug / direction derivation.
# ---------------------------------------------------------------------------

_ENGINE_TOKENS: tuple[tuple[str, str], ...] = (
    ("PL/pgSQL", "postgresql"),
    ("PL-pgSQL", "postgresql"),
    ("PostgreSQL", "postgresql"),
    ("Postgres", "postgresql"),
    ("PL/SQL", "oracle"),
    ("PL-SQL", "oracle"),
    ("Oracle", "oracle"),
    ("T-SQL", "tsql"),
    ("TSQL", "tsql"),
    ("SQL Server", "tsql"),
    ("MySQL", "mysql"),
)
_CANON_ORDER = ("tsql", "oracle", "postgresql", "mysql")


def _engines_in(fragment: str) -> list[str]:
    found: list[str] = []
    for token, canon in _ENGINE_TOKENS:
        if token in fragment and canon not in found:
            found.append(canon)
    if (
        re.search(r"\b(all|every)\b", fragment, re.IGNORECASE)
        and "target" in fragment.lower()
    ):
        found.append("all")
    return found


def _canon_join(engines: list[str]) -> str:
    if "all" in engines:
        return "all"
    ordered = [e for e in _CANON_ORDER if e in engines]
    return "/".join(ordered)


def derive_direction(title: str) -> tuple[str, bool]:
    """Return ``(direction, inferred)``; *inferred* is True when the title had
    no arrow and the value came from :data:`_DIRECTION_OVERRIDE`."""
    if title in _DIRECTION_OVERRIDE:
        return _DIRECTION_OVERRIDE[title], True
    for arrow in (" ↔ ", " → "):
        if arrow in title:
            left, right = title.split(arrow, 1)
            srcs = _canon_join(_engines_in(left))
            tgts = _canon_join(_engines_in(right))
            if srcs and tgts:
                return f"{srcs}{arrow}{tgts}", False
            return "cross-engine", True
    return "cross-engine", True


_SLUG_STRIP = re.compile(r"[^a-z0-9]+")


def _auto_slug(title: str) -> str:
    s = title.lower().replace("→", " to ").replace("↔", " to ")
    s = _SLUG_STRIP.sub("-", s).strip("-")
    return "-".join(s.split("-")[:6])


# ---------------------------------------------------------------------------
# Emission plan.
# ---------------------------------------------------------------------------


@dataclass
class Emitted:
    path: Path
    title: str  # page ``# `` title
    heading_line: str  # the ORIGINAL heading line, to re-insert on reconstruct
    body_lines: list[str]  # everything after the heading line, verbatim
    topic: str
    type_name: str
    direction: str
    kind: str  # "article" | "overview"
    inferred: bool
    order: int


@dataclass
class TopicPlan:
    topic: str
    intro_lines: list[str] = field(default_factory=list)
    emitted: list[Emitted] = field(default_factory=list)


def build_plan(topic: str, rewritten: str) -> TopicPlan:
    blocks = parse_blocks(rewritten)
    plan = TopicPlan(topic=topic)
    topic_dir = _RATIONALE / topic
    order = 0
    current_type: str | None = None

    for i, block in enumerate(blocks):
        if block.level == 1:
            plan.intro_lines = block.lines[1:]
            continue
        if block.level == 2:
            current_type = block.title
            body = block.lines[1:]
            has_children = _section_has_children(blocks, i)
            if has_children and not any(ln.strip() for ln in body):
                continue  # section header only (blank intro) → regenerated later
            # overview page: either a section intro, or a prose-only section
            slug = _SECTION_SLUG_OVERRIDE.get((topic, block.title))
            assert slug, f"missing section slug override: {topic!r} {block.title!r}"
            order += 1
            plan.emitted.append(
                Emitted(
                    path=topic_dir / f"{slug}.md",
                    title=block.title,
                    heading_line=block.lines[0],
                    body_lines=body,
                    topic=topic,
                    type_name=block.title,
                    direction="—",
                    kind="overview",
                    inferred=False,
                    order=order,
                )
            )
            continue
        # level-3 article
        title = block.title
        type_name = current_type if current_type is not None else _FLAT_TYPES.get(title)
        assert type_name, f"no type for article: {topic!r} {title!r}"
        direction, inferred = derive_direction(title)
        slug = _SLUG_OVERRIDE.get(title, _auto_slug(title))
        order += 1
        plan.emitted.append(
            Emitted(
                path=topic_dir / f"{slug}.md",
                title=title,
                heading_line=block.lines[0],
                body_lines=block.lines[1:],
                topic=topic,
                type_name=type_name,
                direction=direction,
                kind="article",
                inferred=inferred,
                order=order,
            )
        )
    return plan


# ---------------------------------------------------------------------------
# File text + verification.
# ---------------------------------------------------------------------------


def _nav_line(topic: str) -> str:
    return (
        f"[← {_ENGINE_TITLE[topic]}](README.md) · [All rationale topics](../README.md)"
    )


def _page_text(em: Emitted) -> str:
    inf = " direction-inferred=true" if em.inferred else ""
    meta = (
        f'<!-- rationale: topic={em.topic} type="{em.type_name}" '
        f'direction="{em.direction}" kind={em.kind} order={em.order}{inf} -->'
    )
    header = [_nav_line(em.topic), "", meta, "", f"# {em.title}"]
    return "\n".join(header + em.body_lines)


def _extract_body(page_text: str, title: str) -> list[str]:
    """Recover the body lines: everything after the first ``# <title>`` line."""
    lines = page_text.split("\n")
    marker = f"# {title}"
    for i, ln in enumerate(lines):
        if ln == marker:
            return lines[i + 1 :]
    raise AssertionError(f"heading not found: {marker!r}")


def _reconstruct(
    rewritten: str, plan: TopicPlan, files: dict[Path, str], intro_path: Path
) -> str:
    """Rebuild the link-rewritten page from the emitted files + intro partial."""
    blocks = parse_blocks(rewritten)
    by_heading: dict[str, list[Emitted]] = {}
    for em in plan.emitted:
        by_heading.setdefault(em.heading_line, []).append(em)

    out: list[str] = []
    for i, block in enumerate(blocks):
        if block.level == 1:
            out.append(block.lines[0])
            out.extend(files[intro_path].split("\n"))
            continue
        if block.level == 2:
            out.append(block.lines[0])
            has_children = _section_has_children(blocks, i)
            body = block.lines[1:]
            if has_children and not any(ln.strip() for ln in body):
                out.extend(body)  # blank scaffolding regenerated verbatim
            else:
                em = by_heading[block.lines[0]].pop(0)
                out.extend(_extract_body(files[em.path], em.title))
            continue
        em = by_heading[block.lines[0]].pop(0)
        out.append(block.lines[0])
        out.extend(_extract_body(files[em.path], em.title))
    return "\n".join(out)


def _first_diff(a: str, b: str) -> None:
    la, lb = a.split("\n"), b.split("\n")
    for i in range(max(len(la), len(lb))):
        x = la[i] if i < len(la) else "<EOF>"
        y = lb[i] if i < len(lb) else "<EOF>"
        if x != y:
            print(f"  first diff at line {i + 1}:")
            print(f"    original:      {x!r}")
            print(f"    reconstructed: {y!r}")
            return


def _stub(topic: str) -> str:
    return (
        f"# {_ENGINE_TITLE[topic]}\n\n"
        f"This page has moved. See **[{topic}/README.md]({topic}/README.md)** "
        f"for the topic index and its per-article pages.\n"
    )


def run(dry_run: bool) -> int:
    total_articles = total_overviews = 0
    for topic in _TOPICS:
        original = (_RATIONALE / f"{topic}.md").read_text(encoding="utf-8")
        rewritten = rewrite_links(original)

        if _blank_link_targets(original) != _blank_link_targets(rewritten):
            print(f"ABORT: link rewrite altered non-link text in {topic}.md")
            return 1

        plan = build_plan(topic, rewritten)

        files: dict[Path, str] = {}
        intro_path = _RATIONALE / topic / "_intro.md"
        files[intro_path] = "\n".join(plan.intro_lines)
        seen: set[Path] = set()
        for em in plan.emitted:
            if em.path in seen:
                print(f"ABORT: duplicate slug {em.path.name} in {topic}")
                return 1
            seen.add(em.path)
            files[em.path] = _page_text(em)

        recon = _reconstruct(rewritten, plan, files, intro_path)
        if recon != rewritten:
            print(f"ABORT: reconstruction mismatch for {topic}.md")
            _first_diff(rewritten, recon)
            return 1

        if not dry_run:
            (_RATIONALE / topic).mkdir(parents=True, exist_ok=True)
            for path, content in files.items():
                path.write_text(content.rstrip("\n") + "\n", encoding="utf-8")
            (_RATIONALE / f"{topic}.md").write_text(_stub(topic), encoding="utf-8")

        n_art = sum(1 for e in plan.emitted if e.kind == "article")
        n_ov = sum(1 for e in plan.emitted if e.kind == "overview")
        total_articles += n_art
        total_overviews += n_ov
        print(
            f"  {topic:20s} articles={n_art:3d} overviews={n_ov} intro={len(plan.intro_lines)} lines"
        )

    print(
        f"\n7 topics · {total_articles} article pages · {total_overviews} overview pages"
    )
    print(
        "VERIFICATION PASSED: every page reconstructs byte-for-byte from its split files."
    )
    if dry_run:
        print("(dry run — no files written)")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="verify only; write nothing")
    args = ap.parse_args(argv)
    return run(args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
