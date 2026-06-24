# Unique — Project Status

## Current Phase: Functional-Equivalence Testing

The DML/DDL pipeline and the autonomous procedural engine are complete for all
12 dialect pairs, and the transpiler's output is validated **live against real
engines** (MySQL/MariaDB, PostgreSQL, Oracle) — the procedural fixtures load
into each engine with **0 errors**. The next milestone moves from *syntactic*
validity to *functional* equivalence: confirm that a migrated script produces
the **same final database state** (see `tests/functional_equivalence/` for the
design, and `docs/TODO.md` for the backlog). The detailed history of finished
work lives in `docs/DONE.md`.

### Completed (high level)

- [x] **Core engine (DML/DQL/DDL)** — IR nodes (`ast_nodes.py`), shared
      sqlglot↔IR converter (`converter.py`), transform passes (`transformer.py`),
      orchestrator (`transpiler.py`), dialect registry, error hierarchy.
- [x] **Autonomous procedural engine** — batch splitter, lexer, recursive-descent
      parser, transformer, emitter (`core/procedural/`), plus an optional
      metadata resolver (`metadata.py`) for `%TYPE`/`%ROWTYPE`. Independent of
      sqlglot for the procedural shell; embedded DML is delegated to sqlglot.
- [x] **Dialect plugins** — T-SQL, Oracle, PostgreSQL, MySQL (source and target).
- [x] **Interfaces** — CLI (`unique transpile/validate/dialects`, `--db-url`),
      REST API (FastAPI), Python library, and an embedded web UI.
- [x] **DDL coverage** — ALTER TABLE, CREATE INDEX (incl. CLUSTERED/INCLUDE/
      filtered), CREATE SEQUENCE, CREATE SCHEMA, USE — round-tripped via sqlglot
      passthrough; non-portable type names mapped in both our emitter and
      passthrough DDL.
- [x] **Procedural breadth** — parameters/directions, DECLARE (incl. multi-var
      hoisting), assignment & assignment-select, IF/WHILE/LOOP/FOR, cursors,
      RETURN, RAISERROR/THROW→SIGNAL, TRY/CATCH (per-engine), MERGE, OUTPUT↔
      RETURNING, table variables→temp tables, transaction control (BEGIN
      TRAN/COMMIT/ROLLBACK/SAVE), WAITFOR, SET IDENTITY_INSERT, `@@ERROR`/
      `@@ROWCOUNT`/`@@IDENTITY`, `TOP n [PERCENT]`, QUOTED_IDENTIFIER OFF, and
      function mappings (substring-position, DECODE/NVL2→CASE, STRING_AGG↔
      LISTAGG↔GROUP_CONCAT, date-format and CONVERT style codes, DATEADD/DATEDIFF).
- [x] **Lossy conversions documented & reversible** — non-portable types lower
      to a carrier with a `/* UNIQUE: <original> */` comment; a reverse/onward
      transpilation **restores the original type** where the target supports it
      (e.g. `SQL_VARIANT`→T-SQL, `%TYPE`→Oracle) and re-applies a carrier where it
      doesn't.
- [x] **Triggers** — firing modes/granularity across engines; PostgreSQL trigger
      function + CREATE TRIGGER; `UPDATE(col)` predicate per engine; `inserted`/
      `deleted` pseudo-tables mapped to NEW/OLD (column qualifiers) or documented
      (set-based use).
- [x] **Live validation** — `tests/helpers/live_validation.py` +
      `test_live_syntax.py` validate output against real engines (rolled-back
      transaction; MySQL in a throwaway database). The anonymized procedural
      fixtures (`tests/fixtures/procedures/` for all four engines) are generated
      by the transpiler and load live with 0 errors.
- [x] **Quality gates** — generic transpilation invariants (element conservation
      + round-trip token similarity across all 12 pairs), property-based tests,
      round-trip fidelity tests, full CLI/API coverage.
- [x] **Tooling** — Docker (`Dockerfile`, `Dockerfile.dev`, compose), CI
      (lint/format, type check, test on Python 3.12, live metadata, live syntax,
      docker on tags), sqlglot pinned to an exact version, MIT licensed.

### Test suite

1025 passing + 55 skipped (the skipped ones need a live DB and run in the CI
live jobs). Run `pytest tests/ -q`.

### Dialect pair coverage

All four engines work as both source and target; procedural transpilation is
implemented for every pair. The MySQL/PostgreSQL/Oracle procedures fixtures are
generated from the T-SQL source and validated live at 0 errors.

### Known limitations

See `docs/03-unsupported.md` for the full list. Highlights (intentionally
emitted as documented `-- UNIQUE:` comments / warnings, not silently dropped):

- `%TYPE`/`%ROWTYPE` without `--db-url` → carrier type + `/* UNIQUE: … */`
  comment (now restored on a round-trip back to a supporting engine).
- `EXECUTE IMMEDIATE ... USING` bind variables (T-SQL `sp_executesql`).
- Set-based trigger bodies (`FROM inserted JOIN deleted`) → documented (no
  row-level equivalent; MySQL has no transition tables).
- SQL Server system procedures (`sp_addextendedproperty`, …), SQL*Plus
  directives, and engine-specific physical features (partitioning, tablespaces,
  filegroups, index storage clauses).

### Next steps

See `docs/TODO.md`. Highest priority:

- [ ] **Functional-equivalence test database** — a minimal invoicing schema +
      deterministic scenario + engine-agnostic expected-state spec + a harness
      that runs the transpiled scripts on each engine and asserts identical final
      state. Design scaffolded in `tests/functional_equivalence/`.
- [ ] Generalize the `/* UNIQUE: … */` restorer to non-type constructs.
- [ ] Auto-rewrite a *pure* set-based trigger (PostgreSQL transition tables /
      Oracle compound trigger) instead of documenting it.
- [ ] Publish to PyPI — **deferred (do not publish yet)**.
