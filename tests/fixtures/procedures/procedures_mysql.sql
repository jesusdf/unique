-- ============================================================
-- MySQL fixture: generated from procedures_sqlserver.sql
-- by the unique transpiler (T-SQL -> MySQL).
-- Validated against MySQL 8.0.
-- DO NOT EDIT BY HAND -- regenerate via the transpiler.
-- ============================================================

CREATE TABLE tbl_15 (
  col_59 VARCHAR(5) NOT NULL,
  col_163 VARCHAR(200),
  CONSTRAINT pk_tbl_15 PRIMARY KEY (col_59)
);

CREATE TABLE tbl_14 (
  col_153 INT NOT NULL,
  col_163 VARCHAR(200),
  CONSTRAINT pk_tbl_14 PRIMARY KEY (col_153)
);

CREATE TABLE tbl_13 (
  col_62 VARCHAR(50) NOT NULL,
  col_46 VARCHAR(200),
  col_77 VARCHAR(200),
  CONSTRAINT pk_tbl_13 PRIMARY KEY (col_62)
);

CREATE TABLE tbl_12 (
  col_59 INT NOT NULL,
  col_46 VARCHAR(200),
  col_153 INT,
  col_155 VARCHAR(5),
  CONSTRAINT pk_tbl_12 PRIMARY KEY (col_59)
);

CREATE TABLE tbl_11 (
  col_59 INT NOT NULL,
  col_60 INT,
  col_163 VARCHAR(200),
  CONSTRAINT pk_tbl_11 PRIMARY KEY (col_59)
);

CREATE TABLE tbl_10 (
  col_13 INT NOT NULL,
  col_46 VARCHAR(200),
  col_48 VARCHAR(200),
  col_73 VARCHAR(200),
  col_164 VARCHAR(200),
  col_165 VARCHAR(200),
  col_166 VARCHAR(200),
  CONSTRAINT pk_tbl_10 PRIMARY KEY (col_13)
);

CREATE TABLE tbl_1 (
  col_1 INT NOT NULL,
  col_13 INT,
  col_50 DATETIME,
  col_58 INT,
  col_162 VARCHAR(50),
  CONSTRAINT pk_tbl_1 PRIMARY KEY (col_1)
);

CREATE TABLE tbl_3 (
  col_6 CHAR(36) NOT NULL DEFAULT (UUID()),
  col_7 INT,
  col_91 VARCHAR(4000),
  col_19 VARCHAR(10),
  col_20 DATETIME,
  col_15 VARCHAR(10),
  col_18 DATETIME,
  CONSTRAINT pk_tbl_3 PRIMARY KEY (col_6)
);

CREATE TABLE tbl_2 (
  col_1 INT,
  col_4 INT,
  col_6 CHAR(36),
  col_15 VARCHAR(10),
  col_18 DATETIME,
  col_19 VARCHAR(10),
  col_20 DATETIME
);

CREATE TABLE tbl_4 (
  col_6 CHAR(36),
  col_9 VARCHAR(200),
  col_10 VARCHAR(200),
  col_12 INT,
  col_13 INT
);

CREATE TABLE tbl_5 (
  col_23 INT NOT NULL,
  col_24 INT,
  col_26 VARCHAR(200),
  col_28 INT,
  col_30 INT NOT NULL DEFAULT 1,
  CONSTRAINT pk_tbl_5 PRIMARY KEY (col_23)
);

CREATE TABLE tbl_9 (
  col_30 INT NOT NULL DEFAULT 1,
  col_43 VARCHAR,
  col_61 VARCHAR(200),
  col_65 INT DEFAULT -1440,
  col_66 DATETIME,
  col_67 INT DEFAULT 1440,
  col_79 VARCHAR,
  col_80 VARCHAR,
  col_89 VARCHAR(500),
  col_90 VARCHAR(500),
  col_96 VARCHAR
);

CREATE TABLE tbl_6 (
  col_31 INT AUTO_INCREMENT NOT NULL,
  col_6 CHAR(36),
  col_12 INT,
  col_13 INT,
  col_15 VARCHAR(10),
  col_18 DATETIME,
  col_19 VARCHAR(10),
  col_20 DATETIME,
  col_32 INT DEFAULT 0,
  col_33 DATETIME,
  col_38 VARCHAR,
  col_42 INT DEFAULT 0,
  col_62 VARCHAR(50),
  col_63 VARCHAR(1000),
  col_72 VARCHAR(200),
  col_73 VARCHAR(200),
  col_74 VARCHAR,
  col_9 VARCHAR(200),
  col_10 VARCHAR(200),
  col_95 VARCHAR,
  col_96 VARCHAR,
  CONSTRAINT pk_tbl_6 PRIMARY KEY (col_31)
);

CREATE TABLE tbl_7 (
  col_97 INT NOT NULL,
  col_31 INT,
  col_23 INT NOT NULL,
  col_15 VARCHAR(10),
  col_18 DATETIME,
  col_98 INT,
  col_99 VARCHAR
);

CREATE TABLE tbl_8 (
  col_93 INT AUTO_INCREMENT NOT NULL,
  col_15 VARCHAR(10),
  col_18 DATETIME,
  col_31 INT,
  col_39 INT,
  col_94 DATETIME,
  CONSTRAINT pk_tbl_8 PRIMARY KEY (col_93)
);

-- -- ── Helper stored procedures called by the fixture ────────────────────────────

-- IF OBJECT_ID(N'dbo.proc_13', N'P') IS NULL
--     EXEC (N'CREATE PROCEDURE dbo.proc_13 AS SELECT 1')
DELIMITER $$
CREATE PROCEDURE proc_13
(
    OUT v_where LONGTEXT,
    IN v_col VARCHAR(200),
    IN v_op VARCHAR(10),
    IN v_param VARCHAR(200),
    IN v_val LONGTEXT /* UNIQUE: SQL_VARIANT */
)
BEGIN
    /* UNIQUE: SET NOCOUNT ON -- no mysql equivalent */
    IF v_val IS NOT NULL THEN
            SET v_where = CONCAT(COALESCE(CONCAT(v_where, ' AND '), ''), v_col, ' ', v_op, ' ', v_param);
    END IF;
END$$
DELIMITER ;

-- IF OBJECT_ID(N'dbo.proc_14', N'P') IS NULL
--     EXEC (N'CREATE PROCEDURE dbo.proc_14 AS SELECT 1')
DELIMITER $$
CREATE PROCEDURE proc_14
(
    OUT v_query LONGTEXT,
    IN v_filter LONGTEXT,
    OUT v_page LONGTEXT
)
BEGIN
    /* UNIQUE: SET NOCOUNT ON -- no mysql equivalent */
    SET v_page = NULL;
    IF v_filter IS NOT NULL THEN
            SET v_query = CONCAT(v_query, ' ', v_filter);
    END IF;
END$$
DELIMITER ;

-- ============================================================
-- Stub definitions for anonymized custom functions (T-SQL).
-- These make the script self-contained and runnable; bodies are
-- placeholders that preserve the call signatures and return types.
-- ============================================================
-- IF OBJECT_ID(N'[dbo].[func1]', 'FN') IS NOT NULL DROP FUNCTION [dbo].[func1]
DELIMITER $$
CREATE FUNCTION func1()
RETURNS DATETIME
DETERMINISTIC
BEGIN
    RETURN DATE_ADD(NOW(), INTERVAL - 3 DAY);
END$$
DELIMITER ;

-- IF OBJECT_ID(N'[dbo].[func3]', 'FN') IS NOT NULL DROP FUNCTION [dbo].[func3]
DELIMITER $$
CREATE FUNCTION func3
(
    v_key VARCHAR(100),
    v_def VARCHAR(400)
)
RETURNS VARCHAR(400)
DETERMINISTIC
BEGIN
    RETURN v_def;
END$$
DELIMITER ;

-- IF OBJECT_ID(N'[dbo].[func4]', 'FN') IS NOT NULL DROP FUNCTION [dbo].[func4]
DELIMITER $$
CREATE FUNCTION func4
(
    v_payload LONGTEXT,
    v_secret VARCHAR(400)
)
RETURNS LONGTEXT
DETERMINISTIC
BEGIN
    RETURN SHA2(CONCAT(v_payload, v_secret), 256);
END$$
DELIMITER ;

-- IF OBJECT_ID(N'[dbo].[func5]', 'IF') IS NOT NULL DROP FUNCTION [dbo].[func5]
-- UNIQUE: inline table-valued function ('RETURNS TABLE') has no direct equivalent. MySQL has no table-returning functions; use a view or a procedure with a result set.
-- The non-portable translation is commented out below for review:
-- CREATE FUNCTION func5
-- (
--     v_s LONGTEXT,
--     v_delim VARCHAR(5)
-- )
-- RETURNS TABLE
-- DETERMINISTIC
-- BEGIN
--     RETURN (SELECT LTRIM(RTRIM(value)) AS item FROM JSON_TABLE(CONCAT('["', REPLACE(v_s, v_delim, '","'), '"]'), '$[*]' COLUMNS(value VARCHAR(4000) PATH '$')) AS _ss);
-- END
-- -- xxxxxx xxxxxx


-- -- xxxxxx xxxxxx xxxxxx 

-- IF OBJECT_ID(N'[dbo].[proc_1]', 'P') IS NULL
--     EXEC ('CREATE PROCEDURE [dbo].[proc_1] AS SELECT 1')
-- SET QUOTED_IDENTIFIER ON
-- SET ANSI_NULLS ON
DELIMITER $$
CREATE PROCEDURE proc_1
(
    IN v_col_1 INT,
    IN v_col_2 INT
)
BEGIN
    /* UNIQUE: SET NOCOUNT ON -- no mysql equivalent */
    IF ( v_col_2 IS NOT NULL ) THEN
            /* UNIQUE: SET ROWCOUNT v_col_2 -- no mysql equivalent */
            DO 0;
    END IF;
    SELECT * FROM (SELECT DISTINCT col_3.col_1, col_3.col_4, col_5.col_6, col_5.col_7, col_8.col_9, col_8.col_10 FROM tbl_1 AS col_11 INNER JOIN tbl_2 AS col_3 ON col_3.col_1 = col_11.col_1 INNER JOIN tbl_3 AS col_5 ON col_5.col_6 = col_3.col_6 LEFT JOIN tbl_4 AS col_8 ON col_5.col_6 = col_8.col_6 WHERE col_3.col_1 = v_col_1 AND (col_8.col_6 IS NULL OR (col_8.col_12 = 1 AND col_8.col_13 = col_11.col_13)) UNION ALL SELECT v_col_1 AS col_1, 0 AS col_4, NULL AS col_6, NULL AS col_7, NULL AS col_9, NULL AS col_10) AS col_14 ORDER BY col_4 DESC LIMIT 1;
END$$
DELIMITER ;

-- SET QUOTED_IDENTIFIER OFF
-- SET ANSI_NULLS ON
-- -- xxx xxxxxx xxxxxx xxxxxx

-- -- xxxxxx xxxxxx xxxxxx 

