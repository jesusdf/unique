-- ============================================================
-- DDL: tables required by the procedure fixtures below.
-- Schema: dbo. Idempotent (IF NOT EXISTS guard per table).
-- ============================================================

IF OBJECT_ID(N'dbo.tbl_15', N'U') IS NULL
CREATE TABLE dbo.tbl_15 (
    col_59  VARCHAR(5)   NOT NULL,
    col_163 VARCHAR(200) NULL,
    CONSTRAINT pk_tbl_15 PRIMARY KEY (col_59)
)
GO

IF OBJECT_ID(N'dbo.tbl_14', N'U') IS NULL
CREATE TABLE dbo.tbl_14 (
    col_153 INT          NOT NULL,
    col_163 VARCHAR(200) NULL,
    CONSTRAINT pk_tbl_14 PRIMARY KEY (col_153)
)
GO

IF OBJECT_ID(N'dbo.tbl_13', N'U') IS NULL
CREATE TABLE dbo.tbl_13 (
    col_62  VARCHAR(50)  NOT NULL,
    col_46  VARCHAR(200) NULL,
    col_77  VARCHAR(200) NULL,
    CONSTRAINT pk_tbl_13 PRIMARY KEY (col_62)
)
GO

IF OBJECT_ID(N'dbo.tbl_12', N'U') IS NULL
CREATE TABLE dbo.tbl_12 (
    col_59  INT          NOT NULL,
    col_46  VARCHAR(200) NULL,
    col_153 INT          NULL,
    col_155 VARCHAR(5)   NULL,
    CONSTRAINT pk_tbl_12 PRIMARY KEY (col_59)
)
GO

IF OBJECT_ID(N'dbo.tbl_11', N'U') IS NULL
CREATE TABLE dbo.tbl_11 (
    col_59  INT          NOT NULL,
    col_60  INT          NULL,
    col_163 VARCHAR(200) NULL,
    CONSTRAINT pk_tbl_11 PRIMARY KEY (col_59)
)
GO

IF OBJECT_ID(N'dbo.tbl_10', N'U') IS NULL
CREATE TABLE dbo.tbl_10 (
    col_13  INT          NOT NULL,
    col_46  VARCHAR(200) NULL,
    col_48  VARCHAR(200) NULL,
    col_73  VARCHAR(200) NULL,
    col_164 VARCHAR(200) NULL,
    col_165 VARCHAR(200) NULL,
    col_166 VARCHAR(200) NULL,
    CONSTRAINT pk_tbl_10 PRIMARY KEY (col_13)
)
GO

IF OBJECT_ID(N'dbo.tbl_1', N'U') IS NULL
CREATE TABLE dbo.tbl_1 (
    col_1   INT          NOT NULL,
    col_13  INT          NULL,
    col_50  DATETIME     NULL,
    col_58  INT          NULL,
    col_162 VARCHAR(50)  NULL,
    CONSTRAINT pk_tbl_1 PRIMARY KEY (col_1)
)
GO

IF OBJECT_ID(N'dbo.tbl_3', N'U') IS NULL
CREATE TABLE dbo.tbl_3 (
    col_6   UNIQUEIDENTIFIER NOT NULL DEFAULT NEWSEQUENTIALID(),
    col_7   INT              NULL,
    col_91  VARCHAR(4000)    NULL,
    col_19  VARCHAR(10)      NULL,
    col_20  DATETIME         NULL,
    col_15  VARCHAR(10)      NULL,
    col_18  DATETIME         NULL,
    CONSTRAINT pk_tbl_3 PRIMARY KEY (col_6)
)
GO

IF OBJECT_ID(N'dbo.tbl_2', N'U') IS NULL
CREATE TABLE dbo.tbl_2 (
    col_1   INT              NULL,
    col_4   INT              NULL,
    col_6   UNIQUEIDENTIFIER NULL,
    col_15  VARCHAR(10)      NULL,
    col_18  DATETIME         NULL,
    col_19  VARCHAR(10)      NULL,
    col_20  DATETIME         NULL
)
GO

IF OBJECT_ID(N'dbo.tbl_4', N'U') IS NULL
CREATE TABLE dbo.tbl_4 (
    col_6   UNIQUEIDENTIFIER NULL,
    col_9   VARCHAR(200)     NULL,
    col_10  VARCHAR(200)     NULL,
    col_12  INT              NULL,
    col_13  INT              NULL
)
GO

IF OBJECT_ID(N'dbo.tbl_5', N'U') IS NULL
CREATE TABLE dbo.tbl_5 (
    col_23  INT          NOT NULL,
    col_24  INT          NULL,
    col_26  VARCHAR(200) NULL,
    col_28  INT          NULL,
    col_30  INT          NOT NULL DEFAULT 1,
    CONSTRAINT pk_tbl_5 PRIMARY KEY (col_23)
)
GO

IF OBJECT_ID(N'dbo.tbl_9', N'U') IS NULL
CREATE TABLE dbo.tbl_9 (
    col_30  INT          NOT NULL DEFAULT 1,
    col_43  VARCHAR(MAX) NULL,
    col_61  VARCHAR(200) NULL,
    col_65  INT          NULL DEFAULT -1440,
    col_66  DATETIME     NULL,
    col_67  INT          NULL DEFAULT 1440,
    col_79  VARCHAR(MAX) NULL,
    col_80  VARCHAR(MAX) NULL,
    col_89  VARCHAR(500) NULL,
    col_90  VARCHAR(500) NULL,
    col_96  VARCHAR(MAX) NULL
)
GO

IF OBJECT_ID(N'dbo.tbl_6', N'U') IS NULL
CREATE TABLE dbo.tbl_6 (
    col_31  INT              NOT NULL IDENTITY(1,1),
    col_6   UNIQUEIDENTIFIER NULL,
    col_12  INT              NULL,
    col_13  INT              NULL,
    col_15  VARCHAR(10)      NULL,
    col_18  DATETIME         NULL,
    col_19  VARCHAR(10)      NULL,
    col_20  DATETIME         NULL,
    col_32  INT              NULL DEFAULT 0,
    col_33  DATETIME         NULL,
    col_38  VARCHAR(MAX)     NULL,
    col_42  INT              NULL DEFAULT 0,
    col_62  VARCHAR(50)      NULL,
    col_63  VARCHAR(1000)    NULL,
    col_72  VARCHAR(200)     NULL,
    col_73  VARCHAR(200)     NULL,
    col_74  VARCHAR(MAX)     NULL,
    col_9   VARCHAR(200)     NULL,
    col_10  VARCHAR(200)     NULL,
    col_95  VARCHAR(MAX)     NULL,
    col_96  VARCHAR(MAX)     NULL,
    CONSTRAINT pk_tbl_6 PRIMARY KEY (col_31)
)
GO

IF OBJECT_ID(N'dbo.tbl_7', N'U') IS NULL
CREATE TABLE dbo.tbl_7 (
    col_97  INT          NOT NULL,
    col_31  INT          NULL,
    col_23  INT          NOT NULL,
    col_15  VARCHAR(10)  NULL,
    col_18  DATETIME     NULL,
    col_98  INT          NULL,
    col_99  VARCHAR(MAX) NULL
)
GO

IF OBJECT_ID(N'dbo.tbl_8', N'U') IS NULL
CREATE TABLE dbo.tbl_8 (
    col_93  INT      NOT NULL IDENTITY(1,1),
    col_15  VARCHAR(10)  NULL,
    col_18  DATETIME     NULL,
    col_31  INT          NULL,
    col_39  INT          NULL,
    col_94  DATETIME     NULL,
    CONSTRAINT pk_tbl_8 PRIMARY KEY (col_93)
)
GO

-- ── Helper stored procedures called by the fixture ────────────────────────────

IF OBJECT_ID(N'dbo.proc_13', N'P') IS NULL
    EXEC (N'CREATE PROCEDURE dbo.proc_13 AS SELECT 1')
GO
ALTER PROCEDURE dbo.proc_13
    @where  NVARCHAR(MAX) OUTPUT,
    @col    NVARCHAR(200),
    @op     NVARCHAR(10),
    @param  NVARCHAR(200),
    @val    SQL_VARIANT = NULL
AS
BEGIN
    SET NOCOUNT ON
    IF @val IS NOT NULL
        SET @where = COALESCE(@where + N' AND ', N'') + @col + N' ' + @op + N' ' + @param
END
GO

IF OBJECT_ID(N'dbo.proc_14', N'P') IS NULL
    EXEC (N'CREATE PROCEDURE dbo.proc_14 AS SELECT 1')
GO
ALTER PROCEDURE dbo.proc_14
    @query  NVARCHAR(MAX) OUTPUT,
    @filter NVARCHAR(MAX) = NULL,
    @page   NVARCHAR(MAX) OUTPUT
AS
BEGIN
    SET NOCOUNT ON
    SET @page = NULL
    IF @filter IS NOT NULL
        SET @query = @query + N' ' + @filter
END
GO


-- ============================================================
-- Stub definitions for anonymized custom functions (T-SQL).
-- These make the script self-contained and runnable; bodies are
-- placeholders that preserve the call signatures and return types.
-- ============================================================
GO
IF OBJECT_ID(N'[dbo].[func1]', 'FN') IS NOT NULL DROP FUNCTION [dbo].[func1]
GO
CREATE FUNCTION dbo.func1()
RETURNS datetime
AS
BEGIN
    RETURN DATEADD(day, -3, GETDATE())
END
GO
IF OBJECT_ID(N'[dbo].[func3]', 'FN') IS NOT NULL DROP FUNCTION [dbo].[func3]
GO
CREATE FUNCTION dbo.func3(@key nvarchar(100), @def nvarchar(400))
RETURNS nvarchar(400)
AS
BEGIN
    RETURN @def
END
GO
IF OBJECT_ID(N'[dbo].[func4]', 'FN') IS NOT NULL DROP FUNCTION [dbo].[func4]
GO
CREATE FUNCTION dbo.func4(@payload nvarchar(max), @secret nvarchar(400))
RETURNS nvarchar(max)
AS
BEGIN
    RETURN CONVERT(nvarchar(max), HASHBYTES('SHA2_256', @payload + @secret), 2)
END
GO
IF OBJECT_ID(N'[dbo].[func5]', 'IF') IS NOT NULL DROP FUNCTION [dbo].[func5]
GO
CREATE FUNCTION dbo.func5(@s nvarchar(max), @delim nvarchar(5))
RETURNS TABLE
AS
RETURN (SELECT LTRIM(RTRIM(value)) AS item FROM STRING_SPLIT(@s, @delim))
GO

-- xxxxxx xxxxxx


-- xxxxxx xxxxxx xxxxxx 

IF OBJECT_ID(N'[dbo].[proc_1]', 'P') IS NULL
    EXEC ('CREATE PROCEDURE [dbo].[proc_1] AS SELECT 1')
GO

SET QUOTED_IDENTIFIER ON 
GO
SET ANSI_NULLS ON 
GO

--   <nombre>xxxxxx</nombre>
ALTER PROCEDURE dbo.proc_1
(
    @col_1 int = NULL,
    @col_2 int = NULL
)
AS
BEGIN
    SET NOCOUNT ON

    IF (@col_2 IS NOT NULL)
    BEGIN
        SET ROWCOUNT @col_2
    END

    SELECT TOP(1) *
    FROM (
        SELECT
            DISTINCT
            col_3.col_1,
            col_3.col_4,
            col_5.col_6,
            col_5.col_7,
            col_8.col_9,
            col_8.col_10
        FROM tbl_1 col_11
        INNER JOIN tbl_2 col_3 ON col_3.col_1=col_11.col_1
        INNER JOIN tbl_3 col_5 ON col_5.col_6=col_3.col_6
        LEFT JOIN tbl_4 col_8 ON col_5.col_6=col_8.col_6
        WHERE col_3.col_1=@col_1
        AND (col_8.col_6 IS NULL OR (col_8.col_12=1 AND col_8.col_13=col_11.col_13))
        UNION ALL
        SELECT @col_1 col_1, 0 col_4, null col_6, null col_7, null col_9, null col_10
    ) col_14
    ORDER BY col_4 DESC

