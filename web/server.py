#!/usr/bin/env python3
"""Flight-recorder web UI server (muse-pi-flight-recorder v0.3.0).

Serves the GitHub-style activity heatmap UI (web/static/) plus JSON APIs
backed by data/rollups/ and data/reports/:

  GET /                      -> web/static/index.html
  GET /static/<path>         -> static assets
  GET /api/meta              -> {"hostname": ...}
  GET /api/activity?days=365 -> [{date, task_count, op_count, top_tasks[]}]
  GET /api/day/YYYY-MM-DD    -> {date, task_count, op_count, tasks:[...]}
  GET /api/recent            -> [{date, title, what_why, outcome, op_count, ops:[]}] (10 newest)

Env: RECORDER_PORT (default 8081), RECORDER_DATA_DIR (default <repo>/data),
     MUSE_AUDIT_DIR (default ~/.local/share/muse-audit).
Binds 0.0.0.0 (LAN-only, same posture as the HUD). No auth in v1.
"""

import json
import os
import re
import socket
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = REPO_ROOT / "web" / "static"
DATA_DIR = Path(os.environ.get("RECORDER_DATA_DIR", REPO_ROOT / "data"))
AUDIT_DIR = Path(os.environ.get("MUSE_AUDIT_DIR",
                                Path.home() / ".local" / "share" / "muse-audit"))
PORT = int(os.environ.get("RECORDER_PORT", "8081"))

CONTENT_TYPES = {".html": "text/html; charset=utf-8",
                 ".css": "text/css; charset=utf-8",
                 ".js": "application/javascript; charset=utf-8",
                 ".json": "application/json",
                 ".png": "image/png",
                 ".svg": "image/svg+xml"}
_OPS_CACHE = {}


def read_jsonl(path):
    ops = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        ops.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
    except OSError:
        pass
    return ops


def day_ops(day):
    if day not in _OPS_CACHE:
        _OPS_CACHE[day] = read_jsonl(AUDIT_DIR / f"commands-{day}.jsonl")
    return _OPS_CACHE[day]


def load_rollup(day):
    p = DATA_DIR / "rollups" / f"rollup-{day}.json"
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def slim_op(op):
    return {k: op.get(k) for k in ("ts", "command", "detail", "status",
                                   "duration_ms")}


def task_ops(day, entries):
    if not entries:
        return []
    a, b = entries
    return [slim_op(op) for op in day_ops(day)[a - 1:b]]


def full_task(day, t):
    return {"title": t.get("title", ""), "what_why": t.get("what_why", ""),
            "outcome": t.get("outcome", ""), "op_count": t.get("op_count"),
            "ops": task_ops(day, t.get("entries"))}


class Handler(BaseHTTPRequestHandler):
    server_version = "flight-recorder-web/0.3.0"

    def _send(self, code, body, ctype="application/json"):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, ensure_ascii=False))

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path, qs = parsed.path, urllib.parse.parse_qs(parsed.query)
        if path == "/":
            return self._static("index.html")
        if path.startswith("/static/"):
            return self._static(path[len("/static/"):])
        if path == "/api/meta":
            return self._json({"hostname": socket.gethostname()})
        if path == "/api/activity":
            try:
                days = int(qs.get("days", ["365"])[0])
            except ValueError:
                days = 365
            return self._activity(days)
        if path == "/api/recent":
            return self._recent()
        m = re.match(r"^/api/day/(\d{4}-\d{2}-\d{2})$", path)
        if m:
            return self._day(m.group(1))
        self._json({"error": "not found"}, 404)

    def _static(self, rel):
        p = (STATIC_DIR / rel).resolve()
        if not str(p).startswith(str(STATIC_DIR.resolve())) or not p.is_file():
            return self._json({"error": "not found"}, 404)
        ctype = CONTENT_TYPES.get(p.suffix.lower(), "application/octet-stream")
        self._send(200, p.read_bytes(), ctype)

    def _activity(self, days):
        days = max(1, min(days, 730))
        items = []
        rollup_dir = DATA_DIR / "rollups"
        if rollup_dir.is_dir():
            for p in sorted(rollup_dir.glob("rollup-*.json")):
                try:
                    r = json.loads(p.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                items.append({
                    "date": r.get("date"),
                    "task_count": r.get("task_count", 0),
                    "op_count": r.get("op_count", 0),
                    "top_tasks": [t.get("title", "") for t in r.get("tasks", [])[:3]],
                })
        items.sort(key=lambda x: x["date"] or "")
        return self._json(items[-days:])

    def _day(self, day):
        r = load_rollup(day)
        if r is None:
            return self._json({"date": day, "task_count": 0, "op_count": 0,
                               "tasks": []})
        return self._json({"date": day, "task_count": r.get("task_count", 0),
                           "op_count": r.get("op_count", 0),
                           "tasks": [full_task(day, t)
                                     for t in r.get("tasks", [])]})

    def _recent(self, limit=10):
        out = []
        rollup_dir = DATA_DIR / "rollups"
        if rollup_dir.is_dir():
            rollups = sorted(rollup_dir.glob("rollup-*.json"),
                             key=lambda p: p.name, reverse=True)
            for p in rollups:
                try:
                    r = json.loads(p.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                day = r.get("date", "")
                for t in r.get("tasks", []):
                    ft = full_task(day, t)
                    ft["date"] = day
                    out.append(ft)
                    if len(out) >= limit:
                        return self._json(out)
        return self._json(out)

    def log_message(self, *args):
        pass  # quiet; output goes to the log file via start.sh


def main():
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"flight-recorder web UI on 0.0.0.0:{PORT}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
