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
