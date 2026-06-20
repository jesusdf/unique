-- ============================================================
-- Stub definitions for anonymized custom functions (Oracle).
-- Self-contained, runnable placeholders preserving signatures.
-- ============================================================
CREATE OR REPLACE FUNCTION func1 RETURN DATE AS
BEGIN
    RETURN SYSDATE - 3;
END;
/
CREATE OR REPLACE FUNCTION func3(p_key VARCHAR2, p_def VARCHAR2) RETURN VARCHAR2 AS
BEGIN
    RETURN p_def;
END;
/
CREATE OR REPLACE FUNCTION func4(p_payload VARCHAR2, p_secret VARCHAR2) RETURN VARCHAR2 AS
BEGIN
    RETURN RAWTOHEX(DBMS_CRYPTO.HASH(UTL_RAW.CAST_TO_RAW(p_payload || p_secret), 4));
END;
/
CREATE OR REPLACE FUNCTION func6 RETURN VARCHAR2 AS
BEGIN
    RETURN RAWTOHEX(SYS_GUID());
END;
/
CREATE OR REPLACE TYPE func5_t AS TABLE OF VARCHAR2(4000);
/
CREATE OR REPLACE FUNCTION func5(p_s VARCHAR2, p_delim VARCHAR2) RETURN func5_t PIPELINED AS
    v_rest VARCHAR2(4000) := p_s;
    v_pos  PLS_INTEGER;
BEGIN
    LOOP
        v_pos := INSTR(v_rest, p_delim);
        IF v_pos = 0 THEN
            PIPE ROW (v_rest);
            EXIT;
        END IF;
        PIPE ROW (SUBSTR(v_rest, 1, v_pos - 1));
        v_rest := SUBSTR(v_rest, v_pos + 1);
    END LOOP;
    RETURN;
END;
/
CREATE OR REPLACE FUNCTION func7(p_stmt VARCHAR2, p_col VARCHAR2, p_op VARCHAR2, p_bind VARCHAR2) RETURN VARCHAR2 AS
BEGIN
    RETURN p_stmt || ' AND ' || p_col || ' ' || p_op || ' ' || p_bind;
END;
/
CREATE OR REPLACE FUNCTION func8(p_stmt VARCHAR2, p_filter VARCHAR2) RETURN VARCHAR2 AS
BEGIN
    RETURN p_stmt || ' ' || p_filter;
END;
/
CREATE OR REPLACE FUNCTION func9(p_stmt VARCHAR2, p_name VARCHAR2, p_val NUMBER) RETURN VARCHAR2 AS
BEGIN
    RETURN p_stmt || ' AND ROWNUM <= ' || TO_CHAR(p_val);
END;
/
CREATE OR REPLACE PROCEDURE func10(p_stmt VARCHAR2) AS
BEGIN
    DBMS_OUTPUT.PUT_LINE(p_stmt);
END;
/

-- xxxxxx

-- xxxxxx xxxxxx xxxxxx 

CREATE OR REPLACE PROCEDURE PROC_3 (
--   <nombre>xxxxxx</nombre>
   VAR_1 NUMBER := NULL,
   VAR_2 OUT COL_177.MYCURSOR
)
AS
    VAR_3 TBL_7.COL_99%TYPE := NULL;
BEGIN

    OPEN VAR_2 FOR
    SELECT
        COL_22.COL_23,
        COL_22.COL_24 AS COL_25,
        COL_22.COL_26 AS COL_27,
        VAR_3 AS VALUE,
        COL_22.COL_28 AS COL_29
    FROM
        TBL_5 COL_22
    WHERE
        COL_22.COL_30 = 1
        ORDER BY COL_22.COL_28 ASC;

END;
/
-- xxx xxxxxx xxxxxx xxxxxx

-- xxxxxx xxxxxx xxxxxx 

CREATE OR REPLACE PROCEDURE PROC_4 (
--   <nombre>xxxxxx</nombre>
   VAR_4 NUMBER := NULL,
   VAR_1 NUMBER := NULL,
   VAR_5 OUT COL_177.MYCURSOR
)
AS
    VAR_6 DATE := FUNC1();
    VAR_3 TBL_6.COL_38%TYPE := NULL;
BEGIN

    UPDATE TBL_6 SET COL_32=1, COL_18=VAR_6 WHERE COL_31=VAR_4 AND COL_32=0 AND NOT EXISTS (SELECT NULL FROM TBL_7 WHERE COL_31=VAR_4);
    UPDATE TBL_6 SET COL_33=VAR_6 WHERE COL_31=VAR_4 AND NOT EXISTS (SELECT NULL FROM TBL_7 WHERE COL_31=VAR_4);

    OPEN VAR_5 FOR
    SELECT COL_32, COL_34, COL_35, COL_36
    FROM
    (
        SELECT
            1 AS COL_32,
            COL_37.COL_38 COL_34,
            CAST(NULL AS VARCHAR(2000)) COL_35,
            COALESCE(
                (
                    SELECT 1
                    FROM TBL_8
                    WHERE COL_31=VAR_4
                        AND COL_39 = 3 /* xxxxxx xx xx xxxxxx */
                        AND ROWNUM = 1
                )
            , 0) COL_36
        FROM
            TBL_6 COL_37
            INNER JOIN TBL_8 COL_40 ON
                COL_40.COL_31 IN (
                        SELECT COL_31
                        FROM TBL_6 COL_41
                        WHERE
                            COL_41.COL_6=COL_37.COL_6
                            AND COL_32=1
                            AND COL_42=1 /* xxxxxx */
                    )
                AND COL_40.COL_39=3 /* xxxxxx xx xx xxxxxx */
        WHERE
            COL_37.COL_31 = VAR_4
            AND NOT EXISTS (
                SELECT NULL
                FROM TBL_7
                WHERE COL_31=VAR_4
                /* xx xx xx xxxxxx xx col_161 */
                AND EXISTS (SELECT NULL FROM TBL_9 WHERE COL_30=1 AND COL_43 IS NOT NULL)
            )
        UNION ALL
        SELECT
            0 AS COL_32,
            VAR_3 COL_34,
            CAST(NULL AS VARCHAR(2000)) COL_35,
            0 COL_36
        FROM
            DUAL
    ) COL_44
    WHERE
        ROWNUM = 1
    ORDER BY COL_32 DESC;

END;
/
-- xxx xxxxxx xxxxxx xxxxxx

-- xxxxxx xxxxxx xxxxxx 

CREATE OR REPLACE PROCEDURE PROC_5 (
--   <nombre>xxxxxx</nombre>
   VAR_4 NUMBER := NULL,
   VAR_1 NUMBER := NULL,
   VAR_5 OUT COL_177.MYCURSOR
)
AS
BEGIN

    OPEN VAR_5 FOR
    SELECT
        COL_45.COL_46 AS COL_47,
        COL_45.COL_48 AS COL_49,
        COL_11.COL_50 AS COL_51,
        COL_52.COL_46 AS COL_53,
        COALESCE(
            (
                SELECT 1
                FROM TBL_8
                WHERE COL_31=VAR_4
                    AND COL_39 = 1 /* xxxxxx xx xx col_6 xx xxxxxx */
                    AND ROWNUM = 1
            )
        , 0) COL_54,
        COALESCE(
            (
                SELECT 1
                FROM TBL_7
                WHERE COL_31=VAR_4
                    AND ROWNUM = 1
                /* xx xx xx xxxxxx xx col_161 */
                AND EXISTS (SELECT NULL FROM TBL_9 WHERE COL_30=1 AND COL_43 IS NOT NULL)
            )
        , 0) COL_55
    FROM
        TBL_6 COL_37
        INNER JOIN TBL_2 COL_56 ON COL_37.COL_6=COL_56.COL_6
        INNER JOIN TBL_1 COL_11 ON COL_56.COL_1=COL_11.COL_1
        INNER JOIN TBL_10 COL_45 ON COL_11.COL_13=COL_45.COL_13
        INNER JOIN TBL_11 COL_57 ON COL_11.COL_58=COL_57.COL_59
        INNER JOIN TBL_12 COL_52 ON COL_57.COL_60=COL_52.COL_59
    WHERE
        COL_37.COL_31 = VAR_4;

END;
/
-- xxx xxxxxx xxxxxx xxxxxx

-- xxxxxx xxxxxx xxxxxx 

CREATE OR REPLACE PROCEDURE PROC_6 (
--   <nombre>xxxxxx</nombre>
    VAR_7             IN TBL_9.COL_61%TYPE DEFAULT NULL, -- xxxxxx xxx xxxxxx xx tbl_9
    VAR_8              IN TBL_6.COL_6%TYPE DEFAULT NULL,
    VAR_9         IN TBL_6.COL_42%TYPE DEFAULT 0,
    VAR_10           IN TBL_6.COL_19%TYPE DEFAULT NULL,
    VAR_11          IN TBL_6.COL_13%TYPE DEFAULT NULL,
    VAR_12            IN TBL_6.COL_63%TYPE DEFAULT NULL,
    VAR_13     IN TBL_6.COL_9%TYPE DEFAULT NULL,
    VAR_14     IN TBL_6.COL_10%TYPE DEFAULT NULL,
    VAR_15        IN TBL_6.COL_74%TYPE DEFAULT NULL,
    VAR_16        IN TBL_6.COL_19%TYPE DEFAULT NULL,
    VAR_1   IN NUMBER DEFAULT NULL,
    VAR_5 OUT COL_177.MYCURSOR
)
AS
    VAR_6 DATE := FUNC1();
    VAR_17 NUMBER(9) := -1440;
    VAR_18 NUMBER(9) := 1440;
    VAR_19 DATE;
    VAR_20 DATE;
    VAR_21 DATE;
    VAR_22 VARCHAR2(36) := LOWER(VAR_8);
    VAR_23 VARCHAR2(200) := NULL;
    VAR_24 VARCHAR2(200) := NULL;
    VAR_25 VARCHAR2(4000) := NULL;
    VAR_26 NUMBER(9) := 0;
    VAR_27 VARCHAR2(50) := NULL;
    VAR_28 NUMBER(9) := NULL;
    VAR_29 NUMBER(9) := NULL;
