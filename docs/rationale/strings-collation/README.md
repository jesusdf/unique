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

## Repeat, substring and splice

| Article | Direction | Description |
|---|---|---|
| [Negative/zero REPEAT/REPLICATE clamps](repeat-replicate-clamps.md) | cross-engine | PostgreSQL `repeat(s, n)` and MySQL `REPEAT(s, n)` with `n <= 0` return an empty string `''`. |
| [SUBSTRING negative/zero start semantics per engine](substring-negative-start.md) | cross-engine | T-SQL and PostgreSQL `SUBSTRING(s, start, len)` treat a `start < 1` as counting *backwards from the length*: out-of-range leading positions still consume `len`, they just don't emit characters for them. |
| [Positional string-splice: `OVERLAY`/`STUFF`/`INSERT` (PostgreSQL/T-SQL/MySQL) → all targets](overlay-stuff-insert-splice.md) | tsql/postgresql/mysql → all | Three engines each have a native "replace `len` characters of `string` at 1-based position `start` with `new`" function: PostgreSQL's `OVERLAY(string PLACING new FROM start [FOR len])`, T-SQL's `STUFF(string, start, len, new)`, MySQL's `INSERT(string, start, len, new)`. |

## Trimming

| Article | Direction | Description |
|---|---|---|
| [Character-set `TRIM(chars FROM string)` → Oracle](trim-chars-from-string-to-oracle.md) | cross-engine | `TRIM([BOTH\|LEADING\|TRAILING] chars FROM string)` strips every occurrence of any character in `chars` from the string (both ends by default). |

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
