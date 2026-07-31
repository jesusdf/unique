[← Procedural: cursors, dynamic SQL, system procedures, session directives](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=procedural type="Anonymous block flattening" direction="oracle → tsql" kind=article order=39 -->

# Oracle top-level anonymous block (`DECLARE … BEGIN … END;`) → a plain T-SQL batch

**Problem.** Oracle's top-level anonymous block — `DECLARE ... BEGIN ...
END; /` — is a PL/SQL shell with its own `DECLARE` section and
`BEGIN`/`END` delimiters. T-SQL has no such shell: a batch of statements
*is* the block, and `DECLARE` always names a `@variable` inline rather than
opening a section.

**Solution.**

```sql
-- tests/integration/test_anonymous_block_tsql.py::test_anonymous_block_flattens_to_tsql_batch
DECLARE
  v_cnt NUMBER := 0;
BEGIN
  SELECT COUNT(*) INTO v_cnt FROM t;
  IF v_cnt = 0 THEN
    INSERT INTO t (id) VALUES (1);
  END IF;
END;
/
-- oracle -> tsql:
DECLARE @cnt DECIMAL = 0;
SELECT @cnt = COUNT(*) FROM t;
IF @cnt = 0
BEGIN
    INSERT INTO t (id) VALUES (1);
END
```

A block with no declarations (`BEGIN INSERT INTO t (id) VALUES (1); END;
/`) flattens the same way, just without a leading `DECLARE`. A `DECLARE`
section with several variables keeps every one of them, each on its own
`DECLARE @var type;` line, with every reference to the variable renamed
consistently through the body.

**Discussion.** The Oracle block's `DECLARE` header and its `BEGIN`/`END`
pair carry no information T-SQL needs: the declaration section becomes a
plain sequence of `DECLARE @var type = init;` statements at the top of the
batch, and the body's statements follow directly — there is no batch-level
`BEGIN`/`END` wrapper to emit, since T-SQL only uses `BEGIN`/`END` to scope
a *conditional* or *loop* body, not an entire batch. Recognizing the shape
matters because the alternative — falling through to the general DML path
— mangles the block into invalid fragments (a bare `DECLARE` line with no
`@variable`, an unterminated `BEGIN`/`END` pair) rather than either
flattening it correctly or degrading it honestly.

> **Note** faithful — every declaration and every body statement survives;
> only the Oracle-only shell syntax (the `DECLARE` header line, `BEGIN`,
> `END;`, and the trailing `/`) is removed, since T-SQL has no matching
> shell.

**See Also.** [`test_anonymous_block_tsql.py`](../../../tests/integration/test_anonymous_block_tsql.py)
(`test_anonymous_block_flattens_to_tsql_batch`,
`test_block_without_declarations_flattens_too`,
`test_declare_section_with_multiple_declarations`).
