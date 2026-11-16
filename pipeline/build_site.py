"""Write the site's data files from the metric files and the model.

site/data/catalog.json describes each metric and holds the totals the Ask page
uses. site/data/cubes/<metric>.json holds the counts the dashboard filters.
Every number goes through pipeline/metrics_engine.py. No user ids are written.
"""

import json
from itertools import product
from pathlib import Path

from metrics_engine import (
    dimension_value,
    dimensions,
    evaluate,
    load_metrics,
    read_source,
    select,
)

ROOT = Path(__file__).resolve().parents[1]
MIN_PEOPLE = 5
PERSON_KEYS = {"user_id"}
METRIC_ORDER = ["plans_active", "subscribers_active", "plans_paid_active", "plan_starts"]
PLAN_ORDER = ["Free", "Basic", "Premium", "Premium_Plus_Deluxe_XL"]
OPEN_RANGE = {"on_or_after": "0000-01-01", "on_or_before": "9999-12-31"}
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


def write_site_data(root=ROOT):
    root = Path(root)
    catalog, cubes = build_site_data(root)
    data_dir = root / "site" / "data"
    cubes_dir = data_dir / "cubes"
    cubes_dir.mkdir(parents=True, exist_ok=True)
    for stale in cubes_dir.glob("*.json"):
        if stale.stem not in cubes:
            stale.unlink()
    written = []
    catalog_path = data_dir / "catalog.json"
    catalog_path.write_text(json.dumps(catalog, indent=2) + "\n")
    written.append(catalog_path)
    for name, cube in cubes.items():
        path = cubes_dir / f"{name}.json"
        path.write_text(json.dumps(cube, separators=(",", ":")) + "\n")
        written.append(path)
    return written


def build_site_data(root=ROOT):
    root = Path(root)
    metrics = _ordered(load_metrics(root))
    rows = {definition["name"]: read_source(definition, root) for definition in metrics}
    businesses = _businesses(root)
    values = dimension_values(metrics, rows, businesses)
    cubes = {
        definition["name"]: build_cube(definition, rows[definition["name"]], values)
        for definition in metrics
    }
    catalog = {
        "businesses": businesses,
        "dimensions": values,
        "default_month_range": _default_month_range(metrics),
        "suppression": {
            "min_people": MIN_PEOPLE,
            "applies_to": "Metrics that count distinct user_id. A cell with fewer people is published as blank.",
        },
        "metrics": [_catalog_entry(definition, rows[definition["name"]], businesses) for definition in metrics],
        "refusals": _refusals([definition["name"] for definition in metrics]),
    }
    return catalog, cubes


def build_cube(definition, rows, values):
    names = dimensions(definition)
    params = _open_params(definition)
    person = definition.get("count_distinct") in PERSON_KEYS
    base = select(definition, rows, params=params)
    cells = []
    for combo in product(*[[None] + values[name] for name in names]):
        where = {name: value for name, value in zip(names, combo) if value is not None}
        matching = [
            row for row in base if all(dimension_value(row, name) == value for name, value in where.items())
        ]
        count = evaluate(definition, matching, where, params) if matching else 0
        if count == 0:
            continue
        if person and count < MIN_PEOPLE:
            count = None
        cells.append([*combo, count])
    return {
        "metric": definition["name"],
        "dimensions": names,
        "suppressed_below": MIN_PEOPLE if person else None,
        "cells": cells,
    }


def dimension_values(metrics, rows, businesses):
    found = {}
    for definition in metrics:
        selected = select(definition, rows[definition["name"]], params=_open_params(definition))
        for name in dimensions(definition):
            found.setdefault(name, set()).update(dimension_value(row, name) for row in selected)
    values = {}
    for name, seen in found.items():
        if name == "business_id":
            values[name] = [business["id"] for business in businesses if business["id"] in seen]
        elif name == "plan_tier":
            values[name] = [tier for tier in PLAN_ORDER if tier in seen] + sorted(seen - set(PLAN_ORDER))
        elif name.endswith("_month"):
            values[name] = _month_range(min(seen), max(seen))
        else:
            values[name] = sorted(seen)
    return values


