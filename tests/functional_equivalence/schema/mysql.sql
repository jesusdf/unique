-- ============================================================================
-- Unique — functional-equivalence schema, authored natively in MySQL.
--
-- Phase 2 (4x4 matrix): the MySQL-idiomatic source. Also exercises the MySQL
-- parser when used as a transpile source. Run on its own it must reach the same
-- engine-agnostic ../expected_state.yaml.
--
-- Idiomatic choices: AUTO_INCREMENT, TINYINT(1) for booleans, FOR EACH ROW
-- triggers (MySQL has no statement-level transition tables, so the row-level
-- form is the native one here), and a stored procedure with a DELIMITER block.
-- The harness strips DELIMITER directives and splits on the chosen delimiter.
-- Determinism matches the canonical design: explicit DECIMAL(p, s), 10% tax.
--
-- NOTE: this file is authored for direct execution by the harness, which keeps
-- routine bodies (BEGIN..END) intact. DELIMITER lines are included for parity
-- with hand-running in the mysql client; the runner ignores them.
-- ============================================================================

DROP TABLE IF EXISTS payment;
DROP TABLE IF EXISTS invoice_line;
DROP TABLE IF EXISTS invoice;
DROP TABLE IF EXISTS product;
DROP TABLE IF EXISTS customer;
DROP FUNCTION IF EXISTS fn_tax;
DROP FUNCTION IF EXISTS fn_days_between;
DROP PROCEDURE IF EXISTS create_invoice;
DROP PROCEDURE IF EXISTS flag_payment_status;
DROP VIEW IF EXISTS v_invoice_totals;
DROP VIEW IF EXISTS v_overdue_invoices;


-- ----------------------------------------------------------------------------
-- TABLES
-- ----------------------------------------------------------------------------

CREATE TABLE customer (
    id         INT           NOT NULL AUTO_INCREMENT,
    name       VARCHAR(100)  NOT NULL,
    email      VARCHAR(200)  NOT NULL,
    notes      TEXT          NULL,
    created_at DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_customer_email (email)
);

CREATE TABLE product (
    id         INT           NOT NULL AUTO_INCREMENT,
    name       VARCHAR(100)  NOT NULL,
    unit_price DECIMAL(10, 2) NOT NULL,
    is_active  TINYINT(1)    NOT NULL DEFAULT 1,
    PRIMARY KEY (id)
);

CREATE TABLE invoice (
    id          INT           NOT NULL AUTO_INCREMENT,
    customer_id INT           NOT NULL,
    issued_on   DATE          NOT NULL,
    due_on      DATE          NULL,
    created_at  DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  DATETIME      NULL,
    is_paid     TINYINT(1)    NOT NULL DEFAULT 0,
    total       DECIMAL(12, 2) NOT NULL DEFAULT 0,
    PRIMARY KEY (id),
    CONSTRAINT fk_invoice_customer FOREIGN KEY (customer_id)
        REFERENCES customer (id)
);

CREATE TABLE invoice_line (
    id         INT           NOT NULL AUTO_INCREMENT,
    invoice_id INT           NOT NULL,
    product_id INT           NOT NULL,
    qty        INT           NOT NULL,
    unit_price DECIMAL(10, 2) NOT NULL,
    line_total DECIMAL(10, 2) NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT fk_line_invoice FOREIGN KEY (invoice_id)
        REFERENCES invoice (id),
    CONSTRAINT fk_line_product FOREIGN KEY (product_id)
        REFERENCES product (id),
    CONSTRAINT ck_line_qty CHECK (qty > 0)
);

CREATE TABLE payment (
    id         INT           NOT NULL AUTO_INCREMENT,
    invoice_id INT           NOT NULL,
    paid_on    DATE          NOT NULL,
    amount     DECIMAL(12, 2) NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT fk_payment_invoice FOREIGN KEY (invoice_id)
        REFERENCES invoice (id)
);


-- ----------------------------------------------------------------------------
-- SCALAR FUNCTIONS
-- ----------------------------------------------------------------------------

DELIMITER //

CREATE FUNCTION fn_tax(net DECIMAL(12, 2)) RETURNS DECIMAL(12, 2)
DETERMINISTIC
BEGIN
    RETURN net * 0.10;
END //

CREATE FUNCTION fn_days_between(d1 DATE, d2 DATE) RETURNS INT
DETERMINISTIC
BEGIN
    RETURN DATEDIFF(d2, d1);
END //

DELIMITER ;


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
-- TRIGGERS (row-level — MySQL has no statement-level transition tables)
-- ----------------------------------------------------------------------------

DELIMITER //

