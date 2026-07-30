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
| my-enum-order | consistency (4) | mysql→postgresql,tsql,oracle | ORDER BY a = alphabetical ('hi','lo','mid') | ENUM index order ('lo','mid','hi') | live: MySQL=('lo','mid','hi'); PG (VARCHAR)=('hi','lo','mid'). No warning. BLUE note: MySQL ENUM ordering is by declaration index — either warn that the ordering semantic is lost when degrading ENUM to VARCHAR+CHECK, or emit a mapping table / CASE-based sort key. At minimum this must not silently reorder.  **MAINTAINER DECISION 2026-07-30: convert to a feature brief (docs/TODO.md) — the faithful ENUM-ordinal sort-key mapping is a cross-statement feature; do not warn-patch. Case stays [open] until the brief is executed.** |

### Batch summary (RED 2026-07-30, PG/MySQL sources)
- 24 findings, 90 points, 6 classes. START commit cedf53a (worktree).
- By class: func 8 (40), invalid 8 (16), silent-drop 3 (12), consistency 2 (8), lying-warning 2 (4), composition 1 (5). func = 44%; concentration cap satisfied (no class > 50%), >= 3 classes.
- Cross-cutting: sqlglot 30.14 unread-args tripwire false/vague-fires on Window.over (all windows), Insert.default, Div.safe/typed — audit ALLOWED_UNREAD. Oracle date_trunc unit->format map wrong ('WEEK'/'QUARTER'). Temporal '-' operator (date-int, ts-ts) unconverted while '+' is handled.

<!-- RED batch END: committed-time >= 1h; over==True. 24 findings / 90 pts / 6 classes. -->

<!-- RED batch START 2026-07-30 (SQL Server + Oracle sources, one level up: clause enumeration + composition grids) -->

## RED batch 2026-07-30 (SQL Server + Oracle sources) — clause enumeration + composition grids

| id | class | src→targets | wrong output | expected / live evidence |
|----|-------|-------------|--------------|--------------------------|

Notes: Oracle-source PIVOT is the same converter mechanism as reda-ts-pivot (also silently dropped into tsql where PIVOT is supported) — BLUE fixes the class. Points: func 10, silent-drop 8, invalid 6, lying-warning 6 = 30; 4 classes.

### Additional findings (same batch, continued)

| id | class | src→targets | wrong output | expected / live evidence |
|----|-------|-------------|--------------|--------------------------|

Batch running totals: func 25, invalid 10, silent-drop 8, lying-warning 6, composition 5, consistency 4 = 58 pts; 6 classes; func 43%.

### More findings (same batch)

| id | class | src→targets | wrong output | evidence |
|----|-------|-------------|--------------|----------|
| reda-ora-date-literal-subquery | invalid | oracle→pg,tsql,mysql | DATE literal->bare string in subquery | DATE '..' loses typing as a derived-table projection; outer date-minus-date -> text-text. Live PG 'text - text'.  **UPDATE 2026-07-30: PG and MySQL legs FIXED (DATE-literal typing preserved on projections); only the T-SQL leg (date-type propagation through derived-table columns) remains — routed to feature brief B30 in docs/TODO.md.** |

Batch totals: func 25, invalid 20, silent-drop 12, lying-warning 10, composition 5, consistency 4 = **76 pts**; **6 classes** (max class invalid 26%). All 25 open cases smoke-pass test_challenge.py (601 passed).

### Tail findings (same batch)

| id | class | src→targets | wrong output | evidence |
|----|-------|-------------|--------------|----------|

**FINAL batch totals: 31 findings, ~92 pts, 7 classes** — func 30, invalid 22, lying-warning 14, silent-drop 12, consistency 8, composition 5, crash 3. Max class func 33% (< 50% cap). All open cases smoke-pass test_challenge.py.

### Observations (not scored — dedup/borderline, for BLUE/PURPLE)

