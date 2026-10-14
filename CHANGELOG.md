# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.1] - 2026-10-14

### Fixed
- Heatmap layout: fluid day-cell sizing fills the container width (min 10px,
  then scrolls) so the full calendar fits laptop browsers with no horizontal
  scrollbar and no whitespace on wide desktops; month labels use the same
  computed pitch; grid rebuilds debounced on resize. Content max-width 1040px.
- Operations view: day color floored at the tasks-view color, so switching
  from tasks to operations never lightens a day (operations are the
  finer-grained count).
- Narrow screens: heatmap opens scrolled to the newest days on the right.
- Legend and hint moved out of the horizontal scroll container so they stay
  visible on phones; legend swatches track the fluid cell size.

## [0.3.0] - 2026-10-11

### Added
- `web/server.py`: stdlib-only Python web server (no dependencies) serving the
  UI and JSON APIs (`/api/meta`, `/api/activity`, `/api/day/YYYY-MM-DD`,
  `/api/recent`). Binds 0.0.0.0, port from `RECORDER_PORT` (default 8081).
- `web/static/`: vanilla HTML/CSS/JS UI — GitHub-style 52x7 activity heatmap
  with tasks/operations toggle, hover tooltips, click-to-open day reports,
  and an expandable recent-activity list. Hostname header, Pi-local days.
- `start.sh`: launcher following the HUD convention (no sudo, no systemd,
  pidfile + log, idempotent, safe for @reboot cron).

## [0.2.0] - 2026-10-11

### Added
- `recorder/rollup.py`: rollup aggregator building `data/rollups/rollup-YYYY-MM-DD.json`
  from the day's JSONL log + markdown report (task titles, what/why, outcomes,
  entry ranges, op counts, per-type breakdown).
- `data/` runtime-data convention (gitignored): `data/reports/` holds synced daily
  reports, `data/rollups/` holds generated rollups. Backfilled Oct 9-10, 2026.
- Daily-report job now syncs each report to the Pi and runs the rollup;
  pipeline documented in README.

## [0.1.0] - 2026-10-11

### Added
- Repo scaffolding: README, CHANGELOG, NOTICE, .gitignore.
- `recorder/audit.py`: current on-Pi audit implementation (interim wrapper around
  the daemon dispatch funnel, pending the upstream SDK hook).
- `install.sh`: installer used for the current on-Pi deployment (Oct 9, 2026).
