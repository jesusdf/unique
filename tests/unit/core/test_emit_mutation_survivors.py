# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Targeted assertions for emit.py mutation survivors.

The nightly mutation job's survivor list mapped these branch decisions
as un-asserted (a covered line whose outcome no test checked); each test
here pins one decision so the operator/comparison cannot silently flip.
"""

from __future__ import annotations

import re

from unique.core.transpiler import Transpiler


def _t(sql: str, source: str, target: str):
    return Transpiler().transpile(sql, source=source, target=target)


class TestCteDmlGate:
    """_cte_dml_unsupported: dialect branches and the CTE-name check."""

    _CTE_UPDATE = (
        "with c as (select id from t where x > 0) " "update c set y = 1 where id = 2;"
    )

    def test_mysql_cte_target_carrier(self) -> None:
        r = _t(self._CTE_UPDATE, "tsql", "mysql")
        assert "cannot update through a CTE" in r.sql, r.sql
        assert not any(
            ln.strip() and not ln.strip().startswith("--") for ln in r.sql.splitlines()
        ), r.sql

    def test_oracle_no_with_on_dml_carrier(self) -> None:
        r = _t(
            "with c as (select 1 as x) update t set y = 1 where t.id in "
            "(select x from c);",
            "tsql",
            "oracle",
        )
        assert "Oracle has no WITH clause on UPDATE/DELETE" in r.sql, r.sql

    def test_tsql_target_keeps_cte_update(self) -> None:
        r = _t(self._CTE_UPDATE, "tsql", "tsql")
        assert "UNIQUE:" not in r.sql, r.sql
        assert re.search(r"(?i)WITH c AS", r.sql), r.sql

    def test_non_cte_update_untouched_mysql(self) -> None:
        r = _t("update t set y = 1 where id = 2;", "tsql", "mysql")
        assert "UNIQUE:" not in r.sql, r.sql
        assert re.search(r"(?i)UPDATE t", r.sql), r.sql


class TestPgIndexRebuildDecisions:
    """_pg_index_to_tsql / _tsql_index_predicate branch outcomes."""

    def test_desc_marker_kept(self) -> None:
        r = _t("create index i9 on t9(a desc);", "postgresql", "tsql")
        assert re.search(r"(?i)\(a DESC\)", r.sql), r.sql

    def test_is_null_predicate_renders(self) -> None:
        r = _t("create index i8 on t8(a) where a is null;", "postgresql", "tsql")
        assert re.search(r"(?i)WHERE a IS NULL", r.sql), r.sql

    def test_and_predicate_renders_both_arms(self) -> None:
        r = _t(
            "create index i7 on t7(a) where a is not null and b is not null;",
            "postgresql",
            "tsql",
        )
        assert re.search(r"(?i)WHERE a IS NOT NULL AND b IS NOT NULL", r.sql), r.sql

    def test_unnamed_unique_gets_nulls_note(self) -> None:
        r = _t("create unique index on t6(a);", "postgresql", "tsql")
        assert re.search(r"(?i)CREATE UNIQUE INDEX \w+ ON t6 \(a\)", r.sql), r.sql
        assert "NULLs as distinct" in r.sql, r.sql


class TestCreateTableDefaultRewrites:
    """Per-target DEFAULT rewrites in _emit_create_table."""

    _SRC = "CREATE TABLE d1 (id UNIQUEIDENTIFIER DEFAULT NEWID(), ts DATETIME2 DEFAULT CURRENT_TIMESTAMP())"

    def test_oracle_newid_becomes_sys_guid(self) -> None:
        r = _t(self._SRC, "tsql", "oracle")
        assert re.search(r"(?i)DEFAULT SYS_GUID\(\)", r.sql), r.sql
        assert "NEWID" not in r.sql.upper(), r.sql

    def test_mysql_newid_becomes_uuid(self) -> None:
        r = _t(self._SRC, "tsql", "mysql")
        assert re.search(r"(?i)DEFAULT \(?UUID\(\)\)?", r.sql), r.sql
        assert "NEWID" not in r.sql.upper(), r.sql

    def test_pg_current_timestamp_loses_parens(self) -> None:
        r = _t(self._SRC, "tsql", "postgresql")
        assert not re.search(r"(?i)CURRENT_TIMESTAMP\(\)", r.sql), r.sql
        assert re.search(r"(?i)CURRENT_TIMESTAMP", r.sql), r.sql