- **Falsely-unmapped-operator class** (BLUE: fix the class, not just the 2 scored cases): the "unmapped operator X; no <engine> mapping — statement preserved as a comment" path degrades the WHOLE statement for operators that ARE translatable. Scored: reda-ts-like-escape (Escape), reda-ora-regexp-like (RegexpLike). Additional instance NOT separately scored: T-SQL JSON_VALUE (sqlglot JSONExtractScalar) is degraded as "no mapping" though the Oracle-source direction maps JSON_VALUE fine (PG JSONB_PATH_QUERY_FIRST, MySQL JSON_VALUE, Oracle JSON_VALUE) — a T-SQL-source-only gap.
- **Oracle ROWNUM < n with ORDER BY** (tsql/pg/mysql): mapped to ORDER BY + LIMIT (order-then-limit) which changes Oracle's filter-before-order semantics; left unscored because Oracle's pre-order result is non-deterministic to demonstrate.
- **T-SQL LIKE '[A-C]%' character class** (pg/mysql/oracle): the [..] class is T-SQL-specific (others treat it literally): live 'Bob' LIKE '[A-C]%' = tsql 1 / pg 0 / mysql 0. Left unscored because a (mis-attributed, collation) warning IS emitted — borderline lying-warning; BLUE should still translate the character class or warn specifically.
- **Oracle PIVOT** (into tsql where PIVOT is supported) is silently dropped too — same converter mechanism as reda-ts-pivot.

<!-- RED batch START round 2 2026-07-30 (SEEDED: date-unit space, window frames, comment-adjacency, bit literals, RED-A observations, procedural depth) -->

## RED batch round 2 2026-07-30 (seeded)

