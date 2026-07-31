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
to configure; the directive has no server-side counterpart at all. Because
the directive carries no statement terminator, it has to be recognized and
peeled off explicitly during batch splitting — otherwise it would glue onto
the following block and ship as part of it instead of as its own comment.

> **Warning** `[limit]` for the directive itself (no server-side
> equivalent exists to warn toward). Faithful for the surrounding SQL, which
> transpiles normally around the removed directive.

**See Also.** [`tests/integration/test_sqlplus_directives.py`](../../../tests/integration/test_sqlplus_directives.py) — no dedicated
challenge-corpus case exercises this construct directly, so the example
above is drawn from that dedicated, passing integration test rather than
from `tests/fixtures/challenge/`.
