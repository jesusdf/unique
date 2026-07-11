# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Unit tests for the PG regression-corpus curation pass.

``scripts/fetch_pg_corpus.py`` downloads files from PostgreSQL's regression
suite and strips the psql-specific noise so the result is plain SQL suitable
for ``validity_sweep.py --from postgresql``. These tests pin the strip rules:
backslash meta-commands are line-oriented client commands (dropped), and a
``COPY … FROM stdin`` statement is inseparable from its raw data block
(dropped whole, through the ``\\.`` terminator).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "fetch_pg_corpus",
    Path(__file__).resolve().parents[3] / "scripts" / "fetch_pg_corpus.py",
)
assert _SPEC is not None and _SPEC.loader is not None
fetch_pg_corpus = importlib.util.module_from_spec(_SPEC)
sys.modules["fetch_pg_corpus"] = fetch_pg_corpus
_SPEC.loader.exec_module(fetch_pg_corpus)

strip_psql_noise = fetch_pg_corpus.strip_psql_noise


class TestMetaCommands:
    def test_backslash_line_is_dropped_and_sql_kept(self) -> None:
        src = "insert into t values (1);\n\\d+ t\nselect * from t;\n"
        out = strip_psql_noise(src)
        assert "\\d+" not in out
        assert "insert into t values (1);" in out
        assert "select * from t;" in out

    def test_indented_meta_command_is_dropped(self) -> None:
        out = strip_psql_noise("  \\set var 42\nselect 1;\n")
        assert "\\set" not in out
        assert "select 1;" in out

    def test_kept_lines_are_verbatim(self) -> None:
        src = "select 1,\n       2;\n"
        assert strip_psql_noise(src) == src


class TestCopyStdin:
    def test_copy_stdin_block_dropped_whole(self) -> None:
        src = (
            "create table t (a int, b text);\n"
            "COPY t FROM stdin;\n"
            "1\tfoo\n"
            "2\tbar\n"
            "\\.\n"
            "select * from t;\n"
        )
        out = strip_psql_noise(src)
        assert "COPY" not in out
        assert "foo" not in out and "bar" not in out
        assert "\\." not in out
        assert "create table t (a int, b text);" in out
        assert "select * from t;" in out

    def test_lowercase_copy_with_column_list_and_options(self) -> None:
        src = "copy t (a, b) from stdin with (format csv);\n1,x\n\\.\nselect 2;\n"
        out = strip_psql_noise(src)
        assert "copy" not in out.lower()
        assert "1,x" not in out
        assert "select 2;" in out

    def test_copy_to_stdout_is_plain_sql_and_kept(self) -> None:
        src = "COPY t TO stdout;\nselect 3;\n"
        out = strip_psql_noise(src)
        assert "COPY t TO stdout;" in out
        assert "select 3;" in out

    def test_data_lines_are_not_parsed_as_meta_or_copy(self) -> None:
        # A data row that *looks* like SQL or a meta-command must still be
        # consumed by the COPY block, and the block must end only at \.
        src = "copy t from stdin;\nselect 'not sql';\n\\d fake\n\\.\nselect 4;\n"
        out = strip_psql_noise(src)
        assert "not sql" not in out
        assert "\\d fake" not in out
        assert "select 4;" in out


class TestDefaultFileSet:
    def test_portable_core_is_selected(self) -> None:
        names = fetch_pg_corpus.DEFAULT_FILES
        for expected in ("insert", "join", "aggregates", "plpgsql", "triggers"):
            assert expected in names
        # Engine-internal suites must not be in the default set.
        for internal in ("stats_import", "rowsecurity", "privileges"):
            assert internal not in names


class TestPsqlVariableStatements:
    def test_psql_variable_line_is_dropped(self) -> None:
        src = "select 1;\nCOPY aggtest FROM :'filename';\nselect 2;\n"
        out = strip_psql_noise(src)
        assert ":'filename'" not in out
        assert "select 1;" in out and "select 2;" in out
