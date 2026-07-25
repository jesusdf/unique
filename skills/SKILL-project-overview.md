---
name: unique-project-overview
description: >
  Overview skill for the Unique SQL Transpiler project. Use this skill whenever
  resuming work on the Unique project after a session break. It provides full
  context on the project goals, architecture decisions, current status, and
  coding conventions so that development can continue seamlessly.
---

# Unique — SQL Transpiler Project Overview

## What is Unique?

Unique is a Python-based SQL transpiler that translates SQL scripts between four
database engines: **SQL Server (T-SQL)**, **Oracle**, **PostgreSQL**, and **MySQL**.
It supports SQL scripting features (variables, control flow, stored procedures)
from versions 2012 onward.

## Core Design Decisions

1. **AST-based transpilation** — SQL is parsed into an engine-agnostic Abstract
   Syntax Tree (Intermediate Representation), then emitted as the target dialect.
   This is more reliable than regex/string replacement and more maintainable than
   direct source-to-source rewriting.

2. **Plugin architecture** — Each database dialect is a self-contained plugin that
   implements a `Dialect` interface with a `Parser` and an `Emitter`. Adding a new
   engine means adding a new plugin without touching the core. The **procedural
   engine follows the same per-engine shape**: its emitter and transformer are
   packages with a `base.py` (shared logic + overridable hooks) and one
   self-registering module per target (`tsql.py`, `oracle.py`, …) selected by a
   factory — no `if dialect == …` dispatch in the base. Adding an engine there is
   one new emitter module + one new transformer module.

3. **Python 3.13** — the single supported/CI version (ecosystem richness,
   readability, tooling). sqlglot does the per-statement parsing; Unique adds an
   autonomous procedural engine for the stored-routine shell sqlglot can't model.

4. **TDD with pytest** — Every feature starts with a failing test. The test suite
   lives in `tests/` and mirrors the `src/` structure.

5. **Clean Code** — Small functions, meaningful names, single responsibility.
   No function longer than ~30 lines. Docstrings on every public symbol.

## Repository Layout

```
unique/
├── docs/                         # Markdown documentation
│   ├── 01-compatibility.md       # SQL feature compatibility matrix
│   ├── 02-architecture.md        # Architecture & design decisions
│   ├── 03-unsupported.md         # Features explicitly out of scope
│   ├── 04-development-guide.md   # How to add features, run tests
│   ├── 05-procedural-engine.md   # The stored-routine pipeline
│   ├── 06-installation.md        # pip / Docker / compose
│   ├── 07-interfaces.md          # CLI / Python / REST / web UI
│   ├── STATUS.md                 # Current project state
│   ├── TODO.md                   # Pending backlog (authoritative)
│   ├── MILESTONES.md             # Closed backlog sections (newest first)
│   └── DONE.md                   # Archived completed work (why/how)
├── skills/                       # Claude AI continuity skills
├── src/unique/
│   ├── core/
│   │   ├── ast_nodes.py          # IR node definitions
│   │   ├── converter/            # sqlglot AST ↔ IR conversion + DML/DDL emit
│   │   │   ├── _base.py          #   (hosts the sqlglot DML workarounds:
│   │   │   ├── convert.py        #   string +→concat, bitwise ops, fn args)
│   │   │   ├── emit.py
│   │   │   └── harvest.py
│   │   ├── mappings.py           # Shared dialect knowledge (functions/types/
│   │   │                         #   literals) consumed by BOTH pipelines
│   │   ├── validation.py         # Source-syntax validation (locate errors)
│   │   ├── transformer.py        # DML/DDL transform passes
│   │   ├── transpiler/           # Orchestrator (package since 2026-07-17):
│   │   │   ├── _core.py          #   split → classify → route → join
│   │   │   └── _text_rules.py    #   sanctioned pre-parse strips / guard recognizer
│   │   ├── batch_splitter.py     # Dialect-aware batch splitting + classification
│   │   ├── output_gate.py        # M1 honesty gate (never ship known-invalid output)
│   │   ├── sql_split.py          # Shared string/comment-aware statement splitter
│   │   ├── builtins.py / dialect.py / live_validate.py
│   │   ├── detection.py          # Source-dialect auto-detection
│   │   ├── metadata.py           # Optional DB connection for %TYPE/%ROWTYPE
│   │   ├── registry.py           # Plugin registry (entry-point discovery)
│   │   ├── errors.py             # Custom exceptions
│   │   └── procedural/           # Autonomous procedural engine
│   │       ├── lexer.py          #   tokenizer for procedural SQL (engine-agnostic)
│   │       ├── parser/           #   recursive descent (package: _base.py + _tsql.py/_plsql.py)
│   │       ├── transformer/      #   per-target transform plugins
│   │       │   ├── base.py       #     shared + source/pair logic, factory, maps
│   │       │   └── {tsql,oracle,postgresql,mysql}.py
│   │       └── emitter/          #   per-target emission plugins
│   │           ├── base.py       #     shared structure + overridable hooks, factory
│   │           └── {tsql,oracle,postgresql,mysql}.py
│   ├── dialects/{tsql,oracle,postgresql,mysql,sqlite}/  # Dialect plugins — each a
│   │                             #   SINGLE __init__.py (knowledge lives in
│   │                             #   core/mappings.py + procedural plugins)
│   ├── cli/                      # CLI entry point
│   └── api/                      # REST API (FastAPI) + web UI
├── web/                          # Web UI source + build (build.py)
├── tests/
│   ├── unit/, integration/, property/   # Test suites
│   ├── helpers/                  # live_validation, invariants, functional_equiv
│   ├── fixtures/                 # SQL fixtures (incl. procedures/ for 4 engines)
│   └── functional_equivalence/   # Functional-equivalence test DB (design + assets)
├── Dockerfile / Dockerfile.dev / docker-compose.yaml
├── .github/workflows/ci.yaml
├── pyproject.toml
└── README.md
```

