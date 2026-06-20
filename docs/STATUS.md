# Unique — Project Status

## Current Phase: Real-World Hardening

The DML/DDL pipeline and the autonomous procedural engine are complete for
all 12 dialect pairs. Current focus is hardening against real production
schemas (public sample databases + anonymized stored-procedure fixtures),
validating transpiler output against real engines, and closing DDL gaps
(ALTER TABLE, indexes, sequences). See `docs/TODO.md` for the prioritized
backlog.

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
- [x] **REST API** — FastAPI with `/api/v1/transpile` (with `db_url`),
      `/api/v1/validate`, `/api/v1/detect`, `/api/v1/transpile/file`,
      `/api/v1/dialects`, `/health`, plus the web UI at `/`
- [x] **Web UI** — embedded CodeMirror editors, dialect auto-detection, file
      translation (`web/build.py` produces a self-contained `static/index.html`)
- [x] **Test suite** — 858 tests collected (817 passing + 41 skipped without DB)
- [x] **Docker** — `Dockerfile`, `Dockerfile.dev`, `docker-compose.yaml`
- [x] **CI/CD** — GitHub Actions (`lint`, `typecheck`, `test`, live metadata,
      live syntax validation, `docker`); linter versions pinned; Python 3.12
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



### Known Limitations

See `docs/03-unsupported.md` for the full list and `docs/TODO.md` for the
prioritized backlog. Highlights:

- **`%TYPE`/`%ROWTYPE` without `--db-url`** → emitted as `SQL_VARIANT` with a warning
- **`EXECUTE IMMEDIATE ... USING`** (Oracle bind variables) → flagged for manual conversion
- **Table variables** (`DECLARE @t TABLE (...)`) → column list captured verbatim
- **Ref cursors as OUT parameters** → require manual adaptation
- **ALTER TABLE / CREATE INDEX / CREATE SEQUENCE** → re-transpiled as passthrough
  via sqlglot (IR wiring still pending; see TODO §1)
- **Data-type names inside procedural bodies** → not yet mapped (CREATE TABLE
  types are; see TODO §2)
- Oracle-specific (CONNECT BY, MODEL) and T-SQL-specific (CROSS/OUTER APPLY) constructs

### Next Steps

See `docs/TODO.md` for the full prioritized backlog. Highest priority:

- [ ] Make the anonymized procedural fixtures executable against real engines:
      generate the referenced DDL, then add a CI job that creates the schema
      and runs the scripts + their transpilations against real SQL Server and
      Oracle.
- [ ] Map data-type names inside procedural bodies (variable/parameter
      declarations), extending the CREATE TABLE type mapping.
- [ ] Wire ALTER TABLE, CREATE INDEX, CREATE SEQUENCE, CREATE SCHEMA through the IR
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
- [x] Live syntax validation against real engines (SQL Server / PostgreSQL /
      MySQL), executed in rolled-back transactions — MySQL in a throwaway
      database — as a CI job. This layer found real bugs (NVARCHAR not mapped
      to PG, invalid index CASE, typeless generated columns), all since fixed.
- [x] Non-portable data-type name mapping (CREATE TABLE and passthrough DDL)
- [x] Index `CASE` (NULLS-ordering emulation) stripped for all targets but PG
- [x] Generated columns without a type → documented comment for PG/Oracle/MySQL
- [x] Single Python version (3.12) in CI; fixed a real 3.12 incompatibility
      (`EntryPoints.get()` removed) surfaced by the change
- [x] Anonymized procedural fixtures (T-SQL + Oracle) under
      `tests/fixtures/procedures/`, with parsing / anonymization-guard /
      transpile-without-crash tests
