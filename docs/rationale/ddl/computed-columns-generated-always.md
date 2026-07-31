[← DDL: identity, temp tables, foreign keys, sequences, storage options](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=ddl type="Computed columns" direction="cross-engine" kind=article order=18 -->

# `GENERATED ALWAYS AS (expr)` computed columns (cross-engine)

**Problem.** A computed (generated) column derives its value from an
expression over other columns in the same row, recalculated automatically
on every read or write — a fundamentally different thing from an
auto-incrementing identity column, even though MySQL spells the two very
differently and PostgreSQL's `GENERATED ALWAYS AS (...)` clause is shared
syntax for both. You expect the migrated column to keep computing its
value, not to start generating sequence numbers.

**Solution.**

```sql
-- mysql source
CREATE TABLE t (a INT, b INT GENERATED ALWAYS AS (a + 1));

-- => tsql: no declared type, computed-column syntax
CREATE TABLE t (
  a INT,
  b AS (a + 1)
);

-- => postgresql: STORED (PostgreSQL has no VIRTUAL/on-read form)
CREATE TABLE t (
  a INT,
  b INT GENERATED ALWAYS AS (a + 1) STORED
);

-- => oracle: keeps the VIRTUAL expression form
CREATE TABLE t (
  a NUMBER(10),
  b NUMBER(10) GENERATED ALWAYS AS (a + 1)
);
```

Each target gets its own native computed-column spelling: T-SQL's bare
`b AS (expr)` (no declared type — T-SQL infers it from the expression),
PostgreSQL's `GENERATED ALWAYS AS (expr) STORED` (`STORED` is mandatory
there; PostgreSQL has no on-read/`VIRTUAL` form), and Oracle/MySQL's
`GENERATED ALWAYS AS (expr)` (implicitly `VIRTUAL`, computed on read). With
`a = 5`, every target computes `b = 6`, live-verified.

MySQL's own shorthand — `b INT AS (expr) STORED` (no `GENERATED ALWAYS`
keyword) — models the same computed-column concept and reaches T-SQL as
`AS ... PERSISTED` (T-SQL's on-disk-computed-column keyword):

```sql
-- mysql source
CREATE TABLE t (a INT, b INT AS (a+1) STORED);

-- => tsql
CREATE TABLE t (
  a INT,
  b AS (a + 1) PERSISTED
);
```

A computed column that references another computed column — invalid on
PostgreSQL/T-SQL, which forbid a generated expression over another
generated column — has the referenced column's own expression inlined in
its place instead of being emitted as a dangling reference:

```sql
-- mysql source: my-gencol2 — b is itself computed, c references b
CREATE TABLE t (a INT, b INT AS (a*2) STORED, c INT AS (a+b) VIRTUAL, KEY(b));

-- => postgresql: c's reference to b is inlined (a + a*2), not "a + b"
CREATE TABLE t (
  a INT,
  b INT GENERATED ALWAYS AS (a * 2) STORED,
  c INT GENERATED ALWAYS AS (a + a * 2) STORED
);
-- => tsql: b is STORED in MySQL (PERSISTED); c stays VIRTUAL (on-read, no PERSISTED)
CREATE TABLE t (
  a INT,
  b AS (a * 2) PERSISTED,
  c AS (a + a * 2)
);
```

A computed column referenced by a `CHECK`/`UNIQUE` constraint gains
`PERSISTED` on T-SQL even without an index (T-SQL errors 1764/2733
otherwise, since a constraint can't validate against a purely virtual,
on-read value):

```sql
-- my-gen-constr, mysql → tsql
CREATE TABLE t (a INT, b INT GENERATED ALWAYS AS (a+1) VIRTUAL, UNIQUE (b), CHECK (b>a));
-- => b AS (a + 1) PERSISTED, ...
```

**Discussion.** sqlglot's own AST models MySQL's/PostgreSQL's/Oracle's
generated-column clause with the same node it uses for an identity
(auto-increment) column, so the two constructs — one computed from an
expression, one assigned from an internal counter — collapse together
unless the transpiler tells them apart before emitting. Once told apart,
each target's own generated-column grammar is used, since none of the four
share one spelling: T-SQL wants no type at all on a computed column (it
derives one), PostgreSQL requires the `STORED` keyword explicitly (it has
no lazy/`VIRTUAL` evaluation mode to choose instead), and Oracle/MySQL's
`VIRTUAL` form is implicit when no storage keyword is given. The
chained-reference inlining exists because PostgreSQL and T-SQL apply a
"generated-over-generated" restriction MySQL/Oracle don't — without
inlining, the same source that's legal on MySQL would fail to create on
those two targets.

> **Note** faithful — live-verified: with `a = 5`, `b = 6` on T-SQL,
> PostgreSQL and Oracle; the `my-gencol2` chained case gives `(5, 10, 15)`
> for `(a, b, c)` exact on PostgreSQL and T-SQL; the constrained-computed
> case gives `(3, 4)` exact on T-SQL.

**See Also.** Corpus [`drop-GENERATED`](../../../tests/fixtures/challenge/challenge_mysql.sql),
[`my-gencol2`](../../../tests/fixtures/challenge/challenge_mysql.sql),
[`my-gen-constr`](../../../tests/fixtures/challenge/challenge_mysql.sql),
[`my-json-index`](../../../tests/fixtures/challenge/challenge_mysql.sql) ·
[`TestGeneratedColumn`](../../../tests/integration/test_challenge.py),
[`TestTypedComputedColumnShorthand`](../../../tests/integration/test_challenge.py).
