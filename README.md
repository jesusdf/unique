# Unique — SQL Transpiler

Unique translates SQL scripts between **SQL Server (T-SQL)**, **Oracle**,
**PostgreSQL**, and **MySQL** — including stored procedures, functions, and
triggers, not just standalone queries.

## Built on sqlglot — and what Unique adds

Unique uses [sqlglot](https://github.com/tobymao/sqlglot) for what sqlglot is
excellent at: parsing and re-emitting individual SQL **statements** across
dialects. sqlglot is a load-bearing dependency, pinned to an exact version
(see [docs/sqlglot-dependency.md](docs/sqlglot-dependency.md)).

sqlglot on its own translates *statements*. It does not translate a real
**stored-routine script** — the procedural shell around the SQL (parameters,
`DECLARE`, `IF`/`WHILE`/loops, cursors, `TRY/CATCH`, error handling,
transactions) is dialect-specific and outside sqlglot's statement model. Unique
is the layer that handles that shell and the cross-engine semantics sqlglot
doesn't, delegating the embedded DML/DQL to sqlglot. Concretely, Unique adds:

- **A procedural engine.** A real lexer/parser/transformer/emitter for the
  routine body — `CREATE PROCEDURE/FUNCTION/TRIGGER`, parameter directions
  (`IN/OUT/INOUT`), `DECLARE`, assignment, `IF`/`WHILE`/`LOOP`/`FOR`, cursors,
  `RETURN`, `RAISE`/`THROW`, `TRY/CATCH`, transactions — with the embedded DML
  routed through sqlglot. sqlglot cannot parse `CREATE PROCEDURE ... BEGIN ...
  END` as a translatable unit; Unique can.
- **Cross-engine construct rewrites that change shape, not just syntax.**
  Examples: T-SQL `TRY/CATCH` → MySQL `DECLARE ... HANDLER` (vs. Oracle/PG
  `EXCEPTION`); table variables (`DECLARE @t TABLE`) → `CREATE TEMPORARY
  TABLE`; assignment-select (`SELECT @v = expr`) → `SELECT ... INTO`;
  `STRING_SPLIT` → MySQL `JSON_TABLE`; `OUTPUT ... INTO` handled per engine
  (invalid `RETURNING` is never emitted for MySQL); PostgreSQL triggers split
  into a trigger function plus `CREATE TRIGGER`.
- **Lossy conversions are documented and reversible.** When a type or construct
  has no faithful target equivalent, Unique emits a permissive carrier plus a
  `/* UNIQUE: <original> */` comment (e.g. `SQL_VARIANT` → `TEXT /* UNIQUE:
  SQL_VARIANT */`, unresolved `%TYPE` references, dropped `SET NOCOUNT ON`), so
  nothing is silently lost and a round-trip can restore the original.
- **Original comments are preserved**, with line comments normalized to ANSI
  spacing — they are not discarded the way a statement-only translator would.
- **Functional-equivalence guards.** A structural fingerprint (DML verb counts,
  fields per statement, predicate counts, control-flow, MERGE/JOIN/GROUP BY,
  …) is compared before and after transpilation to catch silent semantic
  drift, not just syntax errors.
- **Whole-script orchestration**: batch/`GO` splitting, source-dialect
  auto-detection, and validation of the result against the *real* target
  engines in CI (not just our own assumptions).

## Features

- **4 dialects**: SQL Server, Oracle, PostgreSQL, MySQL (2012+ coverage)
- **AST + intermediate representation**: Parse → Transform → Emit
- **Plugin architecture**: add new dialects via Python entry points
- **CLI, REST API, Python library, and web UI**
- **Anonymized procedural fixtures** for all four engines, validated live in CI

## Quick start

```bash
pip install -e ".[dev]"

# CLI
unique transpile -s tsql -t postgresql -f input.sql -o output.sql
```

```python
from unique.core import transpile

print(transpile("SELECT TOP 10 * FROM users", source="tsql", target="postgresql").sql)
# SELECT * FROM users LIMIT 10
```

Or run the API + web UI with Docker:

```bash
docker run --rm -p 8000:8000 jesusdf/unique:latest   # open http://localhost:8000/
```

See **[Installation & Deployment](docs/06-installation.md)** and
**[Interfaces](docs/07-interfaces.md)** for the full CLI, Python, REST, web UI,
and Docker details.

## Documentation

- [Installation & Deployment](docs/06-installation.md) — pip, Docker, compose
- [Interfaces](docs/07-interfaces.md) — CLI, Python API, REST API, web UI
- [Compatibility Matrix](docs/01-compatibility.md) — full feature support
- [Architecture](docs/02-architecture.md) — design, components, project layout
- [Unsupported Features](docs/03-unsupported.md) — what's out of scope and why
- [Development Guide](docs/04-development-guide.md) — contributing, adding dialects
- [Procedural Engine](docs/05-procedural-engine.md) — the stored-routine pipeline
- [sqlglot Dependency](docs/sqlglot-dependency.md) — pinning and fork analysis

## License

MIT (see [LICENSE](LICENSE)).
