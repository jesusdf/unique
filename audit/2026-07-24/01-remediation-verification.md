# 01 — Remediation verification (2026-07-08 findings vs v0.30.0)

Every finding of the 2026-07-08 audit re-checked against **v0.30.0**
(HEAD `69a71cd`, 2026-07-24). Probes were re-run through the public
`Transpiler.transpile` API (now `unique.core.transpiler` — a package; result
field is `unsupported`, previously `unsupported_features`) with the original
reproduction inputs; ✅ means the originally reported defect no longer
reproduces, ➖ means partially remediated, ❌ still open.

Severity legend as before: **S1** invalid/lost/semantically changed output
with no warning; **S2** degraded meaning or a guarantee that doesn't hold;
**S3** valid but suboptimal / cosmetic / drift.

Suite size at verification time: **3785 collected tests** (was 1774 at
v0.22.3). Identity-mutation gate re-run locally: **1710/2585 integration
tests detect a no-op transpiler (66%)**, floor 0.45.

## New findings N1–N9 (doc 02)

| Finding | Status | Evidence (v0.30.0) |
|---|---|---|
| N1 (S1) unbracketed real-data `IF [NOT] EXISTS` guard dropped silently | ✅ | The `_TSQL_BEGIN_BLOCK_RE` conjunct is gone: any non-catalog guard routes to the procedural engine (`src/unique/core/batch_splitter.py:337-338`). Probe: `IF NOT EXISTS (SELECT 1 FROM cfg WHERE k='x') INSERT …` → Oracle `BEGIN FOR unique_guard IN (SELECT 1 FROM DUAL WHERE NOT EXISTS(…)) LOOP INSERT …` ; PostgreSQL `DO $$ BEGIN IF NOT EXISTS (…) THEN INSERT …` ; MySQL degrades to a carrier comment **with** a warning ("anonymous PL/SQL block with control flow has no top-level mysql equivalent"). No silent loss anywhere. *Residue (S3, unchanged):* `IF 1=1 INSERT …` (non-EXISTS, unbracketed) still degrades to a warned `Unhandled expression type: IfBlock` carrier |
| N2 (S1) PG → T-SQL temp-table rename not script-wide | ✅ | `SELECT * INTO TEMPORARY tmp; SELECT a FROM tmp; DROP TABLE tmp` → `INTO #tmp` / `FROM #tmp` / `DROP TABLE IF EXISTS #tmp` — the rename is propagated to every later reference |
| N3 (S2) validation false negatives → silent garbage | ✅ | `validate_source("banana banana","tsql")` → `not a valid SQL statement`; `validate_source("CREATE TALBE t (id INT)","tsql")` → `unrecognized CREATE object kind 'TALBE'`. CLI and API both gate on `validate_source` (`src/unique/cli/main.py:85,141`, `src/unique/api/app.py:285`), so garbage no longer reaches the transpiler through any product surface. *Residue (minor):* a **direct library call** `transpile("banana banana", …)` still emits `banana AS banana;` with zero warnings — the recommended transpiler-level "batch survived only as an expression fragment" warning was not implemented |
| N4 (S3) STATUS FE-claim / catalog guard doesn't round-trip | ➖ | (a) **Fixed**: `docs/STATUS.md:146-148` now says the guard round-trip is covered by unit tests "(`test_dual_guard.py` — *not* by the FE harness; see its coverage-matrix)". (b) **Still open**: the self-emitted Oracle catalog guard (`user_objects` probe) still degrades to a warned carrier on the way back to T-SQL (`Oracle anonymous block querying the data dictionary (USER_*/ALL_* views) has no tsql equivalent; preserved as a comment`) — A→B→A of a guarded CREATE still loses the executable statement (warned + registered, so the invariant holds, but the round-trip recommendation was not adopted) |
| N5 (S3) false-positive FOR-loop warning on successful guard round-trip | ✅ | Data guard `tsql → oracle → tsql` round-trips to `IF (NOT EXISTS …) BEGIN INSERT … END` with **warnings: [] / unsupported: []** — the "FOR loop has no direct T-SQL equivalent" cry-wolf warning is gone |
| N6 (S3) `/validate` & `/detect` size caps | ✅ | `ValidateRequest.sql` and `DetectRequest.sql` both carry `max_length=MAX_SQL_BYTES` (`src/unique/api/app.py:222` and `:384`) |
| N7 (S3) `Content-Disposition` unsanitized filename | ✅ | Stem sanitized to `[\w.\- ]` before header interpolation, comment cites N7 (`src/unique/api/app.py:469-478`) |
| N8 (S3) near-duplicate `unsupported` entries | ➖ | `CREATE SCHEMA → oracle` now registers **one** entry (`CREATE SCHEMA sales has no Oracle equivalent`). `EXEC sp_rename → oracle` still registers **two** near-duplicates (`System procedure sp_rename has no equivalent` + the carrier text) — dedup landed for one construct, not the other |
| N9 (S3) docs/skills drift | ✅ | `skills/SKILL-project-overview.md:35` says **Python 3.13**; its layout sketch shows `converter/` as a package and lists `mappings.py`/`validation.py` (`:64-71`). `README.md:57` now notes "image published on release tags" beside the `jesusdf/unique:latest` example. No "Most recently"-stutter remains in `docs/STATUS.md` |

