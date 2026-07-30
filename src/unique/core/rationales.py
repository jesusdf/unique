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
    "UNIQUE-1080": _R(
        construct="Sequence CURRVAL — current value without advancing (→ T-SQL)",
        reason=(
            "T-SQL has NEXT VALUE FOR but no CURRVAL; there is no way to read a "
            "sequence's current value without advancing it."
        ),
        example_case="ora-seq-use",
        divergence="Warned limit — capture NEXT VALUE FOR in a variable instead.",
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
}
