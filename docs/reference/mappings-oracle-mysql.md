# oracle → mysql: function & type mappings

> **Generated — do not edit by hand.** Produced by `python scripts/generate_reference_docs.py` from `src/unique/core/mappings.py`. The CI freshness gate (`python scripts/generate_reference_docs.py --check`) fails the build if this file drifts from the source data.

Both pipelines share this data (audit doc 03): the procedural pipeline rewrites raw routine text using the pair-keyed tables below; the DML pipeline converts through sqlglot's canonical names, so its type table is keyed by target only. See [SKILL-development-workflow.md](../../skills/SKILL-development-workflow.md) · "Dual-pipeline symmetry rule".

## Procedural function renames

| Source function | Target form | Note |
|---|---|---|
| `CHR` | `CHAR` | — |
| `LENGTH` | `CHAR_LENGTH` | — |
| `NVL` | `IFNULL` | — |
| `SUBSTR` | `SUBSTRING` | — |
| `SYS_GUID` | `UUID` | — |

## Procedural type renames

| Source type | Target type |
|---|---|
| `BINARY_DOUBLE` | `DOUBLE` |
| `BINARY_FLOAT` | `FLOAT` |
| `BINARY_INTEGER` | `INT` |
| `BLOB` | `LONGBLOB` |
| `BOOLEAN` | `TINYINT(1)` |
| `CLOB` | `LONGTEXT` |
| `DATE` | `DATETIME` |
| `LONG` | `LONGTEXT` |
| `NCLOB` | `LONGTEXT` |
| `NUMBER` | `DECIMAL` |
| `NVARCHAR2` | `VARCHAR` |
| `PLS_INTEGER` | `INT` |
| `RAW` | `VARBINARY` |
| `TIMESTAMP` | `DATETIME` |
| `VARCHAR2` | `VARCHAR` |
| `XMLTYPE` | `TEXT` |

## Bare-length character types (target: mysql)

| Bare (length-less) type | mysql large-text type |
|---|---|
| `NVARCHAR` | `LONGTEXT` |
| `VARCHAR` | `LONGTEXT` |

## DML-pipeline type emission (target: mysql)

| Non-portable source type name | mysql emission |
|---|---|
| `CLOB` | `LONGTEXT` |
| `DATETIME2` | `DATETIME` |
| `FLOAT4` | `FLOAT` |
| `FLOAT8` | `DOUBLE` |
| `IMAGE` | `LONGBLOB` |
| `INT2` | `SMALLINT` |
| `INT4` | `INT` |
| `INT8` | `BIGINT` |
| `MONEY` | `DECIMAL(19,4)` |
| `NCHAR` | `CHAR` |
| `NCLOB` | `LONGTEXT` |
| `NTEXT` | `LONGTEXT` |
| `NUMBER` | `DECIMAL` |
| `NVARCHAR` | `VARCHAR` |
| `NVARCHAR2` | `VARCHAR` |
| `SMALLDATETIME` | `DATETIME` |
| `SMALLMONEY` | `DECIMAL(10,4)` |
| `TIMESTAMPTZ` | `TIMESTAMP` |
| `TIMETZ` | `TIME` |
| `UBIGINT` | `BIGINT UNSIGNED` |
| `UINT` | `INT UNSIGNED` |
| `UMEDIUMINT` | `MEDIUMINT UNSIGNED` |
| `UNIQUEIDENTIFIER` | `CHAR(36)` |
| `USMALLINT` | `SMALLINT UNSIGNED` |
| `UTINYINT` | `TINYINT UNSIGNED` |
| `UUID` | `CHAR(36)` |
| `VARCHAR2` | `VARCHAR` |

## Niladic / builtin expressions

| Construct | oracle form | mysql form |
|---|---|---|
| `CURRENT_TIMESTAMP` | `SYSDATE` | `CURRENT_TIMESTAMP` |
| `CURRENT_DATE` | `TRUNC(SYSDATE)` | `CURDATE()` |
| UUID generator | `SYS_GUID` | `UUID` |
| Last identity value | `NULL /* last identity: use <sequence>.CURRVAL */` | `LAST_INSERT_ID()` |
| DML-affected-rows predicate | `SQL%FOUND` | `(ROW_COUNT() > 0)` |
| Current error message | `SQLERRM` | — |
| Diagnostic global `SQLSTATE` | `TO_CHAR(SQLCODE)` | — |
| Diagnostic global `SQLCODE` | `SQLCODE` | — |

## Built-ins of oracle with no cross-engine equivalent

Built-in functions of oracle that the catalog (`unique.core.builtins._ENGINE_STANDARD`) records as having **no cross-engine equivalent on any target** — a call to one of these degrades to a documented carrier + warning wherever it lands off oracle:

`CAST_TO_NVARCHAR2`, `CAST_TO_RAW`, `CAST_TO_VARCHAR2`, `COLLECT`, `EDIT_DISTANCE`,
`EDIT_DISTANCE_SIMILARITY`, `JARO_WINKLER`, `JARO_WINKLER_SIMILARITY`, `ODCIDATELIST`,
`ODCINUMBERLIST`, `ODCIVARCHAR2LIST`, `XMLAGG`, `XMLELEMENT`
