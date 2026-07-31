[← Aggregates and window functions](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=aggregates-windows type="Numeric division, cast rounding, and zero-divisor semantics" direction="tsql → postgresql/oracle/mysql" kind=article order=17 -->

# T-SQL `CAST(... AS <integer type>)` truncates; a fractional literal folds, and `AVG(int)` gets a `TRUNC` wrap going the other way

**Problem.** This is the reverse of [`CAST(... AS <integer type>)`
rounding vs. truncation trade](cast-to-integer-rounding.md): T-SQL's own
cast to an integer type always truncates toward zero (`CAST(2.9 AS INT)` =
`2`), while PostgreSQL, Oracle, and MySQL's `SIGNED` cast all round
half-away-from-zero (`CAST(2.9 AS INT)` would be `3` on those). A verbatim
`2.9` reaching a rounding target's cast would silently compute the wrong
truncated value.

**Solution.** A fractional *literal* is folded to its already-truncated
value before the cast, rather than trusting the target's own (rounding)
cast behavior:

```sql
-- corpus cases reda-ts-cast-int-trunc, reda-ts-avg-int-trunc
SELECT CAST(2.9 AS INT) AS r
-- tsql -> postgresql / oracle:
SELECT CAST(2 AS INT) AS r;
-- tsql -> mysql:
SELECT CAST(2 AS SIGNED) AS r;
```

T-SQL's `AVG` over an integer column truncates before dividing (`AVG(1,
2)` = `1`, not `1.5`); on the other three engines, which always average as
decimal, the whole `AVG(...)` call is wrapped in a truncating function to
reproduce the same integer-averaging result:

```sql
SELECT AVG(x) FROM (SELECT 1 x UNION SELECT 2) t
-- tsql -> postgresql / oracle:
SELECT TRUNC(AVG(x)) FROM (SELECT 1 AS x UNION SELECT 2) t;
-- tsql -> mysql:
SELECT TRUNCATE(AVG(x), 0) FROM (SELECT 1 AS x UNION SELECT 2) t;
```

**Discussion.** Both compensations exist because T-SQL is the one engine
in this quartet whose integer-cast and integer-averaging both truncate
rather than round or promote to decimal — a mirror image of [the
`postgresql`/`mysql` → `tsql` direction](cast-to-integer-rounding.md),
which instead wraps the target's truncating cast in `ROUND(x, 0)` to
compensate the other way. Folding a *literal* cast argument at translation
time (rather than emitting a runtime truncation function around it) keeps
the output simple whenever the value is already known; `AVG`, whose
argument is a column rather than a literal, needs the runtime `TRUNC`/
`TRUNCATE` wrap instead, since the actual averaged value isn't known until
query time.

> **Note** faithful — live-verified `CAST(2.9 AS INT)` folds to the same
> `2` truncation T-SQL itself would have produced, and `TRUNC(AVG(x))` /
> `TRUNCATE(AVG(x), 0)` reproduce T-SQL's own `AVG(1, 2) = 1`, not the
> other engines' native `1.5`. No warning.

**See Also.** Corpus [`reda-ts-cast-int-trunc`](../../../tests/fixtures/challenge/challenge_sqlserver.sql), [`reda-ts-avg-int-trunc`](../../../tests/fixtures/challenge/challenge_sqlserver.sql) ·
`test_challenge_assertions_sqlserver.py` (`reda-ts-cast-int-trunc`, `reda-ts-avg-int-trunc`) ·
[`CAST(... AS <integer type>)` rounding vs. truncation trade](cast-to-integer-rounding.md)
(the forward direction this mirrors).
