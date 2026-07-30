# Strings, concatenation and collation

Why Unique emits what it emits for string constructs with no direct
cross-engine equivalent. See [README.md](README.md) for how this page is
built and its entry format.

### CONCAT / `||` NULL-propagation per engine

**Problem.** MySQL's `CONCAT(a, b, …)` **propagates** `NULL`: any
`NULL` argument makes the whole result `NULL`. PostgreSQL `||`, T-SQL `+`
(string context) and MySQL/PostgreSQL/T-SQL's own `CONCAT()` function all
propagate the same way. Oracle's `||` operator is the odd one out: it treats
`NULL` as an **empty string**, so `'a' || NULL || 'b'` = `'ab'`, not `NULL`.

**Solution.**

```sql
-- reda-ora-concat-null-cast, oracle → postgresql
SELECT 'a' || CAST(NULL AS VARCHAR2(10)) || 'b' AS r FROM DUAL;
-- =>
SELECT 'a' || 'b' AS r;   -- Oracle's own '' collapses the operand; folds to 'ab'

-- my-concat-null-col, mysql → postgresql / tsql / oracle
SELECT CONCAT(a, b) AS c FROM (SELECT 1 AS a, CAST(NULL AS CHAR) AS b) t;
-- =>
SELECT CASE
  WHEN a IS NULL OR b IS NULL THEN NULL
  ELSE CONCAT(a, b)
END AS c
FROM (SELECT 1 AS a, CAST(NULL AS TEXT) AS b) t;
```

A literal `NULL` operand of an Oracle-source `||` is
constant-folded away at transpile time. A **non-literal** possibly-`NULL`
operand (a `CAST(NULL AS …)`, or a column recognised as nullable) is guarded
with a `CASE WHEN <op> IS NULL … THEN NULL ELSE <concat> END` so the
propagation direction matches the source engine, whichever way it runs.

The reverse (Oracle as target of a propagating source) needs no CASE guard
when the operand is a bare literal `NULL`: `ora-concat-null` folds `'a' + 'b'`
(T-SQL) / `CONCAT('a', 'b')` (MySQL) / `'a' || 'b'` (PostgreSQL) — dropping
the literal reproduces Oracle's own empty-string treatment without needing a
runtime guard, since a compile-time-known `NULL` is gone either way.

**Discussion.** A straight operator/function copy
reverses the result on whichever side treats `NULL` differently. Going
**Oracle → other engines**, a bare `NULL` operand must be dropped so the
other engines' propagating `||`/`CONCAT` produces Oracle's `'ab'`, not the
propagating engines' own `NULL`. Going **MySQL → other engines**, a `NULL`
operand must instead be preserved (or synthesised) so the target's
non-propagating engines (Oracle) or operators still yield `NULL`. Two
sub-cases compound this: a **non-literal** `NULL` (`CAST(NULL AS
VARCHAR2(10))`, or a `NULL`-valued **column** known only at runtime) is not
visible to a compile-time literal check, so an early fix that only stripped
*literal* `NULL` left both holes open (`reda-ora-concat-null-cast`,
`my-concat-null-col` — both filed as class `func`/`lying-warning`: the only
signal was an unrelated internal "unread sqlglot arg" tripwire, not a message
describing the semantic loss).

> **Note** faithful in both directions — live-verified: T-SQL
> `'a' + 'b'` / PostgreSQL `'a' || 'b'` / MySQL `CONCAT('a', 'b')` all give
> `'ab'` matching Oracle's own `'ab'`; the guarded CASE gives MySQL's `NULL` on
> every target. No warning (the value is reproduced exactly, not merely
> approximated).

**See Also.** Corpus [`ora-concat-null`](../../tests/fixtures/challenge/challenge_oracle.sql), [`reda-ora-concat-null-cast`](../../tests/fixtures/challenge/challenge_oracle.sql),
[`my-concat-null`](../../tests/fixtures/challenge/challenge_mysql.sql), [`my-concat-null-col`](../../tests/fixtures/challenge/challenge_mysql.sql), [`ts-concat-null`](../../tests/fixtures/challenge/challenge_sqlserver.sql), [`pg-concat-null`](../../tests/fixtures/challenge/challenge_postgresql.sql) ·
`emit_expr.py:1869-1897` (`_emit_binary`, CONCAT dialect overrides, docstring).

