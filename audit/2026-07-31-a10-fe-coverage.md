# A10 — Functional-equivalence coverage audit

Measurement pass over the challenge corpus's execution-comparison coverage,
directed and executed by the architect (PURPLE session, 2026-07-31, HEAD at
the B36b/B45 merges). Analysis + live measurement only; no `src/` changes in
this document's scope. Reproduction scripts: `a10_sweep.py` (session
scratchpad; the methodology is fully described below so the numbers can be
re-derived).

## The suspicion being tested

`docs/TODO.md` A10 (maintainer, 2026-07-31): the FE execution-comparison
layer is far greener than the corpus — the nightly result-diff covers the
curated `FUNC_CASES` (~12) plus `[class=func]` challenge cases, while the
other ~900 corpus cases have parse/structural assertions only.

**Verdict: confirmed, precisely quantified below.** The comparable-but-
uncompared set is 670 cases; sweeping just its self-contained subset (501
cases) immediately surfaced 86 unwarned problem pairs, including ~20 that
error outright at runtime on the target engine.

## Headline numbers

Challenge corpus at measurement time: **960 cases**
(tsql 175, oracle 187, postgresql 289, mysql 309).

| Cut | Count | Notes |
|---|---|---|
| FE-comparable (single-statement, deterministic, SELECT) | 691 | `is_comparable` predicate from `tests/helpers/corpus_diff.py` applied to the case body |
| — of which enrolled in live result-diff (`[class=func]`) | 21 | the only cases whose VALUES are compared today |
| — comparable but UNENROLLED | 670 | 530 `[fixed]` + 140 `[limit]` |
| — — `[limit]` (excluded: approved divergences) | 140 | comparing for equality is meaningless by definition |
| — — `[fixed]`, needs tables/setup | 29 | enrollable later with probe scaffolding (the `FuncCase` pattern) |
| — — **`[fixed]`, fully self-contained (literal SELECTs)** | **501** | executable with ZERO setup — swept below |
| Non-comparable remainder | 269 | non-SELECT (DDL/DML/procedural), multi-statement, or nondeterministic per `_NONDETERMINISTIC` |

## The live sweep of the 501 self-contained cases

Method: each case executed on its source engine; transpiled to each of the
other 3 engines; **pairs whose transpile result carries any warning or
unsupported entry are excluded** (a warned degrade is the documented,
acceptable outcome — the corpus rule; the first sweep iteration counted
these and produced 215 false "mismatches", mostly comment-only carriers
returning 0 rows); remaining pairs executed on the target and compared via
`normalize_rows`.

| Bucket | Pairs |
|---|---|
| Warned on that target (excluded — documented degrade) | 669 |
| Clean value match | 748 |
| **DIFF — different result, no warning** | **66** |
| **EXEC-FAIL — target engine rejects the output at runtime, no warning** | **20** |

Source-side execution failures: a handful of cases (counted inside
`exec_fail` in the raw JSON) failed on their own source engine — case-quality
issues (e.g. `red2-ts-at-identity-passthrough` reads `@@IDENTITY` with no
prior INSERT: session-dependent, arguably a vacuous scenario per the corpus
rules).

## Taxonomy of the 86 unwarned problem pairs

Full pair list preserved in the raw JSON (session scratchpad
`a10_result2.json`); classes with representative cases:

### T1 — harness normalization gaps (comparator, not transpiler)
The values are equal; the comparator isn't normalizing representation:
- **string-vs-datetime driver types**: MySQL returns `'2020-01-01 10:30:00'`
  (string), targets return a datetime → isoformat `'…T…'`
  (`my-timestampadd`, `red2-my-dateadd-compound-interval`, `my-cast-truncate`
  time column, `pg-todate2` tz-aware-vs-naive).
- **interval driver objects**: `IntervalYM(years=1, months=2)` (oracledb)
  vs `timedelta` (`ora-interval-out`, `ora-numtointerval` — the YM leg;
  note the pg side renders `425 days`, which is also a VALUE question:
  1 year 2 months ≠ a fixed day count — borderline T4).
- **JSON canonicalization**: `'[1, 2]'` vs `'[1,2]'` vs psycopg's parsed
  dict repr (`my-json-*` family).

### T2 — precision/scale family (policy decision needed)
Same mathematical value at different scale/precision, or engine-default
display scale (`*-decimal-scale`, `*-div-precision`, `*-float-precision`,
`my-avg-precision2`, `*-num-to-str`, `my-agg-boolean→oracle`,
`ora-div-mult2→tsql` `1.0` vs `0.999999`). The maintainer's historical BLUE
rule was "same value + precision diff = acceptable `[fixed]`" — but that
tolerance is nowhere encoded. **Decision needed**: numeric-tolerance
comparison in the harness (turns most of T2 into matches) vs. warning on
precision-changing conversions. Until decided, these belong on the
exclusions ledger, named.

