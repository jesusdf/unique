# Unique — Interfaces

Unique exposes the same transpilation engine through four interfaces: a
command-line tool, a Python library, a REST API, and a browser UI. Pick
whichever fits your workflow.

## CLI

```bash
# Transpile a file
unique transpile input.sql --from tsql --to postgresql -o output.sql

# Transpile inline SQL
unique transpile query.sql --from tsql --to mysql  # input is a file path

# Migrate off SQLite (import-only: SQLite is a valid --from, never a --to)
unique transpile app.db.sql --from sqlite --to postgresql -o output.sql

# List available dialects
unique dialects

# Validate a script's syntax (errors are located by line)
unique validate script.sql -d postgresql

# Structural-similarity of two scripts (e.g. a migration audit: how close is a
# hand-migrated PL/SQL to the original T-SQL?). Dialects auto-detect if omitted.
unique compare original.sql migrated.sql --dialect-a tsql --dialect-b oracle
unique compare a.sql b.sql --json          # machine-readable report
```

`transpile` **validates the source syntax first** and refuses a malformed script
(exit 1), listing each error by line — for example a `CREATE PROCEDURE` with no
preceding `GO` (the batch it must start). Pass `--ignore-syntax-errors` to
transpile anyway. `validate` reports the same located errors without emitting.

