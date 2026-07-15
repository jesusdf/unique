"""Shared converter from sqlglot AST to Unique IR nodes.

All dialect parsers delegate to this module for the heavy lifting of
converting sqlglot's expression tree into our engine-agnostic IR.
"""
from __future__ import annotations
import re
from typing import cast
import sqlglot
import sqlglot.expressions as exp
from unique.core.ast_nodes import Alias, ASTNode, BinaryOp, BinaryOperator, CaseExpression, CastExpression, ColumnDefinition, ColumnRef, CommentStatement, CreateTableStatement, CreateViewStatement, DeleteStatement, DropStatement, ExpressionList, FunctionCall, InsertStatement, JoinClause, JoinType, LimitClause, Literal, OrderByItem, OrderDirection, PassthroughSQL, RawSQL, Script, SelectStatement, SetOperationType, Star, SubqueryExpression, TableRef, UnaryOp, UnaryOperator, UpdateStatement, WindowFunction
from unique.core.converter._base import *
from unique.core.converter._base import _RESERVED_IDENTIFIERS
from unique.core.converter.harvest import _coerce_bit_literal, _coerce_date_literal, _oracle_date_literal
from unique.core.mappings import CURRENT_DATE_EXPR, CURRENT_TIMESTAMP_EXPR, TSQL_OBJECT_CONTEXT_WORDS, tsql_call_needs_schema
from unique.core.sql_split import qualify_function_calls
_CAST_TYPE_MAP: dict[str, dict[str, str]] = {'mysql': {'INT': 'SIGNED', 'INTEGER': 'SIGNED', 'BIGINT': 'SIGNED', 'SMALLINT': 'SIGNED', 'TINYINT': 'SIGNED', 'BOOLEAN': 'SIGNED', 'BOOL': 'SIGNED', 'DATETIME2': 'DATETIME', 'SMALLDATETIME': 'DATETIME', 'VARCHAR': 'CHAR', 'NVARCHAR': 'CHAR'}, 'tsql': {'BOOLEAN': 'BIT', 'BOOL': 'BIT', 'DOUBLE': 'FLOAT'}, 'oracle': {'DATETIME': 'TIMESTAMP', 'DATETIME2': 'TIMESTAMP', 'SMALLDATETIME': 'TIMESTAMP', 'VARCHAR': 'VARCHAR2', 'NVARCHAR': 'NVARCHAR2', 'DOUBLE': 'BINARY_DOUBLE'}, 'postgresql': {'DATETIME': 'TIMESTAMP', 'DATETIME2': 'TIMESTAMP', 'SMALLDATETIME': 'TIMESTAMP'}}
_STAT_AGGREGATE_MAP: dict[str, dict[str, str]] = {'VARIANCE_POP': {'tsql': 'VARP', 'mysql': 'VAR_POP', 'oracle': 'VAR_POP', 'postgresql': 'VAR_POP'}, 'VAR_POP': {'tsql': 'VARP'}, 'VARIANCE': {'tsql': 'VAR', 'mysql': 'VAR_SAMP', 'oracle': 'VAR_SAMP'}, 'VAR_SAMP': {'tsql': 'VAR'}, 'STDDEV_POP': {'tsql': 'STDEVP'}, 'STDDEV_SAMP': {'tsql': 'STDEV'}, 'STDDEV': {'tsql': 'STDEV', 'mysql': 'STDDEV_SAMP', 'oracle': 'STDDEV_SAMP'}}
_DATE_FMT_TOKENS: list[tuple[str, str, str, str]] = [('YYYY', '%Y', 'yyyy', '%Y'), ('YY', '%y', 'yy', '%y'), ('MONTH', '%M', 'MMMM', '%B'), ('MON', '%b', 'MMM', '%b'), ('HH24', '%H', 'HH', '%H'), ('HH12', '%h', 'hh', '%I'), ('MM', '%m', 'MM', '%m'), ('DD', '%d', 'dd', '%d'), ('HH', '%h', 'hh', '%I'), ('MI', '%i', 'mm', '%M'), ('SS', '%s', 'ss', '%S'), ('DAY', '%W', 'dddd', '%A'), ('DY', '%a', 'ddd', '%a'), ('AM', '%p', 'tt', '%p'), ('PM', '%p', 'tt', '%p')]
_FMT_MODEL_IDX = {'oracle': 0, 'mysql': 1, 'tsql': 2, 'python': 3}

def _convert_date_format(fmt: str, src_model: str, dst_model: str) -> str:
    """Translate a date format string between the Oracle, strftime and .NET
    models (longest-token match; literal characters pass through)."""
    si, di = (_FMT_MODEL_IDX[src_model], _FMT_MODEL_IDX[dst_model])
    toks = sorted(_DATE_FMT_TOKENS, key=lambda t: -len(t[si]))
    case_sensitive = si != _FMT_MODEL_IDX['oracle']
    out: list[str] = []
    i = 0
    while i < len(fmt):
        for tok in toks:
            src_tok = tok[si]
            seg = fmt[i:i + len(src_tok)]
            if seg == src_tok if case_sensitive else seg.upper() == src_tok:
                out.append(tok[di])
                i += len(src_tok)
                break
        else:
            out.append(fmt[i])
            i += 1
    return ''.join(out)

def _portable_type_name(name: str, dialect: str) -> str:
    """Map a data-type name to the target dialect's equivalent.

    Falls back to the original name when no mapping is needed. Some mappings
    (e.g. UNIQUEIDENTIFIER -> CHAR(36)) carry their own length, in which case
    the caller's parameter list should be empty; these are types that don't
    take a user-supplied length here.
    """
    return _TYPE_NAME_MAP.get(dialect, {}).get(name.upper(), name)

def _portable_types_in_sql(sql: str, dialect: str) -> str:
    """Replace non-portable type names in raw emitted SQL for ``dialect``.

    Used for passthrough DDL (e.g. CREATE TABLE handled by sqlglot) where
    column types aren't routed through our own emitter. Word-boundary,
    case-insensitive replacement; types that carry their own length in the
    map (e.g. CHAR(36)) only substitute the bare name, so an existing
    ``(n)`` after it would be left — acceptable since those source types
    (UNIQUEIDENTIFIER/UUID) don't take a user length.
    """
    if dialect != 'mysql':
        sql = re.sub('(?i)\\bVARBINARY\\b(?!\\s*\\()', 'LONGBLOB', sql)
    elif dialect == 'tsql':
        sql = re.sub('(?i)\\bVARBINARY\\b(?!\\s*\\()', 'VARBINARY(MAX)', sql)
    mapping = _TYPE_NAME_MAP.get(dialect, {})
    if not mapping:
        return sql
    for src, dst in mapping.items():
        dst_name = dst.split('(')[0]
        sql = re.sub(f'(?i)\\b{re.escape(src)}\\b', dst_name, sql)
    return sql

def emit_sql(nodes: list[ASTNode], dialect: str) -> str:
    """Emit IR nodes as SQL text for the given dialect.

    This is the shared emitter that handles common patterns. Dialect-specific
    emitters may override individual node handling.

    Args:
        nodes: IR nodes to emit.
        dialect: Target dialect name.

    Returns:
        Formatted SQL text.
    """
    parts: list[tuple[str, bool]] = []
    for node in nodes:
        sql = emit_node(node, dialect)
        if sql:
            parts.append((sql, isinstance(node, CommentStatement)))
    if not parts:
        return ''
    separator = '\nGO\n\n' if dialect == 'tsql' else ';\n\n'
    pieces = [parts[0][0]]
    for i in range(1, len(parts)):
        prev_is_comment = parts[i - 1][1]
        text = parts[i][0]
        pieces.append(('\n' if prev_is_comment else separator) + text)
    return ''.join(pieces)

def _comment_block(sql: str) -> str:
    """Comment out every line of *sql* (``-- `` prefix).

    Degraded passthroughs must comment the whole statement: prefixing only
    the first line leaves the remaining lines as raw source SQL, executable
    and invalid on the target.
    """
    return '\n'.join((f'-- {ln}' if ln.strip() else '--' for ln in sql.splitlines()))

def _cte_dml_unsupported(sql: str, read: str, dialect: str) -> str | None:
    """Why a WITH-clause UPDATE/DELETE cannot run on *dialect* (None = it can).

    T-SQL lets a statement update through its CTE (``WITH x AS (SELECT ...)
    UPDATE x SET ...``); nothing else does. Oracle additionally has no WITH
    clause on UPDATE/DELETE at all.
    """
    if dialect == 'tsql':
        return None
    try:
        expr = sqlglot.parse_one(sql, read=read)
    except Exception:
        return None
    with_clause = expr.args.get('with') or expr.args.get('with_')
    if with_clause is None:
        return None
    cte_names = {c.alias_or_name.lower() for c in with_clause.expressions}
    target = expr.this
    target_name = target.name.lower() if isinstance(target, exp.Table) else ''
    if target_name in cte_names:
        return f"{dialect} cannot update through a CTE; rewrite as a MERGE or a correlated UPDATE joined on the table's key."
    if dialect == 'oracle':
        return 'Oracle has no WITH clause on UPDATE/DELETE; inline the CTE as a subquery or rewrite as a MERGE.'
    return None
_ORACLE_MODIFY_RE = re.compile('(?is)^\\s*ALTER\\s+TABLE\\s+(?P<table>[\\w.\\"]+)\\s+MODIFY\\s+(?:\\((?P<parenspec>.+)\\)|(?P<spec>[^;]+?))\\s*;?\\s*$')
_MODIFY_COL_RE = re.compile('(?is)^(?P<col>[\\w\\"]+)\\s*(?P<type>(?!NOT\\b|NULL\\b)[A-Za-z]\\w*(?:\\s*\\(\\s*\\d+(?:\\s*,\\s*\\d+)?\\s*\\))?)?\\s*(?P<null>NOT\\s+NULL|NULL)?$')

def rewrite_oracle_modify(sql: str, dialect: str) -> str | None:
    """Rewrite Oracle's ``ALTER TABLE t MODIFY [(]col type [NULL]...[)]`` for
    *dialect* (sqlglot parses neither form — the statement leaked verbatim).

    Returns None when the statement is not that shape or a column spec is
    more complex than ``col [type] [NOT NULL|NULL]`` (defaults, constraints).
    """
    if dialect == 'oracle':
        return None
    m = _ORACLE_MODIFY_RE.match(sql)
    if not m:
        return None
    table = m.group('table')
    spec_text = m.group('parenspec') or m.group('spec') or ''
    actions: list[str] = []
    for spec in _split_top_level_commas(spec_text):
        cm = _MODIFY_COL_RE.match(spec.strip())
        if not cm:
            return None
        col = cm.group('col')
        ctype = cm.group('type') or ''
        if ctype:
            ctype = _portable_types_in_sql(ctype, dialect)
        nullability = (cm.group('null') or '').upper()
        nullability = re.sub('\\s+', ' ', nullability)
        if not ctype and (not nullability):
            return None
        if dialect == 'tsql':
            if not ctype:
                return None
            suffix = f' {nullability}' if nullability else ''
            actions.append(f'ALTER COLUMN {col} {ctype}{suffix}')
        elif dialect == 'postgresql':
            if ctype:
                actions.append(f'ALTER COLUMN {col} TYPE {ctype}')
            if nullability == 'NOT NULL':
                actions.append(f'ALTER COLUMN {col} SET NOT NULL')
            elif nullability == 'NULL':
                actions.append(f'ALTER COLUMN {col} DROP NOT NULL')
        else:
            if not ctype:
                return None
            suffix = f' {nullability}' if nullability else ''
            actions.append(f'MODIFY COLUMN {col} {ctype}{suffix}')
    if not actions:
        return None
    if dialect == 'tsql':
        return ';\n'.join((f'ALTER TABLE {table} {a}' for a in actions)) + ';'
    return f'ALTER TABLE {table} ' + ', '.join(actions) + ';'
_SEQ_NEXTVAL_RE = re.compile('(?i)\\b([A-Za-z_]\\w*)\\s*\\.\\s*NEXTVAL\\b')
_SEQ_CURRVAL_RE = re.compile('(?i)\\b([A-Za-z_]\\w*)\\s*\\.\\s*CURRVAL\\b')

