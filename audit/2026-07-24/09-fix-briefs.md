# 09 — Fix briefs (pre-analysis per finding)

One brief per open work item from this audit. Purpose: the session that
implements a fix starts **here**, not from scratch — root cause already
verified, approach already chosen, wrong paths already rejected, tests already
specified. A fresh session needs only `skills/SKILL-project-overview.md`,
`skills/SKILL-development-workflow.md` and the brief.

Conventions: file:line references are at HEAD `69a71cd` — **re-confirm the
cited site before patching** (a prior fix may have moved it). Every brief
implies the standard definition of done (guardrail 6): gate green, neighbors
probed, round-trip holds, no validity regression, docs updated in the same
change. "Live" means the four Docker engines
(`docker compose -f docker-compose.test.yaml up -d`).

Root-cause confidence: every N-finding below was live-verified by the audit
(source valid on its engine, output invalid/divergent on the target, zero
warnings); mechanisms were traced by reading the code, and N1's was
independently re-confirmed (`_convert_insert` reads neither `conflict` nor
`returning`).

---

## P1

### B1 — N1: model the upsert clause (`ON CONFLICT` / `ON DUPLICATE KEY UPDATE`)

**Symptom** (02 N1): MySQL `ON DUPLICATE KEY UPDATE` and PG `ON CONFLICT
DO UPDATE / DO NOTHING` are silently dropped on **every** target; upserts ship
as plain INSERTs, zero warnings. The matrix row is already downgraded to ⚠️.

**Root cause:** sqlglot models the clause as `exp.Insert.args["conflict"]`
(`exp.OnConflict`); `_convert_insert` (`converter/convert.py:1348`) reads
`columns`/`expression`/`with` but never `conflict` — the clause dies at IR
construction. The only `conflict` mention (`emit.py:2391`) is unreachable.

**Approach:** IR modeling, both pipelines (embedded INSERTs already route
IR-first, so one model serves both).
1. Add an `on_conflict` field to `InsertStatement` (dataclass:
   `action: Literal["update","nothing"]`, `key_columns: list[str] | None`,
   `assignments: list[Assignment] | None`, `where: Expression | None`).
   Extend with `dataclasses.replace` discipline.
2. Convert from `exp.OnConflict` (both the PG and MySQL spellings — sqlglot
   normalizes both into it; map `EXCLUDED.x` / `VALUES(x)` source references
   into one IR marker for "the incoming row's value").
3. Emit per target:
   | target | DO UPDATE | DO NOTHING |
   |---|---|---|
   | postgresql | native `ON CONFLICT (k) DO UPDATE SET … EXCLUDED.x` | native |
   | mysql | `ON DUPLICATE KEY UPDATE … VALUES(x)`/alias form + **annotation + warning**: MySQL fires on ANY unique key, not the named conflict target | `INSERT IGNORE` + same annotation (IGNORE also swallows other errors — say so) |
   | tsql / oracle | lower to MERGE via the existing canonical-MERGE writer (`converter/_base.py:508`): `USING (VALUES …) src ON (key)` + `WHEN MATCHED THEN UPDATE` + `WHEN NOT MATCHED THEN INSERT` | MERGE with only the `WHEN NOT MATCHED THEN INSERT` clause |
4. MySQL→PG needs a conflict target PG requires: take the harvested
   PK/unique-key columns when the script created the table (extend the
   COLUMN_TYPES harvest to record PK/UNIQUE — B10 touches the same code);
   otherwise degrade whole-statement to carrier + warning (never guess a key).
5. Until every emission path is covered, an `on_conflict` the emitter can't
   render must degrade the statement warned — never strip the clause.

**Rejected:** regex post-processing of the emitted INSERT (guardrail 2);
"warn-only" without modeling (a direct equivalent exists for the common pairs);
silently mapping PG's targeted conflict to MySQL's any-key semantics without
the annotation (lying output).

**Tests first:** unit conversion tests (IR field populated for both source
spellings); per-direction probes asserting target idiom present AND
`ON CONFLICT`/`ON DUPLICATE` absent where lowered; the **live FE-style value
test**: table with a unique key + pre-seeded conflicting row, run the upsert
twice on every target, assert one row with the updated value (this is the
scenario-adequacy rule — the old corpus case had no unique constraint). Fix
the vacuous corpus case `pg-insert-select-conflict`
(`challenge_postgresql.sql:367`) to seed a conflict.

