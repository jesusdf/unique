# Diagnostic catalog (`UNIQUE-NNNN` warnings & errors)

> **Generated — do not edit by hand.** Produced by `python scripts/generate_reference_docs.py` from the `UNIQUE-NNNN` registry (`src/unique/core/diagnostics.py`) and the rationale side-table (`src/unique/core/rationales.py`). The CI freshness gate (`python scripts/generate_reference_docs.py --check`) fails the build if this file drifts from the source data.

One entry per stable diagnostic code the transpiler can emit. `code` is the grep/suppress token (`-- UNIQUE-1234: …`); every code is anchored as `warnings.md#unique-1234`. A code with a rationale entry (200 of 239) renders as a recipe: **Problem** (the triggering construct), **Solution (pointer)** (what Unique does about it — a pointer, not a worked example: the registry carries no SQL sample), **Discussion** (the engine-level reason no direct mapping exists) and **See Also** (the corpus case or test that proves it). The remaining codes render in a compact table marked `_(rationale pending)_` until a rationale is added (the coverage ratchet in `tests/unit/core/test_diagnostics.py` drives that count down).

## Diagnostics with a rationale

### <a id="unique-1001"></a>`UNIQUE-1001` — MERGE with one unconditional MATCHED UPDATE and one unconditional NOT MATCHED INSERT (→ MySQL)

