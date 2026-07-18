#!/usr/bin/env python3
# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Generate the per-engine built-in *function* catalogs (dev-only).

The transpiler must tell a **source built-in** (which it is responsible for
translating) from a **user object** (a UDF / stored proc it must leave alone),
and must know whether an emitted name is a valid **target** built-in. sqlglot's
per-dialect ``parser.FUNCTIONS`` cannot answer this — 635 of ~686 names are
shared across all four dialects, so SOUNDEX shows as a "built-in" everywhere.

So the catalog is sourced *authoritatively* from each engine, live:

- **PostgreSQL** — ``pg_proc`` in the ``pg_catalog`` schema.
- **Oracle**     — ``V$SQLFN_METADATA`` (every SQL function the engine knows).
- **MySQL**      — ``mysql.help_topic`` rows under the Function help categories.
- **SQL Server** — no system catalog of built-ins exists, so a curated list from
  the official T-SQL function reference is embedded below (``_TSQL_CURATED``).

Introspection misses grammar-level SQL-standard functions (``CAST``,
``COALESCE``, ``EXTRACT`` — implemented in the parser, not as catalog rows);
those are added at runtime (``unique.core.builtins._SQL_STANDARD``), not here,
so the data files stay a faithful snapshot of what each engine reports.

Output: one ``<engine>.txt`` per engine under ``src/unique/core/data/builtins/``
(sorted, upper-cased, one name per line, with a provenance header). The runtime
reads those static files — it never touches a database. Re-run this script (with
the docker test stack up) to refresh the snapshot.

Usage:
    docker compose -f docker-compose.test.yaml up -d
    scripts/gen_builtins.py            # refresh all four data files
    scripts/gen_builtins.py --check    # fail if the snapshot is stale
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "src" / "unique" / "core" / "data" / "builtins"

PG_URL = "postgresql://unique:unique@localhost:5433/unique"
MYSQL = dict(
    host="127.0.0.1", port=3307, user="root", password="root", database="mysql"
)
ORACLE = dict(user="system", password="oracle", dsn="localhost:1521/FREEPDB1")

# MySQL's help_topic files a function under a *statement* or *type* category when
# its name collides (REPLACE→"Data Manipulation", DATE→"Data Types", IF→"Compound
# Statements"), so the Function-category query misses them. These are all genuine
# MySQL built-in functions — over-inclusion only ever *under*-degrades (safe).
_MYSQL_SUPPLEMENT: frozenset[str] = frozenset(
    {
        "REPLACE",
        "REPEAT",
        "INSERT",
        "IF",
        "ISNULL",
        "SHA",
        "DATE",
        "TIME",
        "TIMESTAMP",
        "INTERVAL",
        "CHAR",
        "TRUNCATE",
        "MOD",
        "LEFT",
        "RIGHT",
        "MID",
        "TRIM",
    }
)

# SQL Server has no queryable catalog of built-in functions. Curated from the
# official "Built-in functions (Transact-SQL)" reference, SQL Server 2012+.
_TSQL_CURATED: frozenset[str] = frozenset(
    {
        # String
        "ASCII",
        "CHAR",
        "CHARINDEX",
        "CONCAT",
        "CONCAT_WS",
        "DIFFERENCE",
        "FORMAT",
        "LEFT",
        "LEN",
        "LOWER",
        "LTRIM",
        "NCHAR",
        "PATINDEX",
        "QUOTENAME",
        "REPLACE",
        "REPLICATE",
        "REVERSE",
        "RIGHT",
        "RTRIM",
        "SOUNDEX",
        "SPACE",
        "STR",
        "STRING_AGG",
        "STRING_ESCAPE",
        "STRING_SPLIT",
        "STUFF",
        "SUBSTRING",
        "TRANSLATE",
        "TRIM",
        "UNICODE",
        "UPPER",
        # Numeric / math
        "ABS",
        "ACOS",
        "ASIN",
        "ATAN",
        "ATN2",
        "CEILING",
        "COS",
        "COT",
        "DEGREES",
        "EXP",
        "FLOOR",
        "LOG",
        "LOG10",
        "PI",
        "POWER",
        "RADIANS",
        "RAND",
        "ROUND",
        "SIGN",
        "SIN",
        "SQRT",
        "SQUARE",
        "TAN",
        # Date / time
        "CURRENT_TIMESTAMP",
        "CURRENT_TIMEZONE",
        "CURRENT_TIMEZONE_ID",
        "DATEADD",
        "DATEDIFF",
        "DATEDIFF_BIG",
        "DATEFROMPARTS",
        "DATENAME",
        "DATEPART",
        "DATETIME2FROMPARTS",
        "DATETIMEFROMPARTS",
        "DATETIMEOFFSETFROMPARTS",
        "DAY",
        "EOMONTH",
        "GETDATE",
        "GETUTCDATE",
        "ISDATE",
        "MONTH",
        "SMALLDATETIMEFROMPARTS",
        "SWITCHOFFSET",
        "SYSDATETIME",
        "SYSDATETIMEOFFSET",
        "SYSUTCDATETIME",
        "TIMEFROMPARTS",
        "TODATETIMEOFFSET",
        "YEAR",
        # Aggregate / analytic / ranking
        "APPROX_COUNT_DISTINCT",
        "AVG",
        "CHECKSUM_AGG",
        "COUNT",
        "COUNT_BIG",
        "GROUPING",
        "GROUPING_ID",
        "MAX",
        "MIN",
        "STDEV",
        "STDEVP",
        "SUM",
        "VAR",
        "VARP",
        "CUME_DIST",
        "DENSE_RANK",
        "FIRST_VALUE",
        "LAG",
        "LAST_VALUE",
        "LEAD",
        "NTILE",
        "PERCENT_RANK",
        "PERCENTILE_CONT",
        "PERCENTILE_DISC",
        "RANK",
        "ROW_NUMBER",
        # Table-valued / newer built-ins (SQL Server 2016+/2022+)
        "GENERATE_SERIES",
        "DATE_BUCKET",
        "OPENJSON",
        # Conversion
        "CAST",
        "CONVERT",
        "PARSE",
        "TRY_CAST",
        "TRY_CONVERT",
        "TRY_PARSE",
        # Logical / null
        "CHOOSE",
        "IIF",
        "ISNULL",
        # System / metadata / security
        "BINARY_CHECKSUM",
        "CHECKSUM",
        "COMPRESS",
        "CONTEXT_INFO",
        "CURRENT_REQUEST_ID",
        "CURRENT_TRANSACTION_ID",
        "DECOMPRESS",
        "ERROR_LINE",
        "ERROR_MESSAGE",
        "ERROR_NUMBER",
        "ERROR_PROCEDURE",
        "ERROR_SEVERITY",
        "ERROR_STATE",
        "FORMATMESSAGE",
        "HOST_ID",
        "HOST_NAME",
        "ISNUMERIC",
        "NEWID",
        "NEWSEQUENTIALID",
        "ROWCOUNT_BIG",
        "SESSION_CONTEXT",
        "XACT_STATE",
        "COL_LENGTH",
        "COL_NAME",
        "COLUMNPROPERTY",
        "DB_ID",
        "DB_NAME",
        "OBJECT_DEFINITION",
        "OBJECT_ID",
        "OBJECT_NAME",
        "OBJECT_SCHEMA_NAME",
        "OBJECTPROPERTY",
        "OBJECTPROPERTYEX",
        "PARSENAME",
        "SCHEMA_ID",
        "SCHEMA_NAME",
        "SCOPE_IDENTITY",
        "SERVERPROPERTY",
        "STATS_DATE",
        "TYPE_ID",
        "TYPE_NAME",
        "TYPEPROPERTY",
        "CURRENT_USER",
        "SESSION_USER",
        "SUSER_NAME",
        "SUSER_SNAME",
        "SYSTEM_USER",
        "USER_NAME",
        "HASHBYTES",
        "ENCRYPTBYPASSPHRASE",
        "DECRYPTBYPASSPHRASE",
        "PWDENCRYPT",
        "PWDCOMPARE",
        # JSON (2016+/2022+)
        "ISJSON",
        "JSON_MODIFY",
        "JSON_PATH_EXISTS",
        "JSON_QUERY",
        "JSON_VALUE",
        "JSON_OBJECT",
        "JSON_ARRAY",
    }
)


