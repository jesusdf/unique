# 04 — Architecture analysis: why fixing the TODO never converges, and what to change

Requested question: *given everything that is failing (docs 02–03), does the
architecture or design need to change to reach a functional product? Today,
every time the TODO is emptied, testing a new real script surfaces new
transpilation errors.*

Short answer: **no rewrite is needed — the statement-level core is sound — but
four structural changes and one process change are.** The whack-a-mole loop is
not bad luck; it is the predictable output of three specific design choices.
Fixing bug lists without fixing those choices will reproduce the loop forever,
because the input grammar (decades of real-world SQL in four dialects, plus
generator styles like SSMS/SSMA and SQL*Plus conventions) is effectively
unbounded, while each current fix handles one literal shape.

---

## 1. Diagnosis: five root causes behind the ~40 findings

Mapping every finding from docs 02–03 to its mechanism collapses them into
five root causes. The evidence lines are from the current code.

### RC1. The script layer is a regex cascade with silent fallbacks

Statement *translation* is AST-based, but script *structure* — batches,
classification, migration guards, terminators — is regex-driven string
surgery: `batch_splitter._classify` routes on `re.match` over raw text, and
`transpiler.py` (1,713 lines, doubled since the last audit, 49 regex call
sites) hosts a chain of guard extractors (`_IF_OBJECT_PATTERN`,
`_extract_exists_guard`, `_CATALOG_REF_RE`, drop-guard rewriting…). Each
recognizer matches one literal spelling; **everything that misses falls into a
fallback that comments the batch out or passes it through**, usually with a
mislabeled warning ("SET option commented out: IF OBJECT_ID…").

That is why the guard family keeps producing bugs: N1 (unbracketed data guard
loses its condition), N10/A2 (`BEGIN…END` wrapper → commented out), A1
(leading comment → commented out), A3 (leading comment → missing `/`), A5
(idempotency lost on PG). The combinatorics — {condition kind} × {BEGIN or
not} × {leading comment or not} × {OBJECT_ID arity} × {body kind} × {target}
— cannot be enumerated by regexes; there is always an untested cell. **This is
the shotgun-parser anti-pattern the project's own architecture doc forswears.**

### RC2. Embedded DML bypasses the project's own pipeline

