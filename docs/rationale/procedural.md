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

### PL/pgSQL implicit `FOUND` / Oracle implicit `SQL%FOUND` → T-SQL `@@ROWCOUNT` / MySQL `ROW_COUNT()`

**Problem.** PL/pgSQL keeps one implicit boolean, `FOUND`, updated by the
*last* `SELECT INTO`, `UPDATE`, `DELETE`, `INSERT`, or `FETCH` in the
routine — it answers "did that last statement affect/return a row?" for the
routine as a whole, not for one named cursor. Oracle's own implicit-cursor
attribute, bare `SQL%FOUND` (as opposed to a named cursor's `c%FOUND`
covered above), asks the identical question about the routine's last
implicit DML statement.

**Solution.**

```python
# tests/unit/core/test_ir_first_families.py::TestPgFoundFlagInIr
_ir("postgresql", "tsql", "SELECT CASE WHEN FOUND THEN 1 ELSE 2 END")
# -> ... CASE WHEN (@@ROWCOUNT > 0) THEN 1 ELSE 2 END ...

_ir("postgresql", "oracle", "SELECT CASE WHEN FOUND THEN 1 ELSE 2 END")
# -> ... CASE WHEN SQL%FOUND THEN 1 ELSE 2 END ...

_ir("postgresql", "mysql", "SELECT CASE WHEN FOUND THEN 1 ELSE 2 END")
# -> ... CASE WHEN (ROW_COUNT() > 0) THEN 1 ELSE 2 END ...
```

The reverse direction reads the same way: Oracle's bare `SQL%FOUND` /
`SQL%NOTFOUND` map onto T-SQL's `@@ROWCOUNT > 0` / `= 0` and onto
PostgreSQL's own `FOUND`
(`tests/unit/core/test_ir_first_families.py::TestOracleCursorAttrsInIr`).
A bare column named `found` from a source with no such implicit flag (e.g.
MySQL) is left untouched — the rewrite only fires for the dialect's actual
implicit-cursor keyword, never for an identifier that merely shares its
spelling
(`TestPgFoundFlagInIr::test_found_column_untouched_from_other_sources`).

**Discussion.** Unlike a *named* cursor's `%FOUND` above — which needs
per-cursor state because T-SQL/MySQL only expose one shared mechanism — the
implicit flag is already routine-global on every engine: PostgreSQL's
`FOUND`, Oracle's `SQL%FOUND`, T-SQL's `@@ROWCOUNT`, and MySQL's
`ROW_COUNT()` all describe "the last statement," so the mapping is a direct
rename with no per-target state to synthesize. This is why the entry sits
here, next to the named-cursor-attribute mapping, rather than under "Loop
and cursor desugaring" below — it is a value-position attribute rename, not
a control-flow expansion.

> **Note** faithful — same "did the last statement touch a row" question,
> restated in each target's own implicit-state syntax.