---

### Oracle `'' ≡ NULL`

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
> note + warning rather than a silent value change. User-approved 2026-07-19.

**See Also.** Corpus [`ora-empty-is-null`](../../tests/fixtures/challenge/challenge_oracle.sql), [`ora-empty-null`](../../tests/fixtures/challenge/challenge_oracle.sql),
[`pg-empty-is-null`](../../tests/fixtures/challenge/challenge_postgresql.sql) · [§2](../03-unsupported.md), "Empty string as a distinct
value → Oracle" · [`UNIQUE-1207`](../reference/warnings.md#unique-1207).

---

### LIKE … ESCAPE mapping

**Problem.** `LIKE pattern ESCAPE 'c'` is SQL-standard: `c` escapes
a following `%`/`_` so it matches literally.

**Solution.**

```sql
-- reda-ts-like-escape, tsql → postgresql / oracle / mysql
SELECT a FROM t WHERE b LIKE '%x!%y%' ESCAPE '!';
-- => identical on all three targets
SELECT a FROM t WHERE b LIKE '%x!%y%' ESCAPE '!';
```

`LIKE … ESCAPE '…'` now passes through unchanged on
every target.

Separately, PostgreSQL and MySQL treat a bare backslash as their **default**
`LIKE` escape character (with no `ESCAPE` clause at all); Oracle and T-SQL
have **no** default escape. A pattern like `'a\%b'` therefore matches a
literal `%` on a PostgreSQL/MySQL source but a wildcard on an Oracle/T-SQL
target unless compensated — Unique adds an explicit `ESCAPE '\'` when a
backslash-containing `LIKE` pattern crosses from a PostgreSQL/MySQL source to
Oracle/T-SQL, to preserve the source's implicit escaping
(`emit_expr.py:1858-1864`).

**Discussion.** *Why there is no direct mapping — there isn't one, and the
old behaviour lied about it.* `ESCAPE` is supported **identically** by
PostgreSQL, Oracle and MySQL — a pure syntax passthrough. The transpiler used
to treat the `ESCAPE` clause as an "unmapped operator; no `<engine>` mapping"
and comment out the **entire** statement with a warning that misdescribed
reality (a mapping exists; nothing needed translating) — losing a valid,
portable construct entirely (`reda-ts-like-escape`, class `lying-warning`).

> **Note** faithful — live-verified true on all four
> engines. No warning (previously the whole statement was dropped; now
> nothing is).

**See Also.** Corpus [`reda-ts-like-escape`](../../tests/fixtures/challenge/challenge_sqlserver.sql) ·
`emit_expr.py:1858-1864` (backslash default-escape compensation, docstring).

---

### T-SQL LIKE character classes (`'[A-C]%'`) — open, observed divergence

**Problem.** T-SQL's `LIKE` supports bracketed **character
classes**: `'[A-C]%'` matches any string starting with `A`, `B` or `C`.
`'Bob' LIKE '[A-C]%'` is true (`1`) on T-SQL.

**Solution.**

```sql
-- tsql → postgresql / mysql / oracle (not a corpus case; reproduces the
-- FINDINGS.md observation against the current build)
SELECT CASE WHEN 'Bob' LIKE '[A-C]%' THEN 1 ELSE 0 END AS r;
-- =>
-- UNIQUE: string comparison result depends on each engine's default collation
-- (case/accent sensitivity) and trailing-space handling, which differ between
-- tsql and <target> — the boolean result may differ (docs/03-unsupported.md)
SELECT CASE
  WHEN 'Bob' LIKE '[A-C]%' THEN 1
  ELSE 0
END AS r;
```

*Current state — honestly, not fixed.* This is a **known, unresolved**
finding (`tests/fixtures/challenge/FINDINGS.md`, "Observations" section,
2026-07-30 batch), left **unscored** in the campaign because a warning *is*
emitted — but the warning is wrong. PostgreSQL, MySQL and Oracle treat `[` and
`]` as **literal characters** in a `LIKE` pattern (there is no bracket
character-class syntax in standard `LIKE`), so the pattern is passed through
verbatim and silently changes meaning: `'Bob' LIKE '[A-C]%'` is `0` (false)
on all three, because the string would have to *start* with the literal
character `[`. The example above was verified directly against the running
transpiler.

