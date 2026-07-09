-- ============================================================
-- Oracle fixture: generated from procedures_sqlserver.sql
-- by the unique transpiler (T-SQL -> Oracle).
-- Validated against Oracle 23c (FREEPDB1).
-- DO NOT EDIT BY HAND -- regenerate via the transpiler.
-- ============================================================
-- ============================================================
-- DDL: tables required by the procedure fixtures below.
-- Schema: dbo. Idempotent (IF NOT EXISTS guard per table).
-- ============================================================
BEGIN FOR unique_guard IN (SELECT 1 FROM DUAL WHERE NOT EXISTS (
      SELECT 1 FROM user_objects WHERE object_name = 'TBL_15' AND object_type = 'TABLE')) LOOP
    EXECUTE IMMEDIATE q'[CREATE TABLE tbl_15 (
  col_59 VARCHAR2(5) NOT NULL,
  col_163 VARCHAR2(200),
  CONSTRAINT pk_tbl_15 PRIMARY KEY (col_59)
)]';
  END LOOP; END;
/

BEGIN FOR unique_guard IN (SELECT 1 FROM DUAL WHERE NOT EXISTS (
      SELECT 1 FROM user_objects WHERE object_name = 'TBL_14' AND object_type = 'TABLE')) LOOP
    EXECUTE IMMEDIATE q'[CREATE TABLE tbl_14 (
  col_153 NUMBER(10) NOT NULL,
  col_163 VARCHAR2(200),
  CONSTRAINT pk_tbl_14 PRIMARY KEY (col_153)
)]';
  END LOOP; END;
/

BEGIN FOR unique_guard IN (SELECT 1 FROM DUAL WHERE NOT EXISTS (
      SELECT 1 FROM user_objects WHERE object_name = 'TBL_13' AND object_type = 'TABLE')) LOOP
    EXECUTE IMMEDIATE q'[CREATE TABLE tbl_13 (
  col_62 VARCHAR2(50) NOT NULL,
  col_46 VARCHAR2(200),
  col_77 VARCHAR2(200),
  CONSTRAINT pk_tbl_13 PRIMARY KEY (col_62)
)]';
  END LOOP; END;
/

BEGIN FOR unique_guard IN (SELECT 1 FROM DUAL WHERE NOT EXISTS (
      SELECT 1 FROM user_objects WHERE object_name = 'TBL_12' AND object_type = 'TABLE')) LOOP
    EXECUTE IMMEDIATE q'[CREATE TABLE tbl_12 (
  col_59 NUMBER(10) NOT NULL,
  col_46 VARCHAR2(200),
  col_153 NUMBER(10),
  col_155 VARCHAR2(5),
  CONSTRAINT pk_tbl_12 PRIMARY KEY (col_59)
)]';
  END LOOP; END;
/

BEGIN FOR unique_guard IN (SELECT 1 FROM DUAL WHERE NOT EXISTS (
      SELECT 1 FROM user_objects WHERE object_name = 'TBL_11' AND object_type = 'TABLE')) LOOP
    EXECUTE IMMEDIATE q'[CREATE TABLE tbl_11 (
  col_59 NUMBER(10) NOT NULL,
  col_60 NUMBER(10),
  col_163 VARCHAR2(200),
  CONSTRAINT pk_tbl_11 PRIMARY KEY (col_59)
)]';
  END LOOP; END;
/

BEGIN FOR unique_guard IN (SELECT 1 FROM DUAL WHERE NOT EXISTS (
      SELECT 1 FROM user_objects WHERE object_name = 'TBL_10' AND object_type = 'TABLE')) LOOP
    EXECUTE IMMEDIATE q'[CREATE TABLE tbl_10 (
  col_13 NUMBER(10) NOT NULL,
  col_46 VARCHAR2(200),
  col_48 VARCHAR2(200),
  col_73 VARCHAR2(200),
  col_164 VARCHAR2(200),
  col_165 VARCHAR2(200),
  col_166 VARCHAR2(200),
  CONSTRAINT pk_tbl_10 PRIMARY KEY (col_13)
)]';
  END LOOP; END;
/

BEGIN FOR unique_guard IN (SELECT 1 FROM DUAL WHERE NOT EXISTS (
      SELECT 1 FROM user_objects WHERE object_name = 'TBL_1' AND object_type = 'TABLE')) LOOP
    EXECUTE IMMEDIATE q'[CREATE TABLE tbl_1 (
  col_1 NUMBER(10) NOT NULL,
  col_13 NUMBER(10),
  col_50 TIMESTAMP,
  col_58 NUMBER(10),
  col_162 VARCHAR2(50),
  CONSTRAINT pk_tbl_1 PRIMARY KEY (col_1)
)]';
  END LOOP; END;
/

BEGIN FOR unique_guard IN (SELECT 1 FROM DUAL WHERE NOT EXISTS (
      SELECT 1 FROM user_objects WHERE object_name = 'TBL_3' AND object_type = 'TABLE')) LOOP
    EXECUTE IMMEDIATE q'[CREATE TABLE tbl_3 (
  col_6 RAW(16) DEFAULT SYS_GUID() NOT NULL,
  col_7 NUMBER(10),
  col_91 VARCHAR2(4000),
  col_19 VARCHAR2(10),
  col_20 TIMESTAMP,
  col_15 VARCHAR2(10),
  col_18 TIMESTAMP,
  CONSTRAINT pk_tbl_3 PRIMARY KEY (col_6)
)]';
  END LOOP; END;
/

BEGIN FOR unique_guard IN (SELECT 1 FROM DUAL WHERE NOT EXISTS (
      SELECT 1 FROM user_objects WHERE object_name = 'TBL_2' AND object_type = 'TABLE')) LOOP
    EXECUTE IMMEDIATE q'[CREATE TABLE tbl_2 (
  col_1 NUMBER(10),
  col_4 NUMBER(10),
  col_6 RAW(16),
  col_15 VARCHAR2(10),
  col_18 TIMESTAMP,
  col_19 VARCHAR2(10),
  col_20 TIMESTAMP
)]';
  END LOOP; END;
/

BEGIN FOR unique_guard IN (SELECT 1 FROM DUAL WHERE NOT EXISTS (
      SELECT 1 FROM user_objects WHERE object_name = 'TBL_4' AND object_type = 'TABLE')) LOOP
    EXECUTE IMMEDIATE q'[CREATE TABLE tbl_4 (
  col_6 RAW(16),
  col_9 VARCHAR2(200),
  col_10 VARCHAR2(200),
  col_12 NUMBER(10),
  col_13 NUMBER(10)
)]';
  END LOOP; END;
/

BEGIN FOR unique_guard IN (SELECT 1 FROM DUAL WHERE NOT EXISTS (
      SELECT 1 FROM user_objects WHERE object_name = 'TBL_5' AND object_type = 'TABLE')) LOOP
    EXECUTE IMMEDIATE q'[CREATE TABLE tbl_5 (
  col_23 NUMBER(10) NOT NULL,
  col_24 NUMBER(10),
  col_26 VARCHAR2(200),
  col_28 NUMBER(10),
  col_30 NUMBER(10) DEFAULT 1 NOT NULL,
  CONSTRAINT pk_tbl_5 PRIMARY KEY (col_23)
)]';
  END LOOP; END;
/

BEGIN FOR unique_guard IN (SELECT 1 FROM DUAL WHERE NOT EXISTS (
      SELECT 1 FROM user_objects WHERE object_name = 'TBL_9' AND object_type = 'TABLE')) LOOP
    EXECUTE IMMEDIATE q'[CREATE TABLE tbl_9 (
  col_30 NUMBER(10) DEFAULT 1 NOT NULL,
  col_43 VARCHAR2(4000),
  col_61 VARCHAR2(200),
  col_65 NUMBER(10) DEFAULT -1440,
  col_66 TIMESTAMP,
  col_67 NUMBER(10) DEFAULT 1440,
  col_79 VARCHAR2(4000),
  col_80 VARCHAR2(4000),
  col_89 VARCHAR2(500),
  col_90 VARCHAR2(500),
  col_96 VARCHAR2(4000)
)]';
  END LOOP; END;
/

BEGIN FOR unique_guard IN (SELECT 1 FROM DUAL WHERE NOT EXISTS (
      SELECT 1 FROM user_objects WHERE object_name = 'TBL_6' AND object_type = 'TABLE')) LOOP
    EXECUTE IMMEDIATE q'[CREATE TABLE tbl_6 (
  col_31 NUMBER(10) GENERATED BY DEFAULT AS IDENTITY,
  col_6 RAW(16),
  col_12 NUMBER(10),
  col_13 NUMBER(10),
  col_15 VARCHAR2(10),
  col_18 TIMESTAMP,
  col_19 VARCHAR2(10),
  col_20 TIMESTAMP,
  col_32 NUMBER(10) DEFAULT 0,
  col_33 TIMESTAMP,
  col_38 VARCHAR2(4000),
  col_42 NUMBER(10) DEFAULT 0,
  col_62 VARCHAR2(50),
  col_63 VARCHAR2(1000),
  col_72 VARCHAR2(200),
  col_73 VARCHAR2(200),
  col_74 VARCHAR2(4000),
  col_9 VARCHAR2(200),
  col_10 VARCHAR2(200),
  col_95 VARCHAR2(4000),
  col_96 VARCHAR2(4000),
  CONSTRAINT pk_tbl_6 PRIMARY KEY (col_31)
)]';
  END LOOP; END;
/

BEGIN FOR unique_guard IN (SELECT 1 FROM DUAL WHERE NOT EXISTS (
      SELECT 1 FROM user_objects WHERE object_name = 'TBL_7' AND object_type = 'TABLE')) LOOP
    EXECUTE IMMEDIATE q'[CREATE TABLE tbl_7 (
  col_97 NUMBER(10) NOT NULL,
  col_31 NUMBER(10),
  col_23 NUMBER(10) NOT NULL,
  col_15 VARCHAR2(10),
  col_18 TIMESTAMP,
  col_98 NUMBER(10),
  col_99 VARCHAR2(4000)
)]';
  END LOOP; END;
/

BEGIN FOR unique_guard IN (SELECT 1 FROM DUAL WHERE NOT EXISTS (
      SELECT 1 FROM user_objects WHERE object_name = 'TBL_8' AND object_type = 'TABLE')) LOOP
    EXECUTE IMMEDIATE q'[CREATE TABLE tbl_8 (
  col_93 NUMBER(10) GENERATED BY DEFAULT AS IDENTITY,
  col_15 VARCHAR2(10),
  col_18 TIMESTAMP,
  col_31 NUMBER(10),
  col_39 NUMBER(10),
  col_94 TIMESTAMP,
  CONSTRAINT pk_tbl_8 PRIMARY KEY (col_93)
)]';
  END LOOP; END;
/

-- ── Helper stored procedures called by the fixture ────────────────────────────
-- UNIQUE: Unhandled expression type: Execute
CREATE OR REPLACE PROCEDURE proc_13
(
    V_WHERE OUT NVARCHAR2,
    V_COL IN NVARCHAR2,
    V_OP IN NVARCHAR2,
    V_PARAM IN NVARCHAR2,
    V_VAL IN VARCHAR2 /* UNIQUE: SQL_VARIANT */ DEFAULT NULL
)
AS
BEGIN
    /* UNIQUE: SET NOCOUNT ON -- tsql-only, no oracle equivalent */
    IF V_VAL IS NOT NULL THEN
            V_WHERE := COALESCE(V_WHERE || ' AND ', '') || V_COL || ' ' || V_OP || ' ' || V_PARAM;
    END IF;
END;
/

-- UNIQUE: Unhandled expression type: Execute
CREATE OR REPLACE PROCEDURE proc_14
(
    V_QUERY OUT NVARCHAR2,
    V_FILTER IN NVARCHAR2 DEFAULT NULL,
    V_PAGE OUT NVARCHAR2
)
AS
BEGIN
    /* UNIQUE: SET NOCOUNT ON -- tsql-only, no oracle equivalent */
    V_PAGE := NULL;
    IF V_FILTER IS NOT NULL THEN
            V_QUERY := V_QUERY || ' ' || V_FILTER;
    END IF;
END;
/

-- ============================================================
-- Stub definitions for anonymized custom functions (T-SQL).
-- These make the script self-contained and runnable; bodies are
-- placeholders that preserve the call signatures and return types.
-- ============================================================
BEGIN
    EXECUTE IMMEDIATE 'DROP FUNCTION func1';
EXCEPTION
    WHEN OTHERS THEN NULL;  -- object did not exist
END;
/

CREATE OR REPLACE FUNCTION func1
RETURN DATE
AS
BEGIN
    RETURN (SYSDATE + - 3);
END;
/

BEGIN
    EXECUTE IMMEDIATE 'DROP FUNCTION func3';
EXCEPTION
    WHEN OTHERS THEN NULL;  -- object did not exist
END;
/

CREATE OR REPLACE FUNCTION func3
(
    V_KEY IN NVARCHAR2,
    V_DEF IN NVARCHAR2
)
RETURN NVARCHAR2
AS
BEGIN
    RETURN V_DEF;
END;
/

BEGIN
    EXECUTE IMMEDIATE 'DROP FUNCTION func4';
EXCEPTION
    WHEN OTHERS THEN NULL;  -- object did not exist
END;
/

