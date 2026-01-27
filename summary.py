#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///

import json
from pathlib import Path
from datetime import datetime, timezone
from collections import defaultdict
from typing import Optional

OUTPUT_DIR = Path(__file__).parent / "output"


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


def collect_dynamic_event_codes(receipts: list[dict]) -> list[str]:
    """Collect all unique event codes from all receipts, sorted by earliest occurrence.

    Returns a list of event codes in chronological order, excluding IAF which is handled separately.
    """
    # Collect all unique event codes
    event_codes = set()
    for receipt in receipts:
        events = receipt.get("events", [])
        for event in events:
            code = event.get("eventCode")
            if code and code != "IAF":  # Exclude IAF as it's fixed
                event_codes.add(code)

    # Sort by earliest timestamp
    event_codes_with_time = [
        (code, get_earliest_event_timestamp(receipts, code))
        for code in event_codes
    ]

    # Sort by timestamp
    event_codes_with_time.sort(key=lambda x: x[1])

    return [code for code, _ in event_codes_with_time]


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


def load_all_receipts() -> list[dict]:
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
                receipt = {"nickname": folder.name, **data["data"]}
                # Load receipt_info for location
                receipt_info = load_receipt_info(folder)
                if receipt_info:
                    receipt["receipt_info"] = receipt_info
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


def print_table(form_type: str, receipts: list[dict], changed_nicknames: Optional[set[str]] = None) -> None:
    """Print a table for a specific form type."""
    # ANSI color codes
    RED = "\033[91m"
    RESET = "\033[0m"

    # Collect dynamic event codes
    dynamic_event_codes = collect_dynamic_event_codes(receipts)

    # Build headers: Nickname, Loc, IAF, [dynamic event codes], Last Event, Last Updated
    headers = ["Nickname", "Loc", "IAF"] + dynamic_event_codes + ["Last Event", "Last Updated"]

    # Calculate column widths
    nickname_width = 15
    loc_width = 6
    iaf_width = 6
    event_col_width = 6  # Width for each event column
    last_event_width = 16
    last_updated_width = 16

    col_widths = [nickname_width, loc_width, iaf_width] + [event_col_width] * len(dynamic_event_codes) + [last_event_width, last_updated_width]

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
        last_event = get_last_event_time(events)
        time_ago = get_time_ago(receipt.get("updatedAtTimestamp", ""))
        location = receipt.get("receipt_info", {}).get("location", "-") if receipt.get("receipt_info") else "-"

        check = "[x]"
        empty = " · "

        # Build row
        row = [
            receipt["nickname"].ljust(col_widths[0]),
            location.ljust(col_widths[1]),
            (check if has_event_code(events, "IAF") else empty).ljust(col_widths[2]),
        ]

        # Add dynamic event columns
        for i, event_code in enumerate(dynamic_event_codes):
            col_idx = 3 + i
            has_event = has_event_code(events, event_code)
            row.append((check if has_event else empty).ljust(col_widths[col_idx]))

        # Add last event and last updated columns
        row.append(last_event.ljust(col_widths[-2]))
        row.append(time_ago.ljust(col_widths[-1]))

        row_str = "".join(row)

        # Highlight changed rows in red
        if changed_nicknames and receipt["nickname"] in changed_nicknames:
            print(f"{RED}{row_str}{RESET}")
        else:
            print(row_str)


def print_summary(changed_nicknames: Optional[set[str]] = None) -> None:
    """Print the summary tables, optionally highlighting changed nicknames."""
    print("\nUSCIS Receipt Summary")
    print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    receipts = load_all_receipts()
    grouped = group_by_form_type(receipts)

    # Fixed ordering
    form_order = ["I-131", "I-765", "I-485"]
    form_types = [f for f in form_order if f in grouped]
    # Add any other form types not in the predefined order
    form_types.extend(f for f in sorted(grouped.keys()) if f not in form_order)

    for form_type in form_types:
        # Sort receipts by nickname within each group
        grouped[form_type].sort(key=lambda r: r["nickname"])
        print_table(form_type, grouped[form_type], changed_nicknames)

    print()


def main():
    print_summary()


if __name__ == "__main__":
    main()
