# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""PG-source wave 1 (baseline 2026-07-11): session GUC settings.

PostgreSQL's ``SET <guc> = <v>`` / ``SET <guc> TO <v>`` / ``RESET <guc>``
are engine-local session knobs with no meaning elsewhere — shipped raw they
were the largest single class of the pg→tsql baseline (111x near-'=' plus
29x near-'to') and error on every other engine. They degrade to the
documented carrier, like SQL*Plus directives do. Real SQL SET forms
(TRANSACTION, CONSTRAINTS, ROLE, SESSION AUTHORIZATION) keep their path.
"""

from __future__ import annotations

import re

import pytest

from unique.core.transpiler import Transpiler


def _t(sql: str, target: str) -> str:
    return Transpiler().transpile(sql, source="postgresql", target=target).sql


def _t2(sql: str, source: str, target: str) -> str:
    return Transpiler().transpile(sql, source=source, target=target).sql


class TestPgGucSettings:
    @pytest.mark.parametrize("target", ["tsql", "mysql", "oracle"])
    def test_guc_assignment_degrades(self, target: str) -> None:
        out = _t("SET extra_float_digits = 0;", target)
        assert "UNIQUE:" in out, out
        assert not re.search(r"(?im)^\s*SET\s+extra_float_digits", out), out

    @pytest.mark.parametrize("target", ["tsql", "mysql", "oracle"])
    def test_guc_to_spelling_degrades(self, target: str) -> None:
        out = _t("set enable_presorted_aggregate to off;", target)
        assert "UNIQUE:" in out, out
        assert not re.search(r"(?im)^\s*set\s+enable_", out), out

    @pytest.mark.parametrize("target", ["tsql", "mysql", "oracle"])
    def test_reset_degrades(self, target: str) -> None:
        out = _t("RESET enable_seqscan;", target)
        assert "UNIQUE:" in out, out
        assert not re.search(r"(?im)^\s*RESET\b", out), out

    def test_guc_kept_on_pg_target(self) -> None:
        out = _t("SET extra_float_digits = 0;", "postgresql")
        assert re.search(r"(?im)^\s*SET\s+extra_float_digits\s*=\s*0", out), out

    def test_set_transaction_keeps_its_path(self) -> None:
        out = _t("SET TRANSACTION ISOLATION LEVEL READ COMMITTED;", "tsql")
        assert "UNIQUE:" not in out or "TRANSACTION" in out.upper(), out
        assert re.search(r"(?i)TRANSACTION", out), out


class TestValuesRelation:
    """``FROM (VALUES (1,'x'),(2,'y')) v(a,b)`` converted to NOTHING — the
    FROM emitted empty (silent loss caught by the gate; the whole
    'Expected table name but got CROSS/ON/GROUP_BY' family of the
    baseline). Lowered to a UNION ALL chain of row-SELECTs, valid on all
    four engines."""

    _SRC = "select a, b from (values (1,'x'),(2,'y')) v(a,b);"

    @pytest.mark.parametrize("target", ["tsql", "mysql", "oracle", "postgresql"])
    def test_values_relation_survives(self, target: str) -> None:
        import sqlglot

        out = _t(self._SRC, target)
        assert re.search(r"(?i)FROM\s*\(SELECT\s+1\s+AS\s+a", out), out
        assert re.search(r"(?i)UNION ALL", out), out
        assert re.search(r"(?i)\)\s*v\b", out), out
        read = {
            "tsql": "tsql",
            "mysql": "mysql",
            "oracle": "oracle",
            "postgresql": "postgres",
        }[target]
        sqlglot.parse(out, read=read)

    def test_oracle_arms_get_from_dual(self) -> None:
        out = _t(self._SRC, "oracle")
        assert out.upper().count("FROM DUAL") == 2, out

    def test_values_with_string_agg(self) -> None:
        out = _t("select string_agg(a, ',') from (values ('aa'),('bb')) g(a);", "tsql")
        assert "UNIQUE:" not in out, out
        assert re.search(r"(?i)STRING_AGG", out), out


class TestWindowOrderByRequiredOnTsql:
    """T-SQL requires ORDER BY inside OVER for ranking/offset window
    functions (live 4112, 59x); PostgreSQL allows a partition-only or
    empty spec. The neutral ORDER BY (SELECT NULL) preserves the intent."""

    def test_first_value_gains_neutral_order(self) -> None:
        out = _t("select first_value(a) over (partition by b) from t;", "tsql")
        assert re.search(
            r"(?i)OVER\s*\(PARTITION BY b ORDER BY \(SELECT NULL\)\)", out
        ), out

    def test_existing_order_is_kept(self) -> None:
        out = _t("select first_value(a) over (order by c) from t;", "tsql")
        assert re.search(r"(?i)ORDER BY c", out), out
        assert "SELECT NULL" not in out.upper(), out

    def test_aggregate_over_needs_no_order(self) -> None:
        out = _t("select sum(a) over (partition by b) from t;", "tsql")
        assert "SELECT NULL" not in out.upper(), out


class TestJoinedDerivedTableAlias:
    """A joined derived table's alias was dropped on emit
    (``JOIN (SELECT 1 AS a) ON t.x = v.a`` — unreferencable, and MySQL
    requires the alias)."""

    @pytest.mark.parametrize("target", ["tsql", "mysql", "oracle", "postgresql"])
    def test_join_values_keeps_alias(self, target: str) -> None:
        out = _t("select * from t join (values (1)) v(a) on t.x = v.a;", target)
        assert re.search(r"(?i)\)\s*v\s+ON\b", out), out

    def test_join_select_keeps_alias(self) -> None:
        out = _t("select * from t join (select 1 as a) s on t.x = s.a;", "mysql")
        assert re.search(r"(?i)\)\s*s\s+ON\b", out), out


class TestGluedDollarQuoteClose:
    """``end$$ language plpgsql`` (no space — ubiquitous in real plpgsql)
    lexed as ONE identifier ``end$$`` because ``$`` continues identifiers
    (needed for Oracle V$SESSION): the parser never saw END, and the tail
    leaked into the body as an ``end$$ AS language;`` statement (34x in
    the pg-source baseline). For a postgresql SOURCE, ``$`` ends the
    identifier — matching PG's own lexing, where dollar-quotes win."""

    _SRC = (
        "create function f_g() returns void as $$\n"
        "begin\n"
        "  insert into foo values(1);\n"
        "end$$ language plpgsql;"
    )

    def test_no_language_fragment_on_mysql(self) -> None:
        out = _t(self._SRC, "mysql")
        assert "AS language" not in out, out
        assert "end$$" not in out, out
        assert re.search(r"(?i)INSERT INTO foo", out), out

    def test_tagged_close_unaffected_shape(self) -> None:
        src = self._SRC.replace("$$", "$body$")
        out = _t(src, "mysql")
        assert "AS language" not in out, out


class TestTypeOnlyParameters:
    """PG declares parameters with only a type — ``create function
    add2(int, int)`` — and plpgsql bodies reference them as ``$1``/``$2``.
    The signature parser took the first type word as the parameter NAME,
    desynced on the comma, and swallowed the whole function into the
    parameter list: garbage signatures (``$ $,``, ``plpgsql ;`` as
    parameters) with ZERO warnings. Type-only parameters get synthesized
    names (``p1``…) and ``$n`` references rewrite to them."""

    _SRC = (
        "create function add2(int, int) returns int as $$\n"
        "begin\n"
        "  return $1 + $2;\n"
        "end$$ language plpgsql;"
    )

    def test_two_synthesized_params_mysql(self) -> None:
        out = _t(self._SRC, "mysql")
        assert re.search(r"(?i)p1\s+int\s*,\s*p2\s+int", out), out
        assert re.search(r"(?i)RETURNS\s+int", out), out
        assert not re.search(r"\$\s*\d", out), out
        assert "$ $" not in out, out

    def test_body_references_rewritten_mysql(self) -> None:
        out = _t(self._SRC, "mysql")
        assert re.search(r"(?i)RETURN\s+p1\s*\+\s*p2", out), out

    def test_two_synthesized_params_oracle(self) -> None:
        out = _t(self._SRC, "oracle")
        assert re.search(r"(?i)p1\b", out) and re.search(r"(?i)p2\b", out), out
        assert not re.search(r"\$\s*\d", out), out
        assert re.search(r"(?i)RETURN\s+p1\s*\+\s*p2", out), out


class TestPositionalParamReference:
    """plpgsql allows ``$1`` references even when the parameter IS named;
    the lexer split ``$1`` into ``$`` + ``1`` and shipped ``RETURN $ 1``
    with no warning. ``$n`` maps to the n-th parameter's name."""

    def test_dollar_ref_maps_to_declared_name(self) -> None:
        src = (
            "create function np(a int) returns int as $$\n"
            "begin\n"
            "  return $1 + 1;\n"
            "end$$ language plpgsql;"
        )
        out = _t(src, "mysql")
        assert re.search(r"(?i)RETURN\s+a\s*\+\s*1", out), out
        assert not re.search(r"\$\s*\d", out), out


class TestSingleQuotedBody:
    """Old-style plpgsql bodies are single-quoted strings — ``as '
    begin … end; ' language plpgsql`` — and the batch splitter broke the
    unit at semicolons INSIDE the multi-line literal: the inner ``end;``
    shipped as ``COMMIT;`` and the closing ``' language plpgsql;`` went
    alone to sqlglot (tokenize-error carrier). The unit must stay whole
    and convert like its dollar-quoted equivalent."""

    _SRC = (
        "create function sq(int) returns int as '\n"
        "begin\n"
        "  return $1 + 1;\n"
        "end;\n"
        "' language plpgsql;"
    )

    def test_unit_stays_whole_mysql(self) -> None:
        out = _t(self._SRC, "mysql")
        assert "COMMIT" not in out.upper(), out
        assert "Error tokenizing" not in out, out
        assert "language plpgsql" not in out, out

    def test_quoted_body_converts_mysql(self) -> None:
        out = _t(self._SRC, "mysql")
        assert re.search(r"(?i)RETURN\s+p1\s*\+\s*1", out), out
        assert not re.search(r"\$\s*\d", out), out


class TestPgArgmodeFirstParameters:
    """PG puts the argmode BEFORE the name — ``(out x int)`` — the
    reverse of Oracle's ``(x out int)``; the shared name-first parse
    desynced and swallowed the function. Same for a type-only
    parameter carrying DEFAULT (``int default 0``)."""

    _OUT_SRC = (
        "create function f1(out x int) returns int as $$\n"
        "begin\n  x := 1;\nend$$ language plpgsql;"
    )

    def test_out_mode_first_no_desync(self) -> None:
        # MySQL functions cannot declare OUT parameters; the emitter drops
        # the mode (pre-existing behavior for every source). This asserts
        # the wave-5 class only: the signature parses, nothing desyncs.
        out = _t(self._OUT_SRC, "mysql")
        assert re.search(r"(?i)x\s+int", out), out
        assert "plpgsql" not in out, out
        assert "$ $" not in out, out
        assert re.search(r"(?i)SET\s+x\s*=\s*1", out), out

    def test_out_mode_first_kept_on_oracle(self) -> None:
        out = _t(self._OUT_SRC, "oracle")
        assert re.search(r"(?i)x\s+OUT\s+", out), out
        assert "plpgsql" not in out, out

    def test_inout_mode_first(self) -> None:
        src = (
            "create function f2(inout x int) returns int as $$\n"
            "begin\n  x := x + 1;\nend$$ language plpgsql;"
        )
        out = _t(src, "mysql")
        assert re.search(r"(?i)x\s+int", out), out
        assert re.search(r"(?i)SET\s+x\s*=\s*x\s*\+\s*1", out), out
        assert "plpgsql" not in out, out

    def test_type_only_with_default(self) -> None:
        src = (
            "create function f4(int default 0) returns int as $$\n"
            "begin\n  return $1;\nend$$ language plpgsql;"
        )
        out = _t(src, "mysql")
        assert re.search(r"(?i)p1\s+int", out), out
        assert re.search(r"(?i)RETURN\s+p1", out), out
        assert "plpgsql" not in out, out


class TestStatisticalAggregates:
    """sqlglot canonicalizes ``var_pop``→VARIANCE_POP and keeps VARIANCE/
    STDDEV; no engine accepts VARIANCE_POP, T-SQL spells the family
    VARP/VAR/STDEVP/STDEV (unknown names get ``dbo.``-qualified → error
    195/207), and MySQL's own VARIANCE/STDDEV are POPULATION variants
    while PG's are SAMPLE — passing the name through silently changes
    the math."""

    def test_variance_family_tsql(self) -> None:
        out = _t("select var_pop(x), variance(x) from t;", "tsql")
        assert re.search(r"\bVARP\(", out), out
        assert re.search(r"\bVAR\(", out), out
        assert "dbo." not in out and "VARIANCE" not in out.upper(), out

    def test_stddev_family_tsql(self) -> None:
        out = _t("select stddev_pop(x), stddev_samp(x), stddev(x) from t;", "tsql")
        assert re.search(r"\bSTDEVP\(", out), out
        assert re.search(r"\bSTDEV\(", out), out
        assert "dbo." not in out and "STDDEV" not in out.upper(), out

    def test_sample_semantics_mysql(self) -> None:
        out = _t("select variance(x), stddev(x) from t;", "mysql")
        assert re.search(r"(?i)\bVAR_SAMP\(", out), out
        assert re.search(r"(?i)\bSTDDEV_SAMP\(", out), out
        assert not re.search(r"(?i)\bVARIANCE\(", out), out
        assert not re.search(r"(?i)\bSTDDEV\(", out), out

    def test_variance_family_oracle(self) -> None:
        out = _t("select var_pop(x), variance(x) from t;", "oracle")
        assert re.search(r"(?i)\bVAR_POP\(", out), out
        assert re.search(r"(?i)\bVAR_SAMP\(", out), out
        assert "VARIANCE_POP" not in out.upper(), out


