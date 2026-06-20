# Unique — Project Status

## Current Phase: Real-World Hardening

The DML/DDL pipeline and the autonomous procedural engine are complete for
all 12 dialect pairs. Current focus is hardening against real production
schemas (public sample databases + a private procedures file) and closing
DDL gaps (ALTER TABLE, indexes, sequences, table-level constraints).
See `docs/TODO.md` for the prioritized backlog.

### Completed

- [x] **Claude AI continuity skills** — `skills/SKILL-project-overview.md`, `skills/SKILL-development-workflow.md`
- [x] **Compatibility analysis** — `docs/01-compatibility.md` (164 features, 68% fully supported)
- [x] **Architecture design** — `docs/02-architecture.md` (AST + IR approach with plugin system)
- [x] **Procedural engine design** — `docs/05-procedural-engine.md`
- [x] **Unsupported features docs** — `docs/03-unsupported.md`
- [x] **Development guide** — `docs/04-development-guide.md`
- [x] **Core engine (DML/DQL/DDL)**
  - IR node definitions (`ast_nodes.py`) — 65+ node types
  - Shared converter (`converter.py`) — sqlglot AST ↔ IR conversion + emission
  - Transformation passes (`transformer.py`) — function, type, and syntax normalization
  - Transpiler orchestrator (`transpiler.py`) — batch-split → classify → route → join
  - Dialect registry (`registry.py`) — entry-point auto-discovery + manual registration
  - Error hierarchy (`errors.py`)
- [x] **Autonomous procedural engine** (independent of sqlglot for procedural SQL)
  - Batch splitter (`batch_splitter.py`) — dialect-aware splitting (GO, slash, `$$`, DELIMITER) + classification
  - Lexer (`procedural/lexer.py`) — full tokenizer for procedural SQL
  - Parser (`procedural/parser.py`) — recursive descent for T-SQL and PL/SQL
  - Transformer (`procedural/transformer.py`) — dialect-aware AST transformations
  - Emitter (`procedural/emitter.py`) — target-dialect procedural code generation
  - Metadata resolver (`metadata.py`) — optional DB connection for `%TYPE`/`%ROWTYPE`
- [x] **Dialect plugins** — T-SQL, Oracle, PostgreSQL, MySQL
- [x] **CLI** — `unique transpile` (with `--db-url`), `unique validate`, `unique dialects`
- [x] **REST API** — FastAPI with `/api/v1/transpile` (with `db_url`), `/api/v1/validate`, `/api/v1/dialects`, `/health`
- [x] **Test suite** — 401 tests (unit + integration), all passing
- [x] **Docker** — `Dockerfile`, `Dockerfile.dev`, `docker-compose.yaml`
- [x] **CI/CD** — GitHub Actions (`lint`, `typecheck`, `test`, `docker`); linter versions pinned
- [x] **README.md**

### Procedural Engine — Real-World Validation

Validated end-to-end against a private real-world script (not included in
this repository — ~4,300 lines, 25 procedures + 1 trigger), both directions:

| Direction | Procedures | Empty bodies | Translated IF blocks | Assignments | Errors |
|-----------|-----------:|-------------:|---------------------:|------------:|-------:|
| T-SQL → Oracle | 25/25 | 0 | 43 | 44 | 0 |
| Oracle → T-SQL | 25/25 | 0 | (IF/THEN) | 17 | 0 |

Before this work, 100% of procedure bodies were passthrough (untranslated).

### Dialect Pair Coverage

All four engines work as both source and target. Procedural transpilation
(parameters, declarations, control flow, types, variable naming) is
implemented for every common pair:

| As source → targets | Status |
|----------------------|--------|
| T-SQL → Oracle / PostgreSQL / MySQL | validated (incl. real file) |
| Oracle → T-SQL / PostgreSQL / MySQL | validated (incl. real file) |
| PostgreSQL → T-SQL / Oracle / MySQL | header + body parsing |
| MySQL → T-SQL / Oracle / PostgreSQL | params, DECLARE, SET, splitter |

Advanced constructs handled: `EXECUTE IMMEDIATE ... USING` (→ sp_executesql /
PREPARE / native USING), cursors and `EXIT WHEN cur%NOTFOUND`, unconditional
`LOOP`, and cursor `FOR` loops (native in PG, flagged elsewhere).

### Test Coverage Summary

