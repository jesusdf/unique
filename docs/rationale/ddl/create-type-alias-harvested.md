[← DDL: identity, temp tables, foreign keys, sequences, storage options](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=ddl type="T-SQL CREATE TYPE alias resolved to its base type" direction="tsql → oracle/postgresql/mysql" kind=article order=23 -->

# T-SQL `CREATE TYPE x FROM base` alias type → resolved to its base type everywhere

**Problem.** T-SQL lets a script define a named alias type (`CREATE TYPE
[dbo].[Name] FROM [nvarchar](50) NULL`) and then use `[dbo].[Name]` as an
ordinary column type elsewhere in the same script. None of PostgreSQL,
MySQL, or Oracle have an equivalent user-defined scalar alias type — a
column declared `[dbo].[Name]` translated verbatim leaves an
unrecognizable type name in every target's `CREATE TABLE`, breaking the
column outright.

**Solution.**

```sql
-- tests/integration/test_cross_dialect.py::TestTSQLAliasTypes
CREATE TYPE [dbo].[Name] FROM [nvarchar](50) NULL
GO
CREATE TABLE [SalesLT].[Customer](
    [CustomerID] [int] NOT NULL,
    [FirstName] [dbo].[Name] NOT NULL
)
GO
-- tsql -> postgresql / mysql:
CREATE TABLE "SalesLT"."Customer" (
  "CustomerID" INT NOT NULL,
  "FirstName" VARCHAR(50) NOT NULL
);
-- tsql -> oracle:
CREATE TABLE "SalesLT"."Customer" (
  "CustomerID" NUMBER(10) NOT NULL,
  "FirstName" NVARCHAR2(50) NOT NULL
);
```

A column typed with an alias the script never defines (no matching
`CREATE TYPE` anywhere in it) is left with the qualified name untouched,
since there is nothing to resolve it against.

**Discussion.** Unique harvests every `CREATE TYPE ... FROM <base>` in the
script before emitting any `CREATE TABLE`, building a name → base-type map;
every column reference to an alias name is then resolved to that base type
and mapped through the normal cross-engine type table, the same as if the
column had been declared with the base type directly. This was found on a
real sample schema (AdventureWorksLT) where `dbo.Name`-typed columns
otherwise leaked verbatim into every target and broke MySQL parsing
outright, since a naked, unrecognized type name is a syntax error there,
not merely a warning.

> **Note** faithful — the resolved column keeps the alias's own declared
> width and nullability (`(50)`, `NOT NULL`); only the alias name itself is
> replaced by its base type, since no target engine can define or reference
> the alias. No warning.

**See Also.** [`test_cross_dialect.py::TestTSQLAliasTypes`](../../../tests/integration/test_cross_dialect.py)
(`test_alias_column_resolves_to_base_type`,
`test_alias_without_definition_left_untouched`).
