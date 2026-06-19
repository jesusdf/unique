# Unique — SQL Transpiler

Unique is a SQL transpiler that translates scripts between **SQL Server (T-SQL)**, **Oracle**, **PostgreSQL**, and **MySQL**. It parses source SQL into an engine-agnostic intermediate representation (IR), transforms dialect-specific constructs, and emits valid SQL for the target engine.

## Features

- **4 dialects**: SQL Server, Oracle, PostgreSQL, MySQL (2012+ feature coverage)
- **AST-based pipeline**: Parse → Transform → Emit for reliable conversions
- **Plugin architecture**: add new dialects via Python entry points
- **CLI, REST API, and Python library** interfaces
- **112 fully supported features** across DQL, DML, DDL, functions, and procedural SQL

## Quick Start

### Install from source

```bash
pip install -e ".[dev]"
```

### CLI usage

```bash
# Transpile a file
unique transpile -s tsql -t postgresql -f input.sql -o output.sql

# Transpile inline SQL
unique transpile -s tsql -t mysql "SELECT TOP 10 * FROM users"

# List available dialects
unique dialects

# Validate SQL syntax
unique validate -d postgresql "SELECT * FROM users"
```

### Python API

```python
from unique.core import transpile

result = transpile(
    "SELECT TOP 10 * FROM users WHERE active = 1",
    source="tsql",
    target="postgresql",
)
print(result.sql)
# SELECT * FROM users WHERE active = 1 LIMIT 10
```

### Web UI

Once the API server is running, open the browser-based interface at the root
URL (e.g. <http://localhost:8000/>). It provides:

- two side-by-side panes — paste a source script on the left, see the
  translation on the right — with engine selectors above;
- automatic source-engine detection as you type (you can still override it);
- a file section to upload a `.sql` file and download it translated, with an
  "Auto-detect" option for the source engine.

### REST API

```bash
# Start the API server (also serves the web UI at /)
uvicorn unique.api.app:app --host 0.0.0.0 --port 8000

# Transpile via HTTP
curl -X POST http://localhost:8000/api/v1/transpile \
  -H "Content-Type: application/json" \
  -d '{"sql": "SELECT TOP 5 * FROM t", "source": "tsql", "target": "postgresql"}'

# Detect the dialect of a script
curl -X POST http://localhost:8000/api/v1/detect \
  -H "Content-Type: application/json" \
  -d '{"sql": "SELECT TOP 5 * FROM t\nGO"}'

# Translate a file (use source=auto to auto-detect), saving the result
curl -X POST http://localhost:8000/api/v1/transpile/file \
  -F source=auto -F target=postgresql -F file=@script.sql -OJ
```

### Docker

```bash
# Production
docker compose up -d

# Development (with hot-reload)
docker compose --profile dev up
```

## Architecture

Unique uses an **AST with Intermediate Representation** approach:

```
Source SQL → [Parser] → IR Nodes → [Transformer] → IR Nodes → [Emitter] → Target SQL
```

Each dialect is a plugin that implements `parse()` and `emit()` against the shared IR. The transformer applies normalization passes (function mapping, type mapping, syntax normalization) to bridge dialect differences.

See [docs/02-architecture.md](docs/02-architecture.md) for the full design document.

## Project Structure

```
unique/
├── src/unique/
│   ├── core/           # IR nodes, converter, transformer, transpiler
│   ├── dialects/       # Dialect plugins (tsql, oracle, postgresql, mysql)
│   ├── cli/            # Click-based CLI
│   └── api/            # FastAPI REST API
├── tests/
│   ├── unit/           # Unit tests for core and dialects
│   └── integration/    # Cross-dialect transpilation tests
├── docs/               # Documentation (compatibility, architecture, etc.)
├── Dockerfile          # Production image
├── docker-compose.yaml # Compose with dev profile
└── .github/workflows/  # CI pipeline
```

## Development

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest tests/ -v

# Run tests with coverage
pytest tests/ --cov=unique --cov-report=term-missing

# Lint and format
black src/ tests/
isort src/ tests/
ruff check src/ tests/

# Type check
mypy src/unique/ --ignore-missing-imports
```

## Documentation

- [Compatibility Matrix](docs/01-compatibility.md) — full feature support analysis
- [Architecture](docs/02-architecture.md) — design decisions and component overview
- [Unsupported Features](docs/03-unsupported.md) — what's out of scope and why
- [Development Guide](docs/04-development-guide.md) — contributing, adding dialects

## Adding a New Dialect

1. Create `src/unique/dialects/newdb/__init__.py` implementing the `Dialect` interface
2. Register it in `pyproject.toml` under `[project.entry-points."unique.dialects"]`
3. Add tests under `tests/unit/dialects/`
4. Run the full test suite to validate

## License

AGPL-3.0 (see LICENSE for details)
