# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""SQL*Plus ``SET`` client directives are documented, never shipped raw.

On the real Oracle dump ~940 statements per direction failed because ``SET
SERVEROUTPUT ON`` (line-oriented, no ``;``) glued to the following block and
shipped as-is (audit 2026-07-08 sweep). The splitter now peels the directive
into its own batch and the SET_OPTION path comments it with a warning.
"""

from __future__ import annotations

import pytest

from unique.core.transpiler import Transpiler

_SRC = "SET SERVEROUTPUT ON\nBEGIN\n  my_proc('x');\nEND;\n/"


@pytest.mark.parametrize("target", ["tsql", "postgresql", "mysql"])
def test_directive_commented_and_block_survives(target: str) -> None:
    r = Transpiler().transpile(_SRC, "oracle", target)
    assert "-- SET SERVEROUTPUT ON" in r.sql
    # The directive never ships as executable SQL...
    executable = [
        ln
        for ln in r.sql.splitlines()
        if ln.strip() and not ln.strip().startswith("--")
    ]
    assert not any("SERVEROUTPUT" in ln for ln in executable)
    # ...and the block behind it still translates (the call survives).
    assert "my_proc" in " ".join(executable)
    # No-silent-loss: the drop is warned.
    assert any("SQL*Plus directive" in w.message for w in r.warnings)


def test_set_transaction_not_treated_as_directive() -> None:
    # Real Oracle SQL spelled with SET must not be commented out.
    r = Transpiler().transpile("SET TRANSACTION READ ONLY;", "oracle", "postgresql")
    assert "-- SET TRANSACTION" not in r.sql
    assert not any("SQL*Plus directive" in w.message for w in r.warnings)
