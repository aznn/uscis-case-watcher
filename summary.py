#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///

import json
from pathlib import Path
from datetime import datetime, timezone
from collections import defaultdict

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


def count_fta0_events(events: list) -> int:
    """Count the number of FTA0 events."""
    return sum(1 for e in events if e.get("eventCode") == "FTA0")


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


def print_table(form_type: str, receipts: list[dict], changed_nicknames: set[str] | None = None) -> None:
    """Print a table for a specific form type."""
    # ANSI color codes
    RED = "\033[91m"
    RESET = "\033[0m"

    print()
    print("=" * 79)
    form_name = receipts[0].get("formName", "") if receipts else ""
    print(f"  {form_type} - {form_name}")
    print("=" * 79)

    # Table header
    headers = ["Nickname", "FTA0-1", "FTA0-2", "FTA0-3", "FTA0-4", "Last Event", "Last Updated"]
    col_widths = [15, 8, 8, 8, 8, 16, 16]

    header_line = "".join(h.ljust(w) for h, w in zip(headers, col_widths))
    print(header_line)
    print("-" * 79)

    # Table rows
    for receipt in receipts:
        fta0_count = count_fta0_events(receipt.get("events", []))
        last_event = get_last_event_time(receipt.get("events", []))
        time_ago = get_time_ago(receipt.get("updatedAtTimestamp", ""))

        check = "[x]"
        empty = " · "

        row = [
            receipt["nickname"].ljust(col_widths[0]),
            (check if fta0_count >= 1 else empty).ljust(col_widths[1]),
            (check if fta0_count >= 2 else empty).ljust(col_widths[2]),
            (check if fta0_count >= 3 else empty).ljust(col_widths[3]),
            (check if fta0_count >= 4 else empty).ljust(col_widths[4]),
            last_event.ljust(col_widths[5]),
            time_ago.ljust(col_widths[6]),
        ]

        row_str = "".join(row)

        # Highlight changed rows in red
        if changed_nicknames and receipt["nickname"] in changed_nicknames:
            print(f"{RED}{row_str}{RESET}")
        else:
            print(row_str)


def print_summary(changed_nicknames: set[str] | None = None) -> None:
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
