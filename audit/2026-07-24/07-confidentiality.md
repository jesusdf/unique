# 07 — Confidentiality audit (private-corpus leak sweep)

Date: 2026-07-24 · Scope: full repo at HEAD `69a71cd` (= public `origin/main`,
verified via `ls-remote`) plus complete git history (all refs, all blobs).

Policy audited (CLAUDE.md + development-workflow skill): no real object name
(table, procedure, column, schema, revision string, comment text) from
`fixtures-private/` may appear in any committed file or commit message; the
origin of the private MySQL corpus must never be named in committed artifacts.

**This report is deliberately redacted.** No leaked token appears here; hits
are given as `file:line`, category, and first-character + length. The full
unredacted hit list exists only in the session scratchpad
(`CONFIDENTIALITY-HITS-FULL.md` under the local scratchpad directory) — it is
for the maintainer's eyes and must never be committed.

## 1. Tracked-status verdict

- `fixtures-private/` is **not tracked**: `git ls-files` shows no file under it,
  and `git log --all -- fixtures-private/` is empty — it was **never committed
  in any revision**.
- `.gitignore` covers it (lines 230–233: a `*.private.sql` pattern and the
  directory itself). The private corpus-fetch directory is likewise untracked
  and ignored, as are `coverage.xml` and all cache dirs.
- **No `.dockerignore` exists**, but this is currently harmless: both
  `Dockerfile` and `Dockerfile.dev` `COPY` only explicit paths
  (`pyproject.toml`, `README.md`, `src/`, `tests/`, `constraints.txt`) — there
  is no context-wide `COPY . .` that could bake private fixtures into an image.
  Recommendation: add a `.dockerignore` anyway as a guard against a future
  broad `COPY`.

## 2. Methodology

1. **Inventory** (scratchpad only): tokenized all three private SQL files
   (~14 MB); 33,679 raw identifiers reduced to **24,923 distinctive tokens**
   (case-folded; length ≥ 6; SQL keywords/builtins, English and Spanish
   dictionary words, and generic column idioms filtered out). Separately:
   **62 distinctive literals** (URLs, e-mail addresses, internal IPs; the
   corpus contains no GUID literals) and — because the length filter would
   drop them — an explicit check of three short (≤5-char) company/organization
   identifiers found in the corpus.
2. **Sweep**: exact identifier-token intersection (case-insensitive) against
   (a) all **282 tracked files** at HEAD, (b) all **1,441 commit messages**
   (all refs), (c) all **4,804 historical blobs** in the object store (so
   deleted/edited past revisions are covered). Literals and short company
   names swept as substrings over the same three surfaces.
3. **Phrase check**: all Spanish-looking prose fragments (≥18 chars, ≥2
   stopwords) in committed files (60 candidate phrases) checked verbatim
   against the private corpus, to catch copied comment text that identifier
   matching would miss.
4. **Triage**: every raw hit (2,503 in HEAD, 323 in messages, 105k in blobs)
   classified; the overwhelming majority are generic engine builtins present
   in both corpora (`params`, `fetch_status`, `dbms_`-family, etc.) or public
   Northwind sample data. Every remaining candidate was confirmed against the
   private corpus (exact-word and context) before being counted.

## 3. Results overview

| Surface | Verdict |
|---|---|
| `tests/fixtures/challenge/` (862 RED/BLUE cases) | **Clean.** All 171 token hits are generic SQL/engine builtins; zero distinctive identifiers. The campaign's anonymization held. |
| Company/organization names (3 short identifiers) | **Zero hits** anywhere (files, messages, history). |
| Distinctive literals (gov-health URLs, client e-mails, internal IPs, product hostnames) | **Zero hits** anywhere. |
| `audit/2026-07-02/`, `audit/2026-07-08/` (incl. the earlier private-fixture sweep doc, which claims anonymization) | **Clean** — claim verified. |
| Git history beyond HEAD | No bulk private content ever committed; the leak tokens below appear only in earlier revisions of the same files. |
| Test/doc files at HEAD | **10 findings** (below): 7 in tracked files, 2 in commit messages, 1 policy-level origin mention. |

## 4. Findings (redacted)

Severity reflects how uniquely the token identifies the client's schema.
None of the findings expose personal data, credentials, or the client's name;
they expose internal schema vocabulary and, in one case, verbatim comment text.

- **F1 — HIGH — real table name in a committed test.**
  `tests/unit/core/procedural/test_transformer.py:806,810,817,821` uses a real,
  highly distinctive table name `H____________ (13 chars)` (75 occurrences in
  the private corpus) in a `%TYPE` parameter fixture and in output assertions.
- **F2 — HIGH — same table name in a pushed commit message.**
  Commit `6fde4146…` (2026-06-21) quotes the same 13-char table name twice in
  its body. A commit-message hit can only be removed by history rewrite (§5).