class TestBooleanAggregates:
    """PG ``bool_or``/``bool_and``/``every`` canonicalize to LOGICAL_OR/
    LOGICAL_AND (or stay verbatim) — no other engine has them. MySQL:
    MAX/MIN over the 0/1 boolean. T-SQL: MAX/MIN over CAST(b AS INT)
    (bit is not a valid MAX operand)."""

    def test_bool_aggs_mysql(self) -> None:
        out = _t("select bool_or(b), bool_and(b), every(b) from t;", "mysql")
        assert re.search(r"(?i)MAX\(b\)", out), out
        assert re.search(r"(?i)MIN\(b\)", out), out
        assert "LOGICAL" not in out.upper() and "BOOL_OR" not in out.upper(), out

    def test_bool_aggs_tsql(self) -> None:
        out = _t("select bool_or(b), bool_and(b) from t;", "tsql")
        assert re.search(r"(?i)MAX\(CAST\(b AS INT\)\)", out), out
        assert re.search(r"(?i)MIN\(CAST\(b AS INT\)\)", out), out
        assert "dbo." not in out and "LOGICAL" not in out.upper(), out


class TestFloat8Cast:
    """``1.0::float8`` / ``float8 'nan'`` parse to CAST(… AS DOUBLE);
    T-SQL has no DOUBLE (error near ')') and Oracle needs BINARY_DOUBLE
    (ORA-00902). 55x in the pg→tsql residue."""

    def test_double_cast_tsql(self) -> None:
        out = _t("select 1.0::float8;", "tsql")
        assert re.search(r"(?i)CAST\(1\.0 AS FLOAT\)", out), out
        assert "DOUBLE" not in out.upper(), out

    def test_double_cast_oracle(self) -> None:
        out = _t("select 1.0::float8;", "oracle")
        assert re.search(r"(?i)AS BINARY_DOUBLE\)", out), out

    def test_prefixed_literal_tsql(self) -> None:
        out = _t("select float8 '1.5';", "tsql")
        assert re.search(r"(?i)CAST\('1\.5' AS FLOAT\)", out), out


class TestStatAggregateRoundTrip:
    """Spelling differs per engine — round-trip so a no-op cannot pass."""

    def test_var_pop_pg_tsql_pg(self) -> None:
        mid = _t("select var_pop(x) from t;", "tsql")
        assert re.search(r"(?i)\bVARP\(", mid), mid
        back = Transpiler().transpile(mid, source="tsql", target="postgresql").sql
        assert re.search(r"(?i)\bVAR_POP\(", back), back

    def test_mysql_population_survives_to_pg_and_back(self) -> None:
        mid = (
            Transpiler()
            .transpile("SELECT STDDEV(x) FROM t;", source="mysql", target="postgresql")
            .sql
        )
        assert re.search(r"(?i)\bSTDDEV_POP\(", mid), mid
        back = Transpiler().transpile(mid, source="postgresql", target="mysql").sql
        assert re.search(r"(?i)\bSTDDEV_POP\(", back), back


class TestPgTableInheritance:
    """``CREATE TABLE kid (…) INHERITS (parent)`` and ``CREATE TABLE c
    PARTITION OF p FOR VALUES …`` lost their defining clause SILENTLY
    (the partition child shipped as a bare column-less ``CREATE TABLE
    c`` — 30x ``CREATE TABLE #…`` in the tsql residue, 0 warnings).
    No mechanical equivalent off PostgreSQL: the whole statement must
    degrade to a carrier with a warning; the PG target keeps it."""

    _INH = "create table kid (extra int) inherits (parent);"
    _PART = "create temp table c1 partition of p for values in (1);"

    @pytest.mark.parametrize("target", ["tsql", "mysql", "oracle"])
    def test_inherits_degrades_whole(self, target: str) -> None:
        r = Transpiler().transpile(self._INH, source="postgresql", target=target)
        assert "UNIQUE:" in r.sql, r.sql
        assert "INHERITS" in r.sql.upper(), r.sql
        code = [
            ln
            for ln in r.sql.splitlines()
            if ln.strip() and not ln.strip().startswith("--")
        ]
        assert not code, r.sql
        assert r.warnings or r.unsupported, r.sql

    @pytest.mark.parametrize("target", ["tsql", "mysql", "oracle"])
    def test_partition_of_degrades_whole(self, target: str) -> None:
        r = Transpiler().transpile(self._PART, source="postgresql", target=target)
        assert "UNIQUE:" in r.sql, r.sql
        assert "PARTITION OF" in r.sql.upper(), r.sql
        code = [
            ln
            for ln in r.sql.splitlines()
            if ln.strip() and not ln.strip().startswith("--")
        ]
        assert not code, r.sql
        assert r.warnings or r.unsupported, r.sql

    def test_inherits_kept_on_pg(self) -> None:
        out = _t(self._INH, "postgresql")
        assert re.search(r"(?i)INHERITS\s*\(parent\)", out), out
        assert "UNIQUE:" not in out, out

    def test_partition_of_kept_on_pg(self) -> None:
        out = _t(self._PART, "postgresql")
        assert re.search(r"(?i)PARTITION OF p FOR VALUES IN \(1\)", out), out
        assert "UNIQUE:" not in out, out


class TestDeferrableConstraintAttribute:
    """PG constraint attributes (DEFERRABLE / INITIALLY DEFERRED) have no
    T-SQL/MySQL spelling and shipped verbatim (syntax error near ')').
    Oracle supports them and keeps them."""

    _SRC = "create table t3 (a int, b int, primary key (a, b) deferrable);"

    @pytest.mark.parametrize("target", ["tsql", "mysql"])
    def test_deferrable_stripped_with_warning(self, target: str) -> None:
        r = Transpiler().transpile(self._SRC, source="postgresql", target=target)
        assert "DEFERRABLE" not in r.sql.upper(), r.sql
        assert re.search(r"(?i)PRIMARY KEY\s*\(a,?\s*b\)", r.sql), r.sql
        assert any(
            "DEFERRABLE" in str(w.message).upper() for w in r.warnings
        ), r.warnings

    def test_deferrable_kept_on_oracle(self) -> None:
        out = _t(self._SRC, "oracle")
        assert "DEFERRABLE" in out.upper(), out


class TestPgRoutineHeaderAttributes:
    """PG routine-header attributes (STRICT, PARALLEL SAFE, COST n,
    ROWS n, LEAKPROOF, CALLED/RETURNS NULL ON NULL INPUT) were not
    consumed by the header parser and spilled into the routine body as
    garbage declarations (``STRICT LANGUAGE; plpgsql AS; $ $;`` inside
    the Oracle IS-section — 24x+ PLS-00103, and the whole stricttest
    class on MySQL/T-SQL)."""

    _BEFORE = (
        "create function sf(a int) returns int\n"
        "strict parallel safe cost 100 language plpgsql as $$\n"
        "begin\n  return a;\nend$$;"
    )
    _AFTER = (
        "create function sg(a int) returns int as $$\n"
        "begin\n  return a;\nend$$ language plpgsql strict parallel safe;"
    )
    _NULLCALL = (
        "create function sh(a int) returns int\n"
        "returns null on null input leakproof language plpgsql as $$\n"
        "begin\n  return a;\nend$$;"
    )

    @pytest.mark.parametrize("target", ["mysql", "oracle", "tsql"])
    def test_attributes_before_body(self, target: str) -> None:
        out = _t(self._BEFORE, target)
        assert "STRICT" not in out.upper(), out
        assert "PARALLEL" not in out.upper(), out
        assert "plpgsql" not in out, out
        assert "$ $" not in out, out
        # T-SQL parameters gain their @ prefix
        assert re.search(r"(?i)RETURN\s+@?a\b", out), out

    @pytest.mark.parametrize("target", ["mysql", "oracle"])
    def test_attributes_after_body(self, target: str) -> None:
        out = _t(self._AFTER, target)
        assert "STRICT" not in out.upper(), out
        assert "PARALLEL" not in out.upper(), out
        assert re.search(r"(?i)RETURN\s+a\b", out), out

    def test_null_input_and_leakproof(self) -> None:
        out = _t(self._NULLCALL, "mysql")
        assert "LEAKPROOF" not in out.upper(), out
        assert "NULL INPUT" not in out.upper(), out
        assert re.search(r"(?i)RETURN\s+a\b", out), out


class TestJoinUsingOnTsql:
    """T-SQL has no ``JOIN … USING (c)``. The single-join TableRef case
    already rewrote to ON; chained joins and derived-table left sides
    fell back to emitting USING (errors 102/321 — 27x+ in the tsql
    residue). After a FULL join, a later USING references the MERGED
    column, so its ON needs COALESCE over the prior arms."""

    def test_derived_table_left_side(self) -> None:
        out = _t(
            "select * from (select * from t2) s2 "
            "inner join (select * from t3) s3 using (name);",
            "tsql",
        )
        assert "USING" not in out.upper(), out
        assert re.search(r"(?i)ON\s+s2\.name\s*=\s*s3\.name", out), out

    def test_chained_joins(self) -> None:
        out = _t(
            "select * from t1 inner join t2 using (a) inner join t3 using (a);",
            "tsql",
        )
        assert "USING" not in out.upper(), out
        assert re.search(r"(?i)ON\s+t1\.a\s*=\s*t2\.a", out), out
        assert re.search(r"(?i)ON\s+\S*t\d?\.?a?.*=\s*t3\.a", out), out

    def test_full_join_chain_coalesces(self) -> None:
        out = _t(
            "select * from t1 full outer join t2 using (name) "
            "full outer join t3 using (name);",
            "tsql",
        )
        assert "USING" not in out.upper(), out
        assert re.search(
            r"(?i)ON\s+COALESCE\(t1\.name,\s*t2\.name\)\s*=\s*t3\.name", out
        ), out

    def test_using_kept_on_pg(self) -> None:
        out = _t("select * from t1 inner join t2 using (a);", "postgresql")
        assert re.search(r"(?i)USING\s*\(a\)", out), out


class TestPlpgsqlRaiseFormat:
    """plpgsql ``RAISE level 'fmt %', args [USING opt = v]``: the raw
    argument tuple was pasted into single-argument carriers on every
    target (``PRINT 'x', @a`` — error 102; ``PUT_LINE('x', a)`` —
    PLS-00306; a bare ``SELECT 'x', a`` inside a MySQL function), and
    the USING warning mislabeled plpgsql options as RAISERROR args.
    The ``%`` placeholders interleave into a source-dialect ``||``
    concatenation the existing operator machinery then maps per
    target."""

    _SRC = (
        "create function rf(a int) returns int as $$\n"
        "begin\n"
        "  raise notice 'value is %', a;\n"
        "  if a = 0 then\n"
        "    raise exception 'bad % here', a;\n"
        "  end if;\n"
        "  return a;\n"
        "end$$ language plpgsql;"
    )

    def test_notice_interleaves_mysql(self) -> None:
        out = _t(self._SRC, "mysql")
        assert re.search(r"(?i)CONCAT\('value is ',\s*a\)", out), out
        assert not re.search(r"(?i)'value is %'\s*,", out), out

    def test_notice_single_argument_oracle(self) -> None:
        out = _t(self._SRC, "oracle")
        assert re.search(r"(?i)PUT_LINE\('value is '\s*\|\|\s*a\)", out), out

    def test_exception_message_formatted_oracle(self) -> None:
        out = _t(self._SRC, "oracle")
        pat = (
            r"(?i)RAISE_APPLICATION_ERROR\(-20001,"
            r"\s*'bad '\s*\|\|\s*a\s*\|\|\s*' here'\)"
        )
        assert re.search(pat, out), out

    def test_exception_message_formatted_mysql(self) -> None:
        # SIGNAL's MESSAGE_TEXT only accepts a literal or a variable, so
        # the formatted message is hoisted through a user variable.
        out = _t(self._SRC, "mysql")
        assert re.search(
            r"(?i)SET @uq_errmsg = CONCAT\('bad ',\s*a,\s*' here'\)", out
        ), out
        assert re.search(r"(?i)MESSAGE_TEXT\s*=\s*@uq_errmsg", out), out

    def test_double_percent_is_literal(self) -> None:
        out = _t(
            "create function rg() returns void as $$\n"
            "begin\n  raise notice '100%% done';\nend$$ language plpgsql;",
            "oracle",
        )
        assert "100% done" in out, out

    def test_using_options_folded_with_truthful_warning(self) -> None:
        r = Transpiler().transpile(
            "create function rh(a int) returns int as $$\n"
            "begin\n"
            "  raise exception 'bad %', a using hint = 'give nonzero';\n"
            "  return a;\n"
            "end$$ language plpgsql;",
            source="postgresql",
            target="mysql",
        )
        assert "give nonzero" in r.sql, r.sql
        joined = " ".join(w.message for w in r.warnings)
        assert "USING" in joined and "RAISERROR" not in joined, r.warnings


class TestMysqlFunctionNotice:
    """A bare ``SELECT <msg>`` is invalid inside a MySQL FUNCTION
    (functions cannot return result sets — error 1415), which kept the
    whole RAISE NOTICE function class red after wave 10. The message
    diverts to ``@uq_notice`` with a documented carrier; procedures
    keep the visible SELECT channel."""

    def test_notice_in_function_diverts(self) -> None:
        r = Transpiler().transpile(
            "create function nf(a int) returns int as $$\n"
            "begin\n  raise notice 'v %', a;\n  return a;\nend$$ "
            "language plpgsql;",
            source="postgresql",
            target="mysql",
        )
        assert re.search(r"(?i)SET @uq_notice = CONCAT\('v ',\s*a\)", r.sql), r.sql
        assert not re.search(r"(?im)^\s*SELECT CONCAT", r.sql), r.sql
        assert "UNIQUE:" in r.sql, r.sql

    def test_notice_in_procedure_keeps_select(self) -> None:
        out = _t(
            "create procedure np() language plpgsql as $$\n"
            "begin\n  raise notice 'hello';\nend$$;",
            "mysql",
        )
        assert re.search(r"(?i)SELECT 'hello'", out), out
        assert "@uq_notice" not in out, out


class TestReturnsVoid:
    """``RETURNS void`` (62x in the corpus — the most common plpgsql
    test-function type) emitted verbatim on every target, where it is
    invalid: MySQL/T-SQL/Oracle functions must declare AND return a
    real value. Map to the target's neutral scalar and guarantee a
    trailing RETURN."""

    _SRC = (
        "create function vf(a int) returns void as $$\n"
        "begin\n  insert into t values(a);\nend$$ language plpgsql;"
    )

    def test_void_mysql(self) -> None:
        out = _t(self._SRC, "mysql")
        assert "void" not in out.lower(), out
        assert re.search(r"(?i)RETURNS\s+INT", out), out
        assert re.search(r"(?i)RETURN 0;\s*\nEND", out), out

    def test_void_tsql(self) -> None:
        out = _t(self._SRC, "tsql")
        assert "void" not in out.lower(), out
        assert re.search(r"(?i)RETURNS\s+INT", out), out
        assert re.search(r"(?i)RETURN 0", out), out

    def test_void_oracle(self) -> None:
        out = _t(self._SRC, "oracle")
        assert "void" not in out.lower(), out
        assert re.search(r"(?i)RETURN\s+NUMBER", out), out
        assert re.search(r"(?i)RETURN NULL;", out), out

    def test_existing_trailing_return_not_duplicated(self) -> None:
        src = (
            "create function vg() returns void as $$\n"
            "begin\n  return;\nend$$ language plpgsql;"
        )
        out = _t(src, "mysql")
        assert out.upper().count("RETURN 0") == 1, out


