# Unique — Project Status

## Current state: v0.9.0

The DML/DDL pipeline and the autonomous procedural engine are complete, and
**functional equivalence** holds across the **full 4×4 matrix — all 16
source×target pairs converge on the same final database state**, validated live
against real engines (SQL Server via pymssql, PostgreSQL, MySQL/MariaDB, and
Oracle via a local container). Since then the tool has been hardened on real
migration dumps: two O(n²) hot paths removed (a 13 MB script 421 s → ~30 s, now
linear), broad T-SQL migration-idiom coverage (`IF [NOT] EXISTS` guards incl.
their `ELSE` branch, `ADD [CONSTRAINT] DEFAULT … FOR`, constraint check-state,
COMMIT/ROLLBACK/TRUNCATE passthrough, restorable physical index clauses with a
tsql round-trip), Oracle `/`-terminator and DML/DDL comment-preservation fixes,
a GNU-parallel test runner (~62 s → ~23 s), and **SQLite added as an import-only
source**. The detailed history lives in `docs/DONE.md`; the backlog
(`docs/TODO.md`) is now packaging-only.

### Completed (high level)

- [x] **Core engine (DML/DQL/DDL)** — IR nodes (`ast_nodes.py`), shared
      sqlglot↔IR converter (the `converter/` package: `_base`/`harvest`/`convert`/
      `emit`), transform passes (`transformer.py`), orchestrator
      (`transpiler.py`), dialect registry, error hierarchy.
- [x] **Autonomous procedural engine** — batch splitter, lexer, recursive-descent
      parser, transformer, emitter (`core/procedural/`), plus an optional
      metadata resolver (`metadata.py`) for `%TYPE`/`%ROWTYPE`. Independent of
      sqlglot for the procedural shell; embedded DML is delegated to sqlglot.
- [x] **Dialect plugins** — T-SQL, Oracle, PostgreSQL, MySQL (source and target),
      plus SQLite as an **import-only source** (never a target).
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
- [x] **Standalone-DML operator & function fidelity** — a cross-engine audit
      fixed several converter bugs: T-SQL string `+` maps to the target concat
      operator (`||`/`CONCAT`), bitwise `& | ^ << >>` are preserved instead of
      coerced to `=` (the dangerous default was removed), compound assignment
      (`SET a += 1`) expands to `a = a + 1`, and specialized functions keep
      **all** their arguments (sqlglot stores them in named slots — `SUBSTRING`,
      `REPLACE`, `ROUND`, `STUFF`, `REPLICATE`, `DATEADD`, `POWER`, `NULLIF`, …).
- [x] **Triggers** — firing modes/granularity across engines; PostgreSQL trigger
      function + CREATE TRIGGER; `UPDATE(col)` predicate per engine; `inserted`/
      `deleted` pseudo-tables mapped to NEW/OLD (column qualifiers). A **pure**
      set-based trigger is rewritten to a PostgreSQL statement-level trigger with
      `REFERENCING NEW TABLE AS inserted OLD TABLE AS deleted`; mixed/Oracle/MySQL
      cases are documented.
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

~1490 passing + ~120 skipped (the skipped ones need a live DB and run in the CI
live jobs). Run `pytest tests/ -q`, or `scripts/test-parallel.sh` for a
GNU-parallel run across cores (~62 s → ~23 s).

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
- Set-based trigger bodies (`FROM inserted JOIN deleted`) → **rewritten** to a
  PostgreSQL statement-level trigger (transition tables); documented on
  Oracle/MySQL and for mixed row-/set-level triggers.
- Bitwise operators targeting Oracle (no infix bitwise; preserved as-is) and
  `col + col` string concat without type info (left as `+`); `IIF`→`IF` and
  `DATEPART`→`EXTRACT` rewrites pending for standalone DML.
- SQL Server system procedures (`sp_addextendedproperty`, …), SQL*Plus
  directives, and engine-specific physical features (partitioning, tablespaces,
  filegroups, index storage clauses).

### Next steps

The functional-equivalence and audit-remediation backlogs are complete (see
`docs/DONE.md` §13–19), and SQLite import support (phases 1–3: source-only
registration, function mappings, row-level triggers) is done. `docs/TODO.md` now
holds only:

- [ ] Publish to PyPI — **deferred (do not publish yet)**.
