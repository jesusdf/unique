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

- [x] **Residual invalid output ships WITHOUT a warning (P1) — CLOSED at the architectural floor (2026-07-17, `469917a`).** Six-direction residue driven ~770→133; every statement transpiles validly or carries a warning; pg→pg discovery 287→0. Remainder needs schema-aware transpilation. Full log [`docs/DONE.md`](DONE.md) §36.

### P0 — architecture plan (audit doc 04 — ADOPTED 2026-07-08)

- [x] **M3 final — DONE 2026-07-17 (`86f7c11`): IR-first is the expression engine.** The last architecture-plan milestone; scalar fragments route through the shared IR pipeline, text rewriters are the fallback (`UNIQUE_NO_IR_FIRST` kill-switch). Full log [`docs/DONE.md`](DONE.md) §39.
- [x] **Zero-reduction campaign (P2) — CLOSED at the floor, residue 133 → 16 (2026-07-17, `34d7338`).** Mechanism fixes (not waves) drove the six-direction live-syntax residue to 16, both Oracle directions 100.0% validity; remainder is the architectural floor (adversarial pg_regress, schema-dependent inference). Full log [`docs/DONE.md`](DONE.md) §40.
- [x] **Prune fallback-only text rewriters (P3) — CLOSED BY MEASUREMENT 2026-07-17.** 36/37 rewriters carry live fallback traffic; nothing safely prunable. Archived [`docs/DONE.md`](DONE.md) §42.

### P3 — hardening carry-overs (from 2026-07-02, still open)

- [x] **Module growth — DONE 2026-07-17.** All three oversized modules split (procedural/parser package, transformer `_expr.py` seam, `core/transpiler/` package). Full detail [`docs/DONE.md`](DONE.md) §37.
- [x] **tsql→mysql procedural DATEADD nested INTERVAL — FIXED 2026-07-17.** The normalize walk hoists a tsql `DateAdd`'s interval into the unit slot (was `INTERVAL (INTERVAL '-1' MONTH) DAY`). Archived [`docs/DONE.md`](DONE.md) §42.

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

## 4. T-SQL keyword coverage — ✅ DONE (archived [`docs/DONE.md`](DONE.md) §42)

`PROC`≡`PROCEDURE`, `CREATE OR ALTER`, and `BEGIN TRAN[SACTION]` all route and translate; covered by `tests/integration/test_tsql_keyword_alias.py` + `test_challenge.py` + `test_procedural.py`.
## 5. Procedural round-trip fidelity (challenge corpus)

New regression corpus at [`tests/fixtures/challenge/`](../../tests/fixtures/challenge/)
— one anonymized script per source engine collecting tricky constructs as they
are found; guarded by `tests/integration/test_challenge.py`. Cases are tagged
`[fixed]` (strictly guarded) or `[open]` (RED backlog). See the
[challenge-corpus skill](../skills/SKILL-challenge-corpus.md) for the red/blue
workflow.

