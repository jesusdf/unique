# Date/time arithmetic and formatting

Why Unique emits what it emits for date/time constructs with no direct
cross-engine equivalent. See [README.md](README.md) for how this page is
built and its entry format.

### DATEADD(MONTH) (T-SQL/MySQL/PostgreSQL) → Oracle ADD_MONTHS

**Problem.** T-SQL `DATEADD(MONTH, n, d)`, MySQL `DATE_ADD(d,
INTERVAL n MONTH)` and PostgreSQL `d + n * INTERVAL '1 month'` all *keep the
day-of-month* and clamp down only when the target month is shorter:
`DATEADD(MONTH, 1, '2020-02-29')` = `2020-03-29` (not `2020-03-31`).

**Solution.**

```sql
-- reda-ts-addmonths-lastday, tsql → oracle
SELECT DATEADD(MONTH, 1, CAST('2020-02-29' AS DATE)) AS d;
-- =>
SELECT ADD_MONTHS(DATE '2020-02-29', 1)
  - (EXTRACT(DAY FROM ADD_MONTHS(DATE '2020-02-29', 1))
     - LEAST(EXTRACT(DAY FROM DATE '2020-02-29'),
             EXTRACT(DAY FROM LAST_DAY(ADD_MONTHS(DATE '2020-02-29', 1)))))
  AS d
FROM DUAL;
```

The Oracle month/quarter/year path
(`oracle_month_add_daypreserving`, `src/unique/core/mappings.py:1164`)
subtracts the extra days `ADD_MONTHS` stepped past, computed with
`LEAST(day, target-month-length)` so the operand's time-of-day is preserved
(a subtractive fix-up rather than rebuilding from `TRUNC`-to-first-of-month).

**Discussion.** Oracle's `ADD_MONTHS` has a different,
stickier rule: when the operand *is* its own month's last day, the result is
forced to the *target* month's last day too — `ADD_MONTHS('2020-02-29', 1)` =
`2020-03-31`. A bare `ADD_MONTHS` call therefore silently overshoots by the
extra days it stuck past the source's day-of-month (corpus
`reda-ts-addmonths-lastday`).

> **Note** faithful — live-verified `2020-03-29` on all four
> engines (also mid-month, day-31-into-a-30-day-month, leap year, quarter and
> subtraction variants; corpus header). No warning; the compensation is applied
> unconditionally since a column operand may hold a month-end date at runtime.
> The reverse direction (Oracle `ADD_MONTHS` as source) is **not** a bare
> copy either — see the sibling entry below: a target's plain
> `DATEADD`/interval-add is day-preserving, not sticky, so it needs its own
> `CASE WHEN` compensation to reproduce Oracle's stickier rule.

**See Also.** Corpus [`reda-ts-addmonths-lastday`](../../tests/fixtures/challenge/challenge_sqlserver.sql), [`ora-add-months`](../../tests/fixtures/challenge/challenge_oracle.sql) ·
[`oracle_month_add_daypreserving`](../../src/unique/core/mappings.py) (docstring).

---

### ADD_MONTHS (Oracle) → DATEADD/DATE_ADD/interval-add (T-SQL/MySQL/PostgreSQL)

**Problem.** Oracle's `ADD_MONTHS` sticks to the *target* month's last day
whenever the operand is its own month's last day —
`ADD_MONTHS('2020-02-29', 1)` = `2020-03-31`. T-SQL's `DATEADD(MONTH, n,
d)`, MySQL's `DATE_ADD(d, INTERVAL n MONTH)`, and PostgreSQL's `d + n *
INTERVAL '1 month'` are all *day-preserving* instead, clamping only when the
target month is too short: `DATEADD(MONTH, 1, '2020-02-29')` = `2020-03-29`,
not `2020-03-31`. A verbatim copy of the arithmetic reproduces the wrong
rule — this is the reverse of the entry above, and needs the same kind of
compensation in the opposite direction.

**Solution.**

```sql
-- oracle -> mysql / tsql / postgresql
SELECT ADD_MONTHS(d, 1) AS r FROM t;
-- => mysql
SELECT CASE WHEN d = LAST_DAY(d) THEN LAST_DAY(DATE_ADD(d, INTERVAL 1 MONTH)) ELSE DATE_ADD(d, INTERVAL 1 MONTH) END AS r
FROM t;
-- => tsql
SELECT CASE WHEN d = EOMONTH(d) THEN EOMONTH(DATEADD(MONTH, 1, d)) ELSE DATEADD(MONTH, 1, d) END AS r
FROM t
-- => postgresql
SELECT CASE WHEN d = CAST(DATE_TRUNC('month', d) + INTERVAL '1 month' - INTERVAL '1 day' AS DATE)
       THEN CAST(DATE_TRUNC('month', (d + 1 * INTERVAL '1 month')) + INTERVAL '1 month' - INTERVAL '1 day' AS DATE)
       ELSE CAST((d + 1 * INTERVAL '1 month') AS DATE) END AS r