## Dialect Plugin Interface

Every dialect must implement:

```python
class Dialect(ABC):
    name: str                    # e.g. "tsql", "oracle"
    
    @abstractmethod
    def parse(self, sql: str) -> list[ASTNode]:
        """Parse raw SQL into a list of IR nodes."""
    
    @abstractmethod
    def emit(self, nodes: list[ASTNode]) -> str:
        """Emit IR nodes as SQL in this dialect."""
    
    @abstractmethod
    def supported_features(self) -> set[str]:
        """Return set of feature tags this dialect handles."""
```

## Current Status Tracking

When resuming work, check `docs/STATUS.md` for the latest progress tracker.
Each completed feature should have corresponding tests in the test suite.

**Also check `audit/` for the latest audit** (`audit/2026-07-02/`,
`audit/2026-07-08/`, **`audit/2026-07-24/` — current**). Audits are ground
truth about real defects and must not be contradicted by STATUS/README claims.

**The 2026-07-24 audit's ENTIRE backlog is executed (2026-07-25, v0.32.0)** —
all fix briefs B1–B28, the tools T1–T7, the follow-on findings the campaign
itself surfaced, and the B28 features, worked brief-first by worker agents
under architect review (`docs/MILESTONES.md`, `docs/DONE.md` §44–§45; only
two maintainer decisions remain in `docs/TODO.md`). What that campaign left
as STANDING MACHINERY, which every future session works under:
- **Guardrail 7 + the unread-args tripwire** (`UNIQUE_UNREAD_ARGS`, default
  warn) — sqlglot args must be consumed or warned.
- **Architecture ratchets in CI** (`scripts/architecture_ratchets.py`) —
  emitter size, post-emit regex surface, dialect dispatch, C901 offenders
  only go DOWN; when a fix trips one, refactor, never raise a floor.
- **Identity-mutation floor 0.70** (measured 0.76) with the T7 stale
  backstop, and a **self-ratcheting nightly** mutation job.
- **Challenge corpus fully armed**: T4 target-parse gate (+
  `KNOWN_INVALID_TOKENS` denylist for sqlglot leniency), dedicated
  assertions for every `[fixed]` case
  (`test_challenge_assertions_<engine>.py`), a nightly live result-diff job
  (`challenge-live.yml`), and `scripts/challenge_stats.py` batch scoring.
- **Confidentiality tooling**: `scripts/private_leak_check.py` pre-push
  sweep (it caught a real leak on day one; extend its stopwords when
  generic-tech false positives appear).
The prevention plan (`audit/2026-07-24/08-prevention-plan.md`) documents why
each defect class had recurred and the rules that now hold; new findings get
a brief before a fix (`09-fix-briefs.md` is the template).