- [ ] **BLUE batch IN PROGRESS — NOT over (per `SKILL-challenge-corpus.md`, the
      batch ends only when every `[open]` case is `[fixed]` or user-approved as a
      documented limit).** Landed so far (recorded in [`docs/DONE.md`](DONE.md)
      §41): RC-1b gate (DML+procedural), 21 built-in mappings, RC-3
      FK/CHECK/IDENTITY/COMMENT + Oracle ON UPDATE, RC-2 LOG.
      **2026-07-24 — 90 `[open]` / 156 `[limit]` / 616 `[fixed]`** (of 862; HEAD
      `e6eafc4`, CI green). Down from 372 `[open]` on 2026-07-21 — the 07-23/24
      campaign cleared ~282 more (invalid-output tail via the `triage3.py`
      live-DB scan, the recursive-CTE cluster, several disguised "FUNC-DIFF"
      real bugs — paren precedence, float-literal folding, DATE-literal typing —
      plus feature emulation: compound EXTRACT, batch SAVEPOINT, T-SQL derived-
      column naming). **It also fixed a critical Live-Syntax CI regression** (the
      CLOB→VARCHAR2 CAST-in-PL/SQL remap `4f57b2c` had turned the job red for
      hours; gated on `IR_EMBEDDED`, commit `bdbb216`). Full per-commit log in the
      `blue-rc1b-builtin-gate` memory file.
      **2026-07-21 — 372 `[open]` / 37 `[limit]` / 453 `[fixed]` (down from ~600
      open); released `v0.29.0`. The clean single-fn/stale/precision/simple-
      type-map corrections are now EXHAUSTED — the remaining `[open]` are
      features (UPDATE/USING-JOIN, procedural→PG, IS-TRUE-in-value, format masks,
      JSON/XML) or judgment calls (BIT(64) precision, MySQL TIME→Oracle type
      gap, collation DISTINCT/GROUP → [limit]). 2026-07-20/21 waves: faithful string-fn edges
      (LENGTH-trailing, ASCII/POSITION/STRPOS empty-needle, PG LEFT-neg), T-SQL
      CAST-to-int fractional-literal ROUND, Oracle DECODE NULL-safe equality,
      Oracle exception-name → PL/pgSQL condition map, PG GREATEST/LEAST literal-
      NULL drop, Oracle single-arg COALESCE, and a vc7 stale/precision harvest
      (ELT/FIELD/INSERT/pad/REPEAT/PI/trig, TIMESTAMPDIFF-day).** Structural IR-drop fixes (window frame, GROUP BY
      ROLLUP/CUBE/GROUPING SETS, computed columns), base-10 LOG, silent-clause
      carriers (FOR UPDATE/NOT VALID/CONCURRENTLY/EXCLUDE/ON UPDATE/
      MEMORY_OPTIMIZED), collation/charset drops (carrier + warning — the
      **`--db-url` %TYPE-style fallback the user approved**: resolve live when a
      DB connection is given, else warn), UNSIGNED→widen+`CHECK(≥0)`, and a
      source-gated FUNC-DIFF wave (MOD-by-zero, Oracle CAST-to-int rounding,
      GREATEST/LEAST NULL-propagation, negative/float LEFT·REPEAT, INSERT bounds,
      MySQL date-arith→DATE). Later waves (all live-verified, full log in the
      `blue-rc1b-builtin-gate` memory): division/AVG-int/LOG/precision, NULL
      ordering emulation (MySQL/T-SQL null-priority key), T-SQL `LEN`
      trailing-space (`RTRIM`), PG `SUBSTRING` start≤0, PG unbounded numeric cast
      scale (`(38,10)` — cured the pg-round-* "banker's" mirage), MySQL
      case-insensitive `INSTR`/`LOCATE`→`LOWER` on CS targets, PG `DATE-DATE`
      & PG/Oracle `date+int`→DATE_ADD, date-precision flips, and two `[limit]`
      batches (Oracle `''`=NULL, MySQL unsigned-64 bitwise). Procedural:
      `ts-continue-break` (compound assignment + `BREAK`/`CONTINUE`→EXIT/LEAVE +
      labeled MySQL loop), `@@`-global neutral carrier + FETCH-without-INTO
      carrier, `ts-cast-bit`→`SIGN(ABS(x))` (via the `TypeMapper` IR pass).
      **Maintainer policies 2026-07-19:** (a) a correct value differing only in
      decimal/date PRECISION/scale is `[fixed]` (trailing zeros AND
      scale-rounding AND datetime-vs-date zero-time); (b) per-family directives
      below.
      **Composición exacta de los 90 `[open]` (2026-07-24, por tema):**
      14 tipos-sin-equivalente (INTERVAL/TIMESTAMPTZ/TIME/money/datetime) · 14
      formato/semántica nº-fecha + substring-negativo + INSTR-extendido (FUNC-DIFF)
      · 13 DDL/constraints (gen-cols, self-FK, índices expr/inline, identity,
      SOUNDEX, drops silenciosos) · 13 procedural (parser, SQL-embebido-como-texto,
      catálogos, cursor-attrs, sp_executesql) · 10 codificación (bytes↔code-point,
      hex/binario, emoji UTF-16, base64, `U&'…'`) · 7 JSON/arrays · 6 colación/
      orden/mayúsculas · 5 MERGE/transacciones-batch/sesión-tz · 5 GROUPING/
      GROUPING-SETS/ventanas · 3 triggers-INSTEAD-OF/vistas. Cortes: 40 fallan en
      1 motor, 27 en 2, 22 en 3; por motor oracle 54 / tsql 44 / mysql 32 / pg 30;
      64 son error-de-motor y 23 FUNC-DIFF de valor.

      **Los 90 se reparten en CINCO FRENTES — ninguno es "triage-and-flip";
      cada uno es desarrollo deliberado con su propia validación:**

      1. **Frontera arquitectónica: SQL-embebido-como-texto vs modelado-en-IR
         (el ítem de MAYOR palanca — desbloquea un clúster).** La misma causa raíz
         se arregla limpia en el camino IR pero queda bloqueada cuando el DML
         embebido renderiza por *fragmento de texto* procedural. Confirmado hoy:
         `my-reads-sql`/`my-scalar-subquery-assign` (RETURN/asignación por IR) se
         cerraron con `_name_tsql_derived_columns@emit.py`, pero `my-select-into-out`
         (cola de SELECT…INTO por `_fix_select_into_rest`) NO — parche-regex ahí =
         "script-layer shape-patch" prohibido por el guardrail. Igual patrón:
         `pg-check-xor` (CHECK como PassthroughSQL, no en IR), `ts-cursor-attr`
         (CAST char-en-PL/SQL: `CAST(x AS VARCHAR2(n))` es PLS-00103 en expresión
         pero ORA-00906 sin longitud en SQL — la heurística de texto es UNSOUND,
         revertida; un fragmento mezcla sub-contextos SQL y PL/SQL). **Fix limpio:
         enrutar el DML embebido / las condiciones de constraint por el IR** (donde
         el contexto se conoce), en vez de por texto. Desbloquea la trío
         derived-table restante + varios CAST/CHECK procedurales.

      2. **Divergencias inherentes — necesitan DECISIÓN DEL MANTENEDOR sobre si
         avisar.** Colación/mayúsculas (`my-group-case`, `my-order-strings`,
         `my-greatest-string`, `ts-order-strings`), orden no-determinista de
         GROUP_CONCAT (`my-gc-order`), null-ordering bajo DISTINCT
         (`po-distinct-null`), longitud de emoji UTF-16-vs-code-point
         (`my/pg/ts-emoji-len`), byte-vs-code-point de `CHAR` (`my-char-unicode`).
         Un carrier POR CONSULTA sobre-avisa y **rompe tests existentes** (probado:
         el carrier de LISTAGG-orden rompió `test_string_agg_to_oracle`/
         `test_group_concat_to_oracle`, que asertan la conversión limpia sin aviso).
         La convención actual es imponer un orden determinista EN SILENCIO. Sin
         carrier no pueden ser `[limit]` (el test genérico lo exige). → decisión.

      3. **Features multi-parte (mini-proyectos).** MERGE completo con
         `WHEN NOT MATCHED BY SOURCE/TARGET` (`ts-merge-full`), GROUPING/GROUPING_ID
         + ROLLUP (`ts-grouping-id`, `pg-grouping*`), INSTR 4-arg
         ocurrencia/negativo (`ora-instr-edge`), `sp_executesql` con params
         tipados (`ts-sp-executesql`), triggers statement-vs-row + pseudo-tablas
         `inserted`/`deleted`/`FOR EACH ROW` (`ts-instead-of-*`, `ts-trigger-on-view`,
         `ts-after-delete-count`), atributos de función PG que el parser procedural
         mezcla en el cuerpo (`pg-func-attrs`), máscaras de formato num/fecha
         (`*-num-to-str`, `ora-interval-tochar`) — **capa de traducción de máscaras
         PAUSADA por el mantenedor**, sesión dedicada. Método por caso: comprobar
         src-vs-tgt en vivo, compensación con puerta `SOURCE_DIALECT` o entrada
         estrecha en `_DIVERGENCE_RULES` (medir churn; regex amplia sobre-dispara).

      4. **Metadatos entre sentencias.** `pg-drop-not-null` necesita el tipo de
         columna del `CREATE TABLE` del mismo batch para el `MODIFY`/`ALTER COLUMN`
         de MySQL/T-SQL (Oracle sí puede `MODIFY a NULL` sin tipo). Requiere
         rastreo de metadatos cross-statement en el batch. También el bucket de
         casts que pasa por **`transformer.py TypeMapper.visit`** (`ctx.source`/
         `ctx.target` disponibles): date↔int es la época 1900-01-01 de T-SQL
         (necesita inferencia de tipo del operando), money necesita parseo de
         símbolo de moneda, TIMESTAMPTZ/TIME/INTERVAL no tienen tipo destino.

      5. **Bloqueados por parseo / codificación de bajo nivel.**
         `pg-unicode-escape` (`U&'…'` que sqlglot mal-parsea como `U & '…'` —
         guardrail: no pre-parsear texto), `ts-hexcast`/`pg-blob-length`/
         `my-cast-uns2` (binario↔varchar, base64, hex/bit/bool→unsigned — reinterp.
         de bytes por engine con `UTL_RAW`/`CONVERT_FROM`; multi-parte, `ts-hexcast`
         intentado y revertido).

      **Método OBLIGATORIO para cualquier fix (aprendido a golpes esta campaña):**
      probar valor en vivo en los 4 motores → cambio con puerta `SOURCE_DIALECT`/
      `IR_EMBEDDED` (evitar text-patches) → `pytest test_challenge.py` + `ruff`
      (no solo black) + **suite paralela completa** (`sg docker -c
      "bash scripts/test-parallel.sh"`, `REAL_EXIT=0`) → **Y para CUALQUIER cambio
      de emit/procedural/CAST, la suite live-syntax LOCAL** con los 4
      `UNIQUE_TEST_*_URL` (la paralela la SALTA — así se coló la regresión de CI de
      horas) → `mypy src/` → flip a `[fixed]`/`[limit]` + assertion (recordar el
      "comment-prose trap": quitar líneas `--`/`/* */` antes de aserciones
      negativas). **`--db-url` live collation resolver: SKIPPED per user.**

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

