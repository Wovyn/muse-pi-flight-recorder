#!/usr/bin/env python3
"""Flight-recorder rollup aggregator (muse-pi-flight-recorder v0.2.0).

Builds data/rollups/rollup-YYYY-MM-DD.json from:
  - the day's raw JSONL audit log  (~/.local/share/muse-audit/commands-YYYY-MM-DD.jsonl)
  - the day's markdown daily report (data/reports/YYYY-MM-DD.md, if present)

The rollup is the fast data source for the web UI heatmap: one small JSON per
day instead of re-reading raw logs. Reports are synced into data/reports/ by
the daily-report job right after generation.

Usage:  python3 recorder/rollup.py [YYYY-MM-DD]   (default: yesterday, UTC)
"""

import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
AUDIT_DIR = Path(os.environ.get("MUSE_AUDIT_DIR",
                                Path.home() / ".local" / "share" / "muse-audit"))
DATA_DIR = Path(os.environ.get("RECORDER_DATA_DIR", REPO_ROOT / "data"))
ROLLUP_VERSION = 1

TASK_HEADING = re.compile(r"^##\s+\d+\.\s+(.*)$")
ENTRIES_RANGE = re.compile(r"entries\s+(\d+)\s*[-\u2013]\s*(\d+)")
TRAILING_META = re.compile(r"^(.*?)\s*\([^()]*\)\s*$")
FIELD = re.compile(r"\*\*(What / why|Outcome):\*\*\s*(.*?)(?=\n\*\*|\Z)",
                   re.DOTALL)


def parse_report_tasks(report_path):
    """Extract the task list from a daily markdown report.

    Returns a list of {title, entries, what_why, outcome, op_count}.
    Only numbered '## N. ...' headings count as tasks ('## Drill-down' etc.
    are ignored).
    """
    text = report_path.read_text(encoding="utf-8")
    tasks, current = [], None
    for line in text.splitlines():
        m = TASK_HEADING.match(line)
        if m:
            if current:
                tasks.append(current)
            raw = m.group(1).strip()
            em = ENTRIES_RANGE.search(raw)
            entries = [int(em.group(1)), int(em.group(2))] if em else None
            tm = TRAILING_META.match(raw)
            title = tm.group(1).strip() if tm else raw
            current = {"title": title, "entries": entries,
                       "what_why": "", "outcome": "", "_body": []}
        elif current is not None:
            if line.startswith("## "):
                tasks.append(current)
                current = None
            else:
                current["_body"].append(line)
    if current:
        tasks.append(current)
    for t in tasks:
        body = "\n".join(t.pop("_body"))
        for name, val in FIELD.findall(body):
            key = "what_why" if name == "What / why" else "outcome"
            t[key] = " ".join(val.strip().split())
        if t["entries"]:
            t["op_count"] = t["entries"][1] - t["entries"][0] + 1
        else:
            t["op_count"] = None
    return tasks


def session_fallback(ops):
    """Split ops into sessions on >30min gaps; used when no report exists."""
    sessions, last_ts = 0, None
    for op in ops:
        try:
            ts = datetime.fromisoformat(op.get("ts", ""))
        except (ValueError, TypeError):
            ts = None
        if ts is None or last_ts is None or (ts - last_ts) > timedelta(minutes=30):
            sessions += 1
        last_ts = ts or last_ts
    return sessions


def build_rollup(day):
    log_path = AUDIT_DIR / f"commands-{day}.jsonl"
    ops = []
    if log_path.exists():
        for line in log_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                ops.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    report_path = DATA_DIR / "reports" / f"{day}.md"
    tasks, task_source = [], "none"
    if report_path.exists():
        tasks = parse_report_tasks(report_path)
        task_source = "report" if tasks else "report-empty"
    if not tasks and ops:
        task_source = "session-heuristic"
    by_type, errors = {}, 0
    for op in ops:
        by_type[op.get("command", "?")] = by_type.get(op.get("command", "?"), 0) + 1
        if op.get("status") not in ("ok", None):
            errors += 1
    rollup = {
        "rollup_version": ROLLUP_VERSION,
        "date": day,
        "generated_ts": datetime.now(timezone.utc).isoformat(),
        "op_count": len(ops),
        "task_count": len(tasks) if tasks else session_fallback(ops),
        "task_source": task_source,
        "by_type": by_type,
        "errors": errors,
        "time_range": {
            "first": ops[0].get("ts") if ops else None,
            "last": ops[-1].get("ts") if ops else None,
        },
        "tasks": tasks,
    }
    out_dir = DATA_DIR / "rollups"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"rollup-{day}.json"
    out_path.write_text(json.dumps(rollup, indent=2, ensure_ascii=False) + "\n",
                        encoding="utf-8")
    return out_path, rollup


def main():
    if len(sys.argv) > 1:
        day = sys.argv[1]
        datetime.strptime(day, "%Y-%m-%d")  # validate format
    else:
        day = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
    out_path, rollup = build_rollup(day)
    print(f"wrote {out_path} "
          f"({rollup['op_count']} ops, {rollup['task_count']} tasks"
          f" via {rollup['task_source']})")


if __name__ == "__main__":
    main()