CREATE OR REPLACE FUNCTION func4
(
    V_PAYLOAD IN NVARCHAR2,
    V_SECRET IN NVARCHAR2
)
RETURN NVARCHAR2
AS
BEGIN
    DECLARE
        v_unique_ret NVARCHAR2(2000);
    BEGIN
        SELECT CAST(RAWTOHEX(STANDARD_HASH(V_PAYLOAD || V_SECRET, 'SHA256')) AS VARCHAR2(4000)) INTO v_unique_ret FROM DUAL;
        RETURN v_unique_ret;
    END;
END;
/

BEGIN
    EXECUTE IMMEDIATE 'DROP FUNCTION func5';
EXCEPTION
    WHEN OTHERS THEN NULL;  -- object did not exist
END;
/

CREATE OR REPLACE FUNCTION func5
(
    V_S IN NVARCHAR2,
    V_DELIM IN NVARCHAR2
)
RETURN SYS.ODCIVARCHAR2LIST IS
    v_result SYS.ODCIVARCHAR2LIST := SYS.ODCIVARCHAR2LIST();
BEGIN
    SELECT TRIM(REGEXP_SUBSTR(V_S, '[^' || V_DELIM || ']+', 1, LEVEL))
    BULK COLLECT INTO v_result FROM DUAL
    CONNECT BY REGEXP_SUBSTR(V_S, '[^' || V_DELIM || ']+', 1, LEVEL) IS NOT NULL;
    RETURN v_result;
END;
/

-- xxxxxx xxxxxx


-- xxxxxx xxxxxx xxxxxx
-- UNIQUE: Unhandled expression type: Execute
-- SET QUOTED_IDENTIFIER ON
-- SET ANSI_NULLS ON
CREATE OR REPLACE PROCEDURE proc_1
(
    V_COL_1 IN NUMBER DEFAULT NULL,
    V_COL_2 IN NUMBER DEFAULT NULL,
    RESULT_CURSOR OUT SYS_REFCURSOR
)
IS
    --   <nombre>xxxxxx</nombre>
BEGIN
    /* UNIQUE: SET NOCOUNT ON -- tsql-only, no oracle equivalent */
    IF ( V_COL_2 IS NOT NULL ) THEN
            /* UNIQUE: SET ROWCOUNT @col_2 -- tsql-only, no oracle equivalent */
            NULL;
    END IF;
    OPEN RESULT_CURSOR FOR SELECT *
    FROM (SELECT DISTINCT col_3.col_1, col_3.col_4, col_5.col_6, col_5.col_7, col_8.col_9, col_8.col_10
    FROM tbl_1 col_11
    INNER JOIN tbl_2 col_3 ON col_3.col_1 = col_11.col_1
    INNER JOIN tbl_3 col_5 ON col_5.col_6 = col_3.col_6
    LEFT JOIN tbl_4 col_8 ON col_5.col_6 = col_8.col_6
    WHERE col_3.col_1 = V_COL_1 AND (col_8.col_6 IS NULL OR col_8.col_12 = 1 AND col_8.col_13 = col_11.col_13)
    UNION ALL
    SELECT V_COL_1 AS col_1, 0 AS col_4, NULL AS col_6, NULL AS col_7, NULL AS col_9, NULL AS col_10
    FROM DUAL) col_14
    ORDER BY col_4 DESC NULLS LAST
    FETCH FIRST 1 ROWS ONLY;
END;
/

-- SET QUOTED_IDENTIFIER OFF
-- SET ANSI_NULLS ON
-- xxx xxxxxx xxxxxx xxxxxx

-- xxxxxx xxxxxx xxxxxx
-- UNIQUE: Unhandled expression type: Execute
-- SET QUOTED_IDENTIFIER ON
-- SET ANSI_NULLS ON
--   <nombre>xxxxxx</nombre>
/* UNIQUE: was T-SQL table variable V_COL_16 */
CREATE GLOBAL TEMPORARY TABLE proc_2_V_COL_16 (
  col_17 RAW(16)
) ON COMMIT DELETE ROWS;
CREATE OR REPLACE PROCEDURE proc_2
(
    V_COL_1 IN NUMBER DEFAULT NULL,
    V_COL_4 IN NUMBER DEFAULT NULL,
    V_COL_15 IN VARCHAR2 DEFAULT NULL,
    V_COL_2 IN NUMBER DEFAULT NULL,
    RESULT_CURSOR OUT SYS_REFCURSOR
)
IS
    V_FUNC1 DATE := func1 ( );
    V_COL_6 RAW(16) := NULL;
BEGIN
    /* UNIQUE: SET NOCOUNT ON -- tsql-only, no oracle equivalent */
    IF ( V_COL_2 IS NOT NULL ) THEN
            /* UNIQUE: SET ROWCOUNT @col_2 -- tsql-only, no oracle equivalent */
            NULL;
    END IF;
    IF ( V_COL_1 IS NOT NULL ) THEN
            UPDATE tbl_2 SET col_4 = V_COL_4, col_15 = V_COL_15, col_18 = V_FUNC1 WHERE col_1 = V_COL_1 AND col_4 <> V_COL_4;
            SELECT ( SELECT MAX ( col_6 ) FROM tbl_2 where col_1 = V_COL_1 ) INTO V_COL_6 FROM DUAL;
            IF V_COL_6 IS NULL THEN
                        INSERT INTO tbl_3 (
                          col_19,
                          col_20,
                          col_15,
                          col_18
                        )
                        SELECT
                          V_COL_15,
                          V_FUNC1,
                          V_COL_15,
                          V_FUNC1
                        WHERE
                          NOT EXISTS(
                            SELECT
                              NULL
                            FROM tbl_2
                            WHERE
                              col_1 = V_COL_1
                          )  /* UNIQUE: OUTPUT inserted.col_6 dropped — populate the temp table manually */;
                        SELECT ( SELECT MAX ( col_17 ) FROM proc_2_V_COL_16 ) INTO V_COL_6 FROM DUAL;
                        INSERT INTO tbl_2 (col_1, col_4, col_6, col_19, col_20, col_15, col_18)
                        SELECT V_COL_1, V_COL_4, V_COL_6, V_COL_15, V_FUNC1, V_COL_15, V_FUNC1
                        FROM DUAL
                        WHERE NOT EXISTS (SELECT NULL
                        FROM tbl_2
                        WHERE col_1 = V_COL_1);
            END IF;
    END IF;
    OPEN RESULT_CURSOR FOR SELECT LOWER(CAST(V_COL_6 AS VARCHAR2(36))) AS col_21 FROM DUAL;
END;
/

-- SET QUOTED_IDENTIFIER OFF
-- SET ANSI_NULLS ON
-- xxx xxxxxx xxxxxx xxxxxx

-- xxxxxx xxxxxx xxxxxx
-- UNIQUE: Unhandled expression type: Execute
-- SET QUOTED_IDENTIFIER ON
-- SET ANSI_NULLS ON
CREATE OR REPLACE PROCEDURE proc_3
(
    V_COL_2 IN NUMBER DEFAULT NULL,
    RESULT_CURSOR OUT SYS_REFCURSOR
)
IS
    --   <nombre>xxxxxx</nombre>
BEGIN
    /* UNIQUE: SET NOCOUNT ON -- tsql-only, no oracle equivalent */
    IF ( V_COL_2 IS NOT NULL ) THEN
            /* UNIQUE: SET ROWCOUNT @col_2 -- tsql-only, no oracle equivalent */
            NULL;
    END IF;
    OPEN RESULT_CURSOR FOR SELECT col_22.col_23, col_22.col_24 AS col_25, col_22.col_26 AS col_27, CAST(NULL AS VARCHAR2(4000)) AS value, col_22.col_28 AS col_29
    FROM tbl_5 col_22
    WHERE col_22.col_30 = 1
    ORDER BY col_22.col_28 ASC NULLS FIRST;
END;
/

-- SET QUOTED_IDENTIFIER OFF
-- SET ANSI_NULLS ON
-- xxx xxxxxx xxxxxx xxxxxx

-- xxxxxx xxxxxx xxxxxx
-- UNIQUE: Unhandled expression type: Execute
-- SET QUOTED_IDENTIFIER ON
-- SET ANSI_NULLS ON
CREATE OR REPLACE PROCEDURE proc_4
(
    V_COL_31 IN NUMBER DEFAULT NULL,
    V_COL_2 IN NUMBER DEFAULT NULL,
    RESULT_CURSOR OUT SYS_REFCURSOR
)
IS
    --   <nombre>xxxxxx</nombre>
    V_FUNC1 DATE := func1 ( );
BEGIN
    /* UNIQUE: SET NOCOUNT ON -- tsql-only, no oracle equivalent */
    IF ( V_COL_2 IS NOT NULL ) THEN
            /* UNIQUE: SET ROWCOUNT @col_2 -- tsql-only, no oracle equivalent */
            NULL;
    END IF;
    UPDATE tbl_6 SET col_32 = 1, col_18 = V_FUNC1 WHERE col_31 = V_COL_31 AND col_32 = 0 AND NOT EXISTS (SELECT NULL FROM tbl_7 WHERE col_31 = V_COL_31);
    UPDATE tbl_6 SET col_33 = V_FUNC1 WHERE col_31 = V_COL_31 AND NOT EXISTS (SELECT NULL FROM tbl_7 WHERE col_31 = V_COL_31);
    -- xxxxxx xx xx xxxxxx
    -- xxxxxx xx xx xxxxxx
    -- xxxxxx
    -- xx xx xx xxxxxx xx col_161
    OPEN RESULT_CURSOR FOR SELECT col_32, col_34, col_35, col_36
    FROM (SELECT 1 AS col_32, col_37.col_38 AS col_34, CAST(NULL AS VARCHAR2(4000)) AS col_35, COALESCE((SELECT 1
    FROM tbl_8
    WHERE col_31 = V_COL_31 AND col_39 = 3
    FETCH FIRST 1 ROWS ONLY), 0) AS col_36
    FROM tbl_6 col_37
    INNER JOIN tbl_8 col_40 ON col_40.col_31 IN (SELECT col_31
    FROM tbl_6 col_41
    WHERE col_41.col_6 = col_37.col_6 AND col_32 = 1 AND col_42 = 1) AND col_40.col_39 = 3
    WHERE col_37.col_31 = V_COL_31 AND NOT EXISTS (SELECT NULL
    FROM tbl_7
    WHERE col_31 = V_COL_31 AND EXISTS (SELECT NULL
    FROM tbl_9
    WHERE col_30 = 1 AND NOT col_43 IS NULL))
    UNION ALL
    SELECT 0 AS col_32, CAST(NULL AS VARCHAR2(4000)) AS col_34, CAST(NULL AS VARCHAR2(4000)) AS col_35, 0 AS col_36
    FROM DUAL) col_44
    ORDER BY col_32 DESC NULLS LAST
    FETCH FIRST 1 ROWS ONLY;
END;
/

-- SET QUOTED_IDENTIFIER OFF
-- SET ANSI_NULLS ON
-- xxx xxxxxx xxxxxx xxxxxx

-- xxxxxx xxxxxx xxxxxx
-- UNIQUE: Unhandled expression type: Execute
-- SET QUOTED_IDENTIFIER ON
-- SET ANSI_NULLS ON
CREATE OR REPLACE PROCEDURE proc_5
(
    V_COL_31 IN NUMBER DEFAULT NULL,
    V_COL_2 IN NUMBER DEFAULT NULL,
    RESULT_CURSOR OUT SYS_REFCURSOR
)
IS
    --   <nombre>xxxxxx</nombre>
BEGIN
    /* UNIQUE: SET NOCOUNT ON -- tsql-only, no oracle equivalent */
    IF ( V_COL_2 IS NOT NULL ) THEN
            /* UNIQUE: SET ROWCOUNT @col_2 -- tsql-only, no oracle equivalent */
            NULL;
    END IF;
    -- xxxxxx xx xx col_6 xx xxxxxx
    -- xx xx xx xxxxxx xx col_161
    OPEN RESULT_CURSOR FOR SELECT col_45.col_46 AS col_47, col_45.col_48 AS col_49, col_11.col_50 AS col_51, col_52.col_46 AS col_53, COALESCE((SELECT 1
    FROM tbl_8
    WHERE col_31 = V_COL_31 AND col_39 = 1
    ORDER BY col_31 ASC NULLS FIRST
    FETCH FIRST 1 ROWS ONLY), 0) AS col_54, COALESCE((SELECT 1
    FROM tbl_7
    WHERE col_31 = V_COL_31 AND EXISTS (SELECT NULL
    FROM tbl_9
    WHERE col_30 = 1 AND NOT col_43 IS NULL)
    ORDER BY col_31 ASC NULLS FIRST
    FETCH FIRST 1 ROWS ONLY), 0) AS col_55
    FROM tbl_6 col_37
    INNER JOIN tbl_2 col_56 ON col_37.col_6 = col_56.col_6
    INNER JOIN tbl_1 col_11 ON col_56.col_1 = col_11.col_1
    INNER JOIN tbl_10 col_45 ON col_11.col_13 = col_45.col_13
    INNER JOIN tbl_11 col_57 ON col_11.col_58 = col_57.col_59
    INNER JOIN tbl_12 col_52 ON col_57.col_60 = col_52.col_59
    WHERE col_37.col_31 = V_COL_31;
END;
/

-- SET QUOTED_IDENTIFIER OFF
-- SET ANSI_NULLS ON
-- xxx xxxxxx xxxxxx xxxxxx

