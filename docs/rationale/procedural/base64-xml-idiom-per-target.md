[← Procedural: cursors, dynamic SQL, system procedures, session directives](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=procedural type="Base64 decode idiom" direction="tsql → oracle/postgresql/mysql" kind=article order=43 -->

# T-SQL's `CAST(N'' AS XML).value('xs:base64Binary(...)', ...)` base64-decode idiom → each target's native call

**Problem.** T-SQL has no direct `BASE64_DECODE` function; the idiomatic
way to decode a base64 string into binary is to route it through the XML
type system — `CAST(N'' AS XML).value('xs:base64Binary(sql:variable("@x"))',
'VARBINARY(MAX)')`. Every other engine has a plain function for the same
operation, so carrying the XML-value idiom across verbatim would be both
unreadable and untranslatable (none of the other three engines have an
`xs:base64Binary` XQuery function or a `.value()` method at all).

**Solution.**

```sql
-- tests/integration/test_test2_residue_wave.py::TestScalarIdioms::test_base64_xml_idiom_per_target
CREATE PROCEDURE dbo.p_i @picture NVARCHAR(MAX) AS
BEGIN
    DECLARE @img VARBINARY(MAX) =
        CAST(N'' AS XML).value('xs:base64Binary(sql:variable("@picture"))', 'VARBINARY(MAX)')
    UPDATE t_hi SET imagen = @img WHERE n = 1
END
-- tsql -> postgresql:
v_img := DECODE(v_picture, 'base64');
-- tsql -> mysql:
SET v_img = FROM_BASE64(v_picture);
-- tsql -> oracle:
V_IMG := UTL_ENCODE.BASE64_DECODE(UTL_RAW.CAST_TO_RAW(V_PICTURE));
```

**Discussion.** Unique recognizes the whole `CAST(N'' AS XML).value(...)`
shape as a single semantic unit (a base64 decode of the variable named
inside the `sql:variable(...)` XQuery call) rather than trying to translate
the XML/XQuery machinery piece by piece — none of it survives on a target
without T-SQL's XML data type, and a literal translation would produce
nonsense. Each target gets its own native decode call instead:
PostgreSQL's `DECODE(str, 'base64')`, MySQL's `FROM_BASE64(str)`, and
Oracle's `UTL_ENCODE.BASE64_DECODE`, which itself needs the string first
cast to a raw byte sequence via `UTL_RAW.CAST_TO_RAW` (Oracle's base64
decoder operates on `RAW`, not `VARCHAR2`).

> **Note** faithful — all four spellings decode the same base64 payload to
> the same bytes; live-verified no `base64Binary` XQuery fragment leaks
> into any target. No warning.

**See Also.** [`test_test2_residue_wave.py::TestScalarIdioms`](../../../tests/integration/test_test2_residue_wave.py)
(`test_base64_xml_idiom_per_target`).
