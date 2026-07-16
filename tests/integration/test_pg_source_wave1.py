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
        # wave 149 STRENGTHENED: TEXT now maps to the target's modern
        # large-string type instead of passing through raw.
        assert re.search(r"(?i)uq_msg (text|NVARCHAR\(MAX\)|CLOB)", out), out
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


class TestRaiseConditionName:
    """wave 68: PG's `RAISE condition_name [USING k = v]` fell to the
    raw-expression path — T-SQL got `DECLARE @msg NVARCHAR(2048) =
    division_by_zero using detail = '…'` (6x pg→tsql). The condition
    name folds into a literal message (USING items appended as text,
    like the format path already does)."""

    def test_condition_name_tsql(self) -> None:
        src = (
            "create function rt() returns int as $$\n"
            "begin\n"
            "  raise division_by_zero using detail = 'some info';\n"
            "  return 0;\n"
            "end$$ language plpgsql;"
        )
        out = _t(src, "tsql")
        offenders = [
            ln
            for ln in out.splitlines()
            if "using detail" in ln.lower() and not ln.strip().startswith("--")
        ]
        assert not offenders, out
        assert re.search(r"(?i)division_by_zero", out), out

    def test_condition_name_oracle(self) -> None:
        src = (
            "create function rt2() returns int as $$\n"
            "begin\n"
            "  raise unique_violation;\n"
            "  return 0;\n"
            "end$$ language plpgsql;"
        )
        out = _t(src, "oracle")
        assert re.search(r"(?i)unique_violation", out), out
        assert "using" not in out.lower(), out


class TestCteOrderByStrip:
    """wave 69: a CTE body's ORDER BY without LIMIT is illegal on
    T-SQL (error 1033, ~7x pg→tsql) and has no observable effect
    anyway — strip it like the view/scalar-subquery cases."""

    def test_cte_order_by_strips_tsql(self) -> None:
        out = _t(
            "with q as (select max(f1) as m from t1 group by f1 order by f1) "
            "select m from q;",
            "tsql",
        )
        assert "ORDER BY" not in out.upper(), out

    def test_cte_order_by_with_limit_survives(self) -> None:
        out = _t(
            "with q as (select f1 from t1 order by f1 limit 3) " "select f1 from q;",
            "tsql",
        )
        assert re.search(r"(?is)TOP.*ORDER BY|ORDER BY.*OFFSET", out), out


class TestMysqlDeclareHandler:
    """wave 70: MySQL's `DECLARE {EXIT|CONTINUE} HANDLER FOR …` never
    parsed (wave 52 turned the whole routine into a carrier). An EXIT
    handler for SQLEXCEPTION/SQLWARNING is exactly the enclosing
    block's exception section — fold into TryCatchBlock (EXCEPTION
    WHEN OTHERS on PG/Oracle, TRY/CATCH on T-SQL). CONTINUE handlers
    and condition classes with no target equivalent keep the honest
    whole-routine degrade."""

    _EXIT_SRC = (
        "DELIMITER //\n"
        "create procedure hp()\n"
        "begin\n"
        "  declare exit handler for sqlexception select 'bad' as e;\n"
        "  insert into t1 values (1);\n"
        "  select 'ok' as r;\n"
        "end//\n"
        "DELIMITER ;\n"
    )

    def test_exit_handler_pg(self) -> None:
        out = _t2(self._EXIT_SRC, "mysql", "postgresql")
        assert re.search(r"(?is)EXCEPTION\s+WHEN OTHERS THEN", out), out
        assert "handler" not in out.lower(), out
        assert re.search(r"(?is)INSERT INTO t1", out), out

    def test_exit_handler_tsql(self) -> None:
        out = _t2(self._EXIT_SRC, "mysql", "tsql")
        assert re.search(r"(?is)BEGIN TRY.*INSERT INTO t1.*END TRY", out), out
        assert re.search(r"(?is)BEGIN CATCH.*END CATCH", out), out

    def test_continue_handler_degrades(self) -> None:
        src = (
            "DELIMITER //\n"
            "create procedure hc()\n"
            "begin\n"
            "  declare continue handler for sqlstate '23000' select 'dup';\n"
            "  insert into t1 values (1);\n"
            "end//\n"
            "DELIMITER ;\n"
        )
        out = _t2(src, "mysql", "postgresql")
        code = [
            ln
            for ln in out.splitlines()
            if ln.strip() and not ln.strip().startswith("--")
        ]
        assert not code, out


class TestRefcursorInTryCatch:
    """wave 71: the bare-SELECT → SYS_REFCURSOR rewrite (Oracle) did
    not recurse into TryCatchBlock bodies, so a result SELECT inside
    wave 70's folded exception section shipped as PL/SQL
    SELECT-without-INTO (PLS-00428, the +5 from the wave-70
    measure)."""

    def test_select_in_catch_becomes_refcursor(self) -> None:
        src = (
            "DELIMITER //\n"
            "create procedure hp2()\n"
            "begin\n"
            "  declare exit handler for sqlexception select 'bad' as e;\n"
            "  insert into t1 values (1);\n"
            "end//\n"
            "DELIMITER ;\n"
        )
        out = _t2(src, "mysql", "oracle")
        assert re.search(r"(?is)OPEN RESULT_CURSOR FOR SELECT 'bad'", out), out
        assert re.search(r"(?is)RESULT_CURSOR OUT SYS_REFCURSOR", out), out


class TestBareValueConditionsAndTupleIn:
    """wave 72: two more MySQL-truthiness shapes on T-SQL — a bare
    function call or column as a WHERE/HAVING condition needs the
    `<> 0` comparison (error 4145/195), and a row tuple in
    `IN (SELECT …)` has no T-SQL spelling (degrade whole, like wave
    63's tuple = subquery)."""

    def test_bare_function_condition(self) -> None:
        out = _t2("select * from t3 where dayname('1995-01-01');", "mysql", "tsql")
        assert re.search(r"(?is)WHERE .*DAYNAME.* <> 0", out), out

    def test_bare_column_condition(self) -> None:
        out = _t2("select a from t1 where b;", "mysql", "tsql")
        assert re.search(r"(?is)WHERE b <> 0", out), out

    def test_tuple_in_subquery_degrades(self) -> None:
        r = Transpiler().transpile(
            "select * from t1 where (f1, pk) in (select 7, 4 union select 9, 2);",
            source="mysql",
            target="tsql",
        )
        code = [
            ln
            for ln in r.sql.splitlines()
            if ln.strip() and not ln.strip().startswith("--")
        ]
        assert not code, r.sql


class TestRawStrToDateDegrades:
    """wave 73: STR_TO_DATE inside an unconverted expression blob
    (e.g. a BETWEEN that fell to RawSQL) ships raw off MySQL — error
    195 on T-SQL, unknown function elsewhere (6x). The invalid-date
    gate now also degrades statements whose RawSQL text calls
    STR_TO_DATE."""

    def test_str_to_date_in_between_degrades(self) -> None:
        r = Transpiler().transpile(
            "select str_to_date('1000-01-01', '%Y-%m-%d') "
            "between '0000-00-00' and null as x;",
            source="mysql",
            target="tsql",
        )
        code = [
            ln
            for ln in r.sql.splitlines()
            if ln.strip() and not ln.strip().startswith("--")
        ]
        assert not code, r.sql


class TestRefcursorCallSites:
    """wave 74: the SYS_REFCURSOR rewrite adds OUT parameters to the
    procedure's signature, but same-script CALLs kept the old arity —
    PLS-00306 at compile (19x mysql→oracle). Converted signatures now
    register per run; later CALLs gain local cursor variables in a
    nested DECLARE block."""

    def test_call_gains_cursor_arg(self) -> None:
        src = (
            "DELIMITER //\n"
            "create procedure sel1()\n"
            "begin\n"
            "  select * from t1;\n"
            "end//\n"
            "DELIMITER ;\n"
            "call sel1();\n"
        )
        out = _t2(src, "mysql", "oracle")
        assert re.search(r"(?is)DECLARE\s+uq_rc1 SYS_REFCURSOR", out), out
        assert re.search(r"(?is)sel1\(uq_rc1\);", out), out

    def test_call_with_args_appends_cursor(self) -> None:
        src = (
            "DELIMITER //\n"
            "create procedure sel2(x int)\n"
            "begin\n"
            "  select x + 1;\n"
            "end//\n"
            "DELIMITER ;\n"
            "call sel2(7);\n"
        )
        out = _t2(src, "mysql", "oracle")
        assert re.search(r"(?is)sel2\(7, uq_rc1\);", out), out


class TestMysqlDoubleQuotedStrings:
    """wave 75: MySQL double-quoted STRING literals inside procedural
    raw text (`CONCAT(arg, "")`, `SET x = "it's"`) survive to targets
    where double quotes delimit IDENTIFIERS — pg error 42601
    zero-length identifier (11x mysql→pg). Off MySQL they now rewrite
    to single-quoted literals with inner quotes doubled."""

    def test_empty_double_quote_pg(self) -> None:
        src = (
            "DELIMITER //\n"
            "create function dq1(arg text) returns text\n"
            "begin\n"
            '  return concat(arg, "");\n'
            "end//\n"
            "DELIMITER ;\n"
        )
        out = _t2(src, "mysql", "postgresql")
        assert '""' not in out, out
        assert re.search(r"(?is)concat\s*\(\s*arg\s*,\s*''\s*\)", out), out

    def test_double_quote_with_apostrophe(self) -> None:
        src = (
            "DELIMITER //\n"
            "create procedure dq2()\n"
            "begin\n"
            "  declare x text;\n"
            '  set x = "it\'s";\n'
            "end//\n"
            "DELIMITER ;\n"
        )
        out = _t2(src, "mysql", "postgresql")
        assert re.search(r"it''s", out), out
        assert '"' not in out.split("$$")[1], out


class TestLabeledLoops:
    """wave 76: MySQL labeled loops (`foo: loop … end loop foo`) and
    `LEAVE label` mangled into `foo AS %(loop)s;` garbage (4x
    mysql→pg). Labels now parse; PG/Oracle emit `<<label>>` blocks
    with `EXIT label;`."""

    _SRC = (
        "DELIMITER //\n"
        "create procedure lp()\n"
        "begin\n"
        "  declare i int default 0;\n"
        "  foo: loop\n"
        "    set i = i + 1;\n"
        "    if i > 3 then\n"
        "      leave foo;\n"
        "    end if;\n"
        "  end loop foo;\n"
        "end//\n"
        "DELIMITER ;\n"
    )

    def test_labeled_loop_pg(self) -> None:
        out = _t2(self._SRC, "mysql", "postgresql")
        assert "<<foo>>" in out, out
        assert re.search(r"(?i)EXIT foo;", out), out
        assert "%(loop)s" not in out, out

    def test_labeled_loop_oracle(self) -> None:
        out = _t2(self._SRC, "mysql", "oracle")
        assert "<<foo>>" in out, out
        assert re.search(r"(?i)EXIT foo;", out), out


class TestPrintSubqueryHoist:
    """wave 77: T-SQL forbids subqueries in PRINT arguments (error
    1046 — 56x pg→tsql: inlined trigger bodies printing transition
    aggregates). The expression hoists into a DECLAREd temp (where
    subquery initializers ARE legal) and PRINT takes the variable."""

    def test_print_subquery_hoists(self) -> None:
        src = (
            "create function tf3() returns trigger as $$\n"
            "begin\n"
            "  raise notice 'count = %', (select count(*) from newtab);\n"
            "  return null;\nend$$ language plpgsql;\n"
            "create trigger t3 after insert on t1 "
            "referencing new table as newtab "
            "for each statement execute function tf3();"
        )
        out = _t(src, "tsql")
        m = re.search(
            r"(?is)DECLARE (@uq_prt\d+) NVARCHAR\(MAX\) = .*SELECT COUNT.*"
            r"PRINT [^;]*\1;",
            out,
        )
        assert m, out


class TestFromNeverQualifies:
    """wave 78: `FROM (` before a derived table got dbo.-qualified
    (`dbo.FROM`) by the user-function pass — FROM/JOIN were missing
    from TSQL_NEVER_QUALIFY (2x pg→tsql inside trigger CTEs)."""

    def test_from_derived_table_in_trigger(self) -> None:
        src = (
            "create function rif() returns trigger as $$\n"
            "begin\n"
            "  select sum(delta) into strict cnt from\n"
            "    (select 1 as delta from newtab) x;\n"
            "  return null;\nend$$ language plpgsql;\n"
            "create trigger rt after insert on t1 "
            "referencing new table as newtab "
            "for each statement execute function rif();"
        )
        out = _t(src, "tsql")
        assert "dbo.FROM" not in out, out
        assert "dbo.from" not in out, out


class TestPgCastsInRawTextAndNotInCast:
    """wave 79: PG `expr::type` casts inside procedural raw text
    shipped as `@p1 : : text` on T-SQL (65x, the biggest remaining
    pg→tsql class); simple operands now rewrite to CAST(x AS type).
    And `CAST(NOT b AS INT)` is invalid on T-SQL (NOT is not a value
    there; 12x) — the operand wraps tri-state."""

    def test_double_colon_cast_in_body(self) -> None:
        src = (
            "create function cf1(p1 text) returns text as $$\n"
            "begin\n"
            "  return p1::text;\n"
            "end$$ language plpgsql;"
        )
        out = _t(src, "tsql")
        assert "::" not in out, out
        assert ": :" not in out, out
        assert re.search(r"(?i)CAST\(\s*@p1 AS text\s*\)", out), out

    def test_not_inside_cast_tsql(self) -> None:
        out = _t("select min(cast(not b2 as int)) from bt;", "tsql")
        assert not re.search(r"(?i)CAST\(NOT b2", out), out
        assert re.search(
            r"(?i)CASE WHEN b2 = 0 THEN 1 WHEN b2 <> 0 THEN 0 END", out
        ), out


class TestPgDomainTypes:
    """wave 80: PG DOMAIN types (`CREATE DOMAIN foodomain AS text`)
    survived into signatures, declares and CASTs off PG — unknown
    type names everywhere else (the residue of the 65x class).
    Domains harvest per run and resolve to their base type."""

    def test_domain_in_signature_and_cast(self) -> None:
        src = (
            "create domain foodomain as text;\n"
            "create function vf(p1 text) returns foodomain as $$\n"
            "begin\n"
            "  return p1::foodomain;\n"
            "end$$ language plpgsql;"
        )
        out = _t(src, "tsql")
        body = out.split("CREATE FUNCTION", 1)[-1]
        offenders = [
            ln
            for ln in body.splitlines()
            if "foodomain" in ln.lower() and not ln.strip().startswith("--")
        ]
        assert not offenders, out
        # wave 149: the domain's base TEXT maps to NVARCHAR(MAX) on
        # T-SQL (raw TEXT is deprecated there) — stronger than the old
        # passthrough expectation.
        assert re.search(r"(?i)RETURNS (text|NVARCHAR\(MAX\))", out), out


class TestLanguageSqlTailStrip:
    """wave 81: a LANGUAGE-sql single-expression body captured past
    its closing $$ — `language sql` (and neighbors like STRICT/
    IMMUTABLE) leaked into the RETURN expression (part of the 65x
    chain). The tail attributes now strip from the captured
    statement."""

    def test_language_tail_stripped(self) -> None:
        src = (
            "create function ie(p1 text, p2 text) returns int as $$\n"
            "  select case p2::text when p1::text then 1 else 0 end\n"
            "$$ language sql;"
        )
        out = _t(src, "tsql")
        assert "language sql" not in out.lower(), out
        assert re.search(r"(?is)RETURN \(select case", out), out

    def test_strict_immutable_tail_stripped(self) -> None:
        src = (
            "create function ie2(a int) returns int as $$\n"
            "  select a + 1\n"
            "$$ language sql immutable strict;"
        )
        out = _t(src, "tsql")
        assert "immutable" not in out.lower(), out
        assert "language" not in out.lower().replace("language plpgsql", ""), out


class TestStringAggOrderBy:
    """wave 82: PG's in-call aggregate ORDER BY —
    `STRING_AGG(x, ',' ORDER BY a)` — is `STRING_AGG(x, ',') WITHIN
    GROUP (ORDER BY a)` on T-SQL (51x, unblocked by wave 77's PRINT
    hoist). A paren-aware scan rewrites it in raw trigger text."""

    def test_string_agg_order_rewrites(self) -> None:
        src = (
            "create function saf() returns trigger as $$\n"
            "begin\n"
            "  raise notice 'rows = %', "
            "(select string_agg(cast(a as text), ', ' order by a) from newtab);\n"
            "  return null;\nend$$ language plpgsql;\n"
            "create trigger sat after insert on t1 "
            "referencing new table as newtab "
            "for each statement execute function saf();"
        )
        out = _t(src, "tsql")
        assert re.search(r"(?is)STRING_AGG\(.*\) WITHIN GROUP \(ORDER BY a\)", out), out
        assert not re.search(r"(?is)',\s*'\s+order by", out), out


class TestBoolAggregateNotArg:
    """wave 83: `BOOL_AND(NOT b2)` lowered to `MIN(CAST(NOT b2 AS
    INT))` on T-SQL — NOT is not a value expression there (12x). A
    predicate argument to the boolean aggregates now wraps tri-state
    before the CAST."""

    def test_bool_and_not_tsql(self) -> None:
        out = _t("select bool_and(not b2) from bt;", "tsql")
        assert not re.search(r"(?i)CAST\(NOT b2", out), out
        assert re.search(
            r"(?i)MIN\(CAST\(CASE WHEN b2 = 0 THEN 1 "
            r"WHEN b2 <> 0 THEN 0 END AS INT\)\)",
            out,
        ), out

    def test_bool_or_comparison_tsql(self) -> None:
        out = _t("select bool_or(a > 3) from bt;", "tsql")
        assert re.search(r"(?i)MAX\(CAST\(CASE WHEN a > 3 THEN 1", out), out


class TestInsertCteHoist:
    """wave 83b: `INSERT INTO t (cols) WITH cte AS (…) SELECT …` puts
    the CTE after the INSERT clause — T-SQL requires WITH FIRST (14x
    error 156). The CTE hoists before the INSERT on T-SQL."""

    def test_insert_with_cte_tsql(self) -> None:
        out = _t(
            "insert into t3 (f3) with result as (select f1 from t1) "
            "select f1 from result;",
            "tsql",
        )
        assert re.search(
            r"(?is)^\s*WITH result AS \(.*\)\s*INSERT INTO t3 \(f3\)", out
        ), out


class TestCaseWhenBareBoolean:
    """wave 84: a searched CASE's WHEN emitted its condition as an
    EXPRESSION — a bare boolean column (`CASE WHEN b1 THEN …`)
    shipped raw to T-SQL (error 4145). Searched WHENs (no operand)
    now emit in condition position, picking up the truthiness
    wraps."""

    def test_bare_column_when_tsql(self) -> None:
        out = _t("select max(case when b1 then 1 else 0 end) from bt;", "tsql")
        assert re.search(r"(?is)WHEN b1 <> 0 THEN 1", out), out

    def test_simple_case_operand_untouched(self) -> None:
        out = _t("select case a when 1 then 'x' else 'y' end from t;", "tsql")
        assert re.search(r"(?is)CASE a\s+WHEN 1 THEN 'x'", out), out


