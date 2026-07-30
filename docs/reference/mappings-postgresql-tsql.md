# postgresql → tsql: function & type mappings

> **Generated — do not edit by hand.** Produced by `python scripts/generate_reference_docs.py` from `src/unique/core/mappings.py`. The CI freshness gate (`python scripts/generate_reference_docs.py --check`) fails the build if this file drifts from the source data.

Both pipelines share this data (audit doc 03): the procedural pipeline rewrites raw routine text using the pair-keyed tables below; the DML pipeline converts through sqlglot's canonical names, so its type table is keyed by target only. See [SKILL-development-workflow.md](../../skills/SKILL-development-workflow.md) · "Dual-pipeline symmetry rule".

## Procedural function renames

| Source function | Target form | Note |
|---|---|---|
| `CEIL` | `CEILING` | — |
| `CHR` | `CHAR` | — |
| `COALESCE` | `COALESCE` | — |
| `GEN_RANDOM_UUID` | `NEWID` | — |
| `LENGTH` | `LEN` | — |

## Procedural type renames

| Source type | Target type |
|---|---|
| `BOOL` | `BIT` |
| `BOOLEAN` | `BIT` |
| `BPCHAR` | `VARCHAR` |
| `BYTEA` | `VARBINARY(MAX)` |
| `DOUBLE PRECISION` | `FLOAT` |
| `FLOAT4` | `REAL` |
| `FLOAT8` | `FLOAT` |
| `INT2` | `SMALLINT` |
| `INT4` | `INT` |
| `INT8` | `BIGINT` |
| `JSON` | `NVARCHAR(MAX)` |
| `JSONB` | `NVARCHAR(MAX)` |
| `NAME` | `VARCHAR` |
| `TEXT` | `NVARCHAR(MAX)` |
| `TIMESTAMPTZ` | `DATETIMEOFFSET` |
| `UUID` | `UNIQUEIDENTIFIER` |

## Bare-length character types (target: tsql)

| Bare (length-less) type | tsql large-text type |
|---|---|
| `NVARCHAR` | `NVARCHAR(MAX)` |
| `VARCHAR` | `VARCHAR(MAX)` |

## DML-pipeline type emission (target: tsql)

| Non-portable source type name | tsql emission |
|---|---|
| `BLOB` | `VARBINARY(MAX)` |
| `BOOLEAN` | `BIT` |
| `BYTEA` | `VARBINARY(MAX)` |
| `CLOB` | `VARCHAR(MAX)` |
| `DOUBLE` | `FLOAT` |
| `FLOAT4` | `REAL` |
| `FLOAT8` | `FLOAT` |
| `INT2` | `SMALLINT` |
| `INT4` | `INT` |
| `INT8` | `BIGINT` |
| `LONGBLOB` | `VARBINARY(MAX)` |
| `LONGTEXT` | `NVARCHAR(MAX)` |
| `MEDIUMBLOB` | `VARBINARY(MAX)` |
| `MEDIUMINT` | `INT` |
| `MEDIUMTEXT` | `NVARCHAR(MAX)` |
| `NCLOB` | `NVARCHAR(MAX)` |
| `NUMBER` | `NUMERIC` |
| `NVARCHAR2` | `NVARCHAR` |
| `SERIAL` | `INT` |
| `TEXT` | `NVARCHAR(MAX)` |
| `TIMESTAMP` | `DATETIME2` |
| `TIMESTAMPTZ` | `DATETIMEOFFSET` |
| `TINYBLOB` | `VARBINARY(MAX)` |
| `TINYTEXT` | `NVARCHAR(MAX)` |
| `UBIGINT` | `NUMERIC(20)` |
| `UDOUBLE` | `FLOAT` |
| `UINT` | `BIGINT` |
| `UMEDIUMINT` | `INT` |
| `USMALLINT` | `INT` |
| `UTINYINT` | `TINYINT` |
| `UUID` | `UNIQUEIDENTIFIER` |
| `VARCHAR2` | `VARCHAR` |
| `YEAR` | `SMALLINT` |