END
GO
SET QUOTED_IDENTIFIER OFF 
GO
SET ANSI_NULLS ON 
GO
-- xxx xxxxxx xxxxxx xxxxxx

-- xxxxxx xxxxxx xxxxxx 

IF OBJECT_ID(N'[dbo].[proc_2]', 'P') IS NULL
    EXEC ('CREATE PROCEDURE [dbo].[proc_2] AS SELECT 1')
GO

SET QUOTED_IDENTIFIER ON 
GO
SET ANSI_NULLS ON 
GO

--   <nombre>xxxxxx</nombre>
ALTER PROCEDURE dbo.proc_2
(
    @col_1 int = NULL,
    @col_4 int = NULL,
    @col_15 VARCHAR(10) = NULL,
    @col_2 int = NULL
)
AS
BEGIN
    SET NOCOUNT ON

    DECLARE @func1 DATETIME = dbo.func1()
    DECLARE @col_6 UNIQUEIDENTIFIER = NULL
    DECLARE @col_16 TABLE (col_17 UNIQUEIDENTIFIER)

    IF (@col_2 IS NOT NULL)
    BEGIN
        SET ROWCOUNT @col_2
    END

    IF (@col_1 IS NOT NULL)
    BEGIN

        UPDATE tbl_2
        SET col_4 = @col_4, col_15 = @col_15, col_18 = @func1
        WHERE
            col_1 = @col_1
            AND col_4 <> @col_4

        SET @col_6 = (SELECT MAX(col_6) FROM tbl_2 where col_1=@col_1)

        IF @col_6 IS NULL
        BEGIN

            INSERT INTO tbl_3 (col_19, col_20, col_15, col_18)
            OUTPUT inserted.col_6 INTO @col_16
            SELECT @col_15, @func1, @col_15, @func1
            WHERE
                NOT EXISTS (SELECT null FROM tbl_2 WHERE col_1=@col_1)

            SET @col_6 = (SELECT MAX(col_17) FROM @col_16)

            INSERT INTO tbl_2 (col_1, col_4, col_6, col_19, col_20, col_15, col_18)
            SELECT @col_1, @col_4, @col_6, @col_15, @func1, @col_15, @func1
            WHERE
                NOT EXISTS (SELECT null FROM tbl_2 WHERE col_1=@col_1)

        END

    END

    SELECT LOWER(CONVERT(VARCHAR(36), @col_6)) as col_21

END
GO
SET QUOTED_IDENTIFIER OFF 
GO
SET ANSI_NULLS ON 
GO
-- xxx xxxxxx xxxxxx xxxxxx

-- xxxxxx xxxxxx xxxxxx 

IF OBJECT_ID(N'[dbo].[proc_3]', 'P') IS NULL
    EXEC ('CREATE PROCEDURE [dbo].[proc_3] AS SELECT 1')
GO

SET QUOTED_IDENTIFIER ON 
GO
SET ANSI_NULLS ON 
GO

--   <nombre>xxxxxx</nombre>
ALTER PROCEDURE dbo.proc_3
(
    @col_2 int = NULL
)
AS
BEGIN
    SET NOCOUNT ON

    IF (@col_2 IS NOT NULL)
    BEGIN
        SET ROWCOUNT @col_2
    END

    SELECT
        col_22.col_23,
        col_22.col_24 as col_25,
        col_22.col_26 as col_27,
        cast(null as VARCHAR(MAX)) as value,
        col_22.col_28 as col_29
    FROM
        dbo.tbl_5 col_22
    WHERE
        col_22.col_30 = 1
        ORDER BY col_22.col_28 ASC

END
GO
SET QUOTED_IDENTIFIER OFF 
GO
SET ANSI_NULLS ON 
GO
-- xxx xxxxxx xxxxxx xxxxxx

-- xxxxxx xxxxxx xxxxxx 

IF OBJECT_ID(N'[dbo].[proc_4]', 'P') IS NULL
    EXEC ('CREATE PROCEDURE [dbo].[proc_4] AS SELECT 1')
GO

SET QUOTED_IDENTIFIER ON 
GO
SET ANSI_NULLS ON 
GO

--   <nombre>xxxxxx</nombre>
ALTER PROCEDURE dbo.proc_4
(
    @col_31 int = NULL,
    @col_2 int = NULL
)
AS
BEGIN
    SET NOCOUNT ON

    DECLARE @func1 DATETIME = dbo.func1()

    IF (@col_2 IS NOT NULL)
    BEGIN
        SET ROWCOUNT @col_2
    END

    UPDATE dbo.tbl_6 SET col_32=1, col_18=@func1 WHERE col_31=@col_31 AND col_32=0 AND NOT EXISTS (SELECT null FROM dbo.tbl_7 WHERE col_31=@col_31)
    UPDATE dbo.tbl_6 SET col_33=@func1 WHERE col_31=@col_31 AND NOT EXISTS (SELECT null FROM dbo.tbl_7 WHERE col_31=@col_31)

    SELECT TOP(1) col_32, col_34, col_35, col_36
    FROM
    (
        SELECT
            1 as col_32,
            col_37.col_38 col_34,
            cast(null as varchar(MAX)) col_35,
            COALESCE(
                (
                    SELECT TOP(1) 1
                    FROM dbo.tbl_8
                    WHERE col_31=@col_31
                        AND col_39 = 3 /* xxxxxx xx xx xxxxxx */
                )
            , 0) col_36
        FROM
            dbo.tbl_6 col_37
            INNER JOIN dbo.tbl_8 col_40 ON
                col_40.col_31 IN (
                        SELECT col_31
                        FROM dbo.tbl_6 col_41
                        WHERE
                            col_41.col_6=col_37.col_6
                            AND col_32=1
                            AND col_42=1 /* xxxxxx */
                    )
                AND col_40.col_39=3 /* xxxxxx xx xx xxxxxx */
        WHERE
            col_37.col_31 = @col_31
            AND NOT EXISTS (
                SELECT null
                FROM dbo.tbl_7
                WHERE col_31=@col_31
                /* xx xx xx xxxxxx xx col_161 */
               AND EXISTS (SELECT NULL FROM dbo.tbl_9 WHERE col_30=1 AND col_43 IS NOT NULL)
            )
        UNION ALL
        SELECT
            0 as col_32,
            cast(null as varchar(MAX)) col_34,
            cast(null as varchar(MAX)) col_35,
            0 col_36
    ) col_44
    ORDER BY col_32 DESC
END
GO
SET QUOTED_IDENTIFIER OFF 
GO
SET ANSI_NULLS ON 
GO
-- xxx xxxxxx xxxxxx xxxxxx

-- xxxxxx xxxxxx xxxxxx 

IF OBJECT_ID(N'[dbo].[proc_5]', 'P') IS NULL
    EXEC ('CREATE PROCEDURE [dbo].[proc_5] AS SELECT 1')
GO

SET QUOTED_IDENTIFIER ON 
GO
SET ANSI_NULLS ON 
GO

--   <nombre>xxxxxx</nombre>
ALTER PROCEDURE dbo.proc_5
(
    @col_31 int = NULL,
    @col_2 int = NULL
)
AS
BEGIN
    SET NOCOUNT ON

    IF (@col_2 IS NOT NULL)
    BEGIN
        SET ROWCOUNT @col_2
    END

    SELECT
        col_45.col_46 as col_47,
        col_45.col_48 as col_49,
        col_11.col_50 as col_51,
        col_52.col_46 as col_53,
        COALESCE(
            (
                SELECT TOP(1) 1
                FROM dbo.tbl_8
                WHERE col_31=@col_31
                    AND col_39 = 1 /* xxxxxx xx xx col_6 xx xxxxxx */
                ORDER BY col_31 ASC
            )
            , 0) col_54,
        COALESCE(
            (
                SELECT TOP(1) 1
                FROM dbo.tbl_7
                WHERE col_31=@col_31
                /* xx xx xx xxxxxx xx col_161 */
               AND EXISTS (SELECT NULL FROM dbo.tbl_9 WHERE col_30=1 AND col_43 IS NOT NULL)
               ORDER BY col_31 ASC
            )
            , 0) col_55
    FROM
        dbo.tbl_6 col_37
        INNER JOIN dbo.tbl_2 col_56 ON col_37.col_6=col_56.col_6
        INNER JOIN dbo.tbl_1 col_11 WITH(NOLOCK) ON col_56.col_1=col_11.col_1
        INNER JOIN dbo.tbl_10 col_45 WITH(NOLOCK) ON col_11.col_13=col_45.col_13
        INNER JOIN dbo.tbl_11 col_57 WITH(NOLOCK) ON col_11.col_58=col_57.col_59
        INNER JOIN dbo.tbl_12 col_52 WITH(NOLOCK) ON col_57.col_60=col_52.col_59
    WHERE
        col_37.col_31 = @col_31
END
GO
SET QUOTED_IDENTIFIER OFF 
GO
SET ANSI_NULLS ON 
GO
-- xxx xxxxxx xxxxxx xxxxxx

-- xxxxxx xxxxxx xxxxxx 

IF OBJECT_ID(N'[dbo].[proc_6]', 'P') IS NULL
    EXEC ('CREATE PROCEDURE [dbo].[proc_6] AS SELECT 1')
GO

SET QUOTED_IDENTIFIER ON 
GO
SET ANSI_NULLS ON 
GO

