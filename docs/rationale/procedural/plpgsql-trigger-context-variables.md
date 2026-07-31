[← Procedural: cursors, dynamic SQL, system procedures, session directives](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=procedural type="Triggers" direction="cross-engine" kind=article order=20 direction-inferred=true -->

# PL/pgSQL trigger context variables (`TG_NAME`/`TG_TABLE_NAME`/`TG_OP`/`TG_WHEN`/`TG_LEVEL`, `TG_ARGV`/`TG_NARGS`) → compile-time constants once the function inlines

**Problem.** Inside a plpgsql trigger function, `TG_NAME`/`TG_TABLE_NAME`/
`TG_OP`/`TG_WHEN`/`TG_LEVEL` are implicit variables PostgreSQL's trigger
machinery populates at fire time, and `TG_ARGV[n]`/`TG_NARGS` read the
argument list supplied by the specific `CREATE TRIGGER ... EXECUTE FUNCTION
fn(arg1, arg2, ...)` that invoked it. None of these exist on T-SQL — a
trigger body referencing them ships as a bare, unmapped identifier (error
128, "The name ... is not permitted in this context").

**Solution.**

```sql
-- tests/integration/test_pg_source_wave1.py::TestTgContextConstants::test_tg_constants_substitute_tsql (postgresql -> tsql)
create function cf() returns trigger as $$
begin
  insert into log values (TG_NAME, TG_OP, TG_LEVEL);
  return null;
end$$ language plpgsql;
create trigger child1_ins after insert on child1
for each statement execute function cf();
-- transpiles to:
-- UNIQUE-1195: trigger function cf inlined into its T-SQL trigger
CREATE TRIGGER child1_ins ON child1
AFTER INSERT
AS
BEGIN
    INSERT INTO log VALUES ('child1_ins', 'INSERT', 'STATEMENT');
END
```

```sql
-- tests/integration/test_pg_source_wave1.py::TestTgArgvSubstitution::test_tg_argv_substitutes_tsql (postgresql -> tsql)
create function tf() returns trigger as $$
begin
  insert into log values (TG_ARGV[0], TG_NARGS);
  return null;
end$$ language plpgsql;
create trigger t1_ins after insert on t1
for each statement execute function tf('hello', 'world');
-- transpiles to:
-- UNIQUE-1195: trigger function tf inlined into its T-SQL trigger
CREATE TRIGGER t1_ins ON t1
AFTER INSERT
AS
BEGIN
    INSERT INTO log VALUES ('hello', 2);
END
```

An index past the end of the actual argument list
(`TestTgArgvSubstitution::test_tg_argv_out_of_range_degrades`: `TG_ARGV[3]`
against a trigger supplying only one argument) has no value to substitute —
the trigger degrades whole instead of leaving a bare `TG_ARGV` reference
behind.

**Discussion.** Every one of these is resolvable at *transpile* time, not
trigger-fire time, because Unique already inlines the trigger function's
body into its specific `CREATE TRIGGER` (the `-- UNIQUE-1195` comment
marking the standalone function dropped, documented in
[`warnings.md`](../../reference/warnings.md#unique-1195), is that same
inlining). `TG_NAME` is the trigger's own name, `TG_OP`/`TG_LEVEL` are fixed
by which `CREATE TRIGGER` clause is being converted (`AFTER INSERT`/`FOR
EACH STATEMENT`, here), and `TG_ARGV[n]` is simply the `n`-th literal in
that trigger's own `EXECUTE FUNCTION fn(...)` argument list — none of these
vary at runtime for a *specific* compiled trigger the way they do for the
general-purpose function PostgreSQL lets you attach to many triggers at
once. Substituting them as literals is exact for that one trigger; it does
mean a single reusable plpgsql trigger function attached to several `CREATE
TRIGGER`s compiles into several *different* T-SQL trigger bodies, one per
attachment — the same per-trigger duplication the MySQL event-predicate
rewrite above already does, for a different reason.

> **Note** faithful — every constant substituted is fixed for the lifetime
> of that specific compiled trigger; nothing about it varies from one firing
> to the next.

**See Also.** [`TestTgContextConstants`](../../../tests/integration/test_pg_source_wave1.py),
[`TestTgArgvSubstitution`](../../../tests/integration/test_pg_source_wave1.py) ·
not the `NEW`/`OLD` `IS DISTINCT FROM` rewrite in the event-predicates entry
above (that restates Oracle's `UPDATING('col')` predicate; this entry
substitutes the trigger's own identity/argument metadata) · not the general
`IS [NOT] DISTINCT FROM` operator, documented separately in
[booleans.md](../booleans/README.md) ("Null-safe equality: `IS [NOT] DISTINCT FROM`
has no target operator").