**Acceptance:** the four probes of finding N1 produce equivalent final state
on all four engines; warnings appear exactly where the table above says;
identity-mutation kill does not drop.

**Blast radius:** `ast_nodes.py`, `converter/convert.py`, `converter/emit.py`,
`converter/_base.py`, harvest (PK), challenge corpus case, matrix row back to
✅-with-note. Do together with **B2** (the tripwire would have caught this
class). Unlocks nothing else; independent of the MERGE briefs below.

### B2 — T1: unread-args tripwire (converter guard)

**Symptom/class:** N1, N3, N4 are all "sqlglot parsed it; the converter never
read the arg; nothing warned". The workflow skill now has guardrail 7 (manual
checklist); this makes it mechanical.

**Approach:** at the single conversion dispatch point in
`converter/convert.py`, wrap the node's `args` dict in a read-tracking
mapping (subclass recording accessed keys) for the duration of that node's
`_convert_*` call; on return, diff `node.args.keys()` (non-None values only)
against the read set minus a per-node-type allowlist
(`ALLOWED_UNREAD = {"comments", "_leading", …}` — build it empirically).
Any residue → `result.warnings` entry
`"internal: unread sqlglot arg '<k>' on <NodeType> — construct may be dropped"`
and (gate mode) degrade the statement to a carrier. Modes via env
`UNIQUE_UNREAD_ARGS=off|warn|gate`, default `warn`; CI runs `warn` and fails
on any occurrence over the test corpus (a ratchet starting from the bulk-sweep
baseline). Add a `--sweep` script mode that runs the corpus fixtures and
prints unique `(NodeType, arg)` pairs — that list seeds RED clause-level
cases (challenge skill, "Where to hunt").

**Rejected:** per-`_convert_*` hand-maintained consumed-lists (drift by
construction); asserting inside sqlglot (upstream, fragile).

**Tests first:** a unit test with a node type whose converter deliberately
skips an arg (monkeypatched) asserting the warning fires; a regression test
that the full standard fixture set produces **no** unread-args warnings once
the initial findings are burned down or allowlisted.

**Acceptance:** `UNIQUE_UNREAD_ARGS=warn` clean over `tests/fixtures/` +
corpus; N1's input warns (pre-B1) / converts (post-B1).

**Blast radius:** `converter/convert.py` dispatch + a small tracking helper;
CI step. Coordinate with B1 (land tripwire first in `warn`, then B1 clears
its biggest hit).

### B3 — Confidentiality remediation at HEAD (7 files + 2 DONE lines)

**Symptom** (07 F1–F8, F10): real schema vocabulary in 7 committed files;
the private MySQL corpus's origin named in `docs/DONE.md:1614-1615`; plus two
**commit messages** (F2 `6fde4146`, F9 `13989cb7`) that only a history rewrite
could purge. **Maintainer decision 2026-07-24: NO history rewrite** — the two
message hits (and historical blob revisions) are accepted as residual risk;
this brief covers HEAD-level fixes only, and the T2 leak check prevents new
message leaks going forward.