| id | class | src→targets | wrong output | expected / live evidence | BLUE note |
|----|-------|-------------|--------------|--------------------------|-----------|
| red2-ts-datediff-weekday-unit | invalid (2) | tsql→mysql,oracle | DATEDIFF(2020-03-01,'2020-01-01',WEEKDAY) 3-arg passthrough, dates unquoted | live tsql=valid; MySQL 1582 param count; Oracle ORA-00904 WEEKDAY. No warning (datetime-literal variant IS gated) | Reject/degrade unmapped DATEDIFF units; quote date args |
| red2-pg-extract-isoyear-unit | invalid (2) | postgresql→tsql,mysql,oracle | EXTRACT(ISOYEAR..) passed through verbatim | live PG valid; tsql 155 not-a-datepart; MySQL 1064; Oracle ORA-00907. No warning | Compute ISOYEAR per target or degrade-with-warning; same for ISODOW/JULIAN/MILLENNIUM/DECADE/CENTURY |
| red2-pg-window-exclude-current | func (5) | postgresql→tsql,mysql,oracle | EXCLUDE CURRENT ROW/GROUP/TIES dropped from OVER() | live t(a)=(1,1,2,3): PG=6,6,5,4; Oracle transpiled=7,7,7,7. No warning | Warn/degrade or rewrite EXCLUDE |
| red2-my-bitstring-numeric-pg | invalid (2) | mysql→postgresql | b'101'+0 shipped verbatim to PG (BIT literal) | live MySQL=5; PG "operator does not exist: bit + integer". No warning (tsql/ora gated) | Fold bit-string used numerically to int like the hex path |
| red2-ts-json-value-false-unmap | lying-warning (2) | tsql→mysql,oracle,postgresql | JSON_VALUE degraded to comment "no <engine> mapping" | MySQL/Oracle support JSON_VALUE natively (live='1'); Oracle-source direction maps it. False no-mapping warning | Map JSONExtractScalar per target |
| red2-ts-like-charclass | lying-warning (2) | tsql→postgresql,mysql,oracle | LIKE '[A-C]%' passed through; collation warning mis-attributes the loss | live tsql=1, pg/mysql/oracle=0; warning blames collation not the [A-C] char-class | Translate char-class or warn on pattern-syntax loss |
| red2-ts-datepart-week-iso | func (5) | tsql→postgresql,mysql,oracle | DATEPART(WEEK) (non-ISO) mapped to ISO week fns | live 2021-01-01: tsql=1, pg/mysql/oracle=53. No warning | Map DATEPART(WEEK) to non-ISO week per target; reserve ISO fns for ISO_WEEK |
| red2-my-intdiv-false-unmap | lying-warning (2) | mysql→postgresql,tsql,oracle | DIV dropped to comment "no mapping" | live 7 DIV 2=3; PG/tsql 7/2=3, Oracle TRUNC(7/2)=3. T-SQL-source maps / to DIV. False no-mapping | Map IntDiv to integer / (PG/tsql), TRUNC (Oracle) |
| red2-pg-fk-ondelete-setdefault-oracle | invalid (2) | postgresql→oracle | FK ON DELETE SET DEFAULT passed through | live Oracle ORA-03001 unimplemented feature. No warning (MySQL tolerates) | Oracle lacks SET DEFAULT action — degrade+warn |
| red2-ts-exec-named-param-mysql | invalid (2) | tsql→mysql | CALL proc(v_id = 1, v_flag = 0) named-param | live MySQL 1054 Unknown column 'v_id'; positional CALL works. No warning | MySQL CALL is positional — reorder named args or degrade+warn |
| red2-ts-raiserror-format-arg-drop | silent-drop (4) | tsql→postgresql,oracle | RAISERROR %d substitution arg 42 dropped, message left literal | T-SQL raises "value is 42 today"; PG/Oracle emit literal 'value is %d today', arg gone, NO warning (MySQL leg warns) | Translate %d/%s to PG RAISE format args / Oracle concat; at least warn |
| red2-my-dateadd-compound-interval | invalid (2) | mysql→postgresql,tsql,oracle | DATE_ADD compound INTERVAL '1:30' HOUR_MINUTE -> bogus DATEADD(HOUR_MINUTE,'1:30',..) | live MySQL=09:30:00; PG/tsql/oracle all reject. No warning (EXTRACT compound units ARE handled) | Expand compound interval into component units per target |
| red2-ts-set-swallow-next | consistency (4) | tsql→postgresql,mysql,oracle | SET NOCOUNT ON; SELECT 1 -> both commented; SELECT 1 dropped | SELECT 1 transpiles alone; GO-sep keeps it; ;-sep loses it. Warning only names the SET option. Neighbor of fixed reda-ts-exec-swallow-next | Split ';'-separated stmts before degrading the SET |
| red2-my-cast-unsigned-leniency | lying-warning (2) | mysql→postgresql,tsql | CAST('12x' AS UNSIGNED)=12 -> CAST('12x' AS NUMERIC) errors | live MySQL=12; PG "invalid input syntax numeric 12x", tsql 8114. Warning only mentions "unsigned wraparound", not that output errors | Extract leading numeric prefix, or warn about the parse error |
| red2-ora-trunc-day-weekstart | func (5) | oracle→postgresql,tsql,mysql | TRUNC(d,'DAY') [week start] mapped to day-truncation | live 2021-06-15: Oracle TRUNC('DAY')=2021-06-13, PG DATE_TRUNC('day')=2021-06-15. No warning. ('DD' IS day-trunc, correct) | Map 'DAY'/'DY'/'D' to week-start; reserve day-trunc for 'DD' |
| red2-ora-trunc-format-unmapped | invalid (2) | oracle→postgresql,tsql,mysql | TRUNC(d,'W'/'IW') -> DATE_TRUNC(W,d) bare id; TRUNC('HH'/'MI') -> MySQL DATE_TRUNC | live PG "column w does not exist"; MySQL "FUNCTION DATE_TRUNC does not exist". No warning | Map 'W'/'IW' + MySQL time-unit legs or degrade+warn |
| red2-ora-round-date-fmt | invalid (2) | oracle→postgresql,tsql,mysql | ROUND(date,'DAY') treated as numeric ROUND(CAST(date AS NUMERIC),'DAY') | live Oracle ROUND('DAY')=2021-06-13; PG "cannot cast type date to numeric". No warning | Recognize ROUND(date,fmt) as date rounding like TRUNC |
| red2-pg-nextval-false-unmap | lying-warning (2) | postgresql→tsql,oracle,mysql | nextval('seq') degraded "no tsql form" | Oracle seq.NEXTVAL->tsql "NEXT VALUE FOR seq" proves mapping exists; PG-source direction falsely claims no form. Source valid on PG | Map PG NEXTVAL/CURRVAL symmetric with reverse directions |
| red2-my-invisible-column-drop | silent-drop (4) | mysql→oracle (pg,tsql under-warn) | INVISIBLE column attribute dropped, no warning | Oracle supports INVISIBLE (live valid); MySQL SELECT * excludes b (returns (1) for (1,2)). Oracle target would return both | Preserve INVISIBLE on Oracle; warn on PG/tsql |
| red2-ts-at-identity-passthrough | invalid (2) | tsql→postgresql,oracle | @@IDENTITY passed through verbatim | live PG "column identity does not exist", Oracle ORA-00936. No warning. SCOPE_IDENTITY() IS mapped | Map @@IDENTITY like SCOPE_IDENTITY or degrade+warn |
