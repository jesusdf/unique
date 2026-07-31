[← All rationale topics](../README.md)

# DDL: identity, temp tables, foreign keys, sequences, storage options

The `CREATE TABLE`/`ALTER TABLE`/`CREATE SEQUENCE` surface where each engine's
schema model diverges most: auto-generated keys, session-scoped tables,
referential actions, sequence option spelling, and physical storage clauses.
See [README.md](../README.md) for the entry format and sourcing rules.

> **Generated file — do not edit by hand.** Produced by `python scripts/generate_rationale_index.py` from the article pages in this directory; the intro above comes from `_intro.md`. The CI freshness gate (`python scripts/generate_rationale_index.py --check`) fails the build if it drifts.

## The SERIAL / IDENTITY / AUTO_INCREMENT triangle

| Article | Direction | Description |
|---|---|---|
| [Auto-incrementing key columns (PostgreSQL `SERIAL` / T-SQL `IDENTITY` / Oracle `GENERATED … AS IDENTITY` / MySQL `AUTO_INCREMENT`)](auto-incrementing-keys.md) | cross-engine | Each engine spells "the database assigns this column's value from an internal counter" differently: PostgreSQL `SERIAL`/`BIGSERIAL` (sugar for an integer + an owned sequence + a default), T-SQL `IDENTITY(seed, step)`, Oracle `GENERATED ALWAYS\|BY DEFAULT AS IDENTITY [(START WITH s INCREMENT BY i …)]`, MySQL `AUTO_INCREMENT` (a single table-level counter, no per-column seed/step). |
| [T-SQL identity-scope reads (`SCOPE_IDENTITY()`/`@@IDENTITY`/`IDENT_CURRENT()`) → PostgreSQL / Oracle / MySQL](tsql-identity-scope-reads.md) | tsql → oracle/postgresql/mysql | T-SQL exposes the last-generated identity value through three functions with different scoping rules (current scope / current session / a named table). |

## Cross-statement schema-state-driven coercion

