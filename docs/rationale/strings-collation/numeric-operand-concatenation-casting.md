[← Strings, concatenation and collation](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=strings-collation type="Concatenation" direction="cross-engine" kind=article order=16 direction-inferred=true -->

# Numeric-operand `||`/`CONCAT` casting (Oracle/MySQL → T-SQL, → PostgreSQL)

**Problem.** Oracle's `||` and MySQL's `CONCAT` implicitly stringify a
numeric operand: `2 || 3` is the two-character string `'23'`. Neither
T-SQL's `+` nor PostgreSQL's `||` read that the same way — T-SQL's `+` does
arithmetic on two numbers instead (`2 + 3` = `5`), and PostgreSQL's `||` has
no `integer || integer` overload at all (a straight translation is a
parse/type error there, not a wrong value).

**Solution.**

```sql
-- ora-num-concat, oracle → tsql
SELECT 2 || 3 AS r FROM DUAL;
-- =>
SELECT CONCAT(2, 3) AS r;
```

A numeric-operand concatenation reaching T-SQL emits `CONCAT()` instead of
`+`, since T-SQL's `CONCAT` always stringifies its arguments (matching
Oracle's `||`/MySQL's `CONCAT` reading) regardless of operator choice. This
also covers a mixed string/numeric operand:

```sql
-- ora-concat-num, oracle → tsql
SELECT 'a' || 5 AS r FROM DUAL;
-- =>
SELECT CONCAT('a', 5) AS r;
```

On PostgreSQL, where `||` itself has no numeric overload, both operands are
cast to `TEXT` only when **both** are known-numeric — a string or
unknown-typed operand already resolves against PostgreSQL's own `text ||
anynonarray` overload and is left untouched:

```sql
-- ora-num-concat, oracle → postgresql
SELECT 2 || 3 AS r FROM DUAL;
-- =>
SELECT CAST(2 AS TEXT) || CAST(3 AS TEXT) AS r;

-- ora-concat-num, oracle → postgresql (one operand is a string — untouched)
SELECT 'a' || 5 AS r FROM DUAL;
-- =>
SELECT 'a' || 5 AS r;
```

**Discussion.** Each target's `||`/`+`/`CONCAT` resolves a numeric operand
under its own type rules, not the source's: T-SQL's `+` is arithmetic
unless every operand is textual, so a translation that kept `+` would
silently swap concatenation for addition; PostgreSQL's `||` simply has no
built-in numeric overload to resolve against, so an untouched `2 || 3`
would fail to parse rather than produce a wrong value. Both fixes stop at
what each target actually needs: T-SQL gets `CONCAT()` unconditionally
(it stringifies any operand type, so there is no risk in always using it
for a source concatenation), while PostgreSQL only gets the `CAST(...  AS
TEXT)` treatment when guessing wrong would otherwise be required — a
string operand's own type already routes to PostgreSQL's `text ||
anynonarray` overload, so casting it too would be redundant, and guessing a
*column's* type when it isn't already known risks a wrong cast the
transpiler has no basis for.

> **Note** faithful — live-verified: `2 || 3` yields `'23'` on Oracle,
> matching `CONCAT(2, 3)` on T-SQL and the double-`CAST` form on
> PostgreSQL.

**See Also.** Corpus [`ora-num-concat`](../../../tests/fixtures/challenge/challenge_oracle.sql),
[`ora-concat-num`](../../../tests/fixtures/challenge/challenge_oracle.sql) ·
[`TestConcatNumberIntoTsql`](../../../tests/integration/test_challenge.py),
[`TestConcatNumberIntoPostgres`](../../../tests/integration/test_challenge.py) ·
[CONCAT / `\|\|` NULL-propagation per engine](concat-null-propagation.md), the
sibling concatenation-semantics entry.