-- IF OBJECT_ID(N'[dbo].[proc_2]', 'P') IS NULL
--     EXEC ('CREATE PROCEDURE [dbo].[proc_2] AS SELECT 1')
-- SET QUOTED_IDENTIFIER ON
-- SET ANSI_NULLS ON
DELIMITER $$
CREATE PROCEDURE proc_2
(
    IN v_col_1 INT,
    IN v_col_4 INT,
    IN v_col_15 VARCHAR(10),
    IN v_col_2 INT
)
BEGIN
    DECLARE v_func1 DATETIME DEFAULT func1();
    DECLARE v_col_6 CHAR(36) DEFAULT NULL;

    /* UNIQUE: SET NOCOUNT ON -- no mysql equivalent */
    CREATE TEMPORARY TABLE v_col_16 (
      col_17 CHAR(36)
    );  /* UNIQUE: was T-SQL table variable v_col_16 */
    IF ( v_col_2 IS NOT NULL ) THEN
            /* UNIQUE: SET ROWCOUNT v_col_2 -- no mysql equivalent */
            DO 0;
    END IF;
    IF ( v_col_1 IS NOT NULL ) THEN
            UPDATE tbl_2 SET col_4 = v_col_4, col_15 = v_col_15, col_18 = v_func1 WHERE col_1 = v_col_1 AND col_4 <> v_col_4;
            SET v_col_6 = ( SELECT MAX ( col_6 ) FROM tbl_2 where col_1 = v_col_1 );
            IF v_col_6 IS NULL THEN
                        INSERT INTO tbl_3 (col_19, col_20, col_15, col_18) SELECT v_col_15, v_func1, v_col_15, v_func1 WHERE NOT EXISTS(SELECT NULL FROM tbl_2 WHERE col_1 = v_col_1);
                        -- UNIQUE: MySQL has no RETURNING/OUTPUT; the original statement returned: inserted.col_6;
                        SET v_col_6 = ( SELECT MAX ( col_17 ) FROM v_col_16 );
                        INSERT INTO tbl_2 (col_1, col_4, col_6, col_19, col_20, col_15, col_18) SELECT v_col_1, v_col_4, v_col_6, v_col_15, v_func1, v_col_15, v_func1 WHERE NOT EXISTS(SELECT NULL FROM tbl_2 WHERE col_1 = v_col_1);
            END IF;
    END IF;
    SELECT LOWER(CAST(v_col_6 AS CHAR(36))) AS col_21;
END$$
DELIMITER ;

-- SET QUOTED_IDENTIFIER OFF
-- SET ANSI_NULLS ON
-- -- xxx xxxxxx xxxxxx xxxxxx

-- -- xxxxxx xxxxxx xxxxxx 

-- IF OBJECT_ID(N'[dbo].[proc_3]', 'P') IS NULL
--     EXEC ('CREATE PROCEDURE [dbo].[proc_3] AS SELECT 1')
-- SET QUOTED_IDENTIFIER ON
-- SET ANSI_NULLS ON
DELIMITER $$
CREATE PROCEDURE proc_3
(
    IN v_col_2 INT
)
BEGIN
    /* UNIQUE: SET NOCOUNT ON -- no mysql equivalent */
    IF ( v_col_2 IS NOT NULL ) THEN
            /* UNIQUE: SET ROWCOUNT v_col_2 -- no mysql equivalent */
            DO 0;
    END IF;
    SELECT col_22.col_23, col_22.col_24 AS col_25, col_22.col_26 AS col_27, CAST(NULL AS CHAR) AS value, col_22.col_28 AS col_29 FROM tbl_5 AS col_22 WHERE col_22.col_30 = 1 ORDER BY col_22.col_28 ASC;
END$$
DELIMITER ;

-- SET QUOTED_IDENTIFIER OFF
-- SET ANSI_NULLS ON
-- -- xxx xxxxxx xxxxxx xxxxxx

-- -- xxxxxx xxxxxx xxxxxx 

-- IF OBJECT_ID(N'[dbo].[proc_4]', 'P') IS NULL
--     EXEC ('CREATE PROCEDURE [dbo].[proc_4] AS SELECT 1')
-- SET QUOTED_IDENTIFIER ON
-- SET ANSI_NULLS ON
DELIMITER $$
CREATE PROCEDURE proc_4
(
    IN v_col_31 INT,
    IN v_col_2 INT
)
BEGIN
    DECLARE v_func1 DATETIME DEFAULT func1();

    /* UNIQUE: SET NOCOUNT ON -- no mysql equivalent */
    IF ( v_col_2 IS NOT NULL ) THEN
            /* UNIQUE: SET ROWCOUNT v_col_2 -- no mysql equivalent */
            DO 0;
    END IF;
    UPDATE tbl_6 SET col_32 = 1, col_18 = v_func1 WHERE col_31 = v_col_31 AND col_32 = 0 AND NOT EXISTS(SELECT NULL FROM tbl_7 WHERE col_31 = v_col_31);
    UPDATE tbl_6 SET col_33 = v_func1 WHERE col_31 = v_col_31 AND NOT EXISTS(SELECT NULL FROM tbl_7 WHERE col_31 = v_col_31);
    SELECT col_32, col_34, col_35, col_36 FROM (SELECT 1 AS col_32, col_37.col_38 AS col_34, CAST(NULL AS CHAR) AS col_35, COALESCE((SELECT 1 FROM tbl_8 WHERE col_31 = v_col_31 AND col_39 = 3 /* xxxxxx xx xx xxxxxx */ LIMIT 1), 0) AS col_36 FROM tbl_6 AS col_37 INNER JOIN tbl_8 AS col_40 ON col_40.col_31 IN (SELECT col_31 FROM tbl_6 AS col_41 WHERE col_41.col_6 = col_37.col_6 AND col_32 = 1 AND col_42 = 1 /* xxxxxx */) AND col_40.col_39 = 3 /* xxxxxx xx xx xxxxxx */ WHERE col_37.col_31 = v_col_31 AND NOT EXISTS(SELECT NULL FROM tbl_7 WHERE col_31 = v_col_31 /* xx xx xx xxxxxx xx col_161 */ AND EXISTS(SELECT NULL FROM tbl_9 WHERE col_30 = 1 AND NOT col_43 IS NULL)) UNION ALL SELECT 0 AS col_32, CAST(NULL AS CHAR) AS col_34, CAST(NULL AS CHAR) AS col_35, 0 AS col_36) AS col_44 ORDER BY col_32 DESC LIMIT 1;
END$$
DELIMITER ;

-- SET QUOTED_IDENTIFIER OFF
-- SET ANSI_NULLS ON
-- -- xxx xxxxxx xxxxxx xxxxxx

-- -- xxxxxx xxxxxx xxxxxx 

-- IF OBJECT_ID(N'[dbo].[proc_5]', 'P') IS NULL
--     EXEC ('CREATE PROCEDURE [dbo].[proc_5] AS SELECT 1')
-- SET QUOTED_IDENTIFIER ON
-- SET ANSI_NULLS ON
DELIMITER $$
CREATE PROCEDURE proc_5
(
    IN v_col_31 INT,
    IN v_col_2 INT
)
BEGIN
    /* UNIQUE: SET NOCOUNT ON -- no mysql equivalent */
    IF ( v_col_2 IS NOT NULL ) THEN
            /* UNIQUE: SET ROWCOUNT v_col_2 -- no mysql equivalent */
            DO 0;
    END IF;
    SELECT col_45.col_46 AS col_47, col_45.col_48 AS col_49, col_11.col_50 AS col_51, col_52.col_46 AS col_53, COALESCE((SELECT 1 FROM tbl_8 WHERE col_31 = v_col_31 AND col_39 = 1 /* xxxxxx xx xx col_6 xx xxxxxx */ ORDER BY col_31 ASC LIMIT 1), 0) AS col_54, COALESCE((SELECT 1 FROM tbl_7 WHERE col_31 = v_col_31 /* xx xx xx xxxxxx xx col_161 */ AND EXISTS(SELECT NULL FROM tbl_9 WHERE col_30 = 1 AND NOT col_43 IS NULL) ORDER BY col_31 ASC LIMIT 1), 0) AS col_55 FROM tbl_6 AS col_37 INNER JOIN tbl_2 AS col_56 ON col_37.col_6 = col_56.col_6 INNER JOIN tbl_1 AS col_11 ON col_56.col_1 = col_11.col_1 INNER JOIN tbl_10 AS col_45 ON col_11.col_13 = col_45.col_13 INNER JOIN tbl_11 AS col_57 ON col_11.col_58 = col_57.col_59 INNER JOIN tbl_12 AS col_52 ON col_57.col_60 = col_52.col_59 WHERE col_37.col_31 = v_col_31;
END$$
DELIMITER ;

-- SET QUOTED_IDENTIFIER OFF
-- SET ANSI_NULLS ON
-- -- xxx xxxxxx xxxxxx xxxxxx

-- -- xxxxxx xxxxxx xxxxxx 

