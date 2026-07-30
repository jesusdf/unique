"""Generic, content-based invariants for validating transpiler output.

These helpers encode two dialect-agnostic sanity checks that catch a broad
class of bugs without hand-writing assertions per construct:

1. **Element conservation** -- if the input declares N tables / inserts into
   M rows / references K identifiers, the output should contain a comparable
   count, *or* explicitly document what was dropped (a ``-- UNIQUE:`` comment).
   A silent drop (count falls with no explanatory comment) is the bug we care
   about most, because it changes semantics without telling anyone.

2. **Round-trip stability** -- translating A -> B -> A' should yield an A'
   that is "almost identical" to A once both are normalized (whitespace,
   keyword case, identifier quoting, comments removed). Exact string equality
   is too strict across dialects, so we compare *normalized token multisets*.

The goal is a reusable validation, not a rigid rule: callers pick a tolerance
that fits how lossy a given pair is expected to be.
"""

from __future__ import annotations

import re

from unique.core.diagnostics import MARKER, is_registered

# Keywords whose presence is structurally meaningful. We compare how many of
# each survive translation rather than trying to parse the SQL.
_STRUCTURAL_KEYWORDS = (
    "CREATE TABLE",
    "CREATE INDEX",
    "CREATE VIEW",
    "PRIMARY KEY",
    "FOREIGN KEY",
    "REFERENCES",
    "UNIQUE",
    "CHECK",
    "INSERT INTO",
    "UPDATE",
    "DELETE",
    "SELECT",
    "WHERE",
    "JOIN",
)

# Recognizes both the legacy uncoded ``UNIQUE:`` and the coded ``UNIQUE-1234:``
# carrier form (B32) so pre-code and post-code outputs both match; shares its
# marker fragment with the diagnostics registry so both stay in sync.
_UNIQUE_COMMENT = re.compile(rf"(?im)^\s*--\s*{MARKER}")
_LINE_COMMENT = re.compile(r"--[^\n]*")
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_WHITESPACE = re.compile(r"\s+")
_IDENTIFIER_QUOTES = re.compile(r'[`"\[\]]')


def carrier_bodies(sql: str) -> list[str]:
    """The statement body of each "preserved as a comment" carrier in *sql*.

    A carrier is a ``-- UNIQUE: <reason>`` line whose reason says the
    statement is preserved, followed by consecutive ``--`` comment lines
    holding it. The reason line is prose and is excluded (the comment-prose
    trap); only the body lines are returned, ``--`` prefix stripped, ready to
    parse in the source dialect.
    """
    lines = sql.splitlines()
    bodies: list[str] = []
    i = 0
    while i < len(lines):
        m = re.match(r"\s*-- UNIQUE(?:-\d{4})?:\s*(.*)", lines[i])
        if m and "preserved as a comment" in m.group(1).lower():
            body_lines: list[str] = []
            i += 1
            while i < len(lines) and lines[i].lstrip().startswith("--"):
                if re.match(r"\s*-- UNIQUE(?:-\d{4})?:", lines[i]):
                    break
                body_lines.append(re.sub(r"^\s*--\s?", "", lines[i]))
                i += 1
            if any(ln.strip() for ln in body_lines):
                bodies.append("\n".join(body_lines).strip())
            continue
        i += 1
    return bodies


def assert_carrier_bodies_parse_as_source(sql: str, source: str) -> None:
    """Every preserved-statement carrier body must parse in *source*.

    The carrier's contract is that a user can uncomment the body and rewrite
    it by hand — a body that does not even parse in the SOURCE dialect is a
    mid-transform hybrid, not a preserved statement (audit 2026-07-24 N12).
    """
    import sqlglot

    from unique.core.converter._base import sqlglot_dialect_name

    read = sqlglot_dialect_name(source)
    for body in carrier_bodies(sql):
        try:
            sqlglot.parse(body, read=read, error_level=sqlglot.ErrorLevel.RAISE)
        except Exception as e:
            # sqlglot cannot parse procedural routines (multi-statement
            # bodies); for those the parser of record is the procedural
            # engine — accept the body iff IT parses it cleanly.
            from unique.core.procedural.parser import ProceduralParser

            result = ProceduralParser(source).parse(body)
            if result.node is None or result.errors:
                raise AssertionError(
                    f"carrier body does not parse as {source}: {e}\n"
                    f"--- body ---\n{body}"
                ) from e


