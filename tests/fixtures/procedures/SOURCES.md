# Procedural SQL Fixtures

These two scripts exercise the transpiler against realistic **stored-procedure**
workloads — the procedural surface (variables, cursors, control flow, dynamic
SQL, batch separators) that the schema-only fixtures in `../real_world/` don't
cover.

- `procedures_sqlserver.sql` — T-SQL: ~50 procedures and a handful of functions.
- `procedures_oracle.sql` — Oracle PL/SQL: ~26 procedures and functions.

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