## Niladic / builtin expressions

| Construct | postgresql form | tsql form |
|---|---|---|
| `CURRENT_TIMESTAMP` | `CURRENT_TIMESTAMP` | `GETDATE()` |
| `CURRENT_DATE` | `CURRENT_DATE` | `CAST(GETDATE() AS DATE)` |
| UUID generator | `gen_random_uuid` | `NEWID` |
| Last identity value | `LASTVAL()` | `SCOPE_IDENTITY()` |
| DML-affected-rows predicate | `FOUND` | `(@@ROWCOUNT > 0)` |
| Current error message | `SQLERRM` | `ERROR_MESSAGE()` |
| Diagnostic global `SQLSTATE` | `SQLSTATE` | `CAST(ERROR_STATE() AS NVARCHAR(5))` |
| Diagnostic global `SQLCODE` | — | `CAST(ERROR_NUMBER() AS NVARCHAR(20))` |

## Built-ins of postgresql with no cross-engine equivalent

Built-in functions of postgresql that the catalog (`unique.core.builtins._ENGINE_STANDARD`) records as having **no cross-engine equivalent on any target** — a call to one of these degrades to a documented carrier + warning wherever it lands off postgresql:

`GROUPING`, `XMLELEMENT`

## Foreign builtins gated on T-SQL output

Built-in functions of the other three engines with **no name-level mapping onto T-SQL** (`core/mappings.py:FOREIGN_BUILTIN_FUNCTIONS`). If one of these reaches T-SQL output unqualified, the transpiler must not silently qualify it as a phantom `dbo.<name>` user function — it is a visible mapping gap:

`ADD_MONTHS`, `AGE`, `ARRAY_AGG`, `ARRAY_TO_STRING`, `BITAND`, `CHR`, `CURDATE`, `CURRENT_DATE`,
`CURTIME`, `DATE_ADD`, `DATE_FORMAT`, `DATE_PART`, `DATE_SUB`, `DATE_TRUNC`, `DBMS_RANDOM`,
`DECODE`, `DECODE_BASE64`, `EMPTY_BLOB`, `EMPTY_CLOB`, `ENCODE`, `EXTRACT`, `FROM_UNIXTIME`,
`GEN_RANDOM_UUID`, `GREATEST`, `GROUP_CONCAT`, `HEXTORAW`, `IF`, `IFNULL`, `INITCAP`, `INSTR`,
`LAST_DAY`, `LEAST`, `LENGTH`, `LISTAGG`, `LOCATE`, `LPAD`, `MD5`, `MOD`, `MONTHS_BETWEEN`,
`NEXT_DAY`, `NOW`, `NVL`, `NVL2`, `ORA_HASH`, `PG_SLEEP`, `POSITION`, `RAWTOHEX`,
`REGEXP_COUNT`, `REGEXP_INSTR`, `REGEXP_LIKE`, `REGEXP_REPLACE`, `REGEXP_SUBSTR`, `RPAD`,
`SHA1`, `SHA2`, `SPLIT_PART`, `STANDARD_HASH`, `STRING_TO_ARRAY`, `STRPOS`, `STR_TO_DATE`,
`SUBSTR`, `SYSDATE`, `SYSTIMESTAMP`, `SYS_CONTEXT`, `SYS_GUID`, `TIMESTAMPADD`, `TIMESTAMPDIFF`,
`TO_BINARY_DOUBLE`, `TO_CHAR`, `TO_CLOB`, `TO_DATE`, `TO_NUMBER`, `TO_TIMESTAMP`, `TRUNC`,
`TRUNCATE`, `UNIX_TIMESTAMP`, `UNNEST`, `USERENV`, `UUID`, `WM_CONCAT`, `XMLAGG`, `XMLELEMENT`
