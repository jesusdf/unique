# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Nightly differential *execution* over curated challenge func-class cases.

The parse-only challenge gate (``test_challenge.py``) proves the transpiled
output *parses*; this proves it returns the *same answer*. For each curated
``FUNC_CASES`` entry — and any ``[fixed]`` case whose header carries
``[class=func]`` — it executes the source SQL on its source engine and the
transpiled output on each target engine, then compares normalized result sets.
That is the same semantic gate ``test_corpus_results_live.py`` runs over the
SQL corpus, reusing its ``normalize_rows`` result-diff machinery (order- and
precision-insensitive, so DATE-vs-DATETIME rendering and default row order are
not false mismatches).

Skipped per case unless BOTH engines' ``UNIQUE_TEST_*_URL`` env vars are set,
so the default offline suite stays green; it runs in the nightly
``challenge-live`` workflow against the four live containers.
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass

import pytest

from tests.functional_equivalence.engine_runner import connect, split_statements
from tests.helpers.corpus import targets_for
from tests.helpers.corpus_diff import normalize_rows, urls_from_env
from tests.integration.test_challenge import _SOURCE_BY_FILE, _cases, _slug, _status
from unique.core.transpiler import transpile


@dataclass(frozen=True)
class FuncCase:
    """A challenge case whose transpiled output must return the same result set.

    ``slug`` is matched (case-insensitively) against the case header, exactly
    like ``test_challenge._case``. For a self-contained ``SELECT`` case the
    block *is* the observable query, so ``probe`` stays ``None``. For a case
    that mutates state (an upsert, a MERGE) the block is run for effect and
    ``probe`` — a portable ``SELECT`` valid on every engine — observes the final
    state; ``tables`` names the objects the block creates so they are dropped
    before and after on each engine (DDL auto-commits on MySQL/Oracle).
    """

    fixture: str
    source: str
    slug: str
    probe: str | None = None
    tables: tuple[str, ...] = ()


