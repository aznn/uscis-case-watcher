#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///

import argparse
import json
import os
import re
from pathlib import Path
from datetime import datetime, timezone
from collections import defaultdict
from typing import Optional

SCRIPT_DIR = Path(__file__).parent
OUTPUT_DIR = SCRIPT_DIR / "output"
CONFIG_FILE = SCRIPT_DIR / "config.json"


def slugify(text: str) -> str:
    """Convert text to a filesystem-safe slug"""
    text = text.lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[-\s]+', '-', text)
    return text


def load_anon_mapping() -> dict[str, str]:
    """Load nickname to anon_name mapping from USCIS_CONFIG_JSON env var or config.json."""
    try:
        config_json = os.environ.get("USCIS_CONFIG_JSON")
        if config_json:
            config = json.loads(config_json)
        elif CONFIG_FILE.exists():
            with open(CONFIG_FILE) as f:
                config = json.load(f)
        else:
            return {}

        mapping = {}
        for account in config.get("accounts", []):
            anon_name = account.get("anon_name", account.get("name", "Unknown"))
            for case in account.get("cases", []):
                nickname = case.get("nickname", "")
                if nickname:
                    # Extract case type (last word, e.g., "GC", "EAD", "AP")
                    parts = nickname.split()
                    case_type = parts[-1] if parts else ""
                    # Create slugified nickname as key
                    slug = slugify(nickname)
                    # Create anon display name
                    mapping[slug] = f"{anon_name} {case_type}"

        return mapping
    except Exception as e:
        print(f"Warning: Could not load anon mapping: {e}")
        return {}


def get_time_ago(timestamp: str) -> str:
    """Convert timestamp to human-readable relative time."""
    then = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    now = datetime.now(timezone.utc)
    diff = now - then

    total_seconds = int(diff.total_seconds())
    minutes = total_seconds // 60
    hours = total_seconds // 3600
    days = total_seconds // 86400

    if days > 0:
        return f"{days} day{'s' if days != 1 else ''} ago"
    elif hours > 0:
        remaining_minutes = minutes - (hours * 60)
        if remaining_minutes > 0:
            return f"{hours}h {remaining_minutes}m ago"
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    elif minutes > 0:
        return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
    else:
        return "just now"


def has_event_code(events: list, event_code: str) -> bool:
    """Check if there's an event with the given event code."""
    return any(e.get("eventCode") == event_code for e in events)


def get_days_since(timestamp: str) -> int:
    """Calculate days since a timestamp."""
    then = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    now = datetime.now(timezone.utc)
    diff = now - then
    return diff.days


def get_days_between(start_timestamp: str, end_timestamp: str) -> int:
    """Calculate days between two timestamps."""
    start = datetime.fromisoformat(start_timestamp.replace("Z", "+00:00"))
    end = datetime.fromisoformat(end_timestamp.replace("Z", "+00:00"))
    diff = end - start
    return diff.days


def get_event_occurrences(events: list, event_code: str) -> list[str]:
    """Get all timestamps for events with the given event code, sorted chronologically."""
    timestamps = []
    for event in events:
        if event.get("eventCode") == event_code:
            timestamp = event.get("eventTimestamp")
            if timestamp:
                timestamps.append(timestamp)
    # Sort chronologically (earliest first)
    timestamps.sort()
    return timestamps


def count_max_event_occurrences(receipts: list[dict], event_code: str) -> int:
    """Count the maximum number of times an event code appears in any single receipt."""
    max_count = 0
    for receipt in receipts:
        events = receipt.get("events", [])
        count = sum(1 for e in events if e.get("eventCode") == event_code)
        max_count = max(max_count, count)
    return max_count


def get_earliest_event_timestamp(receipts: list[dict], event_code: str) -> str:
    """Get the earliest eventTimestamp for a given event code across all receipts."""
    timestamps = []
    for receipt in receipts:
        events = receipt.get("events", [])
        for event in events:
            if event.get("eventCode") == event_code:
                timestamp = event.get("eventTimestamp")
                if timestamp:
                    timestamps.append(timestamp)

    return min(timestamps) if timestamps else ""


def get_date_from_timestamp(timestamp: str) -> str:
    """Extract date (YYYY-MM-DD) from ISO timestamp."""
    dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    return dt.strftime("%Y-%m-%d")


