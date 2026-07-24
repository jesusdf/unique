# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Tests for the REST API."""

from __future__ import annotations

import re

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
        from unique.api.app import _display_version

        resp = client.get("/api/v1/info")
        assert resp.status_code == 200
        # The reported label is the derived one — no hard-coded version to bump.
        assert resp.json()["version"] == _display_version()

    def test_version_label_is_derived_from_package_version(self) -> None:
        # The UI label tracks unique.__version__ (single-sourced) so a release
        # edits the version in exactly one place and needs no HTML/test edit.
        from unique import __version__
        from unique.api.app import _display_version

        major, minor = (__version__.split(".") + ["0", "0"])[:2]
        assert _display_version() == f"v{major}.{int(minor):02d}"

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

    def test_db_url_accepted_with_raw_opt_in(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # A raw URL needs UNIQUE_ALLOW_RAW_DB_URL on top of the connection
        # gate (audit 2026-07-02, A3); named DSNs are the supported path.
        monkeypatch.setenv("UNIQUE_ALLOW_DB_CONNECTION", "1")
        monkeypatch.setenv("UNIQUE_ALLOW_RAW_DB_URL", "1")
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

    def test_reports_located_syntax_issue(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/validate",
            json={"sql": "SELECT * FROM (SELECT 1", "dialect": "tsql"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["valid"] is False
        assert body["issues"] and body["issues"][0]["line"] == 1


class TestSourceValidationGate:
    _MALFORMED = "INSERT INTO t VALUES (1)\nCREATE PROCEDURE p AS BEGIN SELECT 1 END"

    def test_transpile_refuses_malformed_source(self, client: TestClient) -> None:
        # A CREATE PROCEDURE with no preceding GO is a source syntax error: the
        # request is rejected (422) with the located error, not silently mangled.
        resp = client.post(
            "/api/v1/transpile",
            json={"sql": self._MALFORMED, "source": "tsql", "target": "oracle"},
        )
        assert resp.status_code == 422
        detail = resp.json()["detail"]
        assert detail["error"] == "source_syntax_errors"
        assert detail["issues"][0]["line"] == 2

    def test_ignore_syntax_errors_forces_transpile(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/transpile",
            json={
                "sql": self._MALFORMED,
                "source": "tsql",
                "target": "oracle",
                "ignore_syntax_errors": True,
            },
        )
        assert resp.status_code == 200

    def test_valid_source_transpiles(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/transpile",
            json={"sql": "SELECT 1", "source": "tsql", "target": "oracle"},
        )
        assert resp.status_code == 200


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

    def test_ui_gates_translate_on_source_validation(self, client: TestClient) -> None:
        # The page validates the source live and disables Translate while it has
        # syntax errors (setRunBlocked), showing the located issues.
        body = client.get("/").text
        assert "validateSource" in body
        assert "/api/v1/validate" in body
        assert "setRunBlocked" in body

    def test_index_is_revalidated_not_cached(self, client: TestClient) -> None:
        # ``no-cache`` makes the browser revalidate, so a UI update (new JS) is not
        # masked by a stale cached page.
        assert client.get("/").headers.get("cache-control") == "no-cache"

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

    def test_file_decoded_as_header_utf8(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/transpile/file",
            data={"source": "tsql", "target": "postgresql"},
            files={"file": ("q.sql", "SELECT 'café'".encode(), "text/plain")},
        )
        assert resp.status_code == 200
        assert resp.headers["x-unique-decoded-as"] == "utf-8"

    def test_file_decoded_as_header_utf16(self, client: TestClient) -> None:
        content = "SELECT 'café'".encode("utf-16")  # BOM-prefixed
        resp = client.post(
            "/api/v1/transpile/file",
            data={"source": "tsql", "target": "postgresql"},
            files={"file": ("q.sql", content, "text/plain")},
        )
        assert resp.status_code == 200
        assert resp.headers["x-unique-decoded-as"] == "utf-16"
        assert "café" in resp.text

    def test_file_decoded_as_header_latin1_last_resort(
        self, client: TestClient
    ) -> None:
        content = "SELECT 'café'".encode("latin-1")  # invalid as UTF-8
        resp = client.post(
            "/api/v1/transpile/file",
            data={"source": "tsql", "target": "postgresql"},
            files={"file": ("q.sql", content, "text/plain")},
        )
        assert resp.status_code == 200
        assert resp.headers["x-unique-decoded-as"] == "latin-1"

    def test_file_output_filename_sanitized(self, client: TestClient) -> None:
        # A hostile client filename must not inject quotes/CRLF or path
        # separators into the Content-Disposition header (N7).
        resp = client.post(
            "/api/v1/transpile/file",
            data={"source": "tsql", "target": "postgresql"},
            files={"file": ('a"; x="/etc/passwd.sql', b"SELECT 1", "text/plain")},
        )
        assert resp.status_code == 200
        disposition = resp.headers["content-disposition"]
        # Whatever the multipart client did to the name, the emitted header
        # must stay a single quoted token over a safe character set.
        assert re.fullmatch(
            r'attachment; filename="[\w.\- ]+\.postgresql\.sql"', disposition
        ), disposition

    def test_file_non_ascii_filename_does_not_break_header(
        self, client: TestClient
    ) -> None:
        # A non-latin-1 filename (CJK/Cyrillic) used to crash Starlette's
        # latin-1 header encode into a 500 (audit 2026-07-24 05 A1); the
        # sanitizer must reduce the stem to ASCII (re.ASCII) instead.
        for name in ("中文档.sql", "файл.sql", "ñandú.sql"):
            resp = client.post(
                "/api/v1/transpile/file",
                data={"source": "tsql", "target": "postgresql"},
                files={"file": (name, b"SELECT 1", "text/plain")},
            )
            assert resp.status_code == 200, name
            disposition = resp.headers["content-disposition"]
            assert disposition.isascii(), disposition
            assert re.fullmatch(
                r'attachment; filename="[\w.\- ]+\.postgresql\.sql"', disposition
            ), disposition

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

    def test_file_db_url_accepted_with_raw_opt_in(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("UNIQUE_ALLOW_DB_CONNECTION", "1")
        monkeypatch.setenv("UNIQUE_ALLOW_RAW_DB_URL", "1")
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


class TestApiHardening:
    """Audit 2026-07-02 doc 04: size limits, error hygiene, sync handlers."""

    def test_oversized_sql_body_rejected(self, client) -> None:
        from unique.api import app as app_module

        big = "SELECT 1; " * (app_module.MAX_SQL_BYTES // 10 + 1)
        response = client.post(
            "/api/v1/transpile",
            json={"sql": big, "source": "tsql", "target": "postgresql"},
        )
        assert response.status_code == 422

    def test_oversized_upload_rejected(self, client) -> None:
        from unique.api import app as app_module

        big = b"SELECT 1; " * (app_module.MAX_SQL_BYTES // 10 + 1)
        response = client.post(
            "/api/v1/transpile/file",
            files={"file": ("big.sql", big, "text/plain")},
            data={"source": "tsql", "target": "postgresql"},
        )
        assert response.status_code == 413

    def test_default_cap_allows_large_scripts(self, client) -> None:
        from unique.api import app as app_module

        # The default cap accommodates large real migration scripts, well above
        # the former 2 MB; a 3 MB body (over that old cap) is accepted.
        assert app_module.MAX_SQL_BYTES >= 8_000_000
        sql = "SELECT '" + "x" * 3_000_000 + "' AS c"
        response = client.post(
            "/api/v1/transpile",
            json={"sql": sql, "source": "tsql", "target": "oracle"},
        )
        assert response.status_code == 200

    def test_internal_errors_do_not_leak_details(self, client, monkeypatch) -> None:
        from unique.api import app as app_module

        def boom(*args, **kwargs):
            raise RuntimeError("secret-db-url-oracle://scott:tiger@host")

        monkeypatch.setattr(app_module._transpiler, "transpile", boom)
        response = client.post(
            "/api/v1/transpile",
            json={"sql": "SELECT 1", "source": "tsql", "target": "postgresql"},
        )
        assert response.status_code == 500
        assert "secret-db-url" not in response.text
        assert "tiger" not in response.text

    def test_endpoints_are_threadpool_safe(self) -> None:
        # CPU-bound handlers must be plain functions so FastAPI runs them in
        # its threadpool instead of blocking the event loop (audit A1).
        import inspect

        from unique.api import app as app_module

        for fn in (
            app_module.transpile_sql,
            app_module.validate_sql,
            app_module.transpile_file,
            app_module.detect_sql_dialect,
        ):
            assert not inspect.iscoroutinefunction(fn), fn.__name__

    def test_utf16_upload_decoded(self, client) -> None:
        payload = "SELECT N'ñ' AS x".encode("utf-16")
        response = client.post(
            "/api/v1/transpile/file",
            files={"file": ("script.sql", payload, "text/plain")},
            data={"source": "tsql", "target": "postgresql"},
        )
        assert response.status_code == 200
        assert "ñ" in response.text


class TestNamedDsns:
    """Server-side named DSNs (audit 2026-07-02, A3 — SSRF hardening).

    The API references databases by name (``db``); the URL lives in a
    ``UNIQUE_DSN_<NAME>`` env var on the server. A raw ``db_url`` is a
    separate, stronger opt-in (``UNIQUE_ALLOW_RAW_DB_URL``) because it lets
    any client make the server dial arbitrary hosts with arbitrary
    credentials.
    """

    def test_named_dsn_resolves(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("UNIQUE_ALLOW_DB_CONNECTION", "1")
        monkeypatch.setenv("UNIQUE_DSN_HR_TEST", "postgresql://u:p@127.0.0.1:1/none")
        resp = client.post(
            "/api/v1/transpile",
            json={
                "sql": "SELECT 1;",
                "source": "tsql",
                "target": "oracle",
                "db": "hr-test",
            },
        )
        # The DSN is unreachable, but plain SQL needs no metadata: 200.
        assert resp.status_code == 200

    def test_unknown_name_is_a_client_error(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("UNIQUE_ALLOW_DB_CONNECTION", "1")
        resp = client.post(
            "/api/v1/transpile",
            json={
                "sql": "SELECT 1;",
                "source": "tsql",
                "target": "oracle",
                "db": "nope",
            },
        )
        assert resp.status_code == 400
        # Never echo configured URLs.
        assert "://" not in resp.json()["detail"]

    def test_named_dsn_requires_connections_enabled(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("UNIQUE_DSN_HR_TEST", "postgresql://u:p@127.0.0.1:1/none")
        resp = client.post(
            "/api/v1/transpile",
            json={
                "sql": "SELECT 1;",
                "source": "tsql",
                "target": "oracle",
                "db": "hr-test",
            },
        )
        assert resp.status_code == 403

    def test_raw_db_url_needs_extra_opt_in(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # UNIQUE_ALLOW_DB_CONNECTION alone no longer admits raw URLs.
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
        assert resp.status_code == 403
        assert "UNIQUE_ALLOW_RAW_DB_URL" in resp.json()["detail"]

    def test_raw_db_url_with_both_flags(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("UNIQUE_ALLOW_DB_CONNECTION", "1")
        monkeypatch.setenv("UNIQUE_ALLOW_RAW_DB_URL", "1")
        resp = client.post(
            "/api/v1/transpile",
            json={
                "sql": "SELECT 1;",
                "source": "tsql",
                "target": "oracle",
                "db_url": "postgresql://u:p@127.0.0.1:1/none",
            },
        )
        assert resp.status_code == 200

    def test_info_lists_dsn_names_not_urls(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("UNIQUE_ALLOW_DB_CONNECTION", "1")
        monkeypatch.setenv("UNIQUE_DSN_HR_TEST", "postgresql://u:p@127.0.0.1:1/none")
        resp = client.get("/api/v1/info")
        assert resp.status_code == 200
        data = resp.json()
        assert "hr-test" in data["db_names"]
        assert "://" not in " ".join(data["db_names"])

    def test_file_endpoint_accepts_named_dsn(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("UNIQUE_ALLOW_DB_CONNECTION", "1")
        monkeypatch.setenv("UNIQUE_DSN_HR_TEST", "postgresql://u:p@127.0.0.1:1/none")
        resp = client.post(
            "/api/v1/transpile/file",
            files={"file": ("q.sql", b"SELECT 1;")},
            data={"source": "tsql", "target": "oracle", "db": "hr-test"},
        )
        assert resp.status_code == 200


class TestDbConnectionBuilderUI:
    """The web UI's structured connection builder (engine/host/port/db/user/
    password) must exist in the generated page and stay in sync with the
    template (the generated file is built from web/src via web/build.py)."""

    def test_builder_markup_present_in_generated_page(self) -> None:
        from pathlib import Path

        static = (
            Path(__file__).resolve().parents[3] / "src/unique/api/static/index.html"
        ).read_text(encoding="utf-8")
        for element_id in (
            "dbBuilder",
            "dbEngine",
            "dbHost",
            "dbPort",
            "dbBase",
            "dbUser",
            "dbPass",
        ):
            assert f'id="{element_id}"' in static, element_id
        # The builder assembles the URL client-side and sends db_url.
        assert "builtDbUrl" in static

    def test_template_and_generated_page_agree(self) -> None:
        from pathlib import Path

        root = Path(__file__).resolve().parents[3]
        template = (root / "web/src/index.template.html").read_text(encoding="utf-8")
        static = (root / "src/unique/api/static/index.html").read_text(encoding="utf-8")
        for element_id in ("dbBuilder", "dbEngine"):
            assert (f'id="{element_id}"' in template) == (
                f'id="{element_id}"' in static
            ), f"template/static drift on #{element_id} — rerun web/build.py"


class TestValidateDetectSizeCap:
    """N6: /validate and /detect enforce the same size cap as /transpile."""

    def test_validate_rejects_oversized_sql(self) -> None:
        import unique.api.app as app_module

        big = "SELECT 1;" * (app_module.MAX_SQL_BYTES // 9 + 2)
        client = TestClient(app)
        resp = client.post("/api/v1/validate", json={"sql": big, "dialect": "tsql"})
        assert resp.status_code == 422

    def test_detect_rejects_oversized_sql(self) -> None:
        import unique.api.app as app_module

        big = "SELECT 1;" * (app_module.MAX_SQL_BYTES // 9 + 2)
        client = TestClient(app)
        resp = client.post("/api/v1/detect", json={"sql": big})
        assert resp.status_code == 422
