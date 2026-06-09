# Copyright (C) 2026 Unique Contributors
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.

"""FastAPI REST API for the Unique SQL transpiler."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from unique.core.errors import ParseError, UnknownDialectError
from unique.core.transpiler import Transpiler

app = FastAPI(
    title="Unique SQL Transpiler",
    description="Transpile SQL between SQL Server, Oracle, PostgreSQL, and MySQL.",
    version="0.1.0",
)

_transpiler = Transpiler()


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class TranspileRequest(BaseModel):
    """Request body for the transpile endpoint."""

    sql: str = Field(..., description="Source SQL text to transpile.")
    source: str = Field(..., description="Source dialect name.")
    target: str = Field(..., description="Target dialect name.")


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


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.post("/api/v1/transpile", response_model=TranspileResponse)
async def transpile_sql(request: TranspileRequest) -> TranspileResponse:
    """Transpile SQL from one dialect to another."""
    try:
        result = _transpiler.transpile(
            sql=request.sql,
            source=request.source,
            target=request.target,
        )
    except UnknownDialectError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except ParseError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Transpilation failed: {e}") from e

    return TranspileResponse(
        sql=result.sql,
        warnings=[
            TranspileWarning(message=w.message, feature=w.feature)
            for w in result.warnings
        ],
        unsupported=result.unsupported,
    )


@app.post("/api/v1/validate", response_model=ValidateResponse)
async def validate_sql(request: ValidateRequest) -> ValidateResponse:
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
async def list_dialects() -> DialectsResponse:
    """List all available SQL dialects."""
    return DialectsResponse(dialects=_transpiler.available_dialects())


@app.get("/health")
async def health() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok"}
