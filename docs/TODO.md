# Unique — Pending Work

This document tracks **outstanding** work, ordered by priority. Completed work
has been archived in [`docs/DONE.md`](DONE.md) (with the detailed why/how of
each fix); `docs/STATUS.md` summarizes the project state at a higher level.

Last reviewed: 2026-07-08. The functional-equivalence and 2026-07-02
audit-remediation backlogs are complete and archived in [`docs/DONE.md`](DONE.md)
(§18); source-syntax validation across core/API/web/CLI shipped (§34). The
**2026-07-08 follow-up audit** ([`audit/2026-07-08/`](../audit/2026-07-08/))
verified all 14 previous functional bugs fixed and opened the backlog below.

## Legend

- **P1** — high impact, appears frequently in real schemas
- **P2** — medium impact, common but not blocking
- **P3** — lower impact / niche

---

## 1. Oracle procedural output — validity backlog (P1) — ✅ DONE (26 -> 0)

**Complete.** The T-SQL procedures fixture (32 objects) now transpiles to
**fully-valid Oracle** — `test_procedures_fixture_is_valid_live[oracle]` asserts it
(the `xfail` is gone). The Oracle live-validator queries `USER_ERRORS` after each
`CREATE` (Oracle compiles PL/SQL *lazily*, so `CREATE` succeeds even for an invalid
body) and recompiles to settle forward dependencies. Detailed why/how of each fix
is archived in [`docs/DONE.md`](DONE.md); the arc, in brief:

- **Expression/type:** string-`+` -> `||`; subquery / CAST assignments and RETURNs
  are SQL-only in PL/SQL, so via `SELECT … INTO v FROM DUAL` (or a nested block);
  `SELECT TOP (n)` -> `FETCH FIRST`; CLOB/`SQL_VARIANT` -> bounded `VARCHAR2`;
  `TRY_CAST`/`SHA256`/`EXTRACT(EPOCH …)`/`VARCHAR(MAX)`-cast/character-CAST length;
  `DATEDIFF` sub-day + canonical layout; `TIME_STR_TO_TIME` unwrap.
- **Structure (features):** bare result `SELECT` -> `SYS_REFCURSOR` OUT; `EXEC
  sp_executesql` -> `EXECUTE IMMEDIATE … USING`; **table variable -> hoisted GTT**;
  **trigger DECLARE section**; **reassigned IN parameters shadowed with locals**;
  **inline split TVF -> `SYS.ODCIVARCHAR2LIST` function** + `TABLE(fn(…))` callers.
- **Rules:** OUT/IN OUT params take no DEFAULT; procedure/trigger RETURN carries no
  value; no `AS` before a table alias.

## 2. Audit 2026-07-08 follow-ups

Findings from [`audit/2026-07-08/02-new-findings.md`](../audit/2026-07-08/02-new-findings.md)
(reproductions and mechanism analysis there).

### P1 — silent semantic changes (no-silent-loss violations)

- [x] **Residual invalid output ships WITHOUT a warning (P1) — CLOSED at the
      architectural floor (2026-07-17, user declaration at `469917a`).** The
      direction-residue campaign (waves 103–239) took the six-direction residue
      from ~770 invalid-silent statements to **133 pending** (mysql-corpus
      {tsql 20, pg 15, oracle 13}, pg-corpus {tsql 29, mysql 32, oracle 24}),
      validity **98.9–99.8%**, and the pg→pg silent-gap discovery channel from
      **287 to 0** (`scripts/discover_silent_gaps.py`). Every statement now
      transpiles validly or carries a warning/carrier; the remainder is three
      non-wave classes (adversarial pg_regress error-path inputs,
      schema-dependent ambiguity, RETURN QUERY table functions) that need
      schema-aware transpilation — declared out of scope for statement-level
      transpilation. Full per-wave log (mechanisms, measured commit hashes,
      tests) archived in [`docs/DONE.md`](DONE.md) §36; the floor declaration
      and scope decisions are reproduced there verbatim. Standing decisions:
      live validation stays a development-only tool (never CLI/API), and no
      new waves on these corpora without a new corpus or a fidelity target.

### P0 — architecture plan (audit doc 04 — ADOPTED 2026-07-08)

