# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Heuristic detection of the SQL dialect of a script.

Detection is best-effort: it scores each candidate dialect by counting
signature constructs (syntax, built-in functions, data types, system
objects) and returns the highest-scoring dialect together with a normalized
confidence and the per-dialect scores. When no signal is found the result is
``None`` so callers can fall back to asking the user.

This is intentionally dependency-free (pure regex over the text) so it can run
anywhere, including the API and CLI.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Each rule: (compiled pattern, weight). Higher weight = stronger signal.
# Patterns are matched case-insensitively over the raw script text.
_Rule = tuple[re.Pattern[str], int]


def _rules(*specs: tuple[str, int]) -> list[_Rule]:
    return [(re.compile(p, re.IGNORECASE | re.MULTILINE), w) for p, w in specs]


# Signals strongly characteristic of each engine. Weights are hand-tuned:
# 3 = near-unique to the dialect, 2 = strong, 1 = weak/shared hint.
_SIGNALS: dict[str, list[_Rule]] = {
    "tsql": _rules(
        (r"^\s*GO\s*$", 3),  # batch separator
        (r"\bnvarchar\b", 2),
        (r"\bdatetime2\b", 3),
        (r"\buniqueidentifier\b", 3),
        (r"\bIDENTITY\s*\(", 2),
        (r"\[[A-Za-z_][\w ]*\]", 2),  # [bracketed] identifiers
        (r"\bGETDATE\s*\(\s*\)", 3),
        (r"@@(IDENTITY|ROWCOUNT|ERROR|TRANCOUNT)\b", 3),
        (r"\bsp_\w+", 2),  # system stored procs
        (r"\bDECLARE\s+@\w+", 2),  # @-prefixed variables
        (r"\bISNULL\s*\(", 2),
        (r"\bTOP\s+\d+", 2),
        (r"\bROWGUIDCOL\b", 3),
        (r"\bOUTPUT\s+(INSERTED|DELETED)\.", 3),
    ),
    "oracle": _rules(
        (r"^\s*/\s*$", 3),  # PL/SQL slash terminator
        (r"\bVARCHAR2\b", 3),
        (r"\bNUMBER\s*\(", 2),
        (r"\bNVL\s*\(", 2),
        (r"\bNVL2\s*\(", 3),
        (r"\bDECODE\s*\(", 2),
        (r"\bSYSDATE\b", 3),
        (r"\bDBMS_\w+", 3),
        (r"\bDUAL\b", 2),
        (r"\bCONNECT\s+BY\b", 3),
        (r"\bSTART\s+WITH\b", 2),
        (r"\b\w+%(TYPE|ROWTYPE)\b", 3),
        (r"\bIS\s+(?:NOT\s+NULL\s+)?\bBEGIN\b", 1),
        (r"\bCREATE\s+OR\s+REPLACE\s+PACKAGE\b", 3),
        (r"\bLISTAGG\s*\(", 2),
        (r":\w+\b", 1),  # bind variables
    ),
    "postgresql": _rules(
        (r"\$\$", 3),  # dollar-quoting
        (r"\$[A-Za-z_]\w*\$", 3),  # named dollar-quoting
        (r"\bSERIAL\b", 3),
        (r"\bBIGSERIAL\b", 3),
        (r"\bLANGUAGE\s+plpgsql\b", 3),
        (r"\bRETURNS\s+(SETOF|TABLE|TRIGGER)\b", 2),
        (r"\bNOW\s*\(\s*\)", 1),
        (r"::\w+", 2),  # ::cast syntax
        # Weak signals: TEXT/BOOLEAN exist on MySQL too, so they only
        # nudge the score (they were dead weight-0 rules before the
        # 2026-07-02 audit).
        (r"\bTEXT\b", 1),
        (r"\bBOOLEAN\b", 1),
        (r"\bRETURNING\b", 2),
        (r"\bON\s+CONFLICT\b", 3),
        (r"\bILIKE\b", 3),
        (r"\bSTRING_AGG\s*\(", 1),
        # pg_dump output signatures (data-only dumps lack the above).
        (r"\bSET\s+standard_conforming_strings\b", 3),
        (r"\bSET\s+client_encoding\b", 2),
        (r"\bSET\s+statement_timeout\b", 2),
        (r"\bdefault_with_oids\b", 3),
        (r"\bSET\s+search_path\b", 2),
        (r"Owner:\s*-", 2),
        (r"\bOWNER\s+TO\b", 2),
        (r"\bnextval\s*\(", 2),
    ),
    "mysql": _rules(
        (r"\bDELIMITER\b", 3),
        (r"\bAUTO_INCREMENT\b", 3),
        (r"`[^`]+`", 3),  # backtick identifiers
        (r"\bENGINE\s*=", 3),
        (r"\bUNSIGNED\b", 2),
        (r"\bTINYINT\b", 2),
        (r"\bLAST_INSERT_ID\s*\(", 3),
        (r"\bGROUP_CONCAT\s*\(", 3),
        (r"\bON\s+DUPLICATE\s+KEY\s+UPDATE\b", 3),
        (r"\bUNLOCK\s+TABLES\b", 2),
        (r"\bSEPARATOR\b", 2),
        (r"\bIFNULL\s*\(", 2),
        (r"\bDATE_FORMAT\s*\(", 1),
        (r"\bSTR_TO_DATE\s*\(", 1),
    ),
}


@dataclass(frozen=True)
class DetectionResult:
    """Outcome of dialect detection.

    ``dialect`` is the best guess (or ``None`` if no signal was found),
    ``confidence`` is in [0, 1], and ``scores`` maps every candidate to its
    raw weighted hit count.
    """

    dialect: str | None
    confidence: float
    scores: dict[str, int]


def detect_dialect(sql: str) -> DetectionResult:
    """Guess the SQL dialect of ``sql`` using weighted signature matching.

    Returns a :class:`DetectionResult`. Confidence is the winning score over
    the total of all scores, lightly damped when the margin to the runner-up
    is small so callers can treat a near-tie as low confidence.
    """
    scores: dict[str, int] = {}
    for dialect, rules in _SIGNALS.items():
        total = 0
        for pattern, weight in rules:
            hits = len(pattern.findall(sql))
            total += hits * weight
        scores[dialect] = total

    total_score = sum(scores.values())
    if total_score == 0:
        return DetectionResult(dialect=None, confidence=0.0, scores=scores)

    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    best_dialect, best_score = ranked[0]
    runner_up = ranked[1][1] if len(ranked) > 1 else 0

    # Require a minimum absolute signal so a single weak/shared keyword (e.g.
    # the word "text") in otherwise non-SQL input is not treated as a match.
    if best_score < 2:
        return DetectionResult(dialect=None, confidence=0.0, scores=scores)

    base = best_score / total_score
    # Damp confidence when the lead over the runner-up is thin.
    margin = (best_score - runner_up) / best_score if best_score > 0 else 0.0
    confidence = round(base * (0.5 + 0.5 * margin), 3)

    return DetectionResult(dialect=best_dialect, confidence=confidence, scores=scores)
