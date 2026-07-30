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
| pg-window-groups-frame | invalid (2) | pg→tsql,mysql | `... OVER (ORDER BY x ASC GROUPS BETWEEN 1 PRECEDING AND CURRENT ROW)` | ROWS/RANGE only on T-SQL/MySQL (or warn) | live: T-SQL 102 'Incorrect syntax near GROUPS'; MySQL 1235 'does not yet support GROUPS'. Oracle accepts GROUPS. No warning. Also affects [fixed] pg-groups2. BLUE note: degrade/emulate GROUPS frame off Oracle/PG; a GROUPS frame is a RANGE over distinct ORDER-BY groups — no direct ROWS equivalent, so warn + carrier if unemulated. |
| pg-multifield-interval-arith | invalid (2) | pg→tsql,mysql,oracle | `... + INTERVAL '1 year 2 months 3 days'` verbatim | converted per-engine date math (or warn) | live: PG=2021-03-04; T-SQL err 156, MySQL err 1064, Oracle ORA-30089. No warning. BLUE note: decompose a multi-field PG interval into per-unit adds (DATEADD chained on T-SQL; `+ INTERVAL n MONTH + INTERVAL n DAY` on MySQL; Oracle NUMTOYMINTERVAL/NUMTODSINTERVAL or chained ADD_MONTHS + day add) or degrade with a warning. Single-unit path already works; only the multi-field literal is unhandled. |
| pg-boolagg-filter | composition (5) | pg→tsql | `MAX(CAST(CASE WHEN b = 1 THEN a > 5 END AS INT))` (raw boolean as CASE value) | boolean wrapped 1/0 as bool_or does alone | live: PG=True; T-SQL err 102 'Incorrect syntax near >'. bool_or alone valid on T-SQL (=1), FILTER alone valid — only the combination breaks. (MySQL allows boolean value; Oracle 23ai has native boolean; T-SQL is the broken target.) No warning. BLUE note: the FILTER→CASE rewrite must compose with the boolean-agg's 1/0 wrapping — wrap the boolean arg inside the FILTER CASE's THEN, not leave it raw. |
| pg-round-bare-half-literal | invalid (2) | pg→tsql | `ROUND(0.5, 0)` | 1 (no overflow) | live: PG ROUND(0.5)=1; T-SQL err 8115 'Arithmetic overflow ... to numeric'. No warning. Root cause: T-SQL infers 0.5 as numeric(1,1), no room for the rounded integer digit. BLUE note: for a single-arg PG ROUND into T-SQL, cast the argument to a wider numeric/float first, e.g. ROUND(CAST(0.5 AS DECIMAL(38,6)), 0) or ROUND(CAST(0.5 AS FLOAT), 0). |
| pg-substring-neg-from-for | func (5) | pg→mysql,oracle | `SUBSTRING/SUBSTR('abcde', -2, 2)` verbatim | '' (positions < 1 dropped) | live: PG=''; MySQL='de'; Oracle='de'; T-SQL='' (matches PG). No warning. BLUE note: PG 3-arg substring with start<1 keeps chars from position 1 up to (start+len-1); when start+len-1 < 1 the result is ''. The 2-arg fix (rewrite start->1) is insufficient here — must also clamp the length to (start+len-1) and yield '' when non-positive. |
| my-timestampdiff-mon-pgora | func (5) | mysql→postgresql,oracle | `(year*12+month)` boundary diff = 2 | complete-month count = 1 | live: MySQL=1, T-SQL=1 (fixed), PG=2, Oracle=2. No warning. The [fixed] my-timestampdiff-mon guards T-SQL only; the exact existing-case source (2020-01-15..2020-03-10) also gives 2 on PG/Oracle. BLUE note: port the T-SQL 'drop the incomplete final period' adjustment (subtract 1 when start+diff months > end) to the PG and Oracle rewrites — mappings must go to all targets. |
| pg-insert-default-values-falsewarn | lying-warning (2) | pg→mysql | warns "unread sqlglot arg 'default' on Insert — construct may be dropped" | no warning (correctly translated) | live: PG DEFAULT VALUES row=(7,3); MySQL `() VALUES ()` row=(7,3). BLUE note: mark Insert.args['default'] as READ in the MySQL insert path (do NOT globally allowlist Insert.default — Oracle genuinely degrades it and must keep its real warning). |
| my-enum-order | consistency (4) | mysql→postgresql,tsql,oracle | ORDER BY a = alphabetical ('hi','lo','mid') | ENUM index order ('lo','mid','hi') | live: MySQL=('lo','mid','hi'); PG (VARCHAR)=('hi','lo','mid'). No warning. BLUE note: MySQL ENUM ordering is by declaration index — either warn that the ordering semantic is lost when degrading ENUM to VARCHAR+CHECK, or emit a mapping table / CASE-based sort key. At minimum this must not silently reorder. |
| pg-repeat-negative | func (5) | pg→tsql,oracle | REPLICATE/RPAD emulation returns NULL | '' (empty string) | live: PG=''; MySQL=''; T-SQL(REPLICATE('ab',-1))=NULL; Oracle(RPAD('ab',-2,'ab'))=NULL. No warning. BLUE note: clamp negative/zero repeat counts to '' on T-SQL/Oracle, e.g. REPLICATE('ab', CASE WHEN -1 < 0 THEN 0 ELSE -1 END) or wrap COALESCE(...,''). |
| my-to-days-year-zero | invalid (2) | mysql→pg,tsql,oracle | epoch base `DATE '0000-01-01'` (year 0, rejected) | valid day-number expression | live: MySQL=737790; PG DatetimeFieldOverflow; T-SQL err 241; Oracle ORA-01841. No warning. BLUE note: engines reject year 0000 — use a valid proleptic base and offset the known day count for the MySQL year-0 epoch (TO_DAYS('0001-01-01')=366), i.e. (d - DATE '0001-01-01') + 366, and verify the value matches MySQL's proleptic Gregorian. |
| pg-bool-to-int-cast | invalid (2) | pg→tsql,oracle | `CAST(a > 1 AS INT)` (predicate as CAST operand) | 1 | live: PG=1; T-SQL err 156; Oracle ORA-02000. No warning. BLUE note: a boolean expression cast to a numeric must become CASE WHEN <pred> THEN 1 ELSE 0 END (optionally CAST to the target type) on T-SQL/Oracle; MySQL treats the predicate as 1/0 natively. Same root as pg-boolagg-filter. |
| pg-date-trunc-week | func (5) | pg→tsql (wrong date), pg→oracle (invalid) | T-SQL DATETRUNC(week)=Sunday 2020-06-14; Oracle TRUNC(d,'WEEK') ORA-01898 | Monday 2020-06-15 (ISO) | live: PG=2020-06-15; T-SQL=2020-06-14; Oracle errors (ORA-01898); TRUNC(d,'IW')=2020-06-15 is correct. No warning. BLUE note: PG week is ISO/Monday — on T-SQL compute Monday explicitly (DATEADD(DAY, -(DATEPART(WEEKDAY, d)+@@DATEFIRST-2)%7, d) or DATETRUNC(iso_week,...)); on Oracle use TRUNC(d,'IW'), not 'WEEK'. |
| (pg-date-trunc-week, related) | — | pg→oracle | `TRUNC(d, 'QUARTER')` (ORA-01821) | `TRUNC(d, 'Q')` | Same Oracle date_trunc format-code bug for the 'quarter' unit: PG date_trunc('quarter') emits TRUNC(d,'QUARTER') which Oracle rejects (ORA-01821); the valid code is 'Q'. ('month'/'year'/'day' map fine.) BLUE: fix the whole date_trunc→Oracle unit→format map ('week'->'IW','quarter'->'Q'), not just one unit. |
| pg-date-minus-integer | func (5) | mysql (garbage value), tsql (invalid) | MySQL `CAST(d AS DATE) - 7` = 20200294; T-SQL err 206 | 2020-02-23 (date minus 7 days) | live: PG=2020-02-23; MySQL=20200294 (date coerced to int!); T-SQL error 206. No warning. `date + N` already maps to DATEADD/DATE_ADD; `date - N` is not converted. BLUE note: map `date - <int>` to DATEADD(DAY, -N, d) (T-SQL) / DATE_SUB(d, INTERVAL N DAY) (MySQL) / d - N (Oracle/PG) — mirror the existing '+' handling for the '-' operator. |
| (pg-date-minus-integer, related) | — | mysql (garbage), tsql (invalid) | timestamp - timestamp emitted raw | interval/duration (PG '2:00:00') | Same temporal-`-`-unconverted mechanism: TIMESTAMP - TIMESTAMP → T-SQL err 8117 ('datetime2 invalid for subtract'), MySQL returns 20000 (datetimes coerced to numbers); Oracle correct ('2:00:00'). BLUE: also handle timestamp/date difference → DATEDIFF (T-SQL) / TIMESTAMPDIFF (MySQL), alongside the date±int fix. |

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
| reda-ora-forupdate-of-col | invalid | oracle→pg,mysql | FOR UPDATE OF x (column) leaks | Oracle OF=column, PG/MySQL OF=table. Live PG 'relation "x" not found', MySQL 3568. No warning (SKIP LOCKED path). Also latent in ora-forupdate-wait [limit]. |
| reda-ts-output-into | invalid | tsql→pg | RETURNING INSERTED.a | OUTPUT...INTO breaks INSERTED-stripping; PG 'missing FROM-clause entry for "inserted"'. INTO redirect dropped. No warning. |
| reda-ts-delete-join | invalid | tsql→pg,oracle,mysql | DELETE FROM t WHERE s.flag=1 | multi-table DELETE join dropped; references unjoined s. PG 'missing FROM-clause entry for "s"'. Only internal unread_args tripwire. |
| reda-ora-keep-denserank | lying-warning | oracle→pg,tsql,mysql | MAX(x) OVER (ORDER BY y) | KEEP DENSE_RANK aggregate (1 row) mangled to windowed OVER (N rows). Live KEEP=[20] vs OVER=[10,20,20]. Only internal unread_args warning; no docs entry. |
| reda-ora-concat-null-cast | lying-warning | oracle→pg,tsql,mysql | ...|| CAST(NULL AS VARCHAR(10)) ||... | HOLE in [fixed] ora-concat-null: fix only drops literal NULL, not CAST(NULL)/NULL-typed operand. Live oracle='ab' vs pg=NULL. Only internal unread_args tripwire. |

