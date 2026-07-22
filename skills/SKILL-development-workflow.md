---
name: unique-development-workflow
description: >
  Development workflow skill for the Unique SQL Transpiler. Use this skill
  when implementing new features, adding dialect support, writing tests,
  debugging transpilation issues, updating the backlog (docs/TODO.md), or
  committing and pushing work. Covers the mandatory pre-change analysis,
  TDD methodology, how to add new AST nodes, how to extend a dialect, testing
  patterns, the pre-commit verification gate, the TODO + commit/push
  discipline, and cutting a release (single-sourced version + tag).
---

# Unique — Development Workflow

## Confidential fixtures (mandatory)

Everything under **`fixtures-private/`** (e.g. `test.sql`, `bigtest.sql`) is a real
client's confidential SQL. The repository is **public**. You may extrapolate the
*functionality* (the patterns, the constructs, the bugs they expose) but **never
the file content**: never copy a real object name — table, procedure (including
`sp_*` helpers), column, schema, view, or a revision number — into anything that
gets committed (tests, source-code comments, commit messages, docs).

When writing a test or example from something seen in a private fixture,
**anonymize**: use generic names (`t`, `c`, `my_proc`, `sp_customproc`,
`schema_version`, revision `1`) that reproduce the pattern without the real
identifier. Keep the real names in the working conversation only. If a real name
has already been committed, fix the files **and rewrite git history**
(`git filter-repo --replace-text --replace-message`, then force-push) to purge it.

The same contract covers **license-restricted local corpora** under the
gitignored `fixtures-corpus/`: some tuning material there may not be
redistributed, and its **provenance must never be named in committed
artifacts** (tests, comments, commit messages, docs, or sweep numbers
attributed to a named corpus). Findings from such material are committed only
as synthetic anonymized reproductions, exactly like the client-SQL rule above.

## Analyze before changing (mandatory first step)

Before writing or modifying any code, **read the code you are about to touch
and the surrounding context first**, and flag any problem you find in it —
even when it is not strictly what you were asked to change. Report, at minimum:

- **Architecture-guide violations** — code that contradicts `docs/02-architecture.md`
  (e.g. the procedural engine threading `if self._dialect == …` branches instead
  of following the per-engine plugin/subclass architecture the project promises).
- **Methodology breaches** — changes arriving without a failing test first
  (TDD), fixtures hand-edited instead of regenerated, work landing without the
  pre-commit gate, or the backlog/commit-push discipline being skipped.
- **Policy breaches** — non-English code/comments/docs, missing SPDX/MIT
  headers, secrets (the PAT) about to be printed or committed, output that
  isn't validated against the live engines, etc.
- **Anti-patterns and code smells** — long functions (>~30 lines), duplicated
  logic, deep dialect conditionals, leaky abstractions, dead code, unclear
  names, missing docstrings on public symbols.

Surface these explicitly (in the response and, when actionable, as a
`docs/TODO.md` item) before proceeding, so the human can decide. Do not
silently work around a problem you noticed.

**Prioritize the project's goals over development convenience.** The stated
priorities are, in order: (1) the most *faithful* possible conversion, (2)
maintainable code following Clean Code, (3) the plugin/per-engine architecture.
When a quick or convenient fix conflicts with these, do **not** take the lazy or
lax path: pick the solution that serves the project's goals — a real per-engine
method over another `if/elif`, a correct transformation over a passthrough that
"happens to compile", a regenerated fixture over a hand-tweak. If the faithful
solution is large, say so and propose it; don't quietly downgrade the goal to
make the change easier.

## Architecture guardrails (audit 2026-07-08 doc 04 — binding)

The 2026-07-08 audit traced ~40 real-script defects to five root causes; these
rules keep them from growing back. When one of them blocks the quick version
of your fix, that is the rule working — do the structural version or escalate.

1. **Moratorium on regex shape-patches in the script layer.** Do not add new
   regex recognizers/extractors/special cases for SQL *constructs* to
   `transpiler.py` or to `batch_splitter._classify`'s cascade. New or
   mis-handled constructs (guards, IF forms, EXEC forms, …) are handled in the
   **AST paths**: route the batch to the procedural engine or the IR
   converter and decide there, on parsed structure. The regex cascade only
   ever grew one hole per fix (guard + `BEGIN`, guard + leading comment,
   `OBJECT_ID` with a type argument… each individually "fixed" while its
   neighbors stayed broken).
2. **Never transform SQL as text.** Function/type/literal/operator mappings go
   in the IR converter + `core/mappings.py`, applied on the AST — never as an
   `re.sub` over SQL text. Text-level rewriting is how `MAX(NVL(n,0)) + 1`
   lost tokens on one target and turned `+` into `||` on another (silent
   corruption, the worst defect class we ship). Embedded DML inside routine
   bodies must go through the same IR pipeline as standalone DML (the
   table-variable DDL path shows the pattern); raw `sqlglot.transpile` is a
   *warned* fallback, never the primary path.
3. **Comments are trivia.** No classification, matching, guard extraction, or
   terminator decision may ever operate on text that can still contain
   comments; comments attach to the following statement and are re-emitted.
   If your code needs `strip the comment first`, the stripping belongs in ONE
   shared place, not in your call site.
4. **Never ship invalid output silently.** If an emitted DML/DDL unit does not
   parse in the *target* dialect (sqlglot check), or a procedural unit fails
   the structural checks (balanced blocks, no source-only leftovers), the unit
   degrades to the documented carrier + warning/unsupported entry — the same
   contract as any lossy conversion. A parser that loses sync fails the
   **whole unit** into a carrier; it never emits fragments.
