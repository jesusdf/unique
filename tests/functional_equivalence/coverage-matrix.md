# Coverage matrix

Maps each behavior we want to **guarantee functionally** to where the minimal
invoicing scenario exercises it. The aim is to prove the schema/scenario is
**minimal yet complete**: every row is covered by at least one operation, and no
construct is included that isn't asserted on.

Status: **draft** — fill the "Exercised by" column as the schema and scenario
are authored. Keep only the faithfully-transpilable subset here (lossy
constructs belong to the syntactic/`-- UNIQUE:` tests, not this matrix).

## Data types

| Type (canonical) | Column | Exercised by | Notes |
|---|---|---|---|
| INT / identity | `customer.id`, `invoice.id` | _TBD_ | identity or sequence, pinned start |
| DECIMAL(p,s) | `invoice_line.unit_price`, `invoice.total` | _TBD_ | explicit scale; no float |
| VARCHAR(n) | `customer.name`, `product.name` | _TBD_ | trim CHAR vs VARCHAR on read |
| DATE | `invoice.issued_on` | _TBD_ | fixed literal dates only |
| DATETIME / timestamp | `invoice.created_at` | _TBD_ | trigger-stamped → assert relationship, not value, OR frozen clock |
| BIT / BOOLEAN | `invoice.is_paid` | _TBD_ | normalize 0/1 ↔ false/true on read |
| TEXT / CLOB | `customer.notes` | _TBD_ | from VARCHAR(MAX) |

## Object types

| Object | Name | Exercised by | Notes |
|---|---|---|---|
| Table + PK | all | _TBD_ | |
| FK constraint | `invoice.customer_id`, `invoice_line.invoice_id` | _TBD_ | cascade behavior asserted |
| UNIQUE constraint | `customer.email` | _TBD_ | |
| CHECK constraint | `invoice_line.qty > 0` | _TBD_ | reject-path asserted? (optional) |
| DEFAULT | `invoice.is_paid = 0` | _TBD_ | |
| Identity / sequence | `*.id` | _TBD_ | pin start/increment |
| View | `v_invoice_totals` | _TBD_ | aggregate over lines |
| Trigger (AFTER ins/upd) | `trg_line_total` | _TBD_ | recompute `invoice.total` — "update on a triggered table" |
| Stored procedure | `create_invoice` | _TBD_ | inserts header+lines, returns id — "DML from a procedure" |
| Function (scalar) | `fn_tax` | _TBD_ | compute tax on an amount |

## Mutations (the behavioral scenario)

| Step | Operation | Expected effect | Asserted as |
|---|---|---|---|
| 1 | seed `customer`, `product` | base rows present | row counts + fixed values |
| 2 | direct `INSERT` into `invoice` + `invoice_line` | trigger recomputes `invoice.total` | `invoice.total` value |
| 3 | `UPDATE invoice_line` (qty/price) | trigger readjusts `invoice.total` | updated `invoice.total` |
| 4 | `CALL create_invoice(...)` | new invoice + lines from a proc | new row counts + total |
| 5 | `INSERT payment` | (optional) mark invoice paid | `invoice.is_paid` |

## Determinism checklist (per asserted value)

- [ ] No `GETDATE()`/`SYSDATE`/`NOW()` in an asserted column (or clock frozen).
- [ ] No integer-division ambiguity in an asserted expression.
- [ ] No NULL operand in an asserted concatenation.
- [ ] Explicit `DECIMAL(p, s)` for all monetary values.
- [ ] Reads use `ORDER BY <pk>`; values normalized per type on read.