def map_sequence_refs(sql: str, dialect: str) -> str:
    """Map Oracle ``seq.NEXTVAL``/``seq.CURRVAL`` to the target's spelling.

    T-SQL: NEXT VALUE FOR seq (no CURRVAL equivalent — left for the
    honesty gate); PostgreSQL: nextval('seq')/currval('seq'). MySQL has no
    sequences at all — left untouched for the existing degradation paths.
    """
    if dialect == 'tsql':
        sql = _SEQ_NEXTVAL_RE.sub('NEXT VALUE FOR \\1', sql)
    elif dialect == 'postgresql':
        sql = _SEQ_NEXTVAL_RE.sub(lambda m: f"nextval('{m.group(1).lower()}')", sql)
        sql = _SEQ_CURRVAL_RE.sub(lambda m: f"currval('{m.group(1).lower()}')", sql)
    return sql

def _oracle_merge_paren_on(sql: str) -> str:
    """Wrap a MERGE's ON condition in the parentheses Oracle requires.

    Scans at paren depth 0 (quote-aware) for the ``ON`` that follows USING and
    the ``WHEN`` that ends the condition, so an ON inside the USING subquery
    (a JOIN) is never touched.
    """
    depth = 0
    in_str = False
    on_at = when_at = None
    i = 0
    upper = sql.upper()
    while i < len(sql):
        ch = sql[i]
        if in_str:
            if ch == "'":
                in_str = False
        elif ch == "'":
            in_str = True
        elif ch == '(':
            depth += 1
        elif ch == ')':
            depth -= 1
        elif depth == 0 and upper.startswith(' ON ', i):
            if on_at is None:
                on_at = i
        elif depth == 0 and on_at is not None and upper.startswith(' WHEN ', i):
            when_at = i
            break
        i += 1
    if on_at is None or when_at is None:
        return sql
    cond = sql[on_at + 4:when_at].strip()
    if cond.startswith('(') and cond.endswith(')'):
        return sql
    return f'{sql[:on_at]} ON ({cond}){sql[when_at:]}'

def emit_node(node: ASTNode, dialect: str) -> str:
    """Emit a single IR node as SQL text."""
    if isinstance(node, CommentStatement):
        return node.text
    if isinstance(node, SelectStatement):
        return _emit_select(node, dialect)
    if isinstance(node, InsertStatement):
        return _emit_insert(node, dialect)
    if isinstance(node, UpdateStatement):
        return _emit_update(node, dialect)
    if isinstance(node, DeleteStatement):
        return _emit_delete(node, dialect)
    if isinstance(node, CreateTableStatement):
        return _emit_create_table(node, dialect)
    if isinstance(node, CreateViewStatement):
        return _emit_create_view(node, dialect)
    if isinstance(node, DropStatement):
        return _emit_drop(node, dialect)
    if isinstance(node, RawSQL):
        reason = re.sub('\\x1b\\[[0-9;]*m', '', node.reason)
        reason = ' '.join(reason.split())
        return f'-- UNIQUE: {reason}\n{_comment_block(node.sql)}'
    if isinstance(node, PassthroughSQL):
        return _emit_passthrough(node, dialect)
    if isinstance(node, Script):
        sep = '\nGO\n\n' if dialect == 'tsql' else ';\n\n'
        return sep.join((emit_node(s, dialect) for s in node.statements))
    return _emit_expression(node, dialect)

def _ident_if_plain(name: str, dialect: str) -> str:
    """Quote a bare column name when it is a reserved word in *dialect*
    (``INSERT INTO t (a, manual)`` is a 1064 on MySQL 8.4). Dotted/quoted
    forms pass through untouched."""
    if re.fullmatch('\\w+', name):
        return _ident(name, False, dialect)
    return name

def _quote_reserved_identifiers(expr: exp.Expression, dialect: str) -> exp.Expression:
    """Mark identifiers that are reserved words in *dialect* as quoted, so a
    passthrough CREATE INDEX / ALTER on a reserved name emits valid SQL."""
    reserved = _RESERVED_IDENTIFIERS.get(dialect, frozenset())
    if reserved:
        for ident in expr.find_all(exp.Identifier):
            if not ident.args.get('quoted') and str(ident.this).upper() in reserved:
                ident.set('quoted', True)
    return expr

def _tsql_index_predicate(pred: exp.Expression) -> str | None:
    """Render a filtered-index predicate in T-SQL's restricted grammar.

    ``NOT x IS NULL`` (sqlglot's model of IS NOT NULL) must spell
    ``x IS NOT NULL`` — the only form CREATE INDEX ... WHERE accepts.
    Returns None for shapes outside that grammar (caller falls back)."""
    if isinstance(pred, exp.Not) and isinstance(pred.this, exp.Is) and isinstance(pred.this.expression, exp.Null):
        return f"{pred.this.this.sql(dialect='tsql')} IS NOT NULL"
    if isinstance(pred, exp.Is) and isinstance(pred.expression, exp.Null):
        return f"{pred.this.sql(dialect='tsql')} IS NULL"
    if isinstance(pred, exp.And):
        left = _tsql_index_predicate(pred.this)
        right = _tsql_index_predicate(pred.expression)
        if left and right:
            return f'{left} AND {right}'
        return None
    if isinstance(pred, (exp.EQ, exp.GT, exp.GTE, exp.LT, exp.LTE, exp.NEQ)):
        if isinstance(pred.this, exp.Column) and isinstance(pred.expression, (exp.Literal, exp.Null, exp.Boolean)):
            return str(pred.sql(dialect='tsql'))
        return None
    return None

def _pg_index_rebuild(sql: str, read: str, dialect: str) -> str | None:
    """Rebuild a PostgreSQL CREATE INDEX as valid T-SQL/MySQL, or None
    to let the generic sqlglot path try (expression indexes, exotic
    shapes). Both targets require an index NAME; MySQL has no filtered
    indexes at all, T-SQL only a restricted predicate grammar."""
    physical_kw = ''
    trailing = ''
    note = re.search('(?is)\\s*/\\*\\s*UNIQUE:\\s*(?P<clauses>.+?)\\s*--\\s*tsql-only,[^*]*?physical index clause[^*]*?\\*/', sql)
    if note:
        sql = (sql[:note.start()] + sql[note.end():]).strip()
        clauses = note.group('clauses').strip()
        lead = re.match('(?i)(?P<kw>(?:NON)?CLUSTERED)\\b\\s*(?P<rest>.*)$', clauses)
        if lead:
            physical_kw = lead.group('kw') + ' '
            trailing = lead.group('rest').strip()
        else:
            trailing = clauses
    try:
        tree = sqlglot.parse_one(sql, read=read)
    except Exception:
        return None
    if not isinstance(tree, exp.Create):
        return None
    index = tree.this
    if not isinstance(index, exp.Index):
        return None
    params = index.args.get('params')
    ordered = list(params.args.get('columns') or []) if params else []
    cols: list[str] = []
    for o in ordered:
        inner = o.this
        if isinstance(inner, exp.Opclass):
            inner = inner.this
        if not isinstance(inner, exp.Column):
            return None
        col = str(inner.sql(dialect='mysql' if dialect == 'mysql' else 'tsql'))
        if o.args.get('desc'):
            col += ' DESC'
        cols.append(col)
    if not cols:
        return None
    table = index.args.get('table')
    if table is None:
        return None
    write = 'mysql' if dialect == 'mysql' else 'tsql'
    table_sql = str(table.sql(dialect=write))
    name = str(index.this.sql(dialect=write)) if index.this else ''
    if not name:
        pieces = [re.sub('\\W+', '', table_sql)] + [re.sub('\\W+', '', c) for c in cols[:3]]
        name = '_'.join((p for p in pieces if p)) + '_idx'
    unique = 'UNIQUE ' if tree.args.get('unique') else ''
    where = params.args.get('where') if params else None
    where_sql = ''
    dropped_where = ''
    if where is not None:
        rendered = _tsql_index_predicate(where.this) if dialect == 'tsql' else None
        if rendered is None:
            if tree.args.get('unique'):
                reason = f'partial UNIQUE index predicate has no {dialect} filtered-index form; statement preserved as a comment'
                body = '\n'.join((f'-- {line}' for line in sql.strip().splitlines()))
                return f'-- UNIQUE: {reason}\n{body}'
            dropped_where = f"\n-- UNIQUE: partial-index predicate dropped (no {dialect} filtered-index form); the index is broader than the source's: {where.this.sql(dialect=write)}"
        else:
            where_sql = f' WHERE {rendered}'
    stmt = f"CREATE {unique}{physical_kw}INDEX {name} ON {table_sql} ({', '.join(cols)}){where_sql}"
    if trailing:
        stmt += f' {trailing}'
    if dropped_where:
        stmt += dropped_where
    if unique and (not where_sql) and (dialect == 'tsql'):
        return f'{stmt};\n-- UNIQUE: PostgreSQL unique indexes treat NULLs as distinct; T-SQL allows a single NULL per unique index'
    return stmt

def _emit_condition(node: ASTNode, dialect: str) -> str:
    """Emit an expression in condition position.

    T-SQL has no boolean type in predicates: PG's bare boolean literal
    condition (``JOIN b ON true``, ``WHERE false``) mapped to ``ON 1``,
    which is error 4145 — it must be a real comparison."""
    if dialect == 'tsql' and isinstance(node, Literal) and (node.dtype == 'boolean'):
        return '1 = 1' if node.value else '1 = 0'
    return _emit_expression(node, dialect)

