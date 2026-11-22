"""Fail the build when a raw file or a model table breaks a published rule."""

from datetime import datetime

from rules import (
    AGE_BANDS,
    BILLING_CYCLES,
    BUSINESS_IDS,
    BUSINESS_LINES,
    BUSINESS_NAMES,
    CATEGORIES,
    CHANNELS,
    CONTENT_TYPES,
    COUNTRIES,
    DEVICES,
    EVENT_TYPES,
    EVENTS_WITH_CONTENT,
    EVENTS_WITHOUT_CONTENT,
    HQ_PLANETS,
    ISSUE_DUPLICATES,
    ISSUE_FOREIGN_KEYS,
    ISSUE_MEASURES,
    ISSUE_SENTINELS,
    ISSUE_SUBSCRIPTIONS,
    MAKERHARBOR_BUSINESS_ID,
    PAYOUT_TIERS,
    PLAN_TIERS,
    STATUSES,
    TEST_FLAGS,
    duration_is_invalid,
    follower_count_is_invalid,
    price_is_invalid,
    runtime_is_invalid,
)
from transform import BuildError, blank


def check(raw, model):
    _check_raw_tokens(raw)
    _check_keys(model)
    _check_classified_values(model)
    _check_measures(model)
    _check_subscriptions(model)
    _check_event_content_pattern(model)


USER_BREAKDOWN_MARTS = {
    "mart_user_share_country": "user_geo_country",
    "mart_user_share_age": "user_age_band",
    "mart_user_share_channel": "user_acq_channel",
    "mart_user_info_prim_device": "user_prim_device",
}


def check_dashboard_marts(model, marts):
    """Each mart the dashboard publishes must reconcile to the fact tables."""
    if "mart_user_qtr_counts" in marts:
        _check_quarterly_users(model, marts["mart_user_qtr_counts"])
    _check_user_breakdowns(model, marts)


def _check_user_breakdowns(model, marts):
    """Every user lands in exactly one row of each breakdown, so each one adds up to all active users."""
    active_users = {
        row["user_id"]
        for row in model["fct_subscription"]
        if row["is_test_account"] == "false" and row["status"] == "active"
    }
    for name, column in USER_BREAKDOWN_MARTS.items():
        if name not in marts:
            continue
        rows = marts[name]
        values = [row[column] for row in rows]
        if len(values) != len(set(values)):
            raise BuildError(f"{name} has a repeated {column}. See {ISSUE_DUPLICATES}.")
        got = sum(int(row["n_users"]) for row in rows)
        if got != len(active_users):
            raise BuildError(
                f"{name} adds up to {got} users, but {len(active_users)} non-test users hold an active "
                f"subscription. See {ISSUE_SENTINELS}."
            )
        share = sum(float(row["n_share"]) for row in rows)
        if abs(share - 1) > 0.005:
            raise BuildError(f"{name} shares add up to {share:.4f}, not 1. See {ISSUE_SENTINELS}.")


def _check_quarterly_users(model, rows):
    quarters = [row["quarter"] for row in rows]
    if len(quarters) != len(set(quarters)):
        raise BuildError(f"mart_user_qtr_counts has a repeated quarter. See {ISSUE_DUPLICATES}.")
    real_users = [row for row in model["dim_user"] if row["is_test_account"] == "false"]
    real_subs = [row for row in model["fct_subscription"] if row["is_test_account"] == "false"]
    expected = {
        "user_subscriptions": len(real_subs),
        "user_cancellations": sum(1 for row in real_subs if row["status"] == "canceled" and not blank(row["end_date"])),
    }
    for column, want in expected.items():
        got = sum(int(row[column]) for row in rows)
        if got != want:
            raise BuildError(
                f"mart_user_qtr_counts adds up to {got} {column}, but the fact tables have {want} "
                f"for non-test accounts. See {ISSUE_SENTINELS}."
            )


def _check_raw_tokens(raw):
    _expect(raw["Exercise_users.csv"], "is_test_account_flag", TEST_FLAGS, ISSUE_SENTINELS)
    _expect(raw["Exercise_Businesses.csv"], "business_id", BUSINESS_IDS, ISSUE_SENTINELS)
    _expect(raw["Exercise_Businesses.csv"], "business_name", BUSINESS_NAMES, ISSUE_SENTINELS)
    _expect(raw["Exercise_Businesses.csv"], "business_line", BUSINESS_LINES, ISSUE_SENTINELS)
    _expect(raw["Exercise_Businesses.csv"], "hq_planet", HQ_PLANETS, ISSUE_SENTINELS)