FROM t;
```

A literal ISO date operand into PostgreSQL additionally needs an explicit
`DATE '…'` type: PostgreSQL's `DATE_TRUNC` has no unique overload for an
untyped string (`"date_trunc(unknown, unknown) is not unique"`), so the
literal is wrapped before the rewrite runs; a column operand is left
untyped, since it is already typed
(`tests/integration/test_challenge.py::TestOracleAddMonthsPgTypedLiteral`):

```sql
-- oracle -> postgresql
SELECT ADD_MONTHS(DATE '2020-01-31', 1) AS r;
-- =>
SELECT CASE WHEN DATE '2020-01-31' = CAST(DATE_TRUNC('month', DATE '2020-01-31') + INTERVAL '1 month' - INTERVAL '1 day' AS DATE)
       THEN CAST(DATE_TRUNC('month', (DATE '2020-01-31' + 1 * INTERVAL '1 month')) + INTERVAL '1 month' - INTERVAL '1 day' AS DATE)
       ELSE CAST((DATE '2020-01-31' + 1 * INTERVAL '1 month') AS DATE) END AS r;
```

Each target's own last-day primitive (`LAST_DAY` on MySQL, `EOMONTH` on
T-SQL, the `DATE_TRUNC('month', …) + INTERVAL '1 month' - INTERVAL '1 day'`
build on PostgreSQL) is used both to test "is the operand its own month's
last day" and to compute the sticky result — a `CASE WHEN` of the same
shape as the forward direction above, mirrored.

**Discussion.** Only Oracle's date arithmetic sticks to the last day; every
other engine's month-add is a pure day-preserving offset. Reproducing
Oracle's rule on a target that lacks it natively requires testing the
operand against its own month's last day and branching — no single
expression encodes "day-preserving, except when the operand started on a
month boundary" directly.

> **Note** faithful — same mechanism and code path
> (`src/unique/core/converter/emit_functions.py`'s `ADD_MONTHS`,
> `dialect != "oracle"` branch) as the forward direction. Pinned by
> `test_add_months_preserves_sticky_last_day` (all three non-Oracle targets
> get the `CASE WHEN` wrap with each target's own last-day marker) and the
> PG-typed-literal case above. No warning.

**See Also.** [`test_add_months_preserves_sticky_last_day`](../../tests/integration/test_rc1a_mappings.py), [`TestOracleAddMonthsPgTypedLiteral`](../../tests/integration/test_challenge.py) ·
`src/unique/core/converter/emit_functions.py` (`ADD_MONTHS` branch, docstring) ·
Corpus [`ora-add-months`](../../tests/fixtures/challenge/challenge_oracle.sql).

---

### PostgreSQL date_trunc → Oracle TRUNC format codes and T-SQL ISO week

**Problem.** PostgreSQL `date_trunc('week', ts)` truncates to the
start of the ISO week — **Monday** — and `date_trunc('quarter', ts)` to the
first day of the quarter. Oracle's own `TRUNC(date, fmt)` and T-SQL's
`DATETRUNC` (2022+) spell the same units differently.

**Solution.**

```sql
-- pg-date-trunc-week, postgresql → oracle / tsql
SELECT date_trunc('week', DATE '2020-06-17') AS d;
-- => oracle
SELECT TRUNC(DATE '2020-06-17', 'IW') AS d FROM DUAL;
-- => tsql
SELECT DATETRUNC(ISO_WEEK, CAST('2020-06-17' AS DATE)) AS d;
```

A source-unit → target-format table
(`emit_functions.py:2352`) maps each PostgreSQL/Oracle `DATE_TRUNC` unit to
Oracle's valid `TRUNC` code — `'week'` → `'IW'` (the ISO, Monday-based week,
matching PostgreSQL) — and to T-SQL's `DATETRUNC` part, substituting
`ISO_WEEK` for `week` so the Sunday/Monday mismatch does not leak through.

The same source-unit table backs `EXTRACT(WEEK|QUARTER FROM …)` /
`DATE_PART`: Oracle's `EXTRACT` rejects both `WEEK` and `QUARTER`, so they
route through `TO_CHAR(d, 'IW'|'Q')` instead; MySQL's native
`EXTRACT(WEEK)` follows the DBMS's `default_week_format` (off by one from
ISO) and T-SQL's `DATEPART(WEEK)` is `@@DATEFIRST`-dependent, so both are
overridden with an explicit ISO form (`WEEK(d, 3)` mode 3 = ISO 8601 /
`DATEPART(ISO_WEEK, d)`):

```sql
-- pg-date-part, postgresql → oracle / mysql / tsql
SELECT DATE_PART('week', DATE '2020-06-15'), DATE_PART('quarter', DATE '2020-06-15');
-- => oracle
SELECT TO_NUMBER(TO_CHAR(DATE '2020-06-15', 'IW')), TO_NUMBER(TO_CHAR(DATE '2020-06-15', 'Q')) FROM DUAL;
-- => mysql
SELECT WEEK(CAST('2020-06-15' AS DATE), 3), ...
-- => tsql
SELECT DATEPART(ISO_WEEK, CAST('2020-06-15' AS DATE)), ...
```

**Discussion.** Oracle's `TRUNC` format models are not
PostgreSQL's spelling: `TRUNC(d, 'WEEK')` raises `ORA-01898` (invalid format
model) and `TRUNC(d, 'QUARTER')`/`'MINUTE'` raise `ORA-01821`. T-SQL's
`DATETRUNC(week, …)` starts the week on **Sunday**, one day off PostgreSQL's
Monday-based ISO week, so a bare unit copy silently returns the wrong date
(`2020-06-14` instead of `2020-06-15` for `date_trunc('week', DATE
'2020-06-17')`).

> **Note** faithful — live-verified equal on all four
> engines, including the ISO year-boundary edge case (`pg-week-2016`:
> `2016-01-01` is ISO week 53 of 2015 on PostgreSQL/MySQL/T-SQL once forced to
> the ISO form). MySQL's `date_trunc('week', …)` equivalent (no native
> truncation unit) is built from `WEEKDAY()` instead (Monday=0) and is likewise
> faithful. No warning.

**See Also.** Corpus [`pg-date-trunc-week`](../../tests/fixtures/challenge/challenge_postgresql.sql), [`pg-date-part`](../../tests/fixtures/challenge/challenge_postgresql.sql), [`pg-week`](../../tests/fixtures/challenge/challenge_postgresql.sql),
[`pg-week-2016`](../../tests/fixtures/challenge/challenge_postgresql.sql) · [`TestExtractFieldTranslation`](../../tests/integration/test_challenge.py)
(pinned) · `emit_functions.py:2338-2419` (docstring, "Date truncation").

---

### Temporal +/− arithmetic: date ± int, MySQL numeric coercion, timestamp − timestamp

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

**See Also.** Corpus [`pg-date-minus-integer`](../../tests/fixtures/challenge/challenge_postgresql.sql), [`reda-ts-date-plus-int`](../../tests/fixtures/challenge/challenge_sqlserver.sql) ·
[§2](../03-unsupported.md) ("`timestamp - timestamp` → T-SQL/MySQL") ·
`emit_functions.py:96-176` (docstring).

---

### MySQL TIMESTAMPDIFF complete-month adjustment, ported to every target

**Problem.** MySQL `TIMESTAMPDIFF(MONTH, start, end)` counts
**complete** month periods: `TIMESTAMPDIFF(MONTH, '2020-01-15', '2020-03-10')`
= `1`, not `2`, because the end's day-of-month (`10`) has not reached the
start's (`15`) — the final partial month does not count.

**Solution.**

```sql
-- my-timestampdiff-mon, mysql → tsql
SELECT TIMESTAMPDIFF(MONTH, '2020-01-15', '2020-03-10') AS r;
-- =>
SELECT (DATEDIFF(MONTH, '2020-01-15', '2020-03-10')
        - CASE WHEN DATEADD(MONTH, DATEDIFF(MONTH, '2020-01-15', '2020-03-10'), '2020-01-15')
               > '2020-03-10' THEN 1 ELSE 0 END) AS r;

