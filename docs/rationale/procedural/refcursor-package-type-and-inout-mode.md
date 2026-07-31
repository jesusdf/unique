[← Procedural: cursors, dynamic SQL, system procedures, session directives](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=procedural type="Package ref-cursor type resolution and usage-inferred mode" direction="oracle → postgresql/oracle/mysql" kind=article order=47 -->

# A package-qualified ref-cursor type (`pkg.my_cursor`) → the target's own ref-cursor type

**Problem.** An Oracle procedure parameter can be typed with a
package-defined `REF CURSOR` subtype (`v_cur OUT pkg_ret.my_cursor`) —
`pkg_ret.my_cursor` is only meaningful *inside that package*, never on a
target with no package concept at all. A parameter typed this way still
has to become a usable ref-cursor parameter on every target, not a generic
fallback type that would break the very statement that opens it.

**Solution.**

```sql
-- tests/integration/test_oracle_mysql_tail.py::TestPackageRefCursorType
create or replace PROCEDURE p_rc(v_id IN NUMBER, v_cur OUT pkg_ret.my_cursor) AS
BEGIN
  OPEN v_cur FOR SELECT a FROM t WHERE id = v_id;
END;
/
-- oracle -> postgresql (argmode spelled first, native REFCURSOR):
CREATE OR REPLACE PROCEDURE p_rc
(
    v_id NUMERIC,
    OUT v_cur REFCURSOR
)
...
-- oracle -> oracle (identity transpile keeps the package-qualified type):
CREATE OR REPLACE PROCEDURE p_rc
(
    v_id IN NUMBER,
    v_cur OUT pkg_ret.my_cursor
)
...
-- oracle -> mysql (no ref-cursor concept at all: drops to a direct result
-- set, with a warning):
CREATE PROCEDURE p_rc
(
    IN v_id DECIMAL
)
BEGIN
    SELECT a FROM t WHERE id = v_id;
END
```

The reverse mechanism — a PostgreSQL function parameter typed `refcursor`
that the body actually `OPEN`s (rather than only ever receiving an
already-open one) — resolves to Oracle's `IN OUT SYS_REFCURSOR` mode
instead of a plain `OUT`, since Oracle requires `IN OUT` for a cursor
variable the routine both reads (to `OPEN`) and returns:

```sql
-- tests/unit/core/test_ir_first_families.py::TestZeroPushW5Batch::test_opened_refcursor_param_is_in_out_oracle
create function rr(rc refcursor) returns refcursor as $$
  begin open rc for select a from rc_test; return rc; end$$ language plpgsql;
-- postgresql -> oracle:
FUNCTION rr (rc IN OUT SYS_REFCURSOR) RETURN SYS_REFCURSOR
```

**Discussion.** PostgreSQL's ref-cursor type is spelled `REFCURSOR`
regardless of which package (if any) a source Oracle type came from, so
the package qualifier is simply dropped in favor of the plain target type
— a `TEXT` fallback here (Unique's generic catch-all for an unrecognized
type) would instead corrupt every later `OPEN v_cur FOR ...` into invalid
SQL. Oracle's own identity path is the one case where the qualified type
name is meaningful and kept verbatim, since the package still exists on
that same target. MySQL has no cursor-as-parameter concept whatsoever, so
the procedure degrades to directly running the query as its result set — a
documented, warned loss of the "returns via an OUT parameter" calling
convention, not a silent one. The `IN OUT` mode inference is a separate,
usage-driven decision: Unique reads whether the body's own code opens the
cursor (a read of the parameter, requiring `IN`) in addition to returning
it (a write, requiring `OUT`), rather than assuming a fixed mode for every
cursor parameter.

> **Note** faithful on PostgreSQL and Oracle (the type resolves to a usable
> ref-cursor on both); the MySQL leg is a **documented** `[limit]` — a
> warning names the lost OUT-parameter calling convention rather than
> emitting a phantom type.

**See Also.** [`test_oracle_mysql_tail.py::TestPackageRefCursorType`](../../../tests/integration/test_oracle_mysql_tail.py) ·
[`test_ir_first_families.py::TestZeroPushW5Batch`](../../../tests/unit/core/test_ir_first_families.py)
(`test_opened_refcursor_param_is_in_out_oracle`) ·
[A bare result `SELECT` inside a procedure body → a ref-cursor
parameter](bare-result-select-to-refcursor.md) (the sibling mechanism that
*synthesizes* a ref-cursor parameter, rather than resolving one already
declared).
