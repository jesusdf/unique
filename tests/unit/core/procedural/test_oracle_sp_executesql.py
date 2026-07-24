"""T-SQL ``sp_executesql`` -> Oracle parameterized ``EXECUTE IMMEDIATE … USING``.

``EXEC sp_executesql @stmt, N'<paramdefs>', @a, @b`` runs @stmt with the values
bound positionally. Oracle's equivalent is ``EXECUTE IMMEDIATE @stmt USING @a,
@b`` — the parameter-definition string is dropped (Oracle infers bind types).
"""

import re

from unique.core.transpiler import Transpiler

t = Transpiler()


class TestSpExecuteSql:
    def test_binds_become_using(self) -> None:
        out = t.transpile(
            "CREATE PROCEDURE p AS BEGIN\n"
            "  DECLARE @s NVARCHAR(100)\n"
            "  EXEC sp_executesql @s, N'@x int, @y int', @a, @b\nEND",
            "tsql",
            "oracle",
        ).sql
        up = out.upper()
        # Binds are positional; the trailing UNIQUE note documents that the
        # dynamic string's placeholders must be :1, :2, … .
        assert "EXECUTE IMMEDIATE V_S USING V_A, V_B;" in up, out
        code = re.sub(r"/\*.*?\*/", "", up, flags=re.S)
        assert "SP_EXECUTESQL" not in code, out
        assert "POSITIONALLY" in up, out

    def test_no_binds(self) -> None:
        out = t.transpile(
            "CREATE PROCEDURE p AS BEGIN\n"
            "  DECLARE @s NVARCHAR(100)\n"
            "  EXEC sp_executesql @s\nEND",
            "tsql",
            "oracle",
        ).sql
        assert "EXECUTE IMMEDIATE V_S" in out.upper(), out
        assert "SP_EXECUTESQL" not in out.upper(), out
