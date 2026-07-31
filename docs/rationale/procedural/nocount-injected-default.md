[← Procedural: cursors, dynamic SQL, system procedures, session directives](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=procedural type="SET NOCOUNT ON best-practice default" direction="cross-engine" kind=article order=41 direction-inferred=true -->

# A T-SQL procedure body gains a synthesized `SET NOCOUNT ON;` by default

**Problem.** SQL Server's documented best practice for every stored
procedure is `SET NOCOUNT ON` — it suppresses the "N row(s) affected"
message that would otherwise ride along on every DML statement, cluttering
client output and, over a network round trip, costing real time. Source
engines other than T-SQL have no such statement and never write one, so a
procedure translated verbatim would silently lose this suppression on the
T-SQL side.

**Solution.**

```sql
-- tests/integration/test_tsql_nocount.py::TestNoCountNotDuplicated::test_injection_still_happens_without_body_directive
CREATE OR REPLACE PROCEDURE p (
    RESULT_CURSOR OUT SYS_REFCURSOR
)
AS BEGIN
    OPEN RESULT_CURSOR FOR SELECT * FROM a_tbl;
END;
/
-- oracle -> tsql:
CREATE OR ALTER PROCEDURE p
AS
BEGIN
    SET NOCOUNT ON;

    SELECT * FROM a_tbl;
END
```

The injection is suppressed, never duplicated, when the body already
manages `NOCOUNT` itself — an explicit `SET NOCOUNT ON`/`OFF` the source
author wrote, or a `/* UNIQUE: SET NOCOUNT ON -- tsql-only ... */` carrier
restored on a round trip back from another engine. An author's own `SET
NOCOUNT OFF` is respected exactly as written; Unique never forces `ON` in
front of it.

**Discussion.** This is a T-SQL-only injection: the other three target
engines have no equivalent row-count-message setting to suppress, so
nothing is added for them. The suppression logic has to inspect the body
before deciding whether to inject, since duplicating an author's own `SET
NOCOUNT ON` (two identical statements) or contradicting an author's
explicit `OFF` would both be worse than doing nothing.

> **Note** faithful in the sense that the injected default is the
> documented best practice, not a change to the procedure's data effect —
> `NOCOUNT` never touches query results, only the row-count status
> messages a client may or may not observe. No warning.

**See Also.** [`test_tsql_nocount.py`](../../../tests/integration/test_tsql_nocount.py)
(`TestNoCountNotDuplicated`) · sibling mechanism: [Empty trigger body →
synthesized `SET NOCOUNT ON;` no-op](empty-trigger-body-noop.md) (reuses the
same filler for a different reason — a trigger body T-SQL cannot leave
empty, rather than the best-practice default).
