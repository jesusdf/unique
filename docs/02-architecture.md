# Unique — Architecture Document

## 1. Architectural Approach Evaluation

Before settling on a design, three approaches were evaluated:

### Option A: Regex / String Replacement

**How it works:** Direct text-level pattern matching and replacement (e.g.,
replace `GETDATE()` with `NOW()`, replace `TOP n` with `LIMIT n`).

| Pros | Cons |
|------|------|
| Simple to implement for trivial cases | Extremely brittle with nested or complex SQL |
| No parsing overhead | Cannot handle context-dependent transformations |
| Easy to understand | Combinatorial explosion for multi-dialect support |
| | Impossible for procedural SQL (IF/ELSE, variables) |

**Verdict:** Rejected. Unreliable for anything beyond the simplest queries.

### Option B: Direct Source-to-Source Transpilation

**How it works:** Parse source dialect AST → transform directly to target
dialect AST → emit. Each pair of dialects has its own transformation module.

| Pros | Cons |
|------|------|
| Can be highly optimized per pair | N×(N-1) transformation modules required |
| No intermediate representation overhead | Adding a new dialect requires N new modules |
| | Massive duplication of logic |
| | Unmaintainable at scale |

**Verdict:** Rejected. With 4 dialects, this means 12 transformation modules.
Adding a fifth dialect would require 8 more. Not scalable.

### Option C: AST with Intermediate Representation (Chosen)

**How it works:** Parse source SQL → normalize into an engine-agnostic
Intermediate Representation (IR) → emit as target SQL.

| Pros | Cons |
|------|------|
| Each dialect has only a parser + emitter (2N modules) | IR design is complex upfront |
| Adding a new dialect = 1 parser + 1 emitter | Some constructs may lose fidelity in IR |
| Centralized transformation logic | Two-step process adds latency |
| Highest reliability for complex SQL | |
| Most maintainable long-term | |

**Verdict: Selected.** This approach provides the best balance of reliability,
maintainability, and extensibility. The IR acts as a universal language that
all dialects translate to and from.

---

## 2. High-Level Architecture

```
┌─────────────┐     ┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│ Source SQL   │────▶│   Parser    │────▶│  IR (AST)    │────▶│   Emitter   │────▶ Target SQL
│ (T-SQL)     │     │ (T-SQL      │     │  (Universal) │     │ (PostgreSQL │
│             │     │  Dialect)   │     │              │     │  Dialect)   │
└─────────────┘     └─────────────┘     └──────────────┘     └─────────────┘
                                              │
                                              ▼
                                     ┌─────────────────┐
                                     │  Transformer    │
                                     │  (Normalization │
                                     │   + Adaptation) │
                                     └─────────────────┘
```

### Pipeline Stages

1. **Lexing/Parsing** — The source dialect plugin parses raw SQL text into IR
   nodes. This leverages `sqlglot` for the heavy lifting, extended with custom
   handling for procedural constructs.

2. **Transformation** — A series of transformation passes normalize the IR:
   - Function normalization (ISNULL → COALESCE, NVL → COALESCE)
   - Syntax normalization (TOP → LIMIT, (+) joins → ANSI)
   - Type mapping (VARCHAR2 → VARCHAR, NUMBER → NUMERIC)
   - Procedural adaptation (TRY/CATCH → EXCEPTION blocks)

3. **Emission** — The target dialect plugin takes the normalized IR and produces
   syntactically correct SQL for the target engine.

---

## 3. Component Design

### 3.1 Core Module (`src/unique/core/`)

