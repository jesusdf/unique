# UML catalog of the transpilable surface

`catalog.mmd` is an engine-agnostic UML class diagram that documents **what the
`unique` transpiler can translate** — the full object catalog, not any single
test fixture. It is the visual companion to [`../01-compatibility.md`](../01-compatibility.md),
which remains the authoritative, per-engine feature matrix.

## What it shows

Every object **kind** the transpiler supports, drawn with a UML stereotype:

- `«table»` — with PK / FK / UNIQUE / CHECK / DEFAULT / identity annotations
- `«view»` — including a date-driven view (`v_overdue_invoices`)
- `«sequence»` — (MySQL maps to `AUTO_INCREMENT`)
- `«function-scalar»` and `«function-table»` — the latter flagged where a target
  (MySQL) has no equivalent
- `«procedure»` — covering DML-from-a-procedure, UPDATE-with-JOIN, and
  cursor/loop UPDATE shapes
- `«trigger»` — AFTER INSERT/UPDATE, BEFORE UPDATE, and AFTER INSERT variants

Solid arrows are **structural** (FK relationships); dotted arrows are
**behavioral dependencies** (`reads` / `writes` / `updates` / `uses`) showing
which table a routine or trigger touches. The example domain is the invoicing
model, chosen because it naturally exercises triggers, procedures, scalar &
table functions, views, sequences, date arithmetic, and several UPDATE shapes —
the same constructs enumerated in the compatibility matrix.

This diagram deliberately includes the **stored procedures and triggers** that a
plain entity-relationship diagram omits, so the procedural surface the project
transpiles is visible at a glance.

## Rendering

A pre-rendered `catalog.svg` is committed for convenience. To regenerate after
editing `catalog.mmd`:

```bash
npx -y @mermaid-js/mermaid-cli -i catalog.mmd -o catalog.svg
```

> Keep `catalog.mmd` and `01-compatibility.md` in sync: when the matrix gains or
> loses a supported construct, reflect it here too.
