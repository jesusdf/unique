# Diagnostic catalog (`UNIQUE-NNNN` warnings & errors)

> **Generated — do not edit by hand.** Produced by `python scripts/generate_reference_docs.py` from the `UNIQUE-NNNN` registry (`src/unique/core/diagnostics.py`) and the rationale side-table (`src/unique/core/rationales.py`). The CI freshness gate (`python scripts/generate_reference_docs.py --check`) fails the build if this file drifts from the source data.

One entry per stable diagnostic code the transpiler can emit. `code` is the grep/suppress token (`-- UNIQUE-1234: …`); every code is anchored as `warnings.md#unique-1234`. A code with a B31 rationale (33 of 233) renders as a recipe: **Problem** (the triggering construct), **Solution (pointer)** (what Unique does about it — a pointer, not a worked example: the registry carries no SQL sample), **Discussion** (the engine-level reason no direct mapping exists) and **See Also** (the corpus case or test that proves it). The remaining codes render in a compact table marked `_(rationale pending)_` until a rationale is added (the coverage ratchet in `tests/unit/core/test_diagnostics.py` drives that count down).

## Diagnostics with a rationale

### <a id="unique-1002"></a>`UNIQUE-1002` — SET IDENTITY_INSERT ON/OFF (T-SQL)

**Category:** `statement` · **Message:** SET IDENTITY_INSERT {_ii_tbl} {_ii_st} is a T-SQL session directive with no cross-engine equivalent; dropped (the target accepts an explicit value into an identity/serial/ auto_increment column) (docs/03-unsupported.md

**Problem.** SET IDENTITY_INSERT ON/OFF (T-SQL)

**Solution (pointer).** The INSERT's data is faithful; the two SET directives degrade to carriers (one warning).

**Discussion.** T-SQL requires IDENTITY_INSERT ON before a script may supply its own value for an identity column; no other engine has an explicit identity-override mode — they simply accept an explicit value in the INSERT column list — so the ON/OFF bracket has nothing to map to.

**See Also.** [`reda-ts-identity-insert`](../../tests/fixtures/challenge/)

### <a id="unique-1014"></a>`UNIQUE-1014` — Physical index storage clause, e.g. WITH (FILLFACTOR = n) (T-SQL)

**Category:** `statement` · **Message:** {clauses} -- tsql-only, no {dialect} equivalent (physical index clause

**Problem.** Physical index storage clause, e.g. WITH (FILLFACTOR = n) (T-SQL)

**Solution (pointer).** Faithful in result (storage-only); the clause is dropped and kept in a restorable note.

**Discussion.** FILLFACTOR and sibling physical clauses reserve per-page free space — a storage-tuning knob with no logical effect on query results; Oracle and MySQL CREATE INDEX have no equivalent clause.

**See Also.** [`reda-ts-index-fillfactor-mysql`](../../tests/fixtures/challenge/)

### <a id="unique-1015"></a>`UNIQUE-1015` — DISTINCT / ORDER BY over a string column under MySQL's default collation

**Category:** `statement` · **Message:** MySQL default collation is case-insensitive, so DISTINCT/ordering on a string column merges case-differing values

**Problem.** DISTINCT / ORDER BY over a string column under MySQL's default collation

**Solution (pointer).** Documented limit, warned — deduplicated row counts may differ.

**Discussion.** MySQL's default collation is case-insensitive, so DISTINCT / GROUP BY / ORDER BY treat 'a' and 'A' as equal and collapse them into one row; the case-sensitive PostgreSQL/Oracle defaults keep them distinct — a row-count divergence no ORDER BY LOWER() rewrite can bridge without column-level collation visibility.

**See Also.** [`my-distinct-case`](../../tests/fixtures/challenge/)

### <a id="unique-1016"></a>`UNIQUE-1016` — GROUP BY CUBE / ROLLUP / GROUPING SETS super-aggregate rows (→ MySQL)

**Category:** `statement` · **Message:** MySQL has no GROUP BY …; the base grouping is kept and the super-aggregate (subtotal) rows are omitted

**Problem.** GROUP BY CUBE / ROLLUP / GROUPING SETS super-aggregate rows (→ MySQL)

**Solution (pointer).** Warned — base grouping kept; subtotal rows omitted.

**Discussion.** MySQL has no CUBE / GROUPING SETS and only a trailing WITH ROLLUP, so a multi-element grouping's subtotal (super-aggregate) rows cannot be produced; only the base grouping is kept.

**See Also.** [`pg-grouping-fn`](../../tests/fixtures/challenge/)

### <a id="unique-1049"></a>`UNIQUE-1049` — IDENTITY / GENERATED AS IDENTITY with a non-default START/INCREMENT (→ MySQL)

**Category:** `ddl` · **Message:** source IDENTITY (START {seed} INCREMENT {step}) has no MySQL column form — AUTO_INCREMENT starts at 1, steps by 1 (docs/03-unsupported.md

**Problem.** IDENTITY / GENERATED AS IDENTITY with a non-default START/INCREMENT (→ MySQL)

**Solution (pointer).** Warned limit — AUTO_INCREMENT starts at 1 and steps by 1.

**Discussion.** MySQL's only identity form is AUTO_INCREMENT, whose seed is a table option (AUTO_INCREMENT = n) with no per-column START/INCREMENT — a non-default seed/step cannot be reproduced as a column clause.

**See Also.** [`ora-identity-opts`](../../tests/fixtures/challenge/)

### <a id="unique-1054"></a>`UNIQUE-1054` — Cascading referential action on a self-referencing FK (→ T-SQL)

**Category:** `ddl` · **Message:** T-SQL forbids a cascading action on a self-referencing FK (error 1785); downgraded to NO ACTION — emulate with an AFTER trigger if the automatic action is required (docs/03-unsupported.md

**Problem.** Cascading referential action on a self-referencing FK (→ T-SQL)

**Solution (pointer).** Warned limit — downgraded to ON DELETE NO ACTION; emulate the cascade with an AFTER trigger.

**Discussion.** T-SQL rejects a cascading action on a self-referencing foreign key outright (error 1785 at CREATE TABLE time) — an engine restriction, not a missing feature.

**See Also.** [`my-self-fk`](../../tests/fixtures/challenge/)

### <a id="unique-1065"></a>`UNIQUE-1065` — CAST(... AS TIME) and other Oracle-absent value types

**Category:** `expression` · **Message:** Oracle has no {_what} type — value kept as text (docs/03-unsupported.md

**Problem.** CAST(... AS TIME) and other Oracle-absent value types

**Solution (pointer).** Warned limit — value kept as text.

**Discussion.** Oracle has no bare TIME (or plain INTERVAL) type, so the value is kept as text with a documented carrier rather than an invalid cast.

**See Also.** [`my-cast-time`](../../tests/fixtures/challenge/)

### <a id="unique-1066"></a>`UNIQUE-1066` — MySQL JSON type / CAST(... AS JSON)

**Category:** `expression` · **Message:** MySQL JSON type has no faithful cross-engine equivalent (T-SQL has no JSON type; canonical JSON spacing differs on PG/Oracle) — value kept as text — see docs/03-unsupported.md

**Problem.** MySQL JSON type / CAST(... AS JSON)

**Solution (pointer).** Warned limit — value kept as text.

**Discussion.** MySQL's JSON type has no faithful cross-engine equivalent — T-SQL has no JSON type at all, and canonical JSON spacing differs on PostgreSQL/Oracle — so the value is kept as text.

**See Also.** [`my-cast-json`](../../tests/fixtures/challenge/)

### <a id="unique-1067"></a>`UNIQUE-1067` — PostgreSQL geometric type (point/line/…) cast or column

**Category:** `expression` · **Message:** PostgreSQL geometric type … has no cross-engine equivalent — value kept as text (docs/03-unsupported.md

**Problem.** PostgreSQL geometric type (point/line/…) cast or column

**Solution (pointer).** Warned limit — value kept as text.

**Discussion.** PostgreSQL's geometric types have no cross-engine model (MySQL's spatial POINT is a different WKB type), so the value is kept as text.

**See Also.** [`pg-cast-point`](../../tests/fixtures/challenge/)

### <a id="unique-1069"></a>`UNIQUE-1069` — MySQL UNSIGNED integer type / CAST(... AS UNSIGNED)

**Category:** `expression` · **Message:** MySQL UNSIGNED has no {dialect} equivalent; unsigned wraparound not preserved (docs/03-unsupported.md

**Problem.** MySQL UNSIGNED integer type / CAST(... AS UNSIGNED)

**Solution (pointer).** Warned limit — unsigned wraparound not preserved.

**Discussion.** No other engine has an UNSIGNED integer type; the value is mapped to a signed NUMERIC/NUMBER, so unsigned wraparound semantics are not preserved.

**See Also.** [`my-cast-convert`](../../tests/fixtures/challenge/)

### <a id="unique-1076"></a>`UNIQUE-1076` — LISTAGG(...) WITHIN GROUP (...) OVER (...) — windowed string aggregation (Oracle)

**Category:** `expression` · **Message:** windowed string aggregation (string-agg OVER …) has no {dialect} equivalent — see docs/03-unsupported.md

**Problem.** LISTAGG(...) WITHIN GROUP (...) OVER (...) — windowed string aggregation (Oracle)

**Solution (pointer).** Warned limit — degrades to a NULL value plus annotation.

**Discussion.** T-SQL STRING_AGG and MySQL GROUP_CONCAT can never carry an OVER clause, and PostgreSQL rejects an ORDER-BY aggregate used as a window function — there is no running-string-aggregate form to target.

**See Also.** [`ora-listagg-over`](../../tests/fixtures/challenge/)

### <a id="unique-1077"></a>`UNIQUE-1077` — GROUPS window frame (PostgreSQL / Oracle)

**Category:** `expression` · **Message:** a GROUPS window frame has no {dialect} equivalent (only ROWS/RANGE, and no faithful rewrite with ORDER-BY ties) — see docs/03-unsupported.md

**Problem.** GROUPS window frame (PostgreSQL / Oracle)

**Solution (pointer).** Warned limit on T-SQL/MySQL — degrades to a NULL carrier; faithful on Oracle/PostgreSQL.

**Discussion.** T-SQL and MySQL implement only ROWS and RANGE frame units; a GROUPS frame spans whole peer groups, and no ROWS/RANGE combination reproduces that boundary when the ORDER BY key has ties.

**See Also.** [`pg-window-groups-frame`](../../tests/fixtures/challenge/)

### <a id="unique-1080"></a>`UNIQUE-1080` — Sequence CURRVAL — current value without advancing (→ T-SQL)

**Category:** `expression` · **Message:** T-SQL has no sequence CURRVAL; capture NEXT VALUE FOR {seq} in a variable — see docs/03-unsupported.md

**Problem.** Sequence CURRVAL — current value without advancing (→ T-SQL)

**Solution (pointer).** Warned limit — capture NEXT VALUE FOR in a variable instead.

**Discussion.** T-SQL has NEXT VALUE FOR but no CURRVAL; there is no way to read a sequence's current value without advancing it.

**See Also.** [`ora-seq-use`](../../tests/fixtures/challenge/)

### <a id="unique-1082"></a>`UNIQUE-1082` — An empty-string result on Oracle ('' ≡ NULL)

**Category:** `expression` · **Message:** Oracle stores an empty string as NULL (docs/03-unsupported.md)

**Problem.** An empty-string result on Oracle ('' ≡ NULL)

**Solution (pointer).** Warned limit — the empty string surfaces as Oracle NULL.

**Discussion.** Oracle has no on-disk representation for an empty string distinct from NULL — an empty-string result becomes NULL — so a value that is '' on other engines cannot be reproduced there.

**See Also.** [`pg-repeat-negative`](../../tests/fixtures/challenge/)

### <a id="unique-1083"></a>`UNIQUE-1083` — DATEPART(WEEKDAY, d) (T-SQL)

**Category:** `expression` · **Message:** DATEPART(WEEKDAY) is @@DATEFIRST-dependent; converted assuming the session default (Sunday=1

**Problem.** DATEPART(WEEKDAY, d) (T-SQL)

**Solution (pointer).** Warned — correct under the default @@DATEFIRST = 7; a session that changed DATEFIRST will see a different result.

**Discussion.** DATEPART(WEEKDAY) depends on the session @@DATEFIRST setting, which Unique cannot observe at transpile time; the conversion assumes the T-SQL default (Sunday = 1).

**See Also.** [`reda-ts-datepart-weekday`](../../tests/fixtures/challenge/)

### <a id="unique-1088"></a>`UNIQUE-1088` — MySQL UpdateXML() (→ other engines)

**Category:** `expression` · **Message:** MySQL UpdateXML has no cross-engine equivalent (PG lacks it; T-SQL .modify() and Oracle UPDATEXML differ) — see docs/03-unsupported.md

**Problem.** MySQL UpdateXML() (→ other engines)

**Solution (pointer).** Warned limit.

**Discussion.** UpdateXML has no cross-engine equivalent — PostgreSQL lacks it, and T-SQL .modify() / Oracle UPDATEXML differ in shape and semantics.

**See Also.** [`my-xml-fns`](../../tests/fixtures/challenge/)

### <a id="unique-1090"></a>`UNIQUE-1090` — Oracle REGEXP_SUBSTR capture-group extraction (6th arg) (→ MySQL)

**Category:** `expression` · **Message:** Oracle REGEXP_SUBSTR capture-group extraction (6th arg) has no MySQL equivalent (docs/03-unsupported.md

**Problem.** Oracle REGEXP_SUBSTR capture-group extraction (6th arg) (→ MySQL)

**Solution (pointer).** Warned limit — capture-group extraction not reproduced.

**Discussion.** MySQL's REGEXP_SUBSTR has no capture-group argument, so the sub-group extraction cannot be expressed; the portable (str, pat, pos, occ) subset is emitted.

**See Also.** [`ora-regexp-group`](../../tests/fixtures/challenge/)

### <a id="unique-1096"></a>`UNIQUE-1096` — EXTRACT(EPOCH FROM interval) (PostgreSQL)

**Category:** `expression` · **Message:** EXTRACT(EPOCH FROM interval) has no portable equivalent (T-SQL/MySQL have no interval value type) — see docs/03-unsupported.md

**Problem.** EXTRACT(EPOCH FROM interval) (PostgreSQL)

**Solution (pointer).** Warned limit — degrades to NULL + annotation (EPOCH FROM a timestamp is still computed).

**Discussion.** T-SQL and MySQL have no interval value type, so the epoch (total seconds) of an interval value has no portable equivalent.

**See Also.** [`pg-epoch`](../../tests/fixtures/challenge/)

### <a id="unique-1097"></a>`UNIQUE-1097` — EXTRACT(MICROSECONDS FROM TIME) (→ Oracle)

**Category:** `expression` · **Message:** EXTRACT(MICROSECONDS FROM TIME) has no Oracle equivalent (no TIME type) — see docs/03-unsupported.md

**Problem.** EXTRACT(MICROSECONDS FROM TIME) (→ Oracle)

**Solution (pointer).** Warned limit.

**Discussion.** Oracle has no TIME type, so the microseconds field of a TIME value has no Oracle equivalent.

**See Also.** [`pg-frac-seconds`](../../tests/fixtures/challenge/)

### <a id="unique-1100"></a>`UNIQUE-1100` — MySQL CHAR(n) as a numeric-to-byte-string function

**Category:** `expression` · **Message:** MySQL CHAR({_n}) is a multi-byte byte string, not a single code point (docs/03-unsupported.md

**Problem.** MySQL CHAR(n) as a numeric-to-byte-string function

**Solution (pointer).** Warned limit — carrier flags the byte-string vs code-point difference.

**Discussion.** MySQL's CHAR(n) returns a multi-byte byte string (CHAR(256) = the 2-byte string 0x0100), not a single Unicode code point like CHR/NCHAR, so the two cannot be equated.

**See Also.** [`my-char-256`](../../tests/fixtures/challenge/)

### <a id="unique-1103"></a>`UNIQUE-1103` — SELECT ... FOR SHARE — a shared row lock (→ Oracle)

**Category:** `statement` · **Message:** FOR SHARE (shared row lock) has no Oracle equivalent (Oracle SELECT locking is FOR UPDATE, exclusive); the shared lock is dropped (docs/03-unsupported.md

**Problem.** SELECT ... FOR SHARE — a shared row lock (→ Oracle)

**Solution (pointer).** Warned limit — the shared lock is dropped.

**Discussion.** Oracle SELECT locking is FOR UPDATE (exclusive) only — it has no shared-row-lock mode — so the shared lock cannot be reproduced.

**See Also.** [`my-for-share`](../../tests/fixtures/challenge/)

### <a id="unique-1104"></a>`UNIQUE-1104` — Oracle FOR UPDATE WAIT <n> — a bounded lock wait

**Category:** `statement` · **Message:** Oracle FOR UPDATE WAIT <n> (bounded lock wait) has no {dialect} equivalent; it blocks with the default behavior (docs/03-unsupported.md

**Problem.** Oracle FOR UPDATE WAIT <n> — a bounded lock wait

**Solution (pointer).** Warned limit — it blocks with the target's default behavior.

**Discussion.** PostgreSQL/MySQL offer only FOR UPDATE / NOWAIT / SKIP LOCKED, with no bounded-wait timeout, so the WAIT <n> bound has no equivalent.

**See Also.** [`ora-forupdate-wait`](../../tests/fixtures/challenge/)

### <a id="unique-1137"></a>`UNIQUE-1137` — T-SQL OUTPUT ... INTO <table> redirect (→ PostgreSQL)

**Category:** `statement` · **Message:** T-SQL OUTPUT … INTO <table> redirect has no PostgreSQL equivalent in a plain INSERT (it needs a data-modifying CTE); the INTO target is dropped and the RETURNING result is kept (docs/03-unsupported.md

**Problem.** T-SQL OUTPUT ... INTO <table> redirect (→ PostgreSQL)

**Solution (pointer).** Warned limit — the INTO redirect is dropped; the base DML and plain RETURNING are faithful.

**Discussion.** PostgreSQL's RETURNING only returns a result set to the caller; it has no INTO <table> redirect form, so the redirect cannot be expressed in a plain INSERT.

**See Also.** [`reda-ts-output-into`](../../tests/fixtures/challenge/)

### <a id="unique-1139"></a>`UNIQUE-1139` — A top-level OUTPUT / RETURNING result set (→ Oracle)

**Category:** `statement` · **Message:** Oracle has no top-level RETURNING; the statement returned: {cols}

**Problem.** A top-level OUTPUT / RETURNING result set (→ Oracle)

**Solution (pointer).** Warned limit — the DML runs; the returned result set is documented, not produced.

**Discussion.** Oracle's RETURNING is PL/SQL-only — it must target INTO bind variables and cannot stand alone in a plain SQL statement (ORA-63809) — so a standalone OUTPUT/RETURNING has no Oracle equivalent.

**See Also.** [`reda-ts-output-into`](../../tests/fixtures/challenge/)

### <a id="unique-1148"></a>`UNIQUE-1148` — Foreign-key ON UPDATE referential action (→ Oracle)

**Category:** `statement` · **Message:** FK ON UPDATE referential action dropped — Oracle has no ON UPDATE FK action (docs/03-unsupported.md

**Problem.** Foreign-key ON UPDATE referential action (→ Oracle)

**Solution (pointer).** Warned limit — ON UPDATE is dropped; reproduce it with a trigger if needed.

**Discussion.** Oracle foreign keys support only ON DELETE CASCADE / SET NULL — there is no ON UPDATE referential action (ORA-00905).

**See Also.** [`reda-ts-fk-on-update`](../../tests/fixtures/challenge/)

### <a id="unique-1151"></a>`UNIQUE-1151` — A source-engine built-in with no form in the target's catalog (e.g. SOUNDEX → PostgreSQL)

**Category:** `validation` · **Message:** output failed the {target} validity check ({reason}); original {source} batch preserved

**Problem.** A source-engine built-in with no form in the target's catalog (e.g. SOUNDEX → PostgreSQL)

**Solution (pointer).** Warned limit — the statement is preserved as a carrier and the failing built-in is named.

**Discussion.** A call that is a built-in of the source engine (clearly meant to run, not a user object) but absent from the target's catalog would be rejected outright, so the whole statement degrades rather than shipping an invalid call — the general unmapped-built-in gate.

**See Also.** [`ora-soundex`](../../tests/fixtures/challenge/)

### <a id="unique-1152"></a>`UNIQUE-1152` — Oracle %TYPE / %ROWTYPE column-type reference (without --db-url)

**Category:** `procedural` · **Message:** type origin comment preserved from the source declaration

**Problem.** Oracle %TYPE / %ROWTYPE column-type reference (without --db-url)

**Solution (pointer).** Warned limit without --db-url (carrier type may not match exactly); faithful with --db-url or on an Oracle→Oracle round-trip.

**Discussion.** Only Oracle supports %TYPE/%ROWTYPE; resolving the real column type needs a live catalog lookup (ALL_TAB_COLUMNS) unavailable without a DB connection, so a permissive carrier type is emitted with the original reference preserved for a faithful round-trip back to Oracle.

**See Also.** [`test_type_reference_documented_then_restored`](../../tests/integration/test_procedural.py)

### <a id="unique-1161"></a>`UNIQUE-1161` — T-SQL sp_executesql parameter declarations/bindings (→ MySQL)

**Category:** `procedural` · **Message:** sp_executesql parameter declarations/bindings dropped; pass them via EXECUTE ... USING manually

**Problem.** T-SQL sp_executesql parameter declarations/bindings (→ MySQL)

**Solution (pointer).** Warned limit — parameter bindings dropped.

**Discussion.** MySQL's PREPARE/EXECUTE has no inline parameter-declaration + binding form matching sp_executesql's @params list, so the declarations/bindings are dropped and must be passed via EXECUTE ... USING.

**See Also.** [`ts-sp-executesql`](../../tests/fixtures/challenge/)

### <a id="unique-1180"></a>`UNIQUE-1180` — T-SQL sp_executesql named parameters (→ Oracle)

**Category:** `procedural` · **Message:** sp_executesql named parameters bind POSITIONALLY here — spell the placeholders inside the dynamic string as :1, :2, … (docs/03-unsupported.md

**Problem.** T-SQL sp_executesql named parameters (→ Oracle)

**Solution (pointer).** Warned limit — placeholders must be renumbered positionally.

**Discussion.** Oracle EXECUTE IMMEDIATE ... USING binds positionally, so the named @params of sp_executesql must be re-spelled inside the dynamic string as :1, :2, ….

**See Also.** [`ts-sp-executesql`](../../tests/fixtures/challenge/)

### <a id="unique-1207"></a>`UNIQUE-1207` — Inherent value divergence: default-collation comparison, Oracle '' ≡ NULL, or byte-vs-char length (approved limit)

**Category:** `orchestration` · **Message:** approved value divergence (collation/encoding) kept with a warning; reason carried at runtime

**Problem.** Inherent value divergence: default-collation comparison, Oracle '' ≡ NULL, or byte-vs-char length (approved limit)

**Solution (pointer).** Approved documented limit, warned — the value or row count may differ.

**Discussion.** These divergences (case/accent/trailing-space comparison under the default collation, Oracle's '' ≡ NULL, LENGTH byte-vs-char) are per-column/connection properties the SQL text carries no trace of; no statement-level rewrite bridges them without column-collation/encoding visibility Unique does not have.

**See Also.** [`ora-empty-null`](../../tests/fixtures/challenge/)

### <a id="unique-1211"></a>`UNIQUE-1211` — EXEC sp_<name> — a T-SQL system procedure (→ other engines)

**Category:** `orchestration` · **Message:** {sp} is a SQL Server system procedure with no {target} equivalent; original call omitted

**Problem.** EXEC sp_<name> — a T-SQL system procedure (→ other engines)

**Solution (pointer).** Warned limit — the call becomes a carrier; the administrative action must be performed via the target's own tooling.

**Discussion.** T-SQL system procedures call SQL Server's own catalog/admin machinery; no other engine exposes the same operation through a callable procedure with the same name or signature.

**See Also.** [`reda-ts-exec-swallow-next`](../../tests/fixtures/challenge/)

### <a id="unique-1212"></a>`UNIQUE-1212` — A standalone INSERT/UPDATE/DELETE ... OUTPUT result set (→ Oracle / MySQL)

**Category:** `orchestration` · **Message:** {target} has no standalone OUTPUT/RETURNING result set; the statement returned: {cols} (docs/03-unsupported.md

**Problem.** A standalone INSERT/UPDATE/DELETE ... OUTPUT result set (→ Oracle / MySQL)

**Solution (pointer).** Warned limit — the DML effect is faithful; the returned result set is documented, not produced.

**Discussion.** Neither Oracle (RETURNING is PL/SQL-only, ORA-63809) nor MySQL has a standalone data-modifying-statement result set, so the OUTPUT rows cannot be returned to the caller.

**See Also.** [`ts-insert-output`](../../tests/fixtures/challenge/)

### <a id="unique-1233"></a>`UNIQUE-1233` — A transaction closer (COMMIT/END/ROLLBACK) whose opener failed

**Category:** `statement` · **Message:** transaction closer preserved as a comment: its opener degraded to a parse-failure carrier, so shipping the COMMIT/ROLLBACK would orphan it (no open transaction — T-SQL error 3902)

**Problem.** A transaction closer (COMMIT/END/ROLLBACK) whose opener failed

**Solution (pointer).** Coherent degrade — the closer is preserved as a comment so the output has no orphan COMMIT; both halves of the broken transaction unit are carried, not silently dropped.

**Discussion.** When a transaction opener (BEGIN) glues to the next statement and fails to parse, that whole batch degrades to a parse-failure carrier — no BEGIN reaches the output. Emitting the sibling closer as an executable COMMIT/ROLLBACK would then run against no open transaction (T-SQL error 3902), so the closer must degrade too.

**See Also.** [`TestTransactionOpenerDegradeCoherence::test_orphan_closer_after_failed_opener_degrades`](../../tests/unit/core/test_transpiler.py)

## Diagnostics without a rationale yet

| Code | Category | Message template | Rationale |
|---|---|---|---|
| <a id="unique-1001"></a>`UNIQUE-1001` | statement | MERGE rewritten as INSERT ... ON DUPLICATE KEY UPDATE; requires a UNIQUE or PRIMARY KEY on<br>({on_cols} | _(rationale pending)_ |
| <a id="unique-1003"></a>`UNIQUE-1003` | statement | statement preserved as a comment; the specific reason is carried at runtime | _(rationale pending)_ |
| <a id="unique-1004"></a>`UNIQUE-1004` | statement | NULLS FIRST/LAST index ordering has no {dialect} equivalent; dropped (it affects only the index's<br>physical null order, not query results | _(rationale pending)_ |
| <a id="unique-1005"></a>`UNIQUE-1005` | statement | statement preserved as a comment; the specific reason is carried at runtime | _(rationale pending)_ |
| <a id="unique-1006"></a>`UNIQUE-1006` | statement | {reason} | _(rationale pending)_ |
| <a id="unique-1007"></a>`UNIQUE-1007` | statement | partial-index predicate dropped (no {dialect} filtered-index form); the index is broader than the<br>source's: … | _(rationale pending)_ |
| <a id="unique-1008"></a>`UNIQUE-1008` | statement | PostgreSQL unique indexes treat NULLs as distinct; T-SQL allows a single NULL per unique index | _(rationale pending)_ |
| <a id="unique-1009"></a>`UNIQUE-1009` | statement | T-SQL has no boolean value type; NOT of a non-predicate (e.g. NOT NULL) has no equivalent -- see<br>docs/03-unsupported.md | _(rationale pending)_ |
| <a id="unique-1010"></a>`UNIQUE-1010` | statement | T-SQL ALTER COLUMN defaults the column to NULL; the script does not define {table}.{col}'s<br>nullability, so it cannot be re-stated — verify the column keeps its constraint | _(rationale pending)_ |
| <a id="unique-1011"></a>`UNIQUE-1011` | statement | named DEFAULT constraint {n} dropped (defaults are anonymous on this engine | _(rationale pending)_ |
| <a id="unique-1012"></a>`UNIQUE-1012` | statement | {dialect} does not support INCLUDE covering columns; dropped: … | _(rationale pending)_ |
| <a id="unique-1013"></a>`UNIQUE-1013` | statement | {dialect} does not support filtered indexes; dropped predicate:… | _(rationale pending)_ |
| <a id="unique-1017"></a>`UNIQUE-1017` | statement | MySQL has no multi-element GROUP BY (CUBE/ROLLUP/ GROUPING SETS combined); the base grouping is kept<br>and the super-aggregate (subtotal) rows are omitted | _(rationale pending)_ |
| <a id="unique-1018"></a>`UNIQUE-1018` | statement | T-SQL FOR XML/JSON row serialization has no cross-engine equivalent; the clause is dropped and the<br>base rows are returned instead (see docs/03-unsupported.md | _(rationale pending)_ |
| <a id="unique-1019"></a>`UNIQUE-1019` | statement | MySQL SQL_CALC_FOUND_ROWS has no equivalent here; the full row count for a following FOUND_ROWS() is<br>not computed — run a separate COUNT(*) query | _(rationale pending)_ |
| <a id="unique-1020"></a>`UNIQUE-1020` | statement | all-defaults INSERT has no Oracle spelling without the column list; original preserved | _(rationale pending)_ |
| <a id="unique-1021"></a>`UNIQUE-1021` | statement | INSERT preserved as a comment; the specific reason is carried at runtime | _(rationale pending)_ |
| <a id="unique-1022"></a>`UNIQUE-1022` | statement | conflict target assumed to be (…) from the table's key; the MySQL source names no explicit target<br>(fires on any unique key | _(rationale pending)_ |
| <a id="unique-1023"></a>`UNIQUE-1023` | statement | INSERT IGNORE also swallows other errors (bad values, FK violations), not only duplicate keys —<br>unlike PG ON CONFLICT DO NOTHING | _(rationale pending)_ |
| <a id="unique-1024"></a>`UNIQUE-1024` | statement | MySQL ON DUPLICATE KEY UPDATE fires on ANY unique/primary key, not a single named conflict target | _(rationale pending)_ |
| <a id="unique-1025"></a>`UNIQUE-1025` | statement | MERGE ON key assumed to be (…) from the table's key; the source names no explicit conflict target | _(rationale pending)_ |
| <a id="unique-1026"></a>`UNIQUE-1026` | statement | Oracle has no UPDATE ... FROM and this join shape (no ON condition) cannot become a correlated<br>subquery; rewrite as a MERGE. Original | _(rationale pending)_ |
| <a id="unique-1027"></a>`UNIQUE-1027` | statement | @@ROWCOUNT has no top-level {dialect} equivalent | _(rationale pending)_ |
| <a id="unique-1028"></a>`UNIQUE-1028` | statement | @@FETCH_STATUS has no top-level {dialect} equivalent; it is cursor state | _(rationale pending)_ |
| <a id="unique-1029"></a>`UNIQUE-1029` | statement | @@ERROR has no top-level {dialect} equivalent; use an exception handler | _(rationale pending)_ |
| <a id="unique-1030"></a>`UNIQUE-1030` | statement | @@VERSION -> {fn}; version string differs per engine | _(rationale pending)_ |
| <a id="unique-1031"></a>`UNIQUE-1031` | statement | @@VERSION has no Oracle equivalent outside v$version | _(rationale pending)_ |
| <a id="unique-1032"></a>`UNIQUE-1032` | statement | @@SPID -> {fn}; session id differs per engine | _(rationale pending)_ |
| <a id="unique-1033"></a>`UNIQUE-1033` | statement | SQL%ROWCOUNT has no top-level {dialect} equivalent | _(rationale pending)_ |
| <a id="unique-1034"></a>`UNIQUE-1034` | statement | TABLESAMPLE ({what}) has no MySQL equivalent — all rows returned (docs/03-unsupported.md | _(rationale pending)_ |
| <a id="unique-1035"></a>`UNIQUE-1035` | statement | TABLESAMPLE by row count has no Oracle SAMPLE form (docs/03-unsupported.md | _(rationale pending)_ |
| <a id="unique-1036"></a>`UNIQUE-1036` | statement | TABLESAMPLE by row count has no PostgreSQL equivalent (docs/03-unsupported.md | _(rationale pending)_ |
| <a id="unique-1037"></a>`UNIQUE-1037` | statement | source had WITH TIES; MySQL has no equivalent — rows tying the last one are not returned (see<br>docs/03-unsupported.md | _(rationale pending)_ |
| <a id="unique-1038"></a>`UNIQUE-1038` | statement | source was TOP n PERCENT; {dialect} has no LIMIT PERCENT — emitted as a row count, adjust to<br>CEIL(n/100 * total_rows) if a true percentage is required | _(rationale pending)_ |
| <a id="unique-1039"></a>`UNIQUE-1039` | ddl | Oracle WITH LOCAL TIME ZONE and PostgreSQL timestamptz both display column {name} in the session<br>time zone (same instant, session-dependent wall clock) (docs/03-unsupported.md | _(rationale pending)_ |
| <a id="unique-1040"></a>`UNIQUE-1040` | ddl | tsql has no session-local timestamp type — column {name} WITH LOCAL TIME ZONE maps to<br>DATETIMEOFFSET; the value's instant is kept but the session-time-zone display is not reproduced<br>(docs/03-unsupported.md | _(rationale pending)_ |
| <a id="unique-1041"></a>`UNIQUE-1041` | ddl | mysql has no session-local timestamp type — column {name} WITH LOCAL TIME ZONE maps to TIMESTAMP;<br>the value's instant is kept but the session-time-zone display is not reproduced<br>(docs/03-unsupported.md | _(rationale pending)_ |
| <a id="unique-1042"></a>`UNIQUE-1042` | ddl | Oracle has no TIME type — column … stores the time of day as INTERVAL DAY TO SECOND{tz}<br>(docs/03-unsupported.md | _(rationale pending)_ |
| <a id="unique-1043"></a>`UNIQUE-1043` | ddl | PostgreSQL INTERVAL mixes year-month and day-second fields; column … is mapped to INTERVAL DAY TO<br>SECOND — year-month values need a separate INTERVAL YEAR TO MONTH column (docs/03-unsupported.md | _(rationale pending)_ |
| <a id="unique-1044"></a>`UNIQUE-1044` | ddl | {dialect} has no INTERVAL column type — column … keeps the interval as text (docs/03-unsupported.md | _(rationale pending)_ |
| <a id="unique-1045"></a>`UNIQUE-1045` | ddl | MySQL fractional-seconds precision caps at 6 — column … precision … clamped to 6<br>(docs/03-unsupported.md | _(rationale pending)_ |
| <a id="unique-1046"></a>`UNIQUE-1046` | ddl | {dialect} has no bit-string type — column … BIT(…) stores its numeric value as {mapped}<br>(docs/03-unsupported.md | _(rationale pending)_ |
| <a id="unique-1047"></a>`UNIQUE-1047` | ddl | MySQL SET type on {col_name} has no {dialect} equivalent; stored as {varchar}({total_len}). Allowed<br>members: {quoted_values} | _(rationale pending)_ |
| <a id="unique-1048"></a>`UNIQUE-1048` | ddl | LIKE clone copies column structure only here; the source's indexes/keys are not cloned | _(rationale pending)_ |
| <a id="unique-1050"></a>`UNIQUE-1050` | ddl | MySQL ON UPDATE column clause has no equivalent on the target engine | _(rationale pending)_ |
| <a id="unique-1051"></a>`UNIQUE-1051` | ddl | column {col_name} collation/charset (…) has no portable {dialect} equivalent; the column uses the<br>default collation (comparisons/ordering may differ) — set it explicitly on the target or supply the<br>source DB connection | _(rationale pending)_ |
| <a id="unique-1052"></a>`UNIQUE-1052` | ddl | column {col_name} was INVISIBLE (excluded from SELECT *) on the source; {dialect} has no invisible-<br>column attribute, so the column is now visible to SELECT * (docs/03-unsupported.md | _(rationale pending)_ |
| <a id="unique-1053"></a>`UNIQUE-1053` | ddl | PostgreSQL UNIQUE … NULLS NOT DISTINCT (NULLs compare equal) has no {dialect} equivalent; a plain<br>UNIQUE treats NULLs as distinct (docs/03-unsupported.md | _(rationale pending)_ |
| <a id="unique-1055"></a>`UNIQUE-1055` | ddl | Oracle has no ON DELETE SET DEFAULT referential action; dropped (FK reverts to NO ACTION) — emulate<br>with an AFTER DELETE trigger if required (docs/03-unsupported.md | _(rationale pending)_ |
| <a id="unique-1056"></a>`UNIQUE-1056` | ddl | T-SQL In-Memory OLTP storage option(s) [{opts}] have no {dialect} equivalent; the table is created<br>as a regular disk-based table (no logical/value difference | _(rationale pending)_ |
| <a id="unique-1057"></a>`UNIQUE-1057` | ddl | MySQL table default collation/charset (…) has no portable {dialect} equivalent; string columns use<br>the default collation (comparisons/ordering may differ) — set it explicitly on the target or supply<br>the source DB connection | _(rationale pending)_ |
| <a id="unique-1058"></a>`UNIQUE-1058` | ddl | view modifier {mod} is not portable on {dialect}; dropped | _(rationale pending)_ |
| <a id="unique-1059"></a>`UNIQUE-1059` | ddl | MySQL has no sequences (use an AUTO_INCREMENT column); original preserved | _(rationale pending)_ |
| <a id="unique-1060"></a>`UNIQUE-1060` | ddl | MySQL has no user-defined types; original preserved | _(rationale pending)_ |
| <a id="unique-1061"></a>`UNIQUE-1061` | ddl | {dialect} DROP INDEX requires the owning table, which the source statement does not carry; original<br>preserved | _(rationale pending)_ |
| <a id="unique-1062"></a>`UNIQUE-1062` | ddl | PostgreSQL DROP TRIGGER requires the owning table (ON tbl), which the source statement does not<br>carry; original preserved | _(rationale pending)_ |
| <a id="unique-1063"></a>`UNIQUE-1063` | expression | … (…) — see docs/03-unsupported.md | _(rationale pending)_ |
| <a id="unique-1064"></a>`UNIQUE-1064` | expression | Oracle SESSIONTIMEZONE is session- dependent; the mapped expression reports this session's<br>zone/offset in the target's own format (docs/03-unsupported.md | _(rationale pending)_ |
| <a id="unique-1068"></a>`UNIQUE-1068` | expression | PostgreSQL NaN/Infinity has no {dialect} numeric equivalent (docs/03-unsupported.md | _(rationale pending)_ |
| <a id="unique-1070"></a>`UNIQUE-1070` | expression | Oracle DEFAULT ... ON CONVERSION ERROR has no {dialect} error-safe cast for this type; fallback<br>dropped -- see docs/03-unsupported.md | _(rationale pending)_ |
| <a id="unique-1071"></a>`UNIQUE-1071` | expression | T-SQL FOR XML/JSON row serialization has no cross-engine equivalent — see docs/03-unsupported.md | _(rationale pending)_ |
| <a id="unique-1072"></a>`UNIQUE-1072` | expression | …; no {dialect} mapping — review | _(rationale pending)_ |
| <a id="unique-1073"></a>`UNIQUE-1073` | expression | MySQL date arithmetic on a non-datetime string literal yields NULL (docs/03-unsupported.md | _(rationale pending)_ |
| <a id="unique-1074"></a>`UNIQUE-1074` | expression | MySQL DATE - DATE is a numeric YYYYMMDD subtraction; normalized to a day count<br>(docs/03-unsupported.md | _(rationale pending)_ |
| <a id="unique-1075"></a>`UNIQUE-1075` | expression | timestamp difference is an INTERVAL with no {dialect} equivalent; emitted as a SECOND count<br>(docs/03-unsupported.md | _(rationale pending)_ |
| <a id="unique-1078"></a>`UNIQUE-1078` | expression | a window frame … has no {dialect} equivalent (T-SQL/MySQL have no EXCLUDE, and no faithful<br>ROWS/RANGE rewrite) — see docs/03-unsupported.md | _(rationale pending)_ |
| <a id="unique-1079"></a>`UNIQUE-1079` | expression | {fn} unit '{unit_sql}' has no {dialect} equivalent — the value was not computed<br>(docs/03-unsupported.md | _(rationale pending)_ |
| <a id="unique-1081"></a>`UNIQUE-1081` | expression | DATEPART(WEEKDAY) is @@DATEFIRST-dependent; assumes the session default (Sunday=1 | _(rationale pending)_ |
| <a id="unique-1084"></a>`UNIQUE-1084` | expression | Oracle ROUND(date, '{fmt}') (nearest {fmt} boundary) has no faithful {dialect} equivalent — the<br>value was not computed (docs/03-unsupported.md | _(rationale pending)_ |
| <a id="unique-1085"></a>`UNIQUE-1085` | expression | Oracle TRUNC(date, '{raw_up}') has no {dialect} equivalent — the value was not computed<br>(docs/03-unsupported.md | _(rationale pending)_ |
| <a id="unique-1086"></a>`UNIQUE-1086` | expression | EXTRACT({part}) has no {dialect} equivalent — the value was not computed (docs/03-unsupported.md | _(rationale pending)_ |
| <a id="unique-1087"></a>`UNIQUE-1087` | expression | Oracle INSTR with an occurrence count or backward (negative-start) search has no portable equivalent<br>for non-literal arguments — see docs/03-unsupported.md | _(rationale pending)_ |
| <a id="unique-1089"></a>`UNIQUE-1089` | expression | collation names are engine-specific and cannot match across engines (docs/03-unsupported.md | _(rationale pending)_ |
| <a id="unique-1091"></a>`UNIQUE-1091` | expression | MySQL has no TRANSLATE and a nested-REPLACE emulation is order-dependent (not equivalent) — see<br>docs/03-unsupported.md | _(rationale pending)_ |
| <a id="unique-1092"></a>`UNIQUE-1092` | expression | SUBSTRING(x FROM POSIX pattern) has no T-SQL regex equivalent — see docs/03-unsupported.md | _(rationale pending)_ |
| <a id="unique-1093"></a>`UNIQUE-1093` | expression | SUBSTRING(x FROM SIMILAR-TO pattern FOR escape) has no cross-engine equivalent (SQL-regex metachars<br>differ from POSIX) — see docs/03-unsupported.md | _(rationale pending)_ |
| <a id="unique-1094"></a>`UNIQUE-1094` | expression | Oracle stores an empty string as NULL (docs/03-unsupported.md | _(rationale pending)_ |
| <a id="unique-1095"></a>`UNIQUE-1095` | expression | MySQL VALUES(col) outside INSERT … ON DUPLICATE KEY UPDATE is NULL | _(rationale pending)_ |
| <a id="unique-1098"></a>`UNIQUE-1098` | expression | PG format() with %L/width/positional specifiers has no cross-engine equivalent — see<br>docs/03-unsupported.md | _(rationale pending)_ |
| <a id="unique-1099"></a>`UNIQUE-1099` | expression | PG sha256/sha512 returns a bytea digest; other engines return a hex string (same digest, different<br>representation) — see docs/03-unsupported.md | _(rationale pending)_ |
| <a id="unique-1101"></a>`UNIQUE-1101` | statement | {_cte_reason} | _(rationale pending)_ |
| <a id="unique-1102"></a>`UNIQUE-1102` | statement | MySQL NOT ENFORCED (a CHECK defined but not validated) has no target equivalent; enforced here | _(rationale pending)_ |
| <a id="unique-1105"></a>`UNIQUE-1105` | statement | Oracle FOR UPDATE OF <column> selects which table's rows to lock; {dialect} FOR UPDATE OF takes<br>table names, so the OF list is dropped (every row read is locked) (docs/03-unsupported.md | _(rationale pending)_ |
| <a id="unique-1106"></a>`UNIQUE-1106` | statement | T-SQL has no expression/function index; add a computed column and index it (docs/03-unsupported.md | _(rationale pending)_ |
| <a id="unique-1107"></a>`UNIQUE-1107` | statement | T-SQL IDENTITY() in SELECT INTO reproduced as ROW_NUMBER (id values match); the identity/auto-<br>increment column property is not portable in a CREATE TABLE AS SELECT (docs/03-unsupported.md | _(rationale pending)_ |
| <a id="unique-1108"></a>`UNIQUE-1108` | statement | {dialect} has no ALTER … NOT VALID; the constraint is validated immediately (PostgreSQL defers it | _(rationale pending)_ |
| <a id="unique-1109"></a>`UNIQUE-1109` | statement | TRUNCATE … CASCADE (also truncates FK-dependent tables) has no {dialect} equivalent; only this table<br>is truncated — truncate any dependents explicitly | _(rationale pending)_ |
| <a id="unique-1110"></a>`UNIQUE-1110` | statement | {dialect} has no ALTER COLUMN … USING conversion expression; convert the data manually. Statement<br>preserved as a comment | _(rationale pending)_ |
| <a id="unique-1111"></a>`UNIQUE-1111` | statement | {dialect} needs the column's declared type to alter its nullability and the script does not define<br>{_nn_tbl_raw}.{_nn_col}; original postgresql statement preserved | _(rationale pending)_ |
| <a id="unique-1112"></a>`UNIQUE-1112` | statement | MySQL's only identity form is AUTO_INCREMENT (must be a key; a UNIQUE index is added | _(rationale pending)_ |
| <a id="unique-1113"></a>`UNIQUE-1113` | statement | PostgreSQL GIN/GiST/BRIN index has no {dialect} equivalent (access-method specific); index omitted —<br>queries run unindexed (docs/03-unsupported.md | _(rationale pending)_ |
| <a id="unique-1114"></a>`UNIQUE-1114` | statement | expression index over a LOB-typed column is invalid on {dialect} (ORA-02327 / MySQL functional-index<br>restriction); index omitted — queries run unindexed (docs/03-unsupported.md | _(rationale pending)_ |
| <a id="unique-1115"></a>`UNIQUE-1115` | statement | CONCURRENTLY (PostgreSQL's non-locking index build) has no {dialect} equivalent; the index is<br>created with the target's default locking | _(rationale pending)_ |
| <a id="unique-1116"></a>`UNIQUE-1116` | statement | MySQL session setting has no {dialect} equivalent; configure the session natively. | _(rationale pending)_ |
| <a id="unique-1117"></a>`UNIQUE-1117` | statement | MySQL admin command has no {dialect} equivalent; run the target's own maintenance. | _(rationale pending)_ |
| <a id="unique-1118"></a>`UNIQUE-1118` | statement | {dialect} has no TEMPORARY sequences; statement preserved as a comment | _(rationale pending)_ |
| <a id="unique-1119"></a>`UNIQUE-1119` | statement | MySQL has no sequences; use an AUTO_INCREMENT column instead. Original | _(rationale pending)_ |
| <a id="unique-1120"></a>`UNIQUE-1120` | statement | SET SESSION AUTHORIZATION has no {dialect} equivalent; switch users natively. | _(rationale pending)_ |
| <a id="unique-1121"></a>`UNIQUE-1121` | statement | PostgreSQL session setting has no {dialect} equivalent; configure the session natively. | _(rationale pending)_ |
| <a id="unique-1122"></a>`UNIQUE-1122` | statement | {dialect} has no USE statement; connect to the target database/schema instead. | _(rationale pending)_ |
| <a id="unique-1123"></a>`UNIQUE-1123` | statement | PostgreSQL column STORAGE tuning has no {dialect} equivalent; statement preserved as a comment | _(rationale pending)_ |
| <a id="unique-1124"></a>`UNIQUE-1124` | statement | PostgreSQL's recursive-CTE SEARCH/CYCLE clause has no {dialect} equivalent; statement preserved as a<br>comment | _(rationale pending)_ |
| <a id="unique-1125"></a>`UNIQUE-1125` | statement | MySQL has no MERGE; rewrite as INSERT ... ON DUPLICATE KEY UPDATE. Original | _(rationale pending)_ |
| <a id="unique-1126"></a>`UNIQUE-1126` | statement | CTE with unsupported embedded DML preserved as a comment; reason carried at runtime | _(rationale pending)_ |
| <a id="unique-1127"></a>`UNIQUE-1127` | statement | BEGIN TRANSACTION dropped -- Oracle starts a transaction implicitly | _(rationale pending)_ |
| <a id="unique-1128"></a>`UNIQUE-1128` | statement | T-SQL transactions have no READ … access mode; started as a regular transaction<br>(docs/03-unsupported.md | _(rationale pending)_ |
| <a id="unique-1129"></a>`UNIQUE-1129` | statement | READ COMMITTED is Oracle's default isolation level (no-op; kept as a note so a following SET<br>TRANSACTION mode statement can still open the transaction | _(rationale pending)_ |
| <a id="unique-1130"></a>`UNIQUE-1130` | statement | READ COMMITTED is Oracle's default isolation level (no-op; kept as a note so a following SET<br>TRANSACTION mode statement can still open the transaction | _(rationale pending)_ |
| <a id="unique-1131"></a>`UNIQUE-1131` | statement | Oracle has no {level} isolation level (supports READ COMMITTED/SERIALIZABLE only); statement<br>dropped. Original | _(rationale pending)_ |
| <a id="unique-1132"></a>`UNIQUE-1132` | statement | T-SQL SET TRANSACTION has no READ {mode} access mode; access mode dropped (docs/03-unsupported.md | _(rationale pending)_ |
| <a id="unique-1133"></a>`UNIQUE-1133` | statement | T-SQL SET TRANSACTION has no READ {mode} access mode (docs/03-unsupported.md); statement dropped.<br>Original | _(rationale pending)_ |
| <a id="unique-1134"></a>`UNIQUE-1134` | statement | Oracle CONNECT BY / START WITH hierarchical query has no automatic equivalent; rewrite as a WITH<br>RECURSIVE CTE. Original | _(rationale pending)_ |
| <a id="unique-1135"></a>`UNIQUE-1135` | statement | session-variable SELECT INTO has no cross-dialect equivalent; rewrite as the target's assignment<br>form. Original | _(rationale pending)_ |
| <a id="unique-1136"></a>`UNIQUE-1136` | statement | INSERT combines RETURNING and ON CONFLICT; rewrite as MERGE/upsert with result capture on {dialect}.<br>Original | _(rationale pending)_ |
| <a id="unique-1138"></a>`UNIQUE-1138` | statement | Oracle has no UPDATE … FROM (rewrite with a correlated subquery or MERGE) and no top-level<br>RETURNING. Statement preserved as a comment | _(rationale pending)_ |
| <a id="unique-1140"></a>`UNIQUE-1140` | statement | MySQL has no RETURNING/OUTPUT; the statement returned: {cols} | _(rationale pending)_ |
| <a id="unique-1141"></a>`UNIQUE-1141` | statement | MERGE WHEN NOT MATCHED DO NOTHING has no faithful rewrite; reason carried at runtime | _(rationale pending)_ |
| <a id="unique-1142"></a>`UNIQUE-1142` | statement | MERGE clause has no faithful rewrite; reason carried at runtime | _(rationale pending)_ |
| <a id="unique-1143"></a>`UNIQUE-1143` | statement | T-SQL has no FOR UPDATE/FOR SHARE row-lock clause; lock the rows with a WITH (UPDLOCK, ROWLOCK)<br>table hint | _(rationale pending)_ |
| <a id="unique-1144"></a>`UNIQUE-1144` | statement | Unhandled … | _(rationale pending)_ |
| <a id="unique-1145"></a>`UNIQUE-1145` | statement | inline INDEX table element has no {dialect} equivalent form; index omitted — queries run unindexed.<br>Original: … | _(rationale pending)_ |
| <a id="unique-1146"></a>`UNIQUE-1146` | statement | PostgreSQL EXCLUDE constraint has no {dialect} equivalent; enforce the exclusion with a trigger.<br>Original: … | _(rationale pending)_ |
| <a id="unique-1147"></a>`UNIQUE-1147` | statement | {dialect} requires an explicit type for the generated column {col_name}; original computed column: … | _(rationale pending)_ |
| <a id="unique-1149"></a>`UNIQUE-1149` | expression | UNPIVOT has no {dialect} equivalent and the source columns are not visible to rewrite it as UNION<br>ALL — see docs/03-unsupported.md | _(rationale pending)_ |
| <a id="unique-1150"></a>`UNIQUE-1150` | expression | PIVOT has no {dialect} equivalent and the source columns are not visible to rewrite it as<br>conditional aggregation — see docs/03-unsupported.md | _(rationale pending)_ |
| <a id="unique-1153"></a>`UNIQUE-1153` | procedural | PostgreSQL trigger function ('RETURNS TRIGGER') has no … equivalent (no trigger functions; the body<br>belongs to a CREATE TRIGGER). The non-portable translation is commented out below for review | _(rationale pending)_ |
| <a id="unique-1154"></a>`UNIQUE-1154` | procedural | inline table-valued function ('RETURNS TABLE') has no direct equivalent. …. | _(rationale pending)_ |
| <a id="unique-1155"></a>`UNIQUE-1155` | procedural | trigger reads the T-SQL inserted/deleted pseudo-tables in a set-based way … cannot express; the<br>translation is preserved commented out for a manual rewrite | _(rationale pending)_ |
| <a id="unique-1156"></a>`UNIQUE-1156` | procedural | Oracle COMPOUND TRIGGER … (… {events} ON …) has no automatic … equivalent — it collects affected<br>rows in a PL/SQL collection and re-aggregates in AFTER STATEMENT. Rewrite manually (PostgreSQL: a<br>statement-level trigger with REFERENCING NEW TABLE; MySQL: a row-level trigger that re-reads the<br>table). | _(rationale pending)_ |
| <a id="unique-1157"></a>`UNIQUE-1157` | procedural | PostgreSQL statement-level trigger delegating to a trigger function has no … equivalent (no<br>transition tables / trigger functions). Original binding | _(rationale pending)_ |
| <a id="unique-1158"></a>`UNIQUE-1158` | procedural | {header} LOOP … has no … equivalent (no array type); statement preserved as a comment | _(rationale pending)_ |
| <a id="unique-1159"></a>`UNIQUE-1159` | procedural | PRAGMA … has no … equivalent; dropped. | _(rationale pending)_ |
| <a id="unique-1160"></a>`UNIQUE-1160` | procedural | anonymous PL/SQL block has no top-level … equivalent; preserved below | _(rationale pending)_ |
| <a id="unique-1162"></a>`UNIQUE-1162` | procedural | notice has no output channel inside a MySQL function; message kept in @uq_notice | _(rationale pending)_ |
| <a id="unique-1163"></a>`UNIQUE-1163` | procedural | original RAISERROR/THROW severity/state args dropped: {rest} | _(rationale pending)_ |
| <a id="unique-1164"></a>`UNIQUE-1164` | procedural | BEGIN TRANSACTION dropped -- … starts a transaction implicitly | _(rationale pending)_ |
| <a id="unique-1165"></a>`UNIQUE-1165` | procedural | WAITFOR TIME '…' has no … equivalent (wait until an absolute time | _(rationale pending)_ |
| <a id="unique-1166"></a>`UNIQUE-1166` | procedural | FETCH {direction} has no … equivalent (cursors are forward-only); statement preserved as a comment | _(rationale pending)_ |
| <a id="unique-1167"></a>`UNIQUE-1167` | procedural | FETCH without INTO — … requires target variables (the source discarded the fetched row); preserved<br>as a comment | _(rationale pending)_ |
| <a id="unique-1168"></a>`UNIQUE-1168` | procedural | GOTO … dropped -- … has no GOTO; control flow not replicated (docs/03-unsupported.md | _(rationale pending)_ |
| <a id="unique-1169"></a>`UNIQUE-1169` | procedural | label … dropped -- … has no GOTO/label (docs/03-unsupported.md | _(rationale pending)_ |
| <a id="unique-1170"></a>`UNIQUE-1170` | procedural | could not translate; preserved for review | _(rationale pending)_ |
| <a id="unique-1171"></a>`UNIQUE-1171` | procedural | procedural statement preserved as a comment; reason carried at runtime | _(rationale pending)_ |
| <a id="unique-1172"></a>`UNIQUE-1172` | procedural | GOTO … dropped -- MySQL has no GOTO; control flow not replicated (docs/03-unsupported.md | _(rationale pending)_ |
| <a id="unique-1173"></a>`UNIQUE-1173` | procedural | label … dropped -- MySQL has no GOTO/label (docs/03-unsupported.md | _(rationale pending)_ |
| <a id="unique-1174"></a>`UNIQUE-1174` | procedural | Oracle implicit cursor FOR-loop expanded to an explicit MySQL cursor. -- Declare one variable per<br>selected column and complete the FETCH INTO list. DECLARE {done} INT DEFAULT FALSE; DECLARE {cur}<br>CURSOR FOR {cursor_str}; DECLARE CONTINUE HANDLER FOR NOT FOUND SET {done} = TRUE; OPEN {cur};<br>{variable}_loop: LOOP …FETCH {cur} INTO /* col1, col2, ... */; …IF {done} THEN LEAVE<br>{variable}_loop; END IF | _(rationale pending)_ |
| <a id="unique-1175"></a>`UNIQUE-1175` | procedural | cursor FOR-loop expanded; loop variables are TEXT (exact column types need --db-url metadata). BEGIN | _(rationale pending)_ |
| <a id="unique-1176"></a>`UNIQUE-1176` | procedural | MySQL has no INSTEAD OF trigger; emitted as BEFORE for review (original was INSTEAD OF, typically on<br>a view). | _(rationale pending)_ |
| <a id="unique-1177"></a>`UNIQUE-1177` | procedural | discarded procedure RETURN value ({val} | _(rationale pending)_ |
| <a id="unique-1178"></a>`UNIQUE-1178` | procedural | dynamic SELECT INTO variable has no direct MySQL form (rewrite the dynamic string to select INTO<br>@session variables); original | _(rationale pending)_ |
| <a id="unique-1179"></a>`UNIQUE-1179` | procedural | trigger reads the T-SQL inserted/deleted pseudo-tables in a set-based way Oracle cannot express (no<br>transition tables — use a compound trigger); the translation is preserved commented out for a manual<br>rewrite | _(rationale pending)_ |
| <a id="unique-1181"></a>`UNIQUE-1181` | procedural | INSTEAD OF trigger aggregates over the inserted/deleted transition table; PostgreSQL INSTEAD OF<br>triggers are row-level only — port by hand (docs/03-unsupported.md | _(rationale pending)_ |
| <a id="unique-1182"></a>`UNIQUE-1182` | procedural | PostgreSQL allows INSTEAD OF only on views; on a table the equivalent is a BEFORE row trigger<br>returning NULL (the original operation is suppressed | _(rationale pending)_ |
| <a id="unique-1183"></a>`UNIQUE-1183` | procedural | BEGIN TRANSACTION dropped -- PostgreSQL manages the routine transaction implicitly | _(rationale pending)_ |
| <a id="unique-1184"></a>`UNIQUE-1184` | procedural | SAVEPOINT{sp} dropped -- PL/pgSQL has no explicit savepoints; wrap the statements in a BEGIN …<br>EXCEPTION block, which rolls back to its start on error (docs/03-unsupported.md | _(rationale pending)_ |
| <a id="unique-1185"></a>`UNIQUE-1185` | procedural | ROLLBACK TO SAVEPOINT {name} dropped -- PL/pgSQL has no explicit savepoints; the enclosing BEGIN …<br>EXCEPTION block rolls back automatically on error (docs/03-unsupported.md | _(rationale pending)_ |
| <a id="unique-1186"></a>`UNIQUE-1186` | procedural | SELECT * INTO multiple variables needs the column list (no schema to expand '*'); statement<br>preserved as a comment | _(rationale pending)_ |
| <a id="unique-1187"></a>`UNIQUE-1187` | procedural | cursor FOR-loop expanded; loop variables are NVARCHAR(4000) (exact column types need --db-url<br>metadata). | _(rationale pending)_ |
| <a id="unique-1188"></a>`UNIQUE-1188` | procedural | SET TRANSACTION {mode} dropped -- T-SQL has no READ ONLY/READ WRITE transaction mode; only ISOLATION<br>LEVEL is expressible (docs/03-unsupported.md | _(rationale pending)_ |
| <a id="unique-1189"></a>`UNIQUE-1189` | procedural | EXECUTE IMMEDIATE USING bindings dropped; inline them or use sp_executesql parameters | _(rationale pending)_ |
| <a id="unique-1190"></a>`UNIQUE-1190` | procedural | verify dynamic SQL placeholders match … | _(rationale pending)_ |
| <a id="unique-1191"></a>`UNIQUE-1191` | procedural | OUTPUT <expr> dropped — populate the temp table manually | _(rationale pending)_ |
| <a id="unique-1192"></a>`UNIQUE-1192` | procedural | ROW_COUNT() counts changed rows, not matched rows like the source (docs/03-unsupported.md | _(rationale pending)_ |
| <a id="unique-1193"></a>`UNIQUE-1193` | procedural | … -- …-only, no … equivalent | _(rationale pending)_ |
| <a id="unique-1194"></a>`UNIQUE-1194` | procedural | {name} has no … equivalent; {hint} | _(rationale pending)_ |
| <a id="unique-1195"></a>`UNIQUE-1195` | procedural | trigger function … inlined into its T-SQL trigger | _(rationale pending)_ |
| <a id="unique-1196"></a>`UNIQUE-1196` | procedural | was T-SQL table variable {name} | _(rationale pending)_ |
| <a id="unique-1197"></a>`UNIQUE-1197` | procedural | SET option is source-only and has no target equivalent | _(rationale pending)_ |
| <a id="unique-1198"></a>`UNIQUE-1198` | procedural | T-SQL system procedure has no … equivalent; original: EXEC … | _(rationale pending)_ |
| <a id="unique-1199"></a>`UNIQUE-1199` | procedural | T-SQL system procedure has no … equivalent; original: {original} | _(rationale pending)_ |
| <a id="unique-1200"></a>`UNIQUE-1200` | procedural | Oracle package call has no … equivalent; original | _(rationale pending)_ |
| <a id="unique-1201"></a>`UNIQUE-1201` | procedural | trigger uses the T-SQL set-based inserted/deleted pseudo-tables, which have no row-level (NEW/OLD)<br>equivalent. Rewrite manually (PostgreSQL: a statement-level trigger with REFERENCING NEW TABLE AS<br>inserted OLD TABLE AS deleted; Oracle: a compound trigger; MySQL: no transition tables). Original | _(rationale pending)_ |
| <a id="unique-1202"></a>`UNIQUE-1202` | procedural | statement uses a table-valued function in FROM, which MySQL does not support; commented out for<br>review | _(rationale pending)_ |
| <a id="unique-1203"></a>`UNIQUE-1203` | procedural | unmapped cursor attribute …%… */ (0 = 1 | _(rationale pending)_ |
| <a id="unique-1204"></a>`UNIQUE-1204` | procedural | no MySQL equivalent: ALTER TRIGGER … … | _(rationale pending)_ |
| <a id="unique-1205"></a>`UNIQUE-1205` | procedural | was T-SQL temp table #{var} | _(rationale pending)_ |
| <a id="unique-1206"></a>`UNIQUE-1206` | procedural | {word} dropped -- the exception-guarded block is a subtransaction (transaction control there is a<br>runtime error); it rolls back on error and commits with the surrounding transaction | _(rationale pending)_ |
| <a id="unique-1208"></a>`UNIQUE-1208` | orchestration | T-SQL CREATE SCHEMA has no Oracle equivalent — an Oracle schema is a database user. Create it<br>manually, e.g. CREATE USER {name} …; original | _(rationale pending)_ |
| <a id="unique-1209"></a>`UNIQUE-1209` | orchestration | Oracle ORGANIZATION INDEX/HEAP is a physical-storage clause with no equivalent here; dropped. | _(rationale pending)_ |
| <a id="unique-1210"></a>`UNIQUE-1210` | orchestration | … -- tsql-only, no {target} equivalent (constraint check-state | _(rationale pending)_ |
| <a id="unique-1213"></a>`UNIQUE-1213` | orchestration | T-SQL default constraint value has no {target} equivalent | _(rationale pending)_ |
| <a id="unique-1214"></a>`UNIQUE-1214` | orchestration | READ COMMITTED is Oracle's default isolation level (no-op; noted so a following SET TRANSACTION mode<br>statement can still open the transaction | _(rationale pending)_ |
| <a id="unique-1215"></a>`UNIQUE-1215` | orchestration | T-SQL has no SET ROLE (use role membership / EXECUTE AS); statement preserved as a comment. | _(rationale pending)_ |
| <a id="unique-1216"></a>`UNIQUE-1216` | orchestration | {target} has no deferred-constraint toggling (SET CONSTRAINTS); statement preserved as a comment. | _(rationale pending)_ |
| <a id="unique-1217"></a>`UNIQUE-1217` | orchestration | SET SESSION AUTHORIZATION has no {target} equivalent; switch users natively. | _(rationale pending)_ |
| <a id="unique-1218"></a>`UNIQUE-1218` | orchestration | PostgreSQL session setting has no {target} equivalent; configure the session natively. | _(rationale pending)_ |
| <a id="unique-1219"></a>`UNIQUE-1219` | orchestration | MySQL session setting has no {target} equivalent; configure the session natively. | _(rationale pending)_ |
| <a id="unique-1220"></a>`UNIQUE-1220` | orchestration | live {target} validation rejected this statement ({first_err}); preserved as a comment | _(rationale pending)_ |
| <a id="unique-1221"></a>`UNIQUE-1221` | orchestration | T-SQL TEXTIMAGE_ON filegroup clause dropped (physical storage, no logical-schema impact) | _(rationale pending)_ |
| <a id="unique-1222"></a>`UNIQUE-1222` | orchestration | T-SQL WITH NOCHECK dropped; the constraint is added and the target validates existing rows (no<br>NOVALIDATE applied) | _(rationale pending)_ |
| <a id="unique-1223"></a>`UNIQUE-1223` | orchestration | session/client directive commented out (no cross-engine equivalent); the directive is session-scoped<br>and the specific statement is carried at runtime | _(rationale pending)_ |
| <a id="unique-1224"></a>`UNIQUE-1224` | orchestration | batch commented out (unrecognized migration-guard shape); the specific batch is carried at runtime | _(rationale pending)_ |
| <a id="unique-1225"></a>`UNIQUE-1225` | statement | existence guard dropped; the guarded statement now runs unconditionally (no conditional form on the<br>target); the specific statement is carried at runtime | _(rationale pending)_ |
| <a id="unique-1226"></a>`UNIQUE-1226` | statement | guard ELSE branch dropped (only a diagnostic PRINT can be carried into the target conditional); the<br>specific branch is carried at runtime | _(rationale pending)_ |
| <a id="unique-1227"></a>`UNIQUE-1227` | ddl | Oracle MODIFY keeps the column's current nullability; the redundant NULL is omitted (an explicit<br>NULL raises ORA-01451 when the column is already nullable) | _(rationale pending)_ |
| <a id="unique-1228"></a>`UNIQUE-1228` | validation | internal: a parsed sqlglot construct was not consumed by the converter (unread arg) — the construct<br>may be dropped; the specific arg is carried at runtime | _(rationale pending)_ |
| <a id="unique-1229"></a>`UNIQUE-1229` | validation | DML transpilation failed (internal error); the source statement is preserved as a comment; the error<br>is carried at runtime | _(rationale pending)_ |
| <a id="unique-1230"></a>`UNIQUE-1230` | procedural | procedural parse note; the specific reason is carried at runtime | _(rationale pending)_ |
| <a id="unique-1231"></a>`UNIQUE-1231` | procedural | procedural transformation note; the specific reason is carried at runtime | _(rationale pending)_ |
| <a id="unique-1232"></a>`UNIQUE-1232` | procedural | procedural transpilation failed (internal error); the routine is preserved; the error is carried at<br>runtime | _(rationale pending)_ |

233 codes across 6 categories (33 with a rationale).
