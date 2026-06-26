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

- [ ] **Coverage matrix** — enumerate the behaviors to *guarantee* functionally
      (data types, object types, trigger/proc/function/view semantics), proving
      the schema is minimal yet complete.
- [ ] **Minimal schema** — a small invoicing-style domain (customer, product,
      invoice, invoice_line, payment) that exercises every covered construct;
      canonical DDL + a UML/Mermaid diagram generated from it.
- [ ] **Deterministic scenario** — seed inserts + mutations whose outcome is
      identical across engines (fixed dates, explicit decimal scale, no
      engine-defined division/concat/rounding/collation behavior in asserted
      values).
- [ ] **Engine-agnostic expected-state spec** (`expected_state.yaml`) — per-table
      row counts and specific `pk → column` values, defined once.
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

