[← Procedural: cursors, dynamic SQL, system procedures, session directives](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=procedural type="Loop/cursor desugaring" direction="tsql → oracle" kind=article order=57 -->

# T-SQL `IF EXISTS (<real query>) BEGIN ... END [ELSE ...]` → Oracle cursor `FOR` loop over a `DUAL` probe

**Problem.** `IF EXISTS (SELECT ...) BEGIN ... END` is ordinary control
flow over real table data (not a system-catalog idempotency guard) — a
migration script checking "has this step already run?" before doing more
work, for example. `IF EXISTS(<subquery>)` used as a boolean condition is
invalid PL/SQL (PLS-00204: Oracle only allows `EXISTS` inside a `WHERE`
clause), so the condition can't be carried over as-is, and — unlike a
catalog guard — it can't simply be dropped either: the subquery is real
application data, and losing the condition would silently change which
rows the body affects.

**Solution.**

```sql
-- tests/unit/core/test_if_exists_control_flow.py::TestNonCatalogIfExists::test_if_exists_emulated_as_for_loop
IF EXISTS (SELECT NULL FROM dbo.schema_version WHERE revision = 1)
BEGIN
  PRINT 'already applied'
END
-- tsql -> oracle:
BEGIN FOR unique_guard IN (SELECT 1 FROM DUAL WHERE EXISTS(SELECT NULL FROM dbo.schema_version WHERE revision = 1)) LOOP
    DBMS_OUTPUT.PUT_LINE('already applied');
END LOOP; END;
/
```

An `ELSE` becomes a second loop over the negated probe:

```sql
-- tests/unit/core/test_if_exists_control_flow.py::TestNonCatalogIfExists::test_if_exists_else_becomes_two_for_loops
IF EXISTS (SELECT NULL FROM dbo.t WHERE c = 1)
  BEGIN PRINT 'a' END
ELSE
  BEGIN PRINT 'b' END
-- tsql -> oracle: two FOR loops, one per polarity — EXISTS and NOT EXISTS
-- are mutually exclusive, so exactly one body ever fires.
```

**Discussion.** A one-row cursor `FOR` loop over `DUAL` turns the
condition into something Oracle's `EXISTS` operator is actually allowed to
appear in (a `WHERE` clause) while keeping single-statement shape: `FOR ...
IN (SELECT 1 FROM DUAL WHERE EXISTS(<subquery>)) LOOP <body> END LOOP`
iterates its body exactly once if the subquery finds a row, and zero times
otherwise — the same true/false outcome an `IF` would have produced,
without needing a `DECLARE` block. This is the identical idiom the
system-catalog DDL guards use for the same underlying reason (PL/SQL has
no bare boolean `EXISTS`), but here it wraps **any** statement, not just
`EXECUTE IMMEDIATE`'d DDL, because the condition is genuine row data rather
than a catalog check that could otherwise be special-cased away. An `ELSE`
is handled as a second, independent `FOR` loop over the *negated* probe
(`NOT EXISTS` for the `THEN` arm's opposite) rather than an `IF/ELSE`
inside one loop, which keeps both arms equally simple and correct since
the two probes can never both match. A genuine system-catalog guard
(`sys.objects`/`OBJECT_ID`) is still recognized and handled by the
separate DDL-guard path — its condition is dropped rather than emulated,
since it has no faithful cross-engine query of its own to keep.
PostgreSQL and MySQL need no emulation here at all: both accept `IF EXISTS
(<subquery>) THEN ... END IF` natively inside a `DO $$`/routine block, so
the condition carries straight across.

> **Note** faithful — the Oracle `FOR` loop's body runs iff (and exactly
> as many times as) the source `IF EXISTS` branch would have taken it;
> live-validated.

**See Also.** [`test_if_exists_control_flow.py`](../../../tests/unit/core/test_if_exists_control_flow.py)
(`TestNonCatalogIfExists`) · [§6](../../03-unsupported.md), "Procedural
Engine — Known Limitations" ("Non-catalog `IF EXISTS(…) BEGIN … END`
control flow") · [T-SQL system-catalog DDL guards](../ddl/tsql-existence-guard-catalog-probes.md)
(the sibling mechanism for catalog-only conditions).