class TestNestedChainMidOrderStrip:
    """wave 85: a parenthesized inner set chain carrying its own
    ORDER BY without LIMIT — `(a INTERSECT b ORDER BY 1) UNION ALL c`
    — kept that ORDER BY mid-chain on T-SQL (error 156, 3x). Wave
    48's shielding skipped chain arms; non-final arms now strip the
    tail order (no observable effect without LIMIT)."""

    def test_mid_chain_order_strips(self) -> None:
        out = _t(
            "(select q1 from t1 intersect select q2 from t1 order by 1) "
            "union all select q2 from t1;",
            "tsql",
        )
        m = re.search(r"(?is)ORDER BY.*UNION ALL", out)
        assert not m, out

    def test_nested_chain_first_arm_not_clobbered(self) -> None:
        # The inner chain's links must survive the outer op attaching.
        # Wave 130 STRENGTHENED this: the flat form this test used to
        # assert re-associated the row set (INTERSECT binds tighter than
        # UNION, so flat (A UNION B) INTERSECT C read as A UNION
        # (B INTERSECT C)); the parenthesized chain arm is now shielded
        # as a derived table, preserving both links AND association.
        out = _t(
            "(SELECT 1,2,3 UNION SELECT 4,5,6 ORDER BY 1,2) " "INTERSECT SELECT 4,5,6;",
            "tsql",
        )
        assert re.search(
            r"(?is)FROM \(SELECT 1, 2, 3\s+UNION\s+SELECT 4, 5, 6\)", out
        ), out
        assert re.search(r"(?is)uq_setarm\s+INTERSECT\s+SELECT 4, 5, 6", out), out


class TestPgArrayTypedRoutines:
    """wave 86: PG array types in signatures (`x real[]`) shredded
    the header parser — `[] LANGUAGE; plpgsql STRICT;` garbage
    declares (48x pg→oracle). `type[]` now parses as an array-marked
    DataType, and array-typed params/returns/declares degrade the
    routine whole off PG (no target equivalent)."""

    _SRC = (
        "create function eatarray(x real[]) returns real[] as $$\n"
        "begin\n"
        "  x[1] := x[1] + 1;\n"
        "  return x;\n"
        "end$$ language plpgsql;"
    )

    def test_array_param_degrades_oracle(self) -> None:
        out = _t(self._SRC, "oracle")
        code = [
            ln
            for ln in out.splitlines()
            if ln.strip() and not ln.strip().startswith("--")
        ]
        assert not code, out
        assert "real[]" in out, out

    def test_array_param_degrades_tsql(self) -> None:
        out = _t(self._SRC, "tsql")
        code = [
            ln
            for ln in out.splitlines()
            if ln.strip() and not ln.strip().startswith("--")
        ]
        assert not code, out


class TestArrayConstructorInBody:
    """wave 87: PG ARRAY constructors inside routine BODIES
    (`x := array[$1,$2]`) shipped raw off PG — the wave-86 degrade
    only checked declared types (part of the 39x pg→oracle residue).
    A body whose raw text builds arrays now degrades the routine
    whole."""

    def test_array_constructor_body_degrades(self) -> None:
        src = (
            "create function make_ad(int, int) returns int as $$\n"
            "declare x int;\n"
            "begin\n"
            "  x := array[$1,$2];\n"
            "  return x;\n"
            "end$$ language plpgsql;"
        )
        out = _t(src, "oracle")
        code = [
            ln
            for ln in out.splitlines()
            if ln.strip() and not ln.strip().startswith("--")
        ]
        assert not code, out


class TestReturningOracle:
    """wave 88: top-level DML with RETURNING shipped the clause raw
    to Oracle (ORA-00936, 7x) — Oracle's RETURNING…INTO exists only
    inside PL/SQL with target variables. Like the MySQL branch: the
    DML keeps its effect, the clause strips with a documented note."""

    def test_update_returning_strips_oracle(self) -> None:
        out = _t("update cv set n = 'j' where c = 't' returning *;", "oracle")
        assert "RETURNING" not in [
            ln for ln in out.splitlines() if not ln.strip().startswith("--")
        ], out
        code = [
            ln
            for ln in out.splitlines()
            if ln.strip() and not ln.strip().startswith("--")
        ]
        assert any("UPDATE cv" in ln for ln in code), out
        assert not any("RETURNING" in ln.upper() for ln in code), out
        assert "UNIQUE:" in out, out


class TestOnConflictMysqlAndEStrings:
    """wave 89: the RETURNING+ON CONFLICT carrier (wave 54) sat AFTER
    the MySQL RETURNING branch, so MySQL stripped RETURNING and
    shipped ON CONFLICT raw (4x); the check moves first. And PG
    E-strings in procedural raw text emitted as `E '...'` — invalid
    off PG; MySQL's backslash escapes are compatible, so the prefix
    drops there (3x)."""

    def test_returning_on_conflict_mysql_degrades(self) -> None:
        r = Transpiler().transpile(
            "insert into t (a,b) values (1,'x') "
            "on conflict (a) do update set b = 'y' returning *;",
            source="postgresql",
            target="mysql",
        )
        code = [
            ln
            for ln in r.sql.splitlines()
            if ln.strip() and not ln.strip().startswith("--")
        ]
        assert not any("ON CONFLICT" in ln.upper() for ln in code), r.sql

    def test_estring_prefix_drops_mysql(self) -> None:
        src = (
            "create function st() returns text as $$\n"
            "begin\n"
            "  return E'foo\\\\bar';\n"
            "end$$ language plpgsql;"
        )
        out = _t(src, "mysql")
        assert not re.search(r"\bE\s+'", out), out
        assert not re.search(r"\bE'", out), out


class TestIgnoreInvisibleOffsetOrder:
    """wave 90: three mysql→tsql classes — `DELETE IGNORE` is
    unparseable by sqlglot (the whole batch carriered and glued,
    4x): the IGNORE keyword pre-normalizes away on the retry path;
    MySQL's INVISIBLE column attribute leaked into T-SQL generated
    columns (3x); and OFFSET…FETCH without ORDER BY is illegal on
    T-SQL (6x) — gains `ORDER BY (SELECT NULL)`."""

    def test_delete_ignore_parses(self) -> None:
        out = _t2("delete ignore from t1 where i = 1;", "mysql", "tsql")
        assert re.search(r"(?is)DELETE FROM t1", out), out

    def test_invisible_column_strips(self) -> None:
        out = _t2(
            "create table t1 (f1 int, b int as (1) invisible);",
            "mysql",
            "tsql",
        )
        assert "INVISIBLE" not in out.upper(), out

    def test_offset_without_order_gains_null_order(self) -> None:
        out = _t2("select count(*) from t1 limit 3 offset 2;", "mysql", "tsql")
        assert re.search(r"(?is)ORDER BY \(SELECT NULL\)\s+OFFSET 2 ROWS", out), out


class TestCharsetIntroducersAndRowOracle:
    """wave 91: MySQL charset introducers and COLLATE survive to
    Oracle (`SELECT _latin1 'test' COLLATE latin1_bin`, ORA-00911,
    3x) — both are engine-local and strip off MySQL. And ROW-tuple
    comparisons expand pairwise on Oracle too (wave 61 was
    tsql-only; 3x)."""

    def test_introducer_and_collate_strip(self) -> None:
        out = _t2("select _latin1'test' collate latin1_bin;", "mysql", "oracle")
        assert "_latin1" not in out.lower(), out
        assert "collate" not in out.lower(), out
        assert "'test'" in out, out

    def test_row_tuple_expands_oracle(self) -> None:
        out = _t2("select row(b,a) <> row(a,a) as x from t1;", "mysql", "oracle")
        assert "row(" not in out.lower(), out
        assert re.search(r"(?i)b <> a OR a <> a", out), out


class TestParenCastDegrades:
    """wave 92: PG casts of PARENTHESIZED expressions
    (`row(a,b)::int8_tbl` — composite row types) survive the simple
    ANSI-cast rewrite and ship as `) : : type` (6x pg→tsql). A body
    still carrying such a cast degrades the routine whole."""

    def test_row_cast_composite_degrades(self) -> None:
        src = (
            "create function mki8(a bigint, b bigint) returns int8_tbl as $$\n"
            "  select row(a, b)::int8_tbl\n"
            "$$ language sql;"
        )
        out = _t(src, "tsql")
        code = [
            ln
            for ln in out.splitlines()
            if ln.strip() and not ln.strip().startswith("--")
        ]
        assert not code, out


class TestRaiseSqlstateLiteral:
    """wave 93: PG's `RAISE sqlstate '1234F'` fell to the
    raw-expression path where the T-SQL SQLSTATE→ERROR_STATE()
    substitution mangled it into `CAST(ERROR_STATE() …) '1234F'`
    (3x). Like the condition-name form (wave 68), it folds into a
    literal message."""

    def test_raise_sqlstate_tsql(self) -> None:
        src = (
            "create function rs() returns int as $$\n"
            "begin\n"
            "  raise sqlstate '1234F';\n"
            "  return 0;\n"
            "end$$ language plpgsql;"
        )
        out = _t(src, "tsql")
        assert "ERROR_STATE()" not in out.split("RAISERROR")[0], out
        assert re.search(r"(?i)'SQLSTATE 1234F'", out), out


class TestTupleInValuesList:
    """wave 94: `(a, b) IN (VALUES (1,1), (20,0))` has no T-SQL
    spelling (row constructors; 4145) — literal rows expand to the
    disjunction of conjunctions `(a = 1 AND b = 1) OR (a = 20 AND
    b = 0)`."""

    def test_tuple_in_values_expands(self) -> None:
        out = _t(
            "select * from onek where (u1, ten) in (values (1,1),(20,0));",
            "tsql",
        )
        assert "VALUES" not in out.upper().split("WHERE")[-1], out
        assert re.search(
            r"(?i)\(u1 = 1 AND ten = 1\) OR \(u1 = 20 AND ten = 0\)", out
        ), out


class TestMysqlFunctionDefaultParens:
    """wave 95: MySQL requires parentheses around expression DEFAULTs
    (`DEFAULT (UUID())`, error 1064 bare) — the emitted rewrite
    existed on one path but the column emitter shipped `DEFAULT
    UUID()` (spotted in the closed nightly-mutation item)."""

    def test_uuid_default_parenthesized(self) -> None:
        out = _t(
            "create table t (id uuid default gen_random_uuid(), a int);",
            "mysql",
        )
        assert re.search(r"(?i)DEFAULT \(UUID\(\)\)", out), out

    def test_literal_default_unchanged(self) -> None:
        out = _t("create table t (a int default 3);", "mysql")
        assert re.search(r"(?i)DEFAULT 3", out), out


class TestLastIdentityCaptureNode:
    """M3-prereq increment 3 (wave 96): the Oracle last-identity
    capture consumed a MARKER STRING left in the assignment text; it
    now consumes a dedicated LastIdentityCapture node. Paired
    behavior is unchanged (INSERT … RETURNING id INTO v); the
    UNPAIRED fallback improves from the invalid `v := /* … */;` to a
    valid NULL assignment with the documented note."""

    _DDL = "CREATE TABLE t1 (\n  id INT IDENTITY(1,1),\n  a INT\n);\nGO\n"

    def test_paired_returning_into(self) -> None:
        src = self._DDL + (
            "CREATE PROCEDURE p AS\nBEGIN\n"
            "  INSERT INTO t1 (a) VALUES (1);\n"
            "  SET @id = SCOPE_IDENTITY();\nEND"
        )
        out = _t2(src, "tsql", "oracle")
        assert re.search(r"(?i)RETURNING id INTO V_ID;", out), out
        assert "SCOPE_IDENTITY" not in out.upper(), out

    def test_unpaired_fallback_is_valid(self) -> None:
        src = "CREATE PROCEDURE p2 AS\nBEGIN\n" "  SET @id = SCOPE_IDENTITY();\nEND"
        out = _t2(src, "tsql", "oracle")
        assert re.search(
            r"(?i)V_ID := NULL;\s*/\* last identity: use <sequence>\.CURRVAL \*/",
            out,
        ), out
        assert not re.search(r"(?i)V_ID := /\*", out), out


class TestAssignmentViaSelectNodeAware:
    """M3-prereq increment 4a (wave 97): Oracle's assignment-via-
    SELECT-INTO decision matched the EMITTED TEXT with a spelling
    regex; it now inspects the value NODE first (SubqueryExpression /
    CastExpression anywhere in the tree), keeping the regex only for
    raw text fragments. Behavior pinned: subquery assignments become
    SELECT … INTO … FROM DUAL."""

    def test_subquery_assignment_select_into(self) -> None:
        src = (
            "CREATE PROCEDURE p AS\nBEGIN\n"
            "  SET @c = (SELECT COUNT(*) FROM t1);\nEND"
        )
        out = _t2(src, "tsql", "oracle")
        assert re.search(
            r"(?is)SELECT \(\s*SELECT COUNT\s*\(\s*\*\s*\)\s*FROM t1\s*\)"
            r" INTO V_C FROM DUAL;",
            out,
        ), out

    def test_plain_assignment_stays(self) -> None:
        src = "CREATE PROCEDURE p2 AS\nBEGIN\n  SET @c = 1 + 2;\nEND"
        out = _t2(src, "tsql", "oracle")
        assert re.search(r"(?i)V_C := 1 \+ 2;", out), out


class TestIrNestedDateaddOverDatediff:
    """M3b family migration, dates step 1 (wave 98): the IR's DATEADD
    emission adds an INTERVAL to the base even when the base is a
    DATEDIFF result — a NUMBER (Oracle: invalid; PG: wrong type). The
    text path's live-validated form is plain numeric addition; the IR
    now matches it."""

    def test_nested_numeric_add_oracle(self) -> None:
        out = _t2(
            "SELECT DATEADD(day, 1, DATEDIFF(day, x, y)) FROM t;",
            "tsql",
            "oracle",
        )
        assert "NUMTODSINTERVAL" not in out.upper(), out
        assert re.search(
            r"(?is)\(TRUNC\(CAST\(y AS DATE\)\) - TRUNC\(CAST\(x AS DATE\)\)\)"
            r" \+ 1",
            out,
        ), out

    def test_nested_numeric_add_pg(self) -> None:
        out = _t2(
            "SELECT DATEADD(day, 1, DATEDIFF(day, x, y)) FROM t;",
            "tsql",
            "postgresql",
        )
        assert "INTERVAL" not in out.upper(), out
        assert re.search(r"(?i)\+ 1", out), out


class TestMysqlProceduralFuncMaps:
    """M3b family migration, function renames (wave 99): the
    procedural text path had NO (mysql, postgresql)/(mysql, oracle)
    function maps — IFNULL shipped raw to PG (no such function
    there; found by the text-vs-IR differential)."""

    def test_ifnull_pg(self) -> None:
        src = (
            "DELIMITER //\n"
            "create procedure fp()\n"
            "begin\n"
            "  declare x int;\n"
            "  set x = ifnull(x, 0) + 1;\n"
            "end//\n"
            "DELIMITER ;\n"
        )
        out = _t2(src, "mysql", "postgresql")
        assert "ifnull" not in out.lower(), out
        assert re.search(r"(?i)COALESCE\s*\(\s*x\s*,\s*0\s*\)", out), out

    def test_ifnull_oracle(self) -> None:
        src = (
            "DELIMITER //\n"
            "create procedure fo()\n"
            "begin\n"
            "  declare x int;\n"
            "  set x = ifnull(x, 0) + 1;\n"
            "end//\n"
            "DELIMITER ;\n"
        )
        out = _t2(src, "mysql", "oracle")
        assert "ifnull" not in out.lower(), out
        assert re.search(r"(?i)NVL\s*\(\s*x\s*,\s*0\s*\)", out), out


class TestNationalStringConcat:
    """M3b family migration, concat step (wave 100): T-SQL N'…'
    literals parse as exp.National, which the string classifier did
    not recognize — `N'pre' + s` shipped raw `+` to Oracle (invalid
    on strings; found by the text-vs-IR differential)."""

    def test_national_concat_oracle(self) -> None:
        out = _t2("SELECT N'pre' + s AS r FROM t;", "tsql", "oracle")
        assert "+" not in out.split("FROM")[0], out
        assert re.search(r"(?i)'pre' \|\| s", out), out


class TestSystemGlobalsInDml:
    """M3b family migration, error-globals step (wave 101): the
    system globals (@@ROWCOUNT/@@ERROR, SQL%ROWCOUNT) were mapped
    only in the procedural text path — a top-level `SELECT
    @@ROWCOUNT` shipped raw off T-SQL (found by the text-vs-IR
    differential). The DML emit now shares the mapping."""

    def test_rowcount_mysql(self) -> None:
        out = _t2("SELECT @@ROWCOUNT AS r;", "tsql", "mysql")
        assert "@@" not in out, out
        assert re.search(r"(?i)ROW_COUNT\(\)", out), out

    def test_rowcount_pg_neutral(self) -> None:
        out = _t2("SELECT @@ROWCOUNT AS r;", "tsql", "postgresql")
        assert re.search(r"(?i)SELECT 0 /\* UNIQUE:", out), out

    def test_sql_rowcount_tsql(self) -> None:
        out = _t2("SELECT SQL%ROWCOUNT AS r FROM DUAL;", "oracle", "tsql")
        assert re.search(r"(?i)@@ROWCOUNT", out), out
        assert "SQL %" not in out, out


class TestFetchStatusTopLevel:
    """M3b family survey close (wave 102): @@FETCH_STATUS is
    cursor-contextual by nature (the procedural path maps it to
    FOUND / handler flags / cursor%FOUND using surrounding state);
    context-free at top level it gets the documented neutral like
    the other globals."""

    def test_fetch_status_neutral_pg(self) -> None:
        out = _t2("SELECT 1 WHERE @@FETCH_STATUS = 0;", "tsql", "postgresql")
        assert "@@FETCH_STATUS" not in out.split("/*")[0], out
        assert "UNIQUE:" in out, out


class TestForeignBuiltinNote:
    """P1 silent-output, mechanism 1 (wave 103): a foreign builtin
    deliberately left visible on T-SQL (`CORR`, `TO_CHAR` …) shipped
    with ZERO warnings. It now carries an inline UNIQUE note naming
    the mapping gap — the visible-gap decision stays, but stops
    being silent."""

    def test_corr_notes_gap(self) -> None:
        out = _t("SELECT CORR(b, a) FROM aggtest;", "tsql")
        assert re.search(
            r"(?i)CORR\(b, a\) /\* UNIQUE: unmapped operator Corr", out
        ), out

    def test_native_builtin_unnoted(self) -> None:
        out = _t2("SELECT GETDATE();", "tsql", "tsql")
        assert "UNIQUE:" not in out, out

    def test_mapped_function_unnoted(self) -> None:
        out = _t2("SELECT NVL(a, b) FROM t;", "oracle", "tsql")
        assert "UNIQUE:" not in out, out


class TestPgTableShorthand:
    """P1 silent-output follow-up (wave 104): PG's `TABLE name`
    shorthand mangled silently to `[TABLE] AS onek` (sqlglot parses
    it into an aliased identifier). It is exactly `SELECT * FROM
    name` — mapped on every target."""

    def test_table_shorthand_tsql(self) -> None:
        out = _t("TABLE onek;", "tsql")
        assert re.search(r"(?is)SELECT \*\s+FROM onek", out), out

    def test_table_shorthand_mysql(self) -> None:
        out = _t("TABLE onek;", "mysql")
        assert re.search(r"(?is)SELECT \*\s+FROM onek", out), out


