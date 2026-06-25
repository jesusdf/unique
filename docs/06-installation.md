# Unique — Installation & Deployment

## Install from source

```bash
git clone https://github.com/jesusdf/unique.git
cd unique
pip install -e ".[dev]"
```

This installs the `unique` CLI and the Python library, plus the development
dependencies (test, lint, type-check). For a runtime-only install, drop the
`[dev]` extra.

`unique` pins sqlglot to an exact version (see
[sqlglot-dependency.md](sqlglot-dependency.md)); upgrading it is a deliberate
step, not something `pip` does on its own.

## Run with Docker (end users)

A prebuilt image is published to Docker Hub as
[`jesusdf/unique`](https://hub.docker.com/r/jesusdf/unique). The quickest way
to run the API + web UI is:

```bash
docker run --rm -p 8000:8000 jesusdf/unique:latest
```

Then open <http://localhost:8000/> for the web UI, or call the REST API at
`http://localhost:8000/api/v1/...` (see [07-interfaces.md](07-interfaces.md)).

### docker-compose (pulls the published image)

For a small, self-contained deployment, this compose file pulls the published
image rather than building from source:

```yaml
# docker-compose.yaml
services:
  unique:
    image: jesusdf/unique:latest
    container_name: unique
    ports:
      - "8000:8000"
    environment:
      - LOG_LEVEL=info
      # Set to 1 to allow the db-url option (off by default). See Configuration.
      - UNIQUE_ALLOW_DB_CONNECTION=${UNIQUE_ALLOW_DB_CONNECTION:-0}
    restart: unless-stopped
    healthcheck:
      test:
        - CMD
        - python
        - -c
        - "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"
      interval: 30s
      timeout: 5s
      retries: 3
```

```bash
docker compose up -d
```

To pin a specific build instead of `latest`, replace the tag with the
short commit SHA published by CI (e.g. `jesusdf/unique:abc1234`).

## Configuration

### `UNIQUE_ALLOW_DB_CONNECTION` — enable the database connection (db-url)

Some source constructs are metadata-dependent and can only be resolved
faithfully against a live database — most notably Oracle `%TYPE`/`%ROWTYPE`
references, which name a column's type indirectly. To resolve them, Unique can
connect to the source database via a connection URL (the CLI `--db-url` flag /
the API `db_url` parameter).

Because connecting to a live database is a privileged action, it is **disabled
by default**. Set `UNIQUE_ALLOW_DB_CONNECTION` to `1`/`true`/`yes`/`on` to
enable it:

```bash
# docker compose
UNIQUE_ALLOW_DB_CONNECTION=1 docker compose up -d

# plain docker
docker run -e UNIQUE_ALLOW_DB_CONNECTION=1 -p 8000:8000 jesusdf/unique:latest
```

When enabled:

- the web UI shows an optional **"Database connection"** field (in both the
  script and the file sections) where the user can paste a connection URL such
  as `oracle://user:pass@host:1521/service`; leaving it empty simply skips
  metadata resolution;
- the API accepts `db_url` on `POST /api/v1/transpile` and
  `POST /api/v1/transpile/file`.

When disabled (the default), any request carrying a `db_url` is rejected with
HTTP 403, and the UI hides the field. The current state is reported by
`GET /api/v1/info` as `db_connection_enabled`.

## Build the image yourself (contributors)

The repository ships a `Dockerfile` (production) and `Dockerfile.dev`
(hot-reload), wired up in the repo's own `docker-compose.yaml`:

```bash
# Production image, built locally
docker compose up -d

# Development service with hot-reload and test dependencies
docker compose --profile dev up
```

See the [Development Guide](04-development-guide.md) for the contributor
workflow (tests, linting, adding dialects) and
[Architecture](02-architecture.md) for the design.
