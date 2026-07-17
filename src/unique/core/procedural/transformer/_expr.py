# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Procedural expression rewriter — the curated text-level expression engine.

Extracted from ``base.py`` (the module-growth seam designed 2026-07-11): the
family of SQL-text expression rewriters the procedural transformer applies to
scalar expressions and embedded fragments (function renames, curated
DATEADD/DATEDIFF/STRING_AGG/DECODE handlers, string-concat classification,
niladic/date-format maps, last-identity capture). It is composed into
``ProceduralTransformer`` as ``self._expr`` and reads the narrow context it
needs (source/target dialects, declared string/date variables, the warning
sink and the pair function map) through the owning transformer.

This object is the text path that M3's final step will eventually replace
with IR-first expression handling (see ``docs/TODO.md`` §2, M3-prereq).
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Callable
from typing import TYPE_CHECKING, cast

from unique.core.mappings import (
    CURRENT_TIMESTAMP_EXPR,
    LAST_IDENTITY_EXPR,
    LAST_IDENTITY_SOURCE_FUNCS,
)

if TYPE_CHECKING:  # pragma: no cover - import cycle guard, typing only
    from .base import ProceduralTransformer


# Character cast targets: a CAST to these never fails, so Oracle rejects a
# ``DEFAULT … ON CONVERSION ERROR`` clause on them (used by the TRY_CAST rewrite).
_CHAR_CAST_TYPES = frozenset(
    {"VARCHAR2", "NVARCHAR2", "VARCHAR", "NVARCHAR", "CHAR", "NCHAR", "CLOB", "NCLOB"}
)