### T3 — inherent, already-documented divergence classes, missing their warning
- Oracle `'' ≡ NULL` (`my-left-neg`, `my-repeat-neg` → oracle) — documented
  in `docs/rationale/strings-collation.md`; unwarned here.
- unordered `GROUP_CONCAT` vs synthesized-deterministic `LISTAGG` order
  (`my-gc-order`) — the D1 aggregates entry documents the synthesis; the
  source's order is nondeterministic by contract.
- supplementary-plane NCHAR (`ts-nchar-hex`: live SQL Server yields NULL,
  every target yields 😀) — the known emoji/collation front.
- session-context identity (`reda-ora-user-function`: `USER` differs by
  engine/connection by nature) — belongs in the session-dependent exclusion
  class next to `_NONDETERMINISTIC`.

### T4 — real functional defects, unwarned (the RED-grade harvest)
Roughly 25–30 pairs; the concrete list, by mechanism:
- **Unwarned runtime-invalid output (guardrail-4 class):**
  `pg-bool-repr`/`my-bool-char` → tsql+oracle (broken CAST emission,
  "missing AS keyword"); `po-distinct-case`/`my-having-noagg` → tsql
  (derived table `uq_d`/`uq_h` with an unnamed column);
  `my-dateadd`/`my-str-plus-interval` → oracle+pg (string-typed date +
  INTERVAL arithmetic, needs a date cast); `ora-cast-int-edge` → tsql+pg
  (`'3.9'`→INT: Oracle rounds, targets reject); `my-left-float`/
  `my-repeat-float` → pg (`left(unknown, numeric)` no such function);
  `my-insert-zeropos` → pg (negative substring length);
  `postgresql-qdrop-FOR\s+UPDATE` → oracle (ORA-02014 FOR UPDATE +
  DISTINCT).
- **Unwarned wrong values:** `ts-cast-int-datetime` → mysql (date vs
  `19000102` integer); `ts-compress` → mysql (GZIP vs ZLIB container);
  `my-insert-oob`/`my-insert-zeropos` → oracle (MySQL's out-of-bounds
  `INSERT()` returns the original string; the emulation doesn't guard);
  `my-left-float`/`my-repeat-float` → oracle (MySQL rounds float length
  args; emulation truncates); `my-ts-to-date` → oracle (Oracle DATE keeps
  the time component); `ora-lpad-tochar` → pg (TO_CHAR `#` overflow mask
  fidelity); `pg-baseconv` → mysql (base-conversion arguments);
  `pg-chr-ascii-unicode` → mysql (multibyte CHR/ASCII); `ts-frac-seconds`
  → pg+mysql (fractional-second rounding .123456→.123457);
  `my-cast-binary2` → tsql (fixed-width BINARY padding).

Every T4 row is a ready-made RED-grade finding: the case is already in the
corpus, already minimal, already live-verified on its source — only the FE
check was missing. These feed the next BLUE round directly.

## What A10 changes going forward (implementation plan)

1. **Auto-enrollment harness** (brief A10-H): a nightly-marked test that
   derives the enrolled set mechanically — every `[fixed]`, comparable,
   self-contained case, minus a **named exclusions ledger** (one line per
   exclusion: case id, class T1–T4 or session-dependent, reason). No
   silent caps: the ledger IS the visibility. Warned pairs skip per the
   corpus rule (checked at transpile time, not via a static list).
2. **Comparator upgrades** (same brief): datetime/string, interval, and
   JSON canonicalization (kills T1); numeric tolerance once the T2 policy
   is decided (maintainer).
3. **Ratchet**: the exclusions-ledger size and the unenrolled-comparable
   count both get monotonic-downward floors checked in-suite (same pattern
   as `scripts/architecture_ratchets.py`).
4. **The 29 needs-tables cases**: enroll via the `FuncCase` probe pattern
   (setup + compare + rollback) — follow-up after the self-contained wave.
5. **Procedures corpus live-COMPARE** (brief A10-P): the 4-dialect
   same-routine fixtures are execution-comparable by construction — call
   each routine with fixed inputs on its engine, compare effects (result
   sets / out-params / table state). Today they are only live-VALIDATED
   (compile). Highest-value remaining gap; needs its own design (state
   setup/teardown per engine).
6. **T4 triage** is follow-up BLUE work (backlogged; the pairs are named
   above and in the raw JSON).

## Honest limitations of this measurement

- The self-containment predicate is a `FROM`-clause regex; a case reading
  session state (e.g. `@@IDENTITY`) passes it yet isn't truly
  self-contained — 2 such cases surfaced as source-side failures/diffs.
- Warned-pair exclusion uses the CURRENT transpiler's warnings; a future
  regression that silently drops a warning would move its pair INTO the
  compared set (and likely fail there — which is the desired direction).
- The sweep ran once, on one engine version set (the local Docker stack —
  PG 16, MySQL 8, SQL Server 2022, Oracle 23c); fractional-second and
  collation behaviors can vary across engine versions.
