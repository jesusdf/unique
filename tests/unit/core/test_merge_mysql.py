"""MERGE -> MySQL upsert rewrite (audit 2026-07-02, S1-3).

MySQL has no MERGE. The canonical single-UPDATE/single-INSERT pattern is
rewritten as ``INSERT ... SELECT ... ON DUPLICATE KEY UPDATE``; anything more
complex falls back to a carrier comment, which the no-silent-loss invariant
turns into a warning + unsupported entry.
"""

from unique.core.transpiler import Transpiler

CANONICAL = (
    "MERGE INTO t USING s ON t.id = s.id "
    "WHEN MATCHED THEN UPDATE SET t.v = s.v, t.w = s.w "
    "WHEN NOT MATCHED THEN INSERT (id, v, w) VALUES (s.id, s.v, s.w);"
)


class TestMergeToMySQL:
    def setup_method(self) -> None:
        self.t = Transpiler()

    def test_canonical_merge_becomes_upsert(self) -> None:
        out = self.t.transpile(CANONICAL, "tsql", "mysql").sql
        executable = "\n".join(
            ln for ln in out.splitlines() if not ln.lstrip().startswith("--")
        )
        assert "MERGE" not in executable.upper()
        assert "INSERT INTO t" in executable
        assert "SELECT" in out and "FROM s" in out
        assert "ON DUPLICATE KEY UPDATE" in out
        assert "v = VALUES(v)" in out
        assert "w = VALUES(w)" in out

    def test_upsert_signals_key_assumption(self) -> None:
        result = self.t.transpile(CANONICAL, "tsql", "mysql")
        # The rewrite assumes a UNIQUE/PK on the ON columns; that assumption
        # must be visible both in the SQL and in the result object.
        assert "UNIQUE-1001:" in result.sql
        assert result.warnings

    def test_oracle_merge_source_dialect_also_rewrites(self) -> None:
        sql = (
            "MERGE INTO t USING s ON (t.id = s.id) "
            "WHEN MATCHED THEN UPDATE SET t.v = s.v "
            "WHEN NOT MATCHED THEN INSERT (id, v) VALUES (s.id, s.v);"
        )
        out = self.t.transpile(sql, "oracle", "mysql").sql
        assert "ON DUPLICATE KEY UPDATE" in out

    def test_complex_merge_falls_back_with_signal(self) -> None:
        sql = (
            "MERGE INTO t USING s ON t.id = s.id "
            "WHEN MATCHED THEN DELETE "
            "WHEN NOT MATCHED THEN INSERT (id) VALUES (s.id);"
        )
        result = self.t.transpile(sql, "tsql", "mysql")
        # WHEN MATCHED DELETE has no upsert equivalent: no invalid SQL, and
        # the drop is signalled.
        executable = "\n".join(
            ln for ln in result.sql.splitlines() if not ln.lstrip().startswith("--")
        )
        assert "ON DUPLICATE KEY UPDATE" not in executable
        assert result.warnings
        assert result.unsupported

    def test_merge_to_postgresql_unaffected(self) -> None:
        out = self.t.transpile(CANONICAL, "tsql", "postgresql").sql
        assert "MERGE INTO" in out
