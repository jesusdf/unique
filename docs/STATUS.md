# Unique — Project Status

## Current state: v0.20.0

The DML/DDL pipeline and the autonomous procedural engine are complete, and
**functional equivalence** holds across the **full 4×4 matrix — all 16
source×target pairs converge on the same final database state**, validated live
against real engines (SQL Server via pymssql, PostgreSQL, MySQL/MariaDB, and
Oracle via a local container). Since the functional-equivalence milestone the
tool has been hardened extensively on **real migration dumps and real schemas**,
and — most significantly — a **bug-detection infrastructure** now drives quality
instead of hand-written examples. Most recently, the **T-SQL → Oracle procedures
fixture (32 objects) transpiles to fully-valid PL/SQL** — the Oracle live
validator queries `USER_ERRORS` (Oracle compiles PL/SQL lazily) and the whole
procedural validity backlog is closed (26 → 0 INVALID; `docs/DONE.md` §33).
Migration-script idioms translate too: a real-data `IF EXISTS(subquery)` guard is
emulated with a cursor FOR loop (a THEN/ELSE pair over the negated probe), and a
system-catalog `IF NOT EXISTS(…) CREATE` guard becomes an idempotent, portable
`user_objects` probe + `EXECUTE IMMEDIATE` (re-runnable without `ORA-00955`). The
version is single-sourced from `unique.__version__` and released via
`scripts/release.py`. The detailed history lives in `docs/DONE.md`; the backlog
(`docs/TODO.md`) is packaging-only.

### Bug-detection infrastructure (what replaced ad-hoc manual testing)

Four complementary layers, all in CI:

- **Corpus × live-execution sweep** (`test_corpus_live.py`,
  `scripts/corpus-sweep.py`): a curated, self-contained SQL corpus is transpiled
  to every valid target and the output is **executed against the real engine**
  (a permissive parser accepts output a real engine rejects, so executing is what
  actually catches bugs). Documented gaps are annotated `-- @xfail` in the corpus.
- **Generative fuzzer + preservation invariants** (`tests/property/`,
  `tests/helpers/sql_gen.py`): Hypothesis generates portable SELECTs and asserts
  invariants on every transpile — output parses on the target, no Python `None`
  or IR-node repr leaks, comments preserved, aliases conserved, round-trip valid
  — shrinking any failure to a minimal reproducer.
- **Differential result testing** (`test_corpus_results_live.py`): executes the
  source statement on its engine and the transpiled output on each target,
  comparing normalized result sets — catches **semantic** (wrong-answer) bugs
  that syntactic validity cannot.
- **Mutation testing** (`scripts/mutation_test.py`, nightly `mutation.yml`):
  the objective test-assertion-quality metric; surviving mutants are lines a test
  executes but does not verify. The nightly job fails on a score regression and
  opens a tracking issue.

These caught and fixed real bugs that "valid SQL that executes" would miss:
a **UNION of 3+ arms dropping every middle arm**, dropped derived-table aliases
and joined subqueries, `LIMIT None`, a table-less SELECT to Oracle missing
`FROM DUAL`, an **IR-node repr leaking into SQL** for an `EXISTS` subquery, and a
class of function/type mapping gaps.

### Completed (high level)

- [x] **Core engine (DML/DQL/DDL)** — IR nodes (`ast_nodes.py`), shared
      sqlglot↔IR converter (the `converter/` package: `_base`/`harvest`/`convert`/
      `emit`), transform passes (`transformer.py`), orchestrator
      (`transpiler.py`), dialect registry, error hierarchy.
- [x] **Autonomous procedural engine** — batch splitter, lexer, recursive-descent
      parser, transformer, emitter (`core/procedural/`), plus a metadata resolver
      (`metadata.py`) for `%TYPE`/`%ROWTYPE`.
- [x] **Dialect plugins** — T-SQL, Oracle, PostgreSQL, MySQL (source and target),
      plus SQLite as an **import-only source** (never a target).
- [x] **Interfaces** — CLI, REST API (FastAPI), Python library, embedded web UI
      (with source auto-detect and server-side named DSNs for `--db-url`).
- [x] **Set operations** — `UNION`/`UNION ALL` (any number of arms) and
      `EXCEPT`/`INTERSECT` (Oracle `MINUS`), subqueries in `FROM`/`JOIN`/`EXISTS`,
      table-less SELECT (Oracle `FROM DUAL`), `OFFSET/FETCH`↔`LIMIT`↔`TOP`.
- [x] **Type & function mappings** — binary/LOB families, unsigned integers/
      floats, `NVL2`/`DECODE`→CASE, `IIF`→CASE, `NOW`/`CURDATE`/`CURRENT_DATE`,
      `TO_CHAR`/`TO_DATE` format models, `DATEDIFF`/`DATEADD`, `CONVERT`→CAST,
      per-dialect CAST types, `TRUNC`, string `+` chains → concat, and **bitwise
      operators → Oracle via BITAND/POWER identities** (all validated live).
- [x] **Cross-engine `%TYPE`/`%ROWTYPE`** — resolved through a `--db-url` pointing
      at *any* of the five engines (SQL Server, Oracle, PostgreSQL, MySQL, SQLite).
- [x] **Lossy conversions documented & reversible** — non-portable types lower to
      a `/* UNIQUE: … */` carrier; a reverse/onward transpilation restores the
      original where the target supports it.
- [x] **Triggers** — firing modes/granularity; PostgreSQL trigger function; pure
      set-based triggers → PostgreSQL statement-level with transition tables.
- [x] **Comment preservation** — leading/section comments before `IF [NOT]
      EXISTS` guards and before procedural `CREATE`s are kept (invariant-tested).
- [x] **Real-schema validation** — the MediaWiki 1.46 schema (64 tables) executes
      live: `mysql → {postgresql, oracle, tsql}` and `sqlite → postgresql` green.
- [x] **Tooling & policy** — Docker, CI (lint/format, type check, test on 3.12,
      live metadata, live syntax, nightly mutation, docker on tags), sqlglot
      pinned, English-only by design, MIT licensed.

### Test suite

~1550 passing + the live-only tests that run in the CI live jobs (skipped
without database URLs). Run `pytest tests/ -q`, or `scripts/test-parallel.sh`
for a GNU-parallel run across cores.

### Known limitations

See `docs/03-unsupported.md` for the full list. Highlights (intentionally emitted
as documented `-- UNIQUE:` comments / warnings, never silently dropped):

- `%TYPE`/`%ROWTYPE` **without** `--db-url` → carrier type + comment (restored on
  a round-trip back to a supporting engine); with `--db-url` it resolves.
- `EXECUTE IMMEDIATE … USING` bind variables (T-SQL `sp_executesql`).
- Mixed row-/set-level triggers, and set-based triggers on Oracle/MySQL.
- `col + col` string concat with no type info (no `--db-url`) is left as `+`
  (T-SQL resolves it by declared types the standalone-DML path lacks).
- Indexing an **unbounded** `TEXT`/`BLOB` column on MySQL/SQL Server/Oracle
  (intrinsic source-schema ↔ target-engine mismatch).
- SQL Server system procedures, SQL*Plus directives, and engine-specific physical
  features (partitioning, tablespaces, filegroups, index storage clauses).

### Next steps

The functional-equivalence, audit-remediation and test-quality backlogs are
complete and archived in `docs/DONE.md`. `docs/TODO.md` holds only:

- [ ] Publish to PyPI — **deferred (do not publish yet)**.
