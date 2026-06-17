# Copyright (C) 2026 Unique Contributors
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.

"""Batch splitter for multi-statement SQL scripts.

Splits SQL scripts into individual executable batches respecting
dialect-specific batch separators and string/comment boundaries.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum, auto


class BatchType(Enum):
    """Classification of a batch's content."""

    EMPTY = auto()
    COMMENT = auto()
    SET_OPTION = auto()
    DML = auto()
    DDL = auto()
    PROCEDURAL = auto()
    UNKNOWN = auto()


@dataclass
class Batch:
    """A single executable batch from a script."""

    sql: str
    batch_type: BatchType = BatchType.UNKNOWN
    line_offset: int = 0

    @property
    def is_empty(self) -> bool:
        """Whether this batch has no meaningful content."""
        stripped = self.sql.strip()
        if not stripped:
            return True
        lines = stripped.split("\n")
        return all(
            line.strip() == "" or line.strip().startswith("--") for line in lines
        )


_PROCEDURAL_PATTERNS = {
    "tsql": re.compile(
        r"(?i)^\s*(?:CREATE|ALTER)\s+(?:PROCEDURE|FUNCTION|TRIGGER)\b",
        re.MULTILINE,
    ),
    "oracle": re.compile(
        r"(?i)^\s*CREATE\s+(?:OR\s+REPLACE\s+)?(?:PROCEDURE|FUNCTION|TRIGGER|PACKAGE)\b",
        re.MULTILINE,
    ),
    "postgresql": re.compile(
        r"(?i)^\s*CREATE\s+(?:OR\s+REPLACE\s+)?(?:PROCEDURE|FUNCTION|TRIGGER)\b",
        re.MULTILINE,
    ),
    "mysql": re.compile(
        r"(?i)^\s*CREATE\s+(?:DEFINER\s*=\s*\S+\s+)?(?:PROCEDURE|FUNCTION|TRIGGER)\b",
        re.MULTILINE,
    ),
}

_SET_PATTERN = re.compile(
    r"(?i)^\s*SET\s+(?:NOCOUNT|QUOTED_IDENTIFIER|ANSI_NULLS|XACT_ABORT|ARITHABORT)\b"
)

_IF_OBJECT_PATTERN = re.compile(r"(?i)^\s*IF\s+(?:OBJECT_ID|EXISTS)\b")


def classify_batch(sql: str, dialect: str) -> BatchType:
    """Classify a batch's content type.

    Args:
        sql: The batch SQL text.
        dialect: The source dialect name.

    Returns:
        The BatchType classification.
    """
    stripped = sql.strip()
    if not stripped:
        return BatchType.EMPTY

    lines = [
        line for line in stripped.split("\n") if line.strip() and not line.strip().startswith("--")
    ]
    if not lines:
        return BatchType.COMMENT

    first_meaningful = lines[0].strip()

    if _SET_PATTERN.match(first_meaningful):
        return BatchType.SET_OPTION

    if _IF_OBJECT_PATTERN.match(first_meaningful):
        return BatchType.SET_OPTION

    pattern = _PROCEDURAL_PATTERNS.get(dialect)
    if pattern and pattern.search(stripped):
        return BatchType.PROCEDURAL

    ddl_keywords = ("CREATE", "ALTER", "DROP", "TRUNCATE", "GRANT", "REVOKE")
    upper = first_meaningful.upper()
    for kw in ddl_keywords:
        if upper.startswith(kw):
            return BatchType.DDL

    dml_keywords = ("SELECT", "INSERT", "UPDATE", "DELETE", "MERGE", "WITH")
    for kw in dml_keywords:
        if upper.startswith(kw):
            return BatchType.DML

    return BatchType.UNKNOWN


