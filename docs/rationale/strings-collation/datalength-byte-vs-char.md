[← Strings, concatenation and collation](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=strings-collation type="Length and encoding" direction="cross-engine" kind=article order=11 direction-inferred=true -->

# DATALENGTH byte-vs-char lengths (UTF-16 caveat)

**Problem.** T-SQL `DATALENGTH(x)` returns the storage **byte**
length of `x`, not its character count.

**Solution.**

```sql
-- reda-ts-datalength-nchar, tsql → postgresql / mysql / oracle
SELECT DATALENGTH(N'abc') AS r;
-- => all three targets
SELECT 6 AS r;
```

For a **national literal** operand, the byte count is
computed exactly at transpile time by UTF-16-LE-encoding the literal's Python
string value (correctly handling supplementary-plane characters via UTF-16
surrogate pairs) and folding the whole call to that constant — sidestepping
the byte-vs-char question entirely for a compile-time-known value.

A non-national (`VARCHAR`/`VARBINARY`) argument still routes to
`OCTET_LENGTH`/`LENGTHB`, and a `VARBINARY(MAX)` cast wrapper is unwrapped
first (the byte length of a string is unaffected by a same-length binary
reinterpretation).

**Discussion.** PostgreSQL/MySQL's `OCTET_LENGTH` and
Oracle's `LENGTHB` are the byte-length equivalents and match `DATALENGTH`
exactly for an ordinary (single-byte-per-char-class) `VARCHAR`/`VARBINARY`
argument (`ts-binary-length`). But T-SQL's `NVARCHAR`/`N'…'` national strings
are stored as **UTF-16** — 2 bytes per code unit — so `DATALENGTH(N'abc')` =
`6`, whereas `OCTET_LENGTH('abc')` on a UTF-8-decoded target is `3`. The `N`
prefix was originally dropped during translation, silently halving the byte
count with no warning (`reda-ts-datalength-nchar`, class `func`; live:
tsql=`6`, pg=`3`).

> **Note** faithful for a national **literal** (exact UTF-16
> byte count folded at compile time). A national **column** whose value is only
> known at runtime is not literal-foldable and still routes through
> `OCTET_LENGTH` of the UTF-8 rendering — the same byte-vs-char divergence as
> the general `LENGTH` limit (`docs/03-unsupported.md` §2), inherited rather
> than specifically warned for `DATALENGTH` of a column.

**See Also.** Corpus [`ts-binary-length`](../../../tests/fixtures/challenge/challenge_sqlserver.sql), [`reda-ts-datalength-nchar`](../../../tests/fixtures/challenge/challenge_sqlserver.sql) ·
`emit_functions.py:3094-3115` (docstring) ·
[§2](../../03-unsupported.md), "`LENGTH` bytes-vs-chars".

---