def _emit_passthrough(node: PassthroughSQL, dialect: str) -> str:
    """Re-transpile a passthrough statement to the target dialect.

    Uses sqlglot directly (it handles ALTER, CREATE INDEX, CREATE SEQUENCE,
    etc. well). On failure, fall back to a commented passthrough so nothing
    is silently lost.
    """
    read = sqlglot_dialect_name(node.source_dialect)
    write = sqlglot_dialect_name(dialect)
    if node.kind == 'ALTER' and node.source_dialect == 'tsql':
        rebuilt = _tsql_add_key_constraint(node.sql, dialect)
        if rebuilt is not None:
            return rebuilt
    if node.kind == 'CREATE INDEX' and node.source_dialect == 'postgresql' and (dialect in ('tsql', 'mysql')):
        rebuilt = _pg_index_rebuild(node.sql, read, dialect)
        if rebuilt is not None:
            return rebuilt
    if dialect == 'mysql' and node.kind == 'CREATE SEQUENCE':
        return '-- UNIQUE: MySQL has no sequences; use an AUTO_INCREMENT column instead. Original:\n' + _comment_block(_strip_dbo_schema_qualifier(node.sql))
    if node.kind in ('SET', 'COMMAND') and node.source_dialect == 'postgresql' and (dialect != 'postgresql') and re.match('(?is)^\\s*SET\\s+SESSION\\s+AUTHORIZATION\\b', node.sql):
        return f'-- UNIQUE: SET SESSION AUTHORIZATION has no {dialect} equivalent; switch users natively.\n{_comment_block(node.sql)}'
    if node.kind == 'SET' and node.source_dialect == 'postgresql' and (dialect != 'postgresql') and re.match('(?is)^\\s*SET\\s+(?:LOCAL\\s+|SESSION\\s+(?!AUTHORIZATION\\b))?(?!TRANSACTION\\b|CONSTRAINTS\\b|ROLE\\b|TIME\\s+ZONE\\b)[A-Za-z_][\\w.]*\\s*(?:=|\\bTO\\b)', node.sql):
        return f'-- UNIQUE: PostgreSQL session setting has no {dialect} equivalent; configure the session natively.\n{_comment_block(node.sql)}'
    if node.kind == 'USE' and dialect in ('postgresql', 'oracle'):
        return f'-- UNIQUE: {dialect} has no USE statement; connect to the target database/schema instead.\n{_comment_block(node.sql)}'
    if node.kind == 'MERGE' and dialect == 'mysql':
        upsert = _merge_to_mysql_upsert(node.sql, read)
        if upsert is not None:
            return upsert
        commented = _comment_block(node.sql)
        return '-- UNIQUE: MySQL has no MERGE; rewrite as INSERT ... ON DUPLICATE KEY UPDATE. Original:\n' + commented
    if node.kind == 'CTE DML':
        reason = _cte_dml_unsupported(node.sql, read, dialect)
        if reason is not None:
            return f'-- UNIQUE: {reason} Original:\n{_comment_block(node.sql)}'
    if node.kind == 'CONNECT BY' and dialect != 'oracle':
        commented = _comment_block(node.sql)
        return '-- UNIQUE: Oracle CONNECT BY / START WITH hierarchical query has no automatic equivalent; rewrite as a WITH RECURSIVE CTE. Original:\n' + commented
    if node.kind == 'RETURNING' and dialect == 'mysql':
        m = re.search('(?i)\\bRETURNING\\b\\s+(.*?)\\s*;?\\s*$', node.sql)
        cols = m.group(1).strip() if m else ''
        base = re.sub('(?i)\\s*\\bRETURNING\\b.*$', '', node.sql).rstrip()
        return f'{base};\n-- UNIQUE: MySQL has no RETURNING/OUTPUT; the statement returned: {cols}'
    try:
        out = [_quote_reserved_identifiers(cast(exp.Expression, e), dialect).sql(dialect=write) for e in sqlglot.parse(node.sql, read=read) if e is not None]
        if out and out[0].strip():
            result = out[0]
            if node.kind == 'CREATE INDEX':
                result = _portable_index(result, dialect)
            else:
                result = _portable_types_in_sql(result, dialect)
            if node.kind == 'CREATE SEQUENCE' and dialect == 'oracle':
                result = _oracle_sequence_drop_type(result)
            if node.kind == 'MERGE':
                if dialect in ('tsql', 'postgresql'):
                    result = re.sub('(?i)\\s+FROM\\s+DUAL\\b', '', result)
                if dialect == 'oracle':
                    result = _oracle_merge_paren_on(result)
                if dialect == 'tsql' and (not result.rstrip().endswith(';')):
                    result = result.rstrip() + ';'
                if dialect == 'tsql':

                    def _decide(name: str, prev_word: str | None) -> str | None:
                        if prev_word and prev_word.upper() in TSQL_OBJECT_CONTEXT_WORDS:
                            return None
                        return 'dbo.' if tsql_call_needs_schema(name) else None
                    result = qualify_function_calls(result, _decide)
            if dialect == 'tsql':
                result = _portable_rename_column(result)
                result = re.sub('(?i),\\s*DROP\\s+COLUMN\\s+', ', ', result)
            if dialect != 'tsql' and node.kind == 'ALTER':
                result = _drop_named_default(result)
            if dialect != 'oracle':
                result = _portable_alter_add(result, dialect)
            if dialect in ('oracle', 'mysql', 'postgresql'):
                result = _strip_dbo_schema_qualifier(result)
            return result
    except Exception as e:
        logger.warning('passthrough transpile error (%s): %s', node.kind, e)
    return f'-- UNIQUE: Unhandled {node.kind}\n{_comment_block(node.sql)}'
_TSQL_ADD_KEY_RE = re.compile('(?isx)^\\s*ALTER\\s+TABLE\\s+(?P<table>[\\w.\\[\\]\\"]+)\\s+ADD\\s+CONSTRAINT\\s+(?P<name>[\\w\\[\\]\\"]+)\\s+(?P<kind>PRIMARY\\s+KEY|UNIQUE)\\s*(?:CLUSTERED|NONCLUSTERED)?\\s*\\(\\s*(?P<cols>[^()]*?)\\s*\\)(?P<tail>.*)$')
_TSQL_ADD_KEY_TAIL_RE = re.compile('(?is)^\\s*(?:WITH\\s*\\([^()]*\\))?\\s*(?:ON\\s+[\\w\\[\\]\\"]+)?\\s*;?\\s*$')

def _tsql_add_key_constraint(sql: str, dialect: str) -> str | None:
    """Normalize T-SQL ``ADD CONSTRAINT … PRIMARY KEY/UNIQUE CLUSTERED (col
    ASC) WITH (…) ON [grp]`` for the other engines (audit B1).

    sqlglot splits the storage clauses into comma-joined ALTER actions
    (invalid everywhere) and injects ``NULLS FIRST`` into the key column
    list, so this well-defined shape is rebuilt directly: the CLUSTERED
    keyword, per-column sort order, WITH options and filegroup are
    physical-storage details with no logical-schema impact.
    """
    from unique.core.sql_split import split_top_level_commas
    m = _TSQL_ADD_KEY_RE.match(sql)
    if not m or not _TSQL_ADD_KEY_TAIL_RE.match(m.group('tail')):
        return None
    cols: list[str] = []
    for item in split_top_level_commas(m.group('cols')):
        cm = re.fullmatch('(?is)\\s*([\\w\\[\\]\\"]+)(?:\\s+(?:ASC|DESC))?\\s*', item)
        if not cm:
            return None
        cols.append(_ident(cm.group(1).strip('[]"'), True, dialect))
    if not cols:
        return None
    table_parts = [p.strip('[]"') for p in m.group('table').split('.')]
    if dialect != 'tsql' and table_parts and (table_parts[0].lower() == 'dbo'):
        table_parts = table_parts[1:]
    table_sql = '.'.join((_ident(p, True, dialect) for p in table_parts))
    name_sql = _ident(m.group('name').strip('[]"'), True, dialect)
    kind = ' '.join(m.group('kind').upper().split())
    return f"ALTER TABLE {table_sql} ADD CONSTRAINT {name_sql} {kind} ({', '.join(cols)})"
_RENAME_COLUMN_RE = re.compile('(?is)^\\s*ALTER\\s+TABLE\\s+(?P<table>[\\w.\\[\\]\\"`]+)\\s+RENAME\\s+COLUMN\\s+(?P<old>[\\w\\[\\]\\"`]+)\\s+TO\\s+(?P<new>[\\w\\[\\]\\"`]+)\\s*;?\\s*$')

def _portable_rename_column(sql: str) -> str:
    """T-SQL has no ``ALTER TABLE … RENAME COLUMN``; it renames via
    ``sp_rename 'tbl.old', 'new', 'COLUMN'`` (audit D5 — the clause used to
    pass through verbatim and fail on every run)."""
    m = _RENAME_COLUMN_RE.match(sql)
    if not m:
        return sql

    def bare(s: str) -> str:
        return s.strip('[]"`')
    table, old, new = (bare(m.group('table')), bare(m.group('old')), bare(m.group('new')))
    return f"EXEC sp_rename '{table}.{old}', '{new}', 'COLUMN'"
_NAMED_DEFAULT_RE = re.compile('(?i)\\bCONSTRAINT\\s+([\\w\\[\\]\\"`]+)\\s+(?=DEFAULT\\b)')

def _drop_named_default(sql: str) -> str:
    """Drop a T-SQL named DEFAULT constraint's name (audit B3).

    Only T-SQL names its DEFAULT constraints; everywhere else ``CONSTRAINT
    <name> DEFAULT`` is a syntax error, and the default itself is anonymous.
    The dropped name is documented with a carrier note (the reconciliation
    layer turns it into a warning).
    """
    names = [m.group(1).strip('[]"`') for m in _NAMED_DEFAULT_RE.finditer(sql)]
    if not names:
        return sql
    cleaned = _NAMED_DEFAULT_RE.sub('', sql)
    notes = '\n'.join((f'-- UNIQUE: named DEFAULT constraint {n} dropped (defaults are anonymous on this engine)' for n in names))
    return f'{cleaned}\n{notes}'

def _portable_alter_add(sql: str, dialect: str) -> str:
    """Unwrap Oracle's parenthesized ALTER TABLE ADD ( ... ) form.

    sqlglot's non-Oracle writers render it as "ADD COLUMNS (item, ...)",
    which no other engine parses. T-SQL takes a plain comma list after one
    ADD; PostgreSQL/MySQL need one ADD per item.
    """
    m = re.search('(?is)\\bADD\\s+COLUMNS\\s*\\((.*)\\)\\s*$', sql)
    if not m:
        return sql
    items = [i.strip() for i in _split_top_level_commas(m.group(1))]
    head = sql[:m.start()].rstrip()
    if dialect == 'tsql':
        return f"{head} ADD {', '.join(items)}"
    return f'{head} ADD ' + ', ADD '.join(items)

def _portable_index(sql: str, dialect: str) -> str:
    """Make a transpiled CREATE INDEX portable for the target dialect.

    - CLUSTERED/NONCLUSTERED are T-SQL-only physical hints; drop them for
      other engines (the keyword has no meaning and breaks parsing).
    - INCLUDE (covering columns) is supported by PostgreSQL and T-SQL but not
      MySQL or Oracle; comment it out there with a note.
    - A filtered-index WHERE clause is supported by PostgreSQL (partial
      index) but not MySQL/Oracle; flag it for those.
    """
    if dialect == 'tsql':
        sql = re.sub('(?is)CASE\\s+WHEN\\s+.+?\\s+IS\\s+NULL\\s+THEN\\s+1\\s+ELSE\\s+0\\s+END(?:\\s+(?:ASC|DESC))?\\s*,\\s*', '', sql)
        note = re.search('(?is)\\s*/\\*\\s*UNIQUE:\\s*(?P<clauses>.+?)\\s*--\\s*tsql-only,[^*]*?physical index clause[^*]*?\\*/', sql)
        if note:
            sql = (sql[:note.start()].rstrip() + sql[note.end():]).rstrip().rstrip(';')
            clauses = note.group('clauses').strip()
            lead = re.match('(?i)(?P<kw>(?:NON)?CLUSTERED)\\b\\s*(?P<rest>.*)$', clauses)
            if lead:
                sql = re.sub('(?i)\\bCREATE\\s+(UNIQUE\\s+)?INDEX\\b', lambda m: f"CREATE {m.group(1) or ''}{lead.group('kw')} INDEX", sql, count=1)
                clauses = lead.group('rest').strip()
            if clauses:
                sql = f'{sql} {clauses}'
    dropped_physical: list[str] = []
    if dialect != 'tsql':

        def _drop(match: re.Match[str]) -> str:
            dropped_physical.append(match.group(0).strip())
            return ''
        sql = re.sub('(?i)\\s*\\b(NON)?CLUSTERED\\b', _drop, sql)
        sql = re.sub('(?i)\\s+WITH\\s*\\([^)]*\\)', _drop, sql)
        sql = re.sub('(?i)\\s+ON\\s+(?:\\[[^\\]]+\\]|"[^"]+"|\\w+)\\s*$', _drop, sql)
    if dialect != 'postgresql':
        sql = re.sub('(?i)CASE\\s+WHEN\\s+(?P<col>[\\w.\\[\\]\\"`]+)\\s+IS\\s+NULL\\s+THEN\\s+\\d+\\s+ELSE\\s+\\d+\\s+END\\s*,\\s*(?P=col)', lambda m: m.group('col'), sql)
        sql = re.sub('(?i)\\s+NULLS\\s+(?:FIRST|LAST)', '', sql)
    if dialect in ('mysql', 'oracle'):
        m = re.search('(?i)\\bINCLUDE\\s*\\([^)]*\\)', sql)
        if m:
            sql = sql[:m.start()].rstrip() + sql[m.end():] + f'\n-- UNIQUE: {dialect} does not support INCLUDE covering columns; dropped: {m.group(0)}'
        m = re.search('(?i)\\sWHERE\\s+.+$', sql)
        if m:
            sql = sql[:m.start()].rstrip() + f'\n-- UNIQUE: {dialect} does not support filtered indexes; dropped predicate:{m.group(0)}'
    if dropped_physical:
        clauses = ' '.join(dropped_physical)
        sql += f'\n/* UNIQUE: {clauses} -- tsql-only, no {dialect} equivalent (physical index clause) */'
    return sql