**Discussion.** The warning that fires is the generic **collation**
divergence note (case sensitivity, trailing spaces) — it is real
infrastructure, but it is attached here for the wrong reason: the actual
cause is that the T-SQL bracket character class is untranslated syntax, not a
collation difference, and the warning text never says so.

*What would fix it (not yet done).* Either translate the bracket class to
each target's equivalent (PostgreSQL/Oracle: rewrite to a `SIMILAR
TO`/`REGEXP_LIKE` form or a per-character `OR` chain; MySQL: `REGEXP`), or at
minimum emit a warning that names the real cause instead of the collation
boilerplate.

> **Warning** **Silent-in-effect** (a warning fires, but names
> the wrong mechanism) — this page documents current behaviour, not the
> approved-limit status the other collation entries below have. Not `faithful`,
> not (yet) a correctly-documented limit.

**See Also.** `tests/fixtures/challenge/FINDINGS.md`, "Observations (not
scored — dedup/borderline, for BLUE/PURPLE)" section, 2026-07-30 batch entry
"T-SQL LIKE `'[A-C]%'` character class".

---

### Negative/zero REPEAT/REPLICATE clamps

**Problem.** PostgreSQL `repeat(s, n)` and MySQL `REPEAT(s, n)` with
`n <= 0` return an empty string `''`.

**Solution.**

```sql
-- pg-repeat-negative, postgresql → tsql
SELECT repeat('ab', -1) AS r;
-- =>
SELECT REPLICATE('ab', CASE WHEN ROUND(-1, 0) < 0 THEN 0 ELSE ROUND(-1, 0) END) AS r;
-- => oracle
SELECT '' /* UNIQUE: Oracle stores an empty string as NULL (docs/03-unsupported.md) */ AS r
FROM DUAL;
```

T-SQL clamps the count to `0` before calling
`REPLICATE` (`REPLICATE` of `0` is `''`, matching PostgreSQL); Oracle keeps
its own `RPAD` emulation and warns, since the Oracle-side result is `NULL`
either way (the `'' ≡ NULL` limit, not a clamp bug).

**Discussion.** T-SQL's `REPLICATE(s, n)` and the
`RPAD(s, LENGTH(s)*n, s)` emulation used for Oracle both return `NULL` for a
negative count, not `''` — a different value class entirely, and on Oracle,
compounded by Oracle's own `'' ≡ NULL` (above), so an Oracle target *cannot*
represent PostgreSQL/MySQL's `''` result distinctly from `NULL` regardless of
the clamp (`pg-repeat-negative`, class `func`).

> **Note** faithful on T-SQL (clamped to `''`, matching
> PostgreSQL/MySQL). **Warned limit** on Oracle — not a clamp defect, the same
> `'' ≡ NULL` limit documented above.

**See Also.** Corpus [`pg-repeat-negative`](../../tests/fixtures/challenge/challenge_postgresql.sql) ·
[§2](../03-unsupported.md), "Empty string as a distinct value → Oracle" ·
[`UNIQUE-1082`](../reference/warnings.md#unique-1082).

---

### SUBSTRING negative/zero start semantics per engine

**Problem.** T-SQL and PostgreSQL `SUBSTRING(s, start, len)` treat a
`start < 1` as counting *backwards from the length*: out-of-range leading
positions still consume `len`, they just don't emit characters for them.
`SUBSTRING('hello', 0, 3)` = `'he'` (positions 0, 1, 2 requested; position 0
doesn't exist, so only 1–2 are returned — 2 characters, not 3).

**Solution.**

```sql
-- reda-ts-substring-zero-start, tsql → mysql / oracle
SELECT SUBSTRING('hello', 0, 3) AS r;
-- => both targets
SELECT SUBSTR('hello', 1, 2) AS r;

