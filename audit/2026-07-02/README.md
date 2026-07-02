# Audit — 2026-07-02

Full audit of the `unique` repository at commit `b6632c3` (v0.7.0): functional
correctness, test quality, code quality, API/operations, and documentation.

## Documents

| File | Contents |
|------|----------|
| [01-functional-bugs.md](01-functional-bugs.md) | Concrete transpilation bugs found by exercising the tool (invalid SQL emitted, silent semantic changes, silently dropped statements) |
| [02-test-quality.md](02-test-quality.md) | Mutation-testing evidence that a large share of the tests cannot detect a broken transpiler, and how to fix them |
| [03-code-quality.md](03-code-quality.md) | Complexity hotspots, duplicated dialect knowledge across the two pipelines, plugin-architecture gaps |
| [04-api-security-ops.md](04-api-security-ops.md) | REST API blocking/DoS/SSRF concerns, Docker/CI observations, credential hygiene |
| [05-documentation-issues.md](05-documentation-issues.md) | README/docs claims that do not match the actual behavior or CLI |

## Executive summary

**State of the project.** The engineering hygiene is genuinely good: 1185 tests
pass, coverage is 89%, `ruff`/`black`/`isort`/`mypy --strict` are all clean,
CI validates output against real engines, and the code is consistently
documented. The procedural engine (stored procedures/functions/triggers) is
the strongest part of the codebase and its tests are the most rigorous.

**However, the two headline problems are real:**

1. **The test suite is largely unable to detect broken output.** Replacing the
   transpiler with an identity function (output = input, no translation at
   all) still passes **966 of 1185 tests** overall and **72% of the
   integration suite** (512/712). In `test_cross_dialect.py` only 18% of tests
   fail under this mutation; in `test_function_translation.py` only 3 of 39;
   in `test_real_world.py` only 2 of 98. The dominant assertion style
   (`assert "SELECT" in result.sql`) is true for the *untranslated input* too.
   See [02-test-quality.md](02-test-quality.md).

2. **The standalone-DML pipeline emits invalid or semantically wrong SQL for
   common constructs** — precisely the ones the weak tests cannot catch.
   Highlights (full list with reproductions in
   [01-functional-bugs.md](01-functional-bugs.md)):
   - Quoted identifiers lose their quoting entirely (`` `select` `` /
     `[select]` → bare reserved word → syntax error on the target).
   - Oracle `(+)` outer joins become an `INNER JOIN` **without an ON clause**
     (syntax error *and* silent LEFT→INNER semantic change).
   - `MERGE` → MySQL is replaced by a comment: the statement disappears from
     the executable output **with zero warnings** (`result.warnings == []`),
     contradicting both `docs/03-unsupported.md` (which claims a rewrite to
     `INSERT ... ON DUPLICATE KEY UPDATE`) and the README's "nothing is
     silently lost" principle.
   - `DATEADD` → MySQL emits `DATE_ADD(ts, 7, DAY)` (missing `INTERVAL`),
     `ROWNUM`/`FROM dual`/`ILIKE`/`GROUP_CONCAT` pass through untranslated to
     engines that reject them, boolean literals reach T-SQL as `= TRUE`.
   - Procedural: `THROW 50001, 'not found', 1` loses the error *message* on
     every target; the Oracle emitter produces constrained parameter types
     (`V_ID IN NUMBER(10)`), which Oracle rejects (PLS-00103).

**Root cause connecting both problems:** dialect knowledge is duplicated
between the sqlglot-based DML pipeline (`converter.py`/`transformer.py`) and
the procedural pipeline (`core/procedural/`), and the live-engine CI
validation only covers the procedural fixtures — so the standalone-DML path is
guarded almost exclusively by the weak keyword-presence tests.

## Recommended priorities

1. **P0 — Make silent loss impossible.** Every dropped/untranslatable
   statement (MERGE→MySQL today) must populate `result.warnings` /
   `result.unsupported`. This is the project's own stated core principle.
2. **P0 — Fix the invalid-SQL emissions** in 01, starting with identifier
   quoting and Oracle `(+)` joins (both corrupt real schemas silently).
3. **P1 — Harden the tests** with the pattern described in 02: assert the
   target idiom is present *and* the source idiom is absent; add golden
   snapshots; parse every output with sqlglot in the *target* dialect as a
   cheap validity gate; keep the identity-mutation check in CI.
4. **P1 — Extend live-engine CI validation to standalone DML/DDL**, not just
   the procedural fixtures.
5. **P2 — Deduplicate dialect knowledge** (one function/type/literal mapping
   table shared by both pipelines) and split the >2000-line modules.
6. **P2 — API hardening**: don't run CPU-bound transpilation inside `async def`
   handlers; add request size limits; treat client-supplied `db_url` as SSRF
   surface.
7. **P2 — Fix the documentation drift** (README CLI flags that don't exist,
   compatibility matrix entries that overstate behavior).

## Method

- Static gates re-run locally (pytest, coverage, ruff, black, isort, mypy).
- Identity-mutation run: `Transpiler.transpile` monkeypatched to return its
  input unchanged, then the suite re-run to measure which tests notice.
- Manual black-box probing of ~25 representative constructs across dialect
  pairs, outputs inspected for validity and semantics.
- Source review of the core modules, API, CLI, Docker, CI, and docs.
