-- ============================================================================
-- Unique — functional-equivalence scenario, authored natively in PostgreSQL.
--
-- Phase 2 (4x4). The five locked steps, idiomatic to PostgreSQL, that drive the
-- schema (schema/postgresql.sql) to ../expected_state.yaml. Determinism matches
-- the canonical design: fixed dates, explicit NUMERIC scale, 10% tax exact at
-- scale 2.
--
--   1. seed 2 customers (one with notes, one NULL) + 2 products
--   2. direct INSERT invoice 1 + 2 lines  -> trg_line_total sets total
--   3. UPDATE a line on invoice 1          -> trigger readjusts total
--   4. CALL create_invoice(...)            -> DML from a procedure
--   5. INSERT payment for invoice 2's total -> trg_payment_paid marks it paid
-- ============================================================================

-- Step 1: seed
INSERT INTO customer (name, email, notes)
VALUES ('Acme', 'billing@acme.test', 'Net-30 terms');

INSERT INTO customer (name, email, notes)
VALUES ('Globex', 'ap@globex.test', NULL);

INSERT INTO product (name, unit_price, is_active)
VALUES ('Widget', 10.00, TRUE);

INSERT INTO product (name, unit_price, is_active)
VALUES ('Gadget', 25.50, TRUE);

-- Step 2: direct INSERT invoice 1 + its lines (2 Widget + 1 Gadget = net 45.50)
INSERT INTO invoice (customer_id, issued_on, due_on, created_at, is_paid, total)
VALUES (1, DATE '2024-01-15', NULL, CURRENT_TIMESTAMP, FALSE, 0);

INSERT INTO invoice_line (invoice_id, product_id, qty, unit_price, line_total)
VALUES (1, 1, 2, 10.00, 20.00);

INSERT INTO invoice_line (invoice_id, product_id, qty, unit_price, line_total)
VALUES (1, 2, 1, 25.50, 25.50);

-- Step 3: UPDATE a line on the triggered table (Widget qty 2 -> 3)
-- trigger recomputes line_total (30.00) and invoice 1 total = 55.50 + 5.55 = 61.05
UPDATE invoice_line
SET qty = 3
WHERE invoice_id = 1 AND product_id = 1;

-- Step 4: DML from a stored procedure -> invoice 2 (1 Widget + 1 Gadget = 35.50)
-- total = 35.50 + fn_tax 3.55 = 39.05; is_paid stays FALSE until step 5.
CALL create_invoice(2, DATE '2024-02-01', 1, 1, 2, 1);

-- Step 5: payment equal to invoice 2's total -> trg_payment_paid marks it paid
INSERT INTO payment (invoice_id, paid_on, amount)
VALUES (2, DATE '2024-02-05', 39.05);
