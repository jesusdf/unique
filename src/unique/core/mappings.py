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
    "SYSTIMESTAMP": "CURRENT_TIMESTAMP",
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

#: The current-date expression per dialect (niladic; "today" at midnight).
CURRENT_DATE_EXPR: dict[str, str] = {
    "tsql": "CAST(GETDATE() AS DATE)",
    "oracle": "TRUNC(SYSDATE)",
    "postgresql": "CURRENT_DATE",
    "mysql": "CURDATE()",
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

#: The current-error-message expression per dialect (exception-handler
#: context). MySQL has no expression form (GET DIAGNOSTICS is a statement;
#: the procedural transformer handles assignments) — absent means "no
#: context-free spelling; keep the name visible".
ERROR_MESSAGE_EXPR: dict[str, str] = {
    "tsql": "ERROR_MESSAGE()",
    "oracle": "SQLERRM",
    "postgresql": "SQLERRM",
}

#: Source spellings of the current-error-message global, with the dialects
#: they belong to (SQLERRM is both PL/SQL and plpgsql).
ERROR_MESSAGE_SOURCES: dict[str, frozenset[str]] = {
    "ERROR_MESSAGE": frozenset({"tsql"}),
    "SQLERRM": frozenset({"oracle", "postgresql"}),
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
        "CHR": "CHAR",
        "LENGTH": "LEN",
        "SYS_GUID": "NEWID",
        "SUBSTR": "SUBSTRING",
        "CEIL": "CEILING",
        # TO_CHAR/TO_DATE/TO_NUMBER need a type argument on T-SQL — a name
        # rename would emit CONVERT(x)/CAST(x) without one (error 156). The
        # T-SQL transformer rewrites them argument-aware
        # (_map_oracle_builtins); the placeholders document the gap for the
        # forms it does not cover.
        "TO_CHAR": "-- TO_CHAR(x, fmt) requires manual conversion",
        "TO_DATE": "-- TO_DATE(x, fmt) requires manual conversion",
        "TO_NUMBER": "-- TO_NUMBER -> CAST(x AS DECIMAL(38, 10))",
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
        "CHR": "CHAR",
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
    ("mysql", "postgresql"): {
        "IFNULL": "COALESCE",
        "RAND": "RANDOM",
        "CURDATE": "CURRENT_DATE",
        "UUID": "GEN_RANDOM_UUID",
    },
    ("mysql", "oracle"): {
        "IFNULL": "NVL",
        "CURDATE": "TRUNC(SYSDATE)",
        "UUID": "SYS_GUID",
        # Round-trips of the oracle->mysql renames (symmetry contract).
        "CHAR_LENGTH": "LENGTH",
        "SUBSTRING": "SUBSTR",
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
    ("postgresql", "mysql"): {
        "CHR": "CHAR",
        # Round-trips of the mysql->postgresql renames (symmetry contract);
        # COALESCE/CURRENT_DATE are native on both (identity collapse).
        "COALESCE": "COALESCE",
        "CURRENT_DATE": "CURRENT_DATE",
        "RANDOM": "RAND",
        "GEN_RANDOM_UUID": "UUID",
    },
    ("oracle", "mysql"): {
        "NVL": "IFNULL",
        "CHR": "CHAR",
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
        # Oracle-source names (the passthrough/MODIFY rewriters feed these).
        "NUMBER": "NUMERIC",
        "VARCHAR2": "VARCHAR",
        "NVARCHAR2": "VARCHAR",
        "CLOB": "TEXT",
        "NCLOB": "TEXT",
        "RAW": "BYTEA",
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
        "BINARY": "BYTEA",
        "BLOB": "BYTEA",
        "TINYBLOB": "BYTEA",
        "MEDIUMBLOB": "BYTEA",
        "LONGBLOB": "BYTEA",
        "IMAGE": "BYTEA",
        "TINYTEXT": "TEXT",
        "MEDIUMTEXT": "TEXT",
        "LONGTEXT": "TEXT",
        # MySQL unsigned integers (sqlglot U-prefixed internal names): the
        # next-wider signed type covers the unsigned range.
        "UTINYINT": "SMALLINT",
        "USMALLINT": "INTEGER",
        "UMEDIUMINT": "INTEGER",
        "UINT": "BIGINT",
        "UBIGINT": "NUMERIC(20)",
        # Unsigned floats have no PostgreSQL equivalent — use the signed type.
        "UDOUBLE": "DOUBLE PRECISION",
        "UFLOAT": "REAL",
        "UDECIMAL": "DECIMAL",
        "DOUBLE": "DOUBLE PRECISION",
        "MEDIUMINT": "INTEGER",
        "YEAR": "SMALLINT",
    },
    "mysql": {
        # PG internal type aliases (int4 etc.) — invalid spellings
        # everywhere else (wave 149).
        "INT2": "SMALLINT",
        "INT4": "INT",
        "INT8": "BIGINT",
        "FLOAT4": "FLOAT",
        "FLOAT8": "DOUBLE",
        # Oracle-source names (the passthrough/MODIFY rewriters feed these).
        "NUMBER": "DECIMAL",
        "VARCHAR2": "VARCHAR",
        "NVARCHAR2": "VARCHAR",
        "CLOB": "LONGTEXT",
        "NCLOB": "LONGTEXT",
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
        # PG internal type aliases (int4 etc.) — invalid spellings
        # everywhere else (wave 149).
        "INT2": "SMALLINT",
        "INT4": "INTEGER",
        "INT8": "NUMBER(19)",
        "FLOAT4": "BINARY_FLOAT",
        "FLOAT8": "BINARY_DOUBLE",
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
        "VARBINARY": "RAW",
        "BINARY": "RAW",
        "UNIQUEIDENTIFIER": "RAW(16)",
        "UUID": "RAW(16)",
        "MONEY": "NUMBER(19,4)",
        # Oracle has no DOUBLE (BINARY_DOUBLE is the 64-bit float); FLOAT is a
        # valid Oracle type, so it is left as-is.
        "DOUBLE": "BINARY_DOUBLE",
        "UDOUBLE": "BINARY_DOUBLE",
        "UFLOAT": "FLOAT",
        "UDECIMAL": "NUMBER",
        "IMAGE": "BLOB",
        "TINYBLOB": "BLOB",
        "MEDIUMBLOB": "BLOB",
        "LONGBLOB": "BLOB",
        "BLOB": "BLOB",
        "TINYTEXT": "CLOB",
        "MEDIUMTEXT": "CLOB",
        "LONGTEXT": "CLOB",
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
        # PG internal type aliases (int4 etc.) — invalid spellings
        # everywhere else (wave 149).
        "INT2": "SMALLINT",
        "INT4": "INT",
        "INT8": "BIGINT",
        "FLOAT4": "REAL",
        "FLOAT8": "FLOAT",
        "VARCHAR2": "VARCHAR",
        "NVARCHAR2": "NVARCHAR",
        "NUMBER": "NUMERIC",
        "CLOB": "VARCHAR(MAX)",
        "NCLOB": "NVARCHAR(MAX)",
        "BLOB": "VARBINARY(MAX)",
        "TINYBLOB": "VARBINARY(MAX)",
        "MEDIUMBLOB": "VARBINARY(MAX)",
        "LONGBLOB": "VARBINARY(MAX)",
        "TINYTEXT": "VARCHAR(MAX)",
        "MEDIUMTEXT": "VARCHAR(MAX)",
        "LONGTEXT": "VARCHAR(MAX)",
        "DOUBLE": "FLOAT",
        "UDOUBLE": "FLOAT",
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
        # T-SQL TIMESTAMP is ROWVERSION (an auto binary value), not a datetime,
        # and cannot take a DEFAULT — a wall clock column must be DATETIME2.
        "TIMESTAMP": "DATETIME2",
    },
}

#: A bare character type (no length) reaching the DML emitter came from a
#: T-SQL VARCHAR(MAX)/NVARCHAR(MAX) whose MAX marker is lost during IR
#: conversion. Map it to each engine's large-text type. Keyed by the type
#: name AFTER EMIT_TYPE_MAP has mapped it to the target dialect.
# T-SQL VARCHAR(MAX)/NVARCHAR(MAX) -> the target's large-text type. Oracle uses a
# bounded VARCHAR2/NVARCHAR2 rather than CLOB/NCLOB: a CLOB cannot be a comparison
# or join key (ORA-22848), and these columns are routinely used as predicates. A
# value beyond the bound needs Oracle's MAX_STRING_SIZE = EXTENDED.
BARE_CHAR_BIGTEXT: dict[str, dict[str, str]] = {
    "oracle": {"VARCHAR2": "VARCHAR2(4000)", "NVARCHAR2": "NVARCHAR2(2000)"},
    "mysql": {"VARCHAR": "LONGTEXT", "NVARCHAR": "LONGTEXT"},
    "postgresql": {"VARCHAR": "TEXT", "NVARCHAR": "TEXT"},
    "tsql": {"VARCHAR": "VARCHAR(MAX)", "NVARCHAR": "NVARCHAR(MAX)"},
}

#: Per-pair type renames applied by the procedural pipeline (routine
#: parameters, DECLARE sections, RETURN types).
PROCEDURAL_TYPE_MAPS: dict[tuple[str, str], dict[str, str]] = {
    # PG-source maps NEVER EXISTED before wave 149 — the internal
    # aliases (int4…) and PG-only types shipped raw into every target.
    ("postgresql", "tsql"): {
        "BPCHAR": "VARCHAR",
        "NAME": "VARCHAR",
        "INT2": "SMALLINT",
        "INT4": "INT",
        "INT8": "BIGINT",
        "FLOAT4": "REAL",
        "FLOAT8": "FLOAT",
        "DOUBLE PRECISION": "FLOAT",
        "TEXT": "NVARCHAR(MAX)",
        "BYTEA": "VARBINARY(MAX)",
        "BOOLEAN": "BIT",
        "BOOL": "BIT",
        "TIMESTAMPTZ": "DATETIMEOFFSET",
        "UUID": "UNIQUEIDENTIFIER",
        "JSON": "NVARCHAR(MAX)",
        "JSONB": "NVARCHAR(MAX)",
    },
    ("postgresql", "mysql"): {
        "BPCHAR": "CHAR",
        "NAME": "CHAR",
        "INT2": "SMALLINT",
        "INT4": "INT",
        "INT8": "BIGINT",
        "FLOAT4": "FLOAT",
        "FLOAT8": "DOUBLE",
        "DOUBLE PRECISION": "DOUBLE",
        "BYTEA": "LONGBLOB",
        "TIMESTAMPTZ": "TIMESTAMP",
        "UUID": "CHAR(36)",
        "JSONB": "JSON",
        "SERIAL": "INT",
        "BIGSERIAL": "BIGINT",
    },
    ("postgresql", "oracle"): {
        "BPCHAR": "VARCHAR2",
        "NAME": "VARCHAR2",
        "REFCURSOR": "SYS_REFCURSOR",
        "INT2": "SMALLINT",
        "INT4": "INTEGER",
        "INT8": "NUMBER(19)",
        "FLOAT4": "BINARY_FLOAT",
        "FLOAT8": "BINARY_DOUBLE",
        "DOUBLE PRECISION": "BINARY_DOUBLE",
        "TEXT": "CLOB",
        "BYTEA": "BLOB",
        "TIMESTAMPTZ": "TIMESTAMP WITH TIME ZONE",
        "UUID": "RAW(16)",
        "JSON": "CLOB",
        "JSONB": "CLOB",
        "SERIAL": "NUMBER",
        "BIGSERIAL": "NUMBER",
    },
    ("mysql", "oracle"): {
        "INT": "NUMBER(10)",
        "INTEGER": "NUMBER(10)",
        "BIGINT": "NUMBER(19)",
        "SMALLINT": "NUMBER(5)",
        "MEDIUMINT": "NUMBER(7)",
        "TINYINT": "NUMBER(3)",
        "BOOLEAN": "NUMBER(1)",
        "BOOL": "NUMBER(1)",
        "DOUBLE": "BINARY_DOUBLE",
        "DECIMAL": "NUMBER",
        "NUMERIC": "NUMBER",
        "VARCHAR": "VARCHAR2",
        "TEXT": "CLOB",
        "TINYTEXT": "CLOB",
        "MEDIUMTEXT": "CLOB",
        "LONGTEXT": "CLOB",
        "BLOB": "BLOB",
        "TINYBLOB": "BLOB",
        "MEDIUMBLOB": "BLOB",
        "LONGBLOB": "BLOB",
        "DATETIME": "TIMESTAMP",
    },
    ("mysql", "tsql"): {
        # MySQL declares that T-SQL rejects or narrows (DECLARE @x double
        # was error 'double is not a recognized type' — wave 172).
        "DOUBLE": "FLOAT",
        "MEDIUMINT": "INT",
        "BOOLEAN": "BIT",
        "BOOL": "BIT",
        "TEXT": "VARCHAR(MAX)",
        "TINYTEXT": "VARCHAR(MAX)",
        "MEDIUMTEXT": "VARCHAR(MAX)",
        "LONGTEXT": "VARCHAR(MAX)",
        "BLOB": "VARBINARY(MAX)",
        "TINYBLOB": "VARBINARY(MAX)",
        "MEDIUMBLOB": "VARBINARY(MAX)",
        "LONGBLOB": "VARBINARY(MAX)",
        "YEAR": "SMALLINT",
    },
    ("mysql", "postgresql"): {
        "TINYINT": "SMALLINT",
        "MEDIUMINT": "INTEGER",
        "DOUBLE": "DOUBLE PRECISION",
        "DATETIME": "TIMESTAMP",
        "TINYTEXT": "TEXT",
        "MEDIUMTEXT": "TEXT",
        "LONGTEXT": "TEXT",
        "BLOB": "BYTEA",
        "TINYBLOB": "BYTEA",
        "MEDIUMBLOB": "BYTEA",
        "LONGBLOB": "BYTEA",
    },
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
        # SQL_VARIANT -> ANYDATA is faithful but unusable: a plain value can't be
        # passed to an ANYDATA parameter (PLS-00306), so procedures that pass one
        # fail to compile. Use a bounded VARCHAR2 (values pass, typed ones convert
        # implicitly); the original is kept in a /* UNIQUE: SQL_VARIANT */ comment.
        "SQL_VARIANT": "VARCHAR2(4000)",
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


#: T-SQL builtin functions that are callable UNqualified. An unqualified call
#: to anything else that reaches T-SQL output is error 195 at parse time —
#: scalar UDFs must be schema-qualified (``dbo.fn(…)``), even when the
#: function exists (2026-07-11 sweep: ~15 client-DB-resident UDF calls).
TSQL_CALLABLE_BUILTINS: frozenset[str] = frozenset(
    {
        # Aggregates / windowed
        "AVG",
        "COUNT",
        "COUNT_BIG",
        "MAX",
        "MIN",
        "SUM",
        "STDEV",
        "STDEVP",
        "VAR",
        "VARP",
        "STRING_AGG",
        "GROUPING",
        "GROUPING_ID",
        "CHECKSUM_AGG",
        "APPROX_COUNT_DISTINCT",
        "ROW_NUMBER",
        "RANK",
        "DENSE_RANK",
        "NTILE",
        "LAG",
        "LEAD",
        "FIRST_VALUE",
        "LAST_VALUE",
        "PERCENT_RANK",
        "CUME_DIST",
        "PERCENTILE_CONT",
        "PERCENTILE_DISC",
        # Date / time
        "GETDATE",
        "GETUTCDATE",
        "SYSDATETIME",
        "SYSUTCDATETIME",
        "SYSDATETIMEOFFSET",
        "DATEADD",
        "DATEDIFF",
        "DATEDIFF_BIG",
        "DATEPART",
        "DATENAME",
        "DAY",
        "MONTH",
        "YEAR",
        "EOMONTH",
        "DATEFROMPARTS",
        "DATETIMEFROMPARTS",
        "DATETIME2FROMPARTS",
        "SMALLDATETIMEFROMPARTS",
        "TIMEFROMPARTS",
        "DATETIMEOFFSETFROMPARTS",
        "DATETRUNC",
        "SWITCHOFFSET",
        "TODATETIMEOFFSET",
        "ISDATE",
        "CURRENT_TIMESTAMP",
        # Strings
        "LEN",
        "LEFT",
        "RIGHT",
        "SUBSTRING",
        "CHARINDEX",
        "PATINDEX",
        "REPLACE",
        "REPLICATE",
        "REVERSE",
        "LTRIM",
        "RTRIM",
        "TRIM",
        "UPPER",
        "LOWER",
        "SPACE",
        "STR",
        "STUFF",
        "CONCAT",
        "CONCAT_WS",
        "FORMAT",
        "QUOTENAME",
        "UNICODE",
        "NCHAR",
        "CHAR",
        "ASCII",
        "SOUNDEX",
        "DIFFERENCE",
        "TRANSLATE",
        "STRING_SPLIT",
        "STRING_ESCAPE",
        # Math
        "ABS",
        "CEILING",
        "FLOOR",
        "ROUND",
        "SIGN",
        "SQRT",
        "SQUARE",
        "POWER",
        "EXP",
        "LOG",
        "LOG10",
        "PI",
        "RAND",
        "COS",
        "SIN",
        "TAN",
        "ACOS",
        "ASIN",
        "ATAN",
        "ATN2",
        "COT",
        "DEGREES",
        "RADIANS",
        # Conversion / null handling
        "CAST",
        "CONVERT",
        "TRY_CAST",
        "TRY_CONVERT",
        "PARSE",
        "TRY_PARSE",
        "ISNULL",
        "COALESCE",
        "NULLIF",
        "IIF",
        "CHOOSE",
        "GREATEST",
        "LEAST",
        "ISNUMERIC",
        # System / metadata / identity
        "NEWID",
        "NEWSEQUENTIALID",
        "OBJECT_ID",
        "OBJECT_NAME",
        "SCOPE_IDENTITY",
        "IDENT_CURRENT",
        "DB_NAME",
        "SCHEMA_NAME",
        "SCHEMA_ID",
        "USER_NAME",
        "SUSER_SNAME",
        "SUSER_NAME",
        "HOST_NAME",
        "APP_NAME",
        "COLUMNPROPERTY",
        "OBJECTPROPERTY",
        "OBJECTPROPERTYEX",
        "INDEXPROPERTY",
        "SERVERPROPERTY",
        "COL_LENGTH",
        "COL_NAME",
        "DATALENGTH",
        "TYPE_ID",
        "TYPE_NAME",
        "USER_ID",
        "DATABASE_PRINCIPAL_ID",
        # Error handling / transactions
        "ERROR_MESSAGE",
        "ERROR_NUMBER",
        "ERROR_SEVERITY",
        "ERROR_STATE",
        "ERROR_LINE",
        "ERROR_PROCEDURE",
        "XACT_STATE",
        # Crypto / checksums / JSON / XML
        "HASHBYTES",
        "CHECKSUM",
        "BINARY_CHECKSUM",
        "JSON_VALUE",
        "JSON_QUERY",
        "JSON_MODIFY",
        "ISJSON",
        "OPENJSON",
        "OPENQUERY",
        "OPENROWSET",
        "COMPRESS",
        "DECOMPRESS",
    }
)

#: Builtins of the OTHER supported engines. When one of these reaches T-SQL
#: output unqualified it is a *mapping gap*: it must stay a visible failure
#: (never be masked as a phantom ``dbo.TO_NUMBER`` user function).
FOREIGN_BUILTIN_FUNCTIONS: frozenset[str] = frozenset(
    {
        # Oracle
        "TO_NUMBER",
        "TO_DATE",
        "TO_CHAR",
        "TO_CLOB",
        "TO_TIMESTAMP",
        "NVL",
        "NVL2",
        "DECODE",
        "INSTR",
        "LENGTH",
        "SUBSTR",
        "ADD_MONTHS",
        "MONTHS_BETWEEN",
        "LAST_DAY",
        "NEXT_DAY",
        "SYSDATE",
        "SYSTIMESTAMP",
        "CHR",
        "INITCAP",
        "LPAD",
        "RPAD",
        "TRUNC",
        "EXTRACT",
        "EMPTY_BLOB",
        "EMPTY_CLOB",
        "REGEXP_LIKE",
        "REGEXP_REPLACE",
        "REGEXP_SUBSTR",
        "REGEXP_INSTR",
        "REGEXP_COUNT",
        "SYS_GUID",
        "SYS_CONTEXT",
        "USERENV",
        "LISTAGG",
        "WM_CONCAT",
        "RAWTOHEX",
        "HEXTORAW",
        "BITAND",
        "MOD",
        "GREATEST",
        "LEAST",
        "DBMS_RANDOM",
        "ORA_HASH",
        "STANDARD_HASH",
        "XMLAGG",
        "XMLELEMENT",
        "TO_BINARY_DOUBLE",
        "CURRENT_DATE",
        # PostgreSQL
        "DATE_TRUNC",
        "STRING_TO_ARRAY",
        "ARRAY_TO_STRING",
        "GEN_RANDOM_UUID",
        "PG_SLEEP",
        "AGE",
        "DATE_PART",
        "SPLIT_PART",
        "STRPOS",
        "POSITION",
        "NOW",
        "MD5",
        "ENCODE",
        "DECODE_BASE64",
        "UNNEST",
        "ARRAY_AGG",
        # MySQL
        "DATE_FORMAT",
        "STR_TO_DATE",
        "IFNULL",
        "GROUP_CONCAT",
        "LOCATE",
        "CURDATE",
        "CURTIME",
        "UNIX_TIMESTAMP",
        "FROM_UNIXTIME",
        "DATE_ADD",
        "DATE_SUB",
        "TIMESTAMPDIFF",
        "TIMESTAMPADD",
        "UUID",
        "SHA1",
        "SHA2",
        "TRUNCATE",
        "IF",
    }
)

#: Keywords and type names that legitimately precede ``(`` inside an
#: expression and must never be treated as a function call to qualify.
TSQL_NEVER_QUALIFY: frozenset[str] = frozenset(
    {
        "IN",
        "EXISTS",
        "VALUES",
        "ANY",
        "ALL",
        "SOME",
        "CASE",
        "WHEN",
        "THEN",
        "ELSE",
        "END",
        "AND",
        "OR",
        "NOT",
        "LIKE",
        "BETWEEN",
        "IS",
        "AS",
        "OVER",
        "PARTITION",
        "WHERE",
        "HAVING",
        "ON",
        "BY",
        "DISTINCT",
        "TOP",
        "SELECT",
        "UNION",
        "EXCEPT",
        "INTERSECT",
        "KEY",
        "UNIQUE",
        "CHECK",
        "DEFAULT",
        "WITH",
        "RETURN",
        "RETURNS",
        "IF",
        "WHILE",
        "PRINT",
        "GROUP",
        "ORDER",
        "WITHIN",
        "FILTER",
        "USING",
        "MATCHED",
        "OUTPUT",
        "FROM",
        "JOIN",
        "LATERAL",
        "APPLY",
        # DML verbs: ``WHEN NOT MATCHED THEN INSERT (…)`` puts them right
        # before a parenthesis.
        "INSERT",
        "UPDATE",
        "DELETE",
        "MERGE",
        "INTO",
        # Types (CAST targets / DECLAREs inside captured expressions)
        "VARCHAR",
        "NVARCHAR",
        "CHAR",
        "NCHAR",
        "DECIMAL",
        "NUMERIC",
        "FLOAT",
        "REAL",
        "INT",
        "INTEGER",
        "BIGINT",
        "SMALLINT",
        "TINYINT",
        "BIT",
        "MONEY",
        "SMALLMONEY",
        "DATETIME",
        "DATETIME2",
        "SMALLDATETIME",
        "DATETIMEOFFSET",
        "TIME",
        "DATE",
        "BINARY",
        "VARBINARY",
        "UNIQUEIDENTIFIER",
        "TEXT",
        "NTEXT",
        "IMAGE",
        "XML",
        "SQL_VARIANT",
        "NUMBER",
        "VARCHAR2",
        "NVARCHAR2",
        "CLOB",
        "BLOB",
        "RAW",
        "SIGNED",
        "UNSIGNED",
    }
)

#: Object-introducing words: an identifier right after one of these is a
#: table/routine name position, not a scalar call (``INSERT INTO t (…)``).
TSQL_OBJECT_CONTEXT_WORDS: frozenset[str] = frozenset(
    {
        "INTO",
        "FROM",
        "JOIN",
        "UPDATE",
        "DELETE",
        "TABLE",
        "PROCEDURE",
        "FUNCTION",
        "TRIGGER",
        "VIEW",
        "INDEX",
        "EXEC",
        "EXECUTE",
        "CURSOR",
        "APPLY",
        "MERGE",
        "USING",
        "REFERENCES",
        "OBJECT_ID",
    }
)


def tsql_call_needs_schema(name: str) -> bool:
    """Whether an unqualified call to ``name`` must become ``dbo.name(…)`` on
    T-SQL. True only for names that are neither T-SQL builtins (callable
    bare) nor known builtins of another engine (an unmapped foreign builtin
    is a mapping gap that must stay visible) nor keywords/type names."""
    if not name or "." in name:
        return False
    first = name[0]
    if not (first.isalpha() or first == "_"):
        return False
    upper = name.upper()
    return (
        upper not in TSQL_CALLABLE_BUILTINS
        and upper not in FOREIGN_BUILTIN_FUNCTIONS
        and upper not in TSQL_NEVER_QUALIFY
    )
