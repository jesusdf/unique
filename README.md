> ℹ️ **Note from the developer / analyst**
> 
> This project is just too big for one lifetime, so I'm backing it with AI. 
> The goal is to provide a working tool; how we get there is not that important.

# Unique — SQL Transpiler

Unique translates SQL scripts between **SQL Server (T-SQL)**, **Oracle**,
**PostgreSQL**, and **MySQL** — including stored procedures, functions, and
triggers, not just standalone queries. **SQLite** is an import-only source
(it has no procedural language, so it can never be a target).

## What it adds over sqlglot

[sqlglot](https://github.com/tobymao/sqlglot) (a load-bearing, exact-pinned
dependency — see [docs/sqlglot-dependency.md](docs/sqlglot-dependency.md))
translates individual statements. Unique adds the stored-routine shell that
is outside sqlglot's statement model:

- **A procedural engine** — lexer/parser/transformer/emitter for
  `CREATE PROCEDURE/FUNCTION/TRIGGER` bodies: parameter directions, `DECLARE`,
  `IF`/`WHILE`/`LOOP`/`FOR`, cursors, `RETURN`, `RAISE`/`THROW`, `TRY/CATCH`,
  transactions — with the embedded DML routed through sqlglot.
- **Shape-changing rewrites**, not just syntax: T-SQL `TRY/CATCH` → MySQL
  `DECLARE ... HANDLER`; table variables → temporary tables;
  `SELECT @v = expr` → `SELECT ... INTO`; `STRING_SPLIT` → MySQL
  `JSON_TABLE`; PostgreSQL triggers split into trigger function +
  `CREATE TRIGGER`.
- **No silent loss** — a construct with no faithful equivalent ships as a
  permissive carrier plus a `/* UNIQUE: <original> */` comment and a warning,
  so a round-trip can restore the original. Source comments are preserved.
- **Whole-script orchestration** — batch/`GO` splitting, source-dialect
  auto-detection, source-syntax validation (errors located by line before
  transpiling), and a structural fingerprint compared before/after to catch
  silent semantic drift. Output is validated against the real target engines
  in CI.
- **Measured maturity** — per-direction support is stated as a validity
  percentage measured by running transpiled real-world scripts on live
  engines; current numbers in [docs/STATUS.md](docs/STATUS.md).

## Quick start

```bash
pip install -e ".[dev]"

# CLI
unique transpile input.sql --from tsql --to postgresql -o output.sql

# Structural-similarity of two scripts (migration audit; dialects auto-detect)
unique compare original.sql migrated.sql --dialect-a tsql --dialect-b oracle
```

```python
from unique.core import transpile

print(transpile("SELECT TOP 10 * FROM users", source="tsql", target="postgresql").sql)
# SELECT * FROM users LIMIT 10
```

Or run the REST API + web UI with Docker (image published on release tags):

```bash
docker run --rm -p 8000:8000 jesusdf/unique:latest   # open http://localhost:8000/
```

Full CLI, Python, REST, web UI, and Docker details:
[Installation & Deployment](docs/06-installation.md) and
[Interfaces](docs/07-interfaces.md).

## Documentation

- [Installation & Deployment](docs/06-installation.md) — pip, Docker, compose
- [Interfaces](docs/07-interfaces.md) — CLI, Python API, REST API, web UI
- [Compatibility Matrix](docs/01-compatibility.md) — full feature support
- [Architecture](docs/02-architecture.md) — design, components, project layout
- [Unsupported Features](docs/03-unsupported.md) — what's out of scope and why
- [Development Guide](docs/04-development-guide.md) — contributing, adding dialects
- [Procedural Engine](docs/05-procedural-engine.md) — the stored-routine pipeline
- [sqlglot Dependency](docs/sqlglot-dependency.md) — pinning and fork analysis

## Project language

English-only by design — code, comments, docs, and all program output.
Transpiler diagnostics quote or mirror the engines' own error text, which is
English, so every message stays searchable verbatim.

## License

MIT (see [LICENSE](LICENSE)).
