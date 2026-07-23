# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Per-engine built-in *function* catalogs.

Answers one question the transpiler leans on to convert function calls
faithfully: **is this name a built-in of engine E, or a user object?**

- A **source** built-in is the transpiler's responsibility to translate; if it
  has no target form it degrades to an honest carrier + warning (never ships
  silently invalid).
- A name that is *not* a source built-in is a **user object** (a UDF, stored
  proc, or user type) and is passed through untouched — degrading it would break
  valid calls.
- A **target** built-in tells the gate an emitted name will actually run there.

The catalogs are authoritative, sourced live from each engine (``pg_proc``,
``V$SQLFN_METADATA``, ``mysql.help_topic``) plus a curated T-SQL list, and
snapshotted to static data files by ``scripts/gen_builtins.py``. This module
only *reads* those files — the runtime never touches a database. sqlglot's
per-dialect function registry is deliberately **not** used here: it is shared
across dialects (SOUNDEX shows as a "built-in" on all four) and cannot
discriminate one engine from another.
"""

from __future__ import annotations

from functools import cache
from importlib import resources

#: Our dialect names (the transpiler's), matching the data-file stems.
_ENGINES = ("tsql", "oracle", "postgresql", "mysql")

#: Grammar-level SQL functions every engine implements in its parser rather than
#: as a catalog entry, so they are absent from the introspection snapshots
#: (``CAST``/``COALESCE``/… are not ``pg_proc`` rows). Unioned into every
#: engine's set so a valid ``CAST(x AS ...)`` is never mistaken for an
#: untranslated built-in. Every name here is a recognised call spelling on all
#: four engines (semantic differences, e.g. ``CONVERT`` arg order, are a
#: separate concern from name validity).
_SQL_STANDARD = frozenset(
    {
        "CAST",
        "CONVERT",
        "COALESCE",
        "NULLIF",
        "GREATEST",
        "LEAST",
        "EXTRACT",
        "POSITION",
        "OVERLAY",
        "SUBSTRING",
        "TRIM",
        "LTRIM",
        "RTRIM",
        "UPPER",
        "LOWER",
    }
)


#: Grammar-level SQL/XML functions that only *some* engines implement in their
#: parser (so introspection misses them), unlike the universal _SQL_STANDARD.
#: XMLELEMENT/XMLAGG are SQL/XML built-ins on Oracle and PostgreSQL but do not
#: exist on MySQL/T-SQL, so they must stay engine-scoped — union them globally
#: and the gate would stop degrading them (a genuine limit) where they are
#: absent. Only names whose emitter renders a valid call on the listed engine
#: belong here (adding one the emitter mis-spells would ship silently invalid).
_ENGINE_STANDARD: dict[str, frozenset[str]] = {
    # Oracle built-in package functions with no cross-engine equivalent — listing
    # them lets the output gate flag (and degrade) an unmapped leak rather than
    # ship an undefined function silently. Distinctive names only (no LENGTH,
    # SUBSTR, … that collide with standard scalars).
    "oracle": frozenset(
        {
            "XMLELEMENT",
            "XMLAGG",
            "EDIT_DISTANCE",  # UTL_MATCH
            "EDIT_DISTANCE_SIMILARITY",
            "JARO_WINKLER",
            "JARO_WINKLER_SIMILARITY",
            "CAST_TO_RAW",  # UTL_RAW
            "CAST_TO_VARCHAR2",
            "CAST_TO_NVARCHAR2",
        }
    ),
    "postgresql": frozenset({"XMLELEMENT"}),  # XMLAGG is already introspected
    # T-SQL identity-scope functions with no cross-engine equivalent — they read
    # the last inserted IDENTITY value in a given scope. Flag them so the gate
    # degrades rather than shipping an undefined function.
    "tsql": frozenset({"IDENT_CURRENT"}),
}


@cache
def _load(engine: str) -> frozenset[str]:
    """Load the upper-cased built-in name set for *engine* from its data file."""
    data = (
        resources.files("unique.core")
        .joinpath("data", "builtins", f"{engine}.txt")
        .read_text(encoding="utf-8")
    )
    names = {
        line.strip().upper()
        for line in data.splitlines()
        if line.strip() and not line.startswith("#")
    }
    return frozenset(names | _SQL_STANDARD | _ENGINE_STANDARD.get(engine, frozenset()))


def _bare_name(name: str) -> str:
    """The unqualified function name, upper-cased (drops a ``schema.`` prefix)."""
    return name.rsplit(".", 1)[-1].strip().upper()


def is_builtin(name: str, dialect: str) -> bool:
    """Whether *name* is a built-in function of *dialect*.

    Case-insensitive and schema-insensitive (``dbo.SOUNDEX`` → ``SOUNDEX``).
    An unknown dialect returns ``False`` (treated as "cannot confirm").
    """
    if dialect not in _ENGINES:
        return False
    return _bare_name(name) in _load(dialect)


def builtins_for(dialect: str) -> frozenset[str]:
    """The full built-in catalog for *dialect* (empty for an unknown dialect)."""
    return _load(dialect) if dialect in _ENGINES else frozenset()
