# Unique — Pending Work

This document tracks **outstanding** work only, ordered by priority. Completed
backlog sections move to [`docs/MILESTONES.md`](MILESTONES.md) (closing
summaries) with the detailed why/how of each fix archived in
[`docs/DONE.md`](DONE.md); `docs/STATUS.md` summarizes the project state at a
higher level.

Last reviewed: 2026-07-30.

## Legend

- **P1** — high impact, appears frequently in real schemas
- **P2** — medium impact, common but not blocking
- **P3** — lower impact / niche

---

## Discrete backlog

*Everything approved on 2026-07-30 is executed — campaign (MILESTONES), B29–B33, T8, F1/F2, Q2 (DONE §48–49 + milestones). The 2026-07-24 audit backlog, the findings it surfaced, and the B28 features
are ALL closed — see [`docs/MILESTONES.md`](MILESTONES.md) and
[`docs/DONE.md`](DONE.md) §44–§47. Both maintainer decisions are resolved:
`or_replace` on views kept and documented (2026-07-29, DONE §46); the sqlglot
CASCADED-hang closed by the 30.14.0 upgrade — fixed upstream (2026-07-30,
DONE §47).*

### Q1 — oracle/mysql-source procedural degrades — TRIAGED, briefs ready (P2)

*Triage report: [`audit/2026-07-30-q1-triage.md`](../audit/2026-07-30-q1-triage.md).
Re-measured 2026-07-31 at HEAD `7bffad0` post-B34/B35/B36/B37: NEW-marker
degrades are down to **7/32 oracle→pg** (from 28) and **21/31 mysql→pg**
(mysql now dominated by warned degrades of larger standing fronts: the
embedded-DML raw-sqlglot fallback [~10 routines, UNIQUE-1231 "Embedded DML
not modeled by the IR converter"] and sp_executesql-derived dynamic SQL via
`@_stmt` user variables [4 routines] — neither is a Q1 brief; both belong to
the "SQL-embedded-as-text vs IR" / dynamic-SQL fronts). Remaining briefs by
routines-unblocked and severity:*

- ~~B34~~ — DONE 2026-07-31 (`2067942`): comment spans scrubbed as trivia in
  the MySQL `@var`/`@@sysvar` gates; the 11 false-positive routines cleared.
- ~~B35~~ — DONE 2026-07-31 (`8f1f8a4`): `_split_mysql` balances `CASE…END`
  so a DELIMITER-less routine body stays whole; corruption gone.
- ~~B36~~ — DONE 2026-07-31 (3 of 4 causes): oracle→pg 1151 count 16 → 2.
  SYS_REFCURSOR type map, FROM-DUAL tail strip in SELECT INTO,
  NUMTODSINTERVAL/NUMTOYMINTERVAL → PG interval (both pipelines; 3 challenge
  cases lifted to faithful). Cause 3 became B37b below.
- ~~B37b~~ — DONE 2026-07-31: hoist made spelling-general (`SQL%ROWCOUNT` /
  `@@ROWCOUNT`→`ROW_COUNT()` map / MySQL `ROW_COUNT()` all converge on the
  one B37 hoist; `AlterProcedureStatement` wired in — the tsql stub pattern
  lands bodies there). mysql→pg 1151-rowcount routines 8→0; the tsql→pg
  bare-`ROW_COUNT` silent-invalid is gone (fixture regenerated, live-run on
  pg). mysql-source hoists warn the changed-vs-matched divergence (reuses
  the base.py UNIQUE-1192 rationale). `test_rowcount_hoist_b37b.py`.
- ~~B36b~~ — DONE 2026-07-31: `UNIX_TIMESTAMP`→`EXTRACT(EPOCH …)` (niladic
  FLOOR-wrapped), `RAWTOHEX`→`UPPER(ENCODE(…,'hex'))` type-aware (RAW/BLOB
  columns direct via the `COLUMN_TYPES` harvest + new `CURRENT_SELECT_TABLE`
  scoping; character via `CONVERT_TO`; unknown → honest 1151 degrade),
  `STANDARD_HASH` MD5/SHA256/384/512 byte-identical live; SHA1 (the default)
  = honest degrade, new `UNIQUE-1235` + 03-unsupported row. func2/func4
  faithful. Ratchet kept green by extracting table-ref/TABLESAMPLE emission
  from emit.py (3646→3414) into emit_relations.py.
- ~~B37~~ — DONE 2026-07-31: expression-position hoist with honest re-evaluated-condition degrade; corpus 1033 count 8 → 0.
- ~~B38~~ — DONE 2026-07-31: `_peel_leading_statements` in `_core.py` splits a
  folded `<companion DDL> + <routine>` procedural batch — leading statements
  go through the DML/DDL pipeline (with their own validity gate), the routine
  parses alone. proc_2/7/8/9 oracle→pg: 1170 gone, GTT + full plpgsql emitted,
  all four execute on real PG; mysql-source same-shape fixed too (compiles on
  real Oracle). tsql needs no peel (GO separates). The `_split_generic`
  CASE-depth flag was REFUTED: no such function; `_split_oracle`'s
  `begin_depth` is dead (flush only on `/`), `_split_postgresql` tracks only
  dollar-quotes — immune. `test_procedural_leading_ddl.py`.
- **B44** (P3, found during B38) — `_split_oracle`'s `plsql_start.search`
  matches "CREATE PROCEDURE" inside a *comment* (the codegen line
  `-- EXECUTE([CREATE PROCEDURE …])`), setting `in_plsql` early — that's what
  folds the GTT into the routine batch in the first place. Latent guardrail-3
  (comments are trivia) wrinkle; harmless post-B38 (the peel undoes it) but
  the splitter should not read comment text.
- ~~B39~~ — DONE 2026-07-31: parse/transform warnings ship `code=None` and the
  existing carrier reconciliation backfills the specific code (exact-literal
  match for the parse-fallback warning via `PARSE_FALLBACK_WARNING`); a new
  per-batch fallback keeps 1230/1231 for genuinely generic warnings. Sweep:
  mysql 1231 20→16 (4 → correct 1171), oracle 1230 4→0 (→ 1170). SQL output
  byte-identical. `tests/integration/test_procedural_warning_codes.py`.
- **B40** (P3, found during B39) — the "no warning covers this carrier →
  synthesize a duplicate" reconciliation path emits a second
  `lossy_conversion` warning alongside a correctly-coded parse warning for
  the same carrier (same code twice, cosmetic duplication) — a
  `_warning_covers` shingle-matching limitation, pre-existing.
- ~~B41~~ — DONE 2026-07-31: SIGNAL/RESIGNAL parsed into the existing
  `RaiseErrorStatement` IR (`_parse_mysql_signal`, _plsql.py); MESSAGE_TEXT +
  MYSQL_ERRNO survive, SQLSTATE carried in the previously-unused `state`
  field (PG `USING ERRCODE`, MySQL round-trips it). Live-verified on pg
  (45000/'not one row'), oracle (ORA-20001), mysql (errno 1644). RESIGNAL →
  bare RAISE;/THROW;. `test_procedural.py::TestMySQLSignalSource` (10).
  `DECLARE … CONDITION` still parse-degrades whole+warned (honest,
  pre-existing).
- **B48** (P3, found during D1-W9, live-probed) — `_gate_column_alias_ref`
  degrades the derived-table column-alias list (`(SELECT …) AS xx(c1,c2)`)
  for MySQL claiming "no spelling" — but live MySQL 8 accepts that exact
  syntax with correct results; the degrade is only genuine for Oracle
  (ORA-03048, live-confirmed). Un-gate the mysql target (warned degrade →
  faithful passthrough); docs already note the discrepancy.
- **B47** (P2, found during D1-W4, live-probed; **maintainer decision**) —
  Oracle bare `NUMBER` → `BIGINT` promotion is **unconditional** (`convert.py
  _convert_create_table` ~2428; the PK/identity logic later in the function is
  never consulted): a non-key fractional column (`discount_pct NUMBER`)
  silently becomes `BIGINT` — truncation risk, no warning. Faithful map would
  be PG `NUMERIC` (arbitrary precision) or a role-aware promotion (id-like →
  BIGINT); either changes a long-pinned mapping
  (`TestOracleBareNumberToInteger`) and the shipped fixtures → needs the
  maintainer's call before a fix-brief. Documented with a Warning callout in
  `docs/rationale/ddl.md` meanwhile.
- ~~B46~~ — DONE 2026-07-31: `_parse_expression_until_semicolon` treated a
  DML verb as a boundary only at line start; boundary now unconditional for
  T-SQL source (matches the `_DECLARE_DML_BOUNDARY` precedent), with a
  `FOR`-preceded exception for the cursor-for-query idiom (caught by a real
  regression in the neighbor sweep). `TestReturnValueBoundary` + the
  strengthened original assertion.
- ~~B45~~ — DONE 2026-07-31: `_is_native_bool_type` per-target hook +
  `_bool_vars` tracking keeps `TRUE`/`FALSE` for Oracle native-BOOLEAN
  declares/params/assignments/comparisons/RETURN (`BOOLEAN_VARIABLES`
  ContextVar for the shared comparison emitter); mysql-source still folds
  (BOOLEAN→NUMBER(1), pinned). Live: pre-fix PLS-00382 INVALID → post-fix
  VALID. `TestOracleNativeBooleanVars` + live test.
- **B42** (P3, verified pre-existing) — re-rendered `$$` splits into `$ $`
  inside *commented* degraded-routine carriers (4 occurrences in a fresh
  tsql→pg fixture regeneration); cosmetic, but it keeps the generated
  fixture perpetually dirty vs regeneration.
- **B43** (P3, found during B37b) — mysql→tsql/oracle `ROW_COUNT()` inside
  an IF condition still degrades whole with warned UNIQUE-1151 (the
  `_ROWCOUNT_FN_EXPR` inline substitution isn't applied to IF-condition
  RawSQL on those targets); warned/honest, coverage follow-up.

---

### D1 — rationale wave from the docs-gap sweep (P2; feeds A10's "docs finished" gate)

*Source: [`audit/2026-07-31-docs-gap-sweep.md`](../audit/2026-07-31-docs-gap-sweep.md)
— 179 raw gaps deduplicated into 18 mechanism clusters, 10 HIGH. Work as
themed worker waves (the R1/R2 method: every claim sourced from the pinning
test, live-probe uncertain bindings): (1) boolean/predicate duality — the
most pervasive; (2) a NEW triggers page; (3) loop/cursor desugaring;
(4) schema-state coercion; (5) DDL guards; then the rest. Includes the
flagged ADD_MONTHS doc CORRECTION. Residual recall debt: test_pg_source_wave1.py
was only keyword-swept (32/261 classes) — one follow-up pass there.*

### A10 — functional-equivalence coverage (P2) — MEASURED 2026-07-31, implementation pending

*Audit report: [`audit/2026-07-31-a10-fe-coverage.md`](../audit/2026-07-31-a10-fe-coverage.md).
Suspicion CONFIRMED: 691/960 challenge cases are FE-comparable, only 21
enrolled. Live sweep of the 501 self-contained `[fixed]` cases: 669 warned
pairs correctly excluded, 748 clean matches, **86 unwarned problem pairs**
(66 wrong-value DIFFs + 20 runtime EXEC-FAILs) — taxonomy T1 (comparator
normalization) / T2 (precision policy) / T3 (documented-inherent, missing
warning) / T4 (real defects, ~25-30 pairs, named in the report).*

- **A10-H** — auto-enrollment harness: nightly test derives the enrolled set
  mechanically (`[fixed]` + comparable + self-contained − a named exclusions
  ledger, one reason per line); warned pairs skip at transpile time;
  comparator upgrades (datetime/string, interval, JSON canonicalization —
  kills T1); monotonic-downward floors on the ledger size and the
  unenrolled-comparable count.
- **A10-T2 (maintainer decision)** — precision policy: numeric-tolerance
  comparison vs. warning on precision-changing conversions (the historical
  "same value + precision diff = acceptable" rule is nowhere encoded).
- **A10-T4** — BLUE triage of the ~25-30 real-defect pairs (list in the
  report §T4: broken CAST emission on tsql/oracle, unnamed derived columns,
  string+INTERVAL arithmetic, INSERT()/LEFT()/REPEAT() float/OOB semantics,
  TO_CHAR mask fidelity, …). Ready-made findings, cases already in corpus.
  PLUS two live-verified additions from D1-W8 (documented as Warning
  callouts in `strings-collation.md`): STUFF/OVERLAY→oracle/pg lack the
  out-of-range-start guard the mysql→tsql path has (pg raises at runtime,
  unwarned — same family as `my-insert-oob`); mysql `REPLACE` with a
  NON-literal NULL arg → oracle returns `'abc'` where MySQL yields NULL
  (the literal-only NULL check needs the CASE-guard fallback CONCAT got).
- **A10-P** — procedures corpus live-COMPARE (4-dialect same-routine
  fixtures: call with fixed inputs, compare effects). Needs its own design;
  highest-value remaining gap.
- The 29 comparable-but-needs-tables cases enroll later via the `FuncCase`
  probe pattern.

## Continuously tracked (not a discrete backlog)

- Challenge corpus (`tests/fixtures/challenge/`) remains the live intake for
  new RED findings — new batches follow the class/points rules in
  [`skills/SKILL-challenge-corpus.md`](../skills/SKILL-challenge-corpus.md)
  and are scored by `scripts/challenge_stats.py`.
- The first nightly runs at this HEAD will demand mutation-floor raises
  (`mutation.yml` self-ratcheting stale check) — apply them with the real
  full-run numbers.
- Oracle-source Tier-1 promotion still wants a second real corpus
  (`docs/STATUS.md` direction tiers).

---

## Known limitations to keep documented (not bugs)

These have no faithful cross-engine equivalent and are intentionally emitted as
comments/warnings (see `docs/03-unsupported.md`):

- SQL Server system procedures (`sp_addextendedproperty`, `sp_rename`, …).
- SQL*Plus session directives (`SET FEEDBACK`, etc.) and `rem`/`prompt`
  (preserved as comments).
- `%TYPE`/`%ROWTYPE` without `--db-url` (emitted as a carrier type with the
  original preserved in a `/* UNIQUE: … */` comment, plus a warning). The
  round-trip **restores the original** on a transpilation back to a supporting
  engine — verified for `%TYPE` via the procedural path and for physical index
  clauses via the DML path (`%TYPE` is PL/SQL-only, so it never appears in a
  DML/DDL statement).