def _pg() -> set[str]:
    import psycopg

    q = (
        "SELECT DISTINCT upper(proname) FROM pg_proc p "
        "JOIN pg_namespace n ON p.pronamespace = n.oid "
        "WHERE n.nspname = 'pg_catalog'"
    )
    with psycopg.connect(PG_URL) as c:
        return {r[0] for r in c.execute(q).fetchall()}


def _oracle() -> set[str]:
    import oracledb

    c = oracledb.connect(**ORACLE)
    try:
        cur = c.cursor()
        cur.execute("SELECT DISTINCT UPPER(name) FROM V$SQLFN_METADATA")
        return {r[0] for r in cur.fetchall() if r[0]}
    finally:
        c.close()


def _mysql() -> set[str]:
    import pymysql

    c = pymysql.connect(**MYSQL)
    try:
        cur = c.cursor()
        cur.execute(
            "SELECT DISTINCT UPPER(t.name) FROM help_topic t "
            "JOIN help_category c ON t.help_category_id = c.help_category_id "
            "WHERE c.name LIKE '%Function%' OR c.name = 'Comparison Operators'"
        )
        return {r[0] for r in cur.fetchall()} | _MYSQL_SUPPLEMENT
    finally:
        c.close()


def _clean(names: set[str]) -> set[str]:
    """Keep plain identifier function names (drop operators / odd catalog rows)."""
    return {
        n for n in names if n and n.replace("_", "").isalnum() and not n[0].isdigit()
    }


def build() -> dict[str, set[str]]:
    sources = {
        "postgresql": _pg,
        "oracle": _oracle,
        "mysql": _mysql,
        "tsql": lambda: set(_TSQL_CURATED),
    }
    out: dict[str, set[str]] = {}
    for engine, fn in sources.items():
        out[engine] = _clean(fn())
    return out


def render(engine: str, names: set[str]) -> str:
    header = (
        f"# Built-in function catalog for {engine} — GENERATED by "
        f"scripts/gen_builtins.py.\n"
        f"# Authoritative live introspection + curated SQL-standard specials.\n"
        f"# Do not edit by hand; re-run the generator with the test stack up.\n"
    )
    return header + "\n".join(sorted(names)) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true", help="fail if snapshot is stale")
    args = ap.parse_args()

    cat = build()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stale = False
    for engine, names in cat.items():
        path = OUT_DIR / f"{engine}.txt"
        new = render(engine, names)
        old = path.read_text(encoding="utf-8") if path.exists() else None
        if args.check:
            if old != new:
                print(f"stale: {path.relative_to(ROOT)} ({len(names)} names)")
                stale = True
        else:
            path.write_text(new, encoding="utf-8")
            print(f"wrote {path.relative_to(ROOT)}  ({len(names)} names)")
    if args.check and stale:
        sys.exit(1)


if __name__ == "__main__":
    main()
