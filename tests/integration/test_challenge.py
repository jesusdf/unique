# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Regression guard over the curated ``tests/fixtures/challenge`` corpus.

Each challenge fixture holds anonymized tricky source constructs (one per
``-- CASE:`` entry) that the transpiler once handled wrong. Transpiling each
case to every other engine must not fall back to an *unrecognized-construct*
carrier (``UNIQUE: Unhandled`` / ``could not translate``) — a documented degrade
for an intrinsically unsupported feature is fine, an unhandled construct is not.
Plus per-case assertions that the specific fix holds.
"""

from __future__ import annotations

import pathlib
import re

import pytest

from tests.helpers.validity import assert_statements_parse
from unique.core.diagnostics import CODE_RE, is_registered
from unique.core.transpiler import Transpiler

_CHALLENGE_DIR = pathlib.Path(__file__).resolve().parents[1] / "fixtures" / "challenge"
_SOURCE_BY_FILE = {
    "challenge_sqlserver.sql": "tsql",
    "challenge_oracle.sql": "oracle",
    "challenge_postgresql.sql": "postgresql",
    "challenge_mysql.sql": "mysql",
}
_ALL_ENGINES = ("tsql", "oracle", "postgresql", "mysql")
# ``: Unhandled`` matches both the legacy ``UNIQUE: Unhandled`` and the coded
# ``UNIQUE-1144: Unhandled`` carrier (B32).
_UNRECOGNIZED_MARKERS = (": Unhandled", "could not translate")


def _read(fname: str) -> str:
    return (_CHALLENGE_DIR / fname).read_text(encoding="utf-8")


def _exec_lines(sql: str) -> str:
    return "\n".join(ln for ln in sql.splitlines() if not ln.lstrip().startswith("--"))


# A case is tagged ``-- CASE[fixed]:`` (BLUE faithfully corrected it — strictly
# guarded), ``-- CASE[open]:`` (RED found it, not yet fixed — backlog, only
# smoke-checked), or ``-- CASE[limit]:`` (a genuine no-statement-level-
# compensation divergence the human APPROVED as a documented limit — e.g.
# collation case/accent sensitivity, LENGTH bytes-vs-chars: it produces valid
# output with a different value, so it is neither a defect nor a faithful fix;
# it must cite docs/03-unsupported.md). An untagged ``-- CASE:`` is treated as
# fixed. "Corpus done" means zero ``[open]``.
_CASE_HEAD = r"-- CASE(?:\[(?:open|fixed|limit)\])?(?:\[class=[a-z-]+\])?:"


def _cases(fname: str) -> list[str]:
    """Split a fixture into its ``-- CASE:`` blocks (each self-contained)."""
    blocks = re.split(rf"(?m)^(?={_CASE_HEAD})", _read(fname))
    return [b.strip() for b in blocks if re.match(_CASE_HEAD, b.strip())]


def _status(block: str) -> str:
    m = re.match(r"-- CASE\[(open|fixed|limit)\](?:\[class=[a-z-]+\])?:", block.strip())
    return m.group(1) if m else "fixed"


def _case(fname: str, keyword: str) -> str:
    for block in _cases(fname):
        if keyword.lower() in block.splitlines()[0].lower():
            return block
    raise KeyError(f"no CASE matching {keyword!r} in {fname}")


def _tx(sql: str, source: str, target: str) -> str:
    return Transpiler().transpile(sql, source=source, target=target).sql


def _cases_by_status(want: str) -> list[tuple[str, str, int]]:
    out: list[tuple[str, str, int]] = []
    for fname, src in _SOURCE_BY_FILE.items():
        for i, block in enumerate(_cases(fname)):
            if _status(block) == want:
                out.append((fname, src, i))
    return out


def test_fixed_cases_have_no_unrecognized_construct() -> None:
    """A closed case must transpile to every engine without an unrecognized
    carrier (a documented degrade is fine, an Unhandled construct is not).

    Kept as ONE looping test (not parametrized per case): these generic guards
    check *absence* of a marker, so they pass under an identity transpiler and
    would otherwise dilute the identity-mutation gate as the corpus grows. The
    real assertion-quality lives in the specific ``[fixed]`` classes below."""
    failures: list[str] = []
    for fname, source, i in _cases_by_status("fixed"):
        sql = _cases(fname)[i]
        for target in _ALL_ENGINES:
            if target == source:
                continue
            out = _tx(sql, source, target)
            for marker in _UNRECOGNIZED_MARKERS:
                if marker in out:
                    failures.append(f"{fname}[{i}] -> {target}: {marker!r}")
    assert not failures, "unrecognized carrier on fixed cases:\n" + "\n".join(
        failures[:20]
    )


def test_open_cases_transpile_without_crashing() -> None:
    """OPEN (RED-found, unfixed) cases are the known-defect backlog — output is
    wrong on some target. We only assert the transpiler does not *crash*;
    correctness is BLUE's job (flip to ``[fixed]`` with a real assertion). ONE
    looping test on purpose (a no-crash smoke check passes under identity, so
    parametrizing it per case would swamp the identity-mutation gate). See
    tests/fixtures/challenge/FINDINGS.md."""
    for fname, source, i in _cases_by_status("open"):
        sql = _cases(fname)[i]
        for target in _ALL_ENGINES:
            if target == source:
                continue
            _tx(sql, source, target)  # must not raise


def test_limit_cases_warn_and_annotate_on_every_failing_target() -> None:
    """A ``[limit]`` case is a human-APPROVED divergence with no statement-level
    compensation (collation, LENGTH bytes-vs-chars). It must NEVER ship silently:
    on each target where the value diverges the transpiler must (1) emit a
    ``validity_gate``/warning AND (2) annotate the output with a ``UNIQUE:``
    comment naming the divergence, while keeping the SQL valid (no unrecognized
    carrier). The case comment must also cite ``03-unsupported`` for traceability.

    The divergent targets are read from the case's ``fails on <engines>`` note.
    """
    failures: list[str] = []
    for fname, source, i in _cases_by_status("limit"):
        block = _cases(fname)[i]
        head = block.splitlines()[0]
        if "03-unsupported" not in head.lower():
            failures.append(f"{fname}[{i}]: [limit] case must cite 03-unsupported")
        m = re.search(r"fails on ([^.—]+)", head)
        diverging = (
            {t.strip() for t in m.group(1).replace("sqlserver", "tsql").split(",")}
            if m
            else set()
        )
        for target in _ALL_ENGINES:
            if target == source or target not in diverging:
                continue
            result = Transpiler().transpile(block, source=source, target=target)
            if not result.warnings:
                failures.append(f"{fname}[{i}] -> {target}: no warning for a limit")
            codes = CODE_RE.findall(result.sql)
            if not codes or not all(is_registered(c) for c in codes):
                failures.append(
                    f"{fname}[{i}] -> {target}: no registered UNIQUE-NNNN annotation"
                )
            for marker in _UNRECOGNIZED_MARKERS:
                if marker in result.sql:
                    failures.append(f"{fname}[{i}] -> {target}: {marker!r}")
    assert not failures, "\n".join(failures[:20])


def _slug(block: str) -> str:
    """Stable id for a case = its ``xx-yyy`` header slug, else the head prose."""
    head = block.splitlines()[0]
    body = re.sub(r"^-- CASE(?:\[[a-z]+\])?(?:\[class=[a-z-]+\])?:\s*", "", head)
    m = re.match(r"([a-z0-9]+(?:-[a-z0-9]+)+)", body)
    return m.group(1) if m else re.sub(r"\s+", " ", body)[:60]


# T4 target-parse gate allowlist. Each ``(fixture, case-slug, target)`` here is a
# ``[fixed]`` case whose transpiled output is **valid, executable target SQL that
# sqlglot itself cannot parse** — a sqlglot parser gap, NOT a product defect. Each
# entry was resolved on principle by transpiling the case and EXECUTING the output
# on the live target engine (B17 follow-up (b), 2026-07-25): all four ran clean,
# so they are exempt-with-evidence, not xfailed debt. The comment on each entry
# carries that evidence (engine, date, what ran). The gate stays STRICT: an entry
# that starts parsing (sqlglot upgraded) fails so it gets removed, and an entry
# whose case disappears fails as stale. Because product ``src/`` is correct for
# all four, there is no ``XFAIL_TARGET_PARSE`` debt dict — it emptied when the last
# entry was verified valid and was deleted.
VALID_BUT_SQLGLOT_UNPARSEABLE: dict[tuple[str, str, str], str] = {
    ("challenge_sqlserver.sql", "ts-merge-full", "oracle"): (
        "VALID Oracle: the MERGE 'WHEN MATCHED THEN UPDATE SET ... DELETE WHERE' "
        "fold plus the follow-up anti-join DELETE. sqlglot's oracle parser "
        "rejects the 'DELETE WHERE' fold (Unexpected token). Live-verified "
        "2026-07-25 on Oracle 23ai Free (FREEPDB1): the CREATE TABLEs, the MERGE "
        "and the DELETE all executed clean."
    ),
    ("challenge_postgresql.sql", "pg-savepoint", "tsql"): (
        "VALID T-SQL: 'SAVE TRANSACTION sp' is the T-SQL savepoint spelling; "
        "sqlglot's tsql parser does not accept it (Unexpected token). "
        "Live-verified 2026-07-25 on SQL Server 2022 (master): BEGIN TRANSACTION "
        "/ SAVE TRANSACTION sp / ROLLBACK TRANSACTION sp / COMMIT all executed "
        "clean."
    ),
    ("challenge_mysql.sql", "my-json-build", "tsql"): (
        "VALID T-SQL: JSON_ARRAY/JSON_OBJECT with the 'NULL ON NULL' clause; "
        "sqlglot's tsql parser rejects 'NULL ON NULL' (Expecting )). "
        "Live-verified 2026-07-25 on SQL Server 2022 (master): the SELECT "
        "executed clean."
    ),
    ("challenge_mysql.sql", "my-set-transaction", "postgresql"): (
        "VALID PostgreSQL: 'BEGIN READ ONLY' is the transaction access-mode "
        "spelling; sqlglot's postgres parser rejects the access mode (Unexpected "
        "token). Live-verified 2026-07-25 on PostgreSQL 16 (unique): SET "
        "TRANSACTION ISOLATION LEVEL READ COMMITTED / BEGIN READ ONLY / COMMIT "
        "all executed clean."
    ),
    ("challenge_mysql.sql", "red2-my-invisible-column-drop", "oracle"): (
        "VALID Oracle: an INVISIBLE column ('b NUMBER(10) INVISIBLE', excluded "
        "from SELECT *) is Oracle 12c+ syntax that sqlglot's oracle parser "
        "rejects (Expecting )). Live-verified 2026-07-30 on Oracle 23ai Free "
        "(FREEPDB1): the CREATE TABLE executed clean and SELECT * returned only "
        "the visible column."
    ),
}


def _assert_target_parse_gate(fname: str, source: str) -> None:
    """Every ``[fixed]`` case in *fname* must transpile to each foreign target
    and have its output parse in that target dialect (sqlglot ``RAISE``).

    Uses ``assert_statements_parse``: it splits the output with the FE harness
    splitter and parses each statement in the target dialect, EXEMPTING batches
    the FE classifier marks PROCEDURAL (CREATE PROCEDURE / PL/SQL / DELIMITER
    bodies sqlglot cannot parse), COMMENT (whole-statement carrier degrades),
    EMPTY, and SET_OPTION. Cases whose valid output sqlglot cannot parse are
    parked in ``VALID_BUT_SQLGLOT_UNPARSEABLE`` (each live-verified on the target
    engine) and enforced strictly (a now-parsing or stale entry fails the gate).
    Kept as ONE loop per source engine (not per case) so the gate does not swell
    the identity-mutation denominator (challenge skill's CI gotcha)."""
    seen_allowed: set[tuple[str, str, str]] = set()
    unexpected_fail: list[str] = []
    resolved: list[str] = []
    for block in _cases(fname):
        if _status(block) != "fixed":
            continue
        slug = _slug(block)
        for target in _ALL_ENGINES:
            if target == source:
                continue
            key = (fname, slug, target)
            out = _tx(block, source, target)
            try:
                assert_statements_parse(out, target, context=f"{fname}:{slug}")
            except AssertionError as exc:
                if key in VALID_BUT_SQLGLOT_UNPARSEABLE:
                    seen_allowed.add(key)
                else:
                    unexpected_fail.append(f"{slug} -> {target}: {str(exc)[:200]}")
            else:
                if key in VALID_BUT_SQLGLOT_UNPARSEABLE:
                    resolved.append(f"{slug} -> {target}")
    stale = {k for k in VALID_BUT_SQLGLOT_UNPARSEABLE if k[0] == fname} - seen_allowed
    msgs: list[str] = []
    if unexpected_fail:
        msgs.append(
            "target-parse failures (fix the emission, or — if the output is valid "
            "target SQL sqlglot cannot parse — live-verify it and add a "
            "VALID_BUT_SQLGLOT_UNPARSEABLE entry with the evidence):\n  "
            + "\n  ".join(unexpected_fail)
        )
    if resolved:
        msgs.append(
            "VALID_BUT_SQLGLOT_UNPARSEABLE entries now parse (sqlglot upgraded) — "
            "delete them:\n  " + "\n  ".join(resolved)
        )
    if stale:
        msgs.append(
            "stale VALID_BUT_SQLGLOT_UNPARSEABLE entries (no matching case) — "
            "delete them:\n  " + "\n  ".join(str(k) for k in sorted(stale))
        )
    assert not msgs, "\n".join(msgs)


def test_fixed_outputs_parse_in_target_from_tsql() -> None:
    _assert_target_parse_gate("challenge_sqlserver.sql", "tsql")


def test_fixed_outputs_parse_in_target_from_oracle() -> None:
    _assert_target_parse_gate("challenge_oracle.sql", "oracle")


def test_fixed_outputs_parse_in_target_from_postgresql() -> None:
    _assert_target_parse_gate("challenge_postgresql.sql", "postgresql")


def test_fixed_outputs_parse_in_target_from_mysql() -> None:
    _assert_target_parse_gate("challenge_mysql.sql", "mysql")


class TestOracleSelfQualifiedParam:
    """``get_top_rows.row_limit`` (Oracle self-qualified parameter) resolves to
    the target variable and never leaks the ``<routine>.`` qualifier."""

    def _out(self, target: str) -> str:
        return _tx(_case("challenge_oracle.sql", "self-qualified"), "oracle", target)

    def test_tsql_resolves_to_at_variable(self) -> None:
        out = self._out("tsql")
        assert "SELECT TOP (@row_limit)" in out, out
        assert "get_top_rows." not in _exec_lines(out), out

    def test_mysql_resolves_to_bare_param(self) -> None:
        out = self._out("mysql")
        body = _exec_lines(out)
        assert "get_top_rows." not in body, out
        assert "LIMIT row_limit" in body, out


class TestTsqlCreateProcAbbreviation:
    """``CREATE PROC`` transpiles like ``CREATE PROCEDURE`` and never leaks the
    T-SQL-only ``PROC`` keyword to another engine."""

    @pytest.mark.parametrize("target", ("postgresql", "oracle", "mysql"))
    def test_proc_becomes_procedure(self, target: str) -> None:
        out = _tx(_case("challenge_sqlserver.sql", "PROC abbreviation"), "tsql", target)
        assert "PROCEDURE" in out.upper(), out
        assert not re.search(
            r"\bPROC\b(?!EDURE)", _exec_lines(out), re.IGNORECASE
        ), f"leaked PROC abbreviation ({target}):\n{out}"


class TestTsqlCreateOrAlter:
    """``CREATE OR ALTER`` (T-SQL 2016+) routes to the procedural engine and maps
    to the other engines' ``CREATE OR REPLACE`` — never an Unhandled carrier."""

    @pytest.mark.parametrize("target", ("postgresql", "oracle"))
    def test_maps_to_create_or_replace(self, target: str) -> None:
        out = _tx(_case("challenge_sqlserver.sql", "CREATE OR ALTER"), "tsql", target)
        assert "CREATE OR REPLACE PROCEDURE" in out, out
        assert not re.search(
            re.escape("UNIQUE") + r"(?:-\d{4})?" + re.escape(": Unhandled"), out
        ), out

    def test_tsql_roundtrip_preserves_or_alter(self) -> None:
        out = _tx(_case("challenge_sqlserver.sql", "CREATE OR ALTER"), "tsql", "tsql")
        assert "CREATE OR ALTER PROCEDURE" in out, out


class TestTrimCharacterSet:
    """``TRIM([BOTH|LEADING|TRAILING] chars FROM string)`` keeps its operands in
    order (a swap silently trimmed the wrong argument on every target) and, into
    Oracle, uses LTRIM/RTRIM so a multi-character set never hits ORA-30001."""

    def test_tsql_both_into_oracle_uses_ltrim_rtrim(self) -> None:
        out = _tx(_case("challenge_sqlserver.sql", "ts-trim-chars"), "tsql", "oracle")
        # set 'x' stripped from 'xxabcxx' — operands must not be swapped, and
        # Oracle must not receive TRIM(BOTH set FROM s) (ORA-30001 on >1 char).
        assert "LTRIM(RTRIM('xxabcxx', 'x'), 'x')" in out, out
        assert "TRIM(BOTH" not in out, out

    @pytest.mark.parametrize("target", ("postgresql", "mysql"))
    def test_tsql_both_keeps_operand_order(self, target: str) -> None:
        out = _tx(_case("challenge_sqlserver.sql", "ts-trim-chars"), "tsql", target)
        # 'x' is the trim set, 'xxabcxx' the string — the string follows FROM.
        assert "TRIM(BOTH 'x' FROM 'xxabcxx')" in out, out

    def test_mysql_leading_into_oracle_uses_ltrim(self) -> None:
        out = _tx(_case("challenge_mysql.sql", "my-trim-leading"), "mysql", "oracle")
        assert "LTRIM('007', '0')" in _exec_lines(out), out


class TestDateLiteralIntoOracle:
    """Date built-ins over ISO string literals emit the ANSI ``DATE '…'`` literal
    for Oracle/PG date math — Oracle can't implicitly convert an ISO string to a
    DATE (NLS_DATE_FORMAT, ORA-01861), and a bare CAST(str AS DATE) inherits it."""

    def test_datediff_into_oracle_uses_ansi_date_literal(self) -> None:
        out = _tx(_case("challenge_sqlserver.sql", "ts-datediff "), "tsql", "oracle")
        assert "DATE '2020-01-10'" in out and "DATE '2020-01-01'" in out, out
        # the raw string must not be handed to CAST(... AS DATE) unwrapped.
        assert "CAST('2020-01-10'" not in out, out

    @pytest.mark.parametrize("target", ("oracle", "postgresql"))
    def test_datediff_big_faithful(self, target: str) -> None:
        out = _tx(_case("challenge_sqlserver.sql", "ts-datediff-big"), "tsql", target)
        assert re.search(r"DATE '\d{4}-\d\d-\d\d'", out), out


class TestExtractFieldTranslation:
    """PG ``EXTRACT``/``DATE_PART`` fields the target's native EXTRACT/DATEPART
    either rejects (Oracle WEEK/QUARTER/DOW) or computes with different semantics
    (WEEK's numbering on MySQL/T-SQL, DOW on every engine). Each maps to a
    value-preserving, ISO-8601 / DATEFIRST- / NLS-independent equivalent
    (live-verified on all four engines: PG week=25 quarter=2, DOW=3)."""

    def test_week_quarter_into_oracle(self) -> None:
        out = _tx(
            _case("challenge_postgresql.sql", "pg-date-part "), "postgresql", "oracle"
        )
        assert "TO_NUMBER(TO_CHAR(DATE '2020-06-15', 'IW'))" in out, out
        assert "TO_NUMBER(TO_CHAR(DATE '2020-06-15', 'Q'))" in out, out
        # no invalid Oracle EXTRACT(WEEK/QUARTER) survives in the SQL itself.
        assert "EXTRACT(" not in _exec_lines(out), out

    def test_week_is_iso_on_mysql_and_tsql(self) -> None:
        my = _tx(
            _case("challenge_postgresql.sql", "pg-date-part "), "postgresql", "mysql"
        )
        assert "WEEK(CAST('2020-06-15' AS DATE), 3)" in my, my
        ts = _tx(
            _case("challenge_postgresql.sql", "pg-date-part "), "postgresql", "tsql"
        )
        assert "DATEPART(ISO_WEEK, CAST('2020-06-15' AS DATE))" in ts, ts

    @pytest.mark.parametrize(
        "target,expected",
        [
            ("mysql", "(DAYOFWEEK(CAST('2020-01-01' AS DATE)) - 1)"),
            (
                "oracle",
                "MOD(MOD(TRUNC(DATE '2020-01-01') - DATE '1970-01-04', 7) + 7, 7)",
            ),
            (
                "tsql",
                "(DATEDIFF(DAY, '19000107', CAST('2020-01-01' AS DATE)) % 7 + 7) % 7",
            ),
        ],
    )
    def test_dow_maps_per_engine(self, target: str, expected: str) -> None:
        out = _tx(
            _case("challenge_postgresql.sql", "pg-extract-dow "), "postgresql", target
        )
        assert expected in out, out

    @pytest.mark.parametrize(
        "case,mysql_expr,tsql_expr",
        [
            # ISO-week edge dates: same mechanism, verified values (PG 1/53/1).
            (
                "pg-week ",
                "WEEK(CAST('2020-01-05' AS DATE), 3)",
                "ISO_WEEK, CAST('2020-01-05'",
            ),
            (
                "pg-week-2016 ",
                "WEEK(CAST('2016-01-01' AS DATE), 3)",
                "ISO_WEEK, CAST('2016-01-01'",
            ),
            (
                "pg-week-jan1 ",
                "WEEK(CAST('2020-01-01' AS DATE), 3)",
                "ISO_WEEK, CAST('2020-01-01'",
            ),
        ],
    )
    def test_iso_week_edge_dates(
        self, case: str, mysql_expr: str, tsql_expr: str
    ) -> None:
        my = _tx(_case("challenge_postgresql.sql", case), "postgresql", "mysql")
        assert mysql_expr in my, my
        ts = _tx(_case("challenge_postgresql.sql", case), "postgresql", "tsql")
        assert tsql_expr in ts, ts


class TestMonthEndFunctions:
    """End-of-month built-ins (T-SQL EOMONTH, MySQL LAST_DAY) map to each
    engine's idiom and agree on the date (2020-02-29). Oracle's DATE type
    renders a 00:00:00 time component — same value, precision-only per the
    2026-07-19 maintainer policy (live-verified on all four engines)."""

    def test_eomonth_into_oracle_and_pg(self) -> None:
        o4 = _tx(_case("challenge_sqlserver.sql", "ts-eomonth "), "tsql", "oracle")
        assert "LAST_DAY(DATE '2020-02-15')" in o4, o4
        pg = _tx(_case("challenge_sqlserver.sql", "ts-eomonth "), "tsql", "postgresql")
        assert "DATE_TRUNC('month', DATE '2020-02-15')" in pg, pg

    def test_eomonth_nested_keeps_month_end(self) -> None:
        o4 = _tx(
            _case("challenge_sqlserver.sql", "ts-eomonth-nested "), "tsql", "oracle"
        )
        assert "ADD_MONTHS(LAST_DAY(DATE '2020-03-01'), -1)" in o4, o4

    def test_mysql_last_day_extract_day(self) -> None:
        ts = _tx(_case("challenge_mysql.sql", "my-lastday-extract "), "mysql", "tsql")
        assert "EOMONTH('2020-02-15')" in ts and "DATEPART(DAY, EOMONTH(" in ts, ts
        o4 = _tx(_case("challenge_mysql.sql", "my-lastday-extract "), "mysql", "oracle")
        assert "EXTRACT(DAY FROM LAST_DAY(DATE '2020-02-15'))" in o4, o4


class TestXmlElementBetweenOracleAndPg:
    """XMLELEMENT is faithful between Oracle and PostgreSQL: PG requires the
    ``NAME`` keyword, Oracle does not, and the element name is quoted on both so
    neither re-folds its case (a PG ``NAME foo`` must stay ``<foo>`` on Oracle,
    not ``<FOO>``). MySQL/T-SQL have no XMLELEMENT — a documented [limit].
    (Live-verified: all three cases return ``<foo>bar</foo>`` on Oracle and PG.)"""

    def test_oracle_source_into_pg_uses_name_keyword(self) -> None:
        pg = _tx(
            _case("challenge_oracle.sql", "ora-xmlelement "), "oracle", "postgresql"
        )
        assert 'XMLELEMENT(NAME "foo", ' in pg, pg

    def test_pg_source_into_oracle_quotes_name(self) -> None:
        # PG's unquoted ``NAME foo`` must become quoted ``"foo"`` on Oracle so it
        # is not upper-folded to FOO.
        o4 = _tx(
            _case("challenge_postgresql.sql", "pg-xmlelement "), "postgresql", "oracle"
        )
        assert 'XMLELEMENT("foo", ' in o4, o4
        assert "NAME" not in _exec_lines(o4), o4


class TestBitAggregatesBetweenMysqlAndPg:
    """BIT_AND/BIT_OR/BIT_XOR aggregates exist on both MySQL and PostgreSQL.
    sqlglot canonicalizes them to BitwiseAndAgg/… whose sql_name is not a real
    function, so the converter recovers the real name; otherwise the gate
    degraded valid MySQL/PG output. Oracle and T-SQL have no bit aggregate — a
    documented [limit]. (Live-verified: my-agg-bit = (0,7,0) on MySQL and PG.)"""

    def test_mysql_source_into_pg(self) -> None:
        pg = _tx(_case("challenge_mysql.sql", "my-agg-bit "), "mysql", "postgresql")
        assert "BIT_AND(x)" in pg and "BIT_OR(x)" in pg and "BIT_XOR(x)" in pg, pg

    def test_pg_source_into_mysql(self) -> None:
        my = _tx(
            _case("challenge_postgresql.sql", "po-agg-bit "), "postgresql", "mysql"
        )
        assert "BIT_AND(x)" in my and "BIT_OR(x)" in my and "BIT_XOR(x)" in my, my


class TestJsonAggregates:
    """JSON aggregates map faithfully across MySQL, PostgreSQL and Oracle (same
    JSON value): PG spells them json_agg / json_object_agg, MySQL/Oracle
    JSON_ARRAYAGG / JSON_OBJECTAGG (Oracle needs KEY..VALUE and a VARCHAR2 key).
    T-SQL has no JSON aggregate, so it degrades to a documented [limit].
    (Live-verified: my-json-agg = ([1,2], {"1":10,"2":20}) on all three.)"""

    def test_mysql_source_into_pg_and_oracle(self) -> None:
        pg = _tx(_case("challenge_mysql.sql", "my-json-agg "), "mysql", "postgresql")
        assert "JSON_AGG(x)" in pg and "JSON_OBJECT_AGG(" in pg, pg
        o4 = _tx(_case("challenge_mysql.sql", "my-json-agg "), "mysql", "oracle")
        assert "JSON_ARRAYAGG(x)" in o4, o4
        assert "VALUE" in o4 and "VARCHAR2" in o4, o4  # Oracle KEY..VALUE, VARCHAR2 key

    def test_pg_source_into_mysql(self) -> None:
        my = _tx(
            _case("challenge_postgresql.sql", "pg-json-aggs "), "postgresql", "mysql"
        )
        assert "JSON_ARRAYAGG(x)" in my and "JSON_OBJECTAGG(" in my, my

    def test_tsql_degrades(self) -> None:
        r = Transpiler().transpile(
            _case("challenge_mysql.sql", "my-json-agg "), source="mysql", target="tsql"
        )
        assert r.warnings and "UNIQUE-1151:" in r.sql, r.sql


class TestAlterModifyColumn:
    """MySQL ALTER TABLE … MODIFY COLUMN c <type> (a column type change) spells
    differently per engine: Oracle MODIFY c, PostgreSQL ALTER COLUMN c TYPE,
    T-SQL ALTER COLUMN c — with the type ported (BIGINT -> Oracle NUMBER).
    sqlglot passes MODIFY COLUMN through unchanged, so it is rewritten here."""

    def _out(self, target: str) -> str:
        return _tx(_case("challenge_mysql.sql", "my-alter-modify "), "mysql", target)

    def test_oracle_modify(self) -> None:
        assert "MODIFY b NUMBER" in self._out("oracle"), self._out("oracle")

    def test_pg_alter_column_type(self) -> None:
        assert "ALTER COLUMN b TYPE BIGINT" in self._out("postgresql")

    def test_tsql_alter_column(self) -> None:
        body = "\n".join(
            ln
            for ln in self._out("tsql").splitlines()
            if not ln.lstrip().startswith("--")
        )
        assert "ALTER COLUMN b BIGINT" in body and "MODIFY" not in body, body


class TestAlterChangeColumn:
    """MySQL ALTER TABLE t CHANGE a x <type> renames AND retypes in one
    statement; it splits into a rename + a type change per engine (Oracle/PG
    RENAME COLUMN, T-SQL EXEC sp_rename), the column being `x` afterward."""

    def _out(self, target: str) -> str:
        return _tx(_case("challenge_mysql.sql", "my-change-column "), "mysql", target)

    def test_oracle_rename_then_modify(self) -> None:
        out = self._out("oracle")
        assert "RENAME COLUMN a TO x" in out and "MODIFY x NUMBER" in out, out

    def test_tsql_sp_rename_then_alter(self) -> None:
        out = self._out("tsql")
        assert "sp_rename 't.a', 'x', 'COLUMN'" in out, out
        assert "ALTER COLUMN x INT" in out, out


class TestAlterSetDefault:
    """MySQL ALTER COLUMN c SET DEFAULT v maps to Oracle MODIFY c DEFAULT v and
    T-SQL ADD CONSTRAINT DF_<t>_<c> DEFAULT v FOR c (a named default
    constraint); PostgreSQL keeps the SET DEFAULT spelling."""

    def _out(self, target: str) -> str:
        return _tx(
            _case("challenge_mysql.sql", "my-alter-set-default "), "mysql", target
        )

    def test_oracle_modify_default(self) -> None:
        assert "MODIFY a DEFAULT 5" in self._out("oracle"), self._out("oracle")

    def test_tsql_named_default_constraint(self) -> None:
        assert "ADD CONSTRAINT DF_t_a DEFAULT 5 FOR a" in self._out("tsql")

    def test_pg_source_set_default(self) -> None:
        out = _tx(
            _case("challenge_postgresql.sql", "pg-set-default "), "postgresql", "oracle"
        )
        assert "MODIFY a DEFAULT 5" in out, out


class TestAlterSuiteBatches:
    """Full ALTER batches: T-SQL SET DEFAULT replaces (drops the current default
    constraint first, error 1781 otherwise) and DROP COLUMN pre-drops the
    dependent default constraint (error 5074 otherwise). Whole batches
    live-verified on Oracle + T-SQL."""

    def test_pg_suite_tsql_set_default_replaces(self) -> None:
        out = _tx(
            _case("challenge_postgresql.sql", "pg-alter-suite "), "postgresql", "tsql"
        )
        assert (
            out.count("sys.default_constraints") >= 2
        ), out  # SET DEFAULT + DROP COLUMN
        assert "ADD CONSTRAINT DF_t_name DEFAULT 'x' FOR name" in out, out

    def test_ora_suite_tsql_drop_column_predrops(self) -> None:
        out = _tx(_case("challenge_oracle.sql", "ora-alter-suite "), "oracle", "tsql")
        assert "sys.default_constraints" in out and "DROP COLUMN nm" in out, out


class TestWindowedStringAgg:
    """Oracle windowed LISTAGG (string aggregation OVER a partition) has no
    portable equivalent — T-SQL/MySQL can't window a string-agg at all and PG
    can't window an ORDER-BY'd one; it degrades to NULL + carrier + warning. A
    plain windowed numeric aggregate and a non-ordered STRING_AGG OVER on PG are
    left untouched."""

    def test_listagg_over_degrades(self) -> None:
        case = _case("challenge_oracle.sql", "ora-listagg-over ")
        for target in ("postgresql", "tsql", "mysql"):
            result = Transpiler().transpile(case, source="oracle", target=target)
            assert result.warnings and "UNIQUE-1076:" in result.sql, target
            # No executable window clause survives. The carrier comment mentions
            # "OVER …" as prose; the source ``--`` header also names OVER(...) — so
            # strip ``--`` lines and check for the "OVER (" call form only.
            body = "\n".join(
                ln for ln in result.sql.splitlines() if not ln.lstrip().startswith("--")
            )
            assert "OVER (" not in body, body

    def test_plain_window_untouched(self) -> None:
        out = _tx(
            "SELECT SUM(x) OVER (PARTITION BY d) AS r FROM t;", "postgresql", "tsql"
        )
        assert "SUM(x) OVER" in out and "UNIQUE-" not in out, out


class TestForXml:
    """T-SQL FOR XML/JSON serializes a row set to a single scalar; no other engine
    has an equivalent, so a (SELECT … FOR XML) scalar subquery degrades to NULL +
    carrier + warning (rather than shipping the multi-column rows raw)."""

    def test_for_xml_scalar_degrades(self) -> None:
        case = _case("challenge_sqlserver.sql", "ts-for-xml ")
        for target in ("mysql", "oracle", "postgresql"):
            result = Transpiler().transpile(case, source="tsql", target=target)
            assert result.warnings and "UNIQUE-1071:" in result.sql, target
            # Both the source ``--`` header and the ``/* … */`` carrier name
            # "FOR XML" as prose; strip comment lines then the carrier, and check
            # the remaining executable text has no live FOR XML clause.
            body = "\n".join(
                ln for ln in result.sql.splitlines() if not ln.lstrip().startswith("--")
            )
            executable = body.split("/*")[0]
            assert (
                "NULL" in executable and "FOR XML" not in executable.upper()
            ), result.sql


class TestMysqlCastJson:
    """MySQL's JSON type has no faithful cross-engine cast (T-SQL has none;
    canonical JSON spacing differs on PG/Oracle), so a CAST to JSON keeps the
    source value as text + carrier + warning."""

    def test_cast_json_degrades(self) -> None:
        case = _case("challenge_mysql.sql", "my-cast-json ")
        for target in ("oracle", "tsql", "postgresql"):
            result = Transpiler().transpile(case, source="mysql", target=target)
            assert result.warnings and "UNIQUE-1066:" in result.sql, target
            body = "\n".join(
                ln for ln in result.sql.splitlines() if not ln.lstrip().startswith("--")
            )
            assert "AS JSON" not in body.upper().split("/*")[0], body


class TestMysqlUpdateXml:
    """MySQL UpdateXML (node-replacement XML DML) has no cross-engine equivalent
    and degrades to NULL + carrier + warning; ExtractValue in the same statement
    still translates per engine, and the whole statement stays valid."""

    def test_updatexml_degrades_extractvalue_kept(self) -> None:
        case = _case("challenge_mysql.sql", "my-xml-fns ")
        for target in ("oracle", "postgresql", "tsql"):
            result = Transpiler().transpile(case, source="mysql", target=target)
            assert result.warnings and "UNIQUE-1088:" in result.sql, target
            body = "\n".join(
                ln for ln in result.sql.splitlines() if not ln.lstrip().startswith("--")
            )
            assert "UPDATEXML(" not in body.upper(), body
            # ExtractValue still translated (no raw MySQL ExtractValue leaks).
            assert "XMLTYPE" in body or "XPATH" in body or ".value(" in body, body


class TestMysqlLenientDecimalCast:
    """MySQL casts a string to a number leniently — a non-numeric string yields 0
    (CAST('abc' AS DECIMAL) = 0), where the other engines error. The literal is
    folded to its MySQL-parsed value, and a bare DECIMAL keeps MySQL's scale-0
    default. Live-verified 13/13/0."""

    def test_nonnumeric_string_folds_to_zero(self) -> None:
        case = _case("challenge_mysql.sql", "my-cast-decimal2 ")
        for target in ("oracle", "tsql"):
            assert "CAST(0 AS DECIMAL(10, 0))" in _tx(case, "mysql", target)
        # PG's bare DECIMAL is arbitrary-precision — no scale forced.
        assert "CAST(0 AS DECIMAL)" in _tx(case, "mysql", "postgresql")

    def test_valid_numeric_string_preserved(self) -> None:
        case = _case("challenge_mysql.sql", "my-cast-decimal2 ")
        assert "CAST(12.99 AS DECIMAL(4, 1))" in _tx(case, "mysql", "tsql")


class TestFormatFunc:
    """PG printf-style format() has no cross-engine equivalent (T-SQL/MySQL FORMAT
    is a value formatter). A %s-only template rewrites to concatenation (Oracle
    ||, T-SQL/MySQL CONCAT); complex specs (%I/%L/width) degrade. Live 'a=1'."""

    def test_percent_s_concatenation(self) -> None:
        case = _case("challenge_postgresql.sql", "pg-format-func ")
        assert "'a' || '=' || 1" in _tx(case, "postgresql", "oracle")
        assert "CONCAT('a', '=', 1)" in _tx(case, "postgresql", "tsql")
        assert "CONCAT('a', '=', 1)" in _tx(case, "postgresql", "mysql")

    def test_identifier_spec_quotes(self) -> None:
        # %I now renders the argument as a quoted identifier per target.
        out = _tx("SELECT format('%I', 'tbl') AS r;", "postgresql", "tsql")
        assert "QUOTENAME('tbl')" in out, out

    def test_complex_spec_degrades(self) -> None:
        result = Transpiler().transpile(
            "SELECT format('%L', 'v') AS r;", source="postgresql", target="tsql"
        )
        assert result.warnings and "UNIQUE-1098:" in result.sql


class TestOracleTwoArgReplaceTranslate:
    """Oracle 2-arg REPLACE(s, search) removes all matches and returns NULL when
    the result is empty; it becomes NULLIF(REPLACE(s, search, ''), '') so PG/
    T-SQL/MySQL match. TRANSLATE is native on PG/T-SQL but MySQL has none, so it
    degrades there (a documented limit). Live-verified NULL / 'abc45'."""

    def test_two_arg_replace_rewrite(self) -> None:
        case = _case("challenge_oracle.sql", "ora-translate3 ")
        for target in ("postgresql", "tsql"):
            out = _tx(case, "oracle", target)
            assert "NULLIF(REPLACE('aaa', 'a', ''), '')" in out, out
            assert "TRANSLATE('12345', '123', 'abc')" in out, out

    def test_mysql_translate_degrades(self) -> None:
        case = _case("challenge_oracle.sql", "ora-translate3 ")
        result = Transpiler().transpile(case, source="oracle", target="mysql")
        assert result.warnings and "UNIQUE-1091:" in result.sql
        body = "\n".join(
            ln for ln in result.sql.splitlines() if not ln.lstrip().startswith("--")
        )
        assert "TRANSLATE(" not in body.upper(), body


class TestCastPointGeometric:
    """PG's geometric ``point`` type has no cross-engine equivalent; a cast to it
    degrades to the source's text value plus a carrier + warning. The kept text
    ('(1,2)') happens to equal PG's own text rendering of the point."""

    def test_point_kept_as_text(self) -> None:
        case = _case("challenge_postgresql.sql", "pg-cast-point ")
        for target in ("oracle", "tsql"):
            result = Transpiler().transpile(case, source="postgresql", target=target)
            assert result.warnings and "UNIQUE-1067:" in result.sql
            body = "\n".join(
                ln for ln in result.sql.splitlines() if not ln.lstrip().startswith("--")
            )
            assert "'(1,2)'" in body and "AS POINT" not in body.upper(), body


class TestTryCast:
    """TRY_CAST/TRY_CONVERT (a cast that yields NULL on a conversion error) is
    carried via the CastExpression ``safe`` flag: Oracle DEFAULT NULL ON
    CONVERSION ERROR, T-SQL native TRY_CAST, and PG/MySQL resolve a
    non-convertible literal to NULL at transpile time (they constant-fold a CASE
    guard). Live-verified NULL."""

    def test_try_convert_int(self) -> None:
        case = _case("challenge_sqlserver.sql", "ts-try-convert ")
        assert "CAST('abc' AS INT DEFAULT NULL ON CONVERSION ERROR)" in _tx(
            case, "tsql", "oracle"
        )
        body = "\n".join(
            ln
            for ln in _tx(case, "tsql", "postgresql").splitlines()
            if not ln.lstrip().startswith("--")
        )
        assert "SELECT NULL" in body, body


class TestUnpivot:
    """UNPIVOT (T-SQL/Oracle only) is rewritten to a UNION ALL — one arm per
    unpivoted column, carrying the source's other columns and excluding NULLs to
    match UNPIVOT's default. The name-column *value* is an explicit literal cased
    as the source engine produces it (Oracle upper-cases an unquoted identifier,
    so its UNPIVOT yields 'A' where T-SQL yields 'a'). Live-verified equal on all
    targets."""

    def test_tsql_source_lowercase_names(self) -> None:
        case = _case("challenge_sqlserver.sql", "ts-unpivot ")
        for target in ("oracle", "postgresql", "mysql"):
            out = _tx(case, "tsql", target)
            body = "\n".join(
                ln for ln in out.splitlines() if not ln.lstrip().startswith("--")
            )
            assert "UNION ALL" in body and "UNPIVOT" not in body.upper(), body
            assert "'a' AS col" in body and "'b' AS col" in body, body
            assert "a IS NOT NULL" in body, body

    def test_oracle_source_uppercases_name_value(self) -> None:
        case = _case("challenge_oracle.sql", "ora-unpivot ")
        for target in ("tsql", "postgresql", "mysql"):
            out = _tx(case, "oracle", target)
            assert "UNION ALL" in out, out
            # Oracle folds the unquoted identifier, so the value is upper-cased.
            assert "'A' AS col" in out and "'B' AS col" in out, out


class TestSubstringRegex:
    """PG SUBSTRING(x FROM POSIX pattern) extracts the first regex match. Oracle
    and MySQL have REGEXP_SUBSTR (live-verified '1'); T-SQL has no POSIX regex
    engine, so it degrades to NULL + carrier + warning (a documented limit)."""

    def test_oracle_mysql_regexp_substr(self) -> None:
        case = _case("challenge_postgresql.sql", "pg-substring-regex ")
        for target in ("oracle", "mysql"):
            assert "REGEXP_SUBSTR('a1b2', '[0-9]+')" in _tx(case, "postgresql", target)

    def test_tsql_degrades(self) -> None:
        case = _case("challenge_postgresql.sql", "pg-substring-regex ")
        result = Transpiler().transpile(case, source="postgresql", target="tsql")
        assert result.warnings and "UNIQUE-1092:" in result.sql
        body = "\n".join(
            ln for ln in result.sql.splitlines() if not ln.lstrip().startswith("--")
        )
        assert "REGEXP_SUBSTR" not in body and "NULL" in body, body


class TestSubstringSimilarToEscape:
    """PG SUBSTRING(x FROM pattern FOR escape) is the SQL-standard SIMILAR TO
    regex form (string pattern + string escape); its metacharacters differ from
    POSIX, so it degrades to NULL + carrier + warning off PG (a documented
    limit)."""

    def test_degrades_off_pg(self) -> None:
        case = _case("challenge_postgresql.sql", "pg-substring-escape ")
        for target in ("oracle", "tsql"):
            result = Transpiler().transpile(case, source="postgresql", target=target)
            assert result.warnings and "UNIQUE-1093:" in result.sql
            body = "\n".join(
                ln for ln in result.sql.splitlines() if not ln.lstrip().startswith("--")
            )
            assert "NULL" in body and "REGEXP" not in body, body


class TestRegexpReplaceFlags:
    """PG regexp_replace's 4th arg is a FLAGS string (g/i); Oracle/MySQL take
    numeric position/occurrence and are global by default. Drop 'g', and for
    MySQL double the pattern backslashes and spell backrefs $N. Live-verified
    'a[1]b[2]'."""

    def test_global_backref(self) -> None:
        case = _case("challenge_postgresql.sql", "pg-regexp-backref ")
        ora = _tx(case, "postgresql", "oracle")
        assert r"REGEXP_REPLACE('a1b2', '(\d)', '[\1]')" in ora, ora
        my = _tx(case, "postgresql", "mysql")
        assert r"REGEXP_REPLACE('a1b2', '(\\d)', '[$1]')" in my, my
        # The 'g' flag must not leak as a positional argument (ignore header prose).
        for out in (ora, my):
            body = "\n".join(
                ln for ln in out.splitlines() if not ln.lstrip().startswith("--")
            )
            assert "'g'" not in body, body


class TestTextCastTarget:
    """A CAST to text (PG's ``::text``) lands on CLOB (Oracle) / TEXT (T-SQL),
    neither a legal CAST target; both remap to a castable large-string type so a
    chained ``123::text::int`` round-trips to 123."""

    def test_intermediate_text_cast(self) -> None:
        case = _case("challenge_postgresql.sql", "pg-double-cast ")
        assert "VARCHAR2(4000)" in _tx(case, "postgresql", "oracle")
        assert "VARCHAR(MAX)" in _tx(case, "postgresql", "tsql")
        for target in ("oracle", "tsql"):
            body = "\n".join(
                ln
                for ln in _tx(case, "postgresql", target).splitlines()
                if not ln.lstrip().startswith("--")
            )
            assert "CLOB" not in body and "AS TEXT" not in body.upper(), body


class TestOverlay:
    """OVERLAY(s PLACING r FROM start FOR len) — replace len chars of s at start
    with r — is PG-native only. Rewritten to T-SQL STUFF, MySQL INSERT() (both
    the same 1-based shape) and an Oracle SUBSTR concat. Live-verified 'aXYdef'."""

    def test_overlay_rewrite(self) -> None:
        case = _case("challenge_postgresql.sql", "pg-overlay ")
        assert "STUFF('abcdef', 2, 2, 'XY')" in _tx(case, "postgresql", "tsql")
        assert "INSERT('abcdef', 2, 2, 'XY')" in _tx(case, "postgresql", "mysql")
        ora = _tx(case, "postgresql", "oracle")
        assert "SUBSTR('abcdef', 1, (2) - 1)" in ora and "|| 'XY' ||" in ora, ora


class TestAtTimeZone:
    """AT TIME ZONE is not portable (Oracle/MySQL lack the operator; PG↔T-SQL
    semantics and session-tz display differ), so it degrades to NULL + carrier +
    warning off its own dialect and stays verbatim on it."""

    def test_pg_source_degrades(self) -> None:
        case = _case("challenge_postgresql.sql", "pg-at-time-zone ")
        for target in ("oracle", "tsql", "mysql"):
            result = Transpiler().transpile(case, source="postgresql", target=target)
            assert result.warnings and "UNIQUE-1063:" in result.sql, target
            # Both the -- header and the /* carrier */ name "AT TIME ZONE"; strip
            # comment lines then the carrier and check the executable text.
            body = "\n".join(
                ln for ln in result.sql.splitlines() if not ln.lstrip().startswith("--")
            )
            assert "AT TIME ZONE" not in body.split("/*")[0].upper(), result.sql

    def test_verbatim_on_own_dialect(self) -> None:
        case = _case("challenge_postgresql.sql", "pg-at-time-zone ")
        out = _tx(case, "postgresql", "postgresql")
        assert "AT TIME ZONE 'UTC'" in out and "UNIQUE-" not in out, out


class TestGenerateSeriesFrom:
    """PG FROM generate_series(start, stop[, step]) as a relation is rewritten to
    Oracle CONNECT BY and a T-SQL numbers source (sys.all_objects + ROW_NUMBER);
    the correlation alias doubles as the value column, WITH ORDINALITY adds the
    row index. Live-verified rows."""

    def test_srf_in_from(self) -> None:
        case = _case("challenge_postgresql.sql", "pg-srf-in-select ")
        ora = _tx(case, "postgresql", "oracle")
        assert "CONNECT BY LEVEL <=" in ora and "AS g FROM DUAL" in ora, ora
        tsql = _tx(case, "postgresql", "tsql")
        assert "sys.all_objects" in tsql and "ROW_NUMBER()" in tsql, tsql

    def test_ordinality_step_tsql(self) -> None:
        case = _case("challenge_postgresql.sql", "pg-gen-series-ord ")
        out = _tx(case, "postgresql", "tsql")
        assert "sys.all_objects" in out and "AS v" in out and "AS n" in out, out
        body = "\n".join(
            ln for ln in out.splitlines() if not ln.lstrip().startswith("--")
        )
        assert "ORDINALITY" not in body.upper(), body

    def test_date_range_series(self) -> None:
        case = _case("challenge_postgresql.sql", "pg-gen-series-date ")
        ora = _tx(case, "postgresql", "oracle")
        assert "CONNECT BY LEVEL <=" in ora and "DATE '2020-01-01'" in ora, ora
        tsql = _tx(case, "postgresql", "tsql")
        assert "DATEADD(DAY," in tsql and "sys.all_objects" in tsql, tsql

    def test_srf_in_select_list_moved_to_from(self) -> None:
        case = _case("challenge_postgresql.sql", "pg-generate-series ")
        # SELECT-list generate_series is moved to FROM and rewritten.
        assert "CONNECT BY LEVEL <=" in _tx(case, "postgresql", "oracle")
        assert "sys.all_objects" in _tx(case, "postgresql", "tsql")
        # MySQL has no inline table function → documented degrade.
        result = Transpiler().transpile(case, source="postgresql", target="mysql")
        assert result.warnings and "UNIQUE-1003:" in result.sql


class TestGroupingCube:
    """GROUPING(x) over GROUP BY CUBE renders natively on Oracle/T-SQL. MySQL has
    no CUBE — it degrades to the base grouping (subtotal rows omitted) where
    GROUPING is always 0, kept valid with the CUBE degrade's warning."""

    def test_grouping_native_oracle_tsql(self) -> None:
        case = _case("challenge_postgresql.sql", "pg-grouping-fn ")
        for target in ("oracle", "tsql"):
            out = _tx(case, "postgresql", target)
            assert "GROUPING(x)" in out and "CUBE(x)" in out, out

    def test_grouping_folds_to_zero_on_mysql(self) -> None:
        case = _case("challenge_postgresql.sql", "pg-grouping-fn ")
        result = Transpiler().transpile(case, source="postgresql", target="mysql")
        assert result.warnings and "UNIQUE-1016:" in result.sql
        body = "\n".join(
            ln for ln in result.sql.splitlines() if not ln.lstrip().startswith("--")
        )
        assert "GROUPING" not in body.upper(), body


class TestTsqlScalarFunctionTrailingReturn:
    """A T-SQL scalar function's last statement must be a RETURN (error 455); a
    body ending in an all-branches-return IF/ELSE now gets an unreachable trailing
    RETURN NULL. Live-verified: f(1)='one', recursive f(5)=120."""

    def test_case_and_recursive_get_trailing_return(self) -> None:
        for fname, src, cid in (
            ("challenge_postgresql.sql", "postgresql", "pg-case-statement "),
            ("challenge_oracle.sql", "oracle", "ora-recursive-func "),
        ):
            out = _tx(_case(fname, cid), src, "tsql")
            # The final executable line before END is a RETURN.
            lines = [
                ln.strip()
                for ln in out.splitlines()
                if ln.strip() and not ln.lstrip().startswith("--")
            ]
            assert lines[-1] == "END" and lines[-2].upper().startswith("RETURN"), out


class TestFunctionSideEffectDegrade:
    """A T-SQL scalar function forbids TRY/CATCH, PRINT and RAISERROR (error 443),
    so a PG EXCEPTION handler or RAISE NOTICE has no function-level equivalent and
    the whole function degrades to a carrier. Named exceptions map on Oracle
    (division_by_zero -> ZERO_DIVIDE)."""

    def test_exception_function_degrades_on_tsql(self) -> None:
        for cid in (
            "pg-named-exception ",
            "pg-loop-notice ",
            "pg-exception-handler ",
        ):
            result = Transpiler().transpile(
                _case("challenge_postgresql.sql", cid),
                source="postgresql",
                target="tsql",
            )
            assert result.warnings and "UNIQUE-1171:" in result.sql, cid
            body = "\n".join(
                ln for ln in result.sql.splitlines() if not ln.lstrip().startswith("--")
            )
            assert "BEGIN TRY" not in body.upper(), body

    def test_named_exception_maps_on_oracle(self) -> None:
        out = _tx(
            _case("challenge_postgresql.sql", "pg-named-exception "),
            "postgresql",
            "oracle",
        )
        body = "\n".join(
            ln for ln in out.splitlines() if not ln.lstrip().startswith("--")
        )
        assert "ZERO_DIVIDE" in body and "division_by_zero" not in body.lower(), body


class TestBareThrowReraise:
    """A bare ``THROW;`` (re-raise inside a CATCH) was parsed with an empty
    message and shipped RAISE_APPLICATION_ERROR(-20001, ) on Oracle (PLS-00103);
    it now maps to the native re-raise (Oracle RAISE;, PG/MySQL equivalents)."""

    def test_bare_throw_becomes_raise(self) -> None:
        out = _tx(
            _case("challenge_sqlserver.sql", "ts-realworld-audit "), "tsql", "oracle"
        )
        body = "\n".join(
            ln for ln in out.splitlines() if not ln.lstrip().startswith("--")
        )
        assert "RAISE;" in body, body
        assert "RAISE_APPLICATION_ERROR(-20001, )" not in body, body


class TestVoidFunctionExecuteUsing:
    """A PG RETURNS VOID function is semantically a PROCEDURE; MySQL forbids
    dynamic SQL in a function (1336) but allows it in a procedure, so the void
    function is emitted as a PROCEDURE (and PG's $N placeholder becomes ?)."""

    def test_void_dynamic_sql_becomes_procedure(self) -> None:
        out = _tx(
            _case("challenge_postgresql.sql", "pg-execute-using "),
            "postgresql",
            "mysql",
        )
        assert "CREATE PROCEDURE f" in out, out
        body = "\n".join(
            ln for ln in out.splitlines() if not ln.lstrip().startswith("--")
        )
        assert "$1" not in body and "VALUES (?)" in body, body


class TestScrollCursorFetch:
    """A scroll cursor FETCH (PRIOR/FIRST/LAST/ABSOLUTE/RELATIVE) has no
    cross-engine equivalent — Oracle/PG/MySQL cursors are forward-only — so it
    degrades to a carrier while the OPEN/CLOSE still compile."""

    def test_scroll_fetch_degrades(self) -> None:
        case = _case("challenge_sqlserver.sql", "ts-scroll-cursor ")
        for target in ("oracle", "postgresql", "mysql"):
            result = Transpiler().transpile(case, source="tsql", target=target)
            assert result.warnings and "UNIQUE-1171:" in result.sql, target
            body = "\n".join(
                ln for ln in result.sql.splitlines() if not ln.lstrip().startswith("--")
            )
            assert "FETCH" not in body.upper(), body


class TestDynamicSqlHoist:
    """T-SQL sp_executesql needs its statement as a variable/literal, not a
    concat expression ('...' + @t is a syntax error near '+'); a compound dynamic
    SQL string is hoisted into a local first."""

    def test_concat_dynamic_sql_hoisted(self) -> None:
        out = _tx(_case("challenge_oracle.sql", "ora-dyn-count "), "oracle", "tsql")
        assert "DECLARE @_dyn_sql_1 NVARCHAR(MAX) =" in out, out
        assert "EXEC sp_executesql @_dyn_sql_1" in out, out


class TestEmptyGuardIfBody:
    """A FROM DUAL cursor FOR-loop maps to a T-SQL guard IF; a no-op (NULL-only)
    body would leave an empty BEGIN..END (error 156), so it gets a side-effect-
    free DECLARE no-op."""

    def test_empty_loop_body_gets_noop(self) -> None:
        out = _tx(
            _case("challenge_oracle.sql", "ora-cursor-for-loop "), "oracle", "tsql"
        )
        body = "\n".join(
            ln for ln in out.splitlines() if not ln.lstrip().startswith("--")
        )
        assert "IF (1 = 1)" in body and "DECLARE @uq_noop" in body, body
        assert "FROM DUAL" not in body.upper(), body


class TestMysqlCursorDeclOrder:
    """MySQL requires DECLARE <variable> before DECLARE <cursor> (error 1337);
    the leading declaration block is reordered (variables first, then cursors)."""

    def test_variable_before_cursor(self) -> None:
        out = _tx(_case("challenge_oracle.sql", "ora-cursor "), "oracle", "mysql")
        decls = [
            ln.strip()
            for ln in out.splitlines()
            if "DECLARE" in ln and not ln.lstrip().startswith("--")
        ]
        var_i = next(i for i, d in enumerate(decls) if "CURSOR" not in d.upper())
        cur_i = next(i for i, d in enumerate(decls) if "CURSOR" in d.upper())
        assert var_i < cur_i, decls


class TestMysqlValuesConstructorInProc:
    """MySQL's table value constructor needs ROW() per row — a procedural
    ``SELECT COUNT(*) FROM (VALUES (1),(2)) v(x)`` was a 1064 (VALUES (1),(2));
    it now emits ``VALUES ROW(1), ROW(2)``. Compile-verified on all engines."""

    def test_values_gets_row_wrapper(self) -> None:
        out = _tx(_case("challenge_sqlserver.sql", "ts-while-loop "), "tsql", "mysql")
        body = "\n".join(
            ln for ln in out.splitlines() if not ln.lstrip().startswith("--")
        )
        nospace = body.replace(" ", "")
        assert "VALUESROW(" in nospace, body
        assert "VALUES(1)" not in nospace, body


class TestVoidFunctionToProcedure:
    """A PG function with only OUT params and no RETURNS returns void; on Oracle a
    FUNCTION must RETURN a type (RETURN void = PLS-00201), so it emits a
    PROCEDURE. Live-verified valid + f(5) -> (5, 10)."""

    def test_void_out_function_becomes_oracle_procedure(self) -> None:
        case = _case("challenge_postgresql.sql", "pg-multi-out ")
        out = _tx(case, "postgresql", "oracle")
        assert "CREATE OR REPLACE PROCEDURE f" in out, out
        body = "\n".join(
            ln for ln in out.splitlines() if not ln.lstrip().startswith("--")
        )
        assert "VOID" not in body.upper(), body


class TestDateAddQuarter:
    """MySQL DATE_ADD(ts, INTERVAL n QUARTER) — QUARTER was not a recognized date
    unit, so it dropped to an invalid DATEADD. It is now 3 months on Oracle
    (ADD_MONTHS *3) and PG (INTERVAL '3 months'), native on T-SQL/MySQL."""

    def test_quarter_units(self) -> None:
        case = _case("challenge_mysql.sql", "my-dateadd-units ")
        assert "ADD_MONTHS(SYSDATE, 3)" in _tx(case, "mysql", "oracle")
        assert "DATEADD(QUARTER, 1," in _tx(case, "mysql", "tsql")
        assert "INTERVAL '3 months'" in _tx(case, "mysql", "postgresql")


class TestHashFns:
    """md5() is a hex digest on every engine and translates (Oracle STANDARD_HASH,
    T-SQL HASHBYTES); PG sha256(bytea) returns a bytea digest where the others
    return hex, so it degrades to a carrier. lpad/md5 verified, sha256 NULL."""

    def test_md5_translated_sha256_degraded(self) -> None:
        case = _case("challenge_postgresql.sql", "pg-hash-fns ")
        assert "STANDARD_HASH('x', 'MD5')" in _tx(case, "postgresql", "oracle")
        assert "HASHBYTES('MD5', 'x')" in _tx(case, "postgresql", "tsql")
        for target in ("oracle", "tsql", "mysql"):
            result = Transpiler().transpile(case, source="postgresql", target=target)
            assert result.warnings and "UNIQUE-1099:" in result.sql, target


class TestChrAsciiUnicode:
    """PG chr(n) and ascii() are Unicode code-point operations. Oracle CHR(n>127)
    returns a raw byte and ASCII of a multibyte char returns its raw encoding, so
    they map to NCHR(n) and ASCII(TO_NCHAR(x)). Live-verified ('é', 233)."""

    def test_oracle_unicode_codepoint(self) -> None:
        case = _case("challenge_postgresql.sql", "pg-chr-ascii-unicode ")
        out = _tx(case, "postgresql", "oracle")
        assert "NCHR(233)" in out, out
        assert "ASCII(TO_NCHAR(" in out, out


class TestExtractMicroseconds:
    """PG EXTRACT(MICROSECONDS) = the whole seconds field * 1e6; MySQL/T-SQL only
    expose sub-second MICROSECOND, so add SECOND*1e6 (and keep the literal's
    fraction via a (6) datetime cast on MySQL). Oracle has no TIME type → carrier.
    Live-verified 30123456."""

    def test_microseconds_composite(self) -> None:
        case = _case("challenge_postgresql.sql", "pg-frac-seconds ")
        assert "DATEPART(SECOND," in _tx(case, "postgresql", "tsql")
        my = _tx(case, "postgresql", "mysql")
        assert "SECOND(" in my and "* 1000000" in my and "(6)" in my, my
        result = Transpiler().transpile(case, source="postgresql", target="oracle")
        assert result.warnings and "UNIQUE-1097:" in result.sql


class TestSequenceCurrval:
    """Oracle NEXTVAL -> T-SQL NEXT VALUE FOR; CURRVAL has no T-SQL equivalent and
    degrades to a carrier rather than leaking the unbindable seq.CURRVAL
    (ora-seq-use)."""

    def test_currval_degrades_nextval_kept(self) -> None:
        result = Transpiler().transpile(
            _case("challenge_oracle.sql", "ora-seq-use "),
            source="oracle",
            target="tsql",
        )
        assert result.warnings and "UNIQUE-1080:" in result.sql
        assert "NEXT VALUE FOR s" in result.sql
        # no residual seq.CURRVAL in the executable text (only inside the carrier)
        assert "CURRVAL" not in _exec_lines(result.sql).upper().split("/*")[0]


class TestCaseStatementEmptyBlock:
    """An Oracle CASE statement maps to a T-SQL IF/ELSE; a PL/SQL NULL; no-op must
    not leave an empty BEGIN/END (error 156 near ELSE) — the empty block gets a
    no-op filler (ora-case-statement)."""

    def test_empty_if_blocks_filled(self) -> None:
        case = _case("challenge_oracle.sql", "ora-case-statement ")
        out = _tx(case, "oracle", "tsql")
        # both the IF and ELSE blocks carry an executable statement, not just a
        # comment (the filler keeps the BEGIN/END non-empty).
        assert out.count("SET NOCOUNT ON;") >= 3, out  # proc prelude + 2 fillers


class TestCompoundExtract:
    """MySQL compound EXTRACT units (YEAR_MONTH, DAY_HOUR, …) have no equivalent
    elsewhere; they are rebuilt from the component fields with positional weights
    (my-extract-compound)."""

    def test_compound_units_rebuilt(self) -> None:
        case = _case("challenge_mysql.sql", "my-extract-compound ")
        for target in ("postgresql", "oracle"):
            out = _tx(case, "mysql", target)
            assert "EXTRACT(YEAR FROM" in out and "* 100" in out, out
            assert "YEAR_MONTH" not in _exec_lines(out), out
        ts = _tx(case, "mysql", "tsql")
        assert "DATEPART(YEAR," in ts and "YEAR_MONTH" not in _exec_lines(ts), ts


class TestDateLiteralComparison:
    """DATE('2020-01-01') = '2020-01-01 00:00:00' is a DATE comparison (true), but
    the DATE() of a literal was dropped to a bare string (a false text compare).
    It now emits a real date cast; Oracle lifts the ISO string to a TIMESTAMP
    literal (my-date-eq-dt)."""

    def test_date_typing_preserved(self) -> None:
        case = _case("challenge_mysql.sql", "my-date-eq-dt ")
        for target in ("postgresql", "tsql"):
            assert "CAST('2020-01-01' AS DATE)" in _exec_lines(
                _tx(case, "mysql", target)
            )
        ora = _exec_lines(_tx(case, "mysql", "oracle"))
        assert "DATE '2020-01-01'" in ora and "TIMESTAMP '2020-01-01 00:00:00'" in ora


class TestHighPrecisionDecimalLiteral:
    """A decimal literal a Python float cannot hold (2.9999999999999999 -> 3.0) is
    emitted from its exact source text, so FLOOR stays 2 rather than folding to 3
    (my-floor-precision)."""

    def test_exact_literal_preserved(self) -> None:
        case = _case("challenge_mysql.sql", "my-floor-precision ")
        for target in ("postgresql", "oracle", "tsql"):
            out = _exec_lines(_tx(case, "mysql", target))
            assert "2.9999999999999999" in out, out
            assert "3.0" not in out, out


class TestNotOperandParens:
    """``(NOT x) IS NULL`` — NOT binds looser than IS, so the source parens are
    load-bearing; the IR unwrapped them, re-associating to ``NOT (x IS NULL)`` (the
    opposite truth value). Parens are restored on the engines with a boolean value
    type; T-SQL (which has none) degrades the NOT-of-a-non-predicate to a carrier
    (pg-not-null-is-null)."""

    def test_paren_restored_and_tsql_degrades(self) -> None:
        case = _case("challenge_postgresql.sql", "pg-not-null-is-null ")
        for target in ("mysql", "oracle"):
            assert "(NOT NULL) IS NULL" in _exec_lines(_tx(case, "postgresql", target))
        result = Transpiler().transpile(case, source="postgresql", target="tsql")
        assert result.warnings and "UNIQUE-1009:" in result.sql
        assert "NOT NULL" not in _exec_lines(result.sql).split("/*")[0]


class TestRecursiveCteKeyword:
    """A T-SQL CTE that references its own name is recursive, but T-SQL omits the
    RECURSIVE keyword that PG/MySQL require. The self-reference is detected and
    WITH RECURSIVE emitted (Oracle infers recursion, no keyword) — ts-recursive-cte."""

    def test_recursive_keyword_added_for_pg_mysql(self) -> None:
        case = _case("challenge_sqlserver.sql", "ts-recursive-cte ")
        assert "WITH RECURSIVE r" in _exec_lines(_tx(case, "tsql", "postgresql"))
        assert "WITH RECURSIVE r" in _exec_lines(_tx(case, "tsql", "mysql"))
        # Oracle infers recursion; the keyword would be a syntax error there.
        assert "RECURSIVE" not in _exec_lines(_tx(case, "tsql", "oracle"))


class TestRecursiveCteOracleColumnList:
    """Oracle REQUIRES an explicit column alias list on a recursive CTE (ORA-32039);
    it is derived from the anchor SELECT's output names when the source omits it.
    The T-SQL-only OPTION (MAXRECURSION n) hint is dropped (ts-maxrecursion,
    ts-recursion-limit, my-seq-concat)."""

    def test_oracle_column_list_derived(self) -> None:
        for fname, cid, src in (
            ("challenge_sqlserver.sql", "ts-maxrecursion ", "tsql"),
            ("challenge_sqlserver.sql", "ts-recursion-limit ", "tsql"),
            ("challenge_mysql.sql", "my-seq-concat ", "mysql"),
        ):
            ora = _exec_lines(_tx(_case(fname, cid), src, "oracle"))
            # a parenthesised alias list right after the CTE name, and no leaked hint
            assert re.search(r"WITH\s+\w+\s*\(\s*\w+\s*\)", ora), ora
            assert "MAXRECURSION" not in ora.upper(), ora


class TestNestedProcedureCall:
    """A CALL to another procedure maps to each target's call form; the RED
    PLS-00201 was only the absent callee (the snippet never defines it), not a
    mis-transpilation (my-nested-call, pg-nested-call)."""

    def test_mysql_nested_call_forms(self) -> None:
        case = _case("challenge_mysql.sql", "my-nested-call ")
        assert "other_proc();" in _tx(case, "mysql", "oracle")
        assert "EXEC other_proc" in _tx(case, "mysql", "tsql")
        assert "CALL other_proc();" in _tx(case, "mysql", "postgresql")

    def test_pg_nested_call_forms(self) -> None:
        case = _case("challenge_postgresql.sql", "pg-nested-call ")
        assert "inner_p();" in _tx(case, "postgresql", "oracle")
        assert "EXEC inner_p" in _tx(case, "postgresql", "tsql")
        assert "CALL inner_p();" in _tx(case, "postgresql", "mysql")


class TestNcharHexCodePoint:
    """T-SQL NCHAR(0x1F600) is a Unicode code point (integer), not hex bytes. It
    maps to PG CHR / MySQL CHAR(n USING utf32) / Oracle NCHR — and a supplementary
    code point (> U+FFFF), which Oracle NCHR can't hold, becomes a UNISTR surrogate
    pair (ts-nchar-hex)."""

    def test_codepoint_resolved_per_dialect(self) -> None:
        case = _case("challenge_sqlserver.sql", "ts-nchar-hex ")
        assert "CHR(128512)" in _tx(case, "tsql", "postgresql")
        assert "CHAR(128512 USING utf32)" in _tx(case, "tsql", "mysql")
        # 0x1F600 -> surrogate pair D83D DE00
        assert "UNISTR('\\D83D\\DE00')" in _tx(case, "tsql", "oracle")


class TestCastOnConversionError:
    """Oracle CAST(x AS T DEFAULT d ON CONVERSION ERROR): the fallback must survive.
    T-SQL COALESCE(TRY_CAST,d); PG/MySQL a numeric-validation CASE; a literal folds
    at transpile time so PG's constant-folding cannot raise on the bad cast
    (ora-cast-onerror)."""

    def test_literal_folds_to_fallback(self) -> None:
        case = _case("challenge_oracle.sql", "ora-cast-onerror ")
        # 'abc' is not numeric -> the transpiled value is the fallback -1, with no
        # residual cast of the bad literal (which would raise on PG at plan time).
        for target in ("postgresql", "tsql", "mysql"):
            out = _tx(case, "oracle", target)
            assert "TRY_CAST" in out or "-1" in out, out
            assert "CAST('abc'" not in out.replace(" ", ""), out

    def test_tsql_uses_try_cast_coalesce(self) -> None:
        # A column operand (not a foldable literal) becomes a runtime-safe form:
        # T-SQL COALESCE(TRY_CAST,d), PG/MySQL a validation CASE.
        col = "SELECT CAST(v AS NUMBER DEFAULT -1 ON CONVERSION ERROR) AS n " "FROM t;"
        assert (
            "COALESCE(TRY_CAST("
            in Transpiler().transpile(col, source="oracle", target="tsql").sql
        )
        pg = Transpiler().transpile(col, source="oracle", target="postgresql").sql
        assert "CASE WHEN" in pg and "~ '" in pg


class TestGroupConcatDistinctOrder:
    """A DISTINCT ordered string-aggregate into PG cannot order by the raw value
    (STRING_AGG(DISTINCT v ORDER BY k) requires k to be the DISTINCT'd v, so a
    numeric column would sort by its text cast — '2-10-1' not '10-2-1'). The
    DISTINCT is moved into a (SELECT DISTINCT v) derived table so the aggregate
    orders by the raw value. Oracle keeps LISTAGG(DISTINCT …); the MySQL roundtrip
    keeps the separator (my-groupconcat-distinct / -numord)."""

    def test_pg_distinct_order_dedupes_in_derived_table(self) -> None:
        case = _case("challenge_mysql.sql", "my-groupconcat-distinct ")
        pg = _exec_lines(_tx(case, "mysql", "postgresql"))
        # DISTINCT is deduped in a derived table; the aggregate orders by raw x.
        assert "STRING_AGG(CAST(x AS TEXT), '|' ORDER BY x DESC)" in pg
        assert "SELECT DISTINCT x" in pg and "uq_agg_distinct" in pg
        assert "STRING_AGG(DISTINCT" not in pg
        # roundtrip mysql->oracle->mysql keeps the '|' separator (not silently lost)
        ora = Transpiler().transpile(case, source="mysql", target="oracle").sql
        back = Transpiler().transpile(ora, source="oracle", target="mysql").sql
        assert "SEPARATOR '|'" in back

    def test_pg_distinct_numeric_order_is_numeric(self) -> None:
        # A multi-digit numeric column must order numerically ('10-2-1'), which the
        # derived-table dedup allows (ordering by the text cast gives '2-10-1').
        case = _case("challenge_mysql.sql", "my-groupconcat-distinct-numord ")
        pg = _exec_lines(_tx(case, "mysql", "postgresql"))
        assert "STRING_AGG(CAST(x AS TEXT), '-' ORDER BY x DESC)" in pg
        assert "SELECT DISTINCT x" in pg and "uq_agg_distinct" in pg
        assert "STRING_AGG(DISTINCT" not in pg
        # Oracle already orders numerically via LISTAGG; unaffected by the rewrite.
        ora = _exec_lines(_tx(case, "mysql", "oracle"))
        assert "LISTAGG(DISTINCT x, '-') WITHIN GROUP (ORDER BY x DESC)" in ora


class TestDistinctCaseInsensitiveCollation:
    """MySQL's case-insensitive DISTINCT collapses 'a'='A'; PG/Oracle are
    case-sensitive. A LOWER() ordering emulation is invalid under DISTINCT (the key
    is not in the select list) and cannot fix the dedup — so the plain key is kept
    and the divergence flagged as a carrier (my-distinct-case)."""

    def test_lower_suppressed_and_flagged_under_distinct(self) -> None:
        case = _case("challenge_mysql.sql", "my-distinct-case ")
        for target in ("postgresql", "oracle"):
            result = Transpiler().transpile(case, source="mysql", target=target)
            assert result.warnings and "UNIQUE-1015:" in result.sql, target
            body = "\n".join(
                ln for ln in result.sql.splitlines() if not ln.lstrip().startswith("--")
            ).split("/*")[0]
            assert "LOWER(" not in body.upper(), body


class TestMultisetCollectionUnnest:
    """Oracle TABLE(CAST(MULTISET(...) AS <collection>)) collection unnesting has
    no PG/T-SQL equivalent. It degrades to a carrier — and must never leak a node
    repr (a passthrough subquery reaching expression position used to dump its
    Python repr; the invariant is text-degrade, never an object dump)."""

    def test_multiset_degrades_no_repr_leak(self) -> None:
        case = _case("challenge_oracle.sql", "ora-multiset-table ")
        for target in ("postgresql", "tsql"):
            result = Transpiler().transpile(case, source="oracle", target=target)
            assert result.warnings and "UNIQUE-1151:" in result.sql, target
            assert "PassthroughSQL(" not in result.sql, target
            assert "SourceLocation(" not in result.sql, target


class TestExtractEpochInterval:
    """EXTRACT(EPOCH FROM timestamp) is a literal date-diff, but EXTRACT(EPOCH
    FROM interval) has no portable form (T-SQL/MySQL have no interval value type)
    and degrades to a carrier — the timestamp column still translates."""

    def test_interval_epoch_degrades_timestamp_kept(self) -> None:
        case = _case("challenge_postgresql.sql", "pg-epoch ")
        for target in ("oracle", "tsql", "mysql"):
            result = Transpiler().transpile(case, source="postgresql", target=target)
            assert result.warnings and "UNIQUE-1096:" in result.sql, target
            body = "\n".join(
                ln for ln in result.sql.splitlines() if not ln.lstrip().startswith("--")
            )
            # The interval half degrades; no live INTERVAL keyword survives.
            assert "INTERVAL" not in body.upper().split("/*")[0], body


class TestExtractEpoch:
    """PG EXTRACT(EPOCH FROM timestamp) — Unix seconds — has no native EPOCH field
    on the other engines. Rewritten to a literal date-diff (no session-tz shift):
    Oracle date arithmetic *86400, T-SQL DATEDIFF_BIG(SECOND, …), MySQL
    TIMESTAMPDIFF(SECOND, …). Live-verified 1577836800 on all three."""

    def test_epoch_rewrite(self) -> None:
        case = _case("challenge_postgresql.sql", "pg-extract-epoch ")
        assert "DATE '1970-01-01'" in _tx(case, "postgresql", "oracle")
        assert "DATEDIFF_BIG(SECOND, '1970-01-01'" in _tx(case, "postgresql", "tsql")
        assert "TIMESTAMPDIFF(SECOND, '1970-01-01 00:00:00'" in _tx(
            case, "postgresql", "mysql"
        )
        for target in ("oracle", "tsql", "mysql"):
            body = "\n".join(
                ln
                for ln in _tx(case, "postgresql", target).splitlines()
                if not ln.lstrip().startswith("--")
            )
            assert "EPOCH" not in body, body


class TestSpatialClrScopeResolution:
    """T-SQL spatial/CLR type methods (``geometry::Point(…).STDistance(…)`` — a
    ScopeResolution) have no cross-engine equivalent and sqlglot silently flattens
    them; they now degrade to a NULL placeholder + UNIQUE carrier + warning on
    every other engine, and re-emit verbatim on T-SQL."""

    def test_degrades_with_carrier_off_tsql(self) -> None:
        case = _case("challenge_sqlserver.sql", "ts-st-distance ")
        for target in ("oracle", "postgresql", "mysql"):
            result = Transpiler().transpile(case, source="tsql", target=target)
            assert result.warnings, target
            assert "UNIQUE-1063:" in result.sql and "NULL" in result.sql, result.sql
            # No live spatial call escapes as executable text (only inside the
            # carrier comment); ignore the source ``--`` header prose.
            body = "\n".join(
                ln for ln in result.sql.splitlines() if not ln.lstrip().startswith("--")
            )
            assert "STDistance" not in body.split("/*")[0], body

    def test_verbatim_on_tsql(self) -> None:
        case = _case("challenge_sqlserver.sql", "ts-st-distance ")
        out = _tx(case, "tsql", "tsql")
        assert "STDistance" in out and "UNIQUE-" not in out, out


class TestBitStringCast:
    """T-SQL CAST('true' AS BIT) parses the boolean word (a numeric string by its
    value); other engines can't convert 'true' to a number (ORA-01722). Fold a
    string BIT cast to 1/0. Live-verified (1,1,0)."""

    def test_bit_string_folds(self) -> None:
        out = _tx(_case("challenge_sqlserver.sql", "ts-bit-cast "), "tsql", "oracle")
        assert "SIGN(ABS(1)), 1, SIGN(ABS(0))" in out, out


class TestBitwiseArithmeticPrecedence:
    """Bitwise-vs-arithmetic precedence is not portable (MySQL/Oracle bind
    bitwise looser than +/*; PostgreSQL/T-SQL tighter). A mixed source
    expression is parenthesized explicitly so it can't re-associate."""

    def test_mysql_grouping_preserved_on_tsql(self) -> None:
        for target in ("postgresql", "tsql"):
            out = _tx(_case("challenge_mysql.sql", "my-bit-prec2 "), "mysql", target)
            assert "10 & (6 + 1)" in out and "10 | (2 * 3)" in out, out
            assert "1 << (2 + 1)" in out, out

    def test_pg_grouping_preserved_on_tsql(self) -> None:
        out = _tx(
            _case("challenge_postgresql.sql", "pg-bit-prec2 "), "postgresql", "tsql"
        )
        assert "10 & (6 + 1)" in out and "1 << (2 + 1)" in out, out


class TestDateExtractCast:
    """MySQL/T-SQL DATE(x) extracts the date part (drops any time). Unwrapping
    the sqlglot cast wrapper to the bare expression kept the clock on the
    target; an explicit CAST AS DATE preserves the truncation."""

    def test_date_of_timestamp_drops_time(self) -> None:
        out = _tx(_case("challenge_mysql.sql", "my-ts-to-date "), "mysql", "postgresql")
        assert "CAST(CAST('2020-01-01 14:30' AS TIMESTAMPTZ) AS DATE)" in out, out


class TestLocalTimestamp:
    """Oracle LOCALTIMESTAMP maps to PostgreSQL's niladic keyword (no parens),
    T-SQL SYSDATETIME(), and MySQL CURRENT_TIMESTAMP (a parenthesized
    LOCALTIMESTAMP() is invalid on PG / undefined on T-SQL)."""

    def test_localtimestamp_per_engine(self) -> None:
        case = _case("challenge_oracle.sql", "ora-now-fns ")
        pg = _tx(case, "oracle", "postgresql")
        assert "LOCALTIMESTAMP" in pg and "LOCALTIMESTAMP()" not in pg, pg
        assert "SYSDATETIME()" in _tx(case, "oracle", "tsql")


class TestPkUsingIndex:
    """Oracle's PRIMARY KEY … USING INDEX (backing-index storage detail) is
    stripped for the other engines, which back a PK with an index by default."""

    def test_using_index_stripped(self) -> None:
        case = _case("challenge_oracle.sql", "ora-pk-using-index ")
        for target in ("mysql", "postgresql", "tsql"):
            body = "\n".join(
                ln
                for ln in _tx(case, "oracle", target).splitlines()
                if not ln.lstrip().startswith("--")
            )
            assert "PRIMARY KEY (id)" in body and "USING INDEX" not in body, body


class TestFunctionalIndex:
    """An Oracle expression (function-based) index maps to the MySQL/PostgreSQL
    double-paren form ((expr)); T-SQL has no expression index and degrades."""

    def test_double_parens_on_mysql_pg(self) -> None:
        case = _case("challenge_oracle.sql", "ora-functional-index ")
        assert "ON t ((a * 2))" in _tx(case, "oracle", "mysql")
        assert "ON t ((a * 2))" in _tx(case, "oracle", "postgresql")


class TestSelectIntoCtas:
    """T-SQL / PostgreSQL SELECT … INTO newtable creates a table; Oracle (and
    MySQL) have no such form, so it is rewritten to CREATE TABLE … AS SELECT
    (GLOBAL TEMPORARY for a TEMP / #name target)."""

    def test_tsql_select_into_becomes_ctas(self) -> None:
        out = _tx(_case("challenge_sqlserver.sql", "ts-select-into "), "tsql", "oracle")
        up = "\n".join(
            ln for ln in out.splitlines() if not ln.lstrip().startswith("--")
        ).upper()
        assert "CREATE TABLE DST AS SELECT" in up and " INTO " not in up, up

    def test_pg_temp_select_into_becomes_gtt(self) -> None:
        out = _tx(
            _case("challenge_postgresql.sql", "pg-select-into-ctas "),
            "postgresql",
            "oracle",
        )
        assert "CREATE GLOBAL TEMPORARY TABLE t2 AS SELECT" in out, out


class TestSequenceOptions:
    """Oracle CREATE SEQUENCE one-word negatives (NOCYCLE) map to PostgreSQL /
    T-SQL two-word NO CYCLE, and the ORDER/NOORDER RAC option is dropped."""

    def test_nocycle_and_order_normalized(self) -> None:
        for target in ("postgresql", "tsql"):
            out = _tx(
                _case("challenge_oracle.sql", "ora-sequence-options "), "oracle", target
            )
            body = "\n".join(
                ln for ln in out.splitlines() if not ln.lstrip().startswith("--")
            )
            assert "NO CYCLE" in body and "NOCYCLE" not in body, body
            assert "ORDER" not in body, body


class TestJsonColumnType:
    """A MySQL JSON column maps to Oracle CLOB (its JSON type has usage limits)
    and T-SQL NVARCHAR(MAX) (no JSON type pre-2025); PostgreSQL keeps JSON."""

    def test_json_column_maps_per_engine(self) -> None:
        case = _case("challenge_mysql.sql", "my-json-type ")
        assert "data CLOB" in _tx(case, "mysql", "oracle")
        assert "data NVARCHAR(MAX)" in _tx(case, "mysql", "tsql")


class TestAutoIncrementKey:
    """A PostgreSQL SERIAL maps to a MySQL AUTO_INCREMENT column, which MySQL
    requires to be indexed (error 1075); a KEY is added when nothing covers it,
    but not when the column is already a PRIMARY KEY."""

    def test_serial_gets_key_on_mysql(self) -> None:
        out = _tx(
            _case("challenge_postgresql.sql", "pg-numtypes "), "postgresql", "mysql"
        )
        assert "AUTO_INCREMENT" in out and "KEY (`g`)" in out, out

    def test_serial_pk_not_double_keyed(self) -> None:
        out = _tx(
            "CREATE TABLE t (id SERIAL PRIMARY KEY, x INT)", "postgresql", "mysql"
        )
        assert out.upper().count("KEY") == 1, out


class TestBitWidthType:
    """A multi-bit MySQL BIT(M>1) is a 64-bit value: NUMERIC(20)/NUMBER(20) on
    T-SQL/Oracle (with a warned note) and native BIT(M) on PG. Only a 1-bit
    BIT/BOOL keeps the boolean map (the old width-dropping BIT map silently
    truncated BIT(8) to one bit — the mysql-prec-64 finding)."""

    def test_bit8_maps_to_numeric_on_tsql(self) -> None:
        out = _tx(_case("challenge_mysql.sql", "my-bintypes "), "mysql", "tsql")
        body = _exec_lines(out)
        assert "g NUMERIC(20)" in body, body
        assert "h BIT" in body and "BIT(" not in body, body

    def test_bit8_native_on_postgresql(self) -> None:
        out = _tx(_case("challenge_mysql.sql", "my-bintypes "), "mysql", "postgresql")
        body = _exec_lines(out)
        assert "g BIT(8)" in body, body
        assert "h BOOLEAN" in body, body


class TestFloatDisplayScale:
    """MySQL FLOAT(M,D) is a 4-byte float with a display scale; PostgreSQL and
    T-SQL FLOAT take at most a bit-precision, so it maps to REAL with no width."""

    def test_float_md_maps_to_real_on_tsql(self) -> None:
        out = _tx(_case("challenge_mysql.sql", "my-numeric "), "mysql", "tsql")
        assert "b REAL" in out and "REAL(" not in out, out


class TestCheckEnforced:
    """MySQL's ENFORCED on a CHECK constraint is the default (the constraint is
    validated); it has no keyword on Oracle/PG/T-SQL, so it is stripped."""

    def test_enforced_stripped(self) -> None:
        for target in ("oracle", "postgresql", "tsql"):
            out = _tx(
                _case("challenge_mysql.sql", "my-check-enforced "), "mysql", target
            )
            body = "\n".join(
                ln for ln in out.splitlines() if not ln.lstrip().startswith("--")
            )
            assert "CHECK (a > 0)" in body and "ENFORCED" not in body, body


class TestAlterAddColumnDefault:
    """ADD COLUMN … NOT NULL DEFAULT v: Oracle needs DEFAULT before NOT NULL
    (ORA-30649), and MySQL needs a parenthesized default on TEXT/BLOB columns
    (error 1101). Both are rewritten in the passthrough emitter."""

    def test_tsql_add_reordered_on_oracle(self) -> None:
        out = _tx(_case("challenge_sqlserver.sql", "ts-alter-add "), "tsql", "oracle")
        assert "DEFAULT 'x' NOT NULL" in out, out

    def test_pg_text_default_parenthesized_on_mysql(self) -> None:
        out = _tx(
            _case("challenge_postgresql.sql", "pg-alter-add "), "postgresql", "mysql"
        )
        assert "DEFAULT ('x')" in out, out


class TestAlterDropDefault:
    """ALTER COLUMN a DROP DEFAULT maps to Oracle MODIFY a DEFAULT NULL and to a
    T-SQL dynamic drop of the (auto-named) default constraint via
    sys.default_constraints — a no-op when the column has no default."""

    def test_oracle_modify_default_null(self) -> None:
        out = _tx(
            _case("challenge_mysql.sql", "my-alter-drop-default "), "mysql", "oracle"
        )
        assert "MODIFY a DEFAULT NULL" in out, out

    def test_tsql_dynamic_constraint_drop(self) -> None:
        out = _tx(
            _case("challenge_mysql.sql", "my-alter-drop-default "), "mysql", "tsql"
        )
        assert "sys.default_constraints" in out and "DROP CONSTRAINT" in out, out


class TestPgAlterColumnType:
    """PostgreSQL ALTER COLUMN a [SET DATA] TYPE t maps to Oracle MODIFY a t
    (Oracle has no TYPE keyword); a redundant USING cast IS Oracle's implicit
    conversion and is dropped."""

    def test_alter_type_oracle_modify(self) -> None:
        out = _tx(
            _case("challenge_postgresql.sql", "pg-alter-type "), "postgresql", "oracle"
        )
        assert "MODIFY a NUMBER" in out and "TYPE" not in out.split(";")[-1], out

    def test_alter_using_dropped_on_oracle(self) -> None:
        out = _tx(
            _case("challenge_postgresql.sql", "pg-alter-using "), "postgresql", "oracle"
        )
        body = "\n".join(
            ln for ln in out.splitlines() if not ln.lstrip().startswith("--")
        )
        assert "MODIFY a NUMBER" in body and "USING" not in body, body


class TestPgBooleanWordCast:
    """PostgreSQL casts many word spellings to boolean ('t'/'true'/'yes'/'on' ->
    true), which other engines cannot cast to a number or bit. A string-literal
    ::boolean folds to 1/0, so a downstream ::int matches. Live-verified 1."""

    def test_true_word_folds_to_one(self) -> None:
        out = _tx(
            _case("challenge_postgresql.sql", "pg-bool-int-cast "),
            "postgresql",
            "oracle",
        )
        body = "\n".join(
            ln for ln in out.splitlines() if not ln.lstrip().startswith("--")
        )
        assert "CAST(1 AS INT)" in body, body
        assert "'t'" not in body and "'true'" not in body, body


class TestConvertUsingCharset:
    """MySQL CONVERT(x USING charset) is a per-value charset conversion that
    leaves the string value unchanged; no other engine has per-value charsets,
    so it maps to identity (a bare CAST AS CHAR would truncate to CHAR(1))."""

    def test_convert_using_is_identity(self) -> None:
        for target in ("oracle", "postgresql", "tsql"):
            out = _tx(
                _case("challenge_mysql.sql", "my-convert-using2 "), "mysql", target
            )
            body = "\n".join(
                ln for ln in out.splitlines() if not ln.lstrip().startswith("--")
            )
            # Unbounded string cast (VARCHAR2(4000)/TEXT/VARCHAR(8000)) preserves
            # the value; it must never be a bare CHAR (truncates to CHAR(1)).
            assert "'2020-06-15 14:30'" in body, body
            assert not re.search(r"(?i)AS CHAR\b", body), body


class TestConcatDateIso:
    """Oracle renders a DATE concatenated to a string via NLS_DATE_FORMAT
    ('01-JAN-20'); MySQL uses ISO 'yyyy-mm-dd'. A DATE-valued CONCAT argument is
    wrapped in TO_CHAR(d, 'YYYY-MM-DD') on Oracle. Live-verified '2020-01-01'."""

    def test_oracle_wraps_date_concat_arg(self) -> None:
        out = _tx(_case("challenge_mysql.sql", "my-concat-date "), "mysql", "oracle")
        assert "TO_CHAR(DATE '2020-01-01', 'YYYY-MM-DD')" in out, out

    def test_plain_string_concat_untouched(self) -> None:
        assert "TO_CHAR" not in _tx("SELECT CONCAT('a','b') AS r", "mysql", "oracle")


class TestJsonConstructors:
    """JSON_OBJECT / JSON_ARRAY exist on all four engines with different syntax
    (PG json_build_object/array, Oracle KEY..VALUE, T-SQL colon). A boolean stays
    a JSON boolean (PG/Oracle TRUE; T-SQL renders a BIT as true/false) and NULL is
    preserved (Oracle/T-SQL need NULL ON NULL, which sqlglot's T-SQL reader can't
    parse — the gate skips it). Live-verified [1,"a",null,true] on all four."""

    def test_json_object_per_engine(self) -> None:
        case = _case("challenge_mysql.sql", "my-json-object ")
        assert "JSON_BUILD_OBJECT('a', 1" in _tx(case, "mysql", "postgresql")
        assert "'a' VALUE 1" in _tx(case, "mysql", "oracle")
        assert "'a':1" in _tx(case, "mysql", "tsql")

    def test_json_array_boolean_and_null(self) -> None:
        case = _case("challenge_mysql.sql", "my-json-build ")
        pg = _tx(case, "mysql", "postgresql")
        assert "JSON_BUILD_ARRAY(1, 'a', NULL, TRUE)" in pg, pg
        ts = _tx(case, "mysql", "tsql")
        assert "CAST(1 AS BIT)" in ts and "NULL ON NULL" in ts, ts


class TestMonthsBetweenFractional:
    """Oracle MONTHS_BETWEEN is fractional (whole months + (day1-day2)/31, and a
    whole number when both dates are month-ends or the same day-of-month). T-SQL
    has no such function; the exact CASE is emitted (not an integer DATEDIFF
    boundary count). Live-verified 1.83871 and 1.0."""

    def test_tsql_emits_fractional_case(self) -> None:
        out = _tx(
            _case("challenge_oracle.sql", "ora-months-between-val "), "oracle", "tsql"
        )
        assert "EOMONTH" in out and "/ 31.0" in out, out
        assert "DATEDIFF(MONTH" in out, out


class TestTimestampDiffCompletePeriods:
    """MySQL TIMESTAMPDIFF counts COMPLETE periods; T-SQL DATEDIFF counts
    unit-boundary crossings. For month/quarter/year the transpiler drops the
    incomplete final period (DATEADD(unit, boundary, start) > end). A
    DATEDIFF-sourced batch keeps pure boundary counting. Live-verified 1 and 0."""

    def test_month_complete_period_on_tsql(self) -> None:
        ts = _tx(_case("challenge_mysql.sql", "my-timestampdiff-mon "), "mysql", "tsql")
        assert "DATEADD(MONTH, DATEDIFF(MONTH" in ts and "THEN 1 ELSE 0 END" in ts, ts

    def test_datediff_source_stays_boundary(self) -> None:
        # A T-SQL DATEDIFF must NOT gain the complete-period adjustment.
        out = _tx(
            "SELECT DATEDIFF(MONTH, '2020-01-15', '2020-03-10') AS r", "tsql", "tsql"
        )
        assert "CASE WHEN DATEADD" not in out, out


class TestPiMathFunctions:
    """PI() math across engines. T-SQL RADIANS/DEGREES echo the argument's type,
    so an integer arg truncates (RADIANS(180)=3) — the integer is cast to FLOAT.
    PostgreSQL TRUNC/ROUND have no (double precision, int) overload, so a double
    value like PI() is cast to NUMERIC. Live-verified on all four engines."""

    def test_radians_integer_arg_cast_to_float(self) -> None:
        ts = _tx(_case("challenge_mysql.sql", "my-pi-vals "), "mysql", "tsql")
        assert "RADIANS(CAST(180 AS FLOAT))" in ts, ts

    def test_pg_trunc_round_double_cast_to_numeric(self) -> None:
        pg = _tx(_case("challenge_mysql.sql", "my-pi-fns "), "mysql", "postgresql")
        assert "TRUNC(CAST(PI() AS NUMERIC), 4)" in pg, pg
        assert "ROUND(CAST(PI() AS NUMERIC), 4)" in pg, pg


class TestLastDayAndNames:
    """LAST_DAY / DAYNAME / MONTHNAME (MySQL) across engines. The date-name
    functions wrap a bare ISO string as an ANSI ``DATE`` literal (else Oracle/PG
    reject it) and use the FM-trimmed, init-capped name model so a lone month/day
    name matches MySQL's 'June'/'Monday' instead of Oracle's padded 'JUNE     '.
    Live-verified 2020-02-29, Monday, June on all four engines."""

    def _out(self, target: str) -> str:
        return _tx(_case("challenge_mysql.sql", "my-last-day-name "), "mysql", target)

    def test_last_day_forms(self) -> None:
        assert "EOMONTH('2020-02-15')" in self._out("tsql")
        assert "LAST_DAY(DATE '2020-02-15')" in self._out("oracle")
        assert "DATE_TRUNC('month', DATE '2020-02-15')" in self._out("postgresql")

    def test_month_and_day_names_trimmed(self) -> None:
        ora = self._out("oracle")
        assert "TO_CHAR(DATE '2020-06-15', 'fmDay')" in ora, ora
        assert "TO_CHAR(DATE '2020-06-15', 'FMMonth')" in ora, ora
        pg = self._out("postgresql")
        assert "TO_CHAR(DATE '2020-06-15', 'FMDay')" in pg, pg
        assert "TO_CHAR(DATE '2020-06-15', 'FMMonth')" in pg, pg


class TestJsonPathExtraction:
    """JSON_VALUE(doc, path) and JSON_QUERY(doc, path) (Oracle/T-SQL scalar and
    object extraction). MySQL has JSON_VALUE natively but routes JSON_QUERY
    through JSON_EXTRACT; PostgreSQL <17 has neither and uses the SQL/JSON path
    engine (JSONB_PATH_QUERY_FIRST). Live-verified '1' and '[1]' on all four."""

    def test_json_value_per_engine(self) -> None:
        case = _case("challenge_oracle.sql", "ora-json-value ")
        pg = _tx(case, "oracle", "postgresql")
        assert (
            "JSONB_PATH_QUERY_FIRST(CAST('{\"a\":1}' AS JSONB), '$.a') #>> '{}'" in pg
        ), pg
        assert "JSON_VALUE('{\"a\":1}', '$.a')" in _tx(case, "oracle", "mysql")
        assert "JSON_VALUE('{\"a\":1}', '$.a')" in _tx(case, "oracle", "tsql")

    def test_json_query_object_form(self) -> None:
        case = _case("challenge_oracle.sql", "ora-json-x ")
        # MySQL has no JSON_QUERY -> JSON_EXTRACT; PG -> path engine (no #>>).
        my = _tx(case, "oracle", "mysql")
        assert "JSON_EXTRACT('{\"a\":[1]}', '$.a')" in my, my
        pg = _tx(case, "oracle", "postgresql")
        assert "JSONB_PATH_QUERY_FIRST(CAST('{\"a\":[1]}' AS JSONB), '$.a')" in pg, pg


class TestDateTruncMonth:
    """PG date_trunc parses to TimestampTrunc (fake sql_name); it is canonicalized
    to DATE_TRUNC and mapped per engine — Oracle TRUNC(ts,'MM'), T-SQL
    DATETRUNC(month, …), MySQL DATE_FORMAT. Also exercises the Oracle
    TIMESTAMP-literal seconds padding. (Live-verified 2020-05-01 on all four.)"""

    def test_pg_month_trunc_per_engine(self) -> None:
        case = _case("challenge_postgresql.sql", "pg-date-trunc ")
        o4 = _tx(case, "postgresql", "oracle")
        assert "TRUNC(" in o4 and "'MM'" in o4, o4
        assert "TIMESTAMP '2020-05-17 10:00:00'" in o4, o4  # seconds padded
        ts = _tx(case, "postgresql", "tsql")
        assert "DATETRUNC(month," in ts, ts
        my = _tx(case, "postgresql", "mysql")
        assert "DATE_FORMAT(" in my and "%Y-%m-01" in my, my


class TestDateFormatMasks:
    """TO_CHAR(date, mask) / TO_TIMESTAMP(str, mask): sqlglot canonicalizes the
    mask to python strftime; the emitter translates it to each engine's model
    (Oracle/PG ``YYYY-MM-DD``, MySQL ``%Y-%m-%d`` with bare literals, T-SQL .NET
    ``yyyy-MM-dd``) and spells TO_CHAR / DATE_FORMAT / FORMAT. A constant
    ISO-shaped string parses to a fixed value (ANSI literal / CAST).
    (Live-verified 2020-06-15T14:30:45 and the .123 fractional on all four.)"""

    def test_tochar_iso_formatting(self) -> None:
        case = _case("challenge_oracle.sql", "ora-tochar-iso ")
        my = _tx(case, "oracle", "mysql")
        assert "DATE_FORMAT(" in my and "%Y-%m-%dT%H:%i:%s" in my, my
        ts = _tx(case, "oracle", "tsql")
        assert "FORMAT(" in ts and "yyyy-MM-dd" in ts, ts
        pg = _tx(case, "oracle", "postgresql")
        assert "TO_CHAR(" in pg and 'YYYY-MM-DD"T"HH24:MI:SS' in pg, pg

    def test_to_timestamp_fractional(self) -> None:
        case = _case("challenge_oracle.sql", "ora-to-timestamp ")
        my = _tx(case, "oracle", "mysql")
        assert "DATETIME(6)" in my, my  # keeps the .123 fractional
        pg = _tx(case, "oracle", "postgresql")
        assert "TIMESTAMP '2020-01-01 10:00:00.123'" in pg, pg

    def test_mysql_date_format_wraps_string_value(self) -> None:
        # DATE_FORMAT('2020-05-17', …): the bare ISO string is wrapped as a DATE
        # so Oracle/PG TO_CHAR (which reject a string) work.
        case = _case("challenge_mysql.sql", "my-date-format ")
        o4 = _tx(case, "mysql", "oracle")
        assert "TO_CHAR(DATE '2020-05-17', 'YYYY/MM/DD')" in o4, o4
        ts = _tx(case, "mysql", "tsql")
        assert "FORMAT(CAST('2020-05-17' AS DATE), 'yyyy/MM/dd')" in ts, ts

    def test_bare_letter_mask_degrades(self) -> None:
        # A MySQL mask with a bare-letter literal (%Y-%m-%dT…) or a locale name
        # (%W) cannot round-trip unquoted — it must degrade, not ship wrong.
        r = Transpiler().transpile(
            _case("challenge_mysql.sql", "my-dateformat-iso "),
            source="mysql",
            target="oracle",
        )
        assert r.warnings and "UNIQUE-1151:" in r.sql, r.sql

    def test_number_format_mask(self) -> None:
        # T-SQL FORMAT(num, 'N2') -> Oracle/PG TO_CHAR FM mask, MySQL FORMAT(n, 2).
        case = _case("challenge_sqlserver.sql", "ts-format-number ")
        o4 = _tx(case, "tsql", "oracle")
        assert "TO_CHAR(1234.5, 'FM" in o4 and "D00')" in o4, o4
        my = _tx(case, "tsql", "mysql")
        assert "FORMAT(1234.5, 2)" in my, my

    def test_currency_number_mask_degrades(self) -> None:
        # A currency mask (L) has no cross-engine equivalent — degrade, not
        # ship a wrong DATE_FORMAT.
        r = Transpiler().transpile(
            "SELECT TO_CHAR(1234.5, 'L9G999D99') AS r", source="oracle", target="mysql"
        )
        assert r.warnings and "UNIQUE-1151:" in r.sql, r.sql


class TestTsqlIntToDatetime:
    """T-SQL ``CAST(n AS DATETIME)`` reads n as days since the 1900-01-01 epoch;
    no other engine has that implicit conversion, so it becomes date arithmetic
    ``DATE '1900-01-01' + n`` (live-verified 1900-01-02 on Oracle and PG)."""

    def test_int_to_datetime_epoch(self) -> None:
        case = _case("challenge_sqlserver.sql", "ts-cast-int-datetime ")
        o4 = _tx(case, "tsql", "oracle")
        assert "DATE '1900-01-01' + 1" in o4, o4
        pg = _tx(case, "tsql", "postgresql")
        assert "AS DATE) + 1" in pg, pg

    def test_datalength_byte_length(self) -> None:
        # DATALENGTH(x) is the byte length -> LENGTHB / OCTET_LENGTH; the
        # VARBINARY cast is unwrapped.
        case = _case("challenge_sqlserver.sql", "ts-binary-length ")
        assert "LENGTHB('hello')" in _tx(case, "tsql", "oracle")
        assert "OCTET_LENGTH('hello')" in _tx(case, "tsql", "postgresql")

    def test_money_cast_and_currency_string(self) -> None:
        # MONEY -> NUMBER/NUMERIC(19,4); CONVERT(MONEY, '$12.99') strips $/commas.
        case = _case("challenge_sqlserver.sql", "ts-cast-money ")
        o4 = _tx(case, "tsql", "oracle")
        assert "CAST(12.99 AS NUMBER(19,4))" in o4, o4
        assert "REPLACE(REPLACE('$12.99', '$', ''), ',', '')" in o4, o4

    def test_mysql_cast_char_to_string_type(self) -> None:
        # MySQL CAST(x AS CHAR) (no length) -> a target string type, not a bare
        # length-less CHAR (which Oracle rejects).
        case = _case("challenge_mysql.sql", "my-cast-num-char ")
        assert "VARCHAR2(4000)" in _tx(case, "mysql", "oracle")
        assert "AS TEXT)" in _tx(case, "mysql", "postgresql")

    def test_mysql_cast_to_int_rounds(self) -> None:
        # MySQL CAST(x AS SIGNED) rounds; Oracle INTEGER rounds, T-SQL truncates
        # so ROUND is wrapped -- including for a negated literal (-3.99).
        case = _case("challenge_mysql.sql", "my-round-cast ")
        assert "CAST(-3.99 AS INTEGER)" in _tx(case, "mysql", "oracle")
        assert "CAST(ROUND(-3.99, 0) AS BIGINT)" in _tx(case, "mysql", "tsql")

    def test_mysql_cast_datetime_iso_literal(self) -> None:
        # CAST(iso-string AS DATETIME) -> Oracle ANSI DATE/TIMESTAMP literal (a
        # bare CAST to TIMESTAMP applies NLS and fails).
        case = _case("challenge_mysql.sql", "my-cast-datetime ")
        assert "DATE '2020-01-01'" in _tx(case, "mysql", "oracle")

    def test_mysql_year_type_folds_to_integer(self) -> None:
        # MySQL YEAR (no cross-engine type) folds a literal to its integer year
        # with the 2-digit century rule ('99' -> 1999).
        o4 = _tx(_case("challenge_mysql.sql", "my-cast-year "), "mysql", "oracle")
        assert "2020, 2020, 1999" in o4, o4


class TestStringAggTextCastIntoPg:
    """PG ``string_agg`` will not implicitly stringify its value (unlike T-SQL
    STRING_AGG / Oracle LISTAGG); an integer value is cast to text so PG doesn't
    reject ``string_agg(integer, unknown)``, and the WITHIN GROUP order folds
    into the aggregate call."""

    def test_tsql_within_group_into_pg_casts_value(self) -> None:
        out = _tx(
            _case("challenge_sqlserver.sql", "ts-stragg-within"), "tsql", "postgresql"
        )
        assert "STRING_AGG(CAST(x AS TEXT), ',' ORDER BY x)" in out, out

    def test_oracle_listagg_into_pg_casts_value(self) -> None:
        out = _tx(_case("challenge_oracle.sql", "ora-listagg "), "oracle", "postgresql")
        assert "STRING_AGG(CAST(x AS TEXT), ',' ORDER BY x)" in out, out


class TestTsqlDerivedColumnName:
    """T-SQL requires every derived-table column to be named (error 8155); an
    unnamed projection (a parameter -> @a) gets a synthesized alias (my-reads-sql)."""

    def test_unnamed_derived_column_aliased(self) -> None:
        case = _case("challenge_mysql.sql", "my-reads-sql ")
        out = _tx(case, "mysql", "tsql")
        assert "(SELECT @a AS uq_col1) t" in out, out

    def test_literal_derived_column_aliased(self) -> None:
        # a numeric-literal projection must be aliased too (1 is \w+ but not a name)
        case = _case("challenge_mysql.sql", "my-scalar-subquery-assign ")
        assert "(SELECT 1 AS uq_col1) t" in _tx(case, "mysql", "tsql")


class TestSavepointBatch:
    """SAVEPOINT in a batch is sqlglot-misparsed as an Alias (SAVEPOINT AS sp);
    modeled as a passthrough so T-SQL gets SAVE TRANSACTION and ROLLBACK TO
    SAVEPOINT keeps its name (pg-savepoint)."""

    def test_savepoint_and_rollback_forms(self) -> None:
        case = _case("challenge_postgresql.sql", "pg-savepoint ")
        ts = _exec_lines(_tx(case, "postgresql", "tsql"))
        assert "SAVE TRANSACTION sp" in ts and "ROLLBACK TRANSACTION sp" in ts
        assert "AS sp" not in ts
        my = _exec_lines(_tx(case, "postgresql", "mysql"))
        assert "SAVEPOINT sp" in my and "ROLLBACK TO sp" in my and "AS sp" not in my


class TestDdlConstraintClausesSurvive:
    """Inline CHECK and FK REFERENCES/ON DELETE constraints survive to every
    target (they were once silently dropped; the RC-3 constraint path keeps
    them). Guarded so a regression to the silent-drop is caught."""

    @pytest.mark.parametrize("target", ("mysql", "oracle", "tsql"))
    def test_inline_check_survives(self, target: str) -> None:
        out = _tx(
            _case("challenge_postgresql.sql", "postgresql-drop-CHECK"),
            "postgresql",
            target,
        )
        assert re.search(r"(?i)CHECK\s*\(", _exec_lines(out)), out

    @pytest.mark.parametrize("target", ("mysql", "oracle", "tsql"))
    def test_fk_references_survives(self, target: str) -> None:
        out = _tx(
            _case("challenge_postgresql.sql", "postgresql-drop5-REFERENCES"),
            "postgresql",
            target,
        )
        assert re.search(r"(?i)REFERENCES\b", _exec_lines(out)), out


class TestNegativeSubstr:
    """Oracle/MySQL SUBSTR(s, -n, len) counts from the END; PG/T-SQL SUBSTRING is
    1-indexed and reads -n literally. The start is rewritten to LENGTH(s)-n+1."""

    @pytest.mark.parametrize("target", ("postgresql", "tsql"))
    def test_negative_start_uses_length_offset(self, target: str) -> None:
        out = _tx(_case("challenge_oracle.sql", "ora-substr-neg"), "oracle", target)
        assert re.search(
            r"(?i)(LEN|LENGTH)\('abcdef'\)\s*\+\s*\(-3\)\s*\+\s*1", out
        ), out


class TestConcatNumberIntoTsql:
    """Oracle/PG ``||`` (and MySQL CONCAT) stringify numeric operands; T-SQL
    ``+`` would do arithmetic (2||3 → 5) or error (string+number). A concat with
    a numeric operand emits T-SQL CONCAT()."""

    def test_number_concat_uses_concat(self) -> None:
        out = _tx(_case("challenge_oracle.sql", "ora-num-concat"), "oracle", "tsql")
        assert "CONCAT(2, 3)" in out and "2 + 3" not in out, out

    def test_string_number_concat_uses_concat(self) -> None:
        out = _tx(_case("challenge_oracle.sql", "ora-concat-num"), "oracle", "tsql")
        assert "CONCAT('a', 5)" in out, out


class TestConcatNumberIntoPostgres:
    """PostgreSQL has no ``integer || integer`` operator, so Oracle's ``2||3``
    (which implicitly stringifies to '23') would emit an invalid ``2 || 3`` on
    PG. When both operands of a ``||`` are known-numeric, cast them to TEXT so
    the operator resolves. A ``||`` with a string/unknown operand (PG's
    ``text || anynonarray``) already resolves and must stay untouched."""

    def test_both_numeric_operands_cast_to_text(self) -> None:
        out = _tx(
            _case("challenge_oracle.sql", "ora-num-concat"), "oracle", "postgresql"
        )
        assert "CAST(2 AS TEXT) || CAST(3 AS TEXT)" in out, out

    def test_string_operand_stays_bare(self) -> None:
        # 'a' || 5 : the text operand lets PG resolve text || anynonarray — no cast.
        out = _tx(
            _case("challenge_oracle.sql", "ora-concat-num"), "oracle", "postgresql"
        )
        assert "'a' || 5" in out and "CAST(5 AS TEXT)" not in out, out

    def test_unknown_column_operand_stays_bare(self) -> None:
        # col type unknown: PG resolves if col is text; we do not guess/cast.
        out = _tx("SELECT col || 'x' AS r FROM t", "oracle", "postgresql")
        assert "col || 'x'" in out and "CAST(" not in out, out

    def test_numeric_chain_casts_only_the_all_numeric_node(self) -> None:
        out = _tx("SELECT 2 || 3 || 4 AS r FROM DUAL", "oracle", "postgresql")
        assert "CAST(2 AS TEXT) || CAST(3 AS TEXT) || 4" in out, out


class TestLikeBackslashEscape:
    """PG/MySQL LIKE use backslash as the default escape char; Oracle/T-SQL have
    none. A backslash pattern gets an explicit ``ESCAPE '\\'`` so the literal
    wildcard match is preserved."""

    @pytest.mark.parametrize("target", ("oracle", "tsql"))
    def test_backslash_pattern_gets_escape(self, target: str) -> None:
        out = _tx(_case("challenge_mysql.sql", "my-like-escape"), "mysql", target)
        assert "ESCAPE '\\'" in out, out


class TestSetOperationAll:
    """INTERSECT ALL / EXCEPT ALL keep duplicates — the ALL was dropped (the row
    multiset silently changed). MySQL (8.0.31+) and PG preserve it; Oracle/T-SQL
    (no ALL form) fall back to the distinct spelling."""

    def test_except_all_preserved_into_mysql(self) -> None:
        out = _tx(
            _case("challenge_postgresql.sql", "pg-except-all"), "postgresql", "mysql"
        )
        assert "EXCEPT ALL" in out, out

    def test_intersect_all_preserved_into_mysql(self) -> None:
        out = _tx(
            _case("challenge_postgresql.sql", "pg-intersect-all"), "postgresql", "mysql"
        )
        assert "INTERSECT ALL" in out, out


class TestMoneyCastType:
    """T-SQL MONEY/SMALLMONEY are fixed-scale decimals — mapped in a CAST target
    too (not only as a column type): NUMBER(19,4)/(10,4) on Oracle, NUMERIC on
    PG, DECIMAL on MySQL."""

    def test_money_arith_cast_into_oracle_pg(self) -> None:
        src = _case("challenge_sqlserver.sql", "ts-money-arith")
        assert "CAST(10.5 AS NUMBER(19,4))" in _tx(src, "tsql", "oracle")
        assert "NUMERIC(19,4)" in _tx(src, "tsql", "postgresql")
        assert "AS MONEY" not in _tx(src, "tsql", "oracle").upper()


class TestInitcapSingleArg:
    """PG/Oracle INITCAP take one argument; sqlglot's appended delimiter set
    (a 2-arg Snowflake form) is dropped. T-SQL/MySQL have none → degrade."""

    def test_initcap_into_oracle_single_arg(self) -> None:
        out = _tx(
            _case("challenge_postgresql.sql", "pg-initcap"), "postgresql", "oracle"
        )
        assert "INITCAP('hello world')" in out, out

    def test_initcap_into_tsql_degrades(self) -> None:
        r = Transpiler().transpile(
            _case("challenge_postgresql.sql", "pg-initcap"), "postgresql", "tsql"
        )
        assert "-- UNIQUE-" in r.sql and r.warnings, r.sql


class TestDatetimeFromParts:
    """T-SQL ``DATETIMEFROMPARTS(y,mo,d,h,mi,s,ms)`` constructs a timestamp:
    PG make_timestamp, Oracle TO_TIMESTAMP + interval, MySQL TIMESTAMP + interval
    — no leaked TIMESTAMP_FROM_PARTS."""

    def test_datetimefromparts_per_engine(self) -> None:
        src = _case("challenge_sqlserver.sql", "ts-datetimefromparts")
        assert "make_timestamp(" in _tx(src, "tsql", "postgresql")
        oracle = _tx(src, "tsql", "oracle")
        assert "TO_TIMESTAMP(" in oracle and "NUMTODSINTERVAL(" in oracle
        assert "TIMESTAMP(CONCAT(" in _tx(src, "tsql", "mysql")
        for tgt in ("postgresql", "oracle", "mysql"):
            assert "_FROM_PARTS" not in _exec_lines(_tx(src, "tsql", tgt)).upper()


class TestSequenceNextValue:
    """T-SQL ``NEXT VALUE FOR seq`` maps to Oracle ``seq.NEXTVAL`` and PG
    ``nextval('seq')``; MySQL (no sequences) degrades with a warning."""

    def test_next_value_for_into_oracle_and_pg(self) -> None:
        src = _case("challenge_sqlserver.sql", "ts-sequence-next")
        assert "seq.NEXTVAL" in _tx(src, "tsql", "oracle")
        assert "nextval('seq')" in _tx(src, "tsql", "postgresql")

    def test_next_value_for_mysql_degrades(self) -> None:
        r = Transpiler().transpile(
            _case("challenge_sqlserver.sql", "ts-seq-use"), "tsql", "mysql"
        )
        assert "-- UNIQUE-" in r.sql and r.warnings, r.sql


class TestNcharCharCodePoint:
    """T-SQL ``CHAR(n)``/``NCHAR(n)`` (code point → character) map to each
    engine's spelling: Oracle CHR/NCHR, PG CHR, MySQL CHAR(... USING cs) — and
    MySQL needs a charset so the result is a character, not a BINARY string."""

    def test_char_nchar_into_each_engine(self) -> None:
        src = _case("challenge_sqlserver.sql", "ts-ascii-char")
        assert "NCHR(65)" in _tx(src, "tsql", "oracle"), _tx(src, "tsql", "oracle")
        my = _tx(src, "tsql", "mysql")
        assert "CHAR(65 USING latin1)" in my and "CHAR(65 USING utf32)" in my, my
        assert "NCHAR(" not in _exec_lines(my), my  # no leaked NCHAR


class TestTsqlBeginTransaction:
    """``BEGIN TRANSACTION`` maps to each engine's transaction-open form; Oracle
    (implicit transactions) drops it with a documented carrier + warning."""

    def _case_sql(self) -> str:
        return _case("challenge_sqlserver.sql", "BEGIN TRANSACTION")

    def test_tsql_keeps_begin_transaction(self) -> None:
        assert "BEGIN TRANSACTION" in _tx(self._case_sql(), "tsql", "tsql")

    @pytest.mark.parametrize("target", ("postgresql", "mysql"))
    def test_other_engines_open_a_transaction(self, target: str) -> None:
        body = _exec_lines(_tx(self._case_sql(), "tsql", target))
        assert re.search(r"(?i)\bBEGIN\b|\bSTART TRANSACTION\b", body), body

    def test_oracle_drops_with_warning(self) -> None:
        result = Transpiler().transpile(
            self._case_sql(), source="tsql", target="oracle"
        )
        assert "BEGIN" not in _exec_lines(result.sql), result.sql
        assert any("BEGIN TRANSACTION dropped" in w.message for w in result.warnings), [
            w.message for w in result.warnings
        ]


class TestLpadShrink:
    """LPAD whose target length is shorter than the string truncates it to the
    LEFT n chars (LPAD('hello', 3) = 'hel'); the T-SQL LEFT(REPLICATE(...)) form
    pads nothing (CASE ... ELSE 0) and keeps only LEFT(s, n) (live-verified)."""

    def test_pg_lpad_shrink_keeps_left_chars(self) -> None:
        out = _tx(
            _case("challenge_postgresql.sql", "pg-lpad-shrink"), "postgresql", "tsql"
        )
        assert "ELSE 0 END) + LEFT('hello', 3)" in out, out

    def test_mysql_lpad_trunc_keeps_left_chars(self) -> None:
        out = _tx(_case("challenge_mysql.sql", "my-lpad-trunc"), "mysql", "tsql")
        assert "ELSE 0 END) + LEFT('abc', 2)" in out, out


class TestLogBase10:
    """A 1-arg LOG in the IR only ever comes from PostgreSQL, whose LOG(x) is
    base-10 (MySQL/T-SQL LOG(x) is the natural log → LN; Oracle's LOG needs two
    args). The base-10 sense must be named explicitly, and T-SQL's native LOG10
    is used for the two-arg base-10 case to avoid LOG(x, 10)'s float drift."""

    def test_pg_single_arg_log_is_base_10(self) -> None:
        assert "LOG10(100)" in _tx(
            _case("challenge_postgresql.sql", "pg-log-base"), "postgresql", "tsql"
        )
        assert "LOG10(100)" in _tx(
            _case("challenge_postgresql.sql", "pg-log-base"), "postgresql", "mysql"
        )
        assert "LOG(10, 100)" in _tx(
            _case("challenge_postgresql.sql", "pg-log-base"), "postgresql", "oracle"
        )

    def test_tsql_base_10_uses_native_log10(self) -> None:
        out = _tx(_case("challenge_mysql.sql", "my-log2-log10"), "mysql", "tsql")
        assert "LOG10(1000)" in out, out
        assert "LOG(8, 2)" in out, out  # LOG2 keeps the general arg-swapped form


class TestWindowFramePreserved:
    """A window frame (ROWS/RANGE BETWEEN …) is standard SQL on every engine, but
    the IR dropped it — silently turning a running total into a grand total. It is
    now captured and emitted verbatim (live-verified: PG's [1, 3] running sum is
    reproduced on T-SQL, Oracle and MySQL)."""

    @pytest.mark.parametrize("target", ("tsql", "oracle", "mysql"))
    def test_rows_frame_survives(self, target: str) -> None:
        out = _tx(_case("challenge_postgresql.sql", "qdrop-ROWS"), "postgresql", target)
        assert "ROWS BETWEEN 1 PRECEDING AND CURRENT ROW" in out, out


class TestGroupByRollup:
    """GROUP BY ROLLUP was dropped by the IR — MySQL's ``x WITH ROLLUP`` lost the
    subtotal rows and, worse, the standard ``ROLLUP(x)`` spelling lost the entire
    GROUP BY. MySQL trails ``WITH ROLLUP``; every other engine wraps the columns.
    Live-verified: the super-aggregate (NULL) rows are reproduced on all engines
    (multiset compare — the cases carry no ORDER BY)."""

    @pytest.mark.parametrize("target", ("tsql", "oracle", "postgresql"))
    def test_mysql_with_rollup_becomes_standard_rollup(self, target: str) -> None:
        out = _tx(_case("challenge_mysql.sql", "qdrop-ROLLUP"), "mysql", target)
        assert "GROUP BY ROLLUP(x)" in out, out

    @pytest.mark.parametrize("target", ("tsql", "oracle"))
    def test_pg_rollup_survives_as_standard(self, target: str) -> None:
        out = _tx(_case("challenge_postgresql.sql", "pg-rollup2"), "postgresql", target)
        assert "GROUP BY ROLLUP(a, b)" in out, out

    def test_pg_rollup_to_mysql_uses_with_rollup(self) -> None:
        out = _tx(
            _case("challenge_postgresql.sql", "pg-rollup2"), "postgresql", "mysql"
        )
        assert "GROUP BY a, b WITH ROLLUP" in out, out

    @pytest.mark.parametrize("target", ("oracle", "postgresql"))
    def test_cube_survives_natively(self, target: str) -> None:
        out = _tx(_case("challenge_sqlserver.sql", "ts-cube"), "tsql", target)
        assert "GROUP BY CUBE(a, b)" in out, out

    def test_cube_to_mysql_degrades_with_carrier(self) -> None:
        # MySQL has no CUBE: keep the base grouping, but never silently — a
        # carrier + warning must document the omitted super-aggregate rows.
        result = Transpiler().transpile(
            _case("challenge_sqlserver.sql", "ts-cube"), "tsql", "mysql"
        )
        assert "CUBE" not in _exec_lines(result.sql).upper(), result.sql
        assert "UNIQUE-1016: MySQL has no GROUP BY CUBE" in result.sql, result.sql
        assert any("CUBE" in w.message for w in result.warnings), [
            w.message for w in result.warnings
        ]

    @pytest.mark.parametrize("target", ("oracle", "tsql"))
    def test_grouping_sets_survives_natively(self, target: str) -> None:
        out = _tx(
            _case("challenge_postgresql.sql", "pg-grouping-sets"), "postgresql", target
        )
        assert "GROUP BY GROUPING SETS ((x), ())" in out, out

    def test_grouping_sets_to_mysql_degrades_with_carrier(self) -> None:
        result = Transpiler().transpile(
            _case("challenge_oracle.sql", "ora-grouping-sets"), "oracle", "mysql"
        )
        assert "GROUPING SETS" not in _exec_lines(result.sql).upper(), result.sql
        assert (
            "UNIQUE-1016: MySQL has no GROUP BY GROUPING SETS" in result.sql
        ), result.sql
        assert any("GROUPING SETS" in w.message for w in result.warnings), [
            w.message for w in result.warnings
        ]


class TestForUpdateLockCarrier:
    """PostgreSQL's FOR UPDATE row lock has no trailing-clause form on T-SQL
    (sqlglot drops it silently); Oracle/MySQL keep it. On T-SQL the loss is now
    surfaced as a documented carrier + warning, and the SQL stays valid."""

    def test_tsql_surfaces_a_warning_and_carrier(self) -> None:
        result = Transpiler().transpile(
            _case("challenge_postgresql.sql", "qdrop-FOR"), "postgresql", "tsql"
        )
        assert "FOR UPDATE" not in _exec_lines(result.sql).upper(), result.sql
        assert "UNIQUE-1143: T-SQL has no FOR UPDATE" in result.sql, result.sql
        assert any("FOR UPDATE" in w.message for w in result.warnings), [
            w.message for w in result.warnings
        ]

    @pytest.mark.parametrize("target", ("oracle", "mysql"))
    def test_oracle_mysql_keep_the_lock(self, target: str) -> None:
        out = _tx(_case("challenge_postgresql.sql", "qdrop-FOR"), "postgresql", target)
        assert "FOR UPDATE" in out.upper(), out
        assert "UNIQUE-" not in out, out


class TestAlterNotValidStripped:
    """PostgreSQL's ADD CONSTRAINT … NOT VALID (defer validating existing rows)
    has no equivalent elsewhere and passed through as a syntax error. It is now
    stripped — the constraint definition is identical — leaving valid SQL, with a
    carrier + warning documenting the target's immediate validation."""

    @pytest.mark.parametrize("keyword", ("pg-alter-notvalid", "pg-check-notvalid"))
    @pytest.mark.parametrize("target", ("tsql", "oracle", "mysql"))
    def test_not_valid_is_stripped_with_carrier(
        self, keyword: str, target: str
    ) -> None:
        result = Transpiler().transpile(
            _case("challenge_postgresql.sql", keyword), "postgresql", target
        )
        assert "NOT VALID" not in _exec_lines(result.sql).upper(), result.sql
        assert "UNIQUE-1108:" in result.sql and "NOT VALID" in result.sql, result.sql
        assert any("NOT VALID" in w.message for w in result.warnings), [
            w.message for w in result.warnings
        ]


class TestGeneratedColumn:
    """``GENERATED ALWAYS AS (expr)`` is a COMPUTED column, but sqlglot models it
    with the identity node — it was corrupted into ``IDENTITY(1,1)`` (an
    auto-increment). It now emits each engine's computed-column form: T-SQL
    ``b AS (expr)`` (no declared type), PG ``… GENERATED ALWAYS AS (expr) STORED``,
    Oracle/MySQL the VIRTUAL form. Live-verified: a=5 yields b=6 on all three."""

    _GEN = "CREATE TABLE t (a INT, b INT GENERATED ALWAYS AS (a + 1))"

    def test_generated_always_is_computed_not_identity(self) -> None:
        out = _tx(self._GEN, "mysql", "tsql")
        assert "b AS (a + 1)" in out, out
        assert "IDENTITY" not in out.upper(), out

    def test_pg_uses_stored_generated(self) -> None:
        out = _tx(self._GEN, "mysql", "postgresql")
        assert "GENERATED ALWAYS AS (a + 1) STORED" in out, out

    def test_oracle_keeps_generated_expression(self) -> None:
        out = _tx(self._GEN, "mysql", "oracle")
        assert "GENERATED ALWAYS AS (a + 1)" in out, out
        assert "IDENTITY" not in out.upper(), out

    def test_mysql_shorthand_computed_column_survives_on_tsql(self) -> None:
        # The corpus case uses MySQL's ``AS (expr) STORED`` shorthand (a distinct
        # sqlglot node); its computed column reaches T-SQL as ``AS … PERSISTED``
        # (live-verified valid) rather than being dropped.
        out = _tx(_case("challenge_mysql.sql", "drop-GENERATED"), "mysql", "tsql")
        assert re.search(r"(?i)\bb\s+AS\b.*\ba\s*\+\s*1", _exec_lines(out)), out
        assert "IDENTITY" not in out.upper(), out


class TestCreateIndexConcurrently:
    """PostgreSQL's CREATE INDEX CONCURRENTLY (non-locking build) has no T-SQL or
    MySQL equivalent; the index is identical, so the option is dropped but never
    silently — a carrier + warning documents the target's default locking."""

    @pytest.mark.parametrize("target", ("tsql", "mysql"))
    def test_concurrently_dropped_with_carrier(self, target: str) -> None:
        result = Transpiler().transpile(
            _case("challenge_postgresql.sql", "drop2-CONCURRENTLY"),
            "postgresql",
            target,
        )
        assert "CONCURRENTLY" not in _exec_lines(result.sql).upper(), result.sql
        assert "UNIQUE-1115: CONCURRENTLY" in result.sql, result.sql
        assert any("CONCURRENTLY" in w.message for w in result.warnings), [
            w.message for w in result.warnings
        ]


class TestIdentitySeedPreserved:
    """An IDENTITY seed/step (T-SQL ``IDENTITY(100, 5)``, PG/Oracle ``START WITH
    100 INCREMENT BY 5``) must survive so the sequence does not silently restart
    at 1 on the target (RC-3). Live-verified: the first inserted row gets id 100."""

    def test_tsql_seed_into_pg(self) -> None:
        out = _tx(_case("challenge_sqlserver.sql", "drop2-100"), "tsql", "postgresql")
        assert "START WITH 100 INCREMENT BY 5" in out, out

    def test_oracle_seed_into_tsql(self) -> None:
        out = _tx(_case("challenge_oracle.sql", "drop2-100"), "oracle", "tsql")
        assert "IDENTITY(100," in out, out

    @pytest.mark.parametrize("target", ("oracle", "tsql"))
    def test_pg_seed_and_step_survive(self, target: str) -> None:
        out = _tx(_case("challenge_postgresql.sql", "drop2-100"), "postgresql", target)
        assert "100" in _exec_lines(out) and (
            "START WITH 100 INCREMENT BY 5" in out or "IDENTITY(100,5)" in out
        ), out


class TestCheckInConstraintPreserved:
    """A ``CHECK (a IN (…))`` constraint must survive to every engine and keep
    enforcing (live-verified: a value outside the set is rejected)."""

    @pytest.mark.parametrize("target", ("tsql", "mysql", "oracle"))
    def test_check_in_survives(self, target: str) -> None:
        out = _tx(
            _case("challenge_postgresql.sql", "drop5-CHECK"), "postgresql", target
        )
        assert "CHECK (a IN (1, 2, 3))" in out, out


class TestExcludeConstraintCarrier:
    """PostgreSQL's EXCLUDE exclusion constraint has no equivalent on any other
    engine; it was dropped silently. It now degrades to a documented carrier +
    warning (the table itself stays valid), never a silent loss."""

    @pytest.mark.parametrize("target", ("tsql", "mysql", "oracle"))
    def test_exclude_degrades_with_carrier(self, target: str) -> None:
        result = Transpiler().transpile(
            _case("challenge_postgresql.sql", "drop2-EXCLUDE"), "postgresql", target
        )
        assert "EXCLUDE" not in _exec_lines(result.sql).upper(), result.sql
        assert "UNIQUE-1146: PostgreSQL EXCLUDE" in result.sql, result.sql
        assert any("EXCLUDE" in w.message for w in result.warnings), [
            w.message for w in result.warnings
        ]


class TestOnUpdateTimestampCarrier:
    """MySQL's ``ON UPDATE CURRENT_TIMESTAMP`` auto-update column attribute has no
    column-level equivalent on T-SQL/Oracle/PG (they need a trigger); it was
    dropped silently and now degrades to a documented carrier + warning while the
    table stays valid. MySQL keeps the clause inline."""

    @pytest.mark.parametrize("target", ("tsql", "oracle", "postgresql"))
    def test_on_update_degrades_with_carrier(self, target: str) -> None:
        result = Transpiler().transpile(
            _case("challenge_mysql.sql", "drop2-ON"), "mysql", target
        )
        assert "ON UPDATE" not in _exec_lines(result.sql).upper(), result.sql
        assert (
            "UNIQUE-1050: MySQL's" in result.sql and "ON UPDATE" in result.sql
        ), result.sql
        assert any("ON UPDATE" in w.message for w in result.warnings), [
            w.message for w in result.warnings
        ]


class TestByDefaultIdentityIntoTsql:
    """PostgreSQL's ``GENERATED BY DEFAULT AS IDENTITY`` maps to T-SQL's native
    ``IDENTITY(1,1)`` (T-SQL has no GENERATED/BY DEFAULT keyword — that spelling
    is the faithful equivalent). Live-verified: the first inserted row gets id 1."""

    def test_identity_survives_into_tsql(self) -> None:
        out = _tx(_case("challenge_postgresql.sql", "drop4-BY"), "postgresql", "tsql")
        assert "IDENTITY(1,1)" in out, out


class TestMemoryOptimizedCarrier:
    """T-SQL's WITH (MEMORY_OPTIMIZED = ON) is a physical In-Memory OLTP storage
    option (no logical/value impact) with no equivalent elsewhere; it was dropped
    silently. Off T-SQL it now degrades to a documented carrier + warning while
    the table stays valid (a regular disk table)."""

    @pytest.mark.parametrize("target", ("postgresql", "mysql", "oracle"))
    def test_memory_optimized_degrades_with_carrier(self, target: str) -> None:
        result = Transpiler().transpile(
            _case("challenge_sqlserver.sql", "drop5-MEMORY"), "tsql", target
        )
        assert "MEMORY_OPTIMIZED" not in _exec_lines(result.sql).upper(), result.sql
        assert "UNIQUE-1056: T-SQL In-Memory OLTP" in result.sql, result.sql
        assert any("MEMORY_OPTIMIZED" in w.message for w in result.warnings), [
            w.message for w in result.warnings
        ]


class TestCollationCarrier:
    """Collation names are engine-specific (Oracle BINARY_CI, PG "en_US", MySQL
    utf8mb4_…) with no portable mapping; a dropped COLLATE was silent. Off the
    source engine it now degrades to a documented carrier + warning (a live DB
    connection could resolve the actual collation), and the table stays valid."""

    def test_oracle_column_collate_carried(self) -> None:
        result = Transpiler().transpile(
            _case("challenge_oracle.sql", "drop4-COLLATE"), "oracle", "tsql"
        )
        assert "COLLATE" not in _exec_lines(result.sql).upper(), result.sql
        assert "UNIQUE-1051:" in result.sql and "collation" in result.sql, result.sql
        assert any("collation" in w.message for w in result.warnings), result.sql

    def test_pg_column_collate_carried(self) -> None:
        result = Transpiler().transpile(
            _case("challenge_postgresql.sql", "drop4-COLLATE"), "postgresql", "mysql"
        )
        assert "UNIQUE-1051:" in result.sql and "collation" in result.sql, result.sql
        assert result.warnings, result.sql

    @pytest.mark.parametrize("target", ("oracle", "postgresql"))
    def test_mysql_table_collate_carried(self, target: str) -> None:
        result = Transpiler().transpile(
            _case("challenge_mysql.sql", "drop4-COLLATE|utf8"), "mysql", target
        )
        assert "COLLATE" not in _exec_lines(result.sql).upper(), result.sql
        assert "UNIQUE-1057:" in result.sql and "collation" in result.sql, result.sql
        assert any("collation" in w.message for w in result.warnings), result.sql


class TestCharacterSetCarrier:
    """MySQL CHARACTER SET / DEFAULT CHARSET (column and table level) is
    engine-specific with no portable mapping; a dropped charset was silent. Off
    MySQL it degrades to a documented carrier + warning while the table stays
    valid (same contract as a dropped COLLATE)."""

    def test_column_character_set_carried(self) -> None:
        result = Transpiler().transpile(
            _case("challenge_mysql.sql", "drop2-latin1"), "mysql", "oracle"
        )
        assert "CHARACTER SET" not in _exec_lines(result.sql).upper(), result.sql
        assert "UNIQUE-1051:" in result.sql and "charset" in result.sql, result.sql
        assert result.warnings, result.sql

    @pytest.mark.parametrize("target", ("oracle", "postgresql", "tsql"))
    def test_table_default_charset_carried(self, target: str) -> None:
        result = Transpiler().transpile(
            _case("challenge_mysql.sql", "drop5-utf8mb4"), "mysql", target
        )
        assert "CHARSET" not in _exec_lines(result.sql).upper(), result.sql
        assert "UNIQUE-1057:" in result.sql and "charset" in result.sql, result.sql
        assert result.warnings, result.sql


class TestUnsignedCheck:
    """A MySQL UNSIGNED integer widens to a type that holds its range (INT
    UNSIGNED -> BIGINT), and the non-negativity — which the other engines can't
    put in the type — is preserved with CHECK (col >= 0). Live-verified: the max
    unsigned value stores and a negative is rejected."""

    @pytest.mark.parametrize("target", ("tsql", "oracle", "postgresql"))
    def test_unsigned_adds_nonnegative_check(self, target: str) -> None:
        out = _tx(_case("challenge_mysql.sql", "drop4-UNSIGNED"), "mysql", target)
        assert re.search(r"(?i)CHECK\s*\(\s*a\s*>=\s*0\s*\)", out), out

    def test_mysql_keeps_unsigned(self) -> None:
        out = _tx(_case("challenge_mysql.sql", "drop4-UNSIGNED"), "mysql", "mysql")
        assert "UNSIGNED" in out.upper(), out


class TestDateLiteralSubtraction:
    """``DATE 'a' - DATE 'b'`` is a day count: Oracle/PG subtract dates natively,
    T-SQL/MySQL need DATEDIFF. sqlglot's DATE_STR_TO_DATE wrapper unwrapped to a
    bare string, so ``str - str`` computed nothing. Live-verified: 60 days on all
    four engines."""

    def test_tsql_uses_datediff(self) -> None:
        out = _tx(_case("challenge_oracle.sql", "date-diff-days"), "oracle", "tsql")
        assert "DATEDIFF(DAY," in out and "AS DATE)" in out, out

    def test_pg_subtracts_dates(self) -> None:
        out = _tx(
            _case("challenge_oracle.sql", "date-diff-days"), "oracle", "postgresql"
        )
        assert "DATE '2020-03-01' - DATE '2020-01-01'" in out, out

    def test_mysql_uses_datediff(self) -> None:
        out = _tx(_case("challenge_oracle.sql", "date-diff-days"), "oracle", "mysql")
        assert "DATEDIFF(CAST(" in out, out


class TestMysqlModByZero:
    """MySQL's ``x MOD 0`` returns NULL; the other engines error (PG/T-SQL) or
    return the dividend (Oracle). The MySQL->other emit guards the divisor with
    ``CASE WHEN divisor = 0 THEN NULL`` so the value matches. Live-verified:
    ``5 MOD 0 IS NULL`` is 1 on Oracle."""

    @pytest.mark.parametrize("keyword", ("my-mod-zero", "my-mod-edge"))
    @pytest.mark.parametrize("target", ("oracle", "postgresql", "tsql"))
    def test_mod_zero_guarded(self, keyword: str, target: str) -> None:
        out = _tx(_case("challenge_mysql.sql", keyword), "mysql", target)
        assert re.search(r"(?i)CASE\s+WHEN\s+0\s*=\s*0\s+THEN\s+NULL", out), out


class TestTruncateRestartIdentity:
    """PG TRUNCATE … RESTART IDENTITY / CASCADE: RESTART IDENTITY is the default
    on MySQL/Oracle/T-SQL (strip it), CASCADE is kept on Oracle but carriered on
    MySQL/T-SQL. Live-verified valid on all targets."""

    @pytest.mark.parametrize("target", ("mysql", "oracle", "tsql"))
    def test_restart_identity_stripped(self, target: str) -> None:
        out = _tx(
            _case("challenge_postgresql.sql", "pg-truncate-restart"),
            "postgresql",
            target,
        )
        sql_only = "\n".join(
            ln for ln in out.splitlines() if not ln.lstrip().startswith("--")
        )
        assert not re.search(r"(?i)RESTART\s+IDENTITY", sql_only), out

    def test_cascade_kept_on_oracle_stripped_elsewhere(self) -> None:
        ora = _tx("TRUNCATE TABLE t RESTART IDENTITY CASCADE", "postgresql", "oracle")
        assert re.search(r"(?i)TRUNCATE\s+TABLE\s+t\s+CASCADE", ora), ora
        res = Transpiler().transpile(
            "TRUNCATE TABLE t RESTART IDENTITY CASCADE",
            source="postgresql",
            target="mysql",
        )
        assert (
            re.search(r"(?i)UNIQUE-1109:.*CASCADE", res.sql) and res.warnings
        ), res.sql


class TestIndexNullsOrderCarrier:
    """NULLS FIRST/LAST on an index column has no equivalent on Oracle (ORA-00907
    in an index), T-SQL or MySQL; the drop (physical null-order only, no query
    result impact) is surfaced as a carrier + warning, not dropped silently."""

    @pytest.mark.parametrize("target", ("oracle", "tsql", "mysql"))
    def test_carrier_and_warning(self, target: str) -> None:
        res = Transpiler().transpile(
            _case("challenge_postgresql.sql", "postgresql-drop2-NULLS"),
            source="postgresql",
            target=target,
        )
        assert re.search(r"(?i)UNIQUE-1004:.*NULLS\s+FIRST/LAST", res.sql), res.sql
        assert res.warnings, "expected a loss warning"

    def test_plain_index_has_no_carrier(self) -> None:
        res = Transpiler().transpile(
            "CREATE INDEX ix ON t (a)", source="postgresql", target="oracle"
        )
        assert "UNIQUE-" not in res.sql, res.sql


class TestMysqlComments:
    """MySQL column and table COMMENT materialize on PG/Oracle (COMMENT ON
    COLUMN / COMMENT ON TABLE) rather than being dropped silently."""

    @pytest.mark.parametrize("target", ("oracle", "postgresql"))
    def test_column_comment_materializes(self, target: str) -> None:
        out = _tx(_case("challenge_mysql.sql", "mysql-drop-'note'"), "mysql", target)
        assert re.search(r"(?i)COMMENT\s+ON\s+COLUMN\s+t\.a\s+IS\s+'note'", out), out

    @pytest.mark.parametrize("target", ("oracle", "postgresql"))
    def test_table_comment_materializes(self, target: str) -> None:
        out = _tx(_case("challenge_mysql.sql", "mysql-drop2-my"), "mysql", target)
        assert re.search(r"(?i)COMMENT\s+ON\s+TABLE\s+t\s+IS\s+'my table'", out), out


class TestMysqlSqlCalcFoundRows:
    """MySQL SQL_CALC_FOUND_ROWS has no equivalent on other engines; the drop is
    surfaced as a carrier + warning (mirrored by the no-silent-loss scan) rather
    than dropped silently. The underlying SELECT stays valid."""

    @pytest.mark.parametrize("target", ("oracle", "postgresql", "tsql"))
    def test_carrier_and_warning(self, target: str) -> None:
        res = Transpiler().transpile(
            _case("challenge_mysql.sql", "mysql-qdrop-SQL_CALC_FOU"),
            source="mysql",
            target=target,
        )
        assert "SQL_CALC_FOUND_ROWS" in res.sql, res.sql  # in the carrier comment
        assert res.warnings, "expected a value/loss warning"

    def test_plain_select_has_no_carrier(self) -> None:
        res = Transpiler().transpile("SELECT x FROM t", source="mysql", target="tsql")
        assert "UNIQUE-" not in res.sql, res.sql


class TestMysqlDatetimePrecision:
    """MySQL DATETIME(n)/TIMESTAMP(n) carry fractional-seconds precision. T-SQL
    DATETIME takes no width (error 2716), so DATETIME(n) -> DATETIME2(n); Oracle
    TIMESTAMP's precision goes inside the type (TIMESTAMP(n) WITH TIME ZONE, not
    ...WITH TIME ZONE(n)). Live-verified valid on all targets."""

    def test_tsql_datetime_precision_uses_datetime2(self) -> None:
        out = _tx(
            _case("challenge_mysql.sql", "my-datetime-precision"), "mysql", "tsql"
        )
        assert re.search(r"(?i)DATETIME2\(6\)", out), out

    def test_oracle_timestamp_precision_inside_type(self) -> None:
        out = _tx(
            _case("challenge_mysql.sql", "my-datetime-precision"), "mysql", "oracle"
        )
        assert re.search(r"(?i)TIMESTAMP\(3\)\s+WITH\s+TIME\s+ZONE", out), out

    def test_tsql_bare_datetime_unchanged(self) -> None:
        # A DATETIME with no precision must stay DATETIME (no width, no churn).
        out = _tx("CREATE TABLE t (a DATETIME)", "mysql", "tsql")
        assert re.search(r"(?i)\bDATETIME\b", out) and "DATETIME2" not in out.upper()


class TestOracleTimestampCast:
    """Oracle CAST(x AS TIMESTAMP): MySQL has no TIMESTAMP cast target (1064) so
    it must be DATETIME, and T-SQL TIMESTAMP is a rowversion (binary), not a
    datetime, so it must be DATETIME2 to keep the value."""

    @pytest.mark.parametrize(
        "target,ty", [("mysql", "DATETIME"), ("tsql", "DATETIME2")]
    )
    def test_timestamp_cast_maps(self, target: str, ty: str) -> None:
        out = _tx("SELECT CAST(SYSDATE AS TIMESTAMP) AS r", "oracle", target)
        assert re.search(rf"(?i)CAST\(.*AS {ty}\)", out), out
        assert not re.search(r"(?i)AS\s+TIMESTAMP\)", out), out


class TestOracleAddMonthsPgTypedLiteral:
    """Oracle ADD_MONTHS(DATE 'lit', n) on a PG target: the ISO date literal must
    be typed (DATE '…'), else PG's DATE_TRUNC has no unique overload for an
    untyped string ("date_trunc(unknown, unknown) is not unique"). Live-verified
    2020-02-29 (sticky last-day). A column operand is left untyped."""

    def test_pg_types_the_date_literal(self) -> None:
        out = _tx(
            "SELECT ADD_MONTHS(DATE '2020-01-31', 1) AS r", "oracle", "postgresql"
        )
        assert re.search(r"(?i)DATE_TRUNC\('month',\s*DATE\s*'", out), out

    def test_pg_leaves_a_column_untyped(self) -> None:
        # A column operand needs no DATE wrapper (it is already typed).
        out = _tx("SELECT ADD_MONTHS(d, 1) AS r FROM t", "oracle", "postgresql")
        assert re.search(r"(?i)DATE_TRUNC\('month',\s*d\)", out), out


class TestOracleBitand:
    """Oracle BITAND(a, b) is a bitwise AND; the other engines (including PG,
    which has no BITAND) spell it with the & operator. Live-verified 2."""

    @pytest.mark.parametrize("target", ("mysql", "postgresql", "tsql"))
    def test_bitand_becomes_operator(self, target: str) -> None:
        out = _tx(_case("challenge_oracle.sql", "ora-bitand"), "oracle", target)
        sql_only = "\n".join(
            ln for ln in out.splitlines() if not ln.lstrip().startswith("--")
        )
        assert re.search(r"\(\s*5\s*&\s*3\s*\)", sql_only), out
        assert not re.search(r"(?i)BITAND\s*\(", sql_only), out


class TestMysqlTwoArgAtan:
    """MySQL ATAN(y, x) is the 2-argument arctangent (= ATAN2); Oracle/PG use
    ATAN2 and T-SQL uses ATN2. Live-verified pi/4."""

    @pytest.mark.parametrize(
        "target,fn", [("oracle", "ATAN2"), ("postgresql", "ATAN2"), ("tsql", "ATN2")]
    )
    def test_two_arg_atan_maps(self, target: str, fn: str) -> None:
        out = _tx(_case("challenge_mysql.sql", "my-trig"), "mysql", target)
        assert re.search(rf"(?i){fn}\(\s*1,\s*1\s*\)", out), out


class TestOracleExceptionConditionMapsToPg:
    """Oracle predefined exception names differ from PL/pgSQL condition names
    (ZERO_DIVIDE vs division_by_zero); emitting the Oracle spelling verbatim is
    rejected by PostgreSQL. The PG emitter maps the standard ones."""

    def test_zero_divide_maps_to_division_by_zero(self) -> None:
        out = _tx(
            _case("challenge_oracle.sql", "ora-zero-divide"), "oracle", "postgresql"
        )
        assert re.search(r"(?i)WHEN\s+division_by_zero\s+THEN", out), out
        assert not re.search(r"(?i)WHEN\s+ZERO_DIVIDE", out), out


class TestOracleDecodeNullSafe:
    """Oracle DECODE uses NULL-safe equality (a NULL search matches a NULL
    subject), unlike SQL '=' where NULL = NULL is unknown. The DECODE_CASE emit
    spells a NULL search as ``subject IS NULL`` (not ``= NULL``). Live-verified
    'match', not 'no'."""

    @pytest.mark.parametrize("target", ("mysql", "postgresql", "tsql"))
    def test_null_search_is_null(self, target: str) -> None:
        out = _tx(_case("challenge_oracle.sql", "ora-decode-null"), "oracle", target)
        assert re.search(r"(?i)WHEN\s+NULL\s+IS\s+NULL\s+THEN", out), out
        assert not re.search(r"(?i)WHEN\s+NULL\s*=\s*NULL", out), out

    def test_nonnull_search_uses_equality(self) -> None:
        # A non-NULL search keeps plain '=' (no IS NULL rewrite).
        out = _tx("SELECT DECODE(x, 1, 'a', 'b') AS r FROM t", "oracle", "tsql")
        assert re.search(r"(?i)WHEN\s+x\s*=\s*1\s+THEN", out), out


class TestOracleCastIntRounds:
    """Oracle CAST-to-integer ROUNDS (CAST('3.9' AS INT) = 4); MySQL's
    CAST(... AS SIGNED) truncates a string. The Oracle->MySQL emit rounds first
    so the value matches (live-verified: 4, not 3)."""

    def test_mysql_rounds_the_cast(self) -> None:
        out = _tx(_case("challenge_oracle.sql", "cast-int-edge"), "oracle", "mysql")
        assert "CAST(ROUND('3.9') AS SIGNED)" in out, out


class TestTsqlCastIntRounds:
    """PG/MySQL CAST-to-integer round a numeric literal half-away-from-zero
    (CAST(2.7 AS INT) = 3, 7.5 -> 8); T-SQL CAST truncates. The emit wraps
    ROUND(x, 0) on a T-SQL target (T-SQL ROUND is half-away-from-zero too).
    Live-verified 3/8, not 2/7."""

    @pytest.mark.parametrize(
        "src_file,src,keyword",
        [
            ("challenge_postgresql.sql", "postgresql", "pg-cast-int"),
            ("challenge_postgresql.sql", "postgresql", "pg-cast-round-half"),
            ("challenge_mysql.sql", "mysql", "my-cast-int"),
        ],
    )
    def test_tsql_rounds_the_cast(self, src_file: str, src: str, keyword: str) -> None:
        out = _tx(_case(src_file, keyword), src, "tsql")
        assert re.search(r"(?i)CAST\(\s*ROUND\(.*,\s*0\)\s*AS\b", out), out

    def test_integer_literal_cast_not_wrapped(self) -> None:
        # A non-fractional literal must not get a ROUND wrapper (no churn).
        out = _tx("SELECT CAST(5 AS INT) AS r", "postgresql", "tsql")
        assert "ROUND" not in out.upper(), out


class TestGreatestLeastNullPropagation:
    """MySQL's GREATEST/LEAST return NULL if any argument is NULL; PG and T-SQL
    ignore NULLs. The MySQL->PG/T-SQL emit guards with CASE WHEN <any> IS NULL
    THEN NULL. Live-verified NULL, not 3/1."""

    @pytest.mark.parametrize(
        "keyword,target",
        [
            ("my-greatest-null", "postgresql"),
            ("my-greatest-null", "tsql"),
            ("my-least-null2", "postgresql"),
            ("my-least-null2", "tsql"),
            ("my-greatest-null2", "postgresql"),
            ("my-least-greatest-null", "tsql"),
        ],
    )
    def test_null_propagates(self, keyword: str, target: str) -> None:
        out = _tx(_case("challenge_mysql.sql", keyword), "mysql", target)
        assert re.search(r"(?i)CASE\s+WHEN\b.*\bIS\s+NULL\b.*THEN\s+NULL", out), out


class TestGreatestLeastDropsNullFromPg:
    """PG/T-SQL GREATEST/LEAST ignore NULL args (GREATEST(1, NULL, 3) = 3);
    MySQL/Oracle propagate NULL. A literal NULL arg is dropped on those targets
    so the max/min over the survivors matches. Live-verified 3, not NULL."""

    @pytest.mark.parametrize("target", ("mysql", "oracle"))
    def test_literal_null_dropped(self, target: str) -> None:
        out = _tx(
            _case("challenge_postgresql.sql", "pg-greatest-null"), "postgresql", target
        )
        # GREATEST(1, 3) proves the NULL arg was dropped (it is not in the call).
        assert re.search(r"(?i)GREATEST\(\s*1,\s*3\s*\)", out), out


class TestSingleArgCoalesce:
    """A 1-arg COALESCE(x) is its argument; Oracle (ORA-00938) and T-SQL reject
    a single-argument COALESCE, so it is reduced to the argument."""

    @pytest.mark.parametrize("target", ("oracle", "tsql"))
    def test_reduced_to_argument(self, target: str) -> None:
        out = _tx(_case("challenge_mysql.sql", "my-coalesce-single"), "mysql", target)
        sql_only = "\n".join(
            ln for ln in out.splitlines() if not ln.lstrip().startswith("--")
        )
        assert not re.search(r"(?i)COALESCE\s*\(", sql_only), out


class TestNegativeLengthStringFns:
    """MySQL LEFT / REPEAT with a negative count return '' ; PostgreSQL LEFT
    reads it as "all but the last |n|" and T-SQL REPLICATE returns NULL. The
    MySQL-source emit clamps the count to 0. Live-verified empty string."""

    def test_left_negative_clamps(self) -> None:
        out = _tx(_case("challenge_mysql.sql", "my-left-neg"), "mysql", "postgresql")
        assert re.search(r"(?i)LEFT\(.*CASE\s+WHEN\b.*<\s*0\s+THEN\s+0", out), out

    def test_repeat_negative_clamps(self) -> None:
        out = _tx(_case("challenge_mysql.sql", "my-repeat-neg"), "mysql", "tsql")
        assert re.search(r"(?i)REPLICATE\(.*CASE\s+WHEN\b.*<\s*0\s+THEN\s+0", out), out

    def test_repeat_float_rounds(self) -> None:
        # MySQL rounds a float count (REPEAT('ab', 2.9) = 'ababab'); T-SQL
        # REPLICATE truncates it. Round first (with the scale arg T-SQL needs).
        out = _tx(_case("challenge_mysql.sql", "my-repeat-float"), "mysql", "tsql")
        assert re.search(r"(?i)ROUND\([^)]*,\s*0\)", out), out

    def test_left_float_rounds(self) -> None:
        # MySQL rounds a float length (LEFT('hello', 2.9) = 'hel'); T-SQL LEFT
        # truncates it.
        out = _tx(_case("challenge_mysql.sql", "my-left-float"), "mysql", "tsql")
        assert re.search(r"(?i)LEFT\(.*ROUND\([^)]*,\s*0\)", out), out


class TestMysqlInsertBounds:
    """MySQL INSERT() returns the original string when the position is 0 or past
    the end; T-SQL STUFF returns NULL there. The MySQL->T-SQL emit guards the
    bounds. Live-verified: out-of-bounds and position-0 keep the original."""

    @pytest.mark.parametrize("keyword", ("my-insert-oob", "my-insert-zeropos"))
    def test_bounds_guarded(self, keyword: str) -> None:
        out = _tx(_case("challenge_mysql.sql", keyword), "mysql", "tsql")
        assert re.search(r"(?i)CASE\s+WHEN\b.*<\s*1\s+OR\b.*>\s+LEN\(", out), out


class TestHavingNoGroupBy:
    """MySQL allows HAVING without GROUP BY on a non-aggregate (a post-window row
    filter); Oracle/PG/T-SQL require GROUP BY there. Wrap the query so HAVING
    becomes an outer WHERE, preserving window-then-filter. Live-verified."""

    def test_having_becomes_outer_where(self) -> None:
        for target in ("oracle", "postgresql", "tsql"):
            out = _tx(_case("challenge_mysql.sql", "my-having-noagg "), "mysql", target)
            body = "\n".join(
                ln for ln in out.splitlines() if not ln.lstrip().startswith("--")
            )
            assert "uq_h" in body and "WHERE x > 0" in body, body
            assert "HAVING" not in body, body


class TestMysqlDecimalDivision:
    """MySQL's / is always decimal division (SUM(x)/COUNT(x) = 1.5), but PG/T-SQL
    truncate two integers to an integer (1). Force decimal (* 1.0) on a MySQL
    source, including non-literal integer results like COUNT. Live-verified 1.5."""

    def test_sum_div_count_forces_decimal(self) -> None:
        case = _case("challenge_mysql.sql", "my-sum-div-count ")
        # NULLIF(COUNT(x), 0) preserves MySQL's NULL-safe division too.
        assert "SUM(x) * 1.0 / NULLIF(COUNT(x), 0)" in _tx(case, "mysql", "postgresql")
        assert "SUM(x) * 1.0 / NULLIF(COUNT(x), 0)" in _tx(case, "mysql", "tsql")


class TestMysqlSafeDivision:
    """MySQL ``/`` is NULL-safe (``x / 0`` → NULL, not an error); PG/T-SQL/Oracle
    raise. The converter reads sqlglot's ``Div.safe`` flag and preserves the
    semantics by wrapping the divisor in NULLIF(divisor, 0) — which also silences
    the guardrail-7 unread-args tripwire that false-fired on every MySQL division."""

    def test_safe_division_wraps_divisor_and_no_false_warning(self) -> None:
        r_pg = Transpiler().transpile(
            "SELECT a / b FROM t", source="mysql", target="postgresql"
        )
        assert "NULLIF(b, 0)" in r_pg.sql, r_pg.sql
        r_ora = Transpiler().transpile(
            "SELECT a / b FROM t", source="mysql", target="oracle"
        )
        assert "NULLIF(b, 0)" in r_ora.sql, r_ora.sql
        msgs = [
            w if isinstance(w, str) else getattr(w, "message", str(w))
            for w in (*r_pg.warnings, *r_ora.warnings)
        ]
        assert not any("'safe' on Div" in m for m in msgs), msgs
        # A non-MySQL source has no safe flag → no NULLIF wrapping.
        r_pg2 = Transpiler().transpile(
            "SELECT a / b FROM t", source="postgresql", target="tsql"
        )
        assert "NULLIF" not in r_pg2.sql, r_pg2.sql


class TestTimestampDifferenceDegrade:
    """``timestamp - timestamp`` is an INTERVAL on PG/Oracle but has no interval
    value type on T-SQL/MySQL — degrade to a SECOND count with a warned carrier
    (never the silent invalid/garbage raw subtraction)."""

    _SQL = (
        "SELECT TIMESTAMP '2020-01-01 12:00:00' - "
        "TIMESTAMP '2020-01-01 10:00:00' AS d"
    )

    def test_tsql_and_mysql_degrade_with_warning(self) -> None:
        for target, fn in (
            ("tsql", "DATEDIFF(SECOND,"),
            ("mysql", "TIMESTAMPDIFF(SECOND,"),
        ):
            r = Transpiler().transpile(self._SQL, source="postgresql", target=target)
            assert fn in r.sql, r.sql
            assert "UNIQUE-1075:" in r.sql and r.warnings, r.sql

    def test_oracle_keeps_native_interval(self) -> None:
        r = Transpiler().transpile(self._SQL, source="postgresql", target="oracle")
        assert "TIMESTAMP '2020-01-01 12:00:00' - " in r.sql, r.sql
        assert "DATEDIFF" not in r.sql, r.sql


class TestMysqlDateSubtraction:
    """MySQL's DATE - DATE is a numeric YYYYMMDD subtraction (2020-03-01 -
    2020-01-01 = 200), not a day count; the meaningful day count (60) is emitted
    with a documented carrier flagging the normalization."""

    def test_mysql_date_sub_carries(self) -> None:
        case = _case("challenge_mysql.sql", "my-date-diff-minus ")
        result = Transpiler().transpile(case, source="mysql", target="postgresql")
        assert result.warnings, "normalized date subtraction must warn"
        assert "UNIQUE-1074:" in result.sql, result.sql


class TestSubstringFloatArgs:
    """MySQL rounds a fractional SUBSTRING position/length (2.9 -> 3); Oracle/PG/
    T-SQL truncate (2). Pre-round the literal args on a MySQL source. Verified
    'llo'."""

    def test_float_args_rounded(self) -> None:
        case = _case("challenge_mysql.sql", "my-substr-float ")
        assert "SUBSTR('hello', 3, 3)" in _tx(case, "mysql", "oracle")
        assert "SUBSTRING('hello', 3, 3)" in _tx(case, "mysql", "tsql")


class TestReplaceCaseSensitive:
    """MySQL/Oracle/PG REPLACE matches case-sensitively; T-SQL uses the subject's
    (case-insensitive) collation, so REPLACE('AbCaBc','a','X') would also replace
    the 'A'. Force a BIN2 collation on a literal subject. Live-verified 'AbCXBc'."""

    def test_tsql_literal_subject_is_binary(self) -> None:
        out = _tx(_case("challenge_mysql.sql", "my-replace-case "), "mysql", "tsql")
        assert "REPLACE('AbCaBc' COLLATE Latin1_General_BIN2, 'a', 'X')" in out, out


class TestMysqlCharByteString:
    """MySQL CHAR(n) is byte-based: n > 255 yields a multi-byte byte string
    (CHAR(256) = 0x0100), not the single code point CHR gives on Oracle/PG.
    Emit CHR with a documented carrier + warning for the divergence."""

    def test_mysql_char_256_carries(self) -> None:
        case = _case("challenge_mysql.sql", "my-char-256 ")
        result = Transpiler().transpile(case, source="mysql", target="oracle")
        assert result.warnings, "byte-CHAR quirk must warn"
        assert "UNIQUE-1100:" in result.sql, result.sql


class TestChrUnicode:
    """PG/Oracle CHR(n) is a Unicode code point; above ASCII (n > 127) MySQL's
    byte CHAR gives the wrong bytes and T-SQL's CHAR returns NULL. Build the
    Unicode char — MySQL CHAR(n USING utf16), T-SQL NCHAR(n). Live-verified μ."""

    def test_chr_unicode(self) -> None:
        case = _case("challenge_postgresql.sql", "pg-chr-unicode ")
        assert "CHAR(956 USING utf16)" in _tx(case, "postgresql", "mysql")
        assert "NCHAR(956)" in _tx(case, "postgresql", "tsql")


class TestPositionCaseSensitive:
    """POSITION goes through the CHARINDEX path, so the INSTR case-sensitivity fix
    (BINARY/BIN2 on the literal haystack) applies — POSITION('a' IN 'ABC') = 0 on
    MySQL/T-SQL like PG."""

    def test_position_case_sensitive(self) -> None:
        case = _case("challenge_postgresql.sql", "pg-position-case ")
        assert "BINARY 'ABC'" in _tx(case, "postgresql", "mysql")
        assert "'ABC' COLLATE Latin1_General_BIN2" in _tx(case, "postgresql", "tsql")


class TestOrderByCaseSensitive:
    """A case-sensitive source (PG/Oracle) ordering a provably-string column comes
    back in the target's case-insensitive collation on MySQL/T-SQL; a binary
    collation on the key preserves the case-sensitive order. Live-verified."""

    def test_pg_order_case_sensitive(self) -> None:
        case = _case("challenge_postgresql.sql", "pg-order-case-sens ")
        assert "COLLATE utf8mb4_bin" in _tx(case, "postgresql", "mysql")
        assert "COLLATE Latin1_General_BIN2" in _tx(case, "postgresql", "tsql")

    def test_pg_distinct_case_sensitive(self) -> None:
        case = _case("challenge_postgresql.sql", "po-distinct-case ")
        out = _tx(case, "postgresql", "mysql")
        assert "DISTINCT x COLLATE utf8mb4_bin" in out, out

    def test_pg_group_case_sensitive(self) -> None:
        # SELECT, GROUP BY and ORDER BY keys are all collated consistently.
        out = _tx(
            _case("challenge_postgresql.sql", "po-group-case "), "postgresql", "mysql"
        )
        assert out.count("COLLATE utf8mb4_bin") >= 3, out

    def test_mysql_order_case_insensitive(self) -> None:
        # The reverse: a CI source on a CS target wraps the key in LOWER().
        case = _case("challenge_mysql.sql", "my-order-case-sens ")
        assert "ORDER BY LOWER(x)" in _tx(case, "mysql", "oracle")
        assert "ORDER BY LOWER(x)" in _tx(case, "mysql", "postgresql")


class TestGreatestCaseSensitive:
    """GREATEST/LEAST compare strings by collation: PG/Oracle are case-sensitive
    (GREATEST('a','B') = 'a'), MySQL/T-SQL default case-insensitive ('B'). Force a
    binary collation on the first string literal. Live-verified 'a'."""

    def test_greatest_case_sensitive(self) -> None:
        case = _case("challenge_postgresql.sql", "pg-greatest-string ")
        assert "GREATEST('a' COLLATE utf8mb4_bin, 'B')" in _tx(
            case, "postgresql", "mysql"
        )
        tsql = _tx(case, "postgresql", "tsql")
        assert "GREATEST('a' COLLATE Latin1_General_BIN2, 'B')" in tsql, tsql


class TestInstrCaseSensitive:
    """Oracle/PostgreSQL INSTR searches case-sensitively, but MySQL's and T-SQL's
    default collations are case-insensitive (INSTR('aAaA','A') = 1 not 2). Force a
    binary / BIN2 collation on the haystack so the match position matches the
    source. Live-verified 2 on MySQL and T-SQL."""

    def test_forces_case_sensitive_haystack(self) -> None:
        case = _case("challenge_oracle.sql", "ora-instr-case ")
        assert "BINARY 'aAaA'" in _tx(case, "oracle", "mysql")
        assert "'aAaA' COLLATE Latin1_General_BIN2" in _tx(case, "oracle", "tsql")


class TestGenerateSeries:
    """T-SQL GENERATE_SERIES(start, stop) (column 'value') maps to PG
    generate_series with the column aliased to 'value', and Oracle a CONNECT BY
    LEVEL subquery. Live-verified 1..5 on both."""

    def test_from_position_generate_series(self) -> None:
        case = _case("challenge_sqlserver.sql", "ts-generate-series ")
        assert "generate_series(1, 5) AS uq_gs(value)" in _tx(
            case, "tsql", "postgresql"
        )
        ora = _tx(case, "tsql", "oracle")
        assert "CONNECT BY LEVEL <= (5) - (1) + 1" in ora, ora

    def test_generate_series_with_apply(self) -> None:
        # GENERATE_SERIES with an explicit alias + CROSS APPLY still resolves value.
        case = _case("challenge_sqlserver.sql", "ts-gen-series-apply ")
        assert "generate_series(1, 5) AS g(value)" in _tx(case, "tsql", "postgresql")


class TestTopWithTies:
    """T-SQL TOP n WITH TIES also returns rows tying the last one. PG (13+) and
    Oracle carry it as FETCH FIRST n ROWS WITH TIES (a plain LIMIT would silently
    drop the ties); MySQL has no equivalent, so it keeps LIMIT + a documented
    carrier warning. Live-verified [(1,), (1,)] on PG/Oracle."""

    def test_pg_and_oracle_fetch_with_ties(self) -> None:
        case = _case("challenge_sqlserver.sql", "ts-top-with-ties ")
        assert "FETCH FIRST 1 ROWS WITH TIES" in _tx(case, "tsql", "postgresql")
        assert "FETCH FIRST 1 ROWS WITH TIES" in _tx(case, "tsql", "oracle")

    def test_mysql_documents_dropped_ties(self) -> None:
        case = _case("challenge_sqlserver.sql", "ts-top-with-ties ")
        result = Transpiler().transpile(case, source="tsql", target="mysql")
        assert result.warnings, "MySQL WITH TIES loss must warn"
        assert "WITH TIES" in result.sql and "LIMIT 1" in result.sql, result.sql


class TestOracleIdentityOptions:
    """Oracle IDENTITY (START WITH/INCREMENT BY/MAXVALUE/CYCLE) has no MySQL
    per-column form — AUTO_INCREMENT always starts at 1 / steps by 1. Emit the
    keyed AUTO_INCREMENT plus a documented carrier + warning rather than silently
    resetting the sequence."""

    def test_mysql_carries_dropped_options(self) -> None:
        case = _case("challenge_oracle.sql", "ora-identity-opts ")
        result = Transpiler().transpile(case, source="oracle", target="mysql")
        assert result.warnings, "dropped IDENTITY options must warn"
        assert "UNIQUE-1049:" in result.sql, result.sql
        # AUTO_INCREMENT column must still be keyed (the carrier's "UNIQUE-" is
        # not a key).
        assert "KEY (`a`)" in result.sql, result.sql


class TestTablesample:
    """TABLESAMPLE re-spells natively on PG/T-SQL (TABLESAMPLE) and Oracle
    (SAMPLE); MySQL has no row sampling, so it degrades to a documented carrier +
    warning instead of silently returning every row."""

    def test_pg_sample_to_tsql_and_oracle(self) -> None:
        case = _case("challenge_postgresql.sql", "pg-tablesample ")
        assert "TABLESAMPLE (50 PERCENT)" in _tx(case, "postgresql", "tsql")
        assert "SAMPLE (50)" in _tx(case, "postgresql", "oracle")

    def test_mysql_degrades_with_warning(self) -> None:
        case = _case("challenge_postgresql.sql", "pg-tablesample ")
        result = Transpiler().transpile(case, source="postgresql", target="mysql")
        assert result.warnings, "dropped TABLESAMPLE must warn"
        assert "UNIQUE-1034:" in result.sql and "TABLESAMPLE" in result.sql, result.sql


class TestUsingJoinQualified:
    """T-SQL has no USING; USING(x) becomes ON a.x = b.x, so a bare ``x`` in the
    projection is ambiguous. Qualify it with the left table (a.x). Verified 1."""

    def test_tsql_projection_qualified(self) -> None:
        out = _tx(_case("challenge_mysql.sql", "my-using-join "), "mysql", "tsql")
        assert "SELECT a.x" in out, out
        assert "ON a.x = b.x" in out, out


class TestMysqlUpdateSelfRef:
    """MySQL error 1093: a subquery in SET can't select FROM the UPDATE target.
    Wrap the aliased self-reference in a derived table so the correlated subquery
    is allowed. Live-verified (1,NULL),(2,10),(3,20)."""

    def test_self_ref_wrapped_for_mysql(self) -> None:
        out = _tx(
            _case("challenge_oracle.sql", "ora-upd-correlated "), "oracle", "mysql"
        )
        assert "FROM (SELECT *\nFROM t) x" in out, out
        assert "x.id < t.id" in out, out


class TestMysqlUpdateJoin:
    """MySQL's UPDATE t JOIN s ON … SET … hangs the join off the target table, so
    it was silently dropped (dangling ``s``). Lift it into the per-engine
    cross-table UPDATE: PG FROM/WHERE, T-SQL FROM JOIN, Oracle correlated
    subquery. Live-verified (1,99),(2,88) on all three."""

    def test_update_join_carried(self) -> None:
        case = _case("challenge_mysql.sql", "my-update-join ")
        pg = _tx(case, "mysql", "postgresql")
        assert "FROM s" in pg and "WHERE t.id = s.id" in pg, pg
        tsql = _tx(case, "mysql", "tsql")
        assert "FROM t\nINNER JOIN s ON t.id = s.id" in tsql, tsql
        assert "(SELECT s.n FROM s WHERE t.id = s.id)" in _tx(case, "mysql", "oracle")

    def test_self_join_no_duplicate_target(self) -> None:
        # The T-SQL self-join must bind the aliased target once (not ``t t1, t t1``).
        out = _tx(_case("challenge_mysql.sql", "my-upd-selfjoin "), "mysql", "tsql")
        assert "t t1, t t1" not in out, out
        assert "FROM t t1\nINNER JOIN t t2" in out, out


class TestNamedWindowInlined:
    """A named WINDOW clause (OVER w ... WINDOW w AS (ORDER BY x)) is inlined into
    each OVER reference, since the IR has no named-window concept — an un-inlined
    reference emitted an empty OVER () (ORA-30485). Live-verified on Oracle."""

    def test_window_spec_inlined(self) -> None:
        out = _tx(
            _case("challenge_postgresql.sql", "pg-named-window "),
            "postgresql",
            "oracle",
        )
        body = "\n".join(
            ln for ln in out.splitlines() if not ln.lstrip().startswith("--")
        )
        assert "OVER (ORDER BY x" in body, body
        assert "OVER ()" not in body, body


class TestDualAliasDropped:
    """MySQL rejects an alias on the DUAL pseudo-table (error 1064); the alias was
    only load-bearing for the Oracle hint, which is dropped. Drop it. Verified 1."""

    def test_mysql_dual_alias_dropped(self) -> None:
        out = _tx(_case("challenge_oracle.sql", "ora-hint-comment "), "oracle", "mysql")
        body = "\n".join(
            ln for ln in out.splitlines() if not ln.lstrip().startswith("--")
        )
        assert "FROM DUAL" in body and "DUAL t" not in body, body


class TestToDateToMysql:
    """Oracle/PG TO_DATE / TO_TIMESTAMP map to MySQL STR_TO_DATE with a translated
    format mask (a DATETIME literal when the input is already ISO). Live-verified
    2020-06-15 on both."""

    def test_oracle_to_date_uses_str_to_date(self) -> None:
        out = _tx(_case("challenge_oracle.sql", "ora-todate2 "), "oracle", "mysql")
        assert "STR_TO_DATE('15-JUN-20', '%d-%b-%y')" in out, out

    def test_pg_to_date_uses_str_to_date(self) -> None:
        out = _tx(
            _case("challenge_postgresql.sql", "pg-todate2 "), "postgresql", "mysql"
        )
        assert "STR_TO_DATE('06/15/2020', '%m/%d/%Y')" in out, out


class TestHexLiteralToInt:
    """A hex literal cast to an integer can't go through Oracle HEXTORAW (ORA-00932
    casting BINARY to a number); TO_NUMBER with an 'X' mask parses the digits.
    Live-verified 255."""

    def test_oracle_uses_to_number_hex_mask(self) -> None:
        out = _tx(
            _case("challenge_postgresql.sql", "pg-hex-literal "), "postgresql", "oracle"
        )
        assert "TO_NUMBER('FF', 'XX')" in out, out


class TestStringAggOrderCast:
    """STRING_AGG(x::text ORDER BY x) folds the value cast into a RawSQL; its
    source type name is portabilized and a string cast mapped to the target's
    VARCHAR — LISTAGG rejects CLOB (ORA-00932), T-SQL STRING_AGG rejects TEXT
    (529). Live-verified '1,2'."""

    def test_string_agg_order_cast_portabilized(self) -> None:
        case = _case("challenge_postgresql.sql", "pg-string-agg-order ")
        assert "CAST(x AS VARCHAR2(4000))" in _tx(case, "postgresql", "oracle")
        # PG TEXT now maps to the Unicode NVARCHAR(MAX) (procedural-map parity).
        assert "CAST(x AS NVARCHAR(MAX))" in _tx(case, "postgresql", "tsql")


class TestExtractValue:
    """MySQL EXTRACTVALUE(xml, xpath) maps per engine: Oracle EXTRACTVALUE over an
    XMLTYPE, PG XPATH(...'/text()')[1], T-SQL an XML .value(). Live-verified '1'."""

    def test_extractvalue_per_engine(self) -> None:
        case = _case("challenge_mysql.sql", "my-extractvalue ")
        assert "EXTRACTVALUE(XMLTYPE('<a>1</a>'), '/a')" in _tx(case, "mysql", "oracle")
        assert "XPATH('/a/text()', '<a>1</a>'::XML)" in _tx(case, "mysql", "postgresql")
        assert ".value('(/a/text())[1]', 'NVARCHAR(MAX)')" in _tx(case, "mysql", "tsql")


class TestCollationFn:
    """COLLATION(x) returns the argument's collation name, which is engine-specific
    (MySQL 'utf8mb4_0900_ai_ci' vs Oracle 'USING_NLS_COMP') and can never match.
    Emit the call with a documented carrier + warning."""

    def test_oracle_collation_carries(self) -> None:
        case = _case("challenge_mysql.sql", "my-collation-fn ")
        result = Transpiler().transpile(case, source="mysql", target="oracle")
        assert result.warnings, "engine-specific collation must warn"
        assert "UNIQUE-1089:" in result.sql and "COLLATION(" in result.sql, result.sql


class TestOracleTimeCast:
    """Oracle has no TIME or bare INTERVAL type, so CAST(... AS TIME)/::interval
    shipped an invalid datatype. Keep the value as text with a documented carrier
    + warning."""

    def test_oracle_time_cast_carries(self) -> None:
        case = _case("challenge_mysql.sql", "my-cast-time ")
        result = Transpiler().transpile(case, source="mysql", target="oracle")
        assert result.warnings, "no-TIME-type must warn"
        body = "\n".join(
            ln for ln in result.sql.splitlines() if not ln.lstrip().startswith("--")
        )
        assert "UNIQUE-1065:" in body and "AS TIME)" not in body, body

    def test_oracle_interval_cast_carries(self) -> None:
        case = _case("challenge_postgresql.sql", "pg-cast-interval ")
        result = Transpiler().transpile(case, source="postgresql", target="oracle")
        assert result.warnings, "no-bare-INTERVAL must warn"
        body = "\n".join(
            ln for ln in result.sql.splitlines() if not ln.lstrip().startswith("--")
        )
        assert "UNIQUE-1065:" in body and "AS INTERVAL)" not in body, body


class TestNanCast:
    """PostgreSQL numeric represents NaN (NaN > 1 = true); MySQL DECIMAL does not
    (CAST('NaN' AS DECIMAL) is 0), so the comparison diverges. Emit the cast plus
    a documented carrier + warning."""

    def test_mysql_nan_cast_carries(self) -> None:
        case = _case("challenge_postgresql.sql", "pg-nan-cmp ")
        result = Transpiler().transpile(case, source="postgresql", target="mysql")
        assert result.warnings, "NaN cast must warn"
        assert "UNIQUE-1068:" in result.sql and "NaN" in result.sql, result.sql


class TestRegexpSubstrGroup:
    """Oracle REGEXP_SUBSTR's 6th arg (capture group) has no MySQL equivalent
    (and would ship an invalid 6-arg call). Emit the portable 4-arg subset plus a
    documented carrier + warning."""

    def test_mysql_drops_group_with_carrier(self) -> None:
        case = _case("challenge_oracle.sql", "ora-regexp-group ")
        result = Transpiler().transpile(case, source="oracle", target="mysql")
        assert result.warnings, "dropped capture group must warn"
        assert "UNIQUE-1090:" in result.sql, result.sql
        assert "REGEXP_SUBSTR('a1b2c3', '(\\d)', 1, 1)" in result.sql, result.sql


class TestRoundDateMonth:
    """Oracle ROUND(date,'MONTH') rounds to the nearest month start (day>=16 ->
    1st of next month); MySQL's ROUND is numeric, so emulate with month
    arithmetic. Live-verified 2020-07-01."""

    def test_mysql_month_round_emulated(self) -> None:
        out = _tx(
            _case("challenge_oracle.sql", "ora-round-date-month "), "oracle", "mysql"
        )
        assert "DAYOFMONTH('2020-06-16') < 16" in out, out
        assert "DATE_ADD(" in out and "INTERVAL 1 MONTH" in out, out


class TestCastUnsigned:
    """MySQL's UNSIGNED integer cast has no signed-engine type; map it to a wide
    NUMERIC/NUMBER (value preserved) with a carrier flagging the lost unsigned
    wraparound. Live-verified."""

    def test_unsigned_cast_carries(self) -> None:
        case = _case("challenge_mysql.sql", "my-cast-convert ")
        for target in ("oracle", "postgresql", "tsql"):
            result = Transpiler().transpile(case, source="mysql", target=target)
            assert result.warnings, "UNSIGNED must warn"
            assert (
                "UNIQUE-1069:" in result.sql and "UBIGINT" not in result.sql
            ), result.sql


class TestCastBinary:
    """PG has no BINARY/VARBINARY type; CAST AS BINARY maps to BYTEA.
    Live-verified b'abc'."""

    def test_cast_binary_maps_to_bytea(self) -> None:
        # A bare BINARY cast keeps the runtime BYTEA cast (only an unsized /
        # wide-enough VARBINARY literal folds to its encoded bytes — a fixed
        # BINARY(n) would zero-pad).
        out = _tx(
            _case("challenge_mysql.sql", "my-cast-binary2 "), "mysql", "postgresql"
        )
        assert "CAST('abc' AS BYTEA)" in out, out


class TestCastDouble:
    """A bare CAST(... AS DOUBLE) is an invalid type name on PG (needs DOUBLE
    PRECISION) and Oracle (BINARY_DOUBLE). Map it. Live-verified 3.14."""

    def test_cast_double_maps(self) -> None:
        case = _case("challenge_mysql.sql", "my-cast-matrix ")
        assert "DOUBLE PRECISION" in _tx(case, "mysql", "postgresql")
        assert "BINARY_DOUBLE" in _tx(case, "mysql", "oracle")


class TestToNumberScientific:
    """Oracle TO_NUMBER of a scientific-notation string ('1.234E2') can't CAST to
    a T-SQL DECIMAL (error 8114); FLOAT parses the exponent. Live-verified 123.4."""

    def test_tsql_uses_float_for_exponent(self) -> None:
        out = _tx(_case("challenge_oracle.sql", "ora-to-number-sci "), "oracle", "tsql")
        assert "CAST('1.234E2' AS FLOAT)" in out, out


class TestTimestamptzCast:
    """PG TIMESTAMPTZ maps to each engine's timezone-aware type: T-SQL
    DATETIMEOFFSET, MySQL DATETIME (no tz), Oracle a date literal. Live-verified
    2020-01-01 midnight on all three."""

    def test_timestamptz_per_engine(self) -> None:
        case = _case("challenge_postgresql.sql", "pg-cast-tstz ")
        assert "DATETIMEOFFSET" in _tx(case, "postgresql", "tsql")
        assert "AS DATETIME)" in _tx(case, "postgresql", "mysql")
        ora = "\n".join(
            ln
            for ln in _tx(case, "postgresql", "oracle").splitlines()
            if not ln.lstrip().startswith("--")
        )
        assert "TIMESTAMPTZ" not in ora, ora


class TestPgBooleanToText:
    """PostgreSQL renders a boolean cast to text as 'true'/'false'; MySQL has no
    boolean text and would give '1'/'0'. Emit CASE WHEN <bool> THEN 'true' ELSE
    'false' for a comparison or a true/false literal. Live-verified 'true'."""

    def test_bool_literal_to_text(self) -> None:
        out = _tx(
            _case("challenge_postgresql.sql", "pg-bool-text2 "), "postgresql", "mysql"
        )
        assert "CASE WHEN TRUE THEN 'true' ELSE 'false' END" in out, out

    def test_comparison_to_text(self) -> None:
        out = _tx(
            _case("challenge_postgresql.sql", "pg-bool-repr "), "postgresql", "mysql"
        )
        assert "CASE WHEN 1 > 0 THEN 'true' ELSE 'false' END" in out, out


class TestPgBooleanCastFolds:
    """PostgreSQL word-spelled boolean casts ('true'/'t'/'1'/'yes'/'off') fold to
    1/0 on Oracle/T-SQL (which have no boolean text). Live-verified (1,1,1,1) and
    (1,1,0,1) — True==1, False==0."""

    def test_bool_literals_fold_to_ints(self) -> None:
        for target in ("oracle", "tsql"):
            out = _tx(
                _case("challenge_postgresql.sql", "pg-cast-bool2 "),
                "postgresql",
                target,
            )
            body = "\n".join(
                ln for ln in out.splitlines() if not ln.lstrip().startswith("--")
            )
            assert "1, 1, 0, 1" in body, body


class TestTsqlFracSeconds:
    """T-SQL CAST(... AS DATETIME2/DATETIME) over a fractional-second string maps
    to an Oracle TIMESTAMP literal (a bare string tripped ORA-01843). Live-verified
    10:20:30.123456 / .123000 on Oracle."""

    def test_oracle_timestamp_literal(self) -> None:
        out = _tx(
            _case("challenge_sqlserver.sql", "ts-frac-seconds "), "tsql", "oracle"
        )
        assert "TIMESTAMP '2020-01-01 10:20:30.1234567'" in out, out
        assert "TIMESTAMP '2020-01-01 10:20:30.123'" in out, out


class TestTsqlDateAddEomonth:
    """T-SQL DATEADD / EOMONTH over date-string literals map to each engine's
    idiom (ADD_MONTHS/LAST_DAY on Oracle, DATE_ADD/LAST_DAY on MySQL, interval
    arithmetic on PG) with the literal qualified as a DATE. Live-verified
    2020-02-29 / 2020-01-02 / 2020-02-29 on every target."""

    def test_oracle_uses_add_months_and_last_day(self) -> None:
        out = _tx(_case("challenge_sqlserver.sql", "ts-dateadd "), "tsql", "oracle")
        assert "ADD_MONTHS(DATE '2020-01-31', 1)" in out, out
        assert "LAST_DAY(DATE '2020-02-15')" in out, out

    def test_mysql_uses_date_add(self) -> None:
        out = _tx(_case("challenge_sqlserver.sql", "ts-dateadd "), "tsql", "mysql")
        assert "DATE_ADD('2020-01-31', INTERVAL 1 MONTH)" in out, out
        assert "LAST_DAY('2020-02-15')" in out, out


class TestTimestampAddQualifiesLiteral:
    """TIMESTAMPADD over a bare datetime string can't take interval arithmetic on
    PG/Oracle; qualify it as a TIMESTAMP literal (seconds padded for Oracle).
    Live-verified 2020-01-01 10:30."""

    def test_pg_and_oracle_qualify_datetime(self) -> None:
        case = _case("challenge_mysql.sql", "my-timestampadd ")
        assert "TIMESTAMP '2020-01-01 10:00' + INTERVAL '30 MINUTE'" in _tx(
            case, "mysql", "postgresql"
        )
        assert "TIMESTAMP '2020-01-01 10:00:00' + NUMTODSINTERVAL(30, 'MINUTE')" in _tx(
            case, "mysql", "oracle"
        )


class TestDateAddQualifiesDateLiteral:
    """MySQL's DATE_ADD reads a bare '2020-01-01' string as a date, but PG reads
    it as an interval and Oracle rejects the implicit cast. A date-only literal
    base is qualified as an ANSI DATE literal so the interval add runs (verified
    2020-01-08 on both; midnight on the datetime-typed targets)."""

    def test_pg_and_oracle_qualify_the_literal(self) -> None:
        case = _case("challenge_mysql.sql", "my-date-add-interval ")
        assert "DATE '2020-01-01' + INTERVAL '7 DAY'" in _tx(
            case, "mysql", "postgresql"
        )
        ora = _tx(case, "mysql", "oracle")
        assert "DATE '2020-01-01' + NUMTODSINTERVAL(7, 'DAY')" in ora, ora


class TestMysqlDateArithReturnsDate:
    """MySQL date arithmetic on a DATE returns a DATE ('2020-01-31'); T-SQL
    DATEADD returns a DATETIME ('… 00:00:00'). For a MySQL source with a
    date-only literal base, the T-SQL output is cast back to DATE. Live-verified
    the value/repr matches on all three (ADDDATE, SUBDATE, string + INTERVAL)."""

    @pytest.mark.parametrize(
        "keyword",
        (
            "my-adddate",
            "my-subdate",
            "my-str-plus-interval",
            "my-month-overflow",
            "my-date-add-month",
        ),
    )
    def test_cast_back_to_date(self, keyword: str) -> None:
        out = _tx(_case("challenge_mysql.sql", keyword), "mysql", "tsql")
        assert re.search(r"(?i)CAST\(\s*DATEADD\(.*\)\s+AS\s+DATE\)", out), out


class TestMysqlBooleanCast:
    """MySQL CAST of a boolean (a comparison) to a character type yields '1'/'0'
    (MySQL booleans are integers); PostgreSQL renders the boolean 't'/'f'. The
    MySQL->PG emit converts the boolean to an integer first. Live-verified '1'."""

    def test_bool_cast_to_char_is_int(self) -> None:
        out = _tx(_case("challenge_mysql.sql", "my-bool-char"), "mysql", "postgresql")
        assert re.search(r"(?i)CASE\s+WHEN\b.*THEN\s+1\s+ELSE\s+0\s+END", out), out

    def test_concat_bool_is_int(self) -> None:
        # CONCAT(TRUE, FALSE) is '10' on MySQL; PG must emit CONCAT(1, 0), not
        # CONCAT(TRUE, FALSE) (which is 'tf').
        out = _tx(_case("challenge_mysql.sql", "my-concat-bool"), "mysql", "postgresql")
        assert "CONCAT(1, 0)" in out, out


class TestMysqlAsciiEmpty:
    """MySQL ASCII('') is 0; Oracle/T-SQL return NULL ('' -> NULL). T-SQL can tell
    '' from NULL (faithful CASE, ASCII(NULL) stays NULL); Oracle can't, so
    COALESCE picks the empty-string reading. Live-verified 0 on both."""

    def test_tsql_faithful_case(self) -> None:
        out = _tx(_case("challenge_mysql.sql", "my-ascii-empty"), "mysql", "tsql")
        assert re.search(
            r"(?i)CASE\s+WHEN\b.*=\s*''\s+THEN\s+0\s+ELSE\s+ASCII", out
        ), out

    def test_oracle_coalesce(self) -> None:
        out = _tx(_case("challenge_mysql.sql", "my-ascii-empty"), "mysql", "oracle")
        assert "COALESCE(ASCII(" in out and ", 0)" in out, out

    def test_pg_source_tsql_case(self) -> None:
        # PostgreSQL ASCII('') is also 0 — same recovery on a PG source.
        out = _tx(
            _case("challenge_postgresql.sql", "pg-ascii-empty"), "postgresql", "tsql"
        )
        assert re.search(
            r"(?i)CASE\s+WHEN\b.*=\s*''\s+THEN\s+0\s+ELSE\s+ASCII", out
        ), out

    def test_pg_source_oracle_coalesce(self) -> None:
        out = _tx(
            _case("challenge_postgresql.sql", "pg-ascii-empty"), "postgresql", "oracle"
        )
        assert "COALESCE(ASCII(" in out and ", 0)" in out, out


class TestMysqlLocateEmpty:
    """MySQL LOCATE/INSTR with an empty needle returns 1; Oracle INSTR returns
    NULL ('' -> NULL) and T-SQL CHARINDEX returns 0. Recover the 1 (Oracle
    COALESCE(INSTR, 1); T-SQL CASE WHEN needle = '' THEN 1). Live-verified."""

    @pytest.mark.parametrize("keyword", ("my-locate-empty", "my-locate-empty2"))
    def test_oracle_coalesces_to_one(self, keyword: str) -> None:
        out = _tx(_case("challenge_mysql.sql", keyword), "mysql", "oracle")
        assert re.search(r"(?i)COALESCE\(\s*INSTR\(.*\)\s*,\s*1\)", out), out

    @pytest.mark.parametrize("keyword", ("my-locate-empty", "my-locate-empty2"))
    def test_tsql_case_to_one(self, keyword: str) -> None:
        out = _tx(_case("challenge_mysql.sql", keyword), "mysql", "tsql")
        assert re.search(r"(?i)CASE\s+WHEN\b.*=\s*''\s+THEN\s+1", out), out

    @pytest.mark.parametrize("keyword", ("pg-position-empty", "pg-strpos-empty"))
    def test_pg_oracle_coalesces_to_one(self, keyword: str) -> None:
        # PostgreSQL POSITION/STRPOS with an empty needle also returns 1.
        out = _tx(_case("challenge_postgresql.sql", keyword), "postgresql", "oracle")
        assert re.search(r"(?i)COALESCE\(\s*INSTR\(.*\)\s*,\s*1\)", out), out

    @pytest.mark.parametrize("keyword", ("pg-position-empty", "pg-strpos-empty"))
    def test_pg_tsql_case_to_one(self, keyword: str) -> None:
        out = _tx(_case("challenge_postgresql.sql", keyword), "postgresql", "tsql")
        assert re.search(r"(?i)CASE\s+WHEN\b.*=\s*''\s+THEN\s+1", out), out


class TestMysqlStringPlusIsArithmetic:
    """MySQL '+' is always arithmetic, so '5' + '5' is 10; T-SQL '+' on strings
    concatenates ('55'). For a MySQL source adding numeric string literals, cast
    them so T-SQL does the arithmetic. Live-verified 10.0 (not '55')."""

    def test_numeric_string_add_casts(self) -> None:
        # Literal operands fold to MySQL's DOUBLE arithmetic values; a
        # non-literal string operand keeps the runtime FLOAT cast.
        out = _exec_lines(
            _tx(_case("challenge_mysql.sql", "my-strnum-add"), "mysql", "tsql")
        )
        assert "5.0 + 5.0" in out, out
        assert "'5'" not in out, out


class TestIsTrueInValuePosition:
    """`<predicate> IS TRUE` in a SELECT list has no boolean value on T-SQL/Oracle;
    it normalizes to the predicate inside the CASE wrap (was an invalid `IS 1`).
    Live-verified 1."""

    def test_is_true_normalized(self) -> None:
        for target in ("oracle", "tsql"):
            out = _tx(_case("challenge_mysql.sql", "my-is-true "), "mysql", target)
            body = "\n".join(
                ln for ln in out.splitlines() if not ln.lstrip().startswith("--")
            )
            assert "IS 1" not in body and "IS TRUE" not in body, body
            assert "CASE WHEN 1 IN" in body, body


class TestStringPlusNumberStaysArithmetic:
    """A T-SQL/Oracle '+' with one string and one *numeric-literal* operand is
    arithmetic on every engine (the string is coerced to a number: '10' + 5 = 15,
    '1' + 1 = 2). It must not be rewritten to concatenation. Live-verified."""

    def test_tsql_string_plus_number(self) -> None:
        for target in ("mysql", "oracle", "postgresql"):
            out = _tx(
                _case("challenge_sqlserver.sql", "ts-str-plus-num "), "tsql", target
            )
            body = "\n".join(
                ln for ln in out.splitlines() if not ln.lstrip().startswith("--")
            )
            assert "'10' + 5" in body, body
            assert "||" not in body and "CONCAT" not in body.upper(), body

    def test_oracle_string_plus_number(self) -> None:
        for target in ("mysql", "postgresql", "tsql"):
            out = _tx(
                _case("challenge_oracle.sql", "ora-implicit-arith "), "oracle", target
            )
            assert "'1' + 1" in out, out


class TestMysqlConcatNullPropagates:
    """MySQL CONCAT returns NULL if any argument is NULL; PG/Oracle/T-SQL ignore
    NULL. A MySQL CONCAT with a literal NULL is always NULL — fold it. Only fires
    for a literal NULL, so plain CONCAT (and its roundtrip) is untouched."""

    @pytest.mark.parametrize("target", ("oracle", "postgresql", "tsql"))
    def test_concat_literal_null_is_null(self, target: str) -> None:
        out = _tx(_case("challenge_mysql.sql", "my-concat-null"), "mysql", target)
        assert re.search(r"(?i)SELECT\s+NULL\s+AS\s+r", out), out

    def test_concat_without_null_is_unchanged(self) -> None:
        # Roundtrip-safety: a CONCAT with no NULL literal keeps CONCAT.
        out = _tx("SELECT CONCAT('a', 'b') AS r", "mysql", "postgresql")
        assert "CONCAT('a', 'b')" in out, out

    def test_tsql_source_drops_null_arg(self) -> None:
        # The reverse: T-SQL CONCAT ignores NULL, so the literal NULL is dropped
        # (else MySQL's propagating CONCAT would turn the result NULL).
        out = _tx(_case("challenge_sqlserver.sql", "ts-concat-null"), "tsql", "mysql")
        assert "CONCAT('a', 'b')" in out, out

    def test_pg_source_drops_null_arg(self) -> None:
        out = _tx(
            _case("challenge_postgresql.sql", "pg-concat-null"), "postgresql", "mysql"
        )
        assert "CONCAT('a', 'b')" in out, out


class TestIntegerDivisionSemantics:
    """MySQL/Oracle ``/`` is decimal division (5/2 = 2.5); PG/T-SQL truncate two
    integer operands (5/2 = 2). The emitter forces the source's semantics when
    both operands are known integers."""

    @pytest.mark.parametrize(
        "fixture,source,keyword",
        [
            ("challenge_mysql.sql", "mysql", "my-div"),
            ("challenge_oracle.sql", "oracle", "ora-div"),
        ],
    )
    @pytest.mark.parametrize("target", ("postgresql", "tsql"))
    def test_decimal_div_forced_on_pg_tsql(
        self, fixture: str, source: str, keyword: str, target: str
    ) -> None:
        out = _tx(_case(fixture, keyword), source, target)
        assert "* 1.0 /" in out, out

    def test_pg_intdiv_truncates_on_mysql(self) -> None:
        out = _tx(_case("challenge_postgresql.sql", "pg-intdiv"), "postgresql", "mysql")
        assert "DIV" in out, out

    def test_pg_intdiv_truncates_on_oracle(self) -> None:
        out = _tx(
            _case("challenge_postgresql.sql", "pg-intdiv"), "postgresql", "oracle"
        )
        assert "TRUNC(" in out, out


class TestMysqlCaseInsensitiveSearch:
    """MySQL's default collation is case-insensitive, so LOCATE/INSTR match
    regardless of case (INSTR('aAaA', 'A') = 1); Oracle and PostgreSQL compare
    case-sensitively. The emitter lower-cases both operands there (T-SQL's
    default collation is already case-insensitive, so it is untouched)."""

    @pytest.mark.parametrize("keyword", ("my-instr-case", "my-locate-case"))
    @pytest.mark.parametrize("target", ("oracle", "postgresql"))
    def test_search_lowercased_on_cs_targets(self, keyword: str, target: str) -> None:
        out = _tx(_case("challenge_mysql.sql", keyword), "mysql", target)
        assert out.upper().count("LOWER(") >= 2, out

    def test_tsql_not_lowercased(self) -> None:
        # T-SQL is case-insensitive by default — no LOWER needed.
        out = _tx(_case("challenge_mysql.sql", "my-instr-case"), "mysql", "tsql")
        assert "LOWER(" not in out.upper(), out


class TestDatePlusInteger:
    """PostgreSQL/Oracle ``date + n`` adds n days (yielding a date); MySQL reads
    it as a numeric addition (2020-01-01 + 30 = 20200131) and T-SQL rejects it.
    From a PG/Oracle source the emitter spells it as DATE_ADD / DATEADD."""

    def test_pg_date_plus_int_mysql(self) -> None:
        out = _tx(
            _case("challenge_postgresql.sql", "pg-date-plus-int"), "postgresql", "mysql"
        )
        assert re.search(r"(?i)DATE_ADD\(.*INTERVAL\s+30\s+DAY\)", out), out

    def test_pg_date_plus_int_tsql(self) -> None:
        out = _tx(
            _case("challenge_postgresql.sql", "pg-date-plus-int"), "postgresql", "tsql"
        )
        assert re.search(r"(?i)DATEADD\(\s*DAY\s*,\s*30", out), out

    def test_oracle_date_plus_int_mysql(self) -> None:
        out = _tx(
            _case("challenge_oracle.sql", "ora-date-plus-int2"), "oracle", "mysql"
        )
        assert re.search(r"(?i)DATE_ADD\(.*INTERVAL\s+30\s+DAY\)", out), out


class TestTsqlLoopControl:
    """T-SQL loop body: ``SET @i += 1`` compound assignment, ``BREAK`` and
    ``CONTINUE`` all have to translate to valid PL/SQL, PL/pgSQL and MySQL
    (the procedure would not compile otherwise)."""

    def test_compound_assignment_expands(self) -> None:
        # @i += 1  ->  V_I := V_I + 1 (Oracle), no leftover '= 1'.
        out = _tx(
            _case("challenge_sqlserver.sql", "ts-continue-break"), "tsql", "oracle"
        )
        assert re.search(r"(?i)V_I\s*:=\s*V_I\s*\+\s*\(?1\)?", out), out
        assert ":= =" not in out, out

    @pytest.mark.parametrize(
        "target,brk,cont",
        [
            ("oracle", "EXIT;", "CONTINUE;"),
            ("postgresql", "EXIT;", "CONTINUE;"),
            # MySQL LEAVE/ITERATE target the loop's unique generated label
            # (loop_lbl_<n>, per finding N5a) — assert the exact form below.
            ("mysql", None, None),
        ],
    )
    def test_break_continue_map(
        self, target: str, brk: str | None, cont: str | None
    ) -> None:
        out = _tx(_case("challenge_sqlserver.sql", "ts-continue-break"), "tsql", target)
        body = _exec_lines(out)
        if target == "mysql":
            assert re.search(r"LEAVE loop_lbl_\d+;", body), out
            assert re.search(r"ITERATE loop_lbl_\d+;", body), out
        else:
            assert brk in body, out
            assert cont in body, out
        assert "BREAK" not in body.upper(), out  # no leftover T-SQL BREAK

    def test_mysql_loop_is_labeled(self) -> None:
        # Each emitted loop carries a UNIQUE label so nested loops never
        # collide (finding N5a: two ``loop_lbl`` is MySQL error 1309); the
        # LEAVE/ITERATE inside reference the same label.
        out = _tx(
            _case("challenge_sqlserver.sql", "ts-continue-break"), "tsql", "mysql"
        )
        m = re.search(r"(loop_lbl_\d+): WHILE", out)
        assert m, out
        label = m.group(1)
        assert f"LEAVE {label};" in out and f"ITERATE {label};" in out, out


class TestTsqlBitCast:
    """T-SQL ``CAST(x AS BIT)`` maps any non-zero numeric to 1 (0 -> 0, NULL ->
    NULL); other engines keep the value. The emitter normalizes via SIGN(ABS(x))."""

    @pytest.mark.parametrize("target", ("oracle", "postgresql", "mysql"))
    def test_bit_cast_uses_sign_abs(self, target: str) -> None:
        body = _exec_lines(
            _tx(_case("challenge_sqlserver.sql", "ts-cast-bit"), "tsql", target)
        )
        assert re.search(r"(?i)SIGN\s*\(\s*ABS\s*\(", body), body
        assert "AS BIT" not in body.upper(), body


class TestPgDateDifference:
    """PostgreSQL ``DATE - DATE`` is a day count (60); MySQL does a numeric
    subtraction (200) and T-SQL rejects it. The PG date literal parses as
    ``CAST(... AS DATE)``; recognizing that shape lets the emitter spell the
    difference as DATEDIFF on MySQL/T-SQL."""

    def test_mysql_uses_datediff(self) -> None:
        out = _tx(
            _case("challenge_postgresql.sql", "pg-date-diff-days"),
            "postgresql",
            "mysql",
        )
        assert re.search(r"(?i)DATEDIFF\(", out), out

    def test_tsql_uses_datediff_day(self) -> None:
        out = _tx(
            _case("challenge_postgresql.sql", "pg-date-diff-days"), "postgresql", "tsql"
        )
        assert re.search(r"(?i)DATEDIFF\(\s*DAY", out), out


class TestPgUnboundedNumericCastScale:
    """PostgreSQL's unbounded ``numeric`` is arbitrary-precision, but a bare
    DECIMAL cast defaults to scale 0 on MySQL/Oracle/T-SQL and silently
    truncates the fraction (2.675::numeric became 3 before a later ROUND). The
    emitter gives the unbounded cast a scale so the value survives."""

    @pytest.mark.parametrize("keyword", ("pg-round-2675", "pg-round-1005", "pg-fround"))
    @pytest.mark.parametrize("target", ("mysql", "oracle", "tsql"))
    def test_unbounded_numeric_cast_keeps_scale(
        self, keyword: str, target: str
    ) -> None:
        out = _tx(_case("challenge_postgresql.sql", keyword), "postgresql", target)
        assert re.search(r"(?i)AS\s+(?:DECIMAL|NUMERIC|NUMBER)\(38,\s*10\)", out), out


class TestPgSubstringZeroStart:
    """PostgreSQL SUBSTRING(s, start, len) with a start <= 0 counts the
    out-of-range leading positions toward the length (SUBSTRING('abcdef', 0, 3)
    = 'ab'); Oracle clamps 0 to 1 and MySQL returns ''. The emitter rebases to
    start 1 with an adjusted length."""

    @pytest.mark.parametrize("target", ("mysql", "oracle"))
    def test_zero_start_rebased(self, target: str) -> None:
        out = _tx(
            _case("challenge_postgresql.sql", "pg-substr-zero"), "postgresql", target
        )
        assert re.search(r"(?i)SUBSTR\('abcdef',\s*1,\s*2\)", out), out

    def test_positive_start_unchanged(self) -> None:
        # A positive start is not rebased — the args stay (2, 3).
        out = _tx("SELECT SUBSTRING('abcdef', 2, 3) AS r", "postgresql", "mysql")
        assert re.search(r"(?i)'abcdef',\s*2,\s*3\)", out), out


class TestTsqlLenTrailingSpaces:
    """T-SQL ``LEN`` excludes trailing spaces (LEN('abc   ') = 3); MySQL
    CHAR_LENGTH and Oracle/PostgreSQL LENGTH count them (6). The emitter trims
    the argument (RTRIM) on non-T-SQL targets to preserve the count."""

    @pytest.mark.parametrize("target", ("mysql", "oracle", "postgresql"))
    def test_len_trims_trailing_on_other_engines(self, target: str) -> None:
        # A column argument keeps the runtime RTRIM emulation.
        out = _tx("SELECT LEN(c) AS r FROM t", "tsql", target)
        assert "RTRIM(" in out.upper(), out

    @pytest.mark.parametrize("target", ("oracle", "postgresql"))
    def test_len_literal_folds_to_count(self, target: str) -> None:
        # The corpus case's literal argument folds to T-SQL LEN's value (3).
        out = _tx(_case("challenge_sqlserver.sql", "ts-len-trailing"), "tsql", target)
        assert re.search(r"(?i)SELECT 3 AS r", out), out

    def test_len_unchanged_on_tsql(self) -> None:
        out = _tx("SELECT LEN('abc   ') AS r", "tsql", "tsql")
        assert "RTRIM" not in out.upper(), out

    def test_len_counts_trailing_from_oracle(self) -> None:
        # Reverse direction: Oracle/PG LENGTH counts trailing spaces, so on a
        # T-SQL target emit LEN(x + '.') - 1 to preserve the count.
        out = _tx(
            _case("challenge_oracle.sql", "ora-length-trailing"), "oracle", "tsql"
        )
        assert re.search(r"(?i)LEN\(.*\+\s*'\.'\)\s*-\s*1", out), out


class TestPgLeftNegative:
    """PostgreSQL ``LEFT(s, -n)`` returns "all but the last |n|" characters
    (LEFT('abc', -1) = 'ab'); MySQL returns '' for a negative length. The emitter
    rebases to LEFT(s, GREATEST(CHAR_LENGTH(s) + n, 0)) on a MySQL target."""

    def test_negative_length_rebased(self) -> None:
        out = _tx(
            _case("challenge_postgresql.sql", "pg-left-neg"), "postgresql", "mysql"
        )
        assert re.search(
            r"(?i)LEFT\(.*GREATEST\(\s*CHAR_LENGTH\(.*\)\s*\+\s*-1,\s*0\)\)", out
        ), out

    def test_positive_length_unchanged(self) -> None:
        # A positive length is not rebased — LEFT('abc', 2) stays as-is.
        out = _tx("SELECT LEFT('abc', 2) AS r", "postgresql", "mysql")
        assert "GREATEST" not in out.upper(), out


class TestTsqlAvgIntegerPromotion:
    """T-SQL ``AVG`` returns the input type, so ``AVG`` over an integer column
    truncates (AVG of 1, 2 = 1); MySQL/Oracle/PostgreSQL always average as a
    decimal (1.5). The emitter promotes the argument (``AVG((x) * 1.0)``)."""

    @pytest.mark.parametrize(
        "fixture,source,keyword",
        [
            ("challenge_mysql.sql", "mysql", "my-avg-int"),
            ("challenge_postgresql.sql", "postgresql", "pg-avg-int"),
        ],
    )
    def test_avg_promoted_to_decimal_on_tsql(
        self, fixture: str, source: str, keyword: str
    ) -> None:
        out = _tx(_case(fixture, keyword), source, "tsql")
        assert re.search(r"(?i)AVG\(\s*\(.*\)\s*\*\s*1\.0\s*\)", out), out

    def test_avg_not_promoted_on_pg(self) -> None:
        # The promotion is T-SQL-only; PG already averages as decimal.
        out = _tx(_case("challenge_mysql.sql", "my-avg-int"), "mysql", "postgresql")
        assert "* 1.0" not in out, out


class TestLogArgumentOrder:
    """PostgreSQL ``LOG(base, x)`` takes the base first; T-SQL ``LOG(x, base)``
    takes it last, so the two arguments must be swapped (LOG(2, 8) = 3)."""

    def test_pg_log_two_arg_swaps_for_tsql(self) -> None:
        out = _tx(
            _case("challenge_postgresql.sql", "pg-log-2arg"), "postgresql", "tsql"
        )
        assert re.search(r"(?i)LOG\(\s*8\s*,\s*2\s*\)", out), out


class TestNullOrderingEmulation:
    """Oracle/PostgreSQL sort NULLs HIGH by default (LAST ascending); MySQL and
    T-SQL sort them LOW and lack a NULLS FIRST/LAST keyword. The emitter restores
    the source order with a leading ``CASE WHEN col IS NULL`` priority key."""

    @pytest.mark.parametrize("target", ("mysql", "tsql"))
    def test_oracle_nulls_last_default_emulated(self, target: str) -> None:
        out = _tx(
            _case("challenge_oracle.sql", "ora-order-nulls-default"), "oracle", target
        )
        assert re.search(r"(?i)CASE WHEN .*IS NULL THEN 1 ELSE 0 END", out), out

    @pytest.mark.parametrize("target", ("mysql", "tsql"))
    def test_pg_nulls_last_default_emulated(self, target: str) -> None:
        out = _tx(
            _case("challenge_postgresql.sql", "pg-order-nulls-default"),
            "postgresql",
            target,
        )
        assert re.search(r"(?i)CASE WHEN .*IS NULL THEN 1 ELSE 0 END", out), out

    @pytest.mark.parametrize("target", ("mysql", "tsql"))
    def test_pg_group_by_nulls_last_emulated(self, target: str) -> None:
        out = _tx(
            _case("challenge_postgresql.sql", "po-group-null"), "postgresql", target
        )
        assert re.search(r"(?i)CASE WHEN .*IS NULL THEN 1 ELSE 0 END", out), out

    def test_tsql_distinct_wraps_to_keep_key(self) -> None:
        # T-SQL forbids an ORDER BY expression outside the select list under
        # DISTINCT — the DISTINCT now wraps in a derived table and the
        # null-priority key orders OUTSIDE it (live-verified 1, 2, NULL).
        out = " ".join(
            _exec_lines(
                _tx(
                    _case("challenge_postgresql.sql", "po-distinct-null"),
                    "postgresql",
                    "tsql",
                )
            ).split()
        )
        assert re.search(r"(?i)\) uq_d ORDER BY CASE WHEN x IS NULL", out), out

    def test_mysql_distinct_keeps_key(self) -> None:
        # MySQL allows a non-selected ORDER BY expression under DISTINCT, so the
        # emulation still applies there.
        out = _tx(
            _case("challenge_postgresql.sql", "po-distinct-null"), "postgresql", "mysql"
        )
        assert re.search(r"(?i)CASE WHEN .*IS NULL THEN 1 ELSE 0 END", out), out

    def test_window_order_by_untouched(self) -> None:
        # A window ORDER BY must NOT get a null-priority key (it would change the
        # frame's peer groups).
        out = _tx("SELECT ROW_NUMBER() OVER (ORDER BY x) FROM t", "postgresql", "mysql")
        assert "IS NULL THEN" not in out.upper(), out


class TestMysqlReplaceNullPropagates:
    """MySQL REPLACE propagates NULL — REPLACE(str, NULL, x) is NULL — while
    Oracle ignores a NULL search/replace and returns the subject unchanged. A
    literal-NULL arg makes the MySQL result NULL; fold it. Only fires for a
    literal NULL, so plain REPLACE (and its roundtrip) is untouched."""

    @pytest.mark.parametrize("target", ("oracle", "postgresql", "tsql"))
    def test_replace_literal_null_is_null(self, target: str) -> None:
        out = _tx(_case("challenge_mysql.sql", "my-replace-null2"), "mysql", target)
        # The REPLACE call collapsed to a bare NULL (no REPLACE call survives).
        assert "REPLACE(" not in out.upper(), out
        assert re.search(r"(?i)\bNULL\s+IS\s+NULL\b", out), out

    def test_replace_without_null_is_unchanged(self) -> None:
        out = _tx("SELECT REPLACE('abc', 'a', 'x') AS r", "mysql", "oracle")
        assert "REPLACE('abc', 'a', 'x')" in out, out


class TestMysqlConcatNumBool:
    """MySQL CONCAT stringifies numbers, floats and booleans (5->'5', TRUE->'1')
    and propagates NULL. Cured by the CONCAT boolean->int and NULL-fold handlers:
    CONCAT('x',5), CONCAT('x',5.5), CONCAT('x',TRUE)->CONCAT('x',1),
    CONCAT('x',NULL)->NULL all match. Live-verified on all three."""

    @pytest.mark.parametrize("target", ("oracle", "postgresql", "tsql"))
    def test_concat_num_bool_null(self, target: str) -> None:
        out = _tx(_case("challenge_mysql.sql", "my-fconcatnum"), "mysql", target)
        assert "CONCAT('x', 1)" in out and "NULL" in out, out


class TestPgCastMatrix:
    """PG cast matrix: the failing legs were the deprecated TEXT cast target
    (tsql error 529 / no VARCHAR length on oracle); cured by the CAST-only
    TEXT type remap. Live value-verified (precision-tolerant) 2026-07-24."""

    def test_tsql_text_cast_modernized(self) -> None:
        out = _tx(
            _case("challenge_postgresql.sql", "pg-cast-matrix"), "postgresql", "tsql"
        )
        assert "VARCHAR(MAX)" in out, out
        assert "AS TEXT" not in out.upper(), out
        assert "::" not in out, out

    def test_oracle_text_cast_modernized(self) -> None:
        out = _tx(
            _case("challenge_postgresql.sql", "pg-cast-matrix"), "postgresql", "oracle"
        )
        assert "VARCHAR2(4000)" in out, out
        assert "BINARY_DOUBLE" in out, out
        assert "::" not in out, out


class TestPgSynonymAsView:
    """The emitted view DDL is plain and valid; the corpus live check failed
    only because it ran as SYSTEM (whose schema has the SYN dictionary
    synonym). Identity-proof: OR REPLACE/ALTER added, source text absent."""

    def test_oracle_view_form(self) -> None:
        out = _tx(
            _case("challenge_postgresql.sql", "pg-synonym-as-view"),
            "postgresql",
            "oracle",
        )
        assert re.search(r"(?i)CREATE OR REPLACE VIEW syn", out), out

    def test_tsql_view_form(self) -> None:
        out = _tx(
            _case("challenge_postgresql.sql", "pg-synonym-as-view"),
            "postgresql",
            "tsql",
        )
        assert re.search(r"(?i)CREATE OR ALTER VIEW syn", out), out


class TestGroupConcatUnorderedRefinement:
    """GROUP_CONCAT with no ORDER BY is unordered in MySQL, so Oracle's LISTAGG
    (which requires WITHIN GROUP) legitimately imposes a deterministic order."""

    def test_oracle_listagg_ordered(self) -> None:
        out = _exec_lines(
            _tx(_case("challenge_mysql.sql", "my-gc-order"), "mysql", "oracle")
        )
        assert re.search(r"(?i)LISTAGG\(.*WITHIN GROUP \(ORDER BY", out), out
        assert "GROUP_CONCAT" not in out.upper(), out


class TestTsqlOrderStringsCollation:
    """T-SQL CI ordering to a CS target gets the LOWER() key emulation; the
    MySQL target is CI natively so the plain column order is kept."""

    @pytest.mark.parametrize("target", ("oracle", "postgresql"))
    def test_cs_target_gets_lower_key(self, target: str) -> None:
        out = _tx(_case("challenge_sqlserver.sql", "ts-order-strings"), "tsql", target)
        assert re.search(r"(?i)ORDER BY LOWER\(x\)", out), out

    def test_mysql_ci_target_plain(self) -> None:
        out = _exec_lines(
            _tx(_case("challenge_sqlserver.sql", "ts-order-strings"), "tsql", "mysql")
        )
        assert re.search(r"(?i)ORDER BY x", out), out
        assert "LOWER" not in out.upper(), out


class TestWaitforExecSystemProc:
    """WAITFOR DELAY maps to a PUBLIC-granted sleep on Oracle and EXEC of a
    Microsoft system procedure degrades to a warned carrier off T-SQL."""

    def test_oracle_sleep_and_carrier(self) -> None:
        result = Transpiler().transpile(
            _case("challenge_sqlserver.sql", "ts-waitfor-exec"),
            source="tsql",
            target="oracle",
        )
        assert "DBMS_SESSION.SLEEP(1);" in result.sql, result.sql
        code = _exec_lines(result.sql)
        assert "DBMS_LOCK" not in code, result.sql
        assert "sp_who" not in code, result.sql
        assert any("sp_who" in str(w) for w in result.warnings), result.warnings

    @pytest.mark.parametrize("target", ("postgresql", "mysql"))
    def test_other_targets_carrier(self, target: str) -> None:
        result = Transpiler().transpile(
            _case("challenge_sqlserver.sql", "ts-waitfor-exec"),
            source="tsql",
            target=target,
        )
        code = "\n".join(
            ln for ln in result.sql.splitlines() if not ln.lstrip().startswith("--")
        )
        assert "sp_who" not in code, result.sql
        assert any("sp_who" in str(w) for w in result.warnings), result.warnings


class TestTypeGapClosestType:
    """Column types the target lacks map to the closest type with a warned
    -- UNIQUE: note (docs/03-unsupported.md §3.19), never silently."""

    def test_time_to_oracle_interval(self) -> None:
        result = Transpiler().transpile(
            _case("challenge_sqlserver.sql", "ts-dttypes"),
            source="tsql",
            target="oracle",
        )
        body = _exec_lines(result.sql)
        assert "INTERVAL DAY TO SECOND" in body, result.sql
        assert re.search(r"(?i)\bb TIME\b", body) is None, result.sql
        assert re.search(r"(?i)\be DATE\b", body), result.sql  # SMALLDATETIME
        assert result.warnings, "type-gap note must warn"

    def test_interval_to_tsql_text(self) -> None:
        result = Transpiler().transpile(
            _case("challenge_oracle.sql", "ora-tz-interval"),
            source="oracle",
            target="tsql",
        )
        body = _exec_lines(result.sql)
        assert body.count("VARCHAR(30)") == 2, result.sql
        assert "INTERVAL" not in body.upper(), result.sql
        assert "DATETIMEOFFSET" in body, result.sql
        assert result.warnings, result.warnings

    def test_datetime7_clamped_on_mysql(self) -> None:
        result = Transpiler().transpile(
            _case("challenge_sqlserver.sql", "ts-datetimeoffset"),
            source="tsql",
            target="mysql",
        )
        body = _exec_lines(result.sql)
        assert "DATETIME(6)" in body, result.sql
        assert "(7)" not in body, result.sql
        assert result.warnings, result.warnings

    def test_pg_interval_to_oracle(self) -> None:
        result = Transpiler().transpile(
            _case("challenge_postgresql.sql", "pg-tz-interval"),
            source="postgresql",
            target="oracle",
        )
        body = _exec_lines(result.sql)
        assert body.upper().count("INTERVAL DAY TO SECOND") == 2, result.sql
        assert "TIMETZ" not in body.upper(), result.sql
        assert result.warnings, result.warnings


class TestOracleDateCastTruncates:
    """Off-Oracle, CAST(x AS DATE) strips the time of day; Oracle DATE keeps
    it, so an Oracle-target DATE cast from another source gains TRUNC()."""

    def test_mysql_timestamp_cast(self) -> None:
        out = _tx(_case("challenge_mysql.sql", "my-cast-truncate"), "mysql", "oracle")
        assert re.search(
            r"(?i)TRUNC\(CAST\(TIMESTAMP '2020-01-01 10:30:00' AS DATE\)\)", out
        ), out

    def test_oracle_source_keeps_its_semantics(self) -> None:
        out = _tx("SELECT CAST(SYSTIMESTAMP AS DATE) FROM DUAL", "oracle", "oracle")
        assert "TRUNC" not in out.upper(), out


class TestPgMoneyAnnotated:
    """PG money renders '$12.99'; the numeric map keeps the value but not the
    symbol — annotated + warned (docs/03-unsupported.md §3.20)."""

    def test_money_cast_warns(self) -> None:
        result = Transpiler().transpile(
            _case("challenge_postgresql.sql", "pg-cast-money"),
            source="postgresql",
            target="oracle",
        )
        assert "NUMBER(19,4)" in result.sql, result.sql
        assert any("currency" in str(w) for w in result.warnings), result.warnings


class TestOraCastDatetime3:
    """Oracle datetime casts land as native mysql/tsql types (no TIMESTAMPTZ
    leak); values are SYSDATE-nondeterministic so the idiom is asserted."""

    def test_tsql_types(self) -> None:
        out = _exec_lines(
            _tx(_case("challenge_oracle.sql", "ora-cast-datetime3"), "oracle", "tsql")
        )
        assert "DATETIMEOFFSET" in out and "TIMESTAMPTZ" not in out.upper(), out

    def test_mysql_types(self) -> None:
        out = _exec_lines(
            _tx(_case("challenge_oracle.sql", "ora-cast-datetime3"), "oracle", "mysql")
        )
        assert "AS DATETIME" in out and "TIMESTAMPTZ" not in out.upper(), out


class TestLiteralFolds:
    """Compile-time folds over literal arguments emit the SOURCE engine's
    value directly (substring edges, extended INSTR, LENGTH family, byte
    decodes, MySQL string arithmetic) — live value-verified 2026-07-24."""

    def test_mysql_substr_zero_folds_empty(self) -> None:
        out = _exec_lines(
            _tx(_case("challenge_mysql.sql", "my-fsubstr"), "mysql", "postgresql")
        )
        assert "''" in out, out
        assert "SUBSTRING('abc', 0" not in out, out

    def test_mysql_substr_zero_oracle_annotated(self) -> None:
        result = Transpiler().transpile(
            _case("challenge_mysql.sql", "my-fsubstr"), source="mysql", target="oracle"
        )
        assert "UNIQUE-1094: Oracle stores an empty string as NULL" in result.sql
        assert result.warnings, result.warnings

    def test_pg_substr_edges_rewritten(self) -> None:
        out = _exec_lines(
            _tx(
                _case("challenge_postgresql.sql", "pg-substr-edge"),
                "postgresql",
                "mysql",
            )
        )
        assert "SUBSTR('hello', 1)" in out, out  # start <= 0 -> from 1
        assert "SUBSTR('hello', 2)" in out, out  # RIGHT(s,-1) -> all but first
        assert "RIGHT(" not in out.upper(), out

    def test_oracle_instr_occurrence_folds(self) -> None:
        out = _exec_lines(
            _tx(_case("challenge_oracle.sql", "ora-instr-edge"), "oracle", "postgresql")
        )
        assert re.search(r"\b4\b", out), out
        assert "INSTR" not in out.upper(), out

    def test_oracle_instr_nonliteral_degrades(self) -> None:
        result = Transpiler().transpile(
            "SELECT INSTR(c, 'l', 1, 2) FROM t;", source="oracle", target="tsql"
        )
        assert "NULL /* UNIQUE-1087: Oracle INSTR" in result.sql, result.sql
        assert result.warnings, result.warnings

    def test_length_folds(self) -> None:
        # pg-trim-len: CHAR_LENGTH('  ') / LENGTH(TRIM('  ')) fold to 2, 0.
        out = _exec_lines(
            _tx(
                _case("challenge_postgresql.sql", "pg-trim-len"), "postgresql", "oracle"
            )
        )
        assert re.search(r"(?i)SELECT 2, 0\b", out), out

    def test_emoji_len_folds(self) -> None:
        assert "SELECT 2" in _exec_lines(
            _tx(_case("challenge_sqlserver.sql", "ts-emoji-len"), "tsql", "postgresql")
        )
        assert "SELECT 1" in _exec_lines(
            _tx(_case("challenge_postgresql.sql", "pg-emoji-len"), "postgresql", "tsql")
        )
        # MySQL CHAR_LENGTH shares its IR name with byte-LENGTH, so the emoji
        # literal doesn't fold — the T-SQL emit uses an _SC collation instead.
        out = _exec_lines(
            _tx(_case("challenge_mysql.sql", "my-emoji-len"), "mysql", "tsql")
        )
        assert "COLLATE Latin1_General_100_CI_AS_SC" in out, out

    def test_b64_length_folds(self) -> None:
        out = _exec_lines(
            _tx(
                _case("challenge_postgresql.sql", "pg-blob-length"),
                "postgresql",
                "tsql",
            )
        )
        assert "SELECT 5" in out, out

    def test_hexcast_folds(self) -> None:
        out = _exec_lines(
            _tx(_case("challenge_sqlserver.sql", "ts-hexcast"), "tsql", "oracle")
        )
        assert "'Hello'" in out, out
        assert "HEXTORAW('48656C6C6F')" in out, out
        assert "TO_TIMESTAMP" not in out.upper(), out

    def test_mysql_hex_char_decodes(self) -> None:
        out = _exec_lines(
            _tx(_case("challenge_mysql.sql", "my-cast-charset"), "mysql", "oracle")
        )
        assert "'é'" in out, out
        assert (
            _exec_lines(
                _tx(_case("challenge_mysql.sql", "my-cast-hex-char"), "mysql", "oracle")
            )
            .strip()
            .startswith("SELECT NULL")
        ), "invalid utf8 byte must fold to NULL"

    def test_mysql_char_unicode_null(self) -> None:
        out = _exec_lines(
            _tx(_case("challenge_mysql.sql", "my-char-unicode"), "mysql", "postgresql")
        )
        assert "SELECT NULL" in out, out

    def test_mysql_string_arith_folds(self) -> None:
        out = _exec_lines(
            _tx(_case("challenge_mysql.sql", "my-hex-str-add"), "mysql", "postgresql")
        )
        assert "0.0 + 0" in out, out
        assert "'0x10'" not in out, out

    def test_mysql_timestr_interval_null(self) -> None:
        result = Transpiler().transpile(
            _case("challenge_mysql.sql", "my-timestr-plus"),
            source="mysql",
            target="tsql",
        )
        assert "NULL /* UNIQUE-1073: MySQL date arithmetic" in result.sql, result.sql
        assert result.warnings, result.warnings

    def test_mysql_greatest_ci_folds(self) -> None:
        out = _exec_lines(
            _tx(
                _case("challenge_mysql.sql", "my-greatest-string"),
                "mysql",
                "postgresql",
            )
        )
        assert "'B'" in out, out
        assert "GREATEST" not in out.upper(), out

    def test_trailing_zero_literal_kept(self) -> None:
        out = _tx("SELECT 'x=' || 5.50 AS r", "postgresql", "mysql")
        assert "5.50" in out, out

    def test_pg_hex_literal_is_integer(self) -> None:
        out = _exec_lines(
            _tx(
                _case("challenge_postgresql.sql", "pg-num-literals"),
                "postgresql",
                "mysql",
            )
        )
        assert "31" in out, out
        assert "x'1F'" not in out, out

    def test_pg_wide_numeric_cast_sized(self) -> None:
        out = _exec_lines(
            _tx(
                _case("challenge_postgresql.sql", "pg-scientific"),
                "postgresql",
                "mysql",
            )
        )
        assert "DECIMAL(30, 0)" in out, out


class TestWave4Rewrites:
    """Wave-4 expression/DDL rewrites, live-executed 2026-07-24."""

    def test_any_array_subquery_unwrapped(self) -> None:
        out = " ".join(
            _exec_lines(
                _tx(
                    _case("challenge_postgresql.sql", "pg-any-array-subquery"),
                    "postgresql",
                    "tsql",
                )
            ).split()
        )
        assert re.search(r"(?i)= ANY \(SELECT id FROM b\)", out), out
        assert "ARRAY" not in out.upper(), out

    def test_interval_arith_per_target(self) -> None:
        case = _case("challenge_postgresql.sql", "pg-interval-arith")
        assert "DATEADD(DAY, -1, GETDATE())" in _tx(case, "postgresql", "tsql")
        assert "INTERVAL 1 DAY" in _tx(case, "postgresql", "mysql")
        assert "INTERVAL '1' DAY" in _tx(case, "postgresql", "oracle")

    def test_now_plus_int_is_day_arith(self) -> None:
        case = _case("challenge_oracle.sql", "ora-date-plus-int")
        assert "DATE_ADD(CURRENT_TIMESTAMP, INTERVAL 1 DAY)" in _tx(
            case, "oracle", "mysql"
        )
        assert "+ INTERVAL '1' DAY" in _tx(case, "oracle", "postgresql")

    def test_cast_now_to_int_rounds_epoch_days(self) -> None:
        case = _case("challenge_sqlserver.sql", "ts-cast-date-int")
        assert "ROUND(SYSDATE - DATE '1900-01-01')" in _tx(case, "tsql", "oracle")
        assert re.search(
            r"(?i)ROUND\(EXTRACT\(EPOCH FROM \(CURRENT_TIMESTAMP - "
            r"TIMESTAMP '1900-01-01'\)\) / 86400\)",
            _tx(case, "tsql", "postgresql"),
        )

    def test_convert_style_126_mask(self) -> None:
        out = _exec_lines(
            _tx(_case("challenge_sqlserver.sql", "ts-convert-style"), "tsql", "oracle")
        )
        assert "HH24:MI:SS.FF3" in out, out
        assert '"T"' in out, out
        assert "%f" not in out, out

    def test_stragg_cast_sized(self) -> None:
        case = _case("challenge_sqlserver.sql", "ts-stragg-within2")
        assert "CAST(n AS VARCHAR2(4000))" in _tx(case, "tsql", "oracle")
        assert "CAST(n AS CHAR)" in _tx(case, "tsql", "mysql")

    def test_pg_text_column_modernized(self) -> None:
        out = _exec_lines(
            _tx(
                _case("challenge_postgresql.sql", "pg-computed-func"),
                "postgresql",
                "tsql",
            )
        )
        assert "NVARCHAR(MAX)" in out, out
        assert re.search(r"(?i)\bTEXT\b", out) is None, out


class TestWave5GroupingAndFolds:
    """Wave-5: GROUPING_ID mapping, VALUES-subquery rewrite, binary-literal
    numeric folds — live value-verified 2026-07-24."""

    def test_grouping_id_maps_to_multiarg_grouping(self) -> None:
        case = _case("challenge_sqlserver.sql", "ts-grouping-id")
        for target in ("postgresql", "mysql"):
            out = _exec_lines(_tx(case, "tsql", target))
            assert "GROUPING(a, b)" in out, out
            assert "GROUPING_ID" not in out.upper(), out
        # Oracle keeps the native spelling.
        assert "GROUPING_ID(a, b)" in _tx(case, "tsql", "oracle")

    def test_rollup_keeps_real_grouping_on_mysql(self) -> None:
        out = _exec_lines(
            _tx(_case("challenge_oracle.sql", "ora-grouping-id"), "oracle", "mysql")
        )
        assert "WITH ROLLUP" in out, out
        assert "GROUPING(deptno)" in out, out  # not folded to 0
        assert "COLLATE" not in out.upper(), out  # would break GROUPING refs

    def test_degraded_grouping_sets_folds_grouping_to_zero(self) -> None:
        result = Transpiler().transpile(
            _case("challenge_postgresql.sql", "pg-grouping"),
            source="postgresql",
            target="mysql",
        )
        code = _exec_lines(result.sql)
        assert "GROUPING" not in code.upper(), result.sql
        assert result.warnings, result.warnings

    def test_quantified_values_rewritten(self) -> None:
        out = " ".join(
            _exec_lines(
                _tx(
                    _case("challenge_postgresql.sql", "pg-all-values"),
                    "postgresql",
                    "oracle",
                )
            ).split()
        )
        assert "ALL (SELECT 1 FROM DUAL UNION ALL SELECT 2" in out, out
        assert "VALUES" not in out.upper(), out

    def test_mysql_binary_literals_fold_numeric(self) -> None:
        out = _exec_lines(
            _tx(_case("challenge_mysql.sql", "my-cast-uns2"), "mysql", "postgresql")
        )
        assert "65535" in out and "15" in out, out
        assert "bytea" not in out.lower(), out

    def test_soundex_format_masks(self) -> None:
        case = _case("challenge_mysql.sql", "my-soundex-format")
        assert "TO_CHAR(1234.5, 'FM999G999G999G990D00')" in _tx(case, "mysql", "oracle")
        assert "FORMAT(1234.5, 'N2')" in _tx(case, "mysql", "tsql")

    def test_window_clause_inlined(self) -> None:
        out = _exec_lines(
            _tx(_case("challenge_mysql.sql", "my8-window"), "mysql", "tsql")
        )
        assert out.upper().count("OVER (ORDER BY ID") == 2, out
        assert re.search(r"(?i)WINDOW\s+w\s+AS", out) is None, out


class TestWave6Procedural:
    """Wave-6 procedural/misc fixes, live-verified 2026-07-24."""

    def test_format_identifier_spec(self) -> None:
        out = _tx(
            _case("challenge_postgresql.sql", "pg-dyn-count"), "postgresql", "oracle"
        )
        assert "REPLACE(tbl, '\"', '\"\"')" in out, out
        assert "NUMBER(19)" in out, out

    def test_check_violation_sqlcode_handler(self) -> None:
        out = _tx(
            _case("challenge_postgresql.sql", "pg-realworld-transfer"),
            "postgresql",
            "oracle",
        )
        assert "SQLCODE = -2290" in out, out
        assert re.search(r"(?i)ELSE\s+RAISE;", out), out

    def test_infoschema_catalog_map(self) -> None:
        out = _exec_lines(
            _tx(_case("challenge_mysql.sql", "my-infoschema"), "mysql", "oracle")
        )
        assert re.search(r"(?i)FROM all_tables", out), out
        assert "information_schema" not in out.lower(), out

    def test_sessiontimezone_mapped_and_annotated(self) -> None:
        result = Transpiler().transpile(
            _case("challenge_oracle.sql", "ora-tz-funcs"),
            source="oracle",
            target="postgresql",
        )
        assert "current_setting('TimeZone')" in result.sql, result.sql
        assert result.warnings, result.warnings

    def test_interval_literal_extract_folds(self) -> None:
        out = _exec_lines(
            _tx(
                _case("challenge_postgresql.sql", "pg-cast-interval3"),
                "postgresql",
                "oracle",
            )
        )
        assert re.search(r",\s*5\b", " ".join(out.split())), out
        assert "EXTRACT" not in out.upper(), out


class TestWave7JsonAndDdl:
    """Wave-7: JSONB type map, GIN degrade, ALTER identity, sp_executesql
    positional binds — live-verified 2026-07-24."""

    def test_jsonb_type_maps(self) -> None:
        case = _case("challenge_postgresql.sql", "pg-gin-jsonb")
        assert "b JSON" in _exec_lines(_tx(case, "postgresql", "mysql"))
        assert "b CLOB" in _exec_lines(_tx(case, "postgresql", "oracle"))
        assert "b NVARCHAR(MAX)" in _exec_lines(_tx(case, "postgresql", "tsql"))

    def test_gin_index_degrades_warned(self) -> None:
        result = Transpiler().transpile(
            _case("challenge_postgresql.sql", "pg-gin-jsonb"),
            source="postgresql",
            target="oracle",
        )
        assert "GIN/GiST/BRIN" in result.sql, result.sql
        assert "USING gin" not in _exec_lines(result.sql), result.sql
        assert result.warnings, result.warnings

    def test_computed_jsonb_columns(self) -> None:
        case = _case("challenge_postgresql.sql", "pg-computed-jsonb")
        assert "->> '$.name'" in _tx(case, "postgresql", "mysql")
        assert "JSON_VALUE(data, '$.name')" in _tx(case, "postgresql", "tsql")

    def test_add_identity_to_mysql(self) -> None:
        out = _exec_lines(
            _tx(
                _case("challenge_postgresql.sql", "pg-add-identity"),
                "postgresql",
                "mysql",
            )
        )
        assert "AUTO_INCREMENT, ADD UNIQUE (big)" in out, out
        assert "GENERATED" not in out.upper(), out

    def test_sp_executesql_positional_binds(self) -> None:
        result = Transpiler().transpile(
            _case("challenge_sqlserver.sql", "ts-sp-executesql"),
            source="tsql",
            target="oracle",
        )
        assert re.search(
            r"(?i)EXECUTE IMMEDIATE V_SQL USING 5;", result.sql
        ), result.sql
        assert "=>" not in result.sql, result.sql
        assert result.warnings, result.warnings

    def test_json_object_star_gated_on_pg(self) -> None:
        result = Transpiler().transpile(
            _case("challenge_oracle.sql", "ora23-json-object-star"),
            source="oracle",
            target="postgresql",
        )
        assert result.warnings, result.warnings
        assert "JSON_OBJECT(*)" not in _exec_lines(result.sql), result.sql

    def test_inline_index_kept_on_mysql(self) -> None:
        out = _exec_lines(
            _tx(_case("challenge_mysql.sql", "my-json-index"), "mysql", "mysql")
        )
        assert re.search(r"(?i)INDEX \(\(CAST", out), out


class TestInlineIndexReconstructed:
    """The T-SQL inline INDEX element (sqlglot misparses it as a column named
    INDEX) is reconstructed: inline on T-SQL/MySQL, a separate CREATE INDEX
    on PG/Oracle. Live-executed on all three 2026-07-24."""

    def test_separate_create_index_on_pg_oracle(self) -> None:
        for target in ("postgresql", "oracle"):
            out = " ".join(
                _exec_lines(
                    _tx(
                        _case("challenge_sqlserver.sql", "ts-inline-index2"),
                        "tsql",
                        target,
                    )
                ).split()
            )
            assert "CREATE INDEX ix_name ON t (name)" in out, out
            assert '"INDEX"' not in out, out

    def test_inline_on_mysql(self) -> None:
        out = _exec_lines(
            _tx(_case("challenge_sqlserver.sql", "ts-inline-index2"), "tsql", "mysql")
        )
        assert "INDEX ix_name (name)" in out, out


class TestSelectIntoDerivedColumnsNamed:
    """The SELECT-INTO tail's derived table aliases unnamed projections on
    T-SQL (error 8155) — the text-path twin of _name_tsql_derived_columns."""

    def test_tail_derived_column_aliased(self) -> None:
        out = _tx(_case("challenge_mysql.sql", "my-select-into-out"), "mysql", "tsql")
        assert "SELECT 1 AS uq_col1" in out, out


class TestCrossStatementMetadata:
    """COLUMN_TYPES harvest: the script's own CREATE TABLE supplies column
    types to later statements. Live-verified 2026-07-24."""

    def test_drop_not_null_restates_type(self) -> None:
        case = _case("challenge_postgresql.sql", "pg-drop-not-null")
        assert "MODIFY a INT NULL" in _tx(case, "postgresql", "mysql")
        assert "ALTER COLUMN a INT NULL" in _tx(case, "postgresql", "tsql")
        out = _tx(case, "postgresql", "oracle")
        assert "MODIFY (a NULL)" in out and "SQLCODE NOT IN (-1451, -1442)" in out

    def test_unknown_column_degrades_warned(self) -> None:
        result = Transpiler().transpile(
            "ALTER TABLE elsewhere ALTER COLUMN x DROP NOT NULL;",
            source="postgresql",
            target="mysql",
        )
        assert result.warnings, result.sql
        assert "does not define" in result.sql, result.sql

    def test_lob_expression_index_degrades(self) -> None:
        case = _case("challenge_postgresql.sql", "pg-expr-index")
        for target in ("mysql", "oracle"):
            result = Transpiler().transpile(case, source="postgresql", target=target)
            assert "LOB-typed column" in result.sql, result.sql
            assert result.warnings, result.warnings

    def test_varchar_expression_index_native(self) -> None:
        out = _tx(
            "CREATE TABLE v (a INT, b VARCHAR(50)); CREATE INDEX iv ON v (lower(b));",
            "postgresql",
            "oracle",
        )
        assert "CREATE INDEX iv ON v(LOWER(b))" in out.replace("  ", " "), out


class TestSetTransactionModes:
    """Transaction access modes per target; the single-line multi-statement
    batch splits. Live-executed on all four 2026-07-24."""

    def test_oracle_read_only(self) -> None:
        out = _exec_lines(
            _tx(_case("challenge_mysql.sql", "my-set-transaction"), "mysql", "oracle")
        )
        assert "SET TRANSACTION READ ONLY" in out, out
        assert "START TRANSACTION" not in out.upper(), out

    def test_mysql_identity_keeps_long_spelling(self) -> None:
        out = _exec_lines(
            _tx(_case("challenge_mysql.sql", "my-set-transaction"), "mysql", "mysql")
        )
        assert "START TRANSACTION READ ONLY" in out, out

    def test_tsql_mode_noted(self) -> None:
        result = Transpiler().transpile(
            _case("challenge_mysql.sql", "my-set-transaction"),
            source="mysql",
            target="tsql",
        )
        assert "no READ ONLY access mode" in result.sql, result.sql
        assert result.warnings, result.warnings


class TestPgFnAttrsAndAggregationAssignment:
    """pg-func-attrs + ts-dyn-concat-loop fixes, live-compiled 2026-07-24."""

    @pytest.mark.parametrize("target", ("tsql", "oracle", "mysql"))
    def test_fn_attribute_tail_stripped(self, target: str) -> None:
        out = _exec_lines(
            _tx(
                _case("challenge_postgresql.sql", "pg-func-attrs"), "postgresql", target
            )
        )
        assert "SECURITY" not in out.upper(), out
        assert "PARALLEL" not in out.upper(), out

    def test_aggregation_assignment_listagg(self) -> None:
        out = _tx(
            _case("challenge_sqlserver.sql", "ts-dyn-concat-loop"), "tsql", "oracle"
        )
        assert re.search(r"(?i)LISTAGG\('DROP TABLE ' \|\| table_name", out), out
        assert "WITHIN GROUP (ORDER BY ROWNUM)" in out, out
        assert "EXECUTE IMMEDIATE V_SQL;" in out, out
        assert re.search(r"(?i)\bFROM user_tables\b", out), out


class TestInsteadOfTriggers:
    """T-SQL INSTEAD OF triggers into PG: row-level rewrite (views) and the
    BEFORE-row suppression emulation (tables). Live semantics verified
    2026-07-24 (insert-through-view, exactly-once insert, filtered delete)."""

    def test_view_trigger_row_level(self) -> None:
        out = _exec_lines(
            _tx(
                _case("challenge_sqlserver.sql", "ts-trigger-on-view"),
                "tsql",
                "postgresql",
            )
        )
        assert "INSTEAD OF INSERT ON v" in out, out
        assert "FOR EACH ROW" in out, out
        assert "REFERENCING" not in out.upper(), out
        assert "SELECT NEW.id" in out, out

    def test_table_trigger_before_suppression(self) -> None:
        out = _exec_lines(
            _tx(
                _case("challenge_sqlserver.sql", "ts-instead-of-insert"),
                "tsql",
                "postgresql",
            )
        )
        assert re.search(r"(?i)BEFORE INSERT ON t", out), out
        assert "RETURN NULL;" in out, out
        assert "pg_trigger_depth() > 1" in out, out

    def test_delete_guard_returns_old(self) -> None:
        out = _exec_lines(
            _tx(
                _case("challenge_sqlserver.sql", "ts-trg-instead-delete"),
                "tsql",
                "postgresql",
            )
        )
        assert re.search(r"(?is)pg_trigger_depth\(\) > 1 THEN\s+RETURN OLD;", out), out
        assert "SELECT OLD.id WHERE OLD.id > 0" in out, out

    def test_statement_level_aggregate_degrades_on_oracle(self) -> None:
        result = Transpiler().transpile(
            _case("challenge_sqlserver.sql", "ts-after-delete-count"),
            source="tsql",
            target="oracle",
        )
        assert result.warnings, result.warnings
        code = _exec_lines(result.sql)
        assert "deleted" not in code.lower(), result.sql


class TestTypedComputedColumnShorthand:
    """The typed MySQL computed-column shorthand models as a generated
    ColumnDefinition — chained refs inline, PERSISTED when constrained, JSON
    accessors per target. Live values exact 2026-07-24."""

    def test_chained_reference_inlined(self) -> None:
        case = _case("challenge_mysql.sql", "my-gencol2")
        pg = _exec_lines(_tx(case, "mysql", "postgresql"))
        assert "GENERATED ALWAYS AS (a + a * 2) STORED" in pg, pg
        ts = _exec_lines(_tx(case, "mysql", "tsql"))
        assert "b AS (a * 2) PERSISTED" in ts, ts

    def test_constrained_computed_persisted(self) -> None:
        out = _exec_lines(
            _tx(_case("challenge_mysql.sql", "my-gen-constr"), "mysql", "tsql")
        )
        assert "b AS (a + 1) PERSISTED" in out, out

    def test_json_extract_typed_accessors(self) -> None:
        case = _case("challenge_mysql.sql", "my-json-index")
        pg = _exec_lines(_tx(case, "mysql", "postgresql"))
        assert "CAST(JSON_EXTRACT_PATH_TEXT(b, 'x') AS INT)" in pg, pg
        ts = _exec_lines(_tx(case, "mysql", "tsql"))
        assert (
            "CAST(ISNULL(JSON_QUERY(b, '$.x'), JSON_VALUE(b, '$.x')) AS INT)" in ts
        ), ts

    def test_pg_fullsyntax_scalar_accessor_unaffected(self) -> None:
        # PG's ->> (JSONExtractScalar) keeps its passthrough rendering.
        out = _tx(
            _case("challenge_postgresql.sql", "pg-computed-jsonb"),
            "postgresql",
            "mysql",
        )
        assert "->> '$.name'" in out, out


class TestCursorAttributes:
    """Oracle cursor attributes map before the IR (which read c%FOUND as
    modulo): FETCH-status forms + a per-cursor rowcount counter. Live-compiled
    VALID on tsql + mysql 2026-07-24."""

    def test_tsql_counter_and_status(self) -> None:
        out = _exec_lines(
            _tx(_case("challenge_oracle.sql", "ora-cursor-attr"), "oracle", "tsql")
        )
        assert "DECLARE @uq_c_rc INT = 0;" in out, out
        assert "IF @@FETCH_STATUS = 0 SET @uq_c_rc = @uq_c_rc + 1;" in out, out
        assert "% FOUND" not in out and "% ROWCOUNT" not in out, out

    def test_mysql_handler_flag_and_counter(self) -> None:
        out = _exec_lines(
            _tx(_case("challenge_oracle.sql", "ora-cursor-attr"), "oracle", "mysql")
        )
        assert "DECLARE CONTINUE HANDLER FOR NOT FOUND SET v_fetch_done" in out, out
        # %NOTFOUND reads a PER-cursor done flag transferred from the shared
        # handler flag after each FETCH (so a nested cursor cannot leak its
        # exhaustion into an outer loop — finding N5b).
        assert "IF NOT v_uq_c_done THEN" in out, out
        assert "SET v_uq_c_done = v_fetch_done; SET v_fetch_done = FALSE;" in out, out
        assert re.search(r"(?i)SET uq_c_rc = uq_c_rc \+ 1", out), out


class TestCheckXorPredicateWrap:
    """A CHECK comparing predicate operands wraps them in CASE 1/0 on T-SQL
    (no boolean value type). Live: XOR enforced 2026-07-24."""

    def test_case_wrap(self) -> None:
        out = _exec_lines(
            _tx(_case("challenge_postgresql.sql", "pg-check-xor"), "postgresql", "tsql")
        )
        assert (
            "CHECK (CASE WHEN a IS NULL THEN 1 ELSE 0 END <> "
            "CASE WHEN b IS NULL THEN 1 ELSE 0 END)" in out
        ), out


class TestPlsqlExpressionCastContext:
    """Oracle inverts CAST typing rules between contexts: a PL/SQL expression
    rejects any constrained type (PLS-00103) while a SQL statement requires the
    char length (ORA-00906). The PRINT argument is a marked expression
    position, so its char CAST is emitted lengthless. Live-compiled VALID on
    oracle 2026-07-24."""

    def test_print_cast_is_lengthless(self) -> None:
        out = _tx(_case("challenge_sqlserver.sql", "ts-cursor-attr"), "tsql", "oracle")
        line = next(x for x in out.splitlines() if "PUT_LINE" in x)
        assert re.search(r"AS\s+VARCHAR2\s*\)", line), out
        assert not re.search(r"AS\s+VARCHAR2?\s*\(", line), out

    def test_sql_statement_cast_keeps_length(self) -> None:
        out = _tx(
            "CREATE PROCEDURE p AS BEGIN DECLARE @v VARCHAR(10); "
            "SELECT @v = CAST(n AS VARCHAR(10)) FROM t; END",
            "tsql",
            "oracle",
        )
        assert re.search(r"(?i)AS\s+VARCHAR2\s*\(\s*10\s*\)", out), out


class TestMergeExtendedClauses:
    """T-SQL's extended MERGE clauses: NOT MATCHED BY SOURCE splits into a
    follow-up anti-join statement (PG only gained the clause in 17; Oracle
    never had it), and Oracle folds a conditional MATCHED UPDATE/DELETE pair
    into its single-clause UPDATE + DELETE WHERE spelling. Live: identical
    final rows on tsql/oracle/pg 2026-07-24."""

    def _out(self, target: str) -> str:
        return _tx(_case("challenge_sqlserver.sql", "ts-merge-full"), "tsql", target)

    def test_oracle_folds_matched_pair_and_splits_by_source(self) -> None:
        out = self._out("oracle")
        assert (
            "WHEN MATCHED THEN UPDATE SET n = CASE WHEN src.n > 0 "
            "THEN src.n ELSE tgt.n END DELETE WHERE NOT (src.n > 0)" in out
        ), out
        assert (
            "DELETE FROM tgt WHERE NOT EXISTS "
            "(SELECT 1 FROM src WHERE tgt.id = src.id)" in out
        ), out
        assert "BY SOURCE" not in _exec_lines(out), out

    def test_postgresql_keeps_matched_pair_and_splits_by_source(self) -> None:
        out = self._out("postgresql")
        assert "WHEN MATCHED AND src.n > 0 THEN UPDATE SET n = src.n" in out, out
        assert "WHEN MATCHED THEN DELETE" in out, out
        assert (
            "DELETE FROM tgt WHERE NOT EXISTS "
            "(SELECT 1 FROM src WHERE tgt.id = src.id)" in out
        ), out
        assert "BY SOURCE" not in _exec_lines(out), out


# --- Audit 2026-07-24 finding N2: MERGE conditional-DELETE fold safety ---


class TestMergeConditionalDeleteFoldSafety:
    """N2: Oracle folds a conditional MATCHED DELETE/UPDATE pair into
    ``UPDATE … DELETE WHERE``, but Oracle evaluates ``DELETE WHERE`` against
    *post-update* values. Folding is only value-equivalent when the DELETE
    condition references no target column the UPDATE assigns."""

    _UNSAFE = (
        "MERGE INTO dst AS d USING src AS s ON d.id = s.id "
        "WHEN MATCHED AND d.qty = 0 THEN DELETE "
        "WHEN MATCHED THEN UPDATE SET d.qty = s.qty;"
    )
    # UPDATE-first neighbour: the folded DELETE cond NOT(uc) also reads d.qty.
    _UNSAFE_UPDATE_FIRST = (
        "MERGE INTO dst AS d USING src AS s ON d.id = s.id "
        "WHEN MATCHED AND d.qty > 0 THEN UPDATE SET d.qty = s.qty "
        "WHEN MATCHED THEN DELETE;"
    )
    _SAFE = (
        "MERGE INTO dst AS d USING src AS s ON d.id = s.id "
        "WHEN MATCHED AND s.qty = 0 THEN DELETE "
        "WHEN MATCHED THEN UPDATE SET d.qty = s.qty;"
    )

    def test_unsafe_delete_on_updated_column_degrades(self) -> None:
        r = Transpiler().transpile(self._UNSAFE, "tsql", "oracle")
        # No silent post-update DELETE WHERE fold.
        assert "DELETE WHERE" not in _exec_lines(r.sql), r.sql
        # The whole MERGE is degraded to a carrier + warning.
        assert "-- UNIQUE-" in r.sql
        assert r.warnings, "unsafe fold must warn"
        assert any("post-update" in w.message.lower() for w in r.warnings), r.warnings

    def test_unsafe_update_first_order_degrades(self) -> None:
        r = Transpiler().transpile(self._UNSAFE_UPDATE_FIRST, "tsql", "oracle")
        assert "DELETE WHERE" not in _exec_lines(r.sql), r.sql
        assert r.warnings, r.warnings

    def test_safe_source_column_condition_still_folds(self) -> None:
        out = _tx(self._SAFE, "tsql", "oracle")
        assert "DELETE WHERE s.qty = 0" in out, out
        assert "CASE WHEN NOT (s.qty = 0)" in out, out

    def test_ts_merge_full_corpus_case_still_folds(self) -> None:
        # The corpus case uses a source-column condition — must keep folding.
        out = _tx(_case("challenge_sqlserver.sql", "ts-merge-full"), "tsql", "oracle")
        assert "DELETE WHERE NOT (src.n > 0)" in out, out


# --- Audit 2026-07-24 finding N4: PG MERGE THEN DO NOTHING carve-out ---

import sqlglot  # noqa: E402

from unique.core.converter._base import sqlglot_dialect_name  # noqa: E402


def _target_parses(sql: str, target: str) -> bool:
    """Every executable (non-comment) statement in *sql* parses in *target*."""
    read = sqlglot_dialect_name(target)
    # Drop trivia first so a ``;`` inside a block/line comment can't split a
    # statement mid-token.
    stripped = re.sub(r"/\*.*?\*/", "", sql, flags=re.S)
    stripped = "\n".join(
        ln for ln in stripped.splitlines() if not ln.lstrip().startswith("--")
    )
    for stmt in stripped.split(";"):
        body = stmt.strip()
        if not body:
            continue
        sqlglot.parse(body, read=read, error_level=sqlglot.ErrorLevel.RAISE)
    return True


class TestMergeDoNothingCarveOut:
    """N4: PG MERGE ``THEN DO NOTHING`` has no T-SQL/Oracle spelling. First-
    match-wins makes it a condition carve-out on later same-kind clauses."""

    _SQL = (
        "MERGE INTO dst AS d USING src AS s ON d.id = s.id "
        "WHEN MATCHED AND s.qty IS NULL THEN DO NOTHING "
        "WHEN MATCHED THEN UPDATE SET qty = s.qty "
        "WHEN NOT MATCHED THEN INSERT (id, qty) VALUES (s.id, s.qty);"
    )

    @pytest.mark.parametrize("target", ["tsql", "oracle"])
    def test_do_nothing_carved_out(self, target: str) -> None:
        r = Transpiler().transpile(self._SQL, "postgresql", target)
        assert "DO NOTHING" not in r.sql.upper(), r.sql
        # The carve-out negates the DO NOTHING condition onto the UPDATE.
        assert "NOT (s.qty IS NULL)" in r.sql, r.sql
        assert _target_parses(r.sql, target), r.sql

    def test_unconditional_do_nothing_drops_later_matched(self) -> None:
        sql = (
            "MERGE INTO dst AS d USING src AS s ON d.id = s.id "
            "WHEN MATCHED THEN DO NOTHING "
            "WHEN NOT MATCHED THEN INSERT (id, qty) VALUES (s.id, s.qty);"
        )
        r = Transpiler().transpile(sql, "postgresql", "tsql")
        assert "DO NOTHING" not in r.sql.upper(), r.sql
        assert "WHEN MATCHED" not in _exec_lines(r.sql).upper(), r.sql
        assert "WHEN NOT MATCHED" in _exec_lines(r.sql).upper(), r.sql
        assert _target_parses(r.sql, "tsql"), r.sql

    def test_unknown_var_action_degrades(self) -> None:
        # Construct a MERGE whose action is an unknown Var directly via sqlglot.
        tree = sqlglot.parse_one(
            "MERGE INTO dst AS d USING src AS s ON d.id = s.id "
            "WHEN MATCHED THEN DELETE",
            read="tsql",
        )
        when = tree.args["whens"].expressions[0]
        when.set("then", sqlglot.exp.Var(this="FROBNICATE"))
        from unique.core.converter.emit import _merge_carve_do_nothing

        reason = _merge_carve_do_nothing(tree)
        assert reason is not None and "FROBNICATE" in reason


class TestMergeOutputToPostgres:
    """N3: T-SQL MERGE OUTPUT → PostgreSQL. PG has no MERGE RETURNING; the
    OUTPUT must degrade to the documented carrier + warning, and the tail must
    never land on a follow-up statement or inside a comment."""

    _PLAIN = (
        "MERGE INTO dst AS d USING src AS s ON d.id = s.id "
        "WHEN MATCHED THEN UPDATE SET d.qty = s.qty "
        "OUTPUT $action, inserted.id;"
    )
    _BY_SOURCE = (
        "MERGE INTO dst AS d USING src AS s ON d.id = s.id "
        "WHEN MATCHED THEN UPDATE SET d.qty = s.qty "
        "WHEN NOT MATCHED BY SOURCE THEN DELETE "
        "OUTPUT $action, inserted.id;"
    )
    _COMMENT = (
        "MERGE INTO dst AS d USING src AS s ON d.id = s.id "
        "WHEN MATCHED THEN UPDATE SET d.qty = s.qty -- qty sync\n"
        "OUTPUT $action, inserted.id;"
    )

    @pytest.mark.parametrize("sql", [_PLAIN, _BY_SOURCE, _COMMENT])
    def test_merge_output_to_pg_degrades_no_returning(self, sql: str) -> None:
        r = Transpiler().transpile(sql, "tsql", "postgresql")
        assert "RETURNING" not in _exec_lines(r.sql).upper(), r.sql
        assert "OUTPUT/RETURNING result set" in r.sql, r.sql
        assert r.warnings, r.warnings
        assert _target_parses(r.sql, "postgresql"), r.sql

    def test_plain_insert_output_to_pg_still_returns(self) -> None:
        # Regression: non-MERGE OUTPUT → PG keeps its valid RETURNING.
        r = Transpiler().transpile(
            "INSERT INTO t (a) OUTPUT INSERTED.id VALUES (1)", "tsql", "postgresql"
        )
        assert "RETURNING" in r.sql.upper(), r.sql


class TestInsertSelectConflict:
    """``pg-insert-select-conflict`` — INSERT … SELECT with ON CONFLICT (id) DO
    NOTHING models the upsert per target instead of dropping the clause (audit
    2026-07-24 B1/N1). The case seeds a PK conflict so DO NOTHING is a real
    no-op (scenario adequacy)."""

    def _out(self, target: str) -> str:
        return _tx(
            _case("challenge_postgresql.sql", "pg-insert-select-conflict"),
            "postgresql",
            target,
        )

    def test_tsql_lowers_conflict_to_insert_only_merge(self) -> None:
        out = self._out("tsql")
        assert "MERGE INTO" in out, out
        assert "WHEN NOT MATCHED THEN INSERT" in out, out
        assert "ON CONFLICT" not in _exec_lines(out).upper(), out

    def test_oracle_lowers_conflict_to_insert_only_merge(self) -> None:
        out = self._out("oracle")
        assert "MERGE INTO" in out, out
        assert "ON CONFLICT" not in _exec_lines(out).upper(), out

    def test_mysql_uses_insert_ignore(self) -> None:
        out = self._out("mysql")
        assert "INSERT IGNORE INTO" in out, out
        # Strip the honesty annotation (which names ON CONFLICT) before the
        # source-idiom-absent check.
        code = re.sub(r"/\*.*?\*/", "", _exec_lines(out), flags=re.DOTALL)
        assert "ON CONFLICT" not in code.upper(), out


class TestMoneyLiteralMangle:
    """N8/B9: T-SQL's bare money literal (``$12.50``) sqlglot mis-parses as
    ``Column(this=Literal(50), table=Identifier($12))`` — a bogus column
    ``50`` of a table ``$12``. Rebuilt as the numeric literal at conversion
    time instead of shipping the garbage ``table.column`` shape."""

    @pytest.mark.parametrize(
        ("literal", "expected"),
        [
            ("$12.50", "12.50"),
            ("$0.5", "0.5"),
            ("$12.05", "12.05"),
            ("$100", "100"),
        ],
    )
    @pytest.mark.parametrize("target", ["postgresql", "oracle", "mysql"])
    def test_money_literal_becomes_numeric(
        self, literal: str, expected: str, target: str
    ) -> None:
        out = _tx(f"SELECT {literal} AS price;", "tsql", target)
        assert expected in out, out
        assert "$" not in out, out
        assert _target_parses(out, target), out

    def test_money_literal_survives_arithmetic(self) -> None:
        out = _tx("SELECT $12.50 + 1;", "tsql", "postgresql")
        assert "12.50" in out or "12.5" in out, out
        assert "$" not in out, out

    def test_negative_control_bracket_quoted_identifier_untouched(self) -> None:
        # A genuine bracket-quoted identifier that merely starts with '$'
        # (never a valid *unquoted* T-SQL identifier) must not be rewritten.
        out = _tx("SELECT [$12abc] FROM t;", "tsql", "postgresql")
        assert "12abc" in out.replace('"', ""), out

    def test_negative_control_quoted_dotted_form_untouched(self) -> None:
        # A quoted "$12".50 is invalid T-SQL (live-verified: Msg 102) and is
        # NOT the money-literal shorthand, unlike the unquoted form — it must
        # not be silently reinterpreted as 12.50.
        out = _tx('SELECT "$12".50 FROM t;', "tsql", "postgresql")
        assert "12.50" not in out, out

    def test_non_tsql_source_flags_the_same_shape_as_garbage(self) -> None:
        # Oracle/MySQL have no money-literal shorthand — the identical
        # Column(table=$12, this=Literal(50)) shape there is genuine garbage
        # (07-08 N3's detector, generalized one level down).
        from unique.core.validation import validate_source

        issues = validate_source("SELECT $12.50 AS price;", "oracle")
        assert issues and "not a valid column reference" in issues[0].message


class TestRowcountDivergenceAnnotation:
    """N11/B12: Oracle's implicit-cursor ``SQL%ROWCOUNT`` (rows MATCHED)
    maps to MySQL's ``ROW_COUNT()`` (rows CHANGED) — the mapping is kept
    (still the closest fit) but annotated with a UNIQUE: note + warning
    instead of shipped silently. T-SQL's ``@@ROWCOUNT`` is matched-rows too
    (verified equivalent) and stays unannotated."""

    _ORACLE_SRC = (
        "CREATE PROCEDURE p AS BEGIN "
        "UPDATE dst SET qty = 7 WHERE id = 1; "
        "IF SQL%ROWCOUNT = 0 THEN INSERT INTO dst (id, qty) VALUES (1, 7); "
        "END IF; END;"
    )

    def test_mysql_target_annotates_and_warns(self) -> None:
        r = Transpiler().transpile(self._ORACLE_SRC, "oracle", "mysql")
        assert "ROW_COUNT()" in r.sql, r.sql
        assert "UNIQUE-1192:" in r.sql, r.sql
        assert "changed rows" in r.sql, r.sql
        assert any(
            "ROW_COUNT() counts rows CHANGED" in w.message for w in r.warnings
        ), r.warnings

    def test_tsql_target_stays_unannotated(self) -> None:
        r = Transpiler().transpile(self._ORACLE_SRC, "oracle", "tsql")
        assert "@@ROWCOUNT" in r.sql, r.sql
        assert "UNIQUE-" not in r.sql, r.sql
        assert not r.warnings, r.warnings

    def test_warning_deduplicated_across_multiple_occurrences(self) -> None:
        # Two independent SQL%ROWCOUNT checks in one routine must not spam
        # the same warning twice (guardrail 5: aggregated, not repeated).
        src = (
            "CREATE PROCEDURE p AS BEGIN "
            "UPDATE dst SET qty = 7 WHERE id = 1; "
            "IF SQL%ROWCOUNT = 0 THEN INSERT INTO dst (id, qty) VALUES (1, 7); "
            "END IF; "
            "UPDATE dst SET qty = 8 WHERE id = 2; "
            "IF SQL%ROWCOUNT = 0 THEN INSERT INTO dst (id, qty) VALUES (2, 8); "
            "END IF; END;"
        )
        r = Transpiler().transpile(src, "oracle", "mysql")
        matches = [
            w for w in r.warnings if "ROW_COUNT() counts rows CHANGED" in w.message
        ]
        assert len(matches) == 1, r.warnings

    def test_get_diagnostics_row_count_to_mysql_annotates(self) -> None:
        # The same divergence via PostgreSQL's GET DIAGNOSTICS ROW_COUNT
        # (matched rows) -> MySQL's ROW_COUNT() (base.py:2904's table).
        src = (
            "CREATE OR REPLACE FUNCTION p() RETURNS void AS $$\n"
            "DECLARE cnt INT;\n"
            "BEGIN\n"
            "  UPDATE dst SET qty = 7 WHERE id = 1;\n"
            "  GET DIAGNOSTICS cnt = ROW_COUNT;\n"
            "END;\n"
            "$$ LANGUAGE plpgsql;"
        )
        r = Transpiler().transpile(src, "postgresql", "mysql")
        assert "ROW_COUNT()" in r.sql, r.sql
        assert "UNIQUE-1192:" in r.sql, r.sql
        assert any(
            "ROW_COUNT() counts rows CHANGED" in w.message for w in r.warnings
        ), r.warnings

    def test_mysql_to_mysql_get_diagnostics_not_annotated(self) -> None:
        # Same engine both ends: no divergence, no annotation.
        src = (
            "CREATE PROCEDURE p()\n"
            "BEGIN\n"
            "  UPDATE dst SET qty = 7 WHERE id = 1;\n"
            "  GET DIAGNOSTICS @cnt = ROW_COUNT;\n"
            "END"
        )
        r = Transpiler().transpile(src, "mysql", "mysql")
        assert "UNIQUE-" not in r.sql, r.sql


class TestBitStringNumericFold:
    """red2-my-bitstring-numeric-pg: a MySQL bit-string literal ``b'101'`` used
    numerically is its integer value (5); shipping the bare bit literal to PG
    is an invalid ``bit + integer``. Fold it to the integer like the hex path."""

    def test_bitstring_folds_to_integer_on_every_target(self) -> None:
        src = _case("challenge_mysql.sql", "red2-my-bitstring-numeric-pg")
        for target in ("postgresql", "tsql", "oracle"):
            out = _exec_lines(_tx(src, "mysql", target))
            assert "5 + 0" in out, out
            assert "b'101'" not in out.lower(), out
            assert_statements_parse(out, target, context="bitstring")


class TestBoolColumnIsPredicate:
    """red2-pg-boolcol-is-true: a boolean-column ``flag IS TRUE`` / ``IS FALSE``
    predicate is invalid on engines with no boolean type (``flag IS 1`` ->
    T-SQL 156 / ORA-00908). Rewrite to the value comparison (``flag = 1`` /
    ``= 0``) there, keeping ``IS NOT TRUE``'s NULL leg."""

    def test_is_true_becomes_value_comparison(self) -> None:
        src = _case("challenge_postgresql.sql", "red2-pg-boolcol-is-true")
        for target in ("tsql", "oracle"):
            out = _exec_lines(_tx(src, "postgresql", target))
            assert "flag = 1" in out, out
            assert "IS 1" not in out and "IS TRUE" not in out.upper(), out
            assert_statements_parse(out, target, context="boolcol")

    def test_is_false_and_negations(self) -> None:
        for pred, want in (
            ("flag IS FALSE", "flag = 0"),
            ("flag IS NOT TRUE", "flag <> 1 OR flag IS NULL"),
            ("flag IS NOT FALSE", "flag <> 0 OR flag IS NULL"),
        ):
            for target in ("tsql", "oracle"):
                out = _tx(f"SELECT a FROM t WHERE {pred}", "postgresql", target)
                assert want in out, (pred, target, out)
                assert " IS 1" not in out and " IS 0" not in out, out
                assert_statements_parse(out, target, context=pred)

    def test_mysql_keeps_native_boolean(self) -> None:
        out = _tx("SELECT a FROM t WHERE flag IS TRUE", "postgresql", "mysql")
        assert "IS TRUE" in out, out


class TestAtAtIdentityGlobal:
    """red2-ts-at-identity-passthrough: T-SQL ``@@IDENTITY`` was shipped raw
    (PG 'column identity does not exist' / ORA-00936). Map it to the same
    'last generated id' expression SCOPE_IDENTITY() uses, symmetrically."""

    def test_at_identity_maps_like_scope_identity(self) -> None:
        src = _case("challenge_sqlserver.sql", "red2-ts-at-identity-passthrough")
        expect = {
            "postgresql": "LASTVAL()",
            "mysql": "LAST_INSERT_ID()",
            "oracle": "CURRVAL",
        }
        for target, idiom in expect.items():
            out = _exec_lines(_tx(src, "tsql", target))
            assert idiom in out, (target, out)
            assert "@@IDENTITY" not in out.upper(), out
            assert_statements_parse(out, target, context="at-identity")

    def test_tsql_target_keeps_at_identity(self) -> None:
        out = _tx("SELECT @@IDENTITY AS id", "tsql", "tsql")
        assert "@@IDENTITY" in out, out


class TestTryCastMysqlNull:
    """red2-ts-trycast-mysql-zero: TRY_CAST('abc' AS INT) is NULL on T-SQL but
    MySQL's plain CAST AS SIGNED returned 0 (the fold missed MySQL's SIGNED
    spelling of an INT target). A non-numeric literal must fold to NULL."""

    def test_nonnumeric_literal_folds_to_null_on_mysql(self) -> None:
        src = _case("challenge_sqlserver.sql", "red2-ts-trycast-mysql-zero")
        out = _exec_lines(_tx(src, "tsql", "mysql"))
        assert "NULL AS r" in out, out
        assert "SIGNED" not in out.upper(), out
        assert_statements_parse(out, "mysql", context="trycast")

    def test_numeric_literal_still_casts(self) -> None:
        out = _tx("SELECT TRY_CAST('123' AS INT) AS r", "tsql", "mysql")
        assert "CAST('123' AS SIGNED)" in out, out


class TestTryCastColumnNonliteral:
    """red3-ts-trycast-column-nonliteral + red3-ts-tryconvert-column-nonliteral
    (func): TRY_CAST/TRY_CONVERT over a COLUMN can't be folded, so the TRY
    (null-on-failure) semantics were dropped — MySQL returned 0, PG aborted the
    query. Wrap the numeric cast in a runtime guard so a bad row yields NULL.
    Live-verified (blue8 stack, c in ('abc','42')): PG/MySQL/Oracle all return
    (42, NULL), matching T-SQL. Oracle already had DEFAULT NULL ON CONVERSION
    ERROR."""

    def _assert_guarded(self, case: str) -> None:
        src = _case("challenge_sqlserver.sql", case)
        # MySQL: REGEXP guard on the string form, ELSE NULL.
        my = _exec_lines(_tx(src, "tsql", "mysql"))
        assert "REGEXP '^[+-]?[0-9]+$'" in my, my
        assert "ELSE NULL END" in my, my
        assert_statements_parse(my, "mysql", context=case)
        # PG: ``~`` regex guard on ::text, ELSE NULL — no bare CAST that aborts.
        pg = _exec_lines(_tx(src, "tsql", "postgresql"))
        assert "~ '^[+-]?[0-9]+$'" in pg, pg
        assert "ELSE NULL END" in pg, pg
        assert_statements_parse(pg, "postgresql", context=case)
        # Oracle keeps its native error-safe cast.
        ora = _exec_lines(_tx(src, "tsql", "oracle"))
        assert "DEFAULT NULL ON CONVERSION ERROR" in ora, ora

    def test_trycast_column_guarded(self) -> None:
        self._assert_guarded("red3-ts-trycast-column-nonliteral")

    def test_tryconvert_column_guarded(self) -> None:
        self._assert_guarded("red3-ts-tryconvert-column-nonliteral")

    def test_decimal_target_uses_general_numeric_pattern(self) -> None:
        # A DECIMAL target must accept decimal strings (the general pattern),
        # unlike the integer-only guard for an INT target.
        out = _tx("SELECT TRY_CAST(c AS DECIMAL(10,2)) AS r FROM t", "tsql", "mysql")
        assert "([0-9]+([.][0-9]*)?" in out, out
        assert "ELSE NULL END" in out, out

    def test_string_target_stays_plain_cast_no_warning(self) -> None:
        # A cast to a string type never fails, so TRY == plain CAST — no guard,
        # no (lying) warning about failure.
        r = Transpiler().transpile(
            "SELECT TRY_CAST(c AS VARCHAR(10)) AS r FROM t", "tsql", "postgresql"
        )
        assert "CASE WHEN" not in r.sql, r.sql
        assert "CAST(c AS VARCHAR(10))" in r.sql, r.sql
        assert r.warnings == [], r.warnings


class TestExecNamedParamMysql:
    """red2-ts-exec-named-param-mysql: T-SQL ``EXEC proc @p = v`` (named
    binding) became ``CALL proc(v_p = v)`` on MySQL — 1054 (no named-argument
    syntax). MySQL CALL is positional-only: drop the names to positional and
    warn; PG/Oracle keep the ``name => v`` form."""

    def test_mysql_call_is_positional_and_warns(self) -> None:
        src = _case("challenge_sqlserver.sql", "red2-ts-exec-named-param-mysql")
        r = Transpiler().transpile(src, "tsql", "mysql")
        out = _exec_lines(r.sql)
        assert "CALL get_rows(1, 0)" in out, out
        assert "=" not in out.split("get_rows", 1)[1].split(")", 1)[0], out
        assert any("no named arguments" in w.message for w in r.warnings), r.warnings

    def test_pg_and_oracle_keep_named_args(self) -> None:
        src = _case("challenge_sqlserver.sql", "red2-ts-exec-named-param-mysql")
        for target in ("postgresql", "oracle"):
            out = _exec_lines(_tx(src, "tsql", target))
            assert "=>" in out, (target, out)


class TestFkOnDeleteSetDefaultOracle:
    """red2-pg-fk-ondelete-setdefault-oracle: Oracle has no ON DELETE SET
    DEFAULT (ORA-03001). Drop the action (revert to NO ACTION) with a carrier +
    warning; PG/MySQL keep it."""

    def test_oracle_drops_action_and_warns(self) -> None:
        src = _case("challenge_postgresql.sql", "red2-pg-fk-ondelete-setdefault-oracle")
        r = Transpiler().transpile(src, "postgresql", "oracle")
        body = _exec_lines(r.sql)
        assert "SET DEFAULT" not in body.upper(), r.sql
        assert "REFERENCES p (id)" in body, r.sql
        assert any(
            "ON DELETE SET DEFAULT" in w.message and "Oracle" in w.message
            for w in r.warnings
        ), r.warnings
        assert "UNIQUE-1055:" in r.sql, r.sql
        assert_statements_parse(body, "oracle", context="fk-setdefault")

    def test_pg_and_mysql_keep_set_default(self) -> None:
        src = _case("challenge_postgresql.sql", "red2-pg-fk-ondelete-setdefault-oracle")
        for target in ("postgresql", "mysql"):
            out = _tx(src, "postgresql", target)
            assert "ON DELETE SET DEFAULT" in out.upper(), (target, out)


class TestDistinctOnQualifiedOrderBy:
    """red2-pg-distincton-qualified-orderby: the DISTINCT ON -> ROW_NUMBER
    rewrite left the outer ORDER BY referencing the source qualifier (``x.a``),
    out of scope at the wrapper (4104 / 1054 / ORA-00904). Re-point order keys
    to the wrapper's bare projected columns."""

    def test_qualified_order_keys_requalified(self) -> None:
        src = _case("challenge_postgresql.sql", "red2-pg-distincton-qualified-orderby")
        for target in ("tsql", "mysql", "oracle"):
            out = _exec_lines(_tx(src, "postgresql", target))
            order_clause = out.rsplit("ORDER BY", 1)[1]
            assert "x.a" not in order_clause and "x.b" not in order_clause, out
            assert "uq_rn = 1" in out, out
            assert_statements_parse(out, target, context="distincton")

    def test_unqualified_distinct_on_still_works(self) -> None:
        out = _tx(
            "SELECT DISTINCT ON (a) a, b FROM t ORDER BY a, b DESC",
            "postgresql",
            "tsql",
        )
        assert "uq_rn = 1" in out, out
        assert_statements_parse(out, "tsql", context="distincton-unqualified")


class TestOraclePlusOuterJoinDuplicate:
    """red2-ora-plus-outer-join-dup: with an ALIASED preserved table, sqlglot
    30.14's eliminate_join_marks re-adds it as a spurious CROSS JOIN (duplicate
    alias -> 'table name b specified more than once'). Dedup the bare repeat."""

    def test_multi_plus_predicate_no_duplicate_join(self) -> None:
        src = _case("challenge_oracle.sql", "red2-ora-plus-outer-join-dup")
        for target in ("postgresql", "tsql", "mysql"):
            out = _exec_lines(_tx(src, "oracle", target))
            assert out.count("tb b") == 1, out
            assert "CROSS JOIN" not in out.upper(), out
            assert "LEFT JOIN ta a" in out, out
            assert_statements_parse(out, target, context="plus-join")

    def test_single_aliased_plus_predicate_no_duplicate(self) -> None:
        out = _tx(
            "SELECT a.x, b.y FROM ta a, tb b WHERE a.id(+) = b.id",
            "oracle",
            "postgresql",
        )
        assert out.count("tb b") == 1, out
        assert_statements_parse(out, "postgresql", context="plus-single")


class TestWindowFrameExclude:
    """red2-pg-window-exclude-current: a frame EXCLUDE CURRENT ROW/GROUP/TIES
    was silently dropped, changing the aggregate. PG/Oracle support it (pass
    through); T-SQL/MySQL have no equivalent -> warned NULL carrier."""

    def test_oracle_and_pg_keep_exclude(self) -> None:
        src = _case("challenge_postgresql.sql", "red2-pg-window-exclude-current")
        for target in ("oracle", "postgresql"):
            out = _exec_lines(_tx(src, "postgresql", target))
            assert "EXCLUDE CURRENT ROW" in out, (target, out)
            assert_statements_parse(out, target, context="exclude")

    def test_tsql_mysql_warned_degrade(self) -> None:
        src = _case("challenge_postgresql.sql", "red2-pg-window-exclude-current")
        for target in ("tsql", "mysql"):
            r = Transpiler().transpile(src, "postgresql", target)
            body = _exec_lines(r.sql)
            # The window is not emitted at all — it degrades to a NULL carrier.
            assert "OVER (" not in body, r.sql
            assert "NULL /* UNIQUE-" in body, r.sql
            assert any(
                "EXCLUDE" in w.message and target in w.message for w in r.warnings
            ), r.warnings
            assert_statements_parse(body, target, context="exclude")


class TestDeleteOrderByLimitCap:
    """red2-my-delete-orderby-limit-drop (PRIORITY 1, data loss): MySQL
    ``DELETE … ORDER BY id LIMIT 5`` deletes only the first 5 by id, but the
    ORDER BY + LIMIT were dropped and the DELETE hit ALL matching rows. Each
    target renders the ordered cap via a keyed subquery."""

    def test_ordered_cap_rendered_per_target(self) -> None:
        src = _case("challenge_mysql.sql", "red2-my-delete-orderby-limit-drop")
        expect = {
            "mysql": "ORDER BY id",  # native
            "postgresql": "ctid IN",
            "tsql": "WITH uq_del",
            "oracle": "rowid IN",
        }
        for target, idiom in expect.items():
            out = _exec_lines(_tx(src, "mysql", target))
            assert idiom in out, (target, out)
            # the cap must survive on every target (no bare unbounded DELETE)
            assert "5" in out, out
            assert_statements_parse(out, target, context="delete-cap")

    def test_no_unread_args_warning(self) -> None:
        # The ORDER BY + LIMIT must be read (guardrail 7): no tripwire on them.
        src = _case("challenge_mysql.sql", "red2-my-delete-orderby-limit-drop")
        for target in ("postgresql", "tsql", "oracle", "mysql"):
            r = Transpiler().transpile(src, "mysql", target)
            assert not any(
                "unread sqlglot arg" in w.message and "Delete" in w.message
                for w in r.warnings
            ), (target, r.warnings)

    def test_unordered_cap_still_arbitrary(self) -> None:
        # A plain LIMIT (no ORDER BY) keeps the unordered cap idioms.
        out = _tx("DELETE FROM t WHERE v < 0 LIMIT 3", "mysql", "tsql")
        assert "DELETE TOP (3)" in out, out


class TestUpdateOrderByLimitCap:
    """red3-my-update-orderby-limit-drop + red3-my-update-limit-no-orderby (func,
    data loss): MySQL ``UPDATE … [ORDER BY id] LIMIT 5`` updates only the first 5
    rows, but the ORDER BY + LIMIT were dropped so the UPDATE hit ALL matching
    rows. The twin of the DELETE cap: each target renders the cap via a keyed
    subquery. Live-verified (blue8 stack, 10 rows v=-id): MySQL ORIGINAL updates
    5; PG/T-SQL/Oracle TRANSPILED each update exactly 5 (was 10)."""

    def test_ordered_cap_rendered_per_target(self) -> None:
        src = _case("challenge_mysql.sql", "red3-my-update-orderby-limit-drop")
        expect = {
            "mysql": "ORDER BY id",  # native ORDER BY + LIMIT
            "postgresql": "ctid IN",
            "tsql": "WITH uq_upd",
            "oracle": "rowid IN",
        }
        for target, idiom in expect.items():
            out = _exec_lines(_tx(src, "mysql", target))
            assert idiom in out, (target, out)
            # the cap must survive on every target (no bare unbounded UPDATE)
            assert "5" in out, out
            # the source ORDER BY must not have been dropped into a plain update
            assert "ORDER BY id" in out, (target, out)
            assert_statements_parse(out, target, context="update-cap")

    def test_no_unread_args_warning(self) -> None:
        # The ORDER BY + LIMIT must be read (guardrail 7): no tripwire on them.
        src = _case("challenge_mysql.sql", "red3-my-update-orderby-limit-drop")
        for target in ("postgresql", "tsql", "oracle", "mysql"):
            r = Transpiler().transpile(src, "mysql", target)
            assert not any(
                "unread sqlglot arg" in w.message and "Update" in w.message
                for w in r.warnings
            ), (target, r.warnings)

    def test_unordered_cap_bounds_every_target(self) -> None:
        src = _case("challenge_mysql.sql", "red3-my-update-limit-no-orderby")
        expect = {
            "mysql": "LIMIT 5",  # native
            "postgresql": "ctid IN",
            "tsql": "WITH uq_upd",
            "oracle": "ROWNUM <= 5",
        }
        for target, idiom in expect.items():
            out = _exec_lines(_tx(src, "mysql", target))
            assert idiom in out, (target, out)
            assert "5" in out, out
            assert_statements_parse(out, target, context="update-cap-noorder")

    def test_unordered_has_no_spurious_order_by(self) -> None:
        # A plain LIMIT (no ORDER BY) must not invent an ORDER BY on any target.
        src = _case("challenge_mysql.sql", "red3-my-update-limit-no-orderby")
        for target in ("postgresql", "tsql", "oracle", "mysql"):
            out = _exec_lines(_tx(src, "mysql", target))
            assert "ORDER BY" not in out.upper(), (target, out)


class TestInvisibleColumn:
    """red2-my-invisible-column-drop: a MySQL INVISIBLE column (excluded from
    SELECT *) had its attribute silently dropped. Oracle supports INVISIBLE
    (preserve); PG/T-SQL have no equivalent -> carrier + warning."""

    def test_oracle_and_mysql_keep_invisible(self) -> None:
        src = _case("challenge_mysql.sql", "red2-my-invisible-column-drop")
        for target in ("oracle", "mysql"):
            out = _exec_lines(_tx(src, "mysql", target))
            assert "INVISIBLE" in out, (target, out)
        # sqlglot cannot parse the (valid) Oracle INVISIBLE attribute — the
        # output gate whitelists it and it is live-validated — so only the
        # MySQL output is checked with the sqlglot parse gate here.
        assert_statements_parse(
            _exec_lines(_tx(src, "mysql", "mysql")), "mysql", context="invisible"
        )

    def test_pg_tsql_warn_and_drop(self) -> None:
        src = _case("challenge_mysql.sql", "red2-my-invisible-column-drop")
        for target in ("postgresql", "tsql"):
            r = Transpiler().transpile(src, "mysql", target)
            body = _exec_lines(r.sql)
            assert "INVISIBLE" not in body.split("UNIQUE-")[0].upper(), r.sql
            assert any(
                "INVISIBLE" in w.message and target in w.message for w in r.warnings
            ), r.warnings
            assert_statements_parse(body, target, context="invisible-drop")


class TestSetSwallowNext:
    """red2-ts-set-swallow-next: a degraded ``SET NOCOUNT ON; SELECT 1`` batch
    commented BOTH lines out, dropping the valid SELECT (no-silent-loss). Split
    the ;-separated statements so only the SET degrades and the SELECT
    transpiles — the neighbor of the EXEC-swallow split."""

    def test_set_degraded_but_following_select_survives(self) -> None:
        src = _case("challenge_sqlserver.sql", "red2-ts-set-swallow-next")
        for target in ("postgresql", "mysql", "oracle"):
            r = Transpiler().transpile(src, "tsql", target)
            body = _exec_lines(r.sql)
            # the SELECT is emitted as real SQL (not just commented away)
            assert "SELECT 1 AS a" in body, (target, r.sql)
            assert_statements_parse(body, target, context="set-swallow")
            assert any("SET option" in w.message for w in r.warnings), r.warnings

    def test_lone_set_still_whole_comment(self) -> None:
        # A SET with no following statement keeps the whole-comment behaviour.
        out = _tx("SET NOCOUNT ON", "tsql", "postgresql")
        assert out.strip() == "-- SET NOCOUNT ON", out


class TestRaiserrorFormatArgs:
    """red2-ts-raiserror-format-arg-drop: RAISERROR('value is %d today', 16, 1,
    42) dropped the substitution arg 42 silently on PG/Oracle. Splice it: PG
    RAISE format args (%), Oracle string concatenation."""

    def test_pg_uses_raise_format_arg(self) -> None:
        src = _case("challenge_sqlserver.sql", "red2-ts-raiserror-format-arg-drop")
        out = _exec_lines(_tx(src, "tsql", "postgresql"))
        assert "RAISE EXCEPTION 'value is % today', 42" in out, out
        assert "%d" not in out, out

    def test_oracle_concatenates_arg(self) -> None:
        src = _case("challenge_sqlserver.sql", "red2-ts-raiserror-format-arg-drop")
        out = _exec_lines(_tx(src, "tsql", "oracle"))
        assert "'value is ' || 42 || ' today'" in out, out
        assert "%d" not in out, out


class TestProcSavepointComposition:
    """red2-ora-proc-savepoint-as: SAVEPOINT is correct standalone but inside a
    routine emitted invalid ``SAVEPOINT AS sp1`` (embedded-DML mis-parse). Model
    it as a transaction statement: no spurious AS; T-SQL SAVE/ROLLBACK
    TRANSACTION sp1; PG has no plpgsql savepoints -> warned degrade."""

    def test_no_spurious_as_and_per_target_savepoint(self) -> None:
        src = _case("challenge_oracle.sql", "red2-ora-proc-savepoint-as")
        for target in ("mysql", "oracle"):
            out = _exec_lines(_tx(src, "oracle", target))
            assert "SAVEPOINT sp1" in out and "SAVEPOINT AS" not in out, (target, out)
            assert "ROLLBACK TO SAVEPOINT sp1" in out, (target, out)

    def test_tsql_uses_save_transaction(self) -> None:
        src = _case("challenge_oracle.sql", "red2-ora-proc-savepoint-as")
        out = _exec_lines(_tx(src, "oracle", "tsql"))
        assert "SAVE TRANSACTION sp1" in out, out
        assert "ROLLBACK TRANSACTION sp1" in out, out
        assert "SAVEPOINT AS" not in out, out

    def test_pg_degrades_savepoint_with_warning(self) -> None:
        src = _case("challenge_oracle.sql", "red2-ora-proc-savepoint-as")
        r = Transpiler().transpile(src, "oracle", "postgresql")
        body = _exec_lines(r.sql)
        assert "SAVEPOINT AS" not in body, r.sql
        assert "SAVEPOINT sp1 dropped" in body, r.sql
        assert any(
            "no explicit savepoints" in w.message for w in r.warnings
        ), r.warnings


class TestProcSetTransaction:
    """red3-ora-set-transaction-proc (invalid): ``SET TRANSACTION READ ONLY``
    inside a routine was mis-parsed as a variable assignment (``TRANSACTION :=
    READ ONLY`` / ``SET @transaction = READ ONLY`` — invalid, no warning). Model
    it as transaction control: native on Oracle/PG/MySQL; T-SQL has no READ
    ONLY mode -> carrier + warning. Live-validated on all four targets."""

    def test_pg_and_mysql_emit_native_set_transaction(self) -> None:
        src = _case("challenge_oracle.sql", "red3-ora-set-transaction-proc")
        for target in ("postgresql", "mysql"):
            out = _exec_lines(_tx(src, "oracle", target))
            assert "SET TRANSACTION READ ONLY" in out, (target, out)
            assert ":= READ ONLY" not in out, (target, out)
            assert "TRANSACTION = READ ONLY" not in out, (target, out)
            assert_statements_parse(out, target, context="set-transaction")

    def test_tsql_degrades_read_only_with_warning(self) -> None:
        src = _case("challenge_oracle.sql", "red3-ora-set-transaction-proc")
        r = Transpiler().transpile(src, "oracle", "tsql")
        body = _exec_lines(r.sql)
        # no invalid assignment; READ ONLY preserved as a carrier + warning
        assert "@transaction" not in body.lower(), r.sql
        assert "SET TRANSACTION READ ONLY dropped" in body, r.sql
        assert any(
            "no READ ONLY/READ WRITE transaction mode" in w.message for w in r.warnings
        ), r.warnings

    def test_tsql_keeps_isolation_level_natively(self) -> None:
        src = "CREATE OR REPLACE PROCEDURE p AS BEGIN "
        src += "SET TRANSACTION ISOLATION LEVEL SERIALIZABLE; NULL; END;"
        out = _exec_lines(_tx(src, "oracle", "tsql"))
        assert "SET TRANSACTION ISOLATION LEVEL SERIALIZABLE" in out, out


class TestProcGotoLabel:
    """red3-ts-goto-label-proc (invalid): a GOTO + label proc body was garbled
    (``GOTO AS done``, ``IF … GOTO done THEN``, bare ``done;``) behind a LYING
    'Embedded DML not modeled' warning. Model GOTO/label in both procedural
    parsers: Oracle/T-SQL native (GOTO/<<x>>/x:); PG/MySQL have no GOTO ->
    carrier + warning (MySQL pairs a DO 0 no-op so a block is never empty).
    Live-validated on all four targets."""

    def test_oracle_emits_native_goto_and_label(self) -> None:
        src = _case("challenge_sqlserver.sql", "red3-ts-goto-label-proc")
        out = _exec_lines(_tx(src, "tsql", "oracle"))
        assert "GOTO done;" in out, out
        assert "<<done>>" in out, out
        assert "GOTO AS" not in out, out

    def test_pg_and_mysql_degrade_with_warning_not_lying(self) -> None:
        src = _case("challenge_sqlserver.sql", "red3-ts-goto-label-proc")
        for target in ("postgresql", "mysql"):
            r = Transpiler().transpile(src, "tsql", target)
            body = _exec_lines(r.sql)
            assert "GOTO AS" not in body, (target, body)
            assert "GOTO done dropped" in body, (target, body)
            assert any("has no GOTO" in w.message for w in r.warnings), (
                target,
                r.warnings,
            )
            # the old lying 'Embedded DML not modeled' warning must be gone
            assert not any(
                "Embedded DML not modeled" in w.message for w in r.warnings
            ), (target, r.warnings)
            assert_statements_parse(body, target, context="goto")

    def test_oracle_source_label_neighbor_is_modeled(self) -> None:
        # The PL/SQL <<label>>/GOTO neighbor must be modeled too (same class).
        src = (
            "CREATE OR REPLACE PROCEDURE p AS i NUMBER := 0; BEGIN "
            "IF i = 0 THEN GOTO done; END IF; i := 1; <<done>> i := 2; END;"
        )
        out = _exec_lines(_tx(src, "oracle", "tsql"))
        assert "GOTO done;" in out and "done:" in out, out
        assert "GOTO AS" not in out and "<<" not in out, out


class TestFalseUnmapMappedSymmetrically:
    """RED round-2 asymmetric false-unmaps: constructs whose reverse direction
    already mapped were degrading (comment / validity-gate carrier) behind a
    false "no <engine> form" claim. Each is now wired symmetrically. Live-verified
    2026-07-30 on all four engines: 7 DIV 2 = 3, JSON_VALUE = '1', the sequence
    and materialized-view outputs run clean."""

    def test_intdiv_maps_per_engine(self) -> None:
        case = _case("challenge_mysql.sql", "red2-my-intdiv")
        for target, expected in (
            ("postgresql", "(7 / 2)"),
            ("tsql", "(7 / 2)"),
            ("oracle", "TRUNC(7 / 2)"),
        ):
            out = _tx(case, "mysql", target)
            assert expected in out, out
            body = _exec_lines(out)
            assert "DIV" not in body.upper(), body  # MySQL operator is gone
            assert "UNIQUE-" not in body, out

    def test_json_value_scalar_maps_per_engine(self) -> None:
        case = _case("challenge_sqlserver.sql", "red2-ts-json-value")
        for target in ("mysql", "oracle"):
            out = _tx(case, "tsql", target)
            assert "JSON_VALUE('{\"a\":1}', '$.a')" in out, out
            assert "UNIQUE-" not in _exec_lines(out), out
        pg = _tx(case, "tsql", "postgresql")
        assert "->> 'a'" in pg, pg
        assert "JSON_VALUE" not in _exec_lines(pg).upper(), pg

    def test_pg_nextval_maps_to_tsql_and_oracle(self) -> None:
        case = _case("challenge_postgresql.sql", "red2-pg-nextval")
        ts = _tx(case, "postgresql", "tsql")
        assert "NEXT VALUE FOR seq" in ts, ts
        o4 = _tx(case, "postgresql", "oracle")
        assert "seq.NEXTVAL" in o4, o4
        # MySQL genuinely has no sequences -> honest degrade with a warning.
        r = Transpiler().transpile(case, source="postgresql", target="mysql")
        assert r.warnings and "UNIQUE-1119:" in r.sql, r.sql

    def test_pg_materialized_view_native_on_oracle(self) -> None:
        case = _case("challenge_postgresql.sql", "red2-pg-matview")
        o4 = Transpiler().transpile(case, source="postgresql", target="oracle")
        assert "CREATE MATERIALIZED VIEW mv" in o4.sql, o4.sql
        assert not any(
            "not portable on oracle" in w.message for w in o4.warnings
        ), o4.warnings

    def test_mysql_dayofweek_maps_per_engine(self) -> None:
        # Sweep sibling (RED round-2 observation): MySQL DAYOFWEEK (Sun=1..7) was
        # falsely degraded though the reverse DATEPART(WEEKDAY)->DAYOFWEEK maps.
        src = "SELECT DAYOFWEEK(d) AS r FROM t"
        assert "EXTRACT(DOW FROM CAST(d AS DATE)) + 1" in _tx(
            src, "mysql", "postgresql"
        )
        assert "DATE '1970-01-04'" in _tx(src, "mysql", "oracle")
        assert "DATEPART(WEEKDAY, CAST(d AS DATE))" in _tx(src, "mysql", "tsql")
        for target in ("postgresql", "oracle", "tsql"):
            body = _exec_lines(_tx(src, "mysql", target))
            assert "DAYOFWEEK" not in body.upper(), body

    def test_pg_case_insensitive_regex_maps(self) -> None:
        # Sweep sibling: PG ``~*`` (RegexpILike) -> Oracle/MySQL REGEXP_LIKE 'i'.
        src = "SELECT a FROM t WHERE x ~* 'abc'"
        for target in ("oracle", "mysql"):
            out = _tx(src, "postgresql", target)
            assert "REGEXP_LIKE(x, 'abc', 'i')" in out, out
            assert "UNIQUE-" not in _exec_lines(out), out
        # T-SQL genuinely has no regex -> honest degrade with a warning.
        r = Transpiler().transpile(src, source="postgresql", target="tsql")
        assert r.warnings and "UNIQUE-1003:" in r.sql, r.sql


class TestTsqlLikeCharClassTranslated:
    """RED round-2 red2-ts-like-charclass: T-SQL ``LIKE '[A-C]%'`` uses a
    character-class range other engines match literally (result flips to 0).
    Translate to a portable predicate so the value holds — PG SIMILAR TO, MySQL/
    Oracle regex. Live-verified 2026-07-30: 'Bob' matches (=1) on all four."""

    def _out(self, target: str) -> str:
        return _tx(
            _case("challenge_sqlserver.sql", "red2-ts-like-charclass"), "tsql", target
        )

    def test_pg_similar_to(self) -> None:
        out = self._out("postgresql")
        assert "SIMILAR TO '[A-C]%'" in out, out
        assert "LIKE '[A-C]" not in _exec_lines(out), out

    def test_mysql_regexp(self) -> None:
        out = self._out("mysql")
        assert "REGEXP '^[A-C].*$'" in out, out
        assert "LIKE '[A-C]" not in _exec_lines(out), out

    def test_oracle_regexp_like(self) -> None:
        out = self._out("oracle")
        assert "REGEXP_LIKE('Bob', '^[A-C].*$')" in out, out
        assert "LIKE '[A-C]" not in _exec_lines(out), out


class TestMysqlCastUnsignedLenient:
    """RED round-2 red2-my-cast-unsigned-leniency: MySQL ``CAST('12x' AS
    UNSIGNED)`` = 12 (lenient leading-numeric parse); the previous
    CAST('12x' AS NUMERIC) errored on PG/T-SQL. Fold the literal to its MySQL
    value so the output runs. Live-verified 2026-07-30: value 12 on PG/T-SQL."""

    def test_leading_numeric_prefix_folded(self) -> None:
        for target in ("postgresql", "tsql"):
            out = _tx(
                _case("challenge_mysql.sql", "red2-my-cast-unsigned"), "mysql", target
            )
            assert "CAST(12 AS NUMERIC)" in out, out
            assert "'12x'" not in _exec_lines(out), out


class TestDateAddDiffUnits:
    """RED round-2 date-unit fixes (DATEADD/DATEDIFF unit space).

    * red2-ts-datediff-weekday-unit: T-SQL DATEDIFF(WEEKDAY,..) counts day
      boundaries exactly like DAY (it is not day-of-week) — mapped to DAY, was a
      3-arg passthrough that shipped invalid. Live-verified value 60 on all four.
    * red2-my-dateadd-compound-interval: MySQL INTERVAL '1:30' HOUR_MINUTE has no
      single-count form; expanded into chained per-unit adds. Live-verified value
      2021-06-15 09:30:00 on all four.
    An unmapped unit now degrades to a warned NULL carrier (non-T-SQL), never an
    invalid silent passthrough.
    """

    def test_datediff_weekday_is_day(self) -> None:
        case = _case("challenge_sqlserver.sql", "red2-ts-datediff-weekday-unit")
        assert "DATEDIFF('2020-03-01', '2020-01-01')" in _tx(case, "tsql", "mysql")
        assert "DATEDIFF(DAY, '2020-01-01', '2020-03-01')" in _tx(case, "tsql", "tsql")
        for target in ("mysql", "oracle", "postgresql"):
            body = _exec_lines(_tx(case, "tsql", target))
            assert "WEEKDAY" not in body.upper(), body

    def test_compound_interval_expanded(self) -> None:
        case = _case("challenge_mysql.sql", "red2-my-dateadd-compound-interval")
        assert "INTERVAL '1 HOUR' + INTERVAL '30 MINUTE'" in _tx(
            case, "mysql", "postgresql"
        )
        assert "DATEADD(MINUTE, 30, DATEADD(HOUR, 1," in _tx(case, "mysql", "tsql")
        assert "NUMTODSINTERVAL(1, 'HOUR') + NUMTODSINTERVAL(30, 'MINUTE')" in _tx(
            case, "mysql", "oracle"
        )
        for target in ("postgresql", "tsql", "oracle"):
            body = _exec_lines(_tx(case, "mysql", target))
            assert "HOUR_MINUTE" not in body.upper(), body

    def test_unmapped_diff_unit_degrades_not_invalid(self) -> None:
        # A unit with no cross-engine form -> warned NULL carrier off T-SQL, valid
        # native DATEDIFF on T-SQL (a real datepart) — never invalid + silent.
        src = "SELECT DATEDIFF(NANOSECOND, '2020-01-01', '2020-03-01') AS d"
        for target in ("mysql", "oracle", "postgresql"):
            r = Transpiler().transpile(src, source="tsql", target=target)
            assert r.warnings and "UNIQUE-1079:" in r.sql, r.sql
            assert "NANOSECOND" in r.sql, r.sql  # unit named for review
        assert "DATEDIFF(NANOSECOND" in _tx(src, "tsql", "tsql")


class TestExtractUnitSpace:
    """RED round-2 EXTRACT/DATEPART unit space.

    * red2-pg-extract-isoyear-unit: PG EXTRACT(ISOYEAR) computed per target as
      the year of the ISO week's Thursday. Live-verified value 2020 on all four.
    * red2-ts-datepart-week-iso: T-SQL DATEPART(WEEK) is the NON-ISO,
      DATEFIRST-based week (was mapped to the ISO week functions, value 53 vs 1);
      mapped to each engine's non-ISO week formula. DATEPART(ISO_WEEK) keeps the
      ISO functions. Live-verified value 1 for 2021-01-01 on all four.
    """

    def test_isoyear_maps_per_engine(self) -> None:
        case = _case("challenge_postgresql.sql", "red2-pg-extract-isoyear")
        assert "EXTRACT(YEAR FROM (TRUNC(DATE '2020-03-15', 'IW') + 3))" in _tx(
            case, "postgresql", "oracle"
        )
        assert "DATEDIFF(DAY, '19000101'" in _tx(case, "postgresql", "tsql")
        for target in ("tsql", "mysql", "oracle"):
            body = _exec_lines(_tx(case, "postgresql", target))
            assert "ISOYEAR" not in body.upper(), body  # unit is gone

    def test_datepart_week_is_noniso(self) -> None:
        case = _case("challenge_sqlserver.sql", "red2-ts-datepart-week-iso")
        # non-ISO formula, NOT the ISO week functions
        my = _tx(case, "tsql", "mysql")
        assert "DAYOFWEEK(MAKEDATE(YEAR(" in my, my
        assert "WEEK('2021-01-01', 3)" not in my, my  # ISO form must be gone
        pg = _tx(case, "tsql", "postgresql")
        assert "EXTRACT(DOY FROM DATE '2021-01-01')" in pg, pg
        o4 = _tx(case, "tsql", "oracle")
        assert "TO_CHAR(DATE '2021-01-01', 'DDD')" in o4, o4

    def test_datepart_iso_week_stays_iso(self) -> None:
        # Neighbor: DATEPART(ISO_WEEK) must keep the ISO week functions.
        src = "SELECT DATEPART(ISO_WEEK, '2021-01-01') AS w"
        assert "WEEK('2021-01-01', 3)" in _tx(src, "tsql", "mysql")
        assert "TO_CHAR('2021-01-01', 'IW')" in _tx(src, "tsql", "oracle")


class TestOracleTruncRoundFormatModels:
    """RED round-2 Oracle TRUNC/ROUND date-format models.

    * red2-ora-trunc-day-weekstart: TRUNC(d,'DAY') is the START OF THE (Sunday)
      WEEK, not day truncation ('DD'); mapped to a Sunday week-start per target.
      Live-verified 2021-06-13 on PG/T-SQL/MySQL.
    * red2-ora-trunc-format-unmapped: 'IW' (ISO week) maps to the ISO-week
      truncation; 'W' (week-of-month, no portable form) degrades to a warned
      carrier off Oracle; MySQL hour/minute now truncate instead of shipping an
      invalid DATE_TRUNC. Live-verified 'IW' = 2021-06-14.
    * red2-ora-round-date-fmt: ROUND(date, fmt) is date rounding, not numeric —
      kept native on Oracle, degrades to a warned carrier off Oracle (was invalid
      ROUND(CAST(date AS NUMERIC), ...)).
    """

    def test_trunc_day_is_week_start(self) -> None:
        case = _case("challenge_oracle.sql", "red2-ora-trunc-day-weekstart")
        pg = _tx(case, "oracle", "postgresql")
        assert "EXTRACT(DOW FROM DATE '2021-06-15')" in pg, pg
        assert (
            "DATE_TRUNC('day', DATE '2021-06-15') AS d" not in pg
        ), pg  # not plain day
        assert "DATEDIFF(DAY, '19000107'" in _tx(case, "oracle", "tsql")
        assert "DAYOFWEEK(DATE(" in _tx(case, "oracle", "mysql")

    def test_trunc_dd_stays_day(self) -> None:
        # Neighbor: 'DD' is genuine day truncation and must be unaffected.
        src = "SELECT TRUNC(DATE '2021-06-15', 'DD') AS d FROM dual"
        assert "DATE_TRUNC('day', DATE '2021-06-15')" in _tx(
            src, "oracle", "postgresql"
        )
        assert "DATE(CAST" in _tx(src, "oracle", "mysql")

    def test_trunc_week_of_month_degrades(self) -> None:
        case = _case("challenge_oracle.sql", "red2-ora-trunc-format-unmapped")
        for target in ("postgresql", "tsql", "mysql"):
            r = Transpiler().transpile(case, source="oracle", target=target)
            assert r.warnings and "UNIQUE-1085:" in r.sql, r.sql
            body = _exec_lines(r.sql)
            assert "DATE_TRUNC(W" not in body and "DATE_TRUNC('W'" not in body, body

    def test_trunc_iso_week_maps(self) -> None:
        src = "SELECT TRUNC(DATE '2021-06-15', 'IW') AS d FROM dual"
        assert "DATE_TRUNC('week', DATE '2021-06-15')" in _tx(
            src, "oracle", "postgresql"
        )
        assert "DATETRUNC(ISO_WEEK," in _tx(src, "oracle", "tsql")

    def test_round_date_degrades_off_oracle(self) -> None:
        case = _case("challenge_oracle.sql", "red2-ora-round-date-fmt")
        for target in ("postgresql", "tsql", "mysql"):
            r = Transpiler().transpile(case, source="oracle", target=target)
            assert r.warnings and "UNIQUE-1084:" in r.sql, r.sql
            body = _exec_lines(r.sql)
            assert "AS NUMERIC" not in body.upper(), body  # not the numeric round
            assert "NULL" in body, body
