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

## Topics left out for lack of source support

- **Ref cursor `OUT` parameters** (`SYS_REFCURSOR`) and **`EXECUTE IMMEDIATE
  … USING bind1, bind2`** Oracle→T-SQL specifics are documented in
  `docs/03-unsupported.md` §6, but no challenge-corpus case exercises either
  construct, so no dedicated entry is made here to avoid inventing an
  example.
