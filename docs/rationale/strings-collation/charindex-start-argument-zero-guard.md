[← Strings, concatenation and collation](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=strings-collation type="Repeat, substring and splice" direction="tsql → postgresql" kind=article order=19 direction-inferred=true -->

# 3-argument `CHARINDEX(needle, s, start)` (T-SQL) → PostgreSQL zero-guarded `POSITION`

**Problem.** T-SQL's `CHARINDEX(needle, s, start)` searches only from
`start` onward, and returns `0` (not `NULL`) when the needle isn't found
anywhere from `start` on. PostgreSQL's `POSITION(needle IN s)` has no
start-position argument at all — a naive translation either drops the
start offset silently (searching from the beginning, a wrong answer for
any match before `start`) or, if the start is folded in by slicing the
haystack (`POSITION(needle IN SUBSTRING(s FROM start)) + start - 1`),
returns the *wrong* result specifically for the not-found case: a bare
`POSITION(...) = 0` inside the sliced haystack becomes `0 + start - 1`, a
non-zero number that looks like a real match position.

**Solution.**

```sql
-- tests/unit/core/test_ir_first_families.py::TestCharindexStartGuardOnPg
SELECT CHARINDEX('x', s, 5) FROM t
-- tsql -> postgresql:
SELECT CASE WHEN POSITION('x' IN SUBSTRING(s FROM 5)) = 0 THEN 0
            ELSE POSITION('x' IN SUBSTRING(s FROM 5)) + 5 - 1 END
FROM t
```

**Discussion.** The start offset itself translates cleanly by slicing the
haystack with `SUBSTRING(s FROM start)` before searching — PostgreSQL's
`POSITION` finds the needle's index *within that slice*, which needs `+
start - 1` added back to become an index into the original string. The
not-found case is the part that needs guarding: `POSITION` returns `0` for
"not found" the same way `CHARINDEX` does, but only *before* the `+ start -
1` offset is added — once added, a real `0` (not found) and a found match
at the slice's very first character both risk landing on numbers that no
longer mean what they say unless the not-found case is tested and
short-circuited first. The `CASE WHEN ... = 0 THEN 0 ELSE ... END` wrap
tests the raw (pre-offset) `POSITION` result and returns a bare `0` for
not-found, only adding the offset on the found branch.

> **Note** faithful — the not-found case now returns exactly `0`, matching
> `CHARINDEX`'s contract, instead of the `start - 1` a bare offset-add would
> have produced; live-verified the guarded form matches `CHARINDEX`'s value
> on both branches. No warning.

**See Also.** [`test_ir_first_families.py::TestCharindexStartGuardOnPg`](../../../tests/unit/core/test_ir_first_families.py) ·
[`test_trigger_predicates_scheduler.py::test_three_arg_charindex_keeps_start_on_postgresql`](../../../tests/integration/test_trigger_predicates_scheduler.py)
(a companion pinning test inside a function body) ·
[§2.1](../../03-unsupported.md), which notes `CHARINDEX`↔`INSTR`↔`LOCATE`
argument reordering generally — this entry covers the specific
zero-guard needed only for the T-SQL → PostgreSQL 3-argument form.
