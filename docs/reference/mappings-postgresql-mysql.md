# postgresql → mysql: function & type mappings

> **Generated — do not edit by hand.** Produced by `python scripts/generate_reference_docs.py` from `src/unique/core/mappings.py`. The CI freshness gate (`python scripts/generate_reference_docs.py --check`) fails the build if this file drifts from the source data.

Both pipelines share this data (audit doc 03): the procedural pipeline rewrites raw routine text using the pair-keyed tables below; the DML pipeline converts through sqlglot's canonical names, so its type table is keyed by target only. See [SKILL-development-workflow.md](../../skills/SKILL-development-workflow.md) · "Dual-pipeline symmetry rule".

## Procedural function renames

| Source function | Target form | Note |
|---|---|---|
| `CHR` | `CHAR` | — |
| `COALESCE` | `COALESCE` | — |
| `CURRENT_DATE` | `CURRENT_DATE` | — |
| `GEN_RANDOM_UUID` | `UUID` | — |
| `RANDOM` | `RAND` | — |

## Procedural type renames

| Source type | Target type |
|---|---|
| `BIGSERIAL` | `BIGINT` |
| `BPCHAR` | `CHAR` |
| `BYTEA` | `LONGBLOB` |
| `DOUBLE PRECISION` | `DOUBLE` |
| `FLOAT4` | `FLOAT` |
| `FLOAT8` | `DOUBLE` |
| `INT2` | `SMALLINT` |
| `INT4` | `INT` |
| `INT8` | `BIGINT` |
| `JSONB` | `JSON` |
| `NAME` | `CHAR` |
| `SERIAL` | `INT` |
| `TIMESTAMPTZ` | `TIMESTAMP` |
| `UUID` | `CHAR(36)` |

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

| Construct | postgresql form | mysql form |
|---|---|---|
| `CURRENT_TIMESTAMP` | `CURRENT_TIMESTAMP` | `CURRENT_TIMESTAMP` |
| `CURRENT_DATE` | `CURRENT_DATE` | `CURDATE()` |
| UUID generator | `gen_random_uuid` | `UUID` |
| Last identity value | `LASTVAL()` | `LAST_INSERT_ID()` |
| DML-affected-rows predicate | `FOUND` | `(ROW_COUNT() > 0)` |
| Current error message | `SQLERRM` | — |
| Diagnostic global `SQLSTATE` | `SQLSTATE` | — |
| Diagnostic global `SQLCODE` | — | — |

## Built-ins of postgresql with no cross-engine equivalent

Built-in functions of postgresql that the catalog (`unique.core.builtins._ENGINE_STANDARD`) records as having **no cross-engine equivalent on any target** — a call to one of these degrades to a documented carrier + warning wherever it lands off postgresql:

`GROUPING`, `XMLELEMENT`
