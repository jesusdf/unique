"""Tests for the error hierarchy."""

import pytest

from unique.core.errors import (
    EmitError,
    ParseError,
    TransformError,
    UniqueError,
    UnknownDialectError,
    UnsupportedFeatureError,
)


class TestErrorHierarchy:
    """All custom errors should inherit from UniqueError."""

    @pytest.mark.parametrize(
        "error_cls",
        [
            ParseError,
            EmitError,
            UnsupportedFeatureError,
            UnknownDialectError,
            TransformError,
        ],
    )
    def test_inherits_from_unique_error(self, error_cls: type) -> None:
        assert issubclass(error_cls, UniqueError)

    def test_parse_error_message(self) -> None:
        err = ParseError("bad SQL", line=5, column=10)
        assert "bad SQL" in str(err)
        assert "line 5" in str(err)

    def test_unknown_dialect_error(self) -> None:
        err = UnknownDialectError("sqlite")
        assert "sqlite" in str(err)

    def test_unsupported_feature_error(self) -> None:
        err = UnsupportedFeatureError("GOTO", source="tsql", target="postgresql")
        assert "GOTO" in str(err)
