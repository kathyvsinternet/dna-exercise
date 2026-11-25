"""One chat turn, driven by scripted models. No provider or network is used.

These tests check the plumbing: refusals go back to the model, unsourced numbers are
caught, the tool-call limit holds, and the HTTP contract returns the right codes. They do
not measure how well a real model answers. That comes later, with a live model.

The golden questions also run through the loop, with a model that asks for the golden
query and writes the expected values back.
"""

import contextlib
import io
import json
import sys
import unittest
from pathlib import Path

import yaml

TESTS = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTS.parent / "pipeline"))
sys.path.insert(0, str(TESTS))

import chat  # noqa: E402
from catalog import load_catalog  # noqa: E402
from test_golden import _assert_rows  # noqa: E402

GOLDEN = TESTS / "golden_questions.yml"
ORIGIN = "https://example.github.io"


class ScriptedModel:
    """Returns whatever responder(messages) says. Records every call it received."""

    def __init__(self, responder):
        self.responder = responder
        self.received = []

    def respond(self, system, messages, tools):
        self.received.append([dict(m) for m in messages])
        return self.responder(messages)


def ask(query, call_id="t1"):
    return {"text": None, "tool_calls": [{"id": call_id, "name": "query_mart", "input": query}]}


def say(text):
    return {"text": text, "tool_calls": []}


def script(*replies):
    """A model that gives the replies in order, whatever it is sent."""
    queue = list(replies)
    return ScriptedModel(lambda messages: queue.pop(0))


HEADLINE = {"mart": "mart_user_info_counts", "measures": ["n_users_active"]}


class ChatTurnTests(unittest.TestCase):
    def test_grounded_answer_is_returned(self):
        model = script(ask(HEADLINE), say("There are 389 active users."))
        payload = chat.answer("How many active users are there?", model)
        self.assertEqual(payload["status"], "answered")
        self.assertEqual(payload["answer"], "There are 389 active users.")
        self.assertEqual(payload["rows"], [{"n_users_active": 389}])
        self.assertEqual(payload["mart"], "mart_user_info_counts")
        self.assertEqual(payload["refusals"], [])

    def test_number_not_in_the_rows_gets_a_cannot_answer_reply(self):
        model = script(ask(HEADLINE), say("There are 400 active users."))
        payload = chat.answer("How many active users are there?", model)
        self.assertEqual(payload["status"], "unverified")
        self.assertEqual(payload["answer"], chat.CANNOT_VERIFY)
        self.assertNotIn("400", payload["answer"])
        self.assertNotIn("389", payload["answer"])

    def test_number_in_the_question_is_allowed(self):
        query = {
            "mart": "mart_user_qtr_counts",
            "measures": ["user_subscriptions"],
            "filters": [
                {"column": "quarter", "op": "gte", "value": "2025-01-01"},
                {"column": "quarter", "op": "lte", "value": "2025-12-31"},
            ],
        }
        model = script(ask(query), say("236 subscriptions started in 2025."))
        payload = chat.answer("How many subscriptions started in 2025?", model)
        self.assertEqual(payload["status"], "answered")

    def test_percentages_and_rounding_of_a_share_are_accepted(self):
        query = {
            "mart": "mart_user_share_device",
            "measures": ["n_users", "n_share"],
            "filters": [{"column": "user_prim_device", "op": "eq", "value": "iOS_app"}],
        }
        model = script(ask(query), say("84 users, about 21.6% of the active users, use iOS as their main device."))
        payload = chat.answer("What share of active users use iOS?", model)
        self.assertEqual(payload["status"], "answered")

    def test_number_inside_a_title_is_allowed(self):
        query = {
            "mart": "mart_content_engagement",
            "group_by": ["title"],
            "measures": ["n_engagement_events"],
            "sort": [{"column": "n_engagement_events", "direction": "desc"}],
            "limit": 1,
        }
        model = script(ask(query), say("The Last Prairiefox (Mock Book #205) has 23 engagements."))
        payload = chat.answer("Which title has the most engagement?", model)
        self.assertEqual(payload["status"], "answered")

    def test_figure_quoted_from_a_catalog_note_is_sourced(self):
        shown = [{"row_count": 5, "rows": [], "notes": ["The shares of all rows add up to 1, so a total is meaningful."]}]
        self.assertEqual(chat._unverified_numbers("The shares add up to 1.", "q", shown), [])
        self.assertEqual(chat._unverified_numbers("The shares add up to 2.", "q", shown), [2.0])

    def test_list_positions_are_not_treated_as_figures(self):
        nothing_shown = [{"row_count": 0, "rows": []}]
        self.assertEqual(chat._unverified_numbers("1. Alpha\n2. Beta\n3. Gamma", "q", nothing_shown), [])
        self.assertEqual(chat._unverified_numbers("There are 7 of them.", "q", nothing_shown), [7.0])
        self.assertEqual(chat._unverified_numbers("About 2.5 users", "q", nothing_shown), [2.5])

    def test_refusal_goes_back_to_the_model_and_it_recovers(self):
        bad = {"mart": "mart_user_share_country", "group_by": ["email"], "measures": ["n_users"]}
        model = script(ask(bad), say("I can't provide email addresses."))
        payload = chat.answer("What is the email for USR_00001?", model)
        self.assertEqual(payload["status"], "declined")
        self.assertEqual(payload["refusals"], ["unknown_column"])
        tool_message = [m for m in model.received[1] if m["role"] == "tool"][0]
        self.assertIn("unknown_column", tool_message["content"])

    def test_unsourced_number_with_no_successful_query_is_unverified(self):
        model = script(say("There are 5 email addresses on file."))
        payload = chat.answer("What is the email for USR_00001?", model)
        self.assertEqual(payload["status"], "unverified")
        self.assertEqual(payload["answer"], chat.CANNOT_VERIFY)

    def test_text_without_numbers_and_without_data_is_declined(self):
        model = script(say("I can't answer that from the available data."))
        payload = chat.answer("What is our retention rate?", model)
        self.assertEqual(payload["status"], "declined")
        self.assertEqual(payload["rows"], [])

    def test_tool_call_limit_stops_a_looping_model(self):
        bad = {"mart": "dim_user", "measures": ["n_users"]}
        model = ScriptedModel(lambda messages: ask(bad))
        payload = chat.answer("Show me the users table.", model)
        self.assertEqual(payload["status"], "gave_up")
        self.assertEqual(payload["refusals"], ["unknown_mart"] * chat.MAX_TOOL_CALLS)
        self.assertEqual(payload["tool_calls"], chat.MAX_TOOL_CALLS + 1)

    def test_question_must_be_text_and_short(self):
        for bad, code in ((None, "bad_request"), ("   ", "bad_request"), ("x" * (chat.MAX_QUESTION_CHARS + 1), "too_long")):
            with self.subTest(question=bad if bad is None else bad[:10]):
                with self.assertRaises(chat.ChatError) as raised:
                    chat.answer(bad, script(say("hi")))
                self.assertEqual(raised.exception.code, code)

    def test_system_prompt_lists_catalog_columns_and_no_restricted_names(self):
        prompt = chat.build_system_prompt(load_catalog())
        self.assertIn("mart_user_info_counts", prompt)
        self.assertIn("total_monthly_payment", prompt)
        self.assertNotIn("user_name", prompt)
        self.assertNotIn("- email (", prompt)

    def test_tool_schema_offers_only_catalog_marts(self):
        catalog = load_catalog()
        tool = chat.tool_definition(catalog)
        self.assertEqual(tool["input_schema"]["properties"]["mart"]["enum"], sorted(catalog["marts"]))