`compare` reports a **structural similarity** percentage plus a per-dimension
breakdown (DML structure, predicates, control flow, tree match) — it is *not* a
probability of semantic equivalence (see
[03-unsupported.md](03-unsupported.md#338-structural-similarity-not-equivalence)).
Both scripts are normalized through the transpiler to a PostgreSQL pivot, so
dialect idioms (`ISNULL`/`NVL`/`COALESCE`) collapse before comparison. An
undetectable dialect or an untranspilable input exits `2` (distinct from a
low-similarity run).

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

```python
from unique.core.similarity import compare

report = compare(sql_original, sql_migrated, dialect_a="tsql", dialect_b="oracle")
print(report.overall)              # e.g. 82.4  (structural similarity, 0–100)
print(report.dimensions)           # {'dml_structure': …, 'predicates': …,
                                   #  'control_flow': …, 'tree_match': …}
print(report.unmatched_a, report.unmatched_b)   # statements with no counterpart
```

`compare(sql_a, sql_b, dialect_a=None, dialect_b=None)` returns a
`SimilarityReport` (overall score, per-dimension scores, per-statement pairs,
unmatched counts, and any transpiler warnings surfaced during normalization).
Dialects default to auto-detection; `report.detected_a`/`detected_b` record
whether each was detected. It raises `ValueError` naming the offending input if
a dialect cannot be detected or the input cannot be transpiled.

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

# Validate source syntax (locates errors by line)
curl -X POST http://localhost:8000/api/v1/validate \
  -H "Content-Type: application/json" \
  -d '{"sql": "SELECT * FROM (SELECT 1", "dialect": "tsql"}'

# Translate a file (use source=auto to auto-detect), saving the result
curl -X POST http://localhost:8000/api/v1/transpile/file \
  -F source=auto -F target=postgresql -F file=@script.sql -OJ
```

`/api/v1/transpile` **rejects a malformed source with `422`**, returning the
located errors (`{error, message, issues: [{line, column, message, snippet}]}`);
set `"ignore_syntax_errors": true` in the body to transpile anyway. A `source` of
`auto` is detected before validating. `/api/v1/validate` returns the same
structured issues (`valid: false` with `issues`).

## Web UI

Once the API server is running, open the browser-based interface at the root
URL (e.g. <http://localhost:8000/>). It provides:

- two side-by-side editors with SQL syntax highlighting (CodeMirror, embedded
  in the page — no external CDN, so it works behind an offline reverse proxy);
- automatic source-engine detection as you type (you can still override it),
  which also switches the highlighting dialect;
- **live source-syntax validation**: while the script has syntax errors the
  Translate button is disabled and the located errors are listed, so a malformed
  script is never silently transpiled to garbage;
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
- **REST API:** databases are configured **server-side** as named DSNs and
  referenced by name — never as raw URLs (audit 2026-07-02, A3: a raw URL
  from a client is an SSRF/credential-relay primitive on a shared service):

  ```bash
  # Server: enable connections and configure the allowed DSNs by name
  export UNIQUE_ALLOW_DB_CONNECTION=1
  export UNIQUE_DSN_HR_READONLY="oracle://app:secret@db.internal:1521/FREEPDB1"

  # Client: reference the DSN by name (lowercase, '_' and '-' equivalent)
  curl -X POST http://localhost:8000/api/v1/transpile \
    -H "Content-Type: application/json" \
    -d '{"sql": "...", "source": "oracle", "target": "mysql", "db": "hr-readonly"}'
  ```

  `GET /api/v1/info` lists the configured names (`db_names`, never the URLs)
  so the UI can offer them. A raw `db_url` in the request body is only
  honored when the deployment *additionally* sets
  `UNIQUE_ALLOW_RAW_DB_URL=1`; this is discouraged outside single-user lab
  setups.

- **Web UI:** when connections are enabled, the page shows a *Database
  connection* panel driven by `GET /api/v1/info`: the server-side DSNs appear
  in a combo (referenced by name — the URL never reaches the browser). If the
  deployment also allows raw URLs (`UNIQUE_ALLOW_RAW_DB_URL=1`), a structured
  builder appears instead of a bare URL box: an engine combo (SQL Server /
  Oracle / PostgreSQL / MySQL), host, port (pre-filled with the engine's
  default), database/service, user and password; the UI assembles the
  connection URL from those fields. A selected named DSN always takes
  precedence over the builder.

### Connection URL format

`scheme://user:password@host:port/database_or_service`

The scheme selects the engine to connect to (independent of the `--from`/`--to`
dialects):

| Engine | Scheme(s) | Driver required | Example |
| --- | --- | --- | --- |
| SQL Server | `mssql`, `sqlserver` | `pymssql` (preferred) or `pyodbc` | `mssql://user:pass@localhost:1433/mydb` |
| Oracle | `oracle` | `oracledb` | `oracle://user:pass@localhost:1521/FREEPDB1` |
| PostgreSQL | `postgresql`, `postgres` | `psycopg` | `postgresql://user:pass@localhost:5432/mydb` |
| MySQL | `mysql` | `mysql-connector-python` | `mysql://user:pass@localhost:3306/mydb` |
| SQLite | `sqlite` | `sqlite3` (stdlib — always available) | `sqlite:///path/to/file.db` |

The relevant driver must be installed (they are not hard dependencies of
Unique); if it is missing, Unique raises an `ImportError` naming the driver.
SQL Server prefers `pymssql` (its wheel bundles FreeTDS — no system ODBC driver
needed) and falls back to `pyodbc`.

The metadata source is **independent of the `--from`/`--to` dialects**: because
the same schema typically exists on every engine during a migration, an Oracle
`%TYPE`/`%ROWTYPE` source can be resolved through a `--db-url` pointing at *any*
of the five engines above (including a SQLite file). A `%TYPE` reference is
replaced by the concrete column type; a `%ROWTYPE` reference is validated against
the connected schema and its columns are recorded in the accompanying
`/* UNIQUE: … */` comment and warning (targets without a record type keep it as a
carrier). This is covered end-to-end by
`tests/integration/test_metadata_live.py::TestOracleTypeResolutionAcrossEngines`.

### Examples

```bash
# Oracle: resolve %TYPE/%ROWTYPE against a live schema while converting to MySQL
unique transpile pkg.sql --from oracle --to mysql --db-url \
  "oracle://app:secret@db.internal:1521/FREEPDB1"

# SQL Server source, connecting to SQL Server for metadata
unique transpile proc.sql --from tsql --to postgresql --db-url \
  "mssql://sa:Str0ng!Pass@localhost:1433/sales"

# PostgreSQL
unique transpile funcs.sql --from postgresql --to mysql --db-url \
  "postgresql://app:secret@localhost:5432/analytics"

# MySQL
unique transpile routines.sql --from mysql --to tsql --db-url \
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