Standalone DML flows through the IR converter/transformer — the code where all
the 2026-07-02 fixes, the shared `mappings.py`, and the warning machinery
live. But DML *inside routine bodies* takes a different path
(`procedural/transformer/base.py:1526`): **raw `sqlglot.transpile` with
`error_level=WARN`** (silent passthrough on anything sqlglot can't map),
bracketed by ~37 regex-based text fixups (`_rewrite_string_concat` — 118 lines
of *text* rewriting, `_map_now_in_sql`, `_fix_target_dml`,
`_oracle_function_fixes`…). Other fragments (`SELECT INTO` tails, cursor
queries, conditions) are carried as raw text and share those fixups.

Consequences, all observed on real scripts: `ROWNUM` and `FROM DUAL` are
translated in standalone DML but survive inside routine bodies (D3, D4);
`NEWID()` maps per-target standalone but becomes MySQL's `UUID()` on Oracle
inside a guard (A4); and the text-level rewriters produce the worst finding of
the sweep — `MAX(NVL(n,0)) + 1` **losing tokens** on T-SQL and turning numeric
`+` into `||` on PostgreSQL (D8). A text rewriter can corrupt expressions; an
AST transform structurally cannot. The dual-pipeline asymmetry was named in
the 2026-07-02 audit; `mappings.py` shared the *tables*, but not the *engine*
that applies them.

### RC3. Comments are handled ad hoc at every layer

At least six recent commits (header-comment round-trip, splitter
mis-classification, comment-only batches, GO-after-comment…) and four new
findings (A1, A3, B4/N16, plus the mislabeled warnings quoting comment text)
are all the same defect: **comments are not a first-class token**. Every layer
— splitter classification, guard extractors, the procedural parser, terminator
logic — re-invents comment handling, and each re-invention has its own hole
(B4: a bare `RETURN` eats the next comment as its "value"; A1: a leading
comment defeats the guard recognizer; A3: it defeats the `/` terminator).

### RC4. Failures are silent instead of loud

Three symptoms of one missing invariant:

- The procedural parser, when it desyncs (D9: `create or replace⏎PROCEDURE` +
  a `<codegen>` header comment), **spills declaration fragments as top-level
  batches** instead of failing the unit.
- Emitters happily ship output that is not even parseable in the target
  grammar (`PRIMARY KEY, CLUSTERED (…)`, `EXEC AS proc`, `DATE_TRUNC` on
  T-SQL) — nothing in the *product* ever checks its own output; validity
  checking exists only in the test suite and CI.
- Warnings are so noisy (11,766 on one 38k-statement dump, most of them
  per-occurrence `set_option` repeats) and sometimes wrong (N5's false
  "FOR loop has no equivalent", RC1's mislabels) that they can't serve as the
  no-silent-loss signal they are meant to be.

### RC5. The definition of done is "the fixture passes"

The workflow is TDD per shape: real dump → failure → minimal fixture → fix →
green → TODO done. Each cycle is locally correct, but the metric never says
how much of the *input grammar* is covered — so "TODO empty" and "next dump
breaks" coexist indefinitely. The project already proved the countermeasure
works in another dimension: the identity-mutation floor turned test assertion
quality from anecdotes into a ratcheted number. Output validity needs the same
treatment.

---

## 2. What does NOT need to change

- **The IR + sqlglot statement core.** Every 2026-07-02 statement-level bug
  stayed fixed; the FE harness holds 16/16 pairs on the curated scenario. Keep.
- **The per-engine plugin shape of the procedural emitters/transformers.** The
  factory/hook design is good; the problem is what flows through it (raw
  text), not the structure.
- **The external validation stack** (live syntax, corpus, differential
  results, FE harness, mutation gates) — it is what caught all of this. It
  needs to be *promoted into the product and the process*, not changed.
- **No new IR, no parser-generator migration (yet)** — see §5 contingency.

---

## 3. Proposed changes (design)

Ordered so that each one removes a *class* of bugs, with the highest
leverage-to-effort first.

### P1 — Honesty gate: the transpiler validates its own output (small, do first)

After emitting any DML/DDL unit, parse it with sqlglot in the **target**
dialect (`error_level=RAISE`); after emitting any procedural unit, run cheap
structural checks (balanced BEGIN/END, a per-target deny-list of
source-only leftovers: `VARCHAR2|ROWNUM|EXEC AS|GO` in PG output, etc.).
On failure: **never ship the invalid text** — degrade to the documented
carrier + `unsupported` entry, exactly like other lossy paths.
Complementarily: a parser desync must fail the whole unit into a carrier
(never spill fragments), and warnings must be deduplicated/aggregated
(one warning with a count, not 338 repeats) and correctly labeled.

Effect: the S1 class ("invalid or corrupted SQL, silently") becomes
structurally impossible; every remaining gap is visible, counted, and honest.
This one change turns the product from "sometimes lies" into "always tells
you". It also gives P5 its metric for free. Estimated effort: days, not weeks
— `tests/helpers/validity.py` already contains the logic.

### P2 — Comments become trivia (small/medium)

One implementation, used by every layer: the splitter/lexer attaches comment
runs to the *following* statement as metadata ("leading trivia"), all
classification and matching operates on trivia-free text (partially true
today), and emitters re-emit trivia and apply terminator logic *after* it.
Guard extraction, `/` termination, RETURN parsing, and batch classification
all stop seeing comments entirely. Kills A1, A3, B4, the mislabeled warning
texts, and the recurring "comment broke X" commit genre.

### P3 — One guard path, decided on the AST (medium)

Delete the regex guard recognizers/extractors from `transpiler.py`. The
splitter routes **every** `IF`-headed batch to the procedural engine — which
already has a real parser for `IF`, conditions, and blocks. There, a single
transform decides on the *AST*: does the condition reference a system catalog
(known catalog tables / `OBJECT_ID`), or real data? Then each target
transformer renders its native idempotent form (`IF NOT EXISTS` DDL clauses,
`DROP … IF EXISTS`, the Oracle guard FOR-loop / `EXECUTE IMMEDIATE`, PG
`DO $$`), keeping data-guards as control flow, warning only where the target
truly has no form. One decision point, one test matrix, no fallback that
comments things out. Clears N1, N10, A1–A5 by construction, and shrinks
`transpiler.py` back toward the orchestrator the architecture doc promises.

### P4 — Embedded DML goes through the IR pipeline (medium/large, biggest payoff)

`_transform_embedded_dml` (and the raw-text tails of `SELECT INTO`, cursor
queries, and conditions) switch from raw `sqlglot.transpile` + text fixups to
the same `parse_sql → transform → emit` IR path standalone DML uses — the
table-variable DDL path (`_table_variable_to_temp_table`) already does exactly
this, so the pattern exists in-tree. Raw sqlglot remains only as an explicit,
*warned* fallback. The text-level expression rewriters (`_rewrite_string_concat`
et al.) are deleted; their logic already exists as AST transforms on the
standalone side. Effect: D3, D4, D8, A4 and the whole "mapped in one pipeline,
not the other" genre become impossible — one mapping engine, two callers. This
is the completion of the 2026-07-02 "deduplicate dialect knowledge"
recommendation, and the single highest-value refactor available.

### P5 — Corpus-metric ratchet: change the definition of done (process)

Productize this audit's sweep as `scripts/validity_sweep.py`: transpile a
corpus, execute per-statement against the Docker engines, classify
(syntax-class = defect; missing-object = expected), report **per-direction
validity percentages** and a per-class frequency table. Then:

- **Release metric.** STATUS/README state measured numbers per direction
  ("T-SQL→PostgreSQL: 99.x% of 51k statements valid"), never "complete".
- **CI ratchet** on the public corpus (like the mutation floor); the private
  corpora run locally/nightly, and every failing class found there lands as an
  *anonymized shape* in the public corpus — over time the corpus converges on
  the real-world grammar distribution.
- **Prioritize by frequency × severity** from the sweep table (e.g. `FROM
  DUAL` in INSERT-guards ≈ 6,000 occurrences vs. one exotic PK spelling).
- **Property-based shape generation** for the combinatorial surfaces
  (guards: condition × wrapper × trivia × body × target) asserting the P1
  invariants — finds the untested cell before a client script does.

This is the answer to "cada vez que completo el TODO aparecen errores": the
TODO stops being the goal; the number does.

### P6 — Scope the promise per direction (product)

The data says maturity is wildly asymmetric: T-SQL→X is near-usable;
Oracle→X emits 29–44% invalid statements on a real dump. Tier the matrix
publicly: **Tier 1 (supported, with measured validity)** and **Tier 2
(experimental)**, promoting a direction only when the corpus metric crosses a
threshold. This makes "functional product" achievable *incrementally* and
honestly, instead of a single binary that testing keeps falsifying. The
Oracle-source direction then becomes a planned bring-up (doc 03 §D is its
backlog) rather than a standing embarrassment.

---

## 4. Suggested sequencing

| Milestone | Content | Exit criterion (measured) |
|---|---|---|
| **M0** | P5 harness productized; baselines recorded | validity % per direction on both corpora |
| **M1** | P1 honesty gate + desync-to-carrier + warning dedup/labels | zero syntax-class errors *shipped silently*: every invalid unit is a carrier + warning |
| **M2** | P2 trivia + P3 unified guards | guard property-suite green; T-SQL→X validity on the private migration corpus > 99% |
| **M3** | P4 embedded DML through IR; delete text rewriters | asymmetry probes impossible-by-construction; procedural corpus validity matches standalone |
| **M4** | Oracle-source bring-up from doc 03 §D, priority by frequency | Oracle→X validity > 95% then > 99% |

M1 is deliberately before the refactors: once the product cannot lie, every
subsequent step is measurable and safe to do incrementally. **Moratorium
during M1–M3: no new regex shape-patches in `transpiler.py`** — new guard/DML
shapes must land in the AST paths, or the cascade grows back.

## 5. Contingency and rejected options

- **ANTLR (grammars-v4 T-SQL/PL/SQL) for the procedural parser** — only if,
  after M3, corpus metrics stall on parser-coverage gaps (D9-class). The
  hand-written parser handled most of a 217k-line dump; its failure mode
  (silent desync) is fixed by P1/RC4 at a fraction of the cost of a grammar
  migration. Revisit with data.
- **Full rewrite / new IR** — rejected: the failing 20% is localized (script
  layer, embedded-DML path); the IR and per-engine plugin design are pulling
  their weight.
- **LLM-assisted translation fallback** — rejected for the product core:
  non-deterministic, unverifiable; the project's value proposition is the
  opposite.

## 6. One-paragraph summary

The product's core (IR + sqlglot + per-engine plugins + live validation) is
healthy. What keeps generating bugs is everything that *bypasses* that core:
a regex classification cascade at the script layer, raw-text transformation of
embedded DML, ad-hoc comment handling, and fallbacks that fail silently.
Close the bypasses (P2–P4), make failure loud and honest (P1), and replace
"TODO empty" with a measured per-direction validity ratchet (P5–P6). None of
this is a rewrite; all of it is finishing the architecture the documentation
already promises.
