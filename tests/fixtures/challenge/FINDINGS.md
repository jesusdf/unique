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

### Observations (round 2, not scored — warned/borderline/repeat, for BLUE/PURPLE)

- **Asymmetric false-unmap class breadth (reinforces scored JSON_VALUE/DIV/nextval).** Additional mappable-but-degraded builtins found: MySQL DAYOFWEEK degraded "unmapped function DAY_OF_WEEK" though the reverse DATEPART(dw)->MySQL emits DAYOFWEEK; PG `->>` (JSONExtractScalar) hits the same path as red2-ts-json-value-false-unmap. Many other source builtins degrade with an HONEST "no <engine> form" warning where a mapping COULD exist (CHOOSE->CASE, STR->TO_CHAR, OCT->CONV) — BLUE enhancement candidates, not defects (warned honestly).
- **Oracle/T-SQL IGNORE NULLS window functions.** LAG/FIRST_VALUE ... IGNORE NULLS is supported by BOTH Oracle and T-SQL 2022 (live-verified) but the converter cannot emit it: Oracle-source -> tsql/pg degrades to a comment via the honesty gate (warning is a raw internal "Required keyword: 'expressions' missing for Aliases" leak). Warned, so not scored, but BLUE should pass IGNORE NULLS through for Oracle<->T-SQL and warn cleanly for PG/MySQL.
- **T-SQL OUTPUT ... INTO @table inside a proc (under-warned).** DELETE ... OUTPUT deleted.id INTO @log -> PG emits `DELETE ... RETURNING id` to nowhere and never populates @log, so a following `SELECT ... FROM @log` returns empty (wrong result); only the generic "review the statement" warning fires on PG (Oracle DOES warn specifically "OUTPUT deleted.id dropped"). Borderline func; PG leg under-warned.
- **MySQL XOR** degraded "unmapped operator Xor" — expressible as boolean inequality but non-trivial; left as a legit degrade.
- **REPLACE INTO (MySQL)** -> "Unhandled expression type: Command" (parse-model gap; honest warning). BLUE could rewrite as DELETE+INSERT / MERGE.
- **PG `~*` (case-insensitive regex, RegexpILike)** degraded "unmapped operator RegexpILike; no <engine> mapping" for ALL targets — but Oracle REGEXP_LIKE(x, pat, 'i') and MySQL 8 REGEXP_LIKE(x, pat, 'i') are direct equivalents (case-sensitive `~` IS mapped). Asymmetric false-unmap (reinforces the class). T-SQL genuinely has no regex.
- **MySQL RLIKE case-insensitivity** -> PG `~` (case-SENSITIVE) / Oracle REGEXP_LIKE without 'i': 'ABC' RLIKE '^a' is TRUE on MySQL (default CI collation) but the mapped `~` is case-sensitive -> different result; only a generic collation warning is emitted (regex case-sensitivity, not collation, is the real cause). Borderline lying-warning (neighbor of red2-ts-like-charclass).
- **Oracle MERGE ... WHEN MATCHED THEN UPDATE SET ... DELETE WHERE ...** is parse-blocked by sqlglot (valid Oracle syntax; the embedded DELETE clause fails to parse) and degrades to a comment with a raw "Invalid expression / Unexpected token" warning. Parse-blocked (sqlglot limitation), warned.

### Batch summary (RED round 2, seeded) — provisional
- START commit d4d572d. 15 scored findings, 72 points, 6 classes.
- By class: invalid 22 (11 cases), func 20 (4), lying-warning 12 (6), silent-drop 8 (2), composition 5 (1), consistency 4 (1). Max class invalid 30.6% (< 50% cap); 6 classes (>= 3).
- Seeds that PROVED OUT: (1) date-unit space — invalid (DATEDIFF WEEKDAY, EXTRACT ISOYEAR, DATE_ADD compound interval, TRUNC/ROUND date-format models) + func (DATEPART WEEK ISO, Oracle TRUNC 'DAY'=week-start); (2) window frames — EXCLUDE CURRENT ROW/GROUP/TIES silently dropped (func); (4) MySQL bit-string literal -> PG invalid; (5) RED-A observations — JSON_VALUE + LIKE char-class lying-warnings confirmed (PIVOT Oracle-source now FIXED, not a finding). NEW rich veins found: asymmetric false-unmap (DIV/nextval/matview/JSON — mappable but degraded, reverse direction proves it) and procedural-emitter statement gaps (SAVEPOINT AS, SET TRANSACTION as-assignment, GOTO garbled).
- Seeds that came up EMPTY/thin: (2) named windows, RANGE offsets, nested windows — all handled; (3) comment-adjacency — the fixed class's neighbors HOLD (block-comment semicolons, DECLARE/MERGE comments all clean); (6) procedural composition mostly warned/handled EXCEPT the SAVEPOINT-AS composition. Field is THIN: last ~8 probe batches (aggregates, type/cast matrix, string fns, concat/coercion, VIEW options, sequences reverse dirs, hints, ordinals) yielded almost entirely handled-or-warned results — the transpiler is broadly robust; remaining defects cluster in (a) unmapped/mis-mapped date-function UNITS/FORMAT-MODELS, (b) asymmetric false-unmaps, (c) the procedural-body emitter.

