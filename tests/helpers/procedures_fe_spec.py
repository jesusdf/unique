# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Declarative specs + seed data for the procedures functional-equivalence harness.

``tests/fixtures/procedures/`` holds the SAME ~33 routines authored once in T-SQL
(``procedures_sqlserver.sql``) and transpiler-generated for the other three
engines. ``test_live_syntax`` only proves they *compile*; this harness proves a
routine *does the same thing* — call it with fixed inputs on each engine and the
observable effect (scalar return, OUT param, or table state) must match.

This module is the curated, declarative half (like ``FUNC_CASES`` in
``test_challenge_live``): one ``RoutineCase`` per enrolled routine, naming its
effect kind, the seed tables it needs, the fixed call inputs, and the portable
probe(s) that read its effect. The per-engine driver mechanics (callproc vs CALL,
Oracle RAW GUIDs, T-SQL ``IDENTITY_INSERT``) live in typed helpers here so the
specs stay branch-free; the actual execution + comparison is in
``tests/integration/test_procedures_fe_live.py``.

Scope is the A10-P1 start set (audit ``2026-07-31-a10p-procedures-fe-design.md``):
scalar-return, OUT-param, and single-table / cascade **table-state** routines.
Result-set routines, the ``func1``-freeze report procs, the trigger, and the TVF
stay out (brief A10-P2/P3) — every one of them is named on the exclusions ledger
(``procedures_fe_exclusions.py``), so ``enrolled + ledger == total`` holds with no
silent gap.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path
from typing import Any

_FIXTURE = (
    Path(__file__).resolve().parent.parent
    / "fixtures"
    / "procedures"
    / "procedures_sqlserver.sql"
)

# The only warnings a transpiled routine may carry and still be COMPARED. Both are
# no-ops for the fixed inputs the specs use (audit design §3, architect-approved):
#   UNIQUE-1193 — SET NOCOUNT ON / SET ROWCOUNT @col_2 dropped (a no-op when every
#                 call passes @col_2 = NULL, which the specs guarantee).
#   UNIQUE-1196 — "was T-SQL table variable …" (table-var -> temp-table rewrite,
#                 purely informational).
# Any other code (1152 SQL_VARIANT, 1163 RAISERROR-args, 1191 OUTPUT-dropped, …)
# means a documented degrade: the routine is skipped-with-reason at runtime.
BENIGN_WARNINGS = frozenset({"UNIQUE-1193", "UNIQUE-1196"})

# T-SQL identity columns need SET IDENTITY_INSERT to seed explicit key values; the
# targets generate GENERATED-BY-DEFAULT / SERIAL / AUTO_INCREMENT, which accept
# explicit inserts directly.
_IDENTITY_COLUMN = {"tbl_6": "col_31", "tbl_8": "col_93"}


@dataclass(frozen=True)
class Guid:
    """A GUID seed/argument value, rendered per engine.

    T-SQL ``UNIQUEIDENTIFIER`` / PG ``UUID`` / MySQL ``CHAR(36)`` take the dashed
    string; Oracle ``RAW(16)`` takes ``HEXTORAW`` in a literal and raw ``bytes``
    as a bound argument.
    """

    dashed: str

    @property
    def hex(self) -> str:
        return self.dashed.replace("-", "")


_GUID_A = Guid("11111111-1111-1111-1111-111111111111")
_GUID_B = Guid("22222222-2222-2222-2222-222222222222")


@dataclass(frozen=True)
class SeedTable:
    """A seed table and the fixed rows to load before a routine runs.

    Each row is ``{column: value}`` (value is ``int`` / ``str`` / ``Guid`` /
    ``None``); unspecified columns take their DDL default (NULL here). The table
    DDL is the fixture's own ``CREATE TABLE`` block, transpiled per engine.
    """

    name: str
    rows: tuple[dict[str, Any], ...] = ()


