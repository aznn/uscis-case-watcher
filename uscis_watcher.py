#!/usr/bin/env python3
"""
USCIS Case Watcher
Logs into USCIS, fetches case details via API, and tracks changes over time.
Supports multiple accounts and cases.
"""

import argparse
import copy
import json
import time
from datetime import datetime
from typing import Optional
from pathlib import Path

from selenium import webdriver
from pyotp import TOTP
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from deepdiff import DeepDiff
from summary import print_summary

# File paths
SCRIPT_DIR = Path(__file__).parent
CONFIG_FILE = SCRIPT_DIR / "config.json"
OUTPUT_DIR = SCRIPT_DIR / "output"


def load_config() -> dict:
    """Load configuration from config.json"""
    if not CONFIG_FILE.exists():
        raise FileNotFoundError(f"Config file not found: {CONFIG_FILE}")

    with open(CONFIG_FILE, "r") as f:
        return json.load(f)


def humanize_time_ago(timestamp_str: str) -> str:
    """Convert an ISO timestamp to a human-readable 'X hours and Y minutes ago' format"""
    try:
        # Parse the timestamp
        if timestamp_str.endswith('Z'):
            timestamp_str = timestamp_str[:-1] + '+00:00'
        ts = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
        # Make it timezone-aware if it isn't
        if ts.tzinfo is None:
            from datetime import timezone
            ts = ts.replace(tzinfo=timezone.utc)
        now = datetime.now(ts.tzinfo)
        delta = now - ts

        total_seconds = int(delta.total_seconds())
        if total_seconds < 0:
            return "in the future"

        days = total_seconds // 86400
        hours = (total_seconds % 86400) // 3600
        minutes = (total_seconds % 3600) // 60

        parts = []
        if days > 0:
            parts.append(f"{days} day{'s' if days != 1 else ''}")
        if hours > 0:
            parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
        if minutes > 0 and days == 0:  # Only show minutes if less than a day
            parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")

        if not parts:
            return "just now"
        return " and ".join(parts[:2]) + " ago"
    except Exception:
        return timestamp_str


def slugify(text: str) -> str:
    """Convert text to a filesystem-safe slug"""
    # Replace spaces and special chars with hyphens, lowercase
    import re
    text = text.lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[-\s]+', '-', text)
    return text


def get_case_output_dir(nickname: str) -> Path:
    """Get the output directory for a specific case using nickname"""
    folder_name = slugify(nickname)
    case_dir = OUTPUT_DIR / folder_name
    case_dir.mkdir(parents=True, exist_ok=True)
    return case_dir


def save_latest(nickname: str, data: dict) -> Path:
    """Save the latest case data to latest.json"""
    case_dir = get_case_output_dir(nickname)
    latest_file = case_dir / "latest.json"
    with open(latest_file, "w") as f:
        json.dump(data, f, indent=2)
    return latest_file


def load_latest(nickname: str) -> Optional[dict]:
    """Load the previous case data from latest.json if it exists"""
    case_dir = get_case_output_dir(nickname)
    latest_file = case_dir / "latest.json"
    if not latest_file.exists():
        return None

    with open(latest_file, "r") as f:
        return json.load(f)


def save_receipt_info(nickname: str, data: dict) -> Path:
    """Save the receipt_info data to receipt_info.json"""
    case_dir = get_case_output_dir(nickname)
    receipt_info_file = case_dir / "receipt_info.json"
    with open(receipt_info_file, "w") as f:
        json.dump(data, f, indent=2)
    return receipt_info_file


def load_receipt_info(nickname: str) -> Optional[dict]:
    """Load the previous receipt_info data if it exists"""
    case_dir = get_case_output_dir(nickname)
    receipt_info_file = case_dir / "receipt_info.json"
    if not receipt_info_file.exists():
        return None

    with open(receipt_info_file, "r") as f:
        return json.load(f)