```
core/
├── __init__.py
├── ast_nodes.py           # IR node type hierarchy
├── transpiler/            # Orchestrator (package: _core.py + _text_rules.py)
├── converter/             # sqlglot-backed DML/DDL path (package:
│                          #   _base/harvest/convert/emit submodules)
├── batch_splitter.py      # Dialect-aware batch splitting + classification
├── mappings.py            # Shared dialect knowledge (both pipelines)
├── transformer.py         # DML/DDL transform passes
├── output_gate.py         # M1 honesty gate (never ship known-invalid output)
├── sql_split.py           # Shared string/comment-aware statement splitter
├── validation.py          # Source-syntax validation
├── detection.py           # Source-dialect auto-detection
├── builtins.py / dialect.py / live_validate.py / metadata.py
├── registry.py            # Plugin discovery & registration
├── errors.py              # Exception hierarchy
└── procedural/            # The procedural engine (the value-add over sqlglot)
    ├── lexer.py           # Engine-agnostic tokenizer
    ├── parser/            # Source-family parser (package: _base.py + _tsql.py/_plsql.py)
    ├── emitter/           # Per-target emitter plugins
    │   ├── __init__.py    #   factory + registry, re-exports ProceduralEmitter
    │   ├── base.py        #   ProceduralEmitter: shared logic + overridable hooks
    │   ├── tsql.py        #   TSqlEmitter
    │   ├── oracle.py      #   OracleEmitter
    │   ├── postgresql.py  #   PostgresEmitter
    │   └── mysql.py       #   MySqlEmitter
    └── transformer/       # Per-target transformer plugins (same shape)
        ├── __init__.py
        ├── base.py        #   ProceduralTransformer: shared + source/pair logic
        ├── tsql.py / oracle.py / postgresql.py / mysql.py
```

#### The procedural engine is itself plugin-structured

The procedural engine (lexer → parser → transformer → emitter) is what Unique
adds on top of sqlglot, and it follows the same per-engine plugin philosophy as
the dialect plugins under `src/unique/dialects/`:

- **Emitter** — output depends only on the *target* dialect, so
  `ProceduralEmitter` is a base class holding the shared structure, and each
  target is a subclass (`TSqlEmitter`, …) that overrides only the methods that
  differ (e.g. `_emit_try_catch`, `_returns_clause`, `_assignment_form`).
  `ProceduralEmitter(dialect)` is a factory (via `__new__`) that returns the
  registered subclass. The base carries **no** `if dialect == …` dispatch.
- **Transformer** — a transform is a *source → target* operation, so the
  pattern is the same per *target* subclass, but pair-dependent logic (e.g.
  variable naming `@x`→`V_X`/`v_x`/`@x`) and source-only logic stay in the base
  parameterized by `self._source`; only genuinely target-only decisions are
  overridden in the subclass.
- **Parser** — depends on the *source* dialect, of which there are only two
  syntactic families (T-SQL and PL/SQL), so it is a single class with the
  family distinction named by `_is_tsql_source()` / `_parse_routine_body()`
  rather than a subclass hierarchy.
- **Lexer** — engine-agnostic; not specialized per dialect.

Adding a new engine means adding one emitter module and one transformer module
(plus a one-line import in each package `__init__`), without editing the shared
core logic — the open/closed shape the architecture promises.

#### ast_nodes.py — Intermediate Representation

The IR uses a hierarchy of immutable dataclasses:

```
ASTNode (base)
├── Statement
│   ├── SelectStatement
│   ├── InsertStatement
│   ├── UpdateStatement
│   ├── DeleteStatement
│   ├── MergeStatement
│   ├── CreateTableStatement
│   ├── AlterTableStatement
│   ├── DropStatement
│   ├── CreateIndexStatement
│   ├── CreateViewStatement
│   ├── CreateProcedureStatement
│   ├── CreateFunctionStatement
│   ├── CreateTriggerStatement
│   ├── DeclareStatement
│   ├── SetVariableStatement
│   ├── IfStatement
│   ├── WhileStatement
│   ├── BeginEndBlock
│   ├── TryCatchBlock
│   ├── ReturnStatement
│   ├── RaiseErrorStatement
│   ├── TransactionStatement
│   ├── ExecuteStatement
│   └── RawSQL (passthrough for untranslatable code)
├── Expression
│   ├── ColumnRef
│   ├── TableRef
│   ├── Literal
│   ├── FunctionCall
│   ├── BinaryOp
│   ├── UnaryOp
│   ├── CaseExpression
│   ├── CastExpression
│   ├── SubqueryExpression
│   ├── WindowFunction
│   ├── AggregateFunction
│   └── ParameterRef
├── Clause
│   ├── WhereClause
│   ├── JoinClause
│   ├── OrderByClause
│   ├── GroupByClause
│   ├── HavingClause
│   ├── LimitClause
│   ├── CTEClause
│   └── OutputClause
└── TypeNode
    ├── DataType
    └── ColumnDefinition
```

