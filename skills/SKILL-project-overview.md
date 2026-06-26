---
name: unique-project-overview
description: >
  Overview skill for the Unique SQL Transpiler project. Use this skill whenever
  resuming work on the Unique project after a session break. It provides full
  context on the project goals, architecture decisions, current status, and
  coding conventions so that development can continue seamlessly.
---

# Unique — SQL Transpiler Project Overview

## What is Unique?

Unique is a Python-based SQL transpiler that translates SQL scripts between four
database engines: **SQL Server (T-SQL)**, **Oracle**, **PostgreSQL**, and **MySQL**.
It supports SQL scripting features (variables, control flow, stored procedures)
from versions 2012 onward.

## Core Design Decisions

1. **AST-based transpilation** — SQL is parsed into an engine-agnostic Abstract
   Syntax Tree (Intermediate Representation), then emitted as the target dialect.
   This is more reliable than regex/string replacement and more maintainable than
   direct source-to-source rewriting.

2. **Plugin architecture** — Each database dialect is a self-contained plugin that
   implements a `Dialect` interface with a `Parser` and an `Emitter`. Adding a new
   engine means adding a new plugin without touching the core. The **procedural
   engine follows the same per-engine shape**: its emitter and transformer are
   packages with a `base.py` (shared logic + overridable hooks) and one
   self-registering module per target (`tsql.py`, `oracle.py`, …) selected by a
   factory — no `if dialect == …` dispatch in the base. Adding an engine there is
   one new emitter module + one new transformer module.

3. **Python 3.12** — the single supported/CI version (ecosystem richness,
   readability, tooling). sqlglot does the per-statement parsing; Unique adds an
   autonomous procedural engine for the stored-routine shell sqlglot can't model.

4. **TDD with pytest** — Every feature starts with a failing test. The test suite
   lives in `tests/` and mirrors the `src/` structure.

5. **Clean Code** — Small functions, meaningful names, single responsibility.
   No function longer than ~30 lines. Docstrings on every public symbol.

## Repository Layout

```
unique/
├── docs/                         # Markdown documentation
│   ├── 01-compatibility.md       # SQL feature compatibility matrix
│   ├── 02-architecture.md        # Architecture & design decisions
│   ├── 03-unsupported.md         # Features explicitly out of scope
│   ├── 04-development-guide.md   # How to add features, run tests
│   ├── 05-procedural-engine.md   # The stored-routine pipeline
│   ├── 06-installation.md        # pip / Docker / compose
│   ├── 07-interfaces.md          # CLI / Python / REST / web UI
│   ├── STATUS.md                 # Current project state
│   ├── TODO.md                   # Pending backlog (authoritative)
│   └── DONE.md                   # Archived completed work (why/how)
├── skills/                       # Claude AI continuity skills
├── src/unique/
│   ├── core/
│   │   ├── ast_nodes.py          # IR node definitions
│   │   ├── converter.py          # sqlglot AST ↔ IR conversion + DML/DDL emit
│   │   │                         #   (also hosts the sqlglot DML workarounds:
│   │   │                         #   string +→concat, bitwise ops, fn args)
│   │   ├── transformer.py        # DML/DDL transform passes
│   │   ├── transpiler.py         # Orchestrator: split → classify → route → join
│   │   ├── batch_splitter.py     # Dialect-aware batch splitting + classification
│   │   ├── detection.py          # Source-dialect auto-detection
│   │   ├── metadata.py           # Optional DB connection for %TYPE/%ROWTYPE
│   │   ├── registry.py           # Plugin registry (entry-point discovery)
│   │   ├── errors.py             # Custom exceptions
│   │   └── procedural/           # Autonomous procedural engine
│   │       ├── lexer.py          #   tokenizer for procedural SQL (engine-agnostic)
│   │       ├── parser.py         #   recursive descent (T-SQL + PL/SQL families)
│   │       ├── transformer/      #   per-target transform plugins
│   │       │   ├── base.py       #     shared + source/pair logic, factory, maps
│   │       │   └── {tsql,oracle,postgresql,mysql}.py
│   │       └── emitter/          #   per-target emission plugins
│   │           ├── base.py       #     shared structure + overridable hooks, factory
│   │           └── {tsql,oracle,postgresql,mysql}.py
│   ├── dialects/{tsql,oracle,postgresql,mysql}/   # Dialect plugins (DML/DDL via sqlglot)
│   ├── cli/                      # CLI entry point
│   └── api/                      # REST API (FastAPI) + web UI
├── web/                          # Web UI source + build (build.py)
├── tests/
│   ├── unit/, integration/, property/   # Test suites
│   ├── helpers/                  # live_validation, invariants, functional_equiv
│   ├── fixtures/                 # SQL fixtures (incl. procedures/ for 4 engines)
│   └── functional_equivalence/   # Functional-equivalence test DB (design + assets)
├── Dockerfile / Dockerfile.dev / docker-compose.yaml
├── .github/workflows/ci.yaml
├── pyproject.toml
└── README.md
```

## Dialect Plugin Interface

Every dialect must implement:

```python
class Dialect(ABC):
    name: str                    # e.g. "tsql", "oracle"
    
    @abstractmethod
    def parse(self, sql: str) -> list[ASTNode]:
        """Parse raw SQL into a list of IR nodes."""
    
    @abstractmethod
    def emit(self, nodes: list[ASTNode]) -> str:
        """Emit IR nodes as SQL in this dialect."""
    
    @abstractmethod
    def supported_features(self) -> set[str]:
        """Return set of feature tags this dialect handles."""
```

## Current Status Tracking

When resuming work, check `docs/STATUS.md` for the latest progress tracker.
Each completed feature should have corresponding tests in the test suite.

## Key Libraries

- `sqlglot` — Used as the primary SQL parsing foundation (supports all four
  dialects). We extend it with custom transforms for scripting constructs.
- `click` — CLI framework.
- `fastapi` — Optional REST API.
- `pytest` — Testing.
- `docker` — Deployment.

## Conventions

- All code and documentation in **English**.
- Commit messages: `feat:`, `fix:`, `test:`, `docs:`, `refactor:`.
- Branch naming: `feature/<name>`, `fix/<name>`.
- Every PR must have passing tests and maintain or increase coverage.
