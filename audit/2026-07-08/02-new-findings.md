# 02 — New findings (v0.22.3)

Severity legend as in the 2026-07-02 audit: **S1** invalid/lost/semantically
changed output with no warning; **S2** degraded meaning or a guarantee that
doesn't hold; **S3** valid but suboptimal / cosmetic / drift.

---

## N1 (S1). Unbracketed real-data `IF [NOT] EXISTS` guard is dropped silently

```text
IN  (tsql):
    IF NOT EXISTS (SELECT 1 FROM cfg WHERE k = 'x')
    INSERT INTO cfg (k) VALUES ('x');
    GO

OUT (oracle, postgresql, mysql — all identical):
    INSERT INTO cfg (k) VALUES ('x');

warnings: []   unsupported: []
```

The guard condition queries **real data**, not a system catalog, yet it is
discarded: re-running the migration now inserts duplicates. The same happens
for `UPDATE` and `DELETE` bodies. This is the exact "silent semantic change"
class the no-silent-loss invariant forbids, reintroduced by the migration-guard
feature.

**Mechanism** (`src/unique/core/batch_splitter.py:270-282`): a batch matching
`IF [NOT] EXISTS(…)` is routed to the procedural engine (which preserves the
condition) only when it contains a `BEGIN` block **and** has no catalog
reference:

```python
if (
    dialect == "tsql"
    and _TSQL_BEGIN_BLOCK_RE.search(without_comments)   # <- wrong conjunct
    and not _CATALOG_REF_RE.search(without_comments)
):
    return BatchType.PROCEDURAL
return BatchType.SET_OPTION   # guard-drop path
```

The unbracketed single-statement form — by far the most common spelling in real
migration scripts — falls through to the guard-drop path regardless of what the
condition queries. The module's own comment states the rule correctly ("A
real-data condition must not have its guard dropped"); the code just doesn't
implement it for this form. The `BEGIN … END` form works:

```text
IF NOT EXISTS (SELECT 1 FROM cfg WHERE k = 'x') BEGIN INSERT … END
  → (oracle) BEGIN FOR unique_guard IN (SELECT 1 FROM DUAL WHERE NOT EXISTS(…)) LOOP INSERT …
```

**Fix:** drop the `_TSQL_BEGIN_BLOCK_RE` conjunct — route any non-catalog
`IF [NOT] EXISTS` to the procedural engine, `BEGIN` or not. Add probes for the
single-statement INSERT/UPDATE/DELETE guards in each direction, and an FE
scenario that runs a guarded INSERT twice and asserts one row.

Related quality gap (S3): `IF 1=1 INSERT INTO …` (non-EXISTS condition, no
`BEGIN`) degrades to `-- UNIQUE: Unhandled expression type: IfBlock` — warned,
so the invariant holds, but a plain `IF <cond> <stmt>` is common enough in
T-SQL scripts to deserve a real translation.

## N2 (S1). PostgreSQL → T-SQL temp-table rename is not script-wide

```text
IN  (postgresql):
    SELECT * INTO TEMPORARY tmp FROM t;
    SELECT a FROM tmp;
    DROP TABLE tmp;

OUT (tsql):
    SELECT * INTO #tmp FROM t
    GO
    SELECT a FROM tmp        -- reads a *permanent* table that doesn't exist
    GO
    DROP TABLE IF EXISTS tmp -- drops the wrong name

warnings: []
```

Only the `INTO TEMPORARY` clause knows the table is temporary, so only it gets
the `#` prefix; every later reference keeps the bare name. The output creates
one table and reads/drops another — a runtime error (or worse, if a permanent
`tmp` exists, silent wrong results). The forward direction (T-SQL → PG) is
consistent because `#tmp` is lexically distinctive everywhere it appears.

**Fix:** when a `SELECT INTO TEMPORARY <name>` (or `CREATE TEMPORARY TABLE`)
is renamed for T-SQL, propagate the rename to subsequent statements of the
script (the transpiler already holds the whole script; a per-script rename map
applied during emission would cover `FROM`/`JOIN`/`DROP`/`INSERT INTO`).
Round-trip test: PG temp-table script → T-SQL → PG must reference one table.

## N3 (S2). Source-syntax validation false negatives → silent garbage output

```text
validate_source("banana banana", <any dialect>)        → []   (valid!)
validate_source("CREATE TALBE t (id INT)", "tsql")      → []   (valid!)

transpile("banana banana", "tsql", "postgresql").sql   → "banana AS banana;"
warnings: []   unsupported: []
```

The garbage detector (`src/unique/core/validation.py:168`) flags a batch that
parses to a *single bare* `Column/Identifier/Literal/Boolean/Null`, but:

- **two** bare tokens parse as an aliased column (`exp.Alias`) and pass;
- a typo'd statement head (`CREATE TALBE …`) becomes a sqlglot
  `Command` fallback, which line 65 deliberately exempts.

Since v0.21.0 the API/CLI/web *refuse* invalid input based on this function, so
a false negative flows straight through and the transpiler emits an
executable-looking fragment (`banana AS banana;`) **with no warning** — a
no-silent-loss violation on top of the validation gap. (Single `banana`,
`hello; world;`, `SELCT`/`FORM` typos are all correctly caught.)

**Fix:** extend the bare-statement check to `exp.Alias`/expression-only
statements whose source has no recognized statement keyword, and treat an
unknown-verb `Command` at a batch head as invalid for the *source* dialect.
Independently, the transpiler should warn whenever a batch's parse result is a
bare expression rather than a statement.