# ~10 high-value semantic cases hand-picked from the corpus and live-verified to
# return an *exactly* equal result set on every engine pair (2026-07-25). Each
# targets a silent-wrong-answer class the parse gate cannot see:
#
#   integer-vs-decimal division  — ora-div / my-div / my-sum-div-count: a '/'
#     over two ints truncates on PG/T-SQL but is decimal on Oracle/MySQL; the
#     converter forces '* 1.0' to preserve the value (2.5 / 1.5). Aggregate
#     SUM()/COUNT() is a distinct code path, hence its own case.
#   numeric-string arithmetic    — ora-implicit-arith / ts-str-plus-num: '1' + 1
#     is arithmetic (=2/=15), NOT concat; the guardrail-2 text-rewrite bug
#     turned exactly this '+' into '||' and corrupted the value silently.
#   concat vs NULL semantics     — ora-concat-num ('a' || 5 = 'a5'),
#     ora-concat-null ('a'||NULL||'b' = 'ab', Oracle treats NULL as ''),
#     ts-concat-null (CONCAT skips NULL = 'ab'): each returned a different
#     string ('NULL', dropped operand) before the fix.
#   numeric concat              — ora-num-concat (2 || 3 = '23'): PG has no
#     integer||integer operator, so the all-numeric || needs TEXT casts;
#     T-SQL/MySQL fold to CONCAT(). Emitted bare (invalid) on PG before the fix.
#   safe cast                    — ora-cast-onerror: CAST(... ON CONVERSION
#     ERROR) folds to the default (-1) on the engines without a native form.
#   upsert                       — pg-insert-select-conflict: ON CONFLICT DO
#     NOTHING keeps the pre-seeded row (id=1,n=10) instead of overwriting it —
#     the exact clause that used to be dropped, shipping a plain INSERT.
#   MERGE fold                   — ts-merge-full: the full conditional MERGE
#     (UPDATE/DELETE/INSERT + NOT MATCHED BY SOURCE) must leave the same rows
#     in tgt on every engine after its multi-statement lowering.
#   TRY_CAST/TRY_CONVERT column  — red3-ts-trycast-column-nonliteral /
#     red3-ts-tryconvert-column-nonliteral: a non-literal (column) safe cast
#     over a non-numeric value must yield NULL, not 0 (MySQL) or an aborted
#     query (PG).
#   window EXCLUDE               — red2-pg-window-exclude-current: EXCLUDE
#     CURRENT ROW must not be silently dropped from the frame; Oracle passes
#     it through natively (matches), T-SQL/MySQL correctly warn+degrade.
#   UPDATE ORDER BY/LIMIT cap    — red3-my-update-orderby-limit-drop /
#     red3-my-update-limit-no-orderby: MySQL's row cap must survive as a
#     keyed-subquery UPDATE on every target, not silently update every row.
#
# ROW_COUNT / LAST_INSERT_ID / session functions are deliberately excluded: they
# return engine- and session-specific values, so they are not result-comparable
# across engines. Cases with an approved precision-only or boundary divergence
# (ora-div-precision, my-timestampdiff-year) are excluded for the same reason —
# a strict result-diff would (correctly) flag them, but they are documented
# limits, not regressions.
FUNC_CASES: tuple[FuncCase, ...] = (
    FuncCase("challenge_oracle.sql", "oracle", "ora-div "),
    FuncCase("challenge_mysql.sql", "mysql", "my-div "),
    FuncCase("challenge_mysql.sql", "mysql", "my-sum-div-count "),
    FuncCase("challenge_oracle.sql", "oracle", "ora-implicit-arith "),
    FuncCase("challenge_sqlserver.sql", "tsql", "ts-str-plus-num "),
    FuncCase("challenge_oracle.sql", "oracle", "ora-num-concat "),
    FuncCase("challenge_oracle.sql", "oracle", "ora-concat-num "),
    FuncCase("challenge_oracle.sql", "oracle", "ora-concat-null "),
    FuncCase("challenge_sqlserver.sql", "tsql", "ts-concat-null "),
    FuncCase("challenge_oracle.sql", "oracle", "ora-cast-onerror "),
    FuncCase(
        "challenge_postgresql.sql",
        "postgresql",
        "pg-insert-select-conflict ",
        probe="SELECT id, n FROM t ORDER BY id, n",
        tables=("t",),
    ),
    FuncCase(
        "challenge_sqlserver.sql",
        "tsql",
        "ts-merge-full ",
        probe="SELECT id, n FROM tgt ORDER BY id, n",
        tables=("tgt", "src"),
    ),
    FuncCase(
        "challenge_sqlserver.sql",
        "tsql",
        "red3-ts-trycast-column-nonliteral ",
        tables=("t",),
    ),
    FuncCase(
        "challenge_sqlserver.sql",
        "tsql",
        "red3-ts-tryconvert-column-nonliteral ",
        tables=("t",),
    ),
    FuncCase(
        "challenge_postgresql.sql",
        "postgresql",
        "red2-pg-window-exclude-current ",
        tables=("t",),
    ),
    FuncCase(
        "challenge_mysql.sql",
        "mysql",
        "red3-my-update-orderby-limit-drop ",
        probe="SELECT id, v FROM t ORDER BY id",
        tables=("t",),
    ),
    FuncCase(
        "challenge_mysql.sql",
        "mysql",
        "red3-my-update-limit-no-orderby ",
        probe="SELECT id, v FROM t ORDER BY id",
        tables=("t",),
    ),
)


def _locate(case: FuncCase) -> str:
    """Return the ``[fixed]`` case block for *case* (KeyError if missing)."""
    for block in _cases(case.fixture):
        if case.slug.lower() in block.splitlines()[0].lower():
            assert _status(block) == "fixed", f"{case.slug!r} is not [fixed]"
            return block
    raise KeyError(f"no case matching {case.slug!r} in {case.fixture}")


def _source_sql(block: str) -> str:
    """The executable SQL of a case block (its ``--`` header/comment stripped)."""
    return "\n".join(
        ln for ln in block.splitlines() if not ln.lstrip().startswith("--")
    ).strip()