--   <nombre>xxxxxx</nombre>
ALTER PROCEDURE dbo.proc_6
(
    @col_61 VARCHAR(MAX) = NULL, -- xxxxxx xxx xxxxxx xx tbl_9
    @col_6 UNIQUEIDENTIFIER = NULL,
    @col_42 int = 0,
    @col_62 VARCHAR(50) = NULL,
    @col_13 INT = NULL,
    @col_63 VARCHAR(1000) = NULL,
    @col_9 VARCHAR(200) = NULL,
    @col_10 VARCHAR(200) = NULL,
    @col_64 VARCHAR(MAX) = NULL,
    @col_15 VARCHAR(50) = NULL,
    @col_2 int = NULL
)
AS
BEGIN
    SET NOCOUNT ON

    DECLARE @func1 DATETIME = dbo.func1()
    DECLARE @col_65 INT = COALESCE((SELECT TOP(1) col_65 FROM tbl_9 WHERE col_30=1 order by col_66 desc), -1440)
    DECLARE @col_67 INT = COALESCE((SELECT TOP(1) col_67 FROM tbl_9 WHERE col_30=1 order by col_66 desc), 1440)
    DECLARE @col_68 DATETIME
    DECLARE @col_69 DATETIME
    DECLARE @col_70 DATETIME
    DECLARE @col_71 VARCHAR(36) = LOWER(CONVERT(VARCHAR(36), @col_6))
    DECLARE @col_72 VARCHAR(200) = NULL
    DECLARE @col_73 VARCHAR(200) = NULL
    DECLARE @col_74 VARCHAR(MAX) = NULL
    DECLARE @col_32 INT = 0
    DECLARE @col_75 VARCHAR(50) = NULL
    DECLARE @col_17 INT = NULL
    DECLARE @col_12 INT = NULL

    IF (@col_2 IS NOT NULL)
    BEGIN
        SET ROWCOUNT @col_2
    END

    IF ((@col_6 IS NULL) OR (@col_42 IS NULL))
    BEGIN
        RETURN NULL
    END

    SET @col_12 = (SELECT CASE WHEN @col_42 = 1 THEN 2                             -- xxxxxx
                                    WHEN @col_42 = 0 AND @col_13 IS NOT NULL THEN 1   -- col_151
                                    ELSE 0 END)                                            -- xxxxxx

    -- xx xx xx xxxxxx
    IF @col_12 = 2
    BEGIN

        DELETE FROM tbl_6 WHERE col_6=@col_6 AND col_42=1 AND col_62=@col_62

        SELECT
            @col_72 = col_76.col_46,
            @col_73 = LOWER(COALESCE(col_76.col_77, @col_62 + '@' + @col_61))
            FROM tbl_13 col_76
        WHERE
            col_76.col_62 = @col_62
    END

    -- xx xx xx xxxxxx
    IF @col_12 = 1
    BEGIN

        DELETE FROM tbl_6 WHERE col_6=@col_6 AND col_42=0 AND col_13=@col_13

        SELECT
            @col_72 = col_45.col_46,
            @col_73 = LOWER(COALESCE(col_45.col_73, CONVERT(VARCHAR(50), col_45.col_13) + '@' + @col_61))
        FROM tbl_2 col_3
            INNER JOIN tbl_1 col_11 ON col_11.col_1=col_3.col_1
            INNER JOIN tbl_10 col_45 ON col_45.col_13=col_11.col_13
        WHERE
            col_3.col_6 = @col_6
    END

    -- xx xx xx xxxxxx
    IF @col_12 = 0
    BEGIN

        DELETE FROM tbl_6 WHERE col_6=@col_6 AND col_42=0 AND col_62=@col_62 AND col_13 IS NULL

        SELECT
            @col_72 = @col_62,
            @col_73 = LOWER(@col_62 + '@' + @col_61)

    END

    SELECT
        @col_68 = col_11.col_50
    FROM tbl_2 col_3
        INNER JOIN tbl_1 col_11 ON col_11.col_1=col_3.col_1
    WHERE
        col_3.col_6 = @col_6

    -- xxxxxx xx xxxxxx xxx xxxxxx
    SET @col_69 = DATEADD(minute, @col_65, @col_68)
    SET @col_70 = DATEADD(minute, @col_67, @col_68)

    INSERT INTO tbl_6 (col_12, col_62, col_13, col_19, col_20, col_15, col_18, col_6, col_72, col_73, col_63, col_42, col_74, col_32, col_9, col_10)
    VALUES (@col_12, @col_62, @col_13, @col_15, @func1, @col_15, @func1, @col_6, @col_72, @col_73, @col_63, @col_42, '-', @col_32, @col_9, @col_10)

    -- xx xxxxxx xxx xxxxxx xxxx xx xxxxxx xxxxx xxx xxxxxx xx xx xxxxx
    SET @col_17 = SCOPE_IDENTITY()
    SET @col_75 = CONVERT(VARCHAR(20), @col_17)

    IF (@col_64 IS NULL)
    BEGIN
        SET @col_74 = dbo.func2(@col_61, @col_69, @col_70, @col_75, @col_71, @col_72, @col_73, @col_63, @col_42)
    END
    ELSE
    BEGIN
        SET @col_74 = @col_64
    END

    IF (COALESCE(@col_74, 'xxxxxxx-xxxx') = 'xxxxxxx-xxxx')
    BEGIN
        DELETE FROM tbl_6 WHERE col_31 = @col_17
    END
    ELSE
    BEGIN
        UPDATE tbl_6 SET col_74=@col_74 WHERE col_31 = @col_17
    END

    SELECT col_31, col_74 FROM tbl_6 WHERE col_31 = @col_17

END
GO
SET QUOTED_IDENTIFIER OFF 
GO
SET ANSI_NULLS ON 
GO
-- xxx xxxxxx xxxxxx xxxxxx

-- xxxxxx xxxxxx xxxxx 

IF OBJECT_ID(N'[dbo].[func2]') IS NULL
    EXEC('CREATE FUNCTION [dbo].[func2] () RETURNS VARCHAR AS BEGIN RETURN NULL END')
GO

SET QUOTED_IDENTIFIER ON 
GO
SET ANSI_NULLS ON 
GO

--   <nombre>xxxxx</nombre>
ALTER FUNCTION dbo.func2
(
    @col_61 VARCHAR(MAX) = NULL, -- xxxxxx xxx xxxxxx xx tbl_9
    @col_69  DATETIME = NULL,
    @col_70  DATETIME = NULL,
    @col_62 VARCHAR(50) = NULL,
    @col_6 VARCHAR(1000) = NULL,
    @col_72 VARCHAR(200) = NULL,
    @col_73 VARCHAR(200) = NULL,
    @col_63 VARCHAR(1000) = NULL,
    @col_42 int = NULL
)
RETURNS VARCHAR(4000)
AS
BEGIN

    -- xxxxxx

    DECLARE @func1 DATETIME

    DECLARE @col_79 VARCHAR(MAX)
    DECLARE @col_80 VARCHAR(MAX)
    DECLARE @mod VARCHAR(10)
    DECLARE @col_74 VARCHAR(MAX)
    DECLARE @col_81 VARCHAR(1000)
    DECLARE @col_82 DATETIME

    DECLARE @col_83 VARCHAR(500)   -- col_89
    DECLARE @col_84 VARCHAR(500)   -- col_90
    DECLARE @col_75 VARCHAR(50)    -- xxxxxx
    DECLARE @col_85 BIGINT         -- xxxxxx xx
    DECLARE @col_86 BIGINT         -- xxx xxxxxx
    DECLARE @col_87 BIGINT         -- xxxxxx xxxx
    DECLARE @col_88 VARCHAR(50)    -- col_88

    SET @func1 = dbo.func1()

    SELECT @col_79=col_79, @col_83=col_89, @col_84=col_90, @col_80=col_80 FROM tbl_9 WHERE col_61=@col_61 AND col_30=1

    IF (@col_79 IS NULL OR @col_62 IS NULL OR @col_69 IS NULL OR @col_70 IS NULL OR @col_6 IS NULL)
    BEGIN
        RETURN 'xxxxxxx-xxxx'
    END

    set @col_75 = 'xxxx.xxxxx'
    SET @mod = CASE WHEN COALESCE(@col_42, 0) = 1 THEN 'xxxx' ELSE 'xxxxx' END
    SET @col_88 = REPLACE(COALESCE(@col_62, ''), '"', '')
    SET @col_81 = COALESCE(dbo.func3('xxxxxxxxxxx', '/'), '/')
    IF (SUBSTRING(@col_81, LEN(@col_81), 1) <> '/')
    BEGIN
        SET @col_81 = @col_81 + '/'
    END
    SET @col_80 = REPLACE(@col_80, '~/', @col_81)
    SET @col_63 = REPLACE(COALESCE(@col_63, REPLACE(@col_80, '{x}', @col_75)), '"', '')
    SET @col_72 = REPLACE(COALESCE(@col_72, @col_75), '"', '')
    SET @col_73 = REPLACE(COALESCE(@col_73, @col_75 + '@' + @col_61), '"', '')
    SET @col_82 = CONVERT(DATETIME, 'xxxx-xx-xx xx:xx:xx', 120)
    SET @col_85 = DATEDIFF(second, @col_82, @func1)
    SET @col_86 = DATEDIFF(second, @col_82, COALESCE(@col_69, @func1))
    SET @col_87 = DATEDIFF(second, @col_82, COALESCE(@col_70, @func1 + 1))

    SET @col_74='{
  "xxxxxxx": {
    "xxxx": {
      "xxxxxx": "$xxxxxx$",
      "xxxx": "$xxxx$",
      "xxxxx": "$xxxxx$"
    }
  },
  "xxx": $xxx$,
  "xxx": $xxx$,
  "xxx": $xxx$,
  "xxx": "$xxx$",
  "xxx": "$xxx$",
  "xxxxxxxxx": "$xxxxxxxxx$",
  "xxx": "$xxx$",
  "xxxx": "$xxxx$",
  "xxxxxxxxx": $xxxxxxxxx$
}'

    SET @col_74 = REPLACE(@col_74, '$xxxxxx$', @col_63)
    SET @col_74 = REPLACE(@col_74, '$xxxx$', @col_72)
    SET @col_74 = REPLACE(@col_74, '$xxxxx$', @col_73)
    SET @col_74 = REPLACE(@col_74, '$xxx$', CONVERT(VARCHAR(50), @col_85))
    SET @col_74 = REPLACE(@col_74, '$xxx$', CONVERT(VARCHAR(50), @col_86))
    SET @col_74 = REPLACE(@col_74, '$xxx$', CONVERT(VARCHAR(50), @col_87))
    SET @col_74 = REPLACE(@col_74, '$xxx$', @col_84)
    SET @col_74 = REPLACE(@col_74, '$xxx$', @col_83)
    SET @col_74 = REPLACE(@col_74, '$xxxxxxxxx$', @col_88)
    SET @col_74 = REPLACE(@col_74, '$xxx$', @col_75)
    SET @col_74 = REPLACE(@col_74, '$xxxx$', @col_6)
    SET @col_74 = REPLACE(@col_74, '$xxxxxxxxx$', @mod)

    -- xxxxxx xx xxxxxx xxx xxxx
    SET @col_74 = REPLACE(@col_74, CHAR(13), '')
    SET @col_74 = REPLACE(@col_74, CHAR(10), '')
    SET @col_74 = REPLACE(@col_74, '    ', ' ')
    SET @col_74 = REPLACE(@col_74, '  ', ' ')
    SET @col_74 = REPLACE(@col_74, '  ', ' ')
    SET @col_74 = REPLACE(@col_74, '{ ', '{')
    SET @col_74 = REPLACE(@col_74, '} ', '}')
    SET @col_74 = REPLACE(@col_74, ': ', ':')
    SET @col_74 = REPLACE(@col_74, ', "', ',"')
    SET @col_74 = REPLACE(@col_74, ' "', '"')
    SET @col_74 = REPLACE(@col_74, '" ', '"')

    return dbo.func4(@col_74, @col_79)

END
GO
SET QUOTED_IDENTIFIER OFF 
GO
SET ANSI_NULLS ON 
GO
-- xxx xxxxxx xxxxxx xxxxx

-- xxxxxx xxxxxx xxxxxx 

IF OBJECT_ID(N'[dbo].[proc_7]', 'P') IS NULL
    EXEC ('CREATE PROCEDURE [dbo].[proc_7] AS SELECT 1')
GO

SET QUOTED_IDENTIFIER ON 
GO
SET ANSI_NULLS ON 
GO

--    <nombre>xxxxxx</nombre>
ALTER PROCEDURE dbo.proc_7
(
    @col_6 uniqueidentifier = NULL OUTPUT,
    @col_7 int = NULL,
    @col_91 varchar(4000) = NULL,
    @col_19 varchar(10) = NULL,
    @col_20 datetime = NULL,
    @col_15 varchar(10) = NULL,
    @col_18 datetime = NULL
)
AS
BEGIN
    SET NOCOUNT ON

    DECLARE @col_92 TABLE (col_17 UNIQUEIDENTIFIER)

    INSERT INTO tbl_3 (col_7, col_91, col_19, col_20, col_15, col_18)
    OUTPUT inserted.col_6 INTO @col_92
    VALUES (@col_7, @col_91, @col_19, @col_20, @col_15, @col_18)

    SET @col_6 = (SELECT MAX(col_17) FROM @col_92)

END
GO
SET QUOTED_IDENTIFIER OFF 
GO
SET ANSI_NULLS ON 
GO
-- xxx xxxxxx xxxxxx xxxxxx

-- xxxxxx xxxxxx xxxxxx 

IF OBJECT_ID(N'[dbo].[proc_8]', 'P') IS NULL
    EXEC ('CREATE PROCEDURE [dbo].[proc_8] AS SELECT 1')
GO

SET QUOTED_IDENTIFIER ON 
GO
SET ANSI_NULLS ON 
GO

