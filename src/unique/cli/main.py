# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Command-line interface for the Unique SQL transpiler."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

import click

from unique.core import diagnostics
from unique.core.registry import DialectRegistry
from unique.core.transpiler import TranspileOptions, Transpiler
from unique.core.validation import validate_source

if TYPE_CHECKING:
    from unique.core.similarity import SimilarityReport


@click.group()
@click.version_option(package_name="unique")
def cli() -> None:
    """Unique — SQL transpiler for SQL Server, Oracle, PostgreSQL, and MySQL."""


@cli.command()
@click.argument("input_file", type=click.Path(exists=True), required=False)
@click.option(
    "--from",
    "source",
    required=True,
    help="Source dialect (tsql, oracle, postgresql, mysql, sqlite).",
)
@click.option(
    "--to",
    "target",
    required=True,
    help="Target dialect (tsql, oracle, postgresql, mysql; not sqlite).",
)
@click.option(
    "--output", "-o", type=click.Path(), help="Output file. Defaults to stdout."
)
@click.option(
    "--ignore-syntax-errors",
    "ignore_syntax_errors",
    is_flag=True,
    default=False,
    help="Transpile even if the source has syntax errors (reported by default).",
)
@click.option(
    "--ignore",
    "ignore_codes",
    multiple=True,
    metavar="UNIQUE-NNNN",
    help=(
        "Suppress warnings carrying this diagnostic code from the WARNING "
        "output (repeatable). The code must be registered (see the reference "
        "catalog). Carriers stay in the transpiled SQL — the SQL text is the "
        "artifact; --ignore governs only the warning channel."
    ),
)
@click.option(
    "--db-url",
    "db_url",
    default=None,
    help=(
        "Optional database connection URL for resolving metadata-dependent "
        "constructs such as Oracle %TYPE/%ROWTYPE references. "
        "Examples: oracle://user:pass@host:1521/service, "
        "mssql://user:pass@host:1433/db."
    ),
)
def transpile(
    input_file: str | None,
    source: str,
    target: str,
    output: str | None,
    ignore_syntax_errors: bool,
    ignore_codes: tuple[str, ...],
    db_url: str | None,
) -> None:
    """Transpile SQL from one dialect to another.

    Reads from INPUT_FILE or stdin if no file is given.
    """
    # Reject unregistered --ignore codes up front (a typo silently suppressing
    # nothing is worse than an error).
    ignore_set = {code.upper() for code in ignore_codes}
    unknown = sorted(c for c in ignore_set if not diagnostics.is_registered(c))
    if unknown:
        click.echo(
            f"Error: unknown diagnostic code(s) for --ignore: {', '.join(unknown)}. "
            "Codes look like UNIQUE-1234; see the reference catalog.",
            err=True,
        )
        sys.exit(1)
    # Read input
    if input_file:
        with open(input_file, encoding="utf-8") as f:
            sql = f.read()
    else:
        sql = sys.stdin.read()

    if not sql.strip():
        click.echo("Error: No SQL input provided.", err=True)
        sys.exit(1)

    # Refuse a malformed source up front (unless told to transpile anyway).
    if not ignore_syntax_errors:
        try:
            issues = validate_source(sql, source)
        except Exception:
            issues = []
        if issues:
            click.echo(
                f"Error: {len(issues)} syntax error(s) in the source "
                "(use --ignore-syntax-errors to transpile anyway):",
                err=True,
            )
            for issue in issues:
                click.echo(f"  {issue}", err=True)
            sys.exit(1)

    # Transpile
    transpiler = Transpiler()
    options = TranspileOptions(db_url=db_url)
    try:
        result = transpiler.transpile(
            sql, source=source, target=target, options=options
        )
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    # Output warnings, honoring --ignore (the warning channel only — carriers
    # remain in result.sql).
    shown = [w for w in result.warnings if w.code not in ignore_set]
    suppressed = len(result.warnings) - len(shown)
    for warning in shown:
        prefix = f"WARNING [{warning.code}]: " if warning.code else "WARNING: "
        click.echo(f"{prefix}{warning.message}", err=True)
    if suppressed:
        click.echo(f"{suppressed} warning(s) suppressed by --ignore", err=True)

    if result.has_unsupported:
        for feature in result.unsupported:
            click.echo(f"UNSUPPORTED: {feature}", err=True)

    # Write output
    if output:
        with open(output, "w", encoding="utf-8") as f:
            f.write(result.sql)
        click.echo(f"Output written to {output}", err=True)
    else:
        click.echo(result.sql)