def get_short_date(timestamp: str) -> str:
    """Extract short date (M/D) from ISO timestamp."""
    dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    return f"{dt.month}/{dt.day}"


def get_date_label(timestamp: str) -> str:
    """Format timestamp as 'Jan 15, 2024' for absolute date display."""
    dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    return dt.strftime("%b %-d, %Y")


def build_timeline(receipts: list[dict]) -> list[tuple[str, str, str, int]]:
    """
    Build a chronological timeline grouped by event_code or (silent, date).

    Returns a list of (type, identifier, date, count) tuples sorted chronologically.
    - type: "event" or "silent"
    - identifier: event code or "S"
    - date: earliest date (YYYY-MM-DD) for this group (used for sort order)
    - count: how many columns needed (max total occurrences of this code in any single case)
    """
    # Group events by code only and track max total occurrences across all receipts
    event_groups: dict[str, dict] = {}  # code -> {"earliest": ts, "max_count": 0}

    for receipt in receipts:
        events = receipt.get("events", [])
        receipt_code_counts: dict[str, int] = defaultdict(int)
        receipt_code_earliest: dict[str, str] = {}

        for event in events:
            code = event.get("eventCode")
            timestamp = event.get("eventTimestamp")
            if code and timestamp:
                receipt_code_counts[code] += 1
                if code not in receipt_code_earliest or timestamp < receipt_code_earliest[code]:
                    receipt_code_earliest[code] = timestamp

        for code, count in receipt_code_counts.items():
            if code not in event_groups:
                event_groups[code] = {"earliest": receipt_code_earliest[code], "max_count": 0}
            else:
                if receipt_code_earliest[code] < event_groups[code]["earliest"]:
                    event_groups[code]["earliest"] = receipt_code_earliest[code]
            event_groups[code]["max_count"] = max(event_groups[code]["max_count"], count)

    # Group silent updates by date
    silent_groups = defaultdict(lambda: {"date": "", "timestamps": set(), "max_count": 0})

    for receipt in receipts:
        silent_updates = receipt.get("silent_updates", [])
        receipt_silent_counts = defaultdict(int)

        for silent_ts in silent_updates:
            date = get_date_from_timestamp(silent_ts)
            silent_groups[date]["date"] = date
            silent_groups[date]["timestamps"].add(silent_ts)
            receipt_silent_counts[date] += 1

        # Update max counts
        for date, count in receipt_silent_counts.items():
            silent_groups[date]["max_count"] = max(silent_groups[date]["max_count"], count)

    # Build timeline entries
    timeline = []

    # Add event groups (one entry per unique code)
    for code, info in event_groups.items():
        earliest = info["earliest"]
        timeline.append((earliest, "event", code, earliest[:10], info["max_count"]))

    # Add silent update groups
    for date, info in silent_groups.items():
        earliest = min(info["timestamps"])
        timeline.append((earliest, "silent", "S", date, info["max_count"]))

    # Sort by earliest timestamp in each group
    timeline.sort(key=lambda x: x[0])

    # Return as (type, identifier, date, count) tuples
    return [(typ, identifier, date, count) for _, typ, identifier, date, count in timeline]


def get_last_event_time(events: list) -> str:
    """Get the timestamp of the most recent event."""
    if not events:
        return "N/A"
    # Find the most recent event by createdAtTimestamp
    latest = max(events, key=lambda e: e.get("createdAtTimestamp", ""))
    timestamp = latest.get("createdAtTimestamp", "")
    if not timestamp:
        return "N/A"
    return get_time_ago(timestamp)


def load_receipt_info(folder: Path) -> Optional[dict]:
    """Load receipt_info.json from a folder if it exists."""
    receipt_info_path = folder / "receipt_info.json"
    if not receipt_info_path.exists():
        return None

    try:
        with open(receipt_info_path) as f:
            data = json.load(f)
        return data.get("data", {}).get("receipt_details", {}) if data.get("data") else None
    except Exception:
        return None


def load_silent_updates(folder: Path) -> list[str]:
    """Load silent update timestamps from silent_updates.json."""
    silent_updates_path = folder / "silent_updates.json"
    if not silent_updates_path.exists():
        return []

    try:
        with open(silent_updates_path) as f:
            data = json.load(f)
        return data.get("silent_updates", [])
    except Exception:
        return []