Notes: Oracle-source PIVOT is the same converter mechanism as reda-ts-pivot (also silently dropped into tsql where PIVOT is supported) — BLUE fixes the class. Points: func 10, silent-drop 8, invalid 6, lying-warning 6 = 30; 4 classes.

### Additional findings (same batch, continued)

| id | class | src→targets | wrong output | expected / live evidence |
|----|-------|-------------|--------------|--------------------------|
| reda-ts-substring-zero-start | func | tsql→mysql,oracle | SUBSTRING passed through | start<1 semantics differ. Live SUBSTRING('hello',0,3): tsql/pg='he', mysql='', oracle='hel'. |
| reda-ts-avg-int-trunc | func | tsql→pg,mysql,oracle | AVG(x) passed through | T-SQL integer AVG truncates=1; others=1.5. Live tsql=1, pg=1.5, mysql=1.5. |
| reda-ts-cte-merge | composition | tsql→mysql,oracle | CTE dropped/misplaced | WITH src..MERGE: MySQL upsert drops the CTE (live 1146 "Table 'src' doesn't exist"); Oracle keeps WITH before MERGE (live ORA-00928), no warning. Components green alone. |
| reda-ts-alter-column-oracle | invalid | tsql→oracle | ALTER COLUMN a SET DATA TYPE NUMBER | Oracle needs MODIFY. Live ORA-01735. No warning. (MySQL-source MODIFY path is handled, T-SQL path isn't.) |
| reda-ts-identity-insert | consistency | tsql→pg,oracle,mysql | SET IDENTITY_INSERT = t AS OFF | ON->comment+warn, OFF->mangled live SQL, invalid (PG syntax error near "AS"), no warning. Identity-override bracket incoherent. |
| reda-ts-date-plus-int | func | tsql→mysql,pg | datetime + 1 passed through | T-SQL adds a day. Live: mysql=20200101000001 (numeric, wrong), pg=error timestamp+int, tsql/oracle=2020-01-02. |

Batch running totals: func 25, invalid 10, silent-drop 8, lying-warning 6, composition 5, consistency 4 = 58 pts; 6 classes; func 43%.

### More findings (same batch)

| id | class | src→targets | wrong output | evidence |
|----|-------|-------------|--------------|----------|
| reda-ora-greatest-null | lying-warning | oracle→pg | GREATEST(1,NULL,3) passed through | Oracle/MySQL=NULL, PG ignores NULL=3. Only internal ignore_nulls tripwire. |
| reda-ts-like-escape | lying-warning | tsql→pg,oracle,mysql | whole SELECT commented out | LIKE..ESCAPE is standard, supported identically on all 3 (live-verified). Falsely warned 'no mapping'. |
| reda-ts-datepart-weekday | invalid | tsql→pg,oracle,mysql | EXTRACT(DAYOFWEEK FROM d) | no engine has DAYOFWEEK extract unit. Live PG/MySQL/Oracle all error. No warning. |
| reda-ora-date-literal-subquery | invalid | oracle→pg,tsql,mysql | DATE literal->bare string in subquery | DATE '..' loses typing as a derived-table projection; outer date-minus-date -> text-text. Live PG 'text - text'. |
| reda-ts-sequence-no-cycle | invalid | tsql→oracle | NO MAXVALUE NO CYCLE verbatim | Oracle needs NOMAXVALUE/NOCYCLE (one word). Live ORA-03049. No warning. |
| reda-ts-index-fillfactor-mysql | invalid | tsql→mysql | ON t ((a) WITH (FILLFACTOR=80)) | WITH folded into key list. Live MySQL 1064. No warning (Oracle path warns). |
| reda-ora-interval-literal-arith | invalid | oracle→tsql,mysql | INTERVAL '1-6' YEAR TO MONTH verbatim | T-SQL has no INTERVAL literal (err 102); MySQL uses YEAR_MONTH not YEAR TO MONTH (1064). No warning. |

Batch totals: func 25, invalid 20, silent-drop 12, lying-warning 10, composition 5, consistency 4 = **76 pts**; **6 classes** (max class invalid 26%). All 25 open cases smoke-pass test_challenge.py (601 passed).

### Tail findings (same batch)

| id | class | src→targets | wrong output | evidence |
|----|-------|-------------|--------------|----------|
| reda-ts-isnull-trunc | lying-warning | tsql→pg,oracle,mysql | COALESCE(CAST(NULL AS VARCHAR(2)),'abcdef') | ISNULL truncates to 1st arg type='ab'; COALESCE='abcdef'. Only internal is_null tripwire. Live tsql='ab', pg='abcdef'. |
| reda-ts-datalength-nchar | func | tsql→pg,mysql | OCTET_LENGTH('abc') | DATALENGTH(N'abc')=6 (UTF-16); N dropped, OCTET_LENGTH=3. Hole in [fixed] ts-binary-length. No warning. |
| reda-ts-datediff-quarter | crash | tsql→all | KeyError 'QUARTER' -> /* TRANSPILATION ERROR */ | DATEDIFF(QUARTER/WEEK) raises in _emit_date_diff (emit_functions.py ~235/254), caught into an invalid carrier. DATEADD(QUARTER) works. |
| reda-ts-convert-numeric-style | invalid | tsql→pg,mysql,oracle | TO_TIMESTAMP('26','MON DD YYYY…') | CONVERT(INT,'26',0)=26 but the numeric target type is ignored and it maps to a date parse. Live PG error, MySQL NULL. No warning. |
| reda-ora-regexp-like | lying-warning | oracle→pg,mysql | whole statement commented out | REGEXP_LIKE falsely 'no mapping'; PG '~' and MySQL 'REGEXP' both support it (live-verified). Only T-SQL genuinely lacks it. |
| reda-ts-exec-swallow-next | consistency | tsql→pg,oracle,mysql | UPDATE folded into sp_rename carrier | a ';'-separated statement after a degraded EXEC is silently dropped (survives with GO). |

**FINAL batch totals: 31 findings, ~92 pts, 7 classes** — func 30, invalid 22, lying-warning 14, silent-drop 12, consistency 8, composition 5, crash 3. Max class func 33% (< 50% cap). All open cases smoke-pass test_challenge.py.

### Observations (not scored — dedup/borderline, for BLUE/PURPLE)

- **Falsely-unmapped-operator class** (BLUE: fix the class, not just the 2 scored cases): the "unmapped operator X; no <engine> mapping — statement preserved as a comment" path degrades the WHOLE statement for operators that ARE translatable. Scored: reda-ts-like-escape (Escape), reda-ora-regexp-like (RegexpLike). Additional instance NOT separately scored: T-SQL JSON_VALUE (sqlglot JSONExtractScalar) is degraded as "no mapping" though the Oracle-source direction maps JSON_VALUE fine (PG JSONB_PATH_QUERY_FIRST, MySQL JSON_VALUE, Oracle JSON_VALUE) — a T-SQL-source-only gap.
- **Oracle ROWNUM < n with ORDER BY** (tsql/pg/mysql): mapped to ORDER BY + LIMIT (order-then-limit) which changes Oracle's filter-before-order semantics; left unscored because Oracle's pre-order result is non-deterministic to demonstrate.
- **T-SQL LIKE '[A-C]%' character class** (pg/mysql/oracle): the [..] class is T-SQL-specific (others treat it literally): live 'Bob' LIKE '[A-C]%' = tsql 1 / pg 0 / mysql 0. Left unscored because a (mis-attributed, collation) warning IS emitted — borderline lying-warning; BLUE should still translate the character class or warn specifically.
- **Oracle PIVOT** (into tsql where PIVOT is supported) is silently dropped too — same converter mechanism as reda-ts-pivot.
