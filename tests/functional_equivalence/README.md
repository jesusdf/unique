# Functional-equivalence test database

> **Status: design / scaffolding.** This folder holds the design and (later) the
> assets and harness for functional-equivalence testing. Build it *after* the
> current `docs/TODO.md` items are closed. Nothing here is wired into CI yet.

## Why

The existing `syntax-live` CI job validates that a transpiled script **compiles**
on the target engine (syntactic validity). It does *not* catch **semantic**
divergence: a trigger that fires differently, integer-vs-decimal division, NULL
handling in concatenation, date arithmetic, rounding, etc.

**Goal:** confirm that a script migrated from one engine to another **behaves
identically** — i.e. produces the **same final database state** after running
its DDL + seed data + mutations. This is the gold standard for a transpiler:
functional equivalence, not just syntactic validity.

This extends `tests/helpers/functional_equivalence.py`, which today compares
functional equivalence **statically** (field counts, condition counts, DML
verbs). Here we assert the actual **runtime state** in real engines.

## Architecture (the important decisions)

### 1. Generate the target scripts — don't hand-write them

If all four per-engine scripts were written by hand, the test would compare
hand-written artifacts, not the transpiler (the system under test). So:

- Author the scenario **once** in a canonical dialect (start with T-SQL, our
  richest source and the basis of the existing fixtures).
- The **transpiler generates** the other three.
- Run all four and assert they all reach the **same expected state**.

The expected state is defined **once**, engine-agnostic, and every run checks
against it. That makes the transpiler the thing under test.

### 2. Mature form: the 4×4 matrix

