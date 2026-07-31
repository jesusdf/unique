[← Strings, concatenation and collation](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=strings-collation type="LIKE and pattern matching" direction="postgresql → oracle/mysql" kind=article order=18 -->

# PostgreSQL `regexp_replace` flags → Oracle/MySQL positional occurrence + backreference respelling

**Problem.** PostgreSQL's `regexp_replace(source, pattern, replacement,
flags)` fourth argument is a **flags string** (`'g'` for global, `'i'` for
case-insensitive, …); Oracle's and MySQL's `REGEXP_REPLACE` instead take a
**numeric** occurrence/position argument in that slot, and both already
replace every match by default. A literal translation would leak the flags
string into a numeric argument position — an error, not a degraded result.

**Solution.**

```sql
-- pg-regexp-backref, postgresql → oracle / mysql
SELECT regexp_replace('a1b2', '(\d)', '[\1]', 'g') AS r;
-- => oracle
SELECT REGEXP_REPLACE('a1b2', '(\d)', '[\1]') AS r FROM DUAL;
-- => mysql
SELECT REGEXP_REPLACE('a1b2', '(\\d)', '[$1]') AS r;
```

The `'g'` flag is simply dropped rather than passed through as a bogus
positional argument, since Oracle and MySQL are already global by default —
no argument at all reproduces it. Going to MySQL specifically, the
pattern's backslashes are doubled (MySQL's `REGEXP_REPLACE` pattern is a
string literal that itself needs escaping) and backreferences are respelled
from PostgreSQL's `\N` syntax to MySQL's `$N`. Both targets return
`'a[1]b[2]'`, matching PostgreSQL.

**Discussion.** PostgreSQL's flags argument packs several independent
regex-engine options into one string (`g` global, `i` case-insensitive,
`n`/`m` line-mode, …); Oracle and MySQL split the same information across
a *numeric* occurrence-position argument and separate case-sensitivity
handling, with global replacement as their unconditional default. Reading
the flags string as if it belonged in the numeric slot instead — which is
what a value-blind rename would do — produces a runtime type error, not
just a wrong result, so the flags string is parsed and translated:
`g` maps to "no argument needed" (both targets are already global),
and other flags map to their per-target equivalent where one exists. The
pattern and replacement strings additionally need re-escaping for MySQL,
whose backslash and backreference conventions inside a `REGEXP_REPLACE`
string literal differ from PostgreSQL's own.

> **Note** faithful — live-verified `'a[1]b[2]'` on both Oracle and MySQL,
> matching PostgreSQL's `regexp_replace('a1b2', '(\d)', '[\1]', 'g')`.

**See Also.** Corpus [`pg-regexp-backref`](../../../tests/fixtures/challenge/challenge_postgresql.sql) ·
[`TestRegexpReplaceFlags`](../../../tests/integration/test_challenge.py).
