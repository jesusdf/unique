# Challenge fixtures

A curated, growing regression corpus of **tricky source constructs** — one
script per source engine. Each new problematic case we find (a construct the
transpiler handled wrong) is added here, anonymized, so it stays fixed.

- `challenge_sqlserver.sql` — T-SQL source
- `challenge_oracle.sql` — Oracle / PL-SQL source
- `challenge_postgresql.sql` — PostgreSQL / PL-pgSQL source
- `challenge_mysql.sql` — MySQL source

Rules:

- **One construct per entry, non-repeated.** Add the *smallest* self-contained
  routine/statement that reproduces the problem; don't duplicate a construct
  already covered.
- **Anonymize.** Never copy a real object name (table, procedure, column,
  schema, revision) from a private fixture — use generic names (`t`, `c`,
  `get_top_rows`, `row_limit`). See the development-workflow skill.
- **Each entry is a fixed regression.** When you add a case, fix it and add an
  assertion in `tests/integration/test_challenge.py`; the fixture then guards
  against the bug returning.

Header each entry with a `-- CASE: <short description>` comment.
