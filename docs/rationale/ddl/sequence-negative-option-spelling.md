[← DDL: identity, temp tables, foreign keys, sequences, storage options](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=ddl type="Sequences" direction="oracle ↔ tsql/postgresql" kind=article order=11 direction-inferred=true -->

# One-word vs two-word negative options (Oracle `NOMAXVALUE`/`NOCYCLE` vs T-SQL/PostgreSQL `NO MAXVALUE`/`NO CYCLE`)

**Problem.** `CREATE SEQUENCE … NO MAXVALUE NO CYCLE` (T-SQL,
PostgreSQL) and `CREATE SEQUENCE … NOMAXVALUE NOCYCLE` (Oracle) both mean
"no upper bound, do not wrap around" — the same option, spelled as two words
on some engines and fused to one word on Oracle.

**Solution.**

```sql
-- corpus case reda-ts-sequence-no-cycle
CREATE SEQUENCE seq START WITH 1 INCREMENT BY 1 NO MAXVALUE NO CYCLE
-- Oracle: CREATE SEQUENCE seq START WITH 1 INCREMENT BY 1 NOMAXVALUE NOCYCLE
```

The Oracle emitter collapses `NO MAXVALUE`→`NOMAXVALUE`,
`NO MINVALUE`→`NOMINVALUE`, `NO CYCLE`→`NOCYCLE`, `NO CACHE`→`NOCACHE`.
Conversely, Oracle's own one-word negatives map to the two-word spelling
onto PostgreSQL/T-SQL. Oracle's `ORDER`/`NOORDER` clause (a RAC-only option
with no equivalent on any other engine) is dropped.

**Discussion.** This is a pure spelling gap, not a
semantic one: Oracle's grammar rejects the two-word form outright
(`ORA-03049`, "SQL keyword 'NO' is not syntactically valid").

> **Note** faithful (a spelling fix, not a semantic
> degrade). The earlier defect emitted the two-word form verbatim into Oracle,
> which failed to parse — a real defect, not an approved limit.

**See Also.** [`reda-ts-sequence-no-cycle`](../../../tests/fixtures/challenge/challenge_sqlserver.sql), [`ora-sequence-options`](../../../tests/fixtures/challenge/challenge_oracle.sql).