BEGIN

    IF (VAR_8 IS NULL OR VAR_9 IS NULL) THEN
        RETURN;
    END IF;

    SELECT CASE WHEN VAR_9 = 1 THEN 2                              -- xxxxxx
                WHEN VAR_9 = 0 AND VAR_11 IS NOT NULL THEN 1   -- col_151
                ELSE 0 END                                               -- xxxxxx
         INTO
         VAR_29
    FROM DUAL;

    -- xx xx xx xxxxxx
    IF (VAR_29 = 2) THEN

        DELETE FROM TBL_6 WHERE COL_6=VAR_22 AND COL_42=1 AND COL_62=VAR_10;

        SELECT
            COL_76.COL_46, LOWER(COALESCE(COL_76.COL_77, VAR_10 || '@' || CAST(VAR_7 AS VARCHAR2(200))))
            INTO
            VAR_23, VAR_24
        FROM TBL_13 COL_76
        WHERE
            COL_76.COL_62 = VAR_10;
    END IF;

    -- xx xx xx xxxxxx
    IF (VAR_29 = 1) THEN

        DELETE FROM TBL_6 WHERE COL_6=VAR_22 AND COL_42=0 AND COL_13=VAR_11;

        SELECT
            COL_45.COL_46, LOWER(COALESCE(COL_45.COL_73, TO_CHAR(COL_45.COL_13) || '@' || CAST(VAR_7 AS VARCHAR2(200))))
            INTO
            VAR_23, VAR_24
        FROM TBL_2 COL_3
            INNER JOIN TBL_1 COL_11 ON COL_11.COL_1=COL_3.COL_1
            INNER JOIN TBL_10 COL_45 ON COL_45.COL_13=COL_11.COL_13
        WHERE
            COL_3.COL_6 = VAR_22;
    END IF;

    -- xx xx xx xxxxxx
    IF (VAR_29 = 0) THEN

        DELETE FROM TBL_6 WHERE COL_6=VAR_22 AND COL_42=0 AND COL_62=VAR_10 AND COL_13 IS NULL;

        SELECT
            VAR_10, LOWER(VAR_10 || '@' || CAST(VAR_7 AS VARCHAR2(200)))
            INTO
            VAR_23, VAR_24
        FROM DUAL;

    END IF;

    SELECT
        COL_11.COL_50 INTO VAR_19
    FROM TBL_2 COL_3
        INNER JOIN TBL_1 COL_11 ON COL_11.COL_1=COL_3.COL_1
    WHERE
        COL_3.COL_6 = VAR_22;

    -- xxxxxx xx xxxxxx xxx xxxxxx
    SELECT COALESCE((SELECT COL_65 FROM TBL_9 WHERE COL_30=1 AND ROWNUM = 1), -1440) INTO VAR_17 FROM DUAL;
    SELECT COALESCE((SELECT COL_67 FROM TBL_9 WHERE COL_30=1 AND ROWNUM = 1), 1440) INTO VAR_18 FROM DUAL;
    VAR_20 := VAR_19 + (1/1440 * VAR_17);
    VAR_21 := VAR_19 + (1/1440 * VAR_18);

    -- xxxxxx xxxx xxxxx xxxxx xxxxxx xxx xxxxxx xxx xxxxxx
    INSERT INTO TBL_6 (COL_12, COL_62, COL_13, COL_19, COL_20, COL_15, COL_18, COL_6, COL_72, COL_73, COL_63, COL_42, COL_74, COL_32, COL_9, COL_10)
    VALUES (VAR_29, VAR_10, VAR_11, VAR_16, VAR_6, VAR_16, VAR_6, VAR_22, VAR_23, VAR_24, VAR_12, VAR_9, '-', VAR_26, VAR_13, VAR_14)
    COL_178 COL_31 INTO VAR_28;

    -- xx xxxxxx xxx xxxxxx xxxx xx xxxxxx xxxxx xxx xxxxxx xx xx xxxxx
    VAR_27 := TO_CHAR(VAR_28);

    IF (VAR_15 IS NULL) THEN
        VAR_25 := FUNC2(VAR_7, VAR_20, VAR_21, VAR_27, VAR_22, VAR_23, VAR_24, VAR_12, VAR_9);
    ELSE
        VAR_25 := VAR_15;
    END IF;

    IF (COALESCE(VAR_25, 'xxxxxxx-xxxx') = 'xxxxxxx-xxxx') THEN
        DELETE FROM TBL_6 WHERE COL_31 = VAR_28;
    ELSE
        UPDATE TBL_6 SET COL_74=VAR_25 WHERE COL_31 = VAR_28;
    END IF;

    OPEN VAR_5 FOR
    SELECT COL_31, COL_74 FROM TBL_6 WHERE COL_31 = VAR_28;

END;
/
-- xxx xxxxxx xxxxxx xxxxxx

-- xxxxxx xxxxxx xxxxxx 

CREATE OR REPLACE PROCEDURE PROC_25 (
--   <nombre>xxxxxx</nombre>
    VAR_30 IN TBL_1.COL_1%TYPE DEFAULT NULL,
    VAR_31 IN TBL_1.COL_50%TYPE DEFAULT NULL,
    VAR_32 IN TBL_1.COL_50%TYPE DEFAULT NULL,
    VAR_33 IN TBL_12.COL_59%TYPE DEFAULT NULL,
    VAR_34 IN TBL_15.COL_59%TYPE DEFAULT NULL,
    VAR_35 VARCHAR2 DEFAULT NULL,
    VAR_36 VARCHAR2 DEFAULT NULL,
    VAR_37 VARCHAR2 DEFAULT NULL,
    VAR_38 VARCHAR2 DEFAULT NULL,
    VAR_39 VARCHAR2 DEFAULT NULL,
    VAR_40 VARCHAR2 DEFAULT NULL,
    VAR_41 VARCHAR2 DEFAULT NULL,
    VAR_42 VARCHAR2 DEFAULT NULL,
    VAR_1 NUMBER := NULL,
    VAR_43 OUT COL_177.MYCURSOR
)
AS
    VAR_6 DATE := FUNC1();
    VAR_44 DATE := TRUNC(VAR_6);
BEGIN

    OPEN VAR_43 FOR
    SELECT
        COL_1,
        COL_50,
        COL_148,
        CASE
            WHEN COL_148 = 'A' THEN VAR_40
            WHEN COL_148 = 'B' THEN VAR_41
            WHEN COL_148 = 'C' THEN VAR_42
        ELSE
            VAR_36
        END AS COL_149,
        COL_150,
        COL_58,
        COL_13,
        COL_151,
        COL_152,
        COL_137,
        COL_60,
        COL_153,
        COL_154,
        COL_138,
        COL_155,
        CASE
            WHEN COL_156 IS NOT NULL THEN VAR_39
            WHEN COL_157 IS NOT NULL THEN VAR_39
            WHEN COL_158 IS NOT NULL THEN VAR_38
            WHEN COL_159 IS NOT NULL THEN VAR_37
        ELSE
            VAR_36
        END
        AS COL_160,
        COL_159,
        COL_158,
        COL_157,
        COL_156,
        COL_161
    FROM (
    SELECT

        DISTINCT

        COL_11.COL_1,
        COL_11.COL_50,
        COL_11.COL_162 AS COL_148,
        COL_11.COL_58 AS COL_150,
        COL_57.COL_163 AS COL_58,
        COL_11.COL_13,
        COL_45.COL_46 AS COL_151,
        COALESCE(COL_37.COL_10, COL_45.COL_164, COL_45.COL_165, COL_45.COL_166) AS COL_152,
        COL_57.COL_60 AS COL_137,
        COL_52.COL_46 AS COL_60,
        COL_52.COL_153,
        COL_167.COL_163 AS COL_154,
        COL_52.COL_155 AS COL_138,
        COL_22.COL_163 AS COL_155,

        (SELECT MIN(COL_40.COL_94)
            FROM TBL_8 COL_40
            WHERE COL_40.COL_31 IN (
                SELECT COL_31 FROM TBL_6 COL_168
                WHERE COL_168.COL_6=COL_37.COL_6 AND COL_168.COL_12 IN (0, 1) /* xxxxxx col_151 */
            )
            AND COL_40.COL_39 = 1 /* xxxxxx xx xx col_6 xx xxxxxx */
        ) AS COL_159,

        (SELECT MIN(COL_40.COL_94)
            FROM TBL_8 COL_40
            WHERE COL_40.COL_31 IN (
                SELECT COL_31 FROM TBL_6 COL_168
                WHERE COL_168.COL_6=COL_37.COL_6 AND COL_168.COL_12 IN (0, 1, 2) /* xxxxxx col_151 col_60 */
            )
            AND COL_40.COL_39 = 3 /* xxxxxx xx xx xxxxxx */
        ) AS COL_158,

        (SELECT MAX(COL_40.COL_94)
            FROM TBL_8 COL_40
            WHERE COL_40.COL_31 IN (
                SELECT COL_31 FROM TBL_6 COL_168
                WHERE COL_168.COL_6=COL_37.COL_6 AND COL_168.COL_12 IN (0, 1, 2) /* xxxxxx col_151 col_60 */
            )
            AND COL_40.COL_39 = 4 /* xxxxxx xx xx xxxxxx */
        ) AS COL_157,

        (SELECT MAX(COL_40.COL_94)
            FROM TBL_8 COL_40
            WHERE COL_40.COL_31 IN (
                SELECT COL_31 FROM TBL_6 COL_168
                WHERE COL_168.COL_6=COL_37.COL_6 AND COL_168.COL_12 IN (0, 1) /* xxxxxx col_151 col_60 */
            )
            AND COL_40.COL_39 = 2 /* xxxxxx xx xx col_6 xx xxxxxx */
        ) AS COL_156,

        COALESCE(
        (
            SELECT 1
            FROM TBL_7
            WHERE COL_31=COL_37.COL_31
            AND ROWNUM = 1
            /* xxxxxx xx xx xxxxxx xx col_161 */
        )
        , 0) AS COL_161

    FROM
        TBL_1 COL_11
        INNER JOIN TBL_2 COL_56 ON COL_11.COL_1 = COL_56.COL_1
        INNER JOIN TBL_6 COL_37 ON COL_37.COL_6 = COL_56.COL_6
        INNER JOIN TBL_10 COL_45 ON COL_11.COL_13=COL_45.COL_13
        INNER JOIN TBL_11 COL_57 ON COL_11.COL_58=COL_57.COL_59
        INNER JOIN TBL_12 COL_52 ON COL_57.COL_60=COL_52.COL_59
        INNER JOIN TBL_14 COL_167 ON COL_52.COL_153=COL_167.COL_153
        INNER JOIN TBL_15 COL_22 ON COL_52.COL_155=COL_22.COL_59
    WHERE
        COL_11.COL_50 BETWEEN COALESCE(VAR_31, VAR_44) AND COALESCE(VAR_32, VAR_6)
        AND COL_37.COL_12 = 1 /* col_151 */
        AND COL_37.COL_13 = COL_11.COL_13
        AND COL_37.COL_42 = 0
        AND (VAR_30 IS NULL OR COL_11.COL_1 = VAR_30)
        AND (VAR_33 IS NULL OR COL_57.COL_60 = VAR_33)
        AND (VAR_34 IS NULL OR COL_52.COL_155 = VAR_34)
        AND (VAR_35 IS NULL OR COL_11.COL_162 IN (SELECT COL_179 FROM TABLE(FUNC5(VAR_35, ','))))
    ) COL_160
    ORDER BY COL_50 ASC;