-- xxxxxx xxxxxx xxxxxx
-- UNIQUE: Unhandled expression type: Execute
-- SET QUOTED_IDENTIFIER ON
-- SET ANSI_NULLS ON
CREATE OR REPLACE PROCEDURE proc_6
(
    V_COL_61 IN VARCHAR2 DEFAULT NULL,
    V_COL_6 IN RAW DEFAULT NULL,
    V_COL_42 IN NUMBER DEFAULT 0,
    V_COL_62 IN VARCHAR2 DEFAULT NULL,
    V_COL_13 IN NUMBER DEFAULT NULL,
    V_COL_63 IN VARCHAR2 DEFAULT NULL,
    V_COL_9 IN VARCHAR2 DEFAULT NULL,
    V_COL_10 IN VARCHAR2 DEFAULT NULL,
    V_COL_64 IN VARCHAR2 DEFAULT NULL,
    V_COL_15 IN VARCHAR2 DEFAULT NULL,
    V_COL_2 IN NUMBER DEFAULT NULL,
    RESULT_CURSOR OUT SYS_REFCURSOR
)
IS
    --   <nombre>xxxxxx</nombre>
    V_FUNC1 DATE := func1 ( );
    V_COL_65 NUMBER(10);
    V_COL_67 NUMBER(10);
    V_COL_68 DATE;
    V_COL_69 DATE;
    V_COL_70 DATE;
    V_COL_71 VARCHAR2(36);
    V_COL_72 VARCHAR2(200) := NULL;
    V_COL_73 VARCHAR2(200) := NULL;
    V_COL_74 VARCHAR2(4000) := NULL;
    V_COL_32 NUMBER(10) := 0;
    V_COL_75 VARCHAR2(50) := NULL;
    V_COL_17 NUMBER(10) := NULL;
    V_COL_12 NUMBER(10) := NULL;
BEGIN
    SELECT COALESCE((SELECT col_65 FROM tbl_9 WHERE col_30 = 1 ORDER BY col_66 DESC NULLS LAST FETCH FIRST 1 ROWS ONLY), -1440) INTO V_COL_65 FROM DUAL;
    SELECT COALESCE((SELECT col_67 FROM tbl_9 WHERE col_30 = 1 ORDER BY col_66 DESC NULLS LAST FETCH FIRST 1 ROWS ONLY), 1440) INTO V_COL_67 FROM DUAL;
    SELECT LOWER(CAST(V_COL_6 AS VARCHAR2(36))) INTO V_COL_71 FROM DUAL;
    /* UNIQUE: SET NOCOUNT ON -- tsql-only, no oracle equivalent */
    IF ( V_COL_2 IS NOT NULL ) THEN
            /* UNIQUE: SET ROWCOUNT @col_2 -- tsql-only, no oracle equivalent */
            NULL;
    END IF;
    IF ( ( V_COL_6 IS NULL ) OR ( V_COL_42 IS NULL ) ) THEN
            RETURN;  -- UNIQUE: discarded procedure RETURN value (NULL)
    END IF;
    SELECT ( SELECT CASE WHEN V_COL_42 = 1 THEN 2 /* xxxxxx */ WHEN V_COL_42 = 0 AND V_COL_13 IS NOT NULL THEN 1 /* col_151 */ ELSE 0 END ) /* xxxxxx */ /* xx xx xx xxxxxx */ INTO V_COL_12 FROM DUAL;
    IF V_COL_12 = 2 THEN
            DELETE FROM tbl_6 WHERE col_6 = V_COL_6 AND col_42 = 1 AND col_62 = V_COL_62;
            BEGIN
                SELECT col_76.col_46, LOWER(COALESCE(col_76.col_77, V_COL_62 || '@' || V_COL_61)) INTO V_COL_72, V_COL_73 FROM tbl_13 col_76 WHERE col_76 . col_62 = V_COL_62;
            EXCEPTION
                WHEN NO_DATA_FOUND THEN
                    NULL;  -- T-SQL leaves the variables unchanged
            END;
    END IF;
    -- xx xx xx xxxxxx
    IF V_COL_12 = 1 THEN
            DELETE FROM tbl_6 WHERE col_6 = V_COL_6 AND col_42 = 0 AND col_13 = V_COL_13;
            BEGIN
                SELECT col_45.col_46, LOWER(COALESCE(col_45.col_73, CAST(col_45.col_13 AS VARCHAR2(50)) || '@' || V_COL_61)) INTO V_COL_72, V_COL_73 FROM tbl_2 col_3 INNER JOIN tbl_1 col_11 ON col_11 . col_1 = col_3 . col_1 INNER JOIN tbl_10 col_45 ON col_45 . col_13 = col_11 . col_13 WHERE col_3 . col_6 = V_COL_6;
            EXCEPTION
                WHEN NO_DATA_FOUND THEN
                    NULL;  -- T-SQL leaves the variables unchanged
            END;
    END IF;
    -- xx xx xx xxxxxx
    IF V_COL_12 = 0 THEN
            DELETE FROM tbl_6 WHERE col_6 = V_COL_6 AND col_42 = 0 AND col_62 = V_COL_62 AND col_13 IS NULL;
            BEGIN
                SELECT V_COL_62, LOWER(V_COL_62 || '@' || V_COL_61) INTO V_COL_72, V_COL_73 ;
            EXCEPTION
                WHEN NO_DATA_FOUND THEN
                    NULL;  -- T-SQL leaves the variables unchanged
            END;
    END IF;
    BEGIN
        SELECT col_11 . col_50 INTO V_COL_68 FROM tbl_2 col_3 INNER JOIN tbl_1 col_11 ON col_11 . col_1 = col_3 . col_1 WHERE col_3 . col_6 = V_COL_6;
    EXCEPTION
        WHEN NO_DATA_FOUND THEN
            NULL;  -- T-SQL leaves the variables unchanged
    END;
    -- xxxxxx xx xxxxxx xxx xxxxxx
    V_COL_69 := (V_COL_68 || NUMTODSINTERVAL(V_COL_65, 'MINUTE'));
    V_COL_70 := (V_COL_68 || NUMTODSINTERVAL(V_COL_67, 'MINUTE'));
    INSERT INTO tbl_6 (col_12, col_62, col_13, col_19, col_20, col_15, col_18, col_6, col_72, col_73, col_63, col_42, col_74, col_32, col_9, col_10)
    VALUES (V_COL_12, V_COL_62, V_COL_13, V_COL_15, V_FUNC1, V_COL_15, V_FUNC1, V_COL_6, V_COL_72, V_COL_73, V_COL_63, V_COL_42, '-', V_COL_32, V_COL_9, V_COL_10) RETURNING col_31 INTO V_COL_17;
    -- xx xxxxxx xxx xxxxxx xxxx xx xxxxxx xxxxx xxx xxxxxx xx xx xxxxx
    SELECT CAST(V_COL_17 AS VARCHAR2(20)) INTO V_COL_75 FROM DUAL;
    IF ( V_COL_64 IS NULL ) THEN
            V_COL_74 := func2 ( V_COL_61 , V_COL_69 , V_COL_70 , V_COL_75 , V_COL_71 , V_COL_72 , V_COL_73 , V_COL_63 , V_COL_42 );
    ELSE
            V_COL_74 := V_COL_64;
    END IF;
    IF ( COALESCE ( V_COL_74 , 'xxxxxxx-xxxx' ) = 'xxxxxxx-xxxx' ) THEN
            DELETE FROM tbl_6 WHERE col_31 = V_COL_17;
    ELSE
            UPDATE tbl_6 SET col_74 = V_COL_74 WHERE col_31 = V_COL_17;
    END IF;
    OPEN RESULT_CURSOR FOR SELECT col_31, col_74 FROM tbl_6 WHERE col_31 = V_COL_17;
END;
/

-- SET QUOTED_IDENTIFIER OFF
-- SET ANSI_NULLS ON
-- xxx xxxxxx xxxxxx xxxxxx

-- xxxxxx xxxxxx xxxxx
-- UNIQUE: Unhandled expression type: Execute
-- SET QUOTED_IDENTIFIER ON
-- SET ANSI_NULLS ON
CREATE OR REPLACE FUNCTION func2
(
    V_COL_61 IN VARCHAR2 DEFAULT NULL,
    V_COL_69 IN DATE DEFAULT NULL,
    V_COL_70 IN DATE DEFAULT NULL,
    V_COL_62 IN VARCHAR2 DEFAULT NULL,
    V_COL_6 IN VARCHAR2 DEFAULT NULL,
    V_COL_72_IN IN VARCHAR2 DEFAULT NULL,
    V_COL_73_IN IN VARCHAR2 DEFAULT NULL,
    V_COL_63_IN IN VARCHAR2 DEFAULT NULL,
    V_COL_42 IN NUMBER DEFAULT NULL
)
RETURN VARCHAR2
IS
    --   <nombre>xxxxx</nombre>
    V_COL_72 VARCHAR2(200) := V_COL_72_IN;
    V_COL_73 VARCHAR2(200) := V_COL_73_IN;
    V_COL_63 VARCHAR2(1000) := V_COL_63_IN;
    V_FUNC1 DATE;
    V_COL_79 VARCHAR2(4000);
    V_COL_80 VARCHAR2(4000);
    V_MOD VARCHAR2(10);
    V_COL_74 VARCHAR2(4000);
    V_COL_81 VARCHAR2(1000);
    V_COL_82 DATE;
    V_COL_83 VARCHAR2(500);
    V_COL_84 VARCHAR2(500);
    V_COL_75 VARCHAR2(50);
    V_COL_85 NUMBER(19);
    V_COL_86 NUMBER(19);
    V_COL_87 NUMBER(19);
    V_COL_88 VARCHAR2(50);
BEGIN
    -- xxxxxx
    V_FUNC1 := func1 ( );
    BEGIN
        SELECT col_79, col_89, col_90, col_80 INTO V_COL_79, V_COL_83, V_COL_84, V_COL_80 FROM tbl_9 WHERE col_61 = V_COL_61 AND col_30 = 1;
    EXCEPTION
        WHEN NO_DATA_FOUND THEN
            NULL;  -- T-SQL leaves the variables unchanged
    END;
    IF ( V_COL_79 IS NULL OR V_COL_62 IS NULL OR V_COL_69 IS NULL OR V_COL_70 IS NULL OR V_COL_6 IS NULL ) THEN
            RETURN 'xxxxxxx-xxxx';
    END IF;
    V_COL_75 := 'xxxx.xxxxx';
    V_MOD := CASE WHEN COALESCE ( V_COL_42 , 0 ) = 1 THEN 'xxxx' ELSE 'xxxxx' END;
    V_COL_88 := REPLACE ( COALESCE ( V_COL_62 , '' ) , '"' , '' );
    V_COL_81 := COALESCE ( func3 ( 'xxxxxxxxxxx' , '/' ) , '/' );
    IF ( SUBSTR ( V_COL_81 , LENGTH ( V_COL_81 ) , 1 ) <> '/' ) THEN
            V_COL_81 := V_COL_81 || '/';
    END IF;
    V_COL_80 := REPLACE ( V_COL_80 , '~/' , V_COL_81 );
    V_COL_63 := REPLACE ( COALESCE ( V_COL_63 , REPLACE ( V_COL_80 , '{x}' , V_COL_75 ) ) , '"' , '' );
    V_COL_72 := REPLACE ( COALESCE ( V_COL_72 , V_COL_75 ) , '"' , '' );
    V_COL_73 := REPLACE(COALESCE(V_COL_73, V_COL_75 || '@' || V_COL_61), '"', '');
    V_COL_82 := TO_TIMESTAMP('xxxx-xx-xx xx:xx:xx', 'YYYY-MM-DD HH24:MI:SS');
    V_COL_85 := ((V_FUNC1 - V_COL_82) * 86400);
    V_COL_86 := ((COALESCE ( V_COL_69 , V_FUNC1 ) - V_COL_82) * 86400);
    V_COL_87 := ((COALESCE(V_COL_70, V_FUNC1 + 1) - V_COL_82) * 86400);
    V_COL_74 := '{
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
    V_COL_74 := REPLACE ( V_COL_74 , '$xxxxxx$' , V_COL_63 );
    V_COL_74 := REPLACE ( V_COL_74 , '$xxxx$' , V_COL_72 );
    V_COL_74 := REPLACE ( V_COL_74 , '$xxxxx$' , V_COL_73 );
    SELECT REPLACE(V_COL_74, '$xxx$', CAST(V_COL_85 AS VARCHAR2(50))) INTO V_COL_74 FROM DUAL;
    SELECT REPLACE(V_COL_74, '$xxx$', CAST(V_COL_86 AS VARCHAR2(50))) INTO V_COL_74 FROM DUAL;
    SELECT REPLACE(V_COL_74, '$xxx$', CAST(V_COL_87 AS VARCHAR2(50))) INTO V_COL_74 FROM DUAL;
    V_COL_74 := REPLACE ( V_COL_74 , '$xxx$' , V_COL_84 );
    V_COL_74 := REPLACE ( V_COL_74 , '$xxx$' , V_COL_83 );
    V_COL_74 := REPLACE ( V_COL_74 , '$xxxxxxxxx$' , V_COL_88 );
    V_COL_74 := REPLACE ( V_COL_74 , '$xxx$' , V_COL_75 );
    V_COL_74 := REPLACE ( V_COL_74 , '$xxxx$' , V_COL_6 );
    V_COL_74 := REPLACE ( V_COL_74 , '$xxxxxxxxx$' , V_MOD ) /* xxxxxx xx xxxxxx xxx xxxx */;
    V_COL_74 := REPLACE(V_COL_74, CHR(13), '');
    V_COL_74 := REPLACE(V_COL_74, CHR(10), '');
    V_COL_74 := REPLACE ( V_COL_74 , '    ' , ' ' );
    V_COL_74 := REPLACE ( V_COL_74 , '  ' , ' ' );
    V_COL_74 := REPLACE ( V_COL_74 , '  ' , ' ' );
    V_COL_74 := REPLACE ( V_COL_74 , '{ ' , '{' );
    V_COL_74 := REPLACE ( V_COL_74 , '} ' , '}' );
    V_COL_74 := REPLACE ( V_COL_74 , ': ' , ':' );
    V_COL_74 := REPLACE ( V_COL_74 , ', "' , ',"' );
    V_COL_74 := REPLACE ( V_COL_74 , ' "' , '"' );
    V_COL_74 := REPLACE ( V_COL_74 , '" ' , '"' );
    RETURN func4 ( V_COL_74 , V_COL_79 );
