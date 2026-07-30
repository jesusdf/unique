# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Declarative rationale side-table for the ``UNIQUE-NNNN`` catalog (B31).

The *why* of each degrade/creative conversion — the engine-level reason, a
worked example, and the exact divergence — used to live only in free-form
docstrings and hand-written ``docs/rationale/`` pages, which drift. This module
makes that narrative layer **generable**: each diagnostic code may carry a
:class:`Rationale`, keyed by the same ``UNIQUE-NNNN`` code the B32 registry
(:mod:`unique.core.diagnostics`) allocates. ``scripts/generate_reference_docs.py``
(T8) then emits ``docs/reference/warnings.md`` mechanically, and
``tests/unit/core/test_diagnostics.py`` reports codes with no rationale
(a floor that ratchets *down*, never up).

Design (B31 "Design constraint"):

* A **side-table keyed by the code**, deliberately a separate module rather
  than extra fields on :class:`~unique.core.diagnostics.Diagnostic`. The B32
  registry stays a lean ``code -> {category, message}`` table read by every
  emission site and by the registry-integrity test; the rationale is
  docs-generation metadata consumed only at *build* time by T8 and the
  coverage test. No emitter imports this module — zero runtime cost, and no
  churn on the shared ``DIAGNOSTICS`` dict.