--    <nombre>xxxxxx</nombre>
ALTER PROCEDURE dbo.proc_8
(
    @col_93 int = NULL OUTPUT,
    @col_15 varchar(10) = NULL,
    @col_18 datetime = NULL,
    @col_31 int = NULL,
    @col_39 int = NULL,
    @col_94 datetime = NULL
)
AS
BEGIN
    SET NOCOUNT ON

    DECLARE @col_92 TABLE (col_17 INTEGER)

    INSERT INTO tbl_8 (col_15, col_18, col_31, col_39, col_94)
    OUTPUT inserted.col_93 INTO @col_92
    VALUES (@col_15, @col_18, @col_31, @col_39, @col_94)

    SET @col_93 = (SELECT MAX(col_17) FROM @col_92)

END
GO
SET QUOTED_IDENTIFIER OFF 
GO
SET ANSI_NULLS ON 
GO
-- xxx xxxxxx xxxxxx xxxxxx

-- xxxxxx xxxxxx xxxxxx 

IF OBJECT_ID(N'[dbo].[proc_9]', 'P') IS NULL
    EXEC ('CREATE PROCEDURE [dbo].[proc_9] AS SELECT 1')
GO

SET QUOTED_IDENTIFIER ON 
GO
SET ANSI_NULLS ON 
GO

--    <nombre>xxxxxx</nombre>
ALTER PROCEDURE dbo.proc_9
(
    @col_31 int = NULL OUTPUT,
    @col_6 uniqueidentifier = NULL,
    @col_32 int = NULL,
    @col_33 datetime = NULL,
    @col_12 int = NULL,
    @col_42 int = NULL,
    @col_62 varchar(10) = NULL,
    @col_13 int = NULL,
    @col_9 varchar(200) = NULL,
    @col_10 varchar(200) = NULL,
    @col_74 varchar(MAX) = NULL,
    @col_38 varchar(MAX) = NULL,
    @col_95 varchar(MAX) = NULL,
    @col_96 varchar(MAX) = NULL,
    @col_72 varchar(200) = NULL,
    @col_73 varchar(200) = NULL,
    @col_63 varchar(1000) = NULL,
    @col_19 varchar(10) = NULL,
    @col_20 datetime = NULL,
    @col_15 varchar(10) = NULL,
    @col_18 datetime = NULL
)
AS
BEGIN
    SET NOCOUNT ON

    DECLARE @col_92 TABLE (col_17 INTEGER)

    INSERT INTO tbl_6 (col_6, col_32, col_33, col_12, col_42, col_62, col_13, col_9, col_10, col_74, col_38, col_95, col_96, col_72, col_73, col_63, col_19, col_20, col_15, col_18)
    OUTPUT inserted.col_31 INTO @col_92
    VALUES (@col_6, @col_32, @col_33, @col_12, @col_42, @col_62, @col_13, @col_9, @col_10, @col_74, @col_38, @col_95, @col_96, @col_72, @col_73, @col_63, @col_19, @col_20, @col_15, @col_18)

    SET @col_31 = (SELECT MAX(col_17) FROM @col_92)

END
GO
SET QUOTED_IDENTIFIER OFF 
GO
SET ANSI_NULLS ON 
GO
-- xxx xxxxxx xxxxxx xxxxxx

-- xxxxxx xxxxxx xxxxxx 

IF OBJECT_ID(N'[dbo].[proc_10]', 'P') IS NULL
    EXEC ('CREATE PROCEDURE [dbo].[proc_10] AS SELECT 1')
GO

SET QUOTED_IDENTIFIER ON 
GO
SET ANSI_NULLS ON 
GO

--    <nombre>xxxxxx</nombre>
ALTER PROCEDURE dbo.proc_10
(
    @col_97 int = NULL,
    @col_31 int = NULL,
    @col_23 int = NULL,
    @col_15 varchar(10) = NULL,
    @col_18 datetime = NULL,
    @col_98 int = NULL,
    @col_99 varchar(MAX) = NULL,
    @col_100 int = NULL,
    @col_101 int = NULL,
    @col_102 int = NULL,
    @col_103 varchar(10) = NULL,
    @col_104 datetime = NULL,
    @col_105 int = NULL,
    @col_106 varchar(MAX) = NULL
)
AS
BEGIN
    SET NOCOUNT ON

    UPDATE tbl_7
    SET col_15 = @col_15,
        col_18 = @col_18,
        col_98 = @col_98,
        col_99 = @col_99
    WHERE ( col_97 = @col_100 )
     AND ( col_31 = @col_101 )
     AND ( col_23 = @col_102 )
     AND ( ( col_15 = @col_103 ) OR ( col_15 IS NULL AND @col_103 IS NULL ) )
     AND ( ( col_18 = @col_104 ) OR ( col_18 IS NULL AND @col_104 IS NULL ) )
     AND ( ( col_98 = @col_105 ) OR ( col_98 IS NULL AND @col_105 IS NULL ) )
     AND ( ( col_99 = @col_106 ) OR ( col_99 IS NULL AND @col_106 IS NULL ) )

    -- xx xx xx xxxxxx xx xxxxxx xxxxxx xxxxx
    IF @@ROWCOUNT <> 1
    BEGIN
        RAISERROR (16947, 16, 1)
    END

    -- xxxxxx xx xxxxxx xxxx xx xxxxx xxxxxx
    IF @col_97 IS NULL OR @col_31 IS NULL OR @col_23 IS NULL
    BEGIN
        RAISERROR (40302, 16, 1)
    END

END
GO
SET QUOTED_IDENTIFIER OFF 
GO
SET ANSI_NULLS ON 
GO
-- xxx xxxxxx xxxxxx xxxxxx

-- xxxxxx xxxxxx xxxxxx 

IF OBJECT_ID(N'[dbo].[proc_11]', 'P') IS NULL
    EXEC ('CREATE PROCEDURE [dbo].[proc_11] AS SELECT 1')
GO

SET QUOTED_IDENTIFIER ON 
GO
SET ANSI_NULLS ON 
GO

--    <nombre>xxxxxx</nombre>
ALTER PROCEDURE dbo.proc_11
(
    @col_97 int = NULL,
    @col_31 int = NULL,
    @col_23 int = NULL,
    @col_15 varchar(10) = NULL,
    @col_18 datetime = NULL,
    @col_98 int = NULL,
    @col_99 varchar(MAX) = NULL
)
AS
BEGIN
    SET NOCOUNT ON

    INSERT INTO tbl_7 (col_97, col_31, col_23, col_15, col_18, col_98, col_99)
    VALUES (@col_97, @col_31, @col_23, @col_15, @col_18, @col_98, @col_99)

END
GO
SET QUOTED_IDENTIFIER OFF 
GO
SET ANSI_NULLS ON 
GO
-- xxx xxxxxx xxxxxx xxxxxx

-- xxxxxx xxxxxx xxxxxx 

IF OBJECT_ID(N'[dbo].[proc_12]', 'P') IS NULL
    EXEC ('CREATE PROCEDURE [dbo].[proc_12] AS SELECT 1')
GO

SET QUOTED_IDENTIFIER ON 
GO
SET ANSI_NULLS ON 
GO

--    <nombre>xxxxxx</nombre>
ALTER PROCEDURE dbo.proc_12
(
    @col_97 int = NULL,
    @col_31 int = NULL,
    @col_23 int = NULL,
    @col_15 varchar(10) = NULL,
    @col_18 datetime = NULL,
    @col_98 int = NULL,
    @col_99 varchar(MAX) = NULL,
    @col_107 varchar(MAX) = NULL,
    @col_2 int = NULL
)
AS
BEGIN
    SET NOCOUNT ON

    DECLARE @col_108 VARCHAR(MAX), @col_109 NVARCHAR(MAX), @col_110 NVARCHAR(MAX)

    IF (@col_2 IS NOT NULL)
    BEGIN
        SET ROWCOUNT @col_2
    END

    IF @col_97 IS NOT NULL AND @col_31 IS NOT NULL AND @col_23 IS NOT NULL AND @col_107 IS NULL
    BEGIN
        SELECT col_97, col_31, col_23, col_15, col_18, col_98, col_99
        FROM tbl_7
        WHERE ( @col_97 = col_97 )
            AND ( @col_31 = col_31 )
            AND ( @col_23 = col_23 ) AND
        ( col_97 = @col_97 OR @col_97 IS NULL )
     AND ( col_31 = @col_31 OR @col_31 IS NULL )
     AND ( col_23 = @col_23 OR @col_23 IS NULL )
     AND ( col_15 = @col_15 OR @col_15 IS NULL )
     AND ( col_18 = @col_18 OR @col_18 IS NULL )
     AND ( col_98 = @col_98 OR @col_98 IS NULL )
     AND ( col_99 = @col_99 OR @col_99 IS NULL );
    END
    ELSE
    BEGIN
        SET @col_109 = '
            SELECT col_97, col_31, col_23, col_15, col_18, col_98, col_99
            FROM tbl_7'

        EXEC proc_13 @col_110 OUTPUT, 'xxxxxxxxxxxxxxxx', '=', '@xxxxxxxxxxxxxxxx', @col_97
        EXEC proc_13 @col_110 OUTPUT, 'xxxxxxxxxxxxx', '=', '@xxxxxxxxxxxxx', @col_31
        EXEC proc_13 @col_110 OUTPUT, 'xxxxxxxxxxxxxxx', '=', '@xxxxxxxxxxxxxxx', @col_23
        EXEC proc_13 @col_110 OUTPUT, 'xxxxxxxxxx', '=', '@xxxxxxxxxx', @col_15
        EXEC proc_13 @col_110 OUTPUT, 'xxxxxxxx', '=', '@xxxxxxxx', @col_18
        EXEC proc_13 @col_110 OUTPUT, 'xxxxx', '=', '@xxxxx', @col_98
        EXEC proc_13 @col_110 OUTPUT, 'xxxxxxxxx', '=', '@xxxxxxxxx', @col_99

        if @col_110 IS NOT NULL
        begin
            set @col_109 = @col_109 + ' WHERE ' + @col_110
        end

        exec proc_14 @col_109 output, @col_107, @col_108 output

        exec sp_executesql @col_109, N'
            @xxxxxxxxxxxxxxxx xxx,
            @xxxxxxxxxxxxx xxx,
            @xxxxxxxxxxxxxxx xxx,
            @xxxxxxxxxx xxxxxxx(xx),
            @xxxxxxxx xxxxxxxx,
            @xxxxx xxx,
            @xxxxxxxxx xxxxxxx(xxx),
            @xxxxxxxx_xxxxxx xxxxxxx(xxx)',
            @col_97, @col_31, @col_23, @col_15, @col_18, @col_98, @col_99,
            @col_108
    END

END
GO
SET QUOTED_IDENTIFIER OFF 
GO
SET ANSI_NULLS ON 
GO
-- xxx xxxxxx xxxxxx xxxxxx

-- xxxxxx xxxxxx xxxxxx 

IF OBJECT_ID(N'[dbo].[proc_15]', 'P') IS NULL
    EXEC ('CREATE PROCEDURE [dbo].[proc_15] AS SELECT 1')
GO

SET QUOTED_IDENTIFIER ON 
GO
SET ANSI_NULLS ON 
GO

--    <nombre>xxxxxx</nombre>
ALTER PROCEDURE dbo.proc_15
(
    @col_100 int = NULL,
    @col_101 int = NULL,
    @col_102 int = NULL,
    @col_103 varchar(10) = NULL,
    @col_104 datetime = NULL,
    @col_105 int = NULL,
    @col_106 varchar(MAX) = NULL
)
AS
BEGIN
    SET NOCOUNT ON

    DELETE FROM tbl_7
    WHERE ( col_97 = @col_100 )
     AND ( col_31 = @col_101 )
     AND ( col_23 = @col_102 )
     AND ( ( col_15 = @col_103 ) OR ( col_15 IS NULL AND @col_103 IS NULL ) )
     AND ( ( col_18 = @col_104 ) OR ( col_18 IS NULL AND @col_104 IS NULL ) )
     AND ( ( col_98 = @col_105 ) OR ( col_98 IS NULL AND @col_105 IS NULL ) )
     AND ( ( col_99 = @col_106 ) OR ( col_99 IS NULL AND @col_106 IS NULL ) )

    -- xx xx xx xxxxxx xx xxxxxx xxxxxx xxxxx
    IF @@ROWCOUNT <> 1
    BEGIN
        RAISERROR (16947, 16, 1)
    END

