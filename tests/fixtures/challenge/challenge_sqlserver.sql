-- Challenge fixtures — T-SQL source.
-- Anonymized tricky constructs; one per entry. See README.md.

-- CASE: CREATE PROC abbreviation (PROC == PROCEDURE) must route like the full
-- spelling and never leak the T-SQL-only PROC keyword to another engine.
CREATE PROC get_row
    @id INT
AS
BEGIN
    SET NOCOUNT ON;
    SELECT * FROM t WHERE id = @id;
END
GO

-- CASE: CREATE OR ALTER (T-SQL 2016+ idempotent form) must route to the
-- procedural engine (not degrade to an "Unhandled CREATE" carrier) and map to
-- the other engines' CREATE OR REPLACE.
CREATE OR ALTER PROCEDURE upd_row
    @id INT
AS
BEGIN
    UPDATE t SET touched = 1 WHERE id = @id;
END
GO

-- CASE: BEGIN TRANSACTION (and its BEGIN TRAN abbreviation) must translate to
-- each engine's transaction-open form; Oracle has none (implicit), so it drops
-- with a documented carrier rather than a bare invalid BEGIN.
BEGIN TRANSACTION
GO
