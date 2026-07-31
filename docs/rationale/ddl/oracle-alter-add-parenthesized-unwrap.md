[← DDL: identity, temp tables, foreign keys, sequences, storage options](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=ddl type="Oracle ALTER TABLE ADD (...) parenthesized-list unwrapping" direction="oracle → tsql/postgresql/mysql" kind=article order=26 -->

# Oracle `ALTER TABLE ... ADD ( ... )` (parenthesized element list) → an unwrapped `ADD` clause

**Problem.** Oracle allows one or more table elements (columns,
constraints) to be added in a single parenthesized list —
`ALTER TABLE t ADD (CONSTRAINT fk FOREIGN KEY (col) REFERENCES p(id))`.
Every other engine's `ALTER TABLE ... ADD` grammar expects the element
directly, without an enclosing parenthesis — the parenthesized form (which
one common parser renders as `ADD COLUMNS (...)`) isn't valid syntax
anywhere else.

**Solution.**

```sql
-- found on the HR sample schema: every PK/FK/CHECK there arrives as
-- ALTER TABLE ADD (CONSTRAINT ...)
ALTER TABLE countries
ADD ( CONSTRAINT countr_reg_fk
         FOREIGN KEY (region_id)
          REFERENCES regions(region_id)
    );
-- oracle -> tsql / postgresql / mysql:
ALTER TABLE countries ADD CONSTRAINT countr_reg_fk FOREIGN KEY (region_id) REFERENCES regions (region_id)
```

**Discussion.** The parenthesized form is purely a grouping convenience
Oracle allows for adding several elements in one statement — it carries no
meaning beyond "here are the elements to add." Unique unwraps the
parentheses and re-emits each contained element as a plain `ADD <element>`
clause (a single `ADD CONSTRAINT ...` here; multiple elements would each
get their own `ADD`), matching the unparenthesized grammar every target
(including Oracle itself, which also accepts the unparenthesized single-
element form) already uses.

> **Note** faithful — the same constraint, with the same referential
> action, is added to the same table; only the parenthesized grouping
> syntax is removed, since it carries no information no target's plain
> `ADD` clause already expresses. No warning.

**See Also.** [`test_cross_dialect.py::TestOracleAlterAddParenthesized`](../../../tests/integration/test_cross_dialect.py)
(`test_single_constraint_unwrapped`).
