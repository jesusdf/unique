[← Date/time arithmetic and formatting](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=datetime type="Truncation and unit maps" direction="cross-engine" kind=article order=16 -->

# `EXTRACT(field FROM x)` ↔ T-SQL `DATEPART(field, x)` for the standard fields

**Problem.** Oracle, PostgreSQL and MySQL spell a date-field extraction as
`EXTRACT(field FROM x)` (a special two-token syntax, not an ordinary
function call); T-SQL has no `EXTRACT` at all and instead uses
`DATEPART(field, x)` — an ordinary comma-separated function call. Neither
form is valid on the other family of engines: `EXTRACT(YEAR, x)` (the
comma form) is rejected by Oracle/PostgreSQL/MySQL, and a bare `EXTRACT`
reaching T-SQL is an unresolved-function error.

**Solution.**

```sql
-- tests/integration/test_oracle_source_m4_wave.py::TestOracleScalarsOnTsqlWave16::test_extract_standalone_becomes_datepart
UPDATE t SET a = EXTRACT(YEAR FROM d);
-- oracle/postgresql/mysql -> tsql:
UPDATE t SET a = DATEPART(YEAR, d)

-- tsql -> oracle/postgresql/mysql:
SELECT DATEPART(YEAR, d) FROM t
-- =>
SELECT EXTRACT(YEAR FROM d) FROM t;
```

**Discussion.** For the common fields both sides already agree on —
`YEAR`, `MONTH`, `DAY`, `HOUR`, `MINUTE`, `SECOND` — the two spellings
name the identical value; only the calling convention differs (a
`FROM`-separated pseudo-function vs. a comma-separated one), so the
conversion is a direct syntactic respelling in both directions. This
closed a real leak: a bare `EXTRACT(...)` reaching a T-SQL target used to
ship as an unresolved built-in (error 195) instead of `DATEPART`. Date
parts outside this common set — `WEEKDAY`, `QUARTER`, `ISO_WEEK` and
similar — need their own per-target reconstruction instead of a plain
respelling; see
[the DATEDIFF/DATEPART unit-map article](datediff-datepart-unit-maps.md)
for those.

> **Note** faithful — the extracted field value is identical on every
> engine for the standard calendar fields. No warning.

**See Also.** [`test_oracle_source_m4_wave.py::TestOracleScalarsOnTsqlWave16`](../../../tests/integration/test_oracle_source_m4_wave.py)
· [§3.12](../../03-unsupported.md), "IIF and DATEPART" ·
[DATEDIFF/DATEPART unit maps: the QUARTER crash and WEEKDAY per-target forms](datediff-datepart-unit-maps.md)
(the non-standard fields that need reconstruction instead) ·
[T-SQL `IIF`/MySQL `IF` → searched `CASE`](../dml/iif-to-case-or-native.md)
(the other half of the same 03-unsupported.md section).
