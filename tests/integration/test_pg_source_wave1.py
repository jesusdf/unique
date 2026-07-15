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