## N4 (S3). STATUS claims the guard round-trip is FE-exercised; it isn't — and via the public API the catalog guard never round-trips

`docs/STATUS.md` (v0.22.3):

> the idempotent `FROM DUAL` guard-loop Unique emits now round-trips back to an
> `IF` … — exercised, with the `ALTER TABLE ADD` guard, by the
> functional-equivalence harness (Scenario C).

`tests/functional_equivalence/coverage-matrix.md` ("Not exercised here (by
design)") says the opposite — the round-trip is covered only by the *unit*
tests (`test_dual_guard.py`), which drive the procedural transformer/emitter
directly. Through the public `transpile()` API, the guard Unique itself emits
for Oracle (catalog probe on `user_objects`) **degrades to a carrier comment on
every target** — warned and registered as unsupported (so not a silent-loss
violation), because `USER_*` views exist only on Oracle:

```text
tsql IF NOT EXISTS(sys.objects…) CREATE TABLE → oracle guard-loop → tsql:
    -- UNIQUE: anonymous PL/SQL block has no top-level tsql equivalent; …
```

Two actions: (a) fix the STATUS sentence (the FE claim); (b) consider mapping
the *known, self-emitted* guard shapes back to the target's catalog
(`user_objects` → `sys.objects` / `information_schema`) so Unique's own output
round-trips executable — today A→B→A of a guarded migration loses the
statement. Note the carrier also keeps Oracle spellings inside
(`EXEC sp_executesql q'[…]'`, `NUMBER(10)`), misleading if a user uncomments it.

Meanwhile the *data* guard (block form) round-trips correctly:
`IF NOT EXISTS(SELECT … FROM cfg …) BEGIN INSERT … END` → Oracle FOR-loop →
back to the original `IF (NOT EXISTS …) BEGIN … END`. ✔

## N5 (S3). False-positive warning on a successful FOR→IF round-trip

The successful data-guard round-trip above still appends:

> FOR loop has no direct T-SQL equivalent. Manual conversion to WHILE loop
> required.

(`src/unique/core/procedural/transformer/tsql.py:258`) — emitted before the
guard-shaped FOR is recognized and converted to an `IF`. A warning that cries
wolf erodes the signal the no-silent-loss invariant depends on; suppress it
when the guard rewrite succeeds.

## N6 (S3, API). `/api/v1/validate` and `/api/v1/detect` have no size cap

`TranspileRequest.sql` carries `max_length=MAX_SQL_BYTES`, but
`ValidateRequest.sql` and `DetectRequest.sql` do not — both endpoints do
CPU-bound work (full parse / regex scoring) on unbounded input, re-opening a
corner of the A2 DoS surface. One-line fix each.

## N7 (S3, API). `Content-Disposition` built from unsanitized client filename

`transpile_file` interpolates the uploaded filename into
`attachment; filename="{out_name}"`. A filename containing `"` or non-ASCII
breaks the header (Starlette encodes headers latin-1; h11 rejects CR/LF), which
surfaces as a 500 rather than an injection — still, sanitize the stem
(strip quotes/control chars, RFC 5987-encode non-ASCII) before echoing it.

## N8 (S3). Near-duplicate `unsupported` entries for one construct

`CREATE SCHEMA` → Oracle registers **two** overlapping entries
(`'CREATE SCHEMA sales has no Oracle equivalent'` and the carrier text
`'T-SQL CREATE SCHEMA has no Oracle equivalent — … original:'`); `sp_rename`
likewise. API consumers counting `unsupported` see doubled numbers. Deduplicate
at the reconciliation step that pairs carriers with result entries.

## N9 (S3, docs/skills). Drift

- `skills/SKILL-project-overview.md` still says **"Python 3.12 — the single
  supported/CI version"**; the project requires **3.13** (pyproject, CI,
  py313 linter targets). The layout sketch also still shows `core/converter.py`
  as a single file (now a package) and omits `mappings.py`/`validation.py`.
- README shows `docker run … jesusdf/unique:latest` with no note that images
  publish only on `v*` tags (2026-07-02 D4, still open).
- `docs/STATUS.md` opens three consecutive claims with "Most recently" —
  rewrite the paragraph on the next release per the state-docs discipline.

---

## Improvement opportunities (ordered by leverage)

1. **Raise the identity-mutation floor** from 0.33 toward the measured 0.38,
   and keep converting `test_cross_dialect.py` (291 survivors) and
   `test_comment_preservation.py` (12/15 survive) to
   present-AND-absent assertions.
2. **CI: assert engine coverage.** After the live jobs, fail if fewer than the
   expected engines were actually exercised (count non-skipped per-engine
   tests); today a broken ODBC install or an Oracle startup timeout silently
   shrinks validation to 2 engines.
3. **Resume the module-size work** along the seams the 2026-07-02 audit named:
   `procedural/parser.py` (2886) and `procedural/transformer/base.py` (2813)
   grew past their audited sizes, and `transpiler.py` more than doubled (1713)
   — it now hosts guard extraction/rewriting that could live beside the
   splitter.
4. **Docker digest pin + constraints file** for reproducible images (carry-over).
5. **Report the decode encoding** used by `/transpile/file` in a response
   header next to `X-Unique-Source-Dialect` (A5 residue).
