# Unique — Project Status

## Current Phase: MVP Development

### Completed

- [x] **Claude AI continuity skills** — `skills/SKILL-project-overview.md`, `skills/SKILL-development-workflow.md`
- [x] **Compatibility analysis** — `docs/01-compatibility.md` (164 features, 68% fully supported)
- [x] **Architecture design** — `docs/02-architecture.md` (AST + IR approach with plugin system)
- [x] **Unsupported features docs** — `docs/03-unsupported.md`
- [x] **Development guide** — `docs/04-development-guide.md`
- [x] **Core engine**
  - IR node definitions (`ast_nodes.py`) — ~50 node types
  - Shared converter (`converter.py`) — sqlglot AST ↔ IR conversion + emission
  - Transformation passes (`transformer.py`) — function, type, and syntax normalization
  - Transpiler orchestrator (`transpiler.py`) — parse → transform → emit pipeline
  - Dialect registry (`registry.py`) — entry-point auto-discovery + manual registration
  - Error hierarchy (`errors.py`)
- [x] **Dialect plugins** — T-SQL, Oracle, PostgreSQL, MySQL
- [x] **CLI** — `unique transpile`, `unique validate`, `unique dialects`
- [x] **REST API** — FastAPI with `/api/v1/transpile`, `/api/v1/validate`, `/api/v1/dialects`, `/health`
- [x] **Test suite** — 332 tests (unit + integration), all passing
- [x] **Docker** — `Dockerfile`, `Dockerfile.dev`, `docker-compose.yaml`
- [x] **CI/CD** — GitHub Actions (`lint`, `typecheck`, `test`, `docker`)
- [x] **README.md**

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
| integration (cross-dialect) | 214 |
| **Total** | **332** |

### Known Limitations (MVP)

- Procedural SQL (stored procedures, functions, triggers) parses to RawSQL fallback
- MERGE statements have basic support
- Window function frame clauses have limited cross-dialect normalization
- Oracle-specific syntax (CONNECT BY, MODEL) not supported
- T-SQL-specific (CROSS APPLY, OUTER APPLY) converted with comments

### Next Steps

- [ ] Expand procedural SQL support (IF/ELSE, WHILE, variables, BEGIN/END)
- [ ] Add MERGE statement full cross-dialect support
- [ ] Implement window function frame clause normalization
- [ ] Add property-based testing with Hypothesis
- [ ] Improve error messages with source location tracking
- [ ] Add SQL formatting/pretty-print options
- [ ] Publish to PyPI
