# oracle → tsql: function & type mappings

> **Generated — do not edit by hand.** Produced by `python scripts/generate_reference_docs.py` from `src/unique/core/mappings.py`. The CI freshness gate (`python scripts/generate_reference_docs.py --check`) fails the build if this file drifts from the source data.

Both pipelines share this data (audit doc 03): the procedural pipeline rewrites raw routine text using the pair-keyed tables below; the DML pipeline converts through sqlglot's canonical names, so its type table is keyed by target only. See [SKILL-development-workflow.md](../../skills/SKILL-development-workflow.md) · "Dual-pipeline symmetry rule".

## Procedural function renames

| Source function | Target form | Note |
|---|---|---|
| `CEIL` | `CEILING` | — |
| `CHR` | `CHAR` | — |
| `LENGTH` | `LEN` | — |
| `NVL` | `ISNULL` | — |
| `SUBSTR` | `SUBSTRING` | — |
| `SYS_GUID` | `NEWID` | — |
| `TO_CHAR` | _manual conversion needed_ | TO_CHAR(x, fmt) requires manual conversion |
| `TO_DATE` | _manual conversion needed_ | TO_DATE(x, fmt) requires manual conversion |
| `TO_NUMBER` | _manual conversion needed_ | TO_NUMBER -> CAST(x AS DECIMAL(38, 10)) |
| `TRUNC` | _manual conversion needed_ | TRUNC requires manual conversion |

## Procedural type renames

| Source type | Target type |
|---|---|
| `ANYDATA` | `SQL_VARIANT` |
| `BINARY_INTEGER` | `INT` |
| `BLOB` | `VARBINARY(MAX)` |
| `BOOLEAN` | `BIT` |
| `CLOB` | `NVARCHAR(MAX)` |
| `DATE` | `DATETIME` |
| `NCLOB` | `NVARCHAR(MAX)` |
| `NUMBER` | `DECIMAL` |
| `NVARCHAR2` | `NVARCHAR` |
| `PLS_INTEGER` | `INT` |
| `RAW` | `VARBINARY` |
| `TIMESTAMP` | `DATETIME2` |
| `VARCHAR2` | `NVARCHAR` |
| `XMLTYPE` | `XML` |

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

| Construct | oracle form | tsql form |
|---|---|---|
| `CURRENT_TIMESTAMP` | `SYSDATE` | `GETDATE()` |
| `CURRENT_DATE` | `TRUNC(SYSDATE)` | `CAST(GETDATE() AS DATE)` |
| UUID generator | `SYS_GUID` | `NEWID` |
| Last identity value | `NULL /* last identity: use <sequence>.CURRVAL */` | `SCOPE_IDENTITY()` |
| DML-affected-rows predicate | `SQL%FOUND` | `(@@ROWCOUNT > 0)` |
| Current error message | `SQLERRM` | `ERROR_MESSAGE()` |
| Diagnostic global `SQLSTATE` | `TO_CHAR(SQLCODE)` | `CAST(ERROR_STATE() AS NVARCHAR(5))` |
| Diagnostic global `SQLCODE` | `SQLCODE` | `CAST(ERROR_NUMBER() AS NVARCHAR(20))` |

## Oracle date-format → T-SQL `CONVERT` style

| Oracle format | T-SQL CONVERT style |
|---|---|
| `DD/MM/YYYY` | 103 |
| `MM/DD/YYYY` | 101 |
| `YYYY-MM-DD` | 120 |
| `YYYYMMDD` | 112 |
| `DD-MM-YYYY` | 105 |
| `DD.MM.YYYY` | 104 |

## Built-ins of oracle with no cross-engine equivalent

Built-in functions of oracle that the catalog (`unique.core.builtins._ENGINE_STANDARD`) records as having **no cross-engine equivalent on any target** — a call to one of these degrades to a documented carrier + warning wherever it lands off oracle:

`CAST_TO_NVARCHAR2`, `CAST_TO_RAW`, `CAST_TO_VARCHAR2`, `COLLECT`, `EDIT_DISTANCE`,
`EDIT_DISTANCE_SIMILARITY`, `JARO_WINKLER`, `JARO_WINKLER_SIMILARITY`, `ODCIDATELIST`,
`ODCINUMBERLIST`, `ODCIVARCHAR2LIST`, `XMLAGG`, `XMLELEMENT`

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
