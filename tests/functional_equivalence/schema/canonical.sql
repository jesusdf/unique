-- ============================================================================
-- Unique — functional-equivalence canonical SCHEMA (Phase 1 source: T-SQL).
--
-- This is the SINGLE authored DDL. The transpiler generates the MySQL,
-- PostgreSQL and Oracle equivalents from it; all four are then run and asserted
-- against the one engine-agnostic spec in ../expected_state.yaml.
--
-- Design is locked in ../coverage-matrix.md (Scenario A + Scenario B) and
-- visualized in schema.mmd. Everything here is deliberately deterministic
-- across engines: explicit DECIMAL(p, s); identity pinned to START 1 INCREMENT
-- 1; no engine-defined behavior in any column that ../expected_state.yaml
-- asserts on. Clock-stamped columns (created_at, updated_at) are present but
-- assert presence only.
--
-- Schema: dbo. Object-creation order respects FK dependencies. Idempotent
-- guards (IF OBJECT_ID ... IS NULL / DROP IF EXISTS) so the harness can re-run
-- a clean setup. SQL Server 2012+ syntax (matches the project's source floor).
-- ============================================================================


-- ----------------------------------------------------------------------------
-- TABLES
-- ----------------------------------------------------------------------------

IF OBJECT_ID(N'dbo.customer', N'U') IS NULL
CREATE TABLE dbo.customer (
    id         INT            IDENTITY(1, 1) NOT NULL,
    name       VARCHAR(100)   NOT NULL,
    email      VARCHAR(200)   NOT NULL,
    notes      VARCHAR(MAX)   NULL,          -- TEXT/CLOB carrier; NULL on one row
    created_at DATETIME       NOT NULL DEFAULT SYSDATETIME(),  -- presence only
    CONSTRAINT pk_customer PRIMARY KEY (id),
    CONSTRAINT uq_customer_email UNIQUE (email)
)
GO

IF OBJECT_ID(N'dbo.product', N'U') IS NULL
CREATE TABLE dbo.product (
    id         INT            IDENTITY(1, 1) NOT NULL,
    name       VARCHAR(100)   NOT NULL,
    unit_price DECIMAL(10, 2) NOT NULL,
    is_active  BIT            NOT NULL DEFAULT 1,   -- Scenario B: toggled by UPDATE
    CONSTRAINT pk_product PRIMARY KEY (id)
)
GO

IF OBJECT_ID(N'dbo.invoice', N'U') IS NULL
CREATE TABLE dbo.invoice (
    id          INT            IDENTITY(1, 1) NOT NULL,
    customer_id INT            NOT NULL,
    issued_on   DATE           NOT NULL,
    due_on      DATE           NULL,         -- Scenario B: issued_on + 30 days
    created_at  DATETIME       NOT NULL DEFAULT SYSDATETIME(),  -- presence only
    updated_at  DATETIME       NULL,         -- Scenario B: set by trg_invoice_touch
    is_paid     BIT            NOT NULL DEFAULT 0,
    total       DECIMAL(12, 2) NOT NULL DEFAULT 0,  -- maintained by trg_line_total
    CONSTRAINT pk_invoice PRIMARY KEY (id),
    CONSTRAINT fk_invoice_customer FOREIGN KEY (customer_id)
        REFERENCES dbo.customer (id)
)
GO

IF OBJECT_ID(N'dbo.invoice_line', N'U') IS NULL
CREATE TABLE dbo.invoice_line (
    id         INT            IDENTITY(1, 1) NOT NULL,
    invoice_id INT            NOT NULL,
    product_id INT            NOT NULL,
    qty        INT            NOT NULL,
    unit_price DECIMAL(10, 2) NOT NULL,
    line_total DECIMAL(10, 2) NOT NULL,      -- qty * unit_price (maintained)
    CONSTRAINT pk_invoice_line PRIMARY KEY (id),
    CONSTRAINT fk_line_invoice FOREIGN KEY (invoice_id)
        REFERENCES dbo.invoice (id),
    CONSTRAINT fk_line_product FOREIGN KEY (product_id)
        REFERENCES dbo.product (id),
    CONSTRAINT ck_line_qty CHECK (qty > 0)
)
GO

IF OBJECT_ID(N'dbo.payment', N'U') IS NULL
CREATE TABLE dbo.payment (
    id         INT            IDENTITY(1, 1) NOT NULL,
    invoice_id INT            NOT NULL,
    paid_on    DATE           NOT NULL,
    amount     DECIMAL(12, 2) NOT NULL,
    CONSTRAINT pk_payment PRIMARY KEY (id),
    CONSTRAINT fk_payment_invoice FOREIGN KEY (invoice_id)
        REFERENCES dbo.invoice (id)
)
GO

-- ----------------------------------------------------------------------------
-- SEQUENCE (Scenario B surface; MySQL target maps this to AUTO_INCREMENT)
-- ----------------------------------------------------------------------------

IF OBJECT_ID(N'dbo.invoice_seq', N'SO') IS NOT NULL
    DROP SEQUENCE dbo.invoice_seq
GO

CREATE SEQUENCE dbo.invoice_seq
    AS INT
    START WITH 1
    INCREMENT BY 1
GO


-- ----------------------------------------------------------------------------
-- SCALAR FUNCTIONS
-- ----------------------------------------------------------------------------

-- fn_tax: 10% tax. Rate chosen so every taxed subtotal in the scenario is exact
-- at scale 2 (no rounding-mode dependence between engines).
IF OBJECT_ID(N'dbo.fn_tax', N'FN') IS NOT NULL
    DROP FUNCTION dbo.fn_tax
GO

CREATE FUNCTION dbo.fn_tax (@net DECIMAL(12, 2))
RETURNS DECIMAL(12, 2)
AS
BEGIN
    RETURN @net * CAST(0.10 AS DECIMAL(12, 2))
END
GO

-- fn_days_between: engine-neutral DATEDIFF wrapper (whole days, @d2 - @d1).
IF OBJECT_ID(N'dbo.fn_days_between', N'FN') IS NOT NULL
    DROP FUNCTION dbo.fn_days_between
GO

CREATE FUNCTION dbo.fn_days_between (@d1 DATE, @d2 DATE)
RETURNS INT
AS
BEGIN
    RETURN DATEDIFF(DAY, @d1, @d2)
END
GO


-- ----------------------------------------------------------------------------
-- VIEWS
-- ----------------------------------------------------------------------------

IF OBJECT_ID(N'dbo.v_invoice_totals', N'V') IS NOT NULL
    DROP VIEW dbo.v_invoice_totals
GO

CREATE VIEW dbo.v_invoice_totals
AS
    SELECT
        il.invoice_id          AS invoice_id,
        SUM(il.line_total)     AS net_total,
        COUNT(*)               AS line_count
    FROM dbo.invoice_line AS il
    GROUP BY il.invoice_id
GO

-- v_overdue_invoices: date-driven view. days_overdue is computed against a
-- caller-supplied "as of" date at query time, never a clock function, so the
-- view itself stays deterministic; the harness passes a fixed as-of date.
IF OBJECT_ID(N'dbo.v_overdue_invoices', N'V') IS NOT NULL
    DROP VIEW dbo.v_overdue_invoices
GO

CREATE VIEW dbo.v_overdue_invoices
AS
    SELECT
        i.id        AS invoice_id,
        i.due_on    AS due_on,
        i.is_paid   AS is_paid
    FROM dbo.invoice AS i
    WHERE i.due_on IS NOT NULL
GO


-- ----------------------------------------------------------------------------
-- TRIGGERS
-- ----------------------------------------------------------------------------

-- trg_line_total: keep invoice_line.line_total and invoice.total consistent.
-- Set-based (operates over the inserted/deleted pseudo-tables, not row-by-row)
-- so it is faithfully transpilable to the other engines. invoice.total is the
-- per-invoice net (SUM of line_total) plus fn_tax of that net.
IF OBJECT_ID(N'dbo.trg_line_total', N'TR') IS NOT NULL
    DROP TRIGGER dbo.trg_line_total
GO

CREATE TRIGGER dbo.trg_line_total
ON dbo.invoice_line
AFTER INSERT, UPDATE
AS
BEGIN
    SET NOCOUNT ON;

    -- Maintain line_total for the affected rows.
    UPDATE il
    SET il.line_total = il.qty * il.unit_price
    FROM dbo.invoice_line AS il
    INNER JOIN inserted AS i ON i.id = il.id;

    -- Recompute the rolled-up total (net + tax) for every affected invoice.
    -- Uses a correlated subquery (not a JOIN against an aggregate subquery) so
    -- the statement transpiles faithfully to every engine's UPDATE form.
    UPDATE inv
    SET inv.total =
        (SELECT SUM(il.line_total) FROM dbo.invoice_line AS il
         WHERE il.invoice_id = inv.id)
        + dbo.fn_tax(
            (SELECT SUM(il.line_total) FROM dbo.invoice_line AS il
             WHERE il.invoice_id = inv.id))
    FROM dbo.invoice AS inv
    WHERE inv.id IN (
        SELECT invoice_id FROM inserted
        UNION
        SELECT invoice_id FROM deleted
    );
END
GO

-- trg_invoice_touch: BEFORE-UPDATE semantics. T-SQL has no BEFORE trigger, so
-- the canonical form is an AFTER UPDATE that stamps updated_at; targets that
-- support BEFORE (Oracle/PostgreSQL/MySQL) may receive a BEFORE form. updated_at
-- is presence-asserted only, so the exact clock value never affects equivalence.
IF OBJECT_ID(N'dbo.trg_invoice_touch', N'TR') IS NOT NULL
    DROP TRIGGER dbo.trg_invoice_touch
GO

CREATE TRIGGER dbo.trg_invoice_touch
ON dbo.invoice
AFTER UPDATE
AS
BEGIN
    SET NOCOUNT ON;

    -- Stamp updated_at for the affected rows. Set-based over inserted (no
    -- UPDATE(col) predicate, so the trigger is *purely* set-based and maps onto
    -- PostgreSQL transition tables). The WHERE guard skips rows already stamped
    -- this second, preventing the AFTER-UPDATE trigger from re-firing forever.
    UPDATE inv
    SET inv.updated_at = SYSDATETIME()
    FROM dbo.invoice AS inv
    INNER JOIN inserted AS i ON i.id = inv.id
    WHERE (inv.updated_at IS NULL
       OR inv.updated_at <> SYSDATETIME());
END
GO

-- trg_payment_paid: when a payment is recorded, mark the invoice paid once the
-- sum of its payments covers its total. Set-based over inserted.
IF OBJECT_ID(N'dbo.trg_payment_paid', N'TR') IS NOT NULL
    DROP TRIGGER dbo.trg_payment_paid
GO

CREATE TRIGGER dbo.trg_payment_paid
ON dbo.payment
AFTER INSERT
AS
BEGIN
    SET NOCOUNT ON;

    -- Mark an invoice paid once its payments cover its total. Correlated
    -- subquery (not a JOIN against an aggregate) for faithful transpilation.
    UPDATE inv
    SET inv.is_paid = 1
    FROM dbo.invoice AS inv
    WHERE inv.id IN (SELECT invoice_id FROM inserted)
      AND (SELECT SUM(p.amount) FROM dbo.payment AS p
           WHERE p.invoice_id = inv.id) >= inv.total;
END
GO

-- ----------------------------------------------------------------------------
-- STORED PROCEDURE
-- ----------------------------------------------------------------------------

-- create_invoice: build an invoice header + its two lines for a customer, then
-- return the new invoice id. The "DML from a procedure" path. unit_price is
-- copied from product so a later reprice does not change historical lines;
-- invoice.total is maintained by trg_line_total as each line is inserted, and
-- is_paid is left at its DEFAULT (0).
IF OBJECT_ID(N'dbo.create_invoice', N'P') IS NOT NULL
    DROP PROCEDURE dbo.create_invoice
GO

CREATE PROCEDURE dbo.create_invoice
    @customer_id INT,
    @issued_on   DATE,
    @product_a   INT,
    @qty_a       INT,
    @product_b   INT,
    @qty_b       INT
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @new_id INT;

    INSERT INTO dbo.invoice (customer_id, issued_on, due_on, created_at, is_paid, total)
    VALUES (@customer_id, @issued_on, NULL, SYSDATETIME(), 0, 0);

    SET @new_id = SCOPE_IDENTITY();

    INSERT INTO dbo.invoice_line (invoice_id, product_id, qty, unit_price, line_total)
    SELECT @new_id, p.id, @qty_a, p.unit_price, @qty_a * p.unit_price
    FROM dbo.product AS p
    WHERE p.id = @product_a;

    INSERT INTO dbo.invoice_line (invoice_id, product_id, qty, unit_price, line_total)
    SELECT @new_id, p.id, @qty_b, p.unit_price, @qty_b * p.unit_price
    FROM dbo.product AS p
    WHERE p.id = @product_b;
END
GO
