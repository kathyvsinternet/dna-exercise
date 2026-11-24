"""Run a structured query against a published mart, after checking it against the catalog.

A query is a plain dict. The chat interface will send one of these, and it is the
only thing that reaches the data:

    {
      "mart": "mart_user_share_country",
      "group_by": ["user_geo_country"],          # dimensions only
      "measures": ["n_users", "n_share"],         # measures only
      "filters": [{"column": "user_geo_country", "op": "eq", "value": "Germany"}],
      "sort": [{"column": "n_users", "direction": "desc"}],
      "limit": 25
    }

Rules, in the order they are checked:

- The mart and every column must be in the catalog. Anything else is refused.
- group_by takes dimensions. measures takes measures. Filters take dimensions.
- Filter operators: eq and in for text, eq and in for integers, eq, gte, and lte for dates
  and integers. Values are checked against the column type.
- A measure with aggregation sum adds up within each group. A measure with aggregation
  none is returned only when every group has exactly one row. Otherwise it is refused.
- A people count under 5 in a returned group is refused, unless the mart is a
  small_cell_exceptions mart.
- Rows are ordered by the sort keys, then by group_by, so ties come out the same way every run.
- limit defaults to 25 and may not exceed 100.

Every result carries the mart's notes and the caveats of the measures it returns, so
an answer can show them.

Refusals raise QueryRefused with a short code and a message. Nothing else is returned
for a refused query.
"""

import json
import re
from collections import OrderedDict
from datetime import date
from pathlib import Path

from catalog import SITE_MARTS, load_catalog

DEFAULT_LIMIT = 25
MAX_LIMIT = 100
SMALL_GROUP = 5
ALLOWED_KEYS = {"mart", "group_by", "measures", "filters", "sort", "limit"}
OPERATORS = {
    "text": {"eq", "in"},
    "integer": {"eq", "in", "gte", "lte"},
    "date": {"eq", "gte", "lte"},
    "number": set(),
}