-- IF OBJECT_ID(N'[dbo].[proc_6]', 'P') IS NULL
--     EXEC ('CREATE PROCEDURE [dbo].[proc_6] AS SELECT 1')
-- SET QUOTED_IDENTIFIER ON
-- SET ANSI_NULLS ON
DELIMITER $$
CREATE PROCEDURE proc_6
(
    IN v_col_61 LONGTEXT,
    IN v_col_6 CHAR(36),
    IN v_col_42 INT,
    IN v_col_62 VARCHAR(50),
    IN v_col_13 INT,
    IN v_col_63 VARCHAR(1000),
    IN v_col_9 VARCHAR(200),
    IN v_col_10 VARCHAR(200),
    IN v_col_64 LONGTEXT,
    IN v_col_15 VARCHAR(50),
    IN v_col_2 INT
)
proc_exit: BEGIN
    DECLARE v_func1 DATETIME DEFAULT func1();
    DECLARE v_col_65 INT DEFAULT COALESCE ( ( SELECT TOP ( 1 ) col_65 FROM tbl_9 WHERE col_30 = 1 order by col_66 desc ) , - 1440 );
    DECLARE v_col_67 INT DEFAULT COALESCE ( ( SELECT TOP ( 1 ) col_67 FROM tbl_9 WHERE col_30 = 1 order by col_66 desc ) , 1440 );
    DECLARE v_col_68 DATETIME;
    DECLARE v_col_69 DATETIME;
    DECLARE v_col_70 DATETIME;
    DECLARE v_col_71 VARCHAR(36) DEFAULT LOWER(CAST(v_col_6 AS CHAR(36)));
    DECLARE v_col_72 VARCHAR(200) DEFAULT NULL;
    DECLARE v_col_73 VARCHAR(200) DEFAULT NULL;
    DECLARE v_col_74 LONGTEXT DEFAULT NULL;
    DECLARE v_col_32 INT DEFAULT 0;
    DECLARE v_col_75 VARCHAR(50) DEFAULT NULL;
    DECLARE v_col_17 INT DEFAULT NULL;
    DECLARE v_col_12 INT DEFAULT NULL;

    /* UNIQUE: SET NOCOUNT ON -- no mysql equivalent */
    IF ( v_col_2 IS NOT NULL ) THEN
            /* UNIQUE: SET ROWCOUNT v_col_2 -- no mysql equivalent */
            DO 0;
    END IF;
    IF ( ( v_col_6 IS NULL ) OR ( v_col_42 IS NULL ) ) THEN
            LEAVE proc_exit;  -- UNIQUE: discarded procedure RETURN value (NULL)
    END IF;
    SET v_col_12 = ( SELECT CASE WHEN v_col_42 = 1 THEN 2 /* xxxxxx */ WHEN v_col_42 = 0 AND v_col_13 IS NOT NULL THEN 1 /* col_151 */ ELSE 0 END ) /* xxxxxx */ /* xx xx xx xxxxxx */;
    IF v_col_12 = 2 THEN
            DELETE FROM tbl_6 WHERE col_6 = v_col_6 AND col_42 = 1 AND col_62 = v_col_62;
            SELECT col_76.col_46, LOWER(COALESCE(col_76.col_77, CONCAT(v_col_62, '@', v_col_61))) INTO v_col_72, v_col_73 FROM tbl_13 col_76 WHERE col_76 . col_62 = v_col_62;
    END IF;
    -- xx xx xx xxxxxx
    IF v_col_12 = 1 THEN
            DELETE FROM tbl_6 WHERE col_6 = v_col_6 AND col_42 = 0 AND col_13 = v_col_13;
            SELECT col_45.col_46, LOWER(COALESCE(col_45.col_73, CONCAT(CAST(col_45.col_13 AS CHAR(50)), '@', v_col_61))) INTO v_col_72, v_col_73 FROM tbl_2 col_3 INNER JOIN tbl_1 col_11 ON col_11 . col_1 = col_3 . col_1 INNER JOIN tbl_10 col_45 ON col_45 . col_13 = col_11 . col_13 WHERE col_3 . col_6 = v_col_6;
    END IF;
    -- xx xx xx xxxxxx
    IF v_col_12 = 0 THEN
            DELETE FROM tbl_6 WHERE col_6 = v_col_6 AND col_42 = 0 AND col_62 = v_col_62 AND col_13 IS NULL;
            SELECT v_col_62, LOWER(CONCAT(v_col_62, '@', v_col_61)) INTO v_col_72, v_col_73 ;
    END IF;
    SELECT col_11 . col_50 INTO v_col_68 FROM tbl_2 col_3 INNER JOIN tbl_1 col_11 ON col_11 . col_1 = col_3 . col_1 WHERE col_3 . col_6 = v_col_6;
    -- xxxxxx xx xxxxxx xxx xxxxxx
    SET v_col_69 = DATE_ADD(v_col_68, INTERVAL v_col_65 MINUTE);
    SET v_col_70 = DATE_ADD(v_col_68, INTERVAL v_col_67 MINUTE);
    INSERT INTO tbl_6 (col_12, col_62, col_13, col_19, col_20, col_15, col_18, col_6, col_72, col_73, col_63, col_42, col_74, col_32, col_9, col_10) VALUES (v_col_12, v_col_62, v_col_13, v_col_15, v_func1, v_col_15, v_func1, v_col_6, v_col_72, v_col_73, v_col_63, v_col_42, '-', v_col_32, v_col_9, v_col_10);
    -- xx xxxxxx xxx xxxxxx xxxx xx xxxxxx xxxxx xxx xxxxxx xx xx xxxxx
    SET v_col_17 = LAST_INSERT_ID();
    SET v_col_75 = CAST(v_col_17 AS CHAR(20));
    IF ( v_col_64 IS NULL ) THEN
            SET v_col_74 = func2(v_col_61, v_col_69, v_col_70, v_col_75, v_col_71, v_col_72, v_col_73, v_col_63, v_col_42);
    ELSE
            SET v_col_74 = v_col_64;
    END IF;
    IF ( COALESCE ( v_col_74 , 'xxxxxxx-xxxx' ) = 'xxxxxxx-xxxx' ) THEN
            DELETE FROM tbl_6 WHERE col_31 = v_col_17;
    ELSE
            UPDATE tbl_6 SET col_74 = v_col_74 WHERE col_31 = v_col_17;
    END IF;
    SELECT col_31, col_74 FROM tbl_6 WHERE col_31 = v_col_17;
END$$
DELIMITER ;

-- SET QUOTED_IDENTIFIER OFF
-- SET ANSI_NULLS ON
-- -- xxx xxxxxx xxxxxx xxxxxx

-- -- xxxxxx xxxxxx xxxxx 

-- IF OBJECT_ID(N'[dbo].[func2]') IS NULL
--     EXEC('CREATE FUNCTION [dbo].[func2] () RETURNS VARCHAR AS BEGIN RETURN NULL END')
-- SET QUOTED_IDENTIFIER ON
-- SET ANSI_NULLS ON
DELIMITER $$
CREATE FUNCTION func2
(
    v_col_61 LONGTEXT,
    v_col_69 DATETIME,
    v_col_70 DATETIME,
    v_col_62 VARCHAR(50),
    v_col_6 VARCHAR(1000),
    v_col_72 VARCHAR(200),
    v_col_73 VARCHAR(200),
    v_col_63 VARCHAR(1000),
    v_col_42 INT
)
RETURNS VARCHAR(4000)
DETERMINISTIC
BEGIN
    DECLARE v_func1 DATETIME;
    DECLARE v_col_79 LONGTEXT;
    DECLARE v_col_80 LONGTEXT;
    DECLARE v_mod VARCHAR(10);
    DECLARE v_col_74 LONGTEXT;
    DECLARE v_col_81 VARCHAR(1000);
    DECLARE v_col_82 DATETIME;
    DECLARE v_col_83 VARCHAR(500);
    DECLARE v_col_84 VARCHAR(500);
    DECLARE v_col_75 VARCHAR(50);
    DECLARE v_col_85 BIGINT;
    DECLARE v_col_86 BIGINT;
    DECLARE v_col_87 BIGINT;
    DECLARE v_col_88 VARCHAR(50);

    -- xxxxxx
    SET v_func1 = func1();
    SELECT col_79, col_89, col_90, col_80 INTO v_col_79, v_col_83, v_col_84, v_col_80 FROM tbl_9 WHERE col_61 = v_col_61 AND col_30 = 1;
    IF ( v_col_79 IS NULL OR v_col_62 IS NULL OR v_col_69 IS NULL OR v_col_70 IS NULL OR v_col_6 IS NULL ) THEN
            RETURN 'xxxxxxx-xxxx';
    END IF;
    SET v_col_75 = 'xxxx.xxxxx';
    SET v_mod = CASE WHEN COALESCE ( v_col_42 , 0 ) = 1 THEN 'xxxx' ELSE 'xxxxx' END;
    SET v_col_88 = REPLACE ( COALESCE ( v_col_62 , '' ) , '"' , '' );
    SET v_col_81 = COALESCE(func3('xxxxxxxxxxx', '/'), '/');
    IF ( SUBSTRING ( v_col_81 , CHAR_LENGTH ( v_col_81 ) , 1 ) <> '/' ) THEN
            SET v_col_81 = CONCAT(v_col_81, '/');
    END IF;
    SET v_col_80 = REPLACE ( v_col_80 , '~/' , v_col_81 );
    SET v_col_63 = REPLACE ( COALESCE ( v_col_63 , REPLACE ( v_col_80 , '{x}' , v_col_75 ) ) , '"' , '' );
    SET v_col_72 = REPLACE ( COALESCE ( v_col_72 , v_col_75 ) , '"' , '' );
    SET v_col_73 = REPLACE(COALESCE(v_col_73, CONCAT(v_col_75, '@', v_col_61)), '"', '');
    SET v_col_82 = STR_TO_DATE('xxxx-xx-xx xx:xx:xx', '%Y-%m-%d %T');
    SET v_col_85 = TIMESTAMPDIFF(SECOND, v_col_82, v_func1);
    SET v_col_86 = TIMESTAMPDIFF(SECOND, v_col_82, COALESCE ( v_col_69 , v_func1 ));
    SET v_col_87 = TIMESTAMPDIFF(SECOND, v_col_82, COALESCE(v_col_70, v_func1 + 1));
    SET v_col_74 = '{
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
    }';
    SET v_col_74 = REPLACE ( v_col_74 , '$xxxxxx$' , v_col_63 );
    SET v_col_74 = REPLACE ( v_col_74 , '$xxxx$' , v_col_72 );
    SET v_col_74 = REPLACE ( v_col_74 , '$xxxxx$' , v_col_73 );
    SET v_col_74 = REPLACE(v_col_74, '$xxx$', CAST(v_col_85 AS CHAR(50)));
    SET v_col_74 = REPLACE(v_col_74, '$xxx$', CAST(v_col_86 AS CHAR(50)));
    SET v_col_74 = REPLACE(v_col_74, '$xxx$', CAST(v_col_87 AS CHAR(50)));
    SET v_col_74 = REPLACE ( v_col_74 , '$xxx$' , v_col_84 );
    SET v_col_74 = REPLACE ( v_col_74 , '$xxx$' , v_col_83 );
    SET v_col_74 = REPLACE ( v_col_74 , '$xxxxxxxxx$' , v_col_88 );
    SET v_col_74 = REPLACE ( v_col_74 , '$xxx$' , v_col_75 );
    SET v_col_74 = REPLACE ( v_col_74 , '$xxxx$' , v_col_6 );
    SET v_col_74 = REPLACE ( v_col_74 , '$xxxxxxxxx$' , v_mod ) /* xxxxxx xx xxxxxx xxx xxxx */;
    SET v_col_74 = REPLACE ( v_col_74 , CHAR ( 13 ) , '' );
    SET v_col_74 = REPLACE ( v_col_74 , CHAR ( 10 ) , '' );
    SET v_col_74 = REPLACE ( v_col_74 , '    ' , ' ' );
    SET v_col_74 = REPLACE ( v_col_74 , '  ' , ' ' );
    SET v_col_74 = REPLACE ( v_col_74 , '  ' , ' ' );
    SET v_col_74 = REPLACE ( v_col_74 , '{ ' , '{' );
    SET v_col_74 = REPLACE ( v_col_74 , '} ' , '}' );
    SET v_col_74 = REPLACE ( v_col_74 , ': ' , ':' );
    SET v_col_74 = REPLACE ( v_col_74 , ', "' , ',"' );
    SET v_col_74 = REPLACE ( v_col_74 , ' "' , '"' );
    SET v_col_74 = REPLACE ( v_col_74 , '" ' , '"' );
    RETURN func4(v_col_74, v_col_79);
END$$
DELIMITER ;

-- SET QUOTED_IDENTIFIER OFF
-- SET ANSI_NULLS ON
-- -- xxx xxxxxx xxxxxx xxxxx

-- -- xxxxxx xxxxxx xxxxxx 

-- IF OBJECT_ID(N'[dbo].[proc_7]', 'P') IS NULL
--     EXEC ('CREATE PROCEDURE [dbo].[proc_7] AS SELECT 1')
-- SET QUOTED_IDENTIFIER ON
-- SET ANSI_NULLS ON
DELIMITER $$
CREATE PROCEDURE proc_7
(
    OUT v_col_6 CHAR(36),
    IN v_col_7 INT,
    IN v_col_91 VARCHAR(4000),
    IN v_col_19 VARCHAR(10),
    IN v_col_20 DATETIME,
    IN v_col_15 VARCHAR(10),
    IN v_col_18 DATETIME
)
BEGIN
    /* UNIQUE: SET NOCOUNT ON -- no mysql equivalent */
    CREATE TEMPORARY TABLE v_col_92 (
      col_17 CHAR(36)
    );  /* UNIQUE: was T-SQL table variable v_col_92 */
    INSERT INTO tbl_3 (col_7, col_91, col_19, col_20, col_15, col_18) VALUES (v_col_7, v_col_91, v_col_19, v_col_20, v_col_15, v_col_18);
    -- UNIQUE: MySQL has no RETURNING/OUTPUT; the original statement returned: inserted.col_6;
    SET v_col_6 = ( SELECT MAX ( col_17 ) FROM v_col_92 );
END$$
DELIMITER ;

-- SET QUOTED_IDENTIFIER OFF
-- SET ANSI_NULLS ON
-- -- xxx xxxxxx xxxxxx xxxxxx

-- -- xxxxxx xxxxxx xxxxxx 

