# Unique — Documentation index

Start here. The two entry points most readers want first:

## ⭐ Architecture

- **[02-architecture.md](02-architecture.md)** — the design: AST/IR pipeline,
  dialect plugins, the procedural engine, and the decisions behind them.
- [05-procedural-engine.md](05-procedural-engine.md) — the stored-routine
  pipeline (lexer → parser → transformer → emitter, one plugin per engine).

## ⭐ Rationale — the "why" wiki

Why Unique emits what it emits when a construct has no direct equivalent, or
when the faithful conversion is non-obvious. Written for readers outside the
project; every claim is traceable to a verified corpus case.

- **[rationale/README.md](rationale/README.md)** — how the pages work + index.
- By topic: [datetime](rationale/datetime.md) ·
  [strings & collation](rationale/strings-collation.md) ·
  [aggregates & windows](rationale/aggregates-windows.md) ·
  [DML](rationale/dml.md) · [DDL](rationale/ddl.md) ·
  [procedural](rationale/procedural.md)
- **[reference/warnings.md](reference/warnings.md)** — every `UNIQUE-NNNN`
  diagnostic code the transpiler can emit, with its rationale. If you found a
  code in your migrated SQL, look it up here.

## Reference (generated — do not edit by hand)

Machine-generated from the code by `scripts/generate_reference_docs.py`,
kept fresh by a CI gate:

- [reference/limits.md](reference/limits.md) — the approved-degradation catalog.
- [reference/coverage.md](reference/coverage.md) — challenge-corpus counts.
- `reference/mappings-<source>-<target>.md` — per-engine-pair function/type
  mapping matrices (12 pages).

## Using Unique

- [06-installation.md](06-installation.md) — pip / Docker / compose.
- [07-interfaces.md](07-interfaces.md) — CLI (`transpile`, `compare`,
  `--ignore UNIQUE-NNNN`), Python API, REST API, web UI.
- [01-compatibility.md](01-compatibility.md) — the feature compatibility matrix.
- [03-unsupported.md](03-unsupported.md) — the normative catalog of what is
  out of scope or degrades, and why.

## Contributing / project state

- [04-development-guide.md](04-development-guide.md) — how to add features and
  run the test suites.
- [STATUS.md](STATUS.md) — current project state at a glance.
- [TODO.md](TODO.md) — pending work (authoritative backlog);
  [MILESTONES.md](MILESTONES.md) — closed backlog summaries;
  [DONE.md](DONE.md) — the detailed why/how archive.
- [sqlglot-dependency.md](sqlglot-dependency.md) — the parsing foundation and
  its version policy.
