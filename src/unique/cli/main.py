# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Command-line interface for the Unique SQL transpiler."""

from __future__ import annotations

import sys

import click

from unique.core.registry import DialectRegistry
from unique.core.transpiler import TranspileOptions, Transpiler
from unique.core.validation import validate_source


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
    db_url: str | None,
) -> None:
    """Transpile SQL from one dialect to another.

    Reads from INPUT_FILE or stdin if no file is given.
    """
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

    # Output warnings
    if result.has_warnings:
        for warning in result.warnings:
            click.echo(f"WARNING: {warning.message}", err=True)

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
