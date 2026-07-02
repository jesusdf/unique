# 03 — Code quality & architecture

## What is in good shape

- **Static gates all green**: `ruff` (E,F,I,N,W,UP,B,SIM), `black`, `isort`,
  and `mypy --strict` over `src/` pass with zero findings. Type annotations
  are thorough; docstrings are consistent and often explain *why*, not *what*.
- **No TODO/FIXME/HACK markers** left in `src/` — intent is either implemented
  or documented in `docs/`.
- Clean separation of interfaces (CLI / API / library) from the core.
- The carrier-comment convention (`/* UNIQUE: ... */`) is a genuinely good
  idea for lossy conversions — it just needs to be wired to `warnings`
  consistently (see doc 01).
- Pinning `sqlglot==30.11.0` with a written rationale
  (`docs/sqlglot-dependency.md`) is the right call for a correctness-critical
  dependency.

## Hotspots: module and function size

| Module | Lines | Longest functions |
|---|---:|---|
| `core/procedural/parser.py` | 2639 | `_parse_embedded_dml` (125), `_parse_plsql_select_or_dml` (110), `_try_parse_tsql_assignment_select` (103) |
| `core/procedural/transformer/base.py` | 2425 | `_rewrite_string_concat` (118), `_transform_data_type` (83) |
| `core/converter.py` | 2253 | `_emit_create_table` (117), `_convert_create_table` (105), `convert_expression` (93) |
| `core/procedural/emitter/base.py` | 1208 | — |
| `core/procedural/lexer.py` | — | `_tokenize_one` (198) |
| `core/transpiler.py` | 712 | `transpile` (129), `_transpile_dml` (97) |

None of this is *wrong*, but four modules >1200 lines with 100–200-line
functions is where maintainability erodes first, and it directly conflicts
with the project's stated Clean Code goal. Suggested cuts along existing
seams:

- `converter.py` → `converter/expressions.py`, `converter/ddl.py`,
  `converter/dml.py` (the section comments already mark these boundaries).
- `procedural/parser.py` → per-family modules (tsql / plsql / plpgsql
  routines) behind the existing dispatch.
- `lexer._tokenize_one` → a table of `(predicate, handler)` pairs.

## Duplicated dialect knowledge (the structural risk)

The same facts are encoded in **at least three places**:

- `core/transformer.py` — function-name map for the DML pipeline
  (`GETDATE → CURRENT_TIMESTAMP`, …).
- `core/converter.py` — emit-side per-dialect literals
  (`return "GETDATE()" / "SYSDATE"` around line 1956).
- `core/procedural/transformer/base.py` — its own map
  (`{"tsql": "GETDATE()", "oracle": "SYSDATE", ...}` around line 1931).

This is the mechanism behind the asymmetries in doc 01: `STRING_AGG → MySQL`
is mapped while `GROUP_CONCAT → PostgreSQL` is not; `ISNULL` is handled in one
pipeline and boolean literals in neither. **Recommendation:** a single
declarative mapping layer (functions, types, literals, pseudo-tables like
`dual`) consumed by both pipelines. One table, one test file that iterates it
in both directions, asymmetry becomes impossible by construction.

## Plugin architecture: thinner than advertised

The spec and README promise a modular per-engine plugin system, and the entry
points exist (`[project.entry-points."unique.dialects"]`). But the dialect
plugin classes are 13–16 statements each, while the real dialect knowledge
lives in core as string comparisons (`if target == "oracle": ...`) spread
across converter/transformer/emitters. Adding a fifth engine today means
editing every core module, not writing a plugin.

Not urgent, but if the plugin goal is real, the direction is: dialect classes
own their mapping tables and emitter hooks; core orchestrates. The
per-dialect procedural emitters/transformers already follow this shape — the
DML pipeline doesn't.

## Smaller findings

- `core/detection.py`: weight-0 rules (`TEXT`, `BOOLEAN` under postgresql)
  can never affect a score — dead entries.
- `pyproject.toml`: `requires-python = ">=3.12"` but black/ruff
  `target-version = "py311"` — harmless today, but it stops the linters from
  suggesting 3.12-only idioms; align to `py312`.
- `tests/helpers/functional_equivalence.py` fingerprint is a good invariant,
  but it lives under `tests/` while being described as a product guarantee in
  the README. Consider promoting it into `src/unique/` and exposing it (e.g.
  `unique verify`), so users get the guard, not only CI.
- `errors.py` is at 81% coverage with some exception branches never exercised
  — cheap wins for targeted unit tests.
- Two batches of near-identical shell logic in `.github/workflows/ci.yaml`
  (capture pytest output → summary → `::error::`) could be a composite action
  or script to keep the workflow readable.
