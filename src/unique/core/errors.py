# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Custom exception hierarchy for the Unique transpiler."""


class UniqueError(Exception):
    """Base exception for all Unique errors."""


class ParseError(UniqueError):
    """Raised when SQL parsing fails."""

    def __init__(
        self, message: str, line: int | None = None, column: int | None = None
    ):
        self.line = line
        self.column = column
        location = ""
        if line is not None:
            location = f" at line {line}"
            if column is not None:
                location += f", column {column}"
        super().__init__(f"Parse error{location}: {message}")


class EmitError(UniqueError):
    """Raised when SQL emission fails."""

    def __init__(self, message: str, node_type: str | None = None):
        self.node_type = node_type
        prefix = f"Emit error for {node_type}" if node_type else "Emit error"
        super().__init__(f"{prefix}: {message}")


class UnsupportedFeatureError(UniqueError):
    """Raised when a construct cannot be translated to the target dialect."""

    def __init__(self, feature: str, source: str, target: str):
        self.feature = feature
        self.source = source
        self.target = target
        super().__init__(f"Cannot transpile '{feature}' from {source} to {target}")


class UnknownDialectError(UniqueError):
    """Raised when a requested dialect is not registered."""

    def __init__(self, dialect: str):
        self.dialect = dialect
        msg = (
            f"Unknown dialect '{dialect}'. "
            "Use 'unique dialects' to list available dialects."
        )
        super().__init__(msg)


class TransformError(UniqueError):
    """Raised when a transformation pass fails."""

    def __init__(self, message: str, pass_name: str | None = None):
        self.pass_name = pass_name
        prefix = f"Transform error in {pass_name}" if pass_name else "Transform error"
        super().__init__(f"{prefix}: {message}")
