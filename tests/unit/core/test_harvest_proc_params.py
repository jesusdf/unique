# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""``harvest_proc_date_params``: behaviour + a ReDoS regression.

The ``CREATE PROCEDURE`` header regex runs over user-supplied SQL (via the API
when the target is Oracle). CodeQL flagged it as ``py/polynomial-redos``: a
crafted, unterminated header backtracked quadratically. These guard both the
parsing behaviour and that the pathological input now stays linear.
"""

from __future__ import annotations

import time

from unique.core.converter.harvest import harvest_proc_date_params


class TestHarvestProcDateParams:
    def test_detects_tsql_date_param_position(self) -> None:
        out = harvest_proc_date_params("CREATE PROCEDURE p @a INT, @b DATE AS SELECT 1")
        assert out == {"p": frozenset({1})}

    def test_parenthesized_in_date_form(self) -> None:
        out = harvest_proc_date_params(
            "CREATE PROCEDURE s.f (p1 IN NUMBER, p2 IN DATE) IS BEGIN NULL; END"
        )
        assert out == {"f": frozenset({1})}

    def test_no_date_params_is_empty(self) -> None:
        assert harvest_proc_date_params("CREATE PROCEDURE p @a INT AS SELECT 1") == {}

    def test_unterminated_header_is_not_a_redos(self) -> None:
        # No AS/IS/BEGIN/LANGUAGE terminator + a long whitespace run: the old regex
        # backtracked polynomially (~30 s at 2k chars). The possessive-quantifier
        # header regex is linear — assert it returns fast. The bound is generous
        # (the fixed form takes ~1 ms) so it is not timing-flaky on slow CI.
        evil = "CREATE PROCEDURE x " + " " * 40000
        start = time.perf_counter()
        result = harvest_proc_date_params(evil)
        assert time.perf_counter() - start < 2.0
        assert result == {}