**Category:** `statement` · **Message:** MERGE rewritten as INSERT ... ON DUPLICATE KEY UPDATE; requires a UNIQUE or PRIMARY KEY on ({on_cols}

**Problem.** MERGE with one unconditional MATCHED UPDATE and one unconditional NOT MATCHED INSERT (→ MySQL)

**Solution (pointer).** Faithful when a UNIQUE/PRIMARY KEY covers the ON columns (the common case); the key assumption is only noted, not verified against a live schema.

**Discussion.** MySQL has no MERGE statement at all; the canonical single-UPDATE/single-INSERT shape is the only one with a faithful MySQL rewrite (INSERT ... SELECT ... ON DUPLICATE KEY UPDATE), and that rewrite relies on a UNIQUE or PRIMARY KEY covering the ON columns to detect the 'matched' case the same way the MERGE's ON did.

**See Also.** [`TestMergeToMySQL::test_upsert_signals_key_assumption`](../../tests/unit/core/test_merge_mysql.py)

### <a id="unique-1002"></a>`UNIQUE-1002` — SET IDENTITY_INSERT ON/OFF (T-SQL)

**Category:** `statement` · **Message:** SET IDENTITY_INSERT {_ii_tbl} {_ii_st} is a T-SQL session directive with no cross-engine equivalent; dropped (the target accepts an explicit value into an identity/serial/ auto_increment column) (docs/03-unsupported.md

**Problem.** SET IDENTITY_INSERT ON/OFF (T-SQL)

**Solution (pointer).** The INSERT's data is faithful; the two SET directives degrade to carriers (one warning).

**Discussion.** T-SQL requires IDENTITY_INSERT ON before a script may supply its own value for an identity column; no other engine has an explicit identity-override mode — they simply accept an explicit value in the INSERT column list — so the ON/OFF bracket has nothing to map to.

**See Also.** [`reda-ts-identity-insert`](../../tests/fixtures/challenge/challenge_sqlserver.sql)

### <a id="unique-1003"></a>`UNIQUE-1003` — A source construct with no per-site conversion — the shared RawSQL fallback carrier (e.g. a SELECT-list set-returning function relocated to FROM, which MySQL has no inline table-function form for)

**Category:** `statement` · **Message:** statement preserved as a comment; the specific reason is carried at runtime

**Problem.** A source construct with no per-site conversion — the shared RawSQL fallback carrier (e.g. a SELECT-list set-returning function relocated to FROM, which MySQL has no inline table-function form for)

**Solution (pointer).** Warned limit — the statement is preserved as a comment; the base rows are unaffected on targets where the construct does map.

**Discussion.** This code is the converter's generic 'could not emit this node' escape valve — used at many unrelated call sites for whatever sqlglot reason string reaches it (an unmodeled expression type, a foreign built-in with no target form, a parse error) — so the concrete engine-level reason is carried in the comment text at runtime rather than fixed per code.

**See Also.** [`TestGenerateSeriesFrom::test_srf_in_select_list_moved_to_from`](../../tests/integration/test_challenge.py)

### <a id="unique-1004"></a>`UNIQUE-1004` — NULLS FIRST/LAST index-column ordering (→ Oracle/T-SQL/MySQL)

**Category:** `statement` · **Message:** NULLS FIRST/LAST index ordering has no {dialect} equivalent; dropped (it affects only the index's physical null order, not query results

**Problem.** NULLS FIRST/LAST index-column ordering (→ Oracle/T-SQL/MySQL)

**Solution (pointer).** Warned limit — physical null-order only, no result-set impact.

**Discussion.** NULLS FIRST/LAST in an index definition is Oracle-rejected outright (ORA-00907) and has no T-SQL/MySQL spelling at all; it affects only the index's physical null placement, not query results, so it is dropped rather than block the CREATE INDEX.

**See Also.** [`postgresql-drop2-NULLS`](../../tests/fixtures/challenge/challenge_postgresql.sql)

### <a id="unique-1005"></a>`UNIQUE-1005` — An index over an expression, e.g. CREATE INDEX ... ((concat(a, b))) (→ T-SQL)

**Category:** `statement` · **Message:** statement preserved as a comment; the specific reason is carried at runtime

**Problem.** An index over an expression, e.g. CREATE INDEX ... ((concat(a, b))) (→ T-SQL)

**Solution (pointer).** Warned limit — statement preserved as a comment; add a computed column and index it by hand.

**Discussion.** T-SQL has no expression/functional index at all — an index can only cover column names, not an arbitrary expression — so there is no CREATE INDEX form to target; a computed column plus an index on it is the closest workaround, but it is a schema change the transpiler cannot make unilaterally.

**See Also.** [`TestWave204ExpressionIndexes::test_expression_index_carrier_tsql`](../../tests/integration/test_pg_source_wave1.py)

### <a id="unique-1006"></a>`UNIQUE-1006` — A partial (WHERE-filtered) UNIQUE index whose predicate is outside T-SQL's filtered-index grammar

**Category:** `statement` · **Message:** {reason}

**Problem.** A partial (WHERE-filtered) UNIQUE index whose predicate is outside T-SQL's filtered-index grammar

**Solution (pointer).** Warned limit — statement preserved as a comment.

**Discussion.** T-SQL's filtered-index WHERE accepts only a narrow comparison grammar (error 10735 otherwise); a broader UNIQUE index (one covering more rows than the filtered original) would reject rows the source's partial index allowed, so widening it silently would change what INSERTs succeed — the whole CREATE INDEX degrades rather than emit a subtly different constraint.

**See Also.** [`TestIndexRebuildRefinements::test_complex_predicate_unique_degrades`](../../tests/integration/test_pg_source_wave1.py)

### <a id="unique-1007"></a>`UNIQUE-1007` — A partial (WHERE-filtered) non-unique index whose predicate is outside T-SQL's filtered-index grammar

**Category:** `statement` · **Message:** partial-index predicate dropped (no {dialect} filtered-index form); the index is broader than the source's: …

**Problem.** A partial (WHERE-filtered) non-unique index whose predicate is outside T-SQL's filtered-index grammar

**Solution (pointer).** Warned limit — the index is broader than the source's (covers more rows); query results are unaffected.

**Discussion.** T-SQL's filtered-index WHERE accepts only a narrow comparison grammar (error 10735 otherwise); unlike the UNIQUE case, a broader plain index changes no INSERT/UPDATE behavior — it only covers more rows than strictly needed — so the predicate is dropped and the (now unfiltered) index is kept rather than degrading the whole statement.

**See Also.** [`TestIndexRebuildRefinements::test_complex_predicate_nonunique_drops_where`](../../tests/integration/test_pg_source_wave1.py)

### <a id="unique-1008"></a>`UNIQUE-1008` — A plain (unfiltered) UNIQUE index on a nullable column (→ T-SQL)

**Category:** `statement` · **Message:** PostgreSQL unique indexes treat NULLs as distinct; T-SQL allows a single NULL per unique index

**Problem.** A plain (unfiltered) UNIQUE index on a nullable column (→ T-SQL)

**Solution (pointer).** Warned limit — a second NULL row that PostgreSQL allowed raises a duplicate-key error on T-SQL.

**Discussion.** PostgreSQL (and Oracle/MySQL) treat every NULL in a unique index as distinct from every other NULL, so multiple NULL rows are all allowed; T-SQL's UNIQUE index allows only a single NULL row — a genuine behavioral divergence with no rewrite that preserves PostgreSQL's semantics on T-SQL.

**See Also.** [`TestPgIndexToTsql::test_nameless_index_gets_a_name`](../../tests/integration/test_pg_source_wave1.py)

### <a id="unique-1009"></a>`UNIQUE-1009` — NOT applied to a non-predicate operand, e.g. (NOT NULL) IS NULL (→ T-SQL)

**Category:** `statement` · **Message:** T-SQL has no boolean value type; NOT of a non-predicate (e.g. NOT NULL) has no equivalent -- see docs/03-unsupported.md

**Problem.** NOT applied to a non-predicate operand, e.g. (NOT NULL) IS NULL (→ T-SQL)

**Solution (pointer).** Warned limit on T-SQL — the operand degrades to a carrier; faithful (1/TRUE) on the other three engines.

**Discussion.** PostgreSQL/MySQL/Oracle evaluate NOT under three-valued logic — the negation of NULL is still NULL — but T-SQL has no boolean value type at all: NOT requires a genuine predicate operand, so NOT of a bare NULL/column literal is error 4145, not a value.

**See Also.** [`pg-not-null-is-null`](../../tests/fixtures/challenge/challenge_postgresql.sql)

### <a id="unique-1010"></a>`UNIQUE-1010` — ALTER COLUMN ... TYPE on a column whose nullability the script never declares (→ T-SQL)

**Category:** `statement` · **Message:** T-SQL ALTER COLUMN defaults the column to NULL; the script does not define {table}.{col}'s nullability, so it cannot be re-stated — verify the column keeps its constraint

**Problem.** ALTER COLUMN ... TYPE on a column whose nullability the script never declares (→ T-SQL)

**Solution (pointer).** Warned limit — the ALTER COLUMN still runs (best-effort NULL); verify the column keeps its original constraint.

**Discussion.** T-SQL's ALTER COLUMN <type> re-states the FULL column definition and defaults to NULL when nullability is omitted, silently dropping an existing NOT NULL; without an in-script CREATE TABLE (or --db-url) to harvest the column's declared nullability from, the transpiler cannot know whether re-stating NULL is safe.

**See Also.** [`TestB10RunningColumnTypeAlterNullability::test_unknown_column_warns`](../../tests/integration/test_pg_source_wave1.py)

### <a id="unique-1011"></a>`UNIQUE-1011` — A T-SQL named DEFAULT constraint (CONSTRAINT df_x DEFAULT ...) on an ADD/ALTER COLUMN (→ MySQL/PostgreSQL/Oracle)

**Category:** `statement` · **Message:** named DEFAULT constraint {n} dropped (defaults are anonymous on this engine

**Problem.** A T-SQL named DEFAULT constraint (CONSTRAINT df_x DEFAULT ...) on an ADD/ALTER COLUMN (→ MySQL/PostgreSQL/Oracle)

**Solution (pointer).** Warned limit — the constraint's name is lost (nothing references it downstream); the default value and column definition are faithful.

**Discussion.** Only T-SQL names its DEFAULT constraints as a separate object; every other engine's DEFAULT is an anonymous column attribute with no CONSTRAINT <name> spelling at all, so the name has nothing to bind to and is dropped while the default value itself is kept.

**See Also.** [`test_named_default_constraint_dropped_with_note`](../../tests/integration/test_ddl_rename_dropindex.py)

### <a id="unique-1012"></a>`UNIQUE-1012` — A T-SQL CREATE INDEX ... INCLUDE (col, ...) covering-columns clause (→ MySQL/Oracle)

**Category:** `statement` · **Message:** {dialect} does not support INCLUDE covering columns; dropped: …

**Problem.** A T-SQL CREATE INDEX ... INCLUDE (col, ...) covering-columns clause (→ MySQL/Oracle)

**Solution (pointer).** Warned limit — the index no longer covers those columns; a query relying on them for an index-only scan now needs a table lookup (PostgreSQL keeps INCLUDE natively).

**Discussion.** INCLUDE columns are stored in the index leaf but excluded from its key/sort order (a covering-index optimization); MySQL and Oracle indexes have no non-key column list at all, so there is no clause to carry the covering columns to.

**See Also.** [`TestPortableIndex::test_include_index_flagged_elsewhere`](../../tests/integration/test_cross_dialect.py)

### <a id="unique-1013"></a>`UNIQUE-1013` — A filtered (WHERE-predicated) CREATE INDEX (→ MySQL/Oracle)

**Category:** `statement` · **Message:** {dialect} does not support filtered indexes; dropped predicate:…

**Problem.** A filtered (WHERE-predicated) CREATE INDEX (→ MySQL/Oracle)

**Solution (pointer).** Warned limit — the index now covers every row instead of just the filtered subset (PostgreSQL keeps the predicate natively).

**Discussion.** MySQL and Oracle have no partial/filtered index at all — an index always covers every row of the table — so the predicate has no clause to attach to.

**See Also.** [`TestPortableIndex::test_filtered_index_flagged_elsewhere`](../../tests/integration/test_cross_dialect.py)

### <a id="unique-1014"></a>`UNIQUE-1014` — Physical index storage clause, e.g. WITH (FILLFACTOR = n) (T-SQL)

**Category:** `statement` · **Message:** {clauses} -- tsql-only, no {dialect} equivalent (physical index clause

**Problem.** Physical index storage clause, e.g. WITH (FILLFACTOR = n) (T-SQL)

**Solution (pointer).** Faithful in result (storage-only); the clause is dropped and kept in a restorable note.

**Discussion.** FILLFACTOR and sibling physical clauses reserve per-page free space — a storage-tuning knob with no logical effect on query results; Oracle and MySQL CREATE INDEX have no equivalent clause.

**See Also.** [`reda-ts-index-fillfactor-mysql`](../../tests/fixtures/challenge/challenge_sqlserver.sql)

### <a id="unique-1015"></a>`UNIQUE-1015` — DISTINCT / ORDER BY over a string column under MySQL's default collation

**Category:** `statement` · **Message:** MySQL default collation is case-insensitive, so DISTINCT/ordering on a string column merges case-differing values

**Problem.** DISTINCT / ORDER BY over a string column under MySQL's default collation

**Solution (pointer).** Documented limit, warned — deduplicated row counts may differ.

**Discussion.** MySQL's default collation is case-insensitive, so DISTINCT / GROUP BY / ORDER BY treat 'a' and 'A' as equal and collapse them into one row; the case-sensitive PostgreSQL/Oracle defaults keep them distinct — a row-count divergence no ORDER BY LOWER() rewrite can bridge without column-level collation visibility.

**See Also.** [`my-distinct-case`](../../tests/fixtures/challenge/challenge_mysql.sql)

### <a id="unique-1016"></a>`UNIQUE-1016` — GROUP BY CUBE / ROLLUP / GROUPING SETS super-aggregate rows (→ MySQL)

**Category:** `statement` · **Message:** MySQL has no GROUP BY …; the base grouping is kept and the super-aggregate (subtotal) rows are omitted

**Problem.** GROUP BY CUBE / ROLLUP / GROUPING SETS super-aggregate rows (→ MySQL)

**Solution (pointer).** Warned — base grouping kept; subtotal rows omitted.

**Discussion.** MySQL has no CUBE / GROUPING SETS and only a trailing WITH ROLLUP, so a multi-element grouping's subtotal (super-aggregate) rows cannot be produced; only the base grouping is kept.

**See Also.** [`pg-grouping-fn`](../../tests/fixtures/challenge/challenge_postgresql.sql)

### <a id="unique-1017"></a>`UNIQUE-1017` — A multi-element GROUP BY combining CUBE/ROLLUP/GROUPING SETS in one clause, e.g. GROUP BY CUBE(a, b), ROLLUP(c) (→ MySQL)

**Category:** `statement` · **Message:** MySQL has no multi-element GROUP BY (CUBE/ROLLUP/ GROUPING SETS combined); the base grouping is kept and the super-aggregate (subtotal) rows are omitted

**Problem.** A multi-element GROUP BY combining CUBE/ROLLUP/GROUPING SETS in one clause, e.g. GROUP BY CUBE(a, b), ROLLUP(c) (→ MySQL)

**Solution (pointer).** Warned limit — the base grouping is kept but every super-aggregate (subtotal) row the combined CUBE/ROLLUP/GROUPING SETS would have produced is omitted.

**Discussion.** MySQL supports only a single trailing WITH ROLLUP modifier on the whole GROUP BY — it has no CUBE, no GROUPING SETS, and no way to combine multiple grouping elements — so a clause combining more than one such element has nothing to lower to beyond the plain column list.

**See Also.** [`pg-groupby-multi-cube-rollup`](../../tests/fixtures/challenge/challenge_postgresql.sql)

### <a id="unique-1018"></a>`UNIQUE-1018` — A top-level SELECT ... FOR XML / FOR JSON PATH row-serialization clause (T-SQL) (→ MySQL/PostgreSQL/Oracle)

**Category:** `statement` · **Message:** T-SQL FOR XML/JSON row serialization has no cross-engine equivalent; the clause is dropped and the base rows are returned instead (see docs/03-unsupported.md

**Problem.** A top-level SELECT ... FOR XML / FOR JSON PATH row-serialization clause (T-SQL) (→ MySQL/PostgreSQL/Oracle)

**Solution (pointer).** Warned limit — the clause is dropped and the plain multi-row/multi-column result set is returned instead of the single serialized scalar; rebuild the aggregation with the target's own JSON/XML functions if the scalar form is required.

**Discussion.** FOR XML/FOR JSON collapses the whole multi-row result set into a single XML or JSON scalar under T-SQL's own node-naming and null-omission rules; no other engine has a matching top-level row-serialization clause, so there is no faithful drop-in and shipping the base rows raw would silently turn one scalar row into many rows/columns.

**See Also.** [`reda-ts-for-json`](../../tests/fixtures/challenge/challenge_sqlserver.sql)

### <a id="unique-1019"></a>`UNIQUE-1019` — SQL_CALC_FOUND_ROWS on a SELECT with LIMIT (MySQL) → other engines

**Category:** `statement` · **Message:** MySQL SQL_CALC_FOUND_ROWS has no equivalent here; the full row count for a following FOUND_ROWS() is not computed — run a separate COUNT(*) query

**Problem.** SQL_CALC_FOUND_ROWS on a SELECT with LIMIT (MySQL) → other engines

**Solution (pointer).** Warned limit — the hint is dropped; run a separate COUNT(*) query for the discarded-row total.

**Discussion.** SQL_CALC_FOUND_ROWS is a MySQL-only optimizer hint that makes a following FOUND_ROWS() return the row count the LIMIT would otherwise have discarded; no other engine has an equivalent two-statement result-caching mechanism.

**See Also.** [`mysql-qdrop-SQL_CALC_FOU`](../../tests/fixtures/challenge/challenge_mysql.sql)

### <a id="unique-1020"></a>`UNIQUE-1020` — INSERT INTO t VALUES () — an all-defaults insert with no column list (→ Oracle)

**Category:** `statement` · **Message:** all-defaults INSERT has no Oracle spelling without the column list; original preserved

**Problem.** INSERT INTO t VALUES () — an all-defaults insert with no column list (→ Oracle)

**Solution (pointer).** Warned limit — statement preserved as a comment; supply an explicit column list to insert on Oracle.

**Discussion.** Oracle's INSERT grammar has no all-defaults form: a column-less VALUES () is rejected outright, and there is no DEFAULT VALUES keyword (T-SQL) or empty-parens shorthand (MySQL/PostgreSQL) to fall back on without knowing the table's column list.

**See Also.** [`TestEmptyValuesAndIsNullValue::test_empty_values_oracle_degrades`](../../tests/integration/test_pg_source_wave1.py)

### <a id="unique-1021"></a>`UNIQUE-1021` — An upsert (PG ON CONFLICT DO UPDATE-shaped) INSERT with no in-script conflict target to harvest

**Category:** `statement` · **Message:** INSERT preserved as a comment; the specific reason is carried at runtime

**Problem.** An upsert (PG ON CONFLICT DO UPDATE-shaped) INSERT with no in-script conflict target to harvest

**Solution (pointer).** Warned limit — statement preserved as a comment rather than a bare INSERT that would raise a duplicate-key error.

**Discussion.** PostgreSQL's ON CONFLICT DO UPDATE needs an explicit conflict target (column list or constraint); the source (e.g. a MySQL ON DUPLICATE KEY UPDATE, which names none) leaves it to be inferred from the table's declared key, and without an in-script CREATE TABLE (or --db-url) there is nothing to infer it from.

**See Also.** [`test_mysql_upsert_without_known_key_degrades_whole`](../../tests/unit/core/test_upsert.py)

### <a id="unique-1022"></a>`UNIQUE-1022` — MySQL INSERT ... ON DUPLICATE KEY UPDATE lowered to PostgreSQL ON CONFLICT (col) (or the MERGE ON clause)

**Category:** `statement` · **Message:** conflict target assumed to be (…) from the table's key; the MySQL source names no explicit target (fires on any unique key

**Problem.** MySQL INSERT ... ON DUPLICATE KEY UPDATE lowered to PostgreSQL ON CONFLICT (col) (or the MERGE ON clause)

**Solution (pointer).** Warned assumption — faithful when the harvested key is the one that would actually collide.

**Discussion.** MySQL's ON DUPLICATE KEY UPDATE names no explicit conflict target — it fires on any unique or primary key the row collides with — while PostgreSQL's ON CONFLICT and the MERGE ON clause both require one; the transpiler infers it from the table's declared key (visible in-script or via --db-url) and must flag that inference, since a different key could exist.

**See Also.** [`test_mysql_update_to_pg_needs_harvested_key`](../../tests/unit/core/test_upsert.py)

### <a id="unique-1023"></a>`UNIQUE-1023` — PostgreSQL ON CONFLICT DO NOTHING lowered to MySQL INSERT IGNORE

**Category:** `statement` · **Message:** INSERT IGNORE also swallows other errors (bad values, FK violations), not only duplicate keys — unlike PG ON CONFLICT DO NOTHING

**Problem.** PostgreSQL ON CONFLICT DO NOTHING lowered to MySQL INSERT IGNORE

**Solution (pointer).** Warned limit — faithful on a genuine duplicate key; a non-duplicate error that the source would raise is instead swallowed.

**Discussion.** MySQL's INSERT IGNORE is a broader error-suppressor than PostgreSQL's DO NOTHING (or the MERGE insert-only forms): it also swallows non-duplicate errors — bad values, foreign-key violations — that the source would have raised, so the mapping is the closest available but not behavior-identical on error.

**See Also.** [`test_pg_do_nothing_to_mysql_is_insert_ignore`](../../tests/unit/core/test_upsert.py)

### <a id="unique-1024"></a>`UNIQUE-1024` — PostgreSQL ON CONFLICT (col) DO UPDATE lowered to MySQL ON DUPLICATE KEY UPDATE

**Category:** `statement` · **Message:** MySQL ON DUPLICATE KEY UPDATE fires on ANY unique/primary key, not a single named conflict target

**Problem.** PostgreSQL ON CONFLICT (col) DO UPDATE lowered to MySQL ON DUPLICATE KEY UPDATE

**Solution (pointer).** Warned limit — faithful when the named conflict target is the table's only unique key.

**Discussion.** MySQL's ON DUPLICATE KEY UPDATE fires on a collision with ANY unique or primary key on the table, not only the single named conflict target the PostgreSQL source declared — a genuine any-key-vs-one-key semantic gap with no MySQL syntax to narrow it.

**See Also.** [`test_pg_update_to_mysql_uses_on_duplicate_key`](../../tests/unit/core/test_upsert.py)

### <a id="unique-1025"></a>`UNIQUE-1025` — MySQL INSERT ... ON DUPLICATE KEY UPDATE lowered to a T-SQL MERGE

**Category:** `statement` · **Message:** MERGE ON key assumed to be (…) from the table's key; the source names no explicit conflict target

**Problem.** MySQL INSERT ... ON DUPLICATE KEY UPDATE lowered to a T-SQL MERGE

**Solution (pointer).** Warned assumption — faithful when the harvested key is the one that would actually collide.

**Discussion.** MySQL's ON DUPLICATE KEY UPDATE names no explicit conflict column, but a MERGE's ON clause requires one; the transpiler assumes the table's declared key (harvested in-script or via --db-url) is the intended join column and must flag that assumption rather than silently pick a possibly-wrong key.

**See Also.** [`test_mysql_update_to_tsql_lowers_to_merge_with_harvested_key`](../../tests/unit/core/test_upsert.py)

### <a id="unique-1027"></a>`UNIQUE-1027` — A top-level (non-cursor-context) T-SQL @@ROWCOUNT reference (→ PostgreSQL/Oracle)

**Category:** `statement` · **Message:** @@ROWCOUNT has no top-level {dialect} equivalent

**Problem.** A top-level (non-cursor-context) T-SQL @@ROWCOUNT reference (→ PostgreSQL/Oracle)

**Solution (pointer).** Warned limit — degrades to the constant 0 (MySQL maps to ROW_COUNT() instead and is faithful).

**Discussion.** @@ROWCOUNT is context-free only inside T-SQL's own session state; outside a T-SQL procedural body (the procedural path maps it to GET DIAGNOSTICS / SQL%ROWCOUNT using surrounding statement context) there is nothing to map it to, so a bare top-level reference gets a documented neutral value instead.

**See Also.** [`TestSystemGlobalsInDml::test_rowcount_pg_neutral`](../../tests/integration/test_pg_source_wave1.py)

### <a id="unique-1028"></a>`UNIQUE-1028` — A top-level (non-cursor-context) T-SQL @@FETCH_STATUS reference (→ PostgreSQL/Oracle/MySQL)

**Category:** `statement` · **Message:** @@FETCH_STATUS has no top-level {dialect} equivalent; it is cursor state

**Problem.** A top-level (non-cursor-context) T-SQL @@FETCH_STATUS reference (→ PostgreSQL/Oracle/MySQL)

**Solution (pointer).** Warned limit — degrades to the constant 0 outside cursor context.

**Discussion.** @@FETCH_STATUS is cursor state by nature — the procedural path maps it using the surrounding FETCH's context (FOUND / handler flags / cursor%FOUND) — so a context-free top-level reference has nothing to bind to and gets a documented neutral instead.

**See Also.** [`TestFetchStatusTopLevel::test_fetch_status_neutral_pg`](../../tests/integration/test_pg_source_wave1.py)

### <a id="unique-1030"></a>`UNIQUE-1030` — T-SQL @@VERSION (→ PostgreSQL/MySQL)

**Category:** `statement` · **Message:** @@VERSION -> {fn}; version string differs per engine

**Problem.** T-SQL @@VERSION (→ PostgreSQL/MySQL)

**Solution (pointer).** Warned limit — mapped to the target's native version function; the string value differs from T-SQL's.

**Discussion.** PostgreSQL's version() and MySQL's VERSION() return each engine's own version string in its own format, never T-SQL's — the closest available function, but the returned value can never equal the source's.

**See Also.** [`ts-spid-version`](../../tests/fixtures/challenge/challenge_sqlserver.sql)

### <a id="unique-1031"></a>`UNIQUE-1031` — T-SQL @@VERSION (→ Oracle)

**Category:** `statement` · **Message:** @@VERSION has no Oracle equivalent outside v$version

**Problem.** T-SQL @@VERSION (→ Oracle)

**Solution (pointer).** Warned limit — degrades to NULL rather than a fabricated version string.

**Discussion.** Oracle's version string lives only in the v$version view, which needs a query (and often elevated privileges) — not a scalar expression a statement can splice in — so there is no drop-in replacement expression at all.

**See Also.** [`ts-spid-version`](../../tests/fixtures/challenge/challenge_sqlserver.sql)

### <a id="unique-1032"></a>`UNIQUE-1032` — T-SQL @@SPID (→ PostgreSQL/MySQL/Oracle)

**Category:** `statement` · **Message:** @@SPID -> {fn}; session id differs per engine

**Problem.** T-SQL @@SPID (→ PostgreSQL/MySQL/Oracle)

**Solution (pointer).** Warned limit — mapped to the target's own session-id function; the numeric value differs from T-SQL's.

**Discussion.** Every engine spells its session/connection identifier differently (PostgreSQL pg_backend_pid(), MySQL CONNECTION_ID(), Oracle SYS_CONTEXT('USERENV','SID')) and the value is inherently per-connection, so it can never equal T-SQL's @@SPID even when mapped to the engine's closest equivalent.

**See Also.** [`ts-spid-version`](../../tests/fixtures/challenge/challenge_sqlserver.sql)

### <a id="unique-1033"></a>`UNIQUE-1033` — Oracle SQL%ROWCOUNT used in a re-evaluated loop or EXIT condition (WHILE SQL%ROWCOUNT > 0 / EXIT WHEN SQL%ROWCOUNT = 0) (→ PostgreSQL)

**Category:** `statement` · **Message:** SQL%ROWCOUNT has no top-level {dialect} equivalent

**Problem.** Oracle SQL%ROWCOUNT used in a re-evaluated loop or EXIT condition (WHILE SQL%ROWCOUNT > 0 / EXIT WHEN SQL%ROWCOUNT = 0) (→ PostgreSQL)

**Solution (pointer).** Warned limit — degrades to the constant 0; T-SQL and MySQL read the row count inline natively and are unaffected.

**Discussion.** PostgreSQL reads the last statement's row count only through the GET DIAGNOSTICS statement, not an inline expression; a single hoisted capture placed before the loop would freeze the value instead of re-reading it each iteration the way SQL%ROWCOUNT does, so a condition re-evaluated every pass cannot be captured with one hoist and has no faithful inline substitute (a reference in the loop body, or in a single-evaluated position like an IF/assignment/RETURN, is captured by a hoisted local and never reaches this code).

**See Also.** [`TestLoopConditionDegrades::test_while_condition_kept_as_carrier`](../../tests/integration/test_oracle_rowcount_hoist_b37.py)

### <a id="unique-1034"></a>`UNIQUE-1034` — TABLESAMPLE (→ MySQL)

**Category:** `statement` · **Message:** TABLESAMPLE ({what}) has no MySQL equivalent — all rows returned (docs/03-unsupported.md

**Problem.** TABLESAMPLE (→ MySQL)

**Solution (pointer).** Warned limit — all rows are returned instead of a sample.

**Discussion.** MySQL has no row-sampling clause at all (and sampling is inherently non-deterministic besides), so there is no way to return a subset of rows equivalent to the source's sample.

**See Also.** [`pg-tablesample`](../../tests/fixtures/challenge/challenge_postgresql.sql)

### <a id="unique-1037"></a>`UNIQUE-1037` — TOP ... WITH TIES (T-SQL) / FETCH FIRST ... WITH TIES (→ MySQL)

**Category:** `statement` · **Message:** source had WITH TIES; MySQL has no equivalent — rows tying the last one are not returned (see docs/03-unsupported.md

**Problem.** TOP ... WITH TIES (T-SQL) / FETCH FIRST ... WITH TIES (→ MySQL)

**Solution (pointer).** Warned limit — rows tying the last returned row are not included (PostgreSQL/Oracle FETCH FIRST ... WITH TIES are faithful).

**Discussion.** MySQL's LIMIT has no WITH TIES equivalent — it caps at a fixed row count with no provision for including rows that tie the last one on the ORDER BY key.

**See Also.** [`ts-top-with-ties`](../../tests/fixtures/challenge/challenge_sqlserver.sql)

### <a id="unique-1038"></a>`UNIQUE-1038` — TOP n PERCENT (T-SQL) → PostgreSQL/MySQL

**Category:** `statement` · **Message:** source was TOP n PERCENT; {dialect} has no LIMIT PERCENT — emitted as a row count, adjust to CEIL(n/100 * total_rows) if a true percentage is required

**Problem.** TOP n PERCENT (T-SQL) → PostgreSQL/MySQL

**Solution (pointer).** Warned limit — n is emitted as a literal row count, not n percent of the actual result size; adjust with CEIL(n/100 * total_rows) if a true percentage is required.

**Discussion.** PostgreSQL's LIMIT and MySQL's LIMIT both take a row count, not a percentage of the result set's size — and the result set's size is not knowable at transpile time (it depends on the query's own WHERE/JOIN), so n cannot be converted to an equivalent row count without executing the query first.

**See Also.** [`TestParseSelectLimit::test_top_percent_postgresql_documented`](../../tests/unit/core/test_converter.py)

### <a id="unique-1039"></a>`UNIQUE-1039` — Oracle TIMESTAMP WITH LOCAL TIME ZONE column (→ PostgreSQL)

**Category:** `ddl` · **Message:** Oracle WITH LOCAL TIME ZONE and PostgreSQL timestamptz both display column {name} in the session time zone (same instant, session-dependent wall clock) (docs/03-unsupported.md

**Problem.** Oracle TIMESTAMP WITH LOCAL TIME ZONE column (→ PostgreSQL)

**Solution (pointer).** Faithful — same instant, same session-dependent wall-clock display.

**Discussion.** PostgreSQL timestamptz has the identical session-time-zone display behaviour as Oracle's LTZ (live-verified: the same instant shows 12:00 in a UTC session and 07:00 in a New York session), so the column maps directly rather than losing anything.

**See Also.** [`ora-dttypes`](../../tests/fixtures/challenge/challenge_oracle.sql)

### <a id="unique-1040"></a>`UNIQUE-1040` — Oracle TIMESTAMP WITH LOCAL TIME ZONE column (→ T-SQL)

**Category:** `ddl` · **Message:** tsql has no session-local timestamp type — column {name} WITH LOCAL TIME ZONE maps to DATETIMEOFFSET; the value's instant is kept but the session-time-zone display is not reproduced (docs/03-unsupported.md

**Problem.** Oracle TIMESTAMP WITH LOCAL TIME ZONE column (→ T-SQL)

**Solution (pointer).** Warned limit — the value's instant is kept, but the session-time-zone display is not reproduced.

**Discussion.** T-SQL has no session-local timestamp type; the column maps to DATETIMEOFFSET, which keeps a fixed stored offset instead of re-deriving the session's own time zone on every read.

**See Also.** [`ora-dttypes`](../../tests/fixtures/challenge/challenge_oracle.sql)

### <a id="unique-1041"></a>`UNIQUE-1041` — Oracle TIMESTAMP WITH LOCAL TIME ZONE column (→ MySQL)

**Category:** `ddl` · **Message:** mysql has no session-local timestamp type — column {name} WITH LOCAL TIME ZONE maps to TIMESTAMP; the value's instant is kept but the session-time-zone display is not reproduced (docs/03-unsupported.md

**Problem.** Oracle TIMESTAMP WITH LOCAL TIME ZONE column (→ MySQL)

**Solution (pointer).** Warned limit — the value's instant is kept, but the session-time-zone display is not reproduced.

**Discussion.** MySQL has no session-local timestamp type; the column maps to TIMESTAMP, which normalizes to UTC storage instead of re-deriving the session's own time zone on every read.

**See Also.** [`ora-dttypes`](../../tests/fixtures/challenge/challenge_oracle.sql)

### <a id="unique-1042"></a>`UNIQUE-1042` — A TIME/TIMETZ column (→ Oracle)

**Category:** `ddl` · **Message:** Oracle has no TIME type — column … stores the time of day as INTERVAL DAY TO SECOND{tz} (docs/03-unsupported.md

**Problem.** A TIME/TIMETZ column (→ Oracle)

**Solution (pointer).** Faithful for TIME (the same time-of-day value, stored as a duration); warned limit for TIMETZ — the zone offset is dropped.

**Discussion.** Oracle has no bare TIME (or TIME WITH TIME ZONE) column type, so the time-of-day value is stored as INTERVAL DAY TO SECOND (a duration since midnight) instead.

**See Also.** [`pg-dttypes`](../../tests/fixtures/challenge/challenge_postgresql.sql)

### <a id="unique-1043"></a>`UNIQUE-1043` — A bare PostgreSQL INTERVAL column, with no YEAR TO MONTH/DAY TO SECOND qualifier (→ Oracle)

**Category:** `ddl` · **Message:** PostgreSQL INTERVAL mixes year-month and day-second fields; column … is mapped to INTERVAL DAY TO SECOND — year-month values need a separate INTERVAL YEAR TO MONTH column (docs/03-unsupported.md

**Problem.** A bare PostgreSQL INTERVAL column, with no YEAR TO MONTH/DAY TO SECOND qualifier (→ Oracle)

**Solution (pointer).** Warned limit — year-month values need a separate INTERVAL YEAR TO MONTH column on Oracle.

**Discussion.** PostgreSQL's INTERVAL mixes year-month and day-second fields in one value; Oracle splits INTERVAL into two distinct column types, so the column maps to INTERVAL DAY TO SECOND and any year-month component has nowhere to go.

**See Also.** [`pg-dttypes`](../../tests/fixtures/challenge/challenge_postgresql.sql)

### <a id="unique-1044"></a>`UNIQUE-1044` — An INTERVAL column (→ T-SQL / MySQL)

**Category:** `ddl` · **Message:** {dialect} has no INTERVAL column type — column … keeps the interval as text (docs/03-unsupported.md

**Problem.** An INTERVAL column (→ T-SQL / MySQL)

**Solution (pointer).** Warned limit — the value is kept as text, not usable in interval arithmetic on the target.

**Discussion.** T-SQL has no interval type at all, and MySQL's INTERVAL is only an arithmetic qualifier (e.g. INTERVAL 1 DAY), never a column type, so the interval value is kept as text instead.

**See Also.** [`ora-tz-interval`](../../tests/fixtures/challenge/challenge_oracle.sql)

### <a id="unique-1045"></a>`UNIQUE-1045` — A fractional-seconds column precision above 6 (DATETIME(n)/TIMESTAMP(n)/TIME(n) with n>6) (→ MySQL)

**Category:** `ddl` · **Message:** MySQL fractional-seconds precision caps at 6 — column … precision … clamped to 6 (docs/03-unsupported.md

**Problem.** A fractional-seconds column precision above 6 (DATETIME(n)/TIMESTAMP(n)/TIME(n) with n>6) (→ MySQL)

**Solution (pointer).** Warned limit — precision clamped to 6; sub-microsecond digits lost.

**Discussion.** MySQL's sub-second precision caps at microseconds (6 digits); a higher source precision (e.g. T-SQL DATETIME2(7)) has no wider MySQL fractional-seconds type to map onto.

**See Also.** [`ts-datetimeoffset`](../../tests/fixtures/challenge/challenge_sqlserver.sql)

### <a id="unique-1046"></a>`UNIQUE-1046` — MySQL multi-bit BIT(n>1) column (→ Oracle / T-SQL)

**Category:** `ddl` · **Message:** {dialect} has no bit-string type — column … BIT(…) stores its numeric value as {mapped} (docs/03-unsupported.md

**Problem.** MySQL multi-bit BIT(n>1) column (→ Oracle / T-SQL)

**Solution (pointer).** Warned limit — the numeric value is preserved but the bit-string type semantics (bitwise operations, display) are not.

**Discussion.** Neither engine has a bit-string column type; a multi-bit BIT is a 64-bit numeric value, not a boolean, so it maps to a wide NUMBER/NUMERIC that holds the same value instead.

**See Also.** [`my-bintypes`](../../tests/fixtures/challenge/challenge_mysql.sql)

### <a id="unique-1048"></a>`UNIQUE-1048` — T-SQL structure-clone CREATE TABLE t2 LIKE t1 (→ T-SQL / Oracle)

**Category:** `ddl` · **Message:** LIKE clone copies column structure only here; the source's indexes/keys are not cloned

**Problem.** T-SQL structure-clone CREATE TABLE t2 LIKE t1 (→ T-SQL / Oracle)

**Solution (pointer).** Warned limit — the source's indexes/keys are not cloned.

**Discussion.** T-SQL/Oracle have no native CREATE TABLE ... LIKE; the faithful idiom is an empty SELECT INTO / CTAS (WHERE 1 = 0), which clones column structure only — indexes, keys and constraints are not part of that idiom.

**See Also.** [`TestCreateTableLikeClone::test_like_tsql_empty_select_into`](../../tests/integration/test_pg_source_wave1.py)

### <a id="unique-1049"></a>`UNIQUE-1049` — IDENTITY / GENERATED AS IDENTITY with a non-default START/INCREMENT (→ MySQL)

**Category:** `ddl` · **Message:** source IDENTITY (START {seed} INCREMENT {step}) has no MySQL column form — AUTO_INCREMENT starts at 1, steps by 1 (docs/03-unsupported.md

**Problem.** IDENTITY / GENERATED AS IDENTITY with a non-default START/INCREMENT (→ MySQL)

**Solution (pointer).** Warned limit — AUTO_INCREMENT starts at 1 and steps by 1.

**Discussion.** MySQL's only identity form is AUTO_INCREMENT, whose seed is a table option (AUTO_INCREMENT = n) with no per-column START/INCREMENT — a non-default seed/step cannot be reproduced as a column clause.

**See Also.** [`ora-identity-opts`](../../tests/fixtures/challenge/challenge_oracle.sql)

### <a id="unique-1050"></a>`UNIQUE-1050` — MySQL column-level ON UPDATE CURRENT_TIMESTAMP auto-refresh clause (→ other engines)

**Category:** `ddl` · **Message:** MySQL ON UPDATE column clause has no equivalent on the target engine

**Problem.** MySQL column-level ON UPDATE CURRENT_TIMESTAMP auto-refresh clause (→ other engines)

**Solution (pointer).** Warned limit — the column keeps its DEFAULT but is no longer auto-refreshed; add a trigger to restore the behaviour.

**Discussion.** No other engine has a column-level auto-refresh-on-update clause; the behaviour can only be reproduced there with an explicit AFTER UPDATE trigger.

**See Also.** [`mysql-drop2-ON`](../../tests/fixtures/challenge/challenge_mysql.sql)

### <a id="unique-1051"></a>`UNIQUE-1051` — A column-level COLLATE clause (→ a different target engine)

**Category:** `ddl` · **Message:** column {col_name} collation/charset (…) has no portable {dialect} equivalent; the column uses the default collation (comparisons/ordering may differ) — set it explicitly on the target or supply the source DB connection

**Problem.** A column-level COLLATE clause (→ a different target engine)

**Solution (pointer).** Warned limit — the column uses the target's default collation; comparisons/ordering may differ.

**Discussion.** Collation names are engine-specific catalog identifiers with no cross-engine mapping; without a live database connection, Unique cannot resolve what collation the source column actually uses.

**See Also.** [`postgresql-drop4-COLLATE`](../../tests/fixtures/challenge/challenge_postgresql.sql)

### <a id="unique-1052"></a>`UNIQUE-1052` — MySQL/Oracle INVISIBLE column attribute (→ PostgreSQL / T-SQL)

**Category:** `ddl` · **Message:** column {col_name} was INVISIBLE (excluded from SELECT *) on the source; {dialect} has no invisible-column attribute, so the column is now visible to SELECT * (docs/03-unsupported.md

**Problem.** MySQL/Oracle INVISIBLE column attribute (→ PostgreSQL / T-SQL)

**Solution (pointer).** Warned limit — the column becomes visible to SELECT *, changing that query's result shape.

**Discussion.** PostgreSQL and T-SQL have no invisible-column attribute (a column excluded from SELECT *), so it cannot be reproduced there.

**See Also.** [`red2-my-invisible-column-drop`](../../tests/fixtures/challenge/challenge_mysql.sql)

### <a id="unique-1053"></a>`UNIQUE-1053` — PostgreSQL UNIQUE ... NULLS NOT DISTINCT (→ other engines)

**Category:** `ddl` · **Message:** PostgreSQL UNIQUE … NULLS NOT DISTINCT (NULLs compare equal) has no {dialect} equivalent; a plain UNIQUE treats NULLs as distinct (docs/03-unsupported.md

**Problem.** PostgreSQL UNIQUE ... NULLS NOT DISTINCT (→ other engines)

**Solution (pointer).** Warned limit — degrades to a plain UNIQUE; multiple NULL rows become allowed on the target.

**Discussion.** Only PostgreSQL 15+ has a NULLS NOT DISTINCT unique-constraint modifier (NULLs compare equal, so only one NULL row is allowed); every other engine's UNIQUE always treats NULLs as distinct.

**See Also.** [`pg-unique-nulls-notdistinct`](../../tests/fixtures/challenge/challenge_postgresql.sql)

### <a id="unique-1054"></a>`UNIQUE-1054` — Cascading referential action on a self-referencing FK (→ T-SQL)

**Category:** `ddl` · **Message:** T-SQL forbids a cascading action on a self-referencing FK (error 1785); downgraded to NO ACTION — emulate with an AFTER trigger if the automatic action is required (docs/03-unsupported.md

**Problem.** Cascading referential action on a self-referencing FK (→ T-SQL)

**Solution (pointer).** Warned limit — downgraded to ON DELETE NO ACTION; emulate the cascade with an AFTER trigger.

**Discussion.** T-SQL rejects a cascading action on a self-referencing foreign key outright (error 1785 at CREATE TABLE time) — an engine restriction, not a missing feature.

**See Also.** [`my-self-fk`](../../tests/fixtures/challenge/challenge_mysql.sql)

### <a id="unique-1055"></a>`UNIQUE-1055` — Foreign-key ON DELETE SET DEFAULT referential action (→ Oracle)

**Category:** `ddl` · **Message:** Oracle has no ON DELETE SET DEFAULT referential action; dropped (FK reverts to NO ACTION) — emulate with an AFTER DELETE trigger if required (docs/03-unsupported.md

**Problem.** Foreign-key ON DELETE SET DEFAULT referential action (→ Oracle)

**Solution (pointer).** Warned limit — the action is dropped (FK reverts to NO ACTION); emulate with an AFTER DELETE trigger if required.

**Discussion.** Oracle foreign keys support only CASCADE/SET NULL/NO ACTION — SET DEFAULT raises ORA-03001 ('unimplemented feature') if shipped verbatim.

**See Also.** [`red2-pg-fk-ondelete-setdefault-oracle`](../../tests/fixtures/challenge/challenge_postgresql.sql)

### <a id="unique-1056"></a>`UNIQUE-1056` — T-SQL In-Memory OLTP table storage option(s) (MEMORY_OPTIMIZED / DURABILITY) (→ other engines)

**Category:** `ddl` · **Message:** T-SQL In-Memory OLTP storage option(s) [{opts}] have no {dialect} equivalent; the table is created as a regular disk-based table (no logical/value difference

**Problem.** T-SQL In-Memory OLTP table storage option(s) (MEMORY_OPTIMIZED / DURABILITY) (→ other engines)

**Solution (pointer).** Faithful (storage-only) — the table becomes a regular disk-based table with the same logical content.

**Discussion.** No other engine has an in-memory table storage mode; the option is a physical-storage clause with no logical effect on query results.

**See Also.** [`tsql-drop5-MEMORY_OPTIM`](../../tests/fixtures/challenge/)

### <a id="unique-1057"></a>`UNIQUE-1057` — MySQL table-level default COLLATE/CHARSET clause (→ other engines)

**Category:** `ddl` · **Message:** MySQL table default collation/charset (…) has no portable {dialect} equivalent; string columns use the default collation (comparisons/ordering may differ) — set it explicitly on the target or supply the source DB connection

**Problem.** MySQL table-level default COLLATE/CHARSET clause (→ other engines)

**Solution (pointer).** Warned limit — string columns use the target's default collation.

**Discussion.** Same underlying gap as UNIQUE-1051 but table-scoped: collation names are engine-specific and unresolvable without a live database connection.

**See Also.** [`mysql-drop5-utf8mb4`](../../tests/fixtures/challenge/challenge_mysql.sql)

### <a id="unique-1058"></a>`UNIQUE-1058` — A non-portable CREATE VIEW modifier (e.g. SCHEMABINDING, ALGORITHM=, DEFINER=, SQL SECURITY) with no native form on the target

**Category:** `ddl` · **Message:** view modifier {mod} is not portable on {dialect}; dropped

**Problem.** A non-portable CREATE VIEW modifier (e.g. SCHEMABINDING, ALGORITHM=, DEFINER=, SQL SECURITY) with no native form on the target

**Solution (pointer).** Warned limit — the modifier is dropped; the view's query and columns are otherwise faithful.

**Discussion.** These modifiers are single-engine syntax with no equivalent option elsewhere (MATERIALIZED is handled separately, natively, on Oracle/PostgreSQL, so it never reaches this drop).

**See Also.** [`red2-pg-matview-oracle-falsewarn`](../../tests/fixtures/challenge/challenge_postgresql.sql)

### <a id="unique-1059"></a>`UNIQUE-1059` — DROP SEQUENCE (→ MySQL)

**Category:** `ddl` · **Message:** MySQL has no sequences (use an AUTO_INCREMENT column); original preserved

**Problem.** DROP SEQUENCE (→ MySQL)

**Solution (pointer).** Warned limit — degrades to a documented carrier; the original statement is preserved as a comment.

**Discussion.** MySQL has no sequence object at all (identity is expressed only via AUTO_INCREMENT columns), so there is nothing for a DROP SEQUENCE to target.

**See Also.** [`TestDropSequenceMySql::test_mysql_degrades_to_documented_carrier`](../../tests/integration/test_oracle_mysql_tail.py)

### <a id="unique-1060"></a>`UNIQUE-1060` — DROP TYPE (→ MySQL)

**Category:** `ddl` · **Message:** MySQL has no user-defined types; original preserved

**Problem.** DROP TYPE (→ MySQL)

**Solution (pointer).** Warned limit — degrades to a documented carrier; the original statement is preserved.

**Discussion.** MySQL has no user-defined type in any form (no CREATE TYPE/DOMAIN equivalent), so a DROP TYPE has nothing to target.

**See Also.** [`TestMysqlUserTypesDegrade::test_drop_type_degrades_mysql`](../../tests/integration/test_pg_source_wave1.py)

### <a id="unique-1061"></a>`UNIQUE-1061` — A DROP INDEX <name> with no owning table (→ T-SQL / MySQL)

**Category:** `ddl` · **Message:** {dialect} DROP INDEX requires the owning table, which the source statement does not carry; original preserved

**Problem.** A DROP INDEX <name> with no owning table (→ T-SQL / MySQL)

**Solution (pointer).** Warned limit — degrades to a documented carrier rather than shipping a syntactically incomplete DROP INDEX.

**Discussion.** T-SQL and MySQL both require the owning table in DROP INDEX (index names are table-scoped there); Oracle/PostgreSQL index names are schema-scoped, so a source statement from either carries no table for the target to require.

**See Also.** [`test_drop_index_without_table_never_ships_invalid`](../../tests/integration/test_ddl_rename_dropindex.py)

### <a id="unique-1062"></a>`UNIQUE-1062` — A schema-scoped DROP TRIGGER <name> with no owning table (→ PostgreSQL)

**Category:** `ddl` · **Message:** PostgreSQL DROP TRIGGER requires the owning table (ON tbl), which the source statement does not carry; original preserved

**Problem.** A schema-scoped DROP TRIGGER <name> with no owning table (→ PostgreSQL)

**Solution (pointer).** Warned limit — degrades to a documented carrier; the original statement is preserved.

**Discussion.** PostgreSQL trigger names are per-table (DROP TRIGGER requires ON <table>); T-SQL/MySQL/Oracle trigger names are schema-scoped, so a source statement from any of them carries no table to supply.

**See Also.** [`TestDropTriggerOnTable::test_sourceless_on_degrades_to_pg`](../../tests/integration/test_pg_source_wave1.py)

### <a id="unique-1063"></a>`UNIQUE-1063` — A construct with no cross-engine mapping, kept as a documented carrier (e.g. T-SQL AT TIME ZONE, or the T-SQL CLR spatial '::' method-call operator)

**Category:** `expression` · **Message:** … (…) — see docs/03-unsupported.md

**Problem.** A construct with no cross-engine mapping, kept as a documented carrier (e.g. T-SQL AT TIME ZONE, or the T-SQL CLR spatial '::' method-call operator)

**Solution (pointer).** Warned limit — degrades to NULL + annotation; valid only on the source engine.

**Discussion.** The generic degrade path for a value Unique recognizes but cannot compute on another engine — used e.g. for AT TIME ZONE (Oracle/MySQL have no such operator; PostgreSQL/T-SQL's own session-tz-dependent display differs) and T-SQL's geometry/geography '::' static-method call (no other engine has CLR types).

**See Also.** [`ts-at-time-zone`](../../tests/fixtures/challenge/challenge_sqlserver.sql)

### <a id="unique-1064"></a>`UNIQUE-1064` — Oracle bare SESSIONTIMEZONE global (→ other engines)

**Category:** `expression` · **Message:** Oracle SESSIONTIMEZONE is session- dependent; the mapped expression reports this session's zone/offset in the target's own format (docs/03-unsupported.md

**Problem.** Oracle bare SESSIONTIMEZONE global (→ other engines)

**Solution (pointer).** Warned limit — the value is session-dependent on the target too and may not match the source session's zone.

**Discussion.** SESSIONTIMEZONE reports the connecting session's own UTC offset — a per-session value with no fixed cross-engine equivalent; the mapped expression reports the TARGET session's own zone in its native format instead.

**See Also.** [`ora-tz-funcs`](../../tests/fixtures/challenge/challenge_oracle.sql)

### <a id="unique-1065"></a>`UNIQUE-1065` — CAST(... AS TIME) and other Oracle-absent value types

**Category:** `expression` · **Message:** Oracle has no {_what} type — value kept as text (docs/03-unsupported.md

**Problem.** CAST(... AS TIME) and other Oracle-absent value types

**Solution (pointer).** Warned limit — value kept as text.

**Discussion.** Oracle has no bare TIME (or plain INTERVAL) type, so the value is kept as text with a documented carrier rather than an invalid cast.

**See Also.** [`my-cast-time`](../../tests/fixtures/challenge/challenge_mysql.sql)

### <a id="unique-1066"></a>`UNIQUE-1066` — MySQL JSON type / CAST(... AS JSON)

**Category:** `expression` · **Message:** MySQL JSON type has no faithful cross-engine equivalent (T-SQL has no JSON type; canonical JSON spacing differs on PG/Oracle) — value kept as text — see docs/03-unsupported.md

**Problem.** MySQL JSON type / CAST(... AS JSON)

**Solution (pointer).** Warned limit — value kept as text.

**Discussion.** MySQL's JSON type has no faithful cross-engine equivalent — T-SQL has no JSON type at all, and canonical JSON spacing differs on PostgreSQL/Oracle — so the value is kept as text.

**See Also.** [`my-cast-json`](../../tests/fixtures/challenge/challenge_mysql.sql)

### <a id="unique-1067"></a>`UNIQUE-1067` — PostgreSQL geometric type (point/line/…) cast or column

**Category:** `expression` · **Message:** PostgreSQL geometric type … has no cross-engine equivalent — value kept as text (docs/03-unsupported.md

**Problem.** PostgreSQL geometric type (point/line/…) cast or column

**Solution (pointer).** Warned limit — value kept as text.

**Discussion.** PostgreSQL's geometric types have no cross-engine model (MySQL's spatial POINT is a different WKB type), so the value is kept as text.

**See Also.** [`pg-cast-point`](../../tests/fixtures/challenge/challenge_postgresql.sql)

### <a id="unique-1068"></a>`UNIQUE-1068` — A PostgreSQL numeric NaN/Infinity literal cast to a numeric type (→ MySQL / T-SQL / Oracle)

**Category:** `expression` · **Message:** PostgreSQL NaN/Infinity has no {dialect} numeric equivalent (docs/03-unsupported.md

**Problem.** A PostgreSQL numeric NaN/Infinity literal cast to a numeric type (→ MySQL / T-SQL / Oracle)

**Solution (pointer).** Warned limit — the carrier documents that the value cannot be reproduced numerically on the target.

**Discussion.** Only PostgreSQL's numeric type has a NaN/Infinity value; MySQL/T-SQL/Oracle DECIMAL/NUMBER silently collapse a 'NaN' cast to 0, so the special value has no faithful representation there.

**See Also.** [`pg-nan-cmp`](../../tests/fixtures/challenge/challenge_postgresql.sql)

### <a id="unique-1069"></a>`UNIQUE-1069` — MySQL UNSIGNED integer type / CAST(... AS UNSIGNED)

**Category:** `expression` · **Message:** MySQL UNSIGNED has no {dialect} equivalent; unsigned wraparound not preserved (docs/03-unsupported.md

**Problem.** MySQL UNSIGNED integer type / CAST(... AS UNSIGNED)

**Solution (pointer).** Warned limit — unsigned wraparound not preserved.

**Discussion.** No other engine has an UNSIGNED integer type; the value is mapped to a signed NUMERIC/NUMBER, so unsigned wraparound semantics are not preserved.

**See Also.** [`my-cast-convert`](../../tests/fixtures/challenge/challenge_mysql.sql)

### <a id="unique-1071"></a>`UNIQUE-1071` — A scalar subquery serialized via T-SQL FOR XML/JSON (→ other engines)

**Category:** `expression` · **Message:** T-SQL FOR XML/JSON row serialization has no cross-engine equivalent — see docs/03-unsupported.md

**Problem.** A scalar subquery serialized via T-SQL FOR XML/JSON (→ other engines)

**Solution (pointer).** Warned limit — degrades to NULL + annotation.

**Discussion.** FOR XML/JSON row-serialization inside a (SELECT ... FOR XML/JSON) scalar subquery has no cross-engine equivalent; dropping only the clause would ship the multi-column rows raw into a scalar context (ORA-00913 'too many values'), so the whole scalar degrades instead.

**See Also.** [`ts-for-xml`](../../tests/fixtures/challenge/challenge_sqlserver.sql)

### <a id="unique-1073"></a>`UNIQUE-1073` — MySQL date arithmetic on a non-datetime string literal (e.g. DATE_ADD('not-a-date', INTERVAL ...))

**Category:** `expression` · **Message:** MySQL date arithmetic on a non-datetime string literal yields NULL (docs/03-unsupported.md

**Problem.** MySQL date arithmetic on a non-datetime string literal (e.g. DATE_ADD('not-a-date', INTERVAL ...))

**Solution (pointer).** Warned limit — the value folds to NULL to match MySQL's own behaviour.

**Discussion.** MySQL's own date-arithmetic functions yield NULL when the first argument doesn't parse as a date/time value; folding the literal at transpile time reproduces that NULL rather than emitting an invalid cast on another engine.

**See Also.** [`my-timestr-plus`](../../tests/fixtures/challenge/challenge_mysql.sql)

### <a id="unique-1074"></a>`UNIQUE-1074` — MySQL DATE - DATE subtraction

**Category:** `expression` · **Message:** MySQL DATE - DATE is a numeric YYYYMMDD subtraction; normalized to a day count (docs/03-unsupported.md

**Problem.** MySQL DATE - DATE subtraction

**Solution (pointer).** Warned limit — normalized to a day count rather than MySQL's own YYYYMMDD arithmetic result.

**Discussion.** MySQL's DATE - DATE operator is a numeric YYYYMMDD subtraction (e.g. 2020-03-01 - 2020-01-01 = 200), not a day count; the meaningful day-count value (60, matching every other engine's date subtraction) is emitted instead.

**See Also.** [`my-date-diff-minus`](../../tests/fixtures/challenge/challenge_mysql.sql)

### <a id="unique-1075"></a>`UNIQUE-1075` — timestamp - timestamp subtraction (→ T-SQL / MySQL)

**Category:** `expression` · **Message:** timestamp difference is an INTERVAL with no {dialect} equivalent; emitted as a SECOND count (docs/03-unsupported.md

**Problem.** timestamp - timestamp subtraction (→ T-SQL / MySQL)

**Solution (pointer).** Warned limit — a SECOND count replaces the source's INTERVAL value (same information, different type).

**Discussion.** PostgreSQL/Oracle timestamp subtraction yields an INTERVAL; T-SQL and MySQL have no interval value type, so the difference is computed as a SECOND count via DATEDIFF/TIMESTAMPDIFF instead.

**See Also.** [`TestTimestampDifferenceDegrade::test_tsql_and_mysql_degrade_with_warning`](../../tests/integration/test_challenge.py)

### <a id="unique-1076"></a>`UNIQUE-1076` — LISTAGG(...) WITHIN GROUP (...) OVER (...) — windowed string aggregation (Oracle)

**Category:** `expression` · **Message:** windowed string aggregation (string-agg OVER …) has no {dialect} equivalent — see docs/03-unsupported.md

**Problem.** LISTAGG(...) WITHIN GROUP (...) OVER (...) — windowed string aggregation (Oracle)

**Solution (pointer).** Warned limit — degrades to a NULL value plus annotation.

**Discussion.** T-SQL STRING_AGG and MySQL GROUP_CONCAT can never carry an OVER clause, and PostgreSQL rejects an ORDER-BY aggregate used as a window function — there is no running-string-aggregate form to target.

**See Also.** [`ora-listagg-over`](../../tests/fixtures/challenge/challenge_oracle.sql)

### <a id="unique-1077"></a>`UNIQUE-1077` — GROUPS window frame (PostgreSQL / Oracle)

**Category:** `expression` · **Message:** a GROUPS window frame has no {dialect} equivalent (only ROWS/RANGE, and no faithful rewrite with ORDER-BY ties) — see docs/03-unsupported.md

**Problem.** GROUPS window frame (PostgreSQL / Oracle)

**Solution (pointer).** Warned limit on T-SQL/MySQL — degrades to a NULL carrier; faithful on Oracle/PostgreSQL.

**Discussion.** T-SQL and MySQL implement only ROWS and RANGE frame units; a GROUPS frame spans whole peer groups, and no ROWS/RANGE combination reproduces that boundary when the ORDER BY key has ties.

**See Also.** [`pg-window-groups-frame`](../../tests/fixtures/challenge/challenge_postgresql.sql)

### <a id="unique-1078"></a>`UNIQUE-1078` — A window frame EXCLUDE clause (CURRENT ROW / GROUP / TIES) (→ T-SQL / MySQL)

**Category:** `expression` · **Message:** a window frame … has no {dialect} equivalent (T-SQL/MySQL have no EXCLUDE, and no faithful ROWS/RANGE rewrite) — see docs/03-unsupported.md

**Problem.** A window frame EXCLUDE clause (CURRENT ROW / GROUP / TIES) (→ T-SQL / MySQL)

**Solution (pointer).** Warned limit on T-SQL/MySQL — degrades to a NULL carrier; faithful on PostgreSQL/Oracle, which support EXCLUDE natively.

**Discussion.** T-SQL and MySQL implement no EXCLUDE option on a window frame at all, and there is no faithful ROWS/RANGE rewrite that reproduces excluding specific peer rows from the frame.

**See Also.** [`red2-pg-window-exclude-current`](../../tests/fixtures/challenge/challenge_postgresql.sql)

### <a id="unique-1080"></a>`UNIQUE-1080` — Sequence CURRVAL — current value without advancing (→ T-SQL)

**Category:** `expression` · **Message:** T-SQL has no sequence CURRVAL; capture NEXT VALUE FOR {seq} in a variable — see docs/03-unsupported.md

**Problem.** Sequence CURRVAL — current value without advancing (→ T-SQL)

**Solution (pointer).** Warned limit — capture NEXT VALUE FOR in a variable instead.

**Discussion.** T-SQL has NEXT VALUE FOR but no CURRVAL; there is no way to read a sequence's current value without advancing it.

**See Also.** [`ora-seq-use`](../../tests/fixtures/challenge/challenge_oracle.sql)

### <a id="unique-1082"></a>`UNIQUE-1082` — An empty-string result on Oracle ('' ≡ NULL)

**Category:** `expression` · **Message:** Oracle stores an empty string as NULL (docs/03-unsupported.md)

**Problem.** An empty-string result on Oracle ('' ≡ NULL)

**Solution (pointer).** Warned limit — the empty string surfaces as Oracle NULL.

**Discussion.** Oracle has no on-disk representation for an empty string distinct from NULL — an empty-string result becomes NULL — so a value that is '' on other engines cannot be reproduced there.

**See Also.** [`pg-repeat-negative`](../../tests/fixtures/challenge/challenge_postgresql.sql)

### <a id="unique-1083"></a>`UNIQUE-1083` — DATEPART(WEEKDAY, d) (T-SQL)

**Category:** `expression` · **Message:** DATEPART(WEEKDAY) is @@DATEFIRST-dependent; converted assuming the session default (Sunday=1

**Problem.** DATEPART(WEEKDAY, d) (T-SQL)

**Solution (pointer).** Warned — correct under the default @@DATEFIRST = 7; a session that changed DATEFIRST will see a different result.

**Discussion.** DATEPART(WEEKDAY) depends on the session @@DATEFIRST setting, which Unique cannot observe at transpile time; the conversion assumes the T-SQL default (Sunday = 1).

**See Also.** [`reda-ts-datepart-weekday`](../../tests/fixtures/challenge/challenge_sqlserver.sql)

### <a id="unique-1084"></a>`UNIQUE-1084` — Oracle ROUND(date, fmt) — a date rounded to the nearest fmt boundary (→ other engines)

**Category:** `expression` · **Message:** Oracle ROUND(date, '{fmt}') (nearest {fmt} boundary) has no faithful {dialect} equivalent — the value was not computed (docs/03-unsupported.md

**Problem.** Oracle ROUND(date, fmt) — a date rounded to the nearest fmt boundary (→ other engines)

**Solution (pointer).** Warned limit — degrades to a NULL carrier; not computed off Oracle.

**Discussion.** No other engine has a nearest-boundary date-rounding function; only Oracle's own ROUND(date, fmt) computes this, so the general case (any fmt) has no cross-engine formula.

**See Also.** [`red2-ora-round-date-fmt`](../../tests/fixtures/challenge/challenge_oracle.sql)

### <a id="unique-1085"></a>`UNIQUE-1085` — Oracle TRUNC(date, fmt) with a format model that has no portable truncation (e.g. 'W' week-of-month)

**Category:** `expression` · **Message:** Oracle TRUNC(date, '{raw_up}') has no {dialect} equivalent — the value was not computed (docs/03-unsupported.md

**Problem.** Oracle TRUNC(date, fmt) with a format model that has no portable truncation (e.g. 'W' week-of-month)

**Solution (pointer).** Warned limit — degrades to a NULL carrier off Oracle; native TRUNC is kept on Oracle.

**Discussion.** Most Oracle TRUNC format models map to a portable truncation unit (day, month, year, ISO week, ...), but a few (like 'W', week-of-the-month) have no equivalent boundary on any other engine.

**See Also.** [`red2-ora-trunc-format-unmapped`](../../tests/fixtures/challenge/challenge_oracle.sql)

### <a id="unique-1087"></a>`UNIQUE-1087` — Oracle INSTR with a non-literal occurrence count or a non-literal backward (negative-start) search

**Category:** `expression` · **Message:** Oracle INSTR with an occurrence count or backward (negative-start) search has no portable equivalent for non-literal arguments — see docs/03-unsupported.md

**Problem.** Oracle INSTR with a non-literal occurrence count or a non-literal backward (negative-start) search

**Solution (pointer).** Warned limit — degrades to a NULL carrier for the non-literal case; literal arguments still fold to the correct value.

**Discussion.** INSTR's occurrence/backward-search semantics fold to the engine-agnostic computed value only when every argument is a literal (at transpile time); a non-literal (column/expression) argument cannot be folded, and no other engine's positional-search function reproduces Oracle's occurrence/backward semantics directly.

**See Also.** [`TestLiteralFolds::test_oracle_instr_nonliteral_degrades`](../../tests/integration/test_challenge.py)

### <a id="unique-1088"></a>`UNIQUE-1088` — MySQL UpdateXML() (→ other engines)

**Category:** `expression` · **Message:** MySQL UpdateXML has no cross-engine equivalent (PG lacks it; T-SQL .modify() and Oracle UPDATEXML differ) — see docs/03-unsupported.md

**Problem.** MySQL UpdateXML() (→ other engines)

**Solution (pointer).** Warned limit.

**Discussion.** UpdateXML has no cross-engine equivalent — PostgreSQL lacks it, and T-SQL .modify() / Oracle UPDATEXML differ in shape and semantics.

**See Also.** [`my-xml-fns`](../../tests/fixtures/challenge/challenge_mysql.sql)

### <a id="unique-1089"></a>`UNIQUE-1089` — COLLATION(x) — the collation name of a value (→ other engines)

**Category:** `expression` · **Message:** collation names are engine-specific and cannot match across engines (docs/03-unsupported.md

**Problem.** COLLATION(x) — the collation name of a value (→ other engines)

**Solution (pointer).** Warned limit — the source's engine-specific collation name is preserved but will not match the target's naming.

**Discussion.** Collation names are engine-specific catalog identifiers (e.g. MySQL's utf8mb4_0900_ai_ci vs Oracle's NLS-based names) with no cross-engine mapping, even though the function itself exists on multiple engines.

**See Also.** [`my-collation-fn`](../../tests/fixtures/challenge/challenge_mysql.sql)

### <a id="unique-1090"></a>`UNIQUE-1090` — Oracle REGEXP_SUBSTR capture-group extraction (6th arg) (→ MySQL)

**Category:** `expression` · **Message:** Oracle REGEXP_SUBSTR capture-group extraction (6th arg) has no MySQL equivalent (docs/03-unsupported.md

**Problem.** Oracle REGEXP_SUBSTR capture-group extraction (6th arg) (→ MySQL)

**Solution (pointer).** Warned limit — capture-group extraction not reproduced.

**Discussion.** MySQL's REGEXP_SUBSTR has no capture-group argument, so the sub-group extraction cannot be expressed; the portable (str, pat, pos, occ) subset is emitted.

**See Also.** [`ora-regexp-group`](../../tests/fixtures/challenge/challenge_oracle.sql)

### <a id="unique-1091"></a>`UNIQUE-1091` — Oracle TRANSLATE(s, from, to) (→ MySQL)

**Category:** `expression` · **Message:** MySQL has no TRANSLATE and a nested-REPLACE emulation is order-dependent (not equivalent) — see docs/03-unsupported.md

**Problem.** Oracle TRANSLATE(s, from, to) (→ MySQL)

**Solution (pointer).** Warned limit — degrades to a NULL carrier on MySQL; native and faithful on PostgreSQL/T-SQL.

**Discussion.** TRANSLATE is native on PostgreSQL/T-SQL, but MySQL has no TRANSLATE function; a nested-REPLACE emulation is order-dependent (each REPLACE can rematch a previous substitution's output) and is not equivalent to TRANSLATE's simultaneous single-pass character mapping.

**See Also.** [`ora-translate3`](../../tests/fixtures/challenge/challenge_oracle.sql)

### <a id="unique-1092"></a>`UNIQUE-1092` — SUBSTRING(x FROM POSIX-regex-pattern) (→ T-SQL)

**Category:** `expression` · **Message:** SUBSTRING(x FROM POSIX pattern) has no T-SQL regex equivalent — see docs/03-unsupported.md

**Problem.** SUBSTRING(x FROM POSIX-regex-pattern) (→ T-SQL)

**Solution (pointer).** Warned limit — degrades to a NULL carrier on T-SQL; faithful on Oracle/MySQL via REGEXP_SUBSTR.

**Discussion.** T-SQL has no POSIX regular-expression engine, so a POSIX-pattern SUBSTRING (native on Oracle REGEXP_SUBSTR / MySQL) has no equivalent there.

**See Also.** [`pg-substring-regex`](../../tests/fixtures/challenge/challenge_postgresql.sql)

### <a id="unique-1093"></a>`UNIQUE-1093` — SUBSTRING(x FROM SIMILAR-TO-pattern FOR escape) — the SQL-standard regex form

**Category:** `expression` · **Message:** SUBSTRING(x FROM SIMILAR-TO pattern FOR escape) has no cross-engine equivalent (SQL-regex metachars differ from POSIX) — see docs/03-unsupported.md

**Problem.** SUBSTRING(x FROM SIMILAR-TO-pattern FOR escape) — the SQL-standard regex form

**Solution (pointer).** Warned limit — degrades to a NULL carrier.

**Discussion.** The SQL-standard SIMILAR TO pattern syntax uses different metacharacters (%, _, #"..."# capture markers) than POSIX regex, so no faithful cross-engine rewrite exists on engines whose regex functions expect POSIX syntax.

**See Also.** [`pg-substring-escape`](../../tests/fixtures/challenge/challenge_postgresql.sql)

### <a id="unique-1094"></a>`UNIQUE-1094` — An empty-string function result on Oracle (e.g. SUBSTR yielding '')

**Category:** `expression` · **Message:** Oracle stores an empty string as NULL (docs/03-unsupported.md

**Problem.** An empty-string function result on Oracle (e.g. SUBSTR yielding '')

**Solution (pointer).** Warned limit — the empty string surfaces as Oracle NULL.

**Discussion.** The same underlying limit as Oracle's NULL-equals-empty-string storage (UNIQUE-1082/1207), applied to a computed (not stored) empty-string result — Oracle collapses it to NULL at the point of computation too.

**See Also.** [`my-fsubstr`](../../tests/fixtures/challenge/challenge_mysql.sql)

### <a id="unique-1095"></a>`UNIQUE-1095` — MySQL VALUES(col) used outside an INSERT ... ON DUPLICATE KEY UPDATE statement

**Category:** `expression` · **Message:** MySQL VALUES(col) outside INSERT … ON DUPLICATE KEY UPDATE is NULL

**Problem.** MySQL VALUES(col) used outside an INSERT ... ON DUPLICATE KEY UPDATE statement

**Solution (pointer).** Faithful — matches MySQL's own out-of-context NULL behaviour.

**Discussion.** MySQL's VALUES(col) function only has meaning inside the ON DUPLICATE KEY UPDATE clause of the very INSERT it appears in (reading the row that would have been inserted); used elsewhere (e.g. inside a stored procedure's ordinary UPDATE) it is NULL on MySQL itself, so the transpiler reproduces that NULL.

**See Also.** [`TestWave223ValuesFnOutfile::test_values_fn_null_oracle`](../../tests/integration/test_pg_source_wave1.py)

### <a id="unique-1096"></a>`UNIQUE-1096` — EXTRACT(EPOCH FROM interval) (PostgreSQL)

**Category:** `expression` · **Message:** EXTRACT(EPOCH FROM interval) has no portable equivalent (T-SQL/MySQL have no interval value type) — see docs/03-unsupported.md

**Problem.** EXTRACT(EPOCH FROM interval) (PostgreSQL)

**Solution (pointer).** Warned limit — degrades to NULL + annotation (EPOCH FROM a timestamp is still computed).

**Discussion.** T-SQL and MySQL have no interval value type, so the epoch (total seconds) of an interval value has no portable equivalent.

**See Also.** [`pg-epoch`](../../tests/fixtures/challenge/challenge_postgresql.sql)

### <a id="unique-1097"></a>`UNIQUE-1097` — EXTRACT(MICROSECONDS FROM TIME) (→ Oracle)

**Category:** `expression` · **Message:** EXTRACT(MICROSECONDS FROM TIME) has no Oracle equivalent (no TIME type) — see docs/03-unsupported.md

**Problem.** EXTRACT(MICROSECONDS FROM TIME) (→ Oracle)

**Solution (pointer).** Warned limit.

**Discussion.** Oracle has no TIME type, so the microseconds field of a TIME value has no Oracle equivalent.

**See Also.** [`pg-frac-seconds`](../../tests/fixtures/challenge/challenge_postgresql.sql)

### <a id="unique-1098"></a>`UNIQUE-1098` — PostgreSQL format() with a %I/%L specifier, a width, or a positional argument (→ other engines)

**Category:** `expression` · **Message:** PG format() with %L/width/positional specifiers has no cross-engine equivalent — see docs/03-unsupported.md

**Problem.** PostgreSQL format() with a %I/%L specifier, a width, or a positional argument (→ other engines)

**Solution (pointer).** Warned limit — degrades to a NULL carrier; a %s-only template still rewrites faithfully.

**Discussion.** Only the plain %s-only template has a portable rewrite (string concatenation); %I (quoted identifier) and %L (quoted literal) specifiers, width modifiers and positional (%1$s) arguments have no equivalent formatting primitive on other engines.

**See Also.** [`TestFormatFunc::test_complex_spec_degrades`](../../tests/integration/test_challenge.py)

### <a id="unique-1099"></a>`UNIQUE-1099` — PostgreSQL sha256()/sha512() (→ other engines)

**Category:** `expression` · **Message:** PG sha256/sha512 returns a bytea digest; other engines return a hex string (same digest, different representation) — see docs/03-unsupported.md

**Problem.** PostgreSQL sha256()/sha512() (→ other engines)

**Solution (pointer).** Warned limit — degrades to a NULL carrier; md5() and other hash functions with matching representations still map faithfully.

**Discussion.** PostgreSQL's sha256/sha512 return a bytea digest, while every other engine's equivalent hash function returns a hex-encoded string — the underlying digest is identical, but the representation differs and cannot be reconciled without an explicit encode() the source SQL doesn't have.

**See Also.** [`pg-hash-fns`](../../tests/fixtures/challenge/challenge_postgresql.sql)

### <a id="unique-1100"></a>`UNIQUE-1100` — MySQL CHAR(n) as a numeric-to-byte-string function

**Category:** `expression` · **Message:** MySQL CHAR({_n}) is a multi-byte byte string, not a single code point (docs/03-unsupported.md

**Problem.** MySQL CHAR(n) as a numeric-to-byte-string function

**Solution (pointer).** Warned limit — carrier flags the byte-string vs code-point difference.

**Discussion.** MySQL's CHAR(n) returns a multi-byte byte string (CHAR(256) = the 2-byte string 0x0100), not a single Unicode code point like CHR/NCHAR, so the two cannot be equated.

**See Also.** [`my-char-256`](../../tests/fixtures/challenge/challenge_mysql.sql)

### <a id="unique-1101"></a>`UNIQUE-1101` — A data-modifying CTE, e.g. WITH ins AS (INSERT ... RETURNING ...) SELECT ... (PostgreSQL) → T-SQL

**Category:** `statement` · **Message:** {_cte_reason}

**Problem.** A data-modifying CTE, e.g. WITH ins AS (INSERT ... RETURNING ...) SELECT ... (PostgreSQL) → T-SQL

**Solution (pointer).** Warned limit — statement preserved as a comment.

**Discussion.** T-SQL's WITH only introduces read-only query CTEs — an INSERT/UPDATE/DELETE/MERGE inside a WITH body is invalid there — so a data-modifying CTE has no T-SQL spelling at all.

**See Also.** [`TestZeroPushW7Batch::test_data_modifying_cte_carrier_tsql`](../../tests/unit/core/test_ir_first_families.py)

### <a id="unique-1103"></a>`UNIQUE-1103` — SELECT ... FOR SHARE — a shared row lock (→ Oracle)

**Category:** `statement` · **Message:** FOR SHARE (shared row lock) has no Oracle equivalent (Oracle SELECT locking is FOR UPDATE, exclusive); the shared lock is dropped (docs/03-unsupported.md

**Problem.** SELECT ... FOR SHARE — a shared row lock (→ Oracle)

**Solution (pointer).** Warned limit — the shared lock is dropped.

**Discussion.** Oracle SELECT locking is FOR UPDATE (exclusive) only — it has no shared-row-lock mode — so the shared lock cannot be reproduced.

**See Also.** [`my-for-share`](../../tests/fixtures/challenge/challenge_mysql.sql)

### <a id="unique-1104"></a>`UNIQUE-1104` — Oracle FOR UPDATE WAIT <n> — a bounded lock wait

**Category:** `statement` · **Message:** Oracle FOR UPDATE WAIT <n> (bounded lock wait) has no {dialect} equivalent; it blocks with the default behavior (docs/03-unsupported.md

**Problem.** Oracle FOR UPDATE WAIT <n> — a bounded lock wait

**Solution (pointer).** Warned limit — it blocks with the target's default behavior.

**Discussion.** PostgreSQL/MySQL offer only FOR UPDATE / NOWAIT / SKIP LOCKED, with no bounded-wait timeout, so the WAIT <n> bound has no equivalent.

**See Also.** [`ora-forupdate-wait`](../../tests/fixtures/challenge/challenge_oracle.sql)

### <a id="unique-1105"></a>`UNIQUE-1105` — Oracle FOR UPDATE OF <column> (→ PostgreSQL/MySQL)

**Category:** `statement` · **Message:** Oracle FOR UPDATE OF <column> selects which table's rows to lock; {dialect} FOR UPDATE OF takes table names, so the OF list is dropped (every row read is locked) (docs/03-unsupported.md

**Problem.** Oracle FOR UPDATE OF <column> (→ PostgreSQL/MySQL)

**Solution (pointer).** Warned limit — the source's column name is dropped rather than leaked unchanged into a table-name position.

**Discussion.** Oracle's FOR UPDATE OF names a COLUMN, selecting which joined table's rows to lock via the column's owning table; PostgreSQL and MySQL's FOR UPDATE OF instead takes a TABLE/alias name directly — an incompatible argument shape, not just a renaming.

**See Also.** [`reda-ora-forupdate-of-col`](../../tests/fixtures/challenge/challenge_oracle.sql)

### <a id="unique-1108"></a>`UNIQUE-1108` — ADD CONSTRAINT ... NOT VALID (PostgreSQL, deferred validation) → T-SQL/Oracle/MySQL

**Category:** `statement` · **Message:** {dialect} has no ALTER … NOT VALID; the constraint is validated immediately (PostgreSQL defers it

**Problem.** ADD CONSTRAINT ... NOT VALID (PostgreSQL, deferred validation) → T-SQL/Oracle/MySQL

**Solution (pointer).** Warned limit — the constraint definition is identical; the target validates existing rows immediately instead of deferring.

**Discussion.** Only PostgreSQL can add a constraint without validating existing rows against it immediately; T-SQL, Oracle and MySQL all validate an added constraint at ADD time, with no deferred-validation mode to opt into.

**See Also.** [`pg-alter-notvalid`](../../tests/fixtures/challenge/challenge_postgresql.sql)

### <a id="unique-1109"></a>`UNIQUE-1109` — TRUNCATE ... CASCADE (PostgreSQL, also truncates FK-dependent tables) → MySQL/T-SQL

**Category:** `statement` · **Message:** TRUNCATE … CASCADE (also truncates FK-dependent tables) has no {dialect} equivalent; only this table is truncated — truncate any dependents explicitly

**Problem.** TRUNCATE ... CASCADE (PostgreSQL, also truncates FK-dependent tables) → MySQL/T-SQL

**Solution (pointer).** Warned limit — only the named table is truncated; truncate dependent tables explicitly.

**Discussion.** Only Oracle's TRUNCATE has a CASCADE option matching PostgreSQL's; MySQL and T-SQL TRUNCATE truncate only the named table, with no mechanism to also truncate its FK-dependent tables in one statement.

**See Also.** [`pg-truncate-restart`](../../tests/fixtures/challenge/challenge_postgresql.sql)

### <a id="unique-1110"></a>`UNIQUE-1110` — ALTER COLUMN ... TYPE t USING <non-trivial expression> (PostgreSQL) → T-SQL

**Category:** `statement` · **Message:** {dialect} has no ALTER COLUMN … USING conversion expression; convert the data manually. Statement preserved as a comment

**Problem.** ALTER COLUMN ... TYPE t USING <non-trivial expression> (PostgreSQL) → T-SQL

**Solution (pointer).** Warned limit — statement preserved as a comment; convert the data manually.

**Discussion.** T-SQL's ALTER COLUMN has no USING conversion-expression clause at all — it can only re-cast to the new type using the engine's own implicit conversion, with no way to run an arbitrary expression over the existing data during the ALTER.

**See Also.** [`TestWave199CteDeleteUsingAlterUsing::test_alter_using_expression_carriers`](../../tests/integration/test_pg_source_wave1.py)

### <a id="unique-1112"></a>`UNIQUE-1112` — ADD COLUMN ... GENERATED ALWAYS AS IDENTITY / SERIAL (→ MySQL)

**Category:** `statement` · **Message:** MySQL's only identity form is AUTO_INCREMENT (must be a key; a UNIQUE index is added

**Problem.** ADD COLUMN ... GENERATED ALWAYS AS IDENTITY / SERIAL (→ MySQL)

**Solution (pointer).** Faithful, with an added UNIQUE index noted as a MySQL-specific requirement, not part of the source schema.

**Discussion.** MySQL's only identity form is AUTO_INCREMENT, which MySQL additionally requires to be a key (error 1075 otherwise) — a constraint PostgreSQL/Oracle identity columns do not share — so a UNIQUE index must be synthesized alongside the column.

**See Also.** [`pg-add-identity`](../../tests/fixtures/challenge/challenge_postgresql.sql)

### <a id="unique-1113"></a>`UNIQUE-1113` — A GIN/GiST/BRIN index (PostgreSQL) → T-SQL/MySQL/Oracle

**Category:** `statement` · **Message:** PostgreSQL GIN/GiST/BRIN index has no {dialect} equivalent (access-method specific); index omitted — queries run unindexed (docs/03-unsupported.md

**Problem.** A GIN/GiST/BRIN index (PostgreSQL) → T-SQL/MySQL/Oracle

**Solution (pointer).** Warned limit — the index is omitted; queries that relied on it run unindexed.

**Discussion.** GIN/GiST/BRIN are PostgreSQL-specific access methods (inverted, generalized-search-tree, block-range) with no equivalent index type on the other three engines — the choice of access method is inherently engine-specific, unlike a plain B-tree index.

**See Also.** [`pg-gin-jsonb`](../../tests/fixtures/challenge/challenge_postgresql.sql)

### <a id="unique-1114"></a>`UNIQUE-1114` — An expression index over a column that maps to a LOB type on the target

**Category:** `statement` · **Message:** expression index over a LOB-typed column is invalid on {dialect} (ORA-02327 / MySQL functional-index restriction); index omitted — queries run unindexed (docs/03-unsupported.md

**Problem.** An expression index over a column that maps to a LOB type on the target

**Solution (pointer).** Warned limit — the index is omitted; queries that relied on it run unindexed.

**Discussion.** A source TEXT/CLOB-mapped column used inside an index expression is invalid on the target once the type maps to a LOB (Oracle ORA-02327 forbids a LOB in a function-based index; MySQL's functional-index grammar has the same restriction).

**See Also.** [`pg-expr-index`](../../tests/fixtures/challenge/challenge_postgresql.sql)

### <a id="unique-1115"></a>`UNIQUE-1115` — CREATE INDEX CONCURRENTLY (PostgreSQL's non-locking index build) → T-SQL/MySQL

**Category:** `statement` · **Message:** CONCURRENTLY (PostgreSQL's non-locking index build) has no {dialect} equivalent; the index is created with the target's default locking

**Problem.** CREATE INDEX CONCURRENTLY (PostgreSQL's non-locking index build) → T-SQL/MySQL

**Solution (pointer).** Faithful in result; the index is built with the target's default (locking) behavior instead.

**Discussion.** CONCURRENTLY is a PostgreSQL build-strategy option (avoids locking the table during the build); T-SQL and MySQL have no matching keyword — the resulting index is identical, only the build-time locking behavior differs.

**See Also.** [`postgresql-drop2-CONCURRENTLY`](../../tests/fixtures/challenge/challenge_postgresql.sql)

### <a id="unique-1116"></a>`UNIQUE-1116` — SET @@var = ... — a MySQL system-variable assignment via the @@ form (→ PostgreSQL/T-SQL/Oracle)

**Category:** `statement` · **Message:** MySQL session setting has no {dialect} equivalent; configure the session natively.

**Problem.** SET @@var = ... — a MySQL system-variable assignment via the @@ form (→ PostgreSQL/T-SQL/Oracle)

**Solution (pointer).** Warned limit — statement preserved as a comment; configure the session natively on the target.

**Discussion.** MySQL's @@ system variables (session or global) are engine-local tuning knobs (sql_mode, server_id, ...) with no meaning on any other engine — every other engine either lacks the setting or spells session configuration a completely different way.

**See Also.** [`TestMysqlSessionKnobsDegrade::test_knob_degrades`](../../tests/integration/test_pg_source_wave1.py)

### <a id="unique-1118"></a>`UNIQUE-1118` — CREATE TEMPORARY SEQUENCE (PostgreSQL) → T-SQL/MySQL/Oracle

**Category:** `statement` · **Message:** {dialect} has no TEMPORARY sequences; statement preserved as a comment

**Problem.** CREATE TEMPORARY SEQUENCE (PostgreSQL) → T-SQL/MySQL/Oracle

**Solution (pointer).** Warned limit — statement preserved as a comment.

**Discussion.** A session-scoped (TEMPORARY) sequence exists only on PostgreSQL; T-SQL and Oracle sequences are always permanent schema objects, and MySQL has no sequences at all, so there is no target form that preserves the session-scoping.

**See Also.** [`TestZeroPushZ4bBatch::test_temporary_sequence_carriers`](../../tests/unit/core/test_ir_first_families.py)

### <a id="unique-1119"></a>`UNIQUE-1119` — CREATE SEQUENCE (→ MySQL)

**Category:** `statement` · **Message:** MySQL has no sequences; use an AUTO_INCREMENT column instead. Original

**Problem.** CREATE SEQUENCE (→ MySQL)

**Solution (pointer).** Warned limit — statement preserved as a comment; use an AUTO_INCREMENT column instead.

**Discussion.** MySQL has no sequence object at all; an AUTO_INCREMENT column is the closest idiom, but it is a column property, not a free-standing, shareable object the way a sequence is, so CREATE SEQUENCE has no direct MySQL statement to become.

**See Also.** [`red2-pg-nextval-false-unmap`](../../tests/fixtures/challenge/challenge_postgresql.sql)

### <a id="unique-1122"></a>`UNIQUE-1122` — USE <database> (T-SQL/MySQL) → PostgreSQL/Oracle

**Category:** `statement` · **Message:** {dialect} has no USE statement; connect to the target database/schema instead.

**Problem.** USE <database> (T-SQL/MySQL) → PostgreSQL/Oracle

**Solution (pointer).** Warned limit — statement preserved as a comment; connect to the target database/schema instead.

**Discussion.** USE switches the active database within a single connection on T-SQL and MySQL; PostgreSQL has no SQL-level equivalent (only the psql client meta-command \c, which reconnects) and Oracle has none at all (a schema is a database user, selected at connect time).

**See Also.** [`TestCrossDialectDDL::test_use_statement_documented_where_unsupported`](../../tests/integration/test_cross_dialect.py)

### <a id="unique-1123"></a>`UNIQUE-1123` — ALTER COLUMN ... SET STORAGE {PLAIN|EXTERNAL|EXTENDED|MAIN} (PostgreSQL) → T-SQL/MySQL/Oracle

**Category:** `statement` · **Message:** PostgreSQL column STORAGE tuning has no {dialect} equivalent; statement preserved as a comment

**Problem.** ALTER COLUMN ... SET STORAGE {PLAIN|EXTERNAL|EXTENDED|MAIN} (PostgreSQL) → T-SQL/MySQL/Oracle

**Solution (pointer).** Faithful in result (storage-only); statement preserved as a comment off PostgreSQL.

**Discussion.** SET STORAGE tunes PostgreSQL's internal TOAST compression/out-of-line storage strategy for a column — an engine-internal physical-storage knob with no logical effect on query results and no equivalent concept on any other engine.

**See Also.** [`TestWave132Batch::test_set_storage_degrades_off_pg`](../../tests/integration/test_pg_source_wave1.py)

### <a id="unique-1124"></a>`UNIQUE-1124` — A recursive CTE's SEARCH DEPTH/BREADTH FIRST BY ... SET ... / CYCLE clause (PostgreSQL 14+) → T-SQL/MySQL/Oracle

**Category:** `statement` · **Message:** PostgreSQL's recursive-CTE SEARCH/CYCLE clause has no {dialect} equivalent; statement preserved as a comment

**Problem.** A recursive CTE's SEARCH DEPTH/BREADTH FIRST BY ... SET ... / CYCLE clause (PostgreSQL 14+) → T-SQL/MySQL/Oracle

**Solution (pointer).** Faithful on PostgreSQL; statement preserved as a comment elsewhere.

**Discussion.** SEARCH/CYCLE are PostgreSQL-only recursive-CTE ordering/cycle-detection clauses (SQL:1999 features PostgreSQL adopted in 14); no other supported engine's recursive CTE grammar has them, and sqlglot itself cannot parse them outside PostgreSQL.

**See Also.** [`TestWave191PgSearchCte::test_search_clause_carrier_mysql`](../../tests/integration/test_pg_source_wave1.py)

### <a id="unique-1125"></a>`UNIQUE-1125` — A MERGE outside the canonical single-UPDATE/single-INSERT shape (→ MySQL)

**Category:** `statement` · **Message:** MySQL has no MERGE; rewrite as INSERT ... ON DUPLICATE KEY UPDATE. Original

**Problem.** A MERGE outside the canonical single-UPDATE/single-INSERT shape (→ MySQL)

**Solution (pointer).** Warned limit — statement preserved as a comment.

**Discussion.** MySQL has no MERGE statement; only the canonical two-branch shape has a faithful INSERT ... ON DUPLICATE KEY UPDATE rewrite (UNIQUE-1001) — any other clause combination (multiple conditional branches, a DELETE branch, NOT MATCHED BY SOURCE) has no MySQL equivalent to fall back to.

**See Also.** [`TestDDLPassthrough::test_merge_to_mysql_documented`](../../tests/integration/test_cross_dialect.py)

### <a id="unique-1126"></a>`UNIQUE-1126` — A WITH-clause (CTE) feeding an UPDATE/DELETE — either updating *through* the CTE name, or a data-modifying CTE body (WITH x AS (INSERT/UPDATE/DELETE ... RETURNING) SELECT ...) — transpiled cross-engine

**Category:** `statement` · **Message:** CTE with unsupported embedded DML preserved as a comment; reason carried at runtime

**Problem.** A WITH-clause (CTE) feeding an UPDATE/DELETE — either updating *through* the CTE name, or a data-modifying CTE body (WITH x AS (INSERT/UPDATE/DELETE ... RETURNING) SELECT ...) — transpiled cross-engine

**Solution (pointer).** Warned limit — statement preserved as a comment.

**Discussion.** Data-modifying CTE bodies are PostgreSQL-only syntax; updating through a CTE name is a T-SQL-only capability (no other engine resolves the CTE as an updatable view); and Oracle additionally rejects a WITH clause on UPDATE/DELETE outright, so none of the three shapes has a mechanical, engine-agnostic rewrite.

**See Also.** [`TestCteDmlGate::test_oracle_no_with_on_dml_carrier`](../../tests/unit/core/test_emit_mutation_survivors.py)

### <a id="unique-1127"></a>`UNIQUE-1127` — BEGIN TRANSACTION (T-SQL) → Oracle

**Category:** `statement` · **Message:** BEGIN TRANSACTION dropped -- Oracle starts a transaction implicitly

**Problem.** BEGIN TRANSACTION (T-SQL) → Oracle

**Solution (pointer).** Faithful — Oracle opens the same transaction implicitly on the first DML statement that follows.

**Discussion.** Oracle has no explicit 'start transaction' statement — a transaction begins implicitly with the first DML — so an explicit BEGIN TRANSACTION has nothing to map to and is simply redundant on Oracle, not an error to reproduce.

**See Also.** [`TestTsqlBeginTransaction::test_oracle_drops_with_warning`](../../tests/integration/test_challenge.py)

### <a id="unique-1128"></a>`UNIQUE-1128` — START TRANSACTION READ ONLY|READ WRITE (MySQL) → T-SQL

**Category:** `statement` · **Message:** T-SQL transactions have no READ … access mode; started as a regular transaction (docs/03-unsupported.md

**Problem.** START TRANSACTION READ ONLY|READ WRITE (MySQL) → T-SQL

**Solution (pointer).** Warned limit — the transaction opens as a normal (read/write) transaction; the READ ONLY/WRITE intent is dropped.

**Discussion.** T-SQL's BEGIN TRANSACTION has no access-mode clause at all — unlike MySQL/PostgreSQL, which accept READ ONLY/READ WRITE on the opener — so the requested mode has nothing to map to.

**See Also.** [`TestSetTransactionModes::test_tsql_mode_noted`](../../tests/integration/test_challenge.py)

### <a id="unique-1132"></a>`UNIQUE-1132` — SET TRANSACTION ISOLATION LEVEL <lvl> READ ONLY|READ WRITE — combined isolation + access mode (PostgreSQL) → T-SQL

**Category:** `statement` · **Message:** T-SQL SET TRANSACTION has no READ {mode} access mode; access mode dropped (docs/03-unsupported.md

**Problem.** SET TRANSACTION ISOLATION LEVEL <lvl> READ ONLY|READ WRITE — combined isolation + access mode (PostgreSQL) → T-SQL

**Solution (pointer).** Warned limit — the isolation level is kept faithfully; the access mode is dropped.

**Discussion.** T-SQL's SET TRANSACTION has no READ ONLY/READ WRITE access-mode clause at all — only ISOLATION LEVEL is expressible — so the access-mode half of a combined PostgreSQL statement has no T-SQL spelling.

**See Also.** [`TestPgSetTransactionAccessMode::test_combined_tsql_keeps_isolation_drops_access_mode_with_warning`](../../tests/integration/test_pg_source_wave1.py)

### <a id="unique-1133"></a>`UNIQUE-1133` — A bare SET TRANSACTION READ ONLY|READ WRITE with no isolation level (PostgreSQL) → T-SQL

**Category:** `statement` · **Message:** T-SQL SET TRANSACTION has no READ {mode} access mode (docs/03-unsupported.md); statement dropped. Original

**Problem.** A bare SET TRANSACTION READ ONLY|READ WRITE with no isolation level (PostgreSQL) → T-SQL

**Solution (pointer).** Warned limit — the whole statement is dropped (nothing to keep); original preserved as a comment.

**Discussion.** T-SQL's SET TRANSACTION expresses only ISOLATION LEVEL, never an access mode; with no isolation level present in the source either, there is nothing left in the statement that has a T-SQL spelling at all.

**See Also.** [`TestPgSetTransactionAccessMode::test_bare_access_mode_tsql_degrades_with_warning`](../../tests/integration/test_pg_source_wave1.py)

### <a id="unique-1134"></a>`UNIQUE-1134` — Oracle CONNECT BY / START WITH hierarchical query (→ PostgreSQL/MySQL/T-SQL), outside the shapes the automatic recursive-CTE rewrite covers

**Category:** `statement` · **Message:** Oracle CONNECT BY / START WITH hierarchical query has no automatic equivalent; rewrite as a WITH RECURSIVE CTE. Original

**Problem.** Oracle CONNECT BY / START WITH hierarchical query (→ PostgreSQL/MySQL/T-SQL), outside the shapes the automatic recursive-CTE rewrite covers

**Solution (pointer).** Warned limit — statement preserved as a comment; rewrite as a WITH RECURSIVE CTE by hand.

**Discussion.** CONNECT BY has no native equivalent on the other three engines; a WITH RECURSIVE CTE is the standard rewrite, but it must be constructed by hand for shapes the automatic CONNECT-BY-to-CTE conversion does not model, since a mechanical rewrite risks an incorrect recursion base or join.

**See Also.** [`TestNoSilentLoss::test_connect_by_to_postgresql_signals_warning`](../../tests/unit/core/test_no_silent_loss.py)

### <a id="unique-1136"></a>`UNIQUE-1136` — An INSERT combining RETURNING and ON CONFLICT DO UPDATE in one statement (PostgreSQL) → MySQL

**Category:** `statement` · **Message:** INSERT combines RETURNING and ON CONFLICT; rewrite as MERGE/upsert with result capture on {dialect}. Original

**Problem.** An INSERT combining RETURNING and ON CONFLICT DO UPDATE in one statement (PostgreSQL) → MySQL

**Solution (pointer).** Warned limit — statement preserved as a comment; rewrite as an upsert with a separate result-capturing SELECT.

**Discussion.** MySQL has neither RETURNING nor a named-target upsert clause; with both present at once there is no partial mapping to fall back to (RETURNING alone would map to a follow-up SELECT, ON CONFLICT alone to INSERT ... ON DUPLICATE KEY UPDATE, but the combination needs a MERGE-like statement plus result capture that MySQL cannot express).

**See Also.** [`TestOnConflictMysqlAndEStrings::test_returning_on_conflict_mysql_degrades`](../../tests/integration/test_pg_source_wave1.py)

### <a id="unique-1137"></a>`UNIQUE-1137` — T-SQL OUTPUT ... INTO <table> redirect (→ PostgreSQL)

**Category:** `statement` · **Message:** T-SQL OUTPUT … INTO <table> redirect has no PostgreSQL equivalent in a plain INSERT (it needs a data-modifying CTE); the INTO target is dropped and the RETURNING result is kept (docs/03-unsupported.md

**Problem.** T-SQL OUTPUT ... INTO <table> redirect (→ PostgreSQL)

**Solution (pointer).** Warned limit — the INTO redirect is dropped; the base DML and plain RETURNING are faithful.

**Discussion.** PostgreSQL's RETURNING only returns a result set to the caller; it has no INTO <table> redirect form, so the redirect cannot be expressed in a plain INSERT.

**See Also.** [`reda-ts-output-into`](../../tests/fixtures/challenge/challenge_sqlserver.sql)

### <a id="unique-1138"></a>`UNIQUE-1138` — UPDATE ... FROM ... RETURNING (PostgreSQL) → Oracle

**Category:** `statement` · **Message:** Oracle has no UPDATE … FROM (rewrite with a correlated subquery or MERGE) and no top-level RETURNING. Statement preserved as a comment

**Problem.** UPDATE ... FROM ... RETURNING (PostgreSQL) → Oracle

**Solution (pointer).** Warned limit — statement preserved as a comment.

**Discussion.** Oracle has neither UPDATE ... FROM (needs a correlated subquery or MERGE rewrite instead) nor a top-level RETURNING (PL/SQL-only, ORA-63809 standalone) — with both present at once in the same statement, there is no single Oracle statement shape left that can carry both the join and the returned columns.

**See Also.** [`TestWave206OracleReturningShapes::test_returning_update_from_carrier_oracle`](../../tests/integration/test_pg_source_wave1.py)

### <a id="unique-1139"></a>`UNIQUE-1139` — A top-level OUTPUT / RETURNING result set (→ Oracle)

**Category:** `statement` · **Message:** Oracle has no top-level RETURNING; the statement returned: {cols}

**Problem.** A top-level OUTPUT / RETURNING result set (→ Oracle)

**Solution (pointer).** Warned limit — the DML runs; the returned result set is documented, not produced.

**Discussion.** Oracle's RETURNING is PL/SQL-only — it must target INTO bind variables and cannot stand alone in a plain SQL statement (ORA-63809) — so a standalone OUTPUT/RETURNING has no Oracle equivalent.

**See Also.** [`reda-ts-output-into`](../../tests/fixtures/challenge/challenge_sqlserver.sql)

### <a id="unique-1140"></a>`UNIQUE-1140` — OUTPUT/RETURNING on an INSERT/UPDATE/DELETE (→ MySQL)

**Category:** `statement` · **Message:** MySQL has no RETURNING/OUTPUT; the statement returned: {cols}

**Problem.** OUTPUT/RETURNING on an INSERT/UPDATE/DELETE (→ MySQL)

**Solution (pointer).** Warned limit — the DML itself runs faithfully; the OUTPUT/RETURNING result set is documented, not produced.

**Discussion.** MySQL has no clause that returns affected-row values alongside a data-modifying statement — LAST_INSERT_ID() only ever returns the last auto-increment value, not arbitrary column values, and there is no set-returning DML form at all.

**See Also.** [`TestOutputClauseToMySQL::test_output_into_var_is_documented_not_returning`](../../tests/integration/test_procedural.py)

### <a id="unique-1142"></a>`UNIQUE-1142` — T-SQL MERGE with a MATCHED UPDATE and a conditional MATCHED DELETE whose condition reads a column the UPDATE assigns (→ Oracle)

**Category:** `statement` · **Message:** MERGE clause has no faithful rewrite; reason carried at runtime

**Problem.** T-SQL MERGE with a MATCHED UPDATE and a conditional MATCHED DELETE whose condition reads a column the UPDATE assigns (→ Oracle)

**Solution (pointer).** Warned limit — the whole MERGE is preserved as a comment; rewrite the two-clause fold by hand, preserving Oracle's post-update DELETE WHERE evaluation order.

**Discussion.** Oracle folds a conditional MATCHED UPDATE/DELETE pair into one UPDATE (CASE-guarded) plus a trailing DELETE WHERE, but Oracle evaluates that DELETE WHERE against post-update values; when the DELETE's own condition reads a column the UPDATE just wrote, the fold would delete rows the source MERGE keeps, so the whole statement degrades rather than ship silently wrong rows.

**See Also.** [`TestMergeConditionalDeleteFoldSafety::test_unsafe_delete_on_updated_column_degrades`](../../tests/integration/test_challenge.py)

### <a id="unique-1143"></a>`UNIQUE-1143` — A trailing FOR UPDATE / FOR SHARE row-lock clause (PostgreSQL/Oracle/MySQL) → T-SQL

**Category:** `statement` · **Message:** T-SQL has no FOR UPDATE/FOR SHARE row-lock clause; lock the rows with a WITH (UPDLOCK, ROWLOCK) table hint

**Problem.** A trailing FOR UPDATE / FOR SHARE row-lock clause (PostgreSQL/Oracle/MySQL) → T-SQL

**Solution (pointer).** Warned limit — the clause is dropped rather than left as invalid trailing syntax; add a WITH (UPDLOCK, ROWLOCK) hint by hand for equivalent locking.

**Discussion.** T-SQL has no trailing row-lock clause on SELECT at all; row locking is instead requested via a WITH (UPDLOCK, ROWLOCK) table hint on the FROM clause — a different syntactic position, not a drop-in keyword substitution.

**See Also.** [`postgresql-qdrop-FOR`](../../tests/fixtures/challenge/challenge_postgresql.sql)

### <a id="unique-1145"></a>`UNIQUE-1145` — A MySQL inline functional/plain INDEX table element (→ other engines)

**Category:** `statement` · **Message:** inline INDEX table element has no {dialect} equivalent form; index omitted — queries run unindexed. Original: …

**Problem.** A MySQL inline functional/plain INDEX table element (→ other engines)

**Solution (pointer).** Warned limit — the index is omitted; queries still return correct rows, just unindexed. Write a separate CREATE INDEX by hand where the target supports the expression.

**Discussion.** An inline INDEX inside CREATE TABLE is a MySQL-only spelling; every other engine treats an index as a separate, purely physical object with no bearing on query results, so there is no column/constraint-list form to carry it to.

**See Also.** [`my-json-index`](../../tests/fixtures/challenge/challenge_mysql.sql)

### <a id="unique-1146"></a>`UNIQUE-1146` — An EXCLUDE exclusion constraint (PostgreSQL) → T-SQL/MySQL/Oracle

**Category:** `statement` · **Message:** PostgreSQL EXCLUDE constraint has no {dialect} equivalent; enforce the exclusion with a trigger. Original: …

**Problem.** An EXCLUDE exclusion constraint (PostgreSQL) → T-SQL/MySQL/Oracle

**Solution (pointer).** Warned limit — the table itself stays valid; the exclusion is not enforced. Emulate it with a trigger if required.

**Discussion.** EXCLUDE (e.g. preventing overlapping ranges via a GiST index) is a PostgreSQL-only constraint type with no equivalent declarative constraint on any other engine; the same behavior there needs a hand-written trigger.

**See Also.** [`postgresql-drop2-EXCLUDE`](../../tests/fixtures/challenge/challenge_postgresql.sql)

### <a id="unique-1147"></a>`UNIQUE-1147` — T-SQL computed column, e.g. total AS (a + b) PERSISTED (→ PostgreSQL/MySQL/Oracle)

**Category:** `statement` · **Message:** {dialect} requires an explicit type for the generated column {col_name}; original computed column: …

**Problem.** T-SQL computed column, e.g. total AS (a + b) PERSISTED (→ PostgreSQL/MySQL/Oracle)

**Solution (pointer).** Warned limit — the column definition is documented as a comment outside the (still valid) CREATE TABLE column list.

**Discussion.** T-SQL's computed-column syntax declares no explicit type at all (it is inferred from the expression); PostgreSQL, MySQL and Oracle all require an explicit type on a generated column (live-verified: MySQL rejects the typeless form too), and the transpiler cannot always infer one without full expression type-checking.

**See Also.** [`TestCrossDialectDDL::test_computed_column_preserved`](../../tests/integration/test_cross_dialect.py)

### <a id="unique-1148"></a>`UNIQUE-1148` — Foreign-key ON UPDATE referential action (→ Oracle)

**Category:** `statement` · **Message:** FK ON UPDATE referential action dropped — Oracle has no ON UPDATE FK action (docs/03-unsupported.md

**Problem.** Foreign-key ON UPDATE referential action (→ Oracle)

**Solution (pointer).** Warned limit — ON UPDATE is dropped; reproduce it with a trigger if needed.

**Discussion.** Oracle foreign keys support only ON DELETE CASCADE / SET NULL — there is no ON UPDATE referential action (ORA-00905).

**See Also.** [`reda-ts-fk-on-update`](../../tests/fixtures/challenge/challenge_sqlserver.sql)

### <a id="unique-1151"></a>`UNIQUE-1151` — A source-engine built-in with no form in the target's catalog (e.g. SOUNDEX → PostgreSQL)

**Category:** `validation` · **Message:** output failed the {target} validity check ({reason}); original {source} batch preserved

**Problem.** A source-engine built-in with no form in the target's catalog (e.g. SOUNDEX → PostgreSQL)

**Solution (pointer).** Warned limit — the statement is preserved as a carrier and the failing built-in is named.

**Discussion.** A call that is a built-in of the source engine (clearly meant to run, not a user object) but absent from the target's catalog would be rejected outright, so the whole statement degrades rather than shipping an invalid call — the general unmapped-built-in gate.

**See Also.** [`ora-soundex`](../../tests/fixtures/challenge/challenge_oracle.sql)

### <a id="unique-1152"></a>`UNIQUE-1152` — Oracle %TYPE / %ROWTYPE column-type reference (without --db-url)

**Category:** `procedural` · **Message:** type origin comment preserved from the source declaration

**Problem.** Oracle %TYPE / %ROWTYPE column-type reference (without --db-url)

**Solution (pointer).** Warned limit without --db-url (carrier type may not match exactly); faithful with --db-url or on an Oracle→Oracle round-trip.

**Discussion.** Only Oracle supports %TYPE/%ROWTYPE; resolving the real column type needs a live catalog lookup (ALL_TAB_COLUMNS) unavailable without a DB connection, so a permissive carrier type is emitted with the original reference preserved for a faithful round-trip back to Oracle.

**See Also.** [`test_type_reference_documented_then_restored`](../../tests/integration/test_procedural.py)

### <a id="unique-1153"></a>`UNIQUE-1153` — PostgreSQL trigger function (CREATE FUNCTION ... RETURNS TRIGGER) (→ MySQL)

**Category:** `procedural` · **Message:** PostgreSQL trigger function ('RETURNS TRIGGER') has no … equivalent (no trigger functions; the body belongs to a CREATE TRIGGER). The non-portable translation is commented out below for review

**Problem.** PostgreSQL trigger function (CREATE FUNCTION ... RETURNS TRIGGER) (→ MySQL)

**Solution (pointer).** Warned limit — the non-portable translation is preserved commented out for a manual rewrite.

**Discussion.** MySQL has no trigger functions — a trigger's body belongs directly to CREATE TRIGGER, not to a separately-callable RETURNS TRIGGER function — so the PL/pgSQL function shape has nothing to bind to.

**See Also.** [`TestPostgresTriggerToMySQL::test_trigger_function_degrades_with_warning`](../../tests/integration/test_triggers.py)

### <a id="unique-1154"></a>`UNIQUE-1154` — T-SQL inline table-valued function (CREATE FUNCTION ... RETURNS TABLE AS RETURN (...))

**Category:** `procedural` · **Message:** inline table-valued function ('RETURNS TABLE') has no direct equivalent. ….

**Problem.** T-SQL inline table-valued function (CREATE FUNCTION ... RETURNS TABLE AS RETURN (...))

**Solution (pointer).** Warned limit — documented and commented out rather than emitted as invalid RETURNS TABLE.

**Discussion.** Neither MySQL nor PostgreSQL has an inline (single-statement, substituted-at-call-site) table-valued function form; both would need a full multi-statement function/procedure rewritten by hand.

**See Also.** [`TestInlineTableValuedFunction::test_mysql_documents_and_comments_out`](../../tests/integration/test_procedural.py)

### <a id="unique-1155"></a>`UNIQUE-1155` — A trigger body that reads the T-SQL inserted/deleted pseudo-tables in a set-based way (FROM/JOIN inserted|deleted) the target cannot express

**Category:** `procedural` · **Message:** trigger reads the T-SQL inserted/deleted pseudo-tables in a set-based way … cannot express; the translation is preserved commented out for a manual rewrite

**Problem.** A trigger body that reads the T-SQL inserted/deleted pseudo-tables in a set-based way (FROM/JOIN inserted|deleted) the target cannot express

**Solution (pointer).** Warned limit — the whole trigger becomes a documented carrier.

**Discussion.** Once the set-based pseudo-table read degrades to a per-statement carrier (UNIQUE-1201), the surrounding trigger no longer has a runnable body — shipping it partially would execute a half-empty trigger per row, so the whole trigger is preserved commented out instead.

**See Also.** [`TestSetBasedTriggerRewrite::test_pure_set_based_to_mysql_documented`](../../tests/integration/test_triggers.py)

### <a id="unique-1156"></a>`UNIQUE-1156` — Oracle COMPOUND TRIGGER (→ MySQL)

**Category:** `procedural` · **Message:** Oracle COMPOUND TRIGGER … (… {events} ON …) has no automatic … equivalent — it collects affected rows in a PL/SQL collection and re-aggregates in AFTER STATEMENT. Rewrite manually (PostgreSQL: a statement-level trigger with REFERENCING NEW TABLE; MySQL: a row-level trigger that re-reads the table).

**Problem.** Oracle COMPOUND TRIGGER (→ MySQL)

**Solution (pointer).** Warned limit — documented for a manual rewrite (a MySQL row-level trigger that re-reads the table).

**Discussion.** A compound trigger's BEFORE/AFTER EACH ROW + AFTER STATEMENT sections collect affected rows into a PL/SQL collection and re-aggregate them statement-wide; MySQL has no equivalent mechanism (no transition tables, no multi-timing trigger sections) to mechanically rewrite that accumulation into.

**See Also.** [`TestOracleCompoundTrigger::test_degrades_to_carrier_mysql`](../../tests/integration/test_triggers.py)

### <a id="unique-1157"></a>`UNIQUE-1157` — A PostgreSQL statement-level trigger delegating its body to a trigger function via EXECUTE FUNCTION (→ MySQL)

**Category:** `procedural` · **Message:** PostgreSQL statement-level trigger delegating to a trigger function has no … equivalent (no transition tables / trigger functions). Original binding

**Problem.** A PostgreSQL statement-level trigger delegating its body to a trigger function via EXECUTE FUNCTION (→ MySQL)

**Solution (pointer).** Warned limit — documented carrier.

**Discussion.** MySQL has neither trigger functions nor transition tables, so a statement-level trigger that references its bound function's transition-table reads has nothing to bind to.

**See Also.** [`TestPostgresTriggerToMySQL::test_trigger_binding_degrades_with_warning`](../../tests/integration/test_triggers.py)

### <a id="unique-1158"></a>`UNIQUE-1158` — A PostgreSQL FOREACH ... IN ARRAY LOOP (→ other engines)

**Category:** `procedural` · **Message:** {header} LOOP … has no … equivalent (no array type); statement preserved as a comment

**Problem.** A PostgreSQL FOREACH ... IN ARRAY LOOP (→ other engines)

**Solution (pointer).** Warned limit — statement preserved as a comment.

**Discussion.** The FOREACH-over-array loop is inherently array-typed, and no other engine has an array column/variable type at all, so there is no array to iterate over on the target.

**See Also.** [`TestForeachArrayLoop::test_foreach_degrades_off_pg`](../../tests/integration/test_pg_source_wave1.py)

### <a id="unique-1159"></a>`UNIQUE-1159` — An Oracle PL/SQL PRAGMA declaration (e.g. AUTONOMOUS_TRANSACTION) (→ other engines)

**Category:** `procedural` · **Message:** PRAGMA … has no … equivalent; dropped.

**Problem.** An Oracle PL/SQL PRAGMA declaration (e.g. AUTONOMOUS_TRANSACTION) (→ other engines)

**Solution (pointer).** Warned limit — dropped; the surrounding declarations and body still transpile.

**Discussion.** A PRAGMA is a compiler directive to the Oracle PL/SQL engine itself (no runtime SQL effect); no other engine's procedural language has an equivalent compiler-directive mechanism.

**See Also.** [`TestPragmaAutonomousTransaction::test_off_oracle_pragma_never_ships_executable`](../../tests/integration/test_oracle_mysql_tail.py)

### <a id="unique-1160"></a>`UNIQUE-1160` — A standalone (anonymous) PL/SQL block at the top level, with no enclosing CREATE PROCEDURE/FUNCTION

**Category:** `procedural` · **Message:** anonymous PL/SQL block has no top-level … equivalent; preserved below

**Problem.** A standalone (anonymous) PL/SQL block at the top level, with no enclosing CREATE PROCEDURE/FUNCTION

**Solution (pointer).** Warned limit — preserved as a documented comment below the carrier.

**Discussion.** No other engine has a top-level anonymous executable block outside a routine definition (T-SQL's nearest analog, a batch, has different scoping/semantics), so a mechanical rewrite risks silently changing what runs when.

**See Also.** [`TestOracleCatalogDropBlock::test_degrades_on_postgresql`](../../tests/integration/test_procedural.py)

### <a id="unique-1161"></a>`UNIQUE-1161` — T-SQL sp_executesql parameter declarations/bindings (→ MySQL)

**Category:** `procedural` · **Message:** sp_executesql parameter declarations/bindings dropped; pass them via EXECUTE ... USING manually

**Problem.** T-SQL sp_executesql parameter declarations/bindings (→ MySQL)

**Solution (pointer).** Warned limit — parameter bindings dropped.

**Discussion.** MySQL's PREPARE/EXECUTE has no inline parameter-declaration + binding form matching sp_executesql's @params list, so the declarations/bindings are dropped and must be passed via EXECUTE ... USING.

**See Also.** [`ts-sp-executesql`](../../tests/fixtures/challenge/challenge_sqlserver.sql)

### <a id="unique-1162"></a>`UNIQUE-1162` — A PL/pgSQL RAISE NOTICE inside a function that returns a scalar value (→ MySQL)

**Category:** `procedural` · **Message:** notice has no output channel inside a MySQL function; message kept in @uq_notice

**Problem.** A PL/pgSQL RAISE NOTICE inside a function that returns a scalar value (→ MySQL)

**Solution (pointer).** Warned limit — the message lands in @uq_notice, not printed inline; procedures (which can SELECT) keep the visible channel.

**Discussion.** A bare SELECT (MySQL's own notice-style output channel) is invalid inside a MySQL FUNCTION — functions cannot return an extra result set (error 1415) — so the message is diverted into a session variable instead.

**See Also.** [`TestMysqlFunctionNotice::test_notice_in_function_diverts`](../../tests/integration/test_pg_source_wave1.py)

### <a id="unique-1163"></a>`UNIQUE-1163` — T-SQL RAISERROR/THROW with severity/state arguments (→ MySQL)

**Category:** `procedural` · **Message:** original RAISERROR/THROW severity/state args dropped: {rest}

**Problem.** T-SQL RAISERROR/THROW with severity/state arguments (→ MySQL)

**Solution (pointer).** Warned limit — severity/state args dropped, listed in the carrier.

**Discussion.** MySQL's SIGNAL statement has no severity/state argument slots matching RAISERROR's — only the message transfers, so the extra arguments are dropped and named in the carrier rather than silently discarded.

**See Also.** [`red2-ts-raiserror-format-arg-drop`](../../tests/fixtures/challenge/challenge_sqlserver.sql)

### <a id="unique-1164"></a>`UNIQUE-1164` — BEGIN TRANSACTION (→ Oracle)

**Category:** `procedural` · **Message:** BEGIN TRANSACTION dropped -- … starts a transaction implicitly

**Problem.** BEGIN TRANSACTION (→ Oracle)

**Solution (pointer).** Faithful (no-op drop) — Oracle's implicit transaction start reproduces the same behaviour.

**Discussion.** Oracle has no explicit transaction-start statement — a transaction begins implicitly with the first DML statement — so an explicit BEGIN TRANSACTION has nothing to translate to.

**See Also.** [`TestTransactionControl::test_begin_transaction_documented_for_oracle_pg`](../../tests/integration/test_procedural.py)

### <a id="unique-1165"></a>`UNIQUE-1165` — T-SQL WAITFOR TIME '...' — wait until an absolute clock time (→ MySQL)

**Category:** `procedural` · **Message:** WAITFOR TIME '…' has no … equivalent (wait until an absolute time

**Problem.** T-SQL WAITFOR TIME '...' — wait until an absolute clock time (→ MySQL)

**Solution (pointer).** Warned limit — documented, not computed.

**Discussion.** Every target's sleep primitive (DBMS_SESSION.SLEEP, pg_sleep, MySQL SLEEP) takes a relative duration, not an absolute wall-clock time to wait until; WAITFOR DELAY (relative) maps cleanly, but WAITFOR TIME has no relative-duration equivalent to compute without the current time at run time.

**See Also.** [`TestWaitFor::test_time_documented`](../../tests/integration/test_procedural.py)

### <a id="unique-1166"></a>`UNIQUE-1166` — A non-forward cursor FETCH (FETCH LAST/PRIOR/FIRST/ABSOLUTE/RELATIVE) from a scrollable cursor (→ Oracle)

**Category:** `procedural` · **Message:** FETCH {direction} has no … equivalent (cursors are forward-only); statement preserved as a comment

**Problem.** A non-forward cursor FETCH (FETCH LAST/PRIOR/FIRST/ABSOLUTE/RELATIVE) from a scrollable cursor (→ Oracle)

**Solution (pointer).** Warned limit — the scroll fetch degrades to a carrier; the surrounding OPEN/FETCH NEXT/CLOSE still compile.

**Discussion.** Oracle cursors, like every other target's, are forward-only (only FETCH NEXT); a non-forward fetch direction has no operation to translate to.

**See Also.** [`TestFetchDirections::test_fetch_last_degrades_oracle`](../../tests/integration/test_pg_source_wave1.py)

### <a id="unique-1167"></a>`UNIQUE-1167` — A cursor FETCH with no INTO target-variable list

**Category:** `procedural` · **Message:** FETCH without INTO — … requires target variables (the source discarded the fetched row); preserved as a comment

**Problem.** A cursor FETCH with no INTO target-variable list

**Solution (pointer).** Warned limit — documented as a comment rather than shipping an incomplete FETCH.

**Discussion.** PostgreSQL/Oracle/MySQL all require FETCH to specify where the fetched row's columns go; a source FETCH that discards the row (no INTO) has nothing for the target's FETCH to bind, so emitting 'FETCH c INTO ;' would be invalid syntax.

**See Also.** [`TestUnsupportedCursorConstructsAreValidCarriers::test_fetch_without_into_is_documented_not_empty`](../../tests/integration/test_procedural.py)

### <a id="unique-1168"></a>`UNIQUE-1168` — GOTO <label> (→ PostgreSQL)

**Category:** `procedural` · **Message:** GOTO … dropped -- … has no GOTO; control flow not replicated (docs/03-unsupported.md

**Problem.** GOTO <label> (→ PostgreSQL)

**Solution (pointer).** Warned limit — dropped; control flow is not replicated (T-SQL/Oracle keep native GOTO).

**Discussion.** PL/pgSQL has no GOTO statement (or any unconditional-jump control-flow form), so a source GOTO has no operation to translate to.

**See Also.** [`red3-ts-goto-label-proc`](../../tests/fixtures/challenge/challenge_sqlserver.sql)

### <a id="unique-1169"></a>`UNIQUE-1169` — A GOTO target label (→ PostgreSQL)

**Category:** `procedural` · **Message:** label … dropped -- … has no GOTO/label (docs/03-unsupported.md

**Problem.** A GOTO target label (→ PostgreSQL)

**Solution (pointer).** Warned limit — dropped alongside its GOTO.

**Discussion.** Without a GOTO to jump to it, and with PL/pgSQL having no label/GOTO mechanism at all, the label marker itself has nothing to bind to on the target.

**See Also.** [`red3-ts-goto-label-proc`](../../tests/fixtures/challenge/challenge_sqlserver.sql)

### <a id="unique-1170"></a>`UNIQUE-1170` — A procedural construct the parser cannot recognize at all (e.g. a PL/SQL collection-TYPE declaration inside a trigger's DECLARE section)

**Category:** `procedural` · **Message:** could not translate; preserved for review

**Problem.** A procedural construct the parser cannot recognize at all (e.g. a PL/SQL collection-TYPE declaration inside a trigger's DECLARE section)

**Solution (pointer).** Warned limit — the whole routine/statement is preserved as a documented comment for manual review.

**Discussion.** This code is the procedural pipeline's own generic 'could not parse this' escape valve — paired 1:1 with the parser's own fallback (it captures the unparsed token stream as a carrier), so the concrete unrecognized shape varies by call site rather than being fixed per code.

**See Also.** [`test_unparseable_construct_does_not_duplicate_the_carrier_warning`](../../tests/integration/test_procedural_warning_codes.py)

### <a id="unique-1171"></a>`UNIQUE-1171` — A whole procedural construct the transformer recognizes but cannot map on the target (the shared transformer-degrade carrier)

**Category:** `procedural` · **Message:** procedural statement preserved as a comment; reason carried at runtime

**Problem.** A whole procedural construct the transformer recognizes but cannot map on the target (the shared transformer-degrade carrier)

**Solution (pointer).** Warned limit — the construct is preserved as a documented comment.

**Discussion.** Shared carrier path for any transformer-level whole-unit degrade (an unsupported PL/SQL exception context in a T-SQL scalar function, a client-tool directive, ...); each specific reason is interpolated into the same carrier template rather than allocating one code per message.

**See Also.** [`pg-named-exception`](../../tests/fixtures/challenge/challenge_postgresql.sql)

### <a id="unique-1172"></a>`UNIQUE-1172` — GOTO <label> (→ MySQL)

**Category:** `procedural` · **Message:** GOTO … dropped -- MySQL has no GOTO; control flow not replicated (docs/03-unsupported.md

**Problem.** GOTO <label> (→ MySQL)

**Solution (pointer).** Warned limit — dropped; control flow not replicated.

**Discussion.** MySQL has no GOTO statement either; the carrier additionally pairs the drop with a DO 0 no-op so an IF/loop body the GOTO occupied is never left syntactically empty (MySQL error 1064).

**See Also.** [`red3-ts-goto-label-proc`](../../tests/fixtures/challenge/challenge_sqlserver.sql)

### <a id="unique-1173"></a>`UNIQUE-1173` — A GOTO target label (→ MySQL)

**Category:** `procedural` · **Message:** label … dropped -- MySQL has no GOTO/label (docs/03-unsupported.md

**Problem.** A GOTO target label (→ MySQL)

**Solution (pointer).** Warned limit — dropped alongside its GOTO.

**Discussion.** Same underlying gap as UNIQUE-1169 but for MySQL, which also has no label/GOTO mechanism.

**See Also.** [`red3-ts-goto-label-proc`](../../tests/fixtures/challenge/challenge_sqlserver.sql)

### <a id="unique-1174"></a>`UNIQUE-1174` — An Oracle/PostgreSQL implicit cursor FOR loop whose query's column list Unique cannot resolve (e.g. SELECT * or an unresolvable projection) (→ T-SQL / MySQL)

**Category:** `procedural` · **Message:** Oracle implicit cursor FOR-loop expanded to an explicit MySQL cursor. -- Declare one variable per selected column and complete the FETCH INTO list. DECLARE {done} INT DEFAULT FALSE; DECLARE {cur} CURSOR FOR {cursor_str}; DECLARE CONTINUE HANDLER FOR NOT FOUND SET {done} = TRUE; OPEN {cur}; {variable}_loop: LOOP …FETCH {cur} INTO /* col1, col2, ... */; …IF {done} THEN LEAVE {variable}_loop; END IF

**Problem.** An Oracle/PostgreSQL implicit cursor FOR loop whose query's column list Unique cannot resolve (e.g. SELECT * or an unresolvable projection) (→ T-SQL / MySQL)

**Solution (pointer).** Warned limit — the FETCH INTO target list is left as a placeholder comment for manual completion; OPEN/CLOSE and the loop shape are still emitted.

**Discussion.** The faithful expansion needs one FETCH-target variable per selected column; when the column list isn't statically resolvable (a bare SELECT * with no visible schema, or a referenced record field the visible list doesn't expose), Unique cannot generate that variable list, so it emits a documented scaffold for the developer to complete instead of guessing.

**See Also.** [`test_unresolvable_select_star_keeps_documented_scaffold`](../../tests/integration/test_cursor_for_loop_tsql.py)

### <a id="unique-1175"></a>`UNIQUE-1175` — An Oracle/PostgreSQL implicit cursor FOR loop with a resolvable column list (→ MySQL)

**Category:** `procedural` · **Message:** cursor FOR-loop expanded; loop variables are TEXT (exact column types need --db-url metadata). BEGIN

**Problem.** An Oracle/PostgreSQL implicit cursor FOR loop with a resolvable column list (→ MySQL)

**Solution (pointer).** Warned limit without --db-url (loop variables are TEXT, not the real column types); the loop's control flow and FETCH are otherwise faithful.

**Discussion.** The columns are resolvable, so the loop expands completely (one variable per column, positional FETCH), but without a --db-url connection Unique does not know each column's real type, so every loop variable is declared as the permissive TEXT type.

**See Also.** [`TestMySqlCursorForLoopExpansion::test_named_cursor_drives_directly`](../../tests/integration/test_oracle_mysql_tail.py)

### <a id="unique-1176"></a>`UNIQUE-1176` — A T-SQL INSTEAD OF trigger (→ MySQL)

**Category:** `procedural` · **Message:** MySQL has no INSTEAD OF trigger; emitted as BEFORE for review (original was INSTEAD OF, typically on a view).

**Problem.** A T-SQL INSTEAD OF trigger (→ MySQL)

**Solution (pointer).** Warned limit — emitted as BEFORE for review, with the original INSTEAD OF timing documented.

**Discussion.** MySQL has no INSTEAD OF trigger timing at all (only BEFORE/AFTER); the closest emulation is a BEFORE trigger, which runs in addition to (not instead of) the triggering statement, so the substitution semantics are not reproduced automatically.

**See Also.** [`TestInsteadOfTrigger::test_instead_of_documented_on_mysql`](../../tests/integration/test_triggers.py)

### <a id="unique-1177"></a>`UNIQUE-1177` — A T-SQL procedure-level RETURN <value> (a status code) (→ MySQL)

**Category:** `procedural` · **Message:** discarded procedure RETURN value ({val}

**Problem.** A T-SQL procedure-level RETURN <value> (a status code) (→ MySQL)

**Solution (pointer).** Warned limit — the status-code value is documented, not returned; a FUNCTION's RETURN <value> is unaffected and kept.

**Discussion.** MySQL stored procedures have no return value (only functions do); a procedure's RETURN <expr> is rewritten to a bare LEAVE (exiting the procedure), and the discarded value is named in the carrier rather than silently dropped.

**See Also.** [`TestReturnValueInProcedure::test_return_value_in_procedure_becomes_leave`](../../tests/integration/test_procedural.py)

### <a id="unique-1178"></a>`UNIQUE-1178` — A dynamic-SQL EXECUTE ... INTO <var> whose target string is not a compile-time-resolvable SELECT INTO @session-variable form (→ MySQL)

**Category:** `procedural` · **Message:** dynamic SELECT INTO variable has no direct MySQL form (rewrite the dynamic string to select INTO @session variables); original

**Problem.** A dynamic-SQL EXECUTE ... INTO <var> whose target string is not a compile-time-resolvable SELECT INTO @session-variable form (→ MySQL)

**Solution (pointer).** Warned limit — documented; the dynamic string must be rewritten by hand to select into a MySQL session variable.

**Discussion.** MySQL's PREPARE/EXECUTE workflow can only capture a dynamic result into a variable if the dynamic SQL text itself is rewritten to 'SELECT ... INTO @var', which Unique cannot reliably synthesize for an arbitrary dynamic string built at runtime.

**See Also.** [`pg-dyn-count`](../../tests/fixtures/challenge/challenge_postgresql.sql)

### <a id="unique-1179"></a>`UNIQUE-1179` — A trigger body that reads the T-SQL inserted/deleted pseudo-tables in a set-based way (→ Oracle)

**Category:** `procedural` · **Message:** trigger reads the T-SQL inserted/deleted pseudo-tables in a set-based way Oracle cannot express (no transition tables — use a compound trigger); the translation is preserved commented out for a manual rewrite

**Problem.** A trigger body that reads the T-SQL inserted/deleted pseudo-tables in a set-based way (→ Oracle)

**Solution (pointer).** Warned limit — the whole trigger degrades to a documented carrier for a manual compound-trigger rewrite (the Oracle-specific sibling of UNIQUE-1155).

**Discussion.** Oracle has no transition tables at all (a compound trigger's PL/SQL-collection accumulation is the closest analog, and is not a mechanical rewrite of an arbitrary set-based DML statement), so the set-based read cannot be expressed.

**See Also.** [`TestSetBasedTriggerRewrite::test_pure_set_based_to_oracle_documented`](../../tests/integration/test_triggers.py)

### <a id="unique-1180"></a>`UNIQUE-1180` — T-SQL sp_executesql named parameters (→ Oracle)

**Category:** `procedural` · **Message:** sp_executesql named parameters bind POSITIONALLY here — spell the placeholders inside the dynamic string as :1, :2, … (docs/03-unsupported.md

**Problem.** T-SQL sp_executesql named parameters (→ Oracle)

**Solution (pointer).** Warned limit — placeholders must be renumbered positionally.

**Discussion.** Oracle EXECUTE IMMEDIATE ... USING binds positionally, so the named @params of sp_executesql must be re-spelled inside the dynamic string as :1, :2, ….

**See Also.** [`ts-sp-executesql`](../../tests/fixtures/challenge/challenge_sqlserver.sql)

### <a id="unique-1182"></a>`UNIQUE-1182` — A T-SQL INSTEAD OF trigger on a base TABLE, not a view (→ PostgreSQL)

**Category:** `procedural` · **Message:** PostgreSQL allows INSTEAD OF only on views; on a table the equivalent is a BEFORE row trigger returning NULL (the original operation is suppressed

**Problem.** A T-SQL INSTEAD OF trigger on a base TABLE, not a view (→ PostgreSQL)

**Solution (pointer).** Faithful — the rewritten BEFORE-trigger-with-guard form reproduces the substitution semantics (live-verified insert-exactly-once).

**Discussion.** PostgreSQL restricts INSTEAD OF triggers to views only; on a table, the equivalent behaviour (substituting the trigger's own logic for the triggering statement) is a BEFORE row trigger that returns NULL, suppressing the original operation — a different trigger-timing model requiring a pg_trigger_depth() guard so the trigger's own DML still executes.

**See Also.** [`ts-instead-of-insert`](../../tests/fixtures/challenge/challenge_sqlserver.sql)

### <a id="unique-1183"></a>`UNIQUE-1183` — BEGIN TRANSACTION (→ PostgreSQL)

**Category:** `procedural` · **Message:** BEGIN TRANSACTION dropped -- PostgreSQL manages the routine transaction implicitly

**Problem.** BEGIN TRANSACTION (→ PostgreSQL)

**Solution (pointer).** Faithful (no-op drop) — PostgreSQL's implicit routine-transaction handling reproduces the same behaviour.

**Discussion.** A PL/pgSQL routine already runs inside the caller's transaction (or manages its own via nested procedure-call semantics) — there is no explicit statement to start one, so an explicit BEGIN TRANSACTION has nothing to translate to.

**See Also.** [`TestTransactionControl::test_begin_transaction_documented_for_oracle_pg`](../../tests/integration/test_procedural.py)

### <a id="unique-1184"></a>`UNIQUE-1184` — SAVEPOINT (→ PostgreSQL)

**Category:** `procedural` · **Message:** SAVEPOINT{sp} dropped -- PL/pgSQL has no explicit savepoints; wrap the statements in a BEGIN … EXCEPTION block, which rolls back to its start on error (docs/03-unsupported.md

**Problem.** SAVEPOINT (→ PostgreSQL)

**Solution (pointer).** Warned limit — dropped; wrap the guarded statements in a BEGIN...EXCEPTION block to reproduce the rollback boundary (Oracle keeps native SAVEPOINT).

**Discussion.** PL/pgSQL has no explicit SAVEPOINT statement; the equivalent behaviour (a partial rollback boundary) comes from wrapping statements in a BEGIN ... EXCEPTION block, which rolls back to its own start on error.

**See Also.** [`TestTransactionControl::test_rollback_to_savepoint`](../../tests/integration/test_procedural.py)

### <a id="unique-1185"></a>`UNIQUE-1185` — ROLLBACK TO SAVEPOINT <name> (→ PostgreSQL)

**Category:** `procedural` · **Message:** ROLLBACK TO SAVEPOINT {name} dropped -- PL/pgSQL has no explicit savepoints; the enclosing BEGIN … EXCEPTION block rolls back automatically on error (docs/03-unsupported.md

**Problem.** ROLLBACK TO SAVEPOINT <name> (→ PostgreSQL)

**Solution (pointer).** Warned limit — dropped alongside its SAVEPOINT.

**Discussion.** Same underlying gap as UNIQUE-1184 — PL/pgSQL has no explicit savepoints to roll back to; the enclosing BEGIN...EXCEPTION block already rolls back automatically on error.

**See Also.** [`TestTransactionControl::test_rollback_to_savepoint`](../../tests/integration/test_procedural.py)

### <a id="unique-1186"></a>`UNIQUE-1186` — SELECT * INTO <multiple variables> (→ other engines)

**Category:** `procedural` · **Message:** SELECT * INTO multiple variables needs the column list (no schema to expand '*'); statement preserved as a comment

**Problem.** SELECT * INTO <multiple variables> (→ other engines)

**Solution (pointer).** Warned limit — documented; supply the column list explicitly to fix.

**Discussion.** Expanding SELECT * into a positional variable-assignment list requires knowing the source's column list, which a bare '*' does not carry without schema access; the same is true across engines, so the statement cannot be mechanically completed.

**See Also.** [`TestWave233StarIntoMultipleVars::test_star_into_multi_degrades`](../../tests/integration/test_pg_source_wave1.py)

### <a id="unique-1187"></a>`UNIQUE-1187` — An Oracle/PostgreSQL implicit cursor FOR loop with a resolvable column list (→ T-SQL)

**Category:** `procedural` · **Message:** cursor FOR-loop expanded; loop variables are NVARCHAR(4000) (exact column types need --db-url metadata).

**Problem.** An Oracle/PostgreSQL implicit cursor FOR loop with a resolvable column list (→ T-SQL)

**Solution (pointer).** Warned limit without --db-url (loop variables are NVARCHAR(4000)); the loop's control flow and FETCH are otherwise faithful and complete.

**Discussion.** The T-SQL sibling of UNIQUE-1175 — the columns are resolvable and the loop expands completely (one @variable per column, positional FETCH NEXT), but without --db-url metadata each loop variable is declared as the permissive NVARCHAR(4000) rather than the column's real type.

**See Also.** [`test_named_cursor_loop_expands_completely`](../../tests/integration/test_cursor_for_loop_tsql.py)

### <a id="unique-1188"></a>`UNIQUE-1188` — SET TRANSACTION READ ONLY/READ WRITE inside a routine (→ T-SQL)

**Category:** `procedural` · **Message:** SET TRANSACTION {mode} dropped -- T-SQL has no READ ONLY/READ WRITE transaction mode; only ISOLATION LEVEL is expressible (docs/03-unsupported.md

**Problem.** SET TRANSACTION READ ONLY/READ WRITE inside a routine (→ T-SQL)

**Solution (pointer).** Warned limit — the access mode is dropped; ISOLATION LEVEL modes on the same statement still map natively.

**Discussion.** T-SQL's SET TRANSACTION only sets the ISOLATION LEVEL; it has no access-mode spelling at all (Oracle/PostgreSQL/MySQL all accept READ ONLY/READ WRITE natively), so the mode has no target keyword to map to.

**See Also.** [`TestProcSetTransaction::test_tsql_degrades_read_only_with_warning`](../../tests/integration/test_challenge.py)

### <a id="unique-1190"></a>`UNIQUE-1190` — Oracle EXECUTE IMMEDIATE ... USING <binds> with no INTO clause (→ T-SQL)

**Category:** `procedural` · **Message:** verify dynamic SQL placeholders match …

**Problem.** Oracle EXECUTE IMMEDIATE ... USING <binds> with no INTO clause (→ T-SQL)

**Solution (pointer).** Warned limit — placeholders inside the dynamic string need manual renumbering to @p1, @p2, ...; the call itself is valid and parameterized.

**Discussion.** T-SQL's sp_executesql takes named parameters (@p1, @p2, ...) bound by name, while Oracle's USING binds positionally against :1, :2, ... placeholders inside the dynamic string; the rewrite emits a parameterized sp_executesql call, but the placeholders inside the dynamic-SQL text itself must still be renumbered by hand to match.

**See Also.** [`TestDynamicSQL::test_oracle_to_tsql_uses_sp_executesql`](../../tests/integration/test_procedural.py)

### <a id="unique-1192"></a>`UNIQUE-1192` — Oracle's implicit-cursor SQL%ROWCOUNT (rows the last DML MATCHED) (→ MySQL)

**Category:** `procedural` · **Message:** ROW_COUNT() counts changed rows, not matched rows like the source (docs/03-unsupported.md

**Problem.** Oracle's implicit-cursor SQL%ROWCOUNT (rows the last DML MATCHED) (→ MySQL)

**Solution (pointer).** Warned limit — the value may differ from the source when a matched row's UPDATE is a no-op (T-SQL's @@ROWCOUNT is matched-rows too and needs no such note).

**Discussion.** MySQL's closest equivalent, ROW_COUNT(), counts rows actually CHANGED by the last DML, not rows matched by its WHERE clause — for an UPDATE that matches a row but assigns it its current value, Oracle's matched-count and MySQL's changed-count diverge; the mapping is kept (still the closest fit) but annotated rather than shipped silently.

**See Also.** [`TestRowcountDivergenceAnnotation::test_mysql_target_annotates_and_warns`](../../tests/integration/test_challenge.py)

### <a id="unique-1193"></a>`UNIQUE-1193` — A source-only procedural statement with no target concept at all (e.g. T-SQL SET IDENTITY_INSERT/SET NOCOUNT inside a routine) (→ other engines)

**Category:** `procedural` · **Message:** … -- …-only, no … equivalent

**Problem.** A source-only procedural statement with no target concept at all (e.g. T-SQL SET IDENTITY_INSERT/SET NOCOUNT inside a routine) (→ other engines)

**Solution (pointer).** Warned limit — dropped; documented as source-engine-only, and restored verbatim on a round trip back to the source engine.

**Discussion.** The statement configures a source-engine-only session/compiler behaviour with no corresponding concept on the target at all (not merely a missing spelling), so the shared carrier documents it as '{source}-only' rather than attempting any target-side equivalent.

**See Also.** [`TestUniqueCommentRestore::test_identity_insert_documented_then_restored`](../../tests/integration/test_procedural.py)

### <a id="unique-1194"></a>`UNIQUE-1194` — A T-SQL global (@@ERROR/@@TRANCOUNT/@@CURSOR_ROWS/SQL%ROWCOUNT-family) used inside an expression position (e.g. an IF condition) with no target equivalent

**Category:** `procedural` · **Message:** {name} has no … equivalent; {hint}

**Problem.** A T-SQL global (@@ERROR/@@TRANCOUNT/@@CURSOR_ROWS/SQL%ROWCOUNT-family) used inside an expression position (e.g. an IF condition) with no target equivalent

**Solution (pointer).** Warned limit — a neutral literal (0) replaces the global so the expression parses; the specific behaviour it gated is lost.

**Discussion.** These globals have no faithful non-source equivalent, and unlike a top-level statement, an expression position cannot simply be dropped — a value-shaped placeholder is required so the surrounding expression stays syntactically valid.

**See Also.** [`TestErrorGlobalInCondition::test_error_in_if_mysql`](../../tests/integration/test_procedural.py)

### <a id="unique-1195"></a>`UNIQUE-1195` — A PostgreSQL trigger function's body, when its trigger delegates to it via EXECUTE FUNCTION (→ T-SQL)

**Category:** `procedural` · **Message:** trigger function … inlined into its T-SQL trigger

**Problem.** A PostgreSQL trigger function's body, when its trigger delegates to it via EXECUTE FUNCTION (→ T-SQL)

**Solution (pointer).** Faithful — the inlined trigger reproduces the same DML; live-compiled valid.

**Discussion.** T-SQL has no separately-callable trigger function — a trigger's logic must live inline in CREATE TRIGGER — so the delegating function's body is inlined directly into the T-SQL trigger, with the PG-only pg_trigger_depth() guard and RETURN NULL protocol dropped (T-SQL triggers have no such re-entrancy-guard convention).

**See Also.** [`TestPgDelegatingTriggerToTSql::test_inlined_into_tsql_trigger`](../../tests/integration/test_triggers.py)

### <a id="unique-1196"></a>`UNIQUE-1196` — A T-SQL table variable (DECLARE @var TABLE (...)) (→ MySQL)

**Category:** `procedural` · **Message:** was T-SQL table variable {name}

**Problem.** A T-SQL table variable (DECLARE @var TABLE (...)) (→ MySQL)

**Solution (pointer).** Faithful — a temporary table reproduces the same session-scoped, statement-usable storage; the carrier is purely documentary.

**Discussion.** MySQL has no table-variable DECLARE form; the closest equivalent is a CREATE TEMPORARY TABLE statement inside the routine body, which the carrier documents as the table variable's replacement.

**See Also.** [`TestTableVariableToMySQL::test_table_variable_becomes_temp_table`](../../tests/integration/test_procedural.py)

### <a id="unique-1197"></a>`UNIQUE-1197` — A source-only SET option with no target equivalent, inside a routine body (e.g. MySQL SET SQL_MODE)

**Category:** `procedural` · **Message:** SET option is source-only and has no target equivalent

**Problem.** A source-only SET option with no target equivalent, inside a routine body (e.g. MySQL SET SQL_MODE)

**Solution (pointer).** Warned limit — dropped; documented as source-only.

**Discussion.** The option configures source-engine-only parsing/execution behaviour (MySQL's SQL_MODE flags, for instance) that no other engine's session model has a matching concept for.

**See Also.** [`TestWave162AdddateSqlMode::test_set_sql_mode_carrier_tsql`](../../tests/integration/test_pg_source_wave1.py)

### <a id="unique-1198"></a>`UNIQUE-1198` — EXEC <T-SQL system procedure> as a standalone statement (e.g. EXEC sp_who) inside a routine body (→ other engines)

**Category:** `procedural` · **Message:** T-SQL system procedure has no … equivalent; original: EXEC …

**Problem.** EXEC <T-SQL system procedure> as a standalone statement (e.g. EXEC sp_who) inside a routine body (→ other engines)

**Solution (pointer).** Warned limit — the call becomes a documented carrier; the administrative action must be performed via the target's own tooling.

**Discussion.** T-SQL system procedures call into SQL Server's own catalog/admin machinery (the same class as UNIQUE-1211's top-level EXEC, here inside a routine); no other engine exposes the same operation through a callable procedure.

**See Also.** [`ts-waitfor-exec`](../../tests/fixtures/challenge/challenge_sqlserver.sql)

### <a id="unique-1200"></a>`UNIQUE-1200` — An Oracle built-in package call (e.g. DBMS_SCHEDULER.CREATE_JOB) (→ other engines)

**Category:** `procedural` · **Message:** Oracle package call has no … equivalent; original

**Problem.** An Oracle built-in package call (e.g. DBMS_SCHEDULER.CREATE_JOB) (→ other engines)

**Solution (pointer).** Warned limit — the call becomes a documented carrier rather than an invalid raw call.

**Discussion.** Oracle's DBMS_*/UTL_* packages call into Oracle-specific server-side machinery (job scheduling, session control, ...) with no cross-engine equivalent; shipped raw, the call is a guaranteed runtime error off Oracle.

**See Also.** [`test_dbms_scheduler_degrades_to_carrier`](../../tests/integration/test_trigger_predicates_scheduler.py)

### <a id="unique-1201"></a>`UNIQUE-1201` — A trigger DML statement that reads the T-SQL inserted/deleted pseudo-tables in a set-based way (FROM inserted / JOIN deleted) (→ other engines, absent a transition-table rewrite)

**Category:** `procedural` · **Message:** trigger uses the T-SQL set-based inserted/deleted pseudo-tables, which have no row-level (NEW/OLD) equivalent. Rewrite manually (PostgreSQL: a statement-level trigger with REFERENCING NEW TABLE AS inserted OLD TABLE AS deleted; Oracle: a compound trigger; MySQL: no transition tables). Original

**Problem.** A trigger DML statement that reads the T-SQL inserted/deleted pseudo-tables in a set-based way (FROM inserted / JOIN deleted) (→ other engines, absent a transition-table rewrite)

**Solution (pointer).** Warned limit — the statement is documented with per-target rewrite guidance rather than shipped referencing an undefined table.

**Discussion.** A set-based pseudo-table read has no row-level (NEW/OLD) equivalent; where the whole trigger can be rewritten with real transition tables (PostgreSQL statement-level triggers, Oracle compound triggers) the set-based DML is left as-is, but where it cannot (MySQL, or a mixed row+set trigger), the specific statement is documented instead of emitted referencing an undefined table.

**See Also.** [`TestSetBasedTriggerRewrite::test_pure_set_based_to_mysql_documented`](../../tests/integration/test_triggers.py)

### <a id="unique-1202"></a>`UNIQUE-1202` — A T-SQL table-valued function used in a FROM clause (→ MySQL)

**Category:** `procedural` · **Message:** statement uses a table-valued function in FROM, which MySQL does not support; commented out for review

**Problem.** A T-SQL table-valued function used in a FROM clause (→ MySQL)

**Solution (pointer).** Warned limit — commented out for review (STRING_SPLIT, rewritten to the valid JSON_TABLE form, is unaffected).

**Discussion.** MySQL has no table-valued function mechanism (a function cannot appear as a FROM-clause row source); the statement is commented out rather than shipping an invalid function-in-FROM.

**See Also.** [`TestTableValuedFunctionInFrom::test_user_tvf_in_from_commented`](../../tests/integration/test_procedural.py)

### <a id="unique-1203"></a>`UNIQUE-1203` — An Oracle cursor attribute the transformer does not recognize (e.g. c%BULK_ROWCOUNT) (→ other engines)

**Category:** `procedural` · **Message:** unmapped cursor attribute …%… */ (0 = 1

**Problem.** An Oracle cursor attribute the transformer does not recognize (e.g. c%BULK_ROWCOUNT) (→ other engines)

**Solution (pointer).** Warned limit — degrades to a neutral 0 carrier rather than silently becoming modulo arithmetic.

**Discussion.** Only a fixed, explicitly-mapped set of cursor attributes (%FOUND/%NOTFOUND/%ISOPEN/%ROWCOUNT) has a per-cursor state translation on T-SQL/MySQL; an attribute outside that set has no known target form, and — critically — must not fall through to the general expression parser, which would otherwise read 'c%attr' as 'c' modulo 'attr'.

**See Also.** [`TestUnknownAttributeWarns::test_unknown_attribute_warns_and_does_not_leak_modulo`](../../tests/integration/test_cursor_state_b7.py)

### <a id="unique-1205"></a>`UNIQUE-1205` — A T-SQL #temp table declared with an explicit CREATE TABLE #name (...) (→ Oracle)

**Category:** `procedural` · **Message:** was T-SQL temp table #{var}

**Problem.** A T-SQL #temp table declared with an explicit CREATE TABLE #name (...) (→ Oracle)

**Solution (pointer).** Faithful — the hoisted GTT, cleared and repopulated per call, reproduces the same session-scoped storage; the carrier is purely documentary.

**Discussion.** Same underlying gap as UNIQUE-1196 but for a real temp table rather than a table variable — Oracle has no session-scoped #temp table; the CREATE is hoisted to a GLOBAL TEMPORARY TABLE before the routine (a CREATE cannot live inside PL/SQL), and the carrier documents the substitution.

**See Also.** [`TestOracle::test_hoists_global_temporary_table`](../../tests/integration/test_temp_table_in_procedure.py)

### <a id="unique-1206"></a>`UNIQUE-1206` — COMMIT/ROLLBACK inside a T-SQL TRY/CATCH block translated to a PL/pgSQL BEGIN...EXCEPTION block (→ PostgreSQL)

**Category:** `procedural` · **Message:** {word} dropped -- the exception-guarded block is a subtransaction (transaction control there is a runtime error); it rolls back on error and commits with the surrounding transaction

**Problem.** COMMIT/ROLLBACK inside a T-SQL TRY/CATCH block translated to a PL/pgSQL BEGIN...EXCEPTION block (→ PostgreSQL)

**Solution (pointer).** Faithful (the subtransaction reproduces the same net transactional behaviour) with the explicit COMMIT/ROLLBACK dropped and documented rather than shipped as a guaranteed runtime error.

**Discussion.** PL/pgSQL's exception-guarded block is itself a subtransaction (savepoint); issuing an explicit COMMIT/ROLLBACK inside one is a runtime error ('cannot commit while a subtransaction is active') rather than a parse-time gap, and the subtransaction already provides the same rollback-on-error/commit-with-caller semantics T-SQL's TRY/CATCH expressed explicitly.

**See Also.** [`TestTopLevelTryCatch::test_begin_transaction_prefix_lowers_on_postgresql`](../../tests/integration/test_procedural.py)

### <a id="unique-1207"></a>`UNIQUE-1207` — Inherent value divergence: default-collation comparison, Oracle '' ≡ NULL, or byte-vs-char length (approved limit)

**Category:** `orchestration` · **Message:** approved value divergence (collation/encoding) kept with a warning; reason carried at runtime

**Problem.** Inherent value divergence: default-collation comparison, Oracle '' ≡ NULL, or byte-vs-char length (approved limit)

**Solution (pointer).** Approved documented limit, warned — the value or row count may differ.

**Discussion.** These divergences (case/accent/trailing-space comparison under the default collation, Oracle's '' ≡ NULL, LENGTH byte-vs-char) are per-column/connection properties the SQL text carries no trace of; no statement-level rewrite bridges them without column-collation/encoding visibility Unique does not have.

**See Also.** [`ora-empty-null`](../../tests/fixtures/challenge/challenge_oracle.sql)

### <a id="unique-1208"></a>`UNIQUE-1208` — CREATE SCHEMA (T-SQL) → Oracle

**Category:** `orchestration` · **Message:** T-SQL CREATE SCHEMA has no Oracle equivalent — an Oracle schema is a database user. Create it manually, e.g. CREATE USER {name} …; original

**Problem.** CREATE SCHEMA (T-SQL) → Oracle

**Solution (pointer).** Warned limit — documented as unsupported rather than emitting an invalid CREATE SCHEMA; create the equivalent Oracle user by hand.

**Discussion.** Oracle has no CREATE SCHEMA statement — a schema on Oracle IS a database user (created with CREATE USER and granted privileges), a fundamentally different object model from T-SQL's schema as a namespace within a shared database.

**See Also.** [`TestTranspiler::test_create_schema_oracle_documented_carrier`](../../tests/unit/core/test_transpiler.py)

### <a id="unique-1209"></a>`UNIQUE-1209` — Oracle ORGANIZATION INDEX/HEAP table-organization clause (→ PostgreSQL/T-SQL/MySQL)

**Category:** `orchestration` · **Message:** Oracle ORGANIZATION INDEX/HEAP is a physical-storage clause with no equivalent here; dropped.

**Problem.** Oracle ORGANIZATION INDEX/HEAP table-organization clause (→ PostgreSQL/T-SQL/MySQL)

**Solution (pointer).** Faithful in result (storage-only); the clause is dropped and the table converts as an ordinary table.

**Discussion.** ORGANIZATION INDEX/HEAP selects Oracle's physical row-storage strategy (index-organized vs heap-organized table) — a storage-engine-level choice with no logical-schema meaning and no equivalent concept on any other engine.

**See Also.** [`TestCrossDialectDDL::test_oracle_organization_index_table_converted`](../../tests/integration/test_cross_dialect.py)

### <a id="unique-1210"></a>`UNIQUE-1210` — ALTER TABLE t {CHECK|NOCHECK} CONSTRAINT c — a constraint's enabled/disabled check-state toggle (T-SQL) → MySQL

**Category:** `orchestration` · **Message:** … -- tsql-only, no {target} equivalent (constraint check-state

**Problem.** ALTER TABLE t {CHECK|NOCHECK} CONSTRAINT c — a constraint's enabled/disabled check-state toggle (T-SQL) → MySQL

**Solution (pointer).** Warned limit — preserved as a restorable note rather than dropped; the constraint's enforcement state on MySQL is unchanged.

**Discussion.** T-SQL's CHECK/NOCHECK CONSTRAINT toggles whether an existing constraint is currently enforced without dropping it; MySQL has no equivalent enable/disable toggle for a constraint (Oracle maps to ENABLE/DISABLE CONSTRAINT, PostgreSQL to VALIDATE CONSTRAINT) — the state change itself has nothing to become.

**See Also.** [`TestTranspiler::test_constraint_check_state_toggle`](../../tests/unit/core/test_transpiler.py)

### <a id="unique-1211"></a>`UNIQUE-1211` — EXEC sp_<name> — a T-SQL system procedure (→ other engines)

**Category:** `orchestration` · **Message:** {sp} is a SQL Server system procedure with no {target} equivalent; original call omitted

**Problem.** EXEC sp_<name> — a T-SQL system procedure (→ other engines)

**Solution (pointer).** Warned limit — the call becomes a carrier; the administrative action must be performed via the target's own tooling.

**Discussion.** T-SQL system procedures call SQL Server's own catalog/admin machinery; no other engine exposes the same operation through a callable procedure with the same name or signature.

**See Also.** [`reda-ts-exec-swallow-next`](../../tests/fixtures/challenge/challenge_sqlserver.sql)

### <a id="unique-1212"></a>`UNIQUE-1212` — A standalone INSERT/UPDATE/DELETE ... OUTPUT result set (→ Oracle / MySQL)

**Category:** `orchestration` · **Message:** {target} has no standalone OUTPUT/RETURNING result set; the statement returned: {cols} (docs/03-unsupported.md

**Problem.** A standalone INSERT/UPDATE/DELETE ... OUTPUT result set (→ Oracle / MySQL)

**Solution (pointer).** Warned limit — the DML effect is faithful; the returned result set is documented, not produced.

**Discussion.** Neither Oracle (RETURNING is PL/SQL-only, ORA-63809) nor MySQL has a standalone data-modifying-statement result set, so the OUTPUT rows cannot be returned to the caller.

**See Also.** [`ts-insert-output`](../../tests/fixtures/challenge/challenge_sqlserver.sql)

### <a id="unique-1215"></a>`UNIQUE-1215` — SET ROLE (PostgreSQL/MySQL/Oracle) → T-SQL

**Category:** `orchestration` · **Message:** T-SQL has no SET ROLE (use role membership / EXECUTE AS); statement preserved as a comment.

**Problem.** SET ROLE (PostgreSQL/MySQL/Oracle) → T-SQL

**Solution (pointer).** Warned limit — statement preserved as a comment; use role membership / EXECUTE AS on T-SQL instead.

**Discussion.** SET ROLE changes the current session's active role/privilege set on the engines that have a role system; T-SQL has no SET ROLE statement at all — role-like membership is expressed through EXECUTE AS or role membership grants instead, a structurally different mechanism.

**See Also.** [`TestWave139DecodeAndSetRole::test_set_role_degrades_tsql`](../../tests/integration/test_pg_source_wave1.py)

### <a id="unique-1216"></a>`UNIQUE-1216` — SET CONSTRAINTS ... {DEFERRED|IMMEDIATE} (PostgreSQL/Oracle) → MySQL/T-SQL

**Category:** `orchestration` · **Message:** {target} has no deferred-constraint toggling (SET CONSTRAINTS); statement preserved as a comment.

**Problem.** SET CONSTRAINTS ... {DEFERRED|IMMEDIATE} (PostgreSQL/Oracle) → MySQL/T-SQL

**Solution (pointer).** Warned limit — statement preserved as a comment.

**Discussion.** SET CONSTRAINTS toggles when a DEFERRABLE constraint's check runs (at each statement vs at COMMIT); MySQL and T-SQL have no deferrable-constraint model at all, so there is no timing to toggle.

**See Also.** [`TestZeroPushPgOnlyShapes::test_set_constraints_carrier`](../../tests/unit/core/test_ir_first_families.py)

### <a id="unique-1217"></a>`UNIQUE-1217` — SET SESSION AUTHORIZATION (PostgreSQL) → T-SQL/MySQL/Oracle

**Category:** `orchestration` · **Message:** SET SESSION AUTHORIZATION has no {target} equivalent; switch users natively.

**Problem.** SET SESSION AUTHORIZATION (PostgreSQL) → T-SQL/MySQL/Oracle

**Solution (pointer).** Warned limit — statement preserved as a comment; switch users through the target's own mechanism.

**Discussion.** SET SESSION AUTHORIZATION switches the session's effective user for privilege checks — a PostgreSQL-specific session directive; the other engines switch users through entirely different mechanisms (T-SQL EXECUTE AS, MySQL/Oracle connection-level authentication), none of which is a drop-in SQL-statement substitution.

**See Also.** [`TestSessionAuthorizationDegrades::test_session_authorization_degrades`](../../tests/integration/test_pg_source_wave1.py)

### <a id="unique-1218"></a>`UNIQUE-1218` — A PostgreSQL session GUC, e.g. SET extra_float_digits = 0 / SET x TO v / RESET x (→ T-SQL/MySQL/Oracle)

**Category:** `orchestration` · **Message:** PostgreSQL session setting has no {target} equivalent; configure the session natively.

**Problem.** A PostgreSQL session GUC, e.g. SET extra_float_digits = 0 / SET x TO v / RESET x (→ T-SQL/MySQL/Oracle)

**Solution (pointer).** Warned limit — statement preserved as a comment; configure the session natively on the target.

**Discussion.** PostgreSQL's SET/RESET cover hundreds of engine-internal session tuning knobs (query planner costs, timeouts, locale, ...) with no cross-engine namespace at all — each is either meaningless or configured through a completely different mechanism on the other three engines.

**See Also.** [`TestPgGucSettings::test_guc_assignment_degrades`](../../tests/integration/test_pg_source_wave1.py)

### <a id="unique-1219"></a>`UNIQUE-1219` — A MySQL session knob, e.g. SET sql_mode = '...' / FLUSH STATUS (→ PostgreSQL/T-SQL/Oracle)

**Category:** `orchestration` · **Message:** MySQL session setting has no {target} equivalent; configure the session natively.

**Problem.** A MySQL session knob, e.g. SET sql_mode = '...' / FLUSH STATUS (→ PostgreSQL/T-SQL/Oracle)

**Solution (pointer).** Warned limit — statement preserved as a comment; configure the session / run maintenance natively on the target.

**Discussion.** MySQL's SET (bare name, GLOBAL/SESSION/PERSIST) and its admin statements (FLUSH/LOCK TABLES/ANALYZE TABLE/...) are engine-local session and maintenance knobs with no meaning on any other engine.

**See Also.** [`TestMysqlSessionKnobsDegrade::test_knob_degrades`](../../tests/integration/test_pg_source_wave1.py)

### <a id="unique-1221"></a>`UNIQUE-1221` — TEXTIMAGE_ON <filegroup> — a T-SQL LOB-storage-placement clause (→ PostgreSQL/MySQL/Oracle)

**Category:** `orchestration` · **Message:** T-SQL TEXTIMAGE_ON filegroup clause dropped (physical storage, no logical-schema impact)

**Problem.** TEXTIMAGE_ON <filegroup> — a T-SQL LOB-storage-placement clause (→ PostgreSQL/MySQL/Oracle)

**Solution (pointer).** Faithful in result (storage-only); the clause is dropped so the CREATE TABLE converts instead of falling back to an unparsed passthrough.

**Discussion.** TEXTIMAGE_ON pins a table's LOB columns to a specific T-SQL filegroup — a physical storage-placement detail with no logical-schema meaning and no equivalent concept (filegroups themselves are T-SQL-only) on any other engine.

**See Also.** [`TestTranspiler::test_textimage_on_filegroup_stripped`](../../tests/unit/core/test_transpiler.py)

### <a id="unique-1222"></a>`UNIQUE-1222` — ALTER TABLE t WITH NOCHECK ADD CONSTRAINT ... (T-SQL) → PostgreSQL/MySQL/Oracle

**Category:** `orchestration` · **Message:** T-SQL WITH NOCHECK dropped; the constraint is added and the target validates existing rows (no NOVALIDATE applied)

**Problem.** ALTER TABLE t WITH NOCHECK ADD CONSTRAINT ... (T-SQL) → PostgreSQL/MySQL/Oracle

**Solution (pointer).** Warned limit — the constraint is added and the target validates existing rows immediately, unlike the source's NOCHECK.

**Discussion.** T-SQL's WITH NOCHECK adds a constraint without validating existing rows against it; the other engines either validate immediately with no opt-out (MySQL/Oracle) or validate immediately by default with a different deferred-validation syntax entirely (PostgreSQL's NOT VALID, a separate construct).

**See Also.** [`TestTranspiler::test_alter_add_constraint_with_nocheck_stripped`](../../tests/unit/core/test_transpiler.py)

### <a id="unique-1223"></a>`UNIQUE-1223` — A SQL*Plus client directive, e.g. SET SERVEROUTPUT ON (Oracle) → PostgreSQL/T-SQL/MySQL

**Category:** `orchestration` · **Message:** session/client directive commented out (no cross-engine equivalent); the directive is session-scoped and the specific statement is carried at runtime

**Problem.** A SQL*Plus client directive, e.g. SET SERVEROUTPUT ON (Oracle) → PostgreSQL/T-SQL/MySQL

**Solution (pointer).** Faithful (no server-side effect anywhere) — the directive is commented out rather than shipped as invalid SQL.

**Discussion.** SQL*Plus SET directives configure the CLIENT tool's display behavior — they have no server-side meaning even on Oracle itself, let alone on another engine's SQL grammar, where they are a syntax error.

**See Also.** [`test_representative_warnings_are_coded`](../../tests/unit/core/test_diagnostic_completeness.py)

### <a id="unique-1225"></a>`UNIQUE-1225` — An unrecognized IF <catalog-guard> BEGIN ... END migration-guard batch that no shape-recognizer models

**Category:** `statement` · **Message:** existence guard dropped; the guarded statement now runs unconditionally (no conditional form on the target); the specific statement is carried at runtime

**Problem.** An unrecognized IF <catalog-guard> BEGIN ... END migration-guard batch that no shape-recognizer models

**Solution (pointer).** Warned limit — the guarded statement now runs unconditionally (the guard is dropped); the original is carried in the comment.

**Discussion.** Idempotent-migration IF-guards (IF [NOT] EXISTS(...) around a DDL/DML body) are recognized and rewritten only for the shapes the guard-translation layer models; a guard body that falls outside every modeled shape (e.g. an unsupported statement inside it) cannot be safely rewritten, so it is preserved whole rather than guessed at.

**See Also.** [`TestHonestFallbackLabel::test_non_set_batch_gets_honest_signal`](../../tests/unit/core/test_guard_translation.py)

### <a id="unique-1226"></a>`UNIQUE-1226` — An IF <real-data condition> ... ELSE ... guard whose ELSE branch is not a bare diagnostic PRINT

**Category:** `statement` · **Message:** guard ELSE branch dropped (only a diagnostic PRINT can be carried into the target conditional); the specific branch is carried at runtime

**Problem.** An IF <real-data condition> ... ELSE ... guard whose ELSE branch is not a bare diagnostic PRINT

**Solution (pointer).** Warned limit — only the THEN branch is translated; the ELSE branch is dropped and carried in the comment.

**Discussion.** The IF/ELSE guard rewrite (e.g. into PostgreSQL's DO $$ ... IF ... THEN ... END IF; END $$) can carry a PRINT-only ELSE body into the target's own diagnostic-output statement, but an ELSE with real DML/DDL has no such narrow, safe rewrite — dropping vs. keeping it both risk changing which branch runs, so it is flagged rather than guessed at.

**See Also.** [`TestGuardElseBranch::test_non_print_else_warns`](../../tests/unit/core/test_guard_translation.py)

### <a id="unique-1231"></a>`UNIQUE-1231` — Any ProceduralTransformer-level warning with no more specific UNIQUE-NNNN code of its own

**Category:** `procedural` · **Message:** procedural transformation note; the specific reason is carried at runtime

**Problem.** Any ProceduralTransformer-level warning with no more specific UNIQUE-NNNN code of its own

**Solution (pointer).** Varies by the underlying message; in the bound example, a MySQL CONTINUE handler for SQLEXCEPTION has no PostgreSQL equivalent and the whole routine degrades to a documented carrier.

**Discussion.** The shared fallback code for procedural-transform warnings — most transform-level messages carry their own specific code (reconciled from the matching inline carrier in the output), but a message with no corresponding inline carrier still needs a stable code to report through rather than shipping uncoded.

**See Also.** [`TestParseFallbackDegradesCrossDialect::test_unparsed_routine_degrades_pg`](../../tests/integration/test_pg_source_wave1.py)

### <a id="unique-1233"></a>`UNIQUE-1233` — A transaction closer (COMMIT/END/ROLLBACK) whose opener failed

**Category:** `statement` · **Message:** transaction closer preserved as a comment: its opener degraded to a parse-failure carrier, so shipping the COMMIT/ROLLBACK would orphan it (no open transaction — T-SQL error 3902)

**Problem.** A transaction closer (COMMIT/END/ROLLBACK) whose opener failed

**Solution (pointer).** Coherent degrade — the closer is preserved as a comment so the output has no orphan COMMIT; both halves of the broken transaction unit are carried, not silently dropped.

**Discussion.** When a transaction opener (BEGIN) glues to the next statement and fails to parse, that whole batch degrades to a parse-failure carrier — no BEGIN reaches the output. Emitting the sibling closer as an executable COMMIT/ROLLBACK would then run against no open transaction (T-SQL error 3902), so the closer must degrade too.

**See Also.** [`TestTransactionOpenerDegradeCoherence::test_orphan_closer_after_failed_opener_degrades`](../../tests/unit/core/test_transpiler.py)

### <a id="unique-1235"></a>`UNIQUE-1235` — Oracle STANDARD_HASH(x, 'SHA1') (→ PostgreSQL)

**Category:** `expression` · **Message:** Oracle STANDARD_HASH(x, 'SHA1') (the default algorithm) has no core-PostgreSQL equivalent (needs the pgcrypto extension) — see docs/03-unsupported.md

**Problem.** Oracle STANDARD_HASH(x, 'SHA1') (→ PostgreSQL)

**Solution (pointer).** Warned limit — degrades to a NULL carrier; MD5/SHA256/SHA384/SHA512 still map faithfully (byte-for-byte, live-verified).

**Discussion.** STANDARD_HASH defaults to SHA1 when no algorithm argument is given. PostgreSQL 11+ has core md5()/sha256()/sha384()/sha512() (live-verified byte-identical to Oracle's RAWTOHEX(STANDARD_HASH(x, ALG)) for those four algorithms), but no sha1 without the pgcrypto extension, which is not assumed to be installed.

**See Also.** [`TestOracleHashFunctionsToPostgresql::test_standard_hash_sha1_degrades_honestly`](../../tests/integration/test_function_translation.py)

### <a id="unique-1236"></a>`UNIQUE-1236` — A non-id bare Oracle NUMBER column (→ MySQL / T-SQL)

**Category:** `ddl` · **Message:** {dialect} has no unbounded numeric type — column … (Oracle bare NUMBER) is bounded to DECIMAL(38, 10); values beyond that precision/scale are not representable (docs/03-unsupported.md

**Problem.** A non-id bare Oracle NUMBER column (→ MySQL / T-SQL)

**Solution (pointer).** Warned limit — values needing more than 38 total / 10 fractional digits are not representable; PostgreSQL keeps the full precision.

**Discussion.** Oracle's unqualified NUMBER holds an arbitrary-precision value. A column with no id role (not a PRIMARY KEY, UNIQUE, identity, or FOREIGN KEY) keeps that meaning as unbounded NUMERIC on PostgreSQL, but MySQL and T-SQL have no unbounded numeric type, so it is bounded to the project's canonical DECIMAL(38, 10) instead of being promoted to a fractional-value-truncating BIGINT.

**See Also.** [`TestOracleBareNumberToInteger::test_non_key_bare_number_to_tsql_bounded_and_warned`](../../tests/unit/core/test_boolean_timestamp.py)

### <a id="unique-1237"></a>`UNIQUE-1237` — SELECT ... FOR UPDATE over a non-key-preserved view (VALUES / set operation / DISTINCT / GROUP BY) → Oracle

**Category:** `statement` · **Message:** Oracle cannot FOR UPDATE from a view built on VALUES / a set operation / DISTINCT / GROUP BY (ORA-02014); the rows are not lockable, so the row lock is dropped (docs/03-unsupported.md

**Problem.** SELECT ... FOR UPDATE over a non-key-preserved view (VALUES / set operation / DISTINCT / GROUP BY) → Oracle

**Solution (pointer).** Warned limit — the unlockable row lock is dropped rather than left as an ORA-02014 runtime error; the result set is unchanged.

**Discussion.** Oracle rejects FOR UPDATE when the locked relation is not key-preserved — an inline view built on a VALUES constructor, a set operation, or DISTINCT/GROUP BY has no lockable base rows (ORA-02014). T-SQL/PostgreSQL/MySQL tolerate the same query, so the restriction bites only Oracle; a plain base-table FOR UPDATE keeps its lock.

**See Also.** [`postgresql-qdrop-FOR`](../../tests/fixtures/challenge/challenge_postgresql.sql)

### <a id="unique-1238"></a>`UNIQUE-1238` — T-SQL OPTION (MAXRECURSION n) on a recursive CTE

**Category:** `statement` · **Message:** T-SQL OPTION (MAXRECURSION n) has no portable equivalent — T-SQL raises an error once a recursive CTE exceeds n recursions (default 100), while PostgreSQL/MySQL/Oracle recursion has no such limit; the hint is dropped (see docs/03-unsupported.md)

**Problem.** T-SQL OPTION (MAXRECURSION n) on a recursive CTE

**Solution (pointer).** Warned limit — the hint is dropped; a source query that relied on the T-SQL error to bound a runaway recursion instead runs to completion (or loops) on the other three engines. A T-SQL target keeps the clause verbatim (same dialect, no divergence).

**Discussion.** MAXRECURSION is T-SQL's recursion-depth guard on a recursive CTE: the server raises an error once the recursion exceeds n levels (the implicit default is 100 when the OPTION clause is absent). PostgreSQL, MySQL and Oracle recursive queries have no equivalent depth limit — the recursion simply runs (or loops) until it terminates on its own, so there is no clause to translate the guard into.

**See Also.** [`TestMaxRecursionDroppedWithSemanticWarning::test_pg_target`](../../tests/integration/test_tsql_maxrecursion_option.py)

### <a id="unique-1239"></a>`UNIQUE-1239` — A non-MAXRECURSION T-SQL OPTION (...) query hint (MAXDOP, RECOMPILE, FORCE ORDER, KEEPFIXED PLAN, ...)

**Category:** `statement` · **Message:** T-SQL OPTION (...) query hint (e.g. MAXDOP, RECOMPILE, FORCE ORDER) has no portable equivalent — a pure optimizer directive with no effect on the result set; the hint is dropped (see docs/03-unsupported.md)

**Problem.** A non-MAXRECURSION T-SQL OPTION (...) query hint (MAXDOP, RECOMPILE, FORCE ORDER, KEEPFIXED PLAN, ...)

**Solution (pointer).** Warned limit — the hint is dropped; the result set is unchanged, only the execution plan is no longer steered. A T-SQL target keeps the clause verbatim (same dialect, no divergence).

**Discussion.** T-SQL's OPTION (...) clause carries optimizer directives — join strategy, degree of parallelism, plan caching, and similar execution-plan hints — that steer the query PLAN, not its result. No other engine has this clause, and none of these hints has an observable effect on the rows returned, so there is nothing to preserve for correctness.

**See Also.** [`TestGenericHintDroppedWithLighterWarning::test_maxdop_and_recompile_dropped`](../../tests/integration/test_tsql_maxrecursion_option.py)

### <a id="unique-1240"></a>`UNIQUE-1240` — COMPRESS() / DECOMPRESS() (T-SQL → MySQL)

**Category:** `expression` · **Message:** T-SQL COMPRESS/DECOMPRESS use the GZIP container; MySQL's same-named functions use zlib with a length prefix — the bytes differ and are not interchangeable (docs/03-unsupported.md

**Problem.** COMPRESS() / DECOMPRESS() (T-SQL → MySQL)

**Solution (pointer).** Warned limit — the transpiled COMPRESS runs on MySQL but returns different bytes than SQL Server's GZIP output; DECOMPRESS on the matching engine still round-trips.

**Discussion.** Both engines have COMPRESS/DECOMPRESS functions, but with different on-disk containers: SQL Server uses the GZIP format (RFC 1952) while MySQL uses raw zlib (RFC 1950) prefixed with a 4-byte little-endian uncompressed-length header. The compressed bytes are therefore not interchangeable — a blob produced by one engine will not DECOMPRESS on the other — and there is no built-in cross-container conversion, so the MySQL function is kept but the value is flagged as non-equal.

**See Also.** [`ts-compress`](../../tests/fixtures/challenge/challenge_sqlserver.sql)

## Diagnostics without a rationale yet

| Code | Category | Message template | Rationale |
|---|---|---|---|
| <a id="unique-1026"></a>`UNIQUE-1026` | statement | Oracle has no UPDATE ... FROM and this join shape (no ON condition) cannot become a correlated<br>subquery; rewrite as a MERGE. Original | _(rationale pending)_ |
| <a id="unique-1029"></a>`UNIQUE-1029` | statement | @@ERROR has no top-level {dialect} equivalent; use an exception handler | _(rationale pending)_ |
| <a id="unique-1035"></a>`UNIQUE-1035` | statement | TABLESAMPLE by row count has no Oracle SAMPLE form (docs/03-unsupported.md | _(rationale pending)_ |
| <a id="unique-1036"></a>`UNIQUE-1036` | statement | TABLESAMPLE by row count has no PostgreSQL equivalent (docs/03-unsupported.md | _(rationale pending)_ |
| <a id="unique-1047"></a>`UNIQUE-1047` | ddl | MySQL SET type on {col_name} has no {dialect} equivalent; stored as {varchar}({total_len}). Allowed<br>members: {quoted_values} | _(rationale pending)_ |
| <a id="unique-1070"></a>`UNIQUE-1070` | expression | Oracle DEFAULT ... ON CONVERSION ERROR has no {dialect} error-safe cast for this type; fallback<br>dropped -- see docs/03-unsupported.md | _(rationale pending)_ |
| <a id="unique-1072"></a>`UNIQUE-1072` | expression | …; no {dialect} mapping — review | _(rationale pending)_ |
| <a id="unique-1079"></a>`UNIQUE-1079` | expression | {fn} unit '{unit_sql}' has no {dialect} equivalent — the value was not computed<br>(docs/03-unsupported.md | _(rationale pending)_ |
| <a id="unique-1081"></a>`UNIQUE-1081` | expression | DATEPART(WEEKDAY) is @@DATEFIRST-dependent; assumes the session default (Sunday=1 | _(rationale pending)_ |
| <a id="unique-1086"></a>`UNIQUE-1086` | expression | EXTRACT({part}) has no {dialect} equivalent — the value was not computed (docs/03-unsupported.md | _(rationale pending)_ |
| <a id="unique-1102"></a>`UNIQUE-1102` | statement | MySQL NOT ENFORCED (a CHECK defined but not validated) has no target equivalent; enforced here | _(rationale pending)_ |
| <a id="unique-1106"></a>`UNIQUE-1106` | statement | T-SQL has no expression/function index; add a computed column and index it (docs/03-unsupported.md | _(rationale pending)_ |
| <a id="unique-1107"></a>`UNIQUE-1107` | statement | T-SQL IDENTITY() in SELECT INTO reproduced as ROW_NUMBER (id values match); the identity/auto-<br>increment column property is not portable in a CREATE TABLE AS SELECT (docs/03-unsupported.md | _(rationale pending)_ |
| <a id="unique-1111"></a>`UNIQUE-1111` | statement | {dialect} needs the column's declared type to alter its nullability and the script does not define<br>{_nn_tbl_raw}.{_nn_col}; original postgresql statement preserved | _(rationale pending)_ |
| <a id="unique-1117"></a>`UNIQUE-1117` | statement | MySQL admin command has no {dialect} equivalent; run the target's own maintenance. | _(rationale pending)_ |
| <a id="unique-1120"></a>`UNIQUE-1120` | statement | SET SESSION AUTHORIZATION has no {dialect} equivalent; switch users natively. | _(rationale pending)_ |
| <a id="unique-1121"></a>`UNIQUE-1121` | statement | PostgreSQL session setting has no {dialect} equivalent; configure the session natively. | _(rationale pending)_ |
| <a id="unique-1129"></a>`UNIQUE-1129` | statement | READ COMMITTED is Oracle's default isolation level (no-op; kept as a note so a following SET<br>TRANSACTION mode statement can still open the transaction | _(rationale pending)_ |
| <a id="unique-1130"></a>`UNIQUE-1130` | statement | READ COMMITTED is Oracle's default isolation level (no-op; kept as a note so a following SET<br>TRANSACTION mode statement can still open the transaction | _(rationale pending)_ |
| <a id="unique-1131"></a>`UNIQUE-1131` | statement | Oracle has no {level} isolation level (supports READ COMMITTED/SERIALIZABLE only); statement<br>dropped. Original | _(rationale pending)_ |
| <a id="unique-1135"></a>`UNIQUE-1135` | statement | session-variable SELECT INTO has no cross-dialect equivalent; rewrite as the target's assignment<br>form. Original | _(rationale pending)_ |
| <a id="unique-1141"></a>`UNIQUE-1141` | statement | MERGE WHEN NOT MATCHED DO NOTHING has no faithful rewrite; reason carried at runtime | _(rationale pending)_ |
| <a id="unique-1144"></a>`UNIQUE-1144` | statement | Unhandled … | _(rationale pending)_ |
| <a id="unique-1149"></a>`UNIQUE-1149` | expression | UNPIVOT has no {dialect} equivalent and the source columns are not visible to rewrite it as UNION<br>ALL — see docs/03-unsupported.md | _(rationale pending)_ |
| <a id="unique-1150"></a>`UNIQUE-1150` | expression | PIVOT has no {dialect} equivalent and the source columns are not visible to rewrite it as<br>conditional aggregation — see docs/03-unsupported.md | _(rationale pending)_ |
| <a id="unique-1181"></a>`UNIQUE-1181` | procedural | INSTEAD OF trigger aggregates over the inserted/deleted transition table; PostgreSQL INSTEAD OF<br>triggers are row-level only — port by hand (docs/03-unsupported.md | _(rationale pending)_ |
| <a id="unique-1189"></a>`UNIQUE-1189` | procedural | EXECUTE IMMEDIATE USING bindings dropped; inline them or use sp_executesql parameters | _(rationale pending)_ |
| <a id="unique-1191"></a>`UNIQUE-1191` | procedural | OUTPUT <expr> dropped — populate the temp table manually | _(rationale pending)_ |
| <a id="unique-1199"></a>`UNIQUE-1199` | procedural | T-SQL system procedure has no … equivalent; original: {original} | _(rationale pending)_ |
| <a id="unique-1204"></a>`UNIQUE-1204` | procedural | no MySQL equivalent: ALTER TRIGGER … … | _(rationale pending)_ |
| <a id="unique-1213"></a>`UNIQUE-1213` | orchestration | T-SQL default constraint value has no {target} equivalent | _(rationale pending)_ |
| <a id="unique-1214"></a>`UNIQUE-1214` | orchestration | READ COMMITTED is Oracle's default isolation level (no-op; noted so a following SET TRANSACTION mode<br>statement can still open the transaction | _(rationale pending)_ |
| <a id="unique-1220"></a>`UNIQUE-1220` | orchestration | live {target} validation rejected this statement ({first_err}); preserved as a comment | _(rationale pending)_ |
| <a id="unique-1224"></a>`UNIQUE-1224` | orchestration | batch commented out (unrecognized migration-guard shape); the specific batch is carried at runtime | _(rationale pending)_ |
| <a id="unique-1227"></a>`UNIQUE-1227` | ddl | Oracle MODIFY keeps the column's current nullability; the redundant NULL is omitted (an explicit<br>NULL raises ORA-01451 when the column is already nullable) | _(rationale pending)_ |
| <a id="unique-1228"></a>`UNIQUE-1228` | validation | internal: a parsed sqlglot construct was not consumed by the converter (unread arg) — the construct<br>may be dropped; the specific arg is carried at runtime | _(rationale pending)_ |
| <a id="unique-1229"></a>`UNIQUE-1229` | validation | DML transpilation failed (internal error); the source statement is preserved as a comment; the error<br>is carried at runtime | _(rationale pending)_ |
| <a id="unique-1230"></a>`UNIQUE-1230` | procedural | procedural parse note; the specific reason is carried at runtime | _(rationale pending)_ |
| <a id="unique-1232"></a>`UNIQUE-1232` | procedural | procedural transpilation failed (internal error); the routine is preserved; the error is carried at<br>runtime | _(rationale pending)_ |

239 codes across 6 categories (200 with a rationale).
