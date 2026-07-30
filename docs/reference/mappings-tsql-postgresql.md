# tsql → postgresql: function & type mappings

> **Generated — do not edit by hand.** Produced by `python scripts/generate_reference_docs.py` from `src/unique/core/mappings.py`. The CI freshness gate (`python scripts/generate_reference_docs.py --check`) fails the build if this file drifts from the source data.

Both pipelines share this data (audit doc 03): the procedural pipeline rewrites raw routine text using the pair-keyed tables below; the DML pipeline converts through sqlglot's canonical names, so its type table is keyed by target only. See [SKILL-development-workflow.md](../../skills/SKILL-development-workflow.md) · "Dual-pipeline symmetry rule".

## Procedural function renames

| Source function | Target form | Note |
|---|---|---|
| `CEILING` | `CEIL` | — |
| `DATEADD` | _manual conversion needed_ | DATEADD requires interval arithmetic |
| `DATEDIFF` | _manual conversion needed_ | DATEDIFF requires manual conversion |
| `GETUTCDATE` | `NOW() AT TIME ZONE 'UTC'` | — |
| `ISNULL` | `COALESCE` | — |
| `LEN` | `LENGTH` | — |
| `LOWER` | `LOWER` | — |
| `NEWID` | `GEN_RANDOM_UUID` | — |
| `REPLACE` | `REPLACE` | — |
| `SUBSTRING` | `SUBSTRING` | — |
| `UPPER` | `UPPER` | — |

## Procedural type renames

| Source type | Target type |
|---|---|
| `BIGINT` | `BIGINT` |
| `BINARY` | `BYTEA` |
| `BIT` | `BOOLEAN` |
| `DATETIME` | `TIMESTAMP` |
| `DATETIME2` | `TIMESTAMP` |
| `FLOAT` | `DOUBLE PRECISION` |
| `IMAGE` | `BYTEA` |
| `INT` | `INTEGER` |
| `MONEY` | `NUMERIC(19,4)` |
| `NTEXT` | `TEXT` |
| `NVARCHAR` | `VARCHAR` |
| `REAL` | `REAL` |
| `SMALLDATETIME` | `TIMESTAMP` |
| `SMALLINT` | `SMALLINT` |
| `TEXT` | `TEXT` |
| `TINYINT` | `SMALLINT` |
| `UNIQUEIDENTIFIER` | `UUID` |
| `VARBINARY` | `BYTEA` |
| `VARCHAR` | `VARCHAR` |
| `XML` | `XML` |

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

| Construct | tsql form | postgresql form |
|---|---|---|
| `CURRENT_TIMESTAMP` | `GETDATE()` | `CURRENT_TIMESTAMP` |
| `CURRENT_DATE` | `CAST(GETDATE() AS DATE)` | `CURRENT_DATE` |
| UUID generator | `NEWID` | `gen_random_uuid` |
| Last identity value | `SCOPE_IDENTITY()` | `LASTVAL()` |
| DML-affected-rows predicate | `(@@ROWCOUNT > 0)` | `FOUND` |
| Current error message | `ERROR_MESSAGE()` | `SQLERRM` |
| Diagnostic global `SQLSTATE` | `CAST(ERROR_STATE() AS NVARCHAR(5))` | `SQLSTATE` |
| Diagnostic global `SQLCODE` | `CAST(ERROR_NUMBER() AS NVARCHAR(20))` | — |

## Built-ins of tsql with no cross-engine equivalent

Built-in functions of tsql that the catalog (`unique.core.builtins._ENGINE_STANDARD`) records as having **no cross-engine equivalent on any target** — a call to one of these degrades to a documented carrier + warning wherever it lands off tsql:

`IDENT_CURRENT`
