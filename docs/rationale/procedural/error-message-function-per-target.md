[← Procedural: cursors, dynamic SQL, system procedures, session directives](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=procedural type="ERROR_MESSAGE() function mapping" direction="tsql → oracle/postgresql/mysql" kind=article order=44 -->

# T-SQL `ERROR_MESSAGE()` (inside a `CATCH` block) → each target's own error-text accessor

**Problem.** Inside a T-SQL `CATCH` block, `ERROR_MESSAGE()` reads the text
of the error that was just caught. Every other engine's exception handler
has its own, differently-spelled way to read the same text — this is a
plain built-in function call, not an expression Unique's error-hoisting
machinery (which handles *composing* a message, not *reading* the caught
one) already covers.

**Solution.**

```sql
-- tests/integration/test_test2_residue_wave.py::TestScalarIdioms::test_error_message_maps_per_target
CREATE PROCEDURE dbo.p_e AS
BEGIN
    BEGIN TRY
        UPDATE t_z SET x = 1
    END TRY
    BEGIN CATCH
        DECLARE @msg NVARCHAR(2048) = ERROR_MESSAGE()
        RAISERROR(@msg, 16, 1)
    END CATCH
END
-- tsql -> postgresql (PL/pgSQL exception handler):
v_msg := SQLERRM;
RAISE EXCEPTION '%', v_msg;
-- tsql -> oracle:
V_MSG := SQLERRM;
RAISE_APPLICATION_ERROR(-20001, V_MSG);
-- tsql -> mysql:
GET DIAGNOSTICS CONDITION 1 v_msg = MESSAGE_TEXT;
SET MESSAGE_TEXT = v_msg;
```

**Discussion.** T-SQL's `ERROR_MESSAGE()` is a niladic function callable
anywhere inside a `CATCH` block; PostgreSQL and Oracle's PL/SQL both expose
the equivalent as a bare identifier (`SQLERRM`) rather than a function
call, and MySQL has no expression form at all — the same information is
only reachable through the `GET DIAGNOSTICS CONDITION 1 ... =
MESSAGE_TEXT` statement, which must run as its own statement immediately
inside the handler rather than being substitutable inline. Unique reads
`ERROR_MESSAGE()` off the T-SQL source and emits whichever of these three
forms the target's exception-handling grammar requires, keeping the
surrounding assignment/re-raise structure intact.

> **Note** faithful — every target's spelling reads the same caught error
> text; MySQL's `GET DIAGNOSTICS` statement form is the one true structural
> difference (a statement instead of an inline read), not a value change.
> No warning.

**See Also.** [`test_test2_residue_wave.py::TestScalarIdioms`](../../../tests/integration/test_test2_residue_wave.py)
(`test_error_message_maps_per_target`) · [RAISERROR (T-SQL) ↔ Oracle
`RAISE_APPLICATION_ERROR` / PostgreSQL `RAISE EXCEPTION`: expression
messages and printf substitutions](raiserror-expression-messages.md) (the
sibling mechanism for *composing* a raised message, as opposed to *reading*
one already caught).