- **F3 — MEDIUM — verbatim private comment text.**
  A 30-character Spanish comment phrase that occurs exactly once in the
  private corpus is reproduced verbatim (source and assertion) in
  `tests/integration/test_oracle_mysql_tail.py:400,415` and
  `tests/unit/core/test_ir_first_families.py:247,262`. Comment text is
  explicitly covered by the policy.
- **F4 — MEDIUM — five real column names + audit-column echo in one test file.**
  `tests/integration/test_oracle_source_m4_wave.py` lines 34, 43, 50 (column
  `n_______ (8)`), 34 (`n_______ (8)`), 130 (`i_________ (10)`), 326–332
  (`t_________ (10)`), 511 (`o_____ (6)`), and 455/458 (a parameter named after
  the client's universal 8-char audit column, `v_f_______`). The table names in
  the same fixtures are truncated prefixes of real tables (partial
  anonymization — low residual risk, but the columns are exact).
- **F5 — MEDIUM — real column + real data value + real command-string prefix.**
  `tests/integration/test_procedural.py:476–490`: an `EXEC` fixture combines a
  real 6-char column name, a real 5-digit menu-ID literal (present in the
  private corpus on the analogous statement), and an 8-char command-string
  prefix (`N_______-…`) that prefixes 179 private literals. The procedure name
  itself is anonymized but retains the real 4-char procedure prefix and a real
  table-name fragment.
- **F6 — MEDIUM — real config table + columns in the client's idiom.**
  `tests/unit/core/test_no_ir_leak.py:47,49,64` uses the client's real 8-char
  config table (with schema prefix) and its real 8-char/6-char columns in the
  client's characteristic `INSERT … WHERE NOT EXISTS` guard shape.
- **F7 — LOW/MEDIUM — real PL/SQL collection type name in docs.**
  `docs/DONE.md:3121` names a real 13-char collection type (`A____________`);
  it also appears in ~200 historical revisions of `docs/TODO.md`.
- **F8 — LOW — the anti-leak guard enumerates real fragments.**
  `tests/integration/test_procedures_fixtures.py:35`: the regex that guards
  fixtures against private-name leaks itself lists three real 4-char procedure
  prefixes and one real 8-char table-name fragment.
- **F9 — LOW — real cursor name in a pushed commit message.**
  Commit `13989cb7…` (2026-07-10) quotes a real 15-char cursor declaration
  name (5 occurrences in the private corpus).
- **F10 — LOW/informational — MySQL private-corpus origin named.**
  `docs/DONE.md:1614–1615` and the message of commit `2e39442a…` name the
  upstream project's test-suite path and its test DSL (with its GPLv2
  license), framed as "evaluated and rejected for committing". This does not
  admit private use, but the standing policy is that the origin is never named
  in committed artifacts.

Borderline, not counted: one generic Spanish DDL banner phrase echoing the
client's script style (`tests/unit/core/test_transpiler.py:329`, table `t`);
one test file named after a private fixture's generic filename; public
Northwind sample rows containing Spanish company names (false positive).

## 5. Remediation

1. **HEAD fixes (no history rewrite needed for the file contents to stop
   being served at tip):** rename the identifiers/literals in F1, F3–F8 to
   synthetic equivalents (same shape, same test semantics — each test asserts
   on its own fixture text, so rename source and assertion together), and
   reword the `docs/DONE.md` lines (F7, F10). ~7 files, mechanical.
2. **Commit-message hits (F2, F9) and all historical blob revisions can only
   be purged with a history rewrite:**
   `git filter-repo --replace-message` (for the two messages) plus
   `--replace-text` (for the historical file revisions), then a force-push of
   `main` and tags, followed by contacting GitHub Support to drop cached
   views/PR refs and checking for forks. This invalidates all clones and CI
   caches; whether table/column-level vocabulary exposure justifies it is a
   maintainer/client decision. If a rewrite is done, fold step 1's renames
   into the same rewrite.
3. **Guards going forward:** add a `.dockerignore`; consider extending the
   existing fixture-guard test (F8) to load its fragment list from an
   untracked local file so the guard itself stays clean; run this sweep's
   token-intersection check (scripts preserved in the session scratchpad) as
   an occasional pre-release step.

## 6. Bottom line

The two highest-volume anonymization efforts held up well — the 862-case
challenge corpus and all distinctive literals/company identifiers are
completely clean — but 7 committed files and 2 pushed commit messages carry
real schema vocabulary (1 table name at high confidence twice, 1 verbatim
comment line, ~9 real column/type/cursor names, 1 real data value), and the
private MySQL corpus's origin is named once in docs and once in a commit
message. File-level fixes are quick; the two commit messages require
git-filter-repo if full removal is desired.
