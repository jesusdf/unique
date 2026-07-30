# tsql → mysql: function & type mappings

> **Generated — do not edit by hand.** Produced by `python scripts/generate_reference_docs.py` from `src/unique/core/mappings.py`. The CI freshness gate (`python scripts/generate_reference_docs.py --check`) fails the build if this file drifts from the source data.

Both pipelines share this data (audit doc 03): the procedural pipeline rewrites raw routine text using the pair-keyed tables below; the DML pipeline converts through sqlglot's canonical names, so its type table is keyed by target only. See [SKILL-development-workflow.md](../../skills/SKILL-development-workflow.md) · "Dual-pipeline symmetry rule".

## Procedural function renames

| Source function | Target form | Note |
|---|---|---|
| `CEILING` | `CEILING` | — |
| `DATEADD` | _manual conversion needed_ | DATEADD -> DATE_ADD with INTERVAL |
| `DATEDIFF` | _manual conversion needed_ | DATEDIFF differs (MySQL DATEDIFF returns days) |
| `GETUTCDATE` | `UTC_TIMESTAMP` | — |
| `ISNULL` | `IFNULL` | — |
| `LEN` | `CHAR_LENGTH` | — |
| `LOWER` | `LOWER` | — |
| `NEWID` | `UUID` | — |
| `REPLACE` | `REPLACE` | — |
| `SUBSTRING` | `SUBSTRING` | — |
| `UPPER` | `UPPER` | — |

## Procedural type renames

| Source type | Target type |
|---|---|
| `BIGINT` | `BIGINT` |
| `BINARY` | `BINARY` |
| `BIT` | `TINYINT(1)` |
| `CHAR` | `CHAR` |
| `DATE` | `DATE` |
| `DATETIME` | `DATETIME` |
| `DATETIME2` | `DATETIME` |
| `DECIMAL` | `DECIMAL` |
| `FLOAT` | `DOUBLE` |
| `IMAGE` | `LONGBLOB` |
| `INT` | `INT` |
| `INTEGER` | `INT` |
| `MONEY` | `DECIMAL(19,4)` |
| `NCHAR` | `CHAR` |
| `NTEXT` | `LONGTEXT` |
| `NUMERIC` | `DECIMAL` |
| `NVARCHAR` | `VARCHAR` |
| `REAL` | `FLOAT` |
| `SMALLDATETIME` | `DATETIME` |
| `SMALLINT` | `SMALLINT` |
| `SMALLMONEY` | `DECIMAL(10,4)` |
| `SQL_VARIANT` | `LONGTEXT` |
| `TEXT` | `TEXT` |
| `TIME` | `TIME` |
| `TINYINT` | `TINYINT` |
| `UNIQUEIDENTIFIER` | `CHAR(36)` |
| `VARBINARY` | `VARBINARY` |
| `VARCHAR` | `VARCHAR` |
| `XML` | `TEXT` |

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

| Construct | tsql form | mysql form |
|---|---|---|
| `CURRENT_TIMESTAMP` | `GETDATE()` | `CURRENT_TIMESTAMP` |
| `CURRENT_DATE` | `CAST(GETDATE() AS DATE)` | `CURDATE()` |
| UUID generator | `NEWID` | `UUID` |
| Last identity value | `SCOPE_IDENTITY()` | `LAST_INSERT_ID()` |
| DML-affected-rows predicate | `(@@ROWCOUNT > 0)` | `(ROW_COUNT() > 0)` |
| Current error message | `ERROR_MESSAGE()` | — |
| Diagnostic global `SQLSTATE` | `CAST(ERROR_STATE() AS NVARCHAR(5))` | — |
| Diagnostic global `SQLCODE` | `CAST(ERROR_NUMBER() AS NVARCHAR(20))` | — |

## Built-ins of tsql with no cross-engine equivalent

Built-in functions of tsql that the catalog (`unique.core.builtins._ENGINE_STANDARD`) records as having **no cross-engine equivalent on any target** — a call to one of these degrades to a documented carrier + warning wherever it lands off tsql:

`IDENT_CURRENT`
