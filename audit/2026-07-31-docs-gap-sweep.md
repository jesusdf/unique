# Docs-gap sweep — faithful creative conversions with no user-facing doc

Analysis-only pass over the **test suite** (`tests/integration/` +
`tests/unit/core/`), directed by PURPLE. No `src/` changes, no rationale
entries written, nothing fixed. HEAD at start: `d1acd8e` (fast-forwarded,
strict ancestor, clean); the sweep itself made no code changes, so this
report applies regardless of how far `main` has moved since.

**The blind spot this hunts:** `UNIQUE-NNNN` warned degrades already have a
rationale-coverage floor (`src/unique/core/rationales.py`). The gap is
**faithful** conversions — the transpiler silently produces a *structurally
different* output than a literal reading of the input would suggest (a
rewrite, hoist, relocation, wrapper, compensation, decomposition, or
derived-table restructure), with **no warning and no code**, pinned only by
a test. The seed example, already fixed same-day: leading comments before a
routine header get relocated into the declaration section
(`docs/rationale/procedural.md`, "Comments written before a routine
header"). This sweep looks for its siblings.

## Method

1. Inventoried "already documented": every `###` heading in
   `docs/rationale/*.md` (54 constructs across 6 pages), every topic heading
   in `docs/03-unsupported.md`, `docs/05-procedural-engine.md`,
   `docs/07-interfaces.md`, and the `UNIQUE-NNNN` registry
   (`src/unique/core/rationales.py`, warned-degrade family — out of scope by
   definition).
2. Split `tests/integration/` (51 files, ~30.7k lines) and
   `tests/unit/core/` (39 files, ~7.3k lines) into 7 batches by file-size
   tier; each batch was swept independently (4 general-purpose workers ran
   synchronously, 3 ran as background agents; the largest file,
   `tests/integration/test_pg_source_wave1.py` at 8,400 lines/261 classes,
   was finished in the foreground directly by the orchestrator via a
   keyword-only docstring grep + full reads of the 32 flagged classes, no
   systematic every-Nth sample — see recall notes).
3. Each worker classified every candidate class as: (a) pure rename/spelling
   map → excluded, (b) warned degrade (`UNIQUE-NNNN`/carrier/diagnostic) →
   excluded, (c) harness/infra/identity → excluded, or (d) a faithful
   structural rewrite with no warning → checked against the documented-set
   inventory (generous matching) and reported as **covered** or **gap**.
4. This document merges the 7 batch reports: a synthesized, deduplicated
   **top-clusters** table first (the actionable list — several batches
   independently rediscovered the same mechanism from different files,
   which is itself a signal of how pervasive/undocumented it is), then the
   full raw per-batch tables as an appendix for traceability.

## Headline counts

| | Count |
|---|---|
| Rationale-page constructs already documented (`###` headings) | 54 |
| `03-unsupported.md` / `05` / `07` topics already documented | ~45 |
| Test files swept | 51 integration + 39 unit/core = 90 |
| Transformation candidates examined across all batches | ~334 |
| Already covered (generous match) | ~155 |
| **Raw gap rows reported by the 7 batches** | **179** |
| **Distinct mechanism clusters after cross-batch dedup** | **~18** |

The raw-179 number overcounts: several batches independently found the same
mechanism from different test files (e.g. the tri-state boolean CASE-wrap
turned up in 4 of 7 batches unprompted — see cluster 1). The 18-cluster list
below is the actionable one; the appendix keeps all 179 raw rows because
each still cites a distinct pinning test worth keeping for a future BLUE
pass.

## Top clusters (synthesized, ranked)

| # | Behavior (plain words) | Representative pinning tests | Suggested rationale page | Priority |
|---|---|---|---|---|
| 1 | **Boolean/predicate value duality.** A comparison, `AND`/`OR`, `IS [NOT] NULL`, or bare truthy-typed expression used in *value* position (SELECT list, computed column, assignment) on an engine without a first-class boolean-as-value gets wrapped in a tri-state `CASE WHEN p THEN 1 WHEN NOT-p THEN 0 END` (implicit `ELSE NULL`); the reverse — a numeric/bit value used in *predicate* position (`IF`, `WHILE`) — gets a `<> 0` comparison synthesized. Found independently by 4 of 7 batches without prompting. | `test_ir_first_families.py::TestZeroPush{Z4b,W1,W7}Batch`, `test_challenge.py::TestBoolColumnIsPredicate`, `test_pg_source_wave1.py::{TestSelectListComparisonsWrap,TestBooleanOpInSelectList,TestUnaryPredicateInSelectList,TestWave169NotNullParenCompare}`, `test_ir_first_families.py::TestZeroPushMysqlOracle` | `03-unsupported.md` §3.18 (currently only covers the narrow "NOT of a non-predicate" case) — needs a general "value/predicate duality" write-up, likely its own rationale page | **HIGH** |
| 2 | **Triggers have no dedicated rationale page at all.** Row-level trigger bodies (`:NEW`/`SET NEW.col`) rewritten to statement-level set-based `UPDATE ... FROM inserted/deleted` (T-SQL); event predicates (`INSERTING`/`UPDATING('col')`/T-SQL `UPDATE(col)`) rewritten per engine (`TG_OP`, `IS DISTINCT FROM`, `UPDATING(...)`); a re-reading MySQL/PG row trigger synthesized into an Oracle `COMPOUND TRIGGER`; T-SQL `INSTEAD OF` emulated on PG via `BEFORE` + `pg_trigger_depth()` suppression; a PG trigger decomposed into `CREATE FUNCTION ... RETURNS TRIGGER` + `CREATE TRIGGER`; MySQL gets the body statically duplicated per event variant. Only the pure set-based→transition-table case is documented (03-unsupported §-adjacent); everything else in this family is silent. | `test_triggers.py` (whole file), `test_trigger_predicates_scheduler.py`, `test_oracle_source_m4_wave.py::TestEventPredicates`, `test_challenge.py::TestInsteadOfTriggers`, `test_ir_first_families.py::TestTriggerShellIdiomsIrFirst`, `test_transpiler.py::test_sqlite_trigger_to_targets` | New `docs/rationale/procedural.md` "Triggers" section (multiple workers suggested this independently) | **HIGH** |
| 3 | **Procedural loop/cursor desugaring.** `SET @cur = CURSOR ... FOR q; OPEN @cur;` merges to one statement; PL/SQL `FOR rec IN cur LOOP` expands into an explicit `DECLARE`/`OPEN`/positional-`FETCH INTO`/`CLOSE`/`DEALLOCATE` scaffold with every `rec.col` rewritten to `@rec_col`; `FOR i IN a..b LOOP` desugars into an explicit `WHILE`+counter; a MySQL cursor `FOR` loop expands into `OPEN`/`FETCH`/`WHILE` with synthesized per-column `DECLARE`s in a new block. | `test_cursor_variable_binding.py`, `test_cursor_for_loop_tsql.py`, `test_oracle_mysql_tail.py::{TestNumericRangeForLoop,TestMySqlCursorForLoopExpansion}` | `docs/rationale/procedural.md` (new entries; existing scroll-cursor/`%FOUND` entries are adjacent, not this) | **HIGH** |
| 4 | **Cross-statement schema-state-driven coercion.** Integer `0`/`1` literals written into a T-SQL `BIT` column (default/INSERT/UPDATE, incl. inside procedure bodies) get coerced to `TRUE`/`FALSE` on PostgreSQL by tracking that column's declared type across statements; T-SQL `ALTER COLUMN <c> <type>` re-states the column's last-known nullability (from `CREATE TABLE`, a prior `ADD COLUMN`, or a prior `ALTER`, surviving an intervening `RENAME COLUMN`) instead of silently defaulting it to nullable; Oracle bare `NUMBER` maps to `BIGINT`/identity/`DECIMAL` depending on the column's inferred role (PK/FK/sized) in the same table. | `test_boolean_timestamp.py::{TestBitDefaultToBoolean,TestBitLiteralCoercion,TestOracleBareNumberToInteger}`, `test_pg_source_wave1.py::TestB10RunningColumnTypeAlterNullability` | `docs/rationale/ddl.md` | **HIGH** |
| 5 | **DDL guard / catalog-probe cross-engine synthesis.** A T-SQL `IF NOT EXISTS(SELECT 1 FROM sys.columns ...) ALTER TABLE ... ADD ...` idempotent guard becomes a full synthesized probe block on each target: Oracle `FOR unique_guard IN (SELECT 1 FROM DUAL WHERE NOT EXISTS(user_tab_columns...)) LOOP EXECUTE IMMEDIATE...`, PostgreSQL `DO $$ IF NOT EXISTS(information_schema.columns...)`, MySQL `PREPARE`/`EXECUTE`/`DROP PREPARE`; a guarded `DROP TRIGGER` targeting PG becomes a `pg_trigger` catalog-probe `DO $$` block (PG's `DROP TRIGGER` needs `ON table`, absent from the source guard); Oracle catalog probes (`user_indexes`, `user_tab_cols`) get rewritten to each target's native catalog. Only the `sys.objects`/`OBJECT_ID` CREATE/DROP-guard family is documented; the column/index/trigger-existence probe family is not. | `test_guard_translation.py`, `test_transpiler.py::TestTranspiler` (alter-add idempotent tests), `test_oracle_source_m4_wave.py::{TestOracleCatalogOnTsql,TestWave11Classes}` | `docs/03-unsupported.md` (extend the guard entry) | **HIGH** |
| 6 | **`CREATE TABLE AS SELECT` ↔ `SELECT ... INTO` bidirectional idiom.** T-SQL has no CTAS: rewritten as `SELECT ... INTO <table> FROM ...` (temp or plain table); the reverse direction (a plain, non-temp `SELECT INTO` from a PG/T-SQL source) becomes `CREATE TABLE ... AS SELECT ...` on MySQL/Oracle. | `test_pg_source_wave1.py::TestTsqlCtasBecomesSelectInto`, `test_challenge.py::TestSelectIntoCtas`, `test_cross_dialect.py::TestDDLPassthrough` | `docs/rationale/ddl.md` (extend the existing temp-table entry to cover the plain-table CTAS case explicitly) | **HIGH** |
| 7 | **Oracle `(+)` / `ROWNUM` reverse direction.** Oracle's `(+)` outer-join mark rewrites to an explicit `LEFT JOIN ... ON`; comma joins become `CROSS JOIN`+`WHERE`; `ROWNUM <= n` in a `SELECT ... WHERE` becomes `LIMIT`/`TOP`. `docs/rationale/dml.md` documents only the *reverse* direction of each (T-SQL flattening → Oracle, `DELETE TOP` → `ROWNUM`), so a reader trusting the existing doc would miss that these also run outbound from Oracle. | `test_oracle_join_mark.py::TestOracleJoinMark`, `test_rownum_dual.py::TestRownum` | `docs/rationale/dml.md` | **HIGH** |
| 8 | **MySQL `DECLARE {EXIT|CONTINUE} HANDLER FOR ...` folded into block-structured exception handling.** MySQL's handler is declared *separately* from the code it protects; an `EXIT` handler for `SQLEXCEPTION`/`SQLWARNING` is exactly the enclosing block's exception section and folds into `EXCEPTION WHEN OTHERS` (PG/Oracle) or wraps the whole body in `BEGIN TRY...END TRY BEGIN CATCH...END CATCH` (T-SQL). `CONTINUE` handlers and unmapped condition classes keep the honest whole-routine degrade (that part is warned/covered). | `test_pg_source_wave1.py::TestMysqlDeclareHandler` | `docs/rationale/procedural.md` (§3.5 Error Handling is TRY/CATCH↔EXCEPTION in general; this specific declarative-to-block-structured fold isn't named) | **HIGH** |
| 9 | **Expression-valued error/call arguments hoisted through a synthesized variable.** `RAISERROR`'s message argument accepts only a literal or a variable — an expression payload (e.g. a `+`/`\|\|` concatenation) hoists through a synthesized `@unique_errmsgN`; the same pattern hoists an `EXEC`/routine-call argument expression through `@uq_nowN`; Oracle's `RAISE_APPLICATION_ERROR` with an expression message hoists through a `DECLARE @unique_errmsgN`; `RAISERROR`'s printf-style `%d`/`%s` substitution args get spliced into PostgreSQL's `%`-placeholder `RAISE EXCEPTION` or Oracle's string concatenation. | `test_pg_source_wave1.py::TestTsqlRaiserrorExpressionHoist`, `test_oracle_source_m4_wave.py::{TestOracleBuiltinsOnTsql,TestWave12And13Classes}`, `test_challenge.py::TestRaiserrorFormatArgs` | `docs/rationale/procedural.md` | **HIGH** |
| 10 | **`agg(x) FILTER (WHERE p)` → universal `CASE` rewrite.** PostgreSQL's `FILTER` clause has no T-SQL/MySQL/Oracle spelling; it rewrites to `agg(CASE WHEN p THEN x END)` (with `COUNT(*) FILTER` counting a literal `1`) on every non-PG target. The existing `bool_or(...) FILTER (...)` rationale entry covers only that one aggregate; the general rewrite for any aggregate is undocumented. | `test_pg_source_wave1.py::TestAggregateFilterRewrite` | `docs/rationale/aggregates-windows.md` | **HIGH** |
| 11 | **Numeric division/rounding/precision compensation family.** Integer division compensated per target (`TRUNC(...)` on Oracle, `DIV`/`NULLIF` on MySQL/PG, `* 1.0` on decimal targets) for both literals and declared-integer variables; `AVG()` over an integer column promoted via `AVG((x) * 1.0)` on T-SQL; a fractional-literal `CAST(... AS INT)` into T-SQL wrapped in `ROUND(x, 0)` to trade truncation for rounding; MySQL's NULL-safe `a / b` preserved elsewhere by wrapping the divisor in `NULLIF(b, 0)`; `MOD`/`%` by zero guarded with `CASE WHEN divisor = 0 THEN NULL ELSE ...`. Recurred independently in 4 of 7 batches. | `test_func_compensation.py`, `test_challenge_assertions_{sqlserver,oracle,mysql}.py` (division/AVG/MOD cases), `test_challenge.py::{TestTsqlCastIntRounds,TestTsqlAvgIntegerPromotion,TestMysqlSafeDivision}` | `docs/rationale/aggregates-windows.md` (extend the existing `SUM(x)/COUNT(x)` NULL-safe-division entry into a general numeric-semantics family) | **MED** |
| 12 | **Oracle `ADD_MONTHS` sticky-last-day compensation contradicts the existing doc.** `docs/rationale/datetime.md`'s "DATEADD(MONTH) → Oracle ADD_MONTHS" entry states the *reverse* direction (Oracle `ADD_MONTHS` as source) "needs no compensation" — but `test_rc1a_mappings.py::test_add_months_preserves_sticky_last_day` shows Oracle-source `ADD_MONTHS` wrapped in a sticky-last-day `CASE WHEN` when targeting MySQL/T-SQL/PostgreSQL, and `test_pg_source_wave1.py`'s `TestOracleAddMonthsPgTypedLiteral`-adjacent tests show the PG-target emulation via `DATE_TRUNC('month', ...)`. This needs a **correction**, not just an addition — a reader trusting the current text is actively misled. | `test_rc1a_mappings.py::test_add_months_preserves_sticky_last_day` | `docs/rationale/datetime.md` (fix the existing entry) | **HIGH** |
| 13 | **Multi-join `UPDATE` restructured per engine.** `UPDATE t SET ... FROM t JOIN d ... JOIN c ...` (or the aliased single-table Oracle form) restructures differently per target: Oracle gets a correlated scalar subquery guarded by `EXISTS`; MySQL gets a comma-join `UPDATE t1, t2 SET ...`; PostgreSQL keeps `FROM`/`WHERE`. Only the analogous multi-table *DELETE* case is documented. | `test_embedded_dml_ir.py::test_multijoin_cross_table_update_rewrites_for_oracle`, `test_cross_dialect.py::TestCrossDialectDML`, `test_ir_first_families.py::TestZeroPushW3Batch` (update-from), `test_oracle_source_m4_wave.py::TestAliasedSingleTableUpdateOnTsql` | `docs/rationale/dml.md` (sibling entry to the documented multi-table DELETE) | **MED** |
| 14 | **Synthesized deterministic identifiers for anonymous constructs.** Unnamed derived-table/`SELECT INTO` projections get a synthesized alias (`uq_col1`); alias-less derived tables and join subqueries get `uq_dtN`/`uq_j`; a nameless `CREATE INDEX ON t(col)` gets a synthesized index name; a joined derived table's own alias must survive (not synthesized, but must not be dropped). | `test_challenge.py::{TestTsqlDerivedColumnName,TestSelectIntoDerivedColumnsNamed}`, `test_pg_source_wave1.py::{TestWave198BareDerivedTables,TestWave205InlineTvfJoinAlias}`, `test_ir_first_families.py::TestZeroPushW2Batch` (index naming) | `docs/rationale/ddl.md` / `dml.md` | **MED** |
| 15 | **NULL-propagation guard `CASE` wraps for functions that differ across engines.** `GREATEST`/`LEAST` NULL-propagate on MySQL but not T-SQL/PG — guarded with a synthesized `CASE WHEN ... IS NULL THEN NULL ...`; Oracle's 2-arg `REPLACE(s, search)` NULL-when-empty semantics reproduced via `NULLIF(REPLACE(s, search, ''), '')`; MySQL's `REPLACE` with a literal-NULL argument folds the whole call to `NULL`. | `test_challenge_assertions_mysql.py` (greatest/least null cases), `test_challenge.py::{TestOracleTwoArgReplaceTranslate,TestMysqlReplaceNullPropagates}` | `docs/rationale/strings-collation.md` (NULL-propagation section) | **MED** |
| 16 | **String/character-set function emulation family.** Oracle 3-arg `TRIM('x' FROM col)` emulated via nested `LTRIM(RTRIM(col,'x'),'x')`; PG-only `OVERLAY(... PLACING ...)` rebuilt via `STUFF` (T-SQL), `INSERT()` (MySQL), or `SUBSTR`+`\|\|` composition (Oracle); MySQL `INSERT(str,pos,len,new)` emulated for Oracle by splicing three `SUBSTR` calls; `STUFF` emulated via `SUBSTR`+concat (Oracle)/`OVERLAY` (PG)/`INSERT` (MySQL). | `test_pg_source_wave1.py::TestWave188IfBareCondTrimTwoArg`, `test_challenge.py::TestOverlay`, `test_challenge_assertions_mysql.py` (INSERT cases), `test_challenge_assertions_sqlserver.py` (`ts-stuff`) | `docs/rationale/strings-collation.md` | **MED** |
| 17 | **PostgreSQL row-source constructs rewritten to a portable form on every target, even ones that support the native syntax.** `FROM (VALUES (1),(2),...)` rewrites to a `UNION ALL SELECT` chain even on T-SQL/MySQL (which support `VALUES` natively); `FROM generate_series(a,b)` rewrites to `ROW_NUMBER() OVER ... sys.all_objects` (T-SQL) or `CONNECT BY LEVEL ... FROM DUAL` (Oracle); a quantified bare-`VALUES` subquery (`n > ALL (VALUES ...)`) rewrites the same way. | `test_challenge_assertions_postgresql.py` (`pg-avg-null`, `pg-bulk-insert`), `test_challenge.py::{TestGenerateSeriesFrom,TestWave5GroupingAndFolds::test_quantified_values_rewritten}` | `docs/rationale/dml.md` | **MED** |
| 18 | **Parenthesized-structure unwrapping / shielding.** Parenthesized set-operation arms (`(SELECT ...) UNION ALL (SELECT ...)`) unwrap, but an arm carrying its own `ORDER BY`/`LIMIT` is shielded by wrapping it in a derived table (so the outer union doesn't re-scope the ordering); a parenthesized join-relation group in `FROM` unwraps, hoisting the inner table+joins directly into the outer list; PostgreSQL's column-aliased table ref (`tbl AS alias(col1,col2)`) rewrites as a derived-table wrap (`(SELECT * FROM tbl) AS alias(col1,col2)`) for T-SQL. | `test_pg_source_wave1.py::{TestParenthesizedUnionArms,TestParenthesizedJoinRelations,TestTableColumnAliases}` | `docs/rationale/dml.md` | **MED** |

## Appendix — full raw findings by batch

Batches 1–4 and 7 were finished by parallel workers; batch 5
(`test_challenge.py`, 6,251 lines / 263 classes) and batch 6
(`test_pg_source_wave1.py`, 8,400 lines / 261 classes) are the two largest
files in the suite and were read via a keyword-grep-plus-sample strategy
rather than linearly in full — see each batch's recall notes. All tables
below are the workers' own output, lightly reformatted; priorities are the
individual worker's call and may differ slightly from the synthesized
cluster table above where I merged/re-ranked.

### Batch 1 — small integration files (26 files, `test_func_compensation.py` … `test_live_syntax.py`)

10 gaps reported (of ~18 transformation candidates, 8 already covered):

| Behavior | Pinning test | Priority |
|---|---|---|
| Integer division compensated per target (literal + declared-integer operands) | `test_func_compensation.py::{test_integer_division_literals_preserved,test_integer_division_declared_variables_procedural}` | MED |
| Inline column-level `REFERENCES ... ON DELETE` / `CHECK` relocated to table-level | `test_clause_drops.py::{test_inline_fk_with_on_delete_survives_to_every_target,test_inline_check_survives,test_inline_fk_without_action_survives}` | MED |
| T-SQL cursor-variable binding merged into one statement per target | `test_cursor_variable_binding.py` | HIGH |
| PL/SQL `FOR rec IN cur LOOP` expanded into full cursor scaffold | `test_cursor_for_loop_tsql.py` | HIGH |
| Oracle anonymous block flattened to a bare T-SQL batch (DECLARE/BEGIN/END dropped) | `test_anonymous_block_tsql.py` | MED |
| Unqualified T-SQL scalar UDF calls auto-qualified with `dbo.` | `test_tsql_udf_qualification.py` | MED |
| `SET NOCOUNT ON` injected into every T-SQL procedure lacking one | `test_tsql_nocount.py::test_injection_still_happens_without_body_directive` | HIGH |
| `LOG(base, x)` argument order swapped to T-SQL's `LOG(x, base)` | `test_log_arg_order.py` | MED |
| `ELT`/`FIELD` decomposed into a synthesized `CASE` chain | `test_rc1a_mappings.py::test_elt_and_field_to_case_chains` | MED |
| Oracle `ADD_MONTHS` sticky-last-day wrap contradicts existing doc | `test_rc1a_mappings.py::test_add_months_preserves_sticky_last_day` | HIGH |

### Batch 2 — mid integration files (triggers, cursors, real-world, embedded DML)

12 gaps reported (of ~28 candidates, ~16 covered):

| Behavior | Pinning test | Priority |
|---|---|---|
| Oracle `INSERTING`/`DELETING` → T-SQL `EXISTS(SELECT 1 FROM inserted/deleted)` | `test_trigger_predicates_scheduler.py::test_inserting_deleting_predicates_map_to_tsql` | HIGH |
| Row-level trigger body → T-SQL statement-level set-based `UPDATE ... FROM inserted/deleted` | `test_trigger_predicates_scheduler.py`, `test_triggers.py::{TestRowLevelTriggerToTSql,TestPgDelegatingTriggerToTSql}` | HIGH |
| T-SQL `UPDATE(col)` predicate → per-target boolean expression | `test_triggers.py::TestTriggerUpdatePredicate` | HIGH |
| Re-reading MySQL/PG trigger synthesized into Oracle `COMPOUND TRIGGER` (and reverse) | `test_triggers.py::{TestRowLevelReReadToOracleCompound,TestOracleCompoundTrigger}` | HIGH |
| `EXECUTE IMMEDIATE ... INTO x` → two-statement T-SQL dynamic-SQL capture via table variable | `test_trigger_predicates_scheduler.py::test_execute_immediate_into_tsql_capture` | HIGH |
| T-SQL base64-XML idiom → each target's native base64-decode call | `test_test2_residue_wave.py::TestScalarIdioms::test_base64_xml_idiom_per_target` | HIGH |
| Multi-join `UPDATE ... FROM` → Oracle correlated-`EXISTS` scalar subquery | `test_embedded_dml_ir.py::test_multijoin_cross_table_update_rewrites_for_oracle` | HIGH |
| `ERROR_MESSAGE()`/`RAISERROR` → per-target error-capture+re-raise idiom | `test_test2_residue_wave.py::TestScalarIdioms::test_error_message_maps_per_target` | MED |
| Nested `DECLARE ... = <expr>` hoisted to routine top with a conditional assignment left in place | `test_trigger_predicates_scheduler.py::test_nested_declare_hoists_with_conditional_assignment` | MED |
| 3-arg `CHARINDEX` on PostgreSQL compensated with `SUBSTRING`+`POSITION`+`CASE` offset | `test_trigger_predicates_scheduler.py::test_three_arg_charindex_keeps_start_on_postgresql` | MED |
| PostgreSQL trigger decomposed into `CREATE FUNCTION ... RETURNS TRIGGER` + `CREATE TRIGGER` | `test_triggers.py::TestTriggerTiming::test_after_insert_postgresql_emits_function_and_trigger` | MED |
| Trailing inline comment relocated to a leading line comment to protect the terminator | `test_embedded_dml_ir.py::test_procedural_inline_comment_does_not_eat_terminator` | LOW |

### Batch 3 — dialect assertions A (`test_oracle_mysql_tail.py`, `test_challenge_assertions_{sqlserver,oracle}.py`, `test_cross_dialect.py`, `test_oracle_source_m4_wave.py`)

31 gaps reported (of ~75 candidates, ~44 covered):

| Behavior | Pinning test | Priority |
|---|---|---|
| Bare `RETURN` in a nested MySQL handler → labeled `proc_exit:` block + `LEAVE` | `test_oracle_mysql_tail.py::TestMySqlReturnBecomesLeave` | HIGH |
| `EXECUTE...USING` binds copied into synthesized `SET @var = local` before the call | `test_oracle_mysql_tail.py::TestMySqlExecuteUsingSessionVars` | HIGH |
| `FOR i IN a..b LOOP` desugared into explicit `WHILE`+counter | `test_oracle_mysql_tail.py::TestNumericRangeForLoop` | HIGH |
| Cursor `FOR` loop expanded into `OPEN`/`FETCH`/`WHILE` scaffold (MySQL) | `test_oracle_mysql_tail.py::TestMySqlCursorForLoopExpansion` | HIGH |
| Oracle single-table `UPDATE` restructured per target (FROM/WHERE, comma-join, correlated) | `test_cross_dialect.py::TestCrossDialectDML`, `test_oracle_source_m4_wave.py::TestAliasedSingleTableUpdateOnTsql` | HIGH |
| `CREATE TYPE x FROM base` alias harvested; columns typed `x` resolve to base type | `test_cross_dialect.py::TestTSQLAliasTypes` | HIGH |
| Bare `RETURN;` in a PG trigger's nested handler → `RETURN NEW;` | `test_oracle_source_m4_wave.py::TestBareReturnInPgTriggerFunction` | HIGH |
| `RAW(16) DEFAULT SYS_GUID()` → `BYTEA` + `DECODE(REPLACE(gen_random_uuid()...))` default | `test_oracle_source_m4_wave.py::TestRawGuidDefaultOnPg` | HIGH |
| Oracle `INSERTING`/`UPDATING('col')` → PG `TG_OP`/`IS DISTINCT FROM`; MySQL body duplicated per event | `test_oracle_source_m4_wave.py::TestEventPredicates` | HIGH |
| Oracle catalog probes rewritten to target's native catalog | `test_oracle_source_m4_wave.py::{TestOracleCatalogOnTsql,TestWave11Classes}` | HIGH |
| `CAST(2.9 AS INT)` literal folds; `AVG(int)` wrapped in `TRUNC`/`TRUNCATE` | `test_challenge_assertions_sqlserver.py` (`reda-ts-cast-int-trunc`, `reda-ts-avg-int-trunc`) | MED |
| Oracle-source `int/int` division compensated with `* 1.0` | `test_challenge_assertions_oracle.py` (`ora-div*`) | MED |
| Unary bitwise NOT emulated (Oracle `-(x)-1`, MySQL `CAST(~x AS SIGNED)`) | `test_challenge_assertions_sqlserver.py` (`ts-bitops`) | MED |
| `STUFF` emulated via `SUBSTR`+concat/`OVERLAY`/`INSERT` | `test_challenge_assertions_sqlserver.py` (`ts-stuff`) | MED |
| `COT(x)` emulated as `1/TAN(x)` (Oracle) | `test_challenge_assertions_sqlserver.py` (`ts-trig`) | MED |
| Hex/binary literal folded to its integer value in arithmetic | `test_challenge_assertions_sqlserver.py` (`reda-ts-hex-literal-arith`) | MED |
| `DECODE` mixed-type branches → `CASE` with a `CAST` inserted to unify types | `test_challenge_assertions_oracle.py` (`reda-ora-decode-mixed-type`) | MED |
| DATE-literal typing propagated through a derived-table alias | `test_challenge_assertions_oracle.py` (`reda-ora-date-literal-subquery`) | MED |
| `LTRIM`/`RTRIM` with a character set → `TRIM(LEADING/TRAILING ... FROM ...)` | `test_challenge_assertions_oracle.py` (`ora-ltrim-set`, `ora-rtrim-chars`, `ora-trim-translate`) | MED |
| `GREATEST` NULL-propagation guarded with synthesized `CASE` | `test_challenge_assertions_oracle.py` (`reda-ora-greatest-null`) | MED |
| `CONVERT(type,val,style)` numeric style codes → format strings | `test_cross_dialect.py::TestConvertStyle` | MED |
| Oracle `ALTER TABLE ADD (...)` parenthesized list unwrapped per target | `test_cross_dialect.py::TestOracleAlterAddParenthesized` | MED |
| `RAISE_APPLICATION_ERROR` expression message hoisted into `DECLARE @unique_errmsgN` | `test_oracle_source_m4_wave.py::TestOracleBuiltinsOnTsql.test_error_context_and_sys_context` | MED |
| Routine-call expression argument hoisted into `DECLARE @uq_nowN` | `test_oracle_source_m4_wave.py::TestWave12And13Classes.test_exec_expression_argument_hoisted` | MED |
| Bare `BOOLEAN` variable in a condition gains explicit `= 1` (T-SQL) | `test_oracle_source_m4_wave.py::TestBooleanVarCondition` | MED |
| `SELECT ... INTO :NEW.col1, :NEW.col2` routed through MySQL session vars | `test_oracle_source_m4_wave.py::TestPseudoRowIntoTargets` | MED |
| Mid-expression line comment relocated + converted to inline `/* ... */` | `test_oracle_mysql_tail.py::{TestCommentInsideIfCondition,TestCommentInsideCaseStatement}` | LOW |
| 3-arg `CONVERT` with numeric target type ignores the style code | `test_challenge_assertions_sqlserver.py` (`reda-ts-convert-numeric-style`) | LOW |
| `LPAD` multi-character pad emulated via `REPLICATE` | `test_challenge_assertions_oracle.py` (`ora-lpad-multichar`) | LOW |
| Plain `SELECT ... INTO tbl` → `CREATE TABLE tbl AS SELECT` (MySQL/Oracle) | `test_cross_dialect.py::TestDDLPassthrough` | LOW |
| Package ref-cursor type resolved to native `REFCURSOR` (PostgreSQL) | `test_oracle_mysql_tail.py::TestPackageRefCursorType` | LOW |

### Batch 4 — dialect assertions B (`test_challenge_assertions_{postgresql,mysql}.py`, `test_procedural.py`)

20 gaps reported (of ~38 candidates, ~18 covered):

| Behavior | Pinning test | Priority |
|---|---|---|
| PG `VALUES(...)` table constructor rewritten to `UNION ALL SELECT` on every target | `test_challenge_assertions_postgresql.py` (`pg-avg-null`, etc.) | HIGH |
| Top-level T-SQL/Oracle batch wrapped in synthesized PostgreSQL `DO $$ ... $$` | `test_procedural.py::{TestTopLevelPrintAndSet,TestTopLevelTryCatch,TestExecOutputCapture,TestOracleAnonymousBlock}` | HIGH |
| `CATCH`-block-local `DECLARE` hoisted to the routine's top-level declaration section | `test_procedural.py::TestTopLevelTryCatch::test_catch_local_declare_is_hoisted_on_oracle` | HIGH |
| `generate_series` row source → `ROW_NUMBER() OVER ... sys.all_objects` / `CONNECT BY LEVEL` | `test_challenge_assertions_postgresql.py` (`pg-bulk-insert`) | HIGH |
| Bare `RETURN` in MySQL procedure → `LEAVE` + synthesized `proc_exit:` wrapper | `test_procedural.py::{TestBareReturnInProcedure,TestReturnValueInProcedure}` | HIGH |
| MySQL `CAST(x AS SIGNED)` rounds; T-SQL cast truncates — `ROUND(x,0)` inserted | `test_challenge_assertions_mysql.py` (`my-cast-int`) | HIGH |
| MySQL `ELT`/`FIELD` emulated via synthesized `CASE` on every foreign target | `test_challenge_assertions_mysql.py` (`my-elt`, `my-field`, `my-index-fns`) | HIGH |
| MySQL `GREATEST`/`LEAST` NULL-propagation guard `CASE` | `test_challenge_assertions_mysql.py` (greatest/least-null cases) | HIGH |
| `ALTER COLUMN a DROP DEFAULT` → Oracle `MODIFY DEFAULT NULL`; T-SQL dynamic-SQL script querying `sys.default_constraints` | `test_challenge_assertions_postgresql.py` (`pg-drop-default`) | HIGH |
| `AVG()` on integer/numeric widened via `*1.0` on T-SQL | `test_challenge_assertions_mysql.py` (`my-avg-precision2`) | MED |
| Positional `GROUP BY 1` resolved to the actual column name | `test_challenge_assertions_postgresql.py` (`pg-group-by-ordinal`) | MED |
| MySQL `MOD`/`%` by zero guarded (NULL-safe) vs raising engines | `test_challenge_assertions_mysql.py` (`my-mod-edge`, `my-mod-zero`) | MED |
| Bitwise NOT emulated (Oracle `-(x)-1`; MySQL `CAST(~x AS SIGNED)`) | `test_challenge_assertions_postgresql.py` (`pg-bitnot`, `pg-bit-negative`) | MED |
| CAST inside PL/SQL expression hoisted into `SELECT ... INTO ... FROM DUAL` | `test_procedural.py::TestTSQLToOracle::test_cast_in_plsql_body_drops_constraint` | MED |
| MySQL `LOCATE('', s)=1` vs T-SQL `CHARINDEX` empty-needle guard `CASE` | `test_challenge_assertions_mysql.py` (`my-locate-empty*`) | MED |
| MySQL `INSERT(str,pos,len,new)` emulated for Oracle via 3 spliced `SUBSTR` calls | `test_challenge_assertions_mysql.py` (`my-insert-*`) | MED |
| `PI()` emulated as `ACOS(-1)` (Oracle); `TRUNC(x,n)` as `ROUND(x,n,1)` (T-SQL) | `test_challenge_assertions_postgresql.py` (`pg-pi-fns`) | LOW |
| `WAITFOR DELAY` parsed to seconds, mapped to each engine's sleep primitive | `test_procedural.py::TestWaitFor` | LOW |
| `RAISERROR(<numeric-id>,...)` mapped to canned literal MySQL `SIGNAL` text | `test_procedural.py::TestRaiserrorToMySQLSignal::test_numeric_message_id` | LOW |
| Call argument recognized as ISO date wrapped in `DATE '...'` for Oracle | `test_procedural.py::TestTSQLToOracle::test_call_wraps_iso_date_argument` | LOW |

### Batch 5 — `test_challenge.py` (6,251 lines, 263 classes; ~99 read in full via sample+keyword grep)

51 merged gap rows (of ~89 candidates, ~38 covered). Full table preserved
from the worker report (grouped loosely by theme; several rows are already
folded into the synthesized clusters above — CTAS/SELECT-INTO,
triggers/`INSTEAD OF`, tri-state CASE-wrap, RAISERROR hoist, division/AVG
compensation, `VALUES`/`generate_series`, synthesized aliases):

- MySQL `HAVING` without `GROUP BY` → outer derived-table `WHERE` (`TestHavingNoGroupBy`, HIGH)
- `UPDATE` SET-subquery self-reference wrapped in a derived table for MySQL (`TestMysqlUpdateSelfRef`, HIGH)
- MySQL `UPDATE ... ORDER BY ... LIMIT n` capped via keyed subquery per target (`TestUpdateOrderByLimitCap`, HIGH)
- `generate_series` → `CONNECT BY LEVEL`/`ROW_NUMBER()` numbers source (`TestGenerateSeriesFrom`, HIGH)
- T-SQL int↔DATETIME epoch (1900-01-01) rebuilt as explicit arithmetic (`TestTsqlIntToDatetime`, `TestWave4Rewrites`, HIGH)
- ISO date-string literals into Oracle/PG promoted to ANSI `DATE '...'` (`TestDateLiteralIntoOracle`, HIGH)
- `DATE`-valued `CONCAT` argument wrapped in `TO_CHAR(d,'YYYY-MM-DD')` on Oracle (`TestConcatDateIso`, HIGH)
- Oracle `ROUND(date,'MONTH')` emulated on MySQL via day-of-month conditional (`TestRoundDateMonth`, HIGH)
- MySQL lenient string→number casts folded at transpile time (`TestMysqlLenientDecimalCast`, `TestMysqlCastUnsignedLenient`, HIGH)
- PG word-spelled boolean casts folded to 1/0 literals (`TestPgBooleanWordCast`, `TestPgBooleanCastFolds`, HIGH)
- T-SQL `CAST('true' AS BIT)` folded to a `SIGN(ABS(...))`-shaped expr (`TestBitStringCast`, HIGH)
- `OVERLAY(... PLACING ...)` rewritten to `STUFF`/`INSERT()`/`SUBSTR`+`\|\|` (`TestOverlay`, HIGH)
- Boolean-column `IS TRUE`/`IS NOT FALSE` → value comparisons (`TestBoolColumnIsPredicate`, HIGH)
- T-SQL `INSTEAD OF` triggers → PG `BEFORE`+`pg_trigger_depth()` suppression (`TestInsteadOfTriggers`, HIGH)
- Oracle 2-arg `REPLACE` NULL-when-empty via `NULLIF(REPLACE(...,''),'')` (`TestOracleTwoArgReplaceTranslate`, MED)
- MySQL NULL-safe division via `NULLIF(divisor,0)` (`TestMysqlSafeDivision`, MED)
- Fractional `CAST(...AS INT)` into T-SQL wrapped in `ROUND(x,0)` (`TestTsqlCastIntRounds`, MED)
- `AVG` over integers promoted via `AVG((x)*1.0)` (`TestTsqlAvgIntegerPromotion`, MED)
- STRING_AGG/LISTAGG value cast to `TEXT` + `WITHIN GROUP` folded (`TestStringAggTextCastIntoPg`, MED)
- Unordered `GROUP_CONCAT` gains synthesized deterministic `WITHIN GROUP (ORDER BY ...)` on Oracle (`TestGroupConcatUnorderedRefinement`, MED)
- MySQL named `WINDOW w AS (...)` inlined into each `OVER w` (`TestWave5GroupingAndFolds`, MED)
- Oracle `JSON_OBJECTAGG` gains synthesized `KEY ... VALUE` + explicit cast (`TestJsonAggregates`, MED)
- Unnamed derived-table/SELECT-INTO projection gets synthesized alias `uq_col1` (`TestTsqlDerivedColumnName`, `TestSelectIntoDerivedColumnsNamed`, MED)
- Quantified bare-`VALUES` subquery rewritten to `UNION ALL` derived subquery (`TestWave5GroupingAndFolds`, MED)
- `USING(x)` join → `ON a.x=b.x` + re-qualified bare projected `x` (`TestUsingJoinQualified`, MED)
- Self-qualified Oracle routine parameter resolved, qualifier stripped per target (`TestOracleSelfQualifiedParam`, MED)
- PG `check_violation` named condition → Oracle `WHEN OTHERS`+`SQLCODE=-2290` test+re-`RAISE` (`TestWave6Procedural`, MED)
- `RAISERROR` printf substitution args spliced per target (`TestRaiserrorFormatArgs`, MED)
- `DAYNAME`/`MONTHNAME` → `TO_CHAR(d,'fmDay'/'FMMonth')` (`TestLastDayAndNames`, MED)
- MySQL `YEAR` literal folds to 4-digit integer with 2-digit century rule (`TestTsqlIntToDatetime`, MED)
- `CONVERT(MONEY,'$12.99')` currency string stripped via nested `REPLACE` (`TestTsqlIntToDatetime`, MED)
- Oracle `ADD_MONTHS` into PG emulated via `DATE_TRUNC('month',...)` (`TestOracleAddMonthsPgTypedLiteral`, MED)
- Oracle `DECODE` NULL-safe equality spelled `WHEN NULL IS NULL THEN` (`TestOracleDecodeNullSafe`, MED)
- MySQL string-`+`-is-arithmetic preserved on T-SQL via operand folding/casting (`TestMysqlStringPlusIsArithmetic`, MED)
- MySQL `REPLACE` with literal-NULL arg folds the call to `NULL` (`TestMysqlReplaceNullPropagates`, MED)
- `DATE(x)` emitted as explicit `CAST(...AS DATE)` (`TestDateExtractCast`, MED)
- Plain `SELECT ... INTO newtable` → `CREATE TABLE ... AS SELECT` (Oracle) (`TestSelectIntoCtas`, MED)
- `ADD COLUMN` clause order swapped for Oracle; MySQL TEXT/BLOB default parenthesized (`TestAlterAddColumnDefault`, MED)
- MySQL `CONVERT(x USING charset)` → unbounded string cast (`TestConvertUsingCharset`, MED)
- `XMLELEMENT` element-name keyword/quoting requoted per target (`TestXmlElementBetweenOracleAndPg`, MED)
- MySQL binary/bit-string literals fold to integer values (`TestBitStringNumericFold`, MED)
- Single-arg `COALESCE(x)` reduced to `x` (`TestSingleArgCoalesce`, LOW)
- MySQL `WITH ROLLUP` ↔ standard `ROLLUP(x)` spelling interconversion (`TestGroupByRollup`, LOW)
- Leading `DECLARE` block reordered (variables before cursors) for MySQL (`TestMysqlCursorDeclOrder`, LOW)
- `VALUES` constructor rows wrapped in `ROW(...)` for MySQL derived tables (`TestMysqlValuesConstructorInProc`, LOW)
- Length-less MySQL `CAST(x AS CHAR)` gets synthesized bounded length on Oracle (`TestTsqlIntToDatetime`, LOW)
- MySQL `CONCAT` boolean argument stringified as `1`/`0` (`TestMysqlConcatNumBool`, LOW)
- Redundant PG `= ANY(ARRAY(subquery))` unwrapped to `= ANY (subquery)` (`TestWave4Rewrites`, LOW)
- `information_schema.tables`/`sys.tables` mapped to Oracle catalog views (`TestWave6Procedural`, LOW)
- Base64 blob-length literal folds to computed byte length (`TestLiteralFolds`, LOW)
- Wide scientific-notation numeric cast explicitly sized `DECIMAL(30,0)` (`TestLiteralFolds`, LOW)

Recall note from the worker: 164/263 classes (62%) were never read in full;
the pass-2 keyword grep is docstring-language dependent and would miss a
conversion whose docstring avoids the trigger vocabulary.

### Batch 6 — `test_pg_source_wave1.py` (8,400 lines, 261 classes; done in foreground by the orchestrator, keyword-grep only, no systematic sample)

32 classes flagged by keyword grep, all read in full. ~20 were genuine
transformation candidates, ~7 already covered (row-value tuple expansion via
the documented `dml.md` entry, `STRING_AGG ... ORDER BY` → `WITHIN GROUP`
generously covered by the LISTAGG/STRING_AGG family, `DECODE('ff','hex')` →
per-engine hex function judged rename-class, MySQL `STR_TO_DATE` known-format
→ fixed `CONVERT` style covered by §3.1). 13 gaps:

| Behavior | Pinning test | Priority |
|---|---|---|
| MySQL `DECLARE {EXIT} HANDLER FOR ...` folded into `EXCEPTION WHEN OTHERS`/TRY-CATCH | `TestMysqlDeclareHandler` | HIGH |
| T-SQL CTAS has no native form → `SELECT ... INTO <table>` | `TestTsqlCtasBecomesSelectInto` | HIGH |
| `agg(x) FILTER (WHERE p)` → universal `CASE WHEN p THEN x END` rewrite | `TestAggregateFilterRewrite` | HIGH |
| Parenthesized union arm with its own `ORDER BY`/`LIMIT` shielded via derived-table wrap | `TestParenthesizedUnionArms` | MED |
| PG column-aliased table ref (`x AS xx(xx1,xx2)`) → T-SQL derived-table wrap | `TestTableColumnAliases` | MED |
| Parenthesized join-relation group in `FROM` unwrapped, joins hoisted to outer list | `TestParenthesizedJoinRelations` | MED |
| Oracle 3-arg `TRIM('x' FROM col)` emulated via nested `LTRIM(RTRIM(...))` | `TestWave188IfBareCondTrimTwoArg::test_two_arg_trim_oracle` | MED |
| `LANGUAGE sql` bare-statement-list body parsed as statements; trailing SELECT → RETURN | `TestLanguageSqlBody` | MED |
| PG `RETURNS TABLE` single-`RETURN` body → T-SQL inline TVF (`AS RETURN (select)`) form | `TestWave205InlineTvfJoinAlias::test_inline_tvf_tsql` | MED |
| Cross-statement `ALTER COLUMN` re-states last-known nullability (survives RENAME/USING-strip) | `TestB10RunningColumnTypeAlterNullability` | MED |
| plpgsql `$1` positional refs / `ALIAS FOR` declarations resolved to the declared name, alias declaration removed | `TestPositionalParamReference`, `TestAliasForDeclaration` | MED |
| `FOR v IN EXECUTE '<literal>' LOOP` — EXECUTE dropped, query inlines directly | `TestForExecuteLiteralInlines` | LOW |
| (confirms, doesn't add) synthesized `uq_dtN`/`uq_j` aliases for alias-less derived tables/joins | `TestWave198BareDerivedTables`, `TestWave205InlineTvfJoinAlias` | — |

Recall note (orchestrator, honest): this batch skipped the systematic
every-Nth-class sample pass the other large-file batches used, due to the
"no more rounds" directive — only the keyword-flagged 32/261 classes (12%)
were read. A conversion whose docstring doesn't use the trigger vocabulary
(`relocat|hoist|rewrit|restructur|wrap|compensat|decompos|fold|synthesiz|
emulat|faithful|becomes|maps to|guard|...`) is invisible to this pass. Given
this file is the largest in the suite and organized as ~150 sequential
"wave" bug-fix classes (each pinning one narrow defect fix), the true gap
count here is very likely higher than 13 — this is the batch with the
weakest recall guarantee in the whole sweep.

### Batch 7 — `tests/unit/core/*.py` (39 files, ~7,300 lines, 3 sub-workers merged)

42 gaps reported (of 66 candidates, 24 covered) — see the synthesized
clusters above for the highest-value rows (cross-statement BIT/nullability
coercion, DDL guard synthesis, Oracle `(+)`/`ROWNUM`). Additional rows not
folded into a cluster:

| Behavior | Pinning test | Priority |
|---|---|---|
| SQLite `CREATE TRIGGER` → PG decomposed into function + trigger | `test_transpiler.py::test_sqlite_trigger_to_targets` | HIGH |
| ISO date/timestamp literals into schema-harvested DATE/TIMESTAMP columns wrapped in Oracle ANSI literals | `test_transpiler.py::TestOracleDateLiterals` | HIGH |
| MySQL tristate `NOT` emulated on Oracle with a NULL-preserving ELSE-less `CASE` | `test_ir_first_families.py::TestZeroPushMysqlOracle` | HIGH |
| PG `UPDATE ... FROM` restructured into MySQL comma-join `UPDATE t1, t2 SET ...` | `test_ir_first_families.py::TestZeroPushW3Batch` | HIGH |
| Oracle local variable colliding with a built-in name silently renamed everywhere | `test_ir_first_families.py::TestZeroPushW4Batch` | HIGH |
| 3-arg `CHARINDEX` on PG wrapped in a zero-guard `CASE` | `test_ir_first_families.py::TestCharindexStartGuardOnPg` | MED |
| `IN` refcursor param promoted to `IN OUT SYS_REFCURSOR` on Oracle (usage-inferred mode) | `test_ir_first_families.py::TestZeroPushW5Batch` | MED |
| Oracle bare `TO_NUMBER(x)` → T-SQL `CAST(x AS DECIMAL(38,10))` with invented precision | `test_ir_first_families.py::TestToNumberInIr` | MED |
| PG implicit `FOUND` flag → `@@ROWCOUNT>0`/`ROW_COUNT()>0` | `test_ir_first_families.py::TestPgFoundFlagInIr` | MED |
| `CONVERT(...,HASHBYTES(...),2)` wrapper collapses to native hash call | `test_ir_first_families.py::TestStyledConvertInIr` | MED |
| `DBMS_LOB.SUBSTR` args reordered to T-SQL `SUBSTRING` order | `test_ir_first_families.py::TestTrimPositionAndLobHelpers` | MED |
| `TRUNC(x)` on MySQL dispatches by inferred variable type (date vs numeric) | `test_ir_first_families.py::TestDateVarsContextInIr` | MED |
| Empty/comment-only trigger body synthesizes `SET NOCOUNT ON;` no-op (T-SQL forbids empty body) | `test_ir_first_families.py::{TestZeroPushZ4bBatch,TestZeroPushW5Batch}` | MED |
| `CAST(x AS BIT)` → Oracle `SIGN(ABS(x))` instead of a plain cast | `test_transformer.py::TestTypeMapper::test_bit_cast_normalizes_to_sign_abs` | MED |
| Oracle guard-loop idiom rewritten as plain `IF (NOT EXISTS(...)) BEGIN...END` on T-SQL | `test_output_gate.py::TestNoFalseGuardWarning` | MED |
| One T-SQL `ALTER COLUMN` decomposed into two PG clauses (`TYPE` + `SET NOT NULL`) | `test_transpiler.py::TestTranspiler::test_alter_column_postgres_type_then_nullability` | MED |
| Oracle parameter/RETURN types stripped of precision/scale (context-sensitive vs table columns) | `test_boolean_timestamp.py::TestOracleParameterTypes` | MED |
| Bare `DROP TABLE t` gains synthesized `IF EXISTS` on PG | `test_ddl_flags.py::TestDropGuard` | MED |
| `THROW`/`RAISERROR` → per-engine raise with synthesized Oracle number offset (`50001`→`-20001`) | `test_throw_message.py::TestThrowMessagePreserved` | MED |
| PG `ILIKE` → Oracle `UPPER(x) LIKE UPPER(pattern)` | `test_ilike_groupconcat.py::TestIlike` | MED |
| T-SQL derived-table `ORDER BY` (no LIMIT/OFFSET) silently dropped | `test_ir_first_families.py::TestZeroPushW3Batch` | MED |
| `FROM DUAL` synthesized onto table-less SELECT for Oracle | `test_rownum_dual.py::TestFromDual` | MED |
| Oracle `CREATE SEQUENCE ... AS <type>` silently dropped (ORA-03048) | `test_transpiler.py::TestCreateSequence` | LOW |
| Oracle `/` batch-terminator placement rule (only after PL/SQL blocks) | `test_transpiler.py::TestTranspiler` | LOW |
| `NVL2(e,a,b)` → `CASE WHEN e IS NOT NULL THEN a ELSE b END` | `test_function_mappings.py::TestNullFunctions` | LOW |
| `GROUP_CONCAT` gains synthesized `WITHIN GROUP (ORDER BY <arg>)` on Oracle LISTAGG | `test_ilike_groupconcat.py::TestStringAggregation` | LOW |
| `MODE() WITHIN GROUP (ORDER BY s)` collapses to Oracle `STATS_MODE(s)` | `test_ir_first_families.py::TestZeroPushW2Batch` | LOW |
| `SELECT (VALUES (1))` → `SELECT (SELECT 1)` on T-SQL | `test_ir_first_families.py::TestZeroPushW1Batch` | LOW |
| `SQLSTATE`/`SQLCODE` → `CAST(ERROR_STATE()/ERROR_NUMBER() AS NVARCHAR(n))` | `test_ir_first_families.py::TestFlipRegressions` | LOW |
| Invalid self-referential variable initializer silently dropped on Oracle | `test_ir_first_families.py::{TestZeroPushW4Batch,TestZeroPushW5Batch}` | LOW |
| `count() OVER ()` gains synthesized `*` on MySQL | `test_ir_first_families.py::TestZeroPushPgOnlyShapes` | LOW |
| No-op `OFFSET 0` dropped on T-SQL/MySQL | `test_ir_first_families.py::TestZeroPushW2Batch` | LOW |
| `PRIMARY KEY CLUSTERED (col ASC)` drops `CLUSTERED`+ordering on PG | `test_output_gate.py::TestGateEndToEnd` | LOW |

## Recall / method honesty notes

- **File-size-driven recall gradient.** Batches on files under ~1,300 lines
  (1–4, 7) read every assigned class in full; recall there is high. The two
  largest files — `test_challenge.py` (6,251 lines) and
  `test_pg_source_wave1.py` (8,400 lines), together 40% of
  `tests/integration/`'s line count — were swept via keyword-grep-on-
  docstring plus (for batch 5 only) an every-10th-class sample. A
  creative-conversion class whose docstring avoids the trigger vocabulary is
  invisible to a pure keyword pass; batch 6 in particular (this file, done
  by the orchestrator under a "no more rounds" time constraint) skipped even
  the sample pass, reading only the 32/261 (12%) keyword-flagged classes.
  ~~**`test_pg_source_wave1.py` is the weakest-coverage batch in this sweep
  and the most likely place to find additional gaps in a follow-up pass.**~~
  **Closed 2026-07-31 by Batch 6b** (below): all 261/261 classes now read in
  full, no sampling. 16 new gap rows found; see that section for the
  reconciled counts and the corrected disposition of 5 items batch 6/the
  top-cluster table had mis-scoped (2 misclassified as silent when they
  already warn, 3 already covered by `docs/03-unsupported.md` §7's
  per-target impossibility-gate bullets, which this file's batch-6 pass
  never cross-checked against). ~~Batch 5's `test_challenge.py`
  (263 classes, only ~99 read in full via sample+keyword grep, 164 never
  read) is the sibling debt of comparable size.~~ **Closed 2026-07-31 by
  Batch 5b** (below): every class not already cited by name in batch 5's own
  51 raw gap rows (215/263) was read in full, in source order, no sampling.
  18 new gap rows found — plus one stale-doc correction (the T-SQL `LIKE`
  bracket-character-class section claims "not yet fixed" for a mechanism a
  same-day RED-round-2 fix already covers) and two possible defects flagged
  for a BLUE brief (a silently-dropped `MAXRECURSION` hint; an unwarned
  `INTERSECT`/`EXCEPT ALL`→plain fallback on Oracle/T-SQL) — see that
  section for the reconciled counts and the list of candidates that turned
  out to already be covered by docs that grew same-day (`03-unsupported.md`
  §3.15/§7 in particular).
- **"Covered" calls were generous by instruction**, per the brief's
  explicit ask. Several rows credited as covered lean on family/umbrella
  statements (e.g. "NULL-propagation section," "§3.21 literal-fold
  umbrella," "the LISTAGG/STRING_AGG family") rather than an exact-mechanism
  sentence. A stricter bar would move some of those back into the gap list.
- **Cross-batch duplication is itself signal.** Four independent workers,
  reading different files with no visibility into each other's findings,
  converged on the tri-state boolean CASE-wrap pattern (cluster 1) and the
  trigger-restructuring family (cluster 2) from entirely different test
  files. That convergence is stronger evidence of a real, pervasive,
  undocumented mechanism than any single worker's report would be alone.
- **Mechanism vs. instance risk in the raw appendix.** Several raw rows
  likely share one underlying `src/` mechanism (e.g. many of the
  transpile-time literal folds, or the various synthesized-identifier
  cases) — a BLUE fix pass should cluster by mechanism before writing
  rationale entries, not fix/document one row at a time.
- **What this sweep did NOT check:** whether any of these behaviors is
  *correct* (live-DB verification was out of scope — this is a
  documentation-coverage sweep, not a correctness audit), and it did not
  read `tests/fixtures/challenge/*.sql` fixture files directly except where
  a worker cited one for evidence.

### Batch 6b — full-recall pass (2026-07-31)

**Method.** Re-derived the batch-6 keyword-grep flag set from the recall
note's own vocabulary list and confirmed it under-flagged (55/261 classes
match on a faithful re-run of the same keywords, vs. the 32 originally read
— the exact 32 aren't independently reproducible from the note alone); to
close the debt properly rather than argue over the exact prior set, this
pass instead read **all 261 classes in the file, in source order, line 1 to
8,399, with no sampling** (7 sequential full reads covering the whole file
with overlapping chunk boundaries, so no line range was skipped). Each class
was classified (a) rename/spelling, (b) warned degrade, (c)
harness/infra/parser-fix/PG-native-fidelity-bugfix, or (d) faithful
structural rewrite with no warning; every (d) candidate was checked against
the **current** state of `docs/rationale/*.md` and `docs/03-unsupported.md`
(re-read in full for this pass, since both were reported as actively
changing while this pass ran) and against this document's own top-18-cluster
table and Batch 6's original 13-row table, to avoid re-reporting an
already-known gap as new.

**A significant fraction of Batch 6's original candidates turned out to be
covered by `docs/03-unsupported.md` §7** ("Per-target impossibility gates"),
a section the original batch-6 pass — reading only 12% of the file under a
time constraint — never had the chance to cross-reference systematically.
§7 turns out to already document, in prose-bullet form (not the
`### <construct>` rationale-page format the rest of this sweep matched
against), several mechanisms this pass initially flagged as new: T-SQL
`APPLY` taking no `ON` (LATERAL-with-real-condition degrades), a PG
void/OUT-param function becoming a T-SQL/MySQL procedure, Oracle's
parenthesized-join-tree flattening, and Oracle's static-DDL
`EXECUTE IMMEDIATE` auto-wrap. A fifth candidate
(`TestCreateTableLikeClone`) turned out to already be a **warned** degrade
(`UNIQUE-1048`, fully written up in `docs/reference/warnings.md`) that this
pass initially misread as silent — corrected before this table was written.

**Counts.**

| | Count |
|---|---|
| Classes read (of 261) | **261 (100%)** |
| (d)-classified candidates (transformation, no warning) | ~95 |
| Already covered by current docs (generous match, incl. `03-unsupported.md` §7) | ~55 |
| Already a known gap elsewhere in this audit (top-18 clusters / batch 6's 13 rows), reinforced with new pinning tests but not counted again | ~24 |
| **New gap rows (distinct mechanisms, not previously surfaced anywhere in this audit)** | **16** |

**New gaps.**

| Behavior | Representative pinning tests | Suggested rationale page | Priority |
|---|---|---|---|
| PG `RETURNS void` (docstring-claimed the most common plpgsql function shape in the corpus, 62x) maps to each target's neutral scalar return type (MySQL/T-SQL `INT`, Oracle `NUMBER`) with a synthesized trailing `RETURN 0`/`RETURN NULL`; an existing explicit `RETURN;` is not duplicated. | `TestReturnsVoid` | `docs/rationale/procedural.md` | HIGH |
| PG's null-safe `IS [NOT] DISTINCT FROM` has no target operator: MySQL gets the native `<=>` (negated for `DISTINCT`); T-SQL/Oracle get a version-safe `EXISTS(SELECT a INTERSECT SELECT b)`/`NOT EXISTS(...)` rewrite, wrapped in a `CASE...THEN 1 ELSE 0 END` in value position and left bare in predicate position. (Not the same mechanism as the trigger-predicate `IS DISTINCT FROM` spelling already in `procedural.md`'s Triggers section — this is the general operator, used directly in a query.) | `TestNullSafeComparison`, `TestNullsafeValuePosition`, `TestUserVarsRowTuplesOracleDouble::test_row_tuple_intersect_unpacks` | `docs/rationale/booleans.md` or `dml.md` | HIGH |
| Trigger-context inlining, a family absent from the (otherwise thorough) new Triggers section: `TG_NAME`/`TG_TABLE_NAME`/`TG_OP`/`TG_WHEN`/`TG_LEVEL` substitute as compile-time literal constants once a function is inlined into a specific `CREATE TRIGGER`; the same `CREATE TRIGGER`'s `EXECUTE FUNCTION` argument list resolves `TG_ARGV[n]`/`TG_NARGS` the same way (an out-of-range index degrades the trigger whole); a statement trigger's `REFERENCING NEW/OLD TABLE AS <alias>` renames every reference to `inserted`/`deleted` when the body inlines for T-SQL. | `TestTgContextConstants`, `TestTgArgvSubstitution`, `TestTransitionTableAliases` | `docs/rationale/procedural.md` (extend the Triggers section) | HIGH |
| A bare result `SELECT` (no `INTO`) inside a MySQL/PG procedure has no PL/SQL spelling (Oracle forbids `SELECT` without `INTO`): it rewrites to `OPEN result_cursor FOR <query>` and synthesizes an `OUT SYS_REFCURSOR` parameter appended to the procedure's own signature; the rewrite recurses into TRY/CATCH-folded exception sections, and every same-script `CALL` site gains a matching local `uq_rcN SYS_REFCURSOR` variable and updated argument list. `docs/03-unsupported.md`'s own "Ref cursor OUT parameters" bullet describes a *different*, older, unconverted Oracle→T-SQL direction — this working, signature-propagating PG/MySQL→Oracle mechanism has no write-up anywhere. | `TestRefcursorInTryCatch`, `TestRefcursorCallSites` | `docs/rationale/procedural.md` | HIGH |
| T-SQL requires `ORDER BY` inside `OVER(...)` for ranking/offset window functions and inside `OFFSET...FETCH` pagination; a neutral `ORDER BY (SELECT NULL)` is synthesized whenever the source has none (partition-only/empty window spec, bare `OFFSET n`, MySQL's 2-arg `LIMIT o,n` embedded in procedural text). Existing explicit `ORDER BY` is left untouched. | `TestWindowOrderByRequiredOnTsql`, `TestIgnoreInvisibleOffsetOrder::test_offset_without_order_gains_null_order`, `TestWave212TsqlTwoArgLimit` | `docs/rationale/aggregates-windows.md` | MED |
| PG positional parameter references (`$1`, `$2`, ...) resolve to the declared parameter's name; type-only, argmode-first, `VARIADIC`, and dotted-unnamed-`%TYPE` parameters get synthesized names (`p1`, `p2`, ...) with every `$n` body reference rewritten to match. | `TestTypeOnlyParameters`, `TestPositionalParamReference`, `TestPgArgmodeFirstParameters`, `TestWave131Batch::test_variadic_param`, `TestWave132Batch::test_dotted_unnamed_type_param` | `docs/rationale/procedural.md` | MED |
| T-SQL has no `JOIN ... USING(c)`: it rewrites to explicit `ON` predicates, qualifying each side through a chain of joins; after a `FULL OUTER JOIN`, a later `USING` against the now-merged column becomes `ON COALESCE(t1.c, t2.c) = t3.c`. | `TestJoinUsingOnTsql` | `docs/rationale/dml.md` | MED |
| PG `PERFORM expr;` (evaluate-and-discard) converts to each target's own discard idiom: MySQL's native `DO expr;`; T-SQL synthesizes `DECLARE @uq_discardN SQL_VARIANT = (expr);`; Oracle synthesizes a nested block (`DECLARE uq_discard VARCHAR2(4000); BEGIN SELECT TO_CHAR(expr) INTO uq_discard FROM DUAL; END;`). | `TestPerformDiscard` | `docs/rationale/procedural.md` | MED |
| PG `GET STACKED DIAGNOSTICS v = MESSAGE_TEXT` (inside an exception handler) desugars to a plain per-target assignment (`SQLERRM` on Oracle, `ERROR_MESSAGE()` on T-SQL). The sibling `... = ROW_COUNT` case is already thoroughly documented (`03-unsupported.md` §3.22 + the B37 rowcount-hoist entry); this `MESSAGE_TEXT` variant is not. | `TestGetDiagnostics::test_message_text_oracle` | `docs/rationale/procedural.md` | MED |
| MySQL `REPEAT ... UNTIL cond END REPEAT` parses as a post-test loop, spelled natively per target (`LOOP ... EXIT WHEN cond END LOOP` on PG/Oracle); MySQL labeled loops (`foo: LOOP ... END LOOP foo`) and `LEAVE`/`ITERATE foo` become `<<foo>>` blocks with `EXIT foo;`/`CONTINUE;` on PG/Oracle, or a label-stripped `WHILE`/`CONTINUE` on T-SQL (no loop labels there); a `LEAVE` of the routine's own enclosing labeled `BEGIN` block becomes `RETURN`. Distinct from the already-documented `FOR`-loop/cursor-loop desugaring (cluster 3). | `TestRepeatUntilLoop`, `TestLabeledLoops`, `TestWave156LabeledBodyNoBegin`, `TestWave158LabeledBeginBlock` | `docs/rationale/procedural.md` (new "Loop desugaring" section, sibling to the existing cursor-loop entries) | MED |
| PG `CREATE DOMAIN x AS basetype` domains are harvested per-run and resolved to their base type wherever referenced off PG (parameter/return types, `DECLARE`, `::domain` casts), since no other engine has domain types. | `TestPgDomainTypes` | `docs/rationale/ddl.md` | MED |
| MySQL's `HAVING` may reference a `SELECT`-list alias; T-SQL/PostgreSQL/Oracle can't resolve an alias there, so the alias inlines to its full source expression (`HAVING a > 1` → `HAVING MAX(col1) > 1`). MySQL keeps the alias natively. | `TestWave157HavingAliasStringAggDistinct` | `docs/rationale/dml.md` | MED |
| PG's bare `OFFSET n` (no `LIMIT`) maps to MySQL's documented-nowhere-in-`docs/` magic-number all-rows idiom `LIMIT 18446744073709551615 OFFSET n` (MySQL has no bare `OFFSET`); a literal `OFFSET 0` (a no-op) drops entirely instead. | `TestWave192MysqlBareOffset` | `docs/rationale/dml.md` | MED |
| MySQL's `INSERT`/`REPLACE t SET a=1, b=2` assignment-list DML shorthand rewrites to standard `INSERT`/`REPLACE INTO t (a, b) VALUES (1, 2)` on every target. | `TestWave168InsertSetUservarIsTrue`, `TestWave189BitwiseNotReplaceSet::test_replace_set_converts` | `docs/rationale/dml.md` | LOW |
| PG `INSERT INTO t (cols) WITH cte AS (...) SELECT ...` (CTE trailing the `INSERT` clause, valid PG) reorders to `WITH cte AS (...) INSERT INTO t (cols) SELECT ...` for T-SQL, which requires `WITH` to lead the whole batch. | `TestInsertCteHoist` | `docs/rationale/dml.md` | LOW |
| Comma-list `DECLARE z1, z2 int;` / `SET a=1, b=2;` / `DROP TABLE a, b, c` / `DROP FUNCTION a, b` (forms sqlglot cannot parse as one statement) split into N separate per-item statements — valid everywhere, and for `DROP`, the only form Oracle accepts. | `TestWave159MultiDeclareMultiSet`, `TestWave236MultiTableDrop`, `TestWave239MultiObjectDrop` | `docs/rationale/ddl.md` / `procedural.md` | LOW |

**Corrections to prior batch-6/top-cluster scoping** (found while cross-checking
the new candidates against current docs, kept here rather than silently
edited into the earlier tables so the audit trail stays honest):

- `TestCreateTableLikeClone` (batch-6-adjacent, cluster-style finding) is
  **not** a silent gap — `UNIQUE-1048` warns it and `docs/reference/warnings.md`
  documents it in full. Excluded from both this table and the covered count
  above being counted as new.
- Cluster "LateralToApply", "OracleJoinTreeFlatten", "OracleDdlExecImmediate"
  and "VoidOutBecomesProc" candidates found during this pass are **covered**
  by `docs/03-unsupported.md` §7 ("Per-target impossibility gates") bullets
  under "To T-SQL"/"To Oracle" — a prose-bullet format easy to miss when
  matching only against `### <construct>` rationale-page headings, which is
  why they surfaced as apparent gaps mid-pass before the full-file §7 re-read
  caught them.

**Defects noticed, not gaps (reported here, not added to any gap table).**
None of the ~95 (d)-candidates read in this pass produced invalid or
silently-lost output on inspection — every genuinely new gap above is a
*faithful* conversion, just an undocumented one, consistent with this
sweep's scope. No `[open]`-style defect was found in `test_pg_source_wave1.py`
during this full read.

### Batch 5b — full-recall pass (2026-07-31)

**Method.** Batch 5's original 99/263 figure is not exactly re-derivable
(the report names its keyword-flagged-plus-every-10th-sample set only in
aggregate, not as a list of class names) — per the brief's fallback, this
pass instead re-derived a conservative "already covered" set from batch 5's
own **51 raw gap rows** (48 distinct `TestXxx` class names explicitly cited
as findings, cross-checked against the top-18-cluster table's own
`test_challenge.py` citations too — no additions there, full overlap) and
read **every one of the other 215/263 classes in full, in source order,
line 1 to 6,251, in seven sequential chunks with no sampling**. This is a
stricter bar than "~164 remaining" would suggest (some of batch 5's ~99
originally-read classes get re-read here), which the brief explicitly
sanctioned as the honest fallback when the original set can't be
reconstructed. Each of the 215 was classified (a) rename/spelling, (b)
warned degrade, (c) harness/infra/regression-guard, or (d) faithful
structural rewrite with no warning; every (d) candidate was checked against
the **current** state of `docs/rationale/*.md` (now 106 `###` headings, up
from 54 at the sweep's start — `booleans.md`'s `IS [NOT] DISTINCT FROM`
section and `procedural.md`'s Triggers/Loop/`RETURNS void`/refcursor-OUT
sections landed same-day) and `docs/03-unsupported.md` (including §7,
"Per-target impossibility gates," read in full per Batch 6b's lesson), and
against this document's top-18-cluster table and batch 5's own 51 rows, to
avoid re-reporting a known gap as new.

**Counts.**

| | Count |
|---|---|
| Classes read (of 263) | **215 read this pass + 48 already covered by batch 5's cited rows = 263 (100%)** |
| (d)-classified candidates (transformation, no warning) examined | ~100 (53 required a doc cross-check; ~50 more were immediately recognizable as reinforcing an existing cluster/heading without one) |
| Already covered by current docs (generous match, incl. `03-unsupported.md` §7 and §3.15/§3.16/§3.18) | ~65 |
| Reinforcing an already-known gap (top-18 clusters / batch 5's 51 rows), new pinning tests only, not counted again | ~20 |
| **New gap rows (distinct mechanisms, not previously surfaced anywhere in this audit)** | **18** |

Several candidates that looked new mid-pass turned out to be covered once
checked against the *current* (same-day-grown) docs — most notably the
entire `TRY_CAST`/`TRY_CONVERT` runtime-guard family (`TestTryCast`,
`TestTryCastMysqlNull`, `TestTryCastColumnNonliteral`) and the
`RETURNS void`/OUT-param-only-function-becomes-a-procedure family
(`TestVoidFunctionExecuteUsing`, `TestVoidFunctionToProcedure`), both
written up in detail the same day this pass ran (`03-unsupported.md` §3.15
and §7 respectively) — a reminder that "check against current docs, not a
snapshot" matters most on a day when the docs are actively growing.

**New gaps.**

| Behavior | Representative pinning tests | Suggested rationale page | Priority |
|---|---|---|---|
| A whole **collation/case-sensitivity compensation family**: comparing, ordering, or searching a string literal across a source engine's default collation and a target's differently-cased-default collation gets an explicit binary collation forced on the literal operand (`BINARY`/`COLLATE utf8mb4_bin`/`COLLATE Latin1_General_BIN2`) to preserve case-sensitive semantics — or, the reverse direction, both operands wrapped in `LOWER()` when a case-insensitive source compares against a case-sensitive target. Applies to `POSITION`, `ORDER BY`, `DISTINCT`, `GROUP BY`, `GREATEST`/`LEAST`, `INSTR`, and `REPLACE`. No warning anywhere — distinct from (and complementary to) `strings-collation.md`'s "Collation and ordering divergences" section, which documents only the *column*-collation case as an approved, unbridgeable limit; here the operand is a literal, so the transpiler *does* bridge it. | `TestPositionCaseSensitive`, `TestOrderByCaseSensitive`, `TestGreatestCaseSensitive`, `TestInstrCaseSensitive`, `TestMysqlCaseInsensitiveSearch`, `TestTsqlOrderStringsCollation`, `TestReplaceCaseSensitive` | `docs/rationale/strings-collation.md` (new section, sibling to "Collation and ordering divergences") | **HIGH** |
| **String-function positional-argument edge cases** not yet folded into the existing SUBSTRING-zero-start / REPEAT-clamp sections: PostgreSQL `LEFT(s, -n)` ("all but the last `\|n\|`") rebased to `LEFT(s, GREATEST(CHAR_LENGTH(s) + n, 0))` for MySQL (which returns `''` for a negative length); T-SQL `LEN()` excludes trailing spaces (unlike `LENGTH`/`CHAR_LENGTH`) so an `RTRIM()` wrap compensates going off T-SQL, and the reverse direction (`LEN(x \|\| '.') - 1`) compensates coming *from* a trailing-space-counting engine; MySQL rounds a fractional `SUBSTRING`/`LEFT`/`REPEAT` position or length argument (others truncate) — pre-rounded on a MySQL source. | `TestPgLeftNegative`, `TestTsqlLenTrailingSpaces`, `TestSubstringFloatArgs`, `TestNegativeLengthStringFns` | `docs/rationale/strings-collation.md` (extend the SUBSTRING-zero-start / REPEAT-clamp sections into one "string-function edge-case argument" family) | **MED** |
| **Numeric-operand `\|\|`/`+` concatenation casting.** Oracle/MySQL implicitly stringify a numeric operand of `\|\|`/`CONCAT`/(MySQL) `+`; T-SQL's `+` would instead do arithmetic on two numbers, so a numeric-operand concatenation emits T-SQL `CONCAT()` instead. PostgreSQL's `\|\|` has no `integer \|\| integer` overload at all, so when **both** operands of a `\|\|` are known-numeric they are cast to `TEXT` — but a string or unknown-typed operand is left bare (PG's own `text \|\| anynonarray` already resolves; guessing a column's type would risk a wrong cast). | `TestConcatNumberIntoTsql`, `TestConcatNumberIntoPostgres` | `docs/rationale/strings-collation.md` | **MED** |
| `GENERATED ALWAYS AS (expr)` **computed columns** are emitted per-engine (T-SQL bare `b AS (expr)` — no declared type; PostgreSQL `GENERATED ALWAYS AS (expr) STORED`; Oracle/MySQL the `VIRTUAL` form) — was previously corrupted into an `IDENTITY(1,1)` auto-increment (sqlglot's `Identity` node conflated the two). MySQL's own `AS (expr) STORED` shorthand reaches T-SQL as `AS … PERSISTED`; a chained reference to another computed column inlines the referent's expression; a typed JSON-accessor computed column (`->>`) gets a per-target typed-cast accessor form. | `TestGeneratedColumn`, `TestTypedComputedColumnShorthand` | `docs/rationale/ddl.md` | **MED** |
| An engine-specific **inline DDL attribute is decomposed into a standalone accompanying statement** rather than dropped: MySQL's inline column/table `COMMENT '…'` materializes as a separate `COMMENT ON COLUMN`/`COMMENT ON TABLE` statement on PostgreSQL/Oracle (which have no inline form); a T-SQL inline `INDEX ix (col)` table-element (which sqlglot misparses as a column literally named `INDEX`) is reconstructed and emitted as a separate `CREATE INDEX` statement on PostgreSQL/Oracle, staying inline only on T-SQL/MySQL. | `TestMysqlComments`, `TestInlineIndexReconstructed` | `docs/rationale/ddl.md` | **MED** |
| A MySQL `UNSIGNED` integer column widens to a signed type large enough to hold its range (as already documented) **and additionally synthesizes a `CHECK (col >= 0)`** on the target so the non-negativity constraint — which the wider signed type can no longer express structurally — still holds. | `TestUnsignedCheck` | `docs/rationale/ddl.md` | **MED** |
| PostgreSQL `TRUNCATE … RESTART IDENTITY` — the default behavior on MySQL/Oracle/T-SQL — is **silently stripped** with no carrier or warning (unlike the sibling `CASCADE` clause, which *is* carriered on MySQL/T-SQL when it would otherwise be dropped). Possibly an inconsistency worth a maintainer look, not just a docs gap — see defects below. | `TestTruncateRestartIdentity` | `docs/rationale/ddl.md` | **LOW** |
| **Boolean-to-text/char rendering** when the target has no boolean-to-string cast: PostgreSQL's boolean-to-text cast (`'true'`/`'false'`) and a boolean-valued comparison rendered as text are reproduced on MySQL via `CASE WHEN <bool> THEN 'true' ELSE 'false' END`; the reverse — MySQL's boolean-as-integer cast to `CHAR` (`'1'`/`'0'`), including inside `CONCAT`, which would otherwise render PostgreSQL's `TRUE`/`FALSE` literally as `'tf'` — gets the same `CASE`-wrap pattern converting to `1`/`0` first. | `TestPgBooleanToText`, `TestMysqlBooleanCast` | `docs/rationale/booleans.md` | **MED** |
| A T-SQL procedural loop (`BREAK`/`CONTINUE`, compound `+=` assignment) translated **into** MySQL gets a synthesized, per-loop-instance **unique label** (`loop_lbl_N`) so `BREAK`/`CONTINUE` can spell MySQL's `LEAVE`/`ITERATE` (which are label-targeted, unlike T-SQL's unlabeled loop-relative keywords) — nested loops never collide. This is the reverse direction of the Batch 6b "Loop desugaring" recommendation (which covered MySQL as the *source*); no "Loop desugaring" section exists yet in `procedural.md` to hold either direction. | `TestTsqlLoopControl` | `docs/rationale/procedural.md` (new "Loop desugaring" section — still not written, per both this pass and 6b) | **MED** |
| A T-SQL **cursor-loop that concatenates a dynamic-SQL string** row-by-row is recognized as a set-based string aggregation and rewritten to a single Oracle `LISTAGG(...) WITHIN GROUP (ORDER BY ROWNUM)` expression plus one `EXECUTE IMMEDIATE`, replacing the whole loop scaffold — not merely a per-statement translation but a loop-to-aggregate structural restructure. | `TestPgFnAttrsAndAggregationAssignment::test_aggregation_assignment_listagg` | `docs/rationale/procedural.md` | **MED** |
| **Oracle inverts `CAST` typing rules by context**: a PL/SQL *expression* position (e.g. a `DBMS_OUTPUT.PUT_LINE` argument) must emit a **lengthless** `VARCHAR2` cast (a constrained type there is `PLS-00103`), while a *SQL statement* position (e.g. inside a `SELECT`) must keep the length (`ORA-00906` without it) — the same source `CAST` emits differently depending on which Oracle grammar context it lands in. | `TestPlsqlExpressionCastContext` | `docs/rationale/procedural.md` | **MED** |
| A T-SQL **scalar function** whose body ends in an all-branches-return `IF`/`ELSE` gains a synthesized, unreachable **trailing `RETURN NULL`** — T-SQL requires a scalar function's last statement to *be* a `RETURN` (error 455) even when every branch already returns. | `TestTsqlScalarFunctionTrailingReturn` | `docs/rationale/procedural.md` | **MED** |
| A T-SQL CTE that **references its own name is detected as recursive** and gains the `WITH RECURSIVE` keyword PostgreSQL/MySQL require (T-SQL and Oracle infer recursion without one); going to **Oracle**, a recursive CTE without an explicit column-alias list gets one **derived from the anchor `SELECT`'s output names** (`ORA-32039` otherwise). Possible companion defect: the T-SQL-only `OPTION (MAXRECURSION n)` hint is dropped with **no carrier or warning** anywhere in the pinning test — see defects below. | `TestRecursiveCteKeyword`, `TestRecursiveCteOracleColumnList` | `docs/rationale/dml.md` | **HIGH** |
| MySQL's **compound `EXTRACT` units** (`YEAR_MONTH`, `DAY_HOUR`, `DAY_MINUTE`, …, which have no equivalent unit anywhere else) are rebuilt from their component fields with positional decimal weights (e.g. `YEAR_MONTH` → `EXTRACT(YEAR ...) * 100 + EXTRACT(MONTH ...)`). Distinct from the already-documented "Multi-field PostgreSQL INTERVAL decomposition" (a different source construct: an interval *value*, not an `EXTRACT` unit). | `TestCompoundExtract` | `docs/rationale/datetime.md` | **MED** |
| Oracle `MONTHS_BETWEEN` is **fractional** (whole months plus `(day1-day2)/31`, collapsing to a whole number only when both dates are month-ends or share a day-of-month); translated to T-SQL as the **exact** `CASE`-based fractional formula, not an integer `DATEDIFF`-boundary count (which would silently change the value's precision class, not just its formatting). | `TestMonthsBetweenFractional` | `docs/rationale/datetime.md` | **MED** |
| **Explicit parentheses inserted for cross-engine bitwise/arithmetic operator-precedence mismatches**: MySQL and Oracle bind bitwise operators (`&`, `\|`, `<<`) *looser* than `+`/`*`; PostgreSQL and T-SQL bind them *tighter*. A mixed source expression (e.g. MySQL's `10 & 6 + 1`, meaning `10 & (6 + 1)`) is parenthesized explicitly on the way to a tighter-binding target so the source's grouping can't silently re-associate. | `TestBitwiseArithmeticPrecedence` | `docs/rationale/strings-collation.md` or a new operators page (no existing page covers operator precedence generally) | **MED** |
| PostgreSQL `regexp_replace`'s 4th argument is a **flags string** (`g`/`i`); Oracle/MySQL take a numeric position/occurrence and are global by default. The `g` flag is dropped rather than leaked as a bogus positional argument, and going to MySQL the pattern's backslashes are doubled and backreferences respelled `$N` (from PG's `\N`). | `TestRegexpReplaceFlags` | `docs/rationale/strings-collation.md` | **LOW** |
| `INTERSECT ALL`/`EXCEPT ALL` (duplicate-preserving set operations) are preserved on the two engines that support an `ALL` form (MySQL 8.0.31+, PostgreSQL); Oracle and T-SQL have no `ALL` spelling and silently fall back to the duplicate-collapsing plain form — a genuine row-multiset change with **no carrier or warning** in the pinning test for that fallback leg. Possible companion defect — see below. | `TestSetOperationAll` | `docs/rationale/dml.md` | **LOW** |

**Stale-doc correction found while cross-checking (not a new gap — an existing entry is now wrong).**
`docs/rationale/strings-collation.md`'s "T-SQL LIKE character classes
(`'[A-C]%'`) — open, observed divergence" section states, twice, that the
bracket-character-class mistranslation is **"not yet fixed"** ("*What would
fix it (not yet done).*"). It is fixed: `test_challenge.py`'s
`TestTsqlLikeCharClassTranslated` (RED round-2, `red2-ts-like-charclass`,
live-verified 2026-07-30 — the same day this section was apparently
written) shows the transpiler now rewrites the bracket class to a portable
predicate per target (PostgreSQL `SIMILAR TO`, MySQL/Oracle
`REGEXP`/`REGEXP_LIKE`, both anchored). This is the same shape of doc-vs-code
drift the original sweep's cluster 12 (Oracle `ADD_MONTHS`) caught — the doc
needs a correction, not an addition, the next time `strings-collation.md` is
touched.

**Defects noticed, not gaps (flagged here for a BLUE follow-up brief, not
added to any gap table or `docs/TODO.md`).**
- `TestRecursiveCteOracleColumnList`'s pinning test drops the T-SQL-only
  `OPTION (MAXRECURSION n)` hint with no warning assertion anywhere —
  possible silent semantic loss (the target's recursion-depth ceiling
  reverts to its default, e.g. PostgreSQL's unbounded vs. T-SQL's 100).
- `TestSetOperationAll` only pins the MySQL/PostgreSQL `ALL`-preserving
  leg; the Oracle/T-SQL fallback-to-distinct leg (a genuine duplicate-row
  loss) has no warning in the pinning test either.
- `docs/rationale/strings-collation.md`'s own "Positional string-splice"
  section (already-documented, not a gap from this pass) names a **live**
  defect it found while being written: MySQL `INSERT()`'s out-of-bounds
  identity-return semantics are guarded only on the MySQL→T-SQL leg;
  MySQL→Oracle/PostgreSQL and the native `STUFF`/`OVERLAY`→Oracle/PostgreSQL
  paths carry no such guard (a wrong value, silently, on Oracle; PostgreSQL's
  `OVERLAY(... FROM 0 ...)` raises an invalid-statement runtime error with no
  warning at all). Restating it here since it is a genuine open defect
  sitting in committed docs, unscored against any corpus case.

**What this pass did NOT check**, same scope boundary as the rest of this
sweep: live-DB correctness of the ~65 "already covered" dispositions, and
`tests/fixtures/challenge/*.sql` fixture content beyond what a cited test
already quoted.

### Batch 8 — remaining test directories (2026-07-31)

**Method.** The original sweep and its 6b/5b follow-ups covered
`tests/integration/`, `tests/unit/core/` (39 top-level files), and (in 6b/5b)
the two largest integration files in full. This batch closes the rest of
the test tree: every directory `ls tests/` reveals that no prior batch
touched — `tests/unit/core/procedural/` (missed by the original "39 files"
count, which stopped at `tests/unit/core/`'s top level and did not descend
into its `procedural/` subdirectory), `tests/unit/api/`, `tests/unit/dialects/`,
`tests/unit/cli/`, `tests/unit/helpers/`, `tests/functional_equivalence/`,
`tests/property/`, and `tests/unit/`'s own top-level files. Three workers
each read every `test_*.py` file in their assigned directories **in full**
(40 files, 8,234 lines, no sampling — these directories are small enough
that full reads were feasible throughout, unlike the two giant integration
files 6b/5b had to close separately), applied the same (a)/(b)/(c)/(d)
classification as every prior batch, and checked every (d) candidate
against the **current** `docs/rationale/*` article set (now organized as
per-topic subdirectories, e.g. `docs/rationale/procedural/*.md`, not the
flat files the original sweep inventoried against — the flat
`docs/rationale/<topic>.md` files are now redirect stubs) and
`docs/03-unsupported.md` in full, including §7. Every worker-reported
candidate gap was independently re-verified by the orchestrator: reading
the pinning test's actual assertions, re-probing the transpiler directly
(`PYTHONPATH=$PWD/src .venv/bin/python`) for the exact output and warning
set, and live-executing the produced SQL against the target engine (Oracle,
PostgreSQL, MySQL) before accepting it as a genuine, unwarned, faithful gap.

**Per-directory counts.**

| Directory | Files (lines) read | Candidates examined | Covered / excluded | New gaps |
|---|---|---|---|---|
| `tests/unit/core/procedural/` | 15 (3,452) | ~230 | ~31 (28 covered + 3 reinforcing known clusters) | 3 (1 more reported by the worker was reclassified — see correction below) |
| `tests/unit/api/` | 1 (1,052) | 21 | 21 — all (a)/(c) HTTP/API plumbing | 0 |
| `tests/unit/dialects/` | 1 (101) | 4 | 4 — all (a)/(c) registration smoke tests | 0 |
| `tests/unit/cli/` | 1 (251) | 6 | 6 — all (c) CLI plumbing | 0 |
| `tests/unit/helpers/` | 6 (690) | 18 | 18 — all (c) dev-tooling-script tests | 0 |
| `tests/functional_equivalence/` | 3 (630) | ~30 | 30 — all (c) harness self-tests (1 reinforces cluster 2, triggers) | 0 |
| `tests/property/` | 2 (248) | ~11 | 11 — all (c) hypothesis fuzz-invariant harness | 0 |
| `tests/unit/` (top-level, 11 files) | 11 (1,810) | ~123 | 123 — all (c) CI/ratchet/tooling self-tests | 0 |
| **Total** | **40 (8,234)** | **~443** | **~440** | **3** |

Every non-`procedural/` directory closed at **zero** new gaps — confirmed,
not assumed: `tests/unit/api/`, `tests/unit/dialects/`, `tests/unit/cli/`,
`tests/unit/helpers/`, `tests/functional_equivalence/`, `tests/property/`,
and `tests/unit/`'s own top-level files are API/CLI-surface plumbing,
dialect-registration smoke tests, dev-tooling-script unit tests, and the
project's own CI/quality-gate self-tests (ratchet floors, docs-generator
determinism, packaging tripwires, a private-corpus leak scanner, mutation-
and property-fuzz harnesses) — none of them pins a source-engine-to-target
SQL structural rewrite as its subject. `tests/unit/core/procedural/` (a
low-level lexer/parser/transformer/emitter unit suite) was the one directory
in scope with real transpilation-behavior content, and even there the vast
majority of candidates were internal-mechanics tests, not user-facing
conversions — consistent with the brief's expectation that this sweep would
find few new gaps this late in the campaign.

**New gaps.**

| Behavior | Pinning test(s) | Rationale article written | Priority |
|---|---|---|---|
| T-SQL subquery-in-expression variable assignment (`SET @x = (SELECT …)`, including nested inside another call, and a `DECLARE @x = (SELECT …)` initializer) restructures into Oracle `SELECT <expr> INTO x FROM DUAL` — PL/SQL's `:=` forbids a subquery anywhere in its expression (`PLS-00405`). A declare-section initializer can't become a `SELECT … INTO` in place either, so the variable is declared bare and the `SELECT … INTO` is hoisted to the top of the body, ahead of first use. | `test_oracle_subquery_assign.py::{TestOracleSubqueryAssignment,TestOracleSubqueryDeclareInit}` | [`docs/rationale/procedural/tsql-subquery-assignment-to-oracle-select-into.md`](../docs/rationale/procedural/tsql-subquery-assignment-to-oracle-select-into.md) | HIGH |
| Oracle `NUMTODSINTERVAL(n,'unit')`/`NUMTOYMINTERVAL(n,'unit')`, used as the **source**, rewrites to PostgreSQL interval-literal arithmetic (`n * INTERVAL '1 <unit>'`, or a folded `INTERVAL '<n> <unit>'` for a literal count) across `RETURN` expressions, assignment RHS, and embedded DML. Only the reverse direction (T-SQL `DATEADD` → Oracle `NUMTODSINTERVAL` as a **target**) was previously documented, in passing, in `03-unsupported.md` §3.1. | `test_numtointerval.py::TestNumToIntervalToPostgres` (all 4) | [`docs/rationale/datetime/numtointerval-oracle-to-postgresql.md`](../docs/rationale/datetime/numtointerval-oracle-to-postgresql.md) | MED |
| T-SQL `@@FETCH_STATUS`, used as the **source**, maps per target: Oracle's cursor-scoped `%FOUND`/`%NOTFOUND`, PostgreSQL's implicit `FOUND`, or a synthesized MySQL handler flag (`DECLARE ... DEFAULT FALSE` + `DECLARE CONTINUE HANDLER FOR NOT FOUND SET ...`). The existing cursor-attribute article documents only the reverse direction (Oracle `%FOUND` as source → T-SQL/MySQL). | `test_transformer.py::TestIrFetchStatusContext` (6 tests) | [`docs/rationale/procedural/tsql-fetch-status-to-oracle-postgresql-mysql.md`](../docs/rationale/procedural/tsql-fetch-status-to-oracle-postgresql-mysql.md) | MED |

**Correction to a worker-reported candidate (not a gap).** The
`tests/unit/core/procedural/` worker also flagged T-SQL `STRING_SPLIT(...)`
in a `FROM` clause → MySQL `JSON_TABLE(...)` (`test_transformer.py::
TestMySQLStringSplit`) as a fourth silent gap. Re-probing it through the
full `Transpiler` (the unit test calls `ProceduralTransformer._transform_node`
directly, bypassing the pipeline layer that attaches warnings) shows it
**does** carry a warning — `UNIQUE-1231` ("Embedded DML not modeled by the
IR converter … review the statement") — while a control statement with the
same shape but no `STRING_SPLIT` transpiles with zero warnings. That makes
it classification (b), already excluded by this sweep's own rule; it is not
counted as a new gap here.

**Stale-doc correction found while cross-checking (not a new gap).**
`docs/03-unsupported.md` §3.1 states that functions needing argument
reordering (`CHARINDEX`↔`INSTR`↔`LOCATE`, `DECODE`→`CASE`) "are emitted with
an inline review comment rather than a guessed conversion." Live-probing
both shows this is stale: `test_transformer.py::{TestSubstringPosition,
TestDecode}` and a direct transpile of each confirm both are silently,
exactly auto-converted with **no** review comment and **no** warning (a grep
for "review comment"/"guessed conversion" across `src/unique/core/procedural/`
returns nothing). Same shape of drift as cluster 12 (`ADD_MONTHS`) and the
Batch 5b `LIKE`-bracket-class correction — needs fixing the next time §3.1
is touched, not counted as a docs gap here since the behavior it describes
*is* covered elsewhere (§3.1's own DATEADD/DATEDIFF/string-function bullets).

**Defects noticed, not gaps.** None. Every genuine new gap above was
live-verified (Oracle, PostgreSQL, and MySQL, per the target) to produce
valid, faithful output — no invalid SQL or silent semantic loss was found
in this batch's scope.

**The whole test tree is now swept.** Between the original sweep
(`tests/integration/` + `tests/unit/core/` top level), Batch 6b and 5b
(the two giant integration files read in full), and this batch (every
remaining directory `ls tests/` reveals, including the one subdirectory —
`tests/unit/core/procedural/` — the original file-count missed), every
`test_*.py` file under `tests/` has now been read and classified at least
once by this audit. No test directory remains unswept.

### Raw-appendix reconciliation (2026-07-31, brief D1c-2)

**Method.** Every row of batches 1–4 and 7's raw tables above (115 rows —
these five were never re-swept by 5b/6b, whose full-recall passes covered
only batches 5 and 6) was checked, in order, against the **current**
`docs/rationale/**/*.md` (the per-article-page layout the rationale set
migrated to since this sweep started — 134 article files, up from the
single-page-per-topic layout this document's own top-18-cluster table
still cites) and `docs/03-unsupported.md`, matched strictly by mechanism
per this document's own honesty note above, not by family/umbrella
statement. A row already folded into the top-18-cluster table or into
Batch 6b/5b's new-gap tables (found while cross-checking, since those two
passes ran the same day and occasionally reinforced a batch 1–4/7 row with
a second pinning test) is counted **covered** here without a second
article — clusters 4, 5, and 7 in particular absorb nine of batch 7's 42
rows this way. Every remaining genuine gap was verified against the
transpiler directly (`PYTHONPATH=src .venv/bin/python`, live output
captured and quoted in the new article) before being written up, and new
articles cite the sweep's own pinning test(s) in **See Also**.

**Per-batch counts.**

| Batch | Rows | Covered | Gap → new article | Stale | Open (deferred) |
|---|---|---|---|---|---|
| 1 — small integration files | 10 | 4 | 6 | 0 | 0 |
| 2 — mid integration files (triggers/cursors) | 12 | 6 | 5 | 0 | 1 |
| 3 — dialect assertions A | 31 | 13 | 16 | 0 | 2 |
| 4 — dialect assertions B | 20 | 8 | 10 | 0 | 2 |
| 7 — `tests/unit/core/*.py` | 42 | 18 | 16 | 0 | 8 |
| **Total** | **115** | **49** | **53** | **0** | **13** |

No **stale** rows turned up in these five batches (the ADD_MONTHS stale-doc
correction batch 1's own row 10 flagged was already fixed same-day, before
this reconciliation ran — `docs/rationale/datetime/oracle-add-months-to-dateadd.md`
covers it directly, cited below as **covered**).

**53 gap rows → 41 new articles** (several rows share one underlying
mechanism and are cited together in one article — e.g. batch 3's `EXECUTE
IMMEDIATE ... USING` and its own row; the ELT/FIELD pair from batches 1 and
4; the `CAST ... AS BIT`/unary-bitwise-NOT/COT-PI-TRUNC math-function
trio; the Oracle `TO_NUMBER`/`DBMS_LOB`/`TRUNC`-dispatch LOB-helper family;
batch 2's nested-`DECLARE`-hoist row and batch 4's `CATCH`-local-`DECLARE`
row, one mechanism). New articles, by topic:

- **procedural** (20): `anonymous-block-flattens-to-tsql.md`,
  `tsql-udf-auto-qualification.md`, `nocount-injected-default.md`,
  `execute-immediate-into-capture.md`, `base64-xml-idiom-per-target.md`,
  `error-message-function-per-target.md`, `mid-block-declare-hoist.md`,
  `mysql-execute-using-session-vars.md`,
  `pseudo-row-into-mysql-session-vars.md`,
  `refcursor-package-type-and-inout-mode.md`,
  `toplevel-batch-do-block-wrap.md`,
  `oracle-builtin-name-collision-rename.md`,
  `throw-raiserror-numeric-code-per-target.md`,
  `constrained-cast-hoisted-select-into-dual.md`,
  `oracle-formal-parameter-types-unconstrained.md`,
  `oracle-lob-numeric-helpers-to-tsql.md`,
  `sqlstate-sqlcode-to-tsql-error-functions.md`,
  `convert-hashbytes-wrapper-collapse.md`
- **strings-collation** (9): `charindex-start-argument-zero-guard.md`,
  `unary-bitwise-not-emulation.md`, `hex-binary-literal-arithmetic-fold.md`,
  `oracle-ltrim-rtrim-charset-reverse.md`,
  `decode-mixed-type-branch-cast.md`, `locate-empty-needle-guard.md`,
  `ilike-upper-comparison.md`, `no-target-spelling-case-chain.md`
- **ddl** (7): `inline-fk-check-relocated-table-level.md`,
  `create-type-alias-harvested.md`, `raw-guid-default-bytea.md`,
  `alter-column-drop-default.md`, `oracle-alter-add-parenthesized-unwrap.md`,
  `drop-table-idempotent-if-exists.md`
- **datetime** (3): `schema-harvested-date-literal-to-oracle.md`,
  `date-typing-propagated-through-derived-table.md`,
  `convert-style-code-per-target.md`
- **aggregates-windows** (3): `math-function-per-engine-spelling.md`,
  `tsql-cast-int-truncation-reverse.md`,
  `group-concat-synthesized-within-group-oracle.md`
- **booleans** (2): `oracle-boolean-variable-bare-condition.md`,
  `tsql-cast-as-bit-normalizes.md`
- **dml** (1): `group-by-ordinal-resolved.md`

**13 rows left open (deferred, all LOW priority).** Every one of these was
already marked LOW by the originating batch worker; none is a defect (each
is a faithful, warning-free rewrite), and each is small enough that a
future BLUE pass can fold it into an existing article's family rather than
needing a new one:

- Comment relocation (2 rows, one mechanism): a trailing inline comment
  that would otherwise swallow a statement terminator
  (`test_embedded_dml_ir.py::test_procedural_inline_comment_does_not_eat_terminator`),
  and a mid-condition line comment converted to an inline block comment
  (`test_oracle_mysql_tail.py::TestCommentInsideIfCondition`) — comments
  are trivia by this project's own architecture guardrail, and the
  existing "Comments written before a routine header" entry is the natural
  home for a "comment relocation" family once a second example lands.
- `LPAD` multi-character pad emulated via `REPLICATE` (Oracle → T-SQL) —
  `test_challenge_assertions_oracle.py` (`ora-lpad-multichar`).
- `WAITFOR DELAY` parsed to seconds, mapped to each engine's sleep
  primitive — `test_procedural.py::TestWaitFor`.
- A call argument recognized as an ISO date wrapped in `DATE '...'` for
  Oracle — `test_procedural.py::TestTSQLToOracle::test_call_wraps_iso_date_argument`
  (a narrower instance of the schema-harvested date-literal mechanism this
  reconciliation did write up; this row is a *call-argument*, not a
  column-typed `INSERT`/`UPDATE` literal).
- Oracle `CREATE SEQUENCE ... AS <type>` silently dropped —
  `test_transpiler.py::TestCreateSequence`.
- Oracle `/` batch-terminator placement rule — `test_transpiler.py::TestTranspiler`
  (not independently re-verified against current docs beyond the grep
  pass; likely already implied by the general PL/SQL-block-termination
  handling, but no article claims it explicitly).
- `MODE() WITHIN GROUP (ORDER BY s)` → Oracle `STATS_MODE(s)` —
  `test_ir_first_families.py::TestZeroPushW2Batch`.
- `SELECT (VALUES (1))` → `SELECT (SELECT 1)` on T-SQL —
  `test_ir_first_families.py::TestZeroPushW1Batch`.
- An invalid self-referential variable initializer (`x NUMERIC := x`)
  silently dropped on Oracle — `test_ir_first_families.py::TestZeroPushW4Batch`
  /`TestZeroPushW5Batch`. Judged marginal for a rationale entry on
  reflection: the source itself is nonsensical (a variable referencing
  itself before it's declared), so this is defensive robustness against
  malformed input, not a translation of a valid cross-engine construct —
  the article format's "explain the creative alternative used" framing
  doesn't fit a case with no valid intent to preserve.
- `count() OVER ()` gains a synthesized `*` on MySQL —
  `test_ir_first_families.py::TestZeroPushPgOnlyShapes` (cited by the
  original batch-7 row; not independently re-located in this pass's time
  budget).
- No-op `OFFSET 0` dropped on T-SQL/MySQL —
  `test_ir_first_families.py::TestZeroPushW2Batch`.
- `PRIMARY KEY CLUSTERED (col ASC)` drops `CLUSTERED`+ordering on
  PostgreSQL — `test_output_gate.py::TestGateEndToEnd`.

**Defects flagged (report-only, not fixed, not added to any gap table).**
None. Every genuine gap found in this pass was a faithful, warning-free
rewrite on inspection — consistent with batches 5b/6b's own finding that
this sweep's scope (documentation coverage) rarely turns up a live defect
as a side effect.
