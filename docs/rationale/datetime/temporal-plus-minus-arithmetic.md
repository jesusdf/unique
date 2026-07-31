[← Date/time arithmetic and formatting](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=datetime type="Interval and temporal arithmetic" direction="cross-engine" kind=article order=4 direction-inferred=true -->

# Temporal +/− arithmetic: date ± int, MySQL numeric coercion, timestamp − timestamp

**Problem.** PostgreSQL/Oracle `date_col + n` / `date_col - n` is day
arithmetic; T-SQL `datetime_col + n` likewise adds days.

**Solution.**

```sql
-- pg-date-minus-integer, postgresql → tsql / mysql
SELECT DATE '2020-03-01' - 7 AS d;
-- => tsql
SELECT DATEADD(DAY, -7, DATE '2020-03-01') AS d;
-- => mysql
SELECT DATE_SUB(DATE '2020-03-01', INTERVAL 7 DAY) AS d;
```

Both operators route to `DATE_ADD`/`DATE_SUB(…,
INTERVAL n DAY)` on MySQL and `DATEADD(DAY, ±n, …)` on T-SQL.

A MySQL-source `DATE_ADD`/`TIMESTAMPADD` reading a **bare ISO string**
literal is additionally qualified as an ANSI `DATE`/`TIMESTAMP` literal before
emission — PostgreSQL's interval arithmetic reads an unqualified string as an
*interval* ("invalid input syntax"), and Oracle rejects the implicit
string→date cast (`emit_functions.py:111-125`, `reda-ts-date-plus-int`).

For `timestamp − timestamp`, PostgreSQL/Oracle produce an `INTERVAL` value
(e.g. `'02:00:00'`); T-SQL and MySQL have no interval *value* type to hold
it, so the subtraction degrades to a `DATEDIFF_BIG`/`TIMESTAMPDIFF(SECOND,
…)` second-count scalar with a carrier + warning — a different value shape
(scalar seconds, not an interval), never a silent wrong answer. A plain
`date − date` (a day count) translates exactly with no degrade.

**Discussion.** MySQL has no implicit date-plus-integer
operator: it *numerically coerces* the date to its `YYYYMMDD` integer form
and adds there, producing garbage (`DATE '2020-03-01' - 7` would need to
become `20200301 - 7 = 20200294`, not `2020-02-23`). PostgreSQL's own
`TIMESTAMP`/`DATE - int` is valid, but T-SQL rejects `date - int` outright
(error 206, "date is incompatible with int"). The `+` and `-` paths are
independent emitter branches, so a fix for one does not imply the other —
`pg-date-minus-integer` documents exactly this asymmetry (the `+` path was
already handled; `-` was not).

> **Note** faithful for date±int (live-verified
> `2020-02-23` on all targets, `pg-date-minus-integer`; `2020-01-02` on
> mysql/postgresql, `reda-ts-date-plus-int`). The `timestamp − timestamp`
> second-count case is a **documented, warned** shape change (interval → scalar
> seconds), not silent.

**See Also.** Corpus [`pg-date-minus-integer`](../../../tests/fixtures/challenge/challenge_postgresql.sql), [`reda-ts-date-plus-int`](../../../tests/fixtures/challenge/challenge_sqlserver.sql) ·
[§2](../../03-unsupported.md) ("`timestamp - timestamp` → T-SQL/MySQL") ·
`emit_functions.py:96-176` (docstring).

---
