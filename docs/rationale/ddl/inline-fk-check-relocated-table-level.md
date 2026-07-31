[← DDL: identity, temp tables, foreign keys, sequences, storage options](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=ddl type="Inline column-level constraints relocated to table-level" direction="cross-engine" kind=article order=22 direction-inferred=true -->

# An inline column-level `REFERENCES`/`CHECK` constraint → a table-level constraint clause

**Problem.** `c INT REFERENCES p(id) ON DELETE CASCADE` and `c INT CHECK (c
> 0)` declare a foreign key or check constraint directly on the column,
inline inside its own definition — every engine accepts this shorthand.
Read naively as "just a column definition plus a type," the constraint
itself is easy to drop entirely, silently losing the referential-integrity
or validation rule the source author relied on.

**Solution.**

```sql
-- tests/integration/test_clause_drops.py::test_inline_fk_with_on_delete_survives_to_every_target
CREATE TABLE t (a INT, b INT REFERENCES p(id) ON DELETE CASCADE)
-- postgresql -> tsql / mysql / oracle:
CREATE TABLE t (
  a INT,
  b INT,
  FOREIGN KEY (b) REFERENCES p (id) ON DELETE CASCADE
)

-- tests/integration/test_clause_drops.py::test_inline_check_survives
CREATE TABLE t (a INT CHECK (a > 0))
-- postgresql/mysql -> tsql:
CREATE TABLE t (
  a INT,
  CHECK (a > 0)
)
```

**Discussion.** Unique reads the inline constraint off the column
definition and re-emits it as its table-level equivalent — a standalone
`FOREIGN KEY (col) REFERENCES ...` or `CHECK (...)` clause listed alongside
the columns, rather than attached to the column's own type declaration.
Every target engine's grammar accepts the table-level form for both
constraint kinds, so relocating rather than inlining is not a
compatibility workaround for any one engine — it's simply the shape
Unique's `CREATE TABLE` converter already produces every constraint in,
inline or not, keeping one code path for both. The referential action
(`ON DELETE CASCADE`) and the check predicate travel with the constraint
unchanged.

> **Note** faithful — the same foreign key / check rule applies to the same
> column; only its *position* inside the `CREATE TABLE` statement changes,
> which has no effect on the constraint's own semantics. No warning.

**See Also.** [`test_clause_drops.py`](../../../tests/integration/test_clause_drops.py)
(`test_inline_fk_with_on_delete_survives_to_every_target`,
`test_inline_check_survives`, `test_inline_fk_without_action_survives`).
