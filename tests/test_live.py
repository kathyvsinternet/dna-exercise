"""Live golden run against the configured model. Skipped unless a key is available.

Uses real quota: about two requests per answered question, so roughly 40 to 50 requests
for the full set. Gemini's free tier allows 15 requests a minute, so this test waits
between questions.

Run it on purpose:

    .venv/bin/python -m unittest tests/test_live.py -v

The key is read from .env or the environment. It is never printed.
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
from model_gemini import GeminiError, gemini_from_env  # noqa: E402
from test_golden import _assert_rows  # noqa: E402

GOLDEN = TESTS / "golden_questions.yml"
PAUSE_SECONDS = 10


class LiveGoldenTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.saved = dict(os.environ)
        load_dotenv()
        os.environ.setdefault("CHAT_PROVIDER", "gemini")
        cls.model = gemini_from_env()
        if cls.model is None:
            raise unittest.SkipTest("No GEMINI_API_KEY in .env or the environment.")
        cls.questions = yaml.safe_load(GOLDEN.read_text())["questions"]

    @classmethod
    def tearDownClass(cls):
        os.environ.clear()
        os.environ.update(cls.saved)

    def test_golden_questions_against_the_live_model(self):
        failures = []
        for index, item in enumerate(self.questions):
            if index:
                time.sleep(PAUSE_SECONDS)
            try:
                payload = chat.answer(item["question"], self.model)
            except GeminiError as error:
                failures.append((item["id"], f"model error: {error}"))
                continue
            try:
                if "refuse" in item["expect"]:
                    self.assertEqual(payload["status"], "declined", payload["answer"])
                else:
                    self.assertEqual(payload["status"], "answered", payload["answer"])
                    _assert_rows(self, payload["rows"], item["expect"]["rows"])
            except AssertionError as error:
                failures.append((item["id"], f"{payload['status']}: {str(error)[:200]}"))
        if failures:
            report = "\n".join(f"  {item_id}: {reason}" for item_id, reason in failures)
            self.fail(f"{len(failures)} of {len(self.questions)} golden questions failed:\n{report}")


if __name__ == "__main__":
    unittest.main()
