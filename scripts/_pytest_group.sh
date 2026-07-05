#!/usr/bin/env bash
# Run pytest on the newline-separated test node IDs listed in $1.
# ``set -f`` disables globbing so parametrised IDs like ``test_x[a->b]`` are not
# mangled; the array expansion quotes each ID exactly.
set -f
mapfile -t nodes < "$1"
[ "${#nodes[@]}" -eq 0 ] && exit 0

cov_args=()
if [ -n "${COVERAGE_DIR:-}" ]; then
    # Isolate each worker's coverage data so 8 concurrent runs don't race on a
    # shared .coverage file; the orchestrator combines them afterwards.
    export COVERAGE_FILE="$COVERAGE_DIR/.coverage.$$"
    cov_args=(--cov=unique --cov-report=)
fi

exec "${PYTEST_PYTHON:-.venv/bin/python}" -m pytest \
  -q -o addopts="" -p no:cacheprovider "${cov_args[@]}" "${nodes[@]}"
