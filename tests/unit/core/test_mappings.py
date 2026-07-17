# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Consistency checks over the shared declarative mapping layer.

Audit doc 03: dialect knowledge used to live in three modules, which is how
asymmetries crept in (``STRING_AGG -> MySQL`` mapped while ``GROUP_CONCAT ->
PostgreSQL`` was not). These tests iterate the single mapping layer in both
directions so a new entry that lacks its counterpart — or disagrees with the
other pipeline — fails CI instead of surfacing as a doc-01-style bug.

Divergences that are *intentional* are listed here explicitly, each with the
reason, so changing them is a conscious act.
"""

from __future__ import annotations

from unique.core.mappings import (
    BARE_CHAR_BIGTEXT,
    CANONICAL_FUNCTION_NAMES,
    CURRENT_TIMESTAMP_EXPR,
    DIALECTS,
    EMIT_TYPE_MAP,
    PROCEDURAL_FUNC_MAPS,
    PROCEDURAL_TYPE_MAPS,
    UUID_FUNCTION,
)


def _base(type_name: str) -> str:
    """The bare type name: no length params, no UNSIGNED/precision suffix."""
    return type_name.split("(")[0].strip().upper()


class TestTableShape:
    def test_per_dialect_tables_cover_every_dialect(self) -> None:
        for table in (CURRENT_TIMESTAMP_EXPR, UUID_FUNCTION):
            assert set(table) == set(DIALECTS)
        assert set(EMIT_TYPE_MAP) == set(DIALECTS)
        assert set(BARE_CHAR_BIGTEXT) == set(DIALECTS)

    def test_pair_tables_use_known_dialects(self) -> None:
        for source, target in list(PROCEDURAL_TYPE_MAPS) + list(PROCEDURAL_FUNC_MAPS):
            assert source in DIALECTS and target in DIALECTS
            assert source != target

    def test_canonical_names_do_not_chain(self) -> None:
        # A canonical name must itself be canonical (no A->B->C chains).
        for canonical in CANONICAL_FUNCTION_NAMES.values():
            assert canonical not in CANONICAL_FUNCTION_NAMES


class TestFunctionMapSymmetry:
    """A rename A->B must round-trip through the reverse pair map."""

    # (source, target, function): the reverse map deliberately does not
    # invert this entry. Each needs a reason.
    _ONE_WAY: dict[tuple[str, str, str], str] = {
        # TO_CHAR/TO_DATE/TO_NUMBER carry format arguments T-SQL spells as
        # CONVERT style codes; the reverse (CONVERT -> TO_*) needs argument
        # surgery the plain rename table cannot express.
        ("oracle", "tsql", "TO_CHAR"): "argument shapes differ",
        ("oracle", "tsql", "TO_DATE"): "argument shapes differ",
        ("oracle", "tsql", "TO_NUMBER"): "argument shapes differ",
        # MySQL LENGTH() counts bytes; both LENGTH and CHAR_LENGTH fold to
        # LEN on T-SQL, but the reverse expansion picks CHAR_LENGTH only.
        ("mysql", "tsql", "LENGTH"): "byte- vs char-length collapse",
        # CHR -> CHAR must not invert: "CHAR(" is also the type spelling in
        # CAST contexts, which the text rewriter's name(paren) regex would
        # mangle (CAST(x AS CHAR(10)) -> CHR(10)).
        ("oracle", "tsql", "CHR"): "CHAR( collides with the CAST type spelling",
        ("oracle", "mysql", "CHR"): "CHAR( collides with the CAST type spelling",
        ("postgresql", "tsql", "CHR"): "CHAR( collides with the CAST type spelling",
        ("postgresql", "mysql", "CHR"): "CHAR( collides with the CAST type spelling",
    }

    def test_renames_round_trip(self) -> None:
        problems: list[str] = []
        for (source, target), fmap in PROCEDURAL_FUNC_MAPS.items():
            reverse = PROCEDURAL_FUNC_MAPS.get((target, source))
            if reverse is None:
                continue
            for src_fn, tgt_fn in fmap.items():
                if tgt_fn.startswith("--") or not tgt_fn.isidentifier():
                    continue  # documented placeholder or expression rewrite
                if src_fn.upper() == tgt_fn.upper():
                    continue
                if (source, target, src_fn) in self._ONE_WAY:
                    continue
                back = reverse.get(tgt_fn.upper())
                if back is not None and back.upper() == tgt_fn.upper():
                    # Synonym collapse: the target spelling is also native to
                    # the source (e.g. ISNULL -> COALESCE, which T-SQL has),
                    # so the reverse correctly keeps it as-is.
                    continue
                if back is None or back.upper() != src_fn.upper():
                    problems.append(
                        f"{source}->{target} maps {src_fn} -> {tgt_fn}, but "
                        f"{target}->{source} maps {tgt_fn} -> {back!r}"
                    )
        assert not problems, "\n".join(problems)

    def test_no_self_remapping_entries(self) -> None:
        # An entry's output must not be another key of the same map with a
        # different result (the single-pass rewriter shields at runtime, but
        # the table itself should not encode the ambiguity).
        for (source, target), fmap in PROCEDURAL_FUNC_MAPS.items():
            upper = {k.upper(): v for k, v in fmap.items()}
            for src_fn, tgt_fn in upper.items():
                if tgt_fn.startswith("--") or not tgt_fn.isidentifier():
                    continue
                chained = upper.get(tgt_fn.upper())
                assert chained is None or chained.upper() == tgt_fn.upper(), (
                    f"{source}->{target}: {src_fn} -> {tgt_fn} would re-map "
                    f"to {chained}"
                )


class TestTypeMapCrossPipelineAgreement:
    """Both pipelines must translate the same source type the same way."""

    # (source, target, type): the pipelines deliberately differ. Reasons
    # recorded so any change here is conscious (audit doc 03).
    _KNOWN_DIVERGENCES: dict[tuple[str, str, str], str] = {
        ("tsql", "oracle", "DATETIME"): (
            "procedural favors DATE (PL/SQL parameter idiom, second "
            "precision suffices); the DML/DDL pipeline favors TIMESTAMP "
            "for column fidelity"
        ),
        ("tsql", "oracle", "SMALLDATETIME"): "same trade-off as DATETIME",
        ("oracle", "tsql", "NUMBER"): (
            "procedural declares DECIMAL (parameter position, no scale "
            "known); the DML pipeline emits NUMERIC — synonyms on T-SQL"
        ),
        ("oracle", "tsql", "VARCHAR2"): (
            "procedural widens to NVARCHAR (PL/SQL text is often national); "
            "the DML pipeline keeps VARCHAR for column fidelity"
        ),
        ("oracle", "tsql", "CLOB"): (
            "counterpart of the VARCHAR2 trade-off: procedural widens to "
            "NVARCHAR(MAX), the DML pipeline keeps VARCHAR(MAX)"
        ),
        ("tsql", "postgresql", "FLOAT"): (
            "procedural spells DOUBLE PRECISION; the DML pipeline leaves "
            "FLOAT (PostgreSQL accepts both, FLOAT is an alias)"
        ),
        ("tsql", "mysql", "FLOAT"): (
            "procedural widens to DOUBLE (T-SQL FLOAT defaults to float(53)); "
            "the DML pipeline leaves FLOAT"
        ),
        ("tsql", "mysql", "REAL"): "counterpart of the FLOAT trade-off",
    }

    def test_pair_maps_agree_with_emit_map(self) -> None:
        problems: list[str] = []
        for (source, target), tmap in PROCEDURAL_TYPE_MAPS.items():
            emit = EMIT_TYPE_MAP[target]
            for src_type, pair_result in tmap.items():
                emit_result = emit.get(src_type)
                if emit_result is None:
                    continue  # emit map has no opinion: nothing to disagree
                if (source, target, src_type) in self._KNOWN_DIVERGENCES:
                    continue
                if _base(pair_result) != _base(emit_result):
                    problems.append(
                        f"{source}->{target} {src_type}: procedural says "
                        f"{pair_result}, emit map says {emit_result}"
                    )
        assert not problems, "\n".join(problems)

    def test_uuid_and_now_agree_with_func_maps(self) -> None:
        # The per-pair function maps must send each source's UUID function to
        # the target's UUID_FUNCTION spelling.
        for (source, target), fmap in PROCEDURAL_FUNC_MAPS.items():
            src_uuid = UUID_FUNCTION[source].upper()
            tgt_uuid = UUID_FUNCTION[target].upper()
            mapped = fmap.get(src_uuid) or fmap.get(UUID_FUNCTION[source])
            if mapped is not None:
                assert mapped.upper() == tgt_uuid, (
                    f"{source}->{target}: {src_uuid} maps to {mapped}, "
                    f"expected {tgt_uuid}"
                )