Key design decisions:
- **Immutable** (`frozen=True` dataclasses) — safer for transformations.
- **Visitor pattern** — Transformers use the visitor pattern to traverse and
  modify the tree without coupling to specific node types.
- **Metadata** — Each node carries optional source location info for
  error reporting.

#### transpiler/ (package) — Orchestrator

```python
class Transpiler:
    def __init__(self, registry: DialectRegistry):
        self.registry = registry
    
    def transpile(
        self,
        sql: str,
        source: str,
        target: str,
        options: TranspileOptions | None = None,
    ) -> TranspileResult:
        source_dialect = self.registry.get(source)
        target_dialect = self.registry.get(target)
        
        # Parse
        ir_nodes = source_dialect.parse(sql)
        
        # Transform
        transformer = Transformer(source, target)
        transformed = transformer.transform(ir_nodes)
        
        # Emit
        output_sql = target_dialect.emit(transformed)
        
        return TranspileResult(
            sql=output_sql,
            warnings=transformer.warnings,
            unsupported=transformer.unsupported,
        )
```

#### output_gate.py — Output validity gate (never ship known-invalid SQL)

Between emission and assembly, every non-comment batch passes an honesty
check (audit 2026-07-08 doc 04, M1): plain DML/DDL output must parse under
sqlglot in the **target** dialect, and all output is scanned (outside
comments/strings) for source-dialect leftovers that can never be valid on the
target (`ROWNUM` off Oracle, `GETDATE()` off T-SQL, backticks off MySQL, a
stray `GO`/`/` terminator, …). A batch that fails degrades to the documented
carrier comment — the **original source batch** preserved — plus a
`validity_gate` warning and an `unsupported` entry, exactly like any other
lossy conversion. The gate is deliberately conservative (procedural units are
exempt from the sqlglot check, which cannot parse them) and it only *detects*;
fixes belong in the AST paths. Duplicate warnings across a script are
aggregated into one entry with an `(xN)` count so the signal stays readable
on large migration dumps.

#### transformer.py — Transformation Engine

Transformations are organized as composable passes:

```python
class TransformPass(ABC):
    @abstractmethod
    def visit(self, node: ASTNode) -> ASTNode:
        ...

class FunctionNormalizer(TransformPass):
    """Maps dialect-specific functions to canonical forms."""

class TypeMapper(TransformPass):
    """Maps dialect-specific types to target types."""

class SyntaxNormalizer(TransformPass):
    """Normalizes syntax variants (TOP→LIMIT, etc.)."""

class ProceduralAdapter(TransformPass):
    """Adapts control flow constructs between dialects."""
```

#### dialect.py — Plugin Interface

```python
class Dialect(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...
    
    @abstractmethod
    def parse(self, sql: str) -> list[ASTNode]: ...
    
    @abstractmethod
    def emit(self, nodes: list[ASTNode]) -> str: ...
    
    @abstractmethod
    def supported_features(self) -> set[str]: ...
```

#### registry.py — Plugin Discovery

```python
class DialectRegistry:
    def __init__(self):
        self._dialects: dict[str, Dialect] = {}
    
    def register(self, dialect: Dialect) -> None:
        self._dialects[dialect.name] = dialect
    
    def get(self, name: str) -> Dialect:
        if name not in self._dialects:
            raise UnknownDialectError(name)
        return self._dialects[name]
    
    def available(self) -> list[str]:
        return list(self._dialects.keys())
    
    @classmethod
    def auto_discover(cls) -> "DialectRegistry":
        """Discover dialects via entry points."""
        registry = cls()
        for entry_point in importlib.metadata.entry_points(
            group="unique.dialects"
        ):
            dialect_class = entry_point.load()
            registry.register(dialect_class())
        return registry
```

### 3.2 Dialect Plugins (`src/unique/dialects/`)

Each dialect plugin is a **single module**:

```
dialects/<name>/
└── __init__.py      # The Dialect subclass (parse/emit delegate to the core)
```

