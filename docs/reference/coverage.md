# Challenge-corpus coverage

> **Generated — do not edit by hand.** Produced by `python scripts/generate_reference_docs.py` from `tests/fixtures/challenge/challenge_*.sql`, parsed by `scripts/challenge_stats.py`. The CI freshness gate (`python scripts/generate_reference_docs.py --check`) fails the build if this file drifts from the source data.

Per-source-engine counts of the challenge corpus's `-- CASE[status][class=...]:` headers. "Direction" here is the case's tagged source engine — the corpus's only structured axis; each fixture file (`challenge_<source>.sql`) holds every case found starting from that source dialect, against all applicable targets.

| Source | fixed | limit | open | total |
|---|---|---|---|---|
| mysql | 247 | 56 | 4 | 307 |
| oracle | 138 | 44 | 4 | 186 |
| postgresql | 238 | 48 | 3 | 289 |
| sqlserver | 147 | 21 | 4 | 172 |
| **all** | 770 | 169 | 15 | 954 |

## By finding class

| Class | count |
|---|---|
| composition | 3 |
| consistency | 5 |
| crash | 1 |
| func | 19 |
| invalid | 35 |
| lying-warning | 16 |
| silent-drop | 9 |
| unclassified | 866 |
