"""Turn the raw exercise files into the dimension and fact tables.

Marts are not built here. data/marts/sql/*.sql defines them, and pipeline/marts.py
runs that SQL after these tables are written.
"""

from rules import (
    AGE_TO_UNKNOWN,
    CHANNEL_TO_UNKNOWN,
    CONTENT_TYPE_TO_UNKNOWN,
    DEVICE_TO_UNKNOWN,
    EVENT_TYPE_TO_UNKNOWN,
    STATUS_TO_UNKNOWN,
    duration_is_invalid,
    follower_count_is_invalid,
    price_is_invalid,
    runtime_is_invalid,
)


class BuildError(Exception):
    """The raw files broke a rule, so the model was not written."""


def blank(value):
    return value is None or str(value).strip() == ""


def flag(is_true):
    return "true" if is_true else "false"


def whole_number(value):
    number = float(value)
    if number == int(number):
        return str(int(number))
    return str(number)


def money(value):
    return f"{float(value):.2f}"


def governed(value, unknown_values):
    text = "" if value is None else str(value).strip()
    if text in unknown_values:
        return "unknown"
    return text


def dedupe_users(rows):
    """Keep the first row for each user_id. Identical copies are dropped.

    A second row that disagrees with the first stops the build. See
    data/quality/issues/01-duplicate-users.md.
    """
    kept = []
    seen = {}
    for row in rows:
        user_id = row["user_id"]
        previous = seen.get(user_id)
        if previous is None:
            seen[user_id] = row
            kept.append(row)
            continue
        changed = [column for column in row if row[column] != previous[column]]
        if changed:
            fields = ", ".join(changed)
            raise BuildError(
                f"{user_id} is duplicated and the rows disagree on {fields}. "
                "data/quality/issues/01-duplicate-users.md says to stop and choose a winner."
            )
    return kept


def transform(raw):
    users = dedupe_users(raw["Exercise_users.csv"])
    dim_user = [_dim_user_row(row) for row in users]
    test_ids = {row["user_id"] for row in dim_user if row["is_test_account"] == "true"}

    dim_business = [_dim_business_row(row) for row in raw["Exercise_Businesses.csv"]]
    dim_creator = [_dim_creator_row(row) for row in raw["Exercise_creators.csv"]]
    dim_content = [_dim_content_row(row) for row in raw["Exercise_content_items.csv"]]
    fct_subscription = [
        _subscription_row(row, test_ids) for row in raw["Exercise_subscriptions.csv"]
    ]
    fct_engagement_event = [
        _event_row(row, test_ids) for row in raw["Exercise_engagement_events.csv"]
    ]

    model = {
        "dim_business": _sort(dim_business, "business_id"),
        "dim_user": _sort(dim_user, "user_id"),
        "dim_creator": _sort(dim_creator, "creator_id"),
        "dim_content": _sort(dim_content, "content_id"),
        "fct_subscription": _sort(fct_subscription, "subscription_id"),
        "fct_engagement_event": _sort(fct_engagement_event, "event_id"),
    }
    return model


def _sort(rows, *keys):
    return sorted(rows, key=lambda row: tuple(row[key] for key in keys))


def _dim_business_row(row):
    return {
        "business_id": row["business_id"],
        "business_name": row["business_name"],
        "business_line": row["business_line"],
        "launch_date": row["launch_date"],
        "hq_planet": row["hq_planet"],
    }


def _dim_user_row(row):
    return {
        "user_id": row["user_id"],
        "user_name": row["user_name"],
        "email": row["email"],
        "signup_date": row["signup_date"],
        "country": row["country"],
        "age_band": governed(row["age_band"], AGE_TO_UNKNOWN),
        "age_band_raw": row["age_band"],
        "acquisition_channel": governed(row["acquisition_channel"], CHANNEL_TO_UNKNOWN),
        "acquisition_channel_raw": row["acquisition_channel"],
        "primary_device": governed(row["primary_device"], DEVICE_TO_UNKNOWN),
        "primary_device_raw": row["primary_device"],
        "is_test_account": flag(row["is_test_account_flag"] == "True"),
    }


def _dim_creator_row(row):
    invalid = follower_count_is_invalid(row["follower_count_fake"])
    return {
        "creator_id": row["creator_id"],
        "creator_name": row["creator_name"],
        "business_id": row["business_id"],
        "join_date": row["join_date"],
        "payout_tier": row["payout_tier"],
        "follower_count": "" if invalid else whole_number(row["follower_count_fake"]),
        "follower_count_raw": row["follower_count_fake"],
        "follower_count_is_invalid": flag(invalid),
    }


def _dim_content_row(row):
    invalid = runtime_is_invalid(row["runtime_minutes_fake"])
    return {
        "content_id": row["content_id"],
        "business_id": row["business_id"],
        "creator_id": "" if blank(row["creator_id"]) else row["creator_id"],
        "title": row["title"],
        "category": row["category"],
        "content_type": governed(row["content_type"], CONTENT_TYPE_TO_UNKNOWN),
        "content_type_raw": row["content_type"],
        "publish_date": row["publish_date"],
        "runtime_minutes": "" if invalid else whole_number(row["runtime_minutes_fake"]),
        "runtime_minutes_raw": row["runtime_minutes_fake"],
        "runtime_minutes_is_invalid": flag(invalid),
    }


def _subscription_row(row, test_ids):
    invalid = price_is_invalid(row["monthly_price_usd"])
    return {
        "subscription_id": row["subscription_id"],
        "user_id": row["user_id"],
        "business_id": row["business_id"],
        "plan_tier": row["plan_tier"],
        "billing_cycle": "not_applicable" if blank(row["billing_cycle"]) else row["billing_cycle"],
        "billing_cycle_raw": row["billing_cycle"],
        "monthly_price_usd": "" if invalid else money(row["monthly_price_usd"]),
        "monthly_price_usd_raw": row["monthly_price_usd"],
        "monthly_price_is_invalid": flag(invalid),
        "start_date": row["start_date"],
        "end_date": "" if blank(row["end_date"]) else row["end_date"],
        "status": governed(row["status"], STATUS_TO_UNKNOWN),
        "status_raw": row["status"],
        "is_test_account": flag(row["user_id"] in test_ids),
    }


def _event_row(row, test_ids):
    invalid = duration_is_invalid(row["session_duration_sec"])
    return {
        "event_id": row["event_id"],
        "user_id": row["user_id"],
        "content_id": "" if blank(row["content_id"]) else row["content_id"],
        "event_type": governed(row["event_type"], EVENT_TYPE_TO_UNKNOWN),
        "event_type_raw": row["event_type"],
        "event_timestamp": row["event_timestamp"],
        "device": governed(row["device"], DEVICE_TO_UNKNOWN),
        "device_raw": row["device"],
        "session_duration_sec": "" if invalid else whole_number(row["session_duration_sec"]),
        "session_duration_sec_raw": row["session_duration_sec"],
        "session_duration_is_invalid": flag(invalid),
        "is_test_account": flag(row["user_id"] in test_ids),
    }