class TestLiveOutputValidation:
    """P1 silent-output, mechanism 3 (wave 105): opt-in live
    validation — statements the real target engine rejects degrade
    to documented carriers with the engine's error, catching what
    the sqlglot gate's leniency lets through. Side-effect free
    (savepoints / PARSEONLY / throwaway DB)."""

    def test_live_pg_rejects_become_carriers(self) -> None:
        import os

        import pytest

        url = os.environ.get("UNIQUE_TEST_PG_URL")
        if not url:
            pytest.skip("needs UNIQUE_TEST_PG_URL")
        from unique.core.transpiler import TranspileOptions, Transpiler

        # IFNULL survives to PG only through a raw fragment; the live
        # engine rejects it even though sqlglot's reader accepts it.
        r = Transpiler().transpile(
            "SELECT DATE_FORMAT(d, '%Y') FROM t1;",
            source="mysql",
            target="postgresql",
            options=TranspileOptions(
                validate_live_url=url,
            ),
        )
        code = [
            ln
            for ln in r.sql.splitlines()
            if ln.strip() and not ln.strip().startswith("--")
        ]
        assert not code or all("DATE_FORMAT" not in ln for ln in code), r.sql
        assert any(w.feature == "live_validation" for w in r.warnings) or not [
            ln for ln in r.sql.splitlines() if "UNIQUE: live" in ln
        ], r.sql


class TestArrayCastFaithful:
    """wave 106 (live-validation discovery): a PG array-type cast
    `'{…}'::float8[]` collapsed to `CAST(… AS ARRAY)` — invalid even
    on PG→PG (the element type was lost, 11x silent gap found by live
    validation). The array type is preserved on PG; on T-SQL/MySQL/
    Oracle (no PG arrays) the statement whole-degrades."""

    def test_array_cast_faithful_pg(self) -> None:
        out = _t2("SELECT '{4,140}'::float8[] AS v;", "postgresql", "postgresql")
        assert "AS ARRAY" not in out.upper(), out
        assert re.search(r"(?i)DOUBLE PRECISION\[\]|FLOAT8\[\]", out), out

    def test_array_cast_degrades_oracle(self) -> None:
        r = Transpiler().transpile(
            "SELECT '{4,140}'::float8[] AS v;",
            source="postgresql",
            target="oracle",
        )
        code = [
            ln
            for ln in r.sql.splitlines()
            if ln.strip() and not ln.strip().startswith("--")
        ]
        assert not code, r.sql


class TestCreateTableLikeParenForm:
    """wave 107 (live-validation discovery — silent DATA LOSS): PG's
    `CREATE TABLE x (LIKE y)` (LIKE inside the column parens, not a
    property) had its LIKE clause DROPPED entirely, leaving
    `CREATE TABLE x;` — a valid-but-empty table (the wave-85 class,
    caught by live validation). The LIKE source is now harvested from
    the schema too."""

    def test_like_paren_form_pg(self) -> None:
        out = _t2("CREATE TABLE m11 (LIKE mlparted1);", "postgresql", "postgresql")
        assert re.search(r"(?i)LIKE mlparted1", out), out

    def test_like_paren_form_not_empty(self) -> None:
        r = Transpiler().transpile(
            "CREATE TABLE m11 (LIKE mlparted1);",
            source="postgresql",
            target="tsql",
        )
        assert not re.search(r"(?i)CREATE TABLE m11\s*;?\s*$", r.sql), r.sql


