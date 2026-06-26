# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

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


class TestInfo:
    def test_info_reports_version_label(self, client: TestClient) -> None:
        resp = client.get("/api/v1/info")
        assert resp.status_code == 200
        assert resp.json()["version"] == "v0.06"

    def test_version_label_is_derived_from_package_version(self) -> None:
        # The UI label tracks unique.__version__ so a release needs no HTML edit.
        from unique.api.app import _display_version

        assert _display_version() == "v0.06"

    def test_info_db_disabled_by_default(self, client: TestClient) -> None:
        resp = client.get("/api/v1/info")
        assert resp.json()["db_connection_enabled"] is False

    def test_info_db_enabled_via_env(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("UNIQUE_ALLOW_DB_CONNECTION", "true")
        resp = client.get("/api/v1/info")
        assert resp.json()["db_connection_enabled"] is True


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

    def test_db_url_rejected_when_disabled(self, client: TestClient) -> None:
        # Database connections are off by default; a db_url must be rejected.
        resp = client.post(
            "/api/v1/transpile",
            json={
                "sql": "SELECT 1;",
                "source": "tsql",
                "target": "oracle",
                "db_url": "postgresql://u:p@127.0.0.1:1/none",
            },
        )
        assert resp.status_code == 403

    def test_db_url_accepted_when_enabled(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("UNIQUE_ALLOW_DB_CONNECTION", "1")
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

    def test_db_url_omitted_works_when_disabled(self, client: TestClient) -> None:
        # No db_url: the request must succeed even with connections disabled.
        resp = client.post(
            "/api/v1/transpile",
            json={"sql": "SELECT 1;", "source": "tsql", "target": "oracle"},
        )
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


class TestDetect:
    def test_detect_tsql(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/detect",
            json={"sql": "SELECT TOP 5 * FROM t WHERE x = GETDATE()\nGO"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["dialect"] == "tsql"
        assert 0.0 <= body["confidence"] <= 1.0
        assert set(body["scores"]) == {"tsql", "oracle", "postgresql", "mysql"}

    def test_detect_none_on_prose(self, client: TestClient) -> None:
        resp = client.post("/api/v1/detect", json={"sql": "just prose, nothing to see"})
        assert resp.status_code == 200
        assert resp.json()["dialect"] is None


class TestUI:
    def test_root_serves_html(self, client: TestClient) -> None:
        resp = client.get("/")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert "<textarea" in resp.text

    def test_ui_is_self_contained(self, client: TestClient) -> None:
        # The page must embed CodeMirror and load no external resources, so it
        # works behind a reverse proxy with no internet access.
        resp = client.get("/")
        body = resp.text
        assert "CodeMirror" in body
        for cdn in ("cdnjs", "unpkg", "jsdelivr", "googleapis"):
            assert cdn not in body, f"external resource {cdn} must not be referenced"

    def test_logo_is_served(self, client: TestClient) -> None:
        resp = client.get("/static/logo.svg")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("image/svg")
        assert "<svg" in resp.text

    def test_logo_precedes_title_in_header(self, client: TestClient) -> None:
        body = client.get("/").text
        header = body[body.index("<header>") : body.index("</header>")]
        assert "logo.svg" in header
        assert header.index("logo.svg") < header.index("<h1>")

    def test_static_assets_are_packaged_in_the_wheel(self) -> None:
        # The container installs from the wheel, not the source tree, so every
        # static asset type the UI references must be declared in package-data
        # or it 404s in the image (as the SVG logo once did). Guard the SVG and
        # the other web asset types explicitly.
        import tomllib
        from pathlib import Path

        root = Path(__file__).resolve().parents[3]
        with open(root / "pyproject.toml", "rb") as fh:
            cfg = tomllib.load(fh)
        patterns = cfg["tool"]["setuptools"]["package-data"]["unique.api"]
        for needed in ("static/*.svg", "static/*.html", "static/*.css", "static/*.js"):
            assert needed in patterns, f"{needed} missing from wheel package-data"


class TestTranspileFile:
    def test_file_with_explicit_source(self, client: TestClient) -> None:
        content = b"SELECT TOP 5 * FROM t"
        resp = client.post(
            "/api/v1/transpile/file",
            data={"source": "tsql", "target": "postgresql"},
            files={"file": ("q.sql", content, "text/plain")},
        )
        assert resp.status_code == 200
        assert "LIMIT 5" in resp.text
        assert 'filename="q.postgresql.sql"' in resp.headers["content-disposition"]

    def test_file_auto_detect(self, client: TestClient) -> None:
        content = b"CREATE TABLE t (id INT AUTO_INCREMENT) ENGINE=InnoDB;\nDELIMITER //"
        resp = client.post(
            "/api/v1/transpile/file",
            data={"source": "auto", "target": "postgresql"},
            files={"file": ("t.sql", content, "text/plain")},
        )
        assert resp.status_code == 200
        assert resp.headers["x-unique-source-dialect"] == "mysql"
        assert "SERIAL" in resp.text

    def test_file_auto_detect_failure(self, client: TestClient) -> None:
        content = b"this is not sql just words here"
        resp = client.post(
            "/api/v1/transpile/file",
            data={"source": "auto", "target": "mysql"},
            files={"file": ("x.sql", content, "text/plain")},
        )
        assert resp.status_code == 422

    def test_file_unknown_dialect(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/transpile/file",
            data={"source": "tsql", "target": "nope"},
            files={"file": ("q.sql", b"SELECT 1", "text/plain")},
        )
        assert resp.status_code == 400

    def test_file_db_url_rejected_when_disabled(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/transpile/file",
            data={
                "source": "tsql",
                "target": "oracle",
                "db_url": "postgresql://u:p@127.0.0.1:1/none",
            },
            files={"file": ("q.sql", b"SELECT 1", "text/plain")},
        )
        assert resp.status_code == 403

    def test_file_db_url_accepted_when_enabled(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("UNIQUE_ALLOW_DB_CONNECTION", "1")
        resp = client.post(
            "/api/v1/transpile/file",
            data={
                "source": "tsql",
                "target": "oracle",
                "db_url": "postgresql://u:p@127.0.0.1:1/none",
            },
            files={"file": ("q.sql", b"SELECT 1", "text/plain")},
        )
        assert resp.status_code == 200
