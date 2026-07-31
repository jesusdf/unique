[← Procedural: cursors, dynamic SQL, system procedures, session directives](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=procedural type="Triggers" direction="cross-engine" kind=article order=21 direction-inferred=true -->

# PG named transition tables (`REFERENCING ... TABLE AS alias`) → T-SQL `inserted`/`deleted` alias rename

**Problem.** A PostgreSQL statement trigger can name its transition tables
(`REFERENCING NEW TABLE AS newtab`), and the inlined function body reads
rows through that chosen alias. T-SQL's transition tables are the two fixed
pseudo-tables `inserted`/`deleted` — there is no way to rename them, so a
body still referencing `newtab` ships as a table that was never created.

**Solution.**

```sql
-- tests/integration/test_pg_source_wave1.py::TestTransitionTableAliases::test_new_table_alias_becomes_inserted (postgresql -> tsql)
create function ttf() returns trigger as $$
begin
  insert into log select a from newtab where a <> 'newtab';
  return null;
end$$ language plpgsql;
create trigger tg after insert on d
referencing new table as newtab
for each statement execute function ttf();
-- transpiles to:
-- UNIQUE-1195: trigger function ttf inlined into its T-SQL trigger
CREATE TRIGGER tg ON d
AFTER INSERT
AS
BEGIN
    INSERT INTO log SELECT a FROM inserted WHERE a <> 'newtab';
END
```

Only the identifier renames — the string literal `'newtab'`, which happens
to spell the same word, stays untouched, confirming the rewrite operates on
the parsed identifier reference, not a text search-and-replace. PostgreSQL
itself keeps the native `REFERENCING` clause unchanged
(`TestTransitionTableAliases::test_pg_keeps_referencing`).

**Discussion.** The reverse direction also occurs: a T-SQL trigger's fixed
`inserted`/`deleted` become **named** PostgreSQL transition tables when
translating PG-ward (see [the sibling article](tsql-set-based-trigger-to-pg-statement-level.md)).
Here the traffic runs the other way — a PostgreSQL-authored **custom**
alias collapses back down to T-SQL's two fixed pseudo-table names, which
is why every reference to that alias throughout the inlined body has to be
renamed rather than simply carried through.

> **Note** faithful — `inserted` and the source's named transition table
> hold exactly the same batch of affected rows; only the spelling changes.

**See Also.** [`TestTransitionTableAliases`](../../../tests/integration/test_pg_source_wave1.py) ·
[A purely set-based T-SQL trigger → PostgreSQL statement-level trigger](tsql-set-based-trigger-to-pg-statement-level.md)
(the reverse-direction rewrite).
