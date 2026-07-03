# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""FastAPI REST API for the Unique SQL transpiler."""

from __future__ import annotations

import io
import logging
import os
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from unique import __version__
from unique.core.detection import detect_dialect
from unique.core.errors import ParseError, UnknownDialectError
from unique.core.transpiler import TranspileOptions, Transpiler

_STATIC_DIR = Path(__file__).parent / "static"


# Input size cap for SQL bodies and uploads (bytes/characters). CPU-bound
# transpilation with unbounded input is a trivial DoS (audit 2026-07-02, A2).
MAX_SQL_BYTES = int(os.environ.get("UNIQUE_MAX_SQL_BYTES", 2_000_000))

logger = logging.getLogger(__name__)


def _display_version() -> str:
    """The version label shown in the UI, derived from the package version.

    Renders ``major.minor`` with the minor zero-padded to two digits and a
    leading ``v`` (e.g. ``0.2.0`` -> ``v0.02``), so the label tracks
    ``unique.__version__`` and never has to be edited by hand on a release.
    """
    parts = __version__.split(".")
    major = parts[0] if parts else "0"
    minor = parts[1] if len(parts) > 1 else "0"
    return f"v{major}.{int(minor):02d}"


#: The version label shown in the UI and reported by /api/v1/info.
DISPLAY_VERSION = _display_version()