**See Also.** [`TestPgFoundFlagInIr`](../../tests/unit/core/test_ir_first_families.py), [`TestOracleCursorAttrsInIr`](../../tests/unit/core/test_ir_first_families.py) ·
[§3.22](../03-unsupported.md) (the related `SQL%ROWCOUNT` "matched vs.
changed" divergence), [§3.23](../03-unsupported.md).

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

## Loop and cursor desugaring

T-SQL cursor *variables*, PL/SQL/Oracle cursor `FOR` loops, and numeric
range `FOR` loops all bind their query/bounds and their iteration into a
single declarative statement. Every one of MySQL's, T-SQL's, and (for the
numeric case) MySQL's/T-SQL's own procedural dialects requires the
equivalent to be spelled out as an explicit sequence: declare, open/fetch,
test, loop, close — so Unique expands the single source construct into that
target-specific scaffold. This is distinct from the cursor *attribute*
mapping above (which rewrites a value-position flag with no control-flow
change); every entry here changes the statement shape itself.

### T-SQL cursor-variable binding (`SET @cur = CURSOR ... FOR q; OPEN @cur;`) → PostgreSQL / Oracle / MySQL

**Problem.** T-SQL lets a cursor be bound to a *variable* in two steps: a
bare `DECLARE @cur CURSOR;` (no query yet), then `SET @cur = CURSOR ... FOR
<query>` to attach the query, then a bare `OPEN @cur;`. Read literally
across engines, this looks like an assignment statement plus a separate
open — but PostgreSQL/Oracle refcursors and MySQL's own cursor syntax only
ever open a cursor *with* its query in one step.

**Solution.**

```sql
-- tests/integration/test_cursor_variable_binding.py (_CURSOR_VAR_SRC)
CREATE PROCEDURE dbo.p9 AS
BEGIN
  DECLARE @cur CURSOR;
  DECLARE @id INT;
  SET @cur = CURSOR LOCAL FAST_FORWARD FOR SELECT id FROM t1;
  OPEN @cur;
  FETCH NEXT FROM @cur INTO @id;
  CLOSE @cur;
  DEALLOCATE @cur;
END
```

```sql
-- tsql -> postgresql
CREATE OR REPLACE PROCEDURE p9()
LANGUAGE plpgsql
AS $$
DECLARE
    v_cur REFCURSOR;
    v_id INTEGER;
BEGIN
    OPEN v_cur FOR
    SELECT id FROM t1;
    NULL;
    FETCH v_cur INTO v_id;
    CLOSE v_cur;
    -- DEALLOCATE not needed in postgresql
END;
$$;
```

```sql
-- tsql -> mysql (MySQL has no cursor variables: the query moves onto the
-- declaration itself, and the bare OPEN is where it actually runs)
DELIMITER $$
CREATE PROCEDURE p9()
BEGIN
    DECLARE v_id INT;
    DECLARE v_cur CURSOR FOR SELECT id FROM t1;

    OPEN v_cur;
    FETCH v_cur INTO v_id;
    CLOSE v_cur;
    -- DEALLOCATE not needed in mysql
END$$
DELIMITER ;
```

`SET @cur = CURSOR ... FOR <query>` is folded into the `REFCURSOR`/
`SYS_REFCURSOR` declaration's `OPEN ... FOR <query>` (PostgreSQL/Oracle) or
into the `DECLARE ... CURSOR FOR <query>` itself (MySQL); the subsequent
bare `OPEN` — which, on the source, is what actually runs the query — has
nothing left to do on PostgreSQL/Oracle (the `OPEN ... FOR` already ran it),
so it is emitted as a `NULL;` no-op statement rather than re-opening the
cursor a second time, while on MySQL it stays as the real `OPEN`, since that
is where MySQL's own cursor first executes its query.

**Discussion.** PostgreSQL and Oracle refcursors, and MySQL's own cursor
declarations, only support "declare-with-query" or "open-with-query" as a
single step — there is no analogue to T-SQL's separate variable-then-`SET`
binding. Preserving the two-step shape literally (a separate assignment,
then a second, independent `OPEN`) would either not parse (a cursor
variable cannot be assigned like a scalar) or double-open the cursor.

> **Note** faithful — one cursor, opened exactly once, on every target; the
> `tsql -> tsql` identity keeps the original two-statement form verbatim
> (`test_cursor_variable_tsql_identity_keeps_variable_form`), confirming the
> merge is target-specific rather than a lossy parse of the source.

**See Also.** [`test_cursor_variable_to_postgresql_opens_for_query`, `test_cursor_variable_to_oracle_opens_for_query`, `test_cursor_variable_to_mysql_merges_query_into_declaration`](../../tests/integration/test_cursor_variable_binding.py) —
no dedicated challenge-corpus case exercises cursor variables, so the
example above is drawn from that dedicated integration test.

### PL/SQL `FOR rec IN cur LOOP` (Oracle) → T-SQL explicit cursor scaffold

**Problem.** A PL/SQL cursor `FOR` loop declares nothing: it implicitly
opens the cursor, fetches one row per iteration into a record `rec`, and
closes it when the cursor is exhausted — `rec.col` reads that iteration's
column. T-SQL has no such implicit record-fetch loop at all.

**Solution.**

```sql
-- tests/integration/test_cursor_for_loop_tsql.py (_NAMED)
DECLARE
  v_total NUMBER := 0;
  CURSOR cur1 IS SELECT id, amount, name FROM src_t WHERE flag = 1;
BEGIN
  FOR rec IN cur1 LOOP
    IF rec.amount > 0 THEN
      INSERT INTO dst_t (id, label) VALUES (rec.id, rec.name || '!');
    END IF;
    v_total := v_total + rec.amount;
  END LOOP;
END;
/
-- oracle -> tsql:
DECLARE @total DECIMAL = 0;
DECLARE cur1 CURSOR LOCAL FAST_FORWARD FOR SELECT id, amount, name FROM src_t WHERE flag = 1;
-- UNIQUE-1187: cursor FOR-loop expanded; loop variables are NVARCHAR(4000) (exact column types need --db-url metadata).
DECLARE @rec_id NVARCHAR(4000), @rec_amount NVARCHAR(4000), @rec_name NVARCHAR(4000);
OPEN cur1;
FETCH NEXT FROM cur1 INTO @rec_id, @rec_amount, @rec_name;
WHILE @@FETCH_STATUS = 0
BEGIN
    IF @rec_amount > 0
    BEGIN
            INSERT INTO dst_t (id, label) VALUES (@rec_id, @rec_name + '!');
    END
    SET @total = @total + @rec_amount;
FETCH NEXT FROM cur1 INTO @rec_id, @rec_amount, @rec_name;
END;
CLOSE cur1;
DEALLOCATE cur1;
```

The loop expands into a complete `DECLARE`/`OPEN`/positional
`FETCH ... INTO`/`WHILE @@FETCH_STATUS = 0`/`CLOSE`/`DEALLOCATE` scaffold,
one `@rec_<col>` variable per selected column, with every `rec.col`
reference in the body rewritten to the matching `@rec_col`, and the
re-fetch duplicated at the bottom of the loop body (T-SQL's `WHILE` tests
*before* each iteration, unlike PL/SQL's implicit post-fetch test). The same
expansion applies to an inline cursor query
(`test_inline_query_loop_expands_completely`: `FOR r IN (SELECT a, b FROM t
...) LOOP`).

**Discussion.** T-SQL cursors are opened, fetched, and tested for
`@@FETCH_STATUS` as three separate statements — there is no single
statement that both advances a cursor and binds a whole row to a
record-like variable the way PL/SQL's `FOR ... IN cursor LOOP` does, so the
implicit fetch-and-bind has to be made explicit, one scalar variable per
column. Without `--db-url` metadata, Unique does not know each selected
column's real type, so every `@rec_<col>` is declared as the permissive
`NVARCHAR(4000)` (`UNIQUE-1187`) rather than the column's actual type. When
the select list is *not* statically resolvable (e.g. `SELECT *` with no
visible schema), Unique cannot generate the per-column variable list at
all, and falls back to the previously-documented scaffold with a
placeholder `FETCH ... INTO /* col1, ... */` for the developer to complete
(`test_unresolvable_select_star_keeps_documented_scaffold`, `UNIQUE-1174`) —
warned, never guessed.

> **Warning** `[limit]` without `--db-url` — loop variables are
> `NVARCHAR(4000)`, not the column's real type; the loop's control flow,
> `rec.col` rewriting, and FETCH positions are otherwise complete and
> faithful. `[limit]` (documented scaffold, not expanded) when the column
> list cannot be resolved at all.

**See Also.** [`test_named_cursor_loop_expands_completely`, `test_inline_query_loop_expands_completely`, `test_unresolvable_select_star_keeps_documented_scaffold`](../../tests/integration/test_cursor_for_loop_tsql.py) ·
[`UNIQUE-1187`](../reference/warnings.md#unique-1187) ·
[`UNIQUE-1174`](../reference/warnings.md#unique-1174) — no dedicated
challenge-corpus case exercises the named-cursor `FOR` loop, so the example
above is drawn from that dedicated integration test.

### PL/SQL cursor `FOR` loop (Oracle) → MySQL explicit cursor scaffold

**Problem.** The same implicit fetch-and-bind PL/SQL construct as above, but
onto MySQL, whose procedural dialect additionally requires every `DECLARE`
to sit at the very top of its enclosing `BEGIN` block (MySQL error 1337)
and has no `WHILE @@FETCH_STATUS` equivalent — loop termination is driven by
a `CONTINUE HANDLER FOR NOT FOUND`.

**Solution.**

```sql
-- tests/integration/test_oracle_mysql_tail.py::TestMySqlCursorForLoopExpansion (_NAMED)
create or replace PROCEDURE p_cur AS
  CURSOR curES IS SELECT accion, codigo AS codpostal FROM t_dir;
BEGIN
  FOR r IN curES LOOP
    INSERT INTO t_out (a, b) VALUES (r.accion, r.codpostal);
  END LOOP;
END;
/
-- oracle -> mysql:
DELIMITER $$
CREATE PROCEDURE p_cur()
BEGIN
    DECLARE curES CURSOR FOR SELECT accion, codigo AS codpostal FROM t_dir;

    -- UNIQUE-1175: cursor FOR-loop expanded; loop variables are TEXT (exact column types need --db-url metadata).
    BEGIN
        DECLARE r_accion TEXT;
        DECLARE r_codpostal TEXT;
        DECLARE r_done INT DEFAULT FALSE;
        DECLARE CONTINUE HANDLER FOR NOT FOUND SET r_done = TRUE;
        OPEN curES;
        r_loop: LOOP
            FETCH curES INTO r_accion, r_codpostal;
            IF r_done THEN LEAVE r_loop; END IF;
            INSERT INTO t_out (a, b) VALUES (r_accion, r_codpostal);
        END LOOP;
        CLOSE curES;
    END;
END$$
DELIMITER ;
```

The expansion opens a **new nested block** so its per-column `DECLARE`s and
the `CONTINUE HANDLER` are legal at that block's own top (they cannot be
injected into the outer procedure's declaration section, since the loop
variables are scoped to the loop). Each generated loop carries its own
unique label (`r_loop`) so nested cursor loops never collide (MySQL error
1309, "redefining label"). An inline (unnamed) cursor query desugars the
same way, folding its `SELECT` directly into a synthesized
`DECLARE r_cur CURSOR FOR <query>`
(`test_inline_query_expands_completely`), and an unresolvable `SELECT *`
falls back to the documented placeholder scaffold exactly as in the T-SQL
case above (`test_unresolvable_list_keeps_documented_scaffold`,
`UNIQUE-1174`).

**Discussion.** MySQL cursor control flow is built entirely from
declarations, an explicit `LOOP`, and a `NOT FOUND` handler flag that must
be checked after each `FETCH` — there is no statement that fetches into a
whole record and tests exhaustion in one step, so the same rec-to-scalars
expansion as the T-SQL entry above is required, plus MySQL's own
declaration-ordering and block-scoping rules.

> **Warning** `[limit]` without `--db-url` — loop variables are `TEXT`, not
> the column's real type; the loop's control flow and FETCH positions are
> otherwise complete and faithful. `[limit]` (documented scaffold) when the
> column list cannot be resolved.

**See Also.** [`TestMySqlCursorForLoopExpansion`](../../tests/integration/test_oracle_mysql_tail.py) ·
[`UNIQUE-1175`](../reference/warnings.md#unique-1175) ·
[`UNIQUE-1174`](../reference/warnings.md#unique-1174).

### Numeric range `FOR i IN a..b LOOP` (Oracle) → MySQL / T-SQL explicit `WHILE` + counter

**Problem.** `FOR i IN 1..13 LOOP` (optionally `REVERSE`) is Oracle's
counting loop — no cursor at all, just an integer range. Read at the
`DECLARE ... CURSOR FOR 1..13`-shaped patch this used to fall through to,
`1..13` is not a query, so it produced invalid SQL (MySQL error 1064).
MySQL/T-SQL have no native counting-`FOR` construct, so it has to become an
explicit `WHILE` loop with its own counter.

**Solution.**

```sql
-- tests/integration/test_oracle_mysql_tail.py::TestNumericRangeForLoop
create or replace PROCEDURE p_rng AS BEGIN
  FOR i IN 1..13 LOOP
    INSERT INTO t (a) VALUES (i);
  END LOOP;
END;
/
-- oracle -> mysql:
DELIMITER $$
CREATE PROCEDURE p_rng()
BEGIN
    BEGIN
        DECLARE i INT DEFAULT 1;
        WHILE i <= 13 DO
            INSERT INTO t (a) VALUES (i);
            SET i = i + 1;
        END WHILE;
    END;
END$$
DELIMITER ;
-- oracle -> tsql:
DECLARE @i INT = 1;
WHILE @i <= 13
BEGIN
        INSERT INTO t (a) VALUES (@i);
    SET @i = @i + 1;
END;
```

`FOR i IN REVERSE 1..13 LOOP` counts down instead: MySQL/T-SQL get
`DECLARE i INT DEFAULT 13;` / `WHILE i >= 1` / `SET i = i - 1`
(`test_reverse_range_mysql_counts_down`). PostgreSQL and Oracle itself keep
the native `FOR i IN 1..13 LOOP` form unchanged
(`test_postgresql_keeps_native_range_loop`,
`test_oracle_identity_keeps_range_loop`), since both support the construct
directly.

**Discussion.** PostgreSQL and Oracle both have a native integer-range `FOR`
loop; MySQL and T-SQL do not, so counting has to be made explicit — a
`DECLARE`d counter, a `WHILE` bound test, and an explicit increment/decrement
after the body, mirroring exactly what the implicit range loop does
internally.

> **Note** faithful — same iteration count and bound values on every
> target; no warning, since a `WHILE` + counter reproduces the range loop
> exactly (no per-column typing uncertainty is involved here, unlike the
> cursor loops above).

**See Also.** [`TestNumericRangeForLoop`](../../tests/integration/test_oracle_mysql_tail.py) —
no dedicated challenge-corpus case exercises the numeric range loop, so the
example above is drawn from that dedicated integration test.

### Bare `RETURN` in a MySQL procedure → labeled `proc_exit:` block + `LEAVE`

**Problem.** MySQL forbids `RETURN` anywhere inside a `PROCEDURE` body
("RETURN is only allowed in a FUNCTION") — but an early-exit bare `RETURN`
(no value) is ordinary control flow in T-SQL/Oracle/PostgreSQL procedures.

**Solution.**

```sql
-- tests/integration/test_procedural.py::TestBareReturnInProcedure
CREATE PROCEDURE dbo.p @x INT AS BEGIN IF @x < 0 RETURN SELECT @x END
-- tsql -> mysql:
DELIMITER $$
CREATE PROCEDURE p
(
    IN v_x INT
)
proc_exit: BEGIN
    IF v_x < 0 THEN
            LEAVE proc_exit;
    END IF;
    SELECT v_x;
END$$
DELIMITER ;
```

The whole procedure body is wrapped in a label (`proc_exit:`), and every
bare `RETURN` becomes `LEAVE proc_exit;` — jumping to the end of the labeled
block exactly as `RETURN` would exit the procedure. The label is only added
when a bare `RETURN` is actually present
(`test_no_label_when_no_bare_return`); Oracle/PostgreSQL keep the plain
`RETURN;` unchanged, since neither restricts it to functions
(`test_oracle_keeps_plain_return`). The statement immediately following the
bare `RETURN` (here, `SELECT @x`) survives as its own statement rather than
being absorbed into the conditional
(`test_following_statement_not_absorbed`). The same rewrite applies to a
bare `RETURN;` nested inside an exception handler *inside* the procedure
body — a `BEGIN ... EXCEPTION ... END` block's own `RETURN;` still targets
the outer procedure's `proc_exit:` label, not a handler-local one, and the
same holds for a bare `RETURN;` inside a MySQL trigger's nested handler
(triggers have no `proc_exit`-style value to discard, so the label alone is
enough):

```sql
-- tests/integration/test_oracle_mysql_tail.py::TestMySqlReturnBecomesLeave (_PROC)
create or replace PROCEDURE p_ex(p_no IN NUMBER, p_out OUT VARCHAR2)
AS BEGIN
  BEGIN
    SELECT c INTO p_out FROM t WHERE a = p_no;
  EXCEPTION
    WHEN NO_DATA_FOUND THEN
      p_out := 'x';
      RETURN;
  END;
  UPDATE t SET c = p_out WHERE a = p_no;
END;
/
-- oracle -> mysql: nested handler's RETURN -> LEAVE proc_exit; (and the
-- outer UPDATE still runs when the handler is NOT triggered)
```

A `RETURN <value>` inside a T-SQL/Oracle *procedure* (as opposed to a bare
`RETURN`) is a status-code return — something MySQL procedures have no
mechanism for at all — so it becomes `LEAVE proc_exit;` too, with the
discarded value named in an inline comment plus a warning:

```sql
-- tests/integration/test_procedural.py::TestReturnValueInProcedure
CREATE PROCEDURE dbo.p @x INT AS BEGIN IF @x IS NULL RETURN NULL; SELECT @x; END
-- tsql -> mysql:
proc_exit: BEGIN
    IF v_x IS NULL THEN
            LEAVE proc_exit;  -- UNIQUE-1177: discarded procedure RETURN value (NULL)
    END IF;
    SELECT v_x;
END$$
```

A `RETURN <value>` inside a *function*, by contrast, is unaffected on any
target — MySQL functions can return values, so it is kept as a plain
`RETURN <value>;`, with no label needed at all
(`test_return_value_in_function_kept`).

The example above adds an explicit `;` between `RETURN NULL` and the
following `SELECT @x` — a deliberate deviation from
`TestReturnValueInProcedure`'s own literal source string, which omits it
(`"IF @x IS NULL RETURN NULL " "SELECT @x " "END"`, relying on T-SQL's
optional-semicolon, keyword-boundary statement splitting). Probing that
exact string surfaced a real gap: without the `;`, the expression capture
for a value-bearing `RETURN` does not stop at the next statement-starting
keyword the way the bare (no-value) `RETURN` case does — the following
`SELECT @x` is swallowed whole into the discarded-value comment
(`-- UNIQUE-1177: discarded procedure RETURN value (NULL SELECT v_x)`) and
never appears as its own statement, a silent loss the pinning test does not
assert against (unlike the bare-`RETURN` case's
`test_following_statement_not_absorbed`). This is flagged here rather than
documented as faithful; see the handoff report for the corpus/test
reference to hand to a future BLUE pass.

**Discussion.** MySQL's restriction is structural, not just stylistic — a
bare `RETURN` inside a `PROCEDURE` body is a parse error, so there is no
"leave it as-is" option the way Oracle/PostgreSQL/T-SQL allow. A label +
`LEAVE` is MySQL's own idiom for "jump to the end of this block," which is
exactly what an early-exit `RETURN` needs; wrapping the *whole* body in one
label lets every `RETURN`, however deeply nested inside `IF`s or exception
handlers, target the same exit point.

> **Note** faithful for a bare `RETURN` — the following statement is
> preserved, and control still exits at the same point.
> **Warning** `[limit]` for `RETURN <value>` inside a procedure — MySQL has
> no slot to put a procedure's returned status code in, so the value is
> documented in a comment rather than returned; a caller relying on that
> status code must be rewritten to use an `OUT` parameter instead.

**See Also.** [`TestBareReturnInProcedure`, `TestReturnValueInProcedure`](../../tests/integration/test_procedural.py), [`TestMySqlReturnBecomesLeave`](../../tests/integration/test_oracle_mysql_tail.py) ·
[`UNIQUE-1177`](../reference/warnings.md#unique-1177) — no dedicated
challenge-corpus case exercises bare `RETURN`/`LEAVE`, so the examples above
are drawn from those dedicated integration tests.

### Leading `DECLARE` block reordered (MySQL): variables before cursors

**Problem.** MySQL requires every `DECLARE <cursor>` to come *after* every
`DECLARE <variable>` in the same block (error 1337, "Variable or condition
declaration after cursor or handler declaration") — a rule no other target
engine imposes, so a source routine that declares its cursor before its
scalar variables (a legal order on Oracle/T-SQL/PostgreSQL) needs its
leading declaration block reordered for MySQL specifically.

**Solution.**

```sql
-- corpus case ora-cursor
CREATE PROCEDURE p AS CURSOR c IS SELECT 1 AS x FROM DUAL; v NUMBER;
BEGIN OPEN c; FETCH c INTO v; CLOSE c; END;
-- oracle -> mysql:
DELIMITER $$
CREATE PROCEDURE p()
BEGIN
    DECLARE v DECIMAL;
    DECLARE c CURSOR FOR SELECT 1 AS x FROM DUAL;

    OPEN c;
    FETCH c INTO v;
    CLOSE c;
END$$
DELIMITER ;
```

The source declares the cursor `c` first, then the scalar `v`; the MySQL
output reorders them (`v` first, `c` second) while leaving every other
statement — `OPEN`/`FETCH`/`CLOSE` — untouched.

**Discussion.** MySQL's declaration-ordering rule exists because cursor and
handler declarations bind to the block's *remaining* variable declarations
at parse time; Oracle, T-SQL, and PostgreSQL have no such ordering
constraint at all, so a source author is free to declare a cursor before
the variables it will fetch into. Reordering only the leading declaration
block (not any executable statement) is enough to satisfy MySQL's rule
without changing behavior.

> **Note** faithful — live-verified: "Compiles + CALL ok on MySQL." Purely a
> declaration reorder; no executable statement moves or changes.

**See Also.** [`TestMysqlCursorDeclOrder`](../../tests/integration/test_challenge.py) ·
[`ora-cursor`](../../tests/fixtures/challenge/challenge_oracle.sql).

## Topics left out for lack of source support

- **Ref cursor `OUT` parameters** (`SYS_REFCURSOR`) and **`EXECUTE IMMEDIATE
  … USING bind1, bind2`** Oracle→T-SQL specifics are documented in
  `docs/03-unsupported.md` §6, but no challenge-corpus case exercises either
  construct, so no dedicated entry is made here to avoid inventing an
  example.