END
GO
SET QUOTED_IDENTIFIER OFF 
GO
SET ANSI_NULLS ON 
GO
-- xxx xxxxxx xxxxxx xxxxxx

-- xxxxxx xxxxxx xxxxxx 

IF OBJECT_ID(N'[dbo].[proc_16]', 'P') IS NULL
    EXEC ('CREATE PROCEDURE [dbo].[proc_16] AS SELECT 1')
GO

SET QUOTED_IDENTIFIER ON 
GO
SET ANSI_NULLS ON 
GO

--    <nombre>xxxxxx</nombre>
ALTER PROCEDURE dbo.proc_16
(
    @col_93 int = NULL,
    @col_15 varchar(10) = NULL,
    @col_18 datetime = NULL,
    @col_31 int = NULL,
    @col_39 int = NULL,
    @col_94 datetime = NULL,
    @col_112 int = NULL,
    @col_103 varchar(10) = NULL,
    @col_104 datetime = NULL,
    @col_101 int = NULL,
    @col_113 int = NULL,
    @col_114 datetime = NULL
)
AS
BEGIN
    SET NOCOUNT ON

    UPDATE tbl_8
    SET col_15 = @col_15,
        col_18 = @col_18,
        col_31 = @col_31,
        col_39 = @col_39,
        col_94 = @col_94
    WHERE ( col_93 = @col_112 )
     AND ( ( col_15 = @col_103 ) OR ( col_15 IS NULL AND @col_103 IS NULL ) )
     AND ( ( col_18 = @col_104 ) OR ( col_18 IS NULL AND @col_104 IS NULL ) )
     AND ( ( col_31 = @col_101 ) OR ( col_31 IS NULL AND @col_101 IS NULL ) )
     AND ( ( col_39 = @col_113 ) OR ( col_39 IS NULL AND @col_113 IS NULL ) )
     AND ( ( col_94 = @col_114 ) OR ( col_94 IS NULL AND @col_114 IS NULL ) )

    -- xx xx xx xxxxxx xx xxxxxx xxxxxx xxxxx
    IF @@ROWCOUNT <> 1
    BEGIN
        RAISERROR (16947, 16, 1)
    END

    -- xxxxxx xx xxxxxx xxxx xx xxxxx xxxxxx
    IF @col_93 IS NULL
    BEGIN
        RAISERROR (40302, 16, 1)
    END

END
GO
SET QUOTED_IDENTIFIER OFF 
GO
SET ANSI_NULLS ON 
GO
-- xxx xxxxxx xxxxxx xxxxxx

-- xxxxxx xxxxxx xxxxxx 

IF OBJECT_ID(N'[dbo].[proc_17]', 'P') IS NULL
    EXEC ('CREATE PROCEDURE [dbo].[proc_17] AS SELECT 1')
GO

SET QUOTED_IDENTIFIER ON 
GO
SET ANSI_NULLS ON 
GO

--    <nombre>xxxxxx</nombre>
ALTER PROCEDURE dbo.proc_17
(
    @col_93 int = NULL,
    @col_15 varchar(10) = NULL,
    @col_18 datetime = NULL,
    @col_31 int = NULL,
    @col_39 int = NULL,
    @col_94 datetime = NULL,
    @col_107 varchar(MAX) = NULL,
    @col_2 int = NULL
)
AS
BEGIN
    SET NOCOUNT ON

    DECLARE @col_108 VARCHAR(MAX), @col_109 NVARCHAR(MAX), @col_110 NVARCHAR(MAX)

    IF (@col_2 IS NOT NULL)
    BEGIN
        SET ROWCOUNT @col_2
    END

    IF @col_93 IS NOT NULL AND @col_107 IS NULL
    BEGIN
        SELECT col_93, col_15, col_18, col_31, col_39, col_94
        FROM tbl_8
        WHERE ( @col_93 = col_93 ) AND
        ( col_93 = @col_93 OR @col_93 IS NULL )
     AND ( col_15 = @col_15 OR @col_15 IS NULL )
     AND ( col_18 = @col_18 OR @col_18 IS NULL )
     AND ( col_31 = @col_31 OR @col_31 IS NULL )
     AND ( col_39 = @col_39 OR @col_39 IS NULL )
     AND ( col_94 = @col_94 OR @col_94 IS NULL );
    END
    ELSE
    BEGIN
        SET @col_109 = '
            SELECT col_93, col_15, col_18, col_31, col_39, col_94
            FROM tbl_8'

        EXEC proc_13 @col_110 OUTPUT, 'xxxxxxxxxxxxx', '=', '@xxxxxxxxxxxxx', @col_93
        EXEC proc_13 @col_110 OUTPUT, 'xxxxxxxxxx', '=', '@xxxxxxxxxx', @col_15
        EXEC proc_13 @col_110 OUTPUT, 'xxxxxxxx', '=', '@xxxxxxxx', @col_18
        EXEC proc_13 @col_110 OUTPUT, 'xxxxxxxxxxxxx', '=', '@xxxxxxxxxxxxx', @col_31
        EXEC proc_13 @col_110 OUTPUT, 'xxxxxxxxxxxx', '=', '@xxxxxxxxxxxx', @col_39
        EXEC proc_13 @col_110 OUTPUT, 'xxxxx', '=', '@xxxxx', @col_94

        if @col_110 IS NOT NULL
        begin
            set @col_109 = @col_109 + ' WHERE ' + @col_110
        end

        exec proc_14 @col_109 output, @col_107, @col_108 output

        exec sp_executesql @col_109, N'
            @xxxxxxxxxxxxx xxx,
            @xxxxxxxxxx xxxxxxx(xx),
            @xxxxxxxx xxxxxxxx,
            @xxxxxxxxxxxxx xxx,
            @xxxxxxxxxxxx xxx,
            @xxxxx xxxxxxxx,
            @xxxxxxxx_xxxxxx xxxxxxx(xxx)',
            @col_93, @col_15, @col_18, @col_31, @col_39, @col_94,
            @col_108
    END

END
GO
SET QUOTED_IDENTIFIER OFF 
GO
SET ANSI_NULLS ON 
GO
-- xxx xxxxxx xxxxxx xxxxxx

-- xxxxxx xxxxxx xxxxxx 

IF OBJECT_ID(N'[dbo].[proc_18]', 'P') IS NULL
    EXEC ('CREATE PROCEDURE [dbo].[proc_18] AS SELECT 1')
GO

SET QUOTED_IDENTIFIER ON 
GO
SET ANSI_NULLS ON 
GO

--    <nombre>xxxxxx</nombre>
ALTER PROCEDURE dbo.proc_18
(
    @col_112 int = NULL,
    @col_103 varchar(10) = NULL,
    @col_104 datetime = NULL,
    @col_101 int = NULL,
    @col_113 int = NULL,
    @col_114 datetime = NULL
)
AS
BEGIN
    SET NOCOUNT ON

    DELETE FROM tbl_8
    WHERE ( col_93 = @col_112 )
     AND ( ( col_15 = @col_103 ) OR ( col_15 IS NULL AND @col_103 IS NULL ) )
     AND ( ( col_18 = @col_104 ) OR ( col_18 IS NULL AND @col_104 IS NULL ) )
     AND ( ( col_31 = @col_101 ) OR ( col_31 IS NULL AND @col_101 IS NULL ) )
     AND ( ( col_39 = @col_113 ) OR ( col_39 IS NULL AND @col_113 IS NULL ) )
     AND ( ( col_94 = @col_114 ) OR ( col_94 IS NULL AND @col_114 IS NULL ) )

    -- xx xx xx xxxxxx xx xxxxxx xxxxxx xxxxx
    IF @@ROWCOUNT <> 1
    BEGIN
        RAISERROR (16947, 16, 1)
    END

END
GO
SET QUOTED_IDENTIFIER OFF 
GO
SET ANSI_NULLS ON 
GO
-- xxx xxxxxx xxxxxx xxxxxx

-- xxxxxx xxxxxx xxxxxx 

IF OBJECT_ID(N'[dbo].[proc_19]', 'P') IS NULL
    EXEC ('CREATE PROCEDURE [dbo].[proc_19] AS SELECT 1')
GO

SET QUOTED_IDENTIFIER ON 
GO
SET ANSI_NULLS ON 
GO

--    <nombre>xxxxxx</nombre>
ALTER PROCEDURE dbo.proc_19
(
    @col_31 int = NULL,
    @col_6 uniqueidentifier = NULL,
    @col_32 int = NULL,
    @col_33 datetime = NULL,
    @col_12 int = NULL,
    @col_42 int = NULL,
    @col_62 varchar(10) = NULL,
    @col_13 int = NULL,
    @col_9 varchar(200) = NULL,
    @col_10 varchar(200) = NULL,
    @col_74 varchar(MAX) = NULL,
    @col_38 varchar(MAX) = NULL,
    @col_95 varchar(MAX) = NULL,
    @col_96 varchar(MAX) = NULL,
    @col_72 varchar(200) = NULL,
    @col_73 varchar(200) = NULL,
    @col_63 varchar(1000) = NULL,
    @col_19 varchar(10) = NULL,
    @col_20 datetime = NULL,
    @col_15 varchar(10) = NULL,
    @col_18 datetime = NULL,
    @col_101 int = NULL,
    @col_115 uniqueidentifier = NULL,
    @col_116 int = NULL,
    @col_117 datetime = NULL,
    @col_118 int = NULL,
    @col_119 int = NULL,
    @col_120 varchar(10) = NULL,
    @col_121 int = NULL,
    @col_122 varchar(200) = NULL,
    @col_123 varchar(200) = NULL,
    @col_124 varchar(MAX) = NULL,
    @col_125 varchar(MAX) = NULL,
    @col_126 varchar(MAX) = NULL,
    @col_127 varchar(MAX) = NULL,
    @col_128 varchar(200) = NULL,
    @col_129 varchar(200) = NULL,
    @col_130 varchar(1000) = NULL,
    @col_131 varchar(10) = NULL,
    @col_132 datetime = NULL,
    @col_103 varchar(10) = NULL,
    @col_104 datetime = NULL
)
AS
BEGIN
    SET NOCOUNT ON

    UPDATE tbl_6
    SET col_6 = @col_6,
        col_32 = @col_32,
        col_33 = @col_33,
        col_12 = @col_12,
        col_42 = @col_42,
        col_62 = @col_62,
        col_13 = @col_13,
        col_9 = @col_9,
        col_10 = @col_10,
        col_74 = @col_74,
        col_38 = @col_38,
        col_95 = @col_95,
        col_96 = @col_96,
        col_72 = @col_72,
        col_73 = @col_73,
        col_63 = @col_63,
        col_19 = @col_19,
        col_20 = @col_20,
        col_15 = @col_15,
        col_18 = @col_18
    WHERE ( col_31 = @col_101 )
     AND ( ( col_6 = @col_115 ) OR ( col_6 IS NULL AND @col_115 IS NULL ) )
     AND ( ( col_32 = @col_116 ) OR ( col_32 IS NULL AND @col_116 IS NULL ) )
     AND ( ( col_33 = @col_117 ) OR ( col_33 IS NULL AND @col_117 IS NULL ) )
     AND ( ( col_12 = @col_118 ) OR ( col_12 IS NULL AND @col_118 IS NULL ) )
     AND ( ( col_42 = @col_119 ) OR ( col_42 IS NULL AND @col_119 IS NULL ) )
     AND ( ( col_62 = @col_120 ) OR ( col_62 IS NULL AND @col_120 IS NULL ) )
     AND ( ( col_13 = @col_121 ) OR ( col_13 IS NULL AND @col_121 IS NULL ) )
     AND ( ( col_9 = @col_122 ) OR ( col_9 IS NULL AND @col_122 IS NULL ) )
     AND ( ( col_10 = @col_123 ) OR ( col_10 IS NULL AND @col_123 IS NULL ) )
     AND ( ( col_74 = @col_124 ) OR ( col_74 IS NULL AND @col_124 IS NULL ) )
     AND ( ( col_38 = @col_125 ) OR ( col_38 IS NULL AND @col_125 IS NULL ) )
     AND ( ( col_95 = @col_126 ) OR ( col_95 IS NULL AND @col_126 IS NULL ) )
     AND ( ( col_96 = @col_127 ) OR ( col_96 IS NULL AND @col_127 IS NULL ) )
     AND ( ( col_72 = @col_128 ) OR ( col_72 IS NULL AND @col_128 IS NULL ) )
     AND ( ( col_73 = @col_129 ) OR ( col_73 IS NULL AND @col_129 IS NULL ) )
     AND ( ( col_63 = @col_130 ) OR ( col_63 IS NULL AND @col_130 IS NULL ) )
     AND ( ( col_19 = @col_131 ) OR ( col_19 IS NULL AND @col_131 IS NULL ) )
     AND ( ( col_20 = @col_132 ) OR ( col_20 IS NULL AND @col_132 IS NULL ) )
     AND ( ( col_15 = @col_103 ) OR ( col_15 IS NULL AND @col_103 IS NULL ) )
     AND ( ( col_18 = @col_104 ) OR ( col_18 IS NULL AND @col_104 IS NULL ) )

    -- xx xx xx xxxxxx xx xxxxxx xxxxxx xxxxx
    IF @@ROWCOUNT <> 1
    BEGIN
        RAISERROR (16947, 16, 1)
    END

    -- xxxxxx xx xxxxxx xxxx xx xxxxx xxxxxx
    IF @col_31 IS NULL
    BEGIN
        RAISERROR (40302, 16, 1)
    END

