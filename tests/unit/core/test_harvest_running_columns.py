# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Running COLUMN_TYPES / COLUMN_NOT_NULL scan (B10, audit 2026-07-24 N9).

``harvest_column_not_null`` seeds per-column NOT NULL knowledge from CREATE
TABLE bodies; ``fold_alter_into_running_types`` applies each ALTER TABLE
statement to both maps in statement order so later emissions read the current
type/nullability rather than the stale CREATE snapshot.
"""

from __future__ import annotations

from unique.core.converter.harvest import (
    fold_alter_into_running_types,
    harvest_column_not_null,
)


class TestHarvestColumnNotNull:
    def test_create_table_columns(self) -> None:
        out = harvest_column_not_null(
            "CREATE TABLE t (a INT NOT NULL, b TEXT, c INT PRIMARY KEY);"
        )
        assert out == {"t": {"a": True, "b": False, "c": True}}

    def test_table_level_primary_key_implies_not_null(self) -> None:
        out = harvest_column_not_null(
            "CREATE TABLE t (a INT, b TEXT, PRIMARY KEY (a));"
        )
        assert out["t"]["a"] is True
        assert out["t"]["b"] is False

    def test_constraint_items_not_recorded_as_columns(self) -> None:
        out = harvest_column_not_null(
            "CREATE TABLE t (a INT, CONSTRAINT ck CHECK (a > 0), UNIQUE (a));"
        )
        assert set(out["t"]) == {"a"}


class TestFoldAlterIntoRunningTypes:
    def _maps(self) -> tuple[dict, dict]:
        return {"t": {"a": "INT"}}, {"t": {"a": True}}

    def test_pg_type_change_updates_type_keeps_nullability(self) -> None:
        ct, nn = self._maps()
        fold_alter_into_running_types(
            "ALTER TABLE t ALTER COLUMN a TYPE BIGINT;", "postgresql", ct, nn
        )
        assert ct["t"]["a"] == "BIGINT"
        assert nn["t"]["a"] is True

    def test_drop_not_null_updates_nullability_only(self) -> None:
        ct, nn = self._maps()
        fold_alter_into_running_types(
            "ALTER TABLE t ALTER COLUMN a DROP NOT NULL;", "postgresql", ct, nn
        )
        assert ct["t"]["a"] == "INT"
        assert nn["t"]["a"] is False

    def test_add_column_records_type_and_nullability(self) -> None:
        ct, nn = self._maps()
        fold_alter_into_running_types(
            "ALTER TABLE t ADD COLUMN c SMALLINT NOT NULL;", "postgresql", ct, nn
        )
        assert ct["t"]["c"] == "SMALLINT"
        assert nn["t"]["c"] is True

    def test_add_constraint_is_not_a_column(self) -> None:
        ct, nn = self._maps()
        fold_alter_into_running_types(
            "ALTER TABLE t ADD CONSTRAINT u1 UNIQUE (a);", "postgresql", ct, nn
        )
        assert set(ct["t"]) == {"a"}
        assert set(nn["t"]) == {"a"}

    def test_rename_column_moves_both_maps(self) -> None:
        ct, nn = self._maps()
        fold_alter_into_running_types(
            "ALTER TABLE t RENAME COLUMN a TO a2;", "postgresql", ct, nn
        )
        assert ct["t"] == {"a2": "INT"}
        assert nn["t"] == {"a2": True}

    def test_unknown_table_is_a_noop(self) -> None:
        ct, nn = self._maps()
        fold_alter_into_running_types(
            "ALTER TABLE other ALTER COLUMN x TYPE BIGINT;", "postgresql", ct, nn
        )
        assert ct == {"t": {"a": "INT"}}
        assert nn == {"t": {"a": True}}

    def test_mysql_modify_resets_not_null_unless_restated(self) -> None:
        ct, nn = self._maps()
        fold_alter_into_running_types(
            "ALTER TABLE t MODIFY COLUMN a BIGINT;", "mysql", ct, nn
        )
        assert ct["t"]["a"] == "BIGINT"
        assert nn["t"]["a"] is False
        fold_alter_into_running_types(
            "ALTER TABLE t MODIFY COLUMN a BIGINT NOT NULL;", "mysql", ct, nn
        )
        assert nn["t"]["a"] is True

    def test_oracle_modify_updates_type(self) -> None:
        ct, nn = self._maps()
        fold_alter_into_running_types(
            "ALTER TABLE t MODIFY (a NUMBER(19));", "oracle", ct, nn
        )
        assert ct["t"]["a"] == "NUMBER(19)"
        assert nn["t"]["a"] is True
