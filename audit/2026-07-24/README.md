# Audit — 2026-07-24

Full audit of the `unique` repository at **v0.30.0** (HEAD `69a71cd`,
= public `origin/main`). Previous audit: [`audit/2026-07-08/`](../2026-07-08/)
at v0.22.3, ~1,009 commits ago. Three goals: verify the remediation of every
2026-07-08 finding, re-audit the current state across all dimensions, and — for
the first time — sweep the public repo and its full history for private-corpus
leaks.

Since the last audit the project adopted the netsec-inspired **RED/BLUE
continuous-improvement methodology** (`skills/SKILL-challenge-corpus.md`): a
RED role live-validated **862 silent mis-transpilations**, and the BLUE role
resolved all of them (694 `[fixed]`, 168 approved `[limit]`, 0 open). This
audit evaluates what that campaign actually bought, and what it missed.

## Documents

| File | Contents |
|------|----------|
| [01-remediation-verification.md](01-remediation-verification.md) | Item-by-item verification of every 2026-07-08 finding (N1–N9, priorities, carry-overs, the ~25 private-sweep defect classes) against v0.30.0 |
| [02-new-findings.md](02-new-findings.md) | New defects: **10 S1 + 2 S2 + 4 S3**, every S1 live-verified on the four real engines, plus improvement opportunities |
| [03-test-quality.md](03-test-quality.md) | Identity-mutation re-run (66% vs floor 45%), suite growth 1,774 → 3,785, challenge-corpus assertion quality, stalled ratchets |
| [04-code-quality.md](04-code-quality.md) | Guardrail-compliance sweep (2 violations), size evolution (src doubled; `emit.py` 9,992 lines), plugin-architecture health |
| [05-api-security-ops.md](05-api-security-ops.md) | API/security/ops: N6 fixed, N7 partial (1 S2 + 5 S3 new), Docker/CI posture — empirically probed on a live server |
| [06-docs-drift.md](06-docs-drift.md) | Docs accuracy: 13 drift findings (1 S2 overclaim in the compatibility matrix, 12 S3) |
| [07-confidentiality.md](07-confidentiality.md) | Private-corpus leak sweep over all tracked files, all 1,441 commit messages, all 4,804 historical blobs: **10 redacted findings** |
| [08-prevention-plan.md](08-prevention-plan.md) | Why each defect class recurred (7 process root causes) and the countermeasures: skill/instruction changes applied with this audit, mechanical tooling specs (unread-args tripwire, leak check, architecture ratchets, challenge class-scoring), cadence rules |
| [09-fix-briefs.md](09-fix-briefs.md) | Pre-analyzed fix brief per finding (B1–B28 + tools T1–T7): verified root cause, chosen approach, rejected alternatives, tests-first, acceptance criteria — fixes start from the brief |

**Applied with this audit** (not just reported): the 13 docs-drift fixes of
doc 06 (matrix honesty + recount, STATUS floors, DONE §40 heading, FINDINGS.md
prune, layout fictions in 02/04/05/skills, coverage-matrix status), the
normative skill updates listed in doc 08 §A (guardrail 2 extension +
guardrail 7, composition neighbors, scenario-adequacy, `[limit]` tag +
class/points scoring, release ratchet checklist, commit-message
confidentiality rule), a CLAUDE.md pointer, and the `docs/TODO.md` backlog
(P1–P3, one entry per brief).

## Executive summary

**The 2026-07-08 remediation is real.** Both S1s (the unbracketed
`IF [NOT] EXISTS` guard drop and the PG→T-SQL temp-table rename) are fixed
exactly as proposed; of N1–N9, **7 are fixed and 2 partial**, all four P1/P2
priorities landed, and 23 of the ~25 private-sweep defect classes no longer
reproduce (1 partial, 1 open). **No silent-loss finding from 2026-07-08 still
reproduces.** The ops carry-overs closed too: four-engine CI reachability gate,
Docker digest pin + `constraints.txt`, `X-Unique-Decoded-As` header, API size
caps. Still open: the `unique verify` CLI promotion, CI log-block duplication,
and module growth (which got dramatically worse — see below).

