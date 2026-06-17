# Unique — Project Status

## Current Phase: Procedural Engine Complete

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

Validated end-to-end against `procedures.sql` (4,322 lines, 25 procedures + 1 trigger),
both directions:

| Direction | Procedures | Empty bodies | Translated IF blocks | Assignments | Errors |
|-----------|-----------:|-------------:|---------------------:|------------:|-------:|
| T-SQL → Oracle | 25/25 | 0 | 43 | 44 | 0 |
| Oracle → T-SQL | 25/25 | 0 | (IF/THEN) | 17 | 0 |

Before this work, 100% of procedure bodies were passthrough (untranslated).

### Test Coverage Summary

| Module | Tests |
|--------|-------|
| core/errors | 8 |
| core/ast_nodes | 15 |
| core/registry | 7 |
| core/converter | 45 |
| core/transformer | 14 |
| core/transpiler | 13 |
| dialects | 16 |
| procedural/lexer | 24 |
| procedural/batch_splitter | 18 |
| procedural/parser | 21 |
| integration (cross-dialect) | 214 |
| integration (procedural) | 6 |
| **Total** | **401** |

### Known Limitations

See `docs/03-unsupported.md` for the full list. Highlights:

- **`%TYPE`/`%ROWTYPE` without `--db-url`** → emitted as `SQL_VARIANT` with a warning
- **`EXECUTE IMMEDIATE ... USING`** (Oracle bind variables) → flagged for manual conversion
- **Table variables** (`DECLARE @t TABLE (...)`) → column list captured verbatim
- **Ref cursors as OUT parameters** → require manual adaptation
- Oracle-specific (CONNECT BY, MODEL) and T-SQL-specific (CROSS/OUTER APPLY) constructs

### Next Steps

- [ ] Unit tests for procedural transformer, emitter, and metadata resolver
- [ ] Live `--db-url` integration tests (against containerized databases)
- [ ] Handle `EXECUTE IMMEDIATE ... USING` → `sp_executesql` parameter mapping
- [ ] Property-based testing with Hypothesis
- [ ] PostgreSQL and MySQL procedural emission validation against real files
- [ ] Publish to PyPI
