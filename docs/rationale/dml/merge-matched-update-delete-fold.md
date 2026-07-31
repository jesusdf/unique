[← DML: PIVOT/UNPIVOT, MERGE, DELETE, row values](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=dml type="`MERGE` / upsert lowering" direction="tsql → oracle" kind=article order=4 -->

# Conditional `MATCHED` UPDATE+DELETE pair (T-SQL) → Oracle fold

**Problem.** A T-SQL `MERGE` may carry two conditional `WHEN
MATCHED` clauses in sequence — first-match-wins — one `UPDATE`, one `DELETE`.

**Solution.** The pair folds into one Oracle `UPDATE` (whose `SET`
keeps the old value via `CASE` where the update should not apply) plus a
spliced `DELETE WHERE` tail — but **only** when the fold is value-safe: the
`DELETE` condition must reference no target column the `UPDATE` assigns. When
it does (the post-update semantics would delete rows T-SQL keeps), the whole
`MERGE` degrades to a carrier + warning instead of shipping silently-wrong
output.

**Discussion.** Oracle's `MERGE` grammar allows only a
**single** `WHEN MATCHED` clause; conditional forms are spelled as an
`UPDATE … WHERE` plus a trailing `DELETE WHERE` tail on the same clause, not
two separate `WHEN` branches — and critically, Oracle's `DELETE WHERE`
evaluates against the **post-update** row, while T-SQL evaluates the
original (pre-update) row.

> **Note** faithful in the safe shape (live-verified
> identical rows). Full warned carrier in the unsafe shape.

**See Also.** [§3.6](../../03-unsupported.md) (MERGE clause composition,
audit 2026-07-24).