def _emit_select(node: SelectStatement, dialect: str) -> str:
    """Emit a SELECT statement."""
    parts: list[str] = []
    if node.ctes:
        cte_parts = []
        for cte in node.ctes:
            recursive = 'RECURSIVE ' if cte.recursive else ''
            cols = f"({', '.join(cte.columns)})" if cte.columns else ''
            inner = _emit_select(cte.query, dialect)
            cte_parts.append(f'{cte.name}{cols} AS (\n{inner}\n)')
        parts.append(f"WITH {recursive}{', '.join(cte_parts)}")
    top = ''
    if dialect == 'tsql' and node.limit is not None and (node.limit.limit is not None) and (node.limit.offset is None):
        pct = ' PERCENT' if node.limit.percent else ''
        top = f'TOP {_emit_expression(node.limit.limit, dialect)}{pct} '
    distinct = 'DISTINCT ' if node.distinct else ''
    cols = ', '.join((_emit_expression(c, dialect) for c in node.columns)) or '*'
    parts.append(f'SELECT {distinct}{top}{cols}')
    if node.from_clause:
        if isinstance(node.from_clause, SubqueryExpression):
            alias = node.from_clause.alias
            if not alias and dialect != 'oracle':
                alias = 'uq_dt'
            sub_alias = f' {_ident(alias, False, dialect)}' if alias else ''
            inner_sql = _emit_select(node.from_clause.query, dialect)
            if dialect == 'tsql':
                inner_sql = re.sub('(?is)\\s+ORDER\\s+BY\\s+[^()]*$', '', inner_sql) if not re.search('(?i)\\bTOP\\b', inner_sql) else inner_sql
            parts.append(f'FROM ({inner_sql}){sub_alias}')
        else:
            parts.append(f'FROM {_emit_table_ref(node.from_clause, dialect)}')
    elif dialect == 'oracle':
        parts.append('FROM DUAL')
    from_name = None
    if isinstance(node.from_clause, TableRef):
        from_name = node.from_clause.alias or node.from_clause.name
    elif isinstance(node.from_clause, SubqueryExpression):
        from_name = node.from_clause.alias or ('uq_dt' if dialect != 'oracle' else None)
    merged_cols: dict[str, str] = {}
    for join in node.joins:
        parts.append(_emit_join(join, dialect, left_name=from_name, merged_cols=merged_cols))
    if node.where:
        parts.append(f'WHERE {_emit_condition(node.where, dialect)}')
    if node.group_by:
        group_cols = ', '.join((_emit_expression(g, dialect) for g in node.group_by))
        parts.append(f'GROUP BY {group_cols}')
    if node.having:
        parts.append(f'HAVING {_emit_condition(node.having, dialect)}')
    if node.order_by:
        order_items = ', '.join((_emit_order_item(o, dialect) for o in node.order_by))
        parts.append(f'ORDER BY {order_items}')
    if node.limit:
        limit_sql = _emit_limit(node.limit, dialect)
        if limit_sql:
            parts.append(limit_sql)
    result = '\n'.join(parts)
    if node.set_op and node.set_query:
        op_map = {SetOperationType.UNION: 'UNION', SetOperationType.UNION_ALL: 'UNION ALL', SetOperationType.INTERSECT: 'INTERSECT', SetOperationType.EXCEPT: 'EXCEPT' if dialect != 'oracle' else 'MINUS'}
        op = op_map.get(node.set_op, 'UNION')
        right = _emit_select(node.set_query, dialect)
        result = f'{result}\n{op}\n{right}'
    return result

def _emit_insert(node: InsertStatement, dialect: str) -> str:
    """Emit an INSERT statement."""
    table = _emit_table_ref(node.table, dialect)
    col_names = [_ident_if_plain(c, dialect) for c in node.columns]
    cols = f" ({', '.join(col_names)})" if node.columns else ''
    if node.values:
        rows = []
        for row in node.values:
            cells = []
            for i, v in enumerate(row):
                if node.columns and i < len(node.columns):
                    v = _coerce_bit_literal(node.table, node.columns[i], v, dialect)
                    v = _coerce_date_literal(node.table, node.columns[i], v, dialect)
                cells.append(_emit_expression(v, dialect))
            rows.append(f"({', '.join(cells)})")
        values = ', '.join(rows)
        return f'INSERT INTO {table}{cols}\nVALUES {values}'
    if node.select:
        select = _emit_select(node.select, dialect)
        return f'INSERT INTO {table}{cols}\n{select}'
    if dialect == 'mysql':
        return f'INSERT INTO {table} () VALUES ()'
    return f'INSERT INTO {table}{cols}\nDEFAULT VALUES'

def _emit_update(node: UpdateStatement, dialect: str) -> str:
    """Emit an UPDATE statement.

    A cross-table update (``from_clause``/``joins`` present) is rendered in each
    engine's idiomatic form. T-SQL keeps ``UPDATE t SET ... FROM ... JOIN``;
    PostgreSQL uses ``UPDATE t SET ... FROM ... WHERE <join preds>``; MySQL puts
    the joins before SET (``UPDATE t JOIN s ON ... SET ...``); Oracle, which has
    no ``UPDATE ... FROM``, uses correlated subqueries. A plain single-table
    update is unchanged.
    """
    if node.from_clause is not None or node.joins:
        return _emit_cross_table_update(node, dialect)
    table = _emit_table_ref(node.table, dialect)
    set_parts = []
    for col, val in node.assignments:
        val = _coerce_bit_literal(node.table, col, val, dialect)
        val = _coerce_date_literal(node.table, col, val, dialect)
        set_parts.append(f'{_ident_if_plain(col, dialect)} = {_emit_expression(val, dialect)}')
    sets = ', '.join(set_parts)
    alias = getattr(node.table, 'alias', None)
    if dialect == 'tsql' and alias:
        result = f'UPDATE {alias}\nSET {sets}\nFROM {table}'
        if node.where:
            result += f'\nWHERE {_emit_expression(node.where, dialect)}'
        return result
    result = f'UPDATE {table}\nSET {sets}'
    if node.where:
        result += f'\nWHERE {_emit_expression(node.where, dialect)}'
    return result

def _emit_join_table_ref(table: TableRef | SubqueryExpression, dialect: str) -> str:
    """Emit a join's source table, whether a plain table or a subquery."""
    if isinstance(table, SubqueryExpression):
        alias = f' {table.alias}' if table.alias else ''
        return f'({_emit_select(table.query, dialect)}){alias}'
    return _emit_table_ref(table, dialect)

def _emit_cross_table_update(node: UpdateStatement, dialect: str) -> str:
    """Render a cross-table UPDATE (``UPDATE ... SET ... FROM/JOIN``) per engine.

    The T-SQL target alias usually names the same table as the FROM's first
    source (``UPDATE il SET il.c = p.c FROM invoice_line il JOIN product p``).
    We treat that first source as the table being updated and the remaining
    joins as the source side.
    """
    target = _cross_update_target(node)
    assignments = [(col, _emit_expression(_coerce_date_literal(target, col, _coerce_bit_literal(target, col, val, dialect), dialect), dialect)) for col, val in node.assignments]
    if dialect == 'oracle':
        return _emit_update_oracle_subquery(node, target, assignments)
    if dialect == 'mysql':
        return _emit_update_mysql_join(node, target, assignments, dialect)
    if dialect == 'postgresql':
        return _emit_update_postgres_from(node, target, assignments, dialect)
    return _emit_update_tsql_from(node, assignments, dialect)

def _join_predicates(node: UpdateStatement, dialect: str) -> list[str]:
    """Collect every join ON condition as a list of boolean SQL fragments."""
    preds: list[str] = []
    for join in node.joins:
        if join.condition is not None:
            preds.append(_emit_expression(join.condition, dialect))
    return preds

def _emit_update_postgres_from(node: UpdateStatement, target: TableRef, assignments: list[tuple[str, str]], dialect: str) -> str:
    """PostgreSQL: UPDATE t SET c = s.c FROM s [, ...] WHERE <join preds>."""
    target_sql = _emit_table_ref(target, dialect)
    sets = ', '.join((f'{col} = {val}' for col, val in assignments))
    sources = [_emit_join_table_ref(j.table, dialect) for j in node.joins]
    result = f'UPDATE {target_sql}\nSET {sets}'
    if sources:
        result += f"\nFROM {', '.join(sources)}"
    conditions = _join_predicates(node, dialect)
    if node.where is not None:
        conditions.append(_emit_expression(node.where, dialect))
    if conditions:
        result += f"\nWHERE {' AND '.join(conditions)}"
    return result

def _emit_update_mysql_join(node: UpdateStatement, target: TableRef, assignments: list[tuple[str, str]], dialect: str) -> str:
    """MySQL: UPDATE t JOIN s ON ... SET t.c = s.c [WHERE ...]."""
    target_sql = _emit_table_ref(target, dialect)
    joins_sql = ''.join((f'\n{_emit_join(j, dialect)}' for j in node.joins))
    sets = ', '.join((f'{col} = {val}' for col, val in assignments))
    result = f'UPDATE {target_sql}{joins_sql}\nSET {sets}'
    if node.where is not None:
        result += f'\nWHERE {_emit_expression(node.where, dialect)}'
    return result

def _emit_update_tsql_from(node: UpdateStatement, assignments: list[tuple[str, str]], dialect: str) -> str:
    """T-SQL: UPDATE t SET t.c = s.c FROM t JOIN s ON ... [WHERE ...]."""
    table = _emit_table_ref(node.table, dialect)
    sets = ', '.join((f'{col} = {val}' for col, val in assignments))
    result = f'UPDATE {table}\nSET {sets}'
    if node.from_clause is not None:
        from_sql = _emit_table_ref(node.from_clause, dialect)
        joins_sql = ''.join((f'\n{_emit_join(j, dialect)}' for j in node.joins))
        result += f'\nFROM {from_sql}{joins_sql}'
    if node.where is not None:
        result += f'\nWHERE {_emit_expression(node.where, dialect)}'
    return result

def _emit_update_oracle_subquery(node: UpdateStatement, target: TableRef, assignments: list[tuple[str, str]]) -> str:
    """Oracle has no UPDATE ... FROM; use a correlated-subquery UPDATE.

    Each assigned value is rewritten as ``(SELECT <expr> FROM <sources>
    WHERE <first join pred>)`` and an EXISTS guard limits the update to rows
    that have a match. The first join's ON is the predicate correlating the
    sources to the update target; any further joins chain *between* sources,
    so they move inside the subquery's FROM. Falls back to a documented
    comment only for a join without an ON condition.
    """
    dialect = 'oracle'
    target_sql = _emit_table_ref(target, dialect)
    if not node.joins or any((j.condition is None for j in node.joins)):
        original = _emit_update_tsql_from(node, assignments, dialect)
        commented = _comment_block(original)
        return '-- UNIQUE: Oracle has no UPDATE ... FROM and this join shape (no ON condition) cannot become a correlated subquery; rewrite as a MERGE. Original:\n' + commented
    first, rest = (node.joins[0], node.joins[1:])
    source_sql = _emit_join_table_ref(first.table, dialect)
    for j in rest:
        source_sql += f' {_emit_join(j, dialect)}'
    assert first.condition is not None
    pred = _emit_expression(first.condition, dialect)
    set_items = ', '.join((f'{col} = (SELECT {val} FROM {source_sql} WHERE {pred})' for col, val in assignments))
    result = f'UPDATE {target_sql}\nSET {set_items}'
    conditions = [f'EXISTS (SELECT 1 FROM {source_sql} WHERE {pred})']
    if node.where is not None:
        conditions.append(_emit_expression(node.where, dialect))
    result += f"\nWHERE {' AND '.join(conditions)}"
    return result

def _emit_delete(node: DeleteStatement, dialect: str) -> str:
    """Emit a DELETE statement."""
    table = _emit_table_ref(node.table, dialect)
    result = f'DELETE FROM {table}'
    if node.where:
        result += f'\nWHERE {_emit_expression(node.where, dialect)}'
    return result

