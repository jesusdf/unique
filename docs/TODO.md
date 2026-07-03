# Unique — Pending Work

This document tracks **outstanding** work, ordered by priority. Completed work
has been archived in [`docs/DONE.md`](DONE.md) (with the detailed why/how of
each fix); `docs/STATUS.md` summarizes the project state at a higher level.

Last reviewed: 2026-06-25.

## Legend

- **P1** — high impact, appears frequently in real schemas
- **P2** — medium impact, common but not blocking
- **P3** — lower impact / niche

---

## 1. Functional-equivalence test database (P1)

**Goal:** move from *syntactic* validation (the `syntax-live` job confirms a
transpiled script *compiles* on the target engine) to *functional* equivalence
— confirm a migrated script **behaves identically**: same final table state
after running DDL + seed data + mutations (direct DML, updates on a
triggered table, inserts/updates from a stored procedure, …).

Design, schema, scenario and expected-state spec live in their own folder:
**[`tests/functional_equivalence/`](../tests/functional_equivalence/)** — see its
`README.md` for the full architecture and rationale. Build it *after* the items
below are closed.

High-level plan (details in that folder):

- [x] **Coverage matrix** — enumerate the behaviors to *guarantee* functionally
      (data types, object types, trigger/proc/function/view semantics), proving
      the schema is minimal yet complete. Done: `tests/functional_equivalence/
      coverage-matrix.md` locked for Phase 1 — every type/object mapped to a
      scenario step and to an `expected_state.yaml` assertion, with a minimality
      argument and a per-value determinism checklist. Resolved the draft gaps:
      `fn_tax` now exercised via a tax-on-invoice path, `is_paid` set by an
      explicit payment-path UPDATE, `created_at` is presence-asserted only.
- [x] **Minimal schema** — a small invoicing-style domain (customer, product,
      invoice, invoice_line, payment) that exercises every covered construct;
      canonical DDL + a UML/Mermaid diagram. Design locked in `schema.mmd`;
      canonical T-SQL DDL authored in `schema/tsql.sql` (Scenario A + B:
      5 tables with PK/FK/UNIQUE/CHECK/DEFAULT and pinned identity, a sequence,
      `fn_tax`/`fn_days_between`, `v_invoice_totals`/`v_overdue_invoices`, and
      the `trg_line_total`/`trg_invoice_touch`/`trg_payment_paid` triggers).
      Transpiles to all three targets with exit 0; output spot-checked.
      Discovered + fixed while validating: a FOREIGN KEY that `REFERENCES` a
      `dbo`-qualified table kept the `dbo.` on Oracle/MySQL/PostgreSQL (a real
      transpiler bug; the schema of the *created* table was already stripped but
      the reference target was not). Fixed in `converter.py` with a failing test
      first (`test_foreign_key_reference_strips_dbo_schema`).
- [x] **dbo. leak on views / sequences / object bodies** (discovered while
      validating the canonical schema; now fixed). The `dbo` default schema is
      meaningful only in T-SQL, so it is dropped for the three other engines.
      Centralized the strip in `_emit_table_ref` (a new optional `dialect`
      argument), which covers the view name, tables in a view/SELECT body, and
      INSERT/UPDATE/DELETE/JOIN targets; the prior ad-hoc strip in
      `_emit_create_table` now reuses it. A general `_strip_dbo_schema_qualifier`
      cleans sqlglot passthrough output (CREATE SEQUENCE / INDEX / ALTER) and the
      MySQL "no sequences" degradation comment. Failing tests first
      (`test_create_view_strips_dbo_schema`, `test_create_sequence_strips_dbo_schema`).
      Verified end-to-end: the canonical schema transpiles to all three engines
      with **0 executable `dbo.`** (remaining occurrences are inside harmless
      degraded-guard comments).
- [x] **Standalone `UPDATE … FROM … JOIN` fixed** (found while validating the
      canonical trigger bodies). The transpiler used to drop the source table
      and join predicate entirely, emitting a bare `UPDATE t SET c = s.c`
      (wrong: undefined alias, updates every row). `_convert_update` now lifts
      `FROM`/`JOIN` into the IR and `_emit_update` renders each engine's
      idiomatic cross-table form (PostgreSQL `FROM … WHERE`, MySQL `JOIN … SET`,
      Oracle correlated subquery + `EXISTS`, T-SQL native `FROM`/`JOIN`). Also
      fixed a long-standing bug where a join alias was emitted twice (`t2 b b`).
      Tests first (`test_update_from_join_*`, `test_select_join_with_alias_not_duplicated`).