def _db_connection_enabled() -> bool:
    """Whether database connections (the ``db-url`` parameter) are allowed.

    Controlled by the ``UNIQUE_ALLOW_DB_CONNECTION`` environment variable so a
    container can opt in. Accepts the usual truthy spellings; defaults to off,
    since connecting to a live database is a privileged capability.
    """
    return os.environ.get("UNIQUE_ALLOW_DB_CONNECTION", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


app = FastAPI(
    title="Unique SQL Transpiler",
    description="Transpile SQL between SQL Server, Oracle, PostgreSQL, and MySQL.",
    version=__version__,
)

_transpiler = Transpiler()


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class TranspileRequest(BaseModel):
    """Request body for the transpile endpoint."""

    sql: str = Field(
        ...,
        max_length=MAX_SQL_BYTES,
        description="Source SQL text to transpile.",
    )
    source: str = Field(..., description="Source dialect name.")
    target: str = Field(..., description="Target dialect name.")
    db_url: str | None = Field(
        default=None,
        description=(
            "Optional database connection URL for resolving "
            "metadata-dependent constructs such as Oracle %TYPE/%ROWTYPE "
            "references."
        ),
    )


class TranspileWarning(BaseModel):
    """A warning from the transpilation process."""

    message: str
    feature: str


class TranspileResponse(BaseModel):
    """Response from the transpile endpoint."""

    sql: str
    warnings: list[TranspileWarning] = []
    unsupported: list[str] = []


class ValidateRequest(BaseModel):
    """Request body for the validate endpoint."""

    sql: str = Field(..., description="SQL text to validate.")
    dialect: str = Field(..., description="Dialect to validate against.")


class ValidateResponse(BaseModel):
    """Response from the validate endpoint."""

    valid: bool
    statement_count: int = 0
    errors: list[str] = []


class DialectsResponse(BaseModel):
    """Response listing available dialects."""

    dialects: list[str]


class InfoResponse(BaseModel):
    """Runtime info the UI needs to configure itself."""

    version: str = Field(..., description="Human-readable version label, e.g. v0.02.")
    db_connection_enabled: bool = Field(
        ...,
        description=(
            "Whether the deployment allows providing a database connection URL "
            "(controlled by the UNIQUE_ALLOW_DB_CONNECTION environment variable)."
        ),
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.post("/api/v1/transpile", response_model=TranspileResponse)
def transpile_sql(request: TranspileRequest) -> TranspileResponse:
    """Transpile SQL from one dialect to another."""
    db_url = request.db_url
    if db_url and not _db_connection_enabled():
        raise HTTPException(
            status_code=403,
            detail=(
                "Database connections are disabled on this deployment. Set "
                "UNIQUE_ALLOW_DB_CONNECTION=1 to enable the db-url option."
            ),
        )
    try:
        result = _transpiler.transpile(
            sql=request.sql,
            source=request.source,
            target=request.target,
            options=TranspileOptions(db_url=db_url),
        )
    except UnknownDialectError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except ParseError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except Exception as e:
        # Never forward internal details (paths, driver errors, credentials)
        # to the client (audit 2026-07-02, A4).
        logger.exception("Transpilation failed")
        raise HTTPException(
            status_code=500, detail="Transpilation failed; see server logs."
        ) from e

    return TranspileResponse(
        sql=result.sql,
        warnings=[
            TranspileWarning(message=w.message, feature=w.feature)
            for w in result.warnings
        ],
        unsupported=result.unsupported,
    )


@app.post("/api/v1/validate", response_model=ValidateResponse)
def validate_sql(request: ValidateRequest) -> ValidateResponse:
    """Validate SQL syntax by parsing it."""
    try:
        dialect = _transpiler.registry.get(request.dialect)
        nodes = dialect.parse(request.sql)
        return ValidateResponse(valid=True, statement_count=len(nodes))
    except UnknownDialectError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        return ValidateResponse(valid=False, errors=[str(e)])


@app.get("/api/v1/dialects", response_model=DialectsResponse)
def list_dialects() -> DialectsResponse:
    """List all available SQL dialects."""
    return DialectsResponse(dialects=_transpiler.available_dialects())


@app.get("/api/v1/info", response_model=InfoResponse)
def get_info() -> InfoResponse:
    """Report the version label and feature flags the UI needs at load time."""
    return InfoResponse(
        version=DISPLAY_VERSION,
        db_connection_enabled=_db_connection_enabled(),
    )


class DetectRequest(BaseModel):
    """Request body for the detect endpoint."""

    sql: str = Field(..., description="SQL text whose dialect to detect.")


class DetectResponse(BaseModel):
    """Response from the detect endpoint."""

    dialect: str | None
    confidence: float
    scores: dict[str, int]


@app.post("/api/v1/detect", response_model=DetectResponse)
def detect_sql_dialect(request: DetectRequest) -> DetectResponse:
    """Best-effort detection of the SQL dialect of a script."""
    result = detect_dialect(request.sql)
    return DetectResponse(
        dialect=result.dialect,
        confidence=result.confidence,
        scores=result.scores,
    )


@app.post("/api/v1/transpile/file")
def transpile_file(
    file: UploadFile = File(...),  # noqa: B008 - FastAPI dependency pattern
    source: str = Form(...),  # noqa: B008 - FastAPI dependency pattern
    target: str = Form(...),  # noqa: B008 - FastAPI dependency pattern
    db_url: str | None = Form(default=None),  # noqa: B008 - FastAPI pattern
) -> StreamingResponse:
    """Transpile an uploaded SQL file and stream back the translated file.

    ``source`` may be the literal ``auto`` to auto-detect the dialect from the
    file contents. ``db_url`` is an optional database connection URL for
    resolving metadata-dependent constructs; it is rejected unless the
    deployment enables database connections.
    """
    if db_url and not _db_connection_enabled():
        raise HTTPException(
            status_code=403,
            detail=(
                "Database connections are disabled on this deployment. Set "
                "UNIQUE_ALLOW_DB_CONNECTION=1 to enable the db-url option."
            ),
        )
    raw = file.file.read(MAX_SQL_BYTES + 1)
    if len(raw) > MAX_SQL_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File too large; the limit is {MAX_SQL_BYTES} bytes.",
        )
    # BOM-aware decode: SQL Server tooling frequently emits UTF-16
    # (audit 2026-07-02, A5). latin-1 stays as the never-failing last resort.
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        sql = raw.decode("utf-16")
    else:
        try:
            sql = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            sql = raw.decode("latin-1")

    resolved_source = source
    if source == "auto":
        detected = detect_dialect(sql)
        if detected.dialect is None:
            raise HTTPException(
                status_code=422,
                detail="Could not auto-detect the source dialect.",
            )
        resolved_source = detected.dialect

    try:
        result = _transpiler.transpile(
            sql=sql,
            source=resolved_source,
            target=target,
            options=TranspileOptions(db_url=db_url),
        )
    except UnknownDialectError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except ParseError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except Exception as e:  # noqa: BLE001
        logger.exception("Transpilation failed")
        raise HTTPException(
            status_code=500, detail="Transpilation failed; see server logs."
        ) from e

    # Build an output filename: <stem>.<target>.sql
    stem = (file.filename or "script").rsplit(".", 1)[0]
    out_name = f"{stem}.{target}.sql"
    buffer = io.BytesIO(result.sql.encode("utf-8"))
    headers = {
        "Content-Disposition": f'attachment; filename="{out_name}"',
        "X-Unique-Source-Dialect": resolved_source,
        "X-Unique-Warning-Count": str(len(result.warnings)),
    }
    return StreamingResponse(buffer, media_type="application/sql", headers=headers)


@app.get("/health")
async def health() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok"}


@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    """Serve the web UI."""
    return FileResponse(_STATIC_DIR / "index.html")


# Serve static assets (the single-page UI lives under /static and at /).
if _STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")