def _emit_enum_type(col: ColumnDefinition, dialect: str) -> tuple[str, str, str]:
    """Render a MySQL ENUM/SET column type for *dialect*.

    Returns ``(type_sql, inline_check_sql, trailing_note)``. MySQL keeps the
    native type. Elsewhere ENUM becomes VARCHAR sized to the longest value
    plus an inline CHECK carrying the value-list semantics; SET (an unordered
    combination of values) has no CHECK equivalent, so it becomes a VARCHAR
    wide enough for all values with a documented carrier note.
    """
    values = col.data_type.values
    quoted_values = ', '.join(("'" + v.replace("'", "''") + "'" for v in values))
    kind = col.data_type.name.upper()
    if dialect == 'mysql':
        return (f'{kind}({quoted_values})', '', '')
    varchar = _portable_type_name('VARCHAR', dialect)
    col_name = _ident(col.name, col.quoted, dialect)
    if kind == 'ENUM':
        max_len = max((len(v) for v in values))
        return (f'{varchar}({max_len})', f' CHECK ({col_name} IN ({quoted_values}))', '')
    total_len = sum((len(v) for v in values)) + max(len(values) - 1, 0)
    note = f'-- UNIQUE: MySQL SET type on {col_name} has no {dialect} equivalent; stored as {varchar}({total_len}). Allowed members: {quoted_values}'
    return (f'{varchar}({total_len})', '', note)

def _emit_create_table(node: CreateTableStatement, dialect: str) -> str:
    """Emit a CREATE TABLE statement."""
    table = _emit_table_ref(node.table, dialect)
    temp = 'TEMPORARY ' if node.temporary else ''
    inline_exists = ''
    tsql_guard = ''
    if node.if_not_exists:
        if dialect == 'tsql':
            tsql_guard = f"IF OBJECT_ID(N'{_object_id_name(node.table)}', N'U') IS NULL\n"
        else:
            inline_exists = 'IF NOT EXISTS '
    exists = inline_exists
    if node.as_select:
        select = _emit_select(node.as_select, dialect)
        return f'{tsql_guard}CREATE {temp}TABLE {exists}{table} AS\n{select}'
    if node.columns:
        col_defs = []
        set_type_notes: list[str] = []
        for col in node.columns:
            check = ''
            if col.data_type.name.upper() in ('ENUM', 'SET') and col.data_type.values:
                dtype, check, note = _emit_enum_type(col, dialect)
                if note:
                    set_type_notes.append(note)
            else:
                dtype = _portable_type_name(col.data_type.name, dialect)
                skip_params = dialect in ('postgresql', 'tsql') and dtype.upper() in ('SMALLINT', 'INT', 'INTEGER', 'BIGINT', 'TINYINT') or (dialect == 'postgresql' and dtype.upper() in ('BYTEA', 'BLOB')) or (dialect == 'oracle' and dtype.upper() in ('BLOB', 'CLOB', 'NCLOB'))
                if col.data_type.params and '(' not in dtype and (not skip_params):
                    dtype += f"({', '.join((str(p) for p in col.data_type.params))})"
                if not col.data_type.params:
                    _base = dtype.upper().split('(')[0]
                    _bigtext = _BARE_CHAR_BIGTEXT.get(dialect, {}).get(_base)
                    if _bigtext:
                        dtype = _bigtext
                    elif _base in ('VARBINARY', 'BINARY', 'RAW') and '(' not in dtype and (dialect in ('mysql', 'oracle')):
                        dtype = 'BLOB'
            pk = ' PRIMARY KEY' if col.primary_key else ''
            unique = ' UNIQUE' if col.unique else ''
            default = ''
            if col.default is not None:
                default_sql = _emit_expression(col.default, dialect)
                if dialect == 'oracle':
                    default_sql = re.sub('(?i)\\bNEWSEQUENTIALID\\s*\\(\\s*\\)', 'SYS_GUID()', default_sql)
                    default_sql = re.sub('(?i)\\bNEWID\\s*\\(\\s*\\)', 'SYS_GUID()', default_sql)
                elif dialect == 'mysql':
                    default_sql = re.sub('(?i)\\b(?:NEWSEQUENTIALID|NEWID)\\s*\\(\\s*\\)', '(UUID())', default_sql)
                elif dialect == 'postgresql':
                    default_sql = re.sub('(?i)\\b(?:NEWSEQUENTIALID|NEWID)\\s*\\(\\s*\\)', 'gen_random_uuid()', default_sql)
                if dialect in ('postgresql', 'oracle'):
                    default_sql = re.sub('(?i)\\bCURRENT_TIMESTAMP\\s*\\(\\s*\\)', 'CURRENT_TIMESTAMP', default_sql)
                if dialect == 'postgresql' and dtype.upper().split('(')[0] == 'BYTEA' and re.search('(?i)\\bgen_random_uuid\\s*\\(\\s*\\)', default_sql):
                    default_sql = re.sub('(?i)\\bgen_random_uuid\\s*\\(\\s*\\)', "DECODE(REPLACE(gen_random_uuid()::TEXT, '-', ''), 'hex')", default_sql)
                if dialect == 'postgresql' and dtype.upper() == 'BOOLEAN':
                    m_bool = re.fullmatch('\\(*\\s*([01])\\s*\\)*', default_sql)
                    if m_bool:
                        default_sql = 'TRUE' if m_bool.group(1) == '1' else 'FALSE'
                if dialect in ('oracle', 'tsql') and dtype.upper().split('(')[0] in ('RAW', 'BLOB', 'VARBINARY', 'BINARY') and re.fullmatch("'[^']*'", default_sql.strip()):
                    default_sql = ''
                default = f' DEFAULT {default_sql}' if default_sql else ''
            _serial_base = {'SMALLSERIAL': 'SMALLINT', 'SERIAL2': 'SMALLINT', 'SERIAL': 'INTEGER', 'SERIAL4': 'INTEGER', 'BIGSERIAL': 'BIGINT', 'SERIAL8': 'BIGINT'}
            is_serial = col.data_type.name.upper() in _serial_base
            if is_serial and dialect != 'postgresql':
                dtype = _portable_type_name(_serial_base[col.data_type.name.upper()], dialect)
            identity = ''
            if col.identity or (is_serial and dialect != 'postgresql'):
                if dialect == 'mysql':
                    identity = ' AUTO_INCREMENT'
                elif dialect == 'postgresql':
                    dtype = 'BIGSERIAL' if dtype.upper() == 'BIGINT' else 'SERIAL'
                    identity = ''
                elif dialect == 'tsql':
                    identity = ' IDENTITY(1,1)'
                else:
                    identity = ' GENERATED BY DEFAULT AS IDENTITY'
            if dialect == 'oracle':
                nullable = '' if col.nullable or col.identity else ' NOT NULL'
                col_name = _ident(col.name, col.quoted, dialect)
                col_defs.append(f'  {col_name} {dtype}{identity}{default}{nullable}{pk}{unique}{check}')
            else:
                nullable = '' if col.nullable else ' NOT NULL'
                col_name = _ident(col.name, col.quoted, dialect)
                col_defs.append(f'  {col_name} {dtype}{identity}{nullable}{default}{pk}{unique}{check}')
        trailing_comments: list[str] = list(set_type_notes)
        for constraint in node.table_constraints:
            emitted = _emit_passthrough_inline(constraint, dialect)
            if emitted.lstrip().startswith('--'):
                trailing_comments.append(emitted.strip())
            else:
                col_defs.append(f'  {emitted}')
        cols = ',\n'.join(col_defs)
        result = f'{tsql_guard}CREATE {temp}TABLE {exists}{table} (\n{cols}\n)'
        if node.inherits_clause:
            result += f'\n{node.inherits_clause}'
        if trailing_comments:
            result += '\n' + '\n'.join(trailing_comments)
        return result
    bare = f'{tsql_guard}CREATE {temp}TABLE {exists}{table}'
    if node.partition_of_clause:
        return f'{bare} {node.partition_of_clause}'
    if node.inherits_clause:
        return f'{bare} () {node.inherits_clause}'
    return bare

def _emit_passthrough_inline(node: PassthroughSQL, dialect: str) -> str:
    """Re-transpile a constraint fragment for inclusion inside CREATE TABLE.

    Wraps the fragment in a throwaway table so sqlglot will transpile the
    constraint, then extracts it back out. Falls back to the raw fragment.
    """
    read = sqlglot_dialect_name(node.source_dialect)
    write = sqlglot_dialect_name(dialect)
    fragment_sql = node.sql
    if node.source_dialect == 'tsql' and dialect != 'tsql':
        fragment_sql = re.sub('(?i)\\b(NON)?CLUSTERED\\s+', '', fragment_sql)
        fragment_sql = re.sub('(?i)\\s*WITH\\s*\\([^)]*\\)', '', fragment_sql)
        fragment_sql = re.sub('(?i)\\s+ON\\s+(?:\\[[^\\]]+\\]|\\w+)\\s*$', '', fragment_sql)
        if re.match('(?i)\\s*(CONSTRAINT|PRIMARY\\s+KEY|UNIQUE)\\b', fragment_sql):
            fragment_sql = re.sub('(?i)\\s+(?:ASC|DESC)\\b', '', fragment_sql)
    try:
        wrapped = f'CREATE TABLE __c__ (x INT, {fragment_sql})'
        out = sqlglot.transpile(wrapped, read=read, write=write)[0]
        inner = out[out.index('(') + 1:out.rindex(')')]
        parts = inner.split(',', 1)
        if len(parts) == 2:
            fragment = parts[1].strip()
            is_generated = re.search('(?i)\\bGENERATED\\s+ALWAYS\\s+AS\\b|\\bAS\\s*\\(', fragment)
            has_type = re.search('(?i)^\\s*[\\w\\[\\]\\".]+\\s+(INT|INTEGER|BIGINT|SMALLINT|TINYINT|NUMERIC|DECIMAL|FLOAT|REAL|DOUBLE|CHAR|VARCHAR|NVARCHAR|TEXT|DATE|TIMESTAMP|BOOLEAN|NUMBER|RAW)', fragment)
            if dialect in ('postgresql', 'oracle', 'mysql') and is_generated and (not has_type):
                col_name = fragment.split()[0]
                return f'-- UNIQUE: {dialect} requires an explicit type for the generated column {col_name}; original computed column: {node.sql}'
            if dialect in ('oracle', 'postgresql'):
                fragment = re.sub('(?i)\\s+NULLS\\s+(?:FIRST|LAST)', '', fragment)
            if dialect != 'tsql' and re.match('(?i)\\s*(CONSTRAINT|PRIMARY\\s+KEY|UNIQUE)\\b', fragment):
                fragment = re.sub('(?i)\\s+(?:ASC|DESC)\\b', '', fragment)
            if dialect != 'mysql':
                fragment = re.sub('(?i)^UNIQUE\\s+(?:KEY\\s+|INDEX\\s+)?([`\\"\\[\\]\\w]+)\\s*\\(', 'CONSTRAINT \\1 UNIQUE (', fragment)
            if dialect in ('oracle', 'mysql', 'postgresql'):
                fragment = _strip_dbo_from_references(fragment)
            return fragment
    except Exception as e:
        logger.warning('constraint transpile error: %s', e)
    return node.sql

def _emit_create_view(node: CreateViewStatement, dialect: str) -> str:
    """Emit a CREATE VIEW statement."""
    name = _emit_table_ref(node.name, dialect)
    if node.or_replace:
        replace = 'OR ALTER ' if dialect == 'tsql' else 'OR REPLACE '
    else:
        replace = ''
    query = _emit_select(node.query, dialect)
    return f'CREATE {replace}VIEW {name} AS\n{query}'