| Module | Tests |
|--------|-------|
| core/errors | 8 |
| core/ast_nodes | 15 |
| core/registry | 7 |
| core/converter | 45 |
| core/transformer | 14 |
| core/transpiler | 15 |
| dialects | 16 |
| procedural/lexer | 24 |
| procedural/batch_splitter | 25 |
| procedural/parser | 29 |
| procedural/transformer | 54 |
| procedural/emitter | 25 |
| procedural/metadata | 25 |
| cli | 9 |
| api | 9 |
| integration (cross-dialect) | 228 |
| integration (procedural) | 26 |
| integration (real-world fixtures) | 50 |
| integration (metadata live) | 7 (skipped without DB) |
| property-based (Hypothesis) | 7 |
| **Total** | **623 (+7 skipped)** |

Overall line coverage: ~80%. Live `--db-url` resolution is exercised in CI
against real PostgreSQL 16 and MySQL 8 service containers. Four public
sample schemas (AdventureWorksLT, Oracle HR, Sakila, Northwind) are
transpiled across all 12 dialect pairs as regression guards
(see `tests/fixtures/real_world/SOURCES.md`).

### Known Limitations

See `docs/03-unsupported.md` for the full list and `docs/TODO.md` for the
prioritized backlog. Highlights:

- **`%TYPE`/`%ROWTYPE` without `--db-url`** → emitted as `SQL_VARIANT` with a warning
- **`EXECUTE IMMEDIATE ... USING`** (Oracle bind variables) → flagged for manual conversion
- **Table variables** (`DECLARE @t TABLE (...)`) → column list captured verbatim
- **Ref cursors as OUT parameters** → require manual adaptation
- **ALTER TABLE / CREATE INDEX / CREATE SEQUENCE** → IR nodes exist but are
  not yet wired through the converter (commented passthrough today)
- **Table-level constraints and user-defined domain types** in CREATE TABLE
- Oracle-specific (CONNECT BY, MODEL) and T-SQL-specific (CROSS/OUTER APPLY) constructs

### Next Steps

See `docs/TODO.md` for the full prioritized backlog. Highest priority:

- [ ] Wire ALTER TABLE, CREATE INDEX, CREATE SEQUENCE, CREATE SCHEMA through the IR
- [ ] Table-level constraints (PK/FK/UNIQUE/CHECK) and user-defined domain types
- [ ] `SELECT ... INTO <var>` consistency across source dialects
- [ ] Argument-reordering function mappings (CHARINDEX/INSTR/LOCATE, DECODE→CASE)
- [ ] End-to-end tests with the private `procedures.sql` (delivery TBD)
- [ ] Publish to PyPI — **deferred (do not publish yet)**

#### Completed since last review

- [x] Unit tests for procedural transformer, emitter, and metadata resolver
- [x] Live `--db-url` integration tests (containerized databases)
- [x] `EXECUTE IMMEDIATE ... USING` → `sp_executesql` parameter mapping
- [x] Property-based testing with Hypothesis
- [x] PostgreSQL and MySQL as source and target dialects
- [x] CLI and API test coverage
- [x] DATEADD / DATEDIFF translation; broadened function-mapping tables
- [x] Real-world fixture transpilation tests (4 schemas × 12 pairs)
- [x] Oracle splitter: semicolon scripts, `rem`/`prompt` preserved as comments
- [x] MySQL routine characteristics (DETERMINISTIC, READS SQL DATA, ...)
- [x] SQL Server system procedures emitted as comments cross-dialect
- [x] CREATE TABLE column constraints preserved (IDENTITY, NULL, DEFAULT);
      ROWGUIDCOL / NOT FOR REPLICATION stripped
- [x] Table-level constraints, domain types, computed columns, portable
      indexes (CLUSTERED/INCLUDE/filtered), USE/MERGE/CONNECT BY/SELECT INTO,
      OUTPUT↔RETURNING, FOR UPDATE/QUALIFY — preserved or documented rather
      than silently dropped
- [x] Function translation: substring-position reordering, DECODE/NVL2→CASE,
      STRING_AGG↔LISTAGG↔GROUP_CONCAT, bidirectional date-format mapping,
      CONVERT style codes, SCOPE_IDENTITY/@@IDENTITY
- [x] Generic transpilation invariants (element conservation + round-trip
      token similarity) applied across all 12 pairs
- [x] Idiomatic T-SQL output: OBJECT_ID guard instead of CREATE TABLE IF NOT
      EXISTS; GO-based batch separation without spurious `;` or post-comment GO
- [x] Web UI (two CodeMirror editors with SQL highlighting, embedded — no
      CDN), dialect auto-detection, and file upload/download translation;
      new `/api/v1/detect` and `/api/v1/transpile/file` endpoints
- [x] Live syntax validation against real engines (SQL Server PARSEONLY,
      Postgres/MySQL rolled-back transactions) as a CI job
