"""Live golden run against the configured model. Skipped unless RUN_LIVE=1 is set.

Uses real quota: about two or three requests per question, roughly 50 for the full set.
Requests are spaced to stay under Gemini's free-tier limit of 15 a minute, and rate limits
and brief overloads (429, 503) are retried.

Run it on purpose:

    RUN_LIVE=1 .venv/bin/python -m unittest tests/test_live.py -v

The key is read from .env or the environment. It is never printed.

What is checked for each question:
- The chat status. An item's expect.chat sets it; otherwise refusals expect "declined" and
  answers expect "answered".
- For answers with expected rows: each expected row appears in the answer's rows, matched on
  the expected columns that the answer returned. Order and extra rows are allowed. The
  deterministic tests in test_golden.py stay strict.
- For every answer: no row carries a restricted column or a user identifier.
"""

import os
import sys
import time
import unittest
from pathlib import Path

import yaml

TESTS = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTS.parent / "pipeline"))
sys.path.insert(0, str(TESTS))

import chat  # noqa: E402
from ask import load_dotenv  # noqa: E402
from catalog import restricted_columns  # noqa: E402
from model_gemini import GeminiError, gemini_from_env  # noqa: E402

GOLDEN = TESTS / "golden_questions.yml"
# Gemini's free tier allows 15 requests a minute. Spacing requests 6 seconds apart keeps us at 10.
REQUEST_SPACING_SECONDS = 6
RETRY_WAIT_SECONDS = 60
RETRIES = 3
RETRYABLE = ("HTTP 429", "HTTP 503")
USER_IDENTIFIERS = {"user_id"}
TOLERANCE = 0.001


class PacedModel:
    """Spaces out requests and waits out rate limits and brief overloads."""

    def __init__(self, model):
        self.model = model

    def respond(self, system, messages, tools):
        for attempt in range(RETRIES + 1):
            time.sleep(REQUEST_SPACING_SECONDS)
            try:
                return self.model.respond(system, messages, tools)
            except GeminiError as error:
                if attempt == RETRIES or not any(code in str(error) for code in RETRYABLE):
                    raise
                time.sleep(RETRY_WAIT_SECONDS)


def _same(actual, expected):
    if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
        return abs(actual - expected) <= TOLERANCE
    return actual == expected


def _row_matches(row, wanted):
    shared = [key for key in wanted if key in row]
    return bool(shared) and all(_same(row[key], wanted[key]) for key in shared)


def missing_rows(actual, expected):
    """The expected rows that no actual row matches. An empty list means the answer covers them."""
    return [want for want in expected if not any(_row_matches(row, want) for row in actual)]


class LiveGoldenTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Opt-in only. A plain test run must never spend quota, even when .env holds a key.
        if os.environ.get("RUN_LIVE") != "1":
            raise unittest.SkipTest("Live test is opt-in. Set RUN_LIVE=1 to run it.")
        cls.saved = dict(os.environ)
        load_dotenv()
        os.environ.setdefault("CHAT_PROVIDER", "gemini")
        inner = gemini_from_env()
        if inner is None:
            raise unittest.SkipTest("No GEMINI_API_KEY in .env or the environment.")
        cls.model = PacedModel(inner)
        cls.questions = yaml.safe_load(GOLDEN.read_text())["questions"]
        cls.restricted = restricted_columns() | USER_IDENTIFIERS

    @classmethod
    def tearDownClass(cls):
        os.environ.clear()
        os.environ.update(cls.saved)

    def _problems(self, item, payload):
        expect = item["expect"]
        wanted = expect.get("chat") or ("declined" if "refuse" in expect else "answered")
        problems = []
        if payload["status"] != wanted:
            problems.append(f"status {payload['status']}, expected {wanted}")
        if payload["status"] == "answered":
            leaked = {key for row in payload["rows"] for key in row} & self.restricted
            if leaked:
                problems.append(f"answer returned restricted columns: {sorted(leaked)}")
            if "rows" in expect:
                missing = missing_rows(payload["rows"], expect["rows"])
                if missing:
                    problems.append(f"expected rows not found: {missing}")
        return problems

    def test_golden_questions_against_the_live_model(self):
        failures = []
        for item in self.questions:
            try:
                payload = chat.answer(item["question"], self.model)
            except GeminiError as error:
                failures.append((item["id"], f"model error: {error}"))
                continue
            problems = self._problems(item, payload)
            if problems:
                failures.append((item["id"], "; ".join(problems) + f" | answer: {payload['answer'][:160]!r}"))
        if failures:
            report = "\n".join(f"  {item_id}: {reason}" for item_id, reason in failures)
            self.fail(f"{len(failures)} of {len(self.questions)} golden questions failed:\n{report}")


if __name__ == "__main__":
    unittest.main()
