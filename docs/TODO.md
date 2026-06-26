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
      canonical T-SQL DDL authored in `schema/canonical.sql` (Scenario A + B:
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
- [x] **Deterministic scenario authored** (`scenario/canonical.sql`) — the five
      locked steps in T-SQL: seed (2 customers, one with notes one NULL; 2
      products), direct INSERT invoice 1 + 2 lines, UPDATE a line on the
      triggered table (Widget qty 2→3), `create_invoice` proc call for invoice 2,
      and a payment that marks it paid. All literals fixed (dates, `CAST(… AS
      DECIMAL(p,s))`), 10% tax exact at scale 2. Also added the missing
      `create_invoice` stored procedure to `schema/canonical.sql`. Schema +
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
- [ ] **Standalone anonymous block (`DECLARE … EXEC …`) emission.** Routing is
      fixed, but the procedural emitter leaves a top-level anonymous block almost
      verbatim (`DECLARE v_inv2 INT ; EXEC create_invoice … OUTPUT ;`) instead of
      the target form: PostgreSQL needs a `DO $$ DECLARE … BEGIN CALL
      create_invoice(…); END $$;` wrapper (or a plain `CALL` when no variable
      capture is needed), `EXEC name args` → `CALL name(args)`, and the trailing
      `OUTPUT` dropped with the OUT arg bound. The procedural engine already does
      EXEC→CALL *inside* a CREATE PROCEDURE body; extend that to a standalone
      anonymous block. Required before step 4 of the scenario runs end-to-end.
- [x] **Engine-agnostic expected-state spec** (`expected_state.yaml`) — per-table
      row counts and specific `pk → column` values, defined once. Done: locked
      for Phase 1, all values reconciled (invoice.total = net + 10% tax, every
      taxed value exact at scale 2) and cross-checked against the matrix.
- [ ] **Harness + CI** — for each engine: clean setup → run script → read each
      table into a canonical (type-normalized) form → assert against the spec →
      teardown. Reuse `tests/helpers/live_validation.py`. Start with one
      canonical source (T-SQL) transpiled to the other three (4 runs); grow to
      the full 4×4 matrix (each engine authored natively, cross-transpiled).

Key design risks, captured for when we start:
- **Determinism** is the central challenge — see the folder README for the list
  of engine-defined behaviors to design around.
- **Cross-engine value normalization** for the assertions (BIT vs BOOLEAN,
  NUMBER vs INT, DECIMAL scale, CHAR padding, CLOB/NCLOB, NULL) is the bulk of
  harness work and where subtle false results hide.
- **Scope to the faithfully-transpilable subset**; lossy constructs stay covered
  by the existing syntactic + `-- UNIQUE:` comment tests.

## 2. Packaging (P3)

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

