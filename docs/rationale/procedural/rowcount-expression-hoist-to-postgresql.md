[← Procedural: cursors, dynamic SQL, system procedures, session directives](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=procedural type="Cursor attribute mapping" direction="oracle/tsql/mysql → postgresql" kind=article order=60 -->

# Implicit row count in EXPRESSION position (Oracle `SQL%ROWCOUNT` / T-SQL `@@ROWCOUNT` / MySQL `ROW_COUNT()`) → PostgreSQL `GET DIAGNOSTICS` hoist

**Problem.** Oracle's `SQL%ROWCOUNT`, T-SQL's `@@ROWCOUNT`, and MySQL's
`ROW_COUNT()` are all readable **inline**, as an expression, anywhere a value
is expected (`IF SQL%ROWCOUNT <> 1`, `v := SQL%ROWCOUNT + 1`, a call
argument, a `RETURN`). PostgreSQL exposes the same information only through
`GET DIAGNOSTICS x = ROW_COUNT`, a **statement** — it has no inline form at
all, so a plain substitution has nowhere to go.

**Solution.**

```sql
-- tests/integration/test_oracle_rowcount_hoist_b37.py::TestIfCondition, oracle -> postgresql
CREATE OR REPLACE PROCEDURE p IS
BEGIN
    UPDATE t SET x = 1 WHERE id = 5;
    IF SQL%ROWCOUNT <> 1 THEN
        RAISE_APPLICATION_ERROR(-20001, 42);
    END IF;
END;
-- =>
CREATE OR REPLACE PROCEDURE p()
LANGUAGE plpgsql
AS $$
DECLARE
    uq_rowcount bigint;
BEGIN
    UPDATE t SET x = 1 WHERE id = 5;
    GET DIAGNOSTICS uq_rowcount = ROW_COUNT;
    IF uq_rowcount <> 1 THEN
        ...
    END IF;
END;
$$;
```

A `GET DIAGNOSTICS uq_rowcount = ROW_COUNT;` capture is inserted immediately
before the statement that references the row count, and the reference itself
is substituted with `uq_rowcount` — a `bigint` local declared once per
routine no matter how many references it serves (each gets its own capture,
placed right after the DML it reads and right before its own use). The same
hoist recognizes all three source spellings that can reach PostgreSQL: a
degrade carrier (the common case), MySQL's own `ROW_COUNT()` spelling, and
T-SQL's `@@ROWCOUNT` (already renamed to `ROW_COUNT()` upstream) — so the
mechanism is one recognizer, not three.

A condition that is **re-evaluated**, such as a `WHILE`/`EXIT` loop
condition, cannot be captured once and substituted — each iteration would
need its own fresh read, which a single hoisted local cannot provide — so it
keeps the honest `UNIQUE-1033` carrier + warning instead:

```sql
-- tests/integration/test_oracle_rowcount_hoist_b37.py::TestLoopConditionDegrades
WHILE SQL%ROWCOUNT > 0 LOOP
    DELETE FROM t WHERE flag = 1;
END LOOP;
-- => stays a documented carrier; no capture invented for the loop condition
```

A reference **inside** a loop's body (as opposed to its condition) still
hoists correctly — the capture lands inside the loop, re-executing each
iteration along with the DML it reads.

**Discussion.** Oracle's `SQL%ROWCOUNT` names the last DML *executed by the
session*, which in straight-line procedural code is simply the immediately
preceding statement; `GET DIAGNOSTICS` does not itself touch `ROW_COUNT`, so
placing the capture right before the use reads exactly the value the source
would have read at that point. This only breaks down for a condition that is
evaluated more than once between DML statements (a loop test), which is why
that shape is excluded and kept as the pre-existing carrier.

> **Note** faithful — live-verified on PostgreSQL: the captured local drives
> the same branch the source `SQL%ROWCOUNT` comparison would. T-SQL
> (`@@ROWCOUNT`) and MySQL (`ROW_COUNT()`) already read the count inline on
> their own targets and are unaffected by this hoist.

**See Also.** [`test_oracle_rowcount_hoist_b37.py`](../../../tests/integration/test_oracle_rowcount_hoist_b37.py), [`test_rowcount_hoist_b37b.py`](../../../tests/integration/test_rowcount_hoist_b37b.py) ·
[§3.22](../../03-unsupported.md) (the residual re-evaluated-loop-condition carrier, `UNIQUE-1033`) ·
[Oracle cursor attributes](oracle-cursor-attributes.md) (the related but distinct per-cursor `%ROWCOUNT`) ·
[implicit `FOUND`/`SQL%FOUND`](implicit-found-flag.md) (the boolean sibling, a direct rename with no hoist needed) ·
[the `SQL%ROWCOUNT`/`ROW_COUNT()` matched-vs-changed divergence onto MySQL](../../03-unsupported.md).

---
