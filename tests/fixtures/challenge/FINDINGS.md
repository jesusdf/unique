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
| pg-window-groups-frame | invalid (2) | pg→tsql,mysql | `... OVER (ORDER BY x ASC GROUPS BETWEEN 1 PRECEDING AND CURRENT ROW)` | ROWS/RANGE only on T-SQL/MySQL (or warn) | live: T-SQL 102 'Incorrect syntax near GROUPS'; MySQL 1235 'does not yet support GROUPS'. Oracle accepts GROUPS. No warning. Also affects [fixed] pg-groups2. BLUE note: degrade/emulate GROUPS frame off Oracle/PG; a GROUPS frame is a RANGE over distinct ORDER-BY groups — no direct ROWS equivalent, so warn + carrier if unemulated. |
| my-enum-order | consistency (4) | mysql→postgresql,tsql,oracle | ORDER BY a = alphabetical ('hi','lo','mid') | ENUM index order ('lo','mid','hi') | live: MySQL=('lo','mid','hi'); PG (VARCHAR)=('hi','lo','mid'). No warning. BLUE note: MySQL ENUM ordering is by declaration index — either warn that the ordering semantic is lost when degrading ENUM to VARCHAR+CHECK, or emit a mapping table / CASE-based sort key. At minimum this must not silently reorder. |
| my-to-days-year-zero | invalid (2) | mysql→pg,tsql,oracle | epoch base `DATE '0000-01-01'` (year 0, rejected) | valid day-number expression | live: MySQL=737790; PG DatetimeFieldOverflow; T-SQL err 241; Oracle ORA-01841. No warning. BLUE note: engines reject year 0000 — use a valid proleptic base and offset the known day count for the MySQL year-0 epoch (TO_DAYS('0001-01-01')=366), i.e. (d - DATE '0001-01-01') + 366, and verify the value matches MySQL's proleptic Gregorian. |

### Batch summary (RED 2026-07-30, PG/MySQL sources)
- 24 findings, 90 points, 6 classes. START commit cedf53a (worktree).
- By class: func 8 (40), invalid 8 (16), silent-drop 3 (12), consistency 2 (8), lying-warning 2 (4), composition 1 (5). func = 44%; concentration cap satisfied (no class > 50%), >= 3 classes.
- Cross-cutting: sqlglot 30.14 unread-args tripwire false/vague-fires on Window.over (all windows), Insert.default, Div.safe/typed — audit ALLOWED_UNREAD. Oracle date_trunc unit->format map wrong ('WEEK'/'QUARTER'). Temporal '-' operator (date-int, ts-ts) unconverted while '+' is handled.

<!-- RED batch END: committed-time >= 1h; over==True. 24 findings / 90 pts / 6 classes. -->

<!-- RED batch START 2026-07-30 (SQL Server + Oracle sources, one level up: clause enumeration + composition grids) -->

## RED batch 2026-07-30 (SQL Server + Oracle sources) — clause enumeration + composition grids

| id | class | src→targets | wrong output | expected / live evidence |
|----|-------|-------------|--------------|--------------------------|
| reda-ts-cast-int-trunc | func | tsql→pg,mysql,oracle | plain CAST, no compensation | T-SQL CAST(2.9 AS INT) truncates=2; targets round=3. Live tsql=2/pg=3/mysql=3/oracle=3. BLUE: wrap TRUNC() toward zero. |
| reda-ts-addmonths-lastday | func | tsql→oracle | DATEADD(MONTH)→ADD_MONTHS | ADD_MONTHS sticks to month-end; DATEADD does not. Live DATEADD(1mo,2020-02-29)=2020-03-29 vs ADD_MONTHS=2020-03-31. |
| reda-ts-output-into | invalid | tsql→pg | RETURNING INSERTED.a | OUTPUT...INTO breaks INSERTED-stripping; PG 'missing FROM-clause entry for "inserted"'. INTO redirect dropped. No warning. |
| reda-ora-keep-denserank | lying-warning | oracle→pg,tsql,mysql | MAX(x) OVER (ORDER BY y) | KEEP DENSE_RANK aggregate (1 row) mangled to windowed OVER (N rows). Live KEEP=[20] vs OVER=[10,20,20]. Only internal unread_args warning; no docs entry. |
| reda-ora-concat-null-cast | lying-warning | oracle→pg,tsql,mysql | ...|| CAST(NULL AS VARCHAR(10)) ||... | HOLE in [fixed] ora-concat-null: fix only drops literal NULL, not CAST(NULL)/NULL-typed operand. Live oracle='ab' vs pg=NULL. Only internal unread_args tripwire. |

Notes: Oracle-source PIVOT is the same converter mechanism as reda-ts-pivot (also silently dropped into tsql where PIVOT is supported) — BLUE fixes the class. Points: func 10, silent-drop 8, invalid 6, lying-warning 6 = 30; 4 classes.

### Additional findings (same batch, continued)

