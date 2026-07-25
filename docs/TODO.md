# Unique — Pending Work

This document tracks **outstanding** work only, ordered by priority. Completed
backlog sections move to [`docs/MILESTONES.md`](MILESTONES.md) (closing
summaries) with the detailed why/how of each fix archived in
[`docs/DONE.md`](DONE.md); `docs/STATUS.md` summarizes the project state at a
higher level.

Last reviewed: 2026-07-25.

## Legend

- **P1** — high impact, appears frequently in real schemas
- **P2** — medium impact, common but not blocking
- **P3** — lower impact / niche

---

## Discrete backlog

*The 2026-07-24 audit backlog, the findings it surfaced, and the B28 features
are ALL closed — see [`docs/MILESTONES.md`](MILESTONES.md) and
[`docs/DONE.md`](DONE.md) §44–§45. Only the two maintainer decisions below
remain.*

### P3 — maintainer decisions

- [ ] **`or_replace` on converted views** (found 2026-07-25, predates the
  view-modifier work): `_convert_create_view` tests `is not None` but sqlglot
  stores `replace=False`, so EVERY converted view emits `CREATE OR REPLACE`
  (`OR ALTER` on tsql). Migration-friendly but a silent semantic change (a
  plain CREATE errors on an existing view; OR REPLACE overwrites it). Decide:
  document as an idempotency feature (03-unsupported note + annotation) or
  fix to `bool(...)` and re-bless the affected corpus/tests.
- [ ] **sqlglot hang guard**: sqlglot 30.x's parse-error highlighter hangs
  (infinite) on `WITH CASCADED CHECK OPTION` under the `oracle` reader at
  `ErrorLevel.RAISE`. Our pre-parse hook strips the clause first; if raw user
  input can ever reach a RAISE-parse on the oracle reader, guard it (timeout
  or pre-strip) — and consider reporting upstream.

---

## Continuously tracked (not a discrete backlog)

- Challenge corpus (`tests/fixtures/challenge/`) remains the live intake for
  new RED findings — new batches follow the class/points rules in
  [`skills/SKILL-challenge-corpus.md`](../skills/SKILL-challenge-corpus.md)
  and are scored by `scripts/challenge_stats.py`.
- The first nightly runs at this HEAD will demand mutation-floor raises
  (`mutation.yml` self-ratcheting stale check) — apply them with the real
  full-run numbers.
- Oracle-source Tier-1 promotion still wants a second real corpus
  (`docs/STATUS.md` direction tiers).

---

## Known limitations to keep documented (not bugs)

These have no faithful cross-engine equivalent and are intentionally emitted as
comments/warnings (see `docs/03-unsupported.md`):

- SQL Server system procedures (`sp_addextendedproperty`, `sp_rename`, …).
- SQL*Plus session directives (`SET FEEDBACK`, etc.) and `rem`/`prompt`
  (preserved as comments).
- `%TYPE`/`%ROWTYPE` without `--db-url` (emitted as a carrier type with the
  original preserved in a `/* UNIQUE: … */` comment, plus a warning). The
  round-trip **restores the original** on a transpilation back to a supporting
  engine — verified for `%TYPE` via the procedural path and for physical index
  clauses via the DML path (`%TYPE` is PL/SQL-only, so it never appears in a
  DML/DDL statement).
