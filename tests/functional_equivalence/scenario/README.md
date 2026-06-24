# Scenario

The **canonical** scenario lives here: the ordered SQL that, run against a fresh
schema, produces the state asserted in `../expected_state.yaml`.

Planned files (added in the build-out, see `../README.md`):

- `canonical.sql` — the **single source of truth** for Phase 1: DDL (or `\i
  ../schema/canonical.sql`) + seed inserts + mutations, authored in T-SQL. The
  transpiler generates the MySQL / PostgreSQL / Oracle variants; all four are
  run and checked against `../expected_state.yaml`.
- (Phase 2) `canonical_mysql.sql`, `canonical_postgresql.sql`,
  `canonical_oracle.sql` — each engine's natively-authored scenario, for the
  full 4×4 cross-transpilation matrix.

Authoring rules (recap from `../README.md`):

- Every mutation's outcome must be **deterministic across engines** — fixed
  literal dates, explicit `DECIMAL(p, s)`, no integer-division / NULL-concat /
  rounding / collation dependence in any asserted value.
- Exercise the "interesting" paths on purpose: a **direct** insert/update, an
  update on a **triggered** table, and inserts/updates **from a stored
  procedure** — so functional equivalence is tested beyond plain DML.
- Keep it minimal: only what the coverage matrix requires.
