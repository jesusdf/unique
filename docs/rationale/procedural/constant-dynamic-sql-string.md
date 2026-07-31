[← Procedural: cursors, dynamic SQL, system procedures, session directives](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=procedural type="Dynamic SQL constant translation" direction="cross-engine" kind=article order=11 direction-inferred=true -->

# A constant dynamic-SQL string (T-SQL `EXEC sp_executesql` / Oracle `EXECUTE IMMEDIATE` / PL/pgSQL `EXECUTE`) → any target

**Problem.** Dynamic SQL executes a string built at runtime. When
that string is a **literal** (or a variable whose single assignment is a
literal), its content is, in practice, statically known SQL in the source
dialect.

**Solution.**

```sql
-- corpus case pg-dyn-count
CREATE FUNCTION f(tbl TEXT) RETURNS BIGINT AS $$
  DECLARE n BIGINT;
  BEGIN EXECUTE format('SELECT COUNT(*) FROM %I', tbl) INTO n; RETURN n; END;
$$ LANGUAGE plpgsql
-- Oracle: EXECUTE IMMEDIATE '...' || '"' || REPLACE(tbl, ...) || '"' ...
--   (live-compiled VALID); PL/SQL BIGINT -> NUMBER(19)

-- corpus case ts-sp-executesql
CREATE PROCEDURE p AS BEGIN
  DECLARE @sql NVARCHAR(200) = N'SELECT * FROM t WHERE id=@i';
  EXEC sp_executesql @sql, N'@i INT', @i = 5;
END
-- Oracle: EXECUTE IMMEDIATE ... USING :1 ...  (named params bind POSITIONALLY;
-- a UNIQUE note warns the dynamic string's placeholders must be :1, :2, ...)
-- live-compiled VALID
```

A **constant** dynamic-SQL string is itself translated using the same rules
as the surrounding script, and the translated text is spliced back into the
string literal, so the target engine executes its own dialect at runtime
(nested translation capped at depth 2, warned beyond). A string
**built at runtime** (concatenation, parameter values, more than one
assignment) cannot be translated statically: literal fragments still get
ordinary fragment-level rewrites, and the statement is flagged with a
"review the dynamic SQL" warning instead. `format('%I', …)`-style identifier
quoting inside a dynamic-SQL template is re-spelled per target (Oracle
`'"'||REPLACE(…)||'"'`, T-SQL `QUOTENAME`), and a printf-style `%s`-only
`format()` template is rewritten to concatenation (`||`/`CONCAT`) rather than
kept as PostgreSQL-only syntax; complex `%I`/`%L`/width specs still degrade
to a carrier.

**Discussion.** A dynamic-SQL string is opaque to a
purely syntactic transpiler by default — it is just a string literal, not
parsed SQL — so naively copying it across leaves source-dialect SQL running
unmodified inside the target engine.

> **Note** faithful for a constant string (live-compiled
> valid). `[limit]`/warned for a runtime-built string or a complex `format()`
> template.

**See Also.** [`pg-dyn-count`](../../../tests/fixtures/challenge/challenge_postgresql.sql), [`pg-format-func`](../../../tests/fixtures/challenge/challenge_postgresql.sql), [`ts-sp-executesql`](../../../tests/fixtures/challenge/challenge_sqlserver.sql) ·
[§6](../../03-unsupported.md) (Dynamic SQL) ·
[`UNIQUE-1161`](../../reference/warnings.md#unique-1161) ·
[`UNIQUE-1180`](../../reference/warnings.md#unique-1180).