class QueryRefused(Exception):
    """The query was not run. code says why, message says what to change."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


class Executor:
    def __init__(self, catalog=None, site_marts=SITE_MARTS):
        self.catalog = catalog or load_catalog()
        self.site_marts = Path(site_marts)
        self._rows = {}

    def run(self, query):
        spec = self._normalize(query)
        entry = self._mart(spec["mart"])
        rows = self._load(spec["mart"])
        types = {name: col["type"] for name, col in entry["columns"].items()}

        matched = [row for row in rows if all(_matches(row, f, types) for f in spec["filters"])]
        groups = self._group(matched, spec["group_by"])
        exception = spec["mart"] in self.catalog["small_cell_exceptions"]

        out = []
        for key, members in groups.items():
            record = dict(zip(spec["group_by"], key))
            for name in spec["measures"]:
                measure = entry["columns"][name]
                if measure["aggregation"] == "sum":
                    record[name] = _sum([_coerce(m[name], measure["type"]) for m in members], measure["type"])
                elif len(members) != 1:
                    raise QueryRefused(
                        "not_additive",
                        f"{name} cannot be added up. Group it by a column that gives one row per group, "
                        f"or ask for it on a single row.",
                    )
                else:
                    record[name] = _coerce(members[0][name], measure["type"])
                if measure["people"] and record[name] is not None and record[name] < SMALL_GROUP and not exception:
                    raise QueryRefused(
                        "small_group",
                        f"A group has fewer than {SMALL_GROUP} people. Combine it with another group.",
                    )
            out.append(record)

        out = _sort(out, spec["sort"], spec["group_by"])
        total = len(out)
        out = out[: spec["limit"]]

        return {
            "mart": spec["mart"],
            "label": entry["label"],
            "group_by": spec["group_by"],
            "measures": spec["measures"],
            "rows": out,
            "row_count": total,
            "notes": self._notes(entry, spec["measures"], no_match=not matched),
            "query": spec,
        }

    def _normalize(self, query):
        if not isinstance(query, dict):
            raise QueryRefused("invalid_request", "A query must be an object.")
        unknown = set(query) - ALLOWED_KEYS
        if unknown:
            raise QueryRefused("invalid_request", f"Unknown keys: {sorted(unknown)}.")
        mart = query.get("mart")
        if not isinstance(mart, str):
            raise QueryRefused("invalid_request", "A query needs a mart name.")
        entry = self._mart(mart)

        group_by = query.get("group_by", [])
        measures = query.get("measures")
        filters = query.get("filters", [])
        sort = query.get("sort", [])
        limit = query.get("limit", DEFAULT_LIMIT)

        if not isinstance(group_by, list) or not isinstance(filters, list) or not isinstance(sort, list):
            raise QueryRefused("invalid_request", "group_by, filters, and sort must be lists.")
        if not isinstance(measures, list) or not measures:
            raise QueryRefused("invalid_request", "A query needs at least one measure.")
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= MAX_LIMIT:
            raise QueryRefused("limit_exceeded", f"limit must be a whole number from 1 to {MAX_LIMIT}.")

        for name in group_by:
            column = self._column(entry, name)
            if column["role"] != "dimension":
                raise QueryRefused("invalid_field", f"{name} is a measure. Put it in measures, not group_by.")
        for name in measures:
            column = self._column(entry, name)
            if column["role"] != "measure":
                raise QueryRefused("invalid_field", f"{name} is a dimension. Put it in group_by, not measures.")

        normalized_filters = []
        for item in filters:
            if not isinstance(item, dict) or set(item) != {"column", "op", "value"}:
                raise QueryRefused("invalid_request", "Each filter needs column, op, and value.")
            column = self._column(entry, item["column"])
            if column["role"] != "dimension":
                raise QueryRefused("invalid_field", f"{item['column']} cannot be filtered on. Only dimensions can.")
            if item["op"] not in OPERATORS[column["type"]]:
                raise QueryRefused(
                    "bad_operator",
                    f"{item['op']} is not allowed on {item['column']}. Use one of {sorted(OPERATORS[column['type']])}.",
                )
            normalized_filters.append(
                {"column": item["column"], "op": item["op"], "value": _filter_value(item, column)}
            )

        normalized_sort = []
        for item in sort:
            if not isinstance(item, dict) or set(item) != {"column", "direction"}:
                raise QueryRefused("invalid_request", "Each sort needs column and direction.")
            if item["direction"] not in ("asc", "desc"):
                raise QueryRefused("invalid_request", "direction must be asc or desc.")
            if item["column"] not in group_by and item["column"] not in measures:
                raise QueryRefused("invalid_field", f"Sort by {item['column']} only if it is returned.")
            normalized_sort.append({"column": item["column"], "direction": item["direction"]})

        return {
            "mart": mart,
            "group_by": list(group_by),
            "measures": list(measures),
            "filters": normalized_filters,
            "sort": normalized_sort,
            "limit": limit,
        }

    def _mart(self, name):
        entry = self.catalog["marts"].get(name)
        if entry is None:
            raise QueryRefused("unknown_mart", f"{name} is not a mart this interface can query.")
        return entry

    def _column(self, entry, name):
        column = entry["columns"].get(name) if isinstance(name, str) else None
        if column is None:
            raise QueryRefused("unknown_column", f"{name!r} is not available in {entry['name']}.")
        return column

    def _load(self, mart):
        if mart not in self._rows:
            path = self.site_marts / f"{mart}.json"
            self._rows[mart] = json.loads(path.read_text())["rows"]
        return self._rows[mart]

    def _group(self, rows, group_by):
        """{group key: rows}. With no group_by, all rows form one group, or none if empty."""
        if not group_by:
            return OrderedDict([((), rows)]) if rows else OrderedDict()
        groups = OrderedDict()
        for row in rows:
            key = tuple(row[name] for name in group_by)
            groups.setdefault(key, []).append(row)
        return groups

    def _notes(self, entry, measures, no_match):
        notes = list(entry["notes"])
        for name in measures:
            caveat = entry["columns"][name]["caveat"]
            if caveat:
                notes.append(f"{entry['columns'][name]['label']}: {caveat}")
        if no_match:
            notes.append("No rows match these filters.")
        return notes


def _filter_value(item, column):
    """Normalize a filter value. Some models send a list as a JSON string, so that is accepted too."""
    kind = column["type"]
    raw = item["value"]
    if item["op"] == "in":
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except ValueError:
                raw = None
        if not isinstance(raw, list) or not raw:
            raise QueryRefused("bad_value", f"in needs a non-empty list for {item['column']}.")
        values = raw
    else:
        values = [raw]
    coerced = []
    for value in values:
        try:
            coerced.append(_check_value(value, kind))
        except (TypeError, ValueError) as error:
            raise QueryRefused("bad_value", f"{value!r} is not a valid {kind} for {item['column']}.") from error
    return coerced if item["op"] == "in" else coerced[0]


def _check_value(value, kind):
    if kind == "text":
        if not isinstance(value, str):
            raise TypeError
        return value
    if kind == "integer":
        if isinstance(value, str) and re.fullmatch(r"-?\d+", value.strip()):
            return int(value)
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError
        return value
    if kind == "date":
        if not isinstance(value, str):
            raise TypeError
        return date.fromisoformat(value).isoformat()
    raise ValueError


def _matches(row, item, types):
    value = row[item["column"]]
    kind = types[item["column"]]
    target = item["value"]
    if value is None:
        return False
    if kind == "integer":
        value = int(value)
    if item["op"] == "eq":
        return value == target
    if item["op"] == "in":
        return value in target
    if item["op"] == "gte":
        return value >= target
    if item["op"] == "lte":
        return value <= target
    return False


def _sum(values, kind):
    present = [value for value in values if value is not None]
    if not present:
        return 0
    if kind == "integer":
        return int(sum(present))
    return round(sum(present), 2)


def _coerce(value, kind):
    if value is None:
        return None
    if kind == "integer":
        return int(value)
    if kind == "number":
        return float(value)
    return str(value)


def _sort(rows, sort, group_by):
    """Order by group_by ascending as the tiebreak, then apply the sort keys.

    Each sort key is stable, so ties keep the group_by order. Missing values go last
    for every direction.
    """
    ordered = sorted(rows, key=lambda r: tuple(_key(r[name]) for name in group_by))
    for item in reversed(sort):
        column = item["column"]
        present = [r for r in ordered if r[column] is not None]
        missing = [r for r in ordered if r[column] is None]
        present.sort(key=lambda r: r[column], reverse=item["direction"] == "desc")
        ordered = present + missing
    return ordered


def _key(value):
    # None sorts after every value in the group_by tiebreak.
    if value is None:
        return (1, "")
    return (0, value)
