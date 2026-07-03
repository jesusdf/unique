# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Single declarative mapping layer shared by both pipelines (audit doc 03).

Every cross-dialect fact about *names* — function spellings, type names,
current-timestamp expressions — lives here, consumed by the standalone-DML
pipeline (``converter.py`` / ``transformer.py``) and by the procedural
pipeline (``procedural/transformer``). Keeping one module makes asymmetries
visible: ``tests/unit/core/test_mappings.py`` iterates these tables in both
directions and fails on unexplained divergence between pipelines or between
a mapping and its reverse.

Two shapes coexist, reflecting how each pipeline works:

- ``EMIT_TYPE_MAP`` is keyed by *target only*: the DML pipeline converts
  through sqlglot's canonical type names, so the source dialect is already
  normalized away when a type is emitted.
- ``PROCEDURAL_TYPE_MAPS`` / ``PROCEDURAL_FUNC_MAPS`` are keyed by
  ``(source, target)``: the procedural pipeline rewrites raw routine text,
  where the source spelling is still present.

A procedural function-map value that starts with ``--`` is a documented
"needs manual conversion" placeholder, skipped by the rewriter.
"""

from __future__ import annotations

DIALECTS = ("tsql", "oracle", "postgresql", "mysql")

# ---------------------------------------------------------------------------
# Functions
# ---------------------------------------------------------------------------

#: Source spellings folded to a canonical function name by the DML
#: transformer (FunctionNormalizer). IIF/DECODE become CASE expressions and
#: are handled structurally, not listed here.
CANONICAL_FUNCTION_NAMES: dict[str, str] = {
    # Null handling
    "ISNULL": "COALESCE",
    "NVL": "COALESCE",
    "IFNULL": "COALESCE",
    # Date/time
    "GETDATE": "CURRENT_TIMESTAMP",
    "SYSDATETIME": "CURRENT_TIMESTAMP",
    "SYSDATE": "CURRENT_TIMESTAMP",
    # String
    "LEN": "LENGTH",
    "SUBSTR": "SUBSTRING",
}

#: The current-timestamp expression per dialect (niladic; parenthesization
#: differs). Used by the DML emitter and the procedural text rewriter.
CURRENT_TIMESTAMP_EXPR: dict[str, str] = {
    "tsql": "GETDATE()",
    "oracle": "SYSDATE",
    "postgresql": "CURRENT_TIMESTAMP",
    "mysql": "CURRENT_TIMESTAMP",
}

#: UUID-generating function per dialect. sqlglot canonicalizes
#: NEWID/GEN_RANDOM_UUID/SYS_GUID to UUID, which only exists on MySQL.
UUID_FUNCTION: dict[str, str] = {
    "tsql": "NEWID",
    "oracle": "SYS_GUID",
    "postgresql": "gen_random_uuid",
    "mysql": "UUID",
}

#: The "last generated identity value" expression per dialect. Oracle has no
#: session-scoped form (the value comes from ``<sequence>.CURRVAL``), so it is
#: emitted as a documented comment. Rewritten in both directions by the
#: procedural transformer.
LAST_IDENTITY_EXPR: dict[str, str] = {
    "tsql": "SCOPE_IDENTITY()",
    "postgresql": "LASTVAL()",
    "mysql": "LAST_INSERT_ID()",
    "oracle": "/* last identity: use <sequence>.CURRVAL */",
}

#: The source spellings recognized as a "last generated id" call, mapped to
#: the dialect whose LAST_IDENTITY_EXPR they are (so any source is handled).
LAST_IDENTITY_SOURCE_FUNCS: dict[str, str] = {
    "SCOPE_IDENTITY": "tsql",
    "LASTVAL": "postgresql",
    "LAST_INSERT_ID": "mysql",
}

#: Per-pair function renames applied by the procedural pipeline to raw
#: routine text (function-call positions only). Values starting with "--"
#: document constructs that need manual conversion and are not rewritten.
PROCEDURAL_FUNC_MAPS: dict[tuple[str, str], dict[str, str]] = {
    ("tsql", "oracle"): {
        "GETUTCDATE": "SYS_EXTRACT_UTC(SYSTIMESTAMP)",
        "ISNULL": "NVL",
        "LEN": "LENGTH",
        "NEWID": "SYS_GUID",
        "UPPER": "UPPER",
        "LOWER": "LOWER",
        "LTRIM": "LTRIM",
        "RTRIM": "RTRIM",
        "REPLACE": "REPLACE",
        "SUBSTRING": "SUBSTR",
        "CEILING": "CEIL",
        "SQUARE": "-- SQUARE(x) -> x*x",
        "DATEDIFF": "-- DATEDIFF requires manual conversion",
        "DATEADD": "-- DATEADD requires manual conversion",
    },
    ("oracle", "tsql"): {
        "NVL": "ISNULL",
        "LENGTH": "LEN",
        "SYS_GUID": "NEWID",
        "SUBSTR": "SUBSTRING",
        "CEIL": "CEILING",
        "TO_CHAR": "CONVERT",
        "TO_DATE": "CONVERT",
        "TO_NUMBER": "CAST",
        "TRUNC": "-- TRUNC requires manual conversion",
    },
    ("tsql", "postgresql"): {
        "GETUTCDATE": "NOW() AT TIME ZONE 'UTC'",
        "ISNULL": "COALESCE",
        "LEN": "LENGTH",
        "NEWID": "GEN_RANDOM_UUID",
        "SUBSTRING": "SUBSTRING",
        "UPPER": "UPPER",
        "LOWER": "LOWER",
        "REPLACE": "REPLACE",
        "CEILING": "CEIL",
        "DATEDIFF": "-- DATEDIFF requires manual conversion",
        "DATEADD": "-- DATEADD requires interval arithmetic",
    },
    ("postgresql", "tsql"): {
        "COALESCE": "COALESCE",
        "LENGTH": "LEN",
        "GEN_RANDOM_UUID": "NEWID",
        "CEIL": "CEILING",
    },
    ("tsql", "mysql"): {
        "GETUTCDATE": "UTC_TIMESTAMP",
        "ISNULL": "IFNULL",
        "LEN": "CHAR_LENGTH",
        "NEWID": "UUID",
        "SUBSTRING": "SUBSTRING",
        "UPPER": "UPPER",
        "LOWER": "LOWER",
        "REPLACE": "REPLACE",
        "CEILING": "CEILING",
        "DATEDIFF": "-- DATEDIFF differs (MySQL DATEDIFF returns days)",
        "DATEADD": "-- DATEADD -> DATE_ADD with INTERVAL",
    },
    ("mysql", "tsql"): {
        "IFNULL": "ISNULL",
        "CHAR_LENGTH": "LEN",
        "LENGTH": "LEN",
        "UUID": "NEWID",
        "UTC_TIMESTAMP": "GETUTCDATE",
    },
    ("oracle", "postgresql"): {
        "NVL": "COALESCE",
        "LENGTH": "LENGTH",
        "SYS_GUID": "GEN_RANDOM_UUID",
        "SUBSTR": "SUBSTRING",
        "TO_CHAR": "TO_CHAR",
        "TO_DATE": "TO_DATE",
        "TO_NUMBER": "-- TO_NUMBER -> CAST(... AS NUMERIC)",
    },
    ("oracle", "mysql"): {
        "NVL": "IFNULL",
        "LENGTH": "CHAR_LENGTH",
        "SYS_GUID": "UUID",
        "SUBSTR": "SUBSTRING",
    },
}

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

#: Non-portable type names mapped to a portable equivalent, keyed by *target*
#: dialect (the DML pipeline emits from sqlglot-canonicalized names). T-SQL
#: national/unicode types collapse to the regular char types elsewhere
#: (PostgreSQL/Oracle/MySQL store text as unicode by default).
EMIT_TYPE_MAP: dict[str, dict[str, str]] = {
    "postgresql": {
        "NVARCHAR": "VARCHAR",
        "NCHAR": "CHAR",
        "NTEXT": "TEXT",
        "DATETIME": "TIMESTAMP",
        "DATETIME2": "TIMESTAMP",
        "SMALLDATETIME": "TIMESTAMP",
        "TINYINT": "SMALLINT",
        "MONEY": "NUMERIC(19,4)",
        "BIT": "BOOLEAN",
        "UNIQUEIDENTIFIER": "UUID",
        "VARBINARY": "BYTEA",
        "IMAGE": "BYTEA",
        # MySQL unsigned integers (sqlglot U-prefixed internal names): the
        # next-wider signed type covers the unsigned range.
        "UTINYINT": "SMALLINT",
        "USMALLINT": "INTEGER",
        "UMEDIUMINT": "INTEGER",
        "UINT": "BIGINT",
        "UBIGINT": "NUMERIC(20)",
        "MEDIUMINT": "INTEGER",
        "YEAR": "SMALLINT",
    },
    "mysql": {
        "NVARCHAR": "VARCHAR",
        "NCHAR": "CHAR",
        # NTEXT holds up to 2^30 chars; MySQL TEXT caps at 64 KB, so the
        # faithful carrier is LONGTEXT (matches the procedural map).
        "NTEXT": "LONGTEXT",
        "DATETIME2": "DATETIME",
        "SMALLDATETIME": "DATETIME",
        "UNIQUEIDENTIFIER": "CHAR(36)",
        "UUID": "CHAR(36)",
        "MONEY": "DECIMAL(19,4)",
        "IMAGE": "LONGBLOB",
        # sqlglot parses MySQL's own unsigned/timestamp types into internal
        # names; map them back to real MySQL spellings.
        "UTINYINT": "TINYINT UNSIGNED",
        "USMALLINT": "SMALLINT UNSIGNED",
        "UMEDIUMINT": "MEDIUMINT UNSIGNED",
        "UINT": "INT UNSIGNED",
        "UBIGINT": "BIGINT UNSIGNED",
        "TIMESTAMPTZ": "TIMESTAMP",
    },
    "oracle": {
        "NVARCHAR": "NVARCHAR2",
        "VARCHAR": "VARCHAR2",
        "NTEXT": "NCLOB",
        "TEXT": "CLOB",
        "DATETIME": "TIMESTAMP",
        "DATETIME2": "TIMESTAMP",
        "TINYINT": "NUMBER(3)",
        "INT": "NUMBER(10)",
        "BIGINT": "NUMBER(19)",
        "BIT": "NUMBER(1)",
        "UNIQUEIDENTIFIER": "RAW(16)",
        "UUID": "RAW(16)",
        "MONEY": "NUMBER(19,4)",
        "IMAGE": "BLOB",
        "UTINYINT": "NUMBER(3)",
        "USMALLINT": "NUMBER(5)",
        "UMEDIUMINT": "NUMBER(8)",
        "UINT": "NUMBER(10)",
        "UBIGINT": "NUMBER(20)",
        "MEDIUMINT": "NUMBER(7)",
        "YEAR": "NUMBER(4)",
        # MySQL TIMESTAMP is timezone-aware (stored UTC), parsed by sqlglot
        # as TIMESTAMPTZ.
        "TIMESTAMPTZ": "TIMESTAMP WITH TIME ZONE",
    },
    "tsql": {
        "VARCHAR2": "VARCHAR",
        "NVARCHAR2": "NVARCHAR",
        "NUMBER": "NUMERIC",
        "CLOB": "VARCHAR(MAX)",
        "NCLOB": "NVARCHAR(MAX)",
        "BLOB": "VARBINARY(MAX)",
        "BOOLEAN": "BIT",
        "BYTEA": "VARBINARY(MAX)",
        "UUID": "UNIQUEIDENTIFIER",
        "SERIAL": "INT",
        "UTINYINT": "TINYINT",  # T-SQL TINYINT is already 0-255
        "USMALLINT": "INT",
        "UMEDIUMINT": "INT",
        "UINT": "BIGINT",
        "UBIGINT": "NUMERIC(20)",
        "MEDIUMINT": "INT",
        "YEAR": "SMALLINT",
        "TIMESTAMPTZ": "DATETIMEOFFSET",
    },
}

#: A bare character type (no length) reaching the DML emitter came from a
#: T-SQL VARCHAR(MAX)/NVARCHAR(MAX) whose MAX marker is lost during IR
#: conversion. Map it to each engine's large-text type. Keyed by the type
#: name AFTER EMIT_TYPE_MAP has mapped it to the target dialect.
BARE_CHAR_BIGTEXT: dict[str, dict[str, str]] = {
    "oracle": {"VARCHAR2": "CLOB", "NVARCHAR2": "NCLOB"},
    "mysql": {"VARCHAR": "LONGTEXT", "NVARCHAR": "LONGTEXT"},
    "postgresql": {"VARCHAR": "TEXT", "NVARCHAR": "TEXT"},
    "tsql": {"VARCHAR": "VARCHAR(MAX)", "NVARCHAR": "NVARCHAR(MAX)"},
}

#: Per-pair type renames applied by the procedural pipeline (routine
#: parameters, DECLARE sections, RETURN types).
PROCEDURAL_TYPE_MAPS: dict[tuple[str, str], dict[str, str]] = {
    ("tsql", "oracle"): {
        "INT": "NUMBER(10)",
        "INTEGER": "NUMBER(10)",
        "BIGINT": "NUMBER(19)",
        "SMALLINT": "NUMBER(5)",
        "TINYINT": "NUMBER(3)",
        "BIT": "NUMBER(1)",
        "FLOAT": "FLOAT",
        "REAL": "FLOAT",
        "DECIMAL": "NUMBER",
        "NUMERIC": "NUMBER",
        "MONEY": "NUMBER(19,4)",
        "SMALLMONEY": "NUMBER(10,4)",
        "VARCHAR": "VARCHAR2",
        "NVARCHAR": "NVARCHAR2",
        "CHAR": "CHAR",
        "NCHAR": "NCHAR",
        "TEXT": "CLOB",
        "NTEXT": "NCLOB",
        "IMAGE": "BLOB",
        "BINARY": "RAW",
        "VARBINARY": "RAW",
        "DATETIME": "DATE",
        "DATETIME2": "TIMESTAMP",
        "DATE": "DATE",
        "TIME": "TIMESTAMP",
        "SMALLDATETIME": "DATE",
        "UNIQUEIDENTIFIER": "RAW(16)",
        "XML": "XMLTYPE",
        "SQL_VARIANT": "ANYDATA",
    },
    ("oracle", "tsql"): {
        "NUMBER": "DECIMAL",
        "VARCHAR2": "NVARCHAR",
        "NVARCHAR2": "NVARCHAR",
        "CLOB": "NVARCHAR(MAX)",
        "NCLOB": "NVARCHAR(MAX)",
        "BLOB": "VARBINARY(MAX)",
        "RAW": "VARBINARY",
        "DATE": "DATETIME",
        "TIMESTAMP": "DATETIME2",
        "XMLTYPE": "XML",
        "BOOLEAN": "BIT",
        "PLS_INTEGER": "INT",
        "BINARY_INTEGER": "INT",
        "ANYDATA": "SQL_VARIANT",
    },
    ("oracle", "postgresql"): {
        "NUMBER": "NUMERIC",
        "VARCHAR2": "VARCHAR",
        "NVARCHAR2": "VARCHAR",
        "CLOB": "TEXT",
        "NCLOB": "TEXT",
        "BLOB": "BYTEA",
        "RAW": "BYTEA",
        "LONG": "TEXT",
        "DATE": "TIMESTAMP",
        "TIMESTAMP": "TIMESTAMP",
        "XMLTYPE": "XML",
        "BOOLEAN": "BOOLEAN",
        "PLS_INTEGER": "INTEGER",
        "BINARY_INTEGER": "INTEGER",
        "BINARY_FLOAT": "REAL",
        "BINARY_DOUBLE": "DOUBLE PRECISION",
    },
    ("oracle", "mysql"): {
        "NUMBER": "DECIMAL",
        "VARCHAR2": "VARCHAR",
        "NVARCHAR2": "VARCHAR",
        "CLOB": "LONGTEXT",
        "NCLOB": "LONGTEXT",
        "BLOB": "LONGBLOB",
        "RAW": "VARBINARY",
        "LONG": "LONGTEXT",
        "DATE": "DATETIME",
        "TIMESTAMP": "DATETIME",
        "XMLTYPE": "TEXT",
        "BOOLEAN": "TINYINT(1)",
        "PLS_INTEGER": "INT",
        "BINARY_INTEGER": "INT",
        "BINARY_FLOAT": "FLOAT",
        "BINARY_DOUBLE": "DOUBLE",
    },
    ("tsql", "postgresql"): {
        "INT": "INTEGER",
        "BIGINT": "BIGINT",
        "SMALLINT": "SMALLINT",
        "TINYINT": "SMALLINT",
        "BIT": "BOOLEAN",
        "FLOAT": "DOUBLE PRECISION",
        "REAL": "REAL",
        "MONEY": "NUMERIC(19,4)",
        "DATETIME": "TIMESTAMP",
        "DATETIME2": "TIMESTAMP",
        "SMALLDATETIME": "TIMESTAMP",
        "UNIQUEIDENTIFIER": "UUID",
        "TEXT": "TEXT",
        "NTEXT": "TEXT",
        "IMAGE": "BYTEA",
        "BINARY": "BYTEA",
        "VARBINARY": "BYTEA",
        "VARCHAR": "VARCHAR",
        "NVARCHAR": "VARCHAR",
        "XML": "XML",
    },
    ("tsql", "mysql"): {
        "INT": "INT",
        "INTEGER": "INT",
        "BIGINT": "BIGINT",
        "SMALLINT": "SMALLINT",
        "TINYINT": "TINYINT",
        "BIT": "TINYINT(1)",
        "FLOAT": "DOUBLE",
        "REAL": "FLOAT",
        "DECIMAL": "DECIMAL",
        "NUMERIC": "DECIMAL",
        "MONEY": "DECIMAL(19,4)",
        "SMALLMONEY": "DECIMAL(10,4)",
        "DATETIME": "DATETIME",
        "DATETIME2": "DATETIME",
        "SMALLDATETIME": "DATETIME",
        "DATE": "DATE",
        "TIME": "TIME",
        "UNIQUEIDENTIFIER": "CHAR(36)",
        "VARCHAR": "VARCHAR",
        "NVARCHAR": "VARCHAR",
        "CHAR": "CHAR",
        "NCHAR": "CHAR",
        "TEXT": "TEXT",
        "NTEXT": "LONGTEXT",
        "IMAGE": "LONGBLOB",
        "BINARY": "BINARY",
        "VARBINARY": "VARBINARY",
        "XML": "TEXT",
        # SQL_VARIANT stores values of various scalar types. MySQL has no
        # variant type; LONGTEXT is the most permissive carrier that preserves
        # arbitrary scalar values (callers compare/convert as needed), keeping
        # functionality rather than dropping the column/parameter.
        "SQL_VARIANT": "LONGTEXT",
    },
}
