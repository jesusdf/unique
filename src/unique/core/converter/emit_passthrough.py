# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Shared converter from sqlglot AST to Unique IR nodes.

All dialect parsers delegate to this module for the heavy lifting of
converting sqlglot's expression tree into our engine-agnostic IR.
"""

from __future__ import annotations

import dataclasses
import re
from typing import cast

import sqlglot
import sqlglot.expressions as exp

from unique.core.ast_nodes import PassthroughSQL

# Split out of the former single-file converter; see the package __init__.
from unique.core.converter._base import *  # noqa: F401,F403
from unique.core.converter.harvest import (  # noqa: F401
    _coerce_bit_literal,
    _coerce_date_literal,
    _oracle_date_literal,
    wrap_oracle_date_arg,
)
from unique.core.mappings import TSQL_OBJECT_CONTEXT_WORDS, tsql_call_needs_schema
from unique.core.sql_split import qualify_function_calls

# NOTE: moved verbatim from emit.py (audit doc 04 F4 split). The emit.py
# helpers this module calls are imported explicitly at the module tail (after
# the defs) — see emit.py's module docstring for why the cross-family imports
# live at the tail rather than the top.

__all__ = [
    "_emit_passthrough",
    "_emit_passthrough_inline",
]


def _rewrite_select_into_identity(sql: str, read: str) -> exp.Expression | None:
    """Rewrite a T-SQL ``IDENTITY(type, seed, incr)`` in a SELECT-INTO list to a
    ``ROW_NUMBER()`` expression reproducing the same id values, returning the
    transformed sqlglot expression (or None when there is no such call).

    ``IDENTITY(_, seed, incr)`` -> ``((ROW_NUMBER() OVER (ORDER BY (SELECT NULL))
    - 1) * incr + seed)`` (simplified to bare ROW_NUMBER for seed=incr=1). The
    transform is on the AST, not the text (guardrail 2)."""
    try:
        parsed = sqlglot.parse_one(sql, read=read)
    except Exception:  # noqa: BLE001
        return None
    if parsed is None:
        return None

    def _lit(args: list[exp.Expression], idx: int, default: int) -> int:
        if idx < len(args) and isinstance(args[idx], exp.Literal):
            try:
                return int(args[idx].name)
            except ValueError:  # pragma: no cover - non-numeric seed/incr
                return default
        return default

    found = False
    for anon in list(parsed.find_all(exp.Anonymous)):
        if anon.name.upper() != "IDENTITY":
            continue
        args = anon.expressions
        seed, incr = _lit(args, 1, 1), _lit(args, 2, 1)
        base = "ROW_NUMBER() OVER (ORDER BY (SELECT NULL))"
        expr_str = (
            base if (seed, incr) == (1, 1) else f"((({base}) - 1) * {incr} + {seed})"
        )
        anon.replace(sqlglot.parse_one(expr_str, read="tsql"))
        found = True
    return cast(exp.Expression, parsed) if found else None


def _emit_passthrough(node: PassthroughSQL, dialect: str) -> str:
    """Re-transpile a passthrough statement to the target dialect.

    Uses sqlglot directly (it handles ALTER, CREATE INDEX, CREATE SEQUENCE,
    etc. well). On failure, fall back to a commented passthrough so nothing
    is silently lost.
    """
    read = sqlglot_dialect_name(node.source_dialect)
    write = sqlglot_dialect_name(dialect)

    # T-SQL has no data-modifying CTE — an INSERT/UPDATE/DELETE inside a WITH
    # (PostgreSQL's ``WITH ins AS (INSERT … RETURNING) …``) is invalid there;
    # sqlglot re-transpiles it verbatim. Preserve it as a documented carrier.
    if dialect == "tsql":
        # sqlglot drops the WITH arg when a CTE body is DML (``RETURNING … *``
        # defeats its parse), so detect it on scrubbed text: a statement that
        # starts with WITH and has a CTE body opening with a DML verb.
        _scrubbed = re.sub(r"'(?:[^']|'')*'", "''", node.sql)
        if re.match(r"(?is)^\s*WITH\b", _scrubbed) and re.search(
            r"(?is)\bAS\s*\(\s*(?:INSERT|UPDATE|DELETE|MERGE)\b", _scrubbed
        ):
            _cte_reason = (
                "T-SQL has no data-modifying CTE (INSERT/UPDATE/DELETE "
                "inside WITH); statement preserved as a comment"
            )
            return f"-- UNIQUE: {_cte_reason}\n{_comment_block(node.sql)}"

    # MySQL's STRAIGHT_JOIN is INNER JOIN plus a join-order hint no other
    # engine spells — inside a parenthesized join tree it survived the
    # re-transpile verbatim (wave 179; ORA-00907 / error 102 live).
    if (
        node.source_dialect == "mysql"
        and dialect != "mysql"
        and re.search(r"(?i)\bSTRAIGHT_JOIN\b", node.sql)
    ):
        node = dataclasses.replace(
            node,
            sql=re.sub(r"(?i)\bSTRAIGHT_JOIN\b", "INNER JOIN", node.sql),
        )

    # Oracle/PG have no ``ALTER VIEW … AS`` (ORA-00922; PG alters only
    # properties): redefining a view is CREATE OR REPLACE VIEW there
    # (wave 180). T-SQL/MySQL keep ALTER VIEW.
    if (
        node.kind == "ALTER"
        and dialect in ("oracle", "postgresql")
        and re.match(r"(?is)^\s*ALTER\s+VIEW\b.*\bAS\b", node.sql)
    ):
        node = dataclasses.replace(
            node,
            sql=re.sub(
                r"(?is)^\s*ALTER\s+VIEW\b",
                "CREATE OR REPLACE VIEW",
                node.sql,
                count=1,
            ),
        )

    # Running-scan fold: a type/ADD/RENAME/nullability ALTER updates the
    # cross-statement COLUMN_TYPES / COLUMN_NOT_NULL maps in statement order,
    # so a LATER statement (this same table's DROP NOT NULL, another ALTER
    # TYPE) reads the current type/nullability rather than the stale CREATE
    # TABLE snapshot (audit 2026-07-24 N9). Idempotent, so safe if re-emitted.
    if node.kind == "ALTER":
        from unique.core.converter.harvest import fold_alter_into_running_types

        fold_alter_into_running_types(
            node.sql, node.source_dialect, COLUMN_TYPES.get(), COLUMN_NOT_NULL.get()
        )

    # ``ALTER TABLE t MODIFY [COLUMN] c <type>`` changes a column's type; sqlglot
    # passes MODIFY COLUMN through unchanged (unsupported on every write dialect).
    # Each engine spells the type change differently:
    #   Oracle      ALTER TABLE t MODIFY c <type>
    #   PostgreSQL  ALTER TABLE t ALTER COLUMN c TYPE <type>
    #   T-SQL       ALTER TABLE t ALTER COLUMN c <type>
    # Only the simple type-only form is rewritten; a modify carrying an inline
    # constraint (NOT NULL / DEFAULT / …) leaves the tail unmatched and falls
    # through to the generic path.
    if node.kind == "ALTER" and dialect != node.source_dialect:
        m_mod = re.match(
            r"(?is)^\s*ALTER\s+TABLE\s+(\S+)\s+MODIFY\s+(?:COLUMN\s+)?"
            r"(\S+)\s+([A-Za-z0-9_]+(?:\s*\([\d,\s]*\))?)\s*;?\s*$",
            node.sql,
        )
        if m_mod:
            _mt, _mc, _mtype = m_mod.groups()
            _mtype = _portable_types_in_sql(_mtype, dialect)
            if dialect == "oracle":
                return f"ALTER TABLE {_mt} MODIFY {_mc} {_mtype}"
            if dialect == "postgresql":
                return f"ALTER TABLE {_mt} ALTER COLUMN {_mc} TYPE {_mtype}"
            if dialect == "tsql":
                return f"ALTER TABLE {_mt} ALTER COLUMN {_mc} {_mtype}"
            return f"ALTER TABLE {_mt} MODIFY COLUMN {_mc} {_mtype}"

    # T-SQL source ``ALTER TABLE t ALTER COLUMN c <type> [NULL|NOT NULL]`` -> Oracle
    # ``MODIFY (c type [NOT NULL])``. sqlglot renders the Oracle form as an invalid
    # ``ALTER COLUMN c SET DATA TYPE …`` (ORA-01735). A single-statement batch is
    # handled by ``_transpile_alter_column`` (anchored ^…$), but the ALTER inside a
    # multi-statement ``;``-batch reaches the AST/passthrough path, so map it here
    # too. Oracle MODIFY keeps the current nullability, and an explicit NULL on an
    # already-nullable column raises ORA-01451 — so emit NOT NULL only.
    if node.kind == "ALTER" and (node.source_dialect, dialect) == ("tsql", "oracle"):
        try:
            _alt = sqlglot.parse_one(node.sql, read=read)
        except Exception:  # noqa: BLE001
            _alt = None
        _acts = _alt.args.get("actions") if isinstance(_alt, exp.Alter) else None
        if (
            isinstance(_alt, exp.Alter)
            and _acts
            and len(_acts) == 1
            and isinstance(_acts[0], exp.AlterColumn)
        ):
            _ac = _acts[0]
            _dt = _ac.args.get("dtype")
            if _dt is not None:
                _tt = _alt.this.sql(dialect=write)
                _tc = _ac.this.sql(dialect=write)
                _tty = _portable_types_in_sql(_dt.sql(dialect="tsql"), "oracle")
                # Oracle MODIFY keeps the current nullability; an explicit NULL on
                # an already-nullable column raises ORA-01451, so emit NOT NULL only.
                _tnn = " NOT NULL" if _ac.args.get("allow_null") is False else ""
                return f"ALTER TABLE {_tt} MODIFY ({_tc} {_tty}{_tnn})"

    # ``ALTER TABLE t ALTER COLUMN c SET DEFAULT v``: the MySQL/PostgreSQL-native
    # spelling (T-SQL uses ADD DEFAULT … FOR, handled by the guard/default paths,
    # so this stays gated to those sources). Oracle uses MODIFY c DEFAULT v;
    # T-SQL has no ALTER COLUMN … DEFAULT — a default is a named constraint, so
    # ADD CONSTRAINT … DEFAULT v FOR c (name derived from table+column).
    if (
        node.kind == "ALTER"
        and node.source_dialect in ("mysql", "postgresql")
        and dialect != node.source_dialect
    ):
        m_sd = re.match(
            r"(?is)^\s*ALTER\s+TABLE\s+(\S+)\s+ALTER\s+COLUMN\s+(\S+)\s+"
            r"SET\s+DEFAULT\s+(.+?)\s*;?\s*$",
            node.sql,
        )
        if m_sd:
            _t, _c, _v = m_sd.groups()
            if dialect == "oracle":
                return f"ALTER TABLE {_t} MODIFY {_c} DEFAULT {_v}"
            if dialect == "tsql":
                # SET DEFAULT replaces any existing default (MySQL/PG semantics);
                # T-SQL ADD CONSTRAINT would collide (error 1781), so drop the
                # current default constraint (dynamic — name unknown) first.
                _cn = re.sub(r"[^A-Za-z0-9_]", "", _t.split(".")[-1] + "_" + _c)
                return (
                    f"{_tsql_drop_col_default(_t, _c)}; "
                    f"ALTER TABLE {_t} ADD CONSTRAINT DF_{_cn} DEFAULT {_v} FOR {_c}"
                )
            return f"ALTER TABLE {_t} ALTER COLUMN {_c} SET DEFAULT {_v}"

        # PostgreSQL ``ALTER COLUMN c [SET DATA] TYPE t [USING …]`` -> Oracle
        # ``MODIFY c t`` (Oracle has neither the TYPE keyword nor a USING clause;
        # a redundant USING cast IS the target's implicit conversion). The other
        # targets keep the ALTER COLUMN … TYPE spelling (sqlglot handles them).
        if dialect == "oracle":
            m_ty = re.match(
                r"(?is)^\s*ALTER\s+TABLE\s+(\S+)\s+ALTER\s+COLUMN\s+(\S+)\s+"
                r"(?:SET\s+DATA\s+)?TYPE\s+([A-Za-z0-9_]+(?:\s*\([\d,\s]*\))?)"
                r"(?:\s+USING\b.*)?\s*;?\s*$",
                node.sql,
            )
            if m_ty:
                _t2, _c2, _ty2 = m_ty.groups()
                _ty2 = _portable_types_in_sql(_ty2, "oracle")
                return f"ALTER TABLE {_t2} MODIFY {_c2} {_ty2}"

        # PostgreSQL ``ALTER COLUMN c [SET DATA] TYPE t`` -> T-SQL ``ALTER
        # COLUMN c t`` — but T-SQL DEFAULTS an unspecified nullability to NULL,
        # silently dropping a NOT NULL constraint PG's TYPE change preserves
        # (audit 2026-07-24 N9). Re-state the column's known nullability from
        # the running COLUMN_NOT_NULL map; warn when the script never defined
        # the column (a table it did not create in-script). The USING-clause
        # forms have their own handler below (redundant-cast strip / carrier),
        # so match only the plain type-only form here.
        if dialect == "tsql" and node.source_dialect == "postgresql":
            m_tt = re.match(
                r"(?is)^\s*ALTER\s+TABLE\s+(\S+)\s+ALTER\s+COLUMN\s+(\S+)\s+"
                r"(?:SET\s+DATA\s+)?TYPE\s+([A-Za-z0-9_]+(?:\s*\([\d,\s]*\))?)"
                r"\s*;?\s*$",
                node.sql,
            )
            if m_tt:
                return _tsql_alter_type_restating_nullability(*m_tt.groups())

        # ``ALTER COLUMN c DROP DEFAULT``: Oracle spells it MODIFY c DEFAULT NULL.
        # T-SQL has no column-level drop — a default is a named constraint whose
        # (auto-generated) name is unknown here, so look it up and drop it via
        # dynamic SQL (a no-op when the column has no default, matching MySQL/PG).
        m_dd = re.match(
            r"(?is)^\s*ALTER\s+TABLE\s+(\S+)\s+ALTER\s+COLUMN\s+(\S+)\s+"
            r"DROP\s+DEFAULT\s*;?\s*$",
            node.sql,
        )
        if m_dd:
            _td, _cd = m_dd.groups()
            if dialect == "oracle":
                return f"ALTER TABLE {_td} MODIFY {_cd} DEFAULT NULL"
            if dialect == "tsql":
                return _tsql_drop_col_default(_td, _cd)
            return f"ALTER TABLE {_td} ALTER COLUMN {_cd} DROP DEFAULT"

    # ``ALTER TABLE t CHANGE [COLUMN] old new <type>`` renames a column AND
    # changes its type in one MySQL-only statement. Split into a rename + a type
    # change (the column is ``new`` after the rename); only the simple type-only
    # form is handled, a trailing constraint falls through.
    if node.kind == "ALTER" and node.source_dialect == "mysql" and dialect != "mysql":
        m_ch = re.match(
            r"(?is)^\s*ALTER\s+TABLE\s+(\S+)\s+CHANGE\s+(?:COLUMN\s+)?"
            r"(\S+)\s+(\S+)\s+([A-Za-z0-9_]+(?:\s*\([\d,\s]*\))?)\s*;?\s*$",
            node.sql,
        )
        if m_ch:
            _t, _old, _new, _ty = m_ch.groups()
            _ty = _portable_types_in_sql(_ty, dialect)
            if dialect == "oracle":
                return (
                    f"ALTER TABLE {_t} RENAME COLUMN {_old} TO {_new};\n"
                    f"ALTER TABLE {_t} MODIFY {_new} {_ty}"
                )
            if dialect == "postgresql":
                return (
                    f"ALTER TABLE {_t} RENAME COLUMN {_old} TO {_new};\n"
                    f"ALTER TABLE {_t} ALTER COLUMN {_new} TYPE {_ty}"
                )
            if dialect == "tsql":
                _tn = _t.strip('[]"`')
                _on = _old.strip('[]"`')
                _nn = _new.strip('[]"`')
                return (
                    f"EXEC sp_rename '{_tn}.{_on}', '{_nn}', 'COLUMN';\n"
                    f"ALTER TABLE {_t} ALTER COLUMN {_new} {_ty}"
                )

    # Oracle requires DEFAULT before NOT NULL in a column definition (ORA-30649
    # otherwise); sqlglot keeps the source's ``NOT NULL DEFAULT`` order. Reorder
    # it for an ADD/MODIFY column on Oracle.
    if (
        node.kind == "ALTER"
        and dialect == "oracle"
        and re.search(r"(?is)\bNOT\s+NULL\s+DEFAULT\b", node.sql)
    ):
        try:
            rendered = sqlglot.transpile(node.sql, read=read, write=write)
            base = rendered[0] if rendered and rendered[0].strip() else node.sql
        except Exception:  # noqa: BLE001 - keep the source spelling on failure
            base = node.sql
        return re.sub(
            r"(?is)\bNOT\s+NULL\s+DEFAULT\s+('(?:[^']|'')*'|\S+)",
            r"DEFAULT \1 NOT NULL",
            base,
        )

    # MySQL rejects a literal DEFAULT on a TEXT/BLOB/JSON/spatial column (error
    # 1101) — it must be an expression default ``DEFAULT (v)``. Wrap the literal
    # when such a type appears in an ADD/MODIFY column (parenthesizing a literal
    # default is valid for every type on MySQL 8.0.13+, so it is always safe).
    if (
        node.kind == "ALTER"
        and dialect == "mysql"
        and re.search(r"(?i)\bDEFAULT\s+(?!\()", node.sql)
        and re.search(
            r"(?i)\b(?:TINY|MEDIUM|LONG)?TEXT\b|\b(?:TINY|MEDIUM|LONG)?BLOB\b"
            r"|\bJSON\b|\bGEOMETRY\b",
            node.sql,
        )
    ):
        try:
            rendered = sqlglot.transpile(node.sql, read=read, write=write)
            base = rendered[0] if rendered and rendered[0].strip() else node.sql
        except Exception:  # noqa: BLE001 - keep the source spelling on failure
            base = node.sql
        return re.sub(
            r"(?i)\bDEFAULT\s+('(?:[^']|'')*'|-?\d+(?:\.\d+)?|TRUE|FALSE)(?!\s*\()",
            r"DEFAULT (\1)",
            base,
        )

    # MySQL's ENFORCED / NOT ENFORCED on a CHECK constraint: ENFORCED is the
    # default (the constraint IS validated) — strip the keyword for every other
    # engine (identical semantics). NOT ENFORCED (defined but skipped) has no
    # equivalent — strip with a carrier so the semantic loss is documented.
    if (
        node.kind == "ALTER"
        and node.source_dialect == "mysql"
        and dialect != "mysql"
        and re.search(r"(?i)\bENFORCED\b", node.sql)
    ):
        not_enforced = re.search(r"(?i)\bNOT\s+ENFORCED\b", node.sql)
        stripped = re.sub(r"(?i)\s*\b(?:NOT\s+)?ENFORCED\b", "", node.sql).rstrip()
        try:
            rendered = sqlglot.transpile(stripped, read=read, write=write)
            base = rendered[0] if rendered and rendered[0].strip() else stripped
        except Exception:  # noqa: BLE001 - keep the stripped spelling on failure
            base = stripped
        if dialect == "tsql":
            base = base.rstrip().rstrip(";")
        if not_enforced:
            return (
                f"-- UNIQUE: MySQL NOT ENFORCED (a CHECK that is defined but not "
                f"validated) has no {dialect} equivalent; it is enforced here\n"
                f"{base}"
            )
        return base

    # T-SQL cannot DROP a COLUMN that still has a default constraint (error
    # 5074); other engines drop the default with the column. Drop any default
    # constraint on the column first (dynamic — the name is auto-generated),
    # then drop the column. Only the single-column form is rewritten.
    if node.kind == "ALTER" and dialect == "tsql" and node.source_dialect != "tsql":
        m_drop = re.match(
            r"(?is)^\s*ALTER\s+TABLE\s+(\S+)\s+DROP\s+COLUMN\s+(\S+)\s*;?\s*$",
            node.sql,
        )
        if m_drop:
            _tdc, _cdc = m_drop.groups()
            return (
                f"{_tsql_drop_col_default(_tdc, _cdc)}; "
                f"ALTER TABLE {_tdc} DROP COLUMN {_cdc}"
            )

    # MySQL/PostgreSQL FOR SHARE (a shared row lock) has no Oracle form — Oracle
    # SELECT locking is FOR UPDATE (exclusive) only. Drop it and document the
    # absent shared lock.
    if (
        dialect == "oracle"
        and node.source_dialect in ("mysql", "postgresql")
        and re.search(r"(?i)\bFOR\s+SHARE\b", node.sql)
    ):
        _fs = re.sub(r"(?i)\s*\bFOR\s+SHARE\b", "", node.sql)
        try:
            _fsr = sqlglot.transpile(_fs, read=read, write=write)
            _fsb = _fsr[0] if _fsr and _fsr[0].strip() else _fs
        except Exception:  # noqa: BLE001 - keep the stripped spelling on failure
            _fsb = _fs
        return (
            "-- UNIQUE: FOR SHARE (shared row lock) has no Oracle equivalent "
            "(Oracle SELECT locking is FOR UPDATE, exclusive); the shared lock "
            f"is dropped (docs/03-unsupported.md)\n{_fsb}"
        )

    # Oracle FOR UPDATE WAIT <n> (block up to n seconds for the row lock) has no
    # PostgreSQL/MySQL form — they offer only FOR UPDATE (block) and NOWAIT. Drop
    # the WAIT <n> and document the lost bounded-wait timeout.
    if (
        node.source_dialect == "oracle"
        and dialect in ("postgresql", "mysql")
        and re.search(r"(?i)\bFOR\s+UPDATE\b[\s\S]*\bWAIT\s+\d+", node.sql)
    ):
        _stripped = re.sub(r"(?i)\s*\bWAIT\s+\d+\b", "", node.sql)
        try:
            _rendered = sqlglot.transpile(_stripped, read=read, write=write)
            _base = _rendered[0] if _rendered and _rendered[0].strip() else _stripped
        except Exception:  # noqa: BLE001 - keep the stripped spelling on failure
            _base = _stripped
        return (
            f"-- UNIQUE: Oracle FOR UPDATE WAIT <n> (bounded lock wait) has no "
            f"{dialect} equivalent; it blocks with the default behavior "
            f"(docs/03-unsupported.md)\n{_base}"
        )

    # Oracle ``FOR UPDATE OF <col-list>`` names COLUMNS; PostgreSQL/MySQL
    # ``FOR UPDATE OF`` names TABLES/aliases, so the column leaks as an unknown
    # relation (PG 'relation … not found in FROM', MySQL 3568). Oracle's OF only
    # selects which joined table's rows to lock; the portable form drops the OF
    # list (locking every FROM row) and warns about the widened lock scope.
    if node.source_dialect == "oracle" and dialect in ("postgresql", "mysql"):
        try:
            _of_ast = sqlglot.parse_one(node.sql, read=read)
        except Exception:  # noqa: BLE001
            _of_ast = None
        _of_locks = (
            [lk for lk in _of_ast.args.get("locks") or [] if lk.args.get("expressions")]
            if _of_ast is not None
            else []
        )
        if _of_ast is not None and _of_locks:
            # Oracle's OF names COLUMNS; PG/MySQL OF names TABLES/aliases, so the
            # column leaks as an unknown relation. Oracle's OF only selects which
            # joined table's rows to lock — drop the OF list on the AST (locking
            # every FROM row) and warn about the widened lock scope.
            for lk in _of_locks:
                lk.set("expressions", None)
            try:
                _ofb = _of_ast.sql(dialect=write)
            except Exception:  # noqa: BLE001
                _ofb = node.sql
            return (
                "-- UNIQUE: Oracle FOR UPDATE OF <column> selects which table's "
                f"rows to lock; {dialect} FOR UPDATE OF takes table names, so the "
                "OF list is dropped (every row read is locked) "
                "(docs/03-unsupported.md)\n"
                f"{_ofb}"
            )

    # CREATE INDEX on an EXPRESSION (function-based index): Oracle keeps the
    # native single-parens form; MySQL 8.0.13+/PostgreSQL require the expression
    # in DOUBLE parens; T-SQL has no expression index (it needs a computed
    # column), so it degrades with a carrier. A plain column-list index is
    # unaffected (it has no operator/function, or a top-level comma).
    if node.kind == "CREATE INDEX" and dialect != node.source_dialect:
        m_idx = re.match(
            r"(?is)^\s*CREATE\s+(UNIQUE\s+)?INDEX\s+(\S+)\s+ON\s+(\S+)\s*"
            r"\((.*)\)\s*;?\s*$",
            node.sql,
        )
        if m_idx:
            _uni, _iname, _itbl, _itgt = m_idx.groups()
            _itgt = _itgt.strip()
            # The greedy ``\((.*)\)`` also swallows a trailing physical clause
            # (T-SQL ``WITH (FILLFACTOR = 80)``): ``_itgt`` becomes
            # ``a) WITH (FILLFACTOR=80`` and the ``\w+\s*\(`` heuristic mistakes
            # ``WITH (`` for a function call, folding the option INTO the key
            # parens (MySQL 1064). A real single expression has balanced parens
            # that never close before they open — require that, so a malformed
            # capture falls through to the generic path (which drops WITH with a
            # carrier via ``_portable_index``).
            _balanced, _depth = True, 0
            for _ch in _itgt:
                if _ch == "(":
                    _depth += 1
                elif _ch == ")":
                    _depth -= 1
                    if _depth < 0:
                        _balanced = False
                        break
            _balanced = _balanced and _depth == 0
            is_expr = (
                _balanced
                and bool(re.search(r"[*/%+]|\|\||\b\w+\s*\(", _itgt))
                and ("," not in _itgt)
            )
            if is_expr:
                _uni = _uni or ""
                if dialect in ("mysql", "postgresql"):
                    return f"CREATE {_uni}INDEX {_iname} ON {_itbl} (({_itgt}))"
                if dialect == "tsql":
                    return (
                        "-- UNIQUE: T-SQL has no expression/function index; add a "
                        "computed column and index it (docs/03-unsupported.md)\n"
                        f"{_comment_block(node.sql)}"
                    )

    # Oracle CREATE SEQUENCE spells its negatives as one word (NOCYCLE, NOCACHE,
    # NOMAXVALUE, NOMINVALUE) and has an ORDER/NOORDER RAC option no other engine
    # shares. PostgreSQL/T-SQL use two words (NO CYCLE, …) and have no ORDER
    # clause — normalize sqlglot's (verbatim) output for them.
    if (
        node.kind == "CREATE SEQUENCE"
        and dialect in ("postgresql", "tsql")
        and node.source_dialect == "oracle"
    ):
        try:
            rendered = sqlglot.transpile(node.sql, read=read, write=write)
            base = rendered[0] if rendered and rendered[0].strip() else node.sql
        except Exception:  # noqa: BLE001 - keep the source spelling on failure
            base = node.sql
        base = re.sub(r"(?i)\bNO(CYCLE|CACHE|MAXVALUE|MINVALUE)\b", r"NO \1", base)
        base = re.sub(r"(?i)\s*\b(?:NOORDER|ORDER)\b", "", base)
        return base.rstrip().rstrip(";") if dialect == "tsql" else base

    # T-SQL ``SELECT IDENTITY(type, seed, incr) … INTO t2`` adds a numbered
    # identity column to the new table. No engine has an IDENTITY() scalar
    # function, so it leaked as an invalid call. Reproduce the id VALUES with
    # ROW_NUMBER() on the AST (guardrail 2: not a text rewrite); the
    # identity/auto-increment PROPERTY is not portable in a CREATE-TABLE-AS-SELECT,
    # so warn. Self-contained: emits the CTAS (Oracle/MySQL) or SELECT INTO
    # (PG) for the rewritten statement.
    if node.kind == "SELECT INTO" and dialect != "tsql":
        _ident = _rewrite_select_into_identity(node.sql, read)
        if _ident is not None:
            _identity_note = (
                "\n-- UNIQUE: T-SQL IDENTITY() in SELECT INTO reproduced as "
                "ROW_NUMBER (id values match); the identity/auto-increment column "
                "property is not portable in a CREATE TABLE AS SELECT "
                "(docs/03-unsupported.md)"
            )
            _into = _ident.args.get("into") if isinstance(_ident, exp.Select) else None
            _emitted: str
            if dialect in ("oracle", "mysql") and isinstance(_into, exp.Into):
                # Oracle/MySQL have no SELECT-INTO-table; build a CTAS on the AST.
                _ident_sel = _ident.copy()
                _ident_sel.set("into", None)
                _emitted = exp.Create(
                    this=_into.this, kind="TABLE", expression=_ident_sel
                ).sql(dialect=write)
            else:
                _emitted = _ident.sql(dialect=write)  # PG keeps SELECT INTO
            return _emitted + _identity_note

    # T-SQL / PostgreSQL ``SELECT … INTO [TEMP] newtable FROM …`` CREATES a table;
    # Oracle and MySQL have no SELECT-INTO-table form (INTO there targets
    # variables), so rewrite it to CREATE TABLE … AS SELECT (CTAS).
    if node.kind == "SELECT INTO" and dialect in ("oracle", "mysql"):
        m_si = re.match(
            r"(?is)^\s*SELECT\s+(.*?)\s+INTO\s+(TEMP(?:ORARY)?\s+)?"
            r"([\w.\"\[\]#]+)\s+FROM\s+(.*?)\s*;?\s*$",
            node.sql,
        )
        if m_si:
            _sel, _temp, _tbl, _rest = m_si.groups()
            # A T-SQL ``#name`` target is a (session) temp table too.
            _is_temp = bool(_temp) or _tbl.startswith("#")
            _tbl = _tbl.strip('#[]"')
            # Build the CTAS in the SOURCE dialect (TEMPORARY, its own spelling)
            # and let sqlglot map it to the target (Oracle GLOBAL TEMPORARY, …).
            _temp_kw = "TEMPORARY " if _is_temp else ""
            _ctas = f"CREATE {_temp_kw}TABLE {_tbl} AS SELECT {_sel} FROM {_rest}"
            try:
                rendered = sqlglot.transpile(_ctas, read=read, write=write)
                return rendered[0] if rendered and rendered[0].strip() else _ctas
            except Exception:  # noqa: BLE001 - keep the rewritten spelling
                return _ctas

    # PG's NOT VALID (add the constraint but skip validating existing rows) has
    # no equivalent on the other engines, which validate immediately. Strip it —
    # the constraint definition is identical — and document the difference so the
    # loss is never silent.
    if (
        node.kind == "ALTER"
        and node.source_dialect == "postgresql"
        and dialect != "postgresql"
        and re.search(r"(?is)\bNOT\s+VALID\b\s*;?\s*$", node.sql)
    ):
        stripped = re.sub(r"(?is)\s*\bNOT\s+VALID\b\s*;?\s*$", "", node.sql).rstrip()
        try:
            rendered = sqlglot.transpile(stripped, read=read, write=write)
            base = rendered[0] if rendered and rendered[0].strip() else stripped
        except Exception:  # noqa: BLE001 - keep the source spelling
            base = stripped
        base = _portable_types_in_sql(base, dialect)
        return (
            f"-- UNIQUE: {dialect} has no ALTER … NOT VALID; the constraint is "
            f"validated immediately (PostgreSQL defers it)\n{base}"
        )

    # PG's TRUNCATE … RESTART IDENTITY / CASCADE. RESTART IDENTITY is the
    # DEFAULT TRUNCATE behavior on MySQL/Oracle/T-SQL (they always reset the
    # identity), so strip it — faithful, no divergence. CASCADE (also truncate
    # FK-dependent tables) exists on Oracle but not MySQL/T-SQL; strip it there
    # with a carrier so the semantic loss is not silent.
    if (
        dialect != "postgresql"
        and re.search(r"(?is)^\s*TRUNCATE\b", node.sql)
        and re.search(r"(?i)\bRESTART\s+IDENTITY\b|\bCASCADE\b", node.sql)
    ):
        stripped = re.sub(r"(?i)\s+RESTART\s+IDENTITY\b", "", node.sql)
        carrier = ""
        if dialect in ("mysql", "tsql") and re.search(r"(?i)\bCASCADE\b", stripped):
            stripped = re.sub(r"(?i)\s+CASCADE\b", "", stripped)
            carrier = (
                f"-- UNIQUE: TRUNCATE … CASCADE (also truncates FK-dependent "
                f"tables) has no {dialect} equivalent; only this table is "
                "truncated — truncate any dependents explicitly\n"
            )
        try:
            rendered = sqlglot.transpile(stripped, read=read, write=write)
            base = rendered[0] if rendered and rendered[0].strip() else stripped
        except Exception:  # noqa: BLE001 - keep the stripped spelling
            base = stripped
        return (
            carrier + base.rstrip().rstrip(";") if dialect == "tsql" else carrier + base
        )

    # Oracle rejects parenthesized join trees in FROM (ORA-00907). For a
    # pure INNER/CROSS tree the flat CROSS-chain + ANDed WHERE is exactly
    # equivalent (wave 185); outer joins keep the paren carrier.
    if node.kind == "PAREN JOIN" and dialect == "oracle":
        flattened = _flatten_paren_joins(node.sql, node.source_dialect)
        if flattened is not None:
            node = dataclasses.replace(node, sql=flattened)

    # T-SQL/MySQL require an alias on every derived table — PG's bare
    # ``FROM ((SELECT 1 AS x))`` shipped alias-less (error 102 / 1248;
    # wave 198). Inject uq_dtN aliases structurally.
    if node.kind == "PAREN JOIN" and dialect in ("tsql", "mysql"):
        aliased = _alias_bare_derived_tables(node.sql, node.source_dialect)
        if aliased is not None:
            node = dataclasses.replace(node, sql=aliased)

    # PG's ALTER COLUMN … TYPE … USING <expr>: no other engine has the
    # conversion clause (wave 199). A redundant ``USING CAST(col AS
    # type)`` strips (the engine's implicit conversion IS that cast);
    # any other expression keeps a documented carrier.
    if (
        node.kind == "ALTER"
        and node.source_dialect == "postgresql"
        and dialect != "postgresql"
        and re.search(r"(?i)\bALTER\s+COLUMN\b.*\bUSING\b", node.sql)
    ):
        m_red = re.search(
            r"(?is)\bALTER\s+COLUMN\s+(\w+)\s+(?:SET\s+DATA\s+)?(?:TYPE\s+)?"
            r"(\w+(?:\([\d,\s]*\))?)\s+USING\s+"
            r"CAST\s*\(\s*\1\s+AS\s+(\w+(?:\([\d,\s]*\))?)\s*\)\s*$",
            node.sql.rstrip().rstrip(";"),
        )
        if m_red and m_red.group(2).upper() == m_red.group(3).upper():
            node = dataclasses.replace(
                node,
                sql=re.sub(
                    r"(?is)\s+USING\s+CAST.*$", "", node.sql.rstrip().rstrip(";")
                ),
            )
            # The stripped statement is a plain type change: T-SQL must
            # re-state the column's known nullability like the USING-less
            # form (audit 2026-07-24 N9) — same helper, TYPE optional here
            # (the strip accepts the keyword-less spelling).
            if dialect == "tsql":
                m_st = re.match(
                    r"(?is)^\s*ALTER\s+TABLE\s+(\S+)\s+ALTER\s+COLUMN\s+(\S+)\s+"
                    r"(?:SET\s+DATA\s+)?(?:TYPE\s+)?"
                    r"([A-Za-z0-9_]+(?:\s*\([\d,\s]*\))?)\s*;?\s*$",
                    node.sql,
                )
                if m_st:
                    return _tsql_alter_type_restating_nullability(*m_st.groups())
        else:
            return (
                f"-- UNIQUE: {dialect} has no ALTER COLUMN … USING conversion "
                f"expression; convert the data manually. Statement preserved "
                f"as a comment\n{_comment_block(node.sql)}"
            )

    # T-SQL ADD CONSTRAINT ... PRIMARY KEY/UNIQUE with storage clauses:
    # rebuilt directly (sqlglot mangles it into comma-joined actions).
    if node.kind == "ALTER" and node.source_dialect == "tsql":
        rebuilt = _tsql_add_key_constraint(node.sql, dialect)
        if rebuilt is not None:
            return rebuilt

    # PG ``ALTER TABLE t ALTER COLUMN c DROP/SET NOT NULL``: Oracle spells it
    # MODIFY (c [NOT] NULL) without the type; MySQL MODIFY and T-SQL ALTER
    # COLUMN must RE-STATE the type — recovered from the script's own CREATE
    # TABLE via the COLUMN_TYPES harvest (else a documented carrier).
    if (
        node.kind == "ALTER"
        and dialect != "postgresql"
        and (
            _nn := re.search(
                r"(?i)^\s*ALTER\s+TABLE\s+([\w.\"]+)\s+ALTER\s+(?:COLUMN\s+)?"
                r"(\w+)\s+(DROP|SET)\s+NOT\s+NULL\s*;?\s*$",
                node.sql,
            )
        )
    ):
        _nn_tbl_raw, _nn_col, _nn_op = _nn.group(1), _nn.group(2), _nn.group(3)
        _nn_null = "NULL" if _nn_op.upper() == "DROP" else "NOT NULL"
        if dialect == "oracle":
            # PG's DROP/SET NOT NULL is IDEMPOTENT; Oracle's MODIFY raises
            # ORA-01451/-01442 when the column is already in that state —
            # swallow exactly those two codes.
            return (
                "BEGIN\n"
                f"    EXECUTE IMMEDIATE 'ALTER TABLE {_nn_tbl_raw} "
                f"MODIFY ({_nn_col} {_nn_null})';\n"
                "EXCEPTION\n"
                "    WHEN OTHERS THEN\n"
                "        IF SQLCODE NOT IN (-1451, -1442) THEN\n"
                "            RAISE;\n"
                "        END IF;\n"
                "END;"
            )
        _nn_types = (COLUMN_TYPES.get() or {}).get(
            _nn_tbl_raw.split(".")[-1].strip('"').lower(), {}
        )
        _nn_type = _nn_types.get(_nn_col.lower())
        if _nn_type is None:
            return (
                f"-- UNIQUE: {dialect} needs the column's declared type to "
                f"alter its nullability and the script does not define "
                f"{_nn_tbl_raw}.{_nn_col}; original postgresql statement "
                f"preserved:\n{_comment_block(node.sql)}"
            )
        _nn_type = _portable_types_in_sql(_nn_type, dialect)
        if dialect == "mysql":
            return (
                f"ALTER TABLE {_nn_tbl_raw} MODIFY {_nn_col} " f"{_nn_type} {_nn_null}"
            )
        return (
            f"ALTER TABLE {_nn_tbl_raw} ALTER COLUMN {_nn_col} "
            f"{_nn_type} {_nn_null}"
        )
    # ALTER TABLE … ADD COLUMN … GENERATED … AS IDENTITY -> MySQL: the only
    # auto-number form is AUTO_INCREMENT, and MySQL requires the column to be
    # a key — add a UNIQUE index alongside.
    if (
        node.kind == "ALTER"
        and dialect == "mysql"
        and (
            _mid := re.search(
                r"(?i)\bADD\s+(?:COLUMN\s+)?(\w+)\s+(\w+(?:\(\d+\))?)\s+"
                r"GENERATED\s+(?:ALWAYS|BY\s+DEFAULT)\s+AS\s+IDENTITY\b[^,;]*",
                node.sql,
            )
        )
    ):
        _mcol, _mtype = _mid.group(1), _mid.group(2)
        _mrew = (
            node.sql[: _mid.start()]
            + f"ADD COLUMN {_mcol} {_mtype} AUTO_INCREMENT, ADD UNIQUE ({_mcol})"
            + node.sql[_mid.end() :]
        ).rstrip(";\n ")
        return (
            f"-- UNIQUE: MySQL's only identity form is AUTO_INCREMENT (must be "
            f"a key; a UNIQUE index on {_mcol} is added)\n{_mrew}"
        )

    # PostgreSQL CREATE INDEX -> T-SQL: sqlglot's write-side NULLs-distinct
    # emulation wraps unique-index columns in CASE WHEN expressions
    # (invalid in a T-SQL index column list) and keeps PG's nameless form
    # (T-SQL requires a name). Rebuild from the parsed tree.
    # A PG access-method index (GIN/GiST/BRIN — JSONB path ops, full-text,
    # ranges) has no equivalent structure elsewhere, and its base column
    # (JSONB/array) is typically unindexable there anyway. Physical-only:
    # queries still run without it — carry the loss, never ship USING gin.
    if (
        node.kind == "CREATE INDEX"
        and node.source_dialect == "postgresql"
        and dialect != "postgresql"
        and re.search(r"(?i)\bUSING\s+(?:gin|gist|brin|spgist)\b", node.sql)
    ):
        return (
            f"-- UNIQUE: PostgreSQL GIN/GiST/BRIN index has no {dialect} "
            "equivalent (access-method specific); index omitted — queries "
            "run unindexed (docs/03-unsupported.md)\n" + _comment_block(node.sql)
        )
    # An EXPRESSION index over a column that maps to a LOB on the target
    # (PG TEXT -> CLOB / MySQL TEXT) is invalid there (ORA-02327; MySQL 3757):
    # physical-only, so carry the loss. Column types come from the script's
    # own CREATE TABLE (COLUMN_TYPES harvest).
    if (
        node.kind == "CREATE INDEX"
        and node.source_dialect == "postgresql"
        and dialect in ("oracle", "mysql")
        and (
            _xi := re.search(
                r"(?i)\bON\s+([\w.\"]+)\s*\((.+)\)\s*;?\s*$", node.sql.strip()
            )
        )
        and "(" in _xi.group(2)
    ):
        _xi_types = (COLUMN_TYPES.get() or {}).get(
            _xi.group(1).split(".")[-1].strip('"').lower(), {}
        )
        _xi_lob = re.compile(r"(?i)^(TEXT|CLOB|NCLOB|JSON|JSONB|BLOB|BYTEA|IMAGE|XML)")
        if any(
            _xi_lob.match(_xi_types.get(_r.lower(), ""))
            for _r in re.findall(r"\b\w+\b", _xi.group(2))
        ):
            return (
                f"-- UNIQUE: expression index over a LOB-typed column is "
                f"invalid on {dialect} (ORA-02327 / MySQL functional-index "
                "restriction); index omitted — queries run unindexed "
                "(docs/03-unsupported.md)\n" + _comment_block(node.sql)
            )
    if (
        node.kind == "CREATE INDEX"
        and node.source_dialect == "postgresql"
        and dialect in ("tsql", "mysql")
    ):
        rebuilt = _pg_index_rebuild(node.sql, read, dialect)
        if rebuilt is not None:
            # PG's CONCURRENTLY builds the index without locking the table; no
            # other engine has the option (the index is identical). The rebuild
            # already omits it — surface the loss so it is never silent.
            if re.search(r"(?i)\bCONCURRENTLY\b", node.sql):
                rebuilt = (
                    "-- UNIQUE: CONCURRENTLY (PostgreSQL's non-locking index "
                    f"build) has no {dialect} equivalent; the index is created "
                    "with the target's default locking\n" + rebuilt
                )
            rebuilt = _carry_index_nulls_order(node.sql, rebuilt, dialect)
            return rebuilt

    if (
        node.kind in ("SET", "COMMAND")
        and node.source_dialect == "mysql"
        and dialect != "mysql"
        and (
            re.match(
                r"(?is)^\s*SET\s+(?:@@|(?:GLOBAL|SESSION|LOCAL|PERSIST)\b)",
                node.sql,
            )
            or (re.match(r"(?is)^\s*SET\b", node.sql) and "@@" in node.sql)
        )
    ):
        return (
            f"-- UNIQUE: MySQL session setting has no {dialect} equivalent; "
            f"configure the session natively.\n{_comment_block(node.sql)}"
        )

    # MySQL admin commands (FLUSH/ANALYZE/OPTIMIZE/REPAIR/LOCK TABLES…)
    # are engine-local; sqlglot mangles them (``FLUSH AS STATUS``).
    if (
        node.source_dialect == "mysql"
        and dialect != "mysql"
        and re.match(
            r"(?is)^\s*(?:FLUSH|ANALYZE\s+TABLE|OPTIMIZE\s+TABLE|"
            r"REPAIR\s+TABLE|LOCK\s+TABLES|UNLOCK\s+TABLES|"
            r"CHECK\s+TABLE|CHECKSUM\s+TABLE)\b",
            node.sql,
        )
    ):
        return (
            f"-- UNIQUE: MySQL admin command has no {dialect} equivalent; "
            f"run the target's own maintenance.\n{_comment_block(node.sql)}"
        )

    # A TEMPORARY sequence exists only on PostgreSQL (T-SQL/Oracle
    # sequences are permanent objects; the temp-rename would ship an
    # invalid #name) — zero push.
    if (
        node.kind == "CREATE SEQUENCE"
        and dialect != "postgresql"
        and re.search(r"(?i)\bTEMP(?:ORARY)?\s+SEQUENCE\b", node.sql)
    ):
        return (
            f"-- UNIQUE: {dialect} has no TEMPORARY sequences; statement "
            "preserved as a comment\n" + _comment_block(node.sql)
        )

    # MySQL has no CREATE SEQUENCE; sqlglot would emit invalid SQL.
    if dialect == "mysql" and node.kind == "CREATE SEQUENCE":
        return (
            "-- UNIQUE: MySQL has no sequences; use an AUTO_INCREMENT column "
            "instead. Original:\n"
            + _comment_block(_strip_dbo_schema_qualifier(node.sql))
        )

    # PostgreSQL session GUCs (SET name = v / SET name TO v, optionally
    # LOCAL/SESSION) are engine-local knobs with no meaning elsewhere — the
    # largest class of the pg-source baseline (they error on every other
    # engine). Real SQL SET forms (TRANSACTION, CONSTRAINTS, ROLE, SESSION
    # AUTHORIZATION) keep their path.
    if (
        node.kind in ("SET", "COMMAND")
        and node.source_dialect == "postgresql"
        and dialect != "postgresql"
        and re.match(r"(?is)^\s*SET\s+SESSION\s+AUTHORIZATION\b", node.sql)
    ):
        return (
            f"-- UNIQUE: SET SESSION AUTHORIZATION has no {dialect} "
            f"equivalent; switch users natively.\n{_comment_block(node.sql)}"
        )

    if (
        node.kind == "SET"
        and node.source_dialect == "postgresql"
        and dialect != "postgresql"
        and re.match(
            r"(?is)^\s*SET\s+(?:LOCAL\s+|SESSION\s+(?!AUTHORIZATION\b))?"
            r"(?!TRANSACTION\b|CONSTRAINTS\b|ROLE\b|TIME\s+ZONE\b)"
            r"[A-Za-z_][\w.]*\s*(?:=|\bTO\b)",
            node.sql,
        )
    ):
        return (
            f"-- UNIQUE: PostgreSQL session setting has no {dialect} "
            f"equivalent; configure the session natively.\n"
            f"{_comment_block(node.sql)}"
        )

    # USE <db> switches the active database. Valid in MySQL and T-SQL only;
    # PostgreSQL (\\c is a psql meta-command) and Oracle have no SQL form.
    if node.kind == "USE" and dialect in ("postgresql", "oracle"):
        return (
            f"-- UNIQUE: {dialect} has no USE statement; "
            f"connect to the target database/schema instead.\n"
            f"{_comment_block(node.sql)}"
        )

    # PG's ALTER COLUMN SET STORAGE knob: engine-internal storage tuning.
    if node.kind == "PG STORAGE":
        if dialect == "postgresql":
            return node.sql
        return (
            f"-- UNIQUE: PostgreSQL column STORAGE tuning has no {dialect} "
            f"equivalent; statement preserved as a comment:\n"
            f"-- {node.sql}"
        )

    if node.kind == "PG SEARCH CTE":
        # PG 14 recursive-CTE SEARCH/CYCLE ordering — no spelling on any
        # other engine (wave 191).
        if dialect == "postgresql":
            return node.sql
        return (
            f"-- UNIQUE: PostgreSQL's recursive-CTE SEARCH/CYCLE clause has "
            f"no {dialect} equivalent; statement preserved as a comment\n"
            f"{_comment_block(node.sql)}"
        )

    # SAVEPOINT: same spelling everywhere but T-SQL (SAVE TRANSACTION).
    # Modeled as a passthrough because sqlglot mis-parses the statement
    # into an Alias (wave 123).
    if node.kind == "SAVEPOINT":
        name = node.sql.split()[-1]
        if dialect == "tsql":
            return f"SAVE TRANSACTION {name}"
        return f"SAVEPOINT {name}"

    # ROLLBACK TO SAVEPOINT: T-SQL spells it ROLLBACK TRANSACTION <name> (a bare
    # ROLLBACK would undo the whole transaction); MySQL drops the SAVEPOINT
    # keyword; PG/Oracle keep the full form.
    if node.kind == "ROLLBACK_SAVEPOINT":
        name = node.sql.split()[-1]
        if dialect == "tsql":
            return f"ROLLBACK TRANSACTION {name}"
        if dialect == "mysql":
            return f"ROLLBACK TO {name}"
        return f"ROLLBACK TO SAVEPOINT {name}"

    # MySQL has no MERGE. The canonical one-UPDATE/one-INSERT pattern is
    # rewritten as INSERT ... SELECT ... ON DUPLICATE KEY UPDATE (which relies
    # on a UNIQUE/PRIMARY KEY covering the ON columns — noted in a carrier).
    # Anything more complex falls back to a documented comment.
    if node.kind == "MERGE" and dialect == "mysql":
        upsert = _merge_to_mysql_upsert(node.sql, read)
        if upsert is not None:
            return upsert
        commented = _comment_block(node.sql)
        return (
            "-- UNIQUE: MySQL has no MERGE; rewrite as "
            "INSERT ... ON DUPLICATE KEY UPDATE. Original:\n" + commented
        )

    # A CTE on UPDATE/DELETE: no engine besides T-SQL can update *through*
    # the CTE, and Oracle rejects the WITH clause on DML entirely — emit a
    # documented carrier instead of invalid (or silently re-targeted) SQL.
    if node.kind == "CTE DML":
        reason = _cte_dml_unsupported(node.sql, read, dialect)
        if reason is not None:
            return f"-- UNIQUE: {reason} Original:\n{_comment_block(node.sql)}"

    # BEGIN TRANSACTION: T-SQL/PG/MySQL have a statement form (rendered by the
    # sqlglot passthrough below); Oracle starts a transaction implicitly, so drop
    # it with a documented note instead of a bare — and invalid — ``BEGIN``.
    # An access MODE (READ ONLY / READ WRITE) DOES have an Oracle statement:
    # SET TRANSACTION <mode> (must be the transaction's first statement).
    if node.kind == "BEGIN TRANSACTION":
        _tx_mode = re.search(r"(?i)\bREAD\s+(ONLY|WRITE)\b", node.sql)
        if dialect == "oracle":
            if _tx_mode:
                return f"SET TRANSACTION READ {_tx_mode.group(1).upper()}"
            return (
                "-- UNIQUE: BEGIN TRANSACTION dropped -- Oracle starts a "
                "transaction implicitly"
            )
        if _tx_mode and dialect == "mysql":
            # MySQL's BEGIN takes no access mode — the long spelling does.
            return f"START TRANSACTION READ {_tx_mode.group(1).upper()}"
        if _tx_mode and dialect == "tsql":
            return (
                "BEGIN TRANSACTION /* UNIQUE: T-SQL transactions have no "
                f"READ {_tx_mode.group(1).upper()} access mode; started as a "
                "regular transaction (docs/03-unsupported.md) */"
            )
    # SET TRANSACTION ISOLATION LEVEL READ COMMITTED into Oracle: READ
    # COMMITTED is Oracle's DEFAULT, and its SET TRANSACTION must be the
    # transaction's FIRST statement (a following mapped SET TRANSACTION
    # READ ONLY would be ORA-01453) — note the no-op instead.
    if (
        node.kind in ("SET", "SET_OPTION", "COMMAND")
        and dialect == "oracle"
        and node.source_dialect != "oracle"
        and re.match(
            r"(?i)^\s*SET\s+TRANSACTION\s+ISOLATION\s+LEVEL\s+READ\s+COMMITTED\s*;?\s*$",
            node.sql,
        )
    ):
        return (
            "-- UNIQUE: READ COMMITTED is Oracle's default isolation level "
            "(no-op; kept as a note so a following SET TRANSACTION mode "
            "statement can still open the transaction)"
        )

    # PostgreSQL ``SET TRANSACTION [ISOLATION LEVEL <lvl>] [READ ONLY|READ
    # WRITE]`` (N7/B8): MySQL comma-joins the characteristics in one
    # statement; T-SQL keeps the isolation-level statement and strips the
    # access mode with the same documented-note pattern as the BEGIN
    # TRANSACTION branch above; Oracle reuses that branch's access-mode-first
    # rule (it cannot combine ISOLATION LEVEL and an access mode in one
    # statement — READ ONLY is already implicitly serializable there) plus
    # the READ COMMITTED no-op note from the block below.
    if node.kind == "SET TRANSACTION MODE":
        _level = re.search(
            r"(?i)ISOLATION\s+LEVEL\s+"
            r"(READ\s+COMMITTED|READ\s+UNCOMMITTED|REPEATABLE\s+READ|SERIALIZABLE)",
            node.sql,
        )
        level = re.sub(r"\s+", " ", _level.group(1)).upper() if _level else None
        _mode = re.search(r"(?i)\bREAD\s+(ONLY|WRITE)\b", node.sql)
        mode = _mode.group(1).upper() if _mode else None
        if dialect == "postgresql":
            return node.sql
        if dialect == "mysql":
            parts = [
                p
                for p in (
                    f"ISOLATION LEVEL {level}" if level else None,
                    f"READ {mode}" if mode else None,
                )
                if p
            ]
            return "SET TRANSACTION " + ", ".join(parts)
        if dialect == "oracle":
            if mode:
                return f"SET TRANSACTION READ {mode}"
            if level == "READ COMMITTED":
                return (
                    "-- UNIQUE: READ COMMITTED is Oracle's default isolation "
                    "level (no-op; kept as a note so a following SET "
                    "TRANSACTION mode statement can still open the "
                    "transaction)"
                )
            if level == "SERIALIZABLE":
                return "SET TRANSACTION ISOLATION LEVEL SERIALIZABLE"
            return (
                f"-- UNIQUE: Oracle has no {level} isolation level (supports "
                "READ COMMITTED/SERIALIZABLE only); statement dropped. "
                f"Original:\n{_comment_block(node.sql)}"
            )
        # dialect == "tsql"
        if level:
            base = f"SET TRANSACTION ISOLATION LEVEL {level}"
            if mode:
                return (
                    base + " /* UNIQUE: T-SQL SET TRANSACTION has no "
                    f"READ {mode} access mode; access mode dropped "
                    "(docs/03-unsupported.md) */"
                )
            return base
        return (
            f"-- UNIQUE: T-SQL SET TRANSACTION has no READ {mode} access "
            "mode (docs/03-unsupported.md); statement dropped. "
            f"Original:\n{_comment_block(node.sql)}"
        )

    # Oracle hierarchical query: keep as-is for Oracle; for others there is
    # no faithful automatic rewrite, so emit a documented comment.
    if node.kind == "CONNECT BY" and dialect != "oracle":
        commented = _comment_block(node.sql)
        return (
            "-- UNIQUE: Oracle CONNECT BY / START WITH hierarchical query has "
            "no automatic equivalent; rewrite as a WITH RECURSIVE CTE. "
            "Original:\n" + commented
        )

    # Session-variable SELECT INTO: native on the source engine, no
    # cross-dialect equivalent (T-SQL's form is SELECT @a = expr).
    if node.kind == "SELECT INTO VAR":
        if dialect == node.source_dialect:
            return node.sql
        return (
            "-- UNIQUE: session-variable SELECT INTO has no cross-dialect "
            "equivalent; rewrite as the target's assignment form. Original:\n"
            + _comment_block(node.sql)
        )

    # RETURNING + ON CONFLICT in one statement: any strip/rewrite of one
    # clause would ship the other raw — carrier before the per-target
    # RETURNING branches below get a chance to.
    if node.kind == "RETURNING" and dialect != "postgresql":
        try:
            _oc_parsed = sqlglot.parse(node.sql, read=read)
        except Exception:  # noqa: BLE001
            _oc_parsed = []
        if any(e is not None and e.find(exp.OnConflict) for e in _oc_parsed):
            return (
                "-- UNIQUE: INSERT combines RETURNING and ON CONFLICT; "
                f"rewrite as MERGE/upsert with result capture on {dialect}. "
                "Original:\n" + _comment_block(node.sql)
            )

    # T-SQL ``OUTPUT … INTO <table>`` (sqlglot models it as a Returning with an
    # ``into`` arg): the INTO redirect breaks the plain OUTPUT→RETURNING
    # rewrite, leaking the INSERTED./DELETED. qualifier (RETURNING INSERTED.a —
    # PG 'missing FROM-clause entry for "inserted"') and dropping the redirect
    # silently. PostgreSQL has no INTO-redirect in a plain INSERT (it needs a
    # data-modifying CTE), so strip the qualifier + the INTO and keep the
    # RETURNING result, documenting the dropped redirect.
    if node.kind == "RETURNING" and dialect == "postgresql":
        try:
            _into_parsed = sqlglot.parse(node.sql, read=read)
        except Exception:  # noqa: BLE001
            _into_parsed = []
        _had_into = False
        for _e in _into_parsed:
            if _e is None:
                continue
            for _ret in _e.find_all(exp.Returning):
                if _ret.args.get("into") is not None:
                    _had_into = True
                    _ret.set("into", None)
                    for _col in _ret.find_all(exp.Column):
                        if _col.table and _col.table.upper() in ("INSERTED", "DELETED"):
                            _col.set("table", None)
        if _had_into:
            _body = ";\n".join(_e.sql(dialect=write) for _e in _into_parsed if _e)
            return (
                f"{_body}\n-- UNIQUE: T-SQL OUTPUT … INTO <table> redirect has no "
                "PostgreSQL equivalent in a plain INSERT (it needs a "
                "data-modifying CTE); the INTO target is dropped and the "
                "RETURNING result is kept (docs/03-unsupported.md)"
            )

    # Oracle's RETURNING…INTO exists only inside PL/SQL with target
    # variables; top-level SQL keeps the DML effect, the clause strips
    # with a documented note (same contract as the MySQL branch below).
    if node.kind == "RETURNING" and dialect == "oracle":
        m = re.search(r"(?i)\bRETURNING\b\s+(.*?)\s*;?\s*$", node.sql)
        cols = m.group(1).strip() if m else ""
        base = re.sub(r"(?i)\s*\bRETURNING\b.*$", "", node.sql).rstrip()
        try:
            rendered = sqlglot.transpile(base, read=read, write=write)
            if rendered and rendered[0].strip():
                base = rendered[0]
        except Exception:  # noqa: BLE001 - keep the source spelling
            pass
        # The stripped base may still carry PG-only shapes (wave 206):
        # Oracle takes WITH only inside the INSERT's subquery, and has
        # no UPDATE … FROM at all.
        base = re.sub(
            r"(?is)^\s*WITH\s+(.*?)\s+INSERT\s+INTO\s+(\S+)\s+SELECT\b",
            r"INSERT INTO \2 WITH \1 SELECT",
            base,
            count=1,
        )
        if re.search(r"(?is)\bUPDATE\b.*\bSET\b.*\sFROM\s", base):
            return (
                "-- UNIQUE: Oracle has no UPDATE … FROM (rewrite with a "
                "correlated subquery or MERGE) and no top-level RETURNING. "
                "Statement preserved as a comment\n" + _comment_block(node.sql)
            )
        return (
            f"{base};\n-- UNIQUE: Oracle has no top-level RETURNING; "
            f"the statement returned: {cols}"
        )

    # MySQL has no RETURNING/OUTPUT; comment it rather than emit invalid SQL.
    if node.kind == "RETURNING" and dialect == "mysql":
        m = re.search(r"(?i)\bRETURNING\b\s+(.*?)\s*;?\s*$", node.sql)
        cols = m.group(1).strip() if m else ""
        base = re.sub(r"(?i)\s*\bRETURNING\b.*$", "", node.sql).rstrip()
        # The stripped base may still carry PG-only DML shapes (wave
        # 203): UPDATE … FROM is MySQL's multi-table UPDATE, DELETE …
        # USING its multi-table DELETE — and MySQL takes WITH only
        # inside the INSERT's SELECT (wave 222).
        base = re.sub(
            r"(?is)^\s*WITH\s+(.*?)\s+INSERT\s+INTO\s+(\S+)\s+SELECT\b",
            r"INSERT INTO \2 WITH \1 SELECT",
            base,
            count=1,
        )
        # An aliased / self-join ``UPDATE t AS v1 SET … FROM t AS v2`` needs
        # the modeled multi-table rewrite (the bare-name regex below only
        # handles the simplest shape); re-parse and re-emit that base.
        remodeled = _remodel_update_from(base, dialect)
        if remodeled is not None:
            base = remodeled
        else:
            base = re.sub(
                r"(?is)\bUPDATE\s+([\w.`\"]+)\s+SET\s+(.*?)\s+FROM\s+([\w.`\",\s]+?)"
                r"(\s+WHERE\b)",
                r"UPDATE \1, \3 SET \2\4",
                base,
                count=1,
            )
        base = re.sub(
            r"(?is)\bDELETE\s+FROM\s+([\w.`\"]+)\s+USING\s+([\w.`\",\s]+?)"
            r"(\s+WHERE\b)",
            r"DELETE \1 FROM \1, \2\3",
            base,
            count=1,
        )
        return (
            f"{base};\n-- UNIQUE: MySQL has no RETURNING/OUTPUT; "
            f"the statement returned: {cols}"
        )

    try:
        # Parse → quote reserved-word identifiers → generate, so a passthrough
        # CREATE INDEX / ALTER on a reserved name (e.g. ``collation``) is valid.
        parsed = [e for e in sqlglot.parse(node.sql, read=read) if e is not None]
        merge_followups: list[str] = []
        merge_delete_where: str | None = None
        if node.kind == "MERGE" and dialect in ("oracle", "postgresql", "tsql"):
            for e in parsed:
                if not isinstance(e, exp.Merge):
                    continue
                # PG keeps DO NOTHING natively; T-SQL/Oracle carve it out
                # (before the Oracle CASE fold, which composes with it).
                if dialect in ("oracle", "tsql"):
                    reason = _merge_carve_do_nothing(e)
                    if reason is not None:
                        return f"-- UNIQUE: {reason}\n{_comment_block(node.sql)}"
                if dialect in ("oracle", "postgresql"):
                    merge_followups, merge_delete_where, reason = (
                        _merge_extended_clauses(e, dialect)
                    )
                    if reason is not None:
                        return f"-- UNIQUE: {reason}\n{_comment_block(node.sql)}"
        if (
            node.kind == "RETURNING"
            and dialect != "postgresql"
            and any(e.find(exp.OnConflict) for e in parsed)
        ):
            # RETURNING + ON CONFLICT in one statement: the RETURNING
            # passthrough would ship ON CONFLICT raw after OUTPUT.
            return (
                "-- UNIQUE: INSERT combines RETURNING and ON CONFLICT; "
                f"rewrite as MERGE with OUTPUT on {dialect}. Original:\n"
                + _comment_block(node.sql)
            )
        if node.kind == "RETURNING" and dialect == "tsql":
            # T-SQL OUTPUT items must carry the INSERTED./DELETED. prefix;
            # sqlglot renders RETURNING's items bare.
            for e in parsed:
                _prefix_tsql_output_items(cast(exp.Expression, e))
        out = [
            _quote_reserved_identifiers(cast(exp.Expression, e), dialect).sql(
                dialect=write
            )
            for e in parsed
        ]
        if out and out[0].strip():
            result = out[0]
            if node.kind == "CTE DML" and dialect == "tsql":
                # PG's DELETE … USING inside a CTE statement — T-SQL
                # spells the multi-table delete (wave 199).
                result = re.sub(
                    r"(?is)\bDELETE\s+FROM\s+([\w.\[\]\"]+)\s+USING\s+"
                    r"(.+?)(\s+WHERE\b)",
                    r"DELETE \1 FROM \1, \2\3",
                    result,
                    count=1,
                )
            if node.kind == "RETURNING" and dialect == "tsql":
                # sqlglot renders DELETE's OUTPUT before FROM, which not
                # even its own tsql reader accepts; T-SQL wants it after
                # the table.
                result = re.sub(
                    r"(?is)^DELETE\s+(OUTPUT\s.*?)\s+FROM\s+(\S+)",
                    r"DELETE FROM \2 \1",
                    result,
                    count=1,
                )
                # And no AS alias on the UPDATE target (error 156) —
                # T-SQL names the alias and binds it in FROM (wave 197).
                m197 = re.match(
                    r"(?is)^UPDATE\s+([\w.\[\]\"]+)\s+AS\s+(\w+)\s+"
                    r"SET\s+(.*?)\s+FROM\s+(.*)$",
                    result,
                )
                if m197:
                    tbl, alias, sets, rest = m197.groups()
                    result = (
                        f"UPDATE {alias} SET {sets} " f"FROM {tbl} AS {alias}, {rest}"
                    )
            if node.kind == "CREATE INDEX":
                result = _portable_index(result, dialect)
                result = _carry_index_nulls_order(node.sql, result, dialect)
            else:
                result = _portable_types_in_sql(result, dialect)
            if node.kind == "CREATE SEQUENCE" and dialect == "oracle":
                # Drops AS <type> and collapses NO CYCLE -> NOCYCLE etc.
                result = _oracle_sequence_drop_type(result)
            if node.kind == "MERGE":
                # sqlglot keeps the USING subquery's FROM DUAL on engines
                # that have no dual relation, and T-SQL *requires* MERGE to
                # end with ';' (error 10713) — the one statement where the
                # no-';' T-SQL convention does not apply.
                if dialect in ("tsql", "postgresql"):
                    result = re.sub(r"(?i)\s+FROM\s+DUAL\b", "", result)
                if dialect == "oracle":
                    # Oracle requires MERGE ... ON (<condition>) — the parens
                    # are mandatory (ORA-00969 without them).
                    result = _oracle_merge_paren_on(result)
                if merge_delete_where:
                    # Oracle's conditional-DELETE spelling (no sqlglot
                    # grammar): splice the tail after the folded SET list.
                    result = re.sub(
                        r"(?is)(WHEN\s+MATCHED\s+THEN\s+UPDATE\s+SET\s+.*?)"
                        r"(\s+WHEN\s+NOT\s+MATCHED\b|$)",
                        lambda m: (
                            f"{m.group(1)} DELETE WHERE {merge_delete_where}"
                            f"{m.group(2)}"
                        ),
                        result,
                        count=1,
                    )
                for _ms in merge_followups:
                    result = result.rstrip().rstrip(";") + f";\n{_ms}"
                if dialect == "tsql" and not result.rstrip().endswith(";"):
                    result = result.rstrip() + ";"
                if dialect == "tsql":
                    # Scalar-UDF calls inside the sqlglot-emitted MERGE text
                    # never met the shared dbo. decision (error 195 live).
                    def _decide(name: str, prev_word: str | None) -> str | None:
                        if prev_word and prev_word.upper() in TSQL_OBJECT_CONTEXT_WORDS:
                            return None
                        return "dbo." if tsql_call_needs_schema(name) else None

                    result = qualify_function_calls(result, _decide)
            if dialect == "tsql":
                result = _portable_rename_column(result)
                # T-SQL's multi-column drop is ONE DROP COLUMN with a comma
                # list (each engine's normalized form repeats the keyword).
                result = re.sub(r"(?i),\s*DROP\s+COLUMN\s+", ", ", result)
                # sqlglot's tsql writer emits FETCH FIRST/NEXT without the
                # OFFSET clause T-SQL requires (error 102 near 'first').
                result = re.sub(
                    r"(?i)(?<!ROWS )\bFETCH (FIRST|NEXT)\b",
                    r"OFFSET 0 ROWS FETCH \1",
                    result,
                )
            if dialect != "tsql" and node.kind == "ALTER":
                result = _drop_named_default(result)
            if dialect != "oracle":
                result = _portable_alter_add(result, dialect)
            if dialect in ("oracle", "mysql", "postgresql"):
                result = _strip_dbo_schema_qualifier(result)
            # T-SQL has no trailing row-lock clause (FOR UPDATE / FOR SHARE);
            # sqlglot drops it silently. Surface the loss as a documented
            # carrier so the no-silent-loss invariant mirrors it as a warning
            # (Oracle/MySQL keep the clause, so this only bites T-SQL).
            if (
                dialect == "tsql"
                and node.kind == "SELECT"
                and any(e.args.get("locks") for e in parsed)
                and not re.search(r"(?i)\bFOR\s+(?:UPDATE|SHARE)\b", result)
            ):
                result = (
                    "-- UNIQUE: T-SQL has no FOR UPDATE/FOR SHARE row-lock "
                    "clause; lock the rows with a WITH (UPDLOCK, ROWLOCK) "
                    "table hint\n" + result
                )
            return result
    except Exception as e:  # noqa: BLE001 - report and fall back
        logger.warning("passthrough transpile error (%s): %s", node.kind, e)
    return f"-- UNIQUE: Unhandled {node.kind}\n{_comment_block(node.sql)}"


def _emit_passthrough_inline(node: PassthroughSQL, dialect: str) -> str:
    """Re-transpile a constraint fragment for inclusion inside CREATE TABLE.

    Wraps the fragment in a throwaway table so sqlglot will transpile the
    constraint, then extracts it back out. Falls back to the raw fragment.
    """
    read = sqlglot_dialect_name(node.source_dialect)
    write = sqlglot_dialect_name(dialect)
    fragment_sql = node.sql
    # Oracle ``… USING INDEX [<storage>]`` on a PK/UNIQUE names/tunes the backing
    # index — an Oracle storage detail. Every engine backs a PK/UNIQUE with an
    # index by default, so strip the clause (the constraint is identical).
    if node.source_dialect == "oracle" and dialect != "oracle":
        fragment_sql = re.sub(r"(?is)\s+USING\s+INDEX\b.*$", "", fragment_sql)
    # T-SQL has no boolean VALUE type: a comparison whose operand is itself a
    # predicate (``(a IS NULL) != (b IS NULL)`` — the null-XOR CHECK idiom) is
    # a syntax error there. Wrap each predicate operand in CASE WHEN … THEN 1
    # ELSE 0 END via the sqlglot AST (an exact 0/1 encoding of the boolean).
    _ckm = re.match(
        r"(?is)^\s*((?:CONSTRAINT\s+\w+\s+)?CHECK)\s*\((.*)\)\s*$", fragment_sql
    )
    if (
        dialect == "tsql"
        and _ckm
        and re.search(r"(?i)\bIS\s+(?:NOT\s+)?NULL\s*\)?\s*(?:=|!=|<>)", _ckm.group(2))
    ):
        try:
            _ck = sqlglot.parse_one(f"SELECT 1 WHERE {_ckm.group(2)}", read=read)
        except Exception:
            _ck = None
        if _ck is not None:
            _changed = False
            for _cmp in _ck.find_all(exp.EQ, exp.NEQ):
                for _side in ("this", "expression"):
                    _sv = _cmp.args.get(_side)
                    _inner = _sv.this if isinstance(_sv, exp.Paren) else _sv
                    if isinstance(_inner, (exp.Is, exp.Not, exp.Exists)):
                        _cmp.set(
                            _side,
                            exp.Case(
                                ifs=[
                                    exp.If(
                                        this=_inner.copy(),
                                        true=exp.Literal.number(1),
                                    )
                                ],
                                default=exp.Literal.number(0),
                            ),
                        )
                        _changed = True
            _where = _ck.args.get("where")
            if _changed and _where is not None:
                return f"{_ckm.group(1)} ({_where.this.sql(dialect=write)})"
    # An inline INDEX table element (MySQL functional/plain index): native on
    # MySQL; elsewhere an index is physical-only — carry the loss (a separate
    # CREATE INDEX can be written by hand where the target supports the form).
    if node.kind == "INLINE_INDEX":
        if dialect == "mysql":
            return node.sql
        return (
            f"-- UNIQUE: inline INDEX table element has no {dialect} "
            f"equivalent form; index omitted — queries run unindexed. "
            f"Original: {node.sql}"
        )
    # PostgreSQL EXCLUDE has no equivalent on any other engine; keep it on PG,
    # degrade it to a documented carrier elsewhere (never silently drop it).
    if node.kind == "EXCLUDE" and dialect != "postgresql":
        return (
            f"-- UNIQUE: PostgreSQL EXCLUDE constraint has no {dialect} "
            f"equivalent; enforce the exclusion with a trigger. Original: "
            f"{node.sql}"
        )
    if (
        node.source_dialect == "mysql"
        and dialect != "mysql"
        and re.match(r"(?i)\s*(PRIMARY\s+KEY|UNIQUE|KEY|INDEX)\b", fragment_sql)
    ):
        # MySQL prefix indexes (``KEY (a, b(132))``): only MySQL indexes
        # a column prefix — the length has no spelling elsewhere, and
        # indexing the whole column accepts every row the prefix key
        # accepted (wave 166).
        fragment_sql = re.sub(r"(?i)\b(\w+)\s*\(\s*\d+\s*\)", r"\1", fragment_sql)
    if node.source_dialect == "tsql" and dialect != "tsql":
        # T-SQL physical hints in a table constraint (the CLUSTERED keyword,
        # WITH (...) storage options, ON [filegroup]) have no meaning on the
        # other engines, and sqlglot's non-T-SQL writers render them as bogus
        # comma-separated column-list items ("PRIMARY KEY, CLUSTERED (...),
        # WITH (...), ON ..."). Strip them before re-transpiling.
        fragment_sql = re.sub(r"(?i)\b(NON)?CLUSTERED\s+", "", fragment_sql)
        fragment_sql = re.sub(r"(?i)\s*WITH\s*\([^)]*\)", "", fragment_sql)
        fragment_sql = re.sub(r"(?i)\s+ON\s+(?:\[[^\]]+\]|\w+)\s*$", "", fragment_sql)
        # ASC/DESC are index hints inside a PK/UNIQUE column list; sqlglot's
        # T-SQL reader itself rejects them once the CLUSTERED keyword is gone.
        if re.match(r"(?i)\s*(CONSTRAINT|PRIMARY\s+KEY|UNIQUE)\b", fragment_sql):
            fragment_sql = re.sub(r"(?i)\s+(?:ASC|DESC)\b", "", fragment_sql)
    dropped_on_update = False
    if dialect == "oracle":
        # Oracle has NO ``ON UPDATE`` referential action at all (only ON DELETE
        # CASCADE/SET NULL); keeping it ships invalid DDL. Strip it — a
        # documented engine limitation (docs/03-unsupported.md) — and carry the
        # loss so the no-silent-loss scan warns (mirrors the NULLS-FIRST-index
        # drop: silent stripping of an unmappable clause is a defect).
        _stripped = re.sub(
            r"(?i)\s+ON\s+UPDATE\s+(?:CASCADE|SET\s+NULL|SET\s+DEFAULT|"
            r"RESTRICT|NO\s+ACTION)",
            "",
            fragment_sql,
        )
        dropped_on_update = _stripped != fragment_sql
        fragment_sql = _stripped
        # Nor a FK ``MATCH FULL|PARTIAL|SIMPLE`` clause (PG only, ORA-03075);
        # Oracle FKs are always simple-match. Strip it (documented limitation).
        fragment_sql = re.sub(
            r"(?i)\s+MATCH\s+(?:FULL|PARTIAL|SIMPLE)", "", fragment_sql
        )
    try:
        wrapped = f"CREATE TABLE __c__ (x INT, {fragment_sql})"
        out = sqlglot.transpile(wrapped, read=read, write=write)[0]
        inner = out[out.index("(") + 1 : out.rindex(")")]
        # Drop the placeholder "x INT," prefix.
        parts = inner.split(",", 1)
        if len(parts) == 2:
            fragment = parts[1].strip()
            # PostgreSQL and Oracle require an explicit type before a generated
            # column. T-SQL computed columns carry no declared type, so sqlglot
            # emits a typeless definition -- either "col GENERATED ALWAYS AS
            # (...) STORED" or "col AS (...) PERSISTED" -- that those engines
            # reject. Emit a documented comment instead of invalid SQL.
            # MySQL column visibility is engine-local; INVISIBLE has no
            # spelling elsewhere.
            if dialect != "mysql":
                fragment = re.sub(r"(?i)\s+\bINVISIBLE\b", "", fragment)
            is_generated = re.search(
                r"(?i)\bGENERATED\s+ALWAYS\s+AS\b|\bAS\s*\(", fragment
            )
            has_type = re.search(
                r"(?i)^\s*[\w\[\]\".]+\s+"
                r"(INT|INTEGER|BIGINT|SMALLINT|TINYINT|NUMERIC|DECIMAL|FLOAT|"
                r"REAL|DOUBLE|CHAR|VARCHAR|NVARCHAR|TEXT|DATE|TIMESTAMP|"
                r"BOOLEAN|NUMBER|RAW)",
                fragment,
            )
            if (
                dialect in ("postgresql", "oracle", "mysql")
                and is_generated
                and not has_type
            ):
                col_name = fragment.split()[0]
                return (
                    f"-- UNIQUE: {dialect} requires an explicit type for the "
                    f"generated column {col_name}; original computed column: "
                    f"{node.sql}"
                )
            # Oracle and PostgreSQL do not allow NULLS FIRST / NULLS LAST or
            # ASC / DESC inside PRIMARY KEY or UNIQUE constraint column lists
            # (only in ORDER BY / index specs). sqlglot adds the NULLS
            # ordering when emulating T-SQL ordering; ASC/DESC come straight
            # from the SSMS-generated source and are index hints, not
            # semantics, so dropping them is safe.
            if dialect in ("oracle", "postgresql"):
                fragment = re.sub(r"(?i)\s+NULLS\s+(?:FIRST|LAST)", "", fragment)
            if dialect != "tsql" and re.match(
                r"(?i)\s*(CONSTRAINT|PRIMARY\s+KEY|UNIQUE)\b", fragment
            ):
                fragment = re.sub(r"(?i)\s+(?:ASC|DESC)\b", "", fragment)
            # MySQL's named inline key "UNIQUE name (cols)" is only valid
            # MySQL; the portable spelling is CONSTRAINT name UNIQUE (cols).
            if dialect != "mysql":
                fragment = re.sub(
                    r"(?i)^UNIQUE\s+(?:KEY\s+|INDEX\s+)?([`\"\[\]\w]+)\s*\(",
                    r"CONSTRAINT \1 UNIQUE (",
                    fragment,
                )
            # A FOREIGN KEY may REFERENCE a dbo-qualified table. The "dbo" schema
            # is meaningless on the other engines (and would name a non-existent
            # schema/database), exactly as for the table being created, so strip
            # it from the reference target too.
            if dialect in ("oracle", "mysql", "postgresql"):
                fragment = _strip_dbo_from_references(fragment)
            if dropped_on_update:
                # Carrier so the loss surfaces as a warning; Oracle tolerates an
                # inline block comment inside the column/constraint list.
                fragment += (
                    " /* UNIQUE: FK ON UPDATE referential action dropped — "
                    "Oracle has no ON UPDATE FK action (docs/03-unsupported.md) */"
                )
            return fragment
    except Exception as e:  # noqa: BLE001
        logger.warning("constraint transpile error: %s", e)
    return node.sql


# Cross-family imports at the tail (after the defs above) so the mutually
# recursive emit-family modules resolve without namespace injection — see
# emit.py's module docstring.
from unique.core.converter.emit import (  # noqa: E402
    _alias_bare_derived_tables,
    _carry_index_nulls_order,
    _comment_block,
    _cte_dml_unsupported,
    _drop_named_default,
    _flatten_paren_joins,
    _merge_carve_do_nothing,
    _merge_extended_clauses,
    _oracle_merge_paren_on,
    _pg_index_rebuild,
    _portable_alter_add,
    _portable_index,
    _portable_rename_column,
    _portable_types_in_sql,
    _prefix_tsql_output_items,
    _quote_reserved_identifiers,
    _remodel_update_from,
    _tsql_add_key_constraint,
    _tsql_alter_type_restating_nullability,
    _tsql_drop_col_default,
)