def _ordered(metrics):
    ordered = [metrics[name] for name in METRIC_ORDER if name in metrics]
    ordered += [metrics[name] for name in sorted(metrics) if name not in METRIC_ORDER]
    return ordered


def _catalog_entry(definition, rows, businesses):
    params = _worked_params(definition)
    names = dimensions(definition)
    key = definition.get("count_distinct") or definition.get("count") or definition.get("sum")
    if "count_distinct" in definition:
        aggregation = f"count distinct {key}"
    elif "sum" in definition:
        aggregation = f"sum of {key}"
    else:
        aggregation = f"count of {key}"
    entry = {
        "name": definition["name"],
        "file": definition["file"],
        "question": definition["question"],
        "source": definition["source"],
        "aggregation": aggregation,
        "filters": [_filter_label(item, params) for item in definition.get("filters", [])],
        "conditions": [
            item for item in definition.get("filters", []) if "equals" in item or "not_equals" in item
        ],
        "group_by": definition.get("group_by", []),
        "dimensions": names,
        "notes": definition.get("notes", []),
        "cube": f"data/cubes/{definition['name']}.json",
        "total": evaluate(definition, rows, params=params),
    }
    if params:
        entry["parameters"] = params
    if "business_id" in names:
        entry["by_business"] = [
            {
                "id": business["id"],
                "short": business["short"],
                "value": evaluate(definition, rows, {"business_id": business["id"]}, params),
            }
            for business in businesses
        ]
    if "count_distinct" in definition and "business_id" in names:
        entry["business_totals_sum"] = sum(item["value"] for item in entry["by_business"])
        houses = {}
        for row in select(definition, rows, params=params):
            houses.setdefault(row[key], set()).add(row["business_id"])
        entry["people_in_more_than_one_business"] = sum(1 for seen in houses.values() if len(seen) > 1)
    return entry


def _worked_params(definition):
    parameters = definition.get("parameters", [])
    if not parameters:
        return {}
    known = definition.get("known_result") or {}
    missing = [parameter["name"] for parameter in parameters if parameter["name"] not in known]
    if missing:
        raise ValueError(f"{definition['file']} needs known_result values for {', '.join(missing)}.")
    return {parameter["name"]: known[parameter["name"]] for parameter in parameters}


def _open_params(definition):
    return {
        parameter["name"]: OPEN_RANGE[parameter["comparison"]]
        for parameter in definition.get("parameters", [])
    }


def _default_month_range(metrics):
    for definition in metrics:
        params = _worked_params(definition)
        bounds = {
            parameter["comparison"]: params[parameter["name"]][:7]
            for parameter in definition.get("parameters", [])
        }
        if "on_or_after" in bounds and "on_or_before" in bounds:
            return {"from": bounds["on_or_after"], "to": bounds["on_or_before"]}
    return None


def _month_range(first, last):
    months = []
    year, month = int(first[:4]), int(first[5:7])
    while f"{year:04d}-{month:02d}" <= last:
        months.append(f"{year:04d}-{month:02d}")
        month += 1
        if month == 13:
            year, month = year + 1, 1
    return months


def _businesses(root):
    rows = read_source({"source": "data/model/dim_business.csv"}, root)
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


def _filter_label(item, params):
    column = item["column"]
    if "equals" in item:
        return f"{column} = {item['equals']}"
    if "not_equals" in item:
        return f"{column} ≠ {item['not_equals']}"
    if "on_or_after" in item:
        return f"{column} on or after {params.get(item['on_or_after'], item['on_or_after'])}"
    return f"{column} on or before {params.get(item['on_or_before'], item['on_or_before'])}"


def _refusals(names):
    listed = ", ".join(names)
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
            "body": "plan_starts requires a period. The worked example on this page is 2026-01-01 through 2026-09-30. The dashboard lets you choose another range of start months.",
        },
        {
            "id": "unknown",
            "title": "That question is not in the catalog",
            "body": f"The page can answer {listed}. It will not invent another metric.",
        },
    ]


if __name__ == "__main__":
    for written in write_site_data():
        print(written.relative_to(ROOT))
