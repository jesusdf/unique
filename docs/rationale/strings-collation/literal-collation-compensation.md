[← Strings, concatenation and collation](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=strings-collation type="Collation and ordering" direction="cross-engine" kind=article order=14 direction-inferred=true -->

# Case-sensitivity compensation on string-literal operands (cross-engine)

**Problem.** PostgreSQL and Oracle's default collations compare strings
**case-sensitively**; MySQL's and T-SQL's default collations compare
**case-insensitively**. The same `INSTR('aAaA', 'A')`, `POSITION('a' IN
'ABC')`, `GREATEST('a', 'B')`, `REPLACE('AbCaBc', 'a', 'X')`, or a string
`ORDER BY`/`DISTINCT`/`GROUP BY` key returns a different match position,
argument order, replacement count, or row grouping depending only on which
engine runs it — a value change, not a formatting one.

**Solution.**

```sql
-- ora-instr-case, oracle → mysql / tsql
SELECT INSTR('aAaA', 'A') AS r FROM DUAL;
-- => mysql
SELECT LOCATE('A', BINARY 'aAaA') AS r FROM DUAL;
-- => tsql
SELECT CHARINDEX('A', 'aAaA' COLLATE Latin1_General_BIN2) AS r;
```

Oracle's case-sensitive `INSTR` finds the `'A'` at position 2 (skipping the
lowercase `'a'`); MySQL's and T-SQL's default collations would otherwise
match the lowercase `'a'` at position 1. Forcing `BINARY`/`COLLATE
Latin1_General_BIN2` on the literal haystack makes the comparison
case-sensitive again, so both targets return 2, live-verified matching
Oracle.

The reverse direction — MySQL's case-insensitive default onto a
case-sensitive target — lower-cases both operands instead of forcing a
binary comparison, since PostgreSQL/Oracle have no single collation keyword
that reproduces MySQL's default behavior on an arbitrary column:

```sql
-- my-instr-case, mysql → oracle / postgresql
SELECT INSTR('aAaA', 'A') AS r;
-- => oracle
SELECT INSTR(LOWER('aAaA'), LOWER('A')) AS r FROM DUAL;
-- => postgresql
SELECT POSITION(LOWER('A') IN LOWER('aAaA')) AS r;
-- => tsql (already case-insensitive by default — untouched)
SELECT CHARINDEX('A', 'aAaA') AS r;
```

The same forced-collation idea extends to ordering and set operations, with
the collation applied to every key that needs to stay consistent
(`SELECT`/`GROUP BY`/`ORDER BY` all get it together):

```sql
-- pg-order-case-sens, postgresql → mysql / tsql
SELECT x FROM (SELECT 'Apple' x UNION SELECT 'banana' UNION SELECT 'Cherry') t ORDER BY x;
-- => mysql
SELECT x FROM (...) t ORDER BY CASE WHEN x IS NULL THEN 1 ELSE 0 END, x COLLATE utf8mb4_bin ASC;
-- => tsql
SELECT x FROM (...) t ORDER BY CASE WHEN x IS NULL THEN 1 ELSE 0 END, x COLLATE Latin1_General_BIN2 ASC;
```

`GREATEST`/`LEAST` follow the same rule, collating only the first string
literal (the comparison itself only needs one side pinned):

```sql
-- pg-greatest-string, postgresql → mysql / tsql
SELECT GREATEST('a', 'B') AS r;
-- => mysql
SELECT GREATEST('a' COLLATE utf8mb4_bin, 'B') AS r;
-- => tsql
SELECT GREATEST('a' COLLATE Latin1_General_BIN2, 'B') AS r;
```

**Discussion.** Collation is normally a column- or connection-level
property with no trace in the SQL text — the sibling entry, [Collation and
ordering divergences](collation-and-ordering-limits.md), documents the case
where Unique genuinely has no way to bridge it (an arbitrary column
reference, whose actual collation is invisible to the transpiler). A
*literal* operand is different: its value and type are known at transpile
time, so Unique can pin its comparison behavior explicitly rather than
inherit whichever default the target engine happens to use. The mechanism
covers `POSITION`, `INSTR`, `ORDER BY`/`DISTINCT`/`GROUP BY` keys,
`GREATEST`/`LEAST`, and `REPLACE`'s subject argument — anywhere a
provably-string literal feeds a comparison whose case sensitivity the
source engine's default collation determines.

The two directions use different tools because they need different things:
going from a case-sensitive source to a case-insensitive target, an
explicit binary collation (`BINARY` on MySQL, `COLLATE Latin1_General_BIN2`
on T-SQL) makes the *existing* comparison case-sensitive without changing
either value. Going the other way — a case-insensitive MySQL source onto a
case-sensitive PostgreSQL/Oracle target — there is no single "case
insensitive" collation keyword available on an arbitrary comparison, so
`LOWER()` is applied to both operands instead, which is equivalent for
equality/search purposes. T-SQL is already case-insensitive by default, so
a MySQL source reaching T-SQL needs neither compensation.

Where the literal isn't provably a fixed string (a mix of differently-cased
values whose relative order genuinely can't be reconstructed, or a case
where the values happen to tie under the target's collation), the general
"inherent value divergence" warning still applies instead — see
[`UNIQUE-1207`](../../reference/warnings.md#unique-1207).

> **Note** faithful — live-verified: `INSTR('aAaA','A')` = 2 on Oracle,
> MySQL and T-SQL after compensation (1 without it); the ordered/`DISTINCT`
> result sets match PostgreSQL's case-sensitive order on every target.

**See Also.** Corpus [`ora-instr-case`](../../../tests/fixtures/challenge/challenge_oracle.sql),
[`my-instr-case`](../../../tests/fixtures/challenge/challenge_mysql.sql),
[`pg-position-case`](../../../tests/fixtures/challenge/challenge_postgresql.sql),
[`pg-order-case-sens`](../../../tests/fixtures/challenge/challenge_postgresql.sql),
[`po-distinct-case`](../../../tests/fixtures/challenge/challenge_postgresql.sql),
[`po-group-case`](../../../tests/fixtures/challenge/challenge_postgresql.sql),
[`my-order-case-sens`](../../../tests/fixtures/challenge/challenge_mysql.sql),
[`pg-greatest-string`](../../../tests/fixtures/challenge/challenge_postgresql.sql),
[`my-replace-case`](../../../tests/fixtures/challenge/challenge_mysql.sql),
[`my-locate-case`](../../../tests/fixtures/challenge/challenge_mysql.sql),
[`ts-order-strings`](../../../tests/fixtures/challenge/challenge_sqlserver.sql) ·
[`TestPositionCaseSensitive`](../../../tests/integration/test_challenge.py),
[`TestOrderByCaseSensitive`](../../../tests/integration/test_challenge.py),
[`TestGreatestCaseSensitive`](../../../tests/integration/test_challenge.py),
[`TestInstrCaseSensitive`](../../../tests/integration/test_challenge.py),
[`TestMysqlCaseInsensitiveSearch`](../../../tests/integration/test_challenge.py),
[`TestTsqlOrderStringsCollation`](../../../tests/integration/test_challenge.py),
[`TestReplaceCaseSensitive`](../../../tests/integration/test_challenge.py) ·
[Collation and ordering divergences](collation-and-ordering-limits.md), for the
unbridgeable column-collation case · [`UNIQUE-1207`](../../reference/warnings.md#unique-1207).