## Recommended priorities (doc README)

| Priority | Status |
|---|---|
| P1 — unbracketed real-data guard drop | ✅ fixed (N1 above; the fix is the one the audit proposed — drop the `BEGIN` conjunct in the classifier) |
| P1 — PG→T-SQL temp-table rename script-wide | ✅ fixed (N2 above) |
| P2 — extend garbage detector in `validate_source` | ✅ fixed (N3 above; the transpiler-level bare-expression warning remains unimplemented, but every product surface now refuses the input) |
| P2 — STATUS/coverage-matrix reconciliation, FOR-warning suppression, skill Python version | ✅ all three fixed (N4a, N5, N9) |
| P3 — carry-overs | see table below: 4 of 7 fixed, 1 partial, 2 still open |

## P3 carry-overs and improvement opportunities

| Item | Status | Evidence |
|---|---|---|
| CI: fail when engines silently skip | ✅ | `ci.yaml:312` "Gate — all four engines must be reachable": after the (still `continue-on-error`) wait steps, a dedicated step connects to PostgreSQL, MySQL, Oracle and SQL Server and **fails the job** if any is unreachable; the comment cites "audit P3". The wait-steps' leniency is now log-cosmetic only |
| Docker base image digest pin (+ constraints) | ✅ | `Dockerfile:8` and `:18` — `FROM python@sha256:eb43ff12…` (both stages), comment cites P3; a repo-root `constraints.txt` pins dependencies and the image installs with `pip install -c /tmp/constraints.txt` (`Dockerfile:29-31`). Improvement 4 fully adopted |
| Module sizes (`procedural/parser.py` 2886, `transformer/base.py` 2813, `transpiler.py` 1713) | ➖ | Two of the three were split into packages: `procedural/parser/` (`_base.py` 2358 + `_plsql.py` 1718 + `_tsql.py` 710) and `core/transpiler/` (`_core.py` 1804 + `_text_rules.py` 730). But `procedural/transformer/base.py` **grew 2813 → 4352**, and the new largest file is `converter/emit.py` at **9992 lines** (the audited converter package's largest file was 1873) — the size problem moved rather than shrank |
| Identity-mutation floor vs measured | ➖ | Floor raised twice as recommended: 0.33 → 0.40 (2026-07-10) → **0.45** (2026-07-11), history documented in `scripts/identity_mutation_check.py:20-28`. Local re-run measures **66%** (1710/2585) — assertion quality rose dramatically (38% → 66%), but the floor again trails the measured rate by ~21 points; next ratchet is due |
| Promote FE fingerprint to `unique verify` CLI | ❌ | `src/unique/cli/main.py` still exposes only `transpile`, `validate`, `list-dialects` — no `verify` subcommand; the FE machinery remains CI-only |
| CI duplicated log-capture shell blocks | ❌ | The syntax-live step (`ci.yaml:381-403`) and the FE step (`:429-447`) still carry two near-identical capture/`GITHUB_STEP_SUMMARY`/`::error::` shell blocks — cosmetic, unchanged |
| Report decode encoding in a response header (A5 residue / improvement 5) | ✅ | `X-Unique-Decoded-As` header on `/transpile/file` (`src/unique/api/app.py:482`), comment cites the A5 residue |
| Improvement 1 — raise floor, convert `test_cross_dialect`/`test_comment_preservation` survivors | ➖ | Same as the floor row: measured kill rate 38% → 66% and floor 0.33 → 0.45, so the conversion work clearly happened at scale; the floor still lags the measurement |
| Improvement 2 — CI engine-coverage assertion | ✅ | see the engine-gate row |
| Improvement 3 — module-size work | ➖ | see the module-size row |

## Private-fixture sweep defect classes (doc 03)

Verified with anonymized re-creations of each class (never the private files),
per class through the public API. The classes were also the raw material of the
challenge-corpus campaign (862 findings → 0 `[open]` at v0.30.0), which is
consistent with what the probes show.

| Class | Status | Evidence (v0.30.0) |
|---|---|---|
| A1 (S1) leading comment kills a guard | ✅ | `/* header */ IF OBJECT_ID(…) IS NOT NULL DROP FUNCTION …` → comment preserved + Oracle `EXECUTE IMMEDIATE 'DROP FUNCTION …'` block / PG & MySQL `DROP FUNCTION IF EXISTS` — nothing commented out |
| A2 (S1) `BEGIN…END`-wrapped guards commented out | ✅ | `IF OBJECT_ID('t1') IS NOT NULL BEGIN DROP TABLE t1 END` → Oracle exception-guarded `EXECUTE IMMEDIATE`, PG `DROP TABLE IF EXISTS t1` |
| A3 (S1) leading comment suppresses Oracle `/` | ✅ | comment + data-guard + following batch → the anonymous block **is** followed by `/`, and the next batch (`SELECT 1 FROM DUAL;`) emits separately |
| A4 (S1) `NEWID()` in guard body → `UUID()` on Oracle | ✅ | now `SYS_GUID()` |
| A5 (S2) catalog CREATE-guards lose idempotency on PG/MySQL | ✅ | `IF NOT EXISTS (sys.objects…) BEGIN CREATE TABLE … END` → `CREATE TABLE IF NOT EXISTS …` on both |
| B1 (S1) `PRIMARY KEY CLUSTERED (col ASC)` | ✅ | → `CONSTRAINT pk_t1 PRIMARY KEY (id)` on PG and Oracle — no phantom `CLUSTERED` constraint, no `ASC NULLS FIRST` |
| B2 (S1) `DROP INDEX` untranslated | ✅ | `DROP INDEX t1.ix_a` → PG `DROP INDEX IF EXISTS ix_a`, MySQL `DROP INDEX ix_a ON t1` (table kept); the `… ON tbl` source form keeps `ON t1` |
| B3 (S1) named DEFAULT constraint → MySQL | ✅ | `ADD COLUMN c1 INT NOT NULL DEFAULT 0` + warning "named DEFAULT constraint df_c1 dropped" |
| B4 (S3) bare `RETURN` eats the next-line comment | ❌ | Still reproduces: the comment is consumed as the RETURN "value" and re-emitted inside a false `discarded procedure RETURN value (/* explanatory comment */)` warning attached to `RETURN;` — the comment is displaced (survives only inside the warning text) and the warning still cries wolf |
| C1 (S1) mid-body `DECLARE` not hoisted | ✅ | Scalar mid-body declarations hoisted to the declaration section on all three targets; MySQL correctly uses `DECLARE … DEFAULT` + `SET`, Oracle/PG get plain declarations + assignments |
| C2 (S1) `BEGIN TRY/CATCH` reaches MySQL raw | ✅ | → `DECLARE EXIT HANDLER FOR SQLEXCEPTION` block; a shape using `ERROR_MESSAGE()` (no MySQL form) degrades to a **warned** carrier via the output validity gate — never raw, never silent |
| C3 (S1) `WHILE` PL/SQL-style in MySQL | ✅ | `WHILE v_i < 3 DO … END WHILE` |
| C4 (S1) cursor options spill (`LOCAL FAST_FORWARD`) | ✅ | options stripped cleanly; `-- DEALLOCATE not needed in <target>` comment; no floating fragment |
| C5 (S1) named-argument `CALL` → MySQL | ✅ | `my_proc(p_a => 1, p_b => 'x')` → `CALL my_proc(1, 'x')` + warning "MySQL CALL has no named arguments; passed positionally" |
| D1 (S1) `EXEC proc` → `EXEC AS` / bare `EXEC` on PG | ✅ | Oracle `EXECUTE my_proc` → T-SQL `EXEC my_proc;` (no `AS`), PG `CALL my_proc();` |
| D2 (S1) top-level `DECLARE…BEGIN…END` keeps PL/SQL skeleton in T-SQL | ✅ | flattened to `DECLARE @n DECIMAL = 0; SELECT @n = COUNT(*) …; IF @n = 0 BEGIN INSERT … END` |
| D3 (S1, ~6,000×) INSERT-guard `FROM DUAL` kept | ✅ | `INSERT … SELECT 1,'x' FROM DUAL WHERE NOT EXISTS (…)` → `FROM DUAL` dropped on PG and T-SQL |
| D4 (S1, ~100×) `ROWNUM` in procedural embedded DML | ➖ | No longer silent-invalid: the output validity gate catches the leftover and degrades the whole routine to a **warned** carrier ("source-dialect leftovers: ROWNUM … original oracle batch preserved") on PG and MySQL. The invariant is restored, but the construct is still not *translated* (`LIMIT 1` inside the embedded `SELECT INTO` would be) — this is the "SQL-embedded-as-text vs IR" front documented in `docs/TODO.md §5` |
| D5 (S1) `RENAME COLUMN` passthrough to T-SQL | ✅ | → `EXEC sp_rename 't1.a', 'b', 'COLUMN'` |
| D6 (S1) `IF UPDATING` trigger predicates passthrough | ✅ | → `IF (EXISTS (SELECT 1 FROM inserted) AND EXISTS (SELECT 1 FROM deleted))` inside a `CREATE TRIGGER … AFTER INSERT, UPDATE` |
| D7 (S1) `TRUNC(SYSDATE)` → nonexistent `DATE_TRUNC` | ✅ | → `CAST(GETDATE() AS DATE)` (the version-portable form the audit asked for) |
| D8 (S1, silent corruption) `MAX(NVL(n,0)) + 1` loses tokens / `+`→`\|\|` | ✅ | T-SQL `SELECT @n = MAX(COALESCE(n, 0)) + 1 FROM t1 WHERE a = 1` and PG `SELECT MAX(COALESCE(n, 0)) + 1 INTO v_n …` — arguments, parens and the numeric `+` all intact |
| D9 (S1) split lowercase routine header desyncs the parser | ✅ | `create or replace\nPROCEDURE p6` + codegen comment block parses as one routine; declarations (incl. `CURSOR`, `%TYPE`) land in the T-SQL body correctly, `%TYPE` gets a warned carrier type |
| D10 (S2) `DBMS_SCHEDULER.CREATE_JOB` → raw `CALL` on PG | ✅ | → warned carrier ("Oracle package call DBMS_SCHEDULER.CREATE_JOB has no postgresql equivalent") + `unsupported` entry |
| E1 test-harness MySQL splitter splits inside strings | ✅ | `tests/helpers/live_validation.py:357-364` — `_split_mysql_statements` delegates to the shared string/comment-aware `split_statements`, docstring cites "audit 2026-07-08, E1" |

The doc-03 headline invalid-rates (29% of Oracle→T-SQL batches, 43.6% of
Oracle→PG statements on the 13 MB private dump) were **not re-measured** in
this session (no live-engine sweep was run); however every defect class that
composed them (D1–D10 plus A/B/C) now probes fixed or cleanly warned, and the
intervening challenge-corpus campaign (862 RED findings driven to
0 `[open]` / 694 `[fixed]` / 168 `[limit]`) covered these classes at scale.

## Scorecard

| Group | ✅ fixed | ➖ partial | ❌ open |
|---|---|---|---|
| New findings N1–N9 | 7 | 2 (N4, N8) | 0 |
| P1/P2 priorities | 4/4 | — | — |
| P3 carry-overs + improvements (7 distinct items) | 3 (engine gate, Docker pin+constraints, encoding header) | 2 (module sizes, mutation floor) | 2 (`unique verify` CLI, CI log duplication) |
| Sweep classes (25 probed) | 23 | 1 (D4) | 1 (B4) |

**Still open, with severity:** N4b catalog-guard round-trip degrades to a
warned carrier (S3); N8 `sp_rename` double `unsupported` entry (S3); B4 bare
`RETURN` comment mis-attachment + false warning (S3); D4 embedded-DML `ROWNUM`
degrades instead of translating (S2→warned, feature gap); module sizes
(`converter/emit.py` 9992, `procedural/transformer/base.py` 4352); mutation
floor 0.45 vs measured 0.66; no `unique verify` CLI; CI log-capture
duplication (S3). **No S1 (silent-loss) finding from the 2026-07-08 audit
still reproduces.**
