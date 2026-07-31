[← DML: PIVOT/UNPIVOT, MERGE, DELETE, row values](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=dml type="Oracle join syntax and row limits (source direction)" direction="—" kind=overview order=15 -->

# Oracle join syntax and row limits (source direction)

The entries below run **from** Oracle. The rest of this page (and
[§7](../../03-unsupported.md) "To Oracle") documents the opposite direction —
a T-SQL/PostgreSQL comma-join or parenthesized join tree flattened *onto*
Oracle — which is a different mechanism (Oracle's `FROM` grammar rejects a
parenthesized join tree, ORA-00907); do not confuse the two.
