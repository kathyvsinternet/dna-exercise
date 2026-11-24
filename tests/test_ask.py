"""The .env loader and the command-line entry point. No network, no key needed."""

import contextlib
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path

TESTS = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTS.parent / "pipeline"))

import ask  # noqa: E402


class DotenvTests(unittest.TestCase):
    def setUp(self):
        self.saved = dict(os.environ)
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.saved)

    def _env_file(self, text):
        path = Path(self.dir.name, ".env")
        path.write_text(text)
        return path

    def test_reads_keys_skips_comments_and_strips_quotes(self):
        os.environ.pop("ASK_TEST_A", None)
        os.environ.pop("ASK_TEST_B", None)
        path = self._env_file("# a comment\n\nASK_TEST_A=\"value-a\"\nASK_TEST_B='value-b'\nnot a pair\n")
        loaded = ask.load_dotenv(path)
        self.assertEqual(os.environ["ASK_TEST_A"], "value-a")
        self.assertEqual(os.environ["ASK_TEST_B"], "value-b")
        self.assertEqual(sorted(loaded), ["ASK_TEST_A", "ASK_TEST_B"])

    def test_values_already_in_the_environment_win(self):
        os.environ["ASK_TEST_A"] = "from-shell"
        ask.load_dotenv(self._env_file("ASK_TEST_A=from-file\n"))
        self.assertEqual(os.environ["ASK_TEST_A"], "from-shell")

    def test_empty_values_are_not_loaded(self):
        os.environ.pop("ASK_TEST_EMPTY", None)
        ask.load_dotenv(self._env_file("ASK_TEST_EMPTY=\n"))
        self.assertNotIn("ASK_TEST_EMPTY", os.environ)

    def test_missing_file_is_fine(self):
        self.assertEqual(ask.load_dotenv(Path(self.dir.name, "absent.env")), [])


class MainTests(unittest.TestCase):
    def setUp(self):
        self.saved = dict(os.environ)
        self.addCleanup(self._restore)

    def _restore(self):
        os.environ.clear()
        os.environ.update(self.saved)

    def test_usage_error_without_a_question(self):
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(ask.main(["ask.py"]), 2)
            self.assertEqual(ask.main(["ask.py", "   "]), 2)

    def test_missing_key_says_where_to_put_it(self):
        os.environ.pop("GEMINI_API_KEY", None)
        # Stop .env from supplying a key on a machine where one exists.
        original = ask.load_dotenv
        ask.load_dotenv = lambda *args, **kwargs: []
        try:
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                self.assertEqual(ask.main(["ask.py", "How many active users?"]), 1)
            self.assertIn(".env", stderr.getvalue())
        finally:
            ask.load_dotenv = original


if __name__ == "__main__":
    unittest.main()
