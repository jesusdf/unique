[← DDL: identity, temp tables, foreign keys, sequences, storage options](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=ddl type="DROP emitted idempotently" direction="tsql → postgresql" kind=article order=27 direction-inferred=true -->

# A plain `DROP TABLE t` → `DROP TABLE IF EXISTS t` on PostgreSQL

**Problem.** A migration script is meant to be re-runnable against a
target that may already have run it once before — a bare `DROP TABLE t`
errors on a second run if the table is already gone, stopping the whole
script partway through.

**Solution.**

```sql
-- tests/unit/core/test_ddl_flags.py::TestDropGuard
DROP TABLE tbl
-- tsql -> postgresql:
DROP TABLE IF EXISTS tbl;
```

**Discussion.** Unique emits every `DROP TABLE` idempotently by default,
independent of whether the source script itself guarded the drop — the
same re-runnability principle behind this project's `CREATE OR
REPLACE`/`CREATE OR ALTER` view- and routine-recreation policy: a
migration script should tolerate being executed more than once rather than
failing on the second run because an earlier statement already did its
job. `IF EXISTS` changes nothing about a *first* run (the table is there,
so it drops exactly as a bare `DROP TABLE` would) and only changes the
outcome of a run where the object is already absent, turning a hard error
into a silent no-op for that one statement.

> **Note** faithful on a first run (the table drops exactly as requested);
> a deliberate, documented policy divergence on a re-run, where the
> source's own bare `DROP TABLE` would have errored and Unique's output
> instead continues. No warning — this is the same re-runnability stance
> the project already takes for `CREATE OR REPLACE VIEW`.

**See Also.** [`test_ddl_flags.py::TestDropGuard`](../../../tests/unit/core/test_ddl_flags.py)
(`test_drop_is_idempotent`) · [§4](../../03-unsupported.md), "Behavioral
Differences (Not Bugs)" (view re-creation, the sibling re-runnability
policy for `CREATE`).
