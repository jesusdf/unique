#!/usr/bin/env bash
# Run the test suite across CPU cores with GNU parallel.
#
# pytest has no built-in parallelism here (pytest-xdist is not a dependency), and
# a single heavy file (tests/integration/test_real_world.py, ~48 s serial)
# dominates the wall time, so file-level parallelism does not help. This splits
# the suite at *test* granularity: collect every node ID, round-robin them into
# N groups, and run one pytest process per group concurrently.
#
# Usage:  scripts/test-parallel.sh [pytest args...]
#   PYTEST_WORKERS   number of parallel workers (default: nproc)
#   PYTEST_PYTHON    python interpreter (default: .venv/bin/python)
set -uo pipefail
cd "$(dirname "$0")/.."

PY="${PYTEST_PYTHON:-.venv/bin/python}"
N="${PYTEST_WORKERS:-$(nproc)}"

if ! command -v parallel >/dev/null 2>&1; then
    echo "GNU parallel not found; falling back to a single pytest run." >&2
    exec "$PY" -m pytest -o addopts="" -p no:cacheprovider "$@"
fi

# Silence GNU parallel's one-time citation notice (non-interactive CI).
mkdir -p "${PARALLEL_HOME:-$HOME/.parallel}" 2>/dev/null \
    && touch "${PARALLEL_HOME:-$HOME/.parallel}/will-cite" 2>/dev/null || true

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# Collect the node IDs of the tests that would run (honouring any extra args).
"$PY" -m pytest --collect-only -q -o addopts="" -p no:cacheprovider "$@" \
    2>/dev/null | grep '::' > "$TMP/nodes.txt" || true
total="$(wc -l < "$TMP/nodes.txt")"
if [ "$total" -eq 0 ]; then
    echo "No tests collected." >&2
    exit 1
fi

# Round-robin the nodes into N balanced groups.
awk -v n="$N" -v dir="$TMP" '{print > (dir "/grp_" (NR % n) ".txt")}' "$TMP/nodes.txt"

echo "Running $total tests across $N workers..."
export PYTEST_PYTHON="$PY"
# Opt-in coverage: each worker writes an isolated data file we combine below.
# COV=1 scripts/test-parallel.sh  ->  coverage.xml + a terminal report.
if [ "${COV:-0}" = "1" ]; then
    export COVERAGE_DIR="$TMP"
    # sys.monitoring (Python 3.12+/coverage 7.4+) makes instrumentation nearly
    # free, so coverage barely dents the parallel speedup.
    export COVERAGE_CORE="${COVERAGE_CORE:-sysmon}"
fi

# --halt soon,fail=1 stops launching new groups once one fails; exit is preserved.
find "$TMP" -name 'grp_*.txt' | \
    parallel -j"$N" --halt soon,fail=1 --line-buffer scripts/_pytest_group.sh
rc=$?

if [ "${COV:-0}" = "1" ] && [ "$rc" -eq 0 ]; then
    "$PY" -m coverage combine "$TMP"/.coverage.* >/dev/null 2>&1 || true
    "$PY" -m coverage xml -o coverage.xml >/dev/null 2>&1 || true
    "$PY" -m coverage report || true
fi
exit "$rc"
