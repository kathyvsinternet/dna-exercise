"""Write site/data/catalog.json from the metric files and the subscription fact.

Called from pipeline/build.py after the model CSVs are written. The site reads
this file and does not calculate from user-level rows.
"""

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
METRICS = [
    "plans_active",
    "subscribers_active",
    "plans_paid_active",
    "plan_starts",
]
LINE_LABELS = {
    "premium_published_content": "Premium published content",
    "consumer_community": "Consumer community",
    "creator_content": "Creator content",
}
SHORT_NAMES = {
    "BIZ_1": "PageGarden",
    "BIZ_2": "GatherSquare",
    "BIZ_3": "MakerHarbor",
}


def write_catalog(root=ROOT):
    root = Path(root)
    businesses = _businesses(root)
    subscriptions = _read_csv(root / "data" / "model" / "fct_subscription.csv")
    metrics = []
    for name in METRICS:
        definition = _parse_yaml((root / "metrics" / f"{name}.yml").read_text())
        metrics.append(_metric(definition, subscriptions, businesses))
    catalog = {
        "source": "data/model/fct_subscription.csv",
        "businesses": businesses,
        "metrics": metrics,
        "refusals": _refusals(),
    }
    path = root / "site" / "data" / "catalog.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(catalog, indent=2) + "\n")
    return path


def _businesses(root):
    rows = _read_csv(root / "data" / "model" / "dim_business.csv")
    return [
        {
            "id": row["business_id"],
            "name": row["business_name"],
            "short": SHORT_NAMES.get(row["business_id"], row["business_name"]),
            "line": LINE_LABELS.get(row["business_line"], row["business_line"]),
            "planet": row["hq_planet"],
        }
        for row in rows
    ]


def _metric(definition, subscriptions, businesses):
    rows = [row for row in subscriptions if row["is_test_account"] == "false"]
    if definition["name"] == "plan_starts":
        start, end = _period(definition)
        rows = [row for row in rows if start <= row["start_date"] <= end]
        period = {"start": start, "end": end}
    else:
        period = None
        rows = [row for row in rows if row["status"] == "active"]
        if definition["name"] == "plans_paid_active":
            rows = [row for row in rows if row["plan_tier"] != "Free"]

    distinct = "count_distinct" in definition
    key = definition.get("count_distinct") or definition.get("count")
    record = {
        "name": definition["name"],
        "file": f"metrics/{definition['name']}.yml",
        "question": definition["question"],
        "source": definition["source"],
        "aggregation": f"count distinct {key}" if distinct else f"count of {key}",
        "filters": [_filter_label(item) for item in definition.get("filters", [])],
        "group_by": definition.get("group_by", []),
        "notes": definition.get("notes", []),
        "total": _measure(rows, key, distinct),
        "by_business": [
            {
                "id": business["id"],
                "short": business["short"],
                "value": _measure(
                    [row for row in rows if row["business_id"] == business["id"]],
                    key,
                    distinct,
                ),
            }
            for business in businesses
        ],
    }
    if definition["name"] in ("plans_active", "plans_paid_active"):
        record["by_plan_tier"] = _breakdown(rows, "plan_tier", key, distinct)
        record["by_billing_cycle"] = _breakdown(rows, "billing_cycle", key, distinct)
    if definition["name"] == "subscribers_active":
        record["business_totals_sum"] = sum(item["value"] for item in record["by_business"])
        people = {}
        for row in rows:
            people.setdefault(row["user_id"], set()).add(row["business_id"])
        record["people_in_more_than_one_business"] = sum(1 for houses in people.values() if len(houses) > 1)
    if period:
        record["period"] = period
        record["filters"] = [
            "is_test_account = false",
            f"start_date on or after {period['start']}",
            f"start_date on or before {period['end']}",
        ]
    return record


def _period(definition):
    known = definition.get("known_result") or {}
    return known.get("period_start", "2026-01-01"), known.get("period_end", "2026-09-30")


def _measure(rows, key, distinct):
    if distinct:
        return len({row[key] for row in rows})
    return len(rows)