def _emit_drop(node: DropStatement, dialect: str) -> str:
    """Emit a DROP statement.

    DROP INDEX differs per engine (audit B2): T-SQL and MySQL require the
    owning table (``ON tbl``); Oracle/PostgreSQL take only the index name.
    When the target requires a table the source did not carry, the statement
    degrades to a documented carrier — never invalid SQL.
    """
    name = _emit_table_ref(node.name, dialect)
    exists = 'IF EXISTS ' if node.if_exists else ''
    cascade = ' CASCADE' if node.cascade else ''
    if node.object_type == 'SEQUENCE' and dialect == 'mysql':
        return f'-- UNIQUE: MySQL has no sequences (use an AUTO_INCREMENT column); original preserved:\n-- DROP SEQUENCE {exists}{name}'
    if node.object_type == 'TYPE' and dialect == 'mysql':
        return f'-- UNIQUE: MySQL has no user-defined types; original preserved:\n-- DROP TYPE {exists}{name}'
    if node.object_type == 'INDEX':
        if dialect in ('tsql', 'mysql'):
            if not node.on_table:
                return f'-- UNIQUE: {dialect} DROP INDEX requires the owning table, which the source statement does not carry; original preserved:\n-- DROP INDEX {exists}{name}'
            if dialect == 'mysql':
                return f'DROP INDEX {name} ON {node.on_table}'
            return f'DROP INDEX {exists}{name} ON {node.on_table}'
        return f'DROP INDEX {exists}{name}'
    return f'DROP {node.object_type} {exists}{name}{cascade}'

def _emit_expression(node: ASTNode, dialect: str) -> str:
    """Emit an expression node as SQL text."""
    if isinstance(node, ColumnRef):
        name = _ident(node.name, node.quoted, dialect)
        if node.table:
            table = _ident(node.table, node.table_quoted, dialect)
            return f'{table}.{name}'
        return name
    if isinstance(node, Star):
        if node.table:
            return f'{node.table}.*'
        return '*'
    if isinstance(node, Literal):
        if node.value is None:
            return 'NULL'
        if node.dtype == 'boolean':
            if dialect in ('tsql', 'oracle'):
                return '1' if node.value else '0'
            return 'TRUE' if node.value else 'FALSE'
        if node.dtype == 'string' or (node.dtype == 'unknown' and isinstance(node.value, str)):
            escaped = str(node.value).replace("'", "''")
            return f"'{escaped}'"
        return str(node.value)
    if isinstance(node, Alias):
        inner = _emit_expression(node.expression, dialect)
        return f'{inner} AS {_ident(node.name, node.quoted, dialect)}'
    if isinstance(node, FunctionCall):
        return _emit_function(node, dialect)
    if isinstance(node, BinaryOp):
        return _emit_binary(node, dialect)
    if isinstance(node, UnaryOp):
        return _emit_unary(node, dialect)
    if isinstance(node, CaseExpression):
        return _emit_case(node, dialect)
    if isinstance(node, CastExpression):
        if dialect == 'oracle' and node.target_type.name.upper() in ('DATE', 'TIMESTAMP') and isinstance(node.expression, Literal) and isinstance(node.expression.value, str):
            lit = _oracle_date_literal(node.expression.value.strip())
            if lit is not None:
                return lit
        inner = _emit_expression(node.expression, dialect)
        dtype = node.target_type.name
        mapped = _CAST_TYPE_MAP.get(dialect, {}).get(dtype.upper())
        if mapped:
            dtype = mapped
            if node.target_type.params and mapped in ('VARCHAR2', 'NVARCHAR2', 'CHAR'):
                dtype += f"({', '.join((str(p) for p in node.target_type.params))})"
        elif node.target_type.params:
            dtype += f"({', '.join((str(p) for p in node.target_type.params))})"
        return f'CAST({inner} AS {dtype})'
    if isinstance(node, SubqueryExpression):
        return f'({_emit_select(node.query, dialect)})'
    if isinstance(node, ExpressionList):
        inner = ', '.join((_emit_expression(item, dialect) for item in node.items))
        return f'({inner})'
    if isinstance(node, WindowFunction):
        return _emit_window(node, dialect)
    if isinstance(node, TableRef):
        return _emit_table_ref(node, dialect)
    if isinstance(node, RawSQL):
        return node.sql
    return str(node)

def _emit_date_add(node: FunctionCall, dialect: str) -> str | None:
    """Emit DATE_ADD/DATE_SUB/DATEADD with the target's own idiom.

    The IR canonical form is ``(ts, n, unit)``. Emitting the 3-argument
    ``DATE_ADD(ts, 7, DAY)`` form is invalid on every engine (audit
    2026-07-02, S1-4); each target needs its native spelling.
    """
    if len(node.args) != 3:
        return None
    unit = _date_unit_name(node.args[2])
    if unit is None:
        return None
    ts = _emit_expression(_unwrap_sqlglot_wrappers(node.args[0]), dialect)
    amount = node.args[1]
    literal_n: str | None = None
    if isinstance(amount, Literal) and re.fullmatch('-?\\d+', str(amount.value)):
        literal_n = str(amount.value)
    n = literal_n if literal_n is not None else _emit_expression(amount, dialect)
    sub = node.name.upper() == 'DATE_SUB'
    if dialect == 'mysql':
        fn = 'DATE_SUB' if sub else 'DATE_ADD'
        return f'{fn}({ts}, INTERVAL {n} {unit})'
    if dialect == 'tsql':
        signed = (f'-{n}' if literal_n is not None else f'-({n})') if sub else n
        return f'DATEADD({unit}, {signed}, {ts})'
    if dialect == 'postgresql':
        op = '-' if sub else '+'
        if literal_n is not None:
            return f"{ts} {op} INTERVAL '{n} {unit}'"
        return f"{ts} {op} ({n}) * INTERVAL '1 {unit}'"
    if dialect == 'oracle':
        if unit in ('MONTH', 'YEAR'):
            if unit == 'MONTH':
                months = n
            elif literal_n is not None:
                months = str(int(literal_n) * 12)
            else:
                months = f'({n}) * 12'
            if sub:
                signed = f'-{months}' if literal_n is not None else f'-({months})'
            else:
                signed = months
            return f'ADD_MONTHS({ts}, {signed})'
        op = '-' if sub else '+'
        if unit == 'WEEK':
            days = str(int(literal_n) * 7) if literal_n is not None else f'({n}) * 7'
            return f"{ts} {op} NUMTODSINTERVAL({days}, 'DAY')"
        return f"{ts} {op} NUMTODSINTERVAL({n}, '{unit}')"
    return None

def _emit_date_diff(node: FunctionCall, dialect: str) -> str | None:
    """Emit DATEDIFF with T-SQL boundary-count semantics per target.

    IR canonical argument order is ``(end, start, unit)``. T-SQL DATEDIFF
    counts unit-boundary crossings, so month/year use calendar arithmetic
    rather than elapsed-interval functions (audit 2026-07-02, S1-4).
    """
    if len(node.args) == 2:
        end = _emit_expression(node.args[0], dialect)
        start = _emit_expression(node.args[1], dialect)
        if dialect == 'mysql':
            return f'DATEDIFF({end}, {start})'
        if dialect == 'tsql':
            return f'DATEDIFF(DAY, {start}, {end})'
        return f'(CAST({end} AS DATE) - CAST({start} AS DATE))'
    if len(node.args) != 3:
        return None
    unit = _date_unit_name(node.args[2])
    if unit is None:
        return None
    end = _emit_expression(_unwrap_sqlglot_wrappers(node.args[0]), dialect)
    start = _emit_expression(_unwrap_sqlglot_wrappers(node.args[1]), dialect)
    if dialect == 'tsql':
        return f'DATEDIFF({unit}, {start}, {end})'
    if dialect == 'mysql':
        if unit == 'DAY':
            return f'DATEDIFF({end}, {start})'
        if unit == 'WEEK':
            return f'FLOOR(DATEDIFF({end}, {start}) / 7)'
        if unit == 'MONTH':
            return f'((YEAR({end}) * 12 + MONTH({end})) - (YEAR({start}) * 12 + MONTH({start})))'
        if unit == 'YEAR':
            return f'(YEAR({end}) - YEAR({start}))'
        k = {'HOUR': 3600, 'MINUTE': 60, 'SECOND': 1}[unit]
        return f'(FLOOR(UNIX_TIMESTAMP({end}) / {k}) - FLOOR(UNIX_TIMESTAMP({start}) / {k}))'
    if dialect == 'postgresql':
        if unit == 'DAY':
            return f'(CAST({end} AS DATE) - CAST({start} AS DATE))'
        if unit == 'WEEK':
            return f'FLOOR((CAST({end} AS DATE) - CAST({start} AS DATE)) / 7)'
        if unit == 'MONTH':
            return f'((EXTRACT(YEAR FROM {end}) * 12 + EXTRACT(MONTH FROM {end})) - (EXTRACT(YEAR FROM {start}) * 12 + EXTRACT(MONTH FROM {start})))'
        if unit == 'YEAR':
            return f'(EXTRACT(YEAR FROM {end}) - EXTRACT(YEAR FROM {start}))'
        k = {'HOUR': 3600, 'MINUTE': 60, 'SECOND': 1}[unit]
        return f'(FLOOR(EXTRACT(EPOCH FROM {end}) / {k}) - FLOOR(EXTRACT(EPOCH FROM {start}) / {k}))'
    if dialect == 'oracle':
        if unit == 'DAY':
            return f'(TRUNC(CAST({end} AS DATE)) - TRUNC(CAST({start} AS DATE)))'
        if unit == 'WEEK':
            return f'FLOOR((TRUNC(CAST({end} AS DATE)) - TRUNC(CAST({start} AS DATE))) / 7)'
        if unit == 'MONTH':
            return f'((EXTRACT(YEAR FROM {end}) * 12 + EXTRACT(MONTH FROM {end})) - (EXTRACT(YEAR FROM {start}) * 12 + EXTRACT(MONTH FROM {start})))'
        if unit == 'YEAR':
            return f'(EXTRACT(YEAR FROM {end}) - EXTRACT(YEAR FROM {start}))'
        trunc_fmt = {'HOUR': 'HH24', 'MINUTE': 'MI'}.get(unit)
        mult = {'HOUR': 24, 'MINUTE': 1440, 'SECOND': 86400}[unit]
        if trunc_fmt:
            return f"ROUND((TRUNC(CAST({end} AS DATE), '{trunc_fmt}') - TRUNC(CAST({start} AS DATE), '{trunc_fmt}')) * {mult})"
        return f'ROUND((CAST({end} AS DATE) - CAST({start} AS DATE)) * {mult})'
    return None

def _emit_group_concat(node: FunctionCall, dialect: str) -> str | None:
    """Emit the string-aggregation family in the target's own spelling.

    IR canonical form: ``GROUP_CONCAT(expr[, separator])``. An Oracle LISTAGG
    source may carry its WITHIN GROUP ordering folded into the first argument
    as RawSQL ("expr ORDER BY ...").
    """
    first = node.args[0]
    expr_sql: str
    order_sql: str | None = None
    if isinstance(first, RawSQL) and ' ORDER BY ' in first.sql:
        expr_sql, order_sql = first.sql.split(' ORDER BY ', 1)
        expr_sql = expr_sql.strip()
        order_sql = re.sub('\\s+NULLS\\s+(FIRST|LAST)\\s*$', '', order_sql.strip())
    else:
        expr_sql = _emit_expression(first, dialect)
    sep: str | None = None
    if len(node.args) > 1:
        sep_node = node.args[1]
        if isinstance(sep_node, Literal) and isinstance(sep_node.value, str):
            sep = sep_node.value
        else:
            return None
    distinct = 'DISTINCT ' if node.distinct else ''

    def quoted(s: str) -> str:
        return "'" + s.replace("'", "''") + "'"
    if dialect == 'mysql':
        order = f' ORDER BY {order_sql}' if order_sql else ''
        separator = f' SEPARATOR {quoted(sep)}' if sep is not None else ''
        return f'GROUP_CONCAT({distinct}{expr_sql}{order}{separator})'
    if dialect == 'postgresql':
        order = f' ORDER BY {order_sql}' if order_sql else ''
        return f"STRING_AGG({distinct}{expr_sql}, {quoted(sep or ',')}{order})"
    if dialect == 'tsql':
        within = f' WITHIN GROUP (ORDER BY {order_sql})' if order_sql else ''
        return f"STRING_AGG({expr_sql}, {quoted(sep or ',')}){within}"
    if dialect == 'oracle':
        order = order_sql or expr_sql
        return f"LISTAGG({distinct}{expr_sql}, {quoted(sep or ',')}) WITHIN GROUP (ORDER BY {order})"
    return None

