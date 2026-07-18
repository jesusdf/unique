# Corpus live re-validation (RED compliance pass)

Every `[open]` case in `challenge_<engine>.sql` was re-transpiled to each other
engine and the output re-checked against a **live** target database, to prove the
ledger obeys the RED rules before BLUE picks it up.

## Result (latest pass)

| Outcome | Count | Meaning |
|---|---:|---|
| **REJECTED** (silent) | 1428 | live target rejects the output, **no warning** — confirmed silent defect (the corpus's reason to exist) |
| **ACCEPTS** (review) | 947 | live target accepts the output, no warning — a `func` wrong-result case, or a non-filed target that legitimately works |
| **CARRIER** (no warn) | 0 | no silent `Unhandled` carriers remain |
| **WARNED** | 124 | transpile emitted a warning — **all on non-filed targets** |
| checks total | 2499 | across all open cases × their other engines |
| harness errors | 0 | |

## Rule compliance

- **Warned degradation ≠ defect.** A case is filed only under the target(s) where
  it fails **silently**. The 124 warned combinations are every one on a target the
  case is *not* filed against (documented degradations elsewhere) — **0** warned
  results fall on a filed target. The ledger contains no warned degradations.
- **Live-validated.** Every filed target is either a live REJECT (silent invalid)
  or an executed func-diff (silent wrong result). Nothing is theoretical.

Reproduce with `scratchpad/verify_corpus.py` (RED-only; reads the committed
fixtures, transpiles, and validates against the Docker test stack). Finding-only:
touches no `src/`.
