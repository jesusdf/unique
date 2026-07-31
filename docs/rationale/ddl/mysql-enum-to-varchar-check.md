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
-- target (VARCHAR + CHECK):
CREATE TABLE redb_en (a VARCHAR(3) CHECK (a IN ('lo', 'mid', 'hi')));
INSERT INTO redb_en VALUES ('hi'), ('lo'), ('mid');
SELECT a FROM redb_en
ORDER BY CASE a WHEN 'lo' THEN 1 WHEN 'mid' THEN 2 WHEN 'hi' THEN 3 END ASC;
-- result on every target: 'lo','mid','hi' — MySQL's own declaration order
```

`VARCHAR(n) CHECK (col IN (…))` preserves the value-list constraint, and
`ORDER BY` on the column is rewritten to an ordinal `CASE` expression that
reproduces MySQL's declaration-index order rather than a plain
alphabetical sort.

**Discussion.** None of the other three engines has an
ordered-enumeration column type, so the column itself becomes
`VARCHAR(<max value length>)` plus an inline `CHECK (col IN
('lo','mid','hi'))` reproducing the value-list constraint. A plain
`VARCHAR` sorts **alphabetically**, which would reorder rows wherever
declaration order and alphabetical order disagree (live-diffed: MySQL's
own `('lo','mid','hi')` vs plain-alphabetical `('hi','lo','mid')`), so
`ORDER BY <enum-col>` is rewritten into the ordinal `CASE c WHEN 'lo' THEN
1 WHEN 'mid' THEN 2 … END` sort key on every target instead. Comparisons
(`<`/`>`) and `MIN`/`MAX` are left as plain string semantics: MySQL itself
uses string comparison for those outside a sort context (live-verified on
MySQL 8.4), so the `VARCHAR`+`CHECK` degrade already matches MySQL there —
rewriting them to the ordinal form would introduce a divergence instead of
closing one.

> **Note** faithful for `ORDER BY` on a directly-declared `ENUM` column, and
> for comparisons and `MIN`/`MAX` (MySQL itself already uses string
> semantics for those). `[limit]` when the column's value list cannot be
> resolved — through `SELECT *`, a derived table, or dynamic SQL — where the
> value is preserved but the ordering falls back to alphabetical.

**See Also.** [`my-enum-order`](../../../tests/fixtures/challenge/challenge_mysql.sql).
