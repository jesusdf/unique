# Procedural SQL Engine

## Problem

sqlglot treats stored procedure/function/trigger bodies as opaque `Command`
text. It does not parse or transform procedural constructs such as variable
declarations, IF/THEN/ELSE, cursors, assignments, or loop control. This
means 100% of real-world procedural SQL passes through untransformed.

## Solution

A dedicated **Procedural SQL Engine** built into Unique that handles the
procedural layer independently of sqlglot. sqlglot continues to handle
DML/DQL transpilation (SELECT, INSERT, UPDATE, DELETE); the procedural
engine handles the surrounding control-flow scaffolding.

## Architecture

```
┌─────────────────────────────────────────────────┐
│                  Input Script                    │
└──────────────────────┬──────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────┐
│              BatchSplitter                       │
│  Splits on GO (T-SQL) / slash (Oracle) /        │
│  semicolons (PG/MySQL)                          │
└──────────────────────┬──────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────┐
│          Statement Classifier                    │
│  Is this procedural (CREATE PROC, ALTER PROC,   │
│  CREATE FUNCTION, CREATE TRIGGER, anonymous      │
│  block) or plain DML/DDL?                        │
└────────┬─────────────────────────┬──────────────┘
         │                         │
    procedural                  DML/DDL
         │                         │
         ▼                         ▼
┌──────────────────┐    ┌──────────────────┐
│ ProceduralParser │    │ sqlglot pipeline │
│ (recursive       │    │ (existing)       │
│  descent)        │    │                  │
└────────┬─────────┘    └────────┬─────────┘
         │                       │
         ▼                       │
┌──────────────────┐             │
│ Procedural IR    │             │
│ AST Nodes        │             │
└────────┬─────────┘             │
         │                       │
         ▼                       │
┌──────────────────┐             │
│ Procedural       │             │
│ Transformer      │             │
│ (dialect-aware)  │             │
└────────┬─────────┘             │
         │                       │
         ▼                       ▼
┌─────────────────────────────────────────────────┐
│           ProceduralEmitter                      │
│  Emits target-dialect procedural code.           │
│  Delegates embedded DML to sqlglot.transpile()   │
└──────────────────────┬──────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────┐
│                 Output Script                    │
└─────────────────────────────────────────────────┘
```

## Approach: Token-based Recursive Descent Parser

Regex is too fragile for nested procedural blocks. Instead we use a
hand-written **tokenizer + recursive descent parser**, which:

