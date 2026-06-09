---
name: unique-development-workflow
description: >
  Development workflow skill for the Unique SQL Transpiler. Use this skill
  when implementing new features, adding dialect support, writing tests, or
  debugging transpilation issues. Covers TDD methodology, how to add new
  AST nodes, how to extend a dialect, and testing patterns.
---

# Unique — Development Workflow

## TDD Cycle

Every feature follows Red → Green → Refactor:

1. **Red** — Write a test that describes the desired behavior. Run it, confirm it fails.
2. **Green** — Write the minimum code to make the test pass.
3. **Refactor** — Clean up while keeping tests green.

### Test Structure

```
tests/
├── unit/
│   ├── core/
│   │   ├── test_ast_nodes.py         # IR node construction & equality
│   │   ├── test_transpiler.py        # Orchestration logic
│   │   └── test_registry.py          # Plugin discovery
│   ├── dialects/
│   │   ├── test_tsql_parser.py       # T-SQL → IR
│   │   ├── test_tsql_emitter.py      # IR → T-SQL
│   │   ├── test_oracle_parser.py
│   │   ├── test_oracle_emitter.py
│   │   ├── test_postgresql_parser.py
│   │   ├── test_postgresql_emitter.py
│   │   ├── test_mysql_parser.py
│   │   └── test_mysql_emitter.py
├── integration/
│   ├── test_tsql_to_postgresql.py    # Full transpilation
│   ├── test_oracle_to_mysql.py
│   └── ...                           # All 12 direction combos
└── fixtures/
    ├── select_basic.sql
    ├── join_complex.sql
    ├── stored_procedure.sql
    └── ...
```

### Test Naming Convention

```python
def test_<what>_<condition>_<expected>():
    """Example: test_select_with_top_emits_limit_in_postgresql"""
```

### Fixture-Driven Integration Tests

```python
@pytest.mark.parametrize("fixture", load_fixtures("select"))
def test_transpile_select(fixture):
    result = transpile(fixture.source_sql, source="tsql", target="postgresql")
    assert result == fixture.expected_sql
```

## Adding a New AST Node

1. Define the node in `src/unique/core/ast_nodes.py`:
   ```python
   @dataclass(frozen=True)
   class MergeStatement(ASTNode):
       target: TableRef
       source: TableRef | Subquery
       on_condition: Expression
       when_matched: list[Action]
       when_not_matched: list[Action]
   ```
2. Write unit tests for construction and equality.
3. Add parsing support in each dialect's parser.
4. Add emission support in each dialect's emitter.
5. Write integration tests for transpilation across dialects.

## Adding a New Dialect

1. Create `src/unique/dialects/<name>/`:
   - `__init__.py` with `Dialect` subclass
   - `parser.py` — Implements `parse(sql) -> list[ASTNode]`
   - `emitter.py` — Implements `emit(nodes) -> str`
2. Register in `src/unique/core/registry.py` (auto-discovery via entry points).
3. Mirror test structure in `tests/unit/dialects/`.
4. Add integration test files for all transpilation directions.

## Running Tests

```bash
# All tests
pytest

# Specific dialect
pytest tests/unit/dialects/test_tsql_parser.py

# Integration only
pytest tests/integration/

# With coverage
pytest --cov=unique --cov-report=html

# Single test
pytest -k "test_select_with_top"
```

## Code Quality

```bash
# Formatting
black src/ tests/
isort src/ tests/

# Linting
ruff check src/ tests/

# Type checking
mypy src/
```

## Common Patterns

### Transpiler Orchestration

```python
def transpile(sql: str, source: str, target: str) -> str:
    source_dialect = registry.get(source)
    target_dialect = registry.get(target)
    
    ast_nodes = source_dialect.parse(sql)
    transformed = transform(ast_nodes, source, target)
    return target_dialect.emit(transformed)
```

### Transform Layer

Between parsing and emitting, a transform step normalizes dialect-specific
constructs into portable equivalents:

- `TOP n` → `LIMIT n`
- `ISNULL()` → `COALESCE()`
- `GETDATE()` → `NOW()` / `CURRENT_TIMESTAMP`
- `NVL()` → `COALESCE()`
- String concatenation: `+` ↔ `||` ↔ `CONCAT()`

### Error Handling

```python
class UnsupportedFeatureError(TranspileError):
    """Raised when a construct cannot be translated to the target dialect."""
    
    def __init__(self, feature: str, source: str, target: str):
        super().__init__(
            f"Cannot transpile '{feature}' from {source} to {target}"
        )
```

Unsupported features are logged with context (line number, construct) and
optionally left as comments in the output SQL.
