[← Strings, concatenation and collation](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=strings-collation type="NULL and empty-string semantics" direction="oracle → all" kind=article order=4 direction-inferred=true -->

# Oracle `'' ≡ NULL`

**Problem.** Every other engine stores and compares an empty string
`''` as a distinct, zero-length value: `'' IS NULL` is false, `COALESCE('',
'x')` is `''`.

**Solution.**

```sql
-- ora-empty-is-null, oracle → mysql/postgresql/tsql
SELECT CASE WHEN '' IS NULL THEN 1 ELSE 0 END AS r FROM DUAL;
-- Oracle: 1 (true).  MySQL/PostgreSQL/T-SQL: 0 (false) — no faithful rewrite exists.

-- ora-empty-null, oracle → mysql/postgresql/tsql
SELECT NVL('', 'x') AS r FROM DUAL;
-- Oracle: 'x'.  Elsewhere COALESCE('', 'x') = '' — the two functions disagree
-- precisely because only Oracle treats '' as absent.
```

The literal expressions pass through; where an
Oracle-source result genuinely cannot be reproduced (an empty-string *result*
becomes Oracle `NULL`), the divergence is warned rather than silently shipped.
Function *inputs* are recovered where the maths allows it — `ASCII('')` → `0`,
`LOCATE('', …)` → `1` via `COALESCE` — because those specific results are
recoverable without representing `''` itself.

**Discussion.** Oracle has no on-disk representation for
an empty string separate from `NULL` — assigning `''` to a `VARCHAR2` column
stores `NULL`. `'' IS NULL` is **true** only on Oracle; `NVL('', 'x')` returns
`'x'` (Oracle's `NVL` sees `''` as absent), where `COALESCE('', 'x')` on
every other engine returns `''` unchanged. There is no statement-level
rewrite that can make a non-Oracle target reproduce Oracle's collapse (or
vice versa) without changing the column's actual storage semantics — a
documented, approved limit rather than a bug (`docs/03-unsupported.md` §2,
"Empty string as a distinct value → Oracle").

> **Warning** **Documented limit, warned.** Not `faithful` — no
> workaround exists in either direction; every occurrence carries a `UNIQUE:`
> note + warning rather than a silent value change.

**See Also.** Corpus [`ora-empty-is-null`](../../../tests/fixtures/challenge/challenge_oracle.sql), [`ora-empty-null`](../../../tests/fixtures/challenge/challenge_oracle.sql),
[`pg-empty-is-null`](../../../tests/fixtures/challenge/challenge_postgresql.sql) · [§2](../../03-unsupported.md), "Empty string as a distinct
value → Oracle" · [`UNIQUE-1207`](../../reference/warnings.md#unique-1207).

---