def format_diff(diff: dict, old_data: dict, new_data: dict) -> str:
    """Format a DeepDiff result into a readable markdown string"""
    lines = []

    if "values_changed" in diff:
        for path, change in diff["values_changed"].items():
            lines.append(f"- **{path}**")
            lines.append(f"  - Old: `{change['old_value']}`")
            lines.append(f"  - New: `{change['new_value']}`")

    if "dictionary_item_added" in diff:
        for path in diff["dictionary_item_added"]:
            lines.append(f"- **Added** {path}")

    if "dictionary_item_removed" in diff:
        for path in diff["dictionary_item_removed"]:
            lines.append(f"- **Removed** {path}")

    if "iterable_item_added" in diff:
        for path, value in diff["iterable_item_added"].items():
            lines.append(f"- **Added item** {path}: `{value}`")

    if "iterable_item_removed" in diff:
        for path, value in diff["iterable_item_removed"].items():
            lines.append(f"- **Removed item** {path}: `{value}`")

    return "\n".join(lines) if lines else "No specific changes detected"


def format_diff_console(diff: dict) -> str:
    """Format a DeepDiff result for console output"""
    lines = []

    if "values_changed" in diff:
        for path, change in diff["values_changed"].items():
            # Clean up the path for readability
            clean_path = path.replace("root['data']", "").replace("['", ".").replace("']", "").lstrip(".")
            lines.append(f"    {clean_path}:")
            lines.append(f"      - {change['old_value']}")
            lines.append(f"      + {change['new_value']}")

    if "dictionary_item_added" in diff:
        for path in diff["dictionary_item_added"]:
            clean_path = path.replace("root['data']", "").replace("['", ".").replace("']", "").lstrip(".")
            lines.append(f"    + Added: {clean_path}")

    if "dictionary_item_removed" in diff:
        for path in diff["dictionary_item_removed"]:
            clean_path = path.replace("root['data']", "").replace("['", ".").replace("']", "").lstrip(".")
            lines.append(f"    - Removed: {clean_path}")

    if "iterable_item_added" in diff:
        for path, value in diff["iterable_item_added"].items():
            clean_path = path.replace("root['data']", "").replace("['", ".").replace("']", "").lstrip(".")
            lines.append(f"    + New item in {clean_path}")

    if "iterable_item_removed" in diff:
        for path, value in diff["iterable_item_removed"].items():
            clean_path = path.replace("root['data']", "").replace("['", ".").replace("']", "").lstrip(".")
            lines.append(f"    - Removed item from {clean_path}")

    return "\n".join(lines) if lines else "    (details unavailable)"


def append_changelog(nickname: str, case_number: str, diff: dict, old_data: dict, new_data: dict) -> Path:
    """Append a change entry to the changelog markdown file"""
    case_dir = get_case_output_dir(nickname)
    changelog_file = case_dir / "changelog.md"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Create header if file doesn't exist
    if not changelog_file.exists():
        with open(changelog_file, "w") as f:
            f.write(f"# USCIS Case Changelog: {nickname}\n\n")
            f.write(f"**Case Number:** {case_number}\n\n")
            f.write("This file tracks all changes detected in your USCIS case.\n\n")
            f.write("---\n\n")

    # Append the change entry
    with open(changelog_file, "a") as f:
        f.write(f"## {timestamp}\n\n")
        f.write(format_diff(diff, old_data, new_data))
        f.write("\n\n---\n\n")

    return changelog_file


