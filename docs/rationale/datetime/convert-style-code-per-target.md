[← Date/time arithmetic and formatting](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=datetime type="CONVERT(type, value, style) numeric style codes" direction="tsql → postgresql/mysql/oracle" kind=article order=13 -->

# T-SQL `CONVERT(type, value, style)`'s numeric style code → a per-target format function, or ignored when the target type isn't a date

**Problem.** T-SQL's `CONVERT` takes an optional third argument, a numeric
*style* code, whose meaning depends entirely on what the second argument
is being converted to: against a date/time type, it selects a date format
(`120` = ISO `yyyy-mm-dd hh:mi:ss`, `103` = British/French `dd/mm/yyyy`,
...); against a non-date type, the style code is only meaningful for a
handful of special cases (binary-to-string encodings) and is otherwise
ignored. No other engine's `CONVERT`/`CAST` has a matching style-code
argument at all.

**Solution.** Against a date/time target type, the style code picks each
target's own format function and mask:

```sql
-- tests/integration/test_cross_dialect.py::TestConvertStyle
SELECT CONVERT(VARCHAR, d, 120) FROM t
-- tsql -> postgresql: SELECT TO_CHAR(d, ...) FROM t
-- tsql -> mysql:      SELECT DATE_FORMAT(d, ...) FROM t
-- tsql -> oracle:     SELECT TO_CHAR(d, ...) FROM t

SELECT CONVERT(VARCHAR(10), d, 103) FROM t   -- style 103 = dd/mm/yyyy
-- tsql -> mysql: ... DATE_FORMAT(d, '%d/%m/%Y') ...
```

Against a *non*-date target type, the style code carries no format
information to translate — it's simply dropped, and the conversion becomes
a plain cast:

```sql
-- corpus case reda-ts-convert-numeric-style
SELECT CONVERT(INT, '26', 0) AS r
-- tsql -> postgresql: SELECT CAST('26' AS INT) AS r;
-- tsql -> mysql:      SELECT CAST('26' AS SIGNED) AS r;
-- tsql -> oracle:      SELECT CAST('26' AS INT) AS r;
```

**Discussion.** The style code's meaning is entirely dependent on the
`CONVERT` call's *target type*, which Unique reads before deciding how (or
whether) to translate the style argument: a date/time target routes the
style through this project's general [Date Format
Strings](../../03-unsupported.md) token table, picking the matching mask
for each target's own format function; a non-date target has no comparable
formatting concept for the style code to drive, so the whole third argument
is dropped and the call becomes an ordinary type cast — reproducing
`CONVERT`'s own defined behavior for a style code that doesn't apply to the
conversion it was given.

> **Note** faithful — the date-style leg reproduces the identical formatted
> string on every target (live-verified `103` = `dd/mm/yyyy`); the
> numeric-target leg reproduces the identical cast value, since the
> dropped style code was never operative there to begin with. No warning.

**See Also.** [`test_cross_dialect.py::TestConvertStyle`](../../../tests/integration/test_cross_dialect.py)
(`test_convert_style_120`, `test_convert_style_103_uk_date`) · Corpus
[`reda-ts-convert-numeric-style`](../../../tests/fixtures/challenge/challenge_sqlserver.sql) ·
`test_challenge_assertions_sqlserver.py` (`reda-ts-convert-numeric-style`) ·
[§3.1](../../03-unsupported.md), "Date Format Strings" (the shared token
table this entry's date-style leg routes through).
