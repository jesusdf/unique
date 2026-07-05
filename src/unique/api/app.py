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
# transpilation with unbounded input is a trivial DoS (audit 2026-07-02, A2), so
# the cap stays; the default is 64 MB to accommodate large real migration
# scripts, and ``UNIQUE_MAX_SQL_BYTES`` tunes it per deployment.
MAX_SQL_BYTES = int(os.environ.get("UNIQUE_MAX_SQL_BYTES", 64_000_000))

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


def _raw_db_url_enabled() -> bool:
    """Whether clients may send a *raw* ``db_url`` (audit 2026-07-02, A3).

    A raw URL lets any API client make the server open TCP connections to
    arbitrary hosts with arbitrary credentials — an SSRF/credential-relay
    primitive — so it needs its own opt-in on top of
    ``UNIQUE_ALLOW_DB_CONNECTION``. The supported path is a server-side
    named DSN (``UNIQUE_DSN_<NAME>``) referenced by name.
    """
    return os.environ.get("UNIQUE_ALLOW_RAW_DB_URL", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


_DSN_ENV_PREFIX = "UNIQUE_DSN_"


def _named_dsns() -> dict[str, str]:
    """Server-configured DSNs, keyed by their lowercase hyphenated name.

    ``UNIQUE_DSN_HR_READONLY=oracle://...`` is referenced by clients as
    ``db: "hr-readonly"``. URLs never leave the server.
    """
    return {
        key[len(_DSN_ENV_PREFIX) :].lower().replace("_", "-"): value.strip()
        for key, value in os.environ.items()
        if key.startswith(_DSN_ENV_PREFIX) and value.strip()
    }


def _resolve_db_option(db: str | None, db_url: str | None) -> str | None:
    """Resolve the connection URL for a request, enforcing the A3 policy.

    ``db`` names a server-side DSN; ``db_url`` is a raw URL needing the
    extra ``UNIQUE_ALLOW_RAW_DB_URL`` opt-in. Raises HTTPException on any
    policy violation, never echoing configured URLs.
    """
    if not db and not db_url:
        return None
    if not _db_connection_enabled():
        raise HTTPException(
            status_code=403,
            detail=(
                "Database connections are disabled on this deployment. Set "
                "UNIQUE_ALLOW_DB_CONNECTION=1 to enable the db option."
            ),
        )
    if db:
        url = _named_dsns().get(db.strip().lower().replace("_", "-"))
        if url is None:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Unknown database name {db!r}. Configure it server-side "
                    "as UNIQUE_DSN_<NAME> and reference it by name."
                ),
            )
        return url
    if not _raw_db_url_enabled():
        raise HTTPException(
            status_code=403,
            detail=(
                "Raw db_url values are disabled on this deployment. Use a "
                "server-side named DSN (UNIQUE_DSN_<NAME> + db=<name>), or "
                "set UNIQUE_ALLOW_RAW_DB_URL=1 to accept raw URLs."
            ),
        )
    return db_url


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
    db: str | None = Field(
        default=None,
        description=(
            "Optional name of a server-configured DSN (UNIQUE_DSN_<NAME>) "
            "used to resolve metadata-dependent constructs such as Oracle "
            "%TYPE/%ROWTYPE references."
        ),
    )
    db_url: str | None = Field(
        default=None,
        description=(
            "Optional raw database connection URL. Disabled unless the "
            "deployment sets UNIQUE_ALLOW_RAW_DB_URL; prefer a named DSN "
            "(the 'db' field)."
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
    # Dialects valid only as a transpilation source (import-only, e.g. SQLite);
    # the UI offers them as a source but not as a target.
    source_only: list[str] = []


class InfoResponse(BaseModel):
    """Runtime info the UI needs to configure itself."""

    version: str = Field(..., description="Human-readable version label, e.g. v0.02.")
    db_connection_enabled: bool = Field(
        ...,
        description=(
            "Whether the deployment allows database connections "
            "(controlled by the UNIQUE_ALLOW_DB_CONNECTION environment variable)."
        ),
    )
    db_names: list[str] = Field(
        default_factory=list,
        description=(
            "Names of the server-configured DSNs (UNIQUE_DSN_<NAME>) a client "
            "may reference via the 'db' field. URLs are never exposed."
        ),
    )
    raw_db_url_enabled: bool = Field(
        default=False,
        description=(
            "Whether raw db_url values are accepted "
            "(UNIQUE_ALLOW_RAW_DB_URL; discouraged, see docs)."
        ),
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.post("/api/v1/transpile", response_model=TranspileResponse)
def transpile_sql(request: TranspileRequest) -> TranspileResponse:
    """Transpile SQL from one dialect to another."""
    db_url = _resolve_db_option(request.db, request.db_url)
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
    return DialectsResponse(
        dialects=_transpiler.available_dialects(),
        source_only=_transpiler.source_only_dialects(),
    )


@app.get("/api/v1/info", response_model=InfoResponse)
def get_info() -> InfoResponse:
    """Report the version label and feature flags the UI needs at load time."""
    return InfoResponse(
        version=DISPLAY_VERSION,
        db_connection_enabled=_db_connection_enabled(),
        db_names=sorted(_named_dsns()),
        raw_db_url_enabled=_raw_db_url_enabled(),
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
    db: str | None = Form(default=None),  # noqa: B008 - FastAPI pattern
    db_url: str | None = Form(default=None),  # noqa: B008 - FastAPI pattern
) -> StreamingResponse:
    """Transpile an uploaded SQL file and stream back the translated file.

    ``source`` may be the literal ``auto`` to auto-detect the dialect from the
    file contents. ``db`` names a server-configured DSN (UNIQUE_DSN_<NAME>)
    for resolving metadata-dependent constructs; a raw ``db_url`` needs the
    extra UNIQUE_ALLOW_RAW_DB_URL opt-in (audit 2026-07-02, A3).
    """
    db_url = _resolve_db_option(db, db_url)
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