@cli.command()
@click.argument("input_file", type=click.Path(exists=True))
@click.option("--dialect", "-d", required=True, help="Dialect to validate against.")
def validate(input_file: str, dialect: str) -> None:
    """Report source-SQL syntax errors, located by line, for the given dialect."""
    with open(input_file, encoding="utf-8") as f:
        sql = f.read()

    try:
        Transpiler().registry.get(dialect)  # reject an unknown dialect
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    issues = validate_source(sql, dialect)
    if not issues:
        click.echo("Valid: no syntax errors.")
        return
    click.echo(f"Invalid: {len(issues)} syntax error(s):", err=True)
    for issue in issues:
        click.echo(f"  {issue}", err=True)
    sys.exit(1)


@cli.command()
@click.argument("file_a", type=click.Path(exists=True))
@click.argument("file_b", type=click.Path(exists=True))
@click.option(
    "--dialect-a",
    "dialect_a",
    default=None,
    help="Dialect of FILE_A (auto-detected if omitted).",
)
@click.option(
    "--dialect-b",
    "dialect_b",
    default=None,
    help="Dialect of FILE_B (auto-detected if omitted).",
)
@click.option(
    "--json", "as_json", is_flag=True, default=False, help="Emit the report as JSON."
)
def compare(
    file_a: str,
    file_b: str,
    dialect_a: str | None,
    dialect_b: str | None,
    as_json: bool,
) -> None:
    """Report the STRUCTURAL SIMILARITY of two SQL scripts.

    Both scripts are normalized through the transpiler (PostgreSQL pivot) and
    compared by structural fingerprint and weighted tree alignment. The result
    is a structural-similarity percentage with a per-dimension breakdown — it
    is NOT a probability of semantic equivalence (see docs/03-unsupported.md).
    """
    from unique.core.similarity import compare as compare_scripts

    with open(file_a, encoding="utf-8") as f:
        sql_a = f.read()
    with open(file_b, encoding="utf-8") as f:
        sql_b = f.read()

    try:
        report = compare_scripts(sql_a, sql_b, dialect_a, dialect_b)
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(2)

    if as_json:
        import json

        payload = {"file_a": file_a, "file_b": file_b, **report.to_dict()}
        click.echo(json.dumps(payload, indent=2))
        return

    _print_comparison(file_a, file_b, report)


def _print_comparison(file_a: str, file_b: str, report: SimilarityReport) -> None:
    """Render a :class:`SimilarityReport` for humans."""
    label_a = (
        f"{file_a} ({report.dialect_a}{', auto-detected' if report.detected_a else ''})"
    )
    label_b = (
        f"{file_b} ({report.dialect_b}{', auto-detected' if report.detected_b else ''})"
    )
    click.echo(f"Comparing {label_a}")
    click.echo(f"     with {label_b}")
    click.echo(f"\nStructural similarity: {report.overall}%")
    click.echo("(structural, not a probability of semantic equivalence)\n")
    names = {
        "dml_structure": "DML structure",
        "predicates": "Predicates",
        "control_flow": "Control flow",
        "tree_match": "Tree match",
    }
    for key, label in names.items():
        click.echo(f"  {label:<16} {report.dimensions[key]:5.1f}%")
    click.echo(
        f"\nAligned statement pairs: {len(report.statement_pairs)}   "
        f"Unmatched: A={report.unmatched_a} B={report.unmatched_b}"
    )
    if report.warnings:
        click.echo(
            f"\nTranspiler warnings during normalization: {len(report.warnings)}"
        )
        for w in report.warnings[:5]:
            prefix = f"[{w.code}] " if w.code else ""
            click.echo(f"  - {prefix}{w.message}", err=True)
        if len(report.warnings) > 5:
            click.echo(f"  … and {len(report.warnings) - 5} more", err=True)


@cli.command(name="dialects")
def list_dialects() -> None:
    """List all available SQL dialects."""
    registry = DialectRegistry.with_builtins()
    for name in registry.available():
        dialect = registry.get(name)
        features = len(dialect.supported_features())
        role = " [import-only]" if dialect.source_only else ""
        click.echo(f"  {name:<15} ({features} features){role}")


if __name__ == "__main__":
    cli()