def _emit_function(node: FunctionCall, dialect: str) -> str:
    """Emit a function call."""
    fn_name = node.name.upper()
    if fn_name in _SQLGLOT_WRAPPERS and len(node.args) == 1:
        return _emit_expression(node.args[0], dialect)
    if fn_name in ('DATE_ADD', 'DATE_SUB', 'DATEADD'):
        emitted = _emit_date_add(node, dialect)
        if emitted is not None:
            return emitted
    if fn_name in ('DATEDIFF', 'TIMESTAMPDIFF'):
        emitted = _emit_date_diff(node, dialect)
        if emitted is not None:
            return emitted
    if fn_name in ('GROUP_CONCAT', 'STRING_AGG', 'LISTAGG') and node.args:
        emitted = _emit_group_concat(node, dialect)
        if emitted is not None:
            return emitted
    stat_map = _STAT_AGGREGATE_MAP.get(fn_name)
    if stat_map is not None and len(node.args) == 1:
        arg = _emit_expression(node.args[0], dialect)
        return f'{stat_map.get(dialect, fn_name)}({arg})'
    if fn_name in ('LOGICAL_OR', 'BOOL_OR', 'LOGICAL_AND', 'BOOL_AND', 'EVERY') and len(node.args) == 1:
        arg = _emit_expression(node.args[0], dialect)
        agg = 'MAX' if fn_name in ('LOGICAL_OR', 'BOOL_OR') else 'MIN'
        if dialect == 'tsql':
            return f'{agg}(CAST({arg} AS INT))'
        if dialect == 'mysql':
            return f'{agg}({arg})'
        if dialect == 'oracle':
            return f'{agg}(CASE WHEN {arg} THEN 1 ELSE 0 END)'
        return f"{('BOOL_OR' if agg == 'MAX' else 'BOOL_AND')}({arg})"
    if fn_name in ('IF', 'IIF') and len(node.args) == 3:
        cond, then_v, else_v = (_emit_expression(a, dialect) for a in node.args)
        if dialect == 'tsql':
            return f'IIF({cond}, {then_v}, {else_v})'
        if dialect == 'mysql':
            return f'IF({cond}, {then_v}, {else_v})'
        return f'CASE WHEN {cond} THEN {then_v} ELSE {else_v} END'
    if fn_name == 'EXTRACT' and len(node.args) == 2:
        part = _emit_expression(node.args[0], dialect).strip('\'"').upper()
        value = _emit_expression(node.args[1], dialect)
        if dialect == 'tsql':
            return f'DATEPART({part}, {value})'
        return f'EXTRACT({part} FROM {value})'
    if fn_name == 'NVL2' and len(node.args) == 3:
        a, b, c = (_emit_expression(x, dialect) for x in node.args)
        if dialect == 'oracle':
            return f'NVL2({a}, {b}, {c})'
        return f'CASE WHEN {a} IS NOT NULL THEN {b} ELSE {c} END'
    if fn_name in ('DECODE', 'DECODE_CASE') and len(node.args) >= 3:
        parts = [_emit_expression(x, dialect) for x in node.args]
        if dialect == 'oracle':
            return f"DECODE({', '.join(parts)})"
        subject, whens, i = (parts[0], [], 1)
        while i + 1 < len(parts):
            whens.append(f'WHEN {subject} = {parts[i]} THEN {parts[i + 1]}')
            i += 2
        default = f' ELSE {parts[i]}' if i < len(parts) else ''
        return f"CASE {' '.join(whens)}{default} END"
    if fn_name in ('CURRENT_DATE', 'CURDATE') and (not node.args):
        return CURRENT_DATE_EXPR.get(dialect, 'CURRENT_DATE')
    if fn_name == 'TRUNC' and len(node.args) == 1 and isinstance(node.args[0], Literal) and (str(node.args[0].dtype) in ('integer', 'number')):
        x = _emit_expression(node.args[0], dialect)
        if dialect == 'tsql':
            return f'ROUND({x}, 0, 1)'
        if dialect == 'mysql':
            return f'TRUNCATE({x}, 0)'
    if fn_name == 'TRUNC' and len(node.args) == 2 and isinstance(node.args[1], Literal) and (str(node.args[1].dtype) in ('integer', 'number')):
        x = _emit_expression(node.args[0], dialect)
        d = _emit_expression(node.args[1], dialect)
        if dialect == 'tsql':
            return f'ROUND({x}, {d}, 1)'
        if dialect == 'mysql':
            return f'TRUNCATE({x}, {d})'
        return f'TRUNC({x}, {d})'
    if fn_name in ('EMPTY_BLOB', 'EMPTY_CLOB') and (not node.args):
        if dialect == 'oracle':
            return f'{fn_name}()'
        if fn_name == 'EMPTY_BLOB':
            return {'tsql': '0x', 'postgresql': "''::BYTEA", 'mysql': "x''"}[dialect]
        return "''"
    if fn_name in ('LPAD', 'RPAD') and len(node.args) in (2, 3):
        s = _emit_expression(node.args[0], dialect)
        length = _emit_expression(node.args[1], dialect)
        pad = _emit_expression(node.args[2], dialect) if len(node.args) == 3 else "' '"
        if dialect == 'tsql':
            if fn_name == 'RPAD':
                return f'LEFT({s} + REPLICATE({pad}, {length}), {length})'
            return f'RIGHT(REPLICATE({pad}, {length}) + {s}, {length})'
        return f'{fn_name}({s}, {length}, {pad})'
    if fn_name == 'CONVERT' and len(node.args) == 2 and isinstance(node.args[0], RawSQL):
        target_type = node.args[0].sql.strip()
        value = _emit_expression(node.args[1], dialect)
        if dialect == 'tsql':
            return f'CONVERT({target_type}, {value})'
        if dialect == 'mysql':
            target_type = re.sub('(?i)^VARCHAR\\b', 'CHAR', target_type)
            target_type = re.sub('(?i)^(?:INT|INTEGER|BIGINT)\\b', 'SIGNED', target_type)
        return f'CAST({value} AS {target_type})'
    if fn_name == 'DATE_TRUNC' and len(node.args) == 2 and isinstance(node.args[0], (Literal, RawSQL)):
        raw_part = str(node.args[0].value) if isinstance(node.args[0], Literal) else node.args[0].sql.strip("'")
        trunc_part = {'DD': 'day', 'DAY': 'day', 'DDD': 'day', 'MM': 'month', 'MON': 'month', 'MONTH': 'month', 'YYYY': 'year', 'YY': 'year', 'YEAR': 'year', 'HH': 'hour', 'HH24': 'hour', 'MI': 'minute', 'MINUTE': 'minute', 'Q': 'quarter', 'QUARTER': 'quarter', 'WW': 'week', 'WEEK': 'week'}.get(raw_part.upper())
        if trunc_part is not None:
            value = _emit_expression(node.args[1], dialect)
            if dialect == 'postgresql':
                return f"DATE_TRUNC('{trunc_part}', {value})"
            if dialect == 'oracle':
                if trunc_part == 'day':
                    return f'TRUNC({value})'
                return f"TRUNC({value}, '{raw_part}')"
            if dialect == 'tsql':
                if trunc_part == 'day':
                    return f'CAST({value} AS DATE)'
                return f'DATETRUNC({trunc_part}, {value})'
            if dialect == 'mysql':
                if trunc_part == 'day':
                    return f'DATE({value})'
                if trunc_part == 'month':
                    return f"DATE_FORMAT({value}, '%Y-%m-01')"
                if trunc_part == 'year':
                    return f"DATE_FORMAT({value}, '%Y-01-01')"
    if fn_name == 'TO_CHAR' and len(node.args) == 1 and (dialect != 'oracle'):
        value = _emit_expression(node.args[0], dialect)
        if dialect == 'tsql':
            return f'CONVERT(VARCHAR(4000), {value})'
        if dialect == 'mysql':
            return f'CAST({value} AS CHAR)'
        return f'CAST({value} AS TEXT)'
    if fn_name == 'TO_CHAR' and len(node.args) == 2 and isinstance(node.args[1], Literal):
        value = _emit_expression(node.args[0], dialect)
        fmt = str(node.args[1].value)
        if dialect in ('oracle', 'postgresql'):
            return f"TO_CHAR({value}, '{fmt}')"
        if dialect == 'mysql':
            my = _convert_date_format(fmt, 'oracle', 'mysql')
            return f"DATE_FORMAT({value}, '{my}')"
        return f"FORMAT({value}, '{_convert_date_format(fmt, 'oracle', 'tsql')}')"
    if fn_name == 'TIME_TO_STR' and len(node.args) == 2 and isinstance(node.args[1], Literal):
        value = _emit_expression(node.args[0], dialect)
        fmt = str(node.args[1].value)
        if dialect == 'mysql':
            my = _convert_date_format(fmt, 'python', 'mysql')
            return f"DATE_FORMAT({value}, '{my}')"
        if dialect in ('oracle', 'postgresql'):
            return f"TO_CHAR({value}, '{_convert_date_format(fmt, 'python', 'oracle')}')"
        return f"FORMAT({value}, '{_convert_date_format(fmt, 'python', 'tsql')}')"
    if fn_name == 'STR_TO_DATE' and len(node.args) == 2 and isinstance(node.args[1], Literal):
        value = _emit_expression(node.args[0], dialect)
        fmt = str(node.args[1].value)
        if dialect == 'mysql':
            my = _convert_date_format(fmt, 'python', 'mysql')
            return f"STR_TO_DATE({value}, '{my}')"
        if dialect in ('oracle', 'postgresql'):
            return f"TO_DATE({value}, '{_convert_date_format(fmt, 'python', 'oracle')}')"
        return f'CAST({value} AS DATE)'
    if dialect in ('oracle', 'mysql', 'postgresql') and '.' in node.name:
        node = _strip_dbo_function_name(node)
    if node.name.upper() == 'CURRENT_TIMESTAMP' and (not node.args):
        return CURRENT_TIMESTAMP_EXPR.get(dialect, 'CURRENT_TIMESTAMP')
    if node.name.upper() in ('SYSTIMESTAMP', 'SYSDATE', 'NOW') and (not node.args):
        return CURRENT_TIMESTAMP_EXPR.get(dialect, 'CURRENT_TIMESTAMP')
    if node.name.upper() == 'CHARINDEX' and len(node.args) >= 2:
        needle = _emit_expression(node.args[0], dialect)
        haystack = _emit_expression(node.args[1], dialect)
        start = _emit_expression(node.args[2], dialect) if len(node.args) > 2 else None
        if dialect == 'tsql':
            inner = f'{needle}, {haystack}' + (f', {start}' if start else '')
            return f'CHARINDEX({inner})'
        if dialect == 'mysql':
            inner = f'{needle}, {haystack}' + (f', {start}' if start else '')
            return f'LOCATE({inner})'
        if dialect == 'oracle':
            inner = f'{haystack}, {needle}' + (f', {start}' if start else '')
            return f'INSTR({inner})'
        if start:
            return f'(POSITION({needle} IN SUBSTRING({haystack} FROM {start})) + {start} - 1)'
        return f'POSITION({needle} IN {haystack})'
    name = _map_function_name(node.name, dialect)
    if dialect == 'tsql' and tsql_call_needs_schema(name):
        name = f'dbo.{name}'
    distinct = 'DISTINCT ' if node.distinct else ''
    args = ', '.join((_emit_expression(a, dialect) for a in node.args))
    return f'{name}({distinct}{args})'
