"""Golden tests: every metric file's known_result must match the engine.

Run from the repository root after python pipeline/build.py:

    python -m unittest discover -s tests -v
"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline"))

from build_site import build_site_data  # noqa: E402
from metrics_engine import MetricError, evaluate, load_metrics, read_source, select  # noqa: E402

BREAKDOWNS = {
    "by_business_id": "business_id",
    "by_plan_tier": "plan_tier",
    "by_billing_cycle": "billing_cycle",
}


def worked_params(definition):
    known = definition["known_result"]
    return {parameter["name"]: known[parameter["name"]] for parameter in definition.get("parameters", [])}


class KnownResultTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.metrics = load_metrics(ROOT)
        cls.rows = {name: read_source(definition, ROOT) for name, definition in cls.metrics.items()}

    def test_every_metric_has_a_known_result(self):
        for name, definition in self.metrics.items():
            with self.subTest(metric=name):
                self.assertIn("total", definition.get("known_result", {}))

    def test_totals_and_breakdowns_match(self):
        for name, definition in self.metrics.items():
            known = definition["known_result"]
            params = worked_params(definition)
            rows = self.rows[name]
            with self.subTest(metric=name, view="total"):
                self.assertEqual(evaluate(definition, rows, params=params), known["total"])
            for block, column in BREAKDOWNS.items():
                for value, expected in known.get(block, {}).items():
                    with self.subTest(metric=name, view=f"{column}={value}"):
                        self.assertEqual(evaluate(definition, rows, {column: value}, params), expected)

    def test_subscriber_business_totals_double_count_shared_people(self):
        definition = self.metrics["subscribers_active"]
        known = definition["known_result"]
        rows = self.rows["subscribers_active"]
        by_business = [
            evaluate(definition, rows, {"business_id": business_id})
            for business_id in known["by_business_id"]
        ]
        self.assertEqual(sum(by_business), known["business_totals_sum"])
        houses = {}
        for row in select(definition, rows):
            houses.setdefault(row["user_id"], set()).add(row["business_id"])
        shared = sum(1 for seen in houses.values() if len(seen) > 1)
        self.assertEqual(shared, known["people_active_in_more_than_one_business"])


class RuleTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.metrics = load_metrics(ROOT)

    def test_undeclared_filter_is_rejected(self):
        definition = self.metrics["subscribers_active"]
        rows = read_source(definition, ROOT)
        with self.assertRaises(MetricError):
            evaluate(definition, rows, {"plan_tier": "Basic"})

    def test_plan_starts_requires_a_period(self):
        definition = self.metrics["plan_starts"]
        rows = read_source(definition, ROOT)
        with self.assertRaises(MetricError):
            evaluate(definition, rows)


class SiteDataTest(unittest.TestCase):
    """The dashboard's lookups must give the same numbers as the engine."""

    @classmethod
    def setUpClass(cls):
        cls.metrics = load_metrics(ROOT)
        cls.catalog, cls.cubes = build_site_data(ROOT)

    def cell(self, name, **where):
        cube = self.cubes[name]
        key = [where.get(dimension) for dimension in cube["dimensions"]]
        for cell in cube["cells"]:
            if cell[:-1] == key:
                return cell[-1]
        return 0

    def test_rollup_cells_match_known_results(self):
        for name in ("plans_active", "subscribers_active", "plans_paid_active"):
            known = self.metrics[name]["known_result"]
            with self.subTest(metric=name):
                self.assertEqual(self.cell(name), known["total"])
                for business_id, expected in known["by_business_id"].items():
                    self.assertEqual(self.cell(name, business_id=business_id), expected)

    def test_additive_cells_sum_to_the_total(self):
        for name in ("plans_active", "plans_paid_active"):
            cube = self.cubes[name]
            finest = [cell for cell in cube["cells"] if None not in cell[:-1]]
            with self.subTest(metric=name):
                self.assertEqual(sum(cell[-1] for cell in finest), self.metrics[name]["known_result"]["total"])

    def test_plan_start_months_sum_to_the_worked_period(self):
        known = self.metrics["plan_starts"]["known_result"]
        months = [
            month
            for month in self.catalog["dimensions"]["start_date_month"]
            if known["period_start"][:7] <= month <= known["period_end"][:7]
        ]
        total = sum(self.cell("plan_starts", start_date_month=month) for month in months)
        self.assertEqual(total, known["total"])
        for business_id, expected in known["by_business_id"].items():
            subtotal = sum(
                self.cell("plan_starts", business_id=business_id, start_date_month=month) for month in months
            )
            self.assertEqual(subtotal, expected)

    def test_no_user_identifiers_are_published(self):
        published = repr(self.catalog) + repr(self.cubes)
        self.assertNotIn("USR_", published)
        self.assertNotIn("@", published)


if __name__ == "__main__":
    unittest.main()
