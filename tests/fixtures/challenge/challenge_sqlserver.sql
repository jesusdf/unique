-- Challenge fixtures — T-SQL source.
-- Anonymized tricky constructs; one per entry. See README.md.

-- CASE: CREATE PROC abbreviation (PROC == PROCEDURE) must route like the full
-- spelling and never leak the T-SQL-only PROC keyword to other engines.
CREATE PROC get_row
    @id INT
AS
BEGIN
    SET NOCOUNT ON;
    SELECT * FROM t WHERE id = @id;
END
