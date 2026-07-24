# 05 — API, security & operations (follow-up audit, 2026-07-24)

Scope: `src/unique/api/`, `web/`, dependency posture, Docker, CI workflows,
and an empirical boot test of the API. Baseline: `audit/2026-07-02/04-api-security-ops.md`
(A1–A6) and `audit/2026-07-08/02-new-findings.md` (N6, N7) plus the open ops
carry-overs. Repo state: v0.30.0, HEAD `69a71cd`.

Method: full read of `src/unique/api/app.py` (510 lines, the whole API),
`web/src/index.template.html`, all four workflow files, both Dockerfiles,
compose files, `constraints.txt`, `pyproject.toml`; plus a live uvicorn boot on
port 8971 (`UNIQUE_MAX_SQL_BYTES=1000`) with 14 curl probes. The server was
killed after the probes.

---

## Verdicts on prior findings

| Prior finding | Verdict | Evidence |
|---|---|---|
| 07-02 A1 — CPU-bound work in `async def` | **FIXED** | All heavy endpoints are plain `def` (threadpool): `transpile_sql` app.py:296–297, `validate_sql` :343–344, `detect_sql_dialect` :396–397, `transpile_file` :407–408. Only trivial `/health` and `/` remain `async`. |
| 07-02 A2 — no input size limits | **FIXED** (residues below, new A2/A4) | `TranspileRequest.sql max_length` app.py:160–164; upload read-cap + 413 app.py:423–428; cap tunable via `UNIQUE_MAX_SQL_BYTES` (default 64 MB) app.py:33. Probes: oversized transpile/validate/detect → 422, oversized file → 413. |
| 07-02 A3 — raw `db_url` SSRF | **FIXED, no regression** | Named-DSN architecture intact: `UNIQUE_DSN_<NAME>` app.py:87–100, double gate `UNIQUE_ALLOW_DB_CONNECTION` + `UNIQUE_ALLOW_RAW_DB_URL` app.py:103–140; URLs never echoed. Probe: `db_url` with connections disabled → 403 with policy message only. |
| 07-02 A4 — error detail leakage | **FIXED** | Generic 500 + `logger.exception` app.py:325–331 and :463–467. Probe of an internal crash (below) returned bare `Internal Server Error`; traceback only in the server log. |
| 07-02 A5 — silent latin-1 fallback | **FIXED** | BOM-aware decode app.py:429–440. Carry-over "report the encoding used" also fixed: `X-Unique-Decoded-As` header app.py:480–482. Probes: latin-1 file → `x-unique-decoded-as: latin-1`, UTF-16 file → `utf-16`. |
| 07-02 A6 — CORS / rate limit / logging | **OPEN (docs half missing)** | Still no middleware (grep: no `CORSMiddleware`/rate limiter anywhere in `src/`), which is the accepted design — but the "a reverse proxy is expected to provide auth/rate-limiting/TLS/body caps" statement is still not written down. `docs/07-interfaces.md:91,111` mentions a reverse proxy only for *offline asset serving*. See new A4. |
| 07-08 **N6** — no size cap on `/validate`, `/detect` | **FIXED** | `ValidateRequest.sql max_length=MAX_SQL_BYTES` app.py:219–223; `DetectRequest.sql` app.py:381–385 (commit `83d6307`). Probes (cap=1000, 2000-char body): both → 422 `string_too_long`. |
| 07-08 **N7** — unsanitized `Content-Disposition` filename | **PARTIALLY FIXED** | Sanitizer added app.py:473–474 (commit `33bd5a4`): quotes/CR-LF/path separators neutralized — probes confirm `ev"il…` → `ev_22il.mysql.sql`, `../../etc/passwd.sql` → `.._.._etc_passwd.mysql.sql`, both 200 with well-formed headers. **But** the regex is Unicode-aware, so non-latin-1 filenames still crash → new **A1**. |
| Carry-over — Docker base digest pin | **FIXED** | `python@sha256:eb43ff12…` in Dockerfile:8 and :18, and Dockerfile.dev:4. |
| Carry-over — CI must fail when engines silently skip | **FIXED** | "Gate — all four engines must be reachable" `.github/workflows/ci.yaml:312–371` hard-fails the `syntax-live` job if any of the four connects fails (found a real bug on 07-10 per the in-file comment). |
| Carry-over — decode encoding not reported | **FIXED** | See A5 row above. |

No new endpoints were added since 07-08 (`git diff` of `app.py` shows no
`@app.` additions; last API commits are `83d6307`, `33bd5a4`, both fix
commits). Endpoint inventory: `POST /api/v1/transpile`, `/api/v1/validate`,
`/api/v1/detect`, `/api/v1/transpile/file`, `GET /api/v1/dialects`,
`/api/v1/info`, `/health`, `/` + `/static`. All POST bodies are capped, all
follow the generic-error and DSN-gating rules.

---

## New findings (A-numbered, this audit)

