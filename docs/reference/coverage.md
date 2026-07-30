# Challenge-corpus coverage

> **Generated — do not edit by hand.** Produced by `python scripts/generate_reference_docs.py` from `tests/fixtures/challenge/challenge_*.sql`, parsed by `scripts/challenge_stats.py`. The CI freshness gate (`python scripts/generate_reference_docs.py --check`) fails the build if this file drifts from the source data.

Per-source-engine counts of the challenge corpus's `-- CASE[status][class=...]:` headers. "Direction" here is the case's tagged source engine — the corpus's only structured axis; each fixture file (`challenge_<source>.sql`) holds every case found starting from that source dialect, against all applicable targets.

| Source | fixed | limit | open | total |
|---|---|---|---|---|
| mysql | 244 | 56 | 1 | 301 |
| oracle | 136 | 44 | 1 | 181 |
| postgresql | 234 | 48 | 0 | 282 |
| sqlserver | 142 | 21 | 0 | 163 |
| **all** | 756 | 169 | 2 | 927 |

## By finding class

| Class | count |
|---|---|
| composition | 2 |
| consistency | 4 |
| crash | 1 |
| func | 15 |
| invalid | 23 |
| lying-warning | 9 |
| silent-drop | 7 |
| unclassified | 866 |
