# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Declarative rationale side-table for the ``UNIQUE-NNNN`` catalog (B31).

The *why* of each degrade/creative conversion — the engine-level reason, a
worked example, and the exact divergence — used to live only in free-form
docstrings and hand-written ``docs/rationale/`` pages, which drift. This module
makes that narrative layer **generable**: each diagnostic code may carry a
:class:`Rationale`, keyed by the same ``UNIQUE-NNNN`` code the B32 registry
(:mod:`unique.core.diagnostics`) allocates. ``scripts/generate_reference_docs.py``
(T8) then emits ``docs/reference/warnings.md`` mechanically, and
``tests/unit/core/test_diagnostics.py`` reports codes with no rationale
(a floor that ratchets *down*, never up).

Design (B31 "Design constraint"):

* A **side-table keyed by the code**, deliberately a separate module rather
  than extra fields on :class:`~unique.core.diagnostics.Diagnostic`. The B32
  registry stays a lean ``code -> {category, message}`` table read by every
  emission site and by the registry-integrity test; the rationale is
  docs-generation metadata consumed only at *build* time by T8 and the
  coverage test. No emitter imports this module — zero runtime cost, and no
  churn on the shared ``DIAGNOSTICS`` dict.
* Every field must be **traceable** (the ``docs/rationale/`` rule): each entry
  below is sourced from a curated ``docs/rationale/*.md`` page and/or a live
  probe of the named corpus case, so ``example_case`` names a real
  ``tests/fixtures/challenge/`` slug (or a ``path::test`` reference where no
  corpus case exercises the construct). A code whose rationale cannot be
  sourced honestly is **absent** here — the coverage check reports it; it is
  never invented.
"""

from __future__ import annotations

from typing import NamedTuple


class Rationale(NamedTuple):
    """Narrative metadata for one ``UNIQUE-NNNN`` diagnostic.

    * ``construct`` — the source construct's name (what the user wrote).
    * ``reason`` — the *engine-level* why a direct mapping does not exist
      (a missing value type, a different clamping rule, a parser limit…),
      at the ``docs/rationale/`` bar — never merely "unsupported".
    * ``example_case`` — a ``tests/fixtures/challenge/`` case slug, or a
      ``path::test`` reference where no corpus case exercises the construct.
    * ``divergence`` — ``"faithful"``, or a precise description of what
      differs between source and target.
    """

    construct: str
    reason: str
    example_case: str
    divergence: str


_R = Rationale

#: ``UNIQUE-NNNN`` -> :class:`Rationale`. Keys must be registered in
#: :data:`unique.core.diagnostics.DIAGNOSTICS` (enforced by the coverage test).
#: Append entries only when every field is honestly sourceable; see the module
#: docstring. Keeping this sorted by code eases review against the registry.
RATIONALES: dict[str, Rationale] = {
    "UNIQUE-1001": _R(
        construct=(
            "MERGE with one unconditional MATCHED UPDATE and one "
            "unconditional NOT MATCHED INSERT (→ MySQL)"
        ),
        reason=(
            "MySQL has no MERGE statement at all; the canonical "
            "single-UPDATE/single-INSERT shape is the only one with a "
            "faithful MySQL rewrite (INSERT ... SELECT ... ON DUPLICATE KEY "
            "UPDATE), and that rewrite relies on a UNIQUE or PRIMARY KEY "
            "covering the ON columns to detect the 'matched' case the same "
            "way the MERGE's ON did."
        ),
        example_case=(
            "tests/unit/core/test_merge_mysql.py::TestMergeToMySQL::"
            "test_upsert_signals_key_assumption"
        ),
        divergence=(
            "Faithful when a UNIQUE/PRIMARY KEY covers the ON columns (the "
            "common case); the key assumption is only noted, not verified "
            "against a live schema."
        ),
    ),
    "UNIQUE-1002": _R(
        construct="SET IDENTITY_INSERT ON/OFF (T-SQL)",
        reason=(
            "T-SQL requires IDENTITY_INSERT ON before a script may supply its "
            "own value for an identity column; no other engine has an explicit "
            "identity-override mode — they simply accept an explicit value in "
            "the INSERT column list — so the ON/OFF bracket has nothing to map "
            "to."
        ),
        example_case="reda-ts-identity-insert",
        divergence=(
            "The INSERT's data is faithful; the two SET directives degrade to "
            "carriers (one warning)."
        ),
    ),
    "UNIQUE-1003": _R(
        construct=(
            "A source construct with no per-site conversion — the shared "
            "RawSQL fallback carrier (e.g. a SELECT-list set-returning "
            "function relocated to FROM, which MySQL has no inline "
            "table-function form for)"
        ),
        reason=(
            "This code is the converter's generic 'could not emit this node' "
            "escape valve — used at many unrelated call sites for whatever "
            "sqlglot reason string reaches it (an unmodeled expression type, "
            "a foreign built-in with no target form, a parse error) — so the "
            "concrete engine-level reason is carried in the comment text at "
            "runtime rather than fixed per code."
        ),
        example_case=(
            "tests/integration/test_challenge.py::TestGenerateSeriesFrom::"
            "test_srf_in_select_list_moved_to_from"
        ),
        divergence=(
            "Warned limit — the statement is preserved as a comment; the "
            "base rows are unaffected on targets where the construct does "
            "map."
        ),
    ),
    "UNIQUE-1004": _R(
        construct="NULLS FIRST/LAST index-column ordering (→ Oracle/T-SQL/MySQL)",
        reason=(
            "NULLS FIRST/LAST in an index definition is Oracle-rejected "
            "outright (ORA-00907) and has no T-SQL/MySQL spelling at all; "
            "it affects only the index's physical null placement, not "
            "query results, so it is dropped rather than block the CREATE "
            "INDEX."
        ),
        example_case="postgresql-drop2-NULLS",
        divergence="Warned limit — physical null-order only, no result-set impact.",
    ),
    "UNIQUE-1005": _R(
        construct=(
            "An index over an expression, e.g. CREATE INDEX ... "
            "((concat(a, b))) (→ T-SQL)"
        ),
        reason=(
            "T-SQL has no expression/functional index at all — an index "
            "can only cover column names, not an arbitrary expression — so "
            "there is no CREATE INDEX form to target; a computed column "
            "plus an index on it is the closest workaround, but it is a "
            "schema change the transpiler cannot make unilaterally."
        ),
        example_case=(
            "tests/integration/test_pg_source_wave1.py::"
            "TestWave204ExpressionIndexes::test_expression_index_carrier_tsql"
        ),
        divergence=(
            "Warned limit — statement preserved as a comment; add a "
            "computed column and index it by hand."
        ),
    ),
    "UNIQUE-1006": _R(
        construct=(
            "A partial (WHERE-filtered) UNIQUE index whose predicate is "
            "outside T-SQL's filtered-index grammar"
        ),
        reason=(
            "T-SQL's filtered-index WHERE accepts only a narrow comparison "
            "grammar (error 10735 otherwise); a broader UNIQUE index (one "
            "covering more rows than the filtered original) would reject "
            "rows the source's partial index allowed, so widening it "
            "silently would change what INSERTs succeed — the whole "
            "CREATE INDEX degrades rather than emit a subtly different "
            "constraint."
        ),
        example_case=(
            "tests/integration/test_pg_source_wave1.py::"
            "TestIndexRebuildRefinements::test_complex_predicate_unique_degrades"
        ),
        divergence="Warned limit — statement preserved as a comment.",
    ),
    "UNIQUE-1007": _R(
        construct=(
            "A partial (WHERE-filtered) non-unique index whose predicate "
            "is outside T-SQL's filtered-index grammar"
        ),
        reason=(
            "T-SQL's filtered-index WHERE accepts only a narrow comparison "
            "grammar (error 10735 otherwise); unlike the UNIQUE case, a "
            "broader plain index changes no INSERT/UPDATE behavior — it "
            "only covers more rows than strictly needed — so the predicate "
            "is dropped and the (now unfiltered) index is kept rather than "
            "degrading the whole statement."
        ),
        example_case=(
            "tests/integration/test_pg_source_wave1.py::"
            "TestIndexRebuildRefinements::"
            "test_complex_predicate_nonunique_drops_where"
        ),
        divergence=(
            "Warned limit — the index is broader than the source's (covers "
            "more rows); query results are unaffected."
        ),
    ),
    "UNIQUE-1008": _R(
        construct="A plain (unfiltered) UNIQUE index on a nullable column (→ T-SQL)",
        reason=(
            "PostgreSQL (and Oracle/MySQL) treat every NULL in a unique "
            "index as distinct from every other NULL, so multiple NULL "
            "rows are all allowed; T-SQL's UNIQUE index allows only a "
            "single NULL row — a genuine behavioral divergence with no "
            "rewrite that preserves PostgreSQL's semantics on T-SQL."
        ),
        example_case=(
            "tests/integration/test_pg_source_wave1.py::TestPgIndexToTsql::"
            "test_nameless_index_gets_a_name"
        ),
        divergence=(
            "Warned limit — a second NULL row that PostgreSQL allowed "
            "raises a duplicate-key error on T-SQL."
        ),
    ),
    "UNIQUE-1009": _R(
        construct=(
            "NOT applied to a non-predicate operand, e.g. (NOT NULL) IS "
            "NULL (→ T-SQL)"
        ),
        reason=(
            "PostgreSQL/MySQL/Oracle evaluate NOT under three-valued "
            "logic — the negation of NULL is still NULL — but T-SQL has no "
            "boolean value type at all: NOT requires a genuine predicate "
            "operand, so NOT of a bare NULL/column literal is error 4145, "
            "not a value."
        ),
        example_case="pg-not-null-is-null",
        divergence=(
            "Warned limit on T-SQL — the operand degrades to a carrier; "
            "faithful (1/TRUE) on the other three engines."
        ),
    ),
    "UNIQUE-1010": _R(
        construct=(
            "ALTER COLUMN ... TYPE on a column whose nullability the "
            "script never declares (→ T-SQL)"
        ),
        reason=(
            "T-SQL's ALTER COLUMN <type> re-states the FULL column "
            "definition and defaults to NULL when nullability is omitted, "
            "silently dropping an existing NOT NULL; without an in-script "
            "CREATE TABLE (or --db-url) to harvest the column's declared "
            "nullability from, the transpiler cannot know whether "
            "re-stating NULL is safe."
        ),
        example_case=(
            "tests/integration/test_pg_source_wave1.py::"
            "TestB10RunningColumnTypeAlterNullability::"
            "test_unknown_column_warns"
        ),
        divergence=(
            "Warned limit — the ALTER COLUMN still runs (best-effort "
            "NULL); verify the column keeps its original constraint."
        ),
    ),
    "UNIQUE-1011": _R(
        construct=(
            "A T-SQL named DEFAULT constraint (CONSTRAINT df_x DEFAULT ...) "
            "on an ADD/ALTER COLUMN (→ MySQL/PostgreSQL/Oracle)"
        ),
        reason=(
            "Only T-SQL names its DEFAULT constraints as a separate object; "
            "every other engine's DEFAULT is an anonymous column attribute "
            "with no CONSTRAINT <name> spelling at all, so the name has "
            "nothing to bind to and is dropped while the default value "
            "itself is kept."
        ),
        example_case=(
            "tests/integration/test_ddl_rename_dropindex.py::"
            "test_named_default_constraint_dropped_with_note"
        ),
        divergence=(
            "Warned limit — the constraint's name is lost (nothing "
            "references it downstream); the default value and column "
            "definition are faithful."
        ),
    ),
    "UNIQUE-1012": _R(
        construct=(
            "A T-SQL CREATE INDEX ... INCLUDE (col, ...) covering-columns "
            "clause (→ MySQL/Oracle)"
        ),
        reason=(
            "INCLUDE columns are stored in the index leaf but excluded from "
            "its key/sort order (a covering-index optimization); MySQL and "
            "Oracle indexes have no non-key column list at all, so there is "
            "no clause to carry the covering columns to."
        ),
        example_case=(
            "tests/integration/test_cross_dialect.py::"
            "TestPortableIndex::test_include_index_flagged_elsewhere"
        ),
        divergence=(
            "Warned limit — the index no longer covers those columns; a "
            "query relying on them for an index-only scan now needs a table "
            "lookup (PostgreSQL keeps INCLUDE natively)."
        ),
    ),
    "UNIQUE-1013": _R(
        construct="A filtered (WHERE-predicated) CREATE INDEX (→ MySQL/Oracle)",
        reason=(
            "MySQL and Oracle have no partial/filtered index at all — an "
            "index always covers every row of the table — so the predicate "
            "has no clause to attach to."
        ),
        example_case=(
            "tests/integration/test_cross_dialect.py::"
            "TestPortableIndex::test_filtered_index_flagged_elsewhere"
        ),
        divergence=(
            "Warned limit — the index now covers every row instead of just "
            "the filtered subset (PostgreSQL keeps the predicate natively)."
        ),
    ),
    "UNIQUE-1014": _R(
        construct="Physical index storage clause, e.g. WITH (FILLFACTOR = n) (T-SQL)",
        reason=(
            "FILLFACTOR and sibling physical clauses reserve per-page free "
            "space — a storage-tuning knob with no logical effect on query "
            "results; Oracle and MySQL CREATE INDEX have no equivalent clause."
        ),
        example_case="reda-ts-index-fillfactor-mysql",
        divergence=(
            "Faithful in result (storage-only); the clause is dropped and kept "
            "in a restorable note."
        ),
    ),
    "UNIQUE-1015": _R(
        construct=(
            "DISTINCT / ORDER BY over a string column under MySQL's default "
            "collation"
        ),
        reason=(
            "MySQL's default collation is case-insensitive, so DISTINCT / "
            "GROUP BY / ORDER BY treat 'a' and 'A' as equal and collapse them "
            "into one row; the case-sensitive PostgreSQL/Oracle defaults keep "
            "them distinct — a row-count divergence no ORDER BY LOWER() rewrite "
            "can bridge without column-level collation visibility."
        ),
        example_case="my-distinct-case",
        divergence="Documented limit, warned — deduplicated row counts may differ.",
    ),
    "UNIQUE-1016": _R(
        construct=(
            "GROUP BY CUBE / ROLLUP / GROUPING SETS super-aggregate rows " "(→ MySQL)"
        ),
        reason=(
            "MySQL has no CUBE / GROUPING SETS and only a trailing WITH "
            "ROLLUP, so a multi-element grouping's subtotal (super-aggregate) "
            "rows cannot be produced; only the base grouping is kept."
        ),
        example_case="pg-grouping-fn",
        divergence="Warned — base grouping kept; subtotal rows omitted.",
    ),
    "UNIQUE-1017": _R(
        construct=(
            "A multi-element GROUP BY combining CUBE/ROLLUP/GROUPING SETS "
            "in one clause, e.g. GROUP BY CUBE(a, b), ROLLUP(c) (→ MySQL)"
        ),
        reason=(
            "MySQL supports only a single trailing WITH ROLLUP modifier "
            "on the whole GROUP BY — it has no CUBE, no GROUPING SETS, "
            "and no way to combine multiple grouping elements — so a "
            "clause combining more than one such element has nothing to "
            "lower to beyond the plain column list."
        ),
        example_case="pg-groupby-multi-cube-rollup",
        divergence=(
            "Warned limit — the base grouping is kept but every "
            "super-aggregate (subtotal) row the combined CUBE/ROLLUP/"
            "GROUPING SETS would have produced is omitted."
        ),
    ),
    "UNIQUE-1018": _R(
        construct=(
            "A top-level SELECT ... FOR XML / FOR JSON PATH "
            "row-serialization clause (T-SQL) (→ MySQL/PostgreSQL/Oracle)"
        ),
        reason=(
            "FOR XML/FOR JSON collapses the whole multi-row result set "
            "into a single XML or JSON scalar under T-SQL's own "
            "node-naming and null-omission rules; no other engine has a "
            "matching top-level row-serialization clause, so there is no "
            "faithful drop-in and shipping the base rows raw would "
            "silently turn one scalar row into many rows/columns."
        ),
        example_case="reda-ts-for-json",
        divergence=(
            "Warned limit — the clause is dropped and the plain "
            "multi-row/multi-column result set is returned instead of "
            "the single serialized scalar; rebuild the aggregation with "
            "the target's own JSON/XML functions if the scalar form is "
            "required."
        ),
    ),
    "UNIQUE-1019": _R(
        construct="SQL_CALC_FOUND_ROWS on a SELECT with LIMIT (MySQL) → other engines",
        reason=(
            "SQL_CALC_FOUND_ROWS is a MySQL-only optimizer hint that makes "
            "a following FOUND_ROWS() return the row count the LIMIT would "
            "otherwise have discarded; no other engine has an equivalent "
            "two-statement result-caching mechanism."
        ),
        example_case="mysql-qdrop-SQL_CALC_FOU",
        divergence=(
            "Warned limit — the hint is dropped; run a separate COUNT(*) "
            "query for the discarded-row total."
        ),
    ),
    "UNIQUE-1020": _R(
        construct=(
            "INSERT INTO t VALUES () — an all-defaults insert with no "
            "column list (→ Oracle)"
        ),
        reason=(
            "Oracle's INSERT grammar has no all-defaults form: a "
            "column-less VALUES () is rejected outright, and there is no "
            "DEFAULT VALUES keyword (T-SQL) or empty-parens shorthand "
            "(MySQL/PostgreSQL) to fall back on without knowing the "
            "table's column list."
        ),
        example_case=(
            "tests/integration/test_pg_source_wave1.py::"
            "TestEmptyValuesAndIsNullValue::test_empty_values_oracle_degrades"
        ),
        divergence=(
            "Warned limit — statement preserved as a comment; supply an "
            "explicit column list to insert on Oracle."
        ),
    ),
    "UNIQUE-1021": _R(
        construct=(
            "An upsert (PG ON CONFLICT DO UPDATE-shaped) INSERT with no "
            "in-script conflict target to harvest"
        ),
        reason=(
            "PostgreSQL's ON CONFLICT DO UPDATE needs an explicit conflict "
            "target (column list or constraint); the source (e.g. a MySQL "
            "ON DUPLICATE KEY UPDATE, which names none) leaves it to be "
            "inferred from the table's declared key, and without an "
            "in-script CREATE TABLE (or --db-url) there is nothing to "
            "infer it from."
        ),
        example_case=(
            "tests/unit/core/test_upsert.py::"
            "test_mysql_upsert_without_known_key_degrades_whole"
        ),
        divergence=(
            "Warned limit — statement preserved as a comment rather than a "
            "bare INSERT that would raise a duplicate-key error."
        ),
    ),
    "UNIQUE-1022": _R(
        construct=(
            "MySQL INSERT ... ON DUPLICATE KEY UPDATE lowered to "
            "PostgreSQL ON CONFLICT (col) (or the MERGE ON clause)"
        ),
        reason=(
            "MySQL's ON DUPLICATE KEY UPDATE names no explicit conflict "
            "target — it fires on any unique or primary key the row "
            "collides with — while PostgreSQL's ON CONFLICT and the MERGE "
            "ON clause both require one; the transpiler infers it from the "
            "table's declared key (visible in-script or via --db-url) and "
            "must flag that inference, since a different key could exist."
        ),
        example_case=(
            "tests/unit/core/test_upsert.py::"
            "test_mysql_update_to_pg_needs_harvested_key"
        ),
        divergence=(
            "Warned assumption — faithful when the harvested key is the "
            "one that would actually collide."
        ),
    ),
    "UNIQUE-1023": _R(
        construct="PostgreSQL ON CONFLICT DO NOTHING lowered to MySQL INSERT IGNORE",
        reason=(
            "MySQL's INSERT IGNORE is a broader error-suppressor than "
            "PostgreSQL's DO NOTHING (or the MERGE insert-only forms): it "
            "also swallows non-duplicate errors — bad values, foreign-key "
            "violations — that the source would have raised, so the "
            "mapping is the closest available but not behavior-identical "
            "on error."
        ),
        example_case=(
            "tests/unit/core/test_upsert.py::"
            "test_pg_do_nothing_to_mysql_is_insert_ignore"
        ),
        divergence=(
            "Warned limit — faithful on a genuine duplicate key; a "
            "non-duplicate error that the source would raise is instead "
            "swallowed."
        ),
    ),
    "UNIQUE-1024": _R(
        construct=(
            "PostgreSQL ON CONFLICT (col) DO UPDATE lowered to MySQL ON "
            "DUPLICATE KEY UPDATE"
        ),
        reason=(
            "MySQL's ON DUPLICATE KEY UPDATE fires on a collision with ANY "
            "unique or primary key on the table, not only the single named "
            "conflict target the PostgreSQL source declared — a genuine "
            "any-key-vs-one-key semantic gap with no MySQL syntax to "
            "narrow it."
        ),
        example_case=(
            "tests/unit/core/test_upsert.py::"
            "test_pg_update_to_mysql_uses_on_duplicate_key"
        ),
        divergence=(
            "Warned limit — faithful when the named conflict target is "
            "the table's only unique key."
        ),
    ),
    "UNIQUE-1025": _R(
        construct="MySQL INSERT ... ON DUPLICATE KEY UPDATE lowered to a T-SQL MERGE",
        reason=(
            "MySQL's ON DUPLICATE KEY UPDATE names no explicit conflict "
            "column, but a MERGE's ON clause requires one; the transpiler "
            "assumes the table's declared key (harvested in-script or via "
            "--db-url) is the intended join column and must flag that "
            "assumption rather than silently pick a possibly-wrong key."
        ),
        example_case=(
            "tests/unit/core/test_upsert.py::"
            "test_mysql_update_to_tsql_lowers_to_merge_with_harvested_key"
        ),
        divergence=(
            "Warned assumption — faithful when the harvested key is the "
            "one that would actually collide."
        ),
    ),
    "UNIQUE-1027": _R(
        construct=(
            "A top-level (non-cursor-context) T-SQL @@ROWCOUNT reference "
            "(→ PostgreSQL/Oracle)"
        ),
        reason=(
            "@@ROWCOUNT is context-free only inside T-SQL's own session "
            "state; outside a T-SQL procedural body (the procedural path "
            "maps it to GET DIAGNOSTICS / SQL%ROWCOUNT using surrounding "
            "statement context) there is nothing to map it to, so a bare "
            "top-level reference gets a documented neutral value instead."
        ),
        example_case=(
            "tests/integration/test_pg_source_wave1.py::"
            "TestSystemGlobalsInDml::test_rowcount_pg_neutral"
        ),
        divergence=(
            "Warned limit — degrades to the constant 0 (MySQL maps to "
            "ROW_COUNT() instead and is faithful)."
        ),
    ),
    "UNIQUE-1028": _R(
        construct=(
            "A top-level (non-cursor-context) T-SQL @@FETCH_STATUS "
            "reference (→ PostgreSQL/Oracle/MySQL)"
        ),
        reason=(
            "@@FETCH_STATUS is cursor state by nature — the procedural "
            "path maps it using the surrounding FETCH's context (FOUND / "
            "handler flags / cursor%FOUND) — so a context-free top-level "
            "reference has nothing to bind to and gets a documented "
            "neutral instead."
        ),
        example_case=(
            "tests/integration/test_pg_source_wave1.py::"
            "TestFetchStatusTopLevel::test_fetch_status_neutral_pg"
        ),
        divergence="Warned limit — degrades to the constant 0 outside cursor context.",
    ),
    "UNIQUE-1030": _R(
        construct="T-SQL @@VERSION (→ PostgreSQL/MySQL)",
        reason=(
            "PostgreSQL's version() and MySQL's VERSION() return each "
            "engine's own version string in its own format, never "
            "T-SQL's — the closest available function, but the returned "
            "value can never equal the source's."
        ),
        example_case="ts-spid-version",
        divergence=(
            "Warned limit — mapped to the target's native version "
            "function; the string value differs from T-SQL's."
        ),
    ),
    "UNIQUE-1031": _R(
        construct="T-SQL @@VERSION (→ Oracle)",
        reason=(
            "Oracle's version string lives only in the v$version view, "
            "which needs a query (and often elevated privileges) — not a "
            "scalar expression a statement can splice in — so there is no "
            "drop-in replacement expression at all."
        ),
        example_case="ts-spid-version",
        divergence=(
            "Warned limit — degrades to NULL rather than a fabricated "
            "version string."
        ),
    ),
    "UNIQUE-1032": _R(
        construct="T-SQL @@SPID (→ PostgreSQL/MySQL/Oracle)",
        reason=(
            "Every engine spells its session/connection identifier "
            "differently (PostgreSQL pg_backend_pid(), MySQL "
            "CONNECTION_ID(), Oracle SYS_CONTEXT('USERENV','SID')) and the "
            "value is inherently per-connection, so it can never equal "
            "T-SQL's @@SPID even when mapped to the engine's closest "
            "equivalent."
        ),
        example_case="ts-spid-version",
        divergence=(
            "Warned limit — mapped to the target's own session-id "
            "function; the numeric value differs from T-SQL's."
        ),
    ),
    "UNIQUE-1033": _R(
        construct=(
            "Oracle SQL%ROWCOUNT used in a re-evaluated loop or EXIT "
            "condition (WHILE SQL%ROWCOUNT > 0 / EXIT WHEN SQL%ROWCOUNT = "
            "0) (→ PostgreSQL)"
        ),
        reason=(
            "PostgreSQL reads the last statement's row count only "
            "through the GET DIAGNOSTICS statement, not an inline "
            "expression; a single hoisted capture placed before the loop "
            "would freeze the value instead of re-reading it each "
            "iteration the way SQL%ROWCOUNT does, so a condition "
            "re-evaluated every pass cannot be captured with one hoist "
            "and has no faithful inline substitute (a reference in the "
            "loop body, or in a single-evaluated position like an "
            "IF/assignment/RETURN, is captured by a hoisted local and "
            "never reaches this code)."
        ),
        example_case=(
            "tests/integration/test_oracle_rowcount_hoist_b37.py::"
            "TestLoopConditionDegrades::test_while_condition_kept_as_carrier"
        ),
        divergence=(
            "Warned limit — degrades to the constant 0; T-SQL and MySQL "
            "read the row count inline natively and are unaffected."
        ),
    ),
    "UNIQUE-1034": _R(
        construct="TABLESAMPLE (→ MySQL)",
        reason=(
            "MySQL has no row-sampling clause at all (and sampling is "
            "inherently non-deterministic besides), so there is no way to "
            "return a subset of rows equivalent to the source's sample."
        ),
        example_case="pg-tablesample",
        divergence="Warned limit — all rows are returned instead of a sample.",
    ),
    "UNIQUE-1037": _R(
        construct="TOP ... WITH TIES (T-SQL) / FETCH FIRST ... WITH TIES (→ MySQL)",
        reason=(
            "MySQL's LIMIT has no WITH TIES equivalent — it caps at a "
            "fixed row count with no provision for including rows that "
            "tie the last one on the ORDER BY key."
        ),
        example_case="ts-top-with-ties",
        divergence=(
            "Warned limit — rows tying the last returned row are not "
            "included (PostgreSQL/Oracle FETCH FIRST ... WITH TIES are "
            "faithful)."
        ),
    ),
    "UNIQUE-1038": _R(
        construct="TOP n PERCENT (T-SQL) → PostgreSQL/MySQL",
        reason=(
            "PostgreSQL's LIMIT and MySQL's LIMIT both take a row count, "
            "not a percentage of the result set's size — and the result "
            "set's size is not knowable at transpile time (it depends on "
            "the query's own WHERE/JOIN), so n cannot be converted to an "
            "equivalent row count without executing the query first."
        ),
        example_case=(
            "tests/unit/core/test_converter.py::TestParseSelectLimit::"
            "test_top_percent_postgresql_documented"
        ),
        divergence=(
            "Warned limit — n is emitted as a literal row count, not n "
            "percent of the actual result size; adjust with "
            "CEIL(n/100 * total_rows) if a true percentage is required."
        ),
    ),
    "UNIQUE-1039": _R(
        construct="Oracle TIMESTAMP WITH LOCAL TIME ZONE column (→ PostgreSQL)",
        reason=(
            "PostgreSQL timestamptz has the identical session-time-zone display "
            "behaviour as Oracle's LTZ (live-verified: the same instant shows 12:00 in "
            "a UTC session and 07:00 in a New York session), so the column maps "
            "directly rather than losing anything."
        ),
        example_case="ora-dttypes",
        divergence=(
            "Faithful — same instant, same session-dependent wall-clock display."
        ),
    ),
    "UNIQUE-1040": _R(
        construct="Oracle TIMESTAMP WITH LOCAL TIME ZONE column (→ T-SQL)",
        reason=(
            "T-SQL has no session-local timestamp type; the column maps to "
            "DATETIMEOFFSET, which keeps a fixed stored offset instead of re-deriving "
            "the session's own time zone on every read."
        ),
        example_case="ora-dttypes",
        divergence=(
            "Warned limit — the value's instant is kept, but the session-time-zone "
            "display is not reproduced."
        ),
    ),
    "UNIQUE-1041": _R(
        construct="Oracle TIMESTAMP WITH LOCAL TIME ZONE column (→ MySQL)",
        reason=(
            "MySQL has no session-local timestamp type; the column maps to TIMESTAMP, "
            "which normalizes to UTC storage instead of re-deriving the session's own "
            "time zone on every read."
        ),
        example_case="ora-dttypes",
        divergence=(
            "Warned limit — the value's instant is kept, but the session-time-zone "
            "display is not reproduced."
        ),
    ),
    "UNIQUE-1042": _R(
        construct="A TIME/TIMETZ column (→ Oracle)",
        reason=(
            "Oracle has no bare TIME (or TIME WITH TIME ZONE) column type, so the "
            "time-of-day value is stored as INTERVAL DAY TO SECOND (a duration since "
            "midnight) instead."
        ),
        example_case="pg-dttypes",
        divergence=(
            "Faithful for TIME (the same time-of-day value, stored as a duration); "
            "warned limit for TIMETZ — the zone offset is dropped."
        ),
    ),
    "UNIQUE-1043": _R(
        construct=(
            "A bare PostgreSQL INTERVAL column, with no YEAR TO MONTH/DAY TO SECOND "
            "qualifier (→ Oracle)"
        ),
        reason=(
            "PostgreSQL's INTERVAL mixes year-month and day-second fields in one "
            "value; Oracle splits INTERVAL into two distinct column types, so the "
            "column maps to INTERVAL DAY TO SECOND and any year-month component has "
            "nowhere to go."
        ),
        example_case="pg-dttypes",
        divergence=(
            "Warned limit — year-month values need a separate INTERVAL YEAR TO MONTH "
            "column on Oracle."
        ),
    ),
    "UNIQUE-1044": _R(
        construct="An INTERVAL column (→ T-SQL / MySQL)",
        reason=(
            "T-SQL has no interval type at all, and MySQL's INTERVAL is only an "
            "arithmetic qualifier (e.g. INTERVAL 1 DAY), never a column type, so the "
            "interval value is kept as text instead."
        ),
        example_case="ora-tz-interval",
        divergence=(
            "Warned limit — the value is kept as text, not usable in interval "
            "arithmetic on the target."
        ),
    ),
    "UNIQUE-1045": _R(
        construct=(
            "A fractional-seconds column precision above 6 "
            "(DATETIME(n)/TIMESTAMP(n)/TIME(n) with n>6) (→ MySQL)"
        ),
        reason=(
            "MySQL's sub-second precision caps at microseconds (6 digits); a higher "
            "source precision (e.g. T-SQL DATETIME2(7)) has no wider MySQL "
            "fractional-seconds type to map onto."
        ),
        example_case="ts-datetimeoffset",
        divergence=(
            "Warned limit — precision clamped to 6; sub-microsecond digits lost."
        ),
    ),
    "UNIQUE-1046": _R(
        construct="MySQL multi-bit BIT(n>1) column (→ Oracle / T-SQL)",
        reason=(
            "Neither engine has a bit-string column type; a multi-bit BIT is a 64-bit "
            "numeric value, not a boolean, so it maps to a wide NUMBER/NUMERIC that "
            "holds the same value instead."
        ),
        example_case="my-bintypes",
        divergence=(
            "Warned limit — the numeric value is preserved but the bit-string type "
            "semantics (bitwise operations, display) are not."
        ),
    ),
    "UNIQUE-1047": _R(
        construct=(
            "MySQL SET column type — an unordered combination of values "
            "(→ other engines)"
        ),
        reason=(
            "Only MySQL has a 'combination of values' column type; unlike "
            "ENUM (one value from a list, mappable to VARCHAR + CHECK IN "
            "(...)), a SET holds any comma-joined subset of its allowed "
            "members, which no single CHECK expression can validate, so it "
            "maps to a plain VARCHAR with no CHECK, noting the allowed "
            "members for reference."
        ),
        example_case=(
            "tests/integration/test_real_world.py::TestOutputValidity::"
            "test_statements_parse_in_target_dialect"
        ),
        divergence=(
            "Warned limit — the value-combination constraint is not "
            "enforced on the target."
        ),
    ),
    "UNIQUE-1048": _R(
        construct="T-SQL structure-clone CREATE TABLE t2 LIKE t1 (→ T-SQL / Oracle)",
        reason=(
            "T-SQL/Oracle have no native CREATE TABLE ... LIKE; the faithful idiom is "
            "an empty SELECT INTO / CTAS (WHERE 1 = 0), which clones column structure "
            "only — indexes, keys and constraints are not part of that idiom."
        ),
        example_case=(
            "tests/integration/test_pg_source_wave1.py::TestCreateTableLikeClone::test_like_tsql_empty_select_into"
        ),
        divergence="Warned limit — the source's indexes/keys are not cloned.",
    ),
    "UNIQUE-1049": _R(
        construct=(
            "IDENTITY / GENERATED AS IDENTITY with a non-default "
            "START/INCREMENT (→ MySQL)"
        ),
        reason=(
            "MySQL's only identity form is AUTO_INCREMENT, whose seed is a "
            "table option (AUTO_INCREMENT = n) with no per-column "
            "START/INCREMENT — a non-default seed/step cannot be reproduced as "
            "a column clause."
        ),
        example_case="ora-identity-opts",
        divergence="Warned limit — AUTO_INCREMENT starts at 1 and steps by 1.",
    ),
    "UNIQUE-1050": _R(
        construct=(
            "MySQL column-level ON UPDATE CURRENT_TIMESTAMP auto-refresh clause (→ "
            "other engines)"
        ),
        reason=(
            "No other engine has a column-level auto-refresh-on-update clause; the "
            "behaviour can only be reproduced there with an explicit AFTER UPDATE "
            "trigger."
        ),
        example_case="mysql-drop2-ON",
        divergence=(
            "Warned limit — the column keeps its DEFAULT but is no longer "
            "auto-refreshed; add a trigger to restore the behaviour."
        ),
    ),
    "UNIQUE-1051": _R(
        construct="A column-level COLLATE clause (→ a different target engine)",
        reason=(
            "Collation names are engine-specific catalog identifiers with no "
            "cross-engine mapping; without a live database connection, Unique cannot "
            "resolve what collation the source column actually uses."
        ),
        example_case="postgresql-drop4-COLLATE",
        divergence=(
            "Warned limit — the column uses the target's default collation; "
            "comparisons/ordering may differ."
        ),
    ),
    "UNIQUE-1052": _R(
        construct="MySQL/Oracle INVISIBLE column attribute (→ PostgreSQL / T-SQL)",
        reason=(
            "PostgreSQL and T-SQL have no invisible-column attribute (a column "
            "excluded from SELECT *), so it cannot be reproduced there."
        ),
        example_case="red2-my-invisible-column-drop",
        divergence=(
            "Warned limit — the column becomes visible to SELECT *, changing that "
            "query's result shape."
        ),
    ),
    "UNIQUE-1053": _R(
        construct="PostgreSQL UNIQUE ... NULLS NOT DISTINCT (→ other engines)",
        reason=(
            "Only PostgreSQL 15+ has a NULLS NOT DISTINCT unique-constraint modifier "
            "(NULLs compare equal, so only one NULL row is allowed); every other "
            "engine's UNIQUE always treats NULLs as distinct."
        ),
        example_case="pg-unique-nulls-notdistinct",
        divergence=(
            "Warned limit — degrades to a plain UNIQUE; multiple NULL rows become "
            "allowed on the target."
        ),
    ),
    "UNIQUE-1054": _R(
        construct="Cascading referential action on a self-referencing FK (→ T-SQL)",
        reason=(
            "T-SQL rejects a cascading action on a self-referencing foreign "
            "key outright (error 1785 at CREATE TABLE time) — an engine "
            "restriction, not a missing feature."
        ),
        example_case="my-self-fk",
        divergence=(
            "Warned limit — downgraded to ON DELETE NO ACTION; emulate the "
            "cascade with an AFTER trigger."
        ),
    ),
    "UNIQUE-1055": _R(
        construct="Foreign-key ON DELETE SET DEFAULT referential action (→ Oracle)",
        reason=(
            "Oracle foreign keys support only CASCADE/SET NULL/NO ACTION — SET DEFAULT "
            "raises ORA-03001 ('unimplemented feature') if shipped verbatim."
        ),
        example_case="red2-pg-fk-ondelete-setdefault-oracle",
        divergence=(
            "Warned limit — the action is dropped (FK reverts to NO ACTION); emulate "
            "with an AFTER DELETE trigger if required."
        ),
    ),
    "UNIQUE-1056": _R(
        construct=(
            "T-SQL In-Memory OLTP table storage option(s) (MEMORY_OPTIMIZED / "
            "DURABILITY) (→ other engines)"
        ),
        reason=(
            "No other engine has an in-memory table storage mode; the option is a "
            "physical-storage clause with no logical effect on query results."
        ),
        example_case="tsql-drop5-MEMORY_OPTIM",
        divergence=(
            "Faithful (storage-only) — the table becomes a regular disk-based table "
            "with the same logical content."
        ),
    ),
    "UNIQUE-1057": _R(
        construct="MySQL table-level default COLLATE/CHARSET clause (→ other engines)",
        reason=(
            "Same underlying gap as UNIQUE-1051 but table-scoped: collation names are "
            "engine-specific and unresolvable without a live database connection."
        ),
        example_case="mysql-drop5-utf8mb4",
        divergence="Warned limit — string columns use the target's default collation.",
    ),
    "UNIQUE-1058": _R(
        construct=(
            "A non-portable CREATE VIEW modifier (e.g. SCHEMABINDING, ALGORITHM=, "
            "DEFINER=, SQL SECURITY) with no native form on the target"
        ),
        reason=(
            "These modifiers are single-engine syntax with no equivalent option "
            "elsewhere (MATERIALIZED is handled separately, natively, on "
            "Oracle/PostgreSQL, so it never reaches this drop)."
        ),
        example_case="red2-pg-matview-oracle-falsewarn",
        divergence=(
            "Warned limit — the modifier is dropped; the view's query and columns are "
            "otherwise faithful."
        ),
    ),
    "UNIQUE-1059": _R(
        construct="DROP SEQUENCE (→ MySQL)",
        reason=(
            "MySQL has no sequence object at all (identity is expressed only via "
            "AUTO_INCREMENT columns), so there is nothing for a DROP SEQUENCE to "
            "target."
        ),
        example_case=(
            "tests/integration/test_oracle_mysql_tail.py::TestDropSequenceMySql::test_mysql_degrades_to_documented_carrier"
        ),
        divergence=(
            "Warned limit — degrades to a documented carrier; the original statement "
            "is preserved as a comment."
        ),
    ),
    "UNIQUE-1060": _R(
        construct="DROP TYPE (→ MySQL)",
        reason=(
            "MySQL has no user-defined type in any form (no CREATE TYPE/DOMAIN "
            "equivalent), so a DROP TYPE has nothing to target."
        ),
        example_case=(
            "tests/integration/test_pg_source_wave1.py::TestMysqlUserTypesDegrade::test_drop_type_degrades_mysql"
        ),
        divergence=(
            "Warned limit — degrades to a documented carrier; the original statement "
            "is preserved."
        ),
    ),
    "UNIQUE-1061": _R(
        construct="A DROP INDEX <name> with no owning table (→ T-SQL / MySQL)",
        reason=(
            "T-SQL and MySQL both require the owning table in DROP INDEX (index names "
            "are table-scoped there); Oracle/PostgreSQL index names are schema-scoped, "
            "so a source statement from either carries no table for the target to "
            "require."
        ),
        example_case=(
            "tests/integration/test_ddl_rename_dropindex.py::test_drop_index_without_table_never_ships_invalid"
        ),
        divergence=(
            "Warned limit — degrades to a documented carrier rather than shipping a "
            "syntactically incomplete DROP INDEX."
        ),
    ),
    "UNIQUE-1062": _R(
        construct=(
            "A schema-scoped DROP TRIGGER <name> with no owning table (→ PostgreSQL)"
        ),
        reason=(
            "PostgreSQL trigger names are per-table (DROP TRIGGER requires ON "
            "<table>); T-SQL/MySQL/Oracle trigger names are schema-scoped, so a source "
            "statement from any of them carries no table to supply."
        ),
        example_case=(
            "tests/integration/test_pg_source_wave1.py::TestDropTriggerOnTable::test_sourceless_on_degrades_to_pg"
        ),
        divergence=(
            "Warned limit — degrades to a documented carrier; the original statement "
            "is preserved."
        ),
    ),
    "UNIQUE-1063": _R(
        construct=(
            "A construct with no cross-engine mapping, kept as a documented carrier "
            "(e.g. T-SQL AT TIME ZONE, or the T-SQL CLR spatial '::' method-call "
            "operator)"
        ),
        reason=(
            "The generic degrade path for a value Unique recognizes but cannot compute "
            "on another engine — used e.g. for AT TIME ZONE (Oracle/MySQL have no such "
            "operator; PostgreSQL/T-SQL's own session-tz-dependent display differs) "
            "and T-SQL's geometry/geography '::' static-method call (no other engine "
            "has CLR types)."
        ),
        example_case="ts-at-time-zone",
        divergence=(
            "Warned limit — degrades to NULL + annotation; valid only on the source "
            "engine."
        ),
    ),
    "UNIQUE-1064": _R(
        construct="Oracle bare SESSIONTIMEZONE global (→ other engines)",
        reason=(
            "SESSIONTIMEZONE reports the connecting session's own UTC offset — a "
            "per-session value with no fixed cross-engine equivalent; the mapped "
            "expression reports the TARGET session's own zone in its native format "
            "instead."
        ),
        example_case="ora-tz-funcs",
        divergence=(
            "Warned limit — the value is session-dependent on the target too and may "
            "not match the source session's zone."
        ),
    ),
    "UNIQUE-1065": _R(
        construct="CAST(... AS TIME) and other Oracle-absent value types",
        reason=(
            "Oracle has no bare TIME (or plain INTERVAL) type, so the value is "
            "kept as text with a documented carrier rather than an invalid "
            "cast."
        ),
        example_case="my-cast-time",
        divergence="Warned limit — value kept as text.",
    ),
    "UNIQUE-1066": _R(
        construct="MySQL JSON type / CAST(... AS JSON)",
        reason=(
            "MySQL's JSON type has no faithful cross-engine equivalent — T-SQL "
            "has no JSON type at all, and canonical JSON spacing differs on "
            "PostgreSQL/Oracle — so the value is kept as text."
        ),
        example_case="my-cast-json",
        divergence="Warned limit — value kept as text.",
    ),
    "UNIQUE-1067": _R(
        construct="PostgreSQL geometric type (point/line/…) cast or column",
        reason=(
            "PostgreSQL's geometric types have no cross-engine model (MySQL's "
            "spatial POINT is a different WKB type), so the value is kept as "
            "text."
        ),
        example_case="pg-cast-point",
        divergence="Warned limit — value kept as text.",
    ),
    "UNIQUE-1068": _R(
        construct=(
            "A PostgreSQL numeric NaN/Infinity literal cast to a numeric type (→ MySQL "
            "/ T-SQL / Oracle)"
        ),
        reason=(
            "Only PostgreSQL's numeric type has a NaN/Infinity value; "
            "MySQL/T-SQL/Oracle DECIMAL/NUMBER silently collapse a 'NaN' cast to 0, so "
            "the special value has no faithful representation there."
        ),
        example_case="pg-nan-cmp",
        divergence=(
            "Warned limit — the carrier documents that the value cannot be reproduced "
            "numerically on the target."
        ),
    ),
    "UNIQUE-1069": _R(
        construct="MySQL UNSIGNED integer type / CAST(... AS UNSIGNED)",
        reason=(
            "No other engine has an UNSIGNED integer type; the value is mapped "
            "to a signed NUMERIC/NUMBER, so unsigned wraparound semantics are "
            "not preserved."
        ),
        example_case="my-cast-convert",
        divergence="Warned limit — unsigned wraparound not preserved.",
    ),
    "UNIQUE-1071": _R(
        construct=(
            "A scalar subquery serialized via T-SQL FOR XML/JSON (→ other engines)"
        ),
        reason=(
            "FOR XML/JSON row-serialization inside a (SELECT ... FOR XML/JSON) scalar "
            "subquery has no cross-engine equivalent; dropping only the clause would "
            "ship the multi-column rows raw into a scalar context (ORA-00913 'too many "
            "values'), so the whole scalar degrades instead."
        ),
        example_case="ts-for-xml",
        divergence="Warned limit — degrades to NULL + annotation.",
    ),
    "UNIQUE-1073": _R(
        construct=(
            "MySQL date arithmetic on a non-datetime string literal (e.g. "
            "DATE_ADD('not-a-date', INTERVAL ...))"
        ),
        reason=(
            "MySQL's own date-arithmetic functions yield NULL when the first argument "
            "doesn't parse as a date/time value; folding the literal at transpile time "
            "reproduces that NULL rather than emitting an invalid cast on another "
            "engine."
        ),
        example_case="my-timestr-plus",
        divergence=(
            "Warned limit — the value folds to NULL to match MySQL's own behaviour."
        ),
    ),
    "UNIQUE-1074": _R(
        construct="MySQL DATE - DATE subtraction",
        reason=(
            "MySQL's DATE - DATE operator is a numeric YYYYMMDD subtraction (e.g. "
            "2020-03-01 - 2020-01-01 = 200), not a day count; the meaningful day-count "
            "value (60, matching every other engine's date subtraction) is emitted "
            "instead."
        ),
        example_case="my-date-diff-minus",
        divergence=(
            "Warned limit — normalized to a day count rather than MySQL's own YYYYMMDD "
            "arithmetic result."
        ),
    ),
    "UNIQUE-1075": _R(
        construct="timestamp - timestamp subtraction (→ T-SQL / MySQL)",
        reason=(
            "PostgreSQL/Oracle timestamp subtraction yields an INTERVAL; T-SQL and "
            "MySQL have no interval value type, so the difference is computed as a "
            "SECOND count via DATEDIFF/TIMESTAMPDIFF instead."
        ),
        example_case=(
            "tests/integration/test_challenge.py::TestTimestampDifferenceDegrade::test_tsql_and_mysql_degrade_with_warning"
        ),
        divergence=(
            "Warned limit — a SECOND count replaces the source's INTERVAL value (same "
            "information, different type)."
        ),
    ),
    "UNIQUE-1076": _R(
        construct=(
            "LISTAGG(...) WITHIN GROUP (...) OVER (...) — windowed string "
            "aggregation (Oracle)"
        ),
        reason=(
            "T-SQL STRING_AGG and MySQL GROUP_CONCAT can never carry an OVER "
            "clause, and PostgreSQL rejects an ORDER-BY aggregate used as a "
            "window function — there is no running-string-aggregate form to "
            "target."
        ),
        example_case="ora-listagg-over",
        divergence="Warned limit — degrades to a NULL value plus annotation.",
    ),
    "UNIQUE-1077": _R(
        construct="GROUPS window frame (PostgreSQL / Oracle)",
        reason=(
            "T-SQL and MySQL implement only ROWS and RANGE frame units; a "
            "GROUPS frame spans whole peer groups, and no ROWS/RANGE "
            "combination reproduces that boundary when the ORDER BY key has "
            "ties."
        ),
        example_case="pg-window-groups-frame",
        divergence=(
            "Warned limit on T-SQL/MySQL — degrades to a NULL carrier; "
            "faithful on Oracle/PostgreSQL."
        ),
    ),
    "UNIQUE-1078": _R(
        construct=(
            "A window frame EXCLUDE clause (CURRENT ROW / GROUP / TIES) (→ T-SQL / "
            "MySQL)"
        ),
        reason=(
            "T-SQL and MySQL implement no EXCLUDE option on a window frame at all, and "
            "there is no faithful ROWS/RANGE rewrite that reproduces excluding "
            "specific peer rows from the frame."
        ),
        example_case="red2-pg-window-exclude-current",
        divergence=(
            "Warned limit on T-SQL/MySQL — degrades to a NULL carrier; faithful on "
            "PostgreSQL/Oracle, which support EXCLUDE natively."
        ),
    ),
    "UNIQUE-1079": _R(
        construct=(
            "DATEADD/DATEDIFF with a unit no target engine expresses (e.g. "
            "NANOSECOND) (→ PostgreSQL/Oracle/MySQL)"
        ),
        reason=(
            "T-SQL's DATEADD/DATEDIFF accept any real datepart, including "
            "ones finer than any other engine's date-arithmetic "
            "vocabulary (no engine besides T-SQL has a NANOSECOND unit); "
            "there is no unit to translate to, so the value cannot be "
            "computed."
        ),
        example_case=(
            "tests/integration/test_challenge.py::TestDateAddDiffUnits::"
            "test_unmapped_diff_unit_degrades_not_invalid"
        ),
        divergence=(
            "Warned limit — degrades to a NULL carrier naming the unit " "for review."
        ),
    ),
    "UNIQUE-1080": _R(
        construct="Sequence CURRVAL — current value without advancing (→ T-SQL)",
        reason=(
            "T-SQL has NEXT VALUE FOR but no CURRVAL; there is no way to read a "
            "sequence's current value without advancing it."
        ),
        example_case="ora-seq-use",
        divergence="Warned limit — capture NEXT VALUE FOR in a variable instead.",
    ),
    "UNIQUE-1081": _R(
        construct=(
            "A day-of-week value mapped to T-SQL DATEPART(WEEKDAY, ...) " "(→ T-SQL)"
        ),
        reason=(
            "T-SQL's WEEKDAY datepart is not a fixed numbering — it "
            "shifts with the session's @@DATEFIRST setting — while every "
            "source engine's own day-of-week function (MySQL DAYOFWEEK, "
            "PostgreSQL DOW, Oracle's anchor formula) is fixed Sunday=1; "
            "the mapping is only correct under T-SQL's untouched default."
        ),
        example_case=(
            "tests/integration/test_challenge.py::"
            "TestFalseUnmapMappedSymmetrically::"
            "test_mysql_dayofweek_maps_per_engine"
        ),
        divergence=(
            "Faithful when @@DATEFIRST is left at its default "
            "(7/Sunday); otherwise the value shifts."
        ),
    ),
    "UNIQUE-1082": _R(
        construct="An empty-string result on Oracle ('' ≡ NULL)",
        reason=(
            "Oracle has no on-disk representation for an empty string distinct "
            "from NULL — an empty-string result becomes NULL — so a value that "
            "is '' on other engines cannot be reproduced there."
        ),
        example_case="pg-repeat-negative",
        divergence="Warned limit — the empty string surfaces as Oracle NULL.",
    ),
    "UNIQUE-1083": _R(
        construct="DATEPART(WEEKDAY, d) (T-SQL)",
        reason=(
            "DATEPART(WEEKDAY) depends on the session @@DATEFIRST setting, "
            "which Unique cannot observe at transpile time; the conversion "
            "assumes the T-SQL default (Sunday = 1)."
        ),
        example_case="reda-ts-datepart-weekday",
        divergence=(
            "Warned — correct under the default @@DATEFIRST = 7; a session that "
            "changed DATEFIRST will see a different result."
        ),
    ),
    "UNIQUE-1084": _R(
        construct=(
            "Oracle ROUND(date, fmt) — a date rounded to the nearest fmt boundary (→ "
            "other engines)"
        ),
        reason=(
            "No other engine has a nearest-boundary date-rounding function; only "
            "Oracle's own ROUND(date, fmt) computes this, so the general case (any "
            "fmt) has no cross-engine formula."
        ),
        example_case="red2-ora-round-date-fmt",
        divergence=(
            "Warned limit — degrades to a NULL carrier; not computed off Oracle."
        ),
    ),
    "UNIQUE-1085": _R(
        construct=(
            "Oracle TRUNC(date, fmt) with a format model that has no portable "
            "truncation (e.g. 'W' week-of-month)"
        ),
        reason=(
            "Most Oracle TRUNC format models map to a portable truncation unit (day, "
            "month, year, ISO week, ...), but a few (like 'W', week-of-the-month) have "
            "no equivalent boundary on any other engine."
        ),
        example_case="red2-ora-trunc-format-unmapped",
        divergence=(
            "Warned limit — degrades to a NULL carrier off Oracle; native TRUNC is "
            "kept on Oracle."
        ),
    ),
    "UNIQUE-1087": _R(
        construct=(
            "Oracle INSTR with a non-literal occurrence count or a non-literal "
            "backward (negative-start) search"
        ),
        reason=(
            "INSTR's occurrence/backward-search semantics fold to the engine-agnostic "
            "computed value only when every argument is a literal (at transpile time); "
            "a non-literal (column/expression) argument cannot be folded, and no other "
            "engine's positional-search function reproduces Oracle's "
            "occurrence/backward semantics directly."
        ),
        example_case=(
            "tests/integration/test_challenge.py::TestLiteralFolds::test_oracle_instr_nonliteral_degrades"
        ),
        divergence=(
            "Warned limit — degrades to a NULL carrier for the non-literal case; "
            "literal arguments still fold to the correct value."
        ),
    ),
    "UNIQUE-1088": _R(
        construct="MySQL UpdateXML() (→ other engines)",
        reason=(
            "UpdateXML has no cross-engine equivalent — PostgreSQL lacks it, "
            "and T-SQL .modify() / Oracle UPDATEXML differ in shape and "
            "semantics."
        ),
        example_case="my-xml-fns",
        divergence="Warned limit.",
    ),
    "UNIQUE-1089": _R(
        construct="COLLATION(x) — the collation name of a value (→ other engines)",
        reason=(
            "Collation names are engine-specific catalog identifiers (e.g. MySQL's "
            "utf8mb4_0900_ai_ci vs Oracle's NLS-based names) with no cross-engine "
            "mapping, even though the function itself exists on multiple engines."
        ),
        example_case="my-collation-fn",
        divergence=(
            "Warned limit — the source's engine-specific collation name is preserved "
            "but will not match the target's naming."
        ),
    ),
    "UNIQUE-1090": _R(
        construct="Oracle REGEXP_SUBSTR capture-group extraction (6th arg) (→ MySQL)",
        reason=(
            "MySQL's REGEXP_SUBSTR has no capture-group argument, so the "
            "sub-group extraction cannot be expressed; the portable "
            "(str, pat, pos, occ) subset is emitted."
        ),
        example_case="ora-regexp-group",
        divergence="Warned limit — capture-group extraction not reproduced.",
    ),
    "UNIQUE-1091": _R(
        construct="Oracle TRANSLATE(s, from, to) (→ MySQL)",
        reason=(
            "TRANSLATE is native on PostgreSQL/T-SQL, but MySQL has no TRANSLATE "
            "function; a nested-REPLACE emulation is order-dependent (each REPLACE can "
            "rematch a previous substitution's output) and is not equivalent to "
            "TRANSLATE's simultaneous single-pass character mapping."
        ),
        example_case="ora-translate3",
        divergence=(
            "Warned limit — degrades to a NULL carrier on MySQL; native and faithful "
            "on PostgreSQL/T-SQL."
        ),
    ),
    "UNIQUE-1092": _R(
        construct="SUBSTRING(x FROM POSIX-regex-pattern) (→ T-SQL)",
        reason=(
            "T-SQL has no POSIX regular-expression engine, so a POSIX-pattern "
            "SUBSTRING (native on Oracle REGEXP_SUBSTR / MySQL) has no equivalent "
            "there."
        ),
        example_case="pg-substring-regex",
        divergence=(
            "Warned limit — degrades to a NULL carrier on T-SQL; faithful on "
            "Oracle/MySQL via REGEXP_SUBSTR."
        ),
    ),
    "UNIQUE-1093": _R(
        construct=(
            "SUBSTRING(x FROM SIMILAR-TO-pattern FOR escape) — the SQL-standard regex "
            "form"
        ),
        reason=(
            "The SQL-standard SIMILAR TO pattern syntax uses different metacharacters "
            '(%, _, #"..."# capture markers) than POSIX regex, so no faithful '
            "cross-engine rewrite exists on engines whose regex functions expect POSIX "
            "syntax."
        ),
        example_case="pg-substring-escape",
        divergence="Warned limit — degrades to a NULL carrier.",
    ),
    "UNIQUE-1094": _R(
        construct="An empty-string function result on Oracle (e.g. SUBSTR yielding '')",
        reason=(
            "The same underlying limit as Oracle's NULL-equals-empty-string storage "
            "(UNIQUE-1082/1207), applied to a computed (not stored) empty-string "
            "result — Oracle collapses it to NULL at the point of computation too."
        ),
        example_case="my-fsubstr",
        divergence="Warned limit — the empty string surfaces as Oracle NULL.",
    ),
    "UNIQUE-1095": _R(
        construct=(
            "MySQL VALUES(col) used outside an INSERT ... ON DUPLICATE KEY UPDATE "
            "statement"
        ),
        reason=(
            "MySQL's VALUES(col) function only has meaning inside the ON DUPLICATE KEY "
            "UPDATE clause of the very INSERT it appears in (reading the row that "
            "would have been inserted); used elsewhere (e.g. inside a stored "
            "procedure's ordinary UPDATE) it is NULL on MySQL itself, so the "
            "transpiler reproduces that NULL."
        ),
        example_case=(
            "tests/integration/test_pg_source_wave1.py::TestWave223ValuesFnOutfile::test_values_fn_null_oracle"
        ),
        divergence="Faithful — matches MySQL's own out-of-context NULL behaviour.",
    ),
    "UNIQUE-1096": _R(
        construct="EXTRACT(EPOCH FROM interval) (PostgreSQL)",
        reason=(
            "T-SQL and MySQL have no interval value type, so the epoch (total "
            "seconds) of an interval value has no portable equivalent."
        ),
        example_case="pg-epoch",
        divergence=(
            "Warned limit — degrades to NULL + annotation (EPOCH FROM a "
            "timestamp is still computed)."
        ),
    ),
    "UNIQUE-1097": _R(
        construct="EXTRACT(MICROSECONDS FROM TIME) (→ Oracle)",
        reason=(
            "Oracle has no TIME type, so the microseconds field of a TIME "
            "value has no Oracle equivalent."
        ),
        example_case="pg-frac-seconds",
        divergence="Warned limit.",
    ),
    "UNIQUE-1098": _R(
        construct=(
            "PostgreSQL format() with a %I/%L specifier, a width, or a positional "
            "argument (→ other engines)"
        ),
        reason=(
            "Only the plain %s-only template has a portable rewrite (string "
            "concatenation); %I (quoted identifier) and %L (quoted literal) "
            "specifiers, width modifiers and positional (%1$s) arguments have no "
            "equivalent formatting primitive on other engines."
        ),
        example_case=(
            "tests/integration/test_challenge.py::TestFormatFunc::test_complex_spec_degrades"
        ),
        divergence=(
            "Warned limit — degrades to a NULL carrier; a %s-only template still "
            "rewrites faithfully."
        ),
    ),
    "UNIQUE-1099": _R(
        construct="PostgreSQL sha256()/sha512() (→ other engines)",
        reason=(
            "PostgreSQL's sha256/sha512 return a bytea digest, while every other "
            "engine's equivalent hash function returns a hex-encoded string — the "
            "underlying digest is identical, but the representation differs and cannot "
            "be reconciled without an explicit encode() the source SQL doesn't have."
        ),
        example_case="pg-hash-fns",
        divergence=(
            "Warned limit — degrades to a NULL carrier; md5() and other hash functions "
            "with matching representations still map faithfully."
        ),
    ),
    "UNIQUE-1100": _R(
        construct="MySQL CHAR(n) as a numeric-to-byte-string function",
        reason=(
            "MySQL's CHAR(n) returns a multi-byte byte string (CHAR(256) = the "
            "2-byte string 0x0100), not a single Unicode code point like "
            "CHR/NCHAR, so the two cannot be equated."
        ),
        example_case="my-char-256",
        divergence=(
            "Warned limit — carrier flags the byte-string vs code-point " "difference."
        ),
    ),
    "UNIQUE-1101": _R(
        construct=(
            "A data-modifying CTE, e.g. WITH ins AS (INSERT ... RETURNING "
            "...) SELECT ... (PostgreSQL) → T-SQL"
        ),
        reason=(
            "T-SQL's WITH only introduces read-only query CTEs — an "
            "INSERT/UPDATE/DELETE/MERGE inside a WITH body is invalid "
            "there — so a data-modifying CTE has no T-SQL spelling at all."
        ),
        example_case=(
            "tests/unit/core/test_ir_first_families.py::TestZeroPushW7Batch::"
            "test_data_modifying_cte_carrier_tsql"
        ),
        divergence="Warned limit — statement preserved as a comment.",
    ),
    "UNIQUE-1103": _R(
        construct="SELECT ... FOR SHARE — a shared row lock (→ Oracle)",
        reason=(
            "Oracle SELECT locking is FOR UPDATE (exclusive) only — it has no "
            "shared-row-lock mode — so the shared lock cannot be reproduced."
        ),
        example_case="my-for-share",
        divergence="Warned limit — the shared lock is dropped.",
    ),
    "UNIQUE-1104": _R(
        construct="Oracle FOR UPDATE WAIT <n> — a bounded lock wait",
        reason=(
            "PostgreSQL/MySQL offer only FOR UPDATE / NOWAIT / SKIP LOCKED, "
            "with no bounded-wait timeout, so the WAIT <n> bound has no "
            "equivalent."
        ),
        example_case="ora-forupdate-wait",
        divergence="Warned limit — it blocks with the target's default behavior.",
    ),
    "UNIQUE-1105": _R(
        construct="Oracle FOR UPDATE OF <column> (→ PostgreSQL/MySQL)",
        reason=(
            "Oracle's FOR UPDATE OF names a COLUMN, selecting which joined "
            "table's rows to lock via the column's owning table; "
            "PostgreSQL and MySQL's FOR UPDATE OF instead takes a "
            "TABLE/alias name directly — an incompatible argument shape, "
            "not just a renaming."
        ),
        example_case="reda-ora-forupdate-of-col",
        divergence=(
            "Warned limit — the source's column name is dropped rather "
            "than leaked unchanged into a table-name position."
        ),
    ),
    "UNIQUE-1106": _R(
        construct=(
            "CREATE INDEX over an expression, e.g. CREATE INDEX ix ON t "
            "(a * 2) (→ T-SQL)"
        ),
        reason=(
            "T-SQL has no expression/functional index at all — an index "
            "can only cover column names — so there is no CREATE INDEX "
            "form to target; a computed column plus an index on it is "
            "the closest workaround, but it is a schema change the "
            "transpiler cannot make unilaterally."
        ),
        example_case="ora-functional-index",
        divergence=(
            "Warned limit — statement preserved as a comment; add a "
            "computed column and index it by hand."
        ),
    ),
    "UNIQUE-1107": _R(
        construct=(
            "T-SQL SELECT IDENTITY(type, seed, incr) ... INTO t2 (→ " "other engines)"
        ),
        reason=(
            "No engine has an IDENTITY() scalar function; the "
            "row-numbering values it produces are reproduced with "
            "ROW_NUMBER() so the id column's values match, but the "
            "identity/auto-increment property (a schema attribute) has "
            "no spelling inside a CREATE-TABLE-AS-SELECT on any target."
        ),
        example_case="reda-ts-select-into-identity",
        divergence=(
            "Faithful values, warned limit on the property — id values "
            "match; the column is a plain (non-auto-increment) column "
            "on the target."
        ),
    ),
    "UNIQUE-1108": _R(
        construct=(
            "ADD CONSTRAINT ... NOT VALID (PostgreSQL, deferred "
            "validation) → T-SQL/Oracle/MySQL"
        ),
        reason=(
            "Only PostgreSQL can add a constraint without validating "
            "existing rows against it immediately; T-SQL, Oracle and "
            "MySQL all validate an added constraint at ADD time, with no "
            "deferred-validation mode to opt into."
        ),
        example_case="pg-alter-notvalid",
        divergence=(
            "Warned limit — the constraint definition is identical; the "
            "target validates existing rows immediately instead of "
            "deferring."
        ),
    ),
    "UNIQUE-1109": _R(
        construct=(
            "TRUNCATE ... CASCADE (PostgreSQL, also truncates FK-dependent "
            "tables) → MySQL/T-SQL"
        ),
        reason=(
            "Only Oracle's TRUNCATE has a CASCADE option matching "
            "PostgreSQL's; MySQL and T-SQL TRUNCATE truncate only the "
            "named table, with no mechanism to also truncate its "
            "FK-dependent tables in one statement."
        ),
        example_case="pg-truncate-restart",
        divergence=(
            "Warned limit — only the named table is truncated; truncate "
            "dependent tables explicitly."
        ),
    ),
    "UNIQUE-1110": _R(
        construct=(
            "ALTER COLUMN ... TYPE t USING <non-trivial expression> "
            "(PostgreSQL) → T-SQL"
        ),
        reason=(
            "T-SQL's ALTER COLUMN has no USING conversion-expression "
            "clause at all — it can only re-cast to the new type using "
            "the engine's own implicit conversion, with no way to run an "
            "arbitrary expression over the existing data during the ALTER."
        ),
        example_case=(
            "tests/integration/test_pg_source_wave1.py::"
            "TestWave199CteDeleteUsingAlterUsing::"
            "test_alter_using_expression_carriers"
        ),
        divergence=(
            "Warned limit — statement preserved as a comment; convert the "
            "data manually."
        ),
    ),
    "UNIQUE-1111": _R(
        construct=(
            "PostgreSQL ALTER COLUMN ... {SET|DROP} NOT NULL on a column "
            "the script never declares (→ MySQL/T-SQL)"
        ),
        reason=(
            "MySQL's MODIFY and T-SQL's ALTER COLUMN both require "
            "re-stating the column's full type in the same clause that "
            "changes its nullability (PostgreSQL's own form needs only "
            "the constraint); without the script's own CREATE TABLE to "
            "harvest that type from, there is nothing to re-state."
        ),
        example_case=(
            "tests/integration/test_challenge.py::"
            "TestCrossStatementMetadata::test_unknown_column_degrades_warned"
        ),
        divergence=(
            "Warned limit — degrades to a documented carrier rather "
            "than guessing a type."
        ),
    ),
    "UNIQUE-1112": _R(
        construct="ADD COLUMN ... GENERATED ALWAYS AS IDENTITY / SERIAL (→ MySQL)",
        reason=(
            "MySQL's only identity form is AUTO_INCREMENT, which MySQL "
            "additionally requires to be a key (error 1075 otherwise) — a "
            "constraint PostgreSQL/Oracle identity columns do not share — "
            "so a UNIQUE index must be synthesized alongside the column."
        ),
        example_case="pg-add-identity",
        divergence=(
            "Faithful, with an added UNIQUE index noted as a "
            "MySQL-specific requirement, not part of the source schema."
        ),
    ),
    "UNIQUE-1113": _R(
        construct="A GIN/GiST/BRIN index (PostgreSQL) → T-SQL/MySQL/Oracle",
        reason=(
            "GIN/GiST/BRIN are PostgreSQL-specific access methods "
            "(inverted, generalized-search-tree, block-range) with no "
            "equivalent index type on the other three engines — the "
            "choice of access method is inherently engine-specific, "
            "unlike a plain B-tree index."
        ),
        example_case="pg-gin-jsonb",
        divergence=(
            "Warned limit — the index is omitted; queries that relied on "
            "it run unindexed."
        ),
    ),
    "UNIQUE-1114": _R(
        construct=(
            "An expression index over a column that maps to a LOB type on " "the target"
        ),
        reason=(
            "A source TEXT/CLOB-mapped column used inside an index "
            "expression is invalid on the target once the type maps to a "
            "LOB (Oracle ORA-02327 forbids a LOB in a function-based "
            "index; MySQL's functional-index grammar has the same "
            "restriction)."
        ),
        example_case="pg-expr-index",
        divergence=(
            "Warned limit — the index is omitted; queries that relied on "
            "it run unindexed."
        ),
    ),
    "UNIQUE-1115": _R(
        construct=(
            "CREATE INDEX CONCURRENTLY (PostgreSQL's non-locking index "
            "build) → T-SQL/MySQL"
        ),
        reason=(
            "CONCURRENTLY is a PostgreSQL build-strategy option (avoids "
            "locking the table during the build); T-SQL and MySQL have no "
            "matching keyword — the resulting index is identical, only "
            "the build-time locking behavior differs."
        ),
        example_case="postgresql-drop2-CONCURRENTLY",
        divergence=(
            "Faithful in result; the index is built with the target's "
            "default (locking) behavior instead."
        ),
    ),
    "UNIQUE-1116": _R(
        construct=(
            "SET @@var = ... — a MySQL system-variable assignment via the "
            "@@ form (→ PostgreSQL/T-SQL/Oracle)"
        ),
        reason=(
            "MySQL's @@ system variables (session or global) are "
            "engine-local tuning knobs (sql_mode, server_id, ...) with no "
            "meaning on any other engine — every other engine either "
            "lacks the setting or spells session configuration a "
            "completely different way."
        ),
        example_case=(
            "tests/integration/test_pg_source_wave1.py::"
            "TestMysqlSessionKnobsDegrade::test_knob_degrades"
        ),
        divergence=(
            "Warned limit — statement preserved as a comment; configure "
            "the session natively on the target."
        ),
    ),
    "UNIQUE-1118": _R(
        construct="CREATE TEMPORARY SEQUENCE (PostgreSQL) → T-SQL/MySQL/Oracle",
        reason=(
            "A session-scoped (TEMPORARY) sequence exists only on "
            "PostgreSQL; T-SQL and Oracle sequences are always permanent "
            "schema objects, and MySQL has no sequences at all, so there "
            "is no target form that preserves the session-scoping."
        ),
        example_case=(
            "tests/unit/core/test_ir_first_families.py::"
            "TestZeroPushZ4bBatch::test_temporary_sequence_carriers"
        ),
        divergence="Warned limit — statement preserved as a comment.",
    ),
    "UNIQUE-1119": _R(
        construct="CREATE SEQUENCE (→ MySQL)",
        reason=(
            "MySQL has no sequence object at all; an AUTO_INCREMENT "
            "column is the closest idiom, but it is a column property, "
            "not a free-standing, shareable object the way a sequence is, "
            "so CREATE SEQUENCE has no direct MySQL statement to become."
        ),
        example_case="red2-pg-nextval-false-unmap",
        divergence=(
            "Warned limit — statement preserved as a comment; use an "
            "AUTO_INCREMENT column instead."
        ),
    ),
    "UNIQUE-1122": _R(
        construct="USE <database> (T-SQL/MySQL) → PostgreSQL/Oracle",
        reason=(
            "USE switches the active database within a single connection "
            "on T-SQL and MySQL; PostgreSQL has no SQL-level equivalent "
            "(only the psql client meta-command \\c, which reconnects) "
            "and Oracle has none at all (a schema is a database user, "
            "selected at connect time)."
        ),
        example_case=(
            "tests/integration/test_cross_dialect.py::TestCrossDialectDDL::"
            "test_use_statement_documented_where_unsupported"
        ),
        divergence=(
            "Warned limit — statement preserved as a comment; connect to "
            "the target database/schema instead."
        ),
    ),
    "UNIQUE-1123": _R(
        construct=(
            "ALTER COLUMN ... SET STORAGE {PLAIN|EXTERNAL|EXTENDED|MAIN} "
            "(PostgreSQL) → T-SQL/MySQL/Oracle"
        ),
        reason=(
            "SET STORAGE tunes PostgreSQL's internal TOAST "
            "compression/out-of-line storage strategy for a column — an "
            "engine-internal physical-storage knob with no logical effect "
            "on query results and no equivalent concept on any other "
            "engine."
        ),
        example_case=(
            "tests/integration/test_pg_source_wave1.py::TestWave132Batch::"
            "test_set_storage_degrades_off_pg"
        ),
        divergence=(
            "Faithful in result (storage-only); statement preserved as a "
            "comment off PostgreSQL."
        ),
    ),
    "UNIQUE-1124": _R(
        construct=(
            "A recursive CTE's SEARCH DEPTH/BREADTH FIRST BY ... SET ... "
            "/ CYCLE clause (PostgreSQL 14+) → T-SQL/MySQL/Oracle"
        ),
        reason=(
            "SEARCH/CYCLE are PostgreSQL-only recursive-CTE "
            "ordering/cycle-detection clauses (SQL:1999 features "
            "PostgreSQL adopted in 14); no other supported engine's "
            "recursive CTE grammar has them, and sqlglot itself cannot "
            "parse them outside PostgreSQL."
        ),
        example_case=(
            "tests/integration/test_pg_source_wave1.py::"
            "TestWave191PgSearchCte::test_search_clause_carrier_mysql"
        ),
        divergence=(
            "Faithful on PostgreSQL; statement preserved as a comment " "elsewhere."
        ),
    ),
    "UNIQUE-1125": _R(
        construct=(
            "A MERGE outside the canonical single-UPDATE/single-INSERT "
            "shape (→ MySQL)"
        ),
        reason=(
            "MySQL has no MERGE statement; only the canonical two-branch "
            "shape has a faithful INSERT ... ON DUPLICATE KEY UPDATE "
            "rewrite (UNIQUE-1001) — any other clause combination "
            "(multiple conditional branches, a DELETE branch, NOT "
            "MATCHED BY SOURCE) has no MySQL equivalent to fall back to."
        ),
        example_case=(
            "tests/integration/test_cross_dialect.py::TestDDLPassthrough::"
            "test_merge_to_mysql_documented"
        ),
        divergence="Warned limit — statement preserved as a comment.",
    ),
    "UNIQUE-1126": _R(
        construct=(
            "A WITH-clause (CTE) feeding an UPDATE/DELETE — either "
            "updating *through* the CTE name, or a data-modifying CTE "
            "body (WITH x AS (INSERT/UPDATE/DELETE ... RETURNING) SELECT "
            "...) — transpiled cross-engine"
        ),
        reason=(
            "Data-modifying CTE bodies are PostgreSQL-only syntax; "
            "updating through a CTE name is a T-SQL-only capability (no "
            "other engine resolves the CTE as an updatable view); and "
            "Oracle additionally rejects a WITH clause on UPDATE/DELETE "
            "outright, so none of the three shapes has a mechanical, "
            "engine-agnostic rewrite."
        ),
        example_case=(
            "tests/unit/core/test_emit_mutation_survivors.py::"
            "TestCteDmlGate::test_oracle_no_with_on_dml_carrier"
        ),
        divergence="Warned limit — statement preserved as a comment.",
    ),
    "UNIQUE-1127": _R(
        construct="BEGIN TRANSACTION (T-SQL) → Oracle",
        reason=(
            "Oracle has no explicit 'start transaction' statement — a "
            "transaction begins implicitly with the first DML — so an "
            "explicit BEGIN TRANSACTION has nothing to map to and is "
            "simply redundant on Oracle, not an error to reproduce."
        ),
        example_case=(
            "tests/integration/test_challenge.py::TestTsqlBeginTransaction::"
            "test_oracle_drops_with_warning"
        ),
        divergence=(
            "Faithful — Oracle opens the same transaction implicitly on "
            "the first DML statement that follows."
        ),
    ),
    "UNIQUE-1128": _R(
        construct="START TRANSACTION READ ONLY|READ WRITE (MySQL) → T-SQL",
        reason=(
            "T-SQL's BEGIN TRANSACTION has no access-mode clause at all "
            "— unlike MySQL/PostgreSQL, which accept READ ONLY/READ "
            "WRITE on the opener — so the requested mode has nothing to "
            "map to."
        ),
        example_case=(
            "tests/integration/test_challenge.py::TestSetTransactionModes::"
            "test_tsql_mode_noted"
        ),
        divergence=(
            "Warned limit — the transaction opens as a normal (read/"
            "write) transaction; the READ ONLY/WRITE intent is dropped."
        ),
    ),
    "UNIQUE-1132": _R(
        construct=(
            "SET TRANSACTION ISOLATION LEVEL <lvl> READ ONLY|READ WRITE "
            "— combined isolation + access mode (PostgreSQL) → T-SQL"
        ),
        reason=(
            "T-SQL's SET TRANSACTION has no READ ONLY/READ WRITE "
            "access-mode clause at all — only ISOLATION LEVEL is "
            "expressible — so the access-mode half of a combined "
            "PostgreSQL statement has no T-SQL spelling."
        ),
        example_case=(
            "tests/integration/test_pg_source_wave1.py::"
            "TestPgSetTransactionAccessMode::"
            "test_combined_tsql_keeps_isolation_drops_access_mode_with_warning"
        ),
        divergence=(
            "Warned limit — the isolation level is kept faithfully; the "
            "access mode is dropped."
        ),
    ),
    "UNIQUE-1133": _R(
        construct=(
            "A bare SET TRANSACTION READ ONLY|READ WRITE with no "
            "isolation level (PostgreSQL) → T-SQL"
        ),
        reason=(
            "T-SQL's SET TRANSACTION expresses only ISOLATION LEVEL, "
            "never an access mode; with no isolation level present in "
            "the source either, there is nothing left in the statement "
            "that has a T-SQL spelling at all."
        ),
        example_case=(
            "tests/integration/test_pg_source_wave1.py::"
            "TestPgSetTransactionAccessMode::"
            "test_bare_access_mode_tsql_degrades_with_warning"
        ),
        divergence=(
            "Warned limit — the whole statement is dropped (nothing to "
            "keep); original preserved as a comment."
        ),
    ),
    "UNIQUE-1134": _R(
        construct=(
            "Oracle CONNECT BY / START WITH hierarchical query (→ "
            "PostgreSQL/MySQL/T-SQL), outside the shapes the automatic "
            "recursive-CTE rewrite covers"
        ),
        reason=(
            "CONNECT BY has no native equivalent on the other three "
            "engines; a WITH RECURSIVE CTE is the standard rewrite, but "
            "it must be constructed by hand for shapes the automatic "
            "CONNECT-BY-to-CTE conversion does not model, since a "
            "mechanical rewrite risks an incorrect recursion base or join."
        ),
        example_case=(
            "tests/unit/core/test_no_silent_loss.py::TestNoSilentLoss::"
            "test_connect_by_to_postgresql_signals_warning"
        ),
        divergence=(
            "Warned limit — statement preserved as a comment; rewrite as "
            "a WITH RECURSIVE CTE by hand."
        ),
    ),
    "UNIQUE-1136": _R(
        construct=(
            "An INSERT combining RETURNING and ON CONFLICT DO UPDATE in "
            "one statement (PostgreSQL) → MySQL"
        ),
        reason=(
            "MySQL has neither RETURNING nor a named-target upsert "
            "clause; with both present at once there is no partial "
            "mapping to fall back to (RETURNING alone would map to a "
            "follow-up SELECT, ON CONFLICT alone to INSERT ... ON "
            "DUPLICATE KEY UPDATE, but the combination needs a "
            "MERGE-like statement plus result capture that MySQL cannot "
            "express)."
        ),
        example_case=(
            "tests/integration/test_pg_source_wave1.py::"
            "TestOnConflictMysqlAndEStrings::"
            "test_returning_on_conflict_mysql_degrades"
        ),
        divergence=(
            "Warned limit — statement preserved as a comment; rewrite as "
            "an upsert with a separate result-capturing SELECT."
        ),
    ),
    "UNIQUE-1137": _R(
        construct="T-SQL OUTPUT ... INTO <table> redirect (→ PostgreSQL)",
        reason=(
            "PostgreSQL's RETURNING only returns a result set to the caller; "
            "it has no INTO <table> redirect form, so the redirect cannot be "
            "expressed in a plain INSERT."
        ),
        example_case="reda-ts-output-into",
        divergence=(
            "Warned limit — the INTO redirect is dropped; the base DML and "
            "plain RETURNING are faithful."
        ),
    ),
    "UNIQUE-1138": _R(
        construct="UPDATE ... FROM ... RETURNING (PostgreSQL) → Oracle",
        reason=(
            "Oracle has neither UPDATE ... FROM (needs a correlated "
            "subquery or MERGE rewrite instead) nor a top-level RETURNING "
            "(PL/SQL-only, ORA-63809 standalone) — with both present at "
            "once in the same statement, there is no single Oracle "
            "statement shape left that can carry both the join and the "
            "returned columns."
        ),
        example_case=(
            "tests/integration/test_pg_source_wave1.py::"
            "TestWave206OracleReturningShapes::"
            "test_returning_update_from_carrier_oracle"
        ),
        divergence="Warned limit — statement preserved as a comment.",
    ),
    "UNIQUE-1139": _R(
        construct="A top-level OUTPUT / RETURNING result set (→ Oracle)",
        reason=(
            "Oracle's RETURNING is PL/SQL-only — it must target INTO bind "
            "variables and cannot stand alone in a plain SQL statement "
            "(ORA-63809) — so a standalone OUTPUT/RETURNING has no Oracle "
            "equivalent."
        ),
        example_case="reda-ts-output-into",
        divergence=(
            "Warned limit — the DML runs; the returned result set is "
            "documented, not produced."
        ),
    ),
    "UNIQUE-1140": _R(
        construct="OUTPUT/RETURNING on an INSERT/UPDATE/DELETE (→ MySQL)",
        reason=(
            "MySQL has no clause that returns affected-row values "
            "alongside a data-modifying statement — LAST_INSERT_ID() only "
            "ever returns the last auto-increment value, not arbitrary "
            "column values, and there is no set-returning DML form at all."
        ),
        example_case=(
            "tests/integration/test_procedural.py::TestOutputClauseToMySQL::"
            "test_output_into_var_is_documented_not_returning"
        ),
        divergence=(
            "Warned limit — the DML itself runs faithfully; the "
            "OUTPUT/RETURNING result set is documented, not produced."
        ),
    ),
    "UNIQUE-1142": _R(
        construct=(
            "T-SQL MERGE with a MATCHED UPDATE and a conditional MATCHED "
            "DELETE whose condition reads a column the UPDATE assigns (→ "
            "Oracle)"
        ),
        reason=(
            "Oracle folds a conditional MATCHED UPDATE/DELETE pair into "
            "one UPDATE (CASE-guarded) plus a trailing DELETE WHERE, but "
            "Oracle evaluates that DELETE WHERE against post-update "
            "values; when the DELETE's own condition reads a column the "
            "UPDATE just wrote, the fold would delete rows the source "
            "MERGE keeps, so the whole statement degrades rather than "
            "ship silently wrong rows."
        ),
        example_case=(
            "tests/integration/test_challenge.py::"
            "TestMergeConditionalDeleteFoldSafety::"
            "test_unsafe_delete_on_updated_column_degrades"
        ),
        divergence=(
            "Warned limit — the whole MERGE is preserved as a comment; "
            "rewrite the two-clause fold by hand, preserving Oracle's "
            "post-update DELETE WHERE evaluation order."
        ),
    ),
    "UNIQUE-1141": _R(
        construct=(
            "MERGE WHEN [NOT] MATCHED THEN DO NOTHING (PostgreSQL) → T-SQL/"
            "Oracle, either with an action type sqlglot models but the "
            "MERGE-clause carve-out doesn't recognize, or where carving out "
            "the DO NOTHING clause leaves no action of that match kind at "
            "all"
        ),
        reason=(
            "T-SQL/Oracle have no DO NOTHING merge action; the normal "
            "rewrite folds an unconditional DO NOTHING into a NOT (...) "
            "condition on every later same-kind clause (first-match-wins "
            "semantics), but that fold has nothing to attach to when "
            "DO NOTHING was the ONLY clause of its match kind (the whole "
            "MERGE reduces to no action for that kind) or when the merge "
            "action itself is one the carve-out does not recognize as "
            "either DELETE or DO NOTHING."
        ),
        example_case=(
            "tests/integration/test_challenge.py::TestMergeDoNothingCarveOut::"
            "test_unknown_var_action_degrades"
        ),
        divergence="Warned limit — statement preserved as a comment.",
    ),
    "UNIQUE-1143": _R(
        construct=(
            "A trailing FOR UPDATE / FOR SHARE row-lock clause "
            "(PostgreSQL/Oracle/MySQL) → T-SQL"
        ),
        reason=(
            "T-SQL has no trailing row-lock clause on SELECT at all; row "
            "locking is instead requested via a WITH (UPDLOCK, ROWLOCK) "
            "table hint on the FROM clause — a different syntactic "
            "position, not a drop-in keyword substitution."
        ),
        example_case="postgresql-qdrop-FOR",
        divergence=(
            "Warned limit — the clause is dropped rather than left as "
            "invalid trailing syntax; add a WITH (UPDLOCK, ROWLOCK) hint "
            "by hand for equivalent locking."
        ),
    ),
    "UNIQUE-1145": _R(
        construct=(
            "A MySQL inline functional/plain INDEX table element (→ other " "engines)"
        ),
        reason=(
            "An inline INDEX inside CREATE TABLE is a MySQL-only "
            "spelling; every other engine treats an index as a separate, "
            "purely physical object with no bearing on query results, so "
            "there is no column/constraint-list form to carry it to."
        ),
        example_case="my-json-index",
        divergence=(
            "Warned limit — the index is omitted; queries still return "
            "correct rows, just unindexed. Write a separate CREATE INDEX "
            "by hand where the target supports the expression."
        ),
    ),
    "UNIQUE-1146": _R(
        construct="An EXCLUDE exclusion constraint (PostgreSQL) → T-SQL/MySQL/Oracle",
        reason=(
            "EXCLUDE (e.g. preventing overlapping ranges via a GiST "
            "index) is a PostgreSQL-only constraint type with no "
            "equivalent declarative constraint on any other engine; the "
            "same behavior there needs a hand-written trigger."
        ),
        example_case="postgresql-drop2-EXCLUDE",
        divergence=(
            "Warned limit — the table itself stays valid; the exclusion "
            "is not enforced. Emulate it with a trigger if required."
        ),
    ),
    "UNIQUE-1147": _R(
        construct=(
            "T-SQL computed column, e.g. total AS (a + b) PERSISTED "
            "(→ PostgreSQL/MySQL/Oracle)"
        ),
        reason=(
            "T-SQL's computed-column syntax declares no explicit type at "
            "all (it is inferred from the expression); PostgreSQL, MySQL "
            "and Oracle all require an explicit type on a generated "
            "column (live-verified: MySQL rejects the typeless form too), "
            "and the transpiler cannot always infer one without full "
            "expression type-checking."
        ),
        example_case=(
            "tests/integration/test_cross_dialect.py::TestCrossDialectDDL::"
            "test_computed_column_preserved"
        ),
        divergence=(
            "Warned limit — the column definition is documented as a "
            "comment outside the (still valid) CREATE TABLE column list."
        ),
    ),
    "UNIQUE-1148": _R(
        construct="Foreign-key ON UPDATE referential action (→ Oracle)",
        reason=(
            "Oracle foreign keys support only ON DELETE CASCADE / SET NULL — "
            "there is no ON UPDATE referential action (ORA-00905)."
        ),
        example_case="reda-ts-fk-on-update",
        divergence=(
            "Warned limit — ON UPDATE is dropped; reproduce it with a trigger "
            "if needed."
        ),
    ),
    "UNIQUE-1151": _R(
        construct=(
            "A source-engine built-in with no form in the target's catalog "
            "(e.g. SOUNDEX → PostgreSQL)"
        ),
        reason=(
            "A call that is a built-in of the source engine (clearly meant to "
            "run, not a user object) but absent from the target's catalog "
            "would be rejected outright, so the whole statement degrades rather "
            "than shipping an invalid call — the general unmapped-built-in "
            "gate."
        ),
        example_case="ora-soundex",
        divergence=(
            "Warned limit — the statement is preserved as a carrier and the "
            "failing built-in is named."
        ),
    ),
    "UNIQUE-1152": _R(
        construct="Oracle %TYPE / %ROWTYPE column-type reference (without --db-url)",
        reason=(
            "Only Oracle supports %TYPE/%ROWTYPE; resolving the real column "
            "type needs a live catalog lookup (ALL_TAB_COLUMNS) unavailable "
            "without a DB connection, so a permissive carrier type is emitted "
            "with the original reference preserved for a faithful round-trip "
            "back to Oracle."
        ),
        example_case=(
            "tests/integration/test_procedural.py::"
            "test_type_reference_documented_then_restored"
        ),
        divergence=(
            "Warned limit without --db-url (carrier type may not match "
            "exactly); faithful with --db-url or on an Oracle→Oracle "
            "round-trip."
        ),
    ),
    "UNIQUE-1153": _R(
        construct=(
            "PostgreSQL trigger function (CREATE FUNCTION ... RETURNS TRIGGER) (→ "
            "MySQL)"
        ),
        reason=(
            "MySQL has no trigger functions — a trigger's body belongs directly to "
            "CREATE TRIGGER, not to a separately-callable RETURNS TRIGGER function — "
            "so the PL/pgSQL function shape has nothing to bind to."
        ),
        example_case=(
            "tests/integration/test_triggers.py::TestPostgresTriggerToMySQL::test_trigger_function_degrades_with_warning"
        ),
        divergence=(
            "Warned limit — the non-portable translation is preserved commented out "
            "for a manual rewrite."
        ),
    ),
    "UNIQUE-1154": _R(
        construct=(
            "T-SQL inline table-valued function (CREATE FUNCTION ... RETURNS TABLE AS "
            "RETURN (...))"
        ),
        reason=(
            "Neither MySQL nor PostgreSQL has an inline (single-statement, "
            "substituted-at-call-site) table-valued function form; both would need a "
            "full multi-statement function/procedure rewritten by hand."
        ),
        example_case=(
            "tests/integration/test_procedural.py::TestInlineTableValuedFunction::test_mysql_documents_and_comments_out"
        ),
        divergence=(
            "Warned limit — documented and commented out rather than emitted as "
            "invalid RETURNS TABLE."
        ),
    ),
    "UNIQUE-1155": _R(
        construct=(
            "A trigger body that reads the T-SQL inserted/deleted pseudo-tables in a "
            "set-based way (FROM/JOIN inserted|deleted) the target cannot express"
        ),
        reason=(
            "Once the set-based pseudo-table read degrades to a per-statement carrier "
            "(UNIQUE-1201), the surrounding trigger no longer has a runnable body — "
            "shipping it partially would execute a half-empty trigger per row, so the "
            "whole trigger is preserved commented out instead."
        ),
        example_case=(
            "tests/integration/test_triggers.py::TestSetBasedTriggerRewrite::test_pure_set_based_to_mysql_documented"
        ),
        divergence="Warned limit — the whole trigger becomes a documented carrier.",
    ),
    "UNIQUE-1156": _R(
        construct="Oracle COMPOUND TRIGGER (→ MySQL)",
        reason=(
            "A compound trigger's BEFORE/AFTER EACH ROW + AFTER STATEMENT sections "
            "collect affected rows into a PL/SQL collection and re-aggregate them "
            "statement-wide; MySQL has no equivalent mechanism (no transition tables, "
            "no multi-timing trigger sections) to mechanically rewrite that "
            "accumulation into."
        ),
        example_case=(
            "tests/integration/test_triggers.py::TestOracleCompoundTrigger::test_degrades_to_carrier_mysql"
        ),
        divergence=(
            "Warned limit — documented for a manual rewrite (a MySQL row-level trigger "
            "that re-reads the table)."
        ),
    ),
    "UNIQUE-1157": _R(
        construct=(
            "A PostgreSQL statement-level trigger delegating its body to a trigger "
            "function via EXECUTE FUNCTION (→ MySQL)"
        ),
        reason=(
            "MySQL has neither trigger functions nor transition tables, so a "
            "statement-level trigger that references its bound function's "
            "transition-table reads has nothing to bind to."
        ),
        example_case=(
            "tests/integration/test_triggers.py::TestPostgresTriggerToMySQL::test_trigger_binding_degrades_with_warning"
        ),
        divergence="Warned limit — documented carrier.",
    ),
    "UNIQUE-1158": _R(
        construct="A PostgreSQL FOREACH ... IN ARRAY LOOP (→ other engines)",
        reason=(
            "The FOREACH-over-array loop is inherently array-typed, and no other "
            "engine has an array column/variable type at all, so there is no array to "
            "iterate over on the target."
        ),
        example_case=(
            "tests/integration/test_pg_source_wave1.py::TestForeachArrayLoop::test_foreach_degrades_off_pg"
        ),
        divergence="Warned limit — statement preserved as a comment.",
    ),
    "UNIQUE-1159": _R(
        construct=(
            "An Oracle PL/SQL PRAGMA declaration (e.g. AUTONOMOUS_TRANSACTION) (→ "
            "other engines)"
        ),
        reason=(
            "A PRAGMA is a compiler directive to the Oracle PL/SQL engine itself (no "
            "runtime SQL effect); no other engine's procedural language has an "
            "equivalent compiler-directive mechanism."
        ),
        example_case=(
            "tests/integration/test_oracle_mysql_tail.py::TestPragmaAutonomousTransaction::test_off_oracle_pragma_never_ships_executable"
        ),
        divergence=(
            "Warned limit — dropped; the surrounding declarations and body still "
            "transpile."
        ),
    ),
    "UNIQUE-1160": _R(
        construct=(
            "A standalone (anonymous) PL/SQL block at the top level, with no enclosing "
            "CREATE PROCEDURE/FUNCTION"
        ),
        reason=(
            "No other engine has a top-level anonymous executable block outside a "
            "routine definition (T-SQL's nearest analog, a batch, has different "
            "scoping/semantics), so a mechanical rewrite risks silently changing what "
            "runs when."
        ),
        example_case=(
            "tests/integration/test_procedural.py::TestOracleCatalogDropBlock::test_degrades_on_postgresql"
        ),
        divergence=(
            "Warned limit — preserved as a documented comment below the carrier."
        ),
    ),
    "UNIQUE-1161": _R(
        construct="T-SQL sp_executesql parameter declarations/bindings (→ MySQL)",
        reason=(
            "MySQL's PREPARE/EXECUTE has no inline parameter-declaration + "
            "binding form matching sp_executesql's @params list, so the "
            "declarations/bindings are dropped and must be passed via "
            "EXECUTE ... USING."
        ),
        example_case="ts-sp-executesql",
        divergence="Warned limit — parameter bindings dropped.",
    ),
    "UNIQUE-1162": _R(
        construct=(
            "A PL/pgSQL RAISE NOTICE inside a function that returns a scalar value (→ "
            "MySQL)"
        ),
        reason=(
            "A bare SELECT (MySQL's own notice-style output channel) is invalid inside "
            "a MySQL FUNCTION — functions cannot return an extra result set (error "
            "1415) — so the message is diverted into a session variable instead."
        ),
        example_case=(
            "tests/integration/test_pg_source_wave1.py::TestMysqlFunctionNotice::test_notice_in_function_diverts"
        ),
        divergence=(
            "Warned limit — the message lands in @uq_notice, not printed inline; "
            "procedures (which can SELECT) keep the visible channel."
        ),
    ),
    "UNIQUE-1163": _R(
        construct="T-SQL RAISERROR/THROW with severity/state arguments (→ MySQL)",
        reason=(
            "MySQL's SIGNAL statement has no severity/state argument slots matching "
            "RAISERROR's — only the message transfers, so the extra arguments are "
            "dropped and named in the carrier rather than silently discarded."
        ),
        example_case="red2-ts-raiserror-format-arg-drop",
        divergence="Warned limit — severity/state args dropped, listed in the carrier.",
    ),
    "UNIQUE-1164": _R(
        construct="BEGIN TRANSACTION (→ Oracle)",
        reason=(
            "Oracle has no explicit transaction-start statement — a transaction begins "
            "implicitly with the first DML statement — so an explicit BEGIN "
            "TRANSACTION has nothing to translate to."
        ),
        example_case=(
            "tests/integration/test_procedural.py::TestTransactionControl::test_begin_transaction_documented_for_oracle_pg"
        ),
        divergence=(
            "Faithful (no-op drop) — Oracle's implicit transaction start reproduces "
            "the same behaviour."
        ),
    ),
    "UNIQUE-1165": _R(
        construct=(
            "T-SQL WAITFOR TIME '...' — wait until an absolute clock time (→ MySQL)"
        ),
        reason=(
            "Every target's sleep primitive (DBMS_SESSION.SLEEP, pg_sleep, MySQL "
            "SLEEP) takes a relative duration, not an absolute wall-clock time to wait "
            "until; WAITFOR DELAY (relative) maps cleanly, but WAITFOR TIME has no "
            "relative-duration equivalent to compute without the current time at run "
            "time."
        ),
        example_case=(
            "tests/integration/test_procedural.py::TestWaitFor::test_time_documented"
        ),
        divergence="Warned limit — documented, not computed.",
    ),
    "UNIQUE-1166": _R(
        construct=(
            "A non-forward cursor FETCH (FETCH LAST/PRIOR/FIRST/ABSOLUTE/RELATIVE) "
            "from a scrollable cursor (→ Oracle)"
        ),
        reason=(
            "Oracle cursors, like every other target's, are forward-only (only FETCH "
            "NEXT); a non-forward fetch direction has no operation to translate to."
        ),
        example_case=(
            "tests/integration/test_pg_source_wave1.py::TestFetchDirections::test_fetch_last_degrades_oracle"
        ),
        divergence=(
            "Warned limit — the scroll fetch degrades to a carrier; the surrounding "
            "OPEN/FETCH NEXT/CLOSE still compile."
        ),
    ),
    "UNIQUE-1167": _R(
        construct="A cursor FETCH with no INTO target-variable list",
        reason=(
            "PostgreSQL/Oracle/MySQL all require FETCH to specify where the fetched "
            "row's columns go; a source FETCH that discards the row (no INTO) has "
            "nothing for the target's FETCH to bind, so emitting 'FETCH c INTO ;' "
            "would be invalid syntax."
        ),
        example_case=(
            "tests/integration/test_procedural.py::TestUnsupportedCursorConstructsAreValidCarriers::test_fetch_without_into_is_documented_not_empty"
        ),
        divergence=(
            "Warned limit — documented as a comment rather than shipping an incomplete "
            "FETCH."
        ),
    ),
    "UNIQUE-1168": _R(
        construct="GOTO <label> (→ PostgreSQL)",
        reason=(
            "PL/pgSQL has no GOTO statement (or any unconditional-jump control-flow "
            "form), so a source GOTO has no operation to translate to."
        ),
        example_case="red3-ts-goto-label-proc",
        divergence=(
            "Warned limit — dropped; control flow is not replicated (T-SQL/Oracle keep "
            "native GOTO)."
        ),
    ),
    "UNIQUE-1169": _R(
        construct="A GOTO target label (→ PostgreSQL)",
        reason=(
            "Without a GOTO to jump to it, and with PL/pgSQL having no label/GOTO "
            "mechanism at all, the label marker itself has nothing to bind to on the "
            "target."
        ),
        example_case="red3-ts-goto-label-proc",
        divergence="Warned limit — dropped alongside its GOTO.",
    ),
    "UNIQUE-1170": _R(
        construct=(
            "A procedural construct the parser cannot recognize at all "
            "(e.g. a PL/SQL collection-TYPE declaration inside a "
            "trigger's DECLARE section)"
        ),
        reason=(
            "This code is the procedural pipeline's own generic 'could "
            "not parse this' escape valve — paired 1:1 with the parser's "
            "own fallback (it captures the unparsed token stream as a "
            "carrier), so the concrete unrecognized shape varies by call "
            "site rather than being fixed per code."
        ),
        example_case=(
            "tests/integration/test_procedural_warning_codes.py::"
            "test_unparseable_construct_does_not_duplicate_the_carrier_warning"
        ),
        divergence=(
            "Warned limit — the whole routine/statement is preserved as "
            "a documented comment for manual review."
        ),
    ),
    "UNIQUE-1171": _R(
        construct=(
            "A whole procedural construct the transformer recognizes but cannot map on "
            "the target (the shared transformer-degrade carrier)"
        ),
        reason=(
            "Shared carrier path for any transformer-level whole-unit degrade (an "
            "unsupported PL/SQL exception context in a T-SQL scalar function, a "
            "client-tool directive, ...); each specific reason is interpolated into "
            "the same carrier template rather than allocating one code per message."
        ),
        example_case="pg-named-exception",
        divergence="Warned limit — the construct is preserved as a documented comment.",
    ),
    "UNIQUE-1172": _R(
        construct="GOTO <label> (→ MySQL)",
        reason=(
            "MySQL has no GOTO statement either; the carrier additionally pairs the "
            "drop with a DO 0 no-op so an IF/loop body the GOTO occupied is never left "
            "syntactically empty (MySQL error 1064)."
        ),
        example_case="red3-ts-goto-label-proc",
        divergence="Warned limit — dropped; control flow not replicated.",
    ),
    "UNIQUE-1173": _R(
        construct="A GOTO target label (→ MySQL)",
        reason=(
            "Same underlying gap as UNIQUE-1169 but for MySQL, which also has no "
            "label/GOTO mechanism."
        ),
        example_case="red3-ts-goto-label-proc",
        divergence="Warned limit — dropped alongside its GOTO.",
    ),
    "UNIQUE-1174": _R(
        construct=(
            "An Oracle/PostgreSQL implicit cursor FOR loop whose query's column list "
            "Unique cannot resolve (e.g. SELECT * or an unresolvable projection) (→ "
            "T-SQL / MySQL)"
        ),
        reason=(
            "The faithful expansion needs one FETCH-target variable per selected "
            "column; when the column list isn't statically resolvable (a bare SELECT * "
            "with no visible schema, or a referenced record field the visible list "
            "doesn't expose), Unique cannot generate that variable list, so it emits a "
            "documented scaffold for the developer to complete instead of guessing."
        ),
        example_case=(
            "tests/integration/test_cursor_for_loop_tsql.py::test_unresolvable_select_star_keeps_documented_scaffold"
        ),
        divergence=(
            "Warned limit — the FETCH INTO target list is left as a placeholder "
            "comment for manual completion; OPEN/CLOSE and the loop shape are still "
            "emitted."
        ),
    ),
    "UNIQUE-1175": _R(
        construct=(
            "An Oracle/PostgreSQL implicit cursor FOR loop with a resolvable column "
            "list (→ MySQL)"
        ),
        reason=(
            "The columns are resolvable, so the loop expands completely (one variable "
            "per column, positional FETCH), but without a --db-url connection Unique "
            "does not know each column's real type, so every loop variable is declared "
            "as the permissive TEXT type."
        ),
        example_case=(
            "tests/integration/test_oracle_mysql_tail.py::TestMySqlCursorForLoopExpansion::test_named_cursor_drives_directly"
        ),
        divergence=(
            "Warned limit without --db-url (loop variables are TEXT, not the real "
            "column types); the loop's control flow and FETCH are otherwise faithful."
        ),
    ),
    "UNIQUE-1176": _R(
        construct="A T-SQL INSTEAD OF trigger (→ MySQL)",
        reason=(
            "MySQL has no INSTEAD OF trigger timing at all (only BEFORE/AFTER); the "
            "closest emulation is a BEFORE trigger, which runs in addition to (not "
            "instead of) the triggering statement, so the substitution semantics are "
            "not reproduced automatically."
        ),
        example_case=(
            "tests/integration/test_triggers.py::TestInsteadOfTrigger::test_instead_of_documented_on_mysql"
        ),
        divergence=(
            "Warned limit — emitted as BEFORE for review, with the original INSTEAD OF "
            "timing documented."
        ),
    ),
    "UNIQUE-1177": _R(
        construct="A T-SQL procedure-level RETURN <value> (a status code) (→ MySQL)",
        reason=(
            "MySQL stored procedures have no return value (only functions do); a "
            "procedure's RETURN <expr> is rewritten to a bare LEAVE (exiting the "
            "procedure), and the discarded value is named in the carrier rather than "
            "silently dropped."
        ),
        example_case=(
            "tests/integration/test_procedural.py::TestReturnValueInProcedure::test_return_value_in_procedure_becomes_leave"
        ),
        divergence=(
            "Warned limit — the status-code value is documented, not returned; a "
            "FUNCTION's RETURN <value> is unaffected and kept."
        ),
    ),
    "UNIQUE-1178": _R(
        construct=(
            "A dynamic-SQL EXECUTE ... INTO <var> whose target string is not a "
            "compile-time-resolvable SELECT INTO @session-variable form (→ MySQL)"
        ),
        reason=(
            "MySQL's PREPARE/EXECUTE workflow can only capture a dynamic result into a "
            "variable if the dynamic SQL text itself is rewritten to 'SELECT ... INTO "
            "@var', which Unique cannot reliably synthesize for an arbitrary dynamic "
            "string built at runtime."
        ),
        example_case="pg-dyn-count",
        divergence=(
            "Warned limit — documented; the dynamic string must be rewritten by hand "
            "to select into a MySQL session variable."
        ),
    ),
    "UNIQUE-1179": _R(
        construct=(
            "A trigger body that reads the T-SQL inserted/deleted pseudo-tables in a "
            "set-based way (→ Oracle)"
        ),
        reason=(
            "Oracle has no transition tables at all (a compound trigger's "
            "PL/SQL-collection accumulation is the closest analog, and is not a "
            "mechanical rewrite of an arbitrary set-based DML statement), so the "
            "set-based read cannot be expressed."
        ),
        example_case=(
            "tests/integration/test_triggers.py::TestSetBasedTriggerRewrite::test_pure_set_based_to_oracle_documented"
        ),
        divergence=(
            "Warned limit — the whole trigger degrades to a documented carrier for a "
            "manual compound-trigger rewrite (the Oracle-specific sibling of "
            "UNIQUE-1155)."
        ),
    ),
    "UNIQUE-1180": _R(
        construct="T-SQL sp_executesql named parameters (→ Oracle)",
        reason=(
            "Oracle EXECUTE IMMEDIATE ... USING binds positionally, so the "
            "named @params of sp_executesql must be re-spelled inside the "
            "dynamic string as :1, :2, …."
        ),
        example_case="ts-sp-executesql",
        divergence="Warned limit — placeholders must be renumbered positionally.",
    ),
    "UNIQUE-1182": _R(
        construct=(
            "A T-SQL INSTEAD OF trigger on a base TABLE, not a view (→ PostgreSQL)"
        ),
        reason=(
            "PostgreSQL restricts INSTEAD OF triggers to views only; on a table, the "
            "equivalent behaviour (substituting the trigger's own logic for the "
            "triggering statement) is a BEFORE row trigger that returns NULL, "
            "suppressing the original operation — a different trigger-timing model "
            "requiring a pg_trigger_depth() guard so the trigger's own DML still "
            "executes."
        ),
        example_case="ts-instead-of-insert",
        divergence=(
            "Faithful — the rewritten BEFORE-trigger-with-guard form reproduces the "
            "substitution semantics (live-verified insert-exactly-once)."
        ),
    ),
    "UNIQUE-1183": _R(
        construct="BEGIN TRANSACTION (→ PostgreSQL)",
        reason=(
            "A PL/pgSQL routine already runs inside the caller's transaction (or "
            "manages its own via nested procedure-call semantics) — there is no "
            "explicit statement to start one, so an explicit BEGIN TRANSACTION has "
            "nothing to translate to."
        ),
        example_case=(
            "tests/integration/test_procedural.py::TestTransactionControl::test_begin_transaction_documented_for_oracle_pg"
        ),
        divergence=(
            "Faithful (no-op drop) — PostgreSQL's implicit routine-transaction "
            "handling reproduces the same behaviour."
        ),
    ),
    "UNIQUE-1184": _R(
        construct="SAVEPOINT (→ PostgreSQL)",
        reason=(
            "PL/pgSQL has no explicit SAVEPOINT statement; the equivalent behaviour (a "
            "partial rollback boundary) comes from wrapping statements in a BEGIN ... "
            "EXCEPTION block, which rolls back to its own start on error."
        ),
        example_case=(
            "tests/integration/test_procedural.py::TestTransactionControl::test_rollback_to_savepoint"
        ),
        divergence=(
            "Warned limit — dropped; wrap the guarded statements in a "
            "BEGIN...EXCEPTION block to reproduce the rollback boundary (Oracle keeps "
            "native SAVEPOINT)."
        ),
    ),
    "UNIQUE-1185": _R(
        construct="ROLLBACK TO SAVEPOINT <name> (→ PostgreSQL)",
        reason=(
            "Same underlying gap as UNIQUE-1184 — PL/pgSQL has no explicit savepoints "
            "to roll back to; the enclosing BEGIN...EXCEPTION block already rolls back "
            "automatically on error."
        ),
        example_case=(
            "tests/integration/test_procedural.py::TestTransactionControl::test_rollback_to_savepoint"
        ),
        divergence="Warned limit — dropped alongside its SAVEPOINT.",
    ),
    "UNIQUE-1186": _R(
        construct="SELECT * INTO <multiple variables> (→ other engines)",
        reason=(
            "Expanding SELECT * into a positional variable-assignment list requires "
            "knowing the source's column list, which a bare '*' does not carry without "
            "schema access; the same is true across engines, so the statement cannot "
            "be mechanically completed."
        ),
        example_case=(
            "tests/integration/test_pg_source_wave1.py::TestWave233StarIntoMultipleVars::test_star_into_multi_degrades"
        ),
        divergence=(
            "Warned limit — documented; supply the column list explicitly to fix."
        ),
    ),
    "UNIQUE-1187": _R(
        construct=(
            "An Oracle/PostgreSQL implicit cursor FOR loop with a resolvable column "
            "list (→ T-SQL)"
        ),
        reason=(
            "The T-SQL sibling of UNIQUE-1175 — the columns are resolvable and the "
            "loop expands completely (one @variable per column, positional FETCH "
            "NEXT), but without --db-url metadata each loop variable is declared as "
            "the permissive NVARCHAR(4000) rather than the column's real type."
        ),
        example_case=(
            "tests/integration/test_cursor_for_loop_tsql.py::test_named_cursor_loop_expands_completely"
        ),
        divergence=(
            "Warned limit without --db-url (loop variables are NVARCHAR(4000)); the "
            "loop's control flow and FETCH are otherwise faithful and complete."
        ),
    ),
    "UNIQUE-1188": _R(
        construct=(
            "SET TRANSACTION READ ONLY/READ WRITE inside a routine (→ " "T-SQL)"
        ),
        reason=(
            "T-SQL's SET TRANSACTION only sets the ISOLATION LEVEL; it "
            "has no access-mode spelling at all (Oracle/PostgreSQL/"
            "MySQL all accept READ ONLY/READ WRITE natively), so the "
            "mode has no target keyword to map to."
        ),
        example_case=(
            "tests/integration/test_challenge.py::TestProcSetTransaction::"
            "test_tsql_degrades_read_only_with_warning"
        ),
        divergence=(
            "Warned limit — the access mode is dropped; ISOLATION LEVEL "
            "modes on the same statement still map natively."
        ),
    ),
    "UNIQUE-1190": _R(
        construct=(
            "Oracle EXECUTE IMMEDIATE ... USING <binds> with no INTO clause (→ T-SQL)"
        ),
        reason=(
            "T-SQL's sp_executesql takes named parameters (@p1, @p2, ...) bound by "
            "name, while Oracle's USING binds positionally against :1, :2, ... "
            "placeholders inside the dynamic string; the rewrite emits a parameterized "
            "sp_executesql call, but the placeholders inside the dynamic-SQL text "
            "itself must still be renumbered by hand to match."
        ),
        example_case=(
            "tests/integration/test_procedural.py::TestDynamicSQL::test_oracle_to_tsql_uses_sp_executesql"
        ),
        divergence=(
            "Warned limit — placeholders inside the dynamic string need manual "
            "renumbering to @p1, @p2, ...; the call itself is valid and parameterized."
        ),
    ),
    "UNIQUE-1192": _R(
        construct=(
            "Oracle's implicit-cursor SQL%ROWCOUNT (rows the last DML MATCHED) (→ "
            "MySQL)"
        ),
        reason=(
            "MySQL's closest equivalent, ROW_COUNT(), counts rows actually CHANGED by "
            "the last DML, not rows matched by its WHERE clause — for an UPDATE that "
            "matches a row but assigns it its current value, Oracle's matched-count "
            "and MySQL's changed-count diverge; the mapping is kept (still the closest "
            "fit) but annotated rather than shipped silently."
        ),
        example_case=(
            "tests/integration/test_challenge.py::TestRowcountDivergenceAnnotation::test_mysql_target_annotates_and_warns"
        ),
        divergence=(
            "Warned limit — the value may differ from the source when a matched row's "
            "UPDATE is a no-op (T-SQL's @@ROWCOUNT is matched-rows too and needs no "
            "such note)."
        ),
    ),
    "UNIQUE-1193": _R(
        construct=(
            "A source-only procedural statement with no target concept at all (e.g. "
            "T-SQL SET IDENTITY_INSERT/SET NOCOUNT inside a routine) (→ other engines)"
        ),
        reason=(
            "The statement configures a source-engine-only session/compiler behaviour "
            "with no corresponding concept on the target at all (not merely a missing "
            "spelling), so the shared carrier documents it as '{source}-only' rather "
            "than attempting any target-side equivalent."
        ),
        example_case=(
            "tests/integration/test_procedural.py::TestUniqueCommentRestore::test_identity_insert_documented_then_restored"
        ),
        divergence=(
            "Warned limit — dropped; documented as source-engine-only, and restored "
            "verbatim on a round trip back to the source engine."
        ),
    ),
    "UNIQUE-1194": _R(
        construct=(
            "A T-SQL global (@@ERROR/@@TRANCOUNT/@@CURSOR_ROWS/SQL%ROWCOUNT-family) "
            "used inside an expression position (e.g. an IF condition) with no target "
            "equivalent"
        ),
        reason=(
            "These globals have no faithful non-source equivalent, and unlike a "
            "top-level statement, an expression position cannot simply be dropped — a "
            "value-shaped placeholder is required so the surrounding expression stays "
            "syntactically valid."
        ),
        example_case=(
            "tests/integration/test_procedural.py::TestErrorGlobalInCondition::test_error_in_if_mysql"
        ),
        divergence=(
            "Warned limit — a neutral literal (0) replaces the global so the "
            "expression parses; the specific behaviour it gated is lost."
        ),
    ),
    "UNIQUE-1195": _R(
        construct=(
            "A PostgreSQL trigger function's body, when its trigger delegates to it "
            "via EXECUTE FUNCTION (→ T-SQL)"
        ),
        reason=(
            "T-SQL has no separately-callable trigger function — a trigger's logic "
            "must live inline in CREATE TRIGGER — so the delegating function's body is "
            "inlined directly into the T-SQL trigger, with the PG-only "
            "pg_trigger_depth() guard and RETURN NULL protocol dropped (T-SQL triggers "
            "have no such re-entrancy-guard convention)."
        ),
        example_case=(
            "tests/integration/test_triggers.py::TestPgDelegatingTriggerToTSql::test_inlined_into_tsql_trigger"
        ),
        divergence=(
            "Faithful — the inlined trigger reproduces the same DML; live-compiled "
            "valid."
        ),
    ),
    "UNIQUE-1196": _R(
        construct="A T-SQL table variable (DECLARE @var TABLE (...)) (→ MySQL)",
        reason=(
            "MySQL has no table-variable DECLARE form; the closest equivalent is a "
            "CREATE TEMPORARY TABLE statement inside the routine body, which the "
            "carrier documents as the table variable's replacement."
        ),
        example_case=(
            "tests/integration/test_procedural.py::TestTableVariableToMySQL::test_table_variable_becomes_temp_table"
        ),
        divergence=(
            "Faithful — a temporary table reproduces the same session-scoped, "
            "statement-usable storage; the carrier is purely documentary."
        ),
    ),
    "UNIQUE-1197": _R(
        construct=(
            "A source-only SET option with no target equivalent, inside a routine body "
            "(e.g. MySQL SET SQL_MODE)"
        ),
        reason=(
            "The option configures source-engine-only parsing/execution behaviour "
            "(MySQL's SQL_MODE flags, for instance) that no other engine's session "
            "model has a matching concept for."
        ),
        example_case=(
            "tests/integration/test_pg_source_wave1.py::TestWave162AdddateSqlMode::test_set_sql_mode_carrier_tsql"
        ),
        divergence="Warned limit — dropped; documented as source-only.",
    ),
    "UNIQUE-1198": _R(
        construct=(
            "EXEC <T-SQL system procedure> as a standalone statement (e.g. EXEC "
            "sp_who) inside a routine body (→ other engines)"
        ),
        reason=(
            "T-SQL system procedures call into SQL Server's own catalog/admin "
            "machinery (the same class as UNIQUE-1211's top-level EXEC, here inside a "
            "routine); no other engine exposes the same operation through a callable "
            "procedure."
        ),
        example_case="ts-waitfor-exec",
        divergence=(
            "Warned limit — the call becomes a documented carrier; the administrative "
            "action must be performed via the target's own tooling."
        ),
    ),
    "UNIQUE-1200": _R(
        construct=(
            "An Oracle built-in package call (e.g. DBMS_SCHEDULER.CREATE_JOB) (→ other "
            "engines)"
        ),
        reason=(
            "Oracle's DBMS_*/UTL_* packages call into Oracle-specific server-side "
            "machinery (job scheduling, session control, ...) with no cross-engine "
            "equivalent; shipped raw, the call is a guaranteed runtime error off "
            "Oracle."
        ),
        example_case=(
            "tests/integration/test_trigger_predicates_scheduler.py::test_dbms_scheduler_degrades_to_carrier"
        ),
        divergence=(
            "Warned limit — the call becomes a documented carrier rather than an "
            "invalid raw call."
        ),
    ),
    "UNIQUE-1201": _R(
        construct=(
            "A trigger DML statement that reads the T-SQL inserted/deleted "
            "pseudo-tables in a set-based way (FROM inserted / JOIN deleted) (→ other "
            "engines, absent a transition-table rewrite)"
        ),
        reason=(
            "A set-based pseudo-table read has no row-level (NEW/OLD) equivalent; "
            "where the whole trigger can be rewritten with real transition tables "
            "(PostgreSQL statement-level triggers, Oracle compound triggers) the "
            "set-based DML is left as-is, but where it cannot (MySQL, or a mixed "
            "row+set trigger), the specific statement is documented instead of emitted "
            "referencing an undefined table."
        ),
        example_case=(
            "tests/integration/test_triggers.py::TestSetBasedTriggerRewrite::test_pure_set_based_to_mysql_documented"
        ),
        divergence=(
            "Warned limit — the statement is documented with per-target rewrite "
            "guidance rather than shipped referencing an undefined table."
        ),
    ),
    "UNIQUE-1202": _R(
        construct="A T-SQL table-valued function used in a FROM clause (→ MySQL)",
        reason=(
            "MySQL has no table-valued function mechanism (a function cannot appear as "
            "a FROM-clause row source); the statement is commented out rather than "
            "shipping an invalid function-in-FROM."
        ),
        example_case=(
            "tests/integration/test_procedural.py::TestTableValuedFunctionInFrom::test_user_tvf_in_from_commented"
        ),
        divergence=(
            "Warned limit — commented out for review (STRING_SPLIT, rewritten to the "
            "valid JSON_TABLE form, is unaffected)."
        ),
    ),
    "UNIQUE-1203": _R(
        construct=(
            "An Oracle cursor attribute the transformer does not recognize (e.g. "
            "c%BULK_ROWCOUNT) (→ other engines)"
        ),
        reason=(
            "Only a fixed, explicitly-mapped set of cursor attributes "
            "(%FOUND/%NOTFOUND/%ISOPEN/%ROWCOUNT) has a per-cursor state translation "
            "on T-SQL/MySQL; an attribute outside that set has no known target form, "
            "and — critically — must not fall through to the general expression "
            "parser, which would otherwise read 'c%attr' as 'c' modulo 'attr'."
        ),
        example_case=(
            "tests/integration/test_cursor_state_b7.py::TestUnknownAttributeWarns::test_unknown_attribute_warns_and_does_not_leak_modulo"
        ),
        divergence=(
            "Warned limit — degrades to a neutral 0 carrier rather than silently "
            "becoming modulo arithmetic."
        ),
    ),
    "UNIQUE-1205": _R(
        construct=(
            "A T-SQL #temp table declared with an explicit CREATE TABLE #name (...) (→ "
            "Oracle)"
        ),
        reason=(
            "Same underlying gap as UNIQUE-1196 but for a real temp table rather than "
            "a table variable — Oracle has no session-scoped #temp table; the CREATE "
            "is hoisted to a GLOBAL TEMPORARY TABLE before the routine (a CREATE "
            "cannot live inside PL/SQL), and the carrier documents the substitution."
        ),
        example_case=(
            "tests/integration/test_temp_table_in_procedure.py::TestOracle::test_hoists_global_temporary_table"
        ),
        divergence=(
            "Faithful — the hoisted GTT, cleared and repopulated per call, reproduces "
            "the same session-scoped storage; the carrier is purely documentary."
        ),
    ),
    "UNIQUE-1206": _R(
        construct=(
            "COMMIT/ROLLBACK inside a T-SQL TRY/CATCH block translated to a PL/pgSQL "
            "BEGIN...EXCEPTION block (→ PostgreSQL)"
        ),
        reason=(
            "PL/pgSQL's exception-guarded block is itself a subtransaction "
            "(savepoint); issuing an explicit COMMIT/ROLLBACK inside one is a runtime "
            "error ('cannot commit while a subtransaction is active') rather than a "
            "parse-time gap, and the subtransaction already provides the same "
            "rollback-on-error/commit-with-caller semantics T-SQL's TRY/CATCH "
            "expressed explicitly."
        ),
        example_case=(
            "tests/integration/test_procedural.py::TestTopLevelTryCatch::test_begin_transaction_prefix_lowers_on_postgresql"
        ),
        divergence=(
            "Faithful (the subtransaction reproduces the same net transactional "
            "behaviour) with the explicit COMMIT/ROLLBACK dropped and documented "
            "rather than shipped as a guaranteed runtime error."
        ),
    ),
    "UNIQUE-1207": _R(
        construct=(
            "Inherent value divergence: default-collation comparison, Oracle "
            "'' ≡ NULL, or byte-vs-char length (approved limit)"
        ),
        reason=(
            "These divergences (case/accent/trailing-space comparison under "
            "the default collation, Oracle's '' ≡ NULL, LENGTH "
            "byte-vs-char) are per-column/connection properties the SQL text "
            "carries no trace of; no statement-level rewrite bridges them "
            "without column-collation/encoding visibility Unique does not have."
        ),
        example_case="ora-empty-null",
        divergence=(
            "Approved documented limit, warned — the value or row count may " "differ."
        ),
    ),
    "UNIQUE-1208": _R(
        construct="CREATE SCHEMA (T-SQL) → Oracle",
        reason=(
            "Oracle has no CREATE SCHEMA statement — a schema on Oracle IS "
            "a database user (created with CREATE USER and granted "
            "privileges), a fundamentally different object model from "
            "T-SQL's schema as a namespace within a shared database."
        ),
        example_case=(
            "tests/unit/core/test_transpiler.py::TestTranspiler::"
            "test_create_schema_oracle_documented_carrier"
        ),
        divergence=(
            "Warned limit — documented as unsupported rather than "
            "emitting an invalid CREATE SCHEMA; create the equivalent "
            "Oracle user by hand."
        ),
    ),
    "UNIQUE-1209": _R(
        construct=(
            "Oracle ORGANIZATION INDEX/HEAP table-organization clause "
            "(→ PostgreSQL/T-SQL/MySQL)"
        ),
        reason=(
            "ORGANIZATION INDEX/HEAP selects Oracle's physical "
            "row-storage strategy (index-organized vs heap-organized "
            "table) — a storage-engine-level choice with no "
            "logical-schema meaning and no equivalent concept on any "
            "other engine."
        ),
        example_case=(
            "tests/integration/test_cross_dialect.py::TestCrossDialectDDL::"
            "test_oracle_organization_index_table_converted"
        ),
        divergence=(
            "Faithful in result (storage-only); the clause is dropped and "
            "the table converts as an ordinary table."
        ),
    ),
    "UNIQUE-1210": _R(
        construct=(
            "ALTER TABLE t {CHECK|NOCHECK} CONSTRAINT c — a constraint's "
            "enabled/disabled check-state toggle (T-SQL) → MySQL"
        ),
        reason=(
            "T-SQL's CHECK/NOCHECK CONSTRAINT toggles whether an existing "
            "constraint is currently enforced without dropping it; MySQL "
            "has no equivalent enable/disable toggle for a constraint "
            "(Oracle maps to ENABLE/DISABLE CONSTRAINT, PostgreSQL to "
            "VALIDATE CONSTRAINT) — the state change itself has nothing "
            "to become."
        ),
        example_case=(
            "tests/unit/core/test_transpiler.py::TestTranspiler::"
            "test_constraint_check_state_toggle"
        ),
        divergence=(
            "Warned limit — preserved as a restorable note rather than "
            "dropped; the constraint's enforcement state on MySQL is "
            "unchanged."
        ),
    ),
    "UNIQUE-1211": _R(
        construct="EXEC sp_<name> — a T-SQL system procedure (→ other engines)",
        reason=(
            "T-SQL system procedures call SQL Server's own catalog/admin "
            "machinery; no other engine exposes the same operation through a "
            "callable procedure with the same name or signature."
        ),
        example_case="reda-ts-exec-swallow-next",
        divergence=(
            "Warned limit — the call becomes a carrier; the administrative "
            "action must be performed via the target's own tooling."
        ),
    ),
    "UNIQUE-1212": _R(
        construct=(
            "A standalone INSERT/UPDATE/DELETE ... OUTPUT result set "
            "(→ Oracle / MySQL)"
        ),
        reason=(
            "Neither Oracle (RETURNING is PL/SQL-only, ORA-63809) nor MySQL "
            "has a standalone data-modifying-statement result set, so the "
            "OUTPUT rows cannot be returned to the caller."
        ),
        example_case="ts-insert-output",
        divergence=(
            "Warned limit — the DML effect is faithful; the returned result "
            "set is documented, not produced."
        ),
    ),
    "UNIQUE-1213": _R(
        construct=(
            "A T-SQL default-constraint value with no valid target "
            "spelling (e.g. NEWID() → MySQL)"
        ),
        reason=(
            "The default value is transpiled like any other expression, "
            "but some T-SQL built-ins (NEWID's UUID generation, chief "
            "among them) have no spelling on some targets at all; "
            "shipping the untranslated fragment as a DEFAULT would leave "
            "invalid DDL, so the whole default-constraint statement is "
            "checked against the target's own grammar and, on failure, "
            "preserved as a comment instead."
        ),
        example_case=(
            "tests/unit/core/test_transpiler.py::TestTranspiler::"
            "test_add_default_non_portable_value_falls_back"
        ),
        divergence=(
            "Warned limit — the statement is preserved as a comment; add "
            "the target-native equivalent (e.g. a UUID default/trigger) "
            "by hand."
        ),
    ),
    "UNIQUE-1214": _R(
        construct=(
            "A standalone T-SQL/MySQL SET TRANSACTION ISOLATION LEVEL "
            "READ COMMITTED batch (→ Oracle)"
        ),
        reason=(
            "READ COMMITTED is Oracle's default isolation level, and "
            "Oracle requires SET TRANSACTION to be a transaction's very "
            "first statement (ORA-01453 otherwise); keeping this one "
            "would block a following mapped SET TRANSACTION (e.g. READ "
            "ONLY) from opening the transaction. Same no-op fact as "
            "UNIQUE-1129, reached by a different route: 1129 fires once "
            "the statement has survived into the sqlglot-based "
            "passthrough pipeline as an ordinary node (e.g. it shares a "
            "batch with a preceding statement); 1214 fires when the "
            "statement is (or opens) its own whole batch, handled "
            "directly at the orchestration layer before any sqlglot "
            "parse of it."
        ),
        example_case=(
            "tests/integration/test_challenge.py::TestSetTransactionModes::"
            "test_oracle_read_only"
        ),
        divergence=(
            "Faithful (no-op on both engines) — kept as a comment so a "
            "following SET TRANSACTION mode statement can still open the "
            "transaction."
        ),
    ),
    "UNIQUE-1215": _R(
        construct="SET ROLE (PostgreSQL/MySQL/Oracle) → T-SQL",
        reason=(
            "SET ROLE changes the current session's active role/privilege "
            "set on the engines that have a role system; T-SQL has no "
            "SET ROLE statement at all — role-like membership is "
            "expressed through EXECUTE AS or role membership grants "
            "instead, a structurally different mechanism."
        ),
        example_case=(
            "tests/integration/test_pg_source_wave1.py::"
            "TestWave139DecodeAndSetRole::test_set_role_degrades_tsql"
        ),
        divergence=(
            "Warned limit — statement preserved as a comment; use role "
            "membership / EXECUTE AS on T-SQL instead."
        ),
    ),
    "UNIQUE-1216": _R(
        construct=(
            "SET CONSTRAINTS ... {DEFERRED|IMMEDIATE} (PostgreSQL/Oracle) "
            "→ MySQL/T-SQL"
        ),
        reason=(
            "SET CONSTRAINTS toggles when a DEFERRABLE constraint's check "
            "runs (at each statement vs at COMMIT); MySQL and T-SQL have "
            "no deferrable-constraint model at all, so there is no timing "
            "to toggle."
        ),
        example_case=(
            "tests/unit/core/test_ir_first_families.py::"
            "TestZeroPushPgOnlyShapes::test_set_constraints_carrier"
        ),
        divergence="Warned limit — statement preserved as a comment.",
    ),
    "UNIQUE-1217": _R(
        construct="SET SESSION AUTHORIZATION (PostgreSQL) → T-SQL/MySQL/Oracle",
        reason=(
            "SET SESSION AUTHORIZATION switches the session's effective "
            "user for privilege checks — a PostgreSQL-specific session "
            "directive; the other engines switch users through entirely "
            "different mechanisms (T-SQL EXECUTE AS, MySQL/Oracle "
            "connection-level authentication), none of which is a "
            "drop-in SQL-statement substitution."
        ),
        example_case=(
            "tests/integration/test_pg_source_wave1.py::"
            "TestSessionAuthorizationDegrades::"
            "test_session_authorization_degrades"
        ),
        divergence=(
            "Warned limit — statement preserved as a comment; switch "
            "users through the target's own mechanism."
        ),
    ),
    "UNIQUE-1218": _R(
        construct=(
            "A PostgreSQL session GUC, e.g. SET extra_float_digits = 0 / "
            "SET x TO v / RESET x (→ T-SQL/MySQL/Oracle)"
        ),
        reason=(
            "PostgreSQL's SET/RESET cover hundreds of engine-internal "
            "session tuning knobs (query planner costs, timeouts, "
            "locale, ...) with no cross-engine namespace at all — each is "
            "either meaningless or configured through a completely "
            "different mechanism on the other three engines."
        ),
        example_case=(
            "tests/integration/test_pg_source_wave1.py::TestPgGucSettings::"
            "test_guc_assignment_degrades"
        ),
        divergence=(
            "Warned limit — statement preserved as a comment; configure "
            "the session natively on the target."
        ),
    ),
    "UNIQUE-1219": _R(
        construct=(
            "A MySQL session knob, e.g. SET sql_mode = '...' / FLUSH "
            "STATUS (→ PostgreSQL/T-SQL/Oracle)"
        ),
        reason=(
            "MySQL's SET (bare name, GLOBAL/SESSION/PERSIST) and its "
            "admin statements (FLUSH/LOCK TABLES/ANALYZE TABLE/...) are "
            "engine-local session and maintenance knobs with no meaning "
            "on any other engine."
        ),
        example_case=(
            "tests/integration/test_pg_source_wave1.py::"
            "TestMysqlSessionKnobsDegrade::test_knob_degrades"
        ),
        divergence=(
            "Warned limit — statement preserved as a comment; configure "
            "the session / run maintenance natively on the target."
        ),
    ),
    "UNIQUE-1220": _R(
        construct=(
            "A transpiled statement that the sqlglot output gate accepts "
            "but the real target engine rejects (opt-in live output "
            "validation only)"
        ),
        reason=(
            "sqlglot's writer is deliberately lenient (it renders SQL it "
            "cannot fully validate rather than refuse); a live "
            "connection to the actual target engine is the final "
            "arbiter, so when a development run opts into it and the "
            "engine itself raises on the generated statement, the "
            "statement is degraded to a carrier with the engine's own "
            "error rather than shipping SQL known to fail."
        ),
        example_case=(
            "tests/integration/test_pg_source_wave1.py::"
            "TestLiveOutputValidation::test_live_pg_rejects_become_carriers"
        ),
        divergence=(
            "Warned limit — the statement is preserved as a comment "
            "carrying the live engine's rejection reason; only reachable "
            "with an explicit live-validation URL, not in normal use."
        ),
    ),
    "UNIQUE-1221": _R(
        construct=(
            "TEXTIMAGE_ON <filegroup> — a T-SQL LOB-storage-placement "
            "clause (→ PostgreSQL/MySQL/Oracle)"
        ),
        reason=(
            "TEXTIMAGE_ON pins a table's LOB columns to a specific T-SQL "
            "filegroup — a physical storage-placement detail with no "
            "logical-schema meaning and no equivalent concept (filegroups "
            "themselves are T-SQL-only) on any other engine."
        ),
        example_case=(
            "tests/unit/core/test_transpiler.py::TestTranspiler::"
            "test_textimage_on_filegroup_stripped"
        ),
        divergence=(
            "Faithful in result (storage-only); the clause is dropped so "
            "the CREATE TABLE converts instead of falling back to an "
            "unparsed passthrough."
        ),
    ),
    "UNIQUE-1222": _R(
        construct=(
            "ALTER TABLE t WITH NOCHECK ADD CONSTRAINT ... (T-SQL) → "
            "PostgreSQL/MySQL/Oracle"
        ),
        reason=(
            "T-SQL's WITH NOCHECK adds a constraint without validating "
            "existing rows against it; the other engines either validate "
            "immediately with no opt-out (MySQL/Oracle) or validate "
            "immediately by default with a different deferred-validation "
            "syntax entirely (PostgreSQL's NOT VALID, a separate "
            "construct)."
        ),
        example_case=(
            "tests/unit/core/test_transpiler.py::TestTranspiler::"
            "test_alter_add_constraint_with_nocheck_stripped"
        ),
        divergence=(
            "Warned limit — the constraint is added and the target "
            "validates existing rows immediately, unlike the source's "
            "NOCHECK."
        ),
    ),
    "UNIQUE-1223": _R(
        construct=(
            "A SQL*Plus client directive, e.g. SET SERVEROUTPUT ON "
            "(Oracle) → PostgreSQL/T-SQL/MySQL"
        ),
        reason=(
            "SQL*Plus SET directives configure the CLIENT tool's display "
            "behavior — they have no server-side meaning even on Oracle "
            "itself, let alone on another engine's SQL grammar, where "
            "they are a syntax error."
        ),
        example_case=(
            "tests/unit/core/test_diagnostic_completeness.py::"
            "test_representative_warnings_are_coded"
        ),
        divergence=(
            "Faithful (no server-side effect anywhere) — the directive is "
            "commented out rather than shipped as invalid SQL."
        ),
    ),
    "UNIQUE-1225": _R(
        construct=(
            "An unrecognized IF <catalog-guard> BEGIN ... END "
            "migration-guard batch that no shape-recognizer models"
        ),
        reason=(
            "Idempotent-migration IF-guards (IF [NOT] EXISTS(...) around "
            "a DDL/DML body) are recognized and rewritten only for the "
            "shapes the guard-translation layer models; a guard body that "
            "falls outside every modeled shape (e.g. an unsupported "
            "statement inside it) cannot be safely rewritten, so it is "
            "preserved whole rather than guessed at."
        ),
        example_case=(
            "tests/unit/core/test_guard_translation.py::"
            "TestHonestFallbackLabel::test_non_set_batch_gets_honest_signal"
        ),
        divergence=(
            "Warned limit — the guarded statement now runs "
            "unconditionally (the guard is dropped); the original is "
            "carried in the comment."
        ),
    ),
    "UNIQUE-1226": _R(
        construct=(
            "An IF <real-data condition> ... ELSE ... guard whose ELSE "
            "branch is not a bare diagnostic PRINT"
        ),
        reason=(
            "The IF/ELSE guard rewrite (e.g. into PostgreSQL's DO $$ ... "
            "IF ... THEN ... END IF; END $$) can carry a PRINT-only ELSE "
            "body into the target's own diagnostic-output statement, but "
            "an ELSE with real DML/DDL has no such narrow, safe rewrite "
            "— dropping vs. keeping it both risk changing which branch "
            "runs, so it is flagged rather than guessed at."
        ),
        example_case=(
            "tests/unit/core/test_guard_translation.py::TestGuardElseBranch::"
            "test_non_print_else_warns"
        ),
        divergence=(
            "Warned limit — only the THEN branch is translated; the ELSE "
            "branch is dropped and carried in the comment."
        ),
    ),
    "UNIQUE-1227": _R(
        construct=(
            "T-SQL ALTER COLUMN ... NULL (a redundant, explicit "
            "nullability re-statement) → Oracle"
        ),
        reason=(
            "Oracle's MODIFY raises ORA-01451 if a column already "
            "allows NULL and the statement redundantly re-states NULL "
            "(only a change TO NOT NULL, or FROM NOT NULL back to "
            "nullable, is a real MODIFY); since the column's current "
            "nullability is what the source ALTER COLUMN is re-stating "
            "unchanged, the redundant keyword is dropped rather than "
            "shipped as an error-raising MODIFY."
        ),
        example_case=(
            "tests/unit/core/test_transpiler.py::TestTranspiler::"
            "test_alter_column_varbinary_max_omits_redundant_null"
        ),
        divergence=(
            "Faithful — the column's nullability is unchanged either "
            "way; only the redundant keyword is dropped, with a warning "
            "so the directive isn't silently lost."
        ),
    ),
    "UNIQUE-1228": _R(
        construct=(
            "Internal: a semantic sqlglot AST argument no converter "
            "function reads while building the IR (a structural "
            "safety-net, not a specific SQL construct)"
        ),
        reason=(
            "The converter walks sqlglot's parsed AST and hands each "
            "node's semantic args to a per-construct _convert_* function; "
            "this tripwire records any arg sqlglot considers meaningful "
            "(not in a reviewed allow-list of genuinely inert ones) that "
            "no function ever reads — evidence a clause on that node type "
            "may be silently dropped from the IR/output before anyone "
            "specifically decided to drop it, rather than proof any given "
            "run actually lost something."
        ),
        example_case=(
            "tests/unit/core/test_unread_args.py::TestConverterIntegration::"
            "test_warn_mode_flags_unread_arg"
        ),
        divergence=(
            "Warned limit — the construct may be silently dropped; the "
            "specific arg name is carried in the warning for review."
        ),
    ),
    "UNIQUE-1230": _R(
        construct=(
            "A procedural-routine parse note with no more specific "
            "diagnostic code to inherit (e.g. transpiling a routine to "
            "its own source dialect, a no-op transform that leaves no "
            "carrier in the output)"
        ),
        reason=(
            "A procedural parse warning is raised without a fixed code "
            "of its own; when the routine is rewritten, a later pass "
            "normally infers the specific code from whichever carrier "
            "comment ended up covering the same construct in the "
            "output — but a same-dialect (no-op) transform, or any "
            "other case that leaves no matching carrier, has nothing to "
            "infer from, so the generic fallback code ships instead of "
            "an invented specific one."
        ),
        example_case=(
            "tests/integration/test_procedural_warning_codes.py::"
            "test_genuinely_generic_parse_warning_keeps_fallback_code"
        ),
        divergence=(
            "Warned note — informational; the routine's behavior is "
            "unaffected, only the diagnostic code is generic rather than "
            "specific."
        ),
    ),
    "UNIQUE-1231": _R(
        construct=(
            "Any ProceduralTransformer-level warning with no more specific UNIQUE-NNNN "
            "code of its own"
        ),
        reason=(
            "The shared fallback code for procedural-transform warnings — most "
            "transform-level messages carry their own specific code (reconciled from "
            "the matching inline carrier in the output), but a message with no "
            "corresponding inline carrier still needs a stable code to report through "
            "rather than shipping uncoded."
        ),
        example_case=(
            "tests/integration/test_pg_source_wave1.py::TestParseFallbackDegradesCrossDialect::test_unparsed_routine_degrades_pg"
        ),
        divergence=(
            "Varies by the underlying message; in the bound example, a MySQL CONTINUE "
            "handler for SQLEXCEPTION has no PostgreSQL equivalent and the whole "
            "routine degrades to a documented carrier."
        ),
    ),
    "UNIQUE-1233": _R(
        construct="A transaction closer (COMMIT/END/ROLLBACK) whose opener failed",
        reason=(
            "When a transaction opener (BEGIN) glues to the next statement and "
            "fails to parse, that whole batch degrades to a parse-failure "
            "carrier — no BEGIN reaches the output. Emitting the sibling closer "
            "as an executable COMMIT/ROLLBACK would then run against no open "
            "transaction (T-SQL error 3902), so the closer must degrade too."
        ),
        example_case=(
            "tests/unit/core/test_transpiler.py::"
            "TestTransactionOpenerDegradeCoherence::"
            "test_orphan_closer_after_failed_opener_degrades"
        ),
        divergence=(
            "Coherent degrade — the closer is preserved as a comment so the "
            "output has no orphan COMMIT; both halves of the broken "
            "transaction unit are carried, not silently dropped."
        ),
    ),
    "UNIQUE-1235": _R(
        construct="Oracle STANDARD_HASH(x, 'SHA1') (→ PostgreSQL)",
        reason=(
            "STANDARD_HASH defaults to SHA1 when no algorithm argument is given. "
            "PostgreSQL 11+ has core md5()/sha256()/sha384()/sha512() (live-verified "
            "byte-identical to Oracle's RAWTOHEX(STANDARD_HASH(x, ALG)) for those four "
            "algorithms), but no sha1 without the pgcrypto extension, which is not "
            "assumed to be installed."
        ),
        example_case=(
            "tests/integration/test_function_translation.py::"
            "TestOracleHashFunctionsToPostgresql::"
            "test_standard_hash_sha1_degrades_honestly"
        ),
        divergence=(
            "Warned limit — degrades to a NULL carrier; MD5/SHA256/SHA384/SHA512 "
            "still map faithfully (byte-for-byte, live-verified)."
        ),
    ),
    "UNIQUE-1236": _R(
        construct="A non-id bare Oracle NUMBER column (→ MySQL / T-SQL)",
        reason=(
            "Oracle's unqualified NUMBER holds an arbitrary-precision value. A "
            "column with no id role (not a PRIMARY KEY, UNIQUE, identity, or "
            "FOREIGN KEY) keeps that meaning as unbounded NUMERIC on PostgreSQL, "
            "but MySQL and T-SQL have no unbounded numeric type, so it is bounded "
            "to the project's canonical DECIMAL(38, 10) instead of being promoted "
            "to a fractional-value-truncating BIGINT."
        ),
        example_case=(
            "tests/unit/core/test_boolean_timestamp.py::"
            "TestOracleBareNumberToInteger::"
            "test_non_key_bare_number_to_tsql_bounded_and_warned"
        ),
        divergence=(
            "Warned limit — values needing more than 38 total / 10 fractional "
            "digits are not representable; PostgreSQL keeps the full precision."
        ),
    ),
    "UNIQUE-1237": _R(
        construct=(
            "SELECT ... FOR UPDATE over a non-key-preserved view "
            "(VALUES / set operation / DISTINCT / GROUP BY) → Oracle"
        ),
        reason=(
            "Oracle rejects FOR UPDATE when the locked relation is not "
            "key-preserved — an inline view built on a VALUES constructor, a set "
            "operation, or DISTINCT/GROUP BY has no lockable base rows "
            "(ORA-02014). T-SQL/PostgreSQL/MySQL tolerate the same query, so the "
            "restriction bites only Oracle; a plain base-table FOR UPDATE keeps "
            "its lock."
        ),
        example_case="postgresql-qdrop-FOR",
        divergence=(
            "Warned limit — the unlockable row lock is dropped rather than left "
            "as an ORA-02014 runtime error; the result set is unchanged."
        ),
    ),
    "UNIQUE-1238": _R(
        construct="T-SQL OPTION (MAXRECURSION n) on a recursive CTE",
        reason=(
            "MAXRECURSION is T-SQL's recursion-depth guard on a recursive CTE: "
            "the server raises an error once the recursion exceeds n levels "
            "(the implicit default is 100 when the OPTION clause is absent). "
            "PostgreSQL, MySQL and Oracle recursive queries have no equivalent "
            "depth limit — the recursion simply runs (or loops) until it "
            "terminates on its own, so there is no clause to translate the "
            "guard into."
        ),
        example_case=(
            "tests/integration/test_tsql_maxrecursion_option.py::"
            "TestMaxRecursionDroppedWithSemanticWarning::test_pg_target"
        ),
        divergence=(
            "Warned limit — the hint is dropped; a source query that relied on "
            "the T-SQL error to bound a runaway recursion instead runs to "
            "completion (or loops) on the other three engines. A T-SQL target "
            "keeps the clause verbatim (same dialect, no divergence)."
        ),
    ),
    "UNIQUE-1239": _R(
        construct=(
            "A non-MAXRECURSION T-SQL OPTION (...) query hint (MAXDOP, "
            "RECOMPILE, FORCE ORDER, KEEPFIXED PLAN, ...)"
        ),
        reason=(
            "T-SQL's OPTION (...) clause carries optimizer directives — join "
            "strategy, degree of parallelism, plan caching, and similar "
            "execution-plan hints — that steer the query PLAN, not its result. "
            "No other engine has this clause, and none of these hints has an "
            "observable effect on the rows returned, so there is nothing to "
            "preserve for correctness."
        ),
        example_case=(
            "tests/integration/test_tsql_maxrecursion_option.py::"
            "TestGenericHintDroppedWithLighterWarning::"
            "test_maxdop_and_recompile_dropped"
        ),
        divergence=(
            "Warned limit — the hint is dropped; the result set is unchanged, "
            "only the execution plan is no longer steered. A T-SQL target "
            "keeps the clause verbatim (same dialect, no divergence)."
        ),
    ),
    "UNIQUE-1240": _R(
        construct="COMPRESS() / DECOMPRESS() (T-SQL → MySQL)",
        reason=(
            "Both engines have COMPRESS/DECOMPRESS functions, but with different "
            "on-disk containers: SQL Server uses the GZIP format (RFC 1952) while "
            "MySQL uses raw zlib (RFC 1950) prefixed with a 4-byte little-endian "
            "uncompressed-length header. The compressed bytes are therefore not "
            "interchangeable — a blob produced by one engine will not DECOMPRESS "
            "on the other — and there is no built-in cross-container conversion, "
            "so the MySQL function is kept but the value is flagged as non-equal."
        ),
        example_case="ts-compress",
        divergence=(
            "Warned limit — the transpiled COMPRESS runs on MySQL but returns "
            "different bytes than SQL Server's GZIP output; DECOMPRESS on the "
            "matching engine still round-trips."
        ),
    ),
}