**The gate is green at HEAD**: black, isort, ruff, mypy clean; **3,785 tests
pass** (one performance-budget test is load-sensitive and fails only under
machine contention; it passes at 5.2 s against a 10 s budget on an idle
machine). Identity-mutation kill rate is **66%** (was 38% at 07-08).

**However, this audit found 10 new S1 defects — all live-verified, all
unwarned** ([02-new-findings.md](02-new-findings.md)). The RED/BLUE campaign
cleared the statement-level field, and the residue is concentrated one level
up, in **clause-level conversion and cross-feature composition**:

1. **Upserts are silently destroyed in every direction** (N1): MySQL
   `ON DUPLICATE KEY UPDATE` and PG `ON CONFLICT DO UPDATE / DO NOTHING`
   transpile to a **plain INSERT with zero warnings** — the converter never
   reads sqlglot's `conflict` arg. The compatibility matrix marks this ✅
   (doc 06 D1). This is the headline finding.
2. **The new MERGE support has semantic holes** (N2–N4): the Oracle
   conditional-DELETE fold evaluates post-UPDATE values (live: deletes 2 rows
   where SQL Server deletes 1); MERGE `OUTPUT` → PG emits invalid
   `RETURNING $action` or silently mis-attaches it; PG `THEN DO NOTHING`
   passes through verbatim (invalid on T-SQL/Oracle).
3. **The new cursor-attribute emulation breaks on composition** (N5–N6):
   nested cursor loops produce duplicate MySQL labels (live error 1309), a
   shared never-reset NOT-FOUND flag, wrong `@@FETCH_STATUS` mapping with
   interleaved cursors; `%ISOPEN` leaks as a modulo expression.
4. Plus: PG `SET TRANSACTION … READ ONLY` passthrough (N7), T-SQL money
   literal `$12.50` corrupted (N8), stale cross-statement column-type metadata
   silently reverting an ALTERed type (N9), dynamic-SQL strings shipped
   byte-identical to foreign engines unwarned (N10), and `SQL%ROWCOUNT` →
   MySQL `ROW_COUNT()` matched-vs-changed divergence (N11, S2).

The pattern behind N1/N3/N4 is the already-documented **sqlglot unread-args
leniency class**; doc 02's first improvement opportunity is a converter-side
tripwire (warn whenever a known-semantic arg goes unread) that would have
caught all three at once.

**Test quality** (doc 03): the infrastructure is excellent and the numbers
moved (kill rate 38% → 66%, suite +113%), but **both ratchets have stalled**
(identity floor 0.45 vs measured 0.66; nightly mutation floors untouched since
07-06 while a sampled module scores 82 vs floor 65), the pre-2026-07 weak files
are exactly as weak as a year of audits ago (`test_cross_dialect.py` still 28%
kill), and the challenge `[fixed]` guard is **two-tier**: ~362 of 694 cases
rely only on a generic carrier-absence loop, and challenge outputs are never
target-parsed or live-executed in CI.

**Code quality** (doc 04): the script-layer moratorium held, but **two
guardrail-2 violations** exist (post-emit `re.sub` mapping over converted SQL
text in `_text_rules.py:159` and `converter/emit.py:565`), and the regex
cascade the architecture plan closed in `transpiler.py` has **relocated into
the emitter**: `emit.py` grew 1,873 → **9,992 lines** (82 `re.sub`s, 57
"wave NNN" instance-patch comments, `_emit_function` at 2,270 lines /
cyclomatic complexity 355, 486 dialect string-compares). The procedural side
kept its clean plugin shape (0 dialect compares in the emitter base); the DML
emitter is now the anti-pattern the 2026-07-08 architecture analysis was
written to kill. src doubled in 16 days (20.5k → 44.5k lines).

**API/security** (doc 05): no S1. N6 (size caps) fixed; N7 partial — the
filename sanitizer uses Unicode `\w`, so a non-latin-1 filename still crashes
the download header (500, empirically reproduced; one-line `re.ASCII` fix).
DSN gating, generic errors, digest pins, CI secrets, web-UI XSS all verified
sound.

