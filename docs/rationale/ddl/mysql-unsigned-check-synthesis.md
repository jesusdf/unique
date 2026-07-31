[← DDL: identity, temp tables, foreign keys, sequences, storage options](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=ddl type="Non-negativity constraint synthesis" direction="mysql → tsql/oracle/postgresql" kind=article order=20 -->

# MySQL `UNSIGNED` → widened signed type + synthesized `CHECK (col >= 0)`

**Problem.** A MySQL `UNSIGNED` integer column can never hold a negative
value — that's enforced structurally by the column's own type, not by a
constraint. PostgreSQL, Oracle and T-SQL have no unsigned integer type at
all: the column has to widen to a signed type large enough to hold the same
range, but a bare signed column drops the non-negativity guarantee the
source schema relied on.

**Solution.**

```sql
-- mysql source
CREATE TABLE t (a INT UNSIGNED);

-- => tsql / postgresql
CREATE TABLE t (
  a BIGINT CHECK (a >= 0)
);

-- => oracle
CREATE TABLE t (
  a NUMBER(10) CHECK (a >= 0)
);

-- => mysql (unchanged)
CREATE TABLE t (
  a INT UNSIGNED
);
```

`INT UNSIGNED`'s range (`0` to `4294967295`) needs `BIGINT` to fit signed
on PostgreSQL/T-SQL (a signed `INT` tops out at `2147483647`); Oracle's
`NUMBER(10)` already has the range as a decimal type. On every target, a
`CHECK (a >= 0)` is added alongside the widened type, so an `INSERT` of a
negative value is rejected the same way it would be on the MySQL source
(where the type itself makes a negative value inexpressible), and the
column's own maximum unsigned value still stores. Live-verified: the max
unsigned value stores and a negative insert is rejected on all three
targets.

**Discussion.** Widening the type alone is only half the constraint: an
unsigned MySQL column expresses two things at once — a wider positive-only
range, and the impossibility of a negative value — and only the first of
those survives a type-name mapping by itself. The `CHECK` constraint
reinstates the second half explicitly, since none of PostgreSQL, Oracle or
T-SQL has an unsigned integer type to fall back on structurally. The two
changes always travel together: whichever signed type is wide enough for
the source's unsigned range also needs the `CHECK` to stay equivalent, not
just equivalent-shaped.

> **Note** faithful — live-verified: `INT UNSIGNED`'s maximum value
> (`4294967295`) stores on the widened `BIGINT`/`NUMBER(10)` columns, and
> an `INSERT` of a negative value is rejected by the synthesized `CHECK` on
> PostgreSQL, T-SQL and Oracle, matching MySQL's own rejection.

**See Also.** Corpus [`mysql-drop4-UNSIGNED|CHE`](../../../tests/fixtures/challenge/challenge_mysql.sql) ·
[`TestUnsignedCheck`](../../../tests/integration/test_challenge.py).
