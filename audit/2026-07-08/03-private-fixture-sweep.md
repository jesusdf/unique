# 03 — Private-fixture sweep (live-engine validation)

Addendum to the 2026-07-08 audit: the three `fixtures-private/` scripts (a
T-SQL migration dump ~13k lines, a T-SQL procedures file ~500 lines, and an
Oracle migration dump ~217k lines / 13 MB) were transpiled across the matrix
and the outputs executed statement-by-statement against the real engines
(local `docker-compose.test.yaml` stack: PostgreSQL 16, MySQL 8, SQL Server
2022 via `SET PARSEONLY ON`, Oracle Free 23). Errors were classified: syntax
errors are transpiler defects; missing-object errors are expected (no schema
loaded) and excluded. **All examples below are anonymized re-creations of the
failing patterns — no private identifier appears here.**

## Headline numbers

| Source file | Direction | Invalid statements on the real engine |
|---|---|---|
| T-SQL procedures (~500 lines) | → oracle / postgresql / mysql | Every routine in the file fails to compile on at least one target (declaration-hoisting family C below) |
| T-SQL migration dump (~13k lines) | → oracle / postgresql / mysql | Dozens of batches, all in the guard/DDL families A–B below |
| Oracle migration dump (~217k lines) | → tsql | **11,031 / 38,345 batches (29%) fail `SET PARSEONLY ON`** |
| Oracle migration dump | → postgresql | **22,515 / 51,683 statements (43.6%) are syntax errors** |

The T-SQL→X direction is broadly solid (most statements execute; failures
cluster in a few classes). The **Oracle→X direction is far less mature than
STATUS.md's "complete" wording suggests** — a third to a half of a real dump
does not parse on the target.

Transpile time for the 13 MB dump was ~30–35 s per target with linear-looking
memory — the earlier O(n²) fixes hold.

---

## A. Migration-guard family (T-SQL source) — extends findings N1/N10 of doc 02

The batch classifier routes `IF OBJECT_ID(…)` / `IF [NOT] EXISTS(…)` guards
into an extraction path; every shape the extractor does not recognize falls
into the SET-option fallback, which **comments the whole batch out** with a
mislabeled `set_option` warning ("SET option commented out: IF OBJECT_ID…").

- **A1 (S1). A leading comment kills a guard.** The single-statement guard
  translates correctly bare, but with a `/* section header */` comment in the
  same batch — the universal style of generated migration scripts — the whole
  batch (comment + guard + DROP/CREATE) is emitted as `--` comments on every
  target:

  ```sql
  /* header */
  IF OBJECT_ID('s1.my_func', 'FN') IS NOT NULL
      DROP FUNCTION s1.my_func
  GO
  -- becomes, on every target:
  -- /* header */
  -- IF OBJECT_ID('s1.my_func', 'FN') IS ...   (nothing executable)
  ```

  Dozens of drop-guards in the real dump vanished this way.

- **A2 (S1). `BEGIN…END`-wrapped guards are commented out** on every target
  (`IF OBJECT_ID('t1') IS NOT NULL BEGIN DROP TABLE t1 END`, and the same for
  `IS NULL BEGIN CREATE TABLE … END`) — the exact shape SSMS generates. The
  unbracketed equivalents translate fine.

- **A3 (S1). A leading comment suppresses the Oracle `/` terminator.** A
  data-guard with `BEGIN…END` translates to the Oracle guard FOR-loop
  correctly, but when the batch carries a leading block comment the emitted
  anonymous block is **not followed by `/`** — in SQL*Plus every statement
  after it is swallowed into the block. Reproduced minimally: comment +
  `IF NOT EXISTS(data) BEGIN INSERT END` + a following batch.

