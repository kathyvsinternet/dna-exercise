"""Compute governed metrics from the files in metrics/.

A metric is computed only the way its file says: the filters it lists, the
count it names, and the dimensions in its group_by. A date parameter also adds
a month dimension, such as start_date_month. Any other request raises
MetricError.
"""

import csv
from datetime import date, datetime
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
COMPARISONS = ("equals", "not_equals", "on_or_after", "on_or_before")
MONTH_SUFFIX = "_month"


class MetricError(Exception):
    """A metric file is malformed, or a request asked for something it does not allow."""


def load_metrics(root=ROOT):
    metrics = {}
    for path in sorted((Path(root) / "metrics").glob("*.yml")):
        definition = _plain(yaml.safe_load(path.read_text()))
        _validate(definition, path)
        definition["file"] = f"metrics/{path.name}"
        metrics[definition["name"]] = definition
    return metrics


def read_source(definition, root=ROOT):
    path = Path(root) / definition["source"]
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def dimensions(definition):
    names = list(definition.get("group_by", []))
    for parameter in definition.get("parameters", []):
        column = parameter["column"]
        extra = column if column.endswith(MONTH_SUFFIX) else month_dimension(column)
        if extra not in names:
            names.append(extra)
    return names


def month_dimension(column):
    return f"{column}{MONTH_SUFFIX}"


def dimension_value(row, column):
    if column in row:
        return row[column]
    if column.endswith(MONTH_SUFFIX):
        source = column[: -len(MONTH_SUFFIX)]
        if source in row:
            return row[source][:7]
    raise MetricError(f"{column} is not a column in the metric source.")


def select(definition, rows, where=None, params=None):
    where = where or {}
    allowed = dimensions(definition)
    undeclared = sorted(set(where) - set(allowed))
    if undeclared:
        raise MetricError(
            f"{definition['name']} cannot be filtered by {', '.join(undeclared)}. "
            f"Its file allows {', '.join(allowed)}."
        )
    values = _parameters(definition, params)
    selected = [
        row
        for row in rows
        if all(_passes(row, item, values) for item in definition.get("filters", []))
    ]
    for column, value in where.items():
        selected = [row for row in selected if dimension_value(row, column) == value]
    return selected


def evaluate(definition, rows, where=None, params=None):
    return measure(definition, select(definition, rows, where, params))


def measure(definition, rows):
    if "sum" in definition:
        column = definition["sum"]
        total = 0
        for row in rows:
            if row[column] == "":
                continue
            number = float(row[column])
            if not number.is_integer():
                raise MetricError(f"{definition['name']} cannot sum {column} because {row[column]} is not a whole number.")
            total += int(number)
        return total
    if "count_distinct" in definition:
        key = definition["count_distinct"]
        return len({row[key] for row in rows})
    return len(rows)


def _parameters(definition, params):
    params = params or {}
    declared = [parameter["name"] for parameter in definition.get("parameters", [])]
    missing = [name for name in declared if name not in params]
    if missing:
        raise MetricError(f"{definition['name']} requires {', '.join(missing)}.")
    unknown = sorted(set(params) - set(declared))
    if unknown:
        raise MetricError(f"{definition['name']} has no parameter {', '.join(unknown)}.")
    return params


def _passes(row, item, params):
    value = row[item["column"]]
    if "equals" in item:
        return value == item["equals"]
    if "not_equals" in item:
        return value != item["not_equals"]
    if value == "":
        return False
    if "on_or_after" in item:
        return value >= params.get(item["on_or_after"], item["on_or_after"])
    return value <= params.get(item["on_or_before"], item["on_or_before"])


def _validate(definition, path):
    if not isinstance(definition, dict):
        raise MetricError(f"{path.name} is not a mapping.")
    if definition.get("name") != path.stem:
        raise MetricError(f"{path.name} declares name {definition.get('name')!r}. The name must match the file.")
    for key in ("question", "source"):
        if not definition.get(key):
            raise MetricError(f"{path.name} is missing {key}.")
    counts = [key for key in ("count", "count_distinct", "sum") if key in definition]
    if len(counts) != 1:
        raise MetricError(f"{path.name} needs exactly one of count, count_distinct, or sum.")
    for item in definition.get("filters", []):
        found = [key for key in COMPARISONS if key in item]
        if "column" not in item or len(found) != 1:
            raise MetricError(f"{path.name} has a filter without one column and one comparison: {item}.")


def _plain(value):
    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_plain(item) for item in value]
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value
