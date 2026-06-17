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

Recursive descent parser producing IR AST nodes:

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

### 4. ProceduralTransformer (`core/procedural/transformer.py`)

Dialect-aware transformations on the procedural IR:

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
| `TOP(1)`                     | `ROWNUM = 1` / `FETCH FIRST`      |
| `ISNULL(a,b)`               | `NVL(a,b)`                         |
| `GETDATE()`                  | `SYSDATE` / `NOW()`               |
| `UNIQUEIDENTIFIER`           | `RAW(16)` / `UUID`                |
| `SCOPE_IDENTITY()`           | sequence `.CURRVAL`                |
| `@@ROWCOUNT`                 | `SQL%ROWCOUNT`                     |
| `RAISERROR`                  | `RAISE_APPLICATION_ERROR`          |
| `TRY...CATCH`               | `EXCEPTION WHEN OTHERS THEN`      |
| `PRINT`                      | `DBMS_OUTPUT.PUT_LINE`            |

(And the reverse direction, plus PG and MySQL variants.)

### 5. ProceduralEmitter (`core/procedural/emitter.py`)

Generates target-dialect procedural SQL from the IR. Each target dialect
has its own emission rules:

- **T-SQL**: `CREATE PROCEDURE`, `@params`, `BEGIN...END`, `SET @x =`
- **Oracle**: `CREATE OR REPLACE PROCEDURE`, `IS/AS`, `BEGIN...END;`,
  `:=` assignments, `EXCEPTION` blocks
- **PostgreSQL**: `CREATE OR REPLACE FUNCTION ... RETURNS void`,
  `$$` dollar-quoting, `LANGUAGE plpgsql`
- **MySQL**: `CREATE PROCEDURE`, `DELIMITER //`, `BEGIN...END`

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