def create_initial_changelog(nickname: str, case_number: str, data: dict = None) -> Path:
    """Create initial changelog entry for first run"""
    case_dir = get_case_output_dir(nickname)
    changelog_file = case_dir / "changelog.md"

    with open(changelog_file, "w") as f:
        f.write(f"# USCIS Case Changelog: {nickname}\n\n")
        f.write(f"**Case Number:** {case_number}\n\n")
        f.write("This file tracks all changes detected in your USCIS case.\n\n")
        f.write("---\n\n")
        f.write(f"## {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - Initial fetch\n\n")
        f.write("First case data recorded.\n\n")

        # Add initial state details if data is provided
        if data and "data" in data:
            inner = data["data"]

            # Last updated
            updated_at = inner.get("updatedAtTimestamp")
            if updated_at:
                time_ago = humanize_time_ago(updated_at)
                f.write(f"**Last Updated:** {updated_at} ({time_ago})\n\n")

            # Events summary
            events = inner.get("events", [])
            if events:
                f.write(f"**Events ({len(events)}):**\n")
                for event in events:
                    event_code = event.get("eventCode", "Unknown")
                    event_time = event.get("createdAtTimestamp", "")
                    time_ago = humanize_time_ago(event_time) if event_time else ""
                    f.write(f"- `{event_code}` - {event_time} ({time_ago})\n")
                f.write("\n")

            # Notices summary
            notices = inner.get("notices", [])
            if notices:
                f.write(f"**Notices ({len(notices)}):**\n")
                for notice in notices:
                    action_type = notice.get("actionType", "Unknown")
                    gen_date = notice.get("generationDate", "")
                    time_ago = humanize_time_ago(gen_date) if gen_date else ""
                    f.write(f"- {action_type} - {gen_date} ({time_ago})\n")
                f.write("\n")

        f.write("---\n\n")

    return changelog_file


def detect_important_changes(old_data: dict, new_data: dict) -> list[str]:
    """Detect important changes and return human-readable descriptions"""
    messages = []

    old_inner = old_data.get("data", {})
    new_inner = new_data.get("data", {})

    # Check for updatedAt change
    old_updated = old_inner.get("updatedAtTimestamp")
    new_updated = new_inner.get("updatedAtTimestamp")
    if old_updated != new_updated and new_updated:
        time_ago = humanize_time_ago(new_updated)
        messages.append(f"Case updated {time_ago}")

    # Check for new events
    old_events = {e.get("eventId"): e for e in old_inner.get("events", [])}
    new_events = new_inner.get("events", [])
    for event in new_events:
        event_id = event.get("eventId")
        if event_id and event_id not in old_events:
            event_code = event.get("eventCode", "Unknown")
            event_time = event.get("createdAtTimestamp", "")
            time_ago = humanize_time_ago(event_time) if event_time else ""
            messages.append(f"New '{event_code}' event added {time_ago}")

    # Check for new notices
    old_notices = {n.get("letterId"): n for n in old_inner.get("notices", [])}
    new_notices = new_inner.get("notices", [])
    for notice in new_notices:
        letter_id = notice.get("letterId")
        if letter_id and letter_id not in old_notices:
            action_type = notice.get("actionType", "Unknown")
            gen_date = notice.get("generationDate", "")
            time_ago = humanize_time_ago(gen_date) if gen_date else ""
            messages.append(f"New notice: '{action_type}' {time_ago}")

    return messages


def print_change_alert(nickname: str, case_number: str, diff: dict, old_data: dict = None, new_data: dict = None):
    """Print a prominent alert when changes are detected"""
    print("\n" + "!" * 60)
    print("!" * 60)
    print(f"!!!  CHANGE DETECTED: {nickname}")
    print(f"!!!  Case: {case_number}")
    print("!" * 60)

    # Show human-readable important changes if we have the data
    if old_data and new_data:
        important = detect_important_changes(old_data, new_data)
        if important:
            print("\n  Summary:")
            for msg in important:
                print(f"    -> {msg}")

    print("\n  Details:")
    print(format_diff_console(diff))
    print("\n" + "!" * 60)
    print("!" * 60 + "\n")