END;
/

-- SET QUOTED_IDENTIFIER OFF
-- SET ANSI_NULLS ON
-- xxx xxxxxx xxxxxx xxxxx

-- xxxxxx xxxxxx xxxxxx
-- UNIQUE: Unhandled expression type: Execute
-- SET QUOTED_IDENTIFIER ON
-- SET ANSI_NULLS ON
--    <nombre>xxxxxx</nombre>
/* UNIQUE: was T-SQL table variable V_COL_92 */
CREATE GLOBAL TEMPORARY TABLE proc_7_V_COL_92 (
  col_17 RAW(16)
) ON COMMIT DELETE ROWS;
CREATE OR REPLACE PROCEDURE proc_7
(
    V_COL_6 OUT RAW,
    V_COL_7 IN NUMBER DEFAULT NULL,
    V_COL_91 IN VARCHAR2 DEFAULT NULL,
    V_COL_19 IN VARCHAR2 DEFAULT NULL,
    V_COL_20 IN DATE DEFAULT NULL,
    V_COL_15 IN VARCHAR2 DEFAULT NULL,
    V_COL_18 IN DATE DEFAULT NULL
)
AS
BEGIN
    /* UNIQUE: SET NOCOUNT ON -- tsql-only, no oracle equivalent */
    INSERT INTO tbl_3 (col_7, col_91, col_19, col_20, col_15, col_18) VALUES (V_COL_7, V_COL_91, V_COL_19, V_COL_20, V_COL_15, V_COL_18)  /* UNIQUE: OUTPUT inserted.col_6 dropped — populate the temp table manually */;
    SELECT ( SELECT MAX ( col_17 ) FROM proc_7_V_COL_92 ) INTO V_COL_6 FROM DUAL;
END;
/

-- SET QUOTED_IDENTIFIER OFF
-- SET ANSI_NULLS ON
-- xxx xxxxxx xxxxxx xxxxxx

-- xxxxxx xxxxxx xxxxxx
-- UNIQUE: Unhandled expression type: Execute
-- SET QUOTED_IDENTIFIER ON
-- SET ANSI_NULLS ON
--    <nombre>xxxxxx</nombre>
/* UNIQUE: was T-SQL table variable V_COL_92 */
CREATE GLOBAL TEMPORARY TABLE proc_8_V_COL_92 (
  col_17 NUMBER(10)
) ON COMMIT DELETE ROWS;
CREATE OR REPLACE PROCEDURE proc_8
(
    V_COL_93 OUT NUMBER,
    V_COL_15 IN VARCHAR2 DEFAULT NULL,
    V_COL_18 IN DATE DEFAULT NULL,
    V_COL_31 IN NUMBER DEFAULT NULL,
    V_COL_39 IN NUMBER DEFAULT NULL,
    V_COL_94 IN DATE DEFAULT NULL
)
AS
BEGIN
    /* UNIQUE: SET NOCOUNT ON -- tsql-only, no oracle equivalent */
    INSERT INTO tbl_8 (col_15, col_18, col_31, col_39, col_94) VALUES (V_COL_15, V_COL_18, V_COL_31, V_COL_39, V_COL_94)  /* UNIQUE: OUTPUT inserted.col_93 dropped — populate the temp table manually */;
    SELECT ( SELECT MAX ( col_17 ) FROM proc_8_V_COL_92 ) INTO V_COL_93 FROM DUAL;
END;
/

-- SET QUOTED_IDENTIFIER OFF
-- SET ANSI_NULLS ON
-- xxx xxxxxx xxxxxx xxxxxx

-- xxxxxx xxxxxx xxxxxx
-- UNIQUE: Unhandled expression type: Execute
-- SET QUOTED_IDENTIFIER ON
-- SET ANSI_NULLS ON
--    <nombre>xxxxxx</nombre>
/* UNIQUE: was T-SQL table variable V_COL_92 */
CREATE GLOBAL TEMPORARY TABLE proc_9_V_COL_92 (
  col_17 NUMBER(10)
) ON COMMIT DELETE ROWS;
CREATE OR REPLACE PROCEDURE proc_9
(
    V_COL_31 OUT NUMBER,
    V_COL_6 IN RAW DEFAULT NULL,
    V_COL_32 IN NUMBER DEFAULT NULL,
    V_COL_33 IN DATE DEFAULT NULL,
    V_COL_12 IN NUMBER DEFAULT NULL,
    V_COL_42 IN NUMBER DEFAULT NULL,
    V_COL_62 IN VARCHAR2 DEFAULT NULL,
    V_COL_13 IN NUMBER DEFAULT NULL,
    V_COL_9 IN VARCHAR2 DEFAULT NULL,
    V_COL_10 IN VARCHAR2 DEFAULT NULL,
    V_COL_74 IN VARCHAR2 DEFAULT NULL,
    V_COL_38 IN VARCHAR2 DEFAULT NULL,
    V_COL_95 IN VARCHAR2 DEFAULT NULL,
    V_COL_96 IN VARCHAR2 DEFAULT NULL,
    V_COL_72 IN VARCHAR2 DEFAULT NULL,
    V_COL_73 IN VARCHAR2 DEFAULT NULL,
    V_COL_63 IN VARCHAR2 DEFAULT NULL,
    V_COL_19 IN VARCHAR2 DEFAULT NULL,
    V_COL_20 IN DATE DEFAULT NULL,
    V_COL_15 IN VARCHAR2 DEFAULT NULL,
    V_COL_18 IN DATE DEFAULT NULL
)
AS
BEGIN
    /* UNIQUE: SET NOCOUNT ON -- tsql-only, no oracle equivalent */
    INSERT INTO tbl_6 (
      col_6,
      col_32,
      col_33,
      col_12,
      col_42,
      col_62,
      col_13,
      col_9,
      col_10,
      col_74,
      col_38,
      col_95,
      col_96,
      col_72,
      col_73,
      col_63,
      col_19,
      col_20,
      col_15,
      col_18
    )
    VALUES
      (
        V_COL_6,
        V_COL_32,
        V_COL_33,
        V_COL_12,
        V_COL_42,
        V_COL_62,
        V_COL_13,
        V_COL_9,
        V_COL_10,
        V_COL_74,
        V_COL_38,
        V_COL_95,
        V_COL_96,
        V_COL_72,
        V_COL_73,
        V_COL_63,
        V_COL_19,
        V_COL_20,
        V_COL_15,
        V_COL_18
      )  /* UNIQUE: OUTPUT inserted.col_31 dropped — populate the temp table manually */;
    SELECT ( SELECT MAX ( col_17 ) FROM proc_9_V_COL_92 ) INTO V_COL_31 FROM DUAL;
END;
/

-- SET QUOTED_IDENTIFIER OFF
-- SET ANSI_NULLS ON
-- xxx xxxxxx xxxxxx xxxxxx

-- xxxxxx xxxxxx xxxxxx
-- UNIQUE: Unhandled expression type: Execute
-- SET QUOTED_IDENTIFIER ON
-- SET ANSI_NULLS ON
CREATE OR REPLACE PROCEDURE proc_10
(
    V_COL_97 IN NUMBER DEFAULT NULL,
    V_COL_31 IN NUMBER DEFAULT NULL,
    V_COL_23 IN NUMBER DEFAULT NULL,
    V_COL_15 IN VARCHAR2 DEFAULT NULL,
    V_COL_18 IN DATE DEFAULT NULL,
    V_COL_98 IN NUMBER DEFAULT NULL,
    V_COL_99 IN VARCHAR2 DEFAULT NULL,
    V_COL_100 IN NUMBER DEFAULT NULL,
    V_COL_101 IN NUMBER DEFAULT NULL,
    V_COL_102 IN NUMBER DEFAULT NULL,
    V_COL_103 IN VARCHAR2 DEFAULT NULL,
    V_COL_104 IN DATE DEFAULT NULL,
    V_COL_105 IN NUMBER DEFAULT NULL,
    V_COL_106 IN VARCHAR2 DEFAULT NULL
)
IS
    --    <nombre>xxxxxx</nombre>
BEGIN
    /* UNIQUE: SET NOCOUNT ON -- tsql-only, no oracle equivalent */
    UPDATE tbl_7
    SET col_15 = V_COL_15, col_18 = V_COL_18, col_98 = V_COL_98, col_99 = V_COL_99
    WHERE col_97 = V_COL_100 AND col_31 = V_COL_101 AND col_23 = V_COL_102 AND (col_15 = V_COL_103 OR col_15 IS NULL AND V_COL_103 IS NULL) AND (col_18 = V_COL_104 OR col_18 IS NULL AND V_COL_104 IS NULL) AND (col_98 = V_COL_105 OR col_98 IS NULL AND V_COL_105 IS NULL) AND (col_99 = V_COL_106 OR col_99 IS NULL AND V_COL_106 IS NULL);
    -- xx xx xx xxxxxx xx xxxxxx xxxxxx xxxxx
    IF SQL%ROWCOUNT <> 1 THEN
            RAISE_APPLICATION_ERROR(-20001, 16947);
    END IF;
    -- xxxxxx xx xxxxxx xxxx xx xxxxx xxxxxx
    IF V_COL_97 IS NULL OR V_COL_31 IS NULL OR V_COL_23 IS NULL THEN
            RAISE_APPLICATION_ERROR(-20001, 40302);
    END IF;
END;
/

-- SET QUOTED_IDENTIFIER OFF
-- SET ANSI_NULLS ON
-- xxx xxxxxx xxxxxx xxxxxx

-- xxxxxx xxxxxx xxxxxx
-- UNIQUE: Unhandled expression type: Execute
-- SET QUOTED_IDENTIFIER ON
-- SET ANSI_NULLS ON
CREATE OR REPLACE PROCEDURE proc_11
(
    V_COL_97 IN NUMBER DEFAULT NULL,
    V_COL_31 IN NUMBER DEFAULT NULL,
    V_COL_23 IN NUMBER DEFAULT NULL,
    V_COL_15 IN VARCHAR2 DEFAULT NULL,
    V_COL_18 IN DATE DEFAULT NULL,
    V_COL_98 IN NUMBER DEFAULT NULL,
    V_COL_99 IN VARCHAR2 DEFAULT NULL
)
IS
    --    <nombre>xxxxxx</nombre>
BEGIN
    /* UNIQUE: SET NOCOUNT ON -- tsql-only, no oracle equivalent */
    INSERT INTO tbl_7 (col_97, col_31, col_23, col_15, col_18, col_98, col_99) VALUES (V_COL_97, V_COL_31, V_COL_23, V_COL_15, V_COL_18, V_COL_98, V_COL_99);
END;
/

-- SET QUOTED_IDENTIFIER OFF
-- SET ANSI_NULLS ON
-- xxx xxxxxx xxxxxx xxxxxx

-- xxxxxx xxxxxx xxxxxx
-- UNIQUE: Unhandled expression type: Execute
-- SET QUOTED_IDENTIFIER ON
-- SET ANSI_NULLS ON
CREATE OR REPLACE PROCEDURE proc_12
(
    V_COL_97 IN NUMBER DEFAULT NULL,
    V_COL_31 IN NUMBER DEFAULT NULL,
    V_COL_23 IN NUMBER DEFAULT NULL,
    V_COL_15 IN VARCHAR2 DEFAULT NULL,
    V_COL_18 IN DATE DEFAULT NULL,
    V_COL_98 IN NUMBER DEFAULT NULL,
    V_COL_99 IN VARCHAR2 DEFAULT NULL,
    V_COL_107 IN VARCHAR2 DEFAULT NULL,
    V_COL_2 IN NUMBER DEFAULT NULL,
    RESULT_CURSOR OUT SYS_REFCURSOR
)
IS
    --    <nombre>xxxxxx</nombre>
    V_COL_108 VARCHAR2(4000);
    V_COL_109 NVARCHAR2(2000);
    V_COL_110 NVARCHAR2(2000);
