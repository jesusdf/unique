# Unique — Interfaces

Unique exposes the same transpilation engine through four interfaces: a
command-line tool, a Python library, a REST API, and a browser UI. Pick
whichever fits your workflow.

## CLI

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

The full command surface (flags, stdin/stdout usage) is documented in
[02-architecture.md](02-architecture.md#33-cli-srcuniquecli).

## Python API

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

`transpile()` returns a result object carrying the translated `sql` plus any
warnings raised for constructs that could not be translated faithfully (these
are also emitted inline as `/* UNIQUE: ... */` comments — see the README's
value-add section).

## REST API

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

## Web UI

Once the API server is running, open the browser-based interface at the root
URL (e.g. <http://localhost:8000/>). It provides:

- two side-by-side editors with SQL syntax highlighting (CodeMirror, embedded
  in the page — no external CDN, so it works behind an offline reverse proxy);
- automatic source-engine detection as you type (you can still override it),
  which also switches the highlighting dialect;
- a file section to upload a `.sql` file and download it translated, with an
  "Auto-detect" option for the source engine.

### Rebuilding the UI

The page is built from `web/src/index.template.html` plus the vendored
CodeMirror assets in `web/vendor/`. After editing either, regenerate the
self-contained `src/unique/api/static/index.html` with:

```bash
python web/build.py
```

The output is fully self-contained (no external resource loads), which is what
lets it run behind an offline reverse proxy.

## Database connection (`--db-url` / `db_url`)

Some T-SQL/PL-SQL constructs can only be translated faithfully if the actual
column types are known — the main example being Oracle `%TYPE`/`%ROWTYPE`
references (e.g. `v_name H_TABLE.NAME%TYPE`). Without a connection, Unique
cannot resolve what `H_TABLE.NAME` actually is, so it emits a permissive
carrier type and records the original in a `/* UNIQUE: … */` comment plus a
warning. Provide a connection string and Unique resolves the real type
instead.

The connection is **optional** and used only for metadata lookups; ordinary
transpilation needs no database.

- **CLI:** `--db-url "<url>"`
- **Python:** `transpile(sql, source, target, db_url="<url>")`, or
  `TranspileOptions(db_url="<url>")`

### Connection URL format

`scheme://user:password@host:port/database_or_service`

The scheme selects the engine to connect to (independent of the `--from`/`--to`
dialects):

| Engine | Scheme(s) | Driver required | Example |
| --- | --- | --- | --- |
| SQL Server | `mssql`, `sqlserver` | `pyodbc` | `mssql://user:pass@localhost:1433/mydb` |
| Oracle | `oracle` | `oracledb` | `oracle://user:pass@localhost:1521/FREEPDB1` |
| PostgreSQL | `postgresql`, `postgres` | `psycopg` | `postgresql://user:pass@localhost:5432/mydb` |
| MySQL | `mysql` | `mysql-connector-python` | `mysql://user:pass@localhost:3306/mydb` |

The relevant driver must be installed (they are not hard dependencies of
Unique); if it is missing, Unique raises an `ImportError` naming the driver.

### Examples

```bash
# Oracle: resolve %TYPE/%ROWTYPE against a live schema while converting to MySQL
unique transpile -s oracle -t mysql -f pkg.sql --db-url \
  "oracle://app:secret@db.internal:1521/FREEPDB1"

# SQL Server source, connecting to SQL Server for metadata
unique transpile -s tsql -t postgresql -f proc.sql --db-url \
  "mssql://sa:Str0ng!Pass@localhost:1433/sales"

# PostgreSQL
unique transpile -s postgresql -t mysql -f funcs.sql --db-url \
  "postgresql://app:secret@localhost:5432/analytics"

# MySQL
unique transpile -s mysql -t tsql -f routines.sql --db-url \
  "mysql://app:secret@localhost:3306/shop"
```

```python
from unique.core import transpile

result = transpile(
    open("pkg.sql").read(),
    source="oracle",
    target="mysql",
    db_url="oracle://app:secret@db.internal:1521/FREEPDB1",
)
print(result.sql)
for w in result.warnings:
    print("warning:", w)
```