END;
/
-- xxx xxxxxx xxxxxx xxxxxx

-- xxxxxx xxxxxx xxxxxx 

CREATE OR REPLACE PROCEDURE PROC_26 (
--   <nombre>xxxxxx</nombre>
    VAR_30 TBL_2.COL_1%TYPE DEFAULT NULL,
    VAR_11 TBL_1.COL_13%TYPE DEFAULT NULL,
    VAR_43 OUT COL_177.MYCURSOR
)
AS
    VAR_6 DATE := FUNC1();
    VAR_18 NUMBER(9) := 1440;
BEGIN

    SELECT COALESCE((SELECT COL_67 FROM TBL_9 WHERE COL_30=1 AND ROWNUM = 1), 1440) INTO VAR_18 FROM DUAL;

    -- xxxxxx xxx xxxxxx xxxxxx xxxxxx xx xxxxxx x xxxxxx
    UPDATE TBL_6
    SET COL_32 = 0
    WHERE
        COL_32 = 1
        AND COL_31 IN (
        SELECT COL_171.COL_31
        FROM TBL_6 COL_171
        INNER JOIN TBL_2 COL_56 ON COL_171.COL_6=COL_56.COL_6
        INNER JOIN TBL_1 COL_11 ON COL_56.COL_1=COL_11.COL_1
            WHERE
                COL_32 = 1 AND
                VAR_6 > (COL_11.COL_50 + (1/1440 * VAR_18))
        );

    -- xxxxxx xxx xxxxxx xx xx xxxxx xx xxxxxx
    -- xxxx xxx xxxx xxx xx x xxxxxx xxx xx xx xxxx xxxx xx xxxxxx
    UPDATE TBL_6
    SET COL_32 = 0
    WHERE
        COL_32 = 1
        AND VAR_6 > COALESCE(COL_33, VAR_6) + (1/1440 * 5);

    OPEN VAR_43 FOR
    SELECT
        DISTINCT
        COL_56.COL_1
    FROM TBL_2 COL_56
    WHERE
    EXISTS
    (
        SELECT NULL
        FROM TBL_6 COL_37
        WHERE
        COL_37.COL_6=COL_56.COL_6 AND
        COL_37.COL_32 = 1 AND
        (VAR_11 IS NULL OR COL_37.COL_13=VAR_11)
    )
    AND (VAR_30 IS NULL OR COL_56.COL_1=VAR_30);

END;
/
-- xxx xxxxxx xxxxxx xxxxxx

-- xxxxxx xxxxxx xxxxxx 

CREATE OR REPLACE PROCEDURE PROC_1 (

--   <nombre>xxxxxx</nombre>

   VAR_30 TBL_2.COL_1%TYPE DEFAULT NULL,
   VAR_1 NUMBER DEFAULT NULL,
   VAR_45 OUT COL_177.MYCURSOR
)
AS
BEGIN
    OPEN VAR_45 FOR
    SELECT *
    FROM (
        SELECT
            DISTINCT
            COL_3.COL_1,
            COL_3.COL_4,
            COL_5.COL_6,
            COL_5.COL_7,
            COL_8.COL_9,
            COL_8.COL_10
        FROM TBL_1 COL_11
        INNER JOIN TBL_2 COL_3 ON COL_3.COL_1=COL_11.COL_1
        INNER JOIN TBL_3 COL_5 ON COL_5.COL_6=COL_3.COL_6
        LEFT JOIN TBL_6 COL_8 ON COL_5.COL_6=COL_8.COL_6
        WHERE COL_3.COL_1=VAR_30
        AND (COL_8.COL_6 IS NULL OR (COL_8.COL_12=1 AND COL_8.COL_13=COL_11.COL_13))
        UNION ALL
        SELECT VAR_30 COL_1, 0 COL_4, NULL COL_6, NULL COL_7, NULL COL_9, NULL COL_10 FROM DUAL
    ) COL_14
    WHERE ROWNUM=1
    ORDER BY COL_4 DESC;

END;
/
-- xxx xxxxxx xxxxxx xxxxxx

-- xxxxxx xxxxxx xxxxxx 

CREATE OR REPLACE PROCEDURE PROC_27 (
--   <nombre>xxxxxx</nombre>
   VAR_30 IN NUMBER DEFAULT NULL,
   VAR_1 IN NUMBER DEFAULT NULL
)
AS
    VAR_8 TBL_2.COL_6%TYPE := NULL;
BEGIN

    SELECT COL_6 INTO VAR_8 FROM TBL_2 WHERE COL_1=VAR_30;

    IF VAR_8 IS NOT NULL THEN

        DELETE FROM TBL_8 WHERE COL_31 IN (SELECT COL_31 FROM TBL_6 WHERE COL_6 = VAR_8);

        DELETE FROM TBL_6 WHERE COL_6 = VAR_8;

        DELETE FROM TBL_2 WHERE COL_1=VAR_30;

        DELETE FROM TBL_3 WHERE COL_6 = VAR_8;

    END IF;

END;
/
-- xxx xxxxxx xxxxxx xxxxxx

-- xxxxxx xxxxxx xxxxxx 

CREATE OR REPLACE PROCEDURE PROC_2 (
--   <nombre>xxxxxx</nombre>
    VAR_30 IN TBL_2.COL_1%TYPE DEFAULT NULL,
    VAR_46 IN TBL_2.COL_4%TYPE DEFAULT NULL,
    VAR_16 IN TBL_2.COL_15%TYPE DEFAULT NULL,
    VAR_1 IN NUMBER DEFAULT NULL,
    VAR_43 OUT COL_177.MYCURSOR
)
AS
    VAR_6 TBL_2.COL_18%TYPE := FUNC1();
    VAR_8 TBL_2.COL_6%TYPE := NULL;
BEGIN

    IF VAR_30 IS NOT NULL THEN

        UPDATE TBL_2
        SET COL_4 = VAR_46, COL_15 = VAR_16, COL_18 = VAR_6
        WHERE
            COL_1 = VAR_30
            AND COL_4 <> VAR_46;

        SELECT COL_6 INTO VAR_8 FROM TBL_2 WHERE COL_1 = VAR_30;

        IF VAR_8 IS NULL THEN

            VAR_8 := FUNC6();

            INSERT INTO TBL_3 (COL_6, COL_19, COL_20, COL_15, COL_18)
            SELECT VAR_8, VAR_16, VAR_6, VAR_16, VAR_6
            FROM DUAL
            WHERE
                NOT EXISTS (SELECT NULL FROM TBL_2 WHERE COL_1=VAR_30);

            INSERT INTO TBL_2 (COL_1, COL_4, COL_6, COL_19, COL_20, COL_15, COL_18)
            SELECT VAR_30, VAR_46, VAR_8, VAR_16, VAR_6, VAR_16, VAR_6
            FROM DUAL
            WHERE
                NOT EXISTS (SELECT NULL FROM TBL_2 WHERE COL_1=VAR_30);

        END IF;

    END IF;

    OPEN VAR_43 FOR
    SELECT LOWER(VAR_8) AS COL_21 FROM DUAL;

END;
/
-- xxx xxxxxx xxxxxx xxxxxx

-- xxxxxx xxxxxx xxxxx 

CREATE OR REPLACE FUNCTION FUNC2 (
--   <nombre>xxxxx</nombre>
    VAR_7     IN TBL_9.COL_61%TYPE DEFAULT NULL, -- xxxxxx xxx xxxxxx xx tbl_9
    VAR_20     IN DATE DEFAULT NULL,
    VAR_21     IN DATE DEFAULT NULL,
    VAR_10   IN VARCHAR2 DEFAULT NULL,
    VAR_8      IN VARCHAR2 DEFAULT NULL,
    VAR_23      IN TBL_6.COL_72%TYPE DEFAULT NULL,
    VAR_24     IN TBL_6.COL_73%TYPE DEFAULT NULL,
    VAR_12    IN TBL_6.COL_63%TYPE DEFAULT NULL,
    VAR_9 IN TBL_6.COL_42%TYPE DEFAULT NULL
)
RETURN VARCHAR2
AS
    VAR_6           DATE;

    VAR_47        VARCHAR2(4000);
    VAR_48     VARCHAR2(4000);
    VAR_49         TBL_6.COL_72%TYPE;
    VAR_50        TBL_6.COL_73%TYPE;
    VAR_51       TBL_6.COL_63%TYPE;
    VAR_52           VARCHAR2(10);
    VAR_25         VARCHAR2(4000);
    VAR_53       VARCHAR2(1000);
    VAR_54      DATE;

    VAR_55 VARCHAR2(500);   -- col_89
    VAR_56 VARCHAR2(500);   -- col_90
    VAR_27 VARCHAR2(50);    -- xxxxxx
    VAR_57 NUMBER(19);          -- xxxxxx xx
    VAR_58 NUMBER(19);          -- xxx xxxxxx
    VAR_59 NUMBER(19);          -- xxxxxx xxxx
    VAR_60 VARCHAR2(50);    -- col_88
