[← DDL: identity, temp tables, foreign keys, sequences, storage options](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=ddl type="Synthesized identifiers for anonymous constructs" direction="postgresql → tsql" kind=article order=15 -->

# Nameless `CREATE INDEX ON t(col)` (PostgreSQL) → T-SQL

**Problem.** PostgreSQL allows `CREATE INDEX ON t (col)` with no index
name — the server picks one internally (`t_col_idx`-shaped, but never
surfaced to the script). T-SQL's `CREATE INDEX` grammar has no anonymous
form at all: an index name is mandatory syntax.

**Solution.**

```sql
-- tests/unit/core/test_ir_first_families.py::TestZeroPushW2Batch::test_nameless_create_index_in_trigger_gets_name
create table ddl_t (c1 integer, c2 integer);
create or replace function ddl_fn() returns trigger as $$
begin
  create index on ddl_t (c2);
  return new;
end$$ language plpgsql;
create trigger ddl_fn_t before insert on ddl_t for each row
  execute procedure ddl_fn();
-- postgresql -> tsql:
CREATE TABLE ddl_t (
  c1 INT,
  c2 INT
)
GO

CREATE TRIGGER ddl_fn_t ON ddl_t
AFTER INSERT
AS
BEGIN
    CREATE INDEX ddl_t_c2_idx ON dbo.ddl_t (c2);
END
```

The synthesized name follows PostgreSQL's own internal convention
(`<table>_<column>_idx`), so it reads the same way a PostgreSQL DBA
inspecting the catalog would expect, even though T-SQL never actually
computes it server-side.

**Discussion.** The rewrite reaches a `CREATE INDEX` even when it appears
*inside* a PL/pgSQL trigger function body (the example above), not just at
the top level — the trigger function itself gets inlined into the T-SQL
trigger (`UNIQUE-1195`, a separate degrade covering PL/pgSQL-function-into-
trigger inlining, unrelated to the index naming), and the nameless index
inside that inlined body still needs a name to be valid T-SQL.

> **Note** faithful — an index by any name behaves identically; only a
> name T-SQL requires but PostgreSQL's grammar doesn't is being supplied.

**See Also.** [`TestZeroPushW2Batch::test_nameless_create_index_in_trigger_gets_name`](../../../tests/unit/core/test_ir_first_families.py) ·
[`UNIQUE-1195`](../../reference/warnings.md#unique-1195) (the unrelated trigger-inlining degrade in the same example).
