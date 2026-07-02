# 04 — API, security & operations

## REST API (`src/unique/api/app.py`)

### A1. CPU-bound work inside `async def` handlers (blocks the event loop)

`transpile_sql`, `transpile_file` and `validate_sql` are declared `async def`
but call the fully synchronous, CPU-bound `Transpiler.transpile` directly.
Under uvicorn this **blocks the event loop**: while one large script is being
transpiled, every other request (including `/health`, so the Docker
healthcheck can flap) is stalled.

Fix: declare the endpoints as plain `def` (FastAPI then runs them in its
threadpool) or wrap the call in `run_in_executor`. One-line change per
endpoint.

### A2. No input size limits (DoS surface)

Neither `/api/v1/transpile` (JSON body) nor `/api/v1/transpile/file`
(upload, `await file.read()` into memory) enforces a size cap. Combined with
A1, a single multi-MB script freezes the service. Add a `max_length` on the
`sql` field, a cap on the upload size, and ideally a transpilation timeout.

### A3. Client-supplied `db_url` is an SSRF / credential-relay primitive

When `UNIQUE_ALLOW_DB_CONNECTION=1`, any client of the HTTP API can make the
server open TCP connections to **arbitrary hosts/ports with arbitrary
credentials** (`oracle://user:pass@internal-host:1521/...`). In any deployment
where the container can reach networks the caller cannot, this is a classic
SSRF pivot, and it also invites users to funnel production credentials
through a shared service.

The off-by-default env gate is good, but when enabled there is no restriction
at all. Recommendations, strongest first:

1. Configure allowed DSNs **server-side** (env/config file) and let the API
   reference them by name (`db: "hr-prod-readonly"`), never accept raw URLs.
2. If raw URLs must be accepted, add an allowlist of hosts/schemes and block
   private ranges by default.
3. Never echo the URL back in error messages (see A4).

### A4. Error detail leakage

The catch-all `except Exception as e: HTTPException(500, f"Transpilation
failed: {e}")` forwards internal exception text (paths, driver errors —
potentially including the `db_url`) to the client. Log the full exception
server-side; return a generic message plus a correlation id.

### A5. Silent `latin-1` decode fallback

`transpile_file` falls back to `latin-1` on any `UnicodeDecodeError`, which
never fails and silently mojibakes UTF-16 or cp1252 scripts (SQL Server
tooling frequently emits UTF-16 with BOM). At minimum: detect BOMs
(`utf-8-sig`, `utf-16`), and report the encoding used in the response.

### A6. Missing operational middleware

No CORS configuration (fine while UI and API are same-origin — but then an
explicit restrictive default documents the intent), no rate limiting, no
request logging/metrics. Acceptable for a lab tool; document that a reverse
proxy is expected to provide these in real deployments.

## CLI

- `-o/--output` writes files without any overwrite guard; fine, but note the
  broad `except Exception` around transpile hides tracebacks — add
  `--verbose` to re-raise.
- README/docs advertise flags the CLI does not have — detailed in doc 05.

## Docker

Good: multi-stage build, non-root `appuser`, healthcheck, wheel install,
`UNIQUE_ALLOW_DB_CONNECTION=0` default, sensible dev profile in compose.

Improvements:

- Pin the base image by digest (`python:3.12-slim@sha256:…`) for
  reproducible, tamper-evident builds; the wheel deps are already pinned via
  `sqlglot==`, but the rest float (`fastapi>=0.110`) — consider a lock/
  constraints file for the image.
- The healthcheck spawning a Python interpreter every 30s is heavy-ish;
  `python -c` is fine, but note it will also be blocked by A1 under load.
- `docker-compose.test.yaml` starts four database engines; document the RAM
  expectation (SQL Server + Oracle ≈ 4–6 GB) so contributors aren't surprised.

## CI (`.github/workflows/ci.yaml`)

Strengths: lint/type/test/live-syntax as gating jobs; Docker publish only on
tags after the full gate; live validation against all four real engines is
well beyond typical rigor; the Oracle startup handling is pragmatic and
documented.

Observations:

- The FE harness is `continue-on-error: true` with a written flip condition —
  good discipline; keep the reminder in `docs/TODO.md` so it doesn't linger.
- Several `continue-on-error`/`|| true` steps around SQL Server/ODBC mean a
  broken driver install silently downgrades the job to "checks will skip" —
  the job stays green while validating less. Consider a final step that
  *fails* if fewer than N engines were actually exercised.
- Coverage is uploaded as an artifact but no threshold is enforced; given doc
  02, enforce assertion quality (mutation job) rather than a coverage %.
- Duplicated log-capture shell blocks (also noted in doc 03).

## Credential hygiene (outside the repo, but important)

The working notes shared alongside this project (`repository.txt`) contain a
**live GitHub PAT in plaintext**. Nothing inside the repo leaks secrets (CI
uses `secrets.*` correctly; test passwords are throwaway), but that PAT
should be treated as exposed: **rotate it**, scope the replacement to this
repo with the minimum permissions, and prefer short expiry. Never store PATs
in files that travel with project documentation.