-- my-timestampdiff-mon-pgora, mysql → postgresql
SELECT TIMESTAMPDIFF(MONTH, '2020-01-31', '2020-03-30') AS r;
-- =>
SELECT (((EXTRACT(YEAR FROM DATE '2020-03-30') * 12 + EXTRACT(MONTH FROM DATE '2020-03-30'))
       - (EXTRACT(YEAR FROM DATE '2020-01-31') * 12 + EXTRACT(MONTH FROM DATE '2020-01-31')))
       - CASE WHEN DATE '2020-01-31' + (…) * INTERVAL '1 month' > DATE '2020-03-30'
              THEN 1 ELSE 0 END) AS r;
```

A shared helper (`_complete_period_adjust`,
`emit_functions.py:179`) drops the incomplete final period from any
year/quarter/month boundary count: it re-adds the boundary count as an
interval to `start` and subtracts 1 whenever that overshoots `end`.

**Discussion.** T-SQL `DATEDIFF(MONTH, …)`, and the
naïve `(year*12 + month)` boundary difference used for PostgreSQL/Oracle,
both count **calendar-boundary crossings**, not complete periods —
`DATEDIFF(MONTH, '2020-01-15', '2020-03-10')` = `2` (January→February,
February→March boundaries), overcounting by exactly the incomplete final
period. The gap was found and fixed once for the T-SQL target
(`my-timestampdiff-mon`), then found again on PostgreSQL/Oracle
(`my-timestampdiff-mon-pgora`) — the boundary-count rewrite used there had not
inherited the same adjustment.

> **Note** faithful — live-verified `1` (T-SQL) and the
> PG/Oracle case verified against MySQL's own `1` (was silently `2` before the
> fix). No warning; a plain `DATEDIFF`-sourced batch (T-SQL boundary counting,
> not MySQL complete-period counting) deliberately keeps the unadjusted
> boundary count.

**See Also.** Corpus [`my-timestampdiff-mon`](../../tests/fixtures/challenge/challenge_mysql.sql), [`my-timestampdiff-mon-pgora`](../../tests/fixtures/challenge/challenge_mysql.sql) ·
`emit_functions.py::_complete_period_adjust` (docstring) ·
`emit_functions.py::_emit_date_diff`.

---

### MySQL TO_DAYS year-0000 epoch rebase

**Problem.** MySQL `TO_DAYS(d)` returns the count of days since a
notional `0000-01-01`.

**Solution.**

```sql
-- my-to-days-year-zero, mysql → postgresql / tsql / oracle
SELECT TO_DAYS('2020-01-01') AS d;
-- =>
SELECT (CAST(DATE '2020-01-01' AS DATE) - CAST(DATE '1970-01-01' AS DATE)) + 719528 AS d;
```

`_rebase_to_days` (`convert.py:3271`) recognises the
`DATEDIFF(x, DATE '0000-01-01', DAY) + 1` shape and re-expresses it against
`1970-01-01` — a value every engine parses identically — offset by the known
constant `719528` (`TO_DAYS('1970-01-01')`).

**Discussion.** sqlglot lowers `TO_DAYS(d)` to
`DATEDIFF(d, DATE '0000-01-01', DAY) + 1`, but year `0000` is rejected by
every other engine — PostgreSQL raises `DatetimeFieldOverflow`, T-SQL raises
"Conversion failed" (241), and Oracle's `DATE` literal range is `-4713..9999`
(`ORA-01841`) and would in any case put the value on the Julian calendar for
pre-1582 dates, two days off the proleptic Gregorian count MySQL uses. This
produced a hard runtime error on every target with no warning
(`my-to-days-year-zero`).

> **Note** faithful — the rebase is an exact algebraic
> identity (day counts from any two fixed epochs differ by a constant), so the
> result matches MySQL's `TO_DAYS` for any post-Gregorian-reform date. No
> warning.

**See Also.** Corpus [`my-to-days-year-zero`](../../tests/fixtures/challenge/challenge_mysql.sql) ·
`convert.py::_rebase_to_days` (docstring).

---

### Multi-field PostgreSQL INTERVAL decomposition

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

**See Also.** Corpus [`pg-multifield-interval-arith`](../../tests/fixtures/challenge/challenge_postgresql.sql) ·
`emit_expr.py::_decompose_interval`, `emit_expr.py::_emit_interval_chain`.

---

### DATEDIFF/DATEPART unit maps: the QUARTER crash and WEEKDAY per-target forms

**Problem.** T-SQL `DATEDIFF(QUARTER, d1, d2)` and `DATEDIFF(WEEK,
d1, d2)` are valid, translatable unit spellings; `DATEPART(WEEKDAY, d)`
returns the day-of-week under the session's `@@DATEFIRST` setting (default:
Sunday = 1).

**Solution.**

```sql
-- reda-ts-datediff-quarter, tsql → mysql
SELECT DATEDIFF(QUARTER, CAST('2020-01-01' AS DATE), CAST('2020-12-31' AS DATE)) AS r;
-- =>
SELECT ((YEAR(CAST('2020-12-31' AS DATE)) * 4 + QUARTER(CAST('2020-12-31' AS DATE)))
      - (YEAR(CAST('2020-01-01' AS DATE)) * 4 + QUARTER(CAST('2020-01-01' AS DATE)))) AS r;