| id | class | src→targets | wrong output | expected / live evidence |
|----|-------|-------------|--------------|--------------------------|
| reda-ts-avg-int-trunc | func | tsql→pg,mysql,oracle | AVG(x) passed through | T-SQL integer AVG truncates=1; others=1.5. Live tsql=1, pg=1.5, mysql=1.5. |
| reda-ts-cte-merge | composition | tsql→mysql,oracle | CTE dropped/misplaced | WITH src..MERGE: MySQL upsert drops the CTE (live 1146 "Table 'src' doesn't exist"); Oracle keeps WITH before MERGE (live ORA-00928), no warning. Components green alone. |
| reda-ts-identity-insert | consistency | tsql→pg,oracle,mysql | SET IDENTITY_INSERT = t AS OFF | ON->comment+warn, OFF->mangled live SQL, invalid (PG syntax error near "AS"), no warning. Identity-override bracket incoherent. |

Batch running totals: func 25, invalid 10, silent-drop 8, lying-warning 6, composition 5, consistency 4 = 58 pts; 6 classes; func 43%.

### More findings (same batch)

| id | class | src→targets | wrong output | evidence |
|----|-------|-------------|--------------|----------|
| reda-ora-greatest-null | lying-warning | oracle→pg | GREATEST(1,NULL,3) passed through | Oracle/MySQL=NULL, PG ignores NULL=3. Only internal ignore_nulls tripwire. |
| reda-ts-like-escape | lying-warning | tsql→pg,oracle,mysql | whole SELECT commented out | LIKE..ESCAPE is standard, supported identically on all 3 (live-verified). Falsely warned 'no mapping'. |
| reda-ora-date-literal-subquery | invalid | oracle→pg,tsql,mysql | DATE literal->bare string in subquery | DATE '..' loses typing as a derived-table projection; outer date-minus-date -> text-text. Live PG 'text - text'. |

Batch totals: func 25, invalid 20, silent-drop 12, lying-warning 10, composition 5, consistency 4 = **76 pts**; **6 classes** (max class invalid 26%). All 25 open cases smoke-pass test_challenge.py (601 passed).

### Tail findings (same batch)

| id | class | src→targets | wrong output | evidence |
|----|-------|-------------|--------------|----------|
| reda-ts-isnull-trunc | lying-warning | tsql→pg,oracle,mysql | COALESCE(CAST(NULL AS VARCHAR(2)),'abcdef') | ISNULL truncates to 1st arg type='ab'; COALESCE='abcdef'. Only internal is_null tripwire. Live tsql='ab', pg='abcdef'. |
| reda-ts-datalength-nchar | func | tsql→pg,mysql | OCTET_LENGTH('abc') | DATALENGTH(N'abc')=6 (UTF-16); N dropped, OCTET_LENGTH=3. Hole in [fixed] ts-binary-length. No warning. |
| reda-ora-regexp-like | lying-warning | oracle→pg,mysql | whole statement commented out | REGEXP_LIKE falsely 'no mapping'; PG '~' and MySQL 'REGEXP' both support it (live-verified). Only T-SQL genuinely lacks it. |
| reda-ts-exec-swallow-next | consistency | tsql→pg,oracle,mysql | UPDATE folded into sp_rename carrier | a ';'-separated statement after a degraded EXEC is silently dropped (survives with GO). |

**FINAL batch totals: 31 findings, ~92 pts, 7 classes** — func 30, invalid 22, lying-warning 14, silent-drop 12, consistency 8, composition 5, crash 3. Max class func 33% (< 50% cap). All open cases smoke-pass test_challenge.py.

### Observations (not scored — dedup/borderline, for BLUE/PURPLE)

- **Falsely-unmapped-operator class** (BLUE: fix the class, not just the 2 scored cases): the "unmapped operator X; no <engine> mapping — statement preserved as a comment" path degrades the WHOLE statement for operators that ARE translatable. Scored: reda-ts-like-escape (Escape), reda-ora-regexp-like (RegexpLike). Additional instance NOT separately scored: T-SQL JSON_VALUE (sqlglot JSONExtractScalar) is degraded as "no mapping" though the Oracle-source direction maps JSON_VALUE fine (PG JSONB_PATH_QUERY_FIRST, MySQL JSON_VALUE, Oracle JSON_VALUE) — a T-SQL-source-only gap.
- **Oracle ROWNUM < n with ORDER BY** (tsql/pg/mysql): mapped to ORDER BY + LIMIT (order-then-limit) which changes Oracle's filter-before-order semantics; left unscored because Oracle's pre-order result is non-deterministic to demonstrate.
- **T-SQL LIKE '[A-C]%' character class** (pg/mysql/oracle): the [..] class is T-SQL-specific (others treat it literally): live 'Bob' LIKE '[A-C]%' = tsql 1 / pg 0 / mysql 0. Left unscored because a (mis-attributed, collation) warning IS emitted — borderline lying-warning; BLUE should still translate the character class or warn specifically.
- **Oracle PIVOT** (into tsql where PIVOT is supported) is silently dropped too — same converter mechanism as reda-ts-pivot.
