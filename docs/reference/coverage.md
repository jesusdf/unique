# Challenge-corpus coverage

> **Generated — do not edit by hand.** Produced by `python scripts/generate_reference_docs.py` from `tests/fixtures/challenge/challenge_*.sql`, parsed by `scripts/challenge_stats.py`. The CI freshness gate (`python scripts/generate_reference_docs.py --check`) fails the build if this file drifts from the source data.

Per-source-engine counts of the challenge corpus's `-- CASE[status][class=...]:` headers. "Direction" here is the case's tagged source engine — the corpus's only structured axis; each fixture file (`challenge_<source>.sql`) holds every case found starting from that source dialect, against all applicable targets.

| Source | fixed | limit | open | total |
|---|---|---|---|---|
| mysql | 244 | 56 | 7 | 307 |
| oracle | 136 | 44 | 6 | 186 |
| postgresql | 234 | 48 | 7 | 289 |
| sqlserver | 142 | 21 | 9 | 172 |
| **all** | 756 | 169 | 29 | 954 |

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
