Why Unique emits what it emits when a construct has **no direct equivalent**
on a target engine, or when the faithful conversion is **non-obvious**
("creative"). Written for users outside the project: each entry explains the
source construct's semantics, the *engine-level* reason a direct mapping does
not exist, what Unique emits instead, and exactly what (if anything) diverges.

This is the narrative companion to two machine-checked sources of truth:

- [`docs/03-unsupported.md`](../03-unsupported.md) — the normative catalog of
  approved degradations. Every `[limit]` case in the challenge corpus must
  cite it (enforced by `tests/integration/test_challenge.py`).
- `tests/fixtures/challenge/challenge_*.sql` — the regression corpus. Every
  example in these pages is lifted from a corpus case (already live-verified
  on the four engines), never invented.
