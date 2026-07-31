# A10-P — Procedures-corpus live-COMPARE harness (design)

Design for the last big functional-equivalence gap named in
[`audit/2026-07-31-a10-fe-coverage.md`](2026-07-31-a10-fe-coverage.md)
§implementation-plan item 5. Analysis + design only; no `src/` / test / doc
change ships from this document's scope. Every non-obvious claim below is
live-probed on the local 4-engine Docker stack (PG 16, MySQL 8, SQL Server
2022, Oracle 23c Free); the probe scripts live in the session scratchpad
(`a10p_probe.py`, `ora_rc3.py`, `warncheck.py`, `proto.py`) and the exact
outputs are quoted inline.

## The gap, precisely

`tests/fixtures/procedures/` holds the **same** ~33 routines in four dialects:
one hand-written T-SQL source (`procedures_sqlserver.sql`, 27 procedures + 5
functions + 1 trigger) and three transpiler-generated siblings
(`procedures_{oracle,postgresql,mysql}.sql`, "Regenerate via the transpiler
rather than editing by hand" — `SOURCES.md`). They are execution-comparable
**by construction**: call the same routine with the same fixed inputs on each
engine, the effects must match.

Today they are only **compile-validated**:
`tests/integration/test_live_syntax.py::test_procedures_fixture_is_valid_live`
transpiles the whole T-SQL file to each target and asks the engine "does this
load?" (Oracle via `USER_ERRORS` to catch lazy-INVALID compiles). Nothing ever
*calls* a routine. That misses every semantic defect a valid-but-wrong body
carries — and the very first prototype run below surfaced two such defects that
the compile gate passes clean.

## 1. Inventory

Derived by reading `procedures_sqlserver.sql` end to end and cross-reading the
generated PG/Oracle signatures. Column key: **Effect** = the observable
class(es) — `RET` scalar return, `OUT` output param(s), `RS` result set(s),
`TBL` table state, `TVF` table-valued, `TRG` trigger side-effect; **Seed** =
tables that must exist/be populated for a fixed-input call; **Comparable** =
enroll now / needs-seed / excluded-with-reason.

### Functions (5)

| Routine | Signature (inputs → out) | Effect | Touches | Deterministic? | Comparable |
|---|---|---|---|---|---|
| `func1` | `() → datetime` = `DATEADD(day,-3,GETDATE())` | RET | — | **No** (`GETDATE`) | Excluded: nondeterministic-clock. *(Lever: it is a fixture stub — redefining it to a constant makes its ~5 dependents comparable; see §3.)* |
| `func2` | `(9 args) → varchar(4000)` builds a JSON blob | RET | reads `tbl_9`; calls `func1`/`func3`/`func4` | No (`func1`) + table read | Excluded: nondeterministic-clock + needs-seed |
| `func3` | `(@key,@def) → nvarchar(400)` = `@def` (passthrough stub) | RET | — | Yes | **Enroll now** — 0 warnings, no tables |
| `func4` | `(@payload,@secret) → nvarchar(max)` = hex `HASHBYTES('SHA2_256', @payload+@secret)` | RET | — | Yes | Enroll (tsql↔mysql*) — but **encoding divergence + PG defect**, see below |
| `func5` | `(@s,@delim) → TABLE` = `STRING_SPLIT` | TVF | — | Yes | Excluded on PG (`UNIQUE-1154`, no TVF equiv, not generated); tsql/mysql/oracle only |

`func4` is the sharpest illustration in the whole corpus (prototype, §2/§5):
the transpile is **0-warning clean** to all three targets, yet
- tsql returns `13B33575…6E06`, oracle returns `61A4E403…45B6` — **different
  digests**. `HASHBYTES` hashes the `NVARCHAR` (UTF-16LE) bytes on SQL Server;
  Oracle `STANDARD_HASH`/PG `digest` hash the `VARCHAR2`/`text` (UTF-8) bytes.
  Inherent encoding divergence — not normalizable, ledger class `encoding-inherent`.
- PG errors at call: `function sha256(text) does not exist` — PG's `sha256`
  takes `bytea`. **Real unwarned defect** (needs `sha256(convert_to(x,'UTF8'))`
  / a `bytea` cast). Ledger class `defect-pending-fix`, feeds BLUE.

### Procedures (27)

Grouped by effect shape (params abbreviated; every proc opens with
`SET NOCOUNT ON` → a benign `UNIQUE-1193`, and most take a trailing
`@col_2 int=NULL` "row cap" arg that becomes `SET ROWCOUNT` → also `1193`,
dropped-to-comment: **must always be called with `@col_2 = NULL`** so the cap
branch is skipped and the drop is a genuine no-op).

| Routine | Effect | Seed tables | Comparable / ledger reason |
|---|---|---|---|
| `proc_11` | TBL (plain `INSERT tbl_7`) | `tbl_7` (empty) | **Enroll now** — only `1193` |
| `proc_27` | TBL (cascade `DELETE tbl_8/6/2/3`) | `tbl_2,3,6,8` (rows) | **Enroll now** — only `1193` |
| `proc_10` | TBL (`UPDATE tbl_7`) + `RAISERROR` on rowcount≠1 | `tbl_7` (rows) | Enroll (needs-seed); mysql adds `1163` |
| `proc_15` | TBL (`DELETE tbl_7`) + RAISERROR | `tbl_7` | Enroll (needs-seed) |
| `proc_16` | TBL (`UPDATE tbl_8`) + RAISERROR | `tbl_8` | Enroll (needs-seed) |
| `proc_18` | TBL (`DELETE tbl_8`) + RAISERROR | `tbl_8` | Enroll (needs-seed) |
| `proc_19` | TBL (`UPDATE tbl_6`, 20-col) + RAISERROR | `tbl_6` | Enroll (needs-seed) |
| `proc_21` | TBL (`DELETE tbl_6`) + RAISERROR | `tbl_6` | Enroll (needs-seed) |
| `proc_22` | TBL (`UPDATE tbl_3`) + RAISERROR | `tbl_3` | Enroll (needs-seed) |
| `proc_24` | TBL (`DELETE tbl_3`) + RAISERROR | `tbl_3` | Enroll (needs-seed) |
| `proc_13` | OUT `@where NVARCHAR(MAX)` (WHERE-clause builder) | — | Enroll (no seed) — `1193`+`1152` (SQL_VARIANT param; call without `@val`) |
| `proc_14` | OUT `@query`,`@page NVARCHAR(MAX)` (paging) | — | **Enroll now** — only `1193`, no tables |
| `proc_7` | OUT `@col_6 uuid` + TBL `INSERT tbl_3` | `tbl_3` | OUT excluded `generated-key` (`NEWSEQUENTIALID`); TBL comparable minus the PK |
| `proc_8` | OUT `@col_93 int`(identity) + TBL `INSERT tbl_8` | `tbl_8` | **Excluded `degrade-output-clause`** — `UNIQUE-1191` "OUTPUT inserted.col_93 dropped": the identity capture is lost → OUT wrong. Real defect, feeds BLUE |
| `proc_9` | OUT `@col_31 int`(identity) + TBL `INSERT tbl_6` | `tbl_6` | Excluded `degrade-output-clause` (same `1191`) |
| `proc_1` | RS (top-1 over `tbl_1..4` + literal UNION ALL) | `tbl_1,2,3,4` | Enroll tsql→{oracle,mysql}; **PG excluded `resultset-pg-invalid`** (see §2) |
| `proc_3` | RS (`SELECT … tbl_5`) | `tbl_5` | Enroll tsql→{oracle,mysql}; PG excluded |
| `proc_5` | RS (6-table join, `WITH(NOLOCK)`) | `tbl_1,2,6,10,11,12` | Enroll tsql→{oracle,mysql}; PG excluded |
| `proc_25` | RS (big correlated-subquery report, `func5`, `OPTION(RECOMPILE)`) | 10 tables | Excluded: nondeterministic-clock (`func1`) unless frozen; PG excluded |
| `proc_2` | TBL+RS, `func1`, `NEWSEQUENTIALID` | `tbl_1,2,3` | Excluded: nondeterministic-clock + generated-key |
| `proc_4` | TBL(`UPDATE tbl_6`)+RS, `func1` | `tbl_6,7,8,9` | Excluded: nondeterministic-clock (freeze lever) |
| `proc_6` | TBL(`INSERT tbl_6`)+RS, `func1`,`func2` | many | Excluded: nondeterministic-clock + needs `func2` |
| `proc_26` | TBL(`UPDATE tbl_6` ×2)+RS, `func1` | `tbl_1,2,6,9` | Excluded: nondeterministic-clock (freeze lever) |
| `proc_12` | RS via `sp_executesql` + `EXEC proc_13/proc_14` | `tbl_7` | Excluded: dynamic-sql |
| `proc_17` | RS via `sp_executesql` | `tbl_8` | Excluded: dynamic-sql |
| `proc_20` | RS via `sp_executesql` | `tbl_6` | Excluded: dynamic-sql |
| `proc_23` | RS via `sp_executesql` | `tbl_3` | Excluded: dynamic-sql |

### Trigger (1)

`col_173` on `tbl_6 FOR UPDATE` → `INSERT tbl_8` when `UPDATE(col_32)`; uses
`func1`. Excluded (first wave): needs the update chain + `func1`; later wave once
table-state procs are green.

### Inventory roll-up

- **Enroll-now (no seed):** `func3`, `func4`†, `proc_11`, `proc_14`, `proc_13` — 5.
- **Enroll with seed (deterministic, benign warnings):** `proc_27`, `proc_10/15/16/18/19/21/22/24` (single-table DML), `proc_1/3/5` (RS, non-PG), `proc_7`-TBL — ~13 more.
- **Excluded-with-reason:** nondeterministic-clock (`func1,func2,proc_2/4/6/25/26`), generated-key (`proc_7`-OUT, `proc_2`), degrade-output-clause (`proc_8/9` — defects), dynamic-sql (`proc_12/17/20/23`), resultset-pg-invalid (`proc_1/3/5/25` PG target — defect), tvf-no-pg-equiv (`func5` PG), encoding-inherent (`func4` oracle/mysql), trigger-complex (`col_173`).

†`func4` enrolls only for pairs where the hash byte-encoding agrees; today
that is effectively none across the NVARCHAR boundary — carried as a
`defect-pending-fix` (PG) + `encoding-inherent` (oracle/mysql) example, valuable
precisely because it is the canonical "0 warnings, still wrong" specimen.

## 2. Effect capture per engine (live-probed)

Four effect classes, each with a per-engine capture path. The tricky driver
paths were probed live; working snippets below.

### Scalar return (`func3`, `func4`)
`SELECT fn(args)` (`… FROM dual` on Oracle), `fetchall()[0][0]`. Trivial.

### Result sets (`proc_1/3/5`, and the SELECT tail of RS procs) — 4 *different* conventions
The transpiler lowers a T-SQL "bare `SELECT` returns rows" body differently per
target, so the *capture* differs per target:

- **tsql (source), pymssql:** `EXEC proc @a=…` then `cur.fetchall()`.
  Probed: `EXEC dbo.zz_rs @a=5` → `[(5, 6)]`.
- **mysql, pymysql:** `cur.callproc("proc",(args…)); cur.fetchall()`.
  Probed: `callproc("zz_rs",(5,0))` → result rows `((5, 6),)`.
- **oracle:** the body's bare `SELECT` becomes a synthesized
  `RESULT_CURSOR OUT SYS_REFCURSOR` (confirmed in `procedures_oracle.sql`:
  `proc_1 … RESULT_CURSOR OUT SYS_REFCURSOR`; mechanism documented in
  `docs/rationale/procedural/bare-result-select-to-refcursor.md`). Capture:
  **bind a separate `Cursor` object directly** —
  ```python
  out_cur = conn.cursor()
  cur.callproc("proc_1", [*in_args, out_cur])   # cursor is the OUT arg
  rows = out_cur.fetchall()
  ```
  Probed: `[(5, 6)]`. **Do NOT use `cur.var(oracledb.CURSOR)`** for the OUT
  refcursor — that path *hangs* indefinitely against this stack (probed twice,
  killed at 2 min and 5 min; the direct-`Cursor`-bind returns immediately). This
  is a hard harness constraint.
- **postgresql — BROKEN TODAY.** The generated PG body is a bare
  `SELECT … ;` (no `INTO`) inside a `plpgsql` `PROCEDURE`. It **compiles** (so
  the current compile-gate passes it) but **errors at CALL**:
  probed `CALL zz_rs(5)` → `SyntaxError: query has no destination for result
  data` (SQLSTATE 42601). So `proc_1/3/5/25` are non-runnable on PG as
  generated. Two runnable shapes both probed working and are the fix options
  for the architect:
  - `RETURNS TABLE(col type…)` function + `RETURN QUERY` → call `SELECT * FROM
    fn(args)` (probed `[(5, 6)]`); or
  - `INOUT rc refcursor` procedure + `OPEN rc FOR …` → `CALL proc(args,'cur');
    FETCH ALL FROM cur` inside a txn (probed `[(5, 6)]`).
  Until fixed, the ledger excludes the PG target for RS procs
  (`resultset-pg-invalid`, defect-pending-fix); the harness re-includes them
  automatically the moment the transpiler emits a runnable shape.

### OUT scalar params (`proc_13/14`; `proc_7/8/9` where in scope)
- **tsql, pymssql:** `cur.callproc("proc",(inp, pymssql.output(int)))` returns a
  tuple with the OUT slot filled — probed `(3, 30)`. (Wrapper form also works:
  `DECLARE @o int; EXEC proc @res=@o OUTPUT; SELECT @o` → `[(30,)]`.)
- **oracle, oracledb:** `v = cur.var(oracledb.NUMBER); cur.callproc("proc",
  (inp, v)); v.getvalue()` — probed `30`. (Strings: `cur.var(oracledb.STRING,
  size)`; a scalar `var` does NOT hang — only the `CURSOR` var does.)
- **mysql, pymysql:** `callproc`'s return tuple carries the INs, not the OUTs;
  read the OUT via the driver's session vars: after `cur.callproc("proc",(inp,
  0))`, `SELECT @_proc_1` → probed `[(50,)]` (`@_<procname>_<argindex>`).
- **postgresql:** a plpgsql procedure's OUT params come back as a result row of
  `CALL`: `cur.execute("CALL proc(%s, NULL)"); cur.fetchone()` (standard psycopg
  behavior; the harness passes `NULL` placeholders for OUT positions).

### Table state (`proc_11/27/10/15/16/18/19/21/22/24`, inserts)
The existing `FuncCase` pattern (`test_challenge_live._execute`): drop seed
tables → create + seed → run the routine for effect → `SELECT <cols> FROM
<table> ORDER BY <key>` probe → `normalize_rows` → drop. DDL auto-commits on
MySQL/Oracle, so drop **before and after** on every engine (already the pattern).

### Timing (prototype, `proto.py`)
End-to-end `func4` across all four engines (connect + create + call) ran in
well under a second wall-clock with warm containers (internal timings:
`conn≈0.0–0.1s`, `call≈0.0s` per engine). The dominant costs are Oracle
**cold**-connect (seconds, once per session) and per-routine **seed DDL**. See
§4 for the extrapolated nightly budget.

## 3. Harness shape

Proposed layout (mirrors the challenge-FE trio so the repo has one FE idiom):

```
tests/integration/test_procedures_fe_live.py   # the nightly test (like test_challenge_live.py)
tests/helpers/procedures_fe_spec.py            # RoutineCase specs + seed data
tests/helpers/procedures_fe_exclusions.py      # named ledger (like challenge_fe_exclusions.py)
tests/unit/test_procedures_fe_ratchet.py       # offline monotonic floor + no-silent-loss
```

**Per-routine declarative spec** (one dataclass, no per-engine branching in the
spec — the branching lives in typed capture helpers):

```python
@dataclass(frozen=True)
class RoutineCase:
    name: str                       # "proc_11"
    kind: str                       # "scalar" | "resultset" | "out" | "table_state"
    seed: tuple[str, ...] = ()      # table names this routine needs (subset of the fixture DDL)
    args: tuple[Any, ...] = ()      # fixed call inputs (source-dialect order; @col_2 always NULL)
    out_types: tuple[str, ...] = () # for kind="out": ("str",) / ("int",) driver bind types
    probes: tuple[str, ...] = ()    # for kind="table_state": portable "SELECT … ORDER BY …" per seed table