_ORACLE_BITWISE = frozenset({BinaryOperator.BIT_AND, BinaryOperator.BIT_OR, BinaryOperator.BIT_XOR, BinaryOperator.BIT_LSHIFT, BinaryOperator.BIT_RSHIFT})
_BIN_PRECEDENCE = {BinaryOperator.OR: 1, BinaryOperator.AND: 2, BinaryOperator.EQ: 3, BinaryOperator.NEQ: 3, BinaryOperator.LT: 3, BinaryOperator.GT: 3, BinaryOperator.LTE: 3, BinaryOperator.GTE: 3, BinaryOperator.LIKE: 3, BinaryOperator.ILIKE: 3, BinaryOperator.IN: 3, BinaryOperator.NOT_IN: 3, BinaryOperator.BETWEEN: 3, BinaryOperator.BIT_OR: 4, BinaryOperator.BIT_XOR: 4, BinaryOperator.BIT_AND: 4, BinaryOperator.BIT_LSHIFT: 4, BinaryOperator.BIT_RSHIFT: 4, BinaryOperator.ADD: 5, BinaryOperator.SUB: 5, BinaryOperator.CONCAT: 5, BinaryOperator.MUL: 6, BinaryOperator.DIV: 6, BinaryOperator.MOD: 6}
_NON_ASSOCIATIVE = frozenset({BinaryOperator.SUB, BinaryOperator.DIV, BinaryOperator.MOD, BinaryOperator.BIT_LSHIFT, BinaryOperator.BIT_RSHIFT})

def _emit_operand(child: ASTNode, parent: BinaryOperator, dialect: str, right: bool=False) -> str:
    """Emit a binary operand, parenthesized when it binds weaker than *parent*."""
    text = _emit_expression(child, dialect)
    if isinstance(child, BinaryOp):
        child_prec = _BIN_PRECEDENCE[child.operator]
        parent_prec = _BIN_PRECEDENCE[parent]
        if child_prec < parent_prec or (right and child_prec == parent_prec and (parent in _NON_ASSOCIATIVE)):
            return f'({text})'
    return text

def _emit_binary(node: BinaryOp, dialect: str) -> str:
    """Emit a binary operation."""
    left = _emit_operand(node.left, node.operator, dialect)
    right = _emit_operand(node.right, node.operator, dialect, right=True)
    op_map = {BinaryOperator.EQ: '=', BinaryOperator.NEQ: '<>', BinaryOperator.LT: '<', BinaryOperator.GT: '>', BinaryOperator.LTE: '<=', BinaryOperator.GTE: '>=', BinaryOperator.AND: 'AND', BinaryOperator.OR: 'OR', BinaryOperator.ADD: '+', BinaryOperator.SUB: '-', BinaryOperator.MUL: '*', BinaryOperator.DIV: '/', BinaryOperator.MOD: '%', BinaryOperator.LIKE: 'LIKE', BinaryOperator.ILIKE: 'ILIKE', BinaryOperator.IN: 'IN', BinaryOperator.NOT_IN: 'NOT IN', BinaryOperator.BETWEEN: 'BETWEEN', BinaryOperator.CONCAT: '||', BinaryOperator.BIT_AND: '&', BinaryOperator.BIT_OR: '|', BinaryOperator.BIT_XOR: '^', BinaryOperator.BIT_LSHIFT: '<<', BinaryOperator.BIT_RSHIFT: '>>'}
    op = op_map[node.operator]
    if node.operator == BinaryOperator.CONCAT:
        if dialect == 'tsql':
            op = '+'
        elif dialect == 'mysql':
            return f'CONCAT({left}, {right})'
    if node.operator == BinaryOperator.MOD and dialect == 'oracle':
        return f'MOD({left}, {right})'
    if node.operator == BinaryOperator.BIT_XOR and dialect == 'postgresql':
        op = '#'
    if dialect == 'oracle' and node.operator in _ORACLE_BITWISE:
        if node.operator == BinaryOperator.BIT_AND:
            return f'BITAND({left}, {right})'
        if node.operator == BinaryOperator.BIT_OR:
            return f'({left} + {right} - BITAND({left}, {right}))'
        if node.operator == BinaryOperator.BIT_XOR:
            return f'({left} + {right} - 2 * BITAND({left}, {right}))'
        if node.operator == BinaryOperator.BIT_LSHIFT:
            return f'({left} * POWER(2, {right}))'
        if node.operator == BinaryOperator.BIT_RSHIFT:
            return f'FLOOR({left} / POWER(2, {right}))'
    return f'{left} {op} {right}'

def _emit_unary(node: UnaryOp, dialect: str) -> str:
    """Emit a unary operation."""
    operand = _emit_expression(node.operand, dialect)
    if isinstance(node.operand, BinaryOp) and node.operator in (UnaryOperator.NOT, UnaryOperator.NEGATIVE):
        operand = f'({operand})'
    if node.operator == UnaryOperator.NOT:
        return f'NOT {operand}'
    if node.operator == UnaryOperator.NEGATIVE:
        return f'-{operand}'
    if node.operator == UnaryOperator.IS_NULL:
        return f'{operand} IS NULL'
    if node.operator == UnaryOperator.IS_NOT_NULL:
        return f'{operand} IS NOT NULL'
    if node.operator == UnaryOperator.EXISTS:
        return f'EXISTS {operand}'
    return operand

def _emit_case(node: CaseExpression, dialect: str) -> str:
    """Emit a CASE expression."""
    parts = ['CASE']
    if node.operand:
        parts[0] += f' {_emit_expression(node.operand, dialect)}'
    for condition, result in node.whens:
        cond = _emit_expression(condition, dialect)
        res = _emit_expression(result, dialect)
        parts.append(f'  WHEN {cond} THEN {res}')
    if node.else_expr:
        parts.append(f'  ELSE {_emit_expression(node.else_expr, dialect)}')
    parts.append('END')
    return '\n'.join(parts)

def _emit_window(node: WindowFunction, dialect: str) -> str:
    """Emit a window function."""
    func = _emit_function(node.function, dialect)
    spec_parts: list[str] = []
    if node.window.partition_by:
        partition = ', '.join((_emit_expression(p, dialect) for p in node.window.partition_by))
        spec_parts.append(f'PARTITION BY {partition}')
    if node.window.order_by:
        order = ', '.join((_emit_order_item(o, dialect) for o in node.window.order_by))
        spec_parts.append(f'ORDER BY {order}')
    elif dialect == 'tsql' and re.match('(?i)\\s*(FIRST_VALUE|LAST_VALUE|LAG|LEAD|NTILE|ROW_NUMBER|RANK|DENSE_RANK|PERCENT_RANK|CUME_DIST)\\s*\\(', func):
        spec_parts.append('ORDER BY (SELECT NULL)')
    spec = ' '.join(spec_parts)
    return f'{func} OVER ({spec})'

def _emit_table_ref(node: TableRef, dialect: str | None=None) -> str:
    """Emit a table reference.

    When ``dialect`` is one of the non-T-SQL engines, the T-SQL default schema
    ``dbo`` is dropped: it names no real schema on Oracle/PostgreSQL and would
    name a non-existent database on MySQL. Passing ``dialect=None`` keeps the
    reference verbatim (used where the schema must be preserved, e.g. a T-SQL
    OBJECT_ID guard).
    """
    parts = []
    if node.database:
        parts.append(node.database)
    schema = node.schema
    if dialect in ('oracle', 'mysql', 'postgresql') and schema == 'dbo':
        schema = None
    if schema:
        parts.append(_ident(schema, node.schema_quoted, dialect))
    name = node.name
    if dialect == 'tsql' and (not name.startswith('#')):
        temp_tables = TEMP_TABLES.get()
        if temp_tables and name.lower() in temp_tables:
            name = f'#{name}'
    parts.append(_ident(name, node.quoted, dialect))
    result = '.'.join(parts)
    if node.alias:
        result += f' {node.alias}'
    return result

def _emit_join(join: JoinClause, dialect: str, left_name: str | None=None, merged_cols: dict[str, str] | None=None) -> str:
    """Emit a JOIN clause.

    ``left_name`` is the FROM relation's name/alias; with ``merged_cols``
    (shared across a SELECT's join chain, mapping USING column ->
    merged-column expression) it lets a ``USING (...)`` join be rewritten
    as an explicit ``ON`` for T-SQL, which has no USING syntax — chained
    joins included, where a later USING references the chain's MERGED
    column (COALESCE over the arms once a FULL join is involved).
    """
    type_map = {JoinType.INNER: 'INNER JOIN', JoinType.LEFT: 'LEFT JOIN', JoinType.RIGHT: 'RIGHT JOIN', JoinType.FULL: 'FULL OUTER JOIN', JoinType.CROSS: 'CROSS JOIN', JoinType.NATURAL: 'NATURAL JOIN', JoinType.LATERAL: 'LATERAL JOIN'}
    join_type = type_map.get(join.join_type, 'JOIN')
    if isinstance(join.table, SubqueryExpression):
        table = f'({_emit_select(join.table.query, dialect)})'
        alias = join.alias or join.table.alias
        if alias:
            table += f' {_ident(alias, False, dialect)}'
    else:
        table = _emit_table_ref(join.table, dialect)
        if join.alias and (not join.table.alias):
            table += f' {_ident(join.alias, False, dialect)}'
    if join.condition is None and (not join.using) and (join.join_type == JoinType.INNER):
        join_type = 'CROSS JOIN'
    result = f'{join_type} {table}'
    right = join.alias or (join.table.alias or join.table.name if isinstance(join.table, TableRef) else join.table.alias if isinstance(join.table, SubqueryExpression) else None)
    if join.condition:
        result += f' ON {_emit_condition(join.condition, dialect)}'
    elif join.using:
        if dialect == 'tsql' and left_name and right:
            merged = merged_cols if merged_cols is not None else {}
            on_parts = []
            for c in join.using:
                left_expr = merged.get(c.lower(), f'{left_name}.{c}')
                on_parts.append(f'{left_expr} = {right}.{c}')
                if join.join_type == JoinType.FULL:
                    merged[c.lower()] = f'COALESCE({left_expr}, {right}.{c})'
                elif join.join_type == JoinType.RIGHT:
                    merged[c.lower()] = f'{right}.{c}'
                else:
                    merged[c.lower()] = left_expr
            result += f" ON {' AND '.join(on_parts)}"
        else:
            result += f" USING ({', '.join(join.using)})"
    return result

def _emit_order_item(item: OrderByItem, dialect: str) -> str:
    """Emit an ORDER BY item.

    PostgreSQL/Oracle default to NULLS LAST ascending and NULLS FIRST
    descending; when the source's NULL ordering (carried in ``nulls_first``)
    differs, it must be spelled out or the row order silently changes.
    T-SQL/MySQL have no NULLS FIRST/LAST syntax, so it is omitted there
    (same as a raw sqlglot transpile).
    """
    expr = _emit_expression(item.expression, dialect)
    direction = 'DESC' if item.direction == OrderDirection.DESC else 'ASC'
    out = f'{expr} {direction}'
    if item.nulls_first is not None and dialect in ('postgresql', 'oracle'):
        target_default_first = item.direction == OrderDirection.DESC
        if item.nulls_first != target_default_first:
            out += ' NULLS FIRST' if item.nulls_first else ' NULLS LAST'
    return out

def _emit_limit(limit: LimitClause, dialect: str) -> str:
    """Emit LIMIT/OFFSET clause in dialect-appropriate syntax."""
    if dialect == 'oracle':
        parts = []
        if limit.offset:
            parts.append(f'OFFSET {_emit_expression(limit.offset, dialect)} ROWS')
        if limit.limit:
            pct = ' PERCENT' if limit.percent else ''
            parts.append(f'FETCH FIRST {_emit_expression(limit.limit, dialect)}{pct} ROWS ONLY')
        return '\n'.join(parts)
    if dialect == 'tsql':
        if limit.offset:
            parts = [f'OFFSET {_emit_expression(limit.offset, dialect)} ROWS']
            if limit.limit:
                parts.append(f'FETCH NEXT {_emit_expression(limit.limit, dialect)} ROWS ONLY')
            return '\n'.join(parts)
        if limit.limit:
            return ''
    parts = []
    if limit.limit:
        limit_sql = f'LIMIT {_emit_expression(limit.limit, dialect)}'
        if limit.percent:
            limit_sql += f' /* UNIQUE: source was TOP n PERCENT; {dialect} has no LIMIT PERCENT — emitted as a row count, adjust to CEIL(n/100 * total_rows) if a true percentage is required */'
        parts.append(limit_sql)
    if limit.offset:
        parts.append(f'OFFSET {_emit_expression(limit.offset, dialect)}')
    return '\n'.join(parts)