def _breakdown(rows, column, key, distinct):
    values = sorted({row[column] for row in rows})
    return [
        {"label": value, "value": _measure([row for row in rows if row[column] == value], key, distinct)}
        for value in values
    ]


def _filter_label(item):
    column = item["column"]
    if "equals" in item:
        return f"{column} = {item['equals']}"
    if "not_equals" in item:
        return f"{column} ≠ {item['not_equals']}"
    if "on_or_after" in item:
        return f"{column} on or after {item['on_or_after']}"
    if "on_or_before" in item:
        return f"{column} on or before {item['on_or_before']}"
    return column


def _refusals():
    return [
        {
            "id": "revenue",
            "title": "Revenue is not a metric",
            "body": "The catalog has no revenue, ARR, or cash metric. active monthly price on the model mart is a list-price total, and it is not in metrics/.",
        },
        {
            "id": "completion",
            "title": "Completion rate is not a metric",
            "body": "Completes are not a subset of opens, so a completion rate is not defined. content_completes and content_opens are not in the catalog.",
        },
        {
            "id": "identity",
            "title": "User-level fields stay off this site",
            "body": "email, user_name, and age_band are restricted. This page only returns a metric from metrics/.",
        },
        {
            "id": "history",
            "title": "There is no point-in-time subscriber metric",
            "body": "status is the current value. A past date cannot be reconstructed from it. plan_starts counts subscriptions whose start_date falls in a period, which is a different question.",
        },
        {
            "id": "events",
            "title": "Subscription events are not plan counts",
            "body": "subscription_start and subscription_cancel are engagement events. Plan metrics are counted from fct_subscription.",
        },
        {
            "id": "period",
            "title": "That period is not in the catalog",
            "body": "plan_starts requires a period. The worked example on this site is 2026-01-01 through 2026-09-30.",
        },
        {
            "id": "unknown",
            "title": "That question is not in the catalog",
            "body": "The page can answer plans_active, subscribers_active, plans_paid_active, and plan_starts. It will not invent another metric.",
        },
    ]


def _read_csv(path):
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def _parse_yaml(text):
    lines = []
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        lines.append((len(raw) - len(raw.lstrip(" ")), raw.strip()))
    parsed, index = _parse_map(lines, 0, 0)
    if index != len(lines):
        raise ValueError(f"Could not parse metric YAML near {lines[index][1]}")
    return parsed


def _parse_map(lines, index, indent):
    result = {}
    while index < len(lines):
        level, text = lines[index]
        if level < indent or text.startswith("- "):
            break
        key, _, rest = text.partition(":")
        rest = rest.strip()
        index += 1
        if rest:
            result[key] = _scalar(rest)
            continue
        if index >= len(lines) or lines[index][0] <= level:
            result[key] = {}
            continue
        if lines[index][1].startswith("- "):
            child, index = _parse_list(lines, index, lines[index][0])
        else:
            child, index = _parse_map(lines, index, lines[index][0])
        result[key] = child
    return result, index


def _parse_list(lines, index, indent):
    items = []
    while index < len(lines):
        level, text = lines[index]
        if level < indent or not text.startswith("- "):
            break
        payload = text[2:].strip()
        index += 1
        if payload == "":
            child, index = _parse_map(lines, index, lines[index][0])
            items.append(child)
            continue
        if ":" in payload and not payload.startswith(("'", '"')):
            key, _, rest = payload.partition(":")
            item = {key: _scalar(rest.strip())} if rest.strip() else {key: {}}
            while index < len(lines) and lines[index][0] > level and not lines[index][1].startswith("- "):
                child_level, child_text = lines[index]
                child_key, _, child_rest = child_text.partition(":")
                item[child_key] = _scalar(child_rest.strip())
                index += 1
            items.append(item)
        else:
            items.append(_scalar(payload))
    return items, index


def _scalar(value):
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    return value


if __name__ == "__main__":
    print(write_catalog().relative_to(ROOT))