- Handles nested BEGIN/END, IF/THEN/ELSE/END IF correctly
- Respects string literals (won't match keywords inside strings)
- Handles comments (single-line and block)
- Is extensible for new constructs
- Delegates embedded DML (SELECT, INSERT, UPDATE, DELETE) to sqlglot

### Why not a full grammar tool (ANTLR, PEG)?

- Adds a heavy dependency and build step
- We only need to parse the procedural *scaffolding*, not every SQL
  expression. Embedded DML is delegated to sqlglot.
- Recursive descent is simpler to debug, test, and maintain

## Components

### 1. BatchSplitter (`core/batch_splitter.py`)

Splits a multi-statement script into individual batches:
- T-SQL: splits on `^GO$` lines
- Oracle: splits on `^/$` lines
- PostgreSQL/MySQL: splits on `;` (respecting string literals and
  `$$` dollar-quoting in PG)

### 2. ProceduralLexer (`core/procedural/lexer.py`)

Tokenizes procedural SQL into a stream of typed tokens:
- Keywords: CREATE, PROCEDURE, FUNCTION, BEGIN, END, IF, THEN, ELSE,
  ELSIF, WHILE, FOR, LOOP, DECLARE, CURSOR, OPEN, FETCH, CLOSE, INTO,
  RETURN, EXCEPTION, WHEN, RAISE, SET, EXEC, PRINT, etc.
- Identifiers: names, @variables, :=, %TYPE, %ROWTYPE
- Literals: strings, numbers, NULL
- Operators: =, :=, <, >, <=, >=, <>, !=, +, -, *, /, ||
- Punctuation: (, ), ;, ,, .
- Comments: preserved as tokens
- Embedded DML: captured as a single token for delegation to sqlglot

### 3. ProceduralParser (`core/procedural/parser.py`)

Recursive descent parser producing IR AST nodes. The parser depends on the
*source* dialect, of which there are only two syntactic families — T-SQL and
PL/SQL (Oracle/PostgreSQL/MySQL). That distinction is named by
`_is_tsql_source()` and centralized in `_parse_routine_body()`, rather than
scattered `if dialect == "tsql"` checks, so the parser stays a single class
(a 4-way subclass split would be over-structure for an almost-entirely-shared
body).

```
parse_batch()
  ├── parse_create_procedure()
  ├── parse_create_function()
  ├── parse_create_trigger()
  ├── parse_alter_procedure()  (T-SQL: ALTER PROCEDURE = CREATE OR REPLACE)
  └── parse_anonymous_block()

parse_body()
  ├── parse_declare_section()
  │   ├── parse_variable_declaration()
  │   ├── parse_cursor_declaration()
  │   └── parse_type_reference()  (%TYPE, %ROWTYPE)
  ├── parse_begin_end()
  ├── parse_if_statement()
  ├── parse_while_statement()
  ├── parse_for_loop()
  ├── parse_assignment()
  ├── parse_cursor_operation()  (OPEN, FETCH, CLOSE, DEALLOCATE)
  ├── parse_return()
  ├── parse_raise_error()
  ├── parse_execute()  (EXEC / EXECUTE IMMEDIATE)
  ├── parse_print()
  ├── parse_set_statement()
  ├── parse_try_catch()
  └── parse_embedded_dml()  → delegates to sqlglot
```

### 4. ProceduralTransformer (`core/procedural/transformer/`)

A per-target package: `base.py` holds `ProceduralTransformer` (the shared
transform logic, the type/function mapping tables, and the
source/pair-dependent logic), and `tsql.py`/`oracle.py`/`postgresql.py`/
`mysql.py` each hold one target subclass. `ProceduralTransformer(source,
target)` is a factory that returns the registered target subclass.

Because a transform is a *source → target* operation, only genuinely
target-only decisions are overridden in a subclass (e.g. `_system_var_map`,
`_uses_set_statement`, `_transform_try_catch`, `_update_predicate`). Logic that
depends on the *pair* (e.g. variable naming `@x`→`V_X`/`v_x`/`@x`) or only on
the *source* stays in the base parameterized by `self._source` — forcing it
into a target-only subclass would be incorrect.

Representative source→target mappings:

| Source (T-SQL)                | Target (Oracle)                     |
|-------------------------------|-------------------------------------|
| `ALTER PROCEDURE dbo.x`      | `CREATE OR REPLACE PROCEDURE x`    |
| `@variable`                  | `V_VARIABLE`                       |
| `DECLARE @x INT`             | `x NUMBER` (in DECLARE section)    |
| `SET @x = value`             | `x := value;`                      |
| `IF @x = 1 BEGIN...END`      | `IF x = 1 THEN...END IF;`         |
| `WHILE ... BEGIN...END`      | `WHILE ... LOOP...END LOOP;`       |
| `EXEC(@sql)`                 | `EXECUTE IMMEDIATE sql;`           |
| `SET NOCOUNT ON`             | (removed)                          |
| `@@ROWCOUNT`                 | `SQL%ROWCOUNT`                     |
| `RAISERROR`                  | `RAISE_APPLICATION_ERROR`          |
| `TRY...CATCH`               | `EXCEPTION WHEN OTHERS THEN`      |
| `PRINT`                      | `DBMS_OUTPUT.PUT_LINE`            |

(And the reverse direction, plus PG and MySQL variants.)

### 5. ProceduralEmitter (`core/procedural/emitter/`)

A per-target package mirroring the transformer: `base.py` holds
`ProceduralEmitter` (the shared emission structure and the overridable hooks),
and `tsql.py`/`oracle.py`/`postgresql.py`/`mysql.py` each hold one target
subclass overriding only what differs. `ProceduralEmitter(dialect)` is a
factory returning the registered subclass; the base carries **no**
`if dialect == …` dispatch. Each target's emission shape:

- **T-SQL**: `CREATE PROCEDURE`, `@params`, `BEGIN...END`, `SET @x =`
- **Oracle**: `CREATE OR REPLACE PROCEDURE`, `IS/AS`, `BEGIN...END;`,
  `:=` assignments, `EXCEPTION` blocks
- **PostgreSQL**: `CREATE OR REPLACE FUNCTION ... RETURNS void`,
  `$$` dollar-quoting, `LANGUAGE plpgsql`
- **MySQL**: `CREATE PROCEDURE`, `DELIMITER //`, `BEGIN...END`

Adding a new target engine means adding a `transformer/<engine>.py` and an
`emitter/<engine>.py` (each self-registering on import) plus a one-line import
in the package `__init__` — no change to the shared base logic.

### 6. MetadataResolver (`core/metadata.py`)

Optional database connection for resolving metadata-dependent constructs:

```python
class MetadataResolver:
    """Connects to a source database to resolve type references."""

    def resolve_column_type(self, table: str, column: str) -> DataType:
        """Resolve %TYPE references to actual column data types."""

    def resolve_table_columns(self, table: str) -> list[ColumnDefinition]:
        """Resolve %ROWTYPE references to full column lists."""
```

Supports connection via:
- `--db-url` CLI parameter: standard connection string
- API request body: `db_url` field
- Drivers: `pyodbc` (SQL Server), `oracledb` (Oracle),
  `psycopg` (PostgreSQL), `mysql-connector-python` (MySQL)

When no database connection is provided, `%TYPE` references are emitted
as comments with a warning, or mapped to a best-guess type based on the
column name conventions.

## Integration Points

The procedural engine integrates at the `Transpiler.transpile()` level:

```python
def transpile(self, sql, source, target, options):
    # Step 0: Split into batches
    batches = BatchSplitter.split(sql, source)

    results = []
    for batch in batches:
        if ProceduralClassifier.is_procedural(batch, source):
            # Procedural pipeline
            ir = ProceduralParser(source).parse(batch)
            ir = ProceduralTransformer(source, target).transform(ir)
            output = ProceduralEmitter(target).emit(ir)
        else:
            # Existing sqlglot pipeline
            output = sqlglot_transpile(batch, source, target)
        results.append(output)

    return join_batches(results, target)
```

## Limitations

Some constructs remain inherently untranslatable:
- Database-specific packages (Oracle `UTL_FILE`, `DBMS_LOB`)
- CLR procedures (SQL Server)
- External language functions
- Database links / linked servers
- Engine-specific hints and pragmas

These will be emitted as `RawSQL` with warning comments.