def count_silent_updates_between(silent_updates: list[str], start_time: Optional[str], end_time: Optional[str]) -> int:
    """
    Count silent updates that occurred between start_time and end_time.
    If start_time is None, count from beginning.
    If end_time is None, count until now.
    """
    count = 0
    for timestamp in silent_updates:
        # Parse timestamp
        try:
            ts = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        except Exception:
            continue

        # Check if within range
        after_start = True
        if start_time:
            try:
                start_dt = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
                after_start = ts > start_dt
            except Exception:
                pass

        before_end = True
        if end_time:
            try:
                end_dt = datetime.fromisoformat(end_time.replace("Z", "+00:00"))
                before_end = ts < end_dt
            except Exception:
                pass

        if after_start and before_end:
            count += 1

    return count


def load_all_receipts(anon_mapping: Optional[dict[str, str]] = None) -> list[dict]:
    """Load all receipts from output folders."""
    receipts = []

    for folder in OUTPUT_DIR.iterdir():
        if not folder.is_dir():
            continue

        latest_path = folder / "latest.json"
        if not latest_path.exists():
            continue

        try:
            with open(latest_path) as f:
                data = json.load(f)

            if data.get("data"):
                folder_name = folder.name
                # Apply anon mapping if provided
                if anon_mapping and folder_name in anon_mapping:
                    display_name = anon_mapping[folder_name]
                else:
                    display_name = folder_name

                receipt = {"nickname": display_name, "folder_name": folder_name, **data["data"]}
                # Load receipt_info for location
                receipt_info = load_receipt_info(folder)
                if receipt_info:
                    receipt["receipt_info"] = receipt_info
                # Load silent updates timestamps
                silent_updates = load_silent_updates(folder)
                receipt["silent_updates"] = silent_updates
                receipts.append(receipt)
        except Exception as e:
            print(f"Error reading {latest_path}: {e}")

    return receipts


def group_by_form_type(receipts: list[dict]) -> dict[str, list[dict]]:
    """Group receipts by form type."""
    groups = defaultdict(list)
    for receipt in receipts:
        groups[receipt.get("formType", "Unknown")].append(receipt)
    return dict(groups)


