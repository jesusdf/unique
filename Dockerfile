# ---------------------------------------------------------------------------
# Unique SQL Transpiler — Multi-stage Docker build
# ---------------------------------------------------------------------------

# --- Stage 1: build ---
# python:3.13-slim, pinned by digest (P3: reproducible, tamper-evident
# builds; bump deliberately when refreshing the base).
FROM python@sha256:eb43ff125d8d58d7449dcba7d336c23bcac412f526d861db493b9994d8010280 AS builder

WORKDIR /build
COPY pyproject.toml README.md ./
COPY src/ src/

RUN pip install --no-cache-dir build \
    && python -m build --wheel --outdir /build/dist

# --- Stage 2: runtime ---
FROM python@sha256:eb43ff125d8d58d7449dcba7d336c23bcac412f526d861db493b9994d8010280

LABEL maintainer="Jesús Diéguez Fernández" \
      description="SQL transpiler: translate scripts between SQL Server, Oracle, PostgreSQL, and MySQL"

WORKDIR /app

# Install the wheel built in the previous stage. The constraints file pins
# the full runtime dependency closure so two builds of the same commit
# install identical versions (P3).
COPY --from=builder /build/dist/*.whl /tmp/
COPY constraints.txt /tmp/constraints.txt
RUN pip install --no-cache-dir -c /tmp/constraints.txt /tmp/*.whl \
    && rm /tmp/*.whl /tmp/constraints.txt

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