- [x] **Set-based trigger bodies now functional on PostgreSQL.** The procedural
      engine (a separate parser/transformer/emitter from the standalone-DML
      path) used to delegate embedded DML straight to sqlglot, which mishandles
      `UPDATE … FROM … JOIN`, leaving the set-based trigger UPDATEs invalid or
      degraded. `_transform_embedded_dml` now routes a cross-table embedded
      UPDATE through the IR converter/emitter, so PostgreSQL emits a valid
      `UPDATE … FROM inserted WHERE …` inside the `FOR EACH STATEMENT` trigger
      function (with `REFERENCING NEW TABLE AS inserted OLD TABLE AS deleted`).
      All three canonical triggers (`trg_line_total`, `trg_invoice_touch`,
      `trg_payment_paid`) now transpile to **functional** PostgreSQL: 0 degraded
      bodies, 0 executable `dbo.`, 0 empty `FROM`. Along the way, fixed three
      general bugs (TDD): a top-level `AND`/`OR` in a WHERE emitted as a function
      call `AND(a,b)` (`exp.And` is also `exp.Func`, so Binary is now checked
      before Func); a schema-qualified user-function call `dbo.fn_tax(...)`
      (parsed as an `exp.Dot`) kept `dbo.` and is now folded into a
      FunctionCall whose qualifier is stripped per engine; and an empty `FROM`
      when a join targeted a subquery (now falls back to the documented path).
      Canonical trigger bodies were also rewritten to use correlated subqueries
      (not JOIN-against-aggregate) — the faithfully-transpilable pattern.
      MySQL/Oracle still document the set-based form (no named transition
      tables); that is a real limitation, not a bug — see next item.
- [ ] **MySQL/Oracle set-based triggers remain documented (by design).** Neither
      has T-SQL's named `inserted`/`deleted` transition tables, so a set-based
      trigger can't be mechanically rewritten to a single faithful trigger
      (Oracle would need a compound trigger accumulating rows into a PL/SQL
      collection; MySQL has no transition tables at all). Both emit a `-- UNIQUE:`
      note today. Revisit only if a faithful automatic rewrite proves feasible;
      otherwise this stays a documented divergence, and the functional-
      equivalence harness should assert trigger-maintained values on PostgreSQL
      (+ T-SQL) and treat MySQL/Oracle trigger effects as out of scope.
- [x] **Deterministic scenario authored** (`scenario/tsql.sql`) — the five
      locked steps in T-SQL: seed (2 customers, one with notes one NULL; 2
      products), direct INSERT invoice 1 + 2 lines, UPDATE a line on the
      triggered table (Widget qty 2→3), `create_invoice` proc call for invoice 2,
      and a payment that marks it paid. All literals fixed (dates, `CAST(… AS
      DECIMAL(p,s))`), 10% tax exact at scale 2. Also added the missing
      `create_invoice` stored procedure to `schema/tsql.sql`. Schema +
      scenario transpile to all three targets with exit 0; PostgreSQL output
      spot-checked (proc body, INSERTs, triggered UPDATE all valid).
- [x] **`EXEC proc` / batch `DECLARE` now route to the procedural engine.** The
      batch classifier only treated `CREATE/ALTER PROCEDURE/FUNCTION/TRIGGER` as
      procedural, so a standalone `EXEC dbo.create_invoice …` or `DECLARE @x …`
      fell to the sqlglot path and degraded to `-- UNIQUE: Unhandled … Declare/
      Execute`. Added T-SQL classifier patterns for `EXEC/EXECUTE <user proc>`
      (system `sp_*`, incl. schema-qualified `sys.sp_*`, still excluded so the
      DML pipeline documents them) and batch-level `DECLARE @…`. TDD:
      test_exec_proc_is_procedural / _execute_keyword_ / _batch_declare_ /
      _exec_system_proc_not_procedural. Full suite green (1149).
