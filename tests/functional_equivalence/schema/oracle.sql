-- ============================================================================
-- Unique — functional-equivalence schema, authored natively in Oracle.
--
-- Phase 2 (4x4 matrix): the Oracle-idiomatic source. Also exercises the Oracle
-- parser when used as a transpile source. Run on its own it must reach the same
-- engine-agnostic ../expected_state.yaml.
--
-- Idiomatic choices: GENERATED ALWAYS AS IDENTITY, NUMBER(1) for booleans (0/1),
-- VARCHAR2 / CLOB, NUMBER(p, s) for money, row-level triggers (Oracle has no
-- named statement-level transition tables that fit this shape simply), and
-- PL/SQL bodies terminated by '/'. The harness splits on '/' block terminators.
-- Determinism matches the canonical design: explicit NUMBER(p, s), 10% tax.
--
-- Re-runnable: each object is dropped first, ignoring "does not exist" errors
-- via a small anonymous block, since Oracle has no DROP ... IF EXISTS pre-23c.
-- ============================================================================

BEGIN
    FOR r IN (
        SELECT 'DROP TABLE ' || table_name || ' CASCADE CONSTRAINTS' AS cmd
        FROM user_tables
        WHERE table_name IN ('PAYMENT', 'INVOICE_LINE', 'INVOICE', 'PRODUCT', 'CUSTOMER')
    ) LOOP
        EXECUTE IMMEDIATE r.cmd;
    END LOOP;
    FOR r IN (
        SELECT 'DROP ' || object_type || ' ' || object_name AS cmd
        FROM user_objects
        WHERE object_name IN ('FN_TAX', 'FN_DAYS_BETWEEN', 'CREATE_INVOICE',
                              'V_INVOICE_TOTALS', 'V_OVERDUE_INVOICES')
          AND object_type IN ('FUNCTION', 'PROCEDURE', 'VIEW')
    ) LOOP
        EXECUTE IMMEDIATE r.cmd;
    END LOOP;
END;
/


-- ----------------------------------------------------------------------------
-- TABLES
-- ----------------------------------------------------------------------------

CREATE TABLE customer (
    id         NUMBER        GENERATED ALWAYS AS IDENTITY,
    name       VARCHAR2(100) NOT NULL,
    email      VARCHAR2(200) NOT NULL,
    notes      CLOB          NULL,
    created_at TIMESTAMP     DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT pk_customer PRIMARY KEY (id),
    CONSTRAINT uq_customer_email UNIQUE (email)
)
/

CREATE TABLE product (
    id         NUMBER        GENERATED ALWAYS AS IDENTITY,
    name       VARCHAR2(100) NOT NULL,
    unit_price NUMBER(10, 2) NOT NULL,
    is_active  NUMBER(1)     DEFAULT 1 NOT NULL,
    CONSTRAINT pk_product PRIMARY KEY (id)
)
/

CREATE TABLE invoice (
    id          NUMBER        GENERATED ALWAYS AS IDENTITY,
    customer_id NUMBER        NOT NULL,
    issued_on   DATE          NOT NULL,
    due_on      DATE          NULL,
    created_at  TIMESTAMP     DEFAULT SYSTIMESTAMP NOT NULL,
    updated_at  TIMESTAMP     NULL,
    is_paid     NUMBER(1)     DEFAULT 0 NOT NULL,
    total       NUMBER(12, 2) DEFAULT 0 NOT NULL,
    CONSTRAINT pk_invoice PRIMARY KEY (id),
    CONSTRAINT fk_invoice_customer FOREIGN KEY (customer_id)
        REFERENCES customer (id)
)
/

CREATE TABLE invoice_line (
    id         NUMBER        GENERATED ALWAYS AS IDENTITY,
    invoice_id NUMBER        NOT NULL,
    product_id NUMBER        NOT NULL,
    qty        NUMBER        NOT NULL,
    unit_price NUMBER(10, 2) NOT NULL,
    line_total NUMBER(10, 2) NOT NULL,
    CONSTRAINT pk_invoice_line PRIMARY KEY (id),
    CONSTRAINT fk_line_invoice FOREIGN KEY (invoice_id)
        REFERENCES invoice (id),
    CONSTRAINT fk_line_product FOREIGN KEY (product_id)
        REFERENCES product (id),
    CONSTRAINT ck_line_qty CHECK (qty > 0)
)
/

CREATE TABLE payment (
    id         NUMBER        GENERATED ALWAYS AS IDENTITY,
    invoice_id NUMBER        NOT NULL,
    paid_on    DATE          NOT NULL,
    amount     NUMBER(12, 2) NOT NULL,
    CONSTRAINT pk_payment PRIMARY KEY (id),
    CONSTRAINT fk_payment_invoice FOREIGN KEY (invoice_id)
        REFERENCES invoice (id)
)
/


-- ----------------------------------------------------------------------------
-- SCALAR FUNCTIONS
-- ----------------------------------------------------------------------------

CREATE FUNCTION fn_tax(net NUMBER) RETURN NUMBER IS
BEGIN
    RETURN net * 0.10;
