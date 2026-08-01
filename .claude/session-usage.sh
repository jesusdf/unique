#!/usr/bin/env bash
# .claude/session-usage.sh — session-usage probe + cache service.
# Maintainer-authorized 2026-08-01, READ-ONLY, usage-% only — see
# skills/SKILL-development-workflow.md (team-mode section).
#
# Subcommands:
#   read    (default) live screen read; prints <pct> or "no-line" and appends
#           the reading to the state file (plus a "reset" marker when the
#           usage line vanishes or drops sharply after being visible)
#   cached  no screen access: prints "value=<v> age=<s>s verdict=<verdict>";
#           verdicts: no-data | ok | below-threshold | above-threshold |
#           reset-detected (line vanished/dropped after being visible → the
#           full ratio is back, pending work can resume). ",stale" is
#           appended when the last sample is older than 15 min.
#   daemon  detached single-instance sampler (every 5 min); exits on its own
#           when the screen session disappears
#
# Everything is environment-derived: $STY (falls back to the user's single
# attached screen session), $USER, $XDG_RUNTIME_DIR (falls back to /tmp).
# State lives OUTSIDE the repo.
set -euo pipefail

THRESHOLD=90
INTERVAL=300
KEEP_LINES=200
STALE_SECS=900
STATE_DIR="${XDG_RUNTIME_DIR:-/tmp}"
STATE_FILE="$STATE_DIR/session-usage-${USER}.state"
LOCK_FILE="$STATE_DIR/session-usage-${USER}.lock"

find_sty() {
  local sty="${STY:-}"
  if [[ -z "$sty" ]]; then
    sty="$(screen -ls 2>/dev/null | awk '/\(Attached\)/ {print $1; exit}')"
  fi
  if [[ -z "$sty" ]]; then
    echo "error: no screen session found (\$STY unset, none attached)" >&2
    return 1
  fi
  printf '%s\n' "$sty"
}

live_read() { # $1 = screen session; prints <pct> or no-line
  local sty="$1" tmp pct
  tmp="$(mktemp "$STATE_DIR/session-usage-${USER}.XXXXXX")"
  screen -S "$sty" -X hardcopy "$tmp"
  # hardcopy writes asynchronously from the screen process; wait briefly.
  for _ in 1 2 3 4 5; do
    [[ -s "$tmp" ]] && break
    sleep 0.2
  done
  pct="$(grep -oE "used [0-9]+% of your session limit" "$tmp" \
    | grep -oE '[0-9]+' | head -1 || true)"
  rm -f "$tmp"
  printf '%s\n' "${pct:-no-line}"
}

record() { # $1 = value; append it, with a reset marker on the transition
  local val="$1" prev now
  now="$(date +%s)"
  prev=""
  if [[ -s "$STATE_FILE" ]]; then
    prev="$(awk -F'\t' '$2 ~ /^[0-9]+$/ || $2 == "no-line" {v=$2} END{print v}' \
      "$STATE_FILE")"
  fi
  # The usage line only appears near the limit, so numeric → gone (or a
  # sharp drop) means the limit message reset.
  if [[ "$prev" =~ ^[0-9]+$ ]]; then
    if [[ "$val" == "no-line" ]] \
      || { [[ "$val" =~ ^[0-9]+$ ]] && ((val < prev - 30)); }; then
      printf '%s\treset\n' "$now" >>"$STATE_FILE"
    fi
  fi
  printf '%s\t%s\n' "$now" "$val" >>"$STATE_FILE"
  if (($(wc -l <"$STATE_FILE") > KEEP_LINES)); then
    tail -n "$KEEP_LINES" "$STATE_FILE" >"${STATE_FILE}.trim" \
      && mv "${STATE_FILE}.trim" "$STATE_FILE"
  fi
}

cmd_read() {
  local sty val
  sty="$(find_sty)"
  val="$(live_read "$sty")"
  record "$val"
  printf '%s\n' "$val"
}

cmd_cached() {
  if [[ ! -s "$STATE_FILE" ]]; then
    echo "value=none age=- verdict=no-data"
    return
  fi
  local last_ts last_val now age last_num_ts last_reset_ts verdict
  last_ts="$(tail -n1 "$STATE_FILE" | cut -f1)"
  last_val="$(tail -n1 "$STATE_FILE" | cut -f2)"
  now="$(date +%s)"
  age=$((now - last_ts))
  last_num_ts="$(awk -F'\t' '$2 ~ /^[0-9]+$/ {t=$1} END{print t+0}' "$STATE_FILE")"
  last_reset_ts="$(awk -F'\t' '$2 == "reset" {t=$1} END{print t+0}' "$STATE_FILE")"
  if ((last_reset_ts > 0 && last_reset_ts >= last_num_ts)); then
    verdict=reset-detected
  elif [[ "$last_val" =~ ^[0-9]+$ ]] && ((last_val >= THRESHOLD)); then
    verdict=above-threshold
  elif [[ "$last_val" =~ ^[0-9]+$ ]]; then
    verdict=below-threshold
  else
    verdict=ok
  fi
  ((age > STALE_SECS)) && verdict="${verdict},stale"
  echo "value=$last_val age=${age}s verdict=$verdict"
}

cmd_daemon() {
  find_sty >/dev/null # fail fast if there is nothing to watch
  setsid bash "$0" _loop >/dev/null 2>&1 </dev/null &
  echo "daemon: sampling every ${INTERVAL}s -> $STATE_FILE (single instance)"
}

cmd_loop() { # internal: the detached sampler body
  exec 9>>"$LOCK_FILE"
  flock -n 9 || exit 0 # another instance already holds the lock
  local sty
  sty="$(find_sty)" || exit 1
  while screen -ls 2>/dev/null | grep -qF "$sty"; do
    record "$(live_read "$sty" || echo no-line)"
    sleep "$INTERVAL"
  done
}

case "${1:-read}" in
read) cmd_read ;;
cached) cmd_cached ;;
daemon) cmd_daemon ;;
_loop) cmd_loop ;;
*)
  echo "usage: $0 [read|cached|daemon]" >&2
  exit 2
  ;;
esac
