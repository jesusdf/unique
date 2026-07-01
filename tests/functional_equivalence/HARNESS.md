# Running the functional-equivalence harness

This is the **runbook** for executing the harness against real engines (the
design rationale lives in `README.md`). Everything except the live runs is
already verified in CI without any database:

- `test_state_check.py` — value normalization + table comparison (pure).
- `test_engine_runner.py` — the statement splitter, plus an end-to-end
  read+compare smoke test on **SQLite** (stands in for a real engine).

The live test (`test_functional_equivalence_live.py`) is **skipped** unless the
matching connection URL env var is set, so it never breaks CI.

## What the live test does

For each target in {PostgreSQL, MySQL, Oracle, and the T-SQL identity run}:

1. Transpile `schema/<dialect>.sql` and `scenario/<dialect>.sql` from T-SQL to
   the target (the identity run uses the canonical T-SQL unchanged).
2. Execute the transpiled schema, then the scenario, on the live database.
3. Read every table and assert it matches `expected_state.yaml` after
   per-engine value normalization.

All four reaching the same engine-agnostic state == functional equivalence.

## 1. Start the databases

```bash
docker compose -f docker-compose.test.yaml up -d
# wait for healthchecks (Oracle takes the longest on first boot)
docker compose -f docker-compose.test.yaml ps
```

## 2. Install the drivers you need

```bash
pip install psycopg pymysql oracledb pyodbc
```

(Only the drivers for the engines you point at are required; a missing driver
just skips that engine.)

## 3. Run

```bash
UNIQUE_TEST_PG_URL=postgresql://unique:unique@localhost:5433/unique \
UNIQUE_TEST_MYSQL_URL=mysql://unique:unique@localhost:3307/unique \
UNIQUE_TEST_ORACLE_URL=oracle://system:oracle@localhost:1521/FREEPDB1 \
pytest tests/functional_equivalence/test_functional_equivalence_live.py -v
```

Add `UNIQUE_TEST_MSSQL_URL=...` (with `pyodbc`) to include the T-SQL identity run.

## 4. Expected first-run adjustments

The transpiler is the system under test, so a first live run is where the final
per-engine wrinkles surface. Likely spots, and where to fix each:

- **Statement splitting.** If a routine body is split mid-block, refine
  `split_statements` in `engine_runner.py` (it already keeps `$$ … $$` and
  `BEGIN … END` bodies intact, and handles Oracle `/`).
- **A transpiled statement errors on an engine.** That is a real transpiler
  finding — capture it as a failing case and fix the emitter (the whole point of
  the harness). The error message names the offending statement.
- **A value compares unequal but is "morally" equal** (e.g. an engine returns a
  bool as `b'\x01'`, or a date as a string in a different shape): extend
  `normalize` in `state_check.py`. Keep it minimal and add a unit test in
  `test_state_check.py` for the new coercion.
- **Teardown.** `_drop_all` is best-effort (tries `DROP TABLE IF EXISTS` then
  `DROP TABLE`). If an engine needs `CASCADE`, add it there.

## Notes

- Reads use `SELECT * FROM <table> ORDER BY id`; every canonical table has an
  `id` PK, so ordering is deterministic.
- `invoice.created_at` / `updated_at` are **not** value-asserted (clock-
  sensitive) — they are simply absent from `expected_state.yaml`.
- MySQL/Oracle set-based triggers are documented divergences (no named
  transition tables); if their trigger-maintained values (`invoice.total`,
  `is_paid`) differ there, that is expected — assert those on PostgreSQL (and
  T-SQL) and treat MySQL/Oracle trigger effects as out of scope for Phase 1.
