[← All rationale topics](../README.md)

# Date/time arithmetic and formatting

Why Unique emits what it emits for date/time constructs with no direct
cross-engine equivalent. See [README.md](../README.md) for how this page is
built and its entry format.

> **Generated file — do not edit by hand.** Produced by `python scripts/generate_rationale_index.py` from the article pages in this directory; the intro above comes from `_intro.md`. The CI freshness gate (`python scripts/generate_rationale_index.py --check`) fails the build if it drifts.

## Month arithmetic and month-end semantics

| Article | Direction | Description |
|---|---|---|
| [DATEADD(MONTH) (T-SQL/MySQL/PostgreSQL) → Oracle ADD_MONTHS](dateadd-month-to-oracle-add-months.md) | tsql/postgresql/mysql → oracle | T-SQL `DATEADD(MONTH, n, d)`, MySQL `DATE_ADD(d, INTERVAL n MONTH)` and PostgreSQL `d + n * INTERVAL '1 month'` all *keep the day-of-month* and clamp down only when the target month is shorter: `DATEADD(MONTH, 1, '2020-02-29')` = `2020-03-29` (not `2020-03-31`). |
| [ADD_MONTHS (Oracle) → DATEADD/DATE_ADD/interval-add (T-SQL/MySQL/PostgreSQL)](oracle-add-months-to-dateadd.md) | oracle → tsql/postgresql/mysql | Oracle's `ADD_MONTHS` sticks to the *target* month's last day whenever the operand is its own month's last day — `ADD_MONTHS('2020-02-29', 1)` = `2020-03-31`. |
| [MySQL TIMESTAMPDIFF complete-month adjustment, ported to every target](mysql-timestampdiff-complete-month.md) | mysql → all | MySQL `TIMESTAMPDIFF(MONTH, start, end)` counts **complete** month periods: `TIMESTAMPDIFF(MONTH, '2020-01-15', '2020-03-10')` = `1`, not `2`, because the end's day-of-month (`10`) has not reached the start's (`15`) — the final partial month does not count. |
| [Oracle `MONTHS_BETWEEN` fractional value → T-SQL exact `CASE` formula](months-between-fractional.md) | oracle → tsql | Oracle's `MONTHS_BETWEEN(date1, date2)` returns a **fractional** number of months: whole months plus `(day1 - day2) / 31` for the remainder, collapsing to a whole number only when both dates are the last day of their month or share the same day-of-month. |

## Truncation and unit maps

| Article | Direction | Description |
|---|---|---|
| [PostgreSQL date_trunc → Oracle TRUNC format codes and T-SQL ISO week](date-trunc-to-oracle-trunc.md) | postgresql → tsql/oracle | PostgreSQL `date_trunc('week', ts)` truncates to the start of the ISO week — **Monday** — and `date_trunc('quarter', ts)` to the first day of the quarter. |
| [DATEDIFF/DATEPART unit maps: the QUARTER crash and WEEKDAY per-target forms](datediff-datepart-unit-maps.md) | cross-engine | T-SQL `DATEDIFF(QUARTER, d1, d2)` and `DATEDIFF(WEEK, d1, d2)` are valid, translatable unit spellings; `DATEPART(WEEKDAY, d)` returns the day-of-week under the session's `@@DATEFIRST` setting (default: Sunday = 1). |

## Interval and temporal arithmetic

| Article | Direction | Description |
|---|---|---|
| [Temporal +/− arithmetic: date ± int, MySQL numeric coercion, timestamp − timestamp](temporal-plus-minus-arithmetic.md) | cross-engine | PostgreSQL/Oracle `date_col + n` / `date_col - n` is day arithmetic; T-SQL `datetime_col + n` likewise adds days. |
| [Multi-field PostgreSQL INTERVAL decomposition](postgresql-interval-decomposition.md) | postgresql → all | PostgreSQL accepts a verbose, multi-unit interval literal in one string: `INTERVAL '1 year 2 months 3 days'`. |
| [Oracle `NUMTODSINTERVAL` / `NUMTOYMINTERVAL` → PostgreSQL `INTERVAL`](numtointerval-oracle-to-postgresql.md) | oracle → postgresql | Oracle's `NUMTODSINTERVAL(n, 'unit')` and `NUMTOYMINTERVAL(n, 'unit')` build a standalone day-to-second or year-to-month `INTERVAL` value from a number and a unit name (`NUMTODSINTERVAL(-3, 'DAY')` is "an interval of minus three days"). |

## Epoch rebasing

| Article | Direction | Description |
|---|---|---|
| [MySQL TO_DAYS year-0000 epoch rebase](mysql-to-days-epoch-rebase.md) | mysql → all | MySQL `TO_DAYS(d)` returns the count of days since a notional `0000-01-01`. |

## Compound EXTRACT units

| Article | Direction | Description |
|---|---|---|
| [MySQL compound `EXTRACT` units (`YEAR_MONTH`, `DAY_HOUR`, …) → all targets](mysql-compound-extract-units.md) | mysql → all | MySQL's `EXTRACT` accepts several **compound** units — `YEAR_MONTH`, `DAY_HOUR`, `DAY_MINUTE`, `DAY_SECOND`, and others — that pack two or more calendar fields into a single decimal-weighted number in one call. |

## Schema-harvested ANSI date/timestamp literal wrapping

| Article | Direction | Description |
|---|---|---|
| [An ISO date/timestamp string written into a harvested `DATE`/`DATETIME` column → wrapped in an Oracle ANSI literal](schema-harvested-date-literal-to-oracle.md) | tsql → oracle | `INSERT INTO evt (d, ts) VALUES ('2024-01-15', '2024-01-15 10:30:00')` relies on the target column's own declared type (`DATE`/`DATETIME`) to interpret a plain ISO string as a date or timestamp — T-SQL, PostgreSQL, and MySQL all accept this implicit string-to-date coercion. |

## DATE typing propagated through a derived table

| Article | Direction | Description |
|---|---|---|
| [An Oracle `DATE` literal inside a derived-table projection → its typing survives to the outer column reference](date-typing-propagated-through-derived-table.md) | oracle → tsql/mysql/postgresql | `SELECT ShipDate - OrderDate FROM (SELECT DATE '2020-01-10' ShipDate, DATE '2020-01-01' OrderDate FROM DUAL) x` computes a day count on Oracle, since `DATE - DATE` is arithmetic there. |

## CONVERT(type, value, style) numeric style codes

| Article | Direction | Description |
|---|---|---|
| [T-SQL `CONVERT(type, value, style)`'s numeric style code → a per-target format function, or ignored when the target type isn't a date](convert-style-code-per-target.md) | tsql → postgresql/mysql/oracle | T-SQL's `CONVERT` takes an optional third argument, a numeric *style* code, whose meaning depends entirely on what the second argument is being converted to: against a date/time type, it selects a date format (`120` = ISO `yyyy-mm-dd hh:mi:ss`, `103` = British/French `dd/mm/yyyy`, ...); against a non-date type, the style code is only meaningful for a handful of special cases (binary-to-string encodings) and is otherwise ignored. |
