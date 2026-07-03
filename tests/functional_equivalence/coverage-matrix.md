# Coverage matrix

Maps each behavior we **guarantee functionally** to where the minimal invoicing
scenario exercises it. This proves the schema/scenario is **minimal yet
complete**: every construct below is touched by at least one operation *and*
asserted on in `expected_state.yaml`, and nothing is included that isn't
asserted.

Status: **LOCKED for Phase 1** (T-SQL canonical source → MySQL / PostgreSQL /
Oracle). Only the faithfully-transpilable subset lives here; lossy constructs
stay covered by the syntactic / `-- UNIQUE:` tests, not this matrix.

Step numbers below refer to the ordered scenario (also recapped in
`expected_state.yaml` and authored in full in `scenario/tsql.sql`):

1. seed `customer`, `product`
2. direct `INSERT` invoice 1 + 2 lines → `trg_line_total` recomputes `invoice.total`
3. `UPDATE` a line on invoice 1 (qty 2 → 3) → trigger readjusts `invoice.total`
4. `CALL create_invoice(...)` builds invoice 2 (DML from a procedure)
5. `INSERT payment` for invoice 2's full total → marks invoice 2 `is_paid`

`invoice.total` is defined as `SUM(line_total) + fn_tax(SUM(line_total))`, so the
scalar function `fn_tax` is exercised on every recompute (steps 2, 3, 4).

## Data types

| Type (canonical) | Column | Exercised by | Asserted in expected_state | Notes / determinism |
|---|---|---|---|---|
| INT / identity | `customer.id`, `product.id`, `invoice.id`, `invoice_line.id`, `payment.id` | steps 1–5 (every insert) | PK values 1..n in every table | identity/sequence pinned to START 1 INCREMENT 1 |
| DECIMAL(10,2) | `product.unit_price`, `invoice_line.unit_price`, `invoice_line.line_total` | steps 1–4 | `unit_price`, `line_total` values | explicit scale; no float; qty×price exact at scale 2 |
| DECIMAL(12,2) | `invoice.total`, `payment.amount` | steps 2–5 | `invoice.total`, `payment.amount` | net + 10% tax; all values exact at scale 2 (no rounding-mode dependence) |
| VARCHAR(n) | `customer.name`, `customer.email`, `product.name` | step 1 | `name`, `email` values | read trimmed (CHAR vs VARCHAR) |
| DATE | `invoice.issued_on`, `payment.paid_on` | steps 2,4,5 | `issued_on`, `paid_on` | fixed literal dates only |
| DATETIME / timestamp | `invoice.created_at` | steps 2,4 (trigger/clock-stamped) | **presence only** (not value) | documented divergence — clock-sensitive; exact-value assertion deferred to Phase 2 (frozen clock) |
| BIT / BOOLEAN | `invoice.is_paid` | step 4 (DEFAULT 0), step 5 (set true) | `is_paid` on both invoices | normalize 0/1 ↔ false/true on read |
| TEXT / CLOB | `customer.notes` | step 1 (one row sets it, one leaves NULL) | NULL vs non-empty presence | from `VARCHAR(MAX)`; not asserted by literal text, only NULL vs set |

## Object types

| Object | Name | Exercised by | Asserted as | Notes |
|---|---|---|---|---|
| Table + PK | all 5 tables | steps 1–5 | row counts + PK values | |
| FK constraint | `invoice.customer_id`, `invoice_line.invoice_id`, `invoice_line.product_id`, `payment.invoice_id` | steps 2–5 | referenced rows resolve; counts hold | inserts respect FK order |
| UNIQUE constraint | `customer.email` | step 1 | both emails distinct & present | |
| CHECK constraint | `invoice_line.qty > 0` | steps 2–4 (all qty ≥ 1) | satisfied (happy path) | reject-path is out of Phase-1 scope (asserting an error is engine-message-specific) |
| DEFAULT | `invoice.is_paid = 0` | step 4 (invoice 2 starts unpaid) | invoice 2 unpaid until step 5 | |
| Identity / sequence | `*.id` | steps 1–5 | contiguous PKs 1..n | START 1 INCREMENT 1, pinned per engine |
| View | `v_invoice_totals` | read-side (harness/manual) | not a stored table → not in expected_state | aggregate SUM(line_total) per invoice; validated to equal `invoice.total − tax` |
| Trigger (AFTER ins/upd) | `trg_line_total` | steps 2 (insert) & 3 (update) | `invoice.total` after each | the "update on a triggered table" path is step 3 |
| Stored procedure | `create_invoice` | step 4 | invoice 2 + its 2 lines, returned id | the "DML from a procedure" path |
| Function (scalar) | `fn_tax` | steps 2,3,4 (called by the trigger) | folded into asserted `invoice.total` | tax = net × 0.10, exact at scale 2 |

