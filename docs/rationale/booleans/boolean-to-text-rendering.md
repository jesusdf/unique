[← Booleans: the value/predicate duality](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=booleans type="Value position: booleans wrapped for engines with no boolean value" direction="postgresql/mysql → mysql/postgresql" kind=article order=8 -->

# Boolean-to-text/char rendering (PostgreSQL `::text` / MySQL `CAST(... AS CHAR)`)

**Problem.** PostgreSQL renders a boolean cast to text as the words
`'true'`/`'false'`; MySQL has no boolean text representation at all — its
booleans are ordinary integers, so casting one to a character type gives
`'1'`/`'0'` instead. Neither engine's own text rendering matches the
other's, so a straight `CAST` translation gives the wrong string in both
directions.

**Solution.**

PostgreSQL's boolean-to-text cast, and a boolean-valued comparison
rendered as text, reach MySQL as a `CASE` expression producing the literal
words:

```sql
-- pg-bool-text2, postgresql → mysql
SELECT true::text AS r;
-- =>
SELECT CASE WHEN TRUE THEN 'true' ELSE 'false' END AS r;

-- pg-bool-repr, postgresql → mysql (a comparison rendered as text)
SELECT (1>0)::text AS r;
-- =>
SELECT CASE WHEN 1 > 0 THEN 'true' ELSE 'false' END AS r;
```

The reverse direction — MySQL's boolean-as-integer `CAST(... AS CHAR)` —
gets the mirror-image `CASE`, converting to `1`/`0` first so MySQL's
`'1'`/`'0'` reading survives instead of leaking PostgreSQL's `TRUE`/`FALSE`
words:

```sql
-- my-bool-char, mysql → postgresql
SELECT CAST((1=1) AS CHAR) AS r;
-- =>
SELECT CAST(CASE WHEN 1 = 1 THEN 1 ELSE 0 END AS TEXT) AS r;
```

The same conversion applies inside `CONCAT`, where a bare PostgreSQL
`TRUE`/`FALSE` would otherwise render as the letters `t`/`f` instead of
MySQL's `1`/`0`:

```sql
-- my-concat-bool, mysql → postgresql
SELECT CONCAT(TRUE, FALSE) AS r;
-- =>
SELECT CONCAT(1, 0) AS r;
```

**Discussion.** Every target here already has a way to render a boolean as
text or as a character type — the problem is that each one's native
rendering is different words entirely (`'true'`/`'false'` vs. `'1'`/`'0'`
vs., left unconverted, PostgreSQL's own `t`/`f` single-character form
inside `CONCAT`). A `CASE WHEN <bool> THEN <text-1> ELSE <text-2> END`
reproduces the *source* engine's own textual convention explicitly on the
target, rather than falling through to whatever the target's own
cast/concatenation happens to produce. This is the same tri-state-`CASE`
shape used throughout this topic to carry a boolean value across engines
with no boolean value type — here applied to the boolean's *textual*
representation instead of its numeric one.

> **Note** faithful — live-verified: `true::text` = `'true'` on PostgreSQL,
> matched by the `CASE`-wrapped MySQL form; `CAST((1=1) AS CHAR)` = `'1'`
> on MySQL, matched by the `CASE`-wrapped PostgreSQL form; `CONCAT(TRUE,
> FALSE)` = `'10'` on MySQL, matched by `CONCAT(1, 0)` on PostgreSQL.

**See Also.** Corpus [`pg-bool-text2`](../../../tests/fixtures/challenge/challenge_postgresql.sql),
[`pg-bool-repr`](../../../tests/fixtures/challenge/challenge_postgresql.sql),
[`my-bool-char`](../../../tests/fixtures/challenge/challenge_mysql.sql),
[`my-concat-bool`](../../../tests/fixtures/challenge/challenge_mysql.sql) ·
[`TestPgBooleanToText`](../../../tests/integration/test_challenge.py),
[`TestMysqlBooleanCast`](../../../tests/integration/test_challenge.py).