-- pg-substr-zero, postgresql → mysql / oracle (same rebase, PG source)
SELECT SUBSTRING('abcdef', 0, 3) AS r;
-- =>
SELECT SUBSTR('abcdef', 1, 2) AS r;
```

A `start <= 0` argument is rebased to T-SQL/PostgreSQL
semantics for MySQL and Oracle: `start` becomes `1` and `len` is reduced by
`1 - start` (the count of out-of-range leading positions that no longer need
representing).

The 2-argument form (`SUBSTRING(s, start)`, no length) gets the equivalent
treatment: a `start <= 0` on PostgreSQL (which runs from the beginning) is
rewritten to an explicit `start = 1` for MySQL/Oracle/T-SQL, none of which
share PostgreSQL's "runs from the start" reading of an out-of-range start:

```sql
-- pg-fsubstr, postgresql → tsql / oracle / mysql
SELECT substring('abc', 0);
-- => tsql
SELECT SUBSTRING('abc', 1, LEN('abc'));
-- => oracle
SELECT SUBSTR('abc', 1) FROM DUAL;
-- => mysql
SELECT SUBSTR('abc', 1);
```

**Discussion.** MySQL's `SUBSTRING(s, 0, n)` treats
position `0` as simply invalid and returns `''` (empty). Oracle's `SUBSTR(s,
0, n)` instead **clamps** `0` up to `1` and returns `n` characters from
there — `SUBSTR('hello', 0, 3)` = `'hel'`. Three engines, three different
results for the same call shape, and the original code passed the call
through unchanged with no warning (`reda-ts-substring-zero-start`, class
`func`; live: tsql=`'he'`, pg=`'he'`, mysql=`''`, oracle=`'hel'`).

> **Note** faithful — live-verified `'he'` (tsql) / `'he'`
> (pg source) reproduced as `'he'` on MySQL/Oracle post-rebase (was `''` /
> `'hel'` before the fix); `('abc','abc','bc')` verified on all three for the
> 2-arg form. No warning.

**See Also.** Corpus [`reda-ts-substring-zero-start`](../../tests/fixtures/challenge/challenge_sqlserver.sql), [`pg-substr-zero`](../../tests/fixtures/challenge/challenge_postgresql.sql),
[`pg-fsubstr`](../../tests/fixtures/challenge/challenge_postgresql.sql) · [`TestPgSubstringZeroStart`](../../tests/integration/test_challenge.py)
(pinned).

---

### DATALENGTH byte-vs-char lengths (UTF-16 caveat)

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

**See Also.** Corpus [`ts-binary-length`](../../tests/fixtures/challenge/challenge_sqlserver.sql), [`reda-ts-datalength-nchar`](../../tests/fixtures/challenge/challenge_sqlserver.sql) ·
`emit_functions.py:3094-3115` (docstring) ·
[§2](../03-unsupported.md), "`LENGTH` bytes-vs-chars".

---

### SOUNDEX as the canonical unmapped-builtin gate example

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
oversight. This is the reference example the built-in catalog gate
(`docs/03-unsupported.md` §2.1) is written around: a call that is a built-in
of the *source* engine (so it is clearly meant to run, not a user object)
but absent from the *target*'s catalog degrades the **whole statement**
rather than shipping a call the target engine would reject outright.

> **Warning** **Documented limit, warned** — a carrier + the
> `docs/03-unsupported.md` §2.1 catalog entry (`unsupported` finding), never a
> silently-invalid `SOUNDEX(...)` call on PostgreSQL. Deliberately **not**
> special-cased with a hand-built `SOUNDEX` emulation — it is kept as the
> worked example of the general unmapped-built-in gate mechanism, which is
> meant to catch the long tail of similar gaps (`GENERATE_SERIES`→Oracle,
> `LISTAGG`→MySQL, `INITCAP`→T-SQL/MySQL, …) rather than being patched one
> function at a time.

**See Also.** Corpus [`ora-soundex`](../../tests/fixtures/challenge/challenge_oracle.sql), [`ora-soundex3`](../../tests/fixtures/challenge/challenge_oracle.sql), [`my-soundex-format`](../../tests/fixtures/challenge/challenge_mysql.sql) ·
[§2.1](../03-unsupported.md), "Unmapped built-in scalar functions" ·
[`_untranslated_source_builtin`](../../src/unique/core/output_gate.py),
`gate_reason` · [`UNIQUE-1151`](../reference/warnings.md#unique-1151).

---

### Collation and ordering divergences — documented limits

**Problem.** String equality, `ORDER BY`, `DISTINCT`, `GROUP BY` and
`LIKE` all compare under the source engine's **default collation** — case
sensitivity, accent sensitivity, and trailing-space handling are properties
of that collation, not of the SQL text.

**Solution.**

```sql
-- pg-order-nulls-default, postgresql → mysql
SELECT x FROM (VALUES (3),(1),(NULL)) v(x) ORDER BY x;
-- =>
SELECT x
FROM (SELECT 3 AS x UNION ALL SELECT 1 UNION ALL SELECT NULL) v
ORDER BY CASE WHEN x IS NULL THEN 1 ELSE 0 END, x ASC;
```

A related but **fixable** case is `NULL`-ordering default: PostgreSQL and
Oracle sort `NULL` **high** (last, ascending) by default; MySQL and T-SQL
sort it **low** and have no `NULLS FIRST/LAST` keyword to ask for the other
order explicitly. This *is* statement-compensable — the source order can be
reconstructed with a leading priority key — so it is not a limit but a
`faithful` rewrite.

**Discussion.** Collation is a **per-column** (or
connection-default) property that a statement like `SELECT 'a ' = 'a'` does
not carry any trace of — there is nothing in the transpiled text to compile
against. T-SQL's default collation is case-insensitive and (per SQL Server's
padding rules) ignores trailing spaces in comparison, so `'a '='a'` is true
there; PostgreSQL/Oracle/MySQL's typical defaults are case- and
space-sensitive, so the same comparison is false. No statement-level rewrite
can bridge this without knowing the actual target column collation, which
Unique does not have visibility into — an **approved limit**, not a bug
(`docs/03-unsupported.md` §2, "String collation in `=`/`ORDER BY`/`DISTINCT`/
`LIKE`", user-approved 2026-07-18):

```sql
-- ts-trailing-eq, tsql → mysql / oracle / postgresql
SELECT IIF('a ' = 'a', 1, 0) AS r;
-- T-SQL: 1 (true, CI + space-insensitive default).  Others: 0 (false).
```

MySQL's/T-SQL's default **case-insensitive** collation additionally changes
what `DISTINCT`/`GROUP BY`/`ORDER BY` themselves consider equal — `'a'` and
`'A'` collapse into one row under `DISTINCT` on MySQL/T-SQL but stay two rows
on the case-sensitive PostgreSQL/Oracle defaults. This is a **row-count**
divergence, not just a display/order difference, and cannot be bridged by an
`ORDER BY LOWER(x)` rewrite (invalid under `DISTINCT`, since the sort key
would not be in the select list, and it does not change what `DISTINCT`
itself deduplicates) — documented separately as its own limit
(`docs/03-unsupported.md` §3.14).

> **Warning** `NULL`-ordering: `faithful` (live-verified
> reconstruction). Case/accent/trailing-space **comparison** results and
> case-insensitive **deduplication** row counts: **documented limits, warned**
> — no workaround exists without column-level collation visibility Unique does
> not have.

**See Also.** Corpus [`ts-trailing-eq`](../../tests/fixtures/challenge/challenge_sqlserver.sql), [`ts-trailing-space-cmp`](../../tests/fixtures/challenge/challenge_sqlserver.sql),
[`pg-order-nulls-default`](../../tests/fixtures/challenge/challenge_postgresql.sql), [`my-distinct-case`](../../tests/fixtures/challenge/challenge_mysql.sql), [`my-group-case`](../../tests/fixtures/challenge/challenge_mysql.sql) ·
[§2](../03-unsupported.md), "String collation in `=`/`ORDER BY`/`DISTINCT`/
`LIKE`" · §3.14, "Case-Insensitive Collation Under DISTINCT / ORDER BY" ·
[`TestNullOrderingEmulation`](../../tests/integration/test_challenge.py) (pinned) ·
[`UNIQUE-1015`](../reference/warnings.md#unique-1015).
