# muse-pi-flight-recorder

Wovyn R&D project — command audit ("flight recorder") for Muse-Pi-1, plus a
GitHub-style web UI for browsing activity history.

## What it does

Automatically logs every `system.run` command, `file.read`, and `file.write`
(file paths and byte counts — never file contents) issued on Muse-Pi-1, with
secret redaction applied before records are written. A daily job turns the raw
log into a readable markdown report of higher-level tasks with drill-down to
exact commands. A web UI presents a calendar heatmap of activity, a
recent-operations list, and per-day reports.

## Architecture: two repos

- **Upstream SDK fork** (separate): the audit *hook* — a registration point in
  the gadget daemon's command-dispatch funnel. No log writing. Being discussed
  with the Muse Gadgets SDK owners as an upstream PR.
- **This repo**: the *recorder* — everything that subscribes to the hook:
  JSONL writing, redaction, retention, daily reports, rollup aggregation,
  web UI.

Until the upstream hook lands, `recorder/audit.py` is the interim
implementation: a thin wrapper installed around the daemon's dispatch funnel
(see `install.sh`).

## Repo layout

- `recorder/audit.py` — zero-token audit wrapper (current on-Pi implementation)
- `recorder/rollup.py` — rollup aggregator: builds one small JSON per day
  from the raw JSONL log + the markdown daily report
- `recorder/` — (planned) listener subscribing to the upstream hook
- `reporter/` — (planned) daily report generator
- `web/` — stdlib-only Python web server (`web/server.py`) + vanilla
  HTML/CSS/JS heatmap UI (`web/static/`). Binds 0.0.0.0, port from
  `RECORDER_PORT` (default 8081). Launch with `./start.sh` — no sudo, no
  systemd (same convention as the HUD); idempotent, writes a pidfile and log.
  APIs: `GET /api/meta`, `GET /api/activity?days=365`,
  `GET /api/day/YYYY-MM-DD`, `GET /api/recent`.
- `install.sh` — installer used for the current on-Pi deployment
- `data/` — runtime data, not committed: `data/reports/YYYY-MM-DD.md`
  (synced daily reports) and `data/rollups/rollup-YYYY-MM-DD.json`

## Data pipeline

1. The daemon's audit wrapper appends to
   `~/.local/share/muse-audit/commands-YYYY-MM-DD.jsonl` (90-day retention).
2. The daily-report job (~7:47am Scott's time) generates the markdown report,
   syncs it to `data/reports/` on the Pi, and runs
   `python3 recorder/rollup.py YYYY-MM-DD`.
3. `rollup.py` parses the report's task list (titles, what/why, outcomes,
   entry ranges) and combines it with JSONL counts into
   `data/rollups/rollup-YYYY-MM-DD.json` — the fast data source for the web UI.
4. The web UI serves the heatmap from the rollups and renders day reports
   from the synced markdown + rollup entry ranges.

## Status

v0.3.0: web UI — GitHub-style heatmap, day drill-down, recent activity.
See [CHANGELOG.md](CHANGELOG.md).

## Conventions

- Semver, keep-a-changelog, NOTICE attributions (Apache-2.0, see LICENSE).
- `main` is the release branch. Scott is the sole pusher; Muse commits locally
  on the Pi as MuseCell-1.
- No version bumps or commits without Scott's explicit go-ahead.
