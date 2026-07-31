[← Strings, concatenation and collation](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=strings-collation type="String function argument/edge cases" direction="tsql → oracle/postgresql/mysql" kind=article order=28 -->

# T-SQL `NCHAR(n)` Unicode code point → PostgreSQL `CHR`, MySQL `CHAR(... USING utf32)`, Oracle `NCHR`/`UNISTR`

**Problem.** T-SQL's `NCHAR(n)` returns the character for Unicode code
point `n` — an integer argument (a `0x…` literal is still a *number*
there, not a byte string) — with no matching built-in on any other engine
under that name.

**Solution.**

```sql
-- tests/fixtures/challenge/challenge_sqlserver.sql (ts-ascii-char)
SELECT NCHAR(65) AS r
-- tsql -> oracle:
SELECT NCHR(65) AS r FROM DUAL;
```

```sql
-- tests/fixtures/challenge/challenge_sqlserver.sql (ts-nchar-hex), a
-- supplementary-plane code point (U+1F600, 😀) beyond Oracle NCHR's range:
SELECT NCHAR(0x1F600) AS r
-- tsql -> postgresql:
SELECT CHR(128512) AS r;
-- tsql -> mysql:
SELECT CHAR(128512 USING utf32) AS r;
-- tsql -> oracle (NCHR truncates > U+FFFF to 16 bits, so this uses a
-- UTF-16 surrogate pair instead):
SELECT UNISTR('\D83D\DE00') AS r FROM DUAL;
```

**Discussion.** PostgreSQL's `CHR(n)` and MySQL's `CHAR(n USING utf32)`
both already accept a full Unicode code point directly (MySQL needs the
explicit `utf32` charset — its bare `CHAR(n)` would instead treat `n` as
raw bytes). Oracle's `NCHR(n)` is a like-for-like match for any code point
within the Basic Multilingual Plane (`U+0000`–`U+FFFF`), but it only
understands a 16-bit argument and truncates anything above that range —
so a supplementary character (`U+1F600` needs 21 bits) can't go through
`NCHR` at all. For those, Oracle's `UNISTR('\HHHH\LLLL')` is used instead,
spelling the code point as its UTF-16 **surrogate pair** (the same two
16-bit units a UTF-16 string would encode it as) — the same mechanism
`NVARCHAR` storage itself relies on internally, just written out
literally.

> **Note** faithful — live-verified: `NCHAR(0x1F600)` (😀, U+1F600)
> reproduces the identical character on PostgreSQL, MySQL and Oracle.

**See Also.** Corpus [`ts-ascii-char`, `ts-nchar-hex`](../../../tests/fixtures/challenge/challenge_sqlserver.sql)
· [`TestNcharCharCodePoint`](../../../tests/integration/test_challenge.py) ·
[§3.16](../../03-unsupported.md), "`NCHAR(n)` Unicode Code Point".
