# Scenario

The **canonical** scenario lives here: the ordered SQL that, run against a fresh
schema, produces the state asserted in `../expected_state.yaml`.

Planned files (added in the build-out, see `../README.md`):

- `tsql.sql` — the **single source of truth** for Phase 1: DDL (or `\i
  ../schema/tsql.sql`) + seed inserts + mutations, authored in T-SQL. The
  transpiler generates the MySQL / PostgreSQL / Oracle variants; all four are
  run and checked against `../expected_state.yaml`.
- (Phase 2) `canonical_mysql.sql`, `canonical_postgresql.sql`,
  `canonical_oracle.sql` — each engine's natively-authored scenario, for the
  full 4×4 cross-transpilation matrix.

## Locked ordered steps (Phase 1)

The design is locked in `../coverage-matrix.md` and `../expected_state.yaml`.
`tsql.sql` must implement exactly these five steps, in order:

1. **Seed** 2 `customer` + 2 `product` rows (one customer has `notes`, one
   leaves it NULL).
2. **Direct INSERT** invoice 1 + its 2 lines (2 Widget, 1 Gadget) →
   `trg_line_total` sets `invoice.total = net 45.50 + fn_tax 4.55 = 50.05`.
3. **UPDATE** a line on invoice 1 (Widget qty 2 → 3) → trigger readjusts to
   `net 55.50 + fn_tax 5.55 = 61.05` (the "update on a triggered table" path).
4. **CALL `create_invoice(...)`** to build invoice 2 (1 Widget, 1 Gadget) →
   `net 35.50 + fn_tax 3.55 = 39.05`, `is_paid` left at its DEFAULT false (the
   "DML from a procedure" path).
5. **INSERT `payment`** of 39.05 for invoice 2, then an explicit
   `UPDATE invoice SET is_paid = 1 WHERE id = 2` (the payment path).

Tax is `fn_tax(net) = net * 0.10`; the trigger folds it into `invoice.total`.

Authoring rules (recap from `../README.md`):

- Every mutation's outcome must be **deterministic across engines** — fixed
  literal dates, explicit `DECIMAL(p, s)`, no integer-division / NULL-concat /
  rounding / collation dependence in any asserted value. The 10% tax rate is
  chosen so every taxed subtotal is exact at scale 2 (no rounding-mode drift).
- Exercise the "interesting" paths on purpose: a **direct** insert/update, an
  update on a **triggered** table, and inserts/updates **from a stored
  procedure** — so functional equivalence is tested beyond plain DML.
- Keep it minimal: only what the coverage matrix requires.