class TestArrayModelFidelity:
    """wave 108: the IR had no array model, so arrays silently mangled.

    ``ARRAY[1,2,3]`` collapsed to a generic FunctionCall emitted as
    ``ARRAY(1, 2, 3)`` — invalid even on PG. Worse, subscripts went
    through the unhandled-expression RawSQL fallback rendered WITHOUT a
    dialect: sqlglot stores PG subscripts 0-based, so ``arr[2]`` shipped
    as ``arr[1]`` (silent data corruption; on T-SQL it even parsed, as a
    quoted identifier, so no gate caught it). Arrays are now a real IR
    node (ArrayLiteral), unhandled fallbacks render in the SOURCE
    dialect, and subscripts/array-carrying WITHIN GROUP degrade on
    targets without arrays."""

    def test_array_literal_pg_keeps_bracket_spelling(self) -> None:
        out = _t("select array[1,2,3];", "postgresql")
        assert "ARRAY[1, 2, 3]" in out, out
        assert not re.search(r"(?i)ARRAY\(", out), out
        assert "UNIQUE:" not in out, out

    def test_nested_array_literal_pg(self) -> None:
        out = _t("select array[[1,2],[3,4]];", "postgresql")
        assert "ARRAY[ARRAY[1, 2], ARRAY[3, 4]]" in out, out
        assert not re.search(r"(?i)ARRAY\(", out), out

    def test_array_subquery_constructor_pg(self) -> None:
        out = _t("select array(select c from t2) from t1;", "postgresql")
        assert re.search(r"(?is)ARRAY\(SELECT c\s+FROM t2\)", out), out
        assert "UNIQUE:" not in out, out
        assert "SelectStatement(" not in out, out

    def test_subscript_index_preserved_pg(self) -> None:
        out = _t("select arr[2] from t;", "postgresql")
        assert "arr[2]" in out, out
        assert "arr[1]" not in out, out
        assert "UNIQUE:" not in out, out

    def test_paren_array_subscript_preserved_pg(self) -> None:
        out = _t("select (array[1,2,3])[1];", "postgresql")
        assert ")[1]" in out, out
        assert ")[0]" not in out, out

    def test_variadic_array_pg(self) -> None:
        out = _t("select myfn(variadic array[1,2,3]);", "postgresql")
        assert re.search(r"(?i)VARIADIC ARRAY\[1, 2, 3\]", out), out
        assert "UNIQUE:" not in out, out

    def test_percentile_array_arg_valid_pg(self) -> None:
        out = _t(
            "select percentile_cont(array[0.25,0.5]) "
            "within group (order by x) from t;",
            "postgresql",
        )
        assert "ARRAY[0.25, 0.5]" in out, out
        assert not re.search(r"(?i)ARRAY\(0\.25", out), out
        assert "UNIQUE:" not in out, out

    @pytest.mark.parametrize("target", ["tsql", "mysql", "oracle"])
    def test_subscript_degrades_off_pg(self, target: str) -> None:
        r = Transpiler().transpile(
            "select arr[2] from t;", source="postgresql", target=target
        )
        code = [
            ln
            for ln in r.sql.splitlines()
            if ln.strip() and not ln.strip().startswith("--")
        ]
        assert not code, r.sql
        assert r.warnings or r.unsupported, r.sql
        assert "arr[2]" in r.sql, r.sql  # original preserved, index intact

    def test_percentile_array_arg_degrades_oracle(self) -> None:
        r = Transpiler().transpile(
            "select percentile_cont(array[0.25,0.5]) "
            "within group (order by x) from t;",
            source="postgresql",
            target="oracle",
        )
        code = [
            ln
            for ln in r.sql.splitlines()
            if ln.strip() and not ln.strip().startswith("--")
        ]
        assert not code, r.sql
        assert r.warnings or r.unsupported, r.sql

    def test_plain_within_group_still_ships_oracle(self) -> None:
        out = _t(
            "select percentile_cont(0.5) within group (order by x) from t;",
            "oracle",
        )
        assert re.search(r"(?i)WITHIN GROUP", out), out
        assert "UNIQUE:" not in out, out

    @pytest.mark.parametrize("target", ["tsql", "mysql"])
    def test_array_subquery_carrier_has_no_ir_repr(self, target: str) -> None:
        r = Transpiler().transpile(
            "select array(select c from t2) from t1;",
            source="postgresql",
            target=target,
        )
        assert "SelectStatement(" not in r.sql, r.sql
        assert re.search(r"(?is)SELECT c\s+(-- )?FROM t2", r.sql), r.sql
        assert r.warnings or r.unsupported, r.sql

    @pytest.mark.parametrize("target", ["tsql", "mysql", "oracle"])
    def test_array_inside_unmodeled_fragment_degrades(self, target: str) -> None:
        # = ANY(ARRAY[…]) reaches the gate as an unmapped-operator RawSQL;
        # the ARRAY inside the fragment text must still degrade the
        # statement whole (neighbor of the ArrayLiteral node gate).
        r = Transpiler().transpile(
            "delete from t where id = any(array[1,2,3]);",
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

    def test_any_array_kept_on_pg(self) -> None:
        out = _t("delete from t where id = any(array[1,2,3]);", "postgresql")
        assert re.search(r"(?i)ANY\(ARRAY\[1, 2, 3\]\)", out), out
        assert "UNIQUE:" not in out, out


class TestEmbeddedFallbackSpelling:
    """wave 108 regression (caught live by the FE suite): the source-dialect
    RawSQL fallback rendering is WRONG inside procedural bodies — that text
    is mid-transform (variables already @-rewritten for T-SQL), so a
    postgres render turned ``@p_customer_id`` into the invalid pseudocolumn
    ``$p_customer_id``. Embedded IR calls keep the generic rendering; only
    the top-level DML path renders in the source dialect."""

    def test_embedded_insert_params_keep_at_spelling(self) -> None:
        src = (
            "create function add_inv(p_customer_id int, p_qty int) "
            "returns int as $$\n"
            "declare new_id int;\n"
            "begin\n"
            "  insert into invoice (customer_id, qty) "
            "values (p_customer_id, p_qty);\n"
            "  select max(id) into new_id from invoice;\n"
            "  insert into invoice_line (invoice_id, qty)\n"
            "  select new_id, p_qty from product p where p.id = p_qty;\n"
            "  return new_id;\n"
            "end $$ language plpgsql;"
        )
        out = _t(src, "tsql")
        assert "$p_" not in out, out
        assert "$new_id" not in out, out
        assert re.search(r"(?i)VALUES \(@p_customer_id, @p_qty\)", out), out
        assert re.search(r"(?i)SELECT @new_id, @p_qty", out), out

    def test_top_level_fallback_still_source_spelled(self) -> None:
        # The pg->pg subscript fidelity (the wave-108 fix) must survive.
        out = _t("select arr[2] from t;", "postgresql")
        assert "arr[2]" in out, out
        assert "arr[1]" not in out, out


class TestDropTriggerOnTable:
    """wave 109: PG's ``DROP TRIGGER name ON table`` lost its mandatory ON
    clause even pg→pg (sqlglot parks it in the unread ``cluster`` arg —
    the DROP INDEX lesson again), shipping invalid PG silently. And the
    inverse neighbor: a T-SQL/MySQL/Oracle DROP TRIGGER (schema-scoped,
    no table) shipped to PG without the ON that PG requires — now the
    documented carrier, like DROP INDEX."""

    def test_pg_keeps_on_table(self) -> None:
        out = _t("drop trigger if exists mytrig on t1;", "postgresql")
        assert re.search(r"(?i)DROP TRIGGER IF EXISTS mytrig ON t1", out), out
        assert "UNIQUE:" not in out, out

    @pytest.mark.parametrize("target", ["tsql", "mysql", "oracle"])
    def test_on_correctly_dropped_off_pg(self, target: str) -> None:
        out = _t("drop trigger if exists mytrig on t1;", target)
        assert re.search(r"(?i)DROP TRIGGER", out), out
        assert not re.search(r"(?i)ON t1", out), out
        assert "UNIQUE:" not in out, out

    @pytest.mark.parametrize("source", ["tsql", "mysql", "oracle"])
    def test_sourceless_on_degrades_to_pg(self, source: str) -> None:
        r = Transpiler().transpile(
            "drop trigger mytrig;", source=source, target="postgresql"
        )
        code = [
            ln
            for ln in r.sql.splitlines()
            if ln.strip() and not ln.strip().startswith("--")
        ]
        assert not code, r.sql
        assert r.warnings or r.unsupported, r.sql
        assert re.search(r"(?i)DROP TRIGGER (IF EXISTS )?mytrig", r.sql), r.sql


class TestFunctionRelations:
    """wave 110: a set-returning function in FROM/JOIN position VANISHED —
    ``FROM generate_series(1,3) g`` shipped as ``FROM g`` (the alias
    promoted to a table name, the function gone: silent data loss even
    pg→pg, the biggest remaining discovery class). sqlglot models it as
    ``Table(this=<func>)``; the converter only read ``.name``. TableRef
    now carries the function, PG re-emits it faithfully (FROM, JOIN,
    WITH ORDINALITY, unnest with column aliases), and targets without
    the construct keep their honest paths."""

    def test_from_function_preserved_pg(self) -> None:
        out = _t("select * from generate_series(1,3) g;", "postgresql")
        assert re.search(r"(?i)FROM generate_series\(1, 3\) (AS )?g", out), out
        assert not re.search(r"(?i)FROM\s+g\b(?!enerate)", out), out
        assert "UNIQUE:" not in out, out

    def test_join_function_preserved_pg(self) -> None:
        out = _t(
            "select * from t join generate_series(1,3) g on g = t.id;",
            "postgresql",
        )
        assert re.search(r"(?i)JOIN generate_series\(1, 3\) (AS )?g", out), out
        assert not re.search(r"(?i)JOIN g\b(?!enerate)", out), out
        assert "UNIQUE:" not in out, out

    def test_unnest_relation_with_column_alias_pg(self) -> None:
        out = _t("select * from unnest(arr) as u(x);", "postgresql")
        assert re.search(r"(?i)FROM UNNEST\(arr\) (AS )?u\(x\)", out), out
        assert "UNIQUE:" not in out, out

    def test_with_ordinality_pg(self) -> None:
        out = _t(
            "select * from generate_series(1,3) with ordinality as g(v, o);",
            "postgresql",
        )
        assert re.search(
            r"(?i)generate_series\(1, 3\) WITH ORDINALITY (AS )?g\(v, o\)", out
        ), out
        assert "UNIQUE:" not in out, out

    def test_comma_lateral_shape_pg(self) -> None:
        # The corpus shape that exposed the class: SRF + comma + LATERAL.
        out = _t(
            "select s1, sm from generate_series(1,3) s1, "
            "lateral (select sum(s1) as sm from t) ss;",
            "postgresql",
        )
        assert re.search(r"(?i)generate_series\(1, 3\)", out), out
        assert "UNIQUE:" not in out, out

    def test_unnest_relation_still_degrades_off_pg(self) -> None:
        r = Transpiler().transpile(
            "select * from unnest(arr) as u(x);",
            source="postgresql",
            target="tsql",
        )
        code = [
            ln
            for ln in r.sql.splitlines()
            if ln.strip() and not ln.strip().startswith("--")
        ]
        assert not code, r.sql
        assert r.warnings or r.unsupported, r.sql

    def test_plain_table_alias_unaffected(self) -> None:
        out = _t("select * from mytable g;", "postgresql")
        assert re.search(r"(?i)FROM mytable (AS )?g", out), out


class TestCommaLateralJoin:
    """wave 111 (the blocker wave 110 exposed): a comma-joined LATERAL
    (``FROM t, LATERAL (…) ss``) emitted ``JOIN LATERAL (…) ss`` with NO
    ON clause — invalid PG/MySQL that sqlglot's lenient gate passes (the
    silent-gap signature). An unconditioned inner lateral is spelled
    ``CROSS JOIN LATERAL``."""

    def test_comma_lateral_emits_cross_join_pg(self) -> None:
        out = _t(
            "select s1, sm from generate_series(1,3) s1, "
            "lateral (select sum(s1) as sm from t) ss;",
            "postgresql",
        )
        assert re.search(r"(?i)CROSS JOIN LATERAL", out), out
        assert not re.search(r"(?i)(?<!CROSS )JOIN LATERAL", out), out
        assert "UNIQUE:" not in out, out

    def test_conditioned_lateral_keeps_on_pg(self) -> None:
        out = _t(
            "select * from t left join lateral (select x from u "
            "where u.id = t.id) ss on true;",
            "postgresql",
        )
        assert re.search(r"(?i)LEFT JOIN LATERAL", out), out
        assert re.search(r"(?i)ON TRUE", out), out


class TestDoubleColonCastInBodies:
    """wave 112: the procedural lexer tokenized ``::`` as two COLON tokens,
    and the token-joiner spaced them — ``relname::text`` shipped as the
    invalid ``relname : : text`` inside converted routine bodies (25x of
    the discovery tail, plus 4x live on the pg→tsql sweep). ``::`` is now
    ONE operator token; PG accepts spaced ``x :: text``."""

    def test_cast_survives_in_sql_function_body(self) -> None:
        src = (
            "create function error1(text) returns text language sql as $$\n"
            "SELECT relname::text FROM pg_class c WHERE c.oid = $1::regclass\n"
            "$$;"
        )
        out = _t(src, "postgresql")
        assert ": :" not in out, out
        assert re.search(r"(?i)relname\s*::\s*text", out), out
        assert re.search(r"(?i)p1\s*::\s*regclass", out), out

    def test_cast_in_plpgsql_assignment(self) -> None:
        src = (
            "create function f() returns date as $$\n"
            "declare d date;\n"
            "begin\n"
            "  d := '2024-01-01'::date;\n"
            "  return d;\n"
            "end $$ language plpgsql;"
        )
        out = _t(src, "postgresql")
        assert ": :" not in out, out
        assert re.search(r"::\s*date", out), out

    def test_oracle_trigger_colon_refs_unaffected(self) -> None:
        src = (
            "create or replace trigger trg before insert on t for each row\n"
            "begin\n"
            "  :new.c := 1;\n"
            "end;"
        )
        out = _t2(src, "oracle", "oracle")
        assert ":new" in out.lower() or ": new" not in out, out
        assert ": :" not in out, out


class TestFunctionRelationTargets:
    """wave 113: wave 110 preserved SRF relations, which surfaced the
    target-side truth — MySQL has NO table functions (except JSON_TABLE),
    so ``FROM generate_series(…) g`` shipped as a hard 1064 syntax error
    (243x on the pg→mysql sweep, previously hidden as an
    'expected-missing' bare alias). Per the no-silent-loss contract the
    statement degrades WHOLE on mysql; Oracle spells a function relation
    ``TABLE(fn(args)) alias``."""

    def test_srf_relation_degrades_on_mysql(self) -> None:
        r = Transpiler().transpile(
            "select * from generate_series(1,3) g;",
            source="postgresql",
            target="mysql",
        )
        code = [
            ln
            for ln in r.sql.splitlines()
            if ln.strip() and not ln.strip().startswith("--")
        ]
        assert not code, r.sql
        assert r.warnings or r.unsupported, r.sql
        assert re.search(r"(?i)generate_series", r.sql), r.sql

    def test_srf_relation_table_wrapped_on_oracle(self) -> None:
        out = _t("select * from generate_series(1,3) g;", "oracle")
        assert re.search(r"(?i)TABLE\(GENERATE_SERIES\(1, 3\)\) g", out), out
        assert "UNIQUE:" not in out, out

    def test_srf_relation_kept_on_tsql(self) -> None:
        # T-SQL has table functions (and GENERATE_SERIES since 2022).
        out = _t("select * from generate_series(1,3) g;", "tsql")
        assert re.search(r"(?i)GENERATE_SERIES\(1, 3\) g", out), out

    def test_json_table_not_degraded_on_mysql(self) -> None:
        # JSON_TABLE is MySQL's own table function — it must keep its path.
        r = Transpiler().transpile(
            "select * from json_table('[1]', '$[*]' columns (x int path '$')) jt;",
            source="mysql",
            target="mysql",
        )
        assert "1064" not in " ".join(r.unsupported), r.sql


class TestDataModifyingCte:
    """wave 114: a data-modifying CTE (``WITH ins AS (INSERT … RETURNING)
    SELECT …``) had its DML body SHREDDED into a ``SELECT *`` skeleton by
    the CTE converter (silent loss of the INSERT/DELETE itself, 15x
    'SELECT * with no tables' in the discovery). PG-only construct:
    preserved pg→pg via the CTE-DML passthrough, degraded whole with a
    carrier elsewhere."""

    def test_with_insert_returning_preserved_pg(self) -> None:
        out = _t(
            "with ins as (insert into t (a) values (1) returning a, b) "
            "select a, b from ins;",
            "postgresql",
        )
        assert re.search(r"(?i)INSERT INTO t", out), out
        assert re.search(r"(?i)RETURNING", out), out
        assert not re.search(r"(?i)AS \(\s*SELECT \*\s*\)", out), out
        assert "UNIQUE:" not in out, out

    def test_with_delete_returning_preserved_pg(self) -> None:
        out = _t(
            "with d as (delete from t where a = 1 returning a) " "select * from d;",
            "postgresql",
        )
        assert re.search(r"(?i)DELETE FROM t", out), out
        assert "UNIQUE:" not in out, out

    @pytest.mark.parametrize("target", ["tsql", "mysql", "oracle"])
    def test_dml_cte_degrades_off_pg(self, target: str) -> None:
        r = Transpiler().transpile(
            "with ins as (insert into t (a) values (1) returning a) "
            "select a from ins;",
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
        assert re.search(r"(?i)INSERT INTO t", r.sql), r.sql


class TestPlpgsqlDeclareModifiers:
    """wave 115: the plpgsql DECLARE parser stopped at the first token it
    did not know and SHREDDED the declaration — ``rc constant refcursor``
    became ``rc constant;`` + ``refcursor ;;``, ``c scroll cursor for …``
    became ``c scroll;`` + orphan tokens, and ``a integer[] = '{…}'``
    became ``a integer;`` + ``[] =;`` (the ';', 'FOR', 'data type' and
    '[' discovery classes — one parser mechanism). The declaration
    grammar now consumes CONSTANT, [NO] SCROLL cursors, and array
    suffixes; PG re-emits them faithfully."""

    def test_constant_declare_pg(self) -> None:
        src = (
            "create function f() returns refcursor as $$\n"
            "declare rc constant refcursor := 'my_cursor';\n"
            "begin return rc; end $$ language plpgsql;"
        )
        out = _t(src, "postgresql")
        assert ";;" not in out, out
        assert re.search(r"(?i)rc CONSTANT refcursor", out), out

    def test_scroll_cursor_declare_pg(self) -> None:
        src = (
            "create function f() returns int as $$\n"
            "declare c scroll cursor for select 1;\n"
            "declare x int;\n"
            "begin open c; fetch c into x; close c; return x; end\n"
            "$$ language plpgsql;"
        )
        out = _t(src, "postgresql")
        assert re.search(r"(?i)c SCROLL CURSOR FOR", out), out
        assert "scroll;" not in out.lower(), out

    def test_no_scroll_cursor_declare_pg(self) -> None:
        src = (
            "create function f() returns int as $$\n"
            "declare c no scroll cursor for select 1; x int;\n"
            "begin open c; fetch c into x; close c; return x; end\n"
            "$$ language plpgsql;"
        )
        out = _t(src, "postgresql")
        assert re.search(r"(?i)c NO SCROLL CURSOR FOR", out), out
        assert "no;" not in out.lower(), out

    def test_array_declare_pg(self) -> None:
        src = (
            "create function f() returns void as $$\n"
            "declare a integer[] = '{10,20,30}';\n"
            "begin a[1] := 1; end $$ language plpgsql;"
        )
        out = _t(src, "postgresql")
        assert "[] =" not in out, out
        assert re.search(r"(?i)a integer\[\]\s*:?=", out), out

    def test_setof_array_return_pg(self) -> None:
        src = (
            "create function f() returns setof integer[] as $$\n"
            "begin return; end $$ language plpgsql;"
        )
        out = _t(src, "postgresql")
        assert re.search(r"(?i)RETURNS SETOF integer\[\]", out), out

    def test_scroll_cursor_tsql_native(self) -> None:
        src = (
            "create function f() returns int as $$\n"
            "declare c scroll cursor for select 1; x int;\n"
            "begin open c; fetch c into x; close c; return x; end\n"
            "$$ language plpgsql;"
        )
        out = _t(src, "tsql")
        assert "scroll;" not in out.lower(), out
        assert ";;" not in out, out


class TestOpenCursorScrollExecute:
    """wave 116: ``OPEN c [NO] SCROLL FOR [EXECUTE …]`` — the OPEN parse
    stopped at the cursor name, leaving ``scroll for execute '…';`` as an
    orphan statement (the remaining ';' class). The modifiers and the
    dynamic FOR EXECUTE form are now consumed; PG re-emits them."""

    def test_open_scroll_for_execute_pg(self) -> None:
        src = (
            "create function f() returns int as $$\n"
            "declare c refcursor; x integer;\n"
            "begin\n"
            "  open c scroll for execute 'select f1 from t';\n"
            "  fetch c into x; close c; return x;\n"
            "end $$ language plpgsql;"
        )
        out = _t(src, "postgresql")
        assert re.search(
            r"(?is)OPEN c SCROLL FOR\s+EXECUTE 'select f1 from t'", out
        ), out
        assert not re.search(r"(?im)^\s*scroll\b", out), out

    def test_open_no_scroll_for_query_pg(self) -> None:
        src = (
            "create function f() returns int as $$\n"
            "declare c refcursor; x integer;\n"
            "begin\n"
            "  open c no scroll for select f1 from t;\n"
            "  fetch c into x; close c; return x;\n"
            "end $$ language plpgsql;"
        )
        out = _t(src, "postgresql")
        assert re.search(r"(?is)OPEN c NO SCROLL FOR\s+SELECT f1", out), out
        assert not re.search(r"(?im)^\s*scroll\b", out), out

    def test_plain_open_for_unchanged_pg(self) -> None:
        src = (
            "create function f() returns int as $$\n"
            "declare c refcursor; x integer;\n"
            "begin\n"
            "  open c for select f1 from t;\n"
            "  fetch c into x; close c; return x;\n"
            "end $$ language plpgsql;"
        )
        out = _t(src, "postgresql")
        assert re.search(r"(?is)OPEN c FOR\s+SELECT f1", out), out


class TestAliasForDeclaration:
    """wave 117 (found by the two-strikes end-to-end trace of a real
    corpus function): ``myname ALIAS FOR $1;`` shredded into ``myname
    alias;`` + orphan ``for p1;`` — the unmoved 14x ';' class. The
    token-level rename (alias -> its target, the same mechanism as the
    $n positional aliasing) is the faithful translation on EVERY
    target; the declaration itself vanishes."""

    def test_alias_for_positional_param(self) -> None:
        src = (
            "create function f(bpchar) returns integer as '\n"
            "declare\n"
            "    myname alias for $1;\n"
            "    mytype char(2);\n"
            "begin\n"
            "    mytype := substr(myname, 1, 2);\n"
            "    return 0;\n"
            "end' language plpgsql;"
        )
        out = _t(src, "postgresql")
        assert "alias" not in out.lower(), out
        assert not re.search(r"(?im)^\s*for p1;", out), out
        assert re.search(r"(?i)substr\s*\(\s*p1", out), out

    def test_alias_for_named_param(self) -> None:
        src = (
            "create function f(x integer) returns integer as $$\n"
            "declare n alias for x;\n"
            "begin return n + 1; end $$ language plpgsql;"
        )
        out = _t(src, "postgresql")
        assert "alias" not in out.lower(), out
        assert re.search(r"(?i)RETURN x \+ 1", out), out


class TestFetchDirections:
    """wave 118: ``FETCH NEXT|LAST|… FROM c INTO x`` — the FETCH parse
    took the DIRECTION word as the cursor name, emitting ``FETCH next
    INTO ;`` plus an orphan ``from c into x;`` (the 7x INTO class).
    Directions are native on PG and T-SQL; Oracle/MySQL cursors only
    step forward, so a non-NEXT direction degrades to the documented
    carrier there."""

    def test_fetch_next_from_pg(self) -> None:
        src = (
            "create function f() returns int as $$\n"
            "declare rc refcursor; x record;\n"
            "begin\n"
            "  rc := get_cur();\n"
            "  fetch next from rc into x;\n"
            "  return x.a;\n"
            "end $$ language plpgsql;"
        )
        out = _t(src, "postgresql")
        assert re.search(r"(?i)FETCH NEXT FROM rc INTO x;", out), out
        assert "INTO ;" not in out, out

    def test_fetch_last_from_pg(self) -> None:
        src = (
            "create function f() returns int as $$\n"
            "declare c cursor for select f1 from t; x integer;\n"
            "begin\n"
            "  open c;\n"
            "  fetch last from c into x;\n"
            "  close c; return x;\n"
            "end $$ language plpgsql;"
        )
        out = _t(src, "postgresql")
        assert re.search(r"(?i)FETCH LAST FROM c INTO x;", out), out
        assert "INTO ;" not in out, out

    def test_fetch_last_degrades_oracle(self) -> None:
        src = (
            "create function f() returns int as $$\n"
            "declare c cursor for select f1 from t; x integer;\n"
            "begin\n"
            "  open c;\n"
            "  fetch last from c into x;\n"
            "  close c; return x;\n"
            "end $$ language plpgsql;"
        )
        out = _t(src, "oracle")
        code = [
            ln
            for ln in out.splitlines()
            if ln.strip() and not ln.strip().startswith("--")
        ]
        assert not any(re.search(r"(?i)FETCH LAST", ln) for ln in code), out
        assert "UNIQUE:" in out, out

    def test_plain_fetch_unchanged_pg(self) -> None:
        src = (
            "create function f() returns int as $$\n"
            "declare c cursor for select f1 from t; x integer;\n"
            "begin open c; fetch c into x; close c; return x; end\n"
            "$$ language plpgsql;"
        )
        out = _t(src, "postgresql")
        assert re.search(r"(?i)FETCH c INTO x;", out), out


class TestBareRaiseAndUsing:
    """wave 119: plpgsql's bare re-``RAISE;`` and ``RAISE USING key =
    expr`` fell into the generic expression fallback — the re-raise
    emitted the invalid ``RAISE EXCEPTION '%', ;`` and the USING form
    mangled into ``'%', using message = …``. Every engine has a native
    re-raise (PG/Oracle ``RAISE;``, T-SQL ``THROW;``, MySQL
    ``RESIGNAL;``); USING's message option IS the message."""

    _SRC_RERAISE = (
        "create function f() returns void as $$\n"
        "begin\n"
        "  begin\n"
        "    raise exception 'boom';\n"
        "  exception when others then\n"
        "    raise;\n"
        "  end;\n"
        "end $$ language plpgsql;"
    )

    def test_bare_reraise_pg(self) -> None:
        out = _t(self._SRC_RERAISE, "postgresql")
        assert "'%', ;" not in out, out
        assert re.search(r"(?im)^\s*RAISE;", out), out

    def test_bare_reraise_tsql(self) -> None:
        out = _t(self._SRC_RERAISE, "tsql")
        assert "'%', ;" not in out, out
        assert re.search(r"(?im)^\s*THROW;", out), out

    def test_bare_reraise_mysql(self) -> None:
        out = _t(self._SRC_RERAISE, "mysql")
        assert re.search(r"(?i)RESIGNAL", out), out

    def test_bare_reraise_oracle(self) -> None:
        out = _t(self._SRC_RERAISE, "oracle")
        assert "'%', ;" not in out, out
        assert re.search(r"(?im)^\s*RAISE;", out), out

    def test_raise_using_message_pg(self) -> None:
        src = (
            "create function f() returns void as $$\n"
            "begin\n"
            "  raise using message = 'custom' || ' message';\n"
            "end $$ language plpgsql;"
        )
        out = _t(src, "postgresql")
        assert "using message" not in out.lower(), out
        assert re.search(r"(?i)RAISE EXCEPTION '%', 'custom' \|\| ' message'", out), out


class TestForeachArrayLoop:
    """wave 120: plpgsql's ``FOREACH x [SLICE n] IN ARRAY expr LOOP …
    END LOOP`` was not modeled — the loop structure shredded (``foreach
    x in array p1 loop raise notice`` flattened, END LOOP lost). PG-only
    construct (arrays): preserved pg→pg, degraded whole with a carrier
    elsewhere."""

    _SRC = (
        "create function f(anyarray) returns void as $$\n"
        "declare x int;\n"
        "begin\n"
        "  foreach x in array $1\n"
        "  loop\n"
        "    raise notice '%', x;\n"
        "  end loop;\n"
        "end $$ language plpgsql;"
    )

    def test_foreach_preserved_pg(self) -> None:
        out = _t(self._SRC, "postgresql")
        assert re.search(r"(?i)FOREACH x IN ARRAY p1", out), out
        assert re.search(r"(?i)END LOOP;", out), out
        # The body must render as SQL lines, not a Python list repr
        # (the first emit shipped ["        RAISE NOTICE ..."]).
        assert re.search(r"(?im)^\s*RAISE NOTICE", out), out
        assert '["' not in out, out

    def test_foreach_slice_preserved_pg(self) -> None:
        src = self._SRC.replace("in array", "slice 1 in array").replace(
            "x int", "x int[]"
        )
        out = _t(src, "postgresql")
        assert re.search(r"(?i)FOREACH x SLICE 1 IN ARRAY p1", out), out
        assert re.search(r"(?i)END LOOP;", out), out

    @pytest.mark.parametrize("target", ["tsql", "mysql", "oracle"])
    def test_foreach_degrades_off_pg(self, target: str) -> None:
        r = Transpiler().transpile(self._SRC, source="postgresql", target=target)
        out_low = r.sql.lower()
        code = [
            ln
            for ln in r.sql.splitlines()
            if ln.strip() and not ln.strip().startswith("--")
        ]
        assert not any("foreach" in ln.lower() for ln in code), r.sql
        assert r.warnings or r.unsupported, r.sql
        assert "foreach" in out_low, r.sql  # original preserved in the carrier


class TestPgDynamicExecute:
    """wave 121: plpgsql's EXECUTE is ALWAYS dynamic SQL (procedure calls
    are spelled CALL there), but the SQL*Plus exec-call fallthrough
    mangled ``EXECUTE 'select …' INTO STRICT x`` into ``CALL 'select
    …'();`` plus an orphan ``into strict x;`` (8x, the biggest remaining
    discovery class)."""

    def test_execute_string_into_strict(self) -> None:
        src = (
            "create or replace function f() returns void as $$\n"
            "declare x record;\n"
            "begin\n"
            "  execute 'select * from foo where f1 = 3' into strict x;\n"
            "end $$ language plpgsql;"
        )
        out = _t(src, "postgresql")
        assert "CALL '" not in out, out
        assert re.search(
            r"(?i)EXECUTE 'select \* from foo where f1 = 3' INTO STRICT x;", out
        ), out

    def test_execute_expr_using(self) -> None:
        src = (
            "create or replace function f(n int) returns void as $$\n"
            "declare x int;\n"
            "begin\n"
            "  execute 'select $1 + 1' into x using n;\n"
            "end $$ language plpgsql;"
        )
        out = _t(src, "postgresql")
        assert "CALL '" not in out, out
        assert re.search(r"(?i)EXECUTE 'select .* \+ 1' INTO x USING n;", out), out

    def test_call_statement_untouched(self) -> None:
        src = (
            "create or replace function f() returns void as $$\n"
            "begin\n"
            "  call my_proc(1);\n"
            "end $$ language plpgsql;"
        )
        out = _t(src, "postgresql")
        assert re.search(r"(?i)CALL my_proc\s*\(\s*1\s*\);", out), out


class TestNonSqlLanguageFunction:
    """wave 122: a ``LANGUAGE C`` function (``AS '$libdir/…'``) has no SQL
    body — it emitted an EMPTY plpgsql function with the LANGUAGE
    rewritten (silent loss of the implementation reference). Verbatim on
    its own engine, documented carrier cross-dialect."""

    _SRC = (
        "CREATE FUNCTION check_primary_key() RETURNS trigger\n"
        "AS '$libdir/refint' LANGUAGE C;"
    )

    def test_language_c_verbatim_pg(self) -> None:
        out = _t(self._SRC, "postgresql")
        assert re.search(r"(?i)LANGUAGE C", out), out
        assert re.search(r"(?i)\$libdir/refint", out), out
        assert "plpgsql" not in out.lower(), out

    @pytest.mark.parametrize("target", ["tsql", "mysql", "oracle"])
    def test_language_c_degrades_off_pg(self, target: str) -> None:
        r = Transpiler().transpile(self._SRC, source="postgresql", target=target)
        code = [
            ln
            for ln in r.sql.splitlines()
            if ln.strip() and not ln.strip().startswith("--")
        ]
        assert not code, r.sql
        assert r.warnings or r.unsupported, r.sql
        assert re.search(r"(?i)libdir/refint", r.sql), r.sql


class TestSavepointStatement:
    """wave 123: ``SAVEPOINT a`` mis-parses in sqlglot as an Alias and
    shipped as the invalid ``SAVEPOINT AS a`` on every engine. Modeled
    as a passthrough: same spelling on PG/MySQL/Oracle, T-SQL spells it
    ``SAVE TRANSACTION``."""

    @pytest.mark.parametrize("target", ["postgresql", "mysql", "oracle"])
    def test_savepoint_plain(self, target: str) -> None:
        out = _t("savepoint a;", target)
        assert re.search(r"(?i)SAVEPOINT a", out), out
        assert "AS a" not in out, out

    def test_savepoint_tsql(self) -> None:
        out = _t("savepoint a;", "tsql")
        assert re.search(r"(?i)SAVE TRANSACTION a", out), out
        assert "SAVEPOINT" not in out.upper(), out


class TestEmptySelectList:
    """wave 124: PG's empty select list (``SELECT;`` — zero columns, one
    row, allowed since 9.4) silently gained a ``*`` (``SELECT *;`` is
    invalid without FROM and changes the result shape with one).
    Preserved on PG; degraded whole elsewhere (no other engine has the
    form)."""

    def test_empty_select_pg(self) -> None:
        out = _t("select;", "postgresql")
        assert "*" not in out, out
        assert re.search(r"(?im)^\s*SELECT\s*;", out), out

    def test_empty_select_union_pg(self) -> None:
        out = _t("select union select;", "postgresql")
        assert "*" not in out, out
        assert re.search(r"(?is)SELECT\s+UNION\s+SELECT", out), out

    @pytest.mark.parametrize("target", ["tsql", "mysql", "oracle"])
    def test_empty_select_degrades_off_pg(self, target: str) -> None:
        r = Transpiler().transpile("select;", source="postgresql", target=target)
        code = [
            ln
            for ln in r.sql.splitlines()
            if ln.strip() and not ln.strip().startswith("--")
        ]
        assert not code, r.sql
        assert r.warnings or r.unsupported, r.sql

    def test_normal_star_select_unaffected(self) -> None:
        out = _t("select * from t;", "postgresql")
        assert re.search(r"(?i)SELECT \*\s+FROM t", out), out


class TestTruncateTrigger:
    """wave 125: PG's TRUNCATE trigger event was not a recognized event —
    the whole trigger shredded into garbage declarations (``DECLARE
    TRUNCATE ON; mytable FOR; …``). Recognized on PG; degraded whole on
    targets without the event."""

    _SRC = (
        "CREATE TRIGGER trig BEFORE TRUNCATE ON mytable "
        "FOR EACH STATEMENT EXECUTE FUNCTION f();"
    )

    def test_truncate_trigger_preserved_pg(self) -> None:
        out = _t(self._SRC, "postgresql")
        assert re.search(r"(?i)BEFORE TRUNCATE\s+ON mytable", out), out
        assert "TRUNCATE ON;" not in out, out
        assert "UNIQUE:" not in out, out

    @pytest.mark.parametrize("target", ["tsql", "mysql", "oracle"])
    def test_truncate_trigger_degrades_off_pg(self, target: str) -> None:
        r = Transpiler().transpile(self._SRC, source="postgresql", target=target)
        code = [
            ln
            for ln in r.sql.splitlines()
            if ln.strip() and not ln.strip().startswith("--")
        ]
        assert not code, r.sql
        assert r.warnings or r.unsupported, r.sql


class TestPlpgsqlBlockLabel:
    """wave 126: plpgsql ``<<label>>`` block labels (and their qualified
    variable references, ``label.var``) are not modeled — the declare
    loop shredded them into ``< <; label >; >`` garbage. Verbatim on PG,
    documented carrier elsewhere."""

    _SRC = (
        "create function f() returns integer as $$\n"
        "<<outerblock>>\n"
        "declare quantity integer := 30;\n"
        "begin\n"
        "  quantity := quantity + 10;\n"
        "  return outerblock.quantity;\n"
        "end $$ language plpgsql;"
    )

    def test_block_label_verbatim_pg(self) -> None:
        out = _t(self._SRC, "postgresql")
        assert "<<outerblock>>" in out.replace(" ", ""), out
        assert "< <;" not in out, out

    @pytest.mark.parametrize("target", ["tsql", "mysql", "oracle"])
    def test_block_label_degrades_off_pg(self, target: str) -> None:
        r = Transpiler().transpile(self._SRC, source="postgresql", target=target)
        code = [
            ln
            for ln in r.sql.splitlines()
            if ln.strip() and not ln.strip().startswith("--")
        ]
        assert not code, r.sql
        assert r.warnings or r.unsupported, r.sql


class TestCteFidelity:
    """wave 127: `_convert_cte` harvested only name+query — RECURSIVE
    and the column list `x(a)` silently dropped (both fields existed on
    CTEDefinition, unset), and a VALUES body mangled into a one-row
    SELECT (`SELECT ('a'), ('b')`)."""

    def test_recursive_and_columns_kept(self) -> None:
        out = _t(
            "with recursive x(a) as (select 1 union all "
            "select a + 1 from x where a < 3) select * from x;",
            "postgresql",
        )
        assert re.search(r"(?i)WITH RECURSIVE x\(a\) AS", out), out

    def test_values_cte_body(self) -> None:
        out = _t("with v(a) as (values (1), (2)) select * from v;", "postgresql")
        assert not re.search(r"(?i)SELECT \(1\), \(2\)", out), out
        assert re.search(r"(?is)SELECT 1(\s+AS a)?\s+UNION ALL\s+SELECT 2", out), out


class TestTempAndZeroColumnTables:
    """wave 128: ``CREATE TEMP TABLE`` lost its TEMPORARY even pg→pg (a
    session-scoped table silently became permanent), and a zero-column
    ``CREATE TABLE onerow()`` lost its parens (invalid PG; the form
    doesn't exist elsewhere and degrades there)."""

    def test_temp_table_kept_pg(self) -> None:
        out = _t("create temp table t2 (a int);", "postgresql")
        assert re.search(r"(?i)CREATE TEMPORARY TABLE t2", out), out

    def test_zero_column_table_pg(self) -> None:
        out = _t("create temp table onerow();", "postgresql")
        assert re.search(r"(?i)CREATE TEMPORARY TABLE onerow\s*\(\s*\)", out), out

    @pytest.mark.parametrize("target", ["tsql", "mysql", "oracle"])
    def test_zero_column_degrades_off_pg(self, target: str) -> None:
        r = Transpiler().transpile(
            "create table onerow();", source="postgresql", target=target
        )
        code = [
            ln
            for ln in r.sql.splitlines()
            if ln.strip() and not ln.strip().startswith("--")
        ]
        assert not code, r.sql
        assert r.warnings or r.unsupported, r.sql


class TestRecursiveCtePerDialect:
    """wave 127b (caught by the sweep regression 145→178 on tsql): the
    RECURSIVE keyword is REQUIRED on PG/MySQL and does not EXIST on
    T-SQL/Oracle (recursion is implicit there)."""

    _SRC = (
        "with recursive x(a) as (select 1 union all "
        "select a + 1 from x where a < 3) select * from x;"
    )

    @pytest.mark.parametrize("target", ["postgresql", "mysql"])
    def test_recursive_kept(self, target: str) -> None:
        out = _t(self._SRC, target)
        assert re.search(r"(?i)WITH RECURSIVE x", out), out

    @pytest.mark.parametrize("target", ["tsql", "oracle"])
    def test_recursive_dropped(self, target: str) -> None:
        out = _t(self._SRC, target)
        assert "RECURSIVE" not in out.upper(), out
        assert re.search(r"(?i)WITH x", out), out


class TestSetArmWithCte:
    """wave 129: a parenthesized UNION arm carrying its own WITH lost
    the parens (``UNION ALL WITH z AS (…) SELECT …`` — invalid; the
    WITH must stay inside a parenthesized arm)."""

    def test_union_arm_with_cte_pg(self) -> None:
        out = _t(
            "with x as (select 1 as a union all "
            "(with z as (select 2 as a) select a from z)) select * from x;",
            "postgresql",
        )
        assert re.search(r"(?is)UNION ALL\s*\(\s*WITH z", out), out


class TestWave130Batch:
    """wave 130: three shapes — a FOR range shipped as ``0 . . n``
    (``..`` is now ONE lexer token, the wave-112 ``::`` twin); plpgsql
    ``#option`` compiler lines shredded (whole-unit like block labels);
    and a parenthesized set arm with its own ORDER BY lost its parens."""

    def test_for_range_dots(self) -> None:
        src = (
            "create function f() returns int as $$\n"
            "declare s int := 0;\n"
            "begin\n"
            "  for i in 0..3 loop s := s + i; end loop;\n"
            "  return s;\n"
            "end $$ language plpgsql;"
        )
        out = _t(src, "postgresql")
        assert ". ." not in out, out
        assert re.search(r"(?i)IN 0\s?\.\.\s?3", out), out

    def test_print_strict_params_option(self) -> None:
        src = (
            "create or replace function f() returns void as $$\n"
            "#print_strict_params on\n"
            "declare x record;\n"
            "begin\n"
            "  select 1 into strict x;\n"
            "end $$ language plpgsql;"
        )
        out = _t(src, "postgresql")
        assert "#print_strict_params on" in out, out
        assert "#print_strict_params on;" not in out, out

    def test_union_arm_with_order_by(self) -> None:
        out = _t(
            "select 1.1 as two union (select 2 union all select 2) order by 1;",
            "postgresql",
        )
        # The parenthesized chain arm is shielded as a derived table so
        # its association survives and the outer ORDER BY stays outside.
        assert re.search(
            r"(?is)UNION\s+SELECT \*\s+FROM \(SELECT 2\s+UNION ALL\s+SELECT 2\)", out
        ), out
        assert out.rstrip().endswith("ORDER BY 1 ASC;"), out


class TestWave131Batch:
    """wave 131, five shapes from the individual-gap dump: VARIADIC is an
    argmode not a parameter NAME (every $1 alias became 'variadic');
    ``i integer NOT NULL := 0`` declares split; a VALUES set-op arm
    mangled to a one-row SELECT; ``TABLE name`` with a leading comment
    escaped its pre-normalization (comments are trivia); BOOLEAN carried
    a width."""

    def test_variadic_param(self) -> None:
        src = (
            "create or replace function vari(variadic int[]) returns void as $$\n"
            "begin\n"
            "  for i in array_lower($1,1)..array_upper($1,1) loop\n"
            "    raise notice '%', $1[i];\n"
            "  end loop;\n"
            "end $$ language plpgsql;"
        )
        out = _t(src, "postgresql")
        assert re.search(r"(?i)VARIADIC p1 int\[\]", out), out
        assert re.search(r"(?i)array_lower\s*\(\s*p1", out), out
        assert "( variadic" not in out.lower(), out

    def test_not_null_declare_pg(self) -> None:
        src = (
            "create function f() returns integer as $$\n"
            "declare i integer NOT NULL := 0;\n"
            "begin return i; end $$ language plpgsql;"
        )
        out = _t(src, "postgresql")
        assert re.search(r"(?i)i integer NOT NULL := 0;", out), out
        assert "NOT NULL :=" not in out.replace("integer NOT NULL :=", ""), out

    def test_values_set_arm(self) -> None:
        out = _t(
            "with x(a) as ((values ('a'), ('b')) union all select 'c') "
            "select * from x;",
            "postgresql",
        )
        assert not re.search(r"(?i)SELECT \('a'\), \('b'\)", out), out
        assert re.search(
            r"(?is)SELECT 'a'(\s+AS a)?\s+UNION ALL\s+SELECT 'b'", out
        ), out

    def test_table_shorthand_with_comment(self) -> None:
        out = _t("-- a comment\ntable my_table;", "postgresql")
        assert '"table"' not in out.lower(), out
        assert re.search(r"(?i)SELECT \*\s+FROM my_table", out), out

    def test_boolean_no_params(self) -> None:
        out = _t("create table t (y bit(4));", "postgresql")
        assert "BOOLEAN(" not in out.upper(), out


class TestWave132Batch:
    """wave 132: RETURN QUERY for SETOF sql-bodies (a scalar RETURN (…)
    is invalid there); PG's ALTER COLUMN SET STORAGE knob (sqlglot's own
    round-trip INVENTS a ``DROP DEFAULT,`` before it) verbatim on PG and
    carried elsewhere; a dotted unnamed %TYPE parameter took the table
    name as the PARAM name."""

    def test_setof_sql_body_return_query(self) -> None:
        src = (
            "create function sillysrf(int) returns setof int as\n"
            "  'values (1),(10),(2),($1)' language sql;"
        )
        out = _t(src, "postgresql")
        assert re.search(r"(?i)RETURN QUERY\s+values", out), out
        assert not re.search(r"(?i)RETURN \(values", out), out

    def test_set_storage_verbatim_pg(self) -> None:
        out = _t("ALTER TABLE t ALTER COLUMN b SET STORAGE plain;", "postgresql")
        assert "DROP DEFAULT" not in out.upper(), out
        assert re.search(r"(?i)SET STORAGE plain", out), out

    @pytest.mark.parametrize("target", ["tsql", "mysql", "oracle"])
    def test_set_storage_degrades_off_pg(self, target: str) -> None:
        r = Transpiler().transpile(
            "ALTER TABLE t ALTER COLUMN b SET STORAGE plain;",
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

    def test_dotted_unnamed_type_param(self) -> None:
        src = (
            "CREATE OR REPLACE FUNCTION f(some_table.a%type) "
            "RETURNS int AS $$\n"
            "begin return p1; end $$ language plpgsql;"
        )
        out = _t(src, "postgresql")
        assert re.search(r"(?i)p1 some_table\.a%TYPE", out), out
        assert "some_table ." not in out, out


class TestWave133Batch:
    """wave 133 — the last discovery tail: FILTER over an ordered-set
    aggregate shredded into a fake WITHINGROUP() call; FETCH RELATIVE -2
    lost its sign; RAISE EXCEPTION USING (leveled, no message) mangled;
    FOREACH comma-target shredded; and three deep-single body shapes
    (nested DECLARE block, a variable named ``return``, CTE feeding
    SELECT INTO) go whole-unit — verbatim on PG, carrier elsewhere."""

    def test_filter_within_group_view(self) -> None:
        out = _t(
            "create view v as select percentile_disc(0.5) within group "
            "(order by t) filter (where h = 1) as px from tk;",
            "postgresql",
        )
        assert "WITHINGROUP(CASE" not in out.upper(), out
        assert re.search(
            r"(?i)WITHIN GROUP \(ORDER BY t\)\s*FILTER\s*\(WHERE", out
        ), out

    def test_fetch_relative_negative(self) -> None:
        src = (
            "create function f() returns setof integer as $$\n"
            "declare c refcursor; x integer;\n"
            "begin\n"
            "  open c scroll for execute 'select f1 from t';\n"
            "  fetch relative -2 from c into x;\n"
            "  close c;\n"
            "end $$ language plpgsql;"
        )
        out = _t(src, "postgresql")
        assert re.search(r"(?i)FETCH RELATIVE -2 FROM c INTO x;", out), out
        assert "INTO ;" not in out, out

    def test_raise_exception_using(self) -> None:
        src = (
            "create function f() returns void as $$\n"
            "begin\n"
            "  raise exception using column = 'c1', constraint = 'x_fk';\n"
            "end $$ language plpgsql;"
        )
        out = _t(src, "postgresql")
        assert "'%', using" not in out.lower(), out
        assert re.search(r"(?i)RAISE EXCEPTION", out), out

    def test_foreach_comma_targets(self) -> None:
        src = (
            "create function f(anyarray) returns void as $$\n"
            "declare x int; y int;\n"
            "begin\n"
            "  foreach x, y in array $1 loop\n"
            "    raise notice '%', x;\n"
            "  end loop;\n"
            "end $$ language plpgsql;"
        )
        out = _t(src, "postgresql")
        assert re.search(r"(?i)FOREACH x, y IN ARRAY p1", out), out
        assert "IN ARRAY ," not in out, out

    def test_nested_declare_block_whole_unit(self) -> None:
        src = (
            "create or replace function shadowtest() returns void as $$\n"
            "declare f1 int;\n"
            "begin\n"
            "  declare f1 int;\n"
            "  begin\n"
            "  end;\n"
            "end $$ language plpgsql;"
        )
        out = _t(src, "postgresql")
        assert out.lower().count("f1 int;\n    f1 int;") == 0, out
        assert re.search(r"(?is)begin\s+declare", out), out

    def test_cte_select_into_whole_unit(self) -> None:
        src = (
            "create function f() returns trigger language plpgsql as $$\n"
            "declare x int;\n"
            "begin\n"
            "  with p as (select a from t)\n"
            "  select a into x from p;\n"
            "  return null;\n"
            "end $$;"
        )
        out = _t(src, "postgresql")
        assert not re.search(r"(?i)\(.*\);\s*SELECT a INTO", out), out
        assert re.search(r"(?is)with p as\s*\(", out.lower()), out


class TestNestedCteArmGate:
    """wave 134: a WITH inside a parenthesized set arm is valid PG (wave
    129 restored the parens) but T-SQL and Oracle only allow CTEs at the
    statement top — the arm shipped invalid (12x of the pg→tsql sweep
    residue). Degrade whole there; PG and MySQL (8+) keep it."""

    _SRC = (
        "with x as (select 1 as a union all "
        "(with z as (select 2 as a) select a from z)) select * from x;"
    )

    @pytest.mark.parametrize("target", ["tsql", "oracle"])
    def test_nested_cte_arm_degrades(self, target: str) -> None:
        r = Transpiler().transpile(self._SRC, source="postgresql", target=target)
        code = [
            ln
            for ln in r.sql.splitlines()
            if ln.strip() and not ln.strip().startswith("--")
        ]
        assert not code, r.sql
        assert r.warnings or r.unsupported, r.sql

    def test_nested_cte_arm_kept_pg(self) -> None:
        out = _t(self._SRC, "postgresql")
        assert re.search(r"(?is)UNION ALL\s*\(WITH z", out), out
        assert "UNIQUE:" not in out, out


class TestBareBooleanConditions:
    """wave 135: PG boolean truthiness under the condition TREE — a bare
    column under AND/OR (or NOT col) shipped bare to T-SQL/Oracle (4145,
    8x of the tsql residue); only the top-of-WHERE case was handled."""

    def test_bare_column_under_and(self) -> None:
        out = _t("select * from t where a = 1 and boolcol;", "tsql")
        assert re.search(r"(?i)AND boolcol <> 0", out), out

    def test_not_bare_column(self) -> None:
        out = _t("select * from t where not boolcol;", "tsql")
        assert re.search(r"(?i)boolcol = 0", out), out
        assert not re.search(r"(?i)NOT boolcol", out), out

    def test_oracle_too(self) -> None:
        out = _t("select * from t where a = 1 and boolcol;", "oracle")
        assert re.search(r"(?i)AND boolcol <> 0", out), out

    def test_real_predicates_untouched(self) -> None:
        out = _t("select * from t where a = 1 and b > 2;", "tsql")
        assert "<> 0" not in out, out


class TestWave136LateralAndDeepCte:
    """wave 136: a LATERAL join with a REAL ON condition has no
    T-SQL/Oracle APPLY form (APPLY takes no ON) and shipped `JOIN
    LATERAL`; and the nested-CTE gate only saw set arms — a WITH inside
    an APPLY/derived subquery still shipped."""

    @pytest.mark.parametrize("target", ["tsql", "oracle"])
    def test_conditioned_lateral_degrades(self, target: str) -> None:
        r = Transpiler().transpile(
            "select count(*) from t1 a, t2 b join lateral "
            "(values(a.x)) ss(x) on b.y = ss.x;",
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

    @pytest.mark.parametrize("target", ["tsql", "oracle"])
    def test_cte_inside_lateral_degrades(self, target: str) -> None:
        r = Transpiler().transpile(
            "select sum(ss.a) from o cross join lateral "
            "(with x(a) as (select o.f as a) select * from x) ss;",
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

    def test_unconditioned_lateral_still_applies_tsql(self) -> None:
        out = _t(
            "select * from t cross join lateral (select t.a + 1 as b) ss;",
            "tsql",
        )
        assert re.search(r"(?i)CROSS APPLY", out), out
        assert "UNIQUE:" not in out, out


class TestCompositeRowValues:
    """wave 137: PG composite/row VALUES in expression position — a row
    constructor as a CASE result (``ELSE (a, b, c)``, 7x on the tsql
    sweep) and the parenthesized whole-row form (``(n.*)``, distinct
    from expanding ``n.*``) — have no spelling off PG. Preserved on PG,
    degraded whole elsewhere."""

    _ROW_SRC = (
        "select f(case when a is null then null else (a, b, c) end) "
        "from (select 1 as a, 3 as b, 'x' as c) s;"
    )

    @pytest.mark.parametrize("target", ["tsql", "mysql", "oracle"])
    def test_row_constructor_degrades(self, target: str) -> None:
        r = Transpiler().transpile(self._ROW_SRC, source="postgresql", target=target)
        code = [
            ln
            for ln in r.sql.splitlines()
            if ln.strip() and not ln.strip().startswith("--")
        ]
        assert not code, r.sql
        assert r.warnings or r.unsupported, r.sql

    def test_row_constructor_kept_pg(self) -> None:
        out = _t(self._ROW_SRC, "postgresql")
        assert "(a, b, c)" in out, out
        assert "UNIQUE:" not in out, out

    def test_expanding_star_untouched(self) -> None:
        out = _t("select n.* from nocols n;", "tsql")
        assert re.search(r"(?i)SELECT n\.\*", out), out
        assert "UNIQUE:" not in out, out


class TestBareWholeRowTriggerRef:
    """wave 138: a BARE whole-row OLD/NEW ('x' || OLD) inside a trigger
    body has no off-PG equivalent (rows are addressed per column there);
    the inlined T-SQL trigger shipped `+ OLD` raw (5x). Qualified refs,
    RETURN NEW/OLD and REFERENCING new|old TABLE stay on their paths."""

    def test_bare_old_degrades_tsql(self) -> None:
        src = (
            "create function tf() returns trigger as $$\n"
            "begin\n"
            "  raise notice 'Got OLD row %, returning NULL', OLD;\n"
            "  return null;\n"
            "end $$ language plpgsql;\n"
            "create trigger tg after update on t "
            "for each row execute function tf();"
        )
        r = Transpiler().transpile(src, source="postgresql", target="tsql")
        code = [
            ln
            for ln in r.sql.splitlines()
            if ln.strip() and not ln.strip().startswith("--")
        ]
        assert not code, r.sql
        assert r.warnings or r.unsupported, r.sql

    def test_qualified_refs_keep_path(self) -> None:
        src = (
            "create function tf2() returns trigger as $$\n"
            "begin\n"
            "  update t2 set c = NEW.c where id = NEW.id;\n"
            "  return new;\n"
            "end $$ language plpgsql;\n"
            "create trigger tg2 after update on t "
            "for each row execute function tf2();"
        )
        out = _t(src, "tsql")
        assert "whole-row OLD/NEW" not in out, out


class TestWave139DecodeAndSetRole:
    """wave 139: PG's binary DECODE(text, 'hex') is not Oracle's
    conditional DECODE (that becomes CASE) — faithful hex mappings exist
    everywhere; and SET ROLE exists on PG/MySQL/Oracle but not T-SQL."""

    def test_decode_hex_tsql(self) -> None:
        out = _t("insert into bt values (decode('ff', 'hex'));", "tsql")
        assert re.search(r"(?i)CONVERT\(VARBINARY\(MAX\), 'ff', 2\)", out), out

    def test_decode_hex_oracle(self) -> None:
        out = _t("insert into bt values (decode('ff', 'hex'));", "oracle")
        assert re.search(r"(?i)HEXTORAW\('ff'\)", out), out

    def test_decode_hex_mysql(self) -> None:
        out = _t("insert into bt values (decode('ff', 'hex'));", "mysql")
        assert re.search(r"(?i)UNHEX\('ff'\)", out), out

    def test_set_role_degrades_tsql(self) -> None:
        r = Transpiler().transpile("set role ru;", source="postgresql", target="tsql")
        code = [
            ln
            for ln in r.sql.splitlines()
            if ln.strip() and not ln.strip().startswith("--")
        ]
        assert not code, r.sql
        assert r.warnings or r.unsupported, r.sql

    def test_set_role_kept_mysql(self) -> None:
        out = _t("set role ru;", "mysql")
        assert re.search(r"(?i)set role ru", out), out
        assert "UNIQUE:" not in out, out


class TestWave140GroupConcatAndDeleteAlias:
    """wave 140: string_agg(x, NULL) shipped a nonexistent GROUP_CONCAT
    on T-SQL (NULL separator = concatenate bare) and an EXPRESSION
    separator fell through the same hole; and T-SQL spells an aliased
    delete ``DELETE dt FROM t dt`` (``DELETE FROM t dt`` is an error)."""

    def test_string_agg_null_separator_tsql(self) -> None:
        out = _t("select string_agg(v, null) from t;", "tsql")
        assert "GROUP_CONCAT" not in out.upper(), out
        assert re.search(r"(?i)STRING_AGG\(v, ''\)", out), out

    def test_string_agg_expr_separator_tsql(self) -> None:
        out = _t("select string_agg(v, sep_col) from t;", "tsql")
        assert "GROUP_CONCAT" not in out.upper(), out
        assert re.search(r"(?i)STRING_AGG\(v, sep_col\)", out), out

    def test_delete_alias_tsql(self) -> None:
        out = _t("delete from delete_test dt where dt.a > 75;", "tsql")
        assert re.search(r"(?i)DELETE dt FROM delete_test dt", out), out

    def test_delete_alias_pg_unchanged(self) -> None:
        out = _t("delete from delete_test dt where dt.a > 75;", "postgresql")
        assert re.search(r"(?i)DELETE FROM delete_test dt", out), out


class TestBooleanOpInSelectList:
    """wave 141: a boolean AND/OR in VALUE position wrapped into a CASE
    whose condition kept the BARE columns (``CASE WHEN b1 AND a3`` —
    4145, 6x): the wrap must route through _emit_condition, which
    comparisonizes truthy operands."""

    def test_and_in_select_list_tsql(self) -> None:
        out = _t("select (b1 and a3) as b3 from t;", "tsql")
        assert re.search(r"(?i)WHEN b1 <> 0 AND a3 <> 0 THEN 1", out), out

    def test_or_in_select_list_oracle(self) -> None:
        out = _t("select (b1 or a3) as b3 from t;", "oracle")
        assert re.search(r"(?i)WHEN b1 <> 0 OR a3 <> 0 THEN 1", out), out

    def test_comparison_wrap_unchanged(self) -> None:
        out = _t("select a > 3 as flag from t;", "tsql")
        assert re.search(r"(?i)CASE WHEN a > 3 THEN 1 WHEN a <= 3 THEN 0", out), out


class TestUnaryPredicateInSelectList:
    """wave 141b: unary predicates in VALUE position — ``(id IS NOT
    NULL) AS a3`` shipped as ``NOT (id IS NULL) AS a3`` (4145). Two-valued
    predicates get ELSE 0; NOT keeps the tri-state two-WHEN form."""

    def test_is_not_null_value_tsql(self) -> None:
        out = _t("select (id is not null) as a3 from t;", "tsql")
        # Any CASE wrap is valid; the bare predicate-as-value is what 4145s.
        assert re.search(r"(?i)CASE WHEN .*id IS NULL.* THEN 1", out), out
        assert not re.search(r"(?im)^\s*SELECT NOT \(", out), out

    def test_exists_value_oracle(self) -> None:
        out = _t("select exists(select 1 from u) as e from t;", "oracle")
        assert re.search(r"(?i)CASE WHEN EXISTS", out), out


class TestVoidOutFunctionBecomesProc:
    """wave 142: a PG void function with OUT/INOUT parameters cannot be a
    T-SQL FUNCTION (error 181: no OUTPUT option there) — it IS a
    procedure on that engine."""

    def test_void_out_function_procs_tsql(self) -> None:
        src = (
            "create function f1(inout i int) returns void as $$\n"
            "begin\n"
            "  i := i + 1;\n"
            "end $$ language plpgsql;"
        )
        out = _t(src, "tsql")
        assert re.search(r"(?i)CREATE PROCEDURE f1", out), out
        assert "RETURNS" not in out.upper(), out
        assert re.search(r"(?i)@i int OUTPUT", out), out

    def test_void_no_out_stays_function(self) -> None:
        src = (
            "create function f2(i int) returns void as $$\n"
            "begin\n"
            "  perform pg_sleep(0);\n"
            "end $$ language plpgsql;"
        )
        out = _t(src, "tsql")
        assert re.search(r"(?i)CREATE FUNCTION f2|CREATE PROCEDURE f2", out), out


class TestEStringsInBodies:
    """wave 143: PG E-strings inside procedural bodies token-split into a
    bare identifier ``E`` plus the literal (``PRINT E 'foo\\bar'`` — name
    E not permitted, 3x). The lexer now decodes the C-style escapes into
    a plain single-quoted literal every target understands."""

    def test_estring_in_function_body(self) -> None:
        src = (
            "create function strtest() returns text as $$\n"
            "begin\n"
            "  raise notice '%', E'foo\\\\bar';\n"
            "  return E'foo\\\\bar';\n"
            "end $$ language plpgsql;"
        )
        out = _t(src, "tsql")
        assert not re.search(r"(?i)\bE\s+'", out), out
        assert "foo\\bar" in out, out


class TestWave144TupleColumnAndTempFn:
    """wave 144: a row tuple AS a select column (lateral ``SELECT (a,
    b)``) joins the composite gate; and a T-SQL FUNCTION cannot access
    temporary tables (2772) — a body creating one degrades whole."""

    @pytest.mark.parametrize("target", ["tsql", "oracle"])
    def test_tuple_select_column_degrades(self, target: str) -> None:
        r = Transpiler().transpile(
            "select * from x cross join lateral (select (x.q1, x.q2)) v;",
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

    def test_temp_table_in_function_degrades_tsql(self) -> None:
        src = (
            "create function tf() returns int as $$\n"
            "begin\n"
            "  create temp table tt(a int);\n"
            "  return 1;\n"
            "end $$ language plpgsql;"
        )
        r = Transpiler().transpile(src, source="postgresql", target="tsql")
        code = [
            ln
            for ln in r.sql.splitlines()
            if ln.strip() and not ln.strip().startswith("--")
        ]
        assert not code, r.sql
        assert r.warnings or r.unsupported, r.sql

    def test_plain_function_unaffected_tsql(self) -> None:
        src = (
            "create function tf2() returns int as $$\n"
            "begin return 1; end $$ language plpgsql;"
        )
        out = _t(src, "tsql")
        assert re.search(r"(?i)CREATE FUNCTION tf2", out), out


class TestWave145MysqlAggForms:
    """wave 145: MySQL-impossible aggregate forms — an EXPRESSION
    separator (SEPARATOR takes a literal only; the comma form
    concatenates it onto every value, audit S1-8) and DISTINCT inside a
    non-builtin aggregate (hard 1064). Both degrade whole on mysql."""

    def test_expr_separator_degrades_mysql(self) -> None:
        r = Transpiler().transpile(
            "select string_agg(v, decode('ee','hex')) from t;",
            source="postgresql",
            target="mysql",
        )
        code = [
            ln
            for ln in r.sql.splitlines()
            if ln.strip() and not ln.strip().startswith("--")
        ]
        assert not code, r.sql
        assert r.warnings or r.unsupported, r.sql

    def test_distinct_custom_agg_degrades_mysql(self) -> None:
        r = Transpiler().transpile(
            "select my_avg(distinct one) from t;",
            source="postgresql",
            target="mysql",
        )
        code = [
            ln
            for ln in r.sql.splitlines()
            if ln.strip() and not ln.strip().startswith("--")
        ]
        assert not code, r.sql
        assert r.warnings or r.unsupported, r.sql

    def test_count_distinct_untouched_mysql(self) -> None:
        out = _t("select count(distinct a) from t;", "mysql")
        assert re.search(r"(?i)COUNT\(DISTINCT a\)", out), out
        assert "UNIQUE:" not in out, out

    def test_literal_separator_untouched_mysql(self) -> None:
        out = _t("select string_agg(v, ',') from t;", "mysql")
        assert re.search(r"(?i)GROUP_CONCAT\(v SEPARATOR ','\)", out), out


class TestMysqlProceduralCastTypes:
    """wave 146: MySQL CAST accepts a fixed target set — the DML pipeline
    maps foreign spellings via _CAST_TYPE_MAP, but the procedural
    expression text shipped them raw (``RETURN CAST(p1 AS text)`` — hard
    1064). Dual-pipeline mirror."""

    def test_cast_text_in_body(self) -> None:
        src = (
            "create function volfoo(p1 text) returns text as $$\n"
            "begin\n"
            "  return cast(p1 as text);\n"
            "end $$ language plpgsql;"
        )
        out = _t(src, "mysql")
        assert not re.search(r"(?i)AS\s+text\s*\)", out), out
        assert re.search(r"(?i)CAST\(\s*p1 AS CHAR\s*\)", out), out

    def test_cast_int_in_body(self) -> None:
        src = (
            "create function f(x text) returns int as $$\n"
            "begin\n"
            "  return cast(x as integer) + 1;\n"
            "end $$ language plpgsql;"
        )
        out = _t(src, "mysql")
        assert re.search(r"(?i)CAST\(\s*x AS SIGNED\s*\)", out), out


class TestMysqlNonConstLag:
    """wave 147: MySQL requires a CONSTANT LAG/LEAD offset — a column
    offset (``LAG(ten, four)``) raises 1327 (3x). Degrades whole on
    mysql; constant offsets and other targets keep their path."""

    def test_column_offset_degrades_mysql(self) -> None:
        r = Transpiler().transpile(
            "select lag(ten, four) over (order by ten) from t;",
            source="postgresql",
            target="mysql",
        )
        code = [
            ln
            for ln in r.sql.splitlines()
            if ln.strip() and not ln.strip().startswith("--")
        ]
        assert not code, r.sql
        assert r.warnings or r.unsupported, r.sql

    def test_constant_offset_kept_mysql(self) -> None:
        out = _t("select lag(ten, 2) over (order by ten) from t;", "mysql")
        assert re.search(r"(?i)LAG\(ten, 2\)", out), out
        assert "UNIQUE:" not in out, out

    def test_column_offset_kept_pg(self) -> None:
        out = _t("select lag(ten, four) over (order by ten) from t;", "postgresql")
        assert re.search(r"(?i)LAG\(ten, four\)", out), out


class TestMysqlDmlCastText:
    """wave 148: the DML cast map covered VARCHAR/NVARCHAR→CHAR but not
    TEXT — PG's habitual cast target shipped ``CAST(x AS TEXT)`` raw on
    MySQL (1064). The wave-146 procedural mirror had it; the DML side
    lagged (dual-pipeline symmetry, both directions this time)."""

    def test_cast_text_in_view_mysql(self) -> None:
        out = _t(
            "create view zv1 as select cast('dummy' as text) as junk from zt1;",
            "mysql",
        )
        assert "AS TEXT" not in out.upper(), out
        assert re.search(r"(?i)CAST\('dummy' AS CHAR\)", out), out


class TestPgSourceProceduralTypeMaps:
    """wave 149: the PG-source PROCEDURAL_TYPE_MAPS never existed — the
    internal aliases (int4/int8/float8…) and PG-only types shipped raw
    into every target's routine signatures."""

    def test_int_aliases_mysql(self) -> None:
        src = (
            "create function g1(x int4) returns int8 as $$\n"
            "begin return x; end $$ language plpgsql;"
        )
        out = _t(src, "mysql")
        assert "int4" not in out.lower(), out
        assert re.search(r"(?i)RETURNS BIGINT", out), out

    def test_float8_tsql(self) -> None:
        src = (
            "create function g2(x float8) returns float8 as $$\n"
            "begin return x; end $$ language plpgsql;"
        )
        out = _t(src, "tsql")
        assert "float8" not in out.lower(), out
        assert re.search(r"(?i)RETURNS FLOAT", out), out

    def test_bytea_oracle(self) -> None:
        src = (
            "create function g3(x bytea) returns bytea as $$\n"
            "begin return x; end $$ language plpgsql;"
        )
        out = _t(src, "oracle")
        assert "bytea" not in out.lower(), out
        assert re.search(r"(?i)RETURN BLOB", out), out


class TestOracleBareStarWithSiblings:
    """wave 150: Oracle rejects a BARE ``*`` alongside other select items
    (ORA-00923, 13x) — it must be qualified with the FROM relation."""

    def test_star_with_sibling_oracle(self) -> None:
        out = _t(
            "create view zv1 as select *, cast('d' as text) as junk from zt1;",
            "oracle",
        )
        assert re.search(r"(?i)SELECT zt1\.\*,", out), out

    def test_lone_star_untouched_oracle(self) -> None:
        out = _t("select * from t;", "oracle")
        assert re.search(r"(?i)SELECT \*", out), out


class TestTableRowtypeParams:
    """wave 151: every PG table name is also a ROWTYPE — a routine
    parameter typed with one (``function f(t onek)``) is as
    untranslatable off PG as an explicit composite; table names now join
    the composite-type harvest."""

    _SRC = (
        "create table onek (a int, b text);\n"
        "create function f_field_select(t onek) returns int as $$\n"
        "begin return t.a; end $$ language plpgsql;"
    )

    @pytest.mark.parametrize("target", ["mysql", "tsql", "oracle"])
    def test_rowtype_param_degrades(self, target: str) -> None:
        r = Transpiler().transpile(self._SRC, source="postgresql", target=target)
        assert not re.search(r"(?im)^\s*CREATE (OR REPLACE )?FUNCTION", r.sql), r.sql
        assert r.warnings or r.unsupported, r.sql

    def test_rowtype_param_kept_pg(self) -> None:
        out = _t(self._SRC, "postgresql")
        assert re.search(r"(?i)t onek", out), out
        assert "UNIQUE:" not in out.split("create function")[0], out


class TestUnknownParamType:
    """wave 152: a routine parameter typed with a name that resolves
    NOWHERE — not a known scalar, domain, composite or %TYPE — is a
    rowtype/custom type defined OUTSIDE the script (pg_regress setup
    tables like ``onek``); it cannot exist on the target either."""

    @pytest.mark.parametrize("target", ["mysql", "tsql", "oracle"])
    def test_external_rowtype_param_degrades(self, target: str) -> None:
        src = (
            "create function f_field_select(t onek) returns int as $$\n"
            "begin return t.a; end $$ language plpgsql;"
        )
        r = Transpiler().transpile(src, source="postgresql", target=target)
        assert not re.search(r"(?im)^\s*CREATE (OR REPLACE )?FUNCTION", r.sql), r.sql
        assert r.warnings or r.unsupported, r.sql

    def test_known_scalars_unaffected(self) -> None:
        src = (
            "create function g(a int, b text, c numeric(10,2)) returns int as $$\n"
            "begin return a; end $$ language plpgsql;"
        )
        out = _t(src, "mysql")
        assert re.search(r"(?i)CREATE FUNCTION g", out), out
        assert "unresolvable" not in out, out


class TestRowCompareAny:
    """wave 153: a row tuple compared with ANY/ALL over a subquery ships
    as a source-spelled RawSQL fragment (RANDOM() unmapped inside) — no
    verified spelling off PG; joins the composite gate."""

    @pytest.mark.parametrize("target", ["mysql", "tsql", "oracle"])
    def test_row_any_degrades(self, target: str) -> None:
        r = Transpiler().transpile(
            "select 1 from t b where (b.u, random() > 0) = any "
            "(select q1, random() > 0 from c);",
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

    def test_scalar_any_untouched(self) -> None:
        out = _t("select 1 from t where x = any (select q1 from c);", "mysql")
        assert "UNIQUE:" not in out, out


class TestWave154RepeatConcat:
    """wave 154 (mysql-corpus front): MySQL's REPEAT is T-SQL REPLICATE
    (it shipped dbo.-qualified as a fake UDF), and a single-argument
    CONCAT — valid MySQL/PG — needs 2+ args on T-SQL/Oracle: it IS its
    argument."""

    def test_repeat_replicate_tsql(self) -> None:
        out = _t2("select repeat('ab', 3);", "mysql", "tsql")
        assert re.search(r"(?i)REPLICATE\('ab', 3\)", out), out
        assert "dbo.REPEAT" not in out, out

    def test_one_arg_concat_tsql(self) -> None:
        out = _t2("select concat(a) from t;", "mysql", "tsql")
        assert "CONCAT" not in out.upper(), out
        assert re.search(r"(?i)SELECT a\s+FROM t", out), out

    def test_two_arg_concat_untouched(self) -> None:
        out = _t2("select concat(a, b) from t;", "mysql", "tsql")
        assert re.search(r"(?i)CONCAT\(a, b\)", out), out

    def test_repeat_kept_pg(self) -> None:
        out = _t2("select repeat('ab', 3);", "mysql", "postgresql")
        assert re.search(r"(?i)REPEAT\('ab', 3\)", out), out


class TestWave155ConditionLiterals:
    """wave 155 (mysql-corpus): MySQL treats a bare integer as a truth
    value in IF()/searched-CASE conditions; T-SQL/Oracle raise 4145 —
    the literal must become a real comparison (``1 <> 0``)."""

    def test_iif_integer_condition_tsql(self) -> None:
        out = _t2("select if(1, 'a', 'b');", "mysql", "tsql")
        assert re.search(r"(?i)IIF\(1 <> 0,", out), out

    def test_case_when_integer_tsql(self) -> None:
        out = _t2("select case when 1 then 'a' else 'b' end;", "mysql", "tsql")
        assert re.search(r"(?i)WHEN 1 <> 0 THEN", out), out

    def test_case_when_integer_oracle(self) -> None:
        out = _t2(
            "select case when 1 then 'a' else 'b' end from dual;",
            "mysql",
            "oracle",
        )
        assert re.search(r"(?i)WHEN 1 <> 0 THEN", out), out

    def test_if_integer_kept_mysql(self) -> None:
        out = _t2("select if(1, 'a', 'b');", "mysql", "mysql")
        assert re.search(r"(?i)IF\(1,", out), out

    def test_real_condition_untouched(self) -> None:
        out = _t2(
            "select case when a = 1 then 'a' else 'b' end from t;",
            "mysql",
            "tsql",
        )
        assert re.search(r"(?i)WHEN a = 1 THEN", out), out


class TestWave156LabeledBodyNoBegin:
    """wave 156 (mysql-corpus): a MySQL routine body that is a single
    LABELED loop (``proc c(x int) hmm: while … end while hmm``) — or a
    bare REPEAT/LOOP — has no BEGIN; the declare loop shredded it into
    garbage ``DECLARE @hmm :;`` statements."""

    _LOOP = (
        "create procedure c(x int)\n"
        "hmm: while x > 0 do\n"
        "  insert into t1 values ('c', x);\n"
        "  set x = x - 1;\n"
        "  iterate hmm;\n"
        "end while hmm"
    )

    def test_labeled_while_tsql_not_shredded(self) -> None:
        out = _t2(self._LOOP, "mysql", "tsql")
        assert "DECLARE @hmm" not in out, out
        # Parsed, not the raw-fallback text: parameters got the @ sigil
        # and ITERATE became a bare CONTINUE (T-SQL has no labels).
        assert re.search(r"(?i)WHILE @x > 0", out), out
        assert re.search(r"(?i)INSERT INTO t1", out), out
        assert re.search(r"(?i)CONTINUE;", out), out
        assert "iterate" not in out.lower(), out

    def test_labeled_while_pg(self) -> None:
        out = _t2(self._LOOP, "mysql", "postgresql")
        assert "DECLARE @hmm" not in out, out
        assert re.search(r"(?i)WHILE x > 0", out), out
        assert re.search(r"(?i)CONTINUE", out), out

    def test_labeled_while_mysql_roundtrip(self) -> None:
        out = _t2(self._LOOP, "mysql", "mysql")
        assert re.search(r"(?i)ITERATE hmm;", out), out

    def test_bare_repeat_body_tsql(self) -> None:
        sql = (
            "create procedure b2(x int)\n"
            "repeat\n"
            "  insert into t1 values ('b2', x);\n"
            "  set x = x - 1;\n"
            "until x = 0 end repeat"
        )
        out = _t2(sql, "mysql", "tsql")
        assert "DECLARE @repeat" not in out, out
        assert re.search(r"(?i)INSERT INTO t1", out), out


class TestWave157HavingAliasStringAggDistinct:
    """wave 157 (mysql-corpus): MySQL lets HAVING reference a select
    alias — T-SQL/PG/Oracle need the expression inlined. And
    STRING_AGG(DISTINCT …) has no T-SQL spelling at all: honest
    carrier, never invalid output."""

    def test_having_alias_inlined_tsql(self) -> None:
        out = _t2(
            "select max(col1) as a from t1 group by col2 having a like '%';",
            "mysql",
            "tsql",
        )
        assert re.search(r"(?i)HAVING MAX\(col1\) LIKE '%'", out), out

    def test_having_alias_inlined_pg(self) -> None:
        out = _t2(
            "select max(col1) as a from t1 group by col2 having a > 1;",
            "mysql",
            "postgresql",
        )
        assert re.search(r"(?i)HAVING MAX\(col1\) > 1", out), out

    def test_having_alias_kept_mysql(self) -> None:
        out = _t2(
            "select max(col1) as a from t1 group by col2 having a > 1;",
            "mysql",
            "mysql",
        )
        assert re.search(r"(?i)HAVING a > 1", out), out

    def test_having_real_column_untouched(self) -> None:
        out = _t2(
            "select col2, max(col1) from t1 group by col2 having col2 > 1;",
            "mysql",
            "tsql",
        )
        assert re.search(r"(?i)HAVING col2 > 1", out), out

    def test_string_agg_distinct_carrier_tsql(self) -> None:
        out = _t2(
            "select group_concat(distinct col1) from t1 group by col2;",
            "mysql",
            "tsql",
        )
        assert "UNIQUE:" in out, out
        assert "STRING_AGG(DISTINCT" not in out.upper(), out

    def test_string_agg_distinct_kept_pg(self) -> None:
        out = _t2(
            "select group_concat(distinct col1) from t1 group by col2;",
            "mysql",
            "postgresql",
        )
        assert re.search(r"(?i)STRING_AGG\(DISTINCT col1", out), out


class TestWave158LabeledBeginBlock:
    """wave 158 (mysql-corpus): MySQL labels BEGIN blocks too —
    ``proc i(x int) foo: begin … leave foo; … end foo``. The label
    shredded into ``DECLARE @foo :;`` and LEAVE became a bare BREAK
    (invalid outside a loop); a LEAVE of the body's own label is
    RETURN."""

    _PROC = (
        "create procedure i(x int)\n"
        "foo:\n"
        "begin\n"
        "  if x = 0 then\n"
        "    leave foo;\n"
        "  end if;\n"
        "  insert into t1 values ('i', x);\n"
        "end foo"
    )

    def test_labeled_body_block_tsql(self) -> None:
        out = _t2(self._PROC, "mysql", "tsql")
        assert "DECLARE @foo" not in out, out
        assert re.search(r"(?i)IF @x = 0", out), out
        assert re.search(r"(?i)RETURN;", out), out
        assert "BREAK" not in out.upper(), out
        assert re.search(r"(?i)INSERT INTO t1", out), out

    def test_labeled_empty_block_body(self) -> None:
        out = _t2(
            "create procedure bug_1()\nlabel1: begin end label1",
            "mysql",
            "tsql",
        )
        assert "DECLARE @label1" not in out, out
        assert ":" not in out.replace("::", ""), out

    def test_nested_labeled_blocks(self) -> None:
        sql = (
            "create procedure bug_2()\n"
            "begin\n"
            "  label: begin end;\n"
            "  label1: begin end;\n"
            "end"
        )
        out = _t2(sql, "mysql", "tsql")
        assert "DECLARE @label" not in out, out


class TestWave159MultiDeclareMultiSet:
    """wave 159 (mysql-corpus): MySQL declares several variables with
    one type (``DECLARE z1, z2 int;``) and assigns several in one SET
    (``SET a = 1, b = 2;``) — both shredded/shipped invalid on T-SQL."""

    def test_multi_declare_tsql(self) -> None:
        sql = (
            "create procedure locset(x char(16), y int)\n"
            "begin\n"
            "  declare z1, z2 int;\n"
            "  set z1 = y;\n"
            "  set z2 = z1 + 2;\n"
            "  insert into t1 values (x, z2);\n"
            "end"
        )
        out = _t2(sql, "mysql", "tsql")
        assert re.search(r"(?i)DECLARE @z1 int", out), out
        assert re.search(r"(?i)DECLARE @z2 int", out), out
        assert re.search(r"(?i)SET @z2 = @z1 \+ 2", out), out
        assert "," not in out.split("DECLARE @z1")[1].split(";")[0], out

    def test_multi_set_split_tsql(self) -> None:
        sql = (
            "create procedure zap(x int)\n"
            "begin\n"
            "  declare z int;\n"
            "  set z = x + 1, x = z - 1;\n"
            "end"
        )
        out = _t2(sql, "mysql", "tsql")
        assert re.search(r"(?i)SET @z = @x \+ 1;", out), out
        assert re.search(r"(?i)SET @x = @z - 1;", out), out

    def test_multi_declare_default_mysql_roundtrip(self) -> None:
        sql = (
            "create procedure p1()\n"
            "begin\n"
            "  declare a, b int default 3;\n"
            "  set a = b;\n"
            "end"
        )
        out = _t2(sql, "mysql", "mysql")
        assert re.search(r"(?i)DECLARE a int DEFAULT 3", out), out
        assert re.search(r"(?i)DECLARE b int DEFAULT 3", out), out


class TestWave160NotParenTruthiness:
    """wave 160 (mysql-corpus): MySQL truthiness under NOT — bare
    columns inside ``NOT (a AND b)`` and a parenthesized predicate
    compared to 0/1 (``NOT (c2 IS NULL) = 1``) are both error 4145 on
    T-SQL."""

    def test_not_paren_bare_columns_tsql(self) -> None:
        out = _t2("select * from t1 where not (a and b);", "mysql", "tsql")
        assert re.search(r"(?i)NOT \(a <> 0 AND b <> 0\)", out), out

    def test_predicate_eq_one_tsql(self) -> None:
        out = _t2("select * from t1 where not (c2 is null) = 1;", "mysql", "tsql")
        assert re.search(r"(?i)NOT \(c2 IS NULL\)", out), out
        assert "= 1" not in out, out

    def test_predicate_eq_zero_tsql(self) -> None:
        out = _t2("select * from t1 where not (c2 is null) = 0;", "mysql", "tsql")
        assert re.search(r"(?i)NOT \(NOT \(c2 IS NULL\)\)", out), out

    def test_real_comparison_untouched(self) -> None:
        out = _t2("select * from t1 where not (a = 1 and b = 2);", "mysql", "tsql")
        assert re.search(r"(?i)NOT \(a = 1 AND b = 2\)", out), out

    def test_mysql_keeps_truthiness(self) -> None:
        out = _t2("select * from t1 where not (a and b);", "mysql", "mysql")
        assert re.search(r"(?i)NOT \(a AND b\)", out), out


class TestWave161CoalesceOneArgDistinctWrapper:
    """wave 161 (mysql-corpus): a single-argument COALESCE is error
    1088 on T-SQL — it IS its argument. And an aggregate's DISTINCT
    wrapper (Count(this=Distinct(…))) converted to a verbatim RawSQL
    argument, so inner expressions bypassed every function mapping."""

    def test_one_arg_coalesce_tsql(self) -> None:
        out = _t2("select coalesce(1), coalesce(a, b) from t1;", "mysql", "tsql")
        assert re.search(r"(?i)SELECT 1, COALESCE\(a, b\)", out), out

    def test_one_arg_coalesce_kept_pg(self) -> None:
        out = _t2("select coalesce(1) from t1;", "mysql", "postgresql")
        assert re.search(r"(?i)COALESCE\(1\)", out), out

    def test_count_distinct_inner_repeat_mapped(self) -> None:
        out = _t2("select count(distinct repeat(65, 3)) from t2;", "mysql", "tsql")
        assert re.search(r"(?i)COUNT\(DISTINCT REPLICATE\(65, 3\)\)", out), out

    def test_count_distinct_plain_column(self) -> None:
        out = _t2("select count(distinct a) from t2;", "mysql", "tsql")
        assert re.search(r"(?i)COUNT\(DISTINCT a\)", out), out


class TestWave162AdddateSqlMode:
    """wave 162 (mysql-corpus): ADDDATE/SUBDATE are DATE_ADD/DATE_SUB
    aliases sqlglot leaves anonymous — they shipped dbo.-qualified with
    a raw INTERVAL argument. And ``SET sql_mode = …`` inside a routine
    is a session option, not a variable — it shipped a fake
    ``SET @sql_mode`` local on T-SQL."""

    def test_adddate_interval_tsql(self) -> None:
        out = _t2("select adddate('2001-01-01', interval 1 day);", "mysql", "tsql")
        assert re.search(r"(?i)DATEADD\(DAY, 1, '2001-01-01'\)", out), out
        assert "dbo." not in out, out

    def test_subdate_interval_pg(self) -> None:
        out = _t2(
            "select subdate('2001-01-01', interval 1 day);",
            "mysql",
            "postgresql",
        )
        assert "dbo." not in out and "SUBDATE" not in out.upper(), out
        assert re.search(r"(?i)INTERVAL", out), out

    def test_adddate_bare_days(self) -> None:
        out = _t2("select adddate('2001-01-01', 31);", "mysql", "tsql")
        assert re.search(r"(?i)DATEADD\(DAY, 31, '2001-01-01'\)", out), out

    def test_set_sql_mode_carrier_tsql(self) -> None:
        out = _t2(
            "create procedure p() begin set sql_mode = 'TRADITIONAL';" " select 1; end",
            "mysql",
            "tsql",
        )
        assert "UNIQUE:" in out and "SQL_MODE" in out.upper(), out
        assert "SET @sql_mode" not in out, out

    def test_set_sql_mode_kept_mysql(self) -> None:
        out = _t2(
            "create procedure p() begin set sql_mode = 'TRADITIONAL';" " select 1; end",
            "mysql",
            "mysql",
        )
        assert re.search(r"(?i)SET sql_mode = 'TRADITIONAL'", out), out


class TestWave163CharsetCastSubqueryOrder:
    """wave 163 (mysql-corpus): sqlglot collapses ``CAST(x AS CHAR
    CHARACTER SET cs)`` to a CHARACTER_SET type — it emitted a
    nonexistent ``CAST(… AS CHARACTER_SET)`` everywhere (silent
    corruption of the CHAR base). And a set-op subquery hangs its
    ORDER BY on the LAST arm, dodging the existing strip."""

    def test_charset_cast_tsql(self) -> None:
        out = _t2(
            "select cast('bar' as char character set utf8mb3);",
            "mysql",
            "tsql",
        )
        assert re.search(r"(?i)CAST\('bar' AS CHAR\)", out), out
        assert "CHARACTER_SET" not in out.upper(), out

    def test_charset_cast_kept_mysql(self) -> None:
        out = _t2(
            "select cast('bar' as char character set utf8mb3);",
            "mysql",
            "mysql",
        )
        assert re.search(r"(?i)CHAR CHARACTER SET utf8mb3", out), out

    def test_setop_subquery_order_stripped_tsql(self) -> None:
        out = _t2(
            "select (select 1 as foo union select 2 order by foo asc) as x" " from t1;",
            "mysql",
            "tsql",
        )
        assert "ORDER BY" not in out.upper(), out
        assert re.search(r"(?i)UNION\s+SELECT 2", out), out

    def test_ordered_subquery_with_limit_keeps_order(self) -> None:
        out = _t2(
            "select (select a from t2 order by a limit 1) from t1;",
            "mysql",
            "tsql",
        )
        assert "ORDER BY" in out.upper(), out


class TestWave164AssignOpSelectLimit:
    """wave 164 (mysql-corpus): MySQL's ``SET x := 1`` (walrus form)
    left the ``:=`` in the value (``SET @x = := 1``), and a SELECT
    INTO's trailing ``LIMIT n`` survived verbatim in the T-SQL
    SELECT-assign, where the spelling is TOP."""

    def test_set_walrus_tsql(self) -> None:
        out = _t2("create procedure p() begin set x := 1; end", "mysql", "tsql")
        assert re.search(r"(?i)SET @x = 1;", out), out
        assert ":=" not in out, out

    def test_select_into_limit_becomes_top(self) -> None:
        out = _t2(
            "create procedure q(x char(16)) begin"
            " select id into x from t1 limit 1; end",
            "mysql",
            "tsql",
        )
        assert re.search(r"(?i)SELECT TOP 1 @x = id\b", out), out
        assert "limit" not in out.lower(), out

    def test_select_into_no_limit_untouched(self) -> None:
        out = _t2(
            "create procedure r(x int) begin" " select max(id) into x from t1; end",
            "mysql",
            "tsql",
        )
        assert re.search(r"(?i)SELECT @x = max\s*\(\s*id\s*\)", out), out
        assert "TOP" not in out.upper(), out

    def test_select_into_limit_kept_pg(self) -> None:
        out = _t2(
            "create procedure q(x char(16)) begin"
            " select id into x from t1 limit 1; end",
            "mysql",
            "postgresql",
        )
        assert re.search(r"(?i)LIMIT 1", out), out


class TestWave165IntervalIndexFunction:
    """wave 165 (mysql-corpus): MySQL's INTERVAL(x, v1, v2, …) index
    function (position of the last threshold ≤ x, −1 for NULL) parsed
    as an Interval literal and shipped ``INTERVAL ((x, v1, …))`` —
    invalid everywhere. Targets without it get the CASE chain."""

    def test_interval_fn_case_chain_tsql(self) -> None:
        out = _t2("select interval(qty, 2, 3) from t1;", "mysql", "tsql")
        up = " ".join(out.upper().split())
        assert "CASE WHEN QTY IS NULL THEN -1" in up, out
        assert "WHEN QTY < 2 THEN 0" in up, out
        assert "WHEN QTY < 3 THEN 1" in up, out
        assert "ELSE 2 END" in up, out

    def test_interval_fn_kept_mysql(self) -> None:
        out = _t2("select interval(qty, 2, 3) from t1;", "mysql", "mysql")
        assert re.search(r"(?i)INTERVAL\(qty, 2, 3\)", out), out

    def test_interval_literal_untouched(self) -> None:
        out = _t2("select date_add('2001-01-01', interval 1 day);", "mysql", "tsql")
        assert re.search(r"(?i)DATEADD\(DAY, 1, '2001-01-01'\)", out), out


class TestWave166PrefixIndexFlush:
    """wave 166 (mysql-corpus): MySQL prefix indexes (``PRIMARY KEY
    (a, b(132))``) have no cross-engine spelling — the length is
    stripped (whole-column keys accept every row the prefix key
    accepted). And FLUSH/RESET/PURGE admin statements shredded into
    ``flush AS query`` via the embedded-DML fallback — now honest
    carriers."""

    def test_prefix_pk_stripped_tsql(self) -> None:
        out = _t2(
            "create temporary table t2 (a int, b varchar(200) not null,"
            " primary key (a, b(132)));",
            "mysql",
            "tsql",
        )
        assert "b(132)" not in out and "b (132)" not in out, out
        assert re.search(r"(?i)PRIMARY KEY\s*\(a, b\)", out), out

    def test_prefix_pk_kept_mysql(self) -> None:
        out = _t2(
            "create temporary table t2 (a int, b varchar(200) not null,"
            " primary key (a, b(132)));",
            "mysql",
            "mysql",
        )
        assert re.search(r"(?i)b\s*\(132\)", out), out

    def test_flush_carrier_tsql(self) -> None:
        out = _t2(
            "create procedure p() begin update t3 set a = 1;" " flush query cache; end",
            "mysql",
            "tsql",
        )
        assert "UNIQUE:" in out and "FLUSH" in out.upper(), out
        assert "flush AS" not in out, out
        assert re.search(r"(?i)UPDATE t3 SET a = 1", out), out

    def test_flush_kept_mysql(self) -> None:
        out = _t2(
            "create procedure p() begin update t3 set a = 1;" " flush query cache; end",
            "mysql",
            "mysql",
        )
        assert re.search(r"(?i)flush query cache", out), out
        assert "UNIQUE:" not in out, out


class TestWave167MysqlSystemVars:
    """wave 167 (mysql-corpus): MySQL @@system variables
    (``@@server_id``) shipped raw — T-SQL rejects an unknown @@name
    (error 137). The user-variable whole-routine degrade now covers
    them."""

    def test_sysvar_function_carrier_tsql(self) -> None:
        out = _t2(
            "create function f1() returns int begin return @@server_id; end",
            "mysql",
            "tsql",
        )
        assert "UNIQUE:" in out and "server_id" in out, out
        assert re.search(r"(?im)^\s*RETURN @@server_id", out) is None, out

    def test_sysvar_kept_mysql(self) -> None:
        out = _t2(
            "create function f1() returns int begin return @@server_id; end",
            "mysql",
            "mysql",
        )
        assert "UNIQUE:" not in out, out
        assert "@@server_id" in out, out

    def test_plain_routine_untouched(self) -> None:
        out = _t2(
            "create function f2() returns int begin return 42; end",
            "mysql",
            "tsql",
        )
        assert "UNIQUE:" not in out, out
        assert re.search(r"(?i)RETURN 42", out), out


class TestWave168InsertSetUservarIsTrue:
    """wave 168 (mysql-corpus): INSERT … SET (sqlglot cannot parse it;
    the routine fallback DROPPED the SET clause — silent loss),
    top-level ``SET @var`` shipping raw via the SET-option classifier,
    and ``(pred) IS TRUE`` emitting ``IS 1``."""

    def test_insert_set_form_tsql(self) -> None:
        out = _t2(
            "create procedure p() begin insert into t3 set a=null; end",
            "mysql",
            "tsql",
        )
        assert re.search(r"(?i)INSERT INTO t3 \(a\)\s*VALUES \(NULL\)", out), out

    def test_insert_set_two_cols_top_level(self) -> None:
        out = _t2("insert into t3 set a=1, b='x,y';", "mysql", "tsql")
        assert re.search(r"(?i)INSERT INTO t3 \(a, b\)\s*VALUES \(1, 'x,y'\)", out), out

    def test_top_level_set_uservar_carrier(self) -> None:
        out = _t2("set @v0 = '2';", "mysql", "tsql")
        assert "UNIQUE:" in out and "@v0" in out, out
        assert not re.search(r"(?im)^\s*SET @v0", out), out

    def test_top_level_set_uservar_kept_mysql(self) -> None:
        out = _t2("set @v0 = '2';", "mysql", "mysql")
        assert "UNIQUE:" not in out, out

    def test_predicate_is_true_tsql(self) -> None:
        out = _t2(
            "select * from t1 where not (c2 is null) is true;",
            "mysql",
            "tsql",
        )
        assert re.search(r"(?i)NOT \(c2 IS NULL\)", out), out
        assert "IS 1" not in out.upper(), out

    def test_predicate_is_false_tsql(self) -> None:
        out = _t2("select * from t1 where (c2 is null) is false;", "mysql", "tsql")
        assert re.search(r"(?i)NOT \(c2 IS NULL\)", out), out


class TestWave169NotNullParenCompare:
    """wave 169 (mysql-corpus): ``(c2 IS NOT NULL) = 1`` — sqlglot
    spells IS NOT NULL as NOT(IS NULL), so the predicate-to-int
    rewrite's BinaryOp-left guard missed it and T-SQL got
    ``NOT (c2 IS NULL) = 1`` (error 102/156)."""

    def test_isnotnull_eq_one(self) -> None:
        out = _t2(
            "SELECT * FROM t1 LEFT JOIN t2 ON c1=c2" " WHERE (c2 IS NOT NULL) = 1;",
            "mysql",
            "tsql",
        )
        assert re.search(r"(?i)WHERE NOT \(c2 IS NULL\)\s*$", out.strip()), out

    def test_isnotnull_is_true(self) -> None:
        out = _t2(
            "SELECT * FROM t1 LEFT JOIN t2 ON c1=c2" " WHERE (c2 IS NOT NULL) IS TRUE;",
            "mysql",
            "tsql",
        )
        assert "IS 1" not in out.upper() and "= 1" not in out, out

    def test_isnotnull_eq_zero(self) -> None:
        out = _t2(
            "SELECT * FROM t1 LEFT JOIN t2 ON c1=c2" " WHERE (c2 IS NOT NULL) = 0;",
            "mysql",
            "tsql",
        )
        assert re.search(r"(?i)NOT \(NOT \(c2 IS NULL\)\)", out), out


class TestWave170NullTruthinessNotValue:
    """wave 170 (mysql-corpus): a bare NULL as a truth value (``… OR
    NULL``) is error 4145 on T-SQL (``NULL <> 0`` is the UNKNOWN-
    preserving comparison), and ``SET done = NOT done`` has no NOT in
    T-SQL value position (tri-state CASE)."""

    def test_or_null_condition_tsql(self) -> None:
        out = _t2(
            "select case when min(a) is null or null then 1 else 0 end" " from t1;",
            "mysql",
            "tsql",
        )
        assert re.search(r"(?i)OR NULL <> 0", out), out

    def test_set_not_flip_tsql(self) -> None:
        out = _t2(
            "create procedure p() begin declare done int default 0;"
            " set done = not done; end",
            "mysql",
            "tsql",
        )
        assert re.search(
            r"(?i)SET @done = CASE WHEN @done = 0 THEN 1"
            r" WHEN @done <> 0 THEN 0 END;",
            out,
        ), out

    def test_set_not_kept_mysql(self) -> None:
        out = _t2(
            "create procedure p() begin declare done int default 0;"
            " set done = not done; end",
            "mysql",
            "mysql",
        )
        assert re.search(r"(?i)SET done = not done;", out), out


class TestWave171KillConnectionId:
    """wave 171 (mysql-corpus): ``KILL QUERY id`` DROPPED its id via
    the embedded fallback (silent loss) — now a whole admin carrier;
    and CONNECTION_ID() shipped as a fake dbo. UDF — every engine has
    a session id under a different name."""

    def test_kill_carrier_tsql(self) -> None:
        out = _t2(
            "create procedure p() begin declare id int;"
            " set id = connection_id(); kill query id; end",
            "mysql",
            "tsql",
        )
        assert "UNIQUE:" in out and "kill query id" in out.lower(), out

    def test_connection_id_spid_tsql(self) -> None:
        out = _t2(
            "create procedure p() begin declare id int;"
            " set id = connection_id(); end",
            "mysql",
            "tsql",
        )
        assert "@@SPID" in out, out
        assert "connection_id" not in out.lower(), out

    def test_connection_id_pg(self) -> None:
        out = _t2(
            "create procedure p() begin declare id int;"
            " set id = connection_id(); end",
            "mysql",
            "postgresql",
        )
        assert "pg_backend_pid()" in out, out

    def test_connection_id_kept_mysql(self) -> None:
        out = _t2(
            "create procedure p() begin declare id int;"
            " set id = connection_id(); end",
            "mysql",
            "mysql",
        )
        assert re.search(r"(?i)connection_id\s*\(\s*\)", out), out


class TestWave172MysqlTsqlDeclareTypes:
    """wave 172 (mysql-corpus): PROCEDURAL_TYPE_MAPS had NO
    (mysql, tsql) entry at all — ``DECLARE @lf double`` shipped a type
    T-SQL does not recognize (its spelling is FLOAT)."""

    def test_declare_double_becomes_float(self) -> None:
        out = _t2(
            "create procedure p() begin declare lf double;" " set lf = 1.5; end",
            "mysql",
            "tsql",
        )
        assert re.search(r"(?i)DECLARE @lf FLOAT", out), out
        assert "double" not in out.lower(), out

    def test_declare_text_becomes_varchar_max(self) -> None:
        out = _t2(
            "create procedure p() begin declare s text; set s = 'x'; end",
            "mysql",
            "tsql",
        )
        assert re.search(r"(?i)DECLARE @s VARCHAR\(MAX\)", out), out

    def test_declare_double_kept_mysql(self) -> None:
        out = _t2(
            "create procedure p() begin declare lf double;" " set lf = 1.5; end",
            "mysql",
            "mysql",
        )
        assert re.search(r"(?i)DECLARE lf double", out), out


class TestWave173ExecExpressionArgs:
    """wave 173 (mysql-corpus): T-SQL EXEC arguments take only
    variables/literals — ``EXEC cbv2 @y + 1, @y`` was error 102. The
    expression hoists into a variable of the referenced variable's
    declared type."""

    def test_exec_arith_arg_hoisted(self) -> None:
        out = _t2(
            "create procedure cbv1() begin declare y int default 3;"
            " call cbv2(y+1, y); end",
            "mysql",
            "tsql",
        )
        assert re.search(r"(?i)DECLARE @uq_exec\d+ int = @y \+ 1;", out), out
        assert re.search(r"(?i)EXEC cbv2 @uq_exec\d+, @y;", out), out

    def test_exec_atomic_args_untouched(self) -> None:
        out = _t2(
            "create procedure p() begin declare y int;" " call q(y, 5, 'x'); end",
            "mysql",
            "tsql",
        )
        assert "uq_exec" not in out, out
        assert re.search(r"(?i)EXEC q @y, 5, 'x';", out), out

    def test_call_kept_mysql(self) -> None:
        out = _t2(
            "create procedure cbv1() begin declare y int default 3;"
            " call cbv2(y+1, y); end",
            "mysql",
            "mysql",
        )
        assert re.search(r"(?i)CALL cbv2\(y\s*\+\s*1, y\)", out), out


class TestWave174HexRowcountSubstring:
    """wave 174 (mysql-corpus): x'…' hex literals rendered as DECIMAL
    numbers (overflowing past BIGINT digits); ROW_COUNT() is a global
    on T-SQL/Oracle (and not a legal EXEC argument — hoisted); and
    T-SQL's SUBSTRING requires its length argument."""

    def test_hex_literal_tsql(self) -> None:
        out = _t2("insert into t1 values (x'8000000000000000');", "mysql", "tsql")
        assert "0x8000000000000000" in out, out

    def test_hex_literal_kept_mysql(self) -> None:
        out = _t2("insert into t1 values (x'8f');", "mysql", "mysql")
        assert re.search(r"(?i)x'8f'", out), out

    def test_rowcount_exec_arg_hoisted(self) -> None:
        out = _t2(
            "create procedure p() begin update b set n = n + 1;"
            " call log_p('x', row_count()); end",
            "mysql",
            "tsql",
        )
        assert re.search(r"(?i)DECLARE @uq_exec\d+ INT = @@ROWCOUNT;", out), out
        assert re.search(r"(?i)EXEC log_p 'x', @uq_exec\d+;", out), out

    def test_two_arg_substring_tsql(self) -> None:
        out = _t2(
            "select substring(email, locate('@', email) + 1) from t1;",
            "mysql",
            "tsql",
        )
        assert re.search(
            r"(?i)SUBSTRING\(email, CHARINDEX\('@', email\) \+ 1," r" LEN\(email\)\)",
            out,
        ), out


class TestWave175AllComputedTable:
    """wave 175 (mysql-corpus): T-SQL requires at least one
    non-computed column in a table (verified live: error 102 at the
    closing paren) — an all-generated MySQL table degrades WHOLE."""

    def test_all_computed_carrier_tsql(self) -> None:
        out = _t2(
            "create table t1 (a int as (1), b int as (a), c int as (1));",
            "mysql",
            "tsql",
        )
        assert "UNIQUE:" in out and "non-computed" in out, out
        assert not re.search(r"(?im)^\s*CREATE TABLE", out), out

    def test_mixed_table_untouched(self) -> None:
        out = _t2("create table t2 (x int, a int as (1));", "mysql", "tsql")
        assert "UNIQUE:" not in out, out
        assert re.search(r"(?i)CREATE TABLE", out), out

    def test_all_computed_kept_mysql(self) -> None:
        out = _t2(
            "create table t1 (a int as (1), b int as (a));",
            "mysql",
            "mysql",
        )
        assert "UNIQUE:" not in out, out
        assert re.search(r"(?i)CREATE TABLE", out), out


class TestWave176PgConditionLiterals:
    """wave 176 (mysql-corpus, pg front): PG's CASE/WHERE demand a
    boolean too — MySQL's numeric truthiness (``CASE WHEN 1``) is
    error 42804 there."""

    def test_case_when_integer_pg(self) -> None:
        out = _t2(
            "select case when 1 then 'a' else 'b' end;",
            "mysql",
            "postgresql",
        )
        assert re.search(r"(?i)WHEN 1 <> 0 THEN", out), out

    def test_boolean_literal_kept_pg(self) -> None:
        out = _t2(
            "select case when true then 'a' else 'b' end;",
            "mysql",
            "postgresql",
        )
        assert re.search(r"(?i)WHEN TRUE THEN", out), out


class TestWave177OracleInoutEmptyBody:
    """wave 177 (mysql-corpus, oracle front): Oracle spells the
    bidirectional mode ``IN OUT`` (a verbatim INOUT was PLS-00103),
    and PL/SQL requires at least one statement in a block — an empty
    MySQL body needs ``NULL;``."""

    def test_inout_spelled_in_out(self) -> None:
        out = _t2(
            "create procedure inc(inout io int) begin set io = io + 1; end",
            "mysql",
            "oracle",
        )
        assert re.search(r"(?i)io IN OUT NUMBER", out), out
        assert "INOUT" not in out.upper().replace("IN OUT", ""), out

    def test_empty_body_gets_null(self) -> None:
        out = _t2("create procedure avg_() begin end", "mysql", "oracle")
        assert re.search(r"(?i)BEGIN\s+NULL;\s+END;", out), out

    def test_inout_kept_mysql(self) -> None:
        out = _t2(
            "create procedure inc(inout io int) begin set io = io + 1; end",
            "mysql",
            "mysql",
        )
        assert re.search(r"(?i)INOUT io int", out), out


class TestWave178SysvarGateExecImmediate:
    """wave 178 (mysql-corpus): Oracle/PG have no @@ globals at all —
    a MySQL @@sysvar in a top-level statement degrades WHOLE there too;
    and PL/SQL cannot run DDL statically — embedded CREATE/DROP wraps
    in EXECUTE IMMEDIATE."""

    def test_sysvar_insert_carrier_oracle(self) -> None:
        out = _t2("insert into t1 values (@@connect_timeout);", "mysql", "oracle")
        assert "UNIQUE:" in out and "connect_timeout" in out, out
        assert not re.search(r"(?im)^\s*INSERT INTO", out), out

    def test_sysvar_insert_carrier_pg(self) -> None:
        out = _t2(
            "insert into t1 values (@@connect_timeout);",
            "mysql",
            "postgresql",
        )
        assert "UNIQUE:" in out, out

    def test_ddl_in_body_exec_immediate(self) -> None:
        out = _t2(
            "create procedure cs(x char(16), y int) begin"
            " insert into t1 values (x, y);"
            " create temporary table t3 as select * from t1;"
            " drop table t3; end",
            "mysql",
            "oracle",
        )
        assert re.search(r"(?i)EXECUTE IMMEDIATE 'CREATE ", out), out
        assert re.search(r"(?i)EXECUTE IMMEDIATE 'DROP TABLE", out), out
        assert re.search(r"(?i)INSERT INTO t1 VALUES", out), out


class TestWave179StraightJoin:
    """wave 179 (mysql-corpus): STRAIGHT_JOIN is INNER JOIN plus a
    join-order hint no other engine spells — inside a parenthesized
    join tree it survived the passthrough re-transpile verbatim."""

    _SQL = (
        "SELECT t1.pk FROM (BB AS t1 INNER JOIN"
        " (AA AS t2 STRAIGHT_JOIN A AS t3 ON (t3.k = t2.pk))"
        " ON (t3.dk = t2.ik)) WHERE t1.pk > 0;"
    )

    def test_straight_join_tsql(self) -> None:
        out = _t2(self._SQL, "mysql", "tsql")
        assert "STRAIGHT_JOIN" not in out.upper(), out
        assert re.search(r"(?i)INNER JOIN A", out), out

    def test_straight_join_oracle(self) -> None:
        out = _t2(self._SQL, "mysql", "oracle")
        assert "STRAIGHT_JOIN" not in out.upper(), out

    def test_straight_join_kept_mysql(self) -> None:
        out = _t2(self._SQL, "mysql", "mysql")
        assert "STRAIGHT_JOIN" in out.upper(), out


class TestWave180AlterViewLimitOracle:
    """wave 180 (mysql-corpus): Oracle/PG have no ``ALTER VIEW … AS``
    (ORA-00922) — redefinition is CREATE OR REPLACE VIEW; and a raw
    embedded ``LIMIT [a,] b`` spells OFFSET/FETCH on Oracle."""

    def test_alter_view_oracle(self) -> None:
        out = _t2("alter view v1 as select b from t1;", "mysql", "oracle")
        assert re.search(r"(?i)CREATE OR REPLACE VIEW v1", out), out
        assert "ALTER VIEW" not in out.upper(), out

    def test_alter_view_kept_tsql(self) -> None:
        out = _t2("alter view v1 as select b from t1;", "mysql", "tsql")
        assert re.search(r"(?i)ALTER VIEW v1", out), out

    def test_embedded_limit_two_oracle(self) -> None:
        out = _t2(
            "create function f1(p1 int, p2 int) returns int begin"
            " declare c int;"
            " set c = (select count(*) from"
            " (select * from t1 limit p1, p2) a);"
            " return c; end",
            "mysql",
            "oracle",
        )
        assert re.search(r"(?i)OFFSET p1 ROWS FETCH NEXT p2 ROWS ONLY", out), out
        assert "limit" not in out.lower(), out

    def test_limit_kept_pg(self) -> None:
        out = _t2(
            "create procedure q(x int) begin" " select id into x from t1 limit 1; end",
            "mysql",
            "postgresql",
        )
        assert re.search(r"(?i)LIMIT 1", out), out


class TestWave181OracleShadowedParam:
    """wave 181 (mysql-corpus): Oracle forbids a local variable
    shadowing a parameter (PLS-00410); MySQL allows it — the local
    renames to uq_<name>, its default still sees the parameter, body
    references follow the local."""

    def test_shadowed_local_renamed(self) -> None:
        out = _t2(
            "create procedure bug14376(x int) begin"
            " declare x int default x;"
            " select x; end",
            "mysql",
            "oracle",
        )
        assert re.search(r"(?i)uq_x NUMBER\(10\) := x;", out), out

    def test_non_shadowing_untouched(self) -> None:
        out = _t2(
            "create procedure p(a int) begin"
            " declare b int default a;"
            " select b; end",
            "mysql",
            "oracle",
        )
        assert "uq_" not in out, out
        assert re.search(r"(?i)b NUMBER\(10\) := a;", out), out

    def test_shadowing_kept_mysql(self) -> None:
        out = _t2(
            "create procedure p(x int) begin" " declare x int default x; select x; end",
            "mysql",
            "mysql",
        )
        assert "uq_" not in out, out


class TestWave182ShowRepairInBody:
    """wave 182 (mysql-corpus): SHOW/REPAIR/OPTIMIZE/… inside a routine
    emitted a bare ``;`` (SHOW — silent loss) or shredded (``REPAIR AS
    TABLE``); they join the admin-statement family."""

    def test_show_carrier_oracle(self) -> None:
        out = _t2(
            "create procedure p() begin"
            " create temporary table tm1 as select 1;"
            " show create table tm1; drop table tm1; end",
            "mysql",
            "oracle",
        )
        assert "UNIQUE:" in out and "show create table tm1" in out.lower(), out
        assert not re.search(r"(?m)^\s*;\s*$", out), out

    def test_optimize_carrier_tsql(self) -> None:
        out = _t2(
            "create procedure p() begin repair table t1;"
            " optimize table t1, t2; analyze table t1; end",
            "mysql",
            "tsql",
        )
        assert out.lower().count("unique:") >= 3, out
        assert "REPAIR AS" not in out, out

    def test_show_kept_mysql(self) -> None:
        out = _t2(
            "create procedure p() begin"
            " create temporary table tm1 as select 1;"
            " show create table tm1; end",
            "mysql",
            "mysql",
        )
        assert re.search(r"(?i)show create table tm1", out), out
        assert "UNIQUE:" not in out, out


class TestWave183CommentOnlyBody:
    """wave 183 (mysql-corpus): a PL/SQL body whose only statement
    degraded to a comment carrier (``BEGIN -- UNIQUE: … END;``) is
    still PLS-00103 — it needs the NULL; too; and bare ``;`` empty
    statements are dropped."""

    def test_comment_only_body_gets_null(self) -> None:
        out = _t2(
            "create procedure p() begin show processlist; end",
            "mysql",
            "oracle",
        )
        assert "UNIQUE:" in out, out
        assert re.search(r"(?im)^\s*NULL;", out), out

    def test_executable_body_no_extra_null(self) -> None:
        out = _t2("create procedure p() begin select 1; end", "mysql", "oracle")
        assert not re.search(r"(?im)^\s*NULL;", out), out