-- IF OBJECT_ID(N'[dbo].[proc_8]', 'P') IS NULL
--     EXEC ('CREATE PROCEDURE [dbo].[proc_8] AS SELECT 1')
-- SET QUOTED_IDENTIFIER ON
-- SET ANSI_NULLS ON
DELIMITER $$
CREATE PROCEDURE proc_8
(
    OUT v_col_93 INT,
    IN v_col_15 VARCHAR(10),
    IN v_col_18 DATETIME,
    IN v_col_31 INT,
    IN v_col_39 INT,
    IN v_col_94 DATETIME
)
BEGIN
    /* UNIQUE: SET NOCOUNT ON -- no mysql equivalent */
    CREATE TEMPORARY TABLE v_col_92 (
      col_17 INT
    );  /* UNIQUE: was T-SQL table variable v_col_92 */
    INSERT INTO tbl_8 (col_15, col_18, col_31, col_39, col_94) VALUES (v_col_15, v_col_18, v_col_31, v_col_39, v_col_94);
    -- UNIQUE: MySQL has no RETURNING/OUTPUT; the original statement returned: inserted.col_93;
    SET v_col_93 = ( SELECT MAX ( col_17 ) FROM v_col_92 );
END$$
DELIMITER ;

-- SET QUOTED_IDENTIFIER OFF
-- SET ANSI_NULLS ON
-- -- xxx xxxxxx xxxxxx xxxxxx

-- -- xxxxxx xxxxxx xxxxxx 

-- IF OBJECT_ID(N'[dbo].[proc_9]', 'P') IS NULL
--     EXEC ('CREATE PROCEDURE [dbo].[proc_9] AS SELECT 1')
-- SET QUOTED_IDENTIFIER ON
-- SET ANSI_NULLS ON
DELIMITER $$
CREATE PROCEDURE proc_9
(
    OUT v_col_31 INT,
    IN v_col_6 CHAR(36),
    IN v_col_32 INT,
    IN v_col_33 DATETIME,
    IN v_col_12 INT,
    IN v_col_42 INT,
    IN v_col_62 VARCHAR(10),
    IN v_col_13 INT,
    IN v_col_9 VARCHAR(200),
    IN v_col_10 VARCHAR(200),
    IN v_col_74 LONGTEXT,
    IN v_col_38 LONGTEXT,
    IN v_col_95 LONGTEXT,
    IN v_col_96 LONGTEXT,
    IN v_col_72 VARCHAR(200),
    IN v_col_73 VARCHAR(200),
    IN v_col_63 VARCHAR(1000),
    IN v_col_19 VARCHAR(10),
    IN v_col_20 DATETIME,
    IN v_col_15 VARCHAR(10),
    IN v_col_18 DATETIME
)
BEGIN
    /* UNIQUE: SET NOCOUNT ON -- no mysql equivalent */
    CREATE TEMPORARY TABLE v_col_92 (
      col_17 INT
    );  /* UNIQUE: was T-SQL table variable v_col_92 */
    INSERT INTO tbl_6 (col_6, col_32, col_33, col_12, col_42, col_62, col_13, col_9, col_10, col_74, col_38, col_95, col_96, col_72, col_73, col_63, col_19, col_20, col_15, col_18) VALUES (v_col_6, v_col_32, v_col_33, v_col_12, v_col_42, v_col_62, v_col_13, v_col_9, v_col_10, v_col_74, v_col_38, v_col_95, v_col_96, v_col_72, v_col_73, v_col_63, v_col_19, v_col_20, v_col_15, v_col_18);
    -- UNIQUE: MySQL has no RETURNING/OUTPUT; the original statement returned: inserted.col_31;
    SET v_col_31 = ( SELECT MAX ( col_17 ) FROM v_col_92 );
END$$
DELIMITER ;

-- SET QUOTED_IDENTIFIER OFF
-- SET ANSI_NULLS ON
-- -- xxx xxxxxx xxxxxx xxxxxx

-- -- xxxxxx xxxxxx xxxxxx 

-- IF OBJECT_ID(N'[dbo].[proc_10]', 'P') IS NULL
--     EXEC ('CREATE PROCEDURE [dbo].[proc_10] AS SELECT 1')
-- SET QUOTED_IDENTIFIER ON
-- SET ANSI_NULLS ON
DELIMITER $$
CREATE PROCEDURE proc_10
(
    IN v_col_97 INT,
    IN v_col_31 INT,
    IN v_col_23 INT,
    IN v_col_15 VARCHAR(10),
    IN v_col_18 DATETIME,
    IN v_col_98 INT,
    IN v_col_99 LONGTEXT,
    IN v_col_100 INT,
    IN v_col_101 INT,
    IN v_col_102 INT,
    IN v_col_103 VARCHAR(10),
    IN v_col_104 DATETIME,
    IN v_col_105 INT,
    IN v_col_106 LONGTEXT
)
BEGIN
    /* UNIQUE: SET NOCOUNT ON -- no mysql equivalent */
    UPDATE tbl_7 SET col_15 = v_col_15, col_18 = v_col_18, col_98 = v_col_98, col_99 = v_col_99 WHERE (col_97 = v_col_100) AND (col_31 = v_col_101) AND (col_23 = v_col_102) AND ((col_15 = v_col_103) OR (col_15 IS NULL AND v_col_103 IS NULL)) AND ((col_18 = v_col_104) OR (col_18 IS NULL AND v_col_104 IS NULL)) AND ((col_98 = v_col_105) OR (col_98 IS NULL AND v_col_105 IS NULL)) AND ((col_99 = v_col_106) OR (col_99 IS NULL AND v_col_106 IS NULL));
    -- xx xx xx xxxxxx xx xxxxxx xxxxxx xxxxx
    IF ROW_COUNT() <> 1 THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Application error', MYSQL_ERRNO = 16947;  -- UNIQUE: original RAISERROR/THROW severity/state args dropped: 16 , 1
    END IF;
    -- xxxxxx xx xxxxxx xxxx xx xxxxx xxxxxx
    IF v_col_97 IS NULL OR v_col_31 IS NULL OR v_col_23 IS NULL THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Application error', MYSQL_ERRNO = 40302;  -- UNIQUE: original RAISERROR/THROW severity/state args dropped: 16 , 1
    END IF;
END$$
DELIMITER ;

-- SET QUOTED_IDENTIFIER OFF
-- SET ANSI_NULLS ON
-- -- xxx xxxxxx xxxxxx xxxxxx

-- -- xxxxxx xxxxxx xxxxxx 

-- IF OBJECT_ID(N'[dbo].[proc_11]', 'P') IS NULL
--     EXEC ('CREATE PROCEDURE [dbo].[proc_11] AS SELECT 1')
-- SET QUOTED_IDENTIFIER ON
-- SET ANSI_NULLS ON
DELIMITER $$
CREATE PROCEDURE proc_11
(
    IN v_col_97 INT,
    IN v_col_31 INT,
    IN v_col_23 INT,
    IN v_col_15 VARCHAR(10),
    IN v_col_18 DATETIME,
    IN v_col_98 INT,
    IN v_col_99 LONGTEXT
)
BEGIN
    /* UNIQUE: SET NOCOUNT ON -- no mysql equivalent */
    INSERT INTO tbl_7 (col_97, col_31, col_23, col_15, col_18, col_98, col_99) VALUES (v_col_97, v_col_31, v_col_23, v_col_15, v_col_18, v_col_98, v_col_99);
END$$
DELIMITER ;

-- SET QUOTED_IDENTIFIER OFF
-- SET ANSI_NULLS ON
-- -- xxx xxxxxx xxxxxx xxxxxx

-- -- xxxxxx xxxxxx xxxxxx 

-- IF OBJECT_ID(N'[dbo].[proc_12]', 'P') IS NULL
--     EXEC ('CREATE PROCEDURE [dbo].[proc_12] AS SELECT 1')
-- SET QUOTED_IDENTIFIER ON
-- SET ANSI_NULLS ON
DELIMITER $$
CREATE PROCEDURE proc_12
(
    IN v_col_97 INT,
    IN v_col_31 INT,
    IN v_col_23 INT,
    IN v_col_15 VARCHAR(10),
    IN v_col_18 DATETIME,
    IN v_col_98 INT,
    IN v_col_99 LONGTEXT,
    IN v_col_107 LONGTEXT,
    IN v_col_2 INT
)
BEGIN
    /* UNIQUE: SET NOCOUNT ON -- no mysql equivalent */
    DECLARE v_col_108 LONGTEXT;
    DECLARE v_col_109 LONGTEXT;
    DECLARE v_col_110 LONGTEXT;
    IF ( v_col_2 IS NOT NULL ) THEN
            /* UNIQUE: SET ROWCOUNT v_col_2 -- no mysql equivalent */
            DO 0;
    END IF;
    IF v_col_97 IS NOT NULL AND v_col_31 IS NOT NULL AND v_col_23 IS NOT NULL AND v_col_107 IS NULL THEN
            SELECT col_97, col_31, col_23, col_15, col_18, col_98, col_99 FROM tbl_7 WHERE (v_col_97 = col_97) AND (v_col_31 = col_31) AND (v_col_23 = col_23) AND (col_97 = v_col_97 OR v_col_97 IS NULL) AND (col_31 = v_col_31 OR v_col_31 IS NULL) AND (col_23 = v_col_23 OR v_col_23 IS NULL) AND (col_15 = v_col_15 OR v_col_15 IS NULL) AND (col_18 = v_col_18 OR v_col_18 IS NULL) AND (col_98 = v_col_98 OR v_col_98 IS NULL) AND (col_99 = v_col_99 OR v_col_99 IS NULL);
    ELSE
            SET v_col_109 = '
                        SELECT col_97, col_31, col_23, col_15, col_18, col_98, col_99
                        FROM tbl_7';
            CALL proc_13(v_col_110, 'xxxxxxxxxxxxxxxx', '=', 'v_xxxxxxxxxxxxxxxx', v_col_97);
            CALL proc_13(v_col_110, 'xxxxxxxxxxxxx', '=', 'v_xxxxxxxxxxxxx', v_col_31);
            CALL proc_13(v_col_110, 'xxxxxxxxxxxxxxx', '=', 'v_xxxxxxxxxxxxxxx', v_col_23);
            CALL proc_13(v_col_110, 'xxxxxxxxxx', '=', 'v_xxxxxxxxxx', v_col_15);
            CALL proc_13(v_col_110, 'xxxxxxxx', '=', 'v_xxxxxxxx', v_col_18);
            CALL proc_13(v_col_110, 'xxxxx', '=', 'v_xxxxx', v_col_98);
            CALL proc_13(v_col_110, 'xxxxxxxxx', '=', 'v_xxxxxxxxx', v_col_99);
            IF v_col_110 IS NOT NULL THEN
                        SET v_col_109 = CONCAT(v_col_109, ' WHERE ', v_col_110);
            END IF;
            CALL proc_14(v_col_109, v_col_107, v_col_108);
            SET @_stmt = v_col_109; PREPARE _dyn FROM @_stmt; EXECUTE _dyn; DEALLOCATE PREPARE _dyn; -- UNIQUE: sp_executesql parameter declarations/bindings dropped; pass them via PREPARE ... USING manually
    END IF;
END$$
DELIMITER ;

-- SET QUOTED_IDENTIFIER OFF
-- SET ANSI_NULLS ON
-- -- xxx xxxxxx xxxxxx xxxxxx

-- -- xxxxxx xxxxxx xxxxxx 

