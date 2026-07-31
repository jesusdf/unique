[← Procedural: cursors, dynamic SQL, system procedures, session directives](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=procedural type="Return-type and signature synthesis" direction="postgresql → tsql/oracle/mysql" kind=article order=13 -->

# `RETURNS void` (PostgreSQL) → neutral scalar return type + synthesized `RETURN` (MySQL / T-SQL / Oracle)

**Problem.** A PostgreSQL function declared `RETURNS void` returns nothing —
per the corpus's own count, the single most common plpgsql function shape
(62 occurrences), typically a side-effecting helper invoked for its
`INSERT`/`UPDATE`, never for a value. MySQL, T-SQL, and Oracle have no
`void` function return type at all: a function must declare a real scalar
type, and every code path must reach a value-carrying `RETURN`.

**Solution.**

```sql
-- tests/integration/test_pg_source_wave1.py::TestReturnsVoid (postgresql -> ...)
create function vf(a int) returns void as $$
begin
  insert into t values(a);
end$$ language plpgsql;
```

```sql
-- -> mysql (test_void_mysql):
CREATE FUNCTION vf
(
    a int
)
RETURNS INT
DETERMINISTIC
BEGIN
    INSERT INTO t VALUES (a);
    RETURN 0;
END

-- -> tsql (test_void_tsql):
CREATE FUNCTION vf
(
    @a int
)
RETURNS INT
AS
BEGIN
    INSERT INTO t VALUES (@a);
    RETURN 0;
END

-- -> oracle (test_void_oracle):
CREATE OR REPLACE FUNCTION vf
(
    a IN int
)
RETURN NUMBER
AS
BEGIN
    INSERT INTO t VALUES (a);
    RETURN NULL;
END;
/
```

A body that already ends its own control flow with an explicit `RETURN;`
(valid PG syntax to exit a void function early or normally) is not followed
by a second synthesized one — the existing `RETURN;` itself is the one that
gains the neutral value (`TestReturnsVoid::test_existing_trailing_return_not_duplicated`:
a function whose body is just `return;` transpiles to exactly one `RETURN
0;`, not two).

**Discussion.** MySQL/T-SQL settle on the same neutral pick (`INT`/`0`) —
both need *some* scalar type and neither has an obvious sentinel for "no
value"; Oracle instead picks `NUMBER`/`NULL`, since `NULL` is PL/SQL's own
honest "no value" answer and, unlike MySQL/T-SQL, it can actually be
returned from any scalar-typed function. A bare `RETURN;` already present
in the body — PG's own idiom for a void function that wants to exit without
a value — is folded to the same neutral value rather than followed by a
second, synthesized `RETURN`, which is what keeps the count at one `RETURN`
instead of two.

> **Note** faithful — nothing about the void function's real behavior (it
> returns nothing meaningful) is lost: callers of a PG void function never
> consume its return value, and the synthesized value is never read by
> anything else Unique generates.

**See Also.** [`TestReturnsVoid`](../../../tests/integration/test_pg_source_wave1.py).