### A1 (S2). Non-latin-1 upload filename → 500 (N7 residue, empirically confirmed)

`src/unique/api/app.py:474` sanitizes the stem with
`re.sub(r"[^\w.\- ]", "_", stem)`. Python's `\w` is **Unicode-aware**, so any
word character passes through — including CJK, Cyrillic, Greek… Starlette
encodes response headers as latin-1 (`starlette/responses.py:61`), so a
filename like `中文.sql` survives sanitization and then crashes header
encoding.

Empirical probe (server at cap=1000):

```
$ curl -F 'file=@ok.sql;filename=中文.sql' -F source=tsql -F target=mysql .../api/v1/transpile/file
HTTP/1.1 500 Internal Server Error
Internal Server Error
```

Server log: `UnicodeEncodeError: 'latin-1' codec can't encode characters in
position 22-23` raised from `app.py:485` via `starlette/responses.py:61`.
(Nothing leaks to the client — the body is the bare ASGI fallback — but the
request fails.) Uvicorn's access log also mis-records the request as
`"POST /api/v1/transpile/file HTTP/1.1" 200 OK` while the client got 500,
which will mislead anyone debugging from access logs.

A second, milder symptom: latin-1-encodable non-ASCII survives but arrives
mojibaked, because UTF-8 text is emitted through a latin-1 header —
probe `filename=señor.sql` returned
`content-disposition: attachment; filename="se<C3><B1>or.mysql.sql"` (browser
shows `señor…`).

This is a plain-usage failure (Chinese/Japanese/Korean/Cyrillic filenames are
common), not just an edge case, hence S2.

**Fix** (one line + optionally one more): make the character class ASCII-only —
`re.sub(r"[^\w.\- ]", "_", stem, flags=re.ASCII)` (or
`[^A-Za-z0-9._\- ]`) — which guarantees a latin-1-safe header. For a nicer UX,
additionally emit the original name RFC 5987-style:
`filename="<ascii-fallback>"; filename*=UTF-8''<pct-encoded>`.

### A2 (S3). Pydantic 422 echoes the full oversized input back

The `max_length` rejection includes the entire offending value in the error
body (`"input": "AAAA…"` — observed with the full 2000-char probe body
reflected). With the default 64 MB cap a client sending a 64 MB+1 body gets a
~64 MB JSON error back: pointless amplification, and it copies potentially
sensitive SQL into responses and any proxy/body-logging layer.