-- IF OBJECT_ID(N'[dbo].[proc_15]', 'P') IS NULL
--     EXEC ('CREATE PROCEDURE [dbo].[proc_15] AS SELECT 1')
-- SET QUOTED_IDENTIFIER ON
-- SET ANSI_NULLS ON
DELIMITER $$
CREATE PROCEDURE proc_15
(
    IN v_col_100 INT,
    IN v_col_101 INT,
    IN v_col_102 INT,
    IN v_col_103 VARCHAR(10),
    IN v_col_104 DATETIME,
    IN v_col_105 INT,
    IN v_col_106 LONGTEXT
)
BEGIN
    /* UNIQUE: SET NOCOUNT ON -- no mysql equivalent */
    DELETE FROM tbl_7 WHERE (col_97 = v_col_100) AND (col_31 = v_col_101) AND (col_23 = v_col_102) AND ((col_15 = v_col_103) OR (col_15 IS NULL AND v_col_103 IS NULL)) AND ((col_18 = v_col_104) OR (col_18 IS NULL AND v_col_104 IS NULL)) AND ((col_98 = v_col_105) OR (col_98 IS NULL AND v_col_105 IS NULL)) AND ((col_99 = v_col_106) OR (col_99 IS NULL AND v_col_106 IS NULL));
    -- xx xx xx xxxxxx xx xxxxxx xxxxxx xxxxx
    IF ROW_COUNT() <> 1 THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Application error', MYSQL_ERRNO = 16947;  -- UNIQUE: original RAISERROR/THROW severity/state args dropped: 16 , 1
    END IF;
END$$
DELIMITER ;

-- SET QUOTED_IDENTIFIER OFF
-- SET ANSI_NULLS ON
-- -- xxx xxxxxx xxxxxx xxxxxx

-- -- xxxxxx xxxxxx xxxxxx 

-- IF OBJECT_ID(N'[dbo].[proc_16]', 'P') IS NULL
--     EXEC ('CREATE PROCEDURE [dbo].[proc_16] AS SELECT 1')
-- SET QUOTED_IDENTIFIER ON
-- SET ANSI_NULLS ON
DELIMITER $$
CREATE PROCEDURE proc_16
(
    IN v_col_93 INT,
    IN v_col_15 VARCHAR(10),
    IN v_col_18 DATETIME,
    IN v_col_31 INT,
    IN v_col_39 INT,
    IN v_col_94 DATETIME,
    IN v_col_112 INT,
    IN v_col_103 VARCHAR(10),
    IN v_col_104 DATETIME,
    IN v_col_101 INT,
    IN v_col_113 INT,
    IN v_col_114 DATETIME
)
BEGIN
    /* UNIQUE: SET NOCOUNT ON -- no mysql equivalent */
    UPDATE tbl_8 SET col_15 = v_col_15, col_18 = v_col_18, col_31 = v_col_31, col_39 = v_col_39, col_94 = v_col_94 WHERE (col_93 = v_col_112) AND ((col_15 = v_col_103) OR (col_15 IS NULL AND v_col_103 IS NULL)) AND ((col_18 = v_col_104) OR (col_18 IS NULL AND v_col_104 IS NULL)) AND ((col_31 = v_col_101) OR (col_31 IS NULL AND v_col_101 IS NULL)) AND ((col_39 = v_col_113) OR (col_39 IS NULL AND v_col_113 IS NULL)) AND ((col_94 = v_col_114) OR (col_94 IS NULL AND v_col_114 IS NULL));
    -- xx xx xx xxxxxx xx xxxxxx xxxxxx xxxxx
    IF ROW_COUNT() <> 1 THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Application error', MYSQL_ERRNO = 16947;  -- UNIQUE: original RAISERROR/THROW severity/state args dropped: 16 , 1
    END IF;
    -- xxxxxx xx xxxxxx xxxx xx xxxxx xxxxxx
    IF v_col_93 IS NULL THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Application error', MYSQL_ERRNO = 40302;  -- UNIQUE: original RAISERROR/THROW severity/state args dropped: 16 , 1
    END IF;
END$$
DELIMITER ;

-- SET QUOTED_IDENTIFIER OFF
-- SET ANSI_NULLS ON
-- -- xxx xxxxxx xxxxxx xxxxxx

-- -- xxxxxx xxxxxx xxxxxx 

-- IF OBJECT_ID(N'[dbo].[proc_17]', 'P') IS NULL
--     EXEC ('CREATE PROCEDURE [dbo].[proc_17] AS SELECT 1')
-- SET QUOTED_IDENTIFIER ON
-- SET ANSI_NULLS ON
DELIMITER $$
CREATE PROCEDURE proc_17
(
    IN v_col_93 INT,
    IN v_col_15 VARCHAR(10),
    IN v_col_18 DATETIME,
    IN v_col_31 INT,
    IN v_col_39 INT,
    IN v_col_94 DATETIME,
    IN v_col_107 LONGTEXT,
    IN v_col_2 INT
)
BEGIN
    /* UNIQUE: SET NOCOUNT ON -- no mysql equivalent */
    DECLARE v_col_108 LONGTEXT;
    DECLARE v_col_109 LONGTEXT;
    DECLARE v_col_110 LONGTEXT;
    IF ( v_col_2 IS NOT NULL ) THEN
            /* UNIQUE: SET ROWCOUNT v_col_2 -- no mysql equivalent */
            DO 0;
    END IF;
    IF v_col_93 IS NOT NULL AND v_col_107 IS NULL THEN
            SELECT col_93, col_15, col_18, col_31, col_39, col_94 FROM tbl_8 WHERE (v_col_93 = col_93) AND (col_93 = v_col_93 OR v_col_93 IS NULL) AND (col_15 = v_col_15 OR v_col_15 IS NULL) AND (col_18 = v_col_18 OR v_col_18 IS NULL) AND (col_31 = v_col_31 OR v_col_31 IS NULL) AND (col_39 = v_col_39 OR v_col_39 IS NULL) AND (col_94 = v_col_94 OR v_col_94 IS NULL);
    ELSE
            SET v_col_109 = '
                        SELECT col_93, col_15, col_18, col_31, col_39, col_94
                        FROM tbl_8';
            CALL proc_13(v_col_110, 'xxxxxxxxxxxxx', '=', 'v_xxxxxxxxxxxxx', v_col_93);
            CALL proc_13(v_col_110, 'xxxxxxxxxx', '=', 'v_xxxxxxxxxx', v_col_15);
            CALL proc_13(v_col_110, 'xxxxxxxx', '=', 'v_xxxxxxxx', v_col_18);
            CALL proc_13(v_col_110, 'xxxxxxxxxxxxx', '=', 'v_xxxxxxxxxxxxx', v_col_31);
            CALL proc_13(v_col_110, 'xxxxxxxxxxxx', '=', 'v_xxxxxxxxxxxx', v_col_39);
            CALL proc_13(v_col_110, 'xxxxx', '=', 'v_xxxxx', v_col_94);
            IF v_col_110 IS NOT NULL THEN
                        SET v_col_109 = CONCAT(v_col_109, ' WHERE ', v_col_110);
            END IF;
            CALL proc_14(v_col_109, v_col_107, v_col_108);
            SET @_stmt = v_col_109; PREPARE _dyn FROM @_stmt; EXECUTE _dyn; DEALLOCATE PREPARE _dyn; -- UNIQUE: sp_executesql parameter declarations/bindings dropped; pass them via PREPARE ... USING manually
    END IF;
END$$
DELIMITER ;

-- SET QUOTED_IDENTIFIER OFF
-- SET ANSI_NULLS ON
-- -- xxx xxxxxx xxxxxx xxxxxx

-- -- xxxxxx xxxxxx xxxxxx 

-- IF OBJECT_ID(N'[dbo].[proc_18]', 'P') IS NULL
--     EXEC ('CREATE PROCEDURE [dbo].[proc_18] AS SELECT 1')
-- SET QUOTED_IDENTIFIER ON
-- SET ANSI_NULLS ON
DELIMITER $$
CREATE PROCEDURE proc_18
(
    IN v_col_112 INT,
    IN v_col_103 VARCHAR(10),
    IN v_col_104 DATETIME,
    IN v_col_101 INT,
    IN v_col_113 INT,
    IN v_col_114 DATETIME
)
BEGIN
    /* UNIQUE: SET NOCOUNT ON -- no mysql equivalent */
    DELETE FROM tbl_8 WHERE (col_93 = v_col_112) AND ((col_15 = v_col_103) OR (col_15 IS NULL AND v_col_103 IS NULL)) AND ((col_18 = v_col_104) OR (col_18 IS NULL AND v_col_104 IS NULL)) AND ((col_31 = v_col_101) OR (col_31 IS NULL AND v_col_101 IS NULL)) AND ((col_39 = v_col_113) OR (col_39 IS NULL AND v_col_113 IS NULL)) AND ((col_94 = v_col_114) OR (col_94 IS NULL AND v_col_114 IS NULL));
    -- xx xx xx xxxxxx xx xxxxxx xxxxxx xxxxx
    IF ROW_COUNT() <> 1 THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Application error', MYSQL_ERRNO = 16947;  -- UNIQUE: original RAISERROR/THROW severity/state args dropped: 16 , 1
    END IF;
END$$
DELIMITER ;

-- SET QUOTED_IDENTIFIER OFF
-- SET ANSI_NULLS ON
-- -- xxx xxxxxx xxxxxx xxxxxx

-- -- xxxxxx xxxxxx xxxxxx 

