# mysql → oracle: function & type mappings

> **Generated — do not edit by hand.** Produced by `python scripts/generate_reference_docs.py` from `src/unique/core/mappings.py`. The CI freshness gate (`python scripts/generate_reference_docs.py --check`) fails the build if this file drifts from the source data.

Both pipelines share this data (audit doc 03): the procedural pipeline rewrites raw routine text using the pair-keyed tables below; the DML pipeline converts through sqlglot's canonical names, so its type table is keyed by target only. See [SKILL-development-workflow.md](../../skills/SKILL-development-workflow.md) · "Dual-pipeline symmetry rule".

## Procedural function renames

| Source function | Target form | Note |
|---|---|---|
| `CHAR_LENGTH` | `LENGTH` | — |
| `CURDATE` | `TRUNC(SYSDATE)` | — |
| `IFNULL` | `NVL` | — |
| `SUBSTRING` | `SUBSTR` | — |
| `UUID` | `SYS_GUID` | — |

## Procedural type renames

| Source type | Target type |
|---|---|
| `BIGINT` | `NUMBER(19)` |
| `BLOB` | `BLOB` |
| `BOOL` | `NUMBER(1)` |
| `BOOLEAN` | `NUMBER(1)` |
| `DATETIME` | `TIMESTAMP` |
| `DECIMAL` | `NUMBER` |
| `DOUBLE` | `BINARY_DOUBLE` |
| `INT` | `NUMBER(10)` |
| `INTEGER` | `NUMBER(10)` |
| `LONGBLOB` | `BLOB` |
| `LONGTEXT` | `CLOB` |
| `MEDIUMBLOB` | `BLOB` |
| `MEDIUMINT` | `NUMBER(7)` |
| `MEDIUMTEXT` | `CLOB` |
| `NUMERIC` | `NUMBER` |
| `SMALLINT` | `NUMBER(5)` |
| `TEXT` | `CLOB` |
| `TINYBLOB` | `BLOB` |
| `TINYINT` | `NUMBER(3)` |
| `TINYTEXT` | `CLOB` |
| `VARCHAR` | `VARCHAR2` |

## Bare-length character types (target: oracle)

| Bare (length-less) type | oracle large-text type |
|---|---|
| `NVARCHAR2` | `NVARCHAR2(2000)` |
| `VARCHAR2` | `VARCHAR2(4000)` |

## DML-pipeline type emission (target: oracle)

| Non-portable source type name | oracle emission |
|---|---|
| `BIGINT` | `NUMBER(19)` |
| `BINARY` | `RAW` |
| `BIT` | `NUMBER(1)` |
| `BLOB` | `BLOB` |
| `DATETIME` | `TIMESTAMP` |
| `DATETIME2` | `TIMESTAMP` |
| `DOUBLE` | `BINARY_DOUBLE` |
| `FLOAT4` | `BINARY_FLOAT` |
| `FLOAT8` | `BINARY_DOUBLE` |
| `IMAGE` | `BLOB` |
| `INT` | `NUMBER(10)` |
| `INT2` | `SMALLINT` |
| `INT4` | `INTEGER` |
| `INT8` | `NUMBER(19)` |
| `LONGBLOB` | `BLOB` |
| `LONGTEXT` | `CLOB` |
| `MEDIUMBLOB` | `BLOB` |
| `MEDIUMINT` | `NUMBER(7)` |
| `MEDIUMTEXT` | `CLOB` |
| `MONEY` | `NUMBER(19,4)` |
| `NTEXT` | `NCLOB` |
| `NVARCHAR` | `NVARCHAR2` |
| `SMALLDATETIME` | `DATE` |
| `SMALLMONEY` | `NUMBER(10,4)` |
| `TEXT` | `CLOB` |
| `TIMESTAMPTZ` | `TIMESTAMP WITH TIME ZONE` |
| `TINYBLOB` | `BLOB` |
| `TINYINT` | `NUMBER(3)` |
| `TINYTEXT` | `CLOB` |
| `UBIGINT` | `NUMBER(20)` |
| `UDECIMAL` | `NUMBER` |
| `UDOUBLE` | `BINARY_DOUBLE` |
| `UFLOAT` | `FLOAT` |
| `UINT` | `NUMBER(10)` |
| `UMEDIUMINT` | `NUMBER(8)` |
| `UNIQUEIDENTIFIER` | `RAW(16)` |
| `USMALLINT` | `NUMBER(5)` |
| `UTINYINT` | `NUMBER(3)` |
| `UUID` | `RAW(16)` |
| `VARBINARY` | `RAW` |
| `VARCHAR` | `VARCHAR2` |
| `YEAR` | `NUMBER(4)` |

## Niladic / builtin expressions

| Construct | mysql form | oracle form |
|---|---|---|
| `CURRENT_TIMESTAMP` | `CURRENT_TIMESTAMP` | `SYSDATE` |
| `CURRENT_DATE` | `CURDATE()` | `TRUNC(SYSDATE)` |
| UUID generator | `UUID` | `SYS_GUID` |
| Last identity value | `LAST_INSERT_ID()` | `NULL /* last identity: use <sequence>.CURRVAL */` |
| DML-affected-rows predicate | `(ROW_COUNT() > 0)` | `SQL%FOUND` |
| Current error message | — | `SQLERRM` |
| Diagnostic global `SQLSTATE` | — | `TO_CHAR(SQLCODE)` |
| Diagnostic global `SQLCODE` | — | `SQLCODE` |

> Month/quarter/year `DATEADD` targeting Oracle uses a day-preserving rewrite (`oracle_month_add_daypreserving` in `core/mappings.py`) rather than a bare `ADD_MONTHS` call; see [docs/rationale/datetime.md](../rationale/datetime.md) for the worked example.

## Built-ins of mysql with no cross-engine equivalent

Built-in functions of mysql that the catalog (`unique.core.builtins._ENGINE_STANDARD`) records as having **no cross-engine equivalent on any target** — a call to one of these degrades to a documented carrier + warning wherever it lands off mysql:

`JSON_MERGE_PATCH`, `JSON_MERGE_PRESERVE`