@dataclass(frozen=True)
class RoutineCase:
    """One enrolled routine and how to exercise + observe it on any engine.

    ``kind`` selects the capture path: ``scalar`` (a function — ``SELECT fn(...)``),
    ``out`` (a procedure with OUT params, read per driver), or ``table_state`` (a
    procedure run for effect, observed by ``probes``). ``args`` maps SOURCE-dialect
    parameter names to fixed inputs (missing params default to NULL, and
    ``@col_2`` is always NULL so the ROWCOUNT branch is a no-op). ``probes`` are
    portable ``SELECT ... ORDER BY`` statements valid on every engine, projecting
    away the surrogate key / GUID whose cross-engine representation differs.
    """

    name: str
    kind: str
    seed: tuple[SeedTable, ...] = ()
    args: dict[str, Any] = field(default_factory=dict)
    scalar_args: tuple[Any, ...] = ()
    probes: tuple[str, ...] = ()
    out_params: tuple[str, ...] = ()

    @property
    def object_kind(self) -> str:
        return "function" if self.kind == "scalar" else "procedure"

    @property
    def source_sql(self) -> str:
        """The routine's own definition, extracted from the T-SQL fixture."""
        return extract_routine(self.name, self.object_kind)


# --------------------------------------------------------------------------- #
# Fixture extraction (per-routine transpile tracks the CURRENT transpiler, so
# the committed generated fixtures stay the reference, never the thing executed).
# --------------------------------------------------------------------------- #
def _fixture_text() -> str:
    return _FIXTURE.read_text(encoding="utf-8")


@cache
def extract_routine(name: str, object_kind: str) -> str:
    """Return a self-contained ``CREATE`` for *name* from the T-SQL fixture.

    Procedures are authored as ``ALTER PROCEDURE`` over a one-line stub; the
    ``ALTER`` is rewritten to ``CREATE`` so the block stands alone. Functions are
    authored directly as ``CREATE FUNCTION``.
    """
    text = _fixture_text()
    if object_kind == "function":
        m = re.search(rf"CREATE FUNCTION dbo\.{name}\b.*?\nGO", text, re.S)
        if not m:
            raise KeyError(f"function {name} not found in fixture")
        return m.group(0).rstrip()
    m = re.search(rf"ALTER PROCEDURE dbo\.{name}\b.*?\nEND\r?\nGO", text, re.S)
    if not m:
        raise KeyError(f"procedure {name} not found in fixture")
    return m.group(0).replace(
        f"ALTER PROCEDURE dbo.{name}", f"CREATE PROCEDURE dbo.{name}", 1
    )


@cache
def extract_table_ddl(name: str) -> str:
    """Return the fixture's ``CREATE TABLE`` block for a seed table."""
    m = re.search(rf"IF OBJECT_ID\(N'dbo\.{name}',.*?\nGO", _fixture_text(), re.S)
    if not m:
        raise KeyError(f"table {name} not found in fixture DDL")
    return m.group(0)


@cache
def param_order(name: str) -> tuple[str, ...]:
    """The procedure's parameter names, in declaration order.

    Read from the signature (everything before the body's ``AS``), so a
    positional call can be built from the spec's name->value ``args`` map.
    """
    header = extract_routine(name, "procedure").split("\nAS", 1)[0]
    seen: list[str] = []
    for pname in re.findall(r"@(\w+)", header):
        if pname not in seen:
            seen.append(pname)
    return tuple(seen)


def discover_routines() -> frozenset[str]:
    """Every routine defined in the T-SQL fixture (procedures, functions, trigger).

    The no-silent-loss invariant is checked against this: a routine added to the
    fixture must be enrolled or ledgered, or the ratchet fails.
    """
    text = _fixture_text()
    names: set[str] = set()
    for m in re.finditer(
        r"(?:ALTER|CREATE)\s+(?:PROCEDURE|FUNCTION)\s+dbo\.(\w+)", text
    ):
        names.add(m.group(1))
    for m in re.finditer(r"CREATE\s+TRIGGER\s+dbo\.(\w+)", text):
        names.add(m.group(1))
    return frozenset(names)


# --------------------------------------------------------------------------- #
# Per-engine value rendering (kept out of the specs so cases stay branch-free).
# --------------------------------------------------------------------------- #
def seed_literal(value: Any, engine: str) -> str:
    """Render *value* as a SQL literal for a seed INSERT on *engine*."""
    if value is None:
        return "NULL"
    if isinstance(value, Guid):
        return f"HEXTORAW('{value.hex}')" if engine == "oracle" else f"'{value.dashed}'"
    if isinstance(value, bool):  # pragma: no cover - specs use ints, not bools
        return "1" if value else "0"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        return "'" + value.replace("'", "''") + "'"
    raise TypeError(f"unsupported seed value {value!r}")


