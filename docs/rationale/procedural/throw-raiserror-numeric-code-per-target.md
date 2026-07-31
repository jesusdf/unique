[← Procedural: cursors, dynamic SQL, system procedures, session directives](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=procedural type="THROW/RAISERROR numeric error code" direction="tsql → oracle/postgresql/mysql" kind=article order=50 -->

# T-SQL `THROW`/`RAISERROR`'s numeric error code → each target's own error-code slot

**Problem.** T-SQL's `THROW 50001, 'not found', 1` and `RAISERROR('not
found', 16, 1)` (with a matching custom message id registered separately)
both carry a *numeric error code* alongside the message text. Every target
has its own error-raising statement with its own numeric-code slot and its
own valid range — none accepts T-SQL's raw `50001` (T-SQL's own
user-error range) verbatim.

**Solution.**

```sql
-- tests/unit/core/test_throw_message.py::TestThrowMessagePreserved
CREATE PROCEDURE p AS BEGIN THROW 50001, 'not found', 1; END
-- tsql -> oracle:
RAISE_APPLICATION_ERROR(-20001, 'not found');
-- tsql -> postgresql:
RAISE EXCEPTION 'not found';
-- tsql -> mysql:
SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'not found', MYSQL_ERRNO = 50001;
```

A T-SQL `RAISERROR` with *no separate message text at all* — a bare
numeric message id registered elsewhere via `sp_addmessage`, which the
migrated script never carries — gets a canned placeholder text instead of
inventing or dropping the message:

```sql
-- tests/integration/test_procedural.py::TestRaiserrorToMySQLSignal::test_numeric_message_id
CREATE PROCEDURE dbo.p AS BEGIN RAISERROR (16947, 16, 1) END
-- tsql -> mysql:
SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Application error', MYSQL_ERRNO = 16947;
```

**Discussion.** Oracle's `RAISE_APPLICATION_ERROR` only accepts codes in
the narrow `-20000` to `-20999` range, so T-SQL's `50001` maps by
subtracting T-SQL's own base (`50000`) and applying it as an offset from
Oracle's `-20000` floor — `50001` → `-20001`, `50002` → `-20002`, and so
on, keeping distinct source codes distinct on Oracle rather than
collapsing them to one fixed number. PostgreSQL's `RAISE EXCEPTION` has no
numeric-code slot at all (it identifies errors by `SQLSTATE`/exception
name instead), so the number is dropped — only the message text carries
over, since there is nowhere on PostgreSQL to put it. MySQL's `SIGNAL`
keeps the number, but in its own `MYSQL_ERRNO` slot alongside a generic
`SQLSTATE '45000'` ("unhandled user-defined exception"), the standard
placeholder state for a custom error.

> **Note** faithful on Oracle and MySQL — the code is preserved (offset,
> for Oracle's narrower range); PostgreSQL loses the numeric code since it
> has no equivalent slot, a structural limit noted here rather than a
> defect (the message text itself never depends on the number to be
> understood). No warning: the number is presentation/diagnostic
> metadata, not a value change to the query's own data.

**See Also.** [`test_throw_message.py::TestThrowMessagePreserved`](../../../tests/unit/core/test_throw_message.py)
(`test_postgresql_keeps_text`, `test_oracle_keeps_text_and_maps_number`,
`test_mysql_keeps_text_and_number`, `test_raiserror_text_form`) ·
[`test_procedural.py::TestRaiserrorToMySQLSignal`](../../../tests/integration/test_procedural.py)
(`test_numeric_message_id`) ·
[RAISERROR (T-SQL) ↔ Oracle `RAISE_APPLICATION_ERROR` / PostgreSQL `RAISE
EXCEPTION`: expression messages and printf substitutions](raiserror-expression-messages.md)
(the sibling mechanism for the *message* side of the same statements).
