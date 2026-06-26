-- ============================================================================
-- Unique — functional-equivalence canonical SCENARIO (Phase 1 source: T-SQL).
--
-- The ordered mutations that, run against a fresh schema (schema/canonical.sql),
-- produce exactly the state asserted in ../expected_state.yaml. The transpiler
-- generates the MySQL / PostgreSQL / Oracle variants; the harness runs all four
-- and checks each engine's final state against the single expected_state spec.
--
-- Determinism rules (see ../coverage-matrix.md): fixed literal dates, explicit
-- DECIMAL(p, s) literals, a 10% tax rate chosen so every taxed subtotal is exact
-- at scale 2, no integer division / NULL-concat / collation-dependent ordering
-- in any asserted value. Identity is pinned (START 1) so PK values are stable.
--
-- The five locked steps (../scenario/README.md):
--   1. seed 2 customers (one with notes, one NULL) + 2 products
--   2. direct INSERT invoice 1 + 2 lines (2 Widget, 1 Gadget) -> trg sets total
--   3. UPDATE a line on invoice 1 (Widget qty 2 -> 3)         -> trg readjusts
--   4. CALL create_invoice(...) builds invoice 2              -> DML-from-proc
--   5. INSERT payment for invoice 2's total                  -> marks it paid
-- ============================================================================


-- ---- Step 1: seed -----------------------------------------------------------

INSERT INTO dbo.customer (name, email, notes)
VALUES ('Acme', 'billing@acme.test', 'Net-30 terms');
GO

INSERT INTO dbo.customer (name, email, notes)
VALUES ('Globex', 'ap@globex.test', NULL);
GO

INSERT INTO dbo.product (name, unit_price, is_active)
VALUES ('Widget', CAST(10.00 AS DECIMAL(10, 2)), 1);
GO

INSERT INTO dbo.product (name, unit_price, is_active)
VALUES ('Gadget', CAST(25.50 AS DECIMAL(10, 2)), 1);
GO


-- ---- Step 2: direct INSERT invoice 1 + its lines ----------------------------
-- 2 Widget (20.00) + 1 Gadget (25.50) = net 45.50; trg_line_total then sets
-- invoice 1 total = 45.50 + fn_tax(45.50) = 50.05 (asserted only after step 3).

INSERT INTO dbo.invoice (customer_id, issued_on, due_on, created_at, is_paid, total)
VALUES (1, '2024-01-15', NULL, SYSDATETIME(), 0, 0);
GO

INSERT INTO dbo.invoice_line (invoice_id, product_id, qty, unit_price, line_total)
VALUES (1, 1, 2, CAST(10.00 AS DECIMAL(10, 2)), CAST(20.00 AS DECIMAL(10, 2)));
GO

INSERT INTO dbo.invoice_line (invoice_id, product_id, qty, unit_price, line_total)
VALUES (1, 2, 1, CAST(25.50 AS DECIMAL(10, 2)), CAST(25.50 AS DECIMAL(10, 2)));
GO


-- ---- Step 3: UPDATE a line on the triggered table ---------------------------
-- Widget qty 2 -> 3 on invoice 1. trg_line_total recomputes line_total (30.00)
-- and rolls up invoice 1 total = net 55.50 + fn_tax(55.50) 5.55 = 61.05.

UPDATE dbo.invoice_line
SET qty = 3
WHERE invoice_id = 1 AND product_id = 1;
GO


-- ---- Step 4: DML from a stored procedure ------------------------------------
-- create_invoice builds invoice 2 for Globex (1 Widget + 1 Gadget = net 35.50);
-- trg_line_total sets total = 35.50 + fn_tax(35.50) 3.55 = 39.05. is_paid stays
-- at its DEFAULT 0 until step 5. Positional arguments (no OUTPUT capture: the new
-- id is invoice 2, referenced directly in step 5) so the call is a portable
-- CALL create_invoice(...) on every engine.
--   args: @customer_id, @issued_on, @product_a, @qty_a, @product_b, @qty_b
EXEC dbo.create_invoice 2, '2024-02-01', 1, 1, 2, 1;
GO


-- ---- Step 5: payment marks invoice 2 paid -----------------------------------
-- A payment equal to invoice 2's total (39.05). trg_payment_paid marks the
-- invoice paid once its payments cover the total.

INSERT INTO dbo.payment (invoice_id, paid_on, amount)
VALUES (2, '2024-02-05', CAST(39.05 AS DECIMAL(12, 2)));
GO