END;
/

CREATE FUNCTION fn_days_between(d1 DATE, d2 DATE) RETURN NUMBER IS
BEGIN
    RETURN d2 - d1;
END;
/


-- ----------------------------------------------------------------------------
-- VIEWS
-- ----------------------------------------------------------------------------

CREATE VIEW v_invoice_totals AS
    SELECT il.invoice_id        AS invoice_id,
           SUM(il.line_total)   AS net_total,
           COUNT(*)             AS line_count
    FROM invoice_line il
    GROUP BY il.invoice_id
/

CREATE VIEW v_overdue_invoices AS
    SELECT i.id      AS invoice_id,
           i.due_on  AS due_on,
           i.is_paid AS is_paid
    FROM invoice i
    WHERE i.due_on IS NOT NULL
/


-- ----------------------------------------------------------------------------
-- TRIGGERS (row-level)
-- ----------------------------------------------------------------------------

-- Compute line_total before the row is written.
CREATE TRIGGER trg_line_compute
BEFORE INSERT OR UPDATE ON invoice_line
FOR EACH ROW
BEGIN
    :NEW.line_total := :NEW.qty * :NEW.unit_price;
END;
/

-- Roll up the invoice total = net + tax after lines change. A row-level AFTER
-- trigger that re-reads invoice_line would raise ORA-04091 (mutating table), so
-- this is a COMPOUND trigger: collect the affected invoice ids per row, then
-- re-aggregate once in AFTER STATEMENT (when the table is no longer mutating).
CREATE TRIGGER trg_line_total
FOR INSERT OR UPDATE ON invoice_line
COMPOUND TRIGGER
    TYPE id_tab IS TABLE OF NUMBER INDEX BY PLS_INTEGER;
    g_ids id_tab;
    g_n   PLS_INTEGER := 0;

    AFTER EACH ROW IS
    BEGIN
        g_n := g_n + 1;
        g_ids(g_n) := :NEW.invoice_id;
    END AFTER EACH ROW;

    AFTER STATEMENT IS
    BEGIN
        FOR i IN 1 .. g_n LOOP
            UPDATE invoice inv
            SET total = (SELECT NVL(SUM(il.line_total), 0)
                         FROM invoice_line il WHERE il.invoice_id = g_ids(i))
                      + fn_tax((SELECT NVL(SUM(il.line_total), 0)
                                FROM invoice_line il
                                WHERE il.invoice_id = g_ids(i)))
            WHERE inv.id = g_ids(i);
        END LOOP;
    END AFTER STATEMENT;
END;
/

-- Stamp updated_at (presence-asserted only).
CREATE TRIGGER trg_invoice_touch
BEFORE UPDATE ON invoice
FOR EACH ROW
BEGIN
    :NEW.updated_at := SYSTIMESTAMP;
END;
/

-- Mark the invoice paid once payments cover its total. Reading payment from a
-- row-level AFTER INSERT trigger would mutate; use a compound trigger.
CREATE TRIGGER trg_payment_paid
FOR INSERT ON payment
COMPOUND TRIGGER
    TYPE id_tab IS TABLE OF NUMBER INDEX BY PLS_INTEGER;
    g_ids id_tab;
    g_n   PLS_INTEGER := 0;

    AFTER EACH ROW IS
    BEGIN
        g_n := g_n + 1;
        g_ids(g_n) := :NEW.invoice_id;
    END AFTER EACH ROW;

    AFTER STATEMENT IS
    BEGIN
        FOR i IN 1 .. g_n LOOP
            UPDATE invoice inv
            SET is_paid = 1
            WHERE inv.id = g_ids(i)
              AND (SELECT NVL(SUM(p.amount), 0)
                   FROM payment p WHERE p.invoice_id = g_ids(i)) >= inv.total;
        END LOOP;
    END AFTER STATEMENT;
END;
/


-- ----------------------------------------------------------------------------
-- STORED PROCEDURE
-- ----------------------------------------------------------------------------

CREATE PROCEDURE create_invoice(
    p_customer_id IN NUMBER,
    p_issued_on   IN DATE,
    p_product_a   IN NUMBER,
    p_qty_a       IN NUMBER,
    p_product_b   IN NUMBER,
    p_qty_b       IN NUMBER
) IS
    v_new_id NUMBER;
BEGIN
    INSERT INTO invoice (customer_id, issued_on, due_on, created_at, is_paid, total)
    VALUES (p_customer_id, p_issued_on, NULL, SYSTIMESTAMP, 0, 0)
    RETURNING id INTO v_new_id;

    INSERT INTO invoice_line (invoice_id, product_id, qty, unit_price, line_total)
    SELECT v_new_id, p.id, p_qty_a, p.unit_price, p_qty_a * p.unit_price
    FROM product p WHERE p.id = p_product_a;

    INSERT INTO invoice_line (invoice_id, product_id, qty, unit_price, line_total)
    SELECT v_new_id, p.id, p_qty_b, p.unit_price, p_qty_b * p.unit_price
    FROM product p WHERE p.id = p_product_b;
END;
/
