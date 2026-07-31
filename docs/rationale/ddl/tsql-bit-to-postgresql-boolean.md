[← DDL: identity, temp tables, foreign keys, sequences, storage options](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=ddl type="Cross-statement schema-state-driven coercion" direction="tsql → postgresql" kind=article order=4 -->

# T-SQL `BIT` `0`/`1` values (defaults, `INSERT`, `UPDATE`, incl. inside procedure bodies) → PostgreSQL `BOOLEAN`

**Problem.** T-SQL's `BIT` type behaves like a 1-bit integer: `0`/`1`
literals are valid in a `DEFAULT` clause, an `INSERT ... VALUES` list, or an
`UPDATE ... SET`, with no special casting. PostgreSQL's `BOOLEAN` has no
implicit integer cast at all — `BOOLEAN DEFAULT 1` and `is_active = 0` are
both rejected outright (`column "is_active" is of type boolean but
expression is of type integer`).

**Solution.**

```sql
-- tests/unit/core/test_boolean_timestamp.py::TestBitDefaultToBoolean
CREATE TABLE t (is_active BIT NOT NULL DEFAULT 1)
-- tsql -> postgresql:
CREATE TABLE t (
  is_active BOOLEAN NOT NULL DEFAULT TRUE
);
```

```sql
-- tests/unit/core/test_boolean_timestamp.py::TestBitLiteralCoercion (SCRIPT)
CREATE TABLE dbo.product (id INT NOT NULL, qty INT NOT NULL, is_active BIT NOT NULL DEFAULT 1)
GO
INSERT INTO dbo.product (id, qty, is_active) VALUES (1, 1, 1)
GO
UPDATE dbo.product SET is_active = 0, qty = 0 WHERE id = 1
GO
-- tsql -> postgresql:
INSERT INTO product (id, qty, is_active)
VALUES (1, 1, TRUE);

UPDATE product
SET is_active = FALSE, qty = 0
WHERE id = 1;
```

The `qty` column (a plain `INT`, not `BIT`) keeps its integer literal on
every target — only the columns the script itself declared `BIT` are
rewritten. The same script transpiled `tsql -> mysql` keeps `1`/`0`
verbatim: MySQL's own `BIT`/`TINYINT` already accepts integer literals
natively, so no coercion is needed there. The coercion also reaches an
`INSERT` embedded in a stored procedure body, using the same column-type
information gathered from the script's own `CREATE TABLE`:

```sql
-- tsql -> postgresql, INSERT inside CREATE PROCEDURE dbo.mk @id INT AS BEGIN ... END
INSERT INTO invoice (id, is_paid) VALUES (v_id, FALSE);
```

**Discussion.** A bare `0`/`1` literal carries no type information by
itself — the only way to know it must become `TRUE`/`FALSE` is to already
know, from an earlier statement, that the column it is being written to was
declared `BIT`. Unique tracks every column's declared type from its
`CREATE TABLE` and keeps consulting that for every later
`INSERT`/`UPDATE`/`DEFAULT`, in or out of a procedure body, so the coercion
follows the column's declared type wherever it is written to, not just at
the point where the type was declared.

> **Note** faithful — same boolean value, spelled in each target's own
> literal domain; MySQL is deliberately left untouched because its `BIT`
> already tolerates the integer spelling (a rewrite there would be
> unnecessary, not merely harmless).

**See Also.** [`TestBitDefaultToBoolean`, `TestBitLiteralCoercion`](../../../tests/unit/core/test_boolean_timestamp.py).