Dialect *knowledge* is deliberately not per-plugin: function/type/literal
mapping tables live centralized in `core/mappings.py` (consumed by both the
DML and the procedural pipelines), and per-target procedural behavior lives in
the plugin modules under `core/procedural/{emitter,transformer}/`.

A dialect may be **source-only** (its `source_only` property returns `True`):
it provides a parser but its `emit()` raises, and the orchestrator rejects it as
a target. **SQLite** (`dialects/sqlite/`) is source-only — it has no procedural
language, so it can be a migration source but never a target; the `/dialects`
API and the web UI expose which dialects are source-only so the target picker can
exclude them.

#### Parser Strategy

Parsers leverage `sqlglot` as the foundation:

```python
class TSQLParser:
    def parse(self, sql: str) -> list[ASTNode]:
        # 1. Use sqlglot to parse into sqlglot AST
        sg_ast = sqlglot.parse(sql, read="tsql")
        
        # 2. Convert sqlglot AST to our IR
        converter = SQLGlotToIRConverter(dialect="tsql")
        ir_nodes = converter.convert(sg_ast)
        
        # 3. Handle constructs sqlglot doesn't cover
        #    (e.g., complex procedural blocks)
        ir_nodes = self._parse_procedural(sql, ir_nodes)
        
        return ir_nodes
```

#### Emitter Strategy

Emitters walk the IR tree and produce formatted SQL:

```python
class PostgreSQLEmitter:
    def emit(self, nodes: list[ASTNode]) -> str:
        parts = []
        for node in nodes:
            parts.append(self._emit_node(node))
        return ";\n\n".join(parts)
    
    def _emit_node(self, node: ASTNode) -> str:
        method = f"_emit_{type(node).__name__}"
        emitter = getattr(self, method, self._emit_unsupported)
        return emitter(node)
```

### 3.3 CLI (`src/unique/cli/`)

```
cli/
├── __init__.py
└── main.py          # Click-based CLI
```

Usage:

```bash
# Single file
unique transpile input.sql --from tsql --to postgresql --output output.sql

# Stdin/stdout
cat input.sql | unique transpile --from oracle --to mysql

# Validate only (parse without emitting)
unique validate input.sql --dialect tsql

# List supported dialects
unique dialects
```

### 3.4 REST API (`src/unique/api/`)

Optional FastAPI-based REST API:

```
api/
├── __init__.py
├── app.py           # FastAPI application: endpoints + Pydantic models
└── static/          # Built web UI served by the app
```

Endpoints:

```
POST /api/v1/transpile
  Body: { "sql": "...", "source": "tsql", "target": "postgresql" }
  Response: { "sql": "...", "warnings": [...], "unsupported": [...] }

GET /api/v1/dialects
  Response: { "dialects": ["tsql", "oracle", "postgresql", "mysql"] }

POST /api/v1/validate
  Body: { "sql": "...", "dialect": "tsql" }
  Response: { "valid": true, "errors": [] }
```

---

## 4. Data Flow

```
Input SQL (source dialect)
       │
       ▼
┌──────────────────────────────┐
│ 1. PARSE                     │
│    Source Dialect Parser      │
│    ┌────────────────────┐    │
│    │ sqlglot parse      │    │
│    │ + procedural parse │    │
│    └────────────────────┘    │
│    Output: list[ASTNode]     │
└──────────────────────────────┘
       │
       ▼
┌──────────────────────────────┐
│ 2. TRANSFORM                 │
│    Sequential passes:        │
│    a) Function normalizer    │
│    b) Type mapper            │
│    c) Syntax normalizer      │
│    d) Procedural adapter     │
│    e) Target-specific tweaks │
│                              │
│    Collects: warnings,       │
│    unsupported features      │
└──────────────────────────────┘
       │
       ▼
┌──────────────────────────────┐
│ 3. EMIT                      │
│    Target Dialect Emitter    │
│    ┌────────────────────┐    │
│    │ Walk IR tree        │    │
│    │ Produce SQL text    │    │
│    │ Format & indent     │    │
│    └────────────────────┘    │
│    Output: formatted SQL     │
└──────────────────────────────┘
       │
       ▼
Output SQL (target dialect)
  + warnings
  + unsupported feature report
```

---

## 5. Technology Stack

