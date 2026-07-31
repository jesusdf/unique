[← DML: PIVOT/UNPIVOT, MERGE, DELETE, row values](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=dml type="Row-value comparisons" direction="oracle/postgresql/mysql → tsql" kind=article order=9 -->

# Row-value inequality (PostgreSQL / Oracle / MySQL) → T-SQL

**Problem.** `(a, b) > (1, 5)` is a lexicographic row-value
comparison — common for keyset pagination — true when `a > 1`, or `a = 1 AND
b > 5`.

**Solution.**

```sql
-- corpus case pg-row-value-comparison
SELECT * FROM t WHERE (a, b) > (1, 5)
-- T-SQL: WHERE a > 1 OR (a = 1 AND (b > 5))
```

T-SQL gets the comparison expanded lexicographically:
`a > 1 OR (a = 1 AND (b > 5))`.

**Discussion.** T-SQL has no row-value comparison syntax
at all; the tuple literal is rejected outright (error 4145, "non-boolean
type … where a condition is expected"). PostgreSQL, Oracle and MySQL all
accept it natively.

> **Note** faithful — PG native result `(3,4)`.

**See Also.** [`pg-row-value-comparison`](../../../tests/fixtures/challenge/challenge_postgresql.sql).
