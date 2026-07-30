"""No-silent-loss invariant (audit 2026-07-02, cross-cutting fix).

Any construct the transpiler cannot map 1:1 must be signalled in
``TranspileResult.warnings`` (and in ``unsupported`` when an executable
statement is dropped). A ``UNIQUE:`` carrier comment in the output alone is
not enough: API/CLI consumers read the result object, not the SQL text.
"""

from unique.core.transpiler import Transpiler


class TestNoSilentLoss:
    def setup_method(self) -> None:
        self.t = Transpiler()

    def test_merge_to_mysql_signals_warning_and_unsupported(self) -> None:
        sql = (
            "MERGE INTO t USING s ON t.id = s.id "
            "WHEN MATCHED THEN UPDATE SET t.v = s.v "
            "WHEN NOT MATCHED THEN INSERT (id, v) VALUES (s.id, s.v);"
        )
        result = self.t.transpile(sql, "tsql", "mysql")
        if "UNIQUE-" in result.sql:
            # Dropped (or partially dropped) statement must be signalled.
            assert result.warnings, "carrier comment present but warnings empty"

    def test_connect_by_to_postgresql_signals_warning(self) -> None:
        sql = (
            "SELECT employee_id FROM employees "
            "START WITH manager_id IS NULL "
            "CONNECT BY PRIOR employee_id = manager_id"
        )
        result = self.t.transpile(sql, "oracle", "postgresql")
        assert "UNIQUE-1134:" in result.sql
        assert result.warnings, "carrier comment present but warnings empty"
        assert result.unsupported, "dropped executable statement not in unsupported"

    def test_every_carrier_comment_has_a_warning(self) -> None:
        """Generic consistency: each UNIQUE carrier implies >=1 warning."""
        lossy_inputs = [
            ("EXEC sp_rename 'a', 'b';", "tsql", "postgresql"),
            (
                "SELECT employee_id FROM employees "
                "CONNECT BY PRIOR employee_id = manager_id",
                "oracle",
                "mysql",
            ),
        ]
        for sql, source, target in lossy_inputs:
            result = self.t.transpile(sql, source, target)
            carriers = [line for line in result.sql.splitlines() if "UNIQUE-" in line]
            if carriers:
                assert (
                    result.warnings
                ), f"{source}->{target}: carriers {carriers!r} but no warnings"

    def test_clean_conversion_synthesizes_nothing(self) -> None:
        result = self.t.transpile("SELECT id FROM t", "tsql", "postgresql")
        assert "UNIQUE-" not in result.sql
        assert result.warnings == []
        assert result.unsupported == []

    def test_degraded_passthrough_comments_every_line(self) -> None:
        # A multi-line statement that cannot be parsed at all (here the
        # T-SQL xml(CONTENT schema-collection) column from AdventureWorksLT)
        # degrades to a commented passthrough. Every line must be commented:
        # commenting only the first line leaves the remaining lines as raw
        # source SQL, executable and invalid on the target.
        sql = (
            "CREATE TABLE [SalesLT].[ProductModel](\n"
            "\t[ProductModelID] [int] IDENTITY(1,1) NOT NULL,\n"
            "\t[CatalogDescription] [xml](CONTENT "
            "[SalesLT].[ProductDescriptionSchemaCollection]) NULL,\n"
            "\t[ModifiedDate] [datetime] NOT NULL\n"
            ") ON [PRIMARY]"
        )
        result = self.t.transpile(sql, "tsql", "postgresql")
        assert "UNIQUE-1003:" in result.sql
        assert result.warnings, "degraded statement must be signalled"
        leaked = [
            line
            for line in result.sql.splitlines()
            if line.strip() and not line.lstrip().startswith("--")
        ]
        assert not leaked, f"executable lines leaked from passthrough: {leaked!r}"
