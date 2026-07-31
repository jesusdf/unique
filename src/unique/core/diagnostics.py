# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Diagnostic code registry — the ``UNIQUE-NNNN`` catalog (B32 wave 1).

Every warning/error/carrier the transpiler emits carries a stable code so a
user can grep for it, suppress it, or look it up — the same contract as the
engines we transpile (``ORA-00942``, ``SQLSTATE``) and modern compilers
(``rustc E0308``). A carrier comment therefore reads ``-- UNIQUE-1234: …`` /
``/* UNIQUE-1234: … */`` and the synthesized :class:`TransformWarning` copies
that code into its ``.code`` field.

Allocation discipline (binding):

* **Flat sequential numbering** — ``UNIQUE-1001`` upward, four digits, no
  thematic ranges (they rot). The construct's ``category`` is registry
  metadata, not encoded in the number.
* **Append-only.** A new diagnostic takes the next free number. Never
  **renumber** an existing code and never **reuse** a retired one — outputs,
  docs anchors, user grep-filters and telemetry all key on the number, so a
  reused code silently changes meaning across releases.
* **One code per distinct diagnostic**, not per call site: two emission sites
  that report the same construct share a code (e.g. the "discarded procedure
  RETURN value" carrier emitted by three procedural emitters).
* The ``message`` is a human-readable *template* describing the construct; the
  emission site renders the live message (with dialect names and identifiers).
  It is documentation and the reference-check target, not a format string.

The ``test_diagnostics`` unit test is the CI collision/coverage check: it
asserts codes are unique and well-formed, that every registered code is
referenced by an emission site in ``src/``, and that every ``UNIQUE-NNNN``
carrier emitted in ``src/`` is registered here.
"""

from __future__ import annotations

import re
from typing import NamedTuple


class Diagnostic(NamedTuple):
    """Registry metadata for one ``UNIQUE-NNNN`` diagnostic code."""

    category: str
    message: str


_D = Diagnostic

#: Regex fragment recognizing a carrier marker in emitted SQL — matches both
#: the legacy uncoded ``UNIQUE:`` (pre-B32 outputs) and the coded
#: ``UNIQUE-1234:`` form. Consumers that reconcile carriers share this so the
#: widening lives in one place.
MARKER = r"UNIQUE(?:-(?P<code>\d{4}))?:"

#: Compiled, anchored matcher for a bare code token (e.g. in a registry check).
CODE_RE = re.compile(r"UNIQUE-\d{4}")

#: A PostgreSQL dollar-quote delimiter (``$$`` or ``$tag$``).
_DOLLAR_TAG_RE = re.compile(r"\$[A-Za-z0-9_]*\$")


def neutralize_dollar_quotes(text: str) -> str:
    """Defang any ``$$``/``$tag$`` dollar-quote delimiter in *text*.

    Carrier comments preserve a degraded routine by prefixing every line with
    ``--``. When the routine's generated PostgreSQL body carried a ``DO $$`` /
    ``AS $$`` wrapper, the ``$$`` leaked into a ``--`` line; a statement scanner
    that tracks dollar-quotes then opens or closes a body on a *comment* line and
    desyncs the split. Inserting a space inside each delimiter (``$$`` -> ``$ $``,
    ``$body$`` -> ``$body $``) keeps the comment human-readable while making it
    self-contained — it cannot terminate or open a dollar-quote. The carrier is
    documentation, never executable (it degraded precisely because it cannot run),
    so this trivia-only rewrite loses nothing recoverable.
    """
    return _DOLLAR_TAG_RE.sub(lambda m: m.group()[:-1] + " $", text)


def is_registered(code: str) -> bool:
    """Whether *code* (e.g. ``"UNIQUE-1042"``) is a known diagnostic."""
    return code in DIAGNOSTICS


#: The catalog: ``UNIQUE-NNNN`` -> :class:`Diagnostic`. Append-only; see the
#: module docstring for the allocation rules.
DIAGNOSTICS: dict[str, Diagnostic] = {
    "UNIQUE-1001": _D(
        "statement",
        "MERGE rewritten as INSERT ... ON DUPLICATE KEY UPDATE; requires a UNIQUE or "
        "PRIMARY KEY on ({on_cols}",
    ),
    "UNIQUE-1002": _D(
        "statement",
        "SET IDENTITY_INSERT {_ii_tbl} {_ii_st} is a T-SQL session directive with no "
        "cross-engine equivalent; dropped (the target accepts an explicit value into "
        "an identity/serial/ auto_increment column) (docs/03-unsupported.md",
    ),
    "UNIQUE-1003": _D(
        "statement",
        "statement preserved as a comment; the specific reason is carried at runtime",
    ),
    "UNIQUE-1004": _D(
        "statement",
        "NULLS FIRST/LAST index ordering has no {dialect} equivalent; dropped (it "
        "affects only the index's physical null order, not query results",
    ),
    "UNIQUE-1005": _D(
        "statement",
        "statement preserved as a comment; the specific reason is carried at runtime",
    ),
    "UNIQUE-1006": _D("statement", "{reason}"),
    "UNIQUE-1007": _D(
        "statement",
        "partial-index predicate dropped (no {dialect} filtered-index form); the index "
        "is broader than the source's: …",
    ),
    "UNIQUE-1008": _D(
        "statement",
        "PostgreSQL unique indexes treat NULLs as distinct; T-SQL allows a single NULL "
        "per unique index",
    ),
    "UNIQUE-1009": _D(
        "statement",
        "T-SQL has no boolean value type; NOT of a non-predicate (e.g. NOT NULL) has "
        "no equivalent -- see docs/03-unsupported.md",
    ),
    "UNIQUE-1010": _D(
        "statement",
        "T-SQL ALTER COLUMN defaults the column to NULL; the script does not define "
        "{table}.{col}'s nullability, so it cannot be re-stated — verify the column "
        "keeps its constraint",
    ),
    "UNIQUE-1011": _D(
        "statement",
        "named DEFAULT constraint {n} dropped (defaults are anonymous on this engine",
    ),
    "UNIQUE-1012": _D(
        "statement", "{dialect} does not support INCLUDE covering columns; dropped: …"
    ),
    "UNIQUE-1013": _D(
        "statement", "{dialect} does not support filtered indexes; dropped predicate:…"
    ),
    "UNIQUE-1014": _D(
        "statement",
        "{clauses} -- tsql-only, no {dialect} equivalent (physical index clause",
    ),
    "UNIQUE-1015": _D(
        "statement",
        "MySQL default collation is case-insensitive, so DISTINCT/ordering on a string "
        "column merges case-differing values",
    ),
    "UNIQUE-1016": _D(
        "statement",
        "MySQL has no GROUP BY …; the base grouping is kept and the super-aggregate "
        "(subtotal) rows are omitted",
    ),
    "UNIQUE-1017": _D(
        "statement",
        "MySQL has no multi-element GROUP BY (CUBE/ROLLUP/ GROUPING SETS combined); "
        "the base grouping is kept and the super-aggregate (subtotal) rows are omitted",
    ),
    "UNIQUE-1018": _D(
        "statement",
        "T-SQL FOR XML/JSON row serialization has no cross-engine equivalent; the "
        "clause is dropped and the base rows are returned instead (see "
        "docs/03-unsupported.md",
    ),
    "UNIQUE-1019": _D(
        "statement",
        "MySQL SQL_CALC_FOUND_ROWS has no equivalent here; the full row count for a "
        "following FOUND_ROWS() is not computed — run a separate COUNT(*) query",
    ),
    "UNIQUE-1020": _D(
        "statement",
        "all-defaults INSERT has no Oracle spelling without the column list; original "
        "preserved",
    ),
    "UNIQUE-1021": _D(
        "statement",
        "INSERT preserved as a comment; the specific reason is carried at runtime",
    ),
    "UNIQUE-1022": _D(
        "statement",
        "conflict target assumed to be (…) from the table's key; the MySQL source "
        "names no explicit target (fires on any unique key",
    ),
    "UNIQUE-1023": _D(
        "statement",
        "INSERT IGNORE also swallows other errors (bad values, FK violations), not "
        "only duplicate keys — unlike PG ON CONFLICT DO NOTHING",
    ),
    "UNIQUE-1024": _D(
        "statement",
        "MySQL ON DUPLICATE KEY UPDATE fires on ANY unique/primary key, not a single "
        "named conflict target",
    ),
    "UNIQUE-1025": _D(
        "statement",
        "MERGE ON key assumed to be (…) from the table's key; the source names no "
        "explicit conflict target",
    ),
    "UNIQUE-1026": _D(
        "statement",
        "Oracle has no UPDATE ... FROM and this join shape (no ON condition) cannot "
        "become a correlated subquery; rewrite as a MERGE. Original",
    ),
    "UNIQUE-1027": _D("statement", "@@ROWCOUNT has no top-level {dialect} equivalent"),
    "UNIQUE-1028": _D(
        "statement",
        "@@FETCH_STATUS has no top-level {dialect} equivalent; it is cursor state",
    ),
    "UNIQUE-1029": _D(
        "statement",
        "@@ERROR has no top-level {dialect} equivalent; use an exception handler",
    ),
    "UNIQUE-1030": _D(
        "statement", "@@VERSION -> {fn}; version string differs per engine"
    ),
    "UNIQUE-1031": _D(
        "statement", "@@VERSION has no Oracle equivalent outside v$version"
    ),
    "UNIQUE-1032": _D("statement", "@@SPID -> {fn}; session id differs per engine"),
    "UNIQUE-1033": _D(
        "statement", "SQL%ROWCOUNT has no top-level {dialect} equivalent"
    ),
    "UNIQUE-1034": _D(
        "statement",
        "TABLESAMPLE ({what}) has no MySQL equivalent — all rows returned "
        "(docs/03-unsupported.md",
    ),
    "UNIQUE-1035": _D(
        "statement",
        "TABLESAMPLE by row count has no Oracle SAMPLE form (docs/03-unsupported.md",
    ),
    "UNIQUE-1036": _D(
        "statement",
        "TABLESAMPLE by row count has no PostgreSQL equivalent (docs/03-unsupported.md",
    ),
    "UNIQUE-1037": _D(
        "statement",
        "source had WITH TIES; MySQL has no equivalent — rows tying the last one are "
        "not returned (see docs/03-unsupported.md",
    ),
    "UNIQUE-1038": _D(
        "statement",
        "source was TOP n PERCENT; {dialect} has no LIMIT PERCENT — emitted as a row "
        "count, adjust to CEIL(n/100 * total_rows) if a true percentage is required",
    ),
    "UNIQUE-1039": _D(
        "ddl",
        "Oracle WITH LOCAL TIME ZONE and PostgreSQL timestamptz both display column "
        "{name} in the session time zone (same instant, session-dependent wall clock) "
        "(docs/03-unsupported.md",
    ),
    "UNIQUE-1040": _D(
        "ddl",
        "tsql has no session-local timestamp type — column {name} WITH LOCAL TIME ZONE "
        "maps to DATETIMEOFFSET; the value's instant is kept but the session-time-zone "
        "display is not reproduced (docs/03-unsupported.md",
    ),
    "UNIQUE-1041": _D(
        "ddl",
        "mysql has no session-local timestamp type — column {name} WITH LOCAL TIME "
        "ZONE maps to TIMESTAMP; the value's instant is kept but the session-time-zone "
        "display is not reproduced (docs/03-unsupported.md",
    ),
    "UNIQUE-1042": _D(
        "ddl",
        "Oracle has no TIME type — column … stores the time of day as INTERVAL DAY TO "
        "SECOND{tz} (docs/03-unsupported.md",
    ),
    "UNIQUE-1043": _D(
        "ddl",
        "PostgreSQL INTERVAL mixes year-month and day-second fields; column … is "
        "mapped to INTERVAL DAY TO SECOND — year-month values need a separate INTERVAL "
        "YEAR TO MONTH column (docs/03-unsupported.md",
    ),
    "UNIQUE-1044": _D(
        "ddl",
        "{dialect} has no INTERVAL column type — column … keeps the interval as text "
        "(docs/03-unsupported.md",
    ),
    "UNIQUE-1045": _D(
        "ddl",
        "MySQL fractional-seconds precision caps at 6 — column … precision … clamped "
        "to 6 (docs/03-unsupported.md",
    ),
    "UNIQUE-1046": _D(
        "ddl",
        "{dialect} has no bit-string type — column … BIT(…) stores its numeric value "
        "as {mapped} (docs/03-unsupported.md",
    ),
    "UNIQUE-1047": _D(
        "ddl",
        "MySQL SET type on {col_name} has no {dialect} equivalent; stored as "
        "{varchar}({total_len}). Allowed members: {quoted_values}",
    ),
    "UNIQUE-1048": _D(
        "ddl",
        "LIKE clone copies column structure only here; the source's indexes/keys are "
        "not cloned",
    ),
    "UNIQUE-1049": _D(
        "ddl",
        "source IDENTITY (START {seed} INCREMENT {step}) has no MySQL column form — "
        "AUTO_INCREMENT starts at 1, steps by 1 (docs/03-unsupported.md",
    ),
    "UNIQUE-1050": _D(
        "ddl", "MySQL ON UPDATE column clause has no equivalent on the target engine"
    ),
    "UNIQUE-1051": _D(
        "ddl",
        "column {col_name} collation/charset (…) has no portable {dialect} equivalent; "
        "the column uses the default collation (comparisons/ordering may differ) — set "
        "it explicitly on the target or supply the source DB connection",
    ),
    "UNIQUE-1052": _D(
        "ddl",
        "column {col_name} was INVISIBLE (excluded from SELECT *) on the source; "
        "{dialect} has no invisible-column attribute, so the column is now visible to "
        "SELECT * (docs/03-unsupported.md",
    ),
    "UNIQUE-1053": _D(
        "ddl",
        "PostgreSQL UNIQUE … NULLS NOT DISTINCT (NULLs compare equal) has no {dialect} "
        "equivalent; a plain UNIQUE treats NULLs as distinct (docs/03-unsupported.md",
    ),
    "UNIQUE-1054": _D(
        "ddl",
        "T-SQL forbids a cascading action on a self-referencing FK (error 1785); "
        "downgraded to NO ACTION — emulate with an AFTER trigger if the automatic "
        "action is required (docs/03-unsupported.md",
    ),
    "UNIQUE-1055": _D(
        "ddl",
        "Oracle has no ON DELETE SET DEFAULT referential action; dropped (FK reverts "
        "to NO ACTION) — emulate with an AFTER DELETE trigger if required "
        "(docs/03-unsupported.md",
    ),
    "UNIQUE-1056": _D(
        "ddl",
        "T-SQL In-Memory OLTP storage option(s) [{opts}] have no {dialect} equivalent; "
        "the table is created as a regular disk-based table (no logical/value "
        "difference",
    ),
    "UNIQUE-1057": _D(
        "ddl",
        "MySQL table default collation/charset (…) has no portable {dialect} "
        "equivalent; string columns use the default collation (comparisons/ordering "
        "may differ) — set it explicitly on the target or supply the source DB "
        "connection",
    ),
    "UNIQUE-1058": _D(
        "ddl", "view modifier {mod} is not portable on {dialect}; dropped"
    ),
    "UNIQUE-1059": _D(
        "ddl",
        "MySQL has no sequences (use an AUTO_INCREMENT column); original preserved",
    ),
    "UNIQUE-1060": _D("ddl", "MySQL has no user-defined types; original preserved"),
    "UNIQUE-1061": _D(
        "ddl",
        "{dialect} DROP INDEX requires the owning table, which the source statement "
        "does not carry; original preserved",
    ),
    "UNIQUE-1062": _D(
        "ddl",
        "PostgreSQL DROP TRIGGER requires the owning table (ON tbl), which the source "
        "statement does not carry; original preserved",
    ),
    "UNIQUE-1063": _D("expression", "… (…) — see docs/03-unsupported.md"),
    "UNIQUE-1064": _D(
        "expression",
        "Oracle SESSIONTIMEZONE is session- dependent; the mapped expression reports "
        "this session's zone/offset in the target's own format (docs/03-unsupported.md",
    ),
    "UNIQUE-1065": _D(
        "expression",
        "Oracle has no {_what} type — value kept as text (docs/03-unsupported.md",
    ),
    "UNIQUE-1066": _D(
        "expression",
        "MySQL JSON type has no faithful cross-engine equivalent (T-SQL has no JSON "
        "type; canonical JSON spacing differs on PG/Oracle) — value kept as text — see "
        "docs/03-unsupported.md",
    ),
    "UNIQUE-1067": _D(
        "expression",
        "PostgreSQL geometric type … has no cross-engine equivalent — value kept as "
        "text (docs/03-unsupported.md",
    ),
    "UNIQUE-1068": _D(
        "expression",
        "PostgreSQL NaN/Infinity has no {dialect} numeric equivalent "
        "(docs/03-unsupported.md",
    ),
    "UNIQUE-1069": _D(
        "expression",
        "MySQL UNSIGNED has no {dialect} equivalent; unsigned wraparound not preserved "
        "(docs/03-unsupported.md",
    ),
    "UNIQUE-1070": _D(
        "expression",
        "Oracle DEFAULT ... ON CONVERSION ERROR has no {dialect} error-safe cast for "
        "this type; fallback dropped -- see docs/03-unsupported.md",
    ),
    "UNIQUE-1071": _D(
        "expression",
        "T-SQL FOR XML/JSON row serialization has no cross-engine equivalent — see "
        "docs/03-unsupported.md",
    ),
    "UNIQUE-1072": _D("expression", "…; no {dialect} mapping — review"),
    "UNIQUE-1073": _D(
        "expression",
        "MySQL date arithmetic on a non-datetime string literal yields NULL "
        "(docs/03-unsupported.md",
    ),
    "UNIQUE-1074": _D(
        "expression",
        "MySQL DATE - DATE is a numeric YYYYMMDD subtraction; normalized to a day "
        "count (docs/03-unsupported.md",
    ),
    "UNIQUE-1075": _D(
        "expression",
        "timestamp difference is an INTERVAL with no {dialect} equivalent; emitted as "
        "a SECOND count (docs/03-unsupported.md",
    ),
    "UNIQUE-1076": _D(
        "expression",
        "windowed string aggregation (string-agg OVER …) has no {dialect} equivalent — "
        "see docs/03-unsupported.md",
    ),
    "UNIQUE-1077": _D(
        "expression",
        "a GROUPS window frame has no {dialect} equivalent (only ROWS/RANGE, and no "
        "faithful rewrite with ORDER-BY ties) — see docs/03-unsupported.md",
    ),
    "UNIQUE-1078": _D(
        "expression",
        "a window frame … has no {dialect} equivalent (T-SQL/MySQL have no EXCLUDE, "
        "and no faithful ROWS/RANGE rewrite) — see docs/03-unsupported.md",
    ),
    "UNIQUE-1079": _D(
        "expression",
        "{fn} unit '{unit_sql}' has no {dialect} equivalent — the value was not "
        "computed (docs/03-unsupported.md",
    ),
    "UNIQUE-1080": _D(
        "expression",
        "T-SQL has no sequence CURRVAL; capture NEXT VALUE FOR {seq} in a variable — "
        "see docs/03-unsupported.md",
    ),
    "UNIQUE-1081": _D(
        "expression",
        "DATEPART(WEEKDAY) is @@DATEFIRST-dependent; assumes the session default "
        "(Sunday=1",
    ),
    "UNIQUE-1082": _D(
        "expression", "Oracle stores an empty string as NULL (docs/03-unsupported.md)"
    ),
    "UNIQUE-1083": _D(
        "expression",
        "DATEPART(WEEKDAY) is @@DATEFIRST-dependent; converted assuming the session "
        "default (Sunday=1",
    ),
    "UNIQUE-1084": _D(
        "expression",
        "Oracle ROUND(date, '{fmt}') (nearest {fmt} boundary) has no faithful "
        "{dialect} equivalent — the value was not computed (docs/03-unsupported.md",
    ),
    "UNIQUE-1085": _D(
        "expression",
        "Oracle TRUNC(date, '{raw_up}') has no {dialect} equivalent — the value was "
        "not computed (docs/03-unsupported.md",
    ),
    "UNIQUE-1086": _D(
        "expression",
        "EXTRACT({part}) has no {dialect} equivalent — the value was not computed "
        "(docs/03-unsupported.md",
    ),
    "UNIQUE-1087": _D(
        "expression",
        "Oracle INSTR with an occurrence count or backward (negative-start) search has "
        "no portable equivalent for non-literal arguments — see docs/03-unsupported.md",
    ),
    "UNIQUE-1088": _D(
        "expression",
        "MySQL UpdateXML has no cross-engine equivalent (PG lacks it; T-SQL .modify() "
        "and Oracle UPDATEXML differ) — see docs/03-unsupported.md",
    ),
    "UNIQUE-1089": _D(
        "expression",
        "collation names are engine-specific and cannot match across engines "
        "(docs/03-unsupported.md",
    ),
    "UNIQUE-1090": _D(
        "expression",
        "Oracle REGEXP_SUBSTR capture-group extraction (6th arg) has no MySQL "
        "equivalent (docs/03-unsupported.md",
    ),
    "UNIQUE-1091": _D(
        "expression",
        "MySQL has no TRANSLATE and a nested-REPLACE emulation is order-dependent (not "
        "equivalent) — see docs/03-unsupported.md",
    ),
    "UNIQUE-1092": _D(
        "expression",
        "SUBSTRING(x FROM POSIX pattern) has no T-SQL regex equivalent — see "
        "docs/03-unsupported.md",
    ),
    "UNIQUE-1093": _D(
        "expression",
        "SUBSTRING(x FROM SIMILAR-TO pattern FOR escape) has no cross-engine "
        "equivalent (SQL-regex metachars differ from POSIX) — see "
        "docs/03-unsupported.md",
    ),
    "UNIQUE-1094": _D(
        "expression", "Oracle stores an empty string as NULL (docs/03-unsupported.md"
    ),
    "UNIQUE-1095": _D(
        "expression",
        "MySQL VALUES(col) outside INSERT … ON DUPLICATE KEY UPDATE is NULL",
    ),
    "UNIQUE-1096": _D(
        "expression",
        "EXTRACT(EPOCH FROM interval) has no portable equivalent (T-SQL/MySQL have no "
        "interval value type) — see docs/03-unsupported.md",
    ),
    "UNIQUE-1097": _D(
        "expression",
        "EXTRACT(MICROSECONDS FROM TIME) has no Oracle equivalent (no TIME type) — see "
        "docs/03-unsupported.md",
    ),
    "UNIQUE-1098": _D(
        "expression",
        "PG format() with %L/width/positional specifiers has no cross-engine "
        "equivalent — see docs/03-unsupported.md",
    ),
    "UNIQUE-1099": _D(
        "expression",
        "PG sha256/sha512 returns a bytea digest; other engines return a hex string "
        "(same digest, different representation) — see docs/03-unsupported.md",
    ),
    "UNIQUE-1100": _D(
        "expression",
        "MySQL CHAR({_n}) is a multi-byte byte string, not a single code point "
        "(docs/03-unsupported.md",
    ),
    "UNIQUE-1101": _D("statement", "{_cte_reason}"),
    "UNIQUE-1102": _D(
        "statement",
        "MySQL NOT ENFORCED (a CHECK defined but not validated) has no target "
        "equivalent; enforced here",
    ),
    "UNIQUE-1103": _D(
        "statement",
        "FOR SHARE (shared row lock) has no Oracle equivalent (Oracle SELECT locking "
        "is FOR UPDATE, exclusive); the shared lock is dropped (docs/03-unsupported.md",
    ),
    "UNIQUE-1104": _D(
        "statement",
        "Oracle FOR UPDATE WAIT <n> (bounded lock wait) has no {dialect} equivalent; "
        "it blocks with the default behavior (docs/03-unsupported.md",
    ),
    "UNIQUE-1105": _D(
        "statement",
        "Oracle FOR UPDATE OF <column> selects which table's rows to lock; {dialect} "
        "FOR UPDATE OF takes table names, so the OF list is dropped (every row read is "
        "locked) (docs/03-unsupported.md",
    ),
    "UNIQUE-1106": _D(
        "statement",
        "T-SQL has no expression/function index; add a computed column and index it "
        "(docs/03-unsupported.md",
    ),
    "UNIQUE-1107": _D(
        "statement",
        "T-SQL IDENTITY() in SELECT INTO reproduced as ROW_NUMBER (id values match); "
        "the identity/auto-increment column property is not portable in a CREATE TABLE "
        "AS SELECT (docs/03-unsupported.md",
    ),
    "UNIQUE-1108": _D(
        "statement",
        "{dialect} has no ALTER … NOT VALID; the constraint is validated immediately "
        "(PostgreSQL defers it",
    ),
    "UNIQUE-1109": _D(
        "statement",
        "TRUNCATE … CASCADE (also truncates FK-dependent tables) has no {dialect} "
        "equivalent; only this table is truncated — truncate any dependents explicitly",
    ),
    "UNIQUE-1110": _D(
        "statement",
        "{dialect} has no ALTER COLUMN … USING conversion expression; convert the data "
        "manually. Statement preserved as a comment",
    ),
    "UNIQUE-1111": _D(
        "statement",
        "{dialect} needs the column's declared type to alter its nullability and the "
        "script does not define {_nn_tbl_raw}.{_nn_col}; original postgresql statement "
        "preserved",
    ),
    "UNIQUE-1112": _D(
        "statement",
        "MySQL's only identity form is AUTO_INCREMENT (must be a key; a UNIQUE index "
        "is added",
    ),
    "UNIQUE-1113": _D(
        "statement",
        "PostgreSQL GIN/GiST/BRIN index has no {dialect} equivalent (access-method "
        "specific); index omitted — queries run unindexed (docs/03-unsupported.md",
    ),
    "UNIQUE-1114": _D(
        "statement",
        "expression index over a LOB-typed column is invalid on {dialect} (ORA-02327 / "
        "MySQL functional-index restriction); index omitted — queries run unindexed "
        "(docs/03-unsupported.md",
    ),
    "UNIQUE-1115": _D(
        "statement",
        "CONCURRENTLY (PostgreSQL's non-locking index build) has no {dialect} "
        "equivalent; the index is created with the target's default locking",
    ),
    "UNIQUE-1116": _D(
        "statement",
        "MySQL session setting has no {dialect} equivalent; configure the session "
        "natively.",
    ),
    "UNIQUE-1117": _D(
        "statement",
        "MySQL admin command has no {dialect} equivalent; run the target's own "
        "maintenance.",
    ),
    "UNIQUE-1118": _D(
        "statement",
        "{dialect} has no TEMPORARY sequences; statement preserved as a comment",
    ),
    "UNIQUE-1119": _D(
        "statement",
        "MySQL has no sequences; use an AUTO_INCREMENT column instead. Original",
    ),
    "UNIQUE-1120": _D(
        "statement",
        "SET SESSION AUTHORIZATION has no {dialect} equivalent; switch users natively.",
    ),
    "UNIQUE-1121": _D(
        "statement",
        "PostgreSQL session setting has no {dialect} equivalent; configure the session "
        "natively.",
    ),
    "UNIQUE-1122": _D(
        "statement",
        "{dialect} has no USE statement; connect to the target database/schema "
        "instead.",
    ),
    "UNIQUE-1123": _D(
        "statement",
        "PostgreSQL column STORAGE tuning has no {dialect} equivalent; statement "
        "preserved as a comment",
    ),
    "UNIQUE-1124": _D(
        "statement",
        "PostgreSQL's recursive-CTE SEARCH/CYCLE clause has no {dialect} equivalent; "
        "statement preserved as a comment",
    ),
    "UNIQUE-1125": _D(
        "statement",
        "MySQL has no MERGE; rewrite as INSERT ... ON DUPLICATE KEY UPDATE. Original",
    ),
    "UNIQUE-1126": _D(
        "statement",
        "CTE with unsupported embedded DML preserved as a comment; reason carried at "
        "runtime",
    ),
    "UNIQUE-1127": _D(
        "statement",
        "BEGIN TRANSACTION dropped -- Oracle starts a transaction implicitly",
    ),
    "UNIQUE-1128": _D(
        "statement",
        "T-SQL transactions have no READ … access mode; started as a regular "
        "transaction (docs/03-unsupported.md",
    ),
    "UNIQUE-1129": _D(
        "statement",
        "READ COMMITTED is Oracle's default isolation level (no-op; kept as a note so "
        "a following SET TRANSACTION mode statement can still open the transaction",
    ),
    "UNIQUE-1130": _D(
        "statement",
        "READ COMMITTED is Oracle's default isolation level (no-op; kept as a note so "
        "a following SET TRANSACTION mode statement can still open the transaction",
    ),
    "UNIQUE-1131": _D(
        "statement",
        "Oracle has no {level} isolation level (supports READ COMMITTED/SERIALIZABLE "
        "only); statement dropped. Original",
    ),
    "UNIQUE-1132": _D(
        "statement",
        "T-SQL SET TRANSACTION has no READ {mode} access mode; access mode dropped "
        "(docs/03-unsupported.md",
    ),
    "UNIQUE-1133": _D(
        "statement",
        "T-SQL SET TRANSACTION has no READ {mode} access mode "
        "(docs/03-unsupported.md); statement dropped. Original",
    ),
    "UNIQUE-1134": _D(
        "statement",
        "Oracle CONNECT BY / START WITH hierarchical query has no automatic "
        "equivalent; rewrite as a WITH RECURSIVE CTE. Original",
    ),
    "UNIQUE-1135": _D(
        "statement",
        "session-variable SELECT INTO has no cross-dialect equivalent; rewrite as the "
        "target's assignment form. Original",
    ),
    "UNIQUE-1136": _D(
        "statement",
        "INSERT combines RETURNING and ON CONFLICT; rewrite as MERGE/upsert with "
        "result capture on {dialect}. Original",
    ),
    "UNIQUE-1137": _D(
        "statement",
        "T-SQL OUTPUT … INTO <table> redirect has no PostgreSQL equivalent in a plain "
        "INSERT (it needs a data-modifying CTE); the INTO target is dropped and the "
        "RETURNING result is kept (docs/03-unsupported.md",
    ),
    "UNIQUE-1138": _D(
        "statement",
        "Oracle has no UPDATE … FROM (rewrite with a correlated subquery or MERGE) and "
        "no top-level RETURNING. Statement preserved as a comment",
    ),
    "UNIQUE-1139": _D(
        "statement", "Oracle has no top-level RETURNING; the statement returned: {cols}"
    ),
    "UNIQUE-1140": _D(
        "statement", "MySQL has no RETURNING/OUTPUT; the statement returned: {cols}"
    ),
    "UNIQUE-1141": _D(
        "statement",
        "MERGE WHEN NOT MATCHED DO NOTHING has no faithful rewrite; reason carried at "
        "runtime",
    ),
    "UNIQUE-1142": _D(
        "statement", "MERGE clause has no faithful rewrite; reason carried at runtime"
    ),
    "UNIQUE-1143": _D(
        "statement",
        "T-SQL has no FOR UPDATE/FOR SHARE row-lock clause; lock the rows with a WITH "
        "(UPDLOCK, ROWLOCK) table hint",
    ),
    "UNIQUE-1144": _D("statement", "Unhandled …"),
    "UNIQUE-1145": _D(
        "statement",
        "inline INDEX table element has no {dialect} equivalent form; index omitted — "
        "queries run unindexed. Original: …",
    ),
    "UNIQUE-1146": _D(
        "statement",
        "PostgreSQL EXCLUDE constraint has no {dialect} equivalent; enforce the "
        "exclusion with a trigger. Original: …",
    ),
    "UNIQUE-1147": _D(
        "statement",
        "{dialect} requires an explicit type for the generated column {col_name}; "
        "original computed column: …",
    ),
    "UNIQUE-1148": _D(
        "statement",
        "FK ON UPDATE referential action dropped — Oracle has no ON UPDATE FK action "
        "(docs/03-unsupported.md",
    ),
    "UNIQUE-1149": _D(
        "expression",
        "UNPIVOT has no {dialect} equivalent and the source columns are not visible to "
        "rewrite it as UNION ALL — see docs/03-unsupported.md",
    ),
    "UNIQUE-1150": _D(
        "expression",
        "PIVOT has no {dialect} equivalent and the source columns are not visible to "
        "rewrite it as conditional aggregation — see docs/03-unsupported.md",
    ),
    "UNIQUE-1151": _D(
        "validation",
        "output failed the {target} validity check ({reason}); original {source} batch "
        "preserved",
    ),
    "UNIQUE-1152": _D(
        "procedural", "type origin comment preserved from the source declaration"
    ),
    "UNIQUE-1153": _D(
        "procedural",
        "PostgreSQL trigger function ('RETURNS TRIGGER') has no … equivalent (no "
        "trigger functions; the body belongs to a CREATE TRIGGER). The non-portable "
        "translation is commented out below for review",
    ),
    "UNIQUE-1154": _D(
        "procedural",
        "inline table-valued function ('RETURNS TABLE') has no direct equivalent. ….",
    ),
    "UNIQUE-1155": _D(
        "procedural",
        "trigger reads the T-SQL inserted/deleted pseudo-tables in a set-based way … "
        "cannot express; the translation is preserved commented out for a manual "
        "rewrite",
    ),
    "UNIQUE-1156": _D(
        "procedural",
        "Oracle COMPOUND TRIGGER … (… {events} ON …) has no automatic … equivalent — "
        "it collects affected rows in a PL/SQL collection and re-aggregates in AFTER "
        "STATEMENT. Rewrite manually (PostgreSQL: a statement-level trigger with "
        "REFERENCING NEW TABLE; MySQL: a row-level trigger that re-reads the table).",
    ),
    "UNIQUE-1157": _D(
        "procedural",
        "PostgreSQL statement-level trigger delegating to a trigger function has no … "
        "equivalent (no transition tables / trigger functions). Original binding",
    ),
    "UNIQUE-1158": _D(
        "procedural",
        "{header} LOOP … has no … equivalent (no array type); statement preserved as a "
        "comment",
    ),
    "UNIQUE-1159": _D("procedural", "PRAGMA … has no … equivalent; dropped."),
    "UNIQUE-1160": _D(
        "procedural",
        "anonymous PL/SQL block has no top-level … equivalent; preserved below",
    ),
    "UNIQUE-1161": _D(
        "procedural",
        "sp_executesql parameter declarations/bindings dropped; pass them via EXECUTE "
        "... USING manually",
    ),
    "UNIQUE-1162": _D(
        "procedural",
        "notice has no output channel inside a MySQL function; message kept in "
        "@uq_notice",
    ),
    "UNIQUE-1163": _D(
        "procedural", "original RAISERROR/THROW severity/state args dropped: {rest}"
    ),
    "UNIQUE-1164": _D(
        "procedural", "BEGIN TRANSACTION dropped -- … starts a transaction implicitly"
    ),
    "UNIQUE-1165": _D(
        "procedural",
        "WAITFOR TIME '…' has no … equivalent (wait until an absolute time",
    ),
    "UNIQUE-1166": _D(
        "procedural",
        "FETCH {direction} has no … equivalent (cursors are forward-only); statement "
        "preserved as a comment",
    ),
    "UNIQUE-1167": _D(
        "procedural",
        "FETCH without INTO — … requires target variables (the source discarded the "
        "fetched row); preserved as a comment",
    ),
    "UNIQUE-1168": _D(
        "procedural",
        "GOTO … dropped -- … has no GOTO; control flow not replicated "
        "(docs/03-unsupported.md",
    ),
    "UNIQUE-1169": _D(
        "procedural", "label … dropped -- … has no GOTO/label (docs/03-unsupported.md"
    ),
    "UNIQUE-1170": _D("procedural", "could not translate; preserved for review"),
    "UNIQUE-1171": _D(
        "procedural",
        "procedural statement preserved as a comment; reason carried at runtime",
    ),
    "UNIQUE-1172": _D(
        "procedural",
        "GOTO … dropped -- MySQL has no GOTO; control flow not replicated "
        "(docs/03-unsupported.md",
    ),
    "UNIQUE-1173": _D(
        "procedural",
        "label … dropped -- MySQL has no GOTO/label (docs/03-unsupported.md",
    ),
    "UNIQUE-1174": _D(
        "procedural",
        "Oracle implicit cursor FOR-loop expanded to an explicit MySQL cursor. -- "
        "Declare one variable per selected column and complete the FETCH INTO list. "
        "DECLARE {done} INT DEFAULT FALSE; DECLARE {cur} CURSOR FOR {cursor_str}; "
        "DECLARE CONTINUE HANDLER FOR NOT FOUND SET {done} = TRUE; OPEN {cur}; "
        "{variable}_loop: LOOP …FETCH {cur} INTO /* col1, col2, ... */; …IF "
        "{done} THEN LEAVE {variable}_loop; END IF",
    ),
    "UNIQUE-1175": _D(
        "procedural",
        "cursor FOR-loop expanded; loop variables are TEXT (exact column types need "
        "--db-url metadata). BEGIN",
    ),
    "UNIQUE-1176": _D(
        "procedural",
        "MySQL has no INSTEAD OF trigger; emitted as BEFORE for review (original was "
        "INSTEAD OF, typically on a view).",
    ),
    "UNIQUE-1177": _D("procedural", "discarded procedure RETURN value ({val}"),
    "UNIQUE-1178": _D(
        "procedural",
        "dynamic SELECT INTO variable has no direct MySQL form (rewrite the dynamic "
        "string to select INTO @session variables); original",
    ),
    "UNIQUE-1179": _D(
        "procedural",
        "trigger reads the T-SQL inserted/deleted pseudo-tables in a set-based way "
        "Oracle cannot express (no transition tables — use a compound trigger); the "
        "translation is preserved commented out for a manual rewrite",
    ),
    "UNIQUE-1180": _D(
        "procedural",
        "sp_executesql named parameters bind POSITIONALLY here — spell the "
        "placeholders inside the dynamic string as :1, :2, … (docs/03-unsupported.md",
    ),
    "UNIQUE-1181": _D(
        "procedural",
        "INSTEAD OF trigger aggregates over the inserted/deleted transition table; "
        "PostgreSQL INSTEAD OF triggers are row-level only — port by hand "
        "(docs/03-unsupported.md",
    ),
    "UNIQUE-1182": _D(
        "procedural",
        "PostgreSQL allows INSTEAD OF only on views; on a table the equivalent is a "
        "BEFORE row trigger returning NULL (the original operation is suppressed",
    ),
    "UNIQUE-1183": _D(
        "procedural",
        "BEGIN TRANSACTION dropped -- PostgreSQL manages the routine transaction "
        "implicitly",
    ),
    "UNIQUE-1184": _D(
        "procedural",
        "SAVEPOINT{sp} dropped -- PL/pgSQL has no explicit savepoints; wrap the "
        "statements in a BEGIN … EXCEPTION block, which rolls back to its start on "
        "error (docs/03-unsupported.md",
    ),
    "UNIQUE-1185": _D(
        "procedural",
        "ROLLBACK TO SAVEPOINT {name} dropped -- PL/pgSQL has no explicit savepoints; "
        "the enclosing BEGIN … EXCEPTION block rolls back automatically on error "
        "(docs/03-unsupported.md",
    ),
    "UNIQUE-1186": _D(
        "procedural",
        "SELECT * INTO multiple variables needs the column list (no schema to expand "
        "'*'); statement preserved as a comment",
    ),
    "UNIQUE-1187": _D(
        "procedural",
        "cursor FOR-loop expanded; loop variables are NVARCHAR(4000) (exact column "
        "types need --db-url metadata).",
    ),
    "UNIQUE-1188": _D(
        "procedural",
        "SET TRANSACTION {mode} dropped -- T-SQL has no READ ONLY/READ WRITE "
        "transaction mode; only ISOLATION LEVEL is expressible (docs/03-unsupported.md",
    ),
    "UNIQUE-1189": _D(
        "procedural",
        "EXECUTE IMMEDIATE USING bindings dropped; inline them or use sp_executesql "
        "parameters",
    ),
    "UNIQUE-1190": _D("procedural", "verify dynamic SQL placeholders match …"),
    "UNIQUE-1191": _D(
        "procedural", "OUTPUT <expr> dropped — populate the temp table manually"
    ),
    "UNIQUE-1192": _D(
        "procedural",
        "ROW_COUNT() counts changed rows, not matched rows like the source "
        "(docs/03-unsupported.md",
    ),
    "UNIQUE-1193": _D("procedural", "… -- …-only, no … equivalent"),
    "UNIQUE-1194": _D("procedural", "{name} has no … equivalent; {hint}"),
    "UNIQUE-1195": _D(
        "procedural", "trigger function … inlined into its T-SQL trigger"
    ),
    "UNIQUE-1196": _D("procedural", "was T-SQL table variable {name}"),
    "UNIQUE-1197": _D(
        "procedural", "SET option is source-only and has no target equivalent"
    ),
    "UNIQUE-1198": _D(
        "procedural", "T-SQL system procedure has no … equivalent; original: EXEC …"
    ),
    "UNIQUE-1199": _D(
        "procedural", "T-SQL system procedure has no … equivalent; original: {original}"
    ),
    "UNIQUE-1200": _D(
        "procedural", "Oracle package call has no … equivalent; original"
    ),
    "UNIQUE-1201": _D(
        "procedural",
        "trigger uses the T-SQL set-based inserted/deleted pseudo-tables, which have "
        "no row-level (NEW/OLD) equivalent. Rewrite manually (PostgreSQL: a "
        "statement-level trigger with REFERENCING NEW TABLE AS inserted OLD TABLE AS "
        "deleted; Oracle: a compound trigger; MySQL: no transition tables). Original",
    ),
    "UNIQUE-1202": _D(
        "procedural",
        "statement uses a table-valued function in FROM, which MySQL does not support; "
        "commented out for review",
    ),
    "UNIQUE-1203": _D("procedural", "unmapped cursor attribute …%… */ (0 = 1"),
    "UNIQUE-1204": _D("procedural", "no MySQL equivalent: ALTER TRIGGER … …"),
    "UNIQUE-1205": _D("procedural", "was T-SQL temp table #{var}"),
    "UNIQUE-1206": _D(
        "procedural",
        "{word} dropped -- the exception-guarded block is a subtransaction "
        "(transaction control there is a runtime error); it rolls back on error and "
        "commits with the surrounding transaction",
    ),
    "UNIQUE-1207": _D(
        "orchestration",
        "approved value divergence (collation/encoding) kept with a warning; reason "
        "carried at runtime",
    ),
    "UNIQUE-1208": _D(
        "orchestration",
        "T-SQL CREATE SCHEMA has no Oracle equivalent — an Oracle schema is a database "
        "user. Create it manually, e.g. CREATE USER {name} …; original",
    ),
    "UNIQUE-1209": _D(
        "orchestration",
        "Oracle ORGANIZATION INDEX/HEAP is a physical-storage clause with no "
        "equivalent here; dropped.",
    ),
    "UNIQUE-1210": _D(
        "orchestration",
        "… -- tsql-only, no {target} equivalent (constraint check-state",
    ),
    "UNIQUE-1211": _D(
        "orchestration",
        "{sp} is a SQL Server system procedure with no {target} equivalent; original "
        "call omitted",
    ),
    "UNIQUE-1212": _D(
        "orchestration",
        "{target} has no standalone OUTPUT/RETURNING result set; the statement "
        "returned: {cols} (docs/03-unsupported.md",
    ),
    "UNIQUE-1213": _D(
        "orchestration", "T-SQL default constraint value has no {target} equivalent"
    ),
    "UNIQUE-1214": _D(
        "orchestration",
        "READ COMMITTED is Oracle's default isolation level (no-op; noted so a "
        "following SET TRANSACTION mode statement can still open the transaction",
    ),
    "UNIQUE-1215": _D(
        "orchestration",
        "T-SQL has no SET ROLE (use role membership / EXECUTE AS); statement preserved "
        "as a comment.",
    ),
    "UNIQUE-1216": _D(
        "orchestration",
        "{target} has no deferred-constraint toggling (SET CONSTRAINTS); statement "
        "preserved as a comment.",
    ),
    "UNIQUE-1217": _D(
        "orchestration",
        "SET SESSION AUTHORIZATION has no {target} equivalent; switch users natively.",
    ),
    "UNIQUE-1218": _D(
        "orchestration",
        "PostgreSQL session setting has no {target} equivalent; configure the session "
        "natively.",
    ),
    "UNIQUE-1219": _D(
        "orchestration",
        "MySQL session setting has no {target} equivalent; configure the session "
        "natively.",
    ),
    "UNIQUE-1220": _D(
        "orchestration",
        "live {target} validation rejected this statement ({first_err}); preserved as "
        "a comment",
    ),
    "UNIQUE-1221": _D(
        "orchestration",
        "T-SQL TEXTIMAGE_ON filegroup clause dropped (physical storage, no "
        "logical-schema impact)",
    ),
    "UNIQUE-1222": _D(
        "orchestration",
        "T-SQL WITH NOCHECK dropped; the constraint is added and the target validates "
        "existing rows (no NOVALIDATE applied)",
    ),
    "UNIQUE-1223": _D(
        "orchestration",
        "session/client directive commented out (no cross-engine equivalent); the "
        "directive is session-scoped and the specific statement is carried at runtime",
    ),
    "UNIQUE-1224": _D(
        "orchestration",
        "batch commented out (unrecognized migration-guard shape); the specific batch "
        "is carried at runtime",
    ),
    "UNIQUE-1225": _D(
        "statement",
        "existence guard dropped; the guarded statement now runs unconditionally (no "
        "conditional form on the target); the specific statement is carried at runtime",
    ),
    "UNIQUE-1226": _D(
        "statement",
        "guard ELSE branch dropped (only a diagnostic PRINT can be carried into the "
        "target conditional); the specific branch is carried at runtime",
    ),
    "UNIQUE-1227": _D(
        "ddl",
        "Oracle MODIFY keeps the column's current nullability; the redundant NULL is "
        "omitted (an explicit NULL raises ORA-01451 when the column is already "
        "nullable)",
    ),
    "UNIQUE-1228": _D(
        "validation",
        "internal: a parsed sqlglot construct was not consumed by the converter "
        "(unread arg) — the construct may be dropped; the specific arg is carried at "
        "runtime",
    ),
    "UNIQUE-1229": _D(
        "validation",
        "DML transpilation failed (internal error); the source statement is preserved "
        "as a comment; the error is carried at runtime",
    ),
    "UNIQUE-1230": _D(
        "procedural",
        "procedural parse note; the specific reason is carried at runtime",
    ),
    "UNIQUE-1231": _D(
        "procedural",
        "procedural transformation note; the specific reason is carried at runtime",
    ),
    "UNIQUE-1232": _D(
        "procedural",
        "procedural transpilation failed (internal error); the routine is preserved; "
        "the error is carried at runtime",
    ),
    "UNIQUE-1233": _D(
        "statement",
        "transaction closer preserved as a comment: its opener degraded to a "
        "parse-failure carrier, so shipping the COMMIT/ROLLBACK would orphan it "
        "(no open transaction — T-SQL error 3902)",
    ),
    "UNIQUE-1235": _D(
        "expression",
        "Oracle STANDARD_HASH(x, 'SHA1') (the default algorithm) has no "
        "core-PostgreSQL equivalent (needs the pgcrypto extension) — see "
        "docs/03-unsupported.md",
    ),
    "UNIQUE-1236": _D(
        "ddl",
        "{dialect} has no unbounded numeric type — column … (Oracle bare NUMBER) "
        "is bounded to DECIMAL(38, 10); values beyond that precision/scale are "
        "not representable (docs/03-unsupported.md",
    ),
}