```

The `QUARTER`/`WEEK` gap was closed by extending
`_emit_date_diff`'s unit handling — `QUARTER` as a boundary count over
`(year*4 + quarter)`, `WEEK` as `FLOOR(day-count / 7)` — on every target.

`DATEPART(WEEKDAY, d)` now routes through the shared `_weekday_extract_expr`
helper (the same DATEFIRST-/NLS-independent rewrite as PostgreSQL's
`EXTRACT(DOW)`, computed from a known reference Sunday) and carries an
explicit caveat, since `@@DATEFIRST` is a **session** setting Unique cannot
observe at transpile time:

```sql
-- reda-ts-datepart-weekday, tsql → postgresql
SELECT DATEPART(WEEKDAY, CAST('2020-06-15' AS DATE)) AS r;
-- =>
SELECT (EXTRACT(DOW FROM CAST('2020-06-15' AS DATE)) + 1)
  /* UNIQUE: DATEPART(WEEKDAY) is @@DATEFIRST-dependent; converted assuming
     the session default (Sunday=1) */ AS r;
```

MySQL emits `DAYOFWEEK(d)` directly (already Sunday=1) and Oracle computes it
via `MOD` arithmetic over a known reference Sunday (`1970-01-04`) — both
DATEFIRST-independent.

**Discussion.** *Why there is no direct mapping (QUARTER/WEEK).* This was not
an inherent engine gap but an implementation hole: `_emit_date_diff`'s
per-target second/minute/hour lookup (`{"HOUR": 3600, "MINUTE": 60, "SECOND":
1}[unit]`) only covered those three units. A `QUARTER` or `WEEK` unit raised
an uncaught Python `KeyError`, which the transpile catch-all swallowed and
surfaced as a `/* TRANSPILATION ERROR: QUARTER */` carrier shipping the raw,
untranslated T-SQL `DATEDIFF` — invalid on MySQL/Oracle
(`reda-ts-datediff-quarter`, class `crash`). `DATEADD(QUARTER)`/`DATEADD(WEEK)`
already worked; only `DATEDIFF`'s unit table was incomplete.

*Why there is no direct mapping (WEEKDAY).* No target's `EXTRACT`/`DATEPART`
has a `DAYOFWEEK` field under that name — mapping it there raised a live
error on all three (PostgreSQL "unit dayofweek not recognized", MySQL 1064,
Oracle `ORA-00907`) with no warning (`reda-ts-datepart-weekday`, class
`invalid`).

> **Note** faithful (QUARTER/WEEK — no crash, no carrier,
> same boundary-count value). **Warned** for WEEKDAY: the emitted value
> assumes the T-SQL default `@@DATEFIRST = 7` (week starts Sunday); a session
> that has changed `DATEFIRST` will see a different T-SQL result the transpiled
> output cannot track, since Unique has no visibility into session state.

**See Also.** Corpus [`reda-ts-datediff-quarter`](../../tests/fixtures/challenge/challenge_sqlserver.sql), [`reda-ts-datepart-weekday`](../../tests/fixtures/challenge/challenge_sqlserver.sql),
[`pg-extract-dow`](../../tests/fixtures/challenge/challenge_postgresql.sql) ·
[`TestExtractFieldTranslation`](../../tests/integration/test_challenge.py) (pinned) ·
`emit_functions.py::_emit_date_diff`, `emit_functions.py::_weekday_extract_expr`
· [`UNIQUE-1083`](../reference/warnings.md#unique-1083).
