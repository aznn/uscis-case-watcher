# USCIS Case Watcher

USCIS Case Watcher automatically logs into your USCIS account and uses the API to check the status of your cases.

## How does it work?

Run the script `./run.sh` - it automatically logs into one or more USCIS accounts and checks case statuses. You will get an output like this:

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

It also stores the latest JSON for your case as well as an append-only changelog so you can see how things changed over time:

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

## Setup

### 1. Prerequisites

- A USCIS account at [myaccount.uscis.gov](https://myaccount.uscis.gov)
- 2FA must be set up using an **authenticator app** (not email or SMS)
- When setting up the authenticator, save the secret key - you'll need it for the config

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

**Note:** The `totp_secret` is the base32 secret key shown when you set up 2FA on your USCIS account.

### 4. Run

```bash
./run.sh
```

Options:
- `./run.sh -v` - Verbose output
- `./run.sh --dry-run` - Check without saving changes
- `./run.sh --simulate` - Test change detection