def print_table(form_type: str, receipts: list[dict], changed_nicknames: Optional[set[str]] = None, days_since_filing: bool = False, show_dates: bool = False) -> None:
    """Print a table for a specific form type."""
    # ANSI color codes
    RED = "\033[91m"
    RESET = "\033[0m"

    # Build timeline of all events and silent updates
    timeline = build_timeline(receipts)

    # Build headers: Nickname, Loc, [timeline columns]
    headers = ["Nickname", "Loc"]

    silent_occurrence_count = 0

    # Add columns for each timeline entry
    for item in timeline:
        typ = item[0]
        identifier = item[1]
        date = item[2]
        count = item[3]

        if typ == "event":
            # Create 'count' number of columns for this event code
            for i in range(count):
                if count == 1:
                    headers.append(identifier)
                else:
                    headers.append(f"{identifier}-{i + 1}")
        else:  # silent update
            # Create 'count' number of columns for this date
            for i in range(count):
                silent_occurrence_count += 1
                headers.append(f"S{silent_occurrence_count}")

    # Calculate column widths
    nickname_width = 15
    loc_width = 6
    col_width = 8  # Width for each timeline column (events and silent updates)

    # Calculate total number of columns (sum of all counts)
    total_timeline_cols = sum(item[3] for item in timeline)
    col_widths = [nickname_width, loc_width] + [col_width] * total_timeline_cols

    total_width = sum(col_widths)

    print()
    print("=" * total_width)
    form_name = receipts[0].get("formName", "") if receipts else ""
    print(f"  {form_type} - {form_name}")
    print("=" * total_width)

    # Table header
    header_line = "".join(h.ljust(w) for h, w in zip(headers, col_widths))
    print(header_line)
    print("-" * total_width)

    # Table rows
    for receipt in receipts:
        events = receipt.get("events", [])
        silent_updates = receipt.get("silent_updates", [])
        location = receipt.get("receipt_info", {}).get("location", "-") if receipt.get("receipt_info") else "-"

        # Find IAF timestamp for this receipt (if using days_since_filing)
        iaf_timestamp = None
        if days_since_filing:
            for event in events:
                if event.get("eventCode") == "IAF":
                    iaf_timestamp = event.get("eventTimestamp")
                    break

        # Create lookup maps for this receipt - group by code only
        event_timestamps_by_code: dict[str, list] = defaultdict(list)  # code -> list of timestamps
        for event in events:
            code = event.get("eventCode")
            timestamp = event.get("eventTimestamp")
            if code and timestamp:
                event_timestamps_by_code[code].append(timestamp)

        # Sort timestamps chronologically within each group
        for key in event_timestamps_by_code:
            event_timestamps_by_code[key].sort()

        # Group silent updates by date
        silent_timestamps_by_date = defaultdict(list)
        for silent_ts in silent_updates:
            date = get_date_from_timestamp(silent_ts)
            silent_timestamps_by_date[date].append(silent_ts)

        # Sort timestamps chronologically within each group
        for date in silent_timestamps_by_date:
            silent_timestamps_by_date[date].sort()

        # Build row
        row = [
            receipt["nickname"].ljust(col_widths[0]),
            location.ljust(col_widths[1]),
        ]

        # Track column index
        col_idx = 2

        # Add columns for each timeline entry
        for item in timeline:
            typ = item[0]
            identifier = item[1]
            date = item[2]
            count = item[3]

            if typ == "event":
                # Get events for this code from this receipt (sorted chronologically)
                receipt_events = event_timestamps_by_code.get(identifier, [])

                # Fill in columns (up to 'count' columns)
                for i in range(count):
                    if i < len(receipt_events):
                        if show_dates:
                            cell = get_short_date(receipt_events[i])
                        elif days_since_filing and iaf_timestamp:
                            cell = f"{get_days_between(iaf_timestamp, receipt_events[i])}d"
                        else:
                            cell = f"{get_days_since(receipt_events[i])}d"
                        row.append(cell.ljust(col_widths[col_idx]))
                    else:
                        row.append("·".ljust(col_widths[col_idx]))
                    col_idx += 1
            else:  # silent update
                # Get silent updates for this date from this receipt
                receipt_silent = silent_timestamps_by_date.get(date, [])

                # Fill in columns (up to 'count' columns)
                for i in range(count):
                    if i < len(receipt_silent):
                        if show_dates:
                            cell = get_short_date(receipt_silent[i])
                        elif days_since_filing and iaf_timestamp:
                            cell = f"{get_days_between(iaf_timestamp, receipt_silent[i])}d"
                        else:
                            cell = f"{get_days_since(receipt_silent[i])}d"
                        row.append(cell.ljust(col_widths[col_idx]))
                    else:
                        row.append("·".ljust(col_widths[col_idx]))
                    col_idx += 1

        row_str = "".join(row)

        # Highlight changed rows in red
        # Use folder_name if available (for anon mode), otherwise nickname
        identifier = receipt.get("folder_name", receipt["nickname"])
        if changed_nicknames and identifier in changed_nicknames:
            print(f"{RED}{row_str}{RESET}")
        else:
            print(row_str)


def print_summary(changed_nicknames: Optional[set[str]] = None, anon: bool = False, days_since_filing: bool = False, show_dates: bool = False) -> None:
    """Print the summary tables, optionally highlighting changed nicknames."""
    print("\nUSCIS Receipt Summary")
    print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # Load anon mapping if requested
    anon_mapping = load_anon_mapping() if anon else None

    receipts = load_all_receipts(anon_mapping)
    grouped = group_by_form_type(receipts)

    # Fixed ordering
    form_order = ["I-131", "I-765", "I-485"]
    form_types = [f for f in form_order if f in grouped]
    # Add any other form types not in the predefined order
    form_types.extend(f for f in sorted(grouped.keys()) if f not in form_order)

    for form_type in form_types:
        # Sort receipts by nickname within each group
        grouped[form_type].sort(key=lambda r: r["nickname"])
        print_table(form_type, grouped[form_type], changed_nicknames, days_since_filing, show_dates)

    print()


def main():
    parser = argparse.ArgumentParser(description="USCIS Receipt Summary")
    parser.add_argument("--anon", action="store_true", help="Use anonymized names from config")
    parser.add_argument("--days-since-filing", action="store_true", help="Show days since filing date (IAF) instead of days ago from today")
    parser.add_argument("--show-dates", action="store_true", help="Show dates (M/D) instead of days")
    args = parser.parse_args()

    print_summary(anon=args.anon, days_since_filing=args.days_since_filing, show_dates=args.show_dates)


if __name__ == "__main__":
    main()