```

**Transpile at runtime**, per routine, tsql→target (consistent with
`test_challenge_live` / `test_live_syntax`); the committed generated fixtures
are the reference/oracle, not the thing executed — so the test tracks the
*current* transpiler, not a stale artifact. Per-routine transpile is safe for
the whole start set (self-contained routines); the only routines that need
whole-script context are the `sp_executesql` orchestrators (`proc_12/17/20/23`),
which are excluded anyway.

**Shared seed module.** Reuse the T-SQL fixture's own DDL block
(`procedures_sqlserver.sql` lines 1–185: `tbl_1`…`tbl_15`) transpiled per engine
as the schema, plus a small deterministic `INSERT` set keyed for reproducibility
(fixed ints/strings, fixed `datetime` literals — never `GETDATE`). Seed only the
tables a routine's spec names, to keep each case cheap and isolated.

**Warning gate — the key departure from `test_challenge_live`.** That test does
`if result.warnings: pytest.skip(...)` — but §1 shows **almost every** procedure
emits at least `UNIQUE-1193` (`SET NOCOUNT ON skipped`), so a blanket skip would
compare *nothing*. The procedures harness must gate on a **per-code BENIGN
allowlist**; any warning outside it means "documented degrade → skip". Seed
allowlist (probed benign, no observable-effect impact):
- `UNIQUE-1193` — `SET NOCOUNT ON` / `SET ROWCOUNT @col_2` dropped (no-op when
  called with `@col_2=NULL`, which the spec guarantees).
- `UNIQUE-1196` — "was T-SQL table variable …" (table-var → temp-table rewrite;
  purely informational).

Everything else stays a skip-with-reason, and each such code is what lands a
routine on the ledger: `UNIQUE-1191` (OUTPUT dropped → `proc_8/9`),
`UNIQUE-1231` (embedded DML raw-converted), `UNIQUE-1152` (SQL_VARIANT type),
`UNIQUE-1154` (no TVF equiv → `func5` PG).

**Reuse the comparator verbatim:** `normalize_rows` / `normalize_cell` /
coarser-operand numeric tolerance from `tests/helpers/corpus_diff.py`, including
`empty_as_null=True` whenever Oracle is either side (Oracle folds `'' → NULL`).
OUT scalars and RET values are wrapped as a single-row single-cell "result set"
so they flow through the same normalizer.

**Cleanup contract (leftover-object hygiene).** Serial execution (no parallel —
shared DBs, shared table names). Per case, on every engine: (1) drop seed tables
+ the routine itself *before* (clear a prior crash's leftovers); (2) create,
run, probe; (3) drop again *after*. Reuse
`engine_runner.EngineRunner.drop_all_objects` (catalog-driven view/routine drop,
already handles overloads and Oracle's lazy catalog) for routine teardown, plus
explicit `DROP TABLE` for the seed set. This is the validity-tooling lesson from
prior Oracle sweeps: a leftover INVALID object contaminates the next same-target
case.

**Failure reporting** — per `(routine, source→target, effect)`, the same
message shape as `test_func_case_result_matches`: the normalized source vs
target value, plus the emitted SQL, so a diff is a self-contained RED finding.

**`func1`-freeze lever (optional, P3).** `func1` is a fixture stub, not the
subject under test; before running its ~5 dependents (`proc_2/4/6/25/26`),
`CREATE OR REPLACE` it to return a *fixed constant* on every engine. That turns
"nondeterministic-clock" routines into comparable ones without touching the body
being validated. Architect call (§5).

## 4. Enrollment + ratchet

**Start set (P1, ~5 routines, zero seed):** `func3`, `proc_14`, `proc_13`
(scalar/OUT, no tables); `proc_11` (INSERT, one empty seed table); `func4`
carried as the documented divergence specimen. Immediately extend (P1 tail) to
the single-table DML procs + `proc_27` once the seed module lands (~13 more).

**Exclusions ledger** — `tests/helpers/procedures_fe_exclusions.py`, identical
structure to `challenge_fe_exclusions.py` (`@dataclass Excluded(id, tag, reason,
match)`; the ledger IS the visibility, one line per exclusion, no silent cap).
Proposed `VALID_TAGS`:

```
nondeterministic-clock   # func1/GETDATE-dependent (removable via freeze lever)
generated-key            # NEWSEQUENTIALID / IDENTITY value in the observable
degrade-output-clause    # UNIQUE-1191 etc. → defect-pending-fix (BLUE)
dynamic-sql              # sp_executesql / EXEC-orchestrated bodies
resultset-pg-invalid     # bare SELECT-in-PROCEDURE 42601 → defect-pending-fix (BLUE)
tvf-no-pg-equiv          # func5 on PG (UNIQUE-1154)
encoding-inherent        # NVARCHAR/UTF-16 vs UTF-8 hash bytes (func4)
trigger-complex          # col_173, deferred wave
```

**Ratchet** — `tests/unit/test_procedures_fe_ratchet.py`, offline (no DB), same
discipline as `scripts/architecture_ratchets.py` / the A10-H ratchet, but
because enrollment here is curated (not corpus-derived) the two-sided invariant
is:
- `enrolled_count >= ENROLLED_FLOOR` — floor only ever moves **UP** as routines
  land (a regression that drops a routine from the enrolled set fails);
- `len(enrolled) + len(ledger) == total_routines_in_fixture` — the **no-silent-
  loss** invariant: every routine is either enrolled or named on the ledger,
  nothing falls through. A new routine added to the fixture must be classified.
- ledger `defect-pending-fix` count is reported (drives BLUE) but need not floor.

**Nightly wiring.** Add one step to `.github/workflows/challenge-live.yml` — it
already stands up all four engines including the Oracle Free container and
exports the four `UNIQUE_TEST_*_URL` vars:
```yaml
- name: Run procedures FE result diff
  env: { …the same four URLs… }
  run: pytest tests/integration/test_procedures_fe_live.py -v -rA