## Mutations (the behavioral scenario)

| Step | Operation | Expected effect | Asserted as |
|---|---|---|---|
| 1 | seed `customer` (2), `product` (2) | base rows present | row counts + fixed values |
| 2 | direct `INSERT` invoice 1 + 2 lines | trigger sets `invoice.total` = 45.50 net + 4.55 tax = 50.05 | (intermediate; final asserted after step 3) |
| 3 | `UPDATE invoice_line` (Widget qty 2 → 3) on invoice 1 | trigger readjusts: 55.50 net + 5.55 tax = **61.05** | `invoice[1].total = "61.05"`, lines updated |
| 4 | `CALL create_invoice(cust 2, …)` | new invoice 2 + 2 lines; 35.50 net + 3.55 tax = **39.05**; starts unpaid | `invoice[2].total = "39.05"`, `is_paid = false`, 2 new lines |
| 5 | `INSERT payment` (39.05) for invoice 2 | payment recorded; invoice 2 marked paid | `payment.row_count = 1`, `invoice[2].is_paid = true` |

**`is_paid` mechanism (resolved):** invoice 2 is marked paid by the **payment
path**. Phase 1 keeps this deterministic and engine-neutral by having
`create_invoice` *not* touch `is_paid` (DEFAULT 0 applies), and step 5 performs
an explicit `UPDATE invoice SET is_paid = 1 WHERE id = 2` immediately after the
payment insert, in the same canonical script. (A second AFTER-INSERT trigger on
`payment` was considered but deferred: two triggers add cross-engine surface
without adding a new *covered behavior* beyond what `trg_line_total` already
proves. Revisit in Phase 2 if we want to cover a payment trigger explicitly.)

## Determinism checklist (per asserted value)

- [x] No `GETDATE()`/`SYSDATE`/`NOW()` in an asserted column — `created_at` is
      excluded from value assertions (presence only).
- [x] No integer-division ambiguity — tax is `net * 0.10` on `DECIMAL` operands,
      never integer division; quantities multiply, never divide.
- [x] No NULL operand in an asserted concatenation — no concatenation is asserted;
      `customer.notes` NULL is asserted only as NULL-vs-set, not concatenated.
- [x] Explicit `DECIMAL(p, s)` for all monetary values — `(10,2)` for unit/line,
      `(12,2)` for totals/amounts.
- [x] Tax rate (10%) chosen so every taxed subtotal (45.50, 55.50, 35.50) is
      exact at scale 2 — no rounding-mode dependence between engines.
- [x] Reads use `ORDER BY <pk>`; values normalized per type on read (see
      `expected_state.yaml` normalization block).
- [x] Identity/sequence pinned (START 1, INCREMENT 1) so PK values are stable.

## Minimality argument

Every type and object above is reachable by removing none of the five steps:
drop step 1 and there is nothing to invoice; drop step 2 and the trigger/insert
path is gone; drop step 3 and the "update on a triggered table" behavior is
untested; drop step 4 and the procedure + DEFAULT paths vanish; drop step 5 and
`is_paid`/payment are untested. No table, column, constraint, or routine is
present that no step touches and no assertion covers — satisfying the matrix's
own "minimal yet complete" rule.

---

## Scenario B — record-update paths & date handling (additive)

Per the design decision to broaden the functional-equivalence DB *only* where it
stays deterministic and faithfully transpilable, Scenario B extends (never
rewrites) the locked Scenario A above. It is a **separate, additive block of
steps** so the Scenario-A assertions in `expected_state.yaml` remain untouched;
Scenario B adds its own tables/columns/objects and its own assertions. It exists
to cover, on purpose, (a) the several distinct **UPDATE** shapes the transpiler
handles and (b) cross-engine **date arithmetic / date functions**.

### New schema surface used by Scenario B

| Object / column | Kind | Purpose |
|---|---|---|
| `invoice.due_on` | `DATE` | `= issued_on + 30 days` — date arithmetic (`DATEADD`/`+ INTERVAL`/`DATE_ADD`) |
| `invoice.updated_at` | `DATETIME` | bumped by `trg_invoice_touch` on every UPDATE (presence-asserted only) |
| `product.is_active` | `BIT/BOOLEAN` | toggled by a searched UPDATE |
| `trg_invoice_touch` | trigger (BEFORE UPDATE) | sets `updated_at` — proves a BEFORE-UPDATE trigger path |
| `fn_days_between(d1,d2)` | scalar function | engine-neutral `DATEDIFF` wrapper, returns INT days |
| `v_overdue_invoices` | view | `days_overdue = fn_days_between(:as_of, due_on)` where `> 0` |
| `bulk_reprice(pct)` | procedure | UPDATE-with-JOIN across `product` → `invoice_line` |
| `recalc_overdue(as_of)` | procedure | cursor/loop performing date-driven UPDATEs |

