[← Strings, concatenation and collation](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=strings-collation type="Repeat, substring and splice" direction="oracle → postgresql/mysql/tsql" kind=article order=29 -->

# Oracle extended `INSTR` (occurrence / backward search) over **literal** arguments → the computed position

**Problem.** Oracle's 4-argument `INSTR(s, sub, start, occurrence)` finds
the `occurrence`-th match at or after `start` — and, when `start` is
negative, searches **backward** from the end of the string instead.
PostgreSQL/MySQL/T-SQL's position functions (`POSITION`, `LOCATE`,
`CHARINDEX`) take no occurrence argument and cannot search backward at all.

**Solution.**

```sql
-- corpus case ora-instr-edge, oracle -> postgresql/mysql/tsql
SELECT INSTR('hello','l'), INSTR('hello','l',1,2), INSTR('hello','l',-1) FROM DUAL;
-- => postgresql
SELECT POSITION('l' IN 'hello'), 4, 4;
-- => mysql
SELECT LOCATE('l', BINARY 'hello'), 4, 4 FROM DUAL;
-- => tsql
SELECT CHARINDEX('l', 'hello' COLLATE Latin1_General_BIN2), 4, 4;
```

When every argument is a **literal**, Unique computes Oracle's own
occurrence/backward-search result at transpile time and emits the plain
number — `INSTR('hello','l',1,2)` (the 2nd `'l'` in `'hello'`) and
`INSTR('hello','l',-1)` (the last `'l'`, found searching backward) both fold
to `4`. The plain 2-argument form (no `start`/`occurrence` at all) needs no
folding — it maps directly to the target's own position function, as shown
for the first column above.

**Discussion.** The occurrence-counting and backward-search rules are
Oracle-specific string-scanning behavior with no runtime function on any
other engine to call — there is no `POSITION(needle, haystack, occurrence)`
to route the extended form through. But when the arguments are compile-time
constants, the *result* is just an integer, so Unique reproduces Oracle's
own scanning rule in Python and substitutes the computed value directly —
no runtime call is needed at all, and the loss (no portable *function* for
the extended search) never affects a literal expression's value. The same
literal-fold approach — compute the value at transpile time when the target
has no runtime equivalent to call — also folds the `LENGTH` family
(T-SQL `LEN`'s UTF-16 code-unit count and right-trim), substring edge
positions, MySQL byte-string decodes, string-operand arithmetic, and T-SQL
binary `CONVERT`s.

> **Note** faithful — live-verified `3, 4, 4` on Oracle and PostgreSQL for
> the exact corpus expression (the plain 2-arg call evaluates identically to
> the folded literals). No warning for a literal call.

A **non-literal** occurrence or negative `start` (a column, a variable, an
expression) cannot be computed ahead of time and has no runtime equivalent
to fall back to — it degrades to a documented `NULL` carrier + warning
(`UNIQUE-1087`) instead. See [§3.21](../../03-unsupported.md).

**See Also.** Corpus [`ora-instr-edge`](../../../tests/fixtures/challenge/challenge_oracle.sql) ·
[§3.21](../../03-unsupported.md) (the non-literal residual limit) ·
[`UNIQUE-1087`](../../reference/warnings.md#unique-1087) ·
`emit_functions.py::_fold_oracle_instr` (docstring) ·
[string-function positional-argument edge cases](string-function-argument-edge-cases.md)
(the sibling literal-fold family: `LEN`, negative `LEFT`, fractional rounding).

---
