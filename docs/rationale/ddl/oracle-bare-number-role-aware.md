[← DDL: identity, temp tables, foreign keys, sequences, storage options](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=ddl type="Cross-statement schema-state-driven coercion" direction="cross-engine" kind=article order=6 direction-inferred=true -->

# Oracle bare `NUMBER` (no precision/scale) → role-aware numeric (B47)

**Problem.** Oracle's unqualified `NUMBER` — no precision or scale — is
overloaded. It is the idiomatic spelling for an integer id/count column
(`id NUMBER GENERATED ALWAYS AS IDENTITY`, `customer_id NUMBER` as an FK),
but it is *also* an arbitrary-precision numeric that legitimately holds a
fractional value (`discount_pct NUMBER`). It parses, dialect-neutrally, to
a bare `DECIMAL`. Two failure modes pull in opposite directions: a bare
`DECIMAL` cannot be `AUTO_INCREMENT` on MySQL and does not match an integer
PK for a foreign key on PostgreSQL (so id columns must become an integer
type), yet blindly promoting *every* bare `NUMBER` to `BIGINT` silently
**truncates** the fractional value of a non-id column.

**Solution — the mapping is role-aware.** The promotion to `BIGINT` fires
only when a **structural** signal makes the column id-like: it is (part of)
the `PRIMARY KEY`, is `UNIQUE`-constrained, is an identity, or is a
`FOREIGN KEY` / `REFERENCES` (which references another table's key — join
compatibility, rule 3). A name like `x_id` is *not* a signal — only the
schema structure is. Every other bare `NUMBER` keeps Oracle's arbitrary
precision: unbounded `NUMERIC` on PostgreSQL (faithful, no warning), and
the project's canonical bounded `DECIMAL(38, 10)` on MySQL/T-SQL — which
have no unbounded numeric type — **with a `UNIQUE-1236` warning** that the
precision is bounded there.

```sql
-- tests/unit/core/test_boolean_timestamp.py::TestOracleBareNumberToInteger (_DDL)
CREATE TABLE invoice (
  id NUMBER GENERATED ALWAYS AS IDENTITY,   -- identity  -> id-like
  customer_id NUMBER NOT NULL,              -- FK        -> id-like
  discount_pct NUMBER,                      -- no role   -> value
  unit_price NUMBER(10, 2) NOT NULL,        -- qualified -> unchanged
  CONSTRAINT fk FOREIGN KEY (customer_id) REFERENCES customer (id)
)
-- oracle -> mysql:
CREATE TABLE invoice (
  id BIGINT AUTO_INCREMENT,
  customer_id BIGINT NOT NULL,
  discount_pct DECIMAL(38, 10) NOT NULL,    -- + UNIQUE-1236 (precision bounded)
  unit_price DECIMAL(10, 2) NOT NULL,
  CONSTRAINT fk FOREIGN KEY (customer_id) REFERENCES customer (id)
);
-- oracle -> postgresql:
CREATE TABLE invoice (
  id BIGINT GENERATED ALWAYS AS IDENTITY,
  customer_id BIGINT NOT NULL,
  discount_pct NUMERIC,                      -- unbounded, faithful, no warning
  unit_price DECIMAL(10, 2) NOT NULL,
  CONSTRAINT fk FOREIGN KEY (customer_id) REFERENCES customer (id)
);
```

`NUMBER(10, 2)` (qualified — has precision/scale) keeps its `DECIMAL`
mapping unchanged: it is not a *bare* `NUMBER` and never reaches this logic.
A bare `DECIMAL` from a *non*-Oracle source is left completely alone
(`test_bare_decimal_from_tsql_source_unchanged`): `CREATE TABLE t (amount
DECIMAL)` from T-SQL stays `amount DECIMAL`/`NUMERIC` on PostgreSQL,
confirming the whole mechanism is gated on the Oracle source dialect, not
on "this looks like a bare decimal."

**Discussion.** The id-vs-value decision consults every structural
signal available for the column: the inline `PRIMARY KEY` / `UNIQUE` /
identity / `REFERENCES` constraints on the column itself, the table-level
`FOREIGN KEY` local columns, and any `PRIMARY KEY`/`UNIQUE` constraint
declared for the table in a separate statement. A non-id column is emitted
as an unbounded `NUMERIC` on PostgreSQL, which has an unbounded numeric
type; MySQL and T-SQL have none, so they get the project's canonical
bounded `DECIMAL(38, 10)` — the same spelling `TO_NUMBER` and the numeric
casts already use — with a `UNIQUE-1236` warning that the precision is
bounded there.

**See Also.** [`TestOracleBareNumberToInteger`](../../../tests/unit/core/test_boolean_timestamp.py).
