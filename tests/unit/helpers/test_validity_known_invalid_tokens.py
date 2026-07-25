# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Unit tests for the validity gate's KNOWN_INVALID_TOKENS denylist.

sqlglot's readers are lenient: the postgres/tsql readers echo the raw
``TIMESTAMPLTZ`` token and the mysql reader rewrites it to ``TIMESTAMP``, so
the pure parse gate waves through DDL that every real engine rejects. The
denylist closes that hole by scanning the comment-stripped output after the
parse. These pin that behaviour against a fabricated invalid output (no live
DB, no transpiler) so a regression in the gate fails here, loudly.
"""

from __future__ import annotations

import pytest

from tests.helpers.validity import (
    KNOWN_INVALID_TOKENS,
    assert_parses,
    assert_statements_parse,
)


class TestAssertParsesDenylist:
    def test_rejects_timestampltz_on_postgres(self) -> None:
        # sqlglot's postgres reader accepts this; the denylist must not.
        with pytest.raises(AssertionError, match="TIMESTAMPLTZ"):
            assert_parses("CREATE TABLE t (d TIMESTAMPLTZ)", "postgresql")

    def test_rejects_timestampltz_on_tsql(self) -> None:
        with pytest.raises(AssertionError, match="TIMESTAMPLTZ"):
            assert_parses("CREATE TABLE t (d TIMESTAMPLTZ)", "tsql")

    def test_accepts_the_real_mapped_type(self) -> None:
        # The fix maps LTZ -> timestamptz; the valid token must pass cleanly.
        assert_parses("CREATE TABLE t (d TIMESTAMPTZ)", "postgresql")

    def test_denylist_ignores_the_token_inside_a_carrier_comment(self) -> None:
        # A -- UNIQUE: carrier that happens to name the token is trivia, not
        # executable DDL, so the comment-stripped scan must not trip on it.
        sql = (
            "CREATE TABLE t (d TIMESTAMPTZ)\n"
            "-- UNIQUE: mapped away from TIMESTAMPLTZ (docs/03-unsupported.md)"
        )
        assert_parses(sql, "postgresql")


class TestAssertStatementsParseDenylist:
    def test_rejects_timestampltz_statement(self) -> None:
        with pytest.raises(AssertionError, match="TIMESTAMPLTZ"):
            assert_statements_parse("CREATE TABLE t (d TIMESTAMPLTZ);", "postgresql")

    def test_accepts_mapped_output(self) -> None:
        assert_statements_parse("CREATE TABLE t (d TIMESTAMPTZ);", "postgresql")


def test_seeded_for_every_foreign_target() -> None:
    # The Oracle LTZ leniency hole exists on all three foreign targets, so the
    # denylist must guard each; oracle (which spells the type natively) is out.
    for target in ("postgresql", "tsql", "mysql"):
        assert "TIMESTAMPLTZ" in KNOWN_INVALID_TOKENS.get(target, ())
