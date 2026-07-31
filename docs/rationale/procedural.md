# Procedural: cursors, dynamic SQL, system procedures, session directives

Stored-procedure/function/trigger bodies parsed into an IR and re-emitted in
the target dialect — cursors, error handling, dynamic SQL, system procedures,
and client-tool directives. See [README.md](README.md) for the entry format
and sourcing rules.

## System procedures

### `EXEC sp_<name>` degrade policy (T-SQL) → PostgreSQL / Oracle / MySQL

**Problem.** T-SQL system procedures (`sp_rename`, `sp_who`, …) call
into SQL Server's own catalog/admin machinery.

**Solution.** An unmapped `sp_*` call degrades to a documented
`-- UNIQUE:` carrier comment plus a `result.warnings` entry — the call is
never shipped as executable SQL, since the target has nothing to route it
to.

**Discussion.** These are engine-internal administrative
routines; no other engine exposes the same operation through a callable
procedure with the same name or signature.

> **Warning** `[limit]` — approved degrade; the administrative
> action itself is lost and must be performed through the target's own
> tooling.

**See Also.** [`reda-ts-exec-swallow-next`](../../tests/fixtures/challenge/challenge_sqlserver.sql), `mysql-drop2` family (see below) ·
[`UNIQUE-1211`](../reference/warnings.md#unique-1211).

### Statement-after-`EXEC` survival fix

**Problem.** A degraded system-proc `EXEC`, followed by another
statement on the same line separated only by `;` (not a batch-separating
`GO`): `EXEC sp_rename 't.a','b','COLUMN'; UPDATE t SET b = 1;`.

**Solution.**

```sql
-- corpus case reda-ts-exec-swallow-next
EXEC sp_rename 't.a', 'b', 'COLUMN'; UPDATE t SET b = 1
-- every target: sp_rename becomes a UNIQUE: carrier + warning;
-- UPDATE t SET b = 1 still transpiles (present on postgresql/oracle/mysql)
```

Statements are split on `;` **before** degrading, so
only the `sp_rename` call becomes a carrier and the `UPDATE` still
transpiles normally on every target.

**Discussion.** *Why there is no direct mapping.* N/A — this is not a
cross-engine gap but a real defect: the `;`-split path that isolates the
degraded `EXEC` into its own carrier used to fold the **following** statement
into that same carrier, so `sp_rename`'s degrade silently swallowed the valid
`UPDATE` too (the warning named only `sp_rename`). With `GO`-separated
batches the `UPDATE` correctly survived — only the `;`-separated case was
affected.

> **Note** faithful for the `UPDATE` — no-silent-loss
> restored. `[limit]` for the `sp_rename` call itself, as above.

**See Also.** [`reda-ts-exec-swallow-next`](../../tests/fixtures/challenge/challenge_sqlserver.sql) ·
[`UNIQUE-1211`](../reference/warnings.md#unique-1211).

## `SET IDENTITY_INSERT` coherent degrade

### `SET IDENTITY_INSERT t ON … INSERT … SET IDENTITY_INSERT t OFF` (T-SQL) → PostgreSQL / Oracle / MySQL

**Problem.** T-SQL requires `IDENTITY_INSERT` to be explicitly
turned `ON` before a script can supply its own value for an identity column,
then turned back `OFF`.

**Solution.**

```sql
-- corpus case reda-ts-identity-insert
CREATE TABLE t (id INT IDENTITY(1,1), v INT);
SET IDENTITY_INSERT t ON;
INSERT INTO t (id, v) VALUES (5, 10);
SET IDENTITY_INSERT t OFF
-- every target: both SET IDENTITY_INSERT statements become carriers (one
-- warning); INSERT INTO t (id, v) VALUES (5, 10) transpiles unchanged
```

Both `SET IDENTITY_INSERT … ON/OFF` statements
degrade to documented carriers (with one warning), and the `INSERT` itself
—value list intact— transpiles normally, since every target already accepts
an explicit identity value without special ceremony.

**Discussion.** None of the other three targets
distinguishes an "explicit identity value" mode — they simply accept an
explicit value in the `INSERT` column list (PostgreSQL 15+ additionally has
`OVERRIDING SYSTEM VALUE`, unused here).

> **Note** faithful for the `INSERT`'s data. `[limit]`
> (carrier) for the `ON`/`OFF` bracket itself. The earlier defect handled the
> two `SET` statements **incoherently**: `ON` degraded correctly, but `OFF`
> was mangled into `SET IDENTITY_INSERT = t AS OFF` and shipped as **live,
> invalid** SQL with no warning (PostgreSQL: `syntax error at or near "AS"`)
> — a real defect this fix closes.

**See Also.** [`reda-ts-identity-insert`](../../tests/fixtures/challenge/challenge_sqlserver.sql) ·
[`UNIQUE-1002`](../reference/warnings.md#unique-1002).

## SQL*Plus directives preserved as comments

### `SET SERVEROUTPUT ON` and similar client directives (Oracle) → PostgreSQL / T-SQL / MySQL

**Problem.** SQL*Plus `SET` directives (`SET SERVEROUTPUT ON`,
etc.) are **line-oriented client-tool commands**, not SQL statements — they
carry no trailing `;` and configure the SQL*Plus session, not the database.

**Solution.**

```python
# tests/integration/test_sqlplus_directives.py::test_directive_commented_and_block_survives
src = "SET SERVEROUTPUT ON\nBEGIN\n  my_proc('x');\nEND;\n/"
# transpiled (oracle -> tsql/postgresql/mysql):
#   -- SET SERVEROUTPUT ON      (never shipped as executable SQL)
#   ... my_proc(...) call, still present and callable ...
```

The splitter peels a recognized directive into its
own batch; it is emitted as a `-- SET SERVEROUTPUT ON`-style comment plus a
warning, never as executable SQL — and the block that follows it still
transpiles normally.

**Discussion.** No target engine has a SQL*Plus client
to configure; the directive has no server-side counterpart at all. Before
the fix, the lack of a statement terminator made the directive **glue onto
the following block** during batch splitting and ship as invalid SQL,
corrupting ~940 statements per direction on a real-world Oracle dump.

> **Warning** `[limit]` for the directive itself (no server-side
> equivalent exists to warn toward). Faithful for the surrounding SQL, which
> now survives instead of being corrupted.

**See Also.** `src/unique/core/procedural/parser/_plsql.py` (SQL*Plus
directive parsing) · `docs/DONE.md` (M4 bring-up, 2026-07-09) ·
`tests/integration/test_sqlplus_directives.py` — no dedicated
challenge-corpus case exercises this construct directly, so the example
above is drawn from that dedicated, passing integration test rather than
from `tests/fixtures/challenge/`.

## `%TYPE` / `%ROWTYPE` carrier without `--db-url`

### Oracle `%TYPE`/`%ROWTYPE` column-type references → PostgreSQL / T-SQL / MySQL

**Problem.** `v_id employees.id%TYPE` declares a variable with
**whatever type** the referenced column currently has — a live binding to
the schema, not a fixed type name.

**Solution.**

```python
# tests/integration/test_procedural.py::test_type_reference_documented_then_restored
src = "CREATE PROCEDURE p (v_id employees.id%TYPE) AS BEGIN NULL; END;"
# oracle -> postgresql: carrier type + "UNIQUE: ... employees.id%TYPE ..." comment
# postgresql -> oracle (round trip): "employees.id%TYPE" restored, no carrier
```

Without `--db-url`: a permissive carrier type per
non-Oracle target (`SQL_VARIANT` on T-SQL, `TEXT` on PostgreSQL, `LONGTEXT` on
MySQL — Oracle keeps the `%TYPE` reference as-is, since it supports it
natively) with a `/* UNIQUE: employees.id%TYPE */` comment preserving the
original reference, plus a warning. With
`--db-url`: the reference resolves to the concrete column type from the live
catalog and no carrier is needed. On a **reverse** transpilation back to an
engine that supports `%TYPE` natively (i.e. back to Oracle), the original
`%TYPE` reference is restored from the comment rather than left as a carrier
— a faithful round trip.

**Discussion.** Only Oracle supports `%TYPE`/`%ROWTYPE`
natively. Resolving the *actual* column type requires a live catalog lookup
(`ALL_TAB_COLUMNS`); without a database connection, Unique has no way to
know what `employees.id`'s type is.

> **Warning** `[limit]` without `--db-url` (the carrier type may
> not match the real column type's behaviour exactly). Faithful with
> `--db-url`, and faithful on the Oracle-to-Oracle round trip either way.

**See Also.** [§6](../03-unsupported.md) ("Oracle → T-SQL specifics") ·
`src/unique/core/procedural/transformer/base.py` (`_transform_data_type`,
the `%TYPE`/`%ROWTYPE` branch) · `tests/integration/test_procedural.py`
(`TestUniqueCommentRestore::test_type_reference_documented_then_restored`) —
no dedicated challenge-corpus case exercises `%TYPE` directly, so the
example above is drawn from that integration test ·
[`UNIQUE-1152`](../reference/warnings.md#unique-1152).

## Cursor attribute mapping

### Oracle `%FOUND`/`%NOTFOUND`/`%ISOPEN`/`%ROWCOUNT` → T-SQL / MySQL

**Problem.** Oracle attaches state to each named cursor:
`c%FOUND`/`c%NOTFOUND` (did the last `FETCH` return a row), `c%ISOPEN`, and
`c%ROWCOUNT` (rows fetched so far on that cursor).

**Solution.**

```sql
-- corpus case ora-cursor-attr
CREATE PROCEDURE p AS CURSOR c IS SELECT 1 FROM DUAL; v NUMBER;
BEGIN OPEN c; FETCH c INTO v; IF c%FOUND THEN DBMS_OUTPUT.PUT_LINE(c%ROWCOUNT); END IF; CLOSE c; END;
-- live-compiled VALID on tsql + mysql
```

Cursor attributes are mapped **before** the general
expression IR sees them (`c%FOUND` would otherwise parse as `c` modulo
`FOUND`). Each named cursor gets its **own** per-cursor state, captured right
beside the cursor operation it depends on: T-SQL captures `@@FETCH_STATUS`
into a per-cursor `@uq_<c>_fs` variable immediately after each `FETCH <c>`;
MySQL transfers the shared handler flag into a per-cursor `v_uq_<c>_done`
right after each `FETCH`, then resets the shared flag. `%ISOPEN` becomes a
per-cursor flag set on `OPEN`/`CLOSE`. `%ROWCOUNT` becomes a per-cursor
counter incremented after each successful `FETCH`. An unrecognized attribute
(e.g. `%BULK_ROWCOUNT`) degrades to a `-- UNIQUE:` carrier + warning — never
emitted as `%` modulo arithmetic.

**Discussion.** T-SQL exposes only a single **global**
`@@FETCH_STATUS`/cursor state, shared across every open cursor in the
routine — reading it for cursor `c` after an intervening `FETCH` on a
*different* cursor `d` would silently report `d`'s status. MySQL similarly
has one shared `NOT FOUND` handler flag per routine, not one per cursor.
Naively mapping Oracle's per-cursor attributes onto either shared mechanism
is only correct if no other cursor is touched in between — not something
Unique can assume about arbitrary procedure bodies.

> **Note** faithful — live-compiled valid on T-SQL and MySQL.

**See Also.** [`ora-cursor-attr`](../../tests/fixtures/challenge/challenge_oracle.sql) · [§3.23](../03-unsupported.md) (audit
B7/N5+N6) — the same section also covers the related but distinct
`SQL%ROWCOUNT`/`ROW_COUNT()` "matched vs. changed rows" divergence onto
MySQL (§3.22).

## Error handling

### MySQL `DECLARE {EXIT|CONTINUE} HANDLER FOR ...` → block-structured exception handling (PostgreSQL / Oracle / T-SQL)

**Problem.** MySQL declares an error handler *separately* from the code it
protects — `DECLARE EXIT HANDLER FOR SQLEXCEPTION <stmt>` sits anywhere in
the block's declaration section, naming the condition(s) it reacts to and a
single action statement. PostgreSQL/Oracle's `EXCEPTION WHEN OTHERS` and
T-SQL's `BEGIN TRY...END TRY BEGIN CATCH...END CATCH` are both
**block-structured** instead: the protected code and its handler are two
halves of one syntactic unit, not a declaration plus free-floating code.

**Solution.** An `EXIT` handler for `SQLEXCEPTION`/`SQLWARNING` is exactly
the enclosing block's exception section, so it folds directly into the
target's own block-structured form — the rest of the block becomes the
protected body, and the handler's action becomes the handler body:

```sql
-- tests/integration/test_pg_source_wave1.py::TestMysqlDeclareHandler (_EXIT_SRC)
create procedure hp()
begin
  declare exit handler for sqlexception select 'bad' as e;
  insert into t1 values (1);
  select 'ok' as r;
end
-- mysql -> postgresql:
CREATE PROCEDURE hp()
LANGUAGE plpgsql
AS $$
BEGIN
    BEGIN
            INSERT INTO t1 VALUES (1);
            SELECT 'ok' AS r;
    EXCEPTION
    WHEN OTHERS THEN
            SELECT 'bad' AS e;
    END;
END;
$$;
-- mysql -> tsql:
CREATE PROCEDURE hp
AS
BEGIN
    SET NOCOUNT ON;

    BEGIN TRY
            INSERT INTO t1 VALUES (1);
            SELECT 'ok' AS r;
    END TRY
    BEGIN CATCH
            SELECT 'bad' AS e;
    END CATCH
END
```

A `CONTINUE` handler, a handler for any condition other than
`SQLEXCEPTION`/`SQLWARNING` (a specific `SQLSTATE`, a named condition, `NOT
FOUND` used outside a cursor loop), more than one handler in the same block,
or a handler declared in a *nested* block all keep the honest,
already-documented whole-routine degrade instead — each with its own
interpolated reason:

```sql
-- tests/integration/test_pg_source_wave1.py::TestMysqlDeclareHandler::test_continue_handler_degrades
create procedure hc()
begin
  declare continue handler for sqlstate '23000' select 'dup';
  insert into t1 values (1);
end
-- mysql -> postgresql:
-- UNIQUE-1171: MySQL CONTINUE handler for SQLSTATE '23000' has no postgresql equivalent; routine preserved as a comment
-- create procedure hc()
-- begin
--   declare continue handler for sqlstate '23000' select 'dup';
--   insert into t1 values (1);
-- end
```

**Discussion.** `EXIT`'s control-flow contract — abandon the block and run
the handler's action — is precisely what `EXCEPTION WHEN OTHERS`/`CATCH`
already do, so a single condition set of `SQLEXCEPTION`/`SQLWARNING` maps
without any semantic gap. `CONTINUE` cannot: it resumes execution at the
statement *after* the one that raised, a resumption model neither
`EXCEPTION`/`CATCH` block nor any other target construct offers. A specific
`SQLSTATE` value or a named condition has no standard cross-engine spelling
Unique can trust without a lookup table it does not have, and a handler
nested inside an inner block, or more than one handler sharing a block,
would need per-condition dispatch logic no target's block-exception form
expresses directly — so each of those keeps the pre-existing whole-routine
carrier rather than guessing a mapping.

> **Note** faithful for the `EXIT`/`SQLEXCEPTION`/`SQLWARNING` fold — same
> protected body, same handler action, restated in each target's own
> block-exception syntax.
> **Warning** `[limit]` (the pre-existing whole-routine degrade,
> unaffected by this fold) for `CONTINUE` handlers, unmapped condition
> classes, multiple handlers, and nested-block handlers.

**See Also.** [`TestMysqlDeclareHandler`](../../tests/integration/test_pg_source_wave1.py) ·
`src/unique/core/procedural/transformer/base.py` (`_fold_mysql_handlers`,
docstring) · [05-procedural-engine.md](../05-procedural-engine.md)
("4. ProceduralTransformer", the `TRY...CATCH` ↔ `EXCEPTION WHEN OTHERS THEN`
mapping-table row) ·
[`UNIQUE-1171`](../reference/warnings.md#unique-1171) — no dedicated
challenge-corpus case exercises `DECLARE HANDLER`, so the examples above are
drawn from that dedicated integration test.

## Expression arguments hoisted through a synthesized variable

### RAISERROR (T-SQL) ↔ Oracle `RAISE_APPLICATION_ERROR` / PostgreSQL `RAISE EXCEPTION`: expression messages and printf substitutions

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
substitution folded into an explicit `||` concatenation instead — before
this was handled, the substitution argument (`42`) was silently **dropped**
on PostgreSQL/Oracle, with the literal `%d` shipped unexpanded and no
warning at all (`red2-ts-raiserror-format-arg-drop`, `class=silent-drop`);
the MySQL leg already warned when the args were dropped, so PG/Oracle were
the inconsistent legs.

> **Note** faithful — the hoisted variable carries the same value the inline
> expression would have produced; the format splice reproduces the same
> substituted text (`"value is 42 today"`) on every target. No warning for
> either direction.

**See Also.** [`TestOracleBuiltinsOnTsql`](../../tests/integration/test_oracle_source_m4_wave.py), [`TestTsqlRaiserrorExpressionHoist`](../../tests/integration/test_pg_source_wave1.py), [`TestRaiserrorFormatArgs`](../../tests/integration/test_challenge.py) ·
Corpus [`red2-ts-raiserror-format-arg-drop`](../../tests/fixtures/challenge/challenge_sqlserver.sql) ·
`src/unique/core/procedural/emitter/tsql.py` (the `_emit_raise_error` message-hoist
branch, docstring) · `src/unique/core/procedural/emitter/postgresql.py`,
`src/unique/core/procedural/emitter/oracle.py` (`_emit_raise_error`, the
printf-substitution comment) · [`UNIQUE-1163`](../reference/warnings.md#unique-1163)
(the MySQL leg's own substitution-args-dropped warning, for contrast).

### EXEC / routine-call expression argument (Oracle) → synthesized variable (T-SQL)

**Problem.** A T-SQL `EXEC` call accepts only a literal, a variable, or
`DEFAULT`/`NULL` in its argument list — never an arbitrary expression. An
Oracle call passing `SYSDATE`, or any other expression, as a named-association
argument (`PRC(V_ID=>1, V_modstamp=>SYSDATE)`) has no legal T-SQL spelling
inline.

**Solution.** The expression is hoisted into a synthesized variable declared
immediately before the `EXEC`, and the call itself passes only that
variable. A `GETDATE()`/`SYSDATETIME()`/`SYSUTCDATETIME()` value (the
Oracle-source `SYSDATE` case) gets its own dedicated `@uq_nowN DATETIME`
variable:

```sql
-- tests/integration/test_oracle_source_m4_wave.py::TestWave12And13Classes::test_exec_expression_argument_hoisted
BEGIN
    PRC_MED_INS(V_ID=>1, V_modstamp=>SYSDATE);
END;
-- oracle -> tsql:
DECLARE @uq_now1 DATETIME = GETDATE();
EXEC PRC_MED_INS @V_ID = 1, @V_modstamp = @uq_now1;
```

A general (non-`now()`) expression argument hoists the same way, into a
variable typed from the callee's own declared parameter type where it can be
resolved (`_hoist_exec_expression_args`), rather than being restricted to
the date-function case.

**Discussion.** T-SQL's `EXEC`/`EXECUTE` call syntax is simply stricter than
Oracle's named-association call, which accepts any expression directly. As
with the `RAISERROR` message hoist above, an expression argument has to be
evaluated into a variable *before* the call, in a separate statement, since
there is no argument-position syntax in T-SQL that would accept it inline.

> **Note** faithful — the hoisted variable holds exactly the value the
> inline expression would have evaluated to at the same point in the routine
> (same evaluation order, immediately before the call). No warning.

**See Also.** [`TestWave12And13Classes`](../../tests/integration/test_oracle_source_m4_wave.py) ·
`src/unique/core/procedural/emitter/tsql.py` (`_emit_call`,
`_hoist_exec_expression_args`, docstrings) — no dedicated challenge-corpus
case exercises the expression-argument hoist, so the example above is drawn
from that dedicated integration test.

## Dynamic SQL constant translation

### A constant dynamic-SQL string (T-SQL `EXEC sp_executesql` / Oracle `EXECUTE IMMEDIATE` / PL/pgSQL `EXECUTE`) → any target

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

A **constant** dynamic-SQL string is run back through
the regular transpilation pipeline and the translated text is spliced back
into the string literal, so the target engine executes its own dialect at
runtime (nested translation capped at depth 2, warned beyond). A string
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

**See Also.** [`pg-dyn-count`](../../tests/fixtures/challenge/challenge_postgresql.sql), [`pg-format-func`](../../tests/fixtures/challenge/challenge_postgresql.sql), [`ts-sp-executesql`](../../tests/fixtures/challenge/challenge_sqlserver.sql) ·
[§6](../03-unsupported.md) (Dynamic SQL, audit N10/B11, 2026-07-25) ·
[`UNIQUE-1161`](../reference/warnings.md#unique-1161) ·
[`UNIQUE-1180`](../reference/warnings.md#unique-1180).

## Other `[limit]` procedural entries

### Scroll cursor `FETCH PRIOR/FIRST/LAST/ABSOLUTE/RELATIVE` (T-SQL) → Oracle / PostgreSQL / MySQL

**Problem.** A T-SQL `SCROLL` cursor supports non-forward fetches:
`FETCH LAST`, `FETCH PRIOR`, `FETCH ABSOLUTE n`, etc.

**Solution.**

```sql
-- corpus case ts-scroll-cursor
CREATE PROCEDURE p AS BEGIN
  DECLARE c CURSOR LOCAL SCROLL FOR SELECT 1;
  OPEN c; FETCH LAST FROM c; CLOSE c; DEALLOCATE c;
END
```

The scroll fetch itself degrades to a carrier
comment; the surrounding `OPEN`/`CLOSE`/`DEALLOCATE` still compile normally.

**Discussion.** Oracle, PostgreSQL and MySQL cursors are
**forward-only** — only `FETCH NEXT` exists — so a non-forward fetch has no
equivalent operation to translate to.

> **Warning** `[limit]` — approved degrade.

**See Also.** [`ts-scroll-cursor`](../../tests/fixtures/challenge/challenge_sqlserver.sql) · [§2](../03-unsupported.md) (scroll
cursor row).

## Comments written before a routine header

**Problem.** You annotate a routine from the outside — `-- author note`
lines immediately before `CREATE PROCEDURE` — and expect them to survive
the migration. On Oracle, trivia sitting *outside* the `CREATE OR REPLACE`
unit is at the mercy of script tooling: SQL*Plus splits units on `/`, and
comments stranded between units are silently discarded by several
execution paths.

**Solution.** Unique relocates leading comments *into* the routine's
declaration section, where every target's body protects them:

```sql
-- Calculates monthly totals for reporting.
CREATE PROCEDURE get_totals AS BEGIN SELECT 1; END
-- => (Oracle)
CREATE OR REPLACE PROCEDURE get_totals (...) IS
    -- Calculates monthly totals for reporting.
BEGIN ...
```

**Discussion.** Comments are trivia to the transpiler's semantics, but they
are the *author's* content — dropping them silently would violate the
no-silent-loss rule for the one artifact a human reads. Placing them at the
top of the declaration section is the only position that is safe on every
target's execution model (Oracle unit splitting, PostgreSQL `$$` bodies,
MySQL `DELIMITER` blocks).

> **Note** faithful — content preserved verbatim; only the position moves
> (from before the header to the top of the declaration section).

**See Also.** [`TestLeadingCommentRelocation`](../../tests/integration/test_procedural.py) ·
[05-procedural-engine.md](../05-procedural-engine.md) (lexer: comments as tokens).

## Triggers

The firing-mode surface that differs between engines: row-level (`FOR EACH
ROW`, `NEW`/`OLD`) vs. statement-level (T-SQL's `inserted`/`deleted`),
timing (`INSTEAD OF`), and each engine's own trigger-declaration shape. A
**purely** set-based T-SQL trigger (reads `inserted`/`deleted` only via
`FROM`/`JOIN`, no row-level qualifier or `UPDATE(col)` predicate) rewriting
to a PostgreSQL statement-level trigger with named transition tables — the
one case in this family already documented — is covered in
[§6](../03-unsupported.md) ("Set-based trigger pseudo-tables"), not
repeated here; the entries below cover the rest of the family.

### Row-level trigger body (`SET NEW.col = expr`) → T-SQL statement-level `UPDATE ... WHERE ... IN (SELECT ... FROM inserted)`

**Problem.** A MySQL/PL-SQL row-level trigger (`FOR EACH ROW`) runs once per
affected row, with `NEW`/`OLD` bound to that single row. T-SQL has no
row-level trigger at all — every trigger is statement-level, and the only
per-row surface it exposes is the `inserted`/`deleted` pseudo-tables holding
the *whole* affected batch.

**Solution.**

```sql
-- tests/integration/test_triggers.py::TestRowLevelTriggerToTSql::test_new_assignment_becomes_setbased_update
CREATE TRIGGER t BEFORE INSERT ON invoice_line FOR EACH ROW
BEGIN
    SET NEW.line_total = NEW.qty * NEW.unit_price;
END
-- mysql -> tsql:
CREATE TRIGGER t ON invoice_line
AFTER INSERT
AS
BEGIN
    UPDATE invoice_line SET line_total = qty * unit_price WHERE id IN (SELECT id FROM inserted);
END
```

A per-row assignment against the trigger's own table becomes a single
`UPDATE` keyed on the primary key of every row in `inserted`. When the body
updates a *different* table via a foreign key
(`test_embedded_update_keyed_on_new_fk_scoped_to_inserted`), the same
scoping happens through the correlated subquery instead:

```sql
-- mysql -> tsql
UPDATE invoice SET total = (SELECT COALESCE(SUM(il.line_total), 0)
    FROM invoice_line il WHERE il.invoice_id = invoice.id)
WHERE invoice.id IN (SELECT invoice_id FROM inserted);
```

(the T-SQL `UPDATE ... FROM` form takes no alias on the *target* table, so
the correlation is re-qualified against the bare table name.)

**Discussion.** MySQL's `BEFORE INSERT` fires once per row and mutates only
that row's `NEW`; T-SQL's `AFTER INSERT` fires once per **statement** and
only ever sees the `inserted` set as a whole, so the row-level assignment
has to become a set operation scoped to that set before it can run at all.

> **Note** faithful when the per-row expression reads only that row's own
> `NEW`/`OLD` values (no cross-row dependency): the set-based `UPDATE`
> recomputes every affected row independently in one pass, which is what N
> per-row firings would have produced anyway.
> **Warning** if the same target table carries its **own** downstream
> trigger, firing counts diverge: MySQL's row-level trigger fires that
> downstream trigger once per originating row (N times for a batch of N rows
> sharing one FK target), while the collapsed T-SQL statement fires it once
> per **distinct** key touched by the single `UPDATE` — a batch of 5
> `invoice_line` inserts for the same invoice fires a downstream `invoice`
> trigger 5 times on MySQL but once on T-SQL.

**See Also.** [`TestRowLevelTriggerToTSql`](../../tests/integration/test_triggers.py) ·
[`test_new_assignment_inside_if_converts_to_setbased`](../../tests/integration/test_trigger_predicates_scheduler.py)
(the same rewrite recursing into an `IF` body).

### Oracle event predicates (`INSERTING`/`DELETING`/`UPDATING('col')`) → per-engine rewrite

**Problem.** An Oracle trigger body asks, inline, "did this statement
INSERT/DELETE/UPDATE, and did this specific column change" via
`INSERTING`/`DELETING`/`UPDATING('col')`. No other engine spells the same
question the same way, and MySQL triggers cannot even ask it — a MySQL
trigger fires on exactly one event.

**Solution.**

```sql
-- tests/integration/test_trigger_predicates_scheduler.py::test_inserting_deleting_predicates_map_to_tsql
CREATE OR REPLACE TRIGGER trg1 AFTER INSERT OR DELETE ON t1 FOR EACH ROW
BEGIN
  IF INSERTING THEN INSERT INTO log_t (op) VALUES ('I'); END IF;
  IF DELETING THEN INSERT INTO log_t (op) VALUES ('D'); END IF;
END;
-- oracle -> tsql:
IF (EXISTS (SELECT 1 FROM inserted) AND NOT EXISTS (SELECT 1 FROM deleted))
BEGIN
    INSERT INTO log_t (op) VALUES ('I');
END
IF (EXISTS (SELECT 1 FROM deleted) AND NOT EXISTS (SELECT 1 FROM inserted))
BEGIN
    INSERT INTO log_t (op) VALUES ('D');
END
```

```sql
-- tests/integration/test_oracle_source_m4_wave.py::TestEventPredicates — IF UPDATING('estado') THEN ...
-- oracle -> postgresql:
IF (TG_OP = 'UPDATE' AND NEW.estado IS DISTINCT FROM OLD.estado) THEN ...
-- oracle -> mysql: the body is statically DUPLICATED once per event (trg_m ->
-- trg_m_ins + trg_m_upd), each copy's own-event predicate folded to a constant
-- instead of tested at runtime:
--   trg_m_ins: IF (1 = 1) THEN ...        -- INSERTING folds true here
--              IF (1 = 0) THEN ...        -- UPDATING('estado') folds false here
--   trg_m_upd: IF (1 = 0) THEN ...        -- INSERTING folds false here
--              IF (NOT (NEW.estado <=> OLD.estado)) THEN ...
```

The reverse direction — T-SQL's `UPDATE(col)` predicate read into every
engine — is the same mechanism read backwards:

```sql
-- tests/integration/test_triggers.py::TestTriggerUpdatePredicate
IF UPDATE(col_32) BEGIN INSERT INTO dbo.log (a) VALUES (1) END
-- tsql -> postgresql:  NEW.col_32 IS DISTINCT FROM OLD.col_32
-- tsql -> mysql:        NOT (NEW.col_32 <=> OLD.col_32)
-- tsql -> oracle:       UPDATING('col_32')
```

**Discussion.** `INSERTING`/`DELETING` describe which pseudo-table has rows
this firing, which T-SQL restates as an existence test against the
`inserted`/`deleted` tables the rest of the trigger already uses.
`UPDATING('col')` and T-SQL's `UPDATE(col)` both ask "did this column's
value actually change on this row" (not merely "was it in the `SET` list"),
which PostgreSQL/MySQL have no keyword for at all — Unique expands it to an
explicit `NEW.col IS DISTINCT FROM OLD.col` (PostgreSQL's NULL-safe
comparison) or `NOT (NEW.col <=> OLD.col)` (MySQL's NULL-safe equality
operator, negated). MySQL's one-event-per-trigger restriction additionally
forces the whole body to be **duplicated per event** — one physical trigger
per event, each copy's own-event predicate folded to a compile-time constant
rather than tested — a structural change (one trigger becomes two, or more),
not a semantic one, since each copy only ever fires for its own event.

> **Note** faithful — each rewrite restates the same boolean question in the
> target's own syntax; unlike the row-level-body family above, these
> predicates only ever gate a body that already runs at the right
> granularity for its engine, so there is no firing-count divergence here.

**See Also.** [`test_inserting_deleting_predicates_map_to_tsql`](../../tests/integration/test_trigger_predicates_scheduler.py) ·
[`TestEventPredicates`](../../tests/integration/test_oracle_source_m4_wave.py) ·
[`TestTriggerUpdatePredicate`](../../tests/integration/test_triggers.py).

### Row-level trigger re-reading its own table (MySQL/PostgreSQL) ↔ Oracle `COMPOUND TRIGGER`

**Problem.** A row-level trigger that aggregates a parent row from its
children (`UPDATE invoice SET total = (SELECT SUM(...) FROM invoice_line
WHERE invoice_id = NEW.invoice_id) WHERE id = NEW.invoice_id`) re-reads the
table it's attached to. Oracle raises `ORA-04091` ("table is mutating") for
exactly this shape in a plain row-level trigger; MySQL and PostgreSQL have no
such restriction.

**Solution.** MySQL/PostgreSQL → Oracle synthesizes a `COMPOUND TRIGGER`:
collect the affected key per row in `AFTER EACH ROW`, re-aggregate once in
`AFTER STATEMENT`:

```sql
-- tests/integration/test_triggers.py::TestRowLevelReReadToOracleCompound::test_synthesizes_compound_trigger
CREATE TRIGGER trg_agg AFTER INSERT ON invoice_line FOR EACH ROW
BEGIN
    UPDATE invoice SET total = (SELECT COALESCE(SUM(line_total), 0)
        FROM invoice_line WHERE invoice_id = NEW.invoice_id)
    WHERE id = NEW.invoice_id;
END
-- mysql -> oracle:
CREATE OR REPLACE TRIGGER trg_agg
FOR INSERT ON invoice_line
COMPOUND TRIGGER
    TYPE unique_kt_1 IS TABLE OF invoice_line.invoice_id%TYPE INDEX BY PLS_INTEGER;
    unique_key_1 unique_kt_1;
    g_n PLS_INTEGER := 0;

    AFTER EACH ROW IS
    BEGIN
        g_n := g_n + 1;
        unique_key_1(g_n) := :NEW.invoice_id;
    END AFTER EACH ROW;

    AFTER STATEMENT IS
    BEGIN
        FOR unique_i IN 1 .. g_n LOOP
            UPDATE invoice SET total = (SELECT COALESCE(SUM(line_total), 0)
                FROM invoice_line WHERE invoice_id = unique_key_1(unique_i))
            WHERE id = unique_key_1(unique_i);
        END LOOP;
    END AFTER STATEMENT;
END;
/
```

The reverse conversion — an Oracle `COMPOUND TRIGGER` written this way, read
into a target where the mutating-table restriction doesn't exist — lowers
to a plain row-level trigger instead:

```sql
-- tests/integration/test_triggers.py::TestOracleCompoundTrigger::test_lowers_to_row_level_postgresql
-- oracle -> postgresql:
CREATE OR REPLACE FUNCTION trg_line_total_func()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    UPDATE invoice SET total = 0 WHERE id = NEW.invoice_id;
    RETURN NEW;
END;
$$;
CREATE OR REPLACE TRIGGER trg_line_total
AFTER INSERT OR UPDATE ON invoice_line
FOR EACH ROW EXECUTE FUNCTION trg_line_total_func();
```

MySQL keeps neither shape: it degrades to a documented carrier
(`test_degrades_to_carrier_mysql`) — MySQL has no compound-trigger
equivalent to lower to, and a mechanical row-level rewrite would reintroduce
the very mutating-read pattern Oracle forbids, so Unique documents rather
than guesses.

A row-level trigger that does **not** re-read its own table is left alone on
Oracle — no needless compound rewrite
(`test_non_self_referencing_row_trigger_stays_row_level`).

**Discussion.** Oracle's `AFTER STATEMENT` phase runs the aggregation
**once per statement**, however many rows were collected; the PostgreSQL
lowering runs it **once per row** instead (a plain `FOR EACH ROW` trigger),
since PostgreSQL has no equivalent phase separation. For a pure aggregate
read like this one, the *final* value after all firings is identical either
way (`COALESCE(SUM(...))` is idempotent under repetition), but a multi-row
batch recomputes and rewrites the parent row N times on PostgreSQL where
Oracle's compound form would have done it once.

> **Warning** the collapse from statement-batched to per-row execution is a
> firing-count divergence, not a value divergence: correct final data, but
> `invoice` is written — and any of *its own* triggers fire — once per
> `invoice_line` row instead of once per statement. `[limit]` (documented,
> not rewritten) on MySQL — no compound-trigger equivalent exists to lower
> to.

**See Also.** [`TestRowLevelReReadToOracleCompound`](../../tests/integration/test_triggers.py) ·
[`TestOracleCompoundTrigger`](../../tests/integration/test_triggers.py) ·
[`UNIQUE-1156`](../reference/warnings.md#unique-1156) ·
[`UNIQUE-1231`](../reference/warnings.md#unique-1231).

### T-SQL `INSTEAD OF` trigger → PostgreSQL (native on views, emulated on tables)

**Problem.** T-SQL allows `INSTEAD OF` on both views *and* base tables — the
trigger body runs **instead of** the attempted INSERT/UPDATE/DELETE, which is
never applied on its own. PostgreSQL's `INSTEAD OF` exists too, but **only**
on views (a table raises "... instead of triggers are only for views").

**Solution.** On a view, the mapping is direct:

```sql
-- corpus case ts-trigger-on-view
CREATE VIEW v AS SELECT id FROM t;
CREATE TRIGGER trg ON v INSTEAD OF INSERT AS BEGIN INSERT INTO t SELECT id FROM inserted; END
-- tsql -> postgresql:
CREATE OR REPLACE TRIGGER trg
INSTEAD OF INSERT ON v
FOR EACH ROW EXECUTE FUNCTION trg_func();
-- (trg_func() body: INSERT INTO t SELECT NEW.id; RETURN NEW;)
```

On a base table, PostgreSQL has nothing to map to at all, so Unique emulates
the "runs instead, never both" contract with a `BEFORE` row trigger plus a
`pg_trigger_depth()` guard: the body's own DML re-enters the same trigger one
level deeper, where the guard lets it through; the *original* attempted row
is always suppressed (`RETURN NULL`) at depth 1:

```sql
-- corpus case ts-instead-of-insert
CREATE TRIGGER trg ON t INSTEAD OF INSERT AS BEGIN INSERT INTO t (id, n) SELECT id, n FROM inserted; END
-- tsql -> postgresql:
CREATE OR REPLACE FUNCTION trg_func()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF pg_trigger_depth() > 1 THEN
        RETURN NEW;
    END IF;
    INSERT INTO t (id, n) SELECT NEW.id, NEW.n;
    RETURN NULL;
END;
$$;
CREATE OR REPLACE TRIGGER trg
BEFORE INSERT ON t
FOR EACH ROW EXECUTE FUNCTION trg_func();
```

A `DELETE` guard returns `OLD` (not `NEW`, which is `NULL` on `DELETE`) at
depth > 1, so the recursive delete is allowed through instead of silently
no-opping:

```sql
-- corpus case ts-trg-instead-delete
CREATE TRIGGER g ON t INSTEAD OF DELETE AS BEGIN DELETE FROM t WHERE id IN (SELECT id FROM deleted WHERE id>0); END
-- tsql -> postgresql:
IF pg_trigger_depth() > 1 THEN
    RETURN OLD;
END IF;
DELETE FROM t WHERE id IN (SELECT OLD.id WHERE OLD.id > 0);
RETURN NULL;
```

**Discussion.** PostgreSQL's row-level restriction (`FOR EACH ROW` only —
`INSTEAD OF` has no statement-level form in PostgreSQL) means the emulation
fires once per originating row, recursing once per row to perform its own
single-row insert/delete, where the source body's `SELECT ... FROM
inserted`/`deleted` was itself already a set read over the whole batch. The
final table contents match (every row in the batch is individually inserted
or deleted, under the same conditions), but the number of statement
executions against `t` differs from a literal reading of the T-SQL body: one
`INSERT ... SELECT ... FROM inserted` (one statement, whole batch) on T-SQL
becomes N recursive single-row inserts on PostgreSQL, one per row in the
batch.

> **Note** faithful in final result — live-verified exactly-once insertion
> per row and exact `id > 0` filtering on delete (2026-07-24) — but not
> execution-count faithful for a multi-row batch, per above.

**See Also.** [`ts-trigger-on-view`](../../tests/fixtures/challenge/challenge_sqlserver.sql), [`ts-instead-of-insert`](../../tests/fixtures/challenge/challenge_sqlserver.sql), [`ts-trg-instead-delete`](../../tests/fixtures/challenge/challenge_sqlserver.sql) ·
[`TestInsteadOfTriggers`](../../tests/integration/test_challenge.py) ·
[`UNIQUE-1182`](../reference/warnings.md#unique-1182).

### Trigger body → PostgreSQL `CREATE FUNCTION ... RETURNS TRIGGER` + `CREATE TRIGGER`

**Problem.** PostgreSQL has no inline trigger body: `CREATE TRIGGER` only
*names* a function, which must already exist and return `TRIGGER`. Every
other engine (T-SQL, Oracle, MySQL, SQLite) writes the body directly inside
`CREATE TRIGGER`.

**Solution.**

```sql
-- tests/integration/test_triggers.py::TestTriggerTiming::test_after_insert_postgresql_emits_function_and_trigger
CREATE TRIGGER trg ON dbo.t
AFTER INSERT
AS BEGIN UPDATE dbo.t SET n = 1 WHERE id = 1 END
-- tsql -> postgresql:
CREATE OR REPLACE FUNCTION trg_func()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    UPDATE t SET n = 1 WHERE id = 1;
    RETURN NEW;
END;
$$;
CREATE OR REPLACE TRIGGER trg
AFTER INSERT ON t
EXECUTE FUNCTION trg_func();
```

The same decomposition applies from any source dialect, including SQLite
(whose own trigger body sits inline, like MySQL's/Oracle's):

```python
# tests/unit/core/test_transpiler.py::test_sqlite_trigger_to_targets
trg = "CREATE TRIGGER trg AFTER INSERT ON orders FOR EACH ROW BEGIN " \
      "UPDATE stats SET total = total + NEW.amount WHERE id = NEW.cat_id; END"
# sqlite -> postgresql: CREATE FUNCTION trg_func() RETURNS TRIGGER ...; CREATE TRIGGER trg ... EXECUTE FUNCTION trg_func();
# sqlite -> oracle:     CREATE OR REPLACE TRIGGER trg ... BEGIN ... :NEW.amount ... END; / (body stays inline)
# sqlite -> mysql:      DELIMITER-wrapped CREATE TRIGGER trg ... NEW.amount ... (body stays inline)
```

**Discussion.** PostgreSQL's function/trigger split is a structural, not a
semantic, requirement — the function's body is exactly the trigger's body,
with a mandatory `RETURN NEW`/`RETURN OLD`/`RETURN NULL` added since a
plpgsql function must return a value of its declared type (`TRIGGER`),
which no other engine's inline body has an equivalent obligation for.

> **Note** faithful — same statements, split across two `CREATE` objects
> instead of one, with the return value synthesized to satisfy PostgreSQL's
> function-return contract.

**See Also.** [`TestTriggerTiming`](../../tests/integration/test_triggers.py) ·
[`test_sqlite_trigger_to_targets`](../../tests/unit/core/test_transpiler.py).

### Bare `RETURN;` inside a PostgreSQL trigger function's nested handler → `RETURN NEW;`

**Problem.** Oracle's bare `RETURN;` inside an exception handler simply
leaves the trigger (there is no return value to supply there). A PostgreSQL
trigger function must return a row of type `TRIGGER` from *every* code
path — a bare `RETURN;` there is `ERROR: 42601: missing expression`
(live-verified).

**Solution.**

```sql
-- tests/integration/test_oracle_source_m4_wave.py::TestBareReturnInPgTriggerFunction
CREATE OR REPLACE TRIGGER trg_r AFTER UPDATE ON t_e FOR EACH ROW
DECLARE v_x NUMBER;
BEGIN
  BEGIN
    SELECT a INTO v_x FROM t2 WHERE b = :NEW.id;
  EXCEPTION
    WHEN NO_DATA_FOUND THEN
      RETURN;
  END;
  UPDATE t3 SET c = v_x WHERE id = :NEW.id;
END;
-- oracle -> postgresql (inside the trigger function):
EXCEPTION
    WHEN no_data_found THEN
        RETURN NEW;
```

**Discussion.** The rewrite fills the bare `RETURN;` in with whatever the
enclosing function's own trailing default return would be — `NEW` for a
row-level trigger (the row-level convention for "let the operation proceed
unchanged"), `NULL` for a set-based/statement-level one — rather than a
fixed guess, since the correct value depends on the trigger's own
granularity, not on the `RETURN` statement itself.

> **Note** faithful — the early exit still leaves the rest of the trigger
> body unexecuted, exactly as Oracle's bare `RETURN;` does; only the value
> handed back changes, to satisfy PostgreSQL's return-type contract.

**See Also.** [`TestBareReturnInPgTriggerFunction`](../../tests/integration/test_oracle_source_m4_wave.py).

### Empty trigger body → synthesized `SET NOCOUNT ON;` no-op (T-SQL)

**Problem.** T-SQL forbids an empty statement block: `BEGIN END` alone after
a trigger header is a syntax error. Other engines allow an intentional no-op
body (`BEGIN END`, or one that only ever held comments before trivia is
stripped).

**Solution.**

```sql
-- tests/unit/core/test_ir_first_families.py::TestZeroPushZ4bBatch::test_empty_trigger_body_gets_executable_noop
CREATE TRIGGER t1_bu AFTER UPDATE ON t1 FOR EACH ROW BEGIN END
-- mysql -> tsql:
CREATE TRIGGER t1_bu ON t1
AFTER UPDATE
AS
BEGIN
    SET NOCOUNT ON;
END
```

**Discussion.** `SET NOCOUNT ON` is already Unique's standard filler for a
T-SQL routine body that would otherwise be empty (it suppresses the
row-count message and has no observable effect on data) — reused here
rather than inventing a trigger-specific placeholder.

> **Note** faithful — the trigger still fires and does nothing, matching the
> source's empty body; the only difference is the now-syntactically-required
> statement, which has no data effect.

**See Also.** [`TestZeroPushZ4bBatch`](../../tests/unit/core/test_ir_first_families.py) —
a related, weaker guard
(`TestZeroPushW5Batch::test_comment_only_trigger_body_gets_noop`) checks the
same invariant conditionally (*if* the emitted trigger body is comment-only,
it must also carry the no-op filler) rather than pinning a genuinely
comment-only source body — that test's own fixture body is not actually
comment-only (`CALL p1();`), so it is cited here for context, not as an
independent proof of the comment-only case.

## Topics left out for lack of source support

- **Ref cursor `OUT` parameters** (`SYS_REFCURSOR`) and **`EXECUTE IMMEDIATE
  … USING bind1, bind2`** Oracle→T-SQL specifics are documented in
  `docs/03-unsupported.md` §6, but no challenge-corpus case exercises either
  construct, so no dedicated entry is made here to avoid inventing an
  example.
