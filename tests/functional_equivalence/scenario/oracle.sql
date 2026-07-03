-- ============================================================================
-- Unique — functional-equivalence scenario, authored natively in Oracle.
--
-- Phase 2 (4x4). The five locked steps that drive schema/oracle.sql to
-- ../expected_state.yaml. Determinism matches the canonical design: fixed
-- dates, explicit NUMBER scale, 10% tax exact at scale 2.
-- ============================================================================

-- Step 1: seed
INSERT INTO customer (name, email, notes)
VALUES ('Acme', 'billing@acme.test', 'Net-30 terms')
/

INSERT INTO customer (name, email, notes)
VALUES ('Globex', 'ap@globex.test', NULL)
/

INSERT INTO product (name, unit_price, is_active)
VALUES ('Widget', 10.00, 1)
/

INSERT INTO product (name, unit_price, is_active)
VALUES ('Gadget', 25.50, 1)
/

-- Step 2: direct INSERT invoice 1 + lines (2 Widget + 1 Gadget = net 45.50)
INSERT INTO invoice (customer_id, issued_on, due_on, created_at, is_paid, total)
VALUES (1, DATE '2024-01-15', NULL, SYSTIMESTAMP, 0, 0)
/

INSERT INTO invoice_line (invoice_id, product_id, qty, unit_price, line_total)
VALUES (1, 1, 2, 10.00, 20.00)
/

INSERT INTO invoice_line (invoice_id, product_id, qty, unit_price, line_total)
VALUES (1, 2, 1, 25.50, 25.50)
/

-- Step 3: UPDATE a line (Widget qty 2 -> 3) -> compound trigger recomputes 61.05
UPDATE invoice_line
SET qty = 3
WHERE invoice_id = 1 AND product_id = 1
/

-- Step 4: DML from a stored procedure -> invoice 2 (net 35.50, total 39.05)
BEGIN
    create_invoice(2, DATE '2024-02-01', 1, 1, 2, 1);
END;
/

-- Step 5: payment equal to invoice 2's total -> trg_payment_paid marks it paid
INSERT INTO payment (invoice_id, paid_on, amount)
VALUES (2, DATE '2024-02-05', 39.05)
/

-- Step 6: payment-status flag (audit S2-3 counterpart) -> customer 1 has no
-- payment ('no payment'); customer 2 is paid ('paid').
BEGIN
    flag_payment_status(1, 1);
END;
/

BEGIN
    flag_payment_status(2, 2);
END;
/