---

## 6. Test-suite memory blow-up (P2) — surfaced 2026-07-21, RESOLVED 2026-07-22

- [x] **Root cause found + fixed (commit `02f483b`).** The "memory growth" was
      **not** linear accumulation and **not** a coverage-only problem — it was a
      single pathological test whose guard had regressed. This cycle's `scrub()`
      lying-warning fix changed scrubbed non-empty literals from `''` to `'x'`,
      which broke the psql-`:'var'` parse guard in `convert.py` (its signature
      `(?<!:):\s*''` no longer matched). So `COPY t FROM :'filename'` fell through
      to sqlglot, whose `_parse_copy_parameters` **loops unboundedly allocating
      memory**. Serially the `MemoryError` is *caught* and the statement still
      degrades — but only after a multi-GB transient spike (the "~9 GB by 22% at
      `test_embedded_dml_ir`" and the misread "linear climb" were this one test).
      Under the parallel runner four such spikes coincide and the OS OOM-killer
      SIGKILLs a worker (EXIT=137) before Python can raise → **the CI Test job's
      4th shard went silent ~6 min then "the runner has received a shutdown
      signal".** Fix: match the new scrub output, `(?<!:):\s*'`. Diagnostic aid
      added: `faulthandler_timeout=120` in `pyproject.toml` (a future single-test
      hang now dumps its stack instead of surfacing only as a runner shutdown).
      Verified: the 4-worker parallel suite (the CI config) passes clean, no OOM;
      CI green on `02f483b`.
- [x] **Coverage re-added to CI (`COV=1`) — 2026-07-23.** With the real cause
      (above) fixed, measured `COV=1 PYTEST_WORKERS=4 scripts/test-parallel.sh`
      locally: **peak total RSS across all workers = 1.19 GB** (all shards green,
      91% coverage, `coverage.xml` produced) — far under a runner's ~16 GB. Memory
      is tied to the core count (nproc workers, ~0.3 GB/worker), so it stays
      bounded. Restored the `COV=1` Test-job step + the `Upload coverage` artifact
      in `.github/workflows/ci.yaml` (reverting `3a2029e`).
      **Process note:** `pytest … | tail` reports the *pipe's* exit, not pytest's
      — capture `> file; echo "EXIT=$?" >> file` for a trustworthy full-suite
      result; use `ulimit -v` so a runaway `MemoryError`s instead of OOM-killing
      the host.