5. **Warnings are part of correctness.** A warning must (a) describe what
   actually happened ("SET option commented out" on a DROP-guard batch is a
   bug), (b) fire exactly when it happened (a warning on a *successful*
   conversion is a bug), and (c) be aggregated (one entry with a count, not
   338 repeats). Treat a false or mislabeled warning like wrong SQL output.
6. **Definition of done for transpilation work** is not "the fixture is
   green". It is: fixture green **and** its combinatorial neighbors probed
   (see the next section) **and** the round-trip holds **and** the validity
   sweep (`scripts/validity_sweep.py`, once available — otherwise the live
   corpus tests) does not regress for the affected direction **and** docs
   updated. Direction maturity is stated as a measured validity %, never as
   "complete".

## The validity-wave cadence (proven 2026-07-15 → 2026-07-17, waves 4-239)

Corpus-driven direction work follows a measured loop; each wave is one
mechanism (never one spelling — see the circuit breakers). **Both shipped
corpora (pg-source, mysql-source) are CLOSED at the architectural floor: the
declared floor of 133 was driven to 16 by the zero-reduction campaign
(2026-07-17, `docs/DONE.md` §40; both Oracle directions at 100.0% validity) —
do not resume waves on them; this cadence applies to NEW corpora or fidelity
targets. Two measurement notes from §40: (a) the pg→oracle sweep hangs at
runtime on bare `SELECT <dml-fn>()` pg_regress driver calls (skip them — not
syntax defects); (b) some failures only reproduce in WHOLE-corpus context
(a preceding statement changes a ContextVar / RETURNING passthrough) — extract
the real output with `Transpiler().transpile(open(corpus).read(), …)` rather
than trusting an isolated probe:**

1. **Classify** the sweep's own failure dumps (`SWEEP_DUMP_FILE` hook): group
   by the first NON-comment code line's leading tokens; sample real blocks
   before naming the mechanism.
2. **Red tests** for the class in the direction's wave test module (e.g.
   `tests/integration/test_pg_source_wave1.py`), meeting the assertion bar
   below (target idiom present, source idiom absent, identity-proof).
3. **Fix the mechanism** at the right layer (lexer/parser/transformer/emit —
   never a text patch); probe combinatorial neighbors.
4. Full **pre-commit gate**, commit, push.
5. **Relaunch the sweep cycle** and record the numbers in `docs/TODO.md`
   **with the measured commit hash**. Record honest negatives too: a class
   fix that un-carriers units often exposes the NEXT blocker in a chain
   (plpgsql routines are blocker CHAINS — expect small deltas per wave).

When adding a NEW test module in this loop, **add it to the `--tests`
selections in `.github/workflows/mutation.yml`** — the nightly mutation
floors sank for seven nights (2026-07-09..15) because the wave module that
kills the new code's mutants was not in the selections, so every new-path
mutant survived by construction.

**Whole-unit degrade contract:** a statement/routine with no mechanical
equivalent degrades WHOLE — carrier + warning + `unsupported` entry, never a
fragment. In the DML path use the statement-level gates in
`Transformer.transform` (`_gate_pg_internals`, `_gate_array_constructs`); in
the procedural path return a `RawSQL` whose reason contains **"preserved as a
comment"** — the procedural emitter renders exactly those as comment carriers
(plus the parse-fallback reason); any other RawSQL reason ships verbatim.

## Detect the wrong path: circuit breakers (mandatory)

History shows the expensive failure mode here is not writing a bad fix — it is
writing a *locally correct* fix that treats one instance of a class, then
repeating it (guards were "fixed" at least four times, each time for exactly
one spelling, while migration dumps kept failing). Before and during any fix,
run these checks; when one fires, **stop patching and change altitude**.

1. **Rule of three.** Before patching a function/regex/fallback, check
   `git log --oneline -- <file>` and `docs/DONE.md` for earlier fixes to the
   same mechanism. If you are about to write the **third** fix to the same
   spot for the same *kind* of input, the mechanism is wrong, not the input.
   Do the class fix, or stop and propose it. Never land patch #3 silently.
2. **Neighbor test.** A shape bug is never alone. Before declaring a fix done,
   enumerate its combinatorial neighbors — ± leading comment, ± `BEGIN…END`
   wrapper, ± an extra argument, sibling statement kinds (INSERT/UPDATE/
   DELETE/CREATE/DROP), and **all targets** — and probe them. If the neighbors
   fail and each would need its own patch, you are patching a class one
   instance at a time: circuit-break to the structural fix.
3. **Green-but-unmoved metric.** If tests pass but the corpus/live/sweep
   number that motivated the work doesn't move, the fix missed the mechanism.
   Re-derive where the failing inputs actually flow (add a temporary trace if
   needed) instead of trying the next variation.
4. **The fallback smell.** If your fix routes yet another case into a path
   that comments code out or passes it through — or adds an `if` to such a
   fallback — treat it as a red flag: fallbacks only ever grow. The right fix
   almost always *removes* traffic from the fallback.
5. **The lying-warning smell.** If you cannot write a warning message that
   truthfully describes what your code does to the user's SQL, the code is
   doing the wrong thing.
6. **Two-strikes rule.** After two failed attempts at the same fix, stop
   trying variations. Read the full code path end-to-end (splitter →
   classifier → parser/converter → transformer → emitter → join) for one
   failing input and write down the mechanism before touching code again.
   Blind iteration on a misunderstood mechanism is how sessions burn.
7. **Test-shaping.** Weakening an assertion, widening a regex in a test, or
   adding an xfail to make your change green is never a fix. If the expected
   output genuinely changed, the assertion change must be *stronger*, and the
   docs must change with it.

