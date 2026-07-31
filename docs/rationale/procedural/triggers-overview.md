[← Procedural: cursors, dynamic SQL, system procedures, session directives](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=procedural type="Triggers" direction="—" kind=overview order=17 -->

# Triggers

The firing-mode surface that differs between engines: row-level (`FOR EACH
ROW`, `NEW`/`OLD`) vs. statement-level (T-SQL's `inserted`/`deleted`),
timing (`INSTEAD OF`), and each engine's own trigger-declaration shape. A
**purely** set-based T-SQL trigger (reads `inserted`/`deleted` only via
`FROM`/`JOIN`, no row-level qualifier or `UPDATE(col)` predicate) rewriting
to a PostgreSQL statement-level trigger with named transition tables — the
one case in this family already documented — is covered in
[§6](../../03-unsupported.md) ("Set-based trigger pseudo-tables"), not
repeated here; the entries below cover the rest of the family.
