[← DML: PIVOT/UNPIVOT, MERGE, DELETE, row values](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=dml type="Error-tolerant cast lowering" direction="oracle/tsql → cross-engine" kind=article order=30 -->

# Error-tolerant cast (Oracle `DEFAULT … ON CONVERSION ERROR` / T-SQL `TRY_CAST`/`TRY_CONVERT`) → cross-engine guard

**Problem.** Oracle's `CAST(x AS T DEFAULT d ON CONVERSION ERROR)` returns
`d` instead of raising when the conversion fails; T-SQL's `TRY_CAST`/
`TRY_CONVERT` return `NULL` the same way. PostgreSQL and MySQL have no
error-safe cast at all — their plain `CAST` raises (PostgreSQL) or, for
MySQL, silently returns a wrong default (`0`) instead of failing.

**Solution.**

```sql
-- corpus case ora-cast-onerror (literal), oracle -> tsql/postgresql/mysql
SELECT CAST('abc' AS NUMBER DEFAULT -1 ON CONVERSION ERROR) AS r FROM DUAL;
-- => every target (folded at transpile time — 'abc' is not numeric)
SELECT -1 AS r;

-- same clause over a COLUMN (nothing to fold), oracle -> tsql/postgresql/mysql
SELECT CAST(c AS NUMBER DEFAULT -1 ON CONVERSION ERROR) AS r FROM t;
-- => tsql
SELECT COALESCE(TRY_CAST(c AS DECIMAL(38, 10)), -1) AS r FROM t;
-- => postgresql
SELECT CASE WHEN c::text ~ '^[+-]?([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][+-]?[0-9]+)?$'
       THEN CAST(c AS DECIMAL) ELSE -1 END AS r FROM t;
-- => mysql
SELECT CASE WHEN CAST(c AS CHAR) REGEXP '^[+-]?([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][+-]?[0-9]+)?$'
       THEN CAST(c AS DECIMAL(38, 10)) ELSE -1 END AS r FROM t;
```

T-SQL's own `TRY_CAST`/`TRY_CONVERT` (no explicit fallback, `NULL` on
failure) reduce to the same mechanism, just with `NULL` in the `ELSE`/
`COALESCE` slot instead of a named default — and translate the other
direction too:

```sql
-- red3-ts-trycast-column-nonliteral, tsql -> postgresql/mysql/oracle
SELECT TRY_CAST(c AS INT) AS r FROM t;
-- => postgresql
SELECT CASE WHEN c::text ~ '^[+-]?[0-9]+$' THEN CAST(c AS INT) ELSE NULL END AS r FROM t;
-- => mysql
SELECT CASE WHEN CAST(c AS CHAR) REGEXP '^[+-]?[0-9]+$' THEN CAST(c AS SIGNED) ELSE NULL END AS r FROM t;
-- => oracle (native)
SELECT CAST(c AS INT DEFAULT NULL ON CONVERSION ERROR) AS r FROM t;
```

A **literal** operand is resolved at transpile time instead of wrapped in a
runtime guard — a valid number casts, a non-numeric one becomes the
fallback directly — because PostgreSQL constant-folds a `CASE`'s `THEN`
branch during query planning and would raise on a bad literal cast before
the guard ever runs at execution time; folding it away sidesteps that
planner-time evaluation entirely. A **column** (or any non-literal) operand
cannot be folded, so PostgreSQL/MySQL instead validate the text against a
number pattern in a runtime `CASE` — `INT`-family targets guard on an
integer-only pattern, `DECIMAL`/`FLOAT` on the general numeric one — before
attempting the cast, so a non-numeric row yields the fallback instead of a
MySQL `0` or a PostgreSQL abort.

**Discussion.** T-SQL is the only non-Oracle engine with a native error-safe
cast (`TRY_CAST`/`TRY_CONVERT`), which is why it needs no guard at all — the
Oracle fallback is simply supplied through `COALESCE`. PostgreSQL and MySQL
have nothing to call, so the "did this convert?" question the source asked
at cast time has to be answered *before* the cast, with a regular-expression
validity test over the text representation — the closest any of these two
engines get to a try/fallback primitive without an extension.

> **Note** faithful — live-verified `-1` (bad input) / `123.5` (good input)
> on all four engines for the literal corpus case, and matching
> `(42, NULL)` results on PostgreSQL/MySQL/Oracle for the column case
> (`c` holding `'42'` and `'abc'`).

A **non-numeric** target type (e.g. casting to `VARCHAR`) has no failure
mode to guard against on PostgreSQL/MySQL — a string cast never fails — so
a fallback paired with a non-numeric target keeps the plain, valid cast and
flags the dropped `DEFAULT` with a documented carrier + warning
(`UNIQUE-1070`) instead: this narrow case is the genuine remaining limit,
covered at [§3.15](../../03-unsupported.md).

**See Also.** Corpus [`ora-cast-onerror`](../../../tests/fixtures/challenge/challenge_oracle.sql), [`ts-cast-trycast`](../../../tests/fixtures/challenge/challenge_sqlserver.sql), [`ts-try-convert`](../../../tests/fixtures/challenge/challenge_sqlserver.sql), [`red3-ts-trycast-column-nonliteral`](../../../tests/fixtures/challenge/challenge_sqlserver.sql), [`red3-ts-tryconvert-column-nonliteral`](../../../tests/fixtures/challenge/challenge_sqlserver.sql) ·
[§3.15](../../03-unsupported.md) (the non-numeric-target residual limit) ·
[`UNIQUE-1070`](../../reference/warnings.md#unique-1070) ·
`emit_expr.py` (`on_error_default` / safe-cast branches, docstrings).

---