class TestRecordDeclarationDegrades:
    """``DECLARE x record`` has no mechanical equivalent off PostgreSQL
    (row shape unknown until runtime); the unit must degrade WHOLE with
    a warning, never ship ``DECLARE x record;`` (1064/PLS-00201)."""

    _SRC = (
        "create function rr() returns int as $$\n"
        "declare x record;\n"
        "begin\n  select 1 as f1 into x;\n  return x.f1;\nend$$ "
        "language plpgsql;"
    )

    @pytest.mark.parametrize("target", ["mysql", "tsql"])
    def test_record_degrades_whole(self, target: str) -> None:
        r = Transpiler().transpile(self._SRC, source="postgresql", target=target)
        code = [
            ln
            for ln in r.sql.splitlines()
            if ln.strip() and not ln.strip().startswith("--")
        ]
        assert not code, r.sql
        assert "record" in r.sql.lower(), r.sql
        assert r.warnings or r.unsupported, r.sql


class TestLanguageSqlBody:
    """A ``LANGUAGE sql`` function body is a bare statement list (no
    BEGIN/DECLARE); the declare-section parser consumed it as garbage
    declarations (``DECLARE select LONGTEXT; DECLARE $ $;``). The body
    parses as statements and, for a non-void function, the trailing
    SELECT becomes the RETURN."""

    def test_scalar_select_body_mysql(self) -> None:
        out = _t(
            "create function fs(a int) returns int as " "'select $1 + 1' language sql;",
            "mysql",
        )
        assert "DECLARE select" not in out, out
        assert re.search(r"(?i)RETURN\s*\(?\s*SELECT\s+a\s*\+\s*1", out), out

    def test_void_dml_body_mysql(self) -> None:
        out = _t(
            "create function fv() returns void as "
            "'insert into t values (1)' language sql;",
            "mysql",
        )
        assert re.search(r"(?i)INSERT INTO t VALUES \(1\)", out), out
        assert re.search(r"(?i)RETURN 0", out), out
        assert "DECLARE insert" not in out, out


class TestPolymorphicPseudoTypes:
    """``anyelement``/``anyarray`` parameters or returns are
    un-instantiable outside PostgreSQL; the routine degrades WHOLE
    with a warning (previously shipped as an invalid type name)."""

    _SRC = (
        "create function pf(x anyelement) returns anyelement as $$\n"
        "begin\n  return x;\nend$$ language plpgsql;"
    )

    @pytest.mark.parametrize("target", ["mysql", "tsql", "oracle"])
    def test_polymorphic_degrades_whole(self, target: str) -> None:
        r = Transpiler().transpile(self._SRC, source="postgresql", target=target)
        code = [
            ln
            for ln in r.sql.splitlines()
            if ln.strip() and not ln.strip().startswith("--")
        ]
        assert not code, r.sql
        assert "anyelement" in r.sql.lower(), r.sql
        assert r.warnings or r.unsupported, r.sql


class TestPlpgsqlEqualsAssignment:
    """plpgsql accepts ``v = expr;`` as assignment (synonym of ``:=``);
    the statement parser only recognized ``:=``, so bare-``=``
    assignments shipped raw (PLS-00103 on Oracle, 8x+ direct plus
    chain blockers everywhere)."""

    _SRC = (
        "create function ea(a int) returns text as $$\n"
        "declare r text;\n"
        "begin\n"
        "  r = 'v' || a;\n"
        "  return r;\n"
        "end$$ language plpgsql;"
    )

    def test_equals_assignment_oracle(self) -> None:
        out = _t(self._SRC, "oracle")
        assert re.search(r"(?i)r\s*:=\s*'v'\s*\|\|\s*a", out), out

    def test_equals_assignment_mysql(self) -> None:
        out = _t(self._SRC, "mysql")
        assert re.search(r"(?i)SET r\s*=\s*CONCAT\('v',\s*a\)", out), out


class TestSetofReturnsDegrade:
    """``RETURNS setof tbl`` desynced the signature parse (two-word
    type: ``setof`` consumed, the table name leaked into the body).
    Set-returning functions (RETURN NEXT protocol) have no mechanical
    equivalent off PostgreSQL: parse the type as a unit and degrade the
    routine WHOLE."""

    _SRC = (
        "create function sr() returns setof t1 as $$\n"
        "declare rec record;\n"
        "begin\n"
        "  for rec in select * from t1 loop\n"
        "    return next rec;\n"
        "  end loop;\n"
        "  return;\n"
        "end$$ language plpgsql;"
    )

    @pytest.mark.parametrize("target", ["oracle", "mysql"])
    def test_setof_degrades_whole(self, target: str) -> None:
        r = Transpiler().transpile(self._SRC, source="postgresql", target=target)
        code = [
            ln
            for ln in r.sql.splitlines()
            if ln.strip() and not ln.strip().startswith("--")
        ]
        assert not code, r.sql
        assert "setof" in r.sql.lower(), r.sql
        assert r.warnings or r.unsupported, r.sql


class TestPgIndexToTsql:
    """PG CREATE INDEX → T-SQL had two stacked failures: PG's nameless
    form (T-SQL requires a name) and sqlglot's write-side NULLs-distinct
    emulation wrapping unique-index columns in CASE WHEN expressions —
    invalid in a T-SQL index column list. The statement is rebuilt from
    the parsed tree; a filtered index's ``NOT x IS NULL`` renders as
    ``x IS NOT NULL`` (the only spelling T-SQL accepts there)."""

    def test_nameless_index_gets_a_name(self) -> None:
        out = _t("create unique index on fkest(x, x10);", "tsql")
        assert re.search(r"(?i)CREATE UNIQUE INDEX \w+ ON fkest", out), out
        assert "CASE WHEN" not in out.upper(), out

    def test_filtered_index_predicate_spelling(self) -> None:
        out = _t(
            "create unique index j1_id2_idx on j1(id2) where not id2 is null;",
            "tsql",
        )
        assert re.search(r"(?i)WHERE id2 IS NOT NULL", out), out
        assert "NOT id2 IS NULL" not in out.upper(), out
        assert "CASE WHEN" not in out.upper(), out

    def test_named_plain_index_unchanged_shape(self) -> None:
        out = _t("create index i2 on t2(a desc, b);", "tsql")
        assert re.search(r"(?i)CREATE INDEX i2 ON t2 \(a DESC, b\)", out), out


class TestBooleanLiteralConditionsTsql:
    """PG allows a bare boolean literal as a join/where condition
    (``JOIN b ON true``); the TRUE→1 mapping produced ``ON 1``, which
    T-SQL rejects (error 4145: non-boolean type where a condition is
    expected — 12x). A boolean literal in condition position emits as
    a real predicate."""

    def test_on_true_tsql(self) -> None:
        out = _t("select * from a full outer join b on true;", "tsql")
        assert re.search(r"(?i)ON 1 = 1", out), out

    def test_on_false_tsql(self) -> None:
        out = _t("select * from a full outer join b on false;", "tsql")
        assert re.search(r"(?i)ON 1 = 0", out), out

    def test_where_true_tsql(self) -> None:
        out = _t("select * from t where true;", "tsql")
        assert re.search(r"(?i)WHERE 1 = 1", out), out

    def test_real_condition_untouched(self) -> None:
        out = _t("select * from a join b on a.x = b.x;", "tsql")
        assert re.search(r"(?i)ON a\.x = b\.x", out), out
        assert "1 = 1" not in out, out


class TestArrayConstructsDegrade:
    """PG array constructs (``ARRAY[…]``, ``array_agg``, ``unnest``)
    shipped as fake function calls on T-SQL/MySQL (``dbo.ARRAY(1,2)``,
    unqualified ``ARRAY_AGG(x)`` — guaranteed engine errors) with ZERO
    warnings. Neither engine has arrays: the statement degrades WHOLE
    with a warning and an unsupported entry."""

    @pytest.mark.parametrize("target", ["tsql", "mysql"])
    @pytest.mark.parametrize(
        "sql",
        [
            "select array[1,2,3];",
            "select array_agg(x) from t;",
            "select unnest(array[1,2]);",
        ],
    )
    def test_array_construct_degrades(self, sql: str, target: str) -> None:
        r = Transpiler().transpile(sql, source="postgresql", target=target)
        code = [
            ln
            for ln in r.sql.splitlines()
            if ln.strip() and not ln.strip().startswith("--")
        ]
        assert not code, r.sql
        assert r.warnings or r.unsupported, r.sql

    def test_array_agg_kept_on_pg(self) -> None:
        out = _t("select array_agg(x) from t;", "postgresql")
        assert re.search(r"(?i)ARRAY_AGG\(x\)", out), out
        assert "UNIQUE:" not in out, out


class TestNestedDollarQuotedLiterals:
    """A dollar-quoted string INSIDE a plpgsql body (``EXECUTE
    $q$…$q$``) is a literal, but the lexer shredded it into ``$ q $``
    token soup (third dollar-quote patch — class fix: the PG lexer
    tokenizes ``$tag$…$tag$`` as ONE STRING, normalized to
    single-quote form like Oracle's q'…' handler, which also unifies
    outer bodies with the wave-5 splice path)."""

    def test_execute_dollar_string(self) -> None:
        src = (
            "create function dyn() returns int as $$\n"
            "declare n int;\n"
            "begin\n"
            "  execute $q$ select count(*) from t $q$ into n;\n"
            "  return n;\n"
            "end$$ language plpgsql;"
        )
        out = _t(src, "oracle")
        assert "$ q $" not in out, out
        assert "$q$" not in out, out
        assert re.search(r"(?i)'\s*select count\(\*\) from t\s*'", out), out

    def test_outer_body_still_parses(self) -> None:
        out = _t(
            "create function ob(a int) returns int as $$\n"
            "begin\n  return a + 1;\nend$$ language plpgsql;",
            "mysql",
        )
        assert re.search(r"(?i)RETURN a \+ 1", out), out
        assert "$" not in out.replace("DELIMITER $$", "").replace("END$$", ""), out

    def test_nested_quotes_escape(self) -> None:
        src = (
            "create function nq() returns text as $$\n"
            "begin\n"
            "  return $x$it's here$x$;\n"
            "end$$ language plpgsql;"
        )
        out = _t(src, "postgresql")
        assert re.search(r"it''s here", out), out


class TestPgCatalogInternalsDegrade:
    """PG catalog casts (``regclass``/``regtype``/…) and system columns
    (``tableoid``, ``ctid``, ``xmin``…) are engine internals with no
    equivalent anywhere (22x ORA-00936 as ``CAST(tableoid AS
    REGCLASS)``); the statement degrades WHOLE on every non-PG
    target."""

    @pytest.mark.parametrize("target", ["oracle", "tsql", "mysql"])
    def test_regclass_cast_degrades(self, target: str) -> None:
        r = Transpiler().transpile(
            "select cast(tableoid as regclass), id from t;",
            source="postgresql",
            target=target,
        )
        code = [
            ln
            for ln in r.sql.splitlines()
            if ln.strip() and not ln.strip().startswith("--")
        ]
        assert not code, r.sql
        assert r.warnings or r.unsupported, r.sql

    def test_ctid_degrades(self) -> None:
        r = Transpiler().transpile(
            "select ctid from t;", source="postgresql", target="oracle"
        )
        code = [
            ln
            for ln in r.sql.splitlines()
            if ln.strip() and not ln.strip().startswith("--")
        ]
        assert not code, r.sql

    def test_plain_cast_kept(self) -> None:
        out = _t("select cast(id as text) from t;", "oracle")
        assert "UNIQUE:" not in out, out
        assert re.search(r"(?i)CAST\(id AS", out), out


class TestOrderedSetAggregatesDegrade:
    """Hypothetical/ordered-set aggregates (``RANK(x) WITHIN GROUP
    (ORDER BY …)``) reach the IR as an unhandled-WithinGroup RawSQL and
    shipped verbatim (9x 1064 on MySQL, error 195/156 on T-SQL, zero
    warnings). Neither engine has them: degrade WHOLE. Also:
    ``CAST(x AS ARRAY)`` joins the wave-17 array gate (the
    aggregate-transition-function class, 8x)."""

    @pytest.mark.parametrize("target", ["mysql", "tsql"])
    def test_within_group_degrades(self, target: str) -> None:
        r = Transpiler().transpile(
            "select rank(3) within group (order by x nulls last) from g;",
            source="postgresql",
            target=target,
        )
        code = [
            ln
            for ln in r.sql.splitlines()
            if ln.strip() and not ln.strip().startswith("--")
        ]
        assert not code, r.sql
        assert r.warnings or r.unsupported, r.sql

    def test_within_group_kept_on_oracle(self) -> None:
        out = _t(
            "select rank(3) within group (order by x nulls last) from g;",
            "oracle",
        )
        assert re.search(r"(?i)WITHIN GROUP", out), out
        assert "UNIQUE:" not in out, out

    @pytest.mark.parametrize("target", ["mysql", "tsql"])
    def test_array_cast_degrades(self, target: str) -> None:
        r = Transpiler().transpile(
            "select f(cast('{4,140}' as array), 100);",
            source="postgresql",
            target=target,
        )
        code = [
            ln
            for ln in r.sql.splitlines()
            if ln.strip() and not ln.strip().startswith("--")
        ]
        assert not code, r.sql
        assert r.warnings or r.unsupported, r.sql


