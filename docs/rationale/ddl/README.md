[← All rationale topics](../README.md)

# DDL: identity, temp tables, foreign keys, sequences, storage options

The `CREATE TABLE`/`ALTER TABLE`/`CREATE SEQUENCE` surface where each engine's
schema model diverges most: auto-generated keys, session-scoped tables,
referential actions, sequence option spelling, and physical storage clauses.
See [README.md](../README.md) for the entry format and sourcing rules.

> **Generated file — do not edit by hand.** Produced by `python scripts/generate_rationale_index.py` from the article pages in this directory; the intro above comes from `_intro.md`. The CI freshness gate (`python scripts/generate_rationale_index.py --check`) fails the build if it drifts.

## By engine

Each article grouped by the engine it converts **from** and **to** (derived from the `direction` metadata). Cross-engine articles — no single source/target — are listed once at the end.

| Engine | As source | As target |
|---|---|---|
| T-SQL | [as source](#t-sql-as-source) | [as target](#t-sql-as-target) |
| Oracle | [as source](#oracle-as-source) | [as target](#oracle-as-target) |
| PostgreSQL | [as source](#postgresql-as-source) | [as target](#postgresql-as-target) |
| MySQL | [as source](#mysql-as-source) | [as target](#mysql-as-target) |
| Cross-engine | [multi-directional](#cross-engine--multi-directional) |  |

### T-SQL as source

| [The SERIAL / IDENTITY / AUTO_INCREMENT triangle](#the-serial--identity--auto_increment-triangle) | [Cross-statement schema-state-driven coercion](#cross-statement-schema-state-driven-coercion) | [Temporary tables and the `CREATE TABLE AS SELECT` ↔ `SELECT INTO` idiom](#temporary-tables-and-the-create-table-as-select--select-into-idiom) | [Foreign-key referential actions](#foreign-key-referential-actions) | [Sequences](#sequences) | [Storage and physical options](#storage-and-physical-options) | [T-SQL CREATE TYPE alias resolved to its base type](#t-sql-create-type-alias-resolved-to-its-base-type) | [DROP emitted idempotently](#drop-emitted-idempotently) | [DDL guards](#ddl-guards) |
|---|---|---|---|---|---|---|---|---|

#### The SERIAL / IDENTITY / AUTO_INCREMENT triangle

| Article | Direction | Description |
|---|---|---|
| [T-SQL identity-scope reads (`SCOPE_IDENTITY()`/`@@IDENTITY`/`IDENT_CURRENT()`) → PostgreSQL / Oracle / MySQL](tsql-identity-scope-reads.md) | tsql → oracle/postgresql/mysql | T-SQL exposes the last-generated identity value through three functions with different scoping rules (current scope / current session / a named table). |

#### Cross-statement schema-state-driven coercion

| Article | Direction | Description |
|---|---|---|
| [T-SQL `BIT` `0`/`1` values (defaults, `INSERT`, `UPDATE`, incl. inside procedure bodies) → PostgreSQL `BOOLEAN`](tsql-bit-to-postgresql-boolean.md) | tsql → postgresql | T-SQL's `BIT` type behaves like a 1-bit integer: `0`/`1` literals are valid in a `DEFAULT` clause, an `INSERT ... VALUES` list, or an `UPDATE ... SET`, with no special casting. |
| [T-SQL `ALTER COLUMN <c> <type>` re-states the column's last-known nullability → PostgreSQL (both directions)](alter-column-nullability.md) | tsql → postgresql | T-SQL's `ALTER COLUMN <c> <type>` bakes type *and* nullability into one clause — omitting a `NULL`/`NOT NULL` keyword does not mean "leave nullability alone," it means "make the column nullable," silently dropping an existing `NOT NULL` the statement never mentioned. |

#### Temporary tables and the `CREATE TABLE AS SELECT` ↔ `SELECT INTO` idiom

| Article | Direction | Description |
|---|---|---|
| [Session-scoped temp tables (PostgreSQL `TEMP` / T-SQL `#temp` / MySQL `TEMPORARY`) → Oracle `GLOBAL TEMPORARY`](session-temp-tables-to-oracle.md) | tsql/postgresql/mysql → oracle | A PostgreSQL `TEMP`/`TEMPORARY` table, a T-SQL `#temp` table, and a MySQL `TEMPORARY` table are all **session-scoped**: their definition and rows live only for the current connection, and — critically — their rows **survive an intervening `COMMIT`**. |

#### Foreign-key referential actions

| Article | Direction | Description |
|---|---|---|
| [`ON UPDATE <action>` (PostgreSQL / T-SQL / MySQL) → Oracle](fk-on-update-action-to-oracle.md) | tsql/postgresql/mysql → oracle | `REFERENCES p(id) ON DELETE CASCADE ON UPDATE CASCADE` propagates both a delete and a primary-key update on the parent to the child. |

#### Sequences

| Article | Direction | Description |
|---|---|---|
| [One-word vs two-word negative options (Oracle `NOMAXVALUE`/`NOCYCLE` vs T-SQL/PostgreSQL `NO MAXVALUE`/`NO CYCLE`)](sequence-negative-option-spelling.md) | oracle ↔ tsql/postgresql | `CREATE SEQUENCE … NO MAXVALUE NO CYCLE` (T-SQL, PostgreSQL) and `CREATE SEQUENCE … NOMAXVALUE NOCYCLE` (Oracle) both mean "no upper bound, do not wrap around" — the same option, spelled as two words on some engines and fused to one word on Oracle. |

#### Storage and physical options

| Article | Direction | Description |
|---|---|---|
| [T-SQL index `WITH (FILLFACTOR = n)` → Oracle / MySQL](tsql-index-fillfactor.md) | tsql → oracle/mysql | `FILLFACTOR` reserves free space per index page for future inserts — a physical storage tuning knob with no logical effect on query results. |

#### T-SQL CREATE TYPE alias resolved to its base type

| Article | Direction | Description |
|---|---|---|
| [T-SQL `CREATE TYPE x FROM base` alias type → resolved to its base type everywhere](create-type-alias-harvested.md) | tsql → oracle/postgresql/mysql | T-SQL lets a script define a named alias type (`CREATE TYPE [dbo].[Name] FROM [nvarchar](50) NULL`) and then use `[dbo].[Name]` as an ordinary column type elsewhere in the same script. |

#### DROP emitted idempotently

| Article | Direction | Description |
|---|---|---|
| [A plain `DROP TABLE t` → `DROP TABLE IF EXISTS t` on PostgreSQL](drop-table-idempotent-if-exists.md) | tsql → postgresql | A migration script is meant to be re-runnable against a target that may already have run it once before — a bare `DROP TABLE t` errors on a second run if the table is already gone, stopping the whole script partway through. |

#### DDL guards

| Article | Direction | Description |
|---|---|---|
| [T-SQL system-catalog DDL guards (`OBJECT_ID`/`sys.objects`/`sys.columns`) → native `IF [NOT] EXISTS` or a synthesized per-target probe](tsql-existence-guard-catalog-probes.md) | tsql → oracle/postgresql/mysql | A T-SQL migration script often guards a `CREATE`/`DROP`/`ALTER` with a system-catalog existence check — `IF OBJECT_ID('t') IS NOT NULL DROP TABLE t` or `IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID('t')) BEGIN CREATE TABLE t (...) END` — so a second run of the same script doesn't fail on an object that's already there (or already gone). |

### T-SQL as target

| [Foreign-key referential actions](#foreign-key-referential-actions-1) | [Sequences](#sequences-1) | [MySQL `ENUM` degrade — open limitation](#mysql-enum-degrade--open-limitation) | [Synthesized identifiers for anonymous constructs](#synthesized-identifiers-for-anonymous-constructs) | [Non-negativity constraint synthesis](#non-negativity-constraint-synthesis) | [TRUNCATE options](#truncate-options) | [ALTER COLUMN DROP DEFAULT](#alter-column-drop-default) | [Oracle ALTER TABLE ADD (...) parenthesized-list unwrapping](#oracle-alter-table-add--parenthesized-list-unwrapping) | [DDL guards](#ddl-guards-1) |
|---|---|---|---|---|---|---|---|---|

#### Foreign-key referential actions

| Article | Direction | Description |
|---|---|---|
| [Self-referencing FK cascade (MySQL) → T-SQL](self-referencing-fk-cascade.md) | mysql → tsql | `FOREIGN KEY (mgr) REFERENCES emp(id) ON DELETE SET NULL`, where the FK references its **own** table (an employee/manager hierarchy). |

#### Sequences

| Article | Direction | Description |
|---|---|---|
| [One-word vs two-word negative options (Oracle `NOMAXVALUE`/`NOCYCLE` vs T-SQL/PostgreSQL `NO MAXVALUE`/`NO CYCLE`)](sequence-negative-option-spelling.md) | oracle ↔ tsql/postgresql | `CREATE SEQUENCE … NO MAXVALUE NO CYCLE` (T-SQL, PostgreSQL) and `CREATE SEQUENCE … NOMAXVALUE NOCYCLE` (Oracle) both mean "no upper bound, do not wrap around" — the same option, spelled as two words on some engines and fused to one word on Oracle. |

#### MySQL `ENUM` degrade — open limitation

| Article | Direction | Description |
|---|---|---|
| [`ENUM('lo','mid','hi')` (MySQL) → PostgreSQL / T-SQL / Oracle VARCHAR + CHECK](mysql-enum-to-varchar-check.md) | mysql → tsql/oracle/postgresql | A MySQL `ENUM` column stores one of a fixed value list, and — the part that matters here — **orders by declaration index**, not alphabetically: `ENUM('lo','mid','hi')` sorts `lo < mid < hi` regardless of the values' lexical order. |

#### Synthesized identifiers for anonymous constructs

| Article | Direction | Description |
|---|---|---|
| [Nameless `CREATE INDEX ON t(col)` (PostgreSQL) → T-SQL](nameless-create-index-to-tsql.md) | postgresql → tsql | PostgreSQL allows `CREATE INDEX ON t (col)` with no index name — the server picks one internally (`t_col_idx`-shaped, but never surfaced to the script). |

#### Non-negativity constraint synthesis

| Article | Direction | Description |
|---|---|---|
| [MySQL `UNSIGNED` → widened signed type + synthesized `CHECK (col >= 0)`](mysql-unsigned-check-synthesis.md) | mysql → tsql/oracle/postgresql | A MySQL `UNSIGNED` integer column can never hold a negative value — that's enforced structurally by the column's own type, not by a constraint. |

#### TRUNCATE options

| Article | Direction | Description |
|---|---|---|
| [PostgreSQL `TRUNCATE ... RESTART IDENTITY / CASCADE` → Oracle/MySQL/T-SQL](truncate-restart-identity-cascade.md) | postgresql → oracle/mysql/tsql | PostgreSQL's `TRUNCATE` defaults to *keeping* an identity column's next value where it was (`CONTINUE IDENTITY` is implicit), and only resets it when you say `RESTART IDENTITY` explicitly; the same statement's `CASCADE` also truncates every table with a foreign key pointing at the truncated one. |

#### ALTER COLUMN DROP DEFAULT

| Article | Direction | Description |
|---|---|---|
| [PostgreSQL `ALTER COLUMN a DROP DEFAULT` → Oracle `MODIFY ... DEFAULT NULL`, T-SQL dynamic-SQL script](alter-column-drop-default.md) | postgresql → oracle/tsql | PostgreSQL's `ALTER TABLE t ALTER COLUMN a DROP DEFAULT` removes a column's default expression by name-free reference — no other engine has an equivalent "just remove whatever default is there" clause. |

#### Oracle ALTER TABLE ADD (...) parenthesized-list unwrapping

| Article | Direction | Description |
|---|---|---|
| [Oracle `ALTER TABLE ... ADD ( ... )` (parenthesized element list) → an unwrapped `ADD` clause](oracle-alter-add-parenthesized-unwrap.md) | oracle → tsql/postgresql/mysql | Oracle allows one or more table elements (columns, constraints) to be added in a single parenthesized list — `ALTER TABLE t ADD (CONSTRAINT fk FOREIGN KEY (col) REFERENCES p(id))`. |

#### DDL guards

| Article | Direction | Description |
|---|---|---|
| [Oracle catalog probes inside dynamic DDL (`user_indexes`/`user_tab_cols`) → the target's own system view](oracle-catalog-probe-rewritten-per-target.md) | oracle → tsql/postgresql | An Oracle PL/SQL script sometimes checks its own data dictionary before running dynamic DDL through `EXECUTE IMMEDIATE` — for example resolving an index's owning table before a table-less `DROP INDEX` (Oracle names only the index; T-SQL requires the table too, error 159), or gating an `ALTER TABLE ... MODIFY` on whether a column already has the target shape. |

### Oracle as source

| [Sequences](#sequences-2) | [Oracle RAW(16) DEFAULT SYS_GUID() → PostgreSQL BYTEA default](#oracle-raw16-default-sys_guid--postgresql-bytea-default) | [Oracle ALTER TABLE ADD (...) parenthesized-list unwrapping](#oracle-alter-table-add--parenthesized-list-unwrapping-1) | [DDL guards](#ddl-guards-2) |
|---|---|---|---|

#### Sequences

| Article | Direction | Description |
|---|---|---|
| [One-word vs two-word negative options (Oracle `NOMAXVALUE`/`NOCYCLE` vs T-SQL/PostgreSQL `NO MAXVALUE`/`NO CYCLE`)](sequence-negative-option-spelling.md) | oracle ↔ tsql/postgresql | `CREATE SEQUENCE … NO MAXVALUE NO CYCLE` (T-SQL, PostgreSQL) and `CREATE SEQUENCE … NOMAXVALUE NOCYCLE` (Oracle) both mean "no upper bound, do not wrap around" — the same option, spelled as two words on some engines and fused to one word on Oracle. |

#### Oracle RAW(16) DEFAULT SYS_GUID() → PostgreSQL BYTEA default

| Article | Direction | Description |
|---|---|---|
| [Oracle `RAW(16) DEFAULT SYS_GUID()` → PostgreSQL `BYTEA` with a matching `DECODE(...)` default](raw-guid-default-bytea.md) | oracle → postgresql | `RAW(16) DEFAULT SYS_GUID()` is Oracle's idiom for a binary-GUID primary key: `SYS_GUID()` generates a 16-byte raw value used directly as the default. |

#### Oracle ALTER TABLE ADD (...) parenthesized-list unwrapping

| Article | Direction | Description |
|---|---|---|
| [Oracle `ALTER TABLE ... ADD ( ... )` (parenthesized element list) → an unwrapped `ADD` clause](oracle-alter-add-parenthesized-unwrap.md) | oracle → tsql/postgresql/mysql | Oracle allows one or more table elements (columns, constraints) to be added in a single parenthesized list — `ALTER TABLE t ADD (CONSTRAINT fk FOREIGN KEY (col) REFERENCES p(id))`. |

#### DDL guards

| Article | Direction | Description |
|---|---|---|
| [Oracle catalog probes inside dynamic DDL (`user_indexes`/`user_tab_cols`) → the target's own system view](oracle-catalog-probe-rewritten-per-target.md) | oracle → tsql/postgresql | An Oracle PL/SQL script sometimes checks its own data dictionary before running dynamic DDL through `EXECUTE IMMEDIATE` — for example resolving an index's owning table before a table-less `DROP INDEX` (Oracle names only the index; T-SQL requires the table too, error 159), or gating an `ALTER TABLE ... MODIFY` on whether a column already has the target shape. |

### Oracle as target

| [The SERIAL / IDENTITY / AUTO_INCREMENT triangle](#the-serial--identity--auto_increment-triangle-1) | [Temporary tables and the `CREATE TABLE AS SELECT` ↔ `SELECT INTO` idiom](#temporary-tables-and-the-create-table-as-select--select-into-idiom-1) | [Foreign-key referential actions](#foreign-key-referential-actions-2) | [Sequences](#sequences-3) | [Storage and physical options](#storage-and-physical-options-1) | [MySQL `ENUM` degrade — open limitation](#mysql-enum-degrade--open-limitation-1) | [Non-negativity constraint synthesis](#non-negativity-constraint-synthesis-1) | [TRUNCATE options](#truncate-options-1) | [T-SQL CREATE TYPE alias resolved to its base type](#t-sql-create-type-alias-resolved-to-its-base-type-1) | [ALTER COLUMN DROP DEFAULT](#alter-column-drop-default-1) | [DDL guards](#ddl-guards-3) |
|---|---|---|---|---|---|---|---|---|---|---|

#### The SERIAL / IDENTITY / AUTO_INCREMENT triangle

| Article | Direction | Description |
|---|---|---|
| [T-SQL identity-scope reads (`SCOPE_IDENTITY()`/`@@IDENTITY`/`IDENT_CURRENT()`) → PostgreSQL / Oracle / MySQL](tsql-identity-scope-reads.md) | tsql → oracle/postgresql/mysql | T-SQL exposes the last-generated identity value through three functions with different scoping rules (current scope / current session / a named table). |

#### Temporary tables and the `CREATE TABLE AS SELECT` ↔ `SELECT INTO` idiom

| Article | Direction | Description |
|---|---|---|
| [Session-scoped temp tables (PostgreSQL `TEMP` / T-SQL `#temp` / MySQL `TEMPORARY`) → Oracle `GLOBAL TEMPORARY`](session-temp-tables-to-oracle.md) | tsql/postgresql/mysql → oracle | A PostgreSQL `TEMP`/`TEMPORARY` table, a T-SQL `#temp` table, and a MySQL `TEMPORARY` table are all **session-scoped**: their definition and rows live only for the current connection, and — critically — their rows **survive an intervening `COMMIT`**. |

#### Foreign-key referential actions

| Article | Direction | Description |
|---|---|---|
| [`ON UPDATE <action>` (PostgreSQL / T-SQL / MySQL) → Oracle](fk-on-update-action-to-oracle.md) | tsql/postgresql/mysql → oracle | `REFERENCES p(id) ON DELETE CASCADE ON UPDATE CASCADE` propagates both a delete and a primary-key update on the parent to the child. |

#### Sequences

| Article | Direction | Description |
|---|---|---|
| [One-word vs two-word negative options (Oracle `NOMAXVALUE`/`NOCYCLE` vs T-SQL/PostgreSQL `NO MAXVALUE`/`NO CYCLE`)](sequence-negative-option-spelling.md) | oracle ↔ tsql/postgresql | `CREATE SEQUENCE … NO MAXVALUE NO CYCLE` (T-SQL, PostgreSQL) and `CREATE SEQUENCE … NOMAXVALUE NOCYCLE` (Oracle) both mean "no upper bound, do not wrap around" — the same option, spelled as two words on some engines and fused to one word on Oracle. |

#### Storage and physical options

| Article | Direction | Description |
|---|---|---|
| [T-SQL index `WITH (FILLFACTOR = n)` → Oracle / MySQL](tsql-index-fillfactor.md) | tsql → oracle/mysql | `FILLFACTOR` reserves free space per index page for future inserts — a physical storage tuning knob with no logical effect on query results. |

#### MySQL `ENUM` degrade — open limitation

| Article | Direction | Description |
|---|---|---|
| [`ENUM('lo','mid','hi')` (MySQL) → PostgreSQL / T-SQL / Oracle VARCHAR + CHECK](mysql-enum-to-varchar-check.md) | mysql → tsql/oracle/postgresql | A MySQL `ENUM` column stores one of a fixed value list, and — the part that matters here — **orders by declaration index**, not alphabetically: `ENUM('lo','mid','hi')` sorts `lo < mid < hi` regardless of the values' lexical order. |

#### Non-negativity constraint synthesis

| Article | Direction | Description |
|---|---|---|
| [MySQL `UNSIGNED` → widened signed type + synthesized `CHECK (col >= 0)`](mysql-unsigned-check-synthesis.md) | mysql → tsql/oracle/postgresql | A MySQL `UNSIGNED` integer column can never hold a negative value — that's enforced structurally by the column's own type, not by a constraint. |

#### TRUNCATE options

| Article | Direction | Description |
|---|---|---|
| [PostgreSQL `TRUNCATE ... RESTART IDENTITY / CASCADE` → Oracle/MySQL/T-SQL](truncate-restart-identity-cascade.md) | postgresql → oracle/mysql/tsql | PostgreSQL's `TRUNCATE` defaults to *keeping* an identity column's next value where it was (`CONTINUE IDENTITY` is implicit), and only resets it when you say `RESTART IDENTITY` explicitly; the same statement's `CASCADE` also truncates every table with a foreign key pointing at the truncated one. |

#### T-SQL CREATE TYPE alias resolved to its base type

| Article | Direction | Description |
|---|---|---|
| [T-SQL `CREATE TYPE x FROM base` alias type → resolved to its base type everywhere](create-type-alias-harvested.md) | tsql → oracle/postgresql/mysql | T-SQL lets a script define a named alias type (`CREATE TYPE [dbo].[Name] FROM [nvarchar](50) NULL`) and then use `[dbo].[Name]` as an ordinary column type elsewhere in the same script. |

#### ALTER COLUMN DROP DEFAULT

| Article | Direction | Description |
|---|---|---|
| [PostgreSQL `ALTER COLUMN a DROP DEFAULT` → Oracle `MODIFY ... DEFAULT NULL`, T-SQL dynamic-SQL script](alter-column-drop-default.md) | postgresql → oracle/tsql | PostgreSQL's `ALTER TABLE t ALTER COLUMN a DROP DEFAULT` removes a column's default expression by name-free reference — no other engine has an equivalent "just remove whatever default is there" clause. |

#### DDL guards

| Article | Direction | Description |
|---|---|---|
| [T-SQL system-catalog DDL guards (`OBJECT_ID`/`sys.objects`/`sys.columns`) → native `IF [NOT] EXISTS` or a synthesized per-target probe](tsql-existence-guard-catalog-probes.md) | tsql → oracle/postgresql/mysql | A T-SQL migration script often guards a `CREATE`/`DROP`/`ALTER` with a system-catalog existence check — `IF OBJECT_ID('t') IS NOT NULL DROP TABLE t` or `IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID('t')) BEGIN CREATE TABLE t (...) END` — so a second run of the same script doesn't fail on an object that's already there (or already gone). |

### PostgreSQL as source

| [Temporary tables and the `CREATE TABLE AS SELECT` ↔ `SELECT INTO` idiom](#temporary-tables-and-the-create-table-as-select--select-into-idiom-2) | [Foreign-key referential actions](#foreign-key-referential-actions-3) | [Sequences](#sequences-4) | [Synthesized identifiers for anonymous constructs](#synthesized-identifiers-for-anonymous-constructs-1) | [TRUNCATE options](#truncate-options-2) | [ALTER COLUMN DROP DEFAULT](#alter-column-drop-default-2) |
|---|---|---|---|---|---|

#### Temporary tables and the `CREATE TABLE AS SELECT` ↔ `SELECT INTO` idiom

| Article | Direction | Description |
|---|---|---|
| [Session-scoped temp tables (PostgreSQL `TEMP` / T-SQL `#temp` / MySQL `TEMPORARY`) → Oracle `GLOBAL TEMPORARY`](session-temp-tables-to-oracle.md) | tsql/postgresql/mysql → oracle | A PostgreSQL `TEMP`/`TEMPORARY` table, a T-SQL `#temp` table, and a MySQL `TEMPORARY` table are all **session-scoped**: their definition and rows live only for the current connection, and — critically — their rows **survive an intervening `COMMIT`**. |

#### Foreign-key referential actions

| Article | Direction | Description |
|---|---|---|
| [`ON UPDATE <action>` (PostgreSQL / T-SQL / MySQL) → Oracle](fk-on-update-action-to-oracle.md) | tsql/postgresql/mysql → oracle | `REFERENCES p(id) ON DELETE CASCADE ON UPDATE CASCADE` propagates both a delete and a primary-key update on the parent to the child. |

#### Sequences

| Article | Direction | Description |
|---|---|---|
| [One-word vs two-word negative options (Oracle `NOMAXVALUE`/`NOCYCLE` vs T-SQL/PostgreSQL `NO MAXVALUE`/`NO CYCLE`)](sequence-negative-option-spelling.md) | oracle ↔ tsql/postgresql | `CREATE SEQUENCE … NO MAXVALUE NO CYCLE` (T-SQL, PostgreSQL) and `CREATE SEQUENCE … NOMAXVALUE NOCYCLE` (Oracle) both mean "no upper bound, do not wrap around" — the same option, spelled as two words on some engines and fused to one word on Oracle. |

#### Synthesized identifiers for anonymous constructs

| Article | Direction | Description |
|---|---|---|
| [Nameless `CREATE INDEX ON t(col)` (PostgreSQL) → T-SQL](nameless-create-index-to-tsql.md) | postgresql → tsql | PostgreSQL allows `CREATE INDEX ON t (col)` with no index name — the server picks one internally (`t_col_idx`-shaped, but never surfaced to the script). |

#### TRUNCATE options

| Article | Direction | Description |
|---|---|---|
| [PostgreSQL `TRUNCATE ... RESTART IDENTITY / CASCADE` → Oracle/MySQL/T-SQL](truncate-restart-identity-cascade.md) | postgresql → oracle/mysql/tsql | PostgreSQL's `TRUNCATE` defaults to *keeping* an identity column's next value where it was (`CONTINUE IDENTITY` is implicit), and only resets it when you say `RESTART IDENTITY` explicitly; the same statement's `CASCADE` also truncates every table with a foreign key pointing at the truncated one. |

#### ALTER COLUMN DROP DEFAULT

| Article | Direction | Description |
|---|---|---|
| [PostgreSQL `ALTER COLUMN a DROP DEFAULT` → Oracle `MODIFY ... DEFAULT NULL`, T-SQL dynamic-SQL script](alter-column-drop-default.md) | postgresql → oracle/tsql | PostgreSQL's `ALTER TABLE t ALTER COLUMN a DROP DEFAULT` removes a column's default expression by name-free reference — no other engine has an equivalent "just remove whatever default is there" clause. |

### PostgreSQL as target

| [The SERIAL / IDENTITY / AUTO_INCREMENT triangle](#the-serial--identity--auto_increment-triangle-2) | [Cross-statement schema-state-driven coercion](#cross-statement-schema-state-driven-coercion-1) | [Sequences](#sequences-5) | [MySQL `ENUM` degrade — open limitation](#mysql-enum-degrade--open-limitation-2) | [Non-negativity constraint synthesis](#non-negativity-constraint-synthesis-2) | [T-SQL CREATE TYPE alias resolved to its base type](#t-sql-create-type-alias-resolved-to-its-base-type-2) | [Oracle RAW(16) DEFAULT SYS_GUID() → PostgreSQL BYTEA default](#oracle-raw16-default-sys_guid--postgresql-bytea-default-1) | [Oracle ALTER TABLE ADD (...) parenthesized-list unwrapping](#oracle-alter-table-add--parenthesized-list-unwrapping-2) | [DROP emitted idempotently](#drop-emitted-idempotently-1) | [DDL guards](#ddl-guards-4) |
|---|---|---|---|---|---|---|---|---|---|

#### The SERIAL / IDENTITY / AUTO_INCREMENT triangle

| Article | Direction | Description |
|---|---|---|
| [T-SQL identity-scope reads (`SCOPE_IDENTITY()`/`@@IDENTITY`/`IDENT_CURRENT()`) → PostgreSQL / Oracle / MySQL](tsql-identity-scope-reads.md) | tsql → oracle/postgresql/mysql | T-SQL exposes the last-generated identity value through three functions with different scoping rules (current scope / current session / a named table). |

#### Cross-statement schema-state-driven coercion

| Article | Direction | Description |
|---|---|---|
| [T-SQL `BIT` `0`/`1` values (defaults, `INSERT`, `UPDATE`, incl. inside procedure bodies) → PostgreSQL `BOOLEAN`](tsql-bit-to-postgresql-boolean.md) | tsql → postgresql | T-SQL's `BIT` type behaves like a 1-bit integer: `0`/`1` literals are valid in a `DEFAULT` clause, an `INSERT ... VALUES` list, or an `UPDATE ... SET`, with no special casting. |
| [T-SQL `ALTER COLUMN <c> <type>` re-states the column's last-known nullability → PostgreSQL (both directions)](alter-column-nullability.md) | tsql → postgresql | T-SQL's `ALTER COLUMN <c> <type>` bakes type *and* nullability into one clause — omitting a `NULL`/`NOT NULL` keyword does not mean "leave nullability alone," it means "make the column nullable," silently dropping an existing `NOT NULL` the statement never mentioned. |

#### Sequences

| Article | Direction | Description |
|---|---|---|
| [One-word vs two-word negative options (Oracle `NOMAXVALUE`/`NOCYCLE` vs T-SQL/PostgreSQL `NO MAXVALUE`/`NO CYCLE`)](sequence-negative-option-spelling.md) | oracle ↔ tsql/postgresql | `CREATE SEQUENCE … NO MAXVALUE NO CYCLE` (T-SQL, PostgreSQL) and `CREATE SEQUENCE … NOMAXVALUE NOCYCLE` (Oracle) both mean "no upper bound, do not wrap around" — the same option, spelled as two words on some engines and fused to one word on Oracle. |

#### MySQL `ENUM` degrade — open limitation

| Article | Direction | Description |
|---|---|---|
| [`ENUM('lo','mid','hi')` (MySQL) → PostgreSQL / T-SQL / Oracle VARCHAR + CHECK](mysql-enum-to-varchar-check.md) | mysql → tsql/oracle/postgresql | A MySQL `ENUM` column stores one of a fixed value list, and — the part that matters here — **orders by declaration index**, not alphabetically: `ENUM('lo','mid','hi')` sorts `lo < mid < hi` regardless of the values' lexical order. |

#### Non-negativity constraint synthesis

| Article | Direction | Description |
|---|---|---|
| [MySQL `UNSIGNED` → widened signed type + synthesized `CHECK (col >= 0)`](mysql-unsigned-check-synthesis.md) | mysql → tsql/oracle/postgresql | A MySQL `UNSIGNED` integer column can never hold a negative value — that's enforced structurally by the column's own type, not by a constraint. |

#### T-SQL CREATE TYPE alias resolved to its base type

| Article | Direction | Description |
|---|---|---|
| [T-SQL `CREATE TYPE x FROM base` alias type → resolved to its base type everywhere](create-type-alias-harvested.md) | tsql → oracle/postgresql/mysql | T-SQL lets a script define a named alias type (`CREATE TYPE [dbo].[Name] FROM [nvarchar](50) NULL`) and then use `[dbo].[Name]` as an ordinary column type elsewhere in the same script. |

#### Oracle RAW(16) DEFAULT SYS_GUID() → PostgreSQL BYTEA default

| Article | Direction | Description |
|---|---|---|
| [Oracle `RAW(16) DEFAULT SYS_GUID()` → PostgreSQL `BYTEA` with a matching `DECODE(...)` default](raw-guid-default-bytea.md) | oracle → postgresql | `RAW(16) DEFAULT SYS_GUID()` is Oracle's idiom for a binary-GUID primary key: `SYS_GUID()` generates a 16-byte raw value used directly as the default. |

#### Oracle ALTER TABLE ADD (...) parenthesized-list unwrapping

| Article | Direction | Description |
|---|---|---|
| [Oracle `ALTER TABLE ... ADD ( ... )` (parenthesized element list) → an unwrapped `ADD` clause](oracle-alter-add-parenthesized-unwrap.md) | oracle → tsql/postgresql/mysql | Oracle allows one or more table elements (columns, constraints) to be added in a single parenthesized list — `ALTER TABLE t ADD (CONSTRAINT fk FOREIGN KEY (col) REFERENCES p(id))`. |

#### DROP emitted idempotently

| Article | Direction | Description |
|---|---|---|
| [A plain `DROP TABLE t` → `DROP TABLE IF EXISTS t` on PostgreSQL](drop-table-idempotent-if-exists.md) | tsql → postgresql | A migration script is meant to be re-runnable against a target that may already have run it once before — a bare `DROP TABLE t` errors on a second run if the table is already gone, stopping the whole script partway through. |

#### DDL guards

| Article | Direction | Description |
|---|---|---|
| [T-SQL system-catalog DDL guards (`OBJECT_ID`/`sys.objects`/`sys.columns`) → native `IF [NOT] EXISTS` or a synthesized per-target probe](tsql-existence-guard-catalog-probes.md) | tsql → oracle/postgresql/mysql | A T-SQL migration script often guards a `CREATE`/`DROP`/`ALTER` with a system-catalog existence check — `IF OBJECT_ID('t') IS NOT NULL DROP TABLE t` or `IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID('t')) BEGIN CREATE TABLE t (...) END` — so a second run of the same script doesn't fail on an object that's already there (or already gone). |
| [Oracle catalog probes inside dynamic DDL (`user_indexes`/`user_tab_cols`) → the target's own system view](oracle-catalog-probe-rewritten-per-target.md) | oracle → tsql/postgresql | An Oracle PL/SQL script sometimes checks its own data dictionary before running dynamic DDL through `EXECUTE IMMEDIATE` — for example resolving an index's owning table before a table-less `DROP INDEX` (Oracle names only the index; T-SQL requires the table too, error 159), or gating an `ALTER TABLE ... MODIFY` on whether a column already has the target shape. |

### MySQL as source

| [Temporary tables and the `CREATE TABLE AS SELECT` ↔ `SELECT INTO` idiom](#temporary-tables-and-the-create-table-as-select--select-into-idiom-3) | [Foreign-key referential actions](#foreign-key-referential-actions-4) | [MySQL `ENUM` degrade — open limitation](#mysql-enum-degrade--open-limitation-3) | [Non-negativity constraint synthesis](#non-negativity-constraint-synthesis-3) |
|---|---|---|---|

#### Temporary tables and the `CREATE TABLE AS SELECT` ↔ `SELECT INTO` idiom

| Article | Direction | Description |
|---|---|---|
| [Session-scoped temp tables (PostgreSQL `TEMP` / T-SQL `#temp` / MySQL `TEMPORARY`) → Oracle `GLOBAL TEMPORARY`](session-temp-tables-to-oracle.md) | tsql/postgresql/mysql → oracle | A PostgreSQL `TEMP`/`TEMPORARY` table, a T-SQL `#temp` table, and a MySQL `TEMPORARY` table are all **session-scoped**: their definition and rows live only for the current connection, and — critically — their rows **survive an intervening `COMMIT`**. |

#### Foreign-key referential actions

| Article | Direction | Description |
|---|---|---|
| [`ON UPDATE <action>` (PostgreSQL / T-SQL / MySQL) → Oracle](fk-on-update-action-to-oracle.md) | tsql/postgresql/mysql → oracle | `REFERENCES p(id) ON DELETE CASCADE ON UPDATE CASCADE` propagates both a delete and a primary-key update on the parent to the child. |
| [Self-referencing FK cascade (MySQL) → T-SQL](self-referencing-fk-cascade.md) | mysql → tsql | `FOREIGN KEY (mgr) REFERENCES emp(id) ON DELETE SET NULL`, where the FK references its **own** table (an employee/manager hierarchy). |

#### MySQL `ENUM` degrade — open limitation

| Article | Direction | Description |
|---|---|---|
| [`ENUM('lo','mid','hi')` (MySQL) → PostgreSQL / T-SQL / Oracle VARCHAR + CHECK](mysql-enum-to-varchar-check.md) | mysql → tsql/oracle/postgresql | A MySQL `ENUM` column stores one of a fixed value list, and — the part that matters here — **orders by declaration index**, not alphabetically: `ENUM('lo','mid','hi')` sorts `lo < mid < hi` regardless of the values' lexical order. |

#### Non-negativity constraint synthesis

| Article | Direction | Description |
|---|---|---|
| [MySQL `UNSIGNED` → widened signed type + synthesized `CHECK (col >= 0)`](mysql-unsigned-check-synthesis.md) | mysql → tsql/oracle/postgresql | A MySQL `UNSIGNED` integer column can never hold a negative value — that's enforced structurally by the column's own type, not by a constraint. |

### MySQL as target

| [The SERIAL / IDENTITY / AUTO_INCREMENT triangle](#the-serial--identity--auto_increment-triangle-3) | [Storage and physical options](#storage-and-physical-options-2) | [TRUNCATE options](#truncate-options-3) | [T-SQL CREATE TYPE alias resolved to its base type](#t-sql-create-type-alias-resolved-to-its-base-type-3) | [Oracle ALTER TABLE ADD (...) parenthesized-list unwrapping](#oracle-alter-table-add--parenthesized-list-unwrapping-3) | [DDL guards](#ddl-guards-5) |
|---|---|---|---|---|---|

#### The SERIAL / IDENTITY / AUTO_INCREMENT triangle

| Article | Direction | Description |
|---|---|---|
| [T-SQL identity-scope reads (`SCOPE_IDENTITY()`/`@@IDENTITY`/`IDENT_CURRENT()`) → PostgreSQL / Oracle / MySQL](tsql-identity-scope-reads.md) | tsql → oracle/postgresql/mysql | T-SQL exposes the last-generated identity value through three functions with different scoping rules (current scope / current session / a named table). |

#### Storage and physical options

| Article | Direction | Description |
|---|---|---|
| [T-SQL index `WITH (FILLFACTOR = n)` → Oracle / MySQL](tsql-index-fillfactor.md) | tsql → oracle/mysql | `FILLFACTOR` reserves free space per index page for future inserts — a physical storage tuning knob with no logical effect on query results. |

#### TRUNCATE options

| Article | Direction | Description |
|---|---|---|
| [PostgreSQL `TRUNCATE ... RESTART IDENTITY / CASCADE` → Oracle/MySQL/T-SQL](truncate-restart-identity-cascade.md) | postgresql → oracle/mysql/tsql | PostgreSQL's `TRUNCATE` defaults to *keeping* an identity column's next value where it was (`CONTINUE IDENTITY` is implicit), and only resets it when you say `RESTART IDENTITY` explicitly; the same statement's `CASCADE` also truncates every table with a foreign key pointing at the truncated one. |

#### T-SQL CREATE TYPE alias resolved to its base type

| Article | Direction | Description |
|---|---|---|
| [T-SQL `CREATE TYPE x FROM base` alias type → resolved to its base type everywhere](create-type-alias-harvested.md) | tsql → oracle/postgresql/mysql | T-SQL lets a script define a named alias type (`CREATE TYPE [dbo].[Name] FROM [nvarchar](50) NULL`) and then use `[dbo].[Name]` as an ordinary column type elsewhere in the same script. |

#### Oracle ALTER TABLE ADD (...) parenthesized-list unwrapping

| Article | Direction | Description |
|---|---|---|
| [Oracle `ALTER TABLE ... ADD ( ... )` (parenthesized element list) → an unwrapped `ADD` clause](oracle-alter-add-parenthesized-unwrap.md) | oracle → tsql/postgresql/mysql | Oracle allows one or more table elements (columns, constraints) to be added in a single parenthesized list — `ALTER TABLE t ADD (CONSTRAINT fk FOREIGN KEY (col) REFERENCES p(id))`. |

#### DDL guards

| Article | Direction | Description |
|---|---|---|
| [T-SQL system-catalog DDL guards (`OBJECT_ID`/`sys.objects`/`sys.columns`) → native `IF [NOT] EXISTS` or a synthesized per-target probe](tsql-existence-guard-catalog-probes.md) | tsql → oracle/postgresql/mysql | A T-SQL migration script often guards a `CREATE`/`DROP`/`ALTER` with a system-catalog existence check — `IF OBJECT_ID('t') IS NOT NULL DROP TABLE t` or `IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID('t')) BEGIN CREATE TABLE t (...) END` — so a second run of the same script doesn't fail on an object that's already there (or already gone). |

### Cross-engine / multi-directional

| [The SERIAL / IDENTITY / AUTO_INCREMENT triangle](#the-serial--identity--auto_increment-triangle-4) | [Cross-statement schema-state-driven coercion](#cross-statement-schema-state-driven-coercion-2) | [Temporary tables and the `CREATE TABLE AS SELECT` ↔ `SELECT INTO` idiom](#temporary-tables-and-the-create-table-as-select--select-into-idiom-4) | [Synthesized identifiers for anonymous constructs](#synthesized-identifiers-for-anonymous-constructs-2) | [Computed columns](#computed-columns) | [Inline DDL attributes decomposed into standalone statements](#inline-ddl-attributes-decomposed-into-standalone-statements) | [Inline column-level constraints relocated to table-level](#inline-column-level-constraints-relocated-to-table-level) |
|---|---|---|---|---|---|---|

#### The SERIAL / IDENTITY / AUTO_INCREMENT triangle

| Article | Direction | Description |
|---|---|---|
| [Auto-incrementing key columns (PostgreSQL `SERIAL` / T-SQL `IDENTITY` / Oracle `GENERATED … AS IDENTITY` / MySQL `AUTO_INCREMENT`)](auto-incrementing-keys.md) | cross-engine | Each engine spells "the database assigns this column's value from an internal counter" differently: PostgreSQL `SERIAL`/`BIGSERIAL` (sugar for an integer + an owned sequence + a default), T-SQL `IDENTITY(seed, step)`, Oracle `GENERATED ALWAYS\|BY DEFAULT AS IDENTITY [(START WITH s INCREMENT BY i …)]`, MySQL `AUTO_INCREMENT` (a single table-level counter, no per-column seed/step). |

#### Cross-statement schema-state-driven coercion

| Article | Direction | Description |
|---|---|---|
| [Oracle bare `NUMBER` (no precision/scale) → role-aware numeric](oracle-bare-number-role-aware.md) | cross-engine | Oracle's unqualified `NUMBER` — no precision or scale — is overloaded. |

#### Temporary tables and the `CREATE TABLE AS SELECT` ↔ `SELECT INTO` idiom

| Article | Direction | Description |
|---|---|---|
| [`CREATE TABLE AS SELECT` ↔ `SELECT ... INTO` for ordinary (non-temporary) tables](ctas-vs-select-into.md) | cross-engine | This extends the entry above from *temp* tables specifically to *any* table: T-SQL has no `CREATE TABLE ... AS SELECT` syntax at all — whether or not the table is session-scoped — so any CTAS from another source dialect must become a T-SQL `SELECT ... INTO`. |

#### Synthesized identifiers for anonymous constructs

| Article | Direction | Description |
|---|---|---|
| [Unnamed derived-table / `SELECT ... INTO` projections → synthesized `uq_col1` (T-SQL)](unnamed-projection-synthesized-name.md) | cross-engine | `SELECT (SELECT a) t` or `SELECT (SELECT 1) t` — a derived table whose single projected column is a bare parameter reference or a literal, with no alias — is legal on PostgreSQL/MySQL/Oracle (the column gets an engine-assigned display name that nothing else references). |

#### Computed columns

| Article | Direction | Description |
|---|---|---|
| [`GENERATED ALWAYS AS (expr)` computed columns (cross-engine)](computed-columns-generated-always.md) | cross-engine | A computed (generated) column derives its value from an expression over other columns in the same row, recalculated automatically on every read or write — a fundamentally different thing from an auto-incrementing identity column, even though MySQL spells the two very differently and PostgreSQL's `GENERATED ALWAYS AS (...)` clause is shared syntax for both. |

#### Inline DDL attributes decomposed into standalone statements

| Article | Direction | Description |
|---|---|---|
| [Inline DDL attributes decomposed into standalone statements: MySQL `COMMENT`, T-SQL inline `INDEX`](inline-attribute-to-standalone-statement.md) | cross-engine | MySQL lets a column or table carry a `COMMENT '...'` right inside its `CREATE TABLE`, and T-SQL lets a table element declare an `INDEX` inline alongside its columns. |

#### Inline column-level constraints relocated to table-level

| Article | Direction | Description |
|---|---|---|
| [An inline column-level `REFERENCES`/`CHECK` constraint → a table-level constraint clause](inline-fk-check-relocated-table-level.md) | cross-engine | `c INT REFERENCES p(id) ON DELETE CASCADE` and `c INT CHECK (c > 0)` declare a foreign key or check constraint directly on the column, inline inside its own definition — every engine accepts this shorthand. |

## All articles by type

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

## DDL guards

| Article | Direction | Description |
|---|---|---|
| [T-SQL system-catalog DDL guards (`OBJECT_ID`/`sys.objects`/`sys.columns`) → native `IF [NOT] EXISTS` or a synthesized per-target probe](tsql-existence-guard-catalog-probes.md) | tsql → oracle/postgresql/mysql | A T-SQL migration script often guards a `CREATE`/`DROP`/`ALTER` with a system-catalog existence check — `IF OBJECT_ID('t') IS NOT NULL DROP TABLE t` or `IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID('t')) BEGIN CREATE TABLE t (...) END` — so a second run of the same script doesn't fail on an object that's already there (or already gone). |
| [Oracle catalog probes inside dynamic DDL (`user_indexes`/`user_tab_cols`) → the target's own system view](oracle-catalog-probe-rewritten-per-target.md) | oracle → tsql/postgresql | An Oracle PL/SQL script sometimes checks its own data dictionary before running dynamic DDL through `EXECUTE IMMEDIATE` — for example resolving an index's owning table before a table-less `DROP INDEX` (Oracle names only the index; T-SQL requires the table too, error 159), or gating an `ALTER TABLE ... MODIFY` on whether a column already has the target shape. |