| Article | Direction | Description |
|---|---|---|
| [Cross-statement schema-state-driven coercion](cross-statement-coercion-overview.md) | overview | The three entries below share one mechanism: a single statement cannot be transpiled correctly by looking at its own text alone, because the correct output depends on a column's *declared* type or nullability, established somewhere earlier in the same script (a `CREATE TABLE`, a prior `ALTER TABLE`, even a prior `RENAME COLUMN`) or on the column's role inside the *same* `CREATE TABLE`. |
| [T-SQL `BIT` `0`/`1` values (defaults, `INSERT`, `UPDATE`, incl. inside procedure bodies) → PostgreSQL `BOOLEAN`](tsql-bit-to-postgresql-boolean.md) | tsql → postgresql | T-SQL's `BIT` type behaves like a 1-bit integer: `0`/`1` literals are valid in a `DEFAULT` clause, an `INSERT ... VALUES` list, or an `UPDATE ... SET`, with no special casting. |
| [T-SQL `ALTER COLUMN <c> <type>` re-states the column's last-known nullability → PostgreSQL (both directions)](alter-column-nullability.md) | tsql → postgresql | T-SQL's `ALTER COLUMN <c> <type>` bakes type *and* nullability into one clause — omitting a `NULL`/`NOT NULL` keyword does not mean "leave nullability alone," it means "make the column nullable," silently dropping an existing `NOT NULL` the statement never mentioned. |
| [Oracle bare `NUMBER` (no precision/scale) → role-aware numeric](oracle-bare-number-role-aware.md) | cross-engine | Oracle's unqualified `NUMBER` — no precision or scale — is overloaded. |

## Temporary tables and the `CREATE TABLE AS SELECT` ↔ `SELECT INTO` idiom

| Article | Direction | Description |
|---|---|---|
| [Session-scoped temp tables (PostgreSQL `TEMP` / T-SQL `#temp` / MySQL `TEMPORARY`) → Oracle `GLOBAL TEMPORARY`](session-temp-tables-to-oracle.md) | tsql/postgresql/mysql → oracle | A PostgreSQL `TEMP`/`TEMPORARY` table, a T-SQL `#temp` table, and a MySQL `TEMPORARY` table are all **session-scoped**: their definition and rows live only for the current connection, and — critically — their rows **survive an intervening `COMMIT`**. |
| [`CREATE TABLE AS SELECT` ↔ `SELECT ... INTO` for ordinary (non-temporary) tables](ctas-vs-select-into.md) | cross-engine | This extends the entry above from *temp* tables specifically to *any* table: T-SQL has no `CREATE TABLE ... AS SELECT` syntax at all — whether or not the table is session-scoped — so any CTAS from another source dialect must become a T-SQL `SELECT ... INTO`. |

## Foreign-key referential actions

| Article | Direction | Description |
|---|---|---|
| [`ON UPDATE <action>` (PostgreSQL / T-SQL / MySQL) → Oracle](fk-on-update-action-to-oracle.md) | tsql/postgresql/mysql → oracle | `REFERENCES p(id) ON DELETE CASCADE ON UPDATE CASCADE` propagates both a delete and a primary-key update on the parent to the child. |
| [Self-referencing FK cascade (MySQL) → T-SQL](self-referencing-fk-cascade.md) | mysql → tsql | `FOREIGN KEY (mgr) REFERENCES emp(id) ON DELETE SET NULL`, where the FK references its **own** table (an employee/manager hierarchy). |

## Sequences

| Article | Direction | Description |
|---|---|---|
| [One-word vs two-word negative options (Oracle `NOMAXVALUE`/`NOCYCLE` vs T-SQL/PostgreSQL `NO MAXVALUE`/`NO CYCLE`)](sequence-negative-option-spelling.md) | oracle ↔ tsql/postgresql | `CREATE SEQUENCE … NO MAXVALUE NO CYCLE` (T-SQL, PostgreSQL) and `CREATE SEQUENCE … NOMAXVALUE NOCYCLE` (Oracle) both mean "no upper bound, do not wrap around" — the same option, spelled as two words on some engines and fused to one word on Oracle. |

## Storage and physical options

| Article | Direction | Description |
|---|---|---|
| [T-SQL index `WITH (FILLFACTOR = n)` → Oracle / MySQL](tsql-index-fillfactor.md) | tsql → oracle/mysql | `FILLFACTOR` reserves free space per index page for future inserts — a physical storage tuning knob with no logical effect on query results. |

## MySQL `ENUM` degrade — open limitation

| Article | Direction | Description |
|---|---|---|
| [`ENUM('lo','mid','hi')` (MySQL) → PostgreSQL / T-SQL / Oracle VARCHAR + CHECK](mysql-enum-to-varchar-check.md) | mysql → tsql/oracle/postgresql | A MySQL `ENUM` column stores one of a fixed value list, and — the part that matters here — **orders by declaration index**, not alphabetically: `ENUM('lo','mid','hi')` sorts `lo < mid < hi` regardless of the values' lexical order. |

## Synthesized identifiers for anonymous constructs

| Article | Direction | Description |
|---|---|---|
| [Synthesized identifiers for anonymous constructs](synthesized-identifiers-overview.md) | overview | T-SQL requires a name in two places where PostgreSQL/MySQL/Oracle happily accept an anonymous construct: every derived-table column must have one (error 8155), and — outside DDL proper but pinned by the same "T-SQL requires a name" family — every index does too. |
| [Nameless `CREATE INDEX ON t(col)` (PostgreSQL) → T-SQL](nameless-create-index-to-tsql.md) | postgresql → tsql | PostgreSQL allows `CREATE INDEX ON t (col)` with no index name — the server picks one internally (`t_col_idx`-shaped, but never surfaced to the script). |
| [Unnamed derived-table / `SELECT ... INTO` projections → synthesized `uq_col1` (T-SQL)](unnamed-projection-synthesized-name.md) | cross-engine | `SELECT (SELECT a) t` or `SELECT (SELECT 1) t` — a derived table whose single projected column is a bare parameter reference or a literal, with no alias — is legal on PostgreSQL/MySQL/Oracle (the column gets an engine-assigned display name that nothing else references). |

## Topics left out for lack of source support

| Article | Direction | Description |
|---|---|---|
| [Topics left out for lack of source support](topics-left-out.md) | overview | - **PostgreSQL `SET`-type MySQL columns** (unordered multi-value combination) degrade the same way `ENUM` does (to a `VARCHAR` wide enough for all values plus a documented note), but no challenge-corpus case exercises `SET` specifically, so no dedicated entry is made to avoid inventing an example. |

## Computed columns

| Article | Direction | Description |
|---|---|---|
| [`GENERATED ALWAYS AS (expr)` computed columns (cross-engine)](computed-columns-generated-always.md) | cross-engine | A computed (generated) column derives its value from an expression over other columns in the same row, recalculated automatically on every read or write — a fundamentally different thing from an auto-incrementing identity column, even though MySQL spells the two very differently and PostgreSQL's `GENERATED ALWAYS AS (...)` clause is shared syntax for both. |

## Inline DDL attributes decomposed into standalone statements

| Article | Direction | Description |
|---|---|---|
| [Inline DDL attributes decomposed into standalone statements: MySQL `COMMENT`, T-SQL inline `INDEX`](inline-attribute-to-standalone-statement.md) | cross-engine | MySQL lets a column or table carry a `COMMENT '...'` right inside its `CREATE TABLE`, and T-SQL lets a table element declare an `INDEX` inline alongside its columns. |

## Non-negativity constraint synthesis

| Article | Direction | Description |
|---|---|---|
| [MySQL `UNSIGNED` → widened signed type + synthesized `CHECK (col >= 0)`](mysql-unsigned-check-synthesis.md) | mysql → tsql/oracle/postgresql | A MySQL `UNSIGNED` integer column can never hold a negative value — that's enforced structurally by the column's own type, not by a constraint. |

## TRUNCATE options

| Article | Direction | Description |
|---|---|---|
| [PostgreSQL `TRUNCATE ... RESTART IDENTITY / CASCADE` → Oracle/MySQL/T-SQL](truncate-restart-identity-cascade.md) | postgresql → oracle/mysql/tsql | PostgreSQL's `TRUNCATE` defaults to *keeping* an identity column's next value where it was (`CONTINUE IDENTITY` is implicit), and only resets it when you say `RESTART IDENTITY` explicitly; the same statement's `CASCADE` also truncates every table with a foreign key pointing at the truncated one. |

## Inline column-level constraints relocated to table-level

| Article | Direction | Description |
|---|---|---|
| [An inline column-level `REFERENCES`/`CHECK` constraint → a table-level constraint clause](inline-fk-check-relocated-table-level.md) | cross-engine | `c INT REFERENCES p(id) ON DELETE CASCADE` and `c INT CHECK (c > 0)` declare a foreign key or check constraint directly on the column, inline inside its own definition — every engine accepts this shorthand. |

## T-SQL CREATE TYPE alias resolved to its base type

| Article | Direction | Description |
|---|---|---|
| [T-SQL `CREATE TYPE x FROM base` alias type → resolved to its base type everywhere](create-type-alias-harvested.md) | tsql → oracle/postgresql/mysql | T-SQL lets a script define a named alias type (`CREATE TYPE [dbo].[Name] FROM [nvarchar](50) NULL`) and then use `[dbo].[Name]` as an ordinary column type elsewhere in the same script. |

## Oracle RAW(16) DEFAULT SYS_GUID() → PostgreSQL BYTEA default

| Article | Direction | Description |
|---|---|---|
| [Oracle `RAW(16) DEFAULT SYS_GUID()` → PostgreSQL `BYTEA` with a matching `DECODE(...)` default](raw-guid-default-bytea.md) | oracle → postgresql | `RAW(16) DEFAULT SYS_GUID()` is Oracle's idiom for a binary-GUID primary key: `SYS_GUID()` generates a 16-byte raw value used directly as the default. |

## ALTER COLUMN DROP DEFAULT

| Article | Direction | Description |
|---|---|---|
| [PostgreSQL `ALTER COLUMN a DROP DEFAULT` → Oracle `MODIFY ... DEFAULT NULL`, T-SQL dynamic-SQL script](alter-column-drop-default.md) | postgresql → oracle/tsql | PostgreSQL's `ALTER TABLE t ALTER COLUMN a DROP DEFAULT` removes a column's default expression by name-free reference — no other engine has an equivalent "just remove whatever default is there" clause. |

## Oracle ALTER TABLE ADD (...) parenthesized-list unwrapping

| Article | Direction | Description |
|---|---|---|
| [Oracle `ALTER TABLE ... ADD ( ... )` (parenthesized element list) → an unwrapped `ADD` clause](oracle-alter-add-parenthesized-unwrap.md) | oracle → tsql/postgresql/mysql | Oracle allows one or more table elements (columns, constraints) to be added in a single parenthesized list — `ALTER TABLE t ADD (CONSTRAINT fk FOREIGN KEY (col) REFERENCES p(id))`. |

## DROP emitted idempotently

| Article | Direction | Description |
|---|---|---|
| [A plain `DROP TABLE t` → `DROP TABLE IF EXISTS t` on PostgreSQL](drop-table-idempotent-if-exists.md) | tsql → postgresql | A migration script is meant to be re-runnable against a target that may already have run it once before — a bare `DROP TABLE t` errors on a second run if the table is already gone, stopping the whole script partway through. |
