# Unique — Pending Work

This document tracks **outstanding** work, ordered by priority. Completed work
has been archived in [`docs/DONE.md`](DONE.md) (with the detailed why/how of
each fix); `docs/STATUS.md` summarizes the project state at a higher level.

Last reviewed: 2026-07-08. The functional-equivalence and 2026-07-02
audit-remediation backlogs are complete and archived in [`docs/DONE.md`](DONE.md)
(§18); source-syntax validation across core/API/web/CLI shipped (§34). The
**2026-07-08 follow-up audit** ([`audit/2026-07-08/`](../audit/2026-07-08/))
verified all 14 previous functional bugs fixed and opened the backlog below.

## Legend

- **P1** — high impact, appears frequently in real schemas
- **P2** — medium impact, common but not blocking
- **P3** — lower impact / niche

---

## 1. Oracle procedural output — validity backlog (P1) — ✅ DONE (26 -> 0)

**Complete.** The T-SQL procedures fixture (32 objects) now transpiles to
**fully-valid Oracle** — `test_procedures_fixture_is_valid_live[oracle]` asserts it
(the `xfail` is gone). The Oracle live-validator queries `USER_ERRORS` after each
`CREATE` (Oracle compiles PL/SQL *lazily*, so `CREATE` succeeds even for an invalid
body) and recompiles to settle forward dependencies. Detailed why/how of each fix
is archived in [`docs/DONE.md`](DONE.md); the arc, in brief:

- **Expression/type:** string-`+` -> `||`; subquery / CAST assignments and RETURNs
  are SQL-only in PL/SQL, so via `SELECT … INTO v FROM DUAL` (or a nested block);
  `SELECT TOP (n)` -> `FETCH FIRST`; CLOB/`SQL_VARIANT` -> bounded `VARCHAR2`;
  `TRY_CAST`/`SHA256`/`EXTRACT(EPOCH …)`/`VARCHAR(MAX)`-cast/character-CAST length;
  `DATEDIFF` sub-day + canonical layout; `TIME_STR_TO_TIME` unwrap.
- **Structure (features):** bare result `SELECT` -> `SYS_REFCURSOR` OUT; `EXEC
  sp_executesql` -> `EXECUTE IMMEDIATE … USING`; **table variable -> hoisted GTT**;
  **trigger DECLARE section**; **reassigned IN parameters shadowed with locals**;
  **inline split TVF -> `SYS.ODCIVARCHAR2LIST` function** + `TABLE(fn(…))` callers.
- **Rules:** OUT/IN OUT params take no DEFAULT; procedure/trigger RETURN carries no
  value; no `AS` before a table alias.

## 2. Audit 2026-07-08 follow-ups

Findings from [`audit/2026-07-08/02-new-findings.md`](../audit/2026-07-08/02-new-findings.md)
(reproductions and mechanism analysis there).

### P1 — silent semantic changes (no-silent-loss violations)

