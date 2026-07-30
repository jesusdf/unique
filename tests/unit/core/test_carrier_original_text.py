"""Degrade carriers must preserve the ORIGINAL statement (audit 2026-07-24 N12).

A ``-- UNIQUE: … Statement preserved as a comment`` carrier claims to hold the
user's statement verbatim so they can rewrite it by hand. It used to re-render
the half-transformed IR in the source dialect (``emit_node(node, source)``),
which applies the emitter's function/type mappings and yields a mid-transform
hybrid no engine accepts (``dbo.JSON_EXTRACT``, converted accessor pairs). The
parser now attaches the ORIGINAL statement text to each converted node
(``ASTNode.source_text``); the degrade gates quote that.

The general invariant (shared helper ``tests/helpers/invariants.py``): every
"preserved as a comment" carrier body must parse in the SOURCE dialect
(comment markers stripped first — the comment-prose trap; the ``-- UNIQUE:``
reason line is prose, only the body is SQL).
"""

from __future__ import annotations

from helpers.invariants import assert_carrier_bodies_parse_as_source, carrier_bodies

from unique.core.transpiler import Transpiler

# The original N12 vehicle (JSON_VALUE/JSON_QUERY, an ``exp.JSONExtractScalar``
# with no mapping) now maps faithfully per engine (challenge red2-ts-json-value,
# 2026-07-30), so the "preserved as a comment" carrier-preservation invariant is
# re-anchored on a construct that still degrades: MySQL logical ``XOR`` is an
# unmapped operator on every other engine (expressible but non-trivial), so the
# whole statement degrades to a carrier — the same N12 class the audit found.
_N12_SQL = "SELECT a FROM t WHERE x XOR y"
_N12_TARGETS = ("oracle", "postgresql", "tsql")


class TestCarrierPreservesOriginal:
    def setup_method(self) -> None:
        self.t = Transpiler()

    def test_n12_carrier_holds_original_statement(self) -> None:
        for target in _N12_TARGETS:
            out = self.t.transpile(_N12_SQL, "mysql", target).sql
            # The statement degraded to a carrier (fails under an identity
            # transpiler, whose output has no carrier at all)…
            assert "UNIQUE:" in out, out
            # …holding the original source operator verbatim (not a re-render).
            assert "x XOR y" in out, out

    def test_n12_carrier_body_parses_as_source(self) -> None:
        for target in _N12_TARGETS:
            out = self.t.transpile(_N12_SQL, "mysql", target).sql
            bodies = carrier_bodies(out)
            assert bodies, f"no preserved-statement carrier for {target}: {out!r}"
            assert_carrier_bodies_parse_as_source(out, "mysql")

    def test_n12_still_warns(self) -> None:
        # The degrade is still signalled — no-silent-loss unchanged.
        for target in _N12_TARGETS:
            result = self.t.transpile(_N12_SQL, "mysql", target)
            assert result.warnings, target
            assert "UNIQUE:" in result.sql, target

    def test_two_statements_in_one_batch_each_preserve_their_original(self) -> None:
        # Neighbor: the construct twice in one batch — per-statement slices
        # must align (tokenizer boundaries), not fall back to the re-render.
        multi = "SELECT a FROM t WHERE x XOR y;\n" "SELECT b FROM t WHERE p XOR q;"
        out = self.t.transpile(multi, "mysql", "oracle").sql
        assert "UNIQUE:" in out, out  # identity-proof: carrier must exist
        assert "x XOR y" in out, out
        assert "p XOR q" in out, out
        assert_carrier_bodies_parse_as_source(out, "mysql")

    def test_semicolon_inside_string_does_not_break_alignment(self) -> None:
        # A ``;`` inside a string literal must not cut the slice (token
        # boundaries, never a text split).
        sql = "SELECT 'a;b' AS s FROM t WHERE x XOR y;"
        out = self.t.transpile(sql, "mysql", "oracle").sql
        assert "UNIQUE:" in out, out  # identity-proof: carrier must exist
        assert "'a;b'" in out and "x XOR y" in out, out


# Inputs that trigger a range of degrade gates across dialects. The shared
# invariant (carrier body parses in its source dialect) is asserted over all of
# them so a sibling carrier with the N12 defect surfaces here.
_GATE_INPUTS = [
    # unmapped operator (N12 class)
    (_N12_SQL, "mysql", "oracle"),
    (_N12_SQL, "mysql", "postgresql"),
    (_N12_SQL, "mysql", "tsql"),
    # PG catalog internal → non-PG
    ("SELECT CAST(t AS regclass) FROM t", "postgresql", "tsql"),
    ("SELECT ctid FROM t", "postgresql", "oracle"),
    # FULL OUTER JOIN → MySQL
    (
        "SELECT a.id FROM a FULL OUTER JOIN b ON a.id = b.id",
        "postgresql",
        "mysql",
    ),
    # whole-row cast → non-PG
    ("SELECT CAST(t.* AS some_type) FROM t", "postgresql", "tsql"),
    # array constructs → non-PG
    ("SELECT ARRAY[1, 2, 3] AS a", "postgresql", "mysql"),
    # CONNECT BY → PG/MySQL
    (
        "SELECT employee_id FROM employees "
        "CONNECT BY PRIOR employee_id = manager_id",
        "oracle",
        "postgresql",
    ),
]


class TestCarrierBodiesParseAsSource:
    """The general invariant, swept over gate-triggering inputs."""

    def setup_method(self) -> None:
        self.t = Transpiler()

    def test_all_preserved_carriers_parse_as_source(self) -> None:
        for sql, source, target in _GATE_INPUTS:
            out = self.t.transpile(sql, source, target).sql
            assert_carrier_bodies_parse_as_source(out, source)

    def test_gate_carriers_quote_the_original_text(self) -> None:
        # The carriers must hold the source spelling, not a re-render:
        # probe a case whose re-render used to differ (layout + mappings).
        out = self.t.transpile("SELECT ctid FROM t", "postgresql", "oracle").sql
        bodies = carrier_bodies(out)
        assert bodies == ["SELECT ctid FROM t"], bodies