- [x] **M3 final — DONE 2026-07-17 (`86f7c11`): IR-first is the expression
      engine.** The LAST architecture-plan milestone (audit doc-04 P4)
      closed: scalar fragments route through the shared IR pipeline by
      default; the text rewriters serve only IR-declined fragments (parse
      failures, shell-machinery text) — the same primary+fallback shape
      M3a gave embedded DML. `UNIQUE_NO_IR_FIRST` is the kill-switch.
      Arc: probe 126 → 113 → 109 → … → 0-real via ~15 family commits
      (shared func/error/diagnostic tables consumed by BOTH pipelines,
      cursor+FOUND state context, styled CONVERT + TO_DATE/TO_CHAR format
      bridge, trigger-shell guards, comment line→block carrying, national
      literals, Trim positions, nested subqueries, LOB helpers, concat
      classification+flattening) + 23 assertions strengthened to exact IR
      forms at the flip. **Measured (definitive cycle): pg-corpus {tsql
      20, mysql 37, oracle 25}, mysql-corpus {tsql 17, pg 13, oracle 15}
      = TOTAL 127 vs the declared floor 133 (−6); validity 98.7–99.8%;
      discovery pg→pg 0; FE live 16/16.** Full log in
      [`docs/DONE.md`](DONE.md) §39.
- [x] **Zero-reduction campaign (P2) — CLOSED at the floor, residue 133 →
      16 (2026-07-17, batches W1–W10, `34d7338`).** The user-declared floor
      was 133; the M3-final flip measured 127, and this campaign drove it to
      **16** — a further −88% below the declared floor, with **both Oracle
      directions at 100.0% validity**. After the M3-final flip, drove the
      six-direction live syntax residue down with mechanism fixes (not
      waves), each a commit with always-on tests + full gate + live-syntax
      + FE 16/16. Cycles: 127 → 58 → 48 → 40 → 36 → 29 → 25 → 22 → 20 → 19
      → 17 → **16 (z13)**: pg-corpus {tsql 1, mysql 5, oracle **1**},
      mysql-corpus {tsql 4, pg 3, oracle **2**} — **both Oracle directions
      at 100.0% validity**. Discovery pg→pg held 0; overall 99.8–100.0%.
      Highlights: IR-routed trigger predicates (ISNULL), self-join
      `UPDATE…FROM` multi-table (pg + mysql), Oracle refcursor IN OUT /
      named-cursor `=>` / BLOB / unsafe-local rename / self-init drop /
      embedded CREATE INDEX NULLS strip / bool-return wrap, and honest
      carriers (REPLACE, RETURN QUERY, comment-only trigger body,
      data-modifying CTE, whole-row OLD.*/NEW.* trigger, COMMENT ON in body,
      OPEN FOR EXECUTE, set-op ORDER aggregate). Full log:
      [`docs/DONE.md`](DONE.md) §40. **Remaining 16 are the architectural
      floor** — adversarial pg_regress/sqlancer inputs sqlglot cannot parse
      (nested-paren join trees, chained `a=b=c`), a correlated
      outer-aggregate subquery, composite-field access (`(f(x)).field`),
      schema-dependent type inference (COALESCE bigint/char), LATERAL
      column-alias lists, mysql-source structural singletons. Measurement
      gotcha recorded: the pg→oracle sweep hangs at runtime on bare
      `SELECT <dml-fn>()` pg_regress driver calls (not syntax defects).
- [x] **Prune fallback-only text rewriters (P3) — CLOSED BY MEASUREMENT
      2026-07-17:** a coverage run over ALL real material (both corpora,
      the procedures fixtures and the three private fixtures, every
      direction) shows **36 of 37 rewriters still receive fallback
      traffic** — the IR-declined fragments (parse failures, mid-transform
      hybrids) are real and the text fallback is their working surface.
      The single zero-traffic method (`_map_mysql_datefmt_to_oracle`, 8
      lines) is a helper of a live method and reachable by real
      mysql→oracle date formats outside the corpus — deleting it would
      break the fallback with no replacement. Conclusion: nothing is
      safely prunable; the fallback surface stays as-is. (Harness: the
      scratchpad coverage run with COVERAGE_CORE=sysmon; the timed-out
      first attempt without sysmon is the reminder to always use it.)

