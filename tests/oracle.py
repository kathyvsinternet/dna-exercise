"""Golden answers recomputed from the model CSVs in data/model, without the marts.

Each function returns rows in the shape the executor returns them, so a golden
question's expected rows can be compared with them directly. The golden file holds
literal values. test_golden checks those literals against these functions, and the
executor's output against the literals. A wrong mart therefore fails the test even
if the literal was typed in by hand.

These functions use only the model tables and the rules written in
data/model/schema.yml and data/quality. They do not read the catalog or the marts.
"""

import csv
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / "data" / "model"
CONTENT_EVENT_TYPES = {"content_complete", "content_open", "download"}


def _read(name):
    with (MODEL / f"{name}.csv").open(newline="") as handle:
        return list(csv.DictReader(handle))


def _live_subscriptions():
    """Every non-test subscription, in any status."""
    return [row for row in _read("fct_subscription") if row["is_test_account"] == "false"]


def _active_subscriptions():
    return [row for row in _live_subscriptions() if row["status"] == "active"]


def _active_subscriptions_by_user():
    per_user = defaultdict(list)
    for sub in _active_subscriptions():
        per_user[sub["user_id"]].append(sub)
    return per_user


def _active_user_ids():
    return set(_active_subscriptions_by_user())


def _users():
    return {row["user_id"]: row for row in _read("dim_user")}


def headline():
    subs = _active_subscriptions()
    users = _active_user_ids()
    paid = [sub for sub in subs if sub["plan_tier"] != "Free"]
    total = sum(float(sub["monthly_price_usd"]) for sub in subs if sub["monthly_price_usd"] != "")
    return [
        {
            "n_users_active": len(users),
            "n_subs_active": len(subs),
            "n_subs_paid": len(paid),
            "total_monthly_payment": round(total, 2),
            "avg_monthly_payment": round(total / len(users), 2),
        }
    ]


def starts_in_year(year):
    count = sum(1 for sub in _live_subscriptions() if sub["start_date"].startswith(f"{year}-"))
    return [{"user_subscriptions": count}]


def cancellations_between(start, end):
    count = sum(
        1
        for sub in _live_subscriptions()
        if sub["status"] == "canceled" and sub["end_date"] and start <= sub["end_date"] <= end
    )
    return [{"user_cancellations": count}]


def net_subscriptions_at(day):
    """Non-test subscriptions started on or before day and not canceled by then, in any other status."""
    count = sum(
        1
        for sub in _live_subscriptions()
        if sub["start_date"] <= day and not (sub["status"] == "canceled" and sub["end_date"] <= day)
    )
    return [{"running_net_subscriptions": count}]


def churn_in_quarter(start, end):
    """Cancellations in the quarter over the subscriptions in place when it began. None when none were."""
    subs = _live_subscriptions()
    opening = sum(
        1
        for sub in subs
        if sub["start_date"] < start and not (sub["status"] == "canceled" and sub["end_date"] < start)
    )
    canceled = sum(
        1 for sub in subs if sub["status"] == "canceled" and start <= sub["end_date"] <= end
    )
    return [{"quarterly_churn_rate": round(canceled / opening, 4) if opening else None}]


def _content_event_counts():
    counts = Counter()
    for event in _read("fct_engagement_event"):
        if (
            event["is_test_account"] == "false"
            and event["event_type"] in CONTENT_EVENT_TYPES
            and event["content_id"]
        ):
            counts[event["content_id"]] += 1
    return counts


def top_content(n):
    content = {row["content_id"]: row for row in _read("dim_content")}
    titles = [row["title"] for row in content.values()]
    if len(titles) != len(set(titles)):
        raise AssertionError("Titles are not unique, so grouping by title would merge rows.")
    # Ties break by title, the group_by column, as the executor does.
    ranked = [(content[cid]["title"], count) for cid, count in _content_event_counts().items()]
    ranked.sort(key=lambda item: (-item[1], item[0]))
    return [{"title": title, "n_engagement_events": count} for title, count in ranked[:n]]


def category_totals(n):
    category = {row["content_id"]: row["category"] for row in _read("dim_content")}
    totals = Counter()
    for content_id, count in _content_event_counts().items():
        totals[category[content_id]] += count
    ranked = sorted(totals.items(), key=lambda item: (-item[1], item[0]))[:n]
    return [{"category": name, "n_engagement_events": count} for name, count in ranked]


def country_users(country):
    users = _users()
    count = sum(1 for user_id in _active_user_ids() if users[user_id]["country"] == country)
    return [{"user_geo_country": country, "n_users": count}]


def country_total():
    return [{"n_users": len(_active_user_ids())}]


def device_share(device):
    users = _users()
    active = _active_user_ids()
    count = sum(1 for user_id in active if users[user_id]["primary_device"] == device)
    return [{"user_prim_device": device, "n_users": count, "n_share": round(count / len(active), 4)}]


def age_band_users(band):
    users = _users()
    count = sum(1 for user_id in _active_user_ids() if users[user_id]["age_band"] == band)
    return [{"user_age_band": band, "n_users": count}]


def channel_users():
    users = _users()
    counts = Counter(users[user_id]["acquisition_channel"] for user_id in _active_user_ids())
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return [{"user_acq_channel": name, "n_users": count} for name, count in ranked]


def users_with_active_subscriptions(n):
    counts = Counter(len(subs) for subs in _active_subscriptions_by_user().values())
    return [{"n_subs_active": n, "n_users": counts[n]}]