-- IF OBJECT_ID(N'[dbo].[proc_19]', 'P') IS NULL
--     EXEC ('CREATE PROCEDURE [dbo].[proc_19] AS SELECT 1')
-- SET QUOTED_IDENTIFIER ON
-- SET ANSI_NULLS ON
DELIMITER $$
CREATE PROCEDURE proc_19
(
    IN v_col_31 INT,
    IN v_col_6 CHAR(36),
    IN v_col_32 INT,
    IN v_col_33 DATETIME,
    IN v_col_12 INT,
    IN v_col_42 INT,
    IN v_col_62 VARCHAR(10),
    IN v_col_13 INT,
    IN v_col_9 VARCHAR(200),
    IN v_col_10 VARCHAR(200),
    IN v_col_74 LONGTEXT,
    IN v_col_38 LONGTEXT,
    IN v_col_95 LONGTEXT,
    IN v_col_96 LONGTEXT,
    IN v_col_72 VARCHAR(200),
    IN v_col_73 VARCHAR(200),
    IN v_col_63 VARCHAR(1000),
    IN v_col_19 VARCHAR(10),
    IN v_col_20 DATETIME,
    IN v_col_15 VARCHAR(10),
    IN v_col_18 DATETIME,
    IN v_col_101 INT,
    IN v_col_115 CHAR(36),
    IN v_col_116 INT,
    IN v_col_117 DATETIME,
    IN v_col_118 INT,
    IN v_col_119 INT,
    IN v_col_120 VARCHAR(10),
    IN v_col_121 INT,
    IN v_col_122 VARCHAR(200),
    IN v_col_123 VARCHAR(200),
    IN v_col_124 LONGTEXT,
    IN v_col_125 LONGTEXT,
    IN v_col_126 LONGTEXT,
    IN v_col_127 LONGTEXT,
    IN v_col_128 VARCHAR(200),
    IN v_col_129 VARCHAR(200),
    IN v_col_130 VARCHAR(1000),
    IN v_col_131 VARCHAR(10),
    IN v_col_132 DATETIME,
    IN v_col_103 VARCHAR(10),
    IN v_col_104 DATETIME
)
BEGIN
    /* UNIQUE: SET NOCOUNT ON -- no mysql equivalent */
    UPDATE tbl_6 SET col_6 = v_col_6, col_32 = v_col_32, col_33 = v_col_33, col_12 = v_col_12, col_42 = v_col_42, col_62 = v_col_62, col_13 = v_col_13, col_9 = v_col_9, col_10 = v_col_10, col_74 = v_col_74, col_38 = v_col_38, col_95 = v_col_95, col_96 = v_col_96, col_72 = v_col_72, col_73 = v_col_73, col_63 = v_col_63, col_19 = v_col_19, col_20 = v_col_20, col_15 = v_col_15, col_18 = v_col_18 WHERE (col_31 = v_col_101) AND ((col_6 = v_col_115) OR (col_6 IS NULL AND v_col_115 IS NULL)) AND ((col_32 = v_col_116) OR (col_32 IS NULL AND v_col_116 IS NULL)) AND ((col_33 = v_col_117) OR (col_33 IS NULL AND v_col_117 IS NULL)) AND ((col_12 = v_col_118) OR (col_12 IS NULL AND v_col_118 IS NULL)) AND ((col_42 = v_col_119) OR (col_42 IS NULL AND v_col_119 IS NULL)) AND ((col_62 = v_col_120) OR (col_62 IS NULL AND v_col_120 IS NULL)) AND ((col_13 = v_col_121) OR (col_13 IS NULL AND v_col_121 IS NULL)) AND ((col_9 = v_col_122) OR (col_9 IS NULL AND v_col_122 IS NULL)) AND ((col_10 = v_col_123) OR (col_10 IS NULL AND v_col_123 IS NULL)) AND ((col_74 = v_col_124) OR (col_74 IS NULL AND v_col_124 IS NULL)) AND ((col_38 = v_col_125) OR (col_38 IS NULL AND v_col_125 IS NULL)) AND ((col_95 = v_col_126) OR (col_95 IS NULL AND v_col_126 IS NULL)) AND ((col_96 = v_col_127) OR (col_96 IS NULL AND v_col_127 IS NULL)) AND ((col_72 = v_col_128) OR (col_72 IS NULL AND v_col_128 IS NULL)) AND ((col_73 = v_col_129) OR (col_73 IS NULL AND v_col_129 IS NULL)) AND ((col_63 = v_col_130) OR (col_63 IS NULL AND v_col_130 IS NULL)) AND ((col_19 = v_col_131) OR (col_19 IS NULL AND v_col_131 IS NULL)) AND ((col_20 = v_col_132) OR (col_20 IS NULL AND v_col_132 IS NULL)) AND ((col_15 = v_col_103) OR (col_15 IS NULL AND v_col_103 IS NULL)) AND ((col_18 = v_col_104) OR (col_18 IS NULL AND v_col_104 IS NULL));
    -- xx xx xx xxxxxx xx xxxxxx xxxxxx xxxxx
    IF ROW_COUNT() <> 1 THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Application error', MYSQL_ERRNO = 16947;  -- UNIQUE: original RAISERROR/THROW severity/state args dropped: 16 , 1
    END IF;
    -- xxxxxx xx xxxxxx xxxx xx xxxxx xxxxxx
    IF v_col_31 IS NULL THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Application error', MYSQL_ERRNO = 40302;  -- UNIQUE: original RAISERROR/THROW severity/state args dropped: 16 , 1
    END IF;
END$$
DELIMITER ;

-- SET QUOTED_IDENTIFIER OFF
-- SET ANSI_NULLS ON
-- -- xxx xxxxxx xxxxxx xxxxxx

-- -- xxxxxx xxxxxx xxxxxx 

-- IF OBJECT_ID(N'[dbo].[proc_20]', 'P') IS NULL
--     EXEC ('CREATE PROCEDURE [dbo].[proc_20] AS SELECT 1')
-- SET QUOTED_IDENTIFIER ON
-- SET ANSI_NULLS ON
DELIMITER $$
CREATE PROCEDURE proc_20
(
    IN v_col_31 INT,
    IN v_col_6 CHAR(36),
    IN v_col_32 INT,
    IN v_col_33 DATETIME,
    IN v_col_12 INT,
    IN v_col_42 INT,
    IN v_col_62 VARCHAR(10),
    IN v_col_13 INT,
    IN v_col_9 VARCHAR(200),
    IN v_col_10 VARCHAR(200),
    IN v_col_74 LONGTEXT,
    IN v_col_38 LONGTEXT,
    IN v_col_95 LONGTEXT,
    IN v_col_96 LONGTEXT,
    IN v_col_72 VARCHAR(200),
    IN v_col_73 VARCHAR(200),
    IN v_col_63 VARCHAR(1000),
    IN v_col_19 VARCHAR(10),
    IN v_col_20 DATETIME,
    IN v_col_15 VARCHAR(10),
    IN v_col_18 DATETIME,
    IN v_col_107 LONGTEXT,
    IN v_col_2 INT
)
BEGIN
    /* UNIQUE: SET NOCOUNT ON -- no mysql equivalent */
    DECLARE v_col_108 LONGTEXT;
    DECLARE v_col_109 LONGTEXT;
    DECLARE v_col_110 LONGTEXT;
    IF ( v_col_2 IS NOT NULL ) THEN
            /* UNIQUE: SET ROWCOUNT v_col_2 -- no mysql equivalent */
            DO 0;
    END IF;
    IF v_col_31 IS NOT NULL AND v_col_107 IS NULL THEN
            SELECT col_31, col_6, col_32, col_33, col_12, col_42, col_62, col_13, col_9, col_10, col_74, col_38, col_95, col_96, col_72, col_73, col_63, col_19, col_20, col_15, col_18 FROM tbl_6 WHERE (v_col_31 = col_31) AND (col_31 = v_col_31 OR v_col_31 IS NULL) AND (col_6 = v_col_6 OR v_col_6 IS NULL) AND (col_32 = v_col_32 OR v_col_32 IS NULL) AND (col_33 = v_col_33 OR v_col_33 IS NULL) AND (col_12 = v_col_12 OR v_col_12 IS NULL) AND (col_42 = v_col_42 OR v_col_42 IS NULL) AND (col_62 = v_col_62 OR v_col_62 IS NULL) AND (col_13 = v_col_13 OR v_col_13 IS NULL) AND (col_9 = v_col_9 OR v_col_9 IS NULL) AND (col_10 = v_col_10 OR v_col_10 IS NULL) AND (col_74 = v_col_74 OR v_col_74 IS NULL) AND (col_38 = v_col_38 OR v_col_38 IS NULL) AND (col_95 = v_col_95 OR v_col_95 IS NULL) AND (col_96 = v_col_96 OR v_col_96 IS NULL) AND (col_72 = v_col_72 OR v_col_72 IS NULL) AND (col_73 = v_col_73 OR v_col_73 IS NULL) AND (col_63 = v_col_63 OR v_col_63 IS NULL) AND (col_19 = v_col_19 OR v_col_19 IS NULL) AND (col_20 = v_col_20 OR v_col_20 IS NULL) AND (col_15 = v_col_15 OR v_col_15 IS NULL) AND (col_18 = v_col_18 OR v_col_18 IS NULL);
    ELSE
            SET v_col_109 = '
                        SELECT col_31, col_6, col_32, col_33, col_12, col_42, col_62, col_13, col_9, col_10, col_74, col_38, col_95, col_96, col_72, col_73, col_63, col_19, col_20, col_15, col_18
                        FROM tbl_6';
            CALL proc_13(v_col_110, 'xxxxxxxxxxxxx', '=', 'v_xxxxxxxxxxxxx', v_col_31);
            CALL proc_13(v_col_110, 'xxxx', '=', 'v_xxxx', v_col_6);
            CALL proc_13(v_col_110, 'xxxxxxxx', '=', 'v_xxxxxxxx', v_col_32);
            CALL proc_13(v_col_110, 'xxxxxxxx', '=', 'v_xxxxxxxx', v_col_33);
            CALL proc_13(v_col_110, 'xxxxxxxxxxx', '=', 'v_xxxxxxxxxxx', v_col_12);
            CALL proc_13(v_col_110, 'xxxxxxxxx', '=', 'v_xxxxxxxxx', v_col_42);
            CALL proc_13(v_col_110, 'xxxxxxx', '=', 'v_xxxxxxx', v_col_62);
            CALL proc_13(v_col_110, 'xxxxxxxx', '=', 'v_xxxxxxxx', v_col_13);
            CALL proc_13(v_col_110, 'xxxxxxxxxxxxx', '=', 'v_xxxxxxxxxxxxx', v_col_9);
            CALL proc_13(v_col_110, 'xxxxxxxxxxxxx', '=', 'v_xxxxxxxxxxxxx', v_col_10);
            CALL proc_13(v_col_110, 'xxxxx', '=', 'v_xxxxx', v_col_74);
            CALL proc_13(v_col_110, 'xxxxxxxxxx', '=', 'v_xxxxxxxxxx', v_col_38);
            CALL proc_13(v_col_110, 'xxxxxxxxxxxxxxxx', '=', 'v_xxxxxxxxxxxxxxxx', v_col_95);
            CALL proc_13(v_col_110, 'xxxxxxxxxxxxxx', '=', 'v_xxxxxxxxxxxxxx', v_col_96);
            CALL proc_13(v_col_110, 'xxxx', '=', 'v_xxxx', v_col_72);
            CALL proc_13(v_col_110, 'xxxxx', '=', 'v_xxxxx', v_col_73);
            CALL proc_13(v_col_110, 'xxxxxx', '=', 'v_xxxxxx', v_col_63);
            CALL proc_13(v_col_110, 'xxxxxxxxxxx', '=', 'v_xxxxxxxxxxx', v_col_19);
            CALL proc_13(v_col_110, 'xxxxxxxxx', '=', 'v_xxxxxxxxx', v_col_20);
            CALL proc_13(v_col_110, 'xxxxxxxxxx', '=', 'v_xxxxxxxxxx', v_col_15);
            CALL proc_13(v_col_110, 'xxxxxxxx', '=', 'v_xxxxxxxx', v_col_18);
            IF v_col_110 IS NOT NULL THEN
                        SET v_col_109 = CONCAT(v_col_109, ' WHERE ', v_col_110);
            END IF;
            CALL proc_14(v_col_109, v_col_107, v_col_108);
            SET @_stmt = v_col_109; PREPARE _dyn FROM @_stmt; EXECUTE _dyn; DEALLOCATE PREPARE _dyn; -- UNIQUE: sp_executesql parameter declarations/bindings dropped; pass them via PREPARE ... USING manually
    END IF;
END$$
DELIMITER ;

-- SET QUOTED_IDENTIFIER OFF
-- SET ANSI_NULLS ON
-- -- xxx xxxxxx xxxxxx xxxxxx

-- -- xxxxxx xxxxxx xxxxxx 

