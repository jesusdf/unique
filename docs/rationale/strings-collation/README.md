[← All rationale topics](../README.md)

# Strings, concatenation and collation

Why Unique emits what it emits for string constructs with no direct
cross-engine equivalent. See [README.md](../README.md) for how this page is
built and its entry format.

> **Generated file — do not edit by hand.** Produced by `python scripts/generate_rationale_index.py` from the article pages in this directory; the intro above comes from `_intro.md`. The CI freshness gate (`python scripts/generate_rationale_index.py --check`) fails the build if it drifts.

## Concatenation

| Article | Direction | Description |
|---|---|---|
| [CONCAT / `\|\|` NULL-propagation per engine](concat-null-propagation.md) | cross-engine | MySQL's `CONCAT(a, b, …)` **propagates** `NULL`: any `NULL` argument makes the whole result `NULL`. |
| [Numeric-operand `\|\|`/`CONCAT` casting (Oracle/MySQL → T-SQL, → PostgreSQL)](numeric-operand-concatenation-casting.md) | cross-engine | Oracle's `\|\|` and MySQL's `CONCAT` implicitly stringify a numeric operand: `2 \|\| 3` is the two-character string `'23'`. |

## NULL and empty-string semantics

| Article | Direction | Description |
|---|---|---|
| [`GREATEST`/`LEAST` NULL-propagation per engine](greatest-least-null-propagation.md) | cross-engine | MySQL and Oracle's `GREATEST`/`LEAST` return `NULL` if *any* argument is `NULL`. |
| [`REPLACE` and `NULL`: Oracle's 2-arg form vs MySQL's propagation](replace-and-null.md) | cross-engine | Two independent `REPLACE`/`NULL` divergences. |
| [Oracle `'' ≡ NULL`](oracle-empty-string-is-null.md) | oracle → all | Every other engine stores and compares an empty string `''` as a distinct, zero-length value: `'' IS NULL` is false, `COALESCE('', 'x')` is `''`. |

## LIKE and pattern matching

| Article | Direction | Description |
|---|---|---|
| [LIKE … ESCAPE mapping](like-escape-mapping.md) | cross-engine | `LIKE pattern ESCAPE 'c'` is SQL-standard: `c` escapes a following `%`/`_` so it matches literally. |
| [T-SQL LIKE character classes (`'[A-C]%'`) → SIMILAR TO / REGEXP / REGEXP_LIKE](tsql-like-character-classes.md) | cross-engine | T-SQL's `LIKE` supports bracketed **character classes**: `'[A-C]%'` matches any string starting with `A`, `B` or `C`. |
| [PostgreSQL `regexp_replace` flags → Oracle/MySQL positional occurrence + backreference respelling](regexp-replace-flags-and-backreferences.md) | postgresql → oracle/mysql | PostgreSQL's `regexp_replace(source, pattern, replacement, flags)` fourth argument is a **flags string** (`'g'` for global, `'i'` for case-insensitive, …); Oracle's and MySQL's `REGEXP_REPLACE` instead take a **numeric** occurrence/position argument in that slot, and both already replace every match by default. |

## Repeat, substring and splice

| Article | Direction | Description |
|---|---|---|
| [Negative/zero REPEAT/REPLICATE clamps](repeat-replicate-clamps.md) | cross-engine | PostgreSQL `repeat(s, n)` and MySQL `REPEAT(s, n)` with `n <= 0` return an empty string `''`. |
| [SUBSTRING negative/zero start semantics per engine](substring-negative-start.md) | cross-engine | T-SQL and PostgreSQL `SUBSTRING(s, start, len)` treat a `start < 1` as counting *backwards from the length*: out-of-range leading positions still consume `len`, they just don't emit characters for them. |
| [Positional string-splice: `OVERLAY`/`STUFF`/`INSERT` (PostgreSQL/T-SQL/MySQL) → all targets](overlay-stuff-insert-splice.md) | tsql/postgresql/mysql → all | Three engines each have a native "replace `len` characters of `string` at 1-based position `start` with `new`" function: PostgreSQL's `OVERLAY(string PLACING new FROM start [FOR len])`, T-SQL's `STUFF(string, start, len, new)`, MySQL's `INSERT(string, start, len, new)`. |
| [String-function positional-argument edge cases: negative `LEFT`, T-SQL `LEN` trailing spaces, MySQL fractional rounding](string-function-argument-edge-cases.md) | cross-engine | `LEFT`/`SUBSTRING`/`REPEAT`'s position and length arguments, and T-SQL `LEN`, each have one engine-specific edge-case rule that a literal translation would silently drop: PostgreSQL's `LEFT(s, -n)` means something different from a plain clamp, T-SQL's `LEN` counts differently from every other engine's length function, and MySQL rounds a fractional numeric argument where the other engines truncate it. |
| [3-argument `CHARINDEX(needle, s, start)` (T-SQL) → PostgreSQL zero-guarded `POSITION`](charindex-start-argument-zero-guard.md) | tsql → postgresql | T-SQL's `CHARINDEX(needle, s, start)` searches only from `start` onward, and returns `0` (not `NULL`) when the needle isn't found anywhere from `start` on. |

## Trimming