BEGIN

   -- xxxxxx

    VAR_6 := FUNC1();

    SELECT COL_79, COL_89, COL_90, COL_80
      INTO VAR_47, VAR_55, VAR_56, VAR_48
    FROM TBL_9 WHERE COL_61 LIKE VAR_7 AND COL_30=1;

    IF (VAR_47 IS NULL OR VAR_10 IS NULL OR VAR_20 IS NULL OR VAR_21 IS NULL OR VAR_8 IS NULL) THEN
        RETURN 'xxxxxxx-xxxx';
    END IF;

    VAR_27 := 'xxxx.xxxxx';
    VAR_52 := CASE WHEN COALESCE(VAR_9, 0) = 1 THEN 'xxxx' ELSE 'xxxxx' END;
    VAR_60 := REPLACE(COALESCE(VAR_10, ''), '"', '');
    VAR_53 := COALESCE(FUNC3('xxxxxxxxxxx', '/'), '/');
    IF (SUBSTR(VAR_53, LENGTH(VAR_53), 1) <> '/') THEN
        VAR_53 := VAR_53 || '/';
    END IF;
    VAR_48 := REPLACE(VAR_48, '~/', VAR_53);
    VAR_51 := REPLACE(COALESCE(VAR_12, REPLACE(VAR_48, '{x}', VAR_27)), '"', '');
    VAR_49 := REPLACE(COALESCE(VAR_23, VAR_27), '"', '');
    VAR_50 := REPLACE(COALESCE(VAR_24, VAR_27 || '@' || VAR_7), '"', '');
    VAR_54 := TO_DATE('xxxx-xx-xx', 'xxxx-xx-xx');
    VAR_57 := (VAR_6 - VAR_54)  * 60 * 60 * 24;
    VAR_58 := (COALESCE(VAR_20, VAR_6) - VAR_54)  * 60 * 60 * 24;
    VAR_59 := (COALESCE(VAR_21, VAR_6 + 1) - VAR_54)  * 60 * 60 * 24;

    VAR_25:='{
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

    VAR_25 := REPLACE(VAR_25, '$xxxxxx$', VAR_51);
    VAR_25 := REPLACE(VAR_25, '$xxxx$', VAR_49);
    VAR_25 := REPLACE(VAR_25, '$xxxxx$', VAR_50);
    VAR_25 := REPLACE(VAR_25, '$xxx$', TO_CHAR(VAR_57));
    VAR_25 := REPLACE(VAR_25, '$xxx$', TO_CHAR(VAR_58));
    VAR_25 := REPLACE(VAR_25, '$xxx$', TO_CHAR(VAR_59));
    VAR_25 := REPLACE(VAR_25, '$xxx$', VAR_56);
    VAR_25 := REPLACE(VAR_25, '$xxx$', VAR_55);
    VAR_25 := REPLACE(VAR_25, '$xxxxxxxxx$', VAR_60);
    VAR_25 := REPLACE(VAR_25, '$xxx$', VAR_27);
    VAR_25 := REPLACE(VAR_25, '$xxxx$', VAR_8);
    VAR_25 := REPLACE(VAR_25, '$xxxxxxxxx$', VAR_52);

    -- xxxxxx xx xxxxxx xxx xxxx
    VAR_25 := REPLACE(VAR_25, CHR(13), '');
    VAR_25 := REPLACE(VAR_25, CHR(10), '');
    VAR_25 := REPLACE(VAR_25, '    ', ' ');
    VAR_25 := REPLACE(VAR_25, '  ', ' ');
    VAR_25 := REPLACE(VAR_25, '  ', ' ');
    VAR_25 := REPLACE(VAR_25, '{ ', '{');
    VAR_25 := REPLACE(VAR_25, '} ', '}');
    VAR_25 := REPLACE(VAR_25, ': ', ':');
    VAR_25 := REPLACE(VAR_25, ', "', ',"');
    VAR_25 := REPLACE(VAR_25, ' "', '"');
    VAR_25 := REPLACE(VAR_25, '" ', '"');

    RETURN FUNC4(VAR_25, VAR_47);

END;
/
-- xxx xxxxxx xxxxxx xxxxx

-- xxxxxx xxxxxx xxxxxx 

CREATE OR REPLACE PROCEDURE PROC_10 (
--    <nombre>xxxxxx</nombre>

    VAR_61 IN TBL_7.COL_97%TYPE DEFAULT NULL,
    VAR_4 IN TBL_7.COL_31%TYPE DEFAULT NULL,
    VAR_62 IN TBL_7.COL_23%TYPE DEFAULT NULL,
    VAR_16 IN TBL_7.COL_15%TYPE DEFAULT NULL,
    VAR_63 IN TBL_7.COL_18%TYPE DEFAULT NULL,
    VAR_64 IN TBL_7.COL_98%TYPE DEFAULT NULL,
    VAR_65 IN TBL_7.COL_99%TYPE DEFAULT NULL,
    VAR_66 IN TBL_7.COL_97%TYPE DEFAULT NULL,
    VAR_67 IN TBL_7.COL_31%TYPE DEFAULT NULL,
    VAR_68 IN TBL_7.COL_23%TYPE DEFAULT NULL,
    VAR_69 IN TBL_7.COL_15%TYPE DEFAULT NULL,
    VAR_70 IN TBL_7.COL_18%TYPE DEFAULT NULL,
    VAR_71 IN TBL_7.COL_98%TYPE DEFAULT NULL,
    VAR_72 IN TBL_7.COL_99%TYPE DEFAULT NULL
)
AS
BEGIN

    UPDATE TBL_7
    SET COL_15 = VAR_16,
        COL_18 = VAR_63,
        COL_98 = VAR_64,
        COL_99 = VAR_65
    WHERE ( VAR_66 = COL_97 )
     AND ( VAR_67 = COL_31 )
     AND ( VAR_68 = COL_23 )
     AND ( (VAR_69 IS NULL AND COL_15 IS NULL) OR VAR_69 = COL_15 )
     AND ( (VAR_70 IS NULL AND COL_18 IS NULL) OR VAR_70 = COL_18 )
     AND ( (VAR_71 IS NULL AND COL_98 IS NULL) OR VAR_71 = COL_98 );

    -- xx xx xx xxxxxx xx xxxxxx xxxxxx xxxxx
    IF ( COL_180%ROWCOUNT = 0 ) THEN
        RAISE_APPLICATION_ERROR(-20001,'xx xx xx xxxxxxxxxxx xx xxxxxxxxx xxxxxxx xxxx');
    END IF;

    -- xxxxxx xx xxxxxx xxxx xx xxxxx xxxxxx
    IF VAR_61 IS NULL OR VAR_4 IS NULL OR VAR_62 IS NULL THEN
        RAISE_APPLICATION_ERROR(-20001, 'xxxxx xx xxxxxx xxxx xx xxxxx xxxxxxxx');
    END IF;

END;
/
-- xxx xxxxxx xxxxxx xxxxxx

-- xxxxxx xxxxxx xxxxxx 

CREATE OR REPLACE PROCEDURE PROC_11 (
--    <nombre>xxxxxx</nombre>

    VAR_61 IN TBL_7.COL_97%TYPE DEFAULT NULL,
    VAR_4 IN TBL_7.COL_31%TYPE DEFAULT NULL,
    VAR_62 IN TBL_7.COL_23%TYPE DEFAULT NULL,
    VAR_16 IN TBL_7.COL_15%TYPE DEFAULT NULL,
    VAR_63 IN TBL_7.COL_18%TYPE DEFAULT NULL,
    VAR_64 IN TBL_7.COL_98%TYPE DEFAULT NULL,
    VAR_65 IN TBL_7.COL_99%TYPE DEFAULT NULL
)
AS
BEGIN

    INSERT INTO TBL_7 (COL_97, COL_31, COL_23, COL_15, COL_18, COL_98, COL_99)
    VALUES (VAR_61, VAR_4, VAR_62, VAR_16, VAR_63, VAR_64, VAR_65);

END;
/
-- xxx xxxxxx xxxxxx xxxxxx

-- xxxxxx xxxxxx xxxxxx 

CREATE OR REPLACE PROCEDURE PROC_12 (
--    <nombre>xxxxxx</nombre>

    VAR_61 IN TBL_7.COL_97%TYPE DEFAULT NULL,
    VAR_4 IN TBL_7.COL_31%TYPE DEFAULT NULL,
    VAR_62 IN TBL_7.COL_23%TYPE DEFAULT NULL,
    VAR_16 IN TBL_7.COL_15%TYPE DEFAULT NULL,
    VAR_63 IN TBL_7.COL_18%TYPE DEFAULT NULL,
    VAR_64 IN TBL_7.COL_98%TYPE DEFAULT NULL,
    VAR_65 IN TBL_7.COL_99%TYPE DEFAULT NULL,
    VAR_73 IN VARCHAR2 DEFAULT NULL,
    VAR_1 IN NUMBER DEFAULT NULL,
    VAR_2 OUT COL_177.MYCURSOR
)
AS
    COL_109 VARCHAR2(20000);
    COL_110 VARCHAR2(20000) := NULL;
BEGIN

    IF VAR_61 IS NOT NULL AND VAR_4 IS NOT NULL AND VAR_62 IS NOT NULL AND VAR_73 IS NULL THEN

        OPEN VAR_2 FOR
        SELECT COL_97, COL_31, COL_23, COL_15, COL_18, COL_98, COL_99
        FROM TBL_7
        WHERE ( VAR_61 = COL_97 )
            AND ( VAR_4 = COL_31 )
            AND ( VAR_62 = COL_23 )
        AND ( VAR_61 IS NULL OR VAR_61 = COL_97 )
     AND ( VAR_4 IS NULL OR VAR_4 = COL_31 )
     AND ( VAR_62 IS NULL OR VAR_62 = COL_23 )
     AND ( VAR_16 IS NULL OR VAR_16 = COL_15 )
     AND ( VAR_63 IS NULL OR VAR_63 = COL_18 )
     AND ( VAR_64 IS NULL OR VAR_64 = COL_98 );

    ELSE

        COL_109 := 'SELECT COL_97, COL_31, COL_23, COL_15, COL_18, COL_98, COL_99 FROM TBL_7';

        COL_181.FUNC7(col_110, 'xxxxxxxxxxxxxxxx', 'x_xxxxxxxxxxxxxxxx', VAR_61);
        COL_181.FUNC7(col_110, 'xxxxxxxxxxxxx', 'x_xxxxxxxxxxxxx', VAR_4);
        COL_181.FUNC7(col_110, 'xxxxxxxxxxxxxxx', 'x_xxxxxxxxxxxxxxx', VAR_62);
        COL_181.FUNC7(col_110, 'xxxxxxxxxx', 'x_xxxxxxxxxx', VAR_16);
        COL_181.FUNC7(col_110, 'xxxxxxxx', 'x_xxxxxxxx', VAR_63);
        COL_181.FUNC7(col_110, 'xxxxx', 'x_xxxxx', VAR_64);
        COL_181.FUNC7(col_110, 'xxxxxxxxx', 'x_xxxxxxxxx', VAR_65);

        IF COL_110 IS NOT NULL THEN
            COL_109 := COL_109 || ' WHERE ' || COL_110;
        END IF;

        COL_181.FUNC8(COL_109, VAR_73);
        COL_181.FUNC9(COL_109, 'x_xxxxxxxxxxxxxxx', VAR_1);
        COL_181.FUNC10(COL_109);

        OPEN VAR_2
        FOR COL_109
        USING VAR_61, VAR_4, VAR_62, VAR_16, VAR_63, VAR_64, VAR_65, VAR_1;

    END IF;

END;
/
-- xxx xxxxxx xxxxxx xxxxxx

-- xxxxxx xxxxxx xxxxxx 

