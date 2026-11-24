"""Run the golden questions through the executor, and check the literals against the oracle.

Run from the repository root:

    python -m unittest discover -s tests -v
"""

import sys
import unittest
from pathlib import Path

import yaml

TESTS = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTS.parent / "pipeline"))
sys.path.insert(0, str(TESTS))

import oracle  # noqa: E402
from catalog import load_catalog  # noqa: E402
from executor import Executor, QueryRefused  # noqa: E402

GOLDEN = TESTS / "golden_questions.yml"
TOLERANCE = 0.001


def _questions():
    return yaml.safe_load(GOLDEN.read_text())["questions"]


def _assert_rows(test, actual, expected):
    test.assertEqual(len(actual), len(expected), f"expected {len(expected)} rows, got {len(actual)}")
    for got, want in zip(actual, expected):
        for key, value in want.items():
            test.assertIn(key, got, f"missing column {key} in {got}")
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                test.assertAlmostEqual(got[key], value, delta=TOLERANCE, msg=key)
            else:
                test.assertEqual(got[key], value, msg=key)


class GoldenQuestionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.questions = _questions()
        cls.executor = Executor(load_catalog())

    def test_ids_are_unique(self):
        ids = [item["id"] for item in self.questions]
        self.assertEqual(len(ids), len(set(ids)), "Duplicate golden question ids.")

    def test_every_item_has_a_query_and_an_expectation(self):
        for item in self.questions:
            with self.subTest(item["id"]):
                self.assertIn("query", item)
                self.assertTrue("rows" in item["expect"] or "refuse" in item["expect"])

    def test_answers_match_expected_rows(self):
        for item in self.questions:
            if "rows" not in item["expect"]:
                continue
            with self.subTest(item["id"]):
                result = self.executor.run(item["query"])
                _assert_rows(self, result["rows"], item["expect"]["rows"])
                note = item["expect"].get("note_contains")
                if note:
                    self.assertTrue(
                        any(note.lower() in text.lower() for text in result["notes"]),
                        f"No note contains {note!r}: {result['notes']}",
                    )

    def test_refusals_return_the_expected_code(self):
        for item in self.questions:
            if "refuse" not in item["expect"]:
                continue
            with self.subTest(item["id"]):
                with self.assertRaises(QueryRefused) as raised:
                    self.executor.run(item["query"])
                self.assertEqual(raised.exception.code, item["expect"]["refuse"])

    def test_literal_answers_match_the_model_oracle(self):
        """The golden literals must agree with a recount from data/model, not from the marts."""
        for item in self.questions:
            if "oracle" not in item or "rows" not in item["expect"]:
                continue
            with self.subTest(item["id"]):
                spec = item["oracle"]
                recomputed = getattr(oracle, spec["fn"])(*spec.get("args", []))
                _assert_rows(self, recomputed, item["expect"]["rows"])


if __name__ == "__main__":
    unittest.main()