class TestMysqlFullOuterJoinDegrades:
    """MySQL has no FULL OUTER JOIN in any spelling; the statement
    shipped raw (1064, the bulk of the remaining SELECT * class). It
    degrades WHOLE with a warning naming the manual rewrite (LEFT JOIN
    UNION ALL right anti-join)."""

    def test_full_join_degrades_mysql(self) -> None:
        r = Transpiler().transpile(
            "select * from a full outer join b using (i);",
            source="postgresql",
            target="mysql",
        )
        code = [
            ln
            for ln in r.sql.splitlines()
            if ln.strip() and not ln.strip().startswith("--")
        ]
        assert not code, r.sql
        assert any("FULL" in str(w.message).upper() for w in r.warnings), r.warnings

    def test_full_join_kept_on_tsql(self) -> None:
        out = _t("select * from a full outer join b on a.i = b.i;", "tsql")
        assert re.search(r"(?i)FULL OUTER JOIN", out), out
        assert "UNIQUE:" not in out, out

    def test_left_join_untouched_mysql(self) -> None:
        out = _t("select * from a left join b on a.i = b.i;", "mysql")
        assert re.search(r"(?i)LEFT JOIN", out), out
        assert "UNIQUE:" not in out, out


class TestUserAggregateCallsDegrade:
    """PG custom-aggregate CALLS — ``fn(*)`` and ``fn(DISTINCT … ORDER
    BY …)`` — have no T-SQL/MySQL spelling (UDFs cannot be aggregates
    there); they shipped raw (errors 102/156, the remaining ``SELECT
    dbo.…`` class). A non-COUNT star argument or an unhandled inner
    ORDER BY degrades the statement WHOLE."""

    @pytest.mark.parametrize("target", ["tsql", "mysql"])
    def test_star_call_degrades(self, target: str) -> None:
        r = Transpiler().transpile(
            "select newcnt(*) as c from t;", source="postgresql", target=target
        )
        code = [
            ln
            for ln in r.sql.splitlines()
            if ln.strip() and not ln.strip().startswith("--")
        ]
        assert not code, r.sql
        assert r.warnings or r.unsupported, r.sql

    @pytest.mark.parametrize("target", ["tsql", "mysql"])
    def test_inner_order_call_degrades(self, target: str) -> None:
        r = Transpiler().transpile(
            "select aggfns(distinct a, b, c order by b nulls last) from t;",
            source="postgresql",
            target=target,
        )
        code = [
            ln
            for ln in r.sql.splitlines()
            if ln.strip() and not ln.strip().startswith("--")
        ]
        assert not code, r.sql

    def test_count_star_untouched(self) -> None:
        out = _t("select count(*) from t;", "tsql")
        assert re.search(r"(?i)COUNT\(\*\)", out), out
        assert "UNIQUE:" not in out, out


class TestOracleUnderscoreIdentifiers:
    """Oracle rejects identifiers starting with ``_`` unless quoted
    (ORA-00911) — PG's suite aliases VALUES relations as ``_(x)`` (15x)
    and declares ``_sqlstate``-style locals. Leading-underscore
    identifiers emit quoted on the Oracle target."""

    def test_underscore_alias_quoted(self) -> None:
        out = _t("select x from (values ('a'), ('b')) _(x);", "oracle")
        assert '"_"' in out, out
        assert not re.search(r'(?<!")\b_\s*$', out), out

    def test_normal_alias_unquoted(self) -> None:
        out = _t("select x from (values ('a')) v(x);", "oracle")
        assert '"v"' not in out, out


class TestPlpgsqlDeclareEqualsDefault:
    """plpgsql accepts ``DECLARE v type = expr`` (bare ``=``, synonym of
    ``:=``) — wave 14 covered statements but not declarations; the
    default shipped unconsumed (`PLS-00103: =`)."""

    def test_declare_equals_default(self) -> None:
        src = (
            "create function de() returns int as $$\n"
            "declare n int = 5;\n"
            "begin\n  return n;\nend$$ language plpgsql;"
        )
        out = _t(src, "oracle")
        assert re.search(r"(?i)n\s+(int|number)\w*\s*:=\s*5", out), out


class TestAggregateFilterRewrite:
    """PG's ``agg(x) FILTER (WHERE p)`` has no T-SQL/MySQL/Oracle
    spelling but a faithful universal rewrite: ``agg(CASE WHEN p THEN
    x END)`` (``COUNT(*)`` counts ``1``); it shipped verbatim (error
    102, the ``SELECT (SELECT`` class)."""

    @pytest.mark.parametrize("target", ["tsql", "mysql", "oracle"])
    def test_count_star_filter(self, target: str) -> None:
        out = _t("select count(*) filter (where c <> 0) from t;", target)
        assert "FILTER" not in out.upper(), out
        assert re.search(r"(?is)COUNT\(CASE\s+WHEN c <> 0 THEN 1\s+END\)", out), out

    def test_agg_arg_filter(self) -> None:
        out = _t("select sum(x) filter (where y > 5) from t;", "tsql")
        assert "FILTER" not in out.upper(), out
        assert re.search(r"(?is)SUM\(CASE\s+WHEN y > 5 THEN x\s+END\)", out), out


class TestIndexRebuildRefinements:
    """Residual index shapes: a PG opclass (``roomno bpchar_ops``) is a
    PG-only concept — strip it and keep the column (error 35336); a
    filtered-index predicate outside T-SQL's restricted grammar
    (``id1 % 1000 = 1``, error 10735) drops the WHERE with a note on a
    non-unique index and degrades WHOLE on a unique one (a broader
    UNIQUE index would change semantics)."""

    def test_opclass_stripped(self) -> None:
        out = _t(
            "create unique index r_no on room using btree(roomno bpchar_ops);",
            "tsql",
        )
        assert "bpchar_ops" not in out, out
        assert re.search(r"(?i)CREATE UNIQUE INDEX r_no ON room \(roomno\)", out), out

    def test_complex_predicate_nonunique_drops_where(self) -> None:
        out = _t("create index i1 on j1(id1) where id1 % 1000 = 1;", "tsql")
        assert "WHERE" not in out.upper(), out
        assert re.search(r"(?i)CREATE INDEX i1 ON j1 \(id1\)", out), out
        assert "UNIQUE:" in out, out

    def test_complex_predicate_unique_degrades(self) -> None:
        r = Transpiler().transpile(
            "create unique index u1 on j1(id1) where id1 % 1000 = 1;",
            source="postgresql",
            target="tsql",
        )
        code = [
            ln
            for ln in r.sql.splitlines()
            if ln.strip() and not ln.strip().startswith("--")
        ]
        assert not code, r.sql


class TestSessionAuthorizationDegrades:
    """``SET SESSION AUTHORIZATION`` kept its path in wave 1 as a
    "real SQL SET", but only PostgreSQL has it (6x on MySQL + 6x on
    Oracle); off PG it degrades to the documented carrier."""

    @pytest.mark.parametrize("target", ["mysql", "oracle", "tsql"])
    def test_session_authorization_degrades(self, target: str) -> None:
        r = Transpiler().transpile(
            "SET SESSION AUTHORIZATION regress_user;",
            source="postgresql",
            target=target,
        )
        code = [
            ln
            for ln in r.sql.splitlines()
            if ln.strip() and not ln.strip().startswith("--")
        ]
        assert not code, r.sql

    def test_kept_on_pg(self) -> None:
        out = _t("SET SESSION AUTHORIZATION regress_user;", "postgresql")
        assert re.search(r"(?i)SET SESSION AUTHORIZATION", out), out
        assert "UNIQUE:" not in out, out


class TestMysqlUserTypesDegrade:
    """MySQL has no user-defined types in any form; ``DROP TYPE IF
    EXISTS t`` shipped raw (1064, 5x). Degrades with a warning on
    MySQL; Oracle/T-SQL keep their native DROP TYPE."""

    def test_drop_type_degrades_mysql(self) -> None:
        r = Transpiler().transpile(
            "drop type if exists compos;", source="postgresql", target="mysql"
        )
        code = [
            ln
            for ln in r.sql.splitlines()
            if ln.strip() and not ln.strip().startswith("--")
        ]
        assert not code, r.sql
        assert r.warnings or r.unsupported, r.sql

    def test_drop_type_kept_on_oracle(self) -> None:
        out = _t("drop type if exists compos;", "oracle")
        assert re.search(r"(?i)DROP TYPE", out), out


class TestQualifiedStarCountDegrades:
    """PG's whole-row ``COUNT(t2.*)`` (counts non-NULL rows after an
    outer join) has no spelling on any other engine and no mechanical
    rewrite without schema knowledge (9x 1064). COUNT with a QUALIFIED
    star degrades whole; plain ``COUNT(*)`` is untouched."""

    @pytest.mark.parametrize("target", ["mysql", "tsql", "oracle"])
    def test_qualified_star_count_degrades(self, target: str) -> None:
        r = Transpiler().transpile(
            "select t1.q2, count(t2.*) from t1 left join t2 on t1.a = t2.a "
            "group by t1.q2;",
            source="postgresql",
            target=target,
        )
        code = [
            ln
            for ln in r.sql.splitlines()
            if ln.strip() and not ln.strip().startswith("--")
        ]
        assert not code, r.sql
        assert r.warnings or r.unsupported, r.sql

    def test_plain_count_star_untouched(self) -> None:
        out = _t("select count(*) from t;", "mysql")
        assert re.search(r"(?i)COUNT\(\*\)", out), out
        assert "UNIQUE:" not in out, out


class TestPgIndexToMysql:
    """MySQL also requires an index name (4x nameless) and has NO
    filtered indexes at all: the wave-15 rebuild generalizes — name
    synthesis and opclass strip apply, any WHERE drops with a note on
    plain indexes and degrades WHOLE on unique ones."""

    def test_nameless_index_named_mysql(self) -> None:
        out = _t("create index on fkest(x, x10);", "mysql")
        assert re.search(r"(?i)CREATE INDEX \w+ ON fkest", out), out

    def test_partial_index_where_dropped_mysql(self) -> None:
        out = _t("create index i1 on j1(id1) where id1 is not null;", "mysql")
        assert "WHERE" not in out.upper(), out
        assert re.search(r"(?i)CREATE INDEX i1 ON j1 \(id1\)", out), out
        assert "UNIQUE:" in out, out

    def test_partial_unique_degrades_mysql(self) -> None:
        r = Transpiler().transpile(
            "create unique index u1 on j1(id1) where id1 is not null;",
            source="postgresql",
            target="mysql",
        )
        code = [
            ln
            for ln in r.sql.splitlines()
            if ln.strip() and not ln.strip().startswith("--")
        ]
        assert not code, r.sql


class TestRaiseResidue:
    """raise_test's remaining blockers: a bare re-``RAISE;`` inside an
    exception handler emitted ``SET MESSAGE_TEXT = ;`` (empty — broken
    re-raise AND a syntax error); the faithful MySQL form is
    ``RESIGNAL;`` (T-SQL: ``THROW;``). And a level-less ``RAISE 'msg'
    USING …`` (defaults to EXCEPTION) skipped the wave-10 format
    parser, shipping the USING tail raw with the old mislabeled
    warning."""

    _RERAISE = (
        "create function rr2() returns int as $$\n"
        "begin\n"
        "  begin\n"
        "    perform 1/0;\n"
        "  exception when others then\n"
        "    raise;\n"
        "  end;\n"
        "  return 1;\n"
        "end$$ language plpgsql;"
    )

    def test_bare_reraise_mysql_resignal(self) -> None:
        out = _t(self._RERAISE, "mysql")
        assert "MESSAGE_TEXT = ;" not in out, out
        assert re.search(r"(?i)\bRESIGNAL\s*;", out), out

    def test_levelless_raise_using_folds(self) -> None:
        r = Transpiler().transpile(
            "create function rl() returns int as $$\n"
            "begin\n"
            "  raise 'check me' using errcode = 'division_by_zero';\n"
            "  return 1;\nend$$ language plpgsql;",
            source="postgresql",
            target="mysql",
        )
        # the USING options fold INTO the message string; they must not
        # remain as a raw clause after the SIGNAL statement
        assert not re.search(r"(?i)MESSAGE_TEXT\s*=\s*'[^']*'\s+using", r.sql), r.sql
        assert re.search(r"(?i)MESSAGE_TEXT\s*=\s*@uq_errmsg", r.sql), r.sql
        assert "check me" in r.sql, r.sql
        joined = " ".join(w.message for w in r.warnings)
        assert "RAISERROR" not in joined, r.warnings
        assert "folded into the message" in joined, r.warnings


class TestTsqlRaiserrorExpressionHoist:
    """RAISERROR's message argument accepts only a literal or a
    variable; an expression payload starting with a quote
    (``'a' + '…'`` from the wave-10 fold) fooled the is_direct
    heuristic and shipped inline (error 102 near '+'). Expression
    payloads hoist through the @unique_errmsgN variable. PG's
    ``sqlerrm``/``sqlstate`` diagnostics map to ERROR_MESSAGE() /
    ERROR_STATE() inside the CATCH (state domain differs — warned)."""

    def test_concat_payload_hoists(self) -> None:
        out = _t(
            "create function rt3() returns int as $$\n"
            "begin\n"
            "  raise exception 'bad %', 'x' using hint = 'h';\n"
            "  return 1;\nend$$ language plpgsql;",
            "tsql",
        )
        m = re.search(r"(?is)RAISERROR\((.+?),\s*16,\s*1\)", out)
        assert m, out
        payload = m.group(1).strip()
        assert payload.startswith("@") or re.fullmatch(r"'(?:[^']|'')*'", payload), out

    def test_sqlerrm_maps_to_error_message(self) -> None:
        out = _t(
            "create function rt4() returns int as $$\n"
            "begin\n"
            "  begin\n    perform 1;\n"
            "  exception when others then\n"
            "    raise notice 'E: %', sqlerrm;\n"
            "  end;\n  return 1;\nend$$ language plpgsql;",
            "tsql",
        )
        assert re.search(r"(?i)ERROR_MESSAGE\(\)", out), out
        assert not re.search(r"(?i)\bsqlerrm\b", out), out


class TestPerformDiscard:
    """plpgsql ``PERFORM …`` (evaluate and discard) reached sqlglot as
    raw text and mangled to ``perform;``. It converts to the target's
    discard idiom (a discard-variable SELECT INTO / DO); the word
    ``perform`` must never survive."""

    _SRC = (
        "create function pd() returns int as $$\n"
        "begin\n"
        "  perform log_call(1, 'x');\n"
        "  return 1;\n"
        "end$$ language plpgsql;"
    )

    @pytest.mark.parametrize("target", ["mysql", "tsql", "oracle"])
    def test_perform_converts(self, target: str) -> None:
        out = _t(self._SRC, target)
        assert "perform" not in out.lower(), out
        assert re.search(r"(?i)log_call\s*\(\s*1\s*,\s*'x'\s*\)", out), out