CREATE OR REPLACE PROCEDURE PROC_15 (
--    <nombre>xxxxxx</nombre>

    VAR_66 IN TBL_7.COL_97%TYPE DEFAULT NULL,
    VAR_67 IN TBL_7.COL_31%TYPE DEFAULT NULL,
    VAR_68 IN TBL_7.COL_23%TYPE DEFAULT NULL,
    VAR_69 IN TBL_7.COL_15%TYPE DEFAULT NULL,
    VAR_70 IN TBL_7.COL_18%TYPE DEFAULT NULL,
    VAR_71 IN TBL_7.COL_98%TYPE DEFAULT NULL,
    VAR_72 IN TBL_7.COL_99%TYPE DEFAULT NULL
)
AS
BEGIN

  DELETE FROM TBL_7
  WHERE ( VAR_66 = COL_97 )
     AND ( VAR_67 = COL_31 )
     AND ( VAR_68 = COL_23 )
     AND ( (VAR_69 IS NULL AND COL_15 IS NULL) OR VAR_69 = COL_15 )
     AND ( (VAR_70 IS NULL AND COL_18 IS NULL) OR VAR_70 = COL_18 )
     AND ( (VAR_71 IS NULL AND COL_98 IS NULL) OR VAR_71 = COL_98 );

    -- xx xx xx xxxxxx xx xxxxxx xxxxxx xxxxx
    IF ( COL_180%ROWCOUNT = 0 ) THEN
        RAISE_APPLICATION_ERROR(-20001,'xx xx xx xxxxxxxxxxx xx xxxxxxxxx xxxxxxx xxxx');
    END IF;
END;
/
-- xxx xxxxxx xxxxxx xxxxxx

-- xxxxxx xxxxxx xxxxxx 

CREATE OR REPLACE PROCEDURE PROC_16 (
--    <nombre>xxxxxx</nombre>

    VAR_74 IN TBL_8.COL_93%TYPE DEFAULT NULL,
    VAR_16 IN TBL_8.COL_15%TYPE DEFAULT NULL,
    VAR_63 IN TBL_8.COL_18%TYPE DEFAULT NULL,
    VAR_4 IN TBL_8.COL_31%TYPE DEFAULT NULL,
    VAR_75 IN TBL_8.COL_39%TYPE DEFAULT NULL,
    VAR_76 IN TBL_8.COL_94%TYPE DEFAULT NULL,
    VAR_77 IN TBL_8.COL_93%TYPE DEFAULT NULL,
    VAR_69 IN TBL_8.COL_15%TYPE DEFAULT NULL,
    VAR_70 IN TBL_8.COL_18%TYPE DEFAULT NULL,
    VAR_67 IN TBL_8.COL_31%TYPE DEFAULT NULL,
    VAR_78 IN TBL_8.COL_39%TYPE DEFAULT NULL,
    VAR_79 IN TBL_8.COL_94%TYPE DEFAULT NULL
)
AS
BEGIN

    UPDATE TBL_8
    SET COL_15 = VAR_16,
        COL_18 = VAR_63,
        COL_31 = VAR_4,
        COL_39 = VAR_75,
        COL_94 = VAR_76
    WHERE ( VAR_77 = COL_93 )
     AND ( (VAR_69 IS NULL AND COL_15 IS NULL) OR VAR_69 = COL_15 )
     AND ( (VAR_70 IS NULL AND COL_18 IS NULL) OR VAR_70 = COL_18 )
     AND ( (VAR_67 IS NULL AND COL_31 IS NULL) OR VAR_67 = COL_31 )
     AND ( (VAR_78 IS NULL AND COL_39 IS NULL) OR VAR_78 = COL_39 )
     AND ( (VAR_79 IS NULL AND COL_94 IS NULL) OR VAR_79 = COL_94 );

    -- xx xx xx xxxxxx xx xxxxxx xxxxxx xxxxx
    IF ( COL_180%ROWCOUNT = 0 ) THEN
        RAISE_APPLICATION_ERROR(-20001,'xx xx xx xxxxxxxxxxx xx xxxxxxxxx xxxxxxx xxxx');
    END IF;

    -- xxxxxx xx xxxxxx xxxx xx xxxxx xxxxxx
    IF VAR_74 IS NULL THEN
        RAISE_APPLICATION_ERROR(-20001, 'xxxxx xx xxxxxx xxxx xx xxxxx xxxxxxxx');
    END IF;

END;
/
-- xxx xxxxxx xxxxxx xxxxxx

-- xxxxxx xxxxxx xxxxxx 

CREATE OR REPLACE PROCEDURE PROC_8 (
--    <nombre>xxxxxx</nombre>

    VAR_74 OUT TBL_8.COL_93%TYPE,
    VAR_16 IN TBL_8.COL_15%TYPE DEFAULT NULL,
    VAR_63 IN TBL_8.COL_18%TYPE DEFAULT NULL,
    VAR_4 IN TBL_8.COL_31%TYPE DEFAULT NULL,
    VAR_75 IN TBL_8.COL_39%TYPE DEFAULT NULL,
    VAR_76 IN TBL_8.COL_94%TYPE DEFAULT NULL
)
AS
BEGIN

    -- xxxxxx x xxxxxx xx xxxxxx xxxxxx
    SELECT COL_182.NEXTVAL
    INTO VAR_74
    FROM DUAL;

    INSERT INTO TBL_8 (COL_93, COL_15, COL_18, COL_31, COL_39, COL_94)
    VALUES (VAR_74, VAR_16, VAR_63, VAR_4, VAR_75, VAR_76);

END;
/
-- xxx xxxxxx xxxxxx xxxxxx

-- xxxxxx xxxxxx xxxxxx 

CREATE OR REPLACE PROCEDURE PROC_17 (
--    <nombre>xxxxxx</nombre>

    VAR_74 IN TBL_8.COL_93%TYPE DEFAULT NULL,
    VAR_16 IN TBL_8.COL_15%TYPE DEFAULT NULL,
    VAR_63 IN TBL_8.COL_18%TYPE DEFAULT NULL,
    VAR_4 IN TBL_8.COL_31%TYPE DEFAULT NULL,
    VAR_75 IN TBL_8.COL_39%TYPE DEFAULT NULL,
    VAR_76 IN TBL_8.COL_94%TYPE DEFAULT NULL,
    VAR_73 IN VARCHAR2 DEFAULT NULL,
    VAR_1 IN NUMBER DEFAULT NULL,
    VAR_80 OUT COL_177.MYCURSOR
)
AS
    COL_109 VARCHAR2(20000);
    COL_110 VARCHAR2(20000) := NULL;
BEGIN

    IF VAR_74 IS NOT NULL AND VAR_73 IS NULL THEN

        OPEN VAR_80 FOR
        SELECT COL_93, COL_15, COL_18, COL_31, COL_39, COL_94
        FROM TBL_8
        WHERE ( VAR_74 = COL_93 )
        AND ( VAR_74 IS NULL OR VAR_74 = COL_93 )
     AND ( VAR_16 IS NULL OR VAR_16 = COL_15 )
     AND ( VAR_63 IS NULL OR VAR_63 = COL_18 )
     AND ( VAR_4 IS NULL OR VAR_4 = COL_31 )
     AND ( VAR_75 IS NULL OR VAR_75 = COL_39 )
     AND ( VAR_76 IS NULL OR VAR_76 = COL_94 );

    ELSE

        COL_109 := 'SELECT COL_93, COL_15, COL_18, COL_31, COL_39, COL_94 FROM TBL_8';

        COL_181.FUNC7(col_110, 'xxxxxxxxxxxxx', 'x_xxxxxxxxxxxxx', VAR_74);
        COL_181.FUNC7(col_110, 'xxxxxxxxxx', 'x_xxxxxxxxxx', VAR_16);
        COL_181.FUNC7(col_110, 'xxxxxxxx', 'x_xxxxxxxx', VAR_63);
        COL_181.FUNC7(col_110, 'xxxxxxxxxxxxx', 'x_xxxxxxxxxxxxx', VAR_4);
        COL_181.FUNC7(col_110, 'xxxxxxxxxxxx', 'x_xxxxxxxxxxxx', VAR_75);
        COL_181.FUNC7(col_110, 'xxxxx', 'x_xxxxx', VAR_76);

        IF COL_110 IS NOT NULL THEN
            COL_109 := COL_109 || ' WHERE ' || COL_110;
        END IF;

        COL_181.FUNC8(COL_109, VAR_73);
        COL_181.FUNC9(COL_109, 'x_xxxxxxxxxxxxxxx', VAR_1);
        COL_181.FUNC10(COL_109);

        OPEN VAR_80
        FOR COL_109
        USING VAR_74, VAR_16, VAR_63, VAR_4, VAR_75, VAR_76, VAR_1;

    END IF;

END;
/
-- xxx xxxxxx xxxxxx xxxxxx

-- xxxxxx xxxxxx xxxxxx 

CREATE OR REPLACE PROCEDURE PROC_18 (
--    <nombre>xxxxxx</nombre>

    VAR_77 IN TBL_8.COL_93%TYPE DEFAULT NULL,
    VAR_69 IN TBL_8.COL_15%TYPE DEFAULT NULL,
    VAR_70 IN TBL_8.COL_18%TYPE DEFAULT NULL,
    VAR_67 IN TBL_8.COL_31%TYPE DEFAULT NULL,
    VAR_78 IN TBL_8.COL_39%TYPE DEFAULT NULL,
    VAR_79 IN TBL_8.COL_94%TYPE DEFAULT NULL
)
AS
BEGIN

  DELETE FROM TBL_8
  WHERE ( VAR_77 = COL_93 )
     AND ( (VAR_69 IS NULL AND COL_15 IS NULL) OR VAR_69 = COL_15 )
     AND ( (VAR_70 IS NULL AND COL_18 IS NULL) OR VAR_70 = COL_18 )
     AND ( (VAR_67 IS NULL AND COL_31 IS NULL) OR VAR_67 = COL_31 )
     AND ( (VAR_78 IS NULL AND COL_39 IS NULL) OR VAR_78 = COL_39 )
     AND ( (VAR_79 IS NULL AND COL_94 IS NULL) OR VAR_79 = COL_94 );

    -- xx xx xx xxxxxx xx xxxxxx xxxxxx xxxxx
    IF ( COL_180%ROWCOUNT = 0 ) THEN
        RAISE_APPLICATION_ERROR(-20001,'xx xx xx xxxxxxxxxxx xx xxxxxxxxx xxxxxxx xxxx');
    END IF;
END;
/
-- xxx xxxxxx xxxxxx xxxxxx

-- xxxxxx xxxxxx xxxxxx 

