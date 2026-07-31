[← Procedural: cursors, dynamic SQL, system procedures, session directives](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=procedural type="Cursor attribute mapping" direction="oracle/postgresql → tsql/mysql" kind=article order=7 -->

# PL/pgSQL implicit `FOUND` / Oracle implicit `SQL%FOUND` → T-SQL `@@ROWCOUNT` / MySQL `ROW_COUNT()`

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
rename with no per-target state to synthesize — a value-position attribute
rename, not a control-flow expansion.

> **Note** faithful — same "did the last statement touch a row" question,
> restated in each target's own implicit-state syntax.

**See Also.** [`TestPgFoundFlagInIr`](../../../tests/unit/core/test_ir_first_families.py), [`TestOracleCursorAttrsInIr`](../../../tests/unit/core/test_ir_first_families.py) ·
[§3.22](../../03-unsupported.md) (the related `SQL%ROWCOUNT` "matched vs.
changed" divergence), [§3.23](../../03-unsupported.md).
