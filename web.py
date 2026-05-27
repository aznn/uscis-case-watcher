"""
USCIS Case Watcher — Web UI
Read-only Flask dashboard for viewing case timelines and change history.
"""

import json
from pathlib import Path

from flask import Flask, render_template, jsonify

import db as historydb
from summary import (
    load_all_receipts,
    load_silent_updates,
    group_by_form_type,
    build_timeline,
    get_event_occurrences,
    get_days_since,
    get_time_ago,
    get_short_date,
    get_date_label,
    slugify,
    OUTPUT_DIR,
)

app = Flask(__name__)

FORM_ORDER = ["I-131", "I-765", "I-485"]


def get_db():
    return historydb.get_db()


def load_case_config() -> dict[str, dict]:
    """Load per-case config flags keyed by folder slug. Returns empty dict if config.json absent."""
    config_path = Path("config.json")
    if not config_path.exists():
        return {}
    with open(config_path) as f:
        config = json.load(f)
    result = {}
    for account in config.get("accounts", []):
        for case in account.get("cases", []):
            result[slugify(case["nickname"])] = case
    return result


def get_current_case_data(nickname_slug: str) -> dict | None:
    """Load current case data from latest.json for a given slug."""
    folder = OUTPUT_DIR / nickname_slug
    latest_path = folder / "latest.json"
    if not latest_path.exists():
        return None
    with open(latest_path) as f:
        data = json.load(f)
    return data.get("data")


def get_last_run(nickname_slug: str) -> str | None:
    """Load last_run_at timestamp from last_run.json, or None if not found."""
    path = OUTPUT_DIR / nickname_slug / "last_run.json"
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f).get("last_run_at")


@app.route("/")
def dashboard():
    receipts = load_all_receipts()
    case_config = load_case_config()

    for receipt in receipts:
        slug = receipt.get("folder_name", slugify(receipt["nickname"]))
        receipt["last_run_at"] = get_last_run(slug)

    def is_archived(receipt):
        slug = receipt.get("folder_name", slugify(receipt["nickname"]))
        return case_config.get(slug, {}).get("archived", False)

    active_receipts = [r for r in receipts if not is_archived(r)]
    archived_receipts = [r for r in receipts if is_archived(r)]

    grouped = group_by_form_type(active_receipts)
    form_types = [f for f in FORM_ORDER if f in grouped]
    form_types.extend(f for f in sorted(grouped.keys()) if f not in FORM_ORDER)
    for form_type in form_types:
        grouped[form_type].sort(key=lambda r: r["nickname"])

    archived_grouped = group_by_form_type(archived_receipts)
    archived_form_types = [f for f in FORM_ORDER if f in archived_grouped]
    archived_form_types.extend(f for f in sorted(archived_grouped.keys()) if f not in FORM_ORDER)
    for form_type in archived_form_types:
        archived_grouped[form_type].sort(key=lambda r: r["nickname"])

    timeline = build_timeline(active_receipts)
    archived_timeline = build_timeline(archived_receipts)

    return render_template(
        "dashboard.html",
        grouped=grouped,
        form_types=form_types,
        timeline=timeline,
        receipts=active_receipts,
        archived_grouped=archived_grouped,
        archived_form_types=archived_form_types,
        archived_timeline=archived_timeline,
        archived_receipts=archived_receipts,
        get_event_occurrences=get_event_occurrences,
        get_days_since=get_days_since,
        get_time_ago=get_time_ago,
        get_short_date=get_short_date,
        get_date_label=get_date_label,
        slugify=slugify,
    )


@app.route("/case/<nickname>")
def case_detail(nickname: str):
    case_data = get_current_case_data(nickname)
    if not case_data:
        return "Case not found", 404

    conn = get_db()
    changes = historydb.get_changes(conn, nickname=nickname, limit=200)
    timeline_entries = historydb.get_timeline(conn, nickname=nickname)
    conn.close()

    folder = OUTPUT_DIR / nickname
    file_silent_updates = load_silent_updates(folder)
    if file_silent_updates:
        db_timestamps = {c["detected_at"] for c in changes if c["is_silent"]}
        for ts in file_silent_updates:
            if ts not in db_timestamps:
                changes.append({
                    "id": None,
                    "nickname": nickname,
                    "case_number": "",
                    "source_key": "silent",
                    "detected_at": ts,
                    "is_silent": 1,
                    "diff_json": None,
                    "summary": "Silent update",
                })
        changes.sort(key=lambda c: c["detected_at"], reverse=True)

    return render_template(
        "case_detail.html",
        nickname=nickname,
        case_data=case_data,
        changes=changes,
        timeline_entries=timeline_entries,
        last_run=get_last_run(nickname),
        get_time_ago=get_time_ago,
        get_days_since=get_days_since,
        json=json,
    )


@app.route("/api/cases")
def api_cases():
    receipts = load_all_receipts()
    # Strip non-serializable fields
    return jsonify(receipts)


@app.route("/api/cases/<nickname>/changes")
def api_case_changes(nickname: str):
    conn = get_db()
    changes = historydb.get_changes(conn, nickname=nickname, limit=500)
    conn.close()
    return jsonify(changes)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=False)