END
GO
SET QUOTED_IDENTIFIER OFF 
GO
SET ANSI_NULLS ON 
GO
-- xxx xxxxxx xxxxxx xxxxxx

-- xxxxxx xxxxxx xxxxxx 

IF OBJECT_ID(N'[dbo].[proc_20]', 'P') IS NULL
    EXEC ('CREATE PROCEDURE [dbo].[proc_20] AS SELECT 1')
GO

SET QUOTED_IDENTIFIER ON 
GO
SET ANSI_NULLS ON 
GO

--    <nombre>xxxxxx</nombre>
ALTER PROCEDURE dbo.proc_20
(
    @col_31 int = NULL,
    @col_6 uniqueidentifier = NULL,
    @col_32 int = NULL,
    @col_33 datetime = NULL,
    @col_12 int = NULL,
    @col_42 int = NULL,
    @col_62 varchar(10) = NULL,
    @col_13 int = NULL,
    @col_9 varchar(200) = NULL,
    @col_10 varchar(200) = NULL,
    @col_74 varchar(MAX) = NULL,
    @col_38 varchar(MAX) = NULL,
    @col_95 varchar(MAX) = NULL,
    @col_96 varchar(MAX) = NULL,
    @col_72 varchar(200) = NULL,
    @col_73 varchar(200) = NULL,
    @col_63 varchar(1000) = NULL,
    @col_19 varchar(10) = NULL,
    @col_20 datetime = NULL,
    @col_15 varchar(10) = NULL,
    @col_18 datetime = NULL,
    @col_107 varchar(MAX) = NULL,
    @col_2 int = NULL
)
AS
BEGIN
    SET NOCOUNT ON

    DECLARE @col_108 VARCHAR(MAX), @col_109 NVARCHAR(MAX), @col_110 NVARCHAR(MAX)

    IF (@col_2 IS NOT NULL)
    BEGIN
        SET ROWCOUNT @col_2
    END

    IF @col_31 IS NOT NULL AND @col_107 IS NULL
    BEGIN
        SELECT col_31, col_6, col_32, col_33, col_12, col_42, col_62, col_13, col_9, col_10, col_74, col_38, col_95, col_96, col_72, col_73, col_63, col_19, col_20, col_15, col_18
        FROM tbl_6
        WHERE ( @col_31 = col_31 ) AND
        ( col_31 = @col_31 OR @col_31 IS NULL )
     AND ( col_6 = @col_6 OR @col_6 IS NULL )
     AND ( col_32 = @col_32 OR @col_32 IS NULL )
     AND ( col_33 = @col_33 OR @col_33 IS NULL )
     AND ( col_12 = @col_12 OR @col_12 IS NULL )
     AND ( col_42 = @col_42 OR @col_42 IS NULL )
     AND ( col_62 = @col_62 OR @col_62 IS NULL )
     AND ( col_13 = @col_13 OR @col_13 IS NULL )
     AND ( col_9 = @col_9 OR @col_9 IS NULL )
     AND ( col_10 = @col_10 OR @col_10 IS NULL )
     AND ( col_74 = @col_74 OR @col_74 IS NULL )
     AND ( col_38 = @col_38 OR @col_38 IS NULL )
     AND ( col_95 = @col_95 OR @col_95 IS NULL )
     AND ( col_96 = @col_96 OR @col_96 IS NULL )
     AND ( col_72 = @col_72 OR @col_72 IS NULL )
     AND ( col_73 = @col_73 OR @col_73 IS NULL )
     AND ( col_63 = @col_63 OR @col_63 IS NULL )
     AND ( col_19 = @col_19 OR @col_19 IS NULL )
     AND ( col_20 = @col_20 OR @col_20 IS NULL )
     AND ( col_15 = @col_15 OR @col_15 IS NULL )
     AND ( col_18 = @col_18 OR @col_18 IS NULL );
    END
    ELSE
    BEGIN
        SET @col_109 = '
            SELECT col_31, col_6, col_32, col_33, col_12, col_42, col_62, col_13, col_9, col_10, col_74, col_38, col_95, col_96, col_72, col_73, col_63, col_19, col_20, col_15, col_18
            FROM tbl_6'

        EXEC proc_13 @col_110 OUTPUT, 'xxxxxxxxxxxxx', '=', '@xxxxxxxxxxxxx', @col_31
        EXEC proc_13 @col_110 OUTPUT, 'xxxx', '=', '@xxxx', @col_6
        EXEC proc_13 @col_110 OUTPUT, 'xxxxxxxx', '=', '@xxxxxxxx', @col_32
        EXEC proc_13 @col_110 OUTPUT, 'xxxxxxxx', '=', '@xxxxxxxx', @col_33
        EXEC proc_13 @col_110 OUTPUT, 'xxxxxxxxxxx', '=', '@xxxxxxxxxxx', @col_12
        EXEC proc_13 @col_110 OUTPUT, 'xxxxxxxxx', '=', '@xxxxxxxxx', @col_42
        EXEC proc_13 @col_110 OUTPUT, 'xxxxxxx', '=', '@xxxxxxx', @col_62
        EXEC proc_13 @col_110 OUTPUT, 'xxxxxxxx', '=', '@xxxxxxxx', @col_13
        EXEC proc_13 @col_110 OUTPUT, 'xxxxxxxxxxxxx', '=', '@xxxxxxxxxxxxx', @col_9
        EXEC proc_13 @col_110 OUTPUT, 'xxxxxxxxxxxxx', '=', '@xxxxxxxxxxxxx', @col_10
        EXEC proc_13 @col_110 OUTPUT, 'xxxxx', '=', '@xxxxx', @col_74
        EXEC proc_13 @col_110 OUTPUT, 'xxxxxxxxxx', '=', '@xxxxxxxxxx', @col_38
        EXEC proc_13 @col_110 OUTPUT, 'xxxxxxxxxxxxxxxx', '=', '@xxxxxxxxxxxxxxxx', @col_95
        EXEC proc_13 @col_110 OUTPUT, 'xxxxxxxxxxxxxx', '=', '@xxxxxxxxxxxxxx', @col_96
        EXEC proc_13 @col_110 OUTPUT, 'xxxx', '=', '@xxxx', @col_72
        EXEC proc_13 @col_110 OUTPUT, 'xxxxx', '=', '@xxxxx', @col_73
        EXEC proc_13 @col_110 OUTPUT, 'xxxxxx', '=', '@xxxxxx', @col_63
        EXEC proc_13 @col_110 OUTPUT, 'xxxxxxxxxxx', '=', '@xxxxxxxxxxx', @col_19
        EXEC proc_13 @col_110 OUTPUT, 'xxxxxxxxx', '=', '@xxxxxxxxx', @col_20
        EXEC proc_13 @col_110 OUTPUT, 'xxxxxxxxxx', '=', '@xxxxxxxxxx', @col_15
        EXEC proc_13 @col_110 OUTPUT, 'xxxxxxxx', '=', '@xxxxxxxx', @col_18

        if @col_110 IS NOT NULL
        begin
            set @col_109 = @col_109 + ' WHERE ' + @col_110
        end

        exec proc_14 @col_109 output, @col_107, @col_108 output

        exec sp_executesql @col_109, N'
            @xxxxxxxxxxxxx xxx,
            @xxxx xxxxxxxxxxxxxxxx,
            @xxxxxxxx xxx,
            @xxxxxxxx xxxxxxxx,
            @xxxxxxxxxxx xxx,
            @xxxxxxxxx xxx,
            @xxxxxxx xxxxxxx(xx),
            @xxxxxxxx xxx,
            @xxxxxxxxxxxxx xxxxxxx(xxx),
            @xxxxxxxxxxxxx xxxxxxx(xxx),
            @xxxxx xxxxxxx(xxx),
            @xxxxxxxxxx xxxxxxx(xxx),
            @xxxxxxxxxxxxxxxx xxxxxxx(xxx),
            @xxxxxxxxxxxxxx xxxxxxx(xxx),
            @xxxx xxxxxxx(xxx),
            @xxxxx xxxxxxx(xxx),
            @xxxxxx xxxxxxx(xxxx),
            @xxxxxxxxxxx xxxxxxx(xx),
            @xxxxxxxxx xxxxxxxx,
            @xxxxxxxxxx xxxxxxx(xx),
            @xxxxxxxx xxxxxxxx,
            @xxxxxxxx_xxxxxx xxxxxxx(xxx)',
            @col_31, @col_6, @col_32, @col_33, @col_12, @col_42, @col_62, @col_13, @col_9, @col_10, @col_74, @col_38, @col_95, @col_96, @col_72, @col_73, @col_63, @col_19, @col_20, @col_15, @col_18,
            @col_108
    END

END
GO
SET QUOTED_IDENTIFIER OFF 
GO
SET ANSI_NULLS ON 
GO
-- xxx xxxxxx xxxxxx xxxxxx

-- xxxxxx xxxxxx xxxxxx 

IF OBJECT_ID(N'[dbo].[proc_21]', 'P') IS NULL
    EXEC ('CREATE PROCEDURE [dbo].[proc_21] AS SELECT 1')
GO

SET QUOTED_IDENTIFIER ON 
GO
SET ANSI_NULLS ON 
GO

