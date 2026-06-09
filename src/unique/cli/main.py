# Copyright (C) 2026 Unique Contributors
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.

"""Command-line interface for the Unique SQL transpiler."""

from __future__ import annotations

import sys

import click

from unique.core.registry import DialectRegistry
from unique.core.transpiler import Transpiler


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
def transpile(
    input_file: str | None,
    source: str,
    target: str,
    output: str | None,
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
    try:
        result = transpiler.transpile(sql, source=source, target=target)
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
