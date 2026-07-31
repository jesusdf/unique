[← Procedural: cursors, dynamic SQL, system procedures, session directives](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=procedural type="Declaration modifier relaxation" direction="oracle/postgresql → tsql/mysql" kind=article order=62 -->

# `CONSTANT` variable declarations / cursor `[NO] SCROLL` → plain declaration on T-SQL/MySQL

**Problem.** Oracle and PostgreSQL both let a local variable declaration
carry `CONSTANT` (`name CONSTANT type := value`, a compile-time
reassignment guard) and a cursor declaration carry `[NO] SCROLL`
(non-forward fetch support). T-SQL and MySQL have neither concept: no
constant local variables, and no cursor scrollability modifier.

**Solution.**

```sql
-- oracle -> tsql / mysql
max_val CONSTANT NUMBER := 100;
-- => tsql
DECLARE @max_val DECIMAL = 100;
-- => mysql
DECLARE max_val DECIMAL DEFAULT 100;
```

```sql
-- postgresql -> mysql / oracle (cursor SCROLL)
declare c scroll cursor for select 1;
-- => mysql / oracle (SCROLL has no forward-only-cursor equivalent; dropped)
DECLARE c CURSOR FOR SELECT 1;
```

Both modifiers are simply omitted on the targets that cannot express them —
the initializer/query is unaffected, only the keyword itself disappears; no
comment or warning is attached. Going from PostgreSQL, `SCROLL` reaches
**T-SQL** intact instead (T-SQL cursors do support a `SCROLL` option), as
`CURSOR LOCAL SCROLL`.

**Discussion.** Neither modifier changes the *value* a valid program
computes: a `CONSTANT` declaration still initializes the variable to the
same value, and dropping the reassignment guard only matters if the routine
tried to reassign it — code the source engine itself would already reject
as invalid. A dropped `SCROLL` only matters if the routine also performs a
non-`FETCH NEXT` fetch on that cursor, which is a **separate**,
already-documented limit in its own right (a scroll fetch has no
forward-only-engine equivalent regardless of whether the `DECLARE` kept the
modifier). Relaxing the modifier away is therefore safe for any program
that does not lean on the guard/scroll-fetch behavior specifically — which
is exactly the class of program these two targets could run in the first
place.

Even between Oracle and PostgreSQL, both of which share this grammar, a
cross-engine transpile currently relaxes `CONSTANT` the same way it does
onto T-SQL/MySQL — the modifier survives only when source and target are
the same dialect (a round-trip). `SCROLL` reaching PostgreSQL or T-SQL
follows the source engine that declared it: intact from a PostgreSQL
source, relaxed away from a T-SQL source.

> **Note** faithful — no warning: verified silent for a program that only
> reads the constant/only fetches forward, on every direction above.

**See Also.** [`test_constant_declare_pg`](../../../tests/integration/test_pg_source_wave1.py) (`TestDeclarationGrammarConsumesNewTokens`, same-dialect round-trip), [`test_scroll_cursor_tsql_native`](../../../tests/integration/test_pg_source_wave1.py) (PostgreSQL-source `SCROLL` reaching T-SQL) ·
[§1.5](../../03-unsupported.md).

---