def call_argument(value: Any, engine: str) -> Any:
    """Convert a spec argument to what the driver binds for *engine*.

    Only GUIDs need translation: Oracle binds ``RAW`` from ``bytes``; the others
    take the dashed string.
    """
    if isinstance(value, Guid):
        return bytes.fromhex(value.hex) if engine == "oracle" else value.dashed
    return value


def positional_args(case: RoutineCase, engine: str) -> list[Any]:
    """The routine's full positional argument list for *engine* (missing=NULL)."""
    return [call_argument(case.args.get(p), engine) for p in param_order(case.name)]


def identity_column(table: str) -> str | None:
    return _IDENTITY_COLUMN.get(table)


# --------------------------------------------------------------------------- #
# The enrolled start set (A10-P1).
# --------------------------------------------------------------------------- #
ROUTINE_CASES: tuple[RoutineCase, ...] = (
    # -- scalar return ------------------------------------------------------- #
    RoutineCase(
        name="func3",
        kind="scalar",
        scalar_args=("'k'", "'the-default'"),  # passthrough stub returns @def
    ),
    # -- OUT params ---------------------------------------------------------- #
    # proc_13 is enrolled but degrades on UNIQUE-1152 (SQL_VARIANT @val); it is
    # skipped-with-reason at runtime (the SQL_VARIANT branch is a no-op when @val
    # is NULL, but the code is not on the benign allowlist). Kept enrolled so the
    # ratchet counts it and A10-P2 picks it up once 1152 is handled.
    RoutineCase(
        name="proc_13",
        kind="out",
        args={"col": "c", "op": "=", "param": "@p"},  # @val omitted -> NULL
        out_params=("where",),
    ),
    # proc_14's @query is an OUTPUT param the body READS (@query = @query + ' ' +
    # @filter): T-SQL OUTPUT is INOUT, so the caller's input must survive to the
    # target. With @query='base', @filter='flt' the effect is @query='base flt'
    # (and the write-only @page -> NULL). Before B58 every target emitted a
    # write-only OUT and returned NULL with zero warnings; enrolled once the
    # OUTPUT -> IN OUT/INOUT mapping landed.
    RoutineCase(
        name="proc_14",
        kind="out",
        args={"query": "base", "filter": "flt"},  # @page omitted -> NULL
        out_params=("query", "page"),
    ),
    # -- table state: single-table DML (tbl_7 — no identity/GUID) ------------- #
    RoutineCase(
        name="proc_11",
        kind="table_state",
        seed=(SeedTable("tbl_7"),),  # empty; the proc INSERTs
        args={
            "col_97": 1,
            "col_31": 2,
            "col_23": 3,
            "col_15": "x",
            "col_98": 7,
            "col_99": "note",
        },
        probes=(
            "SELECT col_97, col_31, col_23, col_15, col_98, col_99 "
            "FROM tbl_7 ORDER BY col_97, col_31, col_23",
        ),
    ),
    RoutineCase(
        name="proc_10",
        kind="table_state",
        seed=(SeedTable("tbl_7", ({"col_97": 1, "col_31": 2, "col_23": 3},)),),
        args={
            "col_97": 1,
            "col_31": 2,
            "col_23": 3,  # 2nd RAISERROR guard: not-null
            "col_15": "u",
            "col_98": 9,
            "col_99": "upd",  # new values
            "col_100": 1,
            "col_101": 2,
            "col_102": 3,  # WHERE key match -> 1 row
        },
        probes=(
            "SELECT col_97, col_31, col_23, col_15, col_98, col_99 "
            "FROM tbl_7 ORDER BY col_97",
        ),
    ),
    RoutineCase(
        name="proc_15",
        kind="table_state",
        seed=(
            SeedTable(
                "tbl_7",
                (
                    {"col_97": 1, "col_31": 2, "col_23": 3},  # deleted (1 row)
                    {"col_97": 9, "col_31": 8, "col_23": 7},  # survives
                ),
            ),
        ),
        args={"col_100": 1, "col_101": 2, "col_102": 3},
        probes=("SELECT col_97, col_31, col_23 FROM tbl_7 ORDER BY col_97",),
    ),
    # -- table state: tbl_8 (INT identity key match) ------------------------- #
    RoutineCase(
        name="proc_16",
        kind="table_state",
        seed=(SeedTable("tbl_8", ({"col_93": 1},)),),
        # @col_93 must be non-NULL: proc_16 raises 40302 on IF @col_93 IS NULL.
        args={"col_112": 1, "col_93": 1, "col_15": "v", "col_31": 8, "col_39": 2},
        probes=("SELECT col_15, col_31, col_39 FROM tbl_8 ORDER BY col_93",),
    ),
    RoutineCase(
        name="proc_18",
        kind="table_state",
        seed=(SeedTable("tbl_8", ({"col_93": 1}, {"col_93": 2})),),
        args={"col_112": 1},
        probes=("SELECT col_93 FROM tbl_8 ORDER BY col_93",),
    ),
    # -- table state: tbl_6 (INT identity key match, wide row) --------------- #
    RoutineCase(
        name="proc_19",
        kind="table_state",
        seed=(SeedTable("tbl_6", ({"col_31": 1, "col_32": None, "col_42": None},)),),
        args={"col_101": 1, "col_31": 1, "col_12": 5, "col_13": 6, "col_62": "m6"},
        probes=("SELECT col_12, col_13, col_62 FROM tbl_6 ORDER BY col_62",),
    ),
    RoutineCase(
        name="proc_21",
        kind="table_state",
        seed=(
            SeedTable(
                "tbl_6",
                (
                    {"col_31": 1, "col_32": None, "col_42": None},  # deleted
                    {"col_31": 2, "col_32": None, "col_42": None},  # survives
                ),
            ),
        ),
        args={"col_101": 1},
        probes=("SELECT col_31 FROM tbl_6 ORDER BY col_31",),
    ),
    # -- table state: tbl_3 (GUID key match) --------------------------------- #
    RoutineCase(
        name="proc_22",
        kind="table_state",
        seed=(SeedTable("tbl_3", ({"col_6": _GUID_A},)),),
        args={
            "col_6": _GUID_A,
            "col_115": _GUID_A,  # guard + WHERE match
            "col_7": 7,
            "col_91": "p91",
            "col_19": "r",
        },  # new values
        probes=("SELECT col_7, col_91, col_19 FROM tbl_3 ORDER BY col_7",),
    ),
    RoutineCase(
        name="proc_24",
        kind="table_state",
        seed=(
            SeedTable(
                "tbl_3",
                # matched row keeps col_7 NULL (the WHERE guards @col_133=NULL);
                # the col_7=99 row does not match and survives.
                ({"col_6": _GUID_A}, {"col_6": _GUID_B, "col_7": 99}),
            ),
        ),
        args={"col_115": _GUID_A},
        probes=("SELECT col_7 FROM tbl_3 ORDER BY col_7",),
    ),
    # -- table state: multi-table cascade (GUID + identity) ------------------ #
    RoutineCase(
        name="proc_27",
        kind="table_state",
        seed=(
            SeedTable(
                "tbl_2",
                (
                    {"col_1": 1, "col_6": _GUID_A, "col_4": 100},  # cascade target
                    {"col_1": 2, "col_6": _GUID_B, "col_4": 200},  # survives
                ),
            ),
            SeedTable(
                "tbl_6",
                (
                    {"col_31": 10, "col_6": _GUID_A},  # deleted
                    {"col_31": 11, "col_6": _GUID_B},  # survives
                ),
            ),
            SeedTable(
                "tbl_8",
                (
                    {"col_93": 100, "col_31": 10},  # deleted (via tbl_6 join)
                    {"col_93": 101, "col_31": 11},  # survives
                ),
            ),
            SeedTable(
                "tbl_3",
                ({"col_6": _GUID_A, "col_7": 1}, {"col_6": _GUID_B, "col_7": 2}),
            ),
        ),
        args={"col_1": 1},
        probes=(
            "SELECT col_1, col_4 FROM tbl_2 ORDER BY col_1",
            "SELECT col_31 FROM tbl_6 ORDER BY col_31",
            "SELECT col_93, col_31 FROM tbl_8 ORDER BY col_93",
            "SELECT col_7 FROM tbl_3 ORDER BY col_7",
        ),
    ),
)

ENROLLED = tuple(c.name for c in ROUTINE_CASES)
