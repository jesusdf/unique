# Audit — 2026-07-08

Follow-up audit of the `unique` repository at `v0.22.3` (previous audit:
[`audit/2026-07-02/`](../2026-07-02/) at v0.7.0, 226 commits ago). Two goals:
verify the remediation of every 2026-07-02 finding, and re-audit the current
state for new problems.

## Documents

| File | Contents |
|------|----------|
| [01-remediation-verification.md](01-remediation-verification.md) | Item-by-item verification of every 2026-07-02 finding (functional, tests, code, API, docs) against v0.22.3 |
| [02-new-findings.md](02-new-findings.md) | New defects found in this audit, with reproductions, plus improvement opportunities |
| [03-private-fixture-sweep.md](03-private-fixture-sweep.md) | Live-engine validation of the (confidential, anonymized here) real-world scripts across the matrix: ~25 defect classes, 29–44% invalid output in the Oracle→X direction |

## Executive summary

**The 2026-07-02 remediation is real and near-complete.** All **14 functional
bugs (S1-1…S1-11, S2-1…S2-3) are fixed** — each was re-probed against v0.22.3
and produces correct, warning-bearing output. The structural recommendations
landed too: an **identity-mutation gate** now runs in CI (kill rate 28% → 38%,
floor 0.33), a **nightly mutation job** tracks per-module scores,
**live corpus + differential-result validation** runs against real engines on
every CI push, the monolithic `converter.py` became a package, **shared mapping
tables** (`core/mappings.py`) feed both pipelines, and the API grew size caps,
named server-side DSNs (raw `db_url` double-gated), generic 500s, and BOM-aware
decoding. Docs/CLI drift from doc 05 is fixed. The suite grew 1185 → 1774 tests.

**However, this audit found two new S1 defects, both in recently added
features** (details and reproductions in
[02-new-findings.md](02-new-findings.md)):

1. **`IF [NOT] EXISTS (<real-data query>) <single statement>` silently loses
   its guard** on every target. The batch classifier only protects the
   `BEGIN … END` form of a non-catalog guard; the (very common) unbracketed
   form is routed to the guard-drop path, so a re-runnable
   `IF NOT EXISTS (SELECT 1 FROM cfg WHERE k='x') INSERT …` becomes an
   **unconditional INSERT with zero warnings** — the exact "silent semantic
   change" class the project's core invariant forbids.
2. **PostgreSQL → T-SQL temp tables are renamed inconsistently**:
   `SELECT * INTO TEMPORARY tmp; SELECT … FROM tmp; DROP TABLE tmp` emits
   `INTO #tmp` but leaves `FROM tmp` / `DROP TABLE tmp` untouched — the output
   creates one table and reads another, silently.

Also notable: **source-syntax validation has easy false negatives**
(`banana banana`, `CREATE TALBE t (id INT)` both validate clean, and the first
then transpiles to the garbage `banana AS banana;` with no warning), and
**`docs/STATUS.md` claims the FE harness exercises the guard round-trip while
`coverage-matrix.md` explicitly documents that it does not**.

**Addendum (same day): the private-fixture live sweep**
([03-private-fixture-sweep.md](03-private-fixture-sweep.md)) transpiled the
three real-world confidential scripts across the matrix and executed the
outputs on the real engines. It confirmed the guard family above at scale and
surfaced **~25 defect classes**, headlined by: guards with a leading comment
(or a `BEGIN…END` wrapper) commented out wholesale on every target; the
Oracle→X direction emitting **29% invalid batches on SQL Server and 43.6%
invalid statements on PostgreSQL** for a real 13 MB dump (`EXEC AS`, PL/SQL
`DECLARE` skeletons, `FROM DUAL` in INSERT-guards ~6,000×, untranslated
`ROWNUM`/`RENAME COLUMN`/`IF UPDATING`/`TRUNC`); **silent expression
corruption** (`MAX(NVL(x,0)) + 1` losing arguments on T-SQL and turning `+`
into `||` on PostgreSQL); mid-body `DECLARE` never hoisted (breaks whole
routines on all three targets); and MySQL `CALL` emitted with unsupported
named arguments.

**Recommended priorities**

1. **P1 — fix the unbracketed real-data guard drop** (S1; one-line-ish fix in
   `batch_splitter._classify`: require a catalog reference for the guard path
   regardless of `BEGIN`).
2. **P1 — make the PG→T-SQL temp-table rename script-wide** (rename every
   reference, or don't rename at all).
3. **P2 — extend the garbage detector in `validate_source`** to alias-parsed
   bare tokens and unknown `Command` heads, and make the transpiler warn when
   a batch survives only as an expression fragment.
4. **P2 — reconcile STATUS.md with the coverage matrix**, drop the
   false-positive "FOR loop has no direct T-SQL equivalent" warning on
   successful guard round-trips, and update the project-overview skill
   (still says Python 3.12; the project is 3.13).
5. **P3 — carry-overs** still open from 2026-07-02, all minor: CI should fail
   when fewer engines than expected were actually exercised; Docker base image
   digest-pinning; module growth (`procedural/parser.py` 2639→2886,
   `transformer/base.py` 2425→2813, `transpiler.py` 712→1713 lines); ~73% of
   `test_cross_dialect.py` still survives the identity mutant — keep raising
   the floor as assertions harden.

## Method

- Venv rebuilt from `pyproject.toml`; full gate re-run locally: black, isort,
  ruff, mypy, and the full suite (1774 tests) — **all green**.
- Every 2026-07-02 S-finding re-probed through the public
  `Transpiler.transpile` API with the original reproduction inputs.
- Identity-mutation run re-executed locally (per-file kill breakdown in doc 01).
- Round-trip probing (A→B→A′) of the features added since v0.7.0: idempotent
  guards, CREATE SCHEMA, ALTER COLUMN, custom `sp_*` routing, splitter comment
  handling, temp tables, source validation.
- Source review of `batch_splitter.py`, `validation.py`, `api/app.py`, CI
  workflows, and the docs/skills for drift.
