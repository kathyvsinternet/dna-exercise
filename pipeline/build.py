"""Build the model tables from data/raw.

Run from the repository root:

    python pipeline/build.py

The command rewrites data/quality/profile.json from the raw files, applies the
treatments in data/quality/issues/, replaces the CSVs in data/model/, and
refreshes site/data/catalog.json. If a check fails, the model CSVs and the
site catalog are left unchanged.
"""

import csv
import json
import sys
from collections import Counter
from pathlib import Path

PIPELINE_DIR = Path(__file__).resolve().parent
if str(PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(PIPELINE_DIR))

from build_site import write_catalog
from checks import check
from transform import BuildError, transform

ROOT = PIPELINE_DIR.parent
RAW_DIR = ROOT / "data" / "raw"
QUALITY_DIR = ROOT / "data" / "quality"
MODEL_DIR = ROOT / "data" / "model"
MARTS_DIR = MODEL_DIR / "marts"

RAW_FILES = [
    "Exercise_Businesses.csv",
    "Exercise_users.csv",
    "Exercise_creators.csv",
    "Exercise_content_items.csv",
    "Exercise_subscriptions.csv",
    "Exercise_engagement_events.csv",
]

# Names and titles are identifiers. Keep their census counts, not the values.
OMIT_VALUE_LISTS = {"email", "user_name", "creator_name", "title"}

MODEL_FILES = {
    "dim_business": [
        "business_id",
        "business_name",
        "business_line",
        "launch_date",
        "hq_planet",
    ],
    "dim_user": [
        "user_id",
        "user_name",
        "email",
        "signup_date",
        "country",
        "age_band",
        "age_band_raw",
        "acquisition_channel",
        "acquisition_channel_raw",
        "primary_device",
        "primary_device_raw",
        "is_test_account",
    ],
    "dim_creator": [
        "creator_id",
        "creator_name",
        "business_id",
        "join_date",
        "payout_tier",
        "follower_count",
        "follower_count_raw",
        "follower_count_is_invalid",
    ],
    "dim_content": [
        "content_id",
        "business_id",
        "creator_id",
        "title",
        "category",
        "content_type",
        "content_type_raw",
        "publish_date",
        "runtime_minutes",
        "runtime_minutes_raw",
        "runtime_minutes_is_invalid",
    ],
    "fct_subscription": [
        "subscription_id",
        "user_id",
        "business_id",
        "plan_tier",
        "billing_cycle",
        "billing_cycle_raw",
        "monthly_price_usd",
        "monthly_price_usd_raw",
        "monthly_price_is_invalid",
        "start_date",
        "end_date",
        "status",
        "status_raw",
        "is_test_account",
    ],
    "fct_engagement_event": [
        "event_id",
        "user_id",
        "content_id",
        "event_type",
        "event_type_raw",
        "event_timestamp",
        "device",
        "device_raw",
        "session_duration_sec",
        "session_duration_sec_raw",
        "session_duration_is_invalid",
        "is_test_account",
    ],
}

MART_FILES = {
    "business_snapshot": [
        "business_id",
        "business_name",
        "business_line",
        "content_items",
        "unknown_type_content_items",
        "creators",
        "subscriptions",
        "active_subscriptions",
        "canceled_subscriptions",
        "paused_subscriptions",
        "trialing_subscriptions",
        "unknown_status_subscriptions",
        "subscribers",
        "active_monthly_price_usd",
        "engagement_events",
        "content_items_with_engagement",
    ],
    "subscription_mix": [
        "business_id",
        "plan_tier",
        "billing_cycle",
        "status",
        "subscriptions",
        "invalid_price_subscriptions",
        "monthly_price_usd_sum",
    ],
    "content_performance": [
        "content_id",
        "business_id",
        "title",
        "category",
        "content_type",
        "creator_id",
        "events",
        "content_opens",
        "content_completes",
        "likes",
        "shares",
        "comments",
        "downloads",
        "other_events",
        "events_with_valid_duration",
        "session_duration_sec_sum",
    ],
}


def main():
    raw = _read_raw()
    _write_profile(raw)
    try:
        model = transform(raw)
        check(raw, model)
    except BuildError as error:
        print(f"Build failed: {error}", file=sys.stderr)
        print("data/model was not changed.", file=sys.stderr)
        return 1
    _write_model(model)
    catalog = write_catalog(ROOT)
    print("Checks passed.")
    print(f"Wrote {QUALITY_DIR.relative_to(ROOT) / 'profile.json'}")
    print(f"Wrote {catalog.relative_to(ROOT)}")
    for name, rows in model.items():
        folder = "data/model/marts" if name in MART_FILES else "data/model"
        print(f"Wrote {folder}/{name}.csv ({len(rows)} rows)")
    return 0


def _read_raw():
    tables = {}
    for name in RAW_FILES:
        path = RAW_DIR / name
        with path.open(newline="") as handle:
            tables[name] = list(csv.DictReader(handle))
    return tables


def _write_profile(raw):
    profile = {
        "source": "data/raw",
        "note": "Census of the files as given. Treatments live in data/quality/issues. Empty means a blank cell.",
        "tables": {name: _profile_table(raw[name]) for name in RAW_FILES},
    }
    path = QUALITY_DIR / "profile.json"
    path.write_text(json.dumps(profile, indent=2) + "\n")


def _profile_table(rows):
    columns = {}
    if not rows:
        return {"rows": 0, "columns": columns}
    for column in rows[0]:
        values = [row[column] for row in rows]
        entry = {"empty": sum(1 for value in values if value.strip() == ""), "distinct": len(set(values))}
        if entry["distinct"] <= 20 and column not in OMIT_VALUE_LISTS:
            entry["values"] = dict(Counter(values))
        columns[column] = entry
    return {"rows": len(rows), "columns": columns}


def _write_model(model):
    MARTS_DIR.mkdir(parents=True, exist_ok=True)
    for name, fields in MODEL_FILES.items():
        _write_csv(MODEL_DIR / f"{name}.csv", model[name], fields)
    for name, fields in MART_FILES.items():
        _write_csv(MARTS_DIR / f"{name}.csv", model[name], fields)


def _write_csv(path, rows, fields):
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row[field] for field in fields})


if __name__ == "__main__":
    sys.exit(main())
