# Procedural SQL Fixtures

These two scripts exercise the transpiler against realistic **stored-procedure**
workloads — the procedural surface (variables, cursors, control flow, dynamic
SQL, batch separators) that the schema-only fixtures in `../real_world/` don't
cover.

- `procedures_sqlserver.sql` — T-SQL: ~50 procedures and a handful of functions.
- `procedures_oracle.sql` — Oracle PL/SQL: ~26 procedures and functions,
  generated from the T-SQL fixture by the transpiler.
- `procedures_mysql.sql` — MySQL: generated from the T-SQL fixture by the
  transpiler (T-SQL → MySQL). Routines are wrapped in `DELIMITER $$` blocks,
  non-portable T-SQL types/functions are mapped to MySQL equivalents
  (`SQL_VARIANT` → `LONGTEXT`, `CONVERT` → `CAST`/`STR_TO_DATE`, `HASHBYTES`
  → `SHA2`, `STRING_SPLIT` → `JSON_TABLE`), and any type without a faithful
  equivalent keeps its original in a `/* UNIQUE: … */` comment. Regenerate via
  the transpiler rather than editing by hand.
- `procedures_postgresql.sql` — PostgreSQL: generated from the T-SQL fixture by
  the transpiler (T-SQL → PostgreSQL). Routines are PL/pgSQL with dollar-quoted
  (`AS $$ … $$`) bodies; the `dbo` schema is stripped, `OUTPUT` maps to
  `RETURNING`, table variables become `CREATE TEMPORARY TABLE`, and
  `NEWSEQUENTIALID()`/`NEWID()` map to `gen_random_uuid()`. Types with no
  faithful equivalent (e.g. `SQL_VARIANT`) carry a `TEXT /* UNIQUE: … */`
  marker. Regenerate via the transpiler rather than editing by hand.

## Provenance and anonymization

They are derived from a real-world script that was **fully anonymized** before
inclusion: every table, column, variable, procedure and function name was
replaced with generic identifiers (`tbl_N`, `col_N`, `var_N`, `proc_N`,
`funcN()`), string literals were neutralized (their content replaced while
preserving length and structure), and comments were reduced to a syntactically
representative minimum. No original names, data, or business meaning remain; the
files are kept solely for their **syntax**.

To keep the scripts self-contained and runnable, any function that the code
calls but does not define is provided as a small stub at the top of each file
(for example, a `NOW()`-style helper returning `DATEADD(day, -3, GETDATE())` in
T-SQL and `SYSDATE - 3` in Oracle).

## Intended use

Parsing/transpilation coverage today; once accompanying DDL is added, they are
also meant to be **executed against real engines** (SQL Server and Oracle) in CI
to validate that transpiled output runs, not just parses.