-- IF OBJECT_ID(N'[dbo].[proc_21]', 'P') IS NULL
--     EXEC ('CREATE PROCEDURE [dbo].[proc_21] AS SELECT 1')
-- SET QUOTED_IDENTIFIER ON
-- SET ANSI_NULLS ON
DELIMITER $$
CREATE PROCEDURE proc_21
(
    IN v_col_101 INT,
    IN v_col_115 CHAR(36),
    IN v_col_116 INT,
    IN v_col_117 DATETIME,
    IN v_col_118 INT,
    IN v_col_119 INT,
    IN v_col_120 VARCHAR(10),
    IN v_col_121 INT,
    IN v_col_122 VARCHAR(200),
    IN v_col_123 VARCHAR(200),
    IN v_col_124 LONGTEXT,
    IN v_col_125 LONGTEXT,
    IN v_col_126 LONGTEXT,
    IN v_col_127 LONGTEXT,
    IN v_col_128 VARCHAR(200),
    IN v_col_129 VARCHAR(200),
    IN v_col_130 VARCHAR(1000),
    IN v_col_131 VARCHAR(10),
    IN v_col_132 DATETIME,
    IN v_col_103 VARCHAR(10),
    IN v_col_104 DATETIME
)
BEGIN
    /* UNIQUE: SET NOCOUNT ON -- no mysql equivalent */
    DELETE FROM tbl_6 WHERE (col_31 = v_col_101) AND ((col_6 = v_col_115) OR (col_6 IS NULL AND v_col_115 IS NULL)) AND ((col_32 = v_col_116) OR (col_32 IS NULL AND v_col_116 IS NULL)) AND ((col_33 = v_col_117) OR (col_33 IS NULL AND v_col_117 IS NULL)) AND ((col_12 = v_col_118) OR (col_12 IS NULL AND v_col_118 IS NULL)) AND ((col_42 = v_col_119) OR (col_42 IS NULL AND v_col_119 IS NULL)) AND ((col_62 = v_col_120) OR (col_62 IS NULL AND v_col_120 IS NULL)) AND ((col_13 = v_col_121) OR (col_13 IS NULL AND v_col_121 IS NULL)) AND ((col_9 = v_col_122) OR (col_9 IS NULL AND v_col_122 IS NULL)) AND ((col_10 = v_col_123) OR (col_10 IS NULL AND v_col_123 IS NULL)) AND ((col_74 = v_col_124) OR (col_74 IS NULL AND v_col_124 IS NULL)) AND ((col_38 = v_col_125) OR (col_38 IS NULL AND v_col_125 IS NULL)) AND ((col_95 = v_col_126) OR (col_95 IS NULL AND v_col_126 IS NULL)) AND ((col_96 = v_col_127) OR (col_96 IS NULL AND v_col_127 IS NULL)) AND ((col_72 = v_col_128) OR (col_72 IS NULL AND v_col_128 IS NULL)) AND ((col_73 = v_col_129) OR (col_73 IS NULL AND v_col_129 IS NULL)) AND ((col_63 = v_col_130) OR (col_63 IS NULL AND v_col_130 IS NULL)) AND ((col_19 = v_col_131) OR (col_19 IS NULL AND v_col_131 IS NULL)) AND ((col_20 = v_col_132) OR (col_20 IS NULL AND v_col_132 IS NULL)) AND ((col_15 = v_col_103) OR (col_15 IS NULL AND v_col_103 IS NULL)) AND ((col_18 = v_col_104) OR (col_18 IS NULL AND v_col_104 IS NULL));
    -- xx xx xx xxxxxx xx xxxxxx xxxxxx xxxxx
    IF ROW_COUNT() <> 1 THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Application error', MYSQL_ERRNO = 16947;  -- UNIQUE: original RAISERROR/THROW severity/state args dropped: 16 , 1
    END IF;
END$$
DELIMITER ;

-- SET QUOTED_IDENTIFIER OFF
-- SET ANSI_NULLS ON
-- -- xxx xxxxxx xxxxxx xxxxxx

-- -- xxxxxx xxxxxx xxxxxx 

-- IF OBJECT_ID(N'[dbo].[proc_22]', 'P') IS NULL
--     EXEC ('CREATE PROCEDURE [dbo].[proc_22] AS SELECT 1')
-- SET QUOTED_IDENTIFIER ON
-- SET ANSI_NULLS ON
DELIMITER $$
CREATE PROCEDURE proc_22
(
    IN v_col_6 CHAR(36),
    IN v_col_7 INT,
    IN v_col_91 VARCHAR(4000),
    IN v_col_19 VARCHAR(10),
    IN v_col_20 DATETIME,
    IN v_col_15 VARCHAR(10),
    IN v_col_18 DATETIME,
    IN v_col_115 CHAR(36),
    IN v_col_133 INT,
    IN v_col_134 VARCHAR(4000),
    IN v_col_131 VARCHAR(10),
    IN v_col_132 DATETIME,
    IN v_col_103 VARCHAR(10),
    IN v_col_104 DATETIME
)
BEGIN
    /* UNIQUE: SET NOCOUNT ON -- no mysql equivalent */
    UPDATE tbl_3 SET col_7 = v_col_7, col_91 = v_col_91, col_19 = v_col_19, col_20 = v_col_20, col_15 = v_col_15, col_18 = v_col_18 WHERE (col_6 = v_col_115) AND ((col_7 = v_col_133) OR (col_7 IS NULL AND v_col_133 IS NULL)) AND ((col_91 = v_col_134) OR (col_91 IS NULL AND v_col_134 IS NULL)) AND ((col_19 = v_col_131) OR (col_19 IS NULL AND v_col_131 IS NULL)) AND ((col_20 = v_col_132) OR (col_20 IS NULL AND v_col_132 IS NULL)) AND ((col_15 = v_col_103) OR (col_15 IS NULL AND v_col_103 IS NULL)) AND ((col_18 = v_col_104) OR (col_18 IS NULL AND v_col_104 IS NULL));
    -- xx xx xx xxxxxx xx xxxxxx xxxxxx xxxxx
    IF ROW_COUNT() <> 1 THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Application error', MYSQL_ERRNO = 16947;  -- UNIQUE: original RAISERROR/THROW severity/state args dropped: 16 , 1
    END IF;
    -- xxxxxx xx xxxxxx xxxx xx xxxxx xxxxxx
    IF v_col_6 IS NULL THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Application error', MYSQL_ERRNO = 40302;  -- UNIQUE: original RAISERROR/THROW severity/state args dropped: 16 , 1
    END IF;
END$$
DELIMITER ;

-- SET QUOTED_IDENTIFIER OFF
-- SET ANSI_NULLS ON
-- -- xxx xxxxxx xxxxxx xxxxxx

-- -- xxxxxx xxxxxx xxxxxx 

-- IF OBJECT_ID(N'[dbo].[proc_23]', 'P') IS NULL
--     EXEC ('CREATE PROCEDURE [dbo].[proc_23] AS SELECT 1')
-- SET QUOTED_IDENTIFIER ON
-- SET ANSI_NULLS ON
DELIMITER $$
CREATE PROCEDURE proc_23
(
    IN v_col_6 CHAR(36),
    IN v_col_7 INT,
    IN v_col_91 VARCHAR(4000),
    IN v_col_19 VARCHAR(10),
    IN v_col_20 DATETIME,
    IN v_col_15 VARCHAR(10),
    IN v_col_18 DATETIME,
    IN v_col_107 LONGTEXT,
    IN v_col_2 INT
)
BEGIN
    /* UNIQUE: SET NOCOUNT ON -- no mysql equivalent */
    DECLARE v_col_108 LONGTEXT;
    DECLARE v_col_109 LONGTEXT;
    DECLARE v_col_110 LONGTEXT;
    IF ( v_col_2 IS NOT NULL ) THEN
            /* UNIQUE: SET ROWCOUNT v_col_2 -- no mysql equivalent */
            DO 0;
    END IF;
    IF v_col_6 IS NOT NULL AND v_col_107 IS NULL THEN
            SELECT col_6, col_7, col_91, col_19, col_20, col_15, col_18 FROM tbl_3 WHERE (v_col_6 = col_6) AND (col_6 = v_col_6 OR v_col_6 IS NULL) AND (col_7 = v_col_7 OR v_col_7 IS NULL) AND (col_91 = v_col_91 OR v_col_91 IS NULL) AND (col_19 = v_col_19 OR v_col_19 IS NULL) AND (col_20 = v_col_20 OR v_col_20 IS NULL) AND (col_15 = v_col_15 OR v_col_15 IS NULL) AND (col_18 = v_col_18 OR v_col_18 IS NULL);
    ELSE
            SET v_col_109 = '
                        SELECT col_6, col_7, col_91, col_19, col_20, col_15, col_18
                        FROM tbl_3';
            CALL proc_13(v_col_110, 'xxxx', '=', 'v_xxxx', v_col_6);
            CALL proc_13(v_col_110, 'xxxxxxx', '=', 'v_xxxxxxx', v_col_7);
            CALL proc_13(v_col_110, 'xxxxxxxxxx', '=', 'v_xxxxxxxxxx', v_col_91);
            CALL proc_13(v_col_110, 'xxxxxxxxxxx', '=', 'v_xxxxxxxxxxx', v_col_19);
            CALL proc_13(v_col_110, 'xxxxxxxxx', '=', 'v_xxxxxxxxx', v_col_20);
            CALL proc_13(v_col_110, 'xxxxxxxxxx', '=', 'v_xxxxxxxxxx', v_col_15);
            CALL proc_13(v_col_110, 'xxxxxxxx', '=', 'v_xxxxxxxx', v_col_18);
            IF v_col_110 IS NOT NULL THEN
                        SET v_col_109 = CONCAT(v_col_109, ' WHERE ', v_col_110);
            END IF;
            CALL proc_14(v_col_109, v_col_107, v_col_108);
            SET @_stmt = v_col_109; PREPARE _dyn FROM @_stmt; EXECUTE _dyn; DEALLOCATE PREPARE _dyn; -- UNIQUE: sp_executesql parameter declarations/bindings dropped; pass them via PREPARE ... USING manually
    END IF;
END$$
DELIMITER ;

-- SET QUOTED_IDENTIFIER OFF
-- SET ANSI_NULLS ON
-- -- xxx xxxxxx xxxxxx xxxxxx

-- -- xxxxxx xxxxxx xxxxxx 

-- IF OBJECT_ID(N'[dbo].[proc_24]', 'P') IS NULL
--     EXEC ('CREATE PROCEDURE [dbo].[proc_24] AS SELECT 1')
-- SET QUOTED_IDENTIFIER ON
-- SET ANSI_NULLS ON
DELIMITER $$
CREATE PROCEDURE proc_24
(
    IN v_col_115 CHAR(36),
    IN v_col_133 INT,
    IN v_col_134 VARCHAR(4000),
    IN v_col_131 VARCHAR(10),
    IN v_col_132 DATETIME,
    IN v_col_103 VARCHAR(10),
    IN v_col_104 DATETIME
)
BEGIN
    /* UNIQUE: SET NOCOUNT ON -- no mysql equivalent */
    DELETE FROM tbl_3 WHERE (col_6 = v_col_115) AND ((col_7 = v_col_133) OR (col_7 IS NULL AND v_col_133 IS NULL)) AND ((col_91 = v_col_134) OR (col_91 IS NULL AND v_col_134 IS NULL)) AND ((col_19 = v_col_131) OR (col_19 IS NULL AND v_col_131 IS NULL)) AND ((col_20 = v_col_132) OR (col_20 IS NULL AND v_col_132 IS NULL)) AND ((col_15 = v_col_103) OR (col_15 IS NULL AND v_col_103 IS NULL)) AND ((col_18 = v_col_104) OR (col_18 IS NULL AND v_col_104 IS NULL));
    -- xx xx xx xxxxxx xx xxxxxx xxxxxx xxxxx
    IF ROW_COUNT() <> 1 THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Application error', MYSQL_ERRNO = 16947;  -- UNIQUE: original RAISERROR/THROW severity/state args dropped: 16 , 1
    END IF;
END$$
DELIMITER ;

-- SET QUOTED_IDENTIFIER OFF
-- SET ANSI_NULLS ON
-- -- xxx xxxxxx xxxxxx xxxxxx

-- -- xxxxxx xxxxxx xxxxxx 