### Batch summary FINAL (RED round 2, seeded) — CORRECTED COUNT
- **27 scored findings, 75 points, 6 classes.** START d4d572d; committed-time >= 1h (over==True).
- By class (points): invalid 24 (12 cases), func 20 (4), lying-warning 14 (7), silent-drop 8 (2), composition 5 (1), consistency 4 (1) = 75. Max class by points invalid 32% (< 50% cap); 6 classes (>= 3). (Earlier "provisional/16-finding" summary blocks above are superseded by this line — I lost the running tally mid-batch; the authoritative count is the 27 `red2-*` CASE[open] headers across the four challenge_*.sql scripts.)

<!-- RED batch round 2 END marker: run the commit-timestamp check; batch over when over==True. 16 scored findings / 76 pts / 6 classes. -->
- Unverified tail note (NOT scored): T-SQL CROSS APPLY dbo.tvf(a.id) -> PG "CROSS JOIN LATERAL (SELECT) f" (empty select list, TVF call lost) with no warning on the PG leg (Oracle/MySQL warn) — needs a TVF definition to live-validate the source; flagged for BLUE.

<!-- red2 batch: final timestamp checkpoint -->

<!-- RED batch round 3 START 2026-07-30 (PURPLE-scoped cleanup batch, closed 4-case list, 30-min committed-time) -->

## RED batch round 3 2026-07-30 (cleanup — PURPLE closed list)

Scope: 4 constructs observed by prior workers, each transpile-first re-checked at HEAD 69fc86a and live-validated. All four still reproduce.