**Approach:** for each file hit in the unredacted list (session scratchpad
`CONFIDENTIALITY-HITS-FULL.md` — if the scratchpad is gone, regenerate with
the sweep method in doc 07 §2), replace the private identifier with a
same-shape synthetic (same length class, same role: table→`cfg_registry`-style
generic, column→`ref_code`-style, cursor→`cur_items`). Each affected test
asserts on its own fixture text, so rename source and assertion together;
`test_procedures_fixtures.py:35`'s guard list should load its fragment list
from an untracked local file (guard stays useful, repo stays clean). Reword
the two DONE.md passages (drop the upstream project/DSL name; keep the
decision record generic: "an external GPL test corpus, evaluated and
rejected"). Then run the full suite + the sweep again → expect file-hits 0.

**Tests first:** n/a (mechanical rename), but re-run the token sweep as the
acceptance check and the full gate (fixtures regenerate if touched).

**Acceptance:** token-intersection sweep reports 0 file-content hits; suite
green; no test semantics changed (`git diff` shows only identifier renames).

**Blast radius:** the 7 files listed in doc 07 + `docs/DONE.md`. Independent;
do FIRST if a history rewrite is later approved (fold the renames into it).

### B4 — N2: Oracle MERGE conditional-DELETE fold evaluates post-UPDATE values

**Root cause:** `_merge_extended_clauses` (`converter/emit.py:634-731`) folds
`WHEN MATCHED AND dc THEN DELETE` + `WHEN MATCHED THEN UPDATE` into Oracle's
single `UPDATE … DELETE WHERE dc`, but Oracle evaluates `DELETE WHERE`
against **post-update** values; T-SQL evaluates `dc` on the original row.
Live: 2 rows deleted vs 1.

**Approach:** add a safety predicate to the fold: collect target-alias columns
assigned by the UPDATE SET; walk the DELETE-relevant condition(s) (`dc`, and
in UPDATE-first order the folded `NOT(uc) AND dc`); if any referenced
target-alias column is in the assigned set → **do not fold**: degrade the
whole MERGE to the documented carrier + warning ("conditional DELETE reads
columns the UPDATE assigns; Oracle DELETE WHERE would see post-update
values"). Source-column-only conditions keep the current fold (verified
correct). Optional second phase (only if the corpus shows demand): lower the
unsafe shape to a pre-MERGE `DELETE … WHERE EXISTS(<join> AND dc)` when the
MERGE has no INSERT clause.

**Rejected:** rewriting `dc` to reference pre-update values via arithmetic
inversion (impossible in general); snapshot temp tables (blast radius,
concurrency semantics).

**Tests first:** exact N2 live scenario (`dst={(1,5),(2,0)}, src={(1,0),(2,7)}`)
asserting equal final state SQL Server vs Oracle; the safe variant
(`s.qty = 0`) still folds (present/absent assertions on `DELETE WHERE`);
neighbor: UPDATE-first clause order.

**Acceptance:** unsafe shape warns + carries; safe shape unchanged;
`ts-merge-full` corpus case stays green; FE value equality on the N2 scenario.

**Blast radius:** `converter/emit.py` (`_merge_extended_clauses`),
`docs/03-unsupported.md` entry for the degraded shape. Independent of B5/B6
but same function — **land B4/B5/B6 as one series to avoid merge conflicts.**

### B5 — N3: MERGE `OUTPUT` → PostgreSQL invalid/mis-attached `RETURNING`

**Root cause:** the OUTPUT→RETURNING rename fires for PG because PG has
RETURNING — but not on MERGE (PG16: none; PG17: `RETURNING merge_action()`),
and the BY-SOURCE split (`emit.py:2574`) never accounts for a pending OUTPUT
tail, so it lands on the follow-up DELETE or inside a trailing comment.

**Approach:** extract the OUTPUT clause **before** any merge
lowering/splitting; then: target PG (and any non-tsql target) with
OUTPUT-on-MERGE → degrade the OUTPUT to the **existing** "no standalone
OUTPUT/RETURNING result set" carrier + warning (exactly what Oracle/MySQL
already do — reuse that gate, don't invent a new message), emitting the MERGE
itself without the tail. Never attach the tail to a follow-up statement or a
comment. A PG≥17 native translation (`RETURNING merge_action(), …`) is a
separate opt-in once a target-version option exists (improvement #6) — do not
block on it.

**Tests first:** N3's three manifestations (plain, BY-SOURCE split,
interleaved comment): each must produce parseable PG (target-parse), the
carrier + warning, and NO `RETURNING` on any emitted statement; live PG
execution of the lowered MERGE.

**Acceptance:** zero-warning invalid output impossible for OUTPUT-on-MERGE in
any direction; existing INSERT/UPDATE OUTPUT limits untouched.

**Blast radius:** `converter/emit.py` (OUTPUT handling ~:1419, merge splice
~:2574). Fixes N14's worst variant as a side effect; still add N14's comment
assertions (B13-adjacent).

### B6 — N4: PG MERGE `THEN DO NOTHING` passthrough

**Root cause:** sqlglot models the action as `Var(this=DO NOTHING)`;
`_merge_extended_clauses` special-cases only `Var("DELETE")`; everything else
falls through to sqlglot's generator verbatim in every dialect; the output
gate re-parses it leniently and misses it.

**Approach:** handle `DO NOTHING` in the merge lowering by **clause
carve-out**: first-match-wins means `WHEN MATCHED AND c THEN DO NOTHING`
equals adding `AND NOT (c)` to every *later* MATCHED clause (and to the
Oracle CASE fold, where it composes with B4's machinery); an unconditional
`DO NOTHING` simply drops all later MATCHED clauses. Same for
`WHEN NOT MATCHED THEN DO NOTHING` against later NOT-MATCHED clauses. Any
`Var` action that is neither DELETE nor DO NOTHING → degrade the whole MERGE
warned (future-proofing against new sqlglot actions — the B2 tripwire idea
applied locally).

**Tests first:** N4's exact input → tsql/oracle: target-parse + live execute +
value equality with PG original (rows with `s.qty IS NULL` untouched); a
`DO NOTHING`-only MERGE; unknown-Var fallback test (construct via sqlglot AST
directly).

**Acceptance:** live equal state on the three engines; no `DO NOTHING` token
in non-PG output (absent assertion).

**Blast radius:** `converter/emit.py` `_merge_extended_clauses`. Series with
B4/B5.

## P2

### B7 — N5+N6: per-cursor status emulation (one design, four bugs)

**Root causes** (all live-verified):
(a) MySQL emitter hardcodes `loop_lbl` (`procedural/emitter/mysql.py:142`,
438-496) → duplicate labels on nested loops (error 1309);
(b) one shared `v_fetch_done` NOT-FOUND handler flag, never reset → outer loop
exits after the inner cursor exhausts;
(c) T-SQL maps `%NOTFOUND` to global `@@FETCH_STATUS`
(`procedural/transformer/tsql.py:283`, 616-619) — wrong when another FETCH
intervenes;
(d) `%ISOPEN` unmapped → emitted as modulo `c % ISOPEN`
(transformer tsql.py:281-284 / mysql.py:209-211 map only
FOUND/NOTFOUND/ROWCOUNT).

**Approach — the class fix, not four patches** (improvement #2): per-cursor
state variables, mirroring the existing `%ROWCOUNT` counter pattern
(`@uq_<name>_rc`, `transformer/tsql.py:633`):
- **Labels:** a per-emission monotonic counter → `loop_lbl_1`, `loop_lbl_2`
  (emitter base owns the counter; MySQL module consumes it).
- **T-SQL status:** immediately after every `FETCH <c>`, emit
  `SET @uq_<c>_fs = @@FETCH_STATUS`; rewrite `<c>%NOTFOUND`/`%FOUND` to read
  `@uq_<c>_fs`. Adjacency no longer matters.
- **MySQL status:** one done-flag **per cursor** (`v_uq_<c>_done`); the single
  NOT FOUND handler sets a shared flag — so instead emit
  `SET v_uq_<c>_done = …` transfer right after each FETCH from the shared
  handler flag, then **reset the shared flag**; `<c>%NOTFOUND` reads the
  per-cursor flag. (MySQL allows one NOT FOUND handler per scope — the
  transfer+reset idiom is the standard workaround; document it in the emitted
  code once, as a comment.)
- **`%ISOPEN`:** per-cursor `@uq_<c>_open` / `v_uq_<c>_open` flag set to 1/0
  on OPEN/CLOSE, read by `%ISOPEN`, both targets. (T-SQL's
  `CURSOR_STATUS('local', 'c')` rejected: three-state semantics and
  local/global scope guessing — the flag is deterministic.)
- **Backstop:** any cursor `%<attr>` the transformer doesn't recognize must
  hit the unrecognized-construct gate (warned carrier), never lex through as
  `%` arithmetic — this is the N6 class-closure.

**Tests first:** the N5 nested-loop scenario live on MySQL (all parent rows
processed — value assertion, not just syntax), the interleaved-FETCH scenario
live on T-SQL vs Oracle row counts, `%ISOPEN` probe per target, single-cursor
regressions (existing corpus cursor cases stay green), unknown-attribute
(`c%FOO`… invalid on Oracle — instead construct via parser unit test) warns.

**Acceptance:** live row-set equality on the nested and interleaved scenarios
across oracle→{tsql,mysql}; no `loop_lbl:` duplicate in any output; no bare
`% ISOPEN` token anywhere; existing cursor tests green.

**Blast radius:** `procedural/emitter/{base,mysql,tsql}.py`,
`procedural/transformer/{base,tsql,mysql}.py`. Largest P2 item — budget a
full session; the design above is settled, don't relitigate it mid-fix.

### B8 — N7: PG `SET TRANSACTION …` access modes

**Root cause:** `batch_splitter.py:313` routes PG `SET TRANSACTION` to the
DML pipeline → sqlglot `Command` passthrough verbatim; the access-mode
mapping (`emit.py:2331-2366`) matches only the mysql-source
`START TRANSACTION` spellings.

**Approach:** extend that same emit-side mapping to the statement class
`SET TRANSACTION [ISOLATION LEVEL <lvl>] [READ ONLY|READ WRITE]` (PG source):
MySQL → comma-joined characteristics (`ISOLATION LEVEL X, READ ONLY`); T-SQL
→ emit the isolation level statement, strip the access mode with the existing
documented note (`my-set-transaction` precedent); Oracle → passes natively
(verify first-statement rule handling matches the mysql-source path). Reuse
the existing per-target table — one new recognized spelling, not a new
mechanism.

**Tests first:** the three N7 probes per target (present/absent: `READ ONLY`
absent on tsql + warning present; comma present on MySQL) + live execution.

**Acceptance:** live-clean on tsql/mysql; warning where stripped; oracle
unchanged.

**Blast radius:** `converter/emit.py` (~:2331), possibly a
`batch_splitter` classification tweak. Small.

### B9 — N8: T-SQL money literal `$12.50`

**Root cause:** sqlglot misparses to
`Column(this=Literal(50), table=Identifier($12))`; converter accepts the
garbage shape silently.

**Approach:** in the converter's Column handling, detect the known mangle —
table identifier matching `^\$[\d.,]+$` (and quoted variants) with a numeric
`this` — and rebuild the numeric literal (strip `$`/commas, rejoin the
decimal part), reusing the strip logic the `ts-cast-money` fix added for
CONVERT. Generalize the lesson: a `table.column` whose "table" is not a valid
identifier shape should trip the 07-08 garbage detector (extend
`validation.py`'s shape checks) rather than pass silently — add both.

**Tests first:** `SELECT $12.50`, `$1,234.00`, `$0.5` → pg/oracle/mysql
(literal `12.50` present, `$` absent, target-parse + live); negative control:
a real table actually named with `$` (Oracle allows `A$B`) must NOT be
rewritten — assert the guard only fires on the full `^\$[\d.,]+$` shape.

**Acceptance:** live value 12.5 everywhere; no `"$12"` identifier in output.

**Blast radius:** `converter/convert.py`, `core/validation.py`. Small.

### B10 — N9: running COLUMN_TYPES harvest + T-SQL ALTER nullability

**Root cause:** `harvest_column_types` (`converter/harvest.py:189`) reads only
`CREATE TABLE`; later `ALTER … TYPE`/`ADD COLUMN` never update the map, so
the nullability rewrite (`emit.py:2056-2075`) re-states the original type
(silent type revert); and the T-SQL ALTER-TYPE emission (`emit.py:1607-1626`)
omits nullability, silently making the column NULLable.

**Approach:** two halves, one change: (1) make the harvest a **running scan**
applied in statement order (the transpiler already visits in order): fold
`ALTER … TYPE`, `ADD COLUMN`, `RENAME COLUMN` into the map as encountered —
also record PK/UNIQUE (B1 wants it); (2) when emitting T-SQL
`ALTER COLUMN <c> <type>`, append the column's known nullability from the map
(`NOT NULL` when known-true), and warn when the map doesn't know. Statement
order is the contract — document that a script that ALTERs a table it didn't
create in-script gets the warning path.

**Tests first:** the exact N9 three-statement script → tsql, asserting
`ALTER COLUMN a BIGINT NOT NULL` then `ALTER COLUMN a BIGINT NULL`
(present/absent on INT), live-verified end state (`bigint`, `is_nullable=1`
only after the DROP NOT NULL); ADD COLUMN follow-up (improvement #8) folded
in.

**Acceptance:** live column type/nullability equal to PG's end state; warning
fires for the unknown-column case.

**Blast radius:** `converter/harvest.py`, `converter/emit.py`. Do before or
with B1 (shared harvest extension).

### B11 — N10: dynamic-SQL string literals shipped untranslated

**Root cause:** whole-statement string literals reaching
`EXEC`/`sp_executesql`/`EXECUTE IMMEDIATE` are spliced byte-identical; only
concatenated fragments get rewrites. The shell converts, so output compiles
and fails at runtime. docs §6 claims these warn — they don't.

**Approach:** at the dynamic-SQL sink (the procedural transformer already
tracks STRING_VARIABLES/IR_EMBEDDED), take each **constant** string content
(literal, or variable whose assignments are all constant — the existing
tracking decides), run it through the transpiler as source-dialect SQL and
splice the translation; if it doesn't parse as SQL, or the variable is
non-constant, emit the existing "review dynamic SQL" warning. Never silent.
This mirrors the M4 "unwrap constant EXECUTE IMMEDIATE" precedent one level
deeper — reuse that machinery, don't duplicate it.

**Rejected:** regex-translating inside the string (guardrail 2 — the string
IS SQL text; route it through the real pipeline).

**Tests first:** the N10 fixture pair (literal + variable) → pg/oracle:
translated content present (`LIMIT 5`/`FETCH FIRST`, `GETDATE` absent), live
execution of the produced routine; a non-SQL string (`'hello'`) → warning,
unchanged; a non-constant variable → warning.

**Acceptance:** docs §6's "reported as warnings" claim becomes true for every
dynamic-SQL path; live runtime execution succeeds on the translated probes.

**Blast radius:** `procedural/transformer/base.py` (+ per-target), possibly
`transpiler/_core.py` recursion guard (embedded transpile of embedded SQL —
cap depth at 2, warn beyond).

### B12 — N11: `SQL%ROWCOUNT` → MySQL `ROW_COUNT()` divergence

**Approach:** no faithful emulation exists (`ROW_COUNT()` counts changed rows;
connection flag `CLIENT_FOUND_ROWS` flips it globally). This is the §3.22
annotated-inherent-divergence class: keep the mapping, add the `UNIQUE:`
annotation + warning on every `SQL%ROWCOUNT`→MySQL emission
(`procedural/transformer/mysql.py:209`, `base.py:2904`), and a
`docs/03-unsupported.md` §3.22-family entry. T-SQL `@@ROWCOUNT` stays
unannotated (matched-rows, verified equivalent).

**Tests first:** presence of annotation + warning on the mysql direction;
absence on tsql; live demonstration retained as the doc example.
**Acceptance:** warned per the challenge-skill rules (a warned divergence is
an accepted outcome). **Blast radius:** 2 transformer sites + docs. Small.

### B13 — N12: carriers must preserve the ORIGINAL statement

**Root cause:** unmapped-operator carriers re-render the half-transformed
tree in the source dialect (`dbo.JSON_EXTRACT`, converted accessor pairs) —
the "preserved" text is a hybrid no engine accepts; the warning lies.

**Approach:** the converter has the original batch text (the splitter hands
it over) — carry it alongside the tree and emit **that** in the
"Statement preserved as a comment" carrier, never a re-render. Same invariant
as the 07-23 PassthroughSQL repr-leak fix, one level up: add the general
assertion to the carrier tests — **every carrier comment body must parse in
the source dialect** (comment-strip first per the comment-prose trap).

**Tests first:** N12's exact input → all targets: carrier body contains
`JSON_VALUE(doc, '$.name')` verbatim and NOT `dbo.JSON_EXTRACT`; the new
shared carrier-body-parses-as-source assertion wired into the existing
carrier test helper (it will catch unknown siblings — triage, don't suppress).

**Blast radius:** `converter/emit.py` carrier path + carrier test helper.

### B14 — A1: filename sanitizer `re.ASCII`

`api/app.py:474`: `re.sub(r"[^\w.\- ]", "", stem)` uses Unicode `\w` → CJK
names crash the latin-1 header encode (500, live-reproduced). Fix: add
`flags=re.ASCII` (and a fallback stem `output` when the result is empty).
Tests: upload `中文.sql`, `ñandú.sql`, `ev"il.sql` → 200 + ASCII-clean
`Content-Disposition`. One line + tests; do alongside A2–A5 hardening notes
in doc 05 if touching the file anyway.

### B15 — Ratchets: raise now, then automate staleness

1. `scripts/identity_mutation_check.py`: floor 0.45 → **0.60** (measured 0.66
   on 2026-07-24 — margin 6; the skill's release checklist governs future
   raises).
2. `.github/workflows/mutation.yml` per-module floors: after one clean
   nightly at HEAD, set each to `nightly_measured − 10` (the sampled
   `convert.py` run scored 82 vs floor 65).
3. **T7 — stale-floor detector:** the identity gate additionally FAILS when
   `measured − floor > 15` with message "floor is stale — raise it" (belt to
   the release-checklist braces). Trivial addition to the same script.

**Acceptance:** CI green at the new floors; deliberately lowering a floor
below measured−15 turns CI red. **Risk:** the floor raise makes the identity
gate sensitive to *removing* strong tests — intended.

### B16 — Challenge corpus: upgrade the ~362 loop-only `[fixed]` cases + T4

**Symptom** (03 finding 3): ~362/694 `[fixed]` cases have no dedicated
assertion; challenge outputs are never target-parsed in CI.

**Approach:** (1) **T4 first** — add to `test_challenge.py` a per-case
**target-dialect parse** of every `[fixed]` case's output (sqlglot
RAISE-level; keep it ONE looping test to protect the identity-gate
denominator, exactly as the skill's CI-gotcha says — parse checks don't kill
identity mutants anyway, they're a validity gate, and the *dedicated*
assertions carry the kill weight). Expect a triage wave: park failures as
`@xfail(strict)` with case IDs, burn down. (2) Then upgrade cases toward
dedicated assertions **by class priority** (func/semantic first — they need
live value checks; pure-syntax drops later), batched ~50/session, measuring
the identity kill rate per batch (each batch should raise it — measurable
progress, per the green-but-unmoved breaker). A periodic (nightly, not
per-push) live-execution job for the func-class cases completes T4.

**Acceptance:** target-parse gate green over all 694; identity kill rises
with each upgrade batch (record in the PR); nightly live job green.

**Blast radius:** `tests/integration/test_challenge.py` only. Long-tail work
— fine to interleave with feature fixes.

### B17 — Emitter debt: de-regex F1/F2, split emit.py, arm T3/T6

**Symptoms** (04): F1 `_map_oracle_scalars_for_tsql`
(`transpiler/_text_rules.py:159`, called `_core.py:838`) and F2
`map_sequence_refs` (`converter/emit.py:565`) are post-emit regex mappings —
guardrail-2 violations; `emit.py` 9,992 lines, `_emit_function` 2,270
lines/CC 355, 82 `re.sub`s, 486 dialect compares.

**Approach (ordered — measurement first so the burn-down is visible):**
1. **T3 — ratchet gate now:** `scripts/architecture_ratchets.py` asserting
   monotonic non-growth, floors = today's measured baselines (re-measure at
   implementation; doc-04 records: emit.py 9,992 lines; emitter-module
   `re.sub` count; dialect `== "<dialect>"` compares in shared modules:
   emit.py 486, procedural transformer base 66; ruff C901 offenders 107).
   Wire into CI next to the identity gate. Numbers only go down.
2. **T6:** enable `C901` + `PLR0912`/`PLR0915` in pyproject with ceilings at
   today's worst (so it gates new code immediately), ratcheted down via T3.
3. **F1/F2 de-regex:** move the CHR/TO_NUMBER/MONTHS_BETWEEN mappings into
   `core/mappings.py` + the IR converter path (they are ordinary function
   mappings — the machinery exists); NEXTVAL/CURRVAL become IR-level sequence
   references (model on `SequenceRef` if absent). Delete both regex sites;
   ratchet counts drop.
4. **Split emit.py** along doc-04's seams: `emit_functions.py`,
   `emit_passthrough.py`, `emit_ddl.py`, `emit_expr.py` (mechanical moves,
   no behavior change — verify with the formatter-survival checks from the
   workflow skill); then burn `_emit_function` down by extracting per-family
   emitters. The 57 "wave NNN" comments mark instance-patches to revisit as
   classes — file TODO items per family, don't fix inline.

**Rejected:** a big-bang rewrite of emit.py (the ratchet + seams give the
same end state without a frozen branch); keeping F1/F2 "because tests pass"
(the pattern is the finding).

**Acceptance:** ratchet gate live in CI; F1/F2 sites deleted with their
mappings' round-trip tests green; emit.py under 6k lines after the split with
zero behavior diffs (full gate + FE + corpus live).

### B18 — T2: `scripts/private_leak_check.py`

**Spec:** derive the token inventory at runtime from `fixtures-private/`
(same filter as doc 07 §2: case-fold, length ≥6, drop SQL
keywords/builtins/dictionary words + the explicit short-identifier list read
from an untracked side file); check (a) the staged/olddiff→HEAD changed lines,
(b) commit messages about to be pushed (`origin/main..HEAD`); exit non-zero
listing file:line + token. **The script contains no private data** — it is
committable; it no-ops (exit 0, "private corpus absent") when
`fixtures-private/` is missing, so public CI is unaffected. Local use:
pre-push habit (workflow skill already mandates it); optionally a
`.git/hooks/pre-push` sample in `scripts/`. Acceptance: seeding a scratch
file with a known private token makes it fail; clean tree passes; runtime
under ~10 s (token set is built once, ~25k entries — use a set intersection
per line, the audit's sweep already proved the approach at this scale).

### B19 — T5: `scripts/challenge_stats.py`

**Spec:** parse `-- CASE[status][class=x]:` headers across
`tests/fixtures/challenge/challenge_*.sql`; report per-status/per-class/
per-source counts; `--batch-since <ref>` scores cases added since a git ref
against the skill's A9 rules (points table, ≤50% concentration, ≥3 classes)
and exits non-zero on violation. Legacy cases without `[class=]` are counted
as `unclassified` and excluded from batch scoring (no retro-tagging
required). Pure stdlib text processing; unit tests with a fixture corpus
snippet. CI: run the distribution report on challenge-file changes (report
always; batch-gate only when RED batches run, via a manual flag).

## P3 tail (small, do opportunistically)

- **B20 — N13:** whitelist PG's `TABLE t` statement in
  `core/validation.py`'s bare-statement check (dialect-conditional). Probe
  both API and CLI accept it; `banana banana` still rejected.
- **B21 — N14:** MERGE comment trivia — leading standalone comment must
  re-emit above the statement; inline comment emitted once. Covered partly by
  B5's tail extraction; add the present-once assertions.
- **B22 — N16:** change `transpiler/_core.py:1104` to log the full traceback
  (`logger.exception`) so the one-off `KeyError('into')` is diagnosable if it
  recurs. Zero risk.
- **B23 — dead IR nodes** (04): remove the 5 unreferenced node classes
  (`ParameterRef`, `AlterTableStatement`, …) and `builtins_for` after a
  grep-confirmed zero-reference check; hoist the byte-identical plugin helper
  to base. Pure cleanup, separate commit.
- **B24 — mutation-script isolation** (03): `scripts/mutation_test.py`
  mutates `src/` in place — make it copy the tree to a temp dir (or guard
  with an env lock file the test runner checks) so a concurrent local suite
  can't read mutated source. Document in the script header meanwhile.
- **B25 — perf-budget flake:** `test_transpile_within_budget` uses wall
  clock; under parallel/agent load it overshoots (10.3–19.7 s vs 5.2 s
  idle). Switch the measurement to `time.process_time()` (CPU seconds are
  load-stable) with the same budgets re-baselined, or mark the test to run
  in the serial group of `test-parallel.sh`. Prefer process_time — it keeps
  the regression-detection intent without the flake.
- **B26 — `.dockerignore`** (05 A3 / 07): add one excluding
  `fixtures-private/`, `fixtures-corpus/`, `.venv`, caches — guard against a
  future context-wide COPY.
- **B27 — CI deps vs image pins** (05 A5): make CI install with
  `-c constraints.txt` so the tested closure matches the shipped image; add
  a periodic job or release-checklist line to refresh the constraints.
- **B28 — improvements #3/#4** (02 tail): `#temp`-in-procedure wiring and
  top-level `BEGIN TRY/CATCH` procedural routing — both are feature briefs to
  write when scheduled (the current warned degrades are honest, so they are
  P3 enhancements, not invariant violations).

## Suggested worker tier per brief (agentic team mode — see the workflow skill)

Delegate each brief to the cheapest model tier its residual judgment allows;
the architect (strongest model) reviews every diff regardless of tier.

- **Opus** (semantic judgment remains): B1, B2, B4–B7, B10, B11, B13, B16
  (triage waves), B17 steps 3–4.
- **Sonnet** (fully specified, single mechanism): B8, B9, B12, B15, B17
  steps 1–2 (T3/T6 gates), B18, B19, B20, B21, B24, B25, B27.
- **Haiku or architect-direct** (mechanical/one-liners): B3 (renames from the
  hit list), B14, B22, B23, B26.

## Suggested order

1. B3 (confidentiality — unblocks any future history-rewrite decision)
2. B2 warn-mode → B1 (upsert) → B10 (shares harvest) — the headline S1s
3. B4+B5+B6 as one MERGE series
4. B14, B22, B26 (one-liners) — anytime
5. B15 (ratchets) + T3/T6 arming from B17 — early, so the debt burn-down is
   measured from a baseline
6. B7 (cursors), B8, B9, B11, B12, B13
7. B16 (challenge upgrade) and B17 steps 3–4 as background campaigns
8. B18/B19 tooling whenever a session has slack; P3 tail opportunistically