class BatchSplitter:
    """Splits SQL scripts into batches based on dialect separators."""

    @staticmethod
    def split(sql: str, dialect: str) -> list[Batch]:
        """Split a SQL script into individual batches.

        Args:
            sql: The complete SQL script text.
            dialect: The source dialect name.

        Returns:
            A list of Batch objects.
        """
        sql = sql.replace("\r\n", "\n").replace("\r", "\n")

        if dialect == "tsql":
            return BatchSplitter._split_tsql(sql)
        elif dialect == "oracle":
            return BatchSplitter._split_oracle(sql)
        elif dialect == "postgresql":
            return BatchSplitter._split_postgresql(sql)
        elif dialect == "mysql":
            return BatchSplitter._split_mysql(sql)
        else:
            return [Batch(sql=sql, batch_type=classify_batch(sql, dialect))]

    @staticmethod
    def _split_tsql(sql: str) -> list[Batch]:
        """Split T-SQL on GO batch separators."""
        parts = re.split(r"(?m)^GO\s*$", sql)
        batches = []
        line_offset = 0
        for part in parts:
            stripped = part.strip()
            if stripped:
                batch = Batch(
                    sql=stripped,
                    batch_type=classify_batch(stripped, "tsql"),
                    line_offset=line_offset,
                )
                batches.append(batch)
            line_offset += part.count("\n") + 1
        return batches

    @staticmethod
    def _split_oracle(sql: str) -> list[Batch]:
        """Split Oracle on / (slash) batch separators.

        For procedural blocks (CREATE OR REPLACE PROCEDURE/FUNCTION/TRIGGER/PACKAGE),
        the slash is the terminator. For plain DML/DDL, semicolons are used.
        """
        parts = re.split(r"(?m)^/\s*$", sql)
        batches = []
        line_offset = 0
        for part in parts:
            stripped = part.strip()
            if stripped:
                batch = Batch(
                    sql=stripped,
                    batch_type=classify_batch(stripped, "oracle"),
                    line_offset=line_offset,
                )
                batches.append(batch)
            line_offset += part.count("\n") + 1
        return batches

    @staticmethod
    def _split_postgresql(sql: str) -> list[Batch]:
        """Split PostgreSQL respecting $$ dollar-quoting.

        Procedural blocks are wrapped in $$ ... $$ and use CREATE FUNCTION
        with LANGUAGE plpgsql. We split on semicolons outside dollar-quoted
        strings.
        """
        batches: list[Batch] = []
        current: list[str] = []
        in_dollar_quote = False
        dollar_tag = ""
        line_offset = 0
        batch_start = 0

        for i, line in enumerate(sql.split("\n")):
            if in_dollar_quote:
                current.append(line)
                if dollar_tag in line:
                    in_dollar_quote = False
                continue

            dollar_match = re.search(r"\$([a-zA-Z_]*)\$", line)
            if dollar_match:
                dollar_tag = dollar_match.group(0)
                rest = line[dollar_match.end() :]
                if dollar_tag not in rest:
                    in_dollar_quote = True
                current.append(line)
                continue

            current.append(line)

            stripped_line = line.rstrip()
            if stripped_line.endswith(";") and not in_dollar_quote:
                text = "\n".join(current).strip()
                if text:
                    batches.append(
                        Batch(
                            sql=text,
                            batch_type=classify_batch(text, "postgresql"),
                            line_offset=batch_start,
                        )
                    )
                current = []
                batch_start = i + 1

        remaining = "\n".join(current).strip()
        if remaining:
            batches.append(
                Batch(
                    sql=remaining,
                    batch_type=classify_batch(remaining, "postgresql"),
                    line_offset=batch_start,
                )
            )

        return batches

    @staticmethod
    def _split_mysql(sql: str) -> list[Batch]:
        """Split MySQL respecting DELIMITER changes."""
        delimiter = ";"
        batches: list[Batch] = []
        current: list[str] = []
        line_offset = 0
        batch_start = 0

        for i, line in enumerate(sql.split("\n")):
            stripped = line.strip()

            delimiter_match = re.match(
                r"(?i)^DELIMITER\s+(\S+)\s*$", stripped
            )
            if delimiter_match:
                remaining = "\n".join(current).strip()
                if remaining:
                    batches.append(
                        Batch(
                            sql=remaining,
                            batch_type=classify_batch(remaining, "mysql"),
                            line_offset=batch_start,
                        )
                    )
                    current = []
                delimiter = delimiter_match.group(1)
                batch_start = i + 1
                continue

            current.append(line)

            if stripped.endswith(delimiter):
                text = "\n".join(current).strip()
                if delimiter != ";":
                    text = text[: -len(delimiter)].rstrip()
                elif text.endswith(";"):
                    text = text[:-1].rstrip()
                if text:
                    batches.append(
                        Batch(
                            sql=text,
                            batch_type=classify_batch(text, "mysql"),
                            line_offset=batch_start,
                        )
                    )
                current = []
                batch_start = i + 1

        remaining = "\n".join(current).strip()
        if remaining:
            batches.append(
                Batch(
                    sql=remaining,
                    batch_type=classify_batch(remaining, "mysql"),
                    line_offset=batch_start,
                )
            )

        return batches
