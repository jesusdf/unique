# 04 — Code quality & guardrail compliance (v0.30.0, HEAD `69a71cd`, 2026-07-24)

Scope: `src/unique/` at v0.30.0 vs the 2026-07-08 baseline (v0.22.3, audit doc
02 improvement #3 and the 2026-07-02 doc 03). ~1,008 commits landed between the
audits. Every claim below is backed by a file:line or a reproducible command.

**Verdict in one line:** the script-layer moratorium (guardrail 1) **held**;
guardrail 2 ("never transform SQL as text") has **two clear letter violations**
(`_map_oracle_scalars_for_tsql`, `map_sequence_refs`) and one large debt
cluster (the `_emit_passthrough` regex cascade); the codebase **doubled in 16
days** (20,518 → 44,490 lines) with `converter/emit.py` at **9,992 lines**
(5.3× its audited size) and a single 2,270-line function (`_emit_function`,
cyclomatic complexity 355).

---

## 1. Module-size evolution (then → now)

Totals: **20,518** lines at v0.22.3 → **44,490** at v0.30.0 (+117%).

Previously flagged modules (renames/splits tracked via `git log --follow`):

| 07-08 module (lines) | v0.30.0 successor(s) | Lines now | Delta |
|---|---|---:|---|
| `core/procedural/parser.py` (2,886) | `parser/_base.py` + `_plsql.py` + `_tsql.py` (split `17bc529`) | 2,358 + 1,718 + 710 = 4,786 | +66% (but split ✔) |
| `core/procedural/transformer/base.py` (2,813) | `transformer/base.py` + `_expr.py` (extracted `997f0e8`) | 4,352 + 1,425 = 5,777 | +105%; base alone **+55% and >4k** |
| `core/transpiler.py` (1,713) | `transpiler/_core.py` + `_text_rules.py` (split `0e6ead0`) | 1,804 + 730 = 2,534 | +48% (split ✔) |
| `core/converter/emit.py` (1,873) | `converter/emit.py` | **9,992** | **+433%** |
| `core/converter/convert.py` (1,145) | `converter/convert.py` | 2,790 | +144% |
| `core/mappings.py` (488) | `core/mappings.py` | 1,161 | +138% — *desirable* growth (shared table, see §7) |
| `core/transformer.py` (485) | `core/transformer.py` | 2,445 | **+404%** |
| `core/procedural/emitter/base.py` (1,489) | same | 2,029 | +36% |

Files now over the ~2,000-line threshold (six, vs three at 07-08):
`converter/emit.py` 9,992 · `procedural/transformer/base.py` 4,352 ·
`converter/convert.py` 2,790 · `core/transformer.py` 2,445 ·
`procedural/parser/_base.py` 2,358 · `procedural/emitter/base.py` 2,029.

The 07-08 improvement #3 ("resume the module-size work") was **partially
executed**: the three splits it asked for (parser, transpiler, converter
package) all happened. But the campaign volume (RED corpus 862 findings →
BLUE fixes) landed overwhelmingly in `converter/emit.py` (380 commits touch
it) and `procedural/transformer/base.py`, and no size discipline was applied
there — `emit.py` is now larger than the entire v0.22.3 converter package
plus the procedural transformer combined.

### Natural split seams for the worst offenders

- **`converter/emit.py` (9,992)** — it is a flat module of 100 top-level
  functions; the three giants are self-contained:
  - `_emit_function` (line 6289, **2,270 lines**) → `converter/emit_functions.py`.
    Internally it is one `if fn_name == …` chain; the second-order fix is a
    `dict[str, handler]` registry per function name (and pushing the pure
    spelling-swaps into `core/mappings.py`, which both pipelines already read).
  - `_emit_passthrough` (line 1545, **1,085 lines**) + `_emit_passthrough_inline`
    (line 4715, 178) → `converter/emit_passthrough.py` (see §2, F3).
  - DDL family: `_emit_create_table` (line 4043, 670) + neighbors →
    `converter/emit_ddl.py`; expression family: `_emit_expression` (line 5038,
    738) + `_emit_binary` (line 8768, 623) → `converter/emit_expr.py`.
  The package split pattern (star re-export via `_base`, per-file F403/F405
  ignore in `pyproject.toml`) already exists, so the mechanical cost is low.
- **`procedural/transformer/base.py` (4,352)** — largest members are
  `_transform_raw_sql` (line 4110, 181), `_transform_data_type` (line 774,
  179), `_transform_function` (line 1672, 147), `_transform_trigger` (line
  1820, 143). Seams: the RawSQL/embedded-DML machinery (`_transform_raw_sql`
  and its helpers) into `transformer/_rawsql.py`, and the type-mapping block
  into `transformer/_types.py` — both follow the precedent set by `_expr.py`
  (`997f0e8`).
- **`core/transformer.py` (2,445)** — `TypeMapper.visit` (line 218, 179 lines)
  and the sqlglot-tree rewrites; seam: `TypeMapper` into its own module.

---

## 2. Guardrail compliance sweep (binding rules, skill §"Architecture guardrails")

Method: diffed the regex/text-transform surface of the script layer
(`transpiler/*`, `batch_splitter.py`) against v0.22.3, then classified every
rule added since as sanctioned (M2/P3 unified recognizer, trivia, carriers,
pre-parse strips **with warnings**) or shape-patch/text-transform.

### Held: the script-layer moratorium (guardrail 1)

- `batch_splitter.py`: 23 → 25 compiled regexes (both additions are splitting/
  lexing aids, not classification cascade holes); `classify_batch` is the same
  single function (C901 = 21, unchanged in character).
- `transpiler` layer `re.sub` count: 17 → 23. The five text-rule functions
  added since v0.22.3 (`src/unique/core/transpiler/_text_rules.py`) break down
  as: `_extract_catalog_guard` (line 196) — this **is** the sanctioned M2/P3
  "ONE recognizer" consolidation, operates on trivia-free text via the shared
  `split_leading_trivia` (guardrail 3 respected); `_mysql_safe_comments`
  (line 285) — comment-syntax trivia; `_qualify_tsql_udfs_in_sql` (line 177) —
  uses the shared string/comment-aware walker `qualify_function_calls`, not raw
  regex; `_normalize_oracle_multicolumn_drop` (line 144) — pre-parse rewrite of
  a statement sqlglot cannot parse at all (documented sqlglot-gap category);
  and `_map_oracle_scalars_for_tsql` — see F1. The pre-parse strips in
  `_core.py` (TEXTIMAGE_ON line 909, WITH [NO]CHECK ADD lines 928-929,
  ORGANIZATION INDEX/HEAP line 951) each emit a warning/carrier, matching
  guardrail 5.

### F1 — VIOLATION of guardrail 2: `_map_oracle_scalars_for_tsql` (severity: high)

`src/unique/core/transpiler/_text_rules.py:159-174`, called from
`transpiler/_core.py:838` **after** the AST pipeline, over the whole converted
output of every oracle→tsql DML batch:

```python
sql = re.sub(r"(?i)\bCHR\s*\(", "CHAR(", sql)
sql = re.sub(rf"(?is)\bTO_NUMBER\s*\(\s*{_SCALAR_ARG}\s*\)",
             r"CAST(\1 AS DECIMAL(38, 10))", sql)
sql = re.sub(rf"(?is)\bMONTHS_BETWEEN\s*\(...", r"DATEDIFF(MONTH, \2, \1)", sql)
```

This is the exact shape guardrail 2 bans: *"Function/type/literal/operator
mappings go in the IR converter + core/mappings.py, applied on the AST — never
as an `re.sub` over SQL text."* The docstring even names the reason it exists
("sqlglot passes through untranslated in plain DML") — i.e. the converter gap
was patched in the script layer instead of in `_convert_function`/`mappings.py`.
Concrete defects it carries: (a) `_SCALAR_ARG` (line 156) matches only one
paren level, so `TO_NUMBER(SUBSTR(x, INSTR(y, ','), 3))` mis-captures;
(b) it runs on final text, so `CHR(` inside a string literal or comment is
rewritten (guardrail 3: "no matching on text that can still contain comments").

**Recommendation:** move the three mappings into the DML converter
(`convert.py `/`mappings.py`) where the procedural pipeline already has them
(the call-site comment admits "the procedural paths map them via the
transformer"), delete the text rule, and add oracle→tsql round-trip probes with
a nested-call case and a `'CHR('`-in-literal case.

### F2 — VIOLATION of guardrail 2 (same class): `map_sequence_refs` (severity: medium)

`src/unique/core/converter/emit.py:565-595`, called post-emit from
`transpiler/_core.py:828` for oracle→{tsql,postgresql}:
`_SEQ_NEXTVAL_RE = re.compile(r"(?i)\b([A-Za-z_]\w*)\s*\.\s*NEXTVAL\b")` is
substituted over the whole converted batch text. Any `x.NEXTVAL` inside a
string literal or comment is rewritten; a column actually named `nextval`
qualified by alias would also match. Mitigating: the CURRVAL branch degrades to
a documented carrier (guardrail 4/5 respected).
**Recommendation:** intercept `Dot(seq, NEXTVAL)`/`Column(nextval)` in the
sqlglot-tree transformer (`core/transformer.py`) instead; keep the carrier
behavior for T-SQL CURRVAL.

### F3 — Debt cluster / circuit-breaker #4 ("fallbacks only ever grow"): the `_emit_passthrough` regex cascade (severity: high, not a letter violation)

`converter/emit.py:1545` (`_emit_passthrough`, 1,085 lines, C901 = 137) is the
raw-`sqlglot.transpile` fallback for statements the IR does not model. Since
v0.22.3 it accreted a cascade of text-level construct rewrites over the
passthrough SQL — `STRAIGHT_JOIN` → `INNER JOIN` (line 1582), `ALTER VIEW` →
`CREATE OR REPLACE VIEW` (line 1597), MODIFY-column re-spelling, and ~27
`re.sub` calls inside this one function; `emit.py` as a whole went from 23 to
82 `re.sub` calls and carries **57 "wave NNN" comments** (plus 26 in
`convert.py`) — each one an instance-level patch with its wave number attached.
Each entry is individually documented and mostly warned, so this is not silent
corruption; but it is precisely the doc-04 M3 goal inverted: the regex cascade
did not reopen in `transpiler.py` — it **relocated into the converter's
fallback**, where guardrail 1's moratorium does not textually apply.
**Recommendation:** (a) split it out (`emit_passthrough.py`) so its size is
visible; (b) treat every new `re.sub` on `node.sql` there as requiring the same
justification as a script-layer regex (extend the moratorium wording in the
skill to name this function); (c) burn the cascade down by modeling the top
recurring kinds (ALTER VIEW, MODIFY, sequence DDL options) in the IR, which is
the stated M3 direction.

### Performance rule (`+=` in input-proportional loops): CLEAN

AST scan of every `AugAssign(Add)` inside a loop (scratchpad `aug_scan.py`):
all hits are numeric counters, per-statement clause assembly over a *fixed or
small* set (e.g. `emit.py:3849` appends per-JOIN of one statement,
`procedural/emitter/tsql.py:239` per hoisted parameter). No whole-script
string accumulation; `_join_parts`-class regressions have not returned.

### No committed scratch/coverage artifacts

`git ls-files` shows no `scratchpad`/`triage` files; `coverage.xml` exists at
the repo root but is untracked and ignored (`.gitignore:47`). Clean.

---

## 3. Function length / complexity hotspots

`ruff check --select C901` (default max-complexity 10): **107 functions over
the limit**. Note **C901 is not in the enabled rule set**
(`pyproject.toml [tool.ruff.lint] select = ["E","F","I","N","W","UP","B","SIM"]`),
so complexity is entirely ungated today. Worst offenders:

| Function | Complexity | Lines | Location |
|---|---:|---:|---|
| `_emit_function` | **355** | 2,270 | `converter/emit.py:6289` |
| `_emit_passthrough` | 137 | 1,085 | `converter/emit.py:1545` |
| `_emit_expression` | 109 | 738 | `converter/emit.py:5038` |
| `_emit_binary` | 94 | 623 | `converter/emit.py:8768` |
| `_emit_create_table` | 92 | 670 | `converter/emit.py:4043` |
| `_convert_expression_impl` | 67 | 335 | `converter/convert.py:732` |
| `Transpiler.transpile` | 65 | 373 | `transpiler/_core.py:155` |
| `_tokenize_one` | 58 | — | `procedural/lexer.py` (was 198 lines/07-02 — still not table-driven) |
| `_emit_select` | 55 | 415 | `converter/emit.py:3089` |
| `_convert_create_table` | 50 | 393 | `converter/convert.py:1542` |

For calibration: at 07-02 the worst function in the repo was ~200 lines.
`_emit_function` alone is now larger than most whole modules.
**Recommendation:** add `C901` to the ruff select with `max-complexity` set
just above the current worst-10 floor via per-file ignores (a ratchet), so new
code cannot join the list while the giants are burned down by the §1 splits.

---

## 4. Duplication across the per-target procedural plugins

Measured body similarity (difflib) of same-named overrides in
`procedural/{transformer,emitter}/{tsql,oracle,postgresql,mysql}.py`:

| Method | Pair | Similarity |
|---|---|---:|
| `_transform_exception_block` | transformer tsql vs mysql | **1.00 (identical, 251 chars)** |
| `_translate_cursor_attrs` | emitter tsql vs postgresql | 0.90 |
| `_rc_increment_sql` | transformer tsql vs mysql | 0.82 |
| `_map_cursor_attributes` | transformer tsql vs mysql | 0.51 |
| `_emit_execute_stmt` | emitter tsql vs oracle | 0.11 |

Verdict: **the plugin layer is healthy overall** — most same-named methods are
genuine per-dialect variation (similarity ≤ 0.6), which is the hook pattern
working. Debt items: the byte-identical `_transform_exception_block`
(`transformer/tsql.py:1145` = `transformer/mysql.py`) should be hoisted to
`base.py` (both flatten handlers into a `TryCatchBlock`), and the 0.82–0.90
pairs are one behavior fix away from silent drift — hoist with a small
spelling hook. (Note: the `scan: tsql,tsql` duplicate flagged by the name scan
is a false positive — two local closures in different methods,
`transformer/tsql.py:732` and `:745`.)

---

## 5. Dead code / orphans (debt, pre-existing — report, don't delete)

Reference scan over all of `src/` + `tests/` (definition-only names):

- **Five IR node classes are never constructed or referenced anywhere**:
  `ParameterRef` (`core/ast_nodes.py:203`), `AlterTableStatement` (`:613`),
  `CreateIndexStatement` (`:621`), `CreateSequenceStatement` (`:642`),
  `TypeReference` (`:905`). They look like planned IR coverage (ALTER/INDEX/
  SEQUENCE currently ride the PassthroughSQL path — see F3): either wire them
  up as part of the M3 burn-down or remove them; today they are dead weight
  that misleads readers about what the IR models.
- `builtins_for` (`core/builtins.py:137`) — public helper with zero callers
  (only `is_builtin` is used). Remove or use.
- All 12 `ContextVar`s in `converter/_base.py` are referenced from ≥2 files —
  none orphaned.
- No TODO/FIXME/XXX markers beyond 3 benign mentions; no leftover scratch
  scripts in the tree (§2).

---

## 6. Type safety

- `mypy` strictness is **unchanged and strong**: `[tool.mypy] strict = true`,
  `python_version = "3.13"`, plus a narrowly-scoped
  `disable_error_code = ["unused-ignore"]` override for exactly the two
  optional-DB-driver modules (`live_validate`, `metadata`) with a written
  rationale (`pyproject.toml:118-126`). This is the right shape.
- `# type: ignore` count: **10 (v0.22.3) → 35 (now)** — 3.5× against a 2.2×
  code growth, i.e. mild inflation. Distribution is flat (max 5 per file:
  `core/transformer.py`, `converter/emit.py`) — no single hot spot; most sit
  at sqlglot-API boundaries. Debt, not a violation; keep the count in the
  audit ratchet.
- The 07-02 nit "black/ruff target-version lags requires-python" is fixed
  (everything is py313).

---

## 7. Registry/plugin architecture health

Count of `== "tsql"|"oracle"|"postgresql"|"mysql"|"sqlite"` string-dispatch in
*shared/base* modules:

| Shared module | v0.22.3 | v0.30.0 |
|---|---:|---:|
| `procedural/emitter/base.py` | — | **0** ✔ (model citizen — all dispatch via subclass hooks) |
| `procedural/parser/_base.py` | — | 10 |
| `procedural/transformer/base.py` | 39 | **66** (+69%) |
| `core/transformer.py` | — | 25 |
| `converter/convert.py` | — | 8 |
| `converter/emit.py` | — | **486** |

Two architectures coexist. The **procedural** stack genuinely follows the
promised plugin shape (per-dialect subclasses; the emitter base has *zero*
dialect string-compares; adding a dialect there is "one module per layer") —
though its transformer base is re-accreting inline dialect branches (39→66)
that belong in the subclasses. The **DML/converter** stack is the opposite:
`emit.py` is one flat module where every function branches on the dialect
string 486 times. Adding a fifth engine today means editing essentially every
function in `emit.py` — the 07-02 finding ("plugin architecture thinner than
advertised") is now an order of magnitude more true on the DML side.

Positive counterweight: `core/mappings.py` (488→1,161) is now imported by
**both** pipelines (`converter/_base.py`, `converter/emit.py`,
`core/transformer.py`, `procedural/transformer/{base,_expr,tsql}.py`) — the
07-02 "single declarative mapping layer" recommendation is real and growing;
and the M1 honesty gate exists as its own module (`core/output_gate.py`, 676).

**Recommendation:** declare the direction explicitly: either (a) accept that
the DML emitter is dialect-dispatch-by-string and contain it behind the §1
splits + a ratchet on new `== "dialect"` sites, or (b) begin folding pure
spelling decisions into `mappings.py` tables (the data already flows to both
pipelines). Also move the 27 new inline branches in
`procedural/transformer/base.py` into the existing per-dialect subclasses as
they are next touched.

---

## Findings ranked

| # | Class | Finding | Action |
|---|---|---|---|
| F1 | **Guardrail violation** | `_map_oracle_scalars_for_tsql`: post-emit regex function-mapping (`_text_rules.py:159`) | Move to converter/mappings; delete rule; add nested-call + literal probes |
| F2 | **Guardrail violation** | `map_sequence_refs`: post-emit regex NEXTVAL/CURRVAL mapping (`emit.py:565`) | AST-level interception in `core/transformer.py` |
| F3 | Debt (breaker #4) | `_emit_passthrough` 1,085-line regex cascade; 57 wave-patch comments in `emit.py` | Split out; extend moratorium wording; model top kinds in IR (M3) |
| F4 | Debt | `emit.py` 9,992 lines / `_emit_function` 2,270 lines, C901 355; 6 files > 2k | §1 seams; registry dispatch for `_emit_function` |
| F5 | Debt | Complexity ungated: 107 C901 offenders, rule not enabled | Enable C901 with per-file ratchet |
| F6 | Debt | Shared `procedural/transformer/base.py` dialect branches 39→66 | Push into subclasses on touch |
| F7 | Debt | 5 dead IR node classes + `builtins_for` | Wire up in M3 or remove |
| F8 | Debt (minor) | Identical/near-identical plugin helpers (`_transform_exception_block` 1.00) | Hoist to base with hooks |
| F9 | Watch | `type: ignore` 10→35 | Track in ratchet |

Clean bills: script-layer moratorium held (batch splitter flat, new transpiler
rules sanctioned or warned); `+=` performance rule clean; no committed scratch
artifacts; mypy strict intact; ContextVars all live; procedural emitter base
has zero dialect dispatch.