class PromptTests(unittest.TestCase):
    def test_prompt_tells_the_model_to_query_totals_without_grouping(self):
        prompt = chat.build_system_prompt(chat.load_catalog())
        self.assertIn("call query_mart with no group_by", prompt)
        self.assertIn("filter to that value", prompt)


class HttpContractTests(unittest.TestCase):
    def _handle(self, body=None, origin=ORIGIN, allowed=ORIGIN, model="default"):
        if model == "default":
            model = script(ask(HEADLINE), say("There are 389 active users."))
        if body is None:
            body = {"question": "How many active users?"}
        return chat.handle_request(body, origin, allowed, model)

    def test_no_allowed_origins_means_every_request_is_refused(self):
        status, payload = self._handle(allowed="")
        self.assertEqual(status, 403)
        self.assertEqual(payload["error"], "origins_not_configured")

    def test_other_origins_are_refused(self):
        status, payload = self._handle(origin="https://elsewhere.example")
        self.assertEqual(status, 403)
        self.assertEqual(payload["error"], "forbidden")

    def test_no_provider_configured_returns_503(self):
        status, payload = self._handle(model=None)
        self.assertEqual(status, 503)
        self.assertEqual(payload["error"], "model_not_configured")

    def test_body_must_be_an_object(self):
        status, payload = self._handle(body=["How many?"])
        self.assertEqual(status, 400)

    def test_success_returns_the_payload(self):
        status, payload = self._handle()
        self.assertEqual(status, 200)
        self.assertEqual(payload["status"], "answered")

    def test_model_failure_does_not_leak_internals(self):
        def explode(messages):
            raise RuntimeError("secret key sk-123 leaked in a traceback")

        with contextlib.redirect_stderr(io.StringIO()):
            status, payload = self._handle(model=ScriptedModel(explode))
        self.assertEqual(status, 502)
        self.assertNotIn("sk-123", json.dumps(payload))

    def test_model_provider_is_read_from_the_environment(self):
        import os

        os.environ.pop("CHAT_PROVIDER", None)
        self.assertIsNone(chat.model_from_env())
        os.environ["CHAT_PROVIDER"] = "not_registered"
        try:
            self.assertIsNone(chat.model_from_env())
        finally:
            os.environ.pop("CHAT_PROVIDER", None)


class GoldenThroughTheLoopTests(unittest.TestCase):
    """Each golden question, asked through the loop by a model that sends the golden query."""

    @classmethod
    def setUpClass(cls):
        cls.questions = yaml.safe_load(GOLDEN.read_text())["questions"]

    def _model_for(self, item):
        expected = item["expect"].get("rows")

        def respond(messages):
            last = messages[-1]
            if last["role"] == "user":
                return ask(item["query"])
            content = json.loads(last["content"])
            if "error" in content:
                return say("I can't answer that from the available data.")
            if expected is None:
                return say("I can't answer that from the available data.")
            values = []
            for row in expected:
                values.append(", ".join(str(value) for value in row.values()))
            return say("Result: " + "; ".join(values) + ".")

        return ScriptedModel(respond)

    def test_every_golden_question_runs_through_the_loop(self):
        for item in self.questions:
            with self.subTest(item["id"]):
                payload = chat.answer(item["question"], self._model_for(item))
                if "refuse" in item["expect"]:
                    self.assertEqual(payload["status"], "declined", payload)
                    self.assertEqual(payload["refusals"], [item["expect"]["refuse"]])
                    continue
                self.assertEqual(payload["status"], "answered", payload)
                _assert_rows(self, payload["rows"], item["expect"]["rows"])
                note = item["expect"].get("note_contains")
                if note:
                    self.assertTrue(any(note.lower() in text.lower() for text in payload["notes"]))


if __name__ == "__main__":
    unittest.main()
