[← Procedural: cursors, dynamic SQL, system procedures, session directives](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=procedural type="Expression arguments hoisted through a synthesized variable" direction="tsql ↔ oracle/postgresql" kind=article order=9 -->

# RAISERROR (T-SQL) ↔ Oracle `RAISE_APPLICATION_ERROR` / PostgreSQL `RAISE EXCEPTION`: expression messages and printf substitutions

**Problem.** T-SQL's `RAISERROR` accepts only a literal, a variable, or a
message id as its first argument — never an expression. An Oracle
`RAISE_APPLICATION_ERROR(code, msg_expr)` translated to T-SQL, or a
T-SQL-source `RAISERROR` whose own message argument is itself an expression
(a `+`/`||` concatenation), both need somewhere to put that expression
before it can reach `RAISERROR`. Separately, `RAISERROR`'s printf-style
`%d`/`%s` substitution arguments (`RAISERROR('value is %d today', 16, 1,
42)`) have no direct spelling on PostgreSQL/Oracle, whose own raise
statements format substitutions differently.

**Solution.** An expression message hoists through a synthesized,
routine-scoped `@unique_errmsgN` variable, declared immediately before the
`RAISERROR` call:

```sql
-- tests/integration/test_oracle_source_m4_wave.py::TestOracleBuiltinsOnTsql::test_error_context_and_sys_context
create or replace PROCEDURE p_x AS
BEGIN
    UPDATE t_c SET x = 1;
EXCEPTION WHEN OTHERS THEN
    RAISE_APPLICATION_ERROR(-20001, SQLCODE || ' ' || SQLERRM);
END;
-- oracle -> tsql:
CREATE OR ALTER PROCEDURE p_x
AS
BEGIN
    SET NOCOUNT ON;

    BEGIN TRY
            UPDATE t_c SET x = 1;
    END TRY
    BEGIN CATCH
            DECLARE @unique_errmsg1 NVARCHAR(2048) = CAST(ERROR_NUMBER() AS NVARCHAR(20)) + ' ' + ERROR_MESSAGE();
            RAISERROR(@unique_errmsg1, 16, 1);
    END CATCH
END
```

The same hoist fires for a T-SQL-source `RAISERROR` whose own payload is a
concatenation, or a PostgreSQL-source `RAISE EXCEPTION` with a format string
plus argument
(`tests/integration/test_pg_source_wave1.py::TestTsqlRaiserrorExpressionHoist::test_concat_payload_hoists`)
— only a single string literal, a bare variable, or a message id is left
inline; anything else routes through the same `@unique_errmsgN` variable.

In the opposite direction — a T-SQL `RAISERROR` with printf substitution
arguments read as the *source* — the arguments are spliced directly into
each target's own format spelling instead of being hoisted or dropped:

```sql
-- corpus case red2-ts-raiserror-format-arg-drop
CREATE PROCEDURE p AS
BEGIN
  RAISERROR('value is %d today', 16, 1, 42);
END
-- tsql -> postgresql:
RAISE EXCEPTION 'value is % today', 42;
-- tsql -> oracle:
RAISE_APPLICATION_ERROR(-20001, 'value is ' || 42 || ' today');
```

**Discussion.** `RAISERROR`'s argument grammar is a T-SQL-only restriction —
PostgreSQL's `RAISE` and Oracle's `RAISE_APPLICATION_ERROR` both already
accept an arbitrary expression in the message position, so the hoist is only
needed when a T-SQL `RAISERROR` is the *target* of the rewrite, never when
it is the source being read into a more permissive target. The printf splice
runs the other way for the same structural reason: PostgreSQL's `RAISE`
already has its own `%`-placeholder substitution mechanism (`RAISE
EXCEPTION 'value is % today', 42`), and Oracle has none, so Oracle gets the
substitution folded into an explicit `||` concatenation instead. MySQL's
`SIGNAL` statement has neither a severity/state argument slot nor a printf
substitution mechanism — only the message text transfers, so the severity,
state, and substitution arguments are all dropped and named in the carrier
warning instead (see `UNIQUE-1163`).

> **Note** faithful — the hoisted variable carries the same value the inline
> expression would have produced; the format splice reproduces the same
> substituted text (`"value is 42 today"`) on PostgreSQL and Oracle, with no
> warning for either. MySQL instead drops the severity/state/substitution
> arguments with a warning (`UNIQUE-1163`).

**See Also.** [`TestOracleBuiltinsOnTsql`](../../../tests/integration/test_oracle_source_m4_wave.py), [`TestTsqlRaiserrorExpressionHoist`](../../../tests/integration/test_pg_source_wave1.py), [`TestRaiserrorFormatArgs`](../../../tests/integration/test_challenge.py) ·
Corpus [`red2-ts-raiserror-format-arg-drop`](../../../tests/fixtures/challenge/challenge_sqlserver.sql) ·
[`UNIQUE-1163`](../../reference/warnings.md#unique-1163)
(the MySQL leg's own substitution-args-dropped warning, for contrast).