- [ ] **Residual invalid output ships WITHOUT a warning (P1, analyzed
      2026-07-17).** The archived wave campaign left ~550 statements
      across the six directions that the live engines reject; behavior
      audit of pg→tsql's 163: **21 are VERBATIM passthroughs of the
      source SQL with ZERO warnings** (e.g. `SELECT CORR(b, a)` — CORR
      is a known-foreign builtin deliberately left visible, but
      silently; `ALTER TABLE … SET (parallel_workers = 4)` — a PG
      storage knob shipped raw), and 142 are transformed-but-invalid
      forms that pass the sqlglot-based output gate because sqlglot is
      more lenient than the real engines. Neither violates data, but
      both violate the no-silent-loss policy: invalid output must
      carry a warning or degrade to a carrier. **Treatment design
      (three mechanisms, ordered by cost):**
      1. *Unmapped-construct note (LANDED 2026-07-17, wave 103):*
         a RawSQL whose reason is `unmapped operator X` emitted
         cross-dialect now carries an inline `/* UNIQUE: … no
         <target> mapping — review */` note (covers CORR & friends —
         they arrive as unmapped-operator RawSQL, not FunctionCall).
         A FunctionCall-level note was tried and REVERTED: it broke
         the downstream text handlers that consume that output
         (TRUNC→ROUND on the M4 path) — the M3 lesson; rewrite passes
         that fix a construct must also CLEAR the stale reason
         (charset strip updated). Tests: TestForeignBuiltinNote. Verified at
         `fd2923f`: validity identical {163/131/89}, notes visible
         in output. Mechanisms 2–3 below remain open.
      2. *Verbatim-fallback warning — VERIFIED ALREADY COVERED
         (2026-07-17):* the DML parse-fallback path already carriers
         + warns (probe: `SELECT 1 INTO STRICT v` → carrier with
         warning). The probe instead exposed a silent-MANGLE class:
         PG's `TABLE name` shorthand shipped as `[TABLE] AS onek`
         (wave 104 fixed it — pre-normalized to `SELECT * FROM
         name`). The remaining silent classes are all
         sqlglot-leniency escapes → mechanism 3. (Wave 104 verified
         at `b400247`: validity flat, mangle gone.)
      3. *Live output validation, opt-in — LANDED 2026-07-17
         (wave 105):* `TranspileOptions.validate_live_url` +
         `core/live_validate.py`. Side-effect free per engine (T-SQL
         PARSEONLY, PG savepoints, MySQL throwaway DB; Oracle raises
         UnsupportedLiveValidationError — no side-effect-free channel
         without DBA rights). Applies the SWEEP'S classification:
         only syntax-class engine errors degrade (environmental
         missing-table errors on the validation DB must not carrier
         good SQL). Smoke-verified against live PG: syntax rejects
         carrier with the engine's error + a `live_validation`
         warning; environmental pass untouched. Oracle channel via
         `DBMS_SQL.PARSE` (syntax+semantics, no execute) added
         2026-07-17 — DML/SELECT only; DDL skipped (Oracle runs DDL
         at parse). **BLIND SPOT (user, 2026-07-17): live validation
         catches INVALID output, NOT silent data loss — a statement
         that dropped a clause/arm/row but stays syntactically valid
         PASSES (wave 85 class). It is NEVER the sole check; it
         complements the no-silent-loss gates, differential audits,
         and review of what each degrade drops.** Tests:
         TestLiveOutputValidation (env-gated). **Live-in-sweep gap
         discovery (user, 2026-07-17): a discovery script ran the
         corpus through the Transpiler + live PG validation, keeping
         only statements the ENGINE rejects that shipped with NO
         carrier/warning — 58 silent gaps. Top: `CAST(… AS ARRAY)`
         (11x — a PG array-type cast `'{…}'::float8[]` collapsed to
         a bare ARRAY, invalid even PG→PG; wave 106 preserves the
         array type and widens the array gate to Oracle, excluding
         WITHIN GROUP which Oracle supports). The discovery tool is committed
         (`scripts/discover_silent_gaps.py`) — MUST use the
         dollar-quote-aware splitter (a naive `;\n` split shreds
         plpgsql bodies into false-positive `return …` fragments —
         verified). Proper run over the whole corpus (5196 stmts):
         **287 silent gaps**. Wave 107 fixed the worst — a genuine
         SILENT DATA LOSS the live check exposed: `CREATE TABLE x
         (LIKE y)` (LIKE inside the column parens) dropped its LIKE
         entirely → empty `CREATE TABLE x` (the LikeProperty lands in
         the schema, not properties; now harvested from both).
         Remaining tail: `ARRAY(...)` constructor (9x, distinct from
         the cast), VARIADIC ARRAY, PERCENTILE_*(ARRAY …) — genuine
         array constructs with no non-PG spelling (degrade candidates
         for a future wave). Wave 108 (2026-07-16) closed that tail
         and found it was worse than a degrade gap — the IR had NO
         array model, one class, three defects: (a) sqlglot stores PG
         subscripts 0-BASED and the unhandled-expression RawSQL
         fallback rendered with NO dialect, so `arr[2]` shipped as
         `arr[1]` — silent data corruption, and on pg→tsql it even
         passed the validity gate (brackets parse as a quoted
         identifier) with ZERO warnings; (b) `ARRAY[…]` collapsed to a
         generic FunctionCall emitted `ARRAY(1, 2, 3)` — invalid even
         on PG; (c) the ARRAY(SELECT …) carrier leaked the IR repr
         instead of SQL. Fixes: `ArrayLiteral` IR node (PG emits
         `ARRAY[…]`/`ARRAY(SELECT …)` faithfully), ALL converter
         RawSQL fallbacks now render in the SOURCE dialect
         (`_source_sql`: unhandled expr, complex EXISTS/subquery,
         unmodeled INSERT body, unhandled CREATE, unmapped operator),
         and the array gate recognizes the node, subscripts
         (Bracket-RawSQL), and any RawSQL fragment carrying `ARRAY[`
         (neighbor probe caught `= ANY(ARRAY[…])` escaping via the
         unmapped-operator path; a WITHIN GROUP fragment with an
         ARRAY arg now degrades on oracle too, plain WITHIN GROUP
         stays). Tests: TestArrayModelFidelity (18). Measured
         (whole-corpus discovery, working tree over `f3c07d9`):
         **287 → 226 silent gaps (−61)**. Next-wave candidates from
         the new top classes (all silent-loss shapes): set-returning
         function dropped from FROM in LATERAL contexts (`FROM
         generate_series(…) s1` → `FROM  s1`), `DROP TRIGGER … ON
         table` losing the ON clause, CTAS over a parenthesized UNION
         subquery truncating (`syntax error at end of input`, 99x),
         and — verified distinct from this wave's DML class — the
         PROCEDURAL pipeline shreds plpgsql array-typed declares
         pg→pg (`a integer[] = '{…}'` → `a integer;` + garbage `[]
         =;` line; `RETURNS SETOF integer[]` silently narrows to
         `SETOF integer`) — the pg→pg preservation counterpart of
         wave 86's off-PG degrade (6x, the remaining `"["` gaps).
         Wave 108b: the live FE suite caught a wave-108 REGRESSION —
         source-dialect fallback rendering is wrong INSIDE procedural
         bodies, where embedded text is mid-transform (variables
         already `@`-rewritten): a postgres render turned
         `@p_customer_id` into the invalid `$p_customer_id` on
         T-SQL. `IR_EMBEDDED` ContextVar (set around
         `_ir_transpile_dml`) keeps the generic rendering there;
         top-level parses stay source-spelled. All 16 FE pairs
         re-verified live-green. Lesson for the structural list: a
         "render faithfully to the source" rule only holds where the
         text IS source — the procedural pipeline's embedded text is
         a hybrid. Tests: TestEmbeddedFallbackSpelling. Wave 109
         (2026-07-16): `DROP TRIGGER name ON tbl` lost its mandatory
         ON even pg→pg (sqlglot parks it in the unread `cluster` arg
         — the DROP INDEX lesson again); now harvested for TRIGGER
         too, PG emits it, and the inverse neighbor (tsql/mysql/
         oracle sources are schema-scoped, no table to carry)
         degrades to the documented carrier instead of shipping
         invalid PG silently. Known honest limit: `ON schema.tbl`
         doesn't parse in sqlglot (carrier + warning, not silent).
         Tests: TestDropTriggerOnTable (7). Measured: **226 → 156
         silent gaps (−70)** (working tree over `45edfa2`; the
         DROP TRIGGERs were most of the 99x end-of-input class).
         Remaining top classes: FROM-position set-returning function
         dropped (`FROM generate_series(…) g` → `FROM g`, the
         biggest remaining silent DATA LOSS — needs a
         function-relation model in the IR, fresh-session scale),
         psql client-side leftovers (25x near ":"), `WITH ins AS
         (INSERT … RETURNING)` mangled to `SELECT *` (14x), plpgsql
         array-typed declare shred (6x, above). Waves 110–111
         (2026-07-16): the function-relation model landed —
         `TableRef.function` (+`ordinality`) carries the SRF,
         harvested from `Table(this=<func>)` in FROM/JOIN position
         and from bare `Unnest` relations; PG re-emits `fn(args)
         [WITH ORDINALITY] [AS a(c…)]` faithfully; unnest relations
         still degrade off-PG via the array gate (it sees the
         FunctionCall by field recursion); sqlglot's internal
         `ExplodingGenerateSeries` canonicalizes to GENERATE_SERIES.
         Wave 110 alone measured FLAT (157) — green-but-unmoved
         fired: those statements were blocker CHAINS, and preserving
         the SRF exposed the next link — comma-joined LATERAL
         emitted `JOIN LATERAL (…) ss` with NO ON (invalid PG that
         sqlglot's lenient gate passes). Wave 111 spells an
         unconditioned inner lateral `CROSS JOIN LATERAL`. Together:
         **156 → 122 silent gaps (−34)** (working tree over
         `6bbf102`; end-of-input 29→4, near-WHERE class gone).
         Tests: TestFunctionRelations (7), TestCommaLateralJoin.
         Wave 112 (2026-07-16): the procedural lexer tokenized `::`
         as two COLON tokens and the joiner spaced them —
         `relname::text` shipped as the invalid `relname : : text`
         inside converted routine bodies (the 25x near-":" discovery
         class, plus 4x live on the pg→tsql sweep). `::` is now ONE
         OPERATOR token (PG accepts spaced `x :: text`); Oracle
         `:new`/`:old` single-colon refs unaffected. Tests:
         TestDoubleColonCastInBodies. Gate green; **discovery/sweep
         re-measurement PENDING** (host RAM upgrade in progress —
         resume by re-running `scripts/discover_silent_gaps.py`
         [expect ≈122−~25] and the full validity sweeps of BOTH
         corpora, which were last measured at `3fdfc88` wave ~102;
         a pg→tsql sweep at `5aed9ee` ran but its summary was lost
         to a `tail` pipe — DON'T pipe sweep output). MEASURED
         post-upgrade (2026-07-16, 31GiB host, all four engines
         parallel): discovery pg→pg **122 → 98** (−24, the ":"
         class gone as predicted). Full sweeps at `314f7c6`:
         pg-source {tsql **153** (95.4%), mysql 246→see 113, oracle
         **79** (97.5%)}; mysql-source {tsql **171** (97.1%), pg
         **105** (98.3%), oracle **129** (97.8%)} — pg-source beats
         the wave-102 record {163/131/89} across the board;
         mysql→tsql +5 vs record (166), unclassified, likely the
         SRF-honesty class. Wave 113 (2026-07-16): wave 110's
         preserved SRF relations surfaced the target truth — MySQL
         has NO table functions except JSON_TABLE (`FROM
         generate_series(…) g` = hard 1064, 243x, previously hidden
         as an expected-missing bare alias): new
         `_gate_mysql_function_relation` degrades WHOLE with
         carrier+warning (JSON_TABLE keeps its path); Oracle now
         spells a function relation `TABLE(fn(args)) alias`.
         Verified: pg→mysql **121** (96.0%, beats the 131 record);
         pg→oracle flat 79. Tests: TestFunctionRelationTargets.
         Wave 114 (2026-07-16): a data-modifying CTE (`WITH ins AS
         (INSERT … RETURNING) SELECT …`, PG-only) had its DML body
         SHREDDED into a `SELECT *` skeleton by `_convert_cte`
         (silent loss of the INSERT/DELETE itself). Now routed
         through the existing CTE-DML passthrough: preserved pg→pg,
         degraded whole with the documented carrier elsewhere (the
         DML-inside-CTE check runs BEFORE the helper's T-SQL
         early-out, which covers the inverse update-through-CTE
         shape). Measured: discovery **98 → 86** (−12; 'SELECT *
         with no tables' 15→3). Tests: TestDataModifyingCte.
         Wave 115 (2026-07-16): the plpgsql DECLARE parser stopped
         at the first unknown token and SHREDDED the declaration —
         one mechanism, four sub-shapes now consumed: `CONSTANT`
         (kept on PG/Oracle, safe mutable relaxation on T-SQL/MySQL,
         documented in 03-unsupported §1.5), `[NO] SCROLL CURSOR`
         (kept on PG; T-SQL SCROLL native, replaces FAST_FORWARD),
         `[]` array suffixes in DECLARE (via `_parse_pg_data_type`,
         closing the 6x `[` class), and `RETURNS SETOF type[]` no
         longer narrowing (pg-aware inner parse). Measured:
         discovery **86 → 81** (−5: `[` −6 and `data type` −3
         cleared, but the 14x `;` class has ANOTHER sub-mechanism —
         re-sampling — and un-shredded routines exposed new chain
         links: INTO 2→4, 'RETURN cannot have a parameter' 2x).
         Tests: TestPlpgsqlDeclareModifiers (6).
         Wave 116 (2026-07-16): `OPEN c [NO] SCROLL FOR [EXECUTE …]`
         — the OPEN parse stopped at the cursor name, shipping
         `scroll for execute '…';` as an ORPHAN statement.
         CursorOperation gains `scroll`; the dynamic `FOR EXECUTE`
         form is preserved verbatim; PG re-emits both (T-SQL keeps
         scrollability on its DECLARE; Oracle/MySQL forward-only).
         Measured: discovery **81 flat** — the wave's own classes
         cleared ('FOR' 3→0, orphans gone) but chains absorbed the
         delta (INTO 4→7). The 14x ';' class STILL unmoved after two
         waves → two-strikes fired: next step is an end-to-end trace
         of one real tg_* corpus function, not another sub-shape
         guess. Tests: TestOpenCursorScrollExecute (3).
         Wave 117 (2026-07-16): the trace found it first try — the
         tg_* corpus functions declare `myname ALIAS FOR $1;`, which
         shredded into `myname alias;` + orphan `for p1;`. Faithful
         translation on EVERY target: token-level rename of the
         alias to its target (the $n positional-aliasing mechanism);
         the declaration vanishes. Measured: discovery **81 → 78**
         (`;` 14→11 — the rest of that class are further sub-shapes,
         next trace needed). Tests: TestAliasForDeclaration (2).
         Wave 118 (2026-07-16): FETCH directions — `FETCH NEXT|LAST|
         ABSOLUTE n … FROM c INTO x` took the DIRECTION as the cursor
         name (`FETCH next INTO ;` + orphan). A word is a direction
         only when FROM/IN follows, so cursors named `last` still
         work; native re-emit on PG and T-SQL, documented carrier on
         Oracle/MySQL (forward-only). Found+fixed en route: the
         shared `_transform_cursor_op`/`_transform_cursor_decl`
         REBUILT their nodes field-by-field, silently dropping any
         field they didn't know (scroll, direction) — now
         dataclasses.replace; that trap ate wave 116's scroll on
         every transformed route. Measured: discovery **78 → 72**
         (INTO class gone). Sweeps at `63de504`: pg→tsql **145**
         (95.6%), pg→mysql **118** (96.1%), pg→oracle **77** (97.6%).
         Tests: TestFetchDirections (4).
         Wave 119 (2026-07-16): plpgsql's bare re-`RAISE;` emitted the
         invalid `RAISE EXCEPTION '%', ;` and `RAISE USING key = expr`
         mangled — both fell into the generic expression fallback. New
         `reraise` flag (native everywhere: PG/Oracle `RAISE;`, T-SQL
         `THROW;`, MySQL `RESIGNAL;`); USING's `message` option IS the
         message, other options fold into the text. The rebuild trap
         hit AGAIN en route (`_transform_raise_error` dropped the new
         flag) — fixed with dataclasses.replace like wave 118's.
         Measured: discovery **72 → 68** ('missing expression' class
         gone). Tests: TestBareRaiseAndUsing (5).
         Wave 120 (2026-07-16): plpgsql `FOREACH var [SLICE n] IN
         ARRAY expr LOOP … END LOOP` modeled (ForeachStatement):
         preserved pg→pg with a transformed body, documented carrier
         elsewhere (the array-body routine degrade usually fires
         first off-PG). Measured: discovery **68 flat** but the
         composition moved — `;` 11→5 (the FOREACH shreds cleared)
         and `[` REAPPEARED at 5x: un-shredding the loops exposed
         their bodies (array subscripts in plpgsql assignment
         contexts, being re-sampled). Chains, as ever. Tests:
         TestForeachArrayLoop (5). Wave 120b: the '[' 5x was my own
         wave-120 emit (a Python list repr interpolated into the loop
         body — the wave tests only checked header/END LOOP;
         strengthened). 68 → 63. Waves 121–122 (2026-07-16):
         plpgsql's EXECUTE is ALWAYS dynamic (CALL is spelled CALL) —
         the SQL*Plus exec-call fallthrough mangled `EXECUTE 'q' INTO
         STRICT x` into `CALL 'q'();` (8x): new `_parse_pg_dynamic_
         execute` with INTO [STRICT] + USING, PG re-emits natively
         (ExecuteStatement.strict). And a `LANGUAGE C` function
         (`AS '$libdir/…'`) emitted an EMPTY plpgsql function —
         silent loss of the implementation reference: non-SQL-language
         units (C/internal/plperl…) now capture whole
         (`_pg_non_sql_language_ahead` + `_whole_unit_raw`), ship
         VERBATIM same-dialect and carrier+warning cross-dialect (the
         transformer decides — it knows both ends). Measured:
         discovery **63 → 48** (−15). Tests: TestPgDynamicExecute
         (3), TestNonSqlLanguageFunction (4). Wave 123
         (2026-07-16): `SAVEPOINT a` mis-parses in SQLGLOT ITSELF as
         an Alias (`SAVEPOINT AS a` even in its own round-trip) —
         pre-recognized in parse_sql (the `TABLE name` precedent) as
         a PassthroughSQL kind: same spelling on PG/MySQL/Oracle,
         `SAVE TRANSACTION` on T-SQL (+ output-gate reparse exemption
         — sqlglot's tsql reader can't read that valid spelling
         either, the DELETE…OUTPUT lesson). Measured: **48 → 45**.
         Tests: TestSavepointStatement (4). Wave 124 (2026-07-16):
         PG's empty select list (`SELECT;`, zero columns one row)
         silently gained a `*` — invalid without FROM, shape-changing
         with one. `SelectStatement.empty_select_list` flag set only
         for genuinely-empty SOURCE lists (converter-fallback empty
         tuples keep their load-bearing `*` default); PG re-emits the
         bare SELECT, other targets gate to the carrier. Measured:
         **45 → 42**. Tests: TestEmptySelectList (6). Wave 125
         (2026-07-16): PG's TRUNCATE trigger event was unrecognized —
         the whole trigger shredded into garbage declarations.
         Recognized on PG (event list + upper_value, TRUNCATE isn't a
         lexer keyword); degraded whole via `_transform_trigger` on
         targets without the event (the `_degrade_mysql_uservar`
         recipe: re-emit in source + carrier + registry). Measured:
         **42 → 36** (FUNCTION and ON classes cleared). Tests:
         TestTruncateTrigger (4).* Wave 126 (2026-07-16): plpgsql
         `<<label>>` block labels (and their label-qualified variable
         refs) are unmodeled — the declare loop shredded them into
         `< <; label >; >` garbage. Detected BEFORE the body splice
         (the body is still one STRING token there — post-splice the
         label is token soup); verbatim on PG via the wave-122
         whole-unit path, carrier elsewhere. Measured: **36 → 34**
         (`<` class gone). Tests: TestPlpgsqlBlockLabel (4).
         Waves 127–128 (+127b, 2026-07-16): CTE fidelity — RECURSIVE
         and the column list `x(a)` were never harvested (fields
         existed, unset) and a VALUES body mangled to a one-row
         SELECT (now the FROM-relation UNION-chain converter);
         `CREATE TEMP TABLE` lost TEMPORARY even pg→pg (now
         harvested: TEMPORARY on pg/mysql, GLOBAL TEMPORARY on
         oracle, dropped-with-#-semantics note on tsql) and
         zero-column `CREATE TABLE x()` keeps its parens on PG /
         gates elsewhere. 127b: the sweep VERIFICATION caught my own
         regression (145→178 on tsql) — RECURSIVE is REQUIRED on
         pg/mysql and DOESN'T EXIST on tsql/oracle; now per-dialect.
         ALSO fixed the 32GiB OOM (user-reported): the PG validator
         (savepoint+execute) began EXECUTING the perf-test SRFs the
         moment the transpiler stopped breaking them — millions of
         rows buffered client-side; `statement_timeout=3000` in the
         validation session (a canceled statement is not
         syntax-class → no gap). MEASUREMENT POLICY: sequential, max
         2 python processes (the OOM was 4 parallel measurements).
         Measured: discovery **34 → 31** (end-of-input cleared);
         sweeps pg→tsql **132** (96.0%), pg→mysql **109** (96.3%),
         pg→oracle **65** (97.9%). Tests: TestCteFidelity,
         TestTempAndZeroColumnTables, TestRecursiveCtePerDialect.
         Waves 129–130 (2026-07-16): a set arm carrying its own WITH
         lost its parens (`UNION ALL WITH z …` invalid); a
         parenthesized CHAIN arm — `A UNION (B UNION ALL C)` — is now
         SHIELDED as a derived table (flattening RE-ASSOCIATED the
         row set: INTERSECT binds tighter than UNION — an old wave-85
         test had the wrong flat form CONSECRATED and was
         strengthened, not weakened); `..` FOR-ranges are ONE lexer
         token (the `::` twin — shipped `0 . . n`); plpgsql
         `#option` compiler lines go whole-unit (valid PG, shredded
         before). Measured: discovery **31 → 20** (WITH/#/0/UNION
         classes cleared). Tests: TestSetArmWithCte, TestWave130Batch,
         strengthened TestNestedChainMidOrderStrip.
         Wave 131 (2026-07-16), five shapes: VARIADIC is an ARGMODE
         (parsed as the param NAME, every `$1` body alias became
         `variadic`); `NOT NULL` declare modifier (the wave-115
         family, PG/Oracle native + tsql/mysql relaxation);
         a VALUES set-op arm (`(VALUES …) UNION ALL …`) now lowers
         via the relation converter; `TABLE name` with a LEADING
         COMMENT escaped the wave-104 pre-normalization (comments are
         trivia — regex now tolerates them); mapped BIT(n) shipped
         `BOOLEAN(4)` (BOOLEAN never takes params). Measured:
         **20 → 13**. Tests: TestWave131Batch (5). Wave 132
         (2026-07-16): SETOF sql-bodies wrap as `RETURN QUERY …`
         (the scalar `RETURN (…)` is invalid there); PG's `ALTER
         COLUMN SET STORAGE` knob — SQLGLOT'S OWN ROUND-TRIP INVENTS
         a `DROP DEFAULT,` before it — pre-recognized with the
         ORIGINAL text (PassthroughSQL kind "PG STORAGE": verbatim
         PG, carrier elsewhere); a dotted unnamed `%TYPE` parameter
         (`f(tbl.col%type)`) took the table as the param NAME
         (dotted first token ⇒ type-only). Measured: **13 → 9**.
         Tests: TestWave132Batch (6). Remaining 9: nested-DECLARE
         shadowing (2, needs block-local declares), dynamic-OPEN
         FETCH chain (2), WITHIN-GROUP-in-CASE view (1), RAISE USING
         variant (1), `return` as a variable name (1), FOREACH
         multi-target (1), transition tables (1). Wave 133
         (2026-07-16) closed ALL NINE: FILTER over an ordered-set
         aggregate (was a fake `WITHINGROUP(CASE…)` call — now the
         source-rendered RawSQL the gates see); `FETCH RELATIVE -n`
         signs; leveled `RAISE EXCEPTION USING key = v` (helper
         shared with wave 119's level-less form); FOREACH
         comma-targets; and three deep singles via the whole-unit
         path with NARROW body-shape regexes (nested DECLARE block,
         a variable literally named `return` with initializer, CTE
         feeding SELECT INTO — first regex draft broke 44 tests by
         matching plain `return x;`, calibrated). **DISCOVERY
         pg→pg = 0 SILENT GAPS (from 287)** — the fixtures-corpus
         no-silent-loss goal for the discovery channel is COMPLETE:
         every statement transpiles validly or carries a
         warning/carrier. Tests: TestWave133Batch (6). Direction-residue
         campaign opened (wave 134, 2026-07-16): a WITH inside a
         set-operation arm (valid PG/MySQL-8 after wave 129) has no
         T-SQL/Oracle spelling (CTEs are statement-top only) —
         `_gate_nested_cte_arm` degrades whole there. Measured:
         pg→tsql **122 → 118** (96.4%), discovery HOLDS at 0.
         Remaining tsql classes (sweep at `de81b44`): non-boolean
         WHERE 8x, near-SELECT 8x, `,` 7x, `(n.*)` star 5x, OLD
         pseudo-rows 5x, boolean-agg NOT 3x, DECODE 3x, set role 3x,
         AS 3x, OUTPUT-in-function 3x, E-strings 3x.
         Tests: TestNestedCteArmGate (3). Wave 135
         (2026-07-16): PG boolean truthiness under the condition
         TREE — a bare column/function/subquery under AND/OR (and
         `NOT col`) shipped bare to T-SQL/Oracle (4145); only the
         top-of-WHERE case was comparisonized. Extended
         `_comparisonize_literals` + `_emit_condition`. Measured:
         pg→tsql **118 → 116** (96.4%), pg→oracle **65 → 61**
         (98.1%), discovery HOLDS 0. Tests:
         TestBareBooleanConditions (4).* Wave 136 (2026-07-16): the
         nested-CTE gate generalizes to ANY non-top WITH (set arms,
         derived tables, APPLY/lateral subqueries, CTE bodies) —
         with the INSERT-source exemption (that CTE is hoistable and
         the emitter already hoists it; the neighbor probe caught the
         over-fire); and a LATERAL join with a REAL ON condition
         degrades on T-SQL/Oracle (APPLY takes no ON — only the
         ON TRUE form maps). Measured: pg→tsql **116 → 100** (96.9%,
         the deep-CTE gate caught double the sampled class),
         pg→oracle **61 → 59** (98.1%), discovery HOLDS 0. Tests:
         TestWave136LateralAndDeepCte (5).* Wave 137 (2026-07-16): PG row
         constructors in VALUE position (`ELSE (a, b, c)` as a CASE
         result / function arg) degrade off PG — detection is
         deliberately NARROW (Tuple-RawSQL under CASE arms or fn
         args, plus the DISTINCT-wrapped text form where the whole
         arg is one RawSQL): the first draft ate the row-tuple
         COMPARISONS that later passes expand (5 tests fired), and
         `ColumnRef('*')` proved ambiguous (legit `n.*` uses it on
         some paths) — the `(n.*)` composite single stays PENDING
         (needs a Paren(Star) marker at conversion). Measured:
         pg→tsql **100 → 97** (97.0%), discovery HOLDS 0. Tests:
         TestCompositeRowValues (5).* Wave 138 (2026-07-16): a BARE
         whole-row OLD/NEW in a trigger body (`'x' || OLD`) has no
         off-PG equivalent (rows are addressed per column there) —
         the inlined T-SQL trigger shipped `+ OLD` raw. The gate
         scans SCRUBBED text (string contents can't false-positive)
         of the trigger shell PLUS the harvested delegated-function
         body (PG triggers delegate; the shell has no body), with
         exclusions for qualified refs, RETURN NEW/OLD and
         REFERENCING new|old TABLE (4 existing tests fired on the
         draft). Measured: pg→tsql **97 → 92** (97.1%), discovery
         HOLDS 0. Tests: TestBareWholeRowTriggerRef (2).* Wave 139 (2026-07-16): PG's
         BINARY `DECODE(text, 'hex')` (2 args — not Oracle's
         conditional DECODE, which becomes CASE at 3+) maps
         faithfully everywhere: `CONVERT(VARBINARY(MAX), x, 2)`
         tsql, `HEXTORAW` oracle, `UNHEX` mysql; and `SET ROLE`
         (real SQL on PG/MySQL/Oracle) carriers on T-SQL only — in
         the SET_OPTION path (the transformer gate drafted first was
         DEAD CODE for that route; the batch classifier short-
         circuits it). Measured: pg→tsql **92 → 87** (97.3%),
         pg→oracle **59 → 56** (98.2%), pg→mysql **109 → 97**
         (96.7%), discovery HOLDS 0. Tests:
         TestWave139DecodeAndSetRole (5).* Wave 140 (2026-07-16):
         `string_agg(x, NULL)` shipped a nonexistent GROUP_CONCAT on
         T-SQL — a NULL separator concatenates bare (`''`) and an
         EXPRESSION separator now stays the target's own argument
         (both fell through the literal-only branch to generic
         emission); and T-SQL's aliased delete is `DELETE dt FROM t
         dt` (`DELETE FROM t dt` is a syntax error). Measured:
         pg→tsql **87 → 83** (97.4%), discovery HOLDS 0. Tests:
         TestWave140GroupConcatAndDeleteAlias (4).* Wave 141 (2026-07-16): boolean
         AND/OR **and unary predicates** (NOT / IS [NOT] NULL /
         EXISTS) in VALUE position — the CASE wrap existed for
         comparisons only; AND/OR wrapped with BARE truthy operands
         (`WHEN b1 AND a3`, 4145) and `(id IS NOT NULL) AS a3`
         shipped bare. Both now route through `_emit_condition`
         (which comparisonizes); two-valued predicates get the exact
         ELSE 0 form. Measured: pg→tsql **83 → 77** (97.6%),
         oracle flat 56, discovery HOLDS 0. Tests:
         TestBooleanOpInSelectList (3),
         TestUnaryPredicateInSelectList (2).* Wave 142 (2026-07-16): a PG
         function with OUT/INOUT params and void-or-INFERRED return
         (`function f1(in i int, out j int)` — PG infers the return
         from OUTs) cannot be a T-SQL FUNCTION (error 181) — it IS a
         procedure there. Measured: pg→tsql **77 → 74** (97.7%),
         discovery HOLDS 0. Tests: TestVoidOutFunctionBecomesProc.* Wave 143 (2026-07-16): PG
         E-strings inside procedural bodies token-split into a bare
         identifier `E` + the literal (`PRINT E 'foo\bar'`, 3x);
         the lexer now DECODES the C-style escapes (\\, \n, octal,
         \x, \u) into a plain single-quoted literal every target
         understands. (Also: a ruff failure hidden by a `| tail`
         pipe — the masked-rc lesson again.) Measured: pg→tsql
         **74 → 71** (97.8%), discovery HOLDS 0. Tests:
         TestEStringsInBodies.* Wave 144 (2026-07-16): a row
         tuple AS a select COLUMN (lateral `SELECT (a, b)`) joins
         the composite gate; and a T-SQL FUNCTION cannot access temp
         tables (2772) — a body creating one degrades whole (the
         wave-138 scan recipe). Measured: pg→tsql **71 → 68**
         (97.9%), discovery HOLDS 0. Tests:
         TestWave144TupleColumnAndTempFn (4).* Wave 145 (2026-07-16):
         MySQL-impossible aggregate forms — an EXPRESSION separator
         (SEPARATOR takes a literal only; the comma form
         CONCATENATES it onto every value — audit S1-8, and my own
         wave-140 dyn-sep emitted the invalid SEPARATOR expr there)
         and DISTINCT inside a non-builtin aggregate (hard 1064;
         arrives both as the flag AND as an Unhandled-Distinct
         RawSQL arg). Both degrade whole on mysql. Measured:
         pg→mysql **97 → 94**, oracle already at **51** (98.4%,
         waves 141-144 side effects), discovery HOLDS 0. Tests:
         TestWave145MysqlAggForms (4).* Wave 146 (2026-07-16): MySQL's
         CAST target set — the DML pipeline maps foreign spellings
         (`_CAST_TYPE_MAP`) but PROCEDURAL expression text shipped
         them raw (`RETURN CAST(p1 AS text)` = hard 1064; the
         dual-pipeline asymmetry classic): `_mysql_cast_types`
         mirror in the mysql fixup family (both sites), outside
         strings. NOTE: per-statement samplers give MISLEADING
         shapes for registry-dependent classes (composite types) —
         the real sweep transpiles the WHOLE file; classify from the
         sweep's own e.g. lines. Measured: pg→mysql **94 → 87**
         (97.0%), discovery HOLDS 0. Tests:
         TestMysqlProceduralCastTypes (2).* Wave 147 (2026-07-16): MySQL
         requires a CONSTANT LAG/LEAD offset — a column offset
         (`LAG(ten, four)`) raises 1327 and has no MySQL spelling;
         degrades whole there. Measured: pg→mysql **87 → 83**
         (97.2%), discovery HOLDS 0. Tests: TestMysqlNonConstLag
         (3).* Wave 148 (2026-07-16): the DML
         cast map covered VARCHAR/NVARCHAR→CHAR but not TEXT — PG's
         habitual cast target shipped `CAST(x AS TEXT)` raw on MySQL
         (the wave-146 procedural mirror had it; the DML side lagged
         — dual-pipeline symmetry cuts BOTH ways). Measured:
         pg→mysql **83 → 78** (97.4%), discovery HOLDS 0. Tests:
         TestMysqlDmlCastText.* Wave 149 (2026-07-16): the
         PG-source PROCEDURAL_TYPE_MAPS **never existed** — internal
         aliases (int2/4/8, float4/8) and PG-only types (TEXT, BYTEA,
         UUID, TIMESTAMPTZ, JSON/B, SERIAL) shipped raw into every
         target's routine signatures. All three maps added, ALIGNED
         with EMIT_TYPE_MAP via the cross-pipeline agreement contract
         (which fired on the first draft: FLOAT4/INT8/TIMESTAMPTZ
         disagreements — Oracle has NO BIGINT, mysql REAL is a
         DOUBLE alias); two tests STRENGTHENED (TEXT now maps to the
         modern large-string type instead of the deprecated raw
         passthrough). Measured: syntax counts flat {68/78/51} BUT
         oracle ok +27 (1749→1776 — correct types moved statements
         from environmental-fail to EXECUTING), discovery HOLDS 0.
         Tests: TestPgSourceProceduralTypeMaps (3).* Wave 150 (2026-07-16): Oracle
         rejects a BARE `*` alongside other select items (ORA-00923,
         13x) — qualified with the FROM relation (`t.*`) at emit.
         Measured: pg→oracle **51 → 38** (98.8%), discovery HOLDS 0.
         Tests: TestOracleBareStarWithSiblings (2).* Wave 151 (2026-07-16): every PG
         table name is also a ROWTYPE — a routine parameter typed
         with one (`function f(t onek)`) is as untranslatable off PG
         as an explicit composite; table names now join the
         composite-type harvest. Measured: pg→mysql **78 → 75**,
         pg→tsql **68 → 67**, discovery HOLDS 0. Tests:
         TestTableRowtypeParams (4).* Wave 152 (2026-07-16): a routine
         parameter typed with a name that resolves NOWHERE (not a
         known scalar/domain/composite/%TYPE) is a rowtype or custom
         type defined OUTSIDE the script (pg_regress setup tables
         like `onek`) — it cannot exist on the target either;
         degrades with a whitelist of known scalar spellings.
         Measured: pg→mysql **75 → 74**, pg→oracle **38 → 35**
         (98.9%), tsql flat 67, discovery HOLDS 0. Tests:
         TestUnknownParamType (4).* Wave 153 (2026-07-16): a row
         tuple compared with ANY/ALL over a subquery arrives as TWO
         source-spelled RawSQL fragments (`BinaryOp(EQ, Tuple-RawSQL,
         Any-RawSQL)` — function maps can't see inside; RANDOM()
         shipped unmapped); STRUCTURAL detection (two regex drafts
         failed: nested parens, then the two-fragment split) joins
         the composite gate. Measured: pg→mysql **74 → 72**,
         pg→tsql **67 → 65** (98.0%), discovery HOLDS 0. Tests:
         TestRowCompareAny (4).* Wave 154 (2026-07-16, mysql-corpus
         front opened): MySQL's REPEAT is T-SQL REPLICATE (it shipped
         dbo.-qualified as a fake UDF) and a 1-arg CONCAT (valid
         MySQL/PG) IS its argument on T-SQL/Oracle. Measured:
         mysql→tsql **167 → 164** — BELOW the 166 campaign record:
         the ⚠+5 anomaly is resolved and beaten (today's shared
         waves −4, this wave −3). Discovery HOLDS 0. Tests:
         TestWave154RepeatConcat (4).* Wave 155 (2026-07-16): MySQL
         truthiness in condition position — a bare numeric literal in
         ``IF(1, …)``/searched ``CASE WHEN 1`` is error 4145 on
         T-SQL/Oracle; ``_emit_condition`` now comparisonizes the
         literal and IIF routes its first argument through condition
         position. Also: pyodbc import-not-found (env driver drift)
         gets the live_validate override treatment. Measured:
         mysql→tsql **164 → 155** (−9). Discovery HOLDS 0. Tests:
         TestWave155ConditionLiterals (5).* Wave 156 (2026-07-16): a MySQL
         routine body that is a single LABELED loop (``proc c(x int)
         hmm: while … end while hmm``) or a bare REPEAT/LOOP has no
         BEGIN — the declare loop shredded it into ``DECLARE @hmm :;``
         garbage. The single-statement no-BEGIN branch now recognizes
         the ``label:`` prefix and identifier-lexed REPEAT/LOOP;
         ITERATE is a modeled ContinueStatement (T-SQL CONTINUE, MySQL
         ITERATE label — it shipped literal ``CONTINUE hmm``).
         Measured: mysql→tsql **155 → 151** (−4). Discovery HOLDS 0.
         Tests: TestWave156LabeledBodyNoBegin (4).* Wave 157 (2026-07-16): MySQL
         lets HAVING reference a select alias — every other engine
         needs the aliased expression inlined (new bottom-up
         ``_inline_having_alias`` + generic ``_map_children`` helper).
         And STRING_AGG(DISTINCT …) has no T-SQL spelling in any form:
         honest whole-statement carrier (``_gate_tsql_agg_distinct``).
         Measured: mysql→tsql **151 → 150** (−1 — the class was
         chain-glued; re-classify next). Discovery HOLDS 0. Tests:
         TestWave157HavingAliasStringAggDistinct (6).* Wave 158 (2026-07-16): MySQL
         labels BEGIN blocks too (``proc i(x int) foo: begin … leave
         foo; … end foo``) — the label shredded into ``DECLARE @foo
         :;`` and LEAVE became a bare BREAK (invalid outside a loop on
         T-SQL). The labeled-statement branch now takes BEGIN, closes
         ``END … label``, and a LEAVE of the body's own label is
         RETURN (MySQL roundtrip re-labels via proc_exit). Measured:
         mysql→tsql **150 → 146** (−4). Discovery HOLDS 0. Tests:
         TestWave158LabeledBeginBlock (3).* Wave 159 (2026-07-16): MySQL
         declares several variables with one type (``DECLARE z1, z2
         int;`` → per-name DeclareStatements in a StatementList) and
         assigns several in one SET (``SET a = 1, b = 2;`` → split;
         the comma form was invalid T-SQL and the second target lost
         its @ sigil). Depth-0 lookahead keeps single-assignment
         values comma-transparent. Measured: mysql→tsql **146 → 143**
         (−3). Discovery HOLDS 0. Tests:
         TestWave159MultiDeclareMultiSet (3).* Wave 160 (2026-07-16): MySQL
         truthiness under NOT — bare columns inside ``NOT (a AND b)``
         and a parenthesized predicate compared to 0/1 (``NOT (c2 IS
         NULL) = 1``) were error 4145 on T-SQL. ``_emit_condition``
         recurses into BinaryOp operands of NOT (narrowed so NOT
         EXISTS keeps its idiomatic spelling — the wide first cut
         broke 3 dual-guard tests) and a new
         ``_predicate_int_comparison`` rewrites ``<pred> = 1/0`` to
         the predicate or its negation. Measured: mysql→tsql
         **143 → 142** (−1; the 8x class holds INTERVAL() and
         outer-ref members). Discovery HOLDS 0. Tests:
         TestWave160NotParenTruthiness (5).* Wave 161 (2026-07-16): a
         single-argument COALESCE is T-SQL error 1088 — it IS its
         argument (CONCAT's wave-154 rule extended). And an
         aggregate's DISTINCT wrapper (``Count(this=Distinct(…))``)
         converted to a verbatim RawSQL argument, so the inner
         expressions bypassed EVERY function mapping
         (``COUNT(DISTINCT REPEAT(65, 3))`` shipped REPEAT on T-SQL) —
         now a real FunctionCall with ``distinct=True``. Measured:
         mysql→tsql **142 → 137** (−5). Discovery HOLDS 0. Tests:
         TestWave161CoalesceOneArgDistinctWrapper (4).* Wave 162 (2026-07-16):
         ADDDATE/SUBDATE are DATE_ADD/DATE_SUB aliases sqlglot leaves
         anonymous — they shipped dbo.-qualified as fake UDFs with a
         raw INTERVAL argument; canonicalized to the (ts, n, unit)
         form (bare-number second argument counts days). And ``SET
         sql_mode = …`` inside a routine is a session option, not a
         variable — it shipped a fake ``SET @sql_mode`` local;
         a known-options list degrades it to the established
         source-only comment carrier with a warning. Measured:
         mysql→tsql **137 → 131** (−6). Discovery HOLDS 0. Tests:
         TestWave162AdddateSqlMode (5).* Wave 163 (2026-07-16): sqlglot
         collapses ``CAST(x AS CHAR CHARACTER SET cs)`` to a
         CHARACTER_SET type — it emitted a nonexistent ``CAST(… AS
         CHARACTER_SET)`` everywhere, silently dropping the CHAR base
         (the corruption class). Converted to ``CHAR CHARACTER SET
         cs`` (MySQL keeps it; other targets strip the suffix). And a
         set-op subquery hangs its ORDER BY on the LAST arm of the
         set_query chain, dodging the existing unlimited-ORDER strip —
         now stripped along the chain. Measured: mysql→tsql
         **131 → 129** (−2). Discovery HOLDS 0. Tests:
         TestWave163CharsetCastSubqueryOrder (4).* Wave 164 (2026-07-16): MySQL's
         walrus assignment (``SET x := 1``) left the ``:=`` in the
         value (``SET @x = := 1`` — the OPERATOR match missed the
         ASSIGN token), and a SELECT INTO's trailing ``LIMIT n``
         survived verbatim in the T-SQL SELECT-assign, where the
         spelling is ``SELECT TOP n @v = …``. Measured: mysql→tsql
         **129 → 119** (−10, the day's biggest drop — both classes
         chained). Validity crossed **98.0%**. Discovery HOLDS 0.
         Tests: TestWave164AssignOpSelectLimit (4).**
         **Scope decision
         (user, 2026-07-17): live validation is a CODE-REFINEMENT
         tool only — used by the sweeps/tuning loops to find mapping
         gaps. It is deliberately NOT exposed in the CLI or the API
         (an end-user feature that needs a live engine to produce
         correct output would be a botch); `validate_live_url` stays
         a development-facing option.**

### P2 — correctness of signals and validation

### P0 — architecture plan (audit doc 04 — ADOPTED 2026-07-08)

- [ ] **M3 — P4 embedded DML through the IR converter**; delete the
      text-level rewriters (clears D3, D4, D8, A4 by construction).
      *M3a landed:* `_transform_embedded_dml` now routes through the shared
      `parse_sql → Transformer → emit_node` IR pipeline (raw sqlglot only as a
      warned fallback), which cleared D3 and D4 and surfaced+fixed four IR
      core bugs that also hit standalone DML: pass recursion stopped at
      top-level SELECTs (generic dataclass-field walker now), `find(exp.Where/
      Having)` duplicated a derived table's WHERE onto the outer SELECT,
      dropped parens/precedence on emit (silent `AND`/`OR` re-association),
      and `nulls_first` never carried (T-SQL DESC row order changed on PG).
      `exp.In`/unstyled `exp.Convert` are now modeled (IN was a RawSQL
      passthrough passes couldn't see; CONVERT now shares the CAST type maps).
      Three head-anchored matchers made trivia-aware via the shared
      `split_leading_trivia` (result-SELECT→refcursor, identity capture,
      trigger set-based rewrite). *M3b:* D8's remaining corruption was the
      T-SQL SELECT-INTO emitter's naive `split(",")` — fixed with the shared
      `split_top_level_commas`. Tests: `tests/integration/
      test_embedded_dml_ir.py` (22). **Measured (2026-07-09, live sweep):**
      test.sql→PG **100.0%** / Oracle 99.6% / MySQL 97.7% (unchanged classes);
      bigtest (Oracle source)→T-SQL **94.3%** / PG **76.6%** (was 73.1 — D3
      cleared) / MySQL 75.0%; live-syntax suite 53 passed. Transpile of the
      13 MB dump ~55 s (+22% vs pre-M3, linear). Still open: deleting the
      expression-level text rewriters — blocked on the M3-prereq below.
- [ ] **M3-prereq: move the procedural text-matchers onto structure before
      routing scalar expressions through the IR.** *Increment 1 landed
      2026-07-11 (`e8196ee`): the IR gains procedural variable types — a
      STRING_VARIABLES ContextVar published around every IR call lets the
      shared `_looks_like_string` classify `@a + @b` over declared string
      variables (fixed a live runtime bug: embedded UPDATE shipped
      `v_a + v_b` on PG). *Increment 2 landed 2026-07-11
      (`35c2155`, `33034ab`): the differential text-vs-IR audit found and
      fixed THREE live semantic bugs in the curated text handlers —
      DATEADD's '+' turned into '||' by the concat classifier (intervals
      now neutralize their literals), a token-joined '- 1' losing its
      sign inside the INTERVAL string (DATEADD(MONTH,-1) silently ADDED a
      month; literal counts compact, expression counts multiply a unit
      interval), and DATEDIFF DAY/MONTH/YEAR emitting Oracle-fractional /
      PG-AGE forms instead of T-SQL's boundary counts (both pipelines now
      share the boundary-counting forms).* Remaining increments: *(3) DONE 2026-07-17 (wave 96):
      LastIdentityCapture node landed — producer in both assignment
      transforms (oracle target, value is only the last-identity
      call), pairing pass consumes the node, marker constant deleted;
      the UNPAIRED fallback improves from the invalid `v := /* … */;`
      to a valid NULL assignment + note. Full gate green on first
      try; pg-corpus verification cycle at `b073133` identical
      {163/131/89} — no regression. Tests:
      TestLastIdentityCaptureNode.* Original analysis
      (2026-07-17): the marker is the TAIL of the Oracle comment
      `LAST_IDENTITY_EXPR["oracle"]` produced by
      `_transform_last_identity`'s text substitution;
      `_identity_assignment_var` then substring-matches it
      (`base.py:390`). Design: when the assignment transform detects a
      LAST_IDENTITY_SOURCE_FUNCS call with target oracle, return a
      dedicated `LastIdentityCapture(target_var)` node; the pairing
      pass (`base.py:345`) consumes the node; the emitter renders the
      documented comment for any UNPAIRED capture (fallback). Keep the
      non-assignment usages (`SELECT @@IDENTITY` in expressions) on
      the comment path. This is a fresh-session-sized refactor — the
      naive attempt broke 18 tests.*; (4) dual-guard→IF and
      DECLARE-init hoisting consume nodes — *4a landed 2026-07-17
      (wave 97): Oracle's assignment-via-SELECT-INTO decision now
      inspects the value NODE first (`_needs_sql_context`: subquery or
      CAST anywhere in the tree; RawSQL fragments keep the spelling
      regex). Tests: TestAssignmentViaSelectNodeAware; verification
      cycle at `129cc6b` identical {163/131/89}. Remaining 4b —
      *analysis 2026-07-17: the DECLARE-init half is DONE BY
      CONSTRUCTION after 4a (the hoisting already builds an
      AssignmentStatement from the initializer NODE, which then takes
      the node-aware SELECT-INTO path — verified live); the
      batch-level T-SQL guard recognizer (`_TSQL_GUARD_HEAD_RE`) is
      PRE-PARSE BY DESIGN (audited M2/P3 single-recognizer decision,
      runs on batch text before any parsing — unaffected by
      IR-emitting scalar expressions). The M3b probe RAN 2026-07-17
      (uncommitted IR-first in `_transform_raw_sql`, full suite):
      **126 failures** — the text path has GROWN as the expression
      engine since the original 18. Category map (top offenders):
      curated DATEADD/DATEDIFF/TRUNC/TO_DATE handlers (16+),
      function-name mapping & oracle-builtin renames (7+),
      FOUND/fetch-status cursor idioms (7), string-concat/plus
      classification (6+), error-global conditions & RAISERROR hoists
      (8+), comments inside expressions (IR drops them, 6+),
      SUBSTRING/position arg orders (4). Conclusion: wholesale
      IR-first is NOT the path — each consumer family must migrate
      individually (the increments-1..4a pattern), OR the IR
      expression pipeline must absorb those behaviors first. The
      probe patch is reproducible: guard `UNIQUE_IR_FIRST` in
      `_transform_raw_sql` wrapping `_ir_transpile_dml` for scalar
      fragments. Family migration step 1 (dates) landed 2026-07-17
      (wave 98): the differential found a live IR bug — DATEADD over
      a DATEDIFF base added an INTERVAL to a NUMBER (invalid Oracle /
      wrongly typed PG); the IR now matches the text path's numeric
      addition. Tests: TestIrNestedDateaddOverDatediff; verification cycle at
      `6be5038` identical {163/131/89}. Family step 2 (function
      renames) landed 2026-07-17 (wave 99): the differential found the
      procedural text path had NO (mysql, postgresql)/(mysql, oracle)
      function maps — IFNULL shipped raw to PG; both maps added
      (IFNULL/RAND/CURDATE/UUID + the symmetry round-trips the
      mapping-contract test enforces). Known cosmetic divergences left
      documented: NVL→ISNULL (text) vs COALESCE (IR) on tsql — both
      valid; sqlglot's LEN→LENGTH(CAST AS CLOB) vs text's plain
      LENGTH — both count trailing spaces that T-SQL LEN ignores
      (shared caveat, not a divergence). Tests:
      TestMysqlProceduralFuncMaps; mysql-corpus cycle at `e933b82`
      stable {166/107/129} (fidelity inside already-counted
      routines). Family step 3 (concat classification) landed
      2026-07-17 (wave 100): T-SQL `N'…'` literals parse as
      exp.National, which `_looks_like_string` did not recognize —
      `N'pre' + s` shipped raw `+` to Oracle (invalid on strings).
      The nested-CONCAT shape on mysql (`CONCAT(CONCAT(a,b),'c')` vs
      flat) is cosmetic, documented not chased. Tests:
      TestNationalStringConcat; verification cycle at `0a0ad03`
      identical {163/131/89}. Family step 4 (error-globals) landed
      2026-07-17 (wave 101): the system globals lived only in the
      procedural maps — a top-level `SELECT @@ROWCOUNT` shipped raw
      off T-SQL. New shared `_map_system_global` in the DML expression
      emit: MySQL gets the real ROW_COUNT(); PG/Oracle top-level get
      a documented neutral (their forms are PL-context only); Oracle's
      `SQL%ROWCOUNT` — which parses as a MODULO — maps at the
      BinaryOp. Tests: TestSystemGlobalsInDml; verification cycle at
      `63e0d31` identical {163/131/89}. Family survey CLOSED
      2026-07-17 (wave 102): @@FETCH_STATUS gets the top-level
      neutral (it is CURSOR-CONTEXTUAL by nature — the procedural
      path maps it with surrounding state: FOUND on pg, handler
      flags on mysql, cursor%FOUND on oracle; a context-free IR
      mapping is impossible today). DESIGN CONCLUSIONS for M3 final:
      (a) the IR expression pipeline must RECEIVE procedural context
      (cursor state, like STRING_VARIABLES) before fetch idioms can
      migrate; (b) in-expression COMMENTS need comment-carrying
      expression nodes in the IR (they are dropped today) — both are
      the remaining preconditions for deleting the text rewriters.
      Tests: TestFetchStatusTopLevel; verification at `2a2dc90`
      identical {163/131/89}.*; then the text rewriters can
      shrink. Original blocker analysis:** A first attempt at IR-first
      for `_transform_raw_sql` expressions (M3b) broke 18 tests and was
      reverted: downstream machinery pattern-matches on the *transformed
      expression text* — the Oracle last-identity capture looks for a marker
      string, the dual-guard→IF and DECLARE-init hoisting match query
      spellings, `_rewrite_string_concat` uses declared-variable types the
      standalone IR doesn't have, and the curated DATEADD/DATEDIFF handlers
      produce live-validated forms the IR emitter doesn't. Those consumers
      must consume nodes (or the IR must gain procedural context: var types,
      PROCEDURAL_FUNC_MAPS) before the text rewriters can be deleted (P4's
      final step). Until then the text path stays the expression engine.
### P1 — private-fixture live sweep (audit doc 03; anonymized repros there)

Found by transpiling the three `fixtures-private/` scripts across the matrix
and executing the outputs on the real engines. Ordered by attack value; every
fix needs an **anonymized** regression fixture (never a private name).

### P3 — hardening carry-overs (from 2026-07-02, still open)

- [ ] **Module growth** — *parser done 2026-07-10:* `procedural/parser` is
      now a package (_base 1.7k + _tsql 0.7k + _plsql 0.8k, explicit
      cross-family contract). Still to split: `procedural/transformer/
      base.py` (~3.5k) and `transpiler.py` (~2.2k). *Finding (2026-07-10):*
      the parser's name-based mixin cut does NOT transfer to the
      transformer — its shared/node-transform/expression-rewrite families
      cross-call heavily (an attempted split needed a dozen-plus stub
      contract and was reverted). **Seam DESIGNED 2026-07-11 (measured):**
      the expression-rewrite family is 24 methods / ~751 lines with 33
      node→expr call edges; its instance state is small (class-constant
      regex/maps + `_source`, `_in_trigger`, `_string_vars`,
      `_get_func_map`). Design: a composed **`ExpressionRewriter`**
      object (`transformer/_expr.py`), constructed per transform with a
      narrow `RewriteContext` protocol (`source`, `target`, `in_trigger`,
      `string_vars`, `date_vars`, `warn()`, `func_map()`, and ONE
      `target_fixups(sql)` hook through which the per-target transformer
      classes keep their overrides — `_fix_raw_sql_target`,
      `_map_oracle_builtins`, …). The 33 call edges rewire mechanically
      to `self._expr.X(...)`. Implement as one mechanical commit with the
      full suite as the net; per-target subclassing of the rewriter can
      come later. This also unblocks M3-prereq's final step (the rewriter
      object is what IR-first expressions will eventually replace).
## 3. Test-corpus expansion (P3)

- Corpus wave campaign **COMPLETED and archived** (2026-07-15 →
  2026-07-17, waves 4–95; full per-wave log with measured commit
  hashes in `docs/DONE.md`, section "Wave campaign — corpus
  validity"; waves 96–102 are the M3-prereq/M3b record kept in the
  §2 M3 item). Final standings at `3fdfc88`:
  - pg-source (PostgreSQL regression corpus,
    `fixtures-corpus/pg_corpus_valid.sql`): →T-SQL **163** syntax
    failures (95.0% validity), →MySQL **131** (95.7%), →Oracle **89**
    (97.2%).
  - mysql-source (private local corpus, provenance undocumented by
    policy): →T-SQL **166** (97.2%), →PG **107** (98.2%), →Oracle
    **129** (97.8%).
  - Both residues are at the deep-singles floor (a full measure cycle
    buys ~−1); do not resume waves on these corpora without a new
    corpus or a fidelity target.

## 4. Packaging (P3)

- [ ] **PyPI publication** — deferred until the tool has been used in real
      projects for a few months and proven stable. Not before then.

---

## Continuously tracked (not a discrete backlog)

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
