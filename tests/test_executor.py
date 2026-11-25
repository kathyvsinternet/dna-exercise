"""Rules the executor enforces, tested on small fake marts.

These cases are not in the golden set because the published marts never trigger
them: no group in the real data is under 5 people outside the approved exceptions,
and the real queries are all valid.
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

TESTS = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTS.parent / "pipeline"))

from catalog import load_catalog  # noqa: E402
from executor import DEFAULT_LIMIT, MAX_LIMIT, Executor, QueryRefused  # noqa: E402


def _column(role, kind, aggregation=None, people=False, label=""):
    return {
        "name": "",
        "role": role,
        "type": kind,
        "label": label,
        "synonyms": [],
        "caveat": "",
        "aggregation": aggregation,
        "people": people,
    }


def _catalog(mart, columns, exceptions=()):
    for name, column in columns.items():
        column["name"] = name
    return {
        "marts": {
            mart: {
                "name": mart,
                "label": mart,
                "description": "",
                "grain": "",
                "notes": [],
                "columns": columns,
            }
        },
        "small_cell_exceptions": set(exceptions),
        "not_answerable": [],
    }


class FakeMart:
    """A throwaway mart on disk, so the executor reads real JSON."""

    def __init__(self, mart, columns, rows, exceptions=()):
        self.dir = tempfile.TemporaryDirectory()
        self.mart = mart
        payload = {"name": mart, "columns": [], "rows": rows}
        Path(self.dir.name, f"{mart}.json").write_text(json.dumps(payload))
        self.catalog = _catalog(mart, columns, exceptions)

    def executor(self):
        return Executor(self.catalog, site_marts=self.dir.name)

    def close(self):
        self.dir.cleanup()


class ExecutorRuleTests(unittest.TestCase):
    def setUp(self):
        self.group = _column("dimension", "text", label="Group")
        self.count = _column("measure", "integer", aggregation="sum", label="Count")
        self.people = _column("measure", "integer", aggregation="sum", people=True, label="People")
        self.share = _column("measure", "number", aggregation="none", label="Share")
        self.columns = {"grp": self.group, "cnt": self.count, "people": self.people, "share": self.share}

    def _run(self, rows, query, exceptions=()):
        fake = FakeMart("fake", self.columns, rows, exceptions)
        self.addCleanup(fake.close)
        return fake.executor().run({"mart": "fake", **query})

    def test_small_group_is_refused(self):
        rows = [
            {"grp": "a", "cnt": 1, "people": 3, "share": 0.1},
            {"grp": "b", "cnt": 1, "people": 40, "share": 0.9},
        ]
        with self.assertRaises(QueryRefused) as raised:
            self._run(rows, {"group_by": ["grp"], "measures": ["people"]})
        self.assertEqual(raised.exception.code, "small_group")

    def test_small_group_is_allowed_for_an_approved_exception(self):
        rows = [{"grp": "a", "cnt": 1, "people": 1, "share": 1.0}]
        result = self._run(rows, {"group_by": ["grp"], "measures": ["people"]}, exceptions=["fake"])
        self.assertEqual(result["rows"], [{"grp": "a", "people": 1}])

    def test_non_additive_measure_over_several_rows_is_refused(self):
        rows = [
            {"grp": "a", "cnt": 1, "people": 10, "share": 0.5},
            {"grp": "b", "cnt": 1, "people": 10, "share": 0.5},
        ]
        with self.assertRaises(QueryRefused) as raised:
            self._run(rows, {"measures": ["share"]})
        self.assertEqual(raised.exception.code, "not_additive")

    def test_non_additive_measure_is_returned_at_its_own_grain(self):
        rows = [
            {"grp": "a", "cnt": 1, "people": 10, "share": 0.5},
            {"grp": "b", "cnt": 1, "people": 10, "share": 0.5},
        ]
        result = self._run(rows, {"group_by": ["grp"], "measures": ["share"]})
        self.assertEqual([r["share"] for r in result["rows"]], [0.5, 0.5])

    def test_integer_sums_stay_integers(self):
        rows = [{"grp": "a", "cnt": 2, "people": 10, "share": 0.5}, {"grp": "a", "cnt": 3, "people": 10, "share": 0.5}]
        result = self._run(rows, {"group_by": ["grp"], "measures": ["cnt"]})
        self.assertEqual(result["rows"], [{"grp": "a", "cnt": 5}])
        self.assertIsInstance(result["rows"][0]["cnt"], int)

    def test_ties_break_by_group_by_and_missing_values_go_last(self):
        rows = [
            {"grp": "b", "cnt": 5, "people": 10, "share": 0.1},
            {"grp": "a", "cnt": 5, "people": 10, "share": 0.1},
            {"grp": "c", "cnt": None, "people": 10, "share": 0.1},
            {"grp": "d", "cnt": 9, "people": 10, "share": 0.1},
        ]
        result = self._run(
            rows,
            {"group_by": ["grp"], "measures": ["cnt"], "sort": [{"column": "cnt", "direction": "desc"}]},
        )
        self.assertEqual([r["grp"] for r in result["rows"]], ["d", "a", "b", "c"])

    def test_no_matching_rows_returns_an_empty_result_with_a_note(self):
        rows = [{"grp": "a", "cnt": 1, "people": 10, "share": 0.5}]
        result = self._run(
            rows,
            {"group_by": ["grp"], "measures": ["cnt"], "filters": [{"column": "grp", "op": "eq", "value": "z"}]},
        )
        self.assertEqual(result["rows"], [])
        self.assertIn("No rows match these filters.", result["notes"])

    def test_default_and_maximum_limits(self):
        rows = [{"grp": str(i).zfill(3), "cnt": 1, "people": 10, "share": 0.1} for i in range(120)]
        result = self._run(rows, {"group_by": ["grp"], "measures": ["cnt"]})
        self.assertEqual(len(result["rows"]), DEFAULT_LIMIT)
        self.assertEqual(result["row_count"], 120)
        result = self._run(rows, {"group_by": ["grp"], "measures": ["cnt"], "limit": MAX_LIMIT})
        self.assertEqual(len(result["rows"]), MAX_LIMIT)

    def test_limit_out_of_range_is_refused(self):
        for bad in (0, MAX_LIMIT + 1, "5", True, 2.5):
            with self.subTest(limit=bad):
                with self.assertRaises(QueryRefused) as raised:
                    self._run([], {"measures": ["cnt"], "limit": bad})
                self.assertEqual(raised.exception.code, "limit_exceeded")

    def test_unknown_keys_are_refused(self):
        with self.assertRaises(QueryRefused) as raised:
            self._run([], {"measures": ["cnt"], "sql": "select 1"})
        self.assertEqual(raised.exception.code, "invalid_request")

    def test_filter_operator_must_fit_the_column_type(self):
        with self.assertRaises(QueryRefused) as raised:
            self._run([], {"measures": ["cnt"], "filters": [{"column": "grp", "op": "gte", "value": "a"}]})
        self.assertEqual(raised.exception.code, "bad_operator")

    def test_filter_value_must_match_the_column_type(self):
        columns = {"grp": self.group, "cnt": self.count, "when": _column("dimension", "date", label="When")}
        fake = FakeMart("fake", columns, [{"grp": "a", "cnt": 1, "when": "2025-01-01"}])
        self.addCleanup(fake.close)
        executor = fake.executor()
        for bad_filter in (
            {"column": "when", "op": "eq", "value": "2025-13-01"},
            {"column": "when", "op": "eq", "value": 2025},
            {"column": "grp", "op": "in", "value": "a"},
            {"column": "grp", "op": "in", "value": []},
        ):
            with self.subTest(filter=bad_filter):
                with self.assertRaises(QueryRefused) as raised:
                    executor.run({"mart": "fake", "measures": ["cnt"], "filters": [bad_filter]})
                self.assertEqual(raised.exception.code, "bad_value")

    def test_field_roles_are_checked(self):
        cases = {
            "group_by a measure": {"group_by": ["cnt"], "measures": ["cnt"]},
            "measure that is a dimension": {"measures": ["grp"]},
            "filter on a measure": {"measures": ["cnt"], "filters": [{"column": "cnt", "op": "eq", "value": 1}]},
            "sort by a column not returned": {"measures": ["cnt"], "sort": [{"column": "people", "direction": "asc"}]},
        }
        for label, query in cases.items():
            with self.subTest(label):
                with self.assertRaises(QueryRefused) as raised:
                    self._run([], query)
                self.assertEqual(raised.exception.code, "invalid_field")

    def test_a_query_needs_a_measure(self):
        with self.assertRaises(QueryRefused) as raised:
            self._run([], {"group_by": ["grp"], "measures": []})
        self.assertEqual(raised.exception.code, "invalid_request")

    def test_unknown_mart_and_column_are_refused(self):
        executor = Executor(load_catalog())
        with self.assertRaises(QueryRefused) as raised:
            executor.run({"mart": "not_a_mart", "measures": ["cnt"]})
        self.assertEqual(raised.exception.code, "unknown_mart")
        with self.assertRaises(QueryRefused) as raised:
            self._run([], {"group_by": ["email"], "measures": ["cnt"]})
        self.assertEqual(raised.exception.code, "unknown_column")

    def test_published_catalog_has_no_restricted_columns(self):
        catalog = load_catalog()
        for name, entry in catalog["marts"].items():
            for column in ("user_name", "email"):
                with self.subTest(mart=name, column=column):
                    self.assertNotIn(column, entry["columns"])


if __name__ == "__main__":
    unittest.main()