CREATE OR REPLACE PROCEDURE PROC_19 (
--    <nombre>xxxxxx</nombre>

    VAR_4 IN TBL_6.COL_31%TYPE DEFAULT NULL,
    VAR_8 IN TBL_6.COL_6%TYPE DEFAULT NULL,
    VAR_26 IN TBL_6.COL_32%TYPE DEFAULT NULL,
    VAR_81 IN TBL_6.COL_33%TYPE DEFAULT NULL,
    VAR_29 IN TBL_6.COL_12%TYPE DEFAULT NULL,
    VAR_9 IN TBL_6.COL_42%TYPE DEFAULT NULL,
    VAR_10 IN TBL_6.COL_62%TYPE DEFAULT NULL,
    VAR_11 IN TBL_6.COL_13%TYPE DEFAULT NULL,
    VAR_13 IN TBL_6.COL_9%TYPE DEFAULT NULL,
    VAR_14 IN TBL_6.COL_10%TYPE DEFAULT NULL,
    VAR_25 IN TBL_6.COL_74%TYPE DEFAULT NULL,
    VAR_82 IN TBL_6.COL_38%TYPE DEFAULT NULL,
    VAR_83 IN TBL_6.COL_95%TYPE DEFAULT NULL,
    VAR_84 IN TBL_6.COL_96%TYPE DEFAULT NULL,
    VAR_23 IN TBL_6.COL_72%TYPE DEFAULT NULL,
    VAR_24 IN TBL_6.COL_73%TYPE DEFAULT NULL,
    VAR_12 IN TBL_6.COL_63%TYPE DEFAULT NULL,
    VAR_85 IN TBL_6.COL_19%TYPE DEFAULT NULL,
    VAR_86 IN TBL_6.COL_20%TYPE DEFAULT NULL,
    VAR_16 IN TBL_6.COL_15%TYPE DEFAULT NULL,
    VAR_63 IN TBL_6.COL_18%TYPE DEFAULT NULL,
    VAR_67 IN TBL_6.COL_31%TYPE DEFAULT NULL,
    VAR_87 IN TBL_6.COL_6%TYPE DEFAULT NULL,
    VAR_88 IN TBL_6.COL_32%TYPE DEFAULT NULL,
    VAR_89 IN TBL_6.COL_33%TYPE DEFAULT NULL,
    VAR_90 IN TBL_6.COL_12%TYPE DEFAULT NULL,
    VAR_91 IN TBL_6.COL_42%TYPE DEFAULT NULL,
    VAR_92 IN TBL_6.COL_62%TYPE DEFAULT NULL,
    VAR_93 IN TBL_6.COL_13%TYPE DEFAULT NULL,
    VAR_94 IN TBL_6.COL_9%TYPE DEFAULT NULL,
    VAR_95 IN TBL_6.COL_10%TYPE DEFAULT NULL,
    VAR_96 IN TBL_6.COL_74%TYPE DEFAULT NULL,
    VAR_97 IN TBL_6.COL_38%TYPE DEFAULT NULL,
    VAR_98 IN TBL_6.COL_95%TYPE DEFAULT NULL,
    VAR_99 IN TBL_6.COL_96%TYPE DEFAULT NULL,
    VAR_100 IN TBL_6.COL_72%TYPE DEFAULT NULL,
    VAR_101 IN TBL_6.COL_73%TYPE DEFAULT NULL,
    VAR_102 IN TBL_6.COL_63%TYPE DEFAULT NULL,
    VAR_103 IN TBL_6.COL_19%TYPE DEFAULT NULL,
    VAR_104 IN TBL_6.COL_20%TYPE DEFAULT NULL,
    VAR_69 IN TBL_6.COL_15%TYPE DEFAULT NULL,
    VAR_70 IN TBL_6.COL_18%TYPE DEFAULT NULL
)
AS
BEGIN

    UPDATE TBL_6
    SET COL_6 = VAR_8,
        COL_32 = VAR_26,
        COL_33 = VAR_81,
        COL_12 = VAR_29,
        COL_42 = VAR_9,
        COL_62 = VAR_10,
        COL_13 = VAR_11,
        COL_9 = VAR_13,
        COL_10 = VAR_14,
        COL_74 = VAR_25,
        COL_38 = VAR_82,
        COL_95 = VAR_83,
        COL_96 = VAR_84,
        COL_72 = VAR_23,
        COL_73 = VAR_24,
        COL_63 = VAR_12,
        COL_19 = VAR_85,
        COL_20 = VAR_86,
        COL_15 = VAR_16,
        COL_18 = VAR_63
    WHERE ( VAR_67 = COL_31 )
     AND ( (VAR_87 IS NULL AND COL_6 IS NULL) OR VAR_87 = COL_6 )
     AND ( (VAR_88 IS NULL AND COL_32 IS NULL) OR VAR_88 = COL_32 )
     AND ( (VAR_89 IS NULL AND COL_33 IS NULL) OR VAR_89 = COL_33 )
     AND ( (VAR_90 IS NULL AND COL_12 IS NULL) OR VAR_90 = COL_12 )
     AND ( (VAR_91 IS NULL AND COL_42 IS NULL) OR VAR_91 = COL_42 )
     AND ( (VAR_92 IS NULL AND COL_62 IS NULL) OR VAR_92 = COL_62 )
     AND ( (VAR_93 IS NULL AND COL_13 IS NULL) OR VAR_93 = COL_13 )
     AND ( (VAR_94 IS NULL AND COL_9 IS NULL) OR VAR_94 = COL_9 )
     AND ( (VAR_95 IS NULL AND COL_10 IS NULL) OR VAR_95 = COL_10 )
     AND ( (VAR_100 IS NULL AND COL_72 IS NULL) OR VAR_100 = COL_72 )
     AND ( (VAR_101 IS NULL AND COL_73 IS NULL) OR VAR_101 = COL_73 )
     AND ( (VAR_102 IS NULL AND COL_63 IS NULL) OR VAR_102 = COL_63 )
     AND ( (VAR_103 IS NULL AND COL_19 IS NULL) OR VAR_103 = COL_19 )
     AND ( (VAR_104 IS NULL AND COL_20 IS NULL) OR VAR_104 = COL_20 )
     AND ( (VAR_69 IS NULL AND COL_15 IS NULL) OR VAR_69 = COL_15 )
     AND ( (VAR_70 IS NULL AND COL_18 IS NULL) OR VAR_70 = COL_18 );

    -- xx xx xx xxxxxx xx xxxxxx xxxxxx xxxxx
    IF ( COL_180%ROWCOUNT = 0 ) THEN
        RAISE_APPLICATION_ERROR(-20001,'xx xx xx xxxxxxxxxxx xx xxxxxxxxx xxxxxxx xxxx');
    END IF;

    -- xxxxxx xx xxxxxx xxxx xx xxxxx xxxxxx
    IF VAR_4 IS NULL THEN
        RAISE_APPLICATION_ERROR(-20001, 'xxxxx xx xxxxxx xxxx xx xxxxx xxxxxxxx');
    END IF;

END;
/
-- xxx xxxxxx xxxxxx xxxxxx

-- xxxxxx xxxxxx xxxxxx 

CREATE OR REPLACE PROCEDURE PROC_9 (
--    <nombre>xxxxxx</nombre>

    VAR_4 OUT TBL_6.COL_31%TYPE,
    VAR_8 IN TBL_6.COL_6%TYPE DEFAULT NULL,
    VAR_26 IN TBL_6.COL_32%TYPE DEFAULT NULL,
    VAR_81 IN TBL_6.COL_33%TYPE DEFAULT NULL,
    VAR_29 IN TBL_6.COL_12%TYPE DEFAULT NULL,
    VAR_9 IN TBL_6.COL_42%TYPE DEFAULT NULL,
    VAR_10 IN TBL_6.COL_62%TYPE DEFAULT NULL,
    VAR_11 IN TBL_6.COL_13%TYPE DEFAULT NULL,
    VAR_13 IN TBL_6.COL_9%TYPE DEFAULT NULL,
    VAR_14 IN TBL_6.COL_10%TYPE DEFAULT NULL,
    VAR_25 IN TBL_6.COL_74%TYPE DEFAULT NULL,
    VAR_82 IN TBL_6.COL_38%TYPE DEFAULT NULL,
    VAR_83 IN TBL_6.COL_95%TYPE DEFAULT NULL,
    VAR_84 IN TBL_6.COL_96%TYPE DEFAULT NULL,
    VAR_23 IN TBL_6.COL_72%TYPE DEFAULT NULL,
    VAR_24 IN TBL_6.COL_73%TYPE DEFAULT NULL,
    VAR_12 IN TBL_6.COL_63%TYPE DEFAULT NULL,
    VAR_85 IN TBL_6.COL_19%TYPE DEFAULT NULL,
    VAR_86 IN TBL_6.COL_20%TYPE DEFAULT NULL,
    VAR_16 IN TBL_6.COL_15%TYPE DEFAULT NULL,
    VAR_63 IN TBL_6.COL_18%TYPE DEFAULT NULL
)
AS
BEGIN

    -- xxxxxx x xxxxxx xx xxxxxx xxxxxx
    SELECT COL_183.NEXTVAL
    INTO VAR_4
    FROM DUAL;

    INSERT INTO TBL_6 (COL_31, COL_6, COL_32, COL_33, COL_12, COL_42, COL_62, COL_13, COL_9, COL_10, COL_74, COL_38, COL_95, COL_96, COL_72, COL_73, COL_63, COL_19, COL_20, COL_15, COL_18)
    VALUES (VAR_4, VAR_8, VAR_26, VAR_81, VAR_29, VAR_9, VAR_10, VAR_11, VAR_13, VAR_14, VAR_25, VAR_82, VAR_83, VAR_84, VAR_23, VAR_24, VAR_12, VAR_85, VAR_86, VAR_16, VAR_63);

END;
/
-- xxx xxxxxx xxxxxx xxxxxx

-- xxxxxx xxxxxx xxxxxx 

CREATE OR REPLACE PROCEDURE PROC_20 (
--    <nombre>xxxxxx</nombre>

    VAR_4 IN TBL_6.COL_31%TYPE DEFAULT NULL,
    VAR_8 IN TBL_6.COL_6%TYPE DEFAULT NULL,
    VAR_26 IN TBL_6.COL_32%TYPE DEFAULT NULL,
    VAR_81 IN TBL_6.COL_33%TYPE DEFAULT NULL,
    VAR_29 IN TBL_6.COL_12%TYPE DEFAULT NULL,
    VAR_9 IN TBL_6.COL_42%TYPE DEFAULT NULL,
    VAR_10 IN TBL_6.COL_62%TYPE DEFAULT NULL,
    VAR_11 IN TBL_6.COL_13%TYPE DEFAULT NULL,
    VAR_13 IN TBL_6.COL_9%TYPE DEFAULT NULL,
    VAR_14 IN TBL_6.COL_10%TYPE DEFAULT NULL,
    VAR_25 IN TBL_6.COL_74%TYPE DEFAULT NULL,
    VAR_82 IN TBL_6.COL_38%TYPE DEFAULT NULL,
    VAR_83 IN TBL_6.COL_95%TYPE DEFAULT NULL,
    VAR_84 IN TBL_6.COL_96%TYPE DEFAULT NULL,
    VAR_23 IN TBL_6.COL_72%TYPE DEFAULT NULL,
    VAR_24 IN TBL_6.COL_73%TYPE DEFAULT NULL,
    VAR_12 IN TBL_6.COL_63%TYPE DEFAULT NULL,
    VAR_85 IN TBL_6.COL_19%TYPE DEFAULT NULL,
    VAR_86 IN TBL_6.COL_20%TYPE DEFAULT NULL,
    VAR_16 IN TBL_6.COL_15%TYPE DEFAULT NULL,
    VAR_63 IN TBL_6.COL_18%TYPE DEFAULT NULL,
    VAR_73 IN VARCHAR2 DEFAULT NULL,
    VAR_1 IN NUMBER DEFAULT NULL,
    VAR_5 OUT COL_177.MYCURSOR
)
AS
    COL_109 VARCHAR2(20000);
    COL_110 VARCHAR2(20000) := NULL;
