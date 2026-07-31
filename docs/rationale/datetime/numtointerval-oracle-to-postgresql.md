[← Date/time arithmetic and formatting](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=datetime type="Interval and temporal arithmetic" direction="oracle → postgresql" kind=article order=11 -->

# Oracle `NUMTODSINTERVAL` / `NUMTOYMINTERVAL` → PostgreSQL `INTERVAL`

**Problem.** Oracle's `NUMTODSINTERVAL(n, 'unit')` and
`NUMTOYMINTERVAL(n, 'unit')` build a standalone day-to-second or
year-to-month `INTERVAL` value from a number and a unit name
(`NUMTODSINTERVAL(-3, 'DAY')` is "an interval of minus three days").
PostgreSQL has no matching constructor function to rename the call to.

**Solution.**

```sql
-- tests/unit/core/procedural/test_numtointerval.py
CREATE OR REPLACE FUNCTION f RETURN DATE AS
BEGIN
    RETURN SYSDATE + NUMTODSINTERVAL(-3, 'DAY');
END;
-- oracle -> postgresql:
CREATE OR REPLACE FUNCTION f()
RETURNS TIMESTAMP
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN CURRENT_TIMESTAMP + INTERVAL '-3 DAY';
END;
$$;
```

The call is rebuilt as PostgreSQL's own interval-literal arithmetic: a
literal count folds directly into `INTERVAL '<n> <unit>'`
(`NUMTOYMINTERVAL(2, 'MONTH')` → `INTERVAL '2 MONTH'`); a variable count
becomes `n * INTERVAL '1 <unit>'` (`NUMTODSINTERVAL(v_n, 'MINUTE')` →
`v_n * INTERVAL '1 MINUTE'`). The rewrite applies wherever the call can
appear — a `RETURN` expression, an assignment right-hand side, or inside
embedded DML (an `UPDATE ... WHERE` predicate) — not just at the top level
of an expression.

**Discussion.** `NUMTODSINTERVAL`/`NUMTOYMINTERVAL` package a number and a
unit name into an interval value in one call; PostgreSQL instead spells an
interval as a typed literal (`INTERVAL '1 DAY'`) that supports ordinary
multiplication by a number. `n * INTERVAL '1 <unit>'` reproduces exactly
the same interval value for any `n`, and folding a literal `n` directly
into the interval string (`INTERVAL '<n> <unit>'`) avoids an unnecessary
multiplication when the count is already known at transpile time.

> **Note** faithful — live-verified on PostgreSQL: the rebuilt
> `CURRENT_TIMESTAMP + INTERVAL '-3 DAY'` evaluates to the same
> three-days-earlier timestamp `SYSDATE + NUMTODSINTERVAL(-3, 'DAY')`
> produces on Oracle.

**See Also.** [`TestNumToIntervalToPostgres`](../../../tests/unit/core/procedural/test_numtointerval.py) ·
[Multi-field PostgreSQL INTERVAL decomposition](postgresql-interval-decomposition.md),
the reverse-direction sibling (a PostgreSQL interval *value* decomposed for
a target with no interval type, rather than an Oracle interval
*constructor* rebuilt as a PostgreSQL interval literal).
