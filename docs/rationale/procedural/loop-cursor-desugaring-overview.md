[← Procedural: cursors, dynamic SQL, system procedures, session directives](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=procedural type="Loop and cursor desugaring" direction="—" kind=overview order=27 -->

# Loop and cursor desugaring

T-SQL cursor *variables*, PL/SQL/Oracle cursor `FOR` loops, and numeric
range `FOR` loops all bind their query/bounds and their iteration into a
single declarative statement. Every one of MySQL's, T-SQL's, and (for the
numeric case) MySQL's/T-SQL's own procedural dialects requires the
equivalent to be spelled out as an explicit sequence: declare, open/fetch,
test, loop, close — so Unique expands the single source construct into that
target-specific scaffold. This is distinct from the cursor *attribute*
mapping above (which rewrites a value-position flag with no control-flow
change); every entry here changes the statement shape itself.
