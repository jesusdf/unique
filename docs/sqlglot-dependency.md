# sqlglot dependency: pinning and vendoring analysis

`unique` builds directly on top of [sqlglot](https://github.com/tobymao/sqlglot)
for parsing and re-emitting the embedded DML/DQL inside stored routines, and
for several scalar-expression rewrites. sqlglot is therefore a load-bearing
dependency: its parser and dialect emitters are part of our output path, not
just a dev convenience.

This document records (a) how the dependency is referenced today, (b) why the
version is now pinned, and (c) an analysis of whether to vendor/fork sqlglot
with a GRUB-style pinned-sources-plus-patches layout. The fork is **not**
currently adopted — this is a recommendation, not a decision.

## How it is referenced

- Plain Python import (`import sqlglot`), declared in `pyproject.toml`.
- **Pinned to an exact version**: `sqlglot==30.11.0` (previously
  `sqlglot>=25.0.0`, an open lower bound that pulled whatever was newest at
  install time).

### Why pin

sqlglot iterates quickly and routinely changes parser behaviour and dialect
output between minor releases. Because its output is part of *our* output, an
unpinned dependency means an unrelated `pip install` can change — or silently
break — transpilation results with no change on our side. We have already hit
several sqlglot-specific behaviours that needed working around in the
transformer (e.g. a T-SQL `OUTPUT`→`RETURNING` mapping that is invalid on
MySQL, a hash-stringify `CONVERT` misread as a date format, double-quoted
string literals treated as identifiers). Pinning makes upgrades deliberate:
we bump the version when we choose to, re-run the suite (and the live-syntax
job), and absorb any breakage in one controlled step.

**Upgrade procedure**: bump the pin in `pyproject.toml`, run the full test
suite plus the live-syntax CI job, regenerate the procedure fixtures
(`procedures_mysql.sql`, `procedures_postgresql.sql`, `procedures_oracle.sql`)
and review the diff, then commit the bump together with any required
transformer adjustments.

## Option analysis: vendoring / forking sqlglot

The question is whether to go beyond pinning and keep sqlglot *inside* the
repository so we can patch it, in the style GRUB uses for its bundled
dependencies (a directory of upstream sources fixed at a known commit, plus a
directory of our own diffs applied at build time).

### Option A — pin only (current)

- **Pros**: zero maintenance overhead; standard, well-understood dependency;
  upgrades are a one-line change; no divergence from upstream.
- **Cons**: we cannot fix a sqlglot bug ourselves — we either work around it in
  our transformer (where most of our current workarounds already live) or wait
  for an upstream release. We are limited to behaviour the installed version
  exposes.

### Option B — vendored fork with a patch queue (GRUB-style)

Layout would be roughly:

```
third_party/sqlglot/
  upstream/        # sqlglot sources fixed at a known commit/tag
  patches/         # ordered *.patch files (our diffs)
  apply-patches.sh # checks out the pinned commit and applies patches in order
  README.md        # records the pinned commit and what each patch does
```

- **Pros**:
  - We can carry **local fixes** for sqlglot bugs without waiting for upstream,
    turning today's transformer workarounds into upstream-shaped patches where
    that is cleaner.
  - Fully reproducible: the exact parser/emitter source is in-tree, not fetched
    from PyPI; supply-chain and offline builds are deterministic.
  - Patches are isolated and reviewable, and rebasing onto a newer upstream
    commit is an explicit, auditable step.
- **Cons**:
  - **Maintenance cost is real and ongoing**: every upgrade means rebasing our
    patches onto upstream and re-validating. sqlglot is large and fast-moving,
    so drift accumulates quickly.
  - Build complexity: an apply-patches step before packaging, plus import-path
    handling so our vendored copy is the one imported (and not a PyPI sqlglot
    pulled in transitively).
  - Most of our needs are *additive transformations around* sqlglot, which the
    transformer already does well without touching sqlglot internals. The set
    of issues that genuinely require editing sqlglot itself is small.
  - Tooling friction: type stubs, linting and packaging now have to cover a
    large vendored tree.

### Recommendation

Stay on **Option A (pin only)** for now — it removes the immediate risk (silent
upstream breakage) at essentially no cost, and our workarounds fit naturally in
the transformer. Adopt **Option B (vendored fork)** only if we accumulate
several issues that *cannot* be solved outside sqlglot, or if reproducibility/
offline-build requirements demand in-tree sources. If we do adopt it, keep the
patch set as small as possible (prefer transformer-side fixes), pin to an
upstream tag rather than an arbitrary commit, and document each patch with the
upstream issue/PR it corresponds to so patches can be dropped as they land
upstream.

If/when Option B is pursued, a lightweight first step is to capture the current
transformer workarounds that are really sqlglot bugs as candidate upstream
patches, so the fork starts with a clear, documented, minimal patch queue.
