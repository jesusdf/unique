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

<!-- RED batch START 2026-07-30 (SQL Server + Oracle sources, one level up: clause enumeration + composition grids) -->

## RED batch 2026-07-30 (SQL Server + Oracle sources) — clause enumeration + composition grids

| id | class | src→targets | wrong output | expected / live evidence |
|----|-------|-------------|--------------|--------------------------|
| reda-ts-cast-int-trunc | func | tsql→pg,mysql,oracle | plain CAST, no compensation | T-SQL CAST(2.9 AS INT) truncates=2; targets round=3. Live tsql=2/pg=3/mysql=3/oracle=3. BLUE: wrap TRUNC() toward zero. |
| reda-ts-addmonths-lastday | func | tsql→oracle | DATEADD(MONTH)→ADD_MONTHS | ADD_MONTHS sticks to month-end; DATEADD does not. Live DATEADD(1mo,2020-02-29)=2020-03-29 vs ADD_MONTHS=2020-03-31. |
| reda-ts-fk-on-update | lying-warning | tsql→oracle | ON UPDATE CASCADE dropped, no warning | Oracle has no ON UPDATE action; degrade shipped silently. BLUE: warn+carrier+docs. |
| reda-ora-forupdate-of-col | invalid | oracle→pg,mysql | FOR UPDATE OF x (column) leaks | Oracle OF=column, PG/MySQL OF=table. Live PG 'relation "x" not found', MySQL 3568. No warning (SKIP LOCKED path). Also latent in ora-forupdate-wait [limit]. |
| reda-ts-output-into | invalid | tsql→pg | RETURNING INSERTED.a | OUTPUT...INTO breaks INSERTED-stripping; PG 'missing FROM-clause entry for "inserted"'. INTO redirect dropped. No warning. |
| reda-ts-delete-join | invalid | tsql→pg,oracle,mysql | DELETE FROM t WHERE s.flag=1 | multi-table DELETE join dropped; references unjoined s. PG 'missing FROM-clause entry for "s"'. Only internal unread_args tripwire. |
| reda-ora-keep-denserank | lying-warning | oracle→pg,tsql,mysql | MAX(x) OVER (ORDER BY y) | KEEP DENSE_RANK aggregate (1 row) mangled to windowed OVER (N rows). Live KEEP=[20] vs OVER=[10,20,20]. Only internal unread_args warning; no docs entry. |
| reda-ts-pivot | silent-drop | tsql→oracle,pg,mysql | SELECT * FROM (subq) src | whole PIVOT dropped, no warning. Live PIVOT=1 row(A=3,B=5) vs 3 raw rows. Oracle supports PIVOT natively. |
| reda-ts-for-json | silent-drop | tsql→pg,oracle,mysql | SELECT a,b FROM t | FOR JSON PATH dropped, no warning (FOR XML warns). Live JSON scalar '[{...}]' vs 2x2 rows. |
| reda-ora-concat-null-cast | lying-warning | oracle→pg,tsql,mysql | ...|| CAST(NULL AS VARCHAR(10)) ||... | HOLE in [fixed] ora-concat-null: fix only drops literal NULL, not CAST(NULL)/NULL-typed operand. Live oracle='ab' vs pg=NULL. Only internal unread_args tripwire. |

Notes: Oracle-source PIVOT is the same converter mechanism as reda-ts-pivot (also silently dropped into tsql where PIVOT is supported) — BLUE fixes the class. Points: func 10, silent-drop 8, invalid 6, lying-warning 6 = 30; 4 classes.

### Additional findings (same batch, continued)

| id | class | src→targets | wrong output | expected / live evidence |
|----|-------|-------------|--------------|--------------------------|
| reda-ts-substring-zero-start | func | tsql→mysql,oracle | SUBSTRING passed through | start<1 semantics differ. Live SUBSTRING('hello',0,3): tsql/pg='he', mysql='', oracle='hel'. |
| reda-ts-avg-int-trunc | func | tsql→pg,mysql,oracle | AVG(x) passed through | T-SQL integer AVG truncates=1; others=1.5. Live tsql=1, pg=1.5, mysql=1.5. |
| reda-ts-cte-merge | composition | tsql→mysql,oracle | CTE dropped/misplaced | WITH src..MERGE: MySQL upsert drops the CTE (live 1146 "Table 'src' doesn't exist"); Oracle keeps WITH before MERGE (live ORA-00928), no warning. Components green alone. |
| reda-ora-rowvalue-in | invalid | oracle→tsql | (a,b) IN ((1,2),(3,4)) passed through | T-SQL has no row-constructor IN. Live T-SQL error 4145. No warning. |
| reda-ts-alter-column-oracle | invalid | tsql→oracle | ALTER COLUMN a SET DATA TYPE NUMBER | Oracle needs MODIFY. Live ORA-01735. No warning. (MySQL-source MODIFY path is handled, T-SQL path isn't.) |
| reda-ts-identity-insert | consistency | tsql→pg,oracle,mysql | SET IDENTITY_INSERT = t AS OFF | ON->comment+warn, OFF->mangled live SQL, invalid (PG syntax error near "AS"), no warning. Identity-override bracket incoherent. |
| reda-ts-date-plus-int | func | tsql→mysql,pg | datetime + 1 passed through | T-SQL adds a day. Live: mysql=20200101000001 (numeric, wrong), pg=error timestamp+int, tsql/oracle=2020-01-02. |

Batch running totals: func 25, invalid 10, silent-drop 8, lying-warning 6, composition 5, consistency 4 = 58 pts; 6 classes; func 43%.

### More findings (same batch)

| id | class | src→targets | wrong output | evidence |
|----|-------|-------------|--------------|----------|
| reda-ora-greatest-null | lying-warning | oracle→pg | GREATEST(1,NULL,3) passed through | Oracle/MySQL=NULL, PG ignores NULL=3. Only internal ignore_nulls tripwire. |
| reda-ts-delete-top | silent-drop | tsql→mysql,oracle,pg | TOP(n) dropped from DELETE | deletes ALL rows not n. MySQL DELETE LIMIT supported. Only internal tables tripwire. |
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
