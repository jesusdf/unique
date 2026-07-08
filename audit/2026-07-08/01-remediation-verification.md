# 01 — Remediation verification (2026-07-02 findings vs v0.22.3)

Every finding of the previous audit re-checked against v0.22.3. Probes were run
through the public `Transpiler.transpile` API with the original reproduction
inputs; ✅ means the originally reported defect no longer reproduces.

## Functional bugs (doc 01) — 14/14 fixed

| Finding | Status | Evidence (v0.22.3 output) |
|---|---|---|
| S1-1 quoted identifiers stripped | ✅ | `` `select` `` → `"select"` (PG), `[select]` → `` `select` `` (MySQL) — quoting translated both ways |
| S1-2 `(+)` → INNER JOIN without ON | ✅ | `WHERE a.id = b.id(+)` → `LEFT JOIN b ON a.id = b.id` |
| S1-3 MERGE→MySQL dropped silently | ✅ | Rewritten to `INSERT … ON DUPLICATE KEY UPDATE` + `lossy_conversion` warning; the non-rewritable form (`WHEN NOT MATCHED BY SOURCE THEN DELETE`) degrades to a carrier **with** warning + unsupported entry |
| S1-4 `DATEADD`→MySQL missing INTERVAL | ✅ | `DATE_ADD(CURRENT_TIMESTAMP, INTERVAL 7 DAY)` |
| S1-5 ROWNUM passthrough to PG | ✅ | `WHERE ROWNUM <= 5` → `LIMIT 5` |
| S1-6 `FROM dual` passthrough | ✅ | dropped for PG |
| S1-7 ILIKE passthrough to MySQL | ✅ | `LIKE` + collation warning |
| S1-8 GROUP_CONCAT passthrough to PG | ✅ | `STRING_AGG(name, ', ')` |
| S1-9 boolean literals reach T-SQL | ✅ | `= TRUE` → `= 1`; `BOOLEAN DEFAULT TRUE` → `BIT DEFAULT 1` |
| S1-10 `CURRENT_TIMESTAMP()` for PG | ✅ | emitted without parens |
| S1-11 Oracle constrained param types | ✅ | `V_PCT IN NUMBER` (unconstrained) |
| S2-1 STRING_AGG→MySQL separator | ✅ | `GROUP_CONCAT(name SEPARATOR ',')` |
| S2-2 THROW loses message | ✅ | Message preserved on all three targets; MySQL also warns about dropped severity/state. *Residue (minor):* PG gets `RAISE EXCEPTION '%', 'not found'` — the 50001 error number is dropped without a warning (`USING ERRCODE` would keep it) |
| S2-3 zero-row SELECT INTO divergence | ✅ | Oracle output wraps the `SELECT INTO` in `EXCEPTION WHEN NO_DATA_FOUND THEN NULL;` so the `IS NULL` guard stays reachable |

## Test quality (doc 02) — addressed, ratchet in place

- **Identity-mutation gate is CI-enforced** (`scripts/identity_mutation_check.py`,
  floor 0.33). Local re-run: **334/871 integration tests detect a no-op
  transpiler (38%)** vs 28% at v0.7.0.
- Per-file kill rates, then → now (killed/collected):
  `test_cross_dialect` 18% → **27%** (105/396); `test_function_translation`
  8% → **32%** (15/47); `test_real_world` 2% → **21%** (28/134);
  `test_procedural` 88% → 86% (121/141); `test_triggers` 86% → 84% (38/45);
  `test_operator_roundtrip` 55% → 55%; `test_comment_preservation` 20% → 20%.
- **Nightly mutation job** (`.github/workflows/mutation.yml`) tracks per-module
  scores and opens an issue on regression — beyond what the audit asked.
- **Recommendation 5 (live DML validation) is implemented and exceeded**:
  `test_corpus_live.py` executes transpiled output on real engines, and
  `test_corpus_results_live.py` compares *result sets* source-vs-target
  (differential testing) on every CI push; the FE harness (4×4 matrix) and
  live-syntax job are now **gating** (no `continue-on-error` on their steps).