BEGIN

    IF VAR_4 IS NOT NULL AND VAR_73 IS NULL THEN

        OPEN VAR_5 FOR
        SELECT COL_31, COL_6, COL_32, COL_33, COL_12, COL_42, COL_62, COL_13, COL_9, COL_10, COL_74, COL_38, COL_95, COL_96, COL_72, COL_73, COL_63, COL_19, COL_20, COL_15, COL_18
        FROM TBL_6
        WHERE ( VAR_4 = COL_31 )
        AND ( VAR_4 IS NULL OR VAR_4 = COL_31 )
     AND ( VAR_8 IS NULL OR VAR_8 = COL_6 )
     AND ( VAR_26 IS NULL OR VAR_26 = COL_32 )
     AND ( VAR_81 IS NULL OR VAR_81 = COL_33 )
     AND ( VAR_29 IS NULL OR VAR_29 = COL_12 )
     AND ( VAR_9 IS NULL OR VAR_9 = COL_42 )
     AND ( VAR_10 IS NULL OR VAR_10 = COL_62 )
     AND ( VAR_11 IS NULL OR VAR_11 = COL_13 )
     AND ( VAR_13 IS NULL OR VAR_13 = COL_9 )
     AND ( VAR_14 IS NULL OR VAR_14 = COL_10 )
     AND ( VAR_23 IS NULL OR VAR_23 = COL_72 )
     AND ( VAR_24 IS NULL OR VAR_24 = COL_73 )
     AND ( VAR_12 IS NULL OR VAR_12 = COL_63 )
     AND ( VAR_85 IS NULL OR VAR_85 = COL_19 )
     AND ( VAR_86 IS NULL OR VAR_86 = COL_20 )
     AND ( VAR_16 IS NULL OR VAR_16 = COL_15 )
     AND ( VAR_63 IS NULL OR VAR_63 = COL_18 );

    ELSE

        COL_109 := 'SELECT COL_31, COL_6, COL_32, COL_33, COL_12, COL_42, COL_62, COL_13, COL_9, COL_10, COL_74, COL_38, COL_95, COL_96, COL_72, COL_73, COL_63, COL_19, COL_20, COL_15, COL_18 FROM TBL_6';

        COL_181.FUNC7(col_110, 'xxxxxxxxxxxxx', 'x_xxxxxxxxxxxxx', VAR_4);
        COL_181.FUNC7(col_110, 'xxxx', 'x_xxxx', VAR_8);
        COL_181.FUNC7(col_110, 'xxxxxxxx', 'x_xxxxxxxx', VAR_26);
        COL_181.FUNC7(col_110, 'xxxxxxxx', 'x_xxxxxxxx', VAR_81);
        COL_181.FUNC7(col_110, 'xxxxxxxxxxx', 'x_xxxxxxxxxxx', VAR_29);
        COL_181.FUNC7(col_110, 'xxxxxxxxx', 'x_xxxxxxxxx', VAR_9);
        COL_181.FUNC7(col_110, 'xxxxxxx', 'x_xxxxxxx', VAR_10);
        COL_181.FUNC7(col_110, 'xxxxxxxx', 'x_xxxxxxxx', VAR_11);
        COL_181.FUNC7(col_110, 'xxxxxxxxxxxxx', 'x_xxxxxxxxxxxxx', VAR_13);
        COL_181.FUNC7(col_110, 'xxxxxxxxxxxxx', 'x_xxxxxxxxxxxxx', VAR_14);
        COL_181.FUNC7(col_110, 'xxxxx', 'x_xxxxx', VAR_25);
        COL_181.FUNC7(col_110, 'xxxxxxxxxx', 'x_xxxxxxxxxx', VAR_82);
        COL_181.FUNC7(col_110, 'xxxxxxxxxxxxxxxx', 'x_xxxxxxxxxxxxxxxx', VAR_83);
        COL_181.FUNC7(col_110, 'xxxxxxxxxxxxxx', 'x_xxxxxxxxxxxxxx', VAR_84);
        COL_181.FUNC7(col_110, 'xxxx', 'x_xxxx', VAR_23);
        COL_181.FUNC7(col_110, 'xxxxx', 'x_xxxxx', VAR_24);
        COL_181.FUNC7(col_110, 'xxxxxx', 'x_xxxxxx', VAR_12);
        COL_181.FUNC7(col_110, 'xxxxxxxxxxx', 'x_xxxxxxxxxxx', VAR_85);
        COL_181.FUNC7(col_110, 'xxxxxxxxx', 'x_xxxxxxxxx', VAR_86);
        COL_181.FUNC7(col_110, 'xxxxxxxxxx', 'x_xxxxxxxxxx', VAR_16);
        COL_181.FUNC7(col_110, 'xxxxxxxx', 'x_xxxxxxxx', VAR_63);

        IF COL_110 IS NOT NULL THEN
            COL_109 := COL_109 || ' WHERE ' || COL_110;
        END IF;

        COL_181.FUNC8(COL_109, VAR_73);
        COL_181.FUNC9(COL_109, 'x_xxxxxxxxxxxxxxx', VAR_1);
        COL_181.FUNC10(COL_109);

        OPEN VAR_5
        FOR COL_109
        USING VAR_4, VAR_8, VAR_26, VAR_81, VAR_29, VAR_9, VAR_10, VAR_11, VAR_13, VAR_14, VAR_25, VAR_82, VAR_83, VAR_84, VAR_23, VAR_24, VAR_12, VAR_85, VAR_86, VAR_16, VAR_63, VAR_1;

    END IF;

END;
/
-- xxx xxxxxx xxxxxx xxxxxx

-- xxxxxx xxxxxx xxxxxx 

CREATE OR REPLACE PROCEDURE PROC_21 (
--    <nombre>xxxxxx</nombre>

    VAR_67 IN TBL_6.COL_31%TYPE DEFAULT NULL,
    VAR_87 IN TBL_6.COL_6%TYPE DEFAULT NULL,
    VAR_88 IN TBL_6.COL_32%TYPE DEFAULT NULL,
    VAR_89 IN TBL_6.COL_33%TYPE DEFAULT NULL,
    VAR_90 IN TBL_6.COL_12%TYPE DEFAULT NULL,
    VAR_91 IN TBL_6.COL_42%TYPE DEFAULT NULL,
    VAR_92 IN TBL_6.COL_62%TYPE DEFAULT NULL,
    VAR_93 IN TBL_6.COL_13%TYPE DEFAULT NULL,
    VAR_94 IN TBL_6.COL_9%TYPE DEFAULT NULL,
    VAR_95 IN TBL_6.COL_10%TYPE DEFAULT NULL,
    VAR_96 IN TBL_6.COL_74%TYPE DEFAULT NULL,
    VAR_97 IN TBL_6.COL_38%TYPE DEFAULT NULL,
    VAR_98 IN TBL_6.COL_95%TYPE DEFAULT NULL,
    VAR_99 IN TBL_6.COL_96%TYPE DEFAULT NULL,
    VAR_100 IN TBL_6.COL_72%TYPE DEFAULT NULL,
    VAR_101 IN TBL_6.COL_73%TYPE DEFAULT NULL,
    VAR_102 IN TBL_6.COL_63%TYPE DEFAULT NULL,
    VAR_103 IN TBL_6.COL_19%TYPE DEFAULT NULL,
    VAR_104 IN TBL_6.COL_20%TYPE DEFAULT NULL,
    VAR_69 IN TBL_6.COL_15%TYPE DEFAULT NULL,
    VAR_70 IN TBL_6.COL_18%TYPE DEFAULT NULL
)
AS
BEGIN

  DELETE FROM TBL_6
  WHERE ( VAR_67 = COL_31 )
     AND ( (VAR_87 IS NULL AND COL_6 IS NULL) OR VAR_87 = COL_6 )
     AND ( (VAR_88 IS NULL AND COL_32 IS NULL) OR VAR_88 = COL_32 )
     AND ( (VAR_89 IS NULL AND COL_33 IS NULL) OR VAR_89 = COL_33 )
     AND ( (VAR_90 IS NULL AND COL_12 IS NULL) OR VAR_90 = COL_12 )
     AND ( (VAR_91 IS NULL AND COL_42 IS NULL) OR VAR_91 = COL_42 )
     AND ( (VAR_92 IS NULL AND COL_62 IS NULL) OR VAR_92 = COL_62 )
     AND ( (VAR_93 IS NULL AND COL_13 IS NULL) OR VAR_93 = COL_13 )
     AND ( (VAR_94 IS NULL AND COL_9 IS NULL) OR VAR_94 = COL_9 )
     AND ( (VAR_95 IS NULL AND COL_10 IS NULL) OR VAR_95 = COL_10 )
     AND ( (VAR_100 IS NULL AND COL_72 IS NULL) OR VAR_100 = COL_72 )
     AND ( (VAR_101 IS NULL AND COL_73 IS NULL) OR VAR_101 = COL_73 )
     AND ( (VAR_102 IS NULL AND COL_63 IS NULL) OR VAR_102 = COL_63 )
     AND ( (VAR_103 IS NULL AND COL_19 IS NULL) OR VAR_103 = COL_19 )
     AND ( (VAR_104 IS NULL AND COL_20 IS NULL) OR VAR_104 = COL_20 )
     AND ( (VAR_69 IS NULL AND COL_15 IS NULL) OR VAR_69 = COL_15 )
     AND ( (VAR_70 IS NULL AND COL_18 IS NULL) OR VAR_70 = COL_18 );

    -- xx xx xx xxxxxx xx xxxxxx xxxxxx xxxxx
    IF ( COL_180%ROWCOUNT = 0 ) THEN
        RAISE_APPLICATION_ERROR(-20001,'xx xx xx xxxxxxxxxxx xx xxxxxxxxx xxxxxxx xxxx');
    END IF;
END;
/
-- xxx xxxxxx xxxxxx xxxxxx

-- xxxxxx xxxxxx xxxxxx 

