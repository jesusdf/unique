# 02 — Test quality

The suspicion that "some tests are not very useful" is confirmed with hard
numbers. The suite is large (1185 passing tests, 89% line coverage) and the
static gates are clean, but **line coverage measures execution, not
verification** — and most integration assertions verify almost nothing.

## Method: identity-mutation run

`Transpiler.transpile` was monkeypatched to a no-op that returns the input
unchanged:

```python
def _identity(self, sql, source, target, options=None):
    return TranspileResult(sql=sql, warnings=[], unsupported=[])
```

Then the suite was re-run. Any test that still passes **cannot detect a
completely broken transpiler**.

## Results (commit `b6632c3`)

| Scope | Tests | Still pass with no-op | Survival rate |
|---|---:|---:|---:|
| Whole suite | 1185 | 966 | 81.5% |
| `tests/integration/` | 712 | 512 | **72%** |

Note: unit tests of the lexer/parser/emitter classes legitimately survive
(they don't go through `Transpiler.transpile`), so the integration number is
the fair headline. Per-file breakdown of the integration suite:

| File | Tests | Killed by mutation | Kill rate | Verdict |
|---|---:|---:|---:|---|
| `test_procedural.py` | 102 | 90 | 88% | **Good** |
| `test_triggers.py` | 21 | 18 | 86% | **Good** |
| `test_operator_roundtrip.py` | 31 | 17 | 55% | Mixed |
| `test_comment_preservation.py` | 15 | 3 | 20% | Weak |
| `test_cross_dialect.py` | 355 | 64 | **18%** | Weak |
| `test_functional_equivalence.py` | 31 | 3 | 10%* | *Mostly helper tests, partly excusable |
| `test_function_translation.py` | 39 | 3 | **8%** | Weak |
| `test_real_world.py` | 98 | 2 | **2%** | Weak (by design "lenient", but too lenient) |

The two weakest files are, unfortunately, the ones guarding the standalone
DML/DDL pipeline — which is exactly where the real bugs live (see
[01-functional-bugs.md](01-functional-bugs.md)).

## Why the tests survive

**Pattern 1 — keyword presence that also holds for the input.**

```python
# test_cross_dialect.py
result = transpiler.transpile("SELECT TOP 10 * FROM users", "tsql", target)
assert "users" in result.sql          # true for the untouched input too
assert "None" not in result.sql or "/* UNIQUE:" in result.sql
```

The `TOP → LIMIT/FETCH` conversion — the whole point of the test — is never
asserted. 355 parametrized tests in this file give an *illusion* of a dense
4×4 matrix, but ~290 of them would pass with `return sql`.

**Pattern 2 — structural counts preserved by identity.**

```python
# test_function_translation.py
out = _expr(_t("SELECT SUBSTRING(a, 1, 3) FROM t", target))
assert "1" in out and "3" in out and "a" in out
assert out.count(",") == 2            # also true when nothing was translated
```

These tests pin "no argument is dropped" — a real regression they once fixed —
but never pin that `SUBSTRING` became `SUBSTR` on Oracle. 36 of 39 survive.

**Pattern 3 — invariants that only catch catastrophic loss.**

`test_real_world.py` checks "doesn't crash, non-empty, CREATE TABLE count
preserved, Jaccard similarity". An identity transpiler trivially maximizes
all of these. 96 of 98 survive.

**Formally weak tests** (no assertions / only `is not None`) are rare — 6 in
757 test functions — so the problem is not laziness, it's assertion *choice*.

## What the suite does well

- The **procedural** tests assert exact target idioms (`:=`, `SIGNAL
  SQLSTATE`, `DELIMITER $$`, PG trigger split) — 88% kill rate. Use them as
  the template.
- The **live CI jobs** (`test_live_syntax.py`, metadata, FE harness) execute
  output against real MySQL/PostgreSQL/Oracle/SQL Server. This is excellent —
  but it only covers the checked-in fixtures, which is why S1-4…S1-11 in doc
  01 slipped through, and it doesn't run locally.
- Property tests exist (`tests/property/`) but only check "parser returns a
  node" — no round-trip or validity properties.

## Recommendations (in order of leverage)

1. **Adopt the "target idiom present AND source idiom absent" pattern.**
   For `TOP → postgresql`: `assert "LIMIT 10" in out and "TOP" not in out`.
   This alone would convert most of `test_cross_dialect.py` into real tests
   with minimal diff.
2. **Parse every transpiled output with sqlglot in the *target* dialect**
   (`parse(out, read=target, error_level=RAISE)`) as a cheap validity gate in
   a shared helper/fixture. It costs milliseconds, needs no database, and
   would have caught S1-1, S1-2, S1-4, S1-8 immediately. (It won't catch
   engine-specific rules sqlglot tolerates — the live jobs remain the final
   gate.)
3. **Golden/snapshot tests** for a curated corpus: exact expected output per
   (input, source, target). Review diffs on change instead of hand-writing
   assertions. `pytest --snapshot-update` workflows (e.g. `syrupy`) fit well.
4. **Keep the identity mutation in CI.** A ~20-line pytest plugin (as used in
   this audit) run as a separate job with an expected kill-rate threshold
   turns "tests must be useful" into a gate. For deeper coverage consider
   `mutmut`/`cosmic-ray` on `converter.py`/`transformer.py`, but the identity
   mutant is the highest value-per-minute.
5. **Extend the live-syntax CI job to standalone DML/DDL**, feeding it the
   same probe corpus as the unit layer (create a table, run the transpiled
   SELECT/UPDATE against each engine).
6. **Add semantic-divergence scenarios to the FE harness** for the cases in
   doc 01: Oracle `NO_DATA_FOUND` vs T-SQL null assignment (S2-3), `(+)`
   outer-join row counts (S1-2), `STRING_AGG` separator (S2-1).
7. **Trim redundant parametrization.** 355 tests in `test_cross_dialect.py`
   that assert `"SELECT" in out` add CI time and false confidence. Fewer,
   sharper cases beat a broad matrix of tautologies.
