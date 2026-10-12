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
