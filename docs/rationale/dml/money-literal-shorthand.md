[← DML: SELECT/INSERT/UPDATE/DELETE, joins, set operations, MERGE](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=dml type="Literal parsing recovery" direction="tsql → oracle/postgresql/mysql" kind=article order=27 -->

# T-SQL bare money literal (`$12.50`) → the numeric literal it means

**Problem.** T-SQL accepts a bare currency-prefixed literal like `$12.50`
or `$100` as a numeric constant, but the underlying parser mis-reads it as
a `table.column` reference instead — `$12.50` becomes
`Column(this=Literal(50), table=Identifier($12))`, a nonsense "column `50`
of table `$12`" — because the digits after the dot look like a member
access, not a decimal point. Left alone, that shape ships as a quoted
`"$12".50` identifier reference, invalid SQL on every target.

**Solution.**

```sql
-- tests/integration/test_challenge.py::TestMoneyLiteralMangle
SELECT $12.50 AS price;
-- tsql -> postgresql / oracle / mysql:
SELECT 12.50 AS price;
```

**Discussion.** Unique recognizes both shapes the mis-parse produces — the
dotted form (`$12.50`) and the whole-dollar form (`$100`, parsed as a bare
column named `$100`) — specifically on **T-SQL source**, and rebuilds the
intended numeric literal from their pieces rather than passing the bogus
`table.column` reference through. The same `table.column` shape is left
alone in two cases where it is *not* the money shorthand: a **quoted**
identifier (`"$12".50` / `[$12].[50]`) is already-invalid T-SQL on its own
terms (not this idiom), and the identical bare shape arriving from
**Oracle or MySQL source** — dialects with no money-literal syntax at
all — is flagged by source validation as invalid input instead of being
guessed at.

> **Note** faithful — the numeric value (`12.50`, `100`, ...) is identical
> on every target, and nothing is lost since the source literal carried no
> currency-specific behavior of its own (unlike PostgreSQL's typed
> `::money`, T-SQL's bare `$12.50` is just numeric literal syntax). No
> warning — there's nothing to warn about, since the rebuilt value is
> exact.

**See Also.** [`test_challenge.py::TestMoneyLiteralMangle`](../../../tests/integration/test_challenge.py) ·
[§3.24](../../03-unsupported.md), "T-SQL Money Literal Shorthand".