- Shared target-dialect parse helper exists (`tests/helpers/validity.py`).
- **Still open:** ~73% of `test_cross_dialect.py` (291/396) and 80% of
  `test_comment_preservation.py` survive the identity mutant; the floor (0.33)
  sits well under the measured 38% — raise it as files are hardened.

## Code quality (doc 03)

| Item | Status |
|---|---|
| Split `converter.py` | ✅ now a package: `converter/{_base,convert,emit,harvest}.py` (largest file 1873 lines) |
| Deduplicate dialect knowledge | ✅ `core/mappings.py` (488 lines) consumed by both pipelines (`transformer.py`, `converter/*`, `procedural/transformer/base.py`) |
| detection.py weight-0 dead rules | ✅ re-weighted (comment cites the audit) |
| black/ruff `target-version` mismatch | ✅ aligned — project moved to Python 3.13 entirely (`requires-python >= 3.13`, CI 3.13, `py313`) |
| Module/function size | ❌ **worse**: `procedural/parser.py` 2639→2886, `procedural/transformer/base.py` 2425→2813, `transpiler.py` 712→**1713** lines. The split only happened for `converter.py` |
| Promote FE fingerprint to a product feature (`unique verify`) | ❌ not done (CLI gained `validate`, which is source-syntax checking — a different thing); still CI-only |
| CI duplicated log-capture shell blocks | ❌ still duplicated (syntax-live + FE steps) — cosmetic |

## API / security / ops (doc 04)

| Item | Status |
|---|---|
| A1 CPU-bound work in `async def` | ✅ all transpile/validate endpoints are plain `def` |
| A2 input size limits | ✅ `MAX_SQL_BYTES` (64 MB default, env-tunable) on `/transpile` body and file upload (bounded read + 413). **Gap:** `/api/v1/validate` and `/api/v1/detect` have **no** `max_length` — see new finding N6 |
| A3 `db_url` SSRF | ✅ strongest recommended fix implemented: server-side named DSNs (`UNIQUE_DSN_<NAME>`), raw `db_url` needs a second opt-in (`UNIQUE_ALLOW_RAW_DB_URL`), URLs never echoed |
| A4 error detail leakage | ✅ catch-all logs server-side, returns a generic 500 |
| A5 latin-1 silent fallback | ✅ BOM-aware (`utf-16`, `utf-8-sig`) with latin-1 as last resort. *Residue:* the encoding used is not reported in the response |
| A6 CORS / rate limiting / logging | ➖ unchanged (acceptable per the original audit; the "reverse proxy expected" note exists only implicitly in doc 07) |
| Docker base image digest pin | ❌ still `python:3.13-slim` by tag; non-sqlglot deps still float |
| CI: fail when engines silently skip | ❌ still possible — the SQL Server/Oracle wait steps are `continue-on-error` and live tests `pytest.skip` on connect failure, so a broken driver quietly shrinks coverage |
| PAT hygiene | (outside the repo — not verifiable here) |

## Documentation (doc 05)

| Item | Status |
|---|---|
| D1 README/doc-07 CLI flags (`-s/-t/-f`) | ✅ all examples use `--from/--to` |
| D2 matrix overstatements (ROWNUM, MERGE→MySQL, boolean) | ✅ all three behaviors now implemented (probed) |
| D3 "nothing silently lost" principle | ✅ enforced for the doc-01 cases; carrier↔warning reconciliation exists. (New violations found in this audit — see doc 02, N1/N2/N3) |
| D4 STATUS scoping / `latest` image note / audit linkage | ➖ mixed: STATUS is current (v0.22.3) and skills point to `audit/`; the README still shows `jesusdf/unique:latest` without the "published only on tags" note |
| New drift found | ❌ `docs/STATUS.md` says the guard round-trip is "exercised … by the functional-equivalence harness (Scenario C)"; `tests/functional_equivalence/coverage-matrix.md` explicitly says it is **not** in the harness (by design). ❌ `skills/SKILL-project-overview.md` still says **Python 3.12**; the project is 3.13-only |
