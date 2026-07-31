[← Aggregates and window functions](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=aggregates-windows type="Math functions with no shared spelling" direction="cross-engine" kind=article order=16 direction-inferred=true -->

# Math functions with no shared spelling: `LOG` argument order, `COT`, `PI()`, `TRUNC(x, n)`

**Problem.** Several ordinary scalar math functions differ across engines
in ways a rename table alone can't bridge — an argument order flip, a
missing function entirely, or a same-name function with different
rounding behavior.

**Solution.**

`LOG(base, x)` is the canonical two-argument form everywhere except T-SQL,
which spells the same call with its arguments swapped, `LOG(x, base)`:

```sql
-- tests/integration/test_log_arg_order.py
SELECT LOG(2, 8) AS r   -- log base 2 of 8
-- postgresql/mysql/oracle -> tsql:
SELECT LOG(8, 2) AS r
```

Oracle has no `COT` (cotangent); it's rebuilt as `1 / TAN(x)`:

```sql
-- corpus case ts-trig
SELECT COT(1) AS r
-- tsql -> oracle:
SELECT (1 / TAN(1)) AS r FROM DUAL;
```

Neither Oracle nor T-SQL has a niladic `PI()`; Oracle's is rebuilt as
`ACOS(-1)` (the standard identity), while T-SQL keeps its own `PI()`
untouched since it has one natively:

```sql
-- tsql -> oracle:
SELECT ACOS(-1) AS r FROM DUAL;
```

PostgreSQL/MySQL's `TRUNC(x, n)` truncates toward zero at `n` decimal
places; T-SQL's `ROUND` needs an explicit third argument (`1`) to switch
from rounding to truncating at the same precision — a bare `ROUND(x, n)`
would round instead:

```sql
-- postgresql -> tsql:
SELECT TRUNC(1.256, 2) AS r
-- =>
SELECT ROUND(1.256, 2, 1) AS r
```

**Discussion.** Each of these is an independent per-function gap in one
target's built-in catalog, not a single shared mechanism — they're grouped
here because none is large enough to warrant its own page, and all four
are plain, warning-free scalar-function rewrites in the same family as
this page's other numeric-semantics entries. `LOG`'s swap is purely
positional (both arguments keep their own value, just trade places); `COT`
and `PI()` are rebuilt from Oracle's own trigonometric primitives, which it
does have; `TRUNC(x, n)` reuses T-SQL's own `ROUND`, since T-SQL has no
separate truncating function, only a mode flag on the rounding one.

> **Note** faithful — each rewrite produces the identical numeric result;
> live-verified `LOG(8, 2) = 3`, `1 / TAN(1)` matches Oracle's own `COT(1)`,
> `ACOS(-1) = π`, and `ROUND(1.256, 2, 1) = 1.25` (truncated, not rounded to
> `1.26`). No warning for any of the four.

**See Also.** [`test_log_arg_order.py`](../../../tests/integration/test_log_arg_order.py) ·
Corpus [`ts-trig`](../../../tests/fixtures/challenge/challenge_sqlserver.sql),
[`pg-pi-fns`](../../../tests/fixtures/challenge/challenge_postgresql.sql) ·
`test_challenge_assertions_sqlserver.py` (`ts-trig`), `test_challenge_assertions_postgresql.py` (`pg-pi-fns`).