--    <nombre>xxxxxx</nombre>
ALTER PROCEDURE dbo.proc_21
(
    @col_101 int = NULL,
    @col_115 uniqueidentifier = NULL,
    @col_116 int = NULL,
    @col_117 datetime = NULL,
    @col_118 int = NULL,
    @col_119 int = NULL,
    @col_120 varchar(10) = NULL,
    @col_121 int = NULL,
    @col_122 varchar(200) = NULL,
    @col_123 varchar(200) = NULL,
    @col_124 varchar(MAX) = NULL,
    @col_125 varchar(MAX) = NULL,
    @col_126 varchar(MAX) = NULL,
    @col_127 varchar(MAX) = NULL,
    @col_128 varchar(200) = NULL,
    @col_129 varchar(200) = NULL,
    @col_130 varchar(1000) = NULL,
    @col_131 varchar(10) = NULL,
    @col_132 datetime = NULL,
    @col_103 varchar(10) = NULL,
    @col_104 datetime = NULL
)
AS
BEGIN
    SET NOCOUNT ON

    DELETE FROM tbl_6
    WHERE ( col_31 = @col_101 )
     AND ( ( col_6 = @col_115 ) OR ( col_6 IS NULL AND @col_115 IS NULL ) )
     AND ( ( col_32 = @col_116 ) OR ( col_32 IS NULL AND @col_116 IS NULL ) )
     AND ( ( col_33 = @col_117 ) OR ( col_33 IS NULL AND @col_117 IS NULL ) )
     AND ( ( col_12 = @col_118 ) OR ( col_12 IS NULL AND @col_118 IS NULL ) )
     AND ( ( col_42 = @col_119 ) OR ( col_42 IS NULL AND @col_119 IS NULL ) )
     AND ( ( col_62 = @col_120 ) OR ( col_62 IS NULL AND @col_120 IS NULL ) )
     AND ( ( col_13 = @col_121 ) OR ( col_13 IS NULL AND @col_121 IS NULL ) )
     AND ( ( col_9 = @col_122 ) OR ( col_9 IS NULL AND @col_122 IS NULL ) )
     AND ( ( col_10 = @col_123 ) OR ( col_10 IS NULL AND @col_123 IS NULL ) )
     AND ( ( col_74 = @col_124 ) OR ( col_74 IS NULL AND @col_124 IS NULL ) )
     AND ( ( col_38 = @col_125 ) OR ( col_38 IS NULL AND @col_125 IS NULL ) )
     AND ( ( col_95 = @col_126 ) OR ( col_95 IS NULL AND @col_126 IS NULL ) )
     AND ( ( col_96 = @col_127 ) OR ( col_96 IS NULL AND @col_127 IS NULL ) )
     AND ( ( col_72 = @col_128 ) OR ( col_72 IS NULL AND @col_128 IS NULL ) )
     AND ( ( col_73 = @col_129 ) OR ( col_73 IS NULL AND @col_129 IS NULL ) )
     AND ( ( col_63 = @col_130 ) OR ( col_63 IS NULL AND @col_130 IS NULL ) )
     AND ( ( col_19 = @col_131 ) OR ( col_19 IS NULL AND @col_131 IS NULL ) )
     AND ( ( col_20 = @col_132 ) OR ( col_20 IS NULL AND @col_132 IS NULL ) )
     AND ( ( col_15 = @col_103 ) OR ( col_15 IS NULL AND @col_103 IS NULL ) )
     AND ( ( col_18 = @col_104 ) OR ( col_18 IS NULL AND @col_104 IS NULL ) )

    -- xx xx xx xxxxxx xx xxxxxx xxxxxx xxxxx
    IF @@ROWCOUNT <> 1
    BEGIN
        RAISERROR (16947, 16, 1)
    END

END
GO
SET QUOTED_IDENTIFIER OFF 
GO
SET ANSI_NULLS ON 
GO
-- xxx xxxxxx xxxxxx xxxxxx

-- xxxxxx xxxxxx xxxxxx 

IF OBJECT_ID(N'[dbo].[proc_22]', 'P') IS NULL
    EXEC ('CREATE PROCEDURE [dbo].[proc_22] AS SELECT 1')
GO

SET QUOTED_IDENTIFIER ON 
GO
SET ANSI_NULLS ON 
GO

--    <nombre>xxxxxx</nombre>
ALTER PROCEDURE dbo.proc_22
(
    @col_6 uniqueidentifier = NULL,
    @col_7 int = NULL,
    @col_91 varchar(4000) = NULL,
    @col_19 varchar(10) = NULL,
    @col_20 datetime = NULL,
    @col_15 varchar(10) = NULL,
    @col_18 datetime = NULL,
    @col_115 uniqueidentifier = NULL,
    @col_133 int = NULL,
    @col_134 varchar(4000) = NULL,
    @col_131 varchar(10) = NULL,
    @col_132 datetime = NULL,
    @col_103 varchar(10) = NULL,
    @col_104 datetime = NULL
)
AS
BEGIN
    SET NOCOUNT ON

    UPDATE tbl_3
    SET col_7 = @col_7,
        col_91 = @col_91,
        col_19 = @col_19,
        col_20 = @col_20,
        col_15 = @col_15,
        col_18 = @col_18
    WHERE ( col_6 = @col_115 )
     AND ( ( col_7 = @col_133 ) OR ( col_7 IS NULL AND @col_133 IS NULL ) )
     AND ( ( col_91 = @col_134 ) OR ( col_91 IS NULL AND @col_134 IS NULL ) )
     AND ( ( col_19 = @col_131 ) OR ( col_19 IS NULL AND @col_131 IS NULL ) )
     AND ( ( col_20 = @col_132 ) OR ( col_20 IS NULL AND @col_132 IS NULL ) )
     AND ( ( col_15 = @col_103 ) OR ( col_15 IS NULL AND @col_103 IS NULL ) )
     AND ( ( col_18 = @col_104 ) OR ( col_18 IS NULL AND @col_104 IS NULL ) )

    -- xx xx xx xxxxxx xx xxxxxx xxxxxx xxxxx
    IF @@ROWCOUNT <> 1
    BEGIN
        RAISERROR (16947, 16, 1)
    END

    -- xxxxxx xx xxxxxx xxxx xx xxxxx xxxxxx
    IF @col_6 IS NULL
    BEGIN
        RAISERROR (40302, 16, 1)
    END

END
GO
SET QUOTED_IDENTIFIER OFF 
GO
SET ANSI_NULLS ON 
GO
-- xxx xxxxxx xxxxxx xxxxxx

-- xxxxxx xxxxxx xxxxxx 

IF OBJECT_ID(N'[dbo].[proc_23]', 'P') IS NULL
    EXEC ('CREATE PROCEDURE [dbo].[proc_23] AS SELECT 1')
GO

SET QUOTED_IDENTIFIER ON 
GO
SET ANSI_NULLS ON 
GO

--    <nombre>xxxxxx</nombre>
ALTER PROCEDURE dbo.proc_23
(
    @col_6 uniqueidentifier = NULL,
    @col_7 int = NULL,
    @col_91 varchar(4000) = NULL,
    @col_19 varchar(10) = NULL,
    @col_20 datetime = NULL,
    @col_15 varchar(10) = NULL,
    @col_18 datetime = NULL,
    @col_107 varchar(MAX) = NULL,
    @col_2 int = NULL
)
AS
BEGIN
    SET NOCOUNT ON

    DECLARE @col_108 VARCHAR(MAX), @col_109 NVARCHAR(MAX), @col_110 NVARCHAR(MAX)

    IF (@col_2 IS NOT NULL)
    BEGIN
        SET ROWCOUNT @col_2
    END

    IF @col_6 IS NOT NULL AND @col_107 IS NULL
    BEGIN
        SELECT col_6, col_7, col_91, col_19, col_20, col_15, col_18
        FROM tbl_3
        WHERE ( @col_6 = col_6 ) AND
        ( col_6 = @col_6 OR @col_6 IS NULL )
     AND ( col_7 = @col_7 OR @col_7 IS NULL )
     AND ( col_91 = @col_91 OR @col_91 IS NULL )
     AND ( col_19 = @col_19 OR @col_19 IS NULL )
     AND ( col_20 = @col_20 OR @col_20 IS NULL )
     AND ( col_15 = @col_15 OR @col_15 IS NULL )
     AND ( col_18 = @col_18 OR @col_18 IS NULL );
    END
    ELSE
    BEGIN
        SET @col_109 = '
            SELECT col_6, col_7, col_91, col_19, col_20, col_15, col_18
            FROM tbl_3'

        EXEC proc_13 @col_110 OUTPUT, 'xxxx', '=', '@xxxx', @col_6
        EXEC proc_13 @col_110 OUTPUT, 'xxxxxxx', '=', '@xxxxxxx', @col_7
        EXEC proc_13 @col_110 OUTPUT, 'xxxxxxxxxx', '=', '@xxxxxxxxxx', @col_91
        EXEC proc_13 @col_110 OUTPUT, 'xxxxxxxxxxx', '=', '@xxxxxxxxxxx', @col_19
        EXEC proc_13 @col_110 OUTPUT, 'xxxxxxxxx', '=', '@xxxxxxxxx', @col_20
        EXEC proc_13 @col_110 OUTPUT, 'xxxxxxxxxx', '=', '@xxxxxxxxxx', @col_15
        EXEC proc_13 @col_110 OUTPUT, 'xxxxxxxx', '=', '@xxxxxxxx', @col_18

        if @col_110 IS NOT NULL
        begin
            set @col_109 = @col_109 + ' WHERE ' + @col_110
        end

        exec proc_14 @col_109 output, @col_107, @col_108 output

        exec sp_executesql @col_109, N'
            @xxxx xxxxxxxxxxxxxxxx,
            @xxxxxxx xxx,
            @xxxxxxxxxx xxxxxxx(xxxx),
            @xxxxxxxxxxx xxxxxxx(xx),
            @xxxxxxxxx xxxxxxxx,
            @xxxxxxxxxx xxxxxxx(xx),
            @xxxxxxxx xxxxxxxx,
            @xxxxxxxx_xxxxxx xxxxxxx(xxx)',
            @col_6, @col_7, @col_91, @col_19, @col_20, @col_15, @col_18,
            @col_108
    END

END
GO
SET QUOTED_IDENTIFIER OFF 
GO
SET ANSI_NULLS ON 
GO
-- xxx xxxxxx xxxxxx xxxxxx

-- xxxxxx xxxxxx xxxxxx 

IF OBJECT_ID(N'[dbo].[proc_24]', 'P') IS NULL
    EXEC ('CREATE PROCEDURE [dbo].[proc_24] AS SELECT 1')
GO

SET QUOTED_IDENTIFIER ON 
GO
SET ANSI_NULLS ON 
GO

--    <nombre>xxxxxx</nombre>
ALTER PROCEDURE dbo.proc_24
(
    @col_115 uniqueidentifier = NULL,
    @col_133 int = NULL,
    @col_134 varchar(4000) = NULL,
    @col_131 varchar(10) = NULL,
    @col_132 datetime = NULL,
    @col_103 varchar(10) = NULL,
    @col_104 datetime = NULL
)
AS
BEGIN
    SET NOCOUNT ON

    DELETE FROM tbl_3
    WHERE ( col_6 = @col_115 )
     AND ( ( col_7 = @col_133 ) OR ( col_7 IS NULL AND @col_133 IS NULL ) )
     AND ( ( col_91 = @col_134 ) OR ( col_91 IS NULL AND @col_134 IS NULL ) )
     AND ( ( col_19 = @col_131 ) OR ( col_19 IS NULL AND @col_131 IS NULL ) )
     AND ( ( col_20 = @col_132 ) OR ( col_20 IS NULL AND @col_132 IS NULL ) )
     AND ( ( col_15 = @col_103 ) OR ( col_15 IS NULL AND @col_103 IS NULL ) )
     AND ( ( col_18 = @col_104 ) OR ( col_18 IS NULL AND @col_104 IS NULL ) )

    -- xx xx xx xxxxxx xx xxxxxx xxxxxx xxxxx
    IF @@ROWCOUNT <> 1
    BEGIN
        RAISERROR (16947, 16, 1)
    END

END
GO
SET QUOTED_IDENTIFIER OFF 
GO
SET ANSI_NULLS ON 
GO
-- xxx xxxxxx xxxxxx xxxxxx

-- xxxxxx xxxxxx xxxxxx 

IF OBJECT_ID(N'[dbo].[proc_25]', 'P') IS NULL
    EXEC ('CREATE PROCEDURE [dbo].[proc_25] AS SELECT 1')
GO

SET QUOTED_IDENTIFIER ON 
GO
SET ANSI_NULLS ON 
GO

