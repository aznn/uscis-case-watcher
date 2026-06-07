# USCIS Case Watcher

USCIS Case Watcher automatically logs into your USCIS account, fetches case data from the USCIS APIs, detects changes vs. prior snapshots, and stores the full change history. It includes an ASCII summary report, a web dashboard, and Docker support for continuous monitoring.

## How does it work?

Run `./run.sh` — it logs into one or more USCIS accounts, checks case statuses, and prints a summary:

```
USCIS Watcher - 2026-01-02 04:08:43

Account: John
----------------------------------------
  John GC: No changes
  John EAD: No changes
  John AP: No changes

Account: Jane
----------------------------------------
  Jane GC: No changes
  Jane EAD: No changes
  Jane AP: No changes

========================================
All cases checked - no changes
========================================

USCIS Receipt Summary
Generated: 2026-01-02 04:07:21

===============================================================================
  I-131 - Application for Travel Documents
===============================================================================
Nickname       FTA0-1  FTA0-2  FTA0-3  FTA0-4  Last Event      Last Updated
-------------------------------------------------------------------------------
john-ap         ·       ·       ·       ·      8 days ago      2 days ago
jane-ap         ·       ·       ·       ·      3 days ago      3 days ago

===============================================================================
  I-765 - Application for Employment Authorization
===============================================================================
Nickname       FTA0-1  FTA0-2  FTA0-3  FTA0-4  Last Event      Last Updated
-------------------------------------------------------------------------------
john-ead       [x]     [x]     [x]      ·      2 days ago      2 days ago
jane-ead       [x]      ·       ·       ·      3 days ago      3 days ago
```

When a change is detected, it's recorded to an append-only changelog and stored in SQLite:

```markdown
# USCIS Case Changelog: My I-485

**Case Number:** IOE1234567890

This file tracks all changes detected in your USCIS case.

---

## 2025-12-30 08:17:28 - Initial fetch

First case data recorded.

**Last Updated:** 2025-12-29T23:27:26.377Z (3 hours ago)

**Events (3):**
- `FTA0` - 2025-12-29T23:27:22.805Z (3 hours ago)
- `FTA0` - 2025-12-29T23:27:22.693Z (3 hours ago)
- `IAF` - 2025-12-24T14:54:29.881Z (5 days ago)

**Notices (1):**
- Appointment Scheduled - 2025-12-29T01:28:53.368Z (1 day ago)

---
```

The web UI at `http://localhost:8080` shows a live dashboard with all cases and a per-case change history timeline.

## Setup

### 1. Prerequisites

- A USCIS account at [myaccount.uscis.gov](https://myaccount.uscis.gov)
- 2FA must be set up using an **authenticator app** (not email or SMS)
- When setting up the authenticator, save the secret key — you'll need it for the config

### 2. Install dependencies

```bash
uv sync
```

### 3. Create config file

```bash
cp config.example.json config.json
```

Edit `config.json`:

```json
{
  "accounts": [
    {
      "name": "My Account",
      "anon_name": "Account A",
      "username": "your.email@example.com",
      "password": "your-password",
      "totp_secret": "ABCD1234EFGH5678IJKL9012MNOP3456",
      "cases": [
        {
          "case_number": "IOE1234567890",
          "nickname": "My I-485"
        }
      ]
    }
  ],
  "browser": {
    "headless": false
  }
}
```

**Config fields:**
- `name` — display name used in output
- `anon_name` — anonymized name used with `summary.py --anon`
- `totp_secret` — base32 secret key shown when you set up 2FA on your USCIS account
- `browser.headless` — set to `true` to run Chrome without a visible window

### 4. Run

```bash
./run.sh
```

## Running

### One-shot check

```bash
./run.sh                  # standard run
./run.sh -v               # verbose output
./run.sh --dry-run        # check for changes without saving
./run.sh --simulate       # simulate a diff with mock data (primary testing tool)
./run.sh --headless       # force headless browser mode
```

### Daemon mode (continuous polling)

```bash
uv run uscis_watcher.py --daemon --headless
```

Polls every `POLL_INTERVAL_MINUTES` (default: 60). Runs forever until stopped.

### ASCII summary report

```bash
uv run summary.py                    # standard report
uv run summary.py --anon             # use anon_name instead of name
uv run summary.py --days-since-filing  # days since initial filing (IAF event) instead of relative time
uv run summary.py --show-dates       # show calendar dates (M/D) instead of "X days ago"
```

### Web UI

```bash
uv run python web.py     # starts Flask on http://localhost:8080
```

## Web UI

The web dashboard is served by Flask on port 8080.

| Route | Description |
|-------|-------------|
| `/` | Dashboard — all cases grouped by form type (I-131, I-765, I-485) with event timeline columns |
| `/case/<nickname>` | Case detail — current events, notices, change history, and raw JSON snapshot |
| `/api/cases` | JSON API — all case data |
| `/api/cases/<nickname>/changes` | JSON API — change history for a specific case (up to 500 entries) |

**Features:**
- Date toggle (top-right button) switches between relative times ("3 days ago") and full timestamps — preference saved in `localStorage`
- Timestamps use your browser's local timezone
- Cases grouped by form type; event codes shown as blue pills, notices as green pills
- Change history timeline on each case detail page (both real changes and silent-only updates)
- Raw JSON viewer at the bottom of each case detail page

## Docker

### Development (build locally)

```bash
docker compose up --build    # build and run watcher + web UI
docker compose up watcher    # watcher only
docker compose up web        # web UI only (no browser needed)
```

### Production (pre-built images from GHCR)

```bash
docker compose -f docker-compose.prod.yml up
```

Uses images from `ghcr.io/elyara/uscis-case-watcher/{watcher,web}:latest`, built automatically by GitHub Actions on every push to `main`.

### Configuration for Docker

Pass your config as an environment variable instead of a file:

```bash
USCIS_CONFIG_JSON='{"accounts":[...]}' docker compose up
```

Or set it in a `.env` file:

```
USCIS_CONFIG_JSON={"accounts":[...]}
```

### Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `USCIS_CONFIG_JSON` | — | Full config JSON as a string (alternative to `config.json`) |
| `POLL_INTERVAL_MINUTES` | `60` | Polling interval in daemon mode |
| `HEADLESS` | — | Set to `true` to force headless browser mode |
| `CHROME_BIN` | — | Path to Chromium binary (set automatically in Docker) |
| `CHROMEDRIVER_PATH` | — | Path to chromedriver (set automatically in Docker) |

## Data & Storage

```
output/
  history.db               # SQLite database with all changes (WAL mode)
  {case-slug-nickname}/
    latest.json            # case_details API snapshot
    receipt_info.json      # receipt_info API snapshot
    documents.json         # documents API snapshot
    case_status.json       # case_status API snapshot
    silent_updates.json    # timestamps of silent-only changes
    changelog.md           # append-only human-readable diff log
```

**Silent updates** — when only the `updatedAt` / `updatedAtTimestamp` field changes (no new events or notices), the change is recorded quietly to `silent_updates.json` and the database without printing an alert. These appear as "S" columns in the ASCII summary.

Both `config.json` and `output/` are gitignored.
