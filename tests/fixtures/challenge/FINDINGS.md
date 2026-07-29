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
| my-concat-null-col | func (5) | mysql→pg,tsql,oracle | `CONCAT(a, b)` verbatim | NULL when any arg NULL | live MySQL=`NULL`; PG/TSQL/ORA=`'1'`. No warning. NOTE: generalizes the [fixed] my-concat-null (constant fold) to a RUNTIME/column NULL the fold can't reach — same mechanism, distinct instance; PURPLE to judge dedupe. BLUE note: MySQL CONCAT ≙ PG/T-SQL string-concat operator (`||`/`+`, which propagate NULL), NOT their CONCAT; Oracle needs CASE WHEN any arg IS NULL. |
| my-groupconcat-distinct-numord | func (5) | mysql→postgresql | `STRING_AGG(DISTINCT CAST(x AS TEXT), '-' ORDER BY CAST(x AS TEXT) DESC)` orders lexically | numeric ORDER BY x DESC | live MySQL='10-2-1', Oracle='10-2-1', PG='2-10-1'. No warning. Exposes vacuous [fixed] my-groupconcat-distinct (values {1,1,2} don't distinguish text vs numeric order). BLUE note: for a numeric DISTINCT arg PG can't order numerically while DISTINCT-ing the text; dedupe in a derived table (SELECT DISTINCT x) then STRING_AGG(CAST(x AS TEXT), sep ORDER BY x) — the same derived-table approach T-SQL already uses. |
| pg-window-over-falsewarn | lying-warning (2) | ALL sources → ALL targets (any window fn) | warns "unread sqlglot arg 'over' on Window — construct may be dropped" | no warning (OVER faithfully emitted, result correct) | live PG=[(1,None),(2,2),(3,5)] == T-SQL == MySQL for SUM..OVER; Window.args['over']=='OVER' (sqlglot 30.14). Regression from the 30.11→30.14 bump. BLUE note: add `"Window": frozenset({"over"})` to ALLOWED_UNREAD in src/unique/core/converter/_unread_args.py — 'over' is the OVER keyword marker, carries no droppable construct (partition_by/order/spec are the real, already-read args). |
