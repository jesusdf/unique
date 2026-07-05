# MediaWiki schema fixtures

Real-world database schemas used to exercise the transpiler against a genuine,
complex production DDL surface (64 core tables: `AUTO_INCREMENT`/`AUTOINCREMENT`,
`UNSIGNED`, `VARBINARY`/`BLOB`, composite keys, inline unique/plain indexes,
integer-affinity columns).

## Source

- **Project:** MediaWiki (the software behind Wikipedia).
- **Version:** 1.46.0.
- **Files:** the generated core schema for each engine, taken verbatim from the
  release tarball at `sql/<engine>/tables-generated.sql`:
  - `mysql-tables.sql`   ← `sql/mysql/tables-generated.sql`
  - `postgres-tables.sql` ← `sql/postgres/tables-generated.sql`
  - `sqlite-tables.sql`  ← `sql/sqlite/tables-generated.sql`
- **Download:** <https://releases.wikimedia.org/mediawiki/1.46/mediawiki-1.46.0.zip>
  (also mirrored at `raw.githubusercontent.com/wikimedia/mediawiki/1.46.0/...`).
- These files are auto-generated from `sql/tables.json`; they contain MediaWiki
  templating comments (`/*_*/` table-prefix, `/*$wgDBTableOptions*/`) which are
  plain SQL comments and are ignored by the parser.

## License

MediaWiki is licensed **GPL-2.0-or-later**. These schema files are redistributed
here **unmodified**, solely as test fixtures, under those terms. This directory's
GPL-2.0+ license applies to these files only; it does not change the MIT license
of the `unique` project itself (these fixtures live under `tests/` and are not
shipped in the built package). Full license text:
<https://www.gnu.org/licenses/old-licenses/gpl-2.0.html>.