- [x] **Standalone `EXEC proc` now emits `CALL` per engine.** A top-level
      anonymous block parses to a new `AnonymousBlock` IR node (the top-level
      parser routes a bare `EXEC`/`DECLARE` batch through the statement parser
      instead of returning one verbatim `RawSQL`). `EXEC [dbo.]proc args` →
      `CALL proc(args)` on PostgreSQL/MySQL and `proc(args);` on Oracle, with the
      `dbo` schema stripped, the trailing `OUTPUT` keyword dropped, and the
      qualified-name regex fixed in all three EXEC emitters (previously
      `CALL dbo(. proc …)`). Oracle wraps the call in a `BEGIN … END;` PL/SQL
      block (a bare call isn't runnable standalone). Scenario step 4 rewritten to
      a positional call (the new id is invoice 2, used directly), and the unused
      `@new_id OUTPUT` removed from `create_invoice`. Result: the full
      schema+scenario transpile to PostgreSQL with **0 degraded steps / 0 UNIQUE
      comments**. TDD: `TestStandaloneExec` (3 engines).
- [ ] **Batch `DECLARE @x … @x OUTPUT` capture (deferred).** The simple proc
      call is done; a block that *captures* a procedure's OUT parameter into a
      batch-local variable still needs a target form (PostgreSQL `CALL` with an
      INOUT inside a `DO $$ DECLARE … $$`, or an Oracle `DECLARE … BEGIN …`).
      Not needed by the current scenario (it uses no OUT capture); revisit if a
      future scenario does.
- [x] **Engine-agnostic expected-state spec** (`expected_state.yaml`) — per-table
      row counts and specific `pk → column` values, defined once. Done: locked
      for Phase 1, all values reconciled (invoice.total = net + 10% tax, every
      taxed value exact at scale 2) and cross-checked against the matrix.
- [x] **Harness built** — `state_check.py` (load `expected_state.yaml`, per-engine
      value normalization: bool/int/decimal-scale/str-trim/date/NULL, and table
      comparison) and `engine_runner.py` (statement splitter for GO / `;` /
      Oracle `/`, keeping `$$…$$` and `BEGIN…END` bodies intact; lazy DB-API
      connect per engine; run script + read tables). The live test
      `test_functional_equivalence_live.py` transpiles schema+scenario per target,
      runs them, and asserts the expected state; it **skips** unless the matching
      `UNIQUE_TEST_*_URL` env var is set (same pattern as `test_live_syntax.py`).
      The pure mechanics are CI-covered with no external DB: `test_state_check.py`
      (17 cases) and `test_engine_runner.py` (splitter + an end-to-end read+compare
      smoke test on SQLite). Added Oracle to `docker-compose.test.yaml` and a
      runbook (`HARNESS.md`).
- [x] **Live run + final adjustments** (2026-07-03, against real PostgreSQL 16
      and MariaDB 11). The first live run surfaced and fixed, test-first:
      PostgreSQL transition-table rules (single event per trigger, NEW/OLD
      TABLE availability per event → the pg emitter and native fixture now
      split multi-event set-based triggers, with a `pg_trigger_depth()` guard
      emulating T-SQL's RECURSIVE_TRIGGERS OFF — unguarded, the rollup
      trigger recursed to the stack limit); `BIT DEFAULT 1`/0-1 literals into
      BOOLEAN columns (harvested BIT-column registry + emit-time coercion,
      incl. embedded procedure DML); T-SQL `IF OBJECT_ID ... IS NOT NULL
      DROP` guards now map to `DROP ... IF EXISTS`/pg_trigger DO-block/Oracle
      tolerant block (transpiled schemas are re-runnable); MySQL one event
      per trigger (split, and multi-routine DELIMITER wrapping); MariaDB's
      no-IGNORE_SPACE rejection of `CAST (` (built-in call spacing collapsed);
      MySQL integer display widths dropped for PostgreSQL; missing DROP VIEW
      guards in the MySQL fixture. Trigger-maintained values
      (`trigger_maintained` in expected_state.yaml) are excluded on targets
      where the source's set-based triggers are documented divergences
      (tsql→mysql/oracle), per the design note below. **Live-green pairs:**
      tsql→postgresql, tsql→mysql, postgresql→postgresql, mysql→mysql.
      MSSQL/Oracle identity pairs need pyodbc / valid Oracle credentials.
- [x] **CI job for the live harness** — the `syntax-live` workflow job runs
      `test_functional_equivalence_live.py` against the same four engines it
      already starts (MSSQL/Oracle/MySQL/PostgreSQL), right after the live syntax
      validation, surfacing any divergence as a `::error::` annotation + step
      summary. Confirmed green against the real engines, so it is now **gating**
      (the `continue-on-error` guard was removed) for the tagged Docker publish.
- [ ] **Phase 2: full 4×4 matrix** — author the scenario natively in each of the
      four dialects and require all 16 source×target runs to converge on the
      same `expected_state.yaml`.
  - [x] **Native fixtures written** — `schema/{postgresql,mysql,oracle}.sql` and
        `scenario/{postgresql,mysql,oracle}.sql`, each idiomatic to its engine
        (PostgreSQL `GENERATED … IDENTITY` + statement-level transition-table
        triggers; MySQL `AUTO_INCREMENT` + `TINYINT(1)` + row-level `FOR EACH ROW`
        triggers with `DELIMITER //` routine bodies; Oracle `GENERATED … IDENTITY`
        + `NUMBER(1)` booleans + **compound triggers** to dodge the mutating-table
        error). All parse cleanly as their own source dialect (exercising each
        parser) and share the canonical arithmetic (totals 61.05 / 39.05). The
        T-SQL native fixture is `*/tsql.sql`.
  - [x] **Harness splitter hardened for the native fixtures** — `split_statements`
        now ignores `--` and `/* */` comments (an apostrophe or BEGIN/END inside
        a comment no longer desyncs it) and honors MySQL `DELIMITER //` directives
        (routine bodies kept intact, directives dropped). TDD in
        `test_engine_runner.py`.
  - [x] **16-pair harness wired** — `test_functional_equivalence_live.py` now
        parametrizes all 16 (source, target) pairs. Only the four native fixtures
        are committed; for source != target the harness transpiles the source's
        native schema+scenario to the target **on the fly** (nothing transpiled
        is stored). Each pair skips unless the target's `UNIQUE_TEST_*_URL` is
        set. Collection verified (16 pairs, all skip cleanly without DB URLs; all
        16 on-the-fly transpilations produce non-empty SQL). The CI `syntax-live`
        job runs it; kept `continue-on-error` until the 12 cross-dialect pairs are
        confirmed green on real engines (the T-SQL->{PG,MySQL,Oracle} column was
        already green). Renamed `canonical.sql` -> `tsql.sql` so the four fixtures
        are symmetric.
  - [ ] **Confirm the 12 cross-dialect pairs on real engines**, then remove
        `continue-on-error` to make the full 4×4 gating. Live status
        (2026-07-03, PostgreSQL+MariaDB): **green** tsql→postgresql and
        tsql→mysql; **red** with identified causes:
        - postgresql→mysql: the pg trigger *function* (`RETURNS TRIGGER`)
          transpiles as a MySQL function returning the nonexistent TRIGGER
          type; needs a pg-source trigger-function + CREATE TRIGGER pairing
          into a single MySQL trigger (or documented degradation).
        - mysql→postgresql: row-level `SET NEW.line_total = ...` mangles to
          `NEW := . line_total = ...`; the pg emitter needs dotted-target
          assignments (`NEW.col := expr`).
        - oracle→postgresql / oracle→mysql: the anonymous
          `FOR r IN (...) LOOP EXECUTE IMMEDIATE` drop block emits invalid
          fragments (`END AS LOOP;`); needs FOR-loop + EXECUTE IMMEDIATE
          support in the anonymous-block path (pg: DO $$ ... $$) or a
          documented degradation instead of invalid SQL.
        Oracle-target pairs untested (server credentials rejected;
        see HARNESS.md runbook).

Key design risks, captured for when we start:
- **Determinism** is the central challenge — see the folder README for the list
  of engine-defined behaviors to design around.
- **Cross-engine value normalization** for the assertions (BIT vs BOOLEAN,
  NUMBER vs INT, DECIMAL scale, CHAR padding, CLOB/NCLOB, NULL) is the bulk of
  harness work and where subtle false results hide.
- **Scope to the faithfully-transpilable subset**; lossy constructs stay covered
  by the existing syntactic + `-- UNIQUE:` comment tests.

## 2. Audit 2026-07-02 remediation (P1)

Findings, evidence and reproductions live in **[`audit/2026-07-02/`](../audit/2026-07-02/)**.
Work the items in this order; each fix requires a test that fails under the
identity mutant (see `skills/SKILL-development-workflow.md` → *Test assertion
quality*).

**P1 — silent loss / invalid SQL (audit doc 01):**

- [x] Enforce the no-silent-loss invariant: every unmapped construct populates
      `result.warnings`/`result.unsupported`; add the carrier↔warnings
      consistency test. (S1-3 mechanism, cross-cutting)
- [x] Translate identifier quoting between engines instead of stripping it
      (`` ` `` ↔ `"` ↔ `[]`). (S1-1)
- [x] Oracle `(+)` outer joins → proper `LEFT/RIGHT OUTER JOIN ... ON`, or
      registered unsupported — never INNER JOIN without ON. (S1-2)
- [x] MERGE → MySQL: implement the simple-case `INSERT ... ON DUPLICATE KEY
      UPDATE` rewrite the docs promise, or mark unsupported with warning. (S1-3)
- [x] `DATEADD` → MySQL `DATE_ADD(ts, INTERVAL n unit)`. (S1-4)
- [x] `ROWNUM` → `LIMIT`/`FETCH FIRST` for non-Oracle targets. (S1-5)
- [x] Drop `FROM dual` for PG/T-SQL targets. (S1-6)
- [x] `ILIKE` rewrite per target. (S1-7)
- [x] `GROUP_CONCAT` ↔ `STRING_AGG` both directions, with `SEPARATOR`
      semantics fixed for the MySQL target. (S1-8, S2-1)
- [x] Boolean literals `TRUE/FALSE` → `1/0` for T-SQL (expressions and
      DDL defaults). (S1-9)
- [x] PG DDL defaults: `CURRENT_TIMESTAMP` without parens. (S1-10)
- [x] Oracle emitter: unconstrained formal-parameter types (strip
      length/precision in parameter position). (S1-11)
- [x] Preserve `THROW`/`RAISERROR` message text on all targets. (S2-2)
- [x] T-SQL assignment-select → Oracle: handle `NO_DATA_FOUND` divergence
      (nested block + empty handler). (S2-3)
- [x] FE-harness scenario for S2-3: step 6 (`flag_payment_status`) reads
      `payment` with an assignment-select that matches no row for invoice 1
      and writes `customer.notes` ('no payment'/'paid'), asserted in
      `expected_state.yaml`; native counterparts use `MAX()` so only the
      T-SQL source exercises the transform. Verified live on PostgreSQL and
      MariaDB (Oracle blocked on server credentials; the wrapper itself is
      unit-covered in `test_no_data_found.py`). Building it also fixed the
      assignment-select `dbo.` strip for PG/MySQL targets.

**P1 — test hardening (audit doc 02):**

- [x] Rewrite `test_cross_dialect.py` / `test_function_translation.py`
      assertions to the "target idiom present, source idiom absent" pattern.
- [x] Harden `test_real_world.py` with procedural-aware validity gates
      (`TestOutputValidity`): every non-procedural transpiled statement of the
      four fixtures parses in the target dialect (FE-harness splitter +
      `classify_batch` to exempt routine bodies), no bracket/backtick/GO
      leaks into executable output, and each fixture's signature construct
      is asserted in the target idiom. Building it surfaced and fixed 10
      emitter bugs (see DONE.md: audit doc 02 hardening); integration
      kill rate 28% → 36%, gate floor raised to 33%.
- [x] Shared helper: parse every transpiled output with sqlglot in the target
      dialect (`ErrorLevel.RAISE`).
- [x] Add the identity-mutation check as a CI job with a kill-rate threshold.
- [ ] Extend live-syntax CI coverage to standalone DML/DDL probes (not only
      the procedural fixtures).

**P2 — structure & ops (audit docs 03–04):**

- [ ] Consolidate function/type/literal mappings into one table consumed by
      both pipelines.
- [x] API: sync (`def`) endpoints, input size limits (UNIQUE_MAX_SQL_BYTES),
      BOM-aware decoding, generic 500 messages.
- [x] `db_url` SSRF hardening (A3): databases are configured server-side as
      named DSNs (`UNIQUE_DSN_<NAME>`) and referenced by name (`db` field on
      both endpoints); `/api/v1/info` exposes the names (never URLs) and the
      UI renders them as a dropdown. A raw `db_url` now needs the extra
      `UNIQUE_ALLOW_RAW_DB_URL` opt-in on top of
      `UNIQUE_ALLOW_DB_CONNECTION`. Found and fixed along the way:
      `web/src/index.template.html` had drifted behind the committed
      generated `static/index.html` (a rebuild would have silently dropped
      the db-field feature); the template was regenerated from the committed
      output (round-trip verified) before applying the UI change.
- [ ] Split the >2000-line modules along their section-comment seams.

**P2 — documentation drift (audit doc 05):**

- [x] Fix README/`docs/07-interfaces.md` CLI examples (`--from/--to`, no
      inline-SQL positional).
- [x] Correct compatibility-matrix rows (ROWNUM, MERGE→MySQL, Boolean) or
      implement them; add matrix probe tests.

## 3. Packaging (P3)

- [ ] **PyPI publication** — deferred until the tool has been used in real
      projects for a few months and proven stable. Not before then.

---

## Known limitations to keep documented (not bugs)

These have no faithful cross-engine equivalent and are intentionally emitted as
comments/warnings (see `docs/03-unsupported.md`):

- SQL Server system procedures (`sp_addextendedproperty`, `sp_rename`, …).
- SQL*Plus session directives (`SET FEEDBACK`, etc.) and `rem`/`prompt`
  (preserved as comments).
- `%TYPE`/`%ROWTYPE` without `--db-url` (emitted as a carrier type with the
  original preserved in a `/* UNIQUE: … */` comment, plus a warning) — see item 2
  for making these reversible.