-- Maintain line_total for the row, then roll up the invoice total = net + tax.
CREATE TRIGGER trg_line_total_ins
AFTER INSERT ON invoice_line
FOR EACH ROW
BEGIN
    UPDATE invoice inv
    SET total = (SELECT COALESCE(SUM(il.line_total), 0)
                 FROM invoice_line il WHERE il.invoice_id = NEW.invoice_id)
              + fn_tax((SELECT COALESCE(SUM(il.line_total), 0)
                        FROM invoice_line il WHERE il.invoice_id = NEW.invoice_id))
    WHERE inv.id = NEW.invoice_id;
END //

CREATE TRIGGER trg_line_total_upd
AFTER UPDATE ON invoice_line
FOR EACH ROW
BEGIN
    UPDATE invoice inv
    SET total = (SELECT COALESCE(SUM(il.line_total), 0)
                 FROM invoice_line il WHERE il.invoice_id = NEW.invoice_id)
              + fn_tax((SELECT COALESCE(SUM(il.line_total), 0)
                        FROM invoice_line il WHERE il.invoice_id = NEW.invoice_id))
    WHERE inv.id = NEW.invoice_id;
END //

-- line_total is kept correct by computing it BEFORE the row is written.
CREATE TRIGGER trg_line_compute_ins
BEFORE INSERT ON invoice_line
FOR EACH ROW
BEGIN
    SET NEW.line_total = NEW.qty * NEW.unit_price;
END //

CREATE TRIGGER trg_line_compute_upd
BEFORE UPDATE ON invoice_line
FOR EACH ROW
BEGIN
    SET NEW.line_total = NEW.qty * NEW.unit_price;
END //

-- Stamp updated_at (presence-asserted only).
CREATE TRIGGER trg_invoice_touch
BEFORE UPDATE ON invoice
FOR EACH ROW
BEGIN
    SET NEW.updated_at = CURRENT_TIMESTAMP;
END //

-- Mark the invoice paid once its payments cover its total.
CREATE TRIGGER trg_payment_paid
AFTER INSERT ON payment
FOR EACH ROW
BEGIN
    UPDATE invoice inv
    SET is_paid = 1
    WHERE inv.id = NEW.invoice_id
      AND (SELECT COALESCE(SUM(p.amount), 0)
           FROM payment p WHERE p.invoice_id = NEW.invoice_id) >= inv.total;
END //

DELIMITER ;


-- ----------------------------------------------------------------------------
-- STORED PROCEDURE
-- ----------------------------------------------------------------------------

DELIMITER //

CREATE PROCEDURE create_invoice(
    IN p_customer_id INT,
    IN p_issued_on   DATE,
    IN p_product_a   INT,
    IN p_qty_a       INT,
    IN p_product_b   INT,
    IN p_qty_b       INT
)
BEGIN
    DECLARE v_new_id INT;

    INSERT INTO invoice (customer_id, issued_on, due_on, created_at, is_paid, total)
    VALUES (p_customer_id, p_issued_on, NULL, CURRENT_TIMESTAMP, 0, 0);

    SET v_new_id = LAST_INSERT_ID();

    INSERT INTO invoice_line (invoice_id, product_id, qty, unit_price, line_total)
    SELECT v_new_id, p.id, p_qty_a, p.unit_price, p_qty_a * p.unit_price
    FROM product p WHERE p.id = p_product_a;

    INSERT INTO invoice_line (invoice_id, product_id, qty, unit_price, line_total)
    SELECT v_new_id, p.id, p_qty_b, p.unit_price, p_qty_b * p.unit_price
    FROM product p WHERE p.id = p_product_b;
END //

DELIMITER ;

-- Payment-status flag (audit S2-3 counterpart). Authored with MAX() so the
-- no-payment case yields NULL portably (an aggregate always returns one row).
DELIMITER //

CREATE PROCEDURE flag_payment_status(
    IN p_customer_id INT,
    IN p_invoice_id  INT
)
BEGIN
    DECLARE v_amount DECIMAL(12, 2);

    SELECT MAX(amount) INTO v_amount FROM payment WHERE invoice_id = p_invoice_id;

    IF v_amount IS NULL THEN
        UPDATE customer SET notes = 'no payment' WHERE id = p_customer_id;
    ELSE
        UPDATE customer SET notes = 'paid' WHERE id = p_customer_id;
    END IF;
END //

DELIMITER ;


-- Scenario C — app_flag.
DROP TABLE IF EXISTS app_flag;
CREATE TABLE app_flag (
    id        INT          AUTO_INCREMENT,
    flag_name VARCHAR(50)  NOT NULL,
    enabled   TINYINT(1)   NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_app_flag_name (flag_name)
);

ALTER TABLE app_flag ADD COLUMN note VARCHAR(20);