BEGIN
    /* UNIQUE: SET NOCOUNT ON -- tsql-only, no oracle equivalent */
    IF ( V_COL_2 IS NOT NULL ) THEN
            /* UNIQUE: SET ROWCOUNT @col_2 -- tsql-only, no oracle equivalent */
            NULL;
    END IF;
    IF V_COL_97 IS NOT NULL AND V_COL_31 IS NOT NULL AND V_COL_23 IS NOT NULL AND V_COL_107 IS NULL THEN
            OPEN RESULT_CURSOR FOR SELECT col_97, col_31, col_23, col_15, col_18, col_98, col_99
            FROM tbl_7
            WHERE V_COL_97 = col_97 AND V_COL_31 = col_31 AND V_COL_23 = col_23 AND (col_97 = V_COL_97 OR V_COL_97 IS NULL) AND (col_31 = V_COL_31 OR V_COL_31 IS NULL) AND (col_23 = V_COL_23 OR V_COL_23 IS NULL) AND (col_15 = V_COL_15 OR V_COL_15 IS NULL) AND (col_18 = V_COL_18 OR V_COL_18 IS NULL) AND (col_98 = V_COL_98 OR V_COL_98 IS NULL) AND (col_99 = V_COL_99 OR V_COL_99 IS NULL);
    ELSE
            V_COL_109 := '
                        SELECT col_97, col_31, col_23, col_15, col_18, col_98, col_99
                        FROM tbl_7';
            proc_13(V_COL_110, 'xxxxxxxxxxxxxxxx', '=', 'V_XXXXXXXXXXXXXXXX', V_COL_97);
            proc_13(V_COL_110, 'xxxxxxxxxxxxx', '=', 'V_XXXXXXXXXXXXX', V_COL_31);
            proc_13(V_COL_110, 'xxxxxxxxxxxxxxx', '=', 'V_XXXXXXXXXXXXXXX', V_COL_23);
            proc_13(V_COL_110, 'xxxxxxxxxx', '=', 'V_XXXXXXXXXX', V_COL_15);
            proc_13(V_COL_110, 'xxxxxxxx', '=', 'V_XXXXXXXX', V_COL_18);
            proc_13(V_COL_110, 'xxxxx', '=', 'V_XXXXX', V_COL_98);
            proc_13(V_COL_110, 'xxxxxxxxx', '=', 'V_XXXXXXXXX', V_COL_99);
            IF V_COL_110 IS NOT NULL THEN
                        V_COL_109 := V_COL_109 || ' WHERE ' || V_COL_110;
            END IF;
            proc_14(V_COL_109, V_COL_107, V_COL_108);
            EXECUTE IMMEDIATE V_COL_109 USING V_COL_97, V_COL_31, V_COL_23, V_COL_15, V_COL_18, V_COL_98, V_COL_99, V_COL_108;
    END IF;
END;
/

-- SET QUOTED_IDENTIFIER OFF
-- SET ANSI_NULLS ON
-- xxx xxxxxx xxxxxx xxxxxx

-- xxxxxx xxxxxx xxxxxx
-- UNIQUE: Unhandled expression type: Execute
-- SET QUOTED_IDENTIFIER ON
-- SET ANSI_NULLS ON
CREATE OR REPLACE PROCEDURE proc_15
(
    V_COL_100 IN NUMBER DEFAULT NULL,
    V_COL_101 IN NUMBER DEFAULT NULL,
    V_COL_102 IN NUMBER DEFAULT NULL,
    V_COL_103 IN VARCHAR2 DEFAULT NULL,
    V_COL_104 IN DATE DEFAULT NULL,
    V_COL_105 IN NUMBER DEFAULT NULL,
    V_COL_106 IN VARCHAR2 DEFAULT NULL
)
IS
    --    <nombre>xxxxxx</nombre>
BEGIN
    /* UNIQUE: SET NOCOUNT ON -- tsql-only, no oracle equivalent */
    DELETE FROM tbl_7
    WHERE col_97 = V_COL_100 AND col_31 = V_COL_101 AND col_23 = V_COL_102 AND (col_15 = V_COL_103 OR col_15 IS NULL AND V_COL_103 IS NULL) AND (col_18 = V_COL_104 OR col_18 IS NULL AND V_COL_104 IS NULL) AND (col_98 = V_COL_105 OR col_98 IS NULL AND V_COL_105 IS NULL) AND (col_99 = V_COL_106 OR col_99 IS NULL AND V_COL_106 IS NULL);
    -- xx xx xx xxxxxx xx xxxxxx xxxxxx xxxxx
    IF SQL%ROWCOUNT <> 1 THEN
            RAISE_APPLICATION_ERROR(-20001, 16947);
    END IF;
END;
/

-- SET QUOTED_IDENTIFIER OFF
-- SET ANSI_NULLS ON
-- xxx xxxxxx xxxxxx xxxxxx

-- xxxxxx xxxxxx xxxxxx
-- UNIQUE: Unhandled expression type: Execute
-- SET QUOTED_IDENTIFIER ON
-- SET ANSI_NULLS ON
CREATE OR REPLACE PROCEDURE proc_16
(
    V_COL_93 IN NUMBER DEFAULT NULL,
    V_COL_15 IN VARCHAR2 DEFAULT NULL,
    V_COL_18 IN DATE DEFAULT NULL,
    V_COL_31 IN NUMBER DEFAULT NULL,
    V_COL_39 IN NUMBER DEFAULT NULL,
    V_COL_94 IN DATE DEFAULT NULL,
    V_COL_112 IN NUMBER DEFAULT NULL,
    V_COL_103 IN VARCHAR2 DEFAULT NULL,
    V_COL_104 IN DATE DEFAULT NULL,
    V_COL_101 IN NUMBER DEFAULT NULL,
    V_COL_113 IN NUMBER DEFAULT NULL,
    V_COL_114 IN DATE DEFAULT NULL
)
IS
    --    <nombre>xxxxxx</nombre>
BEGIN
    /* UNIQUE: SET NOCOUNT ON -- tsql-only, no oracle equivalent */
    UPDATE tbl_8
    SET col_15 = V_COL_15, col_18 = V_COL_18, col_31 = V_COL_31, col_39 = V_COL_39, col_94 = V_COL_94
    WHERE col_93 = V_COL_112 AND (col_15 = V_COL_103 OR col_15 IS NULL AND V_COL_103 IS NULL) AND (col_18 = V_COL_104 OR col_18 IS NULL AND V_COL_104 IS NULL) AND (col_31 = V_COL_101 OR col_31 IS NULL AND V_COL_101 IS NULL) AND (col_39 = V_COL_113 OR col_39 IS NULL AND V_COL_113 IS NULL) AND (col_94 = V_COL_114 OR col_94 IS NULL AND V_COL_114 IS NULL);
    -- xx xx xx xxxxxx xx xxxxxx xxxxxx xxxxx
    IF SQL%ROWCOUNT <> 1 THEN
            RAISE_APPLICATION_ERROR(-20001, 16947);
    END IF;
    -- xxxxxx xx xxxxxx xxxx xx xxxxx xxxxxx
    IF V_COL_93 IS NULL THEN
            RAISE_APPLICATION_ERROR(-20001, 40302);
    END IF;
END;
/

-- SET QUOTED_IDENTIFIER OFF
-- SET ANSI_NULLS ON
-- xxx xxxxxx xxxxxx xxxxxx

-- xxxxxx xxxxxx xxxxxx
-- UNIQUE: Unhandled expression type: Execute
-- SET QUOTED_IDENTIFIER ON
-- SET ANSI_NULLS ON
CREATE OR REPLACE PROCEDURE proc_17
(
    V_COL_93 IN NUMBER DEFAULT NULL,
    V_COL_15 IN VARCHAR2 DEFAULT NULL,
    V_COL_18 IN DATE DEFAULT NULL,
    V_COL_31 IN NUMBER DEFAULT NULL,
    V_COL_39 IN NUMBER DEFAULT NULL,
    V_COL_94 IN DATE DEFAULT NULL,
    V_COL_107 IN VARCHAR2 DEFAULT NULL,
    V_COL_2 IN NUMBER DEFAULT NULL,
    RESULT_CURSOR OUT SYS_REFCURSOR
)
IS
    --    <nombre>xxxxxx</nombre>
    V_COL_108 VARCHAR2(4000);
    V_COL_109 NVARCHAR2(2000);
    V_COL_110 NVARCHAR2(2000);
BEGIN
    /* UNIQUE: SET NOCOUNT ON -- tsql-only, no oracle equivalent */
    IF ( V_COL_2 IS NOT NULL ) THEN
            /* UNIQUE: SET ROWCOUNT @col_2 -- tsql-only, no oracle equivalent */
            NULL;
    END IF;
    IF V_COL_93 IS NOT NULL AND V_COL_107 IS NULL THEN
            OPEN RESULT_CURSOR FOR SELECT col_93, col_15, col_18, col_31, col_39, col_94
            FROM tbl_8
            WHERE V_COL_93 = col_93 AND (col_93 = V_COL_93 OR V_COL_93 IS NULL) AND (col_15 = V_COL_15 OR V_COL_15 IS NULL) AND (col_18 = V_COL_18 OR V_COL_18 IS NULL) AND (col_31 = V_COL_31 OR V_COL_31 IS NULL) AND (col_39 = V_COL_39 OR V_COL_39 IS NULL) AND (col_94 = V_COL_94 OR V_COL_94 IS NULL);
    ELSE
            V_COL_109 := '
                        SELECT col_93, col_15, col_18, col_31, col_39, col_94
                        FROM tbl_8';
            proc_13(V_COL_110, 'xxxxxxxxxxxxx', '=', 'V_XXXXXXXXXXXXX', V_COL_93);
            proc_13(V_COL_110, 'xxxxxxxxxx', '=', 'V_XXXXXXXXXX', V_COL_15);
            proc_13(V_COL_110, 'xxxxxxxx', '=', 'V_XXXXXXXX', V_COL_18);
            proc_13(V_COL_110, 'xxxxxxxxxxxxx', '=', 'V_XXXXXXXXXXXXX', V_COL_31);
            proc_13(V_COL_110, 'xxxxxxxxxxxx', '=', 'V_XXXXXXXXXXXX', V_COL_39);
            proc_13(V_COL_110, 'xxxxx', '=', 'V_XXXXX', V_COL_94);
            IF V_COL_110 IS NOT NULL THEN
                        V_COL_109 := V_COL_109 || ' WHERE ' || V_COL_110;
            END IF;
            proc_14(V_COL_109, V_COL_107, V_COL_108);
            EXECUTE IMMEDIATE V_COL_109 USING V_COL_93, V_COL_15, V_COL_18, V_COL_31, V_COL_39, V_COL_94, V_COL_108;
    END IF;
END;
/

-- SET QUOTED_IDENTIFIER OFF
-- SET ANSI_NULLS ON
-- xxx xxxxxx xxxxxx xxxxxx

-- xxxxxx xxxxxx xxxxxx
-- UNIQUE: Unhandled expression type: Execute
-- SET QUOTED_IDENTIFIER ON
-- SET ANSI_NULLS ON
CREATE OR REPLACE PROCEDURE proc_18
(
    V_COL_112 IN NUMBER DEFAULT NULL,
    V_COL_103 IN VARCHAR2 DEFAULT NULL,
    V_COL_104 IN DATE DEFAULT NULL,
    V_COL_101 IN NUMBER DEFAULT NULL,
    V_COL_113 IN NUMBER DEFAULT NULL,
    V_COL_114 IN DATE DEFAULT NULL
)
IS
    --    <nombre>xxxxxx</nombre>
BEGIN
    /* UNIQUE: SET NOCOUNT ON -- tsql-only, no oracle equivalent */
    DELETE FROM tbl_8
    WHERE col_93 = V_COL_112 AND (col_15 = V_COL_103 OR col_15 IS NULL AND V_COL_103 IS NULL) AND (col_18 = V_COL_104 OR col_18 IS NULL AND V_COL_104 IS NULL) AND (col_31 = V_COL_101 OR col_31 IS NULL AND V_COL_101 IS NULL) AND (col_39 = V_COL_113 OR col_39 IS NULL AND V_COL_113 IS NULL) AND (col_94 = V_COL_114 OR col_94 IS NULL AND V_COL_114 IS NULL);
    -- xx xx xx xxxxxx xx xxxxxx xxxxxx xxxxx
    IF SQL%ROWCOUNT <> 1 THEN
            RAISE_APPLICATION_ERROR(-20001, 16947);
    END IF;
END;
/

-- SET QUOTED_IDENTIFIER OFF
-- SET ANSI_NULLS ON
-- xxx xxxxxx xxxxxx xxxxxx

