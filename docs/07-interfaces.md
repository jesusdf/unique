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
