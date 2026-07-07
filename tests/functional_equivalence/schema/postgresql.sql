-- ============================================================================
-- Unique — functional-equivalence schema, authored natively in PostgreSQL.
--
-- Phase 2 (4x4 matrix): this is the PostgreSQL-idiomatic source. It also
-- exercises the PostgreSQL *parser* when used as a transpile source. Run on
-- its own it must reach the same engine-agnostic ../expected_state.yaml as the
-- T-SQL canonical schema (and as every other source after transpilation).
--
-- Idiomatic choices: GENERATED ALWAYS AS IDENTITY, BOOLEAN, TEXT, TIMESTAMP,
-- a statement-level trigger using REFERENCING ... NEW/OLD TABLE transition
-- tables, and DROP ... CASCADE guards so the harness can re-run a clean setup.
-- Determinism matches the canonical design: explicit NUMERIC(p, s), 10% tax
-- exact at scale 2, no clock value asserted (created_at / updated_at).
-- ============================================================================

DROP TABLE IF EXISTS payment CASCADE;
DROP TABLE IF EXISTS invoice_line CASCADE;
DROP TABLE IF EXISTS invoice CASCADE;
DROP TABLE IF EXISTS product CASCADE;
DROP TABLE IF EXISTS customer CASCADE;
DROP FUNCTION IF EXISTS fn_tax(NUMERIC) CASCADE;
DROP FUNCTION IF EXISTS fn_days_between(DATE, DATE) CASCADE;
DROP PROCEDURE IF EXISTS create_invoice(INTEGER, DATE, INTEGER, INTEGER, INTEGER, INTEGER);
DROP PROCEDURE IF EXISTS flag_payment_status(INTEGER, INTEGER);
DROP FUNCTION IF EXISTS trg_line_total_ins_fn() CASCADE;
DROP FUNCTION IF EXISTS trg_line_total_upd_fn() CASCADE;
DROP FUNCTION IF EXISTS trg_line_total_fn() CASCADE;
DROP FUNCTION IF EXISTS trg_invoice_touch_fn() CASCADE;
DROP FUNCTION IF EXISTS trg_payment_paid_fn() CASCADE;


-- ----------------------------------------------------------------------------
-- TABLES
-- ----------------------------------------------------------------------------

