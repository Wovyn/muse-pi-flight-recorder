#!/bin/bash
# Flight-recorder web UI launcher — no sudo, no systemd. Safe to run from @reboot cron.
# Usage: /home/musecell/projects/muse-pi-flight-recorder/start.sh
set -u
APP_DIR="$(cd "$(dirname "$0")" && pwd)"
PIDFILE="$APP_DIR/recorder-web.pid"
LOG="$APP_DIR/recorder-web.log"
PORT="${RECORDER_PORT:-8081}"

cd "$APP_DIR" || exit 1

if [ -f "$PIDFILE" ]; then
  oldpid="$(cat "$PIDFILE" 2>/dev/null || true)"
  if [ -n "$oldpid" ] && kill -0 "$oldpid" 2>/dev/null; then
    echo "recorder-web already running (pid $oldpid)"
    exit 0
  fi
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 not found in PATH" >&2
  exit 1
fi

nohup env RECORDER_PORT="$PORT" python3 web/server.py >>"$LOG" 2>&1 &
echo $! > "$PIDFILE"
echo "recorder-web started (pid $(cat "$PIDFILE")) on port $PORT — log: $LOG"