**The corpus validity campaigns are CLOSED (2026-07-17).** The pg-source and
mysql-source directions were swept wave-by-wave against the live engines
(waves 4–95 "corpus validity", then 103–239 "direction-residue", closed at a
user-declared floor of **133** syntax failures), then driven far below that
floor by the **zero-reduction campaign** (batches W1–W10, `docs/DONE.md` §40):
the six-direction residue went **133 (declared floor) → 127 (M3-final flip) →
16**, with **both Oracle directions at 100.0% validity** and the rest
99.8–99.9%; silent-gap discovery pg→pg **0** from 287. The full per-wave logs
live in `docs/DONE.md` (wave campaign section + §36 + §40); measured
percentages in `docs/STATUS.md`. **Do not resume waves on these corpora**
without a new corpus or a fidelity target — the remaining 16 is architectural
(schema-dependent ambiguity, adversarial pg_regress/sqlancer inputs sqlglot
cannot parse, composite-field access, correlated outer aggregates). Method preserved in the
development-workflow skill ("validity-wave cadence") for future corpora.
Architecture facts added by those waves worth knowing before touching the
code: the procedural lexer tokenizes PG dollar-quotes as STRING tokens
(normalized to single-quote form), `$n` positional params, `::` and `..`
each as ONE token; the parser aliases `$n` (and `ALIAS FOR $n`) to parameter
names at token level and splices string bodies through one canonical path;
`SOURCE_DIALECT`, `STRING_VARIABLES`, `IR_EMBEDDED`, `TEMP_TABLES` and the
degrade registries (DEGRADED_ROUTINES, PG_COMPOSITE_TYPES, …) are converter
ContextVars set per transpile; converter RawSQL fallbacks render in the
SOURCE dialect at top level (but generic inside embedded routine bodies —
that text is mid-transform, `IR_EMBEDDED` guards it); the IR models arrays
(`ArrayLiteral`), function relations in FROM (`TableRef.function`),
quantified subqueries (`SubqueryExpression.quantifier`) and hex literals;
and `Transformer.transform` runs statement-level whole-degrade gates for
constructs with no target equivalent (arrays, PG catalog internals, non-top
CTEs, per-target impossibilities — see `docs/03-unsupported.md` §7). In
transforms always use `dataclasses.replace`, never field-by-field rebuilds
(they silently drop fields).

**The architecture direction is set by `audit/2026-07-08/04-architecture-analysis.md`
(adopted) — and its M0–M4 milestones are ALL COMPLETE as of 2026-07-17**
(M3 final: IR-first expressions; scalar fragments route through the shared
IR pipeline by default, text rewriters are the warned fallback only;
`UNIQUE_NO_IR_FIRST` is the emergency kill-switch). The binding rules derived from it live
in `skills/SKILL-development-workflow.md` ("Architecture guardrails" and
"Detect the wrong path"); read both before touching `transpiler.py`,
`batch_splitter.py`, or the procedural engine. Headline: the failing 20% is
everything that *bypasses* the AST core — regex classification of batches,
raw-text transformation of embedded DML, ad-hoc comment handling, silent
fallbacks — and fixes must close those bypasses, not add cases to them.

Key standing lessons from 2026-07-02:

- **Test assertions must fail under an identity transpiler.** 72% of the
  integration suite passed when `transpile` returned its input unchanged.
  Every conversion test asserts the target idiom is present AND the source
  idiom is absent, and outputs are parsed in the target dialect. Details and
  the mutation snippet: `skills/SKILL-development-workflow.md` and
  `audit/2026-07-02/02-test-quality.md`.
- **No silent loss.** Anything not mapped 1:1 must populate
  `result.warnings`/`result.unsupported`; a carrier comment alone is not a
  signal. Never replace an executable statement with only a comment.
- **Mappings go in both directions and both pipelines** (standalone DML and
  procedural) — asymmetric one-off fixes caused real bugs
  (`GROUP_CONCAT`/`STRING_AGG`).
- **Docs claims require probe tests.** No ✅ in the compatibility matrix
  without a test proving it; README/CLI examples must be runnable as written.
- Known-broken constructs fixed-or-pending are listed in
  `audit/2026-07-02/01-functional-bugs.md`; check `docs/TODO.md` for their
  current state before assuming they work.

## Key Libraries

- `sqlglot` — Used as the primary SQL parsing foundation (supports all four
  dialects). We extend it with custom transforms for scripting constructs.
- `click` — CLI framework.
- `fastapi` — Optional REST API.
- `pytest` — Testing.
- `docker` — Deployment.

## Conventions

- All code and documentation in **English**.
- Commit messages: `feat:`, `fix:`, `test:`, `docs:`, `refactor:`.
- Branch naming: `feature/<name>`, `fix/<name>`.
- Every PR must have passing tests and maintain or increase coverage.
