# Unique — Development Guide

## Prerequisites

- Python 3.11+
- Docker & Docker Compose (for containerized deployment)
- Git

## Quick Start

```bash
# Clone the repository
git clone https://github.com/<org>/unique.git
cd unique

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# .venv\Scripts\activate   # Windows

# Install in development mode
pip install -e ".[dev]"

# Run tests
pytest

# Run with coverage
pytest --cov=unique --cov-report=html
```

## Docker

```bash
# Build the image
docker build -t unique .

# Run the CLI
docker run --rm unique transpile --from tsql --to postgresql < input.sql

# Run the API server
docker compose up   # serves API + web UI at http://localhost:8000/
```

## Project Structure

See `docs/02-architecture.md` for the full layout.

## Adding a New Feature

1. **Check the compatibility matrix** (`docs/01-compatibility.md`) to understand
   which engines support the feature.

2. **Write a failing test** in the appropriate test file:
   ```python
   def test_merge_basic_tsql_to_postgresql():
       source = "MERGE INTO target USING source ON ..."
       expected = "INSERT INTO target ... ON CONFLICT ..."
       result = transpile(source, source="tsql", target="postgresql")
       assert result.sql.strip() == expected.strip()
   ```

3. **Implement parsing** — If the construct needs a new AST node, define it
   in `ast_nodes.py` first, then add parsing logic to the source dialect parser.

4. **Implement transformation** — Add or update a transform pass in
   `transformer.py`.

5. **Implement emission** — Add the emit method for the new node in the target
   dialect emitter.

6. **Run tests** and ensure all pass.

7. **Update documentation** if the compatibility matrix or unsupported features
   list needs changes.

## Adding a New Dialect

1. Create the dialect directory:
   ```
   src/unique/dialects/<name>/
   ├── __init__.py
   ├── parser.py
   ├── emitter.py
   ├── functions.py
   ├── types.py
   └── keywords.py
   ```

2. Implement the `Dialect` interface in `__init__.py`.

3. Register via entry point in `pyproject.toml`:
   ```toml
   [project.entry-points."unique.dialects"]
   <name> = "unique.dialects.<name>:MyDialect"
   ```

4. Create corresponding test files.

5. Run the full test suite to verify no regressions.

## Code Style

- **Formatter:** `black` with default settings
- **Import sorting:** `isort` with black-compatible profile
- **Linting:** `ruff` — fix all warnings before committing
- **Type hints:** Required on all public functions; checked by `mypy`
- **Docstrings:** Google style on all public classes and methods
- **Max function length:** ~30 lines; extract helpers if longer

## Commit Convention

```
feat: add MERGE statement support for T-SQL parser
fix: correct DATEADD argument order in Oracle emitter
test: add integration tests for recursive CTE transpilation
docs: update compatibility matrix for window functions
refactor: extract common expression visitor into base class
```

## CI Pipeline

GitHub Actions runs on every push and PR:

1. **Lint** — ruff + black --check + isort --check
2. **Type check** — mypy
3. **Test** — pytest with coverage (minimum 80% required)
4. **Build** — Docker image build verification