class TestMysqlSessionKnobsDegrade:
    """mysql-source wave M1 — the mirror of pg wave 1: ``SET
    [@@]sql_mode = …`` (and any SET whose value reads an ``@@`` system
    variable, e.g. the save/restore pattern) plus admin commands
    (``FLUSH STATUS``) are engine-local session knobs; off MySQL they
    degrade to the documented carrier (they were the largest
    mysql-source baseline classes: 68–124x per direction)."""

    @pytest.mark.parametrize("target", ["postgresql", "oracle", "tsql"])
    @pytest.mark.parametrize(
        "sql",
        [
            "SET sql_mode = 'NO_ENGINE_SUBSTITUTION';",
            "SET @@sql_mode = concat(@@sql_mode, ',STRICT_ALL_TABLES');",
            "SET @prev_mode = @@SESSION.sql_mode;",
            "FLUSH STATUS;",
        ],
    )
    def test_knob_degrades(self, sql: str, target: str) -> None:
        r = Transpiler().transpile(sql, source="mysql", target=target)
        code = [
            ln
            for ln in r.sql.splitlines()
            if ln.strip() and not ln.strip().startswith("--")
        ]
        assert not code, r.sql

    def test_plain_user_var_not_gated(self) -> None:
        r = Transpiler().transpile("SET @n = 5;", source="mysql", target="postgresql")
        assert "@@" not in r.sql, r.sql
        # a plain user-variable SET is NOT a session knob; whatever its
        # translation, it must not get the session-setting carrier
        assert "session setting" not in r.sql.lower(), r.sql


class TestMysqlCtasAndTypes:
    """mysql-source wave M2: `CREATE TABLE t [AS] SELECT …` silently
    LOST its query (the converter never read sqlglot's `expression` —
    0 warnings, the worst class); MySQL `DOUBLE(11,0)` maps to PG
    `DOUBLE PRECISION` which takes no params; and `$a` is a legal
    MySQL table name that PG needs quoted."""

    def test_ctas_keeps_query_pg(self) -> None:
        out = _t2("create table tmp select 1+2 as s, 'a' as c;", "mysql", "postgresql")
        assert re.search(r"(?i)CREATE TABLE tmp AS", out), out
        assert re.search(r"(?i)SELECT 1 \+ 2 AS s", out), out

    def test_ctas_keeps_query_tsql(self) -> None:
        out = _t2("create table tmp as select 1 as x;", "mysql", "tsql")
        assert re.search(r"(?i)SELECT 1 AS x", out), out

    def test_double_precision_params_dropped_pg(self) -> None:
        out = _t2("create table d2 (price double(11,0));", "mysql", "postgresql")
        assert re.search(r"(?i)DOUBLE PRECISION\s*(?!\()", out), out
        assert "DOUBLE PRECISION(" not in out.upper(), out

    def test_dollar_table_name_quoted_pg(self) -> None:
        out = _t2("create table $a as select 1 as x;", "mysql", "postgresql")
        assert '"$a"' in out, out


class TestTsqlEmptyBeginBlock:
    """A nested ``BEGIN … END`` whose body is only comments (mysql's
    ``BEGIN NULL; END`` style scopes) is a T-SQL syntax error (156 near
    END); it gets the canonical no-op filler, same as empty BEGIN TRY."""

    def test_comment_only_block_gets_filler(self) -> None:
        out = _t2(
            "delimiter //\ncreate procedure scope_p(a int)\nbegin\n"
            "  begin\n    -- just a scope\n  end;\nend//\ndelimiter ;",
            "mysql",
            "tsql",
        )
        inner = re.findall(r"(?is)BEGIN\s*(.*?)\s*END", out)
        assert all(
            any(
                ln.strip() and not ln.strip().startswith("--")
                for ln in seg.splitlines()
            )
            or "NOCOUNT" in seg
            for seg in inner
            if seg is not None
        ), out


class TestTsqlCtasBecomesSelectInto:
    """T-SQL has no CREATE TABLE AS: the faithful idiom is
    ``SELECT … INTO <table> FROM …`` (133x after wave M2 made CTAS
    queries survive). Views over temp tables (error 4508) degrade
    whole; other targets keep their CTAS."""

    def test_ctas_select_into_tsql(self) -> None:
        out = _t2(
            "create temporary table tmp as select a, b from t3;",
            "mysql",
            "tsql",
        )
        assert "CREATE TABLE" not in out.upper(), out
        assert re.search(r"(?is)SELECT a, b\s+INTO #tmp\s+FROM t3", out), out

    def test_ctas_kept_on_oracle(self) -> None:
        out = _t2("create table tmp2 as select 1 as x;", "mysql", "oracle")
        assert re.search(r"(?i)CREATE TABLE tmp2 AS", out), out

    def test_view_on_temp_table_degrades_tsql(self) -> None:
        r = Transpiler().transpile(
            "create temporary table t1x (a int);\n"
            "create view v1 as select * from t1x;",
            source="mysql",
            target="tsql",
        )
        # the view must not ship executable; the carrier explains why
        view_lines = [
            ln
            for ln in r.sql.splitlines()
            if ln.strip() and not ln.strip().startswith("--") and "VIEW" in ln.upper()
        ]
        assert not view_lines, r.sql
        assert any("temporary tables" in w.message for w in r.warnings), r.warnings


class TestCreateTableLikeClone:
    """MySQL's ``CREATE TABLE t2 LIKE t1`` (structure clone) silently
    dropped its LIKE everywhere (bare ``CREATE TABLE t2``, 0 warnings,
    26x). PG has the native ``(LIKE t1)``; T-SQL/Oracle clone via an
    empty CTAS (``WHERE 1 = 0``) with a note that indexes/keys are not
    cloned."""

    def test_like_native_pg(self) -> None:
        out = _t2("create table t2 like t1;", "mysql", "postgresql")
        assert re.search(r"(?i)CREATE TABLE t2 \(LIKE t1", out), out

    def test_like_tsql_empty_select_into(self) -> None:
        r = Transpiler().transpile(
            "create table t2 like t1;", source="mysql", target="tsql"
        )
        assert re.search(
            r"(?is)SELECT \*\s+INTO t2\s+FROM t1\s+WHERE 1 = 0", r.sql
        ), r.sql
        assert any("not cloned" in w.message for w in r.warnings), r.warnings

    def test_like_oracle_empty_ctas(self) -> None:
        out = _t2("create table t2 like t1;", "mysql", "oracle")
        assert re.search(
            r"(?is)CREATE TABLE t2 AS\s+SELECT \*\s+FROM t1\s+WHERE 1 = 0", out
        ), out


class TestInsertQualifiedColumns:
    """``INSERT INTO t5 (t5.a, t5.b) VALUES …`` (table-qualified column
    lists, legal in MySQL) truncated to ``INSERT INTO t5 (t5)`` with the
    body gone — the 2026-07-09 audit class still alive in the embedded
    procedural path. The qualifier drops (the columns belong to the
    INSERT's table by definition — valid and exact everywhere)."""

    @pytest.mark.parametrize("target", ["postgresql", "tsql", "oracle"])
    def test_qualifier_drops(self, target: str) -> None:
        out = _t2("insert into t5 (t5.a, t5.b) values (1, 2);", "mysql", target)
        assert re.search(r"(?i)INSERT INTO t5 \(a, b\)", out), out
        assert re.search(r"(?i)VALUES\s*\(1,\s*2\)", out), out

    def test_inside_procedure_body(self) -> None:
        out = _t2(
            "delimiter //\ncreate procedure bp()\nbegin\n"
            "  insert into t5 (t5.a) values (9);\nend//\ndelimiter ;",
            "mysql",
            "postgresql",
        )
        assert re.search(r"(?i)INSERT INTO t5 \(a\)", out), out
        assert re.search(r"(?i)VALUES\s*\(9\)", out), out


class TestParameterizedCursors:
    """PG's name-first ``c1 CURSOR (p1 int) FOR …`` shredded the declare
    section (``c1 cursor; for select; …`` garbage) and ``OPEN c1(5)``
    dropped its argument as a stray statement. Oracle/PG have native
    parameterized cursors; T-SQL/MySQL do not — the routine degrades
    whole there."""

    _SRC = (
        "create function pc() returns int as $$\n"
        "declare c1 cursor (p1 int) for select a from t where a > p1;\n"
        "begin\n  open c1(5);\n  close c1;\n  return 1;\nend$$ "
        "language plpgsql;"
    )

    def test_oracle_native(self) -> None:
        out = _t(self._SRC, "oracle")
        assert re.search(r"(?is)CURSOR c1\s*\(p1 .*?\)\s*IS\s*SELECT", out), out
        assert re.search(r"(?i)OPEN c1\s*\(5\)", out), out
        assert "for select;" not in out.lower(), out

    def test_pg_native(self) -> None:
        out = _t(self._SRC, "postgresql")
        assert re.search(r"(?is)c1 CURSOR \(p1 int\) FOR\s+SELECT", out), out
        assert re.search(r"(?i)OPEN c1\s*\(5\)", out), out

    @pytest.mark.parametrize("target", ["tsql", "mysql"])
    def test_degrades_elsewhere(self, target: str) -> None:
        r = Transpiler().transpile(self._SRC, source="postgresql", target=target)
        code = [
            ln
            for ln in r.sql.splitlines()
            if ln.strip() and not ln.strip().startswith("--")
        ]
        assert not code, r.sql
        assert any("cursor" in w.message.lower() for w in r.warnings), r.warnings


class TestOracleUnderscoreLocals:
    """Leading-underscore locals (`_sqlstate text`) are illegal unquoted
    in PL/SQL; quoting would have to reach every raw-text reference, so
    they RENAME (`uq_sqlstate`) via the _var_map rewrite — declare,
    assignments and expression references stay consistent; string
    literals untouched."""

    def test_underscore_local_renamed(self) -> None:
        out = _t(
            "create function sdx() returns text as $$\n"
            "declare _msg text;\n"
            "begin\n  _msg = 'x';\n  return '_msg: ' || _msg;\nend$$ "
            "language plpgsql;",
            "oracle",
        )
        assert re.search(r"(?i)uq_msg text", out), out
        assert re.search(r"(?i)uq_msg := 'x'", out), out
        assert re.search(r"'_msg: ' \|\| uq_msg", out), out


class TestGetDiagnostics:
    """plpgsql ``GET [STACKED] DIAGNOSTICS v = ITEM, …`` (15x) mangled
    to ``get AS stacked;``. It converts to plain per-target
    assignments — Oracle SQLERRM/SQL%ROWCOUNT/FORMAT_ERROR_BACKTRACE,
    T-SQL ERROR_*()/@@ROWCOUNT — via the existing assignment emitters;
    PG keeps the native form."""

    _ROWS = (
        "create function gd1() returns int as $$\n"
        "declare n int;\n"
        "begin\n"
        "  update t set a = 1;\n"
        "  get diagnostics n = row_count;\n"
        "  return n;\n"
        "end$$ language plpgsql;"
    )
    _STACKED = (
        "create function gd2() returns text as $$\n"
        "declare m text;\n"
        "begin\n"
        "  begin\n    perform 1;\n"
        "  exception when others then\n"
        "    get stacked diagnostics m = message_text;\n"
        "  end;\n"
        "  return m;\n"
        "end$$ language plpgsql;"
    )

    def test_row_count_oracle(self) -> None:
        out = _t(self._ROWS, "oracle")
        assert re.search(r"(?i)n := SQL%ROWCOUNT", out), out
        assert "diagnostics" not in out.lower(), out

    def test_row_count_tsql(self) -> None:
        out = _t(self._ROWS, "tsql")
        assert re.search(r"(?i)SET @n = @@ROWCOUNT", out), out
        assert "diagnostics" not in out.lower(), out

    def test_message_text_oracle(self) -> None:
        out = _t(self._STACKED, "oracle")
        assert re.search(r"(?i)m := SQLERRM", out), out

    def test_native_kept_on_pg(self) -> None:
        out = _t(self._ROWS, "postgresql")
        assert re.search(r"(?i)GET DIAGNOSTICS n = ROW_COUNT", out), out


class TestForExecuteLiteralInlines:
    """``FOR v IN EXECUTE '<literal>' LOOP`` — after wave 18 the
    dynamic string is a plain literal, so the EXECUTE is unnecessary:
    the query inlines (faithful on every target; the transition-table
    trigger family shipped ``CURSOR FOR execute '…'``, invalid T-SQL).
    A non-literal EXECUTE (variable SQL) degrades whole."""

    _SRC = (
        "create function fe() returns int as $$\n"
        "declare l int;\n"
        "begin\n"
        "  for l in execute $q$ select a from d $q$ loop\n"
        "    null;\n"
        "  end loop;\n"
        "  return 1;\n"
        "end$$ language plpgsql;"
    )

    def test_literal_execute_inlines_tsql(self) -> None:
        out = _t(self._SRC, "tsql")
        assert "execute '" not in out.lower(), out
        assert re.search(r"(?i)CURSOR .*FOR\s+select a from d", out), out

    def test_literal_execute_inlines_oracle(self) -> None:
        out = _t(self._SRC, "oracle")
        assert "execute '" not in out.lower(), out
        assert re.search(r"(?i)select a from d", out), out

    def test_variable_execute_degrades(self) -> None:
        r = Transpiler().transpile(
            "create function fv(q text) returns int as $$\n"
            "declare l int;\n"
            "begin\n  for l in execute q loop\n    null;\n  end loop;\n"
            "  return 1;\nend$$ language plpgsql;",
            source="postgresql",
            target="tsql",
        )
        code = [
            ln
            for ln in r.sql.splitlines()
            if ln.strip() and not ln.strip().startswith("--")
        ]
        assert not code, r.sql
        assert any("dynamic" in w.message.lower() for w in r.warnings), r.warnings


class TestTransitionTableAliases:
    """PG statement triggers name their transition tables
    (``REFERENCING NEW TABLE AS newtab``); T-SQL's are the fixed
    ``inserted``/``deleted`` pseudo-tables. The inlined body's alias
    references rename (18x, the largest remaining tsql class)."""

    _SRC = (
        "create function ttf() returns trigger as $$\n"
        "begin\n"
        "  insert into log select a from newtab where a <> 'newtab';\n"
        "  return null;\nend$$ language plpgsql;\n"
        "create trigger tg after insert on d "
        "referencing new table as newtab "
        "for each statement execute function ttf();"
    )

    def test_new_table_alias_becomes_inserted(self) -> None:
        out = _t(self._SRC, "tsql")
        assert re.search(r"(?i)FROM inserted\b", out), out
        assert not re.search(r"(?i)FROM newtab\b", out), out
        # the string literal naming the alias stays untouched
        assert "'newtab'" in out, out

    def test_pg_keeps_referencing(self) -> None:
        out = _t(self._SRC, "postgresql")
        assert re.search(r"(?i)REFERENCING new TABLE AS newtab", out), out


