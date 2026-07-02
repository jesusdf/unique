# 05 — Documentation issues

The docs are unusually complete for a project at this stage (compatibility
matrix, architecture, unsupported list, dev guide, status/history). The
problem is **drift**: several claims describe intended behavior as if it were
implemented, and the README's CLI examples don't run.

## D1. README/docs show CLI flags that don't exist

Actual interface (verified with `unique transpile --help`):

```
unique transpile [INPUT_FILE] --from <dialect> --to <dialect> [-o OUT] [--db-url URL]
```

Broken examples:

- `README.md:68` — `unique transpile -s tsql -t postgresql -f input.sql -o output.sql`
  (`-s`, `-t`, `-f` are not defined; fails immediately).
- `docs/07-interfaces.md` — same `-s/-t/-f` style throughout (lines 11, 14,
  129, 133, 137, 141). Line 14 additionally passes inline SQL as the
  positional argument, which is declared `click.Path(exists=True)` and can
  never accept a SQL string.
- `docs/02-architecture.md:379` and `docs/04-development-guide.md:54` use the
  **correct** `--from/--to` form — so the fix is to align README + doc 07 to
  these (or add the short aliases to the CLI; either way, make them match).

## D2. Compatibility matrix overstates behavior (verified against v0.7.0)

| Claim | Location | Reality |
|---|---|---|
| `ROWNUM … ✅ → LIMIT / ROW_NUMBER()` | `docs/01-compatibility.md:51` | `ROWNUM` passes through untranslated to PostgreSQL (invalid) — doc 01, S1-5 |
| `MERGE → MySQL ⚠️ INSERT ON DUP + UPDATE` and §3.6 "the transpiler decomposes MERGE into …" | `docs/01-compatibility.md:146`, `docs/03-unsupported.md:136` | MERGE is replaced by a comment; no rewrite, no warning — doc 01, S1-3 |
| `Boolean … ✅` (BIT / NUMBER(1) / BOOLEAN) | `docs/01-compatibility.md:203` | Types map, but `TRUE/FALSE` **literals** reach T-SQL unchanged (invalid) — doc 01, S1-9 |

## D3. README principles vs. observed behavior

- *"Lossy conversions are documented and reversible … nothing is silently
  lost"* — contradicted by MERGE→MySQL (empty `warnings`/`unsupported`), the
  dropped `THROW` message, and the `(+)` join rewrite (doc 01). The principle
  is right; enforce it (see the cross-cutting fix in doc 01) and until then,
  soften the claim.
- *"Functional-equivalence guards … catch silent semantic drift"* — the
  fingerprint exists but runs only over test fixtures in CI; it is not a
  product feature a user benefits from. Either expose it (`unique verify`) or
  describe it as a CI mechanism.

## D4. Minor

- `docs/STATUS.md` says the procedural fixtures load "with **0 errors**" into
  each engine — true for the fixtures, but easy to misread as a statement
  about arbitrary input; scope the sentence.
- `README.md` Quick start shows `docker run … jesusdf/unique:latest` — worth a
  note that the image is only published on version tags, so `latest` can lag
  `main`.
- The audit folder itself (`audit/`) is not mentioned in `.gitignore` or the
  docs index; if audits become recurring, link them from `docs/STATUS.md`.

## Recommendation

Docs that assert behavior should be generated or verified from code where
possible: the compatibility matrix rows are ideal candidates for a test that
walks the table and asserts each ✅ against a probe input (which would have
flagged D2 automatically).