| Article | Direction | Description |
|---|---|---|
| [Character-set `TRIM(chars FROM string)` → Oracle](trim-chars-from-string-to-oracle.md) | cross-engine | `TRIM([BOTH\|LEADING\|TRAILING] chars FROM string)` strips every occurrence of any character in `chars` from the string (both ends by default). |
| [Oracle `LTRIM(s, chars)`/`RTRIM(s, chars)` → `TRIM(LEADING/TRAILING chars FROM s)`](oracle-ltrim-rtrim-charset-reverse.md) | oracle → tsql/postgresql/mysql | This is the reverse of [Character-set `TRIM(chars FROM string)` → Oracle](trim-chars-from-string-to-oracle.md): Oracle's own `LTRIM`/`RTRIM` already accept a multi-character trim set as their second argument natively. |

## Length and encoding

| Article | Direction | Description |
|---|---|---|
| [DATALENGTH byte-vs-char lengths (UTF-16 caveat)](datalength-byte-vs-char.md) | cross-engine | T-SQL `DATALENGTH(x)` returns the storage **byte** length of `x`, not its character count. |

## Unmapped built-ins

| Article | Direction | Description |
|---|---|---|
| [SOUNDEX as the canonical unmapped-builtin gate example](soundex-unmapped-builtin-gate.md) | cross-engine | Oracle and T-SQL's `SOUNDEX(s)` is a native phonetic built-in. |

## Collation and ordering

| Article | Direction | Description |
|---|---|---|
| [Collation and ordering divergences — documented limits](collation-and-ordering-limits.md) | cross-engine | String equality, `ORDER BY`, `DISTINCT`, `GROUP BY` and `LIKE` all compare under the source engine's **default collation** — case sensitivity, accent sensitivity, and trailing-space handling are properties of that collation, not of the SQL text. |
| [Case-sensitivity compensation on string-literal operands (cross-engine)](literal-collation-compensation.md) | cross-engine | PostgreSQL and Oracle's default collations compare strings **case-sensitively**; MySQL's and T-SQL's default collations compare **case-insensitively**. |

## Operator precedence

| Article | Direction | Description |
|---|---|---|
| [Bitwise/arithmetic operator-precedence parentheses (MySQL/Oracle ↔ PostgreSQL/T-SQL)](bitwise-arithmetic-precedence-parens.md) | cross-engine | `&`, `\|` and `<<`/`>>` bind **looser** than `+`/`*` on MySQL and Oracle, but **tighter** than `+`/`*` on PostgreSQL and T-SQL. |
| [Unary bitwise `~x`/NOT → Oracle `-(x) - 1`, MySQL `CAST(~x AS SIGNED)`](unary-bitwise-not-emulation.md) | postgresql/tsql → oracle/mysql | PostgreSQL and T-SQL's unary bitwise NOT (`~x`) has no direct spelling on Oracle at all (PL/SQL has no bitwise NOT operator or built-in), and MySQL's `~x` operates on an *unsigned* 64-bit integer, so a plain `~5` there returns a huge unsigned complement rather than the signed `-6` the source engine intended. |

## Hex/binary literal folding

| Article | Direction | Description |
|---|---|---|
| [A T-SQL hex/binary literal used in arithmetic → folded to its integer value](hex-binary-literal-arithmetic-fold.md) | tsql → postgresql/oracle/mysql | T-SQL's `0x0A` is a binary-string literal that also behaves as an integer in numeric contexts (`0x0A + 5` = `15`). |

## DECODE mixed-type branches

| Article | Direction | Description |
|---|---|---|
| [Oracle `DECODE` with mixed-type result branches → `CASE` with a `CAST` inserted to unify types](decode-mixed-type-branch-cast.md) | oracle → postgresql/tsql/mysql | Oracle's `DECODE(expr, search1, result1, ..., default)` tolerates result branches of different types — a string in one branch, a number in another — since Oracle resolves the whole expression's type loosely at runtime. |

## Empty-needle search guard

| Article | Direction | Description |
|---|---|---|
| [MySQL `LOCATE('', s)` (always `1`) → T-SQL guarded `CASE`](locate-empty-needle-guard.md) | mysql → tsql | MySQL's `LOCATE(needle, haystack)` special-cases an empty needle: `LOCATE('', s)` is always `1`, regardless of `s`, treating the empty string as matching at the very start. |

## Case-insensitive pattern matching

| Article | Direction | Description |
|---|---|---|
| [PostgreSQL `ILIKE` (case-insensitive `LIKE`) → `UPPER(x) LIKE UPPER(pattern)`](ilike-upper-comparison.md) | postgresql → oracle/tsql/mysql | PostgreSQL's `ILIKE` is a case-insensitive `LIKE` operator — no other target engine has a dedicated case-insensitive pattern-match operator (T-SQL and MySQL's default collations are already case-insensitive, but Oracle's is case-sensitive by default and has no `ILIKE` spelling at all). |

## Lookup functions with no target spelling

| Article | Direction | Description |
|---|---|---|
| [Functions with no target spelling: MySQL `ELT`/`FIELD`, Oracle `NVL2` → a synthesized `CASE`](no-target-spelling-case-chain.md) | mysql/oracle → all | MySQL's `ELT(n, v1, v2, ...)` (pick the `n`th value) and `FIELD(v, v1, v2, ...)` (find `v`'s 1-based position among the rest, `0` if absent) have no equivalent built-in on any other engine. |
