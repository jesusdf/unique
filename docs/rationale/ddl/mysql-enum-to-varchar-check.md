[← DDL: identity, temp tables, foreign keys, sequences, storage options](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=ddl type="MySQL `ENUM` degrade — open limitation" direction="mysql → tsql/oracle/postgresql" kind=article order=13 -->

# `ENUM('lo','mid','hi')` (MySQL) → PostgreSQL / T-SQL / Oracle VARCHAR + CHECK

**Problem.** A MySQL `ENUM` column stores one of a fixed value
list, and — the part that matters here — **orders by declaration index**,
not alphabetically: `ENUM('lo','mid','hi')` sorts `lo < mid < hi` regardless
of the values' lexical order.

**Solution.**

```sql
-- corpus case my-enum-order
CREATE TABLE redb_en (a ENUM('lo','mid','hi'));
INSERT INTO redb_en VALUES ('hi'),('lo'),('mid');
SELECT a FROM redb_en ORDER BY a;
-- target (VARCHAR + CHECK): 'hi','lo','mid' (alphabetical)
-- MySQL source: 'lo','mid','hi' (declaration order) — silently different, no warning
```

`VARCHAR(n) CHECK (col IN (…))` — the value-list
constraint is preserved; the declaration-order semantics are not.

**Discussion.** None of the other three engines has an
ordered-enumeration column type. Unique degrades the column declaration to
`VARCHAR(<max value length>)` plus an inline `CHECK (col IN ('lo','mid','hi'))`
reproducing the value-list constraint — but a plain `VARCHAR` sorts
**alphabetically**, so `ORDER BY`/`MIN`/`MAX`/comparisons on that column
silently change results wherever declaration order and alphabetical order
disagree (live-diffed: MySQL `('lo','mid','hi')` vs PostgreSQL
`('hi','lo','mid')`).

> **Note** faithful for ordering — **fixed 2026-07-30**: the converter
> harvests each `ENUM` column's declared value list into a cross-statement
> registry and rewrites `ORDER BY <enum-col>` into the ordinal
> `CASE c WHEN 'lo' THEN 1 WHEN 'mid' THEN 2 … END` sort key, so every
> target reproduces MySQL's declaration-index order. Comparisons
> (`<`/`>`) and `MIN`/`MAX` are intentionally **left as plain string
> semantics**: live verification on MySQL 8.4 showed MySQL itself uses
> string comparison for those outside a sort context, so the
> VARCHAR+CHECK degrade already matches them — rewriting them to the
> ordinal form would have *introduced* a divergence. An enum sorted
> through `SELECT *`, a derived table or dynamic SQL cannot be resolved
> and keeps the plain value (documented residual).

**See Also.** [`my-enum-order`](../../../tests/fixtures/challenge/challenge_mysql.sql) (`[fixed]`) ·
`transformer.py::_rewrite_enum_ordering` ·
`emit_ddl.py::_emit_enum_type`.