```
**Wall-time estimate.** Prototype warm-pair execution is sub-second (§2). The
real cost is per-routine seed DDL + Oracle. Budget ~18 enrolled routines ×
≈3 targets × (create-seed + create-routine + call + probe + drop) at a
conservative ~1–2 s/engine-cycle ≈ **3–6 min** added to a nightly job that
already provisions and runs against the same containers. No silent caps: every
routine is a named, visible parametrization; a slow engine shows as a slow test,
not a skipped one.

## 5. Risks / decisions for the architect

1. **PG result-set procedures are runtime-invalid.** The bare
   `SELECT … ;`-in-`PROCEDURE` form (proc_1/3/5/25) compiles but throws 42601 on
   CALL (probed). Is this a transpiler defect to fix (emit `RETURNS TABLE` fn or
   `INOUT refcursor` proc — both probed working) or an accepted degrade? Either
   way the FE harness makes it visible; recommend **defect-pending-fix**, PG
   target ledgered until fixed. *(This is a headline finding for A10 in its own
   right — the compile gate is green on non-runnable output.)*
2. **Warning-gate allowlist is a policy call.** Which `UNIQUE-*` codes are
   "benign carrier, compare anyway"? The harness cannot function without one
   (every proc warns `1193`). Proposed seed: `{1193, 1196}` benign; everything
   else = skip-with-reason. Needs a maintainer blessing, and a rule for
   classifying new codes (default: degrade until proven benign).
3. **`func1`-freeze.** Acceptable to `CREATE OR REPLACE` the fixture's own
   `func1` stub to a constant to bring ~5 clock-dependent routines into scope?
   It changes a *helper*, not the routine under test, and the FE claim is about
   the transpiled body — but it is a deliberate deviation from "run the fixture
   as written". Recommend yes, gated behind an explicit spec flag so it is
   visible per-case. (P3 scope.)
4. **Expected-divergence routines / documented degrades.** A routine whose
   transpile carries a *semantic* warning (e.g. a `[limit]`-grade construct) is
   handled uniformly: it is on the ledger with its warning code as the reason,
   never compared — same contract the corpus uses. `func4`'s encoding
   divergence is the concrete case: not normalizable, `encoding-inherent`, kept
   for its illustrative + PG-defect value.
5. **Generated keys.** `proc_7` OUT is a `NEWSEQUENTIALID` GUID and `proc_8/9`
   OUTs are IDENTITY values — the OUT is excluded (`generated-key`), but the
   *table state* those procs write is still comparable if the probe projects
   away the surrogate PK (probe `SELECT <non-key cols> …`). Decision: enroll the
   TBL effect of `proc_7` with a PK-excluding probe, or defer. `proc_8/9` also
   carry the `UNIQUE-1191` OUTPUT-dropped defect independently.
6. **Oracle driver constraint (not negotiable).** Refcursor OUT must be captured
   by binding a **plain `Cursor`** object to `callproc`; `cur.var(oracledb.
   CURSOR)` hangs on this stack. Bake the working helper into the harness.
7. **Whole-file vs per-routine transpile.** Recommend per-routine at runtime
   (tracks current transpiler); the four `sp_executesql` orchestrators that need
   whole-script call-site rewriting are excluded (`dynamic-sql`) so nothing in
   scope loses context.

**Estimated size — medium.** `test_procedures_fe_live.py` ≈ 200–250 lines
(capture helpers dominate), spec+seed ≈ 120, exclusions ledger ≈ 60, ratchet
test ≈ 40, workflow step ≈ 8. Reuses `corpus_diff` and `engine_runner`
wholesale.

**Suggested brief split:**
- **A10-P1** — scaffold + comparator/warning-gate reuse + start set (scalar,
  OUT, single-table DML/table-state; no result sets). Highest value, smallest
  risk; lands `func3/func4/proc_11/13/14/27` + the single-table DML procs and
  the ledger + ratchet + nightly step.
- **A10-P2** — result-set capture (tsql/mysql + Oracle refcursor), and the
  triage of the PG bare-SELECT defect (fix → auto-enroll, or ledger).
- **A10-P3** — `func1`-freeze → the clock-dependent report procs; the `col_173`
  trigger; `func5` TVF (non-PG).
