[← Procedural: cursors, dynamic SQL, system procedures, session directives](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=procedural type="Loop and cursor desugaring" direction="cross-engine" kind=article order=32 direction-inferred=true -->

# Bare `RETURN` in a MySQL procedure → labeled `proc_exit:` block + `LEAVE`

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

**See Also.** [`TestBareReturnInProcedure`, `TestReturnValueInProcedure`](../../../tests/integration/test_procedural.py), [`TestMySqlReturnBecomesLeave`](../../../tests/integration/test_oracle_mysql_tail.py) ·
[`UNIQUE-1177`](../../reference/warnings.md#unique-1177) — no dedicated
challenge-corpus case exercises bare `RETURN`/`LEAVE`, so the examples above
are drawn from those dedicated integration tests.
