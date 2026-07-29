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
