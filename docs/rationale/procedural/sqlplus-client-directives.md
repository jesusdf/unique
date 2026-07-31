[← Procedural: cursors, dynamic SQL, system procedures, session directives](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=procedural type="SQL*Plus directives preserved as comments" direction="oracle → tsql/postgresql/mysql" kind=article order=4 -->

# `SET SERVEROUTPUT ON` and similar client directives (Oracle) → PostgreSQL / T-SQL / MySQL

**Problem.** SQL*Plus `SET` directives (`SET SERVEROUTPUT ON`,
etc.) are **line-oriented client-tool commands**, not SQL statements — they
carry no trailing `;` and configure the SQL*Plus session, not the database.

**Solution.**

```python
# tests/integration/test_sqlplus_directives.py::test_directive_commented_and_block_survives
src = "SET SERVEROUTPUT ON\nBEGIN\n  my_proc('x');\nEND;\n/"
# transpiled (oracle -> tsql/postgresql/mysql):
#   -- SET SERVEROUTPUT ON      (never shipped as executable SQL)
#   ... my_proc(...) call, still present and callable ...
```

The splitter peels a recognized directive into its
own batch; it is emitted as a `-- SET SERVEROUTPUT ON`-style comment plus a
warning, never as executable SQL — and the block that follows it still
transpiles normally.

**Discussion.** No target engine has a SQL*Plus client
to configure; the directive has no server-side counterpart at all. Before
the fix, the lack of a statement terminator made the directive **glue onto
the following block** during batch splitting and ship as invalid SQL,
corrupting ~940 statements per direction on a real-world Oracle dump.

> **Warning** `[limit]` for the directive itself (no server-side
> equivalent exists to warn toward). Faithful for the surrounding SQL, which
> now survives instead of being corrupted.

**See Also.** `src/unique/core/procedural/parser/_plsql.py` (SQL*Plus
directive parsing) · `docs/DONE.md` (M4 bring-up, 2026-07-09) ·
`tests/integration/test_sqlplus_directives.py` — no dedicated
challenge-corpus case exercises this construct directly, so the example
above is drawn from that dedicated, passing integration test rather than
from `tests/fixtures/challenge/`.
