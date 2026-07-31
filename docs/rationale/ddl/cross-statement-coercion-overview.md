[← DDL: identity, temp tables, foreign keys, sequences, storage options](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=ddl type="Cross-statement schema-state-driven coercion" direction="—" kind=overview order=3 -->

# Cross-statement schema-state-driven coercion

The three entries below share one mechanism: a single statement cannot be
transpiled correctly by looking at its own text alone, because the correct
output depends on a column's *declared* type or nullability, established
somewhere earlier in the same script (a `CREATE TABLE`, a prior `ALTER
TABLE`, even a prior `RENAME COLUMN`) or on the column's role inside the
*same* `CREATE TABLE`. Unique tracks this column-level state across the
whole input and carries it forward to every later statement that touches
the column — including procedure bodies, whose embedded DML sees the same
tracked state.
