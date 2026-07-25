"""Shared output-validity helpers (audit 2026-07-02, test hardening).

``assert_parses`` runs every transpiled output through sqlglot in the
*target* dialect — a millisecond, database-free gate that kills the worst
class of bugs (stripped identifier quoting, JOINs without ON, missing
INTERVAL keywords, leaked internal pseudo-functions).

``assert_translated`` enforces the assertion pattern that makes a
conversion test real: the target idiom must be present AND the source
idiom must be gone. Tests written this way fail under an identity
transpiler; keyword-presence-only tests do not (72% of the integration
suite survived that mutation in v0.7.0).
"""

from __future__ import annotations

import re

import sqlglot

SQLGLOT_DIALECT = {
    "tsql": "tsql",
    "oracle": "oracle",
    "postgresql": "postgres",
    "mysql": "mysql",
}

#: Tokens that are syntactically invalid on the named target but which
#: sqlglot's lenient reader accepts (or silently rewrites), so the parse gate
#: alone would pass them. Checked (word-boundary, case-insensitive) against the
#: comment-stripped statement AFTER a successful parse; a hit fails the gate
#: even though sqlglot parsed. Seeded from real leniency holes the challenge
#: sweep found — grow it whenever an engine rejects a token sqlglot waves
#: through.
KNOWN_INVALID_TOKENS: dict[str, tuple[str, ...]] = {
    # Oracle TIMESTAMP WITH LOCAL TIME ZONE is sqlglot's TIMESTAMPLTZ; its
    # postgres/tsql readers echo the raw token and its mysql reader rewrites it
    # to TIMESTAMP, but no real engine spells the type (the emitter maps it to
    # timestamptz / DATETIMEOFFSET / TIMESTAMP).
    "postgresql": ("TIMESTAMPLTZ",),
    "tsql": ("TIMESTAMPLTZ",),
    "mysql": ("TIMESTAMPLTZ",),
}


def _known_invalid_token(body: str, target: str) -> str | None:
    """Return the first :data:`KNOWN_INVALID_TOKENS` token present in *body*
    (comment-stripped, word-boundary, case-insensitive), or ``None``."""
    text = executable_body(body).upper()
    for tok in KNOWN_INVALID_TOKENS.get(target, ()):
        if re.search(rf"\b{re.escape(tok)}\b", text):
            return tok
    return None


def executable_lines(sql: str) -> str:
    """Return only the executable (non-comment) lines of *sql*."""
    return "\n".join(
        line for line in sql.splitlines() if not line.lstrip().startswith("--")
    )


def executable_body(sql: str) -> str:
    """Executable text of *sql*: block comments and ``--`` lines removed."""
    return executable_lines(re.sub(r"/\*.*?\*/", "", sql, flags=re.DOTALL))


def assert_statements_parse(sql_out: str, target: str, *, context: str = "") -> None:
    """Procedural-aware output validity over a whole transpiled script.

    Splits *sql_out* with the functional-equivalence harness splitter (GO /
    ``;`` / Oracle ``/`` / MySQL DELIMITER, keeping routine bodies intact),
    classifies each statement, and sqlglot-parses every non-procedural one in
    the *target* dialect. Procedural bodies are exempt (sqlglot cannot parse
    PL/SQL / T-SQL blocks); they are covered by the procedural suite and the
    live-syntax CI job.
    """
    from tests.functional_equivalence.engine_runner import split_statements
    from unique.core.batch_splitter import BatchType, classify_batch

    failures: list[str] = []
    for stmt in split_statements(sql_out, target):
        body = executable_lines(stmt).strip()
        if not body:
            continue
        if classify_batch(body, target) in (
            BatchType.PROCEDURAL,
            BatchType.COMMENT,
            BatchType.EMPTY,
            BatchType.SET_OPTION,
        ):
            continue
        try:
            sqlglot.parse(
                body,
                read=SQLGLOT_DIALECT[target],
                error_level=sqlglot.ErrorLevel.RAISE,
            )
        except Exception as exc:  # noqa: BLE001 - collect with the statement
            failures.append(f"{type(exc).__name__}: {exc}\n  stmt: {body[:300]}")
            continue
        bad = _known_invalid_token(stmt, target)
        if bad is not None:
            failures.append(
                f"KnownInvalidToken: {bad!r} parses as {target} but no real "
                f"engine accepts the token\n  stmt: {body[:300]}"
            )
    assert not failures, (
        f"{context or 'output'}: {len(failures)} transpiled statement(s) do not "
        f"parse as {target}:\n" + "\n".join(failures[:5])
    )


def assert_parses(sql: str, dialect: str) -> None:
    """Assert *sql* parses in *dialect*. Comment-only output is fine."""
    body = executable_lines(sql).strip()
    if not body:
        return
    try:
        sqlglot.parse(
            body,
            read=SQLGLOT_DIALECT[dialect],
            error_level=sqlglot.ErrorLevel.RAISE,
        )
    except Exception as exc:  # noqa: BLE001 - re-raise with the SQL attached
        raise AssertionError(
            f"output does not parse as {dialect}: {exc}\n--- output ---\n{sql}"
        ) from exc
    bad = _known_invalid_token(sql, dialect)
    if bad is not None:
        raise AssertionError(
            f"output parses as {dialect} but contains {bad!r}, a token no real "
            f"{dialect} engine accepts:\n--- output ---\n{sql}"
        )


def assert_translated(
    sql: str,
    target: str,
    *,
    present: tuple[str, ...] = (),
    absent: tuple[str, ...] = (),
    validate: bool = True,
) -> None:
    """Assert target idioms appeared and source idioms are gone.

    ``absent`` is checked against executable lines only, so a carrier
    comment quoting the original construct doesn't trip it.
    """
    if validate:
        assert_parses(sql, target)
    for needle in present:
        assert needle in sql, f"expected {needle!r} in output:\n{sql}"
    body = executable_lines(sql).upper()
    for needle in absent:
        assert (
            needle.upper() not in body
        ), f"source idiom {needle!r} survived translation:\n{sql}"