def _check_keys(model):
    _unique(model["dim_business"], "business_id")
    _unique(model["dim_user"], "user_id")
    _unique(model["dim_creator"], "creator_id")
    _unique(model["dim_content"], "content_id")
    _unique(model["fct_subscription"], "subscription_id")
    _unique(model["fct_engagement_event"], "event_id")

    businesses = {row["business_id"] for row in model["dim_business"]}
    users = {row["user_id"] for row in model["dim_user"]}
    creators = {row["creator_id"] for row in model["dim_creator"]}
    content = {row["content_id"] for row in model["dim_content"]}

    _foreign_key(model["dim_creator"], "business_id", businesses, "dim_business")
    _foreign_key(model["dim_content"], "business_id", businesses, "dim_business")
    _foreign_key(model["dim_content"], "creator_id", creators, "dim_creator", allow_blank=True)
    _foreign_key(model["fct_subscription"], "user_id", users, "dim_user")
    _foreign_key(model["fct_subscription"], "business_id", businesses, "dim_business")
    _foreign_key(model["fct_engagement_event"], "user_id", users, "dim_user")
    _foreign_key(model["fct_engagement_event"], "content_id", content, "dim_content", allow_blank=True)

    missing_creator = [
        row["content_id"]
        for row in model["dim_content"]
        if row["business_id"] == MAKERHARBOR_BUSINESS_ID and blank(row["creator_id"])
    ]
    if missing_creator:
        sample = ", ".join(missing_creator[:5])
        raise BuildError(
            f"MakerHarbor content is missing a creator ({sample}). See {ISSUE_FOREIGN_KEYS}."
        )


def _check_classified_values(model):
    _expect(model["dim_user"], "country", COUNTRIES, ISSUE_SENTINELS)
    _expect(model["dim_user"], "age_band", AGE_BANDS, ISSUE_SENTINELS)
    _expect(model["dim_user"], "acquisition_channel", CHANNELS, ISSUE_SENTINELS)
    _expect(model["dim_user"], "primary_device", DEVICES, ISSUE_SENTINELS)
    _expect(model["dim_user"], "is_test_account", {"true", "false"}, ISSUE_SENTINELS)
    _expect(model["dim_creator"], "payout_tier", PAYOUT_TIERS, ISSUE_SENTINELS)
    _expect(model["dim_content"], "category", CATEGORIES, ISSUE_SENTINELS)
    _expect(model["dim_content"], "content_type", CONTENT_TYPES, ISSUE_SENTINELS)
    _expect(model["fct_subscription"], "plan_tier", PLAN_TIERS, ISSUE_SENTINELS)
    _expect(model["fct_subscription"], "billing_cycle", BILLING_CYCLES, ISSUE_SUBSCRIPTIONS)
    _expect(model["fct_subscription"], "status", STATUSES, ISSUE_SENTINELS)
    _expect(model["fct_engagement_event"], "event_type", EVENT_TYPES, ISSUE_SENTINELS)
    _expect(model["fct_engagement_event"], "device", DEVICES, ISSUE_SENTINELS)

    planted = {
        "dim_user.age_band": {"", "N/A", "999"},
        "dim_user.acquisition_channel": {"", "carrier_pigeon", "influencer_TEST_CAMPAIGN"},
        "dim_user.primary_device": {"smart_toaster", "unknown_device"},
        "dim_content.content_type": {"TEST_TYPE"},
        "fct_subscription.status": {"TEST_STATUS_DO_NOT_USE"},
        "fct_engagement_event.event_type": {"glitch_in_the_matrix"},
    }
    tables = {name.split(".")[0] for name in planted}
    rows_by_table = {name: model[name] for name in tables}
    for qualified, blocked in planted.items():
        table, column = qualified.split(".")
        found = sorted({row[column] for row in rows_by_table[table] if row[column] in blocked})
        if found:
            raise BuildError(
                f"{qualified} still contains {found}. Map them to unknown. See {ISSUE_SENTINELS}."
            )