**Escalation protocol when a breaker fires:** (1) stop; (2) write the root
cause — the mechanism, not the symptom — as a class-level `docs/TODO.md` item,
mapping it to its root cause in `audit/2026-07-08/04-architecture-analysis.md`
if it fits one; (3) if the class fix is in scope, do that instead of the
patch; (4) otherwise surface it explicitly in your response with a proposal
and land nothing that hides the problem. Spending a session on the class fix
beats spending five sessions on five instances — that trade has already been
measured in this repo, in the wrong direction.

## TDD Cycle

Every feature follows Red → Green → Refactor:

1. **Red** — Write a test that describes the desired behavior. Run it, confirm it fails.
2. **Green** — Write the minimum code to make the test pass.
3. **Refactor** — Clean up while keeping tests green.

### Test Structure

```
tests/
├── unit/
│   ├── core/
│   │   ├── test_ast_nodes.py         # IR node construction & equality
│   │   ├── test_transpiler.py        # Orchestration logic
│   │   └── test_registry.py          # Plugin discovery
│   ├── dialects/
│   │   ├── test_tsql_parser.py       # T-SQL → IR
│   │   ├── test_tsql_emitter.py      # IR → T-SQL
│   │   ├── test_oracle_parser.py
│   │   ├── test_oracle_emitter.py
│   │   ├── test_postgresql_parser.py
│   │   ├── test_postgresql_emitter.py
│   │   ├── test_mysql_parser.py
│   │   └── test_mysql_emitter.py
├── integration/
│   ├── test_tsql_to_postgresql.py    # Full transpilation
│   ├── test_oracle_to_mysql.py
│   └── ...                           # All 12 direction combos
└── fixtures/
    ├── select_basic.sql
    ├── join_complex.sql
    ├── stored_procedure.sql
    └── ...
```

### Test Naming Convention

```python
def test_<what>_<condition>_<expected>():
    """Example: test_select_with_top_emits_limit_in_postgresql"""
```

### Fixture-Driven Integration Tests

```python
@pytest.mark.parametrize("fixture", load_fixtures("select"))
def test_transpile_select(fixture):
    result = transpile(fixture.source_sql, source="tsql", target="postgresql")
    assert result == fixture.expected_sql
```

### Round-trip validation (mandatory)