class ExpressionRewriter:
    """Text-level expression rewrites for one source→target transform.

    Constructed per :class:`ProceduralTransformer`; ``self._t`` is the owning
    transformer, which provides the rewrite context (``_source``, ``_target``,
    ``_string_vars``, ``_date_vars``, ``_warnings``, ``_get_func_map``).
    """

    def __init__(self, transformer: ProceduralTransformer) -> None:
        self._t = transformer

    _DATE_ADD_START_RE = re.compile(r"DATE_ADD\s*\(", re.IGNORECASE)

    # Current-timestamp expression per dialect (shared mapping layer).
    _NOW_EXPR = CURRENT_TIMESTAMP_EXPR

    #: Niladic "now" spellings that differ per engine in whether they take
    #: parentheses: GETDATE() / NOW() (parens), SYSDATE / SYSTIMESTAMP (none).
    #: SYSTIMESTAMP is listed before SYSDATE so the longer name matches first.
    _NOW_PATTERN = re.compile(
        r"\b(GETDATE\s*\(\s*\)|SYSTIMESTAMP\b(?:\s*\(\s*\))?"
        # SYSDATE with EMPTY parens is the same niladic call (an invalid but
        # real client-dump spelling); SYSDATE(<arg>) stays a user function.
        r"|SYSDATE\s*\(\s*\)|SYSDATE\b(?!\s*\()|NOW\s*\(\s*\))",
        flags=re.IGNORECASE,
    )

    #: Any dialect's UUID-generator spelling; sqlglot canonicalizes them all to
    #: ``UUID()``, which only exists on MySQL (audit 2026-07-08, A4).
    _UUID_PATTERN = re.compile(
        r"(?i)\b(?:NEWID|UUID|SYS_GUID|GEN_RANDOM_UUID)\s*\(\s*\)"
    )

    #: Session-id spellings: every engine has one under a different name
    #: (MySQL CONNECTION_ID shipped as a fake dbo. UDF on T-SQL — wave 171).
    _SESSION_ID_PATTERN = re.compile(
        r"(?i)\b(?:CONNECTION_ID\s*\(\s*\)|PG_BACKEND_PID\s*\(\s*\))|@@SPID\b"
    )

    _SESSION_ID_EXPR = {
        "tsql": "@@SPID",
        "postgresql": "pg_backend_pid()",
        "mysql": "CONNECTION_ID()",
        "oracle": "SYS_CONTEXT('USERENV', 'SID')",
    }

    #: MySQL's ROW_COUNT() — T-SQL/Oracle spell it as a global, not a
    #: function (wave 174). PG's form is GET DIAGNOSTICS (a statement,
    #: not an expression), so PG keeps the source spelling.
    _ROWCOUNT_FN_PATTERN = re.compile(r"(?i)\bROW_COUNT\s*\(\s*\)")

    _ROWCOUNT_FN_EXPR = {"tsql": "@@ROWCOUNT", "oracle": "SQL%ROWCOUNT"}

    #: MySQL's TRUE/FALSE are the numbers 1/0; Oracle PL/SQL types them
    #: BOOLEAN, which cannot assign into NUMBER (PLS-00382 — wave 211).
    #: MySQL declares no PL/SQL BOOLEANs, so the rewrite is safe there.
    _BOOL_LITERAL_RE = re.compile(r"(?i)\b(TRUE|FALSE)\b")

    #: MySQL LIMIT in raw embedded text — Oracle's spelling is
    #: OFFSET/FETCH (which, unlike T-SQL's, needs no ORDER BY; wave 180).
    _LIMIT_TWO_RE = re.compile(r"(?i)\bLIMIT\s+(@?\w+)\s*,\s*(@?\w+)")

    _LIMIT_ONE_RE = re.compile(r"(?i)\bLIMIT\s+(@?\w+)")

    # Oracle date-format pattern -> MySQL/strftime specifier.
    _ORACLE_TO_MYSQL_DATEFMT = [
        ("YYYY", "%Y"),
        ("YY", "%y"),
        ("MONTH", "%M"),
        ("MON", "%b"),
        ("MM", "%m"),
        ("DDD", "%j"),
        ("DD", "%d"),
        ("DY", "%a"),
        ("DAY", "%W"),
        ("HH24", "%H"),
        ("HH12", "%h"),
        ("HH", "%h"),
        ("MI", "%i"),
        ("SS", "%s"),
        ("AM", "%p"),
        ("PM", "%p"),
    ]

    # T-SQL date parts → canonical interval unit name.
    _DATEPART_UNITS = {
        "year": "YEAR",
        "yy": "YEAR",
        "yyyy": "YEAR",
        "quarter": "QUARTER",
        "qq": "QUARTER",
        "q": "QUARTER",
        "month": "MONTH",
        "mm": "MONTH",
        "m": "MONTH",
        "day": "DAY",
        "dd": "DAY",
        "d": "DAY",
        "week": "WEEK",
        "wk": "WEEK",
        "ww": "WEEK",
        "hour": "HOUR",
        "hh": "HOUR",
        "minute": "MINUTE",
        "mi": "MINUTE",
        "n": "MINUTE",
        "second": "SECOND",
        "ss": "SECOND",
        "s": "SECOND",
    }

    @classmethod
    def _replace_oracle_date_add(cls, sql: str) -> str:
        """Replace sqlglot's MySQL-style DATE_ADD(d, n, 'UNIT') with Oracle arithmetic.

        Uses paren-depth tracking to correctly split nested arguments.
        """
        result: list[str] = []
        i = 0
        while True:
            m = cls._DATE_ADD_START_RE.search(sql, i)
            if not m:
                result.append(sql[i:])
                break
            result.append(sql[i : m.start()])
            # Walk forward to find the matching closing paren.
            j = m.end()
            depth = 1
            while j < len(sql) and depth > 0:
                if sql[j] == "(":
                    depth += 1
                elif sql[j] == ")":
                    depth -= 1
                j += 1
            inner = sql[m.end() : j - 1]
            # Split inner at top-level commas.
            args: list[str] = []
            d = 0
            start = 0
            for k, ch in enumerate(inner):
                if ch == "(":
                    d += 1
                elif ch == ")":
                    d -= 1
                elif ch == "," and d == 0:
                    args.append(inner[start:k].strip())
                    start = k + 1
            args.append(inner[start:].strip())
            if len(args) == 3:
                date_expr, amount, unit = args[0], args[1], args[2].strip("'").upper()
                if unit in ("SECOND", "MINUTE", "HOUR"):
                    repl = f"({date_expr} + NUMTODSINTERVAL({amount}, '{unit}'))"
                elif unit == "DAY":
                    repl = f"({date_expr} + {amount})"
                elif unit == "WEEK":
                    repl = f"({date_expr} + ({amount}) * 7)"
                elif unit == "MONTH":
                    repl = f"ADD_MONTHS({date_expr}, {amount})"
                elif unit == "QUARTER":
                    repl = f"ADD_MONTHS({date_expr}, ({amount}) * 3)"
                elif unit == "YEAR":
                    repl = f"ADD_MONTHS({date_expr}, ({amount}) * 12)"
                else:
                    repl = f"DATE_ADD({inner})"
            else:
                repl = f"DATE_ADD({inner})"
            result.append(repl)
            i = j
        return "".join(result)

    def _oracle_function_fixes(self, sql: str) -> str:
        """Rewrite T-SQL functions Oracle lacks a direct spelling for."""
        # Oracle forbids ``AS`` before a *table* alias (``FROM t AS x`` -> ORA-00907;
        # only column aliases may use AS). sqlglot drops it for a top-level query,
        # but an IR cross-table UPDATE keeps it in its subquery — strip it here.
        sql = re.sub(
            r"(?i)\b(FROM|JOIN)\s+([A-Za-z_]\w*)\s+AS\s+([A-Za-z_]\w*)",
            r"\1 \2 \3",
            sql,
        )
        # T-SQL ``INSERT … OUTPUT inserted.<col> INTO @tablevar`` becomes a bare
        # ``RETURNING <expr>`` with no INTO. Oracle RETURNING can only target a
        # scalar/collection, never a table, so drop it and document: the GTT (the
        # table variable's replacement) must be populated by hand. A legitimate
        # ``RETURNING … INTO <var>`` (with INTO) is left untouched.
        sql = re.sub(
            r"(?i)\s+RETURNING\s+((?:(?!\bINTO\b)[^;])+?)\s*(?=;|$)",
            r"  /* UNIQUE: OUTPUT \1 dropped — populate the temp table manually */",
            sql,
        )
        # VARCHAR(MAX)/NVARCHAR(MAX) (and the sqlglot VARCHAR2(MAX) spelling) as a
        # CAST target in an expression is invalid Oracle; use a bounded
        # VARCHAR2/NVARCHAR2 (as for column/param types).
        sql = re.sub(r"(?i)\bNVARCHAR2?\s*\(\s*MAX\s*\)", "NVARCHAR2(2000)", sql)
        sql = re.sub(r"(?i)\bVARCHAR2?\s*\(\s*MAX\s*\)", "VARCHAR2(4000)", sql)

        # A character CAST needs a length in Oracle (`CAST(x AS VARCHAR2)` ->
        # ORA-00906). sqlglot keeps CONVERT(VARCHAR(n), …)'s length, but a later
        # concat re-pass drops it; restore a bounded one.
        def _char_cast_size(m: re.Match[str]) -> str:
            base = m.group(1)
            b = base.upper()
            if b in ("VARCHAR2", "VARCHAR"):
                size = "4000"
            elif b == "NCHAR":
                size = "1000"
            else:  # NVARCHAR2/NVARCHAR/CHAR
                size = "2000"
            return f"AS {base}({size}))"

        sql = re.sub(r"(?i)\bAS\s+(N?VARCHAR2?|N?CHAR)\s*\)", _char_cast_size, sql)

        # TRY_CAST(x AS type) -> CAST(x AS type DEFAULT NULL ON CONVERSION ERROR)
        # (Oracle 12.2+): returns NULL on a bad value instead of raising. Oracle
        # rejects the DEFAULT clause for a character target (a cast to VARCHAR2
        # never fails), so a character TRY_CAST is a plain CAST.
        def _try_cast(m: re.Match[str]) -> str:
            val, typ = m.group(1), m.group(2)
            base = typ.split("(")[0].strip().upper()
            if base in _CHAR_CAST_TYPES:
                # A character CAST needs a length in Oracle (CAST(x AS VARCHAR2)
                # -> ORA-00906); CLOB/NCLOB take none.
                if "(" not in typ and base not in ("CLOB", "NCLOB"):
                    typ = f"{typ.strip()}({'2000' if base.startswith('N') else '4000'})"
                return f"CAST({val} AS {typ})"
            return f"CAST({val} AS {typ} DEFAULT NULL ON CONVERSION ERROR)"

        sql = re.sub(
            r"(?i)\bTRY_CAST\s*\(\s*(.+?)\s+AS\s+"
            r"([A-Za-z_]\w*(?:\s*\(\s*\d+(?:\s*,\s*\d+)?\s*\))?)\s*\)",
            _try_cast,
            sql,
        )
        # SHA256(x) / SHA2(x, 256) -> RAWTOHEX(STANDARD_HASH(x, 'SHA256')): Oracle
        # STANDARD_HASH returns RAW, so RAWTOHEX gives the hex string T-SQL yields.
        sql = self._rewrite_balanced_call(
            sql, "SHA256", lambda inner: f"RAWTOHEX(STANDARD_HASH({inner}, 'SHA256'))"
        )
        sql = self._rewrite_balanced_call(
            sql,
            "SHA2",
            lambda inner: f"RAWTOHEX(STANDARD_HASH({inner.rsplit(',', 1)[0].strip()},"
            " 'SHA256'))",
        )
        # A stray sqlglot TIME_STR_TO_TIME / DATE_STR_TO_DATE wrapper around an
        # already-temporal operand is spurious on Oracle — unwrap it.
        sql = self._rewrite_balanced_call(sql, "TIME_STR_TO_TIME", lambda inner: inner)
        sql = self._rewrite_balanced_call(sql, "DATE_STR_TO_DATE", lambda inner: inner)
        # EXTRACT(EPOCH FROM x): Oracle has no EPOCH — seconds since the Unix epoch
        # is (x_as_date - 1970-01-01) * 86400.
        sql = self._rewrite_balanced_call(
            sql,
            "EXTRACT",
            lambda inner: (
                f"((CAST({inner[len('EPOCH FROM'):].strip()} AS DATE)"
                " - DATE '1970-01-01') * 86400)"
                if inner.strip().upper().startswith("EPOCH FROM")
                else f"EXTRACT({inner})"
            ),
        )
        return sql

    @staticmethod
    def _rewrite_balanced_call(sql: str, name: str, build: Callable[[str], str]) -> str:
        """Replace ``name(<balanced>)`` calls, passing the inner text to *build*."""
        out: list[str] = []
        i = 0
        pat = re.compile(rf"(?i)\b{name}\s*\(")
        while True:
            m = pat.search(sql, i)
            if not m:
                out.append(sql[i:])
                break
            out.append(sql[i : m.start()])
            depth, j = 1, m.end()
            while j < len(sql) and depth:
                depth += (sql[j] == "(") - (sql[j] == ")")
                j += 1
            out.append(build(sql[m.end() : j - 1]))
            i = j
        return "".join(out)

    def _to_oracle_row_ref(self, sql: str) -> str:
        """Map a MySQL/PostgreSQL-source ``NEW.``/``OLD.`` row reference to
        Oracle's ``:NEW.``/``:OLD.`` (PLS-00201 otherwise). The negative
        lookbehind leaves an already-``:``-prefixed reference untouched."""
        sql = re.sub(r"(?i)(?<!:)\bNEW\s*\.\s*", ":NEW.", sql)
        sql = re.sub(r"(?i)(?<!:)\bOLD\s*\.\s*", ":OLD.", sql)
        return sql

    def _unwrap_spurious_hash_format(self, sql: str) -> str:
        """Undo sqlglot's misreading of a T-SQL hash-stringify CONVERT.

        ``CONVERT(varchar(max), HASHBYTES('SHA2_256', x), 2)`` stringifies a
        hash; sqlglot maps HASHBYTES to SHA256 but treats the style code ``2``
        as a date format, producing e.g.
        ``CAST(TO_CHAR(SHA256(x), 'YY.MM.DD') AS VARCHAR(MAX))``. The hash
        already returns a hex/text value, so strip the spurious TO_CHAR/format
        and the (MAX) cast, leaving the bare hash call.
        """
        # CAST(TO_CHAR(<inner>, '...') AS VARCHAR(MAX)) -> <inner>
        sql = re.sub(
            r"(?i)CAST\s*\(\s*TO_CHAR\s*\(\s*(.+?)\s*,\s*'[^']*'\s*\)\s*"
            r"AS\s+VARCHAR\s*\(\s*MAX\s*\)\s*\)",
            r"\1",
            sql,
        )
        # Bare TO_CHAR(<hash>, '...') with no surrounding cast.
        sql = re.sub(
            r"(?i)TO_CHAR\s*\(\s*(SHA\d*\s*\(.+?\))\s*,\s*'[^']*'\s*\)",
            r"\1",
            sql,
        )
        return sql

    # direct MySQL equivalents that sqlglot knows, but the procedural pipeline
    # captures expressions as text that often parses as an opaque Command. Re-
    # transpile the fragment from T-SQL to MySQL so CONVERT(t, x) -> CAST(x AS
    # t), CONVERT(date, s, 120) -> STR_TO_DATE(...), HASHBYTES('SHA2_256', x)
    # -> SHA2(x, 256), and similar conversions are applied. The '+' string
    # concatenation is handled separately afterwards (sqlglot can't tell
    # arithmetic from concat without type info).
    def _mysql_normalize_funcs(self, sql: str) -> str:
        import sqlglot
        from sqlglot import exp

        # Cheap guard: only worth the round-trip when a known T-SQL-ism is
        # present. Keeps already-valid fragments byte-for-byte identical.
        if not re.search(r"(?i)\b(CONVERT|HASHBYTES|DATEPART|DATENAME)\s*\(", sql):
            return sql

        def normalize(tree: exp.Expression) -> exp.Expression:
            # T-SQL hashes the binary with HASHBYTES and stringifies it with an
            # outer CONVERT(<type>, ..., 2) (style 2 = hex, no 0x). sqlglot maps
            # HASHBYTES('SHA2_256', x) to SHA2(x, 256) — which already returns a
            # hex string — but mis-handles the wrapping CONVERT's style code,
            # emitting a spurious DATE_FORMAT. Drop the CONVERT wrapper around a
            # hash so just SHA2(...) remains.
            # If the CONVERT is the whole expression (e.g. RETURN CONVERT(...)),
            # it is the tree root and Node.replace() can't substitute it, so
            # return the inner expression directly.
            if isinstance(tree, exp.Convert):
                expr = tree.args.get("expression")
                if expr is not None and (
                    isinstance(expr, exp.SHA2) or expr.find(exp.SHA2)
                ):
                    return cast(exp.Expression, expr.copy())
            wrappers = [
                conv
                for conv in tree.find_all(exp.Convert)
                if (expr := conv.args.get("expression")) is not None
                and (isinstance(expr, exp.SHA2) or expr.find(exp.SHA2))
            ]
            for conv in wrappers:
                expr = conv.args.get("expression")
                if expr is not None:
                    conv.replace(expr.copy())
            return tree

        for wrap, is_wrapped in ((sql, False), (f"SELECT {sql}", True)):
            try:
                tree = sqlglot.parse_one(wrap, read="tsql")
            except Exception:
                continue
            if isinstance(tree, exp.Command):
                continue
            try:
                out = (
                    normalize(cast(exp.Expression, tree))
                    .sql(dialect="mysql")
                    .rstrip()
                    .rstrip(";")
                )
            except Exception:
                continue
            if is_wrapped and not sql.upper().startswith("SELECT"):
                if out.upper().startswith("SELECT "):
                    return out[len("SELECT ") :].strip()
                continue
            return out
        return sql

    # MySQL has no string ``+`` operator and no ``N'...'`` literal prefix.
    # T-SQL uses ``+`` for both arithmetic and string concatenation, so the
    # operator alone is ambiguous; we treat a ``+`` chain as concatenation
    # only when one of its operands is a string literal (the unambiguous
    # signal), rewriting the whole chain to ``CONCAT(...)`` and dropping any
    # ``N`` prefixes. Pure arithmetic (``a + b``, ``x + 1``) is left intact.
    def _mysql_pipes_to_concat(self, sql: str) -> str:
        """Oracle/PG ``||`` concatenation for the MySQL target, where ``||``
        is logical OR — leaking it was *silent semantic corruption* (the
        chain evaluated to 0/1). Round-trips the fragment through sqlglot's
        postgres reader, whose DPipe emits as CONCAT under the mysql writer;
        conservatively skipped when the fragment does not survive (every
        input word/number atom must still be present in the output)."""
        if self._t._source not in ("oracle", "postgresql") or "||" not in sql:
            return sql
        # Only act on a || outside string literals.
        blanked = re.sub(r"'(?:[^']|'')*'", "''", sql)
        if "||" not in blanked:
            return sql
        # The postgres reader turns SELECT ... INTO into CREATE TABLE AS.
        if re.search(r"(?i)\bINTO\b", sql):
            return sql
        import sqlglot

        wrapped = False
        tree = None
        try:
            tree = sqlglot.parse_one(
                sql, read="postgres", error_level=sqlglot.ErrorLevel.RAISE
            )
        except Exception:  # noqa: BLE001 - fall through to the wrapped form
            try:
                tree = sqlglot.parse_one(
                    f"SELECT {sql}",
                    read="postgres",
                    error_level=sqlglot.ErrorLevel.RAISE,
                )
                wrapped = True
            except Exception:  # noqa: BLE001 - not an expression; keep as-is
                return sql
        try:
            out = tree.sql(dialect="mysql")
        except Exception:  # noqa: BLE001 - keep the original on any failure
            return sql
        if wrapped:
            if not out.upper().startswith("SELECT "):
                return sql
            out = out[len("SELECT ") :].rstrip().rstrip(";")

        def atoms(s: str) -> Counter[str]:
            return Counter(re.findall(r"[A-Za-z_]\w*|\d+", s.lower()))

        # No input atom may be lost (a lossy re-parse drops arguments —
        # audit D8); additions (CONCAT itself) are fine.
        lost = atoms(sql) - atoms(out)
        if lost:
            return sql
        return out

    def _mysql_trunc(self, sql: str) -> str:
        """Oracle TRUNC for MySQL (mirrors the T-SQL target's heuristic):
        two-arg TRUNC is numeric truncation (TRUNCATE); one-arg TRUNC is the
        strip-the-time date idiom (DATE) when the argument looks like a date
        (a known date variable or a fecha/date-named expression), numeric
        truncation otherwise."""
        sql = re.sub(
            r"(?is)\bTRUNC\s*\(\s*([^(),]+?)\s*,\s*([^(),]+?)\s*\)",
            r"TRUNCATE(\1, \2)",
            sql,
        )

        def trunc1(m: re.Match[str]) -> str:
            arg = m.group(1).strip()
            if arg in self._t._date_vars or re.search(
                r"(?i)\b(?:fecha|date|fec|sysdate|now|current_timestamp)", arg
            ):
                return f"DATE({arg})"
            return f"TRUNCATE({arg}, 0)"

        return re.sub(r"(?is)\bTRUNC\s*\(\s*([^(),]+?)\s*\)", trunc1, sql)

    def _mysql_string_concat(self, sql: str) -> str:
        return self._rewrite_string_concat(sql, "mysql")

    def _pg_string_concat(self, sql: str) -> str:
        return self._rewrite_string_concat(sql, "postgresql")

    def _rewrite_string_concat(self, sql: str, target: str) -> str:
        """Rewrite T-SQL string `+` concatenation for the target dialect.

        T-SQL overloads `+` for both arithmetic and string concatenation. When
        an operand is (or is known to be) a string, the chain is concatenation
        and must use the target's construct: `CONCAT(...)` for MySQL, the `||`
        operator for PostgreSQL (where `+` on text is an error). Numeric `+`
        chains are left untouched.
        """
        import sqlglot
        from sqlglot import exp

        read = "mysql" if target == "mysql" else "postgres"

        def is_string_atom(n: exp.Expression) -> bool:
            return isinstance(n, exp.National) or (
                isinstance(n, exp.Literal) and bool(n.args.get("is_string"))
            )

        def denationalize(n: exp.Expression) -> exp.Expression:
            if isinstance(n, exp.National):
                return exp.Literal.string(n.this)
            for nat in list(n.find_all(exp.National)):
                nat.replace(exp.Literal.string(nat.this))
            return n

        def flatten_add(n: exp.Expression, parts: list[exp.Expression]) -> None:
            if isinstance(n, exp.Add):
                flatten_add(cast(exp.Expression, n.left), parts)
                flatten_add(cast(exp.Expression, n.right), parts)
            else:
                parts.append(n)

        def is_known_string_var(n: exp.Expression) -> bool:
            # A bare identifier known (from its DECLARE/parameter type) to be a
            # string variable signals concatenation even with no string literal
            # present (e.g. SHA2(@a + @b) over two text columns).
            if isinstance(n, exp.Column) and not n.table:
                return n.name in self._t._string_vars
            return False

        # Functions whose result is numeric or temporal: a string literal
        # among their arguments says nothing about the '+' chain's type.
        # Without this, INSTR(x, ',') + 1 shipped as CONCAT(LOCATE(...), 1)
        # — which compiles and silently yields '31' instead of 4.
        non_string_funcs = frozenset(
            {
                "DATEDIFF",
                "TIMESTAMPDIFF",
                "DATEADD",
                "DATE_ADD",
                "DATE_SUB",
                "ADDDATE",
                "SUBDATE",
                "INSTR",
                "LOCATE",
                "POSITION",
                "STRPOS",
                "STR_POSITION",  # sqlglot's canonical name for LOCATE/INSTR
                "CHARINDEX",
                "TO_NUMBER",
                "TO_DATE",
                "STR_TO_DATE",
                "NUMTODSINTERVAL",
                "NUMTOYMINTERVAL",
                "EXTRACT",
                "LENGTH",
                "CHAR_LENGTH",
                "DATALENGTH",
                "LEN",
                "ROUND",
                "TRUNC",
                "TRUNCATE",
                "MOD",
                "FLOOR",
                "CEIL",
                "CEILING",
                "ABS",
                "SIGN",
                "MONTHS_BETWEEN",
                "YEAR",
                "MONTH",
                "DAY",
                "UNIX_TIMESTAMP",
                "COUNT",
            }
        )

        def func_name(n: exp.Expression) -> str:
            if isinstance(n, exp.Anonymous):
                return str(n.this).upper()
            if isinstance(n, exp.Func):
                return n.sql_name().upper()
            return ""

        def literal_neutralized(lit: exp.Expression, root: exp.Expression) -> bool:
            node = lit.parent
            while isinstance(node, exp.Expression):
                # INTERVAL '7 DAY' / NUMTODSINTERVAL(n, 'SECOND'): temporal
                # arithmetic — the quoted payload says nothing about the
                # '+' chain's type. Without this, DATEADD output turned
                # into '||' and the re-emit dropped a negative sign
                # (silently ADDING a month instead of subtracting).
                if isinstance(node, exp.Interval):
                    return True
                if func_name(node) in non_string_funcs:
                    return True
                if isinstance(node, exp.Cast) and not node.to.is_type(
                    *exp.DataType.TEXT_TYPES
                ):
                    return True
                if node is root:
                    break
                node = node.parent
            return False

        def has_string_operand(parts: list[exp.Expression]) -> bool:
            for p in parts:
                if is_string_atom(p) or is_known_string_var(p):
                    return True
                for lit in p.find_all(exp.Literal, exp.National):
                    if isinstance(lit, exp.Literal) and not lit.args.get("is_string"):
                        continue
                    if not literal_neutralized(lit, p):
                        return True
            return False

        def build_concat(parts: list[exp.Expression]) -> exp.Expression:
            if target == "mysql":
                return cast(exp.Expression, exp.func("CONCAT", *parts))
            # PostgreSQL: chain with the || (DPipe) operator.
            node = parts[0]
            for nxt in parts[1:]:
                node = exp.DPipe(this=node, expression=nxt)
            return node

        def convert(node: exp.Expression) -> exp.Expression:
            if isinstance(node, exp.Add):
                parts: list[exp.Expression] = []
                flatten_add(node, parts)
                if has_string_operand(parts):
                    new_parts = [convert(denationalize(p.copy())) for p in parts]
                    return build_concat(new_parts)
            for key, value in list(node.args.items()):
                if isinstance(value, exp.Expression):
                    node.set(key, convert(value))
                elif isinstance(value, list):
                    node.set(
                        key,
                        [
                            convert(c) if isinstance(c, exp.Expression) else c
                            for c in value
                        ],
                    )
            return node

        # Only attempt the rewrite when a '+' is present at all (the parse cost
        # is otherwise wasted). A string literal OR a known string variable is
        # what later marks a chain as concatenation; require '+' plus one of
        # those signals so already-numeric fragments are skipped cheaply.
        if "+" not in sql:
            return sql
        if "'" not in sql and not self._t._string_vars:
            return sql
        # The raw SQL may be a complete statement (SELECT ... FROM ...) or a
        # bare expression (the right-hand side of a SET). Try the statement
        # form first; if it doesn't parse — or parses as an opaque Command,
        # which sqlglot falls back to for things like ``REPLACE ( ... )`` and
        # which exposes no Add nodes to rewrite — wrap it in a SELECT so a lone
        # expression becomes parseable, and unwrap afterwards.
        wrapped = False
        tree = None
        try:
            parsed = sqlglot.parse_one(sql, read=read)
            if not isinstance(parsed, exp.Command):
                tree = parsed
        except Exception:
            tree = None
        if tree is None:
            try:
                tree = sqlglot.parse_one(f"SELECT {sql}", read=read)
                wrapped = True
            except Exception:
                return sql
        try:
            tree = convert(cast(exp.Expression, tree))
            rendered = tree.sql(dialect=read)
        except Exception:
            return sql
        if wrapped and rendered.upper().startswith("SELECT "):
            return rendered[len("SELECT ") :].rstrip().rstrip(";")
        return rendered

    def _transform_functions_in_sql(self, sql: str) -> str:
        """Transform function names in raw SQL text.

        Applies all mappings in a single pass (alternation regex) so that a
        replacement's output cannot be re-matched by a later mapping. Only
        function-call positions (name followed by '(') are rewritten, and
        commented placeholder mappings are skipped.
        """
        sql = self._transform_niladic_datetime(sql)

        func_map = {
            old: new
            for old, new in self._t._get_func_map().items()
            if not new.startswith("--") and old.upper() != new.upper()
        }
        if not func_map:
            return sql

        # Longest names first to avoid partial-overlap surprises.
        names = sorted(func_map, key=len, reverse=True)
        pattern = re.compile(
            r"\b(" + "|".join(re.escape(n) for n in names) + r")\b(\s*\()",
            flags=re.IGNORECASE,
        )

        lookup = {k.upper(): v for k, v in func_map.items()}

        def repl(m: re.Match[str]) -> str:
            return lookup[m.group(1).upper()] + m.group(2)

        return pattern.sub(repl, sql)

    def _map_now_in_sql(self, sql: str) -> str:
        """Replace any niladic current-timestamp spelling with the target's
        form. Shared by the raw-text rewriter and the embedded-DML path so a
        SYSTIMESTAMP in an UPDATE doesn't leak an invalid ``SYSTIMESTAMP()``."""
        target_expr = self._NOW_EXPR.get(self._t._target)
        if not target_expr:
            return sql
        return self._map_uuid_in_sql(self._NOW_PATTERN.sub(target_expr, sql))

    def _map_uuid_in_sql(self, sql: str) -> str:
        """Replace any UUID-generator spelling with the target's (sourced from
        the shared ``mappings.UUID_FUNCTION`` table — never a private copy).
        A deterministic name-only rewrite; M3 subsumes it when embedded DML
        goes through the IR converter."""
        from unique.core.mappings import UUID_FUNCTION

        target_fn = UUID_FUNCTION.get(self._t._target)
        if not target_fn:
            return sql
        return self._map_session_id_in_sql(
            self._UUID_PATTERN.sub(f"{target_fn}()", sql)
        )

    def _map_session_id_in_sql(self, sql: str) -> str:
        target_expr = self._SESSION_ID_EXPR.get(self._t._target)
        if not target_expr:
            return sql
        return self._map_rowcount_fn_in_sql(
            self._SESSION_ID_PATTERN.sub(target_expr, sql)
        )

    def _map_rowcount_fn_in_sql(self, sql: str) -> str:
        target_expr = self._ROWCOUNT_FN_EXPR.get(self._t._target)
        if not target_expr:
            return self._map_limit_in_sql(self._map_bool_literals_in_sql(sql))
        return self._map_limit_in_sql(
            self._map_bool_literals_in_sql(
                self._ROWCOUNT_FN_PATTERN.sub(target_expr, sql)
            )
        )

    def _map_bool_literals_in_sql(self, sql: str) -> str:
        if self._t._source != "mysql" or self._t._target != "oracle":
            return sql
        return self._BOOL_LITERAL_RE.sub(
            lambda m: "1" if m.group(1).upper() == "TRUE" else "0", sql
        )

    def _map_limit_in_sql(self, sql: str) -> str:
        if self._t._source not in ("mysql", "postgresql"):
            return sql
        if self._t._target == "tsql":
            # Two-arg LIMIT anywhere; single-arg only INSIDE a subquery
            # (``RETURN (select … limit 1)`` — wave 229): the trailing
            # statement-level form stays the SELECT-assign emitter's TOP
            # (wave 212). OFFSET/FETCH needs an ORDER BY — (SELECT NULL)
            # is the standard no-order idiom.
            sql = self._LIMIT_TWO_RE.sub(
                r"ORDER BY (SELECT NULL) OFFSET \1 ROWS FETCH NEXT \2 ROWS ONLY",
                sql,
            )
            return re.sub(
                r"(?i)\bLIMIT\s+(\d+)(\s*\))",
                r"ORDER BY (SELECT NULL) OFFSET 0 ROWS FETCH NEXT \1 ROWS ONLY\2",
                sql,
            )
        if self._t._target != "oracle":
            return sql
        sql = self._LIMIT_TWO_RE.sub(r"OFFSET \1 ROWS FETCH NEXT \2 ROWS ONLY", sql)
        return self._LIMIT_ONE_RE.sub(r"FETCH FIRST \1 ROWS ONLY", sql)

    def _transform_niladic_datetime(self, sql: str) -> str:
        """Translate current-timestamp expressions across dialects.

        Handles the forms that differ in whether they take parentheses:
        GETDATE() (T-SQL), SYSDATE (Oracle), NOW() (PG/MySQL).
        """
        sql = self._map_now_in_sql(sql)
        # Argument-aware function rewrites run regardless of the niladic
        # datetime mapping above.
        sql = self._transform_dateadd(sql)
        sql = self._transform_datediff(sql)
        sql = self._transform_substring_position(sql)
        sql = self._transform_decode(sql)
        sql = self._transform_listagg_within_group(sql)
        sql = self._transform_string_agg(sql)
        sql = self._transform_last_identity(sql)
        sql = self._transform_nvl2(sql)
        sql = self._transform_oracle_date_funcs(sql)
        sql = self._transform_mysql_date_funcs(sql)
        return sql

    def _map_mysql_datefmt_to_oracle(self, fmt: str) -> str:
        """Map a MySQL date-format string to Oracle/PostgreSQL specifiers."""
        out = fmt
        # Reverse of the Oracle->MySQL table; longest specifiers first.
        for ora, mysql in self._ORACLE_TO_MYSQL_DATEFMT:
            out = out.replace(mysql, ora)
        # MySQL %T is HH24:MI:SS.
        out = out.replace("%T", "HH24:MI:SS")
        return out

    def _transform_mysql_date_funcs(self, sql: str) -> str:
        """Translate MySQL DATE_FORMAT/STR_TO_DATE to Oracle/PostgreSQL.

        DATE_FORMAT(d, fmt) -> TO_CHAR(d, mapped_fmt)
        STR_TO_DATE(s, fmt) -> TO_DATE(s, mapped_fmt)
        Targets Oracle and PostgreSQL (both use TO_CHAR/TO_DATE with the same
        format patterns); T-SQL has no direct TO_CHAR, so it is left for the
        CONVERT path / manual review.
        """
        if self._t._source != "mysql" or self._t._target not in (
            "oracle",
            "postgresql",
        ):
            return sql

        def map_fmt_arg(arg: str) -> str:
            s = arg.strip()
            if len(s) >= 2 and s[0] == "'" and s[-1] == "'":
                return "'" + self._map_mysql_datefmt_to_oracle(s[1:-1]) + "'"
            return arg

        def build_date_format(args: list[str]) -> str | None:
            if len(args) != 2:
                return None
            return f"TO_CHAR({args[0]}, {map_fmt_arg(args[1])})"

        def build_str_to_date(args: list[str]) -> str | None:
            if len(args) != 2:
                return None
            return f"TO_DATE({args[0]}, {map_fmt_arg(args[1])})"

        sql = self._rewrite_calls(sql, "DATE_FORMAT", build_date_format)
        sql = self._rewrite_calls(sql, "STR_TO_DATE", build_str_to_date)
        return sql

    def _map_oracle_datefmt_to_mysql(self, fmt: str) -> str:
        """Map an Oracle date-format string literal to MySQL's specifiers."""
        out = fmt
        # Replace longest tokens first to avoid partial overlaps.
        for ora, mysql in self._ORACLE_TO_MYSQL_DATEFMT:
            out = re.sub(ora, mysql, out, flags=re.IGNORECASE)
        return out

    def _transform_oracle_date_funcs(self, sql: str) -> str:
        """Translate Oracle TO_CHAR/TO_DATE with date-format strings.

        Oracle -> MySQL:
          TO_CHAR(d, fmt)  -> DATE_FORMAT(d, mapped_fmt)
          TO_DATE(s, fmt)  -> STR_TO_DATE(s, mapped_fmt)
        The format-pattern mapping covers the common specifiers; uncommon
        ones are left as-is for review.
        """
        if self._t._source != "oracle" or self._t._target != "mysql":
            return sql

        def map_fmt_arg(arg: str) -> str:
            s = arg.strip()
            if len(s) >= 2 and s[0] == "'" and s[-1] == "'":
                inner = s[1:-1]
                return "'" + self._map_oracle_datefmt_to_mysql(inner) + "'"
            return arg

        def build_to_char(args: list[str]) -> str | None:
            if len(args) != 2:
                return None
            return f"DATE_FORMAT({args[0]}, {map_fmt_arg(args[1])})"

        def build_to_date(args: list[str]) -> str | None:
            if len(args) != 2:
                return None
            return f"STR_TO_DATE({args[0]}, {map_fmt_arg(args[1])})"

        sql = self._rewrite_calls(sql, "TO_CHAR", build_to_char)
        sql = self._rewrite_calls(sql, "TO_DATE", build_to_date)
        return sql

    def _transform_nvl2(self, sql: str) -> str:
        """Translate Oracle NVL2(expr, if_not_null, if_null) to CASE.

        NVL2(e, a, b) == CASE WHEN e IS NOT NULL THEN a ELSE b END.
        Applies when translating away from Oracle.
        """
        if self._t._source != "oracle" or self._t._target == "oracle":
            return sql

        def build(args: list[str]) -> str | None:
            if len(args) != 3:
                return None
            expr, if_not_null, if_null = args
            return (
                f"CASE WHEN {expr} IS NOT NULL "
                f"THEN {if_not_null} ELSE {if_null} END"
            )

        return self._rewrite_calls(sql, "NVL2", build)

    def _transform_last_identity(self, sql: str) -> str:
        """Translate the 'last generated id' call across dialects.

        Each engine spells it differently — T-SQL ``SCOPE_IDENTITY()``,
        PostgreSQL ``LASTVAL()``, MySQL ``LAST_INSERT_ID()`` — and Oracle has
        no session-scoped form (the value comes from ``<sequence>.CURRVAL``),
        so it is emitted as a documented comment. Handled for every source,
        not only T-SQL (the shared mapping layer knows all spellings).
        """
        if self._t._source == self._t._target:
            return sql
        replacement = LAST_IDENTITY_EXPR.get(self._t._target)
        if replacement is None:
            return sql
        for func, dialect in LAST_IDENTITY_SOURCE_FUNCS.items():
            if dialect != self._t._source:
                continue
            sql = re.sub(rf"\b{func}\s*\(\s*\)", replacement, sql, flags=re.IGNORECASE)
        return sql

    @staticmethod
    def _fold_string_literal(expr: str) -> str | None:
        """Fold a constant string expression (``'x'``, ``CHR(n)``, and ``||``
        chains of those) into ONE quoted literal, or None if any piece is not
        constant. MySQL's GROUP_CONCAT SEPARATOR accepts only a literal."""
        escapes = {9: "\\t", 10: "\\n", 13: "\\r"}
        pieces: list[str] = []
        for part in re.split(r"\|\|", expr):
            part = part.strip()
            m = re.fullmatch(r"(?is)CHR\s*\(\s*(\d+)\s*\)", part)
            if m:
                esc = escapes.get(int(m.group(1)))
                if esc is None:
                    return None
                pieces.append(esc)
                continue
            if len(part) >= 2 and part.startswith("'") and part.endswith("'"):
                pieces.append(part[1:-1].replace("\\", "\\\\"))
                continue
            return None
        return "'" + "".join(pieces) + "'"

    def _transform_listagg_within_group(self, sql: str) -> str:
        """Translate the full Oracle ``LISTAGG(col, sep) WITHIN GROUP (ORDER
        BY ...)`` form per target. The basic-form handler below rewrote only
        the call and left the WITHIN GROUP suffix dangling — invalid on
        MySQL/PostgreSQL."""
        if self._t._source != "oracle" or self._t._target == "oracle":
            return sql
        from unique.core.sql_split import split_top_level_commas

        pat = re.compile(r"(?i)\bLISTAGG\s*\(")
        out: list[str] = []
        i = 0
        while True:
            m = pat.search(sql, i)
            if not m:
                break

            def scan_parens(start: int) -> int:
                """Index just past the paren that closes depth 1 at start."""
                depth, in_str, j = 1, False, start
                while j < len(sql) and depth:
                    ch = sql[j]
                    if in_str:
                        in_str = ch != "'"
                    elif ch == "'":
                        in_str = True
                    elif ch == "(":
                        depth += 1
                    elif ch == ")":
                        depth -= 1
                    j += 1
                return j

            close = scan_parens(m.end())
            args = split_top_level_commas(sql[m.end() : close - 1])
            wg = re.match(r"(?is)\s*WITHIN\s+GROUP\s*\(\s*ORDER\s+BY\s+", sql[close:])
            order: str | None = None
            end = close
            if wg:
                wg_close = scan_parens(close + wg.end())
                order = sql[close + wg.end() : wg_close - 1].strip()
                end = wg_close
            rep = self._string_agg_with_order(args, order)
            if rep is None:
                out.append(sql[i:end])
            else:
                out.append(sql[i : m.start()])
                out.append(rep)
            i = end
        out.append(sql[i:])
        return "".join(out)

    def _string_agg_with_order(self, args: list[str], order: str | None) -> str | None:
        if len(args) != 2:
            return None
        col, sep = args[0].strip(), args[1].strip()
        if self._t._target == "mysql":
            lit = self._fold_string_literal(sep)
            if lit is None:
                self._t._warnings.append(
                    "GROUP_CONCAT's SEPARATOR accepts only a string literal; "
                    f"the LISTAGG separator '{sep}' is not constant — left "
                    "for manual review"
                )
                return None
            # Convert the aggregated expression's || now: once SEPARATOR
            # syntax wraps it, the pipes pass can no longer parse it.
            col = self._mysql_pipes_to_concat(col)
            ob = f" ORDER BY {order}" if order else ""
            return f"GROUP_CONCAT({col}{ob} SEPARATOR {lit})"
        if self._t._target == "postgresql":
            ob = f" ORDER BY {order}" if order else ""
            return f"STRING_AGG({col}, {sep}{ob})"
        if self._t._target == "tsql":
            wg = f" WITHIN GROUP (ORDER BY {order})" if order else ""
            return f"STRING_AGG({col}, {sep}){wg}"
        return None

    def _transform_string_agg(self, sql: str) -> str:
        """Translate string-aggregation functions across dialects.

        - T-SQL / PostgreSQL: STRING_AGG(col, sep)
        - Oracle:             LISTAGG(col, sep)
        - MySQL:              GROUP_CONCAT(col SEPARATOR sep)

        The full Oracle ``WITHIN GROUP`` form is handled by
        ``_transform_listagg_within_group`` (which must run first); this
        covers the remaining basic ``(col, sep)`` calls.
        """
        source_fn = {
            "tsql": "STRING_AGG",
            "postgresql": "STRING_AGG",
            "oracle": "LISTAGG",
            "mysql": "GROUP_CONCAT",
        }.get(self._t._source)
        if not source_fn or self._t._source == self._t._target:
            return sql

        def build(args: list[str]) -> str | None:
            # MySQL uses "col SEPARATOR sep" as a single arg; normalize.
            col: str
            sep: str | None
            if self._t._source == "mysql":
                if len(args) != 1 or "SEPARATOR" not in args[0].upper():
                    return None
                m = re.split(r"(?i)\bSEPARATOR\b", args[0], maxsplit=1)
                col, sep = m[0].strip(), m[1].strip()
            else:
                if len(args) != 2:
                    return None
                col, sep = args[0], args[1]

            if self._t._target in ("tsql", "postgresql"):
                return f"STRING_AGG({col}, {sep})"
            if self._t._target == "oracle":
                return f"LISTAGG({col}, {sep})"
            return f"GROUP_CONCAT({col} SEPARATOR {sep})"

        return self._rewrite_calls(sql, source_fn, build)

    def _transform_decode(self, sql: str) -> str:
        """Translate Oracle DECODE(expr, s1, r1, [s2, r2, ...], [default]).

        Equivalent to a searched CASE expression:
            CASE WHEN expr = s1 THEN r1 [WHEN expr = s2 THEN r2 ...]
                 [ELSE default] END
        Only applies when translating away from Oracle.
        """
        if self._t._source != "oracle" or self._t._target == "oracle":
            return sql

        def build(args: list[str]) -> str | None:
            if len(args) < 3:
                return None
            expr = args[0]
            pairs = args[1:]
            parts = ["CASE"]
            i = 0
            while i + 1 < len(pairs):
                parts.append(f"WHEN {expr} = {pairs[i]} THEN {pairs[i + 1]}")
                i += 2
            if i < len(pairs):  # trailing default
                parts.append(f"ELSE {pairs[i]}")
            parts.append("END")
            return " ".join(parts)

        return self._rewrite_calls(sql, "DECODE", build)

    def _transform_substring_position(self, sql: str) -> str:
        """Translate substring-position functions with argument reordering.

        The three engines express "position of needle in haystack" with
        different argument orders:
        - T-SQL:  CHARINDEX(needle, haystack)
        - MySQL:  LOCATE(needle, haystack)        (same order as T-SQL)
        - Oracle: INSTR(haystack, needle)         (reversed)
        - PostgreSQL: STRPOS(haystack, needle) / POSITION(needle IN haystack)

        An optional third argument (start position) is preserved as the
        trailing argument in every dialect.
        """
        # Identify the source function name and how to read (needle, haystack).
        source_fn = {
            "tsql": "CHARINDEX",
            "mysql": "LOCATE",
            "oracle": "INSTR",
            "postgresql": "STRPOS",
        }.get(self._t._source)
        if not source_fn or self._t._source == self._t._target:
            return sql

        def build(args: list[str]) -> str | None:
            if len(args) < 2:
                return None
            # Read needle/haystack per source order.
            if self._t._source in ("tsql", "mysql"):
                needle, haystack = args[0], args[1]
            else:  # oracle, postgresql: haystack first
                haystack, needle = args[0], args[1]
            start = args[2] if len(args) >= 3 else None

            if self._t._target == "tsql":
                out = f"CHARINDEX({needle}, {haystack}"
                return (out + f", {start})") if start else (out + ")")
            if self._t._target == "mysql":
                out = f"LOCATE({needle}, {haystack}"
                return (out + f", {start})") if start else (out + ")")
            if self._t._target == "oracle":
                out = f"INSTR({haystack}, {needle}"
                return (out + f", {start})") if start else (out + ")")
            # postgresql
            if start:
                # STRPOS has no start argument: search the substring from
                # ``start`` and re-offset the hit (0 stays 0 = not found).
                # Dropping the start silently returned the wrong position.
                inner = f"STRPOS(SUBSTRING({haystack} FROM {start}), {needle})"
                # Spelled with '-' only: the later string-concat text pass
                # rewrites a '+' near a string literal into '||'.
                return (
                    f"(CASE WHEN {inner} = 0 THEN 0 "
                    f"ELSE {inner} - (1 - {start}) END)"
                )
            return f"STRPOS({haystack}, {needle})"

        return self._rewrite_calls(sql, source_fn, build)

    @staticmethod
    def _split_top_level_args(arglist: str) -> list[str]:
        """Split a comma-separated argument list at top-level commas only.

        Commas inside parentheses or string literals (single or double
        quotes) are not split points.
        """
        parts: list[str] = []
        depth = 0
        cur: list[str] = []
        quote: str | None = None
        for ch in arglist:
            if quote is not None:
                cur.append(ch)
                if ch == quote:
                    quote = None
                continue
            if ch in ("'", '"'):
                quote = ch
                cur.append(ch)
            elif ch == "(":
                depth += 1
                cur.append(ch)
            elif ch == ")":
                depth -= 1
                cur.append(ch)
            elif ch == "," and depth == 0:
                parts.append("".join(cur).strip())
                cur = []
            else:
                cur.append(ch)
        if cur:
            parts.append("".join(cur).strip())
        return parts

    def _rewrite_calls(
        self, sql: str, func_name: str, builder: Callable[[list[str]], str | None]
    ) -> str:
        """Rewrite every top-level call ``func_name(...)`` using ``builder``.

        ``builder`` receives the list of argument strings and returns the
        replacement text, or None to leave the call unchanged. Calls are
        rewritten right-to-left so earlier indices stay valid.
        """
        pattern = re.compile(rf"\b{re.escape(func_name)}\s*\(", re.IGNORECASE)
        result = sql
        for match in reversed(list(pattern.finditer(result))):
            start = match.end()
            depth = 1
            i = start
            while i < len(result) and depth > 0:
                if result[i] == "(":
                    depth += 1
                elif result[i] == ")":
                    depth -= 1
                i += 1
            inner = result[start : i - 1]
            args = self._split_top_level_args(inner)
            replacement = builder(args)
            if replacement is None:
                continue
            result = result[: match.start()] + replacement + result[i:]
        return result

    def _transform_dateadd(self, sql: str) -> str:
        """Translate simple T-SQL DATEADD(part, n, date) calls.

        Only the common, unambiguous form with a recognized date part is
        converted; anything else is left untouched. Source must be T-SQL;
        targets Oracle/PostgreSQL/MySQL.
        """
        if self._t._source != "tsql" or self._t._target not in (
            "oracle",
            "postgresql",
            "mysql",
        ):
            return sql

        def build(args: list[str]) -> str | None:
            if len(args) != 3:
                return None
            part, num, date = args
            unit = self._DATEPART_UNITS.get(part.strip().lower())
            if not unit:
                return None
            if self._t._target == "oracle":
                if unit == "DAY":
                    return f"({date} + {num})"
                if unit == "MONTH":
                    return f"ADD_MONTHS({date}, {num})"
                if unit == "YEAR":
                    return f"ADD_MONTHS({date}, ({num}) * 12)"
                if unit in ("HOUR", "MINUTE", "SECOND"):
                    return f"({date} + NUMTODSINTERVAL({num}, '{unit}'))"
                return None
            if self._t._target == "postgresql":
                # Only a literal count may live inside the INTERVAL string —
                # compacted: token-joined ``- 1`` re-parses as ``1`` (sqlglot
                # silently drops the sign; live: DATEADD(MONTH, -1, d) ADDED
                # a month). An expression count multiplies a unit interval.
                compact = re.sub(r"\s+", "", num)
                if re.fullmatch(r"[+-]?\d+", compact):
                    return f"({date} + INTERVAL '{compact} {unit}')"
                return f"({date} + ({num}) * INTERVAL '1 {unit}')"
            return f"DATE_ADD({date}, INTERVAL {num} {unit})"

        return self._rewrite_calls(sql, "DATEADD", build)

    def _transform_datediff(self, sql: str) -> str:
        """Translate DATEDIFF across dialects.

        T-SQL is 3-arg ``DATEDIFF(part, start, end)``; MySQL is 2-arg
        ``DATEDIFF(end, start)`` (whole days). Both return ``end - start``.
        Conversions:
        - Oracle: day -> (end - start); month -> MONTHS_BETWEEN(end, start);
          year -> MONTHS_BETWEEN(end, start)/12
        - PostgreSQL: day -> (end::date - start::date)
        - MySQL: day -> DATEDIFF(end, start); else TIMESTAMPDIFF(unit, ...)
        - T-SQL: DATEDIFF(DAY, start, end)
        """
        if self._t._source == self._t._target:
            return sql

        def build_tsql(args: list[str]) -> str | None:
            if len(args) != 3:
                return None

            # T-SQL DATEDIFF(part, start, end) = end - start. A sqlglot re-pass
            # rewrites it to its canonical DATEDIFF(end, start, part) (part last),
            # wrapping the operands in TIME_STR_TO_TIME — accept either layout.
            # An Oracle-source shim quotes the part ('D'); accept that too.
            def unit_of(arg: str) -> str | None:
                return self._DATEPART_UNITS.get(arg.strip().strip("'").lower())

            if unit_of(args[0]):
                part, start, end = args
            elif unit_of(args[2]):
                end, start, part = args
            else:
                return None
            unit = unit_of(part)
            if not unit:
                return None
            start, end = self._unwrap_time_str(start), self._unwrap_time_str(end)
            if self._t._target == "tsql":
                # The T-SQL part is a bare keyword; a quoted 'D' is invalid.
                return f"DATEDIFF({unit}, {start}, {end})"
            # T-SQL DATEDIFF counts calendar BOUNDARIES crossed (integer):
            # Jan-31 -> Feb-1 is MONTH = 1; 23:00 -> 01:00 next day is
            # DAY = 1. Oracle's raw subtraction / MONTHS_BETWEEN are
            # fractional — a silent numeric divergence — so both targets
            # use the boundary-counting forms the IR emitter live-validates.
            if self._t._target == "oracle":
                if unit == "DAY":
                    return (
                        f"(TRUNC(CAST({end} AS DATE)) - "
                        f"TRUNC(CAST({start} AS DATE)))"
                    )
                if unit == "MONTH":
                    return (
                        f"((EXTRACT(YEAR FROM {end}) * 12 + "
                        f"EXTRACT(MONTH FROM {end})) - "
                        f"(EXTRACT(YEAR FROM {start}) * 12 + "
                        f"EXTRACT(MONTH FROM {start})))"
                    )
                if unit == "YEAR":
                    return (
                        f"(EXTRACT(YEAR FROM {end}) - " f"EXTRACT(YEAR FROM {start}))"
                    )
                # A sub-day unit is a fraction of the (end - start) day count.
                factor = {"HOUR": 24, "MINUTE": 1440, "SECOND": 86400}.get(unit)
                if factor:
                    return f"(({end} - {start}) * {factor})"
                return None
            if self._t._target == "postgresql":
                if unit == "DAY":
                    return f"({end}::date - {start}::date)"
                if unit == "MONTH":
                    return (
                        f"((EXTRACT(YEAR FROM {end}) * 12 + "
                        f"EXTRACT(MONTH FROM {end})) - "
                        f"(EXTRACT(YEAR FROM {start}) * 12 + "
                        f"EXTRACT(MONTH FROM {start})))"
                    )
                if unit == "YEAR":
                    return (
                        f"(EXTRACT(YEAR FROM {end}) - " f"EXTRACT(YEAR FROM {start}))"
                    )
                return None
            # mysql
            if unit == "DAY":
                return f"DATEDIFF({end}, {start})"
            return f"TIMESTAMPDIFF({unit}, {start}, {end})"

        def build_mysql(args: list[str]) -> str | None:
            # MySQL DATEDIFF(end, start) is whole days (end - start).
            if len(args) != 2:
                return None
            end, start = args
            if self._t._target == "oracle":
                return f"({end} - {start})"
            if self._t._target == "postgresql":
                return f"({end}::date - {start}::date)"
            if self._t._target == "tsql":
                return f"DATEDIFF(DAY, {start}, {end})"
            return None

        # Oracle has no DATEDIFF builtin, so a DATEDIFF in Oracle source is a
        # client-defined T-SQL-style shim — translate it like the T-SQL form.
        if self._t._source in ("tsql", "oracle") and self._t._target in (
            "oracle",
            "postgresql",
            "mysql",
            "tsql",
        ):
            return self._rewrite_calls(sql, "DATEDIFF", build_tsql)
        if self._t._source == "mysql" and self._t._target in (
            "oracle",
            "postgresql",
            "tsql",
        ):
            return self._rewrite_calls(sql, "DATEDIFF", build_mysql)
        return sql

    @staticmethod
    def _unwrap_time_str(expr: str) -> str:
        """Strip a sqlglot TIME_STR_TO_TIME / DATE_STR_TO_DATE wrapper around an
        operand that is already a DATE/TIMESTAMP (spurious on Oracle)."""
        m = re.fullmatch(
            r"(?is)\s*(?:TIME_STR_TO_TIME|DATE_STR_TO_DATE)\s*\((.*)\)\s*", expr
        )
        return m.group(1).strip() if m else expr