The "one fixture per engine" idea becomes the rigorous target version: author
**four** canonical scenarios (each idiomatic to its engine — this also exercises
each dialect's *parser* as a source), transpile each to the other three, and
require all **16 runs** (4 sources × 4 targets, identity included) to converge on
the same expected-state spec. Reuses the project's existing "12 directional
pairs" framing.

**Phase 1** (first value): one canonical T-SQL source → 3 transpiled → 4 runs.
**Phase 2** (rigor): full 4×4.

### 3. UML is for the schema only

A UML/Mermaid class diagram models the **static** schema (tables, columns,
types, PK/FK/unique/check) well, and stays engine-agnostic. But behavior — the
ordered operations, triggers/procs, and especially the *expected state* — does
not live naturally in UML. So:

- **Schema:** `schema/` holds the canonical DDL and a Mermaid diagram
  (ideally generated from the DDL so it can't drift).
- **Behavioral spec:** the ordered operations live in the canonical script;
  the assertions live in `expected_state.yaml` (the single source of truth for
  what each table must contain).

## The hard part: determinism and value normalization

Asserting an *exact* final state only works if every operation is deterministic
across engines. Design the schema and data to **avoid engine-defined behavior**,
or turn each unavoidable difference into a documented expected divergence.

Engine-defined behaviors to design around:

- **Integer vs decimal division:** T-SQL `5/2 = 2`; others may give `2.5`. Use
  explicit casts or decimal types in asserted expressions.
- **NULL in concatenation:** T-SQL `'a' + NULL = NULL`; Oracle `||` treats NULL
  as empty. Avoid NULL operands in asserted concatenations.
- **Non-deterministic functions:** `GETDATE()`/`SYSDATE`/`NOW()` stored as data
  you assert on will differ. Use **fixed literal dates**, or inject a constant
  "clock" value. For trigger-stamped timestamps, assert relationships/presence,
  not exact values (or freeze the clock).
- **Rounding mode, decimal scale, float representation:** use explicit
  `DECIMAL(p, s)` and avoid binary floats in asserted columns.
- **`CHAR(n)` padding, collation / case-sensitivity, ordering without
  `ORDER BY`:** normalize on read (trim, case-fold only if intended) and always
  read with a deterministic `ORDER BY pk`.
- **Identity / sequence start & increment:** pin them explicitly.

### Comparison mechanism

For each table: `SELECT ... ORDER BY <pk>` and reduce to a canonical list of
tuples, normalizing types so the four engines are comparable:

- BIT/BOOLEAN → canonical bool; NUMBER/INT → canonical int; DECIMAL → fixed
  scale; CHAR → trimmed; CLOB/NCLOB/TEXT → str; NULL → a single sentinel.

This per-engine "read table → canonical tuples" function is the bulk of the
harness work and where subtle false positives/negatives live. Keep it small,
explicit, and well-tested in its own right.

### Scope

Cover the **faithfully-transpilable** subset of constructs. Lossy constructs
(those we deliberately degrade to `-- UNIQUE:` comments) stay covered by the
existing syntactic + comment tests; including them here would muddy the
functional-equivalence metric.

## Suggested domain: minimal invoicing

`customer`, `product`, `invoice`, `invoice_line`, `payment`. This naturally
exercises every category the transpiler handles, while staying tiny:

- **Data types:** int, `DECIMAL(p, s)`, varchar, date, datetime, bit/bool,
  text/clob.
- **Objects:** PK / FK / UNIQUE / CHECK / DEFAULT; identity *or* sequence; a
  **view** (invoice totals); a **trigger** (recompute an invoice's total when a
  line is inserted/updated — the "update on a triggered table" case); a
  **stored procedure** (`create_invoice` inserts header + lines and returns the
  id — the "DML from a procedure" case); a **function** (compute tax).
- **Mutations with known end-state:** direct insert → trigger recomputes; update
  a line → trigger readjusts; a proc that inserts → assertions over row counts
  and fixed values.

## Folder layout (planned)

```
tests/functional_equivalence/
  README.md            ← this file (design + rationale)
  coverage-matrix.md   ← feature → where-exercised matrix (proves minimal+complete)
  schema/
    schema.mmd         ← Mermaid class diagram (engine-agnostic)
    tsql.sql           ← T-SQL native DDL
    postgresql.sql     ← PostgreSQL native DDL
    mysql.sql          ← MySQL native DDL
    oracle.sql         ← Oracle native DDL
  scenario/
    README.md          ← the five ordered operations, with the T-SQL script
    tsql.sql           ← T-SQL native seed + mutations
    postgresql.sql     ← PostgreSQL native seed + mutations
    mysql.sql          ← MySQL native seed + mutations
    oracle.sql         ← Oracle native seed + mutations
  expected_state.yaml  ← engine-agnostic per-table assertions (single source of truth)
  state_check.py       ← value normalization + table comparison (pure, unit-tested)
  engine_runner.py     ← statement splitter + per-engine run/read driver
  test_state_check.py  ← unit tests for the comparison core
  test_engine_runner.py← splitter tests + SQLite end-to-end smoke test
  test_functional_equivalence_live.py ← the 4×4 live matrix (skips w/o DB URLs)
  HARNESS.md           ← runbook for the live run
```

Only the four **native fixtures** per folder are committed. The live harness
transpiles each source dialect to the other three **on the fly** at run time;
no transpiled SQL is stored in the repo.

## Build phases

1. **Coverage matrix** — list the behaviors to guarantee.
2. **Schema** — canonical DDL + generated Mermaid.
3. **Scenario** — deterministic seed + mutations.
4. **Expected-state spec** — `expected_state.yaml`.
5. **Harness + CI** — clean setup / run / read-canonical / assert / teardown,
   reusing `tests/helpers/live_validation.py`; one T-SQL source → 3 targets
   first (4 runs), then grow to 4×4.
6. **Iterate** — run, find divergences, fix the transpiler or document them.

## Open question to settle before building

Start with **one canonical source (T-SQL) → 3 generated** (fast, first value),
or go straight to **4 canonical sources → 16 runs** (rigorous, more work)?
Recommendation: phase 1 first, phase 2 as the target.