**Every behavior-changing modification must be validated with a round-trip
(A -> B -> A'), not only a one-way A -> B check.** A one-way assertion silently
passes on a *no-op* or a *drop*: the change looks right going out, but the
inverse pass reveals what was lost or mis-placed. This is exactly how the
"comment before a routine" work surfaced its bug -- moving a T-SQL header comment
*into* an Oracle procedure looked fine one-way, but Oracle -> T-SQL then dropped
it entirely (the parser discarded declaration-section comments), so the round-trip
lost it. Whenever you touch how a construct is emitted or parsed, transpile it
back and assert A' preserves A (place, value, and presence) before you commit.

For anything whose *spelling* differs between engines -- operators (string `+`
vs `||` vs `CONCAT`, bitwise, compound assignment) and functions modeled
differently per dialect -- prefer a **round-trip** test over a one-way one. A
one-way assertion can silently pass on a *no-op* conversion: T-SQL `+` left as
`+` on Oracle "looks plausible", and a one-way test that only checks the target
won't catch it. Transpiling A->B then B->A makes the regression obvious because
A' then differs from A. This technique surfaced the string-concat, bitwise,
compound-assignment and dropped-function-argument bugs. See
`tests/integration/test_operator_roundtrip.py` and `test_function_translation.py`;
cover all 12 engine pairs where the spelling can differ.

### Test assertion quality (mandatory — see audit/2026-07-02)

The 2026-07-02 audit proved that **72% of the integration suite passed with the
transpiler replaced by an identity function** (output = input, zero
translation). The dominant cause: keyword-presence assertions that are also
true for the untranslated input. These rules are binding for every new or
modified test:

1. **The identity test.** Before writing an assertion, ask: *would this pass if
   `transpile` returned its input unchanged?* If yes, the assertion verifies
   nothing — rewrite it. Banned as the *only* assertions of a test:
   `assert "SELECT" in out`, `assert "users" in out`, token/comma counts that
   the input also satisfies, "doesn't crash / non-empty" checks.
2. **Assert the target idiom present AND the source idiom absent.** The pattern
   that makes a conversion test real:
   ```python
   out = transpiler.transpile("SELECT TOP 10 * FROM users", "tsql", "postgresql").sql
   assert "LIMIT 10" in out          # target idiom appeared
   assert "TOP" not in out.upper()   # source idiom is gone
   ```
3. **Parse every output in the target dialect** as a cheap validity gate —
   milliseconds, no database, and it catches stripped identifier quoting,
   JOINs without ON, missing INTERVAL, etc.:
   ```python
   import sqlglot
   sqlglot.parse(out, read=_SQLGLOT_DIALECT[target],
                 error_level=sqlglot.ErrorLevel.RAISE)
   ```
   Prefer putting this in a shared helper/fixture so it applies to whole test
   modules. (sqlglot is lenient about some engine rules — the live CI jobs
   remain the final gate — but it kills the worst class of bugs for free.)
4. **Run the identity-mutation check after adding tests** for translation
   behavior. Monkeypatch `Transpiler.transpile` to return
   `TranspileResult(sql=sql)` and confirm your new tests FAIL under it:
   ```python
   # conftest plugin used by the audit — ~10 lines, keep it handy
   def _identity(self, sql, source, target, options=None):
       return TranspileResult(sql=sql, warnings=[], unsupported=[])
   monkeypatch.setattr(Transpiler, "transpile", _identity)
   ```
   A translation test that survives the identity mutant is not done.
5. **Prefer exact/golden assertions** for curated inputs over fuzzy ones. When
   the full output is stable, compare it whole; diffs on change are easier to
   review than clever substring logic.
6. **Coverage % is not the goal.** 89% line coverage coexisted with the 72%
   mutation-survival rate. Do not add tests to move the coverage number; add
   tests that would fail if the behavior broke.

### No-silent-loss invariant (mandatory)

The project's core promise — "nothing is silently lost" — was violated in
v0.7.0 (MERGE→MySQL vanished into a comment with `warnings == []`; the
`THROW` message and `(+)` join semantics were dropped with no signal). Rules:

- Any construct that cannot be mapped 1:1 **must** add an entry to
  `result.warnings` or `result.unsupported` — the carrier comment
  (`/* UNIQUE: ... */`) alone is NOT enough, because API/CLI consumers read
  the result object, not the SQL text.
- **Never emit a comment as the sole replacement for an executable statement**
  without a corresponding `unsupported` entry.
- **Never downgrade semantics silently** (outer→inner join, exception→null,
  message dropped). If the faithful rewrite is hard, keep the original in a
  carrier, register it as unsupported, and file a `docs/TODO.md` item.
- Cheap enforcement to keep in tests: every `UNIQUE:` carrier in the output
  must have a matching entry in `warnings`/`unsupported`.

### Dual-pipeline symmetry rule

Dialect knowledge lives in two stacks (sqlglot-based DML in
`converter.py`/`transformer.py`; the procedural engine in `core/procedural/`),
and mappings have drifted asymmetric (`STRING_AGG→GROUP_CONCAT` existed while
`GROUP_CONCAT→STRING_AGG` did not; `ISNULL` mapped but boolean literals not).
When adding or fixing any function/type/literal/pseudo-table mapping:

1. Add it in **both directions** (A→B and B→A) unless one direction is
   documented as impossible.
2. Check **both pipelines** (standalone DML and procedural bodies) — a fix in
   one usually needs the other.
3. Add a **round-trip test** and a probe for each direction.
4. Long term, prefer moving the mapping into a single shared table consumed by
   both pipelines (see audit doc 03) rather than adding a fourth copy.

## Adding a New AST Node

1. Define the node in `src/unique/core/ast_nodes.py`:
   ```python
   @dataclass(frozen=True)
   class MergeStatement(ASTNode):
       target: TableRef
       source: TableRef | Subquery
       on_condition: Expression
       when_matched: list[Action]
       when_not_matched: list[Action]
   ```
2. Write unit tests for construction and equality.
3. Add parsing support in each dialect's parser.
4. Add emission support in each dialect's emitter.
5. Write integration tests for transpilation across dialects.

## Adding a New Dialect

1. Create `src/unique/dialects/<name>/`:
   - `__init__.py` with `Dialect` subclass
   - `parser.py` — Implements `parse(sql) -> list[ASTNode]`
   - `emitter.py` — Implements `emit(nodes) -> str`
2. Register in `src/unique/core/registry.py` (auto-discovery via entry points).
3. Mirror test structure in `tests/unit/dialects/`.
4. Add integration test files for all transpilation directions.

## Work in parallel where independent (save time)

Don't serialize steps that have no dependency between them — it wastes
wall-clock time. Be **reasonable** (don't parallelize work that races on the
same file, DB rows, or a fixed port), but by default:

- **Batch independent tool calls into one message** — read several files at
  once, or run `black` + `isort` + `ruff` + `mypy` together, rather than
  one-at-a-time round-trips.
- **Run long jobs in the background** (`run_in_background`) — the full suite, a
  live-DB sweep, a CI poll — and keep working while they run; you are
  re-invoked when they finish. Capture the real exit
  (`> file; echo "EXIT=$?" >> file`), never `… | tail` (that reports the pipe's
  exit, not pytest's).
- **Use the core-parallel test runner** — `scripts/test-parallel.sh` (nproc
  workers) over a serial `pytest`; it is the CI command too.
- **Live-verify a whole batch in one pass** — a single script that transpiles
  every case and runs each output on the four Docker engines, not a round-trip
  per case.
- **Fan out only when it pays** — a genuinely large, independent sweep is worth
  parallelizing; two quick reads are not worth the ceremony.

## Running Tests

```bash
# All tests
pytest

# Specific dialect
pytest tests/unit/dialects/test_tsql_parser.py

# Integration only
pytest tests/integration/

# With coverage
pytest --cov=unique --cov-report=html

# Single test
pytest -k "test_select_with_top"

# Fast full run across CPU cores (needs GNU parallel; ~62s -> ~23s on 8 cores)
scripts/test-parallel.sh
# ...with combined coverage (COVERAGE_CORE=sysmon keeps it near-free)
COV=1 scripts/test-parallel.sh
```

A serial `pytest` run is dominated by one heavy file
(`tests/integration/test_real_world.py`, ~48 s), so file-level parallelism does
not help. `scripts/test-parallel.sh` collects every node ID, round-robins them
into `nproc` groups and runs one pytest process per group via GNU parallel — the
same command CI uses (`COV=1 PYTEST_PYTHON=python`). It runs so often per session
that the ~3x speedup is worth it; it falls back to a single `pytest` run when
GNU parallel is absent.

## Code Quality

```bash
# Formatting
black src/ tests/
isort src/ tests/

# Linting
ruff check src/ tests/

# Type checking
mypy src/
```

### Performance: never build a string by ``+=`` in a loop (mandatory)

The transpiler runs over whole scripts (a real dump is 200k+ lines / 25 MB of
output), so a quadratic hot path turns seconds into minutes. **Accumulating a
string with ``out += piece`` inside a loop that iterates over
input-proportional data (batches, statements, rows, output parts) is O(n²)** —
each concatenation copies the entire accumulator. Build a **list** and
``"".join()`` (or ``sep.join()``) **once** at the end. Same rule for any
per-item work that rescans a growing collection (e.g. checking each item against
all previously accumulated items → dedupe with a ``set`` instead of an O(n)
scan). A 13 MB migration script went from **421 s to ~30 s** by fixing exactly
these two shapes (``_join_parts`` and the carrier↔warning reconciliation); the
same pattern must not be reintroduced. Per-statement ``result += clause`` for a
*fixed* number of clauses (WHERE/FROM/…) is fine — the danger is only the
input-proportional loop.

## Backlog discipline (docs/TODO.md)

`docs/TODO.md` is the single source of truth for the backlog. Keep it current
and treat it as part of the deliverable, not an afterthought.

- **One TODO file only.** The authoritative backlog is `docs/TODO.md`. Do **not**
  create a second TODO (e.g. a scratch `TODO.md` at the repo root); search for
  an existing one before adding tasks and consolidate into `docs/TODO.md`.
- **Record new work as you find it.** Whenever you discover a bug, gap, or
  follow-up while doing something else, add an item immediately (with a short
  rationale and a priority like P1/P2/P3) rather than relying on memory. Bugs
  found via the live-validation layer are especially worth capturing.
- **Mark items done, don't delete the context.** When you finish an item, flip
  `- [ ]` to `- [x]` and append a one-line note on how it was solved (and the
  test that covers it). This keeps the history useful for the next session.
- **Don't duplicate entries.** If an item already exists, update it in place
  instead of adding a near-identical one. Re-check after edits that a heading
  or sibling bullet wasn't accidentally consumed by a replace.
- **Commit & push on every TODO change.** Any time you touch `docs/TODO.md`,
  commit it (together with the related code/test changes when there are any)
  and push to `main`. The backlog on `main` should always reflect reality.

## Documentation discipline (scope/support changes — mandatory)

**Any change to what the transpiler supports or how it behaves must update the
documentation in the same change** — docs are part of the deliverable, not an
afterthought. A change is scope/support-affecting when it: makes a construct
transpile that previously degraded to a carrier (or vice versa), adds/removes a
dialect, adds a type/function mapping or a per-dialect idiom, closes or discovers
an intrinsic limitation, or otherwise changes the compatibility surface.

When that happens, update the relevant docs in the same commit:

- **`docs/03-unsupported.md`** — move an item out of "unsupported/partial" when it
  now works, or add one when a new limitation is found. Keep the reason accurate.
- **`docs/01-compatibility.md`** — the feature matrix and any per-dialect notes.
- **`docs/STATUS.md`** — the project-state snapshot: it names a version and must
  reflect the **current** release, not a stale one. If it has drifted, rewrite it.
- **`docs/DONE.md`** — archive the completed work with its why/how and the test
  that covers it (mirrors the backlog "mark done, keep context" rule).

The "point-in-time" state docs (`STATUS.md`, the compatibility matrix) age
silently; treat a version bump as a trigger to confirm they still describe
reality. When in doubt, prefer rewriting a stale section over patching around it.

## Pre-commit verification gate

Before **every** commit, run the full gate and only commit if it is green:

```bash
black src/ tests/        # format
isort src/ tests/        # import order
ruff check src/ tests/   # lint  -> must print "All checks passed!"
mypy src/unique/ --ignore-missing-imports   # types -> "no issues found"
pytest tests/ -q         # full suite -> "<n> passed"
```

**Watch the ruff result, not just the summary.** `ruff check` can print
`No fixes available (... hidden fix ...)` while still **failing** -- it counts
the issue as an error even when it can't auto-fix it (e.g. `SIM102` nested-`if`,
`SIM103` return-the-condition). CI runs `black --check` / `isort --check-only` /
`ruff check`, so a "1 error" you skim past locally turns into a red CI. Confirm
ruff prints exactly `All checks passed!`.

**Verify large edits survived the formatter.** `str_replace` and the black/isort
auto-fixers have repeatedly **collapsed or deleted adjacent bodies** when an edit
hit a big file (function bodies reduced to signature/docstring, test classes or
doc tables silently dropped, leaving empty gaps). After any non-trivial edit to
`converter.py`, `transpiler.py`, the procedural `base.py` files, a test module,
or a docs/skills table, re-verify before trusting it:

```bash
python -c "import ast; ast.parse(open('PATH').read())"   # still parses?
grep -c "def <helper_you_just_added>" PATH               # exists exactly once?
git diff --stat PATH                                     # sane +/- ratio, not +2/-24?
```

and spot-check behaviour (a quick `Transpiler().transpile(...)`). For appending
test classes use a bash heredoc (`cat >> file <<'PYEOF'`); for rewriting a whole
function or a markdown table, use a small Python script that asserts the old text
was found *exactly once* before replacing -- a silent miss corrupts the file.

If a transformer/emitter/parser change affects the procedural fixtures,
**regenerate them** before committing and review the diff (they are generated,
never hand-edited):

```bash
# Example: regenerate the MySQL fixture from the T-SQL source
python -m unique.cli.main transpile \
  tests/fixtures/procedures/procedures_sqlserver.sql --from tsql --to mysql
# (prepend the standard "DO NOT EDIT BY HAND" header; see SOURCES.md)
```

## Commit & push workflow

- **Commit frequently**, one logical change per commit, with a descriptive
  message (what changed and *why*, plus the test added). Conventional-commit
  prefixes are used (`feat`, `fix`, `docs`, `build`, `test`, ...).
- **Push to `main`** after the gate passes (`git push origin main`). The remote
  and its credentials are configured in the local environment, outside the repo.
  Never print, commit, or document a token or its location in a versioned file.
- After pushing, it's good practice to **check CI** (see the CI section below)
  and fix any failure before moving on.

## Releasing (version bump + tag)

The version is **single-sourced** from `__version__` in `src/unique/__init__.py`;
`pyproject.toml` reads it dynamically (`[tool.setuptools.dynamic] version =
{attr = "unique.__version__"}`), the API's `_display_version()` derives its label
from it, and `tests/unit/api/test_api.py` asserts against that derivation — so a
release edits the version in **exactly one place**. Do **not** hand-edit the
version in more than one file (and never with a one-liner that opens a file for
write before reading it — that truncates it).

Use the release script, which does the whole flow (bump → gate → commit → annotated
tag → push):

```bash
scripts/release.py minor            # 0.19.3 -> 0.20.0  (also: major | patch | X.Y.Z)
scripts/release.py minor --dry-run  # print the plan, change nothing
scripts/release.py patch --no-push  # commit + tag locally, don't push
```

It refuses to run off `main`, on a dirty tree, or if the tag already exists; runs
`black/isort/ruff/mypy/pytest` and **reverts the bump if the gate fails**; and
tags annotated as `vX.Y.Z` / `unique X.Y.Z` (the repo convention). After a
milestone release, refresh the `Current state: vX.Y.Z` line in `docs/STATUS.md`
(narrative, not auto-updated).

## Common Patterns

### Transpiler Orchestration

```python
def transpile(sql: str, source: str, target: str) -> str:
    source_dialect = registry.get(source)
    target_dialect = registry.get(target)
    
    ast_nodes = source_dialect.parse(sql)
    transformed = transform(ast_nodes, source, target)
    return target_dialect.emit(transformed)
```

### Transform Layer

Between parsing and emitting, a transform step normalizes dialect-specific
constructs into portable equivalents:

- `TOP n` -> `LIMIT n`
- `ISNULL()` -> `COALESCE()`
- `GETDATE()` -> `NOW()` / `CURRENT_TIMESTAMP`
- `NVL()` -> `COALESCE()`
- String concatenation: `+` <-> `||` <-> `CONCAT()`

**Where the sqlglot workarounds live.** sqlglot does the per-statement parsing
but has gaps we patch in `core/converter/` for **standalone DML** (the
procedural engine handles routine bodies separately — until doc-04 P4 lands,
a fix often needs doing in *both* places, or the DML form lags behind; per the
architecture guardrails, the procedural copy must be an AST transform, never a
text rewrite):

- T-SQL string `+` -> concat: `_rewrite_tsql_string_concat` rewrites an `Add`
  with a string-ish operand to `DPipe`; `col + col` without type info stays `+`.
- Bitwise `& | ^ << >>`: mapped explicitly in `_convert_binary`/`_emit_binary`;
  an unmapped operator is preserved verbatim, never coerced to `=`.
- Compound assignment (`SET a += 1`): expanded to `a = a + 1` in
  `transpiler._expand_tsql_compound_assignment` before sqlglot sees it.
- Function arguments: `_convert_function` collects args in `arg_types` order so
  named-slot args (Substring/Replace/Round/Stuff/DateAdd/Power/...) aren't lost.

When you fix a sqlglot gap, check whether the same construct also flows through
the procedural engine, and add a round-trip test.

### Error Handling

```python
class UnsupportedFeatureError(TranspileError):
    """Raised when a construct cannot be translated to the target dialect."""
    
    def __init__(self, feature: str, source: str, target: str):
        super().__init__(
            f"Cannot transpile '{feature}' from {source} to {target}"
        )
```

Unsupported features are logged with context (line number, construct) and
optionally left as comments in the output SQL.

## CI Pipeline and Diagnosing Failures

CI is defined in `.github/workflows/ci.yaml` with these jobs: **Lint &
Format** (black + ruff), **Type Check** (mypy), **Test** (Python 3.13), **Live
Metadata Tests** (Postgres + MySQL service containers), **Live Syntax
Validation** (Postgres + MySQL + SQL Server + Oracle, validates transpiler output
against the real engines' grammar), and **Docker Build & Push** (only on a `v*`
tag, to **Docker Hub** — not GHCR). Two more workflows run alongside:
`.github/workflows/codeql.yml` (security scan) and `.github/workflows/mutation.yml`
(nightly mutation testing).

**Actions storage is self-maintained (2026-07-19).** CodeQL writes a per-commit
`codeql-overlay-base-database-*` cache that never self-expires, so it piled up to
~7.5 GB (near the 10 GB cap); `codeql.yml` has a post-analysis step that prunes
all but the two newest overlay caches (needs `permissions: actions: write`).
Workflow runs also accumulate unbounded (they had reached ~1800), so
`.github/workflows/cleanup.yml` runs daily and keeps only the 50 most recent runs
(never touching an in-progress one). Note: the Actions **billing** storage
("Storage for Actions and Packages", 0.5 GB free) counts artifacts + GHCR
packages — **not** the cache — so pruning the cache does not change that number;
inspect it at `GET /repos/jesusdf/unique/actions/cache/usage`,
`.../actions/artifacts`, and Settings → Billing → Usage.

### Checking CI status from the API

`api.github.com` is reachable; query runs and jobs directly:

```bash
PAT=...   # token with actions:read
# Latest run id
RUN_ID=$(curl -s -H "Authorization: token $PAT" \
  "https://api.github.com/repos/jesusdf/unique/actions/runs?per_page=1" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['workflow_runs'][0]['id'])")
# Per-job status + which STEP failed (this is the key to fast diagnosis)
curl -s -H "Authorization: token $PAT" \
  "https://api.github.com/repos/jesusdf/unique/actions/runs/$RUN_ID/jobs" \
  | python3 -c "
import sys, json
for j in json.load(sys.stdin)['jobs']:
    print(j['name'], j['status'], j['conclusion'])
    for s in j.get('steps', []):
        print('  ', s['number'], s['conclusion'], s['name'])
"
```

### Getting failure details WITHOUT the raw logs

**Important environment constraint:** the raw job-log download
(`/actions/jobs/{id}/logs`) 302-redirects to an Azure blob
(`*.blob.core.windows.net`) that is **not in this sandbox's network
allowlist**, so the log text cannot be fetched here. Neither can external
proxies (jina, allorigins, etc.) — all blocked. Do **not** waste time
retrying the blob URL.

Instead, get actionable detail from endpoints served by `api.github.com`:

1. **Step list** (above) — tells you *which step* failed. pytest exit code 2
   means a collection/setup error, not an assertion failure (which is exit 1).
2. **Annotations API** — surfaces the error summary and warnings:

   ```bash
   JOB_ID=...   # the failing job's id
   curl -s -H "Authorization: token $PAT" \
     "https://api.github.com/repos/jesusdf/unique/check-runs/$JOB_ID/annotations" \
     | python3 -c "import sys,json; [print(a['annotation_level'],'-',a['message'][:300]) for a in json.load(sys.stdin)]"
   ```

If full logs are genuinely needed, ask the user to read them in the GitHub
Actions web UI — that is faster than fighting the egress restriction.

**Surfacing test detail through annotations (works around the blocked blob).**
Because raw logs are unreachable here, the `syntax-live` job captures pytest
output and re-emits the failing lines as a GitHub `::error::` annotation, which
*is* readable from `api.github.com`. Pattern to reuse for any job whose detail
you need:

```yaml
run: |
  set +e
  pytest ... > /tmp/out.txt 2>&1
  rc=$?
  set -e
  cat /tmp/out.txt
  { echo '```'; cat /tmp/out.txt; echo '```'; } >> "$GITHUB_STEP_SUMMARY"
  if [ $rc -ne 0 ]; then
    DETAIL=$(grep -E "^(FAILED|E |assert|.*Engine error|.*--- sql ---)" /tmp/out.txt \
      | head -40 | sed 's/%/%25/g; s/\r//g' | awk '{printf "%s%%0A", $0}')
    echo "::error title=<job> failed::${DETAIL}"
  fi
  exit $rc
```

Read it back (decode `%0A`→newline, `%25`→`%`):

```bash
curl -s -H "Authorization: token $PAT" \
  "https://api.github.com/repos/jesusdf/unique/check-runs/$JOB_ID/annotations" \
  | python3 -c "import sys,json; [print(a['message'].replace('%0A','\n').replace('%25','%')) for a in json.load(sys.stdin) if a['annotation_level']=='failure']"
```

The step summary (`\$GITHUB_STEP_SUMMARY`) is visible in the web UI but is
**not** retrievable via these API endpoints, so the `::error::` annotation is
the reliable channel from this sandbox.

### Validating output against real engines

The Live Syntax Validation job checks transpiled SQL against the real target
engine instead of our own assumptions — the robust way to catch dialect
violations (e.g. T-SQL `CREATE TABLE IF NOT EXISTS`, stray `;` before `GO`).
SQL Server and PostgreSQL run the batches inside a rolled-back transaction (so
dependent DDL resolves); MySQL (which auto-commits DDL) runs in a throwaway
database that is dropped after. Oracle is validated with a drop-before/drop-after
cleanup.

> **The local suite (`pytest` / `scripts/test-parallel.sh` 8-shard) does NOT run
> this job.** It needs the `UNIQUE_TEST_*_URL` env vars, which the plain suite
> leaves unset (the live tests skip). So a change can be fully green locally and
> still fail CI here. This bit a char-CAST fix (`c8e5f5f`): the 8-shard + mypy
> passed, but Live Syntax Validation caught `test_procedures_fixture_is_valid_live[oracle]`
> compiling INVALID. **For any procedural, Oracle-CAST, type-mapping, or
> DDL-shape change, run the live suite locally BEFORE pushing.** The CI job runs
> the whole set (`ci.yaml` step "Run live syntax validation"):

```bash
docker compose -f docker-compose.test.yaml up -d   # postgres, mysql, mssql, oracle
UNIQUE_TEST_ORACLE_URL="oracle://system:oracle@localhost:1521/FREEPDB1" \
UNIQUE_TEST_MSSQL_URL="mssql://sa:Unique_Strong!Pass1@localhost:1433/master" \
UNIQUE_TEST_PG_URL="postgresql://unique:unique@localhost:5433/unique" \
UNIQUE_TEST_MYSQL_URL="mysql://root:root@localhost:3307/mysql" \
pytest tests/integration/test_live_syntax.py \
       tests/integration/test_corpus_live.py \
       tests/integration/test_corpus_results_live.py -q
```

(Match the URLs to your local stack — see the `unique-test-databases` memory;
credentials differ from CI's.) `test_corpus_live` sweeps the SQL corpus
(transpile → execute on the real engine); `test_corpus_results_live` goes
further and compares the *result* of source vs transpiled output, catching
wrong-answer bugs a permissive parser would miss.

The Microsoft ODBC Driver 18 (needed by `pyodbc` for SQL Server) must match
the runner's Ubuntu version; the CI step detects `VERSION_ID` and falls back
to 22.04, and points the apt source at the keyring it installs (`signed-by`).

## Dialect-Idiom Gotchas (T-SQL especially)

When emitting T-SQL, watch for non-idiomatic or invalid output (validated by
the live job):

- **No `CREATE TABLE IF NOT EXISTS`** — emit an `IF OBJECT_ID(N'schema.table',
  N'U') IS NULL` guard before the `CREATE TABLE` instead.
- **`GO`, not `;`** — T-SQL separates batches with `GO`; statements are not
  terminated with `;` (only required in specific cases such as before a CTE's
  `WITH`). Never emit `;` immediately followed by `GO`. The terminator logic
  lives in `Transpiler._ensure_terminated`, `converter.emit_sql`, and the
  `Script` node emitter — all branch on `dialect == "tsql"`.
- **No `GO` after a comment** — comment-only batches/output are glued to the
  following statement with a newline, never followed by `GO`/`;`. See
  `Transpiler._join_parts` and `_is_comment_only`.
- **No boolean literals** — `TRUE`/`FALSE` must become `1`/`0` in T-SQL output
  (WHERE clauses, DEFAULTs on `BIT`). Mapping the BOOLEAN *type* is not enough.

## Cross-engine gotchas confirmed broken in v0.7.0 (audit/2026-07-02)

Regression list — each of these shipped invalid or semantically wrong output;
when touching related code, verify the fix and its test exist:

- **Identifier quoting must be translated, never stripped**: `` `x` `` (MySQL)
  ↔ `"x"` (PG/Oracle) ↔ `[x]` (T-SQL). Stripping turns reserved-word or
  mixed-case identifiers into syntax errors and changes case-folding semantics.
- **Oracle `(+)` outer joins**: must become `LEFT/RIGHT OUTER JOIN ... ON`;
  v0.7.0 emitted `INNER JOIN` with **no ON clause** (syntax error + silent
  row loss). If unmappable, register unsupported — never inner-join it.
- **MySQL date arithmetic needs `INTERVAL`**: `DATE_ADD(ts, INTERVAL 7 DAY)`,
  never `DATE_ADD(ts, 7, DAY)`.
- **`GROUP_CONCAT` ↔ `STRING_AGG`**: PG target needs `STRING_AGG(x, sep)`;
  MySQL target needs `GROUP_CONCAT(x SEPARATOR sep)` — `GROUP_CONCAT(x, sep)`
  is valid MySQL but concatenates `sep` to every value (wrong results).
- **`ROWNUM` and `FROM dual`** must not reach non-Oracle targets:
  `WHERE ROWNUM <= n` → `LIMIT n`/`FETCH FIRST`; drop `FROM dual` for PG/T-SQL
  (MySQL tolerates it).
- **`ILIKE`** exists only in PostgreSQL — rewrite (`LIKE` for MySQL/T-SQL with
  a collation warning; `UPPER() LIKE UPPER()` for Oracle).
- **PostgreSQL rejects `CURRENT_TIMESTAMP()`** with parens (e.g. in DDL
  DEFAULTs) — emit `CURRENT_TIMESTAMP` or `now()`.
- **Oracle formal parameters must be unconstrained**: `p IN NUMBER`, never
  `p IN NUMBER(10,2)` (PLS-00103). The type mapper needs a parameter-position
  mode; same applies to PL/SQL RETURN types.
- **`THROW`/`RAISERROR` messages must survive**: map the message text into
  `RAISE EXCEPTION '<msg>'` (PG), `RAISE_APPLICATION_ERROR(-2xxxx, '<msg>')`
  (Oracle), `SET MESSAGE_TEXT = '<msg>'` (MySQL). Never substitute the error
  number for the message.
- **Zero-row semantics diverge**: T-SQL `SELECT @v = ...` leaves `@v` NULL on
  no rows; Oracle `SELECT INTO` raises `NO_DATA_FOUND`. Faithful translation
  needs an exception wrapper (or aggregate rewrite) — a bare `SELECT INTO`
  makes later `IF v IS NULL` guards unreachable.
- **MERGE → MySQL** must actually be rewritten (simple case: `INSERT ... ON
  DUPLICATE KEY UPDATE`) or registered as unsupported with a warning — never
  reduced to a comment with an empty result object.

## Documentation must track behavior

- Never mark a row ✅ in `docs/01-compatibility.md` (or claim a rewrite in
  `docs/03-unsupported.md`) without a passing probe test for that construct in
  each claimed direction. The audit found ✅ rows (ROWNUM, Boolean, MERGE→MySQL
  decomposition) that the code did not implement.
- CLI examples in README/docs must be copy-paste runnable against the real
  interface (`unique transpile [FILE] --from X --to Y [-o OUT]`); `-s/-t/-f`
  style flags in older examples do not exist.
- When behavior changes, update the matrix and README claims in the same
  commit.

## API code rules (from audit doc 04)

- FastAPI endpoints that call the (synchronous, CPU-bound) transpiler must be
  plain `def`, not `async def` — otherwise they block the event loop.
- Enforce input size limits on SQL bodies and file uploads.
- Treat client-supplied `db_url` as SSRF surface: prefer server-side named
  DSNs; never echo the URL in error responses.
