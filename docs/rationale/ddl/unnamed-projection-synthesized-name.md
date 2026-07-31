[← DDL: identity, temp tables, foreign keys, sequences, storage options](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=ddl type="Synthesized identifiers for anonymous constructs" direction="cross-engine" kind=article order=16 direction-inferred=true -->

# Unnamed derived-table / `SELECT ... INTO` projections → synthesized `uq_col1` (T-SQL)

**Problem.** `SELECT (SELECT a) t` or `SELECT (SELECT 1) t` — a derived
table whose single projected column is a bare parameter reference or a
literal, with no alias — is legal on PostgreSQL/MySQL/Oracle (the column
gets an engine-assigned display name that nothing else references). T-SQL
rejects it outright (error 8155, "every column in a derived table must
have an alias").

**Solution.**

```sql
-- corpus case my-reads-sql
CREATE FUNCTION f(a INT) RETURNS INT READS SQL DATA BEGIN RETURN (SELECT COUNT(*) FROM (SELECT a) t); END
-- mysql -> tsql:
RETURN (SELECT COUNT(*) FROM (SELECT @a AS uq_col1) t);
```

```sql
-- corpus case my-select-into-out
CREATE PROCEDURE p(OUT c INT) BEGIN SELECT COUNT(*) INTO c FROM (SELECT 1) t; END
-- mysql -> tsql:
SELECT @c = COUNT(*) FROM (SELECT 1 AS uq_col1) AS t;
```

A literal projection (`SELECT 1`) is aliased the same way as a bare
parameter reference (`SELECT a`) — both are "not a name," so both get
`uq_col1` — pinned separately by the `my-scalar-subquery-assign` corpus
case (`(SELECT 1) t` inside a `SET v = ...` assignment, not a `SELECT
INTO` tail), which confirms the alias is synthesized regardless of which
statement shape wraps the derived table.

**Discussion.** Two independent code paths reach this: the IR-first
pipeline's general derived-table naming (`my-reads-sql`,
`my-scalar-subquery-assign`) and a dedicated sqlglot-AST pass for the
`SELECT ... INTO` tail specifically
(`_name_derived_columns`/`my-select-into-out`, described in the corpus
case as "the text-path twin of the IR `_name_tsql_derived_columns`") —
both converge on the same `uq_col1` synthesized name so the two paths
produce indistinguishable output for a reader of the transpiled script.

> **Note** faithful — the synthesized alias is never referenced by any
> other part of the query (these are all single-column, unreferenced
> derived tables), so the name itself is arbitrary; only T-SQL's mandatory-
> alias rule is being satisfied.

**See Also.** [`my-reads-sql`, `my-select-into-out`, `my-scalar-subquery-assign`](../../../tests/fixtures/challenge/challenge_mysql.sql).
