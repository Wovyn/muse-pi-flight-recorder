# muse-pi-flight-recorder

Wovyn R&D project — command audit ("flight recorder") for Muse-Pi-1, plus a
GitHub-style web UI for browsing activity history.

## What it does

Automatically logs every `system.run` command, `file.read`, and `file.write`
(file paths and byte counts — never file contents) issued on Muse-Pi-1, with
secret redaction applied before records are written. A daily job turns the raw
log into a readable markdown report of higher-level tasks with drill-down to
exact commands. A web UI (planned) presents a calendar heatmap of activity, a
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
- `recorder/` — (planned) listener subscribing to the upstream hook, rollup
  aggregator
- `reporter/` — (planned) daily report generator
- `web/` — (planned) stdlib-only web server + vanilla-JS heatmap UI (port 8081)
- `install.sh` — installer used for the current on-Pi deployment

## Status

v0.1.0 (planned): repo scaffolding + current recorder code. See
[CHANGELOG.md](CHANGELOG.md).

## Conventions

- Semver, keep-a-changelog, NOTICE attributions (Apache-2.0, see LICENSE).
- `main` is the release branch. Scott is the sole pusher; Muse commits locally
  on the Pi as MuseCell-1.
- No version bumps or commits without Scott's explicit go-ahead.
