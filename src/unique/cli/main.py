# Copyright (c) 2026 Unique Contributors
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Command-line interface for the Unique SQL transpiler."""

from __future__ import annotations

import sys

import click

from unique.core.registry import DialectRegistry
from unique.core.transpiler import TranspileOptions, Transpiler


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
    help="Source dialect (tsql, oracle, postgresql, mysql).",
)
@click.option(
    "--to",
    "target",
    required=True,
    help="Target dialect (tsql, oracle, postgresql, mysql).",
)
@click.option(
    "--output", "-o", type=click.Path(), help="Output file. Defaults to stdout."
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
    """Validate SQL syntax by parsing it without emitting.

    Attempts to parse the SQL and reports any errors.
    """
    with open(input_file, encoding="utf-8") as f:
        sql = f.read()

    transpiler = Transpiler()
    try:
        dialect_impl = transpiler.registry.get(dialect)
        nodes = dialect_impl.parse(sql)
        click.echo(f"Valid: parsed {len(nodes)} statement(s).")
    except Exception as e:
        click.echo(f"Invalid: {e}", err=True)
        sys.exit(1)


@cli.command(name="dialects")
def list_dialects() -> None:
    """List all available SQL dialects."""
    registry = DialectRegistry.with_builtins()
    for name in registry.available():
        dialect = registry.get(name)
        features = len(dialect.supported_features())
        click.echo(f"  {name:<15} ({features} features)")


if __name__ == "__main__":
    cli()
