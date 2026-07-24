"""Tests for the unread-args tripwire (audit 2026-07-24 T1 / brief B2).

The tripwire wraps a sqlglot node's ``args`` dict during its ``_convert_*``
call and records which keys were read. A semantic key left unread means a
construct sqlglot parsed but the converter silently dropped (N1 ``ON
CONFLICT``, N3 OUTPUT tail, N4 ``DO NOTHING`` were all this class).
"""

from __future__ import annotations

import pytest
import sqlglot.expressions as exp

from unique.core.converter import _unread_args as ua
from unique.core.transpiler import Transpiler


class TestTrackingMechanism:
    """The read-tracking dict + report primitive in isolation."""

    def test_reports_unread_semantic_arg(self) -> None:
        # A node with two semantic args; the converter reads only one.
        node = exp.Insert(this=exp.to_table("t"), expression=exp.select("1"))
        node.set("conflict", exp.OnConflict())
        tracked = ua._ReadTrackingArgs(node.args)
        tracked.get("this")
        tracked.get("expression")
        # "conflict" was NOT read -> residue.
        ua.reset_sink()
        ua.report_unread_args(node, tracked, "warn")
        msgs = ua.drain_sink()
        assert msgs == [
            "internal: unread sqlglot arg 'conflict' on Insert — "
            "construct may be dropped"
        ]

    def test_read_arg_is_not_reported(self) -> None:
        node = exp.Insert(this=exp.to_table("t"))
        node.set("conflict", exp.OnConflict())
        tracked = ua._ReadTrackingArgs(node.args)
        tracked.get("this")
        tracked.get("conflict")  # read it
        ua.reset_sink()
        ua.report_unread_args(node, tracked, "warn")
        assert ua.drain_sink() == []

    def test_empty_container_arg_is_not_reported(self) -> None:
        # An empty list/tuple carries no construct -> never flagged.
        node = exp.Select()
        node.set("joins", [])
        tracked = ua._ReadTrackingArgs(node.args)
        ua.reset_sink()
        ua.report_unread_args(node, tracked, "warn")
        assert ua.drain_sink() == []

    def test_gate_mode_raises(self) -> None:
        node = exp.Insert(this=exp.to_table("t"))
        node.set("conflict", exp.OnConflict())
        tracked = ua._ReadTrackingArgs(node.args)
        tracked.get("this")
        ua.reset_sink()
        with pytest.raises(ua.UnreadArgError):
            ua.report_unread_args(node, tracked, "gate")
        # The warning is still recorded before the raise.
        assert ua.drain_sink() == [
            "internal: unread sqlglot arg 'conflict' on Insert — "
            "construct may be dropped"
        ]

    def test_iterating_args_marks_all_read(self) -> None:
        # A converter/generator that enumerates every arg (e.g. re-rendering
        # the whole node) drops nothing, so nothing must be flagged.
        node = exp.Insert(this=exp.to_table("t"))
        node.set("conflict", exp.OnConflict())
        tracked = ua._ReadTrackingArgs(node.args)
        list(tracked.values())
        ua.reset_sink()
        ua.report_unread_args(node, tracked, "warn")
        assert ua.drain_sink() == []


class TestConverterIntegration:
    """The tripwire fires through the real conversion dispatch."""

    def test_n1_on_conflict_warns_pre_b1(self, transpiler: Transpiler) -> None:
        # N1: sqlglot models ON CONFLICT as Insert.args["conflict"];
        # _convert_insert never reads it (until B1 lands). The tripwire flags
        # the silent drop.
        sql = (
            "INSERT INTO kv (k, v) VALUES ('a', 1) "
            "ON CONFLICT (k) DO UPDATE SET v = EXCLUDED.v + 1;"
        )
        result = transpiler.transpile(sql, source="postgresql", target="mysql")
        unread = [w.message for w in result.warnings if w.feature == "unread_args"]
        assert any(
            "unread sqlglot arg 'conflict' on Insert" in m for m in unread
        ), unread

    def test_off_mode_suppresses(
        self, transpiler: Transpiler, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("UNIQUE_UNREAD_ARGS", "off")
        sql = (
            "INSERT INTO kv (k, v) VALUES ('a', 1) "
            "ON CONFLICT (k) DO UPDATE SET v = EXCLUDED.v + 1;"
        )
        result = transpiler.transpile(sql, source="postgresql", target="mysql")
        assert not [w for w in result.warnings if w.feature == "unread_args"]

    def test_gate_mode_degrades_to_carrier(
        self, transpiler: Transpiler, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("UNIQUE_UNREAD_ARGS", "gate")
        sql = (
            "INSERT INTO kv (k, v) VALUES ('a', 1) "
            "ON CONFLICT (k) DO UPDATE SET v = EXCLUDED.v + 1;"
        )
        result = transpiler.transpile(sql, source="postgresql", target="mysql")
        # The whole statement degrades to a carrier that preserves the source,
        # and the unread-args warning is surfaced.
        assert "ON CONFLICT" in result.sql
        assert any(w.feature == "unread_args" for w in result.warnings)

    def test_clean_statement_has_no_unread_warning(
        self, transpiler: Transpiler
    ) -> None:
        result = transpiler.transpile(
            "SELECT a, b FROM t WHERE a > 1 ORDER BY b",
            source="postgresql",
            target="mysql",
        )
        assert not [w for w in result.warnings if w.feature == "unread_args"]


def _iter_fixture_sql() -> list[tuple[str, str]]:
    """(path, sql) for every standard fixture the sweep covers."""
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[2] / "fixtures"
    out: list[tuple[str, str]] = []
    for sub in ("sql", "corpus", "real_world"):
        d = root / sub
        if not d.is_dir():
            continue
        for p in sorted(d.rglob("*.sql")):
            out.append((str(p), p.read_text(encoding="utf-8", errors="ignore")))
    return out


class TestFixtureCorpusClean:
    """Regression: the standard fixture set produces no unread-args warnings
    (the empirical findings are either burned down or allowlisted)."""

    def test_no_unread_args_over_fixtures(self, transpiler: Transpiler) -> None:
        offenders: dict[tuple[str, str], str] = {}
        directions = [
            ("tsql", "postgresql"),
            ("postgresql", "tsql"),
            ("oracle", "mysql"),
            ("mysql", "oracle"),
        ]
        for path, sql in _iter_fixture_sql():
            src = _detect_src(path)
            for source, target in directions:
                if src is not None and src != source:
                    continue
                try:
                    result = transpiler.transpile(sql, source=source, target=target)
                except Exception:
                    continue
                for w in result.warnings:
                    if w.feature != "unread_args":
                        continue
                    key = _pair(w.message)
                    if key is not None:
                        offenders.setdefault(key, f"{path} [{source}->{target}]")
        assert not offenders, "unread-args residue over fixtures:\n" + "\n".join(
            f"  {nt}.{arg}  first: {where}"
            for (nt, arg), where in sorted(offenders.items())
        )


def _detect_src(path: str) -> str | None:
    low = path.lower()
    if "sqlserver" in low or "tsql" in low or "mssql" in low:
        return "tsql"
    if "oracle" in low or "plsql" in low:
        return "oracle"
    if "postgres" in low or "_pg" in low or "postgresql" in low:
        return "postgresql"
    if "mysql" in low:
        return "mysql"
    return None


def _pair(message: str) -> tuple[str, str] | None:
    import re

    m = re.search(r"unread sqlglot arg '([^']+)' on (\w+)", message)
    if m is None:
        return None
    return (m.group(2), m.group(1))
