**The wiki our users consult when they don't understand why something
translated the way it did.** A user typically works with one or two engines;
these pages are organized so that view comes first (the by-engine indexes).

The contract (maintainer, 2026-08-01):

- **Scope is the whole application**: every conversion Unique performs that
  is **not a direct equivalence** belongs here — a rewrite, hoist, guard
  synthesis, decomposition, compensation, or creative alternative — whether
  it ends faithful or divergent. The scope is NOT limited to any audit,
  sweep, or test set performed at some point in time; those are verification
  tools, the contract is total coverage.
- Each entry explains the source construct's semantics, the *engine-level*
  reason a direct mapping does not exist, what Unique emits instead, and
  exactly what (if anything) diverges — with the transpiler treated as a
  **black box** (no internals, no project history).
- **Coverage means a rationale article exists.** An entry in
  `docs/03-unsupported.md` counts as coverage only for a *genuine approved
  degradation* (a warned limit); a faithful creative conversion documented
  only there is misfiled — it gets an article here, and 03-unsupported
  cross-links it.

This is the narrative companion to two machine-checked sources of truth:

- [`docs/03-unsupported.md`](../03-unsupported.md) — the normative catalog of
  approved degradations. Every `[limit]` case in the challenge corpus must
  cite it (enforced by `tests/integration/test_challenge.py`).
- `tests/fixtures/challenge/challenge_*.sql` — the regression corpus. Every
  example in these pages is lifted from a corpus case (already live-verified
  on the four engines), never invented.