def count_keyword(sql: str, keyword: str) -> int:
    """Count non-comment occurrences of a structural keyword (word-bounded)."""
    body = strip_comments(sql)
    pattern = r"\b" + r"\s+".join(re.escape(w) for w in keyword.split()) + r"\b"
    return len(re.findall(pattern, body, flags=re.IGNORECASE))


def documented_drops(sql: str) -> int:
    """Number of explicitly documented ``-- UNIQUE:`` drop/notice comments.

    A coded carrier (``UNIQUE-1234:``) only counts if 1234 is a REGISTERED
    diagnostic (B32) -- a stray/malformed code must not excuse a dropped
    keyword. The legacy uncoded ``UNIQUE:`` form (no digits) still counts.
    """
    count = 0
    for m in _UNIQUE_COMMENT.finditer(sql):
        code = m.group("code")
        if code is None or is_registered(f"UNIQUE-{code}"):
            count += 1
    return count


def strip_comments(sql: str) -> str:
    """Remove line and block comments."""
    return _LINE_COMMENT.sub("", _BLOCK_COMMENT.sub("", sql))


def normalize(sql: str) -> str:
    """Normalize SQL for lenient comparison.

    Lowercases, removes comments, strips identifier quoting (`` ` ``, ``"``,
    ``[`` / ``]``), and collapses whitespace. The result is not valid SQL --
    it is a canonical form for comparing *content*, not syntax.
    """
    text = strip_comments(sql)
    text = _IDENTIFIER_QUOTES.sub("", text)
    text = text.lower()
    text = _WHITESPACE.sub(" ", text)
    return text.strip()


def token_multiset(sql: str) -> dict[str, int]:
    """Bag of alphanumeric tokens in the normalized SQL.

    Identifiers and keywords both count; punctuation is ignored. Comparing two
    multisets reveals content that appears or disappears across a round-trip.
    """
    norm = normalize(sql)
    counts: dict[str, int] = {}
    for tok in re.findall(r"[a-z0-9_]+", norm):
        counts[tok] = counts.get(tok, 0) + 1
    return counts


def jaccard_similarity(a: str, b: str) -> float:
    """Jaccard similarity of the distinct token sets of two SQL strings."""
    ta = set(token_multiset(a))
    tb = set(token_multiset(b))
    if not ta and not tb:
        return 1.0
    inter = len(ta & tb)
    union = len(ta | tb)
    return inter / union if union else 1.0


def structural_summary(sql: str) -> dict[str, int]:
    """Map each structural keyword to its count in ``sql``."""
    return {kw: count_keyword(sql, kw) for kw in _STRUCTURAL_KEYWORDS}


def assert_no_silent_loss(
    source_sql: str,
    output_sql: str,
    *,
    keywords: tuple[str, ...] = _STRUCTURAL_KEYWORDS,
    tolerance: float = 0.0,
) -> list[str]:
    """Return a list of human-readable violations (empty if all good).

    For each structural keyword, the output count must be at least the source
    count minus what is explicitly documented via ``-- UNIQUE:`` comments,
    allowing a fractional ``tolerance`` slack. A returned non-empty list means
    something was dropped silently.
    """
    drops = documented_drops(output_sql)
    violations: list[str] = []
    for kw in keywords:
        src_n = count_keyword(source_sql, kw)
        if src_n == 0:
            continue
        out_n = count_keyword(output_sql, kw)
        allowed_floor = src_n * (1.0 - tolerance) - drops
        if out_n < allowed_floor:
            violations.append(
                f"{kw}: source={src_n} output={out_n} "
                f"documented_drops={drops} (floor={allowed_floor:.1f})"
            )
    return violations