* Every field must be **traceable** (the ``docs/rationale/`` rule): each entry
  below is sourced from a curated ``docs/rationale/*.md`` page and/or a live
  probe of the named corpus case, so ``example_case`` names a real
  ``tests/fixtures/challenge/`` slug (or a ``path::test`` reference where no
  corpus case exercises the construct). A code whose rationale cannot be
  sourced honestly is **absent** here — the coverage check reports it; it is
  never invented.
"""

from __future__ import annotations

from typing import NamedTuple


class Rationale(NamedTuple):
    """Narrative metadata for one ``UNIQUE-NNNN`` diagnostic.

    * ``construct`` — the source construct's name (what the user wrote).
    * ``reason`` — the *engine-level* why a direct mapping does not exist
      (a missing value type, a different clamping rule, a parser limit…),
      at the ``docs/rationale/`` bar — never merely "unsupported".
    * ``example_case`` — a ``tests/fixtures/challenge/`` case slug, or a
      ``path::test`` reference where no corpus case exercises the construct.
    * ``divergence`` — ``"faithful"``, or a precise description of what
      differs between source and target.
    """

    construct: str
    reason: str
    example_case: str
    divergence: str


_R = Rationale

#: ``UNIQUE-NNNN`` -> :class:`Rationale`. Keys must be registered in
#: :data:`unique.core.diagnostics.DIAGNOSTICS` (enforced by the coverage test).
#: Append entries only when every field is honestly sourceable; see the module
#: docstring. Keeping this sorted by code eases review against the registry.
RATIONALES: dict[str, Rationale] = {
    "UNIQUE-1002": _R(
        construct="SET IDENTITY_INSERT ON/OFF (T-SQL)",
        reason=(
            "T-SQL requires IDENTITY_INSERT ON before a script may supply its own "
            "value for an identity column; no other engine has an explicit "
            "identity-override mode — they simply accept an explicit value in the "
            "INSERT column list — so the ON/OFF bracket has nothing to map to."
        ),
        example_case="reda-ts-identity-insert",
        divergence=(
            "The INSERT's data is faithful; the two SET directives degrade to carriers "
            "(one warning)."
        ),
    ),
    "UNIQUE-1014": _R(
        construct="Physical index storage clause, e.g. WITH (FILLFACTOR = n) (T-SQL)",
        reason=(
            "FILLFACTOR and sibling physical clauses reserve per-page free space — a "
            "storage-tuning knob with no logical effect on query results; Oracle and "
            "MySQL CREATE INDEX have no equivalent clause."
        ),
        example_case="reda-ts-index-fillfactor-mysql",
        divergence=(
            "Faithful in result (storage-only); the clause is dropped and kept in a "
            "restorable note."
        ),
    ),
    "UNIQUE-1015": _R(
        construct=(
            "DISTINCT / ORDER BY over a string column under MySQL's default collation"
        ),
        reason=(
            "MySQL's default collation is case-insensitive, so DISTINCT / GROUP BY / "
            "ORDER BY treat 'a' and 'A' as equal and collapse them into one row; the "
            "case-sensitive PostgreSQL/Oracle defaults keep them distinct — a "
            "row-count divergence no ORDER BY LOWER() rewrite can bridge without "
            "column-level collation visibility."
        ),
        example_case="my-distinct-case",
        divergence="Documented limit, warned — deduplicated row counts may differ.",
    ),
    "UNIQUE-1016": _R(
        construct=(
            "GROUP BY CUBE / ROLLUP / GROUPING SETS super-aggregate rows (→ MySQL)"
        ),
        reason=(
            "MySQL has no CUBE / GROUPING SETS and only a trailing WITH ROLLUP, so a "
            "multi-element grouping's subtotal (super-aggregate) rows cannot be "
            "produced; only the base grouping is kept."
        ),
        example_case="pg-grouping-fn",
        divergence="Warned — base grouping kept; subtotal rows omitted.",
    ),
    "UNIQUE-1039": _R(
        construct="Oracle TIMESTAMP WITH LOCAL TIME ZONE column (→ PostgreSQL)",
        reason=(
            "PostgreSQL timestamptz has the identical session-time-zone display "
            "behaviour as Oracle's LTZ (live-verified: the same instant shows 12:00 in "
            "a UTC session and 07:00 in a New York session), so the column maps "
            "directly rather than losing anything."
        ),
        example_case="ora-dttypes",
        divergence=(
            "Faithful — same instant, same session-dependent wall-clock display."
        ),
    ),
    "UNIQUE-1040": _R(
        construct="Oracle TIMESTAMP WITH LOCAL TIME ZONE column (→ T-SQL)",
        reason=(
            "T-SQL has no session-local timestamp type; the column maps to "
            "DATETIMEOFFSET, which keeps a fixed stored offset instead of re-deriving "
            "the session's own time zone on every read."
        ),
        example_case="ora-dttypes",
        divergence=(
            "Warned limit — the value's instant is kept, but the session-time-zone "
            "display is not reproduced."
        ),
    ),
    "UNIQUE-1041": _R(
        construct="Oracle TIMESTAMP WITH LOCAL TIME ZONE column (→ MySQL)",
        reason=(
            "MySQL has no session-local timestamp type; the column maps to TIMESTAMP, "
            "which normalizes to UTC storage instead of re-deriving the session's own "
            "time zone on every read."
        ),
        example_case="ora-dttypes",
        divergence=(
            "Warned limit — the value's instant is kept, but the session-time-zone "
            "display is not reproduced."
        ),
    ),
    "UNIQUE-1042": _R(
        construct="A TIME/TIMETZ column (→ Oracle)",
        reason=(
            "Oracle has no bare TIME (or TIME WITH TIME ZONE) column type, so the "
            "time-of-day value is stored as INTERVAL DAY TO SECOND (a duration since "
            "midnight) instead."
        ),
        example_case="pg-dttypes",
        divergence=(
            "Faithful for TIME (the same time-of-day value, stored as a duration); "
            "warned limit for TIMETZ — the zone offset is dropped."
        ),
    ),
    "UNIQUE-1043": _R(
        construct=(
            "A bare PostgreSQL INTERVAL column, with no YEAR TO MONTH/DAY TO SECOND "
            "qualifier (→ Oracle)"
        ),
        reason=(
            "PostgreSQL's INTERVAL mixes year-month and day-second fields in one "
            "value; Oracle splits INTERVAL into two distinct column types, so the "
            "column maps to INTERVAL DAY TO SECOND and any year-month component has "
            "nowhere to go."
        ),
        example_case="pg-dttypes",
        divergence=(
            "Warned limit — year-month values need a separate INTERVAL YEAR TO MONTH "
            "column on Oracle."
        ),
    ),
    "UNIQUE-1044": _R(
        construct="An INTERVAL column (→ T-SQL / MySQL)",
        reason=(
            "T-SQL has no interval type at all, and MySQL's INTERVAL is only an "
            "arithmetic qualifier (e.g. INTERVAL 1 DAY), never a column type, so the "
            "interval value is kept as text instead."
        ),
        example_case="ora-tz-interval",
        divergence=(
            "Warned limit — the value is kept as text, not usable in interval "
            "arithmetic on the target."
        ),
    ),
    "UNIQUE-1045": _R(
        construct=(
            "A fractional-seconds column precision above 6 "
            "(DATETIME(n)/TIMESTAMP(n)/TIME(n) with n>6) (→ MySQL)"
        ),
        reason=(
            "MySQL's sub-second precision caps at microseconds (6 digits); a higher "
            "source precision (e.g. T-SQL DATETIME2(7)) has no wider MySQL "
            "fractional-seconds type to map onto."
        ),
        example_case="ts-datetimeoffset",
        divergence=(
            "Warned limit — precision clamped to 6; sub-microsecond digits lost."
        ),
    ),
    "UNIQUE-1046": _R(
        construct="MySQL multi-bit BIT(n>1) column (→ Oracle / T-SQL)",
        reason=(
            "Neither engine has a bit-string column type; a multi-bit BIT is a 64-bit "
            "numeric value, not a boolean, so it maps to a wide NUMBER/NUMERIC that "
            "holds the same value instead."
        ),
        example_case="my-bintypes",
        divergence=(
            "Warned limit — the numeric value is preserved but the bit-string type "
            "semantics (bitwise operations, display) are not."
        ),
    ),
    "UNIQUE-1048": _R(
        construct="T-SQL structure-clone CREATE TABLE t2 LIKE t1 (→ T-SQL / Oracle)",
        reason=(
            "T-SQL/Oracle have no native CREATE TABLE ... LIKE; the faithful idiom is "
            "an empty SELECT INTO / CTAS (WHERE 1 = 0), which clones column structure "
            "only — indexes, keys and constraints are not part of that idiom."
        ),
        example_case=(
            "tests/integration/test_pg_source_wave1.py::TestCreateTableLikeClone::test_like_tsql_empty_select_into"
        ),
        divergence="Warned limit — the source's indexes/keys are not cloned.",
    ),
    "UNIQUE-1049": _R(
        construct=(
            "IDENTITY / GENERATED AS IDENTITY with a non-default START/INCREMENT (→ "
            "MySQL)"
        ),
        reason=(
            "MySQL's only identity form is AUTO_INCREMENT, whose seed is a table "
            "option (AUTO_INCREMENT = n) with no per-column START/INCREMENT — a "
            "non-default seed/step cannot be reproduced as a column clause."
        ),
        example_case="ora-identity-opts",
        divergence="Warned limit — AUTO_INCREMENT starts at 1 and steps by 1.",
    ),
    "UNIQUE-1050": _R(
        construct=(
            "MySQL column-level ON UPDATE CURRENT_TIMESTAMP auto-refresh clause (→ "
            "other engines)"
        ),
        reason=(
            "No other engine has a column-level auto-refresh-on-update clause; the "
            "behaviour can only be reproduced there with an explicit AFTER UPDATE "
            "trigger."
        ),
        example_case="mysql-drop2-ON",
        divergence=(
            "Warned limit — the column keeps its DEFAULT but is no longer "
            "auto-refreshed; add a trigger to restore the behaviour."
        ),
    ),
    "UNIQUE-1051": _R(
        construct="A column-level COLLATE clause (→ a different target engine)",
        reason=(
            "Collation names are engine-specific catalog identifiers with no "
            "cross-engine mapping; without a live database connection, Unique cannot "
            "resolve what collation the source column actually uses."
        ),
        example_case="postgresql-drop4-COLLATE",
        divergence=(
            "Warned limit — the column uses the target's default collation; "
            "comparisons/ordering may differ."
        ),
    ),
    "UNIQUE-1052": _R(
        construct="MySQL/Oracle INVISIBLE column attribute (→ PostgreSQL / T-SQL)",
        reason=(
            "PostgreSQL and T-SQL have no invisible-column attribute (a column "
            "excluded from SELECT *), so it cannot be reproduced there."
        ),
        example_case="red2-my-invisible-column-drop",
        divergence=(
            "Warned limit — the column becomes visible to SELECT *, changing that "
            "query's result shape."
        ),
    ),
    "UNIQUE-1053": _R(
        construct="PostgreSQL UNIQUE ... NULLS NOT DISTINCT (→ other engines)",
        reason=(
            "Only PostgreSQL 15+ has a NULLS NOT DISTINCT unique-constraint modifier "
            "(NULLs compare equal, so only one NULL row is allowed); every other "
            "engine's UNIQUE always treats NULLs as distinct."
        ),
        example_case="pg-unique-nulls-notdistinct",
        divergence=(
            "Warned limit — degrades to a plain UNIQUE; multiple NULL rows become "
            "allowed on the target."
        ),
    ),
    "UNIQUE-1054": _R(
        construct="Cascading referential action on a self-referencing FK (→ T-SQL)",
        reason=(
            "T-SQL rejects a cascading action on a self-referencing foreign key "
            "outright (error 1785 at CREATE TABLE time) — an engine restriction, not a "
            "missing feature."
        ),
        example_case="my-self-fk",
        divergence=(
            "Warned limit — downgraded to ON DELETE NO ACTION; emulate the cascade "
            "with an AFTER trigger."
        ),
    ),
    "UNIQUE-1055": _R(
        construct="Foreign-key ON DELETE SET DEFAULT referential action (→ Oracle)",
        reason=(
            "Oracle foreign keys support only CASCADE/SET NULL/NO ACTION — SET DEFAULT "
            "raises ORA-03001 ('unimplemented feature') if shipped verbatim."
        ),
        example_case="red2-pg-fk-ondelete-setdefault-oracle",
        divergence=(
            "Warned limit — the action is dropped (FK reverts to NO ACTION); emulate "
            "with an AFTER DELETE trigger if required."
        ),
    ),
    "UNIQUE-1056": _R(
        construct=(
            "T-SQL In-Memory OLTP table storage option(s) (MEMORY_OPTIMIZED / "
            "DURABILITY) (→ other engines)"
        ),
        reason=(
            "No other engine has an in-memory table storage mode; the option is a "
            "physical-storage clause with no logical effect on query results."
        ),
        example_case="tsql-drop5-MEMORY_OPTIM",
        divergence=(
            "Faithful (storage-only) — the table becomes a regular disk-based table "
            "with the same logical content."
        ),
    ),
    "UNIQUE-1057": _R(
        construct="MySQL table-level default COLLATE/CHARSET clause (→ other engines)",
        reason=(
            "Same underlying gap as UNIQUE-1051 but table-scoped: collation names are "
            "engine-specific and unresolvable without a live database connection."
        ),
        example_case="mysql-drop5-utf8mb4",
        divergence="Warned limit — string columns use the target's default collation.",
    ),
    "UNIQUE-1058": _R(
        construct=(
            "A non-portable CREATE VIEW modifier (e.g. SCHEMABINDING, ALGORITHM=, "
            "DEFINER=, SQL SECURITY) with no native form on the target"
        ),
        reason=(
            "These modifiers are single-engine syntax with no equivalent option "
            "elsewhere (MATERIALIZED is handled separately, natively, on "
            "Oracle/PostgreSQL, so it never reaches this drop)."
        ),
        example_case="red2-pg-matview-oracle-falsewarn",
        divergence=(
            "Warned limit — the modifier is dropped; the view's query and columns are "
            "otherwise faithful."
        ),
    ),
    "UNIQUE-1059": _R(
        construct="DROP SEQUENCE (→ MySQL)",
        reason=(
            "MySQL has no sequence object at all (identity is expressed only via "
            "AUTO_INCREMENT columns), so there is nothing for a DROP SEQUENCE to "
            "target."
        ),
        example_case=(
            "tests/integration/test_oracle_mysql_tail.py::TestDropSequenceMySql::test_mysql_degrades_to_documented_carrier"
        ),
        divergence=(
            "Warned limit — degrades to a documented carrier; the original statement "
            "is preserved as a comment."
        ),
    ),
    "UNIQUE-1060": _R(
        construct="DROP TYPE (→ MySQL)",
        reason=(
            "MySQL has no user-defined type in any form (no CREATE TYPE/DOMAIN "
            "equivalent), so a DROP TYPE has nothing to target."
        ),
        example_case=(
            "tests/integration/test_pg_source_wave1.py::TestMysqlUserTypesDegrade::test_drop_type_degrades_mysql"
        ),
        divergence=(
            "Warned limit — degrades to a documented carrier; the original statement "
            "is preserved."
        ),
    ),
    "UNIQUE-1061": _R(
        construct="A DROP INDEX <name> with no owning table (→ T-SQL / MySQL)",
        reason=(
            "T-SQL and MySQL both require the owning table in DROP INDEX (index names "
            "are table-scoped there); Oracle/PostgreSQL index names are schema-scoped, "
            "so a source statement from either carries no table for the target to "
            "require."
        ),
        example_case=(
            "tests/integration/test_ddl_rename_dropindex.py::test_drop_index_without_table_never_ships_invalid"
        ),
        divergence=(
            "Warned limit — degrades to a documented carrier rather than shipping a "
            "syntactically incomplete DROP INDEX."
        ),
    ),
    "UNIQUE-1062": _R(
        construct=(
            "A schema-scoped DROP TRIGGER <name> with no owning table (→ PostgreSQL)"
        ),
        reason=(
            "PostgreSQL trigger names are per-table (DROP TRIGGER requires ON "
            "<table>); T-SQL/MySQL/Oracle trigger names are schema-scoped, so a source "
            "statement from any of them carries no table to supply."
        ),
        example_case=(
            "tests/integration/test_pg_source_wave1.py::TestDropTriggerOnTable::test_sourceless_on_degrades_to_pg"
        ),
        divergence=(
            "Warned limit — degrades to a documented carrier; the original statement "
            "is preserved."
        ),
    ),
    "UNIQUE-1063": _R(
        construct=(
            "A construct with no cross-engine mapping, kept as a documented carrier "
            "(e.g. T-SQL AT TIME ZONE, or the T-SQL CLR spatial '::' method-call "
            "operator)"
        ),
        reason=(
            "The generic degrade path for a value Unique recognizes but cannot compute "
            "on another engine — used e.g. for AT TIME ZONE (Oracle/MySQL have no such "
            "operator; PostgreSQL/T-SQL's own session-tz-dependent display differs) "
            "and T-SQL's geometry/geography '::' static-method call (no other engine "
            "has CLR types)."
        ),
        example_case="ts-at-time-zone",
        divergence=(
            "Warned limit — degrades to NULL + annotation; valid only on the source "
            "engine."
        ),
    ),
    "UNIQUE-1064": _R(
        construct="Oracle bare SESSIONTIMEZONE global (→ other engines)",
        reason=(
            "SESSIONTIMEZONE reports the connecting session's own UTC offset — a "
            "per-session value with no fixed cross-engine equivalent; the mapped "
            "expression reports the TARGET session's own zone in its native format "
            "instead."
        ),
        example_case="ora-tz-funcs",
        divergence=(
            "Warned limit — the value is session-dependent on the target too and may "
            "not match the source session's zone."
        ),
    ),
    "UNIQUE-1065": _R(
        construct="CAST(... AS TIME) and other Oracle-absent value types",
        reason=(
            "Oracle has no bare TIME (or plain INTERVAL) type, so the value is kept as "
            "text with a documented carrier rather than an invalid cast."
        ),
        example_case="my-cast-time",
        divergence="Warned limit — value kept as text.",
    ),
    "UNIQUE-1066": _R(
        construct="MySQL JSON type / CAST(... AS JSON)",
        reason=(
            "MySQL's JSON type has no faithful cross-engine equivalent — T-SQL has no "
            "JSON type at all, and canonical JSON spacing differs on PostgreSQL/Oracle "
            "— so the value is kept as text."
        ),
        example_case="my-cast-json",
        divergence="Warned limit — value kept as text.",
    ),
    "UNIQUE-1067": _R(
        construct="PostgreSQL geometric type (point/line/…) cast or column",
        reason=(
            "PostgreSQL's geometric types have no cross-engine model (MySQL's spatial "
            "POINT is a different WKB type), so the value is kept as text."
        ),
        example_case="pg-cast-point",
        divergence="Warned limit — value kept as text.",
    ),
    "UNIQUE-1068": _R(
        construct=(
            "A PostgreSQL numeric NaN/Infinity literal cast to a numeric type (→ MySQL "
            "/ T-SQL / Oracle)"
        ),
        reason=(
            "Only PostgreSQL's numeric type has a NaN/Infinity value; "
            "MySQL/T-SQL/Oracle DECIMAL/NUMBER silently collapse a 'NaN' cast to 0, so "
            "the special value has no faithful representation there."
        ),
        example_case="pg-nan-cmp",
        divergence=(
            "Warned limit — the carrier documents that the value cannot be reproduced "
            "numerically on the target."
        ),
    ),
    "UNIQUE-1069": _R(
        construct="MySQL UNSIGNED integer type / CAST(... AS UNSIGNED)",
        reason=(
            "No other engine has an UNSIGNED integer type; the value is mapped to a "
            "signed NUMERIC/NUMBER, so unsigned wraparound semantics are not "
            "preserved."
        ),
        example_case="my-cast-convert",
        divergence="Warned limit — unsigned wraparound not preserved.",
    ),
    "UNIQUE-1071": _R(
        construct=(
            "A scalar subquery serialized via T-SQL FOR XML/JSON (→ other engines)"
        ),
        reason=(
            "FOR XML/JSON row-serialization inside a (SELECT ... FOR XML/JSON) scalar "
            "subquery has no cross-engine equivalent; dropping only the clause would "
            "ship the multi-column rows raw into a scalar context (ORA-00913 'too many "
            "values'), so the whole scalar degrades instead."
        ),
        example_case="ts-for-xml",
        divergence="Warned limit — degrades to NULL + annotation.",
    ),
    "UNIQUE-1073": _R(
        construct=(
            "MySQL date arithmetic on a non-datetime string literal (e.g. "
            "DATE_ADD('not-a-date', INTERVAL ...))"
        ),
        reason=(
            "MySQL's own date-arithmetic functions yield NULL when the first argument "
            "doesn't parse as a date/time value; folding the literal at transpile time "
            "reproduces that NULL rather than emitting an invalid cast on another "
            "engine."
        ),
        example_case="my-timestr-plus",
        divergence=(
            "Warned limit — the value folds to NULL to match MySQL's own behaviour."
        ),
    ),
    "UNIQUE-1074": _R(
        construct="MySQL DATE - DATE subtraction",
        reason=(
            "MySQL's DATE - DATE operator is a numeric YYYYMMDD subtraction (e.g. "
            "2020-03-01 - 2020-01-01 = 200), not a day count; the meaningful day-count "
            "value (60, matching every other engine's date subtraction) is emitted "
            "instead."
        ),
        example_case="my-date-diff-minus",
        divergence=(
            "Warned limit — normalized to a day count rather than MySQL's own YYYYMMDD "
            "arithmetic result."
        ),
    ),
    "UNIQUE-1075": _R(
        construct="timestamp - timestamp subtraction (→ T-SQL / MySQL)",
        reason=(
            "PostgreSQL/Oracle timestamp subtraction yields an INTERVAL; T-SQL and "
            "MySQL have no interval value type, so the difference is computed as a "
            "SECOND count via DATEDIFF/TIMESTAMPDIFF instead."
        ),
        example_case=(
            "tests/integration/test_challenge.py::TestTimestampDifferenceDegrade::test_tsql_and_mysql_degrade_with_warning"
        ),
        divergence=(
            "Warned limit — a SECOND count replaces the source's INTERVAL value (same "
            "information, different type)."
        ),
    ),
    "UNIQUE-1076": _R(
        construct=(
            "LISTAGG(...) WITHIN GROUP (...) OVER (...) — windowed string aggregation "
            "(Oracle)"
        ),
        reason=(
            "T-SQL STRING_AGG and MySQL GROUP_CONCAT can never carry an OVER clause, "
            "and PostgreSQL rejects an ORDER-BY aggregate used as a window function — "
            "there is no running-string-aggregate form to target."
        ),
        example_case="ora-listagg-over",
        divergence="Warned limit — degrades to a NULL value plus annotation.",
    ),
    "UNIQUE-1077": _R(
        construct="GROUPS window frame (PostgreSQL / Oracle)",
        reason=(
            "T-SQL and MySQL implement only ROWS and RANGE frame units; a GROUPS frame "
            "spans whole peer groups, and no ROWS/RANGE combination reproduces that "
            "boundary when the ORDER BY key has ties."
        ),
        example_case="pg-window-groups-frame",
        divergence=(
            "Warned limit on T-SQL/MySQL — degrades to a NULL carrier; faithful on "
            "Oracle/PostgreSQL."
        ),
    ),
    "UNIQUE-1078": _R(
        construct=(
            "A window frame EXCLUDE clause (CURRENT ROW / GROUP / TIES) (→ T-SQL / "
            "MySQL)"
        ),
        reason=(
            "T-SQL and MySQL implement no EXCLUDE option on a window frame at all, and "
            "there is no faithful ROWS/RANGE rewrite that reproduces excluding "
            "specific peer rows from the frame."
        ),
        example_case="red2-pg-window-exclude-current",
        divergence=(
            "Warned limit on T-SQL/MySQL — degrades to a NULL carrier; faithful on "
            "PostgreSQL/Oracle, which support EXCLUDE natively."
        ),
    ),
    "UNIQUE-1080": _R(
        construct="Sequence CURRVAL — current value without advancing (→ T-SQL)",
        reason=(
            "T-SQL has NEXT VALUE FOR but no CURRVAL; there is no way to read a "
            "sequence's current value without advancing it."
        ),
        example_case="ora-seq-use",
        divergence="Warned limit — capture NEXT VALUE FOR in a variable instead.",
    ),
    "UNIQUE-1082": _R(
        construct="An empty-string result on Oracle ('' ≡ NULL)",
        reason=(
            "Oracle has no on-disk representation for an empty string distinct from "
            "NULL — an empty-string result becomes NULL — so a value that is '' on "
            "other engines cannot be reproduced there."
        ),
        example_case="pg-repeat-negative",
        divergence="Warned limit — the empty string surfaces as Oracle NULL.",
    ),
    "UNIQUE-1083": _R(
        construct="DATEPART(WEEKDAY, d) (T-SQL)",
        reason=(
            "DATEPART(WEEKDAY) depends on the session @@DATEFIRST setting, which "
            "Unique cannot observe at transpile time; the conversion assumes the T-SQL "
            "default (Sunday = 1)."
        ),
        example_case="reda-ts-datepart-weekday",
        divergence=(
            "Warned — correct under the default @@DATEFIRST = 7; a session that "
            "changed DATEFIRST will see a different result."
        ),
    ),
    "UNIQUE-1084": _R(
        construct=(
            "Oracle ROUND(date, fmt) — a date rounded to the nearest fmt boundary (→ "
            "other engines)"
        ),
        reason=(
            "No other engine has a nearest-boundary date-rounding function; only "
            "Oracle's own ROUND(date, fmt) computes this, so the general case (any "
            "fmt) has no cross-engine formula."
        ),
        example_case="red2-ora-round-date-fmt",
        divergence=(
            "Warned limit — degrades to a NULL carrier; not computed off Oracle."
        ),
    ),
    "UNIQUE-1085": _R(
        construct=(
            "Oracle TRUNC(date, fmt) with a format model that has no portable "
            "truncation (e.g. 'W' week-of-month)"
        ),
        reason=(
            "Most Oracle TRUNC format models map to a portable truncation unit (day, "
            "month, year, ISO week, ...), but a few (like 'W', week-of-the-month) have "
            "no equivalent boundary on any other engine."
        ),
        example_case="red2-ora-trunc-format-unmapped",
        divergence=(
            "Warned limit — degrades to a NULL carrier off Oracle; native TRUNC is "
            "kept on Oracle."
        ),
    ),
    "UNIQUE-1087": _R(
        construct=(
            "Oracle INSTR with a non-literal occurrence count or a non-literal "
            "backward (negative-start) search"
        ),
        reason=(
            "INSTR's occurrence/backward-search semantics fold to the engine-agnostic "
            "computed value only when every argument is a literal (at transpile time); "
            "a non-literal (column/expression) argument cannot be folded, and no other "
            "engine's positional-search function reproduces Oracle's "
            "occurrence/backward semantics directly."
        ),
        example_case=(
            "tests/integration/test_challenge.py::TestLiteralFolds::test_oracle_instr_nonliteral_degrades"
        ),
        divergence=(
            "Warned limit — degrades to a NULL carrier for the non-literal case; "
            "literal arguments still fold to the correct value."
        ),
    ),
    "UNIQUE-1088": _R(
        construct="MySQL UpdateXML() (→ other engines)",
        reason=(
            "UpdateXML has no cross-engine equivalent — PostgreSQL lacks it, and T-SQL "
            ".modify() / Oracle UPDATEXML differ in shape and semantics."
        ),
        example_case="my-xml-fns",
        divergence="Warned limit.",
    ),
    "UNIQUE-1089": _R(
        construct="COLLATION(x) — the collation name of a value (→ other engines)",
        reason=(
            "Collation names are engine-specific catalog identifiers (e.g. MySQL's "
            "utf8mb4_0900_ai_ci vs Oracle's NLS-based names) with no cross-engine "
            "mapping, even though the function itself exists on multiple engines."
        ),
        example_case="my-collation-fn",
        divergence=(
            "Warned limit — the source's engine-specific collation name is preserved "
            "but will not match the target's naming."
        ),
    ),
    "UNIQUE-1090": _R(
        construct="Oracle REGEXP_SUBSTR capture-group extraction (6th arg) (→ MySQL)",
        reason=(
            "MySQL's REGEXP_SUBSTR has no capture-group argument, so the sub-group "
            "extraction cannot be expressed; the portable (str, pat, pos, occ) subset "
            "is emitted."
        ),
        example_case="ora-regexp-group",
        divergence="Warned limit — capture-group extraction not reproduced.",
    ),
    "UNIQUE-1091": _R(
        construct="Oracle TRANSLATE(s, from, to) (→ MySQL)",
        reason=(
            "TRANSLATE is native on PostgreSQL/T-SQL, but MySQL has no TRANSLATE "
            "function; a nested-REPLACE emulation is order-dependent (each REPLACE can "
            "rematch a previous substitution's output) and is not equivalent to "
            "TRANSLATE's simultaneous single-pass character mapping."
        ),
        example_case="ora-translate3",
        divergence=(
            "Warned limit — degrades to a NULL carrier on MySQL; native and faithful "
            "on PostgreSQL/T-SQL."
        ),
    ),
    "UNIQUE-1092": _R(
        construct="SUBSTRING(x FROM POSIX-regex-pattern) (→ T-SQL)",
        reason=(
            "T-SQL has no POSIX regular-expression engine, so a POSIX-pattern "
            "SUBSTRING (native on Oracle REGEXP_SUBSTR / MySQL) has no equivalent "
            "there."
        ),
        example_case="pg-substring-regex",
        divergence=(
            "Warned limit — degrades to a NULL carrier on T-SQL; faithful on "
            "Oracle/MySQL via REGEXP_SUBSTR."
        ),
    ),
    "UNIQUE-1093": _R(
        construct=(
            "SUBSTRING(x FROM SIMILAR-TO-pattern FOR escape) — the SQL-standard regex "
            "form"
        ),
        reason=(
            "The SQL-standard SIMILAR TO pattern syntax uses different metacharacters "
            '(%, _, #"..."# capture markers) than POSIX regex, so no faithful '
            "cross-engine rewrite exists on engines whose regex functions expect POSIX "
            "syntax."
        ),
        example_case="pg-substring-escape",
        divergence="Warned limit — degrades to a NULL carrier.",
    ),
    "UNIQUE-1094": _R(
        construct="An empty-string function result on Oracle (e.g. SUBSTR yielding '')",
        reason=(
            "The same underlying limit as Oracle's NULL-equals-empty-string storage "
            "(UNIQUE-1082/1207), applied to a computed (not stored) empty-string "
            "result — Oracle collapses it to NULL at the point of computation too."
        ),
        example_case="my-fsubstr",
        divergence="Warned limit — the empty string surfaces as Oracle NULL.",
    ),
    "UNIQUE-1095": _R(
        construct=(
            "MySQL VALUES(col) used outside an INSERT ... ON DUPLICATE KEY UPDATE "
            "statement"
        ),
        reason=(
            "MySQL's VALUES(col) function only has meaning inside the ON DUPLICATE KEY "
            "UPDATE clause of the very INSERT it appears in (reading the row that "
            "would have been inserted); used elsewhere (e.g. inside a stored "
            "procedure's ordinary UPDATE) it is NULL on MySQL itself, so the "
            "transpiler reproduces that NULL."
        ),
        example_case=(
            "tests/integration/test_pg_source_wave1.py::TestWave223ValuesFnOutfile::test_values_fn_null_oracle"
        ),
        divergence="Faithful — matches MySQL's own out-of-context NULL behaviour.",
    ),
    "UNIQUE-1096": _R(
        construct="EXTRACT(EPOCH FROM interval) (PostgreSQL)",
        reason=(
            "T-SQL and MySQL have no interval value type, so the epoch (total seconds) "
            "of an interval value has no portable equivalent."
        ),
        example_case="pg-epoch",
        divergence=(
            "Warned limit — degrades to NULL + annotation (EPOCH FROM a timestamp is "
            "still computed)."
        ),
    ),
    "UNIQUE-1097": _R(
        construct="EXTRACT(MICROSECONDS FROM TIME) (→ Oracle)",
        reason=(
            "Oracle has no TIME type, so the microseconds field of a TIME value has no "
            "Oracle equivalent."
        ),
        example_case="pg-frac-seconds",
        divergence="Warned limit.",
    ),
    "UNIQUE-1098": _R(
        construct=(
            "PostgreSQL format() with a %I/%L specifier, a width, or a positional "
            "argument (→ other engines)"
        ),
        reason=(
            "Only the plain %s-only template has a portable rewrite (string "
            "concatenation); %I (quoted identifier) and %L (quoted literal) "
            "specifiers, width modifiers and positional (%1$s) arguments have no "
            "equivalent formatting primitive on other engines."
        ),
        example_case=(
            "tests/integration/test_challenge.py::TestFormatFunc::test_complex_spec_degrades"
        ),
        divergence=(
            "Warned limit — degrades to a NULL carrier; a %s-only template still "
            "rewrites faithfully."
        ),
    ),
    "UNIQUE-1099": _R(
        construct="PostgreSQL sha256()/sha512() (→ other engines)",
        reason=(
            "PostgreSQL's sha256/sha512 return a bytea digest, while every other "
            "engine's equivalent hash function returns a hex-encoded string — the "
            "underlying digest is identical, but the representation differs and cannot "
            "be reconciled without an explicit encode() the source SQL doesn't have."
        ),
        example_case="pg-hash-fns",
        divergence=(
            "Warned limit — degrades to a NULL carrier; md5() and other hash functions "
            "with matching representations still map faithfully."
        ),
    ),
    "UNIQUE-1100": _R(
        construct="MySQL CHAR(n) as a numeric-to-byte-string function",
        reason=(
            "MySQL's CHAR(n) returns a multi-byte byte string (CHAR(256) = the 2-byte "
            "string 0x0100), not a single Unicode code point like CHR/NCHAR, so the "
            "two cannot be equated."
        ),
        example_case="my-char-256",
        divergence=(
            "Warned limit — carrier flags the byte-string vs code-point difference."
        ),
    ),
    "UNIQUE-1103": _R(
        construct="SELECT ... FOR SHARE — a shared row lock (→ Oracle)",
        reason=(
            "Oracle SELECT locking is FOR UPDATE (exclusive) only — it has no "
            "shared-row-lock mode — so the shared lock cannot be reproduced."
        ),
        example_case="my-for-share",
        divergence="Warned limit — the shared lock is dropped.",
    ),
    "UNIQUE-1104": _R(
        construct="Oracle FOR UPDATE WAIT <n> — a bounded lock wait",
        reason=(
            "PostgreSQL/MySQL offer only FOR UPDATE / NOWAIT / SKIP LOCKED, with no "
            "bounded-wait timeout, so the WAIT <n> bound has no equivalent."
        ),
        example_case="ora-forupdate-wait",
        divergence="Warned limit — it blocks with the target's default behavior.",
    ),
    "UNIQUE-1137": _R(
        construct="T-SQL OUTPUT ... INTO <table> redirect (→ PostgreSQL)",
        reason=(
            "PostgreSQL's RETURNING only returns a result set to the caller; it has no "
            "INTO <table> redirect form, so the redirect cannot be expressed in a "
            "plain INSERT."
        ),
        example_case="reda-ts-output-into",
        divergence=(
            "Warned limit — the INTO redirect is dropped; the base DML and plain "
            "RETURNING are faithful."
        ),
    ),
    "UNIQUE-1139": _R(
        construct="A top-level OUTPUT / RETURNING result set (→ Oracle)",
        reason=(
            "Oracle's RETURNING is PL/SQL-only — it must target INTO bind variables "
            "and cannot stand alone in a plain SQL statement (ORA-63809) — so a "
            "standalone OUTPUT/RETURNING has no Oracle equivalent."
        ),
        example_case="reda-ts-output-into",
        divergence=(
            "Warned limit — the DML runs; the returned result set is documented, not "
            "produced."
        ),
    ),
    "UNIQUE-1148": _R(
        construct="Foreign-key ON UPDATE referential action (→ Oracle)",
        reason=(
            "Oracle foreign keys support only ON DELETE CASCADE / SET NULL — there is "
            "no ON UPDATE referential action (ORA-00905)."
        ),
        example_case="reda-ts-fk-on-update",
        divergence=(
            "Warned limit — ON UPDATE is dropped; reproduce it with a trigger if "
            "needed."
        ),
    ),
    "UNIQUE-1151": _R(
        construct=(
            "A source-engine built-in with no form in the target's catalog (e.g. "
            "SOUNDEX → PostgreSQL)"
        ),
        reason=(
            "A call that is a built-in of the source engine (clearly meant to run, not "
            "a user object) but absent from the target's catalog would be rejected "
            "outright, so the whole statement degrades rather than shipping an invalid "
            "call — the general unmapped-built-in gate."
        ),
        example_case="ora-soundex",
        divergence=(
            "Warned limit — the statement is preserved as a carrier and the failing "
            "built-in is named."
        ),
    ),
    "UNIQUE-1152": _R(
        construct="Oracle %TYPE / %ROWTYPE column-type reference (without --db-url)",
        reason=(
            "Only Oracle supports %TYPE/%ROWTYPE; resolving the real column type needs "
            "a live catalog lookup (ALL_TAB_COLUMNS) unavailable without a DB "
            "connection, so a permissive carrier type is emitted with the original "
            "reference preserved for a faithful round-trip back to Oracle."
        ),
        example_case=(
            "tests/integration/test_procedural.py::test_type_reference_documented_then_restored"
        ),
        divergence=(
            "Warned limit without --db-url (carrier type may not match exactly); "
            "faithful with --db-url or on an Oracle→Oracle round-trip."
        ),
    ),
    "UNIQUE-1153": _R(
        construct=(
            "PostgreSQL trigger function (CREATE FUNCTION ... RETURNS TRIGGER) (→ "
            "MySQL)"
        ),
        reason=(
            "MySQL has no trigger functions — a trigger's body belongs directly to "
            "CREATE TRIGGER, not to a separately-callable RETURNS TRIGGER function — "
            "so the PL/pgSQL function shape has nothing to bind to."
        ),
        example_case=(
            "tests/integration/test_triggers.py::TestPostgresTriggerToMySQL::test_trigger_function_degrades_with_warning"
        ),
        divergence=(
            "Warned limit — the non-portable translation is preserved commented out "
            "for a manual rewrite."
        ),
    ),
    "UNIQUE-1154": _R(
        construct=(
            "T-SQL inline table-valued function (CREATE FUNCTION ... RETURNS TABLE AS "
            "RETURN (...))"
        ),
        reason=(
            "Neither MySQL nor PostgreSQL has an inline (single-statement, "
            "substituted-at-call-site) table-valued function form; both would need a "
            "full multi-statement function/procedure rewritten by hand."
        ),
        example_case=(
            "tests/integration/test_procedural.py::TestInlineTableValuedFunction::test_mysql_documents_and_comments_out"
        ),
        divergence=(
            "Warned limit — documented and commented out rather than emitted as "
            "invalid RETURNS TABLE."
        ),
    ),
    "UNIQUE-1155": _R(
        construct=(
            "A trigger body that reads the T-SQL inserted/deleted pseudo-tables in a "
            "set-based way (FROM/JOIN inserted|deleted) the target cannot express"
        ),
        reason=(
            "Once the set-based pseudo-table read degrades to a per-statement carrier "
            "(UNIQUE-1201), the surrounding trigger no longer has a runnable body — "
            "shipping it partially would execute a half-empty trigger per row, so the "
            "whole trigger is preserved commented out instead."
        ),
        example_case=(
            "tests/integration/test_triggers.py::TestSetBasedTriggerRewrite::test_pure_set_based_to_mysql_documented"
        ),
        divergence="Warned limit — the whole trigger becomes a documented carrier.",
    ),
    "UNIQUE-1156": _R(
        construct="Oracle COMPOUND TRIGGER (→ MySQL)",
        reason=(
            "A compound trigger's BEFORE/AFTER EACH ROW + AFTER STATEMENT sections "
            "collect affected rows into a PL/SQL collection and re-aggregate them "
            "statement-wide; MySQL has no equivalent mechanism (no transition tables, "
            "no multi-timing trigger sections) to mechanically rewrite that "
            "accumulation into."
        ),
        example_case=(
            "tests/integration/test_triggers.py::TestOracleCompoundTrigger::test_degrades_to_carrier_mysql"
        ),
        divergence=(
            "Warned limit — documented for a manual rewrite (a MySQL row-level trigger "
            "that re-reads the table)."
        ),
    ),
    "UNIQUE-1157": _R(
        construct=(
            "A PostgreSQL statement-level trigger delegating its body to a trigger "
            "function via EXECUTE FUNCTION (→ MySQL)"
        ),
        reason=(
            "MySQL has neither trigger functions nor transition tables, so a "
            "statement-level trigger that references its bound function's "
            "transition-table reads has nothing to bind to."
        ),
        example_case=(
            "tests/integration/test_triggers.py::TestPostgresTriggerToMySQL::test_trigger_binding_degrades_with_warning"
        ),
        divergence="Warned limit — documented carrier.",
    ),
    "UNIQUE-1158": _R(
        construct="A PostgreSQL FOREACH ... IN ARRAY LOOP (→ other engines)",
        reason=(
            "The FOREACH-over-array loop is inherently array-typed, and no other "
            "engine has an array column/variable type at all, so there is no array to "
            "iterate over on the target."
        ),
        example_case=(
            "tests/integration/test_pg_source_wave1.py::TestForeachArrayLoop::test_foreach_degrades_off_pg"
        ),
        divergence="Warned limit — statement preserved as a comment.",
    ),
    "UNIQUE-1159": _R(
        construct=(
            "An Oracle PL/SQL PRAGMA declaration (e.g. AUTONOMOUS_TRANSACTION) (→ "
            "other engines)"
        ),
        reason=(
            "A PRAGMA is a compiler directive to the Oracle PL/SQL engine itself (no "
            "runtime SQL effect); no other engine's procedural language has an "
            "equivalent compiler-directive mechanism."
        ),
        example_case=(
            "tests/integration/test_oracle_mysql_tail.py::TestPragmaAutonomousTransaction::test_off_oracle_pragma_never_ships_executable"
        ),
        divergence=(
            "Warned limit — dropped; the surrounding declarations and body still "
            "transpile."
        ),
    ),
    "UNIQUE-1160": _R(
        construct=(
            "A standalone (anonymous) PL/SQL block at the top level, with no enclosing "
            "CREATE PROCEDURE/FUNCTION"
        ),
        reason=(
            "No other engine has a top-level anonymous executable block outside a "
            "routine definition (T-SQL's nearest analog, a batch, has different "
            "scoping/semantics), so a mechanical rewrite risks silently changing what "
            "runs when."
        ),
        example_case=(
            "tests/integration/test_procedural.py::TestOracleCatalogDropBlock::test_degrades_on_postgresql"
        ),
        divergence=(
            "Warned limit — preserved as a documented comment below the carrier."
        ),
    ),
    "UNIQUE-1161": _R(
        construct="T-SQL sp_executesql parameter declarations/bindings (→ MySQL)",
        reason=(
            "MySQL's PREPARE/EXECUTE has no inline parameter-declaration + binding "
            "form matching sp_executesql's @params list, so the declarations/bindings "
            "are dropped and must be passed via EXECUTE ... USING."
        ),
        example_case="ts-sp-executesql",
        divergence="Warned limit — parameter bindings dropped.",
    ),
    "UNIQUE-1162": _R(
        construct=(
            "A PL/pgSQL RAISE NOTICE inside a function that returns a scalar value (→ "
            "MySQL)"
        ),
        reason=(
            "A bare SELECT (MySQL's own notice-style output channel) is invalid inside "
            "a MySQL FUNCTION — functions cannot return an extra result set (error "
            "1415) — so the message is diverted into a session variable instead."
        ),
        example_case=(
            "tests/integration/test_pg_source_wave1.py::TestMysqlFunctionNotice::test_notice_in_function_diverts"
        ),
        divergence=(
            "Warned limit — the message lands in @uq_notice, not printed inline; "
            "procedures (which can SELECT) keep the visible channel."
        ),
    ),
    "UNIQUE-1163": _R(
        construct="T-SQL RAISERROR/THROW with severity/state arguments (→ MySQL)",
        reason=(
            "MySQL's SIGNAL statement has no severity/state argument slots matching "
            "RAISERROR's — only the message transfers, so the extra arguments are "
            "dropped and named in the carrier rather than silently discarded."
        ),
        example_case="red2-ts-raiserror-format-arg-drop",
        divergence="Warned limit — severity/state args dropped, listed in the carrier.",
    ),
    "UNIQUE-1164": _R(
        construct="BEGIN TRANSACTION (→ Oracle)",
        reason=(
            "Oracle has no explicit transaction-start statement — a transaction begins "
            "implicitly with the first DML statement — so an explicit BEGIN "
            "TRANSACTION has nothing to translate to."
        ),
        example_case=(
            "tests/integration/test_procedural.py::TestTransactionControl::test_begin_transaction_documented_for_oracle_pg"
        ),
        divergence=(
            "Faithful (no-op drop) — Oracle's implicit transaction start reproduces "
            "the same behaviour."
        ),
    ),
    "UNIQUE-1165": _R(
        construct=(
            "T-SQL WAITFOR TIME '...' — wait until an absolute clock time (→ MySQL)"
        ),
        reason=(
            "Every target's sleep primitive (DBMS_SESSION.SLEEP, pg_sleep, MySQL "
            "SLEEP) takes a relative duration, not an absolute wall-clock time to wait "
            "until; WAITFOR DELAY (relative) maps cleanly, but WAITFOR TIME has no "
            "relative-duration equivalent to compute without the current time at run "
            "time."
        ),
        example_case=(
            "tests/integration/test_procedural.py::TestWaitFor::test_time_documented"
        ),
        divergence="Warned limit — documented, not computed.",
    ),
    "UNIQUE-1166": _R(
        construct=(
            "A non-forward cursor FETCH (FETCH LAST/PRIOR/FIRST/ABSOLUTE/RELATIVE) "
            "from a scrollable cursor (→ Oracle)"
        ),
        reason=(
            "Oracle cursors, like every other target's, are forward-only (only FETCH "
            "NEXT); a non-forward fetch direction has no operation to translate to."
        ),
        example_case=(
            "tests/integration/test_pg_source_wave1.py::TestFetchDirections::test_fetch_last_degrades_oracle"
        ),
        divergence=(
            "Warned limit — the scroll fetch degrades to a carrier; the surrounding "
            "OPEN/FETCH NEXT/CLOSE still compile."
        ),
    ),
    "UNIQUE-1167": _R(
        construct="A cursor FETCH with no INTO target-variable list",
        reason=(
            "PostgreSQL/Oracle/MySQL all require FETCH to specify where the fetched "
            "row's columns go; a source FETCH that discards the row (no INTO) has "
            "nothing for the target's FETCH to bind, so emitting 'FETCH c INTO ;' "
            "would be invalid syntax."
        ),
        example_case=(
            "tests/integration/test_procedural.py::TestUnsupportedCursorConstructsAreValidCarriers::test_fetch_without_into_is_documented_not_empty"
        ),
        divergence=(
            "Warned limit — documented as a comment rather than shipping an incomplete "
            "FETCH."
        ),
    ),
    "UNIQUE-1168": _R(
        construct="GOTO <label> (→ PostgreSQL)",
        reason=(
            "PL/pgSQL has no GOTO statement (or any unconditional-jump control-flow "
            "form), so a source GOTO has no operation to translate to."
        ),
        example_case="red3-ts-goto-label-proc",
        divergence=(
            "Warned limit — dropped; control flow is not replicated (T-SQL/Oracle keep "
            "native GOTO)."
        ),
    ),
    "UNIQUE-1169": _R(
        construct="A GOTO target label (→ PostgreSQL)",
        reason=(
            "Without a GOTO to jump to it, and with PL/pgSQL having no label/GOTO "
            "mechanism at all, the label marker itself has nothing to bind to on the "
            "target."
        ),
        example_case="red3-ts-goto-label-proc",
        divergence="Warned limit — dropped alongside its GOTO.",
    ),
    "UNIQUE-1171": _R(
        construct=(
            "A whole procedural construct the transformer recognizes but cannot map on "
            "the target (the shared transformer-degrade carrier)"
        ),
        reason=(
            "Shared carrier path for any transformer-level whole-unit degrade (an "
            "unsupported PL/SQL exception context in a T-SQL scalar function, a "
            "client-tool directive, ...); each specific reason is interpolated into "
            "the same carrier template rather than allocating one code per message."
        ),
        example_case="pg-named-exception",
        divergence="Warned limit — the construct is preserved as a documented comment.",
    ),
    "UNIQUE-1172": _R(
        construct="GOTO <label> (→ MySQL)",
        reason=(
            "MySQL has no GOTO statement either; the carrier additionally pairs the "
            "drop with a DO 0 no-op so an IF/loop body the GOTO occupied is never left "
            "syntactically empty (MySQL error 1064)."
        ),
        example_case="red3-ts-goto-label-proc",
        divergence="Warned limit — dropped; control flow not replicated.",
    ),
    "UNIQUE-1173": _R(
        construct="A GOTO target label (→ MySQL)",
        reason=(
            "Same underlying gap as UNIQUE-1169 but for MySQL, which also has no "
            "label/GOTO mechanism."
        ),
        example_case="red3-ts-goto-label-proc",
        divergence="Warned limit — dropped alongside its GOTO.",
    ),
    "UNIQUE-1174": _R(
        construct=(
            "An Oracle/PostgreSQL implicit cursor FOR loop whose query's column list "
            "Unique cannot resolve (e.g. SELECT * or an unresolvable projection) (→ "
            "T-SQL / MySQL)"
        ),
        reason=(
            "The faithful expansion needs one FETCH-target variable per selected "
            "column; when the column list isn't statically resolvable (a bare SELECT * "
            "with no visible schema, or a referenced record field the visible list "
            "doesn't expose), Unique cannot generate that variable list, so it emits a "
            "documented scaffold for the developer to complete instead of guessing."
        ),
        example_case=(
            "tests/integration/test_cursor_for_loop_tsql.py::test_unresolvable_select_star_keeps_documented_scaffold"
        ),
        divergence=(
            "Warned limit — the FETCH INTO target list is left as a placeholder "
            "comment for manual completion; OPEN/CLOSE and the loop shape are still "
            "emitted."
        ),
    ),
    "UNIQUE-1175": _R(
        construct=(
            "An Oracle/PostgreSQL implicit cursor FOR loop with a resolvable column "
            "list (→ MySQL)"
        ),
        reason=(
            "The columns are resolvable, so the loop expands completely (one variable "
            "per column, positional FETCH), but without a --db-url connection Unique "
            "does not know each column's real type, so every loop variable is declared "
            "as the permissive TEXT type."
        ),
        example_case=(
            "tests/integration/test_oracle_mysql_tail.py::TestMySqlCursorForLoopExpansion::test_named_cursor_drives_directly"
        ),
        divergence=(
            "Warned limit without --db-url (loop variables are TEXT, not the real "
            "column types); the loop's control flow and FETCH are otherwise faithful."
        ),
    ),
    "UNIQUE-1176": _R(
        construct="A T-SQL INSTEAD OF trigger (→ MySQL)",
        reason=(
            "MySQL has no INSTEAD OF trigger timing at all (only BEFORE/AFTER); the "
            "closest emulation is a BEFORE trigger, which runs in addition to (not "
            "instead of) the triggering statement, so the substitution semantics are "
            "not reproduced automatically."
        ),
        example_case=(
            "tests/integration/test_triggers.py::TestInsteadOfTrigger::test_instead_of_documented_on_mysql"
        ),
        divergence=(
            "Warned limit — emitted as BEFORE for review, with the original INSTEAD OF "
            "timing documented."
        ),
    ),
    "UNIQUE-1177": _R(
        construct="A T-SQL procedure-level RETURN <value> (a status code) (→ MySQL)",
        reason=(
            "MySQL stored procedures have no return value (only functions do); a "
            "procedure's RETURN <expr> is rewritten to a bare LEAVE (exiting the "
            "procedure), and the discarded value is named in the carrier rather than "
            "silently dropped."
        ),
        example_case=(
            "tests/integration/test_procedural.py::TestReturnValueInProcedure::test_return_value_in_procedure_becomes_leave"
        ),
        divergence=(
            "Warned limit — the status-code value is documented, not returned; a "
            "FUNCTION's RETURN <value> is unaffected and kept."
        ),
    ),
    "UNIQUE-1178": _R(
        construct=(
            "A dynamic-SQL EXECUTE ... INTO <var> whose target string is not a "
            "compile-time-resolvable SELECT INTO @session-variable form (→ MySQL)"
        ),
        reason=(
            "MySQL's PREPARE/EXECUTE workflow can only capture a dynamic result into a "
            "variable if the dynamic SQL text itself is rewritten to 'SELECT ... INTO "
            "@var', which Unique cannot reliably synthesize for an arbitrary dynamic "
            "string built at runtime."
        ),
        example_case="pg-dyn-count",
        divergence=(
            "Warned limit — documented; the dynamic string must be rewritten by hand "
            "to select into a MySQL session variable."
        ),
    ),
    "UNIQUE-1179": _R(
        construct=(
            "A trigger body that reads the T-SQL inserted/deleted pseudo-tables in a "
            "set-based way (→ Oracle)"
        ),
        reason=(
            "Oracle has no transition tables at all (a compound trigger's "
            "PL/SQL-collection accumulation is the closest analog, and is not a "
            "mechanical rewrite of an arbitrary set-based DML statement), so the "
            "set-based read cannot be expressed."
        ),
        example_case=(
            "tests/integration/test_triggers.py::TestSetBasedTriggerRewrite::test_pure_set_based_to_oracle_documented"
        ),
        divergence=(
            "Warned limit — the whole trigger degrades to a documented carrier for a "
            "manual compound-trigger rewrite (the Oracle-specific sibling of "
            "UNIQUE-1155)."
        ),
    ),
    "UNIQUE-1180": _R(
        construct="T-SQL sp_executesql named parameters (→ Oracle)",
        reason=(
            "Oracle EXECUTE IMMEDIATE ... USING binds positionally, so the named "
            "@params of sp_executesql must be re-spelled inside the dynamic string as "
            ":1, :2, …."
        ),
        example_case="ts-sp-executesql",
        divergence="Warned limit — placeholders must be renumbered positionally.",
    ),
    "UNIQUE-1182": _R(
        construct=(
            "A T-SQL INSTEAD OF trigger on a base TABLE, not a view (→ PostgreSQL)"
        ),
        reason=(
            "PostgreSQL restricts INSTEAD OF triggers to views only; on a table, the "
            "equivalent behaviour (substituting the trigger's own logic for the "
            "triggering statement) is a BEFORE row trigger that returns NULL, "
            "suppressing the original operation — a different trigger-timing model "
            "requiring a pg_trigger_depth() guard so the trigger's own DML still "
            "executes."
        ),
        example_case="ts-instead-of-insert",
        divergence=(
            "Faithful — the rewritten BEFORE-trigger-with-guard form reproduces the "
            "substitution semantics (live-verified insert-exactly-once)."
        ),
    ),
    "UNIQUE-1183": _R(
        construct="BEGIN TRANSACTION (→ PostgreSQL)",
        reason=(
            "A PL/pgSQL routine already runs inside the caller's transaction (or "
            "manages its own via nested procedure-call semantics) — there is no "
            "explicit statement to start one, so an explicit BEGIN TRANSACTION has "
            "nothing to translate to."
        ),
        example_case=(
            "tests/integration/test_procedural.py::TestTransactionControl::test_begin_transaction_documented_for_oracle_pg"
        ),
        divergence=(
            "Faithful (no-op drop) — PostgreSQL's implicit routine-transaction "
            "handling reproduces the same behaviour."
        ),
    ),
    "UNIQUE-1184": _R(
        construct="SAVEPOINT (→ PostgreSQL)",
        reason=(
            "PL/pgSQL has no explicit SAVEPOINT statement; the equivalent behaviour (a "
            "partial rollback boundary) comes from wrapping statements in a BEGIN ... "
            "EXCEPTION block, which rolls back to its own start on error."
        ),
        example_case=(
            "tests/integration/test_procedural.py::TestTransactionControl::test_rollback_to_savepoint"
        ),
        divergence=(
            "Warned limit — dropped; wrap the guarded statements in a "
            "BEGIN...EXCEPTION block to reproduce the rollback boundary (Oracle keeps "
            "native SAVEPOINT)."
        ),
    ),
    "UNIQUE-1185": _R(
        construct="ROLLBACK TO SAVEPOINT <name> (→ PostgreSQL)",
        reason=(
            "Same underlying gap as UNIQUE-1184 — PL/pgSQL has no explicit savepoints "
            "to roll back to; the enclosing BEGIN...EXCEPTION block already rolls back "
            "automatically on error."
        ),
        example_case=(
            "tests/integration/test_procedural.py::TestTransactionControl::test_rollback_to_savepoint"
        ),
        divergence="Warned limit — dropped alongside its SAVEPOINT.",
    ),
    "UNIQUE-1186": _R(
        construct="SELECT * INTO <multiple variables> (→ other engines)",
        reason=(
            "Expanding SELECT * into a positional variable-assignment list requires "
            "knowing the source's column list, which a bare '*' does not carry without "
            "schema access; the same is true across engines, so the statement cannot "
            "be mechanically completed."
        ),
        example_case=(
            "tests/integration/test_pg_source_wave1.py::TestWave233StarIntoMultipleVars::test_star_into_multi_degrades"
        ),
        divergence=(
            "Warned limit — documented; supply the column list explicitly to fix."
        ),
    ),
    "UNIQUE-1187": _R(
        construct=(
            "An Oracle/PostgreSQL implicit cursor FOR loop with a resolvable column "
            "list (→ T-SQL)"
        ),
        reason=(
            "The T-SQL sibling of UNIQUE-1175 — the columns are resolvable and the "
            "loop expands completely (one @variable per column, positional FETCH "
            "NEXT), but without --db-url metadata each loop variable is declared as "
            "the permissive NVARCHAR(4000) rather than the column's real type."
        ),
        example_case=(
            "tests/integration/test_cursor_for_loop_tsql.py::test_named_cursor_loop_expands_completely"
        ),
        divergence=(
            "Warned limit without --db-url (loop variables are NVARCHAR(4000)); the "
            "loop's control flow and FETCH are otherwise faithful and complete."
        ),
    ),
    "UNIQUE-1190": _R(
        construct=(
            "Oracle EXECUTE IMMEDIATE ... USING <binds> with no INTO clause (→ T-SQL)"
        ),
        reason=(
            "T-SQL's sp_executesql takes named parameters (@p1, @p2, ...) bound by "
            "name, while Oracle's USING binds positionally against :1, :2, ... "
            "placeholders inside the dynamic string; the rewrite emits a parameterized "
            "sp_executesql call, but the placeholders inside the dynamic-SQL text "
            "itself must still be renumbered by hand to match."
        ),
        example_case=(
            "tests/integration/test_procedural.py::TestDynamicSQL::test_oracle_to_tsql_uses_sp_executesql"
        ),
        divergence=(
            "Warned limit — placeholders inside the dynamic string need manual "
            "renumbering to @p1, @p2, ...; the call itself is valid and parameterized."
        ),
    ),
    "UNIQUE-1192": _R(
        construct=(
            "Oracle's implicit-cursor SQL%ROWCOUNT (rows the last DML MATCHED) (→ "
            "MySQL)"
        ),
        reason=(
            "MySQL's closest equivalent, ROW_COUNT(), counts rows actually CHANGED by "
            "the last DML, not rows matched by its WHERE clause — for an UPDATE that "
            "matches a row but assigns it its current value, Oracle's matched-count "
            "and MySQL's changed-count diverge; the mapping is kept (still the closest "
            "fit) but annotated rather than shipped silently."
        ),
        example_case=(
            "tests/integration/test_challenge.py::TestRowcountDivergenceAnnotation::test_mysql_target_annotates_and_warns"
        ),
        divergence=(
            "Warned limit — the value may differ from the source when a matched row's "
            "UPDATE is a no-op (T-SQL's @@ROWCOUNT is matched-rows too and needs no "
            "such note)."
        ),
    ),
    "UNIQUE-1193": _R(
        construct=(
            "A source-only procedural statement with no target concept at all (e.g. "
            "T-SQL SET IDENTITY_INSERT/SET NOCOUNT inside a routine) (→ other engines)"
        ),
        reason=(
            "The statement configures a source-engine-only session/compiler behaviour "
            "with no corresponding concept on the target at all (not merely a missing "
            "spelling), so the shared carrier documents it as '{source}-only' rather "
            "than attempting any target-side equivalent."
        ),
        example_case=(
            "tests/integration/test_procedural.py::TestUniqueCommentRestore::test_identity_insert_documented_then_restored"
        ),
        divergence=(
            "Warned limit — dropped; documented as source-engine-only, and restored "
            "verbatim on a round trip back to the source engine."
        ),
    ),
    "UNIQUE-1194": _R(
        construct=(
            "A T-SQL global (@@ERROR/@@TRANCOUNT/@@CURSOR_ROWS/SQL%ROWCOUNT-family) "
            "used inside an expression position (e.g. an IF condition) with no target "
            "equivalent"
        ),
        reason=(
            "These globals have no faithful non-source equivalent, and unlike a "
            "top-level statement, an expression position cannot simply be dropped — a "
            "value-shaped placeholder is required so the surrounding expression stays "
            "syntactically valid."
        ),
        example_case=(
            "tests/integration/test_procedural.py::TestErrorGlobalInCondition::test_error_in_if_mysql"
        ),
        divergence=(
            "Warned limit — a neutral literal (0) replaces the global so the "
            "expression parses; the specific behaviour it gated is lost."
        ),
    ),
    "UNIQUE-1195": _R(
        construct=(
            "A PostgreSQL trigger function's body, when its trigger delegates to it "
            "via EXECUTE FUNCTION (→ T-SQL)"
        ),
        reason=(
            "T-SQL has no separately-callable trigger function — a trigger's logic "
            "must live inline in CREATE TRIGGER — so the delegating function's body is "
            "inlined directly into the T-SQL trigger, with the PG-only "
            "pg_trigger_depth() guard and RETURN NULL protocol dropped (T-SQL triggers "
            "have no such re-entrancy-guard convention)."
        ),
        example_case=(
            "tests/integration/test_triggers.py::TestPgDelegatingTriggerToTSql::test_inlined_into_tsql_trigger"
        ),
        divergence=(
            "Faithful — the inlined trigger reproduces the same DML; live-compiled "
            "valid."
        ),
    ),
    "UNIQUE-1196": _R(
        construct="A T-SQL table variable (DECLARE @var TABLE (...)) (→ MySQL)",
        reason=(
            "MySQL has no table-variable DECLARE form; the closest equivalent is a "
            "CREATE TEMPORARY TABLE statement inside the routine body, which the "
            "carrier documents as the table variable's replacement."
        ),
        example_case=(
            "tests/integration/test_procedural.py::TestTableVariableToMySQL::test_table_variable_becomes_temp_table"
        ),
        divergence=(
            "Faithful — a temporary table reproduces the same session-scoped, "
            "statement-usable storage; the carrier is purely documentary."
        ),
    ),
    "UNIQUE-1197": _R(
        construct=(
            "A source-only SET option with no target equivalent, inside a routine body "
            "(e.g. MySQL SET SQL_MODE)"
        ),
        reason=(
            "The option configures source-engine-only parsing/execution behaviour "
            "(MySQL's SQL_MODE flags, for instance) that no other engine's session "
            "model has a matching concept for."
        ),
        example_case=(
            "tests/integration/test_pg_source_wave1.py::TestWave162AdddateSqlMode::test_set_sql_mode_carrier_tsql"
        ),
        divergence="Warned limit — dropped; documented as source-only.",
    ),
    "UNIQUE-1198": _R(
        construct=(
            "EXEC <T-SQL system procedure> as a standalone statement (e.g. EXEC "
            "sp_who) inside a routine body (→ other engines)"
        ),
        reason=(
            "T-SQL system procedures call into SQL Server's own catalog/admin "
            "machinery (the same class as UNIQUE-1211's top-level EXEC, here inside a "
            "routine); no other engine exposes the same operation through a callable "
            "procedure."
        ),
        example_case="ts-waitfor-exec",
        divergence=(
            "Warned limit — the call becomes a documented carrier; the administrative "
            "action must be performed via the target's own tooling."
        ),
    ),
    "UNIQUE-1200": _R(
        construct=(
            "An Oracle built-in package call (e.g. DBMS_SCHEDULER.CREATE_JOB) (→ other "
            "engines)"
        ),
        reason=(
            "Oracle's DBMS_*/UTL_* packages call into Oracle-specific server-side "
            "machinery (job scheduling, session control, ...) with no cross-engine "
            "equivalent; shipped raw, the call is a guaranteed runtime error off "
            "Oracle."
        ),
        example_case=(
            "tests/integration/test_trigger_predicates_scheduler.py::test_dbms_scheduler_degrades_to_carrier"
        ),
        divergence=(
            "Warned limit — the call becomes a documented carrier rather than an "
            "invalid raw call."
        ),
    ),
    "UNIQUE-1201": _R(
        construct=(
            "A trigger DML statement that reads the T-SQL inserted/deleted "
            "pseudo-tables in a set-based way (FROM inserted / JOIN deleted) (→ other "
            "engines, absent a transition-table rewrite)"
        ),
        reason=(
            "A set-based pseudo-table read has no row-level (NEW/OLD) equivalent; "
            "where the whole trigger can be rewritten with real transition tables "
            "(PostgreSQL statement-level triggers, Oracle compound triggers) the "
            "set-based DML is left as-is, but where it cannot (MySQL, or a mixed "
            "row+set trigger), the specific statement is documented instead of emitted "
            "referencing an undefined table."
        ),
        example_case=(
            "tests/integration/test_triggers.py::TestSetBasedTriggerRewrite::test_pure_set_based_to_mysql_documented"
        ),
        divergence=(
            "Warned limit — the statement is documented with per-target rewrite "
            "guidance rather than shipped referencing an undefined table."
        ),
    ),
    "UNIQUE-1202": _R(
        construct="A T-SQL table-valued function used in a FROM clause (→ MySQL)",
        reason=(
            "MySQL has no table-valued function mechanism (a function cannot appear as "
            "a FROM-clause row source); the statement is commented out rather than "
            "shipping an invalid function-in-FROM."
        ),
        example_case=(
            "tests/integration/test_procedural.py::TestTableValuedFunctionInFrom::test_user_tvf_in_from_commented"
        ),
        divergence=(
            "Warned limit — commented out for review (STRING_SPLIT, rewritten to the "
            "valid JSON_TABLE form, is unaffected)."
        ),
    ),
    "UNIQUE-1203": _R(
        construct=(
            "An Oracle cursor attribute the transformer does not recognize (e.g. "
            "c%BULK_ROWCOUNT) (→ other engines)"
        ),
        reason=(
            "Only a fixed, explicitly-mapped set of cursor attributes "
            "(%FOUND/%NOTFOUND/%ISOPEN/%ROWCOUNT) has a per-cursor state translation "
            "on T-SQL/MySQL; an attribute outside that set has no known target form, "
            "and — critically — must not fall through to the general expression "
            "parser, which would otherwise read 'c%attr' as 'c' modulo 'attr'."
        ),
        example_case=(
            "tests/integration/test_cursor_state_b7.py::TestUnknownAttributeWarns::test_unknown_attribute_warns_and_does_not_leak_modulo"
        ),
        divergence=(
            "Warned limit — degrades to a neutral 0 carrier rather than silently "
            "becoming modulo arithmetic."
        ),
    ),
    "UNIQUE-1205": _R(
        construct=(
            "A T-SQL #temp table declared with an explicit CREATE TABLE #name (...) (→ "
            "Oracle)"
        ),
        reason=(
            "Same underlying gap as UNIQUE-1196 but for a real temp table rather than "
            "a table variable — Oracle has no session-scoped #temp table; the CREATE "
            "is hoisted to a GLOBAL TEMPORARY TABLE before the routine (a CREATE "
            "cannot live inside PL/SQL), and the carrier documents the substitution."
        ),
        example_case=(
            "tests/integration/test_temp_table_in_procedure.py::TestOracle::test_hoists_global_temporary_table"
        ),
        divergence=(
            "Faithful — the hoisted GTT, cleared and repopulated per call, reproduces "
            "the same session-scoped storage; the carrier is purely documentary."
        ),
    ),
    "UNIQUE-1206": _R(
        construct=(
            "COMMIT/ROLLBACK inside a T-SQL TRY/CATCH block translated to a PL/pgSQL "
            "BEGIN...EXCEPTION block (→ PostgreSQL)"
        ),
        reason=(
            "PL/pgSQL's exception-guarded block is itself a subtransaction "
            "(savepoint); issuing an explicit COMMIT/ROLLBACK inside one is a runtime "
            "error ('cannot commit while a subtransaction is active') rather than a "
            "parse-time gap, and the subtransaction already provides the same "
            "rollback-on-error/commit-with-caller semantics T-SQL's TRY/CATCH "
            "expressed explicitly."
        ),
        example_case=(
            "tests/integration/test_procedural.py::TestTopLevelTryCatch::test_begin_transaction_prefix_lowers_on_postgresql"
        ),
        divergence=(
            "Faithful (the subtransaction reproduces the same net transactional "
            "behaviour) with the explicit COMMIT/ROLLBACK dropped and documented "
            "rather than shipped as a guaranteed runtime error."
        ),
    ),
    "UNIQUE-1207": _R(
        construct=(
            "Inherent value divergence: default-collation comparison, Oracle '' ≡ "
            "NULL, or byte-vs-char length (approved limit)"
        ),
        reason=(
            "These divergences (case/accent/trailing-space comparison under the "
            "default collation, Oracle's '' ≡ NULL, LENGTH byte-vs-char) are "
            "per-column/connection properties the SQL text carries no trace of; no "
            "statement-level rewrite bridges them without column-collation/encoding "
            "visibility Unique does not have."
        ),
        example_case="ora-empty-null",
        divergence=(
            "Approved documented limit, warned — the value or row count may differ."
        ),
    ),
    "UNIQUE-1211": _R(
        construct="EXEC sp_<name> — a T-SQL system procedure (→ other engines)",
        reason=(
            "T-SQL system procedures call SQL Server's own catalog/admin machinery; no "
            "other engine exposes the same operation through a callable procedure with "
            "the same name or signature."
        ),
        example_case="reda-ts-exec-swallow-next",
        divergence=(
            "Warned limit — the call becomes a carrier; the administrative action must "
            "be performed via the target's own tooling."
        ),
    ),
    "UNIQUE-1212": _R(
        construct=(
            "A standalone INSERT/UPDATE/DELETE ... OUTPUT result set (→ Oracle / "
            "MySQL)"
        ),
        reason=(
            "Neither Oracle (RETURNING is PL/SQL-only, ORA-63809) nor MySQL has a "
            "standalone data-modifying-statement result set, so the OUTPUT rows cannot "
            "be returned to the caller."
        ),
        example_case="ts-insert-output",
        divergence=(
            "Warned limit — the DML effect is faithful; the returned result set is "
            "documented, not produced."
        ),
    ),
    "UNIQUE-1231": _R(
        construct=(
            "Any ProceduralTransformer-level warning with no more specific UNIQUE-NNNN "
            "code of its own"
        ),
        reason=(
            "The shared fallback code for procedural-transform warnings — most "
            "transform-level messages carry their own specific code (reconciled from "
            "the matching inline carrier in the output), but a message with no "
            "corresponding inline carrier still needs a stable code to report through "
            "rather than shipping uncoded."
        ),
        example_case=(
            "tests/integration/test_pg_source_wave1.py::TestParseFallbackDegradesCrossDialect::test_unparsed_routine_degrades_pg"
        ),
        divergence=(
            "Varies by the underlying message; in the bound example, a MySQL CONTINUE "
            "handler for SQLEXCEPTION has no PostgreSQL equivalent and the whole "
            "routine degrades to a documented carrier."
        ),
    ),
}