def _check_measures(model):
    for row in model["dim_content"]:
        if row["runtime_minutes"] != "" and runtime_is_invalid(row["runtime_minutes"]):
            raise BuildError(
                f"{row['content_id']} has governed runtime {row['runtime_minutes']}. See {ISSUE_MEASURES}."
            )
        if (row["runtime_minutes"] == "") != (row["runtime_minutes_is_invalid"] == "true"):
            raise BuildError(f"{row['content_id']} runtime flag does not match the governed value.")
    for row in model["dim_creator"]:
        if row["follower_count"] != "" and follower_count_is_invalid(row["follower_count"]):
            raise BuildError(
                f"{row['creator_id']} has governed follower count {row['follower_count']}. See {ISSUE_MEASURES}."
            )
        if (row["follower_count"] == "") != (row["follower_count_is_invalid"] == "true"):
            raise BuildError(f"{row['creator_id']} follower flag does not match the governed value.")
    for row in model["fct_subscription"]:
        if row["monthly_price_usd"] != "" and price_is_invalid(row["monthly_price_usd"]):
            raise BuildError(
                f"{row['subscription_id']} has governed price {row['monthly_price_usd']}. See {ISSUE_MEASURES}."
            )
        if (row["monthly_price_usd"] == "") != (row["monthly_price_is_invalid"] == "true"):
            raise BuildError(f"{row['subscription_id']} price flag does not match the governed value.")
    for row in model["fct_engagement_event"]:
        if row["session_duration_sec"] != "" and duration_is_invalid(row["session_duration_sec"]):
            raise BuildError(
                f"{row['event_id']} has governed duration {row['session_duration_sec']}. See {ISSUE_MEASURES}."
            )
        if (row["session_duration_sec"] == "") != (row["session_duration_is_invalid"] == "true"):
            raise BuildError(f"{row['event_id']} duration flag does not match the governed value.")


def _check_subscriptions(model):
    for row in model["fct_subscription"]:
        price = float(row["monthly_price_usd_raw"])
        if row["plan_tier"] == "Free":
            if row["billing_cycle"] != "not_applicable" or not blank(row["billing_cycle_raw"]) or price != 0:
                raise BuildError(
                    f"{row['subscription_id']} is Free but billing cycle or price is unexpected. "
                    f"See {ISSUE_SUBSCRIPTIONS}."
                )
        elif blank(row["billing_cycle_raw"]) or price == 0:
            raise BuildError(
                f"{row['subscription_id']} is a paid plan with a blank billing cycle or a zero price. "
                f"See {ISSUE_SUBSCRIPTIONS}."
            )
        if row["status_raw"] == "canceled" and blank(row["end_date"]):
            raise BuildError(
                f"{row['subscription_id']} is canceled and has no end date. See {ISSUE_SUBSCRIPTIONS}."
            )
        if not blank(row["end_date"]):
            start = datetime.fromisoformat(row["start_date"])
            end = datetime.fromisoformat(row["end_date"])
            if end < start:
                raise BuildError(
                    f"{row['subscription_id']} ends on {row['end_date']} before it starts. "
                    f"See {ISSUE_SUBSCRIPTIONS}."
                )


def _check_event_content_pattern(model):
    for row in model["fct_engagement_event"]:
        has_content = not blank(row["content_id"])
        event_type = row["event_type_raw"]
        if event_type in EVENTS_WITHOUT_CONTENT and has_content:
            raise BuildError(
                f"{row['event_id']} is a {event_type} and has content {row['content_id']}. "
                f"See {ISSUE_FOREIGN_KEYS}."
            )
        if event_type in EVENTS_WITH_CONTENT and not has_content:
            raise BuildError(
                f"{row['event_id']} is a {event_type} and has no content id. See {ISSUE_FOREIGN_KEYS}."
            )


def _unique(rows, column):
    seen = set()
    for row in rows:
        value = row[column]
        if value in seen:
            raise BuildError(f"Repeated {column} {value}. See {ISSUE_DUPLICATES}.")
        seen.add(value)


def _foreign_key(rows, column, parents, parent_name, allow_blank=False):
    missing = sorted(
        {
            row[column]
            for row in rows
            if not (allow_blank and blank(row[column])) and row[column] not in parents
        }
    )
    if missing:
        sample = ", ".join(missing[:5])
        raise BuildError(f"{column} values missing from {parent_name}: {sample}. See {ISSUE_FOREIGN_KEYS}.")


def _expect(rows, column, allowed, issue):
    found = sorted({row[column] for row in rows if row[column] not in allowed})
    if found:
        sample = ", ".join(found[:8])
        raise BuildError(
            f"Unclassified value in {column}: {sample}. Add it to pipeline/rules.py and record it in {issue}."
        )
