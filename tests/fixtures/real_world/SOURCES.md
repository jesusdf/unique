# Real-World SQL Fixtures — Sources

These SQL scripts are public sample databases used to exercise the
transpiler against real, non-trivial schemas (DDL, constraints, views,
and — where present — stored routines). They are **not authored by this
project**; each is included verbatim under its upstream license, with
attribution below. They are used only as test inputs.

| File | Engine | Upstream source | Retrieved |
|------|--------|-----------------|-----------|
| `adventureworks_lt_sqlserver.sql` | SQL Server | [PaulDSheriff/AdventureWorksLT](https://github.com/PaulDSheriff/AdventureWorksLT/blob/master/AdventureWorksLT-All.sql) | 2026-06-18 |
| `hr_create_oracle.sql` | Oracle | [oracle-samples/db-sample-schemas](https://github.com/oracle-samples/db-sample-schemas/blob/main/human_resources/hr_create.sql) | 2026-06-18 |
| `sakila_schema_mysql.sql` | MySQL | [LintangWisesa/Sakila_MySQL_Example](https://github.com/LintangWisesa/Sakila_MySQL_Example/blob/master/sakila-schema.sql) | 2026-06-18 |
| `northwind_postgresql.sql` | PostgreSQL | [pthom/northwind_psql](https://github.com/pthom/northwind_psql/blob/master/northwind.sql) | 2026-06-18 |

## Notes on licensing

- **AdventureWorksLT** — Microsoft sample database; the AdventureWorks
  family is distributed by Microsoft under the MIT License.
- **HR schema** — part of Oracle's `db-sample-schemas`, released by Oracle
  under the Universal Permissive License (UPL) / MIT (see the header in the
  file).
- **Sakila** — the Sakila sample database is Copyright (c) Oracle and
  licensed under the BSD license (see the header in the file).
- **Northwind (PostgreSQL port)** — Northwind is a long-standing Microsoft
  sample database; this PostgreSQL port is published by `pthom`.

Each file retains its original copyright and license headers. Consult the
upstream repositories for full license terms.

## Private fixtures (not in this repository)

For SQL Server and Oracle we also validate against a private, real
production-style script (`procedures.sql`) that exercises stored
procedures, functions, and triggers. That file is **provided out-of-band
and is never committed** (see `.gitignore`). Tests that need it skip
cleanly when it is absent.
