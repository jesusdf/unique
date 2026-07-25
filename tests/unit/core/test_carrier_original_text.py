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

# N12's exact input: JSON_VALUE/JSON_QUERY select. sqlglot models JSON_VALUE as
# an ``exp.JSONExtractScalar`` binary with no target mapping → the whole
# statement degrades to a carrier.
_N12_SQL = (
    "SELECT JSON_VALUE(doc, '$.name') AS n, "
    "JSON_QUERY(doc, '$.items') AS items FROM docs;"
)


class TestCarrierPreservesOriginal:
    def setup_method(self) -> None:
        self.t = Transpiler()

    def test_n12_carrier_holds_original_json_value(self) -> None:
        for target in ("oracle", "postgresql", "mysql"):
            out = self.t.transpile(_N12_SQL, "tsql", target).sql
            # The statement degraded to a carrier (fails under an identity
            # transpiler, whose output has no carrier at all)…
            assert "UNIQUE:" in out, out
            # …holding the original T-SQL accessors verbatim…
            assert "JSON_VALUE(doc, '$.name')" in out, out
            assert "JSON_QUERY(doc, '$.items')" in out, out
            # …and the mid-transform hybrid is gone.
            assert "dbo.JSON_EXTRACT" not in out, out
            assert "ISNULL(JSON_QUERY" not in out, out

    def test_n12_carrier_body_parses_as_source(self) -> None:
        for target in ("oracle", "postgresql", "mysql"):
            out = self.t.transpile(_N12_SQL, "tsql", target).sql
            bodies = carrier_bodies(out)
            assert bodies, f"no preserved-statement carrier for {target}: {out!r}"
            assert_carrier_bodies_parse_as_source(out, "tsql")

    def test_n12_still_warns(self) -> None:
        # The degrade is still signalled — no-silent-loss unchanged.
        for target in ("oracle", "postgresql", "mysql"):
            result = self.t.transpile(_N12_SQL, "tsql", target)
            assert result.warnings, target
            assert "UNIQUE:" in result.sql, target

    def test_two_statements_in_one_batch_each_preserve_their_original(self) -> None:
        # Neighbor: the construct twice in one batch — per-statement slices
        # must align (tokenizer boundaries), not fall back to the re-render.
        multi = (
            "SELECT JSON_VALUE(doc, '$.name') AS n FROM docs;\n"
            "SELECT JSON_VALUE(doc, '$.tag') AS t FROM docs;"
        )
        out = self.t.transpile(multi, "tsql", "oracle").sql
        assert "UNIQUE:" in out, out  # identity-proof: carrier must exist
        assert "JSON_VALUE(doc, '$.name')" in out, out
        assert "JSON_VALUE(doc, '$.tag')" in out, out
        assert "ISNULL(JSON_QUERY" not in out, out
        assert "dbo.JSON_EXTRACT" not in out, out
        assert_carrier_bodies_parse_as_source(out, "tsql")

    def test_semicolon_inside_string_does_not_break_alignment(self) -> None:
        # A ``;`` inside a string literal must not cut the slice (token
        # boundaries, never a text split).
        sql = "SELECT JSON_VALUE(doc, '$.a;b') AS n FROM docs;"
        out = self.t.transpile(sql, "tsql", "oracle").sql
        assert "UNIQUE:" in out, out  # identity-proof: carrier must exist
        assert "JSON_VALUE(doc, '$.a;b')" in out, out
        assert "dbo.JSON_EXTRACT" not in out, out


# Inputs that trigger a range of degrade gates across dialects. The shared
# invariant (carrier body parses in its source dialect) is asserted over all of
# them so a sibling carrier with the N12 defect surfaces here.
_GATE_INPUTS = [
    # unmapped operator (N12 class)
    (_N12_SQL, "tsql", "oracle"),
    (_N12_SQL, "tsql", "postgresql"),
    (_N12_SQL, "tsql", "mysql"),
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
