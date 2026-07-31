[← Procedural: cursors, dynamic SQL, system procedures, session directives](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=procedural type="SELECT ... INTO :NEW.col pseudo-row targets" direction="oracle → postgresql/mysql" kind=article order=46 -->

# `SELECT ... INTO :NEW.col1, :NEW.col2` (Oracle trigger) → PostgreSQL `NEW.col`, MySQL session variables

**Problem.** An Oracle row-level trigger can `SELECT ... INTO
:NEW.col1, :NEW.col2` directly — assigning query results straight into the
pseudo-row's columns. PostgreSQL's trigger `NEW` is a real record variable,
so it accepts the same direct assignment; MySQL's `NEW` is not an
assignable target of a multi-column `SELECT ... INTO` at all — MySQL's
`SELECT ... INTO` can only target local variables, never `NEW.col`
directly.

**Solution.**

```sql
-- tests/integration/test_oracle_source_m4_wave.py::TestPseudoRowIntoTargets
create or replace TRIGGER trg_pa BEFORE UPDATE ON u_pam FOR EACH ROW
BEGIN
    SELECT familia, grupo INTO :NEW.familia, :NEW.grupo
    FROM s_elem WHERE idelemento = :NEW.idelemento;
END;
-- oracle -> postgresql (native, direct assignment):
SELECT familia, grupo INTO NEW.familia, NEW.grupo
FROM s_elem WHERE idelemento = NEW.idelemento;

-- oracle -> mysql (routed through session variables):
SELECT familia, grupo INTO @uq_sel0, @uq_sel1
FROM s_elem WHERE idelemento = NEW.idelemento;
SET NEW.familia = @uq_sel0;
SET NEW.grupo = @uq_sel1;
```

The same routing applies when the pseudo-row column is a plain call
argument rather than a `SELECT ... INTO` target — `prc_reg_pro(:NEW.rcn_id,
:NEW.moduser)` becomes `CALL prc_reg_pro(NEW.rcn_id, NEW.moduser)` on both
PostgreSQL and MySQL, since a call argument (unlike an `INTO` target) is a
read, which both engines already support directly off `NEW`.

**Discussion.** MySQL's `SELECT ... INTO` grammar only accepts local
variable names as its targets — `NEW.col` is a record-field reference, not
a variable, and is rejected there. Unique reads the query into a set of
synthesized session variables (`@uq_sel0`, `@uq_sel1`, ... — one per `INTO`
target, in order) and follows the `SELECT` with one `SET NEW.col = @uq_selN`
per target, reproducing the same final assignment to `NEW` in two
statements instead of one. PostgreSQL needs no such split: its trigger
`NEW` is a genuine writable `RECORD`, and `INTO NEW.col1, NEW.col2` is
already valid PL/pgSQL.

> **Note** faithful — every column ends up holding the same value on both
> targets; MySQL's extra `SET` statements are a syntactic necessity, not a
> semantic difference, since the session variables are never referenced
> again after the assignment. No warning.

**See Also.** [`test_oracle_source_m4_wave.py::TestPseudoRowIntoTargets`](../../../tests/integration/test_oracle_source_m4_wave.py).
