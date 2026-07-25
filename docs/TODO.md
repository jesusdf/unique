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

*The 2026-07-24 audit backlog (B1–B28 + T1–T7) is fully executed — see
[`docs/MILESTONES.md`](MILESTONES.md) and [`docs/DONE.md`](DONE.md) §44. What
follows are the NEW findings that campaign itself surfaced (per the
prevention-plan discipline, each gets a brief before a fix) plus scheduled
feature work.*

### P2 — new findings from the 2026-07-25 campaign

- [ ] **PL/SQL multi-word datetime types in DECLARE → silent garbage** (found
  by the TIMESTAMPLTZ worker, pre-existing, distinct subsystem): a PL/SQL
  `DECLARE v TIMESTAMP WITH LOCAL TIME ZONE` produces `v TIMESTAMP; WITH
  LOCAL; TIME ZONE;` with no warning — the procedural declaration parser's
  multi-word-type tokenization can't represent these types (`WITH TIME ZONE`
  already degrades honestly via parse error). Brief-first: teach the
  declaration parser the `TIMESTAMP WITH [LOCAL] TIME ZONE` compound (map per
  target like the DDL fix in `emit_ddl._local_tz_gap`), or gate the compound
  into a warned degrade.
- [x] **`TIMESTAMPLTZ` → PostgreSQL silent invalid type** (found by the C4
  assertion sweep): Oracle `TIMESTAMP WITH LOCAL TIME ZONE` → PG emits
  `TIMESTAMPLTZ` (not a PG type) with zero warnings — a no-silent-loss
  violation the T4 target-parse gate MISSES because sqlglot's lenient PG
  reader accepts the token (`ora-dttypes`, left unasserted in
  `test_challenge_assertions_oracle.py`). tsql/mysql degrade honestly.
  Brief-first: map to `TIMESTAMPTZ` + annotation (session-TZ semantics
  differ) or degrade warned; also consider a known-bad-token denylist for
  the parse gate's leniency holes. *(Done 2026-07-25: whole class fixed —
  `emit_ddl._local_tz_gap` maps PG→TIMESTAMPTZ (faithful, live-verified
  same-instant round-trip), tsql→DATETIMEOFFSET, mysql→TIMESTAMP, each
  warned+annotated; `tests/helpers/validity.py` gained the
  `KNOWN_INVALID_TOKENS` denylist closing the sqlglot-leniency hole;
  ora-dttypes un-suspected into a real assertion.)*
- [ ] **Oracle numeric `||` → PostgreSQL invalid** (found by the B17b live
  sweep): `SELECT 2||3` emits bare `2 || 3` — PG rejects
  `integer || integer` (Oracle implicitly casts and returns '23'). Needs
  operand casts (`::text`) or CONCAT() on PG when both operands are numeric.
  Excluded from the nightly FUNC_CASES until fixed (`ora-num-concat`).

### P3 — decisions and notes

- [ ] **Maintainer decision — `or_replace` on converted views** (predates the
  view-modifier work): `_convert_create_view` tests `is not None` but sqlglot
  stores `replace=False`, so EVERY converted view emits `CREATE OR REPLACE`
  (`OR ALTER` on tsql). Migration-friendly but a silent semantic change.
  Decide: document as an idempotency feature (03-unsupported note +
  annotation) or fix to `bool(...)` and re-bless the affected corpus/tests.
- [ ] **sqlglot hang guard**: sqlglot 30.x's parse-error highlighter hangs
  (infinite) on `WITH CASCADED CHECK OPTION` under the `oracle` reader at
  `ErrorLevel.RAISE`. Our pre-parse hook strips the clause first; if raw user
  input can ever reach a RAISE-parse on the oracle reader, guard it (timeout
  or pre-strip) — and consider reporting upstream.

### Scheduled feature work (briefs authored — `audit/2026-07-24/09-fix-briefs.md` §B28)

- [ ] **B28a** `#temp` tables inside converted procedures (PG statement-form
  temp DDL + script-wide rename; Oracle GTT hoisting; MySQL native).
- [ ] **B28b** top-level `BEGIN TRY/CATCH` routed to the procedural engine
  (classify as PROCEDURAL, reuse the in-routine lowering per target).

---

## Continuously tracked (not a discrete backlog)

- Challenge corpus (`tests/fixtures/challenge/`) remains the live intake for
  new RED findings — new batches follow the class/points rules in
  [`skills/SKILL-challenge-corpus.md`](../skills/SKILL-challenge-corpus.md)
  and are scored by `scripts/challenge_stats.py`.
- The first nightly runs at this HEAD will demand floor raises
  (`mutation.yml` self-ratcheting stale check) — apply them with the real
  full-run numbers.

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
