"""Tests for IR AST node definitions."""

from unique.core.ast_nodes import (
    ColumnRef,
    FunctionCall,
    LimitClause,
    Literal,
    SelectStatement,
    SourceLocation,
    Star,
    TableRef,
)


class TestSourceLocation:
    def test_defaults_to_none(self) -> None:
        loc = SourceLocation()
        assert loc.line is None
        assert loc.column is None

    def test_with_position(self) -> None:
        loc = SourceLocation(line=1, column=5)
        assert loc.line == 1
        assert loc.column == 5


class TestASTNodeBase:
    def test_default_location(self) -> None:
        node = Literal(value=42)
        assert node.location == SourceLocation()

    def test_frozen(self) -> None:
        node = Literal(value=1)
        try:
            node.value = 2  # type: ignore[misc]
            raise AssertionError("Should be frozen")
        except AttributeError:
            pass


class TestLiteral:
    def test_integer(self) -> None:
        lit = Literal(value=42, dtype="int")
        assert lit.value == 42
        assert lit.dtype == "int"

    def test_string(self) -> None:
        lit = Literal(value="hello")
        assert lit.value == "hello"

    def test_null(self) -> None:
        lit = Literal(value=None, dtype="null")
        assert lit.value is None


class TestColumnRef:
    def test_simple(self) -> None:
        col = ColumnRef(name="id")
        assert col.name == "id"
        assert col.table is None

    def test_qualified(self) -> None:
        col = ColumnRef(name="id", table="users", schema="dbo")
        assert col.table == "users"
        assert col.schema == "dbo"


class TestTableRef:
    def test_simple(self) -> None:
        tbl = TableRef(name="users")
        assert tbl.name == "users"
        assert tbl.alias is None

    def test_aliased(self) -> None:
        tbl = TableRef(name="users", alias="u")
        assert tbl.alias == "u"


class TestFunctionCall:
    def test_no_args(self) -> None:
        fn = FunctionCall(name="GETDATE", args=())
        assert fn.name == "GETDATE"
        assert len(fn.args) == 0

    def test_with_args(self) -> None:
        fn = FunctionCall(
            name="COALESCE",
            args=(Literal(value="a"), Literal(value="b")),
        )
        assert len(fn.args) == 2


class TestSelectStatement:
    def test_minimal(self) -> None:
        stmt = SelectStatement(
            columns=(Star(),),
            from_clause=TableRef(name="t"),
        )
        assert len(stmt.columns) == 1
        assert isinstance(stmt.from_clause, TableRef)
        assert stmt.where is None
        assert stmt.limit is None

    def test_with_limit(self) -> None:
        stmt = SelectStatement(
            columns=(Star(),),
            from_clause=TableRef(name="t"),
            limit=LimitClause(limit=Literal(value=10)),
        )
        assert stmt.limit is not None
        assert stmt.limit.limit.value == 10  # type: ignore[union-attr]
