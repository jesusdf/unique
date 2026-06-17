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

"""Tests for the REST API."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from unique.api.app import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


class TestHealth:
    def test_health_ok(self, client: TestClient) -> None:
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


class TestDialects:
    def test_list_dialects(self, client: TestClient) -> None:
        resp = client.get("/api/v1/dialects")
        assert resp.status_code == 200
        dialects = resp.json()["dialects"]
        for d in ("tsql", "oracle", "postgresql", "mysql"):
            assert d in dialects


class TestTranspile:
    def test_basic_transpile(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/transpile",
            json={"sql": "SELECT 1;", "source": "tsql", "target": "oracle"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["sql"].strip()
        assert "warnings" in body
        assert "unsupported" in body

    def test_unknown_dialect_returns_400(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/transpile",
            json={"sql": "SELECT 1;", "source": "nope", "target": "oracle"},
        )
        assert resp.status_code == 400

    def test_procedure_transpile(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/transpile",
            json={
                "sql": ("CREATE PROCEDURE p @x INT AS BEGIN " "SET @x = @x + 1 END"),
                "source": "tsql",
                "target": "oracle",
            },
        )
        assert resp.status_code == 200
        assert "PROCEDURE" in resp.json()["sql"].upper()

    def test_db_url_field_accepted(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/transpile",
            json={
                "sql": "SELECT 1;",
                "source": "tsql",
                "target": "oracle",
                "db_url": "postgresql://u:p@127.0.0.1:1/none",
            },
        )
        # Unreachable DB must not 500 for plain SQL.
        assert resp.status_code == 200

    def test_missing_field_returns_422(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/transpile", json={"sql": "SELECT 1;", "source": "tsql"}
        )
        assert resp.status_code == 422


class TestValidate:
    def test_valid_sql(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/validate",
            json={"sql": "SELECT 1;", "dialect": "tsql"},
        )
        assert resp.status_code == 200
        assert resp.json()["valid"] is True

    def test_unknown_dialect_returns_400(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/validate",
            json={"sql": "SELECT 1;", "dialect": "nope"},
        )
        assert resp.status_code == 400
