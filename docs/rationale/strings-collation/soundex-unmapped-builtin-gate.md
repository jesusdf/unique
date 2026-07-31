[← Strings, concatenation and collation](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=strings-collation type="Unmapped built-ins" direction="cross-engine" kind=article order=12 direction-inferred=true -->

# SOUNDEX as the canonical unmapped-builtin gate example

**Problem.** Oracle and T-SQL's `SOUNDEX(s)` is a native phonetic
built-in.

**Solution.**

```sql
-- ora-soundex, oracle → postgresql
SELECT SOUNDEX('Smith') AS r FROM DUAL;
-- =>
-- UNIQUE: output failed the postgresql validity check (untranslated oracle
-- built-in SOUNDEX() (no postgresql form)); original oracle batch preserved:
-- SELECT SOUNDEX('Smith') AS r FROM DUAL
```

The statement is preserved as a `UNIQUE:` carrier
comment naming the unmapped function, with a `validity_gate` warning — never
the bare, invalid `SOUNDEX(...)` call shipped to a target that lacks it.

`SOUNDEX` → T-SQL and `SOUNDEX` → Oracle (as a source-native call reaching a
target that *does* have it) pass through unchanged — only the PostgreSQL leg
degrades. `my-soundex-format` confirms `FORMAT(x, d)` translates cleanly
alongside a `SOUNDEX` call in the same statement — the degrade is scoped to
`SOUNDEX` specifically, not the whole function-name-resolution path.

**Discussion.** PostgreSQL has no `SOUNDEX` in its base
catalog (it lives only in the optional `fuzzystrmatch` extension, which
Unique cannot assume is installed on the target database) — a genuine,
source-engine-built-in-but-target-has-no-form gap, not an implementation
oversight. A call that is a built-in of the *source* engine (so it is
clearly meant to run, not a user object) but absent from the *target*'s
catalog degrades the **whole statement** rather than shipping a call the
target engine would reject outright.

> **Warning** **Documented limit, warned** — a carrier + the
> `docs/03-unsupported.md` §2.1 catalog entry, never a silently-invalid
> `SOUNDEX(...)` call on PostgreSQL. No bespoke `SOUNDEX` emulation is
> substituted; the same general unmapped-built-in handling applies to any
> other source built-in missing from a target's catalog
> (`GENERATE_SERIES`→Oracle, `LISTAGG`→MySQL, `INITCAP`→T-SQL/MySQL, …).

**See Also.** Corpus [`ora-soundex`](../../../tests/fixtures/challenge/challenge_oracle.sql), [`ora-soundex3`](../../../tests/fixtures/challenge/challenge_oracle.sql), [`my-soundex-format`](../../../tests/fixtures/challenge/challenge_mysql.sql) ·
[§2.1](../../03-unsupported.md), "Unmapped built-in scalar functions" ·
[`_untranslated_source_builtin`](../../../src/unique/core/output_gate.py),
`gate_reason` · [`UNIQUE-1151`](../../reference/warnings.md#unique-1151).

---