-- xxxxxx xxxxxx xxxxxx
-- UNIQUE: Unhandled expression type: Execute
-- SET QUOTED_IDENTIFIER ON
-- SET ANSI_NULLS ON
CREATE OR REPLACE PROCEDURE proc_19
(
    V_COL_31 IN NUMBER DEFAULT NULL,
    V_COL_6 IN RAW DEFAULT NULL,
    V_COL_32 IN NUMBER DEFAULT NULL,
    V_COL_33 IN DATE DEFAULT NULL,
    V_COL_12 IN NUMBER DEFAULT NULL,
    V_COL_42 IN NUMBER DEFAULT NULL,
    V_COL_62 IN VARCHAR2 DEFAULT NULL,
    V_COL_13 IN NUMBER DEFAULT NULL,
    V_COL_9 IN VARCHAR2 DEFAULT NULL,
    V_COL_10 IN VARCHAR2 DEFAULT NULL,
    V_COL_74 IN VARCHAR2 DEFAULT NULL,
    V_COL_38 IN VARCHAR2 DEFAULT NULL,
    V_COL_95 IN VARCHAR2 DEFAULT NULL,
    V_COL_96 IN VARCHAR2 DEFAULT NULL,
    V_COL_72 IN VARCHAR2 DEFAULT NULL,
    V_COL_73 IN VARCHAR2 DEFAULT NULL,
    V_COL_63 IN VARCHAR2 DEFAULT NULL,
    V_COL_19 IN VARCHAR2 DEFAULT NULL,
    V_COL_20 IN DATE DEFAULT NULL,
    V_COL_15 IN VARCHAR2 DEFAULT NULL,
    V_COL_18 IN DATE DEFAULT NULL,
    V_COL_101 IN NUMBER DEFAULT NULL,
    V_COL_115 IN RAW DEFAULT NULL,
    V_COL_116 IN NUMBER DEFAULT NULL,
    V_COL_117 IN DATE DEFAULT NULL,
    V_COL_118 IN NUMBER DEFAULT NULL,
    V_COL_119 IN NUMBER DEFAULT NULL,
    V_COL_120 IN VARCHAR2 DEFAULT NULL,
    V_COL_121 IN NUMBER DEFAULT NULL,
    V_COL_122 IN VARCHAR2 DEFAULT NULL,
    V_COL_123 IN VARCHAR2 DEFAULT NULL,
    V_COL_124 IN VARCHAR2 DEFAULT NULL,
    V_COL_125 IN VARCHAR2 DEFAULT NULL,
    V_COL_126 IN VARCHAR2 DEFAULT NULL,
    V_COL_127 IN VARCHAR2 DEFAULT NULL,
    V_COL_128 IN VARCHAR2 DEFAULT NULL,
    V_COL_129 IN VARCHAR2 DEFAULT NULL,
    V_COL_130 IN VARCHAR2 DEFAULT NULL,
    V_COL_131 IN VARCHAR2 DEFAULT NULL,
    V_COL_132 IN DATE DEFAULT NULL,
    V_COL_103 IN VARCHAR2 DEFAULT NULL,
    V_COL_104 IN DATE DEFAULT NULL
)
IS
    --    <nombre>xxxxxx</nombre>
BEGIN
    /* UNIQUE: SET NOCOUNT ON -- tsql-only, no oracle equivalent */
    UPDATE tbl_6
    SET col_6 = V_COL_6, col_32 = V_COL_32, col_33 = V_COL_33, col_12 = V_COL_12, col_42 = V_COL_42, col_62 = V_COL_62, col_13 = V_COL_13, col_9 = V_COL_9, col_10 = V_COL_10, col_74 = V_COL_74, col_38 = V_COL_38, col_95 = V_COL_95, col_96 = V_COL_96, col_72 = V_COL_72, col_73 = V_COL_73, col_63 = V_COL_63, col_19 = V_COL_19, col_20 = V_COL_20, col_15 = V_COL_15, col_18 = V_COL_18
    WHERE col_31 = V_COL_101 AND (col_6 = V_COL_115 OR col_6 IS NULL AND V_COL_115 IS NULL) AND (col_32 = V_COL_116 OR col_32 IS NULL AND V_COL_116 IS NULL) AND (col_33 = V_COL_117 OR col_33 IS NULL AND V_COL_117 IS NULL) AND (col_12 = V_COL_118 OR col_12 IS NULL AND V_COL_118 IS NULL) AND (col_42 = V_COL_119 OR col_42 IS NULL AND V_COL_119 IS NULL) AND (col_62 = V_COL_120 OR col_62 IS NULL AND V_COL_120 IS NULL) AND (col_13 = V_COL_121 OR col_13 IS NULL AND V_COL_121 IS NULL) AND (col_9 = V_COL_122 OR col_9 IS NULL AND V_COL_122 IS NULL) AND (col_10 = V_COL_123 OR col_10 IS NULL AND V_COL_123 IS NULL) AND (col_74 = V_COL_124 OR col_74 IS NULL AND V_COL_124 IS NULL) AND (col_38 = V_COL_125 OR col_38 IS NULL AND V_COL_125 IS NULL) AND (col_95 = V_COL_126 OR col_95 IS NULL AND V_COL_126 IS NULL) AND (col_96 = V_COL_127 OR col_96 IS NULL AND V_COL_127 IS NULL) AND (col_72 = V_COL_128 OR col_72 IS NULL AND V_COL_128 IS NULL) AND (col_73 = V_COL_129 OR col_73 IS NULL AND V_COL_129 IS NULL) AND (col_63 = V_COL_130 OR col_63 IS NULL AND V_COL_130 IS NULL) AND (col_19 = V_COL_131 OR col_19 IS NULL AND V_COL_131 IS NULL) AND (col_20 = V_COL_132 OR col_20 IS NULL AND V_COL_132 IS NULL) AND (col_15 = V_COL_103 OR col_15 IS NULL AND V_COL_103 IS NULL) AND (col_18 = V_COL_104 OR col_18 IS NULL AND V_COL_104 IS NULL);
    -- xx xx xx xxxxxx xx xxxxxx xxxxxx xxxxx
    IF SQL%ROWCOUNT <> 1 THEN
            RAISE_APPLICATION_ERROR(-20001, 16947);
    END IF;
    -- xxxxxx xx xxxxxx xxxx xx xxxxx xxxxxx
    IF V_COL_31 IS NULL THEN
            RAISE_APPLICATION_ERROR(-20001, 40302);
    END IF;
END;
/

-- SET QUOTED_IDENTIFIER OFF
-- SET ANSI_NULLS ON
-- xxx xxxxxx xxxxxx xxxxxx

-- xxxxxx xxxxxx xxxxxx
-- UNIQUE: Unhandled expression type: Execute
-- SET QUOTED_IDENTIFIER ON
-- SET ANSI_NULLS ON
CREATE OR REPLACE PROCEDURE proc_20
(
    V_COL_31 IN NUMBER DEFAULT NULL,
    V_COL_6 IN RAW DEFAULT NULL,
    V_COL_32 IN NUMBER DEFAULT NULL,
    V_COL_33 IN DATE DEFAULT NULL,
    V_COL_12 IN NUMBER DEFAULT NULL,
    V_COL_42 IN NUMBER DEFAULT NULL,
    V_COL_62 IN VARCHAR2 DEFAULT NULL,
    V_COL_13 IN NUMBER DEFAULT NULL,
    V_COL_9 IN VARCHAR2 DEFAULT NULL,
    V_COL_10 IN VARCHAR2 DEFAULT NULL,
    V_COL_74 IN VARCHAR2 DEFAULT NULL,
    V_COL_38 IN VARCHAR2 DEFAULT NULL,
    V_COL_95 IN VARCHAR2 DEFAULT NULL,
    V_COL_96 IN VARCHAR2 DEFAULT NULL,
    V_COL_72 IN VARCHAR2 DEFAULT NULL,
    V_COL_73 IN VARCHAR2 DEFAULT NULL,
    V_COL_63 IN VARCHAR2 DEFAULT NULL,
    V_COL_19 IN VARCHAR2 DEFAULT NULL,
    V_COL_20 IN DATE DEFAULT NULL,
    V_COL_15 IN VARCHAR2 DEFAULT NULL,
    V_COL_18 IN DATE DEFAULT NULL,
    V_COL_107 IN VARCHAR2 DEFAULT NULL,
    V_COL_2 IN NUMBER DEFAULT NULL,
    RESULT_CURSOR OUT SYS_REFCURSOR
)
IS
    --    <nombre>xxxxxx</nombre>
    V_COL_108 VARCHAR2(4000);
    V_COL_109 NVARCHAR2(2000);
    V_COL_110 NVARCHAR2(2000);
BEGIN
    /* UNIQUE: SET NOCOUNT ON -- tsql-only, no oracle equivalent */
    IF ( V_COL_2 IS NOT NULL ) THEN
            /* UNIQUE: SET ROWCOUNT @col_2 -- tsql-only, no oracle equivalent */
            NULL;
    END IF;
    IF V_COL_31 IS NOT NULL AND V_COL_107 IS NULL THEN
            OPEN RESULT_CURSOR FOR SELECT col_31, col_6, col_32, col_33, col_12, col_42, col_62, col_13, col_9, col_10, col_74, col_38, col_95, col_96, col_72, col_73, col_63, col_19, col_20, col_15, col_18
            FROM tbl_6
            WHERE V_COL_31 = col_31 AND (col_31 = V_COL_31 OR V_COL_31 IS NULL) AND (col_6 = V_COL_6 OR V_COL_6 IS NULL) AND (col_32 = V_COL_32 OR V_COL_32 IS NULL) AND (col_33 = V_COL_33 OR V_COL_33 IS NULL) AND (col_12 = V_COL_12 OR V_COL_12 IS NULL) AND (col_42 = V_COL_42 OR V_COL_42 IS NULL) AND (col_62 = V_COL_62 OR V_COL_62 IS NULL) AND (col_13 = V_COL_13 OR V_COL_13 IS NULL) AND (col_9 = V_COL_9 OR V_COL_9 IS NULL) AND (col_10 = V_COL_10 OR V_COL_10 IS NULL) AND (col_74 = V_COL_74 OR V_COL_74 IS NULL) AND (col_38 = V_COL_38 OR V_COL_38 IS NULL) AND (col_95 = V_COL_95 OR V_COL_95 IS NULL) AND (col_96 = V_COL_96 OR V_COL_96 IS NULL) AND (col_72 = V_COL_72 OR V_COL_72 IS NULL) AND (col_73 = V_COL_73 OR V_COL_73 IS NULL) AND (col_63 = V_COL_63 OR V_COL_63 IS NULL) AND (col_19 = V_COL_19 OR V_COL_19 IS NULL) AND (col_20 = V_COL_20 OR V_COL_20 IS NULL) AND (col_15 = V_COL_15 OR V_COL_15 IS NULL) AND (col_18 = V_COL_18 OR V_COL_18 IS NULL);
    ELSE
            V_COL_109 := '
                        SELECT col_31, col_6, col_32, col_33, col_12, col_42, col_62, col_13, col_9, col_10, col_74, col_38, col_95, col_96, col_72, col_73, col_63, col_19, col_20, col_15, col_18
                        FROM tbl_6';
            proc_13(V_COL_110, 'xxxxxxxxxxxxx', '=', 'V_XXXXXXXXXXXXX', V_COL_31);
            proc_13(V_COL_110, 'xxxx', '=', 'V_XXXX', V_COL_6);
            proc_13(V_COL_110, 'xxxxxxxx', '=', 'V_XXXXXXXX', V_COL_32);
            proc_13(V_COL_110, 'xxxxxxxx', '=', 'V_XXXXXXXX', V_COL_33);
            proc_13(V_COL_110, 'xxxxxxxxxxx', '=', 'V_XXXXXXXXXXX', V_COL_12);
            proc_13(V_COL_110, 'xxxxxxxxx', '=', 'V_XXXXXXXXX', V_COL_42);
            proc_13(V_COL_110, 'xxxxxxx', '=', 'V_XXXXXXX', V_COL_62);
            proc_13(V_COL_110, 'xxxxxxxx', '=', 'V_XXXXXXXX', V_COL_13);
            proc_13(V_COL_110, 'xxxxxxxxxxxxx', '=', 'V_XXXXXXXXXXXXX', V_COL_9);
            proc_13(V_COL_110, 'xxxxxxxxxxxxx', '=', 'V_XXXXXXXXXXXXX', V_COL_10);
            proc_13(V_COL_110, 'xxxxx', '=', 'V_XXXXX', V_COL_74);
            proc_13(V_COL_110, 'xxxxxxxxxx', '=', 'V_XXXXXXXXXX', V_COL_38);
            proc_13(V_COL_110, 'xxxxxxxxxxxxxxxx', '=', 'V_XXXXXXXXXXXXXXXX', V_COL_95);
            proc_13(V_COL_110, 'xxxxxxxxxxxxxx', '=', 'V_XXXXXXXXXXXXXX', V_COL_96);
            proc_13(V_COL_110, 'xxxx', '=', 'V_XXXX', V_COL_72);
            proc_13(V_COL_110, 'xxxxx', '=', 'V_XXXXX', V_COL_73);
            proc_13(V_COL_110, 'xxxxxx', '=', 'V_XXXXXX', V_COL_63);
            proc_13(V_COL_110, 'xxxxxxxxxxx', '=', 'V_XXXXXXXXXXX', V_COL_19);
            proc_13(V_COL_110, 'xxxxxxxxx', '=', 'V_XXXXXXXXX', V_COL_20);
            proc_13(V_COL_110, 'xxxxxxxxxx', '=', 'V_XXXXXXXXXX', V_COL_15);
            proc_13(V_COL_110, 'xxxxxxxx', '=', 'V_XXXXXXXX', V_COL_18);
            IF V_COL_110 IS NOT NULL THEN
                        V_COL_109 := V_COL_109 || ' WHERE ' || V_COL_110;
            END IF;
            proc_14(V_COL_109, V_COL_107, V_COL_108);
            EXECUTE IMMEDIATE V_COL_109 USING V_COL_31, V_COL_6, V_COL_32, V_COL_33, V_COL_12, V_COL_42, V_COL_62, V_COL_13, V_COL_9, V_COL_10, V_COL_74, V_COL_38, V_COL_95, V_COL_96, V_COL_72, V_COL_73, V_COL_63, V_COL_19, V_COL_20, V_COL_15, V_COL_18, V_COL_108;
    END IF;
