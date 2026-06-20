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

## CI Pipeline and Diagnosing Failures

CI is defined in `.github/workflows/ci.yaml` with these jobs: **Lint &
Format**, **Type Check**, **Test** (Python 3.11 + 3.12), **Live Metadata
Tests** (Postgres + MySQL service containers), **Live Syntax Validation**
(Postgres + MySQL + SQL Server, validates transpiler output against the real
engines' grammar), and **Docker Build & Push** (only on `main`/tags).

### Checking CI status from the API

`api.github.com` is reachable; query runs and jobs directly:

```bash
PAT=...   # token with actions:read
# Latest run id
RUN_ID=$(curl -s -H "Authorization: token $PAT" \
  "https://api.github.com/repos/jesusdf/unique/actions/runs?per_page=1" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['workflow_runs'][0]['id'])")
# Per-job status + which STEP failed (this is the key to fast diagnosis)
curl -s -H "Authorization: token $PAT" \
  "https://api.github.com/repos/jesusdf/unique/actions/runs/$RUN_ID/jobs" \
  | python3 -c "
import sys, json
for j in json.load(sys.stdin)['jobs']:
    print(j['name'], j['status'], j['conclusion'])
    for s in j.get('steps', []):
        print('  ', s['number'], s['conclusion'], s['name'])
"
```

### Getting failure details WITHOUT the raw logs

**Important environment constraint:** the raw job-log download
(`/actions/jobs/{id}/logs`) 302-redirects to an Azure blob
(`*.blob.core.windows.net`) that is **not in this sandbox's network
allowlist**, so the log text cannot be fetched here. Neither can external
proxies (jina, allorigins, etc.) — all blocked. Do **not** waste time
retrying the blob URL.

Instead, get actionable detail from endpoints served by `api.github.com`:

1. **Step list** (above) — tells you *which step* failed. pytest exit code 2
   means a collection/setup error, not an assertion failure (which is exit 1).
2. **Annotations API** — surfaces the error summary and warnings:

   ```bash
   JOB_ID=...   # the failing job's id
   curl -s -H "Authorization: token $PAT" \
     "https://api.github.com/repos/jesusdf/unique/check-runs/$JOB_ID/annotations" \
     | python3 -c "import sys,json; [print(a['annotation_level'],'-',a['message'][:300]) for a in json.load(sys.stdin)]"
   ```

If full logs are genuinely needed, ask the user to read them in the GitHub
Actions web UI — that is faster than fighting the egress restriction.

### Validating output against real engines

The Live Syntax Validation job (and `tests/integration/test_live_syntax.py`)
checks transpiled SQL against the real target engine instead of our own
assumptions — the robust way to catch dialect violations (e.g. T-SQL
`CREATE TABLE IF NOT EXISTS`, stray `;` before `GO`). SQL Server uses
`SET PARSEONLY ON` (syntax check without compiling/resolving names);
PostgreSQL/MySQL run inside a rolled-back transaction. Run locally with:

```bash
docker compose -f docker-compose.test.yaml up -d   # postgres, mysql, mssql
UNIQUE_TEST_MSSQL_URL="mssql://sa:Unique_Strong!Pass1@localhost:1433/master" \
UNIQUE_TEST_PG_URL="postgresql://unique:unique@localhost:5433/unique" \
UNIQUE_TEST_MYSQL_URL="mysql://unique:unique@localhost:3307/unique" \
pytest tests/integration/test_live_syntax.py -v
```

The Microsoft ODBC Driver 18 (needed by `pyodbc` for SQL Server) must match
the runner's Ubuntu version; the CI step detects `VERSION_ID` and falls back
to 22.04, and points the apt source at the keyring it installs (`signed-by`).

## Dialect-Idiom Gotchas (T-SQL especially)

When emitting T-SQL, watch for non-idiomatic or invalid output (validated by
the live job):

- **No `CREATE TABLE IF NOT EXISTS`** — emit an `IF OBJECT_ID(N'schema.table',
  N'U') IS NULL` guard before the `CREATE TABLE` instead.
- **`GO`, not `;`** — T-SQL separates batches with `GO`; statements are not
  terminated with `;` (only required in specific cases such as before a CTE's
  `WITH`). Never emit `;` immediately followed by `GO`. The terminator logic
  lives in `Transpiler._ensure_terminated`, `converter.emit_sql`, and the
  `Script` node emitter — all branch on `dialect == "tsql"`.
- **No `GO` after a comment** — comment-only batches/output are glued to the
  following statement with a newline, never followed by `GO`/`;`. See
  `Transpiler._join_parts` and `_is_comment_only`.