class TestForExecuteNonQueryDegrades:
    """A FOR-EXECUTE literal that is NOT a query (the transition-table
    tests iterate dynamic EXPLAIN output — engine introspection) has no
    conversion anywhere: the routine degrades whole instead of shipping
    ``dbo.EXPLAIN (…)`` as a cursor source."""

    def test_explain_literal_degrades(self) -> None:
        r = Transpiler().transpile(
            "create function fx() returns int as $$\n"
            "declare l text;\n"
            "begin\n"
            "  for l in execute $q$ explain (costs off) select 1 $q$ loop\n"
            "    null;\n"
            "  end loop;\n"
            "  return 1;\nend$$ language plpgsql;",
            source="postgresql",
            target="tsql",
        )
        code = [
            ln
            for ln in r.sql.splitlines()
            if ln.strip() and not ln.strip().startswith("--")
        ]
        assert not code, r.sql


class TestTriggerInlineDegradeGate:
    """The trigger-inline path bypassed the routine-level degrade scan
    (two flat waves before the end-to-end trace found it): an
    unconvertible inlined body must degrade the TRIGGER whole."""

    def test_dynamic_explain_trigger_degrades_whole(self) -> None:
        src = (
            "CREATE FUNCTION tfn() RETURNS trigger LANGUAGE plpgsql AS $$\n"
            "DECLARE l text;\n"
            "BEGIN\n"
            "  FOR l IN EXECUTE $q$ EXPLAIN (COSTS off) SELECT 1 $q$ LOOP\n"
            "    NULL;\n  END LOOP;\n  RETURN NULL;\nEND; $$;\n"
            "CREATE TRIGGER ttr AFTER INSERT ON bt "
            "REFERENCING NEW TABLE AS nt FOR EACH STATEMENT "
            "EXECUTE PROCEDURE tfn();"
        )
        r = Transpiler().transpile(src, source="postgresql", target="tsql")
        code = [
            ln
            for ln in r.sql.splitlines()
            if ln.strip() and not ln.strip().startswith("--")
        ]
        assert not code, r.sql
        assert any("introspection" in w.message for w in r.warnings), r.warnings


class TestPlpgsqlFoundFlag:
    """plpgsql's ``FOUND`` flag (set by the last DML) shipped bare —
    error 4145 on T-SQL. Per-target predicates: ``(@@ROWCOUNT > 0)``,
    ``(ROW_COUNT() > 0)``, Oracle's native ``SQL%FOUND``."""

    _SRC = (
        "create function ff() returns int as $$\n"
        "begin\n"
        "  update t set a = 1;\n"
        "  if found then\n    return 1;\n  end if;\n"
        "  if not found then\n    return 2;\n  end if;\n"
        "  return 0;\n"
        "end$$ language plpgsql;"
    )

    def test_found_tsql(self) -> None:
        out = _t(self._SRC, "tsql")
        assert re.search(r"(?i)IF \(@@ROWCOUNT > 0\)", out), out
        assert not re.search(r"(?i)\bIF FOUND\b", out), out

    def test_found_mysql(self) -> None:
        out = _t(self._SRC, "mysql")
        assert re.search(r"(?i)IF \(ROW_COUNT\(\) > 0\)", out), out

    def test_found_oracle(self) -> None:
        out = _t(self._SRC, "oracle")
        assert re.search(r"(?i)IF SQL%FOUND", out), out


class TestTgContextConstants:
    """plpgsql's TG_* context variables are compile-time CONSTANTS once
    the function is inlined into a named trigger: TG_NAME/TG_TABLE_NAME/
    TG_OP/TG_WHEN/TG_LEVEL substitute as literals (18x error 128)."""

    _SRC = (
        "create function cf() returns trigger as $$\n"
        "begin\n"
        "  insert into log values (TG_NAME, TG_OP, TG_LEVEL);\n"
        "  return null;\nend$$ language plpgsql;\n"
        "create trigger child1_ins after insert on child1 "
        "for each statement execute function cf();"
    )

    def test_tg_constants_substitute_tsql(self) -> None:
        out = _t(self._SRC, "tsql")
        assert "'child1_ins'" in out, out
        assert "'INSERT'" in out, out
        assert "'STATEMENT'" in out, out
        assert "TG_NAME" not in out.upper(), out


class TestNullSafeComparison:
    """PG's ``IS [NOT] DISTINCT FROM`` (null-safe comparison) shipped
    raw as an unmapped operator (1064 on MySQL). Per-target: MySQL's
    ``<=>``, the version-safe EXISTS-INTERSECT form on T-SQL/Oracle,
    PG native."""

    def test_mysql_spaceship(self) -> None:
        out = _t2("select 2 is not distinct from null as x;", "postgresql", "mysql")
        assert re.search(r"2 <=> NULL", out), out
        out2 = _t2("select 2 is distinct from 3 as x;", "postgresql", "mysql")
        assert re.search(r"(?i)NOT \(2 <=> 3\)", out2), out2

    def test_tsql_intersect_form_value_position(self) -> None:
        # a predicate is not a value on T-SQL: select-list wraps in CASE
        out = _t2("select a is distinct from b from t;", "postgresql", "tsql")
        assert re.search(
            r"(?is)CASE WHEN NOT EXISTS \(SELECT a INTERSECT SELECT b\)"
            r"\s+THEN 1 ELSE 0 END",
            out,
        ), out

    def test_tsql_condition_position_bare(self) -> None:
        out = _t2("select 1 from t where a is distinct from b;", "postgresql", "tsql")
        assert re.search(
            r"(?i)WHERE NOT EXISTS \(SELECT a INTERSECT SELECT b\)", out
        ), out
        assert "CASE WHEN NOT EXISTS" not in out.upper(), out

    def test_oracle_intersect_form(self) -> None:
        out = _t2("select a is not distinct from b from t;", "postgresql", "oracle")
        assert re.search(
            r"(?i)EXISTS \(SELECT a FROM DUAL INTERSECT SELECT b FROM DUAL\)",
            out,
        ), out

    def test_pg_native(self) -> None:
        out = _t2("select a is distinct from b from t;", "postgresql", "postgresql")
        assert re.search(r"(?i)a IS DISTINCT FROM b", out), out


class TestSelectListComparisonsWrap:
    """MySQL comparisons are VALUES (1/0/NULL); T-SQL/Oracle reject a
    predicate in the select list (38x error 102). The tri-state CASE
    wrap is exact: WHEN p THEN 1 WHEN NOT-p THEN 0 (ELSE NULL implicit
    — MySQL's NULL comparison semantics)."""

    def test_comparison_wraps_tsql(self) -> None:
        out = _t2(
            "select cast('2007-10-09' as date) > '2007-10-01' as c;", "mysql", "tsql"
        )
        assert re.search(
            r"(?is)CASE WHEN .* > .* THEN 1 WHEN .* <= .*", out
        ) or re.search(r"(?is)CASE WHEN .* THEN 1 WHEN NOT", out), out
        assert not re.search(r"(?im)^\s*SELECT CAST\([^)]*\) >", out), out

    def test_condition_position_untouched(self) -> None:
        out = _t2("select 1 from t where a > b;", "mysql", "tsql")
        assert re.search(r"(?i)WHERE a > b", out), out
        assert "CASE" not in out.upper(), out

    def test_pg_target_keeps_boolean_value(self) -> None:
        out = _t2("select a > b as c from t;", "mysql", "postgresql")
        assert re.search(r"(?i)a > b", out), out
        assert "CASE" not in out.upper(), out


class TestMysqlSingleStatementBody:
    """MySQL routine bodies may be a SINGLE statement without BEGIN
    (``CREATE PROCEDURE g(..) CASE … END CASE;``); the declare-section
    parser shredded them into garbage declarations."""

    def test_case_body_parses(self) -> None:
        out = _t2(
            "delimiter //\ncreate procedure g(x int)\n"
            "case when x < 0 then insert into t1 values (0);\n"
            "else insert into t1 values (2);\nend case//\ndelimiter ;",
            "mysql",
            "postgresql",
        )
        assert "case when;" not in out.lower(), out
        # the CASE statement legitimately converts to IF/ELSE
        assert re.search(r"(?is)(?:CASE\s+WHEN|IF) x < 0", out), out
        assert out.upper().count("INSERT INTO t1".upper()) == 2, out

    def test_single_insert_body_parses(self) -> None:
        out = _t2(
            "delimiter //\ncreate procedure h()\n"
            "insert into t1 values (1)//\ndelimiter ;",
            "mysql",
            "oracle",
        )
        assert re.search(r"(?i)INSERT INTO t1 VALUES \(1\)", out), out
        assert "insert into;" not in out.lower(), out


class TestBareCreateResidue:
    """Two more dropped-definition shapes (54x bare `CREATE TABLE` in
    mysql→pg): a table whose columns are ALL generated (they route to
    passthrough fragments, `columns` is empty and the emit skipped the
    whole parenthesized branch — constraints included); and CTAS whose
    query is a UNION (the M2 extraction accepted only exp.Select)."""

    def test_all_generated_columns_survive(self) -> None:
        out = _t2(
            "create table tg1 (a int generated always as (1) virtual, "
            "b int generated always as (a) virtual);",
            "mysql",
            "postgresql",
        )
        assert "(" in out.split("\n")[0] or "GENERATED" in out.upper(), out
        assert re.search(r"(?i)GENERATED ALWAYS AS", out), out

    def test_union_ctas_survives(self) -> None:
        out = _t2(
            "create table t3 select a from t1 union all select a from t2;",
            "mysql",
            "postgresql",
        )
        assert re.search(r"(?i)CREATE TABLE t3 AS", out), out
        assert re.search(r"(?i)UNION ALL", out), out


class TestEmptyValuesAndIsNullValue:
    """wave 46: MySQL's all-defaults ``INSERT INTO t VALUES ()`` maps
    to ``DEFAULT VALUES`` on T-SQL/PG (Oracle degrades — no spelling
    without the column list); and an ``IS NULL`` in VALUE position
    (an unmapped-Is RawSQL) wraps tri-state like wave 43's
    comparisons."""

    def test_empty_values_tsql(self) -> None:
        out = _t2("insert into t1 () values ();", "mysql", "tsql")
        assert re.search(r"(?is)INSERT INTO t1\s+DEFAULT VALUES", out), out

    def test_empty_values_pg(self) -> None:
        out = _t2("insert into t1 values ();", "mysql", "postgresql")
        assert re.search(r"(?is)INSERT INTO t1\s+DEFAULT VALUES", out), out

    def test_empty_values_oracle_degrades(self) -> None:
        r = Transpiler().transpile(
            "insert into t1 values ();", source="mysql", target="oracle"
        )
        code = [
            ln
            for ln in r.sql.splitlines()
            if ln.strip() and not ln.strip().startswith("--")
        ]
        assert not code, r.sql

    def test_is_null_value_wraps_tsql(self) -> None:
        out = _t2("select cast(null as date) is null as x;", "mysql", "tsql")
        assert re.search(r"(?is)CASE WHEN CAST\(NULL AS DATE\) IS NULL", out), out


class TestNaturalJoins:
    """wave 47: NATURAL join modifiers survive to engines that speak
    them (PG/MySQL/Oracle) instead of silently dropping — the residue
    emitted ``FULL JOIN`` with no ON at all. T-SQL has no NATURAL in
    any spelling and cannot synthesize the ON without column
    knowledge, so the statement whole-degrades."""

    def test_natural_join_to_mysql(self) -> None:
        out = _t("select * from t1 natural join t2;", "mysql")
        assert re.search(r"(?i)NATURAL JOIN t2", out), out

    def test_natural_full_join_to_oracle(self) -> None:
        out = _t("select * from t1 natural full join t2;", "oracle")
        assert re.search(r"(?i)NATURAL FULL OUTER JOIN t2", out), out

    def test_natural_left_join_derived_to_pg(self) -> None:
        out = _t2(
            "select * from (select a from t1) s1 "
            "natural left join (select a from t2) s2;",
            "mysql",
            "postgresql",
        )
        assert re.search(r"(?is)NATURAL LEFT JOIN \(SELECT", out), out

    def test_natural_join_tsql_degrades(self) -> None:
        r = Transpiler().transpile(
            "select * from t1 natural full join t2;",
            source="postgresql",
            target="tsql",
        )
        code = [
            ln
            for ln in r.sql.splitlines()
            if ln.strip() and not ln.strip().startswith("--")
        ]
        assert not code, r.sql
        assert re.search(r"(?i)natural", r.sql), r.sql


class TestParenthesizedUnionArms:
    """wave 48: parenthesized set-operation arms (``(SELECT …) UNION
    ALL (SELECT …)``) arrive as exp.Subquery; _convert_select read
    them as empty selects, shipping ``SELECT * UNION ALL SELECT *``
    with every FROM/column dropped. Arms unwrap; an arm carrying its
    own ORDER BY+LIMIT is shielded as a derived table (the
    unparenthesized trailing position would re-scope it to the whole
    union); the union's OUTER order/limit attaches to the last arm."""

    def test_paren_union_arms_keep_from(self) -> None:
        out = _t2(
            "(select * from t1) union all (select * from t2);",
            "mysql",
            "postgresql",
        )
        assert re.search(r"(?is)FROM t1\s+UNION ALL\s+SELECT \*\s+FROM t2", out), out

    def test_paren_arm_with_limit_shields(self) -> None:
        out = _t2(
            "select a from t1 union all " "(select a from t2 order by a limit 1);",
            "mysql",
            "postgresql",
        )
        assert re.search(
            r"(?is)UNION ALL\s+SELECT \*\s+FROM \(SELECT a\s+FROM t2\s+"
            r"ORDER BY a[^)]*LIMIT 1\)",
            out,
        ), out

    def test_outer_order_by_survives(self) -> None:
        out = _t2(
            "(select a from t1 limit 2) union all (select a from t2) " "order by a;",
            "mysql",
            "postgresql",
        )
        assert re.search(r"(?is)LIMIT 2", out), out
        assert re.search(r"(?is)FROM t2\s+ORDER BY a\b[^;]*;?\s*$", out), out