**Docs** (doc 06): 13 drift items. The S2 is the compatibility matrix's ✅ on
upserts (= finding N1); the rest are stale numbers (mutation floor "33/38"
vs actual 45/66), a self-contradicting DONE §40 heading, the never-updated
dialect-plugin layout fiction, and a 160-row resolved backlog still sitting in
FINDINGS.md.

**Confidentiality** (doc 07 — redacted; unredacted hit list stays in the
maintainer's local scratchpad): `fixtures-private/` was **never tracked**, the
862-case challenge corpus and all distinctive literals/company identifiers are
**completely clean** — but the sweep found **10 leaks of real schema
vocabulary**: 7 committed files (1 highly distinctive table name, 1 verbatim
private comment line, ~9 real column/type/cursor names, 1 real data value),
**2 pushed commit messages** (removable only by history rewrite), and 1 naming
of the private MySQL corpus's origin in docs + a commit message. File-level
fixes are mechanical; the history-rewrite decision belongs to the maintainer
and client.

## Recommended priorities

1. **P1 — model the upsert clause** (N1): native emit where equivalents exist
   (PG ⟷ MySQL, → MERGE on T-SQL/Oracle), carrier + warning elsewhere; add the
   **unread-args tripwire** so the class stays closed.
2. **P1 — confidentiality remediation at HEAD**: rename the leaked
   identifiers/literals in the 7 files, reword the two `docs/DONE.md` lines
   (mechanical, ~7 files); put the history-rewrite question (2 commit
   messages) to the maintainer/client.
3. **P1 — MERGE semantic fixes** (N2 post-UPDATE DELETE evaluation, N3 OUTPUT
   → PG, N4 DO NOTHING passthrough) — the feature is new, the corpus locked it
   in as green, and two of the three failure modes are silent wrong-data.
4. **P2 — cursor-emulation composition** (N5/N6: per-cursor flags/labels,
   `%ISOPEN` gate), N7/N8/N9/N10 (SET TRANSACTION, money literals, metadata
   staleness, dynamic-SQL warning), and the API `re.ASCII` one-liner.
5. **P2 — re-arm the ratchets**: identity floor 0.45 → 0.60 now, nightly
   mutation floors after one clean run; upgrade the ~362 loop-only challenge
   cases toward dedicated assertions and target-parse (ideally live-execute)
   challenge outputs in CI.
6. **P2 — pay the emitter debt before it calcifies**: split `emit.py` along
   doc 04's proposed seams, de-regex the two guardrail violations, enable
   `C901` with a ceiling and burn the 107 offenders down; decide whether the
   DML emitter adopts the procedural plugin shape (486 dialect compares say
   yes eventually).
7. **P3 — docs sync** (matrix recount + un-✅ upserts/IF-EXISTS-Oracle, floor
   figures, DONE §40 heading, FINDINGS.md prune, plugin-layout sketches),
   `.dockerignore`, align CI's floating deps with the image's
   `constraints.txt`, CI log-block dedup, `unique verify` promotion.

## Method

- Venv gate re-run locally at HEAD: black + isort + ruff + mypy + full
  parallel suite (3,785 tests) — green (one load-sensitive perf flake,
  verified passing on an idle machine).
- Six parallel auditor sessions (remediation, new-findings, tests, code,
  API/ops, docs) + a dedicated confidentiality sweep; every 2026-07-08 finding
  re-probed through the public `Transpiler` API with its original reproduction.
- Every new S1 verified on the **live engines** (the four Docker containers):
  source executed on the source engine, output executed on the target,
  warnings/unsupported checked empty.
- Identity-mutation check re-run exactly as CI runs it; a sampled real
  mutation run (40 mutants) re-scored one module against its nightly floor.
- Confidentiality: 24,923 distinctive private tokens + 62 literals + 3 company
  identifiers swept (case-insensitive) over all 282 tracked files, 1,441
  commit messages and 4,804 historical blobs; hits triaged and confirmed
  against the private corpus; report fully redacted.