### P3 — hardening carry-overs (from 2026-07-02, still open)

- [x] **Module growth — DONE 2026-07-17.** All three oversized modules are
      split: `procedural/parser` package (2026-07-10), the transformer's
      `ExpressionRewriter` seam (`transformer/_expr.py`, `997f0e8` —
      base.py 5053 → 3735 lines), and `transpiler.py` → the
      `core/transpiler/` package (`_text_rules.py` + `_core.py` +
      re-exporting `__init__`, `0e6ead0`). Full detail archived in
      [`docs/DONE.md`](DONE.md) §37; the rewriter object is what M3's
      IR-first expressions will eventually replace.
- [x] **tsql→mysql procedural DATEADD nested INTERVAL — FIXED 2026-07-17**
      (same day it was filed): `_mysql_normalize_funcs`'s sqlglot
      round-trip re-emitted a tsql-read `DateAdd` carrying its whole
      `Interval` in the *expression* slot through the mysql generator,
      which invents an implicit DAY unit (`INTERVAL (INTERVAL '-1'
      MONTH) DAY` — invalid MySQL and a silent unit change). The
      normalize walk hoists the interval into the expression/unit
      slots. Test: TestDateAddUnderConvertMySql.

## 3. Test-corpus expansion (P3)

- Corpus wave campaign **COMPLETED and archived** (2026-07-15 →
  2026-07-17, waves 4–95; full per-wave log with measured commit
  hashes in `docs/DONE.md`, section "Wave campaign — corpus
  validity"; waves 96–102 are the M3-prereq/M3b record kept in the
  §2 M3 item). Final standings at `3fdfc88`:
  - pg-source (PostgreSQL regression corpus,
    `fixtures-corpus/pg_corpus_valid.sql`): →T-SQL **163** syntax
    failures (95.0% validity), →MySQL **131** (95.7%), →Oracle **89**
    (97.2%).
  - mysql-source (private local corpus, provenance undocumented by
    policy): →T-SQL **166** (97.2%), →PG **107** (98.2%), →Oracle
    **129** (97.8%).
  - Both residues are at the deep-singles floor (a full measure cycle
    buys ~−1); do not resume waves on these corpora without a new
    corpus or a fidelity target.

## 4. T-SQL keyword coverage

- [x] **`PROC` abbreviation of `PROCEDURE` (P2)** — T-SQL accepts `PROC` in
      `CREATE`/`ALTER`/`DROP`; the abbreviated spelling was mishandled while the
      full one worked (`CREATE PROC`/`ALTER PROC` degraded to an "Unhandled
      CREATE" carrier; `DROP PROC` leaked the T-SQL-only `PROC` keyword into
      PG/Oracle/MySQL output — invalid there). Fixed at three layers: the
      procedural-routing regex (`batch_splitter._PROCEDURAL_PATTERNS["tsql"]`)
      matches `PROC(?:EDURE)?`; the procedural lexer normalizes `PROC` →
      `PROCEDURE` only in the `CREATE`/`ALTER` keyword position (a column/object
      named `proc` stays an identifier); and `converter._normalize_ddl_kind`
      canonicalizes the DROP/CREATE `kind`. Covered by
      `tests/integration/test_tsql_keyword_alias.py`. The other two documented
      T-SQL statement abbreviations already work: `EXEC`≡`EXECUTE` and
      `TRAN`≡`TRANSACTION` on `COMMIT`/`ROLLBACK`/`SAVE`.
- [x] **`CREATE OR ALTER {PROCEDURE|PROC}` (P2)** — the T-SQL 2016+
      `CREATE OR ALTER` form (distinct from `CREATE OR REPLACE`) fell to the DML
      path and degraded to an "Unhandled CREATE PROCEDURE" carrier. Fixed: the
      routing regex accepts `CREATE\s+OR\s+ALTER`, `parser._parse_create`
      consumes the `OR ALTER` prefix like `OR REPLACE` (both set `or_replace`),
      and the T-SQL emitter now honors `or_replace` — so `CREATE OR ALTER`
      round-trips and Oracle/PG `CREATE OR REPLACE` ↔ T-SQL `CREATE OR ALTER`.
      Covered by `tests/integration/test_challenge.py` + `test_procedural.py`.
