"""Functional-equivalence checks for transpiled stored procedures.

The fingerprint logic was promoted into ``unique.core.similarity`` (backing the
``unique compare`` structural-similarity feature). This module remains a thin
re-export so existing tests keep importing it from here.

See :mod:`unique.core.similarity` for the implementation and the rationale for
the structural fingerprint (DML verbs, query shape, control flow) used to catch
silent semantic changes across a transpilation.
"""

from __future__ import annotations

from unique.core.similarity import (
    ProcedureFingerprint,
    assert_functionally_equivalent,
    fingerprint,
)

__all__ = [
    "ProcedureFingerprint",
    "assert_functionally_equivalent",
    "fingerprint",
]