class USCISWatcher:
    def __init__(self, account: dict, browser_config: dict, verbose: bool = False):
        self.username = account["username"]
        self.password = account["password"]
        self.totp_secret = account["totp_secret"]
        self.account_name = account.get("name", "default")
        self.cases = account["cases"]
        self.browser_config = browser_config
        self.driver = None
        self.verbose = verbose

    def log(self, message: str):
        """Print message only in verbose mode"""
        if self.verbose:
            print(f">>> [{self.account_name}] {message}")

    def _setup_driver(self):
        """Initialize the Chrome driver"""
        options = Options()

        if self.browser_config.get("headless", False):
            options.add_argument("--headless=new")

        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--window-size=1400,900")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)

        # Selenium Manager handles Chrome/chromedriver automatically
        self.driver = webdriver.Chrome(options=options)
        self.driver.implicitly_wait(10)

    def login(self) -> None:
        """Log into USCIS account"""
        if not self.driver:
            self._setup_driver()

        self.log("Navigating to login page...")
        self.driver.get("https://myaccount.uscis.gov/sign-in")

        # Wait for the page to load and find login elements
        wait = WebDriverWait(self.driver, 30)

        self.log("Entering credentials...")
        email_field = wait.until(
            EC.presence_of_element_located((By.ID, "email-address"))
        )
        email_field.send_keys(self.username)

        password_field = self.driver.find_element(By.ID, "password")
        password_field.send_keys(self.password)

        self.log("Signing in...")
        sign_in_button = wait.until(
            EC.element_to_be_clickable((By.ID, "sign-in-btn"))
        )
        sign_in_button.click()

        # Wait for OTP page
        self.log("Entering OTP...")
        otp_field = wait.until(
            EC.presence_of_element_located((By.ID, "secure-verification-code"))
        )

        otp_code = TOTP(self.totp_secret).now()
        otp_field.send_keys(otp_code)

        # Submit OTP
        submit_button = wait.until(
            EC.element_to_be_clickable((By.ID, "2fa-submit-btn"))
        )
        submit_button.click()

        self.log("Waiting for login to complete...")
        # Wait for dashboard to load
        wait.until(EC.url_contains("dashboard"))

        self.log("Login successful!")

    def fetch_case_details(self, case_number: str) -> dict:
        """Fetch case details from the USCIS API"""
        if not self.driver:
            self.login()

        api_url = f"https://my.uscis.gov/account/case-service/api/cases/{case_number}"

        # Execute the fetch and wait for response using execute_async_script
        result = self.driver.execute_async_script(f"""
            var callback = arguments[arguments.length - 1];
            fetch('{api_url}', {{
                method: 'GET',
                credentials: 'include'
            }})
            .then(response => {{
                return response.text().then(text => ({{
                    status: response.status,
                    statusText: response.statusText,
                    body: text
                }}));
            }})
            .then(data => callback(JSON.stringify(data)))
            .catch(error => callback(JSON.stringify({{"error": error.message}})));
        """)

        if result:
            response_data = json.loads(result)
            if "error" in response_data:
                print(f"  ERROR [{case_number}]: {response_data['error']}")
                raise Exception(f"Fetch error: {response_data['error']}")
            if response_data.get("status") != 200:
                print(f"  ERROR [{case_number}]: Status {response_data.get('status')}")
                raise Exception(f"API returned status {response_data.get('status')}")
            # Parse the body as JSON
            return json.loads(response_data["body"])
        else:
            print(f"  ERROR [{case_number}]: No response received")
            raise Exception(f"Failed to fetch case details for {case_number}")

    def fetch_receipt_info(self, case_number: str) -> dict:
        """Fetch receipt info from the USCIS secure-messaging API"""
        if not self.driver:
            self.login()

        api_url = f"https://my.uscis.gov/secure-messaging/api/case-service/receipt_info/{case_number}"

        # Execute the fetch and wait for response using execute_async_script
        result = self.driver.execute_async_script(f"""
            var callback = arguments[arguments.length - 1];
            fetch('{api_url}', {{
                method: 'GET',
                credentials: 'include'
            }})
            .then(response => {{
                return response.text().then(text => ({{
                    status: response.status,
                    statusText: response.statusText,
                    body: text
                }}));
            }})
            .then(data => callback(JSON.stringify(data)))
            .catch(error => callback(JSON.stringify({{"error": error.message}})));
        """)

        if result:
            response_data = json.loads(result)
            if "error" in response_data:
                self.log(f"Receipt info error [{case_number}]: {response_data['error']}")
                return {"data": None, "error": response_data['error']}
            if response_data.get("status") != 200:
                self.log(f"Receipt info status [{case_number}]: {response_data.get('status')}")
                return {"data": None, "error": f"Status {response_data.get('status')}"}
            # Parse the body as JSON
            return json.loads(response_data["body"])
        else:
            self.log(f"Receipt info no response [{case_number}]")
            return {"data": None, "error": "No response received"}

    def process_all_cases(self, dry_run: bool = False) -> tuple[int, set[str]]:
        """Process all cases for this account. Returns (number of changes, set of changed nicknames)."""
        self.login()

        # Navigate to my.uscis.gov first to establish session context
        self.log("Navigating to case portal...")
        self.driver.get("https://my.uscis.gov/account")
        time.sleep(3)

        changes_detected = 0
        changed_nicknames = set()

        for case in self.cases:
            case_number = case["case_number"]
            nickname = case["nickname"]

            try:
                # Fetch case details
                new_data = self.fetch_case_details(case_number)

                # Load previous data for comparison
                old_data = load_latest(nickname)

                if old_data:
                    # Compare with previous data
                    diff = DeepDiff(old_data, new_data, ignore_order=True)

                    if diff:
                        changes_detected += 1
                        changed_nicknames.add(slugify(nickname))
                        print_change_alert(nickname, case_number, diff, old_data, new_data)
                        if not dry_run:
                            changelog_path = append_changelog(nickname, case_number, diff, old_data, new_data)
                            print(f"  Changelog updated: {changelog_path}")
                    else:
                        print(f"  {nickname}: No changes")
                else:
                    print(f"  {nickname}: First run - recording initial data")
                    changed_nicknames.add(slugify(nickname))
                    if not dry_run:
                        create_initial_changelog(nickname, case_number, new_data)

                # Save new data as latest
                if not dry_run:
                    save_latest(nickname, new_data)

                # Fetch and track receipt_info
                new_receipt_info = self.fetch_receipt_info(case_number)
                old_receipt_info = load_receipt_info(nickname)

                if old_receipt_info:
                    # Compare receipt_info data
                    receipt_diff = DeepDiff(old_receipt_info, new_receipt_info, ignore_order=True)
                    if receipt_diff:
                        # Extract location for summary
                        old_location = old_receipt_info.get("data", {}).get("receipt_details", {}).get("location") if old_receipt_info.get("data") else None
                        new_location = new_receipt_info.get("data", {}).get("receipt_details", {}).get("location") if new_receipt_info.get("data") else None
                        if old_location != new_location:
                            print(f"  {nickname}: Receipt info location changed: {old_location} -> {new_location}")
                        else:
                            print(f"  {nickname}: Receipt info changed")
                        changed_nicknames.add(slugify(nickname))
                else:
                    # First time fetching receipt_info
                    location = new_receipt_info.get("data", {}).get("receipt_details", {}).get("location") if new_receipt_info.get("data") else None
                    if location:
                        print(f"  {nickname}: Receipt info recorded (location: {location})")

                # Save receipt_info
                if not dry_run:
                    save_receipt_info(nickname, new_receipt_info)

            except Exception as e:
                print(f"  {nickname}: ERROR - {e}")

        return changes_detected, changed_nicknames

    def close(self):
        """Close the browser"""
        if self.driver:
            self.driver.quit()
            self.driver = None


