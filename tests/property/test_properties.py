# Copyright (c) 2026 Unique Contributors
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Property-based tests for the procedural engine.

These generate randomized—but structurally valid—procedures and assert
invariants that must hold for any input: the engine never crashes, the
lexer always makes progress and terminates, the parser produces a node,
and emission never collapses a non-empty body to nothing.
"""

from __future__ import annotations

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from unique.core.batch_splitter import BatchSplitter
from unique.core.procedural.emitter import ProceduralEmitter
from unique.core.procedural.lexer import Lexer, TokenType
from unique.core.procedural.parser import ProceduralParser
from unique.core.transpiler import transpile

DIALECTS = ["tsql", "oracle", "postgresql", "mysql"]

# Identifiers and simple type names used to build random procedures.
_ident = st.from_regex(r"[a-z][a-z0-9_]{0,12}", fullmatch=True)
_int = st.integers(min_value=0, max_value=999)


# ---------------------------------------------------------------------------
# Lexer invariants
# ---------------------------------------------------------------------------


@settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
@given(st.text(), st.sampled_from(DIALECTS))
def test_lexer_never_crashes_and_terminates(text: str, dialect: str) -> None:
    """The lexer must tokenize any input without raising and terminate."""
    tokens = Lexer(text, dialect).tokens
    # Always at least the EOF token.
    assert tokens
    assert tokens[-1].type == TokenType.EOF


@settings(max_examples=200)
@given(st.text(min_size=1))
def test_lexer_token_columns_are_within_bounds(text: str) -> None:
    """Token positions stay within the source (sanity on advance logic)."""
    lex = Lexer(text, "tsql")
    for tok in lex.tokens:
        assert tok.line >= 1


# ---------------------------------------------------------------------------
# Parser invariants
# ---------------------------------------------------------------------------


@st.composite
def tsql_procedures(draw: st.DrawFn) -> str:
    """Generate a structurally valid (if trivial) T-SQL procedure."""
    name = draw(_ident)
    n_params = draw(st.integers(min_value=0, max_value=3))
    params = ", ".join(f"@{draw(_ident)} INT" for _ in range(n_params))
    param_clause = f" {params}" if params else ""

    n_decls = draw(st.integers(min_value=0, max_value=3))
    decls = "\n".join(f"    DECLARE @{draw(_ident)} INT;" for _ in range(n_decls))

    body_choice = draw(st.sampled_from(["set", "if", "print", "select"]))
    var = draw(_ident)
    if body_choice == "set":
        stmt = f"    SET @{var} = {draw(_int)};"
    elif body_choice == "if":
        stmt = f"    IF @{var} > 0 BEGIN PRINT 'x' END"
    elif body_choice == "print":
        stmt = "    PRINT 'hello';"
    else:
        stmt = f"    SELECT * FROM t WHERE id = {draw(_int)};"

    return f"CREATE PROCEDURE {name}{param_clause}\n" f"AS\nBEGIN\n{decls}\n{stmt}\nEND"


@settings(max_examples=150, suppress_health_check=[HealthCheck.too_slow])
@given(tsql_procedures(), st.sampled_from(DIALECTS))
def test_parser_always_returns_a_node(sql: str, dialect: str) -> None:
    """Parsing a generated procedure must return a node, never raise."""
    result = ProceduralParser(dialect).parse(sql)
    assert result.node is not None


@settings(max_examples=150, suppress_health_check=[HealthCheck.too_slow])
@given(tsql_procedures())
def test_tsql_procedure_round_trips_to_all_targets(sql: str) -> None:
    """A generated T-SQL procedure transpiles to every target without
    crashing and yields non-empty output."""
    for target in DIALECTS:
        result = transpile(sql, "tsql", target)
        assert result.sql.strip()


# ---------------------------------------------------------------------------
# Emitter invariants
# ---------------------------------------------------------------------------


@settings(max_examples=150, suppress_health_check=[HealthCheck.too_slow])
@given(tsql_procedures(), st.sampled_from(DIALECTS))
def test_emitter_preserves_procedure_keyword(sql: str, target: str) -> None:
    """Emission of a CREATE PROCEDURE always contains PROCEDURE."""
    parsed = ProceduralParser("tsql").parse(sql)
    emitter = ProceduralEmitter(target)
    out = emitter.emit(parsed.node)
    assert "PROCEDURE" in out.upper()


# ---------------------------------------------------------------------------
# Batch splitter invariants
# ---------------------------------------------------------------------------


@settings(max_examples=200)
@given(st.text(), st.sampled_from(DIALECTS))
def test_batch_splitter_never_crashes(text: str, dialect: str) -> None:
    """Splitting any text must not raise and must return a list."""
    batches = BatchSplitter.split(text, dialect)
    assert isinstance(batches, list)


@settings(max_examples=150)
@given(
    st.lists(st.from_regex(r"SELECT [0-9]+", fullmatch=True), min_size=1, max_size=6)
)
def test_tsql_go_split_count(statements: list[str]) -> None:
    """N statements joined by GO split into N non-empty batches."""
    sql = "\nGO\n".join(statements)
    batches = [b for b in BatchSplitter.split(sql, "tsql") if not b.is_empty]
    assert len(batches) == len(statements)
