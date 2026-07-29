# Challenge findings ledger (RED)

Open findings live here while a RED batch is active; BLUE removes each row as
it closes the case. **The ledger is currently EMPTY — the 2026-07 campaign is
fully resolved: 0 `[open]` / 694 `[fixed]` / 168 `[limit]` of 862 cases**
(v0.30.0). Per-case status lives in the `challenge_<engine>.sql` script
headers; the campaign summary is in `docs/MILESTONES.md` and the detailed
resolution log in `docs/DONE.md` §41/§43. Historical finding rows (the RED-era
detail, priority classes and totals) are preserved in git history — see the
file's log prior to 2026-07-24.

Scope reminder for the next RED batch (full rules in
`skills/SKILL-challenge-corpus.md`): **SILENT defects only** — a warned
degrade is a documented, acceptable outcome, not a finding. Kinds: **invalid**
(live target rejects the output), **func** (runs clean, different result),
**silent-drop** (a supported clause vanished, no warning), **semantic**
(meaning changed). Every finding needs live validation of the source on its
own engine first.

<!-- RED appends new findings below this line. -->

## RED batch 2026-07-30 (PG/MySQL sources)

| id | class | engines | wrong output | expected | evidence |
|----|-------|---------|--------------|----------|----------|
| pg-distinct-on | func (5) | pg→mysql,tsql,oracle | `SELECT DISTINCT a, b ...` (all distinct pairs) | one row per `a` (first by ORDER BY) | live PG=`[(1,10),(2,5)]`; live MySQL transpiled=`[(1,10),(1,20),(2,5),(2,7)]`. No warning. BLUE note: DISTINCT ON needs a per-group pick — ROW_NUMBER() OVER (PARTITION BY key ORDER BY <order>) = 1, not SELECT DISTINCT. Requires the ORDER BY prefix = DISTINCT ON keys. No portable form on engines lacking QUALIFY; if unsound, degrade with warning. |