def _func_class_cases() -> list[FuncCase]:
    """Auto-discover ``[fixed]`` cases tagged ``[class=func]`` not already curated.

    None carry a ``[class=func]`` tag today; this keeps the nightly gate honest
    as the corpus adopts the class marker (an auto entry is treated as a
    self-contained SELECT — a func-class case that mutates state needs a curated
    ``FuncCase`` with a probe)."""
    curated = {(c.fixture, c.slug.strip()) for c in FUNC_CASES}
    extra: list[FuncCase] = []
    for fixture, source in _SOURCE_BY_FILE.items():
        for block in _cases(fixture):
            head = block.splitlines()[0]
            if _status(block) == "fixed" and "[class=func]" in head:
                slug = _slug(block)
                if (fixture, slug) not in curated:
                    extra.append(FuncCase(fixture, source, slug))
    return extra


_PARAMS = [
    (case, target)
    for case in (*FUNC_CASES, *_func_class_cases())
    for target in targets_for(case.source)
]


def _drop(conn: object, tables: tuple[str, ...]) -> None:
    if not tables:
        return
    cur = conn.cursor()  # type: ignore[attr-defined]
    for table in tables:
        try:
            cur.execute(f"DROP TABLE IF EXISTS {table}")
            conn.commit()  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001 - a stale leftover; roll back and retry after
            with contextlib.suppress(Exception):
                conn.rollback()  # type: ignore[attr-defined]


def _execute(
    engine: str,
    url: str,
    sql: str,
    probe: str | None,
    tables: tuple[str, ...],
    *,
    empty_as_null: bool = False,
) -> list[tuple]:
    """Run *sql* on *engine*, returning the normalized rows to compare.

    Without a probe the last statement's result set is captured (a SELECT case);
    with one, the block is run for effect and the probe observes the final state.
    ``tables`` are dropped before (clear leftovers) and after (DDL auto-commits
    on MySQL/Oracle, so a transaction rollback cannot undo it)."""
    conn = connect(engine, url)
    try:
        _drop(conn, tables)
        cur = conn.cursor()
        rows: list[tuple] | None = None
        for stmt in split_statements(sql, engine):
            if not stmt.strip():
                continue
            cur.execute(stmt)
            with contextlib.suppress(Exception):  # a DML/DDL stmt has no result set
                rows = cur.fetchall()
        if probe:
            cur.execute(probe)
            rows = cur.fetchall()
        with contextlib.suppress(Exception):
            conn.commit()
        return normalize_rows(rows or [], empty_as_null=empty_as_null)
    finally:
        _drop(conn, tables)
        conn.close()


@pytest.mark.integration
@pytest.mark.parametrize(
    "case,target",
    _PARAMS,
    ids=[f"{c.slug.strip()}[{c.source}->{t}]" for c, t in _PARAMS],
)
def test_func_case_result_matches(case: FuncCase, target: str) -> None:
    """The transpiled output must return the SAME result set as the source."""
    urls = urls_from_env()
    if case.source not in urls or target not in urls:
        pytest.skip(f"needs live URLs for {case.source} and {target}")

    sql = _source_sql(_locate(case))
    result = transpile(sql, case.source, target)
    if result.warnings:
        # A documented degrade (carrier + warning) is not result-comparable —
        # the same reason the curated precision/boundary limits are excluded. A
        # construct with no faithful cross-engine form (e.g. an Oracle
        # partition-extended reference) preserves itself as a comment, so there
        # is no executable output to diff.
        pytest.skip(f"{case.slug.strip()} -> {target}: documented degrade")
    # Oracle folds '' into NULL intrinsically — when either side of the pair is
    # Oracle the two values are indistinguishable there, so BOTH sides collapse
    # '' to NULL before comparing (maintainer decision 2026-07-30).
    fold = "oracle" in (case.source, target)
    source_rows = _execute(
        case.source, urls[case.source], sql, case.probe, case.tables, empty_as_null=fold
    )
    output = result.sql
    target_rows = _execute(
        target, urls[target], output, case.probe, case.tables, empty_as_null=fold
    )

    assert source_rows == target_rows, (
        f"{case.slug.strip()} {case.source} -> {target}: transpiled output "
        f"executed but returned a different result set — a semantic bug.\n"
        f"  source: {source_rows}\n"
        f"  target: {target_rows}\n"
        f"  output: {output!r}"
    )
