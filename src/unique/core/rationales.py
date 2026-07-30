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
}
