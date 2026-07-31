[← DDL: identity, temp tables, foreign keys, sequences, storage options](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=ddl type="Inline DDL attributes decomposed into standalone statements" direction="cross-engine" kind=article order=19 -->

# Inline DDL attributes decomposed into standalone statements: MySQL `COMMENT`, T-SQL inline `INDEX`

**Problem.** MySQL lets a column or table carry a `COMMENT '...'` right
inside its `CREATE TABLE`, and T-SQL lets a table element declare an
`INDEX` inline alongside its columns. Neither PostgreSQL nor Oracle has an
inline form for either — but that doesn't mean the information has nowhere
to go: both engines have a perfectly good *standalone* statement for it,
which is where you'd expect the comment or the index to land, not simply
dropped.

**Solution.**

A MySQL column `COMMENT` materializes as a `COMMENT ON COLUMN` statement
right after the `CREATE TABLE`:

```sql
-- mysql source
CREATE TABLE t (a INT COMMENT 'note');
-- => oracle / postgresql
CREATE TABLE t (
  a INT
);
COMMENT ON COLUMN t.a IS 'note';
```

A table-level `COMMENT='...'` option becomes `COMMENT ON TABLE` the same
way:

```sql
-- mysql source
CREATE TABLE t (a INT) COMMENT='my table';
-- => oracle / postgresql
CREATE TABLE t (
  a INT
);
COMMENT ON TABLE t IS 'my table';
```

T-SQL's inline `INDEX` table element is reconstructed the same way, but the
inline form survives on the two engines that natively support it
(T-SQL/MySQL) and only gets split out on the two that don't
(PostgreSQL/Oracle):

```sql
-- tsql source
CREATE TABLE t (id INT, name VARCHAR(50), INDEX ix_name NONCLUSTERED (name));

-- => postgresql / oracle: a separate CREATE INDEX after the table
CREATE TABLE t (
  id INT,
  name VARCHAR(50)
);
CREATE INDEX ix_name ON t (name);

-- => mysql: kept inline
CREATE TABLE t (
  id INT,
  name VARCHAR(50),
  INDEX ix_name (name)
);
```

**Discussion.** T-SQL's inline `INDEX ix (col)` element sits in the same
position as a column definition, which is how sqlglot's own parser reads
it — as a column literally named `INDEX` — unless the transpiler recognizes
the shape and reconstructs it as an index declaration before emitting.
Once recognized, the decomposition follows each target's own grammar:
PostgreSQL and Oracle have no table-element syntax for either a comment or
an inline index at all, so both need a standalone statement immediately
after the `CREATE TABLE` — `COMMENT ON COLUMN`/`COMMENT ON TABLE` for the
comment (both engines' native comment mechanism) and `CREATE INDEX` for the
index. T-SQL and MySQL, which both support the inline index form natively,
keep it inline rather than manufacturing an unnecessary second statement.

> **Note** faithful — live-verified: the `COMMENT ON COLUMN`/`COMMENT ON
> TABLE` statements execute and the comment text reads back unchanged on
> PostgreSQL/Oracle; the reconstructed `CREATE INDEX ix_name ON t (name)`
> executes on PostgreSQL/Oracle, and the inline form executes unchanged on
> MySQL — no `"INDEX"`-as-column-name leftover on any target.

**See Also.** Corpus [`mysql-drop-'note'`](../../../tests/fixtures/challenge/challenge_mysql.sql),
[`mysql-drop2-my`](../../../tests/fixtures/challenge/challenge_mysql.sql),
[`ts-inline-index2`](../../../tests/fixtures/challenge/challenge_sqlserver.sql) ·
[`TestMysqlComments`](../../../tests/integration/test_challenge.py),
[`TestInlineIndexReconstructed`](../../../tests/integration/test_challenge.py) ·
[§2](../../03-unsupported.md), "Column `COMMENT` → T-SQL," for T-SQL's own
comment vehicle (`sp_addextendedproperty`, noted rather than synthesized).
