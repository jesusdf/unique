[← Procedural: cursors, dynamic SQL, system procedures, session directives](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=procedural type="Oracle LOB and numeric-cast helper functions" direction="oracle → tsql/mysql" kind=article order=52 -->

# Oracle `DBMS_LOB`/`UTL_RAW`/`TO_NUMBER`/`TRUNC` helper calls → T-SQL/MySQL built-ins

**Problem.** Several of Oracle's package-qualified LOB helpers and its
bare numeric/date built-ins have no shared name on other engines, and one
(`DBMS_LOB.SUBSTR`) even reorders its arguments compared to the target's
equivalent.

**Solution.**

Oracle's bare `TO_NUMBER(x)` (no format mask) is a decimal cast in
disguise:

```sql
-- tests/unit/core/test_ir_first_families.py::TestToNumberInIr
SELECT TO_NUMBER(c) FROM t
-- oracle -> tsql:
SELECT CAST(c AS DECIMAL(38, 10)) FROM t
```

`DBMS_LOB.SUBSTR(lob, length, position)` reorders to T-SQL's
`SUBSTRING(value, start, length)` — length and position trade places:

```sql
-- tests/unit/core/test_ir_first_families.py::TestTrimPositionAndLobHelpers
SELECT DBMS_LOB.SUBSTR(p_c, 4000, 1) FROM t
-- oracle -> tsql:
SELECT SUBSTRING(P_C, 1, 4000) FROM t
```

`UTL_RAW.CAST_TO_VARCHAR2` and `DBMS_LOB.GETLENGTH` map onto T-SQL's own
conversion and length built-ins:

```sql
SELECT UTL_RAW.CAST_TO_VARCHAR2(x) FROM t   -- => SELECT CONVERT(VARCHAR(MAX), x) FROM t
SELECT DBMS_LOB.GETLENGTH(x) FROM t         -- => SELECT DATALENGTH(x) FROM t
```

Oracle's `TRUNC(x)` is overloaded between date truncation and numeric
truncation depending on `x`'s own type — a distinction MySQL's target
functions don't share a single name for, so the choice of `DATE(x)` vs.
`TRUNCATE(x, 0)` is read off whether `x` is a variable Unique has already
tracked as date-typed:

```sql
-- tests/unit/core/test_ir_first_families.py::TestDateVarsContextInIr
SELECT TRUNC(d_fecha) FROM t   -- d_fecha tracked as a date variable
-- oracle -> mysql: SELECT DATE(D_FECHA) FROM t
SELECT TRUNC(v_num) FROM t     -- v_num not tracked as a date variable
-- oracle -> mysql: SELECT TRUNCATE(V_NUM, 0) FROM t
```

**Discussion.** These are independent 1:1 built-in remaps grouped here
rather than each given its own page, since none is large enough to
warrant one — `TO_NUMBER`'s target precision (`DECIMAL(38, 10)`) is the
same project-wide bounded-numeric convention used for Oracle's bare
`NUMBER` column type; `DBMS_LOB.SUBSTR`'s argument reorder is purely
positional, with no value change; `TRUNC`'s date-vs-numeric dispatch
relies on the same declared-variable-type tracking the numeric-division
and other type-aware compensations on this site rely on elsewhere.

> **Note** faithful — every rewrite reproduces the source call's exact
> value; the `TRUNC` dispatch in particular only picks correctly when the
> variable's type is known from a `DECLARE` earlier in the same routine,
> the same caveat the numeric-division family shares.

**See Also.** [`test_ir_first_families.py`](../../../tests/unit/core/test_ir_first_families.py)
(`TestToNumberInIr`, `TestTrimPositionAndLobHelpers`, `TestDateVarsContextInIr`) ·
[Oracle bare `NUMBER` (no precision/scale) → role-aware numeric](../ddl/oracle-bare-number-role-aware.md)
(shares the `DECIMAL(38, 10)` convention).