class TestNullsafeValuePosition:
    """wave 49: null-safe comparisons in VALUE position on
    T-SQL/Oracle shipped the predicate spelling ``CASE … END = 1``
    (trailing ``= 1`` is not a value there — 12x of pg→tsql). The
    value position keeps just the CASE."""

    def test_is_distinct_select_list_tsql(self) -> None:
        out = _t('select 1 is distinct from 2 as "yes";', "tsql")
        assert "END = 1" not in out, out
        assert re.search(r"(?is)CASE WHEN NOT EXISTS.*END AS \[yes\]", out), out

    def test_is_not_distinct_select_list_oracle(self) -> None:
        out = _t('select 1 is not distinct from 2 as "no";', "oracle")
        assert "END = 1" not in out, out
        assert re.search(r"(?is)CASE WHEN EXISTS.*END AS \"no\"", out), out

    def test_predicate_position_still_bare(self) -> None:
        out = _t("select a from t1 where b is distinct from c;", "tsql")
        assert re.search(r"(?is)WHERE NOT EXISTS \(SELECT", out), out


class TestReturningOutputPrefix:
    """wave 50: PG RETURNING lowers to T-SQL OUTPUT, but T-SQL
    requires every OUTPUT item to carry the INSERTED./DELETED.
    prefix — bare ``OUTPUT *`` / ``OUTPUT a, b`` shipped invalid
    (13x of pg→tsql)."""

    def test_update_returning_star(self) -> None:
        out = _t("update t1 set a = 1 where b = 2 returning *;", "tsql")
        assert re.search(r"(?i)OUTPUT INSERTED\.\*", out), out

    def test_insert_returning_star(self) -> None:
        out = _t("insert into t1 (a) values (1) returning *;", "tsql")
        assert re.search(r"(?i)OUTPUT INSERTED\.\*", out), out

    def test_delete_returning_star(self) -> None:
        out = _t("delete from t1 where a = 1 returning *;", "tsql")
        assert re.search(r"(?i)OUTPUT DELETED\.\*", out), out

    def test_update_returning_columns(self) -> None:
        out = _t("update t1 set a = 1 returning a, b;", "tsql")
        assert re.search(r"(?i)OUTPUT INSERTED\.a, INSERTED\.b", out), out


class TestTgArgvSubstitution:
    """wave 51: TG_ARGV[n] is a compile-time constant once the
    function is inlined into a named trigger — the CREATE TRIGGER's
    EXECUTE FUNCTION argument list supplies the values (8x error 128:
    bare TG_ARGV leaked into the T-SQL trigger). A TG_ARGV whose
    index can't be resolved degrades the trigger whole."""

    _SRC = (
        "create function tf() returns trigger as $$\n"
        "begin\n"
        "  insert into log values (TG_ARGV[0], TG_NARGS);\n"
        "  return null;\nend$$ language plpgsql;\n"
        "create trigger t1_ins after insert on t1 "
        "for each statement execute function tf('hello', 'world');"
    )

    def test_tg_argv_substitutes_tsql(self) -> None:
        out = _t(self._SRC, "tsql")
        assert "'hello'" in out, out
        assert "TG_ARGV" not in out.upper(), out
        assert re.search(r"\b2\b", out), out  # TG_NARGS

    def test_tg_argv_out_of_range_degrades(self) -> None:
        src = (
            "create function tf2() returns trigger as $$\n"
            "begin\n"
            "  insert into log values (TG_ARGV[3]);\n"
            "  return null;\nend$$ language plpgsql;\n"
            "create trigger t2_ins after insert on t2 "
            "for each statement execute function tf2('only');"
        )
        out = _t(src, "tsql")
        offenders = [
            ln
            for ln in out.splitlines()
            if "TG_ARGV" in ln.upper() and not ln.strip().startswith("--")
        ]
        assert not offenders, out


class TestParseFallbackDegradesCrossDialect:
    """wave 52: a routine the procedural parser could not parse falls
    back to RawSQL(reason='Parse error: …') — and shipped RAW to a
    DIFFERENT dialect (~43x of mysql→pg: handler-declaring procedure
    bodies leaked as top-level fragments). Cross-dialect, the parse
    fallback must degrade whole to a documented carrier."""

    _SRC = (
        "DELIMITER //\n"
        "create procedure bug14498_1()\n"
        "begin\n"
        "  declare continue handler for sqlexception select 'error' as 'h';\n"
        "  if v then\n"
        "    select 'yes' as 'v';\n"
        "  end if;\n"
        "  select 'done' as 'e';\n"
        "end//\n"
        "DELIMITER ;\n"
    )

    def test_unparsed_routine_degrades_pg(self) -> None:
        out = _t2(self._SRC, "mysql", "postgresql")
        code = [
            ln
            for ln in out.splitlines()
            if ln.strip() and not ln.strip().startswith("--")
        ]
        assert not code, out
        assert "UNIQUE:" in out, out


class TestTableColumnAliases:
    """wave 53: PG's column-aliased table refs (``x AS xx(xx1, xx2)``)
    silently DROPPED the column list everywhere (7x pg→tsql: the list
    shipped raw inside joins, and plain refs lost the renames). T-SQL
    gets the faithful derived-table rewrite ``(SELECT * FROM x) AS
    xx(xx1, xx2)``; MySQL/Oracle have no spelling without column
    knowledge — whole-degrade."""

    def test_plain_ref_tsql_derived(self) -> None:
        out = _t("select xx1 from x as xx(xx1, xx2);", "tsql")
        assert re.search(
            r"(?is)FROM \(SELECT \* FROM x\) (AS )?xx\s*\(xx1, xx2\)", out
        ), out

    def test_joined_ref_tsql_derived(self) -> None:
        out = _t(
            "select * from y left join x as xx(xx1, xx2) on y1 = xx1;",
            "tsql",
        )
        assert re.search(
            r"(?is)LEFT JOIN \(SELECT \* FROM x\) (AS )?xx\s*\(xx1, xx2\)", out
        ), out

    def test_mysql_degrades_whole(self) -> None:
        r = Transpiler().transpile(
            "select xx1 from x as xx(xx1, xx2);",
            source="postgresql",
            target="mysql",
        )
        code = [
            ln
            for ln in r.sql.splitlines()
            if ln.strip() and not ln.strip().startswith("--")
        ]
        assert not code, r.sql


class TestTsqlInvalidShapesDegrade:
    """wave 54: two shapes shipped invalid T-SQL instead of degrading:
    NTH_VALUE mapped to a fictitious ``dbo.NTH_VALUE(...) OVER`` (a
    scalar UDF cannot take OVER — 4x), and an INSERT carrying BOTH
    RETURNING and ON CONFLICT took the RETURNING passthrough, which
    left ``ON CONFLICT`` raw after OUTPUT (4x)."""

    def test_nth_value_tsql_degrades(self) -> None:
        r = Transpiler().transpile(
            "select nth_value(salary, 2) over (order by salary) from emp;",
            source="postgresql",
            target="tsql",
        )
        code = [
            ln
            for ln in r.sql.splitlines()
            if ln.strip() and not ln.strip().startswith("--")
        ]
        assert not code, r.sql

    def test_returning_with_on_conflict_degrades(self) -> None:
        r = Transpiler().transpile(
            "insert into t (a, b) values (1, 'x') "
            "on conflict (a) do update set b = 'y' returning *;",
            source="postgresql",
            target="tsql",
        )
        out = r.sql
        assert "ON CONFLICT" not in [
            ln for ln in out.splitlines() if not ln.strip().startswith("--")
        ], out
        code = [
            ln
            for ln in out.splitlines()
            if ln.strip()
            and not ln.strip().startswith("--")
            and "ON CONFLICT" in ln.upper()
        ]
        assert not code, out


class TestTsqlBooleanLiteralsAndScalarOrder:
    """wave 55: two mechanical mysql→tsql classes — MySQL treats any
    nonzero numeric as TRUE, so a literal operand of AND/OR in
    condition position must become a real comparison on T-SQL (15x
    error 4145: ``HAVING f1 = 'a' OR 1``); and a scalar subquery's
    ORDER BY without LIMIT is illegal on T-SQL (7x error 1033) and
    meaningless anyway — strip it."""

    def test_or_literal_becomes_comparison(self) -> None:
        out = _t2(
            "select a from t1 having a = 'a' or 1;",
            "mysql",
            "tsql",
        )
        assert re.search(r"(?i)OR 1 <> 0", out), out

    def test_and_zero_literal(self) -> None:
        out = _t2("select a from t1 where a = 1 and 0;", "mysql", "tsql")
        assert re.search(r"(?i)AND 0 <> 0", out), out

    def test_scalar_subquery_order_by_strips(self) -> None:
        out = _t2(
            "select (select 1 as foo order by foo) as x from t1;",
            "mysql",
            "tsql",
        )
        assert "ORDER BY" not in out.upper(), out


class TestSelectIntoUserVariable:
    """wave 56: MySQL's ``SELECT … INTO @var[, @var2]`` (session-
    variable capture) has no faithful cross-dialect conversion —
    sqlglot's parse mangles it (extra vars absorb into the select
    list), and the CTAS path shipped garbage like ``CREATE TABLE $a
    AS …`` (32x mysql→tsql). Off MySQL it degrades whole with the
    assignment-form hint."""

    def test_select_into_var_degrades_tsql(self) -> None:
        r = Transpiler().transpile(
            "select 1, 2 into @a, @b;", source="mysql", target="tsql"
        )
        code = [
            ln
            for ln in r.sql.splitlines()
            if ln.strip() and not ln.strip().startswith("--")
        ]
        assert not code, r.sql

    def test_select_into_var_degrades_pg(self) -> None:
        r = Transpiler().transpile(
            "select count(*) into @cnt from t1;",
            source="mysql",
            target="postgresql",
        )
        code = [
            ln
            for ln in r.sql.splitlines()
            if ln.strip() and not ln.strip().startswith("--")
        ]
        assert not code, r.sql


class TestParenthesizedJoinRelations:
    """wave 57: a parenthesized join relation in FROM —
    ``FROM (t1 AS t2 LEFT JOIN t1 AS t3 USING (a)), t1`` — arrives as
    a Subquery wrapping a Table whose ``joins`` arg the converter
    never read: the whole group shipped raw, USING and all (11x
    mysql→tsql). The group unwraps: inner table + joins hoist into
    the select (parens around joins are semantically transparent;
    emission order preserves the comma-join grouping)."""

    def test_paren_join_using_converts(self) -> None:
        out = _t2(
            "select * from (t1 as x left join t2 as y using (a)), t3;",
            "mysql",
            "tsql",
        )
        assert "USING" not in out.upper(), out
        assert re.search(r"(?is)LEFT JOIN t2 y\s+ON x\.a = y\.a", out), out

    def test_paren_join_on_converts(self) -> None:
        out = _t2(
            "select * from (t1 left join t2 on t1.a = t2.a);",
            "mysql",
            "postgresql",
        )
        assert re.search(r"(?is)FROM t1\s+LEFT JOIN t2 ON t1\.a = t2\.a", out), out


class TestMysqlEdgeValueClasses:
    """wave 58: three mysql→tsql residue classes — CAST of an invalid
    calendar date literal (MySQL returns NULL with a warning;
    '0000-00-00' and friends are hard errors elsewhere — 24x)
    whole-degrades off MySQL; interval arithmetic lowers to DATEADD
    on T-SQL (6x); a MySQL @@sysvar T-SQL doesn't know degrades whole
    (12x error 137)."""

    def test_invalid_date_cast_degrades(self) -> None:
        r = Transpiler().transpile(
            "select cast('0000-00-00' as date);", source="mysql", target="tsql"
        )
        code = [
            ln
            for ln in r.sql.splitlines()
            if ln.strip() and not ln.strip().startswith("--")
        ]
        assert not code, r.sql

    def test_invalid_february_date_degrades(self) -> None:
        r = Transpiler().transpile(
            "select cast('2000-02-31' as date);",
            source="mysql",
            target="postgresql",
        )
        code = [
            ln
            for ln in r.sql.splitlines()
            if ln.strip() and not ln.strip().startswith("--")
        ]
        assert not code, r.sql

    def test_valid_date_cast_still_emits(self) -> None:
        out = _t2("select cast('2000-02-29' as date);", "mysql", "tsql")
        assert re.search(r"(?i)CAST\('2000-02-29' AS DATE\)", out), out

    def test_interval_add_becomes_dateadd(self) -> None:
        out = _t2("select now() + interval 1 day;", "mysql", "tsql")
        assert re.search(r"(?i)DATEADD\(DAY, 1, GETDATE\(\)\)", out), out

    def test_interval_sub_becomes_dateadd(self) -> None:
        out = _t2(
            "select a from t1 where a < b - interval '2' month;",
            "mysql",
            "tsql",
        )
        assert re.search(r"(?i)DATEADD\(MONTH, -2, b\)", out), out

    def test_unknown_sysvar_degrades(self) -> None:
        r = Transpiler().transpile(
            "insert into t1 values (@@connect_timeout);",
            source="mysql",
            target="tsql",
        )
        code = [
            ln
            for ln in r.sql.splitlines()
            if ln.strip() and not ln.strip().startswith("--")
        ]
        assert not code, r.sql


class TestUserVarsRowTuplesOracleDouble:
    """wave 59: three mysql-source classes — a top-level statement
    referencing a MySQL @user variable ships raw off MySQL (no
    equivalent: ORA-00936 / pg syntax error / tsql 137 — degrade
    whole); the EXISTS-INTERSECT null-safe form emitted ROW
    constructors as parenthesized tuples (`SELECT (f1, f2)` — illegal
    select list on Oracle/T-SQL; unpack to items); and DOUBLE(p,s)
    mapped to `BINARY_DOUBLE(7, 2)` on Oracle, which takes no
    parameters (→ NUMBER(p,s))."""

    def test_user_var_select_degrades_oracle(self) -> None:
        r = Transpiler().transpile("select @a, @b;", source="mysql", target="oracle")
        code = [
            ln
            for ln in r.sql.splitlines()
            if ln.strip() and not ln.strip().startswith("--")
        ]
        assert not code, r.sql

    def test_user_var_expr_degrades_pg(self) -> None:
        r = Transpiler().transpile(
            "select @a + 1 from t1;", source="mysql", target="postgresql"
        )
        code = [
            ln
            for ln in r.sql.splitlines()
            if ln.strip() and not ln.strip().startswith("--")
        ]
        assert not code, r.sql

    def test_row_tuple_intersect_unpacks(self) -> None:
        out = _t2(
            "select (1, 2) is distinct from (2, null) as x;",
            "mysql",
            "oracle",
        )
        assert re.search(
            r"(?is)SELECT 1, 2 FROM DUAL INTERSECT SELECT 2, NULL FROM DUAL", out
        ), out

    def test_double_params_to_number_oracle(self) -> None:
        out = _t2(
            "create table t (a double(7,2), b double unsigned);",
            "mysql",
            "oracle",
        )
        assert re.search(r"(?i)a NUMBER\(7, ?2\)", out), out
        assert re.search(r"(?i)b BINARY_DOUBLE", out), out


