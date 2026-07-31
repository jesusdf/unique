[← Date/time arithmetic and formatting](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=datetime type="Interval and temporal arithmetic" direction="postgresql → all" kind=article order=7 direction-inferred=true -->

# Multi-field PostgreSQL INTERVAL decomposition

**Problem.** PostgreSQL accepts a verbose, multi-unit interval
literal in one string: `INTERVAL '1 year 2 months 3 days'`.

**Solution.**

```sql
-- pg-multifield-interval-arith, postgresql → tsql
SELECT TIMESTAMP '2020-01-01 00:00:00' + INTERVAL '1 year 2 months 3 days' AS d;
-- =>
SELECT DATEADD(DAY, 3, DATEADD(MONTH, 2, DATEADD(YEAR, 1, CAST('2020-01-01 00:00:00' AS DATETIME2)))) AS d;
```

`_decompose_interval` (`emit_expr.py:1133`) parses the
verbose form (and the ANSI `YEAR TO MONTH`/`DAY TO SECOND` span forms) into
ordered `(count, UNIT)` components, and `_emit_interval_chain`
(`emit_expr.py:1173`) spells `date ± <interval>` as a chain of per-target
adds: nested `DATEADD` calls on T-SQL, successive `± INTERVAL n UNIT` terms
on MySQL (unquoted count) and Oracle/PostgreSQL (quoted count).

On MySQL/Oracle the same source chains `+ INTERVAL 1 YEAR + INTERVAL 2 MONTH
+ INTERVAL 3 DAY` (MySQL) / `+ INTERVAL '1' YEAR + INTERVAL '2' MONTH +
INTERVAL '3' DAY` (Oracle).

**Discussion.** No other engine's interval literal
accepts PostgreSQL's free-text multi-field spelling: T-SQL has no interval
literal at all, MySQL's `INTERVAL` syntax takes exactly one `n UNIT` pair per
addition, and Oracle's ANSI interval literals need an explicit
`YEAR TO MONTH`/`DAY TO SECOND` qualifier with a different internal
delimiter. Before this was handled, the literal was emitted **verbatim** into
date arithmetic on every non-PostgreSQL target and rejected outright
(`pg-multifield-interval-arith` — a single-unit interval like `INTERVAL '1
month'` already converted correctly; only the multi-field form slipped
through invalid, with no warning).

> **Note** faithful — chained single-unit adds are
> associative and produce the same result date (`2021-03-04`) as PostgreSQL's
> one-shot multi-field add. No warning.

**See Also.** Corpus [`pg-multifield-interval-arith`](../../../tests/fixtures/challenge/challenge_postgresql.sql) ·
`emit_expr.py::_decompose_interval`, `emit_expr.py::_emit_interval_chain`.

---