def simulate_diff():
    """Simulate a diff by modifying the existing latest.json temporarily"""
    print("=" * 60)
    print("SIMULATION MODE - Testing diff detection")
    print("=" * 60)

    # Get first case from config
    config = load_config()
    accounts = config.get("accounts", [])
    if not accounts or not accounts[0].get("cases"):
        print("No cases configured. Add cases to config.json first.")
        return

    first_case = accounts[0]["cases"][0]
    nickname = first_case["nickname"]
    case_number = first_case["case_number"]

    # Find the output directory using nickname
    case_dir = get_case_output_dir(nickname)
    latest_file = case_dir / "latest.json"

    if not latest_file.exists():
        print(f"No latest.json found for {nickname}. Run the watcher first to get initial data.")
        return

    # Load current data
    with open(latest_file, "r") as f:
        current_data = json.load(f)

    # Create simulated "new" data with changes
    simulated_new = copy.deepcopy(current_data)

    # Simulate some realistic changes
    if "data" in simulated_new:
        data = simulated_new["data"]

        # Change 1: Update the status date
        data["updatedAt"] = "2025-12-30"
        data["updatedAtTimestamp"] = "2025-12-30T15:30:00.000Z"

        # Change 2: Add a new event
        new_event = {
            "receiptNumber": case_number,
            "eventId": "simulated-event-001",
            "eventCode": "APPR",
            "createdAt": "2025-12-30",
            "createdAtTimestamp": "2025-12-30T15:30:00.000Z",
            "updatedAt": "2025-12-30",
            "updatedAtTimestamp": "2025-12-30T15:30:00.000Z",
            "eventDateTime": "2025-12-30",
            "eventTimestamp": "2025-12-30T15:30:00.000Z"
        }
        if "events" in data:
            data["events"].insert(0, new_event)

        # Change 3: Add a new notice
        new_notice = {
            "receiptNumber": case_number,
            "letterId": "999999999",
            "generationDate": "2025-12-30T15:30:00.000Z",
            "actionType": "Case Approved"
        }
        if "notices" in data:
            data["notices"].insert(0, new_notice)

    # Compare
    diff = DeepDiff(current_data, simulated_new, ignore_order=True)

    print(f"\nSimulating changes for: {nickname} ({case_number})")
    print("-" * 60)

    if diff:
        print_change_alert(nickname, case_number, diff, current_data, simulated_new)

        # Show what would be written to changelog
        print("\nChangelog entry that would be written:")
        print("-" * 40)
        print(format_diff(diff, current_data, simulated_new))
        print("-" * 40)
    else:
        print("No diff detected (this shouldn't happen in simulation)")

    print("\n" + "=" * 60)
    print("SIMULATION COMPLETE - No actual changes were saved")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="USCIS Case Watcher")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")
    parser.add_argument("--simulate", action="store_true", help="Simulate a diff to test change detection")
    parser.add_argument("--dry-run", action="store_true", help="Check for changes without saving")
    args = parser.parse_args()

    if args.simulate:
        simulate_diff()
        return

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"USCIS Watcher - {timestamp}")

    # Load config
    try:
        config = load_config()
    except FileNotFoundError as e:
        print(f"Error: {e}")
        print("Please create a config.json file with your USCIS credentials.")
        return

    browser_config = config.get("browser", {})
    accounts = config.get("accounts", [])

    if not accounts:
        print("Error: No accounts configured in config.json")
        return

    total_changes = 0
    all_changed_nicknames = set()

    # Process each account
    for account in accounts:
        account_name = account.get("name", "default")
        print(f"\nAccount: {account_name}")
        print("-" * 40)

        watcher = USCISWatcher(account, browser_config, verbose=args.verbose)

        try:
            changes, changed_nicknames = watcher.process_all_cases(dry_run=args.dry_run)
            total_changes += changes
            all_changed_nicknames.update(changed_nicknames)
        except Exception as e:
            print(f"Error processing account {account_name}: {e}")
            raise
        finally:
            watcher.close()

    # Summary
    print("\n" + "=" * 40)
    if total_changes > 0:
        print(f"!!! {total_changes} CHANGE(S) DETECTED !!!")
    else:
        print("All cases checked - no changes")
    print("=" * 40)

    # Print the summary table
    print_summary(all_changed_nicknames if all_changed_nicknames else None)


if __name__ == "__main__":
    main()
