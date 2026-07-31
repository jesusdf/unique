[← Procedural: cursors, dynamic SQL, system procedures, session directives](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=procedural type="Dynamic-SQL loop-to-aggregate rewrite" direction="tsql → oracle" kind=article order=36 -->

# A row-by-row dynamic-SQL string build (T-SQL) → a single Oracle `LISTAGG` + `EXECUTE IMMEDIATE`

**Problem.** A common T-SQL pattern builds a dynamic-SQL string by looping
over a result set implicitly, appending to the same variable on every row:
`SELECT @sql = @sql + expr FROM t`. Translated statement-by-statement, this
has no PL/SQL equivalent — Oracle has no bare aggregation-assignment `SELECT`
that updates a variable once per row the way T-SQL's does — so the whole
pattern needs recognizing as what it actually computes: a string
aggregation over the result set, not a loop.

**Solution.**

```sql
-- ts-dyn-concat-loop, tsql → oracle
CREATE PROCEDURE p AS BEGIN
  DECLARE @sql NVARCHAR(MAX) = N'';
  SELECT @sql = @sql + 'DROP TABLE ' + name + ';' FROM sys.tables;
  EXEC(@sql);
END;

-- =>
CREATE OR REPLACE PROCEDURE p
IS
    V_SQL NVARCHAR2(2000) := N'';
BEGIN
    BEGIN
        SELECT CASE WHEN V_SQL IS NULL THEN NULL
                     ELSE V_SQL || LISTAGG('DROP TABLE ' || table_name || ';', '')
                          WITHIN GROUP (ORDER BY ROWNUM)
                END
        INTO V_SQL
        FROM user_tables;
    EXCEPTION
        WHEN NO_DATA_FOUND THEN
            NULL;  -- T-SQL leaves the variables unchanged
    END;
    EXECUTE IMMEDIATE V_SQL;
END;
```

The whole `SELECT @sql = @sql + expr FROM ...` scaffold — which runs once
per row, re-assigning the variable each time — is replaced by a single
`LISTAGG(expr, '') WITHIN GROUP (ORDER BY ROWNUM)` expression that computes
the same concatenated string set-at-a-time, prefixed with the variable's
own starting value (preserved by the `V_SQL ||` prefix) and T-SQL's
`NULL`-propagation behavior (the `CASE WHEN V_SQL IS NULL THEN NULL`
guard: if the variable started `NULL`, T-SQL's row-by-row `+=` would have
stayed `NULL` throughout). `sys.tables` maps to Oracle's `user_tables`
(`name` becomes `table_name`), and the built string is executed with
`EXECUTE IMMEDIATE` in place of T-SQL's `EXEC(@sql)`.

**Discussion.** This is a structural restructure, not a per-statement
translation: nothing about a bare `SELECT ... FROM t` that reassigns a
variable on every row exists in PL/SQL, so translating the loop shape
literally isn't an option at all — the *only* correct output is a
different construct entirely, one that computes the same final string a
different way. Recognizing that the pattern is a string aggregation in
disguise (T-SQL's own accepted idiom for "concatenate a column across all
rows" before `STRING_AGG` existed) makes `LISTAGG` the natural
set-based equivalent. `WITHIN GROUP (ORDER BY ROWNUM)` supplies a concrete,
deterministic row order for the aggregation, since Oracle's `LISTAGG`
requires an explicit order and the source loop's own row order was
whatever `sys.tables` happened to return.

> **Note** faithful — live-compiled `VALID` on Oracle; the aggregated
> `LISTAGG` result and the `EXECUTE IMMEDIATE` both preserve the original
> loop's intent (build then run one dynamic `DROP TABLE` script).

**See Also.** Corpus [`ts-dyn-concat-loop`](../../../tests/fixtures/challenge/challenge_sqlserver.sql) ·
[`TestPgFnAttrsAndAggregationAssignment::test_aggregation_assignment_listagg`](../../../tests/integration/test_challenge.py) ·
[A constant dynamic-SQL string → any target](constant-dynamic-sql-string.md),
the sibling entry for the simpler, non-looped dynamic-SQL case ·
[`UNIQUE-1231`](../../reference/warnings.md#unique-1231).
