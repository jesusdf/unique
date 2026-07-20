"""Tests for the transformation engine."""

from unique.core.ast_nodes import (
    BinaryOp,
    BinaryOperator,
    CaseExpression,
    CastExpression,
    DataType,
    FunctionCall,
    Literal,
    SelectStatement,
    TableRef,
)
from unique.core.transformer import (
    FunctionNormalizer,
    SyntaxNormalizer,
    TransformContext,
    Transformer,
    TypeMapper,
)


def _ctx(source: str = "tsql", target: str = "postgresql") -> TransformContext:
    return TransformContext(source=source, target=target)


class TestFunctionNormalizer:
    def test_isnull_to_coalesce(self) -> None:
        fn = FunctionCall(name="ISNULL", args=(Literal(value="a"), Literal(value=0)))
        result = FunctionNormalizer().visit(fn, _ctx())
        assert isinstance(result, FunctionCall)
        assert result.name == "COALESCE"
        assert len(result.args) == 2

    def test_nvl_to_coalesce(self) -> None:
        fn = FunctionCall(name="NVL", args=(Literal(value="a"), Literal(value=0)))
        result = FunctionNormalizer().visit(fn, _ctx(source="oracle"))
        assert isinstance(result, FunctionCall)
        assert result.name == "COALESCE"

    def test_getdate_to_current_timestamp(self) -> None:
        fn = FunctionCall(name="GETDATE", args=())
        result = FunctionNormalizer().visit(fn, _ctx())
        assert isinstance(result, FunctionCall)
        assert result.name == "CURRENT_TIMESTAMP"

    def test_len_to_length(self) -> None:
        fn = FunctionCall(name="LEN", args=(Literal(value="hello"),))
        result = FunctionNormalizer().visit(fn, _ctx())
        assert isinstance(result, FunctionCall)
        assert result.name == "LENGTH"

    def test_iif_to_case(self) -> None:
        fn = FunctionCall(
            name="IIF",
            args=(
                BinaryOp(
                    operator=BinaryOperator.GT,
                    left=Literal(value=1),
                    right=Literal(value=0),
                ),
                Literal(value="yes"),
                Literal(value="no"),
            ),
        )
        result = FunctionNormalizer().visit(fn, _ctx())
        assert isinstance(result, CaseExpression)
        assert len(result.whens) == 1
        assert result.else_expr is not None

    def test_decode_to_case(self) -> None:
        fn = FunctionCall(
            name="DECODE",
            args=(
                Literal(value="A"),
                Literal(value="A"),
                Literal(value=1),
                Literal(value="B"),
                Literal(value=2),
                Literal(value=0),
            ),
        )
        ctx = _ctx(source="oracle")
        result = FunctionNormalizer().visit(fn, ctx)
        assert isinstance(result, CaseExpression)
        assert len(result.whens) == 2
        assert result.else_expr is not None

    def test_unknown_function_unchanged(self) -> None:
        fn = FunctionCall(name="MY_CUSTOM_FUNC", args=(Literal(value=1),))
        result = FunctionNormalizer().visit(fn, _ctx())
        assert result is fn  # Unchanged

    def test_non_function_unchanged(self) -> None:
        lit = Literal(value=42)
        result = FunctionNormalizer().visit(lit, _ctx())
        assert result is lit


class TestTypeMapper:
    def test_varchar2_to_varchar(self) -> None:
        dt = DataType(name="VARCHAR2", params=("100",))
        ctx = _ctx(source="oracle", target="postgresql")
        result = TypeMapper().visit(dt, ctx)
        assert isinstance(result, DataType)
        assert result.name == "VARCHAR"

    def test_bit_to_boolean(self) -> None:
        dt = DataType(name="BIT")
        ctx = _ctx(source="tsql", target="postgresql")
        result = TypeMapper().visit(dt, ctx)
        assert isinstance(result, DataType)
        assert result.name == "BOOLEAN"

    def test_cast_expression_type_mapped(self) -> None:
        cast = CastExpression(
            expression=Literal(value="x"),
            target_type=DataType(name="UNIQUEIDENTIFIER"),
        )
        ctx = _ctx(source="tsql", target="postgresql")
        result = TypeMapper().visit(cast, ctx)
        assert isinstance(result, CastExpression)
        assert result.target_type.name == "UUID"

    def test_bit_cast_normalizes_to_sign_abs(self) -> None:
        # T-SQL CAST(x AS BIT) is a 0/1 normalization, not a plain type change;
        # emit SIGN(ABS(x)) so a non-zero value becomes 1 (0 -> 0, NULL -> NULL).
        cast = CastExpression(
            expression=Literal(value=2),
            target_type=DataType(name="BIT"),
        )
        ctx = _ctx(source="tsql", target="oracle")
        result = TypeMapper().visit(cast, ctx)
        assert isinstance(result, FunctionCall)
        assert result.name == "SIGN"
        assert isinstance(result.args[0], FunctionCall)
        assert result.args[0].name == "ABS"

    def test_unknown_type_unchanged(self) -> None:
        dt = DataType(name="INT")
        ctx = _ctx(source="tsql", target="postgresql")
        result = TypeMapper().visit(dt, ctx)
        assert result is dt  # INT is the same everywhere


class TestSyntaxNormalizer:
    def test_concat_to_function_for_mysql(self) -> None:
        node = BinaryOp(
            operator=BinaryOperator.CONCAT,
            left=Literal(value="a"),
            right=Literal(value="b"),
        )
        ctx = _ctx(source="tsql", target="mysql")
        result = SyntaxNormalizer().visit(node, ctx)
        assert isinstance(result, FunctionCall)
        assert result.name == "CONCAT"

    def test_concat_unchanged_for_postgresql(self) -> None:
        node = BinaryOp(
            operator=BinaryOperator.CONCAT,
            left=Literal(value="a"),
            right=Literal(value="b"),
        )
        ctx = _ctx(source="tsql", target="postgresql")
        result = SyntaxNormalizer().visit(node, ctx)
        assert isinstance(result, BinaryOp)
        assert result.operator == BinaryOperator.CONCAT


class TestTransformer:
    def test_transform_applies_all_passes(self) -> None:
        fn = FunctionCall(name="ISNULL", args=(Literal(value="a"), Literal(value=0)))
        stmt = SelectStatement(
            columns=(fn,),
            from_clause=TableRef(name="t"),
        )
        transformer = Transformer("tsql", "postgresql")
        result = transformer.transform([stmt])
        assert len(result) == 1
        transformed = result[0]
        assert isinstance(transformed, SelectStatement)
        col = transformed.columns[0]
        assert isinstance(col, FunctionCall)
        assert col.name == "COALESCE"

    def test_warnings_collected(self) -> None:
        transformer = Transformer("tsql", "postgresql")
        transformer.context.warn("test warning", "test_feature")
        assert len(transformer.warnings) == 1
        assert transformer.warnings[0].message == "test warning"

    def test_unsupported_collected(self) -> None:
        transformer = Transformer("tsql", "postgresql")
        transformer.context.mark_unsupported("GOTO")
        assert "GOTO" in transformer.unsupported