- **A4 (S1). `NEWID()` inside a guard body becomes MySQL's `UUID()` on
  Oracle** (`SYS_GUID()` expected; standalone DML maps all three targets
  correctly — the procedural pipeline's map is not per-target). Another
  instance of the dual-pipeline asymmetry the workflow skill mandates
  checking.

- **A5 (S2). Catalog CREATE-guards lose idempotency on PostgreSQL/MySQL:**
  `IF NOT EXISTS (SELECT * FROM sys.objects …) BEGIN CREATE TABLE t1 … END`
  emits a bare `CREATE TABLE t1` (no `IF NOT EXISTS`, no warning) — a re-run
  errors. Oracle gets the idempotent guard-loop and `CREATE SCHEMA` gets
  `IF NOT EXISTS`, so this is an inconsistency, not a design choice.

## B. Standalone DDL/DML gaps (T-SQL source)

- **B1 (S1). `PRIMARY KEY CLUSTERED (col ASC)`** →
  `PRIMARY KEY, CLUSTERED (col ASC NULLS FIRST)` — invalid on **all four**
  targets (`CLUSTERED` survives as a phantom second constraint; `ASC` in a
  PK column list becomes `ASC NULLS FIRST`, which PostgreSQL rejects inside
  a constraint).

- **B2 (S1). `DROP INDEX` is untranslated across the matrix.**
  `DROP INDEX [IF EXISTS] tbl.idx` passes through: PostgreSQL sees a
  cross-database three-part name, MySQL lacks the required `ON tbl`
  (its form is `DROP INDEX idx ON tbl`), and the `… ON tbl` source form
  drops the table name for every target (Oracle additionally has no
  `IF EXISTS` before 23c).

- **B3 (S1). `ALTER TABLE … ADD COLUMN x INT NOT NULL CONSTRAINT df_x
  DEFAULT 0` → MySQL keeps the named-DEFAULT-constraint syntax** (1064).
  The `CONSTRAINT name` must be dropped (with a warning) for MySQL.

- **B4 (S3). A bare `RETURN` eats the comment on the next line**: the parser
  attaches the following `-- comment` as the RETURN's *value*, then warns
  "discarded procedure RETURN value (<the comment>)" — a false warning and a
  destroyed comment (the round-trip loses it).

## C. Procedural-engine gaps (T-SQL source, exercised by every routine of the procedures file)

- **C1 (S1). Mid-body `DECLARE @x <type> = <expr>` is not hoisted.** All
  three targets require declarations in a declaration section; Unique leaves
  them in place: Oracle gets `V_E NUMBER(10) := INSTR(…);` inside a loop body
  (PLS-00103), MySQL gets `DECLARE v_ch NCHAR(1) = SUBSTRING(…)` mid-body —
  doubly invalid (position, and `=` instead of `DEFAULT`) — and PostgreSQL
  gets `v_cur CURSOR;` (a cursor declared without `FOR query`). The engine
  already hoists table variables; scalar mid-body DECLAREs need the same
  treatment.

- **C2 (S1). `BEGIN TRY … END TRY BEGIN CATCH …` reaches MySQL raw** in at
  least one routine shape (TRY/CATCH → `DECLARE … HANDLER` translation
  exists for other shapes, so this is a path gap, not a missing feature).

- **C3 (S1). A `WHILE` loop inside a MySQL routine is emitted PL/SQL-style**
  (`WHILE cond LOOP … END LOOP` instead of `WHILE cond DO … END WHILE`).

- **C4 (S1). T-SQL cursor options spill:** `DECLARE c CURSOR LOCAL
  FAST_FORWARD FOR …` leaves a floating `; LOCAL AS FAST_FORWARD;` fragment
  in MySQL/PostgreSQL output.

- **C5 (S1). `CALL proc(name => value)` named arguments are emitted for
  MySQL**, which does not support named notation — every translated call of
  the dump fails; MySQL needs positional arguments.

## D. Oracle → X direction (the 29% / 43.6% above decomposes into these)

- **D1 (S1). `EXEC my_proc` → `EXEC AS my_proc` on every target.** In T-SQL,
  `EXECUTE AS` is *impersonation* — a semantically dangerous mistranslation
  if it ever parsed; on PostgreSQL/MySQL `EXEC` does not exist (should be
  `CALL`). Hundreds of occurrences.

- **D2 (S1). Top-level `DECLARE … BEGIN … END;` blocks keep their PL/SQL
  skeleton in T-SQL** (`DECLARE` header line, `BEGIN`, no statement
  terminators) instead of being flattened to T-SQL's top-level
  `DECLARE @x …; <statements>`.

- **D3 (S1, ~6,000×). `INSERT INTO t SELECT … FROM DUAL WHERE NOT EXISTS
  (…)` keeps `FROM DUAL`** on PostgreSQL and T-SQL. The 2026-07-02 fix
  (S1-6) covers a standalone `SELECT 1 FROM dual`, but not the
  INSERT-guard idiom that dominates real Oracle migration dumps.

- **D4 (S1, ~100×). `ROWNUM` survives inside procedural embedded DML**
  (`… AND ROWNUM = 1` in a `SELECT INTO` inside a routine) on
  PostgreSQL/MySQL — the DML pipeline maps ROWNUM (S1-5 fix), the
  procedural pipeline does not. Dual-pipeline asymmetry again.

- **D5 (S1). `ALTER TABLE t RENAME COLUMN a TO b` passes through to T-SQL**
  (needs `EXEC sp_rename 't.a', 'b', 'COLUMN'`).

- **D6 (S1). Trigger predicates `IF UPDATING / INSERTING / DELETING` pass
  through to T-SQL** (need the `UPDATE()` function / inserted-deleted
  emptiness tests).

- **D7 (S1). `TRUNC(SYSDATE)` → `DATE_TRUNC('DD', GETDATE())`** — no such
  function in T-SQL (2022 has `DATETRUNC(day, …)`; older versions need
  `CAST(… AS DATE)`).

- **D8 (S1, silent corruption). `SELECT MAX(NVL(n, 0)) + 1 INTO v FROM t …`**
  → T-SQL `SELECT @v = MAX ( ISNULL ( n FROM t;` (the second
  argument, two closing parens and the `+ 1` are **dropped**) and →
  PostgreSQL `MAX ( COALESCE ( n , 0 ) ) || 1` (numeric `+` rewritten as
  **string concatenation**). The procedural string-concat rewrite is
  misfiring on numeric expressions and eating tokens.

- **D9 (S1). Routine headers split across lines lose the parser.** A real
  dump spells `create or replace\nPROCEDURE name` (lowercase, newline
  between) with a `-- <codegen>` comment block between name and `AS`; the
  procedural parser desynchronizes and **spills declaration fragments as
  top-level batches** (`v_x AS VARCHAR2`, `CURSOR AS cur1`, `m_x AS t1`) —
  dozens of invalid statements on every target.

- **D10 (S2). `DBMS_SCHEDULER.CREATE_JOB(…)` becomes a raw `CALL` on
  PostgreSQL** instead of a carrier + `unsupported` entry (the package does
  not exist off Oracle).

## E. Test-harness defect found along the way

- **E1. `tests/helpers/live_validation._split_mysql_statements` splits on
  `;` inside string literals** (`'A=1;B=0'` becomes two fragments) — the
  MySQL live validators can mis-split any fixture whose strings contain
  semicolons, producing false engine errors (or masking real ones). The
  splitter needs quote-awareness (same for `_split_semicolons`).

## Recommended attack order

1. **A1/A2 (guard + comment / BEGIN shapes)** — highest real-world density in
   T-SQL migration dumps, and the fallback that eats them also mislabels the
   warning. Fixing the guard extractor to (a) tolerate leading comments and
   (b) unwrap `BEGIN…END` correctly likely clears A1, A2 and N1 together.
2. **D3/D1/D2** — three shapes account for a large share of the Oracle→X
   failure volume (guard-INSERT `FROM DUAL`, `EXEC`, anonymous DECLARE
   blocks).
3. **D8** — silent corruption (dropped arguments, `+`→`||`) is worse than a
   syntax error; add the private dump's failing expressions (anonymized) to
   the operator round-trip suite.
4. **C1 (declaration hoisting)** — unlocks whole routines at once on all
   three targets.
5. Everything else in file order; each item should land with an anonymized
   regression fixture and, where the engines are available, a live probe.

## Method / reproducibility

Scratch harness (session-local, not committed): transpile each private file
per target, scan comment-stripped output for source-dialect leftovers, then
execute per-statement against the Docker engines with SQLSTATE/errno
classification (`42601`-class = syntax; `42P01`/1146/ORA-942 = expected
missing schema; SQL Server via `SET PARSEONLY ON`; Oracle per-unit on `/`
boundaries). Statement splitting for PG was dollar-quote- and
string-aware; the MySQL numbers are inflated by E1 (statements re-split at
in-string semicolons) and were cross-checked manually before reporting.
