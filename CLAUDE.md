# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

USCIS Case Watcher is an automated monitoring system that logs into USCIS accounts, fetches case data from multiple USCIS APIs, detects changes vs. prior snapshots, stores change history in SQLite, and provides both ASCII and web-based timeline views.

## Commands

```bash
# Install dependencies
uv sync

# Run the watcher (one-shot)
./run.sh                  # standard run
./run.sh -v               # verbose output
./run.sh --dry-run        # check for changes without saving
./run.sh --simulate       # simulate a diff with mock data (primary testing tool)
./run.sh --headless       # force headless browser mode

# Run continuously (daemon mode)
uv run uscis_watcher.py --daemon --headless   # polls every POLL_INTERVAL_MINUTES (default 60)

# Generate ASCII summary report
uv run summary.py
uv run summary.py --anon               # anonymize account names
uv run summary.py --days-since-filing   # days since initial filing instead of days ago
uv run summary.py --show-dates          # calendar dates instead of days

# Web UI
uv run python web.py                    # starts Flask on http://localhost:8080

# Docker
docker compose up --build               # runs watcher + web UI
docker compose up watcher               # watcher only
docker compose up web                   # web UI only
```

There is no test suite or linter configured.

## Architecture

### Data Flow

1. **Auth** — `USCISWatcher.login()` drives Chrome via Selenium, submits credentials, and generates OTP via `pyotp`
2. **Fetch** — `USCISWatcher.fetch_all_case_data()` runs a single `Promise.all()` via Selenium's async JS execution to call four USCIS APIs in parallel:
   - `/account/case-service/api/cases/{case_number}` → `case_details`
   - `/secure-messaging/api/case-service/receipt_info/{case_number}` → `receipt_info`
   - `/account/case-service/api/cases/{case_number}/documents` → `documents`
   - `/account/case-service/api/case_status/{case_number}` → `case_status`
3. **Diff** — `process_data_source()` loads the prior snapshot from `output/{case-slug}/`, compares with `DeepDiff`, classifies the change, appends to `changelog.md`, and records to SQLite
4. **Report** — `summary.py` renders ASCII timeline; `web.py` serves HTML dashboard reading from JSON files and SQLite

### Change Classification

- **Silent update**: only `updatedAt` / `updatedAtTimestamp` changed → logged to `silent_updates.json` + DB, no alert
- **Real change**: new events, notices, or other data → console alert + `changelog.md` + DB with diff JSON
- **First run**: snapshots saved, initial changelog created

### Storage Layout

```
output/
  history.db               # SQLite database with all changes (WAL mode)
  {case-slug-nickname}/
    latest.json            # case_details snapshot
    receipt_info.json
    documents.json
    case_status.json
    silent_updates.json    # timestamps of silent-only changes
    changelog.md           # append-only human-readable diff log
```

### Key Files

| File | Role |
|------|------|
| `uscis_watcher.py` | Main application — auth, fetch, diff, changelog |
| `summary.py` | ASCII timeline report generator |
| `db.py` | SQLite database module — schema, read/write helpers |
| `web.py` | Flask web UI — dashboard and case detail views |
| `templates/` | Jinja2 HTML templates (Tailwind CSS via CDN) |
| `config.json` | Credentials and case list (gitignored; copy from `config.example.json`) |
| `run.sh` | Thin shell wrapper around `uv run uscis_watcher.py` |
| `Dockerfile` | Multi-stage build: `watcher` (with Chromium) and `web` (Flask only) |
| `docker-compose.yml` | Services: `watcher` (periodic polling) + `web` (port 8080) |

### `DATA_SOURCES` Registry (`uscis_watcher.py`)

Each of the four API sources is registered with its own `load_*` / `save_*` functions and then processed through the same `process_data_source()` pipeline. When adding a new API endpoint, follow this pattern.

### Database Schema (`db.py`)

Single `changes` table stores both real changes and silent updates:
- `is_silent` flag distinguishes them
- `diff_json` contains the serialized DeepDiff (NULL for silent updates)
- `summary` has a human-readable one-liner
- WAL mode enabled for concurrent read (web) / write (watcher)

### Docker Architecture

Multi-stage Dockerfile with shared `base` stage (Python + uv + deps):
- `watcher` stage adds Chromium/chromedriver, runs `--daemon --headless`
- `web` stage copies Flask app and templates, serves on port 8080
- Both share `./output` as a bind mount for SQLite access
- `CHROME_BIN` and `CHROMEDRIVER_PATH` env vars tell Selenium to use system Chrome in Docker

## Configuration

Copy `config.example.json` → `config.json` and fill in:

```json
{
  "accounts": [{
    "name": "Display name",
    "anon_name": "Name for --anon mode",
    "username": "email@example.com",
    "password": "...",
    "totp_secret": "Base32 TOTP secret",
    "cases": [{ "case_number": "IOE...", "nickname": "My I-485" }]
  }],
  "browser": { "headless": false }
}
```

Environment variables for Docker/daemon mode:
- `POLL_INTERVAL_MINUTES` — polling interval (default: 60)
- `HEADLESS` — force headless mode (set to "true")
- `CHROME_BIN` — path to Chromium binary
- `CHROMEDRIVER_PATH` — path to chromedriver binary

`config.json` and `output/` are both gitignored.
