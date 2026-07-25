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

- [x] **PL/SQL multi-word datetime types in DECLARE → silent garbage** (found
  by the TIMESTAMPLTZ worker, pre-existing, distinct subsystem): a PL/SQL
  `DECLARE v TIMESTAMP WITH LOCAL TIME ZONE` produces `v TIMESTAMP; WITH
  LOCAL; TIME ZONE;` with no warning — the procedural declaration parser's
  multi-word-type tokenization can't represent these types (`WITH TIME ZONE`
  already degrades honestly via parse error). Brief-first: teach the
  declaration parser the `TIMESTAMP WITH [LOCAL] TIME ZONE` compound (map per
  target like the DDL fix in `emit_ddl._local_tz_gap`), or gate the compound
  into a warned degrade. *(Done 2026-07-25: `_fold_compound_type` parses the
  whole family — `TIMESTAMP [WITH [LOCAL]|WITHOUT] TIME ZONE` incl. precision
  forms, `INTERVAL <f>[(n)] TO <f>[(n)]` — as ONE type; per-target mapping
  reuses the `_local_tz_gap` decisions via table dispatch; also fixed the
  precision-position bug (`TIMESTAMPTZ(6)` → `TIMESTAMP(6) WITH TIME ZONE`).
  Live: Oracle source VALID, all four targets validate, PG executes,
  round-trips exact. `test_datetime_tz_interval_declares.py`, docs §3.19.)*
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
- [x] **Oracle numeric `||` → PostgreSQL invalid** (found by the B17b live
  sweep) — done 2026-07-25: when BOTH `||` operands are known-numeric the PG
  emission wraps each in `CAST(… AS TEXT)` (string/unknown operands
  untouched), in BOTH pipelines (`emit_expr._emit_binary` CONCAT +
  `procedural/transformer/_expr._pg_numeric_concat_cast`); tsql/mysql were
  already correct (CONCAT() folds). Live: `SELECT 2||3` returns '23' on all
  three targets; `ora-num-concat` re-included in the nightly FUNC_CASES and
  passing. Ratchets kept flat by refactor, not floor raises.

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

- [x] **B28a** `#temp` tables inside converted procedures — done 2026-07-25:
  `_rewrite_temp_select_into` lowers `SELECT … INTO #t` per target (PG/MySQL
  `DROP IF EXISTS` + `CREATE TEMPORARY TABLE … AS`; Oracle hoisted GTT reusing
  the `@table`-variable machinery + script-wide rename); functions keep the
  warned degrade. Live two-call isolation verified on all three targets
  ([30,30], no leakage). Also fixed the pre-existing MySQL cursor-handler
  placement bug the composition exposed (handler hoisted into the declaration
  section). `test_temp_table_in_procedure.py`.
- [x] **B28b** top-level `BEGIN TRY/CATCH` routed to the procedural engine —
  done 2026-07-25: sanctioned recognizer in `batch_splitter.classify_batch` +
  parser routing to an anonymous block; ALL lowering reused (PG `DO $$ …
  EXCEPTION`, Oracle `BEGIN … EXCEPTION`, MySQL documented warned carrier).
  Live raise-and-recover matches the SQL Server reference exactly on PG and
  Oracle (log ['after','caught'], 0 rows persisted). Subtransaction caveat
  documented (03-unsupported §3.5). `TestTopLevelTryCatch`.

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