### UPDATE shapes covered (the "different cases to update records")

| # | UPDATE shape | Where exercised | Asserted effect |
|---|---|---|---|
| U1 | **Searched single-column** UPDATE (`SET is_active = 0 WHERE id = …`) | direct stmt | `product.is_active` flips |
| U2 | **Multi-column** UPDATE in one statement | direct stmt on `invoice` | two columns change atomically |
| U3 | **Compound assignment** (`SET col += expr`) → normalized to `col = col + expr` | direct stmt | numeric column incremented |
| U4 | **UPDATE … FROM / JOIN** (cross-table) | `bulk_reprice` | `invoice_line.unit_price` set from `product` |
| U5 | **UPDATE driven by a subquery / correlated value** | direct stmt | column set from a scalar subquery |
| U6 | **UPDATE that fires a trigger** (BEFORE UPDATE) | any UPDATE on `invoice` | `updated_at` changes (presence) |
| U7 | **UPDATE inside a cursor/loop in a procedure** | `recalc_overdue` | date-driven rows updated |

`bulk_reprice` and U4 are the canonical "UPDATE with JOIN" row from
`docs/01-compatibility.md` §2; the per-engine syntax adaptation (T-SQL
`UPDATE…FROM` ↔ PostgreSQL `UPDATE…FROM` ↔ MySQL multi-table UPDATE ↔ Oracle
`MERGE`/subquery) is exactly what we assert produces the same final rows.

### Date handling covered

| Date behavior | Construct | Determinism note |
|---|---|---|
| Date add | `issued_on + 30 days` → `due_on` | fixed literal base date; integer day offset is exact on all engines |
| Date diff | `fn_days_between(as_of, due_on)` | `as_of` is a **passed-in fixed date**, never `NOW()`/`SYSDATE` |
| Date compare | `WHERE due_on < as_of` in `v_overdue_invoices` | pure comparison of two `DATE`s |
| Part extract | `YEAR(issued_on)` asserted | `YEAR()` maps cleanly (avoid bare `DATEPART()`, per §5.3) |
| Touch timestamp | `updated_at` via trigger | clock-sensitive → **presence-asserted only**, never literal value |

### Scenario B determinism checklist

- [x] Every date is a **fixed literal** or a **passed-in parameter** (`as_of`),
      never a clock function, in any asserted value.
- [x] Date add uses an **integer day count** (`+30`), exact across engines — no
      month/year arithmetic (which differs on end-of-month rules).
- [x] `days_overdue` computed against the injected `as_of = 2024-03-01`; with
      `due_on` of `2024-02-14`/`2024-03-02` it yields `+16` / `-1` → exactly one
      invoice is overdue. Reconciled numerically.
- [x] `bulk_reprice(10%)` keeps values exact at scale 2 (10.00→11.00,
      25.50→28.05); no rounding-mode dependence.
- [x] `updated_at` excluded from value assertions (presence only), like
      `created_at`.

### Why additive instead of editing Scenario A

Rewriting Scenario A to fold in reprice/date columns would change its already
locked, numerically-reconciled totals. Keeping Scenario B additive preserves
those guarantees and isolates the new cross-engine surface (BEFORE-UPDATE
trigger, UPDATE-with-JOIN, cursor UPDATE, date arithmetic) behind its own
assertions, which is cheaper to reason about and to debug per engine.

> Materialization note: the concrete `expected_state.yaml` rows for Scenario B
> are authored together with `scenario/tsql.sql` in the next (first SQL)
> step — this matrix locks the *design* of what those rows must prove.

### Step 6 addendum — assignment-select no-rows semantics (audit S2-3)

`flag_payment_status(customer_id, invoice_id)` reads `payment.amount` for an
invoice into a local variable and writes `customer.notes` (`'no payment'` when
the variable observed no row, `'paid'` otherwise). Called for (1, 1) — invoice
1 has **no** payment row — and (2, 2), which is paid.

- **What it proves:** a T-SQL assignment-select (`SELECT @v = col ...`) that
  matches no row leaves the variable NULL/unchanged; the transpiled Oracle
  `SELECT INTO` must not die on `NO_DATA_FOUND` (the S2-3 wrapper), and every
  engine must take the `IS NULL` branch. Asserted via `customer.notes` on both
  rows (deterministic string literals, no clock/locale dependence).
- **Native counterparts:** the PostgreSQL/MySQL/Oracle fixtures author the
  read with `SELECT MAX(amount) INTO ...` — an aggregate always returns one
  row, so the no-payment case yields NULL portably and natively (no engine
  raises). Only the T-SQL source exercises the S2-3 transform.