- [x] **`BEGIN TRAN[SACTION]` (P2)** — a standalone begin-transaction degraded to
      "Unhandled expression type: Transaction". Fixed: the converter passes
      `exp.Transaction` through (kind `BEGIN TRANSACTION`) so sqlglot renders
      T-SQL `BEGIN TRANSACTION` / PG+MySQL `BEGIN`; Oracle (implicit
      transactions) drops it to a documented carrier + warning in
      `emit._emit_passthrough` rather than a bare invalid `BEGIN`.
      `COMMIT`/`ROLLBACK`/`SAVE` already mapped. Covered by
      `tests/integration/test_challenge.py`. (A multi-statement `BEGIN TRAN … `
      `COMMIT` in ONE semicolon-less batch is a separate splitter limitation.)

## 5. Procedural round-trip fidelity (challenge corpus)

New regression corpus at [`tests/fixtures/challenge/`](../../tests/fixtures/challenge/)
— one anonymized script per source engine collecting tricky constructs as they
are found; guarded by `tests/integration/test_challenge.py`. Cases are tagged
`[fixed]` (strictly guarded) or `[open]` (RED backlog). See the
[challenge-corpus skill](../skills/SKILL-challenge-corpus.md) for the red/blue
workflow.

- [ ] **BLUE backlog: 862 open RED findings — SILENT defects only (P1/P2/P3)** —
      a RED batch (2026-07-17/18; start commit `dac260f`) generated valid
      per-engine source, validated each original on a live DB, transpiled to the
      other three engines, and validated/**executed** the output. **Only silent
      problems are recorded — a construct that degrades WITH a warning is a
      documented, acceptable outcome and was excluded** (~335 warned rows
      dropped; the `carrier` kind is intentionally gone). Ledger in
      [`tests/fixtures/challenge/FINDINGS.md`](../../tests/fixtures/challenge/FINDINGS.md),
      which opens with a **prioritized class list**. **1800 silent-defect rows**:
      **1322 invalid-output** (unmapped function/type → the target engine rejects
      it, no warning), **401 functional-equivalence** (runs clean but returns a
      *different result* — executed on both engines: integer division, NULL/
      collation ordering, `LOG` base, `CAST(x AS INT)` round-vs-truncate,
      `ROUND(x,n)` precision + half-even, `LENGTH` bytes-vs-chars, `LEN` trailing
      -space, `GREATEST/LEAST/CONCAT` NULL, Oracle `||`-null / `''`-is-NULL, `TOP
      … WITH TIES`, MySQL `date-date` numeric, `'5'+'5'`, bitwise sign/precedence,
      float precision, decimal scale, CHAR-pad WHERE filtering, int=varchar JOIN
      coercion, UNION/CASE type resolution, TO_CHAR format masks), **75 silent
      clause-drops**
      (FK `ON DELETE/UPDATE`, CHECK, COLLATE, IDENTITY/sequence seed, UNSIGNED,
      window frame, ROLLUP, EXCLUDE, column COMMENT, BIT-width), **2 semantic**.
      Each is a `-- CASE[open]:` in the per-engine scripts. **BLUE** works these
      down within the existing rules/architecture: fix at the AST layer, flip the
      case to `[fixed]` with an assertion, remove it from the ledger. Highest
      value first: the **functional-equivalence** rows (silent wrong results) and
      the **clause-drops** (data integrity).

  - **RC-1b foundation landed (BLUE, Block 1).** Root-cause of the **invalid**
    class (1322 rows): an unmapped scalar function/type shipped verbatim with no
    warning — the target-parse gate missed it because sqlglot parses unknown
    functions leniently across dialects. Fix = an authoritative per-engine
    **built-in catalog** (`unique.core.builtins`, generated by
    `scripts/gen_builtins.py` from live `pg_proc`/`V$SQLFN_METADATA`/
    `mysql.help_topic` + curated T-SQL, ∪ a grammar-level SQL-standard set) plus
    a source-built-in leak scan in `core/output_gate.py`: a call whose emitted
    name is a source built-in but not a target built-in degrades WHOLE to the
    documented carrier + warning; a non-built-in name is a **user object**
    (UDF/proc) and passes through. **56% of the invalid DML rows (728/1280) now
    degrade honestly** with zero suite regressions (`test_unmapped_builtin_gate.py`).
    Remaining scope: (Block 2) the same scan for **procedural** bodies; (RC-1a)
    add real mappings so built-ins with a target form *translate* instead of
    degrading; then RC-2 (func compensations, annotated) and RC-3 (clause-drops).

  - **Block 2 landed (`d24c27c`)** — the scan now covers routine bodies too;
    MySQL catalog completeness fixed (help_topic miscategorises REPLACE/IF/…),
    table-position names (`INSERT INTO line`) excluded.
  - **RC-3 FK/CHECK landed (Block 3).** Inline column-level constraints
    (`c INT REFERENCES p(id) ON DELETE …`, `c INT CHECK (…)`) were dropped by the
    CREATE TABLE converter (it read only NOT NULL/IDENTITY/PK/UNIQUE/DEFAULT) —
    silent loss of referential integrity / validation. Now routed to the
    table-level constraint path and emitted per-target
    (`tests/integration/test_clause_drops.py`). **Still dropped silently (RC-3
    backlog):** column `COLLATE` (collation names differ per engine → needs a
    map or an honest degrade), column `COMMENT` (PG/Oracle need a separate
    `COMMENT ON COLUMN`), `IDENTITY(seed,step)` seed (→ `GENERATED … START WITH`),
    `UNSIGNED` (widened to BIGINT but the ≥0 constraint is lost), window
    `ROWS/RANGE` frame, `WITH ROLLUP`, `EXCLUDE`. Also **Oracle has no
    `ON UPDATE`** FK action — now preserved (was dropped) but ships invalid on
    Oracle; needs a target gate.
  - **RC-2 (func-diffs) — LOG arg order fixed; rest is the delicate floor.**
    The IR is canonical `LOG(base, x)`; T-SQL spells it `LOG(x, base)`, so the
    emitter swaps only when the target is T-SQL (a lossless correctness fix — the
    naive source-keyed transform double-swapped because the parser already
    canonicalises T-SQL's order; sqlglot handles LOG end-to-end, the IR emit path
    did not). `tests/integration/test_log_arg_order.py`. **The remaining func-diff
    classes are the delicate/architectural floor** and need per-column type or
    collation knowledge that is undecidable at statement level: string collation
    (`'Ä'='A'`, case/accent — 94 rows, the largest cluster), integer division
    (`5/2` — needs operand types), `LENGTH` bytes-vs-chars (a semantic judgement —
    forcing `OCTET_LENGTH`/`DATALENGTH` everywhere over-reaches; warn instead),
    NULL-propagation in `GREATEST`/`LEAST`/`CONCAT`, Oracle `''`-is-NULL and
    `||`-null, `CAST` float→int round-vs-truncate. These want a schema-aware /
    warn-on-divergence pass, not a per-spelling rewrite — the user's own caution
    ("RC-2 es delicado"); handling one wrong ships silent bad data.

  - **RC-1a mapping opportunities — systematic 2026-07-18 sweep, all
        LIVE-VERIFIED (value, not just parse). LANDED:**
    - [x] `LAST_DAY(d)` → tsql `EOMONTH(d)`, pg
        `CAST(DATE_TRUNC('month',d) + INTERVAL '1 month' - INTERVAL '1 day' AS DATE)`
        (live: 2020-05-31, leap 2020-02-29).
    - [x] `QUARTER(d)` (mysql) → tsql `DATEPART(QUARTER,d)`, pg `EXTRACT(QUARTER FROM d)`,
        oracle `TO_NUMBER(TO_CHAR(d,'Q'))` (live: 2).
    - [x] `DAYNAME(d)` (mysql) → tsql `DATENAME(WEEKDAY,d)`, oracle `TO_CHAR(d,'fmDay')`,
        pg `TO_CHAR(d,'FMDay')` (live: 'Friday'; locale = session NLS, like collation).
    - [x] `DEGREES`/`RADIANS` → oracle `(x*180/ACOS(-1))` / `(x*ACOS(-1)/180)` (live exact).
    - [x] `RAND()` → oracle `DBMS_RANDOM.VALUE`; `REPEAT(s,n)` → oracle `RPAD(s,LENGTH(s)*n,s)`.
    - [x] `STUFF(s,start,len,new)` (tsql) → pg `OVERLAY(...)`, mysql `INSERT(...)`,
        oracle `SUBSTR(s,1,start-1)||new||SUBSTR(s,start+len)` (Oracle has no OVERLAY —
        caught live; live: 'aXYZef').
    - [x] `MEDIAN(x)` (oracle) → pg `PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY x)`
        (live: 2.5); `JSON_ARRAYAGG(x)` (mysql) → pg `JSON_AGG(x)` (live: [1,2]).
    - [x] `ELT(n,…)`/`FIELD(v,…)` (mysql) → portable CASE chains (live: ELT
        out-of-range→NULL, FIELD not-found→0).
    - [x] `ADD_MONTHS(d,n)` (oracle) — the sticky-last-day CASE lands after all:
        `CASE WHEN d = lastday(d) THEN lastday(d+n·mo) ELSE d+n·mo END`, using each
        target's last-day primitive (mysql `LAST_DAY`, tsql `EOMONTH`, pg
        DATE_TRUNC). Live-verified vs Oracle on all three targets across the sticky
        Feb-29→Mar-31 edge, clamps, negative n, leap years — all exact.
    - **Still open (mappable but needs more than a one-liner):** `MONTHNAME`
      (sqlglot decomposes it to TIME_TO_STR — handle upstream), `NEXT_DAY`,
      `UNIX_TIMESTAMP`/`FROM_UNIXTIME` (epoch), `WEEK` (mode),
      `MEDIAN`→tsql (window-only form).
    - **Floor after LIVE checks proved a value divergence:** `CBRT`
      (`POWER(ABS,1/3)` is `2.9999…` not `3` — float precision).
    - **Confirmed floor (no faithful equivalent — keep degrading honestly):**
      `TRANSLATE`→mysql/tsql (char map+delete), `INITCAP`→mysql/tsql, `SOUNDEX`→pg
      (needs fuzzystrmatch), `QUOTENAME`→others, `FORMAT` (locale), `SUBSTRING_INDEX`,
      `HEX`/`BIN`/`OCT`/`CONV`/`CRC32` (base conv), `WEEKDAY` (DATEFIRST-dependent),
      `MONTHS_BETWEEN`→mysql/pg (fractional).

- [x] **Duplicate `SET NOCOUNT ON` on `oracle`/`pg`/`mysql` → T-SQL (P2)** — the
      T-SQL procedure emitter injects `SET NOCOUNT ON` as a best-practice
      default, but did so even when the body already opened with one (an
      explicit author directive, or the restored `/* UNIQUE: SET NOCOUNT ON … */`
      round-trip carrier) — emitting it twice, and forcing `ON` in front of an
      explicit `SET NOCOUNT OFF`. Fixed: `emitter.base._emit_procedure_body`
      suppresses the injection when the first executable statement is already a
      `SET NOCOUNT` directive (`_body_manages_nocount`). Removed a dead,
      identically-buggy `_emit_tsql_procedure_body` duplicate. Covered by
      `tests/integration/test_tsql_nocount.py`.
- [x] **Oracle self-qualified parameter `<routine>.<param>` mangled → T-SQL/MySQL
      (P2)** — Oracle lets a body reference a formal parameter as
      `usp_get.topfilas`; the parameter rename treated any qualified name as a
      column, so it was left un-renamed (`WHERE n = usp_get.topfilas`) and, in a
      `FETCH FIRST` count, sqlglot could not parse it and dropped `.topfilas`
      (`FETCH FIRST usp_get`). Fixed: `transformer.base._strip_self_qualified_params`
      drops the `<routine>.` qualifier before the rename when the qualifier is
      the routine's own name and the suffix is a known parameter (a real
      table/alias of the same name is untouched). Covered by
      `tests/integration/test_challenge.py`.

## 6. Packaging (P3)

- [ ] **PyPI publication** — deferred until the tool has been used in real
      projects for a few months and proven stable. Not before then.

---

## Continuously tracked (not a discrete backlog)

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