CREATE OR REPLACE PROCEDURE PROC_22 (
--    <nombre>xxxxxx</nombre>

    VAR_8 IN TBL_3.COL_6%TYPE DEFAULT NULL,
    VAR_105 IN TBL_3.COL_7%TYPE DEFAULT NULL,
    VAR_106 IN TBL_3.COL_91%TYPE DEFAULT NULL,
    VAR_85 IN TBL_3.COL_19%TYPE DEFAULT NULL,
    VAR_86 IN TBL_3.COL_20%TYPE DEFAULT NULL,
    VAR_16 IN TBL_3.COL_15%TYPE DEFAULT NULL,
    VAR_63 IN TBL_3.COL_18%TYPE DEFAULT NULL,
    VAR_87 IN TBL_3.COL_6%TYPE DEFAULT NULL,
    VAR_107 IN TBL_3.COL_7%TYPE DEFAULT NULL,
    VAR_108 IN TBL_3.COL_91%TYPE DEFAULT NULL,
    VAR_103 IN TBL_3.COL_19%TYPE DEFAULT NULL,
    VAR_104 IN TBL_3.COL_20%TYPE DEFAULT NULL,
    VAR_69 IN TBL_3.COL_15%TYPE DEFAULT NULL,
    VAR_70 IN TBL_3.COL_18%TYPE DEFAULT NULL
)
AS
BEGIN

    UPDATE TBL_3
    SET COL_7 = VAR_105,
        COL_91 = VAR_106,
        COL_19 = VAR_85,
        COL_20 = VAR_86,
        COL_15 = VAR_16,
        COL_18 = VAR_63
    WHERE ( VAR_87 = COL_6 )
     AND ( (VAR_107 IS NULL AND COL_7 IS NULL) OR VAR_107 = COL_7 )
     AND ( (VAR_108 IS NULL AND COL_91 IS NULL) OR VAR_108 = COL_91 )
     AND ( (VAR_103 IS NULL AND COL_19 IS NULL) OR VAR_103 = COL_19 )
     AND ( (VAR_104 IS NULL AND COL_20 IS NULL) OR VAR_104 = COL_20 )
     AND ( (VAR_69 IS NULL AND COL_15 IS NULL) OR VAR_69 = COL_15 )
     AND ( (VAR_70 IS NULL AND COL_18 IS NULL) OR VAR_70 = COL_18 );

    -- xx xx xx xxxxxx xx xxxxxx xxxxxx xxxxx
    IF ( COL_180%ROWCOUNT = 0 ) THEN
        RAISE_APPLICATION_ERROR(-20001,'xx xx xx xxxxxxxxxxx xx xxxxxxxxx xxxxxxx xxxx');
    END IF;

    -- xxxxxx xx xxxxxx xxxx xx xxxxx xxxxxx
    IF VAR_8 IS NULL THEN
        RAISE_APPLICATION_ERROR(-20001, 'xxxxx xx xxxxxx xxxx xx xxxxx xxxxxxxx');
    END IF;

END;
/
-- xxx xxxxxx xxxxxx xxxxxx

-- xxxxxx xxxxxx xxxxxx 

CREATE OR REPLACE PROCEDURE PROC_7 (
--    <nombre>xxxxxx</nombre>

    VAR_8 OUT TBL_3.COL_6%TYPE,
    VAR_105 IN TBL_3.COL_7%TYPE DEFAULT NULL,
    VAR_106 IN TBL_3.COL_91%TYPE DEFAULT NULL,
    VAR_85 IN TBL_3.COL_19%TYPE DEFAULT NULL,
    VAR_86 IN TBL_3.COL_20%TYPE DEFAULT NULL,
    VAR_16 IN TBL_3.COL_15%TYPE DEFAULT NULL,
    VAR_63 IN TBL_3.COL_18%TYPE DEFAULT NULL
)
AS
BEGIN

    -- xxxxxx x xxxxxx xx xxxxxx xxxxxx
    SELECT FUNC6()
    INTO VAR_8
    FROM DUAL;

    INSERT INTO TBL_3 (COL_6, COL_7, COL_91, COL_19, COL_20, COL_15, COL_18)
    VALUES (VAR_8, VAR_105, VAR_106, VAR_85, VAR_86, VAR_16, VAR_63);

END;
/
-- xxx xxxxxx xxxxxx xxxxxx

-- xxxxxx xxxxxx xxxxxx 

CREATE OR REPLACE PROCEDURE PROC_23 (
--    <nombre>xxxxxx</nombre>

    VAR_8 IN TBL_3.COL_6%TYPE DEFAULT NULL,
    VAR_105 IN TBL_3.COL_7%TYPE DEFAULT NULL,
    VAR_106 IN TBL_3.COL_91%TYPE DEFAULT NULL,
    VAR_85 IN TBL_3.COL_19%TYPE DEFAULT NULL,
    VAR_86 IN TBL_3.COL_20%TYPE DEFAULT NULL,
    VAR_16 IN TBL_3.COL_15%TYPE DEFAULT NULL,
    VAR_63 IN TBL_3.COL_18%TYPE DEFAULT NULL,
    VAR_73 IN VARCHAR2 DEFAULT NULL,
    VAR_1 IN NUMBER DEFAULT NULL,
    VAR_109 OUT COL_177.MYCURSOR
)
AS
    COL_109 VARCHAR2(20000);
    COL_110 VARCHAR2(20000) := NULL;
BEGIN

    IF VAR_8 IS NOT NULL AND VAR_73 IS NULL THEN

        OPEN VAR_109 FOR
        SELECT COL_6, COL_7, COL_91, COL_19, COL_20, COL_15, COL_18
        FROM TBL_3
        WHERE ( VAR_8 = COL_6 )
        AND ( VAR_8 IS NULL OR VAR_8 = COL_6 )
     AND ( VAR_105 IS NULL OR VAR_105 = COL_7 )
     AND ( VAR_106 IS NULL OR VAR_106 = COL_91 )
     AND ( VAR_85 IS NULL OR VAR_85 = COL_19 )
     AND ( VAR_86 IS NULL OR VAR_86 = COL_20 )
     AND ( VAR_16 IS NULL OR VAR_16 = COL_15 )
     AND ( VAR_63 IS NULL OR VAR_63 = COL_18 );

    ELSE

        COL_109 := 'SELECT COL_6, COL_7, COL_91, COL_19, COL_20, COL_15, COL_18 FROM TBL_3';

        COL_181.FUNC7(col_110, 'xxxx', 'x_xxxx', VAR_8);
        COL_181.FUNC7(col_110, 'xxxxxxx', 'x_xxxxxxx', VAR_105);
        COL_181.FUNC7(col_110, 'xxxxxxxxxx', 'x_xxxxxxxxxx', VAR_106);
        COL_181.FUNC7(col_110, 'xxxxxxxxxxx', 'x_xxxxxxxxxxx', VAR_85);
        COL_181.FUNC7(col_110, 'xxxxxxxxx', 'x_xxxxxxxxx', VAR_86);
        COL_181.FUNC7(col_110, 'xxxxxxxxxx', 'x_xxxxxxxxxx', VAR_16);
        COL_181.FUNC7(col_110, 'xxxxxxxx', 'x_xxxxxxxx', VAR_63);

        IF COL_110 IS NOT NULL THEN
            COL_109 := COL_109 || ' WHERE ' || COL_110;
        END IF;

        COL_181.FUNC8(COL_109, VAR_73);
        COL_181.FUNC9(COL_109, 'x_xxxxxxxxxxxxxxx', VAR_1);
        COL_181.FUNC10(COL_109);

        OPEN VAR_109
        FOR COL_109
        USING VAR_8, VAR_105, VAR_106, VAR_85, VAR_86, VAR_16, VAR_63, VAR_1;

    END IF;

END;
/
-- xxx xxxxxx xxxxxx xxxxxx

-- xxxxxx xxxxxx xxxxxx 

CREATE OR REPLACE PROCEDURE PROC_24 (
--    <nombre>xxxxxx</nombre>

    VAR_87 IN TBL_3.COL_6%TYPE DEFAULT NULL,
    VAR_107 IN TBL_3.COL_7%TYPE DEFAULT NULL,
    VAR_108 IN TBL_3.COL_91%TYPE DEFAULT NULL,
    VAR_103 IN TBL_3.COL_19%TYPE DEFAULT NULL,
    VAR_104 IN TBL_3.COL_20%TYPE DEFAULT NULL,
    VAR_69 IN TBL_3.COL_15%TYPE DEFAULT NULL,
    VAR_70 IN TBL_3.COL_18%TYPE DEFAULT NULL
)
AS
BEGIN

  DELETE FROM TBL_3
  WHERE ( VAR_87 = COL_6 )
     AND ( (VAR_107 IS NULL AND COL_7 IS NULL) OR VAR_107 = COL_7 )
     AND ( (VAR_108 IS NULL AND COL_91 IS NULL) OR VAR_108 = COL_91 )
     AND ( (VAR_103 IS NULL AND COL_19 IS NULL) OR VAR_103 = COL_19 )
     AND ( (VAR_104 IS NULL AND COL_20 IS NULL) OR VAR_104 = COL_20 )
     AND ( (VAR_69 IS NULL AND COL_15 IS NULL) OR VAR_69 = COL_15 )
     AND ( (VAR_70 IS NULL AND COL_18 IS NULL) OR VAR_70 = COL_18 );

    -- xx xx xx xxxxxx xx xxxxxx xxxxxx xxxxx
    IF ( COL_180%ROWCOUNT = 0 ) THEN
        RAISE_APPLICATION_ERROR(-20001,'xx xx xx xxxxxxxxxxx xx xxxxxxxxx xxxxxxx xxxx');
    END IF;
END;
/
-- xxx xxxxxx xxxxxx xxxxxx

-- xxxxxx xxxxxx xxxxxx 

CREATE OR REPLACE TRIGGER COL_173
--    <nombre>xxxxxx</nombre>
   COL_184 UPDATE OF COL_32 ON TBL_6
   FOR COL_185 COL_186 WHEN (COL_187.COL_32 <> COL_188.COL_32)
DECLARE
    VAR_6 TBL_6.COL_18%TYPE := FUNC1();
    VAR_110 NUMBER(9);
BEGIN

     SELECT COL_98 INTO VAR_110
     FROM(
        SELECT 1 AS COL_98 FROM TBL_9 WHERE COL_96 IS NOT NULL AND COL_30=1
        UNION ALL
        SELECT 0 AS COL_98 FROM DUAL
     ) COL_189
     WHERE ROWNUM = 1;

     /* xxxxxx xxxx xxxxxx */
     INSERT INTO TBL_8
     (
        COL_15,
        COL_18,
        COL_31,
        COL_39,
        COL_94
     )
     SELECT
        :COL_188.COL_15,
        :COL_188.COL_18,
        :COL_188.COL_31,
        (4 - ((2 * VAR_110 * (1 - :COL_188.COL_42)) + :COL_188.COL_32)) AS COL_39,
        VAR_6 AS COL_94
     FROM DUAL;

END;
/
-- xxx xxxxxx xxxxxx xxxxxx


