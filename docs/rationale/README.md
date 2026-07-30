# Transpilation rationale

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

## Pages

| Page | Covers |
|---|---|
| [datetime.md](datetime.md) | date/time arithmetic, truncation, unit maps, month-end semantics, epoch rebasing |
| [strings-collation.md](strings-collation.md) | concatenation & NULL, LIKE/ESCAPE, character classes, collation/order, Oracle `''` ≡ NULL, byte vs char lengths |
| [aggregates-windows.md](aggregates-windows.md) | window frames, ordered aggregates, string aggregation, DISTINCT ON, boolean aggregates |
| [dml.md](dml.md) | PIVOT/UNPIVOT, MERGE/upsert lowering, multi-table DELETE, row caps, row-value comparisons |
| [ddl.md](ddl.md) | identity/SERIAL, temp tables, FK actions, sequences, storage options |
| [procedural.md](procedural.md) | cursors, error handling, dynamic SQL, system procedures, session directives |

## Entry format (keep it — the pages are grep-able by construct)

```markdown
### <construct> (<source engine>) → <target(s)>

**Source semantics.** What the construct does, in one or two sentences.
**Why there is no direct mapping.** The target-engine-level reason (missing
value type, different clamping rule, parser limitation…), not "unsupported".
**What Unique emits.** The output shape, with a real input/output example
copied from the corpus case.
**Divergence & warning.** `faithful` (same result set), or the exact
divergence and the warning text the user will see.
**References.** Corpus case id(s) · 03-unsupported § (if a limit).
```

Rules for contributors (human or agent): every claim must be traceable to a
corpus case, an emitter docstring, or a `docs/03-unsupported.md` section —
cite it; examples are copied from corpus cases verbatim (they are
live-verified; an invented example is a liability); `faithful` may only be
claimed where a corpus assertion or the nightly live result-diff proves it.
