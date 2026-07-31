[← Procedural: cursors, dynamic SQL, system procedures, session directives](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=procedural type="Return-type and signature synthesis" direction="—" kind=overview order=12 -->

# Return-type and signature synthesis

Two shapes where a routine's own declared **signature** has to change shape
to satisfy the target grammar, not just its body: a PostgreSQL function that
declares no return value at all, and a procedure whose body streams a result
set that PL/SQL cannot express without an extra parameter.
