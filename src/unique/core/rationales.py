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
            "T-SQL requires IDENTITY_INSERT ON before a script may supply its "
            "own value for an identity column; no other engine has an explicit "
            "identity-override mode — they simply accept an explicit value in "
            "the INSERT column list — so the ON/OFF bracket has nothing to map "
            "to."
        ),
        example_case="reda-ts-identity-insert",
        divergence=(
            "The INSERT's data is faithful; the two SET directives degrade to "
            "carriers (one warning)."
        ),
    ),
    "UNIQUE-1014": _R(
        construct="Physical index storage clause, e.g. WITH (FILLFACTOR = n) (T-SQL)",
        reason=(
            "FILLFACTOR and sibling physical clauses reserve per-page free "
            "space — a storage-tuning knob with no logical effect on query "
            "results; Oracle and MySQL CREATE INDEX have no equivalent clause."
        ),
        example_case="reda-ts-index-fillfactor-mysql",
        divergence=(
            "Faithful in result (storage-only); the clause is dropped and kept "
            "in a restorable note."
        ),
    ),
    "UNIQUE-1015": _R(
        construct=(
            "DISTINCT / ORDER BY over a string column under MySQL's default "
            "collation"
        ),
        reason=(
            "MySQL's default collation is case-insensitive, so DISTINCT / "
            "GROUP BY / ORDER BY treat 'a' and 'A' as equal and collapse them "
            "into one row; the case-sensitive PostgreSQL/Oracle defaults keep "
            "them distinct — a row-count divergence no ORDER BY LOWER() rewrite "
            "can bridge without column-level collation visibility."
        ),
        example_case="my-distinct-case",
        divergence="Documented limit, warned — deduplicated row counts may differ.",
    ),
    "UNIQUE-1016": _R(
        construct=(
            "GROUP BY CUBE / ROLLUP / GROUPING SETS super-aggregate rows " "(→ MySQL)"
        ),
        reason=(
            "MySQL has no CUBE / GROUPING SETS and only a trailing WITH "
            "ROLLUP, so a multi-element grouping's subtotal (super-aggregate) "
            "rows cannot be produced; only the base grouping is kept."
        ),
        example_case="pg-grouping-fn",
        divergence="Warned — base grouping kept; subtotal rows omitted.",
    ),
    "UNIQUE-1049": _R(
        construct=(
            "IDENTITY / GENERATED AS IDENTITY with a non-default "
            "START/INCREMENT (→ MySQL)"
        ),
        reason=(
            "MySQL's only identity form is AUTO_INCREMENT, whose seed is a "
            "table option (AUTO_INCREMENT = n) with no per-column "
            "START/INCREMENT — a non-default seed/step cannot be reproduced as "
            "a column clause."
        ),
        example_case="ora-identity-opts",
        divergence="Warned limit — AUTO_INCREMENT starts at 1 and steps by 1.",
    ),
    "UNIQUE-1054": _R(
        construct="Cascading referential action on a self-referencing FK (→ T-SQL)",
        reason=(
            "T-SQL rejects a cascading action on a self-referencing foreign "
            "key outright (error 1785 at CREATE TABLE time) — an engine "
            "restriction, not a missing feature."
        ),
        example_case="my-self-fk",
        divergence=(
            "Warned limit — downgraded to ON DELETE NO ACTION; emulate the "
            "cascade with an AFTER trigger."
        ),
    ),
    "UNIQUE-1065": _R(
        construct="CAST(... AS TIME) and other Oracle-absent value types",
        reason=(
            "Oracle has no bare TIME (or plain INTERVAL) type, so the value is "
            "kept as text with a documented carrier rather than an invalid "
            "cast."
        ),
        example_case="my-cast-time",
        divergence="Warned limit — value kept as text.",
    ),
    "UNIQUE-1066": _R(
        construct="MySQL JSON type / CAST(... AS JSON)",
        reason=(
            "MySQL's JSON type has no faithful cross-engine equivalent — T-SQL "
            "has no JSON type at all, and canonical JSON spacing differs on "
            "PostgreSQL/Oracle — so the value is kept as text."
        ),
        example_case="my-cast-json",
        divergence="Warned limit — value kept as text.",
    ),
    "UNIQUE-1067": _R(
        construct="PostgreSQL geometric type (point/line/…) cast or column",
        reason=(
            "PostgreSQL's geometric types have no cross-engine model (MySQL's "
            "spatial POINT is a different WKB type), so the value is kept as "
            "text."
        ),
        example_case="pg-cast-point",
        divergence="Warned limit — value kept as text.",
    ),
    "UNIQUE-1069": _R(
        construct="MySQL UNSIGNED integer type / CAST(... AS UNSIGNED)",
        reason=(
            "No other engine has an UNSIGNED integer type; the value is mapped "
            "to a signed NUMERIC/NUMBER, so unsigned wraparound semantics are "
            "not preserved."
        ),
        example_case="my-cast-convert",
        divergence="Warned limit — unsigned wraparound not preserved.",
    ),
    "UNIQUE-1076": _R(
        construct=(
            "LISTAGG(...) WITHIN GROUP (...) OVER (...) — windowed string "
            "aggregation (Oracle)"
        ),
        reason=(
            "T-SQL STRING_AGG and MySQL GROUP_CONCAT can never carry an OVER "
            "clause, and PostgreSQL rejects an ORDER-BY aggregate used as a "
            "window function — there is no running-string-aggregate form to "
            "target."
        ),
        example_case="ora-listagg-over",
        divergence="Warned limit — degrades to a NULL value plus annotation.",
    ),
    "UNIQUE-1077": _R(
        construct="GROUPS window frame (PostgreSQL / Oracle)",
        reason=(
            "T-SQL and MySQL implement only ROWS and RANGE frame units; a "
            "GROUPS frame spans whole peer groups, and no ROWS/RANGE "
            "combination reproduces that boundary when the ORDER BY key has "
            "ties."
        ),
        example_case="pg-window-groups-frame",
        divergence=(
            "Warned limit on T-SQL/MySQL — degrades to a NULL carrier; "
            "faithful on Oracle/PostgreSQL."
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
            "Oracle has no on-disk representation for an empty string distinct "
            "from NULL — an empty-string result becomes NULL — so a value that "
            "is '' on other engines cannot be reproduced there."
        ),
        example_case="pg-repeat-negative",
        divergence="Warned limit — the empty string surfaces as Oracle NULL.",
    ),
    "UNIQUE-1083": _R(
        construct="DATEPART(WEEKDAY, d) (T-SQL)",
        reason=(
            "DATEPART(WEEKDAY) depends on the session @@DATEFIRST setting, "
            "which Unique cannot observe at transpile time; the conversion "
            "assumes the T-SQL default (Sunday = 1)."
        ),
        example_case="reda-ts-datepart-weekday",
        divergence=(
            "Warned — correct under the default @@DATEFIRST = 7; a session that "
            "changed DATEFIRST will see a different result."
        ),
    ),
    "UNIQUE-1088": _R(
        construct="MySQL UpdateXML() (→ other engines)",
        reason=(
            "UpdateXML has no cross-engine equivalent — PostgreSQL lacks it, "
            "and T-SQL .modify() / Oracle UPDATEXML differ in shape and "
            "semantics."
        ),
        example_case="my-xml-fns",
        divergence="Warned limit.",
    ),
    "UNIQUE-1090": _R(
        construct="Oracle REGEXP_SUBSTR capture-group extraction (6th arg) (→ MySQL)",
        reason=(
            "MySQL's REGEXP_SUBSTR has no capture-group argument, so the "
            "sub-group extraction cannot be expressed; the portable "
            "(str, pat, pos, occ) subset is emitted."
        ),
        example_case="ora-regexp-group",
        divergence="Warned limit — capture-group extraction not reproduced.",
    ),
    "UNIQUE-1096": _R(
        construct="EXTRACT(EPOCH FROM interval) (PostgreSQL)",
        reason=(
            "T-SQL and MySQL have no interval value type, so the epoch (total "
            "seconds) of an interval value has no portable equivalent."
        ),
        example_case="pg-epoch",
        divergence=(
            "Warned limit — degrades to NULL + annotation (EPOCH FROM a "
            "timestamp is still computed)."
        ),
    ),
    "UNIQUE-1097": _R(
        construct="EXTRACT(MICROSECONDS FROM TIME) (→ Oracle)",
        reason=(
            "Oracle has no TIME type, so the microseconds field of a TIME "
            "value has no Oracle equivalent."
        ),
        example_case="pg-frac-seconds",
        divergence="Warned limit.",
    ),
    "UNIQUE-1100": _R(
        construct="MySQL CHAR(n) as a numeric-to-byte-string function",
        reason=(
            "MySQL's CHAR(n) returns a multi-byte byte string (CHAR(256) = the "
            "2-byte string 0x0100), not a single Unicode code point like "
            "CHR/NCHAR, so the two cannot be equated."
        ),
        example_case="my-char-256",
        divergence=(
            "Warned limit — carrier flags the byte-string vs code-point " "difference."
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
            "PostgreSQL/MySQL offer only FOR UPDATE / NOWAIT / SKIP LOCKED, "
            "with no bounded-wait timeout, so the WAIT <n> bound has no "
            "equivalent."
        ),
        example_case="ora-forupdate-wait",
        divergence="Warned limit — it blocks with the target's default behavior.",
    ),
    "UNIQUE-1137": _R(
        construct="T-SQL OUTPUT ... INTO <table> redirect (→ PostgreSQL)",
        reason=(
            "PostgreSQL's RETURNING only returns a result set to the caller; "
            "it has no INTO <table> redirect form, so the redirect cannot be "
            "expressed in a plain INSERT."
        ),
        example_case="reda-ts-output-into",
        divergence=(
            "Warned limit — the INTO redirect is dropped; the base DML and "
            "plain RETURNING are faithful."
        ),
    ),
    "UNIQUE-1139": _R(
        construct="A top-level OUTPUT / RETURNING result set (→ Oracle)",
        reason=(
            "Oracle's RETURNING is PL/SQL-only — it must target INTO bind "
            "variables and cannot stand alone in a plain SQL statement "
            "(ORA-63809) — so a standalone OUTPUT/RETURNING has no Oracle "
            "equivalent."
        ),
        example_case="reda-ts-output-into",
        divergence=(
            "Warned limit — the DML runs; the returned result set is "
            "documented, not produced."
        ),
    ),
    "UNIQUE-1148": _R(
        construct="Foreign-key ON UPDATE referential action (→ Oracle)",
        reason=(
            "Oracle foreign keys support only ON DELETE CASCADE / SET NULL — "
            "there is no ON UPDATE referential action (ORA-00905)."
        ),
        example_case="reda-ts-fk-on-update",
        divergence=(
            "Warned limit — ON UPDATE is dropped; reproduce it with a trigger "
            "if needed."
        ),
    ),
    "UNIQUE-1151": _R(
        construct=(
            "A source-engine built-in with no form in the target's catalog "
            "(e.g. SOUNDEX → PostgreSQL)"
        ),
        reason=(
            "A call that is a built-in of the source engine (clearly meant to "
            "run, not a user object) but absent from the target's catalog "
            "would be rejected outright, so the whole statement degrades rather "
            "than shipping an invalid call — the general unmapped-built-in "
            "gate."
        ),
        example_case="ora-soundex",
        divergence=(
            "Warned limit — the statement is preserved as a carrier and the "
            "failing built-in is named."
        ),
    ),
    "UNIQUE-1152": _R(
        construct="Oracle %TYPE / %ROWTYPE column-type reference (without --db-url)",
        reason=(
            "Only Oracle supports %TYPE/%ROWTYPE; resolving the real column "
            "type needs a live catalog lookup (ALL_TAB_COLUMNS) unavailable "
            "without a DB connection, so a permissive carrier type is emitted "
            "with the original reference preserved for a faithful round-trip "
            "back to Oracle."
        ),
        example_case=(
            "tests/integration/test_procedural.py::"
            "test_type_reference_documented_then_restored"
        ),
        divergence=(
            "Warned limit without --db-url (carrier type may not match "
            "exactly); faithful with --db-url or on an Oracle→Oracle "
            "round-trip."
        ),
    ),
    "UNIQUE-1161": _R(
        construct="T-SQL sp_executesql parameter declarations/bindings (→ MySQL)",
        reason=(
            "MySQL's PREPARE/EXECUTE has no inline parameter-declaration + "
            "binding form matching sp_executesql's @params list, so the "
            "declarations/bindings are dropped and must be passed via "
            "EXECUTE ... USING."
        ),
        example_case="ts-sp-executesql",
        divergence="Warned limit — parameter bindings dropped.",
    ),
    "UNIQUE-1180": _R(
        construct="T-SQL sp_executesql named parameters (→ Oracle)",
        reason=(
            "Oracle EXECUTE IMMEDIATE ... USING binds positionally, so the "
            "named @params of sp_executesql must be re-spelled inside the "
            "dynamic string as :1, :2, …."
        ),
        example_case="ts-sp-executesql",
        divergence="Warned limit — placeholders must be renumbered positionally.",
    ),
    "UNIQUE-1207": _R(
        construct=(
            "Inherent value divergence: default-collation comparison, Oracle "
            "'' ≡ NULL, or byte-vs-char length (approved limit)"
        ),
        reason=(
            "These divergences (case/accent/trailing-space comparison under "
            "the default collation, Oracle's '' ≡ NULL, LENGTH "
            "byte-vs-char) are per-column/connection properties the SQL text "
            "carries no trace of; no statement-level rewrite bridges them "
            "without column-collation/encoding visibility Unique does not have."
        ),
        example_case="ora-empty-null",
        divergence=(
            "Approved documented limit, warned — the value or row count may " "differ."
        ),
    ),
    "UNIQUE-1211": _R(
        construct="EXEC sp_<name> — a T-SQL system procedure (→ other engines)",
        reason=(
            "T-SQL system procedures call SQL Server's own catalog/admin "
            "machinery; no other engine exposes the same operation through a "
            "callable procedure with the same name or signature."
        ),
        example_case="reda-ts-exec-swallow-next",
        divergence=(
            "Warned limit — the call becomes a carrier; the administrative "
            "action must be performed via the target's own tooling."
        ),
    ),
    "UNIQUE-1212": _R(
        construct=(
            "A standalone INSERT/UPDATE/DELETE ... OUTPUT result set "
            "(→ Oracle / MySQL)"
        ),
        reason=(
            "Neither Oracle (RETURNING is PL/SQL-only, ORA-63809) nor MySQL "
            "has a standalone data-modifying-statement result set, so the "
            "OUTPUT rows cannot be returned to the caller."
        ),
        example_case="ts-insert-output",
        divergence=(
            "Warned limit — the DML effect is faithful; the returned result "
            "set is documented, not produced."
        ),
    ),
    "UNIQUE-1233": _R(
        construct="A transaction closer (COMMIT/END/ROLLBACK) whose opener failed",
        reason=(
            "When a transaction opener (BEGIN) glues to the next statement and "
            "fails to parse, that whole batch degrades to a parse-failure "
            "carrier — no BEGIN reaches the output. Emitting the sibling closer "
            "as an executable COMMIT/ROLLBACK would then run against no open "
            "transaction (T-SQL error 3902), so the closer must degrade too."
        ),
        example_case=(
            "tests/unit/core/test_transpiler.py::"
            "TestTransactionOpenerDegradeCoherence::"
            "test_orphan_closer_after_failed_opener_degrades"
        ),
        divergence=(
            "Coherent degrade — the closer is preserved as a comment so the "
            "output has no orphan COMMIT; both halves of the broken "
            "transaction unit are carried, not silently dropped."
        ),
    ),
}
