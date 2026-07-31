# oracle → postgresql: function & type mappings

> **Generated — do not edit by hand.** Produced by `python scripts/generate_reference_docs.py` from `src/unique/core/mappings.py`. The CI freshness gate (`python scripts/generate_reference_docs.py --check`) fails the build if this file drifts from the source data.

Both pipelines share this data (audit doc 03): the procedural pipeline rewrites raw routine text using the pair-keyed tables below; the DML pipeline converts through sqlglot's canonical names, so its type table is keyed by target only. See [SKILL-development-workflow.md](../../skills/SKILL-development-workflow.md) · "Dual-pipeline symmetry rule".

## Procedural function renames

| Source function | Target form | Note |
|---|---|---|
| `LENGTH` | `LENGTH` | — |
| `NVL` | `COALESCE` | — |
| `SUBSTR` | `SUBSTRING` | — |
| `SYS_GUID` | `GEN_RANDOM_UUID` | — |
| `TO_CHAR` | `TO_CHAR` | — |
| `TO_DATE` | `TO_DATE` | — |
| `TO_NUMBER` | _manual conversion needed_ | TO_NUMBER -> CAST(... AS NUMERIC) |

## Procedural type renames

| Source type | Target type |
|---|---|
| `BINARY_DOUBLE` | `DOUBLE PRECISION` |
| `BINARY_FLOAT` | `REAL` |
| `BINARY_INTEGER` | `INTEGER` |
| `BLOB` | `BYTEA` |
| `BOOLEAN` | `BOOLEAN` |
| `CLOB` | `TEXT` |
| `DATE` | `TIMESTAMP` |
| `LONG` | `TEXT` |
| `NCLOB` | `TEXT` |
| `NUMBER` | `NUMERIC` |
| `NVARCHAR2` | `VARCHAR` |
| `PLS_INTEGER` | `INTEGER` |
| `RAW` | `BYTEA` |
| `SYS_REFCURSOR` | `REFCURSOR` |
| `TIMESTAMP` | `TIMESTAMP` |
| `VARCHAR2` | `VARCHAR` |
| `XMLTYPE` | `XML` |

## Bare-length character types (target: postgresql)

| Bare (length-less) type | postgresql large-text type |
|---|---|
| `NVARCHAR` | `TEXT` |
| `VARCHAR` | `TEXT` |

## DML-pipeline type emission (target: postgresql)

| Non-portable source type name | postgresql emission |
|---|---|
| `BINARY` | `BYTEA` |
| `BIT` | `BOOLEAN` |
| `BLOB` | `BYTEA` |
| `CLOB` | `TEXT` |
| `DATETIME` | `TIMESTAMP` |
| `DATETIME2` | `TIMESTAMP` |
| `DOUBLE` | `DOUBLE PRECISION` |
| `IMAGE` | `BYTEA` |
| `LONGBLOB` | `BYTEA` |
| `LONGTEXT` | `TEXT` |
| `MEDIUMBLOB` | `BYTEA` |
| `MEDIUMINT` | `INTEGER` |
| `MEDIUMTEXT` | `TEXT` |
| `MONEY` | `NUMERIC(19,4)` |
| `NCHAR` | `CHAR` |
| `NCLOB` | `TEXT` |
| `NTEXT` | `TEXT` |
| `NUMBER` | `NUMERIC` |
| `NVARCHAR` | `VARCHAR` |
| `NVARCHAR2` | `VARCHAR` |
| `RAW` | `BYTEA` |
| `SMALLDATETIME` | `TIMESTAMP` |
| `SMALLMONEY` | `NUMERIC(10,4)` |
| `TINYBLOB` | `BYTEA` |
| `TINYINT` | `SMALLINT` |
| `TINYTEXT` | `TEXT` |
| `UBIGINT` | `NUMERIC(20)` |
| `UDECIMAL` | `DECIMAL` |
| `UDOUBLE` | `DOUBLE PRECISION` |
| `UFLOAT` | `REAL` |
| `UINT` | `BIGINT` |
| `UMEDIUMINT` | `INTEGER` |
| `UNIQUEIDENTIFIER` | `UUID` |
| `USMALLINT` | `INTEGER` |
| `UTINYINT` | `SMALLINT` |
| `VARBINARY` | `BYTEA` |
| `VARCHAR2` | `VARCHAR` |
| `YEAR` | `SMALLINT` |

## Niladic / builtin expressions

| Construct | oracle form | postgresql form |
|---|---|---|
| `CURRENT_TIMESTAMP` | `SYSDATE` | `CURRENT_TIMESTAMP` |
| `CURRENT_DATE` | `TRUNC(SYSDATE)` | `CURRENT_DATE` |
| UUID generator | `SYS_GUID` | `gen_random_uuid` |
| Last identity value | `NULL /* last identity: use <sequence>.CURRVAL */` | `LASTVAL()` |
| DML-affected-rows predicate | `SQL%FOUND` | `FOUND` |
| Current error message | `SQLERRM` | `SQLERRM` |
| Diagnostic global `SQLSTATE` | `TO_CHAR(SQLCODE)` | `SQLSTATE` |
| Diagnostic global `SQLCODE` | `SQLCODE` | — |

## Built-ins of oracle with no cross-engine equivalent

Built-in functions of oracle that the catalog (`unique.core.builtins._ENGINE_STANDARD`) records as having **no cross-engine equivalent on any target** — a call to one of these degrades to a documented carrier + warning wherever it lands off oracle:

`CAST_TO_NVARCHAR2`, `CAST_TO_RAW`, `CAST_TO_VARCHAR2`, `COLLECT`, `EDIT_DISTANCE`,
`EDIT_DISTANCE_SIMILARITY`, `JARO_WINKLER`, `JARO_WINKLER_SIMILARITY`, `ODCIDATELIST`,
`ODCINUMBERLIST`, `ODCIVARCHAR2LIST`, `XMLAGG`, `XMLELEMENT`
