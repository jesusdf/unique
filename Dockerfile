# ---------------------------------------------------------------------------
# Unique SQL Transpiler — Multi-stage Docker build
# ---------------------------------------------------------------------------

# --- Stage 1: build ---
FROM python:3.12-slim AS builder

WORKDIR /build
COPY pyproject.toml README.md ./
COPY src/ src/

RUN pip install --no-cache-dir build \
    && python -m build --wheel --outdir /build/dist

# --- Stage 2: runtime ---
FROM python:3.12-slim

LABEL maintainer="Jesús Diéguez Fernández" \
      description="SQL transpiler: translate scripts between SQL Server, Oracle, PostgreSQL, and MySQL"

WORKDIR /app

# Install the wheel built in the previous stage
COPY --from=builder /build/dist/*.whl /tmp/
RUN pip install --no-cache-dir /tmp/*.whl && rm /tmp/*.whl

# Non-root user for security
RUN useradd --create-home appuser
USER appuser

# Allow providing a database connection URL (db-url) for resolving
# metadata-dependent constructs (e.g. Oracle %TYPE/%ROWTYPE). Off by default,
# since connecting to a live database is a privileged action. Set to 1/true to
# enable; the web UI then shows an optional "Database connection" field.
ENV UNIQUE_ALLOW_DB_CONNECTION=0

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

ENTRYPOINT ["uvicorn", "unique.api.app:app"]
CMD ["--host", "0.0.0.0", "--port", "8000"]