END;
/

-- SET QUOTED_IDENTIFIER OFF
-- SET ANSI_NULLS ON
-- xxx xxxxxx xxxxxx xxxxxx

-- xxxxxx xxxxxx xxxxxx
-- UNIQUE: Unhandled expression type: Execute
-- SET QUOTED_IDENTIFIER ON
-- SET ANSI_NULLS ON
CREATE OR REPLACE PROCEDURE proc_21
(
    V_COL_101 IN NUMBER DEFAULT NULL,
    V_COL_115 IN RAW DEFAULT NULL,
    V_COL_116 IN NUMBER DEFAULT NULL,
    V_COL_117 IN DATE DEFAULT NULL,
    V_COL_118 IN NUMBER DEFAULT NULL,
    V_COL_119 IN NUMBER DEFAULT NULL,
    V_COL_120 IN VARCHAR2 DEFAULT NULL,
    V_COL_121 IN NUMBER DEFAULT NULL,
    V_COL_122 IN VARCHAR2 DEFAULT NULL,
    V_COL_123 IN VARCHAR2 DEFAULT NULL,
    V_COL_124 IN VARCHAR2 DEFAULT NULL,
    V_COL_125 IN VARCHAR2 DEFAULT NULL,
    V_COL_126 IN VARCHAR2 DEFAULT NULL,
    V_COL_127 IN VARCHAR2 DEFAULT NULL,
    V_COL_128 IN VARCHAR2 DEFAULT NULL,
    V_COL_129 IN VARCHAR2 DEFAULT NULL,
    V_COL_130 IN VARCHAR2 DEFAULT NULL,
    V_COL_131 IN VARCHAR2 DEFAULT NULL,
    V_COL_132 IN DATE DEFAULT NULL,
    V_COL_103 IN VARCHAR2 DEFAULT NULL,
    V_COL_104 IN DATE DEFAULT NULL
)
IS
    --    <nombre>xxxxxx</nombre>
BEGIN
    /* UNIQUE: SET NOCOUNT ON -- tsql-only, no oracle equivalent */
    DELETE FROM tbl_6
    WHERE col_31 = V_COL_101 AND (col_6 = V_COL_115 OR col_6 IS NULL AND V_COL_115 IS NULL) AND (col_32 = V_COL_116 OR col_32 IS NULL AND V_COL_116 IS NULL) AND (col_33 = V_COL_117 OR col_33 IS NULL AND V_COL_117 IS NULL) AND (col_12 = V_COL_118 OR col_12 IS NULL AND V_COL_118 IS NULL) AND (col_42 = V_COL_119 OR col_42 IS NULL AND V_COL_119 IS NULL) AND (col_62 = V_COL_120 OR col_62 IS NULL AND V_COL_120 IS NULL) AND (col_13 = V_COL_121 OR col_13 IS NULL AND V_COL_121 IS NULL) AND (col_9 = V_COL_122 OR col_9 IS NULL AND V_COL_122 IS NULL) AND (col_10 = V_COL_123 OR col_10 IS NULL AND V_COL_123 IS NULL) AND (col_74 = V_COL_124 OR col_74 IS NULL AND V_COL_124 IS NULL) AND (col_38 = V_COL_125 OR col_38 IS NULL AND V_COL_125 IS NULL) AND (col_95 = V_COL_126 OR col_95 IS NULL AND V_COL_126 IS NULL) AND (col_96 = V_COL_127 OR col_96 IS NULL AND V_COL_127 IS NULL) AND (col_72 = V_COL_128 OR col_72 IS NULL AND V_COL_128 IS NULL) AND (col_73 = V_COL_129 OR col_73 IS NULL AND V_COL_129 IS NULL) AND (col_63 = V_COL_130 OR col_63 IS NULL AND V_COL_130 IS NULL) AND (col_19 = V_COL_131 OR col_19 IS NULL AND V_COL_131 IS NULL) AND (col_20 = V_COL_132 OR col_20 IS NULL AND V_COL_132 IS NULL) AND (col_15 = V_COL_103 OR col_15 IS NULL AND V_COL_103 IS NULL) AND (col_18 = V_COL_104 OR col_18 IS NULL AND V_COL_104 IS NULL);
    -- xx xx xx xxxxxx xx xxxxxx xxxxxx xxxxx
    IF SQL%ROWCOUNT <> 1 THEN
            RAISE_APPLICATION_ERROR(-20001, 16947);
    END IF;
END;
/

-- SET QUOTED_IDENTIFIER OFF
-- SET ANSI_NULLS ON
-- xxx xxxxxx xxxxxx xxxxxx

-- xxxxxx xxxxxx xxxxxx
-- UNIQUE: Unhandled expression type: Execute
-- SET QUOTED_IDENTIFIER ON
-- SET ANSI_NULLS ON
CREATE OR REPLACE PROCEDURE proc_22
(
    V_COL_6 IN RAW DEFAULT NULL,
    V_COL_7 IN NUMBER DEFAULT NULL,
    V_COL_91 IN VARCHAR2 DEFAULT NULL,
    V_COL_19 IN VARCHAR2 DEFAULT NULL,
    V_COL_20 IN DATE DEFAULT NULL,
    V_COL_15 IN VARCHAR2 DEFAULT NULL,
    V_COL_18 IN DATE DEFAULT NULL,
    V_COL_115 IN RAW DEFAULT NULL,
    V_COL_133 IN NUMBER DEFAULT NULL,
    V_COL_134 IN VARCHAR2 DEFAULT NULL,
    V_COL_131 IN VARCHAR2 DEFAULT NULL,
    V_COL_132 IN DATE DEFAULT NULL,
    V_COL_103 IN VARCHAR2 DEFAULT NULL,
    V_COL_104 IN DATE DEFAULT NULL
)
IS
    --    <nombre>xxxxxx</nombre>
BEGIN
    /* UNIQUE: SET NOCOUNT ON -- tsql-only, no oracle equivalent */
    UPDATE tbl_3
    SET col_7 = V_COL_7, col_91 = V_COL_91, col_19 = V_COL_19, col_20 = V_COL_20, col_15 = V_COL_15, col_18 = V_COL_18
    WHERE col_6 = V_COL_115 AND (col_7 = V_COL_133 OR col_7 IS NULL AND V_COL_133 IS NULL) AND (col_91 = V_COL_134 OR col_91 IS NULL AND V_COL_134 IS NULL) AND (col_19 = V_COL_131 OR col_19 IS NULL AND V_COL_131 IS NULL) AND (col_20 = V_COL_132 OR col_20 IS NULL AND V_COL_132 IS NULL) AND (col_15 = V_COL_103 OR col_15 IS NULL AND V_COL_103 IS NULL) AND (col_18 = V_COL_104 OR col_18 IS NULL AND V_COL_104 IS NULL);
    -- xx xx xx xxxxxx xx xxxxxx xxxxxx xxxxx
    IF SQL%ROWCOUNT <> 1 THEN
            RAISE_APPLICATION_ERROR(-20001, 16947);
    END IF;
    -- xxxxxx xx xxxxxx xxxx xx xxxxx xxxxxx
    IF V_COL_6 IS NULL THEN
            RAISE_APPLICATION_ERROR(-20001, 40302);
    END IF;
END;
/

-- SET QUOTED_IDENTIFIER OFF
-- SET ANSI_NULLS ON
-- xxx xxxxxx xxxxxx xxxxxx

-- xxxxxx xxxxxx xxxxxx
-- UNIQUE: Unhandled expression type: Execute
-- SET QUOTED_IDENTIFIER ON
-- SET ANSI_NULLS ON
CREATE OR REPLACE PROCEDURE proc_23
(
    V_COL_6 IN RAW DEFAULT NULL,
    V_COL_7 IN NUMBER DEFAULT NULL,
    V_COL_91 IN VARCHAR2 DEFAULT NULL,
    V_COL_19 IN VARCHAR2 DEFAULT NULL,
    V_COL_20 IN DATE DEFAULT NULL,
    V_COL_15 IN VARCHAR2 DEFAULT NULL,
    V_COL_18 IN DATE DEFAULT NULL,
    V_COL_107 IN VARCHAR2 DEFAULT NULL,
    V_COL_2 IN NUMBER DEFAULT NULL,
    RESULT_CURSOR OUT SYS_REFCURSOR
)
IS
    --    <nombre>xxxxxx</nombre>
    V_COL_108 VARCHAR2(4000);
    V_COL_109 NVARCHAR2(2000);
    V_COL_110 NVARCHAR2(2000);
BEGIN
    /* UNIQUE: SET NOCOUNT ON -- tsql-only, no oracle equivalent */
    IF ( V_COL_2 IS NOT NULL ) THEN
            /* UNIQUE: SET ROWCOUNT @col_2 -- tsql-only, no oracle equivalent */
            NULL;
    END IF;
    IF V_COL_6 IS NOT NULL AND V_COL_107 IS NULL THEN
            OPEN RESULT_CURSOR FOR SELECT col_6, col_7, col_91, col_19, col_20, col_15, col_18
            FROM tbl_3
            WHERE V_COL_6 = col_6 AND (col_6 = V_COL_6 OR V_COL_6 IS NULL) AND (col_7 = V_COL_7 OR V_COL_7 IS NULL) AND (col_91 = V_COL_91 OR V_COL_91 IS NULL) AND (col_19 = V_COL_19 OR V_COL_19 IS NULL) AND (col_20 = V_COL_20 OR V_COL_20 IS NULL) AND (col_15 = V_COL_15 OR V_COL_15 IS NULL) AND (col_18 = V_COL_18 OR V_COL_18 IS NULL);
    ELSE
            V_COL_109 := '
                        SELECT col_6, col_7, col_91, col_19, col_20, col_15, col_18
                        FROM tbl_3';
            proc_13(V_COL_110, 'xxxx', '=', 'V_XXXX', V_COL_6);
            proc_13(V_COL_110, 'xxxxxxx', '=', 'V_XXXXXXX', V_COL_7);
            proc_13(V_COL_110, 'xxxxxxxxxx', '=', 'V_XXXXXXXXXX', V_COL_91);
            proc_13(V_COL_110, 'xxxxxxxxxxx', '=', 'V_XXXXXXXXXXX', V_COL_19);
            proc_13(V_COL_110, 'xxxxxxxxx', '=', 'V_XXXXXXXXX', V_COL_20);
            proc_13(V_COL_110, 'xxxxxxxxxx', '=', 'V_XXXXXXXXXX', V_COL_15);
            proc_13(V_COL_110, 'xxxxxxxx', '=', 'V_XXXXXXXX', V_COL_18);
            IF V_COL_110 IS NOT NULL THEN
                        V_COL_109 := V_COL_109 || ' WHERE ' || V_COL_110;
            END IF;
            proc_14(V_COL_109, V_COL_107, V_COL_108);
            EXECUTE IMMEDIATE V_COL_109 USING V_COL_6, V_COL_7, V_COL_91, V_COL_19, V_COL_20, V_COL_15, V_COL_18, V_COL_108;
    END IF;
END;
/

-- SET QUOTED_IDENTIFIER OFF
-- SET ANSI_NULLS ON
-- xxx xxxxxx xxxxxx xxxxxx

-- xxxxxx xxxxxx xxxxxx
-- UNIQUE: Unhandled expression type: Execute
-- SET QUOTED_IDENTIFIER ON
-- SET ANSI_NULLS ON
CREATE OR REPLACE PROCEDURE proc_24
(
    V_COL_115 IN RAW DEFAULT NULL,
    V_COL_133 IN NUMBER DEFAULT NULL,
    V_COL_134 IN VARCHAR2 DEFAULT NULL,
    V_COL_131 IN VARCHAR2 DEFAULT NULL,
    V_COL_132 IN DATE DEFAULT NULL,
    V_COL_103 IN VARCHAR2 DEFAULT NULL,
    V_COL_104 IN DATE DEFAULT NULL
)
IS
    --    <nombre>xxxxxx</nombre>
BEGIN
    /* UNIQUE: SET NOCOUNT ON -- tsql-only, no oracle equivalent */
    DELETE FROM tbl_3
    WHERE col_6 = V_COL_115 AND (col_7 = V_COL_133 OR col_7 IS NULL AND V_COL_133 IS NULL) AND (col_91 = V_COL_134 OR col_91 IS NULL AND V_COL_134 IS NULL) AND (col_19 = V_COL_131 OR col_19 IS NULL AND V_COL_131 IS NULL) AND (col_20 = V_COL_132 OR col_20 IS NULL AND V_COL_132 IS NULL) AND (col_15 = V_COL_103 OR col_15 IS NULL AND V_COL_103 IS NULL) AND (col_18 = V_COL_104 OR col_18 IS NULL AND V_COL_104 IS NULL);
    -- xx xx xx xxxxxx xx xxxxxx xxxxxx xxxxx
    IF SQL%ROWCOUNT <> 1 THEN
            RAISE_APPLICATION_ERROR(-20001, 16947);
    END IF;
END;
/

-- SET QUOTED_IDENTIFIER OFF
-- SET ANSI_NULLS ON
-- xxx xxxxxx xxxxxx xxxxxx

