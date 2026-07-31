# tsql → oracle: function & type mappings

> **Generated — do not edit by hand.** Produced by `python scripts/generate_reference_docs.py` from `src/unique/core/mappings.py`. The CI freshness gate (`python scripts/generate_reference_docs.py --check`) fails the build if this file drifts from the source data.

Both pipelines share this data (audit doc 03): the procedural pipeline rewrites raw routine text using the pair-keyed tables below; the DML pipeline converts through sqlglot's canonical names, so its type table is keyed by target only. See [SKILL-development-workflow.md](../../skills/SKILL-development-workflow.md) · "Dual-pipeline symmetry rule".

## Procedural function renames

| Source function | Target form | Note |
|---|---|---|
| `CEILING` | `CEIL` | — |
| `DATEADD` | _manual conversion needed_ | DATEADD requires manual conversion |
| `DATEDIFF` | _manual conversion needed_ | DATEDIFF requires manual conversion |
| `GETUTCDATE` | `SYS_EXTRACT_UTC(SYSTIMESTAMP)` | — |
| `ISNULL` | `NVL` | — |
| `LEN` | `LENGTH` | — |
| `LOWER` | `LOWER` | — |
| `LTRIM` | `LTRIM` | — |
| `NEWID` | `SYS_GUID` | — |
| `REPLACE` | `REPLACE` | — |
| `RTRIM` | `RTRIM` | — |
| `SQUARE` | _manual conversion needed_ | SQUARE(x) -> x*x |
| `SUBSTRING` | `SUBSTR` | — |
| `UPPER` | `UPPER` | — |

## Procedural type renames

| Source type | Target type |
|---|---|
| `BIGINT` | `NUMBER(19)` |
| `BINARY` | `RAW` |
| `BIT` | `NUMBER(1)` |
| `CHAR` | `CHAR` |
| `DATE` | `DATE` |
| `DATETIME` | `DATE` |
| `DATETIME2` | `TIMESTAMP` |
| `DECIMAL` | `NUMBER` |
| `FLOAT` | `FLOAT` |
| `IMAGE` | `BLOB` |
| `INT` | `NUMBER(10)` |
| `INTEGER` | `NUMBER(10)` |
| `MONEY` | `NUMBER(19,4)` |
| `NCHAR` | `NCHAR` |
| `NTEXT` | `NCLOB` |
| `NUMERIC` | `NUMBER` |
| `NVARCHAR` | `NVARCHAR2` |
| `REAL` | `FLOAT` |
| `SMALLDATETIME` | `DATE` |
| `SMALLINT` | `NUMBER(5)` |
| `SMALLMONEY` | `NUMBER(10,4)` |
| `SQL_VARIANT` | `VARCHAR2(4000)` |
| `TEXT` | `CLOB` |
| `TIME` | `TIMESTAMP` |
| `TINYINT` | `NUMBER(3)` |
| `UNIQUEIDENTIFIER` | `RAW(16)` |
| `VARBINARY` | `RAW` |
| `VARCHAR` | `VARCHAR2` |
| `XML` | `XMLTYPE` |

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

| Construct | tsql form | oracle form |
|---|---|---|
| `CURRENT_TIMESTAMP` | `GETDATE()` | `SYSDATE` |
| `CURRENT_DATE` | `CAST(GETDATE() AS DATE)` | `TRUNC(SYSDATE)` |
| UUID generator | `NEWID` | `SYS_GUID` |
| Last identity value | `SCOPE_IDENTITY()` | `NULL /* last identity: use <sequence>.CURRVAL */` |
| DML-affected-rows predicate | `(@@ROWCOUNT > 0)` | `SQL%FOUND` |
| Current error message | `ERROR_MESSAGE()` | `SQLERRM` |
| Diagnostic global `SQLSTATE` | `CAST(ERROR_STATE() AS NVARCHAR(5))` | `TO_CHAR(SQLCODE)` |
| Diagnostic global `SQLCODE` | `CAST(ERROR_NUMBER() AS NVARCHAR(20))` | `SQLCODE` |

> Month/quarter/year `DATEADD` targeting Oracle uses a day-preserving rewrite (`oracle_month_add_daypreserving` in `core/mappings.py`) rather than a bare `ADD_MONTHS` call; see [docs/rationale/datetime/README.md](../rationale/datetime/README.md) for the worked example.

## Built-ins of tsql with no cross-engine equivalent

Built-in functions of tsql that the catalog (`unique.core.builtins._ENGINE_STANDARD`) records as having **no cross-engine equivalent on any target** — a call to one of these degrades to a documented carrier + warning wherever it lands off tsql:

`IDENT_CURRENT`
