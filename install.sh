#!/bin/bash
#
# Flight recorder — one-time install.
# Run as:  cd ~/flight-recorder-install && sudo ./install.sh
# You will be prompted for your password. Nothing else on the Pi is touched.
#
# What it does:
#   1. Installs audit.py into the gadget SDK package (root-owned, read-only for others)
#   2. Patches service.py at the single command-dispatch funnel (backup kept as service.py.bak)
#   3. Syntax-checks everything BEFORE restarting
#   4. Creates the log directory owned by musecell
#   5. Restarts musegadget.service and verifies it came back up
#
set -euo pipefail

SITE=/opt/musegadget/venv/lib/python3.13/site-packages/musegadget
VENV_PY=/opt/musegadget/venv/bin/python
LOG_DIR=/home/musecell/.local/share/muse-audit

if [ "$(id -u)" -ne 0 ]; then
  echo "Please run with sudo: sudo ./install.sh"
  exit 1
fi

echo "==> 1/5 writing audit.py ..."
cat > "$SITE/audit.py" <<'AUDIT_EOF'
"""Flight recorder: zero-token audit log for the Muse gadget daemon.

Wraps the executor's run callable so every invoked command
(system.run / file.read / file.write / device.health) is appended
as one JSON line to a daily log. Installed by wrapping the single
dispatch funnel in service.py:

    run_command=audited(self.executor.run)

The daemon does the writing; no extra tokens are spent per command.
File *contents* are never logged -- only paths and byte counts.
Secrets matching the redaction list are scrubbed before writing.
"""

import json
import os
import pwd
import re
import time
from datetime import datetime, timezone
from pathlib import Path

LOG_DIR = Path(os.environ.get("MUSE_AUDIT_DIR", "/home/musecell/.local/share/muse-audit"))
RETENTION_DAYS = 90

REDACT_PATTERNS = [
    r"mgst_[A-Za-z0-9_-]{40,}",  # gadget SDK tokens
    r"(?i)(password|passwd|secret|api[_-]?key|bearer)\s*[:=]\s*\S+",  # credential assignments
]


def _scrub(text):
    if not text:
        return text
    for pattern in REDACT_PATTERNS:
        text = re.sub(pattern, "[redacted]", text)
    return text


def _ensure_log_dir():
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        # The daemon runs as root; hand the dir to the run-as user so the
        # daily report job (unprivileged) can read it.
        run_as = os.environ.get("MUSEGADGET_RUN_AS", "musecell")
        try:
            pw = pwd.getpwnam(run_as)
            os.chown(LOG_DIR, pw.pw_uid, pw.pw_gid)
        except KeyError:
            pass
    except OSError:
        pass


def audited(run):
    """Wrap an executor run callable with audit logging."""
    _ensure_log_dir()

    def wrapper(command, params, timeout_ms):
        params = params or {}
        ts = datetime.now(timezone.utc).isoformat()
        start = time.monotonic()
        try:
            result = run(command, params, timeout_ms)
            ok = result.get("ok") if isinstance(result, dict) else None
            status = "ok" if ok else "error:" + str((result or {}).get("error"))[:120]
        except Exception as exc:  # never break dispatch
            result, status = {}, "exception:" + type(exc).__name__
        detail = params.get("command") or params.get("path") or ""
        record = {
            "ts": ts,
            "command": command,
            "detail": _scrub(detail),
            "cwd": params.get("cwd"),
            "bytes": params.get("limit") or len(params.get("data_b64") or ""),
            "status": _scrub(status),
            "duration_ms": int((time.monotonic() - start) * 1000),
        }
        try:
            _ensure_log_dir()
            with open(LOG_DIR / ("commands-" + ts[:10] + ".jsonl"), "a") as fh:
                fh.write(json.dumps(record) + "\n")
            cutoff = time.time() - RETENTION_DAYS * 86400
            for old in LOG_DIR.glob("commands-*.jsonl"):
                try:
                    if old.stat().st_mtime < cutoff:
                        old.unlink()
                except OSError:
                    pass
        except OSError:
            pass
        return result

    return wrapper
AUDIT_EOF
chmod 644 "$SITE/audit.py"
chown root:root "$SITE/audit.py"

echo "==> 2/5 patching service.py (backup kept as service.py.bak) ..."
"$VENV_PY" - "$SITE/service.py" <<'PATCH_EOF'
import sys
path = sys.argv[1]
with open(path) as fh:
    orig = fh.read()
src = orig
if "from musegadget.audit import audited" not in src:
    anchor = "from musegadget.executor import COMMAND_SPECS, Executor"
    assert anchor in src, "import anchor not found in service.py"
    src = src.replace(anchor, "from musegadget.audit import audited\n" + anchor)
if "run_command=audited(self.executor.run)," not in src:
    anchor = "run_command=self.executor.run,"
    assert anchor in src, "dispatch anchor not found in service.py"
    src = src.replace(anchor, "run_command=audited(self.executor.run),")
if src != orig:
    import os
    bak = path + ".bak"
    if not os.path.exists(bak):
        with open(bak, "w") as fh:
            fh.write(orig)
        print("backup written:", bak)
    with open(path, "w") as fh:
        fh.write(src)
    print("service.py patched")
else:
    print("service.py already patched, nothing to do")
PATCH_EOF

echo "==> 3/5 syntax check (before touching the running service) ..."
"$VENV_PY" -m py_compile "$SITE/audit.py" "$SITE/service.py"
"$VENV_PY" -c "from musegadget.audit import audited; print('audit hook imports OK')"

echo "==> 4/5 creating log directory ..."
mkdir -p "$LOG_DIR"
chown musecell: "$LOG_DIR"
chmod 755 "$LOG_DIR"

echo "==> 5/5 restarting musegadget.service ..."
systemctl restart musegadget.service
sleep 3
systemctl is-active --quiet musegadget.service && echo "service is active"
echo "--- recent service log ---"
journalctl -u musegadget.service --since "2 min ago" --no-pager | tail -5

echo ""
echo "Done. The next command Muse runs on this Pi will be the first logged entry:"
echo "  $LOG_DIR/commands-$(date -u +%F).jsonl"