-- xxxxxx xxxxxx xxxxxx
-- UNIQUE: Unhandled expression type: Execute
-- SET QUOTED_IDENTIFIER ON
-- SET ANSI_NULLS ON
CREATE OR REPLACE PROCEDURE proc_25
(
    V_COL_1 IN NUMBER DEFAULT NULL,
    V_COL_135 IN DATE DEFAULT NULL,
    V_COL_136 IN DATE DEFAULT NULL,
    V_COL_137 IN VARCHAR2 DEFAULT NULL,
    V_COL_138 IN VARCHAR2 DEFAULT NULL,
    V_COL_139 IN VARCHAR2 DEFAULT NULL,
    V_COL_140 IN VARCHAR2 DEFAULT NULL,
    V_COL_141 IN VARCHAR2 DEFAULT NULL,
    V_COL_142 IN VARCHAR2 DEFAULT NULL,
    V_COL_143 IN VARCHAR2 DEFAULT NULL,
    V_COL_144 IN VARCHAR2 DEFAULT NULL,
    V_COL_145 IN VARCHAR2 DEFAULT NULL,
    V_COL_146 IN VARCHAR2 DEFAULT NULL,
    V_COL_2 IN NUMBER DEFAULT NULL,
    RESULT_CURSOR OUT SYS_REFCURSOR
)
IS
    --   <nombre>xxxxxx</nombre>
    V_FUNC1 DATE := func1 ( );
    V_COL_147 DATE;
BEGIN
    SELECT CAST ( func1 ( ) AS DATE ) INTO V_COL_147 FROM DUAL;
    /* UNIQUE: SET NOCOUNT ON -- tsql-only, no oracle equivalent */
    IF ( V_COL_2 IS NOT NULL ) THEN
            /* UNIQUE: SET ROWCOUNT @col_2 -- tsql-only, no oracle equivalent */
            NULL;
    END IF;
    OPEN RESULT_CURSOR FOR SELECT
      col_1,
      col_50,
      col_148,
      CASE
        WHEN col_148 = 'A'
        THEN V_COL_144
        WHEN col_148 = 'B'
        THEN V_COL_145
        WHEN col_148 = 'C'
        THEN V_COL_146
        ELSE V_COL_144
      END AS col_149,
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
        WHEN NOT col_156 IS NULL
        THEN V_COL_143
        WHEN NOT col_157 IS NULL
        THEN V_COL_143
        WHEN NOT col_158 IS NULL
        THEN V_COL_142
        WHEN NOT col_159 IS NULL
        THEN V_COL_141
        ELSE V_COL_140
      END AS col_160,
      col_159,
      col_158,
      col_157,
      col_156,
      col_161
    FROM (
      SELECT DISTINCT
        col_11.col_1,
        col_11.col_50,
        col_11.col_162 AS col_148,
        col_11.col_58 AS col_150,
        col_57.col_163 AS col_58,
        col_11.col_13,
        col_45.col_46 AS col_151,
        COALESCE(col_37.col_10, col_45.col_164, col_45.col_165, col_45.col_166) AS col_152,
        col_57.col_60 AS col_137,
        col_52.col_46 AS col_60,
        col_52.col_153,
        col_167.col_163 AS col_154,
        col_52.col_155 AS col_138,
        col_22.col_163 AS col_155,
        (
          SELECT
            MIN(col_40.col_94)
          FROM tbl_8 col_40
          WHERE
            col_40.col_31 IN (
              SELECT
                col_31
              FROM tbl_6 col_168
              WHERE
                col_168.col_6 = col_37.col_6 AND col_168.col_12 IN (0, 1) /* xxxxxx col_151 */
            )
            AND col_40.col_39 = 1 /* xxxxxx xx xx col_6 xx xxxxxx */
        ) AS col_159,
        (
          SELECT
            MIN(col_40.col_94)
          FROM tbl_8 col_40
          WHERE
            col_40.col_31 IN (
              SELECT
                col_31
              FROM tbl_6 col_168
              WHERE
                col_168.col_6 = col_37.col_6
                AND col_168.col_12 IN (0, 1, 2) /* xxxxxx col_151 col_60 */
            )
            AND col_40.col_39 = 3 /* xxxxxx xx xx xxxxxx */
        ) AS col_158,
        (
          SELECT
            MAX(col_40.col_94)
          FROM tbl_8 col_40
          WHERE
            col_40.col_31 IN (
              SELECT
                col_31
              FROM tbl_6 col_168
              WHERE
                col_168.col_6 = col_37.col_6
                AND col_168.col_12 IN (0, 1, 2) /* xxxxxx col_151 col_60 */
            )
            AND col_40.col_39 = 4 /* xxxxxx xx xx xxxxxx */
        ) AS col_157,
        (
          SELECT
            MAX(col_40.col_94)
          FROM tbl_8 col_40
          WHERE
            col_40.col_31 IN (
              SELECT
                col_31
              FROM tbl_6 col_168
              WHERE
                col_168.col_6 = col_37.col_6
                AND col_168.col_12 IN (0, 1) /* xxxxxx col_151 col_60 */
            )
            AND col_40.col_39 = 2 /* xxxxxx xx xx col_6 xx xxxxxx */
        ) AS col_156,
        COALESCE(
          (
            SELECT
              1
            FROM tbl_7
            WHERE
              col_31 = col_37.col_31
            ORDER BY
              col_31 ASC NULLS FIRST /* xxxxxx xx xx xxxxxx xx col_161 */
            FETCH FIRST 1 ROWS ONLY
          ),
          0
        ) AS col_161
      FROM tbl_1 col_11
      INNER JOIN tbl_2 col_56
        ON col_11.col_1 = col_56.col_1
      INNER JOIN tbl_6 col_37
        ON col_37.col_6 = col_56.col_6
      INNER JOIN tbl_10 col_45
        ON col_11.col_13 = col_45.col_13
      INNER JOIN tbl_11 col_57
        ON col_11.col_58 = col_57.col_59
      INNER JOIN tbl_12 col_52
        ON col_57.col_60 = col_52.col_59
      INNER JOIN tbl_14 col_167
        ON col_52.col_153 = col_167.col_153
      INNER JOIN tbl_15 col_22
        ON col_52.col_155 = col_22.col_59
      WHERE
        col_11.col_50 BETWEEN COALESCE(V_COL_135, V_COL_147) AND COALESCE(V_COL_136, V_FUNC1)
        AND col_37.col_12 = 1 /* col_151 */
        AND col_37.col_13 = col_11.col_13
        AND col_37.col_42 = 0
        AND (
          V_COL_1 IS NULL OR col_11.col_1 = V_COL_1
        )
        AND (
          V_COL_137 IS NULL OR col_57.col_60 = V_COL_137
        )
        AND (
          V_COL_138 IS NULL OR col_52.col_155 = V_COL_138
        )
        AND (
          V_COL_139 IS NULL
          OR col_11.col_162 IN (
            SELECT column_value FROM TABLE(FUNC5(V_COL_139, ','))
          )
        )
    ) col_160
    ORDER BY
      col_50 ASC NULLS FIRST;
END;
/

-- SET QUOTED_IDENTIFIER OFF
-- SET ANSI_NULLS ON
-- xxx xxxxxx xxxxxx xxxxxx

-- xxxxxx xxxxxx xxxxxx
-- UNIQUE: Unhandled expression type: Execute
-- SET QUOTED_IDENTIFIER ON
-- SET ANSI_NULLS ON
CREATE OR REPLACE PROCEDURE proc_26
(
    V_COL_1 IN NUMBER DEFAULT NULL,
    V_COL_13 IN NUMBER DEFAULT NULL,
    RESULT_CURSOR OUT SYS_REFCURSOR
)
IS
    --   <nombre>xxxxxx</nombre>
    V_FUNC1 DATE := func1 ( );
    V_COL_67 NUMBER(10);
BEGIN
    SELECT COALESCE((SELECT col_67 FROM tbl_9 WHERE col_30 = 1 ORDER BY col_66 ASC NULLS FIRST FETCH FIRST 1 ROWS ONLY), 1440) INTO V_COL_67 FROM DUAL;
    /* UNIQUE: SET NOCOUNT ON -- tsql-only, no oracle equivalent */
    -- xxxxxx xxx xxxxxx xx xx xxxxx xx xxxxxx
    -- xxxx xxx xxxx xxx xx x xxxxxx xxx xx xx xxxx xxxx xx xxxxxx
    UPDATE tbl_6
    SET col_32 = 0
    WHERE col_32 = 1 AND col_31 IN (SELECT col_171.col_31
    FROM tbl_6 col_171
    INNER JOIN tbl_2 col_56 ON col_56.col_6 = col_171.col_6
    INNER JOIN tbl_1 col_11 ON col_11.col_1 = col_56.col_1
    WHERE col_32 = 1 AND V_FUNC1 > col_11.col_50 + NUMTODSINTERVAL(V_COL_67, 'MINUTE'));
    UPDATE tbl_6 SET col_32 = 0 WHERE col_32 = 1 AND V_FUNC1 > COALESCE(col_33, V_FUNC1) + NUMTODSINTERVAL(5, 'MINUTE');
    OPEN RESULT_CURSOR FOR SELECT DISTINCT col_56.col_1
    FROM tbl_2 col_56
    WHERE EXISTS (SELECT NULL
    FROM tbl_6 col_37
    WHERE col_37.col_6 = col_56.col_6 AND col_37.col_32 = 1 AND (V_COL_13 IS NULL OR col_37.col_13 = V_COL_13)) AND (V_COL_1 IS NULL OR col_56.col_1 = V_COL_1);
END;
/

-- SET QUOTED_IDENTIFIER OFF
-- SET ANSI_NULLS ON
-- xxx xxxxxx xxxxxx xxxxxx

-- xxxxxx xxxxxx xxxxxx
-- UNIQUE: Unhandled expression type: Execute
-- SET QUOTED_IDENTIFIER ON
-- SET ANSI_NULLS ON
CREATE OR REPLACE PROCEDURE proc_27
(
    V_COL_1 IN NUMBER DEFAULT NULL,
    V_COL_2 IN NUMBER DEFAULT NULL
)
IS
    --   <nombre>xxxxxx</nombre>
    V_COL_6 RAW(16);
BEGIN
    SELECT ( SELECT col_6 FROM tbl_2 WHERE col_1 = V_COL_1 ) INTO V_COL_6 FROM DUAL;
    /* UNIQUE: SET NOCOUNT ON -- tsql-only, no oracle equivalent */
    IF ( V_COL_2 IS NOT NULL ) THEN
            /* UNIQUE: SET ROWCOUNT @col_2 -- tsql-only, no oracle equivalent */
            NULL;
    END IF;
    IF ( V_COL_6 IS NOT NULL ) THEN
            DELETE FROM tbl_8 WHERE col_31 IN (SELECT col_31 FROM tbl_6 WHERE col_6 = V_COL_6);
            DELETE FROM tbl_6 WHERE col_6 = V_COL_6;
            DELETE FROM tbl_2 WHERE col_1 = V_COL_1;
            DELETE FROM tbl_3 WHERE col_6 = V_COL_6;
    END IF;
END;
/

-- SET QUOTED_IDENTIFIER OFF
-- SET ANSI_NULLS ON
-- -- xxx xxxxxx xxxxxx xxxxxx

-- -- xxxxxx xxxxxx xxxxxx 

-- -- xxxxxx xxxxxx xxxxxx 
-- IF NOT OBJECT_ID(N'[col_173]') IS NULL
--     DROP TRIGGER [dbo].[col_173];
-- -- xxx xxxxxx xxxxxx xxxxxx

-- SET QUOTED_IDENTIFIER ON
-- SET ANSI_NULLS ON
CREATE OR REPLACE TRIGGER col_173
AFTER UPDATE ON tbl_6
DECLARE
    --   <nombre>xxxxxx</nombre>
    V_FUNC1 DATE := func1 ( );
    V_COL_174 NUMBER(10);
BEGIN
    SELECT COALESCE ( ( SELECT 1 FROM tbl_9 WHERE col_96 IS NOT NULL AND col_30 = 1 ) , 0 ) INTO V_COL_174 FROM DUAL;
    /* UNIQUE: SET NOCOUNT ON -- tsql-only, no oracle equivalent */
    IF UPDATING('col_32') THEN
            /* xxxxxx xxxx xxxxxx */
            -- UNIQUE: trigger uses the T-SQL set-based inserted/deleted pseudo-tables, which have no row-level (NEW/OLD) equivalent. Rewrite manually (PostgreSQL: a statement-level trigger with REFERENCING NEW TABLE AS inserted OLD TABLE AS deleted; Oracle: a compound trigger; MySQL: no transition tables). Original:
            -- INSERT INTO tbl_8 (col_15, col_18, col_31, col_39, col_94)
            -- SELECT col_175.col_15, col_175.col_18, col_175.col_31, 4 - (2 * V_COL_174 * (1 - col_175.col_42) + col_175.col_32) AS col_39, V_FUNC1 AS col_94
            -- FROM inserted col_175
            -- INNER JOIN deleted col_176 ON col_176.col_31 = col_175.col_31
            -- WHERE col_175.col_32 <> col_176.col_32
            NULL;
            /* xx xx xxxx xx xxxxxx xxxxxx xx xxxxx col_162 xx xxxxxx xxx x */
    END IF;
END;
/

-- SET QUOTED_IDENTIFIER OFF
-- SET ANSI_NULLS ON
-- xxx xxxxxx xxxxxx xxxxxx