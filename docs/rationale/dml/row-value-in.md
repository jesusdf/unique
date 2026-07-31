[← DML: PIVOT/UNPIVOT, MERGE, DELETE, row values](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=dml type="Row-value comparisons" direction="oracle → tsql" kind=article order=10 -->

# Row-value `IN` (Oracle) → T-SQL

**Problem.** `(a, b) IN ((1, 2), (3, 4))` is a row-constructor `IN`
list, valid on Oracle/PostgreSQL/MySQL.

**Solution.** Expanded to an `OR`-of-`AND`-pairs form:
`(a = 1 AND b = 2) OR (a = 3 AND b = 4)`.

**Discussion.** T-SQL has no row-constructor `IN` either
(the same error 4145 as the inequality case above).

> **Note** faithful.

**See Also.** [`reda-ora-rowvalue-in`](../../../tests/fixtures/challenge/challenge_oracle.sql) (neighbour of [`pg-row-value-comparison`](../../../tests/fixtures/challenge/challenge_postgresql.sql)).
