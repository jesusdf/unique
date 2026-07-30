# mysql → postgresql: function & type mappings

> **Generated — do not edit by hand.** Produced by `python scripts/generate_reference_docs.py` from `src/unique/core/mappings.py`. The CI freshness gate (`python scripts/generate_reference_docs.py --check`) fails the build if this file drifts from the source data.

Both pipelines share this data (audit doc 03): the procedural pipeline rewrites raw routine text using the pair-keyed tables below; the DML pipeline converts through sqlglot's canonical names, so its type table is keyed by target only. See [SKILL-development-workflow.md](../../skills/SKILL-development-workflow.md) · "Dual-pipeline symmetry rule".

## Procedural function renames

| Source function | Target form | Note |
|---|---|---|
| `CURDATE` | `CURRENT_DATE` | — |
| `IFNULL` | `COALESCE` | — |
| `RAND` | `RANDOM` | — |
| `UUID` | `GEN_RANDOM_UUID` | — |

## Procedural type renames

| Source type | Target type |
|---|---|
| `BLOB` | `BYTEA` |
| `DATETIME` | `TIMESTAMP` |
| `DOUBLE` | `DOUBLE PRECISION` |
| `LONGBLOB` | `BYTEA` |
| `LONGTEXT` | `TEXT` |
| `MEDIUMBLOB` | `BYTEA` |
| `MEDIUMINT` | `INTEGER` |
| `MEDIUMTEXT` | `TEXT` |
| `TINYBLOB` | `BYTEA` |
| `TINYINT` | `SMALLINT` |
| `TINYTEXT` | `TEXT` |

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

| Construct | mysql form | postgresql form |
|---|---|---|
| `CURRENT_TIMESTAMP` | `CURRENT_TIMESTAMP` | `CURRENT_TIMESTAMP` |
| `CURRENT_DATE` | `CURDATE()` | `CURRENT_DATE` |
| UUID generator | `UUID` | `gen_random_uuid` |
| Last identity value | `LAST_INSERT_ID()` | `LASTVAL()` |
| DML-affected-rows predicate | `(ROW_COUNT() > 0)` | `FOUND` |
| Current error message | — | `SQLERRM` |
| Diagnostic global `SQLSTATE` | — | `SQLSTATE` |
| Diagnostic global `SQLCODE` | — | — |

## Built-ins of mysql with no cross-engine equivalent

Built-in functions of mysql that the catalog (`unique.core.builtins._ENGINE_STANDARD`) records as having **no cross-engine equivalent on any target** — a call to one of these degrades to a documented carrier + warning wherever it lands off mysql:

`JSON_MERGE_PATCH`, `JSON_MERGE_PRESERVE`