**Fix**: set `model_config = ConfigDict(hide_input_in_errors=True)` on the
request models (or a global `RequestValidationError` handler that strips
`input`). Note the body is still fully received and JSON-parsed before
validation — that is inherent to the framework; the reverse proxy should
enforce a request-body cap (tie into A4's doc fix).

### A3 (S3). No `.dockerignore` — private fixtures ride in the build context

There is no `.dockerignore` at the repo root. Today this is *not* a leak:

- `Dockerfile:11–12` copies only `pyproject.toml README.md src/`;
  `Dockerfile.dev:6–8` adds `tests/` — never `fixtures-private/` or
  `fixtures-corpus/`.
- Both private dirs are gitignored (`.gitignore:233,236`; `git ls-files`
  confirms 0 tracked files), so CI checkouts — where the published image is
  built (`ci.yaml:449–490`) — physically cannot contain them.

But a **local** `docker build` sends the entire context — including
`fixtures-private/` (real client SQL), `fixtures-corpus/` (GPLv2 corpus),
`.git/`, venvs — to the daemon, and the setup is one future broad `COPY . .`
away from baking confidential data into an image. It also bloats local build
context transfer.

**Fix**: add a `.dockerignore` listing at minimum `fixtures-private/`,
`fixtures-corpus/`, `.git/`, `.venv*/`, `audit/`, `coverage.xml`, `tests/`
(for the runtime image), `web/vendor/`.

### A4 (S3). Reverse-proxy deployment expectation still undocumented (07-02 A6 carry-over)

The API deliberately ships with no CORS config, no rate limiting, no auth and
no TLS — fine for the intended deployment behind a reverse proxy, but no doc
says so. `docs/07-interfaces.md` mentions a reverse proxy only in the
offline-assets sense (:91, :111). `UNIQUE_MAX_SQL_BYTES` is documented only in
the `docs/DONE.md` archive (:798, :1128), not in the interfaces/installation
docs. The web UI's structured DB-connection builder also sends the entered
password to the server (`web/src/index.template.html`, `builtDbUrl()`), which
is only sensible over TLS — another reason to state the proxy expectation.

**Fix**: a short "Deployment" subsection in `docs/07-interfaces.md` (or
`06-installation.md`): same-origin UI+API, no built-in auth/rate-limit/TLS —
put a reverse proxy in front for anything beyond a single-user lab; set a
proxy body cap consistent with `UNIQUE_MAX_SQL_BYTES`; document
`UNIQUE_MAX_SQL_BYTES` itself.

### A5 (S3). CI tests a floating dependency closure; the Docker image pins another

`constraints.txt` (new since 07-10, commit `8430cf5`) pins the full runtime
closure (fastapi 0.139.0, sqlglot 30.11.0, uvicorn 0.51.0, …) and **is used
by the runtime image** (`Dockerfile:29–31`, `pip install -c`). CI, however,
installs with plain `pip install -e ".[dev]"` (`ci.yaml:22,44,61,127,213`), so
every CI run resolves the *latest* versions satisfying `pyproject.toml`'s
open ranges (`fastapi>=0.110`, `uvicorn>=0.29`, `pydantic>=2.0`,
pyproject.toml:20–24). The moment upstream releases something newer than the
constraints pins, the tested closure and the shipped-image closure silently
diverge (sqlglot itself is safe — pinned `==30.11.0` in both, per the policy
in `docs/sqlglot-dependency.md`).

**Fix**: add `PIP_CONSTRAINT=constraints.txt` (or `-c constraints.txt`) to the
CI install steps — runtime deps then match the image exactly while dev tools
stay pinned by `pyproject.toml` (`black==26.3.1`, `ruff==0.15.17`, …). Keep
one canary job unconstrained if early warning on upstream drift is wanted.

### A6 (S3, informational). Dev image runs as root

`Dockerfile.dev` has no `USER` directive (runs as root, with source/tests
bind-mounted rw by `docker-compose.yaml`'s `dev` profile). The dev service is
profile-gated and never runs by default (compose `profiles: [dev]`), so this
is acceptable — noted for completeness. The runtime image is correct:
non-root `appuser` (Dockerfile:34–35), `UNIQUE_ALLOW_DB_CONNECTION=0` default
(Dockerfile:41), healthcheck present.

---

## Areas reviewed and found clean

**Web UI (`web/src/index.template.html`, built into
`src/unique/api/static/index.html` by `web/build.py`)** — every dynamic value
reaching an `innerHTML` sink goes through `escapeHtml`: error messages (:323),
syntax issues/snippets (:388–389), download names (:491,494), warnings and
`unsupported` entries (:539). Static markup only elsewhere (:296,:310,:421).
`fillSelect` uses `textContent`. No CDN/remote loads (self-contained by
design). No CSP header is set — low value while all scripts are inline, but a
`Content-Security-Policy` on `/` would be cheap hardening.

**Empirical behavior** (all probes on the live server):
oversized transpile/validate/detect → 422; oversized upload → 413
`File too large; the limit is 1000 bytes.`; valid transpile round-trip OK
(`SELECT TOP 5` → `LIMIT 5`); gated `db_url` → 403 policy text, no echo of the
URL; unknown dialect → 400 with a clean message; unparseable SQL with
`ignore_syntax_errors=true` → 200 with the documented `-- UNIQUE:` carrier +
`lossy_conversion` warning (no-silent-loss invariant holds at the API edge);
`/api/v1/info` correctly reports `db_connection_enabled/raw_db_url_enabled:
false, db_names: []`.

**CI workflows** (`ci.yaml`, `mutation.yml`, `cleanup.yml`, `codeql.yml`) —
secrets used correctly (`secrets.DOCKER_USER/DOCKER_PASSWORD` only in the
tag-gated docker job, ci.yaml:456–457,468–472; `GITHUB_TOKEN` scoped via
`permissions:` blocks in the other three). `fixtures-private` appears nowhere
in any workflow, and since both private dirs are untracked they cannot enter a
CI checkout, a step summary, or an artifact. The only artifact is
`coverage.xml` (public source paths + hit counts). Step summaries cat pytest
output of public-fixture tests only. Docker publish requires the full gate
including live validation (`needs:` ci.yaml:456). The engine-reachability gate
(ci.yaml:312–371) resolves the strongest 07-02 CI observation. The nightly
mutation job now has per-module score floors that fail the run and open a
tracking issue — a genuine improvement over "informational only".

**DSN gating regression check** — logic is unchanged from the 07-08-verified
design; `_resolve_db_option` still raises before any use of a client value,
never includes a configured URL in an error, and `db` (named DSN) takes
precedence over `db_url` (app.py:103–140, mirrored in the file endpoint at
:422).

---

## Summary

- **N6: FIXED** (both endpoints capped, verified by probe).
- **N7: PARTIALLY FIXED** — injection/traversal closed, but the Unicode-aware
  sanitizer still 500s on non-latin-1 filenames (new A1, S2).
- All three ops carry-overs (digest pin, engine gate, decode header) are
  **fixed**; the 07-02 A6 documentation half remains open (new A4).
- New findings: **0 × S1, 1 × S2 (A1), 5 × S3 (A2–A6)**.
- Most urgent: **A1** — one-line `re.ASCII` fix in `app.py:474`; then the
  `.dockerignore` (A3) as cheap insurance for the confidential fixtures.