CREATE TABLE customer (
    id         INTEGER       GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name       VARCHAR(100)  NOT NULL,
    email      VARCHAR(200)  NOT NULL UNIQUE,
    notes      TEXT          NULL,
    created_at TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE product (
    id         INTEGER       GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name       VARCHAR(100)  NOT NULL,
    unit_price NUMERIC(10, 2) NOT NULL,
    is_active  BOOLEAN       NOT NULL DEFAULT TRUE
);

CREATE TABLE invoice (
    id          INTEGER       GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id INTEGER       NOT NULL REFERENCES customer (id),
    issued_on   DATE          NOT NULL,
    due_on      DATE          NULL,
    created_at  TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMP     NULL,
    is_paid     BOOLEAN       NOT NULL DEFAULT FALSE,
    total       NUMERIC(12, 2) NOT NULL DEFAULT 0
);

CREATE TABLE invoice_line (
    id         INTEGER       GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    invoice_id INTEGER       NOT NULL REFERENCES invoice (id),
    product_id INTEGER       NOT NULL REFERENCES product (id),
    qty        INTEGER       NOT NULL CHECK (qty > 0),
    unit_price NUMERIC(10, 2) NOT NULL,
    line_total NUMERIC(10, 2) NOT NULL
);

CREATE TABLE payment (
    id         INTEGER       GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    invoice_id INTEGER       NOT NULL REFERENCES invoice (id),
    paid_on    DATE          NOT NULL,
    amount     NUMERIC(12, 2) NOT NULL
);


-- ----------------------------------------------------------------------------
-- SCALAR FUNCTIONS
-- ----------------------------------------------------------------------------

-- 10% tax; the rate makes every taxed subtotal exact at scale 2.
CREATE FUNCTION fn_tax(net NUMERIC) RETURNS NUMERIC AS $$
BEGIN
    RETURN net * 0.10;
END;
$$ LANGUAGE plpgsql;

-- Engine-neutral whole-day difference (d2 - d1).
CREATE FUNCTION fn_days_between(d1 DATE, d2 DATE) RETURNS INTEGER AS $$
BEGIN
    RETURN d2 - d1;
END;
$$ LANGUAGE plpgsql;


-- ----------------------------------------------------------------------------
-- VIEWS
-- ----------------------------------------------------------------------------

CREATE VIEW v_invoice_totals AS
    SELECT il.invoice_id        AS invoice_id,
           SUM(il.line_total)   AS net_total,
           COUNT(*)             AS line_count
    FROM invoice_line il
    GROUP BY il.invoice_id;

CREATE VIEW v_overdue_invoices AS
    SELECT i.id      AS invoice_id,
           i.due_on  AS due_on,
           i.is_paid AS is_paid
    FROM invoice i
    WHERE i.due_on IS NOT NULL;


-- ----------------------------------------------------------------------------
-- TRIGGERS (statement-level, using NEW/OLD transition tables)
-- ----------------------------------------------------------------------------

-- Maintain invoice_line.line_total and roll up invoice.total = net + tax.
-- PostgreSQL allows transition tables only on single-event triggers (and
-- OLD TABLE only on UPDATE/DELETE), so the INSERT and UPDATE paths are two
-- triggers with per-event functions.
CREATE FUNCTION trg_line_total_ins_fn() RETURNS TRIGGER AS $$
BEGIN
    -- Do not re-fire from our own statements (T-SQL semantics:
    -- RECURSIVE_TRIGGERS OFF; also stops statement-level recursion).
    IF pg_trigger_depth() > 1 THEN
        RETURN NULL;
    END IF;
    UPDATE invoice_line il
    SET line_total = il.qty * il.unit_price
    FROM inserted i
    WHERE i.id = il.id;

    UPDATE invoice inv
    SET total = (SELECT COALESCE(SUM(il.line_total), 0)
                 FROM invoice_line il WHERE il.invoice_id = inv.id)
              + fn_tax((SELECT COALESCE(SUM(il.line_total), 0)
                        FROM invoice_line il WHERE il.invoice_id = inv.id))
    WHERE inv.id IN (SELECT invoice_id FROM inserted);
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_line_total_ins
    AFTER INSERT ON invoice_line
    REFERENCING NEW TABLE AS inserted
    FOR EACH STATEMENT EXECUTE FUNCTION trg_line_total_ins_fn();

CREATE FUNCTION trg_line_total_upd_fn() RETURNS TRIGGER AS $$
BEGIN
    -- Do not re-fire from our own statements (T-SQL semantics:
    -- RECURSIVE_TRIGGERS OFF; also stops statement-level recursion).
    IF pg_trigger_depth() > 1 THEN
        RETURN NULL;
    END IF;
    UPDATE invoice_line il
    SET line_total = il.qty * il.unit_price
    FROM inserted i
    WHERE i.id = il.id;

    UPDATE invoice inv
    SET total = (SELECT COALESCE(SUM(il.line_total), 0)
                 FROM invoice_line il WHERE il.invoice_id = inv.id)
              + fn_tax((SELECT COALESCE(SUM(il.line_total), 0)
                        FROM invoice_line il WHERE il.invoice_id = inv.id))
    WHERE inv.id IN (SELECT invoice_id FROM inserted
                     UNION SELECT invoice_id FROM deleted);
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_line_total_upd
    AFTER UPDATE ON invoice_line
    REFERENCING NEW TABLE AS inserted OLD TABLE AS deleted
    FOR EACH STATEMENT EXECUTE FUNCTION trg_line_total_upd_fn();

-- Stamp updated_at on the affected rows (presence-asserted only).
CREATE FUNCTION trg_invoice_touch_fn() RETURNS TRIGGER AS $$
BEGIN
    -- Do not re-fire from our own statements (T-SQL semantics:
    -- RECURSIVE_TRIGGERS OFF; also stops statement-level recursion).
    IF pg_trigger_depth() > 1 THEN
        RETURN NULL;
    END IF;
    UPDATE invoice inv
    SET updated_at = CURRENT_TIMESTAMP
    FROM inserted i
    WHERE i.id = inv.id
      AND (inv.updated_at IS NULL OR inv.updated_at <> CURRENT_TIMESTAMP);
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_invoice_touch
    AFTER UPDATE ON invoice
    REFERENCING NEW TABLE AS inserted
    FOR EACH STATEMENT EXECUTE FUNCTION trg_invoice_touch_fn();

-- Mark an invoice paid once its payments cover its total.
CREATE FUNCTION trg_payment_paid_fn() RETURNS TRIGGER AS $$
BEGIN
    -- Do not re-fire from our own statements (T-SQL semantics:
    -- RECURSIVE_TRIGGERS OFF; also stops statement-level recursion).
    IF pg_trigger_depth() > 1 THEN
        RETURN NULL;
    END IF;
    UPDATE invoice inv
    SET is_paid = TRUE
    WHERE inv.id IN (SELECT invoice_id FROM inserted)
      AND (SELECT COALESCE(SUM(p.amount), 0)
           FROM payment p WHERE p.invoice_id = inv.id) >= inv.total;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_payment_paid
    AFTER INSERT ON payment
    REFERENCING NEW TABLE AS inserted
    FOR EACH STATEMENT EXECUTE FUNCTION trg_payment_paid_fn();


-- ----------------------------------------------------------------------------
-- STORED PROCEDURE
-- ----------------------------------------------------------------------------

-- Build an invoice header + its two lines for a customer. The "DML from a
-- procedure" path. invoice.total is maintained by trg_line_total per line.
CREATE PROCEDURE create_invoice(
    p_customer_id INTEGER,
    p_issued_on   DATE,
    p_product_a   INTEGER,
    p_qty_a       INTEGER,
    p_product_b   INTEGER,
    p_qty_b       INTEGER
) LANGUAGE plpgsql AS $$
DECLARE
    v_new_id INTEGER;
BEGIN
    INSERT INTO invoice (customer_id, issued_on, due_on, created_at, is_paid, total)
    VALUES (p_customer_id, p_issued_on, NULL, CURRENT_TIMESTAMP, FALSE, 0)
    RETURNING id INTO v_new_id;

    INSERT INTO invoice_line (invoice_id, product_id, qty, unit_price, line_total)
    SELECT v_new_id, p.id, p_qty_a, p.unit_price, p_qty_a * p.unit_price
    FROM product p WHERE p.id = p_product_a;

    INSERT INTO invoice_line (invoice_id, product_id, qty, unit_price, line_total)
    SELECT v_new_id, p.id, p_qty_b, p.unit_price, p_qty_b * p.unit_price
    FROM product p WHERE p.id = p_product_b;
END;
$$;

-- Payment-status flag (audit S2-3 counterpart). Authored with MAX() so the
-- no-payment case yields NULL portably (an aggregate always returns one row,
-- so no engine raises on the empty case).
CREATE PROCEDURE flag_payment_status(
    p_customer_id INTEGER,
    p_invoice_id  INTEGER
) LANGUAGE plpgsql AS $$
DECLARE
    v_amount NUMERIC(12, 2);
BEGIN
    SELECT MAX(amount) INTO v_amount FROM payment WHERE invoice_id = p_invoice_id;

    IF v_amount IS NULL THEN
        UPDATE customer SET notes = 'no payment' WHERE id = p_customer_id;
    ELSE
        UPDATE customer SET notes = 'paid' WHERE id = p_customer_id;
    END IF;
END;
$$;


-- Scenario C — app_flag.
DROP TABLE IF EXISTS app_flag CASCADE;
CREATE TABLE app_flag (
    id        INT          GENERATED ALWAYS AS IDENTITY,
    flag_name VARCHAR(50)  NOT NULL,
    enabled   BOOLEAN      NOT NULL,
    CONSTRAINT pk_app_flag PRIMARY KEY (id),
    CONSTRAINT uq_app_flag_name UNIQUE (flag_name)
);

ALTER TABLE app_flag ADD COLUMN note VARCHAR(20);
