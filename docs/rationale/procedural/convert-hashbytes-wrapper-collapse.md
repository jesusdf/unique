[← Procedural: cursors, dynamic SQL, system procedures, session directives](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=procedural type="CONVERT(...,HASHBYTES(...),2) style-2 hex wrapper collapse" direction="tsql → mysql" kind=article order=55 -->

# T-SQL `CONVERT(NVARCHAR(MAX), HASHBYTES(...), 2)` → MySQL's native hash function directly

**Problem.** T-SQL has no built-in "digest as a hex string" function —
`HASHBYTES(...)` returns raw bytes, so the idiomatic way to get a
readable hex digest is to wrap it in `CONVERT(NVARCHAR(MAX), HASHBYTES(...),
2)`, where style `2` is `CONVERT`'s binary-to-hex-string style code.
MySQL's own hash functions (`SHA2`, `MD5`, ...) already return a hex
string directly — carrying the `CONVERT(..., 2)` wrapper across verbatim
would double-encode the digest, or simply fail since MySQL's `CONVERT` has
no matching style-code argument.

**Solution.**

```sql
-- tests/unit/core/test_ir_first_families.py::TestStyledConvertInIr::test_hash_wrapper_style_2_drops_on_mysql
SELECT CONVERT(NVARCHAR(MAX), HASHBYTES('SHA2_256', x), 2) FROM t
-- tsql -> mysql:
SELECT SHA2(x, 256) FROM t
```

**Discussion.** Unique recognizes the whole `CONVERT(..., HASHBYTES(algo,
arg), 2)` shape as a single unit — a "hash and hex-encode" idiom — rather
than translating the `CONVERT` and `HASHBYTES` calls independently, and
collapses it to a single call against MySQL's own `SHA2(arg, bits)`, which
already returns the hex string the two-call T-SQL idiom builds by hand. The
algorithm name (`'SHA2_256'`) is read to pick the matching bit-length
argument (`256`) MySQL's `SHA2` expects.

> **Note** faithful — `SHA2(x, 256)` produces the identical hex digest
> `CONVERT(NVARCHAR(MAX), HASHBYTES('SHA2_256', x), 2)` would have. No
> warning.

**See Also.** [`test_ir_first_families.py::TestStyledConvertInIr`](../../../tests/unit/core/test_ir_first_families.py)
(`test_hash_wrapper_style_2_drops_on_mysql`,
`test_hash_wrapper_style_2_sha256_on_postgresql`) ·
[§2](../../03-unsupported.md), "Engine-Specific Features with No
Equivalent" (`HASHBYTES` digest value → PostgreSQL/Oracle — the sibling
entry for the bare, un-wrapped call against those two targets).
