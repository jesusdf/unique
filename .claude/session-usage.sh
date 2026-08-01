#!/usr/bin/env bash
# Read the Claude Code session-usage percentage from the enclosing screen
# session (maintainer-authorized 2026-08-01, READ-ONLY, usage-% only — see
# skills/SKILL-development-workflow.md, team-mode section).
#
# Prints one line to stdout:
#   <N>       usage percentage, when the "You've used N% of your session
#             limit · resets HH:MM" status line is visible
#   no-line   the status line is not on screen (below the warning threshold,
#             or the limit message reset — full ratio available again)
#
# User, session and paths are all environment-derived: $STY (set inside
# screen; falls back to the user's single attached session), $TMPDIR, $USER.
set -euo pipefail

sty="${STY:-}"
if [[ -z "$sty" ]]; then
  sty="$(screen -ls 2>/dev/null | awk '/\(Attached\)/ {print $1; exit}')"
fi
if [[ -z "$sty" ]]; then
  echo "error: no screen session found (\$STY unset, none attached)" >&2
  exit 1
fi

tmp="$(mktemp "${TMPDIR:-/tmp}/session-usage-${USER}.XXXXXX")"
trap 'rm -f "$tmp"' EXIT

screen -S "$sty" -X hardcopy "$tmp"
# hardcopy writes asynchronously from the screen process; wait briefly.
for _ in 1 2 3 4 5; do
  [[ -s "$tmp" ]] && break
  sleep 0.2
done

pct="$(grep -oE "used [0-9]+% of your session limit" "$tmp" \
  | grep -oE '[0-9]+' | head -1 || true)"
echo "${pct:-no-line}"