class TestLateralJoins:
    """wave 60: a LATERAL joined subquery vanished — exp.Lateral fell
    through _convert_table_or_subquery to an EMPTY TableRef (the gate
    then carriered the batch; 7x pg→tsql). T-SQL/Oracle spell it
    APPLY (LEFT+ON TRUE → OUTER APPLY, INNER/CROSS → CROSS APPLY);
    PG/MySQL keep native LATERAL."""

    def test_left_lateral_true_becomes_outer_apply(self) -> None:
        out = _t(
            "select t1.a from t1 left join lateral "
            "(select t2.b from t2 where t2.a = t1.a) ss on true;",
            "tsql",
        )
        assert re.search(r"(?is)OUTER APPLY \(SELECT", out), out
        assert "LATERAL" not in out.upper(), out

    def test_cross_join_lateral_becomes_cross_apply(self) -> None:
        out = _t(
            "select t1.a from t1 cross join lateral "
            "(select t2.b from t2 where t2.a = t1.a) ss;",
            "tsql",
        )
        assert re.search(r"(?is)CROSS APPLY \(SELECT", out), out

    def test_lateral_keeps_native_mysql(self) -> None:
        out = _t(
            "select t1.a from t1 left join lateral "
            "(select t2.b from t2 where t2.a = t1.a) ss on true;",
            "mysql",
        )
        assert re.search(r"(?is)LEFT JOIN LATERAL \(SELECT", out), out


class TestTuplesRoundSetNamesBoolLiterals:
    """wave 61: four mysql→tsql classes — row-tuple comparisons
    expand pairwise on T-SQL (no row constructors: 17x error 4145);
    boolean literals under AND/OR join wave 55's rewrite (`OR TRUE`
    shipped as bare `OR 1`, 13x); single-argument ROUND gains the
    mandatory scale 0 (6x error 189); and `SET NAMES` becomes a
    documented session-knob carrier (3x error 195)."""

    def test_row_tuple_eq_expands(self) -> None:
        out = _t2("select * from t1 where (f1, f2) = (2, null);", "mysql", "tsql")
        assert re.search(r"(?i)f1 = 2 AND f2 = NULL", out), out

    def test_row_tuple_neq_expands(self) -> None:
        out = _t2("select * from t1 where (f1, f2) <> (1, 2);", "mysql", "tsql")
        assert re.search(r"(?i)f1 <> 1 OR f2 <> 2", out), out

    def test_or_true_becomes_comparison(self) -> None:
        out = _t2("select a as f1 from t1 having f1 = 'a' or true;", "mysql", "tsql")
        assert re.search(r"(?i)OR 1 = 1", out), out

    def test_round_single_arg_gains_scale(self) -> None:
        out = _t2("select round(rand() * 10) from t1;", "mysql", "tsql")
        assert re.search(r"(?i)ROUND\(RAND\(\) \* 10, 0\)", out), out

    def test_set_names_carrier(self) -> None:
        r = Transpiler().transpile("set names latin1;", source="mysql", target="tsql")
        code = [
            ln
            for ln in r.sql.splitlines()
            if ln.strip() and not ln.strip().startswith("--")
        ]
        assert not code, r.sql


class TestStrToDateAndCompositeTypes:
    """wave 62: STR_TO_DATE of an impossible date becomes a CAST at
    emit time, AFTER wave 58's gate ran — the gate now also inspects
    the function form (6x mysql→tsql). And a routine declaring or
    returning a PG composite type (`CREATE TYPE x AS (…)` — itself an
    Unhandled-CREATE carrier) shipped `DECLARE @v compostype` garbage
    (6x pg→tsql): harvested composite names degrade the routine
    whole."""

    def test_str_to_date_invalid_degrades(self) -> None:
        r = Transpiler().transpile(
            "select str_to_date('2007-10-00', '%Y-%m-%d');",
            source="mysql",
            target="tsql",
        )
        code = [
            ln
            for ln in r.sql.splitlines()
            if ln.strip() and not ln.strip().startswith("--")
        ]
        assert not code, r.sql

    def test_str_to_date_valid_emits(self) -> None:
        out = _t2("select str_to_date('2007-10-01', '%Y-%m-%d');", "mysql", "tsql")
        assert re.search(r"(?i)CAST\('2007-10-01' AS DATE\)", out), out

    def test_composite_type_routine_degrades(self) -> None:
        src = (
            "create type compostype as (x int, y varchar);\n"
            "create function compos() returns compostype as $$\n"
            "declare v compostype;\n"
            "begin\n"
            "  v := (1, 'hello');\n"
            "  return v;\n"
            "end$$ language plpgsql;"
        )
        out = _t(src, "tsql")
        offenders = [
            ln
            for ln in out.splitlines()
            if "compostype" in ln.lower() and not ln.strip().startswith("--")
        ]
        assert not offenders, out


class TestSubqueryConditionsViewOrderCharZero:
    """wave 63: four mysql→tsql classes — a row tuple compared to a
    SUBQUERY has no pairwise expansion (degrade whole, 16x); a bare
    scalar subquery as a WHERE/HAVING condition is MySQL truthiness
    (→ `(sq) <> 0`, 12x); a view's ORDER BY without TOP is illegal on
    T-SQL and advisory on MySQL (strip + warn, 3x); CHAR(0)/
    VARCHAR(0) is legal on MySQL only (→ length 1, 5x error 1001)."""

    def test_tuple_vs_subquery_degrades(self) -> None:
        r = Transpiler().transpile(
            "select * from t1 where (f3, f4) = (select f3, f4 from t2);",
            source="mysql",
            target="tsql",
        )
        code = [
            ln
            for ln in r.sql.splitlines()
            if ln.strip() and not ln.strip().startswith("--")
        ]
        assert not code, r.sql

    def test_bare_subquery_condition_compares(self) -> None:
        out = _t2(
            "select 1 from t1 group by a having (select max(b) from t2);",
            "mysql",
            "tsql",
        )
        assert re.search(r"(?is)HAVING \(SELECT.*\) <> 0", out), out

    def test_view_order_by_strips(self) -> None:
        out = _t2("create view tv as select a from t1 order by a;", "mysql", "tsql")
        assert "ORDER BY" not in out.upper(), out

    def test_char_zero_becomes_one(self) -> None:
        out = _t2("create table t (c char(0));", "mysql", "tsql")
        assert re.search(r"(?i)c CHAR\(1\)", out), out


class TestUserVarsInRoutines:
    """wave 64: wave 59 gated @user variables on the DML pipeline —
    but routines travel the PROCEDURAL pipeline, which shipped
    `@cnt := := @cnt + 1` garbage to Oracle (52x mysql→oracle:
    anonymous CALL blocks, functions, triggers). Same alternate-route
    hole as wave 38; the procedural transformer now degrades the
    whole routine."""

    def test_call_with_user_var_degrades(self) -> None:
        r = Transpiler().transpile(
            "call zap(7, @zap);", source="mysql", target="oracle"
        )
        code = [
            ln
            for ln in r.sql.splitlines()
            if ln.strip() and not ln.strip().startswith("--")
        ]
        assert not any("@" in ln for ln in code), r.sql

    def test_function_with_user_var_degrades(self) -> None:
        src = (
            "DELIMITER //\n"
            "create function f1() returns int\n"
            "begin\n"
            "  set @cnt = @cnt + 1;\n"
            "  return 1;\n"
            "end//\n"
            "DELIMITER ;\n"
        )
        out = _t2(src, "mysql", "oracle")
        offenders = [
            ln
            for ln in out.splitlines()
            if "@" in ln and not ln.strip().startswith("--")
        ]
        assert not offenders, out

    def test_trigger_with_user_var_degrades(self) -> None:
        src = (
            "DELIMITER //\n"
            "create trigger trg before insert on t1 for each row\n"
            "begin\n"
            "  set @a = 1;\n"
            "end//\n"
            "DELIMITER ;\n"
        )
        out = _t2(src, "mysql", "oracle")
        offenders = [
            ln
            for ln in out.splitlines()
            if "@" in ln and not ln.strip().startswith("--")
        ]
        assert not offenders, out

    def test_routine_without_user_var_still_converts(self) -> None:
        src = (
            "DELIMITER //\n"
            "create function f2() returns int\n"
            "begin\n"
            "  return 2;\n"
            "end//\n"
            "DELIMITER ;\n"
        )
        out = _t2(src, "mysql", "oracle")
        assert re.search(r"(?i)CREATE OR REPLACE FUNCTION f2", out), out


class TestUnsignedParamsOracleTypes:
    """wave 65: MySQL's `INT UNSIGNED` in routine parameter/return
    types broke the procedural parser — the whole body was swallowed
    as parameter garbage (15x mysql→pg). UNSIGNED/SIGNED/ZEROFILL now
    parse as type attributes; MySQL integer names map to Oracle
    (TINYINT→NUMBER(3) etc.) in RETURN/DECLARE; and the scalar-
    subquery ORDER BY strip (wave 55, tsql) extends to Oracle (7x
    ORA-00907)."""

    _SRC = (
        "DELIMITER //\n"
        "create function fac(n int unsigned) returns bigint unsigned\n"
        "begin\n"
        "  declare f bigint unsigned default 1;\n"
        "  while n > 1 do\n"
        "    set f = f * n;\n"
        "    set n = n - 1;\n"
        "  end while;\n"
        "  return f;\n"
        "end//\n"
        "DELIMITER ;\n"
    )

    def test_unsigned_params_parse_pg(self) -> None:
        out = _t2(self._SRC, "mysql", "postgresql")
        assert re.search(r"(?is)CREATE OR REPLACE FUNCTION fac\s*\(\s*n", out), out
        assert "unsigned )" not in out.lower(), out
        assert re.search(r"(?is)WHILE.*LOOP", out), out

    def test_tinyint_return_maps_oracle(self) -> None:
        src = (
            "DELIMITER //\n"
            "create function g1() returns tinyint\n"
            "begin\n"
            "  return 0;\n"
            "end//\n"
            "DELIMITER ;\n"
        )
        out = _t2(src, "mysql", "oracle")
        assert "TINYINT" not in out.upper(), out
        assert re.search(r"(?i)RETURN NUMBER", out), out

    def test_scalar_subquery_order_strips_oracle(self) -> None:
        out = _t2(
            "select (select 1 as foo order by foo) as x from t1;",
            "mysql",
            "oracle",
        )
        assert "ORDER BY" not in out.upper(), out


class TestCharBinaryAndDegradedCallRegistry:
    """wave 66: MySQL's `CHAR BINARY` collation attribute shreds the
    parameter parser like UNSIGNED did (12x mysql→pg); and a CALL to
    a routine whose CREATE degraded earlier in the same script
    shipped as `BEGIN a(3); END;` — PLS-00221 at compile because the
    procedure never got created (18x mysql→oracle). Degraded routine
    names now register per run; later CALLs to them degrade too."""

    def test_char_binary_param_parses(self) -> None:
        src = (
            "DELIMITER //\n"
            "create function bug9048(f1 char binary) returns char\n"
            "begin\n"
            "  set f1 = concat('hello', f1);\n"
            "  return f1;\n"
            "end//\n"
            "DELIMITER ;\n"
        )
        out = _t2(src, "mysql", "postgresql")
        assert re.search(r"(?is)CREATE OR REPLACE FUNCTION bug9048\s*\(", out), out
        assert "binary )" not in out.lower(), out

    def test_call_to_degraded_routine_degrades(self) -> None:
        src = (
            "DELIMITER //\n"
            "create procedure p9(x int)\n"
            "begin\n"
            "  set @acc = @acc + x;\n"
            "end//\n"
            "DELIMITER ;\n"
            "call p9(3);\n"
        )
        out = _t2(src, "mysql", "oracle")
        code = [
            ln
            for ln in out.splitlines()
            if ln.strip() and not ln.strip().startswith("--")
        ]
        assert not any("p9" in ln.lower() for ln in code), out

    def test_call_to_converted_routine_survives(self) -> None:
        src = (
            "DELIMITER //\n"
            "create procedure p10(x int)\n"
            "begin\n"
            "  insert into t1 values (x);\n"
            "end//\n"
            "DELIMITER ;\n"
            "call p10(3);\n"
        )
        out = _t2(src, "mysql", "oracle")
        assert re.search(r"(?is)BEGIN\s+p10\(3\);\s+END;", out), out


class TestRepeatUntilLoop:
    """wave 67: MySQL's `REPEAT … UNTIL cond END REPEAT` shredded into
    garbage statements (`repeat AS set;`). It parses now as a
    post-test loop — LoopStatement with a trailing EXIT WHEN — which
    every target spells natively (LOOP…EXIT WHEN on PG/Oracle,
    WHILE/BREAK on T-SQL)."""

    _SRC = (
        "DELIMITER //\n"
        "create procedure rp()\n"
        "begin\n"
        "  declare v int default 0;\n"
        "  repeat\n"
        "    set v = v + 1;\n"
        "  until v >= 3 end repeat;\n"
        "end//\n"
        "DELIMITER ;\n"
    )

    def test_repeat_pg(self) -> None:
        out = _t2(self._SRC, "mysql", "postgresql")
        assert re.search(
            r"(?is)LOOP.*v := v \+ 1.*EXIT WHEN v >= 3.*END LOOP", out
        ), out

    def test_repeat_oracle(self) -> None:
        out = _t2(self._SRC, "mysql", "oracle")
        assert re.search(r"(?is)LOOP.*EXIT WHEN v >= 3.*END LOOP", out), out
        assert "repeat AS" not in out, out
