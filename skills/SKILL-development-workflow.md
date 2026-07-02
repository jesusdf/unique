---
name: unique-development-workflow
description: >
  Development workflow skill for the Unique SQL Transpiler. Use this skill
  when implementing new features, adding dialect support, writing tests,
  debugging transpilation issues, updating the backlog (docs/TODO.md), or
  committing and pushing work. Covers the mandatory pre-change analysis,
  TDD methodology, how to add new AST nodes, how to extend a dialect, testing
  patterns, the pre-commit verification gate, and the TODO + commit/push
  discipline.
---

# Unique — Development Workflow

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

### Round-trip operator/function tests (A -> B -> A')

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
```

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
but has gaps we patch in `core/converter.py` for **standalone DML** (the
procedural engine handles routine bodies separately, so a fix often needs doing
in *both* places, or the DML form lags behind):

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
Format** (black + ruff), **Type Check** (mypy), **Test** (Python 3.12), **Live
Metadata Tests** (Postgres + MySQL service containers), **Live Syntax
Validation** (Postgres + MySQL + SQL Server, validates transpiler output against
the real engines' grammar), and **Docker Build & Push** (only on a `v*` tag).

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

The Live Syntax Validation job (and `tests/integration/test_live_syntax.py`)
checks transpiled SQL against the real target engine instead of our own
assumptions — the robust way to catch dialect violations (e.g. T-SQL
`CREATE TABLE IF NOT EXISTS`, stray `;` before `GO`). SQL Server and PostgreSQL
run the batches inside a rolled-back transaction (so dependent DDL resolves);
MySQL (which auto-commits DDL) runs in a throwaway database that is dropped
after. Oracle is validated with a drop-before/drop-after cleanup. Run locally
with:

```bash
docker compose -f docker-compose.test.yaml up -d   # postgres, mysql, mssql
UNIQUE_TEST_MSSQL_URL="mssql://sa:Unique_Strong!Pass1@localhost:1433/master" \
UNIQUE_TEST_PG_URL="postgresql://unique:unique@localhost:5433/unique" \
UNIQUE_TEST_MYSQL_URL="mysql://unique:unique@localhost:3307/unique" \
pytest tests/integration/test_live_syntax.py -v
```

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