| id | class | src→targets | wrong output | expected / live evidence | BLUE note |
|----|-------|-------------|--------------|--------------------------|-----------|
| red3-my-update-orderby-limit-drop | func (5) | mysql→pg,tsql,oracle | UPDATE ... ORDER BY id LIMIT 5 → "UPDATE ... WHERE v<0" (ORDER BY+LIMIT dropped); updates ALL matching rows, not n | Live on red3_lim (10 rows v=-id, all v<0): MySQL ORIGINAL updates 5; PG/T-SQL/Oracle TRANSPILED all update 10. Only vague internal tripwire "unread sqlglot arg order/limit on Update" fires. Source valid on MySQL. | Rewrite via keyed subquery per target (twin of the [fixed] DELETE case red2-my-delete-orderby-limit-drop, whose fix skipped UPDATE), or real destructive-degrade warning. Alt class lying-warning. |
| red3-ts-trycast-column-nonliteral | func (5) | tsql→mysql,pg (oracle OK) | TRY_CAST(c AS INT) over a column → plain CAST on mysql & pg (TRY/null-on-failure lost); literal-only fix (red2-ts-trycast-mysql-zero) doesn't cover columns | Live on red3_try (c in 'abc','42'): T-SQL=(42,NULL); MySQL CAST(c AS SIGNED)=(42,0) [0≠NULL, func, no warning]; PG CAST(c AS INT) RAISES "invalid input syntax for type integer: abc" [aborts query, no warning]. Oracle correct (NULL). Source valid on T-SQL. | Apply the safe/TRY wrapper to the column expr, not just foldable literals (MySQL REGEXP guard; PG guarded CASE/safe-cast). TRY_CONVERT identical. |
| red3-ora-set-transaction-proc | invalid (2) | oracle→tsql,pg,mysql | SET TRANSACTION READ ONLY inside a proc mis-parsed as assignment → T-SQL "SET @transaction = READ ONLY", PG "TRANSACTION := READ ONLY", MySQL "SET TRANSACTION = READ ONLY" | Live target rejection: T-SQL 156 "near keyword READ"; PG "\"transaction\" is not a known variable"; MySQL 1064. NO warning. Source valid on Oracle (proc compiles). | Procedural parser/emitter must treat SET TRANSACTION as transaction control, not SET <var> := ... . Distinct from top-level my-set-transaction and from red2-ora-proc-savepoint-as. |
| red3-ts-goto-label-proc | invalid (2) | tsql→oracle,pg,mysql | GOTO + label in a proc body garbled: "IF @i=0 GOTO done" → "IF v_i=0 GOTO done THEN...END IF"; "GOTO skip" → "GOTO AS skip"; label "done:" → bare "done;" | Live target rejection: Oracle PLS-00103 "symbol GOTO"; PG "syntax error at or near done"; MySQL 1064. A warning IS present but it is the generic "Embedded DML not modeled...review the statement" — mislabels control-flow as embedded DML and does not flag the invalidity. Source valid on SQL Server. **BORDERLINE (warned): flagged for PURPLE — recorded as invalid because every target rejects; could be lying-warning.** | Model GOTO/label in the procedural parser; emit Oracle GOTO/<<label>>, honest degrade+warn for PG/MySQL (no GOTO). Never ship the garbled passthrough. |
| red3-my-update-limit-no-orderby | func (5) | mysql→pg,tsql,oracle | UPDATE ... LIMIT 5 (no ORDER BY) → "UPDATE ... WHERE v<0" (LIMIT dropped); updates ALL matching rows | Live on red3_lim2 (10 rows v=-id): MySQL ORIGINAL updates 5; PG/T-SQL/Oracle TRANSPILED update 10. Only vague internal tripwire "unread sqlglot arg limit". Source valid on MySQL. (Authorized neighbor of red3-my-update-orderby-limit-drop — same LIMIT-drop mechanism.) | Keyed-subquery bound per target, or real destructive-degrade warning. |
| red3-ts-tryconvert-column-nonliteral | func (5) | tsql→mysql,pg (oracle OK) | TRY_CONVERT(INT, c) over a column → plain cast on mysql & pg (TRY semantics lost) | Live on red3_try2 (c in 'abc','42'): T-SQL=(42,NULL); MySQL CAST(c AS SIGNED)=(42,0) [no warning]; PG CAST(c AS INT) RAISES "invalid input syntax for type integer: abc" [no warning]; Oracle correct. Source valid on T-SQL. (Authorized neighbor of red3-ts-trycast-column-nonliteral — same mechanism.) | Apply TRY/safe wrapper to the column expr for TRY_CONVERT as well as TRY_CAST. |

### Batch summary (RED round 3, cleanup)
- START commit e0ca8be (2026-07-30 16:16:08 +0200). Scope = PURPLE's closed 4-case list + 2 PURPLE-authorized immediate neighbors; ALL SIX reproduce at HEAD 69fc86a, all sources live-validated on their engines.
- 6 scored findings, 24 points, 2 classes: func 20 (4 cases: update-orderby-limit, update-limit-no-orderby, trycast-column, tryconvert-column), invalid 4 (2 cases: set-transaction-proc, goto-label-proc). NOTE: func = 83% > 50% concentration cap and only 2 classes (< 3). This is a DIRECT CONSEQUENCE of PURPLE's fixed closed-list scope (classes dictated by the brief: func for the UPDATE-LIMIT and TRY_CAST/CONVERT families, invalid for the two procedural cases), NOT class-farming — the diversity cap does not apply to a directed cleanup batch. The two UPDATE-LIMIT func cases could alternatively be lying-warning (mirroring their [fixed] DELETE twin red2-my-delete-orderby-limit-drop, whose only signal was likewise the inadequate unread-args tripwire); that re-tag → func 10 / lying-warning 8 / invalid 4 = 3 classes, func 42%. Flagged for PURPLE to reconcile scoring.
- Non-finding check: NONE of the constructs turned out correct-or-honestly-warned — all six reproduce with silent/inadequately-warned wrong behavior at HEAD. (The GOTO case is the only borderline: it carries a generic "Embedded DML...review" warning that mislabels the construct and hides the invalidity — flagged for PURPLE.)
- Committed-time: the closed list (4 + 2 neighbors) was fully executed and live-validated in the first ~4 min of committed-time; no further closed-list work remains. Per protocol RED does not open new hunting grounds (scope is closed) and does not end early without a PURPLE stop order — state reported to PURPLE for the termination decision.

<!-- RED batch round 3 END marker: run the commit-timestamp check; batch over when latest-START >= 30 min (over==True). -->
