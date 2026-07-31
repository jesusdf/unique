[← Procedural: cursors, dynamic SQL, system procedures, session directives](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=procedural type="Convert/HASHBYTES wrapper collapse" direction="tsql → postgresql" kind=article order=59 -->

# T-SQL `HASHBYTES('SHA2_256', x)` → PostgreSQL `sha256`, wrapped for a character argument

**Problem.** sqlglot canonicalizes T-SQL's `HASHBYTES('SHA2_256', x)` to a
bare `SHA256(x)` call reaching PostgreSQL, but PostgreSQL's `sha256`
takes a **bytea**, not text — `sha256(x)` over a character column is
"function sha256(text) does not exist" at *runtime*, a defect a
compile-only validity check does not catch (the call parses fine; it just
never runs).

**Solution.**

```sql
-- tests/integration/test_function_translation.py::TestTsqlHashBytesToPostgresql
CREATE TABLE t (x VARCHAR(50));
SELECT HASHBYTES('SHA2_256', x) FROM t
-- tsql -> postgresql:
SELECT UPPER(ENCODE(SHA256(CONVERT_TO(x, 'UTF8')), 'hex')) FROM t;
```

**Discussion.** The character argument is wrapped in `CONVERT_TO(x,
'UTF8')` first, turning it into the `bytea` PostgreSQL's `sha256` expects
(the same wrapper the Oracle-source hash path already uses), and the
resulting binary digest is rendered back to the uppercase hex string
`HASHBYTES` itself returns via `UPPER(ENCODE(..., 'hex'))`. A column
already typed `bytea`/`RAW` on the source skips the wrapper — it is
already the right shape.

This is **faithful only for a non-Unicode (`VARCHAR`) argument**: T-SQL,
Oracle and PostgreSQL all hash the same UTF-8 bytes for a `VARCHAR` value,
so the digest matches byte-for-byte. A **Unicode (`NVARCHAR`)** argument
does not: T-SQL's `HASHBYTES` hashes the UTF-16LE bytes an `NVARCHAR`
value is actually stored as, Oracle's `NVARCHAR2` hashes UTF-16BE, and
PostgreSQL `text` — which has no UTF-16 encoding for `CONVERT_TO` to
target — only ever hashes UTF-8. These are three genuinely different
byte sequences for the same characters, not a rounding or formatting
difference to compensate for; there is no wrapper that makes them agree.
This is why the procedures-corpus routine that hashes an `NVARCHAR`
argument this way is a **permanent** functional-equivalence exclusion
rather than a bug to fix (see the citation below) — the divergence is
inherent to each engine's storage encoding, not a translation gap.

> **Note** faithful for a `VARCHAR`/non-Unicode argument — live-verified
> byte-for-byte identical against Oracle and T-SQL. **Divergent** for an
> `NVARCHAR`/Unicode argument — permanently different digest bytes across
> engines; not a warned-per-statement carrier, but a documented,
> unresolvable functional-equivalence exclusion.

**See Also.** [`test_function_translation.py::TestTsqlHashBytesToPostgresql`](../../../tests/integration/test_function_translation.py) ·
[`tests/helpers/procedures_fe_exclusions.py`](../../../tests/helpers/procedures_fe_exclusions.py)
(`func4` — the permanent NVARCHAR-hash exclusion) · [§2](../../03-unsupported.md),
"Engine-Specific Features with No Equivalent" (`HASHBYTES` digest value —
the NVARCHAR residual) · [`CONVERT(...,HASHBYTES(...),2)` style-2 hex
wrapper collapse → MySQL](convert-hashbytes-wrapper-collapse.md) (the
sibling entry for the `CONVERT`-wrapped form reaching MySQL).