--   <nombre>xxxxxx</nombre>
ALTER PROCEDURE dbo.proc_25
(
    @col_1 INT = NULL,
    @col_135 DATETIME = NULL,
    @col_136 DATETIME = NULL,
    @col_137 VARCHAR(10) = NULL,
    @col_138 VARCHAR(5) = NULL,
    @col_139 VARCHAR(200) = NULL,
    @col_140 VARCHAR(200) = NULL,
    @col_141 VARCHAR(200) = NULL,
    @col_142 VARCHAR(200) = NULL,
    @col_143 VARCHAR(200) = NULL,
    @col_144 VARCHAR(200) = NULL,
    @col_145 VARCHAR(200) = NULL,
    @col_146 VARCHAR(200) = NULL,
    @col_2 int = NULL
)
AS
BEGIN
    SET NOCOUNT ON

    DECLARE @func1 DATETIME = dbo.func1()
    DECLARE @col_147 DATETIME = CAST(dbo.func1() AS DATE)

    IF (@col_2 IS NOT NULL)
    BEGIN
        SET ROWCOUNT @col_2
    END

    SELECT
        col_1,
        col_50,
        col_148,
        CASE
            WHEN col_148 = 'A' THEN @col_144
            WHEN col_148 = 'B' THEN @col_145
            WHEN col_148 = 'C' THEN @col_146
        ELSE
            @col_144
        END
        as col_149,
        col_150,
        col_58,
        col_13,
        col_151,
        col_152,
        col_137,
        col_60,
        col_153,
        col_154,
        col_138,
        col_155,
        CASE
            WHEN col_156 IS NOT NULL THEN @col_143
            WHEN col_157 IS NOT NULL THEN @col_143
            WHEN col_158 IS NOT NULL THEN @col_142
            WHEN col_159 IS NOT NULL THEN @col_141
        ELSE
            @col_140
        END
        as col_160,
        col_159,
        col_158,
        col_157,
        col_156,
        col_161
    FROM (
    SELECT

        DISTINCT

        col_11.col_1,
        col_11.col_50,
        col_11.col_162 as col_148,
        col_11.col_58 as col_150,
        col_57.col_163 as col_58,
        col_11.col_13,
        col_45.col_46 as col_151,
        COALESCE(col_37.col_10, col_45.col_164, col_45.col_165, col_45.col_166) as col_152,
        col_57.col_60 as col_137,
        col_52.col_46 as col_60,
        col_52.col_153,
        col_167.col_163 as col_154,
        col_52.col_155 as col_138,
        col_22.col_163 as col_155,

        (SELECT MIN(col_40.col_94)
            FROM dbo.tbl_8 col_40
            WHERE col_40.col_31 IN (
            SELECT col_31 FROM dbo.tbl_6 col_168
                WHERE col_168.col_6=col_37.col_6 AND col_168.col_12 IN (0, 1) /* xxxxxx col_151 */
            )
            AND col_40.col_39 = 1 /* xxxxxx xx xx col_6 xx xxxxxx */
        ) as col_159,

        (SELECT MIN(col_40.col_94)
            FROM dbo.tbl_8 col_40
            WHERE col_40.col_31 IN (
                SELECT col_31 FROM dbo.tbl_6 col_168
                WHERE col_168.col_6=col_37.col_6 AND col_168.col_12 IN (0, 1, 2) /* xxxxxx col_151 col_60 */
            )
            AND col_40.col_39 = 3 /* xxxxxx xx xx xxxxxx */
        ) as col_158,

        (SELECT MAX(col_40.col_94)
            FROM dbo.tbl_8 col_40
            WHERE col_40.col_31 IN (
                SELECT col_31 FROM dbo.tbl_6 col_168
                WHERE col_168.col_6=col_37.col_6 AND col_168.col_12 IN (0, 1, 2) /* xxxxxx col_151 col_60 */
            )
            AND col_40.col_39 = 4 /* xxxxxx xx xx xxxxxx */
        ) as col_157,

        (SELECT MAX(col_40.col_94)
            FROM dbo.tbl_8 col_40
            WHERE col_40.col_31 IN (
                SELECT col_31 FROM dbo.tbl_6 col_168
                WHERE col_168.col_6=col_37.col_6 AND col_168.col_12 IN (0, 1) /* xxxxxx col_151 col_60 */
            )
            AND col_40.col_39 = 2 /* xxxxxx xx xx col_6 xx xxxxxx */
        ) as col_156,

        COALESCE(
        (
            SELECT TOP(1) 1
            FROM dbo.tbl_7
            WHERE col_31=col_37.col_31
            ORDER BY col_31 ASC
            /* xxxxxx xx xx xxxxxx xx col_161 */
        )
        , 0) as col_161

    FROM
        dbo.tbl_1 col_11
        INNER JOIN dbo.tbl_2 col_56 ON col_11.col_1 = col_56.col_1
        INNER JOIN dbo.tbl_6 col_37 ON col_37.col_6 = col_56.col_6
        INNER JOIN dbo.tbl_10 col_45 ON col_11.col_13=col_45.col_13
        INNER JOIN dbo.tbl_11 col_57 ON col_11.col_58=col_57.col_59
        INNER JOIN dbo.tbl_12 col_52 ON col_57.col_60=col_52.col_59
        INNER JOIN dbo.tbl_14 col_167 ON col_52.col_153=col_167.col_153
        INNER JOIN dbo.tbl_15 col_22 ON col_52.col_155=col_22.col_59
    WHERE
        col_11.col_50 BETWEEN COALESCE(@col_135, @col_147) AND COALESCE(@col_136, @func1)
        AND col_37.col_12 = 1 /* col_151 */
        AND col_37.col_13 = col_11.col_13
        AND col_37.col_42 = 0
        AND (@col_1 IS NULL OR col_11.col_1 = @col_1)
        AND (@col_137 IS NULL OR col_57.col_60 = @col_137)
        AND (@col_138 IS NULL OR col_52.col_155 = @col_138)
        AND (@col_139 IS NULL OR col_11.col_162 IN (SELECT item FROM dbo.func5(@col_139, ',')))
    ) col_160
    ORDER BY col_50 ASC
    OPTION (RECOMPILE)

END
GO
SET QUOTED_IDENTIFIER OFF 
GO
SET ANSI_NULLS ON 
GO
-- xxx xxxxxx xxxxxx xxxxxx

-- xxxxxx xxxxxx xxxxxx 

IF OBJECT_ID(N'[dbo].[proc_26]', 'P') IS NULL
    EXEC ('CREATE PROCEDURE [dbo].[proc_26] AS SELECT 1')
GO

SET QUOTED_IDENTIFIER ON 
GO
SET ANSI_NULLS ON 
GO

--   <nombre>xxxxxx</nombre>
ALTER PROCEDURE dbo.proc_26
(
    @col_1 int = NULL,
    @col_13 int = NULL
)
AS
BEGIN
    SET NOCOUNT ON

    DECLARE @func1 DATETIME = dbo.func1()
    DECLARE @col_67 INT = COALESCE((SELECT TOP(1) col_67 FROM tbl_9 WHERE col_30=1 ORDER BY col_66 ASC), 1440)

    -- xxxxxx xxx xxxxxx xxxxxx xxxxxx xx xxxxxx x xxxxxx
    UPDATE tbl_6
    SET col_32 = 0
    WHERE
        col_32 = 1
        AND col_31 IN (
            SELECT col_171.col_31
            FROM tbl_6 col_171
            INNER JOIN tbl_2 col_56 ON col_56.col_6=col_171.col_6
            INNER JOIN tbl_1 col_11 ON col_11.col_1=col_56.col_1
            WHERE
                col_32 = 1 AND
                @func1 > DATEADD(minute, @col_67, col_11.col_50)
        )

    -- xxxxxx xxx xxxxxx xx xx xxxxx xx xxxxxx
    -- xxxx xxx xxxx xxx xx x xxxxxx xxx xx xx xxxx xxxx xx xxxxxx
    UPDATE tbl_6
    SET col_32 = 0
    WHERE
        col_32 = 1
        AND @func1 > DATEADD(minute, 5, COALESCE(col_33, @func1))

    SELECT
        DISTINCT
        col_56.col_1
    FROM tbl_2 col_56
    WHERE
    EXISTS
    (
        SELECT null
        FROM tbl_6 col_37
        WHERE
        col_37.col_6=col_56.col_6 and
        col_37.col_32 = 1 and
        (@col_13 IS NULL OR col_37.col_13=@col_13)
    )
    AND (@col_1 IS NULL OR col_56.col_1=@col_1)
    OPTION (RECOMPILE)

END
GO
SET QUOTED_IDENTIFIER OFF 
GO
SET ANSI_NULLS ON 
GO
-- xxx xxxxxx xxxxxx xxxxxx

-- xxxxxx xxxxxx xxxxxx 

IF OBJECT_ID(N'[dbo].[proc_27]', 'P') IS NULL
    EXEC ('CREATE PROCEDURE [dbo].[proc_27] AS SELECT 1')
GO

SET QUOTED_IDENTIFIER ON 
GO
SET ANSI_NULLS ON 
GO

--   <nombre>xxxxxx</nombre>
ALTER PROCEDURE dbo.proc_27
(
    @col_1 int = NULL,
    @col_2 int = NULL
)
AS
BEGIN
    SET NOCOUNT ON

    DECLARE @col_6 UNIQUEIDENTIFIER=(SELECT col_6 FROM tbl_2 WHERE col_1=@col_1)

    IF (@col_2 IS NOT NULL)
    BEGIN
        SET ROWCOUNT @col_2
    END

    IF (@col_6 IS NOT NULL)
    BEGIN

        DELETE FROM tbl_8 WHERE col_31 IN (SELECT col_31 FROM tbl_6 WHERE col_6=@col_6)

        DELETE FROM tbl_6 WHERE col_6=@col_6

        DELETE FROM tbl_2 WHERE col_1=@col_1

        DELETE FROM tbl_3 WHERE col_6=@col_6

    END

END
GO
SET QUOTED_IDENTIFIER OFF 
GO
SET ANSI_NULLS ON 
GO
-- xxx xxxxxx xxxxxx xxxxxx

-- xxxxxx xxxxxx xxxxxx 

-- xxxxxx xxxxxx xxxxxx 
IF NOT OBJECT_ID(N'[col_173]') IS NULL
    DROP TRIGGER [dbo].[col_173];
GO
-- xxx xxxxxx xxxxxx xxxxxx

SET QUOTED_IDENTIFIER ON 
GO
SET ANSI_NULLS ON 
GO

--   <nombre>xxxxxx</nombre>
CREATE TRIGGER dbo.col_173 ON dbo.tbl_6
FOR UPDATE
AS
BEGIN
    SET NOCOUNT ON
    DECLARE @func1 DATETIME = dbo.func1()
    DECLARE @col_174 INT = COALESCE((SELECT 1 FROM dbo.tbl_9 WHERE col_96 IS NOT NULL AND col_30=1), 0)
    IF UPDATE(col_32)
     BEGIN
         /* xxxxxx xxxx xxxxxx */
         INSERT INTO dbo.tbl_8
         (
            col_15,
            col_18,
            col_31,
            col_39,
            col_94
         )
         SELECT
            col_175.col_15,
            col_175.col_18,
            col_175.col_31,
            (4 - ((2 * @col_174 * (1 - col_175.col_42)) + col_175.col_32)) as col_39,
            @func1 as col_94
         FROM inserted col_175
            INNER JOIN deleted col_176 ON col_176.col_31=col_175.col_31
         WHERE
            col_175.col_32 <> col_176.col_32
            /* xx xx xxxx xx xxxxxx xxxxxx xx xxxxx col_162 xx xxxxxx xxx x */
     END
END
GO
SET QUOTED_IDENTIFIER OFF 
GO
SET ANSI_NULLS ON 
GO
-- xxx xxxxxx xxxxxx xxxxxx