| Component | Technology | Justification |
|-----------|-----------|---------------|
| Language | Python 3.12 | Versatility, ecosystem, readability |
| SQL Parsing | sqlglot | Mature, multi-dialect SQL parser/transpiler |
| CLI | Click | Clean CLI framework, composable commands |
| REST API | FastAPI | Modern, async, auto-documented |
| Testing | pytest + hypothesis | TDD with property-based testing |
| Linting | ruff | Fast, comprehensive Python linter |
| Formatting | black + isort | Consistent code style |
| Type Checking | mypy | Static type safety |
| Containers | Docker + docker-compose | Reproducible deployment |
| CI/CD | GitHub Actions | Automated testing and publishing |
| Documentation | Markdown | As specified in requirements |

---

## 6. Plugin System

### Registration via Entry Points

Dialects register themselves via Python entry points in `pyproject.toml`:

```toml
[project.entry-points."unique.dialects"]
tsql = "unique.dialects.tsql:TSQLDialect"
oracle = "unique.dialects.oracle:OracleDialect"
postgresql = "unique.dialects.postgresql:PostgreSQLDialect"
mysql = "unique.dialects.mysql:MySQLDialect"
```

### Adding a Third-Party Dialect

External packages can add dialect support by declaring the same entry point
group in their own `pyproject.toml`:

```toml
# In package "unique-db2"
[project.entry-points."unique.dialects"]
db2 = "unique_db2:DB2Dialect"
```

After installing the package, `unique dialects` will list `db2` alongside
the built-in dialects.

---

## 7. Deployment Architecture

### Docker

```
┌─────────────────────────────────────┐
│ Docker Container                     │
│                                      │
│  ┌──────────┐    ┌──────────┐       │
│  │ CLI      │    │ FastAPI  │       │
│  │ (click)  │    │ (uvicorn)│       │
│  └────┬─────┘    └────┬─────┘       │
│       │               │              │
│       └───────┬───────┘              │
│               │                      │
│       ┌───────▼───────┐             │
│       │  Transpiler   │             │
│       │  Core Engine  │             │
│       └───────────────┘             │
│                                      │
└─────────────────────────────────────┘
```

### docker-compose.yaml

```yaml
services:
  unique-api:
    build: .
    ports:
      - "8000:8000"
    command: uvicorn unique.api.app:app --host 0.0.0.0 --port 8000
    
  unique-cli:
    build: .
    entrypoint: unique
    volumes:
      - ./sql:/sql
```

### GitHub Actions CI/CD

```yaml
jobs:
  test:
    - Checkout
    - Setup Python 3.12
    - Install dependencies
    - Run ruff (lint)
    - Run mypy (type check)
    - Run pytest with coverage
    - Upload coverage report

  build:
    - Build Docker image
    - Push to GitHub Container Registry (on release)
```

---

## 8. Error Handling Strategy

The transpiler produces three categories of output:

1. **Transpiled SQL** — The successfully converted code.
2. **Warnings** — Constructs that were transpiled but may behave slightly
   differently (e.g., date format string differences).
3. **Unsupported blocks** — Constructs that could not be transpiled, returned
   as comments in the output with explanatory messages.

```sql
-- UNIQUE WARNING: Date format specifiers differ between engines.
-- Verify the FORMAT() call output matches your expectations.
SELECT FORMAT(order_date, 'yyyy-MM-dd') FROM orders;

-- UNIQUE UNSUPPORTED: GOTO statements cannot be transpiled to PostgreSQL.
-- Original code:
-- GOTO cleanup_label;
```

---

## 9. Why sqlglot as Foundation

`sqlglot` already provides:
- Parsing for all four target dialects
- AST representation of SQL
- Basic transpilation between dialects
- Function and type mapping

Unique extends `sqlglot` rather than replacing it because:
- Rewriting a SQL parser from scratch is error-prone and unnecessary
- `sqlglot` handles 80%+ of DQL/DML transpilation well
- Unique adds value by handling **procedural SQL** (variables, control flow,
  stored procedures, triggers), **deployment packaging** (Docker, CI/CD),
  and a **plugin architecture** for extensibility
- The IR layer allows Unique to diverge from `sqlglot`'s internal representation
  where needed, particularly for scripting constructs
