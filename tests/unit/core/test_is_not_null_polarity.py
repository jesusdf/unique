# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""``IS NOT NULL`` polarity must survive every pipeline (sqlglot-upgrade pin).

sqlglot ≤30.11 models ``IS NOT NULL`` as ``Not(Is(…))``; 30.12+ folds the
negation into ``Is(…, negate=True)`` (at least under the postgres reader).
An unread ``negate`` arg silently INVERTED predicates on upgrade — a
``DELETE … WHERE a IS NOT NULL`` shipped as ``WHERE a IS NULL`` (upgrade
prep 2026-07-30; the audit's unread-args class). These tests accept either
correct spelling (``IS NOT NULL`` / ``NOT (a IS NULL)``) and reject the
inversion, so they hold under both AST models.
"""

from __future__ import annotations

import re

import pytest

from unique.core.transpiler import Transpiler

_NOT_NULL_FORMS = r"(?i)a\s+IS\s+NOT\s+NULL|NOT\s+\(?\s*a\s+IS\s+NULL\s*\)?"
_INVERTED = r"(?i)WHERE\s+\(?\s*a\s+IS\s+NULL"


def _flat(sql: str) -> str:
    return " ".join(sql.split())


class TestIsNotNullNeverInverts:
    @pytest.mark.parametrize("source", ["tsql", "postgresql", "mysql", "oracle"])
    @pytest.mark.parametrize("target", ["tsql", "postgresql", "mysql", "oracle"])
    def test_delete_predicate_keeps_polarity(self, source: str, target: str) -> None:
        if source == target:
            pytest.skip("identity direction")
        out = (
            Transpiler()
            .transpile("DELETE FROM t WHERE a IS NOT NULL", source, target)
            .sql
        )
        flat = _flat(out)
        assert re.search(_NOT_NULL_FORMS, flat), (source, target, flat)
        assert not re.search(_INVERTED, flat), (source, target, flat)

    def test_update_predicate_keeps_polarity_pg_source(self) -> None:
        out = (
            Transpiler()
            .transpile(
                "UPDATE t SET x = 1 WHERE a IS NOT NULL AND b IS NULL",
                "postgresql",
                "mysql",
            )
            .sql
        )
        flat = _flat(out)
        assert re.search(_NOT_NULL_FORMS, flat), flat
        assert re.search(r"(?i)b\s+IS\s+NULL", flat), flat

    def test_filtered_index_predicate_keeps_polarity(self) -> None:
        # The T-SQL filtered-index grammar only accepts the IS NOT NULL
        # spelling; _tsql_index_predicate must read Is.negate (30.12+) as
        # well as the Not(Is(…)) wrapper (≤30.11).
        out = (
            Transpiler()
            .transpile(
                "create index i7 on t7(a) where a is not null and b is not null;",
                "postgresql",
                "tsql",
            )
            .sql
        )
        assert re.search(r"(?i)WHERE a IS NOT NULL AND b IS NOT NULL", out), out
