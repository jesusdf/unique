"""Guard against an IR node's Python repr leaking into the emitted SQL.

When an emit path falls through to ``str(node)``/``repr(node)`` (e.g. an EXISTS
subquery whose operand is a bare ``SelectStatement``), the dataclass repr —
``SelectStatement(location=SourceLocation(...), ...)`` — ends up in the output.
Every IR node's repr contains ``SourceLocation(``, so that (plus the node class
names) is a reliable, generic marker.
"""

import re

import sqlglot

from unique.core.transpiler import Transpiler

_READ = {"tsql": "tsql", "postgresql": "postgres", "mysql": "mysql", "oracle": "oracle"}

# Any of these followed by "(" means an IR-node repr leaked into the SQL.
_IR_REPR = re.compile(
    r"\b(?:SourceLocation|SelectStatement|InsertStatement|UpdateStatement|"
    r"DeleteStatement|CreateTableStatement|RawSQL|TableRef|ColumnRef|BinaryOp|"
    r"UnaryOp|FunctionCall|SubqueryExpression|CaseExpression|CastExpression|"
    r"WindowFunction|JoinClause|OrderByItem)\("
)

t = Transpiler()

_TARGETS = ("postgresql", "oracle", "mysql", "tsql")


def _assert_clean(sql: str, source: str) -> None:
    for target in _TARGETS:
        out = t.transpile(sql, source, target).sql
        m = _IR_REPR.search(out)
        assert m is None, (
            f"IR repr leaked ({source}->{target}): "
            f"…{out[max(0, m.start() - 25):m.start() + 45]}…"
        )
        # Also: the output must be parseable target SQL.
        sqlglot.parse(out, read=_READ[target], error_level=sqlglot.ErrorLevel.RAISE)


class TestNoIrReprLeak:
    def test_insert_select_where_not_exists(self) -> None:
        # The reported case: INSERT ... SELECT <literals> WHERE NOT EXISTS (…).
        _assert_clean(
            "INSERT INTO dbo.h_config (idconfig, nombre) "
            "SELECT 'x', dbo.Now() "
            "WHERE NOT EXISTS (SELECT NULL FROM dbo.h_config WHERE idconfig = 'x')",
            "tsql",
        )

    def test_exists_and_in_subqueries(self) -> None:
        for sql in (
            "SELECT a FROM t WHERE EXISTS (SELECT 1 FROM u WHERE u.a = t.a)",
            "SELECT a FROM t WHERE a IN (SELECT b FROM u)",
            "SELECT (SELECT MAX(b) FROM u) AS m FROM t",
            "SELECT a FROM t WHERE NOT EXISTS (SELECT NULL FROM u WHERE u.a = t.a)",
        ):
            _assert_clean(sql, "tsql")

    def test_from_not_pulled_from_subquery(self) -> None:
        # The outer table-less SELECT must not steal the NOT EXISTS subquery's
        # FROM (regression: it produced `SELECT 'x' FROM h_config WHERE …`).
        out = t.transpile(
            "INSERT INTO h (a) SELECT 'x' "
            "WHERE NOT EXISTS (SELECT NULL FROM other WHERE a = 'x')",
            "tsql",
            "postgresql",
        ).sql
        # `other` belongs to the subquery only; the outer SELECT has no FROM.
        assert re.search(r"(?i)SELECT 'x'\s+WHERE", out), out