-- IF OBJECT_ID(N'[dbo].[proc_25]', 'P') IS NULL
--     EXEC ('CREATE PROCEDURE [dbo].[proc_25] AS SELECT 1')
-- SET QUOTED_IDENTIFIER ON
-- SET ANSI_NULLS ON
DELIMITER $$
CREATE PROCEDURE proc_25
(
    IN v_col_1 INT,
    IN v_col_135 DATETIME,
    IN v_col_136 DATETIME,
    IN v_col_137 VARCHAR(10),
    IN v_col_138 VARCHAR(5),
    IN v_col_139 VARCHAR(200),
    IN v_col_140 VARCHAR(200),
    IN v_col_141 VARCHAR(200),
    IN v_col_142 VARCHAR(200),
    IN v_col_143 VARCHAR(200),
    IN v_col_144 VARCHAR(200),
    IN v_col_145 VARCHAR(200),
    IN v_col_146 VARCHAR(200),
    IN v_col_2 INT
)
BEGIN
    DECLARE v_func1 DATETIME DEFAULT func1();
    DECLARE v_col_147 DATETIME DEFAULT CAST(func1() AS DATE);

    /* UNIQUE: SET NOCOUNT ON -- no mysql equivalent */
    IF ( v_col_2 IS NOT NULL ) THEN
            /* UNIQUE: SET ROWCOUNT v_col_2 -- no mysql equivalent */
            DO 0;
    END IF;
    SELECT col_1, col_50, col_148, CASE WHEN col_148 = 'A' THEN v_col_144 WHEN col_148 = 'B' THEN v_col_145 WHEN col_148 = 'C' THEN v_col_146 ELSE v_col_144 END AS col_149, col_150, col_58, col_13, col_151, col_152, col_137, col_60, col_153, col_154, col_138, col_155, CASE WHEN NOT col_156 IS NULL THEN v_col_143 WHEN NOT col_157 IS NULL THEN v_col_143 WHEN NOT col_158 IS NULL THEN v_col_142 WHEN NOT col_159 IS NULL THEN v_col_141 ELSE v_col_140 END AS col_160, col_159, col_158, col_157, col_156, col_161 FROM (SELECT DISTINCT col_11.col_1, col_11.col_50, col_11.col_162 AS col_148, col_11.col_58 AS col_150, col_57.col_163 AS col_58, col_11.col_13, col_45.col_46 AS col_151, COALESCE(col_37.col_10, col_45.col_164, col_45.col_165, col_45.col_166) AS col_152, col_57.col_60 AS col_137, col_52.col_46 AS col_60, col_52.col_153, col_167.col_163 AS col_154, col_52.col_155 AS col_138, col_22.col_163 AS col_155, (SELECT MIN(col_40.col_94) FROM tbl_8 AS col_40 WHERE col_40.col_31 IN (SELECT col_31 FROM tbl_6 AS col_168 WHERE col_168.col_6 = col_37.col_6 AND col_168.col_12 IN (0, 1) /* xxxxxx col_151 */) AND col_40.col_39 = 1 /* xxxxxx xx xx col_6 xx xxxxxx */) AS col_159, (SELECT MIN(col_40.col_94) FROM tbl_8 AS col_40 WHERE col_40.col_31 IN (SELECT col_31 FROM tbl_6 AS col_168 WHERE col_168.col_6 = col_37.col_6 AND col_168.col_12 IN (0, 1, 2) /* xxxxxx col_151 col_60 */) AND col_40.col_39 = 3 /* xxxxxx xx xx xxxxxx */) AS col_158, (SELECT MAX(col_40.col_94) FROM tbl_8 AS col_40 WHERE col_40.col_31 IN (SELECT col_31 FROM tbl_6 AS col_168 WHERE col_168.col_6 = col_37.col_6 AND col_168.col_12 IN (0, 1, 2) /* xxxxxx col_151 col_60 */) AND col_40.col_39 = 4 /* xxxxxx xx xx xxxxxx */) AS col_157, (SELECT MAX(col_40.col_94) FROM tbl_8 AS col_40 WHERE col_40.col_31 IN (SELECT col_31 FROM tbl_6 AS col_168 WHERE col_168.col_6 = col_37.col_6 AND col_168.col_12 IN (0, 1) /* xxxxxx col_151 col_60 */) AND col_40.col_39 = 2 /* xxxxxx xx xx col_6 xx xxxxxx */) AS col_156, COALESCE((SELECT 1 FROM tbl_7 WHERE col_31 = col_37.col_31 ORDER BY col_31 ASC /* xxxxxx xx xx xxxxxx xx col_161 */ LIMIT 1), 0) AS col_161 FROM tbl_1 AS col_11 INNER JOIN tbl_2 AS col_56 ON col_11.col_1 = col_56.col_1 INNER JOIN tbl_6 AS col_37 ON col_37.col_6 = col_56.col_6 INNER JOIN tbl_10 AS col_45 ON col_11.col_13 = col_45.col_13 INNER JOIN tbl_11 AS col_57 ON col_11.col_58 = col_57.col_59 INNER JOIN tbl_12 AS col_52 ON col_57.col_60 = col_52.col_59 INNER JOIN tbl_14 AS col_167 ON col_52.col_153 = col_167.col_153 INNER JOIN tbl_15 AS col_22 ON col_52.col_155 = col_22.col_59 WHERE col_11.col_50 BETWEEN COALESCE(v_col_135, v_col_147) AND COALESCE(v_col_136, v_func1) AND col_37.col_12 = 1 /* col_151 */ AND col_37.col_13 = col_11.col_13 AND col_37.col_42 = 0 AND (v_col_1 IS NULL OR col_11.col_1 = v_col_1) AND (v_col_137 IS NULL OR col_57.col_60 = v_col_137) AND (v_col_138 IS NULL OR col_52.col_155 = v_col_138) AND (v_col_139 IS NULL OR col_11.col_162 IN (SELECT item FROM FUNC5(v_col_139, ',')))) AS col_160 ORDER BY col_50 ASC;
END$$
DELIMITER ;

-- SET QUOTED_IDENTIFIER OFF
-- SET ANSI_NULLS ON
-- -- xxx xxxxxx xxxxxx xxxxxx

-- -- xxxxxx xxxxxx xxxxxx 

-- IF OBJECT_ID(N'[dbo].[proc_26]', 'P') IS NULL
--     EXEC ('CREATE PROCEDURE [dbo].[proc_26] AS SELECT 1')
-- SET QUOTED_IDENTIFIER ON
-- SET ANSI_NULLS ON
DELIMITER $$
CREATE PROCEDURE proc_26
(
    IN v_col_1 INT,
    IN v_col_13 INT
)
BEGIN
    DECLARE v_func1 DATETIME DEFAULT func1();
    DECLARE v_col_67 INT DEFAULT COALESCE ( ( SELECT TOP ( 1 ) col_67 FROM tbl_9 WHERE col_30 = 1 ORDER BY col_66 ASC ) , 1440 );

    /* UNIQUE: SET NOCOUNT ON -- no mysql equivalent */
    UPDATE tbl_6 SET col_32 = 0 WHERE col_32 = 1 AND col_31 IN (SELECT col_171.col_31 FROM tbl_6 AS col_171 INNER JOIN tbl_2 AS col_56 ON col_56.col_6 = col_171.col_6 INNER JOIN tbl_1 AS col_11 ON col_11.col_1 = col_56.col_1 WHERE col_32 = 1 AND v_func1 > DATE_ADD(col_11.col_50, INTERVAL v_col_67 MINUTE)) /* xxxxxx xxx xxxxxx xx xx xxxxx xx xxxxxx */ /* xxxx xxx xxxx xxx xx x xxxxxx xxx xx xx xxxx xxxx xx xxxxxx */;
    UPDATE tbl_6 SET col_32 = 0 WHERE col_32 = 1 AND v_func1 > DATE_ADD(COALESCE(col_33, v_func1), INTERVAL 5 MINUTE);
    SELECT DISTINCT col_56.col_1 FROM tbl_2 AS col_56 WHERE EXISTS(SELECT NULL FROM tbl_6 AS col_37 WHERE col_37.col_6 = col_56.col_6 AND col_37.col_32 = 1 AND (v_col_13 IS NULL OR col_37.col_13 = v_col_13)) AND (v_col_1 IS NULL OR col_56.col_1 = v_col_1);
END$$
DELIMITER ;

-- SET QUOTED_IDENTIFIER OFF
-- SET ANSI_NULLS ON
-- -- xxx xxxxxx xxxxxx xxxxxx

-- -- xxxxxx xxxxxx xxxxxx 

-- IF OBJECT_ID(N'[dbo].[proc_27]', 'P') IS NULL
--     EXEC ('CREATE PROCEDURE [dbo].[proc_27] AS SELECT 1')
-- SET QUOTED_IDENTIFIER ON
-- SET ANSI_NULLS ON
DELIMITER $$
CREATE PROCEDURE proc_27
(
    IN v_col_1 INT,
    IN v_col_2 INT
)
BEGIN
    DECLARE v_col_6 CHAR(36) DEFAULT ( SELECT col_6 FROM tbl_2 WHERE col_1 = v_col_1 );

    /* UNIQUE: SET NOCOUNT ON -- no mysql equivalent */
    IF ( v_col_2 IS NOT NULL ) THEN
            /* UNIQUE: SET ROWCOUNT v_col_2 -- no mysql equivalent */
            DO 0;
    END IF;
    IF ( v_col_6 IS NOT NULL ) THEN
            DELETE FROM tbl_8 WHERE col_31 IN (SELECT col_31 FROM tbl_6 WHERE col_6 = v_col_6);
            DELETE FROM tbl_6 WHERE col_6 = v_col_6;
            DELETE FROM tbl_2 WHERE col_1 = v_col_1;
            DELETE FROM tbl_3 WHERE col_6 = v_col_6;
    END IF;
END$$
DELIMITER ;

-- SET QUOTED_IDENTIFIER OFF
-- SET ANSI_NULLS ON
-- UNIQUE: Unhandled expression type: IfBlock
-- 
-- -- xxx xxxxxx xxxxxx xxxxxx

-- SET QUOTED_IDENTIFIER ON
-- SET ANSI_NULLS ON
DELIMITER $$
CREATE TRIGGER col_173
AFTER UPDATE ON tbl_6
FOR EACH ROW
BEGIN
    /* UNIQUE: SET NOCOUNT ON -- no mysql equivalent */
    DECLARE v_func1 DATETIME DEFAULT func1();
    DECLARE v_col_174 INT DEFAULT COALESCE((SELECT 1 FROM tbl_9 WHERE NOT col_96 IS NULL AND col_30 = 1), 0);
    IF UPDATE ( col_32 ) THEN
            /* xxxxxx xxxx xxxxxx */
            INSERT INTO tbl_8 (col_15, col_18, col_31, col_39, col_94) SELECT col_175.col_15, col_175.col_18, col_175.col_31, (4 - ((2 * v_col_174 * (1 - col_175.col_42)) + col_175.col_32)) AS col_39, v_func1 AS col_94 FROM inserted AS col_175 INNER JOIN deleted AS col_176 ON col_176.col_31 = col_175.col_31 WHERE col_175.col_32 <> col_176.col_32;
            /* xx xx xxxx xx xxxxxx xxxxxx xx xxxxx col_162 xx xxxxxx xxx x */
    END IF;
END$$
DELIMITER ;

-- SET QUOTED_IDENTIFIER OFF
-- SET ANSI_NULLS ON
-- xxx xxxxxx xxxxxx xxxxxx